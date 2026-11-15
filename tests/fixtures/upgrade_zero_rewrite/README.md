# 升級零改寫的 state 樣本（HM-07，2026-11-14）

八個產品各一份 `state.json`，內容是 `bb48449` 的程式為「已裝好、已設定」的 add-on 寫出的位元組，給
`tests/test_upgrade_zero_rewrite.py` 用：新程式在這份資料上啟動，`state.json` 一個位元組都不能變、資料目錄不能多出
任何多帳號的檔（計畫 §7.1、§7.3；不變式 I6）。

- 怎麼做出來的：用 `git archive bb48449 packages/mcp-admin-core` 取出的程式（不是本分支的程式），照 add-on 的做法：
  `ProductStore` 第一次開機寫出新 state，再用面板的存檔方式（`Store.update`）存後端、政策（寫入關、停用兩支工具、
  三個寫入授權、一條禁止的操作）、endpoint 與產品自己的設定（Odoo 四個子程式開關與方法清單、n8n session 與
  MCP access token），再輪替一次 token（`change_token`）。之後把 token、child token、遮罩過的舊 token 換成同格式的
  固定假值（`T`×43、`C`×43、`TTTT`＋20 個 `*`＋`TTTT`），輪替時間固定成 `2026-11-14T00:00:00+00:00`，再用同一份程式
  重新序列化（`model_dump_json`，就是 `Store._write` 寫的東西）。產生腳本只跑一次，不在本 repo。
- 本分支的程式用同一個做法產生的位元組完全相同（產生時比對過）。
- 正規化規則同 `tests/fixtures/owner_defaults/README.md`：憑證都是 `DUMMY-…`、網址都是 `.invalid`，沒有任何真的秘密。
- 檔案就是寫進磁碟的原始位元組：緊湊 JSON、欄位照模型順序、結尾沒有換行。改了任何一個位元組，這個測試就不再代表
  `bb48449` 寫出的資料；要換成新版本寫出的樣本時，另開新檔並寫明是哪個 commit 寫的。
