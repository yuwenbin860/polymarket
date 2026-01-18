# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Polymarket Combination Arbitrage System** - An automated trading system that identifies pricing inefficiencies in prediction markets on Polymarket. The system uses LLMs to analyze logical relationships between markets and detect arbitrage opportunities.

**Current Version**: v5.5 (Production Ready)

**Core Strategy Types:**
- **Monotonicity Violation**: Price inversions in threshold markets (e.g., BTC>100k vs BTC>95k)
- **Interval Arbitrage**: Coverage relationships in interval markets
- **Exhaustive Set**: Mutually exclusive outcomes underpriced (total < $1)
- **Implication**: When Event A implies Event B (A → B), but P(B) < P(A)
- **Equivalent Markets**: Different formulations of the same event have price discrepancies
- **Temporal Arbitrage**: Time-based cumulative probability violations

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Interactive mode (default)
python local_scanner_v2.py

# With specific configuration
python local_scanner_v2.py --profile deepseek --domain crypto

# List all available strategies
python local_scanner_v2.py --list-strategies

# Debug mode (full pipeline without execution)
python local_scanner_v2.py --mode debug --strategies monotonicity --domain crypto

# Production mode (Real Execution)
python local_scanner_v2.py --mode production --strategies interval --min-apy 20
```

## Configuration

**LLM Provider Setup:**
```bash
# Method 1: Config file (recommended)
cp config.example.json config.json
# Edit config.json with your provider and api_key

# Method 2: Environment variables
export DEEPSEEK_API_KEY="sk-..."
export LLM_PROVIDER=deepseek

# Method 3: Command line
python local_scanner_v2.py --profile deepseek
```

## Architecture Overview

### Modular Structure (v5.4)

```
polymarket/
├── local_scanner_v2.py      # Main entry point (CLI & Orchestrator)
├── web_app.py               # Streamlit Web Dashboard
├── strategies/              # Pluggable strategy system
│   ├── base.py              # Strategy base class
│   ├── registry.py          # Strategy registration
│   ├── monotonicity.py      # Monotonicity violation strategy
│   ├── interval.py          # Interval arbitrage strategy
│   ├── exhaustive.py        # Exhaustive set strategy
│   ├── implication.py       # Implication violation strategy
│   ├── equivalent.py        # Equivalent markets strategy
│   └── temporal.py          # Temporal arbitrage strategy
├── validation_engine.py     # 6-Layer Validation Engine (Risk Control)
├── validators.py            # Mathematical & Oracle validators
├── llm_providers.py         # Multi-LLM abstraction layer
├── semantic_cluster.py      # Vector similarity clustering
├── execution_engine.py      # Transaction execution & Pre-flight check
├── backtest_engine.py       # Historical backtesting system
├── notifier.py              # Telegram/WeChat notification system
└── config.py                # Configuration management
```

### Core Components

**Scanner Flow:**
```
PolymarketClient → Market Data (Gamma API + CLOB API)
    ↓
Strategy Selection (user choice)
    ↓
Strategy.scan() → Opportunities
    ↓
Validation Engine (6 Layers)
    1. LLM Semantic Analysis
    2. Oracle/Rule Consistency
    3. Math/VWAP/Slippage
    4. APY Calculation
    5. Human Review Checklist
    6. Pre-flight Check
    ↓
Execution Engine (if mode=production)
    ↓
Output → JSON Report / Notification / DB
```

## Development Principles

This project follows **11 core development principles** documented in:
- **`.claude/skills/polymarket-dev-guidelines/SKILL.md`** - Complete 11 principles
- **`docs/PROJECT_BIBLE.md` Chapter 2** - Detailed explanations

**Quick Reference:**
1. 小步快跑 (Incremental Progress)
2. 进度持久化 (Progress Persistence) → Update `docs/PROGRESS.md`
3. 开放创新 (Open Innovation)
4. 核心聚焦 (Core Focus) - Arbitrage discovery > Execution
5. LLM赋能 (LLM Empowerment)
6. 实证优先 (Evidence-First Approach)
7. 策略迭代 (Strategy Evolution)
8. Rules分析优先 (Rules-First Analysis)
9. 交互优先 (Interactive-First)
10. 渐进披露 (Progressive Disclosure)
11. 即时反馈 (Immediate Feedback)
12. 可扩展架构 (Extensible Architecture)

## Project Documentation

**Authoritative Guide:**
- **`docs/PROJECT_BIBLE.md`** - Complete project documentation, strategy analysis, technical architecture

**Work Planning:**
- **`docs/WORK_PLAN.md`** - Milestones, phase status, next steps
- **`docs/PROGRESS.md`** - Detailed work logs and session records

**Quick References:**
- `README.md` - User guide and troubleshooting
- `config.example.json` - Configuration template

## Important Constraints

- Every arbitrage opportunity requires **manual review** before execution (unless in highly trusted automated mode)
- LLM confidence threshold: 0.8 (default)
- Minimum profit percentage: 2% (default)
- Minimum market liquidity: $10,000 USDC (default)
- Minimum APY: 15% (default)

## Key APIs

**Polymarket Data:**
- Gamma API: `https://gamma-api.polymarket.com`
- CLOB API: `https://clob.polymarket.com` (for order book depth & execution)

**Output:**
- Scan reports: `./output/scan_YYYYMMDD_HHMMSS.json`
- Logs: Console output with rich formatting

---

**Version**: v5.5
**Last Updated**: 2026-01-17
