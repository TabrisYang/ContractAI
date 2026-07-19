# 繁體中文合約去識別化系統

這是一個用於自動化處理繁體中文合約的去識別化系統，可以自動偵測並遮罩敏感個資，同時保留原始文件格式。

## 功能特點

- 支援 .docx 與舊版 .doc 檔案處理（.doc 會自動轉成 .docx）
- 支援 PDF 檔案處理：電子文字型直接抽取；掃描/拍照型自動以 OCR 辨識
  （PDF 經抽取文字後處理，**不保留原 PDF 版面**，輸出為去識別化的 docx/txt/json）
- 多種去識別化方法整合：
  - 正則表達式匹配（身份證、手機、統編等）
  - NER 模型識別（姓名、公司、地址等）
  - TF-IDF 罕見詞檢測
- 保留原始文件格式與排版
- 非同步處理架構

## 系統需求

- Python 3.11+
- Redis (用於任務隊列)
- MacOS/Linux 環境 (Windows 需額外設置)
- (選用) 上傳舊版 .doc 檔需要轉檔工具，擇一安裝：
  - 推薦（保留排版）：`brew install --cask libreoffice`（macOS）/ `apt install libreoffice`（Linux）
  - 輕量退化（純文字）：`brew install antiword` / `apt install antiword`
  - 未安裝時仍可正常使用 .docx；上傳 .doc 才會提示需安裝。
  - 若 LibreOffice 不在 PATH，可於 .env 設定 `LIBREOFFICE_BIN=/絕對路徑/soffice`。
- (選用) 上傳掃描/拍照型 PDF 需要 OCR 系統工具：
  - macOS：`brew install poppler tesseract tesseract-lang`
  - Linux：`apt install poppler-utils tesseract-ocr tesseract-ocr-chi-tra`
  - 未安裝時仍可處理電子文字型 PDF；僅掃描檔會提示需安裝 OCR。

## 🚀 快速開始

### 1. 安裝依賴

```bash
# 1. 安裝 Homebrew (如果尚未安裝)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安裝 Redis
brew install redis

# 3. (選用) 處理 .doc 與掃描型 PDF 所需的系統工具
#    未安裝時 .docx 與電子文字型 PDF 仍可正常使用
brew install --cask libreoffice                 # .doc 轉檔（保留排版）
brew install poppler tesseract tesseract-lang   # 掃描型 PDF 的 OCR

# 4. 創建並啟動虛擬環境
conda create -n contract_deid python=3.11 -y
conda activate contract_deid

# 5. 安裝 Python 依賴
pip install -r requirements.txt

# 6. 下載繁體中文 spaCy 模型
#    zh_core_web_sm 為預設值（15MB）；未先下載時程式會於首次執行自動抓取
python -m spacy download zh_core_web_sm
#    若要改用較準的 zh_core_web_trf（415MB，建議搭配 GPU），
#    請改下載它並在 .env 設定 SPACY_MODEL=zh_core_web_trf
```

### 2. 初始化專案

```bash
# 1. (選用) 建立 .env。每項設定都有預設值，沒有 .env 也能啟動
cp .env.example .env

# 2. 給腳本執行權限
chmod +x start_services.sh

# 3. 創建測試數據
python create_test_data.py

# 4. 訓練 TF-IDF 模型（產生 models/tfidf.pkl）
#    略過此步時罕見詞偵測會自動停用，其餘功能不受影響
python train_tfidf.py
```

### 3. 啟動服務

兩種方式，擇一即可。

**方式 A：Streamlit 圖形介面（推薦）**

前端會自動把 Redis / Celery / FastAPI 一併帶起來。
必須從專案根目錄執行，否則 `from frontend.backend_manager import ...` 會找不到套件：

```bash
streamlit run frontend/app.py
```

**方式 B：只啟動後端 API**

```bash
./start_services.sh
```

### 4. 使用 API

1. 訪問 http://127.0.0.1:8000/docs 查看 API 文檔
2. 使用 Swagger UI 上傳測試文件
3. 查看 `outputs/` 目錄下的處理結果

### 5. (選用) 建立合約知識庫，啟用「對話助手」與「合約生成」

這兩項功能倚賴 RAG 向量索引。**在建立索引之前，`/api/v1/chat` 與 `/api/v1/generate` 會回傳 503**，
去識別化主功能則完全不受影響。

```bash
# 1. 準備一個放原始 .docx 合約的資料夾。
#    預設讀取 repo 外層的 ../contracts/，也可在 .env 指定：
#    CONTRACTS_SOURCE_DIR=/絕對路徑/你的合約資料夾

# 2. 建立索引（會先自動去識別化，再寫入 chroma_db/ 向量庫）
python index_contracts.py
```

> 本 repo 不含任何合約資料、向量庫或訓練好的模型（皆已列入 `.gitignore`），
> 你需要自備合約來建立自己的知識庫。

## 🛠 專案結構

標示 (產生) 的目錄不在版控內，會於首次執行時自動建立。

```
主程式/
├── src/                    # 主要原始碼
│   ├── api/               # FastAPI 路由與端點
│   ├── core/              # 核心處理邏輯（含 llm/ provider）
│   ├── models/            # Pydantic 資料模型（schemas.py）
│   └── utils/             # 工具函數
├── frontend/              # Streamlit 前端
├── models/       (產生)    # 訓練好的模型與向量化器（tfidf.pkl）
├── chroma_db/    (產生)    # RAG 向量資料庫
├── uploads/      (產生)    # 上傳的原始檔案
├── outputs/      (產生)    # 處理後的輸出檔案
├── feedback/     (產生)    # 使用者回饋記錄
├── logs/         (產生)    # 系統日誌
├── corpus/       (產生)    # 訓練用語料庫
├── .env.example           # 環境變數範本（複製成 .env）
├── start_services.sh      # 啟動後端服務腳本
├── create_test_data.py    # 生成測試數據
├── train_tfidf.py         # 訓練 TF-IDF 模型
└── index_contracts.py     # 建立 RAG 向量索引
```

## 📚 使用說明

### 1. 上傳合約

使用 POST 請求上傳合約文件：

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/v1/deidentify' \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@/path/to/your/contract.docx;type=application/vnd.openxmlformats-officedocument.wordprocessingml.document'
```

### 2. 查詢處理狀態

```bash
curl -X 'GET' \
  'http://127.0.0.1:8000/api/v1/status/{job_id}' \
  -H 'accept: application/json'
```

### 3. 下載處理結果

```bash
curl -X 'GET' \
  'http://127.0.0.1:8000/api/v1/download/{job_id}' \
  -H 'accept: application/json'
```

## 🔧 自定義設置

### 修改正則表達式規則

編輯 `src/core/deidentifier.py` 中的 `self.patterns` 字典，添加或修改正則表達式規則。

### 調整 TF-IDF 參數

```bash
python train_tfidf.py --ngram-min 1 --ngram-max 3 --min-df 5
```

## 📝 注意事項

1. 首次運行時，請確保 Redis 服務已啟動
2. 處理大型文件時可能需要較長時間
3. 請勿將包含敏感信息的文件上傳到公共環境

## 🤝 開發與貢獻

修改本專案並推送前，請先閱讀 [CONTRIBUTING.md](CONTRIBUTING.md)，重點包含：

- **推送前檢查清單** — 哪些檔案絕不可提交（`.env`、真實合約、向量庫等）
- **依賴改動的驗證方式** — 本機 venv 早已裝好，`requirements.txt` 寫錯只有全新環境才會炸
- **CI 的涵蓋範圍** — 哪些改動自動把關，哪些必須手動測

每次 push 與 PR 會自動於 Python 3.11 / 3.12 的乾淨環境驗證安裝、import
與去識別化功能（見 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)）。
CI 紅燈代表新使用者無法安裝，請勿忽略。

## 📄 授權

MIT License
