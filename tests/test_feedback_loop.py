"""
P0/P1 回饋迴路最小測試（越用越進步）

可獨立執行(無需 pytest)：
    PYTHONPATH=主程式 python 主程式/tests/test_feedback_loop.py
也相容 pytest。
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.core.feedback_store as fs_mod
import src.core.dynamic_rules as dr_mod
from src.core.feedback_store import FeedbackStore
from src.core.dynamic_rules import DynamicRules
from src.core.deidentifier import DocumentDeidentifier


def _fresh_store():
    """建立隔離的臨時回饋庫並接到 dynamic_rules。"""
    store = FeedbackStore(base_dir=Path(tempfile.mkdtemp()))
    fs_mod.feedback_store = store
    dr_mod.feedback_store = store
    return store


def test_feedback_store_record_and_query():
    store = _fresh_store()
    store.record(loop="deid", job_id="j", signal={"text": "甲", "is_valid": False})
    assert store.stats()["deid"] == 1
    assert store.query("deid")[0]["signal"]["text"] == "甲"


def test_false_positive_becomes_whitelist():
    _fresh_store().record(loop="deid", job_id="j", signal={"text": "中央", "is_valid": False})
    rules = DynamicRules()
    assert rules.is_whitelisted("中央")


def test_missing_becomes_dictionary():
    _fresh_store().record(
        loop="deid", job_id="j",
        signal={"text": "代號X", "entity_type": "PROJECT_NAME", "missing": True},
    )
    rules = DynamicRules()
    assert rules.dictionary.get("代號X") == "PROJECT_NAME"


def test_latest_feedback_wins():
    store = _fresh_store()
    store.record(loop="deid", job_id="j", signal={"text": "中央", "is_valid": False})
    store.record(loop="deid", job_id="j", signal={"text": "中央", "entity_type": "ORG", "missing": True})
    rules = DynamicRules()
    assert not rules.is_whitelisted("中央")
    assert rules.dictionary.get("中央") == "ORG"


def test_dynamic_dictionary_masking_and_whitelist_filter():
    _fresh_store()
    d = DocumentDeidentifier.__new__(DocumentDeidentifier)  # 繞過 spaCy 載入
    d.dynamic_rules = DynamicRules()
    d.dynamic_rules.dictionary = {"專案K": "PROJECT_NAME"}
    d.dynamic_rules.whitelist = {"中央"}

    ents = d._apply_dynamic_dictionary_masking("專案K由中央執行，專案K結束。")
    assert len(ents) == 2 and all(e["method"] == "feedback" for e in ents)

    merged = [
        {"text": "中央", "entity_type": "ORG", "start_pos": 0, "end_pos": 2, "method": "ner"},
        {"text": "專案K", "entity_type": "PROJECT_NAME", "start_pos": 3, "end_pos": 6, "method": "feedback"},
    ]
    kept = [e for e in merged if not d.dynamic_rules.is_whitelisted(e["text"])]
    assert len(kept) == 1 and kept[0]["text"] == "專案K"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
