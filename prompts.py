#!/usr/bin/env python3
"""
Polymarket 套利系统 - Prompt工程模块
=====================================

本模块包含用于LLM分析市场逻辑关系的Prompt模板。
通过精心设计的Prompt提高关系识别准确率。

设计原则：
1. 链式思考 (CoT) - 引导LLM逐步推理
2. 丰富上下文 - 提供完整市场信息
3. 具体示例 - 用例子说明各种关系类型
4. 结算规则优先 - 强调检查结算规则差异
5. 边界情况分析 - 引导深入分析例外情况
"""

from typing import Dict, Optional
from dataclasses import dataclass

# ============================================================
# Prompt模板 v2 - 优化版
# ============================================================

RELATIONSHIP_ANALYSIS_PROMPT_V2 = """你是一位预测市场套利分析专家，专门识别Polymarket上市场之间的逻辑关系。

## 任务
分析以下两个预测市场之间是否存在可利用的逻辑关系。

## 市场信息

### 市场A
- **问题**: {question_a}
- **描述**: {description_a}
- **YES价格**: ${price_a:.3f} (即市场认为有{prob_a:.1f}%概率发生)
- **结算日期**: {end_date_a}
- **所属事件**: {event_id_a}
- **结算来源**: {source_a}

### 市场B
- **问题**: {question_b}
- **描述**: {description_b}
- **YES价格**: ${price_b:.3f} (即市场认为有{prob_b:.1f}%概率发生)
- **结算日期**: {end_date_b}
- **所属事件**: {event_id_b}
- **结算来源**: {source_b}

## 逻辑关系类型定义

请判断这两个市场属于以下哪种关系：

### 1. IMPLIES_AB (A蕴含B)
- **定义**: 如果A发生，B必然发生。但B发生不一定意味着A发生。
- **数学约束**: P(B) ≥ P(A)
- **套利条件**: 当 P(B) < P(A) 时存在套利
- **典型例子**:
  - "Trump赢得总统" → "共和党赢得总统" (因为Trump是共和党候选人)
  - "Lakers夺冠" → "Lakers进入季后赛" (夺冠必须先进季后赛)
  - "BTC突破$150k" → "BTC突破$100k" (更高阈值包含更低阈值)
  - "在2025年1月前发生" → "在2025年6月前发生" (更早时间被更晚时间包含)

### 2. IMPLIES_BA (B蕴含A)
- **定义**: 如果B发生，A必然发生。与IMPLIES_AB相反。
- **数学约束**: P(A) ≥ P(B)

### 3. EQUIVALENT (等价)
- **定义**: A和B描述的是完全相同的事件，只是表述不同。
- **数学约束**: P(A) = P(B)
- **套利条件**: 当 |P(A) - P(B)| > 3% 时存在套利
- **典型例子**:
  - "Will Trump win the 2024 election?" ≡ "Trump victory in November 2024?"
  - "Bitcoin above $100k by December?" ≡ "BTC price > $100,000 end of year?"

### 4. MUTUAL_EXCLUSIVE (互斥)
- **定义**: A和B不能同时发生。
- **数学约束**: P(A) + P(B) ≤ 1
- **典型例子**:
  - "Trump赢得2024" 互斥于 "Biden赢得2024"
  - "Lakers夺冠" 互斥于 "Celtics夺冠"

### 5. EXHAUSTIVE (完备集成员)
- **定义**: A和B是同一完备集的不同选项（互斥且穷尽所有可能）。
- **数学约束**: 完备集中所有选项概率之和 = 1
- **套利条件**: 当所有选项价格之和 < 1 时存在套利

### 6. UNRELATED (无关)
- **定义**: 两市场之间没有确定的逻辑关系。

## 分析步骤 (请逐步思考)

**第一步：理解两个市场**
- 市场A具体在问什么？事件发生的条件是什么？
- 市场B具体在问什么？事件发生的条件是什么？

**第二步：检查结算规则兼容性** ⚠️ 最重要
- 两个市场的结算来源是否相同或兼容？
- 结算日期是否接近？时间差异是否会导致不同结果？
- 是否存在结算规则细节差异导致"A发生但B不发生"的可能？

**第三步：判断逻辑关系**
- 如果A发生，B是否必然发生？
- 如果B发生，A是否必然发生？
- 两者是否完全等价？
- 两者是否互斥？

**第四步：分析边界情况**
- 有哪些极端或特殊情况可能打破这种逻辑关系？
- 候选人退出、规则变更、定义模糊等情况是否可能影响？

**第五步：验证价格合理性**
- 当前价格是否符合逻辑约束？
- 如果违反约束，差距有多大？

## 输出格式

请严格按以下JSON格式回答（不要包含其他内容）：

```json
{{
  "relationship": "IMPLIES_AB|IMPLIES_BA|EQUIVALENT|MUTUAL_EXCLUSIVE|EXHAUSTIVE|UNRELATED",
  "confidence": 0.0到1.0的数值,
  "reasoning": {{
    "market_a_understanding": "对市场A的理解",
    "market_b_understanding": "对市场B的理解",
    "logical_analysis": "逻辑关系分析",
    "conclusion": "最终结论"
  }},
  "probability_constraint": "如P(B)>=P(A)，无约束则为null",
  "constraint_violated": true或false,
  "violation_amount": 价格违反约束的程度（如0.05表示差5%），无违反则为0,
  "edge_cases": ["可能打破关系的边界情况"],
  "resolution_check": {{
    "sources_compatible": true或false,
    "dates_compatible": true或false,
    "rules_compatible": true或false,
    "compatibility_notes": "兼容性说明"
  }},
  "arbitrage_viable": true或false,
  "arbitrage_notes": "套利可行性说明"
}}
```
"""


# ============================================================
# 完备集验证Prompt
# ============================================================

EXHAUSTIVE_SET_VERIFICATION_PROMPT = """你是一位预测市场分析专家，请验证以下市场组是否构成一个完备集。

## 什么是完备集？
完备集是一组市场，满足：
1. **互斥性**: 任意两个市场不能同时为YES
2. **完备性**: 所有可能的结果都被覆盖，必有且仅有一个市场最终为YES

## 需要验证的市场组

事件: {event_title}

{markets_list}

总YES价格: ${total_price:.4f}

## 分析要点

1. **互斥性检查**: 这些选项是否真的互斥？有没有可能两个同时发生？
2. **完备性检查**: 是否覆盖了所有可能？有没有遗漏的选项？
3. **结算一致性**: 所有市场的结算规则是否一致？结算来源是否相同？
4. **时间一致性**: 结算时间是否相同？

## 输出格式

```json
{{
  "is_valid_exhaustive_set": true或false,
  "is_mutually_exclusive": true或false,
  "is_complete": true或false,
  "missing_options": ["可能遗漏的选项"],
  "overlap_risks": ["可能同时发生的情况"],
  "resolution_consistent": true或false,
  "confidence": 0.0到1.0,
  "reasoning": "分析说明",
  "arbitrage_safe": true或false
}}
```
"""


# ============================================================
# 简化版Prompt（用于成本敏感场景）
# ============================================================

RELATIONSHIP_ANALYSIS_PROMPT_LITE = """分析两个预测市场的逻辑关系：

市场A: {question_a} (YES=${price_a:.2f})
市场B: {question_b} (YES=${price_b:.2f})

关系类型：
1. IMPLIES_AB: A发生→B必发生 (约束P(B)≥P(A))
2. IMPLIES_BA: B发生→A必发生 (约束P(A)≥P(B))
3. EQUIVALENT: A≡B，同一事件
4. MUTUAL_EXCLUSIVE: A、B互斥
5. EXHAUSTIVE: 完备集成员
6. UNRELATED: 无关

回答JSON格式：
```json
{{"relationship": "类型", "confidence": 0.0-1.0, "reasoning": "原因", "constraint_violated": true/false}}
```
"""


# ============================================================
# Prompt选择器
# ============================================================

@dataclass
class PromptConfig:
    """Prompt配置"""
    version: str = "v2"  # v2=详细版, lite=简化版
    include_examples: bool = True
    include_cot: bool = True  # 链式思考


def get_analysis_prompt(config: PromptConfig = None) -> str:
    """获取分析Prompt"""
    if config is None:
        config = PromptConfig()

    if config.version == "lite":
        return RELATIONSHIP_ANALYSIS_PROMPT_LITE
    else:
        return RELATIONSHIP_ANALYSIS_PROMPT_V2


def format_analysis_prompt(
    market_a: Dict,
    market_b: Dict,
    config: PromptConfig = None
) -> str:
    """格式化分析Prompt"""
    template = get_analysis_prompt(config)

    # 根据版本选择格式化参数
    if config and config.version == "lite":
        return template.format(
            question_a=market_a.get("question", ""),
            price_a=market_a.get("yes_price", 0.5),
            question_b=market_b.get("question", ""),
            price_b=market_b.get("yes_price", 0.5),
        )
    else:
        return template.format(
            question_a=market_a.get("question", ""),
            description_a=(market_a.get("description", "") or "")[:500],
            price_a=market_a.get("yes_price", 0.5),
            prob_a=market_a.get("yes_price", 0.5) * 100,
            end_date_a=market_a.get("end_date", "未指定"),
            event_id_a=market_a.get("event_id", "未指定"),
            source_a=market_a.get("resolution_source", "未指定"),
            question_b=market_b.get("question", ""),
            description_b=(market_b.get("description", "") or "")[:500],
            price_b=market_b.get("yes_price", 0.5),
            prob_b=market_b.get("yes_price", 0.5) * 100,
            end_date_b=market_b.get("end_date", "未指定"),
            event_id_b=market_b.get("event_id", "未指定"),
            source_b=market_b.get("resolution_source", "未指定"),
        )


def format_exhaustive_prompt(
    event_title: str,
    markets: list,
    total_price: float
) -> str:
    """格式化完备集验证Prompt"""
    markets_list = "\n".join([
        f"- {m.get('question', '')}: YES=${m.get('yes_price', 0):.3f}"
        for m in markets
    ])

    return EXHAUSTIVE_SET_VERIFICATION_PROMPT.format(
        event_title=event_title,
        markets_list=markets_list,
        total_price=total_price
    )


# ============================================================
# 找碴验证Prompt (Devil's Advocate) - v1.3新增
# ============================================================

DEVILS_ADVOCATE_PROMPT = """你是一位预测市场的风险分析专家，专门负责"找碴" - 寻找套利策略可能失败的原因。

## 背景
我们的系统认为市场A和市场B之间存在以下逻辑关系：
**{relationship}**

这意味着如果策略正确，我们可以通过买卖这两个市场来获得无风险利润。

## 市场信息

### 市场A
- **问题**: {question_a}
- **YES价格**: ${price_a:.3f}
- **结算日期**: {end_date_a}
- **结算来源**: {source_a}

### 市场B
- **问题**: {question_b}
- **YES价格**: ${price_b:.3f}
- **结算日期**: {end_date_b}
- **结算来源**: {source_b}

## 你的任务

**假设我们的关系判断是正确的**，请深入思考：有哪些情况可能导致"A发生但B没有结算为YES"（或反过来）？

请从以下角度分析可能的失败场景：

### 1. 结算规则差异
- 两个市场的结算标准是否完全相同？
- 是否使用不同的数据来源？
- 对"发生"的定义是否有细微差别？

### 2. 时间窗口差异 [关键检查！]
- **结算日期对比**：市场A结算日期={end_date_a}，市场B结算日期={end_date_b}
- **时区问题**：两市场是否使用不同时区？(UTC vs EST vs 本地时间)
- **蕴含关系规则**：
  - 如果 A→B (A蕴含B)，则 B的结算时间必须 >= A的结算时间
  - 如果 B→A (B蕴含A)，则 A的结算时间必须 >= B的结算时间
- **时间差风险**：两市场结算时间差是否 > 24小时？如果是，需特别警惕
- 是否可能出现"在时间点T1为真，在时间点T2为假"的情况？

### 3. 边界条件
- 如果出现平局/取消/无效结果会怎样？
- 候选人退选/规则变更/定义模糊等情况？
- 法律争议、计票争议等导致结果不确定？

### 4. 技术风险
- 预言机（Oracle）可能出错吗？
- 是否可能出现治理攻击或争议裁决？

### 5. 市场特性
- 两个市场是否由同一方运营？
- 结算机制是否相同（UMA vs 其他）？

## 输出格式

请严格按以下JSON格式回答：

```json
{{
  "relationship_challenged": "{relationship}",
  "overall_risk_level": "low|medium|high|critical",
  "failure_scenarios": [
    {{
      "scenario": "失败场景描述",
      "probability": "low|medium|high",
      "impact": "描述如果发生会如何影响套利",
      "mitigation": "如何降低这个风险"
    }}
  ],
  "resolution_risks": {{
    "different_sources": true或false,
    "different_timing": true或false,
    "definition_ambiguity": true或false,
    "oracle_risk": true或false,
    "details": "详细说明"
  }},
  "edge_cases": [
    "具体的边界情况1",
    "具体的边界情况2"
  ],
  "recommendation": "proceed|proceed_with_caution|avoid|need_human_review",
  "human_checks_needed": [
    "需要人工确认的事项1",
    "需要人工确认的事项2"
  ],
  "confidence_in_challenge": 0.0到1.0的数值,
  "summary": "一句话总结风险评估"
}}
```

注意：你的任务是找问题，不是确认安全。请尽可能挑剔地分析。
"""


DEVILS_ADVOCATE_PROMPT_LITE = """作为风险分析专家，请找出以下套利策略可能失败的原因：

关系: {relationship}
市场A: {question_a} (YES=${price_a:.2f})
市场B: {question_b} (YES=${price_b:.2f})

问题：有哪些情况可能导致"A发生但B没结算为YES"？

考虑：结算规则差异、时间窗口、边界条件、预言机风险

回答JSON格式：
```json
{{"risk_level": "low/medium/high", "failure_scenarios": ["场景1", "场景2"], "recommendation": "proceed/avoid/review", "summary": "总结"}}
```
"""


def format_devils_advocate_prompt(
    market_a: Dict,
    market_b: Dict,
    relationship: str,
    lite: bool = False
) -> str:
    """格式化找碴验证Prompt"""
    template = DEVILS_ADVOCATE_PROMPT_LITE if lite else DEVILS_ADVOCATE_PROMPT

    return template.format(
        relationship=relationship,
        question_a=market_a.get("question", ""),
        price_a=market_a.get("yes_price", 0.5),
        end_date_a=market_a.get("end_date", "未指定"),
        source_a=market_a.get("resolution_source", "未指定"),
        question_b=market_b.get("question", ""),
        price_b=market_b.get("yes_price", 0.5),
        end_date_b=market_b.get("end_date", "未指定"),
        source_b=market_b.get("resolution_source", "未指定"),
    )


# ============================================================
# 多模型投票Prompt - v1.3新增
# ============================================================

SECOND_OPINION_PROMPT = """你是一位独立的预测市场分析师。另一位分析师对两个市场做了以下判断，请提供你的独立意见。

## 市场信息

市场A: {question_a} (YES=${price_a:.2f})
市场B: {question_b} (YES=${price_b:.2f})

## 第一位分析师的判断

- **关系类型**: {first_relationship}
- **置信度**: {first_confidence}
- **理由**: {first_reasoning}

## 你的任务

1. **独立分析**这两个市场的关系，不要受第一位分析师影响
2. **给出你自己的判断**
3. **对比差异**：如果你的判断与第一位不同，解释为什么

## 输出格式

```json
{{
  "my_relationship": "IMPLIES_AB|IMPLIES_BA|EQUIVALENT|MUTUAL_EXCLUSIVE|EXHAUSTIVE|UNRELATED",
  "my_confidence": 0.0到1.0,
  "my_reasoning": "你的分析理由",
  "agree_with_first": true或false,
  "disagreement_reason": "如果不同意，解释原因，否则为null",
  "final_recommendation": "agree|partial_agree|disagree",
  "combined_confidence": 0.0到1.0
}}
```
"""


def format_second_opinion_prompt(
    market_a: Dict,
    market_b: Dict,
    first_analysis: Dict
) -> str:
    """格式化第二意见Prompt"""
    return SECOND_OPINION_PROMPT.format(
        question_a=market_a.get("question", ""),
        price_a=market_a.get("yes_price", 0.5),
        question_b=market_b.get("question", ""),
        price_b=market_b.get("yes_price", 0.5),
        first_relationship=first_analysis.get("relationship", ""),
        first_confidence=first_analysis.get("confidence", 0),
        first_reasoning=first_analysis.get("reasoning", "")
    )


# ============================================================
# Prompt测试工具
# ============================================================

def test_prompt():
    """测试Prompt格式化"""
    market_a = {
        "question": "Will Donald Trump win the 2024 presidential election?",
        "description": "This market resolves YES if Donald Trump wins the 2024 US Presidential Election.",
        "yes_price": 0.55,
        "end_date": "2024-11-06",
        "event_id": "2024-presidential-election",
        "resolution_source": "Associated Press"
    }

    market_b = {
        "question": "Will the Republican Party win the 2024 presidential election?",
        "description": "This market resolves YES if the Republican candidate wins.",
        "yes_price": 0.52,
        "end_date": "2024-11-06",
        "event_id": "2024-presidential-election",
        "resolution_source": "Associated Press"
    }

    # 测试详细版
    print("=" * 60)
    print("详细版Prompt (v2)")
    print("=" * 60)
    prompt_v2 = format_analysis_prompt(market_a, market_b, PromptConfig(version="v2"))
    print(prompt_v2[:2000] + "...")

    print("\n" + "=" * 60)
    print("简化版Prompt (lite)")
    print("=" * 60)
    prompt_lite = format_analysis_prompt(market_a, market_b, PromptConfig(version="lite"))
    print(prompt_lite)


if __name__ == "__main__":
    test_prompt()
