#!/bin/bash

# 設置工作目錄（自動推導為本腳本所在目錄）
WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR" || exit

# 安裝 Homebrew (如果尚未安裝)
if ! command -v brew &> /dev/null; then
    echo "正在安裝 Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# 安裝必要的軟體
echo "正在安裝必要軟體..."
brew install redis
brew services start redis

# 安裝 Python 3.11
if ! command -v python3.11 &> /dev/null; then
    echo "正在安裝 Python 3.11..."
    brew install python@3.11
fi

# 創建虛擬環境
echo "正在設置 Python 虛擬環境..."
python3.11 -m venv venv
source venv/bin/activate

# 安裝依賴
echo "正在安裝 Python 依賴..."
pip install --upgrade pip
pip install -r requirements.txt
python -m spacy download zh_core_web_trf

# 創建必要的目錄
mkdir -p uploads outputs models logs corpus

# 創建 .env 文件
cat > .env << 'ENV'
# 應用程序設置
DEBUG=True
APP_NAME="合約去識別系統"

# 文件路徑
UPLOAD_DIR=./uploads
OUTPUT_DIR=./outputs
MODEL_DIR=./models
LOG_DIR=./logs
CORPUS_DIR=./corpus

# Redis 設置
REDIS_URL=redis://localhost:6379/0

# 模型設置
TFIDF_MODEL_PATH=./models/tfidf.pkl
SPACY_MODEL=zh_core_web_trf

# 去識別化設置
RARE_TERM_THRESHOLD=0.02
ENV

# 創建測試數據
echo "正在生成測試數據..."
python create_test_data.py

# 訓練 TF-IDF 模型
echo "正在訓練 TF-IDF 模型..."
python train_tfidf.py

# 移動應用程序包到桌面
cp -R "合約去識別系統.app" ~/Desktop/

echo "安裝完成！請在桌面上雙擊「合約去識別系統.app」來啟動系統。"
open -R ~/Desktop/合約去識別系統.app
