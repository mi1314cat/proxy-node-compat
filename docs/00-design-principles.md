# 00 · 设计纪律（本项目的宪法）

> 这份文件是**约束**，不是建议。任何代码、数据、判断逻辑与它冲突时，以它为准。
> 改动本项目的行为前，先在这里找到依据；找不到依据的新行为，先改这份文件再改代码。

---

## P1 · 职责边界：compat 只判断，不生成

```
客户端读 URL/订阅 → 解析 URI → 交给 compat → 标准化 Node Profile
→ 按 Kernel+Version 判断 → 返回结构化结果 → 客户端自己决定 UI
→ 客户端自己的内核生成配置并运行
```

compat **不做**：

- 不生成任何内核的配置
- 不接管"最终跑起来"的职责
- 不替客户端决定"显示还是隐藏"（只给结论，决策权在客户端）

**理由**：一旦 compat 开始生成配置，它就被绑死在具体内核的配置格式上，
"内核无关"这个立身之本立刻消失。

---

## P2 · 绝不静默丢失能力（最高优先级）

节点可能带有：protocol / transport / TLS / Reality / Vision / ECH / fingerprint / flow /
headers / XHTTP 参数 / mux / dialer / proxy protocol / obfs / UDP / DNS / socket options / 其他高级参数。

解析、标准化、判断的全过程必须**尽可能完整保留**这些信息。**绝对禁止**：

> 发现目标内核不认识某字段 → 悄悄删掉 → 回报"支持"

正确做法：返回 `SUPPORTED_WITH_LOSS` / `SUPPORTED_WITH_WARNING`，并在 `losses` 里
逐条列出"哪项能力表达不了、为什么、后果是什么"。

**推论**：解析器必须保留**原始 URI**（见 P6），标准化不得覆盖原始输入。

---

## P3 · "能解析" ≠ "支持"

`configuration parsed successfully` **不等价于** `feature supported`。

判定依据只能是这四种，且必须能追溯到具体来源：

1. 官方文档
2. 官方源码
3. **实际内核运行 / 回环测试**
4. 必要时抓包验证

**未知行为一律返回 `UNKNOWN`，不允许猜。** 不许因为"大概率支持"就写 `SUPPORTED`。

> 实测反例（本项目建立的直接动机）：mihomo 的 `network` 字段不做校验。
> 写一个根本不存在的 transport 名，`mihomo -t` 依然返回成功，
> 运行时静默按 tcp 处理 → 用户得到"能导入、能启动、就是不通"的节点。

**实现要求**：能力登记表里每一条都必须带 `evidence` 字段，标明来源类型
（`doc` / `src` / `test` / `unknown`）。没有证据的条目只能是 `UNKNOWN`。

---

## P4 · 内核 + 版本，而不是只有内核

```python
check(node, kernel="mihomo")                    # ❌ 不够
check(node, kernel="mihomo", version="1.19.32") # ✅
```

内核能力随时间变化，以下五类变化必须能进入能力数据库：

`newly supported` / `deprecated` / `removed` / `renamed` / `behavior changed`

> 实例：Xray 新版本移除了 mKCP 的 `header` / `seed` 字段（迁到 finalmask），
> 老配置现在**加载即失败**。这类变化不记进能力库，判断就会错。

---

## P5 · 结果必须结构化

状态机（恰好这五个，不增不减）：

| status | 含义 |
|---|---|
| `SUPPORTED` | 完整支持，无损 |
| `SUPPORTED_WITH_WARNING` | 能用，但需要注意项（不是损失，例如"需要内核 ≥ 某版本"） |
| `SUPPORTED_WITH_LOSS` | 能用，但**确定会丢能力**（必须逐条列出丢了什么） |
| `UNSUPPORTED` | 明确不支持 |
| `UNKNOWN` | 证据不足，**不猜** |

必须同时返回机器可读的 `reason_code`：

```json
{
  "status": "UNSUPPORTED",
  "reason_code": "TRANSPORT_UNSUPPORTED",
  "message": "mihomo does not support xhttp transport"
}
```

**不许只返回一段人类可读文本。** 客户端要能靠 `reason_code` 自动处理 UI。

---

## P6 · 原始节点不可破坏

三者必须**同时存在**：

```
raw_uri              ← 原始分享链接，永远保留
normalized_node      ← 标准化后的 Node Profile
compatibility_result ← 判断结果
```

原始 URI 永远不能因为标准化而丢失 —— 以后发现解析器有 bug，仍然可以重新解析原始输入。

---

## P7 · Feature Provenance（字段来源必须可追溯）

每个能力都要能回答"这个字段从哪来"：

```
source: uri | json | yaml | inferred
```

**尤其禁止**把"推测出来的字段"和"URI 明确提供的字段"混在一起。
`inferred` 的字段参与判断时必须能被区分出来（例如推断出的默认端口不能当成"用户指定"）。

---

## P8 · 三层能力必须分开建模

```
Kernel 支持某功能  ≠  URI 可以表达这个功能  ≠  导入后能完整恢复
```

数据模型必须能分别表达 `URI Representation` 与 `Kernel Representation`，
否则无法回答"这条链接到底能不能无损地用起来"。

---

## P9 · 离线优先

第一阶段是**本地 Library / SDK**（`from proxy_node_compat import check_node`）+ CLI。
判断必须可以完全离线完成 —— 不强制任何客户端访问远程服务。

远程 HTTP API（`POST /v1/check`、`POST /v1/check-many`、`GET /v1/capabilities/{kernel}`）
只是**预留**，且必须与本地库**共用同一套核心逻辑**，绝不允许维护两份判断代码。

---

## P10 · 接入必须简单

第三方客户端接入只应做五件事：

1. 安装 `proxy-node-compat`
2. 声明当前 Kernel（+ Version）
3. 把解析后的 Node Profile 交给它
4. 拿到 compatibility result
5. 按 result 筛选 / 分组 / 提示

不允许要求每个客户端重新实现一遍兼容性判断。

---

## P11 · 架构不得写死内核

禁止：

- `if kernel == "mihomo": ...` 式的判断地狱
- 把协议/传输/能力的支持矩阵硬编码进代码

支持矩阵全部走**数据**（Capability Registry）；新增内核 = 新增数据文件 + 适配器，
**不改判断引擎**。

---

## P12 · 第一阶段明令禁止的事

暂时不要：

- 修改 mihomo-core / sing-box-core / xray--core（三个内核项目）
- 重写三个项目的分享系统
- 自动转换协议
- 自动删除不支持字段
- 自动把一个 transport 换成另一个 transport
- 把"能解析"当成"支持"
- 对未知能力默认判定为支持
- 把三个内核的能力硬编码成 if/else 地狱

**先把公共标准建立起来。** 三个项目怎么接入，等这个层正确之后再说。

---

## P13 · 测试要求：不只有单元测试

至少要有：URI parsing / normalization / capability / cross-kernel compatibility /
version / unknown-field / deprecated-field / **real runtime** 测试。

必须建立真实的双向案例：`X→M`、`X→SB`、`M→X`、`M→SB`、`SB→X`、`SB→M`。

**注意测试重点**：不是"让一个内核生成另一个内核的配置"，而是
**分享 URI / Node Profile 在目标客户端里能否被正确识别、筛选和使用**。

---

## 附：每个能力条目在数据里的样子（最小要求）

```yaml
- feature: transport.xhttp
  kernel: mihomo
  version_range: ">=1.19.0"
  uri_representable: true        # URI 能不能表达
  kernel_field: "proxies[].network: xhttp"
  runtime_support: SUPPORTED
  failure_mode: null             # 不支持时的行为：reject | silent_degrade | ...
  evidence:
    - type: test
      how: "回环：xray 起 xhttp 入站，mihomo 客户端接通"
      date: 2026-10-10
    - type: src
      where: "adapter/outbound/vless.go"
  notes: ""
```

`failure_mode` 是关键字段 —— `silent_degrade`（静默降级）必须被显式建模，
因为它是本项目要替用户挡掉的最危险的一类问题。
