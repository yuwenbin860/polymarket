"""
等价市场套利策略

检测同一事件不同表述的市场之间的价差。
需要 LLM 分析来识别语义等价关系。
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from .base import BaseArbitrageStrategy, StrategyMetadata, RiskLevel
from .registry import StrategyRegistry

if TYPE_CHECKING:
    from local_scanner_v2 import Market, ArbitrageOpportunity


@StrategyRegistry.register
class EquivalentStrategy(BaseArbitrageStrategy):
    """
    等价市场套利策略

    原理:
    - 不同表述的市场可能描述同一事件
    - 如 "BTC突破100k" vs "比特币价格超过10万美元"
    - 这些市场的价格应该相同
    - 当存在显著价差时，低买高卖
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="equivalent",
            name="等价市场套利",
            name_en="Equivalent Markets",
            description="同事件不同表述存在价差时套利",
            priority=5,
            requires_llm=True,
            domains=["all"],
            risk_level=RiskLevel.MEDIUM,
            min_profit_threshold=3.0,  # 等价市场需要更大价差
            icon="🔄",
            help_text="需要LLM分析两个市场是否语义等价",
            tags=["llm", "semantic", "cross-market"],
            help_detail="""检测原理: 同一事件的不同表述应有相同价格
适用条件: 两个市场描述同一事件的不同表述
风险等级: 中（需LLM验证语义等价性）

等价市场:
- 如果市场A和市场B描述的是同一事件
- 则 P(A) = P(B) 应该成立
- 当 |P(A) - P(B)| > 阈值时，低买高卖可套利""",
            example="""示例: 同一BTC目标价的不同表述
市场A: "BTC突破100k美元"，价格 60¢
市场B: "比特币价格超过10万美元"，价格 55¢
分析: 两个市场描述同一事件，应该等价
套利: 买入市场B的YES (55¢)，卖出市场A的YES (60¢)
收益: 价差 5¢（约9.1%）

注意: 需要LLM验证语义等价性，并检查结算规则一致"""
        )

    def scan(
        self,
        markets: List['Market'],
        config: Dict[str, Any],
        progress_callback: Optional[callable] = None
    ) -> List['ArbitrageOpportunity']:
        """
        执行等价市场扫描
        """
        opportunities = []

        try:
            # 🆕 步骤0: 基础过滤 (Phase 2)
            filtered_markets = self.filter_markets(markets, config)
            if not filtered_markets:
                if progress_callback:
                    progress_callback(1, 1, "无符合条件的有效市场")
                return []

            # 使用语义相似度找候选对
            pairs = self._find_similar_pairs(filtered_markets, config)
            total_pairs = len(pairs)

            if progress_callback:
                progress_callback(0, total_pairs + 1, "分析等价市场...")

            for idx, (m1, m2, similarity) in enumerate(pairs):
                # 分析是否等价
                if self._is_equivalent(m1, m2, config):
                    opp = self._check_price_spread(m1, m2, config)
                    if opp and self.validate_opportunity(opp):
                        opportunities.append(opp)

                if progress_callback and (idx + 1) % 10 == 0:
                    progress_callback(idx + 1, total_pairs + 1, f"已分析 {idx + 1}/{total_pairs} 对")

            if progress_callback:
                progress_callback(total_pairs + 1, total_pairs + 1, "等价市场检测完成")

        except Exception as e:
            if progress_callback:
                progress_callback(1, 1, f"错误: {e}")

        return opportunities

    def _find_similar_pairs(
        self,
        markets: List['Market'],
        config: Dict[str, Any]
    ) -> List[tuple]:
        """使用语义聚类或关键词相似度找相似候选对 (Phase 5.1)"""
        clusters = config.get('clusters', [])
        pairs = []
        seen_pairs = set()

        # 🆕 模式 A: 聚类优先 (语义相关度最高)
        if clusters:
            for cluster in clusters:
                if len(cluster) < 2:
                    continue
                for i, m1 in enumerate(cluster):
                    for j in range(i + 1, len(cluster)):
                        m2 = cluster[j]
                        pair_id = tuple(sorted([m1.id, m2.id]))
                        if pair_id not in seen_pairs:
                            # 这里不再需要计算 jaccard，因为聚类本身就是基于向量相似度的
                            pairs.append((m1, m2, 1.0))
                            seen_pairs.add(pair_id)
                if len(pairs) >= 50:
                    break

        # 模式 B: 回退到关键词匹配
        if len(pairs) < 10:
            sample_size = min(len(markets), 40)
            sample = markets[:sample_size]
            for i, m1 in enumerate(sample):
                for m2 in sample[i+1:]:
                    pair_id = tuple(sorted([m1.id, m2.id]))
                    if pair_id in seen_pairs:
                        continue

                    q1 = set(m1.question.lower().split())
                    q2 = set(m2.question.lower().split())
                    intersection = q1.intersection(q2)
                    union = q1.union(q2)
                    sim = len(intersection) / len(union) if union else 0

                    if sim > 0.5:
                        pairs.append((m1, m2, sim))
                        seen_pairs.add(pair_id)

        return sorted(pairs, key=lambda x: x[2], reverse=True)[:30]

    def _is_equivalent(
        self,
        m1: 'Market',
        m2: 'Market',
        config: Dict[str, Any]
    ) -> bool:
        """调用 LLM 判断是否语义等价"""
        analyzer = config.get('analyzer')
        if not analyzer:
            return False

        try:
            result = analyzer.analyze_relationship(m1, m2)
            config['_last_analysis'] = result # 暂存分析结果供下一步使用
            return result.get('relationship') == 'EQUIVALENT' and result.get('confidence', 0) >= 0.8
        except Exception:
            return False

    def _check_price_spread(
        self,
        m1: 'Market',
        m2: 'Market',
        config: Dict[str, Any]
    ) -> Optional['ArbitrageOpportunity']:
        """检查价差并生成套利机会"""
        analysis = config.get('_last_analysis', {})

        p1 = m1.yes_price
        p2 = m2.yes_price

        spread = abs(p1 - p2)
        if spread < (self.metadata.min_profit_threshold / 100):
            return None

        # 确定买卖方向
        if p1 < p2:
            low_m, high_m = m1, m2
        else:
            low_m, high_m = m2, m1

        from datetime import datetime
        try:
            from local_scanner_v2 import ArbitrageOpportunity
        except ImportError:
            return None

        return ArbitrageOpportunity(
            id=f"eqv_{m1.id}_{m2.id}",
            type="EQUIVALENT_MARKETS_SPREAD",
            relationship="equivalent",
            markets=[
                {"question": low_m.question, "id": low_m.id, "yes_price": low_m.yes_price},
                {"question": high_m.question, "id": high_m.id, "yes_price": high_m.yes_price}
            ],
            confidence=analysis.get('confidence', 0.9),
            total_cost=low_m.yes_price + (1 - high_m.yes_price),
            guaranteed_return=1.0,
            profit=spread,
            profit_pct=spread / (low_m.yes_price + 1 - high_m.yes_price) * 100,
            action=f"买入低价市场 {low_m.id} YES + 买入高价市场 {high_m.id} NO",
            reasoning=analysis.get('reasoning', f"语义等价但存在 {spread:.2f} 价差"),
            edge_cases=analysis.get('edge_cases', []),
            needs_review=["验证结算规则一致性", "检查成交深度"],
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
        return min(50, market_count // 2) + 1
