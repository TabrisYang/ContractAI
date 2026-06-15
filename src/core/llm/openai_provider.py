"""OpenAI API 提供者（GPT-4o, GPT-4o-mini 等）"""
from typing import List
import httpx
from loguru import logger

from .base import BaseLLMProvider, LLMMessage, ProviderCategory

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
]


class OpenAIProvider(BaseLLMProvider):
    BASE_URL = "https://api.openai.com/v1"

    def __init__(self, model: str = "gpt-4o-mini", api_key: str = "", **kwargs):
        super().__init__(model)
        self.api_key = api_key

    @property
    def provider_name(self) -> str:
        return "OpenAI"

    @property
    def category(self) -> ProviderCategory:
        return ProviderCategory.API

    @classmethod
    def get_default_models(cls) -> List[str]:
        return OPENAI_MODELS

    async def chat(self, messages: List[LLMMessage], **kwargs) -> str:
        if not self.api_key:
            raise ValueError("OpenAI API Key 未設定")

        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
