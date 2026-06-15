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

    # Redis 設定
    REDIS_URL: str = "redis://localhost:6379/0"

    # 模型設定
    TFIDF_MODEL_PATH: Path = MODEL_DIR / "tfidf.pkl"
    SPACY_MODEL: str = "zh_core_web_sm"

    # 去識別化設定
    RARE_TERM_THRESHOLD: float = 0.02

    # RAG 設定
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    RAG_CHUNK_SIZE: int = 400    # 每段字數
    RAG_TOP_K: int = 4           # 取幾段相關內容

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
]:
    _dir.mkdir(parents=True, exist_ok=True)
