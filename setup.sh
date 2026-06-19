#!/bin/bash

# 創建必要的目錄
mkdir -p uploads outputs models logs corpus

# 創建 .env 文件
cat > .env << 'EOL'
# 應用程序設置
DEBUG=True
APP_NAME="合約去識別化系統"

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

# .doc 轉檔（留空 → 自動偵測 soffice / libreoffice;或填 soffice 絕對路徑）
LIBREOFFICE_BIN=
EOL

echo "安裝腳本已創建完成。請運行以下命令完成設置："
echo "1. 給腳本執行權限: chmod +x setup.sh"
echo "2. 執行腳本: ./setup.sh"
echo "3. 創建虛擬環境: conda create -n contract_deid python=3.11 -y"
echo "4. 激活環境: conda activate contract_deid"
echo "5. 安裝依賴: pip install -r requirements.txt"
echo "6. 下載模型: python -m spacy download zh_core_web_trf"
echo "7. 安裝 Redis: brew install redis && brew services start redis"
