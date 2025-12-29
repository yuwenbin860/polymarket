# Polymarket 组合套利系统

一个用于识别Polymarket预测市场中逻辑定价违规套利机会的自动化系统。

## 🎯 核心功能

1. **完备集套利** - 检测互斥且完备的市场组合是否总价<1
2. **包含关系套利** - 检测逻辑包含关系是否被价格违反
3. **LLM辅助分析** - 使用AI分析市场间的逻辑关系
4. **多LLM支持** - 支持OpenAI、Claude、DeepSeek、通义、GLM、Ollama等

## 📁 项目结构

```
polymarket_arb/
├── PROJECT_BIBLE.md         # 📖 项目完整文档（必读）
├── local_scanner_v2.py      # 主程序（支持多LLM）
├── llm_providers.py         # LLM提供商抽象层
├── config.py                # 配置管理
├── config.example.json      # 配置文件示例
├── polymarket_arb_mvp.py    # MVP版本（模拟数据）
├── requirements.txt         # 依赖列表
└── README.md                # 本文件
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install requests httpx
```

### 2. 配置LLM（任选一个）

```bash
# 方式A: OpenAI
export OPENAI_API_KEY="sk-..."

# 方式B: DeepSeek（推荐，低成本）
export DEEPSEEK_API_KEY="sk-..."
export LLM_PROVIDER=deepseek

# 方式C: 阿里云通义千问
export DASHSCOPE_API_KEY="sk-..."
export LLM_PROVIDER=aliyun

# 方式D: 本地Ollama（免费）
ollama serve  # 先启动服务
ollama pull llama3.1:8b
export LLM_PROVIDER=ollama
```

### 3. 运行扫描

```bash
python local_scanner_v2.py
```

## 🤖 支持的LLM提供商

| 提供商 | 环境变量 | 成本 | 推荐场景 |
|--------|----------|------|----------|
| OpenAI | `OPENAI_API_KEY` | 中 | 高精度需求 |
| Claude | `ANTHROPIC_API_KEY` | 中 | 复杂推理 |
| **DeepSeek** | `DEEPSEEK_API_KEY` | **低** | **日常使用** |
| 阿里云 | `DASHSCOPE_API_KEY` | 低 | 国内网络 |
| 智谱GLM | `ZHIPU_API_KEY` | 中 | 国内网络 |
| **Ollama** | (本地) | **免费** | **离线/测试** |

## 📋 使用配置文件

```bash
# 1. 复制示例配置
cp config.example.json config.json

# 2. 编辑配置
{
  "llm": {
    "provider": "deepseek",
    "model": "deepseek-chat"
  },
  "scan": {
    "min_profit_pct": 2.0,
    "min_liquidity": 10000
  }
}

# 3. 运行
python local_scanner_v2.py
```

## 📚 详细文档

**请阅读 [PROJECT_BIBLE.md](./PROJECT_BIBLE.md)** 了解：

- 完整的策略原理和市场背景
- 系统架构和技术设计
- 开发路线图和任务分解
- 风险管理和人工复核清单
- API参考和常见问题

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

1. **逻辑关系误判** - 所有机会需人工复核
2. **结算规则差异** - 仔细阅读每个市场的规则
3. **流动性风险** - 检查订单簿深度
4. **单笔限制** - 建议不超过总资金10%

## 📄 License

MIT License

---

**免责声明**: 本工具仅供学习研究使用。预测市场交易有风险，请自行评估并承担风险。
