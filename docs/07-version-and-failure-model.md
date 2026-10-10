# 07 · 版本维度与失败模式模型

> 这份文件是为了回答一个被生态**普遍忽略**的问题：同一份配置，换个内核版本，
> 结果可能从「能用」变成「报错」，再变成「静默失效」。
>
> 结论来自 Xray 源码级调研（`research/kernel-xray.md`，114 处 `[src]`）＋我们自己 63 条真内核实测。

---

## 1. 失败模式不是两态，而是四态

生态里只有"通过/不通过"两态，但真内核的行为至少有四种。**必须显式建模**，否则
"校验通过"会被误当成"支持"。

| failure_mode | 含义 | 判定方式 | 实例（真内核证据） |
|---|---|---|---|
| `hard_error` | 配置期直接拒绝 | Tier A 就能抓到 | sing-box 未知 transport → `FATAL`；Xray 26.3.27 移除 h2 → `Failed to build stream settings` |
| `silent_ignore` | **字段不认识，被忽略**（可能回落默认值） | **Tier A 抓不到**，必须靠能力表或 Tier B | mihomo 未知 `network` → 静默当 tcp（实测 4/4 连通） |
| `silent_drop` | **字段存在、解析器也认，但内核不再读它** | 只有源码/版本表能抓 | Xray ≥26.9.30：mKCP `header`/`seed` 字段还在结构体里，但 Build 不读不校验 |
| `runtime_fail` | 配置合法，**拨号时才失败** | 只有 Tier B 能抓 | Xray Vision 在 `security∉{tls,reality}` 时不是配置错，是拨号时才报；ECH 失败时塞无效 ECHConfig 让连接失败 |

**对引擎的硬要求**：

- 静态层结论（Tier A）只能作为**下界**：`hard_error` 可信，其余一律降级为
  `accepted_unverified`（我们的探针已经这么做了：`✅?`）。
- 能力表里每一行都要带 `failure_mode`，客户端才知道"这条不支持"是启动就报错，
  还是"能启动但永远连不上"（后者才是用户最痛的）。

---

## 2. 版本门槛有五种形态，其中一种与**日期**有关

`docs/00-design-principles.md` P4 列的 `newly supported / deprecated / removed /
renamed / behavior changed` 还不够。Xray 调研给出了更细的形态：

| 形态 | 实例 | 数据字段 |
|---|---|---|
| 新增（版本点） | `streamSettings.method` 自 **v26.7.28** 才有 | `valid_from: 26.7.28` |
| 移除（版本点） | HTTP(h2) transport 在 26.x 被移除，迁移到 XHTTP | `valid_until: 26.x` |
| **三段式**（生效→报错→静默） | mKCP `header`/`seed`：≤26.1.23 生效 → 26.2.6–26.9.8 **硬报错** → 26.9.30/main **静默丢弃** | `timeline[]`，每段一个 `failure_mode` |
| 参数被取代 | mKCP `congestion`/`readBufferSize`/`writeBufferSize` 在 26.7.11 被 `cwndMultiplier`/`maxSendingWindow` 取代，老字段静默忽略 | `replaced_by` |
| **时间闸门**（同二进制、同配置、换个日期结果不同） | `allowInsecure`：26.2.6–26.5.9 期间**只有系统时间 < 2026-06-01 UTC 才警告+生效**；26.7.11+ 无条件硬报错 | `time_gate: {until: 2026-06-01}` |

> ⚠️ **时间闸门是本次调研最反直觉的发现**：判断结果依赖**当前日期**。
> 因此 `check(node, kernel, version)` 的签名不够，需要能传入"评估时刻"
> （默认取系统时间，可注入以便测试复现）。

---

## 3. 判定输入是**三维**，不是两维

`xray-knife` 的函数签名 `SingboxReason(profile, **insecure**)` 说明了一件重要的事：
**"这个节点能不能完整使用"还取决于运行期选项**。

```
check(node, kernel_release, runtime_options, evaluated_at)
                    │              │            │
                    │              │            └─ 时间闸门（§2）
                    │              └─ 例如 --insecure / 是否允许跳过证书校验
                    └─ (kernel, variant/fork, version)
```

- 我们自己的客户端就有这类选项（`--keep-unsupported`、Browser Dialer 开关、多出站模式）。
- 忽略它会导致同一个节点在两个客户端里得到不同结论却用同一套数据 —— 必须进签名。

---

## 4. presence 必须显式化（三个 Go 项目全部栽在这里）

调研的三个 Go 项目**100% 同病**：用"零值即未设置"表示字段缺失，于是

- 用户显式写 `false` / `0` / `""` 与"根本没写"**无法区分**；
- 一旦丢失，"这个字段用户到底有没有要求"就再也答不出来 →
  **语义上就写不出 loss 报告**（不知道丢的是"用户的要求"还是"本来就没有"）。

它们都留下了"知道错了"的痕迹：`xray-knife` 在 slice 方向打补丁（注释 "a list's zeros can matter"）、
`proxyparser` 实现了 `(val, present)` 三态又在调用点用 `_` 丢掉、`sub2sing-box` 为去重键打补丁。

**我们的要求**：模型内部一律用存在性显式表示（`present: bool` 或 `Optional`），
并且额外保留 `unconsumed_params[]`（解析器读了但没用上的参数）—— 这是
"未知 ≠ 丢失"的落地点。

---

## 5. URI 表达力是**独立的第三张表**

Xray 调研的关键事实：**Xray-core 全树 grep `vless://|vmess://|trojan://|ss://|shareLink` → 0 命中**。
内核**根本不解析也不生成分享链接**。所以：

```
Kernel Capability       内核能不能做（按版本）
URI Spec                链接规范能不能表达（按参数加入规范的时间）
Client Implementation   某个客户端实际怎么解析（可能不完整/有别名）
```

三张表**必须分开**，否则会把"链接表达不了"误判成"内核不支持"。URI 参数的时间线同样重要：

| 参数 | 进规范时间 | 老客户端行为 |
|---|---|---|
| `ech` | 2025-07-26 | 按 SIP002 精神**静默忽略** |
| `pqv`（后量子验证） | 2025-07-22 | 同上 |
| `pcs` / `vcn` | 2026-01-18 / 2026-02-02 | 同上 |
| `fm`（finalmask） | 2026-01-31 | 同上 |
| `mtu` / `tti`（mKCP） | 2026-03-27 | 同上 |

→ `uri_representation` 不能只标 `full/partial/none`，还要带**"从哪个规范版本起可表达"**，
因为"现在能表达"和"对方的客户端认识这个参数"是两件事。

---

## 6. 组合约束必须进 Registry（不是 if）

Xray 的硬约束实例：**REALITY 只允许 RAW / XHTTP / gRPC**，其它传输组合在配置期硬报错。

这类约束是 `feature × feature` 的关系，不是单点能力。Registry 需要表达：

```
when: {feature: standard:reality}
allows_transport: [tcp(raw), xhttp, grpc]
otherwise: hard_error
```

AnyReality（我们的 ss+reality / trojan+reality / anytls+reality）正好落在这个机制上 ——
**不需要为它写特例，只需要它的组合规则在表里**。

---

## 7. 我们自己代码里已经踩到的一条

`Client/lib/genconfig.py:90,123` 会生成 `streamSettings.method`：

```python
stream: dict = {"network": transport, "method": transport}
```

而调研结论是：**`method` 自 v26.7.28 才存在**。在最新稳定版 26.3.27 上它是**未知字段、
被静默忽略**（这也解释了我早先实测为什么 `Configuration OK` —— 通过不是因为字段被理解，
而是因为它被无视了）。

目前无害（`network` 已经表达了同样的信息），但它是一个**典型的"未来才有意义"字段**：
一旦我们的客户端跑在 26.7.28+，它的语义会突然生效。这类字段必须进能力表的
`valid_from`，否则以后无从解释"为什么老版本没问题、新版本行为变了"。

---

## 8. mihomo 的**结构性根因**（源码确证，v1.19.32）

前面说"不要用 `-t` 当判据"，这一节给出**为什么**——因为它不是 bug，是设计：

- `common/structure/structure.go` 的 decoder 把**没匹配上的输入键**收集进 `dataValKeysUnused`，
  只有当结构体带 `remain` tag 时才消费它。**mihomo 的 proxy option 无一使用 `remain`，
  也没有 `ErrorUnused` 开关** → 任何拼错/不认识的字段都被静默丢弃。
  顶层 `config/config.go:617` 的 `yaml.Unmarshal` 同样没开 `KnownFields`。
- 订阅解析层还会**主动产出内核不认的值**：`common/convert/v.go:110,127` 把 `type=httpupgrade`
  原样写成 `network: httpupgrade`，而 `adapter/` 下 **0 处**处理它 → httpupgrade 节点静默按 TCP 跑。
- `splithttp` 在 mihomo **全仓库 + 全历史 0 命中**（从未存在过）——
  我之前探针里那条"`network: splithttp` 也连通"，正确解释是**未知值回落 tcp**，而不是"支持旧名"。

### 8.1 字段名跨协议不一致（真实陷阱）

| 协议 | SNI 字段名 |
|---|---|
| vmess / vless | 只有 `servername` |
| trojan / hysteria2 / tuic / anytls | 只有 `sni` |

写错**不报错、只静默失效**。trojan 的结构体里**根本没有 `tls` 字段**。
→ 我们必须建**字段名规范化层**，并把"别名/正确名/写错的后果"进 diagnostics，
而不是把用户写错的名字直接传下去。

### 8.2 有些字段是**真校验**的（可以信任）

`xhttp-opts.mode` 在构造期就抛 `xhttp mode %s is not implemented yet`（`-t` 会失败）；
`mieru.transport` 必须恰好 `TCP`/`UDP`（大小写敏感）；snell `obfs-opts.mode`、hysteria2 `obfs` 均硬校验。
→ 能力表要逐字段标 `validation: strict | lax | none`，不能整内核一刀切。

### 8.3 "完整可用"必须叠加**运行期条件**

同一份通过的配置，仍可能因为运行期条件不满足而完全没用：

| 能力 | 需要的额外条件 | 不满足时 |
|---|---|---|
| Reality | 必须有 `client-fingerprint` | **运行期**才报错（`-t` 抓不到） |
| ECH | 必须 `tls: true`，且不能与 shadow-tls/restls/jls 同用 | 静默丢弃 |
| smux | 必须显式 `enabled: true` | 静默不复用 |
| `udp: false` | 在 hysteria/hysteria2/tuic/shadowquic/sudoku/openvpn 上被硬编码 `UDP: true` 抵消 | 用户关不掉 UDP |

→ 这直接印证 §3：`runtime_options`（乃至"用户意图是否被抵消"）必须进判定签名。

## 9. 两件可复用的东西

### 9.1 检测"死字段"的手法（silent_drop 的静态发现法）

`silent_drop`（字段存在但内核不再读）过去只能靠翻 release note 猜。mihomo 调研给出一个
**可机械执行**的判据：

> 在整个仓库里数某个结构体字段被引用的次数。**只有声明处 1 次 = 死字段**。

用这个方法确证：`vless.ws-headers` 在 v1.19.32 中**是死字段**（声明处之外全仓库 0 引用）。
→ 可以把它做成一个**自动化扫描**：对每个内核的每个 proxy option 结构体字段统计引用数，
引用数 ≤1 的字段自动进能力表的 `failure_mode: silent_drop` 候选，再人工确认。

（注意区分：`mux:` 这类**顶层块**不能用这个手法 —— 它可能在多个版本里都不存在，
所以只断言"当前版本中它是未知键、静默丢弃"，不推断历史。）

### 9.2 mihomo 版本门槛速查（源码/ release note 双重确认过的）

| 能力 / 字段 | 最早版本 | 在更老内核上的后果 |
|---|---|---|
| `client-fingerprint` | v1.14.2 | 未知键 → 静默丢弃 |
| `reality-opts` | v1.14.3 | 静默丢弃（且无 fingerprint 时**运行期**才报错） |
| `smux` 块 / `dialer-proxy` / `tfo` | v1.14.4 | 静默丢弃 |
| `mptcp` | v1.15.1 | 静默丢弃 |
| `ech-opts` | v1.19.9 | 静默丢弃 |
| **`xhttp`（network）** | **v1.19.22** | 未知值 → **静默按 tcp**，节点废掉但不报错 |
| `tlsmirror` | v1.19.28 | 静默丢弃 |
| `name-cert-verify` / `jls-opts` / `restls-opts` / `shadow-tls-opts` | v1.19.29 | **静默丢弃 → 节点"裸奔"**（用户以为有这层保护） |

弃用→移除两条时间线：`relay` 组 v1.18.6 弃用 → v1.19.17 移除；
`global-client-fingerprint` v1.19.19 弃用 → v1.19.27 移除。
新增 type 仍在持续出现（rematch v1.19.28、shadowquic v1.19.29、zerotier v1.19.30、easytier v1.19.31）
→ **能力表必须可增量维护**，这也是"版本维度不能漏"的最直接理由。

## 10. 能力键还要加第四维：**构建标签 / 平台**（sing-box 调研，含真 [test]）

sing-box 那份是唯一带**真 [test]** 的（自建两个二进制 + ~55 条 `check` 用例，并在官方 1.14.1 上交叉复现），
它给出一个把 §3 的签名再改一次的理由：

```
能力 = f(内核, 发行版/fork, 版本, 构建标签, 平台)
```

- Reality / uTLS 需要 `with_utls`；hysteria2 / tuic 需要 `with_quic`。
  缺标签时不是配置错，而是**运行期 FATAL**（`QUIC is not included in this build`）。
- 官方二进制的 `sing-box version` 会打印 `Tags:` → **能力识别层应当直接读它**，
  而不是只信版本号。

另外三条必须记下的事实：

1. **官方 sing-box 的 gRPC 不是标准 gRPC**：`grpc.go`（`with_grpc`）与 `grpc_lite.go`（无 tag）是两套实现，
   官方二进制符号表里只有 `v2raygrpclite`。→ "gRPC 校验通过"是**静态层幻觉**，Tier A 原理上抓不到。
2. **没有 Mux.Cool**：`protocol: "mux.cool"` → `FATAL unknown protocol`；只有 smux/yamux/h2mux。
   Xray 的 `mux.enabled` 映射到 sing-box 的 `multiplex` **语义不同构**（映射成默认 h2mux 会静默连不上）。
3. **sing-box 完全不解析分享 URI**（零 URI 解析、零 import 子命令），且 JSON 是**双层严格**
   （未知字段在顶层/outbound/transport/tls 任一层都 FATAL）→ **未知 URI 参数的处理必须发生在兼容层**，
   透传即 FATAL，没有"静默忽略"这个中间态。

### 10.1 对我们自己探针数据的两条修正（诚实记录）

- `research/empirical/probe-results.json` 里记的内核版本是探针**自报**的 `1.14.2`，
  而该路径的二进制在另一份调研中自报 `1.14.1`（tags 含 with_purego）→ 需要核对实际二进制来源。
- `transport.tcp` 用例对 sing-box 的 `accepted` **容易被误读**：sing-box 根本没有 `tcp` transport，
  写 `{"type":"tcp"}` 实测是 `FATAL`；该用例实际表达的是"**不写 transport**"。**用例需要改名**
  （`transport.none`），否则矩阵会让人以为 sing-box 支持 `tcp` transport。
- 同理 `advanced.mux` 用例把 Xray 的 `mux` 与 sing-box 的 `multiplex` 并列，
  **因此抓不到"语义不同构"这个风险** —— 需要拆成两个 feature 并补一条跨内核回环。

## 待办（本文件引发的后续工作）

1. Capability Registry 的数据行必须包含：`valid_from` / `valid_until` / `timeline[]` /
   `time_gate` / `failure_mode` / `replaced_by` / `runtime_options[]` / `evidence[]`。
2. `check()` 签名落地为四参：`check(node, target, runtime_options=None, evaluated_at=None)`。
3. 状态机补 `silent_drop` / `runtime_fail` 的可达性：不能只靠配置校验。
4. sing-box 内核调研仍在进行；其结论需按同一模型（尤其"结构性差异"那类不可表达）并入。
