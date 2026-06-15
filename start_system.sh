#!/bin/bash
cd "$(cd "$(dirname "$0")" && pwd)"
source venv/bin/activate

# 啟動 Redis（如果未運行）
if ! pgrep -x "redis-server" > /dev/null; then
    echo "正在啟動 Redis 服務..."
    /usr/local/bin/redis-server &
    sleep 2
fi

# 啟動 Celery worker
echo "正在啟動 Celery worker..."
celery -A src.celery_app worker --loglevel=info &

# 啟動 FastAPI 服務
echo "正在啟動 FastAPI 服務..."
echo "系統正在啟動，請稍候..."
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
