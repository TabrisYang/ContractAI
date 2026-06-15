#!/bin/bash

# 啟動 Redis 服務 (如果尚未運行)
if ! pgrep -x "redis-server" > /dev/null; then
    echo "正在啟動 Redis 服務..."
    brew services start redis
fi

# 啟動 Celery worker
echo "正在啟動 Celery worker..."
celery -A src.celery_app worker --loglevel=info &
CELERY_PID=$!

# 啟動 FastAPI 服務
echo "正在啟動 FastAPI 服務..."
uvicorn src.api.main:app --reload

# 當 FastAPI 服務停止時，同時停止 Celery worker
trap "kill $CELERY_PID" EXIT
