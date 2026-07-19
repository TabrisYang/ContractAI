"""
合約去識別化系統 API
完整端點：去識別化、狀態查詢、下載、合約分析、對話助手、瀏覽器 Session 設定
"""
import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from celery.result import AsyncResult
from fastapi import FastAPI, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

from ..celery_app import app as celery_app
from ..core.config import settings
from ..core.contract_analyzer import analyze_contract
from ..core.contract_chat import get_chat_assistant
from ..core.contract_generator import get_generator
from ..core.feedback_store import feedback_store
from ..core.llm.factory import create_provider, get_all_providers_info
from ..models.schemas import (
    AnalyzeRequest,
    AnswerFeedbackRequest,
    ChatRequest,
    ChatResponse,
    ContractAnalysis,
    ContractGenerationRequest,
    ContractGenerationResponse,
    ContractRefineRequest,
    CorpusStatus,
    DeidentificationRequest,
    DeidentificationResponse,
    EntityFeedbackRequest,
    GenerationRequirementsSchema,
    JobStatus,
    LLMConfig,
    MissingEntityRequest,
    ProcessingStatus,
)
from ..tasks import process_document

app = FastAPI(
    title="合約去識別化系統 API",
    description="繁體中文合約去識別化 + LLM 分析助手",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 去識別化 ──────────────────────────────────────────────────────

@app.post(
    "/api/v1/deidentify",
    response_model=DeidentificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="上傳合約並啟動去識別化",
)
async def deidentify_contract(
    file: UploadFile,
    options: Optional[str] = Form(default=None),
):
    """上傳 .docx / .doc / .pdf 合約，非同步進行去識別化處理"""
    if not file.filename.lower().endswith((".docx", ".doc", ".pdf")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="僅支援 .docx、.doc 或 .pdf 檔案格式",
        )

    req_options: dict = {}
    if options:
        try:
            req_options = json.loads(options)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="options 參數必須為合法 JSON 字串",
            )

    job_id = str(uuid.uuid4())
    upload_dir = Path(settings.UPLOAD_DIR) / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename

    try:
        content = await file.read()
        file_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"儲存檔案失敗：{e}",
        )

    # 必須指定 task_id=job_id,否則 Celery 會自動產生隨機 task id,
    # 導致 /status/{job_id} 永遠查不到任務而卡在 PENDING(排隊等候中)。
    process_document.apply_async(
        args=[str(file_path), job_id, req_options],
        task_id=job_id,
    )
    logger.info(f"已建立去識別化任務 {job_id}，檔案：{file.filename}")

    return DeidentificationResponse(
        job_id=job_id,
        status="processing",
        message="文件已開始處理",
    )


# ── 狀態查詢 ──────────────────────────────────────────────────────

@app.get(
    "/api/v1/status/{job_id}",
    response_model=JobStatus,
    summary="查詢處理狀態",
)
async def check_status(job_id: str):
    """查詢 Celery 任務進度（0–100%）"""
    task = AsyncResult(job_id, app=celery_app)
    state = task.state
    info = task.info or {}

    if state == "PENDING":
        return JobStatus(
            job_id=job_id,
            status=ProcessingStatus.PENDING,
            progress=0,
            message="排隊等候中",
        )
    elif state == "PROGRESS":
        return JobStatus(
            job_id=job_id,
            status=ProcessingStatus.PROCESSING,
            progress=float(info.get("progress", 0)),
            message=info.get("message", "處理中"),
        )
    elif state == "SUCCESS":
        return JobStatus(
            job_id=job_id,
            status=ProcessingStatus.COMPLETED,
            progress=100,
            message="處理完成",
            result=task.result or {},
        )
    else:
        if isinstance(info, dict):
            msg = info.get("message", "處理失敗")
            err = info.get("error") or info.get("message") or "未知錯誤"
        else:
            msg, err = "處理失敗", (str(info) if info else "未知錯誤")
        return JobStatus(
            job_id=job_id,
            status=ProcessingStatus.FAILED,
            progress=0,
            message=msg,
            error=err,
        )


# ── 下載結果 ──────────────────────────────────────────────────────

@app.get(
    "/api/v1/download/{job_id}",
    summary="下載去識別化結果",
)
async def download_result(job_id: str, file_type: str = "docx"):
    """
    下載去識別化後的文件

    file_type: docx | json（實體清單）| txt
    """
    output_dir = Path(settings.OUTPUT_DIR) / job_id
    ext_map = {
        "docx": (
            f"{job_id}_deidentified.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        "json": (f"{job_id}_entities.json", "application/json"),
        "txt": (f"{job_id}_deidentified.txt", "text/plain; charset=utf-8"),
    }

    if file_type not in ext_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的 file_type：{file_type}，支援 docx / json / txt",
        )

    filename, media_type = ext_map[file_type]
    file_path = output_dir / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到結果檔案，請確認任務已完成（job_id: {job_id}）",
        )

    return FileResponse(path=file_path, filename=filename, media_type=media_type)


# ── 合約分析 ──────────────────────────────────────────────────────

@app.post(
    "/api/v1/analyze/{job_id}",
    response_model=ContractAnalysis,
    summary="LLM 合約分析",
)
async def run_analysis(job_id: str, request: AnalyzeRequest):
    """
    對已去識別化的合約進行 LLM 分析
    回傳：合約類型、條款摘要、風險標記、建議事項
    """
    output_dir = Path(settings.OUTPUT_DIR) / job_id
    if not (output_dir / f"{job_id}_deidentified.txt").exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到去識別化文字檔，請先完成去識別化（job_id: {job_id}）",
        )

    llm = _build_llm_provider(request.llm_config)
    try:
        return await analyze_contract(job_id=job_id, llm=llm, output_dir=output_dir)
    except Exception as e:
        logger.error(f"合約分析失敗 {job_id}：{e}")
        raise HTTPException(status_code=500, detail=f"LLM 分析失敗：{e}")


@app.get(
    "/api/v1/analyze/{job_id}",
    response_model=ContractAnalysis,
    summary="取得已儲存的分析結果",
)
async def get_saved_analysis(job_id: str):
    analysis_path = Path(settings.OUTPUT_DIR) / job_id / f"{job_id}_analysis.json"
    if not analysis_path.exists():
        raise HTTPException(status_code=404, detail="找不到分析結果")
    return ContractAnalysis(**json.loads(analysis_path.read_text(encoding="utf-8")))


# ── 對話助手 ──────────────────────────────────────────────────────

@app.post(
    "/api/v1/chat",
    response_model=ChatResponse,
    summary="對合約提問（RAG）",
)
async def chat_with_contract(request: ChatRequest):
    """
    使用 RAG 對已上傳合約提問
    首次提問時自動建立向量索引
    """
    output_dir = Path(settings.OUTPUT_DIR) / request.job_id
    if not (output_dir / f"{request.job_id}_deidentified.txt").exists():
        raise HTTPException(status_code=404, detail=f"找不到合約文字檔（job_id: {request.job_id}）")

    llm = _build_llm_provider(request.llm_config)
    assistant = get_chat_assistant()

    if not assistant.is_indexed(request.job_id):
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, assistant.index_contract, request.job_id, output_dir)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"向量索引建立失敗：{e}")

    try:
        answer, sources, source_ids = await assistant.chat(
            job_id=request.job_id,
            question=request.message,
            llm=llm,
            history=request.history,
        )
    except Exception as e:
        logger.error(f"對話助手錯誤：{e}")
        raise HTTPException(status_code=500, detail=f"LLM 回應失敗：{e}")

    return ChatResponse(message=answer, sources=sources, source_ids=source_ids)


@app.post("/api/v1/chat/{job_id}/index", summary="預先建立合約向量索引")
async def build_index(job_id: str):
    output_dir = Path(settings.OUTPUT_DIR) / job_id
    if not (output_dir / f"{job_id}_deidentified.txt").exists():
        raise HTTPException(status_code=404, detail="找不到合約文字檔")

    assistant = get_chat_assistant()
    loop = asyncio.get_event_loop()
    try:
        n = await loop.run_in_executor(None, assistant.index_contract, job_id, output_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"索引建立失敗：{e}")

    return {"job_id": job_id, "indexed_chunks": n, "message": "向量索引建立完成"}


# ── 去識別化回饋（越用越進步，回饋迴路 A）──────────────────────────────

@app.post("/api/v1/feedback/{job_id}/entity", summary="修正某個偵測實體（誤判 / 改類型）")
async def submit_entity_feedback(job_id: str, request: EntityFeedbackRequest):
    """使用者檢視 entities.json 後，對單一實體標記誤判或修正類型。

    is_valid=False → 該詞加入動態白名單，下一份合約不再被遮罩。
    corrected_type → 該詞加入動態字典，之後以正確類型遮罩。
    """
    entities_path = Path(settings.OUTPUT_DIR) / job_id / f"{job_id}_entities.json"
    if not entities_path.exists():
        raise HTTPException(status_code=404, detail="找不到實體清單")

    entities = json.loads(entities_path.read_text(encoding="utf-8"))
    idx = request.entity_index
    if not (0 <= idx < len(entities)):
        raise HTTPException(status_code=400, detail="無效的實體索引")

    entity = entities[idx]
    feedback = {
        "is_valid": request.is_valid,
        "corrected_type": request.corrected_type,
        "corrected_text": request.corrected_text,
        "corrected_at": datetime.now().isoformat(),
        "notes": request.notes,
    }
    # 1. 回寫 entities.json（讓前端再開啟時看得到修正狀態）
    entity["user_feedback"] = feedback
    entities_path.write_text(
        json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 2. 寫入統一回饋庫（動態規則 / 重訓會讀這裡）
    record = feedback_store.record(
        loop="deid",
        job_id=job_id,
        target_ref={"entity_index": idx, "entity_id": entity.get("id")},
        signal={
            "text": entity.get("text"),
            "entity_type": entity.get("entity_type"),
            "method": entity.get("method"),
            "is_valid": request.is_valid,
            "corrected_type": request.corrected_type,
        },
    )
    return {"status": "saved", "feedback_id": record["feedback_id"], "job_id": job_id}


@app.post("/api/v1/feedback/{job_id}/missing", summary="回報漏網實體（該遮但沒遮）")
async def submit_missing_feedback(job_id: str, request: MissingEntityRequest):
    """false negative：使用者指出某段文字應被遮罩。該詞加入動態字典，下一份即生效。"""
    record = feedback_store.record(
        loop="deid",
        job_id=job_id,
        target_ref={},
        signal={
            "text": request.text,
            "entity_type": request.entity_type,
            "missing": True,
        },
    )
    return {"status": "saved", "feedback_id": record["feedback_id"], "job_id": job_id}


@app.post("/api/v1/feedback/{job_id}/answer", summary="評價某次 RAG 問答（有用 / 沒用）")
async def submit_answer_feedback(job_id: str, request: AnswerFeedbackRequest):
    """有用 → 命中段落 pos_count +1，之後檢索更容易被選中（回饋迴路 B）。"""
    assistant = get_chat_assistant()
    loop = asyncio.get_event_loop()
    n = await loop.run_in_executor(
        None, assistant.record_answer_feedback, job_id, request.chunk_ids, request.helpful
    )
    return {"status": "saved", "job_id": job_id, "boosted_chunks": n}


@app.get("/api/v1/feedback/stats", summary="回饋統計（各迴路筆數）")
async def feedback_stats():
    return feedback_store.stats()


@app.post("/api/v1/admin/retrain", summary="以使用者回饋重訓 TF-IDF（背景執行）")
async def admin_retrain():
    """背景重訓 TF-IDF：擴充語料（含去識別化合約庫）+ 排除誤判詞。

    重訓完成後，去識別化引擎下次處理會自動載入新模型。
    """
    import subprocess
    import sys as _sys
    script = Path(settings.BASE_DIR) / "train_tfidf.py"
    if not script.exists():
        raise HTTPException(status_code=404, detail="找不到 train_tfidf.py")
    proc = subprocess.Popen(
        [_sys.executable, str(script), "--with-feedback"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(settings.BASE_DIR),
    )
    return {"message": "TF-IDF 重訓已在背景啟動（含回饋）", "pid": proc.pid}


# ── LLM 提供者資訊 ──────────────────────────────────────────────────────

@app.get("/api/v1/llm/providers", summary="取得所有支援的 LLM 提供者")
async def list_providers():
    return get_all_providers_info()


# ── 合約生成 ──────────────────────────────────────────────────────

@app.get("/api/v1/corpus/status", response_model=CorpusStatus, summary="參考合約庫狀態")
async def corpus_status():
    """查詢參考合約庫是否已建立索引"""
    gen = get_generator()
    if gen.corpus_is_ready():
        info = gen.corpus_info()
        return CorpusStatus(
            is_ready=True,
            total_contracts=info.get("total_contracts", 0),
            total_chunks=info.get("total_chunks", 0),
            message=f"已索引 {info.get('total_contracts', 0)} 份合約",
        )
    return CorpusStatus(is_ready=False, message="尚未建立索引，請將合約放入 contracts/ 並點擊「同步合約庫」")


@app.post("/api/v1/corpus/build", summary="觸發同步參考合約庫（去識別化 + 索引）")
async def build_corpus():
    """在背景執行自動管線：偵測新合約 → 去識別化 → 增量索引"""
    import subprocess, sys
    script = Path(settings.BASE_DIR) / "index_contracts.py"
    if not script.exists():
        raise HTTPException(status_code=404, detail="找不到 index_contracts.py")
    if not settings.CONTRACTS_SOURCE_DIR.exists():
        raise HTTPException(status_code=404, detail=f"找不到合約目錄：{settings.CONTRACTS_SOURCE_DIR}")
    proc = subprocess.Popen(
        [sys.executable, str(script), "--auto"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(settings.BASE_DIR),
    )
    return {"message": "合約庫同步已在背景啟動（去識別化 + 向量索引）", "pid": proc.pid}


@app.post("/api/v1/corpus/add/{job_id}", summary="把已去識別化的上傳合約加入合約庫")
async def add_job_to_corpus(job_id: str):
    """將單一已完成去識別化的任務增量加入合約庫（供日後生成參考）。"""
    output_dir = Path(settings.OUTPUT_DIR) / job_id
    txt = output_dir / f"{job_id}_deidentified.txt"
    if not txt.exists():
        raise HTTPException(status_code=404, detail="找不到去識別化文字檔，請先完成去識別化")
    text = txt.read_text(encoding="utf-8")
    if not text.strip():
        raise HTTPException(status_code=400, detail="去識別化內容為空")

    import index_contracts as idx

    source = f"upload_{job_id[:8]}"
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, lambda: idx.add_text_to_corpus(text, source))

    if not info.get("added"):
        if info.get("reason") == "duplicate":
            return {"added": False, "message": "此合約已在合約庫中", "source": source}
        if info.get("reason") == "too_short":
            raise HTTPException(status_code=400, detail="內容太短，無法建立索引段落")
        raise HTTPException(status_code=400, detail="去識別化內容為空")

    logger.info(f"合約已加入合約庫：{source}（{info['chunks']} 段，共 {info['total_contracts']} 份）")
    return {
        "added": True,
        "message": f"已加入合約庫（共 {info['total_contracts']} 份）",
        "source": source,
        "chunks": info["chunks"],
    }


@app.get("/api/v1/corpus/list", summary="列出合約庫內容（依來源彙總）")
async def corpus_list():
    """列出合約庫每個來源(source)及其段落數。"""
    from collections import Counter
    import index_contracts as idx
    import chromadb

    try:
        c = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
        col = c.get_collection(idx.COLLECTION_NAME)
        data = col.get(include=["metadatas"])
    except Exception:
        return {"items": [], "total_contracts": 0, "total_chunks": 0}

    counts = Counter((m or {}).get("source", "?") for m in (data.get("metadatas") or []))
    items = sorted(
        ({"source": s, "chunks": n} for s, n in counts.items()),
        key=lambda x: x["source"],
    )
    return {"items": items, "total_contracts": len(counts), "total_chunks": sum(counts.values())}


@app.delete("/api/v1/corpus/item/{source}", summary="從合約庫移除某一份（依來源）")
async def corpus_remove(source: str):
    """刪除指定 source 的所有段落,並重算合約庫統計。"""
    from collections import Counter
    import index_contracts as idx
    import chromadb

    try:
        c = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
        col = c.get_collection(idx.COLLECTION_NAME)
    except Exception:
        raise HTTPException(status_code=404, detail="合約庫尚未建立")

    hit = col.get(where={"source": source}, limit=1)
    if not (hit and hit.get("ids")):
        raise HTTPException(status_code=404, detail=f"找不到來源：{source}")

    col.delete(where={"source": source})

    # 依剩餘段落重算統計(比單純遞減更穩健)
    data = col.get(include=["metadatas"])
    counts = Counter((m or {}).get("source", "?") for m in (data.get("metadatas") or []))
    idx.write_summary(len(counts), col.count())
    logger.info(f"已從合約庫移除來源：{source}（剩 {len(counts)} 份）")
    return {"removed": source, "total_contracts": len(counts), "total_chunks": col.count()}


@app.post(
    "/api/v1/generate",
    response_model=ContractGenerationResponse,
    summary="合約生成（多輪對話）",
)
async def generate_contract_endpoint(request: ContractGenerationRequest):
    """
    多輪對話生成合約：
    - 若資訊不足回傳追問（stage=clarifying）
    - 資訊足夠時生成草稿（stage=draft_ready）
    """
    gen = get_generator()
    llm = _build_llm_provider(request.llm_config)

    # 萃取需求（小 token）
    history_dicts = [{"role": m.role, "content": m.content} for m in request.history]
    try:
        requirements = await gen.extract_requirements(request.message, llm, history_dicts)
    except Exception as e:
        logger.error(f"需求萃取失敗：{e}")
        raise HTTPException(status_code=500, detail=f"LLM 回應失敗：{e}")

    # 資訊不足 → 追問
    if not requirements.is_complete():
        question = "為了幫您起草合約，需要確認以下資訊：\n" + "\n".join(
            f"・{q}" for q in requirements.missing_info
        )
        req_schema = GenerationRequirementsSchema(
            contract_type=requirements.contract_type,
            party_a=requirements.party_a,
            party_b=requirements.party_b,
            purpose=requirements.purpose,
            duration=requirements.duration,
            amount=requirements.amount,
            special_clauses=requirements.special_clauses,
            missing_info=requirements.missing_info,
        )
        return ContractGenerationResponse(
            gen_id=request.gen_id or str(uuid.uuid4()),
            stage="clarifying",
            question=question,
            requirements=req_schema,
        )

    # 資訊足夠 → 生成草稿
    if not gen.corpus_is_ready():
        raise HTTPException(
            status_code=503,
            detail="參考合約庫尚未建立索引。請先在前端點擊「建立索引」或執行 python index_contracts.py",
        )

    gen_id = request.gen_id or str(uuid.uuid4())
    output_dir = settings.OUTPUT_DIR / "generated" / gen_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        contract_text = await gen.generate(requirements, llm, gen_id, output_dir)
    except Exception as e:
        logger.error(f"合約生成失敗：{e}")
        raise HTTPException(status_code=500, detail=f"合約生成失敗：{e}")

    req_schema = GenerationRequirementsSchema(
        contract_type=requirements.contract_type,
        party_a=requirements.party_a,
        party_b=requirements.party_b,
        purpose=requirements.purpose,
        duration=requirements.duration,
        amount=requirements.amount,
        special_clauses=requirements.special_clauses,
    )
    return ContractGenerationResponse(
        gen_id=gen_id,
        stage="draft_ready",
        contract_text=contract_text,
        requirements=req_schema,
    )


@app.post(
    "/api/v1/generate/{gen_id}/refine",
    response_model=ContractGenerationResponse,
    summary="修改合約草稿",
)
async def refine_contract_endpoint(gen_id: str, request: ContractRefineRequest):
    """根據使用者的修改指示更新合約草稿"""
    output_dir = settings.OUTPUT_DIR / "generated" / gen_id
    if not (output_dir / f"{gen_id}_draft.md").exists():
        raise HTTPException(status_code=404, detail=f"找不到草稿（gen_id: {gen_id}）")

    gen = get_generator()
    llm = _build_llm_provider(request.llm_config)

    try:
        refined_text = await gen.refine(gen_id, request.feedback, llm, output_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"修改失敗：{e}")

    return ContractGenerationResponse(
        gen_id=gen_id,
        stage="draft_ready",
        contract_text=refined_text,
    )


@app.get("/api/v1/generate/{gen_id}/download", summary="下載生成的合約")
async def download_generated(gen_id: str, file_type: str = "docx"):
    """下載合約草稿（docx 或 md）"""
    output_dir = settings.OUTPUT_DIR / "generated" / gen_id
    if file_type == "docx":
        path = output_dir / f"{gen_id}_draft.docx"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"合約草稿_{gen_id[:8]}.docx"
    else:
        path = output_dir / f"{gen_id}_draft.md"
        media_type = "text/markdown; charset=utf-8"
        filename = f"合約草稿_{gen_id[:8]}.md"

    if not path.exists():
        raise HTTPException(status_code=404, detail="找不到草稿檔案")

    # 下載 = 採用訊號（回饋迴路 C），每份草稿只記一次，避免重複下載灌票
    adopted_marker = output_dir / f"{gen_id}.adopted"
    if not adopted_marker.exists():
        try:
            get_generator().record_generation_feedback(gen_id, adopted=True, output_dir=output_dir)
            adopted_marker.write_text("1", encoding="utf-8")
        except Exception as e:
            logger.warning(f"記錄生成採用回饋失敗（gen_id: {gen_id}）：{e}")

    return FileResponse(path=path, filename=filename, media_type=media_type)


# ── 工具方法 ──────────────────────────────────────────────────────

def _build_llm_provider(llm_config: LLMConfig):
    provider_type = (
        llm_config.provider.value
        if hasattr(llm_config.provider, "value")
        else llm_config.provider
    )
    kwargs = {"model": llm_config.model or ""}
    if llm_config.api_key:
        kwargs["api_key"] = llm_config.api_key
    if llm_config.base_url:
        kwargs["base_url"] = llm_config.base_url
    if llm_config.headless is not None:
        kwargs["headless"] = llm_config.headless

    try:
        return create_provider(provider_type, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
