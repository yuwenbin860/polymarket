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
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict
from enum import Enum

# 设置日志
logger = logging.getLogger(__name__)


class ThresholdDirection(Enum):
    """阈值方向"""
    ABOVE = "above"  # X > threshold (价格超过阈值)
    BELOW = "below"  # X < threshold (价格低于阈值)


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

    @property
    def effective_price(self) -> float:
        """有效价格（优先使用中间价）"""
        if self.best_bid > 0 and self.best_ask > 0:
            return (self.best_bid + self.best_ask) / 2
        return self.yes_price

    @property
    def buy_price(self) -> float:
        """YES买入价格"""
        return self.best_ask if self.best_ask > 0 else self.yes_price

    @property
    def sell_price(self) -> float:
        """YES卖出价格"""
        return self.best_bid if self.best_bid > 0 else self.yes_price

    @property
    def no_buy_price(self) -> float:
        """NO买入价格（真实ask价或降级计算）"""
        if self.no_best_ask > 0:
            return self.no_best_ask
        # 降级：使用中间价反推（不准确，会有警告）
        return 1.0 - self.yes_price


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

    def __repr__(self):
        return (f"MonotonicityViolation({self.asset} {self.direction.value}: "
                f"{self.low_threshold} @ {self.low_market.effective_price:.3f} vs "
                f"{self.high_threshold} @ {self.high_market.effective_price:.3f}, "
                f"profit={self.profit_pct:.2%})")


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

    # 阈值提取模式
    THRESHOLD_PATTERNS = [
        # "above $100,000" or "above 100,000" or "above $100k"
        (r'above\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', ThresholdDirection.ABOVE),
        # "over $100,000"
        (r'over\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', ThresholdDirection.ABOVE),
        # "greater than $100,000"
        (r'greater\s+than\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', ThresholdDirection.ABOVE),
        # "> $100,000" or ">100k"
        (r'>\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', ThresholdDirection.ABOVE),
        # "hit $100,000" / "reach $100,000"
        (r'(?:hit|reach|hits|reaches)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', ThresholdDirection.ABOVE),
        # "below $100,000"
        (r'below\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', ThresholdDirection.BELOW),
        # "under $100,000"
        (r'under\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', ThresholdDirection.BELOW),
        # "< $100,000"
        (r'<\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', ThresholdDirection.BELOW),
        # "fall below $100,000"
        (r'fall\s+(?:below|under)\s*\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', ThresholdDirection.BELOW),
    ]

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
        从市场中提取阈值信息

        Args:
            market: Market 对象

        Returns:
            ThresholdInfo 或 None（如果不是阈值市场）
        """
        question = market.question.lower()

        # 1. 识别资产
        asset = self._detect_asset(question)
        if not asset:
            return None

        # 2. 提取阈值和方向
        threshold_result = self._extract_threshold(question)
        if not threshold_result:
            return None

        threshold_value, direction = threshold_result

        # 3. 构建 ThresholdInfo
        return ThresholdInfo(
            market=market,
            asset=asset,
            threshold_value=threshold_value,
            direction=direction,
            end_date=market.end_date.split('T')[0] if market.end_date else "",
            yes_price=market.yes_price,
            best_bid=getattr(market, 'best_bid', 0.0),
            best_ask=getattr(market, 'best_ask', 0.0),
            # 单调性套利修复: 填充 NO token 价格
            no_best_bid=getattr(market, 'best_bid_no', 0.0),
            no_best_ask=getattr(market, 'best_ask_no', 0.0),
        )

    def _detect_asset(self, text: str) -> Optional[str]:
        """检测文本中的资产类型"""
        text_lower = text.lower()
        for asset, patterns in self.ASSET_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return asset
        return None

    def _extract_threshold(self, text: str) -> Optional[Tuple[float, ThresholdDirection]]:
        """提取阈值和方向"""
        text_lower = text.lower()

        for pattern, direction in self.THRESHOLD_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                value_str = match.group(1).replace(',', '')

                # 处理 "k" 后缀
                if 'k' in text_lower[match.end()-2:match.end()+1].lower():
                    value = float(value_str) * 1000
                else:
                    value = float(value_str)

                return (value, direction)

        return None

    def group_ladder_markets(self, threshold_infos: List[ThresholdInfo]) -> Dict[str, List[ThresholdInfo]]:
        """
        按资产、日期、方向分组形成"阶梯"结构

        Args:
            threshold_infos: ThresholdInfo 列表

        Returns:
            {group_key: [ThresholdInfo sorted by threshold]}
        """
        groups = defaultdict(list)

        for info in threshold_infos:
            # 组合键: asset_date_direction
            group_key = f"{info.asset}_{info.end_date}_{info.direction.value}"
            groups[group_key].append(info)

        # 按阈值排序每个组
        for key in groups:
            groups[key].sort(key=lambda x: x.threshold_value)

        return dict(groups)

    def check_monotonicity(self, ladder: List[ThresholdInfo]) -> List[MonotonicityViolation]:
        """
        检查阶梯市场的单调性

        对于 ABOVE 方向：高阈值价格应该 <= 低阈值价格
        对于 BELOW 方向：高阈值价格应该 >= 低阈值价格

        Args:
            ladder: 按阈值排序的 ThresholdInfo 列表

        Returns:
            违背列表
        """
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
                # BELOW: P(X < k_high) 应该 >= P(X < k_low)
                # 即高阈值的 YES 价格应该更高
                if low_price > high_price + self.MIN_INVERSION_THRESHOLD:
                    violation = self._create_violation(high, low, low_price - high_price)
                    if violation:
                        violations.append(violation)

        return violations

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

    def scan(self, markets: List) -> List[MonotonicityViolation]:
        """
        扫描市场列表，检测所有单调性违背

        Args:
            markets: Market 对象列表

        Returns:
            所有违背列表，按利润率排序
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

        # 3. 检查每个阶梯的单调性
        all_violations = []
        for group_key, ladder in ladders.items():
            if len(ladder) >= 2:
                violations = self.check_monotonicity(ladder)
                if violations:
                    logger.info(f"在 {group_key} 发现 {len(violations)} 个违背")
                    all_violations.extend(violations)

        # 4. 按利润率排序
        all_violations.sort(key=lambda v: v.profit_pct, reverse=True)

        return all_violations

    def format_violation(self, v: MonotonicityViolation) -> str:
        """格式化输出违背信息"""
        lines = [
            f"\n{'='*60}",
            f"单调性违背套利机会",
            f"{'='*60}",
            f"资产: {v.asset.upper()}",
            f"方向: {v.direction.value}",
            f"结算日期: {v.end_date}",
            f"",
            f"低阈值市场:",
            f"  阈值: ${v.low_threshold:,.2f}".rstrip('0').rstrip('.'),
            f"  价格: {v.low_market.effective_price:.3f}",
            f"  问题: {v.low_market.market.question[:60]}...",
            f"",
            f"高阈值市场:",
            f"  阈值: ${v.high_threshold:,.2f}".rstrip('0').rstrip('.'),
            f"  价格: {v.high_market.effective_price:.3f}",
            f"  问题: {v.high_market.market.question[:60]}...",
            f"",
            f"套利分析:",
            f"  价格倒挂: {v.price_inversion:.3f}",
            f"  总成本: ${v.total_cost:.3f}",
            f"  保证回报: ${v.guaranteed_return:.2f}",
            f"  利润: ${v.profit:.3f} ({v.profit_pct:.2%})",
            f"  天数: {v.days_to_settlement}",
            f"  APY: {v.apy:.1%}",
        ]

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
