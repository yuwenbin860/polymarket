"""
完备集套利策略

检测互斥完备集的定价不足：
当一组互斥且完备的结果的YES价格总和小于1时，存在套利机会。
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from .base import BaseArbitrageStrategy, StrategyMetadata, RiskLevel
from .registry import StrategyRegistry

if TYPE_CHECKING:
    from local_scanner_v2 import Market, ArbitrageOpportunity


@StrategyRegistry.register
class ExhaustiveSetStrategy(BaseArbitrageStrategy):
    """
    完备集套利策略

    原理:
    - 对于同一事件的多个互斥结果（如总统候选人A、B、C）
    - 这些结果必有且仅有一个发生
    - 因此 P(A) + P(B) + P(C) = 1
    - 当 sum(YES_prices) < 1 时，买入所有YES可保证获利
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="exhaustive",
            name="完备集套利",
            name_en="Exhaustive Set",
            description="互斥完备集价格总和 < 1 时存在套利",
            priority=3,
            requires_llm=False,  # 规则验证即可
            domains=["all"],
            risk_level=RiskLevel.MEDIUM,
            min_profit_threshold=2.0,
            icon="🎯",
            help_text="需要验证结果互斥且完备，适用于多选项市场",
            tags=["multi-option", "event-based"],
            help_detail="""检测原理: 互斥完备集的YES价格总和应等于1
适用条件: 多选项市场（如选举候选人、比赛结果）
风险等级: 中（需验证互斥性和完备性）

完备集条件:
- 互斥: 所有结果中最多只有一个发生
- 完备: 所有结果中至少有一个发生
- 当 sum(P(i)) < 1 时，买入所有YES可套利""",
            example="""示例: 美国总统大选
- 民主党获胜 价格 45¢
- 共和党获胜 价格 42¢
- 第三方获胜 价格 5¢
总和: 0.45 + 0.42 + 0.05 = 0.92 < 1
套利: 买入所有三个选项的YES，总成本 92¢
收益: 三者必有一个赔付$1，利润 8¢（约8.7%）

注意: 需要验证市场规则确保结果互斥且完备"""
        )

    def scan(
        self,
        markets: List['Market'],
        config: Dict[str, Any],
        progress_callback: Optional[callable] = None
    ) -> List['ArbitrageOpportunity']:
        """
        执行完备集套利扫描
        """
        opportunities = []

        try:
            # 🆕 步骤0: 基础过滤 (Phase 2)
            filtered_markets = self.filter_markets(markets, config)
            if not filtered_markets:
                if progress_callback:
                    progress_callback(1, 1, "无符合条件的有效市场")
                return []

            # 按 event_id 分组
            from collections import defaultdict
            events: Dict[str, List] = defaultdict(list)

            for m in filtered_markets:
                if hasattr(m, 'event_id') and m.event_id:
                    events[m.event_id].append(m)

            total_events = len(events)
            if progress_callback:
                progress_callback(0, total_events + 1, f"分析 {total_events} 个完备集...")

            # 分析每个事件
            for idx, (event_id, event_markets) in enumerate(events.items()):
                if len(event_markets) < 2:
                    continue

                opp = self._check_exhaustive_set(event_markets, config)
                if opp and self.validate_opportunity(opp):
                    opportunities.append(opp)

                if progress_callback:
                    progress_callback(idx + 1, total_events + 1, f"已检查 {idx + 1}/{total_events} 事件")

            if progress_callback:
                progress_callback(total_events + 1, total_events + 1, "完备集检测完成")

        except Exception as e:
            if progress_callback:
                progress_callback(1, 1, f"错误: {e}")

        return opportunities

    def _check_exhaustive_set(
        self,
        markets: List['Market'],
        config: Dict[str, Any]
    ) -> Optional['ArbitrageOpportunity']:
        """检查市场组是否形成可套利的完备集"""
        try:
            # 使用订单簿买入价计算实际成本
            total_yes = sum(
                getattr(m, 'effective_buy_price', 0.5)
                for m in markets
            )

            min_profit = config.get('min_profit_pct', 2.0) / 100
            threshold = 1.0 - min_profit

            if total_yes < threshold:
                # 存在套利机会 - 创建机会对象
                from dataclasses import dataclass
                from datetime import datetime

                profit = 1.0 - total_yes
                profit_pct = profit / total_yes * 100 if total_yes > 0 else 0

                # 构造简化的机会对象
                # 实际实现应该使用正式的 ArbitrageOpportunity 类
                @dataclass
                class SimpleOpportunity:
                    id: str = ""
                    type: str = "EXHAUSTIVE_SET_UNDERPRICED"
                    relationship: str = "exhaustive_set"
                    confidence: float = 0.95
                    total_cost: float = 0.0
                    guaranteed_return: float = 1.0
                    profit: float = 0.0
                    profit_pct: float = 0.0
                    action: str = ""
                    reasoning: str = ""
                    markets: List = None
                    edge_cases: List = None
                    needs_review: List = None
                    timestamp: str = ""

                event_id = markets[0].event_id if hasattr(markets[0], 'event_id') else "unknown"
                return SimpleOpportunity(
                    id=f"exh_{event_id}",
                    total_cost=total_yes,
                    profit=profit,
                    profit_pct=profit_pct,
                    action=f"买入所有 {len(markets)} 个市场的 YES",
                    reasoning=f"完备集价格总和 {total_yes:.4f} < 1，利润空间 {profit_pct:.2f}%",
                    markets=[{"question": getattr(m, 'question', str(m))} for m in markets],
                    edge_cases=[],
                    needs_review=["验证结果互斥且完备"],
                    timestamp=datetime.now().isoformat()
                )

            return None

        except Exception:
            return None

    def validate_opportunity(self, opportunity) -> bool:
        """验证机会有效性"""
        if not opportunity:
            return False

        # 利润阈值验证 (修正：统一转换为百分数进行比较)
        profit_pct = getattr(opportunity, 'profit_pct', 0.0)
        if 0 < profit_pct < 1.0:
            profit_pct *= 100.0

        return profit_pct >= self.metadata.min_profit_threshold

    def get_progress_steps(self, market_count: int) -> int:
        """估算进度步骤"""
        # 粗略估计事件数约为市场数的 1/3
        return max(1, market_count // 3) + 1
