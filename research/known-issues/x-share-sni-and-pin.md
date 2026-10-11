# X 内核分享链路：SNI 丢失 / 公网 CA 强写 pin / hy2 丢参数

- 日期：2026-10-10
- 目标仓库：`/root/deepseek/repos/xray--core`（**只改这一个**；`sing-box-core` / `mihomo--core` 只读）
- 真机：`ssh rn`（107.173.154.178，Xray 26.3.27 = `xrayls`、mihomo v1.19.32、sing-box 1.14.2、
  hysteria 内核）、`ssh CC`（192.168.1.178，Xray 26.3.27 arm64 + Client 安装 `/opt/xray-browser-dialer`）
- 所有实验都在 `/tmp`（本机 / RN / CC），跑完已清理（`/tmp/xshare_test`、`/tmp/mihomotest`、
  `/tmp/sbtest`、`/tmp/ccshare` 均已删除）；**没有写任何生产路径**，RN/CC 正式服务全程 active
  （mihomo / sing-box / xrayls / xray-client 复查：`active`）。
- 提交（`main`，已推送：`git ls-remote origin main` = `e4b8b5fc191e649078ed18d2a6bdf878926daa27`）：

| # | commit | 内容 |
|---|---|---|
| 1 | `7bb3d8b` | P1-4 分享层丢 SNI（TLS 节点链接没有 `sni=`、hy2 把连接地址当 SNI） |
| 2 | `92edf3c` | P2-7 公网 CA / 边缘终结 TLS 时不再写 `pinnedPeerCertSha256` |
| 3 | `9231b52` | hy2 链接补齐 `alpn` / 带宽参数（参数名按两家内核解析器对齐） |
| 4 | `e4b8b5f` | 门禁：为这三条加 17 条回归断言 |

- 门禁：`bash tools/check_libs.sh` → **662 通过 / 0 失败**（改动前基线 645/0；同一组断言打在
  修复前的代码上 → **9 条失败**，反向验证成立；提交后在干净树 `git archive HEAD` 里再跑一次
  同样 **662 / 0**，工作树 `git status` 干净）。
- 路径更正：本轮题目里写的 `Client/lib/nodes.py` 实际是 **`conf/lib/nodes.py`**（服务端分享层）。
  `Client/lib/node.py` 是客户端解析器，未改。

---

## 一览

| # | 问题 | 是否已修 | 跨内核验证 | CC 实测 | commit |
|---|---|---|---|---|---|
| P1-4 | TLS 节点链接无 `sni=`；hy2 写 `sni=<IP>` | ✅ | mihomo 000→204；sing-box 000→204 | 000→204 | `7bb3d8b` |
| P2-7 | 公网 CA 证书也写 pin | ✅ | mihomo 侧同字段负控（错 pin 整条订阅失败） | `peer cert is unrecognized` 复现并消失 | `92edf3c` |
| hy2 | 链接丢 `alpn`/带宽 | ✅ | mihomo 采纳 `up/down`+`alpn`；sing-box 面板采纳 `upmbps/downmbps`+`alpn` | — | `9231b52` |

---

## P1-4 · 分享层丢 SNI（最高优先）

### 实证（修复前，RN 真实数据重跑分享链路）

在 RN 上用**未改动的** `nodes.py`（`git show HEAD:conf/lib/nodes.py`）跑 `/root/catmi/xray/conf`
+ `/root/catmi/xray/out/share`（24 个节点、8 条分享元数据）：

```
### vless-xhttp07  vless://1fa7c981-...@107.173.154.178:8443?encryption=none&security=tls&type=xhttp&path=%2FaVCR3P0A%2F
### vless-xhttp08  vless://278502fc-...@107.173.154.178:29601?encryption=none&security=tls&type=ws&path=%2F8KLD3cNj
### hysteria-04    hysteria2://05615ce2-...@107.173.154.178:29604?sni=107.173.154.178&insecure=0
```

- TLS 节点的 `tlsSettings.serverName` 是**空的**（生产 04/05/06/07/08 全空），旧代码只从
  `realitySettings.serverNames` 取 sni → TLS 链接**一个 sni 都没有**；
- hy2 的 `sni` 取的是 `meta["host"]`，而生产元数据里 host 就是**连接地址**（8/8 个 meta 都是
  `107.173.154.178`）→ 生成 `sni=107.173.154.178`。

### 修法（`conf/lib/nodes.py`）

| 新增 | 作用 |
|---|---|
| `tls_domains(tls)` | SNI 候选：`tlsSettings.serverName` → 证书 SAN 的 `DNS:` → CN（`openssl x509`，按 `(路径, mtime)` 缓存）→ `certificates[].domain` |
| `cert_domain(path)` | 读"客户端真的会看到的那张证书"上的名字；读不到返回 None，不猜文件名 |
| `is_ip_literal(host)` | IPv4 / IPv6 / `[v6]` / `host:port` / 末尾点 全部拦掉 |
| `link_sni(n, meta)` | 取第一个非 IP 候选；节点/证书都没有才退回 meta 里的**域名**；都拿不到就**整个参数不写** |
| `reality_sni(n)` | REALITY 仍只取 `serverNames[0]`（取法一字未改），只拦"被填成 IP"的病态配置 |

### 证据链

1. **RN 真机重跑（修复后）**：24 个节点全部解析，`vless-xhttp07/08` →
   `sni=moontv.6896698.xyz`（证书 CN/SAN），`hysteria-04` → `sni=moontv.6896698.xyz`；
   REALITY 节点（TROJAN-03）输出与修复前逐字相同（`sni=audio-ssl.itunes.apple.com`）。
2. **跨内核（RN 真内核，把链接喂给 provider/客户端）**：

| 内核 | 修复前（链接含 `sni=IP` / 无 sni） | 修复后 |
|---|---|---|
| mihomo v1.19.32（hy2） | HTTP **000** `CRYPTO_ERROR 0x12a (local): tls: failed to verify certificate: x509: cannot validate certificate for 107.173.154.178 because it doesn't contain any IP SANs` | HTTP **204** |
| mihomo（vless-xhttp08，无 sni） | HTTP **000** 同上（`107.173.154.178:8443 connect error: ... no IP SANs`） | HTTP **204** |
| mihomo（vless-xhttp07） | HTTP **000** | HTTP **204** |
| sing-box 1.14.2（hy2，`server_name` 取链接的 sni） | HTTP **000** `INTERNAL_ERROR (local): tls: failed to verify certificate: x509: cannot validate cert...` | HTTP **204** |

3. **CC 实测**（Xray 26.3.27，链接经本项目自己的 Client 解析 → `genconfig.py` → 真内核）：

| 链接 | serverName | HTTP | 耗时 |
|---|---|---|---|
| 修复后（`sni=moontv.6896698.xyz` + `alpn=h3`） | moontv.6896698.xyz | **204** | 0.92s |
| 修复前（`sni=107.173.154.178`） | 107.173.154.178 | **000** | 0.79s |

修复前的 CC 内核原话（与题目里报的现象逐字一致）：

```
transport/internet/hysteria: RoundTrip err > CRYPTO_ERROR 0x12a (local):
tls: failed to verify certificate: x509: cannot validate certificate for
107.173.154.178 because it doesn't contain any IP SANs
```

---

## P2-7 · 公网 CA 证书也强制写 pin

### 实证（修复前）

判据是 `conf/vlessxhttpecn.sh:1120` 的 `[ -f "$CERT_FILE" ]`，而紧邻注释写的是
"用公网 CA 签的证书走正常校验, 不需要 pin" —— **注释与实现相反**。

RN 生产产物 `out/vless-xhttp_client-07.json`（由该脚本生成）：

```
"address": "moontv.6896698.xyz", "port": 443        # CDN-ECH 接入
"tlsSettings": { "serverName": "moontv.6896698.xyz", ...,
                 "pinnedPeerCertSha256": "48165d74269bc097af60af23bc8c323f2821b8006983d1316fb5fa47d23ff955" }
```

- 源站证书 = `/home/web/certs/moontv.6896698.xyz_cert.pem`，**Let's Encrypt** 签发 →
  DER sha256 `48165d74...`；
- 客户端实际连的是 Cloudflare 边缘（`ECH_MODE=cdn`），边缘为该 SNI 出示的是
  **Google Trust Services** 签的另一张证书 → DER sha256 `601927a1...`（RN 上
  `openssl s_client` 实读）。
- 两个指纹天然不同 ⇒ pin 必然不匹配。CC 上用**该产物原文件**（只改本机 socks/日志端口）复现：

```
transport/internet/splithttp: failed to GET https://moontv.6896698.xyz/aVCR3P0A/
  > transport/internet/tls: peer cert is unrecognized (against pinnedPeerCertSha256)
HTTP=000
```

### 修法

1. `conf/lib/cert.sh` 新增 **`x_cert_client_pin <crt> <TLS 是否终止于本节点> [强制]`**：
   输出该写进客户端的 hex pin，**不该写时输出空**。
   - TLS 不在本节点终结（nginx 档 / CDN-ECH 档）→ 不写；
   - 证书是公网 CA 签的（`x_cert_trusted`：subject ≠ issuer）→ 不写；
   - `XRAY_PIN_CERT=1`（用户显式要求）跳过上面两条。
   与 **SB** 的 `[[ "$CERT_TRUSTED" == "false" ]]`、**M** 的 `cert_is_trusted()`
   （subject == issuer ⇒ 自签）是同一套判据；两家同样都是"真证书一个 pin 都不写"。
2. `conf/vlessxhttpecn.sh` 只回答一个问题：**TLS 是不是终止在本节点**
   （`ACCESS_MODE != nginx && ECH_MODE != cdn`），其余交给上面的函数；注释与实现现在一致。

### 证据链

| 场景（同一个 `render_client`，只换判据） | 修复前 | 修复后 |
|---|---|---|
| CDN-ECH + 公网 CA 证书（生产 xhttp-07 形态） | pin `c5d61fb1…` | **无 pin** |
| direct-ECH + 公网 CA 证书 | pin | **无 pin** |
| direct-ECH + 自签证书 | pin `acd1af4d…` | pin（应有的钉扎没丢） |
| nginx 档 + 自签证书 | pin | **无 pin** |
| CDN + 自签 + `XRAY_PIN_CERT=1` | pin | pin（显式要求） |

- **CC 实连 CDN 节点**：带 pin 的旧产物 → `peer cert is unrecognized (against pinnedPeerCertSha256)`
  （HTTP 000）；去掉 pin 后该报错**消失**（改道去连源站仍是 204，见下）。
- **CC 实连源站 107.173.154.178:8443**（同一个节点、TLS 由 xray 自己终结）：

| 变体 | HTTP | 说明 |
|---|---|---|
| `sni=域名`，无 pin（新逻辑产物） | **204** | 公网 CA 正常校验 |
| `sni=域名` + pin(源站证书) | 204 | 直连时 pin 恰好对（所以旧判据只在 CDN/nginx 档害人） |
| `sni=IP`（修复前的分享链接） | **000** | `x509: cannot validate ...` |

---

## hy2 链接丢参数

### 实证（修复前）

面板分享链路生成的 hy2 链接只有 `sni` + `insecure`：
`hysteria2://…@107.173.154.178:29604?sni=107.173.154.178&insecure=0`
——比节点自己的客户端产物少一半：`conf/hysteria2.sh` 生成同一个节点时写的是
`sni=…&alpn=h3&upmbps=50&downmbps=200`，客户端 JSON 里还有 `up:"50mbps"/down:"200mbps"`。

### 参数名以两家解析器为准（这是本条的**关键**，写错是静默忽略）

| 参数 | mihomo v1.19.32 | sing-box 面板 `src/conf/outbound_uri.py` |
|---|---|---|
| `sni` | ✅ `converter.go:97` | ✅ `:466`（别名 `peer`） |
| `alpn` | ✅ `:99-101`（逗号切分） | ✅ `:467` |
| `up` / `down` | ✅ `:103-104`（裸数字 = Mbps） | ❌ 不认 |
| `upmbps` / `downmbps` | ❌ **只对已废弃的 hysteria v1 认**（`converter.go:37-65`） | ✅ `:485-491`（别名 `up_mbps`/`down_mbps`，非数字直接报错） |
| `pinSHA256` | ✅ `:102`（hex，长度必须是 64，否则**整条 provider 失败**） | ✅ `:470`（base64 SPKI，语义不同！） |

两家认的名字不一致，所以**两个写法都写**：各自的解析器取自己认识的那个，多出来的只是普通
未知参数（两家都只读自己认识的键，实测不报错）。只写一种就是实测过的坑 —— 旧链接里的
`upmbps=50` 被 mihomo 整条丢掉，带宽提示等于没写。

### 修法（`conf/lib/nodes.py`）

- `extract()` 增 `alpn`（来自节点 `tlsSettings.alpn`，hy2 就是 `h3`）；
- hy2 分支输出 `sni`（域名，见 P1-4）/ `insecure=0` / `alpn` / `up` / `down` /
  `upmbps` / `downmbps`（还有 `mport`，有则写）；
- 默认值与 `conf/hysteria2.sh` 同一组数（up 50 / down 200 / alpn h3），可按节点用
  `share_meta` 的 `upmbps`/`downmbps` 覆盖。

### 证据链

- **mihomo（RN 真内核）**：`alpn=h3` → HTTP 204；`alpn=h2` → HTTP **000**
  `CRYPTO_ERROR 0x178 (remote): tls: no application protocol` ⇒ **alpn 确实被采纳**（不是静默忽略）。
- **mihomo 读 `up`/`down`、忽略 `upmbps`/`downmbps`**：`up/down` 直接进
  `Hysteria2Option.Up/Down` → `utils.StringToBps` → `SendBPS/ReceiveBPS`
  （`adapter/outbound/hysteria2.go:46-47, 211-212`）；`grep upmbps converter.go` 只命中
  `case "hysteria"`（v1）分支。
  速率对照实验（`up=1000&down=1000&upmbps=1&downmbps=1` vs 反向）**未能区分**：三种组合
  都是 38–58 Mbps —— hysteria2 的拥塞控制由**服务端**决定（Xray hysteria 入站不下发
  带宽），客户端单方面设 `up/down` 观察不到限速。故"采纳"的结论来自解析器源码 +
  字段映射，**限速行为侧为 UNKNOWN**。
- **sing-box 面板解析器**（`outbound_uri.py` 直接吃该链接）：`tls.alpn=["h3"]`、
  `up_mbps=50`、`down_mbps=200`；`up`/`down` 被忽略但**不报错**。
- **sing-box 1.14.2 真客户端**（用解析结果建配置，RN 回环连真实节点）：HTTP 204。

---

## 边界与遗留

- 只改 `xray--core`；SB / M 全程只读（M 的 Go 源码读的是本机 `/tmp/xsrc/mihomo`，
  tag v1.19.32，与 RN 上真内核同版本）。
- 没有写任何生产路径；有 `mkdir` 的脚本（`cert.sh` 只在函数内建目录）没被执行到顶层；
  `vlessxhttpecn.sh` 的验证是把 `render_client` 单独抽出来跑的，没跑菜单。
- 推送凭据一次性使用后未落盘（无 `~/.git-credentials`、无 credential.helper、`.git/config`
  无 token），因此没有需要 `shred` 的文件。

### UNKNOWN / 建议后续

1. **`pinSHA256` 两家语义冲突**：mihomo 要 hex(64 字符)，sing-box 要 base64 SPKI，
   同一个参数名两种编码。受影响的是 `conf/hysteria2.sh:740` 自签分支写的 `pin=<hex>`
   —— **mihomo 压根不读 `pin`**（只读 `pinSHA256`），所以自签 hy2 节点经分享链接
   仍然只能靠客户端自己 pin。改名会让 sing-box 侧拿到错的编码，故本轮未动。
2. **本项目自己的 Client 不采纳 hy2 的 up/down**：`Client/lib/genconfig.py` 生成的
   hysteria2 出站里没有 `hysteriaSettings.up/down`（链接里有、shell 产物里也有），
   链接侧补齐后客户端仍会丢。未在本轮三件之内。
3. **xhttp-07 经 CDN 边缘仍连不通**（与 pin 无关）：去掉 pin 后报
   `bad status code: 307 Temporary Redirect`（直连源站 8443 是 204）。看起来是该节点
   当前的边缘/路径状态问题，不是分享链接生成的问题，未深挖。
4. **REALITY 节点 TROJAN-03 经 mihomo 连接 HTTP 000**（修复前后一致，非本轮改动引入），
   未定位；`TROJAN-01` 则因 meta 缺 pbk 被分享层按设计拒发。
5. 速率对照无法证明 `up`/`down` 的**行为**被采纳（服务端决定拥塞控制），见上。
