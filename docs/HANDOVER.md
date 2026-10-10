# proxy-node-compat · 交接文档

> 面向**完全没参与过本项目**的接手者。读完这一份 + 跑通 §4 的命令，即可开工。
>
> - 基线：本仓库 `HEAD = 62850a3`（2026-10-10 19:38 +0800），共 25 个 commit、228 个被跟踪文件。
> - **本文所有数字都是从仓库实际文件里数出来的，或来自实跑命令的输出**；每个结论后面标了它来自哪个文件。
> - 风格约定：`✅` 有真内核回环证据 ｜ `🟡` 只到配置层/源码层 ｜ `❓` UNKNOWN（没证据）。
> - 配套阅读顺序：本文 → `docs/00-design-principles.md`（宪法）→ `docs/phase4-report.md`（Phase 4 交付报告）→ `research/empirical/README.md`（真内核证据怎么读）。

---

## 0. 三十秒速览

```
客户端 → 读分享 URL/订阅 → 解析 URI
      → 【交给 proxy-node-compat】→ Node Profile（内核无关）
      → 按 Kernel + Version 判断 → 结构化结果（status / levels / losses / unknowns / reason_codes）
      → 客户端自己决定 显示 / 隐藏 / 分组 / 禁用
      → 客户端自己的内核生成配置并运行
```

**一句话**：它是跨代理内核的 **Node Compatibility Layer** —— 只回答"这个节点交给这个内核（含版本/构建/平台），到底能不能**完整**用；不能的话**损失什么、还是根本不知道**"。

**它不是**：不是转换器、不是配置生成器、不是订阅管理器、不是内核。

**当前最大的两个事实**（接手必读）：

1. **判定数据是真的、也是薄的。** 67 条规则里 51 条是"版本无关的事实"，真正带版本区间的只有 16 条，且多数规则的版本边界**只在一个点上被验证过**（见 §7）。
2. **引擎里有 3 个"声明了但没人读"的字段**（`Segment.condition`、`Rule.transition`、`unknown_distribution_policy`），这直接造成了一个已知误报和一个"看起来生效其实靠别的机制"的假象。见 §8.1 与 §5.6。

---

## 1. 这个项目是什么 / 不是什么

### 1.1 一句话

> 它不生成配置、不转换节点、不接管任何客户端的运行职责。
> 它只回答一个问题：**这个节点，对当前客户端/内核（含版本）到底能不能完整使用？**
> （`README.md:4-6`）

### 1.2 三条不可违反的原则

出处：`docs/00-design-principles.md`（该文件自称"本项目的宪法"，P1–P13）。
与代码冲突时以它为准；**找不到依据的新行为，先改这份文件再改代码**（`docs/00-design-principles.md:3-4`）。

| # | 原则 | 出处 | 落到代码/数据上的样子 |
|---|---|---|---|
| **1** | **绝不静默丢失能力**（最高优先级） | P2（`00-design-principles.md:27-39`） | 解析全程保留原文（`raw_uri`/`raw_fields`）；表达不了的进 `extensions[]`；返回 `SUPPORTED_WITH_LOSS` + 逐条 `losses[]`，**绝不"删掉字段然后说支持"** |
| **2** | **"能解析" ≠ "支持"** | P3（`:43-61`） | 判定只能基于官方文档/官方源码/**真内核运行回环**/抓包；未知一律 `UNKNOWN`，**不允许猜**；每条能力条目必须带 `evidence` |
| **3** | **架构不写死内核** | P11（`:169-177`） | 禁止 `if kernel == "mihomo"` 式判断地狱；支持矩阵全部走**数据**（Capability Registry）；**新增内核 = 新增数据，不改引擎** |

> 原则 2 不是理论洁癖。实测反例：给 mihomo 一个**根本不存在的** `network` 名，`mihomo -t` 依然返回成功，运行时会**静默按 tcp 处理** —— 用户得到一条"能导入、能启动、就是不通"的节点（`docs/00-design-principles.md:56-58`，回环原始记录 `research/empirical/probe-results.json` → `loopback.xray_server_tcp__mihomo_client_nonsense_transport` = `silent_fallback`）。

### 1.3 明确不做的事（同样是纪律）

| 不做 | 出处 |
|---|---|
| 不生成任何内核的配置、不接管"最终跑起来"的职责 | P1（`00-design-principles.md:8-23`） |
| 不替客户端决定"显示还是隐藏"（只给结论，决策权在客户端） | P1 |
| 不改三个内核仓库、不重写分享系统、不自动转换协议、不自动删除不支持字段、不自动换 transport | P12（`:181-194`） |
| 不把"能解析"当"支持"、不对未知能力默认判支持 | P12 |
| 判定**只在 compat 里发生一次**；生成阶段不做兼容性判断 | `docs/compatibility-evaluation.md:118-126` |

---

## 2. 当前状态

### 2.1 硬数字（本节所有数字均来自实跑输出或对文件的直接计数）

| 指标 | 数值 | 怎么数出来的 |
|---|---|---|
| 单元测试 | **40 个，全绿** | `python3 -m unittest discover -s tests` → `Ran 40 tests in 0.078s / OK` |
| 能力规则 | **67 条** | `python3 -m proxy_node_compat capabilities` 首行 → `注册表覆盖 67 条规则（证据 26 条）` |
| └ 按内核 | xray 23 / mihomo 23 / singbox 21 | 遍历 `data/rules.json` 的 `target.kernel` |
| └ 版本无关规则 | **51 条**（`version_independent: true`） | 同上 |
| └ 带未知区间的规则 | **16 条**（`transition: UNKNOWN`），共 **17 个** `unknown_range` 条目 | 同上 |
| └ 无版本证据规则 | **0 条**（`evidence_only` 在数据里从未使用） | 同上 |
| └ 段落（segments）总数 | 69 | 同上 |
| 证据条目 | **26 条**，全部填了 `limits`（26/26） | `data/rules.json` 的 `evidence[]` |
| └ 类型分布 | SRC 7 / CONFIG_VALIDATION 7 / RUNTIME_TEST 6 / DOC 5 / RELEASE 1 | 同上 |
| └ 置信度 | HIGH 16 / MEDIUM 10 / LOW 0（无 INFERENCE） | 同上 |
| URI 表达力规则 | **12 条** | `data/rules.json` 的 `uri_rules[]` |
| └ 表达力 | NONE 8 / FULL 3 / PARTIAL 1 | 同上 |
| 真内核探针结果 | **63 条**（静态 60 + 回环 3） | `research/empirical/probe-results.json` → `results` 长度 |
| └ 判词分布 | accepted 43 / accepted_unverified 7 / not_representable 7 / rejected 3 / works 2 / silent_fallback 1 | 同上 |
| 跨内核矩阵用例 | **60 条** | `research/empirical/raw/cross-kernel-matrix-results.json` → `results` 长度 |
| └ 判词分布 | PASS 32 / RUNTIME_FAIL 21 / CONFIG_REJECTED_CLIENT 6 / CONFIG_REJECTED_SERVER 1 | 同上 |
| └ tier 分布 | AB 46 / B 3 / A 11 | 同上 |
| 设计验收案例 | 14 个 | `docs/examples/README.md` |
| 代码量 | model 277 / registry 223 / engine 403 / uri 481 / cli 190 行 | `wc -l` |
| 规则数据体积 | `data/rules.json` = 62,012 字节 | `ls -l` |
| 第三方依赖 | **0**（`pyproject.toml` 的 `dependencies = []`） | `pyproject.toml:9` |

### 2.2 Phase 1–4 逐阶段做到哪

| 阶段 | 产物 | 做到哪 | 验证到什么程度 |
|---|---|---|---|
| **Phase 1 · 研究** | `research/kernel-xray.md`（374 行 / 114 处 `[src]` / 51 处 `[doc]` / 0 处 `[test]`）<br>`research/kernel-mihomo.md`（732 行 / 235 `[src]` / 64 `[doc]` / 0 `[test]`）<br>`research/kernel-singbox.md`（692 行 / 135 `[src]` / 54 `[doc]` / **126 `[test]`**）<br>`research/oss/`（6 份，共 4,168 行）<br>`docs/07-version-and-failure-model.md` | ✅ 三家源码级能力清单 + 生态调研 + 版本/失败模式模型 | 🟡 **文档+源码层为主**。sing-box 那份含真机 `[test]`（自建两个二进制 + ~55 条 `check` + 官方 1.14.1 交叉复现，`docs/07-version-and-failure-model.md:229-232`）；**xray / mihomo 两份全文 0 条 `[test]`** —— 它们的结论要靠 `research/empirical/` 补 |
| **Phase 1.5 · 生态再定位** | `docs/06-oss-landscape.md`（357 行） | ✅ 9 个项目对照；结论是"**不是替代，是补位**"（`:319-323`） | 🟡 部分是"读码 + 子代理报告"，未编译未运行（该文件 `附：证据分级` 逐条自陈，`:348-357`） |
| **Phase 2 · 模型设计** | `docs/universal-node-profile.md`（248 行） | ✅ 设计完成（`11861d8`），**只设计不实现** | 🟡 设计层；由 Phase 4 的不变式校验 + 测试落实 |
| **Phase 3 · 注册表/URI/证据/判定设计** | `docs/kernel-capability-registry.md`（262 行）<br>`docs/uri-representation.md`（107 行）<br>`docs/compatibility-evaluation.md`（138 行）<br>`docs/evidence-model.md`（104 行）<br>`docs/examples/README.md`（14 案例，271 行） | ✅ 设计完成，含"禁编版本边界"的三写法与证据三条硬规则 | 🟡 设计层 + 14 个案例的"预期结果"；案例的实际输出在 Phase 4 才验 |
| **Phase 4A–4D · 实现** | `model.py` / `registry.py` / `engine.py` / `uri.py` / `cli.py` / `data/rules.json` / `tests/test_all.py` / `pyproject.toml`（提交 `661e8cc`） | ✅ 全部落地：五态 presence、八源 provenance、不变式 I1–I7、分层判定、失败模式、组合约束、URI 独立表、CLI 三命令、零第三方依赖 | ✅ **40 个测试全绿**（提交时是 26 个，后续验证轮加到 40） |
| **Phase 4 报告** | `docs/phase4-report.md`（93 行，提交 `fefe49a`） | ✅ 交付报告 | ⚠️ **已过时**：它写的是 `Ran 26 tests`、`19 条证据 + 16 条能力规则 + 4 条 URI 规则`（`:17-18,31`），今天是 40 / 26 / 67 / 12。案例输出里的 `semantic=UNKNOWN`（`:42`）现在已变成 `SUPPORTED`。**以本文和实跑为准。** |
| **Phase 4 验证轮**（提交 `c53d795`…`62850a3`，共 13 个 commit） | 真内核探针 63 条、跨内核矩阵 60 条、VLESS Encryption 三内核实证、AnyReality 结案、两份参数质量报表、X 部署调查、**X 客户端接入** | ✅ 见 §2.3 与 §7 | ✅ 这一轮才把"文档层结论"变成"真内核证据"；也是**唯一**一轮产生了 `RUNTIME_TEST` 证据 |

**演进顺序（看 `git log --oneline` 的 25 条）**：研究 → 设计 → 实现 → 验证 → 接入。
关键节点：`95c8be7`(initial) → `f8b65f6`(生态调研+真内核证据) → `76b949e`/`7574e8c`/`b70ac74`(版本与失败模型/mihomo 能力/死字段手法) → `11861d8`(Phase 2/3 设计) → `661e8cc`(Phase 4 实现) → `c53d795`(真链接端到端，修 3 个真实缺口) → `e6ae727`(失败模式四态→六态) → `dec3db0`(60 用例矩阵入库) → `62850a3`(X 客户端接入 + hysteria2 假 UNSUPPORTED 修正)。

### 2.3 验证强度分级（★ 本文档最重要的一张表）

| 等级 | 含义 | 覆盖到哪里 |
|---|---|---|
| ✅ **真内核回环** | 起真服务端 + 真客户端，curl 取回内容 | 三家内核的协议/传输/安全组合（`cross-kernel-matrix.md` 60 用例）、mihomo xhttp、mihomo 未知 transport 静默降级、Xray ss+reality、三家 ECH、三家 vision+reality、三家 flow 无 TLS |
| 🟡 **配置校验 / 源码层** | `xray -test` / `mihomo -t` / `sing-box check` 通过，或读了官方源码 | 大部分协议/传输的"存在性"；**mihomo 上除 xhttp 外的 ws/grpc/http_h2/httpupgrade/mkcp 全部只到这一层**（`accepted_unverified` 7 条，`research/empirical/README.md:104-106`） |
| ❓ **UNKNOWN** | 没证据，按纪律不猜 | 见 §7.3 全清单 |

---

## 3. 架构与代码地图

### 3.1 判定流水线

```
raw URI / profile JSON
        │
        ▼  ① parse_uri()                        proxy_node_compat/uri.py
   NodeProfile  ── raw.uri / raw.fields 字节不变（不变式 I1）
        │         ── 未知 scheme → unknown:<scheme> feature，不抛错
        │         ── 未知参数 → extensions[]（不变式 I2）
        ▼  ② evaluate(profile, target, registry)  proxy_node_compat/engine.py
   ┌──────────────────────────────────────────────────────────┐
   │ 2.1 发行版/fork：无规则 → 内核侧层级全 UNKNOWN（不继承上游）│
   │ 2.2 匹配规则 registry.rules_for(kernel, dist, features)  │
   │ 2.3 挑段落 _segment_for()：                                │
   │       evidence_only → UNKNOWN                              │
   │       version_independent → 直接取第一段                    │
   │       version 缺失 → UNKNOWN（不猜）                        │
   │       命中 unknown_range → UNKNOWN（不外推）                │
   │       无段落覆盖 → UNKNOWN                                  │
   │ 2.4 施加段落 _apply_segment()：                             │
   │       build tags → BUILD_NOT_ENABLED / UNKNOWN             │
   │       runtime_condition → RUNTIME_CONDITION_NOT_MET        │
   │       verdict → 分层结论；failure_mode → 静默类升级为 LOSS  │
   │       constraint（组合约束）→ 直接 UNSUPPORTED              │
   │ 2.5 URI 表达力（独立第三张表）_apply_uri_rules()            │
   │ 2.6 未知命名空间 feature → UNKNOWN                          │
   │ 2.7 R1：只有 INFERENCE 证据 → 不许无警告 SUPPORTED          │
   │ 2.8 汇总：status = 显式判定过的内核侧层级的"最差者"          │
   └──────────────────────────────────────────────────────────┘
        │
        ▼  ③ EvaluationResult（含 levels / losses / warnings / unknowns /
                                reason_codes / evidence / raw_uri / rules_applied）
```

关键实现细节（都在 `engine.py`，改之前先读）：

- 层级：`LEVELS = ("parse", "config", "uri", "runtime", "semantic")`；`KERNEL_LEVELS` 去掉 `uri`（`engine.py:18-20`）。
- **只有被"显式判定过"的层级参与总状态**（`acc.explicit`），没覆盖的层级报 UNKNOWN 但不拖累已独立验证的结论（`engine.py:331-340`）。
- **URI 层的 UNKNOWN 不降级总状态**（"我们没有这条 URI 规则" ≠ "URI 表达不了"，`engine.py:343-350`）。
- 静默类失败强制升级：`failure_mode.startswith("silent_")` → `runtime`/`semantic` 的 `SUPPORTED` 改成 `SUPPORTED_WITH_LOSS`（`engine.py:218-224`）；总状态 `SUPPORTED` + silent → `SUPPORTED_WITH_LOSS`（`:351-352`）。
- 有 warning 且总状态 `SUPPORTED` → 升级为 `SUPPORTED_WITH_WARNING`（`:353-354`）。
- 节点自身显式字段可满足运行期条件（如 URI 里的 `fp` → mihomo 的 `client-fingerprint`），但**必须留痕** `RUNTIME_CONDITION_FROM_PROFILE`（`engine.py:40-61, 204-213`）。

### 3.2 代码文件表

| 文件 | 行数 | 干什么 | 改它的风险 |
|---|---|---|---|
| `proxy_node_compat/__init__.py` | 19 | 导出 API + `check_node(uri_or_profile, target, registry=None)` 最简入口 | 低 |
| `proxy_node_compat/__main__.py` | 3 | `python3 -m proxy_node_compat` 入口 | 无 |
| `proxy_node_compat/model.py` | 277 | Phase 4A：`Presence`(5) / `Provenance`(8) / `Field` / `Feature` / `NodeProfile` / 不变式自检 / 无损序列化 | **不动**（模型变更是认识论级变更） |
| `proxy_node_compat/registry.py` | 223 | Phase 4B：版本解析与区间判定 / `Rule` `Segment` `Evidence` / 加载与证据引用校验 / 查询 | 中；加载期会校验"引用了不存在的证据"并抛错（`:182-184`） |
| `proxy_node_compat/engine.py` | 403 | Phase 4B：`Target` / `_Acc` / `_segment_for` / `_apply_segment` / `evaluate` / `_apply_uri_rules` | **高**，这是判定核心 |
| `proxy_node_compat/uri.py` | 481 | Phase 4C：URI 解析（10 个 scheme + 未知 scheme/传输）、`generate_uri` 回写（含 vmess base64 JSON） | 高；`SCHEMES`/`TRANSPORT_MAP`/`PARAM_OWNER` 三张表是"加数据"的地方 |
| `proxy_node_compat/cli.py` | 190 | Phase 4D：`check` / `check-many` / `capabilities` | 低 |
| `proxy_node_compat/data/rules.json` | 62 KB | 67 规则 + 26 证据 + 12 URI 规则 | **这是日常改动的主战场**，见 §5 |
| `tests/test_all.py` | 506 | 40 个用例：模型/引擎/版本边界红线/URI/真实链接 | 加测试是**唯一**被鼓励的代码改动 |
| `tools/probe/probe.py` | 358 | 数据驱动的两层探针（Tier A 静态 / Tier B 回环） | 中 |
| `tools/probe/cases.json` | 21 静态用例（1 条控制组）+ 3 回环场景 | 探针用例全是数据 | 低 |
| `tools/probe/kernels.example.json` | 47 | 三个内核的调用方式（路径是示例，跑之前必须指向自己的副本） | 低 |
| `tools/probe/loopback_matrix.py` | 916 | 跨内核矩阵回环探针（在 RN 上跑），60 用例由 `build_cases()` 生成 | 中 |

### 3.3 关键数据结构

| 结构 | 定义处 | 字段与语义 |
|---|---|---|
| `Presence` (enum) | `model.py:16-23` | `ABSENT`（根本没有）/ `EXPLICIT`（明确写了，含空串/false/0）/ `DEFAULTED`（协议规范规定的默认值）/ `INFERRED`（推断）/ `UNKNOWN`（上游已抹平）。**`Field.__post_init__` 强制：ABSENT 不许有值、INFERRED 必须有 `basis`**（`model.py:68-72`） |
| `Provenance` (enum) | `model.py:26-34` | `URI` / `XRAY_JSON` / `MIHOMO_YAML` / `SINGBOX_JSON` / `SUBSCRIPTION` / `INFERRED` / `USER_DEFINED` / `EXTENSION`。冲突优先级见 `PROVENANCE_RANK`（`model.py:38-42`） |
| `Field` | `model.py:58-107` | `{presence, v, provenance, raw_key, basis}`。`raw_key` = 它在原始输入里的键名（含别名） |
| `Feature` | `model.py:110-150` | `{id, presence, provenance, params: dict[str,Field], requires[], excludes[], note}`。**id 必须在命名空间语法内**：`standard:` / `custom:` / `unknown:` / `<vendor>:`（`valid_feature_id`，`model.py:48-55`） |
| `NodeProfile` | `model.py:153-277` | `protocol: Feature` + `features: list[Feature]` + `endpoint`/`auth`/`metadata: dict[str,Field]` + `extensions[]` + `diagnostics[]` + `raw_uri` + `raw_fields` + `source_format`。**不含任何内核版本字段**（不变式 I7）；`roundtrip()` 用于"不静默丢信息"测试 |
| `Segment` | `registry.py:81-96` | `{range, verdict: {level: status}, failure_mode, reason_code, losses[], warnings[], requires_build_tags[], runtime_condition, condition(⚠️ 死字段), note}` |
| `Rule` | `registry.py:99-150` | `{rule_id, target{kernel,distribution}, selector, segments[], transition(⚠️ 引擎不读), unknown_range[], evidence_only, version_independent, evidence[], unknown_distribution_policy(⚠️ 死字段), constraint, mismatch, reason_code, message}` |
| `Target` | `engine.py:64-80` | **六维输入**：`kernel` / `distribution` / `version` / `build_tags`（`None` = 未知，**不是"空"**）/ `platform` / `runtime_options` / `evaluated_at`（⚠️ 当前引擎不读） |
| `EvaluationResult` | `engine.py:83-107` | `status` / `levels` / `reason_codes[]` / `message` / `failure_mode` / `losses[]` / `warnings[]` / `unknowns[]` / `detected_features[]` / `evidence[]` / `raw_uri` / `rules_applied[]` |
| `Evidence` | `registry.py:153-166` | `{id, type, confidence, date, claim, how, where, limits}` |

### 3.4 状态机（恰好五个，不增不减）

| status | 含义 |
|---|---|
| `SUPPORTED` | 完整支持，无损 |
| `SUPPORTED_WITH_WARNING` | 能用但有注意项（**不是**损失） |
| `SUPPORTED_WITH_LOSS` | 能用但**确定会丢能力**（必须逐条列 `losses[]`） |
| `UNSUPPORTED` | 明确不支持（必须有 `reason_code`） |
| `UNKNOWN` | 证据不足 —— **合法且鼓励的答案** |

`reason_code` 取值见 `docs/kernel-capability-registry.md:223-239`（10 个）。**新增一个 code 的门槛：必须能对应到一类不同的客户端 UI 动作**。

按 `policy` 筛选（`docs/compatibility-evaluation.md:87-96`）：`strict` 只留 `SUPPORTED`；`normal` = `SUPPORTED` + `WARNING`；`permissive` 再加 `LOSS`。**`UNSUPPORTED` / `UNKNOWN` 在任何 policy 下都不进"可用"集合，但必须保留原始 URI。**（注：`policy` 目前只在设计文档里，**`evaluate()` 没有实现 policy 参数**，筛选在调用方做。）

### 3.5 文档地图

| 文件 | 一句话 |
|---|---|
| `docs/00-design-principles.md` | 宪法（P1–P13），**冲突时以它为准** |
| `docs/universal-node-profile.md` | Phase 2：profile / presence / provenance / 命名空间 / 不变式 I1–I7 |
| `docs/kernel-capability-registry.md` | Phase 3：规则形状、三种精度写法、六态失败模式、组合约束、reason taxonomy |
| `docs/uri-representation.md` | Phase 3：URI 表达力独立表（内核支持 ≠ URI 能表达） |
| `docs/compatibility-evaluation.md` | Phase 3：判定优先级、结果结构、唯一检查点 |
| `docs/evidence-model.md` | Phase 3：证据类型/置信度/三条硬规则（R1/R2/R3） |
| `docs/07-version-and-failure-model.md` | Phase 1：版本维度五形态 + 失败模式六态 + mihomo 结构性根因 |
| `docs/06-oss-landscape.md` | Phase 1.5：9 个生态项目对照与本项目定位 |
| `docs/phase4-report.md` | Phase 4 交付报告（**数字已过时，见 §2.2**） |
| `docs/examples/README.md` | 14 个设计验收案例 |

---

## 4. 怎么跑

### 4.1 CLI 三个命令

零依赖，直接 `python3 -m proxy_node_compat ...`（安装后是 `proxy-node-compat ...`，见 `pyproject.toml:14-15`）。

**① `check` —— 单节点**（`--kernel` 必填；`--version` 缺省则版本相关判断全 UNKNOWN）

```bash
cd /root/deepseek/repos/proxy-node-compat
python3 -m proxy_node_compat check "vless://u@1.2.3.4:443?type=xhttp" \
    --kernel mihomo --version 1.19.32 -v
```

实测输出（2026-10-10 实跑）：

```
🟡 SUPPORTED_WITH_WARNING  [?]
   目标: mihomo 1.19.32
   分层: parse=UNKNOWN  config=SUPPORTED  uri=SUPPORTED  runtime=SUPPORTED  semantic=SUPPORTED
   🟡 注意: VERSION_NOT_EXACTLY_PROBED —— 只回环验证过 1.19.32；1.19.22–1.19.31 未逐版验证
   ❓ 未知: 层级 parse —— 没有任何证据覆盖该层级
   证据:
     - [RUNTIME_TEST/HIGH] mihomo 1.19.32 真正支持 xhttp（回环接通）  ↳ research/empirical/probe-results.json#loopback.xray_server_xhttp__mihomo_client_xhttp  (局限: 只证明 1.19.32)
     - [RELEASE/MEDIUM] mihomo xhttp 自 v1.19.22 起支持  ↳ research/kernel-mihomo.md  (局限: 边界来自 release note，未逐版运行)
     ...
   原始链接已保留: vless://u@1.2.3.4:443?type=xhttp
```

变换 `--kernel` 即可看到跨内核方向性差异（同样命令，实测）：

```
# --kernel singbox --version 1.14.2
❌ UNSUPPORTED     分层: parse=UNKNOWN config=UNSUPPORTED uri=SUPPORTED runtime=UNSUPPORTED semantic=SUPPORTED
   原因码: KERNEL_NEVER_SUPPORTED   失败模式: hard_error

# --kernel singbox --distribution sing-box-lx --version 1.14.2
❓ UNKNOWN         原因码: UNKNOWN_CAPABILITY
   ❓ 未知: distribution=sing-box-lx —— 该发行版/fork 没有任何能力规则；fork 不得默认继承上游

# --kernel mihomo（不给 --version）
❓ UNKNOWN         原因码: UNKNOWN_CAPABILITY
   ❓ 未知: mihomo.transport.xhttp: 目标版本未知 —— 未提供 version —— 版本相关的规则无法判定（不影响版本无关的规则）
   ⓘ 缺少信息: --version; --build-tags（内核 build 标签, 影响可选能力） —— 受影响的判断已标 UNKNOWN, 未用默认值替代
```

常用参数：`--distribution` / `--version` / `--build-tags with_utls,with_quic` / `--platform` / `--runtime k=v`（可重复）/ `--evaluated-at` / `--json` / `-v`（显示证据与局限）/ `--registry <路径>`。
`--json` 输出 `{"target": {...}, "result": {...}}`，适合被客户端消费。

**② `check-many` —— 批量**（每行一个链接，`#` 开头与空行跳过；**单行解析失败只跳过那一行，不拖垮整批**，`cli.py:167-170`）

```bash
printf '%s\n' \
 'vless://u@1.2.3.4:443?type=xhttp&security=reality&pbk=AAA&sid=01&fp=chrome#n1' \
 'hysteria2://pw@1.2.3.4:8443?sni=a.com#n2' \
 'vmess://bm90LXZhbGlkLWJhc2U2NA==#n3' \
 'magic://x@1.2.3.4:443?foo=bar#n4' > /tmp/nodes.txt
python3 -m proxy_node_compat check-many /tmp/nodes.txt --kernel xray --version 26.3.27
```

实测收尾：

```
────────────────────────────────────────────────────────────
共 4 个节点: SUPPORTED=2  UNKNOWN=2
提示: UNKNOWN 表示证据不足（不是不支持）; UNSUPPORTED 才是明确不支持。
```

第 3、4 行（畸形 vmess 载荷 / 未知 scheme）都**没有拖垮整批**，且 `raw_uri` 原样带出。

**③ `capabilities` —— 列出注册表覆盖了什么**

```bash
python3 -m proxy_node_compat capabilities            # 全部
python3 -m proxy_node_compat capabilities --kernel mihomo
python3 -m proxy_node_compat capabilities --json
```

实测首行与末 3 行：

```
注册表覆盖 67 条规则（证据 26 条）:
  ...
  - xray.combo.flow_without_tls                  xray     版本无关
  - xray.combo.xhttp_muxcool                     xray     版本无关
  - xray.protocol.hysteria2                      xray     含未知区间
```

**怎么用这一行**：每条规则后面那列是它的诚实度标签 —— `版本有界`（有确切区间）/ `含未知区间`（两端有证据、中间无）/ `版本无关`（与版本无关的事实）/ `无版本证据`（`evidence_only`，当前 0 条）。

### 4.2 Python API

```python
from proxy_node_compat import check_node, Target, parse_uri, evaluate, Registry, default_registry_path

# 最简：URI 字符串 → EvaluationResult
res = check_node("vless://u@1.2.3.4:443?type=xhttp",
                 Target(kernel="mihomo", version="1.19.32"))

print(res.status)            # SUPPORTED_WITH_WARNING
print(res.levels)            # {'parse': 'UNKNOWN', 'config': 'SUPPORTED', ...}
print(res.losses, res.unknowns, res.reason_codes, res.evidence)
print(res.raw_uri)           # 永不丢
res.to_dict()                # 可直接 JSON 化（客户端消费的形状）

# 需要复用 Registry（逐节点调用时务必缓存，否则每个节点重载 62KB 规则）
reg = Registry.load(default_registry_path())
r2 = evaluate(parse_uri(uri), Target(kernel="xray", version="26.3.27"), reg)
```

`check_node` 签名在 `__init__.py:24-28`。结构化结果的完整字段见 §3.3。

### 4.3 跑测试

```bash
cd /root/deepseek/repos/proxy-node-compat
python3 -m unittest discover -s tests        # → Ran 40 tests ... OK
python3 -m unittest tests.test_all -v        # 看每个用例名
```

40 个用例分布（`tests/test_all.py`）：模型/不变式 4、引擎与 18 个案例 14、**版本边界红线 5**、Xray hysteria2 回归 3、URI 回写 3、真实链接 vmess 5 / vless-encryption 2 / reality 身份 2 / ss 1 / 端到端 1。
其中 `test_redline_middle_version_is_unknown`（`:206`）是**"禁止编造版本边界"这条红线的钉子**：中间版本必须得到 `UNKNOWN`。

### 4.4 用真内核探针（唯一能产出 `RUNTIME_TEST` 证据的途径）

`tools/probe/probe.py` 是**数据驱动**的：内核怎么调用在 `kernels.example.json`，用例长什么样在 `cases.json`，代码里没有 `if kernel == ...`。

**前提：需要能访问 RN（测试服务器）上三个内核的二进制。** `kernels.example.json` 里的路径就是 RN 上的真实路径：

| 内核 | binary | 校验命令 |
|---|---|---|
| xray | `/usr/local/bin/xray` | `xray -test -config {config}` |
| mihomo | `/root/catmi/mihomo/mihomo` | `mihomo -t -f {config} -d {workdir}` |
| singbox | `/root/catmi/sing-box/sing-box` | `sing-box check -c {config}` |

```bash
# 1) 在 RN 上放一份自己的内核路径副本（不要改仓库里的示例文件）
scp tools/probe/kernels.example.json rn:/tmp/probe/kernels.json   # 路径已对，直接可用

# 2) 跑（Tier A 静态 + Tier B 回环）
python3 tools/probe/probe.py --kernels xray,mihomo,singbox \
    --config tools/probe/kernels.example.json \
    --out research/empirical
# 只跑某一条 / 跳过回环：
python3 tools/probe/probe.py --only transport.xhttp
python3 tools/probe/probe.py --skip-loopback

# 3) 跨内核回环矩阵（60 用例，在 RN 上跑）
python3 tools/probe/loopback_matrix.py --all --out /tmp/xtest/results.json
python3 tools/probe/loopback_matrix.py --only ctrl-      # 只跑控制组
python3 tools/probe/loopback_matrix.py --list           # 列用例名
```

**三条必须遵守的探针纪律**（`research/empirical/README.md:30-37`）：

1. **控制组先行**：每个内核都有一条必然通过的用例；对照不过 = **探针坏了，不是内核不支持**，这一轮结果整体作废（`probe.py:265-275`）。
2. **`✅?`（`accepted_unverified`）= 校验通过但该字段内核根本不校验**，必须降级，只有 Tier B 能定论。实测 mihomo 对 `network` 就是这样（`cases.json` 里 `tier_b_required` 列了 8 条用例的 mihomo）。
3. **每个 `❌` 都必须读内核原文甄别**：是"内核不支持"，还是"我的测试数据写错了"？`research/empirical/README.md:134-144` 记录了上一轮抓到的 3 个**自己写错数据**的例子。

输出落到 `--out` 目录的 `probe-results.json`（当前仓库里的那份 `generated: 2026-10-10`，`controls_ok: {xray: true, mihomo: true, singbox: true}`）。

---

## 5. 数据怎么维护（`data/rules.json`）

> 这是**日常改动的主战场**。绝大多数需求（新内核、新协议、新证据、修判定）都应该是"只改数据"。

### 5.1 规则的三种版本写法（精度由证据决定，不是作者的选择）

出处：`docs/kernel-capability-registry.md:88-119`、`docs/evidence-model.md:54-64`（R2）。

**(a) 有确切边界 —— 直接写区间**

```json
{
  "rule_id": "mihomo.transport.xhttp",
  "target": {"kernel": "mihomo", "distribution": "upstream"},
  "selector": {"feature": "standard:xhttp"},
  "segments": [
    {"range": "< 1.19.22",
     "verdict": {"config": "SUPPORTED", "runtime": "SUPPORTED_WITH_LOSS"},
     "failure_mode": "silent_ignore", "reason_code": "KERNEL_NEVER_SUPPORTED"},
    {"range": ">= 1.19.22",
     "verdict": {"config": "SUPPORTED", "runtime": "SUPPORTED"},
     "warnings": [{"code": "VERSION_NOT_EXACTLY_PROBED",
                   "detail": "只回环验证过 1.19.32；1.19.22–1.19.31 未逐版验证"}]}
  ],
  "unknown_range": [{"range": "< 1.19.22", "why": "..."}],
  "transition": "UNKNOWN",
  "evidence": ["e-mihomo-network-lax", "e-mihomo-xhttp-loopback"]
}
```

**(b) 两端已知、中间未知 —— 两段 + `transition: UNKNOWN` + `unknown_range[]`**

```json
{
  "segments": [
    {"range": "<= 26.1.23", "verdict": {"config": "SUPPORTED"}, "evidence": ["e-old"]},
    {"range": ">= 26.2.6,  <= 26.9.8", "verdict": {"config": "UNSUPPORTED"},
     "failure_mode": "hard_error", "evidence": ["e-err"]},
    {"range": ">= 26.9.30", "verdict": {"config": "SUPPORTED_WITH_LOSS"},
     "failure_mode": "silent_drop", "evidence": ["e-silent"]}
  ],
  "transition": "UNKNOWN",
  "unknown_range": [
    {"range": "> 26.1.23, < 26.2.6",  "why": "边界由 release note 给出但未逐版验证"},
    {"range": "> 26.9.8,  < 26.9.30", "why": "同上"}
  ]
}
```

这是仓库里真实存在的 `xray.mkcp.header_seed`（`capabilities` 里显示 `含未知区间`）。**同一能力在三段里是三种不同行为**（生效 / 硬报错 / 静默丢弃）。

**(c) 完全没有版本信息 —— `evidence_only: true`**

```json
{"rule_id": "...", "selector": {...}, "evidence_only": true,
 "evidence": ["e-..."], "unknown_range": [{"range": "*", "why": "无任何版本被验证"}]}
```

→ 引擎对任何版本都返回 UNKNOWN（`engine.py:147-150`）。**当前 `rules.json` 里 0 条**（这个能力已实现但没被用上；新增未知内核时它就是第一选择）。

**另一种：`version_independent: true`** —— 与版本无关的事实（见 §5.2）。

### 5.2 `version_independent` 的适用边界

一句话：**只有当"这件事在任何版本上都成立"本身有证据时才能标。**

可以标（仓库里已有的例子）：

| 类型 | 例子 | 证据来源 |
|---|---|---|
| 该内核配置模型里**从来没有**这个东西 | `singbox.xhttp.never`、`singbox.mkcp.never`、`singbox.ss_reality.never` | 全树 grep 0 命中 + `FATAL unknown field` 实测（`research/kernel-singbox.md`） |
| 该内核的**结构设计**决定了它不校验/不生效 | mihomo 未知键永不报错（decoder 无 `ErrorUnused`，proxy option 无一使用 `remain` tag）→ `mihomo.fieldname.sni_vs_servername` | `docs/07-version-and-failure-model.md:152-163` |
| 跨内核**语义不同构** | `xray.combo.xhttp_muxcool`、`xray.mux.semantics` | 60 用例回环矩阵 |
| 组合约束 | `xray.combo.reality_transports`（REALITY 只允许 RAW/XHTTP/gRPC） | 内核原文硬报错 |

**不可以标**（这是最容易犯的错）：

- "旧版本有、新版本没有" → 必须走 §5.1(b) 的三段式，不许标 `version_independent` 来回避版本问题。
- "我们只测了一个版本，就假设全版本一样" → 必须保留 `unknown_range`。
- "某个 fork 大概跟上游一样" → 见 §5.4 的 `distribution`。

> ⚠️ **实现层面的诚实提示**：引擎里 `version_independent` 的语义是"**跳过版本匹配，直接取第一段**"（`engine.py:151-155`）。所以标了它 = 你对任何版本都给这段结论。**它不会替你挡任何东西。**

### 5.3 证据条目的必填字段

形状（`docs/evidence-model.md:24-34`，`registry.py:153-166`）：

```json
{
  "id": "e-mihomo-xhttp-loopback",
  "type": "RUNTIME_TEST",
  "confidence": "HIGH",
  "date": "2026-10-10",
  "target": {"kernel": "mihomo", "version": "1.19.32", "platform": "linux/amd64"},
  "claim": "mihomo 1.19.32 能真正使用 xhttp（回环实测接通）",
  "how": "xray 起 xhttp-only 入站(18444) → mihomo 客户端取回 COMPAT-OK",
  "where": "research/empirical/probe-results.json#loopback.xray_server_xhttp__mihomo_client_xhttp",
  "limits": "只证明了该版本该构建；未验证其它版本"
}
```

| 字段 | 要求 |
|---|---|
| `type` | `DOC` / `SRC` / `RELEASE` / `RUNTIME_TEST` / `CONFIG_VALIDATION` / `PACKET_CAPTURE` / `COMMUNITY` / `INFERENCE` |
| `confidence` | `HIGH` 可真机运行或源码明确分支并亲自复现；**`MEDIUM` 只允许支撑 WARNING/LOSS**；**`LOW` 只能是 UNKNOWN 的佐证**（`docs/evidence-model.md:38-45`） |
| `where` | **必须能追溯**（文件:行 / `results.json#case-id` / URL）。写不出 `where` 的证据等于没有 |
| **`limits`** | **必填**：这条证据"到底证明了什么、没证明什么"。当前 26/26 全部填写（这是一条被守住的纪律，**新加证据时不要破**） |

**加载期强制**：`Registry.load()` 会检查每条规则的 `evidence[]` 引用的 id 是否存在，不存在直接抛 `ValueError`（`registry.py:182-184`）。所以**不许先写规则后补证据**。

**R1 的实现**：如果某条规则的全部证据都是 `INFERENCE` 类型，引擎会把该规则的 `SUPPORTED` 降级为 `SUPPORTED_WITH_WARNING` 并留 `INFERENCE_ONLY_EVIDENCE`（`engine.py:315-328`）。当前数据里 `INFERENCE` 证据 **0 条**。

### 5.4 禁止编造版本边界 —— 这条红线怎么落地

**红线原文**（`docs/evidence-model.md:52-64` R2）：证据只说了"旧版本有、新版本没有"，就**必须**写成 `known_present` / `known_absent` / `transition: UNKNOWN`；**禁止补出一个 `removed_at: <某版本>`**。精度是证据的属性，不是作者的选择。

它靠**七层**落地（前六层是机制，第七层是人）：

| # | 机制 | 位置 |
|---|---|---|
| 1 | 三种写法里，"中间未知"有**专属形状**（两段 + `transition: UNKNOWN` + `unknown_range[]`）—— 想写"边界"就得先有边界证据 | `docs/kernel-capability-registry.md:106-111` |
| 2 | `version_in_range(version=None, spec)` **恒返回 False** —— 没有版本号就永远不命中任何段 | `registry.py:52-56` |
| 3 | `_segment_for()` 命中 `unknown_range` → **UNKNOWN**；没有任何段覆盖 → **UNKNOWN**（绝不外推） | `engine.py:144-170` |
| 4 | 规则引用了不存在的证据 → **加载即抛错** | `registry.py:182-184` |
| 5 | CLI `capabilities` 给每条规则打诚实度标签（`含未知区间` / `版本无关` / `版本有界`），**评审时一眼能看出谁在装** | `cli.py:139-149` |
| 6 | 测试 `test_redline_middle_version_is_unknown` 钉死"中间版本 = UNKNOWN" | `tests/test_all.py:206` |
| 7 | ⚠️ **没有任何代码能阻止你手写一个假的 `removed_at`。** `transition` 字段引擎根本不读（见 §5.6）。**这条红线的最终执行者是人** | — |

**评审一条新规则时问三句**：这个版本区间是哪条证据给出的？那条证据的 `where` 指向哪里？它的 `limits` 写了什么？

### 5.5 改数据的 checklist

1. 先写 `evidence[]` 条目（含 `limits`），`type`/`confidence` 别虚标。
2. 再写规则；`selector` 只能用 `feature` / `protocol` / `all_of_features` 三个键（**没有否定选择器**，见 §8.1）。
3. 选 §5.1 的三种写法之一，**不许自创第四种**。
4. `python3 -m proxy_node_compat capabilities` 看标签是否符合预期。
5. 跑 `python3 -m unittest discover -s tests`（**40 个必须全绿**）。
6. 有条件就跑 §4.4 的探针，拿真内核原文回来。
7. 给新行为补测试。
8. **不要 push**（当前约定：改动留在本地，由人类推送）。

### 5.6 谁在读这些字段（**声明 ≠ 生效**）

接手者最容易踩的坑：数据里写了某个字段，就以为它起作用了。实测（对 `engine.py` 做符号计数）：

| 字段 | 引擎读吗 | 真实影响 |
|---|---|---|
| `segments[].verdict` / `failure_mode` / `reason_code` / `losses` / `warnings` / `note` | ✅ 读 | 正常生效 |
| `segments[].requires_build_tags` / `runtime_condition` | ✅ 读 | 正常生效 |
| `rule.evidence_only` / `version_independent` / `unknown_range` / `selector` / `target` / `constraint` / `mismatch` / `reason_code` / `message` | ✅ 读 | 正常生效 |
| **`rule.transition`** | ❌ **不读**（0 命中） | **纯文档字段**，只被 `capabilities` 显示。UNKNOWN 行为实际来自 `unknown_range` 匹配 + "无段落覆盖"兜底 |
| **`rule.unknown_distribution_policy`** | ❌ **不读**（0 命中） | **死字段**。"fork 不继承上游"实际由 `Registry.kernel_has_distribution_rule()` 实现（看有没有该 kernel+distribution 的规则），不看这个字段 |
| **`segments[].condition`** | ❌ **不读**（0 命中）；数据里也 0 条 | **死字段**，见 §8.1 |
| **`Target.evaluated_at`** | ❌ **不读**（只在 `Target` 里被存/序列化） | **时间闸门未实现**；数据里 `time_gated` 也 0 条 |
| URI 规则的 `carrier` / `spec_added_at` / `workaround` / `note` | ❌ 不读 | 引擎只读 `representation` / `loss` / `evidence` / `uri_rule_id`（`engine.py:384-399`）。`docs/uri-representation.md:57-68` 要求的"参数进规范时间"**尚未生效** |

> 好消息：加载期**没有**静默丢键 —— 我把 `rules.json` 里出现过的所有键与 dataclass 字段做差集，**结果为空**（规则/段落/证据三层都是）。也就是说上面的字段是"被接收但没人用"，不是"被吃掉"。

---

## 6. 怎么扩展（尽量"只加数据"）

出处：`docs/phase4-report.md:67-77`、`docs/kernel-capability-registry.md:243-262`（架构审查表）。

| 要加什么 | 怎么做 | 改代码吗 |
|---|---|---|
| **新内核**（第四个内核） | 在 `data/rules.json` 的 `rules[]` 加 `target.kernel: <新内核>` 的规则；**没数据就先写 `evidence_only: true`** → 结果即全 UNKNOWN | ❌ 不用 |
| **新 fork / 发行版** | 加 `target.distribution: <fork>` 的规则。**不写就自动 UNKNOWN**（"fork ≠ 上游"），绝不会默认继承上游 | ❌ |
| **新协议** | 首选什么都不用做：`uri.py` 会把它落成 `unknown:<scheme>` 并保留全部原文（`uri.py:178-191`）。想要更好体验就在 `uri.py` 的 `SCHEMES` 加一行（scheme → protocol id + 已知参数集） | ❌（可选加一行） |
| **新传输 / 新 feature** | `features[]` 里用 `<vendor>:<name>` 或 `standard:` / `custom:` / `unknown:` 前缀；组合约束用 `requires`/`excludes` 或规则里的 `constraint` | ❌ |
| **新能力层级 / 新失败模式** | 扩 `engine.py` 的 `LEVELS` / 失败模式枚举 | ⚠️ **小改**（认识论级变化，理应显式 —— 不许悄悄塞进已有取值） |
| **新客户端接入** | 见 §10。**不改内核仓库** | ❌ |

**AnyReality 是这套机制的验收样张**：`standard:shadowsocks` + `standard:reality` + `mi1314cat:anyreality.ss-reality`（带 `requires`），**代码里没有任何 anyreality 分支**（`docs/universal-node-profile.md:182-199`、`research/empirical/anyreality.md:90-101`）。

**加新内核的最小动作示例**：

```jsonc
// data/rules.json → rules[]
{
  "rule_id": "newkernel.support.xhttp",
  "target": {"kernel": "newkernel", "distribution": "upstream"},
  "selector": {"feature": "standard:xhttp"},
  "evidence_only": true,
  "evidence": ["e-newkernel-unknown"],
  "unknown_range": [{"range": "*", "why": "尚未对该内核做任何验证"}]
}
// + evidence[] 里加 e-newkernel-unknown（type: COMMUNITY, confidence: LOW, limits: "仅来自二手描述"）
```

结果：`capabilities` 会把它标成 `无版本证据`，任何节点判它都是 `UNKNOWN`（**不是** UNSUPPORTED —— 未知 ≠ 不支持）。

---

## 7. 已验证与未验证的边界

> **这是接手者最容易踩的地方。** 下面按证据强度分三层。每条都标了来源文件。

### 7.1 ✅ 有真内核回环（`RUNTIME_TEST`）证据的结论

来源：`research/empirical/cross-kernel-matrix.md`（60 用例，原始 JSON 在 `research/empirical/raw/cross-kernel-matrix-results.json`，日志在 `raw/logs/`）+ `research/empirical/probe-results.json`（63 条）+ `research/empirical/vless-encryption-mlkem.md` + `research/empirical/anyreality.md`。

| 结论 | 三家表现 | 来源 |
|---|---|---|
| `ss2022 + REALITY`（AnyReality #1） | Xray ✅ 回环通（错 pbk 必失败）／ mihomo ⚠️ **reality 被静默忽略**（打裸 ss 服务端通、打 reality 服务端不通）／ sing-box ❌ FATAL `unknown field "tls"` | `cross-kernel-matrix.md` §2（A1/A2/A3） |
| `vless + tcp + vision + reality` | 三家 ✅ 都回环通 | 同上 §3.1（B1） |
| `vless + xhttp + reality`（含 `mode=packet-up`/`stream-one`） | Xray ✅／mihomo ✅／sing-box ❌ `unknown transport type: xhttp` | 同上 §3.2（B2/B3） |
| `xmux` 的 `maxConcurrency` + `maxConnections` 同填 | Xray ❌ 配置期硬报错（只填其一 ✅） | 同上（B3c/B3d） |
| `vless + ws + reality` | Xray ❌ 硬报错／mihomo ❌ 静默不生效（`silent_noop_then_runtime_fail`）／sing-box ✅ 回环通 | 同上 §3.3（B4），含 3 条隔离对照 |
| `vless + tcp + ECH` | 三家 ✅ 回环通（换错密钥必失败 → 真的发了 ECH）；**sing-box 的 `ech.config` 必须是 PEM** | 同上 §3.4（B5） |
| mux / smux / multiplex | **三方不同构**：Xray=mux.cool（默认关，`v1.mux.cool:9527`）／mihomo=smux（`sp.mux.sing-box.arpa:444`）／sing-box=multiplex（能作 mux.cool 服务端）。跨内核搬 mux ❌ | 同上 §3.5（B6/B6a） |
| **XHTTP + mux.cool 同开** | Xray ❌ 运行期失败 `common/mux: unexpected network TCP` | 同上 §3.5(2)（B6b）+ X 客户端 CC 实测（`x-client-integration.md` §4.2：mux 关 204 / mux 开 000） |
| `flow=xtls-rprx-vision` + `security=none` | 三家都是配置层 ✅ → **运行期 ❌**（`runtime_fail`） | 同上 §3.6（B7） |
| mihomo 未知 `network` 值 | 配置 ✅ → **运行期静默按 tcp**（`silent_ignore`） | `probe-results.json` → `loopback...nonsense_transport` = `silent_fallback` |
| mihomo 真正支持 xhttp | 回环接通 ✅ | `probe-results.json` → `loopback.xray_server_xhttp__mihomo_client_xhttp` = `works` |
| VLESS 后量子 `encryption=mlkem768x25519plus…` | Xray ✅ 原生且真生效／mihomo ✅ 原生且真生效（换密钥即失败）／sing-box ❌ 字段不存在，**三处配置全拒（连 `"none"` 也拒）** | `research/empirical/vless-encryption-mlkem.md` §4 |
| AnyReality 运行层（上一轮的 UNKNOWN） | **已结案**：Xray 能配且能用；mihomo 静默忽略；sing-box 配置层硬报错。上一轮回环失败的原因是**测试环境**（reality 服务端 mimicry 的 8192B 缓冲上限 + 用真实站点当 dest），不是内核 | `anyreality.md:44-49` + `cross-kernel-matrix.md` §2.4 |

### 7.2 🟡 只到配置层 / 源码层的结论

| 结论 | 只到哪一层 | 为什么不够 | 来源 |
|---|---|---|---|
| mihomo 的 `ws` / `grpc` / `http_h2` / `httpupgrade` / `mkcp` / `splithttp` | Tier A（`-t`）**且降级为 `accepted_unverified`** | mihomo **完全不校验 `network`**（实测 4/4 静默降级），所以静态通过毫无意义 | `research/empirical/README.md:104-106`、`docs/07-version-and-failure-model.md:152-163` |
| Xray 的 ECH **运行时**是否真生效 | 配置层 | Xray 对 ECH **内容**不校验：编造的 base64 也 `Configuration OK`（F5）。**但 60 用例矩阵里的 B5 已用错密钥必失败反证"真发了 ECH"** → 这条现在比原来强，但"是否隐藏了 SNI"仍需抓包 | `README.md:122-126`（F5）、`cross-kernel-matrix.md` §3.4 |
| sing-box 的 `grpc` | 源码层 | **官方 sing-box 的 gRPC 不是标准 gRPC**（`grpc.go` vs `grpc_lite.go` 两套实现，官方二进制只有 `v2raygrpclite`）→ "gRPC 校验通过"是静态层幻觉，Tier A 原理上抓不到 | `docs/07-version-and-failure-model.md:245-246` |
| 大部分版本边界 | release note / 源码跨 tag 比对 | 例如 mihomo xhttp "自 v1.19.22 起"来自 release note（`confidence: MEDIUM`），**未逐版运行** | `CLI -v` 输出即会显示这条局限 |
| Xray mKCP `header`/`seed` 的 `>=26.9.30` 静默丢弃段 | 源码 | `docs/examples/README.md:190-192` 自己标注了这一点（`evidence.type = SRC`、`MEDIUM`） | 同上 |
| AnyReality 在 mihomo / sing-box 的**服务端方向** | 未测 | 只测了出站/客户端方向 | `cross-kernel-matrix.md` §7.7 |

### 7.3 ❓ UNKNOWN 全清单（来源 + 待补证据）

**(A) 阶段性的、全局性的 UNKNOWN**

| # | UNKNOWN | 原因 | 待补什么 | 来源 |
|---|---|---|---|---|
| A1 | **`parse` 层普遍 UNKNOWN** | 没有针对"目标内核解析器是否认识该字段"的证据 | 需要能观测内核解析器的实验或源码级逐字段结论 | `docs/phase4-report.md:58` |
| A2 | **`semantic` 层普遍 UNKNOWN** | 没有"运行语义是否等价"的断言（如"UDP 是否真的可用"） | Tier B 回环补语义断言（**注意：矩阵 B1–B7 已经在收窄这一层**） | 同上 |
| A3 | `uri` 层对未覆盖的 `scheme × feature` UNKNOWN | 12 条 URI 规则只覆盖 vless/ss/vmess/trojan/hysteria2/tuic/anytls 的少数 feature | 补 vmess 的 ws/tls（见 §8.2）、以及其余协议参数的链接形态 | `docs/phase4-report.md:59` |
| A4 | 未知 fork / 发行版（如 `sing-box-lx`） | **只有二手描述，未读源码、未实测** | 读 `sing-box-lx` 源码 + 自建二进制实测 | `docs/phase4-report.md:60`、`docs/06-oss-landscape.md:357` |
| A5 | Xray `allowInsecure` 的时间闸门区间 | 引擎**未实现** `evaluated_at`（`Target.evaluated_at` 被接收但从不参与判定），故整段标 UNKNOWN | 实现时间闸门后再给结论；数据里 `time_gated` 目前 0 条 | `engine.py:74-80`、`rules.json` → `xray.tls.allow_insecure` 的 `unknown_range: "< 26.7.11"` |
| A6 | 大多数规则的"引入点"到"被验证的那一版"之间 | 只验证过 **1 个版本/内核**（见 §7.4） | 逐版二分（成本高，按需） | `docs/phase4-report.md:62` |
| A7 | 所有 60 个矩阵用例的**版本边界** | 矩阵只覆盖 `Xray 26.3.27 / mihomo 1.19.32 / sing-box 1.14.2` 三个点 | 逐版二分 | `cross-kernel-matrix.md` §7.1 |
| A8 | **UDP 覆盖为零** | 所有回环都用 TCP 目标（`curl`） | `network: tcp,udp` / `xudp` / `uot` / mux 下 UDP 的回环 | `cross-kernel-matrix.md` §7.6 |
| A9 | `xmux` 默认值冲突（源码 `maxConcurrency=1-1` vs 官方 discussion `"16-32"`），且运行语义（并发是否真被限制）未测 | 二者矛盾，未做运行期测量 | 运行期测量 | `cross-kernel-matrix.md` §7.4 |
| A10 | ECH 的回落细节（错密钥时是直接失败还是先重试）、外层 SNI 是否泄露、`echForceQuery` 路径 | 只有"失败"这个结果 | 抓包 | `cross-kernel-matrix.md` §7.5 |

**(B) 具体能力项的 UNKNOWN（摘录，全清单在各自文件里）**

| 项 | 为什么不知道 | 来源 |
|---|---|---|
| mihomo 上 `ws/grpc/http_h2/httpupgrade/mkcp/splithttp` 是否**真能用** | 静态层不可信（内核不校验 network），需逐个回环 | `research/empirical/README.md:150` |
| mihomo 是**从哪个版本**开始支持 `encryption` | 只验了 1.19.32，按 R2 不得插值 | `vless-encryption-mlkem.md` §7 |
| mihomo 的 `xorpub`/`random` xorMode 与 Xray **运行时**是否互通；mihomo 能否作 ML-KEM 服务端 | 只回环验了 `native`；mihomo 的 vless 入站未回环 | 同上 |
| Xray 对畸形 `encryption` 值的 **panic** 是否已在更高版本修复 | 未查上游 commit / issue | 同上 |
| h2 transport 被移除的**确切版本**、25.x 是否有过渡兼容 | 需查 changelog / release note | `research/empirical/README.md:153` |
| mihomo 静默降级时**到底**用了什么默认值 | 只能证明"连通了"，需要抓包 | 同上 |
| `xhttp × mux.cool` 在**真实 CDN 节点**上的失败形态 | CC 的 xhttp 节点因 pin 过期根本连不上，无法把失败归因到 mux | `x-client-integration.md` §7 U1 |
| Xray 的 ECH 运行时是否真生效 | 配置层不校验内容；无回环/抓包证据 | 同上 U2 |
| `trojan+REALITY` 在修好 `node.py` 之前的真实可用性 | 客户端解析丢 `pbk`，未构造端到端 | 同上 U4 |
| Xray hysteria2 **入站**方向；`<26.3.27` 的支持情况 | 只验出站；未逐版验证 | 同上 U5/U6 |
| `socks` / `http`（简易出站）的 xray 能力结论 | 注册表没有这两条 xray 协议规则 → 靠回退旧判定 | 同上 U11 |
| `mihomo / sing-box` 客户端的接入效果 | 只接了 X 客户端；纪律要求不动那两个仓库 | 同上 U7 |
| mihomo 作为 **mux 服务端**；`xray mux.cool → mihomo listener` | 未测（无回环） | `cross-kernel-matrix.md` §7.2 |
| 真实站点作 reality `dest` 的适用面 | 只有 microsoft（失败）与本地 Go TLS（成功）两点证据 | 同上 §7.8 |
| 全部 32 个 mihomo/sing-box 节点的**被动 DPI 分类结果**、抗封锁现状、DNS 泄露 | 手上没有 DPI 分类器 / 只从 CC 单点观测 | `research/assessment/mihomo-singbox-quality.md` §5.2（U1/U4/U5） |
| Xray 侧 12 条 UNKNOWN（含 ECH 是否真的隐藏 SNI、`hysteriaSettings.up/down` 是否仍被采纳等） | 需要抓包 / 需要构造特定条件 | `research/assessment/xray-quality.md` §5.2 |
| X 部署侧 4 条 + 5 条 UNKNOWN（含 `obfs=none` 在 sing-box 链接层的解析行为、端口跳跃端到端） | 未取到源码 / 未在隔离环境做 | `research/known-issues/x-deployment-investigation.md` §UNKNOWN |

### 7.4 三个内核到底验证过哪些版本（**必看**）

| 内核 | 唯一被真内核验证过的版本 | 这意味着什么 |
|---|---|---|
| Xray | **26.3.27**（d2758a0, go1.26.1, linux/amd64） | 所有 xray 规则里 `>= 26.3.27` 的那一侧才有 `RUNTIME_TEST`；更早版本一律 `unknown_range` → UNKNOWN |
| mihomo | **v1.19.32**（go1.26.8, with_gvisor） | 同上 |
| sing-box | **1.14.2**（af6e64c, with_utls/with_quic/...） | 同上 |

> ⚠️ 已知的**不一致**：`research/empirical/probe-results.json` 里记的 sing-box 是探针自报的 `1.14.2`，而另一份调研里该路径的二进制自报 `1.14.1`（tags 含 with_purego）→ **需要核对实际二进制来源**（`docs/07-version-and-failure-model.md:255-256` 自己记录了这条）。**接手第一件事之一就是核对它。**

---

## 8. 已知缺口与在办事项

> 排序：前面的更该先做。每条都给了"为什么它是缺口"与"修它要动什么"。

### 8.1 ① 引擎缺否定选择器 / `Segment.condition` 未启用 → `xray.combo.flow_without_tls` 对 reality+vision **误报**

**现象（我已实测复现）**：一个 `vless + tcp + security=reality + flow=xtls-rprx-vision` 的节点（**CC 上实测 204 可用**）被判成损失：

```bash
python3 -m proxy_node_compat check \
  "vless://1111...@1.2.3.4:443?type=tcp&security=reality&flow=xtls-rprx-vision&pbk=AAAABBBBCCCC&sid=0123&fp=chrome&sni=www.example.com#reality-vision" \
  --kernel xray --version 26.3.27
# 🟠 SUPPORTED_WITH_LOSS
#   原因码: RUNTIME_CONDITION_NOT_MET   失败模式: runtime_fail
#   🟠 损失: standard:flow —— xtls-rprx-vision 在 security∉{tls,reality} 时配置层通过、运行期才报错 (xray.combo.flow_without_tls)
```

**根因**：这条规则的 selector 只有 `all_of_features: [standard:flow, standard:transport.tcp]`，**表达不了"且 security 不属于 {tls, reality}"**。引擎的 selector 只支持 `feature` / `protocol` / `all_of_features` 三个键（`registry.py:125-136`），**没有否定/排除语义**；`Segment.condition` 在 dataclass 里存在（`registry.py:91`）但**引擎从不读它**，数据里也 0 条。

**影响面**：`x-client-integration.md` §6 记了 —— 语料 5 条 + CC 2 条受影响；**这是当前唯一的"假会丢能力"误报类别**。

**修法（二选一）**：
- **小**：给 `selector` 加 `none_of_features`（或 `excludes_features`），在 `selector_matches()` 里实现，然后改这条规则的数据。
- **大**：启用 `Segment.condition`（把 `docs/kernel-capability-registry.md:148` 的 `condition: {evaluated_at_before: ...}` 那一类条件真正实现）—— 这条路同时能解决 §8.6 的时间闸门。

**别用**：`if kernel == "xray" and has_reality` 之类的补丁（违反原则 3）。

### 8.2 ② vmess 的 ws/tls 缺 `uri_rules` → uri 层 UNKNOWN

**现象（实测）**：一条正常的 `vmess://`（`net=ws`, `tls=tls`）在 mihomo 1.19.32 上：

```
🟡 SUPPORTED_WITH_WARNING  [vmess-ws-tls]
   分层: parse=UNKNOWN  config=SUPPORTED  uri=UNKNOWN  runtime=SUPPORTED  semantic=SUPPORTED
   ❓ 未知: 层级 uri（scheme=vmess） —— 没有覆盖该 scheme × feature 的 URI 表达力规则
```

**根因**：12 条 `uri_rules` 里 `scheme=vmess` 只有 **1 条**（`uri.vmess.mux`，`NONE`）。`standard:transport.ws` / `standard:tls` 没有对应条目 → 引擎走 `_apply_uri_rules` 的兜底：`uri = UNKNOWN`（`engine.py:400-403`）。

**影响**：vmess 节点的 `uri` 层永远是 UNKNOWN（**好在按 §3.1，uri 的 UNKNOWN 不降级总状态**，所以不产生假结论，只是信息缺失）。

**修法**：**只加数据** —— 在 `uri_rules[]` 里补 `vmess × standard:transport.ws`（`FULL`，载体 `net=ws` + `path`/`host`）、`vmess × standard:tls`（`FULL`，载体 `tls=tls` + `sni`）。同时对照 `_VMESS_QR_KEYS`（`uri.py:88-89`）确认回写路径一致。

### 8.3 ③ 只能进 `extensions` 的字段（vmess `v`、ss `plugin`、vless `fm`）

**现状（实测）**：这三个键在解析器里有名字、但没有归属的 feature，于是全部落到 `extensions[]`，注释是"已收录但未建模到具体 feature"：

```python
# vmess 载荷里的 v（格式版本号）
{"key": "v", "value": "2", "source": "URI", "note": "已收录但未建模到具体 feature"}
# ss:// 的 plugin
{"key": "plugin", "value": "obfs-local;obfs=http", "source": "URI", "note": "已收录但未建模到具体 feature"}
# vless 的 fm（finalmask）
{"key": "fm", "value": "mkcp-aes128gcm", "source": "URI", "note": "已收录但未建模到具体 feature"}
```

**这是"设计上正确、能力上缺失"**：按原则 1，**它们没有丢**（进了 `extensions`、`raw_fields` 里也有原文），但：
- 判定引擎**看不见**它们 → 不会有任何规则覆盖它们；
- URI 回写时 `extensions` 默认不写回（`uri.py:409-411` 需要显式 `allow_extensions=True`）→ round-trip 会丢掉；
- 顺带：`vmess` 的 `type`（header 类型）也走了同一条路。

**修法**：给它们建 feature + 挂进 `PARAM_OWNER`：
- vmess `v` → 可能应该是 `metadata` 类信息（载荷格式版本），而不是能力；
- ss `plugin` → 已经有 `PARAM_OWNER["plugin"] = "standard:shadowsocks.plugin"`（`uri.py:71`），但因为没有这个 feature 的实例，`uri.py:337-339` 会把它判成 `feat = None` → 落 `extensions`。**根因是缺少 feature 实例的构造**；
- vless `fm` → finalmask，`docs/uri-representation.md:64` 明确记了它 **2026-01-31** 才进规范，老客户端静默忽略 → 应该同时补一条 URI 表达力规则与"老客户端"维度。

### 8.4 ④ 失败模式六态已建，但引擎只对 `silent_*` 有动作

- 六态**已写进设计**：`docs/kernel-capability-registry.md:72-83`（`hard_error` / `silent_ignore` / `silent_drop` / `runtime_fail` / `crash` / `silent_noop_then_runtime_fail`）。
- **引擎只实现了两条通用动作**：
  1. `failure_mode.startswith("silent_")` → 把 runtime/semantic 的 `SUPPORTED` 升级为 `SUPPORTED_WITH_LOSS`（`engine.py:218-224`）；
  2. 总状态 `SUPPORTED` 且 failure_mode ∈ {`silent_ignore`, `silent_drop`} → 升级为 `SUPPORTED_WITH_LOSS`（`engine.py:351-352`）。
- **`crash` 与 `silent_noop_then_runtime_fail` 在代码与数据里都是 0 命中**（我对 `proxy_node_compat/`、`tests/`、`tools/` 做了 grep，结果为空）。也就是说：**枚举建了六态，实际只有四态可达**（数据里用到的是 `hard_error` 10 / `silent_ignore` 6 / `runtime_fail` 2 / `silent_drop` 1）。
- **缺的是"客户端动作"**：`docs/07-version-and-failure-model.md:25-26` 要求 —— `crash` 要提示"该配置会让内核崩溃，请勿使用"；`silent_noop_then_runtime_fail` 要提示"这个字段写了等于没写"。目前客户端只能拿到一个字符串自己解释。
- **两条已知的真实案例还没入库**：Xray 26.3.27 对畸形 `encryption` 值 **panic**（`slice bounds out of range [19:18]`，exit 2，上游 bug，`infra/conf/vless.go:355`）、mihomo `encryption: none`/空值 `-t` 通过但连接时 `ML-KEM-768 handshake failed > unexpected EOF`。→ 两条都该有对应规则（`vless-encryption-mlkem.md` §4 已经给出了建议数据行）。
- **修法**：① 把上面两条真实案例写成规则；② 在客户端侧定义每种 failure_mode 的 UI 动作（这是**接入方**的事，见 §10.3）。

### 8.5 ⑤ `tests/__pycache__` 里有被跟踪的历史 `.pyc`，待 `git rm --cached`

实测 `git ls-files | grep pycache`：

```
proxy_node_compat/__pycache__/__init__.cpython-310.pyc
proxy_node_compat/__pycache__/engine.cpython-310.pyc
proxy_node_compat/__pycache__/model.cpython-310.pyc
proxy_node_compat/__pycache__/registry.cpython-310.pyc
proxy_node_compat/__pycache__/uri.cpython-310.pyc
tests/__pycache__/test_all.cpython-310.pyc
```

而 `.gitignore` **已经**写了 `__pycache__/` 和 `*.pyc`（说明是"先跟踪、后加 ignore"的历史遗留）。**6 个文件仍在版本控制里。**

修法（一条命令，注意不要 `git rm` 掉工作区文件）：

```bash
git rm -r --cached proxy_node_compat/__pycache__ tests/__pycache__
git commit -m "清理: 移除被误跟踪的 __pycache__/*.pyc（.gitignore 已覆盖）"
```

**为什么值得做**：`.pyc` 会随 Python 版本/源码变化产生噪声 diff，并且它们**与规则数据的演进没有关系**，评审时会干扰"这次改了什么"。

### 8.6 其他在办事项（按优先级）

| # | 事项 | 为什么 | 参考 |
|---|---|---|---|
| 6 | **时间闸门未实现**：`Target.evaluated_at` 只被存和序列化，从不参与判定；数据里 `time_gated` 0 条 | Xray `allowInsecure` 的结论**依赖系统日期**（`26.2.6–26.5.9` 期间只有系统时间 < 2026-06-01 UTC 才警告+生效）→ 现在整段 UNKNOWN | `docs/07-version-and-failure-model.md:50-52`、`docs/kernel-capability-registry.md:154`、`engine.py:74-80` |
| 7 | `policy`（strict/normal/permissive）只在设计文档里，`evaluate()` 没有这个参数 | 客户端要自己实现筛选，容易出现第二份判断逻辑（违反"判定只发生一次"） | `docs/compatibility-evaluation.md:87-96` |
| 8 | **探针用例需要改名**：`transport.tcp` 对 sing-box 的 `accepted` 容易被误读（sing-box 没有 `tcp` transport，写 `{"type":"tcp"}` 实测是 `FATAL`；该用例实际表达的是"不写 transport"）→ 应改名为 `transport.none`；`advanced.mux` 用例把 Xray 的 `mux` 与 sing-box 的 `multiplex` 并列，**因此抓不到"语义不同构"风险** | 会误导后来者 | `docs/07-version-and-failure-model.md:257-261` |
| 9 | sing-box 二进制来源核对（探针自报 1.14.2 vs 另一份调研自报 1.14.1 with_purego） | 版本是全套结论的基础 | `docs/07-version-and-failure-model.md:255-256` |
| 10 | `docs/phase4-report.md` 的数字与案例输出已过时（26 tests / 16 规则 / 19 证据 / `semantic=UNKNOWN`） | 新人第一份会读到它 | §2.2 |
| 11 | `README.md:86` 写"26 个测试通过"、`README.md:88` 写"尚未接入三个内核项目" | 前者过时；后者已被 X 客户端接入推翻 | `README.md:84-91` |
| 12 | X 部署侧 4 个问题（WARP 出口 IP / 死链 / `gen_psk` / Nginx 周边）与 5 条 UNKNOWN | 其中 Q1/Q3/Q4 **已修**（`xray--core` 提交 `7dfe2a5`），Q2 未改 | `research/known-issues/x-deployment-investigation.md`、`research/known-issues/x-kernel-deployment.md` |
| 13 | `merge` 层的一个待修：`node.py` 的 `parse_trojan()` 不读 `pbk/sid/spx` → trojan+REALITY 假 UNSUPPORTED（现在靠"只收紧"的合并层挡住，不会误导，但结论是错的） | 影响 X 客户端 | `x-client-integration.md` §4.4 P1 |
| 14 | X 客户端的 `Browser Dialer` notes 里"建议开 Mux.Cool"与 `xray.combo.xhttp_muxcool` 的结论**直接打架**，界面上会同时显示两条 | 用户会看见矛盾 | `x-client-integration.md` §4.2 |

---

## 9. 外部依赖与部署边界

### 9.1 三台机器的角色（**不要搞错**）

| 代号 | 是什么 | 能不能碰 | 备注 |
|---|---|---|---|
| **RN** | **测试服务器**（`107.173.154.178`）。三个真内核的二进制都在这里：`/usr/local/bin/xray`、`/root/catmi/mihomo/mihomo`、`/root/catmi/sing-box/sing-box` | ✅ **可以跑探针**，但纪律是：**实验全部在 `/tmp` 下、跑完清理、不改任何正式配置、不重启任何既有服务** | 复现脚本 `tools/probe/loopback_matrix.py` 就是为它写的；`probe-results.json` 的 `kernels[].binary` 就是 RN 路径 |
| **CC** | **客户端实测机**（`192.168.1.178`，armbian/arm64，Xray 26.3.27 d2758a0，客户端 v2.8.3），**局域网内** | ✅ 可以做客户端验收（`cc-verify-v2.sh` 只在 `/tmp` 做事） | `x-client-integration.md:5` |
| **DS** | **生产环境** | 🚫 **禁止触碰** | 本仓库的所有研究都**没有**动过它 |

**已建立的环境卫生惯例**（`research/empirical/vless-encryption-mlkem.md` §"被测版本与方法" 与 §6 甄别记录，值得照抄）：

- 实验全部在 `/tmp/<name>/` 下；用**每用例唯一端口** + 绝对配置路径 + `kill -9 $PID`；
- `pkill -f "<pattern>"` **危险**：曾有一条清理脚本的 pattern **匹配到自己的 ssh shell** 把自己杀了 → 改为扫 `/proc/*/cwd` 精确匹配 + 显式 PID kill；
- 跑完 `rm -rf` 测试目录，并**核对生产进程未被影响**（例如核对配置文件 mtime 未变、`systemctl is-active` 仍为 active）；
- **"内核不支持"这个结论必须由内核原文支撑**，不能由"我的配置没通过"推出（`research/empirical/README.md:144`）。

### 9.2 真内核版本（一切版本结论的锚点）

| 内核 | 版本 | 二进制 | 校验器 |
|---|---|---|---|
| Xray | **26.3.27**（d2758a0, go1.26.1, linux/amd64） | `/usr/local/bin/xray` | `xray -test -config` |
| mihomo | **Mihomo Meta v1.19.32**（go1.26.8, with_gvisor） | `/root/catmi/mihomo/mihomo` | `mihomo -t -f ... -d ...` |
| sing-box | **1.14.2**（af6e64c, with_utls/with_quic/...） | `/root/catmi/sing-box/sing-box` | `sing-box check -c ... -D ...` |

来源：`research/empirical/cross-kernel-matrix.md:14-18`、`research/empirical/probe-results.json` → `kernels`。
**升级任何一个内核 = 现有全部 `RUNTIME_TEST` 证据的 `target.version` 就对不上了**，必须重跑探针（`tools/probe/probe.py`），并按 `docs/evidence-model.md` R2 **不要**把新版本的结论外推到旧版本。

### 9.3 token / 凭据纪律

仓库里**没有**任何凭据文件（`.gitignore` + 25 个 commit 里没有）。历史实践要求：

- **一次性 askpass**：需要密码/密钥时用一次性的 askpass 辅助程序，不把凭据写进任何脚本或环境文件；
- **用完 `shred`**：临时凭据文件用 `shred` 删除（不是 `rm`）；
- **不落文件**：凭据不写进仓库、不写进 `~/.*rc`、不写进日志；
- 探针脚本本身**不需要**任何凭据（全部走 `127.0.0.1` 回环）。

---

## 10. 接入进度

### 10.1 X 客户端：✅ 已接入

| 项 | 内容 |
|---|---|
| 仓库 / 提交 | `xray--core`（`Client/`）· **`1366804`** —— `feat(客户端): 接入 proxy-node-compat（内核能力判定收口到兼容层）+ 双跑对比 + CC 实测` |
| 报告 | `research/integration/x-client-integration.md`（275 行，**接入必读**） |
| 方案 | **vendored + 适配层 + 双跑保险丝 + 一条环境变量回滚** |
| └ vendored | `Client/lib/proxy_node_compat/`（含 `data/rules.json`，实测与主仓库一致：**67 规则 / 26 证据**），零第三方依赖；打包前置校验会检查 vendored 依赖完整性（少文件/规则空 → 拒绝出包） |
| └ 适配层 | `Client/lib/compat2.py`（36 KB）：节点 JSON → Node Profile → `check_node()` → 映射回**与旧实现逐字节兼容的 UI 形状**（多一个 `kernel` 段带 compat 全量结果），**6 个调用点一行都不用改** |
| └ 双跑保险丝 | 机械合并：① compat 判 UNKNOWN **且没有任何确定结论** → 退回旧判定；② 其余取**更差者**（**只许收紧，不许放宽**），出现"新比旧宽"会被挡下并记进 `downgrades` |
| └ 回滚 | `XBD_COMPAT_ENGINE=legacy`（不改代码、不改文件；适配层任何异常也自动落回旧判定） |
| 版本真探测 | `<XBD_PREFIX>/bin/xray version` → `26.3.27`；探测不到就留空 → compat 判 UNKNOWN → 回退旧判定（**不写死、不猜**） |
| 验收数字 | 语料 **60 条**（本地 53 + 生产 7）：**`relaxed: 0`**、`dialer_bug: 0`、收紧 40 条、回退旧判定 0 条；`want-bd` 7 个真实节点 **7/7 SAME**；CC `interactive-test.sh client --read-only` **55 项全过**；`tools/check_libs.sh` **576 通过 / 0 失败** |
| 接入后立刻抓到的真问题 | ① **XHTTP × mux.cool 运行期必失败**（客户端默认给每个出站开 mux）——兼容层判出来、客户端旧判定完全不知道；② **hysteria2 的"假 UNSUPPORTED"**（旧规则把 mihomo/sing-box 形状的用例当三家探针，从没试过 Xray 自己的 `protocol:"hysteria"`+`version:2` 形状）→ **改数据修掉**，引擎/模型/解析器一行未动 |
| 顺带挖出的客户端 P0 | `genconfig.py` 把 `"ech": true`（bool）写成 `echConfigList` → **内核拒绝整份配置**（已修）；`node.py` 的 trojan 解析器丢 `pbk`（**未修**，见 §8.6 #13） |

### 10.2 M 客户端 / SB 客户端：❌ 尚未接入

方案见 `docs/phase4-report.md:86-93`（要点；**该文件的"未接入"表述对 X 已过时**）：

- **M（`mihomo--core/src`）**：M 的节点来自订阅（内核自己解析），接入点在**导入前** —— 把订阅里每条链接先过 compat，`UNSUPPORTED`/`UNKNOWN` 的移入"不兼容"分组并保留原文；mihomo 配置里只放 `SUPPORTED*` 的节点。
- **SB（`sing-box-core/src`）**：`conf/outbound_uri.py` 已有明确报错（"本面板支持 tcp/ws/grpc/http/httpupgrade"）—— 把它的**判断逻辑**替换为 compat 调用，报错文案由 `reason_code` 生成，保持"说了缺什么"的既有优点。

### 10.3 接入新客户端时的硬性要求（**不可协商**）

出处：`docs/compatibility-evaluation.md:118-137`（判定必须发生一次）、`docs/00-design-principles.md:155-165`（P10 · 接入必须简单）、`research/integration/x-client-integration.md` §2。

1. **判定只发生一次**：客户端**不许**自己再实现一份能力判断。旧判定要么删、要么像 X 客户端那样**保留为 `legacy` 通道 + 机械取更差者**（且必须能一键回滚）。
   > 反面教材：v2rayN 把同一个判断写在 **3 处**，其中一处**永久不可达、无人发现**；sing-box-subscribe 把同一个"不支持"演化出**四种结局**（跳过 / 坏配置 / 崩溃 / **降级直连** —— 用户以为在走代理、实际裸奔）。（`docs/06-oss-landscape.md:196-208`）
2. **不许静默丢字段**：客户端没消费的键必须落进 `extensions[]`（禁止"删掉字段然后说支持"）。
3. **`extensions` / `raw_uri` 必须随结果返回**：客户端即使把节点判成 `UNSUPPORTED`，也**必须能原样保存它**，等将来换内核再用（`docs/compatibility-evaluation.md:66-67`）。
4. 客户端只负责声明 `(kernel, distribution, version, build_tags, platform, runtime_options)` 并消费结果；**不改写节点、不自行推断、不自动换 transport**。
5. **版本要真探测**（像 X 客户端那样读二进制自报），探测不到就留空让它判 UNKNOWN —— **不许写死**。
6. 性能：`Registry` 要缓存（逐节点调用时不缓存会每个节点重载 62 KB 规则）。

---

## 11. 给接手者的第一条建议任务清单

按优先级排，5 条以内。**建议先做 1 和 2（都是纯数据、当天可完成、立刻消除一个已知误报），再动 3。**

| # | 任务 | 一句话理由 |
|---|---|---|
| **1** | **修 `xray.combo.flow_without_tls` 的误报**（§8.1）：给 selector 加 `none_of_features` 并改这条规则的数据；先补一条测试钉住"reality+vision 不再报损失" | 这是当前**唯一的"假会丢能力"误报**，且它误报的对象正是生产上在跑、CC 实测 204 的节点 —— 用户会因此怀疑整套判定。 |
| **2** | **补 vmess 的 `uri_rules`**（§8.2：`ws` 与 `tls` 两条，纯数据）**并把 6 个 `.pyc` 从版本控制里摘掉**（§8.5，一条 `git rm --cached`） | 前者让占比很大的 vmess 节点不再永远 uri=UNKNOWN；后者一劳永逸消除评审噪声 —— 两件都是半小时的事。 |
| **3** | **核对 sing-box 二进制的真实版本/构建**（§8.6 #9），并据此复核 `singbox.*` 规则 | sing-box 是唯一带 126 条真机 `[test]` 的内核，但探针记录与另一份调研**自报的版本号不一致**；版本是所有结论的锚点，锚点错了整片结论要重写。 |
| **4** | **让失败模式六态真正可达**（§8.4）：把已实测的两条（Xray 畸形 `encryption` 的 **panic**、mihomo `encryption:none` 的 `silent_noop_then_runtime_fail`）写成规则 | "六态"目前只有四态在数据里可达；这两条是**已经做过实验、只差入库**的证据，性价比最高。 |
| **5** | **实现时间闸门 `evaluated_at`**（§8.6 #6） | `allowInsecure` 的结论随**系统日期**变化，现在整段 UNKNOWN；它是 `docs/kernel-capability-registry.md:154` 明确点名的机制，也是当前唯一"引擎收到的输入被浪费"的维度。 |

---

## 附录 A · 文件索引与规模（`wc -l` 实测）

```
README.md                                 91
pyproject.toml                            20
docs/00-design-principles.md             230   ← 宪法
docs/universal-node-profile.md           248
docs/kernel-capability-registry.md       262
docs/uri-representation.md               107
docs/compatibility-evaluation.md         138
docs/evidence-model.md                   104
docs/examples/README.md                  271   ← 14 案例
docs/06-oss-landscape.md                 357
docs/07-version-and-failure-model.md     269
docs/phase4-report.md                     93   ← ⚠️ 数字已过时
docs/HANDOVER.md                         本文
proxy_node_compat/model.py               277
proxy_node_compat/registry.py            223
proxy_node_compat/engine.py              403
proxy_node_compat/uri.py                 481
proxy_node_compat/cli.py                 190
proxy_node_compat/__init__.py             19
proxy_node_compat/data/rules.json         62,012 字节
tests/test_all.py                        506
tools/probe/probe.py                     358
tools/probe/loopback_matrix.py           916
tools/probe/cases.json                    37,758 字节
research/kernel-xray.md                  374   [src]=114 [doc]=51  [test]=0
research/kernel-mihomo.md                732   [src]=235 [doc]=64  [test]=0
research/kernel-singbox.md               692   [src]=135 [doc]=54  [test]=126
research/oss/proxylink.md                478
research/oss/sub-store.md                747
research/oss/subconverter-and-sublink-worker.md  779
research/oss/go-uri-parsers.md           870
research/oss/v2rayn-and-singbox-subscribe.md     694
research/oss/_notes-sublink-worker.md    600
research/empirical/README.md             158   ← 先读这份
research/empirical/cross-kernel-matrix.md        702   ← 60 用例
research/empirical/vless-encryption-mlkem.md     430
research/empirical/anyreality.md         101
research/empirical/probe-results.json    63 条结果
research/empirical/raw/cross-kernel-matrix-results.json  60 条结果
research/assessment/xray-quality.md      261
research/assessment/mihomo-singbox-quality.md    464
research/known-issues/x-deployment-investigation.md  314
research/known-issues/x-kernel-deployment.md     43
research/integration/x-client-integration.md     275   ← 接入必读
```

## 附录 B · 术语表

| 术语 | 含义 |
|---|---|
| **Node Profile** | 内核无关的节点描述（`model.py` 的 `NodeProfile`）。**不含任何内核版本字段**（不变式 I7） |
| **presence** | 字段"在不在输入里"，五态。`EXPLICIT` 与 `DEFAULTED` **必须分开**：`skip-cert-verify: false` 与"没写"在安全语义上完全不同 |
| **provenance** | 字段"从哪来"，八源。**禁止**把"推测出来的字段"和"URI 明确提供的字段"混在一起 |
| **feature** | 能力一等公民。**组合不折叠**：`vless + reality + xhttp` 是三个 feature，不是一个值 |
| **extensions** | 未知信息的**唯一合法去处**（不变式 I2）。**默认不进入任何生成物**，回写也不许自动写成 query |
| **Tier A / Tier B** | 探针两层。A = 内核自带校验器；B = 真服务端+真客户端回环。**只有 B 能抓出"校验通过但运行时静默降级"** |
| **`accepted_unverified`（`✅?`）** | 静态校验通过、但该字段内核根本不校验 → **不可信**，只有 Tier B 能定论 |
| **`silent_ignore` / `silent_drop` / `silent_noop_then_runtime_fail`** | 三类静默失败。**在最终结果里必须升级成 `SUPPORTED_WITH_LOSS`**，不能显示成 `SUPPORTED` |
| **unknown_range** | 显式记录"这段版本区间没有证据"。**留空与"未知"语义不同**：留空会被下游当成没这条规则 |
| **`limits`** | 每条证据的自陈"到底证明了什么、没证明什么"。**必填** |
| **R1 / R2 / R3** | `docs/evidence-model.md` 的三条硬规则：推断不能变事实 / 精度不得高于证据 / 未知要显式记录 |
| **唯一检查点** | 判定只在 compat 里发生一次，客户端只消费结果 |
| **RN / CC / DS** | 测试服务器 / 客户端实测机（局域网）/ **生产（禁止触碰）** |

---

## 附录 C · Phase 1 调研要点速查（`research/oss/` + `research/kernel-*`）

> 接手者不必重读 4,168 行生态调研 + 1,798 行内核清单才能开工，但**必须知道这些结论的存在** ——
> 它们是"我们为什么这么设计"的全部理由。每条都标了出处文件与行号。

### C.1 生态：九个项目，一个共同的病

`docs/06-oss-landscape.md:10-27`（项目清单）、`:30-48`（"默认行为都是静默丢失"总表）。

| 项目 | 一句话 | 结构性缺陷（我们的存在理由） |
|---|---|---|
| **Proxylink**（Go） | 生态里同赛道最近的一个：URI/Clash/Xray JSON/sing-box JSON → 统一 `ProfileItem` → 生成配置或回写 URI | **完全扁平：59 个标量字段，零嵌套、零 map、零扩展槽**（`research/oss/proxylink.md:54-56`）。会**静默丢 transport**（`default: return nil` → 节点退化成裸 TCP）；`PinSHA256 → sing-box` 无法换算时**降级为 `tls.insecure = true`（跳过全部证书校验）**，只用代码注释说明（`docs/06-oss-landscape.md:34-39`）。**没有 `*_test.go`，没有 round-trip 验证**（`proxylink.md:341-343`） |
| **subconverter**（C++） | 生态最经典的多目标生成器 | **模型里没有 VLESS**（`ProxyType` 枚举无它；全仓库 `vless` 命中 0）→ 任何 VLESS 节点落到 `Unknown` → 被 `subparser.cpp:2658` **静默丢弃**；issue #611 从 2023-06 挂到 2026-02 仍 open（`subconverter-and-sublink-worker.md:65,320,357-360`）。全文件 `continue;` **49 次**，`writeLog` 8 处**没有一处是因为节点/字段被丢**（`:177-191`）。文档里搜 `not support / limitation / known issue / lost / drop` → **0 命中**（`docs/06-oss-landscape.md:44-46`） |
| **Sub-Store**（JS） | 唯一有"无损通道"的项目 | 6 种"目标表达不了"的机制里 **5 种最终都是"节点从产物里消失，信息只进服务端日志"**（`sub-store.md:215`）；`isSupportedMihomoVersion` **实际比的是插件版本**、全项目没有内核版本维度（`docs/06-oss-landscape.md:220-222`）。⚠️ **安全问题**：`anytls/hysteria2/tuic` 三处把未知 query 参数**原样写进节点对象并进入 mihomo 配置**（实测出现 `"evilField":"1"`）→ 这就是我们的规则"未知参数进 `extensions{}`、**默认不进入任何生成物**"的来源（`docs/uri-representation.md:80-83`） |
| **sublink-worker**（JS） | 跑在 Worker/Node 的轻量转换 | 描述里说是 TypeScript，**实际 0 个 `.ts` 文件**（`src/` 49 个 `.js` + 11 个 `.jsx`，`_notes-sublink-worker.md:12-13`）。**Surge 目标静默把 Reality 降级为普通 TLS**（reality/flow/xtls/fingerprint 扫描全 false，`:319`）→ 节点看似有效却连不上。有 38 个测试文件 5,023 行，但**测试把"静默丢弃"写成了预期契约**（`:480-492`） |
| **xray-knife**（Go） | 生态里**最接近**我们的一件事 | 有"能力判断"（`removedTransport` 知道 h2 被 xray 移除、`SingboxReason(p, insecure)`），但**零内核版本维度** —— 说不出"从哪个版本移除"（`docs/06-oss-landscape.md:132-143`、`go-uri-parsers.md:129-167`） |
| **proxyparser**（Go） | 各协议 URI → **clash-meta 风格 `map[string]any`** | **"枢纽 map 反模式"最好的一手证据**：模型直接被某个内核的 schema 绑死；"零值即未设置"使 loss 报告**在语义上不可能写出**（`go-uri-parsers.md:817-827`） |
| **v2rayN**（C#） | 客户端，同一份节点在 Xray / sing-box 间切换 | **同一个判断写在 3 处，其中 1 处因归一化永久不可达**（`v2rayn-and-singbox-subscribe.md:159-171`）→ 必须**唯一检查点**。sing-box 路径**完全没引用**证书钉扎/域校验/后量子验证/`fm` 五个字段，**静默消失且零告警**（`docs/06-oss-landscape.md:198-204`） |
| **sing-box-subscribe**（Py） | 模板 + 订阅 → sing-box 配置 | 把同一个"不支持"演化出**四种结局**：跳过 / 生成坏配置 / **崩掉**（首行畸形抛 `UnboundLocalError`）/ **降级直连**（分组 0 节点时该组被填成 `Direct` —— 用户以为在走代理、实际裸奔）（`docs/06-oss-landscape.md:205-208`） |
| **LxBox / sing-box-lx** | Android 客户端，内核是 sing-box 的 **fork** | 引出本项目的架构修正：**内核不是只有"名字+版本"，还有发行版/fork**；`sing-box-lx` 带 XHTTP/AmneziaWG2/MASQUE，上游完全没有 → `unknown_distribution_policy` 默认 UNKNOWN，**fork 不得默认继承上游**（`docs/06-oss-landscape.md:88-104`、`docs/kernel-capability-registry.md:121-123`） |

**生态里没有对应物的（= 我们唯一的核心工作）**（`docs/06-oss-landscape.md:238-252`）：内核 × 发行版 × 版本维度的能力表 / 字段级 loss-warning-unknown 结构化输出与 `reason_code` / **静默降级的检测** / **round-trip 不变量校验**（所有项目都没有）/ 未知与 vendor feature 的一等公民表示。

### C.2 三家内核：必须记住的硬事实

| 内核 | 硬事实 | 出处 |
|---|---|---|
| **Xray 26.3.27** | ① `streamSettings.method` **v26.7.28 才存在** → 在 26.3.27 上是未知字段、**被静默忽略**（我们自己的 `genconfig.py` 就在写它，目前无害但是典型"未来才有意义"字段）。② `allowInsecure` 有三段：≤v26.1.23 生效 → v26.1.31–26.2.2 **立即硬报错** → v26.2.6–26.5.9 **按日期软禁用**（系统时间 < 2026-06-01 UTC 才警告+生效）→ v26.7.11+ 无条件硬报错。③ `kcpSettings.header/seed`：≤v26.1.23 生效 → v26.2.6–26.9.8 硬报错 → **v26.9.30/main 静默丢弃**。④ **内核全树不解析也不生成分享 URI**（grep `vless://\|shareLink` 命中 0）。⑤ HTTP/HTTP2/QUIC 传输 v24.12.31 起硬错误 | `research/kernel-xray.md:110,130,149,127-128,219,222,294-310`；URI 层结论见 `docs/uri-representation.md:5-6` |
| **mihomo v1.19.32** | ① **未知键永不报错**：decoder 把没匹配的键收进 `dataValKeysUnused`，只有结构体带 `remain` tag 才消费它，而 **proxy option 无一使用 `remain`，也没有 `ErrorUnused` 开关** → 拼错/不认识的字段被静默丢弃（这就是"`-t` 不代表支持"的根因）。② `network` **没有任何枚举校验**，未知值静默按 TCP。③ `xhttp` 只对 vless 生效。④ **`vless.ws-headers` 是死字段**（除声明处外全仓库引用数 = 1）—— 由"字段引用数 ≤ 1 = 死字段"这个**可机械执行**的手法发现（`docs/07-version-and-failure-model.md:197-209`）。⑤ 字段名跨协议不一致：vmess/vless 只有 `servername`，trojan/hysteria2/tuic/anytls 只有 `sni`，**写错不报错只静默失效**；trojan 结构体里根本没有 `tls` 字段。⑥ **少数真的硬校验**：`xhttp-opts.mode` 非法值在构造期就报错（`-t` 会失败），mieru.transport / snell `obfs-opts.mode` / hysteria2 `obfs` 同理 | `research/kernel-mihomo.md:474,478,484,498-501,523,560,567`；`docs/07-version-and-failure-model.md:152-181` |
| **sing-box 1.14.2** | ① **`xhttp` / `splithttp` 完全不存在（任何版本）**：v1.14.2 全量 tarball（1755 条目）grep `xhttp\|splithttp` → **0 命中**。② transport 恒为 5 个（http/ws/quic/grpc/httpupgrade）；写 `tcp`/`kcp` → `FATAL unknown transport type`。③ **JSON 严格**：未知顶层/outbound/transport/tls 字段与未知 type/inbound 值**全 FATAL** → 透传未知 URI 参数即 FATAL，**没有"静默忽略"这个中间态**。④ multiplex 只有 h2mux/smux/yamux，`mux.cool` → `FATAL unknown protocol`。⑤ **官方二进制的 gRPC 不是标准 gRPC**（`grpc.go` vs `grpc_lite.go` 两套实现，官方符号表只有 `v2raygrpclite`）→ "gRPC 校验通过"是静态层幻觉。⑥ `ech.config` **必须是 PEM**。⑦ 官网文档是 `1.15.0-dev`，**照官网写映射表会直接产 FATAL**，须以 tag 内置 docs 为准 | `research/kernel-singbox.md:53,138-143,158-162,281,355,433-439,557`；`docs/07-version-and-failure-model.md:243-251`（`:80-86` 为文档错位） |

**一句话总结**：三家内核**没有一家**会在"我不认识这个字段"时可靠地告诉用户 —— Xray 大部分情况静默忽略、mihomo 结构性地永不报错、sing-box 报错但只在自己解析配置的那一刻（而客户端可能根本没把参数传下去）。**这就是"能解析 ≠ 支持"要由兼容层来兜的根本原因。**
