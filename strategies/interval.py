"""
区间套利策略

检测区间覆盖关系的套利机会。
适用于价格区间类市场（如 BTC 在 95k-100k 之间）。
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from .base import BaseArbitrageStrategy, StrategyMetadata, RiskLevel
from .registry import StrategyRegistry

if TYPE_CHECKING:
    from local_scanner_v2 import Market, ArbitrageOpportunity


@StrategyRegistry.register
class IntervalStrategy(BaseArbitrageStrategy):
    """
    区间套利策略

    原理:
    - 不相交的区间集合如果覆盖所有可能，形成完备集
    - 如 [0,95k], [95k,100k], [100k,∞] 覆盖所有BTC价格
    - 这些区间的YES价格总和应等于1
    - 也可利用区间包含关系进行套利
    """

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            id="interval",
            name="区间套利",
            name_en="Interval Arbitrage",
            description="区间覆盖关系套利",
            priority=2,
            requires_llm=False,  # 区间解析不需要LLM
            domains=["crypto", "all"],
            risk_level=RiskLevel.LOW,
            min_profit_threshold=1.5,
            icon="📏",
            help_text="适用于价格区间类市场，通过区间覆盖关系验证套利",
            tags=["interval", "math-based", "crypto"],
            help_detail="""检测原理: 利用区间覆盖关系和完备性
适用条件: 价格区间类市场（如 BTC在95k-100k之间）
风险等级: 低（数学验证）

区间关系:
- 区间A包含区间B时，P(A) >= P(B)
- 互不相交的区间如果覆盖所有可能值，价格总和应等于1
- 区间重叠时可能存在套利机会""",
            example="""示例1 - 区间包含:
BTC[90k-100k] 价格 40¢，BTC[95k-100k] 价格 45¢
违背: P([90k-100k]) = 0.40 < P([95k-100k]) = 0.45
套利: 买入大的区间，卖出小的区间

示例2 - 完备区间:
BTC[<95k] 价格 30¢，BTC[95k-100k] 价格 35¢，BTC[>100k] 价格 25¢
总和: 0.30 + 0.35 + 0.25 = 0.90 < 1
套利: 买入所有区间的YES，保证至少一个会赔付$1"""
        )

    def scan(
        self,
        markets: List['Market'],
        config: Dict[str, Any],
        progress_callback: Optional[callable] = None
    ) -> List['ArbitrageOpportunity']:
        """
        执行区间套利扫描
        """
        opportunities = []

        try:
            # 🆕 步骤0: 基础过滤 (Phase 2)
            filtered_markets = self.filter_markets(markets, config)
            if not filtered_markets:
                if progress_callback:
                    progress_callback(1, 1, "无符合条件的有效市场")
                return []

            # 解析区间市场
            interval_markets = self._parse_interval_markets(filtered_markets)

            if progress_callback:
                progress_callback(0, 2, f"发现 {len(interval_markets)} 个区间市场")

            # 按资产分组
            from collections import defaultdict
            by_asset: Dict[str, List] = defaultdict(list)

            for m, interval in interval_markets:
                asset = interval.get('asset', 'unknown')
                by_asset[asset].append((m, interval))

            # 分析每个资产的区间
            for asset, intervals in by_asset.items():
                opps = self._analyze_intervals(asset, intervals, config)
                for opp in opps:
                    if self.validate_opportunity(opp):
                        opportunities.append(opp)

            if progress_callback:
                progress_callback(2, 2, "区间检测完成")

        except Exception as e:
            if progress_callback:
                progress_callback(1, 1, f"错误: {e}")

        return opportunities

    def _parse_interval_markets(
        self,
        markets: List['Market']
    ) -> List[tuple]:
        """解析区间市场"""
        results = []

        for m in markets:
            question = getattr(m, 'question', str(m))
            interval = self._extract_interval(question)
            if interval:
                results.append((m, interval))

        return results

    def _extract_interval(self, question: str) -> Optional[Dict]:
        """
        从问题中提取区间信息

        支持格式:
        - "BTC between $95k and $100k"
        - "ETH price 2000-2500"
        - "SOL will be above $150"
        """
        import re

        # 简化的区间提取
        patterns = [
            # between X and Y
            r'(\w+)\s+(?:price\s+)?between\s+\$?([\d.]+)k?\s+and\s+\$?([\d.]+)k?',
            # X-Y range
            r'(\w+)\s+(?:price\s+)?\$?([\d.]+)k?\s*[-–]\s*\$?([\d.]+)k?',
            # above/below X
            r'(\w+)\s+(?:will\s+be\s+)?(?:above|over)\s+\$?([\d.]+)k?',
        ]

        for pattern in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    return {
                        'asset': groups[0].upper(),
                        'low': float(groups[1]),
                        'high': float(groups[2]),
                        'type': 'range'
                    }
                elif len(groups) == 2:
                    return {
                        'asset': groups[0].upper(),
                        'threshold': float(groups[1]),
                        'type': 'threshold'
                    }

        return None

    def _analyze_intervals(
        self,
        asset: str,
        intervals: List[tuple],
        config: Dict[str, Any]
    ) -> List['ArbitrageOpportunity']:
        """分析同一资产的区间关系"""
        # 占位实现
        return []

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
        return 2
