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

## 待办（本文件引发的后续工作）

1. Capability Registry 的数据行必须包含：`valid_from` / `valid_until` / `timeline[]` /
   `time_gate` / `failure_mode` / `replaced_by` / `runtime_options[]` / `evidence[]`。
2. `check()` 签名落地为四参：`check(node, target, runtime_options=None, evaluated_at=None)`。
3. 状态机补 `silent_drop` / `runtime_fail` 的可达性：不能只靠配置校验。
4. sing-box 内核调研仍在进行；其结论需按同一模型（尤其"结构性差异"那类不可表达）并入。
