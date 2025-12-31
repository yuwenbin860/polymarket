#!/usr/bin/env python3
"""
Prompt测试脚本
==============

用于测试和验证新版Prompt的效果。

使用方法:
    python test_prompts.py --profile deepseek
    python test_prompts.py --profile siliconflow --model Qwen/Qwen2.5-72B-Instruct
"""

import json
import argparse
from dataclasses import asdict

from prompts import format_analysis_prompt, format_exhaustive_prompt, PromptConfig
from llm_providers import create_llm_client


# ============================================================
# 测试用例
# ============================================================

TEST_CASES = [
    {
        "name": "包含关系: 候选人 -> 政党",
        "market_a": {
            "question": "Will Donald Trump win the 2024 presidential election?",
            "description": "This market resolves YES if Donald Trump wins the 2024 US Presidential Election.",
            "yes_price": 0.55,
            "end_date": "2024-11-06",
            "event_id": "2024-presidential-election",
            "resolution_source": "Associated Press"
        },
        "market_b": {
            "question": "Will the Republican Party win the 2024 presidential election?",
            "description": "This market resolves YES if the Republican candidate wins the 2024 US Presidential Election.",
            "yes_price": 0.52,  # 违反约束：应该 >= 0.55
            "end_date": "2024-11-06",
            "event_id": "2024-presidential-election",
            "resolution_source": "Associated Press"
        },
        "expected_relationship": "IMPLIES_AB",
        "expected_constraint_violated": True,
        "description": "Trump赢 → 共和党赢，但 P(共和党)=0.52 < P(Trump)=0.55，违反约束"
    },
    {
        "name": "包含关系: 夺冠 -> 季后赛",
        "market_a": {
            "question": "Will the Los Angeles Lakers win the 2025 NBA Championship?",
            "description": "Resolves YES if the Lakers win the 2024-25 NBA Finals.",
            "yes_price": 0.08,
            "end_date": "2025-06-30",
            "event_id": "nba-2025-championship",
            "resolution_source": "NBA.com"
        },
        "market_b": {
            "question": "Will the Los Angeles Lakers make the 2025 NBA Playoffs?",
            "description": "Resolves YES if the Lakers qualify for the 2024-25 NBA Playoffs.",
            "yes_price": 0.65,
            "end_date": "2025-04-15",
            "event_id": "nba-2025-playoffs",
            "resolution_source": "NBA.com"
        },
        "expected_relationship": "IMPLIES_AB",
        "expected_constraint_violated": False,
        "description": "夺冠 → 进季后赛，P(季后赛)=0.65 > P(夺冠)=0.08，符合约束"
    },
    {
        "name": "等价市场",
        "market_a": {
            "question": "Will Bitcoin reach $100,000 by December 31, 2024?",
            "description": "Resolves YES if Bitcoin price reaches or exceeds $100,000 at any point before end of 2024.",
            "yes_price": 0.45,
            "end_date": "2024-12-31",
            "event_id": "btc-100k-2024",
            "resolution_source": "CoinGecko"
        },
        "market_b": {
            "question": "Bitcoin above $100k by end of 2024?",
            "description": "Market resolves YES if BTC/USD exceeds 100000 before January 1, 2025.",
            "yes_price": 0.40,  # 5%价差
            "end_date": "2024-12-31",
            "event_id": "bitcoin-price-2024",
            "resolution_source": "CoinGecko"
        },
        "expected_relationship": "EQUIVALENT",
        "expected_constraint_violated": True,
        "description": "两个市场问的是同一个问题，但价差5%"
    },
    {
        "name": "无关市场",
        "market_a": {
            "question": "Will it rain in New York City on January 1, 2025?",
            "description": "Weather prediction market.",
            "yes_price": 0.35,
            "end_date": "2025-01-01",
            "event_id": "nyc-weather-2025",
            "resolution_source": "Weather.gov"
        },
        "market_b": {
            "question": "Will the S&P 500 close above 5000 on December 31, 2024?",
            "description": "Stock market prediction.",
            "yes_price": 0.70,
            "end_date": "2024-12-31",
            "event_id": "sp500-2024",
            "resolution_source": "NYSE"
        },
        "expected_relationship": "UNRELATED",
        "expected_constraint_violated": False,
        "description": "天气和股票完全无关"
    },
    {
        "name": "数值阈值包含",
        "market_a": {
            "question": "Will Bitcoin reach $150,000 in 2025?",
            "description": "Resolves YES if BTC reaches $150k.",
            "yes_price": 0.25,
            "end_date": "2025-12-31",
            "event_id": "btc-150k",
            "resolution_source": "CoinGecko"
        },
        "market_b": {
            "question": "Will Bitcoin reach $100,000 in 2025?",
            "description": "Resolves YES if BTC reaches $100k.",
            "yes_price": 0.20,  # 违反约束：应该 >= 0.25
            "end_date": "2025-12-31",
            "event_id": "btc-100k",
            "resolution_source": "CoinGecko"
        },
        "expected_relationship": "IMPLIES_AB",
        "expected_constraint_violated": True,
        "description": "BTC破$150k → BTC破$100k，但 P($100k)=0.20 < P($150k)=0.25，违反约束"
    },
]


def run_test(test_case: dict, client, verbose: bool = True):
    """运行单个测试用例"""
    print(f"\n{'='*60}")
    print(f"测试: {test_case['name']}")
    print(f"{'='*60}")
    print(f"说明: {test_case['description']}")
    print(f"预期关系: {test_case['expected_relationship']}")
    print(f"预期违反约束: {test_case['expected_constraint_violated']}")

    # 格式化Prompt
    prompt = format_analysis_prompt(
        test_case['market_a'],
        test_case['market_b'],
        PromptConfig(version="v2")
    )

    if verbose:
        print(f"\n--- Prompt长度: {len(prompt)} 字符 ---")

    # 调用LLM
    print("\n正在分析...")
    try:
        response = client.chat(prompt)
        content = response.content

        # 提取JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())

        # 显示结果
        print(f"\n--- LLM分析结果 ---")
        print(f"关系类型: {result.get('relationship')}")
        print(f"置信度: {result.get('confidence')}")
        print(f"约束违反: {result.get('constraint_violated')}")
        print(f"违反程度: {result.get('violation_amount', 0)}")
        print(f"套利可行: {result.get('arbitrage_viable')}")

        # 显示推理过程
        reasoning = result.get('reasoning', {})
        if isinstance(reasoning, dict):
            print(f"\n推理过程:")
            for key, value in reasoning.items():
                print(f"  {key}: {value[:100]}..." if len(str(value)) > 100 else f"  {key}: {value}")
        else:
            print(f"\n推理: {reasoning[:200]}..." if len(str(reasoning)) > 200 else f"\n推理: {reasoning}")

        # 边界情况
        edge_cases = result.get('edge_cases', [])
        if edge_cases:
            print(f"\n边界情况:")
            for case in edge_cases[:3]:
                print(f"  - {case}")

        # 验证结果
        relationship_match = result.get('relationship') == test_case['expected_relationship']
        constraint_match = result.get('constraint_violated', False) == test_case['expected_constraint_violated']

        print(f"\n--- 验证结果 ---")
        print(f"关系判断: {'✅ 正确' if relationship_match else '❌ 错误'}")
        print(f"约束判断: {'✅ 正确' if constraint_match else '❌ 错误'}")

        return {
            "name": test_case['name'],
            "relationship_correct": relationship_match,
            "constraint_correct": constraint_match,
            "llm_result": result
        }

    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        print(f"原始响应: {response.content[:500]}...")
        return {"name": test_case['name'], "error": str(e)}
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        return {"name": test_case['name'], "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Prompt测试脚本")
    parser.add_argument("--profile", "-p", type=str, help="LLM配置名称")
    parser.add_argument("--model", "-m", type=str, help="覆盖默认模型")
    parser.add_argument("--config", "-c", type=str, help="配置文件路径")
    parser.add_argument("--test", "-t", type=int, help="只运行指定编号的测试（从0开始）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()

    # 初始化LLM客户端
    print("初始化LLM客户端...")
    try:
        # 方式1: 使用 --profile 参数
        if args.profile:
            from llm_config import get_llm_config_by_name
            profile = get_llm_config_by_name(args.profile)
            if not profile:
                print(f"❌ 未找到配置: {args.profile}")
                return 1
            if not profile.is_configured():
                print(f"❌ 配置未设置API Key: {profile.api_key_env}")
                return 1

            model = args.model or profile.model
            client = create_llm_client(
                provider=profile.provider,
                api_base=profile.api_base,
                api_key=profile.get_api_key(),
                model=model,
            )
            print(f"✅ 使用配置 (--profile): {args.profile} / {model}")

        # 方式2: 使用 config.json
        else:
            import os
            from config import Config

            config = Config.load(args.config)

            # 检查config.json是否配置了非默认的provider
            if config.llm.provider and config.llm.provider != "openai":
                # 从config.json读取
                api_key = config.llm.api_key
                if not api_key:
                    # 尝试从环境变量读取
                    env_key_map = {
                        "openai": "OPENAI_API_KEY",
                        "anthropic": "ANTHROPIC_API_KEY",
                        "deepseek": "DEEPSEEK_API_KEY",
                        "aliyun": "DASHSCOPE_API_KEY",
                        "zhipu": "ZHIPU_API_KEY",
                        "siliconflow": "SILICONFLOW_API_KEY",
                        "openai_compatible": "LLM_API_KEY",
                    }
                    env_var = env_key_map.get(config.llm.provider, "LLM_API_KEY")
                    api_key = os.getenv(env_var)

                model = args.model or config.llm.model or None
                client = create_llm_client(
                    provider=config.llm.provider,
                    api_base=config.llm.api_base or None,
                    api_key=api_key,
                    model=model,
                )
                print(f"✅ 使用配置 (config.json): {config.llm.provider} / {client.config.model}")

            # 检查config.json是否配置了api_key或api_base
            elif config.llm.api_key or config.llm.api_base:
                model = args.model or config.llm.model or None
                client = create_llm_client(
                    provider=config.llm.provider,
                    api_base=config.llm.api_base or None,
                    api_key=config.llm.api_key or None,
                    model=model,
                )
                print(f"✅ 使用配置 (config.json): {config.llm.provider} / {client.config.model}")

            # 方式3: 自动检测
            else:
                from llm_config import get_llm_config
                profile = get_llm_config()
                if not profile:
                    print("❌ 未检测到可用的LLM配置")
                    print("   请选择以下方式之一:")
                    print("   1. 设置环境变量 (如 DEEPSEEK_API_KEY)")
                    print("   2. 使用 --profile 参数 (如 --profile deepseek)")
                    print("   3. 在 config.json 中配置 llm.provider 和 llm.api_key")
                    return 1

                model = args.model or profile.model
                client = create_llm_client(
                    provider=profile.provider,
                    api_base=profile.api_base,
                    api_key=profile.get_api_key(),
                    model=model,
                )
                print(f"✅ 使用配置 (自动检测): {profile.name} / {model}")

    except Exception as e:
        print(f"❌ LLM初始化失败: {e}")
        return 1

    # 运行测试
    results = []
    test_cases = TEST_CASES

    if args.test is not None:
        if 0 <= args.test < len(test_cases):
            test_cases = [test_cases[args.test]]
        else:
            print(f"❌ 无效的测试编号: {args.test}，有效范围: 0-{len(TEST_CASES)-1}")
            return 1

    for test_case in test_cases:
        result = run_test(test_case, client, verbose=args.verbose)
        results.append(result)

    # 汇总结果
    print(f"\n{'='*60}")
    print("测试汇总")
    print(f"{'='*60}")

    total = len(results)
    correct_rel = sum(1 for r in results if r.get('relationship_correct', False))
    correct_con = sum(1 for r in results if r.get('constraint_correct', False))
    errors = sum(1 for r in results if 'error' in r)

    print(f"总测试数: {total}")
    print(f"关系判断正确: {correct_rel}/{total-errors} ({correct_rel/(total-errors)*100:.1f}%)" if total > errors else "")
    print(f"约束判断正确: {correct_con}/{total-errors} ({correct_con/(total-errors)*100:.1f}%)" if total > errors else "")
    print(f"错误数: {errors}")

    for r in results:
        status = "✅" if r.get('relationship_correct') and r.get('constraint_correct') else "❌" if 'error' not in r else "⚠️"
        print(f"  {status} {r['name']}")

    client.close()
    return 0


if __name__ == "__main__":
    exit(main())
