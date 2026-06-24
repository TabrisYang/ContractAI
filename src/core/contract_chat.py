"""
合約對話助手（RAG）
使用向量搜尋 + LLM 讓使用者對已上傳合約提問
"""
from pathlib import Path
from typing import List, Optional, Tuple
from loguru import logger

from .llm.base import BaseLLMProvider, LLMMessage
from ..models.schemas import ChatMessage

CHAT_SYSTEM_PROMPT = """你是一位繁體中文法律合約助手。
你的任務是根據提供的合約相關段落，精確回答使用者的問題。

規則：
1. 只根據提供的合約段落回答，不可憑空捏造
2. 若相關段落中找不到答案，請明確說明「此合約未明確規定此事項」
3. 回答要精簡清晰，指出條款位置（若可識別）
4. 使用繁體中文回答
"""


class ContractChatAssistant:
    """RAG 合約對話助手"""

    def __init__(self):
        self._embedder = None
        self._chroma_client = None

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            from .config import settings
            logger.info(f"載入嵌入模型 {settings.EMBEDDING_MODEL}...")
            self._embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
        return self._embedder

    def _get_chroma(self):
        if self._chroma_client is None:
            import chromadb
            from .config import settings
            self._chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
        return self._chroma_client

    @staticmethod
    def _chunk_hash(text: str) -> str:
        import hashlib
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def _chunk_text(self, text: str, chunk_size: int = 400, overlap: int = 50) -> List[str]:
        """將合約文字切成重疊段落"""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        chunks = []
        current = []
        current_len = 0

        for line in lines:
            current.append(line)
            current_len += len(line)
            if current_len >= chunk_size:
                chunks.append("\n".join(current))
                # 保留末尾 overlap 字的段落作為下一段的開頭
                overlap_text = "\n".join(current)[-overlap:]
                current = [overlap_text] if overlap_text else []
                current_len = len(overlap_text)

        if current:
            chunks.append("\n".join(current))

        return [c for c in chunks if c.strip()]

    def index_contract(
        self, job_id: str, output_dir: Optional[Path] = None, force: bool = False
    ) -> int:
        """
        為合約建立向量索引（同步方法，增量）

        以每段內容雜湊比對：內容未變則沿用現有索引、跳過重新嵌入，
        避免每次都暴力刪除重建（回饋迴路 B）。

        Args:
            job_id: 任務 ID
            output_dir: 輸出目錄
            force: 強制重建（忽略雜湊比對）

        Returns:
            已索引的段落數量
        """
        from .config import settings

        if output_dir is None:
            output_dir = settings.OUTPUT_DIR / job_id

        txt_path = output_dir / f"{job_id}_deidentified.txt"
        if not txt_path.exists():
            raise FileNotFoundError(f"找不到合約文字檔：{txt_path}")

        contract_text = txt_path.read_text(encoding="utf-8")
        if not contract_text.strip():
            raise ValueError("合約文字內容為空")

        chunks = self._chunk_text(contract_text, chunk_size=settings.RAG_CHUNK_SIZE)
        if not chunks:
            raise ValueError("合約切分後無任何段落")

        hashes = [self._chunk_hash(c) for c in chunks]
        chroma = self._get_chroma()
        collection_name = f"contract_{job_id}"

        existing = None
        try:
            existing = chroma.get_collection(collection_name)
        except Exception:
            existing = None

        # 內容未變 → 跳過重建
        if existing is not None and not force:
            data = existing.get(include=["metadatas"])
            existing_hashes = [(m or {}).get("content_hash") for m in (data.get("metadatas") or [])]
            if len(existing_hashes) == len(hashes) and set(existing_hashes) == set(hashes):
                logger.info(f"合約 {job_id} 內容未變，沿用現有 {len(hashes)} 段索引（跳過重建）")
                return len(hashes)

        # 內容有變或強制重建 → 刪除後重建
        if existing is not None:
            try:
                chroma.delete_collection(collection_name)
            except Exception:
                pass

        embedder = self._get_embedder()
        embeddings = embedder.encode(chunks, show_progress_bar=False).tolist()

        collection = chroma.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        collection.add(
            embeddings=embeddings,
            documents=chunks,
            # 使用統計：hit_count（被檢索次數）、pos_count（被正評次數）→ 供回饋重排
            metadatas=[
                {"source": job_id, "content_hash": h, "hit_count": 0, "pos_count": 0}
                for h in hashes
            ],
            ids=[f"chunk_{i}" for i in range(len(chunks))],
        )

        logger.info(f"合約 {job_id} 已建立 {len(chunks)} 個向量段落索引")
        return len(chunks)

    def _retrieve(
        self, job_id: str, question: str, top_k: Optional[int] = None
    ) -> Tuple[List[str], List[str], bool]:
        """向量檢索 + 回饋重排，回傳 (段落文字, 段落 id, 是否有索引)。

        先取較多候選（RAG_RERANK_CANDIDATES），以 cosine + β·feedback 重排後取 top_k，
        並累計被選中段落的 hit_count。常被正評（pos_count 高）的段落會被提權。
        """
        from .config import settings

        top_k = top_k or settings.RAG_TOP_K
        chroma = self._get_chroma()
        collection_name = f"contract_{job_id}"

        try:
            collection = chroma.get_collection(collection_name)
        except Exception:
            return [], [], False

        embedder = self._get_embedder()
        q_embedding = embedder.encode([question]).tolist()

        n_cand = max(top_k, settings.RAG_RERANK_CANDIDATES)
        results = collection.query(
            query_embeddings=q_embedding,
            n_results=n_cand,
            include=["documents", "metadatas", "distances"],
        )
        docs = results.get("documents", [[]])[0]
        ids = results.get("ids", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        # 重排：cosine 相似度（= 1 - distance）+ β·回饋分數
        beta = settings.RAG_FEEDBACK_WEIGHT
        ranked = []
        for i in range(len(docs)):
            cosine = 1.0 - float(dists[i]) if i < len(dists) else 0.0
            meta = metas[i] if i < len(metas) else {}
            hit = (meta or {}).get("hit_count", 0) or 0
            pos = (meta or {}).get("pos_count", 0) or 0
            # 回饋分數：正評率，貝氏平滑（Beta(1,1)），無資料時為 0.5
            feedback = (pos + 1) / (hit + 2)
            ranked.append((cosine + beta * feedback, docs[i], ids[i] if i < len(ids) else None))

        ranked.sort(key=lambda x: x[0], reverse=True)
        top = ranked[:top_k]
        top_docs = [t[1] for t in top]
        top_ids = [t[2] for t in top if t[2] is not None]

        self._bump_counts(collection, top_ids, field="hit_count")
        return top_docs, top_ids, True

    @staticmethod
    def _bump_counts(collection, chunk_ids: List[str], field: str, amount: int = 1):
        """為指定段落的 metadata 計數器 +amount（hit_count / pos_count）。"""
        if not chunk_ids:
            return
        try:
            cur = collection.get(ids=chunk_ids, include=["metadatas"])
            metas = cur.get("metadatas") or []
            got_ids = cur.get("ids") or []
            new_metas = []
            for m in metas:
                m = dict(m or {})
                m[field] = (m.get(field, 0) or 0) + amount
                new_metas.append(m)
            if got_ids:
                collection.update(ids=got_ids, metadatas=new_metas)
        except Exception as e:
            logger.warning(f"更新段落計數失敗（{field}）：{e}")

    async def chat(
        self,
        job_id: str,
        question: str,
        llm: BaseLLMProvider,
        history: Optional[List[ChatMessage]] = None,
    ) -> Tuple[str, List[str], List[str]]:
        """
        對合約提問

        Args:
            job_id: 合約任務 ID
            question: 使用者問題
            llm: LLM 提供者
            history: 對話歷史

        Returns:
            (回答文字, 來源段落清單, 來源段落 id 清單)
        """
        relevant_chunks, source_ids, found = self._retrieve(job_id, question)

        if not found:
            # 尚未建立索引，先建立
            try:
                self.index_contract(job_id)
                relevant_chunks, source_ids, _ = self._retrieve(job_id, question)
            except Exception as e:
                return f"無法載入合約內容：{str(e)}", [], []

        if not relevant_chunks:
            return "在合約中找不到與您問題相關的段落。", [], []

        context = "\n\n---\n\n".join(relevant_chunks)
        context_msg = f"以下是合約中的相關段落：\n\n{context}"

        # 建立對話訊息
        messages: List[LLMMessage] = [
            LLMMessage(role="system", content=CHAT_SYSTEM_PROMPT),
        ]

        # 加入歷史對話（最多 6 輪）
        if history:
            for h in history[-6:]:
                messages.append(LLMMessage(role=h.role, content=h.content))

        messages.append(LLMMessage(
            role="user",
            content=f"{context_msg}\n\n使用者問題：{question}",
        ))

        response = await llm.chat(messages, temperature=0.2, max_tokens=2000)
        return response, relevant_chunks, source_ids

    def record_answer_feedback(self, job_id: str, chunk_ids: List[str], helpful: bool) -> int:
        """記錄使用者對某次問答的評價：有用 → 命中的段落 pos_count +1（提權）。

        回傳實際更新的段落數。同時寫入統一回饋庫（loop="rag"）。
        """
        from .feedback_store import feedback_store
        feedback_store.record(
            loop="rag",
            job_id=job_id,
            target_ref={"chunk_ids": chunk_ids},
            signal={"helpful": helpful},
        )
        if not helpful or not chunk_ids:
            return 0
        try:
            collection = self._get_chroma().get_collection(f"contract_{job_id}")
        except Exception:
            return 0
        self._bump_counts(collection, chunk_ids, field="pos_count")
        return len(chunk_ids)

    def delete_index(self, job_id: str) -> bool:
        """刪除合約的向量索引"""
        try:
            chroma = self._get_chroma()
            chroma.delete_collection(f"contract_{job_id}")
            logger.info(f"已刪除合約 {job_id} 的向量索引")
            return True
        except Exception:
            return False

    def is_indexed(self, job_id: str) -> bool:
        """檢查合約是否已建立索引"""
        try:
            chroma = self._get_chroma()
            chroma.get_collection(f"contract_{job_id}")
            return True
        except Exception:
            return False


# 全域單例
_chat_assistant: Optional[ContractChatAssistant] = None


def get_chat_assistant() -> ContractChatAssistant:
    global _chat_assistant
    if _chat_assistant is None:
        _chat_assistant = ContractChatAssistant()
    return _chat_assistant
