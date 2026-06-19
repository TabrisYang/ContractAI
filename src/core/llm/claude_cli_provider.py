"""
Claude 訂閱制（CLI）提供者

透過官方 Claude Code CLI（`claude` 命令）以 subprocess 方式使用 Claude Pro/Max 訂閱額度。
相較於瀏覽器自動化操作 claude.ai：
- 不接觸網頁，完全避開 Cloudflare 機器人驗證
- 可指定模型（sonnet / opus / haiku / fable）
- 用訂閱額度，免 API Key、免按量計費
- 認證由 CLI 內部處理（本機 `claude` 登入，或帶 per-user OAuth token）

前置：本機需安裝並登入 Claude Code CLI（`claude` 在 PATH 中、`claude auth status` 已登入），
或在建立時提供 oauth_token（`claude setup-token` 產生）。
"""
import asyncio
import json
import os
import shutil
import tempfile
from typing import List, Optional

from loguru import logger

from .base import BaseLLMProvider, LLMMessage, ProviderCategory

_TIMEOUT = 240  # 秒(opus 長文較慢)
_BACKOFFS = [4, 12]  # 可重試錯誤的退避秒數(最多 len+1 = 3 次嘗試)
_RATE_LIMIT_MARKERS = (
    "rate limit", "ratelimit", "overloaded", "429", "usage limit",
    "too many requests", "quota", "limit reached",
)


def _looks_retryable(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in _RATE_LIMIT_MARKERS)


class _RetryableCLIError(RuntimeError):
    """CLI 的瞬時/限流失敗,值得退避重試。"""


class ClaudeCLIProvider(BaseLLMProvider):
    """以官方 Claude Code CLI 使用 Claude 訂閱額度。"""

    def __init__(self, model: str = "sonnet", oauth_token: str = "", **kwargs):
        super().__init__(model or "sonnet")
        self.oauth_token = oauth_token or ""

    @property
    def provider_name(self) -> str:
        return "Claude 訂閱制（CLI）"

    @property
    def category(self) -> ProviderCategory:
        return ProviderCategory.BROWSER  # 標籤顯示「訂閱制」

    @classmethod
    def get_default_models(cls) -> List[str]:
        # 別名（自動用最新）+ 特定版本（皆經 CLI 實測可用,可選 4.6/4.7/4.8）
        return [
            "opus", "sonnet", "haiku",
            "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
            "claude-sonnet-4-6", "claude-sonnet-4-5",
            "claude-haiku-4-5",
        ]

    def _build_env(self) -> tuple[Optional[dict], Optional[str]]:
        """有 oauth_token 時注入環境變數並隔離 config 目錄;否則沿用本機登入。"""
        if not self.oauth_token:
            return None, None
        cfg_dir = tempfile.mkdtemp(prefix="claude_cfg_")
        env = {
            **os.environ,
            "CLAUDE_CODE_OAUTH_TOKEN": self.oauth_token,
            "CLAUDE_CONFIG_DIR": cfg_dir,
        }
        return env, cfg_dir

    async def chat(self, messages: List[LLMMessage], **kwargs) -> str:
        if not shutil.which("claude"):
            raise RuntimeError(
                "找不到 claude 命令。請先安裝並登入 Claude Code CLI："
                "`npm i -g @anthropic-ai/claude-code`，再執行 `claude`（或 `claude setup-token`）登入。"
            )

        system = "\n\n".join(m.content for m in messages if m.role == "system").strip()
        user = "\n\n".join(
            m.content for m in messages if m.role in ("user", "assistant")
        ).strip()
        if not user:
            user = system or "（空訊息）"

        # 重試/退避:吸收 CLI 偶發的限流、逾時、空輸出
        last_err = ""
        last_retryable = False
        for attempt in range(len(_BACKOFFS) + 1):
            try:
                return await self._run_once(system, user)
            except _RetryableCLIError as e:
                last_err, last_retryable = str(e), True
                if attempt < len(_BACKOFFS):
                    wait_s = _BACKOFFS[attempt]
                    logger.warning(
                        f"Claude CLI 第 {attempt + 1} 次失敗（可重試）：{last_err[:120]}；"
                        f"{wait_s}s 後重試"
                    )
                    await asyncio.sleep(wait_s)
                    continue
            # 非可重試錯誤直接往外拋（如找不到 claude、明確的非限流錯誤）

        # 重試用盡
        if last_retryable and _looks_retryable(last_err):
            raise RuntimeError(
                "Claude 訂閱額度可能已達上限或服務忙碌,請稍後再試,"
                "或改用「API 型:Anthropic Claude API」。"
            )
        raise RuntimeError(f"Claude CLI 多次嘗試仍失敗：{last_err[:300]}")

    async def _run_once(self, system: str, user: str) -> str:
        """單次 CLI 呼叫。可重試的失敗拋 _RetryableCLIError;其餘拋 RuntimeError。"""
        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--model", self.model,
            "--tools", "",  # 純 LLM 對話,不啟用任何工具
        ]
        if system:
            # 用我們的系統提示完全取代預設的 Claude Code agent 提示
            cmd += ["--system-prompt", system]

        env, cfg_dir = self._build_env()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                limit=1024 * 1024,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(user.encode("utf-8")), timeout=_TIMEOUT
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise _RetryableCLIError(f"Claude CLI 逾時（>{_TIMEOUT}s）")

            err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
            out_text = (stdout or b"").decode("utf-8", errors="replace").strip()

            if not out_text:
                # 無輸出多半是瞬時卡住/限流 → 可重試
                raise _RetryableCLIError(f"Claude CLI 無輸出。{err_text[:300]}")

            try:
                data = json.loads(out_text)
            except json.JSONDecodeError:
                return out_text  # 萬一不是 JSON,直接回傳原始文字

            if data.get("is_error"):
                detail = str(data.get("result") or data.get("api_error_status") or err_text)
                if _looks_retryable(detail):
                    raise _RetryableCLIError(f"Claude CLI 限流/忙碌：{detail[:300]}")
                raise RuntimeError(f"Claude CLI 回報錯誤：{detail[:300]}")

            result = data.get("result", "")
            if not isinstance(result, str) or not result.strip():
                raise _RetryableCLIError(f"Claude CLI 回應為空。{err_text[:300]}")

            logger.info(
                f"Claude CLI 回應成功（model={self.model}，"
                f"used={list((data.get('modelUsage') or {}).keys())}）"
            )
            return result.strip()
        finally:
            if cfg_dir:
                shutil.rmtree(cfg_dir, ignore_errors=True)

    async def is_available(self) -> bool:
        return shutil.which("claude") is not None
