# URI Representation Registry

> `Kernel supports feature` **≠** `URI can express feature` **≠** `从这条 URI 导入后能完整恢复`。
>
> 这张表**与内核无关**，必须独立存在。Phase 1 实证：Xray-core 与 sing-box
> **全树 grep `vless://|vmess://|shareLink` 命中 0** —— 内核根本不解析也不生成分享链接。

---

## 1. 为什么必须独立

| 情形 | 内核 | URI | 后果 |
|---|---|---|---|
| ss + REALITY（AnyReality #1） | Xray ✅ | `ss://` **装不下** reality 参数 | 节点能用，但**链接本身带着损失**；我们仓库现在只能用注释说明 |
| snell | sing-box ❌（从未支持） | 无通用分享格式 | 与内核无关的 `URI_NOT_REPRESENTABLE` |
| xhttp + extra | mihomo ✅ | `extra=` 只在部分客户端被保留 | 需要 `SUPPORTED_WITH_LOSS` |
| VMess + REALITY | mihomo ✅ | VMess QR 只有 15 个字段 | 回写时**整套 reality 字段消失**（Proxylink 实测） |

如果把 URI 表达力并进内核能力表，上面四种会被混成同一类，客户端就没法给出正确提示。

---

## 2. 条目形状

```yaml
- uri_rule_id: uri.vless.reality
  scheme: vless
  feature: standard:reality
  representation: FULL            # FULL | PARTIAL | NONE
  carrier:                        # 表达的载体（query 键 / fragment / 无）
    keys: [security, pbk, sid, spx, fp]
  spec_added_at: null             # 若知道该参数进规范的时间，必须写在 §3
  evidence: [e-xray-sharelink-716]

- uri_rule_id: uri.ss.reality
  scheme: ss                        # SIP002
  feature: standard:reality
  representation: NONE              # ★ ss:// 物理上无法表达 reality
  loss:
    - field: standard:reality.public_key
    - field: standard:reality.short_id
    - field: standard:reality.server_names
  workaround: "本项目的 vendor 扩展: 在 fragment 里带 mi1314cat 参数（非标准，需对端认识）"
  evidence: [e-our-shadowsocks-sh, e-sip002]
```

`representation` 语义：

| 值 | 含义 |
|---|---|
| `FULL` | 该 feature 的全部参数都能表达 |
| `PARTIAL` | 只能表达一部分（必须列 `loss[]`） |
| `NONE` | 完全无法表达（必须列 `loss[]` + 是否有 vendor 变通） |

---

## 3. 参数进规范的时间（老客户端会静默忽略）

| 参数 | 进规范时间 | 老客户端行为 | 证据 |
|---|---|---|---|
| `ech` | 2025-07-26 | 按 SIP002 精神**静默忽略** | `research/kernel-xray.md` |
| `pqv` | 2025-07-22 | 同上 | 同上 |
| `pcs` / `vcn` | 2026-01-18 / 2026-02-02 | 同上 | 同上 |
| `fm`（finalmask） | 2026-01-31 | 同上 | 同上 |
| `mtu` / `tti` | 2026-03-27 | 同上 | 同上 |

→ `uri_rule` 除了 `representation`，还要能表达 **`spec_added_at`** 与
**`client_support`**（哪些客户端认识到什么程度），因为"规范里有"和"对方的客户端认识"是两件事。

---

## 4. 命名空间扩展的 URI 载体（我们的 vendor 扩展）

标准 URI 不认识的参数，**只能**放在：

1. 标准 scheme 的 **未知 query 参数**（风险：多数客户端会丢；个别客户端会**泄漏进配置**，见下）
2. **fragment**（`#` 之后）：所有内核都把它当纯展示名，因此**最安全的 vendor 载体**
3. 独立的 vendor scheme（如 `mi1314cat+ss://`，仅在我们生态内可用）

**安全注意（Phase 1 实测）**：Sub-Store 的 `anytls/hysteria2/tuic` 解析器会把未知 query 参数
**原样写进节点对象并进入 mihomo 配置**（实测出现 `"evilField":"1"`）。
→ 我们自己的规则：**未知参数进 `extensions{}`，默认不进入任何生成物**；
URI 回写时也不许把 `extensions` 里的东西自动写成 query。

---

## 5. 回环（round-trip）不变量

```
raw_uri ──parse──▶ NodeProfile ──generate──▶ uri' ──parse──▶ NodeProfile'
                                                        ▲
                                      必须满足：语义等价（不是字节相等）
```

判定"语义等价"的口径：

| 类别 | 要求 |
|---|---|
| `presence: EXPLICIT` 的字段 | **必须**在 `uri'` 中可恢复，且 presence 仍为 EXPLICIT |
| `presence: DEFAULTED` 的字段 | 允许不写回（默认值不需要表达） |
| `presence: INFERRED` 的字段 | **禁止**写回（写回等于伪造用户意图） |
| `extensions[]` | 默认**不**写回；若写回则必须用 vendor 载体 |
| 无法表达的 feature | 必须进 `losses[]`，**不许**"转换成功"了事 |

Phase 1 对照：生态里**没有一个项目**做 round-trip 属性测试
（Proxylink 连 `*_test.go` 都没有；subconverter 无测试目录；sub-link-worker 有 5023 行回归测试但
`reparse|round-trip|fidelity` 命中 0）。→ 这是我们相对生态的**结构性优势**，必须做成不变量测试。
