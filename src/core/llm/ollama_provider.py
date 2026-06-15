"""
Ollama 本地 LLM 提供者
適合：已安裝 Ollama 的使用者，免費，支援 Llama3, Mistral, Gemma 等
"""
from typing import List
import httpx
from loguru import logger

from .base import BaseLLMProvider, LLMMessage, ProviderCategory

DEFAULT_OLLAMA_MODELS = [
    "llama3.2",
    "llama3.1",
    "mistral",
    "gemma3",
    "qwen2.5",
    "deepseek-r1",
]


class OllamaProvider(BaseLLMProvider):
    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        **kwargs,
    ):
        super().__init__(model)
        self.base_url = base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "Ollama（本地）"

    @property
    def category(self) -> ProviderCategory:
        return ProviderCategory.LOCAL

    @classmethod
    def get_default_models(cls) -> List[str]:
        return DEFAULT_OLLAMA_MODELS

    async def get_installed_models(self) -> List[str]:
        """取得 Ollama 已安裝的模型清單"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return DEFAULT_OLLAMA_MODELS

    async def chat(self, messages: List[LLMMessage], **kwargs) -> str:
        # 使用 OpenAI 相容端點（Ollama 支援）
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.3),
                "num_predict": kwargs.get("max_tokens", 4096),
            },
        }

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


class CustomOpenAIProvider(BaseLLMProvider):
    """
    自訂 OpenAI 相容端點
    適合：LM Studio, LocalAI, vLLM, 企業私有部署等
    """

    def __init__(
        self,
        model: str = "local-model",
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "not-needed",
        **kwargs,
    ):
        super().__init__(model)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    @property
    def provider_name(self) -> str:
        return "自訂端點（OpenAI 相容）"

    @property
    def category(self) -> ProviderCategory:
        return ProviderCategory.LOCAL

    @classmethod
    def get_default_models(cls) -> List[str]:
        return ["local-model"]

    async def chat(self, messages: List[LLMMessage], **kwargs) -> str:
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
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
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
