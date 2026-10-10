# M 客户端（`mihomo--core/src/client.sh`）接入 `proxy-node-compat` · 实施与验收报告

> 日期：2026-10-10 ｜ 实施对象：`mi1314cat/mihomo--core` 的**客户端**（`src/client.sh` / `src/lib/*`）
> 兼容层：`proxy-node-compat` `0.1.0`（vendored，**68 规则 / 29 证据 / 13 URI 规则**，零第三方依赖）
> 提交（`refactor/v2` 与 `main` 一致）：
> ・`a3d1d4d` 接入本体 ・`5467278` 语料口径修正 ・`a4f0b82` 重新 vendor canonical + 验收台三处静默假通过修复
> CC 实测机：arm64，Mihomo Meta **v1.19.32**（与 RN 同版本），M 客户端生产运行（PID 1364829，全程 `active`）
> 原始输出：`research/integration/evidence/cc-run-m.log`（CC 全量实跑 261 行）、`evidence/m-local-dualrun.md`（本地双跑 + 回归断言）
> 对照参考：`research/integration/x-client-integration.md`（照 X 客户端已做过的那套，没有重新设计）

**一句话结论**：接进去**没有退步**，**没有多剔任何一个节点**（21 协议 × 9 传输 × 4 安全层 = 756 组合全扫描，
compat 在 mihomo 上多判出的 UNSUPPORTED = **0**）；CC 真机 23 项断言全过、假 UNSUPPORTED **0**、静默放宽 **0**。
compat 的真实增益是**把"配置看着没问题、其实能力已经没了"的静默失败讲清楚**，而这些主张都被**真机单变量实验**逐条证实
（`network: kcp` 被静默当 tcp、ws 上的 reality 被静默关掉、reality 缺指纹配置层过而拨号失败、trojan+REALITY 走链接形态必然失败）。
过程中还顺带查出**三个既有缺陷**（都不在本次改动范围内，已单列，见 §7）——其中一个会让"导入成功"变成"整组一个节点都没有"。

---

## 0. 交付物

| 位置 | 内容 |
|---|---|
| `mihomo--core/src/lib/proxy_node_compat/` | vendored 兼容层（8 个文件 + `data/rules.json`） |
| `mihomo--core/src/lib/nodecompat.py` | **适配层**：节点/链接 → NodeProfile → `check_node()` → 与旧判定机械合并 |
| `mihomo--core/src/client.sh` | 两条导入通路（`proxies:` YAML / 分享链接 URI 列表）都接上判定；判定结果落盘；回滚开关 |
| `mihomo--core/tools/nodecompat-compare.py` + `tools/compat-corpus.json` | 双跑对比台（语料 60 条：19 条真实产物形状 + 12 条真实分享链接 + 29 条合成用例） |
| `mihomo--core/tools/cc-verify-m.sh` | CC 验收台（只在 `/tmp` 做事：真订阅 / 逐节点真连通 / 单变量实验 / 回滚） |
| `mihomo--core/tests/test_nodecompat.py` | 回归断言 49 项（**不变量级**，不是快照） |
| `mihomo--core/{src/manifest.txt, src/lib/core_mgmt.sh, install.sh}` | vendored 文件的发布登记 + `fetch_repo` 的 `mkdir -p` |
| 本文件 + `evidence/` | 对照表 / 双跑差异 / CC 实测 / 多判出什么 / 有无退步 / 发现 / UNKNOWN |

---

## 1. 现状摸底：M 客户端现在怎么判"节点能不能用"

### 1.1 调用点（接入前）

| 位置 | 判什么 | 触发时机 |
|---|---|---|
| `src/client.sh:_add_from_file()`（内嵌 python） | **协议白名单**：`type` ∈ `validate.PROXY_TYPES`，不在就整条剔除 | 导入订阅 |
| 同上，`validate.strip_unknown()` | **字段白名单**：该 `type` 不认的键剔掉（内核是**静默忽略**，"不剔"就等于"配了没反应"） | 导入订阅 |
| 同上 | 缺 `name/type/server/port` → 剔除 | 导入订阅 |
| `src/lib/env.sh:m_kernel_unsupported_types()` / `m_kernel_supports()` | **运行期真探测**：候选类型塞进最小配置真跑 `mihomo -t`，让内核报 `unsupport proxy type: XXX`，按版本缓存 | 只有**服务端生成节点**用（`src/conf/all.sh:666`）；客户端导入**完全不看** |
| `src/client.sh:node_test()` | **真实延迟**（控制 API `/group/<组>/delay`） | 用户点"节点测速" |
| `src/lib/validate.py:PROXY / PROXY_TYPES` | 上面两张表的**唯一真源**（`_add_from_file` 就是 import 它，不另抄） | — |

### 1.2 UI / 日志（接入前）

```
[过滤] <type>: mihomo 核心不支持该协议, 已剔除 N 个 —— 名字1, 名字2 等 X 个
[过滤] 不是合法代理条目 (缺 name/type/server/port), 已剔除 N 个 —— …
[Info] 已剔除 N 个内核不认的字段
[OK]   已写入 <providers>/<组>.yaml (N 个节点[, 已剔除 M 个不兼容])
```
`node_list` 只有「组名 / N 个节点 / 来源」。**没有任何一行**会说"这个节点能连，但你会丢掉某项能力"。

### 1.3 对照表：旧判定每一项 ↔ compat 里对应的规则

| # | M 客户端判什么 | 判据来源 | `proxy-node-compat` 对应 | 覆盖情况 |
|---|---|---|---|---|
| 1 | `type` ∈ `PROXY_TYPES`（21 个协议） | `validate.py:PROXY` | `mihomo.protocol.{vless,vmess,trojan,shadowsocks,hysteria2,tuic,anytls}` | ✅ 7 个；其余 14 个（snell/wireguard/ssh/mieru/hysteria(v1)/shadow-tls/…）无规则 → compat 判 **UNKNOWN → 退回旧判定**，与接入前逐字一致 |
| 2 | 缺 `name/type/server/port` → 剔除 | — | 无（**不是**能力判定） | ➖ 留在旧判定（guard）。语料 `syn:malformed` 是唯一一次保险丝触发：compat 说能用、旧判定说剔除 → **挡下** |
| 3 | 内核不认的字段 → 剔除 | `validate.py:PROXY` 白名单 | 无（compat 是内核能力库，不是字段校验器） | ❌ 未覆盖，原样留在旧判定，且"取更差者"会**保留它的结论**（trojan 写 `servername` 就是靠这维挡住的） |
| 4 | 版本相关能力（xhttp/reality/ech/flow 是 v1.19.x 逐版加的） | `m_kernel_unsupported_types` 只覆盖**协议类型**，且客户端路径不用它 | `mihomo.transport.xhttp`、`mihomo.support.{xhttp,reality,ech,flow}`、`mihomo.vless.encryption`（带 `>=1.19.x` 区间 + `transition: UNKNOWN`） | 🆕 **新增维度** |
| 5 | 组合能力 | 无 | `mihomo.combo.ws_reality`、`mihomo.combo.ss_reality` | 🆕 **新增** |
| 6 | 传输语义 | 无（`network` 原样写进 provider） | `mihomo.transport.mkcp`（`silent_ignore`：mihomo 没有 mkcp 实现，未知 network **静默按 tcp**） | 🆕 **新增**，真机证实（§6.3） |
| 7 | 运行期前置条件 | 无 | `mihomo.reality.runtime_condition`（有 `reality-opts` 缺 `client-fingerprint` → 配置层查不出、拨号才失败） | 🆕 **新增**，真机证实 |
| 8 | 多路复用语义 | 无（客户端**不**默认开 mux；`smux` 由服务端按档位显式生成） | `mihomo.mux.semantics`（三方 mux 不同构 → `silent_ignore` + `SEMANTIC_MISMATCH`） | 🆕 **新增**（**与 X 客户端的关键差异**：X 那边客户端默认开 mux.cool，M 这边只有节点自带 `smux` 才触发） |
| 9 | 字段名陷阱 | 只有"剔除"这一半 | `mihomo.fieldname.sni_vs_servername`（vless/vmess 只有 `servername`；trojan/hysteria2/tuic/anytls 只有 `sni`） | ⚠️ 部分覆盖：compat 这条只有 `warnings`、**没有 `losses`**，不会事故化；真正挡住的是旧判定的字段剔除。**两者互补**，未覆盖的一半见 U2 |
| 10 | 真实连通性 | `node_test()` | **没有，也不该有**：那是"这一刻能不能连"，不是内核能力 | ➖ 原样留在客户端 |
| 11 | 分享链接通路 | P-M4 之后客户端能吃 `out/*_share-*.txt`（一行行 URI），但**只把列表原样交给内核的内置转换器**，旧判定**不逐条表态** | `parse_uri` + 全套规则（保真最高：值一字节不改），含**只对 mihomo 生效**的 `uri.trojan.reality@mihomo` | 🆕 **本次补齐**：这条以前是判定的真空地带 |
| 12 | —（旧判定完全没有的） | — | `uri.*` 表达力规则、`unknown_range` / `transition` 的"不知道就不猜" | 🆕 新增 |

**结论**：旧判定只覆盖「协议类型 + 字段名」两维；**传输语义、组合、版本区间、运行期条件四维完全空白**。
compat 补的正是这四维，而它不管的那维（字段名）由旧判定兜着 —— 这就是"零退步"的结构性来源。

---

## 2. 接入方式（最小侵入）

```
providers/<组>.yaml 的每个条目 ─┬─(条目带原始链接)─→ parse_uri(raw)   ← 保真最高（I1）
                                └─(mihomo 字段)──→ feature 映射        ← 复用 uri.py 的 TRANSPORT_MAP
                                         │
                                         ├─ 未建模的键 → extensions[]（不变式 I2, 禁止静默丢字段）
                                         └─ 原始字典整份 → raw_fields
                                                  ↓
   分享链接列表的每一行 ────────────────────→ parse_uri(raw)
                                                  ↓
              check_node(profile, Target(kernel="mihomo", version=<真探测>))   ← 唯一判定点
                                                  ↓
                   merged = 更差者(compat 判定, 旧判定)   ← 机械合并，只许收紧
                                                  ↓
                       providers/<组>.yaml（字节不变）+ nodes/<组>.compat.json（判定全量）
```

### 2.1 目标真探测（不写死、不猜）

```
$ python3 src/lib/nodecompat.py kernel
{"probe": {"version": "1.19.32", "distribution": "upstream",
           "build_tags": ["with_gvisor"], "raw": "Mihomo Meta v1.19.32 linux arm64 …",
           "probed": true}, …}
```
版本 / 发行版 / `Use tags:` 全部来自真跑 `<mihomo> -v`（**整体捕获再匹配，不用管道** —— 本项目已因 `| head` + `pipefail`
吃过 SIGPIPE 141 随机猝死）。官方二进制自称 `Mihomo Meta` → `distribution=upstream`；别的名字按 fork 处理
（compat 对 fork 一律 UNKNOWN → 退回旧判定，**不继承上游**）。探测不到 → 版本留 `None` → compat 判 UNKNOWN
（**不是"默认支持"**）→ 退回旧判定。

### 2.2 合并层只做两条策略（不含任何能力规则）

1. **compat 判 UNKNOWN 且无任何确定结论**（无 losses、无 UNSUPPORTED 层、非 hard_error）→ **退回旧判定**。
   UNKNOWN 的含义是"我们没有依据"，不是"不能用"。
2. 其余取**更差者**。出现"新比旧宽"时：
   * 旧判定要**剔除**该节点而 compat 说能用 → **挡下并保留旧判定**（记 `downgrades`，`kind=blocked`）。
   * 其他"compat 更宽"只统计不拦（记 `wider`）：两个引擎量的不是同一件事，每一条都报警 = 计数器永远红 = 等于没有门。

### 2.3 回滚（不改代码、不改文件）

```bash
MH_COMPAT_ENGINE=legacy …      # M 侧的名字
XBD_COMPAT_ENGINE=legacy …     # 与 X 客户端统一的别名
```
任一为 `legacy` → compat 完全不参与，判定 == 接入前（CC 实测：19/19 逐条一致，§6 第 10 项）。
适配层任何异常（含 vendored 包缺失）都自动落回旧判定 —— 这一点被另一路 agent 的门禁脚本无意中验证了：
它把 `src/client.sh` 的 `PYIMP` 段切出来单独跑、临时 lib 目录里只有 `validate.py`，
适配层打一行 `[WARN] 兼容判定层不可用` 后照旧导入成功（§8）。

### 2.4 判定结果随产物落盘（不许静默丢字段）

`nodes/<组>.compat.json`：`engine / target / registry / counts` + 每个节点的
`verdict, label, verdict_source, legacy, compat_status, drop, reasons, downgrades, losses, unknowns,
extensions, raw_uri, warnings, reason_codes, levels, rules_applied, evidence, diagnostics`。
`node_list` 显示一行摘要：`兼容: 支持! 19   内核 1.19.32 · 引擎 compat`。
URI 通路额外记 `source_kind: uri-list`，且每条 `raw_uri` 与原文**逐字节一致**（CC 实测 0 条不一致）。

### 2.5 发布登记（不登记 = 全新安装缺文件）

`src/manifest.txt` + `src/lib/core_mgmt.sh` 兜底清单 + `install.sh` 兜底清单都登记了 vendored 文件；
`install.sh:fetch_repo` 补 `mkdir -p "$(dirname …)"` —— 清单里第一次出现**带子目录**的条目，
少了它 `curl -o <不存在的目录>/x` 只会写失败，而错误被 `2>/dev/null` 吞掉。

---

## 3. 双跑对比（切换前必须全绿）

```bash
$ MIHOMO_BIN=<真内核> python3 tools/nodecompat-compare.py     # 语料 60 条
语料 60 条: 收紧 44 | 回退旧判定 6 | 一致 10
relaxed    : 0   <- 旧判定要剔除、合并后却能用: 必须 0
fuse_fired : 1   期望 1  ✅
字段完整   : ✅
```

语料构成：19 条 = RN 真实产物的**形状**（值已脱敏：IP→TEST-NET、域名→example.com、UUID→占位符）、
12 条 = RN 真实分享链接、29 条 = 覆盖 compat 每条 mihomo 规则的合成用例。

* `relaxed = 0`：旧判定明确"不能用"的节点，合并后**从来没有**变成"能用"。
* `fuse_fired = 1`（期望 1）：唯一一次是 `syn:malformed`（缺 `server`）—— 能力库当然看不出问题，
  而客户端必须剔除它；保险丝按设计挡回旧判定。断言写成"触发次数 == 应该触发的次数"，不是"越小越好"。
* `wider = 7`（信息性）：全是 `trojan 写成 servername` 那类 —— 旧判定的字段剔除维度 compat 按设计不管。
* **全协议扫描**（21 协议 × 9 传输 × 4 安全层 = 756 组合，含 quic 变体共 840 次判定）：
  `SUPPORTED_WITH_LOSS 672 / UNKNOWN 168 / UNSUPPORTED 0` ——
  **compat 在 mihomo 上多判出的 UNSUPPORTED 是 0**。这条对"接进去会不会误伤"是最直接的答复。

---

## 4. 新方案比旧的多判出了什么

### 4.1 `network: kcp` 在 mihomo 上是静默降级

* 旧判定：`network` 只是原样写进 provider，**不看**。
* compat：`mihomo.transport.mkcp` → `SUPPORTED_WITH_LOSS` / `silent_ignore`：
  「mihomo 无 mkcp 实现；`network` 值不被校验 → 静默按 tcp 处理」。
* 真机证据（§6.3）：RN 真实的 `tcp + reality` 节点**只改一项** `network: kcp` → **仍然 204**；
  `network: totally-bogus-net` → **204**。用户以为在用 mKCP，实际是裸 TCP。

### 4.2 ws 上的 reality 被静默关掉

* compat：`mihomo.combo.ws_reality` → `SUPPORTED_WITH_LOSS` / `silent_ignore` / **impact=SECURITY**。
* 真机证据（§6.3）：同一真实 reality 服务端，只把 `network` 改成 `ws` → **502**（基线 204）。
  安全属性无声丢失，客户端以前一无所知。

### 4.3 reality 缺 `client-fingerprint`：配置层过、拨号才失败

* compat：`mihomo.reality.runtime_condition`。节点自带 `client-fingerprint` 时记一条
  `RUNTIME_CONDITION_FROM_PROFILE` 警告；不带 → `SUPPORTED_WITH_LOSS` / `CONNECTIVITY`。
* 真机证据（§6.3）：删掉真实 reality 节点的 `client-fingerprint` → `mihomo -t` **通过**，实际拨号 **502**。

### 4.4 【只对 mihomo 生效】同一节点，走链接 vs 走 YAML 是两个结果

canonical 在本次接入期间补了 `uri.trojan.reality@mihomo`：mihomo 的 **trojan 分享链接解析器不读 `pbk`/`sid`**，
所以 `trojan://…security=reality…` 导入后只按裸 TLS 拨号，必然连不通；而同一节点的 YAML 形态（显式 `reality-opts`）正常。
这条**恰好落在客户端新开的分享链接通路上**，所以专门做了单变量真机对照（§6.4）：

```
配对: 链接原文 107.173.154.178:56676  ←→  YAML 'sub-mTrojan01-REALITY' 107.173.154.178:25672
形态=uri   config_ok=True  真实HTTP=400
形态=yaml  config_ok=True  真实HTTP=204
```
**同一台服务器、同一个活端口、只差"导入形态" → 400 vs 204。compat 的规则被真机证实。**

### 4.5 分享链接通路以前是判定的真空地带

客户端 P-M4 之后能吃 `out/*_share-*.txt`，但那条路**只把列表原样丢给内核转换器**，旧判定一句都不判。
本次接到 compat 的 `parse_uri`：CC 实测 12 条真实链接全部被判到，`raw_uri` 与 RN 原文**逐字节一致**。
合成用例里，一条 `vless + reality + type=kcp` 的链接直接被判出 mkcp 静默降级。

---

## 5. 假 UNSUPPORTED / 退步 —— 逐条回答

| 问题 | 结论 | 证据 |
|---|---|---|
| 假 UNSUPPORTED（compat 判死但真能连） | **0 条** | CC 逐节点实测：31 个可测节点（19 YAML + 12 URI）矩阵里 `假 UNSUPPORTED 0`；756 组合扫描 compat 多判 UNSUPPORTED = 0 |
| 静默放宽（旧说不能用、新说能用） | **0 条** | 语料 `relaxed: 0`；CC 矩阵 `静默放宽 0`；16 种状态组合的穷举断言 |
| 多剔节点 | **0 个** | `drop` 仅在合并判定为 UNSUPPORTED 时为真，而 compat 在 mihomo 上不产生 UNSUPPORTED |
| 导入产物内容变化 | **无**：provider YAML 与接入前**逐字节相同**（只差一行时间戳注释） | 本地实测：接入前/后各跑同一条真实订阅，`diff` 除时间戳外为空 |
| `validate.py` 严格校验 / 内核 `-t` | 不受影响 | CC：`严格字段校验通过`、`gen_config + 内核 -t 全通过` |
| UI 文案变化（非功能退步） | 真实 RN 节点 `支持` → `支持!` | 两个来源：`mihomo.fieldname.sni_vs_servername` 的 `FIELD_NAME_TRAP` 警告，以及 reality 节点的 `RUNTIME_CONDITION_FROM_PROFILE` 警告。**都是"确定会丢能力/必须注意"的真结论**，`.compat.json` 能解释每条来源 |
| 误报面 | 见 U2：`FIELD_NAME_TRAP` 对**所有** TLS 节点一律触发，不区分"键写对了没有" | compat 规则自身的表达力限制（选择器没有"且键名写错"），不是接入引入的；本次纪律是不改规则语义，故只记录 |
| compat 收紧的 31 条是否"有用" | 31 条里 12 条实测连不通；**只有 1 条（trojan+REALITY 走链接形态）compat 报出的损失就是它的失败原因**（§6.4 单变量对照证实），其余 11 条的失败原因是 RN 分享产物端口过期（§7 F2），与 compat 报的"字段名陷阱"无关 | §6.2/§6.4；如实区分，不把无关失败算成 compat 的功劳 |

**真实 RN 节点上 compat 到底多判了什么**（CC 实测，19 YAML + 12 URI = 31）：

| 组 | 条数 | 旧判定 | compat | 合并 | 真实连通 |
|---|---|---|---|---|---|
| 普通 TLS/QUIC 节点（anytls / hysteria2 / tuic / trojan-TLS / vless-ws / cdn-ws / cdn-grpc） | 26 | SUPPORTED | SUPPORTED_WITH_WARNING | 支持! | YAML 通路 17/19 → 204；URI 通路 2/12 → 204（其余 10 条是 F2 端口过期） |
| reality 系（vless×4 / trojan×3，tcp+gRPC+xHTTP） | 7 | SUPPORTED | SUPPORTED_WITH_WARNING（运行期条件留痕） | 支持! | 同上 |
| CDN 节点带空 `username`（trojan/vless ×4） | 4 | **SUPPORTED_WITH_LOSS**（旧判定剔字段） | SUPPORTED_WITH_WARNING | 支持!（**保留旧判定的损失**） | 204 |
| trojan+REALITY 走**分享链接**形态 | 1 | SUPPORTED | **SUPPORTED_WITH_LOSS**（uri 层：reality 必然丢失） | 支持! | **400**（§6.4 已证实原因） |
| **被剔除的节点** | **0** | — | — | — | — |

---

## 6. CC 实测（命令 + 输出）

全部在 `/tmp` 内完成；**没有写任何生产路径**、**没有重启任何生产服务**；CC 生产 `mihomo-client` 全程 `active`、
PID 1364829 未变；RN 侧只在 `/tmp` 起过一个**只监听 127.0.0.1** 的临时订阅服务，经 SSH 回环隧道给 CC 用
（**不在 RN 上开任何公网可达的新端口**），跑完已 kill + `rm -rf`（两侧均已核验干净）。
原始输出：`evidence/cc-run-m.log`。

**结果：`23 通过 / 0 失败 / 1 项既有缺陷发现`，退出码 0。**

| # | 项 | 做法 | 结果 |
|---|---|---|---|
| 1 | 环境与真探测 | `mihomo -v` + `nodecompat.py kernel` | `1.19.32 / upstream / with_gvisor`；临时端口动态选，并**显式挡住**"撞上生产客户端端口"（撞了就等于拿生产实例当被测对象） |
| 2 | **RN 真实订阅** | 用**仓库当前**的 `build_sub.py --conf-dir …`（RN 部署的是旧版，会把 19 个活节点全判成陈旧产物）生成到 RN `/tmp`，回环隧道拉到 CC | **19 个节点**：`anytls 3 / hysteria2 2 / vless 8 / trojan 5 / tuic 1` |
| 3 | M 客户端导入（HTTP 通路） | `node_add` → `…/sub_all.yaml` | `[OK] 已写入 … (19 个节点)`；`[兼容] 能力判定比旧判定更严 15/19 个`；判定报告落盘 |
| 4 | **分享链接通路** | `node_add` → `…/uris.txt`（RN 真实 `*_share-*.txt` 12 条） | 导入成功；`raw_uri` 缺失 0、与原文不一致 0（**I1 成立**） |
| 5 | 分享链接通路（修正版） | 同一批链接只去掉 `&obfs=none` → `…/uris-fixed.txt` | 12/12 被内核加载，用于真正测出逐节点连通性 |
| 6 | **逐节点真实连通性** | 独立内核实例（临时端口 + 临时 `-d`）→ 控制 API 把 **PROXY → 该订阅组 → 节点** 整条链切过去并**读回校验** → `curl -x` `generate_204` → 记 HTTP 码 / 耗时 / 出口 IP | YAML 通路：**17/19 → 204**，2 个 CDN-gRPC → 502；URI 通路（修正版）：2/12 → 204（原因见 §7 F2） |
| 7 | 假 UNSUPPORTED / 退步 | 三列对照聚合 | **收紧 31 \| 假 UNSUPPORTED 0 \| 静默放宽 0 \| 选择失效 0** |
| 8 | **compat 主张的单变量实验** | 从真实 reality 节点派生 5 个变体（只改一个变量），各自独立起内核 | 见 §6.3 |
| 9 | **trojan+REALITY 形态对照** | 按节点名配对（RN 的链接产物与 YAML 产物不是同一批次），把链接改写到对端的活端口 | 见 §6.4 |
| 10 | 一键回滚 | `MH_COMPAT_ENGINE=legacy` 重跑导入 | `判定引擎: legacy`；19 个节点判定与旧判定**不一致的 0 个** |
| 11 | 原有功能 | `validate.py --conf`、`node_list`、`node_test`、内核日志 | 严格校验通过；列表三行（19 + 12 + 12）都带兼容摘要；内核日志 3 条 error/fatal **全部是启动时下载 UI（github.com 不可达）**，与节点无关 |

### 6.1 逐节点矩阵（节选，完整见 evidence）

```
── matrix1.tsv（19 个节点, YAML 通路）──
节点                          旧判定                 compat               合并        真实     选择   出口 IP
🇺🇸 mAnyTLS02-TLS            SUPPORTED            SUPPORTED_WITH_WARNING SUPPORTED_WITH_WARNING ✅ 204  OK  104.28.201.80
🇺🇸 mVLESS01-REALITY         SUPPORTED            SUPPORTED_WITH_WARNING SUPPORTED_WITH_WARNING ✅ 204  OK  104.28.201.80
🇺🇸 mTrojan05-CDN-gRPC       SUPPORTED_WITH_LOSS  SUPPORTED_WITH_WARNING SUPPORTED_WITH_LOSS  ✗ 502  OK  -
🇺🇸 mVLESS05-CDN-gRPC        SUPPORTED_WITH_LOSS  SUPPORTED_WITH_WARNING SUPPORTED_WITH_LOSS  ✗ 502  OK  -
…（17/19 → 204）
── matrix2.tsv（12 个节点, 分享链接通路-修正版）──
🇺🇸 AnyTLS-02                SUPPORTED            SUPPORTED_WITH_WARNING SUPPORTED_WITH_WARNING ✅ 204  OK  104.28.201.80
🇺🇸 AnyTLS-03                SUPPORTED            SUPPORTED_WITH_WARNING SUPPORTED_WITH_WARNING ✅ 204  OK  104.28.201.80
🇺🇸 mTrojan01-REALITY        SUPPORTED            SUPPORTED_WITH_LOSS    SUPPORTED_WITH_LOSS    ✗ 502  OK  -
…（其余 9 条 502；原因见 §7 F2 —— RN 分享产物端口过期）
```

> ⚠ 这张矩阵是被**三次自我纠错**换来的，过程本身值得记下来（三处都是"看起来全绿"的假通过）：
> ① 选节点不读回 → 31 行"全都 204"，实际走的一直是默认选中的那个节点；
> ② 出网链是 `PROXY → <订阅组> → 节点`，只设叶子组不算数 —— `PROXY` 默认停在 `AUTO`（跨全部节点的 url-test），流量根本不经过叶子组；
> ③ 判定报告里的名字是**导入那一刻**的，`node_add` 之后会给组内节点加 `<订阅名>-` 前缀，靠"按名字猜组"在同名节点存在于两个 provider 时会选错组。
> 现在：两段都设 + 都读回；组名取自 `conf/config.yaml` 的 `use:`、节点名取自 `providers/<name>.yaml` 本体（精确而非猜测）；
> 选择失败会让本节**判失败**而不是"看着挺好"。

### 6.2 假 UNSUPPORTED / 退步 判定（原始输出）

```
收紧 31 | 其中真实连不通(compat 判对) 12 | 假 UNSUPPORTED 0 | 静默放宽 0
⚠ 两边都判可用但实测连不通 3 个（既有问题, 与本次接入无关, 逐个列出）:
  - 🇺🇸 mTrojan05-CDN-gRPC（HTTP 502）
  - 🇺🇸 mVLESS05-CDN-gRPC（HTTP 502）
  - 🇺🇸 mTrojan01-REALITY（HTTP 502）   ← 这一条 compat **报了**准确的损失（§6.4），
                                          但判的是"支持!"而非"不支持", 所以它仍被保留、仍被使用
```
> 读法要说清: `SUPPORTED_WITH_LOSS` **不是**"判死" —— 节点照旧导入、照旧可用，只是带一条损失说明。
> 所以上面第三行既出现在"compat 判对"里，也出现在"两边都判可用"里，两者不矛盾。

### 6.3 compat 三条 mihomo 主张的真机验证（原始输出）

```
{"case": "ctrl-baseline",          "config_ok": true, "real_http": "204"}
{"case": "net-kcp",                "config_ok": true, "real_http": "204"}
{"case": "net-bogus",              "config_ok": true, "real_http": "204"}
{"case": "ws-plus-reality",        "config_ok": true, "real_http": "502"}
{"case": "reality-no-fingerprint", "config_ok": true, "real_http": "502"}
```

| 变体 | 只改了什么 | compat 说什么 | 真机 | 判定 |
|---|---|---|---|---|
| `ctrl-baseline` | —（真实 reality 节点原样） | SUPPORTED | **204** | 基线可用 |
| `net-kcp` | `network: kcp` + `mkcp-opts` | `SUPPORTED_WITH_LOSS`：无 mkcp 实现，**静默按 tcp** | **204** | ✅ 判对：`network` 确实被忽略 |
| `net-bogus` | `network: totally-bogus-net` | 同上 | **204** | ✅ 判对 |
| `ws-plus-reality` | `network: ws` + `ws-opts` | `SUPPORTED_WITH_LOSS`（**SECURITY**）：ws 分支不含 Reality | **502** | ✅ 判对：reality 真没生效 |
| `reality-no-fingerprint` | 删掉 `client-fingerprint` | `SUPPORTED_WITH_LOSS`（**CONNECTIVITY**） | **502**（`-t` 仍通过） | ✅ 判对 |

### 6.4 trojan+REALITY 形态对照（原始输出）

```
配对: 链接原文 107.173.154.178:56676  ←→  YAML '🇺🇸 sub-mTrojan01-REALITY' 107.173.154.178:25672 (reality-opts=True)
⚠ 两者端口不同 —— RN 的 out/*_share-*.txt 与 out/*_client-*.yaml 不是同一批次（P-M3 那类产物过期）;
  下面把链接改写到对端的活端口, 让变量只剩"导入形态"
形态=uri   config_ok=True  真实HTTP=400  日志出现 REALITY 行=1
形态=yaml  config_ok=True  真实HTTP=204  日志出现 REALITY 行=0
```

### 6.5 本地台（可离线复现）

| # | 项 | 结果 |
|---|---|---|
| 1 | `python3 tests/test_nodecompat.py` | **49 通过 / 0 失败** |
| 2 | `python3 tools/nodecompat-compare.py` | relaxed 0 / fuse 1==1 / 字段完整 ✅ |
| 3 | `bash tools/check_all.sh` | **全部 19 项通过** |
| 4 | provider 产物与接入前对比 | 除时间戳注释外**逐字节相同** |

---

## 7. 顺带查出的既有缺陷（都不在本次改动范围内）

> 三项都已复现、都有原始输出；**没有**去改它们（`src/share/*` 是另一路 agent 的改动面，且边界明确：
> 只改 `mihomo--core` 与 compat 的报告目录）。列在这里是为了让它们被看见，而不是被静默。

| # | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| **F1** | **`hysteria2://…&obfs=none` 让 mihomo 的 file-provider 整批失败** | 隔离复现（同一份 12 条链接）：原样 → 组内 **0** 个节点 + 内核 `initial proxy provider u error: proxy 3 error: missing obfs password`；去掉全部 `&obfs=none` → **12**；改成 `obfs=salamander&obfs-password=x` → **12**；只放那一行 → 0 | 客户端打印 `[OK] 已写入 12 个节点`、`mihomo -t` 也报 `test is successful`（**配置测试不加载 provider**），而内核**一个节点都没加载**、组里只剩一个 `COMPATIBLE` 占位。用户看到"导入成功" + 一个空组，没有任何线索。这是 M 客户端 P-M4（吃分享链接）与 RN 分享产物（`hysteria2_share-*.txt` 带 `obfs=none`）交叉出来的问题 |
| **F2** | **RN 的 `out/*_share-*.txt` 与 `out/*_client-*.yaml` 不是同一批次** | §6.4：同名节点 `mTrojan01-REALITY`，链接写 `:56676`、YAML 写 `:25672`；RN 实际监听的是 `:25672` | 分享链接大批指向已失效端口 → URI 通路 12 条里 10 条 502。仓库里已有修复（"链接产物端口与监听不一致"那条），**RN 上部署的还是旧版**。这也是为什么本报告**不拿 URI 通路的 502 去给节点定罪**，而用 §6.4 的受控对照判断"导入形态"的影响 |
| **F3** | **2 个 CDN-gRPC 节点实测 502** | `mTrojan05-CDN-gRPC` / `mVLESS05-CDN-gRPC`（YAML 通路） | 两个引擎都判"可用"，实测连不通 → 属节点新鲜度/环境问题（与接入无关），已单列。CDN 前端节点的这类漂移与 X 客户端报告里的 P2 同类 |
| — | （**不是**缺陷，是 compat 的价值）trojan+REALITY 走链接形态必然失败 | §6.4 | 对 M 客户端是**新暴露的风险**：分享链接通路导入 trojan+REALITY 会得到一个连不通的节点。现在它至少被判成 `支持!` 并在 `.compat.json` 里写明"reality 拿不到公钥/shortId → 只按裸 TLS 拨号 → 必然连不通"，而不是静默地"看起来能用" |

---

## 8. 跨 agent 冲突收口（单列，便于对方核对）

另一路 agent 同时在改 `src/share/*` 与 `tools/*`。我**没有**动 `src/share/*`，只做了一处最小收口：

| 项 | 内容 |
|---|---|
| 文件 / 行 | `tools/check_diagonal.sh:135`（"对角线(分享→客户端)"闸门的脚本，对方为 `check_all.sh` 新增的那一项） |
| 原来是什么 | `ok "客户端导入成功: $(grep -o '([0-9]* 个节点[^)]*)' "$CLI/imp.log" \| head -1)"` |
| 为什么红 | 该脚本开头是 `set -euo pipefail`；`\| head -1` 让上游 `grep` 吃 **SIGPIPE(141)** → 上游被判失败 → 随机猝死/判断反（正是既有闸门 `check_pipe_early.sh` 要挡的那一类） |
| 改成什么 | `… \| awk 'NR==1'`（awk 读完输入才结束）；**只换读取器**，断言内容、输出格式、逻辑一行未动，并加了两行说明 |
| 结果 | `bash tools/check_all.sh` → **全部 19 项通过**（§6.5 第 3 行） |
| 备注 | 该行修改已被对方在后续提交里一并提交（工作树是同一个），`main` 上已是修好的版本 |

其他交叉点（均未动对方文件）：
* 对方的 `src/share/link_check.py`、`tools/check_diagonal.sh`、`tools/check_share_products.sh` 曾先后让
  `清单漂移` / `发布脱敏` / `管道早退` 变红，均已由其自行修好；我只处理了上面那一行。
* 对方的 P-M4 让客户端能吃分享链接列表，**恰好把 compat 的 `parse_uri` 通路变成真实通路** —— 本次顺势补齐（§4.5）；
  两条改动落在同一个 heredoc 里，我按"URI 分支也要判定"的方式接，没有回退他的实现。
* 对方的 `check_diagonal.sh` 会从 `src/client.sh` 里**切出 `PYIMP` 段**当独立脚本跑（只传 3 个参数、临时 lib 目录只有
  `validate.py`）。适配层对此**优雅降级**：`import nodecompat` 失败 → 一行 `[WARN]` → `_nc = None` → 走旧路径 → 导入照常成功。
  该闸门在我改完后仍然通过。
* vendored 快照与 canonical 的对齐：接入期间 canonical 前进了（新增 `uri.trojan.reality@mihomo` 与 `encryption=none` 哨兵修复），
  `a4f0b82` 已重新 vendor 到 **68 规则 / 29 证据 / 13 URI 规则**，并逐一比对确认与 canonical **逐字节一致**
  （唯一差别是发布脱敏要求的那个 `<CDN_IP>` 占位）。

---

## 9. UNKNOWN（没证据就不猜）

| # | 事项 | 为什么没结论 |
|---|---|---|
| U1 | **vmess** 的真机连通性 | RN 当前节点集里没有 vmess（config.d 只有 anytls/hysteria2/vless/trojan/tuic）。vmess 只在合成语料里被判定（协议规则 SUPPORTED；走 `parse_uri` 时 `raw_uri` 保留）。要补需在 RN 新增节点，超出本次边界 |
| U2 | `FIELD_NAME_TRAP` 的误报面 | `mihomo.fieldname.sni_vs_servername` 的选择器只有 `standard:tls`，**没有**"且键名写错"这个条件，所以对每个 TLS 节点都触发（表现为所有节点 `支持 → 支持!`）。收窄它要改 compat 的规则数据，而本次纪律是"兼容层已完成、只做接入"，故只记录 |
| U3 | `mihomo.support.{xhttp,reality,ech,flow}` 在 `<1.19.32` 的实际行为 | compat 只对 `>= 1.19.32` 有证据，更低版本显式 `transition: UNKNOWN`；CC/RN 都是 1.19.32，无法实测旧版 |
| U4 | `smux` 语义损失的真实后果 | RN 当前没有带 `smux` 的节点产物（客户端也不默认开 mux），只有 compat 的 `SEMANTIC_MISMATCH` 结论与既有 `e-mux-not-isomorphic` 证据；本次未构造真机回环 |
| U5 | `network: h2` 在 mihomo vless 上的行为 | compat 未收录该组合（`standard:transport.http_h2` 没有 mihomo 规则）→ 判 SUPPORTED，与旧判定一致；但从源码看 vless 侧没有 h2 实现，**很可能也是静默按 tcp**。属规则库覆盖缺口，本次未改规则、未实测 |
| U6 | `ss + reality-opts` 的真实后果 | 需在 RN 挂一个 ss listener 才能端到端验；compat 的 `mihomo.combo.ss_reality` 只有源码证据 |
| U7 | 非官方 fork 的 mihomo 构建 | 只按 `mihomo -v` 首词判断 `distribution`，未实测 fork 二进制；compat 对 fork 一律 UNKNOWN → 退回旧判定（设计行为） |
| U8 | URI 通路 10 条 502 的**逐条**归因 | 已确证 RN 分享产物端口过期（F2），但没有逐条核对"该端口当年是否真的对应那个 listener" —— 那份旧产物已无法与当时的监听状态对照 |
| U9 | 生产订阅的修复效果 | RN 上部署的 `build_sub.py` 仍是旧版（旗帜比较 bug），本次验收用**仓库当前版本**在 RN `/tmp` 里跑；RN 何时更新不在本次范围 |
| U10 | 内核日志里 3 条 `error/fatal` | 全部是启动时下载 UI（`github.com/MetaCubeX/metacubexd` 不可达），与节点无关；属 CC 出网环境限制，未进一步归因 |

---

## 10. 复现方式

```bash
# 1. 本地回归断言（无需内核二进制，版本由桩提供）
cd mihomo--core && python3 tests/test_nodecompat.py            # 49 项

# 2. 双跑对比台（切换前必须全绿）
MIHOMO_BIN=/path/to/mihomo python3 tools/nodecompat-compare.py # relaxed 0 / fuse == 期望

# 3. 适配层自检 / 单节点判定
python3 src/lib/nodecompat.py kernel                            # 真探测到的 Target
python3 src/lib/nodecompat.py selftest                          # 合并层不变量
python3 src/lib/nodecompat.py compare <节点.yaml|json>           # 旧 vs compat vs 合并

# 4. 门禁
bash tools/check_all.sh                                         # 全部 19 项

# 5. CC 真机验收（先把 src/ 与 tools/ 放到 CC 的 /tmp）
#    自备 rn/CC 的 ssh 别名；脚本只用回环隧道、只写 /tmp、跑完自动清理
SRC=/tmp/mvm/src MIHOMO=/root/catmi/mihomo-client/mihomo bash /tmp/cc-verify-m.sh   # 23 项 + 1 项发现

# 6. 一键回滚（不改代码、不改文件）
MH_COMPAT_ENGINE=legacy bash src/client.sh
```
