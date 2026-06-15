"""Anthropic Claude API 提供者"""
from typing import List
import httpx
from loguru import logger

from .base import BaseLLMProvider, LLMMessage, ProviderCategory

ANTHROPIC_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
]


class AnthropicProvider(BaseLLMProvider):
    BASE_URL = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    def __init__(self, model: str = "claude-haiku-4-5-20251001", api_key: str = "", **kwargs):
        super().__init__(model)
        self.api_key = api_key

    @property
    def provider_name(self) -> str:
        return "Anthropic Claude"

    @property
    def category(self) -> ProviderCategory:
        return ProviderCategory.API

    @classmethod
    def get_default_models(cls) -> List[str]:
        return ANTHROPIC_MODELS

    async def chat(self, messages: List[LLMMessage], **kwargs) -> str:
        if not self.api_key:
            raise ValueError("Anthropic API Key 未設定")

        # 分離 system message
        system_content = ""
        user_messages = []
        for m in messages:
            if m.role == "system":
                system_content = m.content
            else:
                user_messages.append(m.to_dict())

        payload = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": user_messages,
        }
        if system_content:
            payload["system"] = system_content

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.BASE_URL}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.API_VERSION,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    async def is_available(self) -> bool:
        return bool(self.api_key)
