# Xray 能力清单（Kernel Capability Inventory — Xray）

> Phase 1 研究产出。目标：为 `proxy-node-compat` 提供 Xray 侧的 **Node Feature / URI Representation /
> Kernel Representation / Runtime Support** 四层映射与**版本门槛**。
>
> **基线版本**：`v26.3.27`（GitHub Releases 中最后一个 `prerelease=false` 的标签，2026-03-27）。
> `v26.4.13` 起所有标签在 GitHub API 中 `prerelease=true`；`main` 又领先于 `v26.9.30`。
> 因此本文同时标注 **26.3.27（稳定）** 与 **main（2026-10-10 快照）** 的差异。
>
> **证据纪律**：每条结论都带 `[doc]` / `[src]` / `[test]` / `[unknown]` 标注。
> 本文件**不含任何 `[test]` 证据**（我没有内核运行环境，未做任何实际运行验证）——
> 运行/回环实测请见 `research/empirical/`（由其它工作表产出）。凡查不到的一律写 `UNKNOWN`，不写"应该支持"。

---

## 0. 证据来源

### 0.1 官方文档（`[doc]`，实际抓取过的页面）

| URL | 用途 |
|---|---|
| https://xtls.github.io/config/transport.html | streamSettings 总览、method/security 枚举、transport×security 兼容表 |
| https://xtls.github.io/config/transports/ | 传输方式索引（当前支持集合） |
| https://xtls.github.io/config/transports/raw.html | RAW（原 TCP）字段、header |
| https://xtls.github.io/config/transports/mkcp.html | mKCP 字段 + `header`/`seed` 已移除声明 |
| https://xtls.github.io/config/transports/websocket.html | WS 字段、`ed`、XHTTP 迁移建议 |
| https://xtls.github.io/config/transports/httpupgrade.html | HTTPUpgrade 字段、`ed` |
| https://xtls.github.io/config/transports/grpc.html | gRPC 字段、multiMode=BETA、限制 |
| https://xtls.github.io/config/transports/hysteria.html | Hysteria 字段、masquerade |
| https://xtls.github.io/config/transports/finalmask.html | FinalMask 全部 type 与 quicParams |
| https://xtls.github.io/config/transports/xhttp.html（及 `http.html`/`h2.html`/`quic.html`/`splithttp.html`） | **全部是 stub**：正文只有 "See XHTTP: Beyond REALITY"，无字段文档 |
| https://xtls.github.io/config/transports/reality.html | REALITY 服务端/客户端字段与限制 |
| https://xtls.github.io/config/transports/tls.html | TLSObject、allowInsecure 弃用、ECH、fingerprint、pcs/vcn |
| https://xtls.github.io/config/transports/sockopt.html | sockopt 全字段 + trustedXForwardedFor 限制 |
| https://xtls.github.io/config/outbound.html | OutboundObject、MuxObject |
| https://xtls.github.io/config/outbounds/vless.html · /config/inbounds/vless.html | VLESS flow / encryption / decryption / fallbacks |
| https://xtls.github.io/config/outbounds/vmess.html · /config/outbounds/trojan.html · /config/outbounds/shadowsocks.html · /config/inbounds/shadowsocks.html | VMess / Trojan / SS 字段与安全要求 |
| https://xtls.github.io/config/features/browser_dialer.html | Browser Dialer：**环境变量**启用、仅 WS/XHTTP、忽略 SNI/自定义头 |
| https://xtls.github.io/config/features/fallback.html | fallback 触发条件、`dest` 端口形态（v25.7.26 变更） |
| https://xtls.github.io/config/features/xtls.html | **内容为空 stub（WIP）**，无任何字段/算法说明 |
| https://xtls.github.io/about/news.html | 大史记：各版本"新增/移除"官方叙述（见 §5） |
| https://xtls.github.io/development/protocols/vless.html | VLESS 协议页（内含"分享链接标准"链接） |
| https://xtls.github.io/en/... （对应英文页） | 交叉核对 |

### 0.2 官方源码（`[src]`，`github.com/XTLS/Xray-core`）

读取方式：`raw.githubusercontent.com/XTLS/Xray-core/<tag>/<path>` 与我本人在内存中解包比对的 tag 快照
（**未 clone、未落盘任何第三方仓库**）。

**比对过的 tag**：`v1.7.5, v1.8.24, v24.9.19, v24.9.30, v24.10.16, v24.10.31, v24.11.21, v24.12.31,
v25.2.18, v25.3.31, v25.4.30, v25.6.8, v25.7.26, v25.9.11, v25.10.15, v25.12.8,
v26.1.13, v26.1.18, v26.1.23, v26.1.31, v26.2.2, v26.2.6, v26.3.27, v26.5.9, v26.6.1,
v26.7.11, v26.7.28, v26.9.8, v26.9.30, main(2026-10-10)`

**重点文件**：

- `infra/conf/transport_internet.go`（26.3.27 及以前的 transport/security 大文件；`StreamConfig`、`TransportProtocol.Build`、`KCPConfig`、`SplitHTTPConfig`、`TLSConfig`、`REALITYConfig`、`WebSocketConfig`、`HttpUpgradeConfig`、`GRPCConfig`、`HysteriaConfig`）
- `infra/conf/transport_method.go`（**v26.7.11 起**拆出的文件：`SplitHTTPConfig`/`XmuxConfig`/`KCPConfig`/`GRPCConfig`/`WebSocketConfig`/`HttpUpgradeConfig`/`MasqueConfig`/`XDriveConfig`/`TCPConfig`）
- `infra/conf/transport_security.go`（**v26.7.11 起**拆出的文件：`TLSConfig`/`REALITYConfig`/`LimitFallback`）
- `infra/conf/transport_finalmask.go`、`infra/conf/transport_sockopt.go`、`infra/conf/lint.go`
- `infra/conf/vless.go`、`vmess.go`、`trojan.go`、`shadowsocks.go`、`xray.go`、`freedom.go`
- `common/errors/feature_errors.go`（`PrintRemovedFeatureError` / `PrintDeprecatedFeatureWarning` / `PrintNonRemovalDeprecatedFeatureWarning` 的语义）
- `transport/internet/tls/tls.go`（fingerprint 全集）、`transport/internet/tls/config.go`、`transport/internet/tls/ech.go`
- `transport/internet/splithttp/dialer.go`（XHTTP auto→mode 映射）
- `proxy/vless/outbound/outbound.go`、`proxy/vless/vless.go`、`proxy/vless/encoding/addons.go`
- `proxy/shadowsocks_2022/shadowsocks_2022.go`（SS2022 method 常量）

### 0.3 官方讨论 / 规范 / 发布说明

- https://github.com/XTLS/Xray-core/discussions/716 — **VMessAEAD / VLESS 分享链接标准**（§4 参数清单，含 2026-01-18 / 2026-03-27 修订记录）
- https://github.com/XTLS/Xray-core/discussions/4113 — **XHTTP: Beyond REALITY**（XHTTP 字段事实来源：docs 的 xhttp.html 已退化为 stub 并指向它）
- https://github.com/XTLS/Xray-core/releases/tag/v26.2.6 — allowInsecure 移除与 2026-06-01 延时禁用说明
- https://github.com/XTLS/Xray-core/releases （标签列表与 prerelease 标记，经 GitHub API 读取）
- https://shadowsocks.org/doc/sip002.html 与 `shadowsocks/shadowsocks-org` 的 `docs/doc/sip002.md`（SS URI 规范）
- https://trojan-gfw.github.io/trojan/usage.html（**只有 CLI 用法，没有任何分享 URI 规范**）

### 0.4 关于 `[test]`

本文件 **0 条 `[test]` 证据**。所有"运行时是否生效"的判断都只到源码层（`[src]`：字段被读取/未读取、是否报错），
**没有**任何实际内核启动、配置校验或连通性验证。凡是需要"跑一次才知道"的，见 §8 UNKNOWN。

---

## 1. 协议清单

| 协议 | Xray 支持（版本门槛） | 必填字段（出站 `settings`） | 证据 |
|---|---|---|---|
| **VLESS** | 至少 v1.7.5 起持续支持（v1.7.5 已存在 `infra/conf/vless.go`）；README 称 v1.0.0 起自 v2fly-core fork，**v1.0.0–v1.7.4 未逐版本核实** | `address`,`port`,`id`；**`encryption` 必须显式给出**（`"none"` 或 `mlkem768x25519plus...`） | `[src]` main `infra/conf/vless.go`：`if account.Encryption == "" { return errors.New("please add/set \"encryption\":\"none\"") }`；同一校验在 v24.9.19 已存在；`v1.7.5/infra/conf/vless.go` 存在（HTTP 200） |
| **VLESS + 后量子加密（VLESS Encryption）** | **v25.9.11 起**（v25.7.26 无 `mlkem768x25519plus`） | 出站 `users[].encryption`；入站 `settings.decryption` | `[src]` 跨 tag 字符串探测：`mlkem768x25519plus` 在 v25.7.26 不存在、v25.9.11 存在；`[doc]` #5067 / outbounds/vless.html |
| **VLESS + flow（Vision）** | v1.6.2 起有 Vision 流控 | `flow`（可空）；入站只接受空或 `xtls-rprx-vision`；出站另接受 `xtls-rprx-vision-udp443` | `[src]` main `infra/conf/vless.go`（入站 `switch c.Flow { case vless.XRV, "": }`；出站 `case xray.XRV, vless.XRV+"-udp443"`）；`proxy/vless/vless.go:10 XRV = "xtls-rprx-vision"`；`[doc]` about/news.html v1.6.2 |
| **VMess（AEAD）** | 持续支持；**仅 AEAD**（MD5/alterId 已移除） | `address`,`port`,`id`；`security` 可选（`auto`/`aes-128-gcm`/`chacha20-poly1305`） | `[src]` main `infra/conf/vmess.go`；`[doc]` about/news.html："v1.5.1 记得将 VMess 配置中的 alterID 去掉"、"v1.8.3 VMess (MD5)…已被卸下" |
| **VMess `security:"zero"`** | **≤v26.5.9 曾支持；v26.7.11 起代码中不再有该分支** | — | `[src]` 跨 tag：`case "zero"` 在 v26.5.9 存在、v26.7.11 不存在；main 的 `VMessAccount.Build` 无匹配分支 → **落到 `default: SecurityType_AUTO`（静默降级，见 §7）** |
| **Trojan** | 至少 v1.7.5 起持续支持（v1.7.5 已有 `infra/conf/trojan.go`），但 main 标记为**非移除型弃用** | `address`,`port`,`password`；**不允许 `flow`**（硬报错） | `[src]` main `infra/conf/trojan.go`：`errors.PrintNonRemovalDeprecatedFeatureWarning("Trojan (with no Flow, etc.)", "VLESS with Flow & Seed")`；`if rec.Flow != "" { return PrintRemovedFeatureError("Flow for Trojan") }`（v24.9.19 起已是硬错误） |
| **Shadowsocks（AEAD 旧式）** | 持续支持，main 标记为非移除型弃用 | `address`,`port`,`method`,`password` | `[src]` main `infra/conf/shadowsocks.go`：`PrintNonRemovalDeprecatedFeatureWarning("Shadowsocks (with no Forward Secrecy, etc.)", "VLESS Encryption")`；`cipherFromString` 仅认 `aes-128-gcm/aes-256-gcm/chacha20-poly1305/xchacha20-poly1305`（含 `aead_*`、`chacha20-ietf-poly1305` 别名），其余 → `CipherType_UNKNOWN` → `errors.New("unknown cipher method")`（**硬报错，不静默**） |
| **Shadowsocks 2022** | **v1.5.6 起** | `method` = `2022-blake3-aes-128-gcm` / `2022-blake3-aes-256-gcm` / `2022-blake3-chacha20-poly1305`；单用户 `password`=base64 key；多用户密码形如 `ServerPassword:UserPassword` | `[src]` main `proxy/shadowsocks_2022/shadowsocks_2022.go` 三个 `Method*` 常量；`infra/conf/shadowsocks.go` `GetCipherMethod` 分支 + "multi-user: only blake3-aes-*-gcm methods are supported"；`[doc]` about/news.html v1.5.6 |
| **Shadowsocks `none`/`plain`** | **不支持** | — | `[src]` `cipherFromString` 无 `none` 分支 → `unknown cipher method`（硬报错） |
| **Hysteria（协议，in/out bound）** | 传输 **v26.1.23 起**（见 §2） | 见 `hysteriaSettings` | `[src]` `case "hysteria"` 首次出现在 v26.1.23；`[doc]` transports/hysteria.html |
| **WireGuard（出站）** | 存在（`protocol: "wireguard"`），与分享 URI 无关 | — | `[doc]` outbound.html 协议枚举 |
| **MTProto / Starlark / VMess-MD5** | **已移除** | — | `[doc]` about/news.html："v1.8.3 … VMess (MD5)、MTProto 以及 Starlark 相关代码已被卸下"（该条为新闻页叙述，我未在源码中逐版本复核） |
| **DomainSocket 传输** | **已移除** | — | `[doc]` about/news.html v24.9.7；`[src]` v24.9.19 的 `TransportProtocol.Build` 已无该 case |

> **必填字段的共同语义（危险点）**：VLESS 的 `encryption`/`decryption` **不能留空**，必须显式 `"none"`。
> 一条只写了 `id` 而没有 `encryption` 的"简化配置"在 Xray 上是**加载失败**，而不是"自动 none"。
> 这与很多客户端"不给这个字段"的默认行为直接冲突。

---

## 2. 传输方式（transport）

`streamSettings` 的选择字段：**稳定版 26.3.27 用 `network`**；**`method` 别名在 v26.7.28 才出现**（`method` 优先于 `network`）。
官方文档（被 main 驱动）只写 `method`。

| transport 名 | 官方名 / 别名 | 版本变化 | 关键参数 | 证据 |
|---|---|---|---|---|
| **RAW** | `raw` / `tcp` → 内核内部名 `tcp`；旧字段 `rawSettings` / `tcpSettings`（**同时存在时 `rawSettings` 优先**） | 别名 `raw` **v24.9.30 加入**（v24.9.19 只认 `tcp`）；官方叙述"v24.9.30 TCP 传输层更名为 RAW" | `header`（`none`/`http`）、`acceptProxyProtocol`、HTTP 伪装的 `request`/`response` | `[src]` v24.9.19 `case "tcp"` vs v24.9.30 `case "raw","tcp"`；main `StreamConfig.Build`：`if c.RAWSettings != nil { c.TCPSettings = c.RAWSettings }`；`[doc]` raw.html + news.html |
| **XHTTP** | `xhttp` / `splithttp` → 内核内部名 `splithttp`；字段 `xhttpSettings`（优先）/ `splithttpSettings` | **别名 `xhttp` v24.10.31 加入**（v24.10.16 只认 `splithttp`）；官方叙述"v24.10.31 SplitHTTP 进化为 XHTTP" | `host`,`path`,`mode`,`extra`（**有 `extra` 时只有这四个生效**）；`extra` 内：`headers`,`xPaddingBytes`,`xPaddingObfsMode`,`xPaddingKey/Header/Placement/Method`,`uplinkHTTPMethod`,`sessionIDPlacement/Key/Table/Length`,`seqPlacement/Key`,`uplinkDataPlacement/Key/ChunkSize`,`noGRPCHeader`,`noSSEHeader`,`scMaxEachPostBytes`,`scMinPostsIntervalMs`,`scMaxBufferedPosts`,`scStreamUpServerSecs`,`serverMaxHeaderBytes`,`xmux{...}`,`downloadSettings` | `[src]` main `infra/conf/transport_method.go` `SplitHTTPConfig`；`transport/internet/splithttp/dialer.go`（auto→mode）；`[doc]` discussion #4113；`[src]` 跨 tag：`case "xhttp","splithttp"` 自 v24.10.31 |
| **XHTTP `mode`** | `auto`(默认) / `packet-up` / `stream-up` / `stream-one` | 与 XHTTP 同期 | `auto` 的客户端映射：**REALITY → `stream-one`（有 `downloadSettings` 时 `stream-up`），否则 `packet-up`** | `[src]` main `splithttp/dialer.go`：`mode = "packet-up"; if realityConfig != nil { mode = "stream-one"; if DownloadSettings != nil { mode = "stream-up" } }`；`[doc]` #4113 另称 "TLS H2 时 stream-up" |
| **XHTTP `downloadSettings`** | 嵌套一套完整 `streamSettings` | — | **`mode: stream-one` 时禁止使用**（硬报错）；`network` 必须为 `xhttp` | `[src]` main：`if c.Mode == "stream-one" { return nil, errors.New("Can not use \"downloadSettings\" in \"stream-one\" mode.") }` |
| **XHTTP `xmux` 默认值（版本不同！）** | `maxConcurrency` / `maxConnections` / `cMaxReuseTimes` / `hMaxRequestTimes` / `hMaxReusableSecs` / `hKeepAlivePeriod` | **26.3.27 默认 `maxConcurrency=1-1`**；**main 改为 `maxConnections=3`** + `hMaxRequestTimes=600-900` + `hMaxReusableSecs=1800-3000` | `maxConnections` 与 `maxConcurrency` 不能同时指定（硬报错） | `[src]` v26.3.27 `if c.Xmux == (XmuxConfig{}) { MaxConcurrency.From/To = 1 }` vs main 同处改为 `MaxConnections.From/To = 3` |
| **mKCP** | `kcp` / `mkcp`；字段 `kcpSettings` | 见 §5：`header`/`seed` 已移除；`congestion`/`readBufferSize`/`writeBufferSize` 被 `cwndMultiplier`/`maxSendingWindow` 取代 | `mtu`,`tti`,`uplinkCapacity`,`downlinkCapacity`,`cwndMultiplier`,`maxSendingWindow` | `[src]` main / v26.3.27 `KCPConfig`；`[doc]` mkcp.html |
| **WebSocket** | `ws` / `websocket`；字段 `wsSettings` | **main 标记非移除型弃用**（建议 XHTTP） | `host`,`path`,`headers`,`heartbeatPeriod`,`acceptProxyProtocol`；**path 中的 `?ed=` 会被抽出**作为 Early Data | `[src]` main `WebSocketConfig.Build` 解析 `q.Get("ed")` 并从 path 删除；`ui` 见 §7（`headers.host` 只警告+迁移） |
| **HTTPUpgrade** | `httpupgrade`；字段 `httpupgradeSettings` | main 标记非移除型弃用 | `host`,`path`,`headers`,`acceptProxyProtocol`；path 中 `?ed=` 同样被抽出 | `[src]` main `HttpUpgradeConfig.Build`；**`headers` 内含 `host` 直接报错**（与 WS 处理不一致） |
| **gRPC** | `grpc`；旧别名 `gun`（v24.9.30 仍有，main 已删除）；字段 `grpcSettings` | main 标记非移除型弃用 | `authority`,`serviceName`,`multiMode`(BETA),`idle_timeout`,`health_check_timeout`,`permit_without_stream`,`initial_windows_size`,`user_agent` | `[src]` main `GRPCConfig`；`[doc]` grpc.html（multiMode 为实验性、不保证跨版本兼容） |
| **Hysteria** | `hysteria`；字段 `hysteriaSettings` | **v26.1.23 起** | `version`（**必须 = 2**）,`auth`,`udpIdleTimeout`,`masquerade{type,dir,url,rewriteHost,xForwarded,insecure,content,headers,statusCode}` | `[src]` `case "hysteria"` 首见于 v26.1.23；`if c.Version != 2 { return errors.New("version != 2") }` |
| **MASQUE** | `masque`；字段 `masqueSettings` | **仅 v26.9.30 与 main**（v26.9.8 无） | `host`,`path`,`user`,`pass`,`headers`,`warp{privateKey,publicKey,address}` | `[src]` 跨 tag：`case "masque"` 在 v26.9.8 不存在、v26.9.30 存在 |
| **XDrive** | `xdrive`；字段 `xdriveSettings` | **仅 v26.9.30 与 main** | `remoteFolder`,`service`(`local`/`Google Drive`/`template`),`secrets`,`segmentBytes`,… | `[src]` 同上一行；main `XDriveConfig` |
| **HTTP / HTTP2 / HTTP3（`h2`/`h3`/`http`）** | — | **已移除**：v24.12.31 起给出"已移除并迁移到 XHTTP stream-one H2 & H3"的**硬错误**；v24.9.19–v24.11.21 期间这些名字**在 switch 中完全不存在** → 只报 `unknown transport protocol` | — | `[src]` 跨 tag 比对（v24.11.21 无、v24.12.31 有） |
| **QUIC** | — | **已移除**；同上两阶段：先"unknown"（≤v24.11.21），v24.12.31 起给出指向 XHTTP stream-one H3 的硬错误 | — | `[src]` 同上；`[doc]` about/news.html v24.9.7 |
| **DomainSocket** | — | 已移除（≤v24.9.19 起 switch 中即不存在） | — | `[src]` v24.9.19 switch；`[doc]` news.html |
| **`streamSettings.method`（别名）** | `method` | **v26.7.28 起才有该 JSON 字段**；26.3.27 及以前**完全不存在** | 与 `network` 同时存在时 `method` 覆盖 `network` | `[src]` `Method *TransportProtocol \`json:"method"\`` 在 v26.3.27/v26.5.9/v26.6.1 计数为 0，v26.7.28/main 为 1；main `StreamConfig.Build`：`if c.Method != nil { c.Network = c.Method }` |
| **全局 `transport` 段** | — | **已移除**（≤v24.9.19 起即硬报错，指向 inbound/outbound 的 `streamSettings`） | — | `[src]` main `infra/conf/xray.go`：`PrintRemovedFeatureError("Global transport config", …)` |

---

## 3. 安全层（security / TLS / REALITY）

`streamSettings.security` 取值：`none`（默认）/ `tls` / `reality`。
（历史值 `xtls` 已移除，见 §5。）

| 能力 | 配置字段 | URI 能否表达 | 版本门槛 | 证据 |
|---|---|---|---|---|
| TLS | `tlsSettings.*` | 部分（`security=tls` + `sni`/`alpn`/`fp`） | 一直支持 | `[doc]` tls.html / #716 |
| REALITY | `security:"reality"` + `realitySettings` | 部分（`pbk`/`sid`/`spx`/`pqv`） | **v1.8.0 起**（新闻页） | `[doc]` about/news.html v1.8.0 |
| **REALITY 传输限制** | — | — | **只允许 RAW / XHTTP / gRPC**；其他组合在**配置加载阶段**报错 | `[src]` main `if config.ProtocolName != "tcp" && != "splithttp" && != "grpc" { return errors.New("REALITY only supports RAW, XHTTP and gRPC for now.") }`；`[doc]` reality.html |
| REALITY 服务端字段 | `show`,`target`(旧名 `dest`，互为 alias),`xver`,`serverNames`(必填),`privateKey`,`minClientVer`,`maxClientVer`,`maxTimeDiff`,`shortIds`(必填),`mldsa65Seed`,`limitFallbackUpload/Download{afterBytes,bytesPerSec,burstBytesPerSec}` | 服务端字段**不在分享 URI 里** | `mldsa65Seed` **v25.7.26 起** | `[src]` main `infra/conf/transport_security.go` `REALITYConfig`；`[doc]` reality.html |
| REALITY 客户端字段 | `serverName`,`fingerprint`(必填),`shortId`,`password`(旧名 `publicKey`),`mldsa65Verify`,`spiderX`(支持 `?p=&c=&t=&i=&r=` 爬虫参数) | `sni`/`fp`/`sid`/`pbk`/`spx`/`pqv` | `mldsa65Verify`/`pqv` **v25.7.26 起** | `[src]` 同上（`if c.Password != "" { c.PublicKey = c.Password }`）；`[src]` 跨 tag：`mldsa65Verify` v25.6.8 无、v25.7.26 有 |
| **REALITY 客户端禁用指纹** | `fingerprint` | `fp` | **`unsafe` 与 `hellogolang` 被拒绝**（REALITY 专用校验；TLS 路径允许 `unsafe`） | `[src]` `if config.Fingerprint == "unsafe" \|\| config.Fingerprint == "hellogolang" { return errors.New("invalid \"fingerprint\"") }`（仅在 `else`＝客户端分支） |
| **REALITY 默认最低客户端版本** | `minClientVer` | 不能 | main 中**默认值赋值被注释掉**（注释写着默认 v26.3.27，但代码不生效） | `[src]` main `// config.MinClientVer = []byte{26, 3, 27} // change it at your own risk`（注释，不执行） |
| **TLS `allowInsecure`** | `allowInsecure` | 历史 URI 常用 `allowInsecure=1`（#716 明确"没有过 allowInsecure"） | **v26.1.23 及以前仍生效**；**v26.1.31–v26.2.2 立即硬报错**；**v26.2.6–v26.5.9 改为"按日期软禁用"**：系统时间 < 2026-06-01 UTC 时仅警告并继续生效，≥ 该时刻硬报错（v26.3.27 仍带此闸门）；**v26.7.11/main 起无日期判断→无条件硬报错** | `[src]` v26.1.23 `config.AllowInsecure = c.Insecure`（仍生效）；v26.1.31/v26.2.2 直接 `PrintRemovedFeatureError`；v26.2.6/v26.3.27 `if time.Now().After(time.Date(2026,6,1,…)) { error } else { warning; config.AllowInsecure = true }`；v26.7.11/v26.7.28/v26.9.30 无 `time.Date(2026,6,1…`；`[doc]` releases/tag/v26.2.6 |
| **`pinnedPeerCertSha256`(pcs)** | `tlsSettings.pinnedPeerCertSha256` | **能**（#716 4.4.4，2026-01-18 加入规范） | **v26.1.23 起** | `[src]` 跨 tag 探测：v25.12.8 无、v26.1.23 有；`[doc]` #716 |
| **`verifyPeerCertByName`(vcn)** | `tlsSettings.verifyPeerCertByName` | **能**（#716 4.4.4，2026-02-02 修订） | **v26.2.6 起** | `[src]` 跨 tag：v26.1.23 无、v26.2.6 有 |
| **ECH** | 服务端 `echServerKeys`；客户端 `echConfigList` + `echSockopt` | **能**（#716 4.4.3，2025-07-26 加入规范） | **v25.7.26 起** | `[src]` 跨 tag：`echServerKeys`/`echConfigList` 在 v25.6.8 无、v25.7.26 有；`[doc]` #716 / tls.html |
| ECH 取值格式 | `echConfigList`：①直接 base64 ECHConfig ②DNS 查询串（`udp://`、`https://…/dns-query`、`h2c://`）③`example.com+https://1.1.1.1/dns-query` | 能（整串进 `ech`） | — | `[src]` `transport/internet/tls/ech.go` `ApplyECH`；`[doc]` tls.html |
| **TLS `fingerprint`（uTLS）** | `fingerprint` | `fp`（**REALITY 必填**） | 预设：`chrome`(默认)/`firefox`/`safari`/`ios`/`android`/`edge`/`360`/`qq`/`random`/`randomized`/`randomizednoalpn`/`unsafe`；另有 `hello*` 全量名（含 `hellogolang`、`hellochrome_1xx`、`helloios_*` 等） | `[src]` main `transport/internet/tls/tls.go` 的 `PresetFingerprints`/`ModernFingerprints`/`OtherFingerprints`；空字符串 → `HelloChrome_Auto`；未知名 → 配置期报错 `unknown "fingerprint"`（TLS 路径；REALITY 路径报 `invalid`） |
| TLS ALPN | `alpn`（`StringList`） | `alpn`（逗号分隔） | 特殊值 `fromMitm`；**含 `fromMitm` 时 alpn 只允许 1 个元素** | `[src]` main：`if tls.IsFromMitm(p) { return errors.New("only one element is allowed in \"alpn\" when using \"fromMitm\" in it") }`；`config.go: func IsFromMitm(str string) bool { return strings.ToLower(str) == "frommitm" }` |
| TLS `serverName` 特殊值 | `serverName = "FromMitM"` → 内部置空 SNI（交给上层/中间人） | 不能（URI 无对应参数） | — | `[src]` main `config.go: func (c *Config) parseServerName() string { if IsFromMitm(c.ServerName) { return "" } … }` |
| TLS 版本/套件 | `minVersion`,`maxVersion`,`cipherSuites` | 不能 | — | `[doc]` tls.html；`[src]` `TLSConfig` |
| TLS 曲线 | `curvePreferences` | 不能 | **v24.12.31 起**（v24.9.19 无） | `[src]` 跨 tag 探测 |
| 证书固定/校验 | `pinnedPeerCertSha256`（leaf 命中即过；CA 命中则改用 vcn 验签）、`verifyPeerCertByName`、`disableSystemRoot`、`enableSessionResumption`、`rejectUnknownSni` | 仅 pcs/vcn | — | `[src]` `transport/internet/tls/config.go` `verifyPeerCert`；`[doc]` tls.html |
| `masterKeyLog` | `masterKeyLog`（值为 `"none"` 表示不写） | 不能 | — | `[src]` `if len(c.MasterKeyLog) > 0 && c.MasterKeyLog != "none"` |
| 入站证书 | `certificates[]{certificateFile,certificate,keyFile,key,usage,ocspStapling,oneTimeLoading,buildChain}` | 不能（服务端侧） | 热重载周期 3600s（文档） | `[doc]` tls.html |
| **`useSystemCA`** | `tlsSettings.useSystemCA` | 不能 | **未发布**：v26.9.30 及以前所有 tag 都没有；仅 main 有 | `[src]` 跨 tag 探测（`UseSystemCA` 在 v1.7.5…v26.9.30 全为 N，main 为 Y） |

---

## 4. 高级 / 特殊能力

| 能力 | 配置位置 | 版本门槛 / 关键约束 | 证据 |
|---|---|---|---|
| **flow / XTLS Vision** | `settings.flow`（VLESS in/out） | 入站只接受 `""`/`xtls-rprx-vision`；出站另接受 `xtls-rprx-vision-udp443`（内部截断为 XRV 并允许 UDP/443）。**Vision 要求连接的底层是 TLS/REALITY**：否则**不是配置错误，而是连接时**报 `XTLS only supports TLS and REALITY directly for now.`。默认拒绝 UDP/443（`XTLS rejected UDP/443 traffic`） | `[src]` main `infra/conf/vless.go`、`proxy/vless/outbound/outbound.go:282`、`proxy/vless/inbound/inbound.go:581`、`:593`、`proxy/vless/encoding/addons.go:70` |
| 旧 Vision 变体 | — | `xtls-rprx-direct`/`splice`/`origin` **已不存在**（news：v1.7.5 是最后一次见到） | `[doc]` about/news.html；`[src]` main 中仅 `XRV` 常量 |
| **mux（mux.cool）** | 出站 `mux{enabled,concurrency,xudpConcurrency,xudpProxyUDP443}` | `concurrency<0` 表示 TCP 不走 mux；`xudpConcurrency` 负数＝UDP 走协议原生（SS→原生 UDP，VLESS→UoT）；`xudpProxyUDP443` ∈ `reject`(默认)/`allow`/`skip`，其他值**配置期报错**。文档明确"使用 XHTTP 时不要启用 mux.cool"；mux 只对 TCP/UDP 语义有效 | `[src]` main `infra/conf/xray.go` `MuxConfig.Build`（`default: return nil, errors.New("unknown \"xudpProxyUDP443\"")`）；`[doc]` outbound.html、#4113 |
| mux 传输标记 | 协议层固定域名 `v1.mux.cool:9527` | — | `[src]` `common/mux/client.go:185-186` |
| **XUDP** | 同 mux | v1.8.1 起（news："XUDP 的控制配置"）；v1.7.5 无 `xudpProxyUDP443` | `[src]` 跨 tag：`XudpProxyUDP443` v1.7.5 无、v1.8.24 有；`[doc]` news.html |
| **packetEncoding** | **Xray 中不存在** | 在 v1.7.5…v26.9.30 与 main 的**全部 .go 源码中都不存在**该字段；官方文档也无（`none/packet/packetaddr/stream` 是其它内核/客户端的字段） | `[src]` 全树 grep `packetEncoding` = 0 命中（各 tag 与 main）；`[doc]` sockopt/mux/policy 页均无 |
| **Browser Dialer** | **环境变量** `XRAY_BROWSER_DIALER=127.0.0.1:8080`（非 JSON 字段） | 仅 **WebSocket 与 XHTTP**；`address` 必须是域名；**SNI == host == address**，**自定义 HTTP 头与其它 tlsSettings 会被忽略**；CORS 限制。XHTTP 下与 REALITY 互斥（源码条件 `browser_dialer.HasBrowserDialer() && realityConfig == nil`） | `[src]` `transport/internet/splithttp/dialer.go:50`、`transport/internet/websocket/dialer.go:106`、`common/platform/platform.go:23`；`[doc]` browser_dialer.html（WebSocket v1.4.1+ / XHTTP v1.8.19+ 标题；v1.4.2 加入） |
| **FinalMask** | `streamSettings.finalmask{tcp[],udp[],quicParams}` | **v26.1.23 起**；`mkcp-legacy`（旧 mKCP 伪装）**v26.7.28 起**。TCP type：`header-custom`,`fragment`,`sudoku`,`xmc`；UDP type：`header-custom`,`mkcp-legacy`,`noise`,`salamander`,`sudoku`,`xdns`,`xicmp`,`realm`,`udphop` | `[src]` main `infra/conf/transport_finalmask.go` 的 `tcpmaskLoader`/`udpmaskLoader`；跨 tag：`finalmask` 目录 v25.12.8 无、v26.1.23 有；`mkcp-legacy` v26.5.9 无、v26.7.28 有；`[doc]` finalmask.html |
| FinalMask quicParams | `congestion`(``/`brutal`/`reno`/`bbr`/`force-brutal`，`force-brutal` 必须给 `up`)、`bbrProfile`、`brutalUp/Down`（≥65536 B/s）、`initStreamReceiveWindow` 等（≥16384）、`maxIdleTimeout`(4–120)、`keepAlivePeriod`(2–60)、`maxIncomingStreams`(≥8)、`brutalDisableLossCompensation`、`disablePathMtuDiscovery`、`disableChromeParrot`、`disableGSO`、`disableStatelessReset` | 非法值 → **配置期硬报错** | `[src]` main `infra/conf/transport_internet.go` 中 quicParams 校验块（大量 `return nil, errors.New(...)`） |
| **sockopt** | `streamSettings.sockopt` | `mark`,`tcpFastOpen`,`tproxy`,`domainStrategy`,`dialerProxy`,`acceptProxyProtocol`,`tcpKeepAliveInterval`,`tcpKeepAliveIdle`,`tcpCongestion`,`tcpWindowClamp`,`tcpMaxSeg`,`penetrate`,`tcpUserTimeout`,`v6only`,`interface`,`tcpMptcp`,`customSockopt`,`addressPortStrategy`,`happyEyeballs{tryDelayMs,prioritizeIPv6,interleave,maxConcurrentTry}`,`trustedXForwardedFor` | `[src]` main `infra/conf/transport_sockopt.go`；`[doc]` sockopt.html（`trustedXForwardedFor` 仅对 XHTTP/WS/HTTPUpgrade/gRPC 生效） |
| sockopt 静默忽略案例 | `trustedXForwardedFor` 未配置时收到 `X-Forwarded-For` → **只记一条 warning 并忽略该头** | — | `[src]` `common/protocol/http/headers.go:34`、`transport/internet/grpc/encoding/remoteaddr.go:53` |
| **fallbacks** | VLESS/Trojan 入站 `fallbacks[]` | **仅 TCP+TLS**；有子节点时必须给入站 TLS `alpn:["http/1.1"]`；VLESS 触发条件"首包 <18 字节或版本无效/认证失败"；Trojan 为"首包 <58 或第 57 字节非 \r"。`dest` 只写端口时：**v25.7.26 起指向 localhost，此前是 127.0.0.1** | `[src]` main `infra/conf/vless.go`（`fb.Dest = "localhost:" + fb.Dest`）；`[doc]` fallback.html |
| **VLESS reverse（反向）** | 出站 `reverse{tag,sniffing}`；入站 user `reverse{tag}` | 旧式 `reverse`（`"reverse":{...}` 顶层）**已移除**，指向 "VLESS Reverse Proxy" | `[src]` main `infra/conf/xray.go`：`PrintRemovedFeatureError("legacy reverse", "VLESS Reverse Proxy")` |
| **TUN 入站** | `protocol: "tun"` | **v26.1.23 起**（`infra/conf/tun.go` 在 v25.12.8 为 404，v26.1.23 起存在；结构体名 `TunConfig`） | `[src]` 跨 tag 文件存在性 + main `infra/conf/tun.go`；`[doc]` inbounds/tun.html |
| **平台/编译约束（影响 Runtime Support）** | — | main 的构建标签**只有 OS/arch**（`windows`/`linux`/`darwin`/`android`/…），**没有** `with_ech`/`with_gvisor`/`with_wintun`/`with_quic` 这类功能标签 | `[src]` main 全树 `//go:build` 行统计；`proxy/tun/tun_default.go` 的约束是 `!linux && !windows && !android && !darwin && !freebsd`（即不支持的 OS 上 TUN 走 stub）；`transport/internet/finalmask/mkcp/original/xor.go` 有 `!amd64` 约束 |
| **VLESS testseed / testpre** | 入站 `testseed`、出站 `testpre`/`testseed` | **仍在运行时被使用**（传给 Vision writer），但**官方文档完全未记载** | `[src]` main `proxy/vless/encoding/addons.go:71`（`NewVisionWriter(..., Testseed)`）、`proxy/vless/outbound/outbound.go:131`（`handler.testpre = a.Testpre`） |
| **VLESS 出站 `seed` 字段** | `settings.seed` | **被注释掉、解析后丢弃**：main `infra/conf/vless.go` 中 `account.Seed = c.Seed` 一行是注释 | `[src]` main `infra/conf/vless.go`（`//account.Seed = c.Seed`） |
| **sniffing / routeOnly** | 入站 `sniffing` | 常规能力，与节点兼容性弱相关 | `[src]` `infra/conf/xray.go` `SniffingConfig` |

---

## 5. 弃用与移除（deprecated / removed / renamed）

三种"弃用/移除"在源码里是**三种不同后果**（`common/errors/feature_errors.go`）：

| 函数 | 行为 |
|---|---|
| `PrintDeprecatedFeatureWarning` | warning："will be removed soon"（**配置仍生效**） |
| `PrintNonRemovalDeprecatedFeatureWarning` | warning："deprecated, not recommended… might be removed"（**配置仍生效**，短期不会删） |
| `PrintRemovedFeatureError` | **返回 error → 配置加载失败**，程序启动不了 |

| 旧形式 | 新形式 | 从哪个版本起 | 老配置的后果 | 证据 |
|---|---|---|---|---|
| `allowInsecure` | `pinnedPeerCertSha256` + `verifyPeerCertByName` | 生效 ≤**v26.1.23**；**v26.1.31 / v26.2.2 立即硬报错**；**v26.2.6–v26.5.9 改为按日期软禁用**（<2026-06-01 UTC 仅警告并生效；v26.3.27 亦如此）；**v26.7.11/main 起无条件硬报错** | 26.1.31+/26.2.2 直接起不来；26.2.6–26.5.9 在 2026-06-01 之前能跑，之后同一份配置/同一个二进制**突然起不来**（看系统时间！） | `[src]` 跨 tag 逐段比对（见 §3 行）；`[doc]` releases/tag/v26.2.6 |
| `security: "xtls"`（Legacy XTLS） | `flow: xtls-rprx-vision` + TLS/REALITY | ≤v24.9.19 起即硬报错 | 配置加载失败 | `[src]` main `PrintRemovedFeatureError("Legacy XTLS", …)`；v24.9.19 已存在 |
| flow `xtls-rprx-direct` / `-splice` / `-origin` | `xtls-rprx-vision` | 已不存在（news：v1.7.5 后） | 配置加载失败（VLESS flow 白名单校验） | `[doc]` about/news.html；`[src]` flow 白名单 |
| `xtls-rprx-vision-udp443`（出站） | 仍被接受（等价 Vision + 允许 UDP/443） | — | 无（但入站不接受该值） | `[src]` main `proxy/vless/outbound/outbound.go:250` |
| **`kcpSettings.header` / `kcpSettings.seed`** | FinalMask：`udp` 的 `header-*` / `mkcp-legacy` / `mkcp-aes128gcm` | **生效 ≤v26.1.23**；**v26.2.6–v26.9.8 硬报错**（"mkcp header & seed has been removed"）；**v26.9.30/main 起静默丢弃**（字段仍在结构体里，但 Build 既不校验也不读取） | 三段式：老版本可用 → 中间版本配置加载失败 → 最新版本**能加载、但 header/seed 完全不生效**（伪装/混淆静默消失） | `[src]` v26.1.23（`c.Seed != nil` 赋值生效）→ v26.2.6/v26.7.11/v26.7.28/v26.9.8（`PrintRemovedFeatureError("mkcp header & seed", …)`）→ v26.9.30/main（该 if 消失，仅剩结构体字段） |
| mKCP `congestion` / `readBufferSize` / `writeBufferSize` | `cwndMultiplier` / `maxSendingWindow` | 存在于 **v26.3.27**；**v26.7.11 起消失**（结构体只剩 mtu/tti/uplinkCapacity/downlinkCapacity/cwndMultiplier/maxSendingWindow） | 老字段在新版被当未知字段**静默忽略**（无 warning） | `[src]` v26.3.27 vs v26.7.11 `KCPConfig` 结构体对比 |
| VMess `security: "zero"` | 无 | 生效 ≤**v26.5.9**；**v26.7.11 起分支消失** | **静默回落到 `AUTO`**（`default: SecurityType_AUTO`），不报错、不警告 | `[src]` 跨 tag `case "zero"` 存在性 + main 的 `switch` 只有 3 个 case + default |
| Trojan `flow` | 无（用 VLESS） | ≤v24.9.19 起硬报错 | 配置加载失败 | `[src]` main/v24.9.19 `trojan.go` |
| 出站 `proxySettings` | `streamSettings.sockopt.dialerProxy` | 生效 ≤**v26.7.28**；**v26.9.8 起硬报错** | 配置加载失败 | `[src]` v26.7.28（`ProxySettings *ProxyConfig`）vs v26.9.8（`*json.RawMessage` + `PrintRemovedFeatureError`） |
| 顶层全局 `transport` 段 | inbound/outbound 各自的 `streamSettings` | 早已移除（≤v24.9.19） | 配置加载失败 | `[src]` main `xray.go` |
| 顶层旧式 `reverse` | VLESS Reverse Proxy | 已移除 | 配置加载失败 | `[src]` main `xray.go:619` |
| `freedom.noise = {…}` | `freedom.noises = [ … ]` | 已移除（main） | 配置加载失败 | `[src]` main `freedom.go:146` |
| `freedom.ipsBlocked` | `finalRules` | 已移除（main） | **仅 warning**（该处用 `LogWarning` 而非 `PrintRemovedFeatureError`，配置仍能加载） | `[src]` main `freedom.go:58`（warning 文案：`The feature "ipsBlocked" has been removed and migrated to "finalRules"`） |
| `freedom.domainStrategy` / `outbound.targetStrategy` | 自动迁移到新字段 | main 中"弃用/自动迁移" | 仅 warning，值被自动改写 | `[src]` main `xray.go:364,367` |
| `dnsProxy` 的 `nonIPQuery` / `blockTypes` | `rules` | main 中弃用 | warning + 旧策略解析 | `[src]` main `dns_proxy.go:99` |
| `wsSettings.headers.host` | 独立 `wsSettings.host` | 弃用（被自动迁移） | **warning + 自动删除该 header 并提升为 `host`**（不报错、行为被改写） | `[src]` main `WebSocketConfig.Build` |
| HTTP / HTTP2 / HTTP3 / QUIC 传输 | XHTTP（stream-one H2/H3） | 先"unknown"（≤v24.11.21），**v24.12.31 起明确 removed 错误** | 配置加载失败 | `[src]` 跨 tag switch 比对 |
| TCP 传输名 → RAW | `raw` | v24.9.30 | `tcp` 仍是合法别名（保留至今） | `[src]` 跨 tag；`[doc]` news.html |
| SplitHTTP → XHTTP | `method: "xhttp"` | v24.10.31 | `splithttp` 仍是合法别名（保留至今） | `[src]` 跨 tag |
| `network` → `method` | `streamSettings.method` | **v26.7.28 起** | **反向兼容性陷阱**：老内核收到 `method` 会当未知字段**静默忽略 → 传输回落为 TCP**（见 §7） | `[src]` 跨 tag 字段存在性 |
| gRPC / WebSocket / HTTPUpgrade 整体 | XHTTP | v24.12.31 已是"will be removed soon"；**v26.1.23 起改为"非移除型弃用"**（`PrintNonRemovalDeprecatedFeatureWarning` 首次出现） | 仅 warning，仍可用 | `[src]` 跨 tag；`feature_errors.go` 该函数在 v26.1.18 不存在、v26.1.23 存在 |
| VMess 整体 / Shadowsocks（非 2022） / Trojan 整体 | "VLESS Encryption" / "VLESS with Flow & Seed" | main（v26.1.23 起有该 warning 机制） | 仅 warning，仍可用 | `[src]` main `vmess.go:65,124`、`shadowsocks.go:50,200`、`trojan.go:43,122` |
| VMess alterId（aid） | 删除 | ≤v1.5.1（news） | 未知字段，静默忽略（VMess 结构体无 aid） | `[doc]` news.html；`[src]` main `vmess.go` 无 aid |
| VMess-MD5 / MTProto / Starlark | 删除 | v1.8.3（news，未由源码复核） | 不再存在 | `[doc]` news.html |
| DomainSocket / QUIC 传输 | 删除 | v24.9.7（news） | 见上 | `[doc]` news.html |

---

## 6. URI 表示能力（分享链接层）

### 6.1 最重要的前提：**Xray 内核本身不解析也不生成分享 URI**

- `[src]` 我对 main 全树（全部 `.go` + `.proto`）grep `vless://` / `vmess://` / `trojan://` / `ss://` /
  `shareLink` / `ParseLink` → **0 命中**。Xray-core 只吃 JSON 配置。
- 因此"URI 能不能表达"完全由**客户端实现 + 分享链接标准**决定。
  本项目的 `URI Representation` 层必须把"客户端解析器"也当成一层证据来源，而不能假设内核行为。

### 6.2 VLESS / VMess：官方分享链接标准（discussion #716，会随版本修订）

规范：`protocol://uuid@host:port?<protocol-specific>&<transport-specific>&<tls-specific>#remark`；
所有 value 必须 `encodeURIComponent`；参数名与常量**大小写敏感**；同一参数禁止重复。

| URI 参数 | 对应配置字段 | 备注（含规范修订时间） | 其它内核风险 |
|---|---|---|---|
| `type` | `streamSettings.network` | 取值 `tcp`/`kcp`/`ws`/`http`/`grpc`/`httpupgrade`/`xhttp`（**规范里没有 `h2`/`quic`/`raw`**） | 用 `raw` 的客户端不通用 |
| `encryption` | VLESS `settings.encryption`（VMess 时对应 `settings.security`） | VLESS 可选 `none` / `mlkem768x25519...`；VMess 可选 `auto`/`aes-128-gcm`/`chacha20-poly1305`/`none`（**规范仍写 `none`，但 Xray 出站 `"zero"` 分支已删**）。规范 2026-01-18 修订 | 旧客户端不认 `mlkem768x25519...` |
| `flow` | `flow` | 规范 2026-01-18 新增；可空 | 老客户端认 `xtls-rprx-vision-udp443` 与否不一 |
| `security` | `security` | `none`/`tls`/`reality`（**规范不含 `xtls`**） | — |
| `sni` | `serverName` | 省略时复用 host；REALITY 下必填 `fp` | — |
| `alpn` | `alpn` | 逗号分隔 | — |
| `fp` | `fingerprint` | 默认 `chrome` | 值集合由客户端 uTLS 决定 |
| `ech` | `echConfigList` | **规范 2025-07-26 新增** | **新增参数：老客户端直接丢弃 → ECH 静默丢失** |
| `pcs` / `vcn` | `pinnedPeerCertSha256` / `verifyPeerCertByName` | **规范 2026-01-18 新增**；逗号自动分割。规范原文："（没有过 allowInsecure，且 Xray-core 已移除该配置项）" | 老客户端不认 → 校验能力丢失 |
| `pbk` / `sid` / `spx` | REALITY `password` / `shortId` / `spiderX` | — | — |
| `pqv` | REALITY `mldsa65Verify` | **规范 2025-07-22 新增** | 老客户端丢弃 → 后量子校验丢失 |
| `serviceName` / `mode` / `authority` | gRPC | `mode` = `gun`(默认)/`multi`/`guna` | `guna` 非 Xray-core 原生（规范引用第三方实现） |
| `path` / `host` | ws / httpupgrade / xhttp | — | — |
| `headerType` | RAW 的 `header.type` / 历史 mKCP 伪装 | **mKCP 的 `headerType`/`seed` 已随内核移除而失去意义**（见 §7） | — |
| `mtu` / `tti` | mKCP | **规范 2026-03-27 新增** | 新参数，老客户端丢弃 |
| **`fm`** | `finalmask` | **规范 2026-01-31 新增**，整段 JSON 直接进 URI | **极新**：几乎只有最新客户端能表达 |
| XHTTP `mode` / `extra` | `mode` / `extra` | 规范 2024-11-11 新增；`extra` 整段 JSON | `extra` 内字段是"客户端自定义 JSON"，不同客户端实现差异大 |
| `mux` / `packetEncoding` | — | **#716 规范里没有任何 mux / packetEncoding 参数** | 这两个属于客户端私有扩展（如 `mux.enabled`），**不属于 Xray 分享标准** |

### 6.3 Trojan / Shadowsocks：**没有 Xray 官方 URI 规范**

- Trojan：`[doc]` 官方 trojan-gfw 文档只有 CLI 用法，**没有 URI 规范**。
  `trojan://password@host:port?security=tls&sni=…&type=…&path=…#tag` 是**客户端事实标准**（v2rayN / Shadowrocket 等），
  因此字段命名（`type`/`path`/`host`/`sni`/`allowInsecure`）无法从官方文档获得权威定义 → 见 §8。
- Shadowsocks：`[doc]` SIP002（shadowsocks.org/doc/sip002.html）：
  `ss://base64url(method:password)@host:port/?plugin=…#tag`；规范示例里明确写了
  `unsupported-arguments=should-be-ignored` —— **解析器必须忽略不认识的 query 参数**，
  这正是"能导入 ≠ 能完整使用"的规范级根源。
- 结论：Trojan/SS 的 URI 层要按"客户端事实标准"逐家建表，不能按内核文档推断。

### 6.4 URI 表达不了的（Xray 侧）

- **服务端专属**：`fallbacks`、`certificates`、`realitySettings` 服务端字段（`privateKey`/`serverNames`/`shortIds`/`limitFallback*`/`minClientVer`/`maxClientVer`/`maxTimeDiff`/`mldsa65Seed`）—— 分享 URI 天然无法表达。
- **sockopt 全组**：`mark`/`tproxy`/`interface`/`tcpMptcp`/`happyEyeballs`/`customSockopt`/`trustedXForwardedFor`… 规范里没有。
- **ECH 的 DNS 侧配置** `echSockopt`；TLS `certificates`/`curvePreferences`/`minVersion`/`masterKeyLog`/`rejectUnknownSni`/`enableSessionResumption`/`disableSystemRoot`。
- **mux 全组**（`concurrency`/`xudpConcurrency`/`xudpProxyUDP443`）。
- **VLESS `testseed` / `testpre`**（未文档化但运行时生效）。
- **XHTTP 的多数调优项**：只有整段 `extra`（以及 `host/path/mode`）能进 URI，`downloadSettings` 只能塞进 `extra`。

---

## 7. 不一致与风险点（本项目最该抓的东西）

按"四层断点"归类。**A = 能解析但不生效；B = URI 表达不了；C = 版本门槛；D = 同一版本行为随时间变化。**

| # | 类别 | 现象 | 版本/条件 | 后果 | 证据 |
|---|---|---|---|---|---|
| R1 | **A** | `streamSettings.method` 在 ≤v26.6.1 的内核上**是未知字段 → 被静默忽略 → 传输回落 TCP** | `method` 自 v26.7.28 才有 | 一份用 `method` 写的现代配置，在 26.3.27（当前"最新稳定版"）上**能启动、但按 TCP 直连** | `[src]` 跨 tag 字段存在性 |
| R2 | **A** | `kcpSettings.header` / `kcpSettings.seed` 在 **v26.9.30/main 上被静默丢弃**（结构体仍有字段，Build 不读不校验） | 26.9.30 起 | mKCP 伪装/seed 静默失效，无任何日志 | `[src]` v26.9.8（有硬错误）vs v26.9.30/main（无校验） |
| R3 | **A** | VMess `security:"zero"` 落 `default` → **静默变 `auto`** | v26.7.11 起 | 客户端以为"不加密"，实际按 auto 协商 | `[src]` main `vmess.go` |
| R4 | **A** | `wsSettings.headers.host` 只 warning，随后**自动删除该 header 并提升为 `host`** | 现版本 | 行为被静默改写（与 XHTTP 直接报错的处理不一致） | `[src]` main `WebSocketConfig.Build` |
| R5 | **A** | XHTTP `extra` 存在时，**外层除 `host`/`path`/`mode` 以外的所有字段被丢弃**（`c = &extra` 整体替换） | 现版本 | 例如外层写了 `headers`/`xPaddingBytes` 而同时有 `extra` → 这些参数无声消失 | `[src]` main `SplitHTTPConfig.Build` `if c.Extra != nil { …; c = &extra }`；`[doc]` #4113 "当存在 extra 时，只有这四个参数生效" |
| R6 | **A** | VLESS 出站 `settings.seed` 被注释掉 → **解析后丢弃** | main | 老配置里的 seed 无任何作用 | `[src]` main `infra/conf/vless.go` `//account.Seed = c.Seed` |
| R7 | **A** | Browser Dialer 下 **SNI == host == address，自定义 HTTP 头与其它 tlsSettings 一律被忽略** | 仅 WS/XHTTP；XHTTP+REALITY 互斥 | 用户以为设置了 SNI/头，实际没有 | `[src]` `splittp/dialer.go:50` 等；`[doc]` browser_dialer.html |
| R8 | **A** | `sockopt.trustedXForwardedFor` 未配置时 `X-Forwarded-For` **被忽略（仅 warning）** | — | 真实 IP 丢失 | `[src]` `common/protocol/http/headers.go:34` |
| R9 | **A** | **`packetEncoding` 在 Xray 中根本不存在**（任何版本、含 main） | 全部版本 | 客户端/订阅里带 `packetEncoding` 的节点，在 Xray 上该设置**完全无效**（无字段、无警告） | `[src]` 全树 grep 0 命中 |
| R10 | **A** | ECH 失败只 `LogError`，随后**塞一个无效 ECHConfig 让连接失败** | ECH 启用时 | 配置能加载、日志里才有线索，表现为"连不上" | `[src]` `tls/config.go:476` + `tls/ech.go`（`if len(ECHConfig) == 0 { ECHConfig = []byte{1,1,4,5,1,4} }`） |
| R11 | **A** | VLESS `flow` 配了 Vision 但 `security` 不是 tls/reality → **配置能加载，连接时才报** `XTLS only supports TLS and REALITY directly for now.` | — | 校验时机错位：导入成功、拨号失败 | `[src]` `proxy/vless/outbound/outbound.go:282` |
| R12 | **A** | Vision + UDP/443：默认直接拒绝 `XTLS rejected UDP/443 traffic`，必须用 `-udp443` 变体 | — | QUIC(UDP/443) 静默不可用 | `[src]` `outbound.go` `if !allowUDP443 && request.Port == 443` |
| R13 | **B** | `fallbacks` / `certificates` / REALITY 服务端字段 / sockopt 全组 / mux 全组 / `testseed` / `echSockopt` **URI 无法表达** | — | 从订阅导入即损失；必须标 `SUPPORTED_WITH_LOSS` | `[doc]` #716 参数表；`[src]` 字段清单 |
| R14 | **B** | `pcs`/`vcn`/`ech`/`pqv`/`fm`/`mtu`/`tti` 都是 **2025-07 之后才加入规范**的参数 | 见 §6.2 | 老客户端解析器会**静默丢弃**（SIP002 精神：忽略未知参数）→ 安全能力降级 | `[doc]` #716 修订时间戳 |
| R15 | **C** | `method`（≥26.7.28）、`hysteria`/`finalmask`/`pcs`/TUN（≥26.1.23）、`masque`/`xdrive`（≥26.9.30）、`mkcp-legacy`（≥26.7.28）、`sessionIDPlacement`（≥26.7.11）、`vcn`（≥26.2.6）、ECH/`mldsa65*`（≥25.7.26）、VLESS Encryption（≥25.9.11）、`curvePreferences`（≥v24.12.31）、`raw` 别名（≥v24.9.30）、`xhttp` 别名（≥v24.10.31） | 见左 | 版本判断必须按"字段首次出现"逐项建表 | `[src]` 跨 tag 探测（§0.2 的 tag 集合） |
| R16 | **C** | **"当前稳定版"本身有歧义**：GitHub 上 `v26.3.27` 是最后一个 `prerelease=false`；`main` 已支持 masque/xdrive/TUN/`sessionIDPlacement` 等 26.3.27 完全没有的能力 | — | 兼容性判定必须让用户**明确选版本**，不能写"Xray 支持 X" | `[src]` GitHub Releases API 的 `prerelease` 字段 |
| R17 | **D** | **同一个二进制、同一份配置，行为随系统时间变化**：`allowInsecure` 在 26.2.6–26.5.9 上，系统时间 < 2026-06-01 UTC 时可用，≥ 时配置加载失败（26.3.27 亦然；26.7.11+ 恒报错） | 26.2.6–26.5.9 | 判定结果必须带"当前日期"维度，否则结果不可复现 | `[src]` `if time.Now().After(time.Date(2026,6,1,…))` |
| R18 | **A** | VLESS `encryption`/`decryption` **不能留空**（必须显式 `"none"`），但很多客户端生成的配置不带该字段 | 长期行为（≤v24.9.19 已如此） | 配置加载失败 | `[src]` `infra/conf/vless.go` |
| R19 | **A** | REALITY 客户端的 `fingerprint` **不接受 `unsafe`/`hellogolang`**，而 TLS 路径接受 `unsafe` | — | 同一 `fp` 值在不同 security 下结局不同 | `[src]` `transport_security.go` REALITY 客户端分支 |
| R20 | **A** | main 中 REALITY"默认最低客户端版本 v26.3.27"只写在**注释**里，代码不生效 | main | 不要按注释推断运行时行为 | `[src]` `// config.MinClientVer = []byte{26, 3, 27}` |
| R21 | **C** | 入站只接受 `flow: xtls-rprx-vision`，出站才接受 `-udp443` | — | 服务端下发 `-udp443` 会加载失败 | `[src]` main `infra/conf/vless.go` |
| R22 | **A** | gRPC `multiMode` 被官方标为 **BETA / 不保证跨版本兼容** | — | 不能作为"长期可用"能力承诺 | `[doc]` grpc.html |

---

## 8. UNKNOWN 清单（明确未确认项）

1. **`[test]` 全层缺失**：没有任何内核运行/回环/抓包验证。所有"运行时是否生效"结论都只到源码静态分析。
2. **Trojan 分享 URI 的权威规范**：官方 trojan-gfw 文档没有 URI 规范（已确认只有 CLI 用法）。
   `trojan://` 的参数集合与语义**只能从各客户端实现反推**，本次未逐一核查客户端源码 → UNKNOWN。
3. **SS URI 的 `plugin` 语义与 Xray 的关系**：SIP002 定义了 `plugin=`，但 **Xray-core 是否有对应字段本次未查证** → UNKNOWN。
4. **Xray 各版本 uTLS 指纹集合的差异**：只确认了 main 的三张 fingerprint 表；**每个指纹名"从哪个版本可用"未逐版本核查** → UNKNOWN。
5. **`echSockopt`（ECHSocketSettings）的引入版本**：只知道 ECH 相关整体自 v25.7.26 出现 → UNKNOWN。
6. **`xPaddingObfsMode` / `noSSEHeader` 的精确引入版本**：`noSSEHeader` 在 v24.9.19 已存在（更早未查）；
   `xPaddingObfsMode` 首次出现在 v26.2.6（v26.1.23 无）→ 更早/更精确的边界 **UNKNOWN**。
7. **`sessionIDPlacement` 系字段的精确引入版本**：v26.6.1 无、v26.7.11 有 → 精确 tag **UNKNOWN**。
8. **SplitHTTP+HTTP 合并为 XHTTP 的精确 tag**：官方 news 只说 v24.9.30 起"下个版本合并"，
   我实测 `xhttp` 别名自 **v24.10.31** 出现 → 是否 v24.10.16 已有其他合并迹象，**UNKNOWN**。
9. **`transport/internet/splithttp/config.go` 之外** XHTTP 字段（`mode`/`extra`/`noSSEHeader`/`downloadSettings`）的 JSON tag 归属：
   我只在 `infra/conf/transport_method.go`（v26.7.11+）确认；**26.3.27 及以前的对应 tag 位置未逐项核对** → UNKNOWN。
10. **`cMaxLifetimeMs`**：仅在 #4113 讨论中被顺带提及，官方文档与内核源码中**未找到** → UNKNOWN（可能是历史名）。
11. **"VLESS without flow 被弃用"**：我无法在任何 main 源码中找到该 warning（已全树 grep `without flow` /
   所有 `Print*FeatureWarning` 调用点 → 无此条）。若某处（如 discussion #5568）确有该文案，**其对应版本与是否生效均 UNKNOWN**。
12. **about/news.html 中我未用源码复核的条目**：MTProto/Starlark/VMess-MD5 移除（v1.8.3）、
    QUIC/DomainSocket 移除（v24.9.7）、SplitHTTP 仅兼容 v1.8.24（移除了 `ok`）、XUDP 控制项（v1.8.1）→
    均为**新闻页单一来源**，未逐版本源码复核。
13. **masque / xdrive 的字段完整语义与运行时行为**：只确认 v26.9.30 起存在 `case "masque"`/`case "xdrive"` 与 JSON 结构体 →
    字段级语义、与分享 URI 的关系 **UNKNOWN**。
14. **TUN 入站**：已确认 `infra/conf/tun.go` 自 v26.1.23 存在、main 无 `with_gvisor`/`with_wintun` 构建标签（只有 OS/arch 约束）。
    但**"Xray 是否仍需特殊构建才带 gVisor 栈"在 v26.1.23 时期的情况未核对**，且 TUN 的字段语义/平台差异未展开 → UNKNOWN。
15. **各字段在"入站 vs 出站"的有效性差异**（例如 `acceptProxyProtocol` 仅入站、`rejectUnknownSni` 仅服务端）：
    文档有说明的部分已标注，**未逐字段穷举** → UNKNOWN。
16. **`sniffing` / `routeOnly` / `targetStrategy` / `sendThrough` 等非节点能力字段**：与"节点能否完整使用"弱相关，本轮未展开 → UNKNOWN。

---

### 附：本文用到的"版本门槛"速查（全部来自 `[src]` 跨 tag 比对）

```
v24.9.7   DomainSocket/QUIC 传输移除（[doc] news，未源码复核）
v24.9.30  network:"raw" 别名；TCP→RAW 改名
v24.10.31 network:"xhttp" 别名；SplitHTTP→XHTTP
v24.12.31 HTTP/H2/H3/QUIC 给出明确 removed 硬错误；curvePreferences 出现
v25.7.26  ECH(echServerKeys/echConfigList)、mldsa65Seed/mldsa65Verify 出现
v25.9.11  VLESS Encryption: mlkem768x25519plus 出现
v26.1.23  NonRemovalDeprecatedFeatureWarning 机制；finalmask；hysteria 传输；TUN 入站
          (infra/conf/tun.go)；pinnedPeerCertSha256；allowInsecure 在此版本仍生效
v26.1.31  allowInsecure 立即硬报错（v26.1.23 仍生效；v26.2.2 同）
v26.2.6   allowInsecure 改为"2026-06-01 前警告+生效"的时间闸门（持续到 v26.5.9）；
          verifyPeerCertByName 出现；mKCP header/seed 由"生效"改为硬报错
v26.3.27  最后一个 prerelease=false 标签（本文基线；仍带 allowInsecure 时间闸门）
v26.7.11  allowInsecure 时间闸门消失（恒报错）；mKCP congestion/readBufferSize/writeBufferSize
          消失，改 cwndMultiplier/maxSendingWindow；VMess security:"zero" 分支消失；
          sessionIDPlacement 系出现；infra/conf 拆出 transport_method.go / transport_security.go
v26.7.28  streamSettings.method 出现；mkcp-legacy 面具出现
v26.9.8   出站 proxySettings 改为硬报错
v26.9.30  kcpSettings.header/seed 由"硬报错"退化为"静默忽略"；masque / xdrive 传输出现
main      useSystemCA / sessionIDTable(PredefinedTable) 等仅存在于 main，未发布
```
