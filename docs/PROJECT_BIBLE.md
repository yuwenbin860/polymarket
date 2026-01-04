# Polymarket 组合套利系统

## 项目圣经 v1.3

> 本文档是项目的核心参考，包含需求定义、策略说明、技术设计、开发路线图和运维指南。
> 所有开发决策应参照本文档执行。

---

# 目录

1. [项目概述](#1-项目概述)
2. [开发准则](#2-开发准则)
3. [战略共识](#3-战略共识) ⭐ **v1.3 新增**
4. [市场背景与策略分析](#4-市场背景与策略分析)
5. [核心需求定义](#5-核心需求定义)
6. [系统架构设计](#6-系统架构设计)
7. [数据模型设计](#7-数据模型设计)
8. [核心算法详解](#8-核心算法详解)
9. [API与外部依赖](#9-api与外部依赖)
10. [开发路线图](#10-开发路线图)
11. [测试策略](#11-测试策略)
12. [风险管理](#12-风险管理)
13. [运维与监控](#13-运维与监控)
14. [扩展计划](#14-扩展计划) ⭐ **v1.3 更新**
15. [创意池](#15-创意池)
16. [附录](#16-附录)

> 📊 **进度追踪**: 查看项目进展和工作日志，请访问 [docs/PROGRESS.md](./PROGRESS.md)

---

# 1. 项目概述

## 1.1 项目定位

**Polymarket组合套利系统**是一个自动化工具，用于识别和捕获预测市场中因逻辑定价错误而产生的套利机会。

### 核心价值主张

| 传统方法 | 本系统方法 |
|----------|------------|
| 人工浏览市场寻找机会 | 自动化扫描数千市场 |
| 依赖直觉判断逻辑关系 | LLM辅助识别语义依赖 |
| 手动计算套利空间 | 实时计算并生成执行建议 |
| 容易错过短暂机会 | 持续监控，及时提醒 |

### 目标用户

- **主要用户**：具有一定技术能力、熟悉预测市场、追求稳健收益的个人交易者
- **使用场景**：每日定时扫描、重大事件前后集中扫描、持续监控模式

## 1.2 项目目标

### 短期目标（Phase 1-2）
- [x] 验证核心策略可行性
- [x] 构建MVP原型
- [x] 支持多种LLM提供商
- [ ] **在真实市场中发现并人工验证套利机会**
- [ ] **实现三层验证架构（关系识别→找碴验证→数学验证）**
- [ ] **完成至少3次成功的模拟执行跟踪**
- [ ] 实现小额（$100-500）手动执行的工作流

### 中期目标（Phase 3-4）
- [ ] 接入Myriad等去中心化平台，实现跨平台价差监控
- [ ] 建立历史回测系统
- [ ] 达到稳定正收益（验证策略有效性）
- [ ] 实现半自动化执行

### 长期目标（Phase 5+）
- [ ] 全自动化运行
- [ ] 扩展到多平台套利（Myriad、Drift BET等）
- [ ] 资金规模达到$10,000+

## 1.3 成功指标

| 指标 | Phase 2 | Phase 2.5 | Phase 3 |
|------|---------|-----------|---------|
| 每周发现机会数 | ≥1 | ≥3 | ≥5 |
| 机会验证准确率 | ≥50% | ≥70% | ≥85% |
| **找碴验证通过率** | - | ≥60% | ≥80% |
| **模拟执行成功率** | - | ≥70% | ≥90% |
| 执行成功率 | - | - | ≥95% |
| 月化收益率 | - | - | ≥5% |

## 1.4 项目边界

### 在范围内 ✅
- Polymarket平台内的组合套利
- **Polymarket与Myriad/Drift BET等去中心化平台的跨平台套利**
- 完备集套利、包含关系套利、等价市场套利
- 手动/半自动执行
- **语义相似度发现隐蔽机会**

### 不在范围内 ❌
- 基于预测的方向性交易（不是套利）
- 高频毫秒级套利（需要专业基础设施）
- 做空策略（Polymarket不支持原生做空）
- 杠杆交易
- **美国合规平台（Kalshi/PredictIt）- 需要美国身份**

---

# 2. 开发准则

> 这些准则指导整个项目的开发方式，确保高效、可追踪、持续迭代。

## 2.1 小步快跑 (Incremental Progress)

**原则**：将宏大目标拆分为小目标，每个小目标独立验证后再进行下一步。

```
宏大目标
├── 小目标 1 ← 实现 → 验证 ✓
├── 小目标 2 ← 实现 → 验证 ✓
├── 小目标 3 ← 实现 → 验证 ...
└── ...
```

**执行要点**：
- 每个小目标应该可以在1-3小时内完成验证
- 验证失败时及时调整方向，避免沉没成本
- 小目标完成后立即记录到进度追踪

## 2.2 进度持久化 (Progress Persistence)

**原则**：每完成一个目标，验证无误后更新进度到文档，确保随时可恢复。

**执行要点**：
- 完成一个小目标后，立即更新 [进度追踪](#3-进度追踪) 章节
- 记录：做了什么、结果如何、下一步是什么
- 确保在任何时间、任何地点都能快速恢复工作上下文

## 2.3 开放创新 (Open Innovation)

**原则**：欢迎任何能改进套利系统的新点子，经确认后记录。

**执行要点**：
- 新点子先记录到 [创意池](#15-创意池)
- 讨论确认可行性后，纳入正式开发计划
- 保持系统活力，不断迭代优化

## 2.4 核心聚焦 (Core Focus)

**原则**：套利是核心中的核心，发现机会比执行更重要。

```
优先级金字塔：

        ┌─────────────┐
        │  发现套利   │  ← 最高优先级
        │   机会      │
        ├─────────────┤
        │  LLM关系    │  ← 高优先级
        │   分析      │
        ├─────────────┤
        │  数据获取   │  ← 中优先级
        │   处理      │
        ├─────────────┤
        │  执行下单   │  ← 低优先级（可人工）
        │   监控      │
        └─────────────┘
```

**执行要点**：
- 第一步重心：组合套利（完备集、包含关系、等价市场）
- 预留不同套利模式的接入口
- 执行和下单可以暂时人工，**发现机会才是关键**

## 2.5 LLM赋能 (LLM Empowerment)

**原则**：最大化利用LLM进行语义分析和逻辑推理。

**LLM在套利系统中的作用**：

| 任务 | LLM作用 | 重要程度 |
|------|---------|----------|
| 识别市场逻辑关系 | 核心能力 | ⭐⭐⭐⭐⭐ |
| 判断完备集完整性 | 辅助验证 | ⭐⭐⭐⭐ |
| 分析结算规则差异 | 风险提示 | ⭐⭐⭐⭐ |
| 生成套利建议 | 输出整理 | ⭐⭐⭐ |
| 边界情况分析 | 风险识别 | ⭐⭐⭐⭐ |

**执行要点**：
- 持续优化Prompt，提高关系识别准确率
- 探索多模型协作、交叉验证
- 记录LLM表现，用于持续改进

## 2.6 实证优先 (Evidence-First Approach)

**原则**：先验证真实套利机会存在，再设计识别算法。

**正确流程**：
```
1. 人工发现真实案例 → 2. 验证确实是套利 → 3. 设计识别算法 → 4. 实现并测试
```

**错误流程**：
```
1. 设计理论模型 → 2. 实现算法 → 3. 希望能找到套利（可能找不到）
```

**执行要点**：
- 每一种新套利类型，必须先有至少1个真实案例
- 人工验证该案例确实存在套利空间后，再投入开发
- 避免"闭门造车"——实践出真知

## 2.7 策略迭代 (Strategy Evolution)

**原则**：项目进行中发现新的套利策略，需及时提出并更新到圣经。

**执行流程**：
```
1. 发现新策略/模式 → 记录到创意池（第15章）
2. 讨论验证可行性 → 人工测试至少1个真实案例
3. 验证通过 → 正式更新到套利策略章节（第4章）
4. 规划实现 → 添加到开发路线图（第10章）
```

**执行要点**：
- 新发现不要遗忘，立即记录到创意池
- 经验证的策略及时"晋升"到正式章节
- 保持项目圣经作为"活文档"，持续演进

---

# 3. 战略共识

> **v1.3 新增** (2026-01-02) - 本章记录项目核心战略决策和共识

## 3.1 核心策略优先级

基于对市场竞争格局和散户优势的分析，确定以下策略优先级：

| 策略 | 饱和度 | 频率 | 散户优势 | 资金门槛 | 风险 | **推荐指数** |
|------|--------|------|----------|----------|------|-------------|
| **包含关系套利** | 🟢低 | 中低频 | ⭐⭐⭐⭐⭐ | $500 | 低 | **A+** |
| **等价市场套利** | 🟢低 | 中低频 | ⭐⭐⭐⭐ | $500 | 低 | **A** |
| **完备集套利** | 🟢低 | 中低频 | ⭐⭐⭐⭐ | $500 | 低 | **A** |
| 跨平台套利(同链) | 🟢低 | 中低频 | ⭐⭐⭐ | $1000 | 中 | **B+** |
| 相关性交易 | 🟡中 | 中频 | ⭐⭐⭐ | $1000 | 中 | **B** |
| 跨平台套利(跨链) | 🟢低 | 低频 | ⭐⭐ | $2000+ | 高 | **B-** |
| 尾部清理套利 | 🟡中 | 低频 | ⭐⭐ | $5000+ | 高 | **B-** |
| 做市策略 | 🟡中 | 持续 | ⭐⭐ | $10000+ | 中 | **C+** |
| 时间延迟套利 | 🟠高 | 高频 | ⭐ | $5000+ | 中 | **C** |
| 单市场套利 | 🔴极高 | 毫秒级 | ❌ | 专业基础设施 | 低 | **D** |

> **v1.4更新 (2026-01-03)**: 跨链跨平台套利从 A- 降级为 B-，原因见 [3.6 三大实战陷阱](#36-三大实战陷阱)

### 核心结论：包含关系套利是核心中的核心

**理由**：
1. **语义理解门槛最高** - 机器人最难自动化，需要理解 "Trump wins" → "GOP wins" 这类逻辑
2. **LLM优势最明显** - 这正是LLM的强项
3. **利润空间可观** - 研究显示成功的组合套利平均利润 ~$19,000/对
4. **竞争最小** - 只占总套利利润的 0.24%，说明机器人不做这个

## 3.2 验证优先原则

> **核心原则**：不急于自动化执行，先验证策略有效性

### 验证清单

在执行任何套利之前，必须完成以下验证：

- [ ] LLM关系识别通过
- [ ] 找碴验证通过（无边界情况）
- [ ] 数学验证通过（利润 > 2%）
- [ ] 人工阅读两市场结算规则
- [ ] 人工确认无时间差风险
- [ ] 小额模拟执行成功

### 验证机制

1. **静态验证（自动）**
   - 数学验证层 (`validators.py`)
   - LLM找碴验证
   - 结算规则对比

2. **动态验证（人工）**
   - 人工打开两个市场页面对比
   - 阅读结算规则细则
   - 检查历史结算记录

3. **模拟执行（半自动）**
   - 记录"假设执行"的仓位
   - 跟踪市场变化
   - 结算后计算"假设收益"

## 3.3 散户优势分析

我们作为散户的优势：

| 优势 | 说明 |
|------|------|
| **语义理解能力** | LLM辅助识别复杂逻辑关系 |
| **耐心等待** | 不需要高频，等待中低频机会 |
| **无KYC限制** | 去中心化平台无身份验证门槛 |
| **灵活资金** | 小资金可以进入大机构忽略的市场 |

## 3.4 技术架构共识

### 相似度计算流程

```
1. event_id 分组 (最快，同事件必相关)
        ↓
2. Jaccard 关键词 (快速初筛，阈值0.2)
        ↓
3. 向量相似度 (语义发现，阈值0.7)  ← Phase 2 引入
        ↓
4. LLM 精确分析 (最终判断)
```

### LLM 三层验证架构

```
Layer 1: 关系识别 (Analyzer)
- 识别 A→B 的逻辑关系
- 输出：关系类型、置信度
        ↓
Layer 2: 找碴验证 (Devil's Advocate)  ← 新增
- Prompt: "假设A发生但B没结算为YES，有哪些可能的情况？"
- 结算规则差异、时间窗口差异、边界条件
        ↓
Layer 3: 多模型交叉验证 (Voting)  ← 新增
- DeepSeek + Qwen 双模型
- 意见不一致时标记为"需人工复核"
```

## 3.5 跨平台战略（针对非美国用户）

> **重要约束**：用户是中国公民，无法使用 Kalshi/PredictIt 等美国合规平台

### 可用平台优先级

| 平台 | 类型 | 链 | 费用 | 无需KYC | 与Poly信息差 | **优先级** |
|------|------|-----|------|---------|-------------|-----------|
| **Myriad** | 去中心化 | BNB Chain | 低 | ✅ | 中高 | **1 (最优先)** |
| **Drift BET** | 去中心化 | Solana | 极低 | ✅ | 中 | **2** |
| Azuro | 去中心化 | Polygon/Gnosis | 低 | ✅ | 中 | **3** |
| ~~Kalshi~~ | 合规/法币 | USD | 0.7% | ❌需KYC | 高 | **不可用** |
| ~~PredictIt~~ | 合规/法币 | USD | 5%+5% | ❌需KYC | 高 | **不可用** |

### Myriad 选择理由

1. **专门服务非美国用户** - BNB Chain 版本面向非美区
2. **用户群体差异** - 与 Polymarket 用户群体有一定分割
3. **无身份验证** - 钱包连接即可，已有 51万+ 用户

## 3.6 三大实战陷阱

> **v1.4 新增** (2026-01-03) - 记录经代码审查确认的实战风险

### 陷阱1：Bid/Ask vs Last Price（价格数据的"自欺欺人"）

**问题**：API 返回的 `outcomePrices` 通常是 Mid Price 或 Last Price，不是真实的交易价格。

**致命影响**：
```
你看到: yes_price = 0.50
实际盘口: Bid @ 0.48, Ask @ 0.52
你买入必须按 Ask (0.52) 买，不是 0.50
后果: 计算出 2% 利润，实际执行亏 4%
```

**修复措施**（已实现 v1.4）：
- Market 实体增加 `best_bid`, `best_ask`, `spread` 字段
- 通过 CLOB API (`https://clob.polymarket.com/book`) 获取真实订单簿
- 套利公式使用 `effective_buy_price` (best_ask) 计算成本
- 输出中显示 "中间价利润 vs 实际利润" 对比

### 陷阱2：跨链套利的"过桥费"

**问题**：Polymarket 在 Polygon，跨链到 BNB/Solana 存在巨大摩擦。

**致命影响**：
```
跨链时间: 几分钟到半小时
套利窗口: 通常只有几秒
结论: 除非预存资金，否则无法捕捉机会

跨链成本 (以 $500 交易为例):
- 桥费用: $5-15
- 源链 Gas: $0.5-2
- 目标链 Gas: $0.5-2
- 总成本: $6-19 = 1.2%-3.8% 的资金
```

**策略建议**：
| 策略 | 可行性 | 原因 |
|------|--------|------|
| Polymarket 内部组合套利 | ✅ 推荐 | 同链，无跨链成本 |
| 同链跨平台套利 (Poly vs Azuro) | 🟡 谨慎 | 需评估 Gas 和流动性 |
| 跨链跨平台套利 | ❌ 仅限长窗口期 | 跨链成本占比过高 |

**结论**：初期死磕 **Polymarket 内部** 的组合套利（同链、同合约、原子化）。

### 陷阱3：时间一致性的"隐形杀手"

**问题**：LLM 容易忽略时间状语差异，导致误判蕴含关系。

**案例**：
```
市场 A: "Bitcoin > 100k in 2024?" (结算: 2024-12-31 UTC)
市场 B: "Bitcoin > 100k by Jan 2025?" (结算: 2025-01-01 EST)

看似 B 包含 A，但时区差异可能导致：
- A 结算为 NO（2024年底未达到）
- B 结算为 YES（2025年1月1日达到）
```

**必检规则**：
1. **蕴含关系 (A→B)**：`end_date(B) >= end_date(A)`
2. **完备集**：所有市场的 `end_date` 差异 ≤ 24小时
3. **时区**：确认使用 UTC 还是本地时间

**人工复核清单新增项**：
- [ ] 确认两市场结算时间差 ≤ 24小时
- [ ] 确认时区一致（或已正确转换）
- [ ] 对于 A→B：确认 B 的结算不早于 A

---

# 4. 市场背景与策略分析

## 4.1 Polymarket平台概述

### 平台基本信息

| 属性 | 说明 |
|------|------|
| 类型 | 去中心化预测市场 |
| 底层链 | Polygon（以太坊L2） |
| 结算货币 | USDC |
| 交易费用 | 0%（全球站）/ 0.01%（美国站计划） |
| 预言机 | UMA Optimistic Oracle |
| 2024年交易量 | ~$9B |
| 估值 | $9B（2025年ICE投资后） |

### 市场结构

```
Event（事件）
├── Market 1（市场1）: "Trump wins?"
│   ├── YES Token（是代币）
│   └── NO Token（否代币）
├── Market 2（市场2）: "Trump wins by 1-49?"
│   ├── YES Token
│   └── NO Token
└── Market 3（市场3）: "Trump wins by 50+?"
    ├── YES Token
    └── NO Token
```

### 定价机制

- **订单簿模式**（非AMM）：买卖双方直接匹配
- **价格范围**：$0.00 - $1.00
- **结算规则**：
  - YES赢得 → 支付$1.00
  - NO赢得 → 支付$1.00
- **理论约束**：P(YES) + P(NO) = 1.00

## 4.2 套利机会来源分析

### 为什么会存在套利机会？

根据学术研究（IMDEA Networks Institute, 2025），2024年4月至2025年4月期间，套利者从Polymarket提取了超过**$40M**的利润。机会存在的原因：

| 原因 | 说明 |
|------|------|
| **散户主导** | 零售交易者情绪化定价，缺乏套利意识 |
| **市场分散** | 数千个市场，难以人工监控全部 |
| **语义复杂** | 相关市场表述不同，逻辑关系不明显 |
| **时间差** | 新闻事件导致不同市场反应速度不一 |
| **流动性碎片化** | 热门市场和冷门市场定价效率差异大 |

### 套利机会的竞争格局

| 策略类型 | 机器人竞争 | 个人机会 | 利润占比 | 说明 |
|----------|------------|----------|----------|------|
| 单市场套利 | 🔴极高 | ❌几乎无 | 99%+ | 毫秒级消失，需要节点级基础设施 |
| 收盘扫货 | 🟡中等 | ⚠️有限 | ~0.5% | 大户操纵风险，黑天鹅事件 |
| **组合套利** | 🟢低 | ✅有 | **0.24%** | 需要逻辑判断，LLM可辅助 |
| **做市** | 🟢低 | ✅有 | - | 需要资金和策略 |
| **跨平台套利** | 🟢低 | ✅有 | - | 需要多平台资金 |

### 选择组合套利的理由

1. **机器人最难做** —— 需要语义理解和逻辑推理
2. **LLM赋能** —— 大语言模型在这方面有优势
3. **资金门槛低** —— $500即可开始
4. **风险可控** —— 理论上无风险（需验证逻辑正确）
5. **可复用** —— 找到模式后可反复应用

## 4.3 组合套利策略详解

### 4.3.1 完备集套利（Exhaustive Set Arbitrage）

**定义**：一组互斥且覆盖所有可能结果的市场，其价格总和应该等于$1.00。

**套利条件**：Σ(YES价格) < $1.00

**数学原理**：
```
设有n个互斥且完备的结果: O₁, O₂, ..., Oₙ
约束: P(O₁) + P(O₂) + ... + P(Oₙ) = 1

如果市场定价: p₁ + p₂ + ... + pₙ < 1
则存在套利机会

操作: 买入所有选项各一份
成本: Σpᵢ < 1
回报: 1.00（无论哪个结果发生）
利润: 1.00 - Σpᵢ
```

**示例**：
```
事件：2028年美国大选结果

市场1: "共和党获270-299选举人票"  YES = $0.18
市场2: "共和党获300-319选举人票"  YES = $0.12
市场3: "共和党获320+选举人票"     YES = $0.05
市场4: "民主党获胜"              YES = $0.58
─────────────────────────────────────────────
总计: $0.93

操作: 各买一份，成本$0.93，必得$1.00
利润: $0.07 (7.5%)
```

**关键验证点**：
- [ ] 这些选项真的互斥吗？
- [ ] 这些选项覆盖了所有可能吗？
- [ ] 结算规则是否一致？
- [ ] 是否有遗漏的选项？

### 4.3.2 包含关系套利（Implication Arbitrage）

**定义**：如果事件A发生必然导致事件B发生（A → B），那么P(B) ≥ P(A)。

**套利条件**：P(B) < P(A) - ε（ε为交易成本）

**数学原理**：
```
逻辑关系: A → B（A蕴含B）
概率约束: P(B) ≥ P(A)

如果市场定价违反此约束: P(B) < P(A)
则存在套利机会

操作: 
- 买B的YES @ P(B)
- 买A的NO @ (1-P(A))

成本: P(B) + (1-P(A))
回报分析:
  - 若A发生（则B必发生）: B的YES=1, A的NO=0, 回报=1
  - 若A不发生且B发生: B的YES=1, A的NO=1, 回报=2
  - 若A不发生且B不发生: B的YES=0, A的NO=1, 回报=1

最小回报: 1.00
利润: 1.00 - 成本
```

**示例**：
```
逻辑关系: "特朗普赢" → "共和党赢"（因为特朗普是共和党候选人）

市场A: "特朗普赢得2028总统"     YES = $0.55
市场B: "共和党赢得2028总统"     YES = $0.50  ← 违反逻辑！

操作:
- 买 "共和党赢" YES @ $0.50
- 买 "特朗普赢" NO @ $0.45
成本: $0.95

结果分析:
┌─────────────────┬───────────┬───────────┬────────┐
│ 实际结果         │ 共和党YES │ 特朗普NO  │ 收入   │
├─────────────────┼───────────┼───────────┼────────┤
│ 特朗普赢        │ $1.00     │ $0.00     │ $1.00  │
│ 其他共和党人赢   │ $1.00     │ $1.00     │ $2.00  │
│ 民主党赢        │ $0.00     │ $1.00     │ $1.00  │
└─────────────────┴───────────┴───────────┴────────┘

无论结果如何，至少收入$1.00，利润≥$0.05 (5.3%)
```

**常见包含关系模式**：

| 模式 | 包含方向 | 示例 |
|------|----------|------|
| 个人→政党 | 候选人赢 → 政党赢 | Trump赢 → GOP赢 |
| 夺冠→季后赛 | 夺冠 → 进季后赛 | Lakers夺冠 → Lakers进季后赛 |
| 具体→抽象 | 具体事件 → 抽象类别 | BTC破$100k → BTC破$90k |
| 州→全国 | 赢关键州组合 → 赢全国 | 赢PA+GA+NC → 赢总统 |
| 时间包含 | 年内发生 → 半年内发生 | 2025年发生 → 2025H1发生 |

### 4.3.3 等价市场套利（Equivalent Market Arbitrage）

**定义**：两个市场本质上问的是同一个问题，只是表述不同。

**套利条件**：|P(A) - P(B)| > ε

**示例**：
```
市场A: "Will Trump win the 2024 election?"    YES = $0.52
市场B: "Trump victory November 2024?"         YES = $0.48

价差: 4%

操作:
- 买低价市场YES @ $0.48
- 买高价市场NO @ $0.48
成本: $0.96

回报: $1.00（两个市场结果必然相同）
利润: $0.04 (4.2%)
```

### 4.3.4 跨平台套利（Cross-Platform Arbitrage）

**定义**：同一事件在不同平台（如Polymarket和Kalshi）的定价不同。

**套利条件**：Polymarket_YES + Kalshi_NO < $1.00 - 费用

**示例**：
```
事件: "比特币1小时内是否突破$95,000"

Polymarket: YES = $0.45
Kalshi:     NO  = $0.48

操作:
- Polymarket买YES @ $0.45
- Kalshi买NO @ $0.48
成本: $0.93

结果: 无论涨跌，收入$1.00，利润$0.07 (7.5%)
```

**跨平台套利风险**：
- ⚠️ **结算规则差异**：两平台对"同一事件"的定义可能不同
- ⚠️ **时间差**：结算时间可能不一致
- ⚠️ **资金分散**：需要在两个平台都存资金
- ⚠️ **费用差异**：不同平台费用结构不同

## 4.4 研究数据支撑

### IMDEA研究关键发现（2024.04-2025.04）

| 指标 | 数据 |
|------|------|
| 分析的交易数 | 8600万笔 |
| 分析的市场数 | 17,218个 |
| 总套利利润 | $39,587,585 |
| 组合套利利润 | $95,157 (0.24%) |
| 组合套利识别对数 | 13对 |
| 成功产生利润的 | 5对 (38%) |
| Top 10套利者利润 | $8.18M (21%) |

### 关键洞察

1. **组合套利规模小但竞争也小**：只占0.24%说明机器人不做这个
2. **62%的LLM识别的依赖关系未能产生利润**：执行障碍是主要问题
3. **成功的组合套利平均利润~$19,000/对**：单个机会利润可观
4. **选举相关市场是主要机会来源**：政治事件产生最多相关市场

### 失败原因分析

| 失败原因 | 占比 | 说明 |
|----------|------|------|
| 结算规则差异 | ~40% | 两市场对"成功"定义不同 |
| 时间差问题 | ~25% | 结算时间不一致 |
| 逻辑关系误判 | ~20% | LLM判断错误 |
| 流动性不足 | ~15% | 无法以预期价格成交 |

---

# 5. 核心需求定义

## 5.1 功能需求

### FR-001: 市场数据获取

| ID | 需求 | 优先级 | Phase |
|----|------|--------|-------|
| FR-001-1 | 获取Polymarket所有活跃市场列表 | P0 | 1 |
| FR-001-2 | 获取市场的实时YES/NO价格 | P0 | 1 |
| FR-001-3 | 获取市场的流动性和交易量 | P0 | 1 |
| FR-001-4 | 获取市场的结算规则和来源 | P0 | 1 |
| FR-001-5 | 获取事件(Event)及其关联市场 | P0 | 1 |
| FR-001-6 | WebSocket实时价格推送 | P1 | 2 |
| FR-001-7 | 获取Kalshi市场数据 | P1 | 3 |
| FR-001-8 | 获取历史价格数据 | P2 | 3 |

### FR-002: 市场关系识别

| ID | 需求 | 优先级 | Phase |
|----|------|--------|-------|
| FR-002-1 | 基于event_id识别同事件市场 | P0 | 1 |
| FR-002-2 | 基于关键词识别相似市场 | P0 | 1 |
| FR-002-3 | 基于向量相似度识别语义相关市场 | P1 | 2 |
| FR-002-4 | LLM分析市场间逻辑关系类型 | P0 | 1 |
| FR-002-5 | LLM输出置信度和边界情况 | P0 | 1 |
| FR-002-6 | 支持多种LLM提供商切换 | P0 | 1 |
| FR-002-7 | 缓存已分析的市场对关系 | P1 | 2 |
| FR-002-8 | 支持人工标注和修正 | P2 | 3 |

### FR-003: 套利检测

| ID | 需求 | 优先级 | Phase |
|----|------|--------|-------|
| FR-003-1 | 检测完备集套利（总和<1） | P0 | 1 |
| FR-003-2 | 检测包含关系违规套利 | P0 | 1 |
| FR-003-3 | 检测等价市场价差套利 | P0 | 1 |
| FR-003-4 | 计算套利利润和成本 | P0 | 1 |
| FR-003-5 | 考虑交易费用和滑点 | P0 | 1 |
| FR-003-6 | 检测跨平台套利 | P1 | 3 |
| FR-003-7 | 设置最小利润阈值过滤 | P0 | 1 |
| FR-003-8 | 设置最小流动性阈值过滤 | P0 | 1 |

### FR-004: 报告与通知

| ID | 需求 | 优先级 | Phase |
|----|------|--------|-------|
| FR-004-1 | 生成JSON格式扫描报告 | P0 | 1 |
| FR-004-2 | 生成人类可读的套利建议 | P0 | 1 |
| FR-004-3 | 标注需要人工复核的项目 | P0 | 1 |
| FR-004-4 | 提供执行操作的具体步骤 | P0 | 1 |
| FR-004-5 | 支持微信/Telegram通知 | P2 | 3 |
| FR-004-6 | 支持邮件通知 | P2 | 3 |
| FR-004-7 | Web界面展示 | P2 | 4 |

### FR-005: 执行支持

| ID | 需求 | 优先级 | Phase |
|----|------|--------|-------|
| FR-005-1 | 提供Polymarket交易链接 | P0 | 1 |
| FR-005-2 | 计算建议仓位大小 | P1 | 2 |
| FR-005-3 | 半自动执行（确认后执行） | P2 | 4 |
| FR-005-4 | 全自动执行（小额） | P3 | 5 |
| FR-005-5 | 交易记录和跟踪 | P1 | 3 |

## 5.2 非功能需求

### NFR-001: 性能

| ID | 需求 | 目标值 |
|----|------|--------|
| NFR-001-1 | 单次扫描完成时间 | < 5分钟 |
| NFR-001-2 | LLM分析单对市场时间 | < 10秒 |
| NFR-001-3 | 支持扫描市场数量 | ≥ 500个 |

### NFR-002: 可靠性

| ID | 需求 | 目标值 |
|----|------|--------|
| NFR-002-1 | API请求失败重试 | 3次 |
| NFR-002-2 | 扫描任务可恢复 | 支持断点续扫 |
| NFR-002-3 | 数据持久化 | 本地JSON/SQLite |

### NFR-003: 可用性

| ID | 需求 | 目标值 |
|----|------|--------|
| NFR-003-1 | 命令行友好输出 | 彩色、结构化 |
| NFR-003-2 | 配置外部化 | 支持环境变量和配置文件 |
| NFR-003-3 | 日志级别可调 | DEBUG/INFO/WARN/ERROR |

### NFR-004: 成本

| ID | 需求 | 目标值 |
|----|------|--------|
| NFR-004-1 | LLM API月成本 | < $30 |
| NFR-004-2 | 服务器成本 | 本地运行，$0 |

## 5.3 用户故事（精简版）

| ID | 场景 | 核心验收标准 |
|----|------|-------------|
| US-001 | 首次使用 | 5分钟内完成环境验证，看到模拟扫描结果 |
| US-002 | 日常扫描 | 一条命令扫描，输出机会列表和利润率 |
| US-003 | 执行套利 | 提供买入指令、价格、Polymarket链接 |
| US-004 | 切换LLM | 通过配置切换提供商，无需改代码 |

---

# 6. 系统架构设计

## 6.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户界面层                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   CLI       │  │   Web UI    │  │  通知服务   │              │
│  │  (Phase 1)  │  │  (Phase 4)  │  │  (Phase 3)  │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        应用服务层                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  ArbitrageScanner                        │    │
│  │            （套利扫描器 - 主编排服务）                      │    │
│  └─────────────────────────────────────────────────────────┘    │
│         │              │              │              │          │
│         ▼              ▼              ▼              ▼          │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │
│  │  Data     │  │ Similarity│  │   LLM     │  │ Arbitrage │    │
│  │  Fetcher  │  │  Filter   │  │  Analyzer │  │  Detector │    │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        基础设施层                                │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │
│  │ Polymarket│  │  Kalshi   │  │  多LLM    │  │  Vector   │    │
│  │    API    │  │   API     │  │  提供商   │  │    DB     │    │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘    │
│       │              │              │              │            │
│       ▼              ▼              ▼              ▼            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    数据存储                              │    │
│  │         JSON Files / SQLite / PostgreSQL                │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 6.2 核心组件设计

### 6.2.1-6.2.4 核心组件概览

| 组件 | 职责 | 主要方法 | 实现 |
|------|------|----------|------|
| **DataFetcher** | 获取市场数据 | `get_markets()`, `get_events()` | PolymarketFetcher, MockFetcher |
| **SimilarityFilter** | 筛选相似市场对 | `find_similar_pairs()` | Jaccard (P1), 向量 (P2) |
| **LLMAnalyzer** | 分析逻辑关系 | `analyze_pair()`, `batch_analyze()` | 多LLM提供商 |
| **ArbitrageDetector** | 检测套利机会 | `check_exhaustive_set()`, `check_implication()`, `check_equivalent()` | 规则+LLM混合 |

**支持的LLM提供商**：

| 提供商 | 适用场景 |
|--------|----------|
| DeepSeek | 日常使用（推荐，低成本） |
| OpenAI | 高精度需求 |
| Ollama | 离线/免费 |
| 阿里云/智谱 | 国内网络 |

> 详细接口定义见源代码: `local_scanner_v2.py`, `llm_providers.py`

### 6.2.5 ArbitrageScanner - 主编排器

协调各组件完成完整扫描流程。主要方法：`scan()`, `scan_event()`, `continuous_scan()`

## 6.3 数据流设计

```
                    扫描流程数据流
                    
    ┌────────────┐
    │  开始扫描   │
    └─────┬──────┘
          │
          ▼
    ┌────────────┐     ┌─────────────────────┐
    │ DataFetcher │────▶│ List[Market]        │
    └─────┬──────┘     │ (200个活跃市场)      │
          │            └─────────────────────┘
          ▼
    ┌────────────┐     ┌─────────────────────┐
    │ 按Event分组 │────▶│ Dict[event_id,      │
    └─────┬──────┘     │      List[Market]]  │
          │            └─────────────────────┘
          │
          ├─────────────────┐
          ▼                 ▼
    ┌────────────┐    ┌────────────────┐
    │ 检测完备集  │    │ SimilarityFilter│
    │   套利     │    │                │
    └─────┬──────┘    └───────┬────────┘
          │                   │
          │                   ▼
          │           ┌─────────────────────┐
          │           │ List[(M1,M2,score)] │
          │           │ (相似市场对)         │
          │           └───────┬─────────────┘
          │                   │
          │                   ▼
          │           ┌────────────────┐
          │           │  LLMAnalyzer   │
          │           │ (多提供商支持)  │
          │           └───────┬────────┘
          │                   │
          │                   ▼
          │           ┌─────────────────────┐
          │           │ RelationshipAnalysis│
          │           │ - relationship      │
          │           │ - confidence        │
          │           │ - reasoning         │
          │           └───────┬─────────────┘
          │                   │
          │                   ▼
          │           ┌────────────────┐
          │           │ArbitrageDetector│
          │           └───────┬────────┘
          │                   │
          ▼                   ▼
    ┌─────────────────────────────────────┐
    │       List[ArbitrageOpportunity]    │
    │       - 合并所有发现的套利机会        │
    └─────────────────┬───────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────┐
    │           生成报告                   │
    │   - JSON文件                        │
    │   - 控制台输出                       │
    │   - 通知推送（可选）                  │
    └─────────────────────────────────────┘
```

## 6.4 配置管理

```python
# config.py

from dataclasses import dataclass, field
from typing import Optional
import os
import json

@dataclass
class LLMSettings:
    """LLM配置"""
    provider: str = "openai"  # openai/anthropic/deepseek/aliyun/zhipu/ollama
    model: str = ""           # 留空使用默认
    api_key: str = ""         # 留空从环境变量读取
    api_base: str = ""        # 留空使用默认
    max_tokens: int = 2000
    temperature: float = 0.7
    timeout: int = 60

@dataclass
class ScanSettings:
    """扫描配置"""
    market_limit: int = 200
    similarity_threshold: float = 0.3
    min_profit_pct: float = 2.0
    min_liquidity: float = 10000
    min_confidence: float = 0.8
    max_llm_calls: int = 30

@dataclass
class OutputSettings:
    """输出配置"""
    output_dir: str = "./output"
    cache_dir: str = "./cache"
    log_level: str = "INFO"
    detailed_log: bool = True

@dataclass
class Config:
    """主配置类"""
    llm: LLMSettings = field(default_factory=LLMSettings)
    scan: ScanSettings = field(default_factory=ScanSettings)
    output: OutputSettings = field(default_factory=OutputSettings)
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载配置"""
        return cls(
            llm=LLMSettings(
                provider=os.getenv("LLM_PROVIDER", "openai"),
                model=os.getenv("LLM_MODEL", ""),
                api_key=os.getenv("LLM_API_KEY", ""),
                api_base=os.getenv("LLM_API_BASE", ""),
            ),
            scan=ScanSettings(
                min_profit_pct=float(os.getenv("MIN_PROFIT_PCT", "2.0")),
                min_liquidity=float(os.getenv("MIN_LIQUIDITY", "10000")),
            ),
            output=OutputSettings(
                log_level=os.getenv("LOG_LEVEL", "INFO"),
            )
        )
    
    @classmethod
    def from_file(cls, path: str) -> "Config":
        """从JSON文件加载配置"""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(
            llm=LLMSettings(**data.get("llm", {})),
            scan=ScanSettings(**data.get("scan", {})),
            output=OutputSettings(**data.get("output", {})),
        )
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """加载配置（优先级：指定文件 > config.json > 环境变量）"""
        if config_path and os.path.exists(config_path):
            return cls.from_file(config_path)
        if os.path.exists("config.json"):
            return cls.from_file("config.json")
        return cls.from_env()
```

---

# 7. 数据模型设计

## 7.1 核心实体概览

| 实体 | 说明 | 核心字段 |
|------|------|----------|
| **Market** | 预测市场 | id, question, yes_price, no_price, event_id, end_date |
| **Event** | 事件（含多市场） | id, title, markets[], category |
| **RelationType** | 逻辑关系枚举 | IMPLIES_AB, IMPLIES_BA, EQUIVALENT, MUTUAL_EXCLUSIVE, EXHAUSTIVE, UNRELATED |
| **RelationshipAnalysis** | LLM分析结果 | relationship, confidence, reasoning, edge_cases |
| **ArbitrageOpportunity** | 套利机会 | type, markets[], profit_pct, action, needs_review |

### RelationType 详解

| 类型 | 符号 | 说明 | 套利条件 |
|------|------|------|----------|
| IMPLIES_AB | A → B | A发生则B必发生 | P(B) < P(A) |
| IMPLIES_BA | B → A | B发生则A必发生 | P(A) < P(B) |
| EQUIVALENT | A ≡ B | 完全等价 | |P(A) - P(B)| > 3% |
| EXHAUSTIVE | A+B+...=Ω | 完备集 | ΣP < 0.98 |

> 详细数据结构定义见源代码: `local_scanner_v2.py`

## 7.2 持久化设计

### Phase 1: JSON文件

```
output/
├── scans/
│   ├── scan_20251229_103045.json    # 单次扫描结果
│   └── scan_20251229_143022.json
├── opportunities/
│   ├── opp_impl_20251229_1.json     # 单个套利机会详情
│   └── opp_exh_20251229_2.json
└── cache/
    └── relationship_cache.json       # LLM分析缓存
```

### Phase 2+: SQLite

```sql
-- 市场表
CREATE TABLE markets (
    id TEXT PRIMARY KEY,
    question TEXT,
    yes_price REAL,
    no_price REAL,
    volume REAL,
    liquidity REAL,
    event_id TEXT,
    end_date TEXT,
    updated_at TEXT
);

-- 关系分析缓存
CREATE TABLE relationship_cache (
    market_a_id TEXT,
    market_b_id TEXT,
    relationship TEXT,
    confidence REAL,
    reasoning TEXT,
    analyzed_at TEXT,
    PRIMARY KEY (market_a_id, market_b_id)
);

-- 套利机会
CREATE TABLE opportunities (
    id TEXT PRIMARY KEY,
    type TEXT,
    markets_json TEXT,
    profit_pct REAL,
    status TEXT,
    discovered_at TEXT,
    verified_at TEXT,
    executed_at TEXT
);

-- 交易记录
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT,
    market_id TEXT,
    side TEXT,  -- buy_yes / buy_no
    price REAL,
    amount REAL,
    executed_at TEXT,
    tx_hash TEXT
);
```

---

# 8. 核心算法详解

## 8.1 相似度计算算法

### Phase 1: Jaccard相似度

```python
def jaccard_similarity(text_a: str, text_b: str) -> float:
    """
    计算两段文本的Jaccard相似度
    
    Jaccard = |A ∩ B| / |A ∪ B|
    """
    # 停用词
    stop_words = {
        'will', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 
        'of', 'by', 'be', 'is', 'are', 'was', 'were', 'been'
    }
    
    # 分词并去停用词
    words_a = set(text_a.lower().split()) - stop_words
    words_b = set(text_b.lower().split()) - stop_words
    
    if not words_a or not words_b:
        return 0.0
    
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    
    return intersection / union if union > 0 else 0.0
```

### 综合相似度

```python
def calculate_similarity(market_a: Market, market_b: Market) -> float:
    """综合相似度计算"""
    
    # 基础文本相似度
    text_sim = jaccard_similarity(market_a.question, market_b.question)
    
    # 同事件加权
    if market_a.event_id and market_a.event_id == market_b.event_id:
        text_sim += 0.4
    
    # 同结算日加权
    if market_a.end_date and market_a.end_date == market_b.end_date:
        text_sim += 0.1
    
    return min(text_sim, 1.0)
```

## 8.2 LLM分析算法

### Prompt工程

```python
ANALYSIS_PROMPT = """你是一个专门分析预测市场逻辑关系的专家。

请分析以下两个Polymarket预测市场之间的逻辑关系：

**市场A:**
- 问题: {question_a}
- 描述: {description_a}
- YES价格: ${price_a:.3f}
- 结算来源: {source_a}

**市场B:**
- 问题: {question_b}
- 描述: {description_b}
- YES价格: ${price_b:.3f}
- 结算来源: {source_b}

请判断逻辑关系类型（6选1）：
1. IMPLIES_AB: A发生→B必发生，约束P(B)≥P(A)
2. IMPLIES_BA: B发生→A必发生，约束P(A)≥P(B)
3. EQUIVALENT: A≡B，约束P(A)≈P(B)
4. MUTUAL_EXCLUSIVE: A⊕B，约束P(A)+P(B)≤1
5. EXHAUSTIVE: 完备集的一部分
6. UNRELATED: 无逻辑关系

请严格按以下JSON格式回答（不要有任何其他内容）：
```json
{{
  "relationship": "类型",
  "confidence": 0.0-1.0,
  "reasoning": "分析理由",
  "probability_constraint": "约束表达式",
  "edge_cases": ["边界情况"],
  "resolution_compatible": true或false
}}
```"""
```

## 8.3 套利检测算法

### 完备集套利检测

```python
def detect_exhaustive_arbitrage(
    markets: List[Market],
    min_profit_pct: float = 2.0
) -> Optional[ArbitrageOpportunity]:
    """
    检测完备集套利
    
    条件：Σ(YES价格) < 1.0 - 交易成本
    """
    if len(markets) < 2:
        return None
    
    # 计算总价
    total_cost = sum(m.yes_price for m in markets)
    
    # 预留2%给滑点和gas
    threshold = 0.98
    
    if total_cost >= threshold:
        return None
    
    # 计算利润
    profit = 1.0 - total_cost
    profit_pct = (profit / total_cost) * 100
    
    if profit_pct < min_profit_pct:
        return None
    
    # 生成操作建议
    actions = [
        f"买 '{m.question[:50]}...' YES @ ${m.yes_price:.3f}"
        for m in markets
    ]
    
    return ArbitrageOpportunity(
        id=generate_id("exhaustive"),
        type="EXHAUSTIVE_SET_UNDERPRICED",
        markets=[market_to_dict(m) for m in markets],
        relationship="exhaustive",
        total_cost=total_cost,
        guaranteed_return=1.0,
        profit=profit,
        profit_pct=profit_pct,
        action="\n".join(actions),
        confidence=0.85,
        needs_review=[
            "确认这些选项互斥且覆盖所有可能",
            "检查结算规则是否一致",
            "确认没有遗漏的选项"
        ],
        discovered_at=datetime.now().isoformat()
    )
```

### 包含关系套利检测

```python
def detect_implication_arbitrage(
    market_a: Market,
    market_b: Market,
    analysis: RelationshipAnalysis,
    min_profit_pct: float = 2.0
) -> Optional[ArbitrageOpportunity]:
    """
    检测包含关系套利
    
    如果 A → B，则 P(B) ≥ P(A)
    如果 P(B) < P(A)，存在套利
    
    操作：买B的YES，买A的NO
    成本：P(B) + (1-P(A))
    回报：无论结果如何，至少得到$1
    """
    
    if analysis.relationship == RelationType.IMPLIES_AB:
        implying = market_a  # 蕴含方
        implied = market_b   # 被蕴含方
    elif analysis.relationship == RelationType.IMPLIES_BA:
        implying = market_b
        implied = market_a
    else:
        return None
    
    # 检查是否违反约束
    if implied.yes_price >= implying.yes_price - 0.01:
        return None  # 定价正确，无套利
    
    # 计算套利
    cost = implied.yes_price + implying.no_price
    profit = 1.0 - cost
    profit_pct = (profit / cost) * 100 if cost > 0 else 0
    
    if profit_pct < min_profit_pct:
        return None
    
    if analysis.confidence < 0.8:
        return None
    
    return ArbitrageOpportunity(
        id=generate_id("implication"),
        type="IMPLICATION_VIOLATION",
        markets=[
            market_to_dict(implied),
            market_to_dict(implying)
        ],
        relationship=analysis.relationship.value,
        total_cost=cost,
        guaranteed_return=1.0,
        profit=profit,
        profit_pct=profit_pct,
        action=f"买 '{implied.question[:50]}...' YES @ ${implied.yes_price:.3f}\n"
               f"买 '{implying.question[:50]}...' NO @ ${implying.no_price:.3f}",
        confidence=analysis.confidence,
        reasoning=analysis.reasoning,
        edge_cases=analysis.edge_cases,
        needs_review=[
            "验证逻辑关系确实成立",
            "检查结算规则是否兼容",
        ],
        discovered_at=datetime.now().isoformat()
    )
```

### 利润计算公式汇总

| 套利类型 | 成本公式 | 回报公式 | 利润公式 |
|----------|----------|----------|----------|
| 完备集 | Σ(YES_i) | 1.00 | 1.00 - Σ(YES_i) |
| 包含关系 A→B | YES_B + NO_A | 1.00 | 1.00 - (YES_B + NO_A) |
| 等价市场 | YES_cheap + NO_expensive | 1.00 | 1.00 - (YES_cheap + NO_expensive) |
| 跨平台 | YES_A + NO_B - fees | 1.00 | 1.00 - cost |

---

# 9. API与外部依赖

## 9.1 Polymarket API

### Gamma API（市场数据）

**Base URL**: `https://gamma-api.polymarket.com`

#### 获取市场列表

```http
GET /markets
```

**参数**：
| 参数 | 类型 | 说明 |
|------|------|------|
| limit | int | 返回数量，默认100 |
| active | bool | 是否只返回活跃市场 |
| closed | bool | 是否包含已关闭市场 |
| order | string | 排序字段（volume/liquidity/created） |
| ascending | bool | 升序/降序 |

**响应示例**：
```json
[
  {
    "id": "0x...",
    "question": "Will Trump win the 2028 election?",
    "description": "...",
    "outcomes": "[\"Yes\",\"No\"]",
    "outcomePrices": "[\"0.55\",\"0.45\"]",
    "volume": "5000000",
    "liquidity": "500000",
    "endDate": "2028-11-05T00:00:00Z",
    "eventSlug": "2028-us-election",
    "conditionId": "0x...",
    "resolutionSource": "AP News"
  }
]
```

## 9.2 LLM API（多提供商支持）

### 9.2.1 支持的提供商

| 提供商 | 环境变量 | 默认模型 | API Base |
|--------|----------|----------|----------|
| **OpenAI** | `OPENAI_API_KEY` | gpt-4o | api.openai.com |
| **Anthropic** | `ANTHROPIC_API_KEY` | claude-sonnet-4-20250514 | api.anthropic.com |
| **DeepSeek** | `DEEPSEEK_API_KEY` | deepseek-chat | api.deepseek.com |
| **阿里云通义** | `DASHSCOPE_API_KEY` | qwen-plus | dashscope.aliyuncs.com |
| **智谱GLM** | `ZHIPU_API_KEY` | glm-4-plus | open.bigmodel.cn |
| **Ollama** | (本地运行) | llama3.1:8b | localhost:11434 |
| **OpenAI兼容** | `LLM_API_KEY` + `LLM_API_BASE` | 自定义 | 自定义 |

### 9.2.2 统一调用接口

```python
from llm_providers import create_llm_client

# 方式1: 自动检测（根据环境变量）
client = create_llm_client()

# 方式2: 指定提供商
client = create_llm_client(provider="openai", model="gpt-4o")
client = create_llm_client(provider="deepseek", model="deepseek-chat")
client = create_llm_client(provider="aliyun", model="qwen-max")

# 方式3: 使用本地Ollama
client = create_llm_client(provider="ollama", model="llama3.1:70b")

# 方式4: 自定义OpenAI兼容接口（如vLLM, OneAPI）
client = create_llm_client(
    provider="openai_compatible",
    api_base="http://my-server:8000/v1",
    model="my-model"
)

# 统一的调用方式
response = client.chat("你好")
print(response.content)

# 带系统提示词
response = client.chat(
    message="分析这两个市场的关系",
    system_prompt="你是一个预测市场分析专家"
)

# 清理资源
client.close()
```

### 9.2.3 成本估算

| 提供商 | 模型 | 输入价格 | 输出价格 | 每次分析估算 |
|--------|------|----------|----------|--------------|
| OpenAI | gpt-4o | $2.5/M | $10/M | ~$0.008 |
| OpenAI | gpt-4o-mini | $0.15/M | $0.6/M | ~$0.0005 |
| Anthropic | Claude Sonnet | $3/M | $15/M | ~$0.01 |
| Anthropic | Claude Haiku | $0.25/M | $1.25/M | ~$0.001 |
| **DeepSeek** | deepseek-chat | ¥1/M | ¥2/M | **~¥0.002** |
| 阿里云 | qwen-plus | ¥0.8/M | ¥2/M | ~¥0.002 |
| 智谱 | glm-4-plus | ¥50/M | ¥50/M | ~¥0.05 |
| **Ollama** | llama3.1:8b | 免费 | 免费 | **$0** |

**推荐配置**：
- **开发测试**：Ollama本地模型（免费）或 DeepSeek（极低成本）
- **生产环境**：DeepSeek 或 Claude Haiku（平衡成本与效果）
- **高精度需求**：GPT-4o 或 Claude Sonnet

### 9.2.4 提供商选择建议

| 场景 | 推荐提供商 | 理由 |
|------|------------|------|
| 国内网络 | DeepSeek / 阿里云 | 无需代理，延迟低 |
| 成本敏感 | Ollama / DeepSeek | 免费或极低成本 |
| 效果优先 | OpenAI / Anthropic | 逻辑推理能力强 |
| 离线环境 | Ollama | 本地运行，无需网络 |
| 企业部署 | OpenAI兼容接口 | 可对接内部模型服务 |

## 9.3 Kalshi API（Phase 3）

**Base URL**: `https://trading-api.kalshi.com/trade-api/v2`

> 需要申请API Key，仅限美国用户

## 9.4 依赖库

### 核心依赖

```
requests>=2.28.0       # HTTP客户端
httpx>=0.24.0          # 异步HTTP客户端（LLM调用）
python-dotenv>=1.0.0   # 环境变量管理
```

### LLM提供商依赖（按需安装）

```
# 使用httpx即可支持所有OpenAI兼容接口
# 以下SDK是可选的

# OpenAI
openai>=1.0.0

# Anthropic
anthropic>=0.18.0

# 阿里云通义
dashscope>=1.10.0

# 智谱GLM
zhipuai>=2.0.0
```

### Phase 2扩展

```
sentence-transformers>=2.2.0   # 文本嵌入
chromadb>=0.4.0               # 向量数据库
numpy>=1.24.0                 # 数值计算
```

---

# 10. 开发路线图

## 10.1 Phase 1: MVP验证 ✅

**目标**：验证核心策略可行性
**时间**：1周
**状态**：已完成

### 任务清单

- [x] T1.1 设计数据模型
- [x] T1.2 实现模拟数据源
- [x] T1.3 实现关键词相似度筛选
- [x] T1.4 实现规则匹配分析（LLM备用）
- [x] T1.5 实现完备集套利检测
- [x] T1.6 实现包含关系套利检测
- [x] T1.7 实现报告生成
- [x] T1.8 实现多LLM提供商支持
- [x] T1.9 编写项目文档

### 交付物

- [x] `polymarket_arb_mvp.py` - MVP完整脚本
- [x] `local_scanner_v2.py` - 支持多LLM的扫描器
- [x] `llm_providers.py` - LLM提供商抽象层
- [x] `config.py` - 配置管理
- [x] `README.md` - 基础文档
- [x] `PROJECT_BIBLE.md` - 完整项目文档

## 10.2 Phase 2: 真实数据验证

**目标**：在真实市场数据上验证
**时间**：1-2周
**状态**：进行中

### 任务清单

- [ ] T2.1 实现Polymarket API客户端
- [ ] T2.2 测试API连接和数据解析
- [ ] T2.3 在真实数据上运行扫描
- [ ] T2.4 手动验证发现的机会
- [ ] T2.5 优化Prompt提高准确率
- [ ] T2.6 添加分析结果缓存

### 验收标准

- 能够成功连接Polymarket API
- 每次扫描能发现至少1个潜在机会
- LLM分析准确率≥70%（人工验证）

## 10.3 Phase 3: 优化与扩展

**目标**：提高效率和覆盖面
**时间**：2-3周
**状态**：计划中

### 任务清单

- [ ] T3.1 实现向量相似度筛选（sentence-transformers + Chroma）
- [ ] T3.2 实现WebSocket实时监控
- [ ] T3.3 实现定时扫描
- [ ] T3.4 实现通知功能（Telegram/微信）
- [ ] T3.5 实现Kalshi API客户端
- [ ] T3.6 实现跨平台套利检测
- [ ] T3.7 实现历史回测

## 10.4 Phase 4: 自动化执行

**目标**：实现半自动/全自动执行
**时间**：3-4周
**状态**：计划中

### 任务清单

- [ ] T4.1 设计执行引擎
- [ ] T4.2 实现Polymarket交易接口
- [ ] T4.3 实现钱包管理
- [ ] T4.4 实现风控模块
- [ ] T4.5 实现半自动执行（确认后执行）
- [ ] T4.6 实现小额全自动执行
- [ ] T4.7 实现交易记录和追踪
- [ ] T4.8 实现盈亏统计

## 10.5 里程碑

```
2024/12/29 ─── M1: MVP完成 ✅
     │
     ├─ Phase 2 开始
     │
2025/01/15 ─── M2: 真实数据验证完成
     │
     ├─ Phase 3 开始
     │
2025/02/15 ─── M3: 优化扩展完成
     │
     ├─ Phase 4 开始
     │
2025/03/31 ─── M4: 自动化执行完成
```

---

# 11. 测试策略

## 11.1 测试层次

| 层次 | 验证内容 | 示例 |
|------|----------|------|
| 单元测试 | 函数逻辑 | 相似度计算、套利检测逻辑 |
| 集成测试 | 组件交互 | LLM分析 + 套利检测联动 |
| E2E测试 | 完整流程 | 数据获取 → 分析 → 输出报告 |

> 测试文件位于 `tests/` 目录

---

# 12. 风险管理

## 12.1 风险矩阵

| 风险类型 | 可能性 | 影响 | 风险等级 | 缓解措施 |
|----------|--------|------|----------|----------|
| 逻辑关系误判 | 中 | 高 | 🔴高 | 人工复核、LLM多次验证 |
| 结算规则差异 | 中 | 高 | 🔴高 | 仔细阅读规则、只做熟悉的市场 |
| Oracle操纵 | 低 | 高 | 🟡中 | 分散投资、关注UMA治理 |
| 流动性不足 | 中 | 中 | 🟡中 | 检查深度、分批执行 |
| API变更 | 低 | 中 | 🟢低 | 版本监控、及时适配 |
| 平台风险 | 低 | 高 | 🟡中 | 不存大额、及时提现 |

## 12.2 仓位管理规则

```python
# 风控参数
MAX_SINGLE_POSITION = 0.10      # 单笔最大仓位（占总资金）
MAX_DAILY_EXPOSURE = 0.30       # 日最大敞口
MAX_EVENT_EXPOSURE = 0.20       # 单事件最大敞口
MIN_LIQUIDITY_RATIO = 0.10      # 仓位不超过市场流动性的10%
```

## 12.3 人工复核清单

每个套利机会执行前，必须完成以下复核：

```markdown
## 套利机会复核清单

### 逻辑验证 ✓/✗
- [ ] LLM判断的逻辑关系我理解并认同
- [ ] 我能用自己的话解释为什么这个关系成立
- [ ] 我考虑过所有边界情况

### 结算规则验证 ✓/✗
- [ ] 我已阅读所有相关市场的结算规则
- [ ] 结算数据来源一致
- [ ] 结算时间接近（≤24小时差异）
- [ ] 不存在可能导致两边都输的情况

### 流动性验证 ✓/✗
- [ ] 我检查了订单簿深度
- [ ] 我的仓位≤市场流动性的10%

### 风控验证 ✓/✗
- [ ] 单笔仓位≤总资金10%
- [ ] 今日总敞口≤总资金30%
- [ ] 我能承受最坏情况的亏损
```

---

# 13. 运维与监控

## 13.1 部署方式

| 阶段 | 方式 | 说明 |
|------|------|------|
| Phase 1-3 | 本地运行 | 手动或crontab定时扫描 |
| Phase 4+ | 服务器部署 | 持续监控模式 |

> 输出目录：`output/` 定时任务：每小时扫描

---

# 14. 扩展计划

## 14.1 新套利类型

| 类型 | 说明 | 状态 |
|------|------|------|
| **合成套利** | 区间/阈值市场组合等价于单一市场的价差 | 🔄 T7整合中 |
| 时间套利 | 同一事件不同时间点市场价差 | ⏳ 待规划 |
| 跨平台套利 | Polymarket vs Myriad等去中心化平台 | ⏳ 待评估 |

### 合成套利示例
```
市场 A: "BTC > $100k"              YES = $0.65
市场 B3: "BTC $100k-$110k"         YES = $0.12
市场 B4: "BTC > $110k"             YES = $0.08
                                   ─────────
合成 (B3 + B4) ≡ A                 合计 = $0.20

套利空间: $0.65 - $0.20 = $0.45
```

## 14.2 平台扩展（非美国用户）

| 平台 | 说明 | 优先级 |
|------|------|--------|
| **Myriad** | 去中心化，BNB Chain | P1 |
| Drift BET | 去中心化，Solana | P2 |
| ~~Kalshi/PredictIt~~ | 需美国身份 | 不可用 |

---

# 15. 创意池

> 本章记录尚未纳入正式计划的创意和点子，待讨论确认后可纳入开发。

## 15.1 待评估的创意

| ID | 创意描述 | 来源 | 状态 | 备注 |
|----|----------|------|------|------|
| I001 | 多LLM交叉验证 - 使用多个模型验证关系判断 | 初始想法 | 待评估 | 提高准确率 |
| I002 | 历史套利模式库 - 记录成功的套利模式用于快速匹配 | 初始想法 | 待评估 | 减少LLM调用 |
| I003 | 事件关联图谱 - 构建市场间的关系图谱 | 初始想法 | 待评估 | 可视化分析 |

## 15.2 已采纳的创意

| ID | 创意描述 | 采纳日期 | 纳入阶段 |
|----|----------|----------|----------|
| - | - | - | - |

## 15.3 已否决的创意

| ID | 创意描述 | 否决原因 | 否决日期 |
|----|----------|----------|----------|
| - | - | - | - |

---

# 16. 附录

## 16.1 术语表

| 术语 | 英文 | 定义 |
|------|------|------|
| 套利 | Arbitrage | 利用价格差异获取无风险利润 |
| 完备集 | Exhaustive Set | 覆盖所有可能结果的互斥选项集合 |
| 包含关系 | Implication | A发生必然导致B发生的逻辑关系 |
| 预言机 | Oracle | 向区块链提供链外数据的机制 |
| 流动性 | Liquidity | 市场中可交易的资金量 |
| 滑点 | Slippage | 预期价格与实际成交价的差异 |

## 16.2 常用命令

### 基本运行

```bash
# 运行扫描（自动检测LLM提供商）
python local_scanner_v2.py

# 指定配置文件
python local_scanner_v2.py --config=config.json

# 调试模式
LOG_LEVEL=DEBUG python local_scanner_v2.py
```

### 不同LLM提供商

```bash
# 使用OpenAI
export OPENAI_API_KEY="sk-..."
python local_scanner_v2.py

# 使用DeepSeek（推荐，低成本）
export DEEPSEEK_API_KEY="sk-..."
export LLM_PROVIDER=deepseek
python local_scanner_v2.py

# 使用阿里云通义千问
export DASHSCOPE_API_KEY="sk-..."
export LLM_PROVIDER=aliyun
python local_scanner_v2.py

# 使用本地Ollama（免费）
ollama serve
ollama pull llama3.1:8b
export LLM_PROVIDER=ollama
python local_scanner_v2.py
```

### 配置文件示例

```json
{
  "llm": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "max_tokens": 2000,
    "temperature": 0.7
  },
  "scan": {
    "market_limit": 200,
    "min_profit_pct": 2.0,
    "min_liquidity": 10000,
    "min_confidence": 0.8
  },
  "output": {
    "output_dir": "./output",
    "log_level": "INFO"
  }
}
```

## 16.3 常见问题

### Q: API请求失败怎么办？

A: 检查网络连接，Polymarket API可能需要科学上网。也可能是请求频率过高被限制。

### Q: LLM分析不准确怎么办？

A: 
1. 检查Prompt是否清晰
2. 提高置信度阈值
3. 所有机会都人工复核
4. 尝试更强的模型（如GPT-4o）

### Q: 发现机会后如何执行？

A:
1. 按照报告中的操作步骤
2. 在Polymarket网站手动下单
3. 先小额测试（$10-50）
4. 确认流程后再放大仓位

### Q: 如何选择LLM提供商？

A:
- **开发测试**：Ollama（免费）
- **日常使用**：DeepSeek（低成本，效果好）
- **高精度需求**：GPT-4o或Claude Sonnet
- **国内网络**：DeepSeek或阿里云

## 16.4 参考资源

### 学术研究

1. IMDEA Networks Institute (2025). "Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets"
   - arXiv: https://arxiv.org/abs/2508.03474

### 官方文档

1. Polymarket API: https://docs.polymarket.com/
2. Polymarket CLOB: https://github.com/Polymarket/py-clob-client
3. Anthropic Claude API: https://docs.anthropic.com/

### 社区资源

1. PolyTrack: https://polytrackhq.app/
2. Polymarket Analytics: https://polymarketanalytics.com/

---

# 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0 | 2024-12-29 | 初始版本 |
| 1.1 | 2024-12-29 | 添加多LLM提供商支持，完善文档结构 |
| 1.2 | 2024-12-30 | 添加开发准则、进度追踪、创意池章节，重新组织章节编号 |

---

**免责声明**: 
本项目仅供学习研究使用。预测市场交易有风险，套利策略也存在执行风险。
请自行评估风险并承担后果。本文档不构成投资建议。
