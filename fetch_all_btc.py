#!/usr/bin/env python3
"""
获取所有Bitcoin相关市场的完整数据
"""

import requests
import json
from datetime import datetime

def fetch_all_bitcoin_markets():
    """获取所有Bitcoin市场"""

    base_url = "https://gamma-api.polymarket.com"
    session = requests.Session()
    session.headers.update({"User-Agent": "BTCScanner/1.0"})

    # 获取大量市场
    print("Fetching markets from Polymarket API...")

    all_btc_markets = []

    # 方法1: 获取活跃市场
    for limit in [500]:
        url = f"{base_url}/markets"
        params = {
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume",
            "ascending": "false"
        }

        try:
            response = session.get(url, params=params, timeout=30)
            markets = response.json()
            print(f"Got {len(markets)} active markets")

            for m in markets:
                q = m.get('question', '').lower()
                if 'bitcoin' in q or 'btc' in q:
                    all_btc_markets.append(m)
        except Exception as e:
            print(f"Error: {e}")

    # 方法2: 尝试获取已关闭的市场
    try:
        url = f"{base_url}/markets"
        params = {
            "limit": 500,
            "closed": "true",
            "order": "volume",
            "ascending": "false"
        }
        response = session.get(url, params=params, timeout=30)
        closed_markets = response.json()
        print(f"Got {len(closed_markets)} closed markets")

        for m in closed_markets:
            q = m.get('question', '').lower()
            if 'bitcoin' in q or 'btc' in q:
                if m not in all_btc_markets:
                    all_btc_markets.append(m)
    except Exception as e:
        print(f"Error fetching closed: {e}")

    print(f"\nTotal Bitcoin markets found: {len(all_btc_markets)}")

    # 按日期和类型分组
    jan3_markets = []
    other_jan_markets = []
    other_markets = []

    for m in all_btc_markets:
        q = m.get('question', '').lower()

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
            'slug': m.get('slug', ''),
            'closed': m.get('closed', False),
            'end_date': m.get('endDate', ''),
            'outcomes': m.get('outcomes', []),
            'description': m.get('description', '')[:200]
        }

        if 'january 3' in q or 'jan 3' in q or 'jan3' in q:
            jan3_markets.append(market_info)
        elif 'january' in q or 'jan' in q:
            other_jan_markets.append(market_info)
        else:
            other_markets.append(market_info)

    # 打印January 3市场
    print("\n" + "="*70)
    print("JANUARY 3 BITCOIN MARKETS")
    print("="*70)

    for i, m in enumerate(jan3_markets, 1):
        print(f"\n[{i}] {m['question']}")
        print(f"    YES: {m['yes_price']:.2%} | NO: {m['no_price']:.2%}")
        print(f"    Volume: ${m['volume']:,.0f} | Liquidity: ${m['liquidity']:,.0f}")
        print(f"    Closed: {m['closed']} | End: {m['end_date'][:10] if m['end_date'] else 'N/A'}")
        if m['outcomes']:
            print(f"    Outcomes: {m['outcomes']}")

    # 打印其他January市场
    print("\n" + "="*70)
    print("OTHER JANUARY BITCOIN MARKETS")
    print("="*70)

    for i, m in enumerate(other_jan_markets[:20], 1):  # 最多20个
        print(f"\n[{i}] {m['question']}")
        print(f"    YES: {m['yes_price']:.2%} | NO: {m['no_price']:.2%}")
        print(f"    Volume: ${m['volume']:,.0f} | Closed: {m['closed']}")

    # 保存完整数据
    output = {
        'timestamp': datetime.now().isoformat(),
        'jan3_markets': jan3_markets,
        'other_jan_markets': other_jan_markets,
        'total_btc_markets': len(all_btc_markets)
    }

    with open('output/all_btc_markets.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to output/all_btc_markets.json")

    return output

if __name__ == "__main__":
    fetch_all_bitcoin_markets()
