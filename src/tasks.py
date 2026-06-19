"""
Celery 非同步任務
"""
import os
from pathlib import Path
from typing import Any, Dict

from celery.exceptions import Ignore
from loguru import logger

from .celery_app import app
from .core.config import settings
from .core.deidentifier import DocumentDeidentifier
from .utils.doc_converter import ensure_docx

logger.add(
    settings.LOG_DIR / "tasks.log",
    rotation="500 MB",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)

# 單例去識別器（避免每個任務重新載入模型）
_deidentifier: DocumentDeidentifier = None


def _get_deidentifier() -> DocumentDeidentifier:
    global _deidentifier
    if _deidentifier is None:
        _deidentifier = DocumentDeidentifier()
    return _deidentifier


@app.task(
    bind=True,
    name="process_document",
)
def process_document(self, file_path: str, job_id: str, options: Dict[str, Any] = None):
    """
    去識別化文件的 Celery 任務

    Args:
        file_path: 上傳文件的絕對路徑
        job_id: 任務 UUID
        options: 去識別化選項（mask_methods, llm_config 等）
    """
    options = options or {}

    def update_progress(progress: float, message: str):
        self.update_state(
            state="PROGRESS",
            meta={"progress": progress, "message": message},
        )

    try:
        logger.info(f"開始處理文件：{file_path}（job_id: {job_id}）")
        update_progress(0, "開始處理")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在：{file_path}")

        # 若為舊版 .doc,先轉成 .docx(已是 .docx 則原樣回傳)
        update_progress(2, "轉換文件格式")
        file_path = ensure_docx(file_path, job_id)

        output_dir = settings.OUTPUT_DIR / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        result = _get_deidentifier().process(
            input_path=file_path,
            output_dir=output_dir,
            job_id=job_id,
            callback=update_progress,
            **options,
        )

        logger.info(f"文件處理完成（job_id: {job_id}）")
        return result

    except Exception as exc:
        logger.error(f"任務失敗（job_id: {job_id}）：{exc}", exc_info=True)
        self.update_state(
            state="FAILURE",
            meta={"progress": 0, "message": f"處理失敗：{exc}", "error": str(exc)},
        )
        # 確定性失敗（缺工具、檔案讀不到等）重試也不會成功;
        # 用 Ignore 保留上面自訂的 FAILURE 狀態,避免 Celery 再次序列化例外而崩潰。
        raise Ignore()
