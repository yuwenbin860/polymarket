#!/usr/bin/env python3
"""
LLM配置管理器
=============

支持多个预设配置，方便在不同提供商和模型间快速切换。

使用方法：
    # 命令行切换
    python local_scanner_v2.py --profile siliconflow
    python local_scanner_v2.py --profile deepseek
    python local_scanner_v2.py --profile ollama
    
    # 环境变量切换
    export LLM_PROFILE=siliconflow
    python local_scanner_v2.py
    
    # 列出所有可用配置
    python llm_config.py --list
    
    # 测试某个配置
    python llm_config.py --test siliconflow
    
    # 添加新配置
    python llm_config.py --add
"""

import os
import json
import sys
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, List
from pathlib import Path


# ============================================================
# 场景常量
# ============================================================

class LLMScenario:
    """
    LLM使用场景常量

    定义系统中使用LLM的不同场景，可以为每个场景配置专用模型。
    """
    # Tag分类场景 - 使用思考模型进行智能分类
    TAG_CLASSIFICATION = "tag_classification"
    # 策略扫描场景 - 使用快速模型进行套利策略分析
    STRATEGY_SCAN = "strategy_scan"
    # 语义分析场景 - 使用快速模型进行语义相似度分析
    SEMANTIC_ANALYSIS = "semantic_analysis"
    # 关系检测场景 - 使用思考模型进行市场关系推理
    RELATIONSHIP_DETECTION = "relationship_detection"


# ============================================================
# 配置数据结构
# ============================================================

@dataclass
class LLMProfile:
    """单个LLM配置"""
    name: str                    # 配置名称
    provider: str                # 提供商类型
    api_base: str                # API地址
    api_key_env: str = ""        # API Key环境变量名（不直接存储key）
    api_key: str = ""            # 直接配置的API Key（可选，用于config.json）
    model: str = ""              # 默认模型
    description: str = ""        # 描述
    models_available: List[str] = field(default_factory=list)  # 可用模型列表
    max_tokens: int = 2000
    temperature: float = 0.7
    # 场景化模型配置：为不同任务场景指定专用模型
    scenario_models: Dict[str, str] = field(default_factory=dict)

    def get_api_key(self) -> Optional[str]:
        """获取API Key - 优先使用直接配置的key，否则从环境变量读取"""
        # 优先返回直接配置的api_key（来自config.json）
        if self.api_key:
            return self.api_key
        # 否则从环境变量读取
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return None

    def is_configured(self) -> bool:
        """检查是否已配置API Key"""
        if self.provider == "ollama":
            return True  # Ollama不需要key
        return bool(self.get_api_key())

    def get_model_for_scenario(self, scenario: str) -> str:
        """
        获取指定场景的模型

        如果场景没有配置专用模型，则返回默认模型。

        Args:
            scenario: 场景名称，如 "tag_classification", "strategy_scan"

        Returns:
            该场景使用的模型名称
        """
        return self.scenario_models.get(scenario, self.model)

    def is_reasoning_model(self, model: Optional[str] = None) -> bool:
        """
        判断指定模型是否为思考模型

        Args:
            model: 模型名称，如果为None则使用默认模型

        Returns:
            是否为思考模型
        """
        from llm_providers import is_reasoning_model
        model_name = model or self.model
        return is_reasoning_model(model_name)

    def get_reasoning_model(self) -> Optional[str]:
        """
        获取可用的思考模型

        返回第一个可用的思考模型名称，如果没有则返回None。

        Returns:
            思考模型名称或None
        """
        from llm_providers import is_reasoning_model
        for m in self.models_available:
            if is_reasoning_model(m):
                return m
        # 检查默认模型
        if is_reasoning_model(self.model):
            return self.model
        return None

    def get_fast_model(self) -> Optional[str]:
        """
        获取可用的快速模型

        返回第一个可用的非思考模型名称，如果没有则返回None。

        Returns:
            快速模型名称或None
        """
        from llm_providers import is_reasoning_model
        for m in self.models_available:
            if not is_reasoning_model(m):
                return m
        # 检查默认模型
        if not is_reasoning_model(self.model):
            return self.model
        return None


# ============================================================
# 预设配置
# ============================================================

BUILTIN_PROFILES: Dict[str, LLMProfile] = {
    # SiliconFlow - 国内聚合平台
    "siliconflow": LLMProfile(
        name="siliconflow",
        provider="openai_compatible",
        api_base="https://api.siliconflow.cn/v1",
        api_key_env="SILICONFLOW_API_KEY",
        model="deepseek-ai/DeepSeek-V3",
        description="SiliconFlow - 国内聚合平台，速度快",
        models_available=[
            "Qwen/Qwen2.5-72B-Instruct",
            "Qwen/Qwen2.5-32B-Instruct",
            "Qwen/Qwen2.5-7B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
            "Pro/deepseek-ai/DeepSeek-R1",
            "THUDM/glm-4-9b-chat",
            "Pro/zai-org/GLM-4.7",
        ],
        scenario_models={
            LLMScenario.TAG_CLASSIFICATION: "deepseek-ai/DeepSeek-R1",  # Tag分类用思考模型
            LLMScenario.STRATEGY_SCAN: "deepseek-ai/DeepSeek-V3",       # 策略扫描用快速模型
        }
    ),

    # DeepSeek官方
    "deepseek": LLMProfile(
        name="deepseek",
        provider="openai_compatible",
        api_base="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        model="deepseek-chat",
        description="DeepSeek官方 - 便宜好用",
        models_available=[
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        scenario_models={
            LLMScenario.TAG_CLASSIFICATION: "deepseek-reasoner",    # Tag分类用思考模型
            LLMScenario.STRATEGY_SCAN: "deepseek-chat",            # 策略扫描用快速模型
        }
    ),
    
    # OpenAI
    "openai": LLMProfile(
        name="openai",
        provider="openai",
        api_base="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        model="gpt-4o",
        description="OpenAI - GPT系列",
        models_available=[
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ]
    ),
    
    # Anthropic Claude
    "anthropic": LLMProfile(
        name="anthropic",
        provider="anthropic",
        api_base="https://api.anthropic.com",
        api_key_env="ANTHROPIC_API_KEY",
        model="claude-sonnet-4-20250514",
        description="Anthropic - Claude系列",
        models_available=[
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
        ]
    ),
    
    # 阿里云通义
    "aliyun": LLMProfile(
        name="aliyun",
        provider="openai_compatible",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        model="qwen-plus",
        description="阿里云通义千问",
        models_available=[
            "qwen-turbo",
            "qwen-plus", 
            "qwen-max",
        ]
    ),
    
    # 智谱GLM
    "zhipu": LLMProfile(
        name="zhipu",
        provider="openai_compatible",
        api_base="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPU_API_KEY",
        model="glm-4-plus",
        description="智谱AI - GLM系列",
        models_available=[
            "glm-4-plus",
            "glm-4",
            "glm-4-flash",
        ]
    ),
    
    # 本地Ollama
    "ollama": LLMProfile(
        name="ollama",
        provider="ollama",
        api_base="http://localhost:11434",
        api_key_env="",
        model="qwen2.5:7b",
        description="本地Ollama - 免费离线",
        models_available=[
            "llama3.1:8b",
            "llama3.1:70b",
            "qwen2.5:7b",
            "qwen2.5:14b",
            "qwen2.5:32b",
            "deepseek-r1:7b",
            "deepseek-r1:14b",
        ],
        scenario_models={
            LLMScenario.TAG_CLASSIFICATION: "deepseek-r1:7b",   # Tag分类用思考模型
            LLMScenario.STRATEGY_SCAN: "qwen2.5:7b",           # 策略扫描用快速模型
        }
    ),
    
    # OpenRouter - 国外聚合
    "openrouter": LLMProfile(
        name="openrouter",
        provider="openai_compatible",
        api_base="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        model="anthropic/claude-3.5-sonnet",
        description="OpenRouter - 国外聚合平台",
        models_available=[
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "google/gemini-pro",
            "meta-llama/llama-3.1-70b-instruct",
        ]
    ),

    # ModelScope - 阿里云模型托管平台
    "modelscope": LLMProfile(
        name="modelscope",
        provider="modelscope",
        api_base="https://api-inference.modelscope.cn/v1",
        api_key_env="MODELSCOPE_API_KEY",
        model="Qwen/Qwen2.5-72B-Instruct",
        description="ModelScope - 阿里云模型托管平台",
        models_available=[
            "Qwen/Qwen2.5-72B-Instruct",
            "Qwen/Qwen2.5-32B-Instruct",
            "Qwen/Qwen2.5-14B-Instruct",
            "Qwen/Qwen2.5-7B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
        ],
        scenario_models={
            LLMScenario.TAG_CLASSIFICATION: "deepseek-ai/DeepSeek-R1",  # Tag分类用思考模型
            LLMScenario.STRATEGY_SCAN: "Qwen/Qwen2.5-32B-Instruct",     # 策略扫描用快速模型
        }
    ),
}


# ============================================================
# 配置管理器
# ============================================================

class LLMConfigManager:
    """LLM配置管理器"""
    
    CONFIG_FILE = "config.json"

    def __init__(self):
        self.profiles: Dict[str, LLMProfile] = BUILTIN_PROFILES.copy()
        self._load_custom_profiles()

    def _load_custom_profiles(self):
        """加载用户自定义配置 - 从config.json的llm_profiles区段读取"""
        config_path = Path(self.CONFIG_FILE)
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 从config.json的llm_profiles区段读取
                llm_profiles = data.get("llm_profiles", {})

                for name, profile_data in llm_profiles.items():
                    # 过滤掉以_开头的注释字段和不支持的字段
                    unsupported_fields = {'embedding_model'}
                    filtered_data = {
                        k: v for k, v in profile_data.items()
                        if not k.startswith('_') and k not in unsupported_fields
                    }

                    # 创建LLMProfile，确保name字段存在
                    if "name" not in filtered_data:
                        filtered_data["name"] = name

                    # 如果没有api_key_env，设置为空字符串（允许使用api_key）
                    if "api_key_env" not in filtered_data:
                        filtered_data["api_key_env"] = ""

                    # 过滤scenario_models中的注释字段
                    if "scenario_models" in filtered_data and isinstance(filtered_data["scenario_models"], dict):
                        filtered_data["scenario_models"] = {
                            k: v for k, v in filtered_data["scenario_models"].items()
                            if not k.startswith('_')
                        }

                    self.profiles[name] = LLMProfile(**filtered_data)
            except Exception as e:
                # 使用简单的ASCII字符避免编码问题
                print(f"[WARNING] Failed to load custom profiles: {e}")
    
    def save_custom_profile(self, profile: LLMProfile):
        """保存自定义配置"""
        config_path = Path(self.CONFIG_FILE)
        
        # 读取现有配置
        data = {"profiles": {}}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        
        # 添加/更新配置
        data["profiles"][profile.name] = asdict(profile)
        
        # 保存
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        self.profiles[profile.name] = profile
    
    def get_profile(self, name: str) -> Optional[LLMProfile]:
        """获取配置"""
        return self.profiles.get(name)
    
    def list_profiles(self) -> List[LLMProfile]:
        """列出所有配置"""
        return list(self.profiles.values())
    
    def get_configured_profiles(self) -> List[LLMProfile]:
        """获取已配置API Key的配置"""
        return [p for p in self.profiles.values() if p.is_configured()]
    
    def detect_profile(self) -> Optional[LLMProfile]:
        """自动检测可用的配置"""
        # 优先级顺序
        priority = ["siliconflow", "deepseek", "modelscope", "aliyun", "zhipu", "openai", "anthropic", "ollama"]

        for name in priority:
            profile = self.profiles.get(name)
            if profile and profile.is_configured():
                return profile

        return None
    
    def get_active_profile(self) -> Optional[LLMProfile]:
        """
        获取当前激活的配置
        
        优先级：
        1. 环境变量 LLM_PROFILE
        2. 自动检测
        """
        # 检查环境变量
        profile_name = os.getenv("LLM_PROFILE")
        if profile_name:
            profile = self.get_profile(profile_name)
            if profile:
                return profile
            print(f"⚠️ 未找到配置: {profile_name}")
        
        # 自动检测
        return self.detect_profile()


# ============================================================
# 命令行工具
# ============================================================

def print_profiles_table(profiles: List[LLMProfile], show_status: bool = True):
    """打印配置表格

    Args:
        profiles: 要显示的配置列表
        show_status: 是否显示配置状态
    """
    print("\n" + "=" * 80)
    print("可用的LLM配置")
    print("=" * 80)

    for p in profiles:
        if p.is_configured():
            status_icon = "[OK]"
            status_text = "已配置"
        else:
            status_icon = "[--]"
            status_text = f"未配置 (需要设置 {p.api_key_env})"

        if not show_status:
            status_icon = "    "

        print(f"\n{status_icon} [{p.name}]")
        print(f"   描述: {p.description}")
        print(f"   默认模型: {p.model}")
        if show_status:
            print(f"   状态: {status_text}")
        if p.models_available:
            models_str = ', '.join(p.models_available[:4])
            if len(p.models_available) > 4:
                models_str += '...'
            print(f"   可用模型: {models_str}")

    # 汇总统计
    configured = [p for p in profiles if p.is_configured()]
    print("\n" + "-" * 80)
    print(f"汇总: {len(configured)}/{len(profiles)} 个配置已就绪")
    if configured:
        ready_names = ', '.join(p.name for p in configured)
        print(f"可用配置: {ready_names}")
    else:
        print("⚠️  没有已配置的profile，请设置对应的API Key环境变量")


def test_profile(profile: LLMProfile) -> bool:
    """测试配置是否可用"""
    print(f"\n测试配置: {profile.name}")
    print(f"  API Base: {profile.api_base}")
    print(f"  Model: {profile.model}")
    
    if not profile.is_configured():
        print(f"  ❌ 未配置 API Key (需要设置环境变量: {profile.api_key_env})")
        return False
    
    try:
        # 动态导入避免循环依赖
        from llm_providers import create_llm_client
        
        client = create_llm_client(
            provider=profile.provider,
            api_base=profile.api_base,
            api_key=profile.get_api_key(),
            model=profile.model,
        )
        
        print("  发送测试请求...")
        response = client.chat("说'测试成功'这三个字")
        print(f"  ✅ 响应: {response.content[:50]}...")
        client.close()
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        return False


def interactive_add_profile():
    """交互式添加配置"""
    print("\n添加新的LLM配置")
    print("-" * 40)
    
    name = input("配置名称 (如 my-llm): ").strip()
    if not name:
        print("取消")
        return
    
    provider = input("提供商类型 [openai_compatible]: ").strip() or "openai_compatible"
    api_base = input("API地址: ").strip()
    api_key_env = input("API Key环境变量名: ").strip()
    model = input("默认模型: ").strip()
    description = input("描述 (可选): ").strip()
    
    profile = LLMProfile(
        name=name,
        provider=provider,
        api_base=api_base,
        api_key_env=api_key_env,
        model=model,
        description=description,
    )
    
    manager = LLMConfigManager()
    manager.save_custom_profile(profile)
    print(f"\n✅ 已保存配置: {name}")


def generate_env_template():
    """生成环境变量模板"""
    template = """# LLM API Keys 配置模板
# 复制此文件为 .env 并填入你的API Key

# 选择激活的配置 (可选，不设置则自动检测)
# LLM_PROFILE=siliconflow

# SiliconFlow (国内聚合平台，推荐)
SILICONFLOW_API_KEY=sk-your-key-here

# DeepSeek (官方，便宜)
DEEPSEEK_API_KEY=sk-your-key-here

# OpenAI
OPENAI_API_KEY=sk-your-key-here

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-your-key-here

# 阿里云通义千问
DASHSCOPE_API_KEY=sk-your-key-here

# 智谱GLM
ZHIPU_API_KEY=your-key-here

# OpenRouter (国外聚合)
OPENROUTER_API_KEY=sk-or-your-key-here
"""
    
    with open(".env.template", "w", encoding="utf-8") as f:
        f.write(template)
    print("✅ 已生成 .env.template")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM配置管理工具")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有配置")
    parser.add_argument("--test", "-t", type=str, help="测试指定配置")
    parser.add_argument("--add", "-a", action="store_true", help="添加新配置")
    parser.add_argument("--env-template", action="store_true", help="生成环境变量模板")
    parser.add_argument("--detect", "-d", action="store_true", help="自动检测可用配置")
    
    args = parser.parse_args()
    
    manager = LLMConfigManager()
    
    if args.list:
        print_profiles_table(manager.list_profiles())
        
    elif args.test:
        profile = manager.get_profile(args.test)
        if profile:
            test_profile(profile)
        else:
            print(f"❌ 未找到配置: {args.test}")
            
    elif args.add:
        interactive_add_profile()
        
    elif args.env_template:
        generate_env_template()
        
    elif args.detect:
        profile = manager.detect_profile()
        if profile:
            print(f"✅ 检测到可用配置: {profile.name}")
            print(f"   模型: {profile.model}")
        else:
            print("❌ 未检测到可用配置，请设置API Key")
            print("\n提示：运行 python llm_config.py --list 查看所有配置")
            
    else:
        # 默认显示帮助和状态
        print("\nLLM配置管理工具")
        print("=" * 50)
        
        configured = manager.get_configured_profiles()
        if configured:
            print(f"\n✅ 已配置的提供商: {', '.join(p.name for p in configured)}")
            
            active = manager.get_active_profile()
            if active:
                print(f"📌 当前激活: {active.name} ({active.model})")
        else:
            print("\n❌ 未检测到任何已配置的API Key")
        
        print("\n常用命令:")
        print("  python llm_config.py --list        # 查看所有配置")
        print("  python llm_config.py --test NAME   # 测试配置")
        print("  python llm_config.py --env-template # 生成.env模板")
        print("  python llm_config.py --add         # 添加自定义配置")


# ============================================================
# 便捷函数（供其他模块调用）
# ============================================================

def get_llm_config() -> Optional[LLMProfile]:
    """获取当前LLM配置（供扫描器调用）"""
    manager = LLMConfigManager()
    return manager.get_active_profile()


def get_llm_config_by_name(name: str) -> Optional[LLMProfile]:
    """根据名称获取配置"""
    manager = LLMConfigManager()
    return manager.get_profile(name)


def list_available_profiles() -> List[str]:
    """列出所有可用配置名"""
    manager = LLMConfigManager()
    return [p.name for p in manager.list_profiles()]


if __name__ == "__main__":
    main()
