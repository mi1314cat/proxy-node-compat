# 跨内核能力矩阵（真内核回环实测）

> 本文件回答**同一个能力组合，在三个真内核上分别能做到哪一层**。
> 结论只对下表三个二进制版本负责；每条结论都带证据类型 / 置信度 / 复现方式 / limits。
>
> 与 `anyreality.md` 的关系：那份文档把 **ss+REALITY 的运行层标成 UNKNOWN**（回环未跑通）。
> 本轮把回环跑通了，并给出**当时的失败原因**（不是内核不支持，是测试用 dest 的握手指纹超过
> reality 的 8192 缓冲 —— 见 §2.4 与 §6 的 `e-xtest-reality-8192`）。故本文件**取代** anyreality.md 的运行层结论。

---

## 0. 被测对象、方法与可复现性

| 内核 | 版本 | 二进制 | 校验器 |
|---|---|---|---|
| Xray | 26.3.27 (d2758a0, go1.26.1 linux/amd64) | `/usr/local/bin/xray` | `xray -test -config` |
| mihomo | Mihomo Meta v1.19.32 (go1.26.8, with_gvisor) | `/root/catmi/mihomo/mihomo` | `mihomo -t -f ... -d ...` |
| sing-box | 1.14.2 (af6e64c, with_utls/with_quic/...) | `/root/catmi/sing-box/sing-box` | `sing-box check -c ... -D ...` |

**两层探针**（沿用 `research/empirical/README.md` 的方法）：
Tier A = 内核自带校验器（只证明"配置层接受"）；Tier B = 真服务端 + 真客户端回环，
从客户端 socks/mixed 口 `curl http://127.0.0.1:<origin>/` 取回 `COMPAT-OK-ORIGIN`。
**只有 Tier B 能区分"配置通过"和"真能用"**，所以能起回环的组合一律起回环（服务端统一用 Xray，
除 B4/B6 里 Xray 自己不支持的组合改用 sing-box 服务端）。

**本轮有效性的前提（控制组 + 负对照，全部按预期）**：

| 控制/负对照 | 期望 | 实测 |
|---|---|---|
| ctrl-xray / ctrl-mihomo / ctrl-singbox `vless+tcp` 回环 | PASS | PASS ×3 |
| ctrl-xray/mihomo/singbox `ss2022` 回环 | PASS | PASS ×3 |
| ctrl-xray `vless+tcp+reality` 回环 | PASS | PASS |
| **neg-\*-deadproxy**（代理指向死端口 1） | FAIL | FAIL ×3 |
| a1 负对照：reality `publicKey` 写错 | FAIL | FAIL |

> ⚠️ 方法学事故（已修正，写在这里防复发）：最初 mihomo 用 `mode: global` 且不显式选路，
> GLOBAL 组默认选 **DIRECT**，流量**绕过代理直连** → 所有 mihomo 用例假 PASS。
> 是 `neg-mihomo-deadproxy`（死端口也"能通"）抓出来的。修正为
> `mode: rule` + `proxy-groups: [{name: PROXY, type: select, proxies: [t]}]` + `rules: [MATCH,PROXY]` 后重跑。
> 任何 mihomo 结论都必须先过死端口负对照。

**原始证据**（机器可读 + 逐进程日志）：

- `research/empirical/raw/cross-kernel-matrix-results.json` —— 60 个用例的 verdict / 校验器原文 / 日志尾部
- `research/empirical/raw/logs/*.log` —— 每个进程的完整 stdout+stderr（含 `[Info]/[Debug]` 原文）
- `research/empirical/raw/doc-findings-mux-xhttp-uri716.md` —— §3.5 引用的**文档/规范原文逐字摘录**
  （Xray 文档仓库全量克隆核对、discussion #4113、分享链接规范 #716、sing-box/mihomo 文档；含 URL 与提交哈希）
- 复现：`python3 tools/probe/loopback_matrix.py --out <path>`（在 RN 上跑；脚本自带 setup/teardown）
- 源码证据取自精确 tag 的 checkout：Xray `v26.3.27`、mihomo `v1.19.32`、sing-box `v1.14.2`，
  以及 Xray 依赖 `github.com/xtls/reality v0.0.0-20260322125925`、`sing-mux v0.3.8`、`sing-vmess v0.2.8`

---

## 1. 大矩阵

图例：`✅` = 回环通 · `❌` = 明确拒绝/跑不通 · `⚠️` = 配置接受但语义与预期不符（静默降级/忽略）
`—` = 该内核配置模型里**没有**这个字段 · `N/T` = 本轮未测

| # | 组合 | Xray 26.3.27 | mihomo 1.19.32 | sing-box 1.14.2 |
|---|---|---|---|---|
| A1 | **ss2022 + REALITY** | config ✅ `Configuration OK`<br>runtime ✅ **回环通**（错 pbk 必失败） | config ✅（`-t` 通过）<br>runtime ⚠️ **reality 被静默忽略**：打 reality 服务端 ❌，打裸 ss 服务端 ✅ | config ❌ FATAL `outbounds[0].tls: json: unknown field "tls"`<br>runtime —（无模型） |
| B1 | vless+tcp+vision+reality | ✅ 回环通 | ✅ 回环通 | ✅ 回环通 |
| B2 | vless+xhttp+reality | ✅ 回环通 | ✅ 回环通 | config ❌ FATAL `unknown transport type: xhttp` |
| B3a | xhttp `mode=packet-up` | ✅ 回环通 | ✅ 回环通 | —（连 xhttp 都没有） |
| B3b | xhttp `mode=stream-one` | ✅ 回环通 | N/T（同族字段存在，未单测） | — |
| B3c | xhttp `xmux`：`maxConcurrency`+`maxConnections` 同填 | config ❌ `maxConnections cannot be specified together with maxConcurrency` | —（无 xmux 模型） | — |
| B3d | xhttp `xmux` 只填其一 | config ✅（单填合法） | — | — |
| B4 | vless+**ws**+reality | config ❌ `REALITY only supports RAW, XHTTP and gRPC for now.`（in/out 都一样） | config ✅ `-t` 通过<br>runtime ❌ **reality 在 ws 分支没被应用**（源码见 §5.5） | ✅ 回环通（sing-box 服务端 + 客户端）；跨内核 mihomo 客户端 ❌ |
| B5 | vless+tcp+**ECH** | ✅ 回环通（两端都是 Xray；错 ECH 密钥必失败） | ✅ 回环通（错密钥必失败 → 真的发了 ECH） | ✅ 回环通（错密钥必失败）；注意 **`ech.config` 要 PEM**，裸 base64 → FATAL |
| B6 | **mux/smux/multiplex** | mux.cool，**默认关闭**，`v1.mux.cool:9527` | smux（h2mux/smux/yamux），`sp.mux.sing-box.arpa:444` | multiplex（h2mux/smux/yamux）＋**服务端兼容 mux.cool** |
| B6a | 跨内核搬 mux | xray mux.cool → sing-box 服务端 ✅ | mihomo yamux → sing-box ✅；→ xray ❌ | sing-box smux → xray ❌；→ sing-box ✅ |
| B6b | XHTTP + mux.cool 同时开 | runtime ❌ `common/mux: unexpected network TCP` | — | — |
| B7 | `flow=xtls-rprx-vision` + `security=none` | config ✅ → runtime ❌ `XTLS only supports TLS and REALITY directly for now.` | config ✅ → runtime ❌ `failed to use vision, maybe "tls" is not enable...` | config ✅ → runtime ❌ `initialize vision: ... not a valid supported TLS connection` |
| — | 复核：mihomo 未知 `network` 值 | — | config ✅（`-t` 通过）→ runtime **静默按 tcp**（日志显示对 127.0.0.1:443 做 TCP+TLS） | — |
| — | 复核：mihomo ss 上写非法 `reality-opts` | — | config ✅（不校验，因为 `ss` 上根本没这个字段） | — |

**矩阵要点（跨内核不通的组合）**：
1. `ss + reality`：只有 Xray 能表达且真能用；mihomo 静默忽略；sing-box 无模型。
2. `ws + reality`：Xray **拒绝配置**；mihomo **接受但 runtime 不生效**；只有 sing-box 通。
3. `xhttp` 系列（含 `packet-up`/`stream-one`/`xmux`）：sing-box 完全没有模型。
4. mux/smux 三方语义不同构，跨内核只有两个方向能通（xray mux.cool→sing-box、smux→sing-box）。
5. `flow=vision` + `security=none`：三家**全部**是"配置通过、运行期才报错"。

---

## 2. A. SS + REALITY（AnyReality 变体 #1）

### 2.1 A1 · Xray：`ss2022 + reality` —— 能用（回环实证）

**做法**：`xray -test` 通过；回环 = Xray 服务端 `shadowsocks` 入站 + `streamSettings.security=reality`
（`dest`/`privateKey`/`shortIds`）↔ Xray 客户端 `shadowsocks` 出站 + reality（`publicKey`/`shortId`/`fingerprint=chrome`）
→ 客户端 socks 口 `curl` 取回 origin 内容。

```bash
# 用例: a1-xray-ss-reality (见 tools/probe/loopback_matrix.py)
xray -test -config a1-xray-ss-reality.server.json   # rc=0  Configuration OK.
xray -test -config a1-xray-ss-reality.client.json   # rc=0  Configuration OK.
curl -s -m 8 --socks5-hostname 127.0.0.1:<cp> http://127.0.0.1:<origin>/
```

原文输出关键字（`raw/logs/a1-xray-ss-reality.*.log`）：

```
[Info] infra/conf: REALITY: Listening on non-443 ports may get your IP blocked by the GFW
[Warning] common/errors: The feature Shadowsocks (with no Forward Secrecy, etc.) is deprecated, ...
[Info] ... proxy/shadowsocks_2022: tunneling request to tcp:127.0.0.1:<origin> via 127.0.0.1:<sp>
curl rc=0  out='COMPAT-OK-ORIGIN'
```

**负对照（决定性）**：同一个服务端 + 客户端只改 `publicKey` → 客户端
`proxy/shadowsocks_2022: failed to connect to server > x509: certificate signed by unknown authority`，
服务端 `REALITY: processed invalid connection ...: authentication failed or validation criteria not met`。
→ 说明这条链路上 **reality 真的在被校验**，不是"配了但没人管"。

- 证据：`RUNTIME_TEST` + `CONFIG_VALIDATION`（HIGH）／源码侧 `SRC`：ss 出站的 stream 层走通用
  `internet.DialSystem` 路径，reality 是**传输层**能力，与协议无关。
- 密钥长度：`2022-blake3-aes-128-gcm` 用 `openssl rand -base64 16`（=24 字符）；本轮全部用对长度。
- **limits**：只证明该版本该构建；`socks5` 目标走 TCP；UDP/`network: tcp,udp` 未单测；
  服务端 reality `dest` 用的是**本地 Go TLS 服务端**（原因见 2.4）。

### 2.2 A2 · mihomo：`type: ss` + `reality-opts` —— **静默忽略**（不是 UNKNOWN 了）

三个实测合起来是决定性的：

| 用例 | 服务端 | 结果 | 含义 |
|---|---|---|---|
| `a2-mihomo-ss-reality` | Xray `ss+reality` | ❌ curl rc=52 | 打不通真 reality 服务端 |
| `a2b-mihomo-ss-reality-vs-plain` | Xray **裸 ss**（无 reality） | ✅ 通 | 带 `reality-opts` 的配置照样连上了**不要求 reality** 的服务端 |
| `a2c-mihomo-ss-plain-vs-reality-server` | Xray `ss+reality` | ❌ | 去掉 `reality-opts` 同样不通（服务端确实要求 reality） |

`a2b` 通过 = mihomo 把 `reality-opts` **整段丢掉**、只发裸 ss；配置层不报错是因为 mihomo 用的是
弱类型 decoder，**未知键不报错**（`common/structure/structure.go`：只有 `remain` 字段与
"结构体有未赋值字段"会报，多余的 data key 直接放过——对比 `cfg-mihomo-smux-bogus-protocol` 会报错，
说明**并非所有字段都不校验**，而是 ss 上**根本没有** `reality-opts` 这个字段）：

```go
// mihomo v1.19.32 adapter/outbound/shadowsocks.go
type ShadowSocksOption struct {
    ...
    Plugin            string         `proxy:"plugin,omitempty"`
    PluginOpts        map[string]any `proxy:"plugin-opts,omitempty"`
    ClientFingerprint string         `proxy:"client-fingerprint,omitempty"`
}   // ← 没有 reality-opts, 也没有 tls
```

- 证据：`RUNTIME_TEST`（HIGH）+ `SRC`（HIGH）+ `CONFIG_VALIDATION`（`cfg-mihomo-ss-reality-badkey`
  在 ss 上写**非法** public-key，`-t` 依旧 `test is successful`）。
- **limits**：只对 mihomo 1.19.32；`plugin=shadow-tls/restls/jls` 这类"自带 TLS 家族的 ss 变体"未测
  （它们走的是另一条路，与 reality 无关）。

### 2.3 A3 · sing-box：**内核没有这个模型**

```bash
sing-box check -c a3-singbox-ss-reality.client.json -D <dir>
# FATAL[0000] decode config at .../a3.client.json: outbounds[0].tls: json: unknown field "tls"
```

```go
// sing-box v1.14.2 option/shadowsocks.go
type ShadowsocksOutboundOptions struct {
    DialerOptions
    ServerOptions
    Method        string                    `json:"method" ...`
    Password      string                    `json:"password"`
    Plugin        string                    `json:"plugin,omitempty"`
    PluginOptions string                    `json:"plugin_opts,omitempty"`
    Network       NetworkList               `json:"network,omitempty"`
    UDPOverTCP    *UDPOverTCPOptions        `json:"udp_over_tcp,omitempty"`
    Multiplex     *OutboundMultiplexOptions `json:"multiplex,omitempty"`
}   // ← 没有 TLS/安全层字段(不是"被移除", 是从未有)
```

**"内核没有该模型" 还是 "厂商不支持"？答：是内核的数据模型里没有这一层。**
sing-box 的安全层是**按协议显式挂载**的（`OutboundTLSOptionsContainer` 只被 vless/trojan/vmess/
hysteria 等类型嵌入；`shadowsocks` 类型不嵌入）。因此这**不是**"厂商表态不支持 ss+reality"这种
策略性缺失，而是**表达层缺失**：写 `tls`/`reality` 直接 `unknown field` 硬报错。
对照 mihomo：字段也没有，但**不报错**（静默忽略）——两者失败模式不同，能力注册表必须分开记。

- 证据：`CONFIG_VALIDATION`（HIGH）+ `SRC`（HIGH）
- **limits**：只证明 shadowsocks 出站；sing-box 的 `shadow-tls` 出站（`shadowtls` 类型）是另一条路径，
  本轮未测；`ss2022 + shadow-tls` 与 `ss+reality` 不是一回事。

### 2.4 顺带：为什么上一轮 anyreality.md 的回环没跑通（重要）

用**真实站点** `www.microsoft.com:443` 作 reality `dest` 时，即使 reality 认证成功
（服务端日志 `hs.c.conn == conn: true`、ClientVer/ClientTime/ClientShortId 全部正确解密），
握手仍然不完成：

```
REALITY remoteAddr: ... len(s2cSaved): 1154	Certificate: 8273
REALITY remoteAddr: ... hs.c.isHandshakeComplete.Load(): false
[Info] transport/internet/tcp: REALITY: processed invalid connection from ...: handshake did not complete successfully
```

**源码解释**（`github.com/xtls/reality` 的 server 端 mimicry 循环）：

```go
size  = 8192
...
if config.Show { fmt.Printf("len(s2cSaved): %v\t%v: %v\n", ...) }   // 先打印(所以我们看到 8273)
if handshakeLen > size { break f }                                  // 8273 > 8192 -> 直接退出读取循环
```

`dest` 的 Certificate 记录 8273 字节 > 8192 缓冲 → 循环 `break` → `hs.handshake()` 从未被调用 →
"handshake did not complete successfully"。**换成证书记录 ~466B 的本地 Go/Xray TLS 服务端作 dest 后，
同一套 ss+reality 配置立刻回环成功**（`hs.handshake() err: <nil>`、`isHandshakeComplete: true`、
客户端 `uConn.Verified: true`）。

- 证据：`RUNTIME_TEST`（A/B 对照，HIGH）+ `SRC`（HIGH）
- **limits**：① 只对 26.3.27 该构建；② 这是 **reality 服务端**行为，与本项目要判定的**客户端**能力
  无关，但会影响"自建节点能不能用真实站点当 dest"的运维结论；③ 是否**所有** >8192B 证书的真实
  dest 都失败、以及 <8192B 的真实 dest 是否都成功，本轮只测了 microsoft（失败）与本地 Go TLS（成功），
  其余真实站点的探测因等待时间不足而**不确定**（见 §7 UNKNOWN）。

---

## 3. B. VLESS 各变体

### 3.1 B1 · `vless + tcp + xtls-rprx-vision + reality` —— 三家都能用

回环：Xray 服务端（`clients[].flow=xtls-rprx-vision` + reality），三个内核分别做客户端，全部取回内容。

| 客户端 | config | runtime | 关键日志 |
|---|---|---|---|
| Xray `flow: xtls-rprx-vision` | ✅ | ✅ PASS | `proxy/vless/outbound: tunneling request to tcp:...` |
| mihomo `flow: xtls-rprx-vision` + `reality-opts` | ✅ `-t` 通过 | ✅ PASS | `[TCP] ... match Match using PROXY[t]` |
| sing-box `flow: xtls-rprx-vision` + `tls.reality` | ✅ | ✅ PASS | `outbound/vless[out]: outbound connection to ...` |

- 证据：`RUNTIME_TEST`（HIGH）；限：TCP 目标、该版本；UDP/`xudp` 未测。

### 3.2 B2/B3 · `vless + xhttp + reality`（含 mode / xmux）

| 用例 | 结果 | 说明 |
|---|---|---|
| `b2-xray-xhttp-reality` | ✅ 回环通 | `network: "xhttp"`（`xhttpSettings.path`） |
| `b2-mihomo-xhttp-reality` | ✅ 回环通 | `network: "xhttp"` + `xhttp-opts.path` + `reality-opts` |
| `b2-singbox-xhttp-reality` | config ❌ | `FATAL ... outbounds[0].transport: unknown transport type: xhttp` |
| `b3-xray-xhttp-packetup` | ✅ 回环通 | 客户端 `xhttpSettings.mode="packet-up"` |
| `b3-xray-xhttp-streamone` | ✅ 回环通 | 两端 `mode="stream-one"` |
| `b3-mihomo-xhttp-packetup` | ✅ 回环通 | mihomo `xhttp-opts.mode="packet-up"` |
| `cfg-xray-xmux-both` | config ❌ | `infra/conf: maxConnections cannot be specified together with maxConcurrency` |
| `cfg-xray-xmux-maxconn-only` / `maxconc-only` | config ✅ | 只填一个 → `Configuration OK`（运行层本轮指向假端口，未测语义） |

`xmux` **默认值（源码）**：整个 `xmux` 对象缺省时

```go
// infra/conf/transport_internet.go (v26.3.27)
if c.Xmux == (XmuxConfig{}) {
    c.Xmux.MaxConcurrency.From = 1
    c.Xmux.MaxConcurrency.To = 1
    c.Xmux.HMaxRequestTimes.From = 600 ... To = 900
    c.Xmux.HMaxReusableSecs.From = 1800 ... To = 3000
}
```
即 26.3.27 里"不写 xmux" ⇒ `maxConcurrency = 1-1`。**注意这与官方 discussion #4113 §XMUX
写的 `"16-32"` 不一致**（该文还写了"全不填相当于全为零，会取到三个默认值"）。
两条证据冲突时本文件以**实测源码**为准，并把差异记为待核项（§7 UNKNOWN-6）。

- 证据：`RUNTIME_TEST`（HIGH，回环）+ `SRC`（HIGH，xmux 校验与默认值）；mihomo/sing-box 的
  xhttp 字段来自各自 SRC。
- **limits**：sing-box 的 xhttp **任何版本都没有**（`unknown transport type` 是"从未支持"而非"已移除"，
  见 §7 的 `KERNEL_NEVER_SUPPORTED`）；`stream-up` 模式、`downloadSettings` 未测；
  xmux 只做了配置层（单填合法、双填硬报错），**没有**测"maxConcurrency=1 时多请求是否真的串行"。

### 3.3 B4 · `vless + ws + reality` —— 三家三种失败

| 内核 | 配置层 | 运行层 | 失败模式 |
|---|---|---|---|
| Xray | ❌ 硬报错（入站/出站都拦） | — | `hard_error` |
| mihomo | ✅ `-t` 通过 | ❌ 连不上（reality 未生效） | `silent_noop_then_runtime_fail` |
| sing-box | ✅ | ✅ **回环通** | — |

```
# b4-xray-server-ws-reality / b4-xray-client-ws-reality  (xray -test, rc=23)
infra/conf: REALITY only supports RAW, XHTTP and gRPC for now.
```

mihomo 的失败是按下面的对照实验定位的（把"reality 坏"和"ws 坏"分开）：

| 隔离用例 | 结果 |
|---|---|
| `b4-singbox-server-ws-plain-mihomo`：mihomo **ws（无 TLS）** → sing-box ws 服务端 | ✅ PASS（ws 管道本身没问题） |
| `b4-mihomo-tcp-reality-vs-singbox-server`：mihomo **tcp + reality** → sing-box reality 服务端 | ✅ PASS（reality 本身没问题） |
| `b4-singbox-server-ws-reality-mihomo`：mihomo **ws + reality** → sing-box ws+reality 服务端 | ❌ `tls: failed to verify certificate: x509: certificate signed by unknown authority` |
| `b4-singbox-server-ws-reality-singbox`：sing-box ws+reality → 同服务端 | ✅ PASS（服务端配置无误） |

那个 x509 报错正是"客户端没做 reality、于是拿到了 reality 服务端回落到 `handshake.server` 的真实证书"
的指纹。源码证实（mihomo `adapter/outbound/vless.go`）：`ws` 分支自建 TLS 配置时**只传**
ShadowTLS/Restls/JLS 与普通 TLS 选项，**没有传 `Reality: v.realityConfig`**；而 `streamTLSConn()`
（tcp/h2/http 走的那条）里有 `Reality: v.realityConfig`；xhttp 走 `makeTransport(..., v.realityConfig != nil)`。

- 证据：`CONFIG_VALIDATION`（Xray 拒绝，HIGH）+ `RUNTIME_TEST`（mihomo 隔离对照，HIGH）+ `SRC`（mihomo，HIGH）
- **limits**：mihomo ws+reality 只在"sing-box reality 服务端"上试过；没有找到任何能通的证据，
  但**没有**穷举服务端（例如 mihomo 自家 listener）。

### 3.4 B5 · `vless + tcp + ECH`

三家都**能配、也真的会发 ECH**（正反对照齐全；服务端是 Xray `echServerKeys` +
`rejectUnknownSni=true`，证书只签 `www.microsoft.com`，ECH 配置的 public_name 是 `cover.example.com`）：

| 用例 | 结果 |
|---|---|
| `b5-control-xray-tls-noech`（纯 TLS，无 ECH） | ✅ PASS（TLS 服务端可用） |
| `b5-xray-ech`（`tlsSettings.echConfigList`） | ✅ PASS |
| `b5-xray-ech-wrongkey`（换成另一对 ECH 密钥） | ❌ FAIL |
| `b5-mihomo-ech`（`ech-opts: {enable, config}`） | ✅ PASS |
| `b5-mihomo-ech-wrongkey` | ❌ FAIL |
| `b5-singbox-ech`（`tls.ech: {enabled, config}`） | ✅ PASS |
| `b5-singbox-ech-wrongkey` | ❌ FAIL |

**判别逻辑**：若客户端根本没发 ECH，它会直接用 `servername=www.microsoft.com` 建 TLS，
服务端 `rejectUnknownSni` 会放行 → 假 PASS。而**错密钥必须失败**（回落到 ECH 的 public_name
`cover.example.com` → 被 `rejectUnknownSni` 拒），实测三个内核的错密钥用例**全部失败**，
所以正例 PASS 是"ECH 真被使用并解密成功"的证据，而不是巧合。

字段/格式差异（都是**配置层**差异，能力注册表要记）：

| 内核 | 客户端字段 | 备注 |
|---|---|---|
| Xray | `tlsSettings.echConfigList`（裸 base64 ECHConfigList）；服务端 `echServerKeys` | 另有 `echForceQuery`（走 DNS HTTPS RR）未测 |
| mihomo | `ech-opts: {enable: true, config: <base64>}` | 源码里 uTLS 路径(`ClientHandleUTLS`)与非 uTLS 路径(`ClientHandle`)**都接 ECH** → 不依赖 `client-fingerprint`（本轮用的是 uTLS/chrome 路径） |
| sing-box | `tls.ech: {enabled: true, config: ["<PEM>"]}` | **必须是 PEM**：`-----BEGIN ECH CONFIGS-----`；裸 base64 → `FATAL ... invalid ECH configs pem`（源码 `common/tls/ech.go` 校验 `block.Type != "ECH CONFIGS"`） |

另外本轮撞到 Xray 26.3.27 的**时间闸门式移除**：客户端 `tlsSettings.allowInsecure` 已不可用
（`The feature "allowInsecure" has been removed and migrated to "pinnedPeerCertSha256"`），
测试改用 `pinnedPeerCertSha256`（`xray tls hash --cert <pem>` 取 leaf SHA256）。

- 证据：`RUNTIME_TEST`（HIGH，正反 A/B）+ `SRC`（sing-box PEM 校验）+ `CONFIG_VALIDATION`（Xray allowInsecure 移除）
- **limits**：只测"显式 ECH 配置"；`echForceQuery`/DNS HTTPS RR 路径未测；没有抓包确认外层 SNI，
  结论建立在"服务端 rejectUnknownSni + 证书 SAN 只含内层名"这个**判别设计**上（已在 §4 记录设计本身）。

### 3.5 B6 · mux / smux / multiplex（三方语义不同构）

#### (1) Xray `mux` 默认值：**默认关闭**（源码 + 运行双证）

```go
// infra/conf/xray.go (v26.3.27) —— 没有 enabled=true 的默认, 也没有反序列化默认
type MuxConfig struct {
    Enabled         bool   `json:"enabled"`
    Concurrency     int16  `json:"concurrency"`
    XudpConcurrency int16  `json:"xudpConcurrency"`
    XudpProxyUDP443 string `json:"xudpProxyUDP443"`
}
// 且 MuxSettings == nil 时根本不构造 MultiplexingConfig
```

运行侧证据：`ctrl-xray-vless-tcp-none`（不写 `mux`）服务端日志里 **0 次** `mux` 字样；
`b6-ctrl-xray-mux`（`mux.enabled=true`）服务端立刻出现

```
[Info] ... proxy/vless/inbound: received request for tcp:v1.mux.cool:0
[Info] ... common/mux: received request for tcp:127.0.0.1:<origin>
```
→ mux.cool 真的被使用，且**默认不启用**。（`concurrency` 缺省 = 8，出自官方文档 `MuxObject`，非实测。）

#### (2) XHTTP 用 mux.cool：官方原文 + 实测复现

- 原文出处（子代理核查，**纠正了父会话的前提**）：那句话**不在** `config/outbound(s).html`（该页
  现在是 404 / 已改名 `outbound.html`），而在**当时的 XHTTP(SplitHTTP) 文档页** `## XmuxObject`，
  2024-12-13 随 XHTTP 文档重构被删：
  - EN: *"Since the default is unlimited reuse, `xmux` actually limits this. It's not recommended to enable `mux.cool` at the same time."*
  - ZH: *"仅客户端，允许用户对 XHTTP 在 h2 与 h3 中的多路复用行为进行控制。使用该功能时不要启用 mux.cool。"*
  - 永久链接：`https://github.com/XTLS/Xray-docs-next/blob/dcc39472dd7fd8772cdd453fdbc13176f5857ca8/docs/config/transports/splithttp.md`
- 维护者原文（discussion **#4113**《XHTTP: Beyond REALITY》，作者 **RPRX**，`author_association: MEMBER`）：
  *"此外，使用 XHTTP 时不要启用 mux.cool，并且新版 Xray 服务端已有检查，只接受纯 XUDP。"*
  以及维护者评论 `#discussioncomment-11491701`：*"双层 mux 肯定不合适，准备在 XHTTP 服务端禁掉了……"*
- **实测（`b6-xray-xhttp-with-muxcool`）**：配置层通过，运行层失败，服务端原文是

```
[Info] proxy/vless/inbound: received request for tcp:v1.mux.cool:0
[Info] common/mux: received request for tcp:127.0.0.1:<origin>
[Info] common/mux: unexpected EOF > common/mux: failed to process data > common/mux: unexpected network TCP
```
  对照 `b6-xray-xhttp-without-mux` ✅ 通过。
  → 更精确的表述：**不是"服务端不认 mux.cool 会话"，而是会话建立后 TCP 载荷被拒**
  （`unexpected network TCP`），与 #4113 那句"只接受纯 XUDP"吻合。

#### (3) `xmux`（XHTTP 自带多路复用）≠ mux.cool

- 默认值：源码 `c.Xmux == (XmuxConfig{})` → `maxConcurrency = 1-1`（§3.2 已列，**与 #4113 的 "16-32" 冲突**）。
- "不能同时指定"**属实且是硬报错**：`maxConnections cannot be specified together with maxConcurrency`
  （源码 `if c.Xmux.MaxConnections.To > 0 && c.Xmux.MaxConcurrency.To > 0 { return error }` + `xray -test` rc=23）。
- 二者是两回事：`xmux` 管的是"一条 XHTTP 连接里并发多少请求 / 最多几条连接"（
  `XMUX: creating xmuxClient because xmuxClients is empty` 是它的 debug 日志），
  mux.cool 是 **VLESS/VMess 层的固定目标 `v1.mux.cool:9527` 子协议**。

#### (4) 三者不是同一个东西（各有 SRC/运行证据）

| | Xray | mihomo | sing-box |
|---|---|---|---|
| 配置字段 | 出站 `mux: {enabled, concurrency, xudpConcurrency, xudpProxyUDP443}` | `smux: {enabled, protocol, max-connections, min-streams, max-streams, padding, ...}` | `multiplex: {enabled, protocol, max_connections, min_streams, max_streams, padding, brutal}` |
| 协议集合 | **只有 mux.cool** | h2mux / smux / yamux（文档默认 h2mux） | h2mux / smux / yamux（文档默认 h2mux）；`enum` 里**没有** mux.cool |
| 固定目标 | `v1.mux.cool`（`common/mux/client.go:185`；VLESS 里 `:9527`） | `sp.mux.sing-box.arpa:444`（运行日志实证） | `sp.mux.sing-box.arpa:444`（sing-mux v0.3.8 `Destination`） |
| 服务端能力 | 认 mux.cool | 未见 smux 服务端 | **认 mux.cool（仅服务端兼容）**：`sing-vmess` `HandleMuxConnection` + `MuxDestination{v1.mux.cool, 666}` + 官方测试 `test/mux_cool_test.go::TestMuxCoolServer` |
| 客户端能否配 mux.cool | 就是它 | 不能（`unknown protocol: no-such-mux` 类校验会拦） | **不能**：`FATAL initialize outbound[0]: unknown protocol: mux.cool` |

跨内核实测（B 层回环）：

| 客户端 → 服务端 | 结果 | 证据 |
|---|---|---|
| xray mux.cool → **xray** | ✅ | `received request for tcp:v1.mux.cool:0` |
| xray mux.cool → **sing-box** | ✅ | sing-box 日志 `mux connection closed: read frame header: EOF`（会话被识别并处理，请求成功取回内容） |
| mihomo smux(yamux) → **sing-box**(multiplex) | ✅ | 两边都用 sing-mux 约定 |
| mihomo smux(yamux) → **xray** | ❌ | xray 服务端把它当成目标域名：`default route for tcp:sp.mux.sing-box.arpa:444` → `lookup sp.mux.sing-box.arpa on 127.0.0.1:53: no such host` |
| sing-box multiplex(smux) → **xray** | ❌ | 同上（sing-box 客户端日志 `outbound connection to sp.mux.sing-box.arpa:444`） |
| sing-box multiplex(mux.cool) | config ❌ | `unknown protocol: mux.cool` |

**"跨内核搬运 mux 设置能不能保证语义一致？" → 不能，必然有损。**
理由不是"参数名不同"，而是三件更硬的事：① 协议集合不同（mux.cool ∉ sing-box 客户端可选集）；
② 复用目标地址不同（`v1.mux.cool` vs `sp.mux.sing-box.arpa`）→ 搬到不支持的那一侧会被当普通域名拨号
（实测 DNS 失败）；③ 字段语义不同（Xray 的 `concurrency` 是"每条 mux 连接的并发流上限"，
mihomo/sing-box 的 `max-connections`/`max-streams`/`min-streams`/`padding`/`brutal` 是另一套模型）。
只有"xray mux.cool → sing-box 服务端"和"mihomo/sing-box 的 smux 系 → sing-box 服务端"这两条路能通。

#### (5) 分享链接里的 mux：**没有**

XTLS/Xray-core discussion **#716**《VMessAEAD / VLESS 分享链接标准提案》（DuckSoft, MEMBER）
的 §4 参数表完整列出 `type / encryption / flow / security / path / host / mtu / tti / serviceName /
mode / authority / extra / fm / fp / sni / alpn / ech / pcs / vcn / pbk / sid / pqv / spx`，
**没有任何 mux/smux/multiplex 参数**（全文 0 匹配）；页面里唯一的 "mux" 是"计划中的 UDP over TCP MUX 隧道"
的讨论文字。sing-box/mihomo 的文档也没有把 mux 放进分享链接（mihomo 的订阅侧是客户端私有扩展）。
→ URI 层结论：`representation: NONE`，mux 设置**只能靠客户端本地配置**，跨客户端导入必然丢失
（应进 `losses[]`，而不是当"内核不支持"）。

- 证据：`SRC`（HIGH，三份源码 + 依赖源码）+ `RUNTIME_TEST`（HIGH，6 条跨内核回环）+ `DOC/COMMUNITY`
  （Xray 文档、#4113、#716、sing-box issue #1876、mihomo 文档）
- **limits**：① 只测 TCP 目标的 mux；UDP/XUDP-over-mux 未测；② mihomo 作为 mux **服务端**的
  接收能力未测（mihomo listener 模型里没有 smux/mux.cool 服务端字段，但没做回环）；
  ③ `max-connections`/`min-streams` 等参数的**运行语义**未逐项验证，只验证了"能不能通"。

### 3.6 B7 · `flow=xtls-rprx-vision` + `security=none`（三家都是"运行期才报错"）

| 内核 | config | runtime 原文 |
|---|---|---|
| Xray | ✅ `-test` OK | `proxy/vless/outbound: XTLS only supports TLS and REALITY directly for now.` |
| mihomo | ✅ `-t` OK | `vision: not a valid supported TLS connection: *net.TCPConn` + `failed to use vision, maybe "tls" is not enable and "encryption" is empty` |
| sing-box | ✅ `check` OK | `initialize vision: vision: not a valid supported TLS connection: *route.trackedConn` |

- 证据：`CONFIG_VALIDATION` + `RUNTIME_TEST`（HIGH，三家一致）
- **limits**：只测 `network=tcp`；`flow=xtls-rprx-vision` 配 `security=tls`（真实证书）未测
  （B1 用的是 reality 版本，已通过）。

---

## 4. 顺带产出的次要结论（都可直接进注册表）

| 结论 | 证据类型 | 置信度 | 备注 |
|---|---|---|---|
| mihomo 未知 `network` 值：`-t` 通过，运行期**静默按 tcp** | `CONFIG_VALIDATION`+`RUNTIME_TEST`+`SRC` | HIGH | 服务端日志 `default: // default tcp network`（`adapter/outbound/vless.go`）；本轮复现：写 `no-such-transport-xyz`，`-t` 成功，运行期真的对 `127.0.0.1:443` 做 TCP+TLS |
| Xray 26.3.27 移除 `allowInsecure` | `CONFIG_VALIDATION` | HIGH | `The feature "allowInsecure" has been removed and migrated to "pinnedPeerCertSha256"`；**时间闸门型移除**，注册表要带 `evaluated_at` |
| sing-box ECH 配置必须是 PEM | `CONFIG_VALIDATION`+`SRC` | HIGH | 裸 base64 → `FATAL ... invalid ECH configs pem` |
| Xray XHTTP `xmux` 单填合法、双填硬报错 | `CONFIG_VALIDATION`+`SRC` | HIGH | 双填错误原文见 §3.2 |
| mihomo `smux.protocol` **会**校验，`network` **不**校验 | `CONFIG_VALIDATION` | HIGH | `proxy 0: unknown protocol: no-such-mux` vs `test is successful` |
| mihomo 的 REALITY **要求** uTLS 指纹 | `SRC` | MEDIUM | `transport/vmess/tls.go`: `REALITY is based on uTLS, please set a client-fingerprint`；**未做运行期复现**（本轮所有 reality 用例都写了 `client-fingerprint`） |
| Xray SS 服务端/客户端启动打印弃用告警 | `RUNTIME_TEST` | HIGH | `The feature Shadowsocks (with no Forward Secrecy, etc.) is deprecated ... Please migrate to VLESS Encryption`（SS2022 也打印） |
| reality 服务端 mimicry 读循环 8192 上限 | `SRC`+`RUNTIME_TEST` | MEDIUM | 见 §2.4；只对 26.3.27 + reality 模块该 commit |
| mihomo 文档声明"不考虑兼容 xray v26.7.11+" | `DOC` | LOW/MEDIUM | 来自 mihomo TLS 文档页（子代理核查），是**未来版本**的预警，与本轮 26.3.27 结论不冲突 |

---

## 5. 给能力注册表的建议数据行

> 形状对齐 `docs/kernel-capability-registry.md` 的 `rule_id / selector / segments / verdict /
> failure_mode / evidence`。`verdict` 按层给（`config` / `runtime` / `uri` / `semantic`）。
> 所有行都只声明**被验证过的那个版本**（`range: "= <version>"`），版本边界一律 UNKNOWN。

```yaml
# ---------- A. SS + REALITY ----------
- rule_id: xray.protocol.shadowsocks.reality
  selector: {feature: standard:security.reality, protocol: shadowsocks}
  segments:
    - range: "= 26.3.27"
      verdict: {config: SUPPORTED, runtime: SUPPORTED}
      evidence: [e-xtest-a1-loopback, e-xtest-a1-negcontrol]
      note: "ss2022(2022-blake3-aes-128-gcm, 16B key) + reality 回环通; 服务端/客户端均可用"
  unknown_range: [{range: "!= 26.3.27", why: "只验证了这一版"}]

- rule_id: mihomo.protocol.shadowsocks.reality
  selector: {feature: mi1314cat:anyreality.ss-reality, protocol: shadowsocks}
  segments:
    - range: "= 1.19.32"
      verdict: {config: SUPPORTED_WITH_WARNING, runtime: UNSUPPORTED, semantic: UNSUPPORTED}
      failure_mode: silent_ignore          # ss 结构体里没有 reality-opts -> 未知键直接丢
      reason_code: KERNEL_NEVER_SUPPORTED
      losses: ["security.reality 被静默丢弃; 节点退化成裸 ss"]
      evidence: [e-xtest-a2-vs-reality, e-xtest-a2b-vs-plain, e-xtest-mihomo-ss-src]
      note: "配置层不报错(弱类型 decoder), 但连 reality 服务端必失败; 连裸 ss 服务端会成功 -> 危险"

- rule_id: singbox.protocol.shadowsocks.tls_layer
  selector: {feature: standard:security.reality, protocol: shadowsocks}
  segments:
    - range: "= 1.14.2"
      verdict: {config: UNSUPPORTED, runtime: UNSUPPORTED}
      failure_mode: hard_error
      reason_code: KERNEL_NEVER_SUPPORTED     # 数据模型里从未存在, 不是被移除
      evidence: [e-xtest-a3-fatal, e-xtest-singbox-ss-src]

# ---------- B1. vision + reality ----------
- rule_id: xray|mihomo|singbox.feature.flow_vision_reality
  selector: {feature: standard:flow.xtls-rprx-vision, protocol: vless}
  segments:
    - range: "= {26.3.27 | 1.19.32 | 1.14.2}"
      verdict: {config: SUPPORTED, runtime: SUPPORTED}
      evidence: [e-xtest-b1-xray, e-xtest-b1-mihomo, e-xtest-b1-singbox]

# ---------- B2/B3. xhttp ----------
- rule_id: mihomo.transport.xhttp
  segments:
    - range: "= 1.19.32"
      verdict: {config: SUPPORTED, runtime: SUPPORTED}   # 含 reality / mode=packet-up
      evidence: [e-xtest-b2-mihomo, e-xtest-b3-mihomo-packetup]
- rule_id: singbox.transport.xhttp
  segments:
    - range: "= 1.14.2"
      verdict: {config: UNSUPPORTED, runtime: UNSUPPORTED}
      failure_mode: hard_error
      reason_code: KERNEL_NEVER_SUPPORTED
      evidence: [e-xtest-b2-singbox-fatal]
- rule_id: xray.transport.xhttp.xmux
  segments:
    - range: "= 26.3.27"
      verdict: {config: SUPPORTED_WITH_WARNING}
      constraints:
        - "maxConnections 与 maxConcurrency 只能二选一, 同填 -> hard_error"
        - "整个 xmux 缺省时源码取 maxConcurrency=1-1 (与 discussion #4113 写的 16-32 冲突, 待核)"
      evidence: [e-xtest-xmux-both, e-xtest-xray-xmux-src]
- rule_id: xray.transport.xhttp.plus_muxcool
  selector: {feature: standard:mux.muxcool, protocol: vless, transport: xhttp}
  segments:
    - range: "= 26.3.27"
      verdict: {config: SUPPORTED, runtime: UNSUPPORTED}
      failure_mode: runtime_fail
      reason_code: KERNEL_DOCUMENTED_CONFLICT   # #4113: 服务端只接受纯 XUDP
      evidence: [e-xtest-xhttp-muxcool, e-xray-4113]

# ---------- B4. ws + reality ----------
- rule_id: xray.transport.ws.reality
  segments:
    - range: "= 26.3.27"
      verdict: {config: UNSUPPORTED}
      failure_mode: hard_error
      reason_code: KERNEL_REMOVED_OR_RESTRICTED   # 原文 "REALITY only supports RAW, XHTTP and gRPC for now."
      evidence: [e-xtest-b4-xray-server, e-xtest-b4-xray-client]
- rule_id: mihomo.transport.ws.reality
  segments:
    - range: "= 1.19.32"
      verdict: {config: SUPPORTED, runtime: UNSUPPORTED, semantic: UNSUPPORTED}
      failure_mode: silent_noop_then_runtime_fail
      reason_code: FIELD_IGNORED_ON_THIS_TRANSPORT
      evidence: [e-xtest-b4-mihomo-ws-reality, e-xtest-b4-mihomo-controls, e-xtest-mihomo-vless-ws-src]
- rule_id: singbox.transport.ws.reality
  segments:
    - range: "= 1.14.2"
      verdict: {config: SUPPORTED, runtime: SUPPORTED}
      evidence: [e-xtest-b4-singbox-self, e-xtest-b4-singbox-tcp-reality]

# ---------- B5. ECH ----------
- rule_id: xray|mihomo|singbox.feature.ech
  segments:
    - range: "= {26.3.27 | 1.19.32 | 1.14.2}"
      verdict: {config: SUPPORTED, runtime: SUPPORTED}
      evidence: [e-xtest-b5-*]
      notes:
        - "xray: echConfigList(裸base64) / echServerKeys; allowInsecure 已被 pinnedPeerCertSha256 取代"
        - "mihomo: ech-opts{enable,config}"
        - "singbox: tls.ech.config 必须 PEM('ECH CONFIGS'), 裸 base64 -> hard_error"

# ---------- B6. mux ----------
- rule_id: xray.feature.mux
  selector: {feature: standard:mux.muxcool}
  segments:
    - range: "= 26.3.27"
      verdict: {config: SUPPORTED, runtime: SUPPORTED, uri: NOT_REPRESENTABLE}
      defaults: {enabled: false, concurrency: 8}
      semantic: {protocol_set: [mux.cool], fixed_destination: "v1.mux.cool:9527", side: client+server}
      evidence: [e-xtest-b6-ctrl-mux, e-xtest-xray-mux-src, e-xray-docs-muxobject]
- rule_id: mihomo.feature.smux
  segments:
    - range: "= 1.19.32"
      verdict: {config: SUPPORTED, runtime: SUPPORTED, uri: NOT_REPRESENTABLE}
      semantic: {protocol_set: [h2mux, smux, yamux], default_doc: h2mux,
                 fixed_destination: "sp.mux.sing-box.arpa:444", side: client}
      evidence: [e-xtest-b6-mihomo-vs-singbox, e-xtest-b6-mihomo-vs-xray, e-xtest-mihomo-smux-src]
- rule_id: singbox.feature.multiplex
  segments:
    - range: "= 1.14.2"
      verdict: {config: SUPPORTED, runtime: SUPPORTED, uri: NOT_REPRESENTABLE}
      semantic: {protocol_set: [h2mux, smux, yamux], default_doc: h2mux,
                 muxcool_client: UNSUPPORTED, muxcool_server: SUPPORTED,
                 fixed_destination: "sp.mux.sing-box.arpa:444"}
      evidence: [e-xtest-b6-singbox-self, e-xtest-b6-xray-mux-to-singbox,
                 e-xtest-b6-singbox-muxcool-fatal, e-singvmess-mux-src, e-singbox-muxcool-test]
- rule_id: cross-kernel.mux.portability
  selector: {feature: standard:mux, relationship: cross_kernel}
  verdict: {semantic: UNSUPPORTED}        # 不是"参数不同", 是协议集合/目标地址/字段语义三者都不同
  mismatch: semantic_mismatch
  evidence: [e-xtest-b6-*]

# ---------- B7. vision + none ----------
- rule_id: xray|mihomo|singbox.feature.flow_vision_without_tls
  segments:
    - range: "= {26.3.27 | 1.19.32 | 1.14.2}"
      verdict: {config: SUPPORTED, runtime: UNSUPPORTED}
      failure_mode: runtime_fail
      reason_code: FLOW_REQUIRES_TLS
      evidence: [e-xtest-b7-xray, e-xtest-b7-mihomo, e-xtest-b7-singbox]

# ---------- 复核型 ----------
- rule_id: mihomo.transport.unknown_network_value
  segments:
    - range: "= 1.19.32"
      verdict: {config: SUPPORTED_WITH_WARNING, runtime: SUPPORTED_WITH_LOSS}
      failure_mode: silent_ignore
      reason_code: FIELD_NOT_VALIDATED
      losses: ["未知 transport 名被静默当成 tcp"]
      evidence: [e-xtest-cfg-mihomo-bogus-network, e-mihomo-network-lax]
```

---

## 6. 证据条目（可直接被注册表引用）

```yaml
- id: e-xtest-a1-loopback
  type: RUNTIME_TEST
  confidence: HIGH
  date: 2026-10-10
  target: {kernel: xray, version: "26.3.27", build: "d2758a0 go1.26.1", platform: linux/amd64}
  claim: "xray ss2022(2022-blake3-aes-128-gcm) + REALITY 出站能真正建链并取回内容"
  how: "xray ss+reality 入站(dest=本地Go TLS服务端) → xray ss+reality 出站 → socks → curl 取回 COMPAT-OK-ORIGIN"
  where: "research/empirical/raw/cross-kernel-matrix-results.json#a1-xray-ss-reality"
  limits: "只证明该版本; TCP 目标; 服务端 dest 为本地 Go TLS 服务端(非真实站点); UDP 未测"
- id: e-xtest-a2b-vs-plain
  type: RUNTIME_TEST
  confidence: HIGH
  claim: "mihomo 的 ss 出站即使写了 reality-opts, 仍然只发裸 ss (连不要求 reality 的服务端成功)"
  how: "同一份 mihomo 配置打 Xray 裸 ss 服务端 -> 取回内容; 打 Xray ss+reality 服务端 -> 失败"
  where: "...#a2b-mihomo-ss-reality-vs-plain, #a2-mihomo-ss-reality"
  limits: "mihomo 1.19.32; 未测 mihomo 作为 ss+reality 服务端"
- id: e-xtest-b4-mihomo-controls
  type: RUNTIME_TEST
  confidence: HIGH
  claim: "mihomo ws+reality 失败可归因于 reality 未在 ws 分支生效, 而非 ws 或 reality 本身"
  how: "三个隔离回环: ws(无TLS)✅ / tcp+reality✅ / ws+reality❌(+ 源码 ws 分支未传 Reality)"
  where: "...#b4-singbox-server-ws-plain-mihomo, #b4-mihomo-tcp-reality-vs-singbox-server, #b4-singbox-server-ws-reality-mihomo"
  limits: "mihomo 1.19.32; 只用了 sing-box 作 reality 服务端"
- id: e-xtest-reality-8192
  type: SRC + RUNTIME_TEST
  confidence: MEDIUM
  claim: "reality 服务端 mimicry 读循环有 8192B 上限; dest 的 Certificate 记录超过它时, 已认证连接也不会完成握手"
  how: "dest=www.microsoft.com(8273B Certificate) 失败 vs 本地 Go TLS(466B) 成功; 源码 size=8192 + `if handshakeLen > size { break f }`"
  where: "...#ctrl-xray-reality-realdest, #ctrl-xray-reality; SRC: xtls/reality tls.go"
  limits: "只对 26.3.27 + 该 reality commit; 未穷举其它真实 dest"
- id: e-xtest-b6-cross-kernel
  type: RUNTIME_TEST
  confidence: HIGH
  claim: "mux 跨内核不可移植: mihomo/sing-box 的 smux 打到 xray 会被当普通域名拨号(sp.mux.sing-box.arpa) 而 DNS 失败; xray mux.cool 打 sing-box 服务端则可用"
  where: "...#b6-mihomo-smux-vs-xray-server, #b6-singbox-smux-vs-xray-server, #b6-xray-mux-vs-singbox-server"
  limits: "TCP 目标; 未测 UDP/XUDP-over-mux; 未测 mihomo 作为 mux 服务端"
```

（其余用例的 `id` 命名规则相同：`e-xtest-<case-name>`，原始 verdict/日志在
`cross-kernel-matrix-results.json` 与 `raw/logs/<case>.*.log`。）

---

## 7. UNKNOWN（显式记录，不许留空）

1. **版本边界**：本文件所有结论只覆盖 `Xray 26.3.27 / mihomo 1.19.32 / sing-box 1.14.2`。
   `ws+reality` 在 Xray 是"何时被限制的"、mihomo 的 ws+reality 是"何时坏的"、
   `allowInsecure` 的移除时点 —— 均 **UNKNOWN**（需逐版二分）。
2. **mihomo 作为 mux 服务端**：mihomo listener 是否能接收 smux/mux.cool 会话 —— 未测（无回环）。
   `xray mux.cool → mihomo listener` / `smux → mihomo listener` 都是 **UNKNOWN**。
3. **XHTTP + mux.cool 的 UDP/XUDP 路径**：#4113 说服务端"只接受纯 XUDP"，本轮只测了 TCP 目标
   （失败于 `unexpected network TCP`）。**纯 XUDP-over-mux.cool 在 XHTTP 上能否工作 = UNKNOWN**。
4. **xmux 默认值冲突**：26.3.27 源码显示缺省 `maxConcurrency=1-1`，官方 discussion #4113 §XMUX
   写 `"16-32"`。二者矛盾，未做运行期测量 → **UNKNOWN（以哪个为准待核）**。
   另外 `xmux` 的运行语义（并发是否真的被限制）本轮**没测**。
5. **ECH 的回落细节**：错密钥时客户端是"直接失败"还是"先重试再失败"、外层 SNI 是否泄露，
   本轮只有"失败"这个结果 → **UNKNOWN**（需抓包）。`echForceQuery`（DNS HTTPS RR）路径未测。
6. **UDP 覆盖**：所有回环都用 TCP 目标（`curl`）。`network: tcp,udp`、`xudp`、`uot`、
   mux 下的 UDP 行为 —— 全部 **UNKNOWN**。
7. **mihomo / sing-box 的 ss+reality 服务端方向**：mihomo 的 ss **listener** 加 reality-opts、
   sing-box 用 `shadowtls` 出站再叠 reality —— 都未测 → **UNKNOWN**（注意与 A3 的"shadowsocks
   出站没有 tls 字段"是两件事）。
8. **真实站点作 reality dest 的适用面**：只有 microsoft（失败）与本地 Go TLS（成功）两点证据，
   其它真实站点是否受 8192 上限影响 → **UNKNOWN**（本轮对 cloudflare/apple/wikipedia 等的探测
   因等待不足未得出结论，不作为证据）。
9. **mihomo ws+reality 是否存在任何可通的服务端**：源码解释了它不发 reality，故**没有**证据它能在
   任何 reality 服务端上工作，但也没穷举 → **UNKNOWN（倾向不可用，但不下断言）**。
10. **fork/发行版**：`sing-box-lx` 等 fork 未测，`unknown_distribution_policy: UNKNOWN`。

---

## 8. 清理与边界声明

- 实验全部在 `ssh rn` 的 `/tmp/xtest/` 下进行；结束时会 kill 所有本轮起的进程并删除该目录
  （**包括**手动起过的 `openssl s_server` / `python3 -m http.server` 残留）。
- **未改动** `/root/catmi/{mihomo,sing-box}` 与 `/usr/local/bin/xray` 的任何正式配置/文件；
  未重启任何既有服务（rn 上原有的 xray/nginx 监听端口不在本轮使用范围内，端口全走动态分配）。
- 复现脚本：`tools/probe/loopback_matrix.py`；本轮脚本是"数据驱动用例表 + 统一 runner"，
  新增用例只需往 `build_cases()` 里加一行。
