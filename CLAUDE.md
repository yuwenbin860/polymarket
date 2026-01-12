# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Polymarket Combination Arbitrage System - An automated trading system that identifies pricing inefficiencies in prediction markets on Polymarket. The system uses LLMs to analyze logical relationships between markets and detect arbitrage opportunities.

**Core Strategy Types:**
- **Exhaustive Set Arbitrage**: Mutually exclusive outcomes that collectively form a complete set are underpriced (total < $1)
- **Implication Arbitrage**: When Event A implies Event B (A -> B), but P(B) < P(A)
- **Equivalent Market Arbitrage**: Different formulations of the same event have price discrepancies

## Running the System

```bash
# Install dependencies
pip install -r requirements.txt

# Set LLM provider (choose one)
export OPENAI_API_KEY="sk-..."      # OpenAI
export DEEPSEEK_API_KEY="sk-..."    # DeepSeek (recommended, low cost)
export LLM_PROVIDER=deepseek        # Or: openai, anthropic, aliyun, zhipu, ollama

# Run main scanner
python local_scanner_v2.py

# Run MVP version (with simulated data)
python polymarket_arb_mvp.py
```

**Using config file instead of environment variables:**
```bash
cp config.example.json config.json
# Edit config.json with your provider and api_key, then run:
python local_scanner_v2.py
```

**LLM配置加载优先级:**
1. 命令行 `--profile` 参数 (最高优先级)
2. `config.json` 中的 `llm.provider` + `llm.api_key`
3. 环境变量自动检测 (DEEPSEEK_API_KEY, SILICONFLOW_API_KEY等)
4. 默认值/规则匹配 (最低优先级)

## Architecture

### Entry Points

| File | Purpose |
|------|---------|
| `local_scanner_v2.py` | Main scanner with multi-LLM support |
| `polymarket_arb_mvp.py` | MVP version with simulated data support |
| `phase0_verify.py` | Phase 0 verification script |

### Core Components

```
ArbitrageScanner (local_scanner_v2.py:562)
    ├── PolymarketClient - Fetches market data from Gamma API
    ├── LLMAnalyzer - Analyzes logical relationships using LLM
    ├── ArbitrageDetector - Detects arbitrage opportunities
    └── SimilarityFilter - Finds similar market pairs
```

### LLM Provider Abstraction

`llm_providers.py` provides a unified interface for multiple LLM providers:

```python
from llm_providers import create_llm_client

# Auto-detects provider from environment variables
client = create_llm_client()

# Or specify explicitly
client = create_llm_client(provider="deepseek", model="deepseek-chat")
```

**Supported providers**: OpenAI, Anthropic, DeepSeek, Aliyun (Qwen), Zhipu (GLM), Ollama, OpenAI-compatible endpoints

### Data Flow

1. **Fetch Markets** - `PolymarketClient.get_markets()` queries Gamma API
2. **Group by Event** - Markets grouped by `event_id` for exhaustive set detection
3. **Exhaustive Set Check** - `ArbitrageDetector.check_exhaustive_set()` finds underpriced complete sets
4. **Similarity Filter** - `SimilarityFilter.find_similar_pairs()` uses Jaccard similarity
5. **LLM Analysis** - `LLMAnalyzer.analyze()` determines logical relationships (IMPLIES_AB, IMPLIES_BA, EQUIVALENT, etc.)
6. **Arbitrage Detection** - `ArbitrageDetector.check_pair()` validates price constraints
7. **Report Generation** - JSON output to `./output/scan_*.json`

### Configuration

`config.py` defines three config classes:
- `LLMSettings`: Provider, model, API keys, generation params
- `ScanSettings`: Market limits, thresholds, filters
- `OutputSettings`: Directories, logging

Config loading priority: `--config` argument > `config.json` > environment variables > defaults

### Key Data Structures

- `Market` (local_scanner_v2.py:60): Core market entity with prices, liquidity, event info
- `RelationType` (local_scanner_v2.py:50): Enum for logical relationships
- `ArbitrageOpportunity` (local_scanner_v2.py:80): Detected arbitrage with execution instructions

### Arbitrage Detection Logic

**Exhaustive Set** (local_scanner_v2.py:386):
- Condition: `sum(yes_prices) < 0.98` (allows 2% for slippage/gas)
- Action: Buy YES on all markets in the set

**Implication** (local_scanner_v2.py:428):
- If A -> B, then P(B) >= P(A)
- When violated: Buy B's YES, Buy A's NO
- Cost: `P(B) + (1 - P(A))`, Return: $1.00 minimum

**Equivalent Markets** (local_scanner_v2.py:468):
- Spread threshold: 3%
- Action: Buy YES on cheaper, Buy NO on expensive

## Supported LLM Providers

| Provider | Env Var | Cost | Best For |
|----------|---------|------|----------|
| OpenAI | `OPENAI_API_KEY` | Medium | High accuracy |
| Anthropic | `ANTHROPIC_API_KEY` | Medium | Complex reasoning |
| DeepSeek | `DEEPSEEK_API_KEY` | Low | Daily use (recommended) |
| Aliyun | `DASHSCOPE_API_KEY` | Low | China network |
| Zhipu | `ZHIPU_API_KEY` | Medium | China network |
| Ollama | (local) | Free | Offline/testing |

## Development Notes

- All LLM providers implement `BaseLLMClient` with `chat()` and `chat_with_history()` methods
- The system falls back to rule-based analysis if LLM initialization fails
- Similarity calculation uses Jaccard index with stop-word filtering
- Market data comes from Polymarket Gamma API: `https://gamma-api.polymarket.com`
- Output reports are saved as JSON with timestamp: `scan_YYYYMMDD_HHMMSS.json`

## Important Constraints

- Every arbitrage opportunity requires **manual review** before execution
- LLM confidence threshold defaults to 0.8
- Minimum profit percentage defaults to 2%
- Markets are filtered by minimum liquidity (default: $10,000 USDC)
- LLM calls are limited per scan (default: 30) to control costs

## Development Principles / 开发准则

### 1. 小步快跑 (Incremental Progress)
- 将宏大目标拆分为小目标和具体实现步骤
- 每个小目标独立验证后再进行下一步
- 避免一次性做太多，保持每步可验证

### 2. 进度持久化 (Progress Persistence)
- **里程碑和阶段进度** → 更新到 `docs/WORK_PLAN.md`
  - 阶段完成度、版本节点、任务状态
  - 用于查看下一步工作方向
- **详细工作日志** → 记录到 `docs/PROGRESS.md`
  - 每次会话的具体变更
  - Bug修复、代码变更等明细
- 确保可以在任何时间、任何地点恢复工作上下文

### 3. 开放创新 (Open Innovation)
- 欢迎任何能改进套利系统的新点子
- 新点子需经确认后记录到 `docs/PROJECT_BIBLE.md` 的扩展计划
- 保持系统活力，不断迭代优化

### 4. 核心聚焦 (Core Focus)
- **套利是核心中的核心** - 如何找到套利机会、如何利用LLM辅助发现套利关系
- 第一步重心：组合套利（完备集、包含关系、等价市场）
- 预留不同套利模式的接入口（跨平台、时间套利等）
- 执行和下单可以暂时人工，发现机会才是关键

### 5. LLM赋能 (LLM Empowerment)
- 组合套利需要大量语义分析和逻辑分析
- **最大化利用LLM** 来识别市场间的逻辑关系
- 持续优化Prompt，提高关系识别准确率
- 探索多模型协作、验证等高级用法

### 6. 实证优先 (Evidence-First Approach)
- **先验证真实套利机会存在，再设计识别算法**
- 正确流程：人工发现案例 → 验证是套利 → 设计算法 → 实现测试
- 每种新套利类型，必须先有至少1个真实案例
- 避免"闭门造车"——实践出真知

### 7. 策略迭代 (Strategy Evolution)
- **发现新套利策略时，及时提出并更新到项目圣经**
- 新发现先记录到创意池（PROJECT_BIBLE第15章）
- 人工验证可行性后，正式更新到套利策略章节（第4章）
- 保持项目圣经作为"活文档"，持续演进

### 8. Rules分析优先 (Rules-First Analysis)
- **在进行任何语义分析或向量化分析之前，必须先读取并理解Event的description字段**
- Event的description包含完整的resolution rules（判定规则、数据源、特殊条件等）
- 这些rules决定了市场的真正含义，忽略rules会导致错误分析和套利失败
- 实现要求：
  1. 使用`PolymarketClient.get_markets_by_tag()`获取包含完整event_description的市场数据
  2. LLM分析时传入`event_description`字段
  3. 向量化时结合question + description进行embedding
  4. 检查rules兼容性（结算来源、日期、边界处理）

**示例**：
```python
# 获取包含rules的市场数据
markets = client.get_markets_by_tag_slug("crypto")

# 访问rules信息
for m in markets:
    rules = m.full_description  # 优先使用event_description
    # 将rules传递给LLM和向量化系统
```

## Project Guidance

**`docs/PROJECT_BIBLE.md` is the authoritative guide** for all project work. It contains:
- Complete strategy analysis and market background
- Detailed technical architecture and API reference
- Development roadmap (Phase 1-5) with task breakdown
- Risk management guidelines and manual review checklist
- All appendices and FAQs

When making decisions about features, architecture changes, or priorities, always reference `docs/PROJECT_BIBLE.md` first.

## References

- `docs/PROJECT_BIBLE.md` - Comprehensive project documentation (authoritative guide)
- `docs/WORK_PLAN.md` - Work plan, milestones, and phase status (check for next steps)
- `docs/PROGRESS.md` - Detailed work logs and session records
- `README.md` - Quick start guide
- `config.example.json` - Configuration template
