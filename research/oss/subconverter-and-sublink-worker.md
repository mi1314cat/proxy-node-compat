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

`proxyToSingBox` 用 `buildSingBoxTransport()`（`subexport.cpp:2245-2281`）构造 transport 对象：

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

调用方（`:2403-2405`、`:2388-2390`）：

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
  （`surge_ver`，`ext.h` 无、见 `subexport.h:65` 的 `proxyToSurge(..., int surge_ver, ...)`），
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

<!-- B 部分（sublink-worker）与横向结论待补 -->
