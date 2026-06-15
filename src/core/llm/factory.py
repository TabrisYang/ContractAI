"""
LLM Provider 工廠函式
根據使用者設定建立對應的 LLM 提供者實例
"""
from typing import Dict, Any, List

from .base import BaseLLMProvider, ProviderCategory
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .google_provider import GoogleProvider
from .ollama_provider import OllamaProvider, CustomOpenAIProvider
from .browser_provider import BrowserChatGPTProvider, BrowserClaudeProvider

# 提供者代碼 → 類別的對應
PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "ollama": OllamaProvider,
    "custom": CustomOpenAIProvider,
    "browser_chatgpt": BrowserChatGPTProvider,
    "browser_claude": BrowserClaudeProvider,
}


def create_provider(provider_type: str, **kwargs) -> BaseLLMProvider:
    """
    根據提供者類型與參數建立 LLM provider 實例

    Args:
        provider_type: 提供者代碼（openai / anthropic / google / ollama / custom / browser_chatgpt / browser_claude）
        **kwargs: 傳遞給提供者建構子的參數（model, api_key, base_url 等）

    Returns:
        BaseLLMProvider 實例
    """
    if provider_type not in PROVIDER_MAP:
        raise ValueError(
            f"不支援的 LLM 提供者：{provider_type}。"
            f"支援的提供者：{list(PROVIDER_MAP.keys())}"
        )
    cls = PROVIDER_MAP[provider_type]
    return cls(**kwargs)


def get_all_providers_info() -> List[Dict[str, Any]]:
    """取得所有提供者的說明資訊（用於前端 UI）"""
    providers = [
        {
            "type": "openai",
            "name": "OpenAI API",
            "category": ProviderCategory.API,
            "category_label": "API 型",
            "description": "GPT-4o、GPT-4o-mini 等，需要 API Key",
            "requires_api_key": True,
            "requires_base_url": False,
            "models": OpenAIProvider.get_default_models(),
        },
        {
            "type": "anthropic",
            "name": "Anthropic Claude API",
            "category": ProviderCategory.API,
            "category_label": "API 型",
            "description": "Claude Sonnet/Haiku/Opus，需要 API Key",
            "requires_api_key": True,
            "requires_base_url": False,
            "models": AnthropicProvider.get_default_models(),
        },
        {
            "type": "google",
            "name": "Google Gemini API",
            "category": ProviderCategory.API,
            "category_label": "API 型",
            "description": "Gemini 2.0 Flash、1.5 Pro 等，需要 API Key",
            "requires_api_key": True,
            "requires_base_url": False,
            "models": GoogleProvider.get_default_models(),
        },
        {
            "type": "ollama",
            "name": "Ollama（本地）",
            "category": ProviderCategory.LOCAL,
            "category_label": "本地型",
            "description": "本機執行的開源模型，免費、無需 API Key，需先安裝 Ollama",
            "requires_api_key": False,
            "requires_base_url": True,
            "base_url_default": "http://localhost:11434",
            "models": OllamaProvider.get_default_models(),
        },
        {
            "type": "custom",
            "name": "自訂端點（LM Studio / LocalAI）",
            "category": ProviderCategory.LOCAL,
            "category_label": "本地型",
            "description": "任何 OpenAI 相容 API 端點，支援 LM Studio、vLLM 等",
            "requires_api_key": False,
            "requires_base_url": True,
            "base_url_default": "http://localhost:1234/v1",
            "models": ["local-model"],
        },
        {
            "type": "browser_chatgpt",
            "name": "ChatGPT Plus（訂閱制）",
            "category": ProviderCategory.BROWSER,
            "category_label": "訂閱制",
            "description": "使用您的 ChatGPT Plus 訂閱，無需另付 API 費用，需首次手動登入",
            "requires_api_key": False,
            "requires_base_url": False,
            "requires_setup": True,
            "models": BrowserChatGPTProvider.get_default_models(),
        },
        {
            "type": "browser_claude",
            "name": "Claude Pro（訂閱制）",
            "category": ProviderCategory.BROWSER,
            "category_label": "訂閱制",
            "description": "使用您的 Claude Pro 訂閱，無需另付 API 費用，需首次手動登入",
            "requires_api_key": False,
            "requires_base_url": False,
            "requires_setup": True,
            "models": BrowserClaudeProvider.get_default_models(),
        },
    ]
    return providers
