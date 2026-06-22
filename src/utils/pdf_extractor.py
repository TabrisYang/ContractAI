"""
PDF 抽取工具

策略:
1. 優先用 pdfplumber 逐頁抽取文字層（電子文字型 PDF,精確且零系統依賴）。
2. 若抽出的文字過短（疑似掃描/拍照檔,無文字層）,fallback 到 OCR
   （pdf2image 轉圖 + pytesseract chi_tra 辨識）。
3. OCR 工具皆不可用時,拋出帶安裝指引的明確錯誤。

對外提供:
- extract_pdf_text(): 回傳 (純文字, 抽取方式)。
- pdf_to_docx():     抽文字後逐行組成 .docx,接回既有 docx 處理管線。
"""
from pathlib import Path

from docx import Document
from loguru import logger

# 文字層判定門檻:總字數低於此值 → 視為掃描檔,改走 OCR
_MIN_TEXT_CHARS = 50
# 每頁平均字數低於此值 → 同樣視為掃描檔（多頁但幾乎沒文字）
_MIN_CHARS_PER_PAGE = 10
# OCR 辨識語言（繁體中文 + 英文）
_OCR_LANG = "chi_tra+eng"


def extract_pdf_text(pdf_path: str) -> tuple[str, str]:
    """抽取 PDF 文字,必要時 fallback 到 OCR。

    Args:
        pdf_path: PDF 檔案的絕對路徑。

    Returns:
        (text, method):text 為抽出的純文字;method 為 "text" 或 "ocr"。

    Raises:
        RuntimeError: 疑似掃描檔但 OCR 工具（poppler / tesseract）不可用。
    """
    path = Path(pdf_path)
    logger.info(f"開始抽取 PDF 文字:{path.name}")

    text, page_count = _extract_with_pdfplumber(path)

    stripped = text.strip()
    avg_per_page = len(stripped) / page_count if page_count else 0
    if len(stripped) >= _MIN_TEXT_CHARS and avg_per_page >= _MIN_CHARS_PER_PAGE:
        logger.info(f"PDF 文字層抽取成功（{len(stripped)} 字,{page_count} 頁）")
        return text, "text"

    # 文字過少 → 疑似掃描/拍照檔,改走 OCR
    logger.info(
        f"PDF 文字層內容過少（{len(stripped)} 字 / {page_count} 頁）,改用 OCR"
    )
    ocr_text = _extract_with_ocr(path)
    return ocr_text, "ocr"


def pdf_to_docx(pdf_path: str, job_id: str = "") -> tuple[str, str]:
    """把 PDF 抽成文字後逐行組成 .docx,回傳 (.docx 路徑, 抽取方式)。

    產生的 .docx 會接回既有的 docx 去識別化管線（偵測 → 遮罩 → 輸出）。
    注意:此轉換不保留原 PDF 版面（PDF 無可編輯段落結構）。

    Args:
        pdf_path: PDF 檔案的絕對路徑。
        job_id: 任務 ID,僅用於日誌。

    Returns:
        (docx_path, method):docx_path 為產生的 .docx 路徑（與來源 PDF 同目錄、
        同檔名）;method 為 "text" 或 "ocr"（供下游標記 OCR 結果需人工複核）。
    """
    path = Path(pdf_path)
    text, method = extract_pdf_text(pdf_path)
    logger.info(f"PDF 轉檔（method={method}）:{path.name}（job_id: {job_id}）")

    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)

    out_path = path.with_suffix(".docx")
    doc.save(str(out_path))
    logger.info(f"PDF 已轉成 .docx:{out_path}")
    return str(out_path), method


def _extract_with_pdfplumber(path: Path) -> tuple[str, int]:
    """用 pdfplumber 逐頁抽取文字層,回傳 (文字, 頁數)。"""
    import pdfplumber

    pages_text: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
    return "\n".join(pages_text), len(pages_text)


def _extract_with_ocr(path: Path) -> str:
    """用 pdf2image + pytesseract 對掃描型 PDF 做 OCR。

    延遲載入相依套件,讓未安裝 OCR 環境的使用者仍能處理文字型 PDF。
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as e:
        raise RuntimeError(
            "此 PDF 疑似為掃描/影像檔,需要 OCR 才能處理,但找不到必要套件。"
            "請安裝:`pip install pdf2image pytesseract`,"
            "並安裝系統工具 —— macOS:`brew install poppler tesseract tesseract-lang`;"
            "Linux:`apt install poppler-utils tesseract-ocr tesseract-ocr-chi-tra`。"
            "或請改上傳電子文字型 PDF / .docx。"
        ) from e

    try:
        images = convert_from_path(str(path))
    except Exception as e:
        raise RuntimeError(
            "PDF 轉圖失敗,通常是系統未安裝 poppler。"
            "請安裝 —— macOS:`brew install poppler`;Linux:`apt install poppler-utils`。"
            f"原始錯誤:{e}"
        ) from e

    pages_text: list[str] = []
    for i, image in enumerate(images, start=1):
        try:
            pages_text.append(pytesseract.image_to_string(image, lang=_OCR_LANG))
        except pytesseract.TesseractNotFoundError as e:
            raise RuntimeError(
                "找不到 tesseract 執行檔。請安裝 —— macOS:`brew install tesseract tesseract-lang`;"
                "Linux:`apt install tesseract-ocr tesseract-ocr-chi-tra`。"
            ) from e
        except pytesseract.TesseractError as e:
            raise RuntimeError(
                "OCR 辨識失敗,通常是缺少繁體中文語言包（chi_tra）。"
                "請安裝 —— macOS:`brew install tesseract tesseract-lang`;"
                "Linux:`apt install tesseract-ocr tesseract-ocr-chi-tra`。"
                f"原始錯誤:{e}"
            ) from e
        logger.info(f"OCR 完成第 {i}/{len(images)} 頁")

    ocr_text = "\n".join(pages_text)
    logger.info(f"OCR 抽取完成（{len(ocr_text.strip())} 字,{len(images)} 頁）")
    return ocr_text
