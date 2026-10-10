# Evidence Model

> Phase 1 的教训：**我们不可能知道每一个能力的确切版本边界。**
> 所以证据模型的作用不是"让数据看起来完整"，而是**让"我们不知道"这件事也被结构化地记录下来**。

---

## 1. 证据类型

```yaml
evidence_type:
  DOC                # 官方文档
  SRC                # 官方源码（给到 文件:行 或 符号名）
  RELEASE            # 官方 release note / changelog / tag
  RUNTIME_TEST       # 真内核运行验证（我们自己的探针或回环）
  CONFIG_VALIDATION  # 内核自带校验器（xray -test / mihomo -t / sing-box check）
  PACKET_CAPTURE     # 抓包
  COMMUNITY          # issue / 论坛 / 第三方（最低可信）
  INFERENCE          # 来自其它条目的推断（**不能单独支撑 SUPPORTED**）
```

## 2. 证据条目形状

```yaml
- id: e-mihomo-xhttp-loopback
  type: RUNTIME_TEST
  confidence: HIGH          # HIGH | MEDIUM | LOW
  date: 2026-10-10
  target: {kernel: mihomo, version: "1.19.32", build: "with_gvisor", platform: linux/amd64}
  claim: "mihomo 1.19.32 能真正使用 xhttp（回环实测接通）"
  how: "xray 起 xhttp-only 入站(18444) → mihomo 客户端取回 COMPAT-OK"
  where: "research/empirical/probe-results.json#loopback.xray_server_xhttp__mihomo_client_xhttp"
  limits: "只证明了该版本该构建；未验证其它版本"
```

**`limits` 是必填项**：每条证据都必须自陈"它到底证明了什么、没证明什么"。

## 3. 置信度与用途

| confidence | 允许单独支撑 | 说明 |
|---|---|---|
| HIGH | ✅ | 真机运行验证 / 官方源码明确分支 + 我们亲自复现 |
| MEDIUM | ⚠️ 仅 WARNING/LOSS | 单一官方文档；源码里存在但未运行验证 |
| LOW | ❌ 只能是 UNKNOWN 的佐证 | 社区说法、推断、未复现的二手信息 |

## 4. 三条硬规则

### R1 · 推断不能变事实

`INFERENCE` 类型（含"1.19.30 支持、1.19.32 支持 ⇒ 1.19.31 支持"这类插值）**不得**单独产生
`SUPPORTED`。它可以产生 `SUPPORTED_WITH_WARNING`（并注明"中间版本未验证"），
或者在有其它 HIGH 证据补强后降级为说明性文字。

### R2 · 精度不得高于证据

证据只说了"旧版本有、新版本没有"，就**必须**写成：

```yaml
known_present: "<= <旧版本号>"
known_absent:  ">= <新版本号>"
transition: UNKNOWN
```

**禁止**补出一个 `removed_at: <某版本>`。精度是证据的属性，不是作者的选择。

### R3 · 未知要被显式记录，而不是留空

每条能力规则都允许 `unknown_range` 与 `open_questions[]`：

```yaml
unknown_range:
  - range: ">= 1.19.23, < 1.19.29"
    why: "没有任何一版被验证过；两端各有证据但中间无证据"
open_questions:
  - "1.19.25 是否支持 xhttp-opts.extra 的 scMaxEachPostBytes"
```

留空与"未知"在语义上不同：**留空会被下游当成没这条规则，UNKNOWN 会被当成待补的未知。**

## 5. 证据覆盖度（供 UI 与维护用）

每条规则的证据覆盖度应当可计算，用于给客户端一个诚实的置信提示：

```yaml
coverage:
  levels_covered: [config, runtime]      # 哪些能力层级有证据
  versions_probed: ["1.19.32"]
  versions_claimed: ">=1.19.22"
  gap: "introduced 到 probed 之间未逐版验证"
```

客户端可以据此决定是显示"支持"还是"支持（未逐版验证）"。

## 6. 反面教材（Phase 1 实证，写在这里防止复发）

| 反面教材 | 后果 |
|---|---|
| 生态项目把"作者当时知道什么"写成代码常量（subconverter 无 VLESS，issue #611 挂了两年） | 内核演进后不报告，用户以为不支持 |
| `isSupportedMihomoVersion` 实际比的是插件版本 | 名字骗人，判断错位 |
| `xray-knife` 知道"h2 被移除"却说不出从哪版移除 | 老内核用户被误判 |
| 我们自己的 `conf/Shadowsocks.sh:396` 注释断言"sing-box 可直接叠加 Reality" | **被真内核推翻**（`unknown field "tls"`） |

共同点：**结论以人类可读文本存在、与证据脱钩、无人复验**。
本模型要求每条结论都挂 `evidence[]`，且 `limits` 必填 —— 就是为了让这种漂移无从发生。
