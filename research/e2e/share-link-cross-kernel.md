# 跨内核端到端验证：「分享链接」那些问题是 X 独有，还是 M / SB 也有？

**日期**：2026-10-10（PDT / UTC-7）
**方法**：真机 E2E。X 的 5 个问题来自 `interactive-all-protocol-cdn.md`（本轮用**同一套 harness** 复现了一遍作对照），M 与 SB 各自走**自己真实的分享机制**，在 CC 上用真内核客户端拉取并实测连通。
**判定纪律**：每格必须有命令 + 原文。没跑到证据的一律 UNKNOWN，不写「应该没有」。

---

## 0. 一句话结论（先给答案）

| 问题 | X 内核 | M 内核 | SB 内核 | 结论 |
|---|---|---|---|---|
| 1 分享层丢 SNI | ✅**有** | ❌**没有** | ❌**没有** | **X 独有** |
| 2 CDN 端口/目标不一致 | ✅**有**（生成即死链） | ⚠️**部分**（内容对；**链接产物 10/12 指向无人监听的端口**） | ❌**没有**（13/13 端口在监听） | **X 独有该形态；M 是同后果、不同成因；SB 无** |
| 3 公网 CA 也 pin | ✅**有** | ❌**没有**（只在自签节点 pin） | ❌**没有**（只在 `CERT_TRUSTED=false` 时 pin） | **X 独有** |
| 4 客户端解析丢 reality 参数 | ✅**有**（`xbd parse_trojan`） | ❌**没有** | ❌**没有** | **X 独有** |
| 5 硬编码 `obfs=none` 让订阅挂掉 | ✅**有** | ✅**有** | ✅**有** | **生态共有（三家全中）** |

**额外发现（本轮新查出来的）**
- **M 的分享订阅生成当前 100% 失败**（`build_sub.py` 名字过滤集合交集 = 0/19）→ 面板报「生成分享内容失败 (没有可分享的节点?)」，已发出的分享内容因此**永久冻结在陈旧快照**上（快照里的端口无人监听）。这是 M 侧最严重的一处，性质与 X 的 P0-2/P0-3 同级但成因完全不同。
- **M 的 `out/*_share-*.txt` 12 条 URL 链接里 10 条端口无监听**（陈旧产物）。
- **M 的客户端不吃自己的 URL 分享链接**（只认原生 `proxies:` YAML）。
- SB 侧**没有**发现分享层新问题。

---

## 1. 环境与版本（实测取值）

| 角色 | 主机 | 关键版本 |
|---|---|---|
| RN（服务端） | `racknerd-75e0e8` / 107.173.154.178 | M `mihomo -d /root/catmi/mihomo/conf`（`Mihomo Meta v1.19.32`，`src/VERSION`=`2d4a088c71b2`）；SB `sing-box -D /root/catmi/sing-box -C .../config run`（`1.14.2`） |
| CC（客户端） | `armbian` / 192.168.1.178 | **M 客户端已装**：`/root/catmi/mihomo-client/mihomo` = `Mihomo Meta v1.19.32 linux arm64`，`mihomo-client.service` active；**SB 客户端已装**：`/opt/sb-client/core/sing-box` = `sing-box 1.14.2 linux/arm64`，`sb-client.service` active |
| 公共服务 | RN `:9443` | `proxy-share-service 1.1.0`（M / SB / X 共用，provider 隔离） |
| CCDNS | — | `hxicc.catmicos.dpdns.org` → **Cloudflare 边缘**（`2606:4700:3031::ac43:b13e`），同时源站 nginx `0.0.0.0:443` 也是真实入口 |

**基线（开工前，已核对 / 收工后复核一致）**
```
# RN
$ systemctl is-active xrayls mihomo sing-box nginx proxy-share-service
active active active active active
PIDs mihomo=119320 sing-box=60510 nginx=958 xrayls=165517
$ ss -tulnH | wc -l
90
# CC
$ systemctl is-active mihomo-client sb-client
active active        # PIDs 1364829 / 1444214，全程未变
$ curl -s https://api.ipify.org   # CC 自身出口（经 RN 观测到的源 IP）
183.210.249.163      # ← 判据：实测出口 IP ≠ 这个值才算真的走了节点
```

---

## 2. 三家「真实的分享机制」是什么（先摸清，再测）

### 2.1 X（对照基准，来自上一轮报告 + 本轮复验）
- **发布**：面板「分享管理 → 生成分享链接」→ 内容交给公共 `proxy-share-service`（provider=`xray`）。URL 形如 `http://107.173.154.178:9443/share/<token>`。
- **内容格式**：**base64 的一整行 URI 列表**（5 条 `hysteria2:// ss:// trojan:// vless://`）。
- **产物**：`/root/catmi/xray/out/*_share-*.txt`（单节点 URL 链接）、`out/*_client-*.json`、`out/share/<tag>.json`（分享元数据）。

### 2.2 M（mihomo）— 一句话：**把自己原生的 `proxies:` YAML 当订阅，经 9443 公共服务发**
- **发布**：`src/share/share.sh: share_create()` → `_share_make_content()` → `python3 src/share/build_sub.py --out-dir out --conf-dir conf --tag <all|协议桶>` → 交给 `share_client.py`（provider=`mihomo`）存进 9443。
- **URL**：`http://<share_addr>:9443/share/<token>`，`share_addr.txt` = `107.173.154.178`。
- **内容格式**：Mihomo 原生 `proxies:` YAML（客户端零转换，直接做 `type: file` 的 proxy-provider）。
- **产物**：`out/<proto>_client-NN.yaml`（客户端片段）、`out/<proto>_share-NN.txt`（单节点 URL 链接）、`out/share_tag-*.txt`（URL）。
- **另有**：`src/share/lan_server.py` / `lan_config.py`（局域网分发）、`mihomo-client` 面板（客户端侧）。

### 2.3 SB（sing-box）— 一句话：**把 `out/sb_client-<tag>.json` 整个客户端配置当分享内容，经同一个 9443 发**
- **发布**：`conf/share.sh create <tag> [max_uses] [ttl_hours]` → `_sb_share_content_file()` = `cp out/sb_client-<tag>.json` → `share_client.py`（provider=`sing-box`）。
- **URL**：`http://<sb_addr_current>:9443/share/<token>`（本次探测到 IPv6 形式，IPv4 同样可用）。
- **内容格式**：sing-box 完整客户端 profile（`{"outbounds":[…],"route":{"final":"PROXY"}}`，含 selector/urltest）。
- **产物**：`out/sb_client-*.json`（客户端配置）、`out/sb_share-*.txt`（单节点 URL 链接）、`out/sb_links-all.txt`（全量 URL 链接）、`out/sb_meta-*.json`。

> 三家共用同一个 `proxy-share-service`（`:9443`），但 **provider 目录隔离**，内容各家自产、服务不解析。

---

## 3. 实测：CC 侧拉取 + 真内核连通

### 3.1 实测方法与判据
- **判据**：`https://www.gstatic.com/generate_204` 的 HTTP 码 + 耗时；出口 IP 用 `http://ip-api.com/line/?fields=query`；**出口 IP ≠ 183.210.249.163（CC 自身公网 IP）才算真的过节点**。
- **M 侧**：CC 上跑 **M 自己的客户端**（`/root/catmi/mihomo-client/src/client.sh`），用 `CLI_ROOT=/tmp/... CLI_SERVICE=mihomo-e2e-tmp` 隔离到 `/tmp`（`CLI_SERVICE` 指向不存在的 unit ⇒ `svc_active=false` ⇒ 绝不重启生产 `mihomo-client`），HTTP 拉 M 的分享 URL → 自动写成 proxy-provider → `mihomo -t` 三道校验通过 → 再用 `mihomo -d <tmp>/conf` 起临时实例逐节点实测。**生产 `mihomo-client` PID 全程 1364829 未变。**
- **SB 侧**：CC 上用 `curl`（**与 `sb-client add_node` 完全同一条命令语义**：`curl -sSL -o f -w %{http_code} --max-time N <url>`）拉分享 URL，再用 `sing-box check -c`（**与 `sb-client cfg_check` 同一条命令**）校验，然后用真 `sing-box` 内核逐 outbound 实测。**未运行 `sb-client add`**——它的 `apply_change()` 会 `do_start` 生产 unit，为避免碰生产服务，改用等价的最小步骤（详见 §7 说明）。
- **X 侧**：用**同一套 mihomo harness** 复现，避免「X 用 xbd 测、M/SB 用 mihomo 测」的口径不一致。

### 3.2 M：**19/19 节点实测全通**
拉取（CC，M 自己的客户端 + M 自己的分享 URL）：
```
$ cd /root/catmi/mihomo-client/src
$ CLI_ROOT=/tmp/e2e-share/mcli CLI_SERVICE=mihomo-e2e-tmp \
  printf '%s\n' "http://107.173.154.178:9443/share/55026a3a49b9c47cb1695ebc8dc9d53f" "2" "" \
  | bash -c "source ./client.sh; node_add"
[Info] 正在拉取...
[OK] 已写入 /tmp/e2e-share/mcli/conf/providers/55026a3a49b9c47cb1695ebc8dc9d53f.yaml (19 个节点)
[Info] 已剔除 6 个内核不认的字段
[OK] 已给 19 个节点加上前缀 [55026a-]
[OK] 生成 /tmp/e2e-share/mcli/conf/config.yaml (1 个 provider)
[OK] 配置已生成并通过全部校验 (服务未运行, 启动后生效)
$ systemctl show -p MainPID --value mihomo-client
1364829        # ← 与开工前一致
```
逐节点实测（真 mihomo 内核，经 mixed-port 10808→17890）：
```
group '107.173.154.178' -> 19 nodes
🇺🇸 55026a-mAnyTLS02-TLS          http=204|2.409711   exit_ip=104.28.201.73
🇺🇸 55026a-mAnyTLS03-TLS          http=204|1.325352   exit_ip=104.28.201.73
🇺🇸 55026a-mAnyTLS01-TLS          http=204|1.336820   exit_ip=104.28.201.73
🇺🇸 55026a-mHysteria202-TLS       http=204|1.764264   exit_ip=104.28.233.73
🇺🇸 55026a-mHysteria201-TLS       http=204|2.286031   exit_ip=104.28.201.73
🇺🇸 55026a-mVLESS01-REALITY       http=204|1.720276   exit_ip=104.28.201.73
🇺🇸 55026a-mVLESS02-REALITY-gRPC  http=204|1.523321   exit_ip=104.28.201.73
🇺🇸 55026a-mVLESS03-REALITY-XHTTP http=204|1.803901   exit_ip=104.28.201.73
🇺🇸 55026a-mTrojan05-CDN-gRPC     http=204|1.251709   exit_ip=104.28.201.73
🇺🇸 55026a-mTrojan04-CDN-WS       http=204|4.000168   exit_ip=104.28.201.73
🇺🇸 55026a-mTrojan01-REALITY      http=204|1.053480   exit_ip=104.28.201.73
🇺🇸 55026a-mTrojan02-REALITY-gRPC http=204|1.669617   exit_ip=104.28.201.73
🇺🇸 55026a-mTrojan03-TLS          http=204|0.935849   exit_ip=104.28.201.73
🇺🇸 55026a-mTUIC01-TLS            http=204|0.914776   exit_ip=104.28.201.73
🇺🇸 55026a-mVLESS05-CDN-gRPC      http=204|0.970980   exit_ip=104.28.201.73
🇺🇸 55026a-mVLESS04-CDN-WS        http=204|3.731437   exit_ip=104.28.201.73
🇺🇸 55026a-mVLESS01-TLS-WS        http=204|3.165405   exit_ip=104.28.201.73
🇺🇸 55026a-mVLESS03-TLS-XHTTP-CDN http=204|3.300616   exit_ip=104.28.201.73
🇺🇸 55026a-mVLESS02-TLS-XHTTP     http=204|1.343967   exit_ip=104.28.201.73
```
→ **19/19 = 204**，出口 IP `104.28.201.73 / 104.28.233.73`（RN 的 CF 出口）≠ CC 自身 `183.210.249.163`。**含 5 个 CDN 节点（domain:443）与 3 个 REALITY 节点全部通过。**

> ⚠️ **口径声明（必读）**：M 的**服务端分享生成当前是坏的**（见 §5 P-M1）。上表用的分享内容是**用 M 自己的生成器 `src/share/build_sub.py`（M 自己的产物、M 自己的代码）生成的**，只是**绕过了那个已经证实会 100% 剔除节点的 `--conf-dir` 过滤参数**；随后用 **M 自己的 `share_client.py create`（provider=mihomo）** 发布、用 **M 自己的客户端**通过 HTTP 拉取。除这一处被文档化的绕过，链路其余环节都是 M 的原生代码。若按面板原样走，第一步就报错、根本拿不到内容（原文见 §5）。

### 3.3 SB：**13/13 真实节点实测全通**
拉取（CC，`sb-client add_node` 的同款 curl）：
```
$ for pair in all:676845724776bc0d2e065209147d030e reality01-REALITY:41bedf894ff070b97abb61e42e7bf32d \
              vless01-TLS-CDN:8db5fb4e22d7f37fd141b2c14c562662 hysteria201-TLS:faec5effbf0e62647efd3e915df1cead; do
    curl -sSL -o "$t.json" -w "%{http_code}" --max-time 20 "http://107.173.154.178:9443/share/$tok"; done
all              -> code=200 size=7360
reality01-REALITY-> code=200 size=594
vless01-TLS-CDN  -> code=200 size=718
hysteria201-TLS  -> code=200 size=401
$ /opt/sb-client/core/sing-box check -c <每个>.json     # 全部无输出 = 通过
```
逐 outbound 实测（真 sing-box 1.14.2 内核，`route.final=<tag>`）：
```
### all.json: 14 outbound(s)
  rn-anytls01-TLS        http=204|2.148706   exit_ip=104.28.201.73
  rn-anytls02-REALITY    http=204|0.658653   exit_ip=104.28.201.73
  rn-hysteria201-TLS     http=204|0.466298   exit_ip=104.28.201.73
  rn-naive01-TLS         http=204|0.487375   exit_ip=104.28.201.73
  rn-reality01-REALITY   http=204|2.335398   exit_ip=104.28.201.73
  rn-shadowsocks01-plain http=204|0.543451   exit_ip=104.28.201.73
  rn-shadowtls01-TLS-out http=000|0.730503   exit_ip=<none>      ← shadowtls 内层 helper，不是独立节点
  rn-shadowtls01-TLS     http=204|1.043194   exit_ip=104.28.201.73 ← 真正的节点（shadowsocks detour→shadowtls）
  rn-trojan01-TLS-CDN    http=204|1.600903   exit_ip=104.28.201.73
  rn-trojan02-REALITY    http=204|1.543546   exit_ip=104.28.201.73
  rn-tuic01-TLS          http=204|0.556843   exit_ip=104.28.201.73
  rn-vless01-TLS-CDN     http=204|2.488436   exit_ip=104.28.201.73
  rn-vmess01-TLS-CDN     http=204|3.855817   exit_ip=104.28.201.73
  rn-vmess02-REALITY     http=204|3.258959   exit_ip=104.28.201.73
### 单节点分享
  reality01-REALITY   http=204|3.140529
  vless01-TLS-CDN     http=204|2.261043
  hysteria201-TLS     http=204|1.577543
```
→ **13/13 真实节点 204**（14 个 outbound 里唯一 000 的是 shadowtls 的内层 helper，按设计不是可直接出网的节点；其外层节点 204 通过）。

### 3.4 X：同一套 harness 复现（口径对齐）
把 X 已发布的分享订阅（9443 上 `f64f61ce…`，944 字节 base64）喂给同一个 mihomo：
```
$ base64 -d x_sub.b64
hysteria2://05615ce2-...@107.173.154.178:29604?sni=107.173.154.178&insecure=0#hysteria-04
ss://MjAyMi1ibGFrZTMtYWVzLTI1Ni1nY206...@107.173.154.178:29603#SS2022-02
trojan://LV7CpzX9Jc8vWuhP0YV0@107.173.154.178:29602?security=reality&type=tcp&sni=audio-ssl.itunes.apple.com&fp=chrome&sid=b860a9f0&pbk=GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU#TROJAN-03
vless://1fa7c981-...@107.173.154.178:8443?encryption=none&security=tls&type=xhttp&path=%2FaVCR3P0A%2F#vless-xhttp07
vless://278502fc-...@107.173.154.178:29601?encryption=none&security=tls&type=ws&path=%2F8KLD3cNj#vless-xhttp08
      ↑ 两条 vless 都没有 sni= ；hy2 的 sni 是 IP
$ bash mh_e2e.sh x_sub_raw x_sub.b64 raw
  provider 't' node count = 5
    hysteria-04    http=000|5.002685   exit_ip=<none>
    SS2022-02      http=204|0.703201   exit_ip=104.28.195.192   ← 唯一通的
    TROJAN-03      http=000|0.878677   exit_ip=<none>
    vless-xhttp07  http=000|5.003627   exit_ip=<none>
    vless-xhttp08  http=000|5.003688   exit_ip=<none>
# run.log 原文（连续刷屏）
level=warning msg="[TCP] dial P (match Match/) ... --> www.gstatic.com:443 error: CRYPTO_ERROR 0x12a (local):
  tls: failed to verify certificate: x509: cannot validate certificate for 107.173.154.178 because it doesn't contain any IP SANs"
```
**对照**：X 的**生成器链接** `out/vless-xhttp_share-08.txt` 是带 SNI 的，单独喂给 mihomo **通**（204/1.39s）——
```
vless://278502fc-...@107.173.154.178:29601?encryption=none&security=tls&sni=moontv.6896698.xyz&type=ws&path=/8KLD3cNj&ech=...  → 204
```
⇒ **丢 SNI 发生在「分享层」（9443 那份订阅），不在生成器。** 与上一轮结论一致。

---

## 4. 核心对照表（逐条给证据）

| 问题 | X 内核 | M 内核 | SB 内核 | 结论（X独有 / 共有 / 各家不同） |
|---|---|---|---|---|
| **1 分享层丢 SNI** | ✅**有**<br>分享订阅里 `vless://…29601?…security=tls&type=ws&path=…` **无 `sni=`**；`hysteria2://…29604?sni=107.173.154.178` 把 IP 当 SNI。mihomo 实测 5 节点仅 1 通，错误 `x509: cannot validate certificate for 107.173.154.178 because it doesn't contain any IP SANs` | ❌**没有**<br>内容层 19 节点 **TLS 型无一缺 sni**（`grep` 判定集合为空）；URL 链接 12 条**全部**带 `sni=`；mihomo 实测 **19/19 = 204** | ❌**没有**<br>13 条链接全带 `sni=`（vmess 的 sni 在 base64 JSON 内 `"sni":"hxicc.catmicos.dpdns.org"`）；14 个客户端 outbound 里 TLS 型都有 `tls.server_name`；实测 **13/13 = 204** | **X 独有** |
| **2 CDN 节点端口/目标不一致** | ✅**有**<br>`out/vless-xhttp_share-07.txt` = `@moontv.6896698.xyz:443`，而片段真实监听 `0.0.0.0:8443`；443 上是 nginx→moontv 网页 → `bad status code:307 Temporary Redirect` / `unexpected response version. Expecting 0 but actually 60`（生成即死链）。分享层端口改对成 8443，但同一节点又丢 SNI | ⚠️**部分（另一成因）**<br>**订阅内容层正确**：CDN 节点 `server: hxicc.catmicos.dpdns.org` / `port: 443` / `servername` 同名，nginx 上 5 条 location 全都回源到真实端口（`/cdnws-0ab96db5→25680`、`/cg0599db34→25681`、`/xhc-bcd2a955→25677`、`/cdnws-7a34637f→25678`、`/cg0523759e→25679`），E2E 5/5 CDN 节点 204。<br>**但 URL 链接产物 12 条里 10 条端口无人监听**（实测 `ss` 比对）：`anytls_share-01→50877`、`hysteria2_share-01→21168`、`-10→23512`、`-11→[IPv6]:22737`、`reality_share-04→42099`、`trojan_share-01→56676`、`tuicv5_share-01→38899`、`-09→[IPv6]:23451` **全部 DEAD**；真实监听是 25669-25684/28725/22812。⇒ 同样是死链 | ❌**没有**<br>链接 `@hxicc.catmicos.dpdns.org:443`，客户端产物 `server=107.173.154.178 / server_port=443`（**目标写法不同：域名 vs IP**），真实入口 nginx `0.0.0.0:443` → `location /5ac821b0→https://127.0.0.1:31003`、`/322c087d→31007`、`/cba311b5→31006`。**13/13 条链接端口全部在监听**（`ss` 逐条比对）。两种写法**实测都通**：`IP:443 → 204\|2.46s`、`domain:443 → 204\|3.82s`（trojan/vmess 同样双通） | **X 独有该形态**；M 是**同后果、不同成因**（陈旧产物，不是生成时写错端口）；**SB 无** |
| **3 对公网 CA 证书也无条件 pin** | ✅**有**<br>`out/vless-xhttp_client-07.json` 里 `"pinnedPeerCertSha256": "48165d74269bc097af60af23bc8c323f2821b8006983d1316fb5fa47d23ff955"`，而该证书是公网 CA 真证书（`moontv.6896698.xyz`）；CDN 路径必然不匹配 → `peer cert is unrecognized (against pinnedPeerCertSha256)` | ❌**没有**<br>pin **只**出现在自签节点 `mHysteria202-TLS`（`sni=www.amazon.com`，证书 `issuer=CN=www.amazon.com` **自签**）→ `pin=b8f8fc05…`（**正确用法**）。真证书节点（`mAnyTLS01/02`、`mHysteria201`、`mTrojan03`、`mTUIC01`、`mVLESS01/02/03-TLS`、**全部 5 个 CDN 节点**）**一律无 pin**，写法是 `skip-cert-verify: false` 或省略。实测 19/19 通过，无一条 pin 报错 | ❌**没有**<br>13 条链接 + 14 个客户端 outbound **零 pin**（`certificate_public_key_sha256` 全缺）；代码侧 `conf/anytls.sh:280`、`conf/hysteria2.sh:284` 都是 `[[ "$CERT_TRUSTED" == "false" ]] && pin=…`。CDN 节点 `insecure:false`，连的是 nginx 上 LE 真证书（`subject=CN=hxicc.catmicos.dpdns.org`、`issuer=C=US,O=Let's Encrypt,CN=YE1`），实测 204 | **X 独有** |
| **4 客户端解析丢 reality 参数** | ✅**有**（X 自家客户端 `xbd`）<br>534 行报告 §3.5/§6 P1-5：订阅解析出 5 个只导入 4 个，`/tmp/.xbd_skipped.json` = `[["TROJAN-03","Xray 内核不支持该协议（trojan）"]]`；`parse_trojan()` 不映射 `pbk/sid` → `security=reality 但缺少 pbk` → 被当不支持丢弃（**链接里 pbk/sid 其实都在**：`&pbk=GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU&sid=b860a9f0`） | ❌**没有**<br>M 客户端导入 **19/19** 个节点，provider YAML 完整保留 `reality-opts: {public-key: uMcVRoEWeMAwPaj6e3jSVCZfbl-gj37MH9_XI9tL5wY, short-id: 58896ecc5f8bf710}`（3 个 vless-reality + 2 个 trojan-reality）。**交叉验证**：把 M 的 `reality_share-04.txt` 喂给 **SB 的 `to_sb.py`**（SB 客户端解析别家订阅的那条路）→ `"reality": {"public_key": "uMcVRoEWeMAwPaj6e3jSVCZfbl-gj37MH9_XI9tL5wY", "short_id": "58896ecc5f8bf710"}` + `server_name: aod.itunes.apple.com` 全在 | ❌**没有**<br>客户端产物 reality 块完整：`public_key=tnXodgtAkqwGSZBIQu-O9hRj1VsFG4PwMriVzy0cHwA` + `short_id` 四条（`60656f4e153adc66` / `5c102aa54237286f` / `c1f47cd762b2fa17` / `a3baeab74472c469`）+ `server_name` 齐。E2E：`reality01-REALITY / anytls02-REALITY / trojan02-REALITY / vmess02-REALITY` **4/4 = 204**。反向验证：SB 的 `to_sb.py` 解析 **X 的** `trojan-share-03.txt` 也完整保留 → 这是 **X 客户端自己的解析缺陷**，不是生态问题 | **X 独有** |
| **5 会让订阅挂掉的硬编码参数**（`obfs=none`） | ✅**有**<br>`out/hy2_share-02.txt`：`…?sni=hxicc…&insecure=0&alpn=h3&obfs=none&upmbps=50&downmbps=200`（`hy2_share-03.txt` 同）。mihomo：`initial proxy provider t error: proxy 0 error: missing obfs password` → provider **0 节点** | ✅**有**<br>`out/hysteria2_share-01/02/10/11.txt` **四条全部** `&obfs=none`。<br>单条：`…?sni=hxicc…&insecure=0&alpn=h3&upmbps=50&downmbps=200&obfs=none` → mihomo `missing obfs password`，0 节点。<br>**混合验证（关键）**：把 1 条 hy2 + 8 条本来能用的 M 链接放进同一订阅 → `provider 't' node count = 0`，报 `proxy 0 error: missing obfs password` ⇒ **一条坏节点把整条订阅打挂**，8 个好节点一起消失 | ✅**有**<br>`out/sb_share-hysteria201-TLS.txt`：`hysteria2://f00f67…@107.173.154.178:31001?sni=hxicc.catmicos.dpdns.org&obfs=none&obfs-password=&alpn=h3`（`sb_links-all.txt` 同）→ mihomo：`proxy 0 error: missing obfs password`，provider **0 节点**。<br>（注：SB 自己不受影响——它的分享内容是 sing-box JSON，`sni/obfs` 字段由 sing-box 语义解释；受害的是把这条 **URI 链接**喂给 mihomo 的场景） | **生态共有（三家全中）** |

**实测通过统计**：X 已发布订阅 **1/5**；M 订阅 **19/19**；M URL 链接 **3/12**；SB **13/13**。

---

## 5. 本轮新发现的问题（不在原 5 条里）

### P-M1【严重】M 的分享订阅生成 **100% 失败**：名字集合交集 = 0
`build_sub.py: live_node_names()` 用 `conf/config.d/.managed.json` 过滤陈旧产物，判据是**字符串全等**：
```
# conf/config.d/.managed.json（merge.py 从 listener.name 写，**裸名**）
['mAnyTLS01-TLS', 'mAnyTLS02-TLS', 'mAnyTLS03-TLS', 'mHysteria201-TLS', ...]
# out/*_client-*.yaml 的 name:（m_node_tag → m_with_flag，**带旗帜**）
  - name: 🇺🇸 mAnyTLS01-TLS
  - name: 🇺🇸 mAnyTLS02-TLS
  ...
$ python3 -c "...交集..."
  artifacts: 19  managed: 19  intersection: 0        # ← 一个都对不上
```
后果（**用 M 自己的代码路径实测**）：
```
$ python3 src/share/build_sub.py --out-dir out --conf-dir conf --tag all
[清理] 剔除了 19 个陈旧产物 (节点已删除, 但 out/ 里旧文件还在)
[ERR] 没有任何可用节点 (out/*_client-*.yaml 为空?)
$ ... source env.sh; source share/share.sh; printf '1\n0\n5\n\n' | share_create
分享哪些节点?
  1) 全部节点 (all)                    ← 只剩「全部」一个选项，协议桶全没了
分享服务对外地址: 107.173.154.178
请输入: [Error] 生成分享内容失败 (没有可分享的节点?)      ← 面板原文
share_create exit=1
$ share_gen_tag_auto all 0 0
0exit=1
```
根因：`m_node_tag()` 是"节点名唯一出口"，后来加了地区旗帜（`m_with_flag` → `🇺🇸 …`），但 **listener 名（写进 `config.d/*.yaml` → `.managed.json`）没有加**，于是 `--conf-dir` 那道"剔除陈旧产物"的过滤把**全部 19 个活节点**判成陈旧。`out/` 产物 mtime 与 `naming.py`/`naming_migrate.py` 同为 `Oct 9 21:20`，`.managed.json` 为 `Oct 9 21:11`，时间上吻合"旗帜特性上线即打断分享生成"。

### P-M2【严重】已发出的分享内容**永久冻结在陈旧快照**，且快照里的端口无人监听
- 公共服务里 M 唯一 active 记录 `fc071c8d6e0f19a0c46b0b71fab4d647`（`created_at=1791605514` = 2026-10-10 04:11 UTC），内容 232 字节：
```
proxies:
- name: 🇺🇸 mAnyTLS01-TLS
  type: anytls
  server: 107.173.154.178
  port: 20000                     # ← ss 全表无 20000，真实监听是 25684
  sni: www.amazon.com             # ← 与实际 25684 上的证书 (LE hxicc...) 不符
  skip-cert-verify: true
```
- `ss -tulnp | grep :20000` → 空。同名的磁盘产物 `out/anytls_anytls_client-01.yaml` 写的是 `port: 25684`。`port: 20000` 只存在于 **10-07 的备份**（`nodes.bak.20261007-194459/out/reality_reality_client-01.yaml`）。
- `share_refresh_all()` 因 P-M1 每条都 `continue` ⇒ 内容**永远不刷新**。CC 实测：M 官方客户端拉这条 URL → `[Error] 链接不存在`（HTTP 404，因为该 token 为 `max_uses=1`，被我先前的一次 `curl` 用掉后已被服务端 `cleanup: 删除 used_up 记录` GC —— 服务端日志原文，非缺陷）。

### P-M3 M 的 URL 链接产物大面积陈旧（见 §4 问题 2 格）
12 条 `out/*_share-*.txt` 里 **10 条端口无人监听**。这类"链接还在、端口早没了"的产物没有任何机制在端口迁移时同步。

### P-M4 M 客户端**不吃自己的 URL 分享链接**
```
$ ... node_add  ← 输入 /tmp/e2e-share/links/m_anytls-02.txt（内容是一条 anytls:// 链接）
[ERR] 不是合法的 Mihomo 订阅 (需要顶层 proxies: 列表)
```
M 的客户端只接受 `proxies:` YAML（HTTP 订阅或本地文件），而 `out/*_share-*.txt` 是 URI 链接 —— 对 M 自家客户端完全无用，只能给别家客户端。

### P-SB-none
SB 侧未发现分享层新问题（分享内容 = 客户端产物 `cp`，字节一致；13/13 端口一致；无多余 pin；实测 13/13 通过）。唯一可记的观察：**CDN 节点的"链接用域名、客户端产物用 IP"两种写法并存**（都实测可用），口径不统一但不构成缺陷。

---

## 6. UNKNOWN 清单

1. **M 那条 232 字节陈旧快照的 `port: 20000` 是谁写进去的**：当前 `out/` 与 `conf/` 里都没有 20000（只在 `nodes.bak.20261007-194459/` 备份里有 `port: 20000`），`created_at` 是 10-10 04:11 UTC —— 无法确定它是 10-07 的产物被 publish、还是当时另有一份产物。**UNKNOWN**。
2. **M 的 `--conf-dir` 过滤在旗帜特性上线前是否正常**：只证明"现在 19/19 全被剔除"，没有拿到修改前的历史运行日志。**UNKNOWN**。
3. **M/SB 的 `hysteria2` 分享链接在「不经过 mihomo」的客户端（如 v2rayN、Nekoray、sing-box 直吃 URI）里是否同样因 `obfs=none` 失败**：本轮只在 mihomo 1.19.32 上做了 `obfs=none` 的加载实验（三家链接同口径）。**UNKNOWN**。
4. **SB 的 `sb-client add` 真身完整跑通**：为避免 `apply_change()→do_start` 触碰生产 unit，本轮用 `curl`+`sing-box check`（与 `add_node` 完全同命令）等价替代。**未执行真身，UNKNOWN**（但拉取/校验/内核连通三段都有实测）。
5. **Cloudflare zone 的 SSL 模式**（CDN 域名回源 443）：只证明 `hxicc.catmicos.dpdns.org:443` 能回源到 nginx 并拿到 LE 证书、SB/M 的 CDN 节点经域名实测 204；具体 SSL 模式 **UNKNOWN**。
6. **X 的 TROJAN-03 在 mihomo 里 000 的确切原因**：X 的分享层 trojan 链接**带了** `pbk=GiR4…&sid=b860a9f0`，mihomo 却连不上（`000`，log 里被 vless/hy2 的 x509 刷屏，未单独隔离该节点的错误行）。上一轮报告说该节点用 Xray 客户端直连是 204 可用的。**UNKNOWN**（不影响 5 条结论，但值得单列）。

---

## 7. 收尾与清理（实际做了什么）

**新增/改动的生产面（全部保留说明，未删生产配置）**
- RN `proxy-share-service` 里新建的 5 条测试分享记录（M 1 条 + SB 4 条），**已全部 revoke**，health 回到开工前形状：
  `{"mihomo":{"total":1,"active":0},"sing-box":{"total":0,"active":0},"xray":{"total":1,"active":1}}`（与开工前逐字一致）。
- RN `out/share_tag-*.txt`：`share.sh create` 的正常副作用（我无法只发 token 不写这个文件）——`share_tag-all.txt`、`share_tag-vless01-TLS-CDN.txt` **被覆盖**（原本就指向已不存在的 token），新建 `share_tag-reality01-REALITY.txt`、`share_tag-hysteria201-TLS.txt`（**已删除**）。**未动任何节点配置、未重启任何服务。**
- CC：`/root/catmi/mihomo-client` 的生产实例**只读使用**（`CLI_ROOT` 隔离到 `/tmp`，`CLI_SERVICE` 指向不存在的 unit，PID 1364829 全程不变）；SB 生产实例未调用其 `add` 路径（PID 1444214 全程不变）。

**清理**
- RN：`rm -rf /tmp/e2e /tmp/m_all.yaml`；`ss -tulnH` 行数 90（= 基线 90）。
- CC：临时内核进程全部结束；`rm -rf /tmp/e2e-share`、`/tmp/harness*.sh /tmp/mh_*.sh /tmp/sb_*.py`；`ps` 再无 e2e 相关进程；测试端口 17800-17999 无一在听；`/tmp/e2e-share` 不存在。
- 本地：`/tmp/e2e-share`、`/tmp/*.out` 等临时文件在报告写完后清理。

**服务状态（收工复核）**
```
# RN
xrayls=active mihomo=active sing-box=active nginx=active proxy-share-service=active
PIDs mihomo=119320 sing-box=60510 nginx=958 xrayls=165517      # 与基线一致
ss 行数 90                                                       # 与基线一致
# CC
mihomo-client=active (PID 1364829)   sb-client=active (PID 1444214)   # 与基线一致
```
**未 push 任何仓库**；仅新增本报告文件。

---

## 8. 复现命令速查

```bash
# ---- M：CC 侧用 M 官方客户端隔离拉取（不碰生产）----
cd /root/catmi/mihomo-client/src
mkdir -p /tmp/mcli && printf 'PORT_MIXED="17890"\nPORT_CTRL="17891"\nBIND_ADDR="127.0.0.1"\nGEO_AUTO_UPDATE="0"\n' > /tmp/mcli/settings.env
ln -sf /root/catmi/mihomo-client/mihomo /tmp/mcli/mihomo
CLI_ROOT=/tmp/mcli CLI_SERVICE=mihomo-e2e-tmp \
  bash -c 'source ./client.sh; printf "%s\n" "<分享URL>" "2" "" | node_add'
/tmp/mcli/mihomo -d /tmp/mcli/conf &          # 临时实例
# 逐节点: GET /proxies/<组> 取 all[] → PUT /proxies/<组> {"name":...} → curl -x http://127.0.0.1:17890 ...

# ---- M：证明分享生成坏掉（只读，安全）----
python3 /root/catmi/mihomo/src/share/build_sub.py --out-dir /root/catmi/mihomo/out \
        --conf-dir /root/catmi/mihomo/conf --tag all
# ---- M/SB/X：hy2 obfs=none 一票否决实验 ----
#   proxy-providers: {t: {type: file, path: <含一行 hysteria2://…obfs=none 的文件>}}
/root/catmi/mihomo-client/mihomo -t -d <cfgdir>;  /root/catmi/mihomo-client/mihomo -d <cfgdir> &
curl -s 127.0.0.1:<api>/providers/proxies/t | jq '.proxies|length'

# ---- SB：拉分享 + 真内核逐节点 ----
curl -sSL -o /tmp/x.json -w '%{http_code}' --max-time 20 http://107.173.154.178:9443/share/<token>
/opt/sb-client/core/sing-box check -c /tmp/x.json
#   run: {"inbounds":[mixed 127.0.0.1:17930], "outbounds":[...分享里的...], "route":{"final":"<tag>"}}
```
