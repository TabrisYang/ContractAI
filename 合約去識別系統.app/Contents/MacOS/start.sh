#!/bin/bash

# 設置工作目錄（.app 位於 主程式/ 內，往上三層即專案根目錄）
WORKDIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$WORKDIR" || exit

# 啟動 Redis（如果未運行）
if ! pgrep -x "redis-server" > /dev/null; then
    echo "正在啟動 Redis 服務..."
    /usr/local/bin/redis-server &
    sleep 2
fi

# 啟動虛擬環境
source venv/bin/activate

# 啟動 Celery worker
echo "正在啟動 Celery worker..."
celery -A src.celery_app worker --loglevel=info &

# 啟動 FastAPI 服務
echo "正在啟動 FastAPI 服務..."
open "http://127.0.0.1:8000/docs"
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 保持終端開啟
echo "按 Enter 鍵退出..."
read
