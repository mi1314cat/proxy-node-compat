# SB 客户端 `to_sb.py` 三条实测缺口 · 修复与真机验收

> 日期：2026-10-11 ｜ 对象：`sing-box-core` 客户端转换器 `src/client/to_sb.py`（**只改这一个仓**）
> 触发：跨内核九宫格 **M → SB** 那一格（`research/e2e/three-servers-three-clients.md` §3.2/§4、
> `research/deploy/rn-reconcile-and-deploy.md` §5.3）从"崩溃 0 导入"变成"导入 18/19、真连 0/18"。
> 判定层：vendored `proxy-node-compat@9b73cc9` + 适配层 `src/client/compat2.py`（**本次一行未改**）。

## 0. 一句话结论

三条缺口全部按 **compat 的结论**修掉，真机 A/B（同一台 CC、同一份 RN 上 M 的真实分享载荷、
同一个 sing-box 1.14.2 内核）：

| | 导入数 | 整份 `sing-box check` | **真连**（curl 204 **且** 出口 IP = RN 的 CF 出口 104.28.x.x） |
|---|---|---|---|
| 改前（HEAD `2c209b0`） | 19 → **18** | **rc=1**（`FATAL initialize outbound[0]: TLS required`） | **0 / 18** |
| 改后 | 19 → **15**（3 条 xhttp 按 compat 判死，不再假装 tcp） | **rc=0** | **13 / 15** |

门禁 `bash tools/check_compat_wiring.sh`：**通过 22 / 失败 0**（改前 19/0；新增的三条缺口断言各自计数）。
本地 commit，**未推 GitHub**。

---

## 1. 三条缺口的根因 / 改法 / 验证

### 缺口① `tls` 块缺 `"enabled": true`（M→SB 真连 0/18 的直接原因）

**根因（代码级）**：`clash_to_outbound()` 从 `sni/alpn/utls/reality-opts` 拼出 `tls` 字典，
**从头到尾没写过 `enabled`**；`_vmess_uri()` 里 `alpn`/`fp` 也在 TLS 开关之外，会造出
"有 tls 段、但没有 enabled"的出站。sing-box 的 TLS 选项默认**关**：

| 协议 | 内核行为（实测 sing-box 1.14.2 linux/amd64） |
|---|---|
| anytls / tuic / hysteria2 | `FATAL initialize outbound[0]: TLS required` —— 连 `check` 都过不去，**一条就废掉整批** |
| vless / trojan | tls 段被**无声忽略**（`check` rc=0），明文去连 → 502 / 000 / reality 握手 panic |

这与 §5.3 的实测归因逐条对上：`TLS required` = anytls×3 + tuic×1（+hy2），`panic: nil pointer`
= vless/trojan REALITY×5，其余 = 明文连出去被 CDN 400/503。**同一批节点在 mihomo 侧 14/19 可用**
⇒ 是 SB 客户端自己的缺陷。

**改法**：只要写出 `tls` 段，就**第一件事**写 `"enabled": true`（clash 侧 + vmess 侧各一处）；
`alpn`/`utls` 收进"TLS 已开"分支里，不再出现"没有 enabled 的 tls 段"。
行内注释写明了为什么（避免以后又被"优化"掉）。

**验证**：
- 改后 M 分享 15 条出站**全部** `tls.enabled=true`（0 条例外）；整份 16 出站 `sing-box check` **rc=0**（改前 rc=1）。
- 真连：`mAnyTLS01/02/03`、`mVLESS01-REALITY`、`mVLESS02-REALITY-gRPC`、`mTrojan01/02/03`、
  `mTrojan04-CDN-WS`、`mVLESS04-CDN-WS`、`mVLESS01-TLS-WS` = **204 + 出口 104.28.201.80**。

### 缺口② 丢 `xhttp` 传输 / **静默降级成 tcp**

**根因（两处，且 mihomo 路径才是活的坑）**：
1. `transport_from_clash()` 对**任何**不认识的 `network` 返回 `None` → 调用方不写 `transport` 段
   → 内核按默认 tcp 跑。URI 路径 `_std_uri()` 的 `if net in (ws/grpc/h2)` 链同样"落到 else 就当 tcp"。
2. **compat 闸门看不出这件事**：mihomo YAML 没有分享原文，`judge(outbound=…)` 拿到的出站里
   传输已经没了，compat 只能看到 `standard:transport.tcp (DEFAULTED)` → 判 SUPPORTED → 节点被"成功导入"。
   实测改前 M 分享的 3 条 xhttp 节点（`mVLESS03-REALITY-XHTTP`、`mVLESS02-TLS-XHTTP`、
   `mVLESS03-TLS-XHTTP-CDN`）产物就是 `"transport": null`，真连 000/panic；
   其中 `mVLESS02-TLS-XHTTP` 在 **mihomo 侧是通的** —— 一条本来可用的节点被 SB 静默变成废节点。
3. 附带同类：mihomo **没有** `network: httpupgrade`，它写成 `network: ws` + `ws-opts.v2ray-http-upgrade: true`
   （本仓 `src/conf/to_mihomo.py:258` 就是生产者）。旧代码只读 `network` → 把 httpupgrade **静默读成 ws**。

**改法（判定仍然只走 compat，to_sb 只负责"按结论构造或明确拒绝"）**：
- `transport_from_clash()` / `_std_uri()` / `_vmess_uri()` 改成三态：**写得出** / **显式 tcp**（不写 transport 段，
  语义等价）/ **写不出**（在出站 dict 上打内部标记 `_sb_unwritable_transport`，**绝不**写进配置）。
- `_keep()` 变成两道闸门：
  1. **转换闸门**（转换器的表达能力，不是内核能力）：带标记的节点直接不让进配置；
  2. **compat 闸门**（内核能力）：有原文链接时用原文判（原文是权威）；没有原文（mihomo/JSON）时，
     把链接里**真实的**传输写进一份**只为判定**的副本交给 compat —— 它绝不进配置。
- 于是：`xhttp` / `kcp` 走 compat 规则 `singbox.xhttp.never` / `singbox.mkcp.never`（`KERNEL_NEVER_SUPPORTED`），
  跳过理由用 compat 自己的文案（含"本内核可用: …"）；`httpupgrade`（含 mihomo 的 ws 编码形态）
  compat 判 SUPPORTED，但本转换器不会写 → **明确拒绝**，理由里写清"这是转换器不写，不是内核不支持"。
- **绝不硬造 transport**：实测 `{"type":"xhttp"}` 会让内核
  `FATAL decode config: outbounds[0].transport: unknown transport type: xhttp` —— 整份配置作废。

**验证**：
- 改后 M 分享：3 条 xhttp 全部不进配置，跳过理由 = `compat[KERNEL_NEVER_SUPPORTED…] 不支持的传输方式 type='xhttp'（…）`；
  没有出现 `"transport": null` 冒充 tcp 的节点。
- X 分享（`p-x.decoded.txt`，5 条）：`vless-xhttp07` 按 compat 判死（与改前一致，URI 路径早就靠 compat 拦住了）；
  `xhttp08`（ws）原样保留 —— 没有连带误伤。
- 内核探针（证据）：`xhttp`/`foobar` → `unknown transport type`（rc=1）；`ws/grpc/http/httpupgrade` → rc=0。

### 缺口③ 丢 `ech`（且绝不允许写一个内核会 FATAL 的值）

**根因**：转换器**完全没有**看 `ech`（URI 参数）/ `ech-opts`（mihomo）→ ECH 静默消失，报告里也没有记录。

**语义与内核约束（实测）**：
- X 侧链接与 mihomo 的形态都是"**运行时去查 DNS** 取 ECHConfig"：
  `ech=cloudflare-ech.com+https://dns.alidns.com/dns-query`（X 的 ECH 查询语法，见 `xray--core/Client/lib/echcli.py`）、
  `ech-opts: {enable: true, query-server-name: …}`。
- sing-box 的 `tls.ech.config` **只吃静态 PEM**（`-----BEGIN ECH CONFIGS-----`）。实测
  base64 → `FATAL initialize outbound[0]: invalid ECH configs pem`（**整份配置作废**）；PEM → rc=0。
- `to_sb.py` 的设计约束就是**不联网**（模块 docstring），转换期不可能去解析 HTTPS/SVCB 记录。

**改法**：能正确转换的（源值本身已经是 PEM）原样写成 `tls.ech = {enabled: true, config: <PEM>}`；
其余一律**不写** `tls.ech`，并且**显式声明不可用**：
- URI 路径：compat 自己的"原文 vs 出站"损失对比会报 `standard:ech`（已有机制，实测有输出）；
- mihomo 路径：没有原文 → to_sb 把忠实的 `ech` 标记放进"只为判定"的副本，让 compat 判 `standard:ech`
  （1.14.2 判 `SUPPORTED_WITH_LOSS`、1.14.1 判 UNKNOWN），再把一条 `standard:ech` 的**转换损失**
  挂到该节点记录上（client.sh 的摘要会以 ⚠ 打印），文案说明"该节点 ECH 未启用；若它必须靠 ECH 才能连通，
  表现就是连不上"。

**验证**：M 分享 5 条带 `ech-opts` 的节点全部被**声明**（4 条保留节点 + 1 条因 xhttp 被拒）；
产出里**没有任何** `ech` 键（`tls` 键集合 = alpn/enabled/insecure/reality/server_name/utls）；
门禁断言"绝不写非 PEM 值 + 必须声明"。

---

## 2. 真机验收（用户点名的口径：导入数 + 真连数 + 出口 IP）

**载荷**：`proxy-node-compat/research/e2e/evidence/3x3/payloads/p-m-surrogate.yaml`
（6312 B / sha256 `08d847fe…` / 19 节点，**与九宫格 M→SB 那一格用的是同一份** RN 上 M 的真实分享载荷）。
**内核**：`sing-box 1.14.2`（linux/amd64，取自 RN `/root/catmi/sing-box/sing-box`，sha256 `fc9c6e6a…`；
CC 用本机 `/opt/sb-client/core/sing-box` 1.14.2 aarch64）。
**方式**：逐节点起隔离实例（`mixed` 入站 → 该出站），`curl http://www.gstatic.com/generate_204`
与 `https://api.ipify.org`；**204 单独不算成功，出口 IP 必须是 104.28.x.x**。

| 机器 | 改前 | 改后 |
|---|---|---|
| **CC**（192.168.1.178，参考客户端机） | 导入 18 ｜ check rc=1 ｜ **真连 0/18** | 导入 15 ｜ check rc=0 ｜ **真连 13/15** |
| xiaomi（本机，客户端） | 导入 18 ｜ check rc=1 ｜ **真连 0/18** | 导入 15 ｜ check rc=0 ｜ 真连 11/15 |

出口 IP 全部为 `104.28.201.80`（RN 的 CF 出口）；改前 18 条的失败原因：`TLS required`×5（anytls×3 + hy2 + tuic）、
tls 段被无声忽略后裸连 → 000 / reality 握手 panic ×6、明文连出去被 CDN 400/503 ×7 —— 全部由缺口①派生。

**改后 CC 的 2 条失败（归因：服务端/CDN 侧，不是转换器）**：
`mTrojan05-CDN-gRPC`、`mVLESS05-CDN-gRPC` → CDN 返回 `403 Forbidden` / `GOAWAY`；
这两条在 **mihomo 侧基线里同样是 FAIL（delay=0）**，且它们正是"带 ech-opts 的 CDN gRPC"节点。

**本机（xiaomi）多出的 2 条失败（归因：本机网络环境）**：`mHysteria201-TLS`、`mTUIC01-TLS`
报 `quic: transport closed: invalid IPTOS size` —— 同一份改后配置**在 CC 上 2/2 真连成功**
（204 + 104.28.201.80），本机有 TUN（`198.18.0.1`）⇒ 环境问题，与转换器无关。

> 复现：`python3 realconn.py pre-outbounds.json / post-outbounds.json`（脚本与原始结果见 §6）。

---

## 3. 消除掉的"静默降级"路径（本次的硬要求）

| 源里的东西 | 改前 | 改后 |
|---|---|---|
| `network: xhttp`（mihomo）/ `type=xhttp`（URI） | 静默成 tcp（mihomo 路径连 compat 都看不出来） | compat 判 `KERNEL_NEVER_SUPPORTED` → 不进配置 + compat 文案 |
| `type=kcp` | 静默成 tcp | 同上（`singbox.mkcp.never`） |
| `type=httpupgrade`（URI）/ `network: ws`+`v2ray-http-upgrade`（mihomo） | 静默成 tcp / 静默读成 ws | **明确拒绝**：理由点名"本转换器不会写 httpupgrade（compat 判定=SUPPORTED，是转换器不写，不是内核不支持）" |
| 任何没见过的传输名 | 静默成 tcp | 明确拒绝（理由含 compat 判定；写进配置会被内核整单拒绝，实测 `unknown transport type`） |
| 链接里有 `ech` / `ech-opts` | 静默丢弃，报告无记录 | 不写非 PEM 值 + 报告里一条 `standard:ech` 转换损失（保留节点） |
| 内部标记 | —— | `_sb_*` 键被 `_keep` 取走，`main()` 再兜一道剥离；门禁断言不许漏进配置 |

输出里**不允许**出现"链接说是 A、配置写成 B"的传输：唯一允许的等价是"显式 tcp/raw/空 → 不写 transport 段"。

## 4. 判定分工与回滚

- **判定只在 compat**：`to_sb.py` 不写任何能力规则。`xhttp` 的拒绝文案、`httpupgrade` 的"内核支持"
  结论、`ech` 的 `SUPPORTED_WITH_LOSS`、reason_code 全部来自 `compat2.judge()`（vendored `9b73cc9`）。
  to_sb 新增的只有两件**转换器事实**：① 这个传输我写不出来；② ECH 我写不成 PEM。
- **一键回滚 `SB_COMPAT_ENGINE=legacy`（语义保持）**：不跑 compat，verdict 回到旧判定
  （门禁 §5 的回滚断言依旧通过：xhttp 链接在 legacy 下 `verdict=SUPPORTED`）。
  **一处有意保留的差异**：回滚**不恢复"静默降级成 tcp"** —— 那是本次要修的缺陷而不是一种行为。
  legacy 下实测 M 分享仍是 15 条（3 条 xhttp 被拒，理由标注 `compat 判定=（compat 未接入）`）。
  `SB_COMPAT_DISABLE=1` / compat2 缺失或异常 → 同样：判定落回旧路径，三条转换级修复仍然生效。

## 5. 门禁（`tools/check_compat_wiring.sh`）

- 改前 **19/0** → 改后 **22/0**，新增三条**各自计数**的断言（§6b）：
  1. 缺口① "产出的 tls 段一律带 enabled: true"（同时要求整份产出被真内核 `check` 接受）；
  2. 缺口② "xhttp 明确拒绝, 不静默降级成 tcp"（含 reason_code 与文案点名；另覆盖 mihomo 的
     `network: ws + v2ray-http-upgrade` 形态不许被静默读成 ws）；
  3. 缺口③ "ECH 不写非 PEM 值, 且显式声明不可用"（mihomo 形态 + URI 形态各一条用例）。
- 夹具是自带的 mihomo YAML（anytls/hy2/tuic/trojan-tls/vless-reality/vless-xhttp/httpupgrade-as-ws[/ech]），
  不依赖仓库外的文件；没有 PyYAML 时自动降级（嵌套 `ech-opts` 用例跳过，由 URI 用例覆盖）。
- **§6 期望值更新（须复核）**：原来断言 `tags=gate-wsenone,gate-hu`（即 httpupgrade 节点被保留、
  但静默降级成 tcp）。按"不许静默降级"的要求，httpupgrade 现在被**明确拒绝**，期望值改为
  `tags=gate-wsenone`，并新增"它必须 ok=False 且理由点名 httpupgrade"。这是本次唯一一处
  对既有断言的**语义修改**（其余断言只增不改）。

## 6. 证据与复现

| 内容 | 位置 |
|---|---|
| 改前/改后产物 + compat 报告 | `/tmp/sbgap/evidence/{pre,post}-outbounds.json`、`{pre,post}-report.json`（临时目录，验收后清理） |
| 改前/改后真连逐节点结果（CC / xiaomi） | `/tmp/sbgap/evidence/{pre,post}-realconn.json`、CC `/tmp/cc-sbgap/{cc-pre,cc-post}.res` |
| 内核探针（xhttp/未知名/FATAL、ECH base64 vs PEM） | `/tmp/sbgap/evidence/{tr-xhttp,tr-foobar,ech-b64,ech-pem}.json` |
| 复现命令 | `python3 to_sb.py <payload> --prefix e2e --compat-report r.json`；`bash tools/check_compat_wiring.sh` |

## 7. 纪律与边界

- 只改 `sing-box-core`：`src/client/to_sb.py`、`tools/check_compat_wiring.sh`。
  `xray--core` / `mihomo--core` 只读（读了 X 的 `echcli.py` 与 M 的 `nodecompat.py` 作为语义依据）。
- **未写任何生产路径**：客户端机器上用 `/tmp/sbgap`（xiaomi）/`/tmp/cc-sbgap`（CC）；
  RN 只做只读（`scp` 取内核二进制、读 share 记录），未跑任何生产生成脚本、**未重启任何服务**。
- vendored compat 与 `compat2.py` **一行未改**（门禁 §2 逐字节比对通过）。
- 本地 commit，**未 push**。

## 8. UNKNOWN / 后续（没验证的不写成已验证）

1. **httpupgrade 只"拒绝"不"写出来"**：内核实测接受 `{"type":"httpupgrade","path":…,"host":…}`
   （`check` rc=0），但 RN 上**没有活的 httpupgrade 节点**（运行配置里 0 处），无法做端到端真连验证
   ⇒ 本次不做映射，改为明确拒绝。要支持的话是"加 8 行映射 + 一条真机用例"。
2. **带 ECH 的 CDN gRPC 节点为什么 403**：mihomo 侧（真正带 ech-opts）也连不上，
   所以**不是**"我们不传 ECH"造成的；是否必须 ECH 才能连通，仍未定论（与 §5-① UNKNOWN 一致）。
3. **M 服务端脏值 `up: 50 Mbps`**（`mHysteria202-TLS`）仍被跳过，跳过文案是旧的
   "不支持的 clash type: hysteria2"（有误导，属另一条线，未动）。
4. **本机 QUIC `invalid IPTOS size`**：只在本机（有 TUN）复现，CC 上 2/2 通过 ⇒ 判环境问题；
   没有进一步定位到具体 TUN/内核参数。
