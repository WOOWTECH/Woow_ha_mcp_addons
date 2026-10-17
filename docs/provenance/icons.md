# Add-on 圖示來源

每支 MCP Server add-on 的 `icon.png`／`logo.png` 都和它所連接的軟體相同（負責人 2026-10-09 決定）。
六支直接取自 [WOOWTECH/Woow_HA_App_Store](https://github.com/WOOWTECH/Woow_HA_App_Store) 裡對應後端 add-on 的同名檔案（逐位元相同）；
LiteLLM 在商店裡沒有後端 add-on，取自 LiteLLM 官方 repo（MIT）。
圖示與商標屬於各軟體的權利人，這裡只用來標示 add-on 所連接的軟體；本專案與這些軟體的開發者沒有隸屬關係。

| Add-on | 軟體 | 來源 | `icon.png` sha256 | `logo.png` sha256 |
|---|---|---|---|---|
| `addons/n8n` | n8n | Store `682d595` 的 [Woow n8n](https://github.com/WOOWTECH/Woow_HA_App_Store/tree/682d595f03de2b1fa70812aa0120db5052a7b5d0/n8n)（`n8n/icon.png`、`n8n/logo.png`） | `d26e7927bf12d8a33808b17f4c3b101722ee1f06ddd17f839ba719579979339a` | `20e3252e6450b4e3483b72d53a4ab8d6c757ea6252af6b919fe35cda1cd80d54` |
| `addons/odoo` | Odoo | Store `682d595` 的 [Woow Odoo 18](https://github.com/WOOWTECH/Woow_HA_App_Store/tree/682d595f03de2b1fa70812aa0120db5052a7b5d0/odoo18ce)（`odoo18ce/icon.png`、`odoo18ce/logo.png`） | `ea79692f3e825368f68911699cf56ef76b690a9e50cb0d2518725cb3d41b5571` | `d6cc56bb513d2889d1c29931eeca25b383454d0b22d971291095346154627e6b` |
| `addons/hermes` | Hermes Agent | Store `682d595` 的 [Woow Hermes Agent](https://github.com/WOOWTECH/Woow_HA_App_Store/tree/682d595f03de2b1fa70812aa0120db5052a7b5d0/woow-hermes)（`woow-hermes/icon.png`、`woow-hermes/logo.png`） | `799c862dca5cb00213ef6c1a61ffb22909d0d9b4ef7cf25ff7a5a03f8dbde9e7` | `53983554c85c49c5584892de02ca9959b71cedfb218d3fe66d3b27bb827fc228` |
| `addons/opendesign` | OpenDesign | Store `682d595` 的 [Woow HA OpenDesign](https://github.com/WOOWTECH/Woow_HA_App_Store/tree/682d595f03de2b1fa70812aa0120db5052a7b5d0/woow_ha_opendesign)（`woow_ha_opendesign/icon.png`、`woow_ha_opendesign/logo.png`） | `4b1c8f1948898dbe7de912c84cf98a24d9166c080184cf49343c203b73e04d0c` | `a30792e35ad10fcb9b057f8c659002b83dc1eaea409de9bbd671d23ee8822df3` |
| `addons/emqx` | EMQX | Store `682d595` 的 [Woow EMQX](https://github.com/WOOWTECH/Woow_HA_App_Store/tree/682d595f03de2b1fa70812aa0120db5052a7b5d0/emqx)（`emqx/icon.png`、`emqx/logo.png`） | `0ca9e6cf4c66ae5fe009562f49434b96a5f019629fa9b2399ee05d65331673f9` | `94507111ec0f00bc0afdbfeda64bc4c9847bc07cd9897577d1aa324c79ca2642` |
| `addons/nextcloud` | Nextcloud | Store `682d595` 的 [Woow Nextcloud Office](https://github.com/WOOWTECH/Woow_HA_App_Store/tree/682d595f03de2b1fa70812aa0120db5052a7b5d0/woow-nextcloud-office)（`woow-nextcloud-office/icon.png`、`woow-nextcloud-office/logo.png`） | `c1be2c912b0d4c80fedbfbb105b8659219dbe9b0665bd71a93b61ad1323b21f5` | `2e9b712a149ed8190d6a9313886a7286ebd505e3e3f8c62920cbd8ccab59b41f` |
| `addons/litellm` | LiteLLM | [BerriAI/litellm](https://github.com/BerriAI/litellm/tree/a6f6c64b6ec37782d871b7cda2f2fd0d9202d85c) `a6f6c64`（`litellm/proxy/logo_monogram.png` → icon、`litellm/proxy/logo.png` → logo） | `5903e2fcc009a17c7f518db364fafccdca23192206419966585039ffbb635df0` | `494961873b06061c00d741e41d1e7fec948ff3beba509766ffa02199f8230cb1` |

後端 add-on 換了圖示時，照上表重新複製、更新雜湊即可；圖示不在映像內，改圖示不需要重建映像。
