#!/usr/bin/env python3
"""
P2.2 真实数据连接测试脚本

测试 Polymarket Gamma API 连接和数据解析
"""

import requests
import json
import time
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

# 导入现有模块
from local_scanner_v2 import PolymarketClient, Market


def print_separator(title: str):
    """打印分隔线"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def test_step1_connection() -> bool:
    """Step 1: 基础连接测试"""
    print_separator("Step 1: 基础连接测试")

    api_base = "https://gamma-api.polymarket.com"

    try:
        start_time = time.time()
        response = requests.get(f"{api_base}/markets", params={"limit": 1}, timeout=30)
        latency = (time.time() - start_time) * 1000

        print(f"API地址: {api_base}")
        print(f"状态码: {response.status_code}")
        print(f"响应延迟: {latency:.0f}ms")

        if response.status_code == 200:
            print("结果: API连接成功")
            return True
        else:
            print(f"结果: API返回非200状态码")
            return False

    except requests.exceptions.Timeout:
        print("结果: 连接超时")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"结果: 连接失败 - {e}")
        return False
    except Exception as e:
        print(f"结果: 未知错误 - {e}")
        return False


def test_step2_data_fetch() -> List[Dict]:
    """Step 2: 数据获取测试"""
    print_separator("Step 2: 数据获取测试")

    client = PolymarketClient()

    # 获取少量市场数据
    print("正在获取10个市场数据...")
    markets = client.get_markets(limit=10, active=True, min_liquidity=0)

    print(f"获取到市场数量: {len(markets)}")

    if markets:
        print("\n样本市场数据:")
        m = markets[0]
        print(f"  ID: {m.id[:20]}...")
        print(f"  问题: {m.question[:60]}...")
        print(f"  YES价格: ${m.yes_price:.4f}")
        print(f"  NO价格: ${m.no_price:.4f}")
        print(f"  交易量: ${m.volume:,.0f}")
        print(f"  流动性: ${m.liquidity:,.0f}")
        print(f"  事件ID: {m.event_id[:40] if m.event_id else 'N/A'}...")
        print(f"  结算日期: {m.end_date}")
        print(f"  结算来源: {m.resolution_source}")
        print(f"  结果选项: {m.outcomes}")

    return markets


def test_step3_data_validation(markets: List[Market]) -> Dict[str, Any]:
    """Step 3: 数据解析验证"""
    print_separator("Step 3: 数据解析验证")

    if not markets:
        print("无数据可验证")
        return {}

    validation_results = {
        "total": len(markets),
        "price_valid": 0,
        "volume_valid": 0,
        "liquidity_valid": 0,
        "event_id_present": 0,
        "outcomes_valid": 0,
        "issues": []
    }

    for m in markets:
        # 验证价格范围
        if 0 <= m.yes_price <= 1 and 0 <= m.no_price <= 1:
            validation_results["price_valid"] += 1
        else:
            validation_results["issues"].append(f"价格异常: {m.id} - YES={m.yes_price}, NO={m.no_price}")

        # 验证交易量
        if m.volume >= 0:
            validation_results["volume_valid"] += 1
        else:
            validation_results["issues"].append(f"交易量异常: {m.id} - volume={m.volume}")

        # 验证流动性
        if m.liquidity >= 0:
            validation_results["liquidity_valid"] += 1
        else:
            validation_results["issues"].append(f"流动性异常: {m.id} - liquidity={m.liquidity}")

        # 验证event_id
        if m.event_id:
            validation_results["event_id_present"] += 1

        # 验证outcomes
        if isinstance(m.outcomes, list) and len(m.outcomes) >= 2:
            validation_results["outcomes_valid"] += 1
        else:
            validation_results["issues"].append(f"outcomes异常: {m.id} - outcomes={m.outcomes}")

    # 打印验证结果
    total = validation_results["total"]
    print(f"验证市场数: {total}")
    print(f"价格有效率: {validation_results['price_valid']}/{total} ({100*validation_results['price_valid']/total:.0f}%)")
    print(f"交易量有效率: {validation_results['volume_valid']}/{total} ({100*validation_results['volume_valid']/total:.0f}%)")
    print(f"流动性有效率: {validation_results['liquidity_valid']}/{total} ({100*validation_results['liquidity_valid']/total:.0f}%)")
    print(f"事件ID存在率: {validation_results['event_id_present']}/{total} ({100*validation_results['event_id_present']/total:.0f}%)")
    print(f"outcomes有效率: {validation_results['outcomes_valid']}/{total} ({100*validation_results['outcomes_valid']/total:.0f}%)")

    if validation_results["issues"]:
        print(f"\n发现问题 ({len(validation_results['issues'])}个):")
        for issue in validation_results["issues"][:5]:
            print(f"  - {issue}")
        if len(validation_results["issues"]) > 5:
            print(f"  ... 还有 {len(validation_results['issues'])-5} 个问题")
    else:
        print("\n所有数据验证通过!")

    return validation_results


def test_step4_edge_cases():
    """Step 4: 边界情况测试"""
    print_separator("Step 4: 边界情况测试")

    client = PolymarketClient()

    # 测试1: min_liquidity过滤
    print("\n测试1: 流动性过滤")
    markets_all = client.get_markets(limit=100, min_liquidity=0)
    markets_10k = client.get_markets(limit=100, min_liquidity=10000)
    markets_100k = client.get_markets(limit=100, min_liquidity=100000)

    print(f"  min_liquidity=0: {len(markets_all)} 个市场")
    print(f"  min_liquidity=10,000: {len(markets_10k)} 个市场")
    print(f"  min_liquidity=100,000: {len(markets_100k)} 个市场")

    # 测试2: 大批量获取
    print("\n测试2: 大批量获取")
    start = time.time()
    markets_200 = client.get_markets(limit=200, min_liquidity=0)
    elapsed = time.time() - start
    print(f"  获取200个市场: {len(markets_200)} 个, 耗时 {elapsed:.2f}s")

    # 测试3: 验证流动性过滤正确性
    print("\n测试3: 验证过滤正确性")
    if markets_10k:
        min_liq = min(m.liquidity for m in markets_10k)
        max_liq = max(m.liquidity for m in markets_10k)
        print(f"  min_liquidity=10,000 过滤后:")
        print(f"    最低流动性: ${min_liq:,.0f}")
        print(f"    最高流动性: ${max_liq:,.0f}")
        if min_liq >= 10000:
            print("    过滤正确!")
        else:
            print(f"    警告: 存在低于阈值的市场 (${min_liq:,.0f})")

    return markets_200


def test_step5_quality_report(markets: List[Market]):
    """Step 5: 数据质量报告"""
    print_separator("Step 5: 数据质量报告")

    if not markets:
        print("无数据可分析")
        return

    # 1. 基础统计
    print("\n1. 基础统计")
    print(f"  总市场数: {len(markets)}")

    total_volume = sum(m.volume for m in markets)
    total_liquidity = sum(m.liquidity for m in markets)
    print(f"  总交易量: ${total_volume:,.0f}")
    print(f"  总流动性: ${total_liquidity:,.0f}")

    # 2. 价格分布
    print("\n2. 价格分布")
    price_ranges = {
        "极低 (0-0.1)": 0,
        "低 (0.1-0.3)": 0,
        "中 (0.3-0.7)": 0,
        "高 (0.7-0.9)": 0,
        "极高 (0.9-1.0)": 0
    }
    for m in markets:
        p = m.yes_price
        if p < 0.1:
            price_ranges["极低 (0-0.1)"] += 1
        elif p < 0.3:
            price_ranges["低 (0.1-0.3)"] += 1
        elif p < 0.7:
            price_ranges["中 (0.3-0.7)"] += 1
        elif p < 0.9:
            price_ranges["高 (0.7-0.9)"] += 1
        else:
            price_ranges["极高 (0.9-1.0)"] += 1

    for range_name, count in price_ranges.items():
        print(f"  {range_name}: {count} ({100*count/len(markets):.0f}%)")

    # 3. 事件分组统计（完备集候选）
    print("\n3. 事件分组统计 (完备集候选)")
    event_groups = defaultdict(list)
    for m in markets:
        if m.event_id:
            event_groups[m.event_id].append(m)

    # 找出有多个市场的事件（潜在完备集）
    multi_market_events = [(eid, mlist) for eid, mlist in event_groups.items() if len(mlist) >= 2]
    multi_market_events.sort(key=lambda x: len(x[1]), reverse=True)

    print(f"  有event_id的市场: {sum(len(m) for m in event_groups.values())}")
    print(f"  独立事件数: {len(event_groups)}")
    print(f"  多市场事件数: {len(multi_market_events)}")

    if multi_market_events:
        print("\n  Top 5 多市场事件 (完备集候选):")
        for eid, mlist in multi_market_events[:5]:
            total_yes = sum(m.yes_price for m in mlist)
            print(f"    - {eid[:50]}...")
            print(f"      市场数: {len(mlist)}, YES价格总和: ${total_yes:.3f}")
            if total_yes < 0.98:
                print(f"      潜在套利机会! (总和 < 0.98)")

    # 4. 高流动性市场
    print("\n4. 高流动性市场 Top 5")
    sorted_by_liq = sorted(markets, key=lambda m: m.liquidity, reverse=True)
    for i, m in enumerate(sorted_by_liq[:5], 1):
        print(f"  {i}. {m.question[:50]}...")
        print(f"     流动性: ${m.liquidity:,.0f}, YES价格: ${m.yes_price:.3f}")

    # 5. 字段完整性
    print("\n5. 字段完整性统计")
    fields = {
        "id": sum(1 for m in markets if m.id),
        "question": sum(1 for m in markets if m.question),
        "description": sum(1 for m in markets if m.description),
        "event_id": sum(1 for m in markets if m.event_id),
        "event_title": sum(1 for m in markets if m.event_title),
        "end_date": sum(1 for m in markets if m.end_date),
        "resolution_source": sum(1 for m in markets if m.resolution_source),
    }
    for field, count in fields.items():
        pct = 100 * count / len(markets)
        status = "" if pct == 100 else " (部分缺失)"
        print(f"  {field}: {count}/{len(markets)} ({pct:.0f}%){status}")


def main():
    """主测试流程"""
    print("\n" + "="*60)
    print("  P2.2 真实数据连接测试")
    print("  Polymarket Gamma API 测试脚本")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    results = {
        "step1_connection": False,
        "step2_fetch": False,
        "step3_validation": False,
        "step4_edge_cases": False,
        "step5_report": False
    }

    # Step 1: 基础连接测试
    results["step1_connection"] = test_step1_connection()
    if not results["step1_connection"]:
        print("\n连接失败，无法继续测试。请检查网络连接。")
        return results

    # Step 2: 数据获取测试
    markets = test_step2_data_fetch()
    results["step2_fetch"] = len(markets) > 0

    if not results["step2_fetch"]:
        print("\n数据获取失败，无法继续测试。")
        return results

    # Step 3: 数据解析验证
    validation = test_step3_data_validation(markets)
    results["step3_validation"] = validation.get("price_valid", 0) == len(markets)

    # Step 4: 边界情况测试
    markets_full = test_step4_edge_cases()
    results["step4_edge_cases"] = len(markets_full) >= 100

    # Step 5: 数据质量报告
    test_step5_quality_report(markets_full)
    results["step5_report"] = True

    # 总结
    print_separator("测试总结")
    all_passed = all(results.values())

    for step, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {step}: {status}")

    print(f"\n总体结果: {'ALL PASSED' if all_passed else 'SOME FAILED'}")

    if all_passed:
        print("\nP2.2 真实数据连接测试通过!")
        print("可以继续进行 P2.3 批量市场分析流程")

    return results


if __name__ == "__main__":
    main()
