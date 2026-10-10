# sing-box 能力清单（Kernel Capability Inventory — sing-box）

**基线版本：sing-box 1.14.2**（本项目指定基准；`v1.14.2` tag 存在，见 §0.3）。
上游另有 `1.14.3` 与 `1.15.0-alpha.*`；**sing-box.sagernet.org 官网文档当前跟随 1.15.0-dev**，
本文所有 `[doc]` 引用**优先使用 tag 内置文档**（`docs/**` 随源码发布，与 tag 严格同版本），
官网 URL 仅作为等价可访问位置给出。文末 §0.5 说明官网与 tag 文档的版本错位。

任务要求的四层区分贯穿全文：
`Node Feature` → `URI Representation` → `Kernel Representation`（sing-box JSON 字段）→ `Runtime Support`。

---

## 0. 证据来源

### 0.1 官方文档 `[doc]`

| # | 内容 | URL | 抓取方式 |
|---|---|---|---|
| D1 | V2Ray Transport（**权威 transport 列表**） | https://sing-box.sagernet.org/configuration/shared/v2ray-transport/ | 官网 HTML + tag 内置 `docs/configuration/shared/v2ray-transport.md` |
| D2 | TLS（Reality / ECH / uTLS 全字段 + 版本门槛） | https://sing-box.sagernet.org/configuration/shared/tls/ | 同上 `docs/configuration/shared/tls.md` |
| D3 | Multiplex | https://sing-box.sagernet.org/configuration/shared/multiplex/ | 同上 |
| D4 | Dial Fields（detour / bind / netns / domain_resolver） | https://sing-box.sagernet.org/configuration/shared/dial/ | 同上 |
| D5 | outbound 索引（类型表） | https://sing-box.sagernet.org/configuration/outbound/ | 同上 `docs/configuration/outbound/index.md` |
| D6 | VLESS / VMess / Trojan / Shadowsocks / HTTP / SOCKS | `/configuration/outbound/{vless,vmess,trojan,shadowsocks,http,socks}/` | 同上 |
| D7 | Hysteria2（端口跳跃 / obfs gecko / realm） | https://sing-box.sagernet.org/configuration/outbound/hysteria2/ | 同上 |
| D8 | ShadowTLS / AnyTLS / TUIC / Hysteria(v1) | `/configuration/outbound/{shadowtls,anytls,tuic,hysteria}/` | 同上 |
| D9 | Route | https://sing-box.sagernet.org/configuration/route/ | 同上 `docs/configuration/route/index.md` |
| D10 | DNS | https://sing-box.sagernet.org/configuration/dns/ | 同上 |
| D11 | Deprecated Feature List（**移除版本权威表**） | https://sing-box.sagernet.org/deprecated/ | tag 内置 `docs/deprecated.md` |
| D12 | Build from source（**build tag 权威表**） | https://sing-box.sagernet.org/installation/build-from-source/ | tag 内置 `docs/installation/build-from-source.md` |
| D13 | Change Log（版本时间线） | https://sing-box.sagernet.org/changelog/ | 官网 HTML |

### 0.2 官方源码 `[src]`（仓库 `SagerNet/sing-box`，逐 tag 比对）

主要锚点（路径均在 tag `v1.14.2`）：

- `option/outbound.go` — `Outbound.UnmarshalJSONContext`（`unknown outbound type: `）、`DialerOptions` / `AbstractDialerOptions`
- `option/v2ray_transport.go` — `_V2RayTransportOptions.Type enum:"http,ws,quic,grpc,httpupgrade"`；`MarshalJSON` 的 `unknown transport type: `
- `option/tls.go` — `OutboundTLSOptions` / `OutboundUTLSOptions` / `OutboundECHOptions` / `OutboundRealityOptions` / `InboundRealityOptions`
- `option/vless.go`、`option/vmess.go`、`option/trojan.go`、`option/shadowsocks.go`、`option/hysteria2.go`、`option/hysteria.go`、`option/tuic.go`、`option/shadowtls.go`、`option/anytls.go`、`option/simple.go`、`option/group.go`、`option/direct.go`
- `option/multiplex.go` — `OutboundMultiplexOptions.Protocol enum:"h2mux,smux,yamux"`
- `option/udp_over_tcp.go`、`option/http.go`（`HTTP2Options`/`QUICOptions`/`HTTPClientOptions`）、`option/route.go`、`option/inbound.go`、`option/options.go`（`decoder.DisallowUnknownFields()`）
- `constant/proxy.go`（类型名常量）、`constant/v2ray.go`（**仅 5 个 transport 常量**）、`constant/rule.go`
- `transport/v2ray/transport.go` — `NewServerTransport` / `NewClientTransport` switch，`default: E.New("unknown transport type: " + options.Type)`
- `transport/v2ray/grpc.go`（`//go:build with_grpc`）vs `transport/v2ray/grpc_lite.go`（`//go:build !with_grpc`）
- `transport/sip003/obfs.go`、`transport/sip003/v2ray.go`（**仅注册 2 个插件**）
- `common/tls/utls_client.go`（`uTLSClientHelloID`）、`common/tls/reality_client.go`、`common/tls/ech.go`
- `include/registry.go`（`OutboundRegistry` + `registerStubForRemovedOutbounds`）、`include/quic.go`（`//go:build with_quic`）
- `release/DEFAULT_BUILD_TAGS`、`release/DEFAULT_BUILD_TAGS_OTHERS`、`release/DEFAULT_BUILD_TAGS_WINDOWS`
- 外部依赖 `github.com/sagernet/sing-vmess v0.2.8` `client.go` `NewClient`（vmess `security` 取值集合）
- 外部依赖 `github.com/SagerNet/sing` `common/json/badjson/`（配置解码路径）

方法：`raw.githubusercontent.com` 按 tag 拉取单文件；另下载 `codeload.github.com` 的 **v1.14.2 全量 tarball**（1755 条目）
用于全树 grep（例如"xhttp/splithttp 是否在任何位置出现"这种**否定性结论**）。

### 0.3 实际内核运行验证 `[test]`

**本轮有 `[test]` 证据**（与 `research/kernel-xray.md` 的"0 条 `[test]`"不同）。方法：

| 二进制 | 来源 | 标签 | 用途 |
|---|---|---|---|
| `/tmp/sing-box-plain` | 本文自建：v1.14.2 tarball + Go 1.25.5，`go build ./cmd/sing-box`（**无 tag**） | （无） | 探测"缺 tag ⇒ 能力缺失"的形态 |
| `/tmp/sing-box-tagged` | 同上，`-tags with_quic,with_utls,with_wireguard` | with_quic,with_utls,with_wireguard | 探测 Reality/uTLS/QUIC 正常形态 |
| `/root/catmi/sing-box/sing-box` | **工作区已有的官方发行版** | `with_gvisor,with_quic,with_dhcp,with_wireguard,with_utls,with_acme,with_clash_api,with_tailscale,with_ccm,with_ocm,with_cloudflared,with_naive_outbound,with_usbip,with_openvpn,with_openconnect,badlinkname,tfogo_checklinkname0,with_purego` | **交叉复核**（关键结论都在官方二进制上复现过） |

手法：`sing-box check -c <config>`，约 55 条配置。全部为**静态校验层**（Tier A）；
**没有任何连通性/语义回环（Tier B）验证** —— 即"校验通过 ≠ 与对端内核互通"。凡属于后者一律进 §8。

> ⚠️ 版本口径提醒：工作区已有的官方二进制自报 **`sing-box version 1.14.1`**，
> 而 `research/empirical/probe-results.json` 的 `kernels.singbox.version` 记为 `"sing-box version 1.14.2"`。
> 两者不一致，见 §7.9。本文的 `[test]` 结论在 **1.14.1（官方构建）** 与 **1.14.2（自建）** 上均已复现，
> 故版本口径不影响本文结论，但会影响依赖该 JSON 的下游结论。

### 0.4 关于"猜测"

凡未查到者一律写 `UNKNOWN` 并进 §8；**没有**任何条目是"按 Xray/mihomo 的习惯推断"的。
特别地：本文**没有**做跨内核连通性测试，因此所有"与 Xray/mihomo 互通"的判断都停在
"字段/实现是否存在"，不外推到"能不能连上"。

### 0.5 官网文档与 tag 文档的版本错位（重要）

- 官网 `sing-box.sagernet.org` 当前含 `Changes in sing-box 1.15.0`、`Since sing-box 1.15.0` 条目
  ⇒ 官网 = **1.15.0-dev**。
- tag `v1.14.2` 内置 `docs/**` **不含任何 1.15.0 字样**（已 grep 确认）⇒ 与 1.14.2 严格对应。
- 因此**以 1.14.2 为基线时必须用 tag 内置文档**。实例：官网 TLS 页有 `certificate_sha256`（Since 1.15.0），
  而 1.14.2 二进制对该字段报 `unknown field`（`[test]`，见 §3.4）。**若照官网写映射表会直接产出 FATAL 配置。**

---

## 1. outbound 类型清单

`type` 字符串即 `constant/proxy.go` 中的常量值。版本门槛由**逐 tag 拉取 `constant/proxy.go` 求首次出现**得到（`[src]` 方法），
最小 tag 集合 `v1.1.0 v1.2.0 v1.3.0 v1.4.0 v1.5.0 v1.6.0 v1.7.0 v1.8.0 v1.9.0 v1.10.0 v1.11.0 v1.12.0 v1.13.0 v1.14.0 v1.14.2`。

| type | 支持（版本） | 必填字段（1.14.2） | 证据 |
|---|---|---|---|
| `direct` | ✅ 全版本（≥1.1.0） | 无 | `[src]` `option/direct.go`；`[test]` 官方二进制 `{"type":"direct","tag":"d"}` accepted |
| `block` | ✅ ≥1.1.0 | 无 | `[src]` `constant/proxy.go`；`include/registry.go` `block.RegisterOutbound` |
| `socks` | ✅ ≥1.1.0 | `server`,`server_port` | `[src]` `option/simple.go` `SOCKSOutboundOptions`（`version` enum `4,4a,5`） |
| `http` | ✅ ≥1.1.0 | `server`,`server_port` | `[src]` `option/simple.go` `HTTPOutboundOptions` |
| `shadowsocks` | ✅ ≥1.1.0 | `server`,`server_port`,`method`,`password` | `[src]` `option/shadowsocks.go`；`[test]` method 非法 ⇒ `unknown method: bogus` |
| `vmess` | ✅ ≥1.1.0 | `server`,`server_port`,`uuid`（`security` 在 struct 中无 `omitempty`，实际按默认 `auto`） | `[src]` `option/vmess.go`；`[test]` |
| `trojan` | ✅ ≥1.1.0 | `server`,`server_port`,`password` | `[src]` `option/trojan.go` |
| `vless` | ✅ ≥1.1.0 | `server`,`server_port`,`uuid` | `[src]` `option/vless.go`；`[test]` |
| `shadowtls` | ✅ ≥1.1.0 | `server`,`server_port`；`version`(1/2/3)；v2/v3 需 `password`；`tls` Required | `[src]` `option/shadowtls.go`；`[doc]` D8；`[test]` `version:4` ⇒ `unknown protocol version: 4` |
| `hysteria`（v1） | ✅ ≥1.1.0（QUIC） | `server`,`server_port`；`up_mbps`/`down_mbps` 或 `up`/`down` 必填其一 | `[src]` `option/hysteria.go`；`[test]` 缺下行速率 ⇒ `missing download speed` |
| `tuic` | ✅ **≥1.4.0**（QUIC） | `server`,`server_port`,`tls` | `[src]` `constant/proxy.go` 首次出现 v1.4.0；`option/tuic.go` |
| `hysteria2` | ✅ **≥1.5.0**（QUIC） | `server`,`server_port`,`tls`；`password` 可选（多用户场景） | `[src]` 首次出现 v1.5.0；`option/hysteria2.go` |
| `anytls` | ✅ **≥1.12.0** | `server`,`server_port`,`tls`（**Required**） | `[src]` 首次出现 v1.12.0；`[doc]` D8 "Since sing-box 1.12.0"；`[test]` 去 tls ⇒ `TLS required` |
| `snell` | ✅ **≥1.14.0** | 见 `option/snell.go`（本文未展开，未验证） | `[src]` 首次出现 v1.14.0 |
| `naive`（NaiveProxy） | ⚠️ 类型 ≥1.1.0，**outbound 注册 ≥1.13.0 且受 build tag 控制** | — | `[src]` `include/naive_outbound.go`（`//go:build !with_naive_outbound` 有 stub）；`[doc]` D12；`[test]` plain 构建 ⇒ `naive outbound is not included in this build` |
| `tor` | ✅ ≥1.1.0 | 无 | `[src]` `constant/proxy.go`；`[test]` plain 构建 accepted（`with_embedded_tor` 仅影响内嵌实现） |
| `ssh` | ✅ ≥1.1.0 | — | `[src]` `constant/proxy.go`；`include/registry.go` |
| `selector` | ✅ ≥1.1.0 | `outbounds` | `[src]` `option/group.go`；`[test]` accepted |
| `urltest` | ✅ ≥1.1.0 | `outbounds` | `[src]` `option/group.go`；`[test]` accepted |
| `wireguard` | ❌ **已于 1.13.0 移除**（改为 `endpoints[]` 的 `wireguard`） | — | `[src]` `include/registry.go` `registerStubForRemovedOutbounds`；`[doc]` D11；`[test]` 两种错误形态（见 §6） |
| `dns` | ❌ **1.11.0 弃用 / 1.13.0 移除** | — | `[src]` `option/outbound.go` 显式 `switch` 拦截；`[test]` |
| `shadowsocksr` | ❌ **1.6.0 移除**（常量仍在，注册为报错 stub） | — | `[src]` `registerStubForRemovedOutbounds`；`[test]` `ShadowsocksR is deprecated and removed in sing-box 1.6.0` |

**注册表口径（`[src]` `include/registry.go` `OutboundRegistry()`）**：真正被注册的 outbound 为
`direct, bridge, block, selector, urltest, socks, http, shadowsocks, snell, vmess, trojan, naive*, tor, ssh, shadowtls, vless, anytls`
加 `registerQUICOutbounds`（`hysteria, tuic, hysteria2`，受 `with_quic`）加 `registerStubForRemovedOutbounds`（`shadowsocksr, wireguard` 报错）。
`*` naive 受 `with_naive_outbound` 控制。

### 1.1 文档与源码不一致（`docs/configuration/outbound/index.md` 已过期）

- `[doc]` D5（tag 内置 1.14.2 版）仍把 `wireguard` 与 `dns` 列为 outbound 类型；
  `[src]`/`[test]` 证明二者在 1.14.2 中**都是报错 stub**。
- ⇒ **兼容层不能拿文档类型表当白名单**，必须以 `include/registry.go` 为准。
- `[doc]` 官网（1.15-dev）该表还多了 `tailcat`；tag 1.14.2 表中无 `tailcat`。

---

## 2. transport 清单

### 2.1 结论先行

**sing-box 只有 5 个 transport，且永远只有这 5 个：`http` / `ws` / `quic` / `grpc` / `httpupgrade`。**

- `[src]` `constant/v2ray.go`：仅定义 `V2RayTransportTypeHTTP|Websocket|QUIC|GRPC|HTTPUpgrade`。
- `[src]` `option/v2ray_transport.go`：`Type` 的 `enum:"http,ws,quic,grpc,httpupgrade"`，两个 switch 的 `default` 均为 `unknown transport type: `。
- `[src]` **全树否定性证据**：对 v1.14.2 全量 tarball（1755 条目）grep `xhttp|splithttp`（大小写不敏感）
  → **0 命中**。`transport/` 目录实际子项为 `openconnect, openvpn, simple-obfs, sip003, trojan, v2ray, v2raygrpc, v2raygrpclite, v2rayhttp, v2rayhttpupgrade, v2rayquic, v2raywebsocket, wireguard`——**无 xhttp/splithttp**。
- `[doc]` D1：*"Available transports: HTTP, WebSocket, QUIC, gRPC, HTTPUpgrade"*；
  并明确 "Difference from v2ray-core: **No TCP transport**, plain HTTP is merged into the HTTP transport. **No mKCP transport**. **No DomainSocket transport**."
- `[test]`（官方 1.14.1 与自建 1.14.2 均复现）：
  `xhttp` ⇒ `FATAL ... outbounds[0].transport: unknown transport type: xhttp`；
  `splithttp`、`tcp`、`kcp` ⇒ 同形态 FATAL；
  `ws`/`http`/`httpupgrade`/`grpc` ⇒ exit 0。

### 2.2 逐条对照表

| sing-box transport | 支持（版本） | Xray 传输名 | mihomo 传输名 | 证据 |
|---|---|---|---|---|
| `http` | ✅ ≥1.1.0 | ⚠️ **现行无对应**：Xray 传输列表已不含 HTTP/2；`/config/transports/{http,h2}.html` 只剩一行 "See XHTTP: Beyond REALITY"（并入 XHTTP） | `h2` / `http`（mihomo VLESS `network` 仍列） | `[src]`；`[doc]` D1 + Xray 传输列表页；`[test]` accepted |
| `ws` | ✅ ≥1.1.0 | `ws`（WebSocket） | `ws` | `[src]`；`[test]` accepted |
| `quic` | ✅ ≥1.1.0 | ⚠️ **现行无对应**：`/config/transports/quic.html` 只剩 "See XHTTP: Beyond REALITY" | 未在 VLESS/Trojan 文档的 `network` 列出 | `[src]`；`[doc]` Xray 传输列表页；`[test]` 无 TLS ⇒ `create client transport: quic: TLS required`（说明类型被识别，**不是** build tag 缺失） |
| `grpc` | ✅ ≥1.1.0，**但默认构建是 lite 实现** | `grpc`（标准 gRPC） | `grpc` | `[src]` `grpc.go`/`grpc_lite.go` 双实现；`[test]` 官方二进制 tags 无 `with_grpc`，符号表仅含 `v2raygrpclite`（`v2raygrpc.NewClient` = 0 命中）；`[doc]` D1/D12 |
| `httpupgrade` | ✅ **≥1.7.0** | `httpupgrade` | 未在 VLESS/Trojan 文档的 `network` 列出 | `[src]` `constant/v2ray.go` v1.6.0 无、v1.7.0 有；`[test]` accepted |
| **`xhttp`** | ❌ **完全不存在（任何版本）** | ✅ `xhttp`（旧名 `splithttp`） | ✅ `xhttp`（VLESS `network` 取值之一） | `[src]` 全树 0 命中 + enum 无此项；`[test]` FATAL；`[doc]` Xray 传输列表含 XHTTP，mihomo VLESS 页 `network` 含 `xhttp` |
| **`tcp` / `raw`** | ❌ 不存在（**无 `tcp` transport 名**） | ✅ `raw`（原 `tcp`） | ✅ 默认（`network` 不设即 TCP） | `[doc]` D1 "No TCP transport"；`[test]` `{"type":"tcp"}` ⇒ FATAL |
| **`mkcp` / `kcp`** | ❌ 不存在 | ✅ `mkcp` | — | `[doc]` D1；`[test]` FATAL |
| **DomainSocket** | ❌ 不存在 | 不在 Xray 现行传输列表 | — | `[doc]` D1（"No DomainSocket transport"） |
| （独立 outbound 而非 transport）`hysteria` | ✅ `type:"hysteria"` | ✅ 作为**传输**：Xray 传输列表含 `Hysteria` | — | `[src]` `constant/proxy.go`；`[doc]` Xray 传输列表 —— **模型差异，见 §7** |
| SIP003 `obfs-local` / `v2ray-plugin` | ✅（shadowsocks `plugin` 字段） | shadowsocks SIP003 | shadowsocks SIP003 | `[src]` 仅 2 处 `RegisterPlugin("obfs-local")`、`RegisterPlugin("v2ray-plugin")`；`[test]` 其它插件名 ⇒ `plugin not found: simple-obfs` |

> ⚠️ **两边的传输集合交集比预期更小（重要结论）**
> Xray 现行 7 种传输 = `RAW, XHTTP, mKCP, gRPC, WebSocket, HTTPUpgrade, Hysteria`；
> sing-box 5 种 = `http, ws, quic, grpc, httpupgrade`。
> 逐项取交集后**真正同名的只有 3 个：`ws` / `grpc` / `httpupgrade`**。
> - sing-box 的 `http`、`quic` 在 Xray 侧**已无对应**（页面并入 XHTTP）；
> - Xray 的 `RAW`/`XHTTP`/`mKCP`/`Hysteria` 在 sing-box 侧**均无对应**；
> - 更糟的是 `grpc` 虽然同名，官方 sing-box 走的是 grpc-lite（§7.5），**同名不等于互通**。
> ⇒ 跨内核（Xray↔sing-box）真正可无损映射的传输，**目前只有 `ws` 与 `httpupgrade` 两个是"同名且实现标准"的**，
> `grpc` 需 `with_grpc` 构建，其余全部需要"降级 / 改写 / 判 UNSUPPORTED"。

> **参考 URL**：Xray 传输列表 https://xtls.github.io/en/config/transports/index.html ；
> mihomo VLESS `network` 取值 https://wiki.metacubex.one/en/config/proxies/vless/ ；
> mihomo Trojan `network` 为 `ws / grpc`（https://wiki.metacubex.one/en/config/proxies/trojan/）。

### 2.3 语义陷阱：`"transport": {}` 与 `"transport": {"type": ""}` 不等价

`[test]` 实测（两种二进制一致）：

| 写法 | 结果 |
|---|---|
| 省略 `transport` | exit 0 |
| `"transport": null` | exit 0 |
| `"transport": {}` | **exit 0**（被当作"无 transport"） |
| `"transport": {"type": ""}` | **exit 1** ⇒ `unknown transport type: ` |
| `"transport": {"type": "ws", "bogus": 1}` | exit 1 ⇒ `transport.bogus: json: unknown field "bogus"` |

⇒ 空对象走"无 transport"路径（`[src]` `transport/v2ray/transport.go` `if options.Type == "" { return nil, nil }`），
但显式空字符串会撞到 `UnmarshalJSON` 的 `default`。**兼容层生成配置时，不要输出 `{"type": ""}` 这种占位。**

---

## 3. TLS / Reality / ECH / uTLS

结构：**TLS 不是 transport 的一层，而是 outbound 上的 `tls` 对象**（`OutboundTLSOptionsContainer`，`"tls": {...}`）。
这与 Xray 的 `streamSettings.security` / `tlsSettings` / `realitySettings` 分层不同。

### 3.1 字段表（`[src]` `option/tls.go` @v1.14.2 + `[doc]` D2）

| 能力 | sing-box 字段 | 版本门槛 | URI 表达（分享链接约定） | 证据 |
|---|---|---|---|---|
| 启用 TLS | `tls.enabled` | ≥1.1.0 | `security=tls` | `[src]` |
| SNI | `tls.server_name` | ≥1.1.0 | `sni=` | `[src]`；`[test]` accepted |
| 跳过证书校验 | `tls.insecure` | ≥1.1.0 | `allowInsecure=1` / `insecure=1`（**名字随客户端而异**） | `[src]`；`[test]` Xray 名 `allowInsecure` 在 sing-box ⇒ `unknown field "allowInsecure"` |
| 不发送 SNI | `tls.disable_sni` | ≥1.1.0（**client only**） | 通常无 | `[src]`；`[test]` 无对应 Xray 名 |
| ALPN | `tls.alpn`（可字符串或数组） | ≥1.1.0 | `alpn=h2,http/1.1` | `[src]` `badoption.Listable[string]` |
| TLS 版本 | `tls.min_version` / `tls.max_version`（`1.0/1.1/1.2/1.3`） | ≥1.1.0 | 通常无 | `[src]`；`[test]` `9.9` ⇒ `parse min_version: unknown tls version:9.9`（**运行期**校验，非 decode 期） |
| 密码套件 | `tls.cipher_suites` | ≥1.1.0 | 通常无 | `[src]` |
| 曲线偏好 | `tls.curve_preferences`（`P256/P384/P521/X25519/X25519MLKEM768`） | **≥1.13.0** | 无 | `[src]` 逐 tag 比对首现 v1.13.0；`[doc]` D2 |
| 证书固定（公钥） | `tls.certificate_public_key_sha256` | **≥1.13.0** | 无 | `[src]`；`[doc]` D2 |
| 证书固定（整证书） | `tls.certificate_sha256` | **≥1.15.0 ⇒ 1.14.2 无此字段** | 无 | `[doc]` 官网 D2 (Since 1.15.0)；`[test]` 1.14.2 二进制 ⇒ `unknown field "certificate_sha256"` |
| 客户端证书（mTLS） | `tls.client_certificate` / `_path` / `client_key` / `_path` | **≥1.13.0** | 通常无 | `[src]`；`[doc]` D2 |
| 服务端要求客户端证书 | `tls.client_authentication`（`no/request/require-any/verify-if-given/require-and-verify`） | **≥1.13.0**（server only） | 无 | `[src]` |
| TLS 引擎 | `tls.engine`（`go/apple/windows`） | **≥1.14.0** | 无 | `[src]`；`[test]` `apple` on Linux ⇒ `Apple TLS engine is not available on non-Apple platforms` |
| 握手超时 | `tls.handshake_timeout` | **≥1.14.0** | 无 | `[src]` |
| 证书提供者 | `tls.certificate_provider` | **≥1.14.0**（server only） | 无 | `[src]`；`[doc]` D2 |
| 内联 ACME | `tls.acme`（**inbound/server only**） | 1.14.0 起弃用，1.16.0 移除 | 无 | `[test]` inbound ⇒ `WARN inline ACME options ... deprecated`；**outbound 上该字段直接 `unknown field "acme"`** |
| TLS 分片 | `tls.fragment` / `fragment_fallback_delay` | **≥1.12.0** | 无（Xray 有 `finalMask`，非同一机制） | `[src]`；`[test]` accepted |
| TLS record 分片 | `tls.record_fragment` | **≥1.12.0** | 无 | `[src]`；`[test]` accepted |
| SNI 欺骗 | `tls.spoof` / `spoof_method` | **≥1.14.0**；仅 Linux/macOS/Windows 且需高权限 | 无 | `[src]`；`[test]` 缺 SNI ⇒ `\`spoof\` requires TLS ClientHello with SNI` |
| 内核 TLS 卸载 | `tls.kernel_tx` / `kernel_rx` | **≥1.13.0**（Linux 5.1+，仅 TLS1.3） | 无 | `[src]`；`[test]` accepted（校验层不检查内核版本） |
| uTLS | `tls.utls.enabled` + `tls.utls.fingerprint` | 见 §3.2 | `fp=chrome` | `[src]` |
| ECH | `tls.ech.*` | 见 §3.3 | 通常无 | `[src]` |
| Reality | `tls.reality.*` | 见 §3.4 | `security=reality&pbk=...&sid=...` | `[src]` |

### 3.2 uTLS

- `[src]` `option/tls.go` `OutboundUTLSOptions{Enabled, Fingerprint}`；
  `common/tls/utls_client.go` `uTLSClientHelloID` 的 switch 决定合法值。
- 合法指纹（`[src]` switch + `[doc]` D2）：`chrome`(含空串)、`firefox`、`edge`、`safari`、`360`、`qq`、`ios`、`android`、`random`、`randomized`。
- **`chrome_psk` / `chrome_psk_shuffle` / `chrome_padding_psk_shuffle` / `chrome_pq` / `chrome_pq_psk` 已被移除**：
  `[src]` 这 5 个 case 与 `chrome` 一起 `fallthrough` 到 `utls.HelloChrome_Auto`（静默降级，**不报错**）；
  `[doc]` D2 "Removed since sing-box 1.10.0 ... will fallback to chrome"；`[test]` `chrome_psk` ⇒ exit 0。
  ⚠️ **但 `option/tls.go` 的 `enum` 标签仍列着这 5 个旧值** ⇒ schema 与实际行为不一致。
- `[test]` 非法指纹 ⇒ `initialize outbound[0]: unknown uTLS fingerprint: bogus`（**运行期**，非 decode 期）。
- **uTLS 受 build tag `with_utls` 控制**：`[test]` plain 构建 ⇒
  `uTLS is not included in this build, rebuild with -tags with_utls`；官方发行版 tags **包含** `with_utls`。

### 3.3 ECH

- `[src]` `OutboundECHOptions{Enabled, Config[](Listable[string]), ConfigPath, QueryServerName, +2 deprecated}`；
  `InboundECHOptions{Enabled, Key[](Listable), KeyPath, +2 deprecated}`。
- 版本门槛：`[doc]` D2 官网把 `ech.query_server_name` 标为 **Since 1.13.0**；`[test]` accepted。
- **已移除字段**：`ech.pq_signature_schemes_enabled`、`ech.dynamic_record_sizing_disabled`
  （1.12.0 弃用 / 1.13.0 移除）。`[test]` 二者 ⇒ `legacy ECH options are deprecated in sing-box 1.12.0 and removed in sing-box 1.13.0`。
  注意：字段**仍在 struct 里**（`schema:"omit"`），所以报的是运行期错误而不是 `unknown field`。
- ECH 实现自 1.12.0 迁移到 **stdlib**（`[src]` `common/tls/ech.go` 带 `//go:build go1.24`；
  `common/tls/ech_tag_stub.go` 声明 `with_ech` tag 已废弃）。⇒ **不再依赖 `with_ech`。**
- `[test]` 官方二进制（含 `with_utls`）上 `tls.ech.enabled=true` ⇒ accepted。

### 3.4 Reality

- `[src]` `OutboundRealityOptions{Enabled, PublicKey, ShortID}`（**客户端只有 3 个字段**）；
  `InboundRealityOptions{Enabled, Handshake{ServerOptions+DialerOptions}, PrivateKey, ShortID(Listable), MaxTimeDifference}`。
- **硬约束：Reality 客户端必须同时开 uTLS。** `[src]` `common/tls/reality_client.go`：
  `if options.UTLS == nil || !options.UTLS.Enabled { return nil, E.New("uTLS is required by reality client") }`；
  `[test]` 官方二进制实测 ⇒ `uTLS is required by reality client`（不因官方含 `with_utls` 而豁免）。
- 另一个硬约束：`spoof` 与 reality 互斥。`[src]` `E.New("spoof is unsupported in reality")`；`[test]` 复现。
- `[src]` reality 实现依赖 `github.com/metacubex/utls`（**非** refraction-networking/utls），文件带 `//go:build with_utls`；
  plain 构建 ⇒ `[test]` `uTLS, which is required by reality is not included in this build, rebuild with -tags with_utls`。
- 版本门槛：`option/tls.go`/`option/outbound.go` 的 `reality` json tag 在 **v1.2.0 首次出现**（`[src]` 逐 tag 比对；
  v1.1.0 无，v1.2.0 有）。
- `short_id`：客户端是 `string`，服务端是 `Listable[string]`（`[src]`）。
- 实心中间人（handshake）只在**服务端**配置；客户端不配置 `handshake`（这是与"Xray 客户端也需要 dest"的常见误解相对的点，具体见 §7）。

---

## 4. 高级能力

### 4.1 multiplex（多路复用）

- `[src]` `option/multiplex.go`：
  - `OutboundMultiplexOptions{Enabled, Protocol enum:"h2mux,smux,yamux", MaxConnections, MinStreams, MaxStreams, Padding, Brutal}`
  - `InboundMultiplexOptions{Enabled, Padding, Brutal}`
- `[doc]` D3：默认 `h2mux`；`max_connections` 与 `max_streams` 互斥（`min_streams` 同）。
- **`[test]` 决定性否定证据：`protocol:"mux.cool"` ⇒ `FATAL initialize outbound[0]: unknown protocol: mux.cool`。**
  `smux`/`yamux`/`h2mux` ⇒ exit 0。
- ⇒ **sing-box 没有 Mux.Cool。** Xray 的 `mux`（Mux.Cool）与 sing-box 的 `multiplex` **不是同一协议**，
  仅有 `smux`/`yamux`/`h2mux` 三者；跨内核做 mux 时不能假设可互通。**见 §7.3（高优先级）。**
- `brutal`（TCP Brutal）是 sing-box 的 multiplex 子项（`BrutalOptions{Enabled,UpMbps,DownMbps}`）`[src]`。

### 4.2 dialer（`Dial Fields`）

`[src]` `option/outbound.go` `DialerOptions` / `AbstractDialerOptions` + `[doc]` D4：

| 字段 | 说明 | 版本门槛 |
|---|---|---|
| `detour` | 上游 outbound tag；**启用后其它 dial 字段被忽略** | ≥1.1.0（关键：**这是 sing-box 的链式代理机制**，等价于 Xray 的 `dialerProxy`/`sockopt.dialerProxy`） |
| `bind_interface` | 绑定网卡 | ≥1.1.0 |
| `inet4_bind_address` / `inet6_bind_address` | 绑定源地址 | ≥1.1.0 |
| `bind_address_no_port` | 不预留源端口（仅 Linux） | **≥1.13.0** |
| `routing_mark` | fwmark（仅 Linux，支持 `"0x1234"`） | ≥1.1.0 |
| `reuse_addr` | — | ≥1.1.0 |
| `netns` | 网络命名空间（仅 Linux） | **≥1.12.0**；1.14.0 起支持引用 tag |
| `connect_timeout` | — | ≥1.1.0 |
| `tcp_fast_open` / `tcp_multi_path` | TFO / MPTCP | ≥1.1.0 |
| `disable_tcp_keep_alive` / `tcp_keep_alive` / `tcp_keep_alive_interval` | 1.13.0 新增；默认值由 10m 改 5m | **≥1.13.0** |
| `udp_fragment` | — | ≥1.1.0 |
| `domain_resolver` | 域名解析器（**1.14.0 起 server 为域名时必需**） | **≥1.12.0** |
| `domain_strategy` | **已弃用（1.12.0），文档声明 1.14.0 移除** | ⚠️ `[test]` 1.14.2 上**仍 accepted**（字段仍在 struct，`schema:"omit"`）—— 见 §6.3 |
| `network_strategy` / `network_type` / `fallback_network_type` / `fallback_delay` | 仅图形客户端（Android/Apple + `auto_detect_interface`） | **≥1.11.0** |

- `[test]` `network_strategy:"bogus"` ⇒ `decode config ... unknown network strategy: bogus`（自定义 Unmarshal，decode 期报错）。
- `[test]` `domain_strategy:"prefer_ipv4"` ⇒ **exit 0**（未按文档在 1.14.0 移除）。

### 4.3 UDP 相关

- `[src]` `NetworkList`（`option/types.go`）只接受 `tcp` / `udp`，其它 ⇒ `unknown network: <v>`；缺省 = 两者都开。
  `[test]` `network:"quic"` ⇒ `decode config ... unknown network: quic`。
- `packet_encoding`（vless/vmess）：
  - `[src]` `protocol/vless/outbound.go`：**`nil` ⇒ `xudp = true`（默认 XUDP）**；`""` ⇒ 关闭；`packetaddr` / `xudp` ⇒ 对应开启；其它 ⇒ `unknown packet encoding: <v>`。
  - `[test]` `bogus` ⇒ `unknown packet encoding: bogus`；`xudp` ⇒ accepted。
  - ⚠️ **默认值是 XUDP**（不是"关闭"），这一点与"Xray 需显式开 xudp"不同 —— 见 §7.4。
- `udp_over_tcp`：`[src]` `option/udp_over_tcp.go`，可写 `false`/`true` 或对象 `{enabled, version: 1|2}`。
  `[test]` **`version: 3` 被接受（exit 0）** —— `enum` 标签只在 JSON Schema 层生效，**运行期不校验**；该字段的 `UnmarshalJSON` 对未知值静默放行。⚠️ 静默容忍点。

### 4.4 obfs

- **Shadowsocks obfs**：不是独立字段，而是 SIP003 `plugin` + `plugin_opts`。
  `[src]` 全树 `RegisterPlugin` 只有 2 处 ⇒ 仅支持 `obfs-local`、`v2ray-plugin`。
  `[test]` `obfs-local` / `v2ray-plugin` ⇒ accepted；`simple-obfs` ⇒ `plugin not found: simple-obfs`。
- **Hysteria2 obfs**：`[src]` `option/hysteria2.go` `Hysteria2Obfs{Type enum:"salamander,gecko", Password, GeckoOptions{MinPacketSize,MaxPacketSize}}`；
  非法值 ⇒ `unknown obfs type: <v>`（`[test]` 复现）。`gecko` 与 `hop_interval_max`/`bbr_profile`/`disable_chrome_parrot`/`realm` 同为 **1.14.0 新增**（`[doc]` D7）。

### 4.5 端口跳跃（port hopping）

- 仅 **Hysteria2 / Hysteria(v1)** 有：`server_ports`（`Listable[string]`，如 `"2080:3000"`）+ `hop_interval` + `hop_interval_max`。
- `[src]` `option/hysteria2.go` / `option/hysteria.go`；`hop_interval`/`server_ports` = **≥1.11.0**，`hop_interval_max` = **≥1.14.0**（`[doc]` D7）。
- `[test]` `server_ports:["2080:3000"] + hop_interval + hop_interval_max` ⇒ accepted。
- 语义注意（`[doc]` D7）：`server_port` 在设了 `server_ports` 时被**忽略**；`server_ports` 与 `realm` 互斥。
- TUIC / VLESS / VMess / Trojan **没有**端口跳跃。

### 4.6 route / DNS 相关

- `[src]` `option/route.go` `RouteOptions`：`rules, rule_set, final, find_process, find_neighbor(≥1.14.0), dhcp_lease_files(≥1.14.0), auto_detect_interface, override_android_vpn, default_interface, default_mark, default_domain_resolver(≥1.12.0), default_network_strategy/…(≥1.11.0), default_http_client(≥1.14.0)` + **保留但 schema 省略的 `geoip`/`geosite`**。
- `[src]` `constant/rule.go` 的 rule action 全集：
  `route, route-options, evaluate, respond, direct, bypass, reject, hijack-dns, sniff, resolve, predefined`。
  `reject` 还有 `method: default|drop|reply`。
- ⇒ **sing-box 用"规则动作"取代了一大批老字段**（`block`/`dns` outbound、inbound 的 `sniff`、`direct.override_address`、DNS 的 `outbound` 规则项）——这是 §6/§7 的主线。
- `[src]` `option/dns.go`：DNS 服务器是**带 `type` 的对象**（`local/hosts/tcp/udp/tls/https/quic/h3/dhcp/fakeip/mdns/resolved/…`，见 `include/registry.go` `DNSTransportRegistry`）。

### 4.7 Xray 有、sing-box 没有的能力（跨内核 = UNSUPPORTED 清单）

| Xray/mihomo 能力 | sing-box | 证据 |
|---|---|---|
| **XHTTP / splithttp 传输** | ❌ 完全不存在 | §2.1（`[src]` 全树 0 命中 + `[test]` FATAL） |
| **mKCP 传输**（含 `header` 伪装、`seed`） | ❌ 不存在 | `[doc]` D1；`[test]` FATAL |
| **显式 TCP/RAW 传输名** | ❌ 不存在（只有"不写 transport"） | `[doc]` D1；`[test]` `{"type":"tcp"}` FATAL |
| **DomainSocket 传输** | ❌ 不存在 | `[doc]` D1 |
| **Mux.Cool 多路复用** | ❌ 只有 smux/yamux/h2mux | `[test]` `unknown protocol: mux.cool` |
| **XTLS 其它 flow**（`xtls-rprx-direct` 等） | ❌ 只有 `xtls-rprx-vision` | `[test]` `unsupported flow: xtls-rprx-direct`；`[doc]` D6 |
| **`sockopt` 大礼包**（`mark`、`tproxy`、`domainStrategy`、`dialerProxy`、`tcpUserTimeout`…） | ⚠️ 部分等价物分散在 Dial Fields / route（见 §4.2），**没有同名同构的一层** | `[src]` `AbstractDialerOptions`；`[doc]` D4 |
| **标准 gRPC**（默认构建） | ⚠️ 官方二进制只有 grpc-lite | `[src]` 双实现；`[test]` 官方 tags 无 `with_grpc`、符号表仅 lite |
| **`streamSettings.tlsSettings.fingerprint`** | ⚠️ 名为 `tls.utls.fingerprint`（**多一层 `utls`**） | `[test]` `tls.fingerprint` ⇒ `unknown field "fingerprint"` |
| **`allowInsecure`** | ⚠️ 名为 `tls.insecure` | `[test]` ⇒ `unknown field "allowInsecure"` |
| **`alterId`** | ⚠️ 名为 `alter_id` | `[test]` ⇒ `unknown field "alterId"` |
| **VMess `aes-128-ctr`** | ❌ 不支持（合法值是 `aes-128-cfb`） | `[test]` `unsupported security type: aes-128-ctr` |

---

## 5. URI ↔ JSON 映射的损失点

### 5.1 最重要的前提：**sing-box 内核完全不解析分享 URI**

- `[src]` 对 v1.14.2 全树 grep `vmess://`、`vless://`、`trojan://`、`hysteria2://`、`tuic://`、`anytls://`
  → **各 0 命中**；唯一的 `ss://` 命中是 `service/ocm/service_websocket.go` 里的 `"wss://"` 字符串截取（无关）。
- `[src]` 全树 grep `share link` / `sharelink` / `subscription` → 仅命中 CCM/OCM 服务的"Claude Code subscription"文案，**与分享链接无关**。
- `[src]` `cmd/sing-box/` 全部子命令：`api, check, completion, format, generate, geoip, geosite, merge, rule-set, run, schema, tools, version`
  —— **没有 import / convert / subscribe 之类的 URI 入口**。
- `[test]` 把 `vless://...` 当配置文件喂给 `sing-box check` ⇒
  `FATAL decode config at u.txt: invalid character 'v' looking for beginning of value: row 1, column 1`。

⇒ **四层里 `URI Representation` 这一层在 sing-box 侧是空的：sing-box 既不定契约、也不报错、也不丢弃——它根本收不到 URI。**
因此：

1. "URI 参数 → sing-box 字段"的映射**必须由兼容性层（本项目）或客户端自己定义并负责**，内核不会兜底；
2. **"映射不上会被丢掉还是报错"这个问题在 sing-box 内核层没有答案**（内核不参与）——
   真正的答案是：**一旦映射产物落到 sing-box JSON，无法映射的字段只有一个结局 —— `unknown field` 硬 FATAL**（§5.3）；
   所以**丢弃必须发生在兼容层的 URI 解析阶段**，绝不能把未知参数透传成 JSON 字段。

URI 参数名的规范来源属**客户端约定**（Xray 的官方讨论 https://github.com/v2fly/v2ray-core/issues/774
即 "Generalized V2Ray URI scheme"，会随版本修订）；本文**不声称**这些参数名有内核级保证。

### 5.2 映射损失点表

"是否无损"的判断基准：**该 URI 语义能否在 sing-box JSON 中找到一个语义等价的字段**（`[src]` 字段存在性 + `[test]` 是否被接受）。

| URI 参数（分享链接约定） | sing-box 字段 | 是否无损 | 证据 |
|---|---|---|---|
| `security=tls` | `tls.enabled: true` | ✅ 无损 | `[src]`；`[test]` |
| `security=reality` | `tls.reality.enabled` + **`tls.utls.enabled` 必须同时为 true** | ⚠️ **有隐藏前提**：URI 里 `security=reality` 蕴含 utls，但 sing-box 需要**两个字段**；漏写 ⇒ FATAL | `[test]` `uTLS is required by reality client` |
| `pbk=` | `tls.reality.public_key` | ✅ | `[src]` |
| `sid=` | `tls.reality.short_id`（**string**，非数组） | ✅ | `[src]` |
| `fp=chrome` | `tls.utls.fingerprint` | ✅（值集合不同，见下） | `[src]`；`[test]` |
| `fp=` 旧值（`chrome_psk` 等 5 个） | ⇒ **静默降级为 chrome** | ⚠️ **静默**：不报错但语义变了 | `[src]` fallthrough；`[test]` exit 0 |
| `sni=` | `tls.server_name` | ✅ | `[src]` |
| `allowInsecure=1` / `insecure=1` | `tls.insecure` | ⚠️ 参数名随客户端而异；**名字写错 ⇒ FATAL** | `[test]` `unknown field "allowInsecure"` |
| `alpn=h2,http/1.1` | `tls.alpn` | ✅（sing-box 接受字符串或数组） | `[src]` `Listable[string]` |
| `flow=xtls-rprx-vision` | `flow` | ✅ | `[src]`；`[test]` accepted |
| `flow=` 其它值（`xtls-rprx-direct` …） | — | ❌ **UNSUPPORTED** | `[test]` `unsupported flow` |
| `type=ws` | `transport.type: "ws"` | ✅ | `[src]`；`[test]` |
| `type=grpc` + `serviceName=` | `transport.type:"grpc"` + `transport.service_name` | ⚠️ 字段可映射，**但默认构建是 grpc-lite**，互通性未验证 | `[src]`；`[test]` |
| `type=httpupgrade` | `transport.type: "httpupgrade"` | ✅（**需 ≥1.7.0**） | `[src]`；`[test]` |
| `type=http`/`h2` | `transport.type: "http"` | ✅（注意无 `h2` 别名） | `[src]` |
| `type=quic` | `transport.type: "quic"` | ⚠️ 需 `tls`（否则 `quic: TLS required`） | `[test]` |
| `type=tcp` / `type=raw` | — | ❌ 必须**删除** `transport` 字段；写 `"tcp"` ⇒ FATAL | `[test]`；`[doc]` D1 |
| **`type=xhttp` / `splithttp`** | — | ❌ **UNSUPPORTED（内核无此概念）** | `[src]`；`[test]` |
| `path=` / `host=` (ws/http/httpupgrade) | `transport.path` / `transport.host` | ✅（`host` 在 http 是 `Listable`，在 httpupgrade 是 `string`） | `[src]` `option/v2ray_transport.go` |
| `host=` 在 http transport | `transport.host`（**数组**） | ⚠️ 类型随 transport 变，生成时需按 transport 分支 | `[src]` |
| `mode=` / `headerType=`（mKCP 相关） | — | ❌ UNSUPPORTED（无 mKCP） | `[doc]` D1 |
| `alterId=0` | `alter_id: 0` | ⚠️ 名字不同；**写 `alterId` ⇒ FATAL** | `[test]` `unknown field "alterId"` |
| `encryption=none`（VLESS 固定值） | **无对应字段**（VLESS outbound 无 `encryption`） | ⚠️ 必须**丢弃**；若透传成字段 ⇒ FATAL | `[src]` `option/vless.go` 无该字段 |
| `security=auto`（VMess） | `security:"auto"` ⇒ **有 TLS 时内核自动改成 `zero`** | ⚠️ **运行期静默改写语义**（不是纯透传） | `[src]` `protocol/vmess/outbound.go`：`if security=="auto" && tlsConfig!=nil { security="zero" }` |
| `security=aes-128-ctr`（VMess） | — | ❌ UNSUPPORTED（合法 legacy 值是 `aes-128-cfb`） | `[test]`；`[doc]` D6 与 `[src]`/`[test]` **不一致**（见 §6.4） |
| `packetEncoding=xudp` | `packet_encoding:"xudp"` | ✅（但**不写时 sing-box 默认就是 xudp**） | `[src]` `PacketEncoding == nil ⇒ xudp=true` |
| `obfs=salamander` + `obfs-password=` | `obfs.type` + `obfs.password` | ✅（Hysteria2） | `[src]`；`[test]` |
| `plugin=obfs-local` / `v2ray-plugin` + `plugin-opts` | `plugin` + `plugin_opts` | ✅ 仅这 2 个；其它 ⇒ FATAL | `[test]` `plugin not found` |
| `mport=`/端口跳跃（Hysteria2） | `server_ports` + `hop_interval` | ⚠️ 分享链接里端口范围**通常写在 `mport` 参数**，字段名/表达不同 | `[src]`；`[test]` accepted；URI 侧参数名 **UNKNOWN** |
| `mux=true`（Xray Mux.Cool） | `multiplex.enabled` —— **但协议不同** | ❌ **语义不可无损映射**（Mux.Cool ≠ smux/yamux/h2mux） | `[test]` `unknown protocol: mux.cool` |
| `remark` / `#tag` | `tag` | ✅（仅作标识，无语义） | `[src]` |

### 5.3 落到 JSON 之后的铁律（`[test]` 实测）

sing-box 的解码路径是**严格**的，且严格点在**两层**：

| 输入 | 结果 | 证据 |
|---|---|---|
| 未知**顶层**键 | `FATAL ... bogus_top: json: unknown field "bogus_top"` | `[test]` |
| 未知 **outbound 内**字段 | `FATAL ... outbounds[0].totally_unknown_field: json: unknown field` | `[test]` |
| 未知 **transport 内**字段 | `FATAL ... outbounds[0].transport.bogus: json: unknown field` | `[test]` |
| 未知 **tls 内**字段 | `FATAL ... outbounds[0].tls.bogus: json: unknown field` | `[test]` |
| 未知 **transport type 值** | `FATAL ... transport: unknown transport type: xhttp` | `[test]` |
| 未知 **outbound type 值** | `FATAL ... outbounds[0]: unknown outbound type: unknown_thing` | `[test]` |
| 未知 **inbound type 值** | `FATAL ... inbounds[0]: unknown inbound type: bogus` | `[test]` |

- `[src]` 顶层：`option/options.go` `decoder.DisallowUnknownFields()`。
- `[src]` 嵌套：`option/outbound.go` 走 `badjson.UnmarshallExcludedContext`，实测同样严格（上表）。
- ⇒ **兼容性层的责任划分是清楚的：未知参数必须在 URI 解析阶段被丢弃或显式报错；一旦写进 JSON 就是 FATAL，没有"静默忽略"这个中间态。**
  （⚠️ 例外：少数**仍保留在 struct 里**的弃用字段会通过 decode 然后在运行期报错或**静默容忍**，见 §6.3。）

---

## 6. 弃用与移除

### 6.1 已移除（写进配置 = 必错）

| 项 | 弃用 | 移除 | 证据 / `[test]` 实际报错 |
|---|---|---|---|
| ShadowsocksR（inbound+outbound） | 1.5.0 | **1.6.0** | `[src]` `registerStubForRemovedOutbounds`；`[test]` `ShadowsocksR is deprecated and removed in sing-box 1.6.0` |
| Proxy Protocol | 1.5.0 | **1.6.0** | `[doc]` D11；`[src]` `ListenOptions` 中 `proxy_protocol` 标 `Deprecated: removed` |
| `dns` outbound | 1.11.0 | **1.13.0** | `[src]` `option/outbound.go` 显式 case；`[test]` `dns outbound is deprecated in sing-box 1.11.0 and removed in sing-box 1.13.0, use rule actions instead` |
| `block` outbound | 1.11.0 | **1.13.0**（改为 rule action） | `[doc]` D11（"Legacy special outbounds (block/dns)"） |
| WireGuard **outbound**（改用 endpoint） | 1.11.0 | **1.13.0** | `[src]` stub；`[test]` 裸配置 ⇒ `WireGuard outbound is deprecated in sing-box 1.11.0 and removed in sing-box 1.13.0, use WireGuard endpoint instead`；带 `server` 字段 ⇒ 先撞 `unknown field "server"`（**报错形态取决于写法**，兼容层需注意） |
| legacy inbound 字段（`sniff`/`domain_strategy`/`sniff_override_destination`/`sniff_timeout`/`udp_disable_domain_unmapping`） | 1.11.0 | **1.13.0** | `[test]` `legacy inbound fields are deprecated in sing-box 1.11.0 and removed in sing-box 1.13.0, checkout migration: ...` |
| `direct.override_address` / `override_port` | 1.11.0 | **1.13.0** | `[src]` `option/direct.go`；`[test]` `destination override fields in direct outbound are deprecated ... use route options instead` |
| `ech.pq_signature_schemes_enabled` / `dynamic_record_sizing_disabled` | 1.12.0 | **1.13.0** | `[test]` `legacy ECH options are deprecated in sing-box 1.12.0 and removed in sing-box 1.13.0` |
| GeoIP / Geosite | 1.8.0 | **1.12.0** | `[doc]` D11 —— ⚠️ 但 `[test]` `route.geoip` **仍被接受（exit 0）**，见 §6.3 |
| TUN `inet4_address` / `inet6_address`（合并进 `address`） | 1.10.0 | **1.12.0** | `[doc]` D11；`[src]` `option/tun.go` |
| `rule_set_ipcidr_match_source`（改名 `rule_set_ip_cidr_match_source`） | 1.10.0 | **1.11.0** | `[doc]` D11 |
| TUN GSO | 1.11.0 | **1.13.0** | `[doc]` D11 |
| legacy DNS server 格式 | 1.12.0 | **1.14.0** | `[doc]` D11 |

### 6.2 1.14.2 当下已弃用（仍可用，未来会移除）

`[doc]` D11（tag 版，最高只到 1.14.0 段）：

- `tls.acme` 内联 ACME（→ certificate provider）：**1.16.0 移除**。`[test]` inbound 上 ⇒ `WARN inline ACME options in TLS is deprecated in sing-box 1.14.0 ...`。
- rule-set `download_detour`（→ `http_client`）：**1.16.0 移除**。
- 隐式默认 HTTP client（→ 显式 `http_clients` + `route.default_http_client`）：**1.16.0 移除**。
- DNS 规则动作的 legacy `strategy` 选项、`rule_set_ip_cidr_accept_empty`、`independent_cache`、`store_rdrc`、DNS 规则中不带 `match_response` 的 `ip_cidr`/`ip_is_private`：均 **1.16.0 移除**。
- `domain_strategy`（Dial Fields）：文档称 1.12.0 弃用、**1.14.0 移除**。
- `domain_resolver` 取代了 outbound DNS 规则项：**1.14.0 起**，server 为域名时 `domain_resolver` 或 `route.default_domain_resolver` 成为**必需**（仅配一个 DNS server 时可省）。
- （官网 1.15-dev 另把 TUN `stack` 标为弃用、1.17.0 移除 —— **不适用于 1.14.2**。）

### 6.3 ⚠️ 高风险：**弃用字段"仍然被接受"的静默区**

`[test]` 实测，以下写法在 1.14.2 上**不报错、也不生效**：

| 写法 | 结果 | 风险 |
|---|---|---|
| `route.geoip: {path: "x.db"}` | **exit 0** | 文档说 1.12.0 已移除，实际字段仍在（`schema:"omit"`）被静默吞掉 ⇒ **兼容层若认为"accepted 就是支持"会误判** |
| `route.rules[].outbound`（legacy outbound 规则项） | **exit 0** | 同上 |
| `dial.domain_strategy` | **exit 0** | 文档说 1.14.0 移除，实际仍接受 |
| `tls.insecure` 写在 **inbound** 上 | **exit 0** | 字段在 `InboundTLSOptions` 里存在但服务端无语义 ⇒ 静默无效 |
| `udp_over_tcp.version: 3`（`enum:"1,2"`） | **exit 0** | `enum` 标签只在 schema 层，运行期不校验 |
| `selector.outbounds: ["nope"]`（引用不存在的 tag） | **exit 0** | `check` 不校验引用完整性 ⇒ 运行期才会失败 |

⇒ **对本项目的直接含义：`[test]` 静态层拿到 `accepted` 不等于 `supported`。**
必须区分 `accepted` / `accepted_unverified` / `rejected` 三态（`research/empirical/README.md` 已有此纪律），
且对"文档已移除但字段仍在"的项（geoip/geosite/domain_strategy）**必须标为 deprecated-no-op 而不是 supported**。

### 6.4 文档与实际的正面冲突：VMess `aes-128-ctr`

- `[doc]` D6（tag 1.14.2 版 vmess.md）把 **`aes-128-ctr`** 列为 legacy encryption method。
- `[src]` `option/vmess.go` 的 enum 是 `auto,none,zero,aes-128-cfb,aes-128-gcm,chacha20-poly1305`（**`aes-128-cfb`，不是 `ctr`**）。
- `[src]` 上游库 `sing-vmess v0.2.8` `NewClient` 的 switch 同样接受 `aes-128-cfb`，其余 → `ErrUnsupportedSecurityType`。
- `[test]` 官方 1.14.1 与自建 1.14.2 均：`aes-128-ctr` ⇒ `vmess: unsupported security type: aes-128-ctr`；`aes-128-cfb` ⇒ exit 0。
- ⇒ **文档错了（或少了一个值）。兼容层以源码/实测为准。**

---

## 7. 结构性差异（与 Xray/mihomo 的模型差异）

> 本节是本文对本项目最有价值的部分：以下差异**不是"支持/不支持"**，而是**模型不同构**，
> 会导致"能生成配置、也能校验通过，但语义不等价"。

### 7.1 安全层不是 transport 的一层，而是 outbound 上的平行对象

- Xray：`streamSettings.{network, security, *Settings}` —— **transport 与 security 平级**。
- sing-box：`outbound.{transport, tls}` —— **两个平行字段**，且 Reality/uTLS/ECH 都塞在 `tls` 里。
- 后果：Xray 的 `security=none` 在 sing-box 里是**不写 `tls`**（没有 `security` 字段）；反向映射时**必须删除 `tls`**，否则会带上一个多余的 TLS 层。
- 证据：`[src]` `option/vless.go`（`OutboundTLSOptionsContainer` + `Transport *V2RayTransportOptions` 并列）。

### 7.2 "一个协议 + 一层 transport" vs "很多能力各自是独立 outbound 类型"

sing-box 的哲学（任务描述中已指出，此处给证据）：

| 能力 | Xray/mihomo | sing-box |
|---|---|---|
| ShadowTLS | transport/附加层（或 mihomo 的 `shadow-tls-opts`） | **独立 outbound `type:"shadowtls"`**（`[src]` `option/shadowtls.go`） |
| AnyTLS | 独立协议 | **独立 outbound `type:"anytls"`**（`[src]`；≥1.12.0） |
| Hysteria2 / TUIC | Xray 有 Hysteria **传输**层 | **各自独立 outbound 类型**（`[src]` `include/quic.go`） |
| WireGuard | 独立 outbound | **`endpoints[]` 里的 `wireguard`**，outbound 形式 1.13.0 已移除（`[src]`/`[test]`） |
| 链式代理 | `sockopt.dialerProxy` | **Dial Fields 的 `detour`**（`[src]`） |

⇒ 兼容层的映射**不是 transport 表对 transport 表**，而是需要一张
`(协议, 传输, 安全) → (outbound type, transport 字段, tls 字段, detour 链)` 的多对多映射表；
其中 ShadowTLS/Hysteria2/TUIC 这类"在 Xray 是层、在 sing-box 是类型"的项**天然需要重写节点模型**。

### 7.3 ⚠️ 最高优先级：multiplex 语义不同构（`mux.cool` ≠ `smux/yamux/h2mux`）

- Xray 的 `mux.enabled` 只有一种实现（Mux.Cool）；mihomo 的 `smux` 支持 `protocol: h2mux/smux/yamux`（sing-box 兼容侧）。
- sing-box 只有 `h2mux/smux/yamux`，**`mux.cool` 直接 FATAL**（`[test]`）。
- ⇒ 一个"Xray 节点 + mux 开启"分享链接映射到 sing-box 时：
  - 若映射成 `multiplex.enabled: true`（默认 h2mux）⇒ **配置合法但协议不同**，服务端不认，**静默走向连接失败**；
  - 若映射成 `protocol:"mux.cool"` ⇒ **FATAL**。
  - 两个结局都不可接受 ⇒ 正确做法是**在兼容层判定为 UNSUPPORTED（或要求关闭 mux）并显式告警**。
- ⚠️ 现有 `tools/probe/cases.json` 的 `advanced.mux` 用例把 Xray `mux.enabled` 与 sing-box `multiplex.protocol:"h2mux"`
  并列成同一 feature，静态层两边都会 `accepted` —— **这个用例在当前形态下抓不到上述风险**，建议补一条跨内核 Tier B。

### 7.4 缺省值差异会静默改变行为

| 项 | sing-box 缺省 | 风险 |
|---|---|---|
| VLESS/VMess `packet_encoding` | **`xudp` 开启**（`PacketEncoding == nil`） | 与"不写=关闭"的直觉相反（`[src]`） |
| VMess `security` | `auto`，且**有 TLS 时被内核改写成 `zero`** | 运行期静默改写（`[src]` `protocol/vmess/outbound.go`） |
| gRPC 实现 | grpc-lite（官方构建） | 见 §7.5 |
| Hysteria2 `hop_interval` | 30s | `[doc]` D7 |
| `tls.min_version` | TLS 1.2 | `[doc]` D2 |
| `multiplex.protocol` | `h2mux` | `[doc]` D3 |

### 7.5 ⚠️ 官方构建的 gRPC 不是标准 gRPC（grpc-lite）

- `[src]` 双实现：`transport/v2raygrpc`（`//go:build with_grpc`）与 `transport/v2raygrpclite`（`//go:build !with_grpc`）；
  `transport/v2ray/grpc_lite.go` 在无 tag 时把 `NewGRPCClient` 直接指向 lite。
- `[doc]` D1：*"standard gRPC has good compatibility but poor performance and **is not included by default**"*；D12 表格里 `with_grpc` 的 "Enabled by default" = ❌。
- `[test]` 官方 1.14.1 二进制：tags 列表**无 `with_grpc`**；符号表 `v2raygrpclite` 命中 46 次、`v2raygrpc.NewClient` **0 次**。
- ⇒ **"sing-box 支持 grpc" 这句话在官方发行版上有歧义**：`transport.type:"grpc"` 合法且校验通过，
  但落到的是 lite 实现。**lite 与 Xray 标准 gRPC 服务端能否互通，本文未验证（UNKNOWN）**，需要跨内核 Tier B。
  这是当前静态探针**原理上抓不到**的一类风险。

### 7.6 能力受 build tag 控制 ⇒ "同一个 sing-box 版本"能力可能不同

`[src]` `release/DEFAULT_BUILD_TAGS*` + `[test]` 实测：

| build tag | 官方默认 | 控制的能力 | `[test]` 缺 tag 时的报错 |
|---|---|---|---|
| `with_quic` | ✅ | hysteria / hysteria2 / tuic / v2ray QUIC transport / DNS QUIC+H3 | `QUIC is not included in this build, rebuild with -tags with_quic` |
| `with_utls` | ✅ | uTLS **+ Reality client** | `uTLS is not included in this build, rebuild with -tags with_utls` |
| `with_grpc` | ❌ | 标准 gRPC（否则 lite） | 无报错（静默用 lite）⚠️ |
| `with_wireguard` | ✅ | WireGuard | — |
| `with_gvisor` | ✅ | gVisor（tun stack / wireguard device） | `gVisor is not included in this build, rebuild with -tags with_gvisor` |
| `with_naive_outbound` | ✅（Linux/Darwin/Android 默认集）/ ❌（OTHERS 集） | naive outbound | `naive outbound is not included in this build, rebuild with -tags with_naive_outbound` |
| `with_acme` / `with_clash_api` / `with_tailscale` / `with_cloudflared` / `with_dhcp` / `with_ccm` / `with_ocm` / `with_usbip` / `with_openvpn` / `with_openconnect` / `with_v2ray_api` | 多数 ✅；`with_v2ray_api` ❌ | 对应服务/endpoint | — |
| `with_embedded_tor` | ❌（需 CGO） | 内嵌 Tor | `[test]` plain 构建下 `type:"tor"` **accepted**（tag 只影响内嵌实现） |
| `with_ech` | — | **已废弃**（1.12.0 起 ECH 走 stdlib） | `[src]` `ech_tag_stub.go` |

- `[test]` 官方发行版实际 tags（`sing-box version` 自报）：
  `with_gvisor,with_quic,with_dhcp,with_wireguard,with_utls,with_acme,with_clash_api,with_tailscale,with_ccm,with_ocm,with_cloudflared,with_naive_outbound,with_usbip,with_openvpn,with_openconnect,badlinkname,tfogo_checklinkname0,with_purego`
- ⇒ **能力识别层必须把"构建配置"当成版本之外的第二个维度**：
  `capability = f(version, build tags, platform)`。仅凭 `1.14.2` 不足以判定 Reality 可用。
  好消息：官方二进制会 `sing-box version` 打印 `Tags:`，可直接读取。

### 7.7 sing-box 的"inbound 也是独立类型"，且与 outbound 不对称

- `[doc]` D5 的 inbound 表：`direct, mixed, socks, http, shadowsocks, vmess, trojan, naive, hysteria, shadowtls, tuic, hysteria2, vless, anytls, snell, tun, redirect, tproxy, cloudflared, tailcat`。
- `[src]` `include/registry.go` `InboundRegistry()` 与 outbound 表**不完全对称**（如 `bridge` 只在 outbound；`mixed`/`tun`/`redirect`/`tproxy`/`cloudflared` 只在 inbound）。
- `[test]` inbound 的 `transport.type:"xhttp"` 同样是 FATAL `unknown transport type: xhttp` ⇒ **inbound 侧与 outbound 侧共享同一份 5 值 transport 集合**。

### 7.8 客户端专属 / 服务端专属字段会在"另一侧"变成 unknown field

- `[test]` `tls.utls` 写在 **inbound** 上 ⇒ `inbounds[0].tls.utls: json: unknown field "utls"`（`InboundTLSOptions` 无此字段）。
- 反之 `tls.insecure` 在 inbound 上**存在但静默无效**（§6.3）。
- ⇒ 兼容层必须区分 `Client-only`（`utls/insecure/disable_sni/fragment/record_fragment/spoof/ech.config/reality.public_key`）与
  `Server-only`（`key/reality.private_key/reality.handshake/ech.key/certificate_provider/acme/client_authentication`），
  否则"把服务端节点配置成客户端 outbound"时会直接 FATAL。

### 7.9 与现有 empirical 证据的对齐（三个需要修正的点）

1. **版本口径不一致**：`research/empirical/probe-results.json` 记 `kernels.singbox.version = "sing-box version 1.14.2"`，
   但该路径的二进制自报 **1.14.1**（tags 含 `with_purego`）。建议核对并修正元数据。
2. **`transport.tcp` 的 accepted 易被误读**：`cases.json` 中 sing-box 的 `transport.tcp` 片段是**不写 `transport`**，
   verdict `accepted` 是对的，但把它读成"sing-box 支持 tcp transport"是错的 ——
   `{"type":"tcp"}` 实测 **FATAL**。建议把 case 名区分成 `transport.tcp_implicit_absence` 之类。
3. **`advanced.mux` 的等价假设不成立**（§7.3）：Xray `mux.enabled`（Mux.Cool）与 sing-box `multiplex.protocol:"h2mux"` 并列，
   静态层会双 accepted，但两者**协议不同**。建议对该 case 增加跨内核 Tier B 或直接降级为 UNSUPPORTED。
4. 另外：文中所有 sing-box 侧 `[test]` 结论本文已在 **1.14.1 官方二进制** 与 **1.14.2 自建二进制** 上双重复现，可直接引用。

---

## 8. UNKNOWN 清单

以下为**明确未确认**项。凡标 UNKNOWN 者，本文不作任何"应该是/大概支持"的推断。

| # | UNKNOWN 内容 | 为什么没有结论 | 建议的验证方式 |
|---|---|---|---|
| U1 | **grpc-lite 与 Xray/mihomo 标准 gRPC 是否互通** | 只证明官方构建用 lite，**未做跨内核连通** | 跨内核 Tier B：sing-box(grpc) 客户端 ↔ Xray(grpc) 服务端 |
| U2 | 其余所有"是否真能连上"的跨内核判断（ws/http/httpupgrade/reality/vision/anytls/hysteria2/tuic/ss2022） | 本文全部为静态校验层，无连接测试 | 跨内核 Tier B 矩阵 |
| U3 | `uTLS` / `ECH` 的**精确引入版本** | `option/tls.go` 在 v1.1.0 已有 `utls`/`ech`；v1.0.0 该文件不存在（`option/outbound.go` 中亦无），未定位 v1.0.0 的实际位置 ⇒ 只能说"≥1.1.0 已存在" | 拉 v1.0.0 全树 grep `utls`/`ech` |
| U4 | `snell` outbound 的必填字段与能力边界 | 未展开 `option/snell.go`（1.14.0 新增，属既有协议） | 读 `option/snell.go` + `protocol/snell/*` |
| U5 | `bridge`、`cloudflared`、`openconnect`、`openvpn-client`、`tailscale`、`usbip` 等 1.12–1.14 新增类型的字段与兼容性 | 超出本次 sing-box 代理能力研究范围 | 按需补 |
| U6 | Hysteria2 端口跳跃在**分享链接**里的标准参数名（如 `mport`） | sing-box 不定义 URI；未找到权威 URI 规范 | 查各客户端解析器实现 |
| U7 | 各 URI 参数名（`sni`/`fp`/`pbk`/`sid`/`allowInsecure` …）的**规范性**保障 | 属客户端约定，无内核级契约；Xray discussion #774 仍在修订 | 以目标客户端解析器为准 |
| U8 | `route.geoip` / `route.rules[].outbound` / `domain_strategy` 是"被静默忽略"还是"仍部分生效" | `[test]` 只证明 `check` 通过；**未做运行期行为验证** | Tier B：写入后观察实际路由行为 |
| U9 | `udp_over_tcp.version: 3` 被接受后的实际行为（是否等同默认值） | 同上，仅静态层 | Tier B 或读 `sing/common/uot` 版本选择逻辑 |
| U10 | `selector`/`urltest` 引用不存在 tag 时的运行期行为 | `check` 不校验引用 ⇒ 静态层无结论 | 运行 `sing-box run` 观察启动是否失败 |
| U11 | Xray `Hysteria` 传输 ↔ sing-box `hysteria` outbound 的语义等价性 | 只知两边"都有 hysteria"，未比对参数集 | 读 Xray Hysteria 传输文档 + sing-box `option/hysteria.go` 逐字段比对 |
| U12 | sing-box 1.14.0 是否真的移除了 `domain_strategy`（文档说移除了，实测仍接受） | `[test]` 只见 accepted，未见 WARN/FATAL；是否仍生效未知 | Tier B 或读 dialer 代码是否消费该字段 |
| U13 | `with_purego` 对能力的影响（官方二进制含该 tag） | 未研究 | 读 `docs/installation/build-from-source.md` naive 章节 |

---

## 附 A：本文 `[test]` 复现方法

```bash
# 1) 取源码（与我用的完全一致）
curl -sSL -o sb.tar.gz https://codeload.github.com/SagerNet/sing-box/tar.gz/refs/tags/v1.14.2
tar -xzf sb.tar.gz && cd sing-box-1.14.2

# 2) 两个二进制
go build -o /tmp/sing-box-plain  ./cmd/sing-box                                   # 无 tag
go build -tags with_quic,with_utls,with_wireguard -o /tmp/sing-box-tagged ./cmd/sing-box

# 3) 逐条用例
/tmp/sing-box-tagged check -c case.json ; echo "exit=$?"
# 或直接交叉复核官方发行版：
/root/catmi/sing-box/sing-box check -c case.json ; echo "exit=$?"
```

关键用例（最小可复现）：

| 用例 | 配置要点 | 期望 |
|---|---|---|
| xhttp 不存在 | vless + `"transport":{"type":"xhttp"}` | FATAL `unknown transport type: xhttp` |
| tcp transport 不存在 | `"transport":{"type":"tcp"}` | FATAL `unknown transport type: tcp` |
| 无 Mux.Cool | `"multiplex":{"enabled":true,"protocol":"mux.cool"}` | FATAL `unknown protocol: mux.cool` |
| vmess ctr 不支持 | `"security":"aes-128-ctr"` | FATAL `unsupported security type: aes-128-ctr` |
| reality 需 utls | `tls.reality.enabled` 且 `tls.utls` 缺失 | FATAL `uTLS is required by reality client` |
| 未知字段硬错 | vless + `"totally_unknown_field":1` | FATAL `json: unknown field` |
| geoip 静默 | `route.geoip.path` | **exit 0**（静默） |
| 空 transport 特例 | `"transport":{}` vs `"transport":{"type":""}` | 0 vs FATAL |

## 附 B：版本门槛速查（全部 `[src]` 逐 tag 比对 + `[doc]` 注解）

| 能力 | 门槛 |
|---|---|
| transport `httpupgrade` | **1.7.0** |
| outbound `tuic` | **1.4.0** |
| outbound `hysteria2` | **1.5.0** |
| outbound `anytls` | **1.12.0** |
| outbound `snell` | **1.14.0** |
| Reality（`tls.reality`） | **1.2.0**（uTLS/ECH 早于此，≥1.1.0，精确值 UNKNOWN） |
| `tls.fragment` / `record_fragment` / `fragment_fallback_delay` | **1.12.0** |
| `tls.curve_preferences` / `kernel_tx` / `kernel_rx` / `certificate_public_key_sha256` / `client_certificate(_path)` / `client_key(_path)` / `client_authentication` / `ech.query_server_name` | **1.13.0** |
| `tls.engine` / `handshake_timeout` / `certificate_provider` / `spoof` / `spoof_method` | **1.14.0** |
| `tls.certificate_sha256` / `client_certificate_sha256` | **1.15.0**（1.14.2 **无**） |
| uTLS 旧指纹 `chrome_psk*`/`chrome_pq*` 移除（降级为 chrome） | **1.10.0** |
| `multiplex` `network_strategy` 等 dial 字段 | **1.11.0** |
| `netns` / `domain_resolver` | **1.12.0** |
| `bind_address_no_port` / TCP keep-alive 三件套 | **1.13.0** |
| Hysteria2 `server_ports` / `hop_interval` | **1.11.0** |
| Hysteria2 `hop_interval_max` / `bbr_profile` / `disable_chrome_parrot` / `realm` / obfs `gecko` | **1.14.0** |
| AnyTLS `client_metadata` | **1.13.16** |
| 移除：ShadowsocksR / Proxy Protocol | **1.6.0** |
| 移除：`dns`/`block` outbound、WireGuard outbound、legacy inbound 字段、`direct.override_*`、legacy ECH 字段、TUN GSO | **1.13.0** |
| 移除：GeoIP / Geosite（文档口径） | **1.12.0**（实测仍 accepted，见 §6.3） |
| 移除：legacy DNS server 格式 | **1.14.0** |
