"""
合約去識別化系統 - Streamlit 前端
功能：去識別化 / 合約分析 / 對話助手
LLM 支援：API 型（OpenAI/Anthropic/Google）+ 本地型（Ollama/自訂）+ 訂閱制（ChatGPT Plus/Claude Pro）
"""
import json
import time
from pathlib import Path

import requests
import streamlit as st

from frontend.backend_manager import ensure_backend, get_active_port

# ── 自動啟動後端服務 ────────────────────────────────────────────
if "backend_checked" not in st.session_state:
    with st.spinner("正在檢查後端服務..."):
        _ok, _msg = ensure_backend(str(Path(__file__).parent.parent))
    if _ok:
        st.session_state["backend_checked"] = True
        st.session_state["api_port"] = get_active_port()
        if "自動啟動" in _msg:
            st.toast(_msg, icon="🚀")
    else:
        st.error(f"後端服務無法啟動：{_msg}")
        st.stop()

API_BASE = f"http://localhost:{st.session_state.get('api_port', 8000)}/api/v1"

st.set_page_config(
    page_title="合約去識別化系統",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
.risk-high { color: #d32f2f; font-weight: bold; }
.risk-medium { color: #f57c00; font-weight: bold; }
.risk-low { color: #388e3c; }
.source-box { background:#f5f5f5; border-left:3px solid #1976d2; padding:8px 12px; margin:4px 0; border-radius:4px; font-size:0.85em; }
</style>
""", unsafe_allow_html=True)


# ── 工具函式 ──────────────────────────────────────────────────────

def api_get(path: str, params: dict = None):
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.session_state.pop("backend_checked", None)
        st.error("後端連線中斷，重新整理頁面即可自動重連")
        return None
    except Exception as e:
        st.error(f"API 錯誤：{e}")
        return None


def api_post(path: str, json_data: dict = None, files=None, data=None, timeout=120):
    try:
        r = requests.post(
            f"{API_BASE}{path}",
            json=json_data,
            files=files,
            data=data,
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.session_state.pop("backend_checked", None)
        st.error("後端連線中斷，重新整理頁面即可自動重連")
        return None
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        st.error(f"API 錯誤：{detail}")
        return None
    except Exception as e:
        st.error(f"請求失敗：{e}")
        return None


def poll_status(job_id: str, progress_bar, status_text) -> dict:
    """輪詢任務狀態直到完成"""
    for _ in range(300):  # 最多等 5 分鐘
        result = api_get(f"/status/{job_id}")
        if not result:
            return {}
        s = result.get("status")
        progress = result.get("progress", 0) / 100
        msg = result.get("message", "處理中...")
        progress_bar.progress(progress)
        status_text.text(f"狀態：{msg}")
        if s == "completed":
            return result
        elif s == "failed":
            st.error(f"處理失敗：{result.get('error', '未知錯誤')}")
            return {}
        time.sleep(1.5)
    st.warning("處理逾時，請稍後重新查詢")
    return {}


def get_llm_config_from_sidebar() -> dict:
    """從 session_state 取得 LLM 設定字典"""
    return {
        "provider": st.session_state.get("llm_provider", "openai"),
        "model": st.session_state.get("llm_model", ""),
        "api_key": st.session_state.get("llm_api_key", ""),
        "base_url": st.session_state.get("llm_base_url", ""),
        "headless": True,
    }


# ── 側邊欄：LLM 設定 ──────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.title("⚙️ LLM 設定")

        # 取得提供者清單
        if "providers_info" not in st.session_state:
            info = api_get("/llm/providers")
            st.session_state["providers_info"] = info or []

        providers_info = st.session_state.get("providers_info", [])

        # 依類別分組顯示
        category_labels = {"api": "🔑 API 型", "local": "💻 本地型", "browser": "🌐 訂閱制"}
        grouped = {}
        for p in providers_info:
            cat = p.get("category", "api")
            grouped.setdefault(cat, []).append(p)

        provider_options = {p["type"]: f"{category_labels.get(p['category'],'')}: {p['name']}" for p in providers_info}

        if not provider_options:
            st.warning("無法取得提供者清單，請確認後端已啟動")
            return

        selected_type = st.selectbox(
            "選擇 LLM 提供者",
            options=list(provider_options.keys()),
            format_func=lambda t: provider_options.get(t, t),
            key="llm_provider",
        )

        selected_info = next((p for p in providers_info if p["type"] == selected_type), {})

        # 顯示說明
        if selected_info.get("description"):
            st.caption(selected_info["description"])

        # 模型選擇
        models = selected_info.get("models", [""])
        if selected_type in ("ollama", "custom"):
            st.text_input("模型名稱", value=models[0] if models else "", key="llm_model")
        else:
            st.selectbox("模型", options=models, key="llm_model")

        # API Key
        if selected_info.get("requires_api_key"):
            provider_name = selected_info.get("name", selected_type)
            st.text_input(
                f"{provider_name} API Key",
                type="password",
                key="llm_api_key",
                placeholder="sk-...",
            )
        else:
            st.session_state["llm_api_key"] = ""

        # Base URL
        if selected_info.get("requires_base_url"):
            default_url = selected_info.get("base_url_default", "")
            st.text_input("Base URL", value=default_url, key="llm_base_url")
        else:
            st.session_state["llm_base_url"] = ""

        # 訂閱制 Session 設定
        if selected_info.get("requires_setup"):
            st.divider()
            st.subheader("🔐 登入設定")

            # 查詢目前 session 狀態
            browser_status = api_get("/browser/status") or {}
            is_configured = browser_status.get(selected_type, {}).get("configured", False)

            if is_configured:
                st.success("✅ 已設定登入 session")
            else:
                st.warning("⚠️ 尚未登入，需要先設定")

            if st.button("🌐 開啟瀏覽器登入", use_container_width=True):
                with st.spinner("開啟瀏覽器中，請在瀏覽器視窗完成登入..."):
                    result = api_post(
                        "/browser/setup",
                        json_data={"provider": selected_type},
                        timeout=200,
                    )
                if result and result.get("is_configured"):
                    st.success("登入成功！")
                    st.rerun()

        st.divider()
        st.caption("💡 LLM 設定僅在分析、對話與合約生成功能中使用，去識別化本身不需要 LLM")

        # ── 參考合約庫狀態 ──
        st.divider()
        st.subheader("📚 參考合約庫")
        corpus = api_get("/corpus/status") or {}
        if corpus.get("is_ready"):
            st.success(f"✅ 已索引 {corpus.get('total_contracts', 0)} 份合約")
            st.caption(f"共 {corpus.get('total_chunks', 0)} 個段落")
        else:
            st.warning("⚠️ 尚未建立索引")
            st.caption("合約生成功能需要先建立索引")
            if st.button("🔨 建立索引", use_container_width=True):
                with st.spinner("建立索引中（約 3–5 分鐘）..."):
                    result = api_post("/corpus/build", timeout=10)
                if result:
                    st.info("索引建立已在背景執行，完成後請重新整理頁面")


# ── 去識別化回饋 UI（讓系統越用越準）────────────────────────────

ENTITY_TYPES = [
    "PERSON", "ORG", "PHONE", "EMAIL", "ADDRESS", "ID", "DATE", "MONEY",
    "BANK", "BANK_ACCOUNT", "PROJECT_NAME", "BRAND", "FAX", "TAX_ID", "LLM_PII",
]


def render_entity_feedback(job_id: str):
    """讓使用者標記去識別化的誤判 / 漏抓，回饋即時影響下一份合約。"""
    with st.expander("✏️ 修正去識別化結果（標記誤判 / 補漏，讓系統越用越準）"):
        try:
            raw = requests.get(f"{API_BASE}/download/{job_id}?file_type=json", timeout=30)
            entities = raw.json() if raw.ok else []
        except Exception as e:
            st.error(f"讀取實體清單失敗：{e}")
            return
        if not isinstance(entities, list):
            entities = []

        st.caption(
            f"共偵測 {len(entities)} 個實體。標記「誤判」→ 該詞下一份不再遮罩；"
            "「補漏」→ 該詞下一份一定遮罩（即時生效，不必重訓）。"
        )

        # 回報漏抓（false negative）
        with st.form(key=f"missing_{job_id}", clear_on_submit=True):
            st.write("**➕ 回報漏抓（該遮但沒遮的詞）**")
            mc1, mc2 = st.columns([3, 2])
            miss_text = mc1.text_input("文字", key=f"miss_txt_{job_id}")
            miss_type = mc2.selectbox("類型", ENTITY_TYPES, key=f"miss_type_{job_id}")
            if st.form_submit_button("送出補遮罩") and miss_text.strip():
                r = api_post(
                    f"/feedback/{job_id}/missing",
                    json_data={"text": miss_text.strip(), "entity_type": miss_type},
                )
                if r:
                    st.success("已記錄，下一份含此詞會被遮罩")

        st.divider()
        st.write("**偵測到的實體（標記誤判 / 改類型）**")
        show = entities[:50]
        for i, e in enumerate(show):
            fb = e.get("user_feedback") or {}
            tag = ""
            if fb.get("is_valid") is False:
                tag = "　🚫已標誤判"
            elif fb.get("corrected_type"):
                tag = f"　✎已改為 {fb['corrected_type']}"

            c1, c2, c3, c4, c5 = st.columns([3, 2, 1.2, 1.8, 1])
            c1.write(f"`{e.get('text', '')}`{tag}")
            c2.caption(f"{e.get('entity_type')} · {e.get('method')}")
            if c3.button("✗誤判", key=f"fp_{job_id}_{i}"):
                if api_post(f"/feedback/{job_id}/entity",
                            json_data={"entity_index": i, "is_valid": False}):
                    st.toast("已標記誤判")
                    st.rerun()
            new_type = c4.selectbox(
                "改類型", ["(改類型)"] + ENTITY_TYPES,
                key=f"ct_{job_id}_{i}", label_visibility="collapsed",
            )
            if c5.button("套用", key=f"apply_{job_id}_{i}") and new_type != "(改類型)":
                if api_post(f"/feedback/{job_id}/entity",
                            json_data={"entity_index": i, "corrected_type": new_type}):
                    st.toast(f"已改為 {new_type}")
                    st.rerun()

        if len(entities) > 50:
            st.caption(f"（僅顯示前 50 個，共 {len(entities)} 個）")


# ── Tab 1：去識別化 ──────────────────────────────────────────────

def render_deidentify_tab():
    st.header("📄 合約去識別化")
    st.write("上傳 .docx / .doc / .pdf 合約，系統將自動遮罩個人資訊（姓名、電話、身分證字號、地址等）")
    st.caption("PDF 支援電子文字型；掃描/拍照檔會自動以 OCR 辨識（需安裝 OCR 系統依賴，且不保留原版面）")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded = st.file_uploader("選擇合約檔案（.docx / .doc / .pdf）", type=["docx", "doc", "pdf"])

    with col2:
        st.subheader("偵測方法")
        use_regex = st.checkbox("Regex（正則）", value=True)
        use_ner = st.checkbox("NER（命名實體）", value=True)
        use_tfidf = st.checkbox("TF-IDF（罕見詞）", value=True)
        use_llm = st.checkbox("LLM 輔助偵測（需設定 LLM）", value=False)

    if uploaded and st.button("🚀 開始去識別化", type="primary", use_container_width=True):
        methods = []
        if use_regex:
            methods.append("regex")
        if use_ner:
            methods.append("ner")
        if use_tfidf:
            methods.append("tfidf")
        if use_llm:
            methods.append("llm")

        options: dict = {"mask_methods": methods}
        if use_llm:
            llm_cfg = get_llm_config_from_sidebar()
            if not llm_cfg.get("provider"):
                st.error("啟用 LLM 輔助請先在側邊欄設定 LLM 提供者")
                return
            options["llm_config"] = llm_cfg

        with st.spinner("上傳並建立任務..."):
            resp = requests.post(
                f"{API_BASE}/deidentify",
                files={"file": (uploaded.name, uploaded.getvalue())},
                data={"options": json.dumps(options)},
                timeout=30,
            )
            if resp.status_code not in (200, 202):
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                st.error(f"上傳失敗：{detail}")
                return
            job_data = resp.json()

        job_id = job_data["job_id"]
        st.info(f"任務 ID：`{job_id}`")

        # 儲存到 session 供其他 tab 使用
        st.session_state["last_job_id"] = job_id

        progress_bar = st.progress(0)
        status_text = st.empty()

        result = poll_status(job_id, progress_bar, status_text)

        if result.get("status") == "completed":
            st.success("去識別化完成！")
            analysis = result.get("result", {}).get("analysis", {})

            if analysis.get("extract_method") == "ocr":
                st.warning(
                    "⚠️ 此 PDF 為掃描/影像檔，內容以 OCR 辨識取得。"
                    "OCR 可能有錯字或漏字，導致部分個資未被遮罩，**建議下載後人工複核**。"
                )

            if analysis:
                m1, m2, m3 = st.columns(3)
                m1.metric("偵測實體數", analysis.get("total_entities", 0))
                m2.metric("文件字數", f"{analysis.get('total_characters', 0):,}")
                m3.metric("處理時間", f"{analysis.get('processing_time', 0):.1f}s")

                by_type = analysis.get("entities_by_type", {})
                if by_type:
                    st.subheader("實體類型分佈")
                    st.bar_chart(by_type)

            st.subheader("下載結果")
            dl_col1, dl_col2, dl_col3 = st.columns(3)
            with dl_col1:
                docx_bytes = requests.get(f"{API_BASE}/download/{job_id}?file_type=docx", timeout=30).content
                st.download_button("⬇️ 去識別化 .docx", docx_bytes, f"{job_id}_deidentified.docx")
            with dl_col2:
                json_bytes = requests.get(f"{API_BASE}/download/{job_id}?file_type=json", timeout=30).content
                st.download_button("⬇️ 實體清單 .json", json_bytes, f"{job_id}_entities.json")
            with dl_col3:
                txt_bytes = requests.get(f"{API_BASE}/download/{job_id}?file_type=txt", timeout=30).content
                st.download_button("⬇️ 純文字 .txt", txt_bytes, f"{job_id}_deidentified.txt")

            st.caption("💡 可於下方將此合約加入合約庫，作為日後合約生成的參考範本")

    # ── 加入合約庫(以 session_state 控制,避免 Streamlit 重跑後消失)──
    last = st.session_state.get("last_job_id")
    if last:
        st.divider()
        st.caption(f"最近完成的任務：`{last}`")
        render_entity_feedback(last)
        if st.button("📚 加入合約庫（供日後生成參考）", use_container_width=True):
            with st.spinner("正在加入合約庫（首次需載入向量模型，請稍候）..."):
                try:
                    r = requests.post(f"{API_BASE}/corpus/add/{last}", timeout=180)
                except requests.RequestException as e:
                    st.error(f"加入失敗：{e}")
                    r = None
            if r is not None:
                if r.ok:
                    d = r.json()
                    (st.success if d.get("added") else st.info)(d.get("message", "完成"))
                else:
                    try:
                        detail = r.json().get("detail", r.text)
                    except Exception:
                        detail = r.text
                    st.error(f"加入失敗：{detail}")

    # ── 合約庫管理(查看 / 移除)──
    with st.expander("📚 合約庫管理（查看 / 移除）"):
        lst = api_get("/corpus/list") or {}
        items = lst.get("items", [])
        st.caption(
            f"目前合約庫:{lst.get('total_contracts', 0)} 份 / "
            f"{lst.get('total_chunks', 0)} 段　(upload_* 為你上傳加入的;contract_* 為原始合約庫)"
        )
        if not items:
            st.write("（合約庫為空）")
        for it in items:
            c1, c2 = st.columns([5, 1])
            c1.write(f"`{it['source']}`　{it['chunks']} 段")
            if c2.button("移除", key=f"rm_{it['source']}"):
                try:
                    rr = requests.delete(f"{API_BASE}/corpus/item/{it['source']}", timeout=60)
                    if rr.ok:
                        st.success(f"已移除 {it['source']}")
                        st.rerun()
                    else:
                        st.error(f"移除失敗：{rr.json().get('detail', rr.text)}")
                except requests.RequestException as e:
                    st.error(f"移除失敗：{e}")


# ── Tab 2：合約分析 ──────────────────────────────────────────────

def render_analysis_tab():
    st.header("🔍 LLM 合約分析")
    st.write("對去識別化後的合約進行智慧分析，識別合約類型、關鍵條款、風險事項")

    job_id = st.text_input(
        "任務 ID（去識別化完成後取得）",
        value=st.session_state.get("last_job_id", ""),
        placeholder="貼上去識別化的 job_id",
    )

    llm_cfg = get_llm_config_from_sidebar()
    provider_display = llm_cfg.get("provider", "未選擇")

    st.info(f"將使用：**{provider_display}** / **{llm_cfg.get('model', '（未選擇模型）')}** 進行分析")

    if st.button("🤖 開始分析", type="primary", disabled=not job_id, use_container_width=True):
        with st.spinner("LLM 分析中，請稍候..."):
            result = api_post(
                f"/analyze/{job_id}",
                json_data={"llm_config": llm_cfg},
                timeout=120,
            )

        if not result:
            return

        st.success("分析完成！")
        _render_analysis_result(result)


def _render_analysis_result(data: dict):
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("合約類型", data.get("contract_type", "-"))
        st.caption(f"分析來源：{data.get('analyzed_by', '-')}")

    with col2:
        st.subheader("合約摘要")
        st.write(data.get("summary", ""))

    risk_flags = data.get("risk_flags", [])
    if risk_flags:
        st.subheader("⚠️ 風險條款")
        for flag in risk_flags:
            st.warning(flag)

    key_clauses = data.get("key_clauses", [])
    if key_clauses:
        st.subheader("📋 關鍵條款")
        for clause in key_clauses:
            risk = clause.get("risk_level", "low")
            risk_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk, "⚪")
            with st.expander(f"{risk_color} {clause.get('title', '未命名條款')}"):
                st.write(clause.get("content", ""))
                if clause.get("notes"):
                    st.caption(f"💡 {clause['notes']}")

    recommendations = data.get("recommendations", [])
    if recommendations:
        st.subheader("💡 建議事項")
        for rec in recommendations:
            st.info(rec)


# ── Tab 3：對話助手 ──────────────────────────────────────────────

def render_chat_tab():
    st.header("💬 合約對話助手")
    st.write("針對已上傳的合約提問，系統從合約中搜尋相關段落並回答")

    job_id = st.text_input(
        "任務 ID",
        value=st.session_state.get("last_job_id", ""),
        placeholder="貼上去識別化的 job_id",
        key="chat_job_id",
    )

    if not job_id:
        st.info("請先在「去識別化」頁面上傳合約，取得任務 ID 後貼上")
        return

    llm_cfg = get_llm_config_from_sidebar()

    # 初始化對話歷史
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "chat_sources" not in st.session_state:
        st.session_state["chat_sources"] = []

    # 顯示歷史對話
    for msg in st.session_state["chat_history"]:
        role = msg.get("role", "user")
        with st.chat_message(role):
            st.write(msg.get("content", ""))

    # 輸入框
    user_input = st.chat_input("輸入您對合約的問題...")

    if user_input:
        # 顯示使用者訊息
        with st.chat_message("user"):
            st.write(user_input)
        st.session_state["chat_history"].append({"role": "user", "content": user_input})

        # 呼叫 API
        with st.chat_message("assistant"):
            with st.spinner("搜尋合約相關段落並生成回答..."):
                result = api_post(
                    "/chat",
                    json_data={
                        "job_id": job_id,
                        "message": user_input,
                        "llm_config": llm_cfg,
                        "history": st.session_state["chat_history"][:-1],
                    },
                    timeout=120,
                )

            if result:
                answer = result.get("message", "無法取得回答")
                sources = result.get("sources", [])
                source_ids = result.get("source_ids", [])

                st.write(answer)
                st.session_state["chat_history"].append({"role": "assistant", "content": answer})
                # 記錄最近一則回答的命中段落，供下方評分使用（回饋迴路 B）
                st.session_state["last_chat"] = {
                    "job_id": job_id, "ids": source_ids, "rated": False,
                }

                if sources:
                    with st.expander(f"📌 參考段落（{len(sources)} 段）"):
                        for i, src in enumerate(sources, 1):
                            st.markdown(
                                f'<div class="source-box"><b>段落 {i}：</b>{src[:300]}{"..." if len(src) > 300 else ""}</div>',
                                unsafe_allow_html=True,
                            )

    # ── 回答評分（讓系統學習更好的檢索；持久顯示，承受 Streamlit 重跑）──
    lc = st.session_state.get("last_chat")
    if lc and lc.get("ids") and not lc.get("rated"):
        st.caption("上一則回答有幫助嗎？（你的評分會讓常被採用的段落更容易被檢索到）")
        rc1, rc2, _ = st.columns([1, 1, 4])
        if rc1.button("👍 有用", key="ans_up"):
            if api_post(f"/feedback/{lc['job_id']}/answer",
                        json_data={"chunk_ids": lc["ids"], "helpful": True}):
                lc["rated"] = True
                st.toast("感謝回饋！已為這些段落加分")
        if rc2.button("👎 沒用", key="ans_down"):
            if api_post(f"/feedback/{lc['job_id']}/answer",
                        json_data={"chunk_ids": lc["ids"], "helpful": False}):
                lc["rated"] = True
                st.toast("已記錄")

    # 清除對話按鈕
    if st.session_state["chat_history"]:
        if st.button("🗑️ 清除對話記錄"):
            st.session_state["chat_history"] = []
            st.rerun()

    # 重建索引按鈕
    with st.expander("進階選項"):
        if st.button("🔄 重新建立向量索引"):
            with st.spinner("建立索引中..."):
                result = api_post(f"/chat/{job_id}/index", timeout=120)
            if result:
                st.success(f"索引建立完成，共 {result.get('indexed_chunks', 0)} 個段落")


# ── Tab 4：合約生成 ──────────────────────────────────────────────

def render_generate_tab():
    st.header("📝 AI 合約生成")
    st.write("用自然語言描述您的需求，系統從 147 份真實合約中提取最佳條款，由 LLM 客製化組合生成合約草稿。")

    # 初始化 session state
    if "gen_history" not in st.session_state:
        st.session_state["gen_history"] = []
    if "gen_id" not in st.session_state:
        st.session_state["gen_id"] = None
    if "gen_draft" not in st.session_state:
        st.session_state["gen_draft"] = None

    llm_cfg = get_llm_config_from_sidebar()

    # 雙欄佈局
    left, right = st.columns([1, 1])

    with left:
        st.subheader("💬 需求對話")

        # 顯示對話歷史
        for msg in st.session_state["gen_history"]:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # 新增對話輸入
        placeholder = (
            "例如：我需要一份軟體開發委託合約，甲方是我的公司（台灣科技有限公司），乙方是外包工程師（王大明），開發一套電商系統，費用 50 萬，期間 6 個月"
            if not st.session_state["gen_history"]
            else "補充資訊或說明修改需求..."
        )
        user_input = st.chat_input(placeholder)

        if user_input:
            # 顯示使用者訊息
            with st.chat_message("user"):
                st.write(user_input)
            st.session_state["gen_history"].append({"role": "user", "content": user_input})

            # 判斷是修改草稿還是繼續生成
            is_refine = (
                st.session_state["gen_draft"] is not None
                and st.session_state["gen_id"] is not None
                and any(kw in user_input for kw in ["修改", "更改", "調整", "改成", "刪除", "加入", "補充"])
            )

            with st.chat_message("assistant"):
                if is_refine:
                    with st.spinner("修改合約中..."):
                        result = api_post(
                            f"/generate/{st.session_state['gen_id']}/refine",
                            json_data={
                                "feedback": user_input,
                                "llm_config": llm_cfg,
                            },
                            timeout=180,
                        )
                else:
                    with st.spinner("分析需求並生成合約（首次生成約需 1–2 分鐘）..."):
                        result = api_post(
                            "/generate",
                            json_data={
                                "message": user_input,
                                "llm_config": llm_cfg,
                                "history": st.session_state["gen_history"][:-1],
                                "gen_id": st.session_state.get("gen_id"),
                            },
                            timeout=300,
                        )

                if not result:
                    st.error("生成失敗，請確認 LLM 設定正確")
                    st.session_state["gen_history"].pop()
                else:
                    stage = result.get("stage")
                    st.session_state["gen_id"] = result.get("gen_id")

                    if stage == "clarifying":
                        # 資訊不足，顯示追問
                        question = result.get("question", "請提供更多資訊")
                        st.write(question)
                        st.session_state["gen_history"].append(
                            {"role": "assistant", "content": question}
                        )

                    elif stage == "draft_ready":
                        msg = "✅ 合約草稿已生成！請在右側預覽，如需修改請直接說明。"
                        st.write(msg)
                        st.session_state["gen_history"].append(
                            {"role": "assistant", "content": msg}
                        )
                        st.session_state["gen_draft"] = result.get("contract_text", "")
                        st.rerun()

        # 清除按鈕
        if st.session_state["gen_history"]:
            if st.button("🗑️ 重新開始", use_container_width=True):
                st.session_state["gen_history"] = []
                st.session_state["gen_id"] = None
                st.session_state["gen_draft"] = None
                st.rerun()

    with right:
        st.subheader("📄 合約草稿預覽")

        if st.session_state["gen_draft"]:
            # 顯示合約內容（markdown 渲染）
            with st.container(height=500):
                st.markdown(st.session_state["gen_draft"])

            st.divider()

            # 下載按鈕
            gen_id = st.session_state["gen_id"]
            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                try:
                    docx_resp = requests.get(
                        f"{API_BASE}/generate/{gen_id}/download?file_type=docx",
                        timeout=30,
                    )
                    if docx_resp.status_code == 200:
                        st.download_button(
                            "⬇️ 下載 .docx",
                            docx_resp.content,
                            file_name=f"合約草稿_{gen_id[:8]}.docx",
                            use_container_width=True,
                            type="primary",
                        )
                except Exception:
                    st.button("⬇️ 下載 .docx（稍後可用）", disabled=True, use_container_width=True)

            with dl_col2:
                st.download_button(
                    "⬇️ 下載 .md",
                    st.session_state["gen_draft"].encode("utf-8"),
                    file_name=f"合約草稿_{gen_id[:8]}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

            # 修改提示
            st.info("💡 如需修改，直接在左側對話框輸入修改指示，例如：「將違約金改為合約金額的 20%」")

        else:
            st.info("合約草稿將在此預覽")
            st.markdown("""
**使用流程：**
1. 在左側描述您的合約需求
2. 系統可能追問補充資訊
3. 資訊充足後自動生成草稿
4. 可繼續對話修改條款
5. 滿意後下載 .docx

**生成方式：**
- 從 147 份真實合約中搜尋最相關條款（不消耗 LLM token）
- LLM 只負責客製化填入您的資訊（token 消耗極低）
            """)


# ── 主程式 ──────────────────────────────────────────────────────

def main():
    st.title("📄 合約 AI 助手")
    st.caption("繁體中文合約 PII 去識別化 · LLM 智慧分析 · 對話式助手 · AI 合約生成")

    render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs(["🔒 去識別化", "🔍 合約分析", "💬 對話助手", "📝 合約生成"])

    with tab1:
        render_deidentify_tab()

    with tab2:
        render_analysis_tab()

    with tab3:
        render_chat_tab()

    with tab4:
        render_generate_tab()


if __name__ == "__main__":
    main()
