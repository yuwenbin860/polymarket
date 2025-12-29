#!/usr/bin/env python3
"""
系统配置文件
============

支持从环境变量和配置文件加载配置
"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any


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
    max_llm_calls: int = 30


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
        
        return cls(
            llm=LLMSettings(**data.get("llm", {})),
            scan=ScanSettings(**data.get("scan", {})),
            output=OutputSettings(**data.get("output", {})),
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
    "max_llm_calls": 30
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


if __name__ == "__main__":
    # 测试配置加载
    config = Config.load()
    print("当前配置:")
    print(f"  LLM Provider: {config.llm.provider}")
    print(f"  LLM Model: {config.llm.model or '(默认)'}")
    print(f"  Min Profit: {config.scan.min_profit_pct}%")
    print(f"  Log Level: {config.output.log_level}")
