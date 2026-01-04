#!/usr/bin/env python3
"""
深度搜索 January 6 的所有Bitcoin市场
"""

import requests
import json
import re
from datetime import datetime

def search_jan6():
    """深度搜索January 6市场"""

    base_url = "https://gamma-api.polymarket.com"
    session = requests.Session()
    session.headers.update({"User-Agent": "BTCSearch/1.0"})

    print("=" * 70)
    print("深度搜索 January 6 Bitcoin 市场")
    print("=" * 70)

    # 获取所有市场（尽可能多）
    all_markets = []
    for offset in range(0, 3000, 500):
        try:
            url = f"{base_url}/markets"
            params = {
                "limit": 500,
                "offset": offset,
            }
            response = session.get(url, params=params, timeout=30)
            markets = response.json()
            if not markets:
                break
            all_markets.extend(markets)
            print(f"  Offset {offset}: got {len(markets)} markets")
        except Exception as e:
            print(f"  Offset {offset}: error - {e}")
            break

    print(f"\nTotal markets: {len(all_markets)}")

    # 找所有January 6的Bitcoin市场
    jan6_markets = []
    for m in all_markets:
        q = (m.get('question', '') or '').lower()
        if ('bitcoin' in q or 'btc' in q) and ('january 6' in q or 'jan 6' in q):
            jan6_markets.append(m)

    print(f"January 6 Bitcoin markets: {len(jan6_markets)}")

    # 详细分析
    print("\n" + "=" * 70)
    print("所有 January 6 Bitcoin 市场详情")
    print("=" * 70)

    above_markets = []
    below_markets = []
    range_markets = []
    other_markets = []

    for m in jan6_markets:
        q = m.get('question', '')
        q_lower = q.lower()

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
            'question': q,
            'yes_price': yes_price,
            'no_price': 1 - yes_price,
            'volume': float(m.get('volume', 0) or 0),
            'liquidity': float(m.get('liquidity', 0) or 0),
            'closed': m.get('closed', False),
            'slug': m.get('slug', '')
        }

        # 分类
        if 'above' in q_lower:
            match = re.search(r'above\s+\$?([\d,]+)', q_lower)
            if match:
                market_info['threshold'] = float(match.group(1).replace(',', ''))
            above_markets.append(market_info)
        elif 'below' in q_lower or 'less than' in q_lower:
            match = re.search(r'(?:below|less than)\s+\$?([\d,]+)', q_lower)
            if match:
                market_info['threshold'] = float(match.group(1).replace(',', ''))
            below_markets.append(market_info)
        elif 'between' in q_lower:
            match = re.search(r'between\s+\$?([\d,]+)\s+and\s+\$?([\d,]+)', q_lower)
            if match:
                market_info['range_low'] = float(match.group(1).replace(',', ''))
                market_info['range_high'] = float(match.group(2).replace(',', ''))
            range_markets.append(market_info)
        else:
            other_markets.append(market_info)

    # 打印所有市场
    print("\n[ABOVE Markets]")
    for m in sorted(above_markets, key=lambda x: x.get('threshold', 0)):
        status = "[CLOSED]" if m['closed'] else "[ACTIVE]"
        t = m.get('threshold', '?')
        print(f"  {status} Above ${t:,.0f}: YES={m['yes_price']:.2%}, NO={m['no_price']:.2%}")
        print(f"         Liq: ${m['liquidity']:,.0f} | {m['slug'][:40]}")

    print("\n[BELOW Markets]")
    for m in sorted(below_markets, key=lambda x: x.get('threshold', 0)):
        status = "[CLOSED]" if m['closed'] else "[ACTIVE]"
        t = m.get('threshold', '?')
        print(f"  {status} Below ${t:,.0f}: YES={m['yes_price']:.2%}")
        print(f"         Liq: ${m['liquidity']:,.0f} | {m['slug'][:40]}")

    print("\n[RANGE Markets]")
    for m in sorted(range_markets, key=lambda x: x.get('range_low', 0)):
        status = "[CLOSED]" if m['closed'] else "[ACTIVE]"
        low = m.get('range_low', '?')
        high = m.get('range_high', '?')
        print(f"  {status} ${low:,.0f}-${high:,.0f}: YES={m['yes_price']:.2%}")
        print(f"         Liq: ${m['liquidity']:,.0f} | {m['slug'][:40]}")

    print("\n[OTHER Markets]")
    for m in other_markets:
        status = "[CLOSED]" if m['closed'] else "[ACTIVE]"
        print(f"  {status} {m['question'][:60]}...")

    # 完备性分析
    print("\n" + "=" * 70)
    print("完备性分析")
    print("=" * 70)

    # 收集所有区间
    all_ranges = []
    for m in range_markets:
        if m.get('range_low') and m.get('range_high'):
            all_ranges.append((m['range_low'], m['range_high'], m['yes_price'], m['question']))

    # 排序
    all_ranges.sort(key=lambda x: x[0])

    print("\n已有区间 (按价格排序):")
    total_yes = 0
    for low, high, price, q in all_ranges:
        print(f"  ${low:,.0f} - ${high:,.0f}: YES = {price:.2%}")
        total_yes += price

    # 加上 below 和 above
    for m in below_markets:
        if m.get('threshold'):
            print(f"  < ${m['threshold']:,.0f}: YES = {m['yes_price']:.2%}")
            total_yes += m['yes_price']

    for m in above_markets:
        if m.get('threshold'):
            # 只加最高的above (避免重复)
            pass

    print(f"\n区间覆盖总和 (不含Above): {total_yes:.2%}")

    # 找缺失的区间
    print("\n缺失的区间:")
    if all_ranges:
        # 检查 below 最低区间
        lowest = all_ranges[0][0]
        below_threshold = None
        for m in below_markets:
            if m.get('threshold'):
                below_threshold = m['threshold']

        if below_threshold and below_threshold < lowest:
            print(f"  [!] 缺少 ${below_threshold:,.0f} - ${lowest:,.0f}")
        elif not below_threshold:
            print(f"  [!] 缺少 < ${lowest:,.0f} 的市场")

        # 检查区间间隙
        for i in range(len(all_ranges) - 1):
            if all_ranges[i][1] < all_ranges[i+1][0]:
                print(f"  [!] 缺少 ${all_ranges[i][1]:,.0f} - ${all_ranges[i+1][0]:,.0f}")

        # 检查 above 最高区间
        highest = all_ranges[-1][1]
        for m in above_markets:
            if m.get('threshold') and m['threshold'] > highest:
                print(f"  [?] Above ${m['threshold']:,.0f} 存在，但缺少 ${highest:,.0f} - ${m['threshold']:,.0f}")

    # 合成套利分析
    print("\n" + "=" * 70)
    print("合成套利机会分析")
    print("=" * 70)

    for above in above_markets:
        if above.get('threshold'):
            threshold = above['threshold']
            above_no = above['no_price']  # P(BTC < threshold)

            # 计算所有 < threshold 的概率之和
            sum_below = 0
            components = []

            # 加below市场
            for m in below_markets:
                if m.get('threshold') and m['threshold'] <= threshold:
                    sum_below += m['yes_price']
                    components.append(f"Below ${m['threshold']:,.0f}: {m['yes_price']:.2%}")

            # 加区间市场
            for m in range_markets:
                if m.get('range_high') and m['range_high'] <= threshold:
                    sum_below += m['yes_price']
                    components.append(f"${m['range_low']:,.0f}-${m['range_high']:,.0f}: {m['yes_price']:.2%}")

            print(f"\n阈值 ${threshold:,.0f}:")
            print(f"  Above市场: Above ${threshold:,.0f} = YES {above['yes_price']:.2%}")
            print(f"  等价关系: P(BTC < ${threshold:,.0f}) = Above NO = {above_no:.2%}")
            print(f"  区间组合:")
            for c in components:
                print(f"    + {c}")
            print(f"  区间总和: {sum_below:.2%}")
            print(f"  理论应等于: {above_no:.2%}")
            print(f"  价差: {abs(above_no - sum_below):.2%}")

            if abs(above_no - sum_below) > 0.5:
                print(f"  [!] 价差过大 - 说明区间覆盖不完整")
            elif abs(above_no - sum_below) > 0.02:
                print(f"  [!!!] 可能存在套利机会!")
            else:
                print(f"  [OK] 定价基本一致")

    # 保存数据
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_markets': len(jan6_markets),
        'above_markets': above_markets,
        'below_markets': below_markets,
        'range_markets': range_markets,
        'other_markets': [m['question'] for m in other_markets]
    }

    with open('output/jan6_complete.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n\nSaved to output/jan6_complete.json")

if __name__ == "__main__":
    search_jan6()
