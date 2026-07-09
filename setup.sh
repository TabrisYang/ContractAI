#!/bin/bash

cd "$(cd "$(dirname "$0")" && pwd)"

# 創建必要的目錄
mkdir -p uploads outputs models logs corpus

# 創建 .env 文件（已存在則保留，不覆寫使用者設定）
if [ -f .env ]; then
    echo "已偵測到 .env，保留現有設定。"
else
    cp .env.example .env
    echo "已從 .env.example 建立 .env。"
fi

echo ""
echo "目錄與設定檔已就緒。請接續完成："
echo "1. 創建虛擬環境: conda create -n contract_deid python=3.11 -y"
echo "2. 激活環境: conda activate contract_deid"
echo "3. 安裝依賴: pip install -r requirements.txt"
echo "4. 下載模型: python -m spacy download zh_core_web_sm"
echo "5. 安裝 Redis: brew install redis && brew services start redis"
