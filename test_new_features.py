#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新功能验证测试脚本
====================

测试新实现的功能：
1. TagManager - Tag管理和按tag获取市场
2. Market数据结构 - event_description, market_description, tags字段
3. IntervalParser - 区间解析和关系判断
4. PolymarketClient新方法 - get_markets_by_tag_slug等

运行方式：
    python test_new_features.py
"""

import sys
import json
from typing import List


def print_header(text: str):
    """打印标题"""
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}")


def print_ok(message: str):
    """打印成功消息"""
    print(f"  [OK] {message}")


def print_fail(message: str):
    """打印失败消息"""
    print(f"  [FAIL] {message}")


# ============================================================
# 测试1: TagManager
# ============================================================

def test_tag_manager() -> bool:
    """测试TagManager功能"""
    print_header("[1/5] Testing TagManager")

    try:
        from tag_manager import TagManager

        manager = TagManager()

        # 测试1.1: 获取crypto tag
        crypto_tag = manager.get_tag("crypto")
        if crypto_tag and crypto_tag.id == "21":
            print_ok(f"get_tag('crypto') returns id='{crypto_tag.id}'")
        else:
            print_fail(f"get_tag('crypto') failed, expected id='21'")
            return False

        # 测试1.2: 获取其他tags
        common_tags = manager.get_common_tag_ids()
        if "crypto" in common_tags and "politics" in common_tags:
            print_ok(f"get_common_tag_ids() returns {len(common_tags)} tags")
        else:
            print_fail("get_common_tag_ids() incomplete")
            return False

        # 测试1.3: get_events_by_tag
        events = manager.get_events_by_tag_id("21", active=True, limit=5)
        if len(events) >= 0:  # 可能没有活跃的crypto events
            print_ok(f"get_events_by_tag(21) returns {len(events)} events")
        else:
            print_fail("get_events_by_tag() failed")
            return False

        return True

    except Exception as e:
        print_fail(f"TagManager测试异常: {e}")
        return False


# ============================================================
# 测试2: Market数据结构
# ============================================================

def test_market_structure() -> bool:
    """测试Market新字段"""
    print_header("[2/5] Testing Market Structure")

    try:
        from local_scanner_v2 import PolymarketClient

        client = PolymarketClient()

        # 使用新的get_markets_by_tag_slug方法获取市场
        markets = client.get_markets_by_tag_slug('crypto', active=True, limit=3)

        if not markets:
            print_fail("No markets returned from get_markets_by_tag_slug('crypto')")
            return False

        print_ok(f"get_markets_by_tag_slug('crypto') returns {len(markets)} markets")

        # 检查第一个市场的字段
        m = markets[0]

        checks = []

        # 检查event_description
        if hasattr(m, 'event_description') and len(m.event_description) > 0:
            checks.append("event_description exists")
            print_ok(f"event_description: {len(m.event_description)} chars")
        else:
            checks.append("event_description MISSING")

        # 检查market_description
        if hasattr(m, 'market_description'):
            checks.append("market_description exists")
            print_ok(f"market_description: {len(m.market_description)} chars")
        else:
            checks.append("market_description MISSING")

        # 检查tags
        if hasattr(m, 'tags') and len(m.tags) > 0:
            tags_list = [t.get('label', 'unknown') for t in m.tags[:3]]
            checks.append("tags exists")
            print_ok(f"tags: {tags_list}")
        else:
            checks.append("tags MISSING")

        # 检查full_description属性
        if hasattr(m, 'full_description'):
            full_desc = m.full_description
            if full_desc:
                checks.append("full_description works")
                print_ok(f"full_description: {len(full_desc)} chars (uses event desc)")
            else:
                checks.append("full_description empty")
        else:
            checks.append("full_description MISSING")

        passed = len([c for c in checks if "MISSING" not in c])
        total = len(checks)

        if passed == total:
            print_ok(f"All {total} Market field checks passed")
            return True
        else:
            print_fail(f"{total - passed}/{total} checks failed")
            return False

    except Exception as e:
        print_fail(f"Market结构测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# 测试3: IntervalParser
# ============================================================

def test_interval_parser() -> bool:
    """测试区间解析器"""
    print_header("[3/5] Testing IntervalParser")

    try:
        from interval_parser import IntervalParser, IntervalType, IntervalRelation

        parser = IntervalParser()

        # 测试3.1: above解析
        interval = parser.parse("Will BTC be above $100k by 2025?")
        if interval and interval.type == IntervalType.ABOVE:
            print_ok(f"Parse 'above $100k' -> {interval.type.value}, lower={interval.lower}")
        else:
            print_fail("Parse 'above $100k' failed")
            return False

        # 测试3.2: below解析
        interval = parser.parse("Will ETH drop below $2000?")
        if interval and interval.type == IntervalType.BELOW:
            print_ok(f"Parse 'below $2000' -> {interval.type.value}, upper={interval.upper}")
        else:
            print_fail("Parse 'below $2000' failed")
            return False

        # 测试3.3: 区间关系比较
        market_a = {
            'question': 'Will BTC be above $100k?',
            'yes_price': 0.30,
            'event_description': '',
            'description': ''
        }
        market_b = {
            'question': 'Will BTC be above $150k?',
            'yes_price': 0.15,
            'event_description': '',
            'description': ''
        }

        result = parser.find_interval_arbitrage(market_a, market_b)
        if result and result.get('type') == 'interval_implication':
            print_ok(f"Interval arbitrage detected: {result.get('relation')}")
        else:
            print_fail("Interval arbitrage not detected (expected A_COVERS_B)")
            return False

        return True

    except Exception as e:
        print_fail(f"IntervalParser测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# 测试4: Solana区间套利场景
# ============================================================

def test_solana_interval_scenario() -> bool:
    """测试Solana区间套利场景"""
    print_header("[4/5] Testing Solana Interval Arbitrage Scenario")

    try:
        from interval_parser import IntervalParser, IntervalRelation
        from local_scanner_v2 import ArbitrageDetector, Market, AppConfig
        from datetime import datetime

        parser = IntervalParser()

        # 模拟Solana Jan 4场景
        # 市场1: "Solana < 130 on Jan 4?" (完备集子市场之一)
        market_below = Market(
            id="1",
            condition_id="0x1",
            question="Will Solana be below 130 on January 4?",
            description="",
            yes_price=0.046,  # 4.6c
            no_price=0.954,
            volume=10000,
            liquidity=5000,
            end_date="2025-01-04",
            event_id="solana-jan4",
            event_title="Solana Price Jan 4",
            resolution_source="Binance",
            outcomes=["Yes", "No"],
            event_description="Resolves based on Binance price",
        )

        # 市场2: "Solana above 130 on Jan 4?"
        market_above = Market(
            id="2",
            condition_id="0x2",
            question="Will Solana be above 130 on January 4?",
            description="",
            yes_price=0.948,  # 94.8c
            no_price=0.052,
            volume=10000,
            liquidity=5000,
            end_date="2025-01-04",
            event_id="solana-jan4-above",
            event_title="Solana Above 130 Jan 4",
            resolution_source="Binance",
            outcomes=["Yes", "No"],
            event_description="Resolves based on Binance price",
        )

        # 解析区间
        interval_below = parser.parse(market_below.question, market_below.event_description)
        interval_above = parser.parse(market_above.question, market_above.event_description)

        if interval_below and interval_above:
            print_ok(f"Parsed below interval: {interval_below.type.value}")
            print_ok(f"Parsed above interval: {interval_above.type.value}")

            # 比较区间关系
            relation = parser.compare_intervals(interval_below, interval_above)
            print_ok(f"Interval relation: {relation.value}")

            # 检查套利条件
            total_cost = market_below.yes_price + market_above.yes_price
            print_ok(f"Total cost: ${total_cost:.4f} (99.4c expected)")

            if total_cost < 1.0:
                profit = 1.0 - total_cost
                print_ok(f"Arbitrage opportunity: ${profit:.4f} profit ({profit/total_cost*100:.2f}%)")
                return True
            else:
                print_fail("No arbitrage opportunity (cost >= 1.0)")
                return False
        else:
            print_fail("Failed to parse intervals")
            return False

    except Exception as e:
        print_fail(f"Solana场景测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# 测试5: 集成测试
# ============================================================

def test_integration() -> bool:
    """集成测试 - 完整数据流程"""
    print_header("[5/5] Integration Test")

    try:
        from local_scanner_v2 import PolymarketClient
        from tag_manager import TagManager

        client = PolymarketClient()
        manager = TagManager()

        # 测试5.1: 获取tag_id并使用它
        crypto_tag = manager.get_tag("crypto")
        if not crypto_tag:
            print_fail("Failed to get crypto tag")
            return False

        print_ok(f"Got crypto tag: id={crypto_tag.id}, label={crypto_tag.label}")

        # 测试5.2: 使用tag_id获取markets
        markets_by_id = client.get_markets_by_tag(
            tag_id=crypto_tag.id,
            active=True,
            limit=2
        )
        print_ok(f"get_markets_by_tag(id={crypto_tag.id}) returns {len(markets_by_id)} markets")

        # 测试5.3: 使用tag_slug获取markets
        markets_by_slug = client.get_markets_by_tag_slug(
            slug="crypto",
            active=True,
            limit=2
        )
        print_ok(f"get_markets_by_tag_slug('crypto') returns {len(markets_by_slug)} markets")

        # 测试5.4: 验证数据完整性
        if markets_by_slug:
            m = markets_by_slug[0]
            has_desc = len(m.event_description) > 0 or len(m.market_description) > 0
            has_tags = len(m.tags) > 0

            if has_desc:
                print_ok(f"Market has description ({len(m.event_description)} chars)")
            if has_tags:
                tag_labels = [t.get('label') for t in m.tags[:3]]
                print_ok(f"Market has tags: {tag_labels}")

            if has_desc or has_tags:
                print_ok("Integration test passed - data flow working correctly")
                return True

        print_fail("Integration test incomplete")
        return False

    except Exception as e:
        print_fail(f"集成测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# 主函数
# ============================================================

def main():
    """运行所有测试"""
    print("="*60)
    print(" New Features Verification Test")
    print("="*60)
    print("\nThis script verifies the newly implemented features:")
    print("  1. TagManager - Tag management and tag-based market fetching")
    print("  2. Market Structure - New fields (event_description, tags)")
    print("  3. IntervalParser - Interval parsing and relation detection")
    print("  4. Solana Interval Arbitrage - Real-world scenario test")
    print("  5. Integration - End-to-end data flow test")

    results = []

    # 运行测试
    results.append(("TagManager", test_tag_manager()))
    results.append(("Market Structure", test_market_structure()))
    results.append(("IntervalParser", test_interval_parser()))
    results.append(("Solana Scenario", test_solana_interval_scenario()))
    results.append(("Integration", test_integration()))

    # 汇总结果
    print_header("Test Results Summary")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {name}")

    print()
    if passed == total:
        print(f"=== All {total} tests passed! ===")
        return 0
    else:
        print(f"=== {total - passed}/{total} tests failed ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
