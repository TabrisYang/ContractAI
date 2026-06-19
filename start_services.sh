#!/bin/bash

# 啟動 Redis 服務 (如果尚未運行)
if ! pgrep -x "redis-server" > /dev/null; then
    echo "正在啟動 Redis 服務..."
    brew services start redis
fi

# 啟動 Celery worker
# macOS 上 prefork 池 fork 子程序後再載入 PyTorch/spaCy 會 SIGSEGV,
# 故改用 solo 池(不 fork);並設定 fork 安全與執行緒環境變數。
echo "正在啟動 Celery worker..."
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
export OMP_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false
celery -A src.celery_app worker --loglevel=info --pool=solo &
CELERY_PID=$!

# 啟動 FastAPI 服務
echo "正在啟動 FastAPI 服務..."
uvicorn src.api.main:app --reload

# 當 FastAPI 服務停止時，同時停止 Celery worker
trap "kill $CELERY_PID" EXIT
