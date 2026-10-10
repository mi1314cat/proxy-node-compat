# 06 · 开源生态调研与架构再定位

> 这一轮不写实现代码，只回答一个问题：**这个公共层该长什么样，才不至于重新造一个与生态不兼容的轮子。**
>
> 结论先行：**生态里已经有人把"解析"做得很好，但没有任何一个项目在做"能力判定"。**
> 而且它们的默认行为全都是**静默丢失** —— 这恰好是我们唯一真正要做的事。

---

## 1. 找到了哪些项目（以及各自解决什么）

| 项目 | 语言 | 解决的问题 | 与本项目的关系 |
|---|---|---|---|
| [Fanju6/Proxylink](https://github.com/Fanju6/Proxylink) | Go | URI/Clash YAML/Xray JSON/sing-box JSON → 统一 `ProfileItem` → 生成 Xray / sing-box 配置或回写 URI | **同赛道最近的一个**。它的模型/解析/生成/回写四件套值得细看；但它没有内核维度，且默认静默丢字段 |
| [tindy2013/subconverter](https://github.com/tindy2013/subconverter) | C++ | 订阅 → 多目标（clash/clashr/singbox/v2ray/surge/loon/quan…）配置生成 | 生态里最经典的"多目标生成"，**每个目标一个生成器**的组织方式值得借鉴；它的丢字段行为是本项目最有力的反面教材 |
| [sub-store-org/Sub-Store](https://github.com/sub-store-org/Sub-Store) | JS | 订阅管理 + 可复用处理链（operator）+ 多目标产出 | operator 管线的设计对"可扩展 feature 处理"最有参考价值（调研进行中） |
| [7Sageer/sublink-worker](https://github.com/7Sageer/sublink-worker) | JS | 跑在 Worker/Node 的轻量订阅转换 | 现代实现的对照样本（已并入 subconverter 报告） |
| [lilendian0x00/xray-knife](https://github.com/lilendian0x00/xray-knife) | Go | 链接 ↔ 配置解码、节点测速存活。**已到 v11**（不是文档说的 v9） | ⚠️ **生态里最接近我们的一件事**：它有"能力判断"（`removedTransport` 知道 h2 被 xray 移除）但**零版本维度** —— 说不出"从哪个版本移除"、也无法表达"你的 sing-box 太旧"。见 §4.5 |
| [mmwX-plugins/proxyparser](https://pkg.go.dev/github.com/MMWOrg/mmwX-plugins/proxyparser) | Go | 各协议 URI → **clash-meta 风格 `map[string]any`**，再向 12 种客户端格式分发 | 印证"生态事实标准枢纽格式 = Clash/Mihomo 风格"；**也暴露了枢纽格式的天花板**，见 §4.5 |
| [2dust/v2rayN](https://github.com/2dust/v2rayN) | C# | 客户端；同一份节点在 **Xray / sing-box 两套内核**间切换 | 生态里最接近"跨内核"的实践（调研进行中） |
| [Toperlock/sing-box-subscribe](https://github.com/Toperlock/sing-box-subscribe) | Python | 模板 + 订阅 → sing-box 配置 | 模板化生成的对照样本（调研进行中） |
| [Leadaxe/LxBox](https://github.com/Leadaxe/LxBox) | Java/Kotlin | Android 客户端，内核是 **sing-box 的 fork** `sing-box-lx` | ⚠️ 引出本报告最重要的架构修正：见 §4.3 |

> 已完成 3 份：Proxylink、subconverter + sublink-worker、xray-knife + proxyparser + sub2sing-box（见 §4.5–§4.7）。
> 仍在调研：Sub-Store、v2rayN + sing-box-subscribe；另有 sing-box 内核能力调研未回。
> §4.5 的一条结论修正了本报告 §7 的初稿。

---

## 2. 一个贯穿全生态的事实：**默认行为都是静默丢失**

这是两份已完成调研（Proxylink、subconverter）＋我们自己的真内核实验共同指向的结论。

| 项目 | 静默丢失的具体表现 | 证据 |
|---|---|---|
| **Proxylink** | transport 表达不了 → `default: return nil` → **Transport 字段被清空**，节点退化成裸 TCP | `pkg/generator/singbox.go:281-282`（我自己读过并复现了这条路径） |
| **Proxylink** | `PinSHA256 → sing-box` 无法换算 → **降级为 `tls.insecure = true`（跳过全部证书校验）**，只用代码注释说明 | `pkg/generator/singbox.go:304-310` |
| **Proxylink** | AnyTLS/TUIC → Xray：`default → nil`，输出 `outbounds: [null]` | `pkg/generator/xray.go:239-240` |
| **subconverter** | 未知参数、未知 scheme 直接丢；未知 transport 静默降级为 TCP | 报告 §A4 例子 1 |
| **subconverter** | Surge 目标默认版本会**整类吃掉** VMess/Trojan/WireGuard/Hysteria2/AnyTLS | 报告 §A4 例子 2 |
| **subconverter** | 全项目 `continue;` **49 次**，"丢节点"是常态；唯一写日志的丢弃只针对**用户显式配置的过滤器** | 报告 §A4 |
| **subconverter** | 文档里搜 `not support / unsupported / limitation / known issue / incomplete / lost / drop` → **命中 0 次** | 报告 §A5 |

**含义**：生态里"转换成功"这个词是不可信的 —— 它可能意味着"节点还在"，也可能意味着
"节点的关键能力被悄悄拿掉了"。**这正是 proxy-node-compat 存在的唯一理由。**
我们不是要再写一个转换器，而是要提供所有转换器都缺的那一层：**丢没丢、丢了什么、为什么丢**。

---

## 3. 值得借鉴的设计

1. **解析与生成的映射必须内聚**（Proxylink）：`parseQueryParams` 与 `buildQueryParams` 放同一文件、
   对称实现，URI↔模型两张映射表不会各自漂移。→ 我们的 URI 层照此组织，并且**同一份映射用于 round-trip 校验**。
2. **"故意忽略" 与 "不支持" 必须分层**（Proxylink 的 `isIgnoredSingboxOutboundType`）：
   `direct/block/dns/selector/urltest` 是**故意跳过**（不该报错、也不该计数），
   而"不认识"是另一回事。→ 我们的引擎要区分 `IGNORED` / `UNSUPPORTED` / `UNKNOWN` 三种语义。
3. **批量转换的部分失败聚合**（Proxylink `ConvertResult{Total,Success,Failed,Errors[]}`）：
   单个节点失败不中断整批，错误带节点标识。→ `check_many()` 的返回结构直接采用这个形状。
4. **格式探测责任链**（`ok=false` 表"不是我的格式，继续试下一个"vs `ok=true` 表"是我的格式，哪怕有错"）：
   订阅可能是 base64/明文/Clash YAML/sing-box JSON 的任意组合，这个语义很关键。
5. **每个目标一个生成器 + 一份过滤规则**（subconverter）：目标特性用**数据**描述（它用
   `src/config/` 的 ini + 生成器分支），不是散落的 if。→ 我们的 capability registry 就是这个思想的彻底版：
   把"目标能表达什么"从代码里挪进数据。
6. **可复用处理链 / operator**（Sub-Store，待补细节）：与我们要做的 "feature 逐个判定" 是同构的，
   如果它的管线模型足够好，我们应当借鉴其**组合方式**而不是另创一套。

---

## 4. 不能直接使用的模型（关键结论）

### 4.1 扁平封闭结构表达不了"未知/自定义能力"

Proxylink 的 `ProfileItem` 是**59 个标量字段、零嵌套、零 map、零扩展槽**的扁平结构
（`pkg/model/profile.go:6-82`）。后果：

- 新能力 = 改结构体 = 改所有解析器/生成器（封闭模型，与"架构不写死"直接冲突）
- **没有地方放未知字段** → 不认识的参数只能丢（`parseQueryParams` 是硬编码 21 个 key 的白名单，
  从不遍历 `url.Values`）
- 没有 `raw_uri` / `raw_params` / provenance → 解析器有 bug 时**无法重新解析**

### 4.2 模型被某个内核的 schema 绑死

Proxylink 直接在 `pkg/subscription/singbox_provider.go:15-21` import
`github.com/sagernet/sing-box/option`（钉 v1.13.14），字段词汇表却取自 Xray
（`h2`/`xhttp`/`finalmask`/`mldsa65Verify`/`spiderX`）。**三个内核的 schema 被转写进同一个扁平结构，
于是无法回答"这个字段是哪个内核的概念"** —— 而"哪个内核的能力"正是我们要判定的东西。

### 4.3 ⚠️ 内核不是只有"名字+版本"，还有 **发行版/fork**

`Leadaxe/LxBox`（601 star）用的内核是 **`sing-box-lx`** —— sing-box 的 fork，带
**XHTTP / AmneziaWG2 / MASQUE**（上游 sing-box 都没有，实测上游 1.14.2 对 xhttp 是
`unknown transport type`）。而且它下面还衍生出别的 fork（`Amesu-afk/sing-box-lx`、
`Dushnilin/tachyon-core`）。

**架构修正**：能力键必须是

```
(kernel, distribution/variant, version) + feature
```

而不是原方案的 `(kernel, version)`。否则同一个"sing-box 1.14.2"会给出错误结论：
上游无 xhttp，`sing-box-lx` 有 xhttp。**这对我们尤其重要** —— 我们自己产 XHTTP 节点，
用户用 LxBox 能连、用上游 sing-box 不能连。

### 4.4 "一节点一真相 + 过早归一化"

`security` 非 tls/reality 直接抹成 `""`、未知 transport 抹成 `tcp`、Clash 的 `http` 改写成 `h2`、
`hy2://` 字符串替换成 `hysteria2://` —— 全部**不可逆且无记录**。我们相反：
**归一化只能增加信息，不能替换信息**；每一次改写都要留 provenance。

---

### 4.5 枢纽格式（hub format）是一个陷阱 —— 这条修正了 §7 的初稿

`proxyparser` 把一切解析成 **clash-meta 风格的 `map[string]any`**，并把它当**全局枢纽**：
连生成 sing-box 配置时也是"先转成 clash-meta，再映射到 sing-box"。后果（子代理报告 §2.1）：

- **凡是 clash-meta 表达不了的能力，在到达 sing-box 之前就已经没了** —— 哪怕 sing-box 本身更强；
- 反向靠事后 `delete(...)` 削掉 sing-box 表达不了的东西；
- 它还会**无条件注入目标可能不认识的 key**（如 vless 的 `encryption`，默认写 `"none"`），
  而"用户到底写没写这个参数"已经无从得知。

更根本的一条：它把 `security` 的三态（`tls`/`reality`/`none`）**压扁成 `"tls": bool`**，
reality 细节另挂 `reality-opts`。map 一旦生成，**"用户原始写了什么"和"目标内核需要什么"就再也分不开**。

> **结论（对 §7 的修正）**：生态的 **字段命名** 可以对齐（互操作便宜），
> 但**绝不能把任何单内核格式（包括 clash-meta）当内部枢纽模型** ——
> 那等于把它的表达力上限变成我们的上限。内部模型必须是**超集**：
> `features[]`（能力一等公民）+ `extensions{}`（未知原样保留）+ `raw_uri`（原文），
> 各目标格式只在**最后一跳**生成，绝不回流成中间表示。

### 4.6 xray-knife：能力维度有了，版本维度没有

它是生态里唯一已经写出"某传输被某内核移除"这类判断的项目（`removedTransport`），
且有一条值得抄的硬规矩：**Shadowsocks 相关处理里"拒绝优于静默降级"**（`shadowsocks.go:180-184`）。

但全仓库对 `.go` + `.md` grep 版本相关表达 → **零命中**：
它说得出"h2 被 xray 移除了"，却说不出"**从哪个版本**移除"，也无法表达
"这个 sing-box 版本还不够新"。`go.mod` 里的 `xray-core` / `sing-box` 只是编译期依赖，
**不参与任何判断**。

→ 这精确地印证了你定的第 6 条要求（Kernel + Version）不是洁癖，而是生态真实缺口。

### 4.7 生态里已有的"能力判定雏形"——以及它们距我们还有多远

这一节是本次调研最出乎意料的收获：**能力判定不是没人做过，而是都做了一半。**

| 项目 | 它已经有的 | 它缺的 | 证据 |
|---|---|---|---|
| **xray-knife v11** | `xrayUnsupported()` / `SingboxReason(p, insecure)` / `removedTransport()`；粒度到协议级 + 传输级 + **参数值级**（SS cipher 白名单）；`Report{Converted, Skipped[]{Index,Name,Reason}}` **节点级跳过报告**，4 个导出器都在填；`OrigLink` 字段让 `GetLink()` 优先返回原文 | **零版本维度**（全仓库 grep 无命中）；报告只到节点级、没有字段级 loss；`prune`/`removeEmptyValues` 递归删 `false/0/""`，把 presence 抹平 | `pkg/core/xray/interface.go`、`shadowsocks.go:180`、`convert/xray.go:120,143` |
| **proxyparser** | `ProduceOptions{IncludeUnsupportedProxy, ClientCompatibilityMode}` + 各目标的闸门表（34 项 SS cipher 白名单、`anytls+reality`、`xhttp`、juicity/naive…）；sing-box 闸门细到 `"VLESS encryption is not supported"` | 无内核版本（唯一提到版本的是注释）；闸门是**硬编码**而非数据；未知参数解析后仍被丢 | 报告 §2 |
| **sub2sing-box** | 唯一**把版本写进代码**的项目：`unsupportedProxyReasons` 里写着 `"ssr outbound was removed in sing-box 1.6.0"`、`"wireguard outbound was removed in 1.13.0"`；订阅路径按 reason 计数+排序+写 stderr | 版本信息是**散文注释**、非结构化数据；不看内核实际版本；字段级 loss 完全没有；`allowInsecure` 只认 `"1"`（`true` 静默变 false）；`type=xhttp/kcp` → Transport 保持 nil = **静默降级为裸 TCP** | `parser/unsupported.go`、`model/options.go:73` |

**结论**：我们要做的不是"从零发明能力判定"，而是把这三家各自做了一半的东西——
**判定函数 + 闸门表 + 版本事实**——合成一张**数据化、带版本、带字段级 loss** 的表。
顺带注意 sub2sing-box 天然给出的**理由三分法**，它必须进我们的 `reason_code`：

```
内核移除    (removed in <version>)   → 版本相关：老内核反而 SUPPORTED
内核从来没有 (never existed)          → 与版本无关的 UNSUPPORTED
URI 表达不了 (no share-link form)     → 与内核无关，属于 URI 层的 LOSS
```

第三类是纯 URI 问题，跟内核毫无关系 —— 混在一起就会得出"sing-box 不支持 snell"这种错结论
（真实原因是 **snell 没有通用分享链接格式**）。

## 5. 哪些协议/能力已经有成熟实现（不必自己造）

| 领域 | 现成可用 | 我们的用法 |
|---|---|---|
| URI 解析（vless/vmess/ss/trojan/hysteria2/tuic/anytls/wireguard/socks/http） | Proxylink `pkg/parser/*`、proxyparser、subconverter、Sub-Store | **作为对照实现与测试语料来源**，不直接依赖（语言/许可/模型都不合） |
| Clash YAML / sing-box JSON / Xray JSON 互转 | subconverter、Sub-Store、sublink-worker | 同上；重点抄它们的**目标特性表** |
| 多目标生成的工程组织 | subconverter 的 `src/generator/` | 抄"目标=数据"的组织方式 |
| 节点存活/测速 | xray-knife | 我们已有自研测速，不必重复 |
| 分享链接规范本身 | SIP002 / VMess QR / 各内核文档 | 直接实现（量小且必须自己掌握） |

### 4.8 三条可直接搬进设计的外部旁证

1. **"没写" 与 "写了 false" 必须分开存** —— subconverter 已经有现成范本：`src/utils/tribool.h` 的
   `indeterminate / true / false` + `is_undef()` / `define()`。把它从**字段级升到能力级**，
   就是我们的 `PRESENT / ABSENT_EXPLICITLY / UNKNOWN_NOT_EXPRESSIBLE` 状态。
   （旁证 §4 结论：三家 Go 项目全部因为没做这件事而写不出 loss 报告。）
2. **损失只能记在返回值里，绝不能塞进客户端配置正文** —— sublink-worker 曾把
   `# <tag> - Unsupported proxy type` 写进 Surge 输出，issue #299 证明这会污染配置语法。
   → `losses[]` 属于 compat 的返回结构，不属于生成物。
3. **字段同名 ≠ 语义相同：Registry 必须建模"语义反转"** —— sing-box 的 `network: "tcp"`
   会**静默关闭 UDP**（连带 DNS hijack / fakeip / QUIC / 所有 selector 失效），
   而同一个字段在 Clash 里无害。这类"支持与否"之外的第二类问题必须进模型
   （`semantic_inversion`），否则我们会把"配置通过"当成"行为正确"。

另记两条工程实践：**UA 可以提供内核版本**（subconverter 的 `UAMatchList` / `verGreaterEqual`、
sublink-worker 的 `resolveSingboxConfigVersion`），其"解析失败就回落到一个安全的老版本（1.12）"
的兜底值得照抄；反之 subconverter `intSurgeVer` **默认 3** 导致不带 `&ver=4` 时
VMess/Trojan/WireGuard/Hysteria2/AnyTLS **整类凭空消失**（issue #643）——默认值选错就是静默丢节点。

**没有现成实现的**（= 我们的核心工作）：

- 内核 **× 发行版 × 版本** 维度的能力表
- **字段级** loss / warning / unknown 结构化输出与 `reason_code`
- **静默降级**的检测（实测 mihomo 把未知 transport 当 tcp；subconverter/Proxylink 生成时也会丢）
- **round-trip 不变量**校验（所有项目都没有测试；Proxylink 连 `*_test.go` 都没有）
- 未知/自定义/vendor feature 的一等公民表示

---

## 6. 我们的特殊需求（生态里没有对应物）

1. **组合能力**：我们的 AnyReality 是"协议 × 可叠加安全层"的组合（ss+REALITY、trojan+REALITY、
   AnyTLS+REALITY），**不是协议**。生态的模型都是"一个节点一个协议类型"，装不下组合。
2. **URI 表达力缺口要成为数据**：ss+reality 的 `ss://` 链接**物理上装不下** reality 参数
   （我们仓库里现在是用注释说明的）→ 必须进 `losses[]`。
3. **内核 fork 差异**（§4.3）。
4. **安全相关的降级必须可阻断**：Proxylink 把 `PinSHA256` 降级成"跳过证书校验"这种事，
   用户必须能被明确告知并选择拒绝 —— 我们要有 `security_downgrade: true` 标记。
5. **零网络依赖**：我们的三个客户端都要离线判断（沿用你定的原则）。
6. **我们自己的扩展**：证书钉扎（`pinned_cert_sha256`）、Browser Dialer、多出站/dialer 模式、
   ECH 相关的一整套处理（103 个文件里都有 ECH 的痕迹）。

---

## 7. Universal Node Model 应该如何吸收这些经验（初步定型）

```
NodeProfile
├── raw_uri            # 原文，永不丢（生态里普遍缺失，我们必须有）
├── protocol           # 标准协议名（词汇表对齐生态: vless/vmess/ss/trojan/hysteria2/tuic/anytls/...）
├── endpoint           # server / port
├── auth               # uuid/password/method/username... （按协议定义）
├── features[]         # ★ 能力列表（一等公民），每项:
│     ├── id           #   standard:reality / standard:xhttp / <ns>:<vendor-feature>
│     ├── params{}     #   该能力的参数（不与其他能力混在一个扁平结构里）
│     ├── source       #   uri | json | yaml | inferred   ← provenance
│     └── raw_key      #   它在原始输入里的 key（便于回写与诊断）
├── extensions{}       # ★ 不认识/未建模的字段原样存放在这里 —— 永不丢弃
└── diagnostics[]      # 解析期的告警（别名、缺省、可疑值）
```

三条硬约束：

1. **标准层词汇表对齐生态**（Clash/Mihomo 风格命名），让互操作成本最低 —— 这是生态的事实标准。
   ⚠️ 但只对齐**命名**，**不对齐枢纽结构**：绝不能把 clash-meta 当内部中间表示（理由见 §4.5）。
2. **扩展层用命名空间**：`<namespace>:<feature>`，第三方不认识 → `UNKNOWN`，不是解析失败、更不是丢弃。
3. **归一化只增不减**：任何"改写/降级"都必须留下 provenance 记录；`raw_uri` 永远保留。

---

## 8. Custom / Vendor Feature Registry 设计

```
feature_id            # 例如 mi1314cat:anyreality.ss-reality
namespace             # standard | mi1314cat | <第三方>
applies_to            # 它能叠加在哪些 protocol/transport 上（组合规则）
params_schema         # 参数定义（校验 + 文档）
uri_representation    # full | partial | none  ← 决定能不能回写链接
uri_carrier           # 若能表达：走哪个 query/fragment 键
evidence              # doc/src/test 三类来源 + 日期
```

关键点：

- `uri_representation: none/partial` 的组合（如 ss+reality）**默认就要产出 `losses[]`**，
  而不是等到目标内核不支持才报 —— 因为"链接本身就装不下"是更早发生的损失。
- namespace 不是装饰：它决定**遇到不认识的东西时的语义** ——
  标准 namespace 里的未知项 → `UNKNOWN`（可能是我们没跟上内核更新）；
  vendor namespace 里的未知项 → `UNKNOWN` 且**必须保留**（可能是别人家的扩展）。
- registry 是**数据文件**，新增内核/能力不改引擎（对齐你定的 P11）。

---

## 9. AnyReality 如何作为扩展能力进入模型

完整实测记录见 `research/empirical/anyreality.md`。要点：

- 我们的三个变体散落在三个仓库里，目前靠**人类注释**维护兼容性结论，其中**一条注释是错的**：
  `conf/Shadowsocks.sh:396` 写「sing-box **可直接叠加 Reality**」，而真内核给出
  `FATAL: outbounds[0].tls: json: unknown field "tls"` —— **sing-box 的 ss 出站根本没有 tls 字段**。
  → 靠注释维护兼容性，生产上就是"用户照说明操作却连不上"。
- 建模方式：`protocol: shadowsocks` + `features: [standard:reality]`，
  对外 id 用 `mi1314cat:anyreality.ss-reality`（vendor 命名空间）——
  **不新增协议类型、不加特例 hack**，判定走"feature 组合 × 内核能力表"的通用路径。
- 对 mihomo 的现有结论（"ss 出站不支持 Reality"）在实测中**只到配置层**：
  `-t` 通过（因为 mihomo 不校验这类字段），运行层回环未跑通 →
  按纪律记为 **UNKNOWN**，不写成 UNSUPPORTED，也不写成支持。

---

## 10. proxy-node-compat 与这些项目的关系

**不是替代，是补位。**

```
   解析/转换生态                          proxy-node-compat
┌──────────────────────┐              ┌────────────────────────┐
│ Proxylink            │              │ 能力判定 + 损失报告     │
│ subconverter         │  节点/URI →  │ ─ 内核×发行版×版本      │
│ Sub-Store            │              │ ─ 字段级 loss/warning   │
│ xray-knife / v2rayN  │              │ ─ 未知 vs 不支持        │
└──────────────────────┘              │ ─ round-trip 不变量     │
        ▲                              └────────────────────────┘
        └── 我们向它们学习：词汇表、目标特性表、工程组织、测试语料
```

具体三条：

1. **学它们的词汇表和目标特性表**（Clash/Mihomo 事实标准），不自创字段名 —— 这是"不造不兼容轮子"的实质。
2. **不 fork 它们的模型**：它们的共同缺陷（扁平/绑死单内核/无版本/无 loss）正是我们存在的理由，
   照搬等于把缺陷一起继承。
3. **可以复用它们当"输入适配器"**：客户端已经用某个转换器产出配置时，我们仍应根据**原始 URI/原始字段**
   判定（所以我们坚持 `raw_uri` + `extensions`），而不是相信转换后的结果 —— 因为转换可能已经悄悄丢了东西。
4. **反向输出**：我们的 `losses[]` / `failure_mode` 数据对上游项目同样有价值
   （例如 Proxylink 的 transport 静默清空、subconverter 的 49 处 `continue`），
   等这套层稳定后可以反馈给它们。

---

## 附：本报告的证据分级

| 结论 | 证据类型 |
|---|---|
| Proxylink 静默丢 transport / `PinSHA256→insecure` | **我自己读源码 + 复现路径**（`singbox.go`）+ 子代理源码报告 |
| subconverter 49 处 `continue` / 0 处 loss 文档 | 子代理源码报告（静态读码，未运行编译） |
| mihomo 静默降级 / xray 移除 h2 与 mkcp 字段 / sing-box 无 xhttp | **真内核实测**（`research/empirical/`，含内核原文报错） |
| sing-box 不能表达 ss+reality | **真内核实测**（`unknown field "tls"`） |
| AnyReality 运行层判定 | **UNKNOWN**（回环未跑通，未记为结论） |
| sing-box-lx 带 XHTTP/AmneziaWG2/MASQUE | 仓库元数据 + 描述（**未读其源码**，标 UNKNOWN 待验） |
