# 三家互通 · M 侧实施与真机验收报告

> ---
>
> ## ⚠ 部署状态更正（2026-10-11 复核）
>
> 1. 本报告的"真机验收"跑在 **RN/CC 上的隔离副本**里，不是 RN 的生产部署路径。
>    复核证据：`src/lib/interop.py` 与 `src/share/build_uri.py` 当时在 RN 上
>    **不存在**（`find /root -name build_uri.py` 返回空），`/root/catmi/mihomo/src/`
>    的内容与时间戳都停在上一轮对账分发的 `54672782`（2026-10-10 08:58 PDT）。
>    报告 §8 自己也写了"未写生产路径"。
> 2. 测试用的那条带声明分享确实是**真公共服务 `:9443`** 发的（代码路径真跑过），
>    所以结论对**代码 + 真服务**成立；对「**已部署**」不成立。
>
> 3. 本轮已把仓库 HEAD 逐字节分发到 RN 并在**部署态**重跑验收 —— 见 `three-way-interop-m-deployed.md`。


> 日期：2026-10-11 ｜ 实施对象：`mihomo--core`（服务端 `src/share/` + 客户端 `src/client.sh`）
> 设计依据：`docs/three-way-interop.md`（用户拍板方案）／参照实现：`xray--core`（`feat/three-way-interop`）
> 门禁：`bash tools/check_all.sh` → **20/20 全绿**（改前基线 19/19；新增 `tools/check_interop.sh` 39 断言）
> 提交：`mihomo--core` 本地 commit **`c446d3f`**（**未 push** —— 用户规矩"验证干净再推"，待统一验证）
> 真机：RN（M 服务端真实部署 + 真公共服务 `:9443`）+ CC（xbd / mihomo 客户端 / sb-client）

---

## 0. 一句话结论

M 服务端现在也**声明自己的内核**并在**同一个订阅地址**上发两种产品：

```
主地址（普通话）   = 19 行分享链接（URI 列表）   ← 任何客户端都能读（xbd / sb-client / mihomo / 第三方）
url-<发行版>（原生） = mihomo YAML（proxies:）     ← 只有 mihomo 内核读
地址查询串          = ?interop=1&kernel=mihomo&distribution=upstream&version=1.19.32
                       &formats=uri,upstream&url-upstream=<原生地址>
```

真机结果（同一台 RN、同一批 19 节点、同一台 CC）：

| 路径 | 改前 | 改后 |
|---|---|---|
| **M → xbd（跨内核）** | 解析 19 个**空壳** → **导入 0/19** | **导入 15/15**（anytls×3 + tuic×1 是 Xray 内核不支持的协议），**逐节点真连 15/15**，出口 IP 全部 `104.28.201.80` |
| **M → mihomo（同内核）** | YAML 19 节点 / 真连 **14/19** | 走**原生**：载荷与改前**逐字节相同**（sha256 `08d847fe…`），真连 **14/19**（同基线） |
| 声明缺失 / 原生 404 | — | 回退普通话并**打出原因**，19 节点照常导入，不报错 |
| 对角线闸门（M 分享 → M 客户端） | 14 通过 / 0 失败 | **14 通过 / 0 失败**（真内核层含真连 204 + 出口 IP） |

---

## 1. 为什么 M 要改：问题不是 bug，是跨生态格式边界

`research/e2e/three-servers-three-clients.md` §3.2 的实测：M 的分享载荷是 mihomo
原生的 `proxies:` YAML，Xray 的 xbd 拉下来 **解析出 19 个空壳**（`name=node, address=""`）、
**导入 0/19**。本次在 RN/CC 上原样复现（§4.1 基线 A/B）。

修法**不是**让 xbd 学 YAML，而是（用户拍板、X 侧已验收的同一套方案）：**服务端声明自己的
内核与可用格式，并把「普通话」（URI 列表）作为默认产品**——xbd 与 mihomo 内核本来都会
解析 URI 列表。

---

## 2. 设计在 M 上的落点（与 X 的差异，逐条有据）

| 项 | X（参照实现） | M（本次） | 为什么 |
|---|---|---|---|
| 声明载体 | 订阅地址查询串 | 同 | 公共服务路由先剥查询串（`path.split("?",1)[0]`）→ 对第三方客户端**可证惰性**（§5.2 实测） |
| 主产品 | base64(URI 列表) | **URI 列表（逐行明文）** | 两家消费者都实测可读：xbd 的 `parse_subscription` 认多行明文；mihomo 的 proxy-provider 认逐行链接（M 客户端注释里已记实测）。base64 在 mihomo provider 路径未验证 → 不用未验证的形态 |
| 原生产品 | Xray JSON（另一 token） | mihomo YAML（另一 token） | M 的原生格式本来就是 YAML；`build_sub.py` 一个字节没改 |
| 发行版标签 | `xray version` 首词小写 | **`upstream`**（官方 mihomo） | ★ 取本仓库既有判定 `src/lib/nodecompat.py:probe_kernel()` 的口径（版本行含 mihomo → `upstream`）。X 的设计文档明确警告：声明里的标签必须与 compat 判能力用的标签是**同一个字符串**，否则"声明匹配上了、能力判定却按另一个名字走"。门禁用真二进制比对两者输出（§6 ⑤） |
| `url-<fmt>` 编码 | 全百分号编码（`%3A%2F%2F`） | **保留 `:/@[]` 原样** | 见下 |

**唯一一处有意的偏离（`url-*` 不做全百分号编码）**：M 的「切换地址族」会把
`out/share_tag-*.txt` 里的 `//<旧host>[:/]` 全量替换成新 host
（`src/lib/env.sh:m_share_links_switch_family`）。若把 `://` 编码成 `%3A%2F%2F`，
那条替换**匹配不到**声明里的原生地址 —— 订阅地址切到新族、原生地址还停在旧族，
客户端走原生会白跑一次。保持原样则两侧一起被改写。对端解析不受影响：X 的客户端与 M
的客户端都用 `parse_qsl`，原始字符与解码后结果等价（**两个方向都真机验证过**：§5.1 用 X 的
`interop.py` 读 M 的声明、§5.3 用 M 的客户端读自己服务端生成的声明）。门禁有断言钉住
"`url-upstream=http://` 必须原样出现"。

**同一份实现只有一处**：`src/lib/interop.py` 服务端与客户端共用（X 那边是两个目录，
所以是两份逐字节副本 + sha256 比对）。门禁断言仓库里只有一份，且 `share.sh` 与
`client.sh` 都引用它 —— "字段名抄两遍而漂移"的表现是**静默全走普通话**，不报错。

---

## 3. 实现清单（只改 `mihomo--core`）

| 文件 | 内容 |
|---|---|
| `src/lib/interop.py`（新） | 声明构建 / 解析 / 决策（9 条规则 + reason code）+ 本机内核事实真探测（`mihomo -v`，规则与 `nodecompat.probe_kernel` 逐条一致，门禁比对）。服务端与客户端**同一份** |
| `src/share/build_uri.py`（新） | **普通话产品生成器**：节点视图 → 逐行分享链接。字段名不发明：取自本仓库既有产出者（`hysteria2.sh:479 hy2_link` / `VLESS.sh:367 render_share_link` / `Trojan.sh:190` / `AnyTLS.sh:537` / `TUIC.sh:357`）与它们记录的 mihomo 源码事实。URI 装不下的字段**逐条报损失**（`[损失]`/`[未覆盖]`），不静默丢 |
| `src/share/build_sub.py` | 抽出 `build_buckets()` / `select_proxies()`：两个产品**同一套收集与陈旧过滤**（设计 §5 要求两条产品发布同一批节点）。CLI 行为与输出一字未变（真机 `cmp` 验证：改前/改后原生 YAML 逐字节相同） |
| `src/share/share.sh` | `_share_create_records()`：**一条分享两条记录**（普通话主 + 原生附带，TTL/次数同源）；地址上挂声明；列表加「格式」列并打印**带声明的地址**；`share_refresh_all` 按 `meta.role` 分派产品；停用/启用/撤销/删除/重建 token **成对**生效；旧记录（无 role）刷新后仍是 YAML |
| `src/client.sh` | 读声明决策（`_sub_import_by_declaration`）+ 运行期回退链；「添加节点」与「更新订阅节点」走**同一套**；日志打出 `本次拉取: 原生 (mihomo YAML) / 普通话 (URI 列表) —— <原因>`；新增非交互入口 `client.sh node-sub <地址> [组名]`（面板同一条代码路径，供门禁与真机验收复现） |
| `src/manifest.txt` / `src/lib/core_mgmt.sh` | 新文件登记（两处清单一致，`check_manifest.sh` 断言） |
| `tools/check_interop.sh`（新，39 断言） | 见 §6 |
| `tools/check_interop.sh`/`tools/check_all.sh`/`tools/check_interfaces.sh` | 接入门禁；顺带修掉接口闸门一处**子串当等值**的匹配 bug（`grep "uri.py"` 命中 `build_uri.py` → 把 `BUILD_URI` 解析成 `proxy_node_compat/uri.py`，报假错） |

**URI 表达不了的东西（报损失，不假装有）**：真机 19 节点上 13 处，逐条：
`xhttp-opts.x-padding-bytes`（3 处，mihomo 私有）、`ech-opts.query-server-name`（5 处，
compat 规则 `uri.vless.ech = PARTIAL`）、anytls `idle-session-*`（4 处）、
自签 hy2 的 `fingerprint` 是证书 sha256（1 处，按 `pinSHA256`+`pin` 两个键写进链接）。

---

## 4. 真机验证

### 4.1 M → xbd：改前 0/19 → 改后 15/15（CC）

**基线（改前，同一份 19 节点载荷）**：把**原生地址**（内容 = mihomo YAML、地址上无声明）
喂给 xbd —— 两种构建都是同一结果：

```
$ XBD_PREFIX=/tmp/xbd-old .../xbd node sub "http://107.173.154.178:9443/share/3e331106…"   # 部署版（无 interop）
✓ 解析出 19 个节点
✓ 已导入 0 个节点                     ← 与 research/e2e/three-servers-three-clients.md §3.2 逐字一致
```

**改后（带声明的地址，X 的 interop 客户端）**：

```
$ python3 /tmp/xbd-m/lib/interop.py decide "<带声明地址>"
{"choice":"uri","reason":"cross-kernel","detail":"服务端内核 mihomo ≠ 本机 xray", …}

$ XBD_PREFIX=/tmp/xbd-m XBD_ROOT=/tmp/xbd-m /tmp/xbd-m/bin/xbd node sub "<带声明地址>"
==> 下载订阅
本次拉取: 普通话 URI 列表 —— 服务端内核 mihomo ≠ 本机 xray       ← 决策日志
✓ 解析出 15 个节点
✓ 已导入 15 个节点
```

**逐节点真连**（xbd 自带 `genconfig.py` + `bin/xray`，隔离实例、随机端口、socks5；
判据 = `204` **且**出口 IP ≠ 本机）：**15/15**，出口 IP 全部 `104.28.201.80`（RN 的 CF 出口）。

```
node-001-mhysteria201-tls       http=204  exit_ip=104.28.201.80
node-001-mhysteria202-tls       http=204  exit_ip=104.28.201.80
node-001-mtrojan01-reality      http=204  exit_ip=104.28.201.80
node-001-mtrojan02-reality-grpc http=204  exit_ip=104.28.201.80
node-001-mtrojan03-tls          http=204  exit_ip=104.28.201.80
node-001-mtrojan04-cdn-ws       http=204  exit_ip=104.28.201.80
node-001-mtrojan05-cdn-grpc     http=204  exit_ip=104.28.201.80
node-001-mvless01-reality       http=204  exit_ip=104.28.201.80
node-001-mvless01-tls-ws        http=204  exit_ip=104.28.201.80
node-001-mvless02-reality-grpc  http=204  exit_ip=104.28.201.80
node-001-mvless02-tls-xhttp     http=204  exit_ip=104.28.201.80
node-001-mvless03-reality-xhttp http=204  exit_ip=104.28.201.80
node-001-mvless03-tls-xhttp-cdn http=204  exit_ip=104.28.201.80
node-001-mvless04-cdn-ws        http=204  exit_ip=104.28.201.80
node-001-mvless05-cdn-grpc      http=204  exit_ip=104.28.201.80
=== xbd 真连: 15/15 ===
```

本机自身出口 IP = `183.210.249.163` / `2409:8a20:1c93:5460::2`（CC 直连多源实测）≠
`104.28.201.80` —— **204 没有单独当成功**。

未导入的 4 个（`anytls×3` + `tuic×1`）是 **Xray 内核不支持这两个协议**（不是载荷问题）：
xbd 的解析产物里它们连 scheme 都不认，因此**不进**导入列表。

### 4.2 一处必须让人看见的**跨生态实测缺陷**：证书 pin 的参数名

第一次全量真连是 **14/15**，唯一失败的是自签节点 `mHysteria202-TLS`（`http=000`）。
查其解析产物：`pinned_cert_sha256 = ""` —— 链接里的 pin **没被 xbd 读到**。

* mihomo 的 hy2 URI 分支只认 `pinSHA256`（M 仓库注释里钉着 mihomo 源码行号，
  写 `pin=` 会被**静默忽略**）；
* Xray 系（`xbd/lib/node.py:489`）只读 `pin=`；同样，`pinSHA256` 被静默忽略。

→ 修法与带宽参数同一套（M 早就写过两套名字 `up/down` + `upmbps/downmbps`）：
**两个键都写**。改后该节点 `pinned_cert_sha256 = b8f8fc05…`（解析产物核实），真连 **204**，
15/15。门禁加断言钉住"两个键都要在"（§6 ①）。

> 这条同时说明：跨生态的 URI 互通里，"某个键只有一家认"是**静默**失效 —— 只有逐节点真连
> 才能发现（解析成功、导入成功、默认节点还能用）。

### 4.3 M → mihomo：走原生，零退步（CC）

同一个带声明地址，用**新版 M 客户端**（`client.sh node-sub`，与面板同一条路径）：

```
[OK] 本次拉取: 原生 (mihomo YAML) —— 同内核同发行版 (mihomo/upstream) → 取原生
[OK] 解析出 19 个节点 (组名 m-rn-native)
```

**逐字节一致的证据（三层）**：

1. `build_sub.py` 改前（部署版 `d13fecbe…`）与改后（新代码）对同一 `out/conf` 的产物
   **`cmp` 逐字节相同**（sha256 `1e21bc2b…`，含 `-o` 头）；
2. 真公共服务上**新原生记录**取回的载荷 sha256 = `08d847fe84a274b0…`（6312 B）=
   **改造前就已发出的那条 M 分享**（`ec23e4cb…`）的 `content_sha256` —— 即"接入前
   生产路径发出的字节"；
3. 客户端落盘的 provider 解析出 **19 节点**，且与 `build_sub.py` 直出的 YAML 同源
   （同一份 `dump_doc` 产物）。

**逐节点真连对照**（隔离 mihomo v1.19.32 实例，逐节点切换 + `204` + 出口 IP）：

| provider | 真连 | 失败的都是谁 |
|---|---|---|
| 原生 YAML | **14/19** | 5 条 CDN 节点（`mTrojan04/05-CDN`、`mVLESS03-TLS-XHTTP-CDN`、`mVLESS04/05-CDN`）—— **与改前基线一致**（`three-servers-three-clients.md` §3.2：5 条 CDN `delay=0`） |
| 普通话 URI | 17/19 | 2 条 `trojan+REALITY`（`mTrojan01/02`）—— 与本仓库已入册的结论一致：**mihomo 的 trojan 链接解析器丢 reality**（`xray--core` 提交 `278089d`） |

即：**URI 普通话不是"功能更差的备份"** —— 它在 mihomo 上把 CDN 节点连通了、却丢 trojan+reality；
两条路径各有取舍，客户端按声明选路径，损失由 compat/报告说出来（不假装两条路一样）。

### 4.4 声明缺失 / 原生 404 / 跨内核（CC，真客户端）

```
# ① 裸主地址（地址上没有声明）
[Info] 本次拉取: 普通话 (URI 列表) —— 地址上没有内核声明
[OK] 解析出 19 个节点                      ← 不报错

# ② 声明在、原生地址 404
[Info] 本次拉取: 普通话 (URI 列表) —— 同内核同发行版 (mihomo/upstream) → 取原生；原生取件失败(HTTP 404) → 回退
[OK] 解析出 19 个节点                      ← 回退且把原因打出来

# ③ 声明是别人家的内核（kernel=xray）
[Info] 本次拉取: 普通话 (URI 列表) —— 服务端内核 xray ≠ 本机 mihomo
[OK] 解析出 19 个节点                      ← 决策在取件之前: 连原生取件都没发生
```

服务端侧（RN 真公共服务）另外验证：

* 同一 token **带声明 vs 不带声明**，响应体 sha256 逐字节相同
  （`20a00d76457ed660…`）—— 声明对第三方客户端**零影响**（惰性可证）；
* 刷新按角色分派：`share_refresh_all` 后主记录仍是 19 行 URI、原生记录仍是 YAML
  （`08d847fe…` 未变）—— 不分派的话原生记录会被写成 URI 列表，而地址上仍声明"原生在那边"。

### 4.5 对角线不倒退（CC，真内核）

```
$ cd /tmp/m-repo && MIHOMO_BIN=/root/catmi/mihomo-client/mihomo \
    M_DIAG_REAL_LINK=/tmp/m-real-native.yaml bash tools/check_diagonal.sh
① 台账名 vs 产物名            6/6 通过
② 经 HTTP 取回字节一致        2/2 通过
③ M 客户端导入（真代码路径）   2/2 通过
④ 真内核解析节点数            2/2 通过
⑤ 真实分享链接 + 真连          真实分享链接被内核解析出 19 个节点
                              mAnyTLS02-TLS http=204 0.77s exit_ip=104.28.201.80（本机 2409:8a20:…）
对角线闸门 (M 分享 → M 客户端): 14 通过 / 0 失败 / 0 跳过
```

**19 节点、真连 204、出口 IP = RN 的 CF 出口** —— 与基线逐项一致，无跳过层。

---

## 5. 一个必须让人看见的**前提**（不是回归，但影响面要说清）

主地址从 YAML 换成 URI 列表之后，**客户端要认得"一行行分享链接"**：

* 仓库自 `60fb4c5`（2026-10-10 23:32，"M 自家客户端能吃自家分享链接 (URI 列表)"）起支持，
  本次真机用**仓库 HEAD 的客户端**验证：URI 列表与 YAML 两种 provider 都正常导入
  （19/19）；
* CC 上**部署的那份**客户端是 2026-10-10 12:22 的构建（`sha256 6f9f9cd7…`，早于
  `60fb4c5`）。它的导入器对 URI 列表报
  `[ERR] 不是合法的 Mihomo 订阅 (需要顶层 proxies: 列表)`（实测原样复现）。

也就是说：

* **已经发出去的旧链接不受影响** —— 记录内容不重写，仍是 YAML（本次特意保证
  `share_refresh_all` 对无 `role` 的旧记录继续刷 YAML，门禁有断言）；
* **新建的分享**要求客户端是含 URI 列表支持的构建。面板在生成分享时**明确打出这一行**
  （`提示: 客户端需认得 URI 列表 (仓库 2026-10-10 23:32 起); 更早的构建请先更新客户端`），
  不静默。

**另一条路（保留 YAML 当主地址）被设计排除了**：X 的客户端在"跨内核 → 拉 URI"时拉的是
**主地址**（`_sub_fetch_by_declaration` 用主 URL），主地址若不是普通话，M→xbd 这条链在
服务端就断了；而"客户端按声明协商主地址"要改 X（本次纪律不允许）。

---

## 6. 门禁

```
$ bash tools/check_all.sh                      # 本机
═══ 全部 20 项通过 ═══

$ cd /tmp/m-repo && MIHOMO_BIN=/root/catmi/mihomo-client/mihomo \
    bash tools/check_all.sh                    # CC（验收机，带真内核）
═══ 全部 20 项通过 ═══
```

* 改前基线：**19/19**（含 `tools/check_diagonal.sh`）；本次新增第 20 道
  `tools/check_interop.sh` → **39 断言 0 失败**；
* `tools/check_interop.sh` 全部离线、`/tmp` 夹具、真代码路径：

| 组 | 断言（要点） |
|---|---|
| ① 两个产品 | 节点集合逐字一致（URI 与 YAML 同一批，含陈旧产物过滤）；生成的 URI 能被 compat 解析回同一节点（端口/凭据/sni 逐项相等）；**自签 pin 两个键都在** |
| ② 不静默降级 | `xhttp-opts.x-padding-bytes` 报损失；做不出链接的协议（snell）报"未覆盖"；可表达的照常产出 |
| ③ 声明 | `declare→parse` 往返；**保留地址上别人的参数**；**片段里的同名字段不算声明**；`url-*` 保持 `://` 原样（地址族切换依赖它） |
| ④ 决策 9 条 | 同内核同发行版 → native；跨内核 / 声明缺失 / 版本不认识 / 内核不认识 / 发行版不在清单 / 本机发行版探测不出 / 没给地址 / 地址不是 http(s) → uri（逐条 reason code） |
| ⑤ 标签同源 | 用**假内核二进制**（与真 `mihomo -v` 首行同形）比对 `interop.self_facts()` 与 `nodecompat.probe_kernel()`：distribution/version 逐字相同 |
| ⑥ 客户端决策+回退 | 跑**真** `client.sh node-sub`（与面板同一条代码路径）+ 真 HTTP：原生→2 节点；原生 404→回退且打出原因；声明缺失→普通话且不报错；跨内核→连原生取件都没发生 |
| ⑦ 同一份实现 | 仓库里只有一份 `interop.py`；服务端与客户端都引用它 |
| ⑧ 服务端两条记录 | 假公共服务（只做存储）驱动**真 share.sh**：建分享=两条记录且角色/内容/互相指向正确；**刷新按角色分派**（不串味）；停用/启用/按 tag 撤销**成对**；删除两条一起删；旧记录（无 role）刷新后仍是 YAML |

* 顺带修掉 `tools/check_interfaces.sh` 一处匹配 bug：`grep "uri.py"` 会命中 `build_uri.py`
  → `BUILD_URI` 被解析成 `proxy_node_compat/uri.py`，报出"传了 `--out-dir` 但 uri.py 里没有
  这个参数"这种**假错**（同一个"子串当等值"的坑，本项目在裸名/带旗帜名上踩过）。

---

## 7. 提交与纪律

* 本地 commit：`mihomo--core` **`c446d3f`**（提交信息含本报告路径）；
  `proxy-node-compat` 里的本报告另有一个文档 commit。**两个仓库都未 push**
  —— 按用户规矩"验证干净再推"，本次结论写在这里待统一验证后推送。
* 只改 `mihomo--core`；`xray--core` / `sing-box-core` 只读（CC 上的 xbd 用 `feat/three-way-interop`
  的三个 lib 文件**复制到 `/tmp/xbd-m`** 隔离前缀运行，**没有改 `/opt/xray-browser-dialer/`**：
  部署版 `actions.sh b304d760…` / `node.py 5ea56a69…` 哈希不变）。
* **没有写任何生产路径**：RN 上只读拷贝 `out/`、`conf/` 到 `/tmp/m-int/`，服务端脚本从
  `/tmp/m-int/src` 运行；CC 上一律 `/tmp`（隔离 xbd 前缀、隔离 M 客户端、隔离内核实例）。
* **没有重启任何服务**：RN `mihomo`（启动于 2026-10-09 21:11 PDT）、`proxy-share-service`
  （2026-10-09 05:08 PDT）时间戳未变；CC 上 xray PID 968528 / mihomo PID 1364829 全程在跑。
* 生产文件哈希未变（RN `share.sh 9b24796b…`、`build_sub.py d13fecbe…`；CC 客户端 `6f9f9cd7…`）。
* 分享记录**用完即删**：测试的两条（`6157b92f…` / `3e331106…`）已 DELETE，
  `provider=mihomo` 回到测试前的 **1 条**（原有的 disabled `ec23e4cb…`）。
* 临时物已清理（RN `/tmp/m-int*`、CC `/tmp/xbd-m`、`/tmp/mcli*`、`/tmp/m-repo`、
  探针配置与日志），无残留进程。

---

## 8. UNKNOWN（没证据就不猜）

| # | 事项 | 为什么没结论 |
|---|---|---|
| U1 | 第三方客户端（v2rayN / Shadowrocket / 机场面板）对**带未知查询参数**的订阅地址是否有改写行为 | 本环境没有这些客户端。服务端侧可证（公共服务忽略查询串、带/不带声明响应逐字节相同）；客户端侧未逐一验证 |
| U2 | 旧的 M 客户端（不含 URI 列表支持的构建）能否通过面板"更新脚本"一次更新到位 | 只证明了"它读不了新主地址"（§5）与"仓库 HEAD 的客户端两种格式都能导入"；更新链路本身未在 CC 上跑（会动生产客户端） |
| U3 | `base64(URI 列表)` 形态在 mihomo proxy-provider 路径上是否也能读 | 未测（xbd 侧支持）。当前按"逐行明文"发，两家都实测可读，所以没有动机用未验证的形态 |
| U4 | 各家客户端对同一个 pin 值写两个键（`pinSHA256` + `pin`）是否都会**忽略**多余的那个 | 实测两端都能取到自己认的那个且不出错（15/15 真连）；"多余键会不会进配置"没逐字节查 |
| U5 | `pcs`（compat 文档记为 2026-01-18 进规范的 pinned-cert-sha256 参数）是否该同时写 | 只在 `docs/uri-representation.md` §3 见过这个名字，本环境两家客户端都不读它 → 没写（不猜） |
| U6 | M 的 **S 服务端**（sing-box）声明口径 | 不在本次范围（只改 `mihomo--core`） |

---

## 9. 复现方式

```bash
# 1) 门禁（全离线，/tmp 夹具，真代码路径）
bash tools/check_all.sh                 # 20/20
bash tools/check_interop.sh             # 39 断言

# 2) 单点调试
python3 src/lib/interop.py self
python3 src/lib/interop.py decide '<订阅地址>'
python3 src/share/build_uri.py --out-dir <out> --conf-dir <conf> --tag all --list-losses
python3 src/share/build_sub.py --out-dir <out> --conf-dir <conf> --tag all

# 3) 客户端（与面板同一条代码路径）
CLI_ROOT=<客户端根> bash src/client.sh node-sub '<带声明的地址>' <组名>

# 4) 真机（RN 服务端 + CC 客户端）
#    RN: 只读拷贝 out/ conf/ 到 /tmp → source src/lib/env.sh; source src/share/share.sh
#        → printf '1\n0\n5\n<对外IP>\n' | share_create
#    CC: XBD_PREFIX=/tmp/xbd-m .../xbd node sub '<带声明地址>'      # 决策日志 + 导入数
#        bash tools/check_diagonal.sh（MIHOMO_BIN + M_DIAG_REAL_LINK）
```

---

## 10. 参考

* 设计：`docs/three-way-interop.md`；X 侧验收：`research/integration/three-way-interop-x.md`
* 九宫格原始归因：`research/e2e/three-servers-three-clients.md`（§3.2 M→xbd 0/19）
* URI 表达力与损失：`docs/uri-representation.md`
* mihomo 侧参数名事实（本仓库既有注释）：`src/conf/hysteria2.sh:484-501`
* mihomo trojan 链接解析器丢 reality：`xray--core` 提交 `278089d`（已入册）
