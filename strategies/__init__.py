"""
套利策略模块 - 可扩展的策略注册表

使用方式:
    from strategies import StrategyRegistry, BaseArbitrageStrategy

    @StrategyRegistry.register
    class MyStrategy(BaseArbitrageStrategy):
        ...
"""

from .base import BaseArbitrageStrategy, StrategyMetadata
from .registry import StrategyRegistry

__all__ = ['BaseArbitrageStrategy', 'StrategyMetadata', 'StrategyRegistry']
