"""
套利策略基类

所有套利策略都需要继承 BaseArbitrageStrategy 并实现必要的方法。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from local_scanner_v2 import Market, ArbitrageOpportunity


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"           # 数学验证，无需LLM
    MEDIUM = "medium"     # 需要LLM分析
    HIGH = "high"         # 需要人工深度验证


@dataclass
class StrategyMetadata:
    """策略元数据，用于菜单显示和注册"""

    id: str                         # 唯一标识符
    name: str                       # 显示名称（中文）
    name_en: str                    # 显示名称（英文）
    description: str                # 简短描述
    priority: int                   # 执行优先级（数字越小优先级越高）
    requires_llm: bool              # 是否需要LLM分析
    domains: List[str]              # 适用领域 ["crypto", "politics", "sports", "other", "all"]
    risk_level: RiskLevel           # 风险等级
    min_profit_threshold: float     # 最低利润阈值(%)

    # 可选字段
    icon: str = ""                  # 显示图标
    help_text: str = ""             # 帮助文本
    tags: List[str] = field(default_factory=list)  # 标签


class BaseArbitrageStrategy(ABC):
    """
    套利策略基类

    所有策略需要实现:
    1. metadata 属性 - 返回策略元数据
    2. scan() 方法 - 执行扫描并返回机会列表
    3. validate_opportunity() 方法 - 验证单个机会

    可选实现:
    - prepare() - 扫描前准备
    - cleanup() - 扫描后清理
    - get_progress_steps() - 返回进度步骤数
    """

    @property
    @abstractmethod
    def metadata(self) -> StrategyMetadata:
        """返回策略元数据"""
        pass

    @abstractmethod
    def scan(
        self,
        markets: List['Market'],
        config: Dict[str, Any],
        progress_callback: Optional[callable] = None
    ) -> List['ArbitrageOpportunity']:
        """
        执行策略扫描

        Args:
            markets: 市场列表
            config: 扫描配置
            progress_callback: 进度回调函数 (current, total, message)

        Returns:
            发现的套利机会列表
        """
        pass

    @abstractmethod
    def validate_opportunity(
        self,
        opportunity: 'ArbitrageOpportunity'
    ) -> bool:
        """
        验证单个套利机会

        Args:
            opportunity: 待验证的机会

        Returns:
            是否有效
        """
        pass

    def prepare(self, markets: List['Market'], config: Dict[str, Any]) -> None:
        """扫描前准备（可选覆盖）"""
        pass

    def cleanup(self) -> None:
        """扫描后清理（可选覆盖）"""
        pass

    def get_progress_steps(self, market_count: int) -> int:
        """
        返回预估的进度步骤数（可选覆盖）

        Args:
            market_count: 市场数量

        Returns:
            步骤数
        """
        return 1

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.metadata.id}>"
