# compat 权威代码同步（副本 → canonical）+ 两处实测回灌 + 一条待入册缺口的复核

- 日期：2026-10-10
- 目标仓库（**唯一被写的仓库**）：`/root/deepseek/repos/proxy-node-compat/`
- 三个内核仓库 `xray--core` / `mihomo--core` / `sing-box-core`：**全程只读**（只读源码、只读副本、只读真机产物）
- 真机：`ssh rn`（racknerd-75e0e8，生产 mihomo **v1.19.32** pid **119320** 全程未动、`/root/catmi/*` 只读）
- 起点 commit：`f32531c`（父代理补推的 SB 接入报表）→ 终点 commit：见 §7
- 关联报告：`research/known-issues/x-hysteria-import-and-unlocated.md`（副本里的原始改动）、
  `research/integration/sb-client-integration.md`（SB 侧假 UNSUPPORTED 与 build tag 缺口）

---

## 0 · 结论一览

| # | 事项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 4 处副本改动搬进 canonical | ✅ **4/4 已同步**（rules.json ×2 行 + registry.py + engine.py），并逐字核对 | §1 |
| 2 | diff 时发现的其它差异 | 只有 1 处**无关差异**：`mihomo--core` 那份副本把证据里的真机 IP 脱敏成 `<CDN_IP>`；`sing-box-core` 那份与 canonical 完全一致。**没有别的语义差异需要搬** | §1.3 |
| 3 | 补 `uri.trojan.reality@mihomo` 同族缺口：mihomo 的 vless URI 不读 `encryption`/`flow` | ❌ **结论不成立（证伪）**：源码 + 上游单测 + 真机三组对照都指向"**读**"。**按任务约定：不新增 uri_rule**，只把"已证伪"作为证据行入库，防止以后有人再加这条假规则 | §3 |
| 4 | 回灌 A：`encryption=none` 哨兵值造成假 UNSUPPORTED | ✅ 修（`uri.py`）+ 8 组回归断言 + 反向验证 3 条失败 | §2.1 |
| 5 | 回灌 B：`hysteria2`/`tuic`/`naive` 的 `requires_build_tags` | ✅ hy2/tuic 补 `with_quic`（有现成规则）；⚠️ **naive 在 compat 里根本没有任何规则、也没有 naive 协议解析** → 新增一条**预留**的 `singbox.protocol.naive`（`with_naive_outbound`），见 §2.2 的重要说明 | §2.2 |
| 6 | 顺带发现并修：CLI 对认不出的 scheme 直接崩 | ✅ 修（白名单 → 泛化 `<scheme>://`），真链接 `naive+https://…` 从 `FileNotFoundError` 变成 UNKNOWN | §4 |
| 7 | 门禁 | **55 用例全绿**（起点 40 → +15），失败 0；三处修复各自做过反向验证 | §5 |

---

## 1 · 把副本的 4 处改动搬进权威代码

### 1.1 副本定位（报告 §2.5 的 ⚠️）

报告只写了"canonical 在 `proxy-node-compat/proxy_node_compat/`"，没写副本在哪。全仓搜索 `rules.json` 得到 4 份：

| 路径 | 与 canonical 的关系 |
|---|---|
| `/root/deepseek/repos/proxy-node-compat/proxy_node_compat/` | **权威（canonical）** |
| `/root/deepseek/repos/xray--core/Client/lib/proxy_node_compat/` | **本轮要搬的副本**（多 1 条 uri_rule + 1 条 evidence + 两处代码改动） |
| `/root/deepseek/repos/mihomo--core/src/lib/proxy_node_compat/` | 只差 1 处 IP 脱敏（§1.3） |
| `/root/deepseek/repos/sing-box-core/src/client/lib/proxy_node_compat/` | `diff -rq` 与 canonical **完全一致** |

### 1.2 搬了什么（4 处，逐字核对）

| # | 位置 | 改动 | 搬法 |
|---|---|---|---|
| 1 | `proxy_node_compat/data/rules.json` → `uri_rules` | 新增 `uri.trojan.reality@mihomo`（`target_kernel: mihomo` + `representation: NONE` + 逐字段 `loss` ×3 + `workaround` + `note` + `evidence`） | JSON 语义对象**逐字**取自带 target_kernel 的副本行 |
| 2 | `proxy_node_compat/data/rules.json` → `evidence` | 新增 `e-mihomo-trojan-uri-reality`（`type=BEHAVIOR`、`confidence=HIGH`，`how` 里含四个对照用例与源码位置，`limits` 写明版本边界） | 同上 |
| 3 | `proxy_node_compat/registry.py` | `uri_rule(scheme, feature, kernel=None)`：带 `target_kernel` 的行**只**对该内核返回；不给 kernel 时忽略它（不猜、不拿别家结论顶替）；全局行仍是回退 | 整函数逐字替换 |
| 4 | `proxy_node_compat/engine.py` | `_apply_uri_rules(profile, scheme, acc, registry, target)`：调用点传 `target`，取规则时传 `target.kernel` | 2 个 hunk 逐字替换 |

搬完的**逐字核对**（不是"看起来对"）：

```console
$ cd /root/deepseek/repos
$ diff -u proxy-node-compat/proxy_node_compat/registry.py xray--core/Client/lib/proxy_node_compat/registry.py && echo IDENTICAL
IDENTICAL
$ diff -u proxy-node-compat/proxy_node_compat/engine.py  xray--core/Client/lib/proxy_node_compat/engine.py  && echo IDENTICAL
IDENTICAL
$ python3 -c "…比较两份 rules.json…"
canonical counts: {'rules': 68, 'evidence': 29, 'uri_rules': 13}   # 68/29 = 本报告 §2 的两个回灌之后
vendored  counts: {'rules': 67, 'evidence': 27, 'uri_rules': 13}
vendored rules missing in canonical: []
uri_rules all present: True
evidence all present: True
```

> **格式说明（不是语义差异）**：副本里那两行是**手工插进** JSON 的，缩进是 1 空格/级、并且有一个孤立的
> `}` 换行 `,` 换行 `  {`。canonical 的 `rules.json` 经核对**逐字节等于** `json.dumps(..., indent=2, ensure_ascii=False) + "\n"`，
> 所以同步时按 canonical 自己的格式重新序列化（字符串值、键名、数组顺序全部逐字不变，`json.load` 后对象相等）。
> 没有整体覆盖文件：diff 显示只增加 2 个条目（`git diff --stat` = `rules.json | 90 +++…`）。

### 1.3 diff 时发现的其它差异（回答"期间有没有别的 agent 改过"）

1. `mihomo--core` 那份副本的 `rules.json` 与 canonical **只差一处**：
   证据 `e-xray-hysteria2-outbound` 的 `how` 里，真机 CF 出口 IP `104.28.195.192` 被改成了 `<CDN_IP>`（脱敏）。
   这是**另一路 agent 在 M 侧副本里做的脱敏**，不属于本轮 4 处语义 → **没有搬**（canonical 保留原 IP，与真机日志一致）。
2. `xray--core` 的 vendored 副本除这 4 处外**没有任何其它差异**（`diff` 只有 3 个 hunk：registry 1 个、engine 2 个）。
3. `sing-box-core` 的副本 `diff -rq` 全等 → 无内容可搬。
4. canonical 在被搬之前是 **26 evidence / 12 uri_rules**，与报告 §2.5 的记载一致；搬完 27/13。

### 1.4 任务要求的 CLI 验收（真实命令与输出）

```console
$ U='trojan://LV7CpzX9Jc8vWuhP0YV0@107.173.154.178:29602?security=reality&type=tcp&sni=audio-ssl.itunes.apple.com&fp=chrome&sid=b860a9f0&pbk=GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU#TROJAN-03'

$ python3 -m proxy_node_compat check "$U" --kernel xray --version 26.3.27
✅ SUPPORTED  [TROJAN-03]
   目标: xray 26.3.27
   分层: parse=UNKNOWN  config=SUPPORTED  uri=UNKNOWN  runtime=SUPPORTED  semantic=SUPPORTED
   ❓ 未知: 层级 uri（scheme=trojan） —— 没有覆盖该 scheme × feature 的 URI 表达力规则

$ python3 -m proxy_node_compat check "$U" --kernel mihomo --version 1.19.32
🟠 SUPPORTED_WITH_LOSS  [TROJAN-03]
   分层: parse=UNKNOWN  config=SUPPORTED  uri=SUPPORTED_WITH_LOSS  runtime=SUPPORTED  semantic=SUPPORTED
   🟠 损失: standard:reality.public_key —— mihomo 的 trojan 分支解析器不读 pbk → 拿不到公钥 [CONNECTIVITY] (uri.trojan.reality@mihomo)
   🟠 损失: standard:reality.short_id —— 同上不读 sid → 拿不到 shortId [CONNECTIVITY] (uri.trojan.reality@mihomo)
   🟠 损失: standard:reality.server_names —— sni 读得到, 但没有 reality-opts 时只按**裸 TLS** 拨号: … [CONNECTIVITY] (uri.trojan.reality@mihomo)

$ python3 -m proxy_node_compat check "$U" --kernel singbox --version 1.14.2 --build-tags with_utls
✅ SUPPORTED  [TROJAN-03]
   分层: parse=UNKNOWN  config=SUPPORTED  uri=UNKNOWN  runtime=SUPPORTED  semantic=SUPPORTED
   ❓ 未知: 层级 uri（scheme=trojan） —— 没有覆盖该 scheme × feature 的 URI 表达力规则
```

⇒ `xray` = `SUPPORTED`；`mihomo` = `SUPPORTED_WITH_LOSS` 且 **losses = 3 条**（全部指向 `uri.trojan.reality@mihomo`）；
换 `singbox` **不受影响**（uri 层仍是 UNKNOWN，losses 里没有这颗规则 —— 逐内核规则不外溢）。

---

## 2 · 两处实测回灌（SB 客户端接入）

### 2.1 假 UNSUPPORTED：`encryption=none` 是哨兵值，不是 VLESS Encryption

**根因**：`uri.py` 原来的条件是"`encryption` 非空就建 `standard:vless.encryption` feature"，
而 `encryption=none` 是分享链接规范 #716 里该字段的**必填默认值/哨兵值**（= 不做 VLESS Encryption）。
于是**每一条常规 vless 链接**都会撞上 sing-box 的 `singbox.vless.encryption.never` → 假 UNSUPPORTED。

**修法**（`proxy_node_compat/uri.py`）：

- 建 feature 的条件加一条：`str(enc_value).strip().lower() != "none"`（大小写不敏感；`none2` / `aes-128-gcm` /
  `mlkem768x25519plus…` 仍照旧建 feature）。`encryption` 本来就在 `consumed` 里，所以哨兵值不会掉进 `extensions`。
- `generate_uri` 配套：哨兵值不建 feature 后，回写会**静默丢参数** → 补一条"没有 feature 携带 `encryption`
  时按 `raw_fields` 原值回写"，保持"用户显式写过的参数不丢"。

**真机链接验收**（RN 上 SB 产物 `sb_share-*.txt`，就是报告里被判死的那两条）：

```console
$ L1=$(ssh rn cat /root/catmi/sing-box/out/sb_share-vless01-TLS-CDN.txt)   # ?encryption=none&security=tls&type=ws…
$ L2=$(ssh rn cat /root/catmi/sing-box/out/sb_share-reality01-REALITY.txt) # ?encryption=none&security=reality…&flow=xtls-rprx-vision

# 修前（把条件退回原样）：
❌ UNSUPPORTED  [🇺🇸 rn vless01-TLS-CDN]      原因码: KERNEL_NEVER_SUPPORTED
# 修后：
✅ SUPPORTED    [🇺🇸 rn vless01-TLS-CDN]
```

**真 VLESS Encryption 没有被放松**（同一条命令，只换 `encryption` 取值）：

```console
$ python3 -m proxy_node_compat check "vless://u@h:443?encryption=mlkem768x25519plus.native.0rtt.ABC&security=tls&type=ws&path=/x" \
      --kernel singbox --version 1.14.2 --build-tags with_utls
❌ UNSUPPORTED  原因码: KERNEL_NEVER_SUPPORTED        # sing-box 完全没有该特性（保持原判）
（同一链接 xray 26.3.27 → SUPPORTED；mihomo 1.19.32 → SUPPORTED_WITH_WARNING；`aes-128-gcm` 同样按真特性判）
```

### 2.2 `requires_build_tags`：hysteria2 / tuic（+ naive 的实情）

**缺口复现**（修前）：

```console
hysteria2://pw@h:443?sni=a.com   tags=[]             status=SUPPORTED   ← 假 SUPPORTED：该构建根本没有 with_quic
tuic://u:p@h:443?sni=a.com       tags=[]             status=SUPPORTED   ← 同上
vless://u@h:443?security=reality… tags=[]            status=UNSUPPORTED reasons=['BUILD_NOT_ENABLED']  ← 机制本身是有效的
```

**修法**：`singbox.protocol.hysteria2` / `singbox.protocol.tuic` 的 segment 加 `requires_build_tags`，
并新增证据行 `e-singbox-buildtags-quic-naive`（源码门控 + CC 真机 tag 清单 + 反向验证）。修后：

```console
$ python3 -m proxy_node_compat check "hysteria2://pw@h:443?sni=a.com" --kernel singbox --version 1.14.2 --build-tags with_utls
❌ UNSUPPORTED  原因码: BUILD_NOT_ENABLED   说明: singbox.protocol.hysteria2: 该构建缺少 ['with_quic']
$ … --build-tags with_utls,with_quic
✅ SUPPORTED
$ …（不给 --build-tags）
✅ SUPPORTED + ❓ 未知: singbox.protocol.hysteria2: build tags —— 未提供 build_tags, 无法判断可选依赖是否编入
```

⇒ **tags 缺失（未知）不判 BUILD_NOT_ENABLED**，只记 UNKNOWN 条目；`tags=[]`（确定没有）才判死。
这与既有的 `singbox.reality.build_tags`（`with_utls`）**逐字一致**（现成测试 `test_unknown_build_stays_unknown_but_siblings_still_resolve`
钉的就是"config 仍 SUPPORTED + unknowns 里有 build 条目"），没有改动 engine 语义。

> ⚠️ **naive 的实情（与任务描述不同，必须说明）**：
> compat 里**没有 naive 的任何规则，也没有 naive 协议解析** —— `grep -ic naive proxy_node_compat/*.py` = **0**，
> `rules.json` 里 naive 出现 **0 次**。真机链接 `naive+https://…@107.173.154.178:31008?sni=…`（RN 的
> `sb_share-naive01-TLS.txt`）走的是 `unknown:naive+https` → 判 **UNKNOWN**（不是假 SUPPORTED）。
> 所以"naive 的规则缺 requires_build_tags"这条**没有可补的现成规则**。
> 我的处理：**新增**一条 `singbox.protocol.naive`（selector `protocol=standard:naive`、
> verdict SUPPORTED、`requires_build_tags: ["with_naive_outbound"]`、证据同上），并在规则里写了
> `message`：compat 今天匹配不到它（是**预留的 tag 约束**）；要让 it 生效需要另开一轮补 naive 协议支持
> （scheme 表 + 三内核规则），那会改变判定（UNKNOWN → SUPPORTED），**不在本轮边界内**。

---

## 3 · "mihomo 的 vless URI 路径不读 `encryption`/`flow`" —— 复核结论：**不成立**

### 3.1 源码证据（决定性）

| 位置（本地快照 `/tmp/xsrc/mihomo`，tag v1.19.32） | 事实 |
|---|---|
| `common/convert/converter.go:222-243` `case "vless"` | 先 `handleVShareLink(...)`，**紧接着**读 `query.Get("flow")` → `vless["flow"]`、读 `query.Get("encryption")` → `vless["encryption"]` |
| 本机快照 vs `raw.githubusercontent.com/MetaCubeX/mihomo/v1.19.32/.../converter.go` | `diff` **空**（逐字相同，工作树干净、`git tag --points-at HEAD` = v1.19.32，blame 指向上游提交 `88dcbf7`） |
| 上游同 tag 单测 `common/convert/converter_test.go:181-189` | 输入一条带 `encryption=none&…&flow=xtls-rprx-vision` 的链接，断言 `proxies[0]["flow"]=="xtls-rprx-vision"`、`proxies[0]["encryption"]=="none"` |
| 对照：`handleVShareLink`（v.go）读的是 pbk/sid/fp/alpn/sni/type/… —— 不读 encryption/flow，所以这两行必须在 `case "vless"` 里补 | 与第 1 行合起来看，vless 是**两处都读**；trojan 分支才是"从不读 pbk/sid"（本轮同步的那条规则） |

### 3.2 真机证据（`ssh rn`，生产 mihomo v1.19.32 二进制，独立实例 `-d /tmp/mhv*`）

语料：RN 上**项目自己生成**的真实链接与产物 —— `out/reality-share-01.txt` 与 `out/reality-client-01.yaml`
（同一节点：REALITY-01，uuid/pbk/sid/servername/**encryption(1610 字符)**/flow **逐字段比对完全相同**，
`diff` 过的字段一致性检查输出 `same=True` ×5）。目标改写成本机回环 `127.0.0.1:50330`（= RN 自己的 REALITY-01 inbound），
排除网络路径（这是上一轮 trojan 实验 A2 的手法）。

| 用例 | 配置形态 | delay | curl | 日志 |
|---|---|---|---|---|
| **B** | 项目自带 `reality-client-01.yaml`（显式 `flow` + `encryption`） | `{"Reality-01":240}` | **204** | 18 行 `XTLS Vision …` |
| **A** | **同一条链接**经 `proxy-provider`（= URI 解析通道） | `{"Reality-01":146}` / `204` / `231` | **204** | 17–18 行 `XTLS Vision …` |
| **C** | A 的链接**删掉 `flow`** | all timeout | **000** | 0 行 Vision |
| **D** | A 的链接**删掉 `encryption`** | all timeout | **000** | 3 行（握手后无响应） |
| **E** | A 的链接**两者都删** | all timeout | **000** | 0 行 |

⇒ A 与 B **等价**（都 204、都进 XTLS Vision），C/D/E 说明这两个字段**确实被这条 URI 通道使用**（删了就断）。

**转发对照（证明字段真的进了配置，而不是"看起来在读"）**：

```
链接写 encryption=deadbeef-not-a-real-encryption-value
  → mihomo: initial proxy provider P error: proxy 0 error: invaild vless encryption value: deadbeef-not-a-real-encryption-value
链接写 flow=zzzzzzzzzzzzzzzzzz
  → mihomo: initial proxy provider P error: proxy 0 error: unsupported xtls flow type: zzzzzzzzzzzzzzzz
```

（两条都是 mihomo 拿着**链接里的原值**去构造 outbound 时报的错 ⇒ 解析路径没有丢弃它们。）

**同一实例内的 A/B 对照**（排除实例差异）：provider(链接) 与 inline(YAML) 的 `/proxies` 标志逐字相同
（`type=Vless, udp/uot/xudp 均 true`），provider 通道单独测时也是 204。

### 3.3 为什么上一轮会得出相反结论（含我自己的一个方法论坑）

1. 上一轮报告 §6 UNKNOWN 3 写的是"用例 D（vless+REALITY 经 URI）拿不到 204，**因为**该服务端要 VLESS-Encryption
   而 mihomo 的 vless URI 分支不读 `encryption`/`flow`" —— 但源码/单测/真机三路都显示**读**。
   D 当时失败的**真实原因没有复现、也没有定位**（见 §8 UNKNOWN 1）。
2. 一个相关的坑（我第一次实验也踩了，如实记录）：把链接地址改写成回环时用
   `urlunsplit((scheme, "127.0.0.1:50330", …))` 会**连 userinfo（uuid）一起丢掉** →
   `vless://127.0.0.1:50330?flow=…`，于是"链接全失败、YAML 全成功"，看着就像"URI 丢了字段"。
   发现方式是看 provider 侧 JSON 全等、而失败日志停在 `REALITY Authentication: true` 之后（= 服务端拒了 VLESS 层），
   再用 od 看链接文件头 `v l e s s : / / 1 2 7 . 0 . 0 . 1 : 5 0 3 3 0 ?` 才发现 uuid 没了。
   **任何"链接 vs YAML"对照都必须先核对链接自身的字段完整性**。
3. 另一个已排除的解释：`handleVShareLink` 在没有 `packetEncoding` 时会设 `xudp: true`。
   实测 YAML 里 `xudp` 默认**也是** true，且显式加 `xudp: true` 仍 204 ⇒ 不是它。
   （`port` 在链接里是字符串、YAML 里是整数：实测字符串端口同样 204 ⇒ 也不是它。）

### 3.4 处置

- **不新增 `uri_rules` 行**（按任务约定：不成立就写报告说明）。
- 新增**证据行** `e-mihomo-vless-uri-encryption-flow`（`type=RUNTIME_TEST`、`confidence=HIGH`，
  `how` 里带全部用例、命令与报错原文；`limits` 写明版本与形态边界），挂到既有的全局规则
  `uri.vless.encryption` 上 —— 让"M 侧读到同一份事实"时**不会再有人按错误结论加一条逐内核规则**。

---

## 4 · 顺带修的一处：CLI 把认不出的 scheme 当文件路径 → 崩

复现（真链接，来自 RN 的 `sb_share-naive01-TLS.txt`）：

```console
$ python3 -m proxy_node_compat check 'naive+https://e53bd040a419:f695c3946d09@107.173.154.178:31008?sni=…' --kernel singbox --version 1.14.2
FileNotFoundError: [Errno 2] No such file or directory: 'naive+https://…'
```

`cli._load` 原来是一张**硬编码 scheme 白名单**，白名单外的链接一律当文件打开 → 整批检查直接崩
（库层一直是对的：`parse_uri` → `unknown:naive+https` → UNKNOWN，绝不假 SUPPORTED）。
改成泛化 `<scheme>://` 正则后：

```console
❓ UNKNOWN  [rn]
   分层: parse=UNKNOWN  config=UNKNOWN  uri=UNKNOWN  runtime=UNKNOWN  semantic=UNKNOWN
   ❓ 未知: singbox × ['unknown:naive+https'] —— 注册表里没有覆盖该组合的规则
```

---

## 5 · 门禁

```console
$ python3 -m unittest discover -s tests
.......................................................
Ran 55 tests in 0.040s
OK
```

起点 40 → **55**（新增 15：逐内核 uri_rule 5、encryption 哨兵值 5、build tag 门控 3、CLI 入口 2）。

**反向验证**（把每处修复单独退回"修前"，跑同一套门禁）：

| 退回的修复 | 失败用例 |
|---|---|
| `uri.py` 哨兵值条件退回原样 | `TestVlessEncryptionSentinel` **3 失败**（feature 被建出来 / `NONE` 大小写 / 假 UNSUPPORTED） |
| 抽掉三处 `requires_build_tags`（并删 naive 规则） | `TestSingboxBuildTagRequirements` **2 失败 + 1 错误** |
| `cli.py` 退回硬编码白名单 | `TestCliLoadUnknownScheme` **1 错误**（FileNotFoundError） |

⇒ 15 条新断言都真的在钉东西，不是"检查根本没跑却全绿"。

---

## 6 · 边界与清理

- **只写** `/root/deepseek/repos/proxy-node-compat/`；`xray--core` / `mihomo--core` / `sing-box-core` 全程只读
  （读副本、读 `/tmp/xsrc/*` 源码快照、读真机产物）。
- **没有写任何生产路径**：RN 上只在 `/tmp/mhv*`（已 `rm -rf`，`ls` 复查为空）；`/root/catmi/*` 全程
  `cat/ls/grep/stat/python3 -c json.load` 只读。
- 本机只在仓库工作树 + `/tmp/work`（已删）。`/tmp/xsrc/*` 是上一轮的内核源码快照，**非本轮创建、未删**。
- 未重启任何服务、未改任何 systemd 单元。跑完复查 RN：`xrayls`/`mihomo`/`sing-box` 全 `active`，
  **生产 mihomo pid 119320 未动**（`ps` 11:28:25 的 etime），`/root/catmi/mihomo/conf` mtime 仍是 10-09 02:27。
- 测试实例全部退出（`ps | grep "mihomo -d /tmp/mhv"` = 空）。

---

## 7 · 变更与 commit

| 文件 | 变更 |
|---|---|
| `proxy_node_compat/data/rules.json` | +`uri.trojan.reality@mihomo`、+`e-mihomo-trojan-uri-reality`、+`e-mihomo-vless-uri-encryption-flow`、+`e-singbox-buildtags-quic-naive`、+`singbox.protocol.naive`、hy2/tuic 补 `requires_build_tags`（67→68 rules，26→29 evidence） |
| `proxy_node_compat/registry.py` | `uri_rule(..., kernel=None)`（逐内核行不外溢） |
| `proxy_node_compat/engine.py` | `_apply_uri_rules(..., target)` 传 `target.kernel` |
| `proxy_node_compat/uri.py` | `encryption=none` 哨兵值不建 feature；`generate_uri` 逐字回写它 |
| `proxy_node_compat/cli.py` | `_load` 泛化 `<scheme>://`（不再把未知 scheme 当文件路径） |
| `tests/test_all.py` | +15 条断言（4 个新测试类） |
| `research/known-issues/compat-canonical-sync.md` | 本报告 |

起点 `f32531c` → **内容 commit：`0f973fe`**（同步 4 处 + 两处回灌 + CLI 修复 + 新增 15 条门禁）
→ **本报告 commit：紧随 `0f973fe` 之后**（`git log -1 --format='%h %s' -- research/known-issues/compat-canonical-sync.md` 可查）。

---

## 8 · UNKNOWN

1. **上一轮用例 D 的 000 真实原因**：源码/单测/真机都显示 mihomo 读 `encryption`+`flow` ⇒ D 的失败不是这个原因；
   本轮没有复现当时的失败（我这轮同样形态的链接是 204）。可疑方向（**未验证**）：当时链接走的公布地址
   `104.28.201.80:27474/50330` —— 我实测该公布地址上**连等价的 YAML 也连不通**（回环才通），
   但那是 node 03 的一次观测，且 CF/Spectrum 回源映射不在本轮边界内 ⇒ UNKNOWN。
2. mihomo **v1.20+** 是否改了这段：未验证（只核了 v1.19.32 与当前 Meta 分支该段逐字相同）。
3. `vmess://` 的 URI 路径是否读 `flow`/`encryption`：本轮**没测**（`case "vmess"` 里 `encryption` 被映射成 `cipher`，
   与 vless 不是同一语义）⇒ 不写结论。
4. `with_quic` / `with_naive_outbound` 的规则来自**源码门控 + stub 报错文本**，没有缺这两个 tag 的真实内核二进制可测
   （CC 有 go1.22 但无上游 sing-box 源码，不能自编译反证）⇒ 不是端到端实测（已写进证据行 `limits`）。
5. naive 协议**完整支持**（`naive+https` scheme 表 + 三内核规则 + `standard:naive` 的 URI 表达力）未做：
   本轮只钉了 tag 约束；它今天匹配不到任何输入（§2.2）。
6. `port` 在 links 里是字符串、YAML 里是整数这一差异**不影响**本轮任何结论（实测字符串端口 204），
   但"mihomo 是否对别的字段也弱类型"未系统验证。
