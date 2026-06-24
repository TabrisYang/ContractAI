import os
import sys
import joblib
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from src.core.config import settings


def load_corpus(corpus_dir):
    """載入語料庫文件"""
    corpus = []
    corpus_dir = Path(corpus_dir)

    if not corpus_dir.exists():
        return corpus

    # 獲取所有 .txt 文件
    txt_files = list(corpus_dir.glob('*.txt'))

    if not txt_files:
        print(f"警告：在 {corpus_dir} 中找不到任何 .txt 文件")
        return corpus

    print(f"正在從 {len(txt_files)} 個文件中載入語料（{corpus_dir}）...")

    for txt_file in tqdm(txt_files, desc="載入文件"):
        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                corpus.append(f.read())
        except Exception as e:
            print(f"載入文件 {txt_file} 時出錯: {e}")

    return corpus


def gather_corpus(corpus_dir, include_deidentified=True):
    """合併語料來源：固定 corpus/ + 已處理過的去識別化合約。

    讓訓練語料隨系統使用而增長（合約越多，統計基準越穩）。
    """
    corpus = load_corpus(corpus_dir)
    if include_deidentified:
        extra = load_corpus(settings.CONTRACTS_DEIDENTIFIED_DIR)
        if extra:
            print(f"另從去識別化合約庫加入 {len(extra)} 份語料")
            corpus += extra
    return corpus


def load_feedback_terms():
    """從 deid 回饋推導：(已驗證敏感詞, 誤判詞)。

    誤判詞 → 訓練時排除（stop_words），避免再被當成罕見敏感詞。
    敏感詞 → 由 P1 動態字典即時強制遮罩，這裡僅回報統計（TF-IDF 罕見詞選取
    機制不適合用來「提權」特定詞，故不在此處動 idf）。
    """
    try:
        from src.core.feedback_store import feedback_store
    except Exception as e:
        print(f"⚠️  無法載入回饋庫，略過回饋：{e}")
        return set(), set()

    sensitive, false_pos = set(), set()
    for rec in feedback_store.query("deid"):
        sig = rec.get("signal", {})
        text = (sig.get("text") or "").strip()
        if not text:
            continue
        if sig.get("is_valid") is False:
            false_pos.add(text)
        elif sig.get("missing") or sig.get("corrected_type"):
            sensitive.add(text)
    return sensitive, false_pos


def train_tfidf(corpus, output_path, ngram_range=(1, 3), min_df=5, stop_terms=None):
    """訓練 TF-IDF 模型。stop_terms：使用者標記為誤判、訓練時排除的詞。"""
    if not corpus:
        print("錯誤：語料庫為空，無法訓練模型")
        return None

    # sklearn 預設 lowercase=True，stop_words 需小寫才能正確比對（中文不受影響）
    stop_words = sorted({t.lower() for t in stop_terms}) if stop_terms else None
    print(f"正在訓練 TF-IDF 模型 (ngram_range={ngram_range}, min_df={min_df}, "
          f"排除誤判詞={len(stop_words) if stop_words else 0})...")

    vectorizer = TfidfVectorizer(
        ngram_range=ngram_range,
        min_df=min_df,
        token_pattern=r'\b\w+\b',  # 匹配單詞邊界
        stop_words=stop_words,
    )

    vectorizer.fit_transform(corpus)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(vectorizer, output_path)

    print(f"模型已保存到 {output_path}")
    print(f"詞彙表大小: {len(vectorizer.get_feature_names_out())}")

    return vectorizer


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='訓練 TF-IDF 模型')
    parser.add_argument('--corpus-dir', type=str, default='corpus',
                       help='語料庫目錄路徑 (默認: corpus)')
    parser.add_argument('--output', type=str, default=str(settings.TFIDF_MODEL_PATH),
                       help='模型輸出路徑')
    parser.add_argument('--ngram-min', type=int, default=1,
                       help='n-gram 最小長度 (默認: 1)')
    parser.add_argument('--ngram-max', type=int, default=3,
                       help='n-gram 最大長度 (默認: 3)')
    parser.add_argument('--min-df', type=int, default=5,
                       help='詞彙最小文檔頻率 (默認: 5)')
    parser.add_argument('--with-feedback', action='store_true',
                       help='納入使用者回饋（擴充語料 + 排除誤判詞）')

    args = parser.parse_args()

    stop_terms = None
    if args.with_feedback:
        sensitive, false_pos = load_feedback_terms()
        stop_terms = false_pos
        print(f"回饋：已驗證敏感詞 {len(sensitive)} 個（由動態字典即時生效）、"
              f"誤判詞 {len(false_pos)} 個（訓練時排除）")
        corpus = gather_corpus(args.corpus_dir, include_deidentified=True)
    else:
        corpus = load_corpus(args.corpus_dir)

    if corpus:
        train_tfidf(
            corpus=corpus,
            output_path=args.output,
            ngram_range=(args.ngram_min, args.ngram_max),
            min_df=args.min_df,
            stop_terms=stop_terms,
        )
