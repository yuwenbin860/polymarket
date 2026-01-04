#!/usr/bin/env python3
"""
合成套利分析 - 分析现有Bitcoin市场数据
=====================================

基于已获取的数据，分析是否存在合成套利机会
"""

import json
import re
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

def load_market_data():
    """加载已保存的市场数据"""
    with open('output/all_btc_markets.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_threshold(question: str) -> Optional[float]:
    """提取阈值"""
    # 格式: above $82,000 / above $96,000 等
    patterns = [
        r'above\s+\$?([\d,]+)',
        r'below\s+\$?([\d,]+)',
        r'\$?([\d,]+)\s+or\s+(?:less|more)',
    ]
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(',', ''))
    return None

def extract_range(question: str) -> Tuple[Optional[float], Optional[float]]:
    """提取区间"""
    # 格式: between $78,000 and $80,000
    pattern = r'between\s+\$?([\d,]+)\s+and\s+\$?([\d,]+)'
    match = re.search(pattern, question, re.IGNORECASE)
    if match:
        low = float(match.group(1).replace(',', ''))
        high = float(match.group(2).replace(',', ''))
        return (low, high)
    return (None, None)

def extract_date(question: str) -> Optional[str]:
    """提取日期"""
    # 格式: January 5, January 7 等
    pattern = r'January\s+(\d+)'
    match = re.search(pattern, question, re.IGNORECASE)
    if match:
        return f"January {match.group(1)}"
    return None

def classify_market(question: str) -> str:
    """分类市场类型"""
    q = question.lower()
    if 'above' in q:
        return 'above_threshold'
    elif 'below' in q:
        return 'below_threshold'
    elif 'between' in q:
        return 'price_range'
    elif 'up or down' in q:
        return 'up_down'
    elif 'reach' in q:
        return 'reach_target'
    return 'other'

def analyze_markets():
    """分析市场数据"""
    data = load_market_data()

    # 合并所有市场
    all_markets = data['jan3_markets'] + data['other_jan_markets']

    print("=" * 70)
    print("合成套利分析报告")
    print("=" * 70)
    print(f"分析时间: {datetime.now().isoformat()}")
    print(f"总市场数: {len(all_markets)}")

    # 按日期分组
    markets_by_date = defaultdict(list)

    for m in all_markets:
        q = m['question']
        date = extract_date(q)
        market_type = classify_market(q)
        threshold = extract_threshold(q)
        range_low, range_high = extract_range(q)

        market_info = {
            'question': q,
            'yes_price': m['yes_price'],
            'no_price': m['no_price'],
            'type': market_type,
            'threshold': threshold,
            'range_low': range_low,
            'range_high': range_high,
            'date': date
        }

        if date:
            markets_by_date[date].append(market_info)

    # 分析每个日期
    print("\n" + "-" * 70)
    print("按日期分组的市场")
    print("-" * 70)

    for date in sorted(markets_by_date.keys()):
        markets = markets_by_date[date]
        print(f"\n### {date} ({len(markets)} markets)")

        above_markets = [m for m in markets if m['type'] == 'above_threshold']
        range_markets = [m for m in markets if m['type'] == 'price_range']
        other_markets = [m for m in markets if m['type'] not in ['above_threshold', 'price_range']]

        if above_markets:
            print(f"\n  Above Threshold Markets:")
            for m in sorted(above_markets, key=lambda x: x['threshold'] or 0):
                print(f"    - Above ${m['threshold']:,.0f}: YES={m['yes_price']:.2%}, NO={m['no_price']:.2%}")

        if range_markets:
            print(f"\n  Price Range Markets:")
            for m in sorted(range_markets, key=lambda x: x['range_low'] or 0):
                print(f"    - ${m['range_low']:,.0f}-${m['range_high']:,.0f}: YES={m['yes_price']:.2%}")

        if other_markets:
            print(f"\n  Other Markets:")
            for m in other_markets:
                print(f"    - {m['question'][:50]}... YES={m['yes_price']:.2%}")

    # 合成套利分析
    print("\n" + "=" * 70)
    print("合成套利机会分析")
    print("=" * 70)

    for date in sorted(markets_by_date.keys()):
        markets = markets_by_date[date]
        above_markets = [m for m in markets if m['type'] == 'above_threshold' and m['threshold']]
        range_markets = [m for m in markets if m['type'] == 'price_range' and m['range_low']]

        if len(above_markets) >= 1 and len(range_markets) >= 1:
            print(f"\n### {date} - 潜在合成套利")

            # 检查逻辑关系
            for above in above_markets:
                threshold = above['threshold']
                print(f"\n  [Above ${threshold:,.0f}]")
                print(f"    Above YES = {above['yes_price']:.2%}")
                print(f"    Above NO = {above['no_price']:.2%} (即 Below ${threshold:,.0f})")

                # 查找相关区间
                related_ranges = []
                for r in range_markets:
                    if r['range_high'] and r['range_high'] <= threshold:
                        related_ranges.append(r)

                if related_ranges:
                    sum_below = sum(r['yes_price'] for r in related_ranges)
                    print(f"\n    低于阈值的区间:")
                    for r in related_ranges:
                        print(f"      ${r['range_low']:,.0f}-${r['range_high']:,.0f}: YES={r['yes_price']:.2%}")
                    print(f"\n    区间YES之和: {sum_below:.2%}")
                    print(f"    Above NO (Below): {above['no_price']:.2%}")

                    gap = abs(above['no_price'] - sum_below)
                    print(f"\n    价差: {gap:.2%}")

                    if gap > 0.02:
                        print(f"    *** 发现套利机会! ***")
                    else:
                        print(f"    (价差不足2%, 无明显套利)")

        # 检查区间完备性
        if len(range_markets) >= 2:
            print(f"\n  [区间完备性检查]")
            total_yes = sum(m['yes_price'] for m in range_markets)
            print(f"    所有区间YES之和: {total_yes:.2%}")
            if total_yes < 0.98:
                print(f"    *** 区间不完整或存在套利空间 ***")
            elif total_yes > 1.02:
                print(f"    *** 区间重叠或定价错误 ***")

    # 生成摘要
    print("\n" + "=" * 70)
    print("验证结论")
    print("=" * 70)

    # January 5 分析
    jan5_markets = markets_by_date.get("January 5", [])
    if jan5_markets:
        print("\n### January 5 详细分析:")
        above_82k = next((m for m in jan5_markets if m['threshold'] == 82000), None)
        range_78_80k = next((m for m in jan5_markets if m['range_low'] == 78000), None)

        if above_82k and range_78_80k:
            print(f"""
  市场1: "Bitcoin above $82,000 on January 5"
    - YES = {above_82k['yes_price']:.2%} (BTC >= $82k)
    - NO  = {above_82k['no_price']:.2%} (BTC < $82k)

  市场2: "Bitcoin between $78,000-$80,000 on January 5"
    - YES = {range_78_80k['yes_price']:.2%} ($78k <= BTC < $80k)

  逻辑关系:
    如果 BTC < $82k (Above NO = {above_82k['no_price']:.2%})
    则可能落在以下区间:
      - $78k-$80k (需要这个市场) = {range_78_80k['yes_price']:.2%}
      - $80k-$82k (需要这个市场) = ???
      - <$78k (需要这个市场) = ???

  结论:
    - 缺少完整的区间覆盖市场
    - 无法构成完备的合成套利
    - 但这个结构展示了合成套利的基本原理!
""")

    print("\n### 总结:")
    print("""
  1. 现有数据中January 5有2个相关市场 (Above + Range)
  2. 但缺少完整的区间覆盖，无法验证完整的合成套利
  3. 用户描述的January 3完整场景(Up/Down + 多区间 + Above)未在当前API数据中找到
  4. 可能原因: January 3已过期、市场已结算、或使用不同的命名

  建议:
  - 等待新的每日Bitcoin市场出现
  - 或手动获取特定市场的slug来验证
""")

if __name__ == "__main__":
    analyze_markets()
