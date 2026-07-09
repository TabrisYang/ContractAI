from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


# ── 去識別化相關 ────────────────────────────────────────────────

class MaskingMethod(str, Enum):
    REGEX = "regex"
    NER = "ner"
    TFIDF = "tfidf"
    LLM = "llm"


class LLMProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    CUSTOM = "custom"
    CLAUDE_CLI = "claude_cli"


class LLMConfig(BaseModel):
    """LLM 提供者設定，由前端傳入，後端按需建立 provider"""
    provider: LLMProviderType
    model: str = Field(default="")
    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    headless: bool = Field(default=True)


class DeidentificationRequest(BaseModel):
    """去識別化請求參數"""
    mask_methods: List[MaskingMethod] = Field(
        default_factory=lambda: [MaskingMethod.REGEX, MaskingMethod.NER, MaskingMethod.TFIDF],
        description="要使用的遮罩方法",
    )
    mask_format: str = Field(default="{{{}}}", description="遮罩格式，預設 {TYPE}")
    output_format: str = Field(default="docx", description="輸出格式：docx 或 txt")
    custom_patterns: Optional[Dict[str, str]] = Field(default=None, description="自訂正則模式")
    preserve_layout: bool = Field(default=True, description="是否保留原始排版")
    llm_config: Optional[LLMConfig] = Field(default=None, description="LLM 輔助去識別設定（選用）")


class DeidentificationResponse(BaseModel):
    job_id: str
    status: str
    message: str


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(BaseModel):
    job_id: str
    status: ProcessingStatus
    progress: float = 0.0
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class EntityFeedback(BaseModel):
    """使用者對某個偵測實體的修正記錄"""
    is_valid: Optional[bool] = None          # True=偵測正確，False=誤判
    corrected_type: Optional[str] = None     # 修正後的實體類型
    corrected_text: Optional[str] = None     # 修正後的文字
    corrected_at: Optional[str] = None       # ISO 時間
    notes: Optional[str] = None              # 使用者備註


class MaskedEntity(BaseModel):
    id: Optional[str] = None                 # 穩定 id：start:end:method
    text: str
    entity_type: str
    start_pos: int
    end_pos: int
    confidence: Optional[float] = None
    method: str
    user_feedback: Optional[EntityFeedback] = None


class DocumentAnalysis(BaseModel):
    total_characters: int
    total_entities: int
    entities_by_type: Dict[str, int]
    processing_time: float
    masking_stats: Dict[str, int] = {}


# ── 合約分析相關 ────────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContractClause(BaseModel):
    title: str
    content: str
    risk_level: RiskLevel = RiskLevel.LOW
    notes: Optional[str] = None


class ContractAnalysis(BaseModel):
    job_id: str
    contract_type: str
    summary: str
    key_clauses: List[ContractClause] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    analyzed_by: str


class AnalyzeRequest(BaseModel):
    llm_config: LLMConfig


# ── 對話助手相關 ────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    job_id: str
    message: str
    llm_config: LLMConfig
    history: List[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    message: str
    sources: List[str] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)  # 命中段落 id（供答案回饋使用）


class AnswerFeedbackRequest(BaseModel):
    """對某次 RAG 問答評價（有用 / 沒用）"""
    chunk_ids: List[str] = Field(default_factory=list, description="ChatResponse.source_ids")
    helpful: bool = Field(..., description="True=有用 → 命中段落提權")


# ── 合約生成相關 ────────────────────────────────────────────────

class GenerationRequirementsSchema(BaseModel):
    contract_type: str = ""
    party_a: str = ""
    party_b: str = ""
    purpose: str = ""
    duration: Optional[str] = None
    amount: Optional[str] = None
    special_clauses: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)


class ContractGenerationRequest(BaseModel):
    message: str = Field(..., description="使用者本輪輸入")
    llm_config: LLMConfig
    history: List[ChatMessage] = Field(default_factory=list)
    gen_id: Optional[str] = Field(default=None, description="已存在的草稿 ID（修改時用）")


class ContractGenerationResponse(BaseModel):
    gen_id: str
    stage: str  # "clarifying" | "draft_ready"
    question: Optional[str] = None        # stage=clarifying 時的追問
    contract_text: Optional[str] = None   # stage=draft_ready 時的合約草稿
    requirements: Optional[GenerationRequirementsSchema] = None


class ContractRefineRequest(BaseModel):
    feedback: str = Field(..., description="修改指示")
    llm_config: LLMConfig


class CorpusStatus(BaseModel):
    is_ready: bool
    total_contracts: int = 0
    total_chunks: int = 0
    message: str


# ── 回饋（越用越進步）─────────────────────────────────────────────

class FeedbackRecord(BaseModel):
    """三條回饋迴路共用的統一回饋紀錄"""
    feedback_id: str
    job_id: str
    loop: str                              # "deid" | "rag" | "gen"
    target_ref: Dict[str, Any] = Field(default_factory=dict)  # entity_index / chunk_id / clause_id
    signal: Dict[str, Any] = Field(default_factory=dict)      # is_valid / corrected_type / rating ...
    created_at: str


class EntityFeedbackRequest(BaseModel):
    """對某個已偵測實體提交修正（誤判 / 改類型）"""
    entity_index: int = Field(..., description="entities.json 陣列索引")
    is_valid: Optional[bool] = Field(default=None, description="False=誤判（加入白名單）")
    corrected_type: Optional[str] = Field(default=None, description="修正後的實體類型")
    corrected_text: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)


class MissingEntityRequest(BaseModel):
    """回報「該遮但沒遮」的漏網實體（false negative）"""
    text: str = Field(..., description="應被遮罩的文字")
    entity_type: str = Field(default="LLM_PII", description="正確的實體類型")
    notes: Optional[str] = Field(default=None)
