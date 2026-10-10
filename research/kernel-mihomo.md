# mihomo（Mihomo Meta / Clash.Meta）节点能力与兼容性清单

- **目标内核版本**：Mihomo Meta **v1.19.32**（GitHub Releases API `tag_name=v1.19.32`，`published_at=2026-09-30T17:09:36Z`，`prerelease=false`；这是抓取时的最新稳定版，`Prerelease-Alpha` 为滚动预发布）
- **分析对象**：`MetaCubeX/mihomo` 源码 **tag `v1.19.32`**（通过对 `codeload.github.com/MetaCubeX/mihomo/tar.gz/refs/tags/v1.19.32` 的 tarball 逐文件阅读）
- **文档对象**：`MetaCubeX/Meta-Docs` @ `main`（commit `c47fd7212afc3f0e6afe9c7cb18591ba55e5e79b`，2026-10-03），即 <https://wiki.metacubex.one> 的源
- **本文的铁律**：每条结论都带证据标签。**没有 `[test]` 条目** —— 本次研究没有内核运行环境，不做任何运行验证，凡未从文档/源码确认的一律进 `## 8. UNKNOWN 清单`。

---

## 0. 证据来源

### 0.1 真查过的来源（全部实际抓取成功）

| 标签 | 来源 | 说明 |
|---|---|---|
| `[src]` | `MetaCubeX/mihomo` **v1.19.32** 源码 tarball（`https://codeload.github.com/MetaCubeX/mihomo/tar.gz/refs/tags/v1.19.32`，约 1.27 MB，984 个 `.go` 文件） | 本文所有 `路径:行号` 均指该 tag 下的文件 |
| `[doc]` | `MetaCubeX/Meta-Docs` raw markdown（`https://raw.githubusercontent.com/MetaCubeX/Meta-Docs/main/docs/...`），渲染页 `https://wiki.metacubex.one/...` | 英文页为主，中文页交叉核对 |
| `[meta]` | GitHub Releases API `https://api.github.com/repos/MetaCubeX/mihomo/releases/latest`；Release Atom feed `https://github.com/MetaCubeX/mihomo/releases.atom` | 仅用于确定版本号与发布时间 |
| `[test]` | **无** | 本次无内核运行环境，0 条 |

### 0.2 版本时间线

`[meta]` 先确认：Atom feed 只返回**最新 10 条**，且 `?page=N` 无效（第 2/3/4 页字节完全相同，各 389,877 B）。因此完整历史改用**完整 git clone**（`origin/Meta`，4330 commits）取 tag 列表 + 逐个 `releases/tag/<tag>` 页面取正文：

- **共 114 个版本 tag**：`v0.x` 25 个（继承自 Clash 线）+ `v1.x` 89 个（其中 7 个 `_tun` 变体）。
- 滚动/非版本 tag：`Prerelease-`、**`Prerelease-Alpha`**（2026-10-08）、`core`、`mini`、`plus`、`plus_pro`、`premium`、`test`。
- **v1.19.32 是当前稳定版**；除滚动 `Prerelease-Alpha` 外没有更新的版本。
- ⚠️ `v1.0.0`–`v1.8.0` 的 release **正文为空**（`v1.9.1`、`v1.11.4`、`v1.11.8`、`v1.13.0` 亦为空），v1.9.0 起才有内容 → **早期能力的版本门槛不可考**（见 §8）。
- ⚠️ **git 图不连续**：`v1.14.x`–`v1.18.5` 这些 tag **不是** `origin/Meta` tip 的祖先。因此本文所有 v1.19.x 的门槛都额外用「该 tag 下的 raw 文件」二次确认。

最近 25 个版本（git `creatordate`；最新 10 个以 release 页 UTC 为准）：

| tag | 日期 | tag | 日期 |
|---|---|---|---|
| **v1.19.32** | **2026-09-30** | v1.19.19 | 2026-01-16 |
| v1.19.31 | 2026-09-14 | v1.19.18 | 2025-12-21 |
| v1.19.30 | 2026-08-16 | v1.19.17 | 2025-12-01 |
| v1.19.29 | 2026-07-18 | v1.19.16 | 2025-11-09 |
| v1.19.28 | 2026-07-08 | v1.19.15 | 2025-10-15 |
| v1.19.27 | 2026-06-06 | v1.19.14 | 2025-09-24 |
| v1.19.26 | 2026-05-30 | v1.19.13 | 2025-08-27 |
| v1.19.25 | 2026-05-16 | v1.19.12 | 2025-07-27 |
| v1.19.24 | 2026-04-20 | v1.19.11 | 2025-06-25 |
| v1.19.23 | 2026-04-08 | v1.19.10 | 2025-05-29 |
| v1.19.22 | 2026-04-01 | v1.19.9 | 2025-05-21 |
| v1.19.21 | 2026-03-09 | v1.19.8 | 2025-05-13 |
| v1.19.20 | 2026-02-08 | | |

### 0.3 文档中出现的版本号（`[doc]`，全文仅此几处）

- `v1.19.18` — “Starting from version v1.19.18, automatic reloading is supported when `certificate`, `private-key`, or `ech-key` are local files.”（<https://wiki.metacubex.one/en/config/general/>）
- `v1.19.20` — “From v1.19.20 onwards, the SNI/servername requirement must also be met.”（`fingerprint` 证书固定，<https://wiki.metacubex.one/en/config/proxies/tls/>）
- `v1.19.30` — “this data is no longer sent by default starting from v1.19.30”（AnyTLS `client-metadata`，<https://wiki.metacubex.one/en/config/proxies/anytls/>）
- `xray v26.7.11+` — Reality 不兼容声明，指 **Xray 服务端**版本，不是 mihomo 版本

### 0.4 关键源码锚点（后文反复引用）

| 主题 | 位置 |
|---|---|
| proxy type 注册表 | `adapter/parser.go:14-284`（`ParseProxy` 的 `switch proxyType`） |
| YAML→结构体解码器 | `common/structure/structure.go`（`Decoder.Decode` / `decodeStructFromMap`） |
| 顶层 config 解析 | `config/config.go:607-622`（`UnmarshalRawConfig`）、`config/config.go:403-471`（`RawConfig`） |
| 配置校验入口（`-t`） | `main.go:76`（`flag.BoolVar(&testConfig, "t", ...)`）、`main.go:175-187` |
| TLS 栈 | `transport/vmess/tls.go`（`StreamTLSConn`）、`component/tls/utls.go`、`component/tls/reality.go`、`component/ca/config.go` |
| 订阅/URI 解析 | `common/convert/converter.go`、`common/convert/v.go`、`adapter/provider/provider.go` |
| provider override | `adapter/provider/override.go`（`overrideSchema`） |

---

## 1. proxy types 清单

`type` 字面量 = `adapter/parser.go` 中 `case` 的值。**未列出的 type 一律硬失败**：`adapter/parser.go:281` → `return nil, fmt.Errorf("unsupport proxy type: %s", proxyType)`；缺 `type` 键 → `adapter/parser.go:17` → `missing type`。

「必填字段」列 = **解码器级必填**：`structure` tag 中**不带** `,omitempty` 的字段，缺键会报 `'xxx' has unset fields: ...`（`common/structure/structure.go:585-593`）。注意这**不是**语义必填，只是「键必须出现」。

| type | 支持(版本) | 必填字段（解码器级） | 证据 |
|---|---|---|---|
| `ss` | ≤ **v1.6.5**（更早无证据） | `name`,`server`,`port`,`password`,`cipher` | `[src] adapter/parser.go:33`；`adapter/outbound/shadowsocks.go:44-56`；版本：`[src]` tag `v1.6.5` 树中已有 `adapter/outbound/snell.go` 等同类文件，v1.0.0–v1.8.0 的 release 正文为空故无法精确定位 |
| `ssr` | ≤ **v1.6.5** | `name`,`server`,`port`,`password`,`cipher`,`obfs`,`protocol` | `[src] adapter/parser.go:41`；`adapter/outbound/shadowsocksr.go:33-42` |
| `socks5` | ≤ **v1.6.5**（**字面量是 `socks5`，不是 `socks`**） | `name`,`server`,`port` | `[src] adapter/parser.go:49`；`adapter/outbound/socks5.go:31-46`；`[doc]` 页面标题写 “SOCKS” 但示例是 `type: socks5` <https://wiki.metacubex.one/en/config/proxies/socks/> |
| `http` | ≤ **v1.6.5** | `name`,`server`,`port` | `[src] adapter/parser.go:57`；`adapter/outbound/http.go:30-43` |
| `vmess` | ≤ **v1.6.5** | `name`,`server`,`port`,`uuid`,**`alterId`**,**`cipher`** | `[src] adapter/parser.go:65`；`adapter/outbound/vmess.go:57-89`（`AlterID`/`Cipher` 均无 `omitempty`）；`alterId` 至今仍被接受：`[src] v1.19.32 vmess.go:59` |
| `vless` | **v1.10.0** | `name`,`server`,`port`,`uuid` | `[src] adapter/parser.go:73`；`adapter/outbound/vless.go:61-91`；`[meta]` RN v1.10.0 “支持出站传输协议 VLESS XTLS / Trojan XTLS” |
| `snell` | ≤ **v1.6.5** | `name`,`server`,`port`,`psk` | `[src] adapter/parser.go:81`；`adapter/outbound/snell.go:33-43`；`snell.version` 4/5 支持在 **v1.19.26**（RN “52edebd feat: add snell version 4/5 outbound and inbound (#2817)”） |
| `trojan` | ≤ **v1.6.5** | `name`,`server`,`port`,`password` | `[src] adapter/parser.go:89`；`adapter/outbound/trojan.go:45-70` |
| `hysteria` | **≤ v1.12.0** | `name`,`server`,**`up`**,**`down`**（**`port` 非必填**） | `[src] adapter/parser.go:97`；`adapter/outbound/hysteria.go:100-120`；`[meta]` RN v1.12.0 “Hysteria协议支持” |
| `hysteria2` | **v1.16.0** | 仅 `name`,`server`（`port`/`ports`/`password` 全部可选） | `[src] adapter/parser.go:105`；`adapter/outbound/hysteria2.go:40-70`；`[meta]` RN v1.16.0 “feat: support Hysteria2” |
| `wireguard` | **v1.14.0** | `name`,`private-key`（**`server`/`port` 非必填**，多 peer 时忽略） | `[src] adapter/parser.go:113`；`adapter/outbound/wireguard.go:63-90`；`[meta]` RN v1.14.0 “support wireguard outbound”；`[doc] wg` 页 “top-level fields such as `server`… are ignored” |
| `tuic` | **v1.14.0**（TUIC v4）/ **v1.15.0**（v5） | `name`,`server`,`port`（**`token`/`uuid`/`password` 源码里全可选**，见 §1.2） | `[src] adapter/parser.go:121`；`adapter/outbound/tuic.go:36-70`；`[meta]` RN v1.14.0 “add tuic outbound”、RN v1.15.0 “feat: support tuicV5” |
| `shadowquic` | **v1.19.29** | `name`,`server`,`port`（`username`/`password` **可选**） | `[src] adapter/parser.go:129`；`adapter/outbound/shadowquic.go:30-55`；`[meta]` RN v1.19.29 “aea5ce4 feat: support shadowquic outbound and listener”；`[src]` v1.19.28 的 `parser.go` 无该 case |
| `gost-relay` | **v1.19.25** | `name`,`server`,`port` | `[src] adapter/parser.go:137`；`[meta]` RN v1.19.25 “5e22035 feat: add GOST relay outbound proxy type (#2795)”（注意与 ss 插件 `gost-plugin`（v1.19.4）不是同一个东西） |
| `direct` | ≤ **v1.6.5** | `name` | `[src] adapter/parser.go:145`；`adapter/outbound/direct.go` |
| `dns` | ≤ **v1.6.5** | `name` | `[src] adapter/parser.go:153`；`adapter/outbound/dns.go` |
| `reject` | ≤ **v1.6.5** | `name` | `[src] adapter/parser.go:161`；`adapter/outbound/reject.go` |
| `rematch` | **v1.19.28** | `name` | `[src] adapter/parser.go:169`；`[meta]` RN v1.19.28 “ea19cda feat: add rematch outbound type and REMATCH-NAME rule type (#2862)”；`[src]` v1.19.27 无 / v1.19.28 有 |
| `ssh` | ≤ **v1.6.5** | `name`,`server`,`port`,`username` | `[src] adapter/parser.go:177`；`adapter/outbound/ssh.go` |
| `mieru` | **v1.19.0** | `name`,`server`,`transport`,`username`,`password` | `[src] adapter/parser.go:185`；`adapter/outbound/mieru.go:31-43`；`[meta]` RN v1.19.0 “613becd feat: support mieru protocol (#1702)” |
| `anytls` | **v1.19.3** | `name`,`server`,`port`,`password` | `[src] adapter/parser.go:193`；`adapter/outbound/anytls.go:27-49`；`[meta]` RN v1.19.3 “9962a0d feat: implement anytls client and server (#1844)”；`[src]` v1.19.2 无 / v1.19.3 有 |
| `sudoku` | **v1.19.17** | `name`,`server`,`port`,`key` | `[src] adapter/parser.go:201`；`adapter/outbound/sudoku.go:33-57`；`[meta]` RN v1.19.17 “6cf1743 feat: add Sudoku protocol inbound & outbound support (#2397)” |
| `masque` | **v1.19.20** | `name`,`server`,`port`,`private-key`,`public-key` | `[src] adapter/parser.go:209`；`adapter/outbound/masque.go:55-75`；`[meta]` RN v1.19.20 “e45c896 feat: support masque outbound” |
| `trusttunnel` | **v1.19.21** | `name`,`server`,`port` | `[src] adapter/parser.go:217`；`adapter/outbound/trusttunnel.go:23-45`；`[meta]` RN v1.19.21 “4ca5158 feat: support trusttunnel inbound and outbound” |
| `openvpn` | **v1.19.25** | `name`,`server`,`port`,`ca` | `[src] adapter/parser.go:225`；`adapter/outbound/openvpn.go:45-75`；`[meta]` RN v1.19.25 “7af9eeb feat: add OpenVPN outbound support (#2785)” |
| `tailscale` | **v1.19.25** | `name` | `[src] adapter/parser.go:233`；`adapter/outbound/tailscale.go`；`[meta]` RN v1.19.25 “571925d feat: add Tailscale outbound support (#2786)” |
| `zerotier` | **v1.19.30** | `name`,`network` | `[src] adapter/parser.go:241`；`adapter/outbound/zerotier.go:105-125`；`[meta]` RN v1.19.30 “b082515 feat: add Zerotier outbound support” |
| `easytier` | **v1.19.31** | `name` | `[src] adapter/parser.go:249`；`adapter/outbound/easytier.go`；`[meta]` RN v1.19.31 “dca26db feat: add EasyTier outbound (#3194)” |

**共 28 个 `type` 字面量**（其中 `direct`/`dns`/`reject`/`rematch` 不是远程节点）。

> **版本维度要点**：`v1.19.24` 之后仍持续新增 type —— `openvpn`/`tailscale`/`gost-relay` 在 **v1.19.25**，`rematch` 在 **v1.19.28**，`shadowquic` 在 **v1.19.29**，`zerotier` 在 **v1.19.30**，`easytier` 在 **v1.19.31**。兼容性判断**必须带内核版本**，否则 “支持 easytier” 这种结论在 v1.19.30 上就是错的。

### 1.1 内部 AdapterType 与 type 的关系

`[src] constant/adapters.go:18-58` 定义内部枚举：`Direct, Reject, RejectDrop, Compatible, Pass, PassRule, Rematch, Dns, Relay, Selector, Fallback, URLTest, LoadBalance, Shadowsocks, ShadowsocksR, Snell, Socks5, Http, Vmess, Vless, Trojan, Hysteria, Hysteria2, WireGuard, Tuic, Ssh, Mieru, AnyTLS, Sudoku, Masque, TrustTunnel, ShadowQuic, OpenVPN, Tailscale, ZeroTier, EasyTier, GostRelay`。

- **没有独立的 AdapterType 给 ShadowTLS / Restls / JLS / TLSMirror / ECH / Reality** —— 它们在 mihomo 里是 **TLS 子模式**，不是节点类型（`[src]` 同上）。
- `Relay` 仍在枚举里，但解析层已无 `type: relay`（见 `## 6. 弃用与移除`）。
- `[doc]` 的 `built-in` 页列出 `DIRECT`/`REJECT`/`REJECT-DROP`/`PASS`/`PASS-RULE`/`COMPATIBLE` 是**规则目标名**，不是 `type:` 值（<https://wiki.metacubex.one/en/config/proxies/built-in/>）。

### 1.2 四个层次的差异（本节要点）

| 层次 | 现状 |
|---|---|
| Node Feature（节点能力） | e.g. “VLESS + Reality + XHTTP + flow” |
| URI Representation | `vless://…?security=reality&type=xhttp&flow=xtls-rprx-vision…`，**见 §7：`type=httpupgrade`/`splithttp`/`kcp` 会被原样写进 `network`** |
| Kernel Representation | mihomo YAML `type: vless` + `network:` + `reality-opts:` + `flow:` |
| Runtime Support | **`network` 不校验 → 未知值静默按 TCP**；`flow` 短于 16 字符时静默丢弃；Reality 在 `ws` 路径下不接线（§5） |

---

## 2. transport / network

### 2.1 结论先行

mihomo **v1.19.32 中 `network` 字段没有任何枚举校验**。vmess/vless/trojan 的 `StreamConnContext` 是 `switch option.Network { ... default: /* default tcp network */ }`，未知值不报错、不告警，**静默按 tcp 处理**（只走 TLS 包装，然后直接发协议头）。

- `[src] adapter/outbound/vless.go:155-262`（`switch v.option.Network`，`default:` 注释即 “// default tcp network”）
- `[src] adapter/outbound/vmess.go:174-291`（同上）
- `[src] adapter/outbound/trojan.go:78-190`（同上）
- `[src] adapter/outbound/vless.go:340-349`、`vmess.go:382-402`、`trojan.go:210-218`：`dialContext` 的 `default:` → `dialer.DialContext(ctx, "tcp", addr)`
- `[doc]` 官方文档**明确承认**该行为：vless 页 “Transport layer. Supports `ws`/`http`/`h2`/`grpc`/`xhttp`. **If unset or set to another value, TCP is used.**”（<https://wiki.metacubex.one/en/config/proxies/vless/>）；vmess 页同句，列表为 `ws/http/h2/grpc/mkcp/mekya`；trojan 页同句，列表为 `ws/grpc`

> **本项目核心结论 1**：`network` 是「写了不一定生效」的字段。`mihomo -t` 通过 ≠ 该 transport 被使用。伪造一个 `totally-nonsense-transport` 与写 `network: quic` 在 v1.19.32 中完全等价。

### 2.2 network 值总表

| network 值 | 是否真支持 | 不支持时的行为 | 证据 |
|---|---|---|---|
| `tcp` | ✅ 全部支持 | —（默认路径） | `[src]` 三个 `default:` 分支；`[doc]` 三个页面的 `network` 小节 |
| （未写） | ✅ 等价 tcp | — | `[doc]`“If unset … TCP is used” |
| `ws` | ✅ vmess / vless / trojan | **其它类型**：`ws-opts` 整个是未知键 → 静默丢弃 | `[src] adapter/outbound/vmess.go:176`、`vless.go:157`、`trojan.go:80`；`grep -rln 'case "ws"' adapter/outbound/*.go` 只命中这 3 个文件 |
| `http`（HTTP 伪装，非 h2） | ✅ vmess / vless | trojan 写 `network: http` → **静默按 TCP**（trojan 无 `case "http"`） | `[src] vmess.go:246`、`vless.go:226`；trojan 只有 `ws`/`grpc`/`default`（`trojan.go:79-190`） |
| `h2` | ✅ vmess / vless | trojan 写 `network: h2` → **静默按 TCP** | `[src] vmess.go:262`、`vless.go:242`；`[doc]` trojan 页只列 `ws`/`grpc` |
| `grpc` | ✅ vmess / vless / trojan | 其它类型 → 未知键静默丢弃 | `[src] vmess.go:274`+`382`、`vless.go:254`+`341`、`trojan.go:148`+`211` |
| `xhttp` | ✅ **仅 vless** | vmess/trojan 写 `network: xhttp` → **静默按 TCP**；其它类型 → 未知键丢弃 | `[src] adapter/outbound/vless.go:256`+`343`；`grep -rln '"xhttp"' adapter/outbound/` 只命中 `vless.go`；`[doc]` transport 页 note：“Only VLESS supports the xhttp transport layer. Do not use it with other protocols.” |
| `mkcp` / `kcp` | ✅ **仅 vmess**（`kcp` 是别名） | vless/trojan 写 `mkcp` → **静默按 TCP** | `[src] adapter/outbound/vmess.go:388`（`case "mkcp", "kcp"`）、`vmess.go:565`；`grep -rln '"mkcp"'` 只命中 `vmess.go`；`[doc]` “Only VMess supports the mKCP transport layer.” |
| `mekya` | ✅ **仅 vmess**（v1.19.32 新增，源码与文档一致） | vless/trojan 写 `mekya` → **静默按 TCP** | `[src] adapter/outbound/vmess.go:272`+`386`；`grep -rln mekya adapter/outbound/` 只命中 `vmess.go`；`[doc]` “Only VMess supports the Mekya transport layer.” |
| `httpupgrade` | ❌ **不被任何 outbound 处理** | **静默按 TCP（含 TLS）**，`ws-opts` 一并被忽略 | `[src]` 字符串 `"httpupgrade"` 全仓库**只出现在 `common/convert/converter.go:356,375` 与 `common/convert/v.go:110,127`**（订阅解析层），`adapter/` 下 0 次；见 §7.3 |
| `splithttp` | ❌ **字符串在整个 v1.19.32 仓库中不存在** | 静默按 TCP（值被原样写进 `network`） | `[src] grep -rn splithttp`（全仓库 0 命中）；`[doc]` Meta-Docs 全语言 `grep splithttp` 也是 0 命中 |
| `quic` | ❌ 作为 transport `network` 值不支持 | **仅 masque** 把 `network: quic` 当作自己的模式（默认值）；在 vmess/vless/trojan 上写 `quic` → 静默按 TCP | `[src] adapter/outbound/masque.go:158,180`；`[doc]` masque 页 “Optional. Defaults to `quic`.”；vmess/vless/trojan 页的列表里没有 `quic` |
| `h3-l4proxy` | ❌ 只在 masque 有意义 | 在 vmess/vless/trojan 上 → 静默按 TCP | `[src] adapter/outbound/masque.go:158`（`option.Network == "h3-l4proxy"`）；`[doc]` masque 页 |

### 2.3 type × network 支持矩阵（`[src]`，逐一核对 switch）

| type | tcp | ws | http | h2 | grpc | xhttp | mkcp/kcp | mekya |
|---|---|---|---|---|---|---|---|---|
| `vmess` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| `vless` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| `trojan` | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| 其它 type | 无 `network` 字段 → 写了即未知键，静默丢弃 | | | | | | | |

`[src]`：`vmess.go:175-291` / `:382-402`；`vless.go:156-262` / `:340-349`；`trojan.go:79-190` / `:210-218`。

### 2.4 与 transport 配套的 `*-opts` 字段

| 字段 | 挂在哪 | 证据 |
|---|---|---|
| `ws-opts{path, headers, max-early-data, early-data-header-name, v2ray-http-upgrade, v2ray-http-upgrade-fast-open}` | `vmess`/`vless`/`trojan` | `[src] adapter/outbound/vmess.go:165-172`；`[doc]` <https://wiki.metacubex.one/en/config/proxies/transport/> |
| `http-opts{method, path, headers}` | `vmess`/`vless` | `[src] vmess.go:145-149` |
| `h2-opts{host, path}` | `vmess`/`vless` | `[src] vmess.go:151-154`。**h2 无多路复用**：`[doc]` transport 页 note “Mihomo's H2 transport layer does not implement multiplexing.” |
| `grpc-opts{grpc-service-name, grpc-user-agent, ping-interval, max-connections, min-streams, max-streams}` | `vmess`/`vless`/`trojan` | `[src] vmess.go:156-163` |
| `mkcp-opts{mtu, tti, uplink-capacity, downlink-capacity, congestion, write-buffer, read-buffer, seed, header}` | `vmess` | `[src] vmess.go:91-101`；`[doc]` “Available values: `none`/`srtp`/`utp`/`wechat-video`/`dtls`/`wireguard`” |
| `mekya-opts{url, h2-pool-size, max-write-delay, max-request-size, polling-interval-initial, max-write-size, max-write-duration-ms, max-simultaneous-write-connection, packet-writing-buffer, kcp}` | `vmess` | `[src] vmess.go:117-143` |
| `xhttp-opts{...}`（25 个子键，含 `reuse-settings`(=XMUX)、`download-settings`） | **仅 vless** | `[src] adapter/outbound/vless.go:93-137`；`[doc]` transport 页 |

> **XHTTP 行为差异（重要）**：`[doc]` “Note: unlike the original implementation, this option has no default value. If omitted, connection reuse is disabled and each request opens a new underlying connection.” —— 即 **mihomo 的 `reuse-settings` 默认关闭复用，与 Xray 默认值不同**；同名节点在 Xray 与 mihomo 上表现不同，属于「节点特性 → 内核表现」不一致的典型案例。

**对照组：`xhttp-opts.mode` 是「真校验」**（与 `network` 形成鲜明对比）：

- `[src] transport/xhttp/config.go:70-89`：`NormalizedMode()` 把空值 → `"auto"`；`EffectiveMode(hasReality)` 再把 `"auto"` 解析为 `stream-one`（有 Reality 且无 download-settings）/ `stream-up`（有 Reality 且有 download-settings）/ `packet-up`（无 Reality）。
- `[src] transport/xhttp/client.go:246-252`：`switch mode { case "stream-one","stream-up","packet-up": default: return nil, fmt.Errorf("xhttp mode %s is not implemented yet", mode) }`
- `[src] adapter/outbound/vless.go:911-914`：`xhttp.NewClient(...)` 在 **`NewVless` 构造期**调用 → 非法 `mode` 是**配置期硬错误，`mihomo -t` 会失败**。
- 因此显式可用值只有 `stream-one` / `stream-up` / `packet-up`（以及等价于空的 `auto`）。`[doc]` 正文写 “Available values: `auto`, `stream-one`, `stream-up`, or `packet-up`”，同页 YAML 注释却写 “Available: "stream-one", "stream-up" or "packet-up"”（无 `auto`）—— **文档自相矛盾**，源码行为是「两者都对，因为 `auto` 会被再解析」。

### 2.5 其它 transport 相关硬事实

- `[src] adapter/outbound/vless.go:340-346`：`grpc`/`xhttp` 在 **`dialContext` 阶段**就建立了专用连接（`gunClient.Dial()` / `xhttpClient.Dial(ctx)`），`StreamConnContext` 里对应 `case` 是空 `break`。
- `[src] adapter/outbound/vmess.go:565-571`：vmess 里 `mkcp`/`kcp` 与 `ShadowTLS`/`Restls`/`JLS` 互斥 → 硬错误 `"%s only supports TCP transports"`（**这是少数会报错的组合**）。
- `[src] adapter/outbound/vmess.go:572-578` / `vless.go:559-564`：`network: h2` 且未给 `h2-opts.host` 时，**静默注入默认值 `www.example.com`**。
- `[src] adapter/outbound/vless.go:190-196`：`network: ws` 且 `tls: false` 且没有 Host 头时，**静默注入随机 Host 与 UA**（`convert.RandHost()` / `convert.SetUserAgent`）。这属于「运行时自造字段」，兼容性判断时不能把「节点没写 Host」当成错误。

### 2.6 transport 版本门槛（`[meta]` release notes + `[src]` 逐 tag 文件比对）

| 能力 | 最早版本 | 证据 |
|---|---|---|
| `network: xhttp` | **v1.19.22** | RN v1.19.22 “530c6b4 feat: add xhttp transport support (#2645) by @Nemu-x”；`[src]` v1.19.21 的 `vless.go` 有 0 个 `case "xhttp"`，v1.19.22 有 3 个 |
| `xhttp-opts` 基础集（`path`,`host`,`mode`,`headers`,`no-grpc-header`,`x-padding-bytes`,`download-settings`） | **v1.19.22** | `[src]` v1.19.22 `XHTTPOptions` 结构体 |
| `xhttp-opts.reuse-settings`（即 XMUX）、`sc-max-each-post-bytes` | **v1.19.23** | RN v1.19.23 “d131991 feat: add reuse-settings support for vless xhttp (aka xmux) (#2670)”、“8b37e99 feat: support sc-max-each-post-bytes…” |
| `mode: h3` / `mode: http1.1`、`x-padding-obfs-mode/key/header/placement/method`、`uplink-http-method`、`session-placement/key`、`seq-placement/key`、`uplink-data-placement/key`、`uplink-chunk-size`、`sc-min-posts-interval-ms` | **v1.19.24** | RN v1.19.24 “cacd01a feat: add h3 mode support for xhttp client (#2686)”、“61dc7b1 … http1.1 mode”、“2337d70 feat: support xhttp new options for bypassing CDN's potential detection” |
| `xhttp-opts.session-table` / `session-length` | **v1.19.28** | RN v1.19.28 “1f80d91 feat: support session-table and session-length for xhttp client”；`[src]` v1.19.27 无、v1.19.28 有 |
| `network: mekya`（vmess） | **v1.19.28** | RN v1.19.28 “e10a1a7 feat: support mekya for vmess” |
| **vmess 的 `mkcp` 支持本身也是 v1.19.28 新增** | **v1.19.28** | RN v1.19.28 “a198581 feat: support mkcp for vmess”（与上一行同一 release） |
| `ws-opts` / `http-opts` / `h2-opts` / `grpc-opts` / `network: http` | 长期存在，v1.19.32 仍有效 | `[src] v1.19.32 vmess.go:79-82`、`vless.go:226` |
| `network: splithttp` | **从未存在** | 全历史 `git log --all -S'splithttp'` 无提交；`[doc]` 全语言 0 命中 |

> ⚠️ **v1.19.22 内部的自我否定**：RN v1.19.22 还含 “7fdc122 fix: remove incomplete xhttp config options (#2648)”，**被移除的选项清单未被枚举** → 见 §8。

---

## 3. TLS / Reality / ECH

### 3.1 字段命名在不同 type 间**不一致**（最高频踩坑点）

`[src]`（`grep 'proxy:"sni' / 'proxy:"servername'`）：

| 字段 | 使用该名字的 type | 证据 |
|---|---|---|
| `sni` | `trojan`, `hysteria`, `hysteria2`, `tuic`, `anytls`, `http`, `gost-relay`, `shadowquic`, `trusttunnel`, `masque`(自身), `hysteria2-realm` | `trojan.go:52`, `hysteria.go:116`, `hysteria2.go:53`, `tuic.go:65`, `anytls.go:34`, `http.go:36`, `gost_relay.go:28`, `shadowquic.go:36`, `trusttunnel.go:28`, `masque.go:63` |
| `servername` | **只有 `vmess` / `vless`** | `vless.go:89`, `vmess.go:70` |

**后果**：
- 在 vless/vmess 上写 `sni: xxx` → **未知键，静默丢弃**，SNI 回退为 `server`。
- 在 trojan/hysteria2/tuic/anytls 上写 `servername: xxx` → **未知键，静默丢弃**。
- `[doc]` TLS 页用 “`sni`/`servername`” 合并描述（“referred to as `servername` in VMess/VLESS”），文档读起来像同义词，**源码里是互斥的两个键**。

### 3.2 TLS 字段表

| 字段 | 谁真正读取 | URI 表达 | 版本门槛 | 证据 |
|---|---|---|---|---|
| `tls` | 仅 `vmess`/`vless`/`http`/`socks5`/`gost-relay`/`sudoku`(httpmask) 有该字段 | `security=tls|reality|xtls…` → `tls: true` | — | `[src] grep -rn 'proxy:"tls' adapter/outbound/*.go`；**trojan 结构体里根本没有 `tls` 字段**（trojan 恒用 TLS） |
| `servername` / `sni` | 见 §3.1 | `sni=` | — | `[src]` 同上 |
| `alpn` | 全部 TLS 类 type | `alpn=h2,http/1.1`（逗号切分） | — | `[src] common/convert/v.go:33-35,145-147` |
| `skip-cert-verify` | 全部 TLS 类 type | `insecure=1`/`allowInsecure=1` | — | `[src]` 各构造器 |
| `name-cert-verify` | 全部 TLS 类 type | ❌ **分享 URI 无法表达** | — | `[src] component/ca/config.go:118-126`；`[doc]` tls 页 “Only modifies the certificate's DNSName verification target, without altering the SNI.” |
| `fingerprint`（证书 SHA-256 固定） | 全部 TLS 类 type | `pcs=` (vless/vmess/trojan), `pinSHA256` (hysteria2), `hpkp` (anytls) | **v1.19.20**：中间/根证书指纹时**额外要求 SNI/servername 匹配** | `[src] component/ca/fingerprint.go`；`[doc]` tls 页 warning |
| `certificate` / `private-key`（mTLS） | 全部 TLS 类 type | ❌ 无法表达 | — | `[src] component/ca/config.go:128-140` |
| `client-fingerprint`（uTLS） | vmess/vless/trojan/anytls（+ ss 插件、snell 间接使用） | `fp=chrome`（**缺省时订阅解析强制注入 `chrome`**） | — | `[src] component/tls/utls.go:42-60`；`[doc]` tls 页 “applicable only to VMess/VLESS/Trojan/AnyTLS” |
| `reality-opts{public-key, short-id, support-x25519mlkem768}` | vmess/vless/trojan（**anytls 没有**） | `pbk=`/`sid=`/`support-x25519mlkem768=` | — | `[src] adapter/outbound/reality.go:13-46`；`anytls.go` 无 Reality 字段 |
| `ech-opts{enable, config, query-server-name}` | vmess/vless/trojan/anytls/hysteria/hysteria2/tuic/trusttunnel… | ❌ **分享 URI 无法表达** | — | `[src] adapter/outbound/ech.go:12-35` |
| `shadow-tls-opts{version, password}` | vmess/vless/trojan/anytls | ❌ 无法表达 | — | `[src] adapter/outbound/shadowtls.go:5-8` |
| `restls-opts{password, version-hint, restls-script}` | vmess/vless/trojan/anytls | ❌ 无法表达 | — | `[src] adapter/outbound/restls.go:5-9` |
| `jls-opts{username, password}` | vmess/vless/trojan/anytls | ❌ 无法表达 | — | `[src] adapter/outbound/jls.go:5-8` |
| `tlsmirror-opts{...}` | **只有 `vmess`** 有该字段 | ❌ 无法表达 | — | `[src] grep -rn 'proxy:"tlsmirror-opts' adapter/outbound/` → 仅 `vmess.go:76`；`[doc]` tls 页 note “Currently, only VMess supports enabling tlsmirror.” |

### 3.3 Reality 的真实生效条件（三层不一致）

1. **必须有 `reality-opts.public-key`（非空）**才构造 Reality 配置；`short-id` 单独写没有用。
   `[src] adapter/outbound/reality.go:20-23` → `if o.PublicKey != "" { ... } return nil, nil`（**public-key 为空 = 静默不启用 Reality，无任何提示**）。
2. **必须有 `client-fingerprint`**，否则**连接时**报错：`[src] transport/vmess/tls.go:130-132` → `errors.New("REALITY is based on uTLS, please set a client-fingerprint")`。注意这是**运行期错误**，`mihomo -t` 检测不到。
3. **只在非 ws 的 TLS 路径接线**：`ws` 分支构造的 `vmess.TLSConfig` **不含 `Reality` 字段**（见 §5.A5）→ `network: ws` + `reality-opts` = **Reality 静默失效**。
4. `short-id` 有校验（硬错误）：`[src] reality.go:32-38` → 超 8 字节解码长度即 `invalid REALITY short id`。
5. `public-key` 有校验（硬错误）：必须是 32 字节 base64url raw，否则 `invalid REALITY public key`（`reality.go:26-28`）。

### 3.4 ECH 的真实生效条件

- `[src] adapter/outbound/ech.go:19-21`：`if !o.Enable { return nil, nil }` → **`ech-opts.enable` 不为 true 时，`config`/`query-server-name` 全部静默丢弃**。
- `[src] adapter/outbound/vless.go:306-329`（`streamTLSConn`）：ECH 只在 `if v.option.TLS { ... }` 内被使用 → **`tls: false` + `ech-opts.enable: true` = ECH 静默失效**，无错误。
- `[src] transport/vmess/tls.go:44-78`：`StreamTLSConn` 按 ShadowTLS → Restls → JLS → TLSMirror 顺序**提前 return**；这些分支**不传递 ECH** → **ECH 与 shadow-tls/restls/jls 同用时静默失效**。（ShadowTLS+Reality 之类的组合会被 §3.5 的互斥检查拦住，但 ECH 不在互斥名单里。）
- `[src] component/ech/ech.go:15-31`：ECH 会把 `MinVersion`/`MaxVersion` 抬到 TLS 1.3（仅当原本非 0）。

### 3.5 会真正报错的 TLS 组合（少数严格校验）

- **安全模式互斥**：`ShadowTLS` / `Restls` / `JLS` / `REALITY`（vmess 还含 `TLSMirror`）同时出现 > 1 → 硬错误 `security modes are mutually exclusive: ...`。
  `[src] adapter/outbound/vless.go:535-551`、`trojan.go:328-345`、`vmess.go:534-565`。
- **安全模式必须 TLS**：`securityMode != "" && !option.TLS` → `"%s requires TLS"`（`vless.go:552-555`）。
- **vmess**：`mkcp`/`kcp` + `ShadowTLS`/`Restls`/`JLS` → `"%s only supports TCP transports"`（`vmess.go:565-571`）。
- **xhttp HTTP/3**：`!option.TLS` → `xhttp HTTP/3 requires TLS`；有 `securityMode` → `xhttp HTTP/3 does not support %s`（`vless.go:693-698`）。

### 3.6 TLS / Reality / ECH 版本门槛（`[meta]` release notes）

| 能力 | 最早版本 | 证据 |
|---|---|---|
| `client-fingerprint`（uTLS） | **v1.14.2** | RN v1.14.2 “feat: Add utls for modifying client's fingerprint.” |
| `reality-opts` | **v1.14.3** | RN v1.14.3 “feat: Support REALITY protocol by @H1JK”（同页头部注明 REALITY 为实验性支持） |
| `reality-opts.support-x25519mlkem768` | **v1.19.9** | RN v1.19.9 “5cf0f18 feat: reality add support-x25519mlkem768, it only works with new version server” |
| SHARE-URI 里转换 Reality ML-KEM 参数 | **v1.19.31** | RN v1.19.31 “518c703 chore: convert support REALITY ML-KEM option (#3199)” |
| `ech-opts`（anytls/ss/trojan/vmess/vless） | **v1.19.9** | RN v1.19.9 “c6d7ef8 feat: add ech-opts for anytls/shadowsocks/trojan/vmess/vless outbound” |
| `ech-opts`（hysteria/hysteria2/tuic） | **v1.19.9** | RN v1.19.9 “dc958e6 feat: add ech-opts for hysteria/hysteria2/tuic outbound” |
| `ech-opts.query-server-name` | **v1.19.20** | RN v1.19.20 “3c526ae feat: add query-server-name for ech-opts” |
| `name-cert-verify` | **v1.19.29** | RN v1.19.29 “5677fd3 feat: add name-cert-verify to support separate certificate verification name” |
| `jls-opts` | **v1.19.29** | RN v1.19.29 “611a448 feat: support jls for vmess/vless/trojan outbound and listener”（+ ss/anytls/snell 同 release） |
| `restls-opts`（统一字段名） | **v1.19.29** | RN v1.19.29 “769ea6f feat: support restls for vmess/vless/trojan outbound and listener”；更早只作为 ss 插件：RN v1.14.3 “feat: Support Restls-V1 in Clash.Meta (#441)” |
| `shadow-tls-opts`（统一字段名） | **v1.19.29** | RN v1.19.29 “c015694 feat: support shadowtls for vmess/vless/trojan outbound and listener”；ss 插件形式在 v1.18.0 已存在；inbound 侧 v1.19.6 |
| `tlsmirror-opts`（**仅 vmess**） | **v1.19.28** | RN v1.19.28 “2f510e8 feat: support tlsmirror for vmess” |
| VLESS `encryption`（`mlkem768x25519plus…`） | **v1.19.13** | RN v1.19.13 “1b0c72b feat: support vless encryption by @wwqgtxx” |
| VLESS XTLS **Vision**（`xtls-rprx-vision`） | **v1.14.3** | RN v1.14.3 “feat: Support VLESS XTLS Vision (#406) by @H1JK” |
| legacy XTLS flow（非 Vision） | **v1.15.1 移除** | RN v1.15.1 “chore: Remove legacy XTLS support (#645) by @hellojack” |

> **兼容性含义**：`name-cert-verify` / `jls-opts` / `restls-opts` / `shadow-tls-opts` 四个字段在 **v1.19.29 之前的内核上会被当作未知键静默丢弃**（§5.A1）—— 也就是说，一个“用了 shadow-tls-opts 的 vmess 节点”在 v1.19.28 上**不会报错，只会裸奔**。

---

## 4. 高级能力

### 4.1 `flow`（仅 vless）

- 字段：`[src] adapter/outbound/vless.go:64` → `Flow string \`proxy:"flow,omitempty"\``
- 逻辑：`[src] adapter/outbound/vless.go:464-472`

```go
if len(option.Flow) >= 16 {
    option.Flow = option.Flow[:16]
    if option.Flow != vless.XRV {          // XRV = "xtls-rprx-vision"
        return nil, fmt.Errorf("unsupported xtls flow type: %s", option.Flow)
    }
    addons = &vless.Addons{Flow: option.Flow}
}
```

- `[src] transport/vless/vless.go:15` → `XRV = "xtls-rprx-vision"`（16 字符）
- **`len(flow) < 16` 时既不截断也不校验 → 静默忽略**。所以 `flow: xtls-rprx-direct`（16 字符，已废弃的 Xray flow）会**报错**，而 `flow: vision`、`flow: abc` 会**静默通过且完全无效**。
- `flow: xtls-rprx-vision-udp443` → 截断为 16 字符 = `xtls-rprx-vision` → 接受。`[doc]` 证实这是有意为之：“Meta's `xtls-*` flow control is effectively equivalent to `xtls-*-udp443` in Xray-core.”（<https://wiki.metacubex.one/en/config/proxies/vless/>）
- 运行时：`[src] transport/vless/conn.go:168` → `switch client.Addons.Flow`。

### 4.2 `fingerprint` / `client-fingerprint`

- `client-fingerprint` 支持集（源码枚举）：`chrome`, `firefox`, `safari`, `ios`, `android`, `edge`, `360`, `qq`, `random`，另有历史项 `chrome120`, `firefox120`, `safari16`, `chrome_psk`, `chrome_psk_shuffle`, `chrome_padding_psk_shuffle`, `chrome_pq`, `chrome_pq_psk`, `randomized`。
  `[src] component/tls/utls.go:78-101`；源码注释 “// deprecated fingerprints should not be used”（`utls.go:94`）。
- 查找是**大小写敏感的精确 map 查找**（`utls.go:53`），**不做 `ToLower`**：`[doc]` 英文页写 `iOS`（<https://wiki.metacubex.one/en/config/proxies/tls/>），而源码 key 是 `ios` → **文档给的 `iOS` 写法会落到未知分支**（仅 `log.Warnln("wrong clientFingerprint:%s")`，然后回退到 Go 原生 TLS）。
- 未知值回退行为：`[src] utls.go:54-59` → `log.Warnln(...)` + `return UClientHelloID{}, false` → 调用方走 `tls.Client`。**回退只在日志里可见，配置测试与 API 都不会显示异常**。
- `fingerprint`（另一个字段）是**证书 SHA-256 固定**，不是 uTLS：`[src] component/ca/config.go:101-116` → 命中时 `InsecureSkipVerify = true` 并改用 `VerifyConnection`。

### 4.3 `mux` / `smux`

- **`smux`（每个 proxy 的块）**：`[src] adapter/parser.go:234-247`

```go
if muxMapping, muxExist := mapping["smux"].(map[string]any); muxExist {
    muxOption := &outbound.SingMuxOption{}
    err = decoder.Decode(muxMapping, muxOption)
    ...
    if muxOption.Enabled {            // ← 必须显式为 true
        proxy, err = outbound.NewSingMux(*muxOption, proxy)
    }
}
```

  → **`smux` 块存在但 `enabled` 不为 true（含缺失、含 `enabled: false`）= 静默不做多路复用**，没有任何错误或警告。`[doc]` 的示例普遍写 `smux: enabled: false`。
- 字段全集：`enabled, protocol, max-connections, min-streams, max-streams, padding, statistic, only-tcp, brutal-opts{enabled, up, down}`（`[src] adapter/outbound/singmux.go:24-40`）。
- `[doc]` 约束（写得很硬但源码不校验）：`max-connections` / `min-streams` 与 `max-streams` 冲突；“sing-mux, only for protocols using TCP transport.”；`only-tcp: true` 时 UDP 走节点原生 UDP（<https://wiki.metacubex.one/en/config/proxies/>）。**文档未说明服务端不支持 smux 时的行为** → 见 §8。
- 运行时 UDP 语义：`[src] adapter/outbound/singmux.go:44-62`（`ListenPacketContext` / `SupportUDP` / `SupportUOT` 在 `only-tcp` 时透传底层）。
- **legacy 全局 `mux:` 块**：`RawConfig` 结构中**根本没有 `mux` 字段**（`[src] config/config.go:403-471`，逐字段核对），全仓库 `grep 'yaml:"mux'` 只命中 **inbound listener 的 `mux-option`**（`listener/config/*.go`）。→ 顶层写 `mux:` 是**未知键，静默丢弃、无日志**。详见 §5.A2 / §6.1。

### 4.4 `udp` / `xudp` / `packet-addr` / `packet-encoding`

- `udp` 是 `Base.udp`，`[src] adapter/outbound/base.go:105-108` → `SupportUDP() { return b.udp }`。
- **`udp: false` 的运行时后果不是报错**：`[src] tunnel/tunnel.go:684-687`

```go
if metadata.NetWork == C.UDP && !adapter.SupportUDP() {
    log.Debugln("%s UDP is not supported", adapter.Name())
    continue        // ← 跳过该 proxy，继续匹配后面的规则
}
```

  → **UDP 请求会静默跳到下一条匹配规则**（可能是别的节点或 DIRECT），日志仅在 `debug` 级别。DNS 出口路径则是硬错误：`[src] tunnel/dns_dialer.go:112-115` → `proxy adapter [%s] UDP is not supported`。
- **`udp` 被硬编码为 true 的 type**（写 `udp: false` 完全无效）：`hysteria`(`hysteria.go:250`)、`hysteria2`(`hysteria2.go:137`)、`tuic`(`tuic.go:247`)、`shadowquic`(`shadowquic.go:166`)、`sudoku`(`sudoku.go:236`)、`openvpn`(`openvpn.go:135`)。`[doc]` 侧对应说明：“This option is enabled by default for UDP-based protocols such as `TUIC`, and for the `direct` and `dns` types.”（<https://wiki.metacubex.one/en/config/proxies/>）
- `xudp` / `packet-addr` / `packet-encoding` 三者互斥关系的源码真相：
  - `[src] adapter/outbound/vless.go:471-483`

```go
switch option.PacketEncoding {
case "packetaddr", "packet":
    option.PacketAddr = true
    option.XUDP = false
default:                       // ← "xudp"、空、以及任何未知值都走这里
    if !option.PacketAddr { option.XUDP = true }
}
if option.XUDP { option.PacketAddr = false }
```

  → **`packet-encoding` 的未知值静默等同 `xudp`**；且**只要没显式写 `packet-addr: true`，`xudp` 就会被默认打开**（`vless` 与 `vmess` 均是：`vmess.go:489-497`）。
- 协议差异：vless 的 `xudp` 会走 sing-vmess XUDP 连接（`vless.go:387-400`），`packet-addr` 走 packetaddr（`vless.go:401-409`）。

### 4.5 `dialer` / `dialer-proxy` / `tfo` / `mptcp` / `interface-name` / `routing-mark` / `ip-version`

`[src] adapter/outbound/base.go:192-199`（`BasicOption`，所有 type 都有）：

| 字段 | 校验情况 | 运行时 | 证据 |
|---|---|---|---|
| `dialer-proxy` | **有校验**：引用的 proxy 必须存在，且检测环 | 通过 `proxydialer.NewByName` 建链 | `[src] config/utils.go:147-176` → `proxy [%s] dialer-proxy [%s] not found` / `has circular dialer-proxy dependency`；`[src] base.go:210-218` |
| `interface-name` | **无校验**（字符串原样进 socket 绑定） | 绑定失败在拨号期体现 | `[src] base.go:139-141` → `dialer.WithInterface(b.iface)` |
| `routing-mark` | **无校验**（int 原样） | 同上（Linux 有效） | `[src] base.go:143-145` |
| `ip-version` | **未知值静默回退 `dual`，且 `UnmarshalText` 返回 nil error** | 影响 DNS 解析偏好与 racing | `[src] constant/dns.go:93-100`：`if !exist { p = DualStack }; *d = p; return nil` |
| `tfo` | 无校验 | **Windows 上被硬关闭**：`[src] component/dialer/tfo_windows.go:9` → `DisableTFO = true` | `[src] component/dialer/dialer.go:186-187` |
| `mptcp` | 无校验 | 通过 `mptcp.SetNetDialer(dialer, opt.mpTcp)` 设置；内核不支持时在拨号期失败 | `[src] component/dialer/dialer.go:158` |

`DialOptions()` 组装顺序与默认值：`[src] adapter/outbound/base.go:146-172`。

### 4.6 `obfs`（分协议）

| 协议 | 字段 | 校验 | 证据 |
|---|---|---|---|
| `ss` | `plugin` ∈ {`obfs`, `v2ray-plugin`, `gost-plugin`, `shadow-tls`, `restls`, `jls`, `kcptun`} | **无 default 分支 → 未知 plugin 静默无效**（见 §5.A9） | `[src] adapter/outbound/shadowsocks.go:321-495` |
| `ss` | `plugin-opts.mode` | **有校验**：`obfs` 必须 `tls`/`http`；`v2ray-plugin`/`gost-plugin` 必须 `websocket` | `[src] shadowsocks.go:327-330, 336-338, 371-373` |
| `ssr` | `obfs` / `protocol`（`tls1.2_ticket_auth`, `auth_sha1_v4`…） | 未见本地枚举校验 | `[src] adapter/outbound/shadowsocksr.go:33-42`；`[doc]` ssr 页**未给出任何允许值列表** |
| `snell` | `obfs-opts.mode` ∈ {`tls`, `http`, ``, `shadow-tls`, `restls`, `jls`} | **有 default → 硬错误** `snell %s obfs mode error: %s` | `[src] adapter/outbound/snell.go:178-233` |
| `hysteria`(v1) | `obfs`（任意字符串，作为 key）+ `obfs-protocol`（别名，覆盖 `protocol`） | **无校验**，任意字节都接受 | `[src] hysteria.go:192-194, 221-224` |
| `hysteria2` | `obfs` ∈ {`salamander`, `gecko`} | **有校验 → 硬错误** `unknown obfs type: %s`；且 `obfs` 非空时 `obfs-password` 必填（`missing obfs password`） | `[src] adapter/outbound/hysteria2.go:149-162` |
| `hysteria2` | `obfs-min-packet-size` / `obfs-max-packet-size` | 只在 `gecko` 时被读取 → 配 `salamander` 时**静默无效** | `[src] hysteria2.go:156-159` |

### 4.7 端口跳跃（port hopping）

- `hysteria2`：`ports` 用 `utils.NewUnsignedRanges[uint16]` 解析，**格式错误 = 硬错误**；`hop-interval` 用 `utils.NewUnsignedRange[uint64]`，**格式错误 = 硬错误**；`start < 5s` 时**静默抬到 5s**（`minHopInterval = 5`），`0`/缺省 → `defaultHopInterval = 30`。
  `[src] adapter/outbound/hysteria2.go:29-30, 236-267`。
  **注意**：`hop-interval` 只在 `option.Ports != ""` 的分支内被读取 → **只写 `hop-interval` 不写 `ports` = 静默无效**。
- `hysteria2`：`port == 0 && len(serverPorts) == 0` → 硬错误 `invalid port`（`hysteria2.go:266-268`）。
- `hysteria`(v1)：`ports` + `hop-interval`（`DefaultHopInterval`），`[src] hysteria.go:199-203, 224-226`。
- URI 层：`hysteria2://…:443,8443-9443@host` 由 `common/convert/v.go:379-424`（`splitHysteria2Ports`）拆分出 `port` + `ports`（`[src]`；见 §7.4）。

### 4.8 `smux` 之外的其它 special features

| 特性 | 位置 | 备注 | 证据 |
|---|---|---|---|
| `ss-opts`（trojan-go 的 SS AEAD 包装） | `trojan` | `enabled`+`method`+`password`；`method` 空默认 `AES-128-GCM`；未知 method 硬错误 | `[src] trojan.go:352-364`、`TrojanSSOption`（`trojan.go:71-75`） |
| `realm-opts`（Hysteria2 Realm） | `hysteria2` | **必须 `enable: true`** 才生效 | `[src] hysteria2.go:270`；`[doc]` hysteria2 页 “enable: true # Must be turned on manually” |
| `client-metadata`（anytls） | `anytls` | **v1.19.30 起默认不再发送** | `[doc]` anytls 页 warning；`[src] anytls.go` 有 `ClientMetadata` 字段 |
| `AnyTLS + Reality` | — | **官方明确不支持且不会支持** | `[doc]` anytls 页 `!!! tip`；`[src] anytls.go` 结构体里确实没有 Reality 字段 |
| `udp-over-tcp` / `udp-over-tcp-version` | `ss` | version 非 `1`/`2`/`0` → 硬错误 `unknown udp over tcp protocol version` | `[src] shadowsocks.go:487-497` |
| `udp-over-stream` / `udp-over-stream-version` | `tuic`, `shadowquic` | 同上，非 `1`/`2`/`0` → 硬错误 | `[src] tuic.go:233-239` |
| `kcptun`（作为 ss plugin） | `ss` | 开启时**强制** `option.UDPOverTCP = true` | `[src] shadowsocks.go:484` |
| `httpmask`（sudoku 的 HTTP 伪装） | `sudoku` | `mode` 校验在 `sudoku.go:268-270`；`auto` 与 `multiplex` 有联动 | `[src] adapter/outbound/sudoku.go:264-300` |
| `ip-stack`（wg/masque/zerotier/openvpn） | — | `gvisor` 需要 `-tags with_gvisor` 编译 | `[doc]` wg/masque 页 |
| `amnezia-wg-option` | `wireguard` | 字段面极大；`j1/j2/j3/itime` 仅 AmneziaWG v1.5 | `[src] adapter/outbound/wireguard.go:95-130`；`[doc]` wg 页注释 |
| `trusttunnel.health-check` / `quic` | `trusttunnel` | — | `[src] adapter/outbound/trusttunnel.go:23-45` |

### 4.9 其它能力的版本门槛（`[meta]` release notes + `[src]` 逐 tag 比对）

| 能力 | 最早版本 | 证据 |
|---|---|---|
| per-proxy `smux:` 块（sing-mux） | **v1.14.4** | RN v1.14.4 “feat: add proxy and sing-based listener support sing-mux”；`[src]` v1.14.3 `parser.go` 无 `mapping["smux"]`，v1.14.4 有 |
| `smux.statistic` / `smux.only-tcp` | **v1.14.4** | RN v1.14.4 “feat: add statistic and only-tcp options for smux by @wwqgtxx” |
| `smux.brutal-opts`（TCP Brutal） | **v1.17.0** | RN v1.17.0 “feat: Add outbound sing-mux tcp-brutal support by @H1JK” |
| `dialer-proxy`（对所有 outbound） | **v1.14.4** | RN v1.14.4 “feat: support dialer-proxy config for all outbound” |
| `tfo`（outbound） | **v1.14.3** | RN v1.14.3 “chore: support TFO for outbounds”（listener 侧 v1.13.1） |
| `mptcp`（所有 proxy）+ `inbound-mptcp` | **v1.15.1** | RN v1.15.1 “feat: add mptcp for all proxy” / “feat: add inbound-mptcp for listeners” |
| `ip-version` | **v1.13.0**（v1.13.1 补文档） | RN v1.13.1 “Add ip-version param for proxy, wiki by @Skyxim” |
| `interface-name` / `routing-mark`（节点级） | **pre-v1.14** | git 首次出现打标 v0.18.0 / v1.8.0；v1.19.32 仍存在（`base.go`） |
| ss 2022 ciphers（`2022-blake3-*`） | **v1.12.0** | RN v1.12.0 “Shadowsocks-2022加密方式支持” |
| ss `udp-over-tcp`（UOT） | **v1.12.0** | RN v1.12.0 “Shadowsocks 支持UDP over TCP(Xray-core v1.5.7)”；RN v1.14.5 “chore: switch ss uot default back to version 1” |
| vmess `packet-addr` | **v1.12.0** | commit d8dc44e78 “Refactor: vmess” |
| vmess `packet-encoding` + `xudp` | **v1.13.2** | RN v1.13.2 “chore: add xudp and packet-encoding support for vmess by @wwqgtxx” |
| vless `packet-addr` / `xudp` | **v1.14.1**；**默认开启在 v1.14.2** | RN v1.14.1 “Feat: VLESS support packet encodings by @H1JK”；RN v1.14.2 “adjust: VLESS enable XUDP by default”；`[src] v1.19.32 vless.go:478-481` |
| hysteria2 `ports` + `hop-interval` | **v1.18.2** | RN v1.18.2 “feedc9e feat: implement port hopping (#1064) by @keakon”；`[src]` v1.18.1 无、v1.18.2 有 |
| hysteria2 `hop-interval` **区间格式**（`int` → `string`，如 `"15-30"`） | **v1.19.24** | RN v1.19.24 “80072eb feat: support range format for hysteria2 hop-interval” |
| hysteria2 `obfs`（salamander）+ `obfs-password` | **v1.16.0** | `[src]` v1.16.0 `hysteria2.go` 已有 `Obfs`/`ObfsPassword` |
| hysteria2 **gecko** obfs + `obfs-min/max-packet-size` | **v1.19.26** | RN v1.19.26 “f30a64f feat: support hysteria2 gecko obfs” |
| hysteria2 `realm-opts` | **v1.19.25** | RN v1.19.25 “98aa7e6 feat: support realm-opts for hysteria2 outbound and listener” |
| `bbr-profile`（hy2/tuic/trusttunnel/masque） | **v1.19.24** | RN v1.19.24 “db25932 feat: support bbr-profile for …” |
| `alterId` | 长期存在，**v1.19.32 仍被接受** | `[src] v1.19.32 vmess.go:59` |

> **兼容性含义**：`smux` / `dialer-proxy` / `tfo` / `mptcp` / `ip-version` 这类“高级能力”在 **v1.14 之前的内核上全部是未知键 → 静默丢弃**。若目标用户群包含老内核，这些字段必须单独做版本判定。

---

## 5. 静默忽略 / 静默降级清单

> 本节是本文件的核心。判据：**「配置被接受（`mihomo -t` 成功）但运行时该字段不起作用/按别的语义起作用，且没有 error 级输出」**。
> 所有条目均为 `[src]`（源码可复核），有 `[doc]` 佐证的额外标注。**无 `[test]`**：以下行为来自源码路径分析，尚未实机验证。

### 5.A 结构性根因：未知键永不报错

| # | 字段/位置 | 现象 | 后果 | 证据 |
|---|---|---|---|---|
| A1 | **任意 proxy 内的未知键** | `structure` 解码器把未匹配的输入键收集进 `dataValKeysUnused`，**该集合只在结构体带 `remain` tag 时才消费**；proxy option 结构体无一使用 `remain`，也**没有 `ErrorUnused` 开关** → 未知键被静默丢弃 | 拼错/写错字段名 = 字段消失 | `[src] common/structure/structure.go:403-406`（收集）、`:540`（命中即删）、`:566-585`（仅 `remain` 消费）、`:585-593`（只对**缺失的必填**报错）。`structure.Option` 只有 `TagName/WeaklyTypedInput/KeyReplacer`（`:16-20`），无严格模式 |
| A2 | **顶层 YAML 未知键** | `yaml.Unmarshal(buf, rawCfg)` 未启用 `KnownFields` | 顶层写错键 = 静默丢弃 | `[src] config/config.go:617`（`go.yaml.in/yaml/v3 v3.0.5`，见 `go.mod:63`）；`common/yaml/yaml.go:9` 是对 `yaml.Unmarshal` 的直通包装 |
| A3 | **顶层 `mux:` 块（legacy 全局多路复用）** | `RawConfig` **没有 `mux` 字段**（28 个字段逐一核对） | 顶层 `mux:` 块（含 `enabled`/`protocol`/`padding`/`brutal`）**整体静默失效，连日志都没有**。⚠️ **但「它曾经有效过」这一点无法确证**：字面量 `"mux"` 在 tag v1.6.5 / v1.8.0 / v1.10.0 / v1.12.0 / v1.14.0 / v1.17.0 / v1.18.10 / v1.19.32 的 `config/` 下**均不出现**，`git log -S'"mux"'` 无任何提交，Meta-Docs 也没有全局 `mux` 章节（只有 `smux.*`、inbound `mux-option:`、ss 插件里的 `mux: true`）→ **很可能是从未存在过的 Clash Premium 特性**，见 §8 | `[src] config/config.go:403-471`；`grep -rn 'yaml:"mux' --include=*.go .` 只命中 `listener/config/{hysteria2,shadowquic,shadowsocks,tuic,vless,vmess}.go` 的 inbound `mux-option` |
| A4 | **`global-client-fingerprint`** | 字段还在 `RawConfig`，但只 `log.Errorln` 后继续 | 配置能加载，指纹不生效；**只有 error 日志，不影响 `-t` 通过与否**（该分支在 `parseGeneral` 里，不在 `Unmarshal` 阶段） | `[src] config/config.go:444, 761-763`：`log.Errorln("The \`global-client-fingerprint\` configuration is removed, ...")` |
| A5 | **`vless.ws-headers`** | **声明了但全仓库只出现 1 次（就是声明本身）→ 死字段** | 写了完全无效果 | `[src] adapter/outbound/vless.go:83`；对全部 `adapter/outbound/*.go` 的 `proxy:`/`obfs:` tag 做「Go 字段名在全仓库非测试代码中的引用数 ≤ 1」扫描，**唯一命中就是它** |

### 5.B `network` 与 transport

| # | 字段/位置 | 现象 | 后果 | 证据 |
|---|---|---|---|---|
| B1 | **`network` = 任意未知值** | `switch` 落 `default: // default tcp network`，无 log | **静默按 TCP + TLS**，与服务端完全对不上（表现为连不上或握手失败，但配置层无任何提示） | `[src] vless.go:156-262`、`vmess.go:175-291`、`trojan.go:79-190`；`[doc]` 三个协议页明写 “If unset or set to another value, TCP is used.” |
| B2 | **`network: httpupgrade`** | 订阅解析层会产出该值（`common/convert/v.go:110,127`、`converter.go:356,375`），但 `adapter/` 下**没有任何 `httpupgrade` 分支** | 分享链接 `type=httpupgrade` 的节点 → `network: httpupgrade` + `ws-opts` → **静默按 TCP**，`ws-opts`（含 `v2ray-http-upgrade-fast-open`）全废 | `[src]` `grep -rn '"httpupgrade"' --include=*.go .`（非测试）仅 4 处，全在 `common/convert/` |
| B3 | **`network: splithttp`**（Xray 旧名） | 字符串在 v1.19.32 全仓库 **0 命中**；订阅解析把 `type=splithttp` 原样写进 `network` | **静默按 TCP**。mihomo 只认 `xhttp`；`splithttp` 不会被自动改写成 `xhttp` | `[src]` 全仓库 grep 0 命中；`[src] common/convert/v.go:104-109`（`network` 原样赋值） |
| B4 | **`network: h2` / `http` / `xhttp` / `mkcp` / `mekya` 用在错误的 type 上** | 见 §2.3 矩阵；不匹配即落 `default` | 静默按 TCP | `[src]` 同上 |
| B5 | **`network: mkcp` + `shadow-tls-opts`/`restls-opts`/`jls-opts`（vmess）** | 这是**会报错**的少数情形 | 硬错误 `%s only supports TCP transports` | `[src] vmess.go:565-571` |
| B6 | **`network: h2` 未给 `h2-opts.host`** | 静默注入 `www.example.com` | 配置被默默改写 | `[src] vmess.go:572-578`、`vless.go:559-564` |
| B7 | **`network: ws` + `tls: false` + 无 Host 头** | 静默注入随机 Host / User-Agent | 配置被默默改写 | `[src] vless.go:190-196` |
| B8 | **`xhttp-opts.mode` 未知值（对照组）** | **会报错**：`xhttp mode %s is not implemented yet`，在 `NewVless` 构造期抛出 | `mihomo -t` **失败** —— 这是「transport 子字段反而被严格校验」的反例，可用于区分「哪些字段值得信任」 | `[src] transport/xhttp/config.go:70-89`、`client.go:246-252`、`adapter/outbound/vless.go:911-914` |

### 5.C TLS / Reality / ECH / fingerprint

| # | 字段/位置 | 现象 | 后果 | 证据 |
|---|---|---|---|---|
| C1 | **`reality-opts` 无 `public-key`（或为空串）** | `Parse()` 直接 `return nil, nil` | Reality **完全不启用**，`short-id` 白写 | `[src] adapter/outbound/reality.go:20-23, 44-46` |
| C2 | **`reality-opts` + `network: ws`** | ws 分支构造的 `TLSConfig` **不含 `Reality`**（也不含 `ECH`） | Reality 静默失效（且因为走的是 `ca.GetTLSConfig` 普通 TLS，也不会触发 §5.C3 的 fp 报错） | `[src]` vless：ws 分支 `vless.go:190-224` 无 `Reality:`，`streamTLSConn` `vless.go:306-329` 有 → `grep -n 'Reality:' adapter/outbound/vless.go` 只命中 `:322`（streamTLSConn）、`:598`（grpc）、`:687`（xhttp h3）、`:850/:878`（download-settings）。vmess：ws 分支 `vmess.go:205-244` 的三个子分支均无 `Reality:`，`streamTLSConn` `vmess.go:346-370` 有。trojan：ws 分支 `trojan.go:120-140` 无，`streamTLSConn` 等价路径 `trojan.go:160-175` 有。**精确例外**：vmess 在 ws 且 `tlsmirror-opts.primary-key != ""` 时会改走 `v.streamTLSConn(ctx, c, false)`（`vmess.go:222-223`），该路径**会**带上 Reality/TLSMirror —— 即「ws + tlsmirror + reality」这一组合下 Reality 反而是生效的 |
| C3 | **`reality-opts` 无 `client-fingerprint`** | **连接时**硬错误 `REALITY is based on uTLS, please set a client-fingerprint` | `-t` 通过、运行失败；错误信息指向 fp 而不是 Reality 配置缺失 | `[src] transport/vmess/tls.go:130-132` |
| C4 | **`client-fingerprint` 未知值** | `log.Warnln("wrong clientFingerprint:%s")` + 回退 Go 原生 TLS（非 uTLS） | **TLS 指纹伪装失效**；若同时有 Reality 则升级为 C3 的硬错误 | `[src] component/tls/utls.go:42-60` |
| C5 | **`client-fingerprint: iOS`（文档写法）** | map key 是 `ios`，查找大小写敏感 | 文档推荐值直接落到 C4 分支 | `[src] utls.go:53, 82` vs `[doc]` tls 页 “Options: `chrome`, …, `iOS`, …” |
| C6 | **`ech-opts` 但 `enable` 非 true** | `if !o.Enable { return nil, nil }` | `config`/`query-server-name` 静默丢弃 | `[src] adapter/outbound/ech.go:19-21` |
| C7 | **`ech-opts.enable: true` + `tls: false`（vless/vmess）** | ECH 只在 `if option.TLS { ... }` 内被装配 | ECH **静默失效**，无任何报错 | `[src] vless.go:306-329`、`vmess.go:340-370` |
| C8 | **`ech-opts` + `shadow-tls-opts`/`restls-opts`/`jls-opts`** | `StreamTLSConn` 在这些分支提前 `return`，**不传 ECH** | ECH 静默失效（互斥检查不覆盖 ECH） | `[src] transport/vmess/tls.go:44-100` |
| C9 | **`servername` 写在 trojan/hysteria2/tuic/anytls 上** | 这些 type 只有 `sni` 字段 | SNI 静默回退为 `server` | `[src] trojan.go:52`、`hysteria2.go:53`、`tuic.go:65`、`anytls.go:34` |
| C10 | **`sni` 写在 vmess/vless 上** | 这两个 type 只有 `servername` 字段 | SNI 静默回退为 `server` | `[src] vless.go:89`、`vmess.go:70` |
| C11 | **`tls: false` 写在 trojan 上** | `TrojanOption` **没有 `tls` 字段** | 未知键被丢弃；trojan **仍然强制 TLS** | `[src] adapter/outbound/trojan.go:45-70`（字段表内无 `tls`） |
| C12 | **`reality-opts` 写在 anytls 上** | `AnyTLSOption` 无 Reality 字段 | 静默丢弃（官方也声明永不支持 AnyTLS+Reality） | `[src] anytls.go:27-49`；`[doc]` anytls 页 `!!! tip` |
| C13 | **`tlsmirror-opts` 写在 vless/trojan 上** | 只有 `vmess` 声明了该字段 | 静默丢弃 | `[src] grep -rn 'proxy:"tlsmirror-opts' adapter/outbound/` → 仅 `vmess.go:76`；`[doc]` “Currently, only VMess supports enabling tlsmirror.” |
| C14 | **`fingerprint` 写成 PEM 里的公钥指纹（HPKP）** | 该字段是**整证书 SHA-256**；不匹配时 `VerifyConnection` 失败 | 连接失败，且被误解为“证书固定生效” | `[doc]` tls 页 warning 第 3 条；`[src] component/ca/fingerprint.go:13-58` |

### 5.D 能力开关与默认值

| # | 字段/位置 | 现象 | 后果 | 证据 |
|---|---|---|---|---|
| D1 | **`smux` 无 `enabled: true`** | `if muxOption.Enabled` 才包装 | 多路复用静默不启用 | `[src] adapter/parser.go:234-247` |
| D2 | **`flow` 长度 < 16** | 既不截断也不校验（§4.1） | flow 静默无效；`network: tcp` 下等于裸 VLESS | `[src] vless.go:464-472` |
| D3 | **`udp: false` 写在 hysteria/hysteria2/tuic/shadowquic/sudoku/openvpn 上** | 构造器硬编码 `UDP: true` | 该字段**完全无效**，UDP 仍然走节点 | `[src] hysteria.go:250`、`hysteria2.go:137`、`tuic.go:247`、`shadowquic.go:166`、`sudoku.go:236`、`openvpn.go:135` |
| D4 | **`udp: false` 写在其它 type 上** | 规则引擎 `continue` 跳过该节点 | **UDP 请求静默改走后续匹配规则**（可能是另一个节点或 DIRECT），仅 debug 日志 | `[src] tunnel/tunnel.go:684-687` |
| D5 | **`packet-encoding` 未知值** | `default:` 分支 → 非 `packet-addr` 时置 `xudp = true` | 未知值静默等于 `xudp` | `[src] vless.go:471-483`、`vmess.go:489-497` |
| D6 | **`packet-encoding` 缺省** | 同上 default 分支 | **默认开启 xudp**（除非显式 `packet-addr: true`） | `[src]` 同上 |
| D7 | **`ip-version` 未知值** | `UnmarshalText` 未命中即 `DualStack` 且 `return nil` | 静默回退 `dual`，**无 error** | `[src] constant/dns.go:93-100` |
| D8 | **`snell.version: 5`** | 代码注释 “Snell v5 servers are backward-compatible with v4 clients.” 后**直接改写为 4** | v5 被静默降级为 v4；**无任何日志** | `[src] adapter/outbound/snell.go:248-251` |
| D9 | **`snell` 不写 `version`** | `DefaultSnellVersion = Version1` | 默认 v1；v1 不支持 UDP，`udp: true` 才会硬错误（`snell version %d not support UDP`） | `[src] transport/snell/snell.go:23`；`snell.go:245-247, 253-261` |
| D10 | **`tuic.udp-relay-mode` 非 `quic`** | `if option.UdpRelayMode != "quic" { udpRelayMode = tuic.NATIVE }` | 拼错（如 `quicc`）静默变 `native`；文档只列 `native`/`quic` | `[src] adapter/outbound/tuic.go:165-168` |
| D11 | **`hysteria2.hop-interval` 但无 `ports`** | 该字段只在 `option.Ports != ""` 分支内读取 | 端口跳跃参数静默无效 | `[src] hysteria2.go:236-267` |
| D12 | **`hysteria2.obfs-min/max-packet-size` + `obfs: salamander`** | 只在 `gecko` 分支读取 | 静默无效 | `[src] hysteria2.go:153-160` |
| D13 | **`hysteria2.realm-opts` 未显式 `enable: true`** | `if option.RealmOpts.Enable` 才生效 | 其余 realm 字段静默丢弃 | `[src] hysteria2.go:270`；`[doc]` “enable: true # Must be turned on manually” |
| D14 | **`hysteria2.port` 与 `ports` 同时写** | `ports` 优先（文档：“Configuring this enables port jumping, ignoring `port`”） | `port` 被忽略 | `[doc]` hysteria2 页；`[src] hysteria2.go:237-267` |
| D15 | **`openvpn` 的 `tls-auth`/`tls-crypt`/`tls-crypt-v2` 互斥** | 文档声明互斥 | 是否被源码强制 → 未逐一确认，见 §8 | `[doc]` openvpn 页 |

### 5.E 订阅/URI 解析层的静默丢弃

（详见 §7；此处只列「静默」性质）

| # | 位置 | 现象 | 后果 | 证据 |
|---|---|---|---|---|
| E1 | 单行解析失败 | `log.Warnln("error:%s line:%s", ...)` 后 `continue` | **该节点被丢弃**，其余节点照常加载；订阅整体不失败 | `[src] common/convert/converter.go:233-235, 258-260` |
| E2 | 行内没有 `://` | `continue` | 静默跳过 | `[src] converter.go:29-32` |
| E3 | 未知 scheme | `switch scheme` **无 default 分支** | 静默跳过（如 `wireguard://`、`snell://`、`ssh://`、`hysteria://` 之外的各种自造 scheme） | `[src] converter.go:36-750`（case 全集见 §7.1） |
| E4 | 整个订阅 0 个可用节点 | `return nil, fmt.Errorf("convert v2ray subscribe error: format invalid")` | 这是**会报错**的情形 | `[src] converter.go:744-746` |
| E5 | `ss` 的 `plugin` 无 `;` | 只在 `strings.Contains(plugin, ";")` 时才解析 | `plugin=obfs-local`（无参数）→ **plugin 静默丢弃**变成裸 SS | `[src] converter.go:445-471` |
| E6 | `ss` 的 `plugin` 不在 obfs*/v2ray-plugin 之外 | 只处理含 `obfs` 与含 `v2ray-plugin` 两种 | `plugin=shadow-tls;…`、`plugin=kcptun;…`、`plugin=restls;…` → **静默丢弃**，即使 mihomo **内核本身支持**这些 plugin | `[src] converter.go:446-471`（无 else） |
| E7 | `vmess` 的 `network` 原样透传 | `vmess["network"] = network`（只做 `http→h2`、`type=http→http` 两次改写） | `net: "httpupgrade"` → `network: httpupgrade` → **运行期静默按 TCP**（§5.B2） | `[src] converter.go:309-318` |
| E8 | `vless` 的 `network` 原样透传 | 同上（`common/convert/v.go:104-109`） | `type=splithttp`/`type=kcp`/`type=quic` 全部静默按 TCP | `[src] v.go:72-109` |
| E9 | `vless` 的 `packetEncoding` 未知值 | `default: proxy["xudp"] = true` | 未知值静默等于 xudp | `[src] v.go:55-62` |
| E10 | `socks`/`http`/`https` 链接 | `socks["skip-cert-verify"] = true` **无条件硬编码** | 所有 socks/http 分享链接都被强制关闭证书校验 | `[src] converter.go:583-586` |
| E11 | `vless`/`vmess`/`trojan` 的 `security` | `strings.HasSuffix(tls, "tls")` 判定 | `security=xtls` 也匹配（后缀就是 `tls`）→ 静默置 `tls: true` | `[src] v.go:25-27` |

---

## 6. 弃用与移除

> 免责：`[meta]` 只能拿到 v1.19.24 → v1.19.32 的发布时间；**每个字段「在哪一版被弃用/移除」多数无法确证** → 见 §8。下表区分「已确证移除」与「UNKNOWN 版本」。

### 6.1 已确证在 v1.19.32 中不存在/失效

| 旧形式 | 新形式 | 版本 | 后果 | 证据 |
|---|---|---|---|---|
| 顶层全局 `mux:`（`enabled`/`protocol`/`padding`/`brutal`…） | 每个 proxy 的 `smux:` 块（**v1.14.4** 引入） | ⚠️ **无证据表明它曾在 mihomo 中存在过**（不是「移除」，而是「未知键」） | **完全静默失效，无日志**（§5.A3） | `[src] config/config.go:403-471`（`RawConfig` 无 `mux`）；字面量 `"mux"` 在 v1.6.5/v1.8.0/v1.10.0/v1.12.0/v1.14.0/v1.17.0/v1.18.10/v1.19.32 的 `config/` 均不出现；`git log -S'"mux"'` 无提交；全仓库 `yaml:"mux` 只命中 inbound `mux-option` |
| `global-client-fingerprint` | 各 proxy 内的 `client-fingerprint` | 引入 **v1.14.2** → 弃用 **v1.19.19** → **移除 v1.19.27** | v1.19.27+ 写它 = 未知键静默丢弃；v1.19.19–v1.19.26 会打一条 error 日志但配置照常加载（v1.19.32 的 `log.Errorln` 分支即此残留） | `[src] config/config.go:444, 761-763`；`[meta]` RN v1.19.19 “97bce45 chore: deprecated global-client-fingerprint, please set client-fingerprint directly on the proxy instead”；RN v1.19.27 “bd72c65 feat: remove global-client-fingerprint”；`[doc]` general 页 warning |
| 代理组 `type: relay` | `dialer-proxy` | 弃用 **v1.18.6** → **完全移除 v1.19.17** | v1.19.17+ 写 `type: relay` → `unsupport proxy type: relay`（硬错误） | `[src] adapter/parser.go:14-281`（28 个 case 无 relay）；`[meta]` RN v1.18.6 “ad5bc51 chore: deprecated the relay group type”；RN v1.19.17 “The group with relay type … was completely removed, please using dialer-proxy instead” |
| 代理组上的 `interface-name` / `routing-mark` | 节点上的同名字段 | 弃用 **v1.19.2** → **移除 v1.19.6** | v1.19.6+ 写在 proxy-group 上 = 未知键静默丢弃 | `[meta]` RN v1.19.2 “b69e52d chore: deprecated routing-mark and interface-name of the group”、RN v1.19.6 “7e7016b chore: removed routing-mark and interface-name of the group”；`[doc]` proxy-groups 页两条 warning |
| legacy XTLS flow（`xtls-rprx-direct` 等非 Vision 形式） | `xtls-rprx-vision`（**v1.14.3** 引入） | **移除 v1.15.1** | v1.15.1+ 写 16 字符的旧 flow → `unsupported xtls flow type: %s`（硬错误） | `[meta]` RN v1.15.1 “chore: Remove legacy XTLS support (#645)”；RN v1.14.3 “feat: Support VLESS XTLS Vision (#406)”；`[src] vless.go:464-472` |
| ss 插件形式的 `restls` / `shadow-tls` | 统一的 `restls-opts` / `shadow-tls-opts` / `jls-opts` | **v1.19.29** | 旧的 ss-plugin 写法仍可用，但新字段在 v1.19.29 之前的内核上**静默无效** | `[meta]` RN v1.19.29 769ea6f / c015694 / 611a448；`[src] v1.19.32` 两套并存（`shadowsocks.go:396,422` 与各 outbound 的 `*-opts`） |
| `splithttp`（Xray 旧名） | 无（mihomo 从未有过该值；对应能力叫 `xhttp`） | **从未存在** | 写 `network: splithttp` → 静默按 TCP | `[meta]` 全历史 `git log --all -S'splithttp'` 无提交；`[doc]` 全语言 0 命中 |
| `vless.ws-headers` | `vless.ws-opts.headers` | 字段从 v1.14.0 起一直存在（release note 层面「仍有效」） | **但 v1.19.32 源码中它是死字段**（除了声明处没有任何读取点，见 §5.A5）→ 写了完全无效果 | `[src] v1.19.32 vless.go:83`；`git grep -l ws-headers v1.19.32` = 仅 `vless.go`；字段名全仓库引用数扫描 = 1 |

### 6.2 行为变更（有明确版本号）

| 项 | 变更 | 版本 | 证据 |
|---|---|---|---|
| AnyTLS `client-metadata` | 默认不再发送 | **v1.19.30** | `[doc]` anytls 页 `!!! warning` |
| `fingerprint`（证书固定）用于中间/根证书时 | 额外要求 SNI/servername 匹配 | **v1.19.20** | `[doc]` tls 页 warning |
| 全局 TLS（API 用）的 `certificate`/`private-key`/`ech-key` | 本地文件时支持自动重载 | **v1.19.18** | `[doc]` general 页 note |
| 配置文件里的所有路径 | 出于安全被限制在 workdir 内（除非设 `SAFE_PATHS`） | **v1.19.6**（v1.19.7–v1.19.11 重复声明） | `[meta]` RN v1.19.6 “Incompatible changes: … For security reasons, all paths appearing in the configuration file will be limited to workdir …” |
| `dialer-proxy` 静态配置 | 新增强校验（引用存在性） | **v1.19.20** | `[meta]` RN v1.19.20 “710772f chore: add simple validation for static dialer-proxy config (#2551)”；`[src] config/utils.go:147-176` |
| 被移除配置项 | 改善日志 | **v1.19.21** | `[meta]` RN v1.19.21 “c3399fd chore: better logging for removed configurations by @wwqgtxx” |
| Decoder 非法值处理 | `decode` 中对非法值的处理被修复 | **v1.19.1** | `[meta]` RN v1.19.1 “3f6823b fix: handle invalid values in Decoder's decode method by @wwqgtxx” |
| hysteria2 `udp-mtu` 默认值 | 默认值改为 1200−3 | **v1.18.1** | `[meta]` RN v1.18.1 “chore: hysteria2 add udp-mtu option default value is 1200-3…” |
| `reject` / `dns` outbound | 不再需要解析；UDP DNS 解析推迟到连接建立时 | **v1.19.10 / v1.19.11** | `[meta]` RN v1.19.10/11 “For reject and DNS outbound, no resolution is required.” |
| 无效 Clash 域名规则 | 报更详细的错误 | **v1.19.31** | `[meta]` RN v1.19.31 “2f7eae5 chore: report detailed errors for invalid Clash-style domain patterns by @wwqgtxx” |
| amd64 构建产物命名 | `-amd64` / `-amd64-compatible` → `-amd64-v1/v2/v3` | **v1.19.12**（v1.19.13/14 重复提示） | `[meta]` RN v1.19.12 |

### 6.3 AmneziaWG 方言内部版本（不是 mihomo 版本）

`j1`/`j2`/`j3`/`itime` 仅 AmneziaWG v1.5，v2+ 已移除（`[doc]` wg 页 YAML 注释）；`version: 2` 时用 legacy 实现，`version: 3` 才用 v3 实现（`[doc]` 同上）。**mihomo 版本门槛 UNKNOWN。**

---

## 7. URI / 订阅解析能力

### 7.1 接受的 scheme 全集（`[src] common/convert/converter.go` 的 `case` 标签）

| scheme（小写后比较） | 映射到的 `type` | 行号 |
|---|---|---|
| `hysteria` | `hysteria` | `converter.go:37` |
| `hysteria2`, `hy2`, `hysteria2+realm`, `hy2+realm` | `hysteria2`（`+realm` 额外生成 `realm-opts`） | `converter.go:72` |
| `tuic` | `tuic` | `converter.go:118` |
| `trojan` | `trojan` | `converter.go:161` |
| `vless` | `vless` | `converter.go:222` |
| `vmess` | `vmess`（先试 base64 JSON，失败再按 URL 解析 = Xray VMessAEAD 链接） | `converter.go:245-247` |
| `ss` | `ss`（支持 SIP002、旧式整体 base64、`user:pass` base64） | `converter.go:400` |
| `ssr` | `ssr` | `converter.go:487` |
| `socks`, `socks5`, `socks5h` | **`socks5`** | `converter.go:546, 576-580` |
| `http`, `https` | **`http`**（`https` 额外 `tls: true`） | `converter.go:546, 581-587` |
| `anytls` | `anytls` | `converter.go:598` |
| `mierus` | `mieru` | `converter.go:641` |

**共 12 个 case 分支（含别名后覆盖 19 个 scheme 字符串）。**

**不接受的 scheme**（无 case、无 default → 静默跳过）：`wireguard`/`wg`、`snell`、`ssh`、`shadowquic`、`sudoku`、`masque`、`openvpn`、`tailscale`、`zerotier`、`easytier`、`gost-relay`、`shadowtls`、`restls`、`jls`、`splithttp`、`ssconf` 等。`[src] converter.go:36-750`（switch 无 default 分支）。

### 7.2 入口与整体流程

```
proxy-provider payload/http/file 内容
  → adapter/provider/provider.go:378-390
      ├─ 先 yaml.Unmarshal(buf, &ProxySchema{})   // 期望有 proxies: 数组
      │    成功但 schema.Proxies == nil → 硬错误 "file must have a `proxies` field"
      └─ YAML 失败 → convert.ConvertsV2Ray(buf)
            → DecodeBase64(buf)          // common/convert/base64.go
            → 按 "\n" 切行
            → 逐行 Cut("://")            // 无 "://" 直接跳过
            → switch scheme              // 未知 scheme 直接跳过
```
`[src] adapter/provider/provider.go:378-395`；`[src] common/convert/converter.go:16-40`。

- **provider `type` 只有 `http`/`file`/`inline`**（`[doc]` proxy-providers 页 “Available options: `http` / `file` / `inline`”）。
- `[doc]` “`YAML`/`uri`/`base64` cannot be written in the same file; `uri`/`base64` do not require the `proxies:` field”（<https://wiki.metacubex.one/en/config/proxy-providers/content/>）。

### 7.3 会被丢掉的 URI 参数（`vless` / `vmess` 共用 `handleVShareLink`，`[src] common/convert/v.go:12-166`）

**被读取的参数（白名单）**：

| URI 参数 | 映射到 | 备注 |
|---|---|---|
| `security` | `tls: true`（当值以 `tls` 结尾或等于 `reality`） | `[src] v.go:25-27`；**`xtls` 也匹配后缀**（§5.E11） |
| `fp` | `client-fingerprint` | **缺省时强制注入 `chrome`**（`v.go:28-33`） |
| `alpn` | `alpn`（逗号切分） | `v.go:34-36` |
| `pcs` | `fingerprint`（证书固定） | `v.go:37-39` |
| `sni` | `servername` | `v.go:41-43`；**无条件写入，即使 `security=none`** |
| `pbk` | `reality-opts.public-key`（+`sid`→`short-id`、`support-x25519mlkem768`） | `v.go:44-56`；**只要 `pbk` 存在就写 `reality-opts`，不看 `security`** |
| `packetEncoding` | `packet-addr` / `xudp` | `[src] v.go:55-62`；未知值 → `xudp` |
| `type` | `network` | `v.go:64-73`；`tcp`+`headerType=http`→`http`；`http`→`h2`；**其它值原样透传** |
| `headerType` | （仅用于上面那条判定） | `v.go:69` |
| `host`, `path`, `method` | `http-opts` / `h2-opts` / `ws-opts.headers` | `v.go:77-105` |
| `ed`, `eh` | `ws-opts.max-early-data` / `early-data-header-name`（`httpupgrade` 时改成 `v2ray-http-upgrade-fast-open`） | `v.go:113-127` |
| `serviceName` | `grpc-opts.grpc-service-name` | `v.go:136-139` |
| `mode`, `extra`（JSON） | `xhttp-opts`（`extra` 经 `parseXHTTPExtra` 展开，含 `xmux`→`reuse-settings`、`downloadSettings`→`download-settings`） | `v.go:141-166` + `:168-380` |

**会被静默丢弃的参数（不在白名单）**：`enc`、`path` 之外的 `spx`、`fm`、`fragment`、`headerType` 之外的一切、`quicSecurity`、`key`、`seed`、`alterId`（VLESS/VMess URI 里）、`allowInsecure`（vless/vmess 路径不读，**trojan 路径读**）、`insecure`（vless/vmess 不读）、`eh` 之外的 ws 参数、`mode` 之外的 xhttp 顶层参数（只能塞进 `extra`）等。
`[src]`：`handleVShareLink` 全文只调用了 `query.Get` 于上述键（`v.go:12-166`），其余键从未被读取。

**`trojan` 分支（`converter.go:161-221`）额外/不同**：
- `allowInsecure` → `skip-cert-verify`；`type` → `network`；**`type` 只处理 `ws` 与 `grpc`**，其它值原样写入 `network`（→ 内核静默按 TCP）。
- `fp` 缺省同样注入 `client-fingerprint: "chrome"`（`converter.go:212-216`）。
- `security` **不读取** → trojan 链接的 `security=` 参数被丢弃。

### 7.4 各协议专属的丢弃点

| scheme | 特殊处理 | 丢弃内容 | 证据 |
|---|---|---|---|
| `hysteria` | `peer`→`sni`，`obfs`，`alpn`，`auth`→`auth_str`，`protocol`，`up`/`upmbps`，`down`/`downmbps`，`insecure` | 其余 query 全部丢弃（**无 `ports`/`hop-interval`**） | `[src] converter.go:37-70` |
| `hysteria2` | `splitHysteria2Ports` 拆 `host:443,8443-9443` → `port` + `ports`；`obfs`/`obfs-password`/`sni`/`insecure`/`alpn`/`pinSHA256`→`fingerprint`/`down`/`up`；`+realm` 变体用 userinfo+path 生成 `realm-opts` | **`hop-interval` 无法从 URI 表达**；`obfs-min/max-packet-size` 无法表达 | `[src] converter.go:72-117`、`v.go:379-424` |
| `tuic` | userinfo 有 `:` → V5（`uuid`+`password`），否则 `token`（V4）；`congestion_control`/`alpn`/`sni`/`disable_sni`/`udp_relay_mode` | `allow_insecure` **按注释被有意移除**（`converter.go:121` “Remove `allow_insecure` field”）→ **无法从 URI 关闭证书校验** | `[src] converter.go:118-160` |
| `ss` | SIP002：`user:pass`（含 base64 fallback）、`udp-over-tcp`/`uot`、`plugin` | 见 §5.E5/E6：**非 obfs/v2ray-plugin 的 plugin 全部丢弃**；`plugin-opts` 只取 `mode`/`host`/`path`/`tls` | `[src] converter.go:400-486` |
| `ssr` | 整体 base64 → `host:port:protocol:method:obfs:urlsafebase64pass/?obfsparam=…&protoparam=…&remarks=…`；**冒号分段必须恰好 6 段**，否则 `continue` 整行丢弃 | 只读 `remarks`/`obfsparam`/`protoparam`；**`group`、`udpport`、`uot` 从未被读取 → 静默丢弃**；`udp` 被硬置 `true`（忽略链接里的 `uot`/`udpport`） | `[src] converter.go:487-545`（`beforeArr` 长度校验 `:504-506`；`ssr["udp"] = true` `:543`） |
| `socks`/`http(s)` | userinfo 必须整体 base64（`DecodeBase64`），`username:password` | **`skip-cert-verify` 无条件 `true`**（§5.E10）；remark 缺省时用 `server:port` | `[src] converter.go:546-597` |
| `anytls` | `insecure == "1"` → `skip-cert-verify`；`sni`；`hpkp`→`fingerprint`；无 password 时 password=username | `udp` 被硬置 `true` | `[src] converter.go:598-640` |
| `mierus` | 从 `port`（可带 `-` 区间）+ `protocol` 两个**平行数组**生成多条节点；`multiplexing`/`handshake-mode`/`traffic-pattern`；profile 名 | **`len(port) != len(protocol)` 或 `port` 为空 → `continue` 整行丢弃** | `[src] converter.go:641-741` |

### 7.5 名字去重（会影响「同一个节点」的判定）

`uniqueName`：同名节点第二次出现会被改写成 `name-02`、第三次 `name-03`……（`[src] converter.go:748-758`；注意首个是 `name`，第二个是 `name-02`）。**兼容性判断不能按名字匹配**，因为转换会改名字。

### 7.6 provider `override`（可以强制/删除字段的官方钩子）

`[src] adapter/provider/override.go:10-28` 的 `overrideSchema` 字段与 `[doc]` proxy-providers 页**完全一致**：
`tfo`, `mptcp`, `udp`, `udp-over-tcp`, `up`, `down`, `dialer-proxy`, `skip-cert-verify`, `name-cert-verify`, `interface-name`, `routing-mark`, `ip-version`, `additional-prefix`, `additional-suffix`, `proxy-name`, `override-expr`。

- `override-expr` 是 yq v4 子集，**可以 `del(.field)` 删除字段、也可以强制赋值**（`[doc]` 示例含 `del(.skip-cert-verify)`、`'.plugin-opts.mode = "tls"'`、`'(select(.port == 443) | .tls) = true'`）。
- 未列出的 `override` 键 → 未知键，静默丢弃（普通 `structure` 解码）。
- `filter` / `exclude-filter` 用 `` ` `` 分隔多条正则；`exclude-type` 用 `|` 分隔且**不支持正则**（`[doc]`；`[src] adapter/provider/provider.go:345-352, 408-421`）。

---

## 8. UNKNOWN 清单

以下均为**查不到 / 无法确证**，按纪律一律标 UNKNOWN，不得据推测填写。

### 8.1 版本门槛类（剩余缺口）

1. **UNKNOWN** — **pre-v1.10 的 proxy type 门槛**：`v1.0.0`–`v1.8.0` 的 release 正文为空，`ss`/`ssr`/`vmess`/`trojan`/`socks5`/`http`/`ssh`/`snell`/`direct`/`dns`/`reject` 无法从 release note 定位。现有最早确凿证据是 **tag v1.6.5 的源码树**（见 §1 表中标 “≤ v1.6.5” 的行）。
2. **UNKNOWN** — **git 图不连续带来的偏差**：`v1.14.x`–`v1.18.5` 不是 `origin/Meta` tip 的祖先，该窗口内「首个包含某 commit 的 tag」可能不准。本文在该窗口只采信 release note 或 raw 文件 diff 双重确认过的门槛。
3. **UNKNOWN** — `smux.max-connections` / `min-streams` / `max-streams` 三个子选项的最早版本（只确证了 `statistic`/`only-tcp` = v1.14.4、`brutal-opts` = v1.17.0）。
4. **UNKNOWN** — v1.19.22 当版被移除的 xhttp 选项清单：RN v1.19.22 只有一句 “7fdc122 fix: remove incomplete xhttp config options (#2648)”，**未枚举被删的选项**。
5. **UNKNOWN** — **全局 `mux:` 块是否曾经存在过**。字面量 `"mux"` 在 v1.6.5 / v1.8.0 / v1.10.0 / v1.12.0 / v1.14.0 / v1.17.0 / v1.18.10 / v1.19.32 的 `config/` 下均不出现，`git log -S'"mux"'` 无提交，Meta-Docs 也没有全局 `mux` 章节。**若曾存在，则早于可获得 release note 的时间（v1.9.0 / 2022-01-04）**。§5.A3 只能断言「v1.19.32 中它是未知键 → 静默丢弃」。
6. **UNKNOWN** — `smux.enabled` / `smux.padding` / `smux.brutal-opts.enabled` 的**文档化默认值**（文档只给了 `smux.protocol` 默认 `h2mux`）。
11. **UNKNOWN** — **snell `version: 5` 是否有真正的 v5 线协议**。RN v1.19.26 加入 v4/v5，但无任何说明解释 v1.19.32 为何把 5 直接改写成 4。
12. **UNKNOWN** — `vless.ws-headers` 从「有效」变成「死字段」的版本（release note 层面该字段一直「存在」，但 v1.19.32 源码中已无读取点 —— 见 §5.A5）。
13. **UNKNOWN** — **ECH（listener 侧）与 jls/restls/shadow-tls 的组合矩阵**：除文档里各协议页的零散说明外，未系统验证。
14. **UNKNOWN** — `openvpn` 的 `tls-auth`/`tls-crypt`/`tls-crypt-v2` 互斥是否被源码强制（`[doc]` 声明互斥，`[src]` 未逐行确认）。

### 8.2 校验/行为未确证

11. **UNKNOWN** — `snell.obfs-opts.version`（ShadowTLS 版本 1/2/3）传入越界值（如 `4`）时的行为；`[src] snell.go` 把 `opt.Version` 直接交给 `shadowtls.ShadowTLSOption{Version: …}`，**未在 outbound 层看到校验**；下游是否校验未读。
12. **UNKNOWN** — `smux.protocol` 传入未知值（如 `foo`）时是否报错。`SingMuxOption.Protocol` 被直接传给外部依赖 `github.com/metacubex/sing-mux` 的 `mux.NewClient`（`[src] adapter/outbound/singmux.go:96-110`），该依赖**不在源码 tarball 内**（`go mod` 依赖，本地无 module cache），故 mihomo 侧无校验这一点可确认，**依赖侧是否报错未确证**。
13. **UNKNOWN** — `ssr` 的 `obfs`/`protocol` 是否有枚举校验（outbound 层没看到；`[doc]` ssr 页也没给允许值列表）。
14. **UNKNOWN** — 服务端**不支持 smux** 时 mihomo 的行为（`[doc]` 明确没有描述，源码层只是包装连接，实际协商失败的表现未验证）。
15. **UNKNOWN** — `interface-name` 指向不存在的网卡、`routing-mark` 无权限、`mptcp`/`tfo` 在内核不支持时的**具体错误形态**（是拨号期报错、还是静默回退）。`[src]` 只看到选项被传递（`base.go:146-172`、`component/dialer/dialer.go:158, 186-187`），未追踪 socket 选项失败路径。
16. **UNKNOWN** — `openvpn` 的 `tls-auth`/`tls-crypt`/`tls-crypt-v2` 互斥是否被源码强制（`[doc]` 声明互斥，`[src]` 未逐行确认）。
17. **UNKNOWN** — `hysteria`(v1) 的 `protocol` 未知值行为。`[src] hysteria.go:195-197` 只在空值时兜底 `DefaultProtocol = "udp"`，非空值原样传给 `core.NewClient(...)`；服务端是否拒绝未验证。
18. **UNKNOWN** — `xhttp-opts.session-*` / `seq-*` / `uplink-*` 组合约束（如 `session-length` 起点不能为 0、`total ID space > 2.1e9`、`seq-placement` 必须在 `session-placement: path` 时也为 `path`、`uplink-chunk-size` 最小 64 字节）**是否被 mihomo 校验**。`[doc]` 只说约束，未说会报错；`[src] transport/xhttp/` 只确证了 `mode` 与 `sc-max-each-post-bytes`/`sc-min-posts-interval-ms` 走 `GetNormalized*` 归一化（`client.go:253-262`），其余未逐一读完。（**`xhttp-opts.mode` 本身不在此列 —— 它已被确证为配置期硬错误，见 §2.4。**）
19. **UNKNOWN** — `masque.network` 未知值、`sudoku.aead-method` 未知值、`trusttunnel.health-check` 结构的具体校验。
20. **UNKNOWN** — `provider.health-check` / `override` 之外的 provider 键（`size-limit`、`age-secret-key`、`header`）的校验细节。

### 8.3 无法用文档/源码证明的（本项目最需要 `[test]` 的部分）

21. **UNKNOWN** — §5 全部条目的**实机表现**：本文的「静默按 TCP / 静默失效」均由源码控制流推断，**尚无 `[test]` 证据**。建议 Phase 2 用真内核逐条验证，尤其是：未知 `network`、`network: httpupgrade`、`flow` 短串、`reality-opts` + `ws`、`tls: false` + `ech-opts.enable: true`、`smux` 无 `enabled`、`snell.version: 5`、`client-fingerprint: iOS`。
22. **UNKNOWN** — Xray/sing-box 侧对同名节点的行为，本文**完全没有涉及**（不在研究范围），因此「四层不一致」目前只覆盖 mihomo 一侧。
23. **UNKNOWN** — `mihomo -t` 是否会因为**运行期**错误（如 §5.C3 的 Reality 缺 fp）而失败：`[src] main.go:175-187` 走的是 `executor.Parse()` / `ParseWithBytes`（完整 `ParseRawConfig`），理论上只做解析与初始化，但 C3 的错误发生在 `DialContext`，故推断 `-t` 检测不到 —— **推断，非实测**。

---

## 附：给下游工具的实现建议（基于本文可确认的事实）

1. **不要把 `mihomo -t` 通过当作「支持」**。`[src] main.go:175-187` + `common/structure/structure.go` 说明 `-t` 只验证「必填键是否出现、值能否转型」，**未知键与未知枚举值一律放过**。
2. **必须自带 `network` 白名单矩阵**（§2.3），并按 (type, network) 组合判定，而不是只看 `network` 字符串。
3. **必须自带字段名规范化层**：同一语义在 vmess/vless 叫 `servername`、在 trojan/hysteria2/tuic/anytls 叫 `sni`；写错不会报错只会静默失效（§3.1）。
4. **URI → YAML 转换要单独建「丢弃参数」表**（§7.3/§7.4），并特别标记 `httpupgrade`/`splithttp`/`kcp` 这三个 transport 的 URI 表达与 mihomo 运行期不一致（§5.B2/B3）。
5. **判定「完整可用」时必须叠加运行期条件**：Reality 需 `client-fingerprint`（§5.C3）；ECH 需 `tls: true` 且不与 shadow-tls/restls/jls 同用（§5.C6-C8）；`smux` 需 `enabled: true`（§5.D1）；`udp: false` 在 UDP 协议上无效（§5.D3）。
6. **「必填」要分两层报**：解码器级必填（§1 表，来自 `omitempty` 缺失）+ 语义必填（如 hysteria 的 `up`/`down` 还会被 `Speed()` 二次校验，`mieru.transport` 必须恰好是 `TCP`/`UDP`，大小写敏感）。文档与源码在此**多处冲突**：tuic 的 `token`/`uuid`/`password` 文档标 Required 而源码全可选；hysteria 的 `up`/`down` 源码必填而文档未标；shadowquic 的 `username`/`password` 文档标 Required 而源码可选。
