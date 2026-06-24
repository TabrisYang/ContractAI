from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # 應用程式設定
    APP_NAME: str = "合約去識別化系統"
    DEBUG: bool = True

    # 檔案路徑設定
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    OUTPUT_DIR: Path = BASE_DIR / "outputs"
    MODEL_DIR: Path = BASE_DIR / "models"
    LOG_DIR: Path = BASE_DIR / "logs"
    CORPUS_DIR: Path = BASE_DIR / "corpus"
    CHROMA_DIR: Path = BASE_DIR / "chroma_db"   # RAG 向量資料庫
    CONTRACTS_SOURCE_DIR: Path = BASE_DIR.parent / "contracts"          # 使用者放原始合約
    CONTRACTS_DEIDENTIFIED_DIR: Path = BASE_DIR / "contracts_deidentified"  # 去識別化後的合約
    FEEDBACK_DIR: Path = BASE_DIR / "feedback"  # 使用者回饋（越用越進步）

    # Redis 設定
    REDIS_URL: str = "redis://localhost:6379/0"

    # 模型設定
    TFIDF_MODEL_PATH: Path = MODEL_DIR / "tfidf.pkl"
    SPACY_MODEL: str = "zh_core_web_sm"

    # 去識別化設定
    RARE_TERM_THRESHOLD: float = 0.02

    # .doc 轉檔設定（空字串 → 自動偵測 soffice / libreoffice / macOS 預設路徑）
    LIBREOFFICE_BIN: str = ""

    # RAG 設定
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    RAG_CHUNK_SIZE: int = 400    # 每段字數
    RAG_TOP_K: int = 4           # 取幾段相關內容
    RAG_RERANK_CANDIDATES: int = 10  # reranker 前先取幾段候選
    RAG_FEEDBACK_WEIGHT: float = 0.2  # 重排時回饋分數的權重 β（final = cosine + β·feedback）

    # 生成回饋重排（P5）
    GEN_ACCEPTANCE_WEIGHT: float = 0.3   # 採用分數權重 β（final = cosine + β·acceptance）
    GEN_THOMPSON_SAMPLING: bool = False  # 是否用 Thompson Sampling 解決「強者恆強」

    # FastAPI 設定
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = True


# 建立設定實例
settings = Settings()

# 確保目錄存在
for _dir in [
    settings.UPLOAD_DIR,
    settings.OUTPUT_DIR,
    settings.MODEL_DIR,
    settings.LOG_DIR,
    settings.CORPUS_DIR,
    settings.CHROMA_DIR,
    settings.CONTRACTS_DEIDENTIFIED_DIR,
    settings.FEEDBACK_DIR,
]:
    _dir.mkdir(parents=True, exist_ok=True)
