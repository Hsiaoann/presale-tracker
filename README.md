# 雙北+青埔 預售案每日追蹤

每天自動抓樂屋網新建案「預售屋」列表，跟前一天比對出「新增案件」與「狀態變化（可能開始銷售、搶早鳥時機）」，依區域分組後推播到 LINE。跑在 GitHub Actions 上，不需要自己的電腦開機。

## 目前狀態（重要）

**樂屋網 adapter 已依實際 HTML 結構寫好並驗證通過**，解析、城市過濾、diff、分組、推播整條管線都用真實資料測過。因為我開發環境的網路限制連不到樂屋網，最後一哩「實際連線抓取」需要你在 GitHub Actions（或本地）跑第一次來確認——那邊沒有網路限制，可正常連樂屋網。

**住展找房（myhousingex.com.tw）是純 JavaScript 網站**，需要用 Playwright 才能抓，列為第二階段。第一版先用樂屋網跑起來，穩定後再加住展。adapters.py 底部已留好住展的實作骨架。

## 設定步驟

### 1. 註冊 GitHub 並建 repo
- 到 github.com 註冊（免費、免信用卡）
- New repository → 取名 `presale-tracker` → 公開或私有都可 → Create
- 把這包所有檔案上傳（含 `.github/workflows/daily.yml` 的資料夾結構）

### 2. 設定通知（Settings → Secrets and variables → Actions）

**先用 console 模式測試**：在 Variables 分頁新增 `NOTIFY_METHOD` = `console`。
這樣第一次跑只會把結果印在 Actions 的 log 裡，不推播，用來確認能正常抓到樂屋網資料。

**確認能抓到後改推播**：LINE Notify 已於 2025 年停止服務，用 LINE Messaging API：
1. 到 LINE Developers Console 建 Messaging API channel（免費）
2. 取得 Channel access token → 存為 secret `LINE_CHANNEL_TOKEN`
3. 加自己的 bot 好友、取得自己的 user id → 存為 secret `LINE_USER_ID`
4. 把 `NOTIFY_METHOD` 改成 `line_messaging`

> 關於「公開 repo 安全嗎」：token 存在 Secrets 是加密的，公開 repo 也讀不到，log 裡會自動遮成 `***`。只要不把 token 直接寫進程式碼，公開 repo 就安全。就算 token 外洩，也只是 bot 能被冒用發訊息，跟你個人 LINE 帳號無關，重新產生 token 即可作廢舊的。

### 3. 第一次執行
Actions 分頁 → 「每日預售案追蹤」→ Run workflow。
首次執行會建立基準線（不推播，避免一次通知全部既有案件），第二次起才推播新案。

### 4. 排程
`daily.yml` 預設每天台灣時間早上 8:00 跑。改時間改 cron 那行（用 UTC，台灣要減 8 小時）。

## 檔案說明

```
config.py        城市與區域分組設定（改範圍、改分組就改這裡）
models.py        資料結構、ehid唯一ID、區域分組
state.py         每日 diff 比對、狀態存檔
adapters.py      樂屋網抓取（已驗證）+ 住展骨架
notify.py        訊息格式化 + LINE 推播
main.py          主程式
requirements.txt 套件清單
.github/workflows/daily.yml   每日排程
seen_listings.json            執行後自動產生，勿手動改
```

## 改範圍 / 改分組

全在 `config.py`：
- 新北市已設六條區域分組線；青埔用關鍵字從桃園資料濾出。
- 改分組：改該城市的 `region_groups`。沒列到的行政區自動歸「其他」。
- 樂屋網列表是全台混排，adapter 會用行政區前綴自動篩出屬於各城市的案件。

## 疑難排解

- **log 顯示抓到 0 筆**：可能樂屋網改版或該頁需要 JS。先確認 `RAKUYA_MAX_PAGES` 頁數、再檢查 adapter 的解析。
- **翻頁太多/太少**：改 config 的 `RAKUYA_MAX_PAGES`（目前 13，依實際總頁數調整）。
- **想加住展**：見 adapters.py 底部 Playwright 骨架，需在 requirements 加 playwright、workflow 加 `playwright install chromium`。

## 建照查詢層（領先指標，尚未自動化）

`config.py` 的 `BUILDING_PERMIT_SOURCES` 放了新北、桃園官方建照查詢入口，建議每週手動查或之後另寫週排程。建照到公開銷售常隔數月，不需每天跑。

## 注意事項

- 預設每天一次、每次請求間隔 2 秒，對網站負擔很低，請勿調高頻率。
- GitHub Actions 對公開 repo 免費無上限；私有 repo 每月 2000 分鐘免費，此用途月用不到 100 分鐘。
