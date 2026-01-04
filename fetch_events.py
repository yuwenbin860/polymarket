#!/usr/bin/env python3
"""
通过Events API获取更完整的市场数据
"""

import requests
import json
from datetime import datetime

def fetch_bitcoin_events():
    """获取Bitcoin相关Events"""

    base_url = "https://gamma-api.polymarket.com"
    session = requests.Session()
    session.headers.update({"User-Agent": "BTCScanner/1.0"})

    print("Fetching events from Polymarket API...")

    # 获取Events
    all_events = []

    try:
        url = f"{base_url}/events"
        params = {
            "limit": 300,
            "active": "true",
        }
        response = session.get(url, params=params, timeout=30)
        active_events = response.json()
        print(f"Got {len(active_events)} active events")
        all_events.extend(active_events)
    except Exception as e:
        print(f"Error: {e}")

    # 获取已关闭的Events
    try:
        url = f"{base_url}/events"
        params = {
            "limit": 300,
            "closed": "true",
        }
        response = session.get(url, params=params, timeout=30)
        closed_events = response.json()
        print(f"Got {len(closed_events)} closed events")
        all_events.extend(closed_events)
    except Exception as e:
        print(f"Error: {e}")

    # 过滤Bitcoin相关Events
    btc_events = []
    for e in all_events:
        title = (e.get('title', '') or '').lower()
        desc = (e.get('description', '') or '').lower()
        if 'bitcoin' in title or 'btc' in title or 'bitcoin' in desc:
            btc_events.append(e)

    print(f"\nTotal Bitcoin events: {len(btc_events)}")

    # 详细打印
    print("\n" + "="*70)
    print("BITCOIN EVENTS WITH MARKETS")
    print("="*70)

    jan3_related = []

    for i, event in enumerate(btc_events, 1):
        title = event.get('title', 'N/A')
        slug = event.get('slug', '')
        markets = event.get('markets', [])

        print(f"\n[Event {i}] {title}")
        print(f"    Slug: {slug}")
        print(f"    Markets count: {len(markets)}")

        # 检查是否January 3相关
        if 'january 3' in title.lower() or 'jan 3' in title.lower():
            jan3_related.append(event)
            print("    *** JANUARY 3 RELATED ***")

        if markets:
            for j, m in enumerate(markets[:10], 1):  # 最多显示10个market
                q = m.get('question', 'N/A')

                # 解析价格
                prices_str = m.get('outcomePrices', '')
                yes_price = 0.5
                if prices_str:
                    try:
                        parts = prices_str.strip('[]').split(',')
                        yes_price = float(parts[0].strip().strip('"\''))
                    except:
                        pass

                outcomes = m.get('outcomes', [])
                print(f"      [{j}] {q[:65]}...")
                print(f"          YES: {yes_price:.2%} | Outcomes: {outcomes}")

                # 检查January 3
                if 'january 3' in q.lower() or 'jan 3' in q.lower():
                    jan3_related.append({'event': title, 'market': m})

    # 专门打印January 3相关
    print("\n" + "="*70)
    print("JANUARY 3 SPECIFIC ITEMS")
    print("="*70)

    for item in jan3_related:
        if isinstance(item, dict) and 'market' in item:
            m = item['market']
            print(f"\nEvent: {item['event']}")
            print(f"Market: {m.get('question', 'N/A')}")
        else:
            print(f"\nEvent: {item.get('title', 'N/A')}")

    # 保存完整数据
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_btc_events': len(btc_events),
        'events': btc_events
    }

    with open('output/btc_events.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to output/btc_events.json")

    return btc_events

if __name__ == "__main__":
    fetch_bitcoin_events()
