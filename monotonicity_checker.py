"""
MonotonicityChecker - 单调性违背套利检测器

核心理论：
对于标量变量 X（如BTC价格），累积分布函数必须单调非减。
即：若 k_1 < k_2，则 P(X > k_1) >= P(X > k_2)

当市场出现"价格倒挂"（高阈值合约价格 > 低阈值合约价格），
则存在无风险套利机会。

使用方法：
    from monotonicity_checker import MonotonicityChecker

    checker = MonotonicityChecker()
    markets = client.fetch_crypto_markets()
    violations = checker.scan(markets)

    for v in violations:
        print(f"发现套利: {v.asset} {v.low_threshold} vs {v.high_threshold}")
        print(f"利润: {v.profit_pct:.2%}, APY: {v.apy:.1%}")

扩展功能：
    - 多级违背检测（检测所有非相邻对）
    - 区间-阈值混合检测
    - 跨日期时间蕴含检测
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime
from collections import defaultdict
from enum import Enum

# 设置日志
logger = logging.getLogger(__name__)


class ThresholdDirection(Enum):
    """阈值方向"""
    ABOVE = "above"  # X > threshold (价格超过阈值)
    BELOW = "below"  # X < threshold (价格低于阈值)
    RANGE = "range"  # threshold_lower <= X <= threshold_upper (区间)


class MarketType(Enum):
    """市场类型"""
    THRESHOLD = "threshold"  # 阈值型市场 (above/below)
    INTERVAL = "interval"    # 区间型市场


@dataclass
class ThresholdInfo:
    """阈值市场信息"""
    market: any  # Market 对象
    asset: str  # 资产名称 (btc, eth, sol, etc.)
    threshold_value: float  # 阈值数值
    direction: ThresholdDirection  # above 或 below
    end_date: str  # 结算日期
    yes_price: float  # YES 合约价格
    best_bid: float  # 最佳买价 (YES)
    best_ask: float  # 最佳卖价 (YES)
    # 单调性套利修复: 增加 NO token 价格字段
    no_best_bid: float = 0.0  # NO 最佳买价
    no_best_ask: float = 0.0  # NO 最佳卖价
    # 区间市场支持
    market_type: MarketType = MarketType.THRESHOLD  # 市场类型
    interval_lower: float = None  # 区间下界（仅区间市场）
    interval_upper: float = None  # 区间上界（仅区间市场）

    @property
    def effective_price(self) -> float:
        """有效价格（优先使用中间价）"""
        if self.best_bid > 0 and self.best_ask > 0:
            price = (self.best_bid + self.best_ask) / 2
        else:
            price = self.yes_price
        # 验证价格有效性: 必须在 (0, 1] 范围内
        if not (0 < price <= 1):
            return 0.0  # 标记为无效价格
        return price

    @property
    def buy_price(self) -> float:
        """YES买入价格"""
        price = self.best_ask if self.best_ask > 0 else self.yes_price
        if not (0 < price <= 1):
            return 0.0
        return price

    @property
    def sell_price(self) -> float:
        """YES卖出价格"""
        price = self.best_bid if self.best_bid > 0 else self.yes_price
        if not (0 < price <= 1):
            return 0.0
        return price

    @property
    def no_buy_price(self) -> float:
        """NO买入价格（真实ask价或降级计算）"""
        if self.no_best_ask > 0:
            return self.no_best_ask
        # 降级：使用中间价反推（不准确，会有警告）
        return 1.0 - self.yes_price

    @property
    def is_interval_market(self) -> bool:
        """是否为区间市场"""
        return self.market_type == MarketType.INTERVAL

    @property
    def threshold_str(self) -> str:
        """阈值字符串表示"""
        if self.is_interval_market:
            if self.interval_lower is not None and self.interval_upper is not None:
                return f"[{self.interval_lower:,.0f}, {self.interval_upper:,.0f}]"
            elif self.interval_lower is not None:
                return f">={self.interval_lower:,.0f}"
            elif self.interval_upper is not None:
                return f"<={self.interval_upper:,.0f}"
        return f"{self.threshold_value:,.0f}"


@dataclass
class IntervalThresholdInfo(ThresholdInfo):
    """
    区间市场信息（扩展自 ThresholdInfo）

    区间市场是指预测价格在某个范围内的市场，如：
    - "BTC in $80k-$100k by end of month"
    - "ETH between $3500 and $4000"

    区间市场的单调性约束：
    - P(a <= X <= b) <= P(X > a)  （区间概率应小于等于高于下界的概率）
    - P(a <= X <= b) <= P(X < b)  （区间概率应小于等于低于上界的概率）
    - P(a <= X <= b) + P(X < a) + P(X > b) = 1  （完备集）
    """
    interval_lower: float = 0.0  # 区间下界
    interval_upper: float = 0.0  # 区间上界

    def __post_init__(self):
        """初始化后设置市场类型"""
        self.market_type = MarketType.INTERVAL
        self.direction = ThresholdDirection.RANGE

    @property
    def interval_width(self) -> float:
        """区间宽度"""
        return self.interval_upper - self.interval_lower

    @property
    def interval_midpoint(self) -> float:
        """区间中点"""
        return (self.interval_lower + self.interval_upper) / 2

    def overlaps_with(self, other: 'IntervalThresholdInfo') -> bool:
        """检查两个区间是否重叠"""
        return not (self.interval_upper < other.interval_lower or
                    self.interval_lower > other.interval_upper)

    def contains_threshold(self, threshold: float) -> bool:
        """检查区间是否包含某个阈值"""
        return self.interval_lower <= threshold <= self.interval_upper


@dataclass
class MonotonicityViolation:
    """单调性违背记录"""
    asset: str  # 资产名称
    end_date: str  # 结算日期
    direction: ThresholdDirection  # 阈值方向

    # 低阈值市场 (应该价格更高)
    low_threshold: float
    low_market: ThresholdInfo

    # 高阈值市场 (应该价格更低，但实际更高 = 违背)
    high_threshold: float
    high_market: ThresholdInfo

    # 价格倒挂幅度
    price_inversion: float  # high_price - low_price (正数表示违背)

    # 套利计算结果
    total_cost: float = 0.0
    guaranteed_return: float = 1.0
    profit: float = 0.0
    profit_pct: float = 0.0
    apy: float = 0.0
    days_to_settlement: int = 0

    # 风险提示
    warnings: List[str] = field(default_factory=list)

    # 区间市场支持
    violation_type: str = "threshold"  # 违背类型: threshold, interval_threshold, interval_interval, temporal

    def __repr__(self):
        return (f"MonotonicityViolation({self.asset} {self.direction.value}: "
                f"{self.low_threshold} @ {self.low_market.effective_price:.3f} vs "
                f"{self.high_threshold} @ {self.high_market.effective_price:.3f}, "
                f"profit={self.profit_pct:.2%})")

    @property
    def violation_summary(self) -> str:
        """违背摘要"""
        if self.violation_type == "interval_threshold":
            return f"区间-阈值违背: {self.low_market.threshold_str} @ {self.low_market.effective_price:.3f} vs {self.high_market.threshold_str} @ {self.high_market.effective_price:.3f}"
        elif self.violation_type == "interval_interval":
            return f"区间-区间违背"
        elif self.violation_type == "temporal":
            return f"时间蕴含违背"
        return f"阈值违背: {self.low_threshold:,.0f} vs {self.high_threshold:,.0f}"


class MonotonicityChecker:
    """
    单调性违背检测器

    核心功能：
    1. 从市场问题中提取阈值信息（资产、阈值、方向）
    2. 按资产和结算日期分组形成"阶梯"结构
    3. 检测价格倒挂（单调性违背）
    4. 计算套利机会和APY
    """

    # 资产识别模式
    ASSET_PATTERNS = {
        'btc': [r'\bbitcoin\b', r'\bbtc\b'],
        'eth': [r'\bethereum\b', r'\beth\b'],
        'sol': [r'\bsolana\b', r'\bsol\b'],
        'xrp': [r'\bripple\b', r'\bxrp\b'],
        'doge': [r'\bdogecoin\b', r'\bdoge\b'],
        'ada': [r'\bcardano\b', r'\bada\b'],
        'bnb': [r'\bbinance\b', r'\bbnb\b'],
        'avax': [r'\bavalanche\b', r'\bavax\b'],
        'dot': [r'\bpolkadot\b', r'\bdot\b'],
        'matic': [r'\bpolygon\b', r'\bmatic\b'],
        'link': [r'\bchainlink\b', r'\blink\b'],
        'atom': [r'\bcosmos\b', r'\batom\b'],
        'ltc': [r'\blitecoin\b', r'\bltc\b'],
        'uni': [r'\buniswap\b', r'\buni\b'],
    }

    # 阈值提取模式（扩展格式支持）
    THRESHOLD_PATTERNS = [
        # ==================== ABOVE 方向 ====================
        # "above $100,000" or "above 100,000" or "above $100k"
        (r'above\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.ABOVE),
        # "over $100,000"
        (r'over\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.ABOVE),
        # "greater than $100,000"
        (r'greater\s+than\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.ABOVE),
        # "> $100,000" or ">100k" or ">$100k"
        (r'>\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.ABOVE),
        # "hit $100,000" / "reach $100,000"
        (r'(?:hit|reach|hits|reaches)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.ABOVE),
        # "surpass $100,000" / "exceed $100,000"
        (r'(?:surpass|exceed|exceeds|surpasses)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.ABOVE),
        # "cross $100,000" / "tops $100,000"
        (r'(?:cross|crosses|tops)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.ABOVE),
        # "at least $100,000" / "$100,000 or higher"
        (r'(?:at\s+least|or\s+higher)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.ABOVE),
        # "minimum $100,000" / "$100,000 minimum"
        (r'(?:minimum|min)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.ABOVE),
        # "triple digits" (特殊: 价格达到3位数，即 >= $100)
        (r'triple\s+digits?', ThresholdDirection.ABOVE),
        # "four digits" (价格达到4位数，即 >= $1,000)
        (r'four\s+digits?', ThresholdDirection.ABOVE),

        # ==================== BELOW 方向 ====================
        # "below $100,000"
        (r'below\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.BELOW),
        # "under $100,000"
        (r'under\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.BELOW),
        # "< $100,000" or "<100k"
        (r'<\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.BELOW),
        # "fall below $100,000" / "drop below $100,000"
        (r'(?:fall|drop|drops|falls)\s+(?:below|under)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.BELOW),
        # "at most $100,000" / "$100,000 or less"
        (r'(?:at\s+most|or\s+less)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.BELOW),
        # "maximum $100,000" / "$100,000 maximum"
        (r'(?:maximum|max)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', ThresholdDirection.BELOW),
        # "single digits" (特殊: 价格跌到个位数，即 < $10)
        (r'single\s+digit', ThresholdDirection.BELOW),
        # "double digits" (价格跌到两位数，即 < $100)
        (r'double\s+digits?', ThresholdDirection.BELOW),

        # ==================== 区间格式 ====================
        # "between $80,000 and $100,000"
        (r'between\s+\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?\s+and\s+\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', None),  # 特殊处理
        # "$80k-$100k" or "80,000-100,000" (带连字符的范围)
        (r'\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?\s*[-–to]\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K|m|M|b|B|t|T)?', None),  # 特殊处理
    ]

    # 单位换算（扩展支持）
    UNIT_MULTIPLIERS = {
        'k': 1_000, 'K': 1_000,
        'm': 1_000_000, 'M': 1_000_000,
        'b': 1_000_000_000, 'B': 1_000_000_000,
        't': 1_000_000_000_000, 'T': 1_000_000_000_000,
    }

    # 最小价格倒挂阈值（考虑交易成本）
    MIN_INVERSION_THRESHOLD = 0.005  # 0.5%

    # 最小利润阈值
    MIN_PROFIT_THRESHOLD = 0.005  # 0.5%

    def __init__(self, min_inversion: float = None, min_profit: float = None):
        """
        初始化检测器

        Args:
            min_inversion: 最小价格倒挂阈值
            min_profit: 最小利润阈值
        """
        if min_inversion is not None:
            self.MIN_INVERSION_THRESHOLD = min_inversion
        if min_profit is not None:
            self.MIN_PROFIT_THRESHOLD = min_profit

    def extract_threshold_info(self, market) -> Optional[ThresholdInfo]:
        """
        从市场中提取阈值信息（扩展支持区间市场）

        Args:
            market: Market 对象

        Returns:
            ThresholdInfo 或 IntervalThresholdInfo，或 None（如果不是阈值市场）
        """
        question = (getattr(market, 'question', None) or getattr(market, 'title', '')).lower()

        # 1. 识别资产
        asset = self._detect_asset(question)
        if not asset:
            return None

        # 2. 提取阈值和方向
        threshold_result = self._extract_threshold(question)
        if not threshold_result:
            return None

        threshold_value, direction = threshold_result

        # 3. 根据方向类型构建相应的对象
        end_date = market.end_date.split('T')[0] if market.end_date else ""
        yes_price = market.yes_price
        best_bid = getattr(market, 'best_bid', 0.0)
        best_ask = getattr(market, 'best_ask', 0.0)
        no_best_bid = getattr(market, 'best_bid_no', 0.0)
        no_best_ask = getattr(market, 'best_ask_no', 0.0)

        # 检查是否为区间市场（返回的是元组）
        if direction == ThresholdDirection.RANGE and isinstance(threshold_value, tuple):
            # 区间市场: (lower_value, upper_value)
            lower_val, upper_val = threshold_value

            # 尝试使用 interval_parser_v2 获取更精确的区间信息
            interval_lower, interval_upper = self._parse_interval_from_market(market, lower_val, upper_val)

            return IntervalThresholdInfo(
                market=market,
                asset=asset,
                threshold_value=lower_val,  # 使用下界作为主阈值
                direction=direction,
                end_date=end_date,
                yes_price=yes_price,
                best_bid=best_bid,
                best_ask=best_ask,
                no_best_bid=no_best_bid,
                no_best_ask=no_best_ask,
                market_type=MarketType.INTERVAL,
                interval_lower=interval_lower,
                interval_upper=interval_upper,
            )

        # 常规阈值市场
        return ThresholdInfo(
            market=market,
            asset=asset,
            threshold_value=threshold_value,
            direction=direction,
            end_date=end_date,
            yes_price=yes_price,
            best_bid=best_bid,
            best_ask=best_ask,
            no_best_bid=no_best_bid,
            no_best_ask=no_best_ask,
            market_type=MarketType.THRESHOLD,
        )

    def _parse_interval_from_market(self, market, default_lower: float, default_upper: float) -> Tuple[float, float]:
        """
        从市场对象解析区间信息

        优先使用 interval_parser_v2，失败则使用默认值

        Args:
            market: Market 对象
            default_lower: 默认下界
            default_upper: 默认上界

        Returns:
            (lower, upper) 元组
        """
        # 尝试使用 interval_parser_v2
        try:
            from interval_parser_v2 import IntervalParser
            parser = IntervalParser()

            # 优先从 groupItemTitle 解析
            group_title = getattr(market, 'group_item_title', None) or getattr(market, 'groupItemTitle', None)
            question = getattr(market, 'question', None) or getattr(market, 'title', '')

            if group_title:
                interval = parser.parse(group_item_title=group_title)
                if interval and interval.type != 'unknown':
                    if interval.type == 'range':
                        return (interval.lower, interval.upper)
                    elif interval.type == 'above':
                        return (interval.lower, float('inf'))
                    elif interval.type == 'below':
                        return (float('-inf'), interval.upper)

            if question:
                interval = parser.parse(question=question)
                if interval and interval.type != 'unknown':
                    if interval.type == 'range':
                        return (interval.lower, interval.upper)
                    elif interval.type == 'above':
                        return (interval.lower, float('inf'))
                    elif interval.type == 'below':
                        return (float('-inf'), interval.upper)
        except Exception:
            pass

        # 使用默认值
        return (default_lower, default_upper)

    def _detect_asset(self, text: str) -> Optional[str]:
        """检测文本中的资产类型"""
        text_lower = text.lower()
        for asset, patterns in self.ASSET_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return asset
        return None

    def _extract_threshold(self, text: str) -> Optional[Tuple[float, ThresholdDirection]]:
        """
        提取阈值和方向（扩展版本，支持更多格式）

        特殊格式处理：
        - "triple digits" -> 100 (表示价格 >= $100)
        - "single digits" -> 10 (表示价格 < $10)
        - 区间格式 -> 返回 (lower_value, None) 表示需要特殊处理
        """
        text_lower = text.lower()

        # 特殊格式：triple digits, four digits 等
        if re.search(r'triple\s+digits?', text_lower):
            return (100.0, ThresholdDirection.ABOVE)  # >= $100
        if re.search(r'four\s+digits?', text_lower):
            return (1_000.0, ThresholdDirection.ABOVE)  # >= $1,000
        if re.search(r'five\s+digits?', text_lower):
            return (10_000.0, ThresholdDirection.ABOVE)  # >= $10,000
        if re.search(r'single\s+digit', text_lower):
            return (10.0, ThresholdDirection.BELOW)  # < $10
        if re.search(r'double\s+digits?', text_lower):
            return (100.0, ThresholdDirection.BELOW)  # < $100

        for pattern, direction in self.THRESHOLD_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                # 处理区间格式（两个值）
                if direction is None and len(match.groups()) >= 2:
                    lower_str = match.group(1).replace(',', '') if match.group(1) else '0'
                    upper_str = match.group(2).replace(',', '') if match.group(2) else '0'
                    # 区间格式特殊处理：返回区间信息
                    # 这里我们简单处理，返回 (lower_value, RANGE)
                    # 实际使用时，需要检测这是一个区间市场
                    try:
                        lower_val = self._parse_value_with_unit(lower_str, text_lower, match, 1)
                        upper_val = self._parse_value_with_unit(upper_str, text_lower, match, 2)
                        # 对于区间市场，我们返回 lower，并标记为 RANGE
                        return ((lower_val, upper_val), ThresholdDirection.RANGE)
                    except (ValueError, IndexError):
                        continue

                value_str = match.group(1).replace(',', '') if match.group(1) else ''
                if not value_str:
                    continue

                value = self._parse_value_with_unit(value_str, text_lower, match, 1)
                return (value, direction)

        return None

    def _parse_value_with_unit(self, value_str: str, text: str, match, group_idx: int) -> float:
        """
        解析带有单位的数值

        Args:
            value_str: 数值字符串
            text: 完整文本
            match: 正则匹配对象
            group_idx: 组索引

        Returns:
            解析后的数值
        """
        try:
            base_value = float(value_str)
        except ValueError:
            return 0.0

        # 检查单位后缀
        # 从匹配位置开始查找单位字符
        match_end = match.end(group_idx) if hasattr(match, 'end') else len(value_str)
        context = text[max(0, match_end - 5):match_end + 5]

        for unit, multiplier in self.UNIT_MULTIPLIERS.items():
            if unit in context.lower():
                return base_value * multiplier

        # 默认检查 k 后缀（向后兼容）
        if 'k' in context.lower():
            return base_value * 1000

        return base_value

    def _deduplicate_thresholds(self, threshold_infos: List[ThresholdInfo]) -> List[ThresholdInfo]:
        """
        去除重复阈值，保留流动性最好的（价格最高的，因为价格高意味着流动性好）

        对于相同的 (asset, end_date, direction, threshold_value)，
        只保留 effective_price 最高的一个。

        Args:
            threshold_infos: ThresholdInfo 列表

        Returns:
            去重后的 ThresholdInfo 列表
        """
        threshold_map = {}

        for info in threshold_infos:
            # 对于区间市场，使用完整的区间作为key
            if info.is_interval_market:
                key = (
                    info.asset,
                    info.end_date,
                    info.direction.value,
                    info.interval_lower,
                    info.interval_upper
                )
            else:
                key = (
                    info.asset,
                    info.end_date,
                    info.direction.value,
                    info.threshold_value
                )

            # 保留 effective_price 更高的（流动性更好）
            if key not in threshold_map:
                threshold_map[key] = info
            else:
                if info.effective_price > threshold_map[key].effective_price:
                    threshold_map[key] = info

        return list(threshold_map.values())

    def group_ladder_markets(self, threshold_infos: List[ThresholdInfo]) -> Dict[str, List[ThresholdInfo]]:
        """
        按资产、日期、方向分组形成"阶梯"结构

        Args:
            threshold_infos: ThresholdInfo 列表

        Returns:
            {group_key: [ThresholdInfo sorted by threshold]}
        """
        # 先去重
        deduplicated = self._deduplicate_thresholds(threshold_infos)

        groups = defaultdict(list)

        for info in deduplicated:
            # 组合键: asset_date_direction
            group_key = f"{info.asset}_{info.end_date}_{info.direction.value}"
            groups[group_key].append(info)

        # 按阈值排序每个组
        for key in groups:
            groups[key].sort(key=lambda x: x.threshold_value)

        return dict(groups)

    def check_monotonicity(self, ladder: List[ThresholdInfo]) -> List[MonotonicityViolation]:
        """
        检查阶梯市场的单调性（仅检测相邻对，保持向后兼容）

        对于 ABOVE 方向：高阈值价格应该 <= 低阈值价格
        对于 BELOW 方向：高阈值价格应该 >= 低阈值价格

        Args:
            ladder: 按阈值排序的 ThresholdInfo 列表

        Returns:
            违背列表
        """
        return self._check_adjacent_violations(ladder)

    def _check_adjacent_violations(self, ladder: List[ThresholdInfo]) -> List[MonotonicityViolation]:
        """检测相邻阈值对的违背"""
        if len(ladder) < 2:
            return []

        violations = []
        direction = ladder[0].direction

        for i in range(len(ladder) - 1):
            low = ladder[i]
            high = ladder[i + 1]

            low_price = low.effective_price
            high_price = high.effective_price

            # 检查单调性违背
            if direction == ThresholdDirection.ABOVE:
                # ABOVE: P(X > k_high) 应该 <= P(X > k_low)
                # 即高阈值的 YES 价格应该更低
                if high_price > low_price + self.MIN_INVERSION_THRESHOLD:
                    violation = self._create_violation(low, high, high_price - low_price)
                    if violation:
                        violations.append(violation)
            else:
                # BELOW: P(X < k_low) >= P(X < k_high)
                # 即低阈值的 YES 价格应该 >= 高阈值的 YES 价格
                # 违背条件: 高阈值价格 > 低阈值价格
                if high_price > low_price + self.MIN_INVERSION_THRESHOLD:
                    violation = self._create_violation(low, high, high_price - low_price)
                    if violation:
                        violations.append(violation)

        return violations

    def check_multi_level_violations(self, ladder: List[ThresholdInfo]) -> List[MonotonicityViolation]:
        """
        检测阶梯中所有阈值对的违背（包括非相邻对）

        这是多级违背检测的核心方法，可以发现更大的套利机会。

        Args:
            ladder: 按阈值排序的 ThresholdInfo 列表

        Returns:
            所有违背列表，按利润率排序

        示例:
            阶梯: BTC > $100k @ $0.40
                  BTC > $110k @ $0.50  ← 违背1 (vs $100k)
                  BTC > $120k @ $0.65  ← 违背2 (vs $100k，更大利润)

            传统方法只发现 $110k vs $120k 的违背
            多级方法可以发现 $100k vs $120k 的更大违背
        """
        if len(ladder) < 2:
            return []

        violations = []
        direction = ladder[0].direction

        # 检测所有可能的阈值对 (i, j) where i < j
        for i in range(len(ladder)):
            for j in range(i + 1, len(ladder)):
                low = ladder[i]
                high = ladder[j]

                low_price = low.effective_price
                high_price = high.effective_price

                # 检查单调性违背
                if direction == ThresholdDirection.ABOVE:
                    # ABOVE: P(X > k_high) 应该 <= P(X > k_low)
                    if high_price > low_price + self.MIN_INVERSION_THRESHOLD:
                        violation = self._create_violation(low, high, high_price - low_price)
                        if violation:
                            violations.append(violation)
                else:
                    # BELOW: P(X < k_high) 应该 >= P(X < k_low)
                    # 对于 BELOW: k_i < k_j，应该 P(X < k_i) <= P(X < k_j)
                    # 违背: P(X < k_i) > P(X < k_j)
                    if low_price > high_price + self.MIN_INVERSION_THRESHOLD:
                        violation = self._create_violation(high, low, low_price - high_price)
                        if violation:
                            violations.append(violation)

        # 按利润率排序
        violations.sort(key=lambda v: v.profit_pct, reverse=True)
        return violations

    def find_optimal_arbitrage(self, ladder: List[ThresholdInfo]) -> Optional[MonotonicityViolation]:
        """
        在阶梯中寻找最优套利机会

        使用贪心算法找到最大利润的套利对。

        Args:
            ladder: 按阈值排序的 ThresholdInfo 列表

        Returns:
            最优套利机会，或 None

        算法:
            1. 对于 ABOVE 方向: 找 min(YES_price) - max(YES_price) 的最大差值
            2. 对于 BELOW 方向: 找 max(YES_price) - min(YES_price) 的最大差值
        """
        if len(ladder) < 2:
            return None

        direction = ladder[0].direction
        best_violation = None
        max_profit = 0

        for i in range(len(ladder)):
            for j in range(i + 1, len(ladder)):
                low = ladder[i]
                high = ladder[j]

                low_price = low.effective_price
                high_price = high.effective_price

                if direction == ThresholdDirection.ABOVE:
                    # ABOVE: 违背时 high_price > low_price
                    # 套利: 买入 low YES, 卖出 high YES
                    # 利润 = 1 - (low_buy + high_no) = 1 - (low_price + (1 - high_price))
                    #      = high_price - low_price
                    if high_price > low_price + self.MIN_INVERSION_THRESHOLD:
                        arb = self.calculate_arbitrage(low, high)
                        if arb['profit_pct'] > max_profit:
                            max_profit = arb['profit_pct']
                            best_violation = self._create_violation(low, high, high_price - low_price)
                else:
                    # BELOW: P(X < k_low) >= P(X < k_high), 即 low_price >= high_price
                    # 违背条件: high_price > low_price
                    # 套利: 买入 low YES, 卖出 high YES
                    if high_price > low_price + self.MIN_INVERSION_THRESHOLD:
                        arb = self.calculate_arbitrage(low, high)
                        if arb['profit_pct'] > max_profit:
                            max_profit = arb['profit_pct']
                            best_violation = self._create_violation(low, high, high_price - low_price)

        return best_violation

    def _create_violation(self, low_info: ThresholdInfo, high_info: ThresholdInfo,
                          inversion: float) -> Optional[MonotonicityViolation]:
        """创建违背记录并计算套利"""

        # 计算套利
        arb = self.calculate_arbitrage(low_info, high_info)
        if arb['profit_pct'] < self.MIN_PROFIT_THRESHOLD:
            return None

        violation = MonotonicityViolation(
            asset=low_info.asset,
            end_date=low_info.end_date,
            direction=low_info.direction,
            low_threshold=low_info.threshold_value,
            low_market=low_info,
            high_threshold=high_info.threshold_value,
            high_market=high_info,
            price_inversion=inversion,
            total_cost=arb['total_cost'],
            guaranteed_return=arb['guaranteed_return'],
            profit=arb['profit'],
            profit_pct=arb['profit_pct'],
            apy=arb['apy'],
            days_to_settlement=arb['days'],
            warnings=arb['warnings'],
        )

        return violation

    def calculate_arbitrage(self, low_info: ThresholdInfo, high_info: ThresholdInfo) -> Dict:
        """
        计算套利机会

        对于 ABOVE 方向的单调性违背：
        - 买入低阈值的 YES (因为 X > low 的概率更高)
        - 卖出高阈值的 YES (或买入 NO)

        Args:
            low_info: 低阈值市场
            high_info: 高阈值市场

        Returns:
            套利计算结果字典
        """
        warnings = []

        # 使用实际交易价格计算
        # 买入低阈值 YES: 使用 ask 价格
        low_buy_price = low_info.buy_price
        # 买入高阈值 NO: 使用真实的 NO ask 价格（单调性套利修复）
        high_no_price = high_info.no_buy_price

        # 如果没有订单簿数据，添加警告
        if low_info.best_ask == 0:
            warnings.append("低阈值市场无YES订单簿数据，使用参考价")
        if high_info.no_best_ask == 0:
            warnings.append("高阈值市场无NO订单簿数据，使用中间价估算（不准确）")

        # 总成本 = 买入低阈值YES + 买入高阈值NO
        total_cost = low_buy_price + high_no_price

        # 保证回报 = $1.00
        # 无论结果如何，至少有一个合约会赢
        # - 如果 X > high_threshold: 两个都赢 = $2
        # - 如果 low_threshold < X <= high_threshold: 低阈值赢 = $1
        # - 如果 X <= low_threshold: 高阈值NO赢 = $1
        guaranteed_return = 1.0

        # 利润
        profit = guaranteed_return - total_cost
        profit_pct = profit / total_cost if total_cost > 0 else 0

        # 计算天数和APY
        days = self._calculate_days_to_settlement(low_info.end_date)
        if days <= 0:
            days = 1  # 避免除以0
            warnings.append("结算日期异常")

        apy = profit_pct * (365 / days) if days > 0 else 0

        return {
            'total_cost': total_cost,
            'guaranteed_return': guaranteed_return,
            'profit': profit,
            'profit_pct': profit_pct,
            'apy': apy,
            'days': days,
            'warnings': warnings,
        }

    def _calculate_days_to_settlement(self, end_date: str) -> int:
        """计算距离结算的天数"""
        try:
            if not end_date:
                return 30  # 默认30天

            # 解析日期
            if 'T' in end_date:
                end_date = end_date.split('T')[0]

            settlement = datetime.strptime(end_date, '%Y-%m-%d')
            today = datetime.now()
            delta = (settlement - today).days

            return max(1, delta)
        except Exception as e:
            logger.warning(f"解析结算日期失败: {end_date}, {e}")
            return 30

    def scan(self, markets: List, detection_mode: str = "all", multi_level: bool = True) -> List[MonotonicityViolation]:
        """
        扫描市场列表，检测所有单调性违背

        Args:
            markets: Market 对象列表
            detection_mode: 检测模式
                - "threshold": 仅标准阈值违背
                - "interval": 包含区间-阈值混合违背
                - "temporal": 包含跨日期时间蕴含违背
                - "all": 所有类型 (默认)
            multi_level: 是否启用多级检测（检测所有非相邻对），默认 True

        Returns:
            所有违背列表，按利润率排序
        """
        all_violations = []

        # 1. 提取阈值市场
        threshold_infos = []
        interval_infos = []
        for market in markets:
            info = self.extract_threshold_info(market)
            if info:
                if info.is_interval_market:
                    interval_infos.append(info)
                else:
                    threshold_infos.append(info)

        logger.info(f"从 {len(markets)} 个市场中提取了 {len(threshold_infos)} 个阈值市场, {len(interval_infos)} 个区间市场")

        if len(threshold_infos) < 2:
            return all_violations

        # 2. 分组形成阶梯
        ladders = self.group_ladder_markets(threshold_infos)
        logger.info(f"形成 {len(ladders)} 个阶梯组")

        # 3. 检查标准阈值违背
        if detection_mode in ["threshold", "all"]:
            check_method = self.check_multi_level_violations if multi_level else self.check_monotonicity
            for group_key, ladder in ladders.items():
                if len(ladder) >= 2:
                    violations = check_method(ladder)
                    if violations:
                        logger.info(f"在 {group_key} 发现 {len(violations)} 个阈值违背")
                        all_violations.extend(violations)

        # 4. 检查区间-阈值混合违背
        if detection_mode in ["interval", "all"] and interval_infos:
            interval_violations = self.check_interval_threshold_violations(interval_infos, threshold_infos)
            if interval_violations:
                logger.info(f"发现 {len(interval_violations)} 个区间-阈值违背")
                all_violations.extend(interval_violations)

        # 4.5. 检查区间-区间违背
        if detection_mode in ["interval", "all"] and interval_infos:
            ii_violations = self.check_interval_interval_violations(interval_infos)
            if ii_violations:
                logger.info(f"发现 {len(ii_violations)} 个区间-区间违背")
                all_violations.extend(ii_violations)

        # 5. 检查跨日期时间蕴含违背
        if detection_mode in ["temporal", "all"]:
            temporal_violations = self.check_temporal_violations(threshold_infos)
            if temporal_violations:
                logger.info(f"发现 {len(temporal_violations)} 个时间蕴含违背")
                all_violations.extend(temporal_violations)

        # 6. 按利润率排序
        all_violations.sort(key=lambda v: v.profit_pct, reverse=True)

        return all_violations

    def scan_multi_level(self, markets: List) -> List[MonotonicityViolation]:
        """
        使用多级检测扫描市场（检测所有非相邻对）

        Args:
            markets: Market 对象列表

        Returns:
            所有违背列表，按利润率排序
        """
        return self.scan(markets, multi_level=True)

    def scan_optimal_only(self, markets: List) -> List[MonotonicityViolation]:
        """
        扫描市场，只返回每个阶梯组的最优套利机会

        Args:
            markets: Market 对象列表

        Returns:
            每个阶梯组的最优套利列表
        """
        # 1. 提取阈值市场
        threshold_infos = []
        for market in markets:
            info = self.extract_threshold_info(market)
            if info:
                threshold_infos.append(info)

        logger.info(f"从 {len(markets)} 个市场中提取了 {len(threshold_infos)} 个阈值市场")

        if len(threshold_infos) < 2:
            return []

        # 2. 分组形成阶梯
        ladders = self.group_ladder_markets(threshold_infos)
        logger.info(f"形成 {len(ladders)} 个阶梯组")

        # 3. 对每个阶梯找最优套利
        optimal_violations = []
        for group_key, ladder in ladders.items():
            if len(ladder) >= 2:
                optimal = self.find_optimal_arbitrage(ladder)
                if optimal:
                    logger.info(f"在 {group_key} 发现最优套利: {optimal.profit_pct:.2%}")
                    optimal_violations.append(optimal)

        # 按利润率排序
        optimal_violations.sort(key=lambda v: v.profit_pct, reverse=True)

        return optimal_violations

    # ============================================================
    # 区间市场支持 (Task 1.2)
    # ============================================================

    def check_interval_threshold_violations(
        self,
        interval_markets: List[ThresholdInfo],
        threshold_markets: List[ThresholdInfo]
    ) -> List[MonotonicityViolation]:
        """
        检测区间-阈值混合违背

        理论约束：
        - 区间 [a, b] 的概率应 <= P(X > a-ε)（高于下界附近）
        - 区间 [a, b] 的概率应 <= P(X < b+ε)（低于上界附近）

        违背条件：
        - P(区间) + P(X < a) > 1  （区间+低于下界）
        - P(区间) + P(X > b) > 1  （区间+高于上界）

        Args:
            interval_markets: 区间市场列表
            threshold_markets: 阈值市场列表

        Returns:
            违背列表

        示例:
            市场A: "BTC in $80k-$100k" @ $0.20 (区间)
            市场B: "BTC > $90k" @ $0.50 (阈值)

            违背: $0.20 + $0.50 = $0.70 < $1.00
            套利: 买入区间 + 买入低于$80k + 买入高于$100k
        """
        violations = []

        for interval in interval_markets:
            if not interval.is_interval_market:
                continue

            interval_lower = interval.interval_lower or 0
            interval_upper = interval.interval_upper or float('inf')

            # 寻找相关的阈值市场
            related_below = []
            related_above = []

            for tm in threshold_markets:
                if tm.asset != interval.asset or tm.end_date != interval.end_date:
                    continue

                if tm.direction == ThresholdDirection.BELOW:
                    # BELOW市场，检查是否与区间上界相关
                    if tm.threshold_value <= interval_upper:
                        related_below.append(tm)
                elif tm.direction == ThresholdDirection.ABOVE:
                    # ABOVE市场，检查是否与区间下界相关
                    if tm.threshold_value >= interval_lower:
                        related_above.append(tm)

            # 检查完备集违背: P(区间) + P(下界以下) + P(上界以上) <= 1
            # 简化: P(区间) + P(X < interval_lower) <= 1 或 P(区间) + P(X > interval_upper) <= 1

            # 检查与 BELOW 市场的违背
            for below_market in related_below:
                total_prob = interval.effective_price + below_market.effective_price
                if total_prob > 1.0 + self.MIN_INVERSION_THRESHOLD:
                    # 违背: 区间 + 低于下界 > 100%
                    violation = self._create_interval_threshold_violation(
                        interval, below_market, "interval_below", total_prob - 1.0
                    )
                    if violation:
                        violations.append(violation)

            # 检查与 ABOVE 市场的违背
            for above_market in related_above:
                total_prob = interval.effective_price + above_market.effective_price
                if total_prob > 1.0 + self.MIN_INVERSION_THRESHOLD:
                    # 违背: 区间 + 高于上界 > 100%
                    violation = self._create_interval_threshold_violation(
                        interval, above_market, "interval_above", total_prob - 1.0
                    )
                    if violation:
                        violations.append(violation)

        return violations

    def _create_interval_threshold_violation(
        self,
        interval: ThresholdInfo,
        threshold: ThresholdInfo,
        violation_subtype: str,
        inversion: float
    ) -> Optional[MonotonicityViolation]:
        """
        创建区间-阈值违背记录

        Args:
            interval: 区间市场
            threshold: 阈值市场
            violation_subtype: 违背子类型 ("interval_below" 或 "interval_above")
            inversion: 价格倒挂幅度
        """
        # 计算套利
        arb = self.calculate_interval_threshold_arbitrage(interval, threshold, violation_subtype)
        if arb['profit_pct'] < self.MIN_PROFIT_THRESHOLD:
            return None

        # 对于区间市场，使用区间下界作为 low_threshold（用于显示）
        # threshold_str 属性会正确显示完整区间
        violation = MonotonicityViolation(
            asset=interval.asset,
            end_date=interval.end_date,
            direction=interval.direction,
            # low_market 是区间市场（使用 threshold_str 显示完整区间）
            low_threshold=interval.interval_lower if interval.interval_lower is not None else interval.threshold_value,
            low_market=interval,
            # high_market 是阈值市场
            high_threshold=threshold.threshold_value,
            high_market=threshold,
            price_inversion=inversion,
            total_cost=arb['total_cost'],
            guaranteed_return=arb['guaranteed_return'],
            profit=arb['profit'],
            profit_pct=arb['profit_pct'],
            apy=arb['apy'],
            days_to_settlement=arb['days'],
            warnings=arb['warnings'],
            violation_type="interval_threshold",
        )

        return violation

    def calculate_interval_threshold_arbitrage(
        self,
        interval: ThresholdInfo,
        threshold: ThresholdInfo,
        violation_subtype: str
    ) -> Dict:
        """
        计算区间-阈值套利

        套利策略：
        - 违背类型 interval_below: 买入区间YES + 买入低于阈值YES
        - 违背类型 interval_above: 买入区间YES + 买入高于阈值NO

        Args:
            interval: 区间市场
            threshold: 阈值市场
            violation_subtype: 违背子类型

        Returns:
            套利计算结果字典
        """
        warnings = []

        if violation_subtype == "interval_below":
            # 区间 + 低于下界 > 100% 的情况
            # 套利: 买入区间NO + 买入低于阈值NO
            # 这样无论结果如何，至少有一个赢
            interval_buy = interval.no_buy_price  # 买入区间NO
            threshold_buy = threshold.no_buy_price  # 买入低于阈值NO
            guaranteed_return = 2.0  # 如果两个都赢
        else:
            # interval_above: 区间 + 高于上界 > 100% 的情况
            # 套利: 买入区间YES + 买入高于阈值NO
            interval_buy = interval.buy_price  # 买入区间YES
            threshold_buy = threshold.no_buy_price  # 买入高于阈值NO
            guaranteed_return = 1.0  # 至少一个赢

        total_cost = interval_buy + threshold_buy
        profit = guaranteed_return - total_cost
        profit_pct = profit / total_cost if total_cost > 0 else 0

        days = self._calculate_days_to_settlement(interval.end_date)
        if days <= 0:
            days = 1
            warnings.append("结算日期异常")

        apy = profit_pct * (365 / days) if days > 0 else 0

        return {
            'total_cost': total_cost,
            'guaranteed_return': guaranteed_return,
            'profit': profit,
            'profit_pct': profit_pct,
            'apy': apy,
            'days': days,
            'warnings': warnings,
        }

    def scan_with_intervals(self, markets: List) -> List[MonotonicityViolation]:
        """
        扫描市场，包括区间-阈值混合检测

        Args:
            markets: Market 对象列表

        Returns:
            所有违背列表（包括阈值违背和区间违背）
        """
        # 1. 分别提取区间市场和阈值市场
        interval_markets = []
        threshold_markets = []

        for market in markets:
            info = self.extract_threshold_info(market)
            if info:
                if info.is_interval_market:
                    interval_markets.append(info)
                else:
                    threshold_markets.append(info)

        logger.info(f"从 {len(markets)} 个市场中提取了 {len(interval_markets)} 个区间市场和 {len(threshold_markets)} 个阈值市场")

        all_violations = []

        # 2. 传统阈值违背检测（多级）
        if len(threshold_markets) >= 2:
            threshold_violations = self.scan_multi_level(markets)
            all_violations.extend(threshold_violations)

        # 3. 区间-阈值混合检测
        if interval_markets and threshold_markets:
            interval_violations = self.check_interval_threshold_violations(
                interval_markets, threshold_markets
            )
            all_violations.extend(interval_violations)
            logger.info(f"发现 {len(interval_violations)} 个区间-阈值违背")

        # 按利润率排序
        all_violations.sort(key=lambda v: v.profit_pct, reverse=True)

        return all_violations

    def check_interval_interval_violations(
        self,
        intervals: List[ThresholdInfo]
    ) -> List[MonotonicityViolation]:
        """
        检测区间-区间违背

        理论约束：
        - 如果区间A包含区间B (A.lower <= B.lower and A.upper >= B.upper)，
          则 P(区间B) <= P(区间A)
        - 如果区间A和区间B重叠但不包含，没有直接约束
        - 如果区间A和区间B不相交，检查完备集约束：P(A) + P(B) + P(其他) <= 1

        Args:
            intervals: 区间市场列表

        Returns:
            区间-区间违背列表
        """
        violations = []

        # 只处理区间市场
        interval_markets = [i for i in intervals if i.is_interval_market]

        # 按资产和日期分组
        groups = {}
        for interval in interval_markets:
            key = (interval.asset, interval.end_date)
            if key not in groups:
                groups[key] = []
            groups[key].append(interval)

        for (asset, end_date), group_intervals in groups.items():
            if len(group_intervals) < 2:
                continue

            # 检查所有区间对
            for i in range(len(group_intervals)):
                for j in range(i + 1, len(group_intervals)):
                    int1 = group_intervals[i]
                    int2 = group_intervals[j]

                    # 确保区间边界已提取
                    lower1 = int1.interval_lower or 0
                    upper1 = int1.interval_upper or float('inf')
                    lower2 = int2.interval_lower or 0
                    upper2 = int2.interval_upper or float('inf')

                    # 检查包含关系
                    int1_contains_int2 = (lower1 <= lower2 and upper1 >= upper2)
                    int2_contains_int1 = (lower2 <= lower1 and upper2 >= upper1)

                    if int1_contains_int2 and not int2_contains_int1:
                        # 区间1包含区间2，应该 P(int2) <= P(int1)
                        if int2.effective_price > int1.effective_price + self.MIN_INVERSION_THRESHOLD:
                            violations.append(self._create_interval_interval_violation(
                                int1, int2, "containment", int2.effective_price - int1.effective_price
                            ))
                    elif int2_contains_int1 and not int1_contains_int2:
                        # 区间2包含区间1，应该 P(int1) <= P(int2)
                        if int1.effective_price > int2.effective_price + self.MIN_INVERSION_THRESHOLD:
                            violations.append(self._create_interval_interval_violation(
                                int2, int1, "containment", int1.effective_price - int2.effective_price
                            ))

                    # 检查完备集约束（不相交的区间）
                    # 如果区间不相交，P(A) + P(B) 应该 <= 1（因为两者不能同时发生）
                    if upper1 < lower2 or upper2 < lower1:
                        total_prob = int1.effective_price + int2.effective_price
                        if total_prob > 1.0 + self.MIN_INVERSION_THRESHOLD:
                            violations.append(self._create_interval_interval_violation(
                                int1, int2, "completeness", total_prob - 1.0
                            ))

        return violations

    def _create_interval_interval_violation(
        self,
        interval1: ThresholdInfo,
        interval2: ThresholdInfo,
        violation_subtype: str,
        inversion: float
    ) -> Optional[MonotonicityViolation]:
        """
        创建区间-区间违背记录

        Args:
            interval1: 第一个区间市场（包含方或较小的完备集）
            interval2: 第二个区间市场（被包含方或较大的完备集）
            violation_subtype: 违背子类型 ("containment" 或 "completeness")
            inversion: 价格倒挂幅度
        """
        # 计算套利
        arb = self._calculate_interval_interval_arbitrage(interval1, interval2, violation_subtype)
        if arb['profit_pct'] < self.MIN_PROFIT_THRESHOLD:
            return None

        violation = MonotonicityViolation(
            asset=interval1.asset,
            end_date=interval1.end_date,
            direction=interval1.direction,
            low_threshold=interval1.interval_lower if interval1.interval_lower is not None else interval1.threshold_value,
            low_market=interval1,
            high_threshold=interval2.interval_lower if interval2.interval_lower is not None else interval2.threshold_value,
            high_market=interval2,
            price_inversion=inversion,
            total_cost=arb['total_cost'],
            guaranteed_return=arb['guaranteed_return'],
            profit=arb['profit'],
            profit_pct=arb['profit_pct'],
            apy=arb['apy'],
            days_to_settlement=arb['days'],
            warnings=arb['warnings'],
            violation_type="interval_interval",
        )

        return violation

    def _calculate_interval_interval_arbitrage(
        self,
        interval1: ThresholdInfo,
        interval2: ThresholdInfo,
        violation_subtype: str
    ) -> Dict:
        """
        计算区间-区间套利

        Args:
            interval1: 第一个区间市场
            interval2: 第二个区间市场
            violation_subtype: 违背子类型

        Returns:
            套利计算结果字典
        """
        warnings = []

        price1 = interval1.effective_price
        price2 = interval2.effective_price

        if price1 <= 0 or price2 <= 0:
            return self._get_zero_arbitrage_result("无效价格")

        # 根据违背类型计算套利
        if violation_subtype == "containment":
            # 包含关系违背: 买入被包含区间YES + 卖出包含区间YES
            # 或者根据价格关系调整
            total_cost = price2  # 简化：只买入较贵的
            guaranteed_return = 1.0
            profit = guaranteed_return - total_cost
            profit_pct = profit / total_cost if total_cost > 0 else 0

        else:  # completeness
            # 完备集违背: 买入两区间的NO
            # P(A) + P(B) > 1 意味着 P(NOT A AND NOT B) < 0
            # 套利: 买入 NO on both
            no_price1 = 1.0 - price1
            no_price2 = 1.0 - price2
            total_cost = no_price1 + no_price2
            guaranteed_return = 1.0  # 至少一个NO会赢（因为不能同时发生）
            profit = guaranteed_return - total_cost
            profit_pct = profit / total_cost if total_cost > 0 else 0

        days = self._calculate_days_to_settlement(interval1.end_date)
        if days <= 0:
            days = 1
            warnings.append("结算日期异常")

        apy = profit_pct * (365 / days) if days > 0 else 0

        return {
            'total_cost': total_cost,
            'guaranteed_return': guaranteed_return,
            'profit': profit,
            'profit_pct': profit_pct,
            'apy': apy,
            'days': days,
            'warnings': warnings,
        }

    # ============================================================
    # 跨日期时间蕴含检测 (Task 2.2)
    # ============================================================

    def check_temporal_violations(
        self,
        threshold_markets: List[ThresholdInfo]
    ) -> List[MonotonicityViolation]:
        """
        检测跨日期时间蕴含违背

        理论约束：
        - 对于同一阈值，较早日期的概率应该 >= 较晚日期的概率
        - P(event by date_early) >= P(event by date_late)

        违背条件：
        - 同一阈值、同一资产，但 date_early 的价格 < date_late 的价格

        Args:
            threshold_markets: 阈值市场列表

        Returns:
            时间违背列表

        示例:
            市场A: "BTC > $100k by Jan 15" @ $0.60
            市场B: "BTC > $100k by Jan 31" @ $0.45  ← 违背

            套利: 买入Jan15 YES + 买入Jan31 NO
        """
        violations = []

        # 按资产、阈值、方向分组
        groups = defaultdict(list)
        for tm in threshold_markets:
            if tm.direction == ThresholdDirection.ABOVE or tm.direction == ThresholdDirection.BELOW:
                # 使用 (asset, threshold_value, direction) 作为键
                key = (tm.asset, tm.threshold_value, tm.direction.value)
                groups[key].append(tm)

        # 检查每组内的时间违背
        for key, markets in groups.items():
            if len(markets) < 2:
                continue

            # 按日期排序
            markets.sort(key=lambda m: m.end_date)

            # 检测所有日期对
            for i in range(len(markets)):
                for j in range(i + 1, len(markets)):
                    early = markets[i]
                    late = markets[j]

                    if early.end_date == late.end_date:
                        continue  # 同一日期，跳过

                    early_price = early.effective_price
                    late_price = late.effective_price

                    # 检查时间违背: P(early) < P(late)
                    if early_price < late_price - self.MIN_INVERSION_THRESHOLD:
                        # 违背：较早日期的价格更低
                        inversion = late_price - early_price
                        violation = self._create_temporal_violation(early, late, inversion)
                        if violation:
                            violations.append(violation)

        # 按利润率排序
        violations.sort(key=lambda v: v.profit_pct, reverse=True)
        return violations

    def _create_temporal_violation(
        self,
        early_market: ThresholdInfo,
        late_market: ThresholdInfo,
        inversion: float
    ) -> Optional[MonotonicityViolation]:
        """创建时间违背记录并计算套利"""
        # 计算套利
        arb = self.calculate_temporal_arbitrage(early_market, late_market)
        if arb['profit_pct'] < self.MIN_PROFIT_THRESHOLD:
            return None

        violation = MonotonicityViolation(
            asset=early_market.asset,
            end_date=f"{early_market.end_date}_vs_{late_market.end_date}",
            direction=early_market.direction,
            low_threshold=early_market.threshold_value,
            low_market=early_market,
            high_threshold=late_market.threshold_value,
            high_market=late_market,
            price_inversion=inversion,
            total_cost=arb['total_cost'],
            guaranteed_return=arb['guaranteed_return'],
            profit=arb['profit'],
            profit_pct=arb['profit_pct'],
            apy=arb['apy'],
            days_to_settlement=arb['days'],
            warnings=arb['warnings'],
            violation_type="temporal",
        )

        return violation

    def calculate_temporal_arbitrage(
        self,
        early_market: ThresholdInfo,
        late_market: ThresholdInfo
    ) -> Dict:
        """
        计算时间蕴含套利

        套利策略：
        - 买入早日期 YES (概率更高)
        - 买入晚日期 NO (因为晚日期应该更便宜)

        Args:
            early_market: 早日期市场
            late_market: 晚日期市场

        Returns:
            套利计算结果字典
        """
        warnings = []

        # 买入早日期 YES，买入晚日期 NO
        early_buy = early_market.buy_price
        late_no = late_market.no_buy_price

        total_cost = early_buy + late_no

        # 保证回报：至少一个会赢
        # 如果事件在早日期发生：早YES赢
        # 如果事件在晚日期才发生：晚NO赢（因为早日期没发生）
        guaranteed_return = 1.0

        profit = guaranteed_return - total_cost
        profit_pct = profit / total_cost if total_cost > 0 else 0

        # 使用早日期的天数计算 APY
        days = self._calculate_days_to_settlement(early_market.end_date)
        if days <= 0:
            days = 1
            warnings.append("结算日期异常")

        apy = profit_pct * (365 / days) if days > 0 else 0

        return {
            'total_cost': total_cost,
            'guaranteed_return': guaranteed_return,
            'profit': profit,
            'profit_pct': profit_pct,
            'apy': apy,
            'days': days,
            'warnings': warnings,
        }

    def scan_with_temporal(self, markets: List) -> List[MonotonicityViolation]:
        """
        扫描市场，包括跨日期时间蕴含检测

        Args:
            markets: Market 对象列表

        Returns:
            所有违背列表（包括阈值违背和时间违背）
        """
        # 1. 提取阈值市场
        threshold_infos = []
        for market in markets:
            info = self.extract_threshold_info(market)
            if info and info.market_type == MarketType.THRESHOLD:
                threshold_infos.append(info)

        logger.info(f"从 {len(markets)} 个市场中提取了 {len(threshold_infos)} 个阈值市场")

        if len(threshold_infos) < 2:
            return []

        # 2. 传统阈值违背检测（多级）
        threshold_violations = self.scan_multi_level(markets)

        # 3. 时间违背检测
        temporal_violations = self.check_temporal_violations(threshold_infos)
        logger.info(f"发现 {len(temporal_violations)} 个时间违背")

        # 合并结果
        all_violations = threshold_violations + temporal_violations

        # 按利润率排序
        all_violations.sort(key=lambda v: v.profit_pct, reverse=True)

        return all_violations

    def format_violation(self, v: MonotonicityViolation) -> str:
        """格式化输出违背信息

        支持四种违背类型:
        - threshold: 标准阈值违背
        - interval_threshold: 区间-阈值混合违背
        - interval_interval: 区间-区间违背
        - temporal: 时间蕴含违背
        """
        lines = [
            f"\n{'='*60}",
            f"单调性违背套利机会",
            f"{'='*60}",
        ]

        # 根据违背类型显示不同的标题和信息
        if v.violation_type == "temporal":
            lines.extend([
                f"类型: 时间蕴含违背 (Temporal Implication Violation)",
                f"资产: {v.asset.upper()}",
                f"方向: {v.direction.value}",
                f"early_date: {v.low_market.end_date}",  # low_market = early market
                f"late_date: {v.high_market.end_date}",  # high_market = late market
                f"",
                f"早期市场 (应该更贵):",
                f"  阈值: {v.low_market.threshold_str}",
                f"  日期: {v.low_market.end_date}",
                f"  价格: {v.low_market.effective_price:.3f}",
                f"  问题: {v.low_market.market.question[:60]}...",
                f"",
                f"晚期市场 (应该更便宜):",
                f"  阈值: {v.high_market.threshold_str}",
                f"  日期: {v.high_market.end_date}",
                f"  价格: {v.high_market.effective_price:.3f}",
                f"  问题: {v.high_market.market.question[:60]}...",
            ])
        elif v.violation_type == "interval_threshold":
            lines.extend([
                f"类型: 区间-阈值混合违背 (Interval-Threshold Violation)",
                f"资产: {v.asset.upper()}",
                f"方向: {v.direction.value}",
                f"",
                f"区间市场:",
                f"  区间: {v.low_market.threshold_str}",
                f"  价格: {v.low_market.effective_price:.3f}",
                f"  问题: {v.low_market.market.question[:60]}...",
                f"",
                f"阈值市场:",
                f"  阈值: {v.high_market.threshold_str}",
                f"  价格: {v.high_market.effective_price:.3f}",
                f"  问题: {v.high_market.market.question[:60]}...",
            ])
        elif v.violation_type == "interval_interval":
            lines.extend([
                f"类型: 区间-区间违背 (Interval-Interval Violation)",
                f"资产: {v.asset.upper()}",
                f"方向: {v.direction.value}",
                f"",
                f"区间市场1:",
                f"  区间: {v.low_market.threshold_str}",
                f"  价格: {v.low_market.effective_price:.3f}",
                f"  问题: {v.low_market.market.question[:60]}...",
                f"",
                f"区间市场2:",
                f"  区间: {v.high_market.threshold_str}",
                f"  价格: {v.high_market.effective_price:.3f}",
                f"  问题: {v.high_market.market.question[:60]}...",
            ])
        else:  # threshold (标准阈值违背)
            lines.extend([
                f"类型: 阈值违背 (Threshold Monotonicity Violation)",
                f"资产: {v.asset.upper()}",
                f"方向: {v.direction.value}",
                f"结算日期: {v.end_date}",
                f"",
                f"低阈值市场 (应该更贵):",
                f"  阈值: {v.low_market.threshold_str}",
                f"  价格: {v.low_market.effective_price:.3f}",
                f"  问题: {v.low_market.market.question[:60]}...",
                f"",
                f"高阈值市场 (应该更便宜):",
                f"  阈值: {v.high_market.threshold_str}",
                f"  价格: {v.high_market.effective_price:.3f}",
                f"  问题: {v.high_market.market.question[:60]}...",
            ])

        # 套利分析（所有类型通用）
        lines.extend([
            f"",
            f"套利分析:",
            f"  价格差异: {v.price_inversion:.3f}",
            f"  总成本: ${v.total_cost:.3f}",
            f"  保证回报: ${v.guaranteed_return:.2f}",
            f"  利润: ${v.profit:.3f} ({v.profit_pct:.2%})",
        ])

        if v.days_to_settlement > 0:
            lines.append(f"  天数: {v.days_to_settlement}")
        if v.apy > 0:
            lines.append(f"  APY: {v.apy:.1%}")

        if v.warnings:
            lines.append(f"")
            lines.append(f"警告:")
            for w in v.warnings:
                lines.append(f"  - {w}")

        lines.append(f"{'='*60}")

        return '\n'.join(lines)


# 便捷函数
def scan_monotonicity_violations(markets: List, min_profit: float = 0.005) -> List[MonotonicityViolation]:
    """
    扫描单调性违背

    Args:
        markets: Market 对象列表
        min_profit: 最小利润阈值

    Returns:
        违背列表
    """
    checker = MonotonicityChecker(min_profit=min_profit)
    return checker.scan(markets)


if __name__ == "__main__":
    # 测试代码
    print("MonotonicityChecker 模块加载成功")

    # 测试阈值提取
    checker = MonotonicityChecker()

    test_questions = [
        "Will Bitcoin be above $100,000 by December 31?",
        "Will BTC hit 95k before end of month?",
        "Ethereum above $4,000?",
        "Will SOL fall below $150?",
        "Bitcoin > 120000 in January?",
        "Will ETH reach $5,000 by Q1 2025?",
    ]

    print("\n阈值提取测试:")
    for q in test_questions:
        result = checker._extract_threshold(q.lower())
        asset = checker._detect_asset(q.lower())
        print(f"  {q}")
        print(f"    -> 资产: {asset}, 阈值: {result}")
