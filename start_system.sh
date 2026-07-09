#!/bin/bash
cd "$(cd "$(dirname "$0")" && pwd)"
source venv/bin/activate

# 啟動 Redis（如果未運行）
# 用 command -v 偵測，同時支援 Intel(/usr/local) 與 Apple Silicon(/opt/homebrew)
if ! pgrep -x "redis-server" > /dev/null; then
    REDIS_BIN="$(command -v redis-server)"
    if [ -z "$REDIS_BIN" ]; then
        echo "找不到 redis-server，請先執行：brew install redis" >&2
        exit 1
    fi
    echo "正在啟動 Redis 服務..."
    "$REDIS_BIN" &
    sleep 2
fi

# 啟動 Celery worker
echo "正在啟動 Celery worker..."
celery -A src.celery_app worker --loglevel=info &

# 啟動 FastAPI 服務
echo "正在啟動 FastAPI 服務..."
echo "系統正在啟動，請稍候..."
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
