"""
由使用者回饋自動產生的動態規則（去識別化「越用越準」最快見效的一環）

從 FeedbackStore(loop="deid") 推導出兩份清單，套到去識別化流程：
  • 動態白名單：被標為「誤判」的詞 → 之後永不遮罩
  • 動態字典：被回報「該遮但沒遮」或被修正類型的詞 → 之後一定遮罩（指定類型）

一筆修正，下一份合約即生效——不必等 TF-IDF 重訓。
"""
from __future__ import annotations

from typing import Dict, Set, Tuple

from loguru import logger

from .feedback_store import feedback_store


def _derive(records) -> Tuple[Set[str], Dict[str, str]]:
    """從 deid 回饋紀錄推導 (whitelist, dictionary)。

    後到的紀錄覆蓋先到的：同一個詞若先被標誤判、後又被回報該遮，以最後一筆為準。
    """
    whitelist: Set[str] = set()
    dictionary: Dict[str, str] = {}

    for rec in records:  # 已按寫入順序（時間遞增）
        sig = rec.get("signal", {})
        text = (sig.get("text") or "").strip()
        if not text:
            continue

        if sig.get("is_valid") is False:
            # 誤判 → 白名單，並撤銷先前的字典登錄
            whitelist.add(text)
            dictionary.pop(text, None)
        elif sig.get("missing") or sig.get("corrected_type"):
            # 漏網 or 類型修正 → 字典，並撤銷先前的白名單登錄
            etype = sig.get("corrected_type") or sig.get("entity_type") or "LLM_PII"
            dictionary[text] = etype
            whitelist.discard(text)

    return whitelist, dictionary


class DynamicRules:
    """去識別化引擎啟動 / 每次處理前載入的動態規則。"""

    def __init__(self):
        self.whitelist: Set[str] = set()
        self.dictionary: Dict[str, str] = {}
        self.reload()

    def reload(self) -> "DynamicRules":
        """重新從回饋庫推導規則。便宜操作，可在每次處理前呼叫。"""
        try:
            records = feedback_store.query("deid")
            self.whitelist, self.dictionary = _derive(records)
            logger.info(
                f"[dynamic_rules] 已載入：白名單 {len(self.whitelist)} 筆、"
                f"字典 {len(self.dictionary)} 筆"
            )
        except Exception as e:  # 回饋庫異常不可拖垮去識別化
            logger.warning(f"[dynamic_rules] 載入失敗，使用空規則：{e}")
            self.whitelist, self.dictionary = set(), {}
        return self

    def is_whitelisted(self, text: str) -> bool:
        return text.strip() in self.whitelist
