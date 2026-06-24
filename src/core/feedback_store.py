"""
統一回饋儲存（越用越進步的共用基建）

三條回饋迴路（deid / rag / gen）都透過這裡進出，避免回饋邏輯散落各處。
後端採 JSONL append 作為單一真實來源（source of truth）——在本系統的資料量級
（數百~數千筆）下，全檔掃描查詢已足夠快且零額外依賴；未來量大可再加 SQLite 索引。
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from .config import settings

_VALID_LOOPS = {"deid", "rag", "gen"}


class FeedbackStore:
    """所有使用者回饋的單一進出口。"""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else settings.FEEDBACK_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, loop: str) -> Path:
        return self.base_dir / f"{loop}.jsonl"

    def record(
        self,
        loop: str,
        job_id: str,
        signal: Dict[str, Any],
        target_ref: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """寫入一筆回饋，回傳完整紀錄（含產生的 feedback_id）。"""
        if loop not in _VALID_LOOPS:
            raise ValueError(f"未知的回饋迴路：{loop}（須為 {_VALID_LOOPS}）")

        record = {
            "feedback_id": uuid.uuid4().hex,
            "job_id": job_id,
            "loop": loop,
            "target_ref": target_ref or {},
            "signal": signal,
            "created_at": datetime.now().isoformat(),
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with open(self._path(loop), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        logger.info(f"[feedback] 已記錄 loop={loop} job={job_id} signal={signal}")
        return record

    def query(
        self,
        loop: str,
        since: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """讀取某條迴路的所有回饋（可選 since=ISO 時間，只取之後的）。"""
        path = self._path(loop)
        if not path.exists():
            return []
        out: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(f"[feedback] 略過損毀的回饋行：{raw[:80]}")
                    continue
                if since and rec.get("created_at", "") < since:
                    continue
                out.append(rec)
        return out

    def stats(self) -> Dict[str, int]:
        """各迴路回饋筆數統計。"""
        return {loop: len(self.query(loop)) for loop in sorted(_VALID_LOOPS)}


# 模組級單例，供 API / deidentifier / dynamic_rules 共用
feedback_store = FeedbackStore()
