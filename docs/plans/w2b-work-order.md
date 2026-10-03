# W2b 功能擴展工作單

W2a 的 184/27/157 是誠實起點，不是完整 migration。取得 W2a 修後雙審後，用 worker 接續，禁止把本表當完成證據。

## 目標

依完整 source inventory 與 handler 行為，盡可能完成其餘正常產品功能的 audited support。不得透過刪除 inventory、將 unsafe 自動視為 read-only、或僅把全部標示 deferred 而宣稱完成。

1. 每類列 source exact schema／必要參數／真正 action(effect) 分類及試驗案例。
2. 所有新增 writer 預設 deny；管理員需能明確按工具（混合則按 operation）opt in。不得將舊全域 writes_enabled=true 視作自動批准本次新增所有工具。
3. 必要時 schema migration 加 per-tool write grants；保留舊 token/backend/disabled 與已實際支援 writer 的既有語義，但新增 surface 不繼承默示授權。損壞/未來/未知tool grant fail closed。
4. Mixed read/write parameter 的合法 enum 都要從 handler 實證；未定 action 拒絕，不能以工具name/category猜。廣義 executor/agent/code/SQL 要整體視write且明確強風險提示，不能用method看似read就降權。
5. Schemas 與實際handler defaults一致；追加/未知參數拒絕，不得信任upstream readOnlyHint作唯一授權依據。Metadata不代表body已被禁止。
6. 後端 egress 繼承已修的固定origin/path、DNS pin、metadata/redirect/TLS policy；新handler可能繞過原client時必須補管線或明示不支援，不能把新功能繞到未受控network/file/shell。
7. credentials、backend config、private session/file內容等敏感輸出要明確view權限與清理；需要新schema或safe model/field/path範圍才可開。沒有安全契約則逐項列出真正阻礙/剩餘設計，而非無理由延期。
8. 新功能必須測：default deny，explicit opt-in allowed，disabled direct-call deny、unknown拒絕、既有session即時生效；mock/backend counter證明deny零副作用。寫入測試只對owned fake backend。
9. 每類至少有read與確實可啟用writer證據（如該來源真的有writer）；不能每類只有health/list還聲稱功能遷移。
10. 真實source/runtime schema inventory和漂移測試保持；現有全部回歸不退步。修後雙審才進W3。

## 可如實延期但不得隱藏

無法本批安全限制的檔案內容/任意程式執行/跨instance/任意HTTP/非HA環境專屬能力，需逐tool列準確原因及所需增補。報告應給出逐類 counts與已覆蓋標準功能；完整產品claim仍被未解功能缺口阻擋。不要為了提高counts而虛構tool、handler、test或成功回應。
