#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
区间解析模块 - Interval Parser
========================

解析预测市场问题中的数值区间，用于检测区间套利机会。

核心功能：
1. 从问题文本中解析区间信息（如 ">$100k", "between 50-100"）
2. 比较两个区间的逻辑关系（包含、重叠、互斥）
3. 生成区间套利策略

使用方法：
    from interval_parser import IntervalParser, Interval

    parser = IntervalParser()
    interval = parser.parse("Will Bitcoin be above $100k in 2025?")
    # Returns: Interval(type="above", lower=100000, upper=inf, unit="USD")

Solana区间套利示例：
    - 市场A: "Solana price on Jan 4?" (完备集)
      - 子市场A1: "< 130" → YES = 4.6c
    - 市场B: "Solana above 130 on Jan 4?"
      - YES = 94.8c, NO = 5.2c
    - 套利: 买A1的YES + 买B的YES = 4.6 + 94.8 = 99.4c → 保证回报$1
"""

import re
import math
from dataclasses import dataclass
from typing import Optional, List, Tuple, Literal
from enum import Enum


class IntervalType(Enum):
    """区间类型"""
    ABOVE = "above"           # > x (大于)
    ABOVE_OR_EQUAL = "above_or_equal"  # >= x (大于等于)
    BELOW = "below"           # < x (小于)
    BELOW_OR_EQUAL = "below_or_equal"  # <= x (小于等于)
    RANGE = "range"           # [x, y] (范围内)
    EXACT = "exact"           # = x (等于)
    UNKNOWN = "unknown"       # 无法解析


@dataclass
class Interval:
    """区间表示"""
    type: IntervalType
    lower: float              # 下界 (float('inf') 表示无上限)
    upper: float              # 上界 (float('-inf') 表示无下界)
    unit: str = ""            # 单位 (如 "USD", "BTC", "%")
    inclusive_lower: bool = True   # 是否包含下界
    inclusive_upper: bool = True   # 是否包含上界
    original_text: str = ""    # 原始文本

    def __repr__(self):
        if self.type == IntervalType.ABOVE:
            op = ">=" if self.inclusive_lower else ">"
            return f"Price {op} {self.lower}{self.unit}"
        elif self.type == IntervalType.BELOW:
            op = "<=" if self.inclusive_upper else "<"
            return f"Price {op} {self.upper}{self.unit}"
        elif self.type == IntervalType.RANGE:
            return f"Price in [{self.lower}, {self.upper}]{self.unit}"
        return f"Interval({self.type.value})"

    def contains(self, value: float) -> bool:
        """检查值是否在区间内"""
        if self.type == IntervalType.ABOVE:
            if self.inclusive_lower:
                return value >= self.lower
            return value > self.lower
        elif self.type == IntervalType.BELOW:
            if self.inclusive_upper:
                return value <= self.upper
            return value < self.upper
        elif self.type == IntervalType.RANGE:
            lower_ok = value >= self.lower if self.inclusive_lower else value > self.lower
            upper_ok = value <= self.upper if self.inclusive_upper else value < self.upper
            return lower_ok and upper_ok
        return False

    def is_subset_of(self, other: 'Interval') -> bool:
        """检查当前区间是否是另一个区间的子集"""
        # A是B的子集意味着：如果A发生，B必然发生
        # 例如：[100, 200] 是 [50, 300] 的子集
        # 但在预测市场中，子集关系通常是：更高阈值蕴含更低阈值
        # ">$200" 是 ">$100" 的子集（如果>$200则必然>$100）

        if self.type == IntervalType.ABOVE and other.type == IntervalType.ABOVE:
            # 更高阈值蕴含更低阈值
            return self.lower >= other.lower
        elif self.type == IntervalType.BELOW and other.type == IntervalType.BELOW:
            # 更低阈值蕴含更高阈值
            return self.upper <= other.upper
        elif self.type == IntervalType.RANGE and other.type == IntervalType.ABOVE:
            # 区间在阈值之上
            return self.lower >= other.lower
        elif self.type == IntervalType.RANGE and other.type == IntervalType.BELOW:
            # 区间在阈值之下
            return self.upper <= other.upper
        return False

    def overlaps_with(self, other: 'Interval') -> bool:
        """检查两个区间是否重叠"""
        # 两个区间有重叠意味着：可能同时为YES
        if self.type == IntervalType.ABOVE and other.type == IntervalType.ABOVE:
            return True  # 两个above总是重叠
        if self.type == IntervalType.BELOW and other.type == IntervalType.BELOW:
            return True  # 两个below总是重叠
        if self.type == IntervalType.ABOVE and other.type == IntervalType.BELOW:
            return self.lower < other.upper  # above的下界 < below的上界
        if self.type == IntervalType.BELOW and other.type == IntervalType.ABOVE:
            return other.lower < self.upper
        # TODO: 处理RANGE类型
        return True


class IntervalRelation(Enum):
    """两个区间之间的逻辑关系"""
    A_COVERS_B = "a_covers_b"       # A覆盖B（B是A的子集）
    B_COVERS_A = "b_covers_a"       # B覆盖A（A是B的子集）
    OVERLAP = "overlap"             # 重叠（但不是子集关系）
    MUTUAL_EXCLUSIVE = "mutual_exclusive"  # 互斥（不可能同时为真）
    UNRELATED = "unrelated"         # 无关


class IntervalParser:
    """区间解析器"""

    # 数值模式：支持各种格式
    NUMBER_PATTERNS = [
        r'\$?([\d,]+(?:\.\d+)?)\s*([kKmMbBtT]?)',  # $100k, 1.5M
        r'([\d,]+(?:\.\d+)?)\s*%?',                # 50%, 0.5
    ]

    # 单位换算
    UNIT_MULTIPLIERS = {
        'k': 1000,
        'K': 1000,
        'm': 1_000_000,
        'M': 1_000_000,
        'b': 1_000_000_000,
        'B': 1_000_000_000,
        't': 1_000_000_000_000,
        'T': 1_000_000_000_000,
    }

    # 关键词模式
    ABOVE_KEYWORDS = ['above', 'higher than', 'exceeds', 'over', 'greater than', 'tops']
    BELOW_KEYWORDS = ['below', 'lower than', 'under', 'less than', 'drops to']
    RANGE_KEYWORDS = ['between', 'from', 'range', 'in']

    def __init__(self):
        # 编译正则表达式
        self.number_re = re.compile(r'\$?([\d,]+(?:\.\d+)?)\s*([kKmMbBtT]?)?')
        self.range_re = re.compile(r'between\s+([\d,]+(?:\.\d+)?)\s*[kKmMbBtT]?\s*(?:and|to|-)\s*([\d,]+(?:\.\d+)?)\s*[kKmMbBtT]?', re.IGNORECASE)

    def parse_number(self, text: str) -> Tuple[float, str]:
        """解析数值和单位"""
        match = self.number_re.search(text)
        if not match:
            return 0.0, ""

        num_str = match.group(1).replace(',', '')
        unit = match.group(2) or ''

        try:
            num = float(num_str)
        except ValueError:
            return 0.0, ""

        # 应用单位乘数
        if unit in self.UNIT_MULTIPLIERS:
            num *= self.UNIT_MULTIPLIERS[unit]

        return num, unit.upper() if unit else ""

    def parse(self, question: str, description: str = "") -> Optional[Interval]:
        """
        解析问题文本中的区间信息

        Args:
            question: 市场问题文本
            description: 可选的描述信息（可能包含更多细节）

        Returns:
            Interval对象或None
        """
        text = f"{question} {description}".lower()

        # 检测区间类型
        if self._is_above(text):
            value, unit = self.parse_number(text)
            return Interval(
                type=IntervalType.ABOVE,
                lower=value,
                upper=float('inf'),
                unit=unit,
                inclusive_lower=False,  # "above"通常不包含等于
                original_text=text[:100]
            )
        elif self._is_below(text):
            value, unit = self.parse_number(text)
            return Interval(
                type=IntervalType.BELOW,
                lower=float('-inf'),
                upper=value,
                unit=unit,
                inclusive_upper=False,  # "below"通常不包含等于
                original_text=text[:100]
            )
        elif self._is_range(text):
            values = self.range_re.findall(text)
            if values and len(values[0]) >= 2:
                low = float(values[0][0].replace(',', ''))
                high = float(values[0][1].replace(',', ''))
                # 检查单位
                unit_match = re.search(r'[kKmMbBtT]', text)
                unit = unit_match.group().upper() if unit_match else ""
                multiplier = self.UNIT_MULTIPLIERS.get(unit, 1)
                return Interval(
                    type=IntervalType.RANGE,
                    lower=low * multiplier,
                    upper=high * multiplier,
                    unit=unit,
                    inclusive_lower=True,
                    inclusive_upper=True,
                    original_text=text[:100]
                )

        return None

    def _is_above(self, text: str) -> bool:
        """检查是否是above类型"""
        text_lower = text.lower()
        for keyword in self.ABOVE_KEYWORDS:
            if keyword in text_lower:
                return True
        return False

    def _is_below(self, text: str) -> bool:
        """检查是否是below类型"""
        text_lower = text.lower()
        for keyword in self.BELOW_KEYWORDS:
            if keyword in text_lower:
                return True
        return False

    def _is_range(self, text: str) -> bool:
        """检查是否是range类型"""
        text_lower = text.lower()
        for keyword in self.RANGE_KEYWORDS:
            if keyword in text_lower:
                return True
        # 检查 "X to Y" 或 "X - Y" 模式
        if re.search(r'\d+\s*(?:to|-)\s*\d+', text_lower):
            return True
        return False

    def compare_intervals(self, interval_a: Interval, interval_b: Interval) -> IntervalRelation:
        """
        比较两个区间的逻辑关系

        Args:
            interval_a: 第一个区间
            interval_b: 第二个区间

        Returns:
            IntervalRelation枚举值
        """
        # 检查子集关系
        if interval_a.is_subset_of(interval_b):
            return IntervalRelation.B_COVERS_A  # B覆盖A
        if interval_b.is_subset_of(interval_a):
            return IntervalRelation.A_COVERS_B  # A覆盖B

        # 检查重叠
        if interval_a.overlaps_with(interval_b):
            return IntervalRelation.OVERLAP

        # 检查互斥
        if interval_a.type == IntervalType.ABOVE and interval_b.type == IntervalType.BELOW:
            if interval_a.lower >= interval_b.upper:
                return IntervalRelation.MUTUAL_EXCLUSIVE
        if interval_a.type == IntervalType.BELOW and interval_b.type == IntervalType.ABOVE:
            if interval_b.lower >= interval_a.upper:
                return IntervalRelation.MUTUAL_EXCLUSIVE

        return IntervalRelation.UNRELATED

    def find_interval_arbitrage(
        self,
        market_a: dict,
        market_b: dict
    ) -> Optional[dict]:
        """
        检测两个市场之间的区间套利机会

        Args:
            market_a: 市场A字典 {question, yes_price, ...}
            market_b: 市场B字典 {question, yes_price, ...}

        Returns:
            套利信息字典或None
        """
        interval_a = self.parse(
            market_a.get('question', ''),
            market_a.get('event_description', '') or market_a.get('description', '')
        )
        interval_b = self.parse(
            market_b.get('question', ''),
            market_b.get('event_description', '') or market_b.get('description', '')
        )

        if not interval_a or not interval_b:
            return None

        relation = self.compare_intervals(interval_a, interval_b)

        # 检查套利条件
        price_a = market_a.get('yes_price', 0.5)
        price_b = market_b.get('yes_price', 0.5)

        arbitrage = None

        if relation == IntervalRelation.A_COVERS_B:
            # A覆盖B（B是A的子集）
            # 应该有: P(B) >= P(A)
            # 如果 P(A) > P(B)，存在套利
            if price_a > price_b:
                arbitrage = {
                    'type': 'interval_implication',
                    'relation': 'A_COVERS_B',
                    'constraint': f'P({market_a.get("question", "A")[:30]}...) <= P({market_b.get("question", "B")[:30]}...)',
                    'actual': f'{price_a:.3f} > {price_b:.3f}',
                    'strategy': f'Buy A YES, Buy A NO',  # 实际策略需要更详细分析
                    'violation': price_a - price_b,
                }
        elif relation == IntervalRelation.B_COVERS_A:
            # B覆盖A（A是B的子集）
            # 应该有: P(A) >= P(B)
            if price_b > price_a:
                arbitrage = {
                    'type': 'interval_implication',
                    'relation': 'B_COVERS_A',
                    'constraint': f'P({market_b.get("question", "B")[:30]}...) <= P({market_a.get("question", "A")[:30]}...)',
                    'actual': f'{price_b:.3f} > {price_a:.3f}',
                    'strategy': 'Buy B YES, Buy B NO',
                    'violation': price_b - price_a,
                }

        return arbitrage


# ============================================================
# 辅助函数
# ============================================================

def parse_all_intervals(markets: List[dict]) -> List[Tuple[dict, Optional[Interval]]]:
    """
    批量解析市场的区间信息

    Args:
        markets: 市场列表

    Returns:
        (market, interval) 元组列表
    """
    parser = IntervalParser()
    results = []

    for market in markets:
        interval = parser.parse(
            market.get('question', ''),
            market.get('event_description', '') or market.get('description', '')
        )
        if interval:
            results.append((market, interval))

    return results


def find_complementary_intervals(
    intervals: List[Tuple[dict, Interval]]
) -> List[dict]:
    """
    寻找互补的区间（可能形成完备集）

    例如：
    - "BTC < 100k" 和 "BTC > 100k" 互补（但不完备，缺少=100k）
    - "BTC < 100k", "BTC = 100k", "BTC > 100k" 形成完备集

    Args:
        intervals: (market, interval) 元组列表

    Returns:
        可能的完备集列表
    """
    # 按单位分组
    by_unit = {}
    for market, interval in intervals:
        unit = interval.unit or "UNKNOWN"
        if unit not in by_unit:
            by_unit[unit] = []
        by_unit[unit].append((market, interval))

    results = []

    for unit, group in by_unit.items():
        # 分析above/below对
        above = [m for m, i in group if i.type == IntervalType.ABOVE]
        below = [m for m, i in group if i.type == IntervalType.BELOW]
        ranges = [m for m, i in group if i.type == IntervalType.RANGE]

        # 简单检测：如果有above和below，可能形成区间划分
        if above and below:
            results.append({
                'unit': unit,
                'type': 'above_below_pair',
                'above_markets': above,
                'below_markets': below,
                'range_markets': ranges,
                'potential_exhaustive': len(above) + len(below) + len(ranges) >= 2
            })

    return results


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    parser = IntervalParser()

    # 测试解析
    test_questions = [
        "Will Bitcoin be above $100k by end of 2025?",
        "Will ETH price drop below $2000 in March?",
        "Will Solana price be between $100 and $150 on January 4?",
        "Will BTC exceed $150,000 in 2025?",
    ]

    print("=" * 60)
    print("Interval Parser Test")
    print("=" * 60)

    for q in test_questions:
        interval = parser.parse(q)
        if interval:
            print(f"\nQ: {q}")
            print(f"  → {interval}")
        else:
            print(f"\nQ: {q}")
            print(f"  → No interval detected")

    # 测试比较
    print("\n" + "=" * 60)
    print("Interval Comparison Test")
    print("=" * 60)

    market_a = {
        'question': 'Will BTC be above $100k?',
        'yes_price': 0.30,
        'description': ''
    }
    market_b = {
        'question': 'Will BTC be above $150k?',
        'yes_price': 0.15,
        'description': ''
    }

    result = parser.find_interval_arbitrage(market_a, market_b)
    if result:
        print(f"\nArbitrage detected!")
        print(f"  Type: {result['type']}")
        print(f"  Relation: {result['relation']}")
        print(f"  Constraint: {result['constraint']}")
        print(f"  Actual: {result['actual']}")
        print(f"  Strategy: {result['strategy']}")
    else:
        print("\nNo arbitrage detected")
