#!/bin/bash
# ============================================================
#  合約去識別化系統 — 一鍵啟動
#  雙擊此檔案即可啟動所有服務並開啟瀏覽器
# ============================================================

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR" || { echo "❌ 找不到工作目錄：$WORKDIR"; read -p "按任意鍵關閉..."; exit 1; }

# ── 顏色輸出 ────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

echo ""
echo "============================================"
echo "   合約去識別化系統  啟動中..."
echo "============================================"
echo ""

# ── 啟用虛擬環境 ────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    err "找不到虛擬環境，請先執行「安裝合約去識別系統.command」"
    read -p "按任意鍵關閉..."
    exit 1
fi
source venv/bin/activate
log "虛擬環境已啟用"

# ── 檢查並安裝新依賴（用 pip show 取代 import，速度快很多）────────────────
MISSING_PKGS=()

pip show pydantic-settings  &>/dev/null || MISSING_PKGS+=("pydantic-settings")
pip show spacy              &>/dev/null || MISSING_PKGS+=("spacy[transformers]")
pip show python-dotenv      &>/dev/null || MISSING_PKGS+=("python-dotenv")
pip show celery             &>/dev/null || MISSING_PKGS+=("celery[redis]")
pip show fastapi            &>/dev/null || MISSING_PKGS+=("fastapi")
pip show uvicorn            &>/dev/null || MISSING_PKGS+=("uvicorn[standard]")
pip show redis              &>/dev/null || MISSING_PKGS+=("redis")
pip show python-docx        &>/dev/null || MISSING_PKGS+=("python-docx")
pip show loguru             &>/dev/null || MISSING_PKGS+=("loguru")
pip show httpx              &>/dev/null || MISSING_PKGS+=("httpx")
pip show chromadb           &>/dev/null || MISSING_PKGS+=("chromadb")
pip show sentence-transformers &>/dev/null || MISSING_PKGS+=("sentence-transformers")
pip show streamlit          &>/dev/null || MISSING_PKGS+=("streamlit")
pip show requests           &>/dev/null || MISSING_PKGS+=("requests")
pip show playwright         &>/dev/null || MISSING_PKGS+=("playwright")

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    warn "偵測到尚未安裝的套件，開始安裝（首次需要幾分鐘，請耐心等候）..."
    echo ""
    echo "  需要安裝：${MISSING_PKGS[*]}"
    echo "  套件較大（sentence-transformers 約 500MB），請勿關閉此視窗..."
    echo ""

    # 逐一安裝並顯示進度
    for pkg in "${MISSING_PKGS[@]}"; do
        info "正在安裝 $pkg ..."
        pip install "$pkg" --progress-bar on
        if [ $? -ne 0 ]; then
            err "安裝 $pkg 失敗，請嘗試手動執行：pip install $pkg"
            read -p "按任意鍵關閉..."
            exit 1
        fi
        log "$pkg 安裝完成"
    done

    # 若 playwright 是新安裝的，同時安裝瀏覽器
    if [[ " ${MISSING_PKGS[*]} " =~ " playwright " ]]; then
        info "安裝 Chromium 瀏覽器（供訂閱制 LLM 使用，約 200MB）..."
        playwright install chromium
    fi

    echo ""
    log "全部套件安裝完成"
fi

# ── 儲存子程序 PID（方便結束時清理）────────────────────────────────
PIDS=()

cleanup() {
    echo ""
    info "正在關閉所有服務..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    # 關閉 Celery worker（--detach 啟動的不在 PIDS 中）
    if [ -f "$WORKDIR/logs/celery.pid" ]; then
        CELERY_PID=$(cat "$WORKDIR/logs/celery.pid")
        kill "$CELERY_PID" 2>/dev/null
        rm -f "$WORKDIR/logs/celery.pid"
    fi
    # 停止 Redis（如果是本腳本啟動的）
    if [ "$REDIS_STARTED_BY_US" = "true" ]; then
        brew services stop redis 2>/dev/null || true
    fi
    log "所有服務已關閉"
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ── 啟動 Redis ────────────────────────────────────────────────
if pgrep -x "redis-server" > /dev/null 2>&1; then
    log "Redis 已在執行中"
    REDIS_STARTED_BY_US="false"
else
    info "啟動 Redis..."
    # 嘗試 brew services（推薦）
    if command -v brew &>/dev/null; then
        brew services start redis 2>/dev/null && REDIS_STARTED_BY_US="true"
    fi
    # 若 brew 啟動失敗，直接執行 redis-server
    if ! pgrep -x "redis-server" > /dev/null 2>&1; then
        REDIS_CMD=$(command -v redis-server || echo "/usr/local/bin/redis-server")
        if [ -f "$REDIS_CMD" ]; then
            "$REDIS_CMD" --daemonize yes --logfile "$WORKDIR/logs/redis.log"
            REDIS_STARTED_BY_US="true"
        else
            err "找不到 redis-server，請先執行：brew install redis"
            read -p "按任意鍵關閉..."
            exit 1
        fi
    fi
    sleep 1
    log "Redis 已啟動"
fi

# ── 確保 venv bin 路徑在 PATH 最前面 ────────────────────────────────
export PATH="$WORKDIR/venv/bin:$PATH"

# ── 清理舊的 Celery 程序 ────────────────────────────────────────────────
CELERY_PID_FILE="$WORKDIR/logs/celery.pid"
if [ -f "$CELERY_PID_FILE" ]; then
    OLD_PID=$(cat "$CELERY_PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        warn "偵測到舊的 Celery 程序（PID: $OLD_PID），正在關閉..."
        kill "$OLD_PID" 2>/dev/null
        sleep 1
    fi
    rm -f "$CELERY_PID_FILE"
fi

# ── 啟動 Celery Worker ────────────────────────────────────────────────
info "啟動 Celery Worker..."
python -m celery -A src.celery_app worker \
    --loglevel=info \
    --logfile="$WORKDIR/logs/celery.log" \
    --detach \
    --pidfile="$WORKDIR/logs/celery.pid"
sleep 2
log "Celery Worker 已啟動"

# ── 自動同步參考合約庫 ────────────────────────────────────────────────
if [ -d "$WORKDIR/../contracts" ]; then
    DOCX_COUNT=$(ls -1 "$WORKDIR/../contracts"/*.docx 2>/dev/null | wc -l | tr -d ' ')
    if [ "$DOCX_COUNT" -gt 0 ]; then
        info "同步參考合約庫（偵測到 ${DOCX_COUNT} 份合約）..."
        python index_contracts.py --auto 2>&1
        if [ $? -eq 0 ]; then
            log "參考合約庫同步完成"
        else
            warn "合約庫同步失敗（不影響主系統啟動）"
        fi
    fi
fi

# ── 啟動 FastAPI ────────────────────────────────────────────────
info "啟動 FastAPI 後端（port 8000）..."
python -m uvicorn src.api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning \
    >> "$WORKDIR/logs/fastapi.log" 2>&1 &
FASTAPI_PID=$!
PIDS+=($FASTAPI_PID)

# 等待 FastAPI 就緒
for i in {1..20}; do
    sleep 1
    if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
        log "FastAPI 後端已就緒 → http://localhost:8000"
        break
    fi
    if [ $i -eq 20 ]; then
        err "FastAPI 啟動逾時，錯誤訊息如下："
        echo "--------------------------------------------"
        tail -20 "$WORKDIR/logs/fastapi.log" 2>/dev/null || echo "（log 檔案為空）"
        echo "--------------------------------------------"
        read -p "按任意鍵關閉..."
        exit 1
    fi
done

# ── 啟動 Streamlit 前端 ────────────────────────────────────────────────
info "啟動 Streamlit 前端（port 8501）..."
python -m streamlit run frontend/app.py \
    --server.port 8501 \
    --server.headless true \
    --server.address 0.0.0.0 \
    --browser.gatherUsageStats false \
    >> "$WORKDIR/logs/streamlit.log" 2>&1 &
STREAMLIT_PID=$!
PIDS+=($STREAMLIT_PID)

# 等待 Streamlit 就緒
for i in {1..20}; do
    sleep 1
    if curl -s http://localhost:8501 > /dev/null 2>&1; then
        log "Streamlit 前端已就緒 → http://localhost:8501"
        break
    fi
    if [ $i -eq 20 ]; then
        warn "Streamlit 啟動時間較長，將直接開啟瀏覽器..."
        break
    fi
done

# ── 開啟瀏覽器 ────────────────────────────────────────────────
sleep 1
open "http://localhost:8501"
log "已開啟瀏覽器"

echo ""
echo "============================================"
echo "   🚀 系統已成功啟動！"
echo "--------------------------------------------"
echo "   前端介面：http://localhost:8501"
echo "   API 文件：http://localhost:8000/docs"
echo "--------------------------------------------"
echo "   關閉方式：直接關閉此視窗"
echo "============================================"
echo ""

# ── 保持執行（等待使用者關閉視窗）────────────────────────────────
wait $STREAMLIT_PID
