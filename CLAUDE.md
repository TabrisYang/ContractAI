# CLAUDE.md

繁體中文合約去識別化系統。公開 repo，任何人可 clone 使用。

完整開發規範見 [CONTRIBUTING.md](CONTRIBUTING.md)，以下是最容易出錯、必須遵守的部分。

## 核心原則：本機能跑 ≠ 別人裝得起來

本機 `venv/` 早已裝好，`requirements.txt` 寫錯不影響本機執行，只有全新環境會炸。
曾因此讓 `ckip-transformers>=0.4.4`（PyPI 最新僅 0.3.4，且程式碼零引用）
存活 5 個 commit，期間所有新使用者都無法安裝。

**只要動到 `requirements.txt`，必須在乾淨 venv 驗證後才能推送：**

```bash
cd /tmp && rm -rf ci_check && git clone <工作目錄> ci_check && cd ci_check
python3 -m venv v && ./v/bin/pip install -r requirements.txt
./v/bin/python -c "import src.api.main; print('OK')"
```

新增套件前用 `pip index versions <套件名>` 確認版本存在，
且**程式碼要真的有引用**才加進 requirements.txt。

## 絕不可提交

`.env`、`contracts/`、`contracts_deidentified/`、`chroma_db/`、`feedback/`、
`models/`、`corpus/`、`uploads/`、`outputs/`

已在 `.gitignore`，但改動 gitignore 時要重新確認。
**用 `git add <明確檔名>`，不要 `git add .`。**

## CI 的邊界

`.github/workflows/ci.yml` 於 Python 3.11 / 3.12 驗證：乾淨安裝、三個進入點
import、去識別化冒煙測試（斷言姓名／身分證／電話／統編皆已遮罩）。

**不涵蓋**：Celery/Redis 非同步流程、RAG 對話與生成、PDF/OCR、`.doc` 轉檔、
Streamlit 前端。改到這些範圍時必須手動測，不能只看 CI 綠燈。

推送後要確認 CI 通過。紅燈代表新使用者裝不起來，不可忽略硬推。

## 改程式碼要連帶更新的文件

| 改動 | 同步更新 |
|---|---|
| 依賴 | `requirements.txt`、README 系統需求 |
| 環境變數 | `.env.example`、`src/core/config.py` |
| API 端點 | README 使用說明的 curl 範例 |
| 新產生的目錄 | `.gitignore`、README 專案結構 |
| 安裝步驟 | README 快速開始、`auto_install.sh` |

## 慣例

- 錯誤處理照 `src/api/main.py` 既有寫法：`logger.error(...)` 後
  `raise HTTPException(status_code=..., detail="可讀訊息")`。
  不要讓例外裸奔成 `Internal Server Error`。
- 註解與 commit 訊息用繁體中文，說明「為什麼」而非只寫「改了什麼」。
- 缺少選用資源時應優雅降級（如缺 `models/tfidf.pkl` 時停用罕見詞偵測並記錄
  WARNING），不要直接崩潰。
