"""
瀏覽器訂閱制 LLM 提供者
透過 Playwright 自動化操作 ChatGPT Plus / Claude Pro 網頁介面
適合：有 ChatGPT Plus 或 Claude Pro 訂閱、不想另外付 API 費用的使用者

注意：
- 首次使用需要手動登入（執行 setup_session）
- 登入 session 儲存於本機，後續自動使用
- 回應速度比 API 慢（需等待網頁渲染）
- 請確認符合各服務的使用條款
"""
import asyncio
import json
import os
from pathlib import Path
from typing import List, Optional
from loguru import logger

from .base import BaseLLMProvider, LLMMessage, ProviderCategory

SESSION_DIR = Path.home() / ".contract_ai" / "browser_sessions"


class BrowserChatGPTProvider(BaseLLMProvider):
    """
    ChatGPT Plus 瀏覽器自動化提供者
    使用已登入的 ChatGPT 網頁介面（需訂閱 ChatGPT Plus）
    """

    LOGIN_URL = "https://chatgpt.com/auth/login"
    CHAT_URL = "https://chatgpt.com/"
    SESSION_FILE = SESSION_DIR / "chatgpt_session.json"

    def __init__(self, model: str = "auto", headless: bool = True, **kwargs):
        super().__init__(model)
        self.headless = headless
        self._lock = asyncio.Lock()

    @property
    def provider_name(self) -> str:
        return "ChatGPT Plus（訂閱制）"

    @property
    def category(self) -> ProviderCategory:
        return ProviderCategory.BROWSER

    @classmethod
    def get_default_models(cls) -> List[str]:
        return ["auto（依訂閱方案）"]

    async def setup_session(self):
        """
        開啟瀏覽器讓使用者手動登入 ChatGPT，登入後自動儲存 session
        首次使用必須執行此方法
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("請先安裝 playwright：pip install playwright && playwright install chromium")

        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("開啟瀏覽器，請登入 ChatGPT...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(self.LOGIN_URL)

            # 等待使用者登入（偵測到對話介面出現）
            logger.info("等待登入完成（請在瀏覽器中登入）...")
            await page.wait_for_url("https://chatgpt.com/", timeout=180000)
            await page.wait_for_selector('div[id="prompt-textarea"], textarea[id="prompt-textarea"]', timeout=30000)

            # 儲存 session
            storage = await context.storage_state()
            with open(self.SESSION_FILE, "w") as f:
                json.dump(storage, f)
            self.SESSION_FILE.chmod(0o600)  # 只有擁有者可讀寫

            logger.info(f"ChatGPT session 已儲存至 {self.SESSION_FILE}")
            await browser.close()

    async def chat(self, messages: List[LLMMessage], **kwargs) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("請先安裝 playwright：pip install playwright && playwright install chromium")

        if not self.SESSION_FILE.exists():
            raise RuntimeError(
                "尚未設定 ChatGPT session。請先執行 setup_session() 進行登入設定。"
            )

        # 合併所有訊息為單一提示
        prompt = self._build_prompt(messages)

        async with self._lock:
            async with async_playwright() as p:
                storage_state = json.loads(self.SESSION_FILE.read_text())
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(storage_state=storage_state)
                page = await context.new_page()

                try:
                    # 建立新對話
                    await page.goto(self.CHAT_URL, timeout=30000)
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)

                    # 找到輸入框
                    input_selector = 'div[id="prompt-textarea"]'
                    await page.wait_for_selector(input_selector, timeout=20000)

                    # 輸入訊息
                    await page.click(input_selector)
                    await page.fill(input_selector, prompt)

                    # 送出
                    send_btn = 'button[data-testid="send-button"]'
                    await page.wait_for_selector(f"{send_btn}:not([disabled])", timeout=10000)
                    await page.click(send_btn)

                    # 等待回應開始
                    await page.wait_for_selector('[data-message-author-role="assistant"]', timeout=30000)

                    # 等待回應結束（送出按鈕重新啟用）
                    await page.wait_for_selector(f"{send_btn}:not([disabled])", timeout=120000)
                    await asyncio.sleep(0.5)

                    # 取得最後一則助手訊息
                    messages_el = await page.query_selector_all('[data-message-author-role="assistant"]')
                    if not messages_el:
                        raise RuntimeError("無法取得 ChatGPT 回應")
                    response_text = await messages_el[-1].inner_text()

                    # 更新 session（維持登入狀態）
                    storage = await context.storage_state()
                    with open(self.SESSION_FILE, "w") as f:
                        json.dump(storage, f)
                    self.SESSION_FILE.chmod(0o600)

                    return response_text.strip()

                finally:
                    await browser.close()

    def _build_prompt(self, messages: List[LLMMessage]) -> str:
        """將多則訊息合併為單一提示詞"""
        parts = []
        for m in messages:
            if m.role == "system":
                parts.append(f"[系統指示]\n{m.content}")
            elif m.role == "user":
                parts.append(m.content)
        return "\n\n".join(parts)

    async def is_available(self) -> bool:
        try:
            import playwright  # noqa
            return self.SESSION_FILE.exists()
        except ImportError:
            return False


class BrowserClaudeProvider(BaseLLMProvider):
    """
    Claude Pro 瀏覽器自動化提供者
    使用已登入的 Claude.ai 網頁介面（需訂閱 Claude Pro）
    """

    LOGIN_URL = "https://claude.ai/login"
    CHAT_URL = "https://claude.ai/new"
    SESSION_FILE = SESSION_DIR / "claude_session.json"

    def __init__(self, model: str = "auto", headless: bool = True, **kwargs):
        super().__init__(model)
        self.headless = headless
        self._lock = asyncio.Lock()

    @property
    def provider_name(self) -> str:
        return "Claude Pro（訂閱制）"

    @property
    def category(self) -> ProviderCategory:
        return ProviderCategory.BROWSER

    @classmethod
    def get_default_models(cls) -> List[str]:
        return ["auto（依訂閱方案）"]

    async def setup_session(self):
        """開啟瀏覽器讓使用者手動登入 Claude.ai"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("請先安裝 playwright：pip install playwright && playwright install chromium")

        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("開啟瀏覽器，請登入 Claude.ai...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(self.LOGIN_URL)

            logger.info("等待登入完成（請在瀏覽器中登入 Claude.ai）...")
            await page.wait_for_url("https://claude.ai/**", timeout=180000)
            await asyncio.sleep(3)

            storage = await context.storage_state()
            with open(self.SESSION_FILE, "w") as f:
                json.dump(storage, f)
            self.SESSION_FILE.chmod(0o600)  # 只有擁有者可讀寫

            logger.info(f"Claude session 已儲存至 {self.SESSION_FILE}")
            await browser.close()

    async def chat(self, messages: List[LLMMessage], **kwargs) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("請先安裝 playwright：pip install playwright && playwright install chromium")

        if not self.SESSION_FILE.exists():
            raise RuntimeError(
                "尚未設定 Claude session。請先執行 setup_session() 進行登入設定。"
            )

        prompt = self._build_prompt(messages)

        async with self._lock:
            async with async_playwright() as p:
                storage_state = json.loads(self.SESSION_FILE.read_text())
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(storage_state=storage_state)
                page = await context.new_page()

                try:
                    await page.goto(self.CHAT_URL, timeout=30000)
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)

                    # 找到輸入框（Claude 使用 contenteditable）
                    input_selector = 'div[contenteditable="true"][data-placeholder]'
                    await page.wait_for_selector(input_selector, timeout=20000)
                    await page.click(input_selector)

                    # 輸入文字（分批輸入避免觸發 paste 偵測）
                    await page.fill(input_selector, prompt)

                    # 按 Enter 送出
                    await page.keyboard.press("Enter")

                    # 等待回應生成
                    await asyncio.sleep(2)
                    # 等待回應完成（送出按鈕重新啟用）
                    await page.wait_for_function(
                        "() => !document.querySelector('button[aria-label=\"Stop\"]')",
                        timeout=120000,
                    )
                    await asyncio.sleep(0.5)

                    # 取得回應
                    response_els = await page.query_selector_all('[data-is-streaming="false"] .font-claude-message, .font-claude-message')
                    if response_els:
                        response_text = await response_els[-1].inner_text()
                    else:
                        # fallback selector
                        all_msgs = await page.query_selector_all('[data-testid="chat-message-content"]')
                        if not all_msgs:
                            raise RuntimeError("無法取得 Claude 回應")
                        response_text = await all_msgs[-1].inner_text()

                    storage = await context.storage_state()
                    with open(self.SESSION_FILE, "w") as f:
                        json.dump(storage, f)
                    self.SESSION_FILE.chmod(0o600)

                    return response_text.strip()

                finally:
                    await browser.close()

    def _build_prompt(self, messages: List[LLMMessage]) -> str:
        parts = []
        for m in messages:
            if m.role == "system":
                parts.append(f"[系統指示]\n{m.content}")
            elif m.role == "user":
                parts.append(m.content)
        return "\n\n".join(parts)

    async def is_available(self) -> bool:
        try:
            import playwright  # noqa
            return self.SESSION_FILE.exists()
        except ImportError:
            return False
