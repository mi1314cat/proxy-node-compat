# proxy-node-compat

> 跨代理内核的 **Node Compatibility Layer**。
>
> 它不生成配置、不转换节点、不接管任何客户端的运行职责。
> 它只回答一个问题：**这个节点，对当前客户端/内核（含版本）到底能不能完整使用？**

## 一句话定位

```
客户端 → 读分享 URL / 订阅 → 解析 URI
      → 【交给 proxy-node-compat】
      → Node Profile（内核无关）
      → 按目标 Kernel + Version 判断
      → 兼容性结果（结构化 + reason_code）
      → 客户端自己决定 显示 / 隐藏 / 分组 / 禁用
      → 客户端自己的内核生成配置并运行
```

**compat 永远不负责生成配置。** 最终跑起来的配置由各客户端自己的内核负责。

## 它要回答的问题

- 这个节点包含哪些能力？
- 这条 URI 实际表达了哪些能力？（URI 的表达力是有上限的）
- 目标内核的**哪个版本**支持这些能力？
- 能否**完整**使用？
- 如果不能，**具体损失什么**？
- 这是**明确不支持**，还是**目前未知**？

## 三条不可违反的原则

### 1. 绝不静默丢失能力

解析、标准化、判断过程中必须尽可能完整保留节点能力。目标内核无法完整表达某项能力时，
返回 `SUPPORTED_WITH_LOSS` / `SUPPORTED_WITH_WARNING`，**绝不**"删掉字段然后说支持"。

### 2. "能解析" ≠ "支持"

`configuration parsed successfully` 不代表 `feature supported`。
判断必须基于：官方文档、官方源码、**实际内核运行/回环测试**、必要时抓包。
未知行为返回 `UNKNOWN`，**不允许猜测**。

> 这不是理论洁癖。实测：给 mihomo 一个完全不存在的 transport 名，`mihomo -t` 返回成功，
> 运行时会**静默按 tcp 处理** —— 用户得到一条"能导入、能启动、就是不通"的节点。
> 详见 `research/empirical/`。

### 3. 架构不写死内核

Xray / mihomo / sing-box 只是第一批目标。协议、传输、能力、版本门槛全部走**数据**
（Capability Registry），不是 `if kernel == "mihomo"` 的 if/else 地狱。

## 核心数据模型（四层）

```
Node Feature          节点具备的能力（Reality / Vision / ECH / mux / obfs ...）
      ↓
URI Representation    分享 URI 能否表达它（表达不了的，导入即损失）
      ↓
Kernel Representation 目标内核配置里的对应字段（可能根本不存在）
      ↓
Runtime Support       该版本内核运行时是否真的生效（可能静默忽略！）
```

四层里任何一层断了，都会让"看起来能用"的节点实际不能用 —— 这正是本项目存在的理由。

## 文档

| 文件 | 内容 |
|---|---|
| `docs/00-design-principles.md` | 绑定的设计纪律（本项目的宪法） |
| `docs/universal-node-profile.md` | **Phase 2**：Universal Node Profile（presence/provenance/feature 命名空间） |
| `docs/kernel-capability-registry.md` | **Phase 3**：能力规则（证据决定精度，禁止伪造版本边界） |
| `docs/uri-representation.md` | **Phase 3**：URI 表达力独立表（内核支持 ≠ URI 能表达） |
| `docs/compatibility-evaluation.md` | **Phase 3**：判定引擎（四维输入 / 分层结论 / losses） |
| `docs/evidence-model.md` | **Phase 3**：证据模型（类型 / 置信度 / 三条硬规则） |
| `docs/phase4-report.md` | **Phase 4**：实现与验收报告（模块 / 测试 / 案例输出 / 待补证据 / 接入方案） |
| `docs/examples/` | **14 个真实案例**验收（含"版本边界未知 → UNKNOWN"） |
| `docs/06-oss-landscape.md` | Phase 1.5：开源生态调研与架构再定位 |
| `docs/07-version-and-failure-model.md` | Phase 1：版本维度与失败模式模型 |
| `research/` | Phase 1 研究：三家官方文档与源码能力清单 |
| `research/empirical/` | 真内核实测证据（配置校验 + 语义回环） |

## 状态

Phase 1（研究）✅ ｜ Phase 2/3（设计）✅ ｜ **Phase 4A–4D（实现）✅**（26 个测试通过）。

零第三方依赖，可完全离线判断；尚未接入三个内核项目（方案见 phase4-report §8）。

接入方式（Phase 7 之后才讨论）：三个客户端各自只告诉 compat「我是哪个 Kernel、哪个 Version」，
把节点交给 compat，拿到结果后自行决定 UI 行为。
