# Fanju6/Proxylink — 源码级调研

- 项目：<https://github.com/Fanju6/Proxylink>
- 调研对象：`main` 分支，commit `44929c0984944870297c260dc43a4aa9262f9e1c`（经 GitHub Trees API 取得文件树）
- 方法：先拉文件树，再逐个读 `raw.githubusercontent.com` 源码。**全部结论来自源码，非 README。**
- 环境限制：本机无 Go 工具链（`which go` → 无），因此**没有编译/运行验证**，所有"某字段被丢弃"的判断都是**静态阅读代码路径**的结论（见 §9）。
- 规模：30 个文件（约 160KB 源码）全部读过；跳过 `.github/*`、`.gitignore`、`LICENSE`、`go.sum`。

---

## 0. 我实际读了哪些文件

全部通过 `https://raw.githubusercontent.com/Fanju6/Proxylink/main/<path>` 读取：

| 类别 | raw 路径 |
| --- | --- |
| 入口 | `Proxylink/main.go` |
| 依赖 | `Proxylink/go.mod` |
| 模型 | `Proxylink/pkg/model/profile.go` |
| 模型 | `Proxylink/pkg/model/config_type.go` |
| 模型 | `Proxylink/pkg/model/network_type.go` |
| 解析入口 | `Proxylink/pkg/parser/parser.go` |
| 解析公共层 | `Proxylink/pkg/parser/base.go` |
| URI 解析 | `Proxylink/pkg/parser/vless.go` |
| URI 解析 | `Proxylink/pkg/parser/shadowsocks.go` |
| URI 解析 | `Proxylink/pkg/parser/trojan.go` |
| URI 解析 | `Proxylink/pkg/parser/anytls.go` |
| URI 解析 | `Proxylink/pkg/parser/hysteria2.go` |
| URI 解析 | `Proxylink/pkg/parser/tuic.go` |
| URI 解析 | `Proxylink/pkg/parser/socks.go` |
| URI 解析 | `Proxylink/pkg/parser/http.go` |
| URI 解析 | `Proxylink/pkg/parser/wireguard.go` |
| 反解：Clash | `Proxylink/pkg/parser/clash.go` |
| 反解：Xray | `Proxylink/pkg/parser/xray.go` |
| 反解：sing-box | `Proxylink/pkg/parser/singbox.go` |
| 生成：Xray | `Proxylink/pkg/generator/xray.go` |
| 生成：sing-box | `Proxylink/pkg/generator/singbox.go` |
| 回写 URI | `Proxylink/pkg/encoder/encoder.go` |
| 订阅 | `Proxylink/pkg/subscription/converter.go` |
| 订阅 | `Proxylink/pkg/subscription/decoder.go` |
| 订阅 | `Proxylink/pkg/subscription/fetcher.go` |
| 订阅 | `Proxylink/pkg/subscription/singbox_provider.go` |
| 工具 | `Proxylink/pkg/util/base64.go` |
| 工具 | `Proxylink/pkg/util/url.go` |
| 文档 | `README.md` |
| 文档 | `DEVELOPMENT.md` |

补充证据（非 raw 源码，仅用于确认某一处 API 归属）：Xray-core 的 `finalmask` / `quicParams` 是上游特性，见 <https://core-tutorial.argsment.com/xray/hysteria2> 与 <https://xtls.github.io/en/config/transports/hysteria.html>。

---

## 1. 数据模型

### 1.1 结论：**完全扁平，59 个标量字段，零嵌套、零 map、零 slice、零扩展槽**

`ProfileItem` 定义在 `Proxylink/pkg/model/profile.go:6-82`，共 **59 个字段**，全部是 `string` / `bool` / `int`。没有任何 `struct` 字段、没有 `map`、没有 `[]string`、没有 `interface{}`、没有 `Extra`/`Raw`/`Unknown`/`Metadata`。

按源码注释分组（行号 → 字段）：

**基座（5）** `profile.go:7-11`
`ConfigType ConfigType` | `SubscriptionID string` | `Remarks string` | `Server string` | `ServerPort string`（注意端口是 **string**，不是 int）

**认证（8）** `profile.go:14-21`
`Password`（多义：VLESS/VMess 的 UUID、SS/Trojan/Hy2/AnyTLS/TUIC 的密码）| `Method`（多义：SS 加密方法 / VLESS encryption / VMess scy）| `Plugin` | `PluginOpts` | `Flow` | `Username` | `UUID`（仅 TUIC）| `AlterId int`

**传输层（16）** `profile.go:24-39`
`UDP bool` | `Network string` | `HeaderType` | `Host` | `Path` | `Seed` | `QuicSecurity` | `QuicKey` | `Mode` | `ServiceName` | `Authority` | `XhttpMode` | `XhttpExtra` | `FinalMask` | `MaxEarlyData int` | `EarlyDataHeaderName`

**TLS（7）** `profile.go:42-48`
`Security`（tls/reality/"")| `SNI` | `ALPN`（**逗号分隔的单个 string**）| `Fingerprint` | `Insecure bool` | `Mldsa65Verify` | `DisableSNI bool`

**Reality（3，与 TLS 平级并列）** `profile.go:51-53`
`PublicKey` | `ShortID` | `SpiderX`

**ECH / 钉扎（4）** `profile.go:56-59`
`EchConfigList` | `EchQueryServerName` | `EchForceQuery`（注意类型是 **string 不是 bool**）| `PinnedCA256`

**WireGuard（5）** `profile.go:62-66`
`SecretKey` | `PreSharedKey` | `LocalAddress` | `Reserved` | `MTU int`

**Hysteria2（6）** `profile.go:69-74`
`ObfsPassword` | `PortHopping` | `PortHoppingInterval` | `PinSHA256` | `BandwidthDown` | `BandwidthUp`

**TUIC（5）** `profile.go:77-81`
`CongestionControl` | `UDPRelayMode` | `UDPOverStream bool` | `ZeroRTTHandshake bool` | `Heartbeat`

### 1.2 高级参数如何表达 —— 逐项回答

| 能力 | 在 ProfileItem 里的表达 | 评价 |
| --- | --- | --- |
| transport | 扁平二元组：`Network string` + 各传输专用扁平字段（`Host`/`Path`/`Seed`/`Mode`/`ServiceName`/`Authority`/`HeaderType`/`QuicSecurity`/`QuicKey`/`XhttpMode`/`XhttpExtra`） | **无 per-transport 子结构**。字段被所有 transport 共享复用，语义随 `Network` 变化（如 `Mode` 对 grpc 是 multiMode，对 xhttp 是 xhttp mode，而解析时二者同时被写入，见 §4.4） |
| TLS | `Security string` + `SNI`/`ALPN`/`Fingerprint`/`Insecure`/`DisableSNI` 扁平放同一层 | `Security` 只有 `tls`/`reality`/`""` 三态（`base.go:36-38` 强制归一） |
| Reality | `PublicKey`/`ShortID`/`SpiderX` 与 TLS 字段平级，靠 `Security=="reality"` 区分 | 无 `Reality` 嵌套；`SpiderX` 是 Xray 专有概念，却放在通用模型里 |
| ECH | `EchConfigList` / `EchQueryServerName` / `EchForceQuery` 三个扁平 string | `EchForceQuery` 用 string 存 bool 语义 |
| flow | `Flow string` | 平级 |
| fingerprint | `Fingerprint string` | 一个字段同时承载 uTLS 指纹（sing-box `utls.fingerprint`）和 Xray `tls.fingerprint`，**未区分语义** |
| headers | **只有 `Host` 一个 string**（`profile.go:27`） | 无 headers map。ws 的 `Headers`、http 的 `Host[]`、`Host` 与 `host` 大小写差异，全部被压成单个逗号分隔字符串 |
| obfs | **只有 SS 的 `Plugin`/`PluginOpts`（string）** + Hysteria2 的 `ObfsPassword` | 无通用 obfs 概念；SS 插件名与参数被拼成分号字符串 |
| multiplex | **完全没有** | 全仓库 grep `mux\|multiplex` 只命中 `generator/xray.go` 的 `MuxBean`，且**恒为 `Enabled:false`**（`xray.go:259,287,310,335,369,396`）。数据模型里没有 mux 字段，也没有从 URI 读取 `mux`/`multiplex` 参数 |
| 内核版本 | **完全没有** | 全仓库无 core-version 概念 |
| 未知/扩展参数 | **完全没有** | 见 §6 |

### 1.3 枚举

- `ConfigType`（`config_type.go:6-18`）：`VMESS, VLESS, SHADOWSOCKS, SOCKS, HTTP, TROJAN, WIREGUARD, HYSTERIA2, ANYTLS, TUIC, CUSTOM` — 11 个值。
  `CUSTOM` 是唯一的"逃生舱"枚举，但**无 scheme**（`ProtocolScheme()` 的 switch 里没有 CUSTOM 分支，落到 `default: return ""`）、**无解析器**、**两个 generator 都不处理**（都返回 nil）。属于**声明了但未实现的死枚举**。
- `NetworkType`（`network_type.go:6-16`）：`tcp, kcp, ws, http, h2, grpc, quic, httpupgrade, xhttp` — 这是**Xray 的词汇表**（`h2`、`xhttp` 是 Xray 叫法；sing-box 叫 `http`）。
  `ParseNetworkType`（`network_type.go:24-47`）做别名归一：`websocket→ws`、`http2→h2`、`gun→grpc`、`splithttp→xhttp`，**`default: return NetworkTCP`** —— 未知 transport **静默变成 tcp**，这是模型层的第一次静默降级。
- `SubscriptionID`（`profile.go:8`）：**全仓库从未被赋值**（grep 只命中定义处）。死字段，暗示多订阅来源本是设计意图，但未落地。

---

## 2. URI 解析

### 2.1 各协议入口（`pkg/parser/parser.go:11-41` 集中分发）

`Parse(uri string) (*model.ProfileItem, error)` 用 `strings.HasPrefix` 串行判断：

| 协议 | scheme（含别名） | 入口函数 | 文件:行 |
| --- | --- | --- | --- |
| VMess | `vmess://` | `ParseVMess` → `parseVMessJSON` / `parseVMessJSONManual` / `parseVMessStd` | `vless.go:80 / 95 / 105 / 194` |
| VLESS | `vless://` | `ParseVLess` | `vless.go:15` |
| Shadowsocks | `ss://` | `ParseShadowsocks` → `parseShadowsocksSIP002` / `parseShadowsocksLegacy` | `shadowsocks.go:15 / 28 / 123` |
| Trojan | `trojan://` | `ParseTrojan` | `trojan.go:12` |
| SOCKS | `socks://`, `socks5://` | `ParseSocks`（自写 body 解析，含 legacy base64） | `socks.go:15` |
| HTTP | `http://` | `ParseHTTP` | `http.go:12` |
| WireGuard | `wireguard://`, `wg://` | `ParseWireGuard`；另 `ParseWireGuardConf`（.conf） | `wireguard.go:15 / 64` |
| Hysteria2 | `hysteria2://`, `hy2://` | `ParseHysteria2` | `hysteria2.go:14` |
| AnyTLS | `anytls://` | `ParseAnyTLS` | `anytls.go:12` |
| TUIC | `tuic://` | `ParseTUIC` | `tuic.go:13` |
| **不认识的 scheme** | — | `errors.New("unsupported protocol: ...")` | `parser.go:38-40` |

非 URI 的输入源另有入口：`ParseClashConfig`（`clash.go:113`）、`ParseXrayConfig`（`xray.go:12`）、`ParseSingboxConfig`（`singbox.go:14`）、`ParseBatch`（`parser.go:44`，逐行、错误累积到 `[]error`）。

**共性实现**：VLESS/VMess-std/SS-SIP002/Trojan/AnyTLS/TUIC/WireGuard/Hysteria2 都走 `url.Parse(util.FixIllegalURL(uri))` + `u.Query()`；`FixIllegalURL`（`util/url.go:56-59`）只做一件事：把空格换成 `%20`。

### 2.2 未知 query 参数怎么处理 —— **静默忽略，无任何记录**

这是最关键的结论，有三条独立证据：

1. **`parseQueryParams` 是一个硬编码白名单**（`base.go:13-59`）。它只对 21 个固定 key 名（外加 `insecure` 的 4 个别名，共 25 个字符串）调用 `query.Get(...)`：`type, headerType, host, path, seed, quicSecurity, key, mode, serviceName, authority, extra, fm, security, sni, peer, alpn, fp, flow, pqv, ech, pcs, insecure/allowInsecure/allow_insecure/skip-cert-verify, pbk, sid, spx`。**从不遍历 `url.Values`**，因此不在表里的 key 连"被看到"的机会都没有。
2. **`profile.go` 没有任何 `Extra`/`Raw*`/`Unknown`/`Metadata` 字段**（§1.1，59 个字段已穷举）。未知参数无处可存。
3. **没有保留原始 URI / 原始 RawQuery**。grep `rawuri|rawquery|rawparams|originaluri` 全仓库零命中。`ProfileItem` 里唯一"近似原文"的字段是 `XhttpExtra`（已知 key `extra` 的 **opaque value**）和 `FinalMask`（已知 key `fm` 的 opaque JSON value）——这是"已知参数、不透明取值"，**不是**未知字段保留机制。

各协议的具体白名单差异（说明未知参数处理在不同协议间还不一致）：

| 解析器 | 读到哪些参数 | 备注 |
| --- | --- | --- |
| `parseQueryParams`（VLESS/VMess/Trojan/AnyTLS/TUIC 共用） | 见上：21 个 key 名 + `insecure` 的 4 个别名 | `sni` 缺失时回退 `peer`（`base.go:41-44`）；`insecure` 别名见 `base.go:53` |
| `ParseHysteria2`（`hysteria2.go:35-53`） | **不调用 `parseQueryParams`**，只读 `sni, alpn, fp, insecure, allowInsecure, obfs-password, mport, mportHopInt, pinSHA256` | 所以 hy2 链接里的 `type/path/host/security/...` 全部被忽略；`up`/`down`（带宽）**根本没读**，`BandwidthUp/Down` 只能由 Clash/sing-box 反解填充 |
| `ParseTUIC`（`tuic.go:32-41,75-82`） | 先 `parseQueryParams`，再 `parseTUICQueryParams`；后者用 `firstQueryValue` 支持别名（`congestion_control|congestion-controller` 等） | `network` 与 `type` 二选一（`tuic.go:84`） |
| `ParseSocks`（`socks.go:15-49`） | **完全不读 query** | userinfo 支持明文/base64/整体 legacy base64 三种 |
| `ParseHTTP`（`http.go:12-37`） | **完全不读 query** | 只取 user:pass@host:port#remarks |
| `ParseShadowsocks`（`shadowsocks.go:63-70`） | 只读 `plugin` | 其它 SIP002 参数（如 `udp`）忽略 |
| `ParseWireGuard`（`wireguard.go:36-58`） | `publickey, peer, address, reserved, presharedkey, mtu` | 缺失时**注入默认值**：`address=10.0.0.2/32`、`reserved=0,0,0`、`mtu=1420`（`wireguard.go:43,47,57`）—— 这是"凭空造值"，round-trip 时会污染原始信息 |
| `ParseVMess` JSON（`vless.go:160-191`） | 由 `vmessJSONToQuery` 把 15 个 `VmessQRCode` 字段映射回 query 再复用 `parseQueryParams` | **只有 15 个字段**（`vless.go:57-74`），vmess JSON 里其它键（如 `spx/pbk/sid/ech`）即使出现在 vmess 链接里也不会进入 `qr`（但会经 `u.Query()` 路径进入？不会——JSON 格式没有 query） |

### 2.3 非 URI 输入源的未知字段处理

- **Xray JSON**（`xray.go:12-37`）：`json.Unmarshal` 进 `generator.XrayConfig` / `XrayOutbound`，Go 默认**忽略未知 JSON key**，无记录。`XrayConfig` 只有 `Outbounds` 一个字段（`xray.go:14-16`），配置里的 `inbounds`/`routing`/`dns`/`log` 等**整块静默丢弃**，且没有任何 "ignored" 提示（对比 sing-box 路径有 `isIgnoredSingboxOutboundType`，见 §5.3）。
- **sing-box JSON**（`singbox_provider.go:102-165`）：先解析为 `[]json.RawMessage`，再按 `type` 分派；未知 key 是否报错取决于 `singjson.UnmarshalContext` 的宽松策略，**我未验证**（见 §9）。
- **Clash YAML**（`clash.go:113-132`）：`yaml.Unmarshal` 进 `ClashProxy`，yaml.v3 默认忽略未知字段，无记录。

---

## 3. 内核/目标格式表示

### 3.1 Xray（`pkg/generator/xray.go`，776 行）

整体是 **v2rayNG/Xray JSON schema 的 Go 镜像**：`XrayConfig`(14) → `XrayOutbound`(19) → `OutSettings`(28) / `StreamSettings`(80)，下游 `TcpSettingsBean`/`KcpSettingsBean`/`WsSettingsBean`/`HttpupgradeSettingsBean`/`XhttpSettingsBean`/`HttpSettingsBean`/`TlsSettingsBean`/`GrpcSettingsBean`/`FinalMaskBean`/`QuicParamsBean`/`UdpHopBean`/`MaskBean`/`MuxBean`。

入口 `GenerateXrayOutbound`（`xray.go:221-242`）：

```go
switch profile.ConfigType {
case model.VLESS: ... case model.HYSTERIA2: return generateHysteria2Outbound(profile)
default: return nil      // ← xray.go:239-240
}
```

**没有 `ANYTLS`、`TUIC`、`CUSTOM` 分支 → 返回 `nil`，不返回 error。** 上游 `GenerateXrayConfig`（`xray.go:245-253`）在 outbound 为 nil 时也返回 nil；`main.go:361-362` 直接 `toJSON(nil)` → **单节点模式打印 `null`**；`main.go:376-378` 批量模式把 nil 直接 append 进 `outbounds` → **产出 `"outbounds": [null]`**。这是全项目最典型的"静默丢失"，见 §5.4 清单。

转换时的字段去向（`buildStreamSettings` 534 → `populateTransportSettings` 554 → `populateTlsSettings` 709）：

| 能力 | Xray 输出 | 是否丢弃 |
| --- | --- | --- |
| tcp/http header | `tcpSettings.header` + `request.headers.Host[]`/`path[]`（`xray.go:558-584`） | 保留（`Host`/`Path` 按逗号拆成数组） |
| kcp | `finalmask.udp` 里的 `header-*` / `mkcp-original` / `mkcp-aes128gcm` mask；`Seed`→mask password（`xray.go:586-610`） | 保留（**Xray 新版 finalmask 表达**，非旧 `kcpSettings`；`kcpSettings`/`seed` 字段仍在结构体里但基本不用） |
| ws + 0-RTT | `path` 拼 `?ed=N`（`xray.go:612-630`） | 保留 |
| httpupgrade / h2 / grpc | `httpupgradeSettings` / `httpSettings` / `grpcSettings`（`grpc` 的 `Mode=="multi"`→`multiMode`，`IdleTimeout:60`、`HealthCheckTimeout:20` **硬编码**） | 保留，但 grpc 超时是编造的常量 |
| xhttp | `xhttpSettings{host,path,mode,extra}`，`mode` 默认 `auto`、`path` 默认 `/`（`xray.go:643-663`） | 保留 |
| **quic** | **`populateTransportSettings` 没有 `case "quic"`** → `ss.Network="quic"` 但无任何 settings | **静默丢弃** `QuicSecurity`/`QuicKey`/`Seed` |
| tls | `tlsSettings`（`xray.go:751-754`） | 保留 |
| reality | `realitySettings`（`xray.go:741-750`），`show:false` 硬编码 | 保留 |
| `Insecure`/`SNI`/`ALPN`/`Fingerprint`/`EchConfigList`/`EchForceQuery`/`PinnedCA256` | `tlsSettings`（`xray.go:727-738`） | 保留 |
| `Mldsa65Verify` | **只在 reality 分支写**（`xray.go:746-748`），放 `realitySettings.mldsa65Verify`（`xray.go:166`） | tls 场景下静默丢弃 |
| `DisableSNI` | `TlsSettingsBean` **没有这个字段**（`xray.go:157-170`） | **静默丢弃**（TUIC 的 `disable-sni` 转 Xray 时消失） |
| `PinSHA256` | `generateHysteria2Outbound` 构造 `TlsSettingsBean`（`xray.go:510-520`）时**没有赋值 `PinnedPeerCertSha256`**，尽管该字段存在（`xray.go:169`） | **静默丢弃** |
| SS `Plugin`/`PluginOpts` | `generateShadowsocksOutbound`（`xray.go:306-329`）**完全不引用** | **静默丢弃**（Xray 无 SIP003 插件，属客观不能，但无提示） |
| SOCKS/HTTP 的 TLS+transport | `generateSocksOutbound`(351) / `generateHTTPOutbound`(379) **不调用 `buildStreamSettings`** | **静默丢弃**（Clash 里带 `tls: true` 的 socks5/http 节点，转 Xray 后 TLS 消失） |
| WireGuard | `generateWireGuardOutbound`(405-444)：`secretKey/address/peers/reserved/mtu` | 保留；`Reserved` 字符串按逗号拆 int |
| Hysteria2 | 自造 `protocol:"hysteria"` + `settings.version:2` + `streamSettings.network:"hysteria"` + `hysteriaSettings{version:2,auth}` + `finalmask.quicParams`（`BrutalUp/Down`，`congestion:"brutal"`）+ `finalmask.udp[salamander]`（`xray.go:446-532`） | 保留（**上游 Xray-core 特性**，见 §0 链接）；`ALPN` 默认 `["h3"]`，端口跳跃 `udpHop{ports,interval}`，interval < 5 时回退 `"30"`（`xray.go:479-482` 静默替换） |
| mux | 恒 `{enabled:false, concurrency:-1}`（6 处硬编码） | 模型无此概念 |
| `snapshot.Rule` 等其它 | 不在模型 | — |

另有隐式覆盖逻辑：`fm` 参数存在时，`populateTransportSettings` 末尾用**原始 JSON 反序列化出的 `FinalMaskBean` 整个覆盖**自动生成的 finalmask（`xray.go:693-703`）。这是全项目唯一的"用户显式意图优先于自动推断"机制。

### 3.2 sing-box（`pkg/generator/singbox.go`，426 行）

结构体：`SingboxConfig`(14) → `SingboxOutbound`(18) → `SingboxTLS`(60) / `SingboxUTLS`(71) / `SingboxReality`(76) / `SingboxECH`(82) / `SingboxTransport`(88) / `SingboxHy2Obfs`(98)。**注意 `SingboxTransport` 里没有 `Host` 之外的 header 表达，且 `Host any` 用 `any` 兼容 string/[]string（`singbox.go:92`）——用类型擦除掩盖 schema 差异。**

入口 `GenerateSingboxOutbound`（`singbox.go:104-112`）：

```go
ob := buildSingboxOutbound(p)
if ob == nil { return "", nil }   // ← 返回空串 + nil error
```

`buildSingboxOutbound`（`singbox.go:154-223`）的 switch 覆盖 `VLESS, VMESS, SHADOWSOCKS, SOCKS, TROJAN, HYSTERIA2, ANYTLS, TUIC`，**`default: return nil`（`singbox.go:208-209`）**。因此：

- **`WIREGUARD` 和 `HTTP` 没有分支** → sing-box 输出为**空字符串且 `err == nil`**。调用方 `main.go:364` 只透传，只看 error 的调用者会拿到空文件。（README §"sing-box 输出说明" 的协议清单确实没列 HTTP/WireGuard，但**运行时没有任何信号**。）
- `ConfigType == CUSTOM` 同理。

传输层 `buildSingboxTransport`（`singbox.go:244-286`）只处理 `ws / grpc / h2|http / httpupgrade`，**`default: return nil`（`singbox.go:281-282`）** → **`kcp`、`quic`、`xhttp` 的 transport 被静默丢弃**（`ob.Transport = nil`）。其中 xhttp 是 Xray 侧完整支持的能力，跨内核就无声消失。

TLS 层 `buildSingboxTLS`（`singbox.go:288-346`）—— **本项目最重要的一段"有意静默降级"**，源码注释写得很清楚（`singbox.go:304-310`）：

```go
// pinSHA256 (Hysteria2/Xray) 钉扎的是【整个证书】的 SHA256 指纹,
// 而 sing-box 只有 certificate_public_key_sha256 (钉扎【公钥】SPKI 哈希),
// 两者哈希对象不同无法换算, sing-box 也没有整证书指纹钉扎选项。
// 故降级为跳过证书验证 (等价于 Clash 订阅的 skip-cert-verify)。
if p.PinSHA256 != "" {
    tls.Insecure = true
}
```

**这是一个把"证书钉扎"降级成"完全不校验证书"的安全语义弱化**，除了注释之外**没有任何结构化输出**（不返回 error、不写 warning、不置 flag）。正是我们项目要检测的那类降级。

sing-box 侧其它字段去向：

| 能力 | sing-box 输出 | 是否丢弃 |
| --- | --- | --- |
| Reality | `tls.reality{enabled,public_key,short_id}`（`singbox.go:326-332`） | 保留；**`SpiderX` 丢弃**（sing-box reality 无此概念） |
| uTLS `Fingerprint` | `tls.utls{enabled,fingerprint}`（`singbox.go:318-323`） | 保留 |
| ECH | `tls.ech{enabled, config:[...], query_server_name}`（`singbox.go:335-343`） | 保留，但 **`EchForceQuery` 丢弃**（`SingboxECH` 无该字段，`singbox.go:82-86`） |
| `Mldsa65Verify` | `SingboxTLS` 无该字段 | **静默丢弃** |
| `PinnedCA256` | `SingboxTLS` 无该字段 | **静默丢弃** |
| `DisableSNI` | `tls.disable_sni`（`singbox.go:302`） | 保留（**Xray 侧反而丢**，方向相反） |
| Hysteria2 带宽 | `up_mbps`/`down_mbps`，`parseMbps` 解析 "100 Mbps"（`singbox.go:348-355,417-425`） | 保留 |
| Hysteria2 端口跳跃 | `server_ports` + `hop_interval`（补 `"s"`，`singbox.go:366-374`），端口区间 `-`→`:` 且校验 1..65535、`start<end`（`singbox.go:377-413`，非法区间**静默 `ok=false` 丢弃**） | 保留/校验 |
| obfs | `obfs{type:salamander,password}` | 保留 |
| SS Plugin | `plugin`/`plugin_opts` | 保留（**Xray 侧丢**） |
| `UDP` | 仅 SOCKS/TUIC 的 `network`（`singbox.go:225-242`） | 部分 |
| TUIC 全套 | `congestion_control/udp_relay_mode/udp_over_stream/zero_rtt_handshake/heartbeat` | 保留 |
| mux | `SingboxOutbound` 无 mux 字段 | 模型无此概念 |
| tag | `p.Remarks`，批量时 `nextSingboxTag` 去重加 `_2`（`singbox.go:142-152`） | — |

### 3.3 sing-box 反解（`pkg/parser/singbox.go` 与 `pkg/subscription/singbox_provider.go`）—— 两套并存且能力不同

存在**两个** sing-box 反解实现，行为不一致，这本身是个信号：

1. `parser.ParseSingboxConfig`（`singbox.go:14-39`）用**自定义的 `generator.SingboxOutbound`**（自家 schema）反序列化，能识别 `vless/vmess/shadowsocks/socks/trojan/hysteria2/anytls/tuic`，未知 type `return nil`（`singbox.go:81-82`）**静默跳过整个节点**（`parseOutbounds` 里 `if p := ...; p != nil`，无法区分"不支持"与"解析失败"）。
2. `subscription.convertContentWithSingboxProvider` → `parseSingboxDocumentContent`（`singbox_provider.go:102-165`）用 **sing-box 官方库 `github.com/sagernet/sing-box/option`** 反序列化（`go.mod:7` 固定 `sing-box v1.13.14`），并区分了"故意忽略"与"不支持"（§5.3）。

第 2 条是**结构性耦合**：`singboxOutboundOptionsRegistry.CreateOptions`（`singbox_provider.go:52-75`）把 `C.Type*` 映射到 `sboption.VLESSOutboundOptions` 等，再 `profileFromSingboxOutbound`（245-342）逐字段搬进 ProfileItem。**ProfileItem 的表达能力上限 = sing-box option 结构体的交集**；sing-box 有而 ProfileItem 没有的字段（`packet_encoding`、`tls.fragment`、`tls.certificate`、`tls.pinned_peer_certificate_chain_sha256`、`tls.curve_preferences` 等）在 `sboption.*` 里存在，但**没有对应的赋值语句**，于是被静默丢弃。

同文件里 `applySingboxTLS`（474-499）**只读** `ServerName/Insecure/DisableSNI/ALPN/UTLS.Fingerprint/ECH` 与 `Reality.PublicKey/ShortID`；`applySingboxTransport`（501-527）只处理 `websocket/http/grpc/httpupgrade`（**kcp/quic 无 case**，但 `p.Network = transport.Type` 已写入，于是留下"Network=kcp 但所有 kcp 参数丢失"的半残状态）。

### 3.4 Clash（`pkg/parser/clash.go`）

`ClashProxy`（`clash.go:19-78`）是 Clash/mihomo 字段的镜像，含 `RealityOpts`(80)/`WsOpts`(85)/`GrpcOpts`(91)/`H2Opts`(95)/`HttpOpts`(100)/`XhttpOpts`(106)。`fromClashProxy`（141-265）做**语义翻译**，其中有几处硬编码判断值得注意：

- Clash `network: http` 被改写成 `h2`，注释「Clash 的 "http" 即 HTTP/2」（`clash.go:295`）——**跨内核语义映射直接写死在解析器里**。
- ws 的 `v2ray-http-upgrade: true` 被改写成 `httpupgrade`（`clash.go:272-274`）。
- SS 插件名翻译：`obfs/simple-obfs → obfs-local`（`clash.go:320-327`）；未知插件"原样拼接"（`clash.go:349-354`）——**这是全项目唯一对未知插件参数的兜底**，但仍不保留原始 map。
- `ClashHttpOpts.Method`（`clash.go:101`）被解析进结构体但**从未使用**；`ClientFingerprint` 与 `Fingerprint` 二选一（`clash.go:255-258`）。
- 不支持的 Clash type → `return nil`（`clash.go:160-161`）**静默丢弃该节点**。

---

## 4. 无损性与 round-trip

### 4.1 结论：**有 round-trip 能力，但没有无损性保证，且没有任何验证机制**

能生成回 URI：`encoder.ToURI`（`encoder/encoder.go:9-34`）按 `ConfigType` 分派到 10 个 `To*URI`，**`CUSTOM` 落 `default: return ""`**（`encoder.go:31-33`），`ToURIBatch` 会**静默跳过**空串结果（`encoder.go:39-43`）。

写回侧的公共实现 `buildQueryParams`（`base.go:62-183`）同样是**硬编码白名单 + 按 `Network` 分支**：

```go
switch network {
case "tcp": ... case "kcp": ... case "ws", "httpupgrade": ...
case "http", "h2": ... case "grpc": ... case "xhttp": ...
}   // ← 没有 "quic" 分支（base.go:127-180）
```

**没有 `quic` 分支**，所以 `QuicSecurity`/`QuicKey`（以及 quic 场景下的 `Seed`）解析进来后**永远写不回去**。

### 4.2 会丢的字段（URI → ProfileItem → URI）

| 字段 | 丢失原因（源码位置） |
| --- | --- |
| `QuicSecurity`, `QuicKey` | `buildQueryParams` 无 `quic` 分支（`base.go:127-180`） |
| `Seed`（非 kcp 网络时） | 只在 `case "kcp"` 内输出（`base.go:135-141`） |
| `HeaderType`（ws/h2/xhttp/grpc 网络时） | 只在 `tcp`/`kcp` 分支输出（`base.go:128-141`） |
| `Host`（kcp 网络时） | kcp 分支只输出 `headerType`/`seed` |
| `Path`（tcp 网络时） | tcp 分支只输出 `headerType`/`host`，**丢失 path** |
| `Insecure`（`Security=="reality"` 时） | `if config.Security == "tls"` 才输出（`base.go:90-98`） |
| `MaxEarlyData` 的 header 名 | `EarlyDataHeaderName` **从不序列化**；解析时硬编码为 `Sec-WebSocket-Protocol`（`base.go:245-260`），写回时只写 `?ed=N`（`base.go:263-270`） |
| `BandwidthUp/Down`（Hysteria2 URI） | `ParseHysteria2` 不读 `up`/`down`，`ToHysteria2URI` 不写（`hysteria2.go:35-53,58-101`）——**该字段在 URI 路径上双向都不可达**，只能来自 Clash/sing-box |
| `UDP`（VLESS/VMess/Trojan 等） | `parseQueryParams` 不读 `udp`；`buildQueryParams` 不写。只有 TUIC/SOCKS 路径处理 |
| 全部 Reality/ECH 字段（VMess `ToVMessURI`） | `VmessQRCode` 只有 15 个字段，**没有 `pbk/sid/spx/ech/pqv/pcs/fm`**（`vless.go:57-74`）。而 `profileFromVMessQR` 通过 `vmessJSONToQuery` 确实把 reality 字段写进了 ProfileItem —— 于是 **vmess+reality 解析进来能存住、写回 URI 时全丢** |
| `udp`/`tls`/`skip-cert-verify`（SOCKS/HTTP `To*URI`） | `ToSocksURI`（`socks.go:123-133`）用 `url.URL` 重建，只输出 scheme/host/user/fragment；`ToHTTPURI`（`http.go:40-59`）同理。**`UDP`、`Network`、`Security` 全部丢失** |

### 4.3 会"凭空多出"的东西（往返污染）

无损性不只是"丢"，Proxylink 还会**加**：

- WireGuard 默认值注入：`address=10.0.0.2/32`、`reserved=0,0,0`、`mtu=1420`（`wireguard.go:43,47,57`），且 `ToWireGuardURI` **无条件输出** `address`/`publickey`（`wireguard.go:156-160`）→ 原始 URI 里没有的字段会被写出来。
- `buildQueryParams` **总是**写 `type`（默认 `tcp`）和 `security`（`Security==""` 时写 `none`）（`base.go:66-70,121-125`）。
- `ToHysteria2URI` **总是**写 `insecure=0|1`（`hysteria2.go:68-72`）。
- `ToTrojanURI` **总是**写 `security=tls`（`trojan.go:54-57`）。
- `VmessQRCode.V` 恒为 `"2"`、`Aid` 恒由 `strconv.Itoa(p.AlterId)` 生成（`vless.go:257-262`）—— 无法区分 `aid` 缺失与 `aid=0`。
- `toJSON`/`marshalSingboxJSON` 用 `omitempty`，使**"空串/零值"与"未设置"不可区分**；Xray 侧还专门用 `Flow *string`（`xray.go:50`）打补丁来表示"存在但为空"，说明作者已感知到 presence 信息丢失，但只在单点打补丁。

### 4.4 语义串味（同一参数写进两个字段）

`parseQueryParams` 里同一行区域：

```go
config.Mode = query.Get("mode")        // base.go:27  → grpc 语义
config.XhttpMode = query.Get("mode")   // base.go:30  → xhttp 语义
```

一个 `mode` 参数**同时**写入 `Mode` 和 `XhttpMode`。写回时 grpc 用 `Mode`、xhttp 用 `XhttpMode`，靠"当前 Network 是哪个"掩盖歧义。这是**扁平模型没有 per-transport 命名空间的直接后果**。

另外 `Mode` 在 Xray grpc 侧被解读为 bool（`MultiMode: p.Mode == "multi"`，`xray.go:686`），在 sing-box 侧**完全不参与 grpc 输出**（`singbox.go:261-263` 只写 `service_name`）—— grpc `mode` 转 sing-box 时静默丢失。

### 4.5 没有 round-trip 验证

- 仓库文件树里**没有任何 `*_test.go`**（Trees API 结果共 32 个文件，无测试）。
- 没有 `parse(emit(x)) == x` 之类的不变量检查、没有 golden 文件、没有字段覆盖率断言。
- 因此"丢字段"从未被发现过；§4.2 的清单是我读代码得出的，不是项目已知问题。

---

## 5. 兼容性 / loss 概念

### 5.1 结论：**没有内核/版本维度的兼容性概念；没有字段级 loss/unsupported/skipped/warning 的结构化输出**

全仓库 grep `unsupported`（8 处）、`skipped`（0 处）、`loss`（0 处）、`warning/warn`（仅 stderr `fmt.Fprintf`）、`version`（仅 Hysteria version=2 与 SIP008 `version`）：
**不存在**"目标内核 X 的版本 Y 不支持能力 Z"这类判断。生成器里所有"表达不了"的情况都是**注释 + 静默 return**。

### 5.2 唯一的结构化输出：`ConvertResult`（`converter.go:20-26`）

```go
type ConvertResult struct {
    Profiles []*model.ProfileItem
    Errors   []error      // 解析错误
    Total    int          // 总行数
    Success  int          // 成功数
    Failed   int          // 失败数
}
```

- 粒度是**节点级**，不是字段级：只有"这个节点解析失败"，没有"这个节点解析成功但有 3 个字段无法表达"。
- `Errors` 是 `[]error`，**纯文本、无结构**（无 code/severity/field/direction 字段）。
- 覆盖面仅"输入解析"，**完全不覆盖生成方向**：`GenerateXrayConfig`/`GenerateSingboxOutbound` 不接收也不返回任何诊断载体。
- 好处（值得借鉴）：**单节点失败不会中断整批**（`converter.go:136-145`、`singbox_provider.go:113-138`），错误里带节点身份信息，例如 `unsupported sing-box outbound %q (%s)`（`singbox_provider.go:124`）。

### 5.3 唯一接近"兼容性判断"的机制：**输入侧**的能力注册表 + 忽略表

`pkg/subscription/singbox_provider.go` 里有三个明确的"能不能处理"判定，是本项目最接近我们目标的代码：

| 机制 | 位置 | 语义 |
| --- | --- | --- |
| `isSupportedSingboxOutboundType` | `singbox_provider.go:418-421`（走 `CreateOptions` 注册表 52-75） | 明确列出支持 9 种 outbound |
| `isSupportedSingboxEndpointType` | `423-430` | 只支持 `wireguard`/`tailscale` |
| `isIgnoredSingboxOutboundType` | `409-416` | `direct/block/dns/selector/urltest/pass` → **故意忽略，不计入 `Errors`** |
| `isSupportedClashProxyType` | `432-439` | 支持列表 |

**"故意忽略" vs "不支持"被区分开，且分别计数**（前者 `continue` 不计数，后者走 `addProviderError`）——这正是我们要的语义分层，但**只在 sing-box 订阅输入侧存在**，且粒度仍是"节点类型"，不是"能力"。

### 5.4 静默丢失清单（本项目"绝不静默丢失"的反面教材）

生成方向**完全不报错**的丢失点，按严重度：

1. **AnyTLS/TUIC → Xray**：`GenerateXrayOutbound` default → `nil` → 输出 JSON `null` / `outbounds:[null]`（`xray.go:239-240`，`main.go:361,376-378`）。
2. **HTTP/WireGuard → sing-box**：`buildSingboxOutbound` default → 返回**空字符串 + nil error**（`singbox.go:106-108,208-209`）。
3. **`PinSHA256` → sing-box**：降级为 `insecure=true`（跳过全部证书校验），只有代码注释说明（`singbox.go:304-310`）。
4. **kcp / quic / xhttp → sing-box transport**：`buildSingboxTransport` default → `nil`（`singbox.go:281-282`）。
5. **SS 插件 → Xray**、**quic 参数 → Xray**、**`DisableSNI`/`Mldsa65Verify`(tls)/`SpiderX`/`EchForceQuery`/`PinnedCA256` 跨内核** 全部无提示丢弃（§3.1/§3.2 表）。
6. **SOCKS/HTTP 的 TLS+transport → Xray**：不调用 `buildStreamSettings`（`xray.go:351-403`）。
7. **`NetworkType.ParseNetworkType` 未知值 → `tcp`**（`network_type.go:44-45`）。
8. **`ParseXrayConfig` 多 user / 多 vnext**：`o.Settings.Vnext[0]`、`v.Users[0]`、`o.Settings.Servers[0]`（`xray.go:95,99,113`）→ 静默只用第一条。
9. **`GenerateSingboxOutbounds` 里 `ob == nil` 直接不 append**（`singbox.go:119-125`）→ 批量输出**静默少节点**，数量与输入不一致。

### 5.5 唯一的"显式拒绝"（正面例子）

- 不认识的 scheme / 协议：`parser.go:38-40` 返回 error。
- sing-box endpoint WireGuard 有 **超过 1 个 peer**：`singbox_provider.go:346-349` 返回 `wireguard peer count %d` 错误，**拒绝而不是截断** —— 与 §5.4 第 8 条形成鲜明对比，说明作者知道该怎么做，只是没统一。

---

## 6. 值得我们借鉴的设计

1. **解析器 / 生成器成对同文件、共享映射函数**：`parseQueryParams`（`base.go:13`）与 `buildQueryParams`（`base.go:62`）在同一文件、字段顺序对称；`vmessJSONToQuery`（`vless.go:160`）把 JSON 字段先降维成 query 再复用公共解析，避免"每种输入格式各写一套解析逻辑漂移"。**我们要保留这个"读写映射内聚"，但把白名单换成"注册表 + 未知捕获"。**
2. **"故意忽略"与"不支持"分离（`isIgnoredSingboxOutboundType`，`singbox_provider.go:409-416`）**：这是我们的 `unsupported` 与 `not-a-node` 两类诊断的直接模板，`direct/block/dns/selector/urltest/pass` 不该报错，`hysteria`(sing-box 无) 才该报。
3. **批处理的部分失败聚合 + 错误带节点身份**：`ConvertResult`（`converter.go:20-26`）+ `addProviderProfile/addProviderError`（`singbox_provider.go:379-388`）。我们要把同类载体升级成"节点级 + 字段级"两层。
4. **格式探测的责任链**：`convertContentWithSingboxProvider`（`singbox_provider.go:88-100`）用 `[]func(string)(*ConvertResult,bool)` 依次尝试 sing-box JSON → Clash → SIP008 → 裸链接，`ok=false` 表示"不是我的格式"（可继续），`ok=true` 表示"是我的格式（哪怕有错）"。这个二分是稳定可靠的多格式 ingest 骨架。
5. **不可表达能力的显式"原样透传槽"**：`FinalMask string`（raw JSON，`fm` 参数，`base.go:32`）+ `XhttpExtra string`（`extra`，`base.go:31`），并且在 Xray 生成时**用户显式 JSON 覆盖自动推断**（`xray.go:693-703`）。思路正确（给模型装一个逃生舱，且显式优先），只是没有推广成通用的未知字段保留。
6. **参数别名容忍层**：`firstQueryValue(query, "congestion_control", "congestion-controller")`（`tuic.go:114-121`）、`queryBool(query, "insecure","allowInsecure","allow_insecure","skip-cert-verify")`（`base.go:53`）、`sni`↔`peer`（`base.go:41-44`）。真实 URI 生态就是这样脏的，我们的规范化层必须有别名表，并**记录"命中哪个别名"**（Proxylink 不记录，这就是它丢信息的地方）。
7. **校验即显式结果**：`normalizeHysteriaPortRange` 返回 `(string, bool)`（`singbox.go:391-413`）、`normalizeSingboxPortRange` 返回 `""` 表示非法（`singbox_provider.go:539-558`）、SOCKS 端口范围校验 1..65535（`socks.go:95-98`）。**"非法值要被拒绝并给出理由"**这个签名风格值得照搬，但要让它**产出诊断**而不是静默丢弃。
8. **`parsePathEarlyData` 揭示 URI 字段非正交**（`base.go:245-260`）：`path=/x?ed=2560` 这种"参数里嵌子 URI"是真实存在的，兼容层必须把这类包装拆解成结构化字段，否则 round-trip 必然错位。这个 case 值得作为我们测试语料。
9. **`CUSTOM` 枚举作为未识别协议的显式兜底位**（`config_type.go:17`）——虽然没实现，但"未知协议要有名字而不是 panic/丢弃"的方向是对的。

---

## 7. 我们不能直接照搬的地方

### 7.1 核心问题：**ProfileItem 是被 Xray schema 绑死的扁平并集，同时又被 sing-box 的 option 结构体反向约束**

**（a）字段词汇表是 Xray 的。** `NetworkType`（`network_type.go:6-16`）是 Xray 的 transport 命名；`h2`、`xhttp`、`finalmask/quicParams`（`xray.go:191-208`，经 §0 链接确认属 Xray-core 上游）、`mldsa65Verify`（`xray.go:166`）、`spiderX`、`xhttpSettings`（`xray.go:87`）全是 Xray 概念，却和 sing-box 概念（`DisableSNI`、`utls.fingerprint`）混在同一个扁平命名空间里。**结果：无法回答"这个字段是哪个内核的能力"。** 例如 `Security=="reality"` 到底是 Xray reality 还是 sing-box reality？两者的 `SpiderX`/`Mldsa65Verify` 支持面不同，模型里没有区分依据。

**（b）反解 side 直接 import 内核库。** `pkg/subscription/singbox_provider.go:15-21` import `github.com/sagernet/sing-box/option`，`go.mod:7` 钉死 `sing-box v1.13.14`。于是 **ProfileItem 的表达能力天花板 = sing-box option 结构体 ∩ 手写 switch**。升级 sing-box 版本会静默改变可识别字段集；且 sing-box 新增的能力（如新的 TLS 选项）**不会**自动进入模型，也不会被报告为"未识别"。
同理 Clash 侧 `ClashProxy`（`clash.go:19-78`）是 mihomo schema 的镜像，Xray 侧 `generator/*` 是 Xray schema 的镜像。**三个内核 schema 都被转写进了同一个扁平结构，谁也不是"中立"的。**

**（c）一节点一真相，没有来源/优先级/版本维度。** `ProfileItem` 无法表达"这个字段来自 URI，那个字段来自 Clash 模板"，也无法表达"这是按 Xray 语义解析的"。合并冲突只能靠后写覆盖（`fromClashProxy` 的字段赋值顺序、`parseQueryParams` 的 `Mode`/`XhttpMode` 双写）——**必然的静默覆盖**。

**（d）presence 信息被零值吞掉。** 全项目靠 `omitempty` + `""`/`false`/`0` 表示"未设置"，只有在 `xray.go:50` 用 `Flow *string` 打了一个补丁。我们若要做"绝不静默丢失"，**必须先区分"字段不存在"与"字段等于零值"**（用指针/optional 或 presence 位图），否则连"丢了什么"都定义不出来。

**（e）归一化过早。** `base.go:36-38` 把非 `tls/reality` 的 `security` 直接抹成 `""`；`network_type.go:44-45` 把未知 transport 抹成 `tcp`；`hysteria2.go:16` / `wireguard.go:17` 把 `hy2://`/`wg://` 直接字符串替换成 `hysteria2://`/`wireguard://`；`clash.go:295` 把 Clash `http` 改写成 `h2`。**这些映射决策全部无记录、无方向、不可逆。** 我们的层必须把"归一化"变成**有日志的、可逆的、带 source/target 的映射**。

**（f）死字段与不对称字段说明模型没有被验证过。** `SubscriptionID` 从未赋值（§1.3）；`BandwidthUp/Down` 在 Hysteria2 URI 路径双向不可达（§4.2）；`QuicSecurity`/`QuicKey` 只进不出；`ClashHttpOpts.Method` 只解不用。这些都不是"设计选择"，而是缺少 round-trip 测试的表现。

**（g）`CUSTOM`/`XhttpExtra` 这类逃生舱是打补丁而非扩展机制。** 只有 2 个硬编码的 opaque 槽，且都绑定具体参数名（`fm`/`extra`）。我们需要的是**通用**的 `unknown`/`vendor` 容器 + 可声明的 namespace。

---

## 8. 它没覆盖、而我们需要的能力

| 我们需要 | Proxylink 的现状 | 证据 |
| --- | --- | --- |
| **内核身份维度** | 没有。内部只有"输入格式"（URI/Clash/Xray/sing-box），没有"输出目标"这个概念——目标格式只是 `main.go` 的一个字符串 flag（`outputFormat`），不参与任何判断 | `main.go:26`、`generator` 里没有 target 参数 |
| **内核版本维度** | **完全没有**。生成 anytls/tuic/xhttp/reality/finalmask 时不做任何版本判断；也没有 `minVersion` 表 | grep `version` 仅命中 Hysteria `version:2` 与 SIP008 |
| **静默降级检测** | 没有。最严重的降级（`PinSHA256 → insecure`）只有注释 | `singbox.go:304-310` |
| **字段级 loss 报告** | 没有。只有节点级 `Errors []error`，且不覆盖生成方向 | `converter.go:20-26` |
| **未知字段/厂商扩展保留** | 没有。59 个字段全为已知标量，无 `RawURI`/`RawQuery`/`Extra`/`Unknown`；未知 key 连读都不读 | §2.2、§6 |
| **round-trip 不变量校验** | 没有。仓库无任何测试文件 | Trees API 结果无 `*_test.go` |
| **能力声明 / feature 注册表（能力粒度）** | 只有**节点类型**粒度的注册表，且仅在 sing-box 订阅输入侧 | `singbox_provider.go:52-75,409-439` |
| **multiplex / 多路复用** | 完全没有（模型无字段，Xray 恒 disabled，sing-box 无输出） | grep `mux\|multiplex` |
| **多 peer / 多 vnext WireGuard 与多 user** | 输入侧对 sing-box WG 多 peer 显式报错（好），Xray 侧 `[0]` 静默截断（坏） | `singbox_provider.go:346-349` vs `xray.go:95,99,113` |
| **诊断分级（info/warn/degraded/unsupported）** | 没有分级，只有 `error` 与"没有 error" | — |
| **"表达不了"→拒绝还是降级，需可配置** | 不可配置，一律静默；行为在不同协议间还不一致（`PinSHA256` 降级、`kcp` 丢弃、`AnyTLS→Xray` 变 null） | §5.4 |
| **安全的敏感降级必须阻断** | `PinSHA256 → 跳过证书校验` 无任何告警 | `singbox.go:308-310` |

---

## 9. UNKNOWN

以下事项我**没有确认，不做推测**：

1. **未编译、未运行。** 本机无 Go 工具链，§3/§4/§5 的"丢弃"结论全部来自静态读代码路径，**没有实测输出**。要作为硬证据需补一次 `go run` / 单元测试。
2. **`singjson.UnmarshalContext`（sing-box 1.13.14）对未知 JSON key 的严格程度未验证**：未知 key 是报错、忽略还是可配置，我未查该库源码，因此"sing-box JSON 的未知字段被静默忽略"这一条**待验证**。
3. **`XrayConfig` 只解析 `outbounds` 之外还会丢掉什么**：`inbounds/routing/dns/log/observatory` 等未在结构体中，但主流程是否在别处使用它们，我未逐一确认（看起来没有）。
4. **`hysteria` protocol + `finalmask` 所需的最低 Xray-core 版本未知**：已确认这两个是上游 Xray-core 特性（§0 链接），但**具体从哪个版本开始可用我没有查证**，因此无法判断 Proxylink 实际对标的 Xray 版本下限。
5. **VMess `vmess://` JSON 缺字段时真实客户端的容错**未知（`ToVMessURI` 恒定输出 `v:"2"`、`aid:"0"` 等，是否会破坏某些客户端未验证）。
6. **`ParseXrayConfig` 对"别名/重复 tag"的行为**未追（只有 `o.Tag` → `Remarks`）。
7. **`splitSSPlugin` / `clashSSPluginOpts` 对含 `;` 或 `=` 的取值是否会二次拆分**：`shadowsocks.go:104` 用 `SplitN(...,2)` 取 opts 整体存 string，而 `parseSSPlugin` 用 `Split(";")` 再解析——嵌套 `;` 的取值（如 v2ray-plugin 的 `path` 含 `;`）行为未验证。
8. **项目是否有 release/tag 或 CHANGELOG**：未查（本次只读 `main` 分支单一 commit）。
9. **`maxSubscriptionSize`、UA fallback 列表等运行期行为**对本调研无关，未评估（`fetcher.go:11-17,88`）。
10. **`CUSTOM` 枚举是否计划实现**：无证据可判断（当前无 parser、无 scheme、两个 generator 都返回 nil）。

---

## 附：对 proxy-node-compat 的直接结论（一句话版）

Proxylink 证明了"统一中间模型 + 多格式生成"的骨架是可行的，但它的 `ProfileItem` 是一个**被 Xray schema 定调、被 sing-box option 反向约束的 59 字段扁平并集**：未知参数在解析层就看不见、目标内核表达不了的字段在生成层静默消失（最严重的是 `PinSHA256 → insecure=false 校验`）、唯一的结构化输出 `ConvertResult` 只统计节点级解析成败、round-trip 无任何不变量校验。**我们要借鉴它的读写映射内聚、"故意忽略 vs 不支持"分层、以及部分失败聚合；必须放弃它的扁平单层模型，改为"分层能力 + 内核/版本维度 + presence 显式化 + 通用 unknown 容器 + 字段级 loss 诊断"。**
