"""
测试已知假阳性案例的修复

Gold 市场假阳性案例：
- Market A: "Will Gold (GC) settle at $4,725-$4,850 in January?" (YES = 92%)
- Market B: "Will Gold (GC) settle over $7,000 on the final trading day of January 2026?" (YES = 0.6%)
- LLM reasoning 说 MUTUAL_EXCLUSIVE，但 relationship 是 IMPLIES_AB

预期结果：应该被验证层拒绝，不生成套利机会
"""

import sys
from local_scanner_v2 import LLMAnalyzer, Market, RelationType
from config import Config as AppConfig


def test_llm_consistency_check():
    """测试 LLM 输出一致性检查功能"""
    print("\n" + "="*60)
    print("测试 1: LLM 输出一致性检查")
    print("="*60)

    try:
        config = AppConfig()
        analyzer = LLMAnalyzer(config)

        # 矛盾案例：reasoning 说互斥，但 relationship 是 IMPLIES
        contradictory_result = {
            'relationship': 'IMPLIES_AB',
            'reasoning': 'These markets are mutually exclusive events',
            'confidence': 0.98
        }

        is_valid, msg = analyzer._validate_llm_response_consistency(contradictory_result)

        if not is_valid:
            print(f"✅ 测试通过: 成功检测到矛盾")
            print(f"   错误信息: {msg}")
        else:
            print(f"❌ 测试失败: 应该检测到矛盾但没有")
            return False

        # 测试中文矛盾关键词
        chinese_result = {
            'relationship': 'IMPLIES_AB',
            'reasoning': '这两个市场是互斥的，不可能同时发生',
            'confidence': 0.95
        }

        is_valid, msg = analyzer._validate_llm_response_consistency(chinese_result)

        if not is_valid:
            print(f"✅ 中文关键词测试通过: {msg}")
        else:
            print(f"❌ 中文关键词测试失败")
            return False

        # 测试正常案例
        normal_result = {
            'relationship': 'IMPLIES_AB',
            'reasoning': 'If Trump wins, then GOP wins because Trump is GOP candidate',
            'confidence': 0.95
        }

        is_valid, msg = analyzer._validate_llm_response_consistency(normal_result)

        if is_valid:
            print(f"✅ 正常案例测试通过: 无矛盾")
        else:
            print(f"❌ 正常案例测试失败: 误报为矛盾")
            return False

        return True

    except Exception as e:
        print(f"❌ 测试失败，异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gold_market_false_positive():
    """
    测试案例：Gold 市场假阳性

    问题描述：
    - Market A: Gold $4,725-$4,850 (YES = 92%)
    - Market B: Gold over $7,000 (YES = 0.6%)
    - LLM reasoning 说 MUTUAL_EXCLUSIVE，但 relationship 是 IMPLIES_AB

    预期结果：应该被拒绝，不生成套利机会
    """
    print("\n" + "="*60)
    print("测试 2: Gold 市场假阳性案例")
    print("="*60)

    try:
        # 创建测试市场（模拟真实数据）
        market_a = Market(
            id="1032227",
            condition_id="cond_a",
            question="Will Gold (GC) settle at $4,725-$4,850 in January?",
            description="Gold price range prediction",
            yes_price=0.92,
            no_price=0.08,
            volume=100000,
            liquidity=50000,
            end_date="2026-01-31",
            event_id="gold_jan_2026",
            event_title="Gold January 2026",
            resolution_source="CME",
            outcomes=["Yes", "No"],
            token_id="",
            best_bid=0.0,
            best_ask=0.0,
            spread=0.0
        )

        market_b = Market(
            id="1032243",
            condition_id="cond_b",
            question="Will Gold (GC) settle over $7,000 on the final trading day of January 2026?",
            description="Gold price target prediction",
            yes_price=0.006,
            no_price=0.994,
            volume=100000,
            liquidity=50000,
            end_date="2026-01-31",
            event_id="gold_jan_2026",
            event_title="Gold January 2026",
            resolution_source="CME",
            outcomes=["Yes", "No"],
            token_id="",
            best_bid=0.0,
            best_ask=0.0,
            spread=0.0
        )

        print(f"市场 A: {market_a.question}")
        print(f"  YES 价格: {market_a.yes_price:.1%}")
        print(f"市场 B: {market_b.question}")
        print(f"  YES 价格: {market_b.yes_price:.1%}")

        # 模拟 LLM 分析结果（矛盾输出）
        llm_analysis = {
            'relationship': 'IMPLIES_AB',  # ❌ 错误分类
            'confidence': 0.98,
            'reasoning': '经过重新分析，市场A和市场B描述的是两个在价格上完全不重叠的事件。'
                        '由于$4,850 < $7,000，两个事件不可能同时为真。'
                        '因此，它们是互斥的（MUTUAL_EXCLUSIVE），而不是蕴含关系。',  # ✓ 正确推理
            'is_consistent': True,  # 假设未通过一致性检查
            'edge_cases': [],
            'needs_review': []
        }

        print(f"\n模拟 LLM 分析结果:")
        print(f"  relationship: {llm_analysis['relationship']}")
        print(f"  confidence: {llm_analysis['confidence']}")
        print(f"  reasoning 片段: {llm_analysis['reasoning'][:100]}...")

        # 验证一致性检查
        config = AppConfig()
        analyzer = LLMAnalyzer(config)

        is_valid, msg = analyzer._validate_llm_response_consistency(llm_analysis)

        if not is_valid:
            print(f"\n✅ 一致性检查成功检测到矛盾:")
            print(f"   {msg}")
            print(f"\n✅ 测试通过: 假阳性被正确拒绝")
            return True
        else:
            print(f"\n❌ 测试失败: 一致性检查未检测到矛盾")
            print(f"   预期: 应该检测到 reasoning 和 relationship 的矛盾")
            print(f"   实际: 未检测到矛盾")
            return False

    except Exception as e:
        print(f"❌ 测试失败，异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "="*70)
    print(" " * 15 + "假阳性修复测试套件")
    print("="*70)

    results = []

    # 测试 1: LLM 一致性检查
    results.append(("LLM 一致性检查", test_llm_consistency_check()))

    # 测试 2: Gold 市场假阳性
    results.append(("Gold 市场假阳性", test_gold_market_false_positive()))

    # 总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！Priority 1 修复验证成功。")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，需要修复。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
