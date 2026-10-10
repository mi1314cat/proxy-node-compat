# Kernel Capability Registry

> 回答：**某一个具体内核，在某个实际运行环境下，对某个 Feature / Node 组合能做到什么程度。**
>
> 组织核心是 **Capability Rule（能力规则）**，不是版本数据库。
> **绝不建立"每个版本一条记录"的表**，也绝不为了整齐而补出没有证据的版本号。

---

## 1. 判定输入（Target 描述）

```yaml
target:
  kernel: mihomo                  # 内核身份
  distribution: upstream          # 发行版 / fork：upstream | sing-box-lx | <第三方>
  version: "1.19.32"              # 可选；缺省 = UNKNOWN
  build:                          # 可选；缺省 = UNKNOWN
    tags: [with_gvisor]           # sing-box 会自报 Tags:，可直接读
    platform: linux/amd64
  runtime_options:                # 第三维：运行期选项（Phase 1: xray-knife 的 --insecure）
    allow_insecure: false
  evaluated_at: "2026-10-10"      # 第四维：时间闸门（Phase 1: Xray allowInsecure 的日期行为）
```

**缺省即 UNKNOWN，不即"默认支持"。** 任何一维缺失都可能把结论降级为 `UNKNOWN`。

---

## 2. 能力层级（levels）——"支持"必须分层

```
parse     解析器认不认这个字段/链接
config    配置校验能不能过（xray -test / mihomo -t / sing-box check）
uri       URI 能不能表达（独立的第三张表，见 uri-representation.md）
runtime   真的跑起来能不能用
semantic  跑起来之后语义是否与节点原意一致
```

`能解析 ≠ 能配置 ≠ URI 能表达 ≠ 实际能运行 ≠ 语义正确`（Phase 1 实证）。

**判定结果按层给**，不允许只给一个总的状态：

```yaml
levels:
  parse:   SUPPORTED
  config:  SUPPORTED
  uri:     NOT_REPRESENTABLE
  runtime: UNKNOWN
  semantic: UNKNOWN
```

---

## 3. 状态枚举

```yaml
status:
  SUPPORTED               # 该层无损可用
  SUPPORTED_WITH_WARNING  # 可用，但有需要注意项（例如"中间版本未逐版验证"）
  SUPPORTED_WITH_LOSS     # 可用，但**确定会丢能力**（必须列出 losses[]）
  UNSUPPORTED             # 明确不可用（必须有 reason_code）
  UNKNOWN                 # 证据不足 —— **合法且鼓励的答案**
```

`SUPPORTED_WITH_LOSS` 必须带**逐条**的损失，只给状态码是不够的
（Phase 1 反例：v2rayN 的 sing-box 路径静默丢掉 `vcn/pcs/spx/pqv/fm` 五个字段且零告警）。

---

## 4. 失败模式（failure_mode）

```yaml
failure_mode:
  hard_error       # 配置期拒绝
  silent_ignore    # 字段不认识 → 忽略（可能回落默认值）
  silent_drop      # 字段存在、解析器也认，但内核不再读它
  runtime_fail     # 配置合法，拨号时才失败
```

`silent_*` 在最终结果里**必须升级成 `SUPPORTED_WITH_LOSS`**，不能显示成 `SUPPORTED`。
一条规则可以在不同版本区间有不同的 `failure_mode`（见 §6 三段式）。

---

## 5. 规则形状（证据决定精度）

```yaml
- rule_id: mihomo.transport.xhttp
  target: {kernel: mihomo, distribution: upstream}
  selector:
    feature: standard:xhttp          # 或 protocol / 字段 / 组合（§9）

  # ---- 精度由证据决定，三种写法都合法 ----
  # (a) 证据给出确切边界
  segments:
    - range: "< 1.19.22"
      verdict: {config: UNSUPPORTED, runtime: UNSUPPORTED}
      failure_mode: silent_ignore    # 未知 network 值 → 静默按 tcp
      evidence: [e-mihomo-network-lax]
    - range: ">= 1.19.22"
      verdict: {config: SUPPORTED, runtime: SUPPORTED}
      evidence: [e-mihomo-xhttp-loopback, e-mihomo-xhttp-src]

  # (b) 只知道"旧有 / 新无"，中间未知 —— 必须这样写，不许补版本号
  # segments:
  #   - {range: "<= 1.19.20", verdict: {...}, evidence: [e-old]}
  #   - {range: ">= 1.19.29", verdict: {...}, evidence: [e-new]}
  # transition: UNKNOWN
  # unknown_range: [{range: ">1.19.20, <1.19.29", why: "无任何一版被验证"}]

  # (c) 完全没有版本信息
  # evidence_only: true
  # verdict_for_any_version: UNKNOWN
  # open_questions: ["哪个版本引入？"]

  unknown_distribution_policy: UNKNOWN   # 未覆盖的 fork 不得默认继承上游
```

`unknown_distribution_policy` 默认 `UNKNOWN`：**fork ≠ 上游**。
Phase 1 实证：`sing-box-lx`（Leadaxe）带 XHTTP/AmneziaWG2/MASQUE，上游 sing-box 完全没有。
若确有证据证明某 fork 与上游一致，用 `inherits: upstream` + `evidence` 显式声明。

---

## 6. 三段式与时间闸门（真实案例）

### 6.1 三段式（Xray mKCP header/seed）

```yaml
- rule_id: xray.transport.mkcp.header_seed
  segments:
    - {range: "<= 26.1.23", verdict: SUPPORTED,             evidence: [e-xray-mkcp-old]}
    - {range: ">= 26.2.6, <= 26.9.8", verdict: UNSUPPORTED, failure_mode: hard_error,  evidence: [e-xray-mkcp-err]}
    - {range: ">= 26.9.30", verdict: UNSUPPORTED,           failure_mode: silent_drop, evidence: [e-xray-mkcp-silent]}
  unknown_range: [{range: ">26.1.23, <26.2.6", why: "边界由 release note 给出但未逐版验证"}]
```

同一能力在三个区间是**三种不同行为**（含"静默丢弃"），单一布尔值无法表达。

### 6.2 时间闸门（Xray allowInsecure）

```yaml
- rule_id: xray.tls.allow_insecure
  time_gated: true          # ★ 判定依赖 evaluated_at
  segments:
    - {range: ">= 26.2.6, <= 26.5.9", verdict: SUPPORTED_WITH_WARNING,
       condition: {evaluated_at_before: "2026-06-01T00:00:00Z"},
       note: "系统时间早于该时刻才警告+生效；之后硬报错"}
  # 未覆盖的 (版本 × 日期) 组合 → UNKNOWN
```

**引擎必须把 `evaluated_at` 纳入缓存键**：同内核同配置，日期不同结论不同。

### 6.3 构建标签（sing-box）

```yaml
- rule_id: singbox.feature.reality
  conditions:
    build_tags_required: [with_utls]
  segments:
    - {build: {tags_has: with_utls},    verdict: {config: SUPPORTED, runtime: SUPPORTED}}
    - {build: {tags_lacks: with_utls},  verdict: {config: UNSUPPORTED, runtime: UNSUPPORTED},
       failure_mode: runtime_fail, reason_code: BUILD_NOT_ENABLED}
  # build 未知（拿不到 Tags:）→ UNKNOWN，不许假设官方源码=用户装的那个二进制
```

---

## 7. 语义不一致（semantic mismatch）

字段名相同 ≠ 语义相同。Registry 必须能记录：

```yaml
- rule_id: singbox.transport.network_tcp_semantics
  feature: standard:transport.tcp
  mismatch: semantic_inversion
  detail: "sing-box 写 network:'tcp' 会**关闭 UDP**（连带 DNS hijack/fakeip/QUIC/selector 失效）；
           同一字段在 Clash/mihomo 无此副作用"
  verdict: SUPPORTED_WITH_WARNING
  evidence: [e-sublink-issue297]
```

`mismatch` 取值：`semantic_inversion` | `semantic_mismatch` | `behavioral_difference`。

---

## 8. 未移除但不可达 / 从未存在 / 被移除 —— 三种要分清

Phase 1 的 `sub2sing-box` 给出天然三分法，必须进 `reason_code`：

| 情形 | reason_code | 例子 |
|---|---|---|
| 内核某版本移除了它 | `KERNEL_REMOVED` | Xray 26.x 移除 HTTP(h2) transport |
| 内核从来没有 | `KERNEL_NEVER_SUPPORTED` | sing-box 无 xhttp（任何版本） |
| URI 表达不了（与内核无关） | `URI_NOT_REPRESENTABLE` | snell 没有通用分享链接格式 |

混为一谈就会得出"sing-box 不支持 snell"这种错结论。

---

## 9. 组合能力（Combination Capability）

**禁止**把单点能力做与运算：`vless ✅ + reality ✅ + xhttp ✅ ⇒ 组合 ✅`。

```yaml
- rule_id: xray.combo.reality_transports
  selector:
    all_of_features: [standard:reality]
    protocol: standard:vless
  constraint:
    allowed_transports: [standard:transport.tcp, standard:transport.xhttp, standard:transport.grpc]
  otherwise: {verdict: UNSUPPORTED, failure_mode: hard_error, reason_code: SEMANTIC_MISMATCH}
  evidence: [e-xray-reality-transports]
```

AnyReality 走的就是这条路（`mi1314cat:anyreality.ss-reality` 的 `requires`/`excludes`），
**不需要任何 `if feature == "anyreality"` 的分支**。

---

## 10. Reason taxonomy（保持可维护，不无限扩张）

```yaml
reason_code:
  KERNEL_REMOVED                 # 曾支持，该版本已移除
  KERNEL_NEVER_SUPPORTED         # 从来没有
  URI_NOT_REPRESENTABLE          # URI 层表达不了（与内核无关）
  VERSION_BELOW_INTRODUCED       # 版本低于引入点（有证据时）
  VERSION_ABOVE_REMOVED          # 版本高于移除点（有证据时）
  BUILD_NOT_ENABLED              # 构建标签/可选依赖缺失
  PLATFORM_NOT_SUPPORTED         # 平台限制
  RUNTIME_CONDITION_NOT_MET      # 需要额外运行期条件（如 reality 需 client-fingerprint）
  SEMANTIC_MISMATCH              # 能跑但语义不同
  UNKNOWN_CAPABILITY             # 证据不足
```

新增一个 code 的门槛：**必须能对应到一类不同的处理动作**（客户端 UI 行为不同），否则不新增。

---

## 11. 架构审查问题（本阶段必须回答）

> 明天增加一个**完全未知的内核**、一个**未知协议**、一个**新 fork**、一个**新的自定义 Feature**，
> 这套模型还能存下它、标记它、等未来补能力吗？需要重构吗？

| 变化 | 需要做什么 | 需要重构吗 |
|---|---|---|
| 未知内核 | 加一份 `target.kernel` 数据文件（哪怕只有 `evidence_only: true` + 全 UNKNOWN） | ❌ |
| 未知协议 | profile 的 `protocol.id` 用 `unknown:<hash>` / `<vendor>:`；`raw.fields` 已保存原文 | ❌ |
| 新 fork | `distribution:` 新值；`unknown_distribution_policy` 默认 UNKNOWN 已经处理"没数据"的情况 | ❌ |
| 新自定义 feature | `features[]` 加一条 `<vendor>:<name>`；约束用 `requires/excludes` 表达 | ❌ |
| 新能力层级 | ⚠️ 若新增"层"需要改 Evaluation 的 levels 枚举（低频、可接受） | ⚠️ 小改 |
| 新失败模式 | 同上，需扩 `failure_mode` 枚举 | ⚠️ 小改 |

**结论：不需要重构 Universal Node Profile。** 前四类（内核/协议/fork/feature）全部是**加数据**；
只有"新增能力层级"或"新增失败模式"这种**认识论级别的变化**才动枚举，而那种变化本身就是
我们需要显式承认的（不允许悄悄塞进已有取值里）。

**唯一的前置条件是**：任何未知输入都必须在 `raw` 或 `extensions` 里留下原文 ——
这是 Node Profile 的不变式 I2，也是这套模型能"等待未来补充能力"的根本原因。
