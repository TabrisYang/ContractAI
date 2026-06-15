"""Google Gemini API 提供者"""
from typing import List
import httpx
from loguru import logger

from .base import BaseLLMProvider, LLMMessage, ProviderCategory

GOOGLE_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.0-pro",
]


class GoogleProvider(BaseLLMProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, model: str = "gemini-2.0-flash", api_key: str = "", **kwargs):
        super().__init__(model)
        self.api_key = api_key

    @property
    def provider_name(self) -> str:
        return "Google Gemini"

    @property
    def category(self) -> ProviderCategory:
        return ProviderCategory.API

    @classmethod
    def get_default_models(cls) -> List[str]:
        return GOOGLE_MODELS

    async def chat(self, messages: List[LLMMessage], **kwargs) -> str:
        if not self.api_key:
            raise ValueError("Google API Key 未設定")

        # 轉換格式：合併 system 到第一個 user message
        contents = []
        system_prefix = ""
        for m in messages:
            if m.role == "system":
                system_prefix = m.content + "\n\n"
            elif m.role == "user":
                text = (system_prefix + m.content) if system_prefix else m.content
                contents.append({"role": "user", "parts": [{"text": text}]})
                system_prefix = ""
            elif m.role == "assistant":
                contents.append({"role": "model", "parts": [{"text": m.content}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.3),
                "maxOutputTokens": kwargs.get("max_tokens", 4096),
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.BASE_URL}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def is_available(self) -> bool:
        return bool(self.api_key)
