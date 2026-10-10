# X 客户端（`xray--core/Client`）接入 `proxy-node-compat` · 实施与验收报告

> 日期：2026-10-10 ｜ 实施对象：`mi1314cat/xray--core` 的 `Client/`
> 兼容层版本：`proxy-node-compat` `0.1.0`（vendored，`rules.json` 67 规则 / 26 证据）
> CC 实测机：`192.168.1.178`（armbian / arm64，Xray **26.3.27** d2758a0，客户端 v2.8.3）
> 原始输出：`research/integration/evidence/cc-run.log`（CC 全量实跑）、`evidence/dualrun-local.md`（本地双跑）

**一句话结论**：接进去有用，而且**立刻抓到两个真问题**（XHTTP×mux.cool 运行期必失败；旧判定里 hysteria2 的假 UNSUPPORTED），
过程中还顺手挖出两个客户端自身的 P0（`genconfig` 把 `ech: true` 写成 `echConfigList` 让整份配置起不来；`node.py` 的 trojan 解析器丢 `pbk`）。
**没有退步**：合并层机械保证"新判定只许收紧、不许放宽"，60 条语料 relaxed = 0；`want-bd`（浏览器拨号）逐节点与旧实现完全一致。

---

## 0. 交付物

| 位置 | 内容 |
|---|---|
| `xray--core/Client/lib/proxy_node_compat/` | vendored 兼容层（含 `data/rules.json`），零第三方依赖 |
| `xray--core/Client/lib/compat2.py` | **适配层**：节点 JSON → Node Profile → 调 `check_node()` → 映射回现有 UI 形状 + 机械合并 |
| `xray--core/Client/lib/compat.py` | 旧判定**原样保留**为 `check_all_legacy()`；`check_all()` 变成分派入口（`XBD_COMPAT_ENGINE=legacy` 一键回滚）；**Browser Dialer 维度仍只在这里判定** |
| `xray--core/Client/tools/dualkernel-compare.py` + `compat-corpus.json` | 双跑对比台（语料 60 条：真实链接 + 合成用例 + 生产节点） |
| `xray--core/Client/tools/cc-verify-v2.sh` | CC 验收台（只在 `/tmp` 做事：列表 / 面板 / 双跑 / 真实链路 / XHTTP×mux 回环） |
| `xray--core/Client/tools/make-release.sh` | 打包前置校验加了 vendored 依赖完整性（少文件/规则空 → 直接拒绝出包） |
| 本文件 | 对照表 / 双跑差异 / CC 实测 / 多判出什么 / 有无退步 / UNKNOWN |

---

## 1. 现状摸底：旧 `compat.py` 判什么、谁在用、UI 长什么样

### 1.1 调用点（接入前）

| 位置 | 用法 | 判定维度 |
|---|---|---|
| `lib/actions.sh`（12 处） | `compat.py json/want-bd/render <节点>` | 两种用法都判 |
| `lib/nodelist.py:113` | `check_all()` → 列表的 `Xray` / `Browser Dialer` 两列 | 两种用法 |
| `lib/state.py:129/280` | `check_all()` → 面板数据 | 两种用法 |
| `lib/nodefilter.py:29` | `can_use_xray` → 导入时剔除不支持的协议 | Xray |
| `lib/latency.py:41`、`scripts/run-xray.sh`、`actions.sh:1383` | `want_browser_dialer()` → 决定进程带不带 `XRAY_BROWSER_DIALER` | Browser Dialer |
| `lib/web/panel.py:42/209/618/2719…` | `check_all()`；`check_xray()` 校验预设；`FP_VALUES/FP_HINT` | 两种用法 |

### 1.2 UI 形状（**接入后必须逐字节兼容的部分**）

```
{"node":…, "xray":{"overall","checks":[{item,verdict,detail}],"notes":[…]} ,
 "dialer":{"overall","checks","notes","probe_ok"},
 "tags":[…], "can_use_xray":bool, "can_use_dialer":bool, "protocol_may_dialer":bool}
overall ∈ {SUPPORTED, SUPPORTED_WITH_WARNING, UNKNOWN, NOT_SUPPORTED}
列表文案：支持 / 支持! / 未知 / 不支持（`nodelist.LABEL`）；卡片：✓ 支持 / ⚠ 支持（有注意项）/ ✗ 不支持 / ? 未知
```
`compat2.check_all()` 返回**同形状的超集**（多一个 `kernel` 段带 compat 全量结果），所以上面 6 个调用点全部不用改。

### 1.3 对照表：旧判定每一项 ↔ compat 对应规则

| # | 旧 `check_xray()` 判什么 | 判据来源 | `proxy-node-compat` 对应 | 覆盖情况 |
|---|---|---|---|---|
| 1 | 协议 ∈ {vless,vmess,trojan,shadowsocks,hysteria2,socks,http} | 源码 `proxy/` 目录 | `xray.protocol.vless/vmess/trojan/shadowsocks`；`xray.protocol.tuic.never/anytls.never`；hysteria2 见 §4.1 | ✅ 覆盖（**本次修正 hysteria2**）；**socks/http 没有规则** → 回退旧判定（U11） |
| 2 | 地址缺失 → 不支持 | — | 无（不是能力问题） | ➖ 不是能力判定，**留在旧判定**（guard） |
| 3 | 指纹白名单（未知值让**整份配置**构建失败） | 实测 `fp=not-a-real-fingerprint` → exit 23 | 无（`fp` 只作为 `standard:tls` 的参数） | ❌ 未覆盖，**留在旧判定**（关键安全网：`vless-bad-fp` 语料里旧=新=不支持） |
| 4 | 凭据完整性（uuid/password/method） | — | 无 | ❌ 未覆盖，**留在旧判定** |
| 5 | 传输 ∈ {raw,xhttp,mkcp,grpc,websocket,httpupgrade,hysteria}（先归一化别名） | 26.x 实测 | `xray.support.xhttp/transport_ws/transport_grpc/*.httpupgrade` + `xray.transport.http_h2`(KERNEL_REMOVED) + `xray.mkcp.header_seed`(KERNEL_REMOVED) | ✅ 覆盖且**更强**（带版本区间与证据；连 h2/http/quic 的"已移除"都单列规则） |
| 6 | security ∈ {none,tls,reality}（xtls 已移除） | 实测内核报错 | `xray.support.tls`、`xray.reality.*`；**xtls 无规则** | ⚠️ 部分覆盖：适配层把未收录的 security 值登记成 `unknown:security.<v>` feature（与 uri.py 处理未知 transport 的写法一致），由 compat 判 UNKNOWN → 回退旧判定 → 仍是"不支持" |
| 7 | reality 但缺 pbk → 不支持 | — | 无（auth/params 不参与判定） | ❌ 未覆盖，**留在旧判定**（正是这条抓到了 `node.py` 丢 pbk，见 §5.3） |
| 8 | **组合**：reality × 传输（只允许 raw/xhttp/grpc） | 实测 `REALITY only supports RAW, XHTTP and gRPC` | `xray.combo.reality_transports`（`constraint.allowed_transports`）+ `xray.combo.ws_reality` | ✅ 覆盖（且是三内核通用的数据驱动写法） |
| 9 | allowInsecure 提示（26.x 已移除） | 官方 issue | `xray.tls.allow_insecure`（≥26.7.11 不支持；<26.7.11 因时间闸门未实现 → **UNKNOWN**） | ⚠️ 部分覆盖：26.3.27 落 UNKNOWN → 回退旧判定（文案不变） |
| 10 | flow 只对 vless 有意义 | — | `xray.combo.flow_without_tls`、`xray.support.flow` | ⚠️ 覆盖但**过宽**（对 security=tls/reality 的 flow+tcp 节点误报损失，见 §5.2） |
| 11 | 传输别名归一化 `canon_transport()` | — | `uri.TRANSPORT_MAP` | ✅ 适配层直接复用 compat 的同一张表（不另写一份） |
| 12 | **Browser Dialer 维度**（实测探测、SNI==host==address、xhttp mode=stream-\*、IP 字面量、端口 443、传输门槛版本、flow 被丢弃…） | 源码 + 实机探测 | **没有，也不该有**：这是客户端自己的功能路径与实测结果，不是内核能力 | ➖ **原样留在 compat.py**（唯一实现，compat2 只转发） |
| 13 | ——（旧判定完全没有的能力） | — | `xray.mkcp.header_seed`、`xray.transport.http_h2`、`xray.combo.xhttp_muxcool`、`xray.mux.semantics`、`xray.vless.encryption`、`xray.ech.config_lax`、`xray.combo.ss_reality`、`uri.*` 表达力规则、`unknown_range`/`transition` | 🆕 **新增判定**（§4） |

**结论**：旧判定里"协议/传输/安全/组合"这一半已被 compat 完整覆盖（且更强）；"节点完整性（地址/凭据/指纹）"这一半
compat 按设计不管（它是内核能力库，不是节点校验器），因此适配层把它们**原样保留**并取**更差者**合并 —— 这也是"零退步"的来源。

---

## 2. 接入方式（最小侵入）

```
节点 JSON ──┬─(source 以 -uri 结尾)─→ parse_uri(raw)          ← 原始链接，保真最高（P6）
            └─(mihomo-yaml/xray-json)─→ 字段→feature 映射      ← 复用 uri.py 的 TRANSPORT_MAP/层级写法
                     │
                     ├─ 补"客户端运行期事实"：genconfig 默认开的 mux.cool（INFERRED + diagnostics 留痕）
                     └─ 其余没落地的键 → extensions[]（禁止静默丢字段）
                     ↓
        check_node(profile, Target(kernel="xray", version=<xray version 真探测>))   ← 唯一判定点
                     ↓
        merged.xray = 更差者(compat 判定, 旧 check_xray 判定)   ← 机械合并，只许收紧
```

关键点：

* **版本真探测**：`<XBD_PREFIX>/bin/xray version` → `26.3.27`；探测不到就留空 → compat 判 UNKNOWN → 回退旧判定（**不写死、不猜**）。
  实测输出：`{"target": {"kernel":"xray","version":"26.3.27","distribution":null,"build_tags":null,"runtime_options":{"mux_cool":true}}}`
* **distribution**：官方二进制首词是 `Xray` → upstream；别的名字按 fork 处理（fork 不继承上游，compat 判 UNKNOWN）。
  `build_tags` 传 `None`（未探测，不是"空"）。
* **合并两条规则**（适配层只做这两条**策略**，不写任何能力规则）：
  1. compat 判 UNKNOWN **且没有任何确定结论**（无 losses、无 UNSUPPORTED 层、非 hard_error）→ **退回旧判定**；
     UNKNOWN 的含义是"我们没有依据"，不是"不能用"，拿它推翻客户端已有的依据会让 XHTTP+ECH 节点凭空变成"不可用"。
  2. 其余情况取**更差者** —— compat 只能收紧，不能放宽。出现"新比旧宽"会被挡下并记进 `downgrades`。
* **回滚**：`XBD_COMPAT_ENGINE=legacy`（不改代码、不改文件）；适配层任何异常都自动落回旧判定，UI 不会崩。
* **性能**：compat2 模块与 `Registry` 各缓存一次（节点列表逐节点调用，不缓存会每个节点重载 61KB 规则）。

---

## 3. 双跑对比（切换前的差异清单）

```bash
$ XBD_XRAY_VERSION=26.3.27 python3 Client/tools/dualkernel-compare.py        # 本地语料 53 条
结论: ✓ 无放宽（新判定只收紧或一致）；收紧 38 条；回退旧判定 0 条

$ ssh CC 'bash /tmp/cc-verify-v2.sh'                                        # + 7 个生产节点 = 60 条
结论: ✓ 无放宽（新判定只收紧或一致）；收紧 40 条；回退旧判定 0 条
- relaxed: 0        ← 旧说"不支持"、新说"支持"：**0 条**（机械保险丝）
- dialer_bug: 0     ← Browser Dialer 维度逐节点一致（它本来就是同一份实现）
```

差异（`tightened`）分三类：

| 类别 | 条数（CC） | 例子（真实链接） | 依据 |
|---|---|---|---|
| **旧"支持" → 新"不支持"** | 4 | `VLESSmKCPSeedWG` / `VLESSmKCPSeed`（`type=kcp&headerType=wireguard&seed=…`） | `xray.mkcp.header_seed`，`KERNEL_REMOVED`（26.x 移除 header/seed，**加载即失败**） |
| **旧"支持" → 新"支持!"（确定的能力损失）** | 36 | 所有节点（客户端默认开 mux.cool）；XHTTP 节点另加"运行期失败"；vless+tcp+vision 加 flow 组合项 | `xray.mux.semantics`、`xray.combo.xhttp_muxcool`、`xray.combo.flow_without_tls` |
| **一致** | 20 | `vless-ws-reality`（两边都不支持）、`vless-h2/http`（两边都不支持）、`vless-bad-fp`（两边都不支持） | — |

回退旧判定（`fallback`）在 CC 上 **0 条**（因为 26.3.27 有规则可用）；在**没有 xray 二进制的机器上**（本地 RN）会整体回退 —— 这是设计行为：
判定来源会在结果里写成 `verdict_source="legacy（compat 判 UNKNOWN）"`，面板/卡片都能看出来。

---

## 4. 新方案比旧的多判出了什么（3 个真实节点 + 1 个系统性）

### 4.1 【假 UNSUPPORTED，已修】hysteria2 在 Xray 上被判"从来没有过"

| | |
|---|---|
| 旧判定 | `hysteria2` 在 `XRAY_PROTOCOLS` 里 → **支持** |
| compat（修正前） | `xray.protocol.hysteria2.never` → ❌ UNSUPPORTED / `KERNEL_NEVER_SUPPORTED` |
| **真实情况** | ✅ 可用。CC 上 26.3.27 实跑：`xray -test` → `Configuration OK`；临时实例经该出站 `curl gstatic/generate_204` → **HTTP 204（1.40s）**，出口 `104.28.195.192`。控制组：`protocol=hysteria9` → `unknown config id`；`protocol=hysteria` + `version=1` → `version != 2`（说明 hysteria 出站处理器**确实存在**且只认 v2）。CC 的**生产实例此刻就在跑**这个出站（`runtime/xray-client.json` → `proxy hysteria mux={"enabled":true}`，`systemctl is-active xray-client` = active） |

原规则是把 mihomo/sing-box 形状的 hysteria2 用例（带 `obfs` 等）当作"三家探针"，从没试过 Xray 自己的
`protocol: "hysteria"` + `settings.version: 2` 形状 → `—` 被记成"内核没有这个字段"。

**处理**：`proxy-node-compat` 只改**数据**（`data/rules.json`）：删 `xray.protocol.hysteria2.never`，改为
`xray.protocol.hysteria2`（`>=26.3.27` → config/runtime SUPPORTED，`<26.3.27` → 显式 UNKNOWN "未逐版验证"），
新增证据 `e-xray-hysteria2-outbound`（RUNTIME_TEST/HIGH，含上面三条命令与输出，并注明**只覆盖出站方向**），
新增 3 个回归测试。**引擎/模型/解析器一行未动**。测试：`Ran 40 tests … OK`（37 → 40）。

> 如果不修：合并层"只许收紧"会让 CC 上**当前正在工作的节点**显示成"不支持"，`nodefilter` 还会拒绝导入 hysteria2 节点 —— 那才是真正的退步。

### 4.2 【系统性，新判出来】XHTTP × mux.cool：客户端默认组合**运行期必失败**

* **旧判定**：只看协议/传输/安全 → 全部"支持"。
* **新判定**：`xray.combo.xhttp_muxcool` → `SUPPORTED_WITH_LOSS` / `runtime_fail` / `SEMANTIC_MISMATCH`：
  「XHTTP 与 mux.cool 同开会运行期失败: `common/mux: unexpected network TCP`」。
* **为什么和这个客户端强相关**：`lib/genconfig.py` 默认给**每个**出站写 `mux:{enabled:true,concurrency:8}`
  （`--no-mux` 才关，`scripts/run-xray.sh` 从不传它），CC 生产配置实测就是这么跑的；节点 JSON 里自己的 `mux:false` **被忽略**。
* **CC 真机回环（服务端也在 /tmp，变量只有 mux）**：

```
===== 13 · XHTTP 回环 =====
--- mux 关（--no-mux）   curl 204 探测 → http_code=204
--- mux 开（默认）       curl 204 探测 → http_code=000     ← 同一台机、同一份配置，只差 mux
```

**另外**：这条结论与客户端自己的一句提示直接打架 —— Browser Dialer 的 notes 里写着"建议开 Mux.Cool：浏览器对同域并发有上限"。
接进来之后，界面会同时显示这两条，用户能看见矛盾（建议后续把 Browser Dialer 那条按 XHTTP 收窄）。

### 4.3 【系统性】mux 的 URI 表达力损失 + 版本区间外不猜

* `uri.vless.mux` / `uri.*.mux`：**分享链接里根本没有 mux 参数**（客户端私有扩展）→ 导入即丢；mux 实现名（mux.cool/smux/h2mux）也无法用链接表达。旧判定对此一无所知。
* 版本区间：`xray.support.xhttp` 只到 `>=26.3.27` 有证据，更早版本 compat 返回 **UNKNOWN**（`unknown_range`），旧判定则一律"支持"。
  语料里 `hysteria2` 在 25.1.1 上就是 UNKNOWN 而不是"支持"（有测试钉住）。

### 4.4 顺带被这套验证挖出来的**客户端自身**问题（与 compat 无关，但都是真问题）

| # | 问题 | 证据 | 处理 |
|---|---|---|---|
| P0 | `genconfig.py` 把旧节点文件里的 `"ech": true`（bool）原样写进 `tlsSettings.echConfigList` → 内核拒绝整份配置：`json: cannot unmarshal bool into Go struct field TLSConfig…echConfigList of type string`；**单节点模式不跑 `--validate-with`** → 写进去 → 内核起不来（切到 CC 的节点 3/4 就是全挂） | CC 实测：`grep -n echConfigList /tmp/xbd-ech-check.json` → `83: "echConfigList": true,`；`xray -test` → `Failed to start` | ✅ **已修**：只写非空字符串，否则跳过并在 stderr 说明（这类节点本来该用 `pinnedPeerCertSha256`） |
| P1 | `node.py` 的 `parse_trojan()` 不读 `pbk/sid/spx` → trojan+REALITY 节点 `reality_public_key=""` → 旧判定报"security=reality 但缺少 pbk"（**假 UNSUPPORTED**），而链接里明明有 pbk | `node-001…` 对照：`compat` 从原始链接解析 → SUPPORTED_WITH_LOSS；旧判定 → NOT_SUPPORTED | ⏸ 未改（超出本次范围）：合并层按"只收紧"保留"不支持"+说明，**不会误导**；修法：trojan 分支补 `pbk/sid/spx`（vless 分支已有） |
| P2 | CDN 节点 pin 过期：CC 的 xhttp 节点 pin 与现行证书不符（节点 `f92bfe59…` vs 线上 `E39FE744…`，Cloudflare 轮换）→ 无论 mux 开关都连不上 | `openssl s_client` 对比 + 直连 `https://mos.casmi.dpdns.org/` = 200 | ⏸ 未改：属节点新鲜度问题，记 UNKNOWN（见 U1）；对自签节点 pin 是对的，对 CDN 节点要谨慎 |

---

## 5. CC 实测（命令 + 输出片段）

全部在 `/tmp` 内完成（解包到 `/tmp/xbd-v2`，节点/配置是**只读副本**），未写 `/opt/xray-browser-dialer` 任何文件、未启停任何服务；
跑完已清理，生产 `xray-client` / `xbd-share` 始终 active。原始输出见 `evidence/cc-run.log`。

| # | 项 | 命令 | 结果 |
|---|---|---|---|
| 1 | 版本真探测 | `compat2.py version` | `version=26.3.27`，`runtime_options.mux_cool=true` |
| 2 | `xbd node list` | `XBD_PREFIX=/tmp/xbd-v2 xbd node list` | 7 个真实节点全部渲染，两列判定正常（见下） |
| 3 | 面板 | `panel.py --port 18099 --token …` + `GET /`、`GET /api/state` | `http=200`（119KB / 178KB）；7 个节点都带 `compat.kernel`；`losses/unknowns/warnings/extensions/raw_uri/diagnostics` 全部随状态带出 |
| 4 | 回滚开关 | `XBD_COMPAT_ENGINE=legacy compat.py json <current>` | 回到旧判定（`engine=` 空 → legacy 路径） |
| 5 | `want-bd` 一致性 | 7 个节点 × 两套引擎 | **7/7 SAME**（浏览器拨号判定零变化） |
| 6 | 真实链路 | 客户端 `genconfig` → 内核 → `curl --socks5-hostname …/generate_204` | reality **204**（mux 开/关都 204）、hysteria2 **204**、xhttp **000**（pin 过期，两变体都 000） |
| 7 | XHTTP×mux 回环 | 临时 XHTTP 服务端（/tmp）+ 客户端配置 | **mux 关 204 / mux 开 000** |
| 8 | `interactive-test.sh client --read-only` | CC 上跑 | **全部通过: 55 项** |
| 9 | `tools/check_libs.sh` | 仓库内 | **576 通过, 0 失败** |
| 10 | `python3 -m unittest discover -s tests` | compat 仓库 | **Ran 40 tests … OK** |

`xbd node list` 实测（新判定；`支持!` = WARN）：

```
  1   *  🇺🇸 CCSmHysteria2-01       hysteria2  quic   支持!   不支持
  2      🇺🇸 CCSmReality-01         vless      tcp    支持!   不支持
  3      🇺🇸 CCSmvless-01           vless      xhttp  支持!   支持!
  4      🇺🇸 CCSXvless-xhttp-01     vless      xhttp  支持!   支持!
  … （7 个节点，Browser Dialer 列与旧实现逐项一致）
```

**"旧 vs 新 vs 真实"三条真实链接的对照**（CC，节选自 `evidence/cc-run.log` §7）：

| 链接 | 旧判定 | compat | 合并 | 真实连通 |
|---|---|---|---|---|
| `vless + reality + vision`（RN 批量 25000） | 支持 | `SUPPORTED_WITH_LOSS`（mux、flow 组合） | 支持! | ✅ 204 |
| `hysteria2`（RN 批量 25002/udp） | 支持 | UNKNOWN（`allowInsecure` 走 unknown_range）→ 但 losses 确定 → WARN | 支持! | ✅ 204 |
| `vless + mKCP + seed`（RN 真链接） | 支持 | ❌ UNSUPPORTED / `KERNEL_REMOVED` | **不支持** | 26.x 加载即失败（`xray.mkcp.header_seed` 证据） |
| `trojan + reality`（RN） | **不支持**（node.py 丢 pbk） | SUPPORTED_WITH_LOSS | 不支持（旧判定的保守结论保留 + 说明） | 未测（U4） |
| 生产 `vless + xhttp + ECH + pin` | 支持! | UNKNOWN（ECH 内容不可验证）但 xhttp×mux 确定 → WARN | 支持! | ❌ 000（pin 过期，与 mux 无关） |

---

## 6. 有没有退步 / 有没有假 UNSUPPORTED

| 问题 | 结论 | 证据 |
|---|---|---|
| 旧"不支持" → 新"支持"（静默放宽） | **0 条** | 60 条语料 `relaxed: 0`；合并层机械取更差者 + `downgrades` 留痕 |
| Browser Dialer 判定变化 | **0 条** | 7 个真实节点 `want-bd` 全 SAME；实现未动 |
| 导入行为变化 | 无（`can_use_xray` 语义不变：只有 OK/WARN 才算可用） | `nodefilter.py` 未改；UNKNOWN 仍不算可用 |
| 假 UNSUPPORTED（新判定） | **0 条** | 唯一一条（hysteria2）已在 §4.1 修掉；`tuic/anytls/xtls/未知传输/未知 scheme` 都仍是不支持 |
| 假 UNSUPPORTED（旧判定，新判定能识别但被保险丝挡下） | 1 条：`trojan+REALITY`（`node.py` 丢 pbk，§4.4 P1） | CC 语料 `🇺🇸 trojan/tcp/reality`：旧=不支持，compat=SUPPORTED_WITH_LOSS，合并=不支持（有说明） |
| 假"会丢能力"（误报） | 1 类：`xray.combo.flow_without_tls` 对 `flow+tcp+security∈{tls,reality}` 也报损失 | 规则选择器只有 `all_of_features:[standard:flow, standard:transport.tcp]`，**表达不了"且没有 tls/reality"**；实际这类节点 CC 实测 204（reality+vision）、语料 5 条 + CC 2 条受影响 |
| UI 文案变化（非功能退步） | 所有节点 `支持` → `支持!` | 因为客户端默认开 mux.cool，compat 判"确定会丢能力"（真结论，不是误报）；卡片会解释这句话的来源 |
| 浏览器拨号行为 | 不变 | `want_browser_dialer()` 一行未改；`compat.py` 仍是该维度唯一实现 |

---

## 7. UNKNOWN（没证据就不猜）

| # | 事项 | 为什么没结论 |
|---|---|---|
| U1 | `xhttp × mux.cool` 在**真实 CDN 节点**上的失败形态 | CC 的 xhttp 节点因 pin 过期（P2）根本连不上，无法把失败归因到 mux；只有本机回环证据（§4.2） |
| U2 | Xray 的 ECH 运行时是否真生效 | compat 的既有结论：配置层不校验内容（`xray.ech.config_lax`）；无回环证据 |
| U3 | `allowInsecure` 在 26.3.27 的实际行为 | compat 标为时间闸门区间（引擎未实现 `evaluated_at`）；客户端本来不写该字段 |
| U4 | `trojan+REALITY` 在修好 `node.py` 之前的真实可用性 | 链接可用、客户端解析丢 `pbk`，未构造端到端 |
| U5 | Xray hysteria2 **入站**方向 | 本次只验出站（客户端只用出站）；规则注释里已写明范围 |
| U6 | hysteria2 在 `<26.3.27`（含 25.x）的支持情况 | 未逐版验证 → compat 规则显式 UNKNOWN |
| U7 | 另外两个内核（mihomo/sing-box）客户端的接入效果 | 本次只接 X 客户端；纪律要求不动那两个仓库 |
| U8 | Xray 的 `build_tags` | 官方二进制无该概念，传 `None`（未知）；目前无 xray 规则依赖它 |
| U9 | 非官方 fork 的 Xray 构建 | 只按 `xray version` 首词判断 distribution，未实测 |
| U10 | CDN 前端节点的 pin 是否会普遍过期 | 只验了 CC 上那一个（已确认不符）；未逐节点核对 |
| U11 | `socks` / `http`（简易出站）的能力结论 | compat 注册表没有 xray 的这两条协议规则 → 本次靠回退旧判定（结论与旧判定相同，未用 compat 独立验证） |

---

## 8. 复现方式

```bash
# 1. 兼容层单测（含本次新增的 hysteria2 回归）
cd /root/deepseek/repos/proxy-node-compat && python3 -m unittest discover -s tests

# 2. 双跑对比（无内核二进制的机器上给个已知版本）
cd xray--core/Client && XBD_XRAY_VERSION=26.3.27 python3 tools/dualkernel-compare.py

# 3. 适配层自检 / 单节点判定
XBD_XRAY_VERSION=26.3.27 python3 lib/compat2.py selftest
python3 lib/compat2.py kernel <节点.json>          # compat 视角（含 raw_uri/extensions）
python3 lib/compat2.py compare <节点.json>         # 旧 vs 新 vs 合并

# 4. CC 验收（先 scp Client/xbd-client.tar.gz 到 /tmp）
ssh CC 'bash /tmp/cc-verify-v2.sh'                 # 收尾 rm -rf /tmp/xbd-v2 …

# 5. 回滚（不改代码）
XBD_COMPAT_ENGINE=legacy xbd node list
```
