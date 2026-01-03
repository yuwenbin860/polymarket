# Polymarket 组合套利系统

一个用于识别Polymarket预测市场中逻辑定价违规套利机会的自动化系统。

## 🎯 核心功能

1. **完备集套利** - 检测互斥且完备的市场组合是否总价<1
2. **包含关系套利** - 检测逻辑包含关系是否被价格违反
3. **LLM辅助分析** - 使用AI分析市场间的逻辑关系
4. **多LLM支持** - 支持OpenAI、Claude、DeepSeek、通义、GLM、Ollama等
5. **真实订单簿价格** - 使用CLOB API获取best_bid/best_ask，而非最后成交价
6. **三层验证架构** - 数学验证 + LLM找碴验证 + 双模型交叉验证

## 📁 项目结构

```
polymarket_arb/
├── PROJECT_BIBLE.md         # 📖 项目完整文档（必读）
├── local_scanner_v2.py      # 主程序（支持多LLM + 订单簿价格）
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

**方式A: 使用 --profile 预设配置（推荐）**
```bash
# 设置API Key
export DEEPSEEK_API_KEY="sk-..."

# 使用预设配置运行
python local_scanner_v2.py --profile deepseek
python local_scanner_v2.py --profile siliconflow
python local_scanner_v2.py --profile ollama

# 查看所有可用配置
python llm_config.py --list
```

**方式B: 使用 config.json**
```bash
cp config.example.json config.json
# 编辑 config.json 填入 provider 和 api_key
python local_scanner_v2.py
```

**方式C: 使用环境变量**
```bash
export DEEPSEEK_API_KEY="sk-..."
python local_scanner_v2.py  # 自动检测
```

### 3. 配置优先级

```
1. --profile 参数      (最高优先级)
2. config.json 配置
3. 环境变量自动检测
4. 规则匹配模式        (最低优先级，不使用LLM)
```

### 4. 运行扫描

```bash
python local_scanner_v2.py
```

## 🤖 支持的LLM提供商

| 提供商 | 环境变量 | 成本 | 推荐场景 |
|--------|----------|------|----------|
| **SiliconFlow** | `SILICONFLOW_API_KEY` | **低** | **国内聚合平台，速度快** |
| **DeepSeek** | `DEEPSEEK_API_KEY` | **低** | **日常使用** |
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
  "llm": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "api_key": "sk-your-api-key",
    "api_base": "https://api.deepseek.com/v1"
  },
  "scan": {
    "min_profit_pct": 2.0,
    "min_liquidity": 10000
  }
}
```

```bash
# 3. 运行（会自动读取config.json）
python local_scanner_v2.py
```

## 🧪 测试Prompt效果

```bash
# 运行所有测试用例
python test_prompts.py

# 指定LLM配置
python test_prompts.py --profile deepseek

# 只运行第一个测试
python test_prompts.py --test 0
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
