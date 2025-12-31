"""
进度追踪模块 - Progress Tracking Module

用于追踪扫描进度、记录历史状态，支持随时恢复工作。

核心功能：
1. 扫描状态管理 - 开始、更新、完成扫描
2. JSON结构化状态存储 - 供程序读取
3. Markdown人类可读日志 - 供人类查看
4. 历史记录管理 - 查询过往扫描
"""

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class ScanStatus(str, Enum):
    """扫描状态枚举"""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


@dataclass
class ScanState:
    """单次扫描状态"""
    scan_id: str
    timestamp: str
    status: ScanStatus

    # 市场数据
    total_markets: int = 0
    markets_analyzed: int = 0

    # 分析数据
    pairs_analyzed: int = 0
    llm_calls_made: int = 0
    patterns_matched: int = 0

    # 结果数据
    opportunities_found: int = 0
    opportunities_by_type: Dict[str, int] = field(default_factory=dict)

    # LLM配置
    llm_provider: str = "unknown"
    llm_model: str = "unknown"

    # 时间数据
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0

    # 反馈数据
    feedback_pending: int = 0
    feedback_collected: int = 0

    # 错误信息
    errors: List[str] = field(default_factory=list)

    # 备注
    notes: str = ""


@dataclass
class GlobalState:
    """全局状态 - 跨扫描的统计信息"""
    total_scans: int = 0
    total_opportunities: int = 0
    total_llm_calls: int = 0
    total_patterns: int = 0
    verified_patterns: int = 0
    last_scan_id: str = ""
    last_scan_time: str = ""


class ProgressTracker:
    """
    进度追踪器

    用法示例:
    >>> tracker = ProgressTracker()
    >>> state = tracker.start_scan({"llm_provider": "deepseek"})
    >>> tracker.update_progress(state.scan_id, pairs_analyzed=10)
    >>> tracker.complete_scan(state.scan_id, opportunities_found=2)
    """

    def __init__(self, state_dir: str = "./state", logs_dir: str = "./logs"):
        self.state_dir = Path(state_dir)
        self.logs_dir = Path(logs_dir)

        # 创建目录
        self.state_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)

        # 文件路径
        self.state_file = self.state_dir / "scan_state.json"
        self.history_file = self.logs_dir / "scan_history.md"
        self.global_file = self.state_dir / "global_state.json"

        # 初始化
        self._ensure_files()

    def _ensure_files(self):
        """确保必要文件存在"""
        if not self.state_file.exists():
            self._write_json(self.state_file, {"current_scan": None, "history": []})

        if not self.global_file.exists():
            self._write_json(self.global_file, asdict(GlobalState()))

        if not self.history_file.exists():
            self.history_file.write_text("# Scan History\n\n记录所有扫描的历史日志\n\n")

    def _write_json(self, path: Path, data: Any):
        """写入JSON文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_json(self, path: Path) -> Any:
        """读取JSON文件"""
        if not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_global_state(self) -> GlobalState:
        """获取全局状态"""
        data = self._read_json(self.global_file)
        if data:
            return GlobalState(**data)
        return GlobalState()

    def update_global_state(self, **updates) -> None:
        """更新全局状态"""
        current = self.get_global_state()
        for key, value in updates.items():
            if hasattr(current, key):
                setattr(current, key, value)
        self._write_json(self.global_file, asdict(current))

    def start_scan(self, config: Dict[str, Any]) -> ScanState:
        """
        开始一次新的扫描

        Args:
            config: 扫描配置，包含 llm_provider, llm_model 等

        Returns:
            新创建的 ScanState
        """
        scan_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        now = datetime.now()
        now_str = now.isoformat()

        state = ScanState(
            scan_id=scan_id,
            timestamp=now_str,
            status=ScanStatus.RUNNING,
            started_at=now_str,
            llm_provider=config.get("llm_provider", "unknown"),
            llm_model=config.get("llm_model", "unknown"),
            opportunities_by_type={}
        )

        # 保存状态
        self._save_state(state)

        # 更新全局状态
        global_state = self.get_global_state()
        global_state.total_scans += 1
        global_state.last_scan_id = scan_id
        global_state.last_scan_time = now_str
        self._write_json(self.global_file, asdict(global_state))

        # 写入日志
        self._log_scan_start(state, config)

        return state

    def update_progress(self, scan_id: str, **updates) -> ScanState:
        """
        更新扫描进度

        Args:
            scan_id: 扫描ID
            **updates: 要更新的字段

        Returns:
            更新后的 ScanState
        """
        state = self.load_state(scan_id)
        if state is None:
            raise ValueError(f"Scan {scan_id} not found")

        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)

        self._save_state(state)
        return state

    def complete_scan(
        self,
        scan_id: str,
        opportunities: List[Dict[str, Any]] = None,
        errors: List[str] = None
    ) -> ScanState:
        """
        完成扫描

        Args:
            scan_id: 扫描ID
            opportunities: 发现的机会列表
            errors: 错误列表

        Returns:
            更新后的 ScanState
        """
        state = self.load_state(scan_id)
        if state is None:
            raise ValueError(f"Scan {scan_id} not found")

        state.status = ScanStatus.COMPLETED
        state.completed_at = datetime.now().isoformat()

        # 计算持续时间
        if state.started_at:
            start = datetime.fromisoformat(state.started_at)
            end = datetime.fromisoformat(state.completed_at)
            state.duration_seconds = (end - start).total_seconds()

        if opportunities:
            state.opportunities_found = len(opportunities)
            # 按类型统计
            for opp in opportunities:
                opp_type = opp.get("type", "unknown")
                state.opportunities_by_type[opp_type] = \
                    state.opportunities_by_type.get(opp_type, 0) + 1

        if errors:
            state.errors = errors

        self._save_state(state)

        # 更新全局统计
        global_state = self.get_global_state()
        global_state.total_opportunities += state.opportunities_found
        global_state.total_llm_calls += state.llm_calls_made
        self._write_json(self.global_file, asdict(global_state))

        # 写入完成日志
        self._log_scan_complete(state, opportunities or [])

        return state

    def fail_scan(self, scan_id: str, error: str) -> ScanState:
        """
        标记扫描失败

        Args:
            scan_id: 扫描ID
            error: 错误信息

        Returns:
            更新后的 ScanState
        """
        state = self.load_state(scan_id)
        if state is None:
            raise ValueError(f"Scan {scan_id} not found")

        state.status = ScanStatus.FAILED
        state.completed_at = datetime.now().isoformat()
        state.errors = [error]

        self._save_state(state)
        self._log_scan_error(state, error)

        return state

    def mark_needs_review(self, scan_id: str, count: int = None) -> ScanState:
        """
        标记需要人工审核

        Args:
            scan_id: 扫描ID
            count: 待审核的数量

        Returns:
            更新后的 ScanState
        """
        state = self.load_state(scan_id)
        if state is None:
            raise ValueError(f"Scan {scan_id} not found")

        state.status = ScanStatus.NEEDS_REVIEW
        if count is not None:
            state.feedback_pending = count

        self._save_state(state)
        return state

    def load_state(self, scan_id: str) -> Optional[ScanState]:
        """
        加载指定扫描状态

        Args:
            scan_id: 扫描ID

        Returns:
            ScanState 或 None
        """
        data = self._read_json(self.state_file)
        if data and data.get("current_scan"):
            current = data["current_scan"]
            if current.get("scan_id") == scan_id:
                # 转换状态字符串为枚举
                if isinstance(current.get("status"), str):
                    current["status"] = ScanStatus(current["status"])
                return ScanState(**current)

        # 查找历史记录
        if data and data.get("history"):
            for hist in data["history"]:
                if hist.get("scan_id") == scan_id:
                    if isinstance(hist.get("status"), str):
                        hist["status"] = ScanStatus(hist["status"])
                    return ScanState(**hist)

        return None

    def get_current_state(self) -> Optional[ScanState]:
        """获取当前正在进行的扫描状态"""
        data = self._read_json(self.state_file)
        if data and data.get("current_scan"):
            current = data["current_scan"]
            if current and current.get("status") == ScanStatus.RUNNING:
                if isinstance(current.get("status"), str):
                    current["status"] = ScanStatus(current["status"])
                return ScanState(**current)
        return None

    def get_history(self, limit: int = 10) -> List[ScanState]:
        """
        获取历史扫描记录

        Args:
            limit: 返回记录数量

        Returns:
            ScanState 列表
        """
        data = self._read_json(self.state_file)
        history = []

        if data and data.get("history"):
            for item in data["history"][:limit]:
                if isinstance(item.get("status"), str):
                    item["status"] = ScanStatus(item["status"])
                history.append(ScanState(**item))

        return history

    def _save_state(self, state: ScanState) -> None:
        """
        保存扫描状态到文件

        如果是正在运行的扫描，保存到 current_scan
        否则移动到 history
        """
        data = self._read_json(self.state_file)

        if data is None:
            data = {"current_scan": None, "history": []}

        state_dict = asdict(state)
        # 转换枚举为字符串
        if isinstance(state_dict.get("status"), ScanStatus):
            state_dict["status"] = state_dict["status"].value

        if state.status == ScanStatus.RUNNING:
            data["current_scan"] = state_dict
        else:
            # 从 current_scan 移除
            if data.get("current_scan", {}).get("scan_id") == state.scan_id:
                data["current_scan"] = None

            # 添加到历史（如果不存在）
            history = data.get("history", [])
            existing_idx = next(
                (i for i, h in enumerate(history) if h.get("scan_id") == state.scan_id),
                None
            )

            if existing_idx is not None:
                history[existing_idx] = state_dict
            else:
                history.insert(0, state_dict)  # 最新的在前

            data["history"] = history[:100]  # 保留最近100条

        self._write_json(self.state_file, data)

    def _log_scan_start(self, state: ScanState, config: Dict[str, Any]) -> None:
        """写入扫描开始日志"""
        entry = f"""
## {state.started_at}

### Scan: {state.scan_id}
- **Status**: 开始扫描
- **LLM Provider**: {state.llm_provider}
- **LLM Model**: {state.llm_model}

### 配置
```json
{json.dumps(config, ensure_ascii=False, indent=2)}
```

---
"""
        self.history_file.write_text(
            self.history_file.read_text() + entry,
            encoding='utf-8'
        )

    def _log_scan_complete(self, state: ScanState, opportunities: List[Dict]) -> None:
        """写入扫描完成日志"""
        opp_summary = ""
        if opportunities:
            opp_summary = "\n### 发现的机会\n\n"
            for i, opp in enumerate(opportunities[:5], 1):  # 只显示前5个
                opp_summary += f"{i}. **{opp.get('type', 'Unknown')}** "
                opp_summary += f"({opp.get('profit_pct', 0):.1f}% profit)\n"
                opp_summary += f"   - {opp.get('relationship', 'N/A')}\n"

            if len(opportunities) > 5:
                opp_summary += f"\n... 还有 {len(opportunities) - 5} 个机会\n"

        entry = f"""
### 扫描完成: {state.scan_id}
- **状态**: {state.status.value}
- **耗时**: {state.duration_seconds:.1f} 秒
- **扫描市场**: {state.total_markets}
- **分析对数**: {state.pairs_analyzed}
- **LLM调用**: {state.llm_calls_made}
- **模式匹配**: {state.patterns_matched} (跳过LLM调用)
- **发现机会**: {state.opportunities_found}
{opp_summary}
---
"""
        self.history_file.write_text(
            self.history_file.read_text() + entry,
            encoding='utf-8'
        )

    def _log_scan_error(self, state: ScanState, error: str) -> None:
        """写入扫描错误日志"""
        entry = f"""
### 扫描失败: {state.scan_id}
- **错误**: {error}

---
"""
        self.history_file.write_text(
            self.history_file.read_text() + entry,
            encoding='utf-8'
        )

    def add_feedback_collected(self, scan_id: str, count: int = 1) -> None:
        """
        记录收集的反馈数量

        Args:
            scan_id: 扫描ID
            count: 收集的反馈数量
        """
        state = self.load_state(scan_id)
        if state:
            state.feedback_collected += count
            state.feedback_pending = max(0, state.feedback_pending - count)
            self._save_state(state)

    def add_pattern_match(self, scan_id: str) -> None:
        """
        记录模式匹配

        Args:
            scan_id: 扫描ID
        """
        state = self.load_state(scan_id)
        if state:
            state.patterns_matched += 1
            self._save_state(state)

    def increment_llm_calls(self, scan_id: str, count: int = 1) -> None:
        """
        增加LLM调用计数

        Args:
            scan_id: 扫描ID
            count: 增加的数量
        """
        state = self.load_state(scan_id)
        if state:
            state.llm_calls_made += count
            self._save_state(state)


def resume_from_last_scan(tracker: ProgressTracker) -> Optional[ScanState]:
    """
    从上次未完成的扫描恢复

    Args:
        tracker: 进度追踪器

    Returns:
        未完成的 ScanState，如果没有则返回 None
    """
    current = tracker.get_current_state()
    if current:
        print(f"发现未完成的扫描: {current.scan_id}")
        print(f"开始时间: {current.started_at}")
        print(f"已分析: {current.pairs_analyzed} 对市场")
        return current
    return None


# 便捷函数
def get_tracker() -> ProgressTracker:
    """获取进度追踪器实例（使用默认路径）"""
    return ProgressTracker()


if __name__ == "__main__":
    # 测试代码
    tracker = get_tracker()

    # 开始扫描
    state = tracker.start_scan({
        "llm_provider": "deepseek",
        "llm_model": "deepseek-chat",
        "market_limit": 200
    })
    print(f"开始扫描: {state.scan_id}")

    # 更新进度
    tracker.update_progress(state.scan_id, total_markets=200, pairs_analyzed=5)
    tracker.increment_llm_calls(state.scan_id, 5)
    tracker.add_pattern_match(state.scan_id)

    # 完成扫描
    opportunities = [
        {"type": "IMPLICATION_VIOLATION", "profit_pct": 5.3},
        {"type": "EXHAUSTIVE_SET", "profit_pct": 7.5}
    ]
    tracker.complete_scan(state.scan_id, opportunities)

    print(f"扫描完成: {state.scan_id}")
    print(f"发现机会: {tracker.load_state(state.scan_id).opportunities_found}")
