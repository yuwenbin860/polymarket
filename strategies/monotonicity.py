"""
单调性违背套利策略

检测阈值市场的价格倒挂，如 BTC>100k 价格高于 BTC>95k。
这是数学上最确定的套利类型，无需LLM分析。
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from .base import BaseArbitrageStrategy, StrategyMetadata, RiskLevel
from .registry import StrategyRegistry

if TYPE_CHECKING:
    from local_scanner_v2 import Market, ArbitrageOpportunity


@StrategyRegistry.register
class MonotonicityStrategy(BaseArbitrageStrategy):
    """
    单调性违背套利策略

    原理:
    - 对于同一资产的阈值市场（如 BTC>100k, BTC>95k）
    - 如果 BTC > 100k 发生，则 BTC > 95k 必然发生
    - 因此 P(BTC>100k) <= P(BTC>95k)
    - 当这个不等式违背时，存在套利机会
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="monotonicity",
            name="单调性违背套利",
            name_en="Monotonicity Violation",
            description="检测阈值市场的价格倒挂（如 BTC>100k 价格高于 BTC>95k）",
            priority=1,  # 最高优先级 - 数学验证
            requires_llm=False,
            domains=["crypto"],
            risk_level=RiskLevel.LOW,
            min_profit_threshold=1.0,
            icon="📊",
            help_text="适用于加密货币阈值市场，通过数学关系验证套利机会",
            tags=["threshold", "crypto", "math-based"],
            help_detail="""检测原理: 检测阈值市场的价格倒挂现象
适用条件: 加密货币阈值市场（如 BTC>100k, ETH>5k）
风险等级: 低（数学验证，无需LLM）

单调性原理:
- 如果条件A比条件B更严格（如 BTC>100k 比 BTC>95k 更难实现）
- 则 P(A) <= P(B) 必然成立
- 当 P(A) > P(B) 时，存在套利机会""",
            example="""示例: BTC>100k 价格 65¢，BTC>95k 价格 60¢
违背: P(>100k) = 0.65 > P(>95k) = 0.60
套利: 买入 BTC>95k YES (60¢)，卖出 BTC>100k YES (65¢)
收益: 65¢ - 60¢ = 5¢（约8.3%）

注意: 需要验证两个市场属于同一资产且判定规则一致"""
        )

    def scan(
        self,
        markets: List['Market'],
        config: Dict[str, Any],
        progress_callback: Optional[callable] = None
    ) -> List['ArbitrageOpportunity']:
        """
        执行单调性违背扫描

        此方法是对 MonotonicityChecker 的适配器包装
        """
        opportunities = []

        try:
            # 🆕 步骤0: 基础过滤 (Phase 2)
            filtered_markets = self.filter_markets(markets, config)
            if not filtered_markets:
                if progress_callback:
                    progress_callback(2, 2, "无符合条件的有效市场")
                return []

            # 延迟导入避免循环依赖
            from monotonicity_checker import MonotonicityChecker

            checker = MonotonicityChecker()

            if progress_callback:
                progress_callback(0, 2, f"分析 {len(filtered_markets)} 个阈值市场...")

            # 执行扫描
            violations = checker.scan(filtered_markets)

            if progress_callback:
                progress_callback(1, 2, f"发现 {len(violations)} 个违背")

            # 转换为标准格式
            for v in violations:
                if self.validate_opportunity(v):
                    opportunities.append(v)

            if progress_callback:
                progress_callback(2, 2, "单调性检测完成")

        except ImportError as e:
            # MonotonicityChecker 不可用
            if progress_callback:
                progress_callback(1, 1, f"跳过: {e}")

        return opportunities

    def validate_opportunity(self, opportunity: 'ArbitrageOpportunity') -> bool:
        """验证单个机会"""
        # 基本验证
        if not opportunity:
            return False

        # 利润阈值验证 (修正：opportunity.profit_pct 已经是百分数，如 5.0 表示 5%)
        # 如果是 MonotonicityViolation 对象，其 profit_pct 可能是小数 (如 0.05)
        profit_pct = getattr(opportunity, 'profit_pct', 0.0)

        # 统一转换为百分数进行比较
        if profit_pct < 1.0 and profit_pct > 0:
            # 极有可能是小数格式，转换为百分数
            profit_pct *= 100.0

        if profit_pct < self.metadata.min_profit_threshold:
            return False

        return True

    def get_progress_steps(self, market_count: int) -> int:
        """返回进度步骤数"""
        return 2
