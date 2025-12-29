# Polymarket 组合套利系统

## 项目圣经 v1.0

> 本文档是项目的核心参考，包含需求定义、策略说明、技术设计、开发路线图和运维指南。
> 所有开发决策应参照本文档执行。

---

# 目录

1. [项目概述](#1-项目概述)
2. [市场背景与策略分析](#2-市场背景与策略分析)
3. [核心需求定义](#3-核心需求定义)
4. [系统架构设计](#4-系统架构设计)
5. [数据模型设计](#5-数据模型设计)
6. [核心算法详解](#6-核心算法详解)
7. [API与外部依赖](#7-api与外部依赖)
8. [开发路线图](#8-开发路线图)
9. [测试策略](#9-测试策略)
10. [风险管理](#10-风险管理)
11. [运维与监控](#11-运维与监控)
12. [扩展计划](#12-扩展计划)
13. [附录](#13-附录)

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

### 短期目标（Phase 1-2，1-2个月）
- [x] 验证核心策略可行性
- [x] 构建MVP原型
- [ ] 在真实市场中发现并验证套利机会
- [ ] 实现小额（$100-500）手动执行的工作流

### 中期目标（Phase 3-4，3-6个月）
- [ ] 实现半自动化执行
- [ ] 建立历史回测系统
- [ ] 达到稳定正收益

### 长期目标（Phase 5+，6个月以上）
- [ ] 全自动化运行
- [ ] 扩展到多平台套利
- [ ] 资金规模达到$10,000+

## 1.3 成功指标

| 指标 | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|
| 每周发现机会数 | ≥1 | ≥3 | ≥5 |
| 机会验证准确率 | ≥50% | ≥70% | ≥85% |
| 执行成功率 | - | ≥80% | ≥95% |
| 月化收益率 | - | ≥5% | ≥10% |

## 1.4 项目边界

### 在范围内 ✅
- Polymarket平台内的组合套利
- Polymarket与Kalshi的跨平台套利
- 完备集套利、包含关系套利、等价市场套利
- 手动/半自动执行

### 不在范围内 ❌
- 基于预测的方向性交易（不是套利）
- 高频毫秒级套利（需要专业基础设施）
- 做空策略（Polymarket不支持）
- 杠杆交易

---

# 2. 市场背景与策略分析

## 2.1 Polymarket平台概述

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
│   ├── YES Token
│   └── NO Token
├── Market 2（市场2）: "Trump wins by 1-49?"
│   ├── YES Token
│   └── NO Token
└── Market 3（市场3）: "Trump wins by 50+?"
    ├── YES Token
    └── NO Token
```

### 定价机制

- 订单簿模式（非AMM）
- 价格范围：$0.00 - $1.00
- 结算：YES赢得支付$1.00，NO赢得支付$1.00
- 理论上：P(YES) + P(NO) = 1.00

## 2.2 套利机会来源分析

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

| 策略类型 | 机器人竞争 | 个人机会 | 说明 |
|----------|------------|----------|------|
| 单市场套利 | 🔴极高 | ❌几乎无 | 毫秒级消失 |
| 收盘扫货 | 🟡中等 | ⚠️有限 | 大户操纵风险 |
| **组合套利** | 🟢低 | ✅有 | 需要逻辑判断 |
| **做市** | 🟢低 | ✅有 | 需要资金和策略 |
| **跨平台套利** | 🟢低 | ✅有 | 需要多平台资金 |

### 选择组合套利的理由

1. **机器人最难做** —— 需要语义理解和逻辑推理
2. **LLM赋能** —— 大语言模型在这方面有优势
3. **资金门槛低** —— $500即可开始
4. **风险可控** —— 理论上无风险（需验证逻辑正确）
5. **可复用** —— 找到模式后可反复应用

## 2.3 组合套利策略详解

### 2.3.1 完备集套利（Exhaustive Set Arbitrage）

**定义**：一组互斥且覆盖所有可能结果的市场，其价格总和应该等于$1.00。

**套利条件**：Σ(YES价格) < $1.00

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

### 2.3.2 包含关系套利（Implication Arbitrage）

**定义**：如果事件A发生必然导致事件B发生（A → B），那么P(B) ≥ P(A)。

**套利条件**：P(B) < P(A) - ε（ε为交易成本）

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

### 2.3.3 等价市场套利（Equivalent Market Arbitrage）

**定义**：两个市场本质上问的是同一个问题，只是表述不同。

**套利条件**：|P(A) - P(B)| > ε

**示例**：

```
市场A: "Will Trump win the 2024 election?"    YES = $0.52
市场B: "Trump victory November 2024?"         YES = $0.48

价差: 4%

操作:
- 买低价市场YES
- 买高价市场NO
```

### 2.3.4 跨平台套利（Cross-Platform Arbitrage）

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

## 2.4 研究数据支撑

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

---

# 3. 核心需求定义

## 3.1 功能需求

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
| FR-002-6 | 缓存已分析的市场对关系 | P1 | 2 |
| FR-002-7 | 支持人工标注和修正 | P2 | 3 |

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

## 3.2 非功能需求

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

## 3.3 用户故事

### US-001: 首次使用

```
作为一个新用户
我想要快速验证系统是否能在我的环境运行
以便我确定是否继续投入时间学习

验收标准:
- 运行setup.sh后，系统提示成功
- 运行MVP脚本，看到模拟数据扫描结果
- 整个过程<5分钟
```

### US-002: 日常扫描

```
作为一个日常使用者
我想要每天运行一次扫描并查看机会
以便我不错过潜在的套利机会

验收标准:
- 一条命令启动扫描
- 扫描完成后输出清晰的机会列表
- 每个机会标注利润率和风险点
- 报告保存到文件供后续参考
```

### US-003: 发现机会后执行

```
作为一个发现了套利机会的用户
我想要知道具体如何执行这个套利
以便我能够捕获利润

验收标准:
- 系统提供具体的买入指令
- 标明每个市场的当前价格
- 提供直接链接到Polymarket
- 列出需要人工确认的检查项
```

### US-004: 验证逻辑关系

```
作为一个谨慎的交易者
我想要验证LLM判断的逻辑关系是否正确
以便我确保这真的是无风险套利

验收标准:
- 能看到LLM的完整推理过程
- 能看到可能的边界情况
- 能看到结算规则的兼容性分析
- 能手动标记"已验证"或"有问题"
```

---

# 4. 系统架构设计

## 4.1 整体架构

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
│  │ Polymarket│  │  Kalshi   │  │  Claude   │  │  Vector   │    │
│  │    API    │  │   API     │  │   API     │  │    DB     │    │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘    │
│       │              │              │              │            │
│       ▼              ▼              ▼              ▼            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    数据存储                              │    │
│  │         JSON Files / SQLite / PostgreSQL                │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 4.2 核心组件设计

### 4.2.1 DataFetcher - 数据获取器

**职责**：从外部数据源获取市场数据

```python
class DataFetcher:
    """数据获取器接口"""
    
    def get_markets(self, limit: int = 100) -> List[Market]:
        """获取市场列表"""
        pass
    
    def get_market_by_id(self, market_id: str) -> Optional[Market]:
        """获取单个市场详情"""
        pass
    
    def get_events(self, limit: int = 50) -> List[Event]:
        """获取事件列表"""
        pass
    
    def get_markets_by_event(self, event_id: str) -> List[Market]:
        """获取事件下所有市场"""
        pass
    
    def subscribe_price_updates(self, market_ids: List[str], callback):
        """订阅价格更新（WebSocket）"""
        pass
```

**实现**：
- `PolymarketFetcher`: Polymarket Gamma API
- `KalshiFetcher`: Kalshi API（Phase 3）
- `MockFetcher`: 模拟数据（测试用）

### 4.2.2 SimilarityFilter - 相似度筛选器

**职责**：找出可能存在逻辑关系的市场对

```python
class SimilarityFilter:
    """相似度筛选器接口"""
    
    def find_similar_pairs(
        self, 
        markets: List[Market],
        threshold: float = 0.3
    ) -> List[Tuple[Market, Market, float]]:
        """
        找出相似的市场对
        返回: [(market_a, market_b, similarity_score), ...]
        """
        pass
    
    def get_embedding(self, text: str) -> np.ndarray:
        """获取文本向量表示"""
        pass
```

**实现**：
- `KeywordSimilarityFilter`: 关键词Jaccard相似度（Phase 1）
- `EmbeddingSimilarityFilter`: 向量相似度 + Chroma（Phase 2）

### 4.2.3 LLMAnalyzer - LLM分析器

**职责**：分析两个市场之间的逻辑关系

```python
class LLMAnalyzer:
    """LLM分析器接口"""
    
    def analyze_pair(
        self, 
        market_a: Market, 
        market_b: Market
    ) -> RelationshipAnalysis:
        """
        分析两个市场的逻辑关系
        返回: 关系类型、置信度、推理过程、边界情况
        """
        pass
    
    def batch_analyze(
        self,
        pairs: List[Tuple[Market, Market]]
    ) -> List[RelationshipAnalysis]:
        """批量分析"""
        pass
```

**实现**：
- `ClaudeAnalyzer`: 调用Claude API
- `RuleBasedAnalyzer`: 规则匹配（备用）
- `CachedAnalyzer`: 带缓存的分析器

### 4.2.4 ArbitrageDetector - 套利检测器

**职责**：根据逻辑关系和价格检测套利机会

```python
class ArbitrageDetector:
    """套利检测器"""
    
    def check_exhaustive_set(
        self, 
        markets: List[Market]
    ) -> Optional[ArbitrageOpportunity]:
        """检测完备集套利"""
        pass
    
    def check_implication(
        self,
        market_a: Market,
        market_b: Market,
        analysis: RelationshipAnalysis
    ) -> Optional[ArbitrageOpportunity]:
        """检测包含关系套利"""
        pass
    
    def check_equivalent(
        self,
        market_a: Market,
        market_b: Market,
        analysis: RelationshipAnalysis
    ) -> Optional[ArbitrageOpportunity]:
        """检测等价市场套利"""
        pass
    
    def check_cross_platform(
        self,
        poly_market: Market,
        kalshi_market: Market
    ) -> Optional[ArbitrageOpportunity]:
        """检测跨平台套利"""
        pass
```

### 4.2.5 ArbitrageScanner - 主编排器

**职责**：协调各组件完成完整扫描流程

```python
class ArbitrageScanner:
    """主扫描器"""
    
    def __init__(
        self,
        fetcher: DataFetcher,
        filter: SimilarityFilter,
        analyzer: LLMAnalyzer,
        detector: ArbitrageDetector
    ):
        pass
    
    def scan(self) -> List[ArbitrageOpportunity]:
        """执行完整扫描"""
        pass
    
    def scan_event(self, event_id: str) -> List[ArbitrageOpportunity]:
        """扫描单个事件"""
        pass
    
    def continuous_scan(self, interval_seconds: int = 3600):
        """持续扫描模式"""
        pass
```

## 4.3 数据流设计

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
          │           │                │
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

## 4.4 配置管理

```python
# config.py

from dataclasses import dataclass
from typing import Optional
import os

@dataclass
class Config:
    """系统配置"""
    
    # API配置
    polymarket_api: str = "https://gamma-api.polymarket.com"
    kalshi_api: str = "https://trading-api.kalshi.com"
    anthropic_api_key: Optional[str] = None
    
    # 扫描配置
    market_limit: int = 200
    similarity_threshold: float = 0.3
    min_profit_pct: float = 2.0
    min_liquidity: float = 10000
    min_confidence: float = 0.8
    max_llm_calls_per_scan: int = 30
    
    # LLM配置
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 1500
    
    # 存储配置
    output_dir: str = "./output"
    cache_dir: str = "./cache"
    
    # 日志配置
    log_level: str = "INFO"
    detailed_log: bool = True
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载配置"""
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            min_profit_pct=float(os.getenv("MIN_PROFIT_PCT", "2.0")),
            min_liquidity=float(os.getenv("MIN_LIQUIDITY", "10000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
    
    @classmethod
    def from_file(cls, path: str) -> "Config":
        """从配置文件加载"""
        import json
        with open(path) as f:
            data = json.load(f)
        return cls(**data)
```

---

# 5. 数据模型设计

## 5.1 核心实体

### Market - 市场

```python
@dataclass
class Market:
    """预测市场"""
    
    # 标识
    id: str                      # 市场ID
    condition_id: str            # 条件ID（用于交易）
    
    # 基本信息
    question: str                # 市场问题
    description: str             # 详细描述
    outcomes: List[str]          # 可能的结果 ["Yes", "No"]
    
    # 价格信息
    yes_price: float             # YES当前价格 (0-1)
    no_price: float              # NO当前价格 (0-1)
    
    # 流动性信息
    volume: float                # 总交易量 (USDC)
    liquidity: float             # 当前流动性 (USDC)
    
    # 时间信息
    end_date: str                # 结算日期
    created_at: str              # 创建时间
    
    # 关联信息
    event_id: str                # 所属事件ID
    event_title: str             # 事件标题
    
    # 结算信息
    resolution_source: str       # 结算数据来源
    resolution_rules: str        # 结算规则
    
    # 状态
    is_active: bool = True       # 是否活跃
    is_closed: bool = False      # 是否已关闭
    outcome: Optional[str] = None  # 结算结果
```

### Event - 事件

```python
@dataclass
class Event:
    """事件（包含多个相关市场）"""
    
    id: str                      # 事件ID/slug
    title: str                   # 事件标题
    description: str             # 事件描述
    markets: List[Market]        # 关联市场
    end_date: str                # 结束日期
    category: str                # 分类（politics/sports/crypto等）
    total_volume: float          # 总交易量
```

### RelationshipAnalysis - 关系分析结果

```python
class RelationType(Enum):
    """逻辑关系类型"""
    IMPLIES_AB = "implies_ab"          # A → B
    IMPLIES_BA = "implies_ba"          # B → A
    EQUIVALENT = "equivalent"          # A ≡ B
    MUTUAL_EXCLUSIVE = "mutual_exclusive"  # A ⊕ B
    EXHAUSTIVE = "exhaustive"          # A + B + ... = Ω
    UNRELATED = "unrelated"            # 无关

@dataclass
class RelationshipAnalysis:
    """LLM分析结果"""
    
    # 关系判断
    relationship: RelationType
    confidence: float            # 0-1
    
    # 推理过程
    reasoning: str               # 分析理由
    probability_constraint: str  # 概率约束，如 "P(B) >= P(A)"
    
    # 验证信息
    current_prices_valid: bool   # 当前定价是否符合逻辑
    arbitrage_exists: bool       # 是否存在套利
    
    # 风险信息
    edge_cases: List[str]        # 边界情况
    resolution_compatible: bool  # 结算规则是否兼容
    resolution_notes: str        # 结算规则说明
    
    # 元信息
    analyzed_at: str             # 分析时间
    model_used: str              # 使用的模型
```

### ArbitrageOpportunity - 套利机会

```python
@dataclass
class ArbitrageOpportunity:
    """套利机会"""
    
    # 标识
    id: str                      # 机会ID
    type: str                    # 类型（exhaustive/implication/equivalent/cross_platform）
    
    # 市场信息
    markets: List[Dict]          # 涉及的市场 [{id, question, yes_price}, ...]
    relationship: str            # 逻辑关系
    
    # 财务信息
    total_cost: float            # 总成本
    guaranteed_return: float     # 保证回报
    profit: float                # 利润
    profit_pct: float            # 利润率
    
    # 执行信息
    action: str                  # 具体操作步骤
    
    # 分析信息
    confidence: float            # LLM置信度
    reasoning: str               # 分析理由
    edge_cases: List[str]        # 边界情况
    
    # 复核信息
    needs_review: List[str]      # 需要人工复核的项目
    
    # 元信息
    discovered_at: str           # 发现时间
    status: str = "pending"      # pending/verified/executed/expired
```

## 5.2 持久化设计

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

# 6. 核心算法详解

## 6.1 相似度计算算法

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

### Phase 2: 向量相似度

```python
from sentence_transformers import SentenceTransformer
import numpy as np

class EmbeddingSimilarity:
    def __init__(self, model_name: str = "intfloat/e5-large-v2"):
        self.model = SentenceTransformer(model_name)
    
    def cosine_similarity(self, text_a: str, text_b: str) -> float:
        """
        计算余弦相似度
        
        cos(θ) = (A · B) / (|A| × |B|)
        """
        emb_a = self.model.encode(text_a)
        emb_b = self.model.encode(text_b)
        
        dot_product = np.dot(emb_a, emb_b)
        norm_a = np.linalg.norm(emb_a)
        norm_b = np.linalg.norm(emb_b)
        
        return dot_product / (norm_a * norm_b)
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
    
    # 同类别加权（如都是政治类）
    # ...
    
    return min(text_sim, 1.0)
```

## 6.2 LLM分析算法

### Prompt工程

```python
ANALYSIS_PROMPT = """
你是一个专门分析预测市场逻辑关系的专家。请分析以下两个市场：

**市场A:** {question_a}
- 描述: {description_a}
- YES价格: ${price_a}
- 结算源: {source_a}

**市场B:** {question_b}
- 描述: {description_b}
- YES价格: ${price_b}
- 结算源: {source_b}

请判断逻辑关系类型（6选1）：
1. IMPLIES_AB: A发生→B必发生，约束P(B)≥P(A)
2. IMPLIES_BA: B发生→A必发生，约束P(A)≥P(B)
3. EQUIVALENT: A≡B，约束P(A)≈P(B)
4. MUTUAL_EXCLUSIVE: A⊕B，约束P(A)+P(B)≤1
5. EXHAUSTIVE: 完备集的一部分
6. UNRELATED: 无逻辑关系

返回JSON格式：
{
  "relationship": "类型",
  "confidence": 0.0-1.0,
  "reasoning": "分析理由",
  "probability_constraint": "约束表达式",
  "edge_cases": ["边界情况列表"],
  "resolution_compatible": true/false
}
"""
```

### 响应解析

```python
def parse_llm_response(response: str) -> RelationshipAnalysis:
    """解析LLM响应"""
    
    # 提取JSON
    if "```json" in response:
        json_str = response.split("```json")[1].split("```")[0]
    elif "```" in response:
        json_str = response.split("```")[1].split("```")[0]
    else:
        json_str = response
    
    data = json.loads(json_str.strip())
    
    return RelationshipAnalysis(
        relationship=RelationType(data["relationship"].lower()),
        confidence=data["confidence"],
        reasoning=data["reasoning"],
        probability_constraint=data.get("probability_constraint"),
        edge_cases=data.get("edge_cases", []),
        resolution_compatible=data.get("resolution_compatible", True),
        # ...
    )
```

## 6.3 套利检测算法

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
        # A → B，检查 P(B) >= P(A)
        implying = market_a  # 蕴含方
        implied = market_b   # 被蕴含方
    elif analysis.relationship == RelationType.IMPLIES_BA:
        # B → A，检查 P(A) >= P(B)
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
            analysis.resolution_notes or "检查结算规则"
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

# 7. API与外部依赖

## 7.1 Polymarket API

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

#### 获取事件列表

```http
GET /events
```

#### 获取事件下的市场

```http
GET /markets?event_slug={slug}
```

### CLOB API（交易）

**Base URL**: `https://clob.polymarket.com`

> 注：交易API需要钱包签名，Phase 4+实现

## 7.2 Claude API

**Base URL**: `https://api.anthropic.com/v1`

### 消息接口

```python
import anthropic

client = anthropic.Anthropic(api_key="...")

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1500,
    messages=[
        {"role": "user", "content": prompt}
    ]
)

content = response.content[0].text
```

### 成本估算

| 模型 | 输入价格 | 输出价格 | 每次分析估算 |
|------|----------|----------|--------------|
| Claude Sonnet | $3/M tokens | $15/M tokens | ~$0.01 |
| Claude Haiku | $0.25/M | $1.25/M | ~$0.001 |

**建议**：开发阶段用Sonnet，生产阶段可切换Haiku降本

## 7.3 Kalshi API（Phase 3）

**Base URL**: `https://trading-api.kalshi.com/trade-api/v2`

> 需要申请API Key，仅限美国用户

## 7.4 依赖库

### 核心依赖

```
requests>=2.28.0       # HTTP客户端
anthropic>=0.18.0      # Claude API
python-dotenv>=1.0.0   # 环境变量管理
```

### Phase 2扩展

```
sentence-transformers>=2.2.0   # 文本嵌入
chromadb>=0.4.0               # 向量数据库
numpy>=1.24.0                 # 数值计算
```

### Phase 3扩展

```
websockets>=11.0       # WebSocket客户端
aiohttp>=3.8.0        # 异步HTTP
apscheduler>=3.10.0   # 定时任务
```

### Phase 4扩展

```
web3>=6.0.0           # 以太坊交互
flask>=2.3.0          # Web框架
sqlalchemy>=2.0.0     # ORM
```

---

# 8. 开发路线图

## 8.1 Phase 1: MVP验证 ✅

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
- [x] T1.8 编写README文档

### 交付物

- [x] `polymarket_arb_mvp.py` - MVP完整脚本
- [x] `README.md` - 基础文档
- [x] `requirements.txt` - 依赖列表

## 8.2 Phase 2: 真实数据验证

**目标**：在真实市场数据上验证
**时间**：1-2周
**状态**：进行中

### 任务清单

- [ ] T2.1 实现Polymarket API客户端
- [ ] T2.2 测试API连接和数据解析
- [ ] T2.3 集成Claude API
- [ ] T2.4 实现LLM分析器
- [ ] T2.5 添加分析结果缓存
- [ ] T2.6 在真实数据上运行扫描
- [ ] T2.7 手动验证发现的机会
- [ ] T2.8 优化Prompt提高准确率

### 交付物

- [ ] `local_scanner.py` - 本地扫描脚本（已完成框架）
- [ ] 至少5个经人工验证的真实套利机会记录
- [ ] LLM分析准确率评估报告

### 验收标准

- 能够成功连接Polymarket API
- 每次扫描能发现至少1个潜在机会
- LLM分析准确率≥70%（人工验证）

## 8.3 Phase 3: 优化与扩展

**目标**：提高效率和覆盖面
**时间**：2-3周
**状态**：计划中

### 任务清单

- [ ] T3.1 实现向量相似度筛选
  - [ ] 集成sentence-transformers
  - [ ] 集成Chroma向量数据库
  - [ ] 实现增量索引
- [ ] T3.2 实现WebSocket实时监控
  - [ ] 订阅价格更新
  - [ ] 实现变化检测
- [ ] T3.3 实现定时扫描
  - [ ] 每小时自动扫描
  - [ ] 结果去重
- [ ] T3.4 实现通知功能
  - [ ] Telegram Bot
  - [ ] 微信通知（可选）
- [ ] T3.5 实现Kalshi API客户端
- [ ] T3.6 实现跨平台套利检测
- [ ] T3.7 实现历史回测

### 交付物

- [ ] 向量搜索模块
- [ ] WebSocket监控模块
- [ ] 通知服务
- [ ] 跨平台套利模块
- [ ] 回测报告

## 8.4 Phase 4: 自动化执行

**目标**：实现半自动/全自动执行
**时间**：3-4周
**状态**：计划中

### 任务清单

- [ ] T4.1 设计执行引擎
- [ ] T4.2 实现Polymarket交易接口
- [ ] T4.3 实现钱包管理
- [ ] T4.4 实现风控模块
  - [ ] 单笔限额
  - [ ] 日限额
  - [ ] 止损
- [ ] T4.5 实现半自动执行（确认后执行）
- [ ] T4.6 实现小额全自动执行
- [ ] T4.7 实现交易记录和追踪
- [ ] T4.8 实现盈亏统计

### 交付物

- [ ] 执行引擎模块
- [ ] 风控模块
- [ ] 交易记录系统
- [ ] 盈亏报表

## 8.5 Phase 5: Web界面

**目标**：提供友好的用户界面
**时间**：4周
**状态**：远期计划

### 任务清单

- [ ] T5.1 设计UI/UX
- [ ] T5.2 实现后端API
- [ ] T5.3 实现前端界面
- [ ] T5.4 实现用户认证
- [ ] T5.5 实现仪表盘
- [ ] T5.6 部署上线

## 8.6 里程碑

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
     │
     ├─ Phase 5 开始（可选）
     │
2025/05/31 ─── M5: Web界面完成
```

---

# 9. 测试策略

## 9.1 测试层次

```
┌─────────────────────────────────────┐
│          端到端测试 (E2E)           │  ← 完整流程验证
├─────────────────────────────────────┤
│          集成测试                    │  ← 组件交互验证
├─────────────────────────────────────┤
│          单元测试                    │  ← 函数逻辑验证
└─────────────────────────────────────┘
```

## 9.2 单元测试

### 测试用例示例

```python
# tests/test_similarity.py

def test_jaccard_similarity_identical():
    """相同文本相似度为1"""
    text = "Will Trump win the election?"
    assert jaccard_similarity(text, text) == 1.0

def test_jaccard_similarity_different():
    """完全不同文本相似度为0"""
    text_a = "Will Trump win?"
    text_b = "Lakers championship odds"
    assert jaccard_similarity(text_a, text_b) < 0.1

def test_jaccard_similarity_partial():
    """部分重叠文本相似度在0-1之间"""
    text_a = "Will Trump win the 2024 election?"
    text_b = "Will Biden win the 2024 election?"
    sim = jaccard_similarity(text_a, text_b)
    assert 0.3 < sim < 0.8


# tests/test_arbitrage_detector.py

def test_exhaustive_arbitrage_exists():
    """完备集总和<1时检测到套利"""
    markets = [
        Market(id="1", question="A", yes_price=0.30, ...),
        Market(id="2", question="B", yes_price=0.30, ...),
        Market(id="3", question="C", yes_price=0.30, ...),
    ]
    opp = detect_exhaustive_arbitrage(markets, min_profit_pct=2.0)
    assert opp is not None
    assert opp.profit_pct > 2.0

def test_exhaustive_no_arbitrage():
    """完备集总和>=1时无套利"""
    markets = [
        Market(id="1", question="A", yes_price=0.50, ...),
        Market(id="2", question="B", yes_price=0.50, ...),
    ]
    opp = detect_exhaustive_arbitrage(markets, min_profit_pct=2.0)
    assert opp is None

def test_implication_arbitrage_exists():
    """包含关系违规时检测到套利"""
    market_a = Market(id="1", question="Trump wins", yes_price=0.55, ...)
    market_b = Market(id="2", question="GOP wins", yes_price=0.50, ...)
    analysis = RelationshipAnalysis(
        relationship=RelationType.IMPLIES_AB,
        confidence=0.95,
        ...
    )
    opp = detect_implication_arbitrage(market_a, market_b, analysis)
    assert opp is not None
```

## 9.3 集成测试

```python
# tests/test_integration.py

def test_full_scan_with_mock_data():
    """使用模拟数据的完整扫描流程"""
    scanner = ArbitrageScanner(
        fetcher=MockFetcher(),
        filter=KeywordSimilarityFilter(),
        analyzer=RuleBasedAnalyzer(),
        detector=ArbitrageDetector()
    )
    
    opportunities = scanner.scan()
    
    # 验证返回结构正确
    assert isinstance(opportunities, list)
    for opp in opportunities:
        assert isinstance(opp, ArbitrageOpportunity)
        assert opp.profit_pct > 0
```

## 9.4 LLM分析测试

```python
# tests/test_llm_analyzer.py

# 预定义的测试用例
TEST_CASES = [
    {
        "market_a": "Will Trump win the 2028 election?",
        "market_b": "Will the Republican candidate win 2028?",
        "expected_relationship": "IMPLIES_AB",
        "expected_constraint": "P(B) >= P(A)"
    },
    {
        "market_a": "Lakers win NBA Championship 2025",
        "market_b": "Lakers make 2025 playoffs",
        "expected_relationship": "IMPLIES_AB",
        "expected_constraint": "P(B) >= P(A)"
    },
    # ... 更多测试用例
]

def test_llm_relationship_detection():
    """测试LLM逻辑关系识别准确率"""
    analyzer = ClaudeAnalyzer()
    correct = 0
    
    for case in TEST_CASES:
        result = analyzer.analyze(
            Market(question=case["market_a"], ...),
            Market(question=case["market_b"], ...)
        )
        if result.relationship.value == case["expected_relationship"].lower():
            correct += 1
    
    accuracy = correct / len(TEST_CASES)
    assert accuracy >= 0.7, f"LLM准确率{accuracy:.0%}低于70%"
```

## 9.5 回测验证

```python
def backtest_strategy(
    historical_data: List[Dict],
    strategy: Callable
) -> Dict:
    """
    策略回测
    
    输入: 历史市场数据和套利机会
    输出: 回测结果统计
    """
    results = {
        "total_opportunities": 0,
        "profitable": 0,
        "unprofitable": 0,
        "total_profit": 0,
        "total_cost": 0,
        "roi": 0
    }
    
    for snapshot in historical_data:
        opportunities = strategy(snapshot["markets"])
        
        for opp in opportunities:
            results["total_opportunities"] += 1
            
            # 检查实际结算结果
            actual_return = calculate_actual_return(
                opp,
                snapshot["resolution"]
            )
            
            if actual_return > opp.total_cost:
                results["profitable"] += 1
            else:
                results["unprofitable"] += 1
            
            results["total_profit"] += actual_return - opp.total_cost
            results["total_cost"] += opp.total_cost
    
    results["roi"] = results["total_profit"] / results["total_cost"]
    return results
```

---

# 10. 风险管理

## 10.1 风险矩阵

| 风险类型 | 可能性 | 影响 | 风险等级 | 缓解措施 |
|----------|--------|------|----------|----------|
| 逻辑关系误判 | 中 | 高 | 🔴高 | 人工复核、LLM多次验证 |
| 结算规则差异 | 中 | 高 | 🔴高 | 仔细阅读规则、只做熟悉的市场 |
| Oracle操纵 | 低 | 高 | 🟡中 | 分散投资、关注UMA治理 |
| 流动性不足 | 中 | 中 | 🟡中 | 检查深度、分批执行 |
| API变更 | 低 | 中 | 🟢低 | 版本监控、及时适配 |
| 平台风险 | 低 | 高 | 🟡中 | 不存大额、及时提现 |

## 10.2 风险缓解策略

### 10.2.1 逻辑关系误判

**问题**：LLM可能错误判断两个市场的逻辑关系

**缓解措施**：
1. 设置高置信度阈值（≥0.8）
2. 要求LLM列出边界情况
3. 所有机会执行前人工复核
4. 建立错误案例库，改进Prompt
5. 对重要决策多次询问LLM

### 10.2.2 结算规则差异

**问题**：两个看似相关的市场可能有不同的结算规则

**真实案例**：
> 2024年美国政府关门事件中，Polymarket以"OPM发布关门公告"为结算标准，
> 而Kalshi要求"实际关门超过24小时"。套利者以为是完美对冲，结果两边都亏钱。

**缓解措施**：
1. 仔细阅读每个市场的结算规则
2. 检查结算数据来源是否一致
3. 对边界情况特别警惕
4. 优先选择结算规则明确的市场

### 10.2.3 Oracle操纵风险

**问题**：Polymarket使用UMA预言机，可能被大户操纵

**真实案例**：
> 2025年3月，一个持有500万UMA代币（25%投票权）的巨鲸操纵了一个700万美元市场的结算

**缓解措施**：
1. 关注UMA治理动态
2. 避免在争议性结算的市场下大注
3. 分散投资，单笔≤总资金10%
4. 优先选择高流动性、低争议市场

### 10.2.4 仓位管理规则

```python
# 风控参数
MAX_SINGLE_POSITION = 0.10      # 单笔最大仓位（占总资金）
MAX_DAILY_EXPOSURE = 0.30       # 日最大敞口
MAX_EVENT_EXPOSURE = 0.20       # 单事件最大敞口
MIN_LIQUIDITY_RATIO = 0.10      # 仓位不超过市场流动性的10%

def calculate_position_size(
    total_capital: float,
    opportunity: ArbitrageOpportunity,
    current_exposure: float
) -> float:
    """计算建议仓位"""
    
    # 基于利润率的基础仓位
    base_size = total_capital * MAX_SINGLE_POSITION
    
    # 根据置信度调整
    confidence_adj = opportunity.confidence  # 0.8-1.0
    
    # 根据流动性调整
    min_liquidity = min(m.liquidity for m in opportunity.markets)
    liquidity_adj = min(1.0, min_liquidity * MIN_LIQUIDITY_RATIO / base_size)
    
    # 根据当前敞口调整
    remaining_exposure = MAX_DAILY_EXPOSURE - current_exposure
    exposure_adj = remaining_exposure / MAX_SINGLE_POSITION
    
    # 最终仓位
    position = base_size * confidence_adj * liquidity_adj * exposure_adj
    
    return max(0, position)
```

## 10.3 人工复核清单

每个套利机会执行前，必须完成以下复核：

```markdown
## 套利机会复核清单

### 基本信息
- 机会ID: _______________
- 发现时间: _______________
- 潜在利润: _______________

### 逻辑验证 ✓/✗
- [ ] LLM判断的逻辑关系我理解并认同
- [ ] 我能用自己的话解释为什么这个关系成立
- [ ] 我考虑过所有边界情况
- [ ] 边界情况发生的概率很低

### 结算规则验证 ✓/✗
- [ ] 我已阅读所有相关市场的结算规则
- [ ] 结算数据来源一致
- [ ] 结算时间接近（≤24小时差异）
- [ ] 不存在可能导致两边都输的情况

### 流动性验证 ✓/✗
- [ ] 我检查了订单簿深度
- [ ] 我的仓位≤市场流动性的10%
- [ ] 滑点预期在可接受范围内

### 风控验证 ✓/✗
- [ ] 单笔仓位≤总资金10%
- [ ] 今日总敞口≤总资金30%
- [ ] 我能承受最坏情况的亏损

### 最终决策
- [ ] 执行 → 记录执行详情
- [ ] 放弃 → 记录放弃原因
- [ ] 需要更多信息 → 列出需要的信息
```

---

# 11. 运维与监控

## 11.1 部署架构

### Phase 1-3: 本地运行

```
本地机器
├── Python环境
├── 扫描脚本
├── 配置文件
└── 输出目录
    ├── scans/
    ├── opportunities/
    └── logs/
```

### Phase 4+: 云部署

```
┌─────────────────────────────────────────────────────────┐
│                      云服务器                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │  扫描服务   │  │  通知服务   │  │  Web服务    │      │
│  └─────────────┘  └─────────────┘  └─────────────┘      │
│         │              │              │                 │
│         ▼              ▼              ▼                 │
│  ┌─────────────────────────────────────────────────┐    │
│  │                   数据库                         │    │
│  │               PostgreSQL                        │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## 11.2 日志规范

```python
import logging

# 日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# 日志级别
# DEBUG: 详细调试信息
# INFO: 正常运行信息
# WARNING: 警告信息
# ERROR: 错误信息

# 日志示例
logger.info(f"开始扫描，市场数量: {len(markets)}")
logger.debug(f"分析市场对: {market_a.id} vs {market_b.id}")
logger.warning(f"API请求重试: {retry_count}/3")
logger.error(f"LLM分析失败: {error}")

# 结构化日志（Phase 3+）
logger.info("opportunity_found", extra={
    "opportunity_id": opp.id,
    "type": opp.type,
    "profit_pct": opp.profit_pct,
    "confidence": opp.confidence
})
```

## 11.3 监控指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| scan_duration | 单次扫描耗时 | >10分钟 |
| api_error_rate | API错误率 | >10% |
| llm_latency | LLM响应时间 | >30秒 |
| opportunities_found | 发现机会数 | 连续3天=0 |
| llm_cost_daily | LLM日成本 | >$5 |

## 11.4 定时任务

```bash
# crontab配置

# 每小时扫描
0 * * * * cd /path/to/project && python local_scanner.py >> logs/scan.log 2>&1

# 每天汇总报告
0 20 * * * cd /path/to/project && python generate_daily_report.py

# 每周清理旧数据
0 3 * * 0 cd /path/to/project && python cleanup_old_data.py --days=30
```

---

# 12. 扩展计划

## 12.1 策略扩展

### 更多套利类型

| 类型 | 说明 | 优先级 |
|------|------|--------|
| 时间套利 | 同一事件不同时间点市场价差 | P2 |
| 相关性套利 | 历史相关性高的事件价格偏离 | P3 |
| 信息套利 | 基于信息优势的快速反应 | P3 |

### 更多平台

| 平台 | 说明 | 优先级 |
|------|------|--------|
| Kalshi | 美国合规预测市场 | P1 |
| PredictIt | 学术预测市场 | P2 |
| Betfair | 传统博彩交易所 | P3 |

## 12.2 技术扩展

### AI能力增强

| 能力 | 说明 | 优先级 |
|------|------|--------|
| 多模型验证 | 用多个LLM交叉验证 | P2 |
| 专家微调 | 在套利案例上微调模型 | P3 |
| Agent自动执行 | LLM自主决策执行 | P4 |

### 基础设施

| 能力 | 说明 | 优先级 |
|------|------|--------|
| 分布式扫描 | 多机并行扫描 | P3 |
| 实时流处理 | Kafka + Flink | P4 |
| 高可用部署 | K8s集群 | P4 |

## 12.3 商业化可能（远期）

| 方向 | 说明 |
|------|------|
| SaaS服务 | 为其他交易者提供信号服务 |
| 基金 | 募资运营套利基金 |
| 数据服务 | 出售市场分析数据 |
| 教育 | 套利策略培训课程 |

---

# 13. 附录

## 13.1 术语表

| 术语 | 英文 | 定义 |
|------|------|------|
| 套利 | Arbitrage | 利用价格差异获取无风险利润 |
| 完备集 | Exhaustive Set | 覆盖所有可能结果的互斥选项集合 |
| 包含关系 | Implication | A发生必然导致B发生的逻辑关系 |
| 预言机 | Oracle | 向区块链提供链外数据的机制 |
| 流动性 | Liquidity | 市场中可交易的资金量 |
| 滑点 | Slippage | 预期价格与实际成交价的差异 |
| YES Token | - | 代表"是"结果的代币 |
| NO Token | - | 代表"否"结果的代币 |

## 13.2 常用命令

```bash
# 运行扫描
python local_scanner.py

# 指定配置
python local_scanner.py --config=config.json

# 调试模式
LOG_LEVEL=DEBUG python local_scanner.py

# 指定最小利润
MIN_PROFIT_PCT=3.0 python local_scanner.py

# 查看帮助
python local_scanner.py --help
```

## 13.3 常见问题

### Q: API请求失败怎么办？

A: 检查网络连接，Polymarket API可能需要科学上网。也可能是请求频率过高被限制。

### Q: LLM分析不准确怎么办？

A: 
1. 检查Prompt是否清晰
2. 提高置信度阈值
3. 所有机会都人工复核
4. 收集错误案例改进Prompt

### Q: 发现机会后如何执行？

A:
1. 按照报告中的操作步骤
2. 在Polymarket网站手动下单
3. 先小额测试（$10-50）
4. 确认流程后再放大仓位

### Q: 如何评估策略效果？

A:
1. 记录每个机会的发现和执行
2. 跟踪最终结算结果
3. 计算准确率和收益率
4. 定期回顾和优化

## 13.4 参考资源

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

---

# 联系方式

如有问题或建议，请通过以下方式联系：

- GitHub Issues: [项目仓库]
- Email: [你的邮箱]

---

**免责声明**: 
本项目仅供学习研究使用。预测市场交易有风险，套利策略也存在执行风险。
请自行评估风险并承担后果。本文档不构成投资建议。
