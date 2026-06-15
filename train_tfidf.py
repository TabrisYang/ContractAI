import os
import joblib
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from tqdm import tqdm

def load_corpus(corpus_dir):
    """載入語料庫文件"""
    corpus = []
    corpus_dir = Path(corpus_dir)
    
    # 獲取所有 .txt 文件
    txt_files = list(corpus_dir.glob('*.txt'))
    
    if not txt_files:
        print(f"警告：在 {corpus_dir} 中找不到任何 .txt 文件")
        return corpus
    
    print(f"正在從 {len(txt_files)} 個文件中載入語料...")
    
    for txt_file in tqdm(txt_files, desc="載入文件"):
        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                corpus.append(f.read())
        except Exception as e:
            print(f"載入文件 {txt_file} 時出錯: {e}")
    
    return corpus

def train_tfidf(corpus, output_path, ngram_range=(1, 3), min_df=5):
    """訓練 TF-IDF 模型"""
    if not corpus:
        print("錯誤：語料庫為空，無法訓練模型")
        return None
    
    print(f"正在訓練 TF-IDF 模型 (ngram_range={ngram_range}, min_df={min_df})...")
    
    # 創建 TF-IDF 向量化器
    vectorizer = TfidfVectorizer(
        ngram_range=ngram_range,
        min_df=min_df,
        token_pattern=r'\b\w+\b'  # 匹配單詞邊界
    )
    
    # 擬合模型
    X = vectorizer.fit_transform(corpus)
    
    # 保存模型
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
    parser.add_argument('--output', type=str, default='models/tfidf.pkl',
                       help='模型輸出路徑 (默認: models/tfidf.pkl)')
    parser.add_argument('--ngram-min', type=int, default=1,
                       help='n-gram 最小長度 (默認: 1)')
    parser.add_argument('--ngram-max', type=int, default=3,
                       help='n-gram 最大長度 (默認: 3)')
    parser.add_argument('--min-df', type=int, default=5,
                       help='詞彙最小文檔頻率 (默認: 5)')
    
    args = parser.parse_args()
    
    # 載入語料
    corpus = load_corpus(args.corpus_dir)
    
    if corpus:
        # 訓練模型
        train_tfidf(
            corpus=corpus,
            output_path=args.output,
            ngram_range=(args.ngram_min, args.ngram_max),
            min_df=args.min_df
        )
