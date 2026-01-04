#!/usr/bin/env python3
"""
搜索 "What price will Bitcoin hit" 类型市场
"""

import requests
import json
from datetime import datetime

def search_price_hit():
    """搜索price hit市场"""

    base_url = "https://gamma-api.polymarket.com"
    session = requests.Session()
    session.headers.update({"User-Agent": "BTCSearch/1.0"})

    print("Searching for 'What price will Bitcoin hit' markets...")

    # 获取所有市场
    all_markets = {}
    for offset in range(0, 5000, 500):
        try:
            url = f"{base_url}/markets"
            params = {"limit": 500, "offset": offset}
            response = session.get(url, params=params, timeout=30)
            markets = response.json()
            if not markets:
                break
            for m in markets:
                mid = m.get('id', '')
                if mid:
                    all_markets[mid] = m
            print(f"  Offset {offset}: {len(markets)} markets")
        except Exception as e:
            print(f"  Error: {e}")
            break

    print(f"\nTotal markets: {len(all_markets)}")

    # 搜索各种模式
    patterns = [
        'what price',
        'price hit',
        'will hit',
        'bitcoin hit',
        'btc hit',
        'reach',
        'december 29',
        'dec 29',
    ]

    found_markets = []

    for mid, m in all_markets.items():
        q = (m.get('question', '') or '').lower()

        # Bitcoin相关
        if not ('bitcoin' in q or 'btc' in q):
            continue

        # 匹配任一模式
        for pattern in patterns:
            if pattern in q:
                # 解析价格
                prices_str = m.get('outcomePrices', '')
                yes_price = 0.5
                if prices_str:
                    try:
                        parts = prices_str.strip('[]').split(',')
                        yes_price = float(parts[0].strip().strip('"\''))
                    except:
                        pass

                found_markets.append({
                    'question': m.get('question', ''),
                    'pattern': pattern,
                    'yes_price': yes_price,
                    'slug': m.get('slug', ''),
                    'closed': m.get('closed', False),
                    'outcomes': m.get('outcomes', [])
                })
                break

    # 去重
    seen = set()
    unique_markets = []
    for m in found_markets:
        if m['question'] not in seen:
            seen.add(m['question'])
            unique_markets.append(m)

    print(f"\nFound {len(unique_markets)} unique markets matching patterns")

    # 按模式分组打印
    print("\n" + "=" * 70)
    for pattern in patterns:
        matches = [m for m in unique_markets if m['pattern'] == pattern]
        if matches:
            print(f"\nPattern: '{pattern}' ({len(matches)} markets)")
            for m in matches[:10]:  # 最多10个
                status = "[C]" if m['closed'] else "[A]"
                print(f"  {status} {m['question'][:70]}...")
                print(f"      YES: {m['yes_price']:.2%} | {m['slug'][:40]}")

    # 特别查找January 4相关
    print("\n" + "=" * 70)
    print("January 4 相关:")
    jan4_markets = [m for m in unique_markets
                    if 'january 4' in m['question'].lower()
                    or 'jan 4' in m['question'].lower()
                    or 'jan4' in m['question'].lower()]

    for m in jan4_markets:
        print(f"\n  {m['question']}")
        print(f"  YES: {m['yes_price']:.2%}")
        print(f"  Outcomes: {m['outcomes']}")

    # 保存
    with open('output/price_hit_search.json', 'w', encoding='utf-8') as f:
        json.dump(unique_markets, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to output/price_hit_search.json")

if __name__ == "__main__":
    search_price_hit()
