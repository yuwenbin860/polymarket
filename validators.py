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
    end_date: str = ""  # 陷阱3修复: 增加结算日期字段

    @property
    def spread(self) -> float:
        """买卖价差"""
        return abs(1.0 - self.yes_price - self.no_price)


@dataclass
class IntervalData:
    """
    区间市场数据（用于 T6 区间完备集套利）

    表示一个数值区间市场，如 "Gold price between $4,725-$4,850"
    """
    market: MarketData           # 底层市场数据
    min_val: float               # 区间最小值
    max_val: float               # 区间最大值
    includes_min: bool = True    # 是否包含最小值边界
    includes_max: bool = True    # 是否包含最大值边界
    description: str = ""        # 区间描述（如 "$4,725-$4,850"）

    @property
    def range_size(self) -> float:
        """区间大小"""
        return self.max_val - self.min_val

    def overlaps_with(self, other: 'IntervalData') -> bool:
        """
        检查与另一个区间是否重叠

        重叠条件: not (self.max_val < other.min_val or other.max_val < self.min_val)
        但需要考虑边界包含情况

        对于完备集区间：
        - [0, 100) 和 [100, 200] 不重叠（边界相接，无公共点）
        - [0, 100] 和 [100, 200] 重叠（都包含100）
        """
        # 情况1: 完全不相交
        if self.max_val < other.min_val:
            return False
        if other.max_val < self.min_val:
            return False

        # 情况2: 边界相接
        if self.max_val == other.min_val:
            # 只有当两个区间都包含边界时才算重叠
            # 如果至少有一个不包含边界，则它们不相交
            # 例如: [0, 100) 和 [100, 200] 不重叠
            #       [0, 100] 和 [100, 200] 重叠于点100
            return self.includes_max and other.includes_min

        if other.max_val == self.min_val:
            return other.includes_max and self.includes_min

        # 情况3: 部分重叠或完全包含
        return True

    def gap_to(self, other: 'IntervalData') -> Optional[float]:
        """
        计算与另一个区间的间隙

        考虑边界包含情况：
        - [0, 100) 和 [100, 200] 无间隙（相接）
        - [0, 99] 和 [100, 200] 有间隙（99到100之间）
        - [0, 100] 和 [100, 200] 无间隙（都包含100）

        Returns:
            float: 间隙大小，如果没有间隙则返回 None
        """
        # 如果重叠，无间隙
        if self.overlaps_with(other):
            return None

        # 检查边界相接情况
        if self.max_val == other.min_val:
            # 边界相接，如果不重叠说明至少有一个不包含边界
            return None

        if other.max_val == self.min_val:
            return None

        # 计算间隙
        if self.max_val < other.min_val:
            # self 在 other 左边
            return other.min_val - self.max_val
        elif other.max_val < self.min_val:
            # other 在 self 左边
            return self.min_val - other.max_val
        else:
            # 重叠（已处理）
            return None


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

    def validate_time_consistency(
        self,
        market_a: MarketData,
        market_b: MarketData,
        relation: str,  # "IMPLIES_AB" 或 "IMPLIES_BA"
        max_time_diff_hours: float = 24.0
    ) -> ValidationReport:
        """
        陷阱3修复: 验证时间一致性

        规则：
        1. 蕴含关系 (A→B) 中，B的结算时间应该 >= A的结算时间
        2. 两市场的结算时间差应该 <= max_time_diff_hours

        Args:
            market_a: 市场A数据
            market_b: 市场B数据
            relation: 关系类型
            max_time_diff_hours: 最大允许的时间差（小时）

        Returns:
            ValidationReport
        """
        report = ValidationReport(
            result=ValidationResult.PASSED,
            reason="时间一致性检查通过"
        )
        report.details["check_type"] = "time_consistency"

        # 如果没有结算日期数据，标记为需要人工复核
        if not market_a.end_date or not market_b.end_date:
            report.result = ValidationResult.NEEDS_REVIEW
            report.reason = "缺少结算日期数据，需人工确认时间一致性"
            report.warnings.append("无法自动验证时间一致性")
            return report

        try:
            from datetime import datetime

            # 解析日期（支持多种格式）
            def parse_date(date_str: str) -> datetime:
                formats = [
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d",
                ]
                for fmt in formats:
                    try:
                        return datetime.strptime(date_str.split('+')[0].split('.')[0] + ('' if 'T' not in fmt else ''), fmt if 'T' not in fmt else fmt.split('.')[0])
                    except:
                        continue
                # 简化解析：只取日期部分
                date_part = date_str.split('T')[0] if 'T' in date_str else date_str
                return datetime.strptime(date_part, "%Y-%m-%d")

            end_a = parse_date(market_a.end_date)
            end_b = parse_date(market_b.end_date)

            report.details["end_date_a"] = str(end_a)
            report.details["end_date_b"] = str(end_b)

            # 计算时间差
            time_diff = abs((end_a - end_b).total_seconds())
            time_diff_hours = time_diff / 3600
            report.details["time_diff_hours"] = time_diff_hours

            # 检查1: 蕴含关系的时间约束
            if relation == "IMPLIES_AB":
                # A蕴含B：B的结算时间应该 >= A的结算时间
                if end_b < end_a:
                    report.result = ValidationResult.FAILED
                    report.reason = f"时间约束违反: B的结算时间 ({end_b}) 早于 A ({end_a})"
                    report.checks_failed.append("implication_time_constraint")
                    return report
                report.checks_passed.append("implication_time_constraint")

            elif relation == "IMPLIES_BA":
                # B蕴含A：A的结算时间应该 >= B的结算时间
                if end_a < end_b:
                    report.result = ValidationResult.FAILED
                    report.reason = f"时间约束违反: A的结算时间 ({end_a}) 早于 B ({end_b})"
                    report.checks_failed.append("implication_time_constraint")
                    return report
                report.checks_passed.append("implication_time_constraint")

            # 检查2: 时间差是否在安全范围内
            if time_diff_hours > max_time_diff_hours:
                report.result = ValidationResult.WARNING
                report.reason = f"结算时间差 {time_diff_hours:.1f} 小时，超过 {max_time_diff_hours} 小时阈值"
                report.warnings.append(f"时间差较大，需人工确认是否会影响套利")
            else:
                report.checks_passed.append("time_diff_threshold")

        except Exception as e:
            report.result = ValidationResult.NEEDS_REVIEW
            report.reason = f"日期解析失败: {str(e)}"
            report.warnings.append("需人工验证时间一致性")

        return report

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

    def _extract_threshold_info(self, question: str) -> Optional[Dict]:
        """
        从市场问题中提取价格阈值信息

        Returns:
            Dict with keys:
            - type: "up" (上涨阈值) 或 "down" (下跌阈值)
            - value: 阈值数值
            如果不是阈值类市场，返回 None
        """
        import re

        # 上涨模式: above, hit, reach, exceed, 突破, 超过
        # 支持 k/K (千), M (百万), B (十亿), T (万亿) 后缀
        up_patterns = [
            r'(?:above|hit|reach|exceed|突破|超过)\s*\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
            r'\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)\s*(?:and above|or higher)',
            r'(?:price|value)\s*(?:>|>=|above)\s*\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
            # NEW: Handle "> $X" format anywhere in question (e.g., "market cap > $2B")
            r'>\s*\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
            # NEW: Handle ">$X" (no space) format
            r'>\$([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
            # NEW: Handle "over $X", "exceeds $X", "crosses $X", "surpasses $X"
            r'(?:over|exceeds|crosses|surpasses|greater than)\s*\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
        ]

        # 下跌模式: dip, below, fall, drop, 跌到, 跌破, 跌至
        down_patterns = [
            r'(?:dip|below|fall|drop|跌到|跌破|跌至)\s*(?:to\s*)?\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
            r'\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)\s*(?:and below|or lower)',
            r'(?:price|value)\s*(?:<|<=|below)\s*\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
            # NEW: Handle "< $X" format anywhere
            r'<\s*\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
            # NEW: Handle "<$X" (no space) format
            r'<\$([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
            # NEW: Handle "under $X", "less than $X"
            r'(?:under|less than)\s*\$?([\d,]+(?:\.\d+)?[kKmMbBtT]?)',
        ]

        def parse_value(val_str: str) -> float:
            """解析数值字符串，支持 k/K (千), M (百万), B (十亿), T (万亿) 后缀"""
            val_str = val_str.replace(',', '')
            multiplier = 1
            if val_str.lower().endswith('k'):
                multiplier = 1_000
                val_str = val_str[:-1]
            elif val_str.lower().endswith('m'):
                multiplier = 1_000_000
                val_str = val_str[:-1]
            elif val_str.lower().endswith('b'):  # Billions (十亿)
                multiplier = 1_000_000_000
                val_str = val_str[:-1]
            elif val_str.lower().endswith('t'):  # Trillions (万亿)
                multiplier = 1_000_000_000_000
                val_str = val_str[:-1]
            return float(val_str) * multiplier

        for pattern in up_patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                try:
                    value = parse_value(match.group(1))
                    return {"type": "up", "value": value}
                except (ValueError, IndexError):
                    continue

        for pattern in down_patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                try:
                    value = parse_value(match.group(1))
                    return {"type": "down", "value": value}
                except (ValueError, IndexError):
                    continue

        return None

    def validate_threshold_implication(
        self,
        market_a: MarketData,
        market_b: MarketData,
        llm_relation: str
    ) -> ValidationReport:
        """
        验证价格阈值类市场的蕴含方向是否正确

        规则:
        - 上涨阈值 (above/hit/突破): 更高阈值 → 更低阈值 (A蕴含B当A>B)
        - 下跌阈值 (dip/below/跌到): 更低阈值 → 更高阈值 (A蕴含B当A<B)

        Args:
            market_a: 市场A数据
            market_b: 市场B数据
            llm_relation: LLM判断的关系类型 ("IMPLIES_AB" 或 "IMPLIES_BA")

        Returns:
            ValidationReport with result indicating if direction is correct
        """
        report = ValidationReport(
            result=ValidationResult.PASSED,
            reason="",
            details={}
        )

        # 只验证蕴含关系
        if llm_relation not in ["IMPLIES_AB", "IMPLIES_BA"]:
            report.reason = "非蕴含关系，跳过阈值方向验证"
            return report

        # 提取阈值信息
        info_a = self._extract_threshold_info(market_a.question)
        info_b = self._extract_threshold_info(market_b.question)

        # 如果不是阈值类市场，跳过验证
        if not info_a or not info_b:
            report.reason = "非阈值类市场，跳过阈值方向验证"
            report.checks_passed.append("threshold_skip_non_threshold")
            return report

        # 阈值类型必须一致
        if info_a["type"] != info_b["type"]:
            report.result = ValidationResult.NEEDS_REVIEW
            report.reason = f"阈值类型不一致 (A={info_a['type']}, B={info_b['type']})，需人工验证"
            report.warnings.append("阈值方向类型不一致可能导致蕴含关系判断错误")
            return report

        val_a = info_a["value"]
        val_b = info_b["value"]
        threshold_type = info_a["type"]

        # 计算正确的蕴含方向
        if threshold_type == "up":
            # 上涨阈值: 更高阈值 → 更低阈值
            # 例如: $150k → $100k (达到150k必然达到100k)
            if val_a > val_b:
                correct_relation = "IMPLIES_AB"  # A蕴含B
            elif val_a < val_b:
                correct_relation = "IMPLIES_BA"  # B蕴含A
            else:
                correct_relation = "EQUIVALENT"  # 相等则等价
        else:  # threshold_type == "down"
            # 下跌阈值: 更低阈值 → 更高阈值
            # 例如: $50 → $100 (跌到50必然跌过100)
            if val_a < val_b:
                correct_relation = "IMPLIES_AB"  # A蕴含B
            elif val_a > val_b:
                correct_relation = "IMPLIES_BA"  # B蕴含A
            else:
                correct_relation = "EQUIVALENT"  # 相等则等价

        # 记录详情
        report.details = {
            "threshold_type": threshold_type,
            "value_a": val_a,
            "value_b": val_b,
            "llm_relation": llm_relation,
            "correct_relation": correct_relation,
            "market_a": market_a.question[:80],
            "market_b": market_b.question[:80]
        }

        # 验证LLM判断是否正确
        if correct_relation == "EQUIVALENT":
            report.result = ValidationResult.NEEDS_REVIEW
            report.reason = f"阈值相等 (${val_a} = ${val_b})，应为等价关系而非蕴含关系"
            report.warnings.append("阈值相等的市场应该是EQUIVALENT关系")
        elif llm_relation == correct_relation:
            report.result = ValidationResult.PASSED
            report.reason = f"阈值蕴含方向正确: {llm_relation} ({threshold_type}阈值 ${val_a} vs ${val_b})"
            report.checks_passed.append("threshold_direction_correct")
        else:
            report.result = ValidationResult.FAILED
            report.reason = (
                f"阈值蕴含方向错误! LLM判断: {llm_relation}, 正确应为: {correct_relation}\n"
                f"  - 阈值类型: {threshold_type} (上涨=更高→更低, 下跌=更低→更高)\n"
                f"  - 市场A阈值: ${val_a}\n"
                f"  - 市场B阈值: ${val_b}"
            )
            report.checks_failed.append("threshold_direction_wrong")

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

    # ============================================================
    # T6: 区间完备集套利验证方法
    # ============================================================

    def validate_interval_overlaps(
        self,
        intervals: List[IntervalData]
    ) -> ValidationReport:
        """
        验证区间是否重叠（T6 区间完备集套利 - 互斥性检查）

        Args:
            intervals: 区间列表

        Returns:
            ValidationReport 包含重叠检测结果
        """
        report = ValidationReport(
            result=ValidationResult.PASSED,
            reason="区间互斥性检查通过",
            details={
                "num_intervals": len(intervals),
                "intervals": [
                    {
                        "market": iv.market.question[:50],
                        "min": iv.min_val,
                        "max": iv.max_val,
                        "description": iv.description
                    }
                    for iv in intervals
                ]
            }
        )

        if len(intervals) < 2:
            report.reason = "至少需要2个区间才能检查重叠"
            report.warnings.append("区间数量不足")
            return report

        # 按最小值排序
        sorted_intervals = sorted(intervals, key=lambda x: x.min_val)

        # 检查所有区间对
        overlapping_pairs = []
        for i in range(len(sorted_intervals)):
            for j in range(i + 1, len(sorted_intervals)):
                interval_a = sorted_intervals[i]
                interval_b = sorted_intervals[j]

                if interval_a.overlaps_with(interval_b):
                    overlapping_pairs.append({
                        "interval_a": {
                            "question": interval_a.market.question[:50],
                            "range": f"[{interval_a.min_val}, {interval_a.max_val}]"
                        },
                        "interval_b": {
                            "question": interval_b.market.question[:50],
                            "range": f"[{interval_b.min_val}, {interval_b.max_val}]"
                        },
                        "overlap_type": "boundary" if (
                            abs(interval_a.max_val - interval_b.min_val) < 0.01 or
                            abs(interval_b.max_val - interval_a.min_val) < 0.01
                        ) else "substantial"
                    })

        report.details["overlapping_pairs"] = overlapping_pairs
        report.details["num_overlaps"] = len(overlapping_pairs)

        if overlapping_pairs:
            report.result = ValidationResult.FAILED
            report.reason = f"发现 {len(overlapping_pairs)} 对重叠区间，不满足互斥性"
            report.checks_failed.append("interval_mutual_exclusivity")
        else:
            report.checks_passed.append("interval_mutual_exclusivity")

        return report

    def validate_interval_gaps(
        self,
        intervals: List[IntervalData],
        global_min: Optional[float] = None,
        global_max: Optional[float] = None
    ) -> ValidationReport:
        """
        验证区间是否有遗漏（T6 区间完备集套利 - 完备性检查）

        Args:
            intervals: 区间列表
            global_min: 全局最小值（如果已知，如 0）
            global_max: 全局最大值（如果已知）

        Returns:
            ValidationReport 包含遗漏检测结果
        """
        report = ValidationReport(
            result=ValidationResult.PASSED,
            reason="区间完备性检查通过",
            details={
                "num_intervals": len(intervals),
                "intervals": [
                    {
                        "market": iv.market.question[:50],
                        "min": iv.min_val,
                        "max": iv.max_val,
                    }
                    for iv in intervals
                ]
            }
        )

        if len(intervals) < 2:
            report.reason = "至少需要2个区间才能检查遗漏"
            report.warnings.append("区间数量不足")
            return report

        # 按最小值排序
        sorted_intervals = sorted(intervals, key=lambda x: x.min_val)

        # 检查相邻区间之间的间隙
        gaps = []
        for i in range(len(sorted_intervals) - 1):
            current = sorted_intervals[i]
            next_interval = sorted_intervals[i + 1]

            gap = current.gap_to(next_interval)
            if gap is not None and gap > 0:
                gaps.append({
                    "after_interval": {
                        "question": current.market.question[:50],
                        "max": current.max_val
                    },
                    "before_interval": {
                        "question": next_interval.market.question[:50],
                        "min": next_interval.min_val
                    },
                    "gap_size": gap,
                    "missing_range": f"({current.max_val}, {next_interval.min_val})"
                })

        # 检查全局范围
        range_warnings = []
        if global_min is not None:
            first_interval = sorted_intervals[0]
            if first_interval.min_val > global_min:
                range_warnings.append({
                    "type": "lower_gap",
                    "missing_range": f"[{global_min}, {first_interval.min_val})",
                    "description": f"全局最小值 {global_min} 到第一个区间 {first_interval.min_val} 之间有遗漏"
                })

        if global_max is not None:
            last_interval = sorted_intervals[-1]
            if last_interval.max_val < global_max:
                range_warnings.append({
                    "type": "upper_gap",
                    "missing_range": f"({last_interval.max_val}, {global_max}]",
                    "description": f"最后一个区间 {last_interval.max_val} 到全局最大值 {global_max} 之间有遗漏"
                })

        report.details["gaps"] = gaps
        report.details["num_gaps"] = len(gaps)
        report.details["range_warnings"] = range_warnings
        report.details["global_min"] = global_min
        report.details["global_max"] = global_max

        if gaps or range_warnings:
            if range_warnings:
                # 全局范围遗漏是严重问题
                report.result = ValidationResult.FAILED
                report.reason = f"发现 {len(gaps)} 个间隙 + {len(range_warnings)} 个全局范围遗漏，不完备"
            else:
                # 仅有间隙可能是可以接受的（如果有明确的边界处理）
                report.result = ValidationResult.WARNING
                report.reason = f"发现 {len(gaps)} 个间隙，可能不完备"
            report.checks_failed.append("interval_completeness")
        else:
            report.checks_passed.append("interval_completeness")

        return report

    def validate_interval_exhaustive_set(
        self,
        intervals: List[IntervalData],
        global_min: Optional[float] = None,
        global_max: Optional[float] = None,
        trade_size: float = 100.0
    ) -> ValidationReport:
        """
        综合验证区间完备集套利（T6）

        包含以下检查：
        1. 互斥性检查（区间不重叠）
        2. 完备性检查（无遗漏区间）
        3. 价格总和检查（ΣP < 1.0）
        4. 流动性检查
        5. 利润计算

        Args:
            intervals: 区间列表
            global_min: 全局最小值
            global_max: 全局最大值
            trade_size: 交易规模

        Returns:
            ValidationReport 包含完整的验证结果
        """
        report = ValidationReport(
            result=ValidationResult.FAILED,
            reason="",
            details={
                "validation_type": "interval_exhaustive_set",
                "num_intervals": len(intervals)
            }
        )

        if len(intervals) < 2:
            report.reason = "区间完备集至少需要2个区间"
            return report

        # === 检查1: 互斥性（无重叠）===
        overlap_report = self.validate_interval_overlaps(intervals)
        report.details["overlap_check"] = overlap_report.to_dict()

        if overlap_report.result == ValidationResult.FAILED:
            report.result = ValidationResult.FAILED
            report.reason = overlap_report.reason
            report.checks_failed.append("interval_mutual_exclusivity")
            return report

        report.checks_passed.append("interval_mutual_exclusivity")

        # === 检查2: 完备性（无遗漏）===
        gap_report = self.validate_interval_gaps(intervals, global_min, global_max)
        report.details["gap_check"] = gap_report.to_dict()

        if gap_report.result == ValidationResult.FAILED:
            report.result = ValidationResult.FAILED
            report.reason = gap_report.reason
            report.checks_failed.append("interval_completeness")
            return report
        elif gap_report.result == ValidationResult.WARNING:
            report.warnings.append(gap_report.reason)

        report.checks_passed.append("interval_completeness")

        # === 检查3: 价格总和 ===
        total_yes_price = sum(iv.market.yes_price for iv in intervals)
        report.details["total_yes_price"] = total_yes_price
        report.details["individual_prices"] = {
            iv.market.question[:30]: iv.market.yes_price
            for iv in intervals
        }

        if total_yes_price >= 1.0:
            report.result = ValidationResult.FAILED
            report.reason = f"价格总和 {total_yes_price:.4f} >= 1.0，无套利空间"
            report.checks_failed.append("price_sum_below_one")
            return report

        report.checks_passed.append("price_sum_below_one")

        # === 检查4: 流动性 ===
        low_liquidity_intervals = [
            iv for iv in intervals
            if iv.market.liquidity < self.min_liquidity
        ]
        if low_liquidity_intervals:
            for iv in low_liquidity_intervals:
                report.warnings.append(
                    f"流动性不足: {iv.market.question[:30]}... (${iv.market.liquidity:.0f})"
                )

        report.checks_passed.append("liquidity_check")

        # === 检查5: 利润计算 ===
        total_cost = total_yes_price
        guaranteed_return = 1.0
        gross_profit = guaranteed_return - total_cost

        report.total_cost = total_cost
        report.guaranteed_return = guaranteed_return
        report.expected_profit = gross_profit
        report.profit_pct = (gross_profit / total_cost) * 100

        # === 检查6: 滑点和费用 ===
        per_interval_size = trade_size / len(intervals)
        total_slippage = sum(
            self.estimate_slippage(iv.market, per_interval_size)
            for iv in intervals
        )
        total_slippage_dollar = total_slippage * trade_size / 100

        fee = total_cost * self.fee_rate * trade_size / 100

        net_profit = gross_profit * trade_size / 100 - total_slippage_dollar - fee
        net_profit_pct = (net_profit / (total_cost * trade_size / 100)) * 100

        report.slippage_estimate = total_slippage
        report.fee_estimate = self.fee_rate
        report.net_profit = net_profit

        # === 检查7: 利润阈值 ===
        min_threshold = max(1.0, self.min_profit_pct - 1.0)

        if net_profit_pct < min_threshold:
            report.result = ValidationResult.WARNING
            report.reason = (
                f"区间完备集验证通过，但净利润率较低: {net_profit_pct:.2f}%\n"
                f"价格总和: {total_yes_price:.4f}，"
                f"区间数: {len(intervals)}"
            )
            report.warnings.append("利润空间较小，需要更大资金量才能覆盖固定成本")
        else:
            report.result = ValidationResult.PASSED
            report.reason = (
                f"区间完备集验证通过！\n"
                f"价格总和: {total_yes_price:.4f}，"
                f"净利润率: {net_profit_pct:.2f}%，"
                f"区间数: {len(intervals)}"
            )

        report.checks_passed.append("net_profit_threshold")

        # 添加执行建议
        report.details["execution"] = [
            {
                "market": iv.market.question[:50],
                "action": "buy_yes",
                "price": iv.market.yes_price,
                "amount": per_interval_size,
                "interval": f"[{iv.min_val}, {iv.max_val}]"
            }
            for iv in intervals
        ]

        # 添加区间汇总信息
        report.details["interval_summary"] = {
            "total_range": f"[{sorted(iv.min_val for iv in intervals)[0]}, {sorted(iv.max_val for iv in intervals)[-1]}]",
            "has_gaps": gap_report.details.get("num_gaps", 0) > 0,
            "has_overlaps": overlap_report.details.get("num_overlaps", 0) > 0,
            "coverage_percentage": self._calculate_coverage(intervals, global_min, global_max)
        }

        return report

    def _calculate_coverage(
        self,
        intervals: List[IntervalData],
        global_min: Optional[float],
        global_max: Optional[float]
    ) -> Optional[float]:
        """
        计算区间覆盖率

        Returns:
            float: 0.0-1.0 的覆盖率，如果无法计算则返回 None
        """
        if not intervals:
            return 0.0

        try:
            # 计算所有区间的并集大小（简化计算：假设区间不重叠）
            total_covered = sum(iv.range_size for iv in intervals)

            # 确定全局范围
            actual_min = min(iv.min_val for iv in intervals)
            actual_max = max(iv.max_val for iv in intervals)

            if global_min is not None:
                actual_min = min(actual_min, global_min)
            if global_max is not None:
                actual_max = max(actual_max, global_max)

            total_range = actual_max - actual_min

            if total_range <= 0:
                return None

            return min(1.0, total_covered / total_range)

        except Exception:
            return None

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

