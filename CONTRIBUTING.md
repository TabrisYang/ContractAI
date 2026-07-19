# 開發與推送須知

本專案是公開 repo，任何人都能 clone 下來使用。因此每次推送都要確保兩件事：
**別人裝得起來**，以及**沒有把真實資料推上去**。

## 為什麼需要這份文件

2026-07 曾發生一次事故：`requirements.txt` 釘選了 `ckip-transformers>=0.4.4`，
但 PyPI 上該套件最新只到 0.3.4，任何人執行 `pip install -r requirements.txt` 都會失敗。
這個問題存活了 5 個 commit 沒被發現，原因很簡單 ——

> **本機開發時 venv 早就裝好了，requirements.txt 寫錯完全不影響你自己執行。
> 只有全新環境才會炸。**

「推得上去」和「別人裝得起來」是兩件事。這份文件的目的就是把這個落差固定地檢查掉。

---

## 一、推送前檢查清單

### 1. 絕對不要推上去的東西

| 項目 | 說明 |
|---|---|
| `.env` | 含 API 金鑰。已在 `.gitignore`，但改動 gitignore 時要再確認 |
| 真實合約檔 | `contracts/`、`contracts_deidentified/` |
| 向量庫 | `chroma_db/`（內容源自真實合約） |
| 使用者回饋 | `feedback/`（可能含合約片段） |
| 訓練產物 | `models/`、`corpus/`、`uploads/`、`outputs/` |

推送前快速確認：

```bash
git status --short          # 不該有上述任何項目
git diff --cached --stat    # 確認這次到底改了什麼
```

若懷疑機密曾被 commit 過：

```bash
git log --all --oneline -- .env "*key*" "*secret*"    # 應無輸出
grep -rnE "(sk-ant-|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,})" src frontend
```

> ⚠️ 若機密真的曾被 commit，**只刪檔案沒有用**，git 歷史仍留著。
> 必須改金鑰並改寫歷史（`git filter-repo`）。

### 2. 動到依賴時，一定要在乾淨環境驗證

只要改了 `requirements.txt`，**推送前先自己跑一次**，不要只依賴 CI：

```bash
cd /tmp && rm -rf ci_check
git clone <你的工作目錄> ci_check && cd ci_check
python3 -m venv v && ./v/bin/pip install -r requirements.txt
./v/bin/python -c "import src.api.main; print('OK')"
```

新增套件時請**確認該版本在 PyPI 上真的存在**：

```bash
pip index versions <套件名>
```

另外：**加進 requirements.txt 的套件，程式碼裡要真的有用到。**
先前的 `ckip-transformers` 就是全 codebase 零引用卻擋住所有人安裝。

### 3. 改到啟動流程時

`start_system.sh`、`auto_install.sh`、`*.command` 這幾個是新使用者的第一道門。
改動後要用**沒有 `venv/` 的乾淨 clone** 測，確認失敗時會給出看得懂的訊息，
而不是一大串 `ModuleNotFoundError`。

---

## 二、CI 涵蓋與不涵蓋的範圍

`.github/workflows/ci.yml` 會在每次 push 與 PR 時，於 Ubuntu 的乾淨環境
以 Python 3.11 / 3.12 各跑一輪。

### ✅ CI 會擋下的

- `pip install -r requirements.txt` 失敗（依賴版本不存在、衝突）
- `src.api.main` / `src.celery_app` / `frontend.backend_manager` import 失敗
- 去識別化壞掉（斷言姓名、身分證、電話、統編皆須被遮罩）
- spaCy 模型自動下載路徑失效

### ❌ CI 不涵蓋，改到請手動測

| 範圍 | 為什麼 | 怎麼測 |
|---|---|---|
| Celery / Redis 非同步流程 | CI 沒起 Redis | 本機起服務，跑一次上傳→查詢→下載 |
| RAG 對話與合約生成 | 需向量索引與 LLM 金鑰 | 建索引後於前端實際對話 |
| PDF / OCR | 需 poppler、tesseract | 各測一份文字型與掃描型 PDF |
| `.doc` 轉檔 | 需 LibreOffice | 上傳一份 `.doc` |
| Streamlit 前端 | 無介面測試 | `streamlit run frontend/app.py` |

**紅燈時**：到 https://github.com/TabrisYang/ContractAI/actions 點進去看是哪一步失敗。
不要用 `--no-verify` 或忽略紅燈硬推 —— 紅燈代表新使用者裝不起來。

---

## 三、修改後要同步更新的文件

程式碼改了，文件沒跟上，使用者一樣會卡住。對照表：

| 你改了什麼 | 要一起更新 |
|---|---|
| 新增／移除依賴 | `requirements.txt`、README「系統需求」 |
| 新增環境變數 | `.env.example`、`src/core/config.py` |
| 改動 API 端點 | README「使用說明」的 curl 範例 |
| 新增產生的目錄 | `.gitignore`、README「專案結構」 |
| 改動安裝步驟 | README「快速開始」、`auto_install.sh` |
| 支援的 Python 版本 | README、`auto_install.sh`、CI 的 matrix |

---

## 四、完整推送流程

```bash
# 1. 確認沒有敏感檔案
git status --short

# 2. 看清楚這次改了什麼
git diff

# 3. 若動到 requirements.txt → 先跑乾淨環境驗證（見上方第一節第 2 點）

# 4. commit（訊息說明「為什麼」，不只是「改了什麼」）
git add <明確指定檔案>        # 避免 git add . 誤加
git commit

# 5. 推送
git push origin main

# 6. 確認 CI 綠燈 —— 這一步不要省略
#    https://github.com/TabrisYang/ContractAI/actions
```

## 五、判斷「新使用者真的能用嗎」的黃金標準

有疑慮時，唯一可信的驗證方式是**從 GitHub 重新 clone**（不是用本機工作目錄），
建全新 venv，完整跑一次。本機的 venv、快取、`.env` 都會掩蓋問題。

```bash
cd /tmp && rm -rf verify
git clone https://github.com/TabrisYang/ContractAI.git verify && cd verify
python3 -m venv v && ./v/bin/pip install -r requirements.txt
# 起服務，實際上傳一份合約，確認遮罩結果正確
```
