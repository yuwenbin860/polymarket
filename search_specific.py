#!/usr/bin/env python3
"""
搜索特定的Bitcoin市场 - 尝试多种方式
"""

import requests
import json
from datetime import datetime

def search_markets():
    """尝试多种方式搜索Bitcoin市场"""

    base_url = "https://gamma-api.polymarket.com"
    session = requests.Session()
    session.headers.update({"User-Agent": "BTCSearch/1.0"})

    print("=" * 70)
    print("搜索Bitcoin市场 - 多种方式")
    print("=" * 70)

    results = []

    # 方法1: 搜索特定slug模式
    slug_patterns = [
        "bitcoin-up-down",
        "btc-updown",
        "bitcoin-price",
        "btc-price",
        "bitcoin-above",
        "btc-above",
    ]

    print("\n[1] 搜索slug模式...")
    for pattern in slug_patterns:
        try:
            url = f"{base_url}/markets"
            params = {"limit": 100, "slug_contains": pattern}
            response = session.get(url, params=params, timeout=30)
            markets = response.json()
            if markets:
                print(f"  Pattern '{pattern}': {len(markets)} markets")
                for m in markets[:3]:
                    print(f"    - {m.get('question', '')[:60]}...")
        except:
            pass

    # 方法2: 获取更多市场（分页）
    print("\n[2] 分页获取市场...")
    all_markets = []
    for offset in [0, 500, 1000]:
        try:
            url = f"{base_url}/markets"
            params = {
                "limit": 500,
                "offset": offset,
                "order": "volume",
                "ascending": "false"
            }
            response = session.get(url, params=params, timeout=30)
            markets = response.json()
            all_markets.extend(markets)
            print(f"  Offset {offset}: got {len(markets)} markets")
        except Exception as e:
            print(f"  Offset {offset}: error - {e}")

    # 过滤Bitcoin + price相关
    btc_price_markets = []
    for m in all_markets:
        q = (m.get('question', '') or '').lower()
        if ('bitcoin' in q or 'btc' in q):
            if any(kw in q for kw in ['price', 'above', 'below', 'between', 'up', 'down']):
                btc_price_markets.append(m)

    print(f"\n  Total BTC price-related markets: {len(btc_price_markets)}")

    # 打印所有找到的市场
    print("\n[3] 所有Bitcoin价格相关市场:")
    print("-" * 70)

    seen_questions = set()
    for m in btc_price_markets:
        q = m.get('question', '')
        if q in seen_questions:
            continue
        seen_questions.add(q)

        prices_str = m.get('outcomePrices', '')
        yes_price = 0.5
        if prices_str:
            try:
                parts = prices_str.strip('[]').split(',')
                yes_price = float(parts[0].strip().strip('"\''))
            except:
                pass

        closed = m.get('closed', False)
        status = "[CLOSED]" if closed else "[ACTIVE]"

        print(f"\n{status} {q}")
        print(f"  YES: {yes_price:.2%} | Slug: {m.get('slug', '')[:40]}...")
        print(f"  Volume: ${float(m.get('volume', 0) or 0):,.0f}")

    # 特别搜索Up or Down市场
    print("\n[4] Up or Down市场详情:")
    print("-" * 70)

    updown_markets = [m for m in btc_price_markets
                      if 'up or down' in m.get('question', '').lower()
                      or 'up/down' in m.get('question', '').lower()]

    for m in updown_markets:
        print(f"\n  Q: {m.get('question', '')}")
        print(f"  Slug: {m.get('slug', '')}")
        print(f"  Outcomes: {m.get('outcomes', [])}")
        print(f"  Description: {m.get('description', '')[:150]}...")

    # 保存结果
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_searched': len(all_markets),
        'btc_price_markets': len(btc_price_markets),
        'markets': [
            {
                'question': m.get('question', ''),
                'slug': m.get('slug', ''),
                'yes_price': float(m.get('outcomePrices', '["0.5"]').strip('[]').split(',')[0].strip().strip('"\'') or 0.5),
                'volume': float(m.get('volume', 0) or 0),
                'closed': m.get('closed', False),
                'outcomes': m.get('outcomes', []),
                'description': m.get('description', '')[:200]
            }
            for m in btc_price_markets
        ]
    }

    with open('output/btc_price_search.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to output/btc_price_search.json")

if __name__ == "__main__":
    search_markets()
