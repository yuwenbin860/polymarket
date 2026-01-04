#!/usr/bin/env python3
"""
搜索 January 4, 5, 6 的完整区间组合
"""

import requests
import json
import re
from collections import defaultdict
from datetime import datetime

def fetch_and_analyze():
    """获取并分析January 4-6的市场"""

    base_url = "https://gamma-api.polymarket.com"
    session = requests.Session()
    session.headers.update({"User-Agent": "BTCSearch/1.0"})

    print("=" * 70)
    print("搜索 January 4, 5, 6 Bitcoin 完整区间组合")
    print("=" * 70)

    # 获取大量市场
    all_markets = []
    for offset in [0, 500, 1000]:
        try:
            url = f"{base_url}/markets"
            params = {
                "limit": 500,
                "offset": offset,
                "order": "liquidity",
                "ascending": "false"
            }
            response = session.get(url, params=params, timeout=30)
            markets = response.json()
            all_markets.extend(markets)
        except Exception as e:
            print(f"Error at offset {offset}: {e}")

    print(f"Total markets fetched: {len(all_markets)}")

    # 过滤Bitcoin市场
    btc_markets = []
    for m in all_markets:
        q = (m.get('question', '') or '').lower()
        if 'bitcoin' in q or 'btc' in q:
            btc_markets.append(m)

    print(f"Bitcoin markets: {len(btc_markets)}")

    # 按日期分组
    dates_to_check = ['january 4', 'january 5', 'january 6', 'jan 4', 'jan 5', 'jan 6']
    markets_by_date = defaultdict(list)

    for m in btc_markets:
        q = m.get('question', '').lower()
        for date_str in dates_to_check:
            if date_str in q:
                # 标准化日期
                normalized = date_str.replace('jan ', 'january ')
                markets_by_date[normalized].append(m)
                break

    # 分析每个日期
    for date in ['january 4', 'january 5', 'january 6']:
        markets = markets_by_date.get(date, [])

        print(f"\n{'='*70}")
        print(f"### {date.upper()} ({len(markets)} markets)")
        print('='*70)

        if not markets:
            print("  No markets found")
            continue

        # 分类
        above_markets = []
        below_markets = []
        range_markets = []
        updown_markets = []
        other_markets = []

        for m in markets:
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
                'closed': m.get('closed', False)
            }

            # 提取数值
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
            elif 'up or down' in q_lower or 'up/down' in q_lower:
                updown_markets.append(market_info)
            else:
                other_markets.append(market_info)

        # 打印Above市场
        if above_markets:
            print(f"\n  [ABOVE Threshold Markets] ({len(above_markets)})")
            for m in sorted(above_markets, key=lambda x: x.get('threshold', 0)):
                status = "[CLOSED]" if m['closed'] else "[ACTIVE]"
                threshold = m.get('threshold', '?')
                print(f"    {status} Above ${threshold:,.0f}: YES={m['yes_price']:.2%}, NO={m['no_price']:.2%}")
                print(f"           Liquidity: ${m['liquidity']:,.0f}")

        # 打印Below市场
        if below_markets:
            print(f"\n  [BELOW Threshold Markets] ({len(below_markets)})")
            for m in sorted(below_markets, key=lambda x: x.get('threshold', 0)):
                status = "[CLOSED]" if m['closed'] else "[ACTIVE]"
                threshold = m.get('threshold', '?')
                print(f"    {status} Below ${threshold:,.0f}: YES={m['yes_price']:.2%}")

        # 打印区间市场
        if range_markets:
            print(f"\n  [RANGE Markets] ({len(range_markets)})")
            for m in sorted(range_markets, key=lambda x: x.get('range_low', 0)):
                status = "[CLOSED]" if m['closed'] else "[ACTIVE]"
                low = m.get('range_low', '?')
                high = m.get('range_high', '?')
                print(f"    {status} ${low:,.0f}-${high:,.0f}: YES={m['yes_price']:.2%}")
                print(f"           Liquidity: ${m['liquidity']:,.0f}")

        # 打印Up/Down市场
        if updown_markets:
            print(f"\n  [UP/DOWN Markets] ({len(updown_markets)})")
            for m in updown_markets[:5]:  # 最多5个
                status = "[CLOSED]" if m['closed'] else "[ACTIVE]"
                print(f"    {status} {m['question'][:55]}...")
                print(f"           YES={m['yes_price']:.2%}")

        # 打印其他市场
        if other_markets:
            print(f"\n  [OTHER Markets] ({len(other_markets)})")
            for m in other_markets[:3]:
                status = "[CLOSED]" if m['closed'] else "[ACTIVE]"
                print(f"    {status} {m['question'][:55]}...")

        # 分析完备性
        print(f"\n  --- 完备性分析 ---")

        if range_markets:
            # 检查区间是否连续
            ranges = sorted([(m.get('range_low', 0), m.get('range_high', 0), m['yes_price'])
                           for m in range_markets if m.get('range_low')])

            if ranges:
                print(f"  区间覆盖: ${ranges[0][0]:,.0f} - ${ranges[-1][1]:,.0f}")
                total_yes = sum(r[2] for r in ranges)
                print(f"  区间YES之和: {total_yes:.2%}")

                # 检查间隙
                gaps = []
                for i in range(len(ranges) - 1):
                    if ranges[i][1] < ranges[i+1][0]:
                        gaps.append((ranges[i][1], ranges[i+1][0]))

                if gaps:
                    print(f"  [!] 发现区间间隙: {gaps}")
                else:
                    print(f"  [OK] 区间连续无间隙")

        if above_markets and range_markets:
            # 检查Above与区间的等价关系
            print(f"\n  --- 合成套利检查 ---")
            for above in above_markets:
                if above.get('threshold'):
                    threshold = above['threshold']
                    # 找所有 < threshold 的区间
                    below_ranges = [r for r in range_markets
                                   if r.get('range_high') and r['range_high'] <= threshold]
                    if below_ranges:
                        sum_below = sum(r['yes_price'] for r in below_ranges)
                        above_no = above['no_price']  # BTC < threshold

                        print(f"\n  阈值 ${threshold:,.0f}:")
                        print(f"    Above NO (< threshold): {above_no:.2%}")
                        print(f"    区间 < threshold 之和: {sum_below:.2%}")
                        gap = abs(above_no - sum_below)
                        print(f"    价差: {gap:.2%}")

                        if gap > 0.02:
                            print(f"    [!!!] 可能存在套利机会!")
                        elif gap > 0.005:
                            print(f"    [~] 小幅价差，需考虑交易成本")
                        else:
                            print(f"    [OK] 定价一致")

    # 保存结果
    output = {
        'timestamp': datetime.now().isoformat(),
        'markets_by_date': {
            date: [
                {
                    'question': m.get('question', ''),
                    'yes_price': float(m.get('outcomePrices', '["0.5"]').strip('[]').split(',')[0].strip().strip('"\'') or 0.5),
                    'liquidity': float(m.get('liquidity', 0) or 0),
                    'closed': m.get('closed', False)
                }
                for m in markets_by_date.get(date, [])
            ]
            for date in ['january 4', 'january 5', 'january 6']
        }
    }

    with open('output/jan456_markets.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n\nSaved to output/jan456_markets.json")

if __name__ == "__main__":
    fetch_and_analyze()
