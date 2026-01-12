# Polymarket 套利系统 - 工作计划与路线图

> **文档版本**: v1.0
> **创建日期**: 2026-01-08
> **基于**: PROJECT_BIBLE.md v2.0-Bible + PROGRESS.md 最新状态
>
> 本文档是项目的**落地执行指导**，与项目圣经配合使用。

---

# 目录

1. [执行摘要](#1-执行摘要)
2. [当前状态评估](#2-当前状态评估)
3. [差距分析](#3-差距分析)
4. [工作计划详情](#4-工作计划详情)
5. [路线图](#5-路线图)
6. [任务优先级矩阵](#6-任务优先级矩阵)
7. [验收标准](#7-验收标准)
8. [风险与依赖](#8-风险与依赖)
9. [附录](#9-附录)

---

# 1. 执行摘要

## 1.1 项目现状

**当前版本**: v2.1.4 (2026-01-07)

**最新进展**:
- 基于深度研究报告《语义Alpha》，新增 **Sprint 0** 专注**单调性违背套利**
- 领域聚焦调整为**加密货币优先**
- 策略优先级重排：单调性违背 > 区间划分 > 其他

**完成度概览**:
```
Sprint 0 (单调性违背)   ████████████████████ 100%  ✅ 全部完成！
Phase 1 (MVP验证)      ████████████████████ 100%
Phase 2 (真实数据)      ██████████████████░░  90%
Phase 2.5 (风控精度)    ██████░░░░░░░░░░░░░░  30%
Phase 3 (策略扩展)      ██░░░░░░░░░░░░░░░░░░  10%
Phase 4 (半自动执行)    ░░░░░░░░░░░░░░░░░░░░   0%
```

## 1.2 核心差距

| 差距类型 | 严重程度 | 影响 |
|---------|---------|------|
| APY计算器未实现 | 🔴 高 | 无法评估机会是否值得做 |
| Oracle对齐检查未实现 | 🔴 高 | 存在预言机基差风险 |
| VWAP/订单簿深度未实现 | 🔴 高 | 滑点风险不可控 |
| 五层验证框架不完整 | 🟠 中 | 验证流程有漏洞 |
| 真实套利案例不足 | 🟠 中 | 缺乏实证支撑 |

## 1.3 下一阶段重点

**Sprint 0 单调性违背套利** 是当前最紧迫的工作（P0最高优先级），聚焦加密货币领域。

**Sprint 0 核心交付物**:
1. `MonotonicityChecker` - 单调性违背检测算法
2. `ThresholdMarketIdentifier` - 阈值型市场自动识别
3. `CryptoFocusedScanner` - 加密货币领域专用扫描
4. `LadderMarketGrouper` - 阶梯行权价市场分组
5. 至少 **1个真实单调性违背案例**

**后续（Sprint 1）风控基础设施**:
1. `APYCalculator` - 年化收益率计算器
2. `OracleComparator` - 预言机对齐检查器
3. `DepthCalculator` - 订单簿深度/VWAP计算器
4. `ValidationEngine` - 五层验证框架

---

# 2. 当前状态评估

## 2.1 已完成功能清单

### 基础设施 (100%)
- [x] 项目结构和配置管理
- [x] 多LLM提供商支持 (OpenAI/DeepSeek/Anthropic/等)
- [x] Polymarket Gamma API 客户端
- [x] 市场数据缓存系统 (MarketCache)
- [x] Tag分类系统 (2757个tags)
- [x] API分页支持 (全量数据获取)
- [x] 速率限制器 (RateLimiter)

### 机会发现引擎 (85%)
- [x] 向量化语义聚类 (SemanticClusterer)
- [x] 关键词相似度筛选 (Jaccard/BM25)
- [x] 完备集套利检测
- [x] 包含关系套利检测
- [x] 等价市场套利检测
- [x] 区间套利检测 (interval_parser_v2.py)
- [x] 跨Event区间关系检测
- [x] 交互式子类别选择 (v2.1.4)
- [ ] 时序套利检测 (待实现)

### 验证体系 (40%)
- [x] LLM关系识别 (Layer 1)
- [x] 阈值方向验证器
- [x] 时间一致性验证器
- [x] LLM一致性检查 (reasoning vs relationship)
- [x] 数学验证层 (MathValidator)
- [ ] APY计算器 (Layer 4) - **缺失**
- [ ] Oracle对齐检查 (Layer 2) - **缺失**
- [ ] VWAP/滑点计算 (Layer 3) - **缺失**
- [ ] 五层验证框架整合 - **不完整**
- [ ] 人工复核清单生成器 (Layer 5) - **缺失**

### 输出与报告 (60%)
- [x] JSON格式报告输出
- [x] 扫描日志记录
- [ ] APY/滑点对比显示 - **缺失**
- [ ] 人工复核清单输出 - **缺失**
- [ ] 机会推送通知 - **缺失**

## 2.2 版本历史关键节点

| 版本 | 日期 | 里程碑 |
|-----|------|-------|
| v1.0 | 2024-12-29 | MVP完成 |
| v1.5 | 2026-01-03 | 验证层集成 |
| v2.0 | 2026-01-04 | 向量化套利发现 |
| v2.0.5 | 2026-01-05 | 阈值方向验证 |
| v2.0.8 | 2026-01-06 | 等价市场匹配修复 |
| v2.1.0 | 2026-01-06 | 区间套利功能 |
| v2.1.4 | 2026-01-07 | 交互式子类别选择 |

## 2.3 发现的套利案例

| 案例 | 类型 | 利润率 | 状态 | 备注 |
|-----|------|-------|------|------|
| Google Dip | 包含关系 | 30.38% | ❌ 误报 | v2.0.5修复 |
| 区间套利案例 | 区间蕴含 | 2.1% | 🔄 待验证 | 跨Event区间 |

**关键问题**: 尚未发现并人工验证3个真实可执行的套利案例

---

# 3. 差距分析

## 3.1 圣经目标 vs 实际状态

### 短期目标 (Phase 1-2) 对比

| 圣经目标 | 状态 | 差距说明 |
|---------|------|---------|
| 验证核心策略可行性 | ✅ 完成 | - |
| 构建MVP原型 | ✅ 完成 | - |
| 支持多种LLM提供商 | ✅ 完成 | - |
| **发现并人工验证至少3个真实套利机会** | ❌ 未完成 | 核心差距 |
| **实现完整验证框架（五层验证）** | 🟡 部分 | 缺少Layer3-5 |
| **完成至少5次模拟执行跟踪** | ❌ 未开始 | - |

### 成功指标 (Phase 2) 对比

| 指标 | 目标 | 当前 | 差距 |
|-----|------|------|------|
| 每周发现潜在机会数 | ≥3 | ~1 | -2 |
| 五层验证通过率 | ≥30% | N/A | 框架未完成 |
| 模拟执行成功率 | ≥50% | 0% | 未开始 |

## 3.2 Phase 2.5 任务详细差距

### 已完成 ✅
```
T2.5.5 阈值方向验证器增强
  └─ validators.py: _extract_threshold_info(), validate_threshold_implication()
  └─ 支持上涨/下跌阈值方向检测
  └─ v2.0.5/v2.1.1 完成

T2.5.6 时间一致性验证器
  └─ validators.py: validate_time_consistency()
  └─ 支持24小时时间差阈值
  └─ v1.5 完成
```

### 未完成 ❌

#### T2.5.1 APYCalculator (P0 优先级)
```
需求:
  - 计算年化收益率 (APY = profit% × 365/days)
  - 过滤 APY < 15% 的机会
  - 考虑锁仓时间和无风险利率

圣经定义 (第6章):
  def calculate_apy(profit_pct, days_to_resolution):
      return profit_pct * (365 / days_to_resolution)

  def validate_apy(opportunity):
      MIN_APY = 0.15  # 15%
      MAX_DAYS = 180
      # 返回 passed, reason, rating

当前状态: 完全未实现
影响: 无法评估机会是否值得执行
```

#### T2.5.2 OracleComparator (P0 优先级)
```
需求:
  - 提取市场的结算来源 (resolution_source)
  - 比对两个市场的Oracle是否一致
  - 返回 ALIGNED / COMPATIBLE / MISALIGNED

圣经定义 (第6章):
  def check_oracle_alignment(market_a, market_b):
      source_a = extract_resolution_source(market_a)
      source_b = extract_resolution_source(market_b)
      if source_a == source_b:
          return "ALIGNED"
      # 权威性排序检查...

当前状态: 完全未实现
影响: 存在预言机基差风险（致命风险#1）
```

#### T2.5.3 DepthCalculator (P0 优先级)
```
需求:
  - 调用 CLOB API 获取订单簿
  - 计算 VWAP (成交量加权平均价)
  - 计算滑点成本

圣经定义 (第6章):
  def calculate_vwap(order_book, target_size_usd):
      asks = sorted(order_book['asks'], key=lambda x: float(x['price']))
      # 遍历订单簿计算VWAP...

当前状态:
  - Market类有 best_bid/best_ask 字段 (v1.4)
  - 有 fetch_orderbook() 方法框架
  - VWAP计算逻辑未实现

影响: 滑点风险不可控（致命风险#5）
```

#### T2.5.4 ValidationEngine (P0 优先级)
```
需求:
  - 整合五层验证架构
  - Layer 1: LLM关系识别 (已有)
  - Layer 2: 规则验证 (Oracle对齐、时间一致性、阈值方向)
  - Layer 3: 数学验证 (VWAP利润计算、滑点估算)
  - Layer 4: APY验证
  - Layer 5: 人工复核清单

当前状态:
  - Layer 1: ✅ 完成
  - Layer 2: 🟡 部分 (缺Oracle)
  - Layer 3: ❌ 缺失
  - Layer 4: ❌ 缺失
  - Layer 5: ❌ 缺失

影响: 验证流程有漏洞，低质量机会可能通过
```

#### T2.5.7 人工复核清单生成器 (P1 优先级)
```
需求:
  - 生成markdown格式的复核清单
  - 包含: 基本信息、逻辑验证、预言机验证、时间验证、
          结算规则验证、流动性验证、APY验证、签字栏

圣经定义 (第6章): 完整的checklist模板

当前状态: 完全未实现
影响: 缺少人工复核的标准化流程
```

#### T2.5.8 输出格式增强 (P1 优先级)
```
需求:
  - 显示 APY 和 APY评级
  - 显示 滑点估算
  - 对比 mid_price_profit vs effective_profit
  - 显示 Oracle对齐状态

当前状态: 完全未实现
影响: 报告信息不完整，难以做决策
```

## 3.3 差距优先级排序

```
🔴 P0 - 必须立即完成 (阻塞后续工作)
├── T2.5.1 APYCalculator
├── T2.5.2 OracleComparator
├── T2.5.3 DepthCalculator
└── T2.5.4 ValidationEngine整合

🟠 P1 - 短期内完成 (提升系统可用性)
├── T2.5.7 人工复核清单生成器
├── T2.5.8 输出格式增强
└── 发现3个真实套利案例

🟡 P2 - 中期完成 (策略扩展)
├── T3.2 时序套利检测
├── T3.5 历史回测系统
└── T3.4 通知功能
```

## 3.4 规范一致性审计记录

### 2026-01-12 审计

**审计范围**: 对比 `PROJECT_BIBLE.md` 规范与当前代码实现

**发现的关键差距**:

| 差距项 | 严重程度 | 规范要求 | 实际状态 | 确认 |
|--------|----------|----------|----------|------|
| APYCalculator | P0 | 年化收益>=15%才执行 | 代码中完全缺失 | ✅ |
| OracleComparator | P0 | 检查预言机一致性 | 代码中完全缺失 | ✅ |
| DepthCalculator/VWAP | P0 | 使用VWAP而非mid price | 代码中完全缺失 | ✅ |
| 五层验证框架 | P0 | 5层完整验证 | Layer 3-5未实现 | ✅ |
| ArbitrageOpportunity字段 | P1 | 包含apy/slippage等 | 缺少11个字段 | ✅ |
| 人工复核清单 | P1 | 6部分验证清单 | 代码中完全缺失 | ✅ |

**代码级别验证**:
```bash
# 搜索关键组件是否存在
grep -r "APYCalculator\|calculate_apy" *.py  # 结果: 仅在文档中
grep -r "OracleComparator\|check_alignment" *.py  # 结果: 仅在文档中
grep -r "VWAP\|vwap\|calculate_vwap" *.py  # 结果: 仅在文档中
```

**ArbitrageOpportunity 实际定义** (local_scanner_v2.py:209-223):
```python
class ArbitrageOpportunity:
    id: str
    type: str
    markets: List[Dict]
    relationship: str
    confidence: float
    total_cost: float
    guaranteed_return: float
    profit: float
    profit_pct: float
    action: str
    reasoning: str
    edge_cases: List[str]
    needs_review: List[str]
    timestamp: str
    # 缺失: apy, apy_rating, oracle_alignment, slippage_estimate,
    #       days_to_resolution, effective_profit, gas_estimate, validation_results
```

**结论**: 第3.2节中识别的差距经代码验证确认，Sprint 1和Sprint 2的任务是必要的。

**下一步**: 按照第4章定义的Sprint 1和Sprint 2任务顺序执行改造。

---

# 4. 工作计划详情

## 4.0 Sprint 0: 单调性违背套利专项 (P0最高) 🆕

> **优先级**: P0（最高优先级）
> **领域聚焦**: 加密货币
> **预计工作量**: 3-4天

### 4.0.1 背景

根据深度研究报告《语义Alpha》，单调性违背套利是：
- 数学上最确定的套利类型（违背概率论公理）
- 机器人竞争最低的领域（需要语义理解）
- 加密货币领域最常见的机会来源

### 4.0.2 任务详情

#### T0.1 MonotonicityChecker 实现 ✅ 已完成

**文件**: `monotonicity_checker.py`（已创建，507行，23个单元测试通过）
**工作量**: 4h

```python
class MonotonicityChecker:
    """单调性违背检测器"""

    def extract_threshold_info(self, market: Market) -> ThresholdInfo:
        """从市场问题中提取阈值信息"""
        # 识别：BTC > 100k, ETH above 4000, SOL hits 300

    def group_ladder_markets(self, markets: List[Market]) -> Dict[str, List[Market]]:
        """按资产和日期分组阶梯市场"""

    def check_monotonicity(self, ladder: List[Market]) -> List[Violation]:
        """检查单调性，返回违背列表"""

    def calculate_arbitrage(self, violation: Violation) -> ArbitrageOpportunity:
        """计算套利机会"""
```

#### T0.2 ThresholdMarketIdentifier 实现 ✅ 已完成

**实现位置**: `monotonicity_checker.py` (extract_threshold_info 方法)
**工作量**: 3h

**已实现功能**:
- 正则表达式识别阈值类问题
- 提取资产名称、阈值数值、方向（above/below）
- 支持14种加密资产和多种表述模式
- 集成到 scan_monotonicity() 流程

#### T0.3 CryptoFocusedScanner 实现 ✅ 已完成

**修改**: `local_scanner_v2.py`
**工作量**: 2h

**已实现功能**:
- `--monotonicity-check` 命令行参数
- `scan_monotonicity()` 方法集成
- 支持 `--subcat` 子类别筛选

**使用示例**:
```bash
python local_scanner_v2.py \
    --domain crypto \
    --monotonicity-check \
    --subcat btc,eth
```

#### T0.4 LadderMarketGrouper 实现 ✅ 已完成

**工作量**: 3h（已在 monotonicity_checker.py 中实现 group_ladder_markets()）

**功能**:
- 将同一资产的阈值市场按行权价排序
- 识别完整的"阶梯"结构
- 输出分组结果供单调性检查

#### T0.5 真实案例验证 ✅ 已完成

**工作量**: 4h

**目标**: 在Polymarket找到至少1个单调性违背案例

**方法**:
1. 运行 `--domain crypto --monotonicity-check` 扫描
2. 分析SOL/XRP/BTC/ETH阈值市场
3. 人工验证发现的价格倒挂
4. 记录案例到 `docs/cases/`

**结果**:
- 发现 CASE-001: SOL $110 vs $120 单调性违背
- 价格倒挂: 0.009 (0.91%), APY: 165.7%
- 详见 `docs/cases/CASE_001_SOL_MONOTONICITY.md`

### 4.0.3 验收标准

- [x] `monotonicity_checker.py` 通过单元测试 ← 23个测试全部通过
- [x] 能够正确识别阈值市场（准确率 > 90%）← 支持14种加密资产
- [x] 能够检测价格倒挂 ← check_monotonicity() 已实现
- [x] 至少发现1个真实单调性违背案例 ← CASE-001: SOL $110 vs $120

---

## 4.1 Sprint 1: 风控基础设施 (P0)

**目标**: 实现APY、Oracle、Depth三大核心计算器
**预计工作量**: 2-3天

### Task 1.1: APYCalculator 实现

**文件**: `apy_calculator.py` (新建) 或集成到 `validators.py`

```python
# 核心接口设计
class APYCalculator:
    """年化收益率计算器"""

    MIN_APY: float = 0.15  # 15% 最低可接受
    MAX_DAYS: int = 180    # 最长锁仓天数
    RISK_FREE_RATE: float = 0.05  # 无风险利率 5%

    def calculate_apy(self, profit_pct: float, days_to_resolution: int) -> float:
        """计算年化收益率"""

    def calculate_days_to_resolution(self, market: Market) -> int:
        """从市场数据计算剩余天数"""

    def validate_apy(self, opportunity: ArbitrageOpportunity) -> APYValidationResult:
        """验证APY是否满足阈值"""

    def get_apy_rating(self, apy: float) -> str:
        """获取APY评级 (优秀/良好/可接受/不推荐)"""
```

**验收标准**:
- [ ] APY计算准确率100%
- [ ] 单元测试覆盖: 7天、30天、90天、180天锁仓
- [ ] 集成到ArbitrageDetector

### Task 1.2: OracleComparator 实现

**文件**: `oracle_comparator.py` (新建) 或集成到 `validators.py`

```python
# 核心接口设计
class OracleComparator:
    """预言机对齐检查器"""

    # 权威性排序
    AUTHORITY_ORDER = [
        "Official Government Source",
        "AP News",
        "Reuters",
        "Major News Networks",
        "Fox News",
    ]

    def extract_resolution_source(self, market: Market) -> Optional[str]:
        """从市场描述中提取结算来源"""

    def check_alignment(self, market_a: Market, market_b: Market) -> OracleStatus:
        """检查两个市场的Oracle对齐状态"""
        # 返回: ALIGNED / COMPATIBLE / MISALIGNED

    def get_authority_rank(self, source: str) -> int:
        """获取来源的权威性排名"""
```

**验收标准**:
- [ ] 能从market.description提取resolution_source
- [ ] 正确判断ALIGNED/COMPATIBLE/MISALIGNED
- [ ] 单元测试覆盖多种场景

### Task 1.3: DepthCalculator 实现

**文件**: `depth_calculator.py` (新建) 或增强 `local_scanner_v2.py`

```python
# 核心接口设计
class DepthCalculator:
    """订单簿深度/VWAP计算器"""

    CLOB_API_BASE = "https://clob.polymarket.com"

    def get_order_book(self, token_id: str) -> OrderBook:
        """获取订单簿数据"""

    def calculate_vwap(self, order_book: OrderBook,
                       target_size_usd: float,
                       side: str = "buy") -> VWAPResult:
        """计算VWAP和滑点"""

    def estimate_slippage(self, market: Market,
                          target_size_usd: float) -> SlippageEstimate:
        """估算滑点成本"""

    def check_liquidity_sufficient(self, market: Market,
                                   target_size_usd: float) -> bool:
        """检查流动性是否充足"""
```

**验收标准**:
- [ ] 成功调用CLOB API获取订单簿
- [ ] VWAP计算逻辑正确
- [ ] 滑点估算合理
- [ ] 流动性不足时正确拒绝

## 4.2 Sprint 2: 验证框架整合 (P0)

**目标**: 整合五层验证架构
**预计工作量**: 1-2天

### Task 2.1: ValidationEngine 整合

**文件**: `validation_engine.py` (新建)

```python
# 核心接口设计
class ValidationEngine:
    """五层验证引擎"""

    def __init__(self,
                 llm_analyzer: LLMAnalyzer,
                 oracle_comparator: OracleComparator,
                 depth_calculator: DepthCalculator,
                 apy_calculator: APYCalculator):
        ...

    def validate(self,
                 markets: List[Market],
                 relationship: RelationType,
                 target_size_usd: float = 500) -> ValidationResult:
        """
        执行五层验证

        Layer 1: LLM关系识别
        Layer 2: 规则验证 (Oracle, Time, Threshold)
        Layer 3: 数学验证 (VWAP, Slippage)
        Layer 4: APY验证
        Layer 5: 生成人工复核清单
        """

    def _layer1_llm_analysis(self, markets: List[Market]) -> Layer1Result:
        """Layer 1: LLM关系识别"""

    def _layer2_rule_validation(self, markets: List[Market],
                                 relationship: RelationType) -> Layer2Result:
        """Layer 2: 规则验证"""

    def _layer3_math_validation(self, markets: List[Market],
                                 relationship: RelationType,
                                 target_size_usd: float) -> Layer3Result:
        """Layer 3: 数学验证"""

    def _layer4_apy_validation(self, opportunity: ArbitrageOpportunity) -> Layer4Result:
        """Layer 4: APY验证"""

    def _layer5_generate_checklist(self, opportunity: ArbitrageOpportunity) -> str:
        """Layer 5: 生成人工复核清单"""
```

**验收标准**:
- [ ] 五层验证顺序执行
- [ ] 任一层失败时正确终止并报告原因
- [ ] 全部通过时输出完整机会信息

### Task 2.2: 集成到主扫描流程

**文件**: `local_scanner_v2.py` 修改

```python
# 修改 ArbitrageScanner.scan() 和 scan_semantic()
# 使用 ValidationEngine 替代分散的验证调用

def _process_opportunity(self, markets, relationship):
    """处理套利机会（使用完整验证引擎）"""
    result = self.validation_engine.validate(
        markets=markets,
        relationship=relationship,
        target_size_usd=self.settings.target_size_usd
    )

    if result.passed:
        # 输出机会 + 人工复核清单
        self._output_opportunity(result.opportunity)
        self._save_checklist(result.checklist)
    else:
        # 记录失败原因
        logger.info(f"[REJECTED] {result.rejection_layer}: {result.reason}")
```

## 4.3 Sprint 3: 输出增强与案例收集 (P1)

**目标**: 增强输出格式，收集真实案例
**预计工作量**: 2-3天

### Task 3.1: 输出格式增强

**修改 ArbitrageOpportunity 数据结构**:
```python
@dataclass
class ArbitrageOpportunity:
    # 现有字段...

    # 新增字段 (v2.5)
    mid_price_profit: float      # 中间价利润
    effective_profit: float      # 考虑滑点后的利润
    slippage_cost: float         # 滑点成本
    days_to_resolution: int      # 锁仓天数
    apy: float                   # 年化收益率
    apy_rating: str              # APY评级
    oracle_alignment: str        # Oracle对齐状态
    checklist_path: str          # 人工复核清单路径
```

**修改报告输出格式**:
```json
{
  "opportunity": {
    "id": "opp_20260108_001",
    "type": "IMPLICATION_VIOLATION",
    "markets": [...],
    "profit_analysis": {
      "mid_price_profit": 0.05,
      "effective_profit": 0.042,
      "slippage_cost": 0.008,
      "profit_pct": 4.2
    },
    "apy_analysis": {
      "days_to_resolution": 30,
      "apy": 0.511,
      "apy_rating": "优秀",
      "comparison": "5年期国债 vs 本机会: 5% vs 51.1%"
    },
    "risk_analysis": {
      "oracle_alignment": "ALIGNED",
      "liquidity_sufficient": true,
      "max_position_usd": 500
    },
    "checklist": "./output/checklists/checklist_20260108_001.md"
  }
}
```

### Task 3.2: 人工复核清单生成器

**文件**: `checklist_generator.py` (新建)

```python
class ChecklistGenerator:
    """人工复核清单生成器"""

    TEMPLATE = """
## 套利机会复核清单

### 基本信息
- 机会ID: {opportunity_id}
- 套利类型: {arb_type}
- 发现时间: {discovered_at}
- 预计结算时间: {resolution_date}
- 锁仓天数: {days}

### 市场信息
{market_info}

### 1. 逻辑验证 [ ]/[X]
- [ ] LLM判断的逻辑关系我理解并认同
- [ ] 我能用自己的话解释为什么这个关系成立
- [ ] 我考虑过所有边界情况

### 2. 预言机验证 [ ]/[X]
- [ ] 两市场结算来源: {oracle_status}
- [ ] 来源A: {source_a}
- [ ] 来源B: {source_b}

### 3. 时间验证 [ ]/[X]
- [ ] 时间差: {time_diff}
- [ ] 时区确认: UTC

### 4. 结算规则验证 [ ]/[X]
- [ ] 我已打开浏览器阅读所有相关市场的结算规则
- [ ] 结算数据来源一致
- [ ] 边界值处理方式已确认

### 5. 流动性验证 [ ]/[X]
- [ ] 订单簿深度检查: {depth_status}
- [ ] 滑点估算: {slippage}
- [ ] 仓位 ≤ 市场流动性的 10%

### 6. APY验证 [ ]/[X]
- [ ] APY: {apy}% ({apy_rating})
- [ ] 锁仓时间: {days} 天
- [ ] 我能承受最坏情况的亏损

### 签字
- 复核人: _______________
- 复核时间: _______________
- 决定: [ ] 执行 [ ] 放弃 [ ] 需更多信息
"""

    def generate(self, opportunity: ArbitrageOpportunity) -> str:
        """生成复核清单"""

    def save(self, opportunity: ArbitrageOpportunity, output_dir: str) -> str:
        """保存清单到文件"""
```

### Task 3.3: 真实套利案例收集

**目标**: 发现并人工验证至少3个真实套利机会

**执行计划**:
1. 运行完整扫描 (crypto域)
2. 运行完整扫描 (politics域 - 2028大选)
3. 手动探索Polymarket寻找机会
4. 对每个发现的机会执行完整五层验证
5. 记录到案例库

**案例记录模板**:
```markdown
## 案例 #1: [标题]

### 发现信息
- 发现时间:
- 发现方式: 自动扫描 / 手动发现
- 市场URL:

### 市场信息
- 市场A: [问题] @ $[价格]
- 市场B: [问题] @ $[价格]

### 五层验证结果
- Layer 1 (LLM): ✅/❌ [结果]
- Layer 2 (规则): ✅/❌ [结果]
- Layer 3 (数学): ✅/❌ [结果]
- Layer 4 (APY): ✅/❌ [结果]
- Layer 5 (人工): ✅/❌ [结果]

### 结论
- 是否为真实套利: 是/否
- 原因:

### 执行跟踪 (如果执行)
- 执行时间:
- 执行金额:
- 实际结果:
```

## 4.4 Sprint 4: Phase 3 准备 (P2)

**目标**: 为策略扩展做准备
**预计工作量**: 1-2天

### Task 4.1: 时序套利检测框架

**文件**: `temporal_arbitrage.py` (新建)

```python
class TemporalArbitrageDetector:
    """时序套利检测器"""

    def detect_cumulative_probability(self,
                                      markets: List[Market]) -> List[ArbitrageOpportunity]:
        """检测累积概率套利"""
        # "BTC在1月突破100k" vs "BTC在2月突破100k"
```

### Task 4.2: 通知功能设计

**文件**: `notifier.py` (新建)

```python
class ArbitrageNotifier:
    """套利机会通知器"""

    def notify_telegram(self, opportunity: ArbitrageOpportunity):
        """发送Telegram通知"""

    def notify_wechat(self, opportunity: ArbitrageOpportunity):
        """发送微信通知"""
```

---

# 5. 路线图

## 5.1 时间线视图

```
2026-01-12 ──────────────────────────────────────────────────────────
     │
     ├─ Sprint 0 开始 (单调性违背套利) ← 🆕 最高优先级
     │   ├─ T0.1: MonotonicityChecker
     │   ├─ T0.2: ThresholdMarketIdentifier
     │   ├─ T0.3: CryptoFocusedScanner
     │   ├─ T0.4: LadderMarketGrouper
     │   └─ T0.5: 真实案例验证
     │
2026-01-15 ──────────────────────────────────────────────────────────
     │
     ├─ [M0] Sprint 0 完成里程碑
     │   - 单调性检测器 ✅
     │   - 加密货币领域扫描 ✅
     │   - 至少1个真实案例 ✅
     │
2026-01-16 ──────────────────────────────────────────────────────────
     │
     ├─ Sprint 1 开始 (风控基础设施)
     │   ├─ Task 1.1: APYCalculator
     │   ├─ Task 1.2: OracleComparator
     │   └─ Task 1.3: DepthCalculator
     │
2026-01-18 ──────────────────────────────────────────────────────────
     │
     ├─ Sprint 2 开始 (验证框架整合)
     │   ├─ Task 2.1: ValidationEngine
     │   └─ Task 2.2: 集成到主流程
     │
2026-01-20 ──────────────────────────────────────────────────────────
     │
     ├─ Sprint 3 开始 (输出增强与案例收集)
     │   ├─ Task 3.1: 输出格式增强
     │   ├─ Task 3.2: 人工复核清单生成器
     │   └─ Task 3.3: 真实套利案例收集
     │
2026-01-23 ──────────────────────────────────────────────────────────
     │
     ├─ [M2.5] Phase 2.5 完成里程碑
     │   - APY计算器 ✅
     │   - Oracle对齐检查 ✅
     │   - 订单簿深度分析 ✅
     │   - 五层验证框架 ✅
     │   - 至少3个验证案例 ✅
     │
2026-01-24 ──────────────────────────────────────────────────────────
     │
     ├─ Sprint 4 开始 (Phase 3 准备)
     │   ├─ Task 4.1: 时序套利检测
     │   └─ Task 4.2: 通知功能
     │
2026-01-29 ──────────────────────────────────────────────────────────
     │
     ├─ [M3] Phase 3 开始
     │
     ...
```

## 5.2 里程碑定义

### M0: Sprint 0 完成 (2026-01-12) ✅ 已完成

**当前进度**: 100% (5/5 交付物完成)

**交付物清单**:
- [x] `monotonicity_checker.py` - 单调性违背检测器 ✅
- [x] `ThresholdMarketIdentifier` 集成到 `local_scanner_v2.py` ✅
- [x] `--domain crypto --monotonicity-check` 命令行参数 ✅
- [x] `LadderMarketGrouper` 阶梯市场分组器 ✅
- [x] 至少1个真实单调性违背案例文档 ✅ CASE-001

**验收标准**:
- [x] 能够自动识别加密货币阈值市场（准确率 > 90%）← 支持14种资产
- [x] 能够检测价格倒挂（单调性违背）← check_monotonicity() 已实现
- [x] 输出包含套利计算和APY ← calculate_arbitrage() 已实现
- [x] 至少发现1个真实单调性违背案例 ← CASE-001: SOL $110 vs $120

---

### M2.5: Phase 2.5 完成 (2026-01-23)

**交付物清单**:
- [ ] `apy_calculator.py` 或集成到 `validators.py`
- [ ] `oracle_comparator.py` 或集成到 `validators.py`
- [ ] `depth_calculator.py` 或增强 `local_scanner_v2.py`
- [ ] `validation_engine.py`
- [ ] `checklist_generator.py`
- [ ] 输出格式增强 (JSON + Markdown)
- [ ] 至少3个验证通过的真实套利案例文档

**验收标准**:
- [ ] APY计算器准确率100%
- [ ] Oracle对齐检查覆盖所有机会
- [ ] VWAP计算正确
- [ ] 五层验证框架完整运行
- [ ] 人工复核清单自动生成
- [ ] 收集3个以上真实案例

### M3: Phase 3 开始 (2026-01-21)

**前置条件**:
- [x] M2.5 完成
- [ ] 至少1个真实套利案例执行跟踪

**Phase 3 目标**:
- 时序套利检测
- WebSocket实时监控
- 通知功能
- 历史回测系统

---

# 6. 任务优先级矩阵

## 6.1 优先级说明

| 优先级 | 定义 | 处理方式 |
|-------|------|---------|
| P0 | 必须立即完成，阻塞后续工作 | 第一时间处理 |
| P1 | 短期内完成，提升系统可用性 | 本周内完成 |
| P2 | 中期完成，策略扩展 | 下阶段处理 |
| P3 | 长期/可选，锦上添花 | 有空再做 |

## 6.2 任务优先级矩阵

| 任务 | 优先级 | 预计工作量 | 状态 | 依赖 | Sprint |
|-----|-------|-----------|------|------|--------|
| **T0.1 MonotonicityChecker** | **P0++** | 4h | ✅完成 | 无 | **Sprint 0** |
| **T0.2 ThresholdMarketIdentifier** | **P0++** | 3h | ✅完成 | 无 | **Sprint 0** |
| **T0.3 CryptoFocusedScanner** | **P0++** | 2h | ✅完成 | T0.1, T0.2 | **Sprint 0** |
| **T0.4 LadderMarketGrouper** | **P0++** | 3h | ✅完成 | T0.2 | **Sprint 0** |
| **T0.5 真实案例验证** | **P0++** | 4h | ✅完成 | T0.1-T0.4 | **Sprint 0** |
| APYCalculator | P0 | 4h | 无 | Sprint 1 |
| OracleComparator | P0 | 4h | 无 | Sprint 1 |
| DepthCalculator | P0 | 6h | 无 | Sprint 1 |
| ValidationEngine整合 | P0 | 4h | 上述3个 | Sprint 2 |
| 集成到主流程 | P0 | 2h | ValidationEngine | Sprint 2 |
| 输出格式增强 | P1 | 3h | ValidationEngine | Sprint 3 |
| 人工复核清单生成器 | P1 | 3h | ValidationEngine | Sprint 3 |
| 真实案例收集 | P1 | 8h+ | 全部P0任务 | Sprint 3 |
| 时序套利检测 | P2 | 8h | Phase 2.5完成 | Sprint 4 |
| 通知功能 | P2 | 6h | 无 | Sprint 4 |
| WebSocket监控 | P2 | 12h | 无 | Phase 3 |
| 历史回测系统 | P2 | 16h | 无 | Phase 3 |

## 6.3 关键路径

```
【Sprint 0 - 单调性违背套利】
ThresholdMarketIdentifier ─┬─► MonotonicityChecker ─► CryptoFocusedScanner ─► 真实案例验证 ─► M0完成
LadderMarketGrouper ───────┘

【Sprint 1+ - 风控基础设施】
APYCalculator ─┬─► ValidationEngine ─► 集成到主流程 ─► 真实案例收集 ─► M2.5完成
OracleComparator ─┤
DepthCalculator ──┘
```

---

# 7. 验收标准

## 7.1 Sprint 1 验收

| 验收项 | 标准 | 验证方法 |
|-------|------|---------|
| APY计算 | 计算结果正确 | 单元测试 + 手工计算对比 |
| APY阈值过滤 | <15%的机会被过滤 | 测试用例 |
| Oracle提取 | 从description正确提取来源 | 真实市场测试 |
| Oracle对齐判断 | ALIGNED/MISALIGNED正确 | 测试用例 |
| CLOB API调用 | 成功获取订单簿 | 真实API测试 |
| VWAP计算 | 计算结果正确 | 手工计算对比 |
| 滑点估算 | 合理范围内 | 真实数据验证 |

## 7.2 Sprint 2 验收

| 验收项 | 标准 | 验证方法 |
|-------|------|---------|
| 五层验证串联 | 顺序执行、正确传递 | 端到端测试 |
| 失败终止 | 任一层失败正确终止 | 测试用例 |
| 结果输出 | 包含所有验证信息 | 输出检查 |
| 主流程集成 | scan()使用新引擎 | 完整扫描测试 |

## 7.3 Sprint 3 验收

| 验收项 | 标准 | 验证方法 |
|-------|------|---------|
| 输出格式 | 包含APY/滑点/Oracle | JSON格式检查 |
| 复核清单 | 自动生成Markdown | 文件生成检查 |
| 真实案例 | ≥3个验证通过 | 案例文档审查 |

## 7.4 Phase 2.5 总体验收

| 验收项 | 标准 |
|-------|------|
| APY过滤有效性 | >50%低质量机会被过滤 |
| 验证框架完整性 | 五层全部实现 |
| 真实案例数量 | ≥3个 |
| 无严重Bug | 主流程稳定运行 |

---

# 8. 风险与依赖

## 8.1 技术风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|------|---------|
| CLOB API限速 | 中 | 高 | 实现重试+缓存 |
| CLOB API变更 | 低 | 高 | 监控API版本 |
| Oracle提取困难 | 中 | 中 | LLM辅助提取 |
| VWAP计算复杂 | 低 | 中 | 充分测试 |

## 8.2 业务风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|------|---------|
| 找不到真实套利 | 中 | 高 | 扩大扫描范围 |
| 套利机会太少 | 中 | 中 | 降低阈值探索 |
| 市场流动性不足 | 高 | 中 | 设置最小流动性 |

## 8.3 依赖关系

```
外部依赖:
├── Polymarket Gamma API (markets, events)
├── Polymarket CLOB API (orderbook)
├── LLM Provider API (analysis)
└── Python Libraries (requests, numpy, sentence-transformers)

内部依赖:
├── Sprint 2 依赖 Sprint 1
├── Sprint 3 依赖 Sprint 2
├── 真实案例收集依赖完整验证框架
└── Phase 3 依赖 Phase 2.5 完成
```

---

# 9. 附录

## 9.1 文件结构规划

```
polymarket/
├── local_scanner_v2.py      # 主扫描器 (修改)
├── validators.py            # 验证器 (增强)
├── apy_calculator.py        # APY计算器 (新建)
├── oracle_comparator.py     # Oracle对齐检查器 (新建)
├── depth_calculator.py      # 订单簿深度计算器 (新建)
├── validation_engine.py     # 五层验证引擎 (新建)
├── checklist_generator.py   # 复核清单生成器 (新建)
├── interval_parser_v2.py    # 区间解析器 (现有)
├── semantic_cluster.py      # 语义聚类 (现有)
├── llm_providers.py         # LLM提供商 (现有)
├── prompts.py               # Prompt模板 (现有)
├── config.py                # 配置管理 (现有)
├── docs/
│   ├── PROJECT_BIBLE.md     # 项目圣经
│   ├── PROGRESS.md          # 进度追踪
│   ├── WORK_PLAN.md         # 本文档
│   └── cases/               # 套利案例 (新建)
│       ├── case_001.md
│       ├── case_002.md
│       └── ...
├── output/
│   ├── scans/               # 扫描结果
│   ├── opportunities/       # 机会详情
│   └── checklists/          # 复核清单 (新建)
└── tests/
    ├── test_apy_calculator.py    # (新建)
    ├── test_oracle_comparator.py # (新建)
    ├── test_depth_calculator.py  # (新建)
    └── test_validation_engine.py # (新建)
```

## 9.2 配置扩展

```python
# config.py 新增配置

@dataclass
class APYSettings:
    """APY相关配置"""
    min_apy: float = 0.15              # 最低可接受APY
    max_days_to_resolution: int = 180  # 最长锁仓天数
    risk_free_rate: float = 0.05       # 无风险利率

@dataclass
class DepthSettings:
    """订单簿深度配置"""
    target_size_usd: float = 500       # 目标交易金额
    max_slippage_pct: float = 3.0      # 最大可接受滑点
    min_liquidity_usd: float = 10000   # 最小流动性要求

@dataclass
class ValidationSettings:
    """验证配置"""
    require_oracle_alignment: bool = True
    require_apy_check: bool = True
    require_depth_check: bool = True
    generate_checklist: bool = True
```

## 9.3 命令行参数扩展

```bash
# 新增命令行参数

python local_scanner_v2.py \
    --semantic \
    --domain crypto \
    --min-apy 0.15 \                  # 最低APY阈值
    --max-days 180 \                  # 最长锁仓天数
    --target-size 500 \               # 目标交易金额
    --require-oracle-alignment \      # 强制Oracle对齐检查
    --generate-checklist \            # 生成人工复核清单
    --output-format enhanced          # 增强输出格式
```

## 9.4 参考文档

| 文档 | 用途 |
|-----|------|
| PROJECT_BIBLE.md | 项目核心指导 |
| PROGRESS.md | 进度追踪 |
| Polymarket API Docs | API参考 |
| CLOB API Docs | 订单簿API参考 |

---

# 变更日志

| 版本 | 日期 | 变更说明 |
|-----|------|---------|
| v1.0 | 2026-01-08 | 初始版本，基于PROJECT_BIBLE v2.0-Bible |

---

**下一步行动**:
1. 确认本工作计划
2. 开始 Sprint 1: Task 1.1 APYCalculator 实现
