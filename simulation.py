"""
simulation.py - 模拟执行跟踪模块

在真正执行套利之前，先通过模拟执行来验证策略的有效性。

功能：
1. 记录"假设买入"的市场、价格、仓位
2. 跟踪价格变化
3. 结算后计算"假设收益"
4. 生成模拟执行报告

使用方法：
    tracker = SimulationTracker()

    # 记录模拟交易
    trade_id = tracker.record_trade(
        market_a=market_a,
        market_b=market_b,
        strategy="implication",
        positions={"a_no": 100, "b_yes": 100}
    )

    # 更新价格（定期运行）
    tracker.update_prices(trade_id, new_prices)

    # 结算
    tracker.settle_trade(trade_id, outcomes={"a": True, "b": True})

    # 生成报告
    report = tracker.generate_report()
"""

import json
import os
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    """交易状态"""
    OPEN = "open"           # 开仓中
    SETTLED = "settled"     # 已结算
    EXPIRED = "expired"     # 已过期
    CANCELLED = "cancelled" # 已取消


class StrategyType(Enum):
    """策略类型"""
    IMPLICATION = "implication"       # 包含关系套利
    EQUIVALENT = "equivalent"         # 等价市场套利
    EXHAUSTIVE_SET = "exhaustive_set" # 完备集套利
    CROSS_PLATFORM = "cross_platform" # 跨平台套利


@dataclass
class Position:
    """仓位"""
    market_id: str
    market_question: str
    side: str  # "yes" or "no"
    size: float  # 金额 (USD)
    entry_price: float
    current_price: float = 0.0
    settlement_outcome: Optional[bool] = None  # True=YES wins, False=NO wins

    @property
    def unrealized_pnl(self) -> float:
        """未实现盈亏"""
        if self.side == "yes":
            return self.size * (self.current_price - self.entry_price)
        else:
            return self.size * ((1 - self.current_price) - (1 - self.entry_price))

    @property
    def realized_pnl(self) -> Optional[float]:
        """已实现盈亏（结算后）"""
        if self.settlement_outcome is None:
            return None

        if self.side == "yes":
            win_value = 1.0 if self.settlement_outcome else 0.0
        else:
            win_value = 1.0 if not self.settlement_outcome else 0.0

        return self.size * (win_value - self.entry_price if self.side == "yes" else win_value - (1 - self.entry_price))


@dataclass
class SimulatedTrade:
    """模拟交易"""
    trade_id: str
    strategy: StrategyType
    status: TradeStatus
    created_at: str
    updated_at: str

    # 关联市场
    market_a_id: str
    market_a_question: str
    market_b_id: Optional[str] = None
    market_b_question: Optional[str] = None

    # 分析结果
    relationship: str = ""
    confidence: float = 0.0
    reasoning: str = ""

    # 仓位
    positions: List[Position] = field(default_factory=list)

    # 价格历史
    price_history: List[Dict] = field(default_factory=list)

    # 结算
    settlement_date: Optional[str] = None
    outcome_a: Optional[bool] = None
    outcome_b: Optional[bool] = None

    # 收益
    total_cost: float = 0.0
    expected_return: float = 0.0
    actual_return: Optional[float] = None
    profit_loss: Optional[float] = None

    # 备注
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """转换为字典"""
        d = asdict(self)
        d["strategy"] = self.strategy.value
        d["status"] = self.status.value
        d["positions"] = [asdict(p) for p in self.positions]
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> "SimulatedTrade":
        """从字典创建"""
        data["strategy"] = StrategyType(data["strategy"])
        data["status"] = TradeStatus(data["status"])
        data["positions"] = [Position(**p) for p in data.get("positions", [])]
        return cls(**data)


class SimulationTracker:
    """
    模拟执行跟踪器

    用于记录和跟踪模拟交易，验证套利策略的有效性。
    数据持久化到 JSON 文件。
    """

    DEFAULT_DATA_DIR = "./simulation_data"
    TRADES_FILE = "simulated_trades.json"

    def __init__(self, data_dir: str = None):
        """
        初始化模拟跟踪器

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir or self.DEFAULT_DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.trades_file = self.data_dir / self.TRADES_FILE

        self.trades: Dict[str, SimulatedTrade] = {}
        self._load_trades()

    def _load_trades(self):
        """从文件加载交易记录"""
        if self.trades_file.exists():
            try:
                with open(self.trades_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for trade_id, trade_data in data.items():
                        self.trades[trade_id] = SimulatedTrade.from_dict(trade_data)
                logger.info(f"加载了 {len(self.trades)} 条模拟交易记录")
            except Exception as e:
                logger.error(f"加载交易记录失败: {e}")
                self.trades = {}

    def _save_trades(self):
        """保存交易记录到文件"""
        try:
            data = {tid: trade.to_dict() for tid, trade in self.trades.items()}
            with open(self.trades_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存交易记录失败: {e}")

    def _generate_trade_id(self) -> str:
        """生成交易ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        count = len(self.trades) + 1
        return f"SIM_{timestamp}_{count:04d}"

    def record_trade(
        self,
        market_a: Any,
        market_b: Optional[Any] = None,
        strategy: str = "implication",
        relationship: str = "",
        confidence: float = 0.0,
        reasoning: str = "",
        positions: Dict[str, float] = None,
        notes: str = ""
    ) -> str:
        """
        记录模拟交易

        Args:
            market_a: 市场A
            market_b: 市场B（可选，完备集套利可能有多个）
            strategy: 策略类型
            relationship: 关系类型
            confidence: 置信度
            reasoning: 分析推理
            positions: 仓位配置，如 {"a_yes": 100, "a_no": 0, "b_yes": 100, "b_no": 0}
            notes: 备注

        Returns:
            trade_id
        """
        trade_id = self._generate_trade_id()
        now = datetime.now().isoformat()

        # 解析策略类型
        try:
            strategy_type = StrategyType(strategy)
        except ValueError:
            strategy_type = StrategyType.IMPLICATION

        # 构建仓位
        trade_positions = []
        total_cost = 0.0

        positions = positions or {}

        # Market A positions
        a_id = getattr(market_a, 'condition_id', str(id(market_a)))
        a_question = getattr(market_a, 'question', str(market_a))
        a_yes_price = getattr(market_a, 'yes_price', 0.5)

        if positions.get("a_yes", 0) > 0:
            pos = Position(
                market_id=a_id,
                market_question=a_question,
                side="yes",
                size=positions["a_yes"],
                entry_price=a_yes_price,
                current_price=a_yes_price
            )
            trade_positions.append(pos)
            total_cost += positions["a_yes"] * a_yes_price

        if positions.get("a_no", 0) > 0:
            pos = Position(
                market_id=a_id,
                market_question=a_question,
                side="no",
                size=positions["a_no"],
                entry_price=1 - a_yes_price,
                current_price=1 - a_yes_price
            )
            trade_positions.append(pos)
            total_cost += positions["a_no"] * (1 - a_yes_price)

        # Market B positions
        b_id = None
        b_question = None
        if market_b:
            b_id = getattr(market_b, 'condition_id', str(id(market_b)))
            b_question = getattr(market_b, 'question', str(market_b))
            b_yes_price = getattr(market_b, 'yes_price', 0.5)

            if positions.get("b_yes", 0) > 0:
                pos = Position(
                    market_id=b_id,
                    market_question=b_question,
                    side="yes",
                    size=positions["b_yes"],
                    entry_price=b_yes_price,
                    current_price=b_yes_price
                )
                trade_positions.append(pos)
                total_cost += positions["b_yes"] * b_yes_price

            if positions.get("b_no", 0) > 0:
                pos = Position(
                    market_id=b_id,
                    market_question=b_question,
                    side="no",
                    size=positions["b_no"],
                    entry_price=1 - b_yes_price,
                    current_price=1 - b_yes_price
                )
                trade_positions.append(pos)
                total_cost += positions["b_no"] * (1 - b_yes_price)

        # 计算预期收益
        expected_return = sum(p.size for p in trade_positions)  # 如果套利成功，收回全部本金

        trade = SimulatedTrade(
            trade_id=trade_id,
            strategy=strategy_type,
            status=TradeStatus.OPEN,
            created_at=now,
            updated_at=now,
            market_a_id=a_id,
            market_a_question=a_question,
            market_b_id=b_id,
            market_b_question=b_question,
            relationship=relationship,
            confidence=confidence,
            reasoning=reasoning,
            positions=trade_positions,
            price_history=[{
                "timestamp": now,
                "prices": {
                    "a_yes": a_yes_price,
                    "b_yes": getattr(market_b, 'yes_price', None) if market_b else None
                }
            }],
            total_cost=total_cost,
            expected_return=expected_return,
            notes=[notes] if notes else []
        )

        self.trades[trade_id] = trade
        self._save_trades()

        logger.info(f"记录模拟交易: {trade_id}, 策略: {strategy}, 成本: ${total_cost:.2f}")
        return trade_id

    def update_prices(
        self,
        trade_id: str,
        prices: Dict[str, float]
    ) -> bool:
        """
        更新交易的当前价格

        Args:
            trade_id: 交易ID
            prices: 价格字典，如 {"a_yes": 0.55, "b_yes": 0.52}

        Returns:
            是否更新成功
        """
        if trade_id not in self.trades:
            logger.warning(f"交易不存在: {trade_id}")
            return False

        trade = self.trades[trade_id]
        if trade.status != TradeStatus.OPEN:
            logger.warning(f"交易已关闭: {trade_id}")
            return False

        now = datetime.now().isoformat()

        # 更新仓位当前价格
        for pos in trade.positions:
            if "a" in prices and pos.market_id == trade.market_a_id:
                if pos.side == "yes":
                    pos.current_price = prices.get("a_yes", pos.current_price)
                else:
                    pos.current_price = 1 - prices.get("a_yes", 1 - pos.current_price)
            elif "b" in prices and pos.market_id == trade.market_b_id:
                if pos.side == "yes":
                    pos.current_price = prices.get("b_yes", pos.current_price)
                else:
                    pos.current_price = 1 - prices.get("b_yes", 1 - pos.current_price)

        # 记录价格历史
        trade.price_history.append({
            "timestamp": now,
            "prices": prices
        })

        trade.updated_at = now
        self._save_trades()

        return True

    def settle_trade(
        self,
        trade_id: str,
        outcome_a: bool,
        outcome_b: Optional[bool] = None,
        notes: str = ""
    ) -> Dict:
        """
        结算交易

        Args:
            trade_id: 交易ID
            outcome_a: 市场A的结果 (True=YES wins)
            outcome_b: 市场B的结果 (True=YES wins)
            notes: 结算备注

        Returns:
            结算结果字典
        """
        if trade_id not in self.trades:
            return {"error": f"交易不存在: {trade_id}"}

        trade = self.trades[trade_id]
        if trade.status != TradeStatus.OPEN:
            return {"error": f"交易已关闭: {trade_id}"}

        now = datetime.now().isoformat()

        # 记录结算结果
        trade.outcome_a = outcome_a
        trade.outcome_b = outcome_b
        trade.settlement_date = now

        # 计算各仓位的实际收益
        total_return = 0.0
        for pos in trade.positions:
            if pos.market_id == trade.market_a_id:
                pos.settlement_outcome = outcome_a
            elif pos.market_id == trade.market_b_id:
                pos.settlement_outcome = outcome_b

            # 计算收益
            if pos.settlement_outcome is not None:
                if pos.side == "yes":
                    win_value = pos.size if pos.settlement_outcome else 0
                else:
                    win_value = pos.size if not pos.settlement_outcome else 0
                total_return += win_value

        # 计算盈亏
        trade.actual_return = total_return
        trade.profit_loss = total_return - trade.total_cost

        trade.status = TradeStatus.SETTLED
        trade.updated_at = now
        if notes:
            trade.notes.append(f"[结算] {notes}")

        self._save_trades()

        result = {
            "trade_id": trade_id,
            "total_cost": trade.total_cost,
            "actual_return": trade.actual_return,
            "profit_loss": trade.profit_loss,
            "roi": (trade.profit_loss / trade.total_cost * 100) if trade.total_cost > 0 else 0,
            "outcome_a": outcome_a,
            "outcome_b": outcome_b
        }

        logger.info(f"结算交易 {trade_id}: 成本=${trade.total_cost:.2f}, 收益=${trade.actual_return:.2f}, 盈亏=${trade.profit_loss:.2f}")

        return result

    def cancel_trade(self, trade_id: str, reason: str = "") -> bool:
        """取消交易"""
        if trade_id not in self.trades:
            return False

        trade = self.trades[trade_id]
        trade.status = TradeStatus.CANCELLED
        trade.updated_at = datetime.now().isoformat()
        if reason:
            trade.notes.append(f"[取消] {reason}")

        self._save_trades()
        return True

    def get_trade(self, trade_id: str) -> Optional[SimulatedTrade]:
        """获取交易"""
        return self.trades.get(trade_id)

    def get_open_trades(self) -> List[SimulatedTrade]:
        """获取所有开仓中的交易"""
        return [t for t in self.trades.values() if t.status == TradeStatus.OPEN]

    def get_settled_trades(self) -> List[SimulatedTrade]:
        """获取所有已结算的交易"""
        return [t for t in self.trades.values() if t.status == TradeStatus.SETTLED]

    def generate_report(self) -> Dict:
        """
        生成模拟执行报告

        Returns:
            报告字典
        """
        settled = self.get_settled_trades()
        open_trades = self.get_open_trades()

        if not settled:
            return {
                "summary": "暂无已结算的模拟交易",
                "open_trades": len(open_trades),
                "total_trades": len(self.trades)
            }

        # 计算统计数据
        total_cost = sum(t.total_cost for t in settled)
        total_return = sum(t.actual_return or 0 for t in settled)
        total_pnl = sum(t.profit_loss or 0 for t in settled)
        win_count = sum(1 for t in settled if (t.profit_loss or 0) > 0)

        # 按策略分类
        by_strategy = {}
        for t in settled:
            key = t.strategy.value
            if key not in by_strategy:
                by_strategy[key] = {
                    "count": 0,
                    "total_cost": 0,
                    "total_pnl": 0,
                    "wins": 0
                }
            by_strategy[key]["count"] += 1
            by_strategy[key]["total_cost"] += t.total_cost
            by_strategy[key]["total_pnl"] += t.profit_loss or 0
            if (t.profit_loss or 0) > 0:
                by_strategy[key]["wins"] += 1

        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_trades": len(settled),
                "total_cost": total_cost,
                "total_return": total_return,
                "total_pnl": total_pnl,
                "roi_percent": (total_pnl / total_cost * 100) if total_cost > 0 else 0,
                "win_count": win_count,
                "win_rate": (win_count / len(settled) * 100) if settled else 0
            },
            "by_strategy": by_strategy,
            "open_trades_count": len(open_trades),
            "recent_trades": [
                {
                    "trade_id": t.trade_id,
                    "strategy": t.strategy.value,
                    "cost": t.total_cost,
                    "pnl": t.profit_loss,
                    "created": t.created_at[:10]
                }
                for t in sorted(settled, key=lambda x: x.settlement_date or "", reverse=True)[:10]
            ]
        }

        return report

    def export_report(self, filepath: str = None) -> str:
        """
        导出报告到文件

        Args:
            filepath: 输出文件路径

        Returns:
            输出文件路径
        """
        report = self.generate_report()

        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.data_dir / f"simulation_report_{timestamp}.json"

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"报告已导出: {filepath}")
        return str(filepath)


# ============================================================
# 便捷函数
# ============================================================

def create_tracker(data_dir: str = None) -> SimulationTracker:
    """创建模拟跟踪器"""
    return SimulationTracker(data_dir)


def record_opportunity(
    tracker: SimulationTracker,
    opportunity: Dict,
    trade_size: float = 100.0
) -> str:
    """
    从套利机会记录模拟交易

    Args:
        tracker: SimulationTracker 实例
        opportunity: 套利机会字典（来自 ArbitrageDetector）
        trade_size: 交易规模（USD）

    Returns:
        trade_id
    """
    strategy = opportunity.get("type", "implication")
    relationship = opportunity.get("relationship", "")

    # 构建仓位
    positions = {}
    execution = opportunity.get("execution", {})

    if "buy_yes" in execution:
        # 包含关系套利: 买入 B 的 YES
        positions["b_yes"] = trade_size

    if "buy_no" in execution:
        # 包含关系套利: 买入 A 的 NO
        positions["a_no"] = trade_size

    if "buy_cheaper_yes" in execution:
        # 等价市场套利
        positions["a_yes"] = trade_size
        positions["b_no"] = trade_size

    # 创建模拟市场对象
    class MockMarket:
        def __init__(self, data):
            self.condition_id = data.get("condition_id", "")
            self.question = data.get("question", "")
            self.yes_price = data.get("yes_price", 0.5)

    market_a = MockMarket(opportunity.get("market_a", {}))
    market_b = MockMarket(opportunity.get("market_b", {})) if opportunity.get("market_b") else None

    return tracker.record_trade(
        market_a=market_a,
        market_b=market_b,
        strategy=strategy,
        relationship=relationship,
        confidence=opportunity.get("confidence", 0.0),
        reasoning=opportunity.get("reasoning", ""),
        positions=positions,
        notes=f"Expected profit: {opportunity.get('expected_profit', 'N/A')}"
    )


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("模拟执行跟踪模块测试")
    print("=" * 60)

    # 创建跟踪器（使用临时目录）
    import tempfile
    temp_dir = tempfile.mkdtemp()
    tracker = SimulationTracker(temp_dir)

    # 模拟市场
    class MockMarket:
        def __init__(self, question, yes_price, condition_id=""):
            self.question = question
            self.yes_price = yes_price
            self.condition_id = condition_id or f"cid_{hash(question)}"

    market_a = MockMarket("Will Trump win?", 0.55, "trump_win")
    market_b = MockMarket("Will Republican win?", 0.52, "gop_win")

    # 记录模拟交易
    print("\n1. 记录模拟交易...")
    trade_id = tracker.record_trade(
        market_a=market_a,
        market_b=market_b,
        strategy="implication",
        relationship="IMPLIES_AB",
        confidence=0.85,
        reasoning="Trump win implies Republican win",
        positions={"a_no": 100, "b_yes": 100},
        notes="Test trade"
    )
    print(f"   Trade ID: {trade_id}")

    # 获取交易详情
    trade = tracker.get_trade(trade_id)
    print(f"   Status: {trade.status.value}")
    print(f"   Total Cost: ${trade.total_cost:.2f}")
    print(f"   Positions: {len(trade.positions)}")

    # 更新价格
    print("\n2. 更新价格...")
    tracker.update_prices(trade_id, {"a_yes": 0.58, "b_yes": 0.54})
    print("   Prices updated")

    # 结算
    print("\n3. 结算交易...")
    result = tracker.settle_trade(
        trade_id,
        outcome_a=True,   # Trump wins
        outcome_b=True,   # Republican wins
        notes="Both markets resolved YES"
    )
    print(f"   Actual Return: ${result['actual_return']:.2f}")
    print(f"   Profit/Loss: ${result['profit_loss']:.2f}")
    print(f"   ROI: {result['roi']:.1f}%")

    # 生成报告
    print("\n4. 生成报告...")
    report = tracker.generate_report()
    print(f"   Total Trades: {report['summary']['total_trades']}")
    print(f"   Total P&L: ${report['summary']['total_pnl']:.2f}")
    print(f"   Win Rate: {report['summary']['win_rate']:.1f}%")

    # 清理
    import shutil
    shutil.rmtree(temp_dir)

    print("\n测试完成！")
