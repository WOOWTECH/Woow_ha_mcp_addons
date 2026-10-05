# n8n 試點：逐步指令（woowtech-ha）

**狀態：指令準備，未執行。** 每個 H 步驟要先取得專案負責人對「那一步」的批准；R 步驟只在一次性 builder VM
與 registry 內。設計與理由見 [私有映像交付設計](n8n-pilot-image-delivery.md)、[試點程序](n8n-haos-pilot.md)。
下文 `<SHA>` 是通過 gate 的候選 commit，`<SHA12>` 是其前 12 碼，`<IMAGE_ID>` 是 P3 的 image ID
（classic store：config digest）。`ha` 指令在 HA 的 SSH add-on 內執行（`ssh woowtech-ssh.woowtech.io`）。

## 0. 前提（缺一不可）

- 候選 `<SHA>` 的真 P1–P5 全部 exit 0（不是模擬）；P5 evidence 已拉回並存證。
- P7 唯讀檢查在試點當天重跑一次（版本、slug／目錄無衝突、8081 未佔用）。
- 負責人已備妥：近期完整備份（或批准第 4 步）、兩個 Gitea token、n8n 測試 API key。

## 1. 憑證交付（負責人在自己的終端機做，不經對話）

token 只寫進 pod 上的 0600 檔案；不要貼進聊天或 `!` 指令（會留在對話紀錄）。在能 `kubectl` 的機器上：

```sh
POD=$(kubectl --context woow-k3s -n pi-agent-woow get pod -l app=pi-agent -o name | head -1)   # 容器名稱是 pi-web
DIR=/data/pi-agent/home/work/mcp-haos-team-runtime/claude-delivery/vm-access
# 依序貼上（兩行：username、token），Ctrl-D 結束；三個檔案各做一次
kubectl --context woow-k3s -n pi-agent-woow exec -i "$POD" -c pi-web -- sh -c "umask 077; cat > $DIR/gitea-push.cred"   # write:package
kubectl --context woow-k3s -n pi-agent-woow exec -i "$POD" -c pi-web -- sh -c "umask 077; cat > $DIR/gitea-pull.cred"   # read:package
kubectl --context woow-k3s -n pi-agent-woow exec -i "$POD" -c pi-web -- sh -c "umask 077; cat > $DIR/n8n-test.key"      # 一行：n8n API key
```

## 2. R2 推送已測映像（VM，不重建）

```sh
VM=$DIR/vssh-pf
$VM 'test "$(docker image inspect local/mcp-n8n:0.1.0 --format {{.Id}})" = "<IMAGE_ID>"'
sed -n 2p $DIR/gitea-push.cred | $VM "docker login git-prod.woowtech.io -u $(sed -n 1p $DIR/gitea-push.cred) --password-stdin"
$VM 'REF=git-prod.woowtech.io/ha-components/pilot-<SHA12>/amd64-mcp-n8n:0.1.0;
     docker tag <IMAGE_ID> $REF && docker push $REF; rc=$?; docker logout git-prod.woowtech.io; exit $rc'
```

推送後立刻撤銷 push token。若 Gitea 拒絕巢狀名稱，停止，改扁平名稱並重新審查 `pilot_variant.py`。

## 3. 讀回核對與收據（VM）

```sh
cat $DIR/gitea-pull.cred | $VM 'umask 077; cat > /srv/work/pull.cred'
$VM 'cd /srv/work && python3 tools2/packaging/registry_fetch.py \
       git-prod.woowtech.io/ha-components/pilot-<SHA12>/amd64-mcp-n8n:0.1.0 pull.cred fetched-<SHA12>;
     rm -f pull.cred'
# subject：image_store=classic、image_id=<IMAGE_ID>、diff_ids 取自 P5 subject.json
$VM 'cd /srv/work && python3 tools2/packaging/delivery_receipt.py check "$(cat fetched-<SHA12>/manifest.digest)" \
       fetched-<SHA12>/manifest.bin fetched-<SHA12>/config.bin subject.json fetched-<SHA12>/blobs'
```

全部 layer 必須 `bytes-verified`；任一不符就停止，不安裝。再以 `delivery_receipt.py assemble` 綁定
source receipt、variant receipt（`pilot_variant.py` 產物）、subject、ref 與子證據。

## 4. 完整備份（HA，需批准）

```sh
ha backups new --name "before-woow-mcp-n8n-pilot-$(date +%Y%m%d)"
ha backups --raw-json | jq -r '.data.backups | sort_by(.date) | last | "\(.date) \(.type) \(.name)"'
```

只建立備份，不還原、不刪舊備份。type 必須是 `full`。

## 5. H1 Supervisor 拉取憑證（HA，需批准）

密碼經 stdin 傳給 Supervisor API，不出現在指令列：

```sh
python3 -c 'import json,sys;u,t=open(sys.argv[1]).read().split("\n")[:2];print(json.dumps({"git-prod.woowtech.io":{"username":u.strip(),"password":t.strip()}}))' \
  $DIR/gitea-pull.cred | ssh woowtech-ssh.woowtech.io \
  'curl -sf -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" -H "Content-Type: application/json" --data-binary @- http://supervisor/docker/registries && echo H1-OK'
ssh woowtech-ssh.woowtech.io 'ha docker registries --raw-json | jq -r ".data.registries | keys[]"'
```

回復：`curl -sf -X DELETE -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/docker/registries/git-prod.woowtech.io`，
再確認清單已無此項。

## 6. H2 放入本地 app 目錄（HA，需批准）

```sh
ssh woowtech-ssh.woowtech.io 'test ! -e /addons/woow_mcp_n8n_pilot' || exit 1
$VM 'tar -C /srv/work/pilot-<SHA12> -cf - woow_mcp_n8n_pilot' | ssh woowtech-ssh.woowtech.io 'tar -C /addons -xf - && ha store reload'
ssh woowtech-ssh.woowtech.io 'ha apps info local_woow_mcp_n8n_pilot --raw-json | jq -r ".data | \"\(.name) \(.version) \(.image)\""'
```

回復：`rm -rf /addons/woow_mcp_n8n_pilot && ha store reload`。

## 7. H3 安裝與啟動（HA，需批准）

```sh
ssh woowtech-ssh.woowtech.io 'ha apps install local_woow_mcp_n8n_pilot && ha apps start local_woow_mcp_n8n_pilot'
ssh woowtech-ssh.woowtech.io 'ha apps info local_woow_mcp_n8n_pilot --raw-json | jq ".data | {state, version, ip_address, ingress_url}"'
ssh woowtech-ssh.woowtech.io 'ha apps logs local_woow_mcp_n8n_pilot | tail -50'
```

日誌不得出現 token／Authorization／backend body。安裝前後各讀一次 registry manifest digest（第 3 步），三次一致。
backend 設定由管理員在 Ingress 面板填 `http://1b7b4ce7-woow-n8n:5678` 與 n8n-test.key。

## 8. P9 實測

依 [試點程序](n8n-haos-pilot.md) P9 矩陣逐項記錄；只用無副作用工具；寫入防護測試要確認 n8n 端無變化。

## 9. H4 收尾與回復（每步各自確認）

1. `ha apps stop local_woow_mcp_n8n_pilot`
2. 解除安裝會刪除它的 `/data`：先取得負責人明確確認，並完成受控 export 或該 app 的 cold backup
   （`ha backups new --apps local_woow_mcp_n8n_pilot --name ...`），記錄 backup slug 與保留決定。
3. `ha apps uninstall local_woow_mcp_n8n_pilot`；`rm -rf /addons/woow_mcp_n8n_pilot && ha store reload`
4. 刪除 Supervisor registry（第 5 步回復），在 Gitea 撤銷 pull token；刪除 pod 上三個憑證檔。
5. 在 n8n 撤銷測試 API key；記錄實際中斷時間與結果。

既有 n8n、Core、Supervisor、k3s 均未修改。
