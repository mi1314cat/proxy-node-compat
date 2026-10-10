# Phase 4 交付报告

> 实现提交：`661e8cc`（本报告为随附文档）
> 范围：只改 `mi1314cat/proxy-node-compat`。三个内核仓库与现有客户端**未触碰**。

---

## 1. 实现的模块与文件

| 文件 | 阶段 | 内容 |
|---|---|---|
| `proxy_node_compat/model.py` | 4A | Presence（5 态）、Provenance（8 源）、`Field`、`Feature`、`NodeProfile`、不变式 I1–I7 校验、无损序列化 |
| `proxy_node_compat/registry.py` | 4B | 版本解析与区间判定、`Rule`/`Segment`/`Evidence`、规则加载与证据引用校验 |
| `proxy_node_compat/engine.py` | 4B | `Target`（六维输入）、分层判定、失败模式、组合约束、R1 推断规则、结果聚合 |
| `proxy_node_compat/uri.py` | 4C | URI 解析（vless/vmess/trojan/ss/hysteria2/tuic/anytls/socks/http + 未知 scheme/未知传输）、回写生成 |
| `proxy_node_compat/cli.py` | 4D | `check` / `check-many` / `capabilities` |
| `proxy_node_compat/data/rules.json` | 4B/4C | 19 条证据 + 16 条能力规则 + 4 条 URI 表达力规则（全部挂证据） |
| `tests/test_all.py` | 4A–4D | 26 个用例（18 个指定案例 + 版本边界红线 + 不变式） |
| `pyproject.toml` | 4D | 零第三方依赖；`proxy-node-compat` 命令入口 |

## 2. 已实现 / 未实现

**已实现**：Node Profile 全模型与不变式；presence/provenance；extensions 保底；规则引擎（版本三写法、分段、未知区间、evidence_only、version_independent、fork 不继承、build tags、runtime options）；分层判定；失败模式四态；组合约束；URI 表达力独立表；losses/warnings/unknowns/reason_codes/evidence；CLI 三命令；批量单行失败不拖垮整批。

**未实现（有意为之，下一阶段）**：内核配置片段（Xray JSON / mihomo YAML / sing-box JSON）的完整导入；`evaluated_at` 时间闸门的实际生效（当前把 Xray allowInsecure 的时间闸门区间整体标为 UNKNOWN，**没有伪造日期结论**）；HTTP API；真实内核自动探测（`sing-box version` 读取 Tags、`--version` 自动发现）；能力数据覆盖度（目前 16 条规则，只覆盖 Phase 1 有实证的部分）。

## 3. 测试实际执行结果

```
$ python3 -m unittest discover -s tests
Ran 26 tests in 0.10s
OK
```

覆盖：案例 1–14、15（未知字段跨序列化存活）、16（INFERRED 不写回）、17（组合不被单点推断）、18（仅推断证据不得为无警告 SUPPORTED）、版本边界红线（1.18.0 支持 / 1.19.5 **UNKNOWN** / 1.19.32 不支持）、缺 build 只影响 runtime 层。

## 4. 关键案例实际输出（CLI）

```
$ proxy-node-compat check "vless://u@1.2.3.4:443?type=xhttp" --kernel mihomo --version 1.19.32 -v
🟡 SUPPORTED_WITH_WARNING
   分层: parse=UNKNOWN  config=SUPPORTED  uri=SUPPORTED  runtime=SUPPORTED  semantic=UNKNOWN
   🟡 注意: VERSION_NOT_EXACTLY_PROBED —— 只回环验证过 1.19.32；1.19.22–1.19.31 未逐版验证
   证据: [RUNTIME_TEST/HIGH] 回环接通 ↳ research/empirical/... (局限: 只证明 1.19.32)
         [RELEASE/MEDIUM] xhttp 自 v1.19.22 起支持 (局限: 边界来自 release note)
   原始链接已保留: vless://u@1.2.3.4:443?type=xhttp

$ ... --kernel singbox --version 1.14.2          → ❌ UNSUPPORTED  KERNEL_NEVER_SUPPORTED (hard_error)
$ ... --kernel singbox --distribution sing-box-lx → ❓ UNKNOWN      UNKNOWN_CAPABILITY（fork 不继承上游）
```

批量（5 个节点）：`SUPPORTED_WITH_LOSS=2  SUPPORTED_WITH_WARNING=1  UNKNOWN=2`；未知协议那一行**没有拖垮整批**，且 `raw_uri` 原样保留。

## 5. 当前所有 UNKNOWN 的原因与待补证据

| UNKNOWN 来源 | 原因 | 待补 |
|---|---|---|
| `parse` / `semantic` 两层普遍 UNKNOWN | 没有针对"目标内核解析器是否认识该字段""运行语义是否等价"的证据 | 需要 Tier B 回环的语义断言（如"UDP 是否真的可用"） |
| `uri` 层对未覆盖的 feature UNKNOWN | 只写了 4 条 URI 规则 | 补 vless/vmess/trojan 的其余参数、hy2/tuic/anytls 的链接形态 |
| `distribution=sing-box-lx` 等未知 fork | 只有二手描述，未读源码/未实测 | 读 `sing-box-lx` 源码 + 自建二进制实测 |
| Xray `allowInsecure` 的时间闸门区间 | 引擎尚未把 `evaluated_at` 纳入判定 | 实现时间闸门后再给结论 |
| mihomo `xhttp` 的 1.19.22–1.19.31 | 只验证过 1.19.32 | 逐版回环（成本高，按需） |
| Xray mKCP 的两处过渡区间 | 两端有证据、中间无 | 逐版 `xray -test` |
| AnyReality 在 Xray 上的运行层结论 | 回环实验未跑通（`research/empirical/anyreality.md`） | 修好 ss+reality 回环 |
| `unknown:magic-transport` 之类 | 自造/未知，内核无对应物 | 等上游定义或用户说明 |

## 6. 如何新增内核 / fork / 协议 / 自定义 Feature

| 要加什么 | 怎么做 | 要改代码吗 |
|---|---|---|
| **新内核** | 在 `data/rules.json` 的 `rules[]` 里加 `target.kernel: <新内核>` 的规则；缺数据就先写 `evidence_only: true`（结果即全 UNKNOWN） | ❌ |
| **新 fork** | 加 `target.distribution: <fork>` 的规则；不写则自动 UNKNOWN（`unknown_distribution_policy`），**不会继承上游** | ❌ |
| **新协议** | `uri.py` 的 `SCHEMES` 加一行（scheme → protocol id）；不加也能用：会落到 `unknown:<scheme>` 并保留全部原文 | ❌（可选加一行） |
| **新自定义 Feature** | `features[]` 里用 `<vendor>:<name>`；组合约束用 `requires`/`excludes` 或规则里的 `constraint` | ❌ |
| **新能力层级 / 新失败模式** | 扩 `LEVELS` / 失败模式枚举 | ⚠️ 小改（认识论级变化，理应显式） |

AnyReality 已经按此机制落地：`standard:shadowsocks` + `standard:reality` + `mi1314cat:anyreality.ss-reality`，**代码里没有任何 anyreality 分支**。

## 7. 提交记录

| commit | 内容 |
|---|---|
| `11861d8` | Phase 2/3 设计文档 |
| `661e8cc` | **Phase 4A–4D 实现**（本次） |

## 8. 下一阶段：接入三个项目的方案

不改内核仓库，按"最小侵入、只消费结果"接：

1. **X 客户端（`xray--core/Client`）**：`lib/compat.py` 里的自研能力表已有 SUPPORTED/WARN/NOT_SUPPORTED 模型 —— 把它换成调用 `proxy_node_compat`（本地 vendored 一份，或 pip 安装），保留现有 UI 文案；`node.py` 产出的节点 JSON 增加一个 `to_profile()` 适配器（字段→feature 映射），**不动解析器的既有行为**。
2. **M 客户端（`mihomo--core/src`）**：M 的节点来自订阅（内核自己解析），因此接入点在**导入前**：把订阅里的每条链接先过 compat，把 `UNSUPPORTED`/`UNKNOWN` 的节点移入"不兼容"分组并保留原文；mihomo 配置里只放 `SUPPORTED*` 的节点。
3. **SB 客户端（`sing-box-core/src`）**：`conf/outbound_uri.py` 已有明确报错（"本面板支持 tcp/ws/grpc/http/httpupgrade"）——把它的**判断逻辑**替换为 compat 调用，报错文案由 `reason_code` 生成，保持"说了缺什么"的既有优点。
4. **共同要求**：三个客户端只传 `(kernel, distribution, version, build_tags, runtime_options)`；判定只在 compat 发生一次；客户端不自行推断、不改写节点、不静默丢字段。
