"""
LLM 提供者抽象基礎類別
支援 API 型、本地型與瀏覽器訂閱型 LLM
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class ProviderCategory(str, Enum):
    API = "api"           # 需要 API Key（OpenAI, Anthropic, Google）
    LOCAL = "local"       # 本地執行（Ollama, LM Studio）
    BROWSER = "browser"   # 瀏覽器訂閱制（ChatGPT Plus, Claude Pro）


@dataclass
class LLMMessage:
    role: str    # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class BaseLLMProvider(ABC):
    """所有 LLM 提供者的抽象基礎類別"""

    def __init__(self, model: str, **kwargs):
        self.model = model

    @abstractmethod
    async def chat(self, messages: List[LLMMessage], **kwargs) -> str:
        """發送訊息並取得回應"""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """檢查提供者是否可用"""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供者名稱，顯示用"""
        pass

    @property
    @abstractmethod
    def category(self) -> ProviderCategory:
        pass

    @classmethod
    @abstractmethod
    def get_default_models(cls) -> List[str]:
        """取得此提供者的預設模型清單"""
        pass

    async def simple_prompt(self, prompt: str, system: Optional[str] = None) -> str:
        """便利方法：單一提示詞呼叫"""
        messages = []
        if system:
            messages.append(LLMMessage(role="system", content=system))
        messages.append(LLMMessage(role="user", content=prompt))
        return await self.chat(messages)
