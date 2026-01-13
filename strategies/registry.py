"""
策略注册表

提供策略的注册、发现和管理功能。
使用装饰器模式自动注册策略。
"""

from typing import Dict, List, Type, Optional
from .base import BaseArbitrageStrategy, StrategyMetadata


class StrategyRegistry:
    """
    套利策略中央注册表

    使用方式:
        @StrategyRegistry.register
        class MonotonicityStrategy(BaseArbitrageStrategy):
            ...

        # 获取所有策略
        all_strategies = StrategyRegistry.get_all()

        # 按ID获取
        strategy = StrategyRegistry.get("monotonicity")

        # 按领域过滤
        crypto_strategies = StrategyRegistry.get_for_domain("crypto")
    """

    _strategies: Dict[str, Type[BaseArbitrageStrategy]] = {}
    _instances: Dict[str, BaseArbitrageStrategy] = {}  # 缓存实例

    @classmethod
    def register(cls, strategy_class: Type[BaseArbitrageStrategy]) -> Type[BaseArbitrageStrategy]:
        """
        装饰器：注册策略类

        使用:
            @StrategyRegistry.register
            class MyStrategy(BaseArbitrageStrategy):
                ...
        """
        # 创建临时实例获取metadata
        instance = strategy_class()
        strategy_id = instance.metadata.id

        if strategy_id in cls._strategies:
            raise ValueError(f"策略ID冲突: {strategy_id} 已被注册")

        cls._strategies[strategy_id] = strategy_class
        cls._instances[strategy_id] = instance

        return strategy_class

    @classmethod
    def get(cls, strategy_id: str) -> Optional[BaseArbitrageStrategy]:
        """
        按ID获取策略实例

        Args:
            strategy_id: 策略ID

        Returns:
            策略实例，不存在则返回None
        """
        if strategy_id not in cls._instances:
            strategy_class = cls._strategies.get(strategy_id)
            if strategy_class:
                cls._instances[strategy_id] = strategy_class()
        return cls._instances.get(strategy_id)

    @classmethod
    def get_class(cls, strategy_id: str) -> Optional[Type[BaseArbitrageStrategy]]:
        """按ID获取策略类"""
        return cls._strategies.get(strategy_id)

    @classmethod
    def get_all(cls) -> List[StrategyMetadata]:
        """
        获取所有已注册策略的元数据

        Returns:
            按优先级排序的策略元数据列表
        """
        metadata_list = []
        for strategy_id in cls._strategies:
            instance = cls.get(strategy_id)
            if instance:
                metadata_list.append(instance.metadata)
        return sorted(metadata_list, key=lambda m: m.priority)

    @classmethod
    def get_for_domain(cls, domain: str) -> List[StrategyMetadata]:
        """
        获取适用于指定领域的策略

        Args:
            domain: 领域名称 ("crypto", "politics", "sports", "other")

        Returns:
            按优先级排序的策略元数据列表
        """
        result = []
        for meta in cls.get_all():
            if "all" in meta.domains or domain in meta.domains:
                result.append(meta)
        return result

    @classmethod
    def get_by_ids(cls, strategy_ids: List[str]) -> List[BaseArbitrageStrategy]:
        """
        按ID列表获取策略实例

        Args:
            strategy_ids: 策略ID列表

        Returns:
            策略实例列表（按优先级排序）
        """
        instances = []
        for sid in strategy_ids:
            instance = cls.get(sid)
            if instance:
                instances.append(instance)
        return sorted(instances, key=lambda s: s.metadata.priority)

    @classmethod
    def list_ids(cls) -> List[str]:
        """获取所有已注册策略的ID列表"""
        return list(cls._strategies.keys())

    @classmethod
    def clear(cls) -> None:
        """清空注册表（仅用于测试）"""
        cls._strategies.clear()
        cls._instances.clear()

    @classmethod
    def count(cls) -> int:
        """获取已注册策略数量"""
        return len(cls._strategies)
