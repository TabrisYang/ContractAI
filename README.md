# 繁體中文合約去識別化系統

這是一個用於自動化處理繁體中文合約的去識別化系統，可以自動偵測並遮罩敏感個資，同時保留原始文件格式。

## 功能特點

- 支援 .docx 檔案處理
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

## 🚀 快速開始

### 1. 安裝依賴

```bash
# 1. 安裝 Homebrew (如果尚未安裝)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安裝 Redis
brew install redis

# 3. 創建並啟動虛擬環境
conda create -n contract_deid python=3.11 -y
conda activate contract_deid

# 4. 安裝 Python 依賴
pip install -r requirements.txt

# 5. 下載繁體中文模型
python -m spacy download zh_core_web_trf
```

### 2. 初始化專案

```bash
# 1. 給腳本執行權限
chmod +x setup.sh start_services.sh

# 2. 運行設置腳本
./setup.sh

# 3. 創建測試數據
python create_test_data.py

# 4. 訓練 TF-IDF 模型
python train_tfidf.py
```

### 3. 啟動服務

```bash
# 啟動 Redis 和所有服務
./start_services.sh
```

### 4. 使用 API

1. 訪問 http://127.0.0.1:8000/docs 查看 API 文檔
2. 使用 Swagger UI 上傳測試文件
3. 查看 `outputs/` 目錄下的處理結果

## 🛠 專案結構

```
主程式/
├── src/                    # 主要原始碼
│   ├── api/               # FastAPI 路由與端點
│   ├── core/              # 核心處理邏輯
│   ├── models/            # 資料模型
│   └── utils/             # 工具函數
├── models/                # 訓練好的模型與向量化器
├── uploads/               # 上傳的原始檔案
├── outputs/               # 處理後的輸出檔案
├── logs/                  # 系統日誌
├── corpus/                # 訓練用語料庫
├── .env                  # 環境變數配置
├── setup.sh              # 一鍵設置腳本
├── start_services.sh     # 啟動服務腳本
├── create_test_data.py   # 生成測試數據
└── train_tfidf.py       # 訓練 TF-IDF 模型
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

## 📄 授權

MIT License
