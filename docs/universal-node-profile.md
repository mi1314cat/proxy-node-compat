# Universal Node Profile

> 描述的是「**这个节点本身包含什么信息**」，与任何内核无关。
>
> **本文件中不允许出现内核版本号。** 节点不属于任何内核版本；
> "某内核能不能用它"是 Phase 3 的事。

---

## 0. 设计约束（来自 `00-design-principles.md` 与本阶段新原则）

| # | 约束 |
|---|---|
| C1 | 不因某内核当前没有某字段而拒绝该字段 |
| C2 | `null` 不足以表达缺失 → presence 必须显式（§2） |
| C3 | 每个重要字段可追溯来源 → provenance（§3） |
| C4 | 特征必须可扩展：`standard:` / vendor / custom / unknown 四类（§4） |
| C5 | 原始 URI 与原始字段原文永不丢失（§1 `raw`） |
| C6 | **不制造版本边界**：本文件不描述版本行为 |
| C7 | 未知一律保留 + 标 UNKNOWN，不丢弃、不当作非法 |

---

## 1. 顶层结构

```yaml
profile_version: 1

raw:                       # C5：原文区，任何转换都不得覆盖
  uri: "vless://uuid@host:443?type=xhttp&mode=auto&security=reality&pbk=...#name"
  source_format: URI        # URI | XRAY_JSON | MIHOMO_YAML | SINGBOX_JSON | MANUAL
  fields:                   # 原始键值**原样**保存（含大小写、别名、未知键）
    type: xhttp
    pbk: AAAA...
    evilField: "1"          # 未知键也在这里，永不丢

protocol:                  # F<feature_id>，见 §2/§4
  id: standard:vless
  presence: EXPLICIT
  provenance: URI

endpoint:
  host: {v: 1.2.3.4,   presence: EXPLICIT, provenance: URI, raw_key: host}
  port: {v: 443,       presence: EXPLICIT, provenance: URI}

auth:
  uuid: {v: "...",     presence: EXPLICIT, provenance: URI}
  # 各协议按需：password / method / username / private_key ...

features:                  # ★ 能力一等公民（组合式，见 §4）
  - id: standard:reality
    presence: EXPLICIT
    provenance: URI
    params:
      public_key: {v: "AAAA...", presence: EXPLICIT, provenance: URI, raw_key: pbk}
      short_id:   {v: "0123",    presence: EXPLICIT, provenance: URI, raw_key: sid}
      spider_x:   {v: "",        presence: ABSENT}
      fingerprint:{v: "chrome",  presence: EXPLICIT, provenance: URI, raw_key: fp}
  - id: standard:xhttp
    presence: EXPLICIT
    params:
      path: {v: "/x",   presence: EXPLICIT, provenance: URI, raw_key: path}
      mode: {v: "auto", presence: EXPLICIT, provenance: URI, raw_key: mode}

extensions:                # ★ 未建模/未知字段，原样保留（C1/C7）
  - key: evilField
    value: "1"
    source: URI
    note: 解析器不认识这个键

metadata:                  # 与连接无关的展示/管理信息
  name: {v: "🇺🇸 X-01", presence: EXPLICIT, provenance: URI, raw_key: fragment}
  group: {v: "美国", presence: INFERRED, provenance: INFERRED, basis: "名称前缀推断"}

diagnostics:               # 解析期的观察，不是结论
  - code: PARAM_ALIAS_USED
    detail: "servername 被识别为 sni 的别名"
  - code: UNKNOWN_PARAM_KEPT
    detail: "evilField 已存入 extensions，不会进入任何生成物"
```

**三条硬规则**

1. `raw.*` **只读**：任何标准化、归一化、修复都不许改写它（解析器有 bug 时可以重放）。
2. `extensions[]` 是未知信息的**唯一合法去处**；`raw.fields` 是原文，`extensions` 是"已被识别为未知"的登记。
3. `diagnostics[]` 记录**观察**，不记录**判定**；判定属于 Evaluation Result。

---

## 2. Presence 模型（C2）

```yaml
presence:
  ABSENT       # 输入里根本没有这个字段
  EXPLICIT     # 输入里明确写了（哪怕是空串、false、0）
  DEFAULTED    # 输入没写，但**协议/规范**规定了默认值（如 vless 的 encryption=none）
  INFERRED     # 由其它信息推断得出（如从名称前缀推断分组）
  UNKNOWN      # 无法确定（如上游解析器已把 presence 抹平）
```

规则：

- **`EXPLICIT` 与 `DEFAULTED` 必须分开**：`skip-cert-verify: false` 与"没写"在安全语义上完全不同。
  （Phase 1 证据：三个 Go 项目 100% 因混同二者而**写不出 loss 报告**。）
- `INFERRED` 的字段**必须**带 `basis`（推断依据），且**不得**在兼容性判定里被当作"用户要求"。
- 若某字段来自一个已经把 presence 抹平的上游（如某个转换器的产物），标 `UNKNOWN`，
  **不要**猜成 `ABSENT` 或 `EXPLICIT`。

对应的 TypeScript 式形状（实现期参考）：

```ts
type Presence = "ABSENT" | "EXPLICIT" | "DEFAULTED" | "INFERRED" | "UNKNOWN";
type Field<T> = {
  v?: T;                    // presence=ABSENT 时不存在
  presence: Presence;
  provenance: Provenance;
  raw_key?: string;         // 它在原始输入里的键名（含别名）
  basis?: string;           // presence=INFERRED 时必填
};
```

---

## 3. Provenance 模型（C3）

```yaml
provenance:
  URI            # 分享链接（最原始，用户可见）
  XRAY_JSON
  MIHOMO_YAML
  SINGBOX_JSON
  SUBSCRIPTION   # 订阅内容（可能是上面任一种的包装）
  INFERRED       # 兼容层推断
  USER_DEFINED   # 用户手工指定（如面板里手填）
  EXTENSION      # 来自某个扩展/插件
```

用途：

- 判定 UI 文案："这是链接里明确的" vs "这是我们猜的"。
- 回写 URI 时的取舍：`INFERRED` 的字段**不写回**链接（写了就等于伪造用户意图）。
- 冲突解决：同一字段多个来源时按 `USER_DEFINED > URI > SUBSCRIPTION > 内核配置 > INFERRED` 排序，
  并把被覆盖的记进 `diagnostics`。

---

## 4. Feature 模型（C4：标准 / vendor / 自定义 / 未知）

### 4.1 命名空间

```
standard:<name>      # 有公开规范或至少被多内核共同实现：vless / reality / xhttp / ech / ws / grpc ...
<vendor>:<name>      # 某个实现方定义的扩展：mi1314cat:anyreality
custom:<name>        # 用户/部署方自造，未发布
unknown:<hash>       # 解析器完全看不懂，只能按原文登记
```

**关键：`features[]` 是开放的。** 新增一个第三方扩展**不改本文件**，只要它的 id 用 `<vendor>:` 前缀。

### 4.2 Feature 条目的形状

```yaml
- id: mi1314cat:anyreality.ss-reality
  presence: EXPLICIT
  provenance: USER_DEFINED
  params: { ... }              # 与 standard 特征同样的 Field 包装
  requires:                    # 组合约束（本 feature 成立的前提）
    - feature: standard:shadowsocks2022
    - feature: standard:reality
  excludes: []                 # 与哪些 feature 互斥
  note: "SS2022 之上叠加 REALITY（AnyReality 变体之一）"
```

### 4.3 组合不折叠

**不允许**把 `vless + reality + xhttp` 折叠成一个 `features` 里的单项或一个 `protocol` 值。

- `protocol` 只表达**协议本身**（vless）；
- `transport` / `security` / `tls` / `reality` / `ech` / `flow` / `multiplex` 等都是**并列的 feature**；
- 判定时必须看**组合**（Phase 3 §9 组合约束）。

### 4.4 AnyReality 如何进入模型（真实案例，无特例 hack）

我们在三个仓库里有三个真实变体（`research/empirical/anyreality.md`）：

```yaml
# 变体 1：SS2022 + REALITY（xray--core/conf/Shadowsocks.sh）
protocol: {id: standard:shadowsocks2022}
features:
  - {id: standard:reality, presence: EXPLICIT, provenance: USER_DEFINED}
  - {id: mi1314cat:anyreality.ss-reality, presence: EXPLICIT, provenance: USER_DEFINED,
     requires: [{feature: standard:shadowsocks2022}, {feature: standard:reality}]}

# 变体 2：Trojan + REALITY（三层模型）
# 变体 3：AnyTLS + REALITY（sing-box-core/src/conf/anytls.sh）
```

**模型里没有任何 "anyreality" 的协议分支** —— 它就是"标准协议 + standard:reality 特征"，
外加一个 vendor 特征用于**表达我们自己的组合语义与文档**。未来任何第三方照此办理即可。

---

## 5. 必须能表达的字段清单（C1 检查表）

| 类别 | 字段（不限于） | 备注 |
|---|---|---|
| 协议 | vless / vmess / trojan / shadowsocks(+2022) / hysteria2 / tuic / anytls / socks / http / wireguard / ssh | 开放集合 |
| transport | tcp(raw) / ws / grpc / http(h2) / httpupgrade / xhttp / splithttp / kcp / quic / masque / xhttp-extra | 含**已移除**与**从未存在**者 |
| security | none / tls / reality | 独立 feature |
| TLS | sni / alpn / fingerprint(utls) / allow_insecure / pinned_cert_sha256 / pinned_ca256 / disable_sni / ech | |
| Reality | public_key / short_id / spider_x / target / server_names | |
| ECH | config_list / query_server_name / force_query | |
| 认证 | uuid / password / method(cipher) / username / plugin+opts / psk | |
| flow | xtls-rprx-vision 等 | 自由字符串，不枚举 |
| multiplex | enabled / protocol(smux/yamux/h2mux/mux.cool) / concurrency / max_connections | |
| DNS | 节点的 dns 相关参数 | |
| transport 专属 | path / host / headers / service_name / mode / extra / mtu / tti / seed / header_type / quic_security / quic_key / authority / max_early_data / early_data_header_name | |
| vendor/自定义 | 任意（进 `features[]` 或 `extensions[]`） | |
| metadata | name / group / subscription_id / remark | |

> 这张表**不是白名单**：表里没有的键一律进 `extensions[]`，而不是被拒绝。

---

## 6. 与其他模型的关系（为什么不直接用它们的）

Phase 1 结论（`docs/06-oss-landscape.md`）：

- 生态的模型（Proxylink `ProfileItem`、Sub-Store 的 Clash 风格对象、proxyparser 的 `map[string]any`）
  都是**扁平 + 无 presence + 无 provenance + 封闭**，且多半把某个内核的 schema 当枢纽格式。
- 我们不能照搬：它们**回答不了**"这是用户写的还是你猜的"（§3）、"这个字段为什么丢了"（§2）。

我们保留它们**可互操作的字段命名**（`ws-opts` / `reality-opts` / `xhttp-opts` 等），
但内部结构是上面的 profile，**不把任何内核格式当中间表示**。

---

## 7. 不变式（实现期必须写成断言）

| # | 不变式 |
|---|---|
| I1 | `raw.uri` 与 `raw.fields` 在整条流水线上字节不变 |
| I2 | 任何被读取但未建模的键，必须出现在 `extensions[]` 或 `raw.fields` 中（二者至少其一） |
| I3 | 每个 `presence: INFERRED` 的字段都有 `basis` |
| I4 | 不存在"值为 `null` 且无 presence 标注"的字段 |
| I5 | `features[]` 里的每个 id 都符合命名空间语法（`standard:` / `<vendor>:` / `custom:` / `unknown:`） |
| I6 | 同一 feature id 不重复；重复时合并 params 并在 `diagnostics` 记录冲突 |
| I7 | **本文件产出的 profile 不含任何内核版本字段**（架构审查项，见 Phase 3 §11） |
