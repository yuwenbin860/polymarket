#!/usr/bin/env python3
"""
系统配置文件
============

支持从环境变量和配置文件加载配置
"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List


@dataclass
class LLMSettings:
    """LLM配置"""
    # 提供商: openai / anthropic / aliyun / zhipu / deepseek / ollama / openai_compatible
    provider: str = "openai"
    
    # 模型名称（留空使用默认）
    model: str = ""
    
    # API密钥（留空从环境变量读取）
    api_key: str = ""
    
    # API地址（留空使用默认）
    api_base: str = ""
    
    # 生成参数
    max_tokens: int = 2000
    temperature: float = 0.7
    timeout: int = 60


@dataclass
class ScanSettings:
    """扫描配置"""
    # 获取市场数量
    market_limit: int = 200

    # 相似度阈值
    similarity_threshold: float = 0.3

    # 最小利润百分比
    min_profit_pct: float = 2.0

    # 最小流动性（USDC）
    min_liquidity: float = 10000

    # 最小LLM置信度
    min_confidence: float = 0.8

    # 每次扫描最大LLM调用次数
    max_llm_calls: int = 300

    # 🆕 向量化相关配置
    # 是否启用语义聚类（向量化模式）
    use_semantic_clustering: bool = True

    # 聚类相似度阈值 (0.0-1.0)
    semantic_threshold: float = 0.85

    # Embedding模型名称
    embedding_model: str = "BAAI/bge-large-zh-v1.5"

    # 🆕 缓存相关配置
    # 是否启用市场数据缓存
    enable_cache: bool = True

    # 缓存有效期（秒）
    cache_ttl: int = 3600

    # 🆕 领域相关配置
    # 扫描的默认市场领域
    scan_domain: str = "crypto"

    # 🆕 子类别筛选配置（v2.1新增）
    # 子类别筛选列表，留空表示获取整个领域的市场
    # 支持简写，如 ["btc", "eth"] 等同于 ["bitcoin", "ethereum"]
    # 会自动包含相关标签，如 "bitcoin" 自动包含 "bitcoin-prices", "bitcoin-volatility" 等
    scan_subcategories: List[str] = field(default_factory=list)

    # 🆕 分页相关配置
    # 是否启用全量获取（默认False=保持旧行为，最多100个市场）
    enable_full_fetch: bool = False

    # 每页大小
    fetch_page_size: int = 100

    # 每个tag最大获取数量（0=全量获取）
    fetch_max_per_tag: int = 0

    # API请求速率限制（每秒请求数）
    fetch_rate_limit: float = 2.0


@dataclass
class OutputSettings:
    """输出配置"""
    # 输出目录
    output_dir: str = "./output"
    
    # 缓存目录
    cache_dir: str = "./cache"
    
    # 日志级别: DEBUG / INFO / WARNING / ERROR
    log_level: str = "INFO"
    
    # 详细日志
    detailed_log: bool = True


@dataclass
class Config:
    """主配置类"""
    llm: LLMSettings = field(default_factory=LLMSettings)
    scan: ScanSettings = field(default_factory=ScanSettings)
    output: OutputSettings = field(default_factory=OutputSettings)

    # 🆕 多LLM配置支持
    llm_profiles: Dict[str, Any] = field(default_factory=dict)  # 多个LLM配置
    active_profile: str = ""  # 当前激活的profile名称

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载配置"""
        return cls(
            llm=LLMSettings(
                provider=os.getenv("LLM_PROVIDER", "openai"),
                model=os.getenv("LLM_MODEL", ""),
                api_key=os.getenv("LLM_API_KEY", ""),
                api_base=os.getenv("LLM_API_BASE", ""),
                max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2000")),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            ),
            scan=ScanSettings(
                market_limit=int(os.getenv("MARKET_LIMIT", "200")),
                min_profit_pct=float(os.getenv("MIN_PROFIT_PCT", "2.0")),
                min_liquidity=float(os.getenv("MIN_LIQUIDITY", "10000")),
                min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.8")),
                use_semantic_clustering=os.getenv("USE_SEMANTIC_CLUSTERING", "true").lower() == "true",
                semantic_threshold=float(os.getenv("SEMANTIC_THRESHOLD", "0.85")),
                enable_cache=os.getenv("ENABLE_CACHE", "true").lower() == "true",
                cache_ttl=int(os.getenv("CACHE_TTL", "3600")),
                scan_domain=os.getenv("SCAN_DOMAIN", "crypto"),
                scan_subcategories=os.getenv("SCAN_SUBCATEGORIES", "").split(",") if os.getenv("SCAN_SUBCATEGORIES") else [],
            ),
            output=OutputSettings(
                output_dir=os.getenv("OUTPUT_DIR", "./output"),
                log_level=os.getenv("LOG_LEVEL", "INFO"),
                detailed_log=os.getenv("DETAILED_LOG", "true").lower() == "true",
            )
        )
    
    @classmethod
    def from_file(cls, path: str) -> "Config":
        """从JSON文件加载配置"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        def _filter_comments(d: dict) -> dict:
            """过滤掉以 _ 开头的注释字段"""
            return {k: v for k, v in d.items() if not k.startswith('_')}

        def _filter_for_llm_settings(d: dict) -> dict:
            """过滤掉 LLMSettings 不支持的字段（如 embedding_model）"""
            allowed = {'provider', 'model', 'api_key', 'api_base', 'max_tokens', 'temperature', 'timeout'}
            return {k: v for k, v in d.items() if k in allowed}

        # 获取 llm_profiles 和 active_profile
        llm_profiles = data.get("llm_profiles", {})
        active_profile = data.get("active_profile", "")

        # 从 active_profile 加载 llm 配置（不再支持独立的 llm 字段）
        llm_data = {}
        if active_profile and active_profile in llm_profiles:
            llm_data = llm_profiles[active_profile]

        return cls(
            llm=LLMSettings(**_filter_for_llm_settings(llm_data)) if llm_data else LLMSettings(),
            scan=ScanSettings(**_filter_comments(data.get("scan", {}))),
            output=OutputSettings(**_filter_comments(data.get("output", {}))),
            llm_profiles=llm_profiles,
            active_profile=active_profile,
        )
    
    def to_file(self, path: str):
        """保存配置到文件"""
        data = {
            "llm": asdict(self.llm),
            "scan": asdict(self.scan),
            "output": asdict(self.output),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_llm_profile(self, profile_name: Optional[str] = None) -> LLMSettings:
        """
        获取指定profile的LLM配置

        优先级：
        1. 指定的profile_name（如果存在于llm_profiles中）
        2. active_profile指定的配置
        3. llm字段（向后兼容）

        Args:
            profile_name: profile名称，留空则使用active_profile

        Returns:
            LLMSettings配置对象
        """
        name = profile_name or self.active_profile

        if name and name in self.llm_profiles:
            profile_data = self.llm_profiles[name]
            return LLMSettings(
                provider=profile_data.get("provider", "openai"),
                model=profile_data.get("model", ""),
                api_key=profile_data.get("api_key", ""),
                api_base=profile_data.get("api_base", ""),
                max_tokens=profile_data.get("max_tokens", 2000),
                temperature=profile_data.get("temperature", 0.7),
                timeout=profile_data.get("timeout", 60),
            )

        # 回退到llm字段（向后兼容）
        return self.llm

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """
        加载配置
        
        优先级：
        1. 指定的配置文件
        2. 当前目录的 config.json
        3. 环境变量
        4. 默认值
        """
        # 尝试从文件加载
        if config_path and os.path.exists(config_path):
            return cls.from_file(config_path)
        
        if os.path.exists("config.json"):
            return cls.from_file("config.json")
        
        # 从环境变量加载
        return cls.from_env()


# 默认配置模板
DEFAULT_CONFIG_TEMPLATE = """{
  "llm": {
    "provider": "openai",
    "model": "",
    "api_key": "",
    "api_base": "",
    "max_tokens": 2000,
    "temperature": 0.7,
    "timeout": 60
  },
  "scan": {
    "market_limit": 200,
    "similarity_threshold": 0.3,
    "min_profit_pct": 2.0,
    "min_liquidity": 10000,
    "min_confidence": 0.8,
    "max_llm_calls": 30,
    "use_semantic_clustering": true,
    "semantic_threshold": 0.85,
    "embedding_model": "BAAI/bge-large-zh-v1.5",
    "enable_cache": true,
    "cache_ttl": 3600,
    "scan_domain": "crypto"
  },
  "output": {
    "output_dir": "./output",
    "cache_dir": "./cache",
    "log_level": "INFO",
    "detailed_log": true
  }
}
"""


def create_default_config(path: str = "config.json"):
    """创建默认配置文件"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(DEFAULT_CONFIG_TEMPLATE)
    print(f"✅ 已创建配置文件: {path}")


