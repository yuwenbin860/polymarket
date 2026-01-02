"""
数学验证层 - 验证套利策略的数学可行性
========================================

在 LLM 分析之后，使用数学方法验证套利机会是否真实可行。
主要防止以下问题：
1. LLM 误判逻辑关系
2. 利润计算错误
3. 忽略滑点和费用
4. 边界条件未考虑

使用方法：
    from validators import MathValidator

    validator = MathValidator()

    # 验证包含关系套利
    is_valid, reason, details = validator.validate_implication(
        market_a, market_b, "IMPLIES_AB"
    )

    # 验证完备集套利
    is_valid, reason, details = validator.validate_exhaustive_set(markets)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum


class ValidationResult(Enum):
    """验证结果类型"""
    PASSED = "passed"           # 验证通过
    FAILED = "failed"           # 验证失败
    WARNING = "warning"         # 有风险但可能可行
    NEEDS_REVIEW = "needs_review"  # 需要人工复核


@dataclass
class ValidationReport:
    """验证报告"""
    result: ValidationResult
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    # 数学计算结果
    total_cost: float = 0.0
    guaranteed_return: float = 0.0
    expected_profit: float = 0.0
    profit_pct: float = 0.0

    # 风险因素
    slippage_estimate: float = 0.0
    fee_estimate: float = 0.0
    net_profit: float = 0.0

    # 检查清单
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        return self.result in [ValidationResult.PASSED, ValidationResult.WARNING]

    def to_dict(self) -> Dict:
        return {
            "result": self.result.value,
            "reason": self.reason,
            "total_cost": self.total_cost,
            "guaranteed_return": self.guaranteed_return,
            "expected_profit": self.expected_profit,
            "profit_pct": self.profit_pct,
            "slippage_estimate": self.slippage_estimate,
            "fee_estimate": self.fee_estimate,
            "net_profit": self.net_profit,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "warnings": self.warnings,
            "details": self.details
        }


@dataclass
class MarketData:
    """市场数据（用于验证）"""
    id: str
    question: str
    yes_price: float
    no_price: float
    liquidity: float
    volume: float = 0.0

    @property
    def spread(self) -> float:
        """买卖价差"""
        return abs(1.0 - self.yes_price - self.no_price)


class MathValidator:
    """
    数学验证器

    验证套利策略的数学可行性，包括：
    - 概率论约束检查
    - 利润计算验证
    - 滑点估算
    - 费用计算
    """

    def __init__(
        self,
        min_profit_pct: float = 2.0,      # 最小利润率 (%)
        slippage_factor: float = 0.5,      # 滑点因子 (%)
        fee_rate: float = 0.0,             # 交易费率 (Polymarket 全球站为0)
        min_liquidity: float = 1000.0,     # 最小流动性要求
    ):
        self.min_profit_pct = min_profit_pct
        self.slippage_factor = slippage_factor
        self.fee_rate = fee_rate
        self.min_liquidity = min_liquidity

    def estimate_slippage(self, market: MarketData, trade_size: float = 100.0) -> float:
        """
        估算滑点

        简化模型：滑点 = (交易额 / 流动性) * slippage_factor
        实际滑点取决于订单簿深度，这里用流动性作为近似
        """
        if market.liquidity <= 0:
            return 0.05  # 无流动性数据时假设5%滑点

        # 交易额占流动性比例越高，滑点越大
        ratio = trade_size / market.liquidity
        slippage = ratio * self.slippage_factor

        # 滑点上限为 5%
        return min(slippage, 0.05)

    def validate_implication(
        self,
        market_a: MarketData,
        market_b: MarketData,
        relation: str,  # "IMPLIES_AB" 或 "IMPLIES_BA"
        trade_size: float = 100.0
    ) -> ValidationReport:
        """
        验证包含关系套利

        逻辑：如果 A → B，则 P(B) >= P(A)

        当 P(B) < P(A) 时存在套利：
        - 买 B 的 YES @ P(B)
        - 买 A 的 NO @ (1 - P(A))
        - 成本 = P(B) + (1 - P(A))
        - 最小回报 = 1.0
        """
        report = ValidationReport(
            result=ValidationResult.FAILED,
            reason="",
            details={
                "market_a": market_a.question[:50],
                "market_b": market_b.question[:50],
                "relation": relation
            }
        )

        # 确定哪个是前提(antecedent)，哪个是结论(consequent)
        if relation == "IMPLIES_AB":
            # A → B: A发生则B必发生
            antecedent = market_a  # 前提
            consequent = market_b  # 结论
        elif relation == "IMPLIES_BA":
            # B → A: B发生则A必发生
            antecedent = market_b
            consequent = market_a
        else:
            report.reason = f"无效的关系类型: {relation}"
            report.checks_failed.append("relation_type_check")
            return report

        report.checks_passed.append("relation_type_check")

        # === 检查1: 概率论约束 ===
        # 如果 antecedent → consequent，则 P(consequent) >= P(antecedent)
        p_antecedent = antecedent.yes_price
        p_consequent = consequent.yes_price

        if p_consequent >= p_antecedent:
            report.reason = f"价格符合逻辑约束: P({consequent.question[:30]}...)={p_consequent:.2f} >= P({antecedent.question[:30]}...)={p_antecedent:.2f}，无套利空间"
            report.checks_failed.append("probability_constraint_violated")
            return report

        report.checks_passed.append("probability_constraint_violated")
        report.details["price_violation"] = p_antecedent - p_consequent

        # === 检查2: 流动性 ===
        if antecedent.liquidity < self.min_liquidity:
            report.warnings.append(f"市场A流动性不足: ${antecedent.liquidity:.0f}")
        if consequent.liquidity < self.min_liquidity:
            report.warnings.append(f"市场B流动性不足: ${consequent.liquidity:.0f}")

        report.checks_passed.append("liquidity_check")

        # === 检查3: 利润计算 ===
        # 操作：买 consequent 的 YES，买 antecedent 的 NO
        cost_consequent_yes = p_consequent
        cost_antecedent_no = 1.0 - p_antecedent

        total_cost = cost_consequent_yes + cost_antecedent_no
        guaranteed_return = 1.0  # 无论结果如何，至少收回 $1

        # 情况分析：
        # 1. antecedent 发生 → consequent 必发生 → 回报 = $1 (consequent YES)
        # 2. antecedent 不发生，consequent 发生 → 回报 = $2
        # 3. antecedent 不发生，consequent 不发生 → 回报 = $1 (antecedent NO)

        gross_profit = guaranteed_return - total_cost

        if gross_profit <= 0:
            report.reason = f"毛利润为负: 成本=${total_cost:.4f} >= 回报=${guaranteed_return:.2f}"
            report.checks_failed.append("gross_profit_positive")
            report.total_cost = total_cost
            report.guaranteed_return = guaranteed_return
            report.expected_profit = gross_profit
            return report

        report.checks_passed.append("gross_profit_positive")

        # === 检查4: 滑点和费用 ===
        slippage_a = self.estimate_slippage(antecedent, trade_size)
        slippage_b = self.estimate_slippage(consequent, trade_size)
        total_slippage = (slippage_a + slippage_b) * trade_size / 100  # 转换为美元

        fee = total_cost * self.fee_rate * trade_size / 100

        net_profit = gross_profit * trade_size / 100 - total_slippage - fee
        net_profit_pct = (net_profit / (total_cost * trade_size / 100)) * 100

        report.total_cost = total_cost
        report.guaranteed_return = guaranteed_return
        report.expected_profit = gross_profit
        report.profit_pct = (gross_profit / total_cost) * 100
        report.slippage_estimate = (slippage_a + slippage_b)
        report.fee_estimate = self.fee_rate
        report.net_profit = net_profit

        if net_profit_pct < self.min_profit_pct:
            report.result = ValidationResult.WARNING
            report.reason = f"净利润率 {net_profit_pct:.2f}% 低于阈值 {self.min_profit_pct}%"
            report.warnings.append(f"考虑滑点后利润较低")
        else:
            report.result = ValidationResult.PASSED
            report.reason = f"数学验证通过！净利润率: {net_profit_pct:.2f}%"

        report.checks_passed.append("net_profit_threshold")

        # 添加执行建议
        report.details["execution"] = {
            "buy_consequent_yes": {
                "market": consequent.question[:50],
                "price": p_consequent,
                "amount": trade_size / 2
            },
            "buy_antecedent_no": {
                "market": antecedent.question[:50],
                "price": 1.0 - p_antecedent,
                "amount": trade_size / 2
            }
        }

        return report

    def validate_exhaustive_set(
        self,
        markets: List[MarketData],
        trade_size: float = 100.0
    ) -> ValidationReport:
        """
        验证完备集套利

        逻辑：互斥且完备的结果集，概率总和应该 = 1.0

        当 Σ(YES价格) < 1.0 时存在套利：
        - 买入所有选项各一份
        - 成本 = Σ(YES价格)
        - 回报 = 1.0（必有一个结果发生）
        """
        report = ValidationReport(
            result=ValidationResult.FAILED,
            reason="",
            details={
                "num_markets": len(markets),
                "markets": [m.question[:30] for m in markets]
            }
        )

        if len(markets) < 2:
            report.reason = "完备集至少需要2个市场"
            report.checks_failed.append("min_markets_check")
            return report

        report.checks_passed.append("min_markets_check")

        # === 检查1: 价格总和 ===
        total_yes_price = sum(m.yes_price for m in markets)

        report.details["total_yes_price"] = total_yes_price
        report.details["individual_prices"] = {m.question[:30]: m.yes_price for m in markets}

        if total_yes_price >= 1.0:
            report.reason = f"价格总和 {total_yes_price:.4f} >= 1.0，无套利空间"
            report.checks_failed.append("price_sum_below_one")
            return report

        report.checks_passed.append("price_sum_below_one")

        # === 检查2: 流动性 ===
        low_liquidity_markets = [m for m in markets if m.liquidity < self.min_liquidity]
        if low_liquidity_markets:
            for m in low_liquidity_markets:
                report.warnings.append(f"流动性不足: {m.question[:30]}... (${m.liquidity:.0f})")

        report.checks_passed.append("liquidity_check")

        # === 检查3: 利润计算 ===
        total_cost = total_yes_price
        guaranteed_return = 1.0
        gross_profit = guaranteed_return - total_cost

        report.total_cost = total_cost
        report.guaranteed_return = guaranteed_return
        report.expected_profit = gross_profit
        report.profit_pct = (gross_profit / total_cost) * 100

        # === 检查4: 滑点和费用 ===
        # 每个市场的交易额 = trade_size / len(markets)
        per_market_size = trade_size / len(markets)
        total_slippage = sum(self.estimate_slippage(m, per_market_size) for m in markets)
        total_slippage_dollar = total_slippage * trade_size / 100

        fee = total_cost * self.fee_rate * trade_size / 100

        net_profit = gross_profit * trade_size / 100 - total_slippage_dollar - fee
        net_profit_pct = (net_profit / (total_cost * trade_size / 100)) * 100

        report.slippage_estimate = total_slippage
        report.fee_estimate = self.fee_rate
        report.net_profit = net_profit

        # === 检查5: 利润阈值 ===
        # 完备集套利通常利润较低，使用更宽松的阈值
        min_threshold = max(1.0, self.min_profit_pct - 1.0)

        if net_profit_pct < min_threshold:
            report.result = ValidationResult.WARNING
            report.reason = f"净利润率 {net_profit_pct:.2f}% 较低，考虑交易成本后可能无利可图"
            report.warnings.append("利润空间较小，需要更大资金量才能覆盖固定成本")
        else:
            report.result = ValidationResult.PASSED
            report.reason = f"数学验证通过！价格总和: {total_yes_price:.4f}，净利润率: {net_profit_pct:.2f}%"

        report.checks_passed.append("net_profit_threshold")

        # 添加执行建议
        report.details["execution"] = [
            {
                "market": m.question[:50],
                "action": "buy_yes",
                "price": m.yes_price,
                "amount": per_market_size
            }
            for m in markets
        ]

        return report

    def validate_equivalent(
        self,
        market_a: MarketData,
        market_b: MarketData,
        trade_size: float = 100.0
    ) -> ValidationReport:
        """
        验证等价市场套利

        逻辑：两个市场问的是同一个问题，应该有相同价格

        当价差 > 阈值时存在套利：
        - 买低价市场的 YES
        - 买高价市场的 NO
        """
        report = ValidationReport(
            result=ValidationResult.FAILED,
            reason="",
            details={
                "market_a": market_a.question[:50],
                "market_b": market_b.question[:50]
            }
        )

        # === 检查1: 价差 ===
        spread = abs(market_a.yes_price - market_b.yes_price)
        report.details["spread"] = spread
        report.details["spread_pct"] = spread * 100

        # 价差小于 2% 通常不值得交易
        if spread < 0.02:
            report.reason = f"价差 {spread:.2%} 过小，不值得交易"
            report.checks_failed.append("min_spread_check")
            return report

        report.checks_passed.append("min_spread_check")

        # 确定哪个是低价，哪个是高价
        if market_a.yes_price < market_b.yes_price:
            low_market = market_a
            high_market = market_b
        else:
            low_market = market_b
            high_market = market_a

        # === 检查2: 流动性 ===
        if low_market.liquidity < self.min_liquidity:
            report.warnings.append(f"低价市场流动性不足: ${low_market.liquidity:.0f}")
        if high_market.liquidity < self.min_liquidity:
            report.warnings.append(f"高价市场流动性不足: ${high_market.liquidity:.0f}")

        report.checks_passed.append("liquidity_check")

        # === 检查3: 利润计算 ===
        # 操作：买低价 YES，买高价 NO
        cost_low_yes = low_market.yes_price
        cost_high_no = 1.0 - high_market.yes_price

        total_cost = cost_low_yes + cost_high_no
        guaranteed_return = 1.0  # 两市场结果相同，必得 $1

        gross_profit = guaranteed_return - total_cost

        if gross_profit <= 0:
            report.reason = f"毛利润为负: 成本=${total_cost:.4f} >= 回报=${guaranteed_return:.2f}"
            report.checks_failed.append("gross_profit_positive")
            report.total_cost = total_cost
            report.guaranteed_return = guaranteed_return
            report.expected_profit = gross_profit
            return report

        report.checks_passed.append("gross_profit_positive")

        # === 检查4: 滑点和费用 ===
        slippage_low = self.estimate_slippage(low_market, trade_size / 2)
        slippage_high = self.estimate_slippage(high_market, trade_size / 2)
        total_slippage = (slippage_low + slippage_high) * trade_size / 100

        fee = total_cost * self.fee_rate * trade_size / 100

        net_profit = gross_profit * trade_size / 100 - total_slippage - fee
        net_profit_pct = (net_profit / (total_cost * trade_size / 100)) * 100

        report.total_cost = total_cost
        report.guaranteed_return = guaranteed_return
        report.expected_profit = gross_profit
        report.profit_pct = (gross_profit / total_cost) * 100
        report.slippage_estimate = (slippage_low + slippage_high)
        report.fee_estimate = self.fee_rate
        report.net_profit = net_profit

        if net_profit_pct < self.min_profit_pct:
            report.result = ValidationResult.WARNING
            report.reason = f"净利润率 {net_profit_pct:.2f}% 低于阈值 {self.min_profit_pct}%"
            report.warnings.append("考虑滑点后利润较低")
        else:
            report.result = ValidationResult.PASSED
            report.reason = f"数学验证通过！价差: {spread:.2%}，净利润率: {net_profit_pct:.2f}%"

        report.checks_passed.append("net_profit_threshold")

        # 添加执行建议
        report.details["execution"] = {
            "buy_low_yes": {
                "market": low_market.question[:50],
                "price": low_market.yes_price,
                "amount": trade_size / 2
            },
            "buy_high_no": {
                "market": high_market.question[:50],
                "price": 1.0 - high_market.yes_price,
                "amount": trade_size / 2
            }
        }

        return report

    def generate_checklist(self, report: ValidationReport) -> List[str]:
        """生成人工验证清单"""
        checklist = []

        # 基础检查
        checklist.append(f"[ ] 数学验证结果: {report.result.value}")
        checklist.append(f"[ ] 预期毛利润: {report.profit_pct:.2f}%")
        checklist.append(f"[ ] 预期净利润: {(report.net_profit / (report.total_cost * 100) * 100) if report.total_cost > 0 else 0:.2f}%")

        # 风险检查
        if report.warnings:
            checklist.append("[ ] 风险警告:")
            for w in report.warnings:
                checklist.append(f"    - {w}")

        # 人工复核项
        checklist.append("[ ] 人工阅读两市场结算规则")
        checklist.append("[ ] 确认两市场结算时间一致")
        checklist.append("[ ] 确认无边界情况（平局、取消等）")
        checklist.append("[ ] 确认流动性足够执行")
        checklist.append("[ ] 小额测试执行")

        return checklist


# === 便捷函数 ===

def validate_opportunity(
    opportunity_type: str,
    markets: List[Dict],
    relation: str = None,
    **kwargs
) -> ValidationReport:
    """
    验证套利机会的便捷函数

    Args:
        opportunity_type: "implication", "exhaustive", "equivalent"
        markets: 市场数据列表
        relation: 关系类型（仅用于 implication）

    Returns:
        ValidationReport
    """
    validator = MathValidator(**kwargs)

    # 转换市场数据
    market_objects = [
        MarketData(
            id=m.get("id", ""),
            question=m.get("question", ""),
            yes_price=m.get("yes_price", 0.0),
            no_price=m.get("no_price", 0.0),
            liquidity=m.get("liquidity", 0.0),
            volume=m.get("volume", 0.0)
        )
        for m in markets
    ]

    if opportunity_type == "implication":
        if len(market_objects) < 2 or not relation:
            return ValidationReport(
                result=ValidationResult.FAILED,
                reason="包含关系验证需要两个市场和关系类型"
            )
        return validator.validate_implication(
            market_objects[0], market_objects[1], relation
        )

    elif opportunity_type == "exhaustive":
        return validator.validate_exhaustive_set(market_objects)

    elif opportunity_type == "equivalent":
        if len(market_objects) < 2:
            return ValidationReport(
                result=ValidationResult.FAILED,
                reason="等价市场验证需要两个市场"
            )
        return validator.validate_equivalent(market_objects[0], market_objects[1])

    else:
        return ValidationReport(
            result=ValidationResult.FAILED,
            reason=f"未知的机会类型: {opportunity_type}"
        )


if __name__ == "__main__":
    # 测试示例
    print("=" * 60)
    print("数学验证层测试")
    print("=" * 60)

    validator = MathValidator(min_profit_pct=2.0)

    # 测试1: 包含关系套利
    print("\n--- 测试1: 包含关系套利 ---")
    market_a = MarketData(
        id="1",
        question="Will Trump win the 2024 election?",
        yes_price=0.55,
        no_price=0.45,
        liquidity=100000
    )
    market_b = MarketData(
        id="2",
        question="Will Republicans win the 2024 election?",
        yes_price=0.50,  # 违反逻辑！应该 >= 0.55
        no_price=0.50,
        liquidity=80000
    )

    report = validator.validate_implication(market_a, market_b, "IMPLIES_AB")
    print(f"结果: {report.result.value}")
    print(f"原因: {report.reason}")
    print(f"毛利润率: {report.profit_pct:.2f}%")
    print(f"检查通过: {report.checks_passed}")
    print(f"警告: {report.warnings}")

    # 测试2: 完备集套利
    print("\n--- 测试2: 完备集套利 ---")
    markets = [
        MarketData(id="1", question="Candidate A wins", yes_price=0.35, no_price=0.65, liquidity=50000),
        MarketData(id="2", question="Candidate B wins", yes_price=0.30, no_price=0.70, liquidity=50000),
        MarketData(id="3", question="Candidate C wins", yes_price=0.15, no_price=0.85, liquidity=30000),
        MarketData(id="4", question="Other candidates win", yes_price=0.15, no_price=0.85, liquidity=20000),
    ]

    report = validator.validate_exhaustive_set(markets)
    print(f"结果: {report.result.value}")
    print(f"原因: {report.reason}")
    print(f"价格总和: {report.details.get('total_yes_price', 0):.4f}")
    print(f"毛利润率: {report.profit_pct:.2f}%")

    # 测试3: 等价市场套利
    print("\n--- 测试3: 等价市场套利 ---")
    market_a = MarketData(
        id="1",
        question="Will BTC hit $100k in 2024?",
        yes_price=0.52,
        no_price=0.48,
        liquidity=200000
    )
    market_b = MarketData(
        id="2",
        question="Bitcoin reaches $100,000 this year?",
        yes_price=0.48,  # 价差 4%
        no_price=0.52,
        liquidity=150000
    )

    report = validator.validate_equivalent(market_a, market_b)
    print(f"结果: {report.result.value}")
    print(f"原因: {report.reason}")
    print(f"价差: {report.details.get('spread_pct', 0):.2f}%")
    print(f"毛利润率: {report.profit_pct:.2f}%")

    # 生成验证清单
    print("\n--- 人工验证清单 ---")
    checklist = validator.generate_checklist(report)
    for item in checklist:
        print(item)
