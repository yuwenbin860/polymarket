#!/usr/bin/env python3
"""
搜索所有January Bitcoin市场 - 多种排序方式
"""

import requests
import json
import re
from collections import defaultdict
from datetime import datetime

def search_all():
    """多种方式搜索"""

    base_url = "https://gamma-api.polymarket.com"
    session = requests.Session()
    session.headers.update({"User-Agent": "BTCSearch/1.0"})

    print("Searching with multiple strategies...")

    all_markets = set()
    market_data = {}

    # 策略1: 按volume排序
    for offset in range(0, 2000, 500):
        try:
            url = f"{base_url}/markets"
            params = {"limit": 500, "offset": offset, "order": "volume", "ascending": "false"}
            response = session.get(url, params=params, timeout=30)
            for m in response.json():
                mid = m.get('id', '')
                if mid and mid not in all_markets:
                    all_markets.add(mid)
                    market_data[mid] = m
        except:
            pass

    print(f"After volume sort: {len(all_markets)} unique markets")

    # 策略2: 按liquidity排序
    for offset in range(0, 2000, 500):
        try:
            url = f"{base_url}/markets"
            params = {"limit": 500, "offset": offset, "order": "liquidity", "ascending": "false"}
            response = session.get(url, params=params, timeout=30)
            for m in response.json():
                mid = m.get('id', '')
                if mid and mid not in all_markets:
                    all_markets.add(mid)
                    market_data[mid] = m
        except:
            pass

    print(f"After liquidity sort: {len(all_markets)} unique markets")

    # 策略3: 按endDate排序
    for offset in range(0, 1000, 500):
        try:
            url = f"{base_url}/markets"
            params = {"limit": 500, "offset": offset, "order": "endDate", "ascending": "true"}
            response = session.get(url, params=params, timeout=30)
            for m in response.json():
                mid = m.get('id', '')
                if mid and mid not in all_markets:
                    all_markets.add(mid)
                    market_data[mid] = m
        except:
            pass

    print(f"After endDate sort: {len(all_markets)} unique markets")

    # 过滤Bitcoin + January市场
    jan_btc_markets = []
    for mid, m in market_data.items():
        q = (m.get('question', '') or '').lower()
        if ('bitcoin' in q or 'btc' in q) and 'january' in q:
            jan_btc_markets.append(m)

    print(f"\nBitcoin + January markets: {len(jan_btc_markets)}")

    # 按日期分组
    by_date = defaultdict(list)
    for m in jan_btc_markets:
        q = m.get('question', '').lower()
        # 提取日期
        match = re.search(r'january\s+(\d+)', q)
        if match:
            day = int(match.group(1))
            by_date[day].append(m)

    # 打印每个日期的市场
    print("\n" + "=" * 70)
    for day in sorted(by_date.keys()):
        markets = by_date[day]
        print(f"\n### JANUARY {day} ({len(markets)} markets)")

        # 分类
        above = []
        below = []
        ranges = []
        updown = []
        other = []

        for m in markets:
            q = m.get('question', '')
            ql = q.lower()

            # 价格
            prices_str = m.get('outcomePrices', '')
            yes_price = 0.5
            if prices_str:
                try:
                    parts = prices_str.strip('[]').split(',')
                    yes_price = float(parts[0].strip().strip('"\''))
                except:
                    pass

            info = {'q': q, 'yes': yes_price, 'no': 1-yes_price,
                   'liq': float(m.get('liquidity', 0) or 0),
                   'closed': m.get('closed', False)}

            if 'above' in ql:
                match = re.search(r'above\s+\$?([\d,]+)', ql)
                if match:
                    info['t'] = float(match.group(1).replace(',', ''))
                above.append(info)
            elif 'below' in ql or 'less than' in ql:
                match = re.search(r'(?:below|less than)\s+\$?([\d,]+)', ql)
                if match:
                    info['t'] = float(match.group(1).replace(',', ''))
                below.append(info)
            elif 'between' in ql:
                match = re.search(r'between\s+\$?([\d,]+)\s+and\s+\$?([\d,]+)', ql)
                if match:
                    info['low'] = float(match.group(1).replace(',', ''))
                    info['high'] = float(match.group(2).replace(',', ''))
                ranges.append(info)
            elif 'up or down' in ql:
                updown.append(info)
            else:
                other.append(info)

        # 打印
        if above:
            print("  ABOVE:")
            for a in sorted(above, key=lambda x: x.get('t', 0)):
                s = "[C]" if a['closed'] else "[A]"
                print(f"    {s} >${a.get('t',0):,.0f}: YES={a['yes']:.2%} NO={a['no']:.2%}")

        if below:
            print("  BELOW:")
            for b in sorted(below, key=lambda x: x.get('t', 0)):
                s = "[C]" if b['closed'] else "[A]"
                print(f"    {s} <${b.get('t',0):,.0f}: YES={b['yes']:.2%}")

        if ranges:
            print("  RANGES:")
            for r in sorted(ranges, key=lambda x: x.get('low', 0)):
                s = "[C]" if r['closed'] else "[A]"
                print(f"    {s} ${r.get('low',0):,.0f}-${r.get('high',0):,.0f}: YES={r['yes']:.2%}")

        if updown:
            print(f"  UP/DOWN: {len(updown)} markets")

        # 完备性检查
        if ranges or above or below:
            print("\n  ANALYSIS:")
            total = 0
            if below:
                for b in below:
                    total += b['yes']
                    print(f"    + Below ${b.get('t',0):,.0f}: {b['yes']:.2%}")
            for r in sorted(ranges, key=lambda x: x.get('low', 0)):
                total += r['yes']
                print(f"    + ${r.get('low',0):,.0f}-${r.get('high',0):,.0f}: {r['yes']:.2%}")

            print(f"    = Total (excl Above): {total:.2%}")

            # 与Above比较
            for a in above:
                if a.get('t'):
                    # 计算 < threshold 的概率
                    sum_below_t = 0
                    for b in below:
                        if b.get('t') and b['t'] <= a['t']:
                            sum_below_t += b['yes']
                    for r in ranges:
                        if r.get('high') and r['high'] <= a['t']:
                            sum_below_t += r['yes']

                    print(f"\n    Compare with Above ${a['t']:,.0f}:")
                    print(f"      Above NO = {a['no']:.2%} (P < ${a['t']:,.0f})")
                    print(f"      Sum of ranges < ${a['t']:,.0f} = {sum_below_t:.2%}")
                    gap = abs(a['no'] - sum_below_t)
                    print(f"      Gap = {gap:.2%}")
                    if gap > 0.5:
                        print(f"      -> Incomplete coverage")
                    elif gap > 0.02:
                        print(f"      -> POTENTIAL ARBITRAGE!")

    # 保存
    output = {
        'timestamp': datetime.now().isoformat(),
        'by_date': {str(d): len(m) for d, m in by_date.items()}
    }
    with open('output/jan_all_dates.json', 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n\nSummary saved to output/jan_all_dates.json")

if __name__ == "__main__":
    search_all()
