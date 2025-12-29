#!/usr/bin/env python3
"""
LLM提供商抽象层
================

支持多种大模型API的统一接口，包括：
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- 阿里云 (通义千问)
- 百度 (文心一言)
- 智谱 (GLM-4)
- DeepSeek
- 本地模型 (Ollama)
- OpenAI兼容接口 (如vLLM, LocalAI, OneAPI等)

使用方法：
    from llm_providers import create_llm_client
    
    # 通过配置创建客户端
    client = create_llm_client(provider="openai", model="gpt-4o")
    
    # 或者从环境变量自动检测
    client = create_llm_client()
    
    # 调用
    response = client.chat("你好")
"""

import os
import json
import httpx
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum


# ============================================================
# 配置和常量
# ============================================================

class LLMProvider(Enum):
    """支持的LLM提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ALIYUN = "aliyun"          # 通义千问
    BAIDU = "baidu"            # 文心一言
    ZHIPU = "zhipu"            # 智谱GLM
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"          # 本地Ollama
    OPENAI_COMPATIBLE = "openai_compatible"  # OpenAI兼容接口


@dataclass
class LLMConfig:
    """LLM配置"""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    max_tokens: int = 2000
    temperature: float = 0.7
    timeout: int = 60
    
    # 额外参数（不同提供商可能需要）
    extra_params: Optional[Dict[str, Any]] = None


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None  # {"prompt_tokens": x, "completion_tokens": y}
    raw_response: Optional[Dict] = None


# ============================================================
# 默认模型配置
# ============================================================

DEFAULT_MODELS = {
    LLMProvider.OPENAI: "gpt-4o",
    LLMProvider.ANTHROPIC: "claude-sonnet-4-20250514",
    LLMProvider.ALIYUN: "qwen-plus",
    LLMProvider.BAIDU: "ernie-4.0-8k",
    LLMProvider.ZHIPU: "glm-4-plus",
    LLMProvider.DEEPSEEK: "deepseek-chat",
    LLMProvider.OLLAMA: "llama3.1:8b",
    LLMProvider.OPENAI_COMPATIBLE: "gpt-4o",
}

API_BASES = {
    LLMProvider.OPENAI: "https://api.openai.com/v1",
    LLMProvider.ANTHROPIC: "https://api.anthropic.com",
    LLMProvider.ALIYUN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    LLMProvider.BAIDU: "https://aip.baidubce.com",
    LLMProvider.ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
    LLMProvider.DEEPSEEK: "https://api.deepseek.com/v1",
    LLMProvider.OLLAMA: "http://localhost:11434",
}

# 环境变量名映射
ENV_API_KEYS = {
    LLMProvider.OPENAI: "OPENAI_API_KEY",
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMProvider.ALIYUN: "DASHSCOPE_API_KEY",
    LLMProvider.BAIDU: "QIANFAN_API_KEY",
    LLMProvider.ZHIPU: "ZHIPU_API_KEY",
    LLMProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
    LLMProvider.OPENAI_COMPATIBLE: "LLM_API_KEY",
}


# ============================================================
# 抽象基类
# ============================================================

class BaseLLMClient(ABC):
    """LLM客户端抽象基类"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.http_client = httpx.Client(timeout=config.timeout)
    
    @abstractmethod
    def chat(self, 
             message: str, 
             system_prompt: Optional[str] = None,
             **kwargs) -> LLMResponse:
        """
        发送聊天请求
        
        Args:
            message: 用户消息
            system_prompt: 系统提示词（可选）
            **kwargs: 额外参数
            
        Returns:
            LLMResponse
        """
        pass
    
    @abstractmethod
    def chat_with_history(self,
                          messages: List[Dict[str, str]],
                          system_prompt: Optional[str] = None,
                          **kwargs) -> LLMResponse:
        """
        带历史记录的聊天
        
        Args:
            messages: 消息历史 [{"role": "user", "content": "..."}, ...]
            system_prompt: 系统提示词
            
        Returns:
            LLMResponse
        """
        pass
    
    def close(self):
        """关闭HTTP客户端"""
        self.http_client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


# ============================================================
# OpenAI 实现
# ============================================================

class OpenAIClient(BaseLLMClient):
    """OpenAI API客户端"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or API_BASES[LLMProvider.OPENAI]
        self.api_key = config.api_key or os.getenv(ENV_API_KEYS[LLMProvider.OPENAI])
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
    
    def _make_request(self, messages: List[Dict], **kwargs) -> LLMResponse:
        """发送请求到OpenAI API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        response = self.http_client.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.config.model),
            usage=data.get("usage"),
            raw_response=data
        )
    
    def chat(self, message: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return self._make_request(messages, **kwargs)
    
    def chat_with_history(self, messages: List[Dict[str, str]], 
                          system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        return self._make_request(full_messages, **kwargs)


# ============================================================
# Anthropic 实现
# ============================================================

class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API客户端"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or API_BASES[LLMProvider.ANTHROPIC]
        self.api_key = config.api_key or os.getenv(ENV_API_KEYS[LLMProvider.ANTHROPIC])
        
        if not self.api_key:
            raise ValueError("Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable.")
    
    def _make_request(self, messages: List[Dict], system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        """发送请求到Anthropic API"""
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        response = self.http_client.post(
            f"{self.api_base}/v1/messages",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        return LLMResponse(
            content=data["content"][0]["text"],
            model=data.get("model", self.config.model),
            usage={
                "prompt_tokens": data.get("usage", {}).get("input_tokens"),
                "completion_tokens": data.get("usage", {}).get("output_tokens")
            },
            raw_response=data
        )
    
    def chat(self, message: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        messages = [{"role": "user", "content": message}]
        return self._make_request(messages, system_prompt, **kwargs)
    
    def chat_with_history(self, messages: List[Dict[str, str]], 
                          system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        return self._make_request(messages, system_prompt, **kwargs)


# ============================================================
# 阿里云通义千问实现
# ============================================================

class AliyunClient(BaseLLMClient):
    """阿里云通义千问API客户端（兼容OpenAI格式）"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or API_BASES[LLMProvider.ALIYUN]
        self.api_key = config.api_key or os.getenv(ENV_API_KEYS[LLMProvider.ALIYUN])
        
        if not self.api_key:
            raise ValueError("Aliyun API key not found. Set DASHSCOPE_API_KEY environment variable.")
    
    def _make_request(self, messages: List[Dict], **kwargs) -> LLMResponse:
        """发送请求"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        response = self.http_client.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.config.model),
            usage=data.get("usage"),
            raw_response=data
        )
    
    def chat(self, message: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return self._make_request(messages, **kwargs)
    
    def chat_with_history(self, messages: List[Dict[str, str]], 
                          system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        return self._make_request(full_messages, **kwargs)


# ============================================================
# 智谱GLM实现
# ============================================================

class ZhipuClient(BaseLLMClient):
    """智谱GLM API客户端"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or API_BASES[LLMProvider.ZHIPU]
        self.api_key = config.api_key or os.getenv(ENV_API_KEYS[LLMProvider.ZHIPU])
        
        if not self.api_key:
            raise ValueError("Zhipu API key not found. Set ZHIPU_API_KEY environment variable.")
    
    def _make_request(self, messages: List[Dict], **kwargs) -> LLMResponse:
        """发送请求"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        response = self.http_client.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.config.model),
            usage=data.get("usage"),
            raw_response=data
        )
    
    def chat(self, message: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return self._make_request(messages, **kwargs)
    
    def chat_with_history(self, messages: List[Dict[str, str]], 
                          system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        return self._make_request(full_messages, **kwargs)


# ============================================================
# DeepSeek实现
# ============================================================

class DeepSeekClient(BaseLLMClient):
    """DeepSeek API客户端（兼容OpenAI格式）"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or API_BASES[LLMProvider.DEEPSEEK]
        self.api_key = config.api_key or os.getenv(ENV_API_KEYS[LLMProvider.DEEPSEEK])
        
        if not self.api_key:
            raise ValueError("DeepSeek API key not found. Set DEEPSEEK_API_KEY environment variable.")
    
    def _make_request(self, messages: List[Dict], **kwargs) -> LLMResponse:
        """发送请求"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        response = self.http_client.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.config.model),
            usage=data.get("usage"),
            raw_response=data
        )
    
    def chat(self, message: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return self._make_request(messages, **kwargs)
    
    def chat_with_history(self, messages: List[Dict[str, str]], 
                          system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        return self._make_request(full_messages, **kwargs)


# ============================================================
# Ollama本地模型实现
# ============================================================

class OllamaClient(BaseLLMClient):
    """Ollama本地模型客户端"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or API_BASES[LLMProvider.OLLAMA]
    
    def _make_request(self, messages: List[Dict], **kwargs) -> LLMResponse:
        """发送请求到Ollama"""
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            }
        }
        
        response = self.http_client.post(
            f"{self.api_base}/api/chat",
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        return LLMResponse(
            content=data["message"]["content"],
            model=data.get("model", self.config.model),
            usage={
                "prompt_tokens": data.get("prompt_eval_count"),
                "completion_tokens": data.get("eval_count")
            },
            raw_response=data
        )
    
    def chat(self, message: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return self._make_request(messages, **kwargs)
    
    def chat_with_history(self, messages: List[Dict[str, str]], 
                          system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        return self._make_request(full_messages, **kwargs)


# ============================================================
# OpenAI兼容接口（通用）
# ============================================================

class OpenAICompatibleClient(BaseLLMClient):
    """
    OpenAI兼容接口客户端
    
    适用于：
    - vLLM
    - LocalAI
    - OneAPI
    - FastChat
    - 各种OpenAI代理服务
    """
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or os.getenv("LLM_API_BASE", "http://localhost:8000/v1")
        self.api_key = config.api_key or os.getenv(ENV_API_KEYS[LLMProvider.OPENAI_COMPATIBLE], "sk-no-key-required")
    
    def _make_request(self, messages: List[Dict], **kwargs) -> LLMResponse:
        """发送请求"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        
        response = self.http_client.post(
            f"{self.api_base}/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.config.model),
            usage=data.get("usage"),
            raw_response=data
        )
    
    def chat(self, message: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return self._make_request(messages, **kwargs)
    
    def chat_with_history(self, messages: List[Dict[str, str]], 
                          system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        return self._make_request(full_messages, **kwargs)


# ============================================================
# 工厂函数
# ============================================================

# 客户端类映射
CLIENT_MAP = {
    LLMProvider.OPENAI: OpenAIClient,
    LLMProvider.ANTHROPIC: AnthropicClient,
    LLMProvider.ALIYUN: AliyunClient,
    LLMProvider.ZHIPU: ZhipuClient,
    LLMProvider.DEEPSEEK: DeepSeekClient,
    LLMProvider.OLLAMA: OllamaClient,
    LLMProvider.OPENAI_COMPATIBLE: OpenAICompatibleClient,
}


def create_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> BaseLLMClient:
    """
    创建LLM客户端
    
    Args:
        provider: 提供商名称（openai/anthropic/aliyun/zhipu/deepseek/ollama/openai_compatible）
        model: 模型名称（可选，使用默认模型）
        api_key: API密钥（可选，从环境变量读取）
        api_base: API地址（可选，使用默认地址）
        **kwargs: 其他配置参数
        
    Returns:
        BaseLLMClient实例
        
    Examples:
        # 使用OpenAI
        client = create_llm_client(provider="openai", model="gpt-4o")
        
        # 使用通义千问
        client = create_llm_client(provider="aliyun", model="qwen-max")
        
        # 使用本地Ollama
        client = create_llm_client(provider="ollama", model="llama3.1:70b")
        
        # 使用自定义OpenAI兼容接口
        client = create_llm_client(
            provider="openai_compatible",
            api_base="http://my-server:8000/v1",
            model="my-model"
        )
        
        # 自动检测（根据环境变量）
        client = create_llm_client()
    """
    
    # 自动检测提供商
    if provider is None:
        provider = _detect_provider()
    
    # 解析提供商枚举
    if isinstance(provider, str):
        try:
            provider_enum = LLMProvider(provider.lower())
        except ValueError:
            raise ValueError(f"Unknown provider: {provider}. Supported: {[p.value for p in LLMProvider]}")
    else:
        provider_enum = provider
    
    # 获取默认模型
    if model is None:
        model = DEFAULT_MODELS.get(provider_enum, "gpt-4o")
    
    # 创建配置
    config = LLMConfig(
        provider=provider_enum,
        model=model,
        api_key=api_key,
        api_base=api_base,
        max_tokens=kwargs.get("max_tokens", 2000),
        temperature=kwargs.get("temperature", 0.7),
        timeout=kwargs.get("timeout", 60),
        extra_params=kwargs.get("extra_params"),
    )
    
    # 创建客户端
    client_class = CLIENT_MAP.get(provider_enum)
    if client_class is None:
        raise ValueError(f"No client implementation for provider: {provider_enum}")
    
    return client_class(config)


def _detect_provider() -> str:
    """根据环境变量自动检测提供商"""
    
    # 按优先级检测
    detection_order = [
        (ENV_API_KEYS[LLMProvider.OPENAI], "openai"),
        (ENV_API_KEYS[LLMProvider.ANTHROPIC], "anthropic"),
        (ENV_API_KEYS[LLMProvider.DEEPSEEK], "deepseek"),
        (ENV_API_KEYS[LLMProvider.ALIYUN], "aliyun"),
        (ENV_API_KEYS[LLMProvider.ZHIPU], "zhipu"),
    ]
    
    for env_var, provider in detection_order:
        if os.getenv(env_var):
            return provider
    
    # 检查是否有Ollama在运行
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            return "ollama"
    except:
        pass
    
    # 检查通用LLM配置
    if os.getenv("LLM_API_BASE"):
        return "openai_compatible"
    
    raise ValueError(
        "No LLM provider detected. Please set one of the following environment variables:\n"
        "  - OPENAI_API_KEY (for OpenAI)\n"
        "  - ANTHROPIC_API_KEY (for Claude)\n"
        "  - DEEPSEEK_API_KEY (for DeepSeek)\n"
        "  - DASHSCOPE_API_KEY (for Aliyun/Qwen)\n"
        "  - ZHIPU_API_KEY (for Zhipu/GLM)\n"
        "  - Or start Ollama locally\n"
        "  - Or set LLM_API_BASE for OpenAI-compatible endpoint"
    )


def list_available_providers() -> List[str]:
    """列出所有可用的提供商"""
    return [p.value for p in LLMProvider]


def get_provider_info(provider: str) -> Dict[str, Any]:
    """获取提供商信息"""
    try:
        p = LLMProvider(provider.lower())
        return {
            "name": p.value,
            "default_model": DEFAULT_MODELS.get(p),
            "api_base": API_BASES.get(p),
            "env_var": ENV_API_KEYS.get(p),
        }
    except ValueError:
        return None


# ============================================================
# 便捷函数
# ============================================================

def quick_chat(message: str, 
               provider: Optional[str] = None,
               model: Optional[str] = None,
               system_prompt: Optional[str] = None) -> str:
    """
    快速发送聊天请求
    
    Args:
        message: 用户消息
        provider: 提供商（可选）
        model: 模型（可选）
        system_prompt: 系统提示词（可选）
        
    Returns:
        助手回复内容
        
    Example:
        response = quick_chat("什么是套利？", provider="deepseek")
    """
    with create_llm_client(provider=provider, model=model) as client:
        response = client.chat(message, system_prompt=system_prompt)
        return response.content


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("LLM提供商测试")
    print("=" * 60)
    
    print("\n可用的提供商:")
    for p in list_available_providers():
        info = get_provider_info(p)
        print(f"  - {p}: {info['default_model']} (env: {info['env_var']})")
    
    print("\n尝试自动检测提供商...")
    try:
        client = create_llm_client()
        print(f"✅ 检测到: {client.config.provider.value}, 模型: {client.config.model}")
        
        print("\n发送测试消息...")
        response = client.chat("你好，请用一句话介绍自己")
        print(f"回复: {response.content}")
        
    except ValueError as e:
        print(f"❌ {e}")
    except Exception as e:
        print(f"❌ 请求失败: {e}")
