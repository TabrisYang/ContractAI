"""
舊版 .doc 轉 .docx 工具

策略:
1. 優先使用 LibreOffice 無頭模式轉檔（保留排版、表格、字型）。
2. 偵測不到 LibreOffice 時,退化使用 antiword 擷取純文字後重組成 .docx（格式遺失,內容可用）。
3. 兩者皆不可用時,拋出帶安裝指引的明確錯誤。

對外只需呼叫 ensure_docx()。
"""
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from docx import Document
from loguru import logger

from ..core.config import settings

# LibreOffice 在 macOS 的常見安裝路徑
_MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"

# 轉檔逾時（秒）
_CONVERT_TIMEOUT = 120


def ensure_docx(input_path: str, job_id: str = "") -> str:
    """確保回傳一個 .docx 路徑。

    Args:
        input_path: 上傳檔案的絕對路徑。
        job_id: 任務 ID,用於隔離 LibreOffice 暫存 profile 與命名輸出。

    Returns:
        .docx 檔案路徑。若輸入本來就是 .docx 則原樣回傳。

    Raises:
        RuntimeError: 輸入為 .doc 但找不到任何可用的轉檔工具。
    """
    path = Path(input_path)

    # 非 .doc（含 .docx）直接放行,零成本
    if path.suffix.lower() != ".doc":
        return input_path

    logger.info(f"偵測到 .doc 檔,開始轉檔:{path.name}")

    # 1. 優先:LibreOffice
    soffice = _find_libreoffice()
    if soffice:
        try:
            out = _convert_with_libreoffice(soffice, path, job_id)
            logger.info(f"LibreOffice 轉檔成功:{out}")
            return str(out)
        except Exception as e:
            logger.warning(f"LibreOffice 轉檔失敗,改試 antiword:{e}")

    # 2. 退化:antiword 純文字擷取
    if shutil.which("antiword"):
        try:
            out = _convert_with_antiword(path)
            logger.info(f"antiword 純文字轉檔成功(格式遺失):{out}")
            return str(out)
        except Exception as e:
            logger.error(f"antiword 轉檔失敗:{e}")

    # 3. 皆不可用
    raise RuntimeError(
        "無法處理 .doc 檔:系統找不到 LibreOffice 或 antiword。"
        "請安裝其一 —— macOS:`brew install --cask libreoffice` 或 `brew install antiword`;"
        "Linux:`apt install libreoffice` 或 `apt install antiword`。或請改上傳 .docx。"
    )


def _find_libreoffice() -> str | None:
    """依序尋找 LibreOffice 執行檔,回傳路徑或 None。"""
    # a. 設定檔明確指定
    configured = getattr(settings, "LIBREOFFICE_BIN", "") or ""
    if configured and Path(configured).exists():
        return configured

    # b. PATH 中的 soffice / libreoffice
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found

    # c. macOS 預設安裝路徑
    if Path(_MAC_SOFFICE).exists():
        return _MAC_SOFFICE

    return None


def _convert_with_libreoffice(soffice: str, path: Path, job_id: str) -> Path:
    """用 LibreOffice 無頭模式把 .doc 轉成 .docx。

    每次轉檔使用獨立的 UserInstallation profile,避免多個 Celery worker
    同時轉檔時搶用同一個 profile 而失敗。
    """
    out_dir = path.parent
    token = job_id or uuid.uuid4().hex
    profile_dir = Path(tempfile.gettempdir()) / f"lo_profile_{token}"

    cmd = [
        soffice,
        "--headless",
        f"-env:UserInstallation=file://{profile_dir}",
        "--convert-to",
        "docx",
        "--outdir",
        str(out_dir),
        str(path),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=_CONVERT_TIMEOUT,
        )
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)

    # LibreOffice 會輸出同名的 .docx 到 out_dir
    out_path = out_dir / (path.stem + ".docx")
    if not out_path.exists():
        raise RuntimeError(f"LibreOffice 未產生預期的輸出檔:{out_path}")

    return out_path


def _convert_with_antiword(path: Path) -> Path:
    """用 antiword 擷取 .doc 純文字,逐行重組成 .docx(格式遺失)。

    必須帶 `-m UTF-8.txt`,否則 antiword 預設無法正確輸出中日韓文字(會變成 ?)。
    """
    result = subprocess.run(
        ["antiword", "-m", "UTF-8.txt", str(path)],
        check=True,
        capture_output=True,
        timeout=_CONVERT_TIMEOUT,
    )
    text = result.stdout.decode("utf-8", errors="replace")

    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)

    out_path = path.with_suffix(".docx")
    doc.save(str(out_path))
    return out_path
