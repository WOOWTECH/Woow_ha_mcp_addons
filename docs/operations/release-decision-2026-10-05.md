# 0.1.0 公開決定（2026-10-05）

**決定人：專案負責人**（Claude 交付線對話中選擇「公開，HA 免權杖」與「一個 repo 放七個 add-on」）。
這是負責人的明確決定，取代原設計「來源授權全部清完才公開」的順序；`RELEASE-GATES.json` 的 manual
gates 未被自動改寫，仍由整合者依此紀錄處理。

## 公開範圍

- GitHub repo `WOOWTECH/Woow_ha_mcp_addons`（含完整 Git 歷史）。Gitea 為 GitHub 的唯讀拉取鏡像。
- 七個 amd64 映像 `ghcr.io/woowtech/amd64-mcp-<product>:0.1.0`：推送的是 supply-chain gate 已測的同一
  image ID（候選 `f75fe32b2f79b4cf9f99563667439a94db8b1d82`，不重建）。
- HA 以商店 repository 安裝；`config.yaml` 的 `image` 與 version 不變。

## 公開前已通過

- 七支真 P1–P5：build、container/mock 驗收、source／history／image／evidence secret 掃描、SBOM、CVE、
  license 全數通過（證據由 Claude 交付線保存）。
- secret 例外只限負責人逐項核准的精確值（`packaging/secret-triage.json`）；source／history 為零容忍。
- 漏洞政策：只有上游明確標示 not-fixed／wont-fix 的 High／Critical／Unknown 不擋，仍完整記錄；
  有修補的一律擋（libpcre2 以固定 Debian security 快照升級）。
- 授權：每映像依賴清單見 [docs/licenses](../licenses/README.md)；MPL-2.0 原始碼附在 release `v0.1.0`。

## 負責人接受的剩餘風險

- OpenDesign 原上游權利人尚未確認。
- 公開的 Git 歷史含內部營運文件曾提及的內部主機名稱與路徑（非憑證；現行文件已移除）。
- 映像為 experimental：尚無 HA 實機驗收、真後端 E2E、aarch64；工具僅部分支援（71/184 已審）。
- 映像內 `THIRD_PARTY_NOTICES.md` 為建置當時版本；最新授權說明以 repo 的 `docs/licenses/` 為準。

## 回復

公開後無法撤回已被下載的內容。若需停止散布：GitHub repo 改回私有、GHCR packages 改私有或刪除
`0.1.0` 版本、從 HA 商店移除 repository；已安裝的 app 不受影響，需逐台處理。
