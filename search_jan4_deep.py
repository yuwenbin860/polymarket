#!/usr/bin/env python3
"""
深度搜索 January 4 的4类市场
============================

Type A: "What price will Bitcoin hit December 29-January 4?"
Type B: "Bitcoin above ___ on January 4?"
Type C: "Bitcoin Up or Down on January 4?"
Type D: "Bitcoin price on January 4?" (区间)
"""

import requests
import json
import re
from collections import defaultdict
from datetime import datetime

def search_jan4_deep():
    """深度搜索January 4市场"""

    base_url = "https://gamma-api.polymarket.com"
    session = requests.Session()
    session.headers.update({"User-Agent": "BTCSearch/1.0"})

    print("=" * 70)
    print("深度搜索 January 4 Bitcoin 市场 (4类)")
    print("=" * 70)

    # 获取尽可能多的市场
    all_markets = {}
    search_params = [
        {"order": "volume", "ascending": "false"},
        {"order": "liquidity", "ascending": "false"},
        {"order": "endDate", "ascending": "true"},
        {"order": "startDate", "ascending": "false"},
    ]

    for params in search_params:
        for offset in range(0, 2000, 500):
            try:
                url = f"{base_url}/markets"
                params.update({"limit": 500, "offset": offset})
                response = session.get(url, params=params, timeout=30)
                for m in response.json():
                    mid = m.get('id', '')
                    if mid:
                        all_markets[mid] = m
            except:
                pass

    print(f"Total unique markets: {len(all_markets)}")

    # 分类搜索
    type_a = []  # What price will Bitcoin hit
    type_b = []  # Bitcoin above
    type_c = []  # Bitcoin Up or Down
    type_d = []  # Bitcoin price (区间)

    for mid, m in all_markets.items():
        q = (m.get('question', '') or '').lower()

        # 必须与January 4相关
        if not ('january 4' in q or 'jan 4' in q or 'jan4' in q):
            # 检查跨时间段 (Dec 29 - Jan 4)
            if not ('january 4' in q or 'jan 4' in q or 'december 29' in q):
                continue

        # 必须与Bitcoin相关
        if not ('bitcoin' in q or 'btc' in q):
            continue

        # 解析价格
        prices_str = m.get('outcomePrices', '')
        yes_price = 0.5
        if prices_str:
            try:
                parts = prices_str.strip('[]').split(',')
                yes_price = float(parts[0].strip().strip('"\''))
            except:
                pass

        market_info = {
            'question': m.get('question', ''),
            'yes_price': yes_price,
            'no_price': 1 - yes_price,
            'volume': float(m.get('volume', 0) or 0),
            'liquidity': float(m.get('liquidity', 0) or 0),
            'closed': m.get('closed', False),
            'slug': m.get('slug', ''),
            'outcomes': m.get('outcomes', []),
            'description': m.get('description', '')[:200]
        }

        # 分类
        if 'what price' in q and 'hit' in q:
            type_a.append(market_info)
        elif 'above' in q:
            match = re.search(r'above\s+\$?([\d,]+)', q)
            if match:
                market_info['threshold'] = float(match.group(1).replace(',', ''))
            type_b.append(market_info)
        elif 'up or down' in q or 'up/down' in q:
            type_c.append(market_info)
        elif 'between' in q or ('price' in q and re.search(r'\d+.*\d+', q)):
            match = re.search(r'between\s+\$?([\d,]+)\s+and\s+\$?([\d,]+)', q)
            if match:
                market_info['range_low'] = float(match.group(1).replace(',', ''))
                market_info['range_high'] = float(match.group(2).replace(',', ''))
            type_d.append(market_info)
        elif 'below' in q or 'less than' in q:
            match = re.search(r'(?:below|less than)\s+\$?([\d,]+)', q)
            if match:
                market_info['threshold'] = float(match.group(1).replace(',', ''))
            type_b.append(market_info)  # 归入Above类（互补）

    # 打印结果
    print(f"\n找到市场分类:")
    print(f"  Type A (What price hit): {len(type_a)}")
    print(f"  Type B (Above/Below): {len(type_b)}")
    print(f"  Type C (Up or Down): {len(type_c)}")
    print(f"  Type D (Price Range): {len(type_d)}")

    print("\n" + "=" * 70)
    print("Type A: 'What price will Bitcoin hit' 市场")
    print("=" * 70)
    for m in type_a:
        print(f"\n  Q: {m['question']}")
        print(f"  YES: {m['yes_price']:.2%} | Liq: ${m['liquidity']:,.0f}")
        print(f"  Slug: {m['slug']}")

    print("\n" + "=" * 70)
    print("Type B: 'Bitcoin above/below' 市场")
    print("=" * 70)
    for m in sorted(type_b, key=lambda x: x.get('threshold', 0)):
        t = m.get('threshold', '?')
        direction = "Above" if 'above' in m['question'].lower() else "Below"
        print(f"\n  {direction} ${t:,.0f}: YES={m['yes_price']:.2%}, NO={m['no_price']:.2%}")
        print(f"  Q: {m['question'][:60]}...")

    print("\n" + "=" * 70)
    print("Type C: 'Bitcoin Up or Down' 市场")
    print("=" * 70)
    # 只显示非15分钟的市场
    daily_updown = [m for m in type_c if '15' not in m['question'] and 'AM' not in m['question'].upper() and 'PM' not in m['question'].upper()]
    short_term = [m for m in type_c if m not in daily_updown]

    print(f"\n  Daily Up/Down: {len(daily_updown)}")
    for m in daily_updown:
        print(f"    Q: {m['question']}")
        print(f"    YES: {m['yes_price']:.2%} | Outcomes: {m['outcomes']}")

    print(f"\n  Short-term (15min): {len(short_term)} markets")
    if short_term:
        # 汇总显示
        print(f"    Average YES: {sum(m['yes_price'] for m in short_term)/len(short_term):.2%}")

    print("\n" + "=" * 70)
    print("Type D: 'Bitcoin price' 区间市场")
    print("=" * 70)
    for m in sorted(type_d, key=lambda x: x.get('range_low', 0)):
        low = m.get('range_low', '?')
        high = m.get('range_high', '?')
        print(f"\n  ${low:,.0f} - ${high:,.0f}: YES={m['yes_price']:.2%}")
        print(f"  Q: {m['question'][:60]}...")

    # 合成套利分析
    print("\n" + "=" * 70)
    print("合成套利分析")
    print("=" * 70)

    if type_b and type_d:
        print("\n[Type B + Type D 等价验证]")
        for above in type_b:
            if above.get('threshold') and 'above' in above['question'].lower():
                threshold = above['threshold']
                above_no = above['no_price']

                # 计算 < threshold 的区间之和
                sum_below = 0
                components = []
                for r in type_d:
                    if r.get('range_high') and r['range_high'] <= threshold:
                        sum_below += r['yes_price']
                        components.append(f"${r['range_low']:,.0f}-${r['range_high']:,.0f}: {r['yes_price']:.2%}")

                if components:
                    print(f"\n  Above ${threshold:,.0f}:")
                    print(f"    Above NO = {above_no:.2%} (P < ${threshold:,.0f})")
                    print(f"    区间组合:")
                    for c in components:
                        print(f"      + {c}")
                    print(f"    区间总和 = {sum_below:.2%}")
                    gap = abs(above_no - sum_below)
                    print(f"    价差 = {gap:.2%}")
                    if gap > 0.5:
                        print(f"    -> 区间不完整")
                    elif gap > 0.02:
                        print(f"    -> [!!!] 可能存在套利!")
                    else:
                        print(f"    -> [OK] 定价一致")

    # 保存结果
    output = {
        'timestamp': datetime.now().isoformat(),
        'type_a': type_a,
        'type_b': type_b,
        'type_c_daily': daily_updown,
        'type_c_short': len(short_term),
        'type_d': type_d
    }

    with open('output/jan4_deep_search.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n\nSaved to output/jan4_deep_search.json")

    return output

if __name__ == "__main__":
    search_jan4_deep()
