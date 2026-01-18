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
import logging
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum

# 获取logger
logger = logging.getLogger(__name__)


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
    MODELSCOPE = "modelscope"  # ModelScope - 阿里云模型托管平台


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
    reasoning_content: Optional[str] = None  # 🆕 思考模型的推理内容


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
    LLMProvider.MODELSCOPE: "Qwen/Qwen2.5-72B-Instruct",
}

API_BASES = {
    LLMProvider.OPENAI: "https://api.openai.com/v1",
    LLMProvider.ANTHROPIC: "https://api.anthropic.com",
    LLMProvider.ALIYUN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    LLMProvider.BAIDU: "https://aip.baidubce.com",
    LLMProvider.ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
    LLMProvider.DEEPSEEK: "https://api.deepseek.com/v1",
    LLMProvider.OLLAMA: "http://localhost:11434",
    LLMProvider.MODELSCOPE: "https://api-inference.modelscope.cn/v1",
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
    LLMProvider.MODELSCOPE: "MODELSCOPE_API_KEY",
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
        """发送请求（含详细错误记录）"""
        url = f"{self.api_base}/chat/completions"
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

        # 提取prompt摘要用于错误日志
        prompt_summary = ""
        if messages:
            last_msg = messages[-1].get("content", "")
            prompt_summary = last_msg[:100] + "..." if len(last_msg) > 100 else last_msg

        try:
            response = self.http_client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # 提取content - 增强对思考模型的支持
            message = data["choices"][0]["message"]
            content = message.get("content", "")
            reasoning_content = message.get("reasoning_content", "")

            # 🆕 智能合并策略
            if not content and reasoning_content:
                # 只有reasoning，使用它
                content = reasoning_content
            elif content and reasoning_content:
                # 两者都有，进行智能判断
                content_stripped = content.strip()

                # 如果content是纯JSON格式，不合并reasoning（保持纯净）
                if content_stripped.startswith('{') and content_stripped.endswith('}'):
                    pass  # 保持content不变
                # 如果reasoning不在content中，合并它们
                elif reasoning_content not in content:
                    content = f"{reasoning_content}\n\n{content}"

            return LLMResponse(
                content=content,
                model=data.get("model", self.config.model),
                usage=data.get("usage"),
                raw_response=data,
                reasoning_content=reasoning_content or None  # 🆕 保留原始reasoning_content
            )

        except httpx.TimeoutException as e:
            error_msg = (
                f"LLM请求超时\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  请求URL: {url}\n"
                f"  请求模型: {self.config.model}\n"
                f"  超时设置: {self.config.timeout}秒\n"
                f"  Prompt摘要: {prompt_summary}"
            )
            logger.error(error_msg)
            raise

        except httpx.HTTPStatusError as e:
            error_msg = (
                f"LLM请求HTTP错误\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  状态码: {e.response.status_code}\n"
                f"  请求URL: {url}\n"
                f"  请求模型: {self.config.model}\n"
                f"  响应内容: {e.response.text[:500] if e.response.text else 'N/A'}\n"
                f"  Prompt摘要: {prompt_summary}"
            )
            logger.error(error_msg)
            raise

        except httpx.RequestError as e:
            error_msg = (
                f"LLM请求网络错误\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  错误信息: {str(e)}\n"
                f"  请求URL: {url}\n"
                f"  请求模型: {self.config.model}\n"
                f"  Prompt摘要: {prompt_summary}"
            )
            logger.error(error_msg)
            raise

        except Exception as e:
            error_msg = (
                f"LLM请求未知错误\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  错误信息: {str(e)}\n"
                f"  请求URL: {url}\n"
                f"  请求模型: {self.config.model}\n"
                f"  Prompt摘要: {prompt_summary}\n"
                f"  堆栈跟踪:\n{traceback.format_exc()}"
            )
            logger.error(error_msg)
            raise

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
# ModelScope客户端
# ============================================================

class ModelScopeClient(BaseLLMClient):
    """
    ModelScope API客户端
    阿里云模型托管平台，支持多种开源模型

    文档: https://api-inference.modelscope.cn/docs
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or API_BASES[LLMProvider.MODELSCOPE]
        self.api_key = config.api_key or os.getenv(ENV_API_KEYS[LLMProvider.MODELSCOPE])

        if not self.api_key:
            raise ValueError(
                "ModelScope API key not found. "
                "Please set MODELSCOPE_API_KEY environment variable or pass api_key parameter."
            )

    def _make_request(self, messages: List[Dict], **kwargs) -> LLMResponse:
        """发送请求到ModelScope API"""
        url = f"{self.api_base}/chat/completions"
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

        # 提取prompt摘要用于错误日志
        prompt_summary = ""
        if messages:
            last_msg = messages[-1].get("content", "")
            prompt_summary = last_msg[:100] + "..." if len(last_msg) > 100 else last_msg

        try:
            response = self.http_client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # 提取content - 增强对思考模型的支持
            message = data["choices"][0]["message"]
            content = message.get("content", "")
            reasoning_content = message.get("reasoning_content", "")

            # 🆕 智能合并策略
            if not content and reasoning_content:
                # 只有reasoning，使用它
                content = reasoning_content
            elif content and reasoning_content:
                # 两者都有，进行智能判断
                content_stripped = content.strip()

                # 如果content是纯JSON格式，不合并reasoning（保持纯净）
                if content_stripped.startswith('{') and content_stripped.endswith('}'):
                    pass  # 保持content不变
                # 如果reasoning不在content中，合并它们
                elif reasoning_content not in content:
                    content = f"{reasoning_content}\n\n{content}"

            return LLMResponse(
                content=content,
                model=data.get("model", self.config.model),
                usage=data.get("usage"),
                raw_response=data,
                reasoning_content=reasoning_content or None  # 🆕 保留原始reasoning_content
            )

        except httpx.TimeoutException as e:
            error_msg = (
                f"ModelScope请求超时\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  请求URL: {url}\n"
                f"  请求模型: {self.config.model}\n"
                f"  超时设置: {self.config.timeout}秒\n"
                f"  Prompt摘要: {prompt_summary}"
            )
            logger.error(error_msg)
            raise

        except httpx.HTTPStatusError as e:
            error_msg = (
                f"ModelScope请求HTTP错误\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  状态码: {e.response.status_code}\n"
                f"  请求URL: {url}\n"
                f"  请求模型: {self.config.model}\n"
                f"  响应内容: {e.response.text[:500] if e.response.text else 'N/A'}\n"
                f"  Prompt摘要: {prompt_summary}"
            )
            logger.error(error_msg)
            raise

        except httpx.RequestError as e:
            error_msg = (
                f"ModelScope请求网络错误\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  错误信息: {str(e)}\n"
                f"  请求URL: {url}\n"
                f"  请求模型: {self.config.model}\n"
                f"  Prompt摘要: {prompt_summary}"
            )
            logger.error(error_msg)
            raise

        except Exception as e:
            error_msg = (
                f"ModelScope请求未知错误\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  错误信息: {str(e)}\n"
                f"  请求URL: {url}\n"
                f"  请求模型: {self.config.model}\n"
                f"  Prompt摘要: {prompt_summary}\n"
                f"  堆栈跟踪:\n{traceback.format_exc()}"
            )
            logger.error(error_msg)
            raise

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
    LLMProvider.MODELSCOPE: ModelScopeClient,
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
        (ENV_API_KEYS[LLMProvider.MODELSCOPE], "modelscope"),
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
        "  - MODELSCOPE_API_KEY (for ModelScope)\n"
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
# 思考模型识别
# ============================================================

def is_reasoning_model(model_name: str) -> bool:
    """
    判断模型是否为思考模型（推理模型）

    思考模型通常具有更强的推理能力，适合复杂任务如Tag分类。
    快速模型则更适合简单任务如策略扫描。

    Args:
        model_name: 模型名称

    Returns:
        是否为思考模型

    识别规则：
    1. 包含 "reasoner" (不区分大小写) - DeepSeek推理模型
    2. 包含 "-R1" 或 ":R1" (不区分大小写) - DeepSeek R1系列
    3. 以 "o1" 开头 (不区分大小写) - OpenAI o1推理系列

    Examples:
        >>> is_reasoning_model("deepseek-reasoner")
        True
        >>> is_reasoning_model("deepseek-ai/DeepSeek-R1")
        True
        >>> is_reasoning_model("deepseek-r1:7b")
        True
        >>> is_reasoning_model("o1-preview")
        True
        >>> is_reasoning_model("deepseek-chat")
        False
        >>> is_reasoning_model("gpt-4o")
        False
    """
    if not model_name:
        return False

    model_lower = model_name.lower()

    # 思考模型识别模式
    reasoning_patterns = [
        'reasoner',    # DeepSeek Reasoner
        '-r1',         # DeepSeek R1 (URL格式)
        ':r1',         # DeepSeek R1 (Ollama格式)
        'o1',          # OpenAI o1系列
    ]

    return any(pattern in model_lower for pattern in reasoning_patterns)


def get_model_display_name(model: str, show_marker: bool = True) -> str:
    """
    获取模型的显示名称（含思考模型标记）

    Args:
        model: 模型名称
        show_marker: 是否显示类型标记

    Returns:
        带标记的显示名称，如 "deepseek-chat [FAST]" 或 "DeepSeek-R1 [THINK]"

    Examples:
        >>> get_model_display_name("deepseek-chat")
        'deepseek-chat [FAST]'
        >>> get_model_display_name("deepseek-reasoner")
        'deepseek-reasoner [THINK]'
        >>> get_model_display_name("DeepSeek-V3", show_marker=False)
        'DeepSeek-V3'
    """
    if not show_marker:
        return model

    if is_reasoning_model(model):
        return f"{model} [THINK]"
    return f"{model} [FAST]"


def get_model_icon(model: str) -> str:
    """
    获取模型的图标

    Args:
        model: 模型名称

    Returns:
        图标字符串：思考模型返回 "🧪"，快速模型返回 "⚡"
    """
    return "🧪" if is_reasoning_model(model) else "⚡"


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

