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
python -m spacy download zh_core_web_sm

# 創建必要的目錄
mkdir -p uploads outputs models logs corpus

# 創建 .env 文件（已存在則保留，不覆寫使用者設定）
if [ -f .env ]; then
    echo "已偵測到 .env，保留現有設定。"
else
    cp .env.example .env
    echo "已從 .env.example 建立 .env。"
fi

# 創建測試數據
echo "正在生成測試數據..."
python create_test_data.py

# 訓練 TF-IDF 模型
echo "正在訓練 TF-IDF 模型..."
python train_tfidf.py

# 創建啟動腳本
cat > start_system.sh << 'EOL2'
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
EOL2

# 設置執行權限
chmod +x start_system.sh

# 創建桌面快捷方式（將安裝目錄寫入捷徑）
cat > ~/Desktop/啟動合約去識別系統.command << EOL3
#!/bin/bash
cd "$WORKDIR"
./start_system.sh
EOL3
chmod +x ~/Desktop/啟動合約去識別系統.command

# 啟動系統
echo "正在啟動系統..."
open -a Terminal.app "$WORKDIR/start_system.sh"

# 打開瀏覽器
sleep 5
open "http://127.0.0.1:8000/docs"

echo "系統已成功啟動！請在瀏覽器中查看界面。"
echo "您也可以通過雙擊桌面上的「啟動合約去識別系統.command」來啟動系統。"
