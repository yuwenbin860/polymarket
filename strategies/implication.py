"""
蕴含关系套利策略

检测 A -> B 的逻辑蕴含关系，当 P(B) < P(A) 时存在套利。
需要 LLM 分析来识别蕴含关系。
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from .base import BaseArbitrageStrategy, StrategyMetadata, RiskLevel
from .registry import StrategyRegistry

if TYPE_CHECKING:
    from local_scanner_v2 import Market, ArbitrageOpportunity


@StrategyRegistry.register
class ImplicationStrategy(BaseArbitrageStrategy):
    """
    蕴含关系套利策略

    原理:
    - 如果事件 A 发生必然导致事件 B 发生（A -> B）
    - 则 P(B) >= P(A)
    - 当 P(B) < P(A) 时，买 B_YES + A_NO 可套利
    - 回报: $1.00（A发生时B必发生，A不发生时有A_NO）
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="implication",
            name="蕴含关系套利",
            name_en="Implication Violation",
            description="A -> B 但 P(B) < P(A) 时存在套利",
            priority=4,
            requires_llm=True,
            domains=["all"],
            risk_level=RiskLevel.MEDIUM,
            min_profit_threshold=2.0,
            icon="➡️",
            help_text="需要LLM分析两个市场之间的逻辑蕴含关系",
            tags=["llm", "logic", "cross-market"],
            help_detail="""检测原理: 利用逻辑蕴含关系 P(B) >= P(A)
适用条件: 两个市场存在逻辑蕴含关系 A -> B
风险等级: 中（需LLM分析蕴含关系）

蕴含关系:
- 如果事件A发生必然导致事件B发生（A蕴含B）
- 则 P(B) >= P(A) 必然成立
- 当 P(B) < P(A) 时，买B的YES + 买A的NO可套利
- 无论哪种结果，收益都至少是$1""",
            example="""示例: "BTC突破100k" 蕴含 "BTC突破95k"
市场A: BTC突破100k，价格 55¢
市场B: BTC突破95k，价格 50¢
违背: P(A) = 0.55 > P(B) = 0.50，但 A->B
套利: 买入B_YES (50¢) + 买入A_NO (45¢) = 95¢
收益:
- 如果BTC>100k: B赔付$1，A_NO赔付0，净赚 5¢
- 如果BTC在95k-100k: B赔付$1，A_NO赔付$1，净赚 $1.05
注意: 需要LLM验证蕴含关系的正确性"""
        )

    def scan(
        self,
        markets: List['Market'],
        config: Dict[str, Any],
        progress_callback: Optional[callable] = None
    ) -> List['ArbitrageOpportunity']:
        """
        执行蕴含关系扫描

        此策略需要 LLM 分析，会调用 LLMAnalyzer
        """
        opportunities = []

        try:
            # 🆕 步骤0: 基础过滤 (Phase 2)
            filtered_markets = self.filter_markets(markets, config)
            if not filtered_markets:
                if progress_callback:
                    progress_callback(1, 1, "无符合条件的有效市场")
                return []

            # 获取相似市场对进行分析
            pairs = self._get_candidate_pairs(filtered_markets, config)
            total_pairs = len(pairs)

            if progress_callback:
                progress_callback(0, total_pairs + 1, "分析市场对...")

            for idx, (m1, m2) in enumerate(pairs):
                # 分析逻辑关系
                result = self._analyze_pair(m1, m2, config)

                if result and result.get('relationship') in ['IMPLIES_AB', 'IMPLIES_BA']:
                    opp = self._check_implication_arbitrage(m1, m2, result, config)
                    if opp and self.validate_opportunity(opp):
                        opportunities.append(opp)

                if progress_callback and (idx + 1) % 10 == 0:
                    progress_callback(idx + 1, total_pairs + 1, f"已分析 {idx + 1}/{total_pairs} 对")

            if progress_callback:
                progress_callback(total_pairs + 1, total_pairs + 1, "蕴含关系检测完成")

        except Exception as e:
            if progress_callback:
                progress_callback(1, 1, f"错误: {e}")

        return opportunities

    def _get_candidate_pairs(
        self,
        markets: List['Market'],
        config: Dict[str, Any]
    ) -> List[tuple]:
        """获取候选市场对 (Phase 5.1: 语义驱动版)"""
        clusters = config.get('clusters', [])
        max_pairs = config.get('max_pairs', 150)
        pairs = []
        seen_pairs = set()

        # 🆕 模式 A: 聚类优先 (高召回率)
        if clusters:
            for cluster in clusters:
                if len(cluster) < 2:
                    continue
                # 在簇内部进行全对匹配
                for i, m1 in enumerate(cluster):
                    for j in range(i + 1, len(cluster)):
                        m2 = cluster[j]
                        pair_id = tuple(sorted([m1.id, m2.id]))
                        if pair_id not in seen_pairs:
                            pairs.append((m1, m2))
                            seen_pairs.add(pair_id)

                if len(pairs) >= max_pairs:
                    return pairs[:max_pairs]

        # 模式 B: 回退到基础采样 (保底逻辑)
        if len(pairs) < 20:
            sample_size = min(len(markets), 30)
            sample = markets[:sample_size]
            for i, m1 in enumerate(sample):
                for m2 in sample[i+1:]:
                    pair_id = tuple(sorted([m1.id, m2.id]))
                    if pair_id not in seen_pairs:
                        pairs.append((m1, m2))
                        seen_pairs.add(pair_id)
                    if len(pairs) >= max_pairs:
                        break

        return pairs[:max_pairs]

    def _analyze_pair(
        self,
        m1: 'Market',
        m2: 'Market',
        config: Dict[str, Any]
    ) -> Optional[Dict]:
        """分析两个市场的逻辑关系"""
        analyzer = config.get('analyzer')
        if not analyzer:
            return None

        try:
            # 调用 LLM 分析两个市场的关系
            return analyzer.analyze_relationship(m1, m2)
        except Exception as e:
            return None

    def _check_implication_arbitrage(
        self,
        m1: 'Market',
        m2: 'Market',
        analysis: Dict,
        config: Dict[str, Any]
    ) -> Optional['ArbitrageOpportunity']:
        """检查蕴含关系套利"""
        relationship = analysis.get('relationship')
        if relationship not in ['IMPLIES_AB', 'IMPLIES_BA']:
            return None

        # 确定前提 (A) 和 结论 (B)
        if relationship == 'IMPLIES_AB':
            antecedent, consequent = m1, m2
        else:
            antecedent, consequent = m2, m1

        # 理论检查: P(B) >= P(A). 违背时 P(B) < P(A)
        # 使用有效价格进行初步筛选
        p_a = antecedent.yes_price
        p_b = consequent.yes_price

        if p_b >= p_a:
            return None

        # 计算套利空间 (理论)
        # 买 B_YES ($p_b) + 买 A_NO ($(1-p_a))
        # 成本 = p_b + 1 - p_a = 1 - (p_a - p_b)
        theoretical_profit = p_a - p_b

        if theoretical_profit < (self.metadata.min_profit_threshold / 100):
            return None

        # 构造 SimpleOpportunity (后续会被 ValidationEngine 增强)
        from datetime import datetime
        try:
            from local_scanner_v2 import ArbitrageOpportunity
        except ImportError:
            return None

        return ArbitrageOpportunity(
            id=f"imp_{antecedent.id}_{consequent.id}",
            type="IMPLICATION_VIOLATION",
            relationship=relationship,
            markets=[
                {"question": antecedent.question, "id": antecedent.id, "yes_price": p_a},
                {"question": consequent.question, "id": consequent.id, "yes_price": p_b}
            ],
            confidence=analysis.get('confidence', 0.8),
            total_cost=p_b + (1 - p_a),
            guaranteed_return=1.0,
            profit=theoretical_profit,
            profit_pct=theoretical_profit / (p_b + 1 - p_a) * 100,
            action=f"买入 {consequent.question[:30]}... YES + 买入 {antecedent.question[:30]}... NO",
            reasoning=analysis.get('reasoning', f"逻辑蕴含 A->B 但 P(B)={p_b} < P(A)={p_a}"),
            edge_cases=analysis.get('edge_cases', []),
            needs_review=["验证蕴含逻辑", "检查结算时间一致性"],
            timestamp=datetime.now().isoformat()
        )

    def validate_opportunity(self, opportunity) -> bool:
        """验证机会"""
        if not opportunity:
            return False

        # 利润阈值验证 (修正：统一转换为百分数进行比较)
        profit_pct = getattr(opportunity, 'profit_pct', 0.0)
        if 0 < profit_pct < 1.0:
            profit_pct *= 100.0

        return profit_pct >= self.metadata.min_profit_threshold

    def get_progress_steps(self, market_count: int) -> int:
        """估算步骤数"""
        # 市场对数量约为 C(n,2) = n*(n-1)/2，但有上限
        return min(100, market_count * (market_count - 1) // 2) + 1
