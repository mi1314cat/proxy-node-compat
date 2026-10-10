# OSS 源码级调研：subconverter 与 sublink-worker

> Phase 1.5 —— 为 `proxy-node-compat` 的「节点能力识别与兼容性判断层」收集**源码级**证据。
>
> 核心问题不是"它们怎么转换"，而是：**当一个目标不支持某个能力时，它们到底做了什么？**
> 因为本项目的第一原则是「绝不静默丢失能力」，所以我们要找的正是**静默丢失的实现方式**，
> 作为反面证据与设计警示。

## 调研方法与可复现性

| 项目 | 仓库 | 调研对象（commit） | commit 日期 |
|---|---|---|---|
| A | `tindy2013/subconverter` (C++) | `a0d4eab28cb8b6c782d4ce5c3a918de4829b4a72` | 2026-07-08 |
| B | `7Sageer/sublink-worker` (TS) | `a223b11c1e5991db2f0e0ab89f0c5c8384845d93` | 2026-09-25 |

方法：`git clone --depth 1` 取完整源码树，用 `grep`/逐段 `read` 通读**真实实现**（不是 README）；
issue 证据走 GitHub Search API。**本文所有"存在/不存在"的结论都附 `path:line`，可复现。**
凡代码无法证实的，一律标 `UNKNOWN`，不推测。

**图例**：`✅` 代码证实存在 · `❌` 代码证实不存在（负证据，本项目最关键的一类） · `⚠️` 部分/有陷阱 · `❓` UNKNOWN

---

# A. subconverter (`tindy2013/subconverter`)

## A1. subconverter 的节点模型

单一结构体 `Proxy`，定义在 `src/parser/config/proxy.h:62-137`，配一个 `ProxyType` 枚举
（`src/parser/config/proxy.h:12-27`）。**它是"所有协议挤在一个结构体里"的扁平并集（fat struct）**，
不是 tagged union，也没有按协议分层的子结构：SS 的 `Plugin`、VMess 的 `AlterId`、WireGuard 的
`PrivateKey`、Hysteria 的 `RecvWindow` 全都平铺在同一个 struct 的同一个命名空间里。

```cpp
// src/parser/config/proxy.h:62
struct Proxy
{
    ProxyType Type = ProxyType::Unknown;
    uint32_t Id = 0;
    uint32_t GroupId = 0;
    String Group;
    String Remark;
    String Hostname;
    uint16_t Port = 0;
    ...
    String TransferProtocol;   // :83  ← transport 维度
    String FakeType;
    bool TLSSecure = false;    // :85  ← TLS 只是一个布尔
    String Host; String Path; String Edge;
    ...
    tribool UDP; tribool TCPFastOpen; tribool AllowInsecure; tribool TLS13;
    ...
    String Fingerprint;        // :123
    StringArray Alpn;          // :130
```

关键字段与能力的表达方式：

| 能力 | subconverter 里怎么表达 | 结论 |
|---|---|---|
| transport | `String TransferProtocol`（裸字符串：`tcp`/`ws`/`http`/`h2`/`grpc`/`kcp`/`quic`…） | ⚠️ 无枚举、无白名单，**任意字符串都能存进来** |
| TLS | `bool TLSSecure` + `String SNI`/`ServerName` + `tribool AllowInsecure` + `StringArray Alpn` + `String Ca/CaStr` | ⚠️ TXT 记录/ECH 无表达；TLS 只有开关没有版本/模式 |
| uTLS / client-fingerprint | **无字段** | ❌ 全仓库 `client-fingerprint`/`utls` 命中 **0** 次 |
| `Fingerprint` 字段 | 实际是**证书固定（cert pinning）**：Clash 出 `fingerprint`（`:513-514`）、Surge 出 `server-cert-fingerprint-sha256`（`:972-973`）、Loon 出 `tls-cert-sha256`（`:2107-2108`） | ⚠️ **同名陷阱**：名字像 uTLS 指纹，语义是证书 SHA256。极易误读 |
| **Reality** | **完全没有**：`reality` 在 `src/` 命中 0（全仓库 7 次命中全是 `realitykings.com` 这类分流规则） | ❌ 模型层不存在 |
| **VLESS** | **完全没有**：`ProxyType` 枚举无 VLESS；全仓库 `vless` 命中 **0** 次 | ❌ **结构性不可能**（见 A6） |
| flow（`xtls-rprx-vision`） | 无字段 | ❌ |
| xhttp / ECH / splithttp | 无字段 | ❌ |
| headers | `Host` / `Path` / `Edge` 三个扁平字段，生成时各自塞进 `ws-opts.headers` 之类的结构 | ⚠️ **只支持 Host/Edge 两个 header 名**，任意自定义 header 无法表达 |
| plugin（SS） | `String Plugin` + `String PluginOption`（`;` 分隔的字符串，出目标时 `replaceAllDistinct(x.PluginOption, ";", "&")`） | ⚠️ 插件参数是**字符串透传**，不是结构化字段 |
| mux | 只在 SS 的 `plugin-opts.mux` 里以子串匹配出现（`:309`） | ❌ 没有独立的 mux 概念 |

**一个立刻可用的正面设计**：`tribool`（`src/utils/tribool.h`）三态布尔——
`indeterminate` / `true` / `false`，带 `is_undef()`、`define()`（"仅在未定义时赋值"）、
`get_str()` 返回 `"undef"`。这让模型能区分**"源里没写这个字段"**和**"源里明确写了 false"**。
这正是本项目 `UNKNOWN` vs "已知不支持" 所需要的字段级纪律。注意：它只用在**字段级**
（UDP / TFO / AllowInsecure / TLS13），**没有上升到能力级**——没有"这个能力未知"的概念。

## A2. subconverter 的 URI 解析

**入口**：`src/parser/subparser.cpp`。三层：

- `explode(link, node)` — `subparser.cpp:2577` — **单条分享链接**的分发器（if/else if 链）
- `explodeSub(sub, nodes)` — `subparser.cpp:2601` — 整份订阅内容（ssd / clash YAML / surge / base64 列表）
- `explodeConfContent(content, nodes)` — `subparser.cpp:2530` — 本地配置文件猜测格式
- 上层调用者是 `addNodes()`（`src/generator/config/nodemanip.cpp:33`）与 `filterNodes()`

支持的 scheme（`subparser.cpp:2577-2599`，逐条 if）：

```
ssr://            → explodeSSR       (:686)
vmess:// vmess1://→ explodeVmess      (:274，内部再分流 std/JSON/shadowrocket/kitsunebi/quan)
ss://             → explodeSS        (:492，含 SIP002 / Android / SSD)
socks:// https://t.me/socks tg://socks → explodeSocks (:787)
tg://http https://t.me/http            → explodeHTTP  (:836)
Netch://          → explodeNetch      (:1013)
trojan://         → explodeTrojan     (:892)
hysteria2:// hy2:// → explodeHysteria2(:1585)
anytls://         → explodeAnyTLS     (:1596)
其余 isLink()     → explodeHTTPSub    (:856)
```

**不认识的参数怎么办？—— 直接丢弃，无任何记录。**
解析是"按名取值"式：`getUrlArg(addition, "host")`（`src/utils/string.cpp:243`），
逐个 `getUrlArg` 把想要的键捞出来，**其余键从未被读取、从未被计数、从未被报告**。

**不认识的 scheme 怎么办？—— 整个节点消失。** `explode()` 末尾没有任何 `else` 分支：
没有分支命中时 `node` 保持默认构造，`Type == ProxyType::Unknown`，随后在
`explodeSub()` 的循环里被静默跳过：

```cpp
// src/parser/subparser.cpp:2658
if(strLink.empty() || node.Type == ProxyType::Unknown)
{
    continue;          // ← 无日志、无计数、无警告
}
```

**不认识的 transport 也会让节点消失**（std 风格 vmess 链接）：

```cpp
// src/parser/subparser.cpp:1427-1443 (explodeStdVMess)
switch(hash_(net))
{
case "tcp"_hash:
case "kcp"_hash:  type = getUrlArg(addition, "type"); break;
case "http"_hash:
case "ws"_hash:   host = getUrlArg(addition, "host"); path = getUrlArg(addition, "path"); break;
case "quic"_hash: type = getUrlArg(addition, "security"); host = getUrlArg(addition, "type"); path = getUrlArg(addition, "key"); break;
default:
    return;        // ← net=grpc / h2 / xhttp：函数直接返回，node 仍是 Unknown → 被 2658 静默丢弃
}
```

这与 issue #354「v2ray 订阅链接转 clash 后丢失 h2 协议节点」完全吻合。

另一半是 **Clash YAML 源**：`explodeClash()`（`subparser.cpp:1115`）手写了
`switch(hash_(proxytype))` + 逐键 `singleproxy["key"] >>= var` 的读取方式，
**没有任何 catch-all / 未知键保留逻辑**。所以源配置里的 `reality-opts`、`client-fingerprint`、
`alpn`（VMess 分支）、`smux` 等在**解析阶段第一步**就不存在了——后面所有目标自然也无从谈起。

## A3. subconverter 的多目标生成

**组织方式：不是"一个目标一个文件"，而是"一个目标一个函数，全部塞在同一个 ~2700 行文件里"**
——`src/generator/config/subexport.cpp`。声明集中在 `src/generator/config/subexport.h:56-77`：

| 目标 (`target=`) | 生成函数 | 位置 |
|---|---|---|
| `clash` / `clashr` | `proxyToClash()` ×2 重载 | `subexport.cpp:232`、`:693` |
| `surge&ver=2/3/4` | `proxyToSurge(..., int surge_ver, ...)` | `:765` |
| `quan` | `proxyToQuan()` | `:1227`、`:1251` |
| `quanx` | `proxyToQuanX()` | `:1453`、`:1484` |
| `loon` | `proxyToLoon()` | `:1981` |
| `mellow` | `proxyToMellow()` | `:1826`、`:1841` |
| `singbox` | `proxyToSingBox()` | `:2326`、`:2631` |
| `ss` / `ssr` / `v2ray` / `trojan` / `mixed` | **共用** `proxyToSingle(nodes, types, ext)`，用位掩码选协议 `SS=1 SSR=2 VMess=4 Trojan=8`（`mixed`=15） | `:1093` |
| `sssub` | `proxyToSSSub()` | `:1174` |
| `ssd` | `proxyToSSD()` | `:1727` |

分发在 `src/handler/interfaces.cpp`：先校验白名单（`:320-334`，非法 target 返回
`400 Invalid target!`），再按 `switch(hash_(argTarget))` 生成（`:762` 起，clash `:762`、
surge `:785`、mellow `:829`、quanx `:900`、loon `:916`、singbox `:938`…）。
另有模板/基底配置层 `src/generator/template/`（jinja2）、规则层 `src/generator/config/ruleconvert.cpp`。

**架构代价**：新增一个目标要改 `subexport.h` + `subexport.cpp` 里那个巨型函数 + `interfaces.cpp`
的 switch/白名单 + 模板与文档，**且每个目标的字段映射都要重新手写一遍**——这正是
"能力×目标"矩阵爆炸的经典形态，也正是本项目要用 Capability Registry 数据化掉的东西。
生成器之间**不共享**任何"字段→目标字段"的映射表，每个 `proxyToXxx` 里都是一段裸的
`proxy += ", sni=" + x.SNI;` 式的拼接。

## A4. 目标不支持的字段怎么处理（最重要）

**结论：没有 `unsupported` 机制，没有 warning，没有 exclude 列表，没有计数——
只有 `continue`（丢节点）和"不写那个 key"（丢字段）两种静默处理。**

### 负证据：整份 `subexport.cpp` 里根本没有"能力不支持"的日志

`writeLog` 在 `subexport.cpp` 中总共出现 **8 次**，全部是 base 配置加载失败：

```
:703  "Clash base loader failed with error: "
:785  "Surge base loader failed with error: "
:1186 "SIP008 base loader failed with error: "
:1233 "Quantumult base loader failed with error: "
:1466 "QuantumultX base loader failed with error: "
:1832 "Mellow base loader failed with error: "
:1993 "Loon base loader failed with error: "
:2641 "sing-box base loader failed with error: "
```

**没有一次是因为某个节点/某个字段被丢弃。** 全文件 `continue;` 出现 **49 次**，其中大量是
"这个节点本目标表达不了 → 跳过"，全部无日志。

### 例子 1（丢**字段**，节点留下来但坏掉）：sing-box 的未知 transport 被静默降级为 TCP

`proxyToSingBox` 用 `buildSingBoxTransport()`（`subexport.cpp:2242-2279`）构造 transport 对象：

```cpp
static rapidjson::Value buildSingBoxTransport(const Proxy& proxy, rapidjson::MemoryPoolAllocator<>& allocator)
{
    rapidjson::Value transport(rapidjson::kObjectType);
    switch (hash_(proxy.TransferProtocol))
    {
        case "http"_hash: { ... }   // :2253
        case "ws"_hash:   { ... }   // :2261
        case "grpc"_hash: { ... }   // :2269
        default:
            break;                  // :2276  ← kcp / quic / xhttp / h2 …：返回空对象
    }
    return transport;
}
```

调用方（VMess 分支 `:2390-2392`、Trojan 分支 `:2400-2402`）：

```cpp
auto transport = buildSingBoxTransport(x, allocator);
if (!transport.ObjectEmpty())
    proxy.AddMember("transport", transport, allocator);   // ← 空对象 → 干脆不写 transport
```

**后果**：一个 `net=kcp`（或任何 subconverter 不认识的 transport）的 VMess/Trojan 节点，
在 `target=singbox` 下会被**原样输出成一个看起来完全合法的纯 TCP 节点**。
不报错、不警告、节点还在、JSON 合法、sing-box 能加载——**只是永远连不上**。
这就是本项目 README 里描述的那类失败（"能导入、能启动、就是不通"），
而且它是**同一个项目内两种不同失败模式之一**（对比例子 2）。

### 例子 2（丢**整个节点**）：Surge 默认版本 3 会静默吃掉 VMess/Trojan/WireGuard/Hysteria2/AnyTLS

`proxyToSurge` 对每种协议做**版本闸门**，不满足就 `continue`：

```cpp
// src/generator/config/subexport.cpp:845-846  (case ProxyType::VMess)
if(surge_ver < 4 && surge_ver != -3)
    continue;                                   // ← 节点整体消失
```

同类闸门：Trojan `:934-935`、WireGuard `:960-961`、Hysteria2 `:985`、AnyTLS `:1000-1001`；
SSR 要求 `surge_ssr_path` 非空 `:880-881`；SS 的 plugin 不认识时 `default: continue;` `:837`。

而 **`surge_ver` 的默认值是 3**：

```cpp
// src/handler/interfaces.cpp:309
int intSurgeVer = !argSurgeVer.empty() ? to_int(argSurgeVer, 3) : 3;
```

所以用户只要请求 `target=surge` 而**没带 `&ver=4`**，输出里所有 VMess / Trojan / WireGuard /
Hysteria2 / AnyTLS 节点都会**凭空消失且零提示**（只有 SS/HTTP/SOCKS5/Snell 活下来）。
issue #643「getprofile target = surge node list，只会保留 ss 类型的节点」就是它的用户侧表现。

### 例子 3（丢**整个节点**）：Clash 的未知 transport

```cpp
// src/generator/config/subexport.cpp:326-371  (case ProxyType::VMess in proxyToClash)
switch(hash_(x.TransferProtocol))
{
case "tcp"_hash:  break;                                        // :327
case "ws"_hash:   ...  break;                                   // :329
case "http"_hash: ...  break;                                   // :348
case "h2"_hash:   ...  break;                                   // :357
case "grpc"_hash: ...  break;                                   // :363
default:
    continue;                                                   // :369  ← kcp/quic/xhttp → 节点消失
}
```

即：**同一份源订阅，`target=clash` 是"丢节点"，`target=singbox` 是"丢 transport 但留下坏节点"**。
目标之间的失败语义完全不一致，而且用户两种都看不出来。

### 例子 4（唯一"有记录"的丢弃——但只针对用户显式配置的过滤器）

全项目唯一会**写出日志**的节点丢弃在 `filterNodes()`（`src/generator/config/nodemanip.cpp:106-121`）：

```cpp
if(chkIgnore(*iter, exclude_remarks, include_remarks))
{
    writeLog(LOG_TYPE_INFO, "Node  " + iter->Group + " - " + iter->Remark + "  has been ignored and will not be added.");
    nodes.erase(iter);
}
```

但它匹配的是 **`Remark`（节点名）正则**（用户的 `include=`/`exclude=` 参数），
**与"目标内核支不支持这个能力"毫无关系**。整个项目里"exclude"只有这一种含义。

### 例子 5（round-trip 丢字段）：`target=mixed` / `v2ray` 重新拼 URL 时字段大面积蒸发

`proxyToSingle` 的 VMess 分支（`subexport.cpp:1150-1154`）调用
`vmessLinkConstruct(remark, hostname, port, faketype, id, aid, transproto, path, host, tls)`
（`:29-55`），而这个函数**只写** `v/p/ps/add/port/type/id/aid/net/path/host/tls` 十个键：

```cpp
// src/generator/config/subexport.cpp:29-55
writer.Key("v");   writer.String("2");
writer.Key("ps"); ... writer.Key("net");  writer.Key("tls"); writer.EndObject();
```

**`sni` / `alpn` / `skip-cert-verify` / `fingerprint` / `servername` 全部丢失**——
尽管 `Proxy` 里明明有这些字段。Trojan 分支（`:1157-1170`）同样只出
`allowInsecure` / `sni` / `ws` / `wspath`。**这是一条"解析进来了、但输出不回去"的静默损失**，
而且 `mixed`/`v2ray` 是分享链接订阅最常见的用途。

## A5. subconverter 有没有承认"转换会丢东西"？

- **README / 文档：❌ 零承认。** `README.md` / `README-cn.md` 中
  `not support | unsupported | limitation | known issue | incomplete | lost | drop` 命中 **0 次**。
- **代码注释：⚠️ 有零星承认，但语气是"照做"而非"报警"**：
  - `//ignoring all nodes with unsupported obfs, protocols and encryption`（`subexport.cpp:373`）
  - `//latest clash core removed support for chacha20 encryption`（`subexport.cpp:287`）
  - `// UDP is not supported yet in clash using snell`（`subexport.cpp:573`）
  这三处是全项目**仅有的**"我知道这不支持"的自述，而且原文就是 `ignoring all nodes`——
  写的人清楚这是在丢东西。
- **issue tracker：⚠️ 用户反复报告，长期未修（这是最有力的证据）**：
  | issue | 标题 | 状态 |
  |---|---|---|
  | #440 | trojan 配置会丢失 sni 参数 | closed |
  | #447 | 转换服务器地址为 IP 的 trojan 会丢失 sni 字段参数 | closed |
  | #354 | v2ray 订阅链接转 clash 后丢失 h2 协议节点 | **open**（2021-07 起） |
  | #798 | proxies `dialer-proxy` 参数会被过滤掉 | **open** |
  | #643 | getprofile target = surge node list，只会保留 ss 类型的节点 | closed |
  | #611 | 请问能不能支持 VLESS-WS-TLS? | **open**（2023-06 起） |
  | #666 | 建议增加 vless(reality) 协议的节点转换为 sing-box 的代理组 | **open**（2023-11 起） |
  | #779 | 能否支持 Vless | **open**（2024-08 起） |
  | #867 | 建议支持 vless 等新协议 | **open**（2025-10 起） |
  | #886 | feat: add VLESS protocol and Snell v4/v5 support（PR） | **open**（2026-02） |

  #611 里社区给出的解释是一句**教科书级的问题陈述**：

  > "原生的 clash 内核还不支持 vless，所以作者干脆就没转换了，但 clash.meta 支持 vless，
  > 换内核之后其实是可以使用 vless 的。" —— @Magic989, 2023-07-01

  **它精确描述了我们项目要消灭的那件事**：转换器的能力上限被**硬编码成"某个内核某个时刻的能力"**，
  内核升级了、或者换一个内核（clash → mihomo），转换器既不知道也不报告——
  它的答案是"干脆不转换"，用户拿到的是**一个静默变少的订阅**。
- **round-trip 测试：❌ 完全没有。** 仓库根本没有 `test/` 目录或任何测试文件
  （`find -iname "*test*"` 只命中分流规则名单，如 `AdRuleTest.list`）；
  `.github/workflows/` 只有 `build.yml` 与 `docker.yml`，**CI 只编译，不跑任何测试**。
  所以"parse → generate → reparse 是否等价"这件事**从未被验证过**，
  A4 例子 5 那类损失可以长期存在而无人发现。

## A6. subconverter 没做的事

- **内核版本维度：⚠️ 只有一个，而且很粗。** 全项目唯一的版本概念是 **Surge 大版本 2/3/4**
  （以函数参数 `int surge_ver` 形式存在，见 `subexport.h:65` / `subexport.cpp:765`；不在 `Proxy` 里），
  外加 `UAMatchList`（`interfaces.cpp:53-80`）通过 User-Agent 猜 target 与 Surge 版本，
  配一个 `verGreaterEqual()`（`interfaces.cpp:83-108`）做版本比较。
  **没有** Clash / mihomo / sing-box / Xray 的任何版本概念：
  `grep -i "mihomo\|meta"` 无版本相关逻辑；sing-box 只有 `global.singBoxAddClashModes`
  这种全局开关（`subexport.cpp:2607`）。
  最要命的是：**版本维度的用途是"决定丢不丢节点"，而不是"报告损失"**（见 A4 例子 2）。
- **"运行时是否真生效"：❌ 完全没有。** 项目不生成后就地校验配置，不调用内核做 `-t`/dry-run，
  没有任何反馈回路。sing-box 的 transport 静默降级（A4 例子 1）正是没有任何兜底校验的直接结果。
- **"未知能力"的概念：❌ 没有。** 只有字段级的三态 `tribool`（A1），
  能力级是"不认识 = 丢弃"：不认识的 scheme（`explode()` 无 else）丢节点、
  不认识的 transport（`explodeStdVMess` `default: return`）丢节点、
  不认识的 Clash YAML 键（`explodeClash` 逐键读取）丢字段。
  **"未知"和"不支持"在实现上是同一个分支**——这正是本项目要拆开的两个状态。
- **VLESS 的结构性缺失：❌ 不是"没实现好"，是"模型里没有"。** `ProxyType` 枚举
  （`proxy.h:12-27`）只有
  `Unknown/Shadowsocks/ShadowsocksR/VMess/Trojan/Snell/HTTP/HTTPS/SOCKS5/WireGuard/Hysteria/Hysteria2/AnyTLS`。
  没有 VLESS ⇒ 任何 VLESS 节点都只能落到 `ProxyType::Unknown` ⇒ 被 `subparser.cpp:2658` 静默丢弃。
  连"Hysteria2/AnyTLS 已经支持"这件事都还没写进 README 的目标表（README 表格停在 Surge 4 / V2Ray，
  **没有 singbox、没有 mellow、没有 hysteria**）——文档与实现已经脱节。

---

# B. sublink-worker (`7Sageer/sublink-worker`)

> ⚠️ **第一个必须纠正的前提**：任务描述称它是 "TypeScript"。**它根本不是 TypeScript。**
> 全仓库 `.ts`/`.tsx`/`.d.ts` 命中 **0**；`src/` 是 49 个 `.js` + 11 个 `.jsx`；
> `package.json` 无 `typescript` 依赖、无 `tsconfig.json`、无 typecheck 脚本。
> **推论很重要**：它**不存在"类型定义"可供阅读**——"看它的类型定义"这条路本身不存在，
> 节点模型是一个**无 schema 的动态 JS 对象字面量**。这决定了下文所有关于"模型"的答案。

## B1. sublink-worker 的节点模型

**没有节点类型/类/schema。** 每个协议解析器各自 `return { ... }` 一个字面量对象，
唯一的不变量是 `type` 字符串字段。共享字段只有
`type / tag / server / server_port` 加可选的 `tls / transport / tcp_fast_open`，
**其余形状按协议各自发散，连命名风格都不统一**：

| 维度 | 表达方式 | 证据 |
|---|---|---|
| TLS | 嵌套对象 `tls = { enabled, server_name, insecure, reality?, utls? }` | `src/utils.js:289-310` |
| Reality | `tls.reality = { enabled, public_key: params.pbk, short_id: params.sid }` | `src/utils.js:301-306` |
| uTLS 指纹 | `tls.utls = { enabled, fingerprint }` —— **但只在 reality 分支被硬编码成 `'chrome'`** | `src/parsers/protocols/vlessParser.js:9-13` |
| flow | **顶层**字段 `flow`（不在 tls 里） | `vlessParser.js:25`、`trojanParser.js:22`、`tuicParser.js:23` |
| transport | `transport = { type, path, headers: {host}, service_name? }`，`type` 为**裸字符串透传** | `src/utils.js:312-322` |
| headers | 只有 `transport.headers.host`，且**形状不一致**：URI 解析器给字符串、vmess/YAML 给数组 | `utils.js:317` vs `convertYamlProxyToObject.js` |
| plugin（SS） | 扁平 `plugin` + `plugin_opts`，由 `shadowsocksParser.js:40-43` 解析 | `src/parsers/protocols/shadowsocksParser.js` |
| 布尔命名 | `tcp_fast_open`（ss/vmess/vless/trojan）**vs** `fast_open`（hy2/tuic/anytls） | 见各 parser |
| anytls 字段 | **kebab-case**：`'idle-session-check-interval'` | `convertYamlProxyToObject.js:255-257` |

**结论**：这是一个"每种协议一个 JSON 约定"的弱模型。它**能表达** reality / flow / uTLS / xhttp-type
（因为 `transport.type` 是裸字符串），但**表达的一致性和完备性没有任何机制保证**——
`sanitized = { ...proxy }` 式的透传（`SingboxConfigBuilder.js:105`、`ClashConfigBuilder.js:307`）
意味着"模型里有什么"直接等于"输出什么"，没有中间层来校验。

## B2. sublink-worker 的 URI 解析

**入口**：`src/parsers/ProxyParser.js:24-36`，一张 `protocolParsers` 分发表：

```js
const protocolParsers = {
    ss, vmess, vless, hysteria, hysteria2, hy2, trojan, tuic, anytls,
    http: fetchSubscription, https: fetchSubscription
};
static async parse(url, userAgent) {
    const type = trimmed.split('://')[0].toLowerCase();
    const parser = protocolParsers[type];
    if (!parser) return undefined;      // ← 未知 scheme：返回 undefined，无日志
    return parser(trimmed, userAgent);
}
```

- **不支持的 scheme**：`ssr / socks / socks5 / http-proxy / wireguard` **都没有节点解析器**
  （`http`/`https` 被映射到**订阅抓取**，不是 http 代理节点，见 `httpSubscriptionFetcher.js`）。
  未知 scheme → `return undefined` → 调用方 `if (subResult)` 判断 → **静默丢弃，无任何日志**。
- **参数采集**：`parseUrlParams()`（`utils.js:272-287`）用
  `Object.fromEntries(searchParams.entries())` **无过滤地收下全部 query 参数**；
  但每个 parser 随后 `return` 一个字面量，**只读它手写白名单里的键** →
  未实现的键与未知的键**待遇完全相同：静默消失**。全仓库没有任何
  `unsupportedParams` / 参数告警机制（grep = 0）。
  实证掉字段：`spx=`（Reality 的真实参数）、grpc 的 `mode=gun`、`extra=` 全部未被读取。
- **一处"静默改写"比静默丢弃更危险**：`vlessParser.js:9-13`——只要 `security=reality`，
  就无条件写入 `tls.utls = { enabled: true, fingerprint: 'chrome' }`。
  用户写 `fp=firefox` 会**被无声换成 chrome**；而 `createTlsConfig()`（`utils.js:289-310`）
  **从不读取 `fp`**（uTLS 块在 `utils.js:296-299` 是注释掉的），
  所以非 reality 的 `fp=...` 则被**无声丢弃**。anytls 是唯一真正尊重 `fp` 的协议
  （`anytlsParser.js:61`）。

## B3. sublink-worker 的多目标生成

**组织方式：一个目标一个文件、一个 `BaseConfigBuilder` 子类**（与 subconverter 的巨型单文件相反）：

| 目标 | 路由 | 生成器 | 路径 |
|---|---|---|---|
| Clash / mihomo | `/clash` | `ClashConfigBuilder` | `src/builders/ClashConfigBuilder.js` |
| sing-box | `/singbox` | `SingboxConfigBuilder` | `src/builders/SingboxConfigBuilder.js` |
| Surge | `/surge` | `SurgeConfigBuilder` | `src/builders/SurgeConfigBuilder.js` |
| （伪）xray | `/xray` | **不是生成器**：只把输入 URI 行重新 Base64 编码 | `src/app/createApp.jsx:263-311` |
| （伪）subconverter | `/subconverter` | 生成外部 subconverter 的 INI 参数 | `createApp.jsx` |

- **没有** `clashmeta`/`mihomo` 独立目标：`clash` 目标本身就是 mihomo 风味
  （输出 MRS rule-provider + `proxy-providers` + `reality-opts`）。
- 公共流程在 `BaseConfigBuilder.js`（`convertProxy` 是抽象方法，`:351-353` 抛错），
  子类实现约 11 个抽象方法（`:344-428`）。
- **加一个目标没有注册表**：要新建 `src/config/*Config.js` + builder 子类 + `config/index.js` 导出 + 路由。
  `AGENTS.md` 里有"如何加协议""如何加 runtime"的配方，**没有"如何加目标"的配方**。

## B4. sublink-worker 的目标不支持字段时怎么处理（最重要）

**结论：字段级不兼容 = 100% 静默丢弃；全代码库只有 2 处用户可见的"不支持"提示，
而且都在 Surge 输出的注释行里。**

### 全部"提示机制"清单（穷举）

| # | 机制 | 位置 | 覆盖范围 |
|---|---|---|---|
| 1 | `# ${proxy.tag} - Unsupported proxy type: ${proxy.type}` | `SurgeConfigBuilder.js:132` | **仅整个协议类型**，且仅 Surge |
| 2 | `# SRC-IP-CIDR not supported by Surge, skipped: ...` | `SurgeConfigBuilder.js:437` | 仅一条规则 |
| — | 字段级（reality/flow/alpn/fp/path/plugin/obfs…） | **不存在** | ❌ 无 |

而且机制 1 的注释还必须被排除在 proxy-group 之外才能保证语法合法——
`getValidProxies()`（`:31-35`）过滤 `#` 开头的行，`getProxyList()`（`:38-40`）覆写，
代码注释写明 `Fixes issue #299: comment strings were incorrectly added to proxy groups`。
即：**这个唯一的"不支持提示"本身还曾经是个 bug**。

**没有任何其它通道**：路由只返回配置正文（+ `subscription-userinfo` 头），
没有 diagnostics 字段、没有 warning 头、`src/i18n/index.js` 里
`unsupported/dropped/ignored` 相关字符串 **0 条**。

### 例子 1（丢**能力**，节点留下来但坏掉——与 subconverter 例子 1 同型）：Surge + Trojan-Reality

Surge 的 `trojan` 分支（`SurgeConfigBuilder.js:91-110`）只写
`password / sni / skip-cert-verify / alpn / ws / grpc`，**完全没有 reality 分支**：

```
输入: trojan://pw@h.example:443?security=reality&pbk=PUBKEY&sid=abcd&flow=xtls-rprx-vision&type=grpc#TrojanReality
内部模型: tls.reality = {enabled:true, public_key:'PUBKEY', short_id:'abcd'}, flow='xtls-rprx-vision'
Surge 输出: TrojanReality = trojan, h.example, 443, password=pw, sni=s.example, grpc-service-name=gsvc
```

生成器**执行过**（未修改源码），整份输出里 `reality` / `flow` / `xtls` / `pbk` / `sid`
子串全部为 false。**Reality 被无声降级成普通 TLS**：配置合法、Surge 能加载、
节点看起来正常、**永远连不上**，用户拿不到任何提示。
`reality|flow|utls|fingerprint|plugin|obfs` 在 `SurgeConfigBuilder.js` 中 grep 命中 **0**。

### 例子 2（丢**字段**：分支写了 `if` 却没有 `else`）：Surge + Trojan-http/h2/xhttp

`SurgeConfigBuilder.js:72-79`（vmess）与 `:92-99`（trojan）的 transport 处理是
`if (transport?.type === 'ws') {...} else if (transport?.type === 'grpc') {...}`
——**没有 `else` 臂**。于是 `type=http` 的节点输出
`TrojanHttp = trojan, h2.example, 443, password=pw, sni=cdn.example`，
**`path` 与 `host` 直接蒸发**。同样的静默丢失适用于 ss 的 `plugin`、
hy2 的 `obfs`、以及 `alpn`/`fp`。

### 例子 3（同一字段在不同目标语义相反 → 最隐蔽的一类）：sing-box 的 `network`

这不是"没实现"，而是**同一个键在两个内核里含义不同**：

```js
// src/builders/SingboxConfigBuilder.js:130-131
delete sanitized.udp;
delete sanitized.network;
```

代码注释完整记录了这次事故（`test/issue-297-vmess-network.test.js` 开头）：

> "the original fix hardcoded `network: 'tcp'` on every parsed proxy so sing-box would stop
> seeing transport names like 'ws' in that slot. That value is harmless in Clash but in sing-box
> `network` is a TCP/UDP allowlist (option/types.go NetworkList), and **"tcp" silently disables UDP**
> — breaking DNS hijack, fakeip, QUIC, and any selector that picks the node."

**这是本项目论点的最强外部佐证**：同一个字面值 `network: "tcp"` 在 Clash 里无害、
在 sing-box 里是"静默关闭 UDP"的语义炸弹。而且发现路径是**用户报 bug（#297）**，
不是任何自动校验——`delete` 掉是修法，**依然不告诉用户**。

### 例子 4（两条相反的静默策略共存于同一文件）

`SingboxConfigBuilder.convertProxy` 的策略是"**删**"：`delete sanitized.udp/network`
（`:130-131`）、`delete sanitized.packet_encoding`（`:148`，注释
`// Remove packet_encoding for now - it's version-specific in sing-box`）、
`delete sanitized.auth/recv_window_conn/fast_open`（`:173-175`）；
文件自己的注释（`:152`）还写着 sing-box `rejects unknown fields outright`。
**但 `plugin`/`plugin_opts`/`tcp_fast_open` 并没有被删掉，会漏进 sing-box 输出。**
即：同一个文件里"怕被拒所以删"和"该删的漏了"同时存在——**没有字段级的统一策略表**。

而 Clash 生成器的策略是相反的"**原样透传**"：

```js
// src/builders/ClashConfigBuilder.js:306-307
default:
    return proxy; // Return as-is if no specific conversion is defined
```

未知协议类型 → 内部 snake_case 对象**原样塞进 mihomo YAML**。
这是"不丢字段"的直觉做法，代价是**可能输出内核不认识的键**——
两个项目的失败模式恰好互为镜像（subconverter 丢，sublink-worker 漏）。

### 例子 5（**入口处**就丢节点，而且被测试固定为"预期行为"）

YAML/Clash 源里类型不认识 → `convertYamlProxyToObject` `default: return null;`
（`convertYamlProxyToObject.js:261-262`）→ 上游 `.filter(p => p != null)`
（`subscriptionContentParser.js:124`、`:159`）→ **整个节点消失**。
而这是**被测试断言为正确行为**的：

```js
// test/yaml-parsing.test.js:76-79
{
    name: '混合类型与无效节点',
    description: '仅返回受支持类型的节点，忽略未知类型',   // ← "忽略未知类型"是需求
    ...
}
```

**"未知类型 = 忽略"被写成了规格。** 本项目要做的恰恰是把这条规格翻过来。

## B5. sublink-worker 有没有承认"转换会丢东西"？

- **文档：❌ 零承认。** `README.md` / `AGENTS.md` / `CLAUDE.md` 中
  `known limitations | unsupported | 不支持 | 丢失` 相关章节 **0 处**。
- **代码注释：✅ 大量、而且质量很高——这是它比 subconverter 强的地方。**
  注释不只承认丢，还解释了**为什么必须丢**（内核语义差异）：
  `SingboxConfigBuilder.js:126-131`（network 会静默关 UDP）、
  `:146-147`（packet_encoding 是 version-specific）、
  `:152`（sing-box 拒绝未知字段）、
  `:541-546`（sing-box 1.14 弃用 download_detour / 1.16 移除）。
  `ClashConfigBuilder.js:13-22`（MRS 是 Clash Meta/mihomo 的二进制格式 + 客户端白名单）。
- **测试：✅ 有真实回归测试套件，主题恰好是"静默丢失"这一类 bug。**
  38 个文件 / 5,023 行（vitest + `@cloudflare/vitest-pool-workers`），
  文件名直接以 issue 号命名，且**每个文件都在文档化一次能力损失事故**：
  | 测试文件 | 记录的损失 |
  |---|---|
  | `test/surge-unsupported-proxy.test.js` | Issue #299：不支持类型的注释串污染 proxy-group（Reality VLESS 样例） |
  | `test/issue-297-vmess-network.test.js` | sing-box `network:"tcp"` **静默关 UDP** |
  | `test/issue-388-trojan-tls.test.js` | trojan 省略 `security` → `tls.enabled=false` → sing-box 起不来 |
  | `test/udp-handling.test.js` | `udp` 在 sing-box 被删、在 Clash 保留（**静默丢弃被断定为预期**） |
  | `test/issue-370-empty-clash-output.test.js` | 空输出 |
  | `test/issue-337-ss-cipher-decode.test.js`、`issue-428-hy2-port-hopping.test.js`、`issue-401-rule-set-download.test.js` … | 各自的字段/兼容性事故 |
- **但 round-trip 测试：❌ 仍然没有。** `reparse | round-trip | fidelity` grep = 0，
  `toMatchSnapshot` = 0。测试全是**针对具体 issue 的字段/子串断言**。
  **没有任何测试断言 Reality 能活到任何一个目标**——B4 例子 1 那类损失因此可以长期存在。
  这与 subconverter 的区别是"有回归网、但网眼只覆盖已报过的 bug"，不是"行为等价性保证"。

## B6. sublink-worker 没做的事

- **内核版本维度：⚠️ 有一个真正的实现，但只覆盖 sing-box，且只用于配置骨架层。**
  这是两个项目里**唯一**像 Capability Registry 的东西：

  ```js
  // src/app/createApp.jsx:494-515
  function resolveSingboxConfigVersion(requestedVersion, userAgent) {
      if (normalizedRequested === 'legacy') return '1.11';
      if (normalizedRequested === 'latest') return '1.14';
      const parsed = parseSemverLike(normalizedRequested);
      if (parsed) return resolveSingboxConfigTier(parsed);
      // 再尝试从 User-Agent 里嗅探 "sing-box/x.y.z"
      if (parsedFromUa) return resolveSingboxConfigTier(parsedFromUa);
      return '1.12';                       // ← "安全档"
  }
  ```
  版本档位 `'1.11' | '1.12' | '1.14'`（`SingboxConfigBuilder.js:17,28`），
  来源是 `singbox_version` / `sb_version` / `sb_ver` query 参数或 UA（`createApp.jsx:89`），
  用于切换 base config（`SING_BOX_CONFIG_V1_11`）与 rule-set 下载形态
  （`configureRuleSetDownload()`，`:549-563`）。
  **但它从不参与"这个节点的能力能不能用"的判断**——没有任何
  "reality 需要 sing-box >= X"、"vision flow 需要 >= Y" 的门槛。
  版本维度管的是**路由/rule-set 管道**，不是**节点能力**。
  Clash/mihomo 侧只有 `supportsMrsFormat` 的 UA 子串嗅探
  （`ClashConfigBuilder.js:18-41`），且只影响 rule-provider 格式，不影响 proxy 字段；
  Surge 侧完全没有版本参数。
- **"运行时是否真生效"：❌ 完全没有。** 无 schema 校验器（无 ajv/zod）、
  不跑 `sing-box check` / `mihomo -t`、无回环。CI 仅 `npm install && npm test`
  （`.github/workflows/test.yml`）。现有的 `validate*` 只检查**引用完整性/空组**
  （`ClashConfigBuilder.js:643-661`、`SingboxConfigBuilder.js:476-509`、
  `helpers/clashConfigUtils.js:60-92`）——它们能抓"组里引用了不存在的节点"，
  **抓不到"字段被静默删了"**（B4 例子 3 正是靠用户报 bug 才发现的）。
- **"未知能力" vs "不支持"：❌ 不区分。** 证据：
  `security=<任意非 none 值>` 一律当 TLS（`utils.js:291`）；
  `transport.type` 原样透传不做白名单（`utils.js:314`，所以 `xhttp` 会漏出去）；
  cipher 无白名单；`parseBool` 对无法解析的值返回 `undefined`；
  `singbox_version` 解析失败**静默回落 1.12**，而 `9.9` 会**静默映射到 1.14**。
  **"我不认识这个值"从不产生一个可报告的第三种状态**——与 subconverter 同病。

---

# C. 横向结论

## C1. 两个项目的对照

| 维度 | subconverter (C++) | sublink-worker (JS) |
|---|---|---|
| 节点模型 | 单一 `struct Proxy` fat struct + 枚举（**编译期固定**） | 无 schema 的动态对象字面量（**运行期发散**） |
| 协议覆盖 | 多，但**无 VLESS / 无 Reality**（模型层不存在） | 少（无 SSR/SOCKS/WireGuard），但**有 VLESS + Reality + flow + uTLS** |
| 生成器组织 | 1 个 2700 行文件，每目标 1 函数，手写字段映射 | 每目标 1 文件 1 子类，共享 `BaseConfigBuilder` 骨架 |
| 加目标的成本 | 改 4 处 + 重写全部字段映射 | 新建 builder 子类 + config + 路由，**无注册表** |
| **不支持字段** | **`continue` 丢整个节点**（clash/surge）**或**不写 key 丢字段（singbox） | **`delete`/不写分支丢字段**，或 `default: return proxy` 原样透传 |
| 有 unsupported 概念吗 | ❌ 无（只有 remark 正则过滤器，且与能力无关） | ⚠️ 仅 2 处，都是 Surge 输出里的 `#` 注释 |
| 丢弃有日志吗 | ❌ 无（`writeLog` 只用于 base 配置加载失败） | ❌ 无（路由只返回配置正文） |
| 内核版本维度 | ⚠️ 仅 Surge 2/3/4，**用途是决定丢哪个节点** | ⚠️ 仅 sing-box 1.11/1.12/1.14，**用途是选 base config** |
| 运行时生效性校验 | ❌ 无（且 CI **只编译、零测试**） | ❌ 无（CI 跑 38 个回归测试，但无内核校验） |
| round-trip / 保真测试 | ❌ **完全没有测试目录** | ❌ 无保真测试（有 per-issue 回归测试） |
| 承认会丢东西 | ❌ README 零承认；仅 3 条代码注释 | ⚠️ 代码注释质量高；文档零承认 |

**两者共同的结论（对本项目最关键的判断）**：
**没有任何一个项目存在"这个能力在目标内核的此版本上会损失什么"这一层。**
两者的"不支持"实现都是**在生成阶段直接 `continue` / `delete` / 不写那个键**——
损失发生在**写出配置的那一刻**，而此刻**没有任何数据结构承载"损失了哪些能力"**。
两者都有"未知"这一情形（未知 scheme / 未知 transport / 未知键），
但都把它**归并进同一个分支**（丢弃或透传），从不产生第三种可报告状态。

## C2. 对我们最有价值的 3 个设计（可借用）

1. **`tribool` 三态字段（subconverter `src/utils/tribool.h`）→ 升级为"能力四态"。**
   `indeterminate / true / false` + `is_undef()` + `define()`（仅在未定义时赋值）+
   `get_str()` 返回 `"undef"`。它证明"字段没写"和"字段写了 false"必须分开存，
   否则 `AllowInsecure` 这类默认值会伪装成用户意图。
   subconverter 只用到了**字段级**——本项目应当把这套纪律**升到能力级**：
   `PRESENT / ABSENT_EXPLICITLY / UNKNOWN_NOT_EXPRESSIBLE_BY_URI / UNSUPPORTED_BY_TARGET`。
   注意 subconverter 自己也没做全（它在 Surge 里用 `tls13.is_undef()` 判断是否输出，
   说明这层区分是**有实际输出后果**的，不是洁癖）。

2. **"不支持就留一条注释"（sublink-worker `SurgeConfigBuilder.js:132`）→ 升格为结构化 `reason_code`。**
   这是两个项目里**唯一**"不静默"的先例：不支持的类型被写成
   `# <tag> - Unsupported proxy type: <type>`，留在配置里、可被 grep、可被人看到。
   虽然它只覆盖"整协议类型"且只管 Surge，但方向上完全正确：
   **保留证据而不是删除证据**。本项目的 `SUPPORTED_WITH_LOSS` + `reason_code`
   就是它的结构化版本。
   反面教材同样有价值：issue #299 说明这条注释**必须与节点列表分离**，
   否则提示信息本身会污染配置语法（sublink-worker 用 `getValidProxies()` 修掉了）。
   → 我们的结论：**损失必须记录在 compat 的返回值里，绝不能塞进客户端配置正文**。

3. **"同一字段在不同内核语义相反"的显式知识（sing-box `network` 事故）。
   `test/issue-297-vmess-network.test.js` 的一段注释是本项目四层模型的现成教材**：
   `network:"tcp"` 在 Clash 无害、在 sing-box 里是"静默关闭 UDP 的语义炸弹"。
   这证明**"字段名相同"绝不等于"语义相同"**，兼容性判断必须
   ① 按目标内核分别建模，② 覆盖"语义反转"而不只是"支持/不支持"。
   同时它给出了本项目的真实失败成本：影响面不是"少个字段"，而是
   **DNS hijack / fakeip / QUIC / 所有 selector 一起坏**——而且只有用户报 bug 才发现。

   （次级但实用：subconverter 的 `UAMatchList` + `verGreaterEqual()`
   （`interfaces.cpp:53-108`）是"从 User-Agent 推断目标内核版本"的可借鉴实现，
   sublink-worker 的 `resolveSingboxConfigVersion` 也做同一件事且更现代
   ——**含"解析失败就回落到安全档 1.12"这一防御式默认**。
   两者都证明：客户端 UA 能提供版本维度，这是本项目在 Phase 7 之后可用的真实输入源。
   但请照抄它的兜底，别照抄它"用版本决定丢节点"。）

## C3. 最该避免的 2 个坑

1. **坑 1：把"生成阶段"当作兼容性判断的发生地——`continue` / `delete` 一旦执行，损失就不可恢复。**
   subconverter 的 `proxyToSurge` 在 `surge_ver < 4` 时直接 `continue` 丢掉整个 VMess 节点
   （`subexport.cpp:845-846`），而 `surge_ver` 默认是 3（`interfaces.cpp:309`）——
   于是"用户没写 `&ver=4`"这个**参数缺失**被静默翻译成"你的节点不存在了"。
   sublink-worker 的 `delete sanitized.udp/network` 同理。
   **为什么对本项目致命**：这与"绝不静默丢失能力"直接冲突，而且**事后无法补救**——
   配置里已经没有那个节点的痕迹，客户端不可能再显示"这条损失了什么"。
   → 本项目的 compat **必须在生成之前、拿着完整 Node Profile 做判断**，
   并且**用"损失清单"而不是"删字段"来表达不支持**。这也正是 README 里
   "compat 永远不负责生成配置"这条纪律的技术理由，源码证据在此。

2. **坑 2：把"来源能力上限"硬编码成"项目能力上限"——即用错误的常量代替目标能力矩阵。**
   subconverter 没有 VLESS，社区解释是
   *"原生的 clash 内核还不支持 vless，所以作者干脆就没转换了，但 clash.meta 支持 vless，
   换内核之后其实是可以使用 vless 的"*（issue #611，2023-07，至今 open）。
   这是**把"某个内核在某个时刻的能力"当成了转换器自己的常量**：
   内核演进了（clash → mihomo），转换器既不知道也不报告，用户拿到的是静默变少的订阅。
   sublink-worker 的同型病是 `default: return proxy`（未知类型原样透传）——
   两个方向相反，病根相同：**没有"目标能力"这份数据，只有"作者当时知道什么"这段代码**。
   → 本项目必须把能力做成**带版本的数据（Capability Registry）**，
   并且显式区分"目标不支持"与"我们尚未收录（UNKNOWN）"——
   后者绝不能被当成前者，否则就是拿猜测冒充结论（违反 README 原则 2）。

## C4. 本项目可直接引用的"反面证据"清单

写设计文档时可直接引用的、已核实的硬证据：

| 主张 | 证据 |
|---|---|
| "能生成合法配置" ≠ "能用" | subconverter `buildSingBoxTransport` `default: break`（`subexport.cpp:2276`）+ 调用方 `if (!transport.ObjectEmpty())`（`:2403`）→ 未知 transport 的节点被输出成纯 TCP |
| 参数缺失会被翻译成节点消失 | `intSurgeVer` 默认 3（`interfaces.cpp:309`）+ `surge_ver < 4 → continue`（`subexport.cpp:845`） |
| 未知 = 丢弃（无第三种状态） | `subparser.cpp:2658`（`Type == Unknown → continue`）、`ProxyParser.js:33`（`return undefined`） |
| 注释是唯一的不支持提示 | `SurgeConfigBuilder.js:132` |
| 提示信息本身会污染语法 | `SurgeConfigBuilder.js:31-40`（issue #299 的修复） |
| 字段同名而语义相反 | `test/issue-297-vmess-network.test.js` 注释 + `SingboxConfigBuilder.js:130-131` |
| 未验证的"安全假设"会变成线上事故 | `test/issue-388-trojan-tls.test.js`（trojan 省略 `security` 导致 sing-box 起不来） |
| "未知类型就忽略"曾被写成规格 | `test/yaml-parsing.test.js:76-79` |
| 上游项目自己也不知道内核版本 | subconverter：仅 Surge ver；sublink-worker：仅 sing-box tier，且都不参与节点判定 |

# D. UNKNOWN（未验证事项，**共 15 条**）

**关于 subconverter（6 条）**

1. **未运行任何内核。** "生成的配置内核能不能接受"未经实测；本文对内核行为的陈述
   一律是引用**项目自己的注释或注释性代码**，不是我的实测结论。
2. `subexport.cpp` 共 2659 行，我按 grep + 定向精读覆盖了字段传播相关的全部位置
   （`Fingerprint`/`Alpn`/`ServerName`/`writeLog`/`continue` 全量枚举），
   但**未逐行通读全文**——在这之外的丢字段点不能 100% 排除。
3. **`base/` 模板层（jinja2 模板与 base 配置）未审计**：模板可能引入或吞掉字段，
   本文结论仅覆盖 `src/` 的解析与生成代码。
4. 解析侧 `explodeSurge` / `explodeQuan` / `explodeNetch` / `explodeSSD` 等分支只做了
   定向阅读，未逐一穷举其丢字段点（`explode()`/`explodeSub`/`explodeStdVMess`/`explodeClash` 已详查）。
5. **issue 评论未读完**：GitHub API 未认证限额（60/h）中途耗尽，
   #666（reality→sing-box）的正文与评论未取到；#611 只读了前 5 条评论。
   维护者对"是否打算支持 VLESS"的明确表态 **UNKNOWN**。
6. MetaCubeX/subconverter（社区推荐的 fork，见 #611）**未调研**——
   它恰好是"同一作者体系下按新内核能力重做"的样本，可能包含有价值的对照。

**关于 sublink-worker（9 条，由子代理明确记录于 `_notes-sublink-worker.md` 的 UNKNOWN 节）**

7. 内核侧接受度未验证（无 sing-box/mihomo/Surge 二进制）：
   具体包括 sing-box 是否接受 `transport.type: "xhttp"`、
   是否真的拒绝漏出的 `plugin`/`plugin_opts`/`tcp_fast_open`。
8. mihomo 是否接受没有 `xhttp-opts` 的 `network: xhttp` 未验证
   （可观测事实只有"path/host 不在输出里"）。
9. 线上 `sublink.works` 部署行为是否等同该 commit 未知；
   仓库外的文档（`sublink.works/guide/...`）**未抓取**，故"官方是否有已知限制页"未知。
10. `src/runtime/*`、`src/adapters/kv/*`、`src/services/*`、Hono JSX UI
    （`src/components/*`、`createApp.jsx` 路由之外的部分）、`src/config/ruleGenerators.js`
    未穷尽阅读——**理论上存在"别处会渲染损失提示"的可能**（但 i18n grep 未发现相关字符串，
    且路由不返回 diagnostics 通道）。
11. `test/`（38 文件 / 5023 行）按结构与 grep + 定向阅读，**未逐行读完**；
    若存在不叫 `round-trip`/`reparse`/`fidelity` 的保真断言，可能被漏掉。
12. `git log` 历史未挖掘，因此"某个字段处理是何时/为何被删除"（例如
    `utils.js:296-299` 被注释掉的 `utls` 块）的意图未知。
13. hy2 的 `up`/`down` 类型观察：真实执行显示 `up=100` 以字符串
    `up_mbps: "100"` 进入 sing-box 输出（`parseMaybeNumber` 只作用于 `upmbps` 别名，
    `hysteria2Parser.js:43-44`）；sing-box 是否接受字符串**未验证**。
14. `GET /xray` 对真实 Xray 客户端意味着什么未验证——
    代码只把输入 URI 行重新 Base64（share-link 列表，不是 Xray JSON 配置）。
15. 克隆是否完整（是否有 submodule / `.git` 排除文件）只做了外观检查，
    未运行 `git submodule status`；树内无 `node_modules`。

> **方法学备注**：subconverter 侧结论来自对 `/tmp/subconverter` 克隆的纯静态阅读；
> sublink-worker 侧在上述静态阅读之外，还由子代理**执行了未修改的 parser/builder 模块**
> （内存 Node resolve hook，stub 掉 js-yaml）来实证 B4 例子 1/2 的字段丢失，
> 并由我本人复核了其中 6 项关键断言（JS-not-TS、Surge 注释机制、
> `default: return proxy`、`.filter(p => p != null)`、
> `test/yaml-parsing.test.js` 的"忽略未知类型"断言、sing-box 版本档位）。
> 两个克隆均只读使用（`/tmp`），**未修改任何其它仓库**。
