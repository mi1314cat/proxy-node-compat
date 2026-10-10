# 真实案例验证（Phase 2/3 设计验收）

14 个案例全部来自 Phase 1 的实证（真内核 / 源码 / 我们自己的仓库），
不是构造出来的假想。每条都给出 **profile 片段 → target → 预期结果**，
用来验证模型"能不能自然得出正确答案"，尤其是**能不能自然地得出 UNKNOWN**。

---

## 1. VLESS + TCP + Reality（三家都支持）

```yaml
profile: {protocol: standard:vless, features: [standard:transport.tcp, standard:reality]}
target:  {kernel: singbox, version: "1.14.2", build: {tags: [with_utls]}}
```
```yaml
status: SUPPORTED
levels: {config: SUPPORTED, uri: FULL, runtime: SUPPORTED}
```
证据：三家真内核 `check` 全部接受（`research/empirical/probe-results.json`）。
注意 build 维度：若 `tags` 缺 `with_utls` → `BUILD_NOT_ENABLED`（案例 14）。

---

## 2. VLESS + XHTTP（跨内核差异最大的一条）

```yaml
profile: {protocol: standard:vless, features: [standard:xhttp]}
```
| target | 结果 |
|---|---|
| `mihomo 1.19.32` | `SUPPORTED_WITH_WARNING`（runtime 有回环证据；但 1.19.22–1.19.31 未逐版验证）+ `warnings[VERSION_NOT_EXACTLY_PROBED]` |
| `singbox 1.14.2` | `UNSUPPORTED` + `KERNEL_NEVER_SUPPORTED`（全树 grep 0 命中，任何版本都没有） |
| `singbox-lx`（LxBox 的 fork） | `UNKNOWN`（有 XHTTP 的公开描述，**未读源码、未实测**）→ 不许默认继承上游结论 |
| `mihomo 1.19.20` | `SUPPORTED_WITH_LOSS` + `silent_ignore`（未知 network 值 → 静默按 tcp，链接看着正常但连不上） |

---

## 3. VLESS + mKCP（三段式）

```yaml
profile: {protocol: standard:vless, features: [standard:mkcp]}
```
| target | 结果 |
|---|---|
| `xray <= 26.1.23` | `SUPPORTED` |
| `xray 26.2.6–26.9.8` | `UNSUPPORTED` + `hard_error`（配置期报错，用户看得见） |
| `xray >= 26.9.30` | `SUPPORTED_WITH_LOSS` + **`silent_drop`**（字段还在结构体里但不读不校验） |
| `mihomo 1.19.32` | `SUPPORTED_WITH_LOSS` + `silent_ignore`（`network: mkcp` 未知 → 按 tcp） |
| `singbox 1.14.2` | `UNSUPPORTED` + `KERNEL_NEVER_SUPPORTED`（`unknown transport type: kcp`） |

→ 同一个节点在五个目标上得到**五种**结果；单一布尔值无法承载。

---

## 4. AnyReality（我们自己，三个变体）

```yaml
# 变体 1
profile:
  protocol: standard:shadowsocks2022
  features:
    - standard:reality
    - {id: mi1314cat:anyreality.ss-reality,
       requires: [standard:shadowsocks2022, standard:reality]}
```
| target | 结果 |
|---|---|
| `xray 26.3.27` | `SUPPORTED_WITH_WARNING`（配置 `Configuration OK`；运行层回环**未跑通** → 见 `unknowns`） |
| `singbox 1.14.2` | `UNSUPPORTED` + `KERNEL_NEVER_SUPPORTED` —— **实测 `FATAL: unknown field "tls"`**（ss 出站没有 tls 字段） |
| `mihomo 1.19.32` | `UNKNOWN` —— 配置层接受（`-t` 通过）但该内核不校验此类字段，运行层未定论 |
| `mi1314cat` 自己的 X 客户端 | `SUPPORTED_WITH_LOSS` + `losses[URI_NOT_REPRESENTABLE]`（`ss://` 装不下 reality 参数） |

**模型里没有任何 anyreality 分支**：它就是"标准协议 + standard:reality + 一个 vendor 特征"。
▶ 这条同时推翻了我们自己仓库里的一句注释（`conf/Shadowsocks.sh:396` 称 sing-box 可直接叠加 Reality）。

---

## 5. ECH（三个内核表示法都不同）

```yaml
profile: {protocol: standard:vless, features: [standard:tls, standard:ech]}
```
| target | 结果 | 说明 |
|---|---|---|
| `xray` | `SUPPORTED_WITH_WARNING` | 字段 `echConfigList` 收 base64；**对内容不校验**（编造的 base64 也 `Configuration OK`）→ 静态层只能给 `accepted_unverified` |
| `mihomo` | `SUPPORTED` | `ech-opts.config` 收 **base64**；喂非法 base64 会被明确拒绝 |
| `singbox` | `SUPPORTED` | `tls.ech.config[]` 要 **PEM**（`-----BEGIN ECH CONFIGS-----`）；喂 base64 → `FATAL: invalid ECH configs pem` |

→ 同一个能力、三套表示法 → 正好验证"Kernel Representation 必须独立建模"。
若给 sing-box 喂 base64：`UNSUPPORTED` + `SEMANTIC_MISMATCH`（表示法不匹配，不是能力缺失）。

---

## 6. 自定义未知 Feature

```yaml
profile:
  protocol: standard:vless
  features: [{id: "mi1314cat:magic-transport", presence: EXPLICIT, provenance: USER_DEFINED}]
  extensions: [{key: magicMode, value: "turbo", source: URI}]
target: {kernel: mihomo, version: "1.19.32"}
```
```yaml
status: UNKNOWN
reason_codes: [UNKNOWN_CAPABILITY]
message: "目标内核是否支持 mi1314cat:magic-transport 未知（我们自己的扩展，第三方内核没有对应物）"
raw_uri: "vless://...#name"        # ★ 原样保留，换内核后仍可用
```
**这是"未知 ≠ 不支持"的核心用例**：mihomo 既没有实现它、也不知道它是什么 →
不能判 `UNSUPPORTED`，只能 `UNKNOWN`。节点信息一字未丢。

---

## 7. 已明确移除的 Feature（Xray 26.x 的 HTTP/h2）

```yaml
profile: {protocol: standard:vless, features: [standard:transport.http_h2]}
target: {kernel: xray, version: "26.3.27"}
```
```yaml
status: UNSUPPORTED
reason_codes: [KERNEL_REMOVED]
message: "The feature HTTP transport ... has been removed and migrated to XHTTP stream-one H2 & H3"
```
同一 profile 在 `mihomo 1.19.32` / `singbox 1.14.2` 上是 `SUPPORTED`
（两家仍支持 h2）→ **跨内核方向性差异**的典型。

---

## 8. 从未支持的 Feature（sing-box 的 xhttp / SSR）

```yaml
profile: {protocol: standard:vless, features: [standard:xhttp]}
target: {kernel: singbox}
```
```yaml
status: UNSUPPORTED
reason_codes: [KERNEL_NEVER_SUPPORTED]
```
对照 `sub2sing-box` 的三分法：`ssr outbound was removed in 1.6.0`（KERNEL_REMOVED）
与 `juicity: no juicity outbound`（KERNEL_NEVER_SUPPORTED）是**不同的 reason_code** ——
客户端的 UI 文案与"要不要建议用户换内核"的决策不同。

---

## 9. 内核支持但 URI 无法完整表达（snell / ss+reality）

```yaml
profile: {protocol: standard:snell, auth: {...}, features: [standard:obfs]}
target: {kernel: singbox, version: "1.14.2"}
```
```yaml
status: UNSUPPORTED
reason_codes: [URI_NOT_REPRESENTABLE]      # ★ 与内核无关
message: "snell 没有通用分享链接格式 —— 问题在链接，不在内核"
```
第二个变体（ss+reality）则是**内核支持 + URI 装不下**：
```yaml
target: {kernel: xray, version: "26.3.27"}
status: SUPPORTED_WITH_LOSS
losses: [{feature: standard:reality.public_key, what: "ss:// 无法表达", impact: CONNECTIVITY}]
```
→ 这两条正好验证 `URI Representation` 必须独立成表。

---

## 10. `silent_ignore`（mihomo 未知 transport）

```yaml
profile: {protocol: standard:vless, features: [standard:xhttp]}
target: {kernel: mihomo, version: "1.19.20"}
status: SUPPORTED_WITH_LOSS
failure_mode: silent_ignore
losses: [{feature: standard:xhttp, what: "network 值不被校验 → 静默按 tcp", impact: CONNECTIVITY}]
```
回环实证：把 `network` 写成**根本不存在的值**，mihomo `-t` 依然成功**且真的连通了**一个纯 tcp 服务端
→ 证明它是"静默当默认值用"，不是"拒绝"。

---

## 11. `silent_drop`（Xray ≥26.9.30 的 mKCP header/seed）

```yaml
profile: {protocol: standard:vless, features: [standard:mkcp, standard:mkcp.header_seed]}
target: {kernel: xray, version: ">= 26.9.30"}
status: SUPPORTED_WITH_LOSS
failure_mode: silent_drop
losses: [{feature: standard:mkcp.header_seed, what: "结构体字段仍在，但 Build 不读不校验", impact: CONNECTIVITY}]
```
> ⚠️ 本条的 `>= 26.9.30` 边界来自 Phase 1 的源码调研（**不是**我们实测），
> 因此该规则的 `evidence.type = SRC`、`confidence = MEDIUM`，
> 且必须附 `unknown_range`（26.9.8 → 26.9.30 之间未逐版验证）。

---

## 12. `runtime_fail`（配置合法、拨号才炸）

```yaml
profile: {protocol: standard:vless, features: [standard:reality]}   # 注意：缺 client_fingerprint
target: {kernel: mihomo, version: "1.19.32"}
status: SUPPORTED_WITH_LOSS
failure_mode: runtime_fail
reason_codes: [RUNTIME_CONDITION_NOT_MET]
losses: [{feature: standard:reality, what: "有 reality-opts 但没有 client-fingerprint → 运行期才报错",
          impact: CONNECTIVITY}]
```
Phase 1 源码确证：`-t` 检测不到这一类。**因此静态探针的 accepted 必须降级为 `accepted_unverified`。**

---

## 13. 版本边界未知的 Feature（★ 本阶段的关键用例）

**设定**：我们只有两条证据 ——

- 某内核 **1.18.0** 的源码里有 `xhttp-opts.extra` 的处理分支；
- 同一个内核 **1.19.32** 的源码里已经没有它（或行为已变）。

**我们不知道中间哪一版发生变化。**

```yaml
- rule_id: <kernel>.xhttp.extra
  segments:
    - {range: "<= 1.18.0",  verdict: SUPPORTED,   evidence: [e-src-1.18.0]}
    - {range: ">= 1.19.32", verdict: UNSUPPORTED, failure_mode: silent_drop,
       evidence: [e-src-1.19.32]}
  transition: UNKNOWN                       # ★ 绝不补 removed_at
  unknown_range:
    - {range: "> 1.18.0, < 1.19.32", why: "两端各有源码证据，中间无任何一版被验证"}
```
于是：

```yaml
target: {kernel: <kernel>, version: "1.19.5"}
status: UNKNOWN
reason_codes: [UNKNOWN_CAPABILITY]
warnings: [{code: BETWEEN_EVIDENCE_POINTS, detail: "1.18.0 支持、1.19.32 不支持；中间未验证"}]
```

**这条用例验收的就是**：模型能否**自然**得出 UNKNOWN，而不是被迫编一个 `removed_at`。
如果实现里出现"因为 1.19.32 不支持，所以 1.19.5 也不支持"这种推断，就是设计失败。

---

## 14. 不同 fork / build / platform 导致能力不同

```yaml
profile: {protocol: standard:vless, features: [standard:xhttp]}
```
| target | 结果 | reason_code |
|---|---|---|
| `singbox 1.14.2, tags=[with_utls]` | `UNSUPPORTED` | `KERNEL_NEVER_SUPPORTED` |
| `singbox-lx`（fork） | `UNKNOWN` | `UNKNOWN_CAPABILITY`（fork ≠ 上游，默认不继承） |
| `singbox 1.14.2` + `standard:reality` + **tags 无 `with_utls`** | `UNSUPPORTED` | `BUILD_NOT_ENABLED` |
| 同上但 **tags 未知**（拿不到 `Tags:`） | `UNKNOWN` | `UNKNOWN_CAPABILITY` |
| `mihomo` on `windows/arm64`（假设某能力有平台限制） | `UNSUPPORTED` | `PLATFORM_NOT_SUPPORTED` |

→ 验证 §1 的四维输入 + §6.3 的 build 条件 +
"**官方源码支持 ≠ 用户装的那个二进制支持**"。

---

## 验收结论

| 要求 | 是否满足 | 靠什么机制 |
|---|---|---|
| 未知内核/协议/fork/feature 不改架构 | ✅ | `raw` + `extensions` + 命名空间 + 全 UNKNOWN 的规则文件 |
| 自然得出 UNKNOWN（不编版本号） | ✅ | 案例 13 的 `transition: UNKNOWN` + `unknown_range` |
| "不知道"与"不支持"分开 | ✅ | 案例 4/6/14（mihomo+AnyReality、自定义 feature、fork） |
| 分层结论（parse/config/uri/runtime/semantic） | ✅ | 案例 2/9/12（静态通过但运行未知、URI 装不下、运行期才炸） |
| 损失逐条可读 | ✅ | 案例 9/10/11/12 的 `losses[]` |
| 组合不被折叠 | ✅ | 案例 1/2/3 的 transport×security 组合差异 |
