"""
參考合約庫自動同步管線
偵測新增/修改的合約 → 去識別化 → 增量向量化索引

用法：
    python index_contracts.py          # 互動模式（顯示完整進度）
    python index_contracts.py --auto   # 靜默模式（只處理新增，供啟動腳本呼叫）
"""
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.core.config import settings

COLLECTION_NAME = "contract_corpus"
CHUNK_SIZE = 400
OVERLAP = 50
EMBEDDING_MODEL = settings.EMBEDDING_MODEL
MANIFEST_PATH = settings.CONTRACTS_DEIDENTIFIED_DIR / "manifest.json"


def load_manifest() -> dict:
    """載入處理記錄（檔名 → 修改時間）"""
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict):
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_new_or_modified(source_dir: Path, manifest: dict) -> list[Path]:
    """找出尚未處理或已修改的 .docx 檔案"""
    new_files = []
    for docx_path in sorted(source_dir.glob("*.docx")):
        mtime = str(os.path.getmtime(docx_path))
        if docx_path.name not in manifest or manifest[docx_path.name] != mtime:
            new_files.append(docx_path)
    return new_files


_deidentifier_instance = None

def _get_deidentifier():
    """單例模式，只載入一次 spaCy 模型"""
    global _deidentifier_instance
    if _deidentifier_instance is None:
        from src.core.deidentifier import DocumentDeidentifier
        _deidentifier_instance = DocumentDeidentifier()
    return _deidentifier_instance


def deidentify_contract(docx_path: Path, output_dir: Path, file_index: int) -> str | None:
    """對單份合約執行去識別化，回傳去識別化後的純文字"""
    job_id = f"corpus_{uuid.uuid4().hex[:8]}"
    deidentifier = _get_deidentifier()

    try:
        result = deidentifier.process(
            input_path=str(docx_path),
            output_dir=output_dir,
            job_id=job_id,
            # 使用全部本機偵測層（Regex + 上下文 + 字典 + 商業機密 + NER），不用 tfidf
            mask_methods=["regex", "ner"],
        )

        # 讀取去識別化後的純文字
        txt_path = output_dir / f"{job_id}_deidentified.txt"
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8")
            # 以編號命名，避免原始檔名洩漏商業資訊
            final_path = output_dir / f"contract_{file_index:03d}.txt"
            final_path.write_text(text, encoding="utf-8")
            # 清理臨時檔案
            for tmp in output_dir.glob(f"{job_id}_*"):
                tmp.unlink(missing_ok=True)
            return text
    except Exception as e:
        print(f"  ⚠️  去識別化失敗 {docx_path.name}: {e}")
    return None


def chunk_text(text: str, source: str) -> list[dict]:
    """將文字切成重疊段落"""
    lines = [l for l in text.splitlines() if l.strip()]
    chunks = []
    current_lines = []
    current_len = 0

    for line in lines:
        current_lines.append(line)
        current_len += len(line)
        if current_len >= CHUNK_SIZE:
            chunk_text_str = "\n".join(current_lines)
            chunks.append({"text": chunk_text_str, "source": source})
            tail = chunk_text_str[-OVERLAP:]
            current_lines = [tail] if tail else []
            current_len = len(tail)

    if current_lines:
        chunks.append({"text": "\n".join(current_lines), "source": source})

    return [c for c in chunks if len(c["text"].strip()) > 20]


def build_index(all_chunks: list[dict], full_rebuild: bool = False):
    """向量化並存入 ChromaDB"""
    from sentence_transformers import SentenceTransformer
    import chromadb

    print("載入嵌入模型...")
    embedder = SentenceTransformer(EMBEDDING_MODEL)

    chroma = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))

    if full_rebuild:
        try:
            chroma.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        collection = chroma.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        id_offset = 0
    else:
        try:
            collection = chroma.get_collection(name=COLLECTION_NAME)
            id_offset = collection.count()
        except Exception:
            collection = chroma.create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            id_offset = 0

    batch_size = 64
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i: i + batch_size]
        texts = [c["text"] for c in batch]
        sources = [c["source"] for c in batch]

        embeddings = embedder.encode(texts, show_progress_bar=False).tolist()

        collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=[{"source": s} for s in sources],
            ids=[f"chunk_{id_offset + i + j}" for j in range(len(batch))],
        )

    return collection.count()


def write_summary(total_contracts: int, total_chunks: int):
    summary_path = settings.CHROMA_DIR / "corpus_summary.json"
    summary = {
        "total_contracts": total_contracts,
        "total_chunks": total_chunks,
        "collection": COLLECTION_NAME,
        "embedding_model": EMBEDDING_MODEL,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    auto_mode = "--auto" in sys.argv
    source_dir = settings.CONTRACTS_SOURCE_DIR
    deident_dir = settings.CONTRACTS_DEIDENTIFIED_DIR
    deident_dir.mkdir(parents=True, exist_ok=True)

    if not auto_mode:
        print("\n" + "=" * 50)
        print("  合約參考庫自動同步管線")
        print("=" * 50)

    # 確認合約目錄
    if not source_dir.exists():
        if auto_mode:
            print(f"ℹ️  contracts/ 目錄不存在，跳過同步")
            return
        print(f"❌ 找不到合約目錄：{source_dir}")
        sys.exit(1)

    all_docx = sorted(source_dir.glob("*.docx"))
    if not all_docx:
        if auto_mode:
            print(f"ℹ️  contracts/ 目錄下無 .docx 檔案，跳過同步")
            return
        print(f"❌ contracts/ 目錄下找不到 .docx 檔案")
        sys.exit(1)

    manifest = load_manifest()
    new_files = get_new_or_modified(source_dir, manifest)

    if not new_files:
        if auto_mode:
            print(f"✅ 合約庫已是最新（{len(all_docx)} 份合約）")
            return
        print(f"✅ 所有 {len(all_docx)} 份合約都已處理過，無需更新")
        print("   若要強制重建，請刪除 contracts_deidentified/ 目錄後重新執行")
        return

    if not auto_mode:
        print(f"✅ 找到 {len(all_docx)} 份合約，其中 {len(new_files)} 份需要處理")
        print(f"📦 嵌入模型：{EMBEDDING_MODEL}")
        print()

    # ── 第一階段：去識別化 ──────────────────────────
    if not auto_mode:
        print("【第一階段】去識別化新合約...")
    else:
        print(f"同步合約庫：去識別化 {len(new_files)} 份新合約...")

    new_chunks = []
    processed_count = 0

    # 計算起始編號（已處理的數量 + 1）
    existing_count = len(manifest) - len(new_files)  # 之前已處理的數量

    for idx, docx_path in enumerate(new_files, 1):
        if not auto_mode:
            print(f"  [{idx}/{len(new_files)}] {docx_path.name}")

        file_index = existing_count + idx
        text = deidentify_contract(docx_path, deident_dir, file_index)
        if text:
            chunks = chunk_text(text, source=f"contract_{file_index:03d}")
            new_chunks.extend(chunks)
            manifest[docx_path.name] = str(os.path.getmtime(docx_path))
            processed_count += 1
        else:
            if not auto_mode:
                print(f"    ⚠️  跳過")

    save_manifest(manifest)

    if not auto_mode:
        print(f"\n✅ 去識別化完成：{processed_count}/{len(new_files)} 份成功")
        print(f"   產生 {len(new_chunks)} 個段落")

    if not new_chunks:
        print("⚠️  沒有新段落需要索引")
        return

    # ── 第二階段：增量索引 ──────────────────────────
    if not auto_mode:
        print("\n【第二階段】增量向量化索引...")
    else:
        print(f"向量化 {len(new_chunks)} 個段落...")

    # 判斷是否需要全量重建（manifest 中的檔案數 == 新處理數，即首次）
    is_first_build = (processed_count == len(manifest))
    total_chunks = build_index(new_chunks, full_rebuild=is_first_build)

    # 更新摘要
    total_contracts = len([f for f in manifest if manifest[f]])
    write_summary(total_contracts, total_chunks)

    if not auto_mode:
        print("\n" + "=" * 50)
        print(f"🎉 同步完成！")
        print(f"   合約數量：{total_contracts} 份")
        print(f"   段落數量：{total_chunks} 個")
        print(f"   去識別化目錄：{deident_dir}")
        print(f"   向量資料庫：{settings.CHROMA_DIR}")
        print("=" * 50 + "\n")
    else:
        print(f"✅ 合約庫同步完成（{total_contracts} 份合約，{total_chunks} 個段落）")


if __name__ == "__main__":
    main()
