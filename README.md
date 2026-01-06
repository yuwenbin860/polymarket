# Polymarket 组合套利系统

一个用于识别Polymarket预测市场中逻辑定价违规套利机会的自动化系统。

## 🎯 核心功能

1. **完备集套利** - 检测互斥且完备的市场组合是否总价<1
2. **包含关系套利** - 检测逻辑包含关系是否被价格违反
3. **LLM辅助分析** - 使用AI分析市场间的逻辑关系
4. **多LLM支持** - 支持OpenAI、Claude、DeepSeek、通义、GLM、Ollama等
5. **真实订单簿价格** - 使用CLOB API获取best_bid/best_ask，而非最后成交价
6. **三层验证架构** - 数学验证 + LLM找碴验证 + 双模型交叉验证
7. **🏷️ Tag分类获取** - 按crypto/politics/sports等标签精准获取市场
8. **📜 Rules分析优先** - 获取并分析每个市场的结算规则
9. **🔢 区间套利检测** - 检测价格区间的互补套利机会

## 📁 项目结构

```
polymarket_arb/
├── PROJECT_BIBLE.md         # 📖 项目完整文档（必读）
├── local_scanner_v2.py      # 主程序（支持多LLM + 订单簿价格）
├── tag_manager.py           # 🏷️ Tag管理模块
├── interval_parser.py       # 🔢 区间解析器
├── semantic_cluster.py      # 🧠 语义聚类模块
├── llm_providers.py         # LLM提供商抽象层
├── llm_config.py            # LLM配置管理器
├── prompts.py               # Prompt工程模块（含时间验证）
├── validators.py            # 数学验证层（时间一致性验证）
├── similarity.py            # 向量相似度计算
├── dual_verification.py     # 双模型交叉验证
├── simulation.py            # 模拟执行跟踪
├── config.py                # 配置管理
├── config.example.json      # 配置文件示例
├── test_prompts.py          # Prompt测试脚本
├── test_new_features.py     # 🧪 新功能验证测试
├── polymarket_arb_mvp.py    # MVP版本（模拟数据）
├── requirements.txt         # 依赖列表
└── README.md                # 本文件
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install requests httpx
```

### 2. 配置LLM（三种方式任选）

**方式A: 使用 config.json（推荐）**
```bash
cp config.example.json config.json
# 编辑 config.json 填入 api_key，修改 active_profile 切换LLM
python local_scanner_v2.py
```

**方式B: 使用 --profile 预设配置**
```bash
# 设置API Key
export DEEPSEEK_API_KEY="sk-..."

# 使用预设配置运行
python local_scanner_v2.py --profile deepseek
python local_scanner_v2.py --profile siliconflow
python local_scanner_v2.py --profile modelscope

# 查看所有可用配置
python local_scanner_v2.py --list-profiles
```

**方式C: 使用环境变量**
```bash
export DEEPSEEK_API_KEY="sk-..."
python local_scanner_v2.py  # 自动检测
```

### 3. 配置优先级

```
1. --profile 参数      (最高优先级)
2. config.json 的 active_profile
3. 环境变量自动检测
4. 默认值              (最低优先级)
```

### 4. 运行扫描

```bash
python local_scanner_v2.py
```

### 5. 命令行参数完整列表

#### LLM配置参数

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--profile` | `-p` | 使用预设LLM配置 | `--profile siliconflow` |
| `--model` | `-m` | 覆盖默认模型 | `--model Qwen/Qwen2.5-72B-Instruct` |
| `--config` | `-c` | 指定配置文件路径 | `--config custom.json` |
| `--list-profiles` | - | 列出所有可用配置 | `--list-profiles` |

#### 扫描参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--min-profit` | 最小利润百分比 | 2.0 |
| `--market-limit` | 获取市场数量 | 200 |

#### 向量化模式参数（语义聚类）

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--no-semantic` | - | 禁用向量化模式 | False |
| `--domain` | `-d` | 市场领域 | crypto |
| `--threshold` | `-t` | 语义聚类相似度阈值 (0.0-1.0) | 0.85 |

#### 使用示例

```bash
# 基础扫描（向量化模式默认启用）
python local_scanner_v2.py

# 禁用向量化模式，使用传统搜索
python local_scanner_v2.py --no-semantic

# 使用指定LLM配置
python local_scanner_v2.py --profile siliconflow
python local_scanner_v2.py -p deepseek

# 切换模型
python local_scanner_v2.py --profile siliconflow --model deepseek-ai/DeepSeek-V3

# 自定义扫描参数
python local_scanner_v2.py --min-profit 3.0 --market-limit 500

# 自定义领域和阈值
python local_scanner_v2.py --domain politics --threshold 0.80

# 组合使用
python local_scanner_v2.py --profile ollama -d sports -t 0.90

# 列出所有可用配置
python local_scanner_v2.py --list-profiles
```

## 🤖 支持的LLM提供商

| 提供商 | 环境变量 | 成本 | 推荐场景 |
|--------|----------|------|----------|
| **SiliconFlow** | `SILICONFLOW_API_KEY` | **低** | **国内聚合平台，速度快** |
| **DeepSeek** | `DEEPSEEK_API_KEY` | **低** | **日常使用** |
| **ModelScope** | `MODELSCOPE_API_KEY` | **低** | **阿里云托管平台** |
| OpenAI | `OPENAI_API_KEY` | 中 | 高精度需求 |
| Claude | `ANTHROPIC_API_KEY` | 中 | 复杂推理 |
| 阿里云 | `DASHSCOPE_API_KEY` | 低 | 国内网络 |
| 智谱GLM | `ZHIPU_API_KEY` | 中 | 国内网络 |
| **Ollama** | (本地) | **免费** | **离线/测试** |

## 📋 使用配置文件

```bash
# 1. 复制示例配置
cp config.example.json config.json

# 2. 编辑 config.json
```

```json
{
  "llm_profiles": {
    "siliconflow": {
      "provider": "openai_compatible",
      "api_base": "https://api.siliconflow.cn/v1",
      "api_key": "sk-your-api-key",
      "model": "deepseek-ai/DeepSeek-V3",
      "embedding_model": "BAAI/bge-large-zh-v1.5"
    },
    "modelscope": {
      "provider": "modelscope",
      "api_base": "https://api-inference.modelscope.cn/v1",
      "api_key": "ms-your-api-key",
      "model": "Qwen/Qwen2.5-72B-Instruct",
      "embedding_model": "Qwen/Qwen3-Embedding-8B"
    },
    "deepseek": {
      "provider": "openai_compatible",
      "api_base": "https://api.deepseek.com/v1",
      "api_key": "sk-your-api-key",
      "model": "deepseek-chat",
      "embedding_model": "BAAI/bge-large-zh-v1.5"
    }
  },
  "active_profile": "siliconflow",
  "scan": {
    "min_profit_pct": 2.0,
    "min_liquidity": 10000,
    "semantic_threshold": 0.85
  }
}
```

```bash
# 3. 运行（会自动读取 config.json 的 active_profile）
python local_scanner_v2.py

# 4. 切换LLM：修改 active_profile 字段即可
```

**配置说明**:
- `active_profile`: 指定使用的配置名称（如 "siliconflow"、"modelscope"、"deepseek"）
- `embedding_model`: 向量化模式使用的embedding模型（每个profile独立配置）

## 🧪 测试Prompt效果

```bash
# 运行所有测试用例
python test_prompts.py

# 指定LLM配置
python test_prompts.py --profile deepseek

# 只运行第一个测试
python test_prompts.py --test 0
```

## 🏷️ 按Tag分类获取市场

系统现在支持直接按分类（如crypto、politics、sports）精准获取市场，无需关键词匹配。

### 使用TagManager

```python
from tag_manager import TagManager

manager = TagManager()

# 获取所有可用tags
tags = manager.get_all_tags()

# 按slug获取tag
crypto_tag = manager.get_tag("crypto")  # id = "21"
print(f"Tag: {crypto_tag.label}, ID: {crypto_tag.id}")
```

### 使用PolymarketClient获取分类市场

```python
from local_scanner_v2 import PolymarketClient

client = PolymarketClient()

# 按tag slug获取markets（推荐方式）
markets = client.get_markets_by_tag_slug('crypto', active=True, limit=100)

# 按tag_id获取markets
markets = client.get_markets_by_tag(tag_id="21", active=True, limit=100)
```

### 常用Tags

| Slug | Tag ID | 分类 |
|------|--------|------|
| `crypto` | 21 | 加密货币 |
| `politics` | 2 | 政治 |
| `sports` | 1 | 体育 |
| `technology` | 22 | 科技 |
| `business` | 23 | 商业 |
| `world` | 24 | 国际 |

### 新方式 vs 旧方式

**旧方式（关键词匹配）**:
- ❌ 需要多次API调用
- ❌ 客户端过滤，可能遗漏相关市场
- ❌ 不包含完整event信息

**新方式（Tag过滤）**:
- ✅ 单次API调用
- ✅ 服务端过滤，结果更准确
- ✅ 包含完整rules和tags信息

## 📜 Rules分析优先

系统现在会获取并分析每个市场的结算规则（resolution rules），在进行语义分析前先理解规则。

### Rules信息来源

```python
markets = client.get_markets_by_tag_slug('crypto')

for m in markets:
    # event_description: Event级别的description，包含完整判定规则
    rules = m.event_description

    # market_description: Market级别的description
    market_desc = m.market_description

    # full_description: 自动选择最完整的描述
    full_desc = m.full_description

    # tags: 事件分类标签
    tags = [t['label'] for t in m.tags]

    print(f"Question: {m.question}")
    print(f"Rules: {rules[:200]}...")
    print(f"Tags: {tags}")
```

### Why Rules Matter

1. **结算来源差异** - 不同的数据源可能导致同一问题的结果不同
2. **时间一致性** - 结算日期差异会影响蕴含关系的有效性
3. **边界处理** - "above"是否包含等于影响区间套利判断

### LLM分析时自动包含Rules

```python
# prompts.py已更新，LLM分析时会自动使用full_description
# 这意味着LLM会同时看到question和rules
```

## 🔢 区间套利检测

系统支持区间套利机会检测，当两个区间的并集覆盖所有可能值且互斥时存在套利。

### 什么是区间套利？

当两个互补的区间市场总价低于$1时，存在无风险套利机会。

### 真实案例：Solana Jan 4

```
区间A: [0, 130)  (完备集子市场之一) → YES价格 = 4.6c
区间B: [130, ∞)  (阈值市场)         → YES价格 = 94.8c

套利策略: 买A的YES + 买B的YES = 4.6 + 94.8 = 99.4c
保证回报: $1.00
利润: 0.6c (0.6%)
```

### 使用IntervalParser

```python
from interval_parser import IntervalParser

parser = IntervalParser()

# 解析区间
interval = parser.parse("Will BTC be above $100k in 2025?")
# 返回: Interval(type=ABOVE, lower=100000, upper=inf, unit="USD")

# 比较区间关系
relation = parser.compare_intervals(interval_a, interval_b)
# 返回: A_COVERS_B, B_COVERS_A, OVERLAP, MUTUAL_EXCLUSIVE, UNRELATED

# 检测套利
arbitrage = parser.find_interval_arbitrage(market_a, market_b)
```

### 支持的区间类型

| 类型 | 示例 | 含义 |
|------|------|------|
| `ABOVE` | "above $100k" | 价格 > 阈值 |
| `BELOW` | "below $50" | 价格 < 阈值 |
| `RANGE` | "between $100 and $150" | 价格在区间内 |

## 🧪 验证新功能

运行验证测试脚本确保所有功能正常：

```bash
# 运行完整测试套件
python test_new_features.py

# 测试内容：
# 1. TagManager - Tag管理和获取
# 2. Market结构 - event_description, tags字段
# 3. IntervalParser - 区间解析和关系判断
# 4. Solana场景 - 真实区间套利案例
# 5. 集成测试 - 端到端数据流程
```

## 📚 详细文档

### 核心文档

- **[docs/PROJECT_BIBLE.md](./docs/PROJECT_BIBLE.md)** - 项目完整指导文档
  - 完整的策略原理和市场背景
  - 系统架构和技术设计
  - 开发路线图和任务分解
  - 风险管理和人工复核清单
  - API参考和常见问题

### 进度文档

- **[docs/PROGRESS.md](./docs/PROGRESS.md)** - 项目进度追踪
  - 当前状态和已完成里程碑
  - 进行中任务和工作日志
  - 每日工作记录
  - 版本历史

### 技术文档

- **[PHASE2_FIX_PLAN.md](./PHASE2_FIX_PLAN.md)** - Phase 2 详细修复计划
- **[CLAUDE.md](./CLAUDE.md)** - Claude Code 开发指南

## 💰 套利示例

### 完备集套利

```
市场1: "共和党获270-299票" YES = $0.18
市场2: "共和党获300-319票" YES = $0.12
市场3: "共和党获320+票"    YES = $0.05
市场4: "民主党获胜"        YES = $0.58
───────────────────────────────────────
总成本: $0.93
保证回报: $1.00
利润: $0.07 (7.5%)
```

### 包含关系套利

```
逻辑: "特朗普赢" → "共和党赢"

市场A: "特朗普赢总统" YES = $0.55
市场B: "共和党赢总统" YES = $0.50  ← 违反逻辑！

操作: 
- 买 "共和党赢" YES @ $0.50
- 买 "特朗普赢" NO @ $0.45
总成本: $0.95，保证回报 $1.00，利润 5.3%
```

## ⚠️ 风险提示

### 核心风险

1. **逻辑关系误判** - 所有机会需人工复核
2. **结算规则差异** - 仔细阅读每个市场的规则
3. **流动性风险** - 检查订单簿深度
4. **单笔限制** - 建议不超过总资金10%

### 三大实战陷阱（已修复）

**陷阱1: Bid/Ask vs Last Price**
- ❌ **问题**: 使用中间价/最后成交价计算套利，而实际成交需要支付 best_ask（更贵）
- ✅ **修复**: 系统现已集成 CLOB API 获取真实订单簿价格
- 📍 **影响**: 套利计算更准确，避免高估利润

**陷阱2: 跨链套利成本**
- ❌ **问题**: 跨链套利（Polygon ↔ BNB/Solana）未考虑桥接费、gas、时延（数分钟至半小时）
- ✅ **修复**: 策略优先级降级，小资金建议专注 Polymarket 内部套利
- 📍 **影响**: 避免跨链摩擦吞噬小额套利利润

**陷阱3: 时间一致性**
- ❌ **问题**: LLM可能忽略时间修饰符（"1月前""3月后"），未自动验证 `end_date(B) >= end_date(A)`
- ✅ **修复**: 新增自动时间验证函数 + 强化 Prompt 时间检查规则
- 📍 **影响**: 避免因结算时间差导致蕴含关系失效

## 📄 License

MIT License

---

**免责声明**: 本工具仅供学习研究使用。预测市场交易有风险，请自行评估并承担风险。
