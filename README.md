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
├── monotonicity_checker.py  # 📉 单调性违背检测模块
├── interval_parser_v2.py    # 🔢 区间解析器
├── semantic_cluster.py      # 🧠 语义聚类模块
├── llm_providers.py         # LLM提供商抽象层
├── llm_config.py            # LLM配置管理器
├── prompts.py               # Prompt工程模块（含时间验证）
├── validators.py            # 数学验证层（时间一致性验证）
├── config.py                # 配置管理
├── config.example.json      # 配置文件示例
├── scripts/
│   └── tag_validator.py     # 🏷️ 标签验证和更新工具
├── data/
│   └── tag_categories.json  # 🏷️ 标签分类配置
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
| `--subcat` | - | 子类别筛选（逗号分隔） | 无 |
| `--list-subcats` | - | 列出指定领域的所有可用子类别 | - |

#### 缓存控制参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--refresh` | `-r` | 强制刷新缓存，重新获取市场数据 | False |
| `--use-cache` | - | 明确指定使用缓存（如果缓存有效） | False |
| `--no-interactive` | - | 禁用交互式提示，使用默认行为 | False |

#### 全量获取参数（分页支持）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--full-fetch` | 启用全量获取（覆盖配置文件） | False |

#### 运行模式参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--mode` | 运行模式 (debug=暂停确认, production=自动保存) | - |

#### 单调性检测参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--monotonicity-check` | 启用单调性违背检测（检测价格倒挂） | False |

**使用示例**:
```bash
# 启用全量获取
python local_scanner_v2.py --domain crypto --full-fetch

# 或通过配置文件启用
# 编辑 config.json: "scan.enable_full_fetch": true
```

#### 验证模式参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--verify` | `-v` | 验证模式：发现机会后暂停等待确认 | False |
| `--verify-auto-save` | - | 自动保存所有发现的机会 | False |

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

# 子类别筛选（只扫描 bitcoin 相关市场）
python local_scanner_v2.py --subcat btc

# 子类别筛选（多个币种）
python local_scanner_v2.py --subcat btc,eth,sol

# 列出所有可用的 crypto 子类别
python local_scanner_v2.py --domain crypto --list-subcats

# 缓存控制：强制刷新数据
python local_scanner_v2.py --refresh
python local_scanner_v2.py -r

# 缓存控制：明确使用缓存
python local_scanner_v2.py --use-cache

# 组合使用
python local_scanner_v2.py --profile ollama -d sports -t 0.90

# 单调性违背扫描（检测价格倒挂）
python local_scanner_v2.py --domain crypto --monotonicity-check
python local_scanner_v2.py -d crypto --monotonicity-check --subcat btc,eth

# 标签验证和更新
python scripts/tag_validator.py --check
python scripts/tag_validator.py --update --min-markets 10
python scripts/tag_validator.py --report --output tag_report.md

# 列出所有可用配置
python local_scanner_v2.py --list-profiles
```

## 🏷️ 子类别筛选

系统支持在选定领域后进一步筛选子类别，减少数据量用于快速验证。

### 交互式菜单选择（推荐）

启动脚本后会自动显示子类别选择菜单：

```bash
$ python local_scanner_v2.py

=======================================================
请选择要扫描的 crypto 子类别:
=======================================================
  1. Bitcoin     (bitcoin-prices, bitcoin-volatility... +2更多)
  2. Ethereum    (ethereum-prices, ethereum-dencun... +5更多)
  3. Solana      (solana-prices, sol, solana)
  4. 主要币种    (xrp, xrp-prices, ada, bnb, litecoin)
  5. 稳定币/DeFi (tether, usdc, uniswap... +2更多)
  6. NFT/meme    (nft, cryptopunks, pepe)
  7. 平台/项目   (binance, megaeth... +2更多)
  8. 综合/其他   (crypto, crypto-prices... +7更多)
  0. 全部子类别
=======================================================
请输入选项 [多个用逗号分隔，直接回车=全部]: 1,2,3
[INFO] 已选择 14 个子类别
```

**输入方式**:
- 单选: `1`
- 多选: `1,3,5`
- 范围: `1-3` (等同于 1,2,3)
- 全选: 直接回车

### Crypto 子类别分组

| 分组 | 包含标签 |
|------|----------|
| **Bitcoin** | bitcoin, bitcoin-prices, bitcoin-volatility, bitcoin-conference, strategic-bitcoin-reserve |
| **Ethereum** | ethereum, ethereum-dencun, ethgas, ethbtc, ether-rock, etherfi, ethena, megaeth |
| **Solana** | solana, solana-prices, sol |
| **主要币种** | xrp, xrp-prices, ripple, cardano, bnb, litecoin, dogecoin |
| **稳定币/DeFi** | tether, usdc, uniswap, defi-app, chainlink, stablecoins |
| **NFT/meme** | nft, cryptopunks, pepe |
| **平台/项目** | binance, token-launch, token-price, hyperliquid, coinbase |
| **综合/其他** | crypto, crypto-prices, cryptocurrency, airdrops, 等 |

**注意**：标签配置已更新，`bitcoin` 和 `ethereum` 核心标签已添加。使用 `scripts/tag_validator.py` 可验证和更新标签配置。

### 命令行参数

如果不想使用交互式菜单，可以通过命令行参数直接指定：

```bash
# 只扫描 bitcoin 相关市场
python local_scanner_v2.py --subcat btc

# 扫描多个币种（支持快捷别名）
python local_scanner_v2.py --subcat btc,eth,sol

# 列出所有可用的子类别
python local_scanner_v2.py --domain crypto --list-subcats
```

### 快捷别名支持

| 别名 | 映射到 |
|------|--------|
| `btc` | `bitcoin` |
| `eth` | `ethereum` |
| `sol` | `solana` |
| `bnb` | `bnb` |
| `xrp` | `xrp` |
| `ada` | `cardano` |
| `dot` | `polkadot` |

### CLI 参数优先级

1. `--subcat xxx,yyy` → 跳过交互，使用命令行指定
2. `--no-interactive` → 跳过交互，使用默认（无筛选）
3. 无参数 → 显示交互式菜单

## 💾 缓存控制

系统支持灵活的缓存控制，方便测试和更新数据。

### 缓存模式

| 模式 | 触发方式 | 行为 |
|------|----------|------|
| **强制刷新** | `--refresh` / `-r` | 跳过缓存，重新获取数据 |
| **使用缓存** | `--use-cache` | 使用缓存（如果有效） |
| **交互模式** | （默认） | 发现缓存时询问用户 |

### 交互模式示例

```bash
$ python local_scanner_v2.py

[缓存] 发现缓存的 crypto 市场数据
是否使用缓存？(y=使用缓存, n=重新获取, 直接回车=y): n
[INFO] 将重新获取市场数据
```

### 使用示例

```bash
# 测试时使用缓存（快速）
python local_scanner_v2.py --use-cache

# 需要更新时强制刷新
python local_scanner_v2.py --refresh
python local_scanner_v2.py -r

# 跳过交互，直接使用默认行为
python local_scanner_v2.py --no-interactive
```

### 缓存文件位置

```
cache/
├── crypto_markets.json           # 完整 crypto 领域缓存
├── crypto_bitcoin_markets.json   # bitcoin 子类别缓存
└── crypto_ethereum_markets.json  # ethereum 子类别缓存
```

## 🔍 验证模式

验证模式允许你在发现每个套利机会后立即暂停，查看详细信息并决定是否保存。这对于逐步验证和优化系统非常有用。

### 启用验证模式

```bash
# 基础验证模式
python local_scanner_v2.py --domain crypto --verify

# 简写
python local_scanner_v2.py -d crypto -v

# 验证模式 + 自动保存所有发现的机会
python local_scanner_v2.py -d crypto -v --verify-auto-save
```

### 验证模式交互命令

发现套利机会后，系统会暂停并显示详细信息，你可以使用以下命令：

| 命令 | 说明 |
|------|------|
| `Enter` | 继续扫描（不保存此机会） |
| `s` | 保存此机会到结果列表 |
| `f` | 标记为误报并记录原因 |
| `q` | 退出扫描 |
| `d` | 显示更多调试详情 |
| `r` | 调整最小利润率阈值 |
| `l` | 调整最小流动性阈值 |
| `j` | 保存此机会到单独JSON文件 |
| `?` | 显示帮助 |

### 验证模式输出示例

```
══════════════════════════════════════════════════════════════
[套利机会 #1] IMPLIES_ARBITRAGE
══════════════════════════════════════════════════════════════

[市场信息]
───────────────────────────────────────────────────────────
市场 A:
  问题: Will Bitcoin exceed $100,000 in January 2025?
  YES价格: $0.6500 (ask: $0.6520)
  NO价格:  $0.3500 (bid: $0.3480)
  流动性:  $125,430 USDC
  结算:   2025-01-31
  链接:   https://polymarket.com/event/market?market=0x1234...

市场 B:
  问题: Will Bitcoin exceed $95,000 in January 2025?
  YES价格: $0.7200 (ask: $0.7220)
  NO价格:  $0.2800 (bid: $0.2780)
  流动性:  $98,200 USDC
  结算:   2025-01-31
  链接:   https://polymarket.com/event/market?market=0x5678...

[套利详情]
───────────────────────────────────────────────────────────
逻辑关系: implies_ab
置信度:   95%
利润率:   7.53%

操作:
  1. 买入市场A的YES @ $0.652
  2. 买入市场B的NO @ $0.278
  成本: $0.930 → 保证回报: $1.00

[LLM 完整推理]
───────────────────────────────────────────────────────────
(此处显示LLM的完整推理过程...)

[风险提示]
───────────────────────────────────────────────────────────
- 需人工验证蕴含方向是否正确
- 检查结算规则是否兼容
- 在 Polymarket 上确认当前价格

══════════════════════════════════════════════════════════════

[验证模式] 操作 (Enter=继续,s=保存,f=误报,q=退出,d=详情,r=阈值,l=流动性,j=存文件,?=帮助): _
```

### 验证模式输出文件

| 文件 | 说明 |
|------|------|
| `output/scan_*.json` | 正式报告（保存的机会） |
| `output/false_positives_*.json` | 误报日志 |
| `output/discovered_opportunities_*.json` | 所有发现的机会（使用 `--verify-auto-save` 时） |
| `output/opportunity_<id>_<timestamp>.json` | 单个机会的详细JSON（使用 `j` 命令保存） |

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
    "semantic_threshold": 0.85,
    "_分页配置": {
      "_enable_full_fetch": "是否启用全量获取（false=保持旧行为，最多100个市场）",
      "_fetch_page_size": "每页大小（默认100）",
      "_fetch_max_per_tag": "每个tag最大获取数量（0=全量获取）",
      "_fetch_rate_limit": "API请求速率限制，每秒请求数（默认2.0）"
    },
    "enable_full_fetch": false,
    "fetch_page_size": 100,
    "fetch_max_per_tag": 0,
    "fetch_rate_limit": 2.0
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

## 🏷️ 标签验证工具

系统提供了标签验证工具 `scripts/tag_validator.py`，用于检测和更新标签配置。

### 功能说明

1. **检查配置** - 对比当前配置与API实际标签，找出差异
2. **更新配置** - 自动添加缺失的有效标签，移除空标签
3. **生成报告** - 输出完整的标签市场数统计报告

### 使用方法

```bash
# 检查当前配置状态
python scripts/tag_validator.py --check

# 预览更新（不实际修改）
python scripts/tag_validator.py --update --dry-run

# 执行更新（自动备份原配置）
python scripts/tag_validator.py --update --min-markets 10

# 生成完整报告
python scripts/tag_validator.py --report --output tag_report.md

# 指定领域
python scripts/tag_validator.py --check --domain crypto
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--check` | 检查当前配置 |
| `--update` | 更新配置文件 |
| `--min-markets` | 最小市场数阈值，只添加市场数>=此值的标签 |
| `--dry-run` | 预览变更，不实际修改 |
| `--keep-empty` | 保留空标签不移除 |
| `--report` | 生成完整报告 |

## 📉 单调性违背检测

单调性违背检测用于发现加密货币阈值市场的价格倒挂机会。

### 什么是单调性违背？

对于同一标的（如BTC）的两个阈值市场：
- 如果阈值A < 阈值B，则价格A应该 >= 价格B（YES价格）
- 当出现价格A < 价格B时，存在单调性违背

### 使用场景

```
市场A: BTC > $100k  YES价格 = 0.40
市场B: BTC > $90k   YES价格 = 0.50  ← 违背单调性！

套利策略: 买A的YES @ 0.40, 买B的NO @ 0.50
如果BTC > $100k: A YES = $1, B NO = $0.5 → 总收益 $1.5
如果BTC <= $100k: A NO = $1, B YES = $1 → 总收益 $2
```

### 运行单调性检测

```bash
# 基础扫描
python local_scanner_v2.py --domain crypto --monotonicity-check

# 指定子类别
python local_scanner_v2.py -d crypto --monotonicity-check --subcat btc,eth

# 组合参数
python local_scanner_v2.py -d crypto --monotonicity-check --refresh
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
