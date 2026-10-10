# Compatibility Evaluation

> 把 Node Profile、Capability Registry、URI Representation 三者合成一个**结构化结论**。
>
> 回答：这个节点交给这个内核，在**当前版本 / build / platform / runtime / 评估时刻**下，究竟会发生什么。

---

## 1. 签名

```
evaluate(profile, target, options=None) -> EvaluationResult

target:
  kernel, distribution="upstream", version=None, build=None,
  runtime_options={}, evaluated_at=None      # None → 取当前时间
options:
  policy = strict | normal | permissive      # 筛选口径
  levels = [parse, config, uri, runtime, semantic]   # 默认全算
```

**四维输入全部参与缓存键**：`(kernel, distribution, version, build, runtime_options, evaluated_at)`。
原因（Phase 1 实证）：Xray `allowInsecure` 的行为**随系统日期变化**；
xray-knife 的 `SingboxReason(p, insecure)` 表明运行期选项也改变结论。

---

## 2. 结果结构

```yaml
status: SUPPORTED_WITH_LOSS            # 见 kernel-capability-registry.md §3
reason_codes: [RUNTIME_CONDITION_NOT_MET, URI_NOT_REPRESENTABLE]
message: "mihomo 1.19.32 可用；但 reality 在 ws 传输下不会被启用，且该链接无法表达 reality 参数"

levels:
  parse:   SUPPORTED
  config:  SUPPORTED
  uri:     NOT_REPRESENTABLE
  runtime: SUPPORTED_WITH_LOSS
  semantic: UNKNOWN

failure_mode: silent_ignore            # 见 registry §4
losses:                                # ★ 逐条，不是一句"有损失"
  - feature: standard:reality
    what: "network: ws 分支的 TLSConfig 不包含 Reality → 静默不启用"
    impact: SECURITY                   # SECURITY | CONNECTIVITY | PERFORMANCE | COSMETIC
    evidence: [e-mihomo-ws-reality]
  - feature: standard:reality.public_key
    what: "ss:// 无法表达 reality 参数"
    impact: CONNECTIVITY
    evidence: [e-sip002]
warnings:
  - code: VERSION_NOT_EXACTLY_PROBED
    detail: "仅验证过 1.19.32；1.19.22–1.19.31 未逐版验证"
unknowns:                              # ★ 未知不是空，是显式条目
  - what: "1.19.23–1.19.28 上 xhttp-opts.extra 的行为"
    why: "无证据"
detected_features:                     # 节点实际带了什么（供 UI 分组/筛选）
  - {id: standard:vless, presence: EXPLICIT}
  - {id: standard:xhttp, presence: EXPLICIT}
  - {id: mi1314cat:anyreality.ss-reality, presence: EXPLICIT}
evidence: [e-..., e-...]               # 支撑本次结论的证据（可追溯）
raw_uri: "vless://..."                 # 原样带回，永不丢
```

**`raw_uri` 与 `raw_fields` 必须随结果一起返回**（Node Profile 不变式 I1 的延续）：
客户端即使把节点判成 `UNSUPPORTED`，也必须能**原样保存**它，等将来换内核再用。

---

## 3. 判定优先级（冲突时的顺序）

```
1. 组合约束          （registry §9）        —— 组合不成立 → 直接 UNSUPPORTED（hard_error）
2. build / platform 条件（§6.3）           —— 缺标签 → BUILD_NOT_ENABLED / PLATFORM_NOT_SUPPORTED
3. 版本分段          （registry §5/§6）     —— 命中已知段用该段结论；落在 unknown_range → UNKNOWN
4. 运行期条件        （runtime_options）    —— 不满足 → RUNTIME_CONDITION_NOT_MET
5. 语义不一致        （semantic mismatch）  —— 升级为 SUPPORTED_WITH_WARNING 并说明
6. URI 表达力        （uri-representation） —— 损失并入 losses[]（不改变内核层结论）
```

规则：**任何一步得到 UNKNOWN，并且后续步骤无法把它变成确定结论时，最终状态取 UNKNOWN** ——
不允许用"其它维度都通过"来掩盖未知。

---

## 4. policy 与筛选

| policy | 保留 | 典型用途 |
|---|---|---|
| `strict` | 只有 `SUPPORTED` | 追求"一定不出问题"的批量导入 |
| `normal` | `SUPPORTED` + `SUPPORTED_WITH_WARNING` | 默认 |
| `permissive` | 上述 + `SUPPORTED_WITH_LOSS`（**必须带标记**） | 允许用户自行承担损失 |

`UNSUPPORTED` / `UNKNOWN` **在任何 policy 下都不进入"可用"集合**，
但客户端**必须**把它们放进"不兼容/待定"分组并**保留原始 URI**（原则 P2/P5）。

---

## 5. 批量结果（`check_many`）

```yaml
total: 12
supported: 7
warning: 2
loss: 1
unsupported: 1
unknown: 1
items: [EvaluationResult, ...]
```

形状借鉴 `xray-knife` 的 `Report{Converted, Skipped[]{Index,Name,Reason}}` 与
Proxylink 的 `ConvertResult{Total,Success,Failed,Errors}` —— 但它们只到**节点级**，
我们要求到**字段级**（`losses[]`）。

---

## 6. 判定必须发生一次（唯一检查点）

Phase 1 实证（`docs/06-oss-landscape.md` §4.9）：v2rayN 把同一个判断写在 **3 处**，
其中一处永久不可达、无人发现；sing-box-subscribe 把同一个"不支持"演化出**四种结局**
（跳过 / 坏配置 / 崩溃 / **降级直连**）。

→ **判定只在 compat 里发生一次**，客户端只消费结果，不自行推断。
生成阶段**不做**兼容性判断（那是损失不可恢复的地方）。

---

## 7. 与生成的关系（职责边界）

```
compat:   profile → EvaluationResult（含 losses/unknowns）
client:   自己决定 UI（显示/隐藏/分组/禁用）
client:   自己的内核生成配置并运行
```

compat **不生成配置**、**不改写节点**、**不自动换 transport**。
若用户无视 `SUPPORTED_WITH_LOSS` 继续使用，损失的记录依然在结果里 —— 客户端可以据此提示。
