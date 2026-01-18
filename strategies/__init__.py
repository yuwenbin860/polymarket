"""
套利策略模块 - 可扩展的策略注册表

使用方式:
    from strategies import StrategyRegistry, BaseArbitrageStrategy

    @StrategyRegistry.register
    class MyStrategy(BaseArbitrageStrategy):
        ...
"""

from .base import BaseArbitrageStrategy, StrategyMetadata, RiskLevel
from .registry import StrategyRegistry

# 自动导入所有策略模块（使装饰器能执行）
from . import (
    monotonicity,
    exhaustive,
    implication,
    equivalent,
    interval,
    temporal
)

__all__ = [
    'BaseArbitrageStrategy',
    'StrategyMetadata',
    'StrategyRegistry',
    'RiskLevel',
]
