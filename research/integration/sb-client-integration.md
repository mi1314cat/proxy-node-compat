# SB 客户端（`sing-box-core` / `src/client`）接入 `proxy-node-compat` · 实施与验收报告

> 日期：2026-10-10 ｜ 实施对象：`mi1314cat/sing-box-core` 的客户端（`src/client/*`，服务端 `src/conf/*` 未动）
> 兼容层：`proxy-node-compat` 快照 **`3a75ba5`**（vendored，8 个文件逐字节一致；67 规则 / 26 证据 / 12 URI 规则，其中 **singbox 21 条**）
> CC 实测机：`192.168.1.178`（armbian / arm64，sing-box **1.14.2** `af6e64c`，客户端 `/opt/sb-client`，生产 PID 1444214）
> RN（服务端+真内核）：sing-box 1.14.2 同 revision，`Tags` 多一个 `with_purego`
> 原始输出：`research/integration/evidence/sb-cc-run.log`（CC 全量实跑）、`evidence/sb-cc-out/`（逐节点 TSV/JSON）

**一句话结论**：接进去有用，抓到一个**会丢真实可用节点的假 UNSUPPORTED**（VLESS 链接的 `encryption=none` 被当成 VLESS Encryption）
和三处客户端自身的真问题（多节点导入按空格拆 tag 落空文件；`to_sb` 给无 `security=` 的 trojan 链接不写 TLS；`to_sb` 的 scheme 白名单漏 anytls）。
**没有退步**：13 条 RN 真实链接 + 75 个真实出站上 `放松 = 0`；回滚开关一键回到旧判定；**真实连通性 13/13 = HTTP 204**，出口 IP 一致。

---

## 0. 交付物

| 位置 | 内容 |
|---|---|
| `src/client/lib/proxy_node_compat/` | vendored 兼容层（含 `data/rules.json`），零第三方依赖，== `proxy-node-compat@3a75ba5` |
| `src/client/compat2.py` | **适配层**：节点 → Node Profile → `check_node(profile, Target(kernel="singbox", …))`；双跑合并；`reason_code` 文案；`filter-json` 闸门；CLI |
| `src/client/to_sb.py` | 订阅转换器：share-URI / mihomo / sing-box JSON 三条路都过 compat 闸门；`--compat-report` 落全量结果 |
| `src/client/client.sh` | 自家 share（已是 sing-box JSON）路径补 compat 闸门；`compat_brief` 摘要；`sb-client compat` 自检；**顺带修**多节点导入的 tag 拆分 bug |
| `install.sh` | 客户端安装时一并复制适配层与 vendored 库 |
| `tools/check_compat_wiring.sh` | **门禁**（本仓库原本没有任何门禁）：bash -n / py_compile / 快照逐字节 / 真探测 / selftest / 双跑语料 / 端到端 / 边界。可重复执行，`通过 19 / 失败 0` |
| 本文件 | 对照表 / 双跑 / CC 实测 / 多判出什么 / 假 UNSUPPORTED / 退步 / UNKNOWN |

---

## 1. 现状摸底：SB 客户端现在怎么判"可用/不可用"

### 1.1 判定点（接入前）

| 位置 | 什么时候判 | 判什么 | 判错的代价 |
|---|---|---|---|
| `src/client/to_sb.py`（客户端订阅导入，**主力**） | 外部订阅转换时 | scheme 白名单、host/port 必填、**只认 ws/grpc/h2 三种传输** | 别的传输**静默降级成 tcp**：内核不报错，节点永远连不上 |
| `src/conf/outbound_uri.py`（面板"分享链接添加"，**客户端机器上一般没有这个文件**） | 用户手动贴链接时 | `SUPPORTED_SCHEMES`、传输白名单 `tcp/ws/grpc/http/httpupgrade`、`SS_METHODS`、plugin 白名单 | 明确报错 —— **"不支持的传输方式 type='xhttp'（本面板支持 tcp/ws/grpc/http/httpupgrade）"就出自这里，这个优点是本次要保住的** |
| `src/client/client.sh` | 导入后 / 运行期 | `sing-box check` 整份配置、`functional_probe`（curl 204）、`node_count` | 只能整份判，说不到"哪个节点为什么不行" |
| `sing-box` 内核 | `check` / `run` | 语法与字段（DisallowUnknownFields） | 一条坏节点能拖掉整份配置 |

**结论**：客户端**没有逐节点的能力判定**。`to_sb.py` 判定的是"认不认识这个 scheme/传输"，一旦不认识就**静默丢掉传输**（不是丢节点）——
这就是"看着支持、实际连不上"的来源；而 `outbound_uri.py` 那种"说了缺什么、支持什么"的报错，客户端这条路上完全没有。

### 1.2 对照表：它的判断 ↔ compat 规则

| # | 现有判定 | 判据来源 | `proxy-node-compat` 对应（kernel=singbox） | 覆盖 |
|---|---|---|---|---|
| 1 | scheme ∈ {ss,vmess,vless,trojan,hysteria2,hy2,tuic}（`to_sb` 另有 socks/http/anytls 的**死代码**） | 源码 | `singbox.protocol.{vless,vmess,trojan,shadowsocks,hysteria2,tuic,anytls}`（全部 `range=*` SUPPORTED） | ✅ 覆盖，且能指出 `naive/shadowtls` 这类**注册表未收录**的协议（UNKNOWN，不判死） |
| 2 | 传输 ∈ {tcp,ws,grpc,h2/http}（`to_sb`）；{tcp,ws,grpc,http,httpupgrade}（`outbound_uri`） | 实测 | `singbox.support.transport_{ws,grpc,httpupgrade}`（SUPPORTED）、`singbox.xhttp.never`、`singbox.mkcp.never`（`KERNEL_NEVER_SUPPORTED`） | ✅ 覆盖且**更强**：xhttp/mkcp 是真不支持；**httpupgrade 内核支持而 `to_sb` 会丢** —— compat 直接点出来 |
| 3 | security ∈ {none,tls,reality,xtls}（xtls 当 tls） | 源码 | `singbox.support.tls`、`singbox.support.reality`（`>=1.14.2`）、`singbox.reality.build_tags`（需 `with_utls`） | ✅ 覆盖，且**版本/构建标签真的参与判定**（见 §3.7） |
| 4 | 缺 host/port → 丢节点 | — | 无（不是能力问题） | ➖ **留在旧判定**（guard） |
| 5 | 凭据完整性（uuid/password/method） | — | 无 | ➖ **留在旧判定** |
| 6 | `ss://` 的 `security=reality`（`to_sb` 提前 return，TLS 段整段丢掉） | — | `singbox.ss_reality.never`（`KERNEL_NEVER_SUPPORTED`） | ✅ 覆盖（JSON 路径实测拦下，见 §5.7） |
| 7 | vless 的 `encryption` 参数 | 无（`to_sb` 直接忽略） | `singbox.vless.encryption.never` | ⚠️ 覆盖但**踩了 uri.py 的坑**：`encryption=none`（哨兵值）也被当 feature → **假 UNSUPPORTED**，见 §4.1 |
| 8 | ECH（`tls.ech.config` 要 PEM 不是 base64） | 无 | `singbox.ech.representation`（`SEMANTIC_MISMATCH`） | 🆕 新增判定 |
| 9 | mux（`multiplex`）：客户端**不写**；但自家/老订阅里带 | 无 | `singbox.mux.semantics`（`silent_ignore` → `SUPPORTED_WITH_LOSS`） | 🆕 新增判定（CC 实测 12 个真实出站命中） |
| 10 | flow（`xtls-rprx-vision`） | 无 | `singbox.support.flow`（`>=1.14.2`） | 🆕 新增判定 |
| 11 | **客户端转换环节丢没丢东西**（链接里有、写出配置里没有） | 无 | —— 由适配层做「原文 profile vs 出站 profile」的差集（**不是能力规则**） | 🆕 新增（真抓到 trojan 丢 TLS / httpupgrade 丢传输） |
| 12 | `sing-box check` + `functional_probe` | 内核/实测 | 不在 compat 范围（运行期实测不是能力） | ➖ **原样保留** |

---

## 2. 接入方式（最小侵入）

```
分享链接 ─┬─ to_sb.uri_to_outbound() ─┐
          │                          ├─→ compat2.judge(uri=原文, outbound=客户端产物)
mihomo ───┼─ clash_to_outbound() ────┤        ↓
sing-box ─┴─ 原样（自家 share） ──────┘   check_node(profile, Target(singbox, version=真探测, build_tags=真读))
                                              ↓
                          合并: compat 只许收紧 / UNKNOWN 退回旧判定 / 放宽记 downgrades
                                              ↓
                          留 → 落盘 node-<tag>.json；丢 → reason_code 文案说清"缺什么、支持什么"
```

* **判定只在 compat 发生一次**：适配层**不写任何能力规则**，只做「节点 → profile」的搬运 + 两条合并策略 + 文案渲染。
  连"本内核支持哪些传输"这种话也是**逐条去问 compat**（`feature_verdict()` 造最小 profile 调 `evaluate`），不是适配层写死的表。
* **版本 + build tags 真读**：`<CLIENT_BIN> version` 的第一行（`sing-box version 1.14.2` → distribution=upstream；别的名字按 fork → 整体 UNKNOWN）
  与 `Tags:` 行；**`Tags` 行不存在时给 `None`（未知）而不是 `[]`（确定没有）** —— 后者会让 Reality 被判 `BUILD_NOT_ENABLED`。
  探测不到就 version=None → compat 判 UNKNOWN → 自动回退旧判定。
* **回滚**：`SB_COMPAT_ENGINE=legacy`（不改代码、不改文件）；`SB_COMPAT_DISABLE=1` 关掉整条闸门；适配层异常一律落回旧判定。
* **必须带出的字段**：`raw_uri` / `losses` / `unknowns` / `warnings` / `extensions` / `client_losses` / `downgrades` / `shims` / `target`，
  由 `--compat-report` 落到 `share-state/.compat-last.json`，`client.sh` 打印摘要。
  **绝不把 compat 的键写进 `node-*.json`** —— 内核 DisallowUnknownFields，会直接拒绝整份配置。

---

## 3. CC 实测（全部在 `/tmp/sbc-verify`，未写 `/opt/sb-client` 任何文件、未启停任何服务）

生产进程在实测前后都在：`1444214 /opt/sb-client/core/sing-box run -D /opt/sb-client/conf`（etime 1-03:54 → 1-04:02）。

### 3.1 目标四元组（真读，不写死）

```
CC:  sing-box version 1.14.2 / go1.26.8 linux/arm64 / Revision af6e64c3b69e6132ebaee0e1a3d24e93903f6709
Tags: with_gvisor,with_quic,with_dhcp,with_wireguard,with_utls,with_acme,with_clash_api,with_tailscale,
      with_ccm,with_ocm,with_cloudflared,with_naive_outbound,with_usbip,with_openvpn,with_openconnect,
      badlinkname,tfogo_checklinkname0                       ← 17 个
RN:  同上 + with_purego                                      ← 18 个
```

### 3.2 真实订阅怎么拉的（诚实说明）

RN 的分享链接是**一次性**的（`max_uses=1`），CC 上那条订阅的 token 已用尽（实测 `HTTP 410`）。
所以把 RN **自己生成**的两份产物原样搬到 CC，用本地 HTTP 发出去，让客户端的「HTTP 拉取 → 识别 → 转换 → compat → 落盘」整条路径真跑：

* `out/sb_client-all.json`（13 个出站，覆盖 anytls/hysteria2/naive/shadowtls/vless/vmess/trojan/tuic/ss）
* `out/sb_share-*.txt`（**13 条真实分享链接**，RN 服务端自己生成的）

### 3.3 三次导入的节点数（同一份真实链接，只有引擎不同）

```
绕行开（默认）       → 8 个节点
绕行关（SB_COMPAT_NO_SHIMS=1）→ 6 个节点   ← 差的 2 个就是"假 UNSUPPORTED"
回滚（SB_COMPAT_ENGINE=legacy）→ 9 个节点  ← 差的那 1 个是服务端链接写错的坏链接
[绕行开 - 回滚]  rn vmess02-REALITY       → compat 判死、旧判定会放进来；实测该链接**真的连不通**（§3.6）
[绕行开 - 绕行关] rn reality01-REALITY / rn vless01-TLS-CDN → 真实可用（都是 204），假 UNSUPPORTED
```

### 3.4 逐节点三方对比

**表 A · URI 路径（13 条 RN 真实链接）**：一致 12 / 收紧 1 / **放松 0** / 回退旧判定 4

| 链接 | 旧判定 | compat | 合并 | 真实连通 |
|---|---|---|---|---|
| `vless reality`（`?encryption=none&security=reality…`） | 支持 | SUPPORTED | 支持 | ✅ 204 |
| `vless ws+tls`（`?encryption=none&security=tls…`） | 支持 | SUPPORTED | 支持 | ✅ 204 |
| `vmess ws+tls` / `vmess ws+reality`（JSON 形态） | 支持 | SUPPORTED | 支持 | ✅ 204 / 204 |
| `trojan ws+tls`（链接里**没有** `security=`） | 支持 | SUPPORTED | 支持（**带转换损失警告**） | 原样导入 ❌ 000；补上 TLS ✅ 204 |
| `trojan ws+reality` | 支持 | SUPPORTED | 支持 | ✅ 204 |
| `hysteria2` / `tuic` / `ss` | 支持 | SUPPORTED | 支持 | ✅ 204 / 204 / 204 |
| `anytls`（×2） | **不支持**（`to_sb` 白名单漏了 anytls） | SUPPORTED | 不支持（取更差者，记 downgrades） | 内核侧 ✅ 204 |
| `shadowtls` / `naive+https` | **不支持**（`to_sb` 转不出来） | UNKNOWN | 不支持（回退旧判定） | ✅ 204 |
| `sb_share-vmess02-REALITY.txt`（其实是 `vless://…encryption=aes-128-gcm`，**服务端分享层写错了 scheme**） | 支持 | ❌ UNSUPPORTED (`singbox.vless.encryption.never`) | 不支持 | 原样导入 ❌ 000 |

**表 B · sing-box JSON 路径（75 个真实出站 = RN 整份 profile 13 + CC 生产节点文件 59）**：
无问题 63 / 有确定损失 12（全部是 `multiplex` 的 `silent_ignore`）/ **判不支持 0** / 未知 0。

### 3.5 真实连通性（每节点一个临时内核实例，mixed 绑 127.0.0.1 高位端口）

```
rn-anytls01-TLS      anytls      204  2.14s  104.28.201.80
rn-anytls02-REALITY  anytls      204  0.94s  104.28.201.80
rn-hysteria201-TLS   hysteria2   204  1.64s  104.28.201.80
rn-naive01-TLS       naive       204  1.11s  104.28.201.80
rn-reality01-REALITY vless       204  1.09s  104.28.201.80
rn-shadowsocks01     ss          204  0.87s  104.28.201.80
rn-shadowtls01-TLS   shadowtls   204  1.45s  104.28.201.80
rn-trojan01-TLS-CDN  trojan      204  2.29s  104.28.201.80
rn-trojan02-REALITY  trojan      204  1.09s  104.28.201.80
rn-tuic01-TLS        tuic        204  1.28s  104.28.201.80
rn-vless01-TLS-CDN   vless       204  3.46s  104.28.201.80
rn-vmess01-TLS-CDN   vmess       204  2.18s  104.28.201.80
rn-vmess02-REALITY   vmess       204  1.14s  104.28.201.80
→ 实测 204 通过 13 / 13
```

### 3.6 转换损失的真实后果（对照实验）

| 用例 | HTTP | 内核日志 |
|---|---|---|
| A `to_sb` 按 RN 真实 trojan 链接转出来的出站（**丢了 TLS**） | **000** | `ERROR connection: open connection … using outbound/trojan[…]: unexpected HTTP response status: 400` |
| B 同一节点补上 TLS | **204** | — |
| C shadowtls 链（原样，**带** `multiplex`） | 204 | — |
| D shadowtls 链（**去掉** `multiplex`） | 204 | — |
| E 把 `sb_share-vmess02-REALITY.txt`（vless+aes-128-gcm）原样导入 | **000** | vless 出站拨到 vmess+REALITY 服务端，静默失败 |

→ A/B 是因果：**compat 报的"转换丢 TLS"不是纸面结论，是真会 400 的**。
→ C/D 说明 compat 报的 mux 损失**不是** shadowtls 那条的故障原因（它本来就 204）；mux 是"语义不一致"的警告，不是"连不上"。

### 3.7 build tags 真的参与判定了吗

* 真读：上面 17/18 个 tag 是从 `sing-box version` 的 `Tags:` 行解析出来的（不是写死的表）。
* 反向验证（门禁里钉住）：把 `build_tags` 说成 `[]` → Reality 立刻 `BUILD_NOT_ENABLED`（`singbox.reality.build_tags` 要求 `with_utls`）；
  **探测不到 tags 时给 `None`** → 只记 UNKNOWN、不判死。
* **规则缺口（未改 compat，只记录）**：`with_quic`（hysteria2/tuic 需要）与 `with_naive_outbound`（naive 出站需要）
  在 singbox 规则里**没有任何 `requires_build_tags`** —— 在缺这两个 tag 的自编译内核上 compat 会判 SUPPORTED 而内核起不来。
  CC/RN 的官方构建两者都有，所以本次实测不受影响（记 UNKNOWN/GAP，见 §7 U3）。

---

## 4. 新方案比旧的多判出了什么

### 4.1 【假 UNSUPPORTED，已绕行】`encryption=none` 被当成 VLESS Encryption

| | |
|---|---|
| 触发 | `vless://…?encryption=none&security=…` —— **VLESS 分享链接规范里的哨兵值**，v2rayN/Xray 一律会写；RN 服务端自己生成的 `sb_share-reality01-REALITY.txt` 就是 |
| 原因 | compat `uri.py:310`：`if proto_id == "standard:vless" and q.get("encryption") not in (None, "")` —— 只要非空就算"VLESS Encryption" feature → 命中 `singbox.vless.encryption.never` → `KERNEL_NEVER_SUPPORTED` |
| 后果（实测） | CC 上 13 条真实链接里 **2 条**（`reality01-REALITY`、`vless01-TLS-CDN`，都是**实测 204 的可用节点**）被判死；整个客户端只要遇到带 `encryption=none` 的 vless 链接就丢节点 —— 现实里这几乎是**全部** vless 链接 |
| 处理 | 适配层加**一条**解析层绕行（`_apply_shims`）：`encryption` 的值明确是 `none` 时，把那个 feature 从 **profile** 里摘掉（不是改 compat、不是加能力规则），结果里带 `shims[]` + 文案留痕；`SB_COMPAT_NO_SHIMS=1` 可复现原判 |
| 证据 | 门禁语料钉死两条：`encryption=none` → SUPPORTED；`encryption=mlkem768x25519plus…` / `encryption=aes-128-gcm` → **仍然 UNSUPPORTED**（真 VLESS Encryption 不受影响） |

> 这是**必须修**的：不绕行就是 2/13 真实可用节点被丢 = 真退步。绕行不是"放宽能力判定"——`none` 的语义就是"不加密"，
> 摘掉它让 profile **更忠实**于链接本意。compat 侧修好 `uri.py` 之后应删除这段（门禁里有回归盯着）。

### 4.2 【新判出来】`to_sb.py` 给"没有 `security=` 的 trojan 链接"不写 TLS

* RN 真实链接 `trojan://…@hxicc…:443?sni=…&alpn=http/1.1&type=ws&path=/…&host=…`（**没有 `security=`**）→ `to_sb._std_uri` 只在 `sec in (tls,reality,xtls)` 时才写 `tls` 段 → **trojan 出站没有 TLS**。
* compat 侧：`standard:tls` 存在（trojan 生态默认 TLS）→ 判定 SUPPORTED，但适配层的**转换损失对比**直接点出来：
  「分享链接里有 standard:tls, 写出的出站里没有 —— 客户端转换环节丢了（内核侧不会报错, 只会连不上）」。
* 实测因果（§3.6 A/B）：原样 **000**（内核 400），补上 TLS **204**。
* 处理：**只报不改**（属客户端转换器语义，超出"接入 compat"范围，也避免顺手放开行为）→ 见 §7 U6。

### 4.3 【新判出来，顺带修】多节点导入按空格拆 tag → 落一堆空文件 → 配置再也生成不出来

* RN 真实链接的节点名是 `🇺🇸 rn vless01-TLS-CDN`（**带空格和 emoji**）。`client.sh` 里 `for t in $tags` 按空格拆成好几个假 tag，
  每个假 tag 都 `select(.tag == $t)` 不到 → jq 整个表达式**无输出** → 落下一批**空文件**；
* 紧接着 `regen_selector` 读空文件抛 `JSONDecodeError` → `90-outbounds.json` **停在旧内容上**（实测：13 条链接 → "导入 24 个节点" + "现 13 个可用节点"）。
* 处理：**已修**（`while IFS= read -r t … done <<< "$tags"`，不开子 shell）。修完 13 条链接 → 正确的 8/6/9 个节点。
* 这是**旧客户端就有的 bug**（与 compat 无关），但不修就没法验证 URI 路径。

### 4.4 【旧判定的假阴性，被保险丝记下来】`to_sb` 的 scheme 白名单漏了 anytls

`to_sb.uri_to_outbound()` 的 scheme 列表是 `(vless, trojan, ss, socks, http, hysteria2, hy2, tuic)` ——
**没有 anytls**，可 `_std_uri()` 里明明有 `elif scheme == "anytls"` 分支（死代码）。所以 RN 两条真实 anytls 链接
（compat 判 SUPPORTED、实测 204）在旧判定里是"不支持"。合并层按"只许收紧"保留旧结论，但把它记进
`downgrades`（"compat 判定比旧判定宽, 已按'只许收紧'取旧判定"），报告里能看见。**未改**（属客户端功能缺失，不属本次范围）。

### 4.5 【系统性，新判出来】`mux`（`multiplex`）的语义不一致

CC 生产节点文件 + RN profile 里 **12 个真实出站**带 `multiplex:{enabled:true,…}` →
`singbox.mux.semantics`（`silent_ignore` → `SUPPORTED_WITH_LOSS`，`SEMANTIC_MISMATCH`）：
「三方 mux 不同构（Xray=mux.cool / mihomo=smux / sing-box=multiplex），跨内核搬运不保证语义一致」。
实测（§3.6 C/D）表明它**不是**"连不上"的原因 —— compat 自己标的也是 `silent_ignore` + `SUPPORTED_WITH_LOSS`，不是硬失败。
SB 客户端自己不写 `multiplex`（X 客户端默认开 mux.cool 那种坑在这里不存在）。

### 4.6 服务端分享层写错了 scheme（**给另一个 agent 的输入**）

`/root/catmi/sing-box/out/sb_share-vmess02-REALITY.txt` 的内容是
`vless://d35b8824-…@107.173.154.178:31011?encryption=aes-128-gcm&security=reality&…`：
**节点是 vmess+REALITY，链接却写成 vless:// 并把 vmess 的密码套件塞进 `encryption`**。
任何客户端照这条链接导入都会得到一个连不通的 vless 节点（实测 000）。
compat 对它判 UNSUPPORTED（对链接而言是**正确**的），但**根因在分享生成侧**。

> 跟进：另一个 agent 已经在 `4fccbc6 修: 分享链接不再写无效参数 —— hy2 去掉 obfs=none, vmess 改回标准 vmess://` 里修掉了生成逻辑。
> 但 RN 上 `out/sb_share-vmess02-REALITY.txt` 仍是 **10-06 00:01** 的旧产物（未重新生成），所以本次实测用的就是这条坏链接 ——
> 结论不变：**compat 判它 UNSUPPORTED 不是假 UNSUPPORTED**。

---

## 5. 有没有退步 / 有没有假 UNSUPPORTED

| 问题 | 结论 | 证据 |
|---|---|---|
| 旧"不支持" → 新"支持"（静默放宽） | **0 条** | 13 条真实链接 + 12 条语料，`放松 = 0`；合并层机械取更差者 + `downgrades` 留痕 |
| 假 UNSUPPORTED | **有，1 类，已绕行**：`encryption=none` 的 vless（真实影响 2/13 条链接，且是**全网 vless 链接的常态**） | §4.1；`SB_COMPAT_NO_SHIMS=1` 前后 8 → 6 个节点 |
| compat 判死的其余节点 | **无假阳性**：`vmess02-REALITY`（链接写错）实测 000；`xhttp`/`mkcp`/`ss+reality` 是内核从来就没有的能力 | §3.6 E；门禁语料；§5.7 |
| JSON 路径判死 | **0 个**（75 个真实出站） | 表 B |
| 真实可用节点被丢 | **0**（绕行开时 13 个实测 204 的节点全部保留；`rn vmess02-REALITY` 的真实节点走 JSON 路径，也保留） | §3.4/§3.5 |
| 导入行为变化 | 只多、不少：`to_sb` 转换闸门只在 compat 明确 UNSUPPORTED 时丢；自家 share JSON 路径以前**完全不判**，现在逐节点判 | §3.3 |
| 单节点 JSON 闸门误伤 | 0：`selector/urltest/direct` 原样保留，只过滤真出站 | 门禁 §7（`filter-json` 用例） |
| 生产服务 | 未触碰 | 实测前后 PID 1444214 都在；改动全在 `/tmp/sbc-verify` |

---

## 6. 复现方式

```bash
# 1) 门禁（本仓库唯一的一道, 可重复执行; 无内核时自动用离线夹具）
cd /root/deepseek/repos/sing-box-core && bash tools/check_compat_wiring.sh
#    → 通过 19 / 失败 0

# 2) 适配层自检 / 目标四元组 / 单链接三方对比
cd src/client
python3 compat2.py version
python3 compat2.py selftest
python3 compat2.py compare 'vless://…@host:443?encryption=none&security=reality&pbk=…&sid=…&type=tcp'
SB_COMPAT_NO_SHIMS=1 python3 compat2.py compare '<同一条>'      # 复现 compat 原判

# 3) 单份订阅的 compat 视图（逐出站）
python3 compat2.py check-json <profile.json>
python3 compat2.py filter-json <profile.json> --out kept.json --report rep.json

# 4) 客户端整条路径（沙箱, 不写生产）
CLIENT_ROOT=/tmp/sbc-verify/client bash /tmp/sbc-verify/client/client.sh add <订阅URL>
CLIENT_ROOT=… bash /tmp/sbc-verify/client/client.sh compat      # 目标 + 自检

# 5) 一键回滚（不改代码、不改文件）
SB_COMPAT_ENGINE=legacy sb-client add <订阅URL>
SB_COMPAT_DISABLE=1 sb-client add <订阅URL>
```

---

## 7. UNKNOWN（没证据就不猜）

| # | 事项 | 为什么没结论 |
|---|---|---|
| U1 | `encryption=none` 的**根因**修在 compat 侧（`uri.py:310`）之后本绕行是否可删 | 本任务边界是"只改 sing-box-core、compat 不改语义"，所以只做了 profile 侧绕行；绕行点已在代码与门禁里标死 |
| U2 | `to_sb` 的 trojan 无 `security=` 不写 TLS | 只做了因果实测（000 vs 204），未改（属转换器语义，另立任务更合适） |
| U3 | 缺 `with_quic` / `with_naive_outbound` 的内核上 hysteria2/tuic/naive 的真实行为 | compat 规则里没有这两条 `requires_build_tags`（GAP，未改 compat）；CC/RN 官方构建都有，没法用现成二进制反证；CC 有 go1.22 但**没有 sing-box 源码**（RN 的 `src-upstream` 是面板源码不是上游），无法自编译验证 → 记 GAP |
| U4 | `with_purego`（RN 有、CC 没有）对能力的影响 | 该 tag 只影响 Go 运行时（cgo/pure-go DNS 解析），未逐项验证 |
| U5 | 真实 CDN 订阅（CC 上 `cadacac.onecatmi.dpdns.org`）里的 30 个节点 | 实测 `HTTP 522`（源站不可达）→ 本次表 B 里的 `der-*`/`cf-*` 是**此前已落盘**的真实出站，未重新拉取 |
| U6 | `mux` 在真实节点上的性能/连通影响 | 只做了 shadowtls 一对对照（都 204），单样本不足以给结论 |
| U7 | `naive`/`shadowtls` 协议在 compat 注册表里的能力 | singbox 规则里**没有**这两条协议规则 → compat 判 UNKNOWN（不判死，回退旧判定）；未补规则（不改 compat） |
| U8 | 上游 `proxy-node-compat` 工作区里在途的 mihomo `uri_rule(target_kernel)` 改动 | vendored 快照钉在**提交版** `3a75ba5`；在途改动未纳入（对 singbox 无影响：那些行都带 `target_kernel: mihomo`） |

---

## 8. 与另一个 agent 的冲突（如实记录）

* `src/conf/share.sh` / `share_client.py` / `lib.sh` / `vmess.sh` / `hysteria2.sh` **同时在改**（不是我改的）。
  门禁只校验"这些文件的 diff 里没有本任务的标记"，输出为 `✓ conf/share.sh / share_client.py 的改动与本任务无关（另一个 agent 的）`。
* **`src/client/to_sb.py` 被两个任务同时改**（我在接 compat 闸门，另一个任务在改 vmess `ps`/`uuid`、`tls=reality`、`obfs=none`）。
  本次提交用**逐 hunk 暂存**只提交了我的部分（+106/-7 行），对方那 2 个 hunk（+31/-5）留在工作区未提交 → **提交内容不含对方代码**。
* `tools/` 目录两边都新建了脚本：我的 `tools/check_compat_wiring.sh`，对方的 `tools/check_share_links.sh`（未暂存、未提交）。
* 我在 `client.sh` 里**没有**碰 `conf/share.sh` / `share_client.py`；`conf/outbound_uri.py` 只被适配层**只读调用**（作为"面板侧旧判定"的参照，不参与合并）。
* **生产路径观察（不是我写的）**：实测期间 CC 的 `/opt/sb-client` 有过改动 —— `share-state/__pycache__/to_sb.cpython-312.pyc`（23:20:09）、
  `subscriptions.json` 与 `conf/90-outbounds.json`（23:24:02）。这两个时间点**早于本次实测的第一次运行**（本地日志 `cc-run.log` 起始 23:26），
  且本次实测全程 `CLIENT_ROOT=/tmp/sbc-verify/client`（沙箱已清理）→ 不是本次动作；同机另一个 agent 在生产客户端上测分享/订阅。
  本次实测**没有**在 `/opt/sb-client` 下写任何文件、没有重启任何服务（生产 PID 1444214 实测前后都在跑，etime 连续）。
  谁写的：**UNKNOWN**（只有时间线与沙箱隔离作证，无法从日志反查对方会话）。

---

## 9. 提交与推送

| 仓库 | 结果 |
|---|---|
| `sing-box-core` | ✅ 已推送：`7009d93` → `origin/main`（`c0a5c19..7009d93`）。仓库里**没有**任何一次提交包含另一个 agent 的代码（逐 hunk 暂存）。此后另一个 agent 又推了 `4fccbc6`/`fe47df8`/`406afcc`（conf/ 分享层 + `to_sb.py` 的 vmess/obfs 修正），`origin/main` 现为 `406afcc`；在这个最终 HEAD 上重跑门禁仍是 **通过 19 / 失败 0** |
| `proxy-node-compat`（本仓库） | ⚠️ **已提交、未推送**：`a9383ff`（只含本报告 + evidence，未动 `proxy_node_compat/**`）。推送被 GitHub 拒绝：`403 Permission to mi1314cat/proxy-node-compat.git denied to mi1314cat` —— 给的是一次性凭据, 只对 `sing-box-core` 有写权限。本仓库工作区里另有**在途未提交**改动（`engine.py`/`registry.py`/`rules.json` 的 mihomo `uri_rule(target_kernel)`），不是我的，未纳入本次提交 |

证据文件：`research/integration/evidence/sb-cc-run.log`、`evidence/sb-cc-out/`、`evidence/sb-harness/`（CC 验收台脚本，沙箱只在 `/tmp` 做事）。
