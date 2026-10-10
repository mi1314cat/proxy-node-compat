# Go 生态「URI 解析 + 内核配置生成」源码级调研

Phase 1.5 · 三个真实 Go 项目的源码级对比，目标是为 `proxy-node-compat` 的 **Kernel-neutral Node Profile** 找参考与反例。

| | 项目 | commit（本次调研钉死） | 规模 | License |
|---|---|---|---|---|
| **A** | [lilendian0x00/xray-knife](https://github.com/lilendian0x00/xray-knife) | `07e207ed458a9ae10c17d0dd2f5dc737c18b7dd3`（2026-09-28，444★） | module `…/xray-knife/v11`，go 1.26 | MIT |
| **B** | [mmwx-group/mmwX-plugins](https://github.com/mmwx-group/mmwX-plugins) → `proxyparser/` | `f1c2c3507f207de3b5cae15e11ae2073d1f72b4c`（2026-10-09，2★） | module `…/mmwX-plugins/proxyparser`，go 1.26 | MIT |
| **C** | [bestnite/sub2sing-box](https://github.com/bestnite/sub2sing-box) | `a97a586e4605fb22996e0663ef61ecad8d91b932`（2026-09-24，168★） | module `github.com/bestnite/sub2sing-box`，go 1.26 | MIT |

**方法与限制**

- 三个仓库全部 `git clone --depth 1` 到本地后**直接读工作区源码**（等价于 raw.githubusercontent.com 内容），并用 `grep`/行号定位。**不是读 README。**
- **本机无 Go 工具链**（`which go` → 无，`/usr/local/go` 不存在）。因此**没有编译、没有运行、没有单元测试执行**。所有"某字段被丢弃"的判断都是**静态阅读代码路径**的结论。见 §7。
- 关于 B 的仓库位置：任务给的 `MMWOrg/mmwX-plugins` 已**改名为 `mmwx-group/mmwX-plugins`**（GitHub 301 → repo id `1246280423`；`curl -sIL https://github.com/MMWOrg/mmwX-plugins` 最终落到 `mmwx-group/mmwX-plugins`）。旧路径 git clone 仍可用（GitHub 重定向），但 `go.mod` 的 module path 仍是旧的 `github.com/MMWOrg/mmwX-plugins/proxyparser`。`proxyparser` 就在**仓库顶层目录** `proxyparser/`，不是子模块化到别的仓库。
- 关于 A 的版本：任务里说"可能已到 v9"，**实际已到 v11**（`go.mod` 第一行 `module github.com/lilendian0x00/xray-knife/v11`，tags 已到 `v9.12.1` 之后有 `MIGRATION-v11.md`）。任务描述的"仓库结构可能是 `xray/` 包 + `cmd/`"**已过时**：现在是 `pkg/core/{xray,singbox,protocol,mtproto}/` + `pkg/convert/` + `cmd/`。

---

## 0. 我实际读了哪些文件

### A. xray-knife（约 90 个 Go 文件，重点读 12 个）

| 类别 | 路径 |
| --- | --- |
| 模型 | `pkg/core/xray/interface.go`（171 行，全读） |
| 中立模型 | `pkg/core/protocol/interface.go`（全读） |
| URI 解析 | `pkg/core/xray/linkutil.go`（212 行，全读）、`pkg/core/xray/vless.go`（Parse 段） |
| 能力判断 | `pkg/core/xray/protocol.go`（全读）、`pkg/core/xray/shadowsocks.go:95-200` |
| 内核选择 | `pkg/core/factory.go:90-175` |
| 导出/丢字段 | `pkg/convert/convert.go`（149 行，全读）、`pkg/convert/clash.go:45-90`、`pkg/convert/singbox.go:55-90`、`pkg/convert/xray.go:15-175` |
| CLI | `cmd/parse/parse.go:1-200` |
| 能力标记 | 全仓 grep `unsupported\|not supported\|cannot be` |

### B. mmwx-group/mmwX-plugins → proxyparser（71 个 Go 文件 / 27,896 行）

| 类别 | 路径 |
| --- | --- |
| 解析入口 | `parser.go`（2040 行；`Parse`/`ParseSubscription` 及 vless 段全读） |
| scheme 表 | `preprocess.go`（126 行，全读） |
| 别名表 | `fields.go`（57 行，全读） |
| 中立/枢纽模型 | `substore/types.go`（117 行，全读） |
| 能力闸门 | `substore/clashmeta.go:60-160`、`substore/singbox.go:40-170` |
| 未知字段 | `substore/singbox.go:249-313`（`singboxConsumedKeys` / `passthroughExtraFields`）、`substore/singbox.go:1900-1995` |
| 反向（节点→URI） | `substore/uri.go:260-310`（`preprocessProxy`）、`360-400`、`substore/v2ray.go`（全读） |
| 生产者注册 | `substore/factory.go`（全读） |
| 能力标记 | 全 `substore/*.go` grep `unsupported\|skip\|drop` |

**未逐行读**：`substore/egern.go`(1000+)、`loon.go`、`surge.go`、`qx.go`、`shadowrocket.go`、`stash.go`、`surfboard.go`、`surgemac.go`、`acl_parser.go`、`rule_generator.go`、`template_*.go`、`regex_compat.go`、`wireguard_fields.go`（只做了 grep 级扫描）。见 §7。

### C. bestnite/sub2sing-box（33 个 Go 文件）

`parser/unsupported.go`、`parser/parsers_map.go`、`parser/query.go`、`parser/error.go`、`parser/vless.go`、`parser/vmess.go`、`parser/shadowsocks.go`、`common/convert.go`（全读）、`model/options.go`、`model/convert.go`、`constant/{prefix,proxy,version}.go`、`go.mod`。未读：`parser/{tuic,hysteria,hysteria2,naive,ssh,http,socks,bandwidth,network,port}.go`、`api/`、`cmd/`。

---

## 1. 项目 A：lilendian0x00/xray-knife

一句话：**双内核（xray-core + sing-box）各自一套 struct 协议模型，加一个"能跑就跑"的自动内核选择器，导出时用 `Report` 记录节点级跳过原因。**

### 1.1 数据模型：**每内核一套自己的 struct，另有一个极扁的 `GeneralConfig`**

**主体是各自 struct，不是目标内核的 map。** `pkg/core/xray/interface.go:9` 定义：

```go
type Protocol interface {
	Parse() error
	BuildOutboundDetourConfig(allowInsecure bool) (*conf.OutboundDetourConfig, error)  // ← xray-core 的 conf 类型
	BuildInboundDetourConfig() (*conf.InboundDetourConfig, error)
	DetailsStr() string
	GetLink() string
	ConvertToGeneralConfig() protocol.GeneralConfig
}
```

同一文件里定义 `Vmess` / `Vless` / `Shadowsocks` / `Trojan` / `Wireguard` / `Socks` / `Hysteria2` 七个 struct。有两点设计值得注意：

1. **每个 struct 都带 `OrigLink string \`json:"-"\``，`GetLink()` 优先返回它**（`shadowsocks.go:127-129`：`if s.OrigLink != "" { return s.OrigLink }`）。**这是"永不丢失"的终极保险**：即使所有字段映射都有损，原始 URI 还在，可以重新解析、可以展示、可以回写。
2. **有一个"勉强算中立"的扁平 struct** `protocol.GeneralConfig`（`pkg/core/protocol/interface.go`），19 个字段全是 `string`：

```go
type GeneralConfig struct {
	Protocol, Address, Security, Aid, Host, ID, Network, Path, Port,
	Remark, TLS, SNI, ALPN, TlsFingerprint, Authority, ServiceName, Mode, Type, OrigLink string
}
```

**但它不是给"能力判断"用的，只是给"取个名字 / 打印一行摘要"用的**：`ConvertToGeneralConfig()` 在 `Shadowsocks` 里只填了 5 个字段（`Protocol/Address/ID/Port/Remark` + `OrigLink`，`shadowsocks.go:152-160`），`Shadowsocks.Plugin`（SIP003 插件，xray 不支持）**根本没进 GeneralConfig**。所以跨内核能力判断**不能**基于 GeneralConfig，它是纯粹的展示层 DTO——这一点对我们很关键（见 §5）。

**另一条重要线索：`protocol.Relayer` 接口 + `protocol.Relays(p)` 帮助函数**（`pkg/core/protocol/interface.go`）：

```go
// Relayer is implemented by a protocol that can tell whether it carries general traffic.
type Relayer interface { Relays() bool }
func Relays(p Protocol) bool { r, ok := p.(Relayer); return !ok || r.Relays() }
```

MTProto 节点实现 `Relays() → false`，`pkg/core/mtproto/mtproto.go:19` 定义 `var ErrNotProxyable = errors.New("mtproto proxies only relay Telegram traffic and cannot be used as a general outbound")`。这是全生态里**唯一一个"这个节点能不能当通用出口"的二值能力位**，而且它用**接口 + 默认值（无接口即 true）**实现——比枚举更可扩展。

### 1.2 URI 解析：**集中 dispatch + 每协议硬编码白名单，未知参数静默丢弃**

入口：`pkg/core/xray/protocol.go:23 func (c *Core) CreateProtocol(configLink string)`，`:37` 起 `switch scheme`；sing-box 侧有对称实现。**没有 URL 库解析来做 dispatch**——`factory.go` 里明确注释：

```go
// Read the scheme without url.Parse, which rejects remarks like "#100%".
scheme, _, found := strings.Cut(configLink, "://")
```

这是一个真实世界的正确做法（`#Speed 100%` 会让 `url.Parse` 报错，见 `linkutil.go` 里 `splitRemark` 的注释）。

支持的 scheme（`factory.go:120-137` 的 `selectCoreForLink`）：

| 内核 | scheme |
| --- | --- |
| sing-box only | `hysteria2`/`hy2`、`hysteria`、`tuic`、`anytls`、`ssh`、`http`/`https`（代理链接，需 host:port 且无 path） |
| xray-core | `vmess`、`vless`、`trojan`、`ss`、`socks`/`socks5`/`socks5h`、`wireguard` |
| mtproto | `mtproto`（`mtproto.IsProxyLink`） |
| 其它 | `errors.New("unsupported protocol for automatic core: %s")` |

**未知 query 参数 = 硬编码白名单，看不见、不记录。** 证据是 `pkg/core/xray/vless.go` 的 `Parse()`：一串 `query.Get(...)`，共 24 个 key（`encryption, security, alpn, fp, type, sni, host, path, extra, flow, pbk, sid, spx, pqv, headerType, serviceName, mode, allowInsecure|insecure|allow_insecure, quicSecurity, key, authority, pcs, vcn, ech`），**从不遍历 `url.Values`**。字段只在 struct 里有位置才会被读（`interface.go` 注释里还留着被注释掉的 `PublicKey/ShortIds/SpiderX`，说明作者是按需加字段的）。

**但注意：这里和 Proxylink 有一个决定性区别——`OrigLink` 始终保留**，所以"未知参数丢失"是**可恢复的**。

`linkutil.go` 里两个细节体现了对真实 URI 脏数据的处理功力，值得抄：

- `splitRemark`：先从 `#` 切开 remark 再 `url.Parse`，避免 remark 里的裸 `%` 炸掉整个链接；remark 用 `lenientUnescape` **只解码一次、且不把 `+` 当空格**。
- `rawQueryValues(raw string) url.Values`（`linkutil.go:122`）：**像 `url.ParseQuery` 但不把 `+` 变成空格**——因为 WireGuard key 是标准 base64，`+` 是有效字符。`ss` 的 2022 密钥同理。**这是一个真实存在的跨协议歧义，我们的 URI 层必须显式处理（form-encoded vs. raw），不能无脑 `QueryUnescape`。**

### 1.3 能力判断：**有！而且是三个项目里最强的——但仍然没有版本维度**

这是 A 最大的价值。**存在"某内核不支持某能力"的一等公民概念**，以"函数返回 reason 字符串，空串表示支持"的形式：

| 机制 | 位置 | 语义 |
| --- | --- | --- |
| `Shadowsocks.xrayUnsupported() string` | `pkg/core/xray/shadowsocks.go:169` | 返回"xray 为什么扛不住这个链接"，`""` = 能 |
| `xraySSMethods` 白名单 | `shadowsocks.go:160` | 明确列出 xray-core 实现的 13 个 SS cipher；注释：**"Legacy stream ciphers (aes-*-cfb, chacha20, rc4-md5, ...) and "none"/"plain" are sing-box only: xray-core rejects them."** |
| `SingboxReason(p Protocol, insecure bool) string` | `pkg/core/xray/protocol.go:66` | 反过来：判断"这个链接该去 sing-box 而不是 xray"，并把 **`--insecure` 这个运行期开关**也纳入判断 |
| `removedTransport(t)` | `protocol.go:99` | **`h2`/`http`/`quic`/`h3` → `"transport %s (removed from xray-core)"`** |
| `transportSpec.singboxReason(insecure)` | `protocol.go:107` | 传输层能力 |
| `AutomaticCore.selectCoreForLink` + `preferSingbox` | `factory.go:108` / `:149` | **内核路由**：先按 scheme 选，再看 `SingboxReason` 改选 |

`SingboxReason` 的 doc comment 本身就是一份能力矩阵：

```go
// SingboxReason reports why a parsed link should run on sing-box rather
// than xray-core, or "" when xray can carry it. insecure is the caller's
// global --insecure setting. Reasons:
//   - a transport xray-core removed (h2/http, quic),
//   - a Shadowsocks plugin or legacy stream cipher,
//   - a request to skip TLS verification: xray-core can only pin or verify,
//     so self-signed servers would always fail there. Links that pin their
//     certificate ("pcs") stay on xray, as do transports and features only
//     xray implements (xhttp, kcp, REALITY, TCP HTTP obfuscation).
```

**三个能力判断的粒度层次，全都在同一个函数族里**：协议级（mtproto 不能当出口）、传输级（h2/quic 被 xray 移除）、参数值级（SS cipher 不在白名单 / plugin 非空）。**正是我们 Capability Registry 需要的最小粒度集合。**

**但：全仓库零版本概念。** 对 `pkg/` 与 `docs/` 全部 `.go` + `.md` grep：

```
xray-core v | sing-box v | core version | version of (the )?(core|xray|sing-box) | 1\.[0-9]+\.[0-9]+ *(\+|or later|removed|since)
```

→ **零命中**。`removedTransport` 说得出"h2 被 xray 移除了"，但**说不出"从哪个版本移除"**，也无法表达"这个 sing-box 版本还不够新"。`go.mod` 里 `xray-core` / `sing-box` 只是编译期依赖，**不参与任何判断**。

**这是一个精确的、可迁移的缺口：A 有"能力维度"，无"版本维度"。**

### 1.4 丢字段：**有结构化记录（节点级），但有一个反向的"清空值"陷阱**

**正面：`pkg/convert/` 有全生态最好的丢字段报告结构**（`convert.go:43-63`）：

```go
var ErrNothingToExport = errors.New("none of the links can be exported in this format")

// Skipped is one link left out of an export.
type Skipped struct {
	Index  int    // position in the input slice
	Name   string // the link's remark, when it parsed
	Reason string
}
type Report struct {
	Converted int
	Skipped   []Skipped
}
```

包注释把设计意图写死了：

> Structured exports return a `*Report`: links that a target cannot express (an xhttp link for sing-box, TUIC for xray, MTProto for anything) are skipped with a reason instead of failing the export. When nothing at all can be exported the error is `ErrNothingToExport` and the report says why.

四个导出器都真的在填它：`ToClash`（`clash.go:81`）、`ToSingbox`（`singbox.go:75,80`）、`ToXray`（`xray.go:43,52,58,63`）、`parseAll`（`convert.go:108,112,116`）。reason 是**内核视角的自然语言**，例如 `"transport xhttp (removed from xray-core)"`、`"not an xray protocol"`、`"not a sing-box protocol"`。

**`Shadowsocks` 里还有一条"拒绝优于静默降级"的硬规矩**（`shadowsocks.go:180-184`）：

```go
func (s *Shadowsocks) BuildOutboundDetourConfig(allowInsecure bool) (*conf.OutboundDetourConfig, error) {
	// Refuse rather than connect without the plugin: the result would be
	// a false failure (or a false pass against the wrong server).
	if reason := s.xrayUnsupported(); reason != "" {
		return nil, fmt.Errorf("%s is not supported by xray-core; use the sing-box or automatic core", reason)
	}
```

**"如果内核扛不住这个节点，宁可报错，也不要生成一个能连上但行为错的配置"——这正是原则 1 的原文。**

**反面（重要）：`prune` / `removeEmptyValues` 会把"显式 false / 0 / 空串"当成"没设置"删掉。**

- `pkg/convert/xray.go:120 prune(v)` + `:143 isEmpty(v)`：递归删除 `nil / false / 0 / ""` 的 map key。它作用于**真实导出产物**（`xray.go:66 outbounds = append(outbounds, prune(generic))`）。
- `cmd/parse/parse.go:35 removeEmptyValues` 是同一逻辑的复制品（作用于 `parse --json` 的展示输出，`:167`）。
- `prune` 有**一处正确的例外处理**（`xray.go:132-139`）：slice 元素全保留，注释写着 *"Keep every element: a list's zeros can matter (WireGuard "reserved": [1, 0, 3])."* —— 说明作者**已经意识到**零值有意义，但只在 slice 这一个方向上打了补丁，**map 方向仍然丢 presence**。

对我们的意义：**A 证明了"节点级 skip + reason"是可行的最小可用形态，但它没有"字段级 loss"。** `Report` 只能说"第 3 个节点被跳过了，因为 xhttp"，**说不出"第 3 个节点导出了，但丢了 2 个字段"**。

### 1.5 对"我们的项目"的参考价值：**中高。可参考其"能力函数"形态与"拒绝优于降级"，不可参考其模型（绑 xray 的 `conf` 类型）**

- **可作参考**：`xrayUnsupported() string` / `SingboxReason(p, insecure) string` 这种"返回 reason 字符串、空串表示支持"的签名，是 Capability Registry 判定函数的直接模板（返回 `reason_code` + 可选 detail）；`Report`/`Skipped` 是兼容性结果结构的雏形；`Relayer` 的"接口 + 默认 true"是能力位的可扩展表达。
- **不能作参考**：`Vless`/`Vmess` 等 struct 直接 import `github.com/xtls/xray-core/infra/conf`，`Protocol` 接口的方法签名里就有 `*conf.OutboundDetourConfig`——**模型与 xray-core 编译期强耦合**，字段语义就是 xray 的字段语义（`HeaderType`、`QuicSecurity`、`Mldsa65Verify`、`Pcs`）。用它的模型当"内核无关 Node Profile"，等价于把 xray 的词汇表升格成宇宙真理。**这正是我们 Phase 1 在 Proxylink 上已经识别出的同一个病，只是 A 做得更干净（拆成两个内核包，而不是揉成一个扁平 struct）。**

---

## 2. 项目 B：mmwx-group/mmwX-plugins → `proxyparser`

一句话：**把任意代理 URI 解析成 clash-meta 风格的 `map[string]any`，然后一路以这个 map 为枢纽，向下游 12 个客户端格式生产者分发。**

（`parser.go:1-3` 的包注释原文：*"把各类代理节点 URI(vless/vmess/ss/trojan/hysteria2/tuic/naive 等) 解析为 clash-meta 风格的 map[string]any。零第三方依赖,供 miaomiaowu / miaomiaowux 共用。"*）

> **对文档说法的核验**：「解析为 clash-meta 风格 map」→ **确认**。「零第三方依赖」→ **基本准确但不严格**：`go.mod` 只有 `require gopkg.in/yaml.v3 v3.0.1` 一行（那是 `substore/` 子包用于 YAML 的），`parser.go`/`preprocess.go`/`fields.go` 这三个顶层文件**只用标准库**（`encoding/base64, encoding/json, fmt, net/netip, net/url, regexp, strconv, strings, unicode`）。作为对照，A 有 **22 个直接依赖（+101 间接）** 且含完整 xray-core，C 直接依赖 sing-box 本体（4 个直接依赖，其余全是传递依赖）。**论"零依赖"B 是三者中唯一接近的。**

### 2.1 数据模型：**直接产出"目标内核的 map"——三者中风险最高**

```go
// substore/types.go:5
type Proxy map[string]interface{}
```

`Parse()` 的返回类型就是 `map[string]any`（`parser.go:1830`），并且**从第一个字节起就在写 clash-meta 的 key**（`parser.go:851-861`）：

```go
node := map[string]any{
	"name": name, "type": "vless", "server": server, "port": port,
	"uuid": uuid, "udp": true,
	"tls": security == "tls" || security == "reality",
	"flow": queryParams["flow"],
	"encryption": encryption,     // ← 见下
}
```

**这条路的风险是结构性的，而且在这个仓库里已经真的发生了：**

1. **解析器必须替目标内核做决定，于是把"来源语义"和"目标语义"压成一层。** 上例里 `"tls": bool` 是把 `security` 三态（`tls`/`reality`/`none`）**压扁成布尔**，reality 的细节另挂在 `reality-opts` 里。这个 map 一旦生成，**"用户原始写了什么"和"clash-meta 需要什么"就再也分不开了**。
2. **它会写入目标内核可能不认识的 key。** `"encryption": encryption`（vless 的 `?encryption=`）被无条件写进 clash-meta 风格的 map，默认值 `"none"`。**clash-meta（mihomo）的 vless 是否有 `encryption` 字段我未验证**（§7）。如果 mihomo 不认这个 key，要么被拒载、要么被静默忽略——**两种结果都是"我们项目要检测的静默丢失"**。而这里它被**无条件注入**，连"用户是否真的写了这个参数"都不知道（见下条）。
3. **`Parse()` 签名里没有"来源/未知字段"的容身之地**——返回的是一个扁平的、已经归一化到 clash 词汇表的 map。

**最能说明问题的是 `substore/singbox.go` 的架构**（`:48-57`）：

```go
// First, convert proxies to ClashMeta format (internal)
clashMetaProducer := NewClashMetaProducer()
clashProxies, err := clashMetaProducer.Produce(proxies, "internal", &ProduceOptions{
	IncludeUnsupportedProxy: true,      // ← 在枢纽层强制关掉能力过滤
})
```

**sing-box 生产者不直接消费节点，而是先"转成 ClashMeta 格式"，再从这个 clash map 映射到 sing-box。** clash-meta map 成了**全局枢纽格式（hub format）**。后果链条非常清楚：

- sing-box 的能力判断被拆成两段（clashmeta 闸门 + singbox 闸门），`IncludeUnsupportedProxy: true` 让枢纽层**故意不做过滤**，把过滤责任推给下游；
- **凡是 clash-meta 表达不了的东西，在到达 sing-box 之前就已经没了**（sing-box 明明有更丰富的能力）；
- 反向也一样：clash-meta 能表达的、sing-box 不能表达的，靠 `delete(...)` 事后削（见 §2.4）。

**这正是我们绝不能采用的结构：一旦选定一个枢纽 schema，这个 schema 的能力上限就成了所有内核的能力上限。**

### 2.2 URI 解析：**单文件巨型 switch，未知 scheme 报错，未知参数静默丢弃**

入口极简（`parser.go:1830`）：

```go
func Parse(uri string) (map[string]any, error) {
	uri = strings.TrimSpace(uri)
	switch {
	case strings.HasPrefix(uri, "vmess://"):   return parseVmessURL(uri)
	case strings.HasPrefix(uri, "ssr://"):     return parseShadowsocksRURL(uri)
	case strings.HasPrefix(uri, "ss://"):      return parseShadowsocksURL(uri)
	case strings.HasPrefix(uri, "socks://"), strings.HasPrefix(uri, "socks5://"): return parseSocksURL(uri)
	case strings.HasPrefix(uri, "trojan://"):  return parseTrojanURL(uri)
	case strings.HasPrefix(uri, "vless://"):   return parseVlessURL(uri)
	case strings.HasPrefix(uri, "hysteria://"):return parseHysteriaURL(uri)
	case strings.HasPrefix(uri, "hy2://"), strings.HasPrefix(uri, "hysteria2://"): return parseHysteria2URL(uri)
	case strings.HasPrefix(uri, "tuic://"):    return parseTuicURL(uri)
	case strings.HasPrefix(uri, "anytls://"):  return parseAnytlsURL(uri)
	case strings.HasPrefix(uri, "miu://"):     return parseMiuURL(uri)
	case strings.HasPrefix(uri, "wireguard://"), strings.HasPrefix(uri, "wg://"): return parseWireGuardURL(uri)
	case strings.HasPrefix(uri, "http://"), strings.HasPrefix(uri, "https://"):   return parseHTTPURL(uri)
	case strings.HasPrefix(uri, "naive://"), strings.HasPrefix(uri, "naive+https://"), strings.HasPrefix(uri, "naive+http://"): return parseNaiveURL(uri)
	case strings.HasPrefix(uri, "mieru://"), strings.HasPrefix(uri, "mierus://"): return parseMieruURL(uri)
	case strings.HasPrefix(uri, "snell://"):   return parseSnellURL(uri)
	default:
		return nil, fmt.Errorf("unsupported protocol: %s", uri)
	}
}
```

**scheme 覆盖是三个项目里最广的（17 类 / 23 个前缀）**，且 `preprocess.go` 里有一份**平行维护的 `supportedSchemes` 数组**（用于 `IsSupportedURI` / `DetectContentType`）——**两份清单手工同步，是明确的漂移风险点**（我未验证二者当前是否完全一致，§7）。

`mieru://` / `mierus://` 分支上留了一条很有价值的实战注释（`parser.go:1862-1863`）：

```go
// mieru 官方客户端导出的链接用的是 mierus://(带 s),社区里两种写法都在流传。
// 只认 mieru:// 的话,官方导出的链接直接「不支持的协议」被丢掉(许可证站 #115)。
```

**"别名不全是故意的，是真实世界的客户端各写各的"——我们的规范化层必须有别名表，并记录命中了哪个别名。**

**未知参数怎么处理：静默丢弃，无记录。** `parseQueryParams`（`parser.go:37-56`）**确实把所有参数都解析进了 `map[string]string`**（比 A 的 `.Get()` 更"看得见"），但**每个 `parseXxxURL` 只用固定 key 去查表**，从不检查"剩下哪些没被用"。以 vless 为例（`parser.go:841-881`）它读了 `security, encryption, type, sni, flow, pbk/public-key, ...`，**剩下的 key 直接消失在函数返回处**。

**更严重的一处：`ParseSubscription` 静默丢弃解析失败的行**（`parser.go:1893-1905`）：

```go
if strings.Contains(line, "://") {
	proxy, err := Parse(line)
	if err != nil {
		continue        // ← 没有计数、没有原因、没有日志
	}
	proxies = append(proxies, proxy)
	continue
}
// 非 URI 行尝试按 Surge INI 行解析(目前仅 snell)
if node := parseSurgeLine(line); node != nil {
	proxies = append(proxies, node)
}
```

一个 100 行的订阅，如果 30 行是 `mieru://`（假设未来被删）、或格式有误，**返回的 `proxies` 就是 70 个，调用方无从知道少了 30 个**。对比 C 在同样场景下**明确写了"不能静默丢掉"的注释并输出到 stderr**（§3.4）——这是 B 最该被我们警惕的地方。

### 2.3 能力判断：**有"客户端兼容模式"闸门，有节点协议版本，但内核版本只在注释里**

**有"某客户端不支持某能力"的一等公民概念**，通过 `ProduceOptions` 传入（`substore/types.go:10-21`）：

```go
type ProduceOptions struct {
	IncludeUnsupportedProxy bool
	ClientCompatibilityMode bool // Auto-filter incompatible nodes for clients
	UseMihomoExternal       bool
	LocalPort               int
	...
}
```

**clash-meta 的闸门写得最完整**（`substore/clashmeta.go:96-133`，`if !opts.IncludeUnsupportedProxy { ... }`）：

```go
// Snell：对齐 Sub-Store，接受 v1–v5（仅跳过更高的未知版本；v5 需较新 mihomo 核心）
if proxyType == "snell" {
	version := GetInt(proxy, "version")
	if version > 5 { continue }
}
// Skip juicity and naive (不被 ClashMeta 支持)
if proxyType == "juicity" || proxyType == "naive" { continue }
// Check SS cipher
if proxyType == "ss" {
	cipher := GetString(proxy, "cipher")
	if !supportedSSCiphers[cipher] { continue }
}
// Check anytls with reality or unsupported network
if proxyType == "anytls" {
	network := GetString(proxy, "network")
	if network != "" && network != "tcp" { continue }
	if network == "tcp" && IsPresent(proxy, "reality-opts") { continue }
}
// Skip xhttp network
if GetString(proxy, "network") == "xhttp" { continue }
```

`supportedSSCiphers` 是 **34 个 cipher 的白名单**（`clashmeta.go:45-81`，含 mihomo 特有扩展 `lea-*-gcm` / `rabbit128-poly1305` / `aegis-128l/256` / `aez-384` / `deoxys-ii-256-128` / `rc4-md5` / `none`），`supportedVMessCiphers` 是 5 个。**这正是 Capability Registry 的 cipher 表该有的样子——只是它是硬编码在生产者里的，不是数据驱动的注册表。**

sing-box 侧闸门（`substore/singbox.go:70-160`）粒度更细，明确到"协议 × 参数值"：

| 判断 | 位置 | 语义 |
| --- | --- | --- |
| `socks5` + `tls` | `singbox.go:84-88` | `"platform sing-box does not support proxy type: socks5 with tls"` |
| `ssr` 需 `IncludeUnsupportedProxy` | `singbox.go:102-107` | `"platform sing-box does not support proxy type: ssr"` |
| `vmess` + network ∉ {``,ws,grpc,h2,http} | `singbox.go:109-115` | `"…proxy type: vmess with network %s"` |
| `vless` + `encryption != "" && != "none"` | `singbox.go:117-119` | **`"VLESS encryption is not supported"`** |
| `vless` + `flow ∉ {``, xtls-rprx-vision}` | `singbox.go:120-127` | 明确到 flow 值 |
| `trojan` + 非空 `flow` | `singbox.go:132-137` | |
| `tuic` + 非空 `token` | `singbox.go:139-142` | `"…TUIC v4"`（v4 用 token，v5 用 uuid/password） |
| `snell` version ∉ {0,4,5,6} | `singbox.go:1984` | `"…snell version %v"` |
| `network == "xhttp"` | `singbox.go:74-76` | 无条件 `continue`（连 `IncludeUnsupportedProxy` 都不看） |

**内核版本维度：不存在结构化表达，但 B 是三者中唯一"在代码里说出内核版本"的地方——只是说在注释里。**

全仓 grep `coreVersion|mihomo.*version|version.*(support|require|min)|semver` 只命中 4 处，全部是**节点协议版本**（shadow-tls version 1/2/3、snell version）：

- `substore/egern.go:247,257` — `"shadow-tls version %d is not supported"`
- `substore/loon.go:880` — 同上
- `substore/surge.go:785` — 注释 *"Note: version < 2 is not supported, but we don't error here"*
- `substore/clashmeta.go` — snell `version > 5` 跳过

而唯一的"内核版本"信息是**注释**：*"v5 需较新 mihomo 核心"*（clashmeta.go，snell 分支）。**它说明"snell v5 需要某个较新的 mihomo"，但没有任何机器可读的版本数据。"较新"是关键词——这正是 UNKNOWN 该出现的位置，而它被写成了注释。**

另有一处揭示了"客户端能力"的第三种状态（`substore/singbox.go:14-16, 1676-1683`）：

```go
// includeUnsupported 记住本次 Produce 的 include-unsupported-proxy 开关。
// sing-box 有一批字段只有非官方版认(client_name / quic_proxy_mode / certificate_server_name),
// 上游把它们挂在这个开关后面,官方版才不会收到不认识的字段。
```

**"官方版 vs 非官方版"是比"内核 + 版本"更细的一层能力维度**，而它用**一个布尔开关**表达。我们的 Registry 迟早要面对"同一内核不同分支/构建"的问题，这里是真实证据。

### 2.4 丢字段：**两种极端策略并存——盲目透传 与 严格白名单——加上"presence 归零"**

B 在这件事上的做法**自相矛盾**，而这个矛盾本身极有信息量：

**(a) 默认策略：盲目透传（blind passthrough）** — `substore/singbox.go:302-313`：

```go
func (p *SingboxProducer) passthroughExtraFields(proxy Proxy, parsed map[string]interface{}) {
	for key, value := range proxy {
		if singboxConsumedKeys[key] { continue }
		sbKey := strings.ReplaceAll(key, "-", "_")
		if _, exists := parsed[sbKey]; exists { continue }
		parsed[sbKey] = value
	}
}
```

**节点 map 里所有"生产者没消费"的 key，会被改名（`-` → `_`）后原样塞进 sing-box 出站。** 调用点注释（`singbox.go:1676-1679`）说明了理由：`client_name` 这类非官方字段要挂在开关后面，*"免得官方版收到不认识的字段"*。

这是**"宁可透传也不丢弃"**的立场，方向正确。但：
- 它是**无条件的**——不区分"这个 key 是 clash 标准字段"还是"用户手写的垃圾"；
- 它**假定 key 命名只差 `-`/`_`**（`strings.ReplaceAll`），clash→sing-box 的真实差异远不止分隔符（`skip-cert-verify`→`tls.insecure`、`ws-opts`→`transport`）；
- **没有任何记录**：透传了哪些 key、哪些被 `singboxConsumedKeys` 挡下、哪些同名的被 `if exists { continue }` 覆盖，全部无痕。

**(b) 例外：WireGuard 严格白名单** — `substore/singbox.go:1916-1946`：

```go
// 只留 sing-box WG endpoint 认识的字段。旧的 server/server_port/peer_public_key/
// pre_shared_key/reserved(出站写法,1.13 起已移除)、network、multiplex 都不在其中,
// 写出去官方 sing-box 会整份拒载。
for key := range parsed {
	if !singboxWireGuardEndpointKeys[key] { delete(parsed, key) }
}
```

`singboxWireGuardEndpointKeys`（`singbox.go:1934`）是一张 **36 个 key 的白名单**，注释里甚至写清了字段来源（*"sing-box option/endpoint.go、option/wireguard.go、option/outbound.go 的 DialerOptions"*）。**这是一张真正手工对齐内核 schema 的表——也正是我们 Registry 该数据化的东西。**

**同一个文件里，一边"什么都透传"，一边"只留 36 个"，规则不同、都不记录。** 注释里的理由是真实的：**透传会让官方 sing-box "整份拒载"（拒绝加载整个配置）**。也就是说 B 是在两个灾难之间做局部选择：**透传可能炸整个配置，丢弃会静默损能力**——它按协议逐个手工决策，没有统一原则。**我们的项目存在的理由，就是把这种"逐个手工决策"变成"注册表 + 显式 loss 报告"。**

**(c) presence 被归零（与 A 同病，但更隐蔽）** — 三处：

1. `substore/uri.go:260 preprocessProxy`：

```go
// Remove null/empty values
for key := range processed {
	if processed[key] == nil || processed[key] == "" { delete(processed, key) }
}
```

2. `parseVlessURL` 里 `skip-cert-verify` 的**默认值注入**（`parser.go:875-877`）：

```go
// Skip cert verify（统一别名）
scv, _ := skipCertVerify(queryParams)   // ← 第二个返回值 present 被丢弃
node["skip-cert-verify"] = scv          // ← 无论用户有没有写，都写入一个 bool
```

`skipCertVerify` 的签名是 `(val bool, present bool)`，`fields.go` 里专门解释了 `present` 的用途（*"存在但全为假 → (false,true);全部不存在 → (false,false)"*）——**作者设计了三态，调用点把它压成两态**。后果：**下游再也分不清"用户明确写了 `insecure=false`"和"用户根本没提这件事"**。

3. `ParseSubscription` 的静默 `continue`（§2.2）。

**(d) 反向（节点 → URI）也无损性保证** — `substore/v2ray.go:34-45`：

```go
for _, proxy := range proxies {
	uri, err := p.uriProducer.ProduceOne(proxy)
	if err != nil {
		// Skip proxies that cannot be encoded
		// In production, you might want to log this
		continue
	}
	uris = append(uris, uri)
}
```

**`// In production, you might want to log this` —— 一句注释，承认了这是未完成的 TODO。** 这正是"绝不静默丢失"原则要禁止的形态：**已知会丢，但只有源代码注释知道。**

### 2.5 对"我们的项目"的参考价值：**中。是"枢纽 map 反模式"最好的一手证据，但它的能力闸门值得抄**

- **最有价值的**：§2.3 的三张闸门（SS cipher 白名单 34 项、vmess cipher 白名单 5 项、协议×参数值判断）**就是 Kernel Capability Registry 的形状**，只是硬编码、没有数据化、没有版本维度。我们应把它**外化成数据**，并补上版本门槛（`singbox.go:1984` 那种 `version ∉ {4,5,6}` 的写法需要变成 `{version: 4, minKernel: "x.y.z"}`）。
- **最有价值的反面教材**：`substore/singbox.go:48-57` 的"先转 ClashMeta 再转 sing-box"。**任何单一枢纽 schema 都会成为所有内核的能力天花板。** 我们的 Node Profile 必须是"能力集合 + 逐内核映射"，**不是"一个格式的 map"**。
- **值得抄的**：`parser.go:1862-1863` 那种"别名是真实世界的现实"的注释与处理；`preprocess.go` 的 `ContentKind` 内容嗅探（HTML / ClashYAML / URIList / Unknown，`DetectContentType`）；`Preprocess` 返回 `(proxies, kind, decoded, err)` 四元组把"这是什么"和"我解出了什么"分开。
- **必须拒绝的**：`map[string]any` 作为节点模型的载体。它**没有 presence 概念**（Go map 的零值 = `nil`，与"存在但为假值"不可分，这是 §2.4(c) 的根因）、**没有来源标记**（哪一层写的？URI 还是模板？）、**没有未知字段容器**（未知 key 混在已知 key 的同一命名空间里，靠 `strings.ReplaceAll` 猜语义）。

---

## 3. 项目 C：bestnite/sub2sing-box

一句话：**订阅 → sing-box 单向转换；数据模型就是 sing-box 自己的 `option.Outbound`；对已知的不支持格式给出带内核版本号的原因，但对真正陌生的输入保持沉默。**

（README 描述：*"将节点和订阅转换为 sing-box 配置"*；`go.mod` 钉 `github.com/sagernet/sing-box v1.15.0-alpha.7` + `github.com/sagernet/sing v0.9.6-0.20260922013359-4ca3bebe0b8e`。）

### 3.1 数据模型：**直接产出目标内核的 struct，零中立层**

```go
// model/options.go:73
type Outbound option.Outbound

// model/options.go:74-76
func (o *Outbound) MarshalJSON() ([]byte, error) {
	return badjson.MarshallObjects((*option.Outbound)(o), o.Options)
}
```

`option` 是 `github.com/sagernet/sing-box/option`。所以：

- **`model.Outbound` 就是 sing-box 的出站类型本身**，`Options` 字段装的是 `option.VLESSOutboundOptions` / `option.ShadowsocksOutboundOptions` / `option.VMessOutboundOptions` …（见 `parser/vless.go` 的 `outboundOptions := option.VLESSOutboundOptions{...}`）。
- `MarshalJSON` 走 sing-box 自己的 `badjson.MarshallObjects`（因为 sing-box 的 option 结构体把真实字段藏在 `json:"-"` 的 `Options` 里，需要自定义编码器）。

**这比 B 的 map 更进一步：连"像不像内核格式"都不用问了，它就是内核格式。** 风险也到顶：

1. **字段名、字段类型、字段存在性、默认值全部由编译期依赖的 sing-box 版本决定。** `go.mod` 里 `v1.15.0-alpha.7` 是一个 **alpha**。升级依赖会**静默改变**解析器能表达的能力集合。
2. **`common/convert.go` 里有一段注释，把"依赖内核类型"的具体代价写得很清楚**：

```go
// marshalOutbound 用 sing 的 context 编码器序列化出站。
// 必须传指针：model.Outbound 的 MarshalJSON 定义在指针接收者上，
// 序列化值副本会退化成结构体编码、丢掉 json:"-" 的 Options，
// 结果只剩 type+tag —— 输出里没有服务器信息，去重时还会把不同服务器但同名的节点当成重复节点。
```

**"传值 → 丢掉全部 Options → 只剩 type+tag"**：模型和内核类型绑死到这种程度，以至于**一个 `&` 的遗漏就会静默产生空节点**。这是一个绝佳的论据，说明**为什么我们的 Node Profile 不该是某个内核的 struct**。
3. **没有 Node 身份、没有来源、没有未知字段槽。** `model.Outbound` 只有 `Type` + `Tag` + `Options`。

### 3.2 URI 解析：**map 注册表 + 独立的"已知不支持"表，未知 scheme 报错**

入口（`common/convert.go`）：

```go
func ConvertCProxyToSProxy(proxy string) (model.Outbound, error) {
	for prefix, parseFunc := range parser.ParserMap {          // ← Go map，迭代顺序随机
		if strings.HasPrefix(proxy, prefix) {
			proxy, err := parseFunc(proxy)
			if err != nil { return model.Outbound{}, err }
			return proxy, nil
		}
	}
	if reason, unsupported := parser.UnsupportedReason(proxy); unsupported {
		return model.Outbound{}, &parser.ParseError{
			Type: parser.ErrUnsupportedProxy, Message: reason, Raw: proxy,
		}
	}
	return model.Outbound{}, errors.New("unknown proxy format")   // ← 无原因的兜底
}
```

`parser.ParserMap`（`parser/parsers_map.go`）15 个前缀 → 14 个解析函数：`ss`、`vmess`、`trojan`、`vless`、`hysteria`、`hysteria2`/`hy2`、`socks`、`anytls`、`tuic`、`ssh`、`naive+https`、`naive+quic`、`proxy-http`、`proxy-https`。

**几个观察：**

- **`for prefix := range map` 的迭代顺序在 Go 里是随机的。** 这里恰好没有互相前缀包含的 scheme，所以当前无害；但这是一个**脆弱的隐式不变量**（对比 A 的显式 `switch`：顺序可读、可测）。
- **`proxy-http://` / `proxy-https://` 而不是 `http://`** —— 一个聪明的设计：避免把普通 URL 误判成节点（A 用 `singbox.IsHTTPProxyLink` 显式校验 host:port 无 path 来达到同样目的，见 `factory.go:128-134`）。
- **错误类型是结构化的**（`parser/error.go`）：

```go
type ParseError struct {
	Type    ParseErrorType
	Message string
	Raw     string
}
const (
	ErrInvalidPrefix             ParseErrorType = "invalid url prefix"
	ErrInvalidStruct             ParseErrorType = "invalid struct"
	ErrInvalidPort               ParseErrorType = "invalid port number"
	ErrInvalidNetworkBytesCompat ParseErrorType = "invalid network bytes compat"
	ErrUnsupportedProxy          ParseErrorType = "unsupported proxy type"
)
```

**这是三个项目里最好的错误模型**：`ErrUnsupportedProxy`（客观不支持）与 `ErrInvalidStruct` / `ErrInvalidPort`（输入有问题）**在类型层面分开**——正是我们需要的"明确不支持" vs "解析失败"分层。而且 `Raw` 保留了原始串。

**未知参数处理：硬编码白名单，丢弃。** `parser/vless.go` 一口气读 12 个：

```go
query := link.Query()
uuid := link.User.Username()
flow, security, alpnStr, sni, insecure, fp, pbk, sid, path, host, serviceName, _type :=
	query.Get("flow"), query.Get("security"), query.Get("alpn"), query.Get("sni"),
	query.Get("allowInsecure"), query.Get("fp"), query.Get("pbk"), query.Get("sid"),
	query.Get("path"), query.Get("host"), query.Get("serviceName"), query.Get("type")
```

没有任何遍历、没有未知计数。`parser/query.go` 提供了 `queryGetFirst`（多别名取第一个非空）和 `queryGetBool`，**但 vless 解析器没用这些帮助函数**——直接用 `query.Get`，于是别名支持在各协议间不一致（如 `insecure` 只认 `allowInsecure`，不认 `insecure`/`allow_insecure`/`skip-cert-verify`；对比 B 的 `fields.go` 有完整的 6 个别名表）。

**silent drop 的具体点（vless，`parser/vless.go`）：**

| 输入 | 行为 | 后果 |
| --- | --- | --- |
| `type=xhttp` / `type=kcp` / `type=tcp`+`headerType=http` | 只有 `ws`/`quic`/`grpc`/`http` 四个 `if`，其余**无 else，Transport 保持 nil** | **静默降级为裸 TCP** —— 节点"能导入、能启动、就是不通" |
| `security` ∉ {`tls`,`reality`}（含 `none`、拼错的值） | 两个 `if` 都不进，**TLS 完全不设置** | 静默无 TLS |
| `allowInsecure=true`（而非 `1`） | `insecureBool := insecure == "1"` | **静默变成 false**（"跳过证书校验"被吞） |
| `alpn=h2`（单值） | `if strings.Contains(alpnStr, ",") { split } else { alpn = nil }` | **单值 ALPN 静默丢弃** |
| 其余未知 query | 不读 | 静默丢弃 |

`parser/vmess.go` 同样的形状：只 `if vmess.Net == "ws"` / `"quic"` / `"grpc"` / `"h2"` 四个分支，`vmess.Tls == "tls"` 才设 TLS，无 else。

### 3.3 能力判断：**有"已知不支持"表，且是三个项目里唯一带内核版本号的——但版本号是散文**

**`parser/unsupported.go` 是全生态最有参考价值的一个文件**（我建议整段抄进我们的 Registry 设计讨论）：

```go
// unsupportedProxyReasons 列出无法从分享链接转换的格式及原因。
// 这些链接必须给出明确原因，不能笼统地报 "unknown proxy format"，
// 否则用户会以为是自己链接写错了，而不是协议本身不被内核支持（或压根没有通用链接格式）。
var unsupportedProxyReasons = map[string]string{
	constant.ShadowsocksRPrefix: "shadowsocksr is not supported: the shadowsocksr outbound was removed in sing-box 1.6.0",
	constant.WireGuardPrefix:    "the wireguard outbound was removed in sing-box 1.13.0: use the wireguard endpoint instead, which sub2sing-box cannot generate yet",
	constant.WireGuardPrefixAlt: "the wireguard outbound was removed in sing-box 1.13.0: use the wireguard endpoint instead, which sub2sing-box cannot generate yet",
	constant.JuicityPrefix:      "juicity is not supported: sing-box has no juicity outbound",
	constant.SnellPrefix:        "snell has no common share link format: write the snell outbound into the template directly",
}
```

**这五条 reason 覆盖了我们需要的三种不同性质的"不支持"，而且项目自己的注释点破了这个三分：**

| 类型 | 例子 | 我们的 `reason_code` 应该长什么样 |
| --- | --- | --- |
| **内核历史上支持过、某版本移除** | `ssr` → *"removed in sing-box **1.6.0**"*；`wireguard` outbound → *"removed in sing-box **1.13.0**"* | `KERNEL_FEATURE_REMOVED`，带 `removed_in: "1.6.0"` |
| **内核从来就没有** | `juicity` → *"sing-box has no juicity outbound"* | `KERNEL_UNSUPPORTED` |
| **URI 格式本身不存在（不是内核的锅）** | `snell` → *"snell has no common share link format"* | `URI_NOT_EXPRESSIBLE`（**与内核无关**） |

**第三个尤其重要**：它证明"表达不了"可以发生在 **URI 层**而不只是内核层——这正是我们四层模型（Node Feature → URI Representation → Kernel Representation → Runtime Support）里第二层的存在理由。

**但版本号是字符串，不是数据。** `"removed in sing-box 1.6.0"` 这个事实**无法被程序消费**：不能用来回答"用户跑的是 1.5.0，那这个节点对他是能用的吗？"。而且这个字符串是**相对于 `go.mod` 里那个 alpha 版本硬编码的**——升级依赖时不会有人回来改它。**这是"版本维度存在但不可计算"的精确样本。**

`UnsupportedReason` 的匹配也是 `strings.HasPrefix` 遍历 map（同样随机序，同样没有前缀包含冲突）：

```go
func UnsupportedReason(proxy string) (string, bool) {
	for prefix, reason := range unsupportedProxyReasons {
		if strings.HasPrefix(proxy, prefix) { return reason, true }
	}
	return "", false
}
```

### 3.4 丢字段：**节点级有记录（写到 stderr），字段级完全没有；且"真未知"仍然静默**

**正面：`ConvertSubscriptionsToSProxy` 是三个项目里唯一对"订阅里丢了节点"做了显式处理的**（`common/convert.go`）：

```go
unsupportedLinks := make(map[string]int)
...
if !matched {
	if reason, unsupported := parser.UnsupportedReason(p); unsupported {
		unsupportedLinks[reason]++
	}
}
...
// sing-box 没有对应出站的链接（如 shadowsocksr）不能静默丢掉，
// 但也不该让整份订阅转换失败：只跳过，并把原因写到 stderr。
reasons := make([]string, 0, len(unsupportedLinks))
for reason := range unsupportedLinks { reasons = append(reasons, reason) }
sort.Strings(reasons)
for _, reason := range reasons {
	fmt.Fprintf(os.Stderr, "skipped %d unsupported proxy link(s): %s\n", unsupportedLinks[reason], reason)
}
```

**这是"绝不静默丢失"的一次真实、有意的实践**，三个细节都做对了：**按 reason 聚合计数**、**排序保证输出稳定**、**降级到 stderr 而不是让整批失败**，并且注释明确写出"不能静默丢掉，但也不该让整份订阅转换失败"这个**取舍**。

**但这个保护有精确的漏洞**：`if !matched { if UnsupportedReason(...) { count++ } }` —— **一个既不匹配 `ParserMap`、也不在 `unsupportedProxyReasons` 里的行，两个 `if` 都不进，被彻底静默丢弃**。讽刺的是，同一个文件里的单节点入口 `ConvertCProxyToSProxy` 对同样的情况会返回 `errors.New("unknown proxy format")`。**批量路径比单节点路径更不安全**——而这正是 `unsupportedProxyReasons` 的 doc comment 想避免的事（*"不能笼统地报 unknown proxy format"*）在批量路径上复发。

**字段级 loss：完全没有。** 全仓没有任何"这个节点转换成功但丢了 N 个字段"的概念。`Convert()` 的返回是 `(string, error)`——**一个 JSON 字符串和一个 error，没有任何诊断载体**（对比 A 的 `Report`）。

**格式化输出侧同样是静默丢弃**（`common/convert.go`）：

```go
tagSet := make(map[string]bool)
for i := range outbounds {
	tag := outbounds[i].Tag
	if _, exists := tagSet[tag]; exists {
		count := 1
		for { newTag := fmt.Sprintf("%s %d", tag, count); ... }
	}
	// 必须登记已用过的 tag，否则重复 tag 永远检测不到，
	// 生成的配置会被内核拒绝：duplicate outbound/endpoint tag: US 01
	tagSet[tag] = true
}
```

**这处注释是"内核会拒绝"这一类失败的最佳例证**：重名 tag 会让 sing-box **整份拒载**（不是丢一个节点）。所以"生成配置"这类项目必须区分两种失败——**内核拒载（响亮）** vs **内核静默忽略（致命）**。B 在 WireGuard 白名单那里也踩到同一件事（*"写出去官方 sing-box 会整份拒载"*）。

去重逻辑也值得一提（`common/convert.go`）：用 `marshalOutbound(&outbounds[i])` 的**完整 JSON** 作为去重键，注释写明 *"去重键必须包含出站的完整配置，不能只剩 type+tag：否则不同服务器但同名的两个节点会被当成重复节点丢掉。"* —— **同样是"传值丢 Options"那个坑的下游后果**。

### 3.5 对"我们的项目"的参考价值：**高（作为反面样本与 reason 分类模板），但模型完全不可用**

- **`parser/unsupported.go` 的注释与三分法直接可用**：它把"内核移除 / 内核没有 / URI 表达不了"分开，且要求每条都给具体原因。我们把它的 `map[string]string` 升级为 `map[scheme]CapabilityGap{kind, removed_in, message}` 即可。
- **`ParseErrorType` 的枚举直接可用**：`ErrUnsupportedProxy` vs `ErrInvalidStruct` vs `ErrInvalidPort` 是"这个节点不支持"与"这个链接是坏的"的类型级分离。
- **"跳过但计数 + 稳定排序 + stderr"的批量降级模式可直接用**（并把漏洞补上：**未匹配的兜底也要计数**）。
- **完全不可用**：`model.Outbound = option.Outbound`。它把节点模型与一个 **alpha 版本**的 sing-box 编译期绑死，连"传值 vs 传指针"都能静默产生空节点（`common/convert.go` 的 `marshalOutbound` 注释）。**用它当 Node Profile 等于把 sing-box 的 schema 变成我们的事实标准。**

---

## 4. 横向对比

| 维度 | A. xray-knife | B. proxyparser | C. sub2sing-box |
| --- | --- | --- | --- |
| **数据模型** | 每内核一套 struct（`pkg/core/xray`、`pkg/core/singbox`）+ 展示用扁 `GeneralConfig` | `map[string]any`（clash-meta 风格），**且是全局枢纽格式** | `type Outbound option.Outbound`——**就是 sing-box 的 struct** |
| **模型与内核耦合** | 编译期绑 `xray-core/infra/conf`（仅 xray 侧） | 绑 clash-meta 的**字段名约定**（无编译依赖） | 绑 `sing-box/option`（v1.15.0-**alpha**.7） |
| **原始 URI 保留** | ✅ **每个 struct 都有 `OrigLink`，`GetLink()` 优先返回** | ❌ 无 | ❌ 无（`ParseError.Raw` 只在错误路径） |
| **scheme 数** | 13（xray 7 + singbox 6 + mtproto） | **23 个前缀 / 17 类（最多）** | 15 个前缀 / 14 类 |
| **未知 scheme** | error `unsupported protocol for automatic core` | error `unsupported protocol: %s` | error `unknown proxy format` + 独立 `UnsupportedReason` 表 |
| **未知 query 参数** | 硬编码白名单（~24 key），**不记录但有 `OrigLink` 兜底** | 解析进 map 后按 key 查表，**不记录、无兜底** | 硬编码白名单（~12 key），**不记录、无兜底** |
| **能力判断** | ✅✅ **最强**：`xrayUnsupported()` / `SingboxReason()` / `removedTransport` / `Relayer`，含**参数值级**（SS cipher 白名单）与**运行期开关**（`insecure`） | ✅ 有闸门：`IncludeUnsupportedProxy` / `ClientCompatibilityMode`，含 **34 项 SS cipher 白名单**、协议×参数值判断 | ✅ 有：`unsupportedProxyReasons` 表 + `ErrUnsupportedProxy` 错误类型 |
| **内核版本维度** | ❌ **零** | ⚠️ 仅注释（*"v5 需较新 mihomo 核心"*）+ 节点协议版本（snell v1-5、shadow-tls v1-3） | ⚠️ **有版本号但是散文**：*"removed in sing-box **1.6.0**"* / *"**1.13.0**"* |
| **节点级 loss 报告** | ✅ `Report{Converted, Skipped[]}`，4 个导出器都在填 | ⚠️ 部分（生产者 `continue`，多数无记录） | ✅ 订阅路径按 reason 计数 → stderr（**有漏洞**：真未知不计数） |
| **字段级 loss 报告** | ❌ | ❌ | ❌ |
| **静默丢失点** | `prune`/`removeEmptyValues` 删 `false/0/""` | `ParseSubscription` `continue`；`preprocessProxy` 删 `nil/""`；`V2RayProducer` 的 TODO 注释 | vless/vmess 未知 transport → 裸 TCP；单值 ALPN；`insecure == "1"` |
| **presence 三态** | ❌ 被 `isEmpty` 压平 | ❌ 被 `preprocessProxy` + **`scv, _ :=` 丢弃 present** 压平 | ❌ 结构性缺失（内核 struct 用零值） |
| **逃逸舱/未知容器** | ✅ `OrigLink`（最有效的一个） | ⚠️ `passthroughExtraFields` 盲目透传（会炸官方版） | ❌ |
| **"拒绝优于降级"** | ✅✅ `shadowsocks.go:180` *"Refuse rather than connect without the plugin"* | ⚠️ 部分（`include-unsupported` 开关全有全无） | ⚠️ 单节点报错、批量静默 |
| **测试** | ✅ 大量 `_test.go`（含 fuzz、e2e、golden fixtures） | ✅ 大量 `_test.go` | ✅ 有 `*_test.go` |

**三个项目共同的、100% 一致的缺口——这就是我们的机会窗口：**

1. **没有任何一个项目有结构化的内核版本模型。** A 完全没有；B 只在注释里；C 有版本号但是不可计算的自然语言字符串。
2. **没有任何一个项目有字段级 loss 报告。** 全部止步于"节点级跳过 + 一句 reason"。
3. **没有任何一个项目区分"字段不存在"与"字段等于零值"。** A 用 `isEmpty` 主动抹平；B 用 `preprocessProxy` 抹平并在调用点丢弃 `present`；C 因内核 struct 而结构性不存在。
4. **没有任何一个项目保留"未知参数"的原始集合。** 只有 A 保留整条 `OrigLink`（**这是唯一真正有效的无损兜底**）。

---

## 5. 对 Node Profile 设计最有价值的 3 点

### ① 「能力判定函数」的正确签名：返回 reason，空串表示支持（来自 A）

A 的三层判定函数族是我们 Registry 判定 API 的直接模板：

```go
func (s *Shadowsocks) xrayUnsupported() string   // "" = 支持；否则是原因
func SingboxReason(p Protocol, insecure bool) string
func removedTransport(t *transportSpec) string
```

**优点**：(a) 支持是**默认路径**，不支持才需要写代码，不会漏；(b) 返回值天然就是给用户看的原因，不需要另建 message 表；(c) `SingboxReason(p, **insecure**)` 把**运行期配置**（`--insecure`）纳入能力判断——**证明"节点能否完整使用"不只取决于节点和内核，还取决于用户当下的运行选项**，这是我们的判定引擎必须接受的第三个输入维度。

我们的对应形态应该是 `func Judge(profile NodeProfile, kernel KernelRef, runtime RuntimeOptions) Verdict`，其中 `Verdict` **必须携带 `reason_code` 而不是只有字符串**（把 A 的 `string` 升级成 `struct{Code, Detail, RemovedIn, LossFields[]}`）。

### ② 「内核移除过某能力」是最需要一等公民表达的兼容性类型（来自 C）

C 的 `parser/unsupported.go` 是唯一说出内核版本号的地方，哪怕只是散文：

```
"shadowsocksr is not supported: the shadowsocksr outbound was removed in sing-box 1.6.0"
"the wireguard outbound was removed in sing-box 1.13.0: use the wireguard endpoint instead"
```

**这揭示了一个我们的兼容性状态机必须有的状态**：不是简单的 `SUPPORTED` / `UNSUPPORTED`，而是**版本依赖的三态**——

- 内核版本 < 移除点：**SUPPORTED**（老内核反而能用！）
- 内核版本 ≥ 移除点：`REMOVED`，且 reason 必须点名版本
- 内核版本 UNKNOWN：**UNKNOWN**（按原则 2，不猜）

**"老内核反而支持"这件事，只有把版本做成数据才能回答**，而三个项目没有一个能回答。这是 `Kernel Capability Registry` 含版本维度的最强论据。

C 还给出了 **reason 必须分类**的三分法（我在 §3.3 表格化了）：`KERNEL_FEATURE_REMOVED` / `KERNEL_UNSUPPORTED` / `URI_NOT_EXPRESSIBLE`。第三类特别重要——**它把"损失"归因到 URI 层而不是内核层**，正是我们四层模型第二层的职责。

### ③ 保留原始输入是成本最低、收益最高的无损兜底（来自 A 的 `OrigLink`）

A 的每个协议 struct 都有 `OrigLink string \`json:"-"\``，`GetLink()` 的第一行就是：

```go
func (s *Shadowsocks) GetLink() string {
	if s.OrigLink != "" { return s.OrigLink }
	...  // 只有在没有原文时才重建
}
```

**价值**：三个项目都证实"解析时的未知参数丢失"是普遍且难以根治的（白名单模式无处不在）。**但保留原始串让这个损失变成"可恢复的"**：可以重新解析、可以原样透传给客户端、可以在发现新能力时回填、可以做 round-trip 校验。

**对我们的直接要求**：`NodeProfile` 必须带上：

- `raw_uri`（原始分享链接，逐字节）
- `raw_params[]`（解析出的**全部** query 键值对，含未消费的）
- `unconsumed_params[]`（**本次解析未使用的** key，显式列出而不是留给读者推断）
- `source`（这个字段来自 URI / 订阅模板 / 用户手改？）

**只有 B 的 `parseQueryParams` 真的把全部参数解析进了 map（然后丢了）——我们要做的是"解析后不丢"，而不是"不解析"。** B 离正确只差一步。

---

## 6. 最该避免的 2 点

### ① 用任何一个内核的 schema 当枢纽格式（B 和 C 都踩，形式不同）

**B 的形式**：`map[string]any` + clash-meta key 约定，并且 **sing-box 生产者要先"转成 ClashMeta 格式"再由它映射**（`substore/singbox.go:48-57`）：

```go
// First, convert proxies to ClashMeta format (internal)
clashMetaProducer := NewClashMetaProducer()
clashProxies, err := clashMetaProducer.Produce(proxies, "internal", &ProduceOptions{
	IncludeUnsupportedProxy: true,
})
```

**C 的形式**：`type Outbound option.Outbound`——连 map 都不需要，直接就是内核类型。

**为什么必须避免**（三个独立的实证理由）：

1. **枢纽 schema 的能力上限 = 所有内核的能力上限。** B 的 clash-meta 枢纽表达不了 sing-box 独有的能力，于是这些能力在到达 sing-box 生产者之前就没了（反之亦然）。B 被迫用 `IncludeUnsupportedProxy: true` 在枢纽层"关掉过滤"，这是**承认枢纽层在做错误的判断**的症状。
2. **耦合到内核的编译期契约会把 bug 藏起来。** C 的 `marshalOutbound` 注释：传值 vs 传指针 → **丢光 `json:"-"` 的 Options → 输出只剩 `type`+`tag`**，且"去重时还会把不同服务器但同名的节点当成重复节点"（`common/convert.go`）。**一个 `&` 的遗漏，静默产生空节点。** 这正是我们项目要防的失败模式。
3. **内核 schema 会漂移，而模型不会自动跟上。** C 钉的是 `sing-box v1.15.0-alpha.7`；B 的 `supportedSSCiphers`（34 项）和 `singboxWireGuardEndpointKeys`（36 项）是手工抄内核 schema 的快照（B 的注释自己写着来源是 *"sing-box option/endpoint.go、option/wireguard.go…"*）。**这些表会腐烂，而且腐烂时没有任何信号。**

**正确形态**：Node Profile 是**内核无关的能力集合**（每个能力带 presence + 来源 + 置信度），内核侧是**独立的 Kernel Capability Registry（数据驱动，含版本）**，两者之间的映射是**显式、可测、会产生 loss 报告**的第三层。**"能不能完整使用"是映射的结果，不是模型自带的属性。**

### ② 用"零值即未设置"抹平 presence（三个项目 100% 同病，且都有明确的修正痕迹）

| 项目 | 位置 | 代码 |
| --- | --- | --- |
| A | `pkg/convert/xray.go:120,143` | `prune` / `isEmpty`：递归删 `false`/`0`/`""` 的 map key |
| A | `cmd/parse/parse.go:35` | `removeEmptyValues`：同一逻辑的复制品 |
| B | `substore/uri.go:260` | `if processed[key] == nil \|\| processed[key] == "" { delete(processed, key) }` |
| B | `parser.go:875-877` | `scv, _ := skipCertVerify(queryParams)` —— **设计了三态的 `present`，调用点丢弃** |
| C | `parser/vless.go` | `insecureBool := insecure == "1"`；内核 struct 用零值表达"未设置" |

**为什么这是致命的**：我们的第一条原则是"绝不静默丢失能力"，而**"丢了什么"的定义前提是知道"原来有什么"**。一旦 `false` 和"没写"都变成同一个字节，**loss 报告在语义上就不可能写出来**——你无法报告"丢失了 `skip-cert-verify: false`"还是"丢失了 `skip-cert-verify` 字段"。

**而且每个项目都留下了"作者知道这是错的"的证据**：

- A 在 `prune` 里为 **slice** 打了例外补丁，注释写得极好：*"Keep every element: a list's zeros can matter (WireGuard "reserved": [1, 0, 3])."* —— **知道零值有意义，但只修了一个方向。**
- A 在 `pkg/core/xray/interface.go` 的 `Shadowsocks` struct 里**没有**用 `omitempty`，但 `Vmess` 的 `Pcs`/`Vcn`/`Ech` 用了 `omitempty`——**同一项目内不一致**。B 在 `fields.go` 里**专门实现了三态**（`boolFromAliases` 返回 `(val, present)`，注释解释三态语义），**然后调用点丢弃它**。
- C 在 `common/convert.go` 里为**去重键**专门做了"必须包含完整配置"的修补，**根因仍是零值/空值不可分**。

**对我们的直接要求**：`NodeProfile` 的每个能力字段必须是**显式三态**之一——`ABSENT` / `PRESENT(value)` / `UNKNOWN`——**绝不能用 Go 零值或 Python falsy 兼任**。推荐：

- 字段用 `Optional[T]` / `*T` / 显式 `present: bool` 位图；
- 序列化时 `ABSENT` 与 `PRESENT(false)` **必须产生不同字节**（禁止 `omitempty` 一类语义）；
- **绝不允许"递归删空值"的规范化步骤存在于解析与判定路径上**（可以用在"给某个内核生成配置"的渲染边缘，且必须在那里就产生 loss 记录）。

**A 的 `isEmpty` 注释里的那半条正确直觉（"a list's zeros can matter"）应该被推广成完整原则：任何位置的零值都可能有意义，除非 Registry 明确声明该字段的零值与缺失等价。**

---

## 7. UNKNOWN

以下事项我**没有确认，不做推测**：

1. **三个项目全部没有编译、没有运行、没有执行单元测试。** 本机无 Go 工具链（`which go` → 无；`/usr/local/go` 不存在）。§1-§3 所有"某字段被丢弃""某路径静默降级"的结论**全部来自静态阅读代码路径**，没有实测输出验证。要作为硬证据需补一次 `go test ./...` + 针对性的 round-trip 测试。
2. **mihomo 对 clash proxy map 里未知 key 的行为未验证。** 这直接决定 B 在 `parseVlessURL` 里无条件写 `"encryption"` 到底是"无害冗余"还是"静默丢失/拒载"。我未查 mihomo 源码，也未实测。
3. **mihomo 的 vless 出站是否有 `encryption` 字段未验证**（与第 2 条相关）。
4. **`badjson` / `sing-box` 对未知 JSON key 的严格程度未验证**（影响 C 的输出是否会被内核拒载，也影响 B 的 `passthroughExtraFields` 的实际风险）。
5. **B 的两份 scheme 清单是否完全一致未验证**：`parser.go:1833-1870` 的 switch 与 `preprocess.go` 的 `supportedSchemes` 是手工平行维护的。我未逐项 diff，因此"漂移风险"是结构性观察，**不是已确认的现存不一致**。
6. **B 的 `substore/` 我只精读了 6 个文件**（`types.go` / `clashmeta.go` / `singbox.go` / `uri.go` / `v2ray.go` / `factory.go`）。`egern.go`(1000+ 行)、`loon.go`、`surge.go`、`qx.go`、`shadowrocket.go`、`stash.go`、`surfboard.go`、`surgemac.go` 只做了 grep 级扫描。**这些生产者的能力闸门与丢字段行为未系统调研**——只从 grep 命中看到 loon/egern 有较完整的 `"platform X does not support ..."` 报错风格（比 clashmeta/singbox 更严格，倾向报错而非 `continue`），但**未逐条核实**。
7. **C 的 `parser/{tuic,hysteria,hysteria2,naive,ssh,http,socks}.go` 未逐行读**，因此这些协议的静默丢弃点未穷举。vless/vmess/ss 三个是我读过并给出具体结论的。
8. **C 的 `common/convert.go` 之外的转换路径未追**（`api/handler/convert.go`、`cmd/convert.go`），因此"批量路径的未知 scheme 静默丢弃"这一结论只对 `ConvertSubscriptionsToSProxy` 成立，未确认 API 路径是否相同。
9. **A 的 `pkg/core/singbox/` 我只按 grep 结果抽样**（`options.go`、`shadowsocks.go`、`tuic.go` 等的 `return nil, fmt.Errorf(...)` 命中），**未系统阅读 sing-box 侧全部能力判断**。§1.3 表格里的 sing-box 侧能力只列了从 grep 看到的部分。
10. **A 的 `removedTransport` 所列 `h2/http/quic/h3` 具体是 xray-core 哪个版本移除的，未查证。** 我只确认了代码里有 `"transport %s (removed from xray-core)"` 这个字符串，**没有验证它是否符合 xray-core 的真实历史**。
11. **C 的 `unsupportedProxyReasons` 里 "sing-box 1.6.0 移除 ssr" / "1.13.0 移除 wireguard outbound" 未对 sing-box changelog 交叉验证。** 这两个版本号是代码里写的，我未独立确认真伪（若为真，它们是很好的 Registry 种子数据；若为假，则是"注释腐烂"的实例）。
12. **三个项目的 release/tag 与 CHANGELOG 未系统查看**（A 的 tags 只 `git ls-remote --tags` 看了尾部；B、C 未看）。
13. **B 的 `ClientCompatibilityMode` 字段是否在任何生产者里被真正读取未验证。** 我在 `substore/*.go` 的 grep 中未看到它的使用点，但未穷举，因此**不能断言它是死字段**。
14. **C 的 `constant/version.go`（`var Version = "dev"`）是应用版本还是参与任何内核版本判断未追**（从 grep 看是 ldflags 注入的应用版本，与内核版本无关，但未确认全部使用点）。

**UNKNOWN 条数：14。**

---

## 附：一句话结论

**A（xray-knife）给了我们"能力判定函数"的正确形态（返回 reason、含运行期开关、支持为默认路径）和"拒绝优于降级"的纪律，但没有版本维度；B（proxyparser）给了我们最全的 scheme 覆盖、最完整的别名表与 cipher 白名单，但它用 `map[string]any` 当全局枢纽格式，把 clash-meta 的能力上限变成了所有内核的上限，并且批量路径会静默丢行；C（sub2sing-box）给了我们唯一带内核版本号的 reason（虽然只是散文）和"内核移除 / 内核没有 / URI 表达不了"的三分法，但它的模型就是 sing-box 的 struct，绑在一个 alpha 版本上。三者共同证明：能力判断可以做，版本维度没人做，字段级 loss 报告没人做，presence 三态没人做。这四件事正好是我们的 Node Profile + Capability Registry 要补的全部空白。**
