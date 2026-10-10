# X 内核（`xray--core`）第一轮：4 条实证 bug 的修复与验证

- 日期：2026-10-10
- 目标仓库：`/root/deepseek/repos/xray--core`（**只改这一个**；`mihomo--core` / `sing-box-core` 未动，只读）
- 真机：`ssh rn`（107.173.154.178，Xray 26.3.27）、`ssh CC`（192.168.1.178，Xray 26.3.27 + `/opt/xray-browser-dialer`）。
  **只读参考**：RN 的 `/usr/local/bin/xray`、`/root/catmi/xray/`；CC 的 `bin/xray` 与 `nodes/`。
  所有实验都在 `/tmp`（本机 / CC）与仓库工作区里做，跑完清理；**没有写 RN/CC 任何生产路径，没有启停正式服务**。
  证据里出现的 `xray` 都是把 RN 的 26.3.27 二进制 / CC 的 `bin/xray` 复制或只读链接到 `/tmp` 后跑的（本机另配了从 CC 取的 `geoip.dat`，否则 `geoip:private` 规则读不到数据文件）。
- 提交（`main`，已推送：`git ls-remote origin main` = `0e396dfb6a197db543fd191eea8fdb1dadc36cc4`）：

| # | commit | 内容 |
|---|---|---|
| 1 | `36fa2b8` | P0-2 gen_psk 被误删 + batch 用退出码 0 掩盖失败 |
| 2 | `ead7e3c` | P0-1 mux 策略（客户端 + 服务端声明） |
| 3 | `8a37e36` | P0-3 绑回环的节点不再按"公网 host:port"发布 + 产物一致性 |
| 4 | `39623d9` | P0-4 旧格式字段类型体检 + 单节点也跑内核校验 |
| 5 | `0e396df` | 门禁：为这 4 条加 44 条回归断言 |

- 门禁：`bash tools/check_libs.sh` → **620 通过 / 0 失败**（提交后的干净树 `git archive HEAD` 里跑的，连跑两次一致；改动前基线 576 通过 / 0 失败）。
- 注：同一工作区还有**另一路并行 agent** 在改 nginx 相关文件（`conf/lib/nginx_apply.py`、`conf/nginx_site.sh`、`conf/node.sh`、`conf/lib/deploy.py`、`conf/fd/xrayserver-reverse.sh` 与 `tools/check_libs.sh` 里 3 处旧门禁行）。这 5 个文件的改动**不属于本轮**，5 个 commit 里一个字节都没纳入（`tools/check_libs.sh` 是用 `git apply --cached` 只提交我的那一个 hunk）。

## 一览

| # | 问题 | 是否已修 | 验证手段 | commit |
|---|---|---|---|---|
| P0-1 | mux 无条件开、节点 `mux:false` 被吞、XHTTP 也照开 | ✅ | CC 回环实测（204/000 对照）+ 真内核 `-test` + 生产节点文件对比 | `ead7e3c` |
| P0-2 | `gen_psk` 未定义 → 永远生成不出 SS2022；batch 退出码 0 | ✅ | `/tmp` 沙箱跑真 batch（修复前/后对照）+ 内核 `-test` | `36fa2b8` |
| P0-3 | 生产 `vless-xhttp-01/02/03` 三条死链 | ✅（根因已修；三条节点本身**不该对外发布**，见下） | 用 RN 真实数据在 `/tmp` 重跑分享链路（修复前/后对照） | `8a37e36` |
| P0-4 | `"ech": true` 类旧字段写坏整份配置 | ✅（ech 那一条此前已被 `1366804` 修掉；本轮补"同类路径"+ 生成后校验） | 旧节点文件 + 真内核实测 + 坏配置不覆盖 | `39623d9` |
| — | 门禁 | ✅ | 620 通过 / 0 失败；新增 44 条 | `0e396df` |

---

## P0-1 · mux 无条件开启（用户直接点出的问题）

### 现象

- 客户端 `Client/lib/genconfig.py` 默认给**每个**出站写 `mux:{enabled:true,concurrency:8}`；开关只有 `--no-mux`，而它的 `default=True` —— 也就是"不表态 = 开"。
- 后果三层，都有实证：
  1. **节点 JSON 里的 `mux:false` 被忽略**。CC 生产 `nodes/node-001-ccsxvless-xhttp-01.json` 里写着 `"mux": false`，而 `runtime/xray-client.json` 里每个出站都带 mux。
  2. **XHTTP 节点被开上 mux.cool**，官方文档明确「使用 XHTTP 时不要启用 mux.cool」（XHTTP 自带 `xhttpSettings.extra.xmux`）。CC 回环实测：同机同配置**只差 mux** → mux 关 `204` / mux 开 `000`。
  3. RN 生产 `log/error.log` 里有 mux.cool 会话直接失败：`common/mux: unexpected EOF > failed to read metadata > timeout`。

### 根因（修复前）

| 位置 | 问题 |
|---|---|
| `Client/lib/genconfig.py:287-288`（`1366804`） | `if mux: ob["mux"] = {"enabled": True, "concurrency": 8}` —— 只看命令行开关，**从不读节点字段**，也不看传输类型 |
| `Client/lib/genconfig.py:828` | `--no-mux` 的 `default=True`：没有"没表态"这个状态 |
| `Client/lib/node.py:454` | `n["mux"] = bool(entry.get("smux") or entry.get("mux"))` —— ① 字典恒为真：mihomo `smux:{enabled:false}` 也读成"要开"；② 把 mihomo/sing-box 的 **SMUX**（另一套协议）当成 Xray 的 **mux.cool**（固定域名 `v1.mux.cool:9527` 只在 Xray 语境有意义） |
| `Client/lib/compat2.py:168-171` | 适配层把"客户端默认开 mux"写死成 `mux_cool=true`（事实变了要跟着改，否则 compat 结论与现实不符） |
| 服务端 | **没有任何 mux 写入点**（全仓库 grep `mux` 只命中 Client/；RN 生产 `conf/`、`out/` 全无 mux）—— 但服务端生成的"节点"（`conf/vlessxhttpecn.sh render_client()` 产出的客户端 JSON / mihomo YAML）**没有对 XHTTP 声明"不要 mux"**，而客户端当时默认开 → 服务端交出去的 XHTTP 节点到了客户端就变成"XHTTP + mux.cool 同开" |

### 修法

1. **判据收口**：`Client/lib/genconfig.py` 新增 `mux_decision()`，三层优先级
   ① `--mux` / `--no-mux`（`--no-mux` 的 default 从 `True` 改成三态 `None`）
   ② 节点 JSON 的 `mux` 字段（**现在真的生效**）
   ③ 默认**不开**（mux.cool 是十多年前为"浏览器同域 6 并发"做的补丁；今天它对 UDP/QUIC/XHTTP 只有副作用）
2. **XHTTP / QUIC 硬拒**：`MUX_FORBIDDEN_TRANSPORTS = {xhttp, quic, mkcp}`、`MUX_FORBIDDEN_PROTOCOLS = {hysteria2}` —— 即使显式 `--mux` 也拒，并在 stderr 说明官方依据 / 实测依据。**不是一刀切砍功能**：非 XHTTP 传输下 `--mux` 与节点 `mux:true` 都能开，只是会打印风险提示。
3. **节点生成侧**：`Client/lib/node.py` 把 `smux` 与 `mux` 分开（`_flag()` 读字典的 `enabled`；新增 `smux` 字段留档，不冒充 mux.cool）；URI 里的 `mux=` / `mux-enabled=`（v2rayN 一类客户端的私有扩展）也兑现成节点字段。
4. **适配层同步**：`compat2.runtime_options()` 默认值 `1→0`；新增 `effective_mux()`（与 genconfig 同判据）；节点声明 mux 但传输不允许时新增诊断 `MUX_REQUEST_DECLINED`，避免 compat 对 XHTTP 节点给出比现实更悲观的运行期结论。
5. **服务端声明**：`conf/vlessxhttpecn.sh render_client()` 对 XHTTP 节点在生成的 Xray 客户端 JSON 里**显式**写 `"mux": {"enabled": false}`（节点对客户端的声明；各家客户端对 mux 的默认值并不一致），mihomo YAML 顶部加同义注释。

### 验证证据

**① CC 回环（真内核 26.3.27，全部只写 `/tmp`，用完清理）**

```
① 默认（无 --mux，节点 mux:false）+ XHTTP
    mux 写进配置: null  network= xhttp / xray -test: OK / curl 204 探测 → http_code=204
② 节点 mux:true + XHTTP（应被拒绝）
    WARN: genconfig: 节点要求开 mux（来自 节点 JSON 的 mux 字段），但传输 xhttp 不能开 —— 已忽略：官方文档明确「使用 XHTTP…
    mux 写进配置: null / curl 204 探测 → http_code=204
③ --mux + XHTTP（应被拒绝）
    WARN: genconfig: 节点要求开 mux（来自 --mux），但传输 xhttp 不能开 —— 已忽略：…
    mux 写进配置: null / curl 204 探测 → http_code=204
④ 反证：同一份配置手工插回 mux（其余逐字节相同）
    mux 写进配置: {"enabled": true, "concurrency": 8} / xray -test: OK / curl 204 探测 → http_code=000
⑤ 生产节点文件（CC 上真实节点）
    node-001-ccsxvless-xhttp-01.json → mux 写进配置: null（修复前是 {"enabled": true, "concurrency": 8}）
    node-001-ccsmreality-01.json     → mux 写进配置: {"enabled": true, "concurrency": 8}（节点确实声明了 mux:true，非 XHTTP → 保留）
```

**② 修复前 / 修复后对照（同一份 CC 生产节点文件）**

```
修复前（HEAD 的 genconfig.py）：mux 写进配置: {"enabled": true, "concurrency": 8} network= xhttp；genconfig 有 mux 相关警告吗: 0 条
修复后（本轮）：              mux 写进配置: null
```

**③ 本机矩阵（真内核 `xray run -test`，8 份配置全 OK）**

| 用例 | 期望 | 实测 |
|---|---|---|
| 节点 `mux:false`，无 `--mux` | 不写 | `null` |
| XHTTP 节点（默认） | 不写 | `null` |
| 节点 `mux:true` + tcp/reality | 写 | `{"enabled": true, "concurrency": 8}` + 风险提示 |
| XHTTP + 节点 `mux:true` | 拒 + 说明 | `null` + stderr 原因 |
| `--mux` + tcp | 写 | 同上 |
| `--mux` + XHTTP | 拒 + 说明 | `null` + stderr 原因 |
| `--no-mux` + 节点 `mux:true` | 不写 | `null` |
| hysteria2 + 节点 `mux:true` | 拒 + 说明 | `null` + "QUIC 自带多路复用 + RN 实测会话超时" |

**④ 服务端产物（`/tmp` 沙箱跑 `conf/vlessxhttpecn.sh`，xhttp + nginx 档 + 自签证书 + 真内核）**

```
片段:        listen=127.0.0.1 port=41012 tag=vless-xhttp01 path=/BjXSjgxN/
客户端 JSON: "mux": {"enabled": false}  address=moontv.test port=443  → xray run -test: Configuration OK
mihomo YAML: # 不要开 smux / mux.cool：XHTTP 自带多路复用，官方明确不建议两者同开
```

### 遗留

- CC 生产客户端仍跑旧代码（`/opt/xray-browser-dialer/xbd-dist` 是 14:29 的包），所以**线上 `runtime/xray-client.json` 现在还是 mux:on**（本任务只改仓库代码、不部署生产）。等客户端包更新后，XHTTP 节点的 mux 才会真正消失。
- 节点文件里历史遗留的 `mux:true`（由旧的 `smux` 误映射写入）**仍会被尊重**（非 XHTTP 传输）——那是"节点声明了 mux"的字面意思；重新导入一次 mihomo YAML 就会变成 `mux:false / smux:true`。
- `--mux` 只能通过环境/命令行给，客户端 UI 没有"这个节点开 mux"的开关（`node.py` 的 `mux` 字段可由导入/订阅带进来）。

---

## P0-2 · `gen_psk` 未定义 → 一键全协议永远生成不出 SS2022

### 现象

`conf/Shadowsocks.sh:232: gen_psk: command not found` → `PSK 长度错误：2022-blake3-aes-256-gcm 需要 32 字节 (获得 0 字节)`；批量（`conf/batch.sh`）把 SS2022 记成 `[失败]`，**退出码却是 0**。

### 根因（修复前）

| 位置 | 问题 |
|---|---|
| `conf/Shadowsocks.sh:232` | `PSK=$(gen_psk "$method")` —— 调用点留着，函数没了 |
| `conf/Shadowsocks.sh`（`1ef13f2` 之前） | `gen_psk()` 长在"随机生成函数"块里，被 `1ef13f2`「端口分配收敛到 `conf/lib/ports.sh`，删 317 行重复实现」**误删**（它与端口无关） |
| `conf/batch.sh:243-245`（修复前） | 汇总完 `batch_summary` 后无条件 `print_ok ... ; return 0` → 失败被完全掩盖 |

### 修法

- `conf/lib/random.sh` 补回 `gen_psk(method)`：`2022-blake3-aes-128-gcm → 16 字节`，`aes-256-gcm / chacha20-poly1305 → 32 字节`，保留 `openssl rand -base64` 的 `=` 填充（去掉会让 base64 解码对不齐）。
- `conf/Shadowsocks.sh` 加载 `lib/random.sh`（本地优先，curl 兜底），并在函数缺失时当场报错 —— 不再让错误以"PSK 长度错误"的面目出现。
- `conf/batch.sh`：有协议失败时收尾 `return 1` + 打印失败清单 + 明确"退出码 1"。
- 配套（为能在 `/tmp` 里用真内核验证）：`conf/{Reality,Trojan,Shadowsocks}.sh` 与 `conf/XRevise.sh` 的 `INSTALL_DIR` 支持 `XRAY_INSTALL_DIR`（并跟随 `XRAY_BASE_DIR`）。没有这条，沙箱里报的是"未找到 xrayls"，看起来像安装坏了。

### 验证证据（`/tmp` 沙箱 + 真内核 26.3.27）

**修复前**（把 `HEAD` 的整棵树 `git archive` 到 `/tmp/xk/head` 跑）：

```
• hysteria2    [OK] 生成
✗ Reality / Trojan / Shadowsocks  (无节点)
[31m失败(详情在日志末尾): Reality Trojan Shadowsocks
[32m[OK]  全协议一键生成流程结束
BATCH_EXIT=0                      ← 3/4 协议失败，退出码仍是 0
```

`/tmp/x-batch-Shadowsocks.log` 原文：

```
/tmp/xk/head/conf/Shadowsocks.sh: line 232: gen_psk: command not found
[Error] PSK 长度错误：2022-blake3-aes-256-gcm 需要 32 字节 (获得 0 字节)
```

**修复后**：

```
✓ Shadowsocks    编号=01  端口=38315  Tag=SS2022-01
✓ hysteria2      编号=01  端口=38316  Tag=hysteria-01
生成成功: Shadowsocks hysteria2
失败(详情在日志末尾): Reality Trojan          ← 沙箱缺 dest_server/证书，与本次修复无关
[Error] 本批有 2 个协议失败: Reality Trojan —— 退出码 1
[Info] 失败详情: /tmp/xk/after-logs/x-batch-<协议>.log
BATCH_EXIT=1
```

SS2022 产物核对 + 内核校验：

```
$ ls /tmp/xk/after/conf → ss2022-01.json hysteria-01.json
$ /tmp/xk/xray -test -config /tmp/xk/after/conf/ss2022-01.json
Configuration OK.        （rc=0；脚本内部也跑了同一条 -test，不通过会把片段删掉）
method= 2022-blake3-aes-256-gcm chars= 44 bytes= 32
```

### 遗留

- 沙箱里 Reality/Trojan 仍失败，原因是它们 `bash <(curl ... conf/XRevise.sh)` 取**已发布**的副本，而沙箱里 `install_info.env` 缺 `dest_server` —— 属沙箱夹具限制，不是本次要修的问题。
- `gen_psk` 的"自定义 PSK"路径没变（长度校验仍在）。

---

## P0-3 · 生产 `vless-xhttp-01/02/03` 三条死链

### 现象

- 三个片段只绑 `127.0.0.1`（`conf/vless-xhttp-0{1,2,3}.json` → 45630 / 31722 / 41721）。
- 分享链接里是 `107.173.154.178:25333 / 26906 / 22168`（`out/vless-xhttp_share-0{1,2,3}.txt`、`out/vless-xhttp_client-0{1,2,3}.json`）→ 外部没人听这些端口，**必然连不上**。
- 而且 RN 上**本机 nginx 里 X 的 location 数 = 0**（生效站点在 nginx 容器里，活跃 location 全是 SB/M 的）→ 即使端口写对，回环节点也依然不可达。

### 根因

**根因 A（发布判据里没有 `listen`）** —— `conf/lib/nodes.py:187-188`（修复前）：

```python
host = meta.get("host") or n.get("sni") or ""
port = meta.get("port") or n.get("port")
```

`build_share_link()` 从头到尾**没看过 `listen`**：把只绑回环的节点当成"公网节点"发布。

**根因 B（端口从哪来 / 为什么对不上）** —— 时间线与证据：

| 时间（RN，只读） | 事实 |
|---|---|
| Sep 21 07:33 | `conf-backup-batch-20260921-073325.tar.gz` 里的 `conf/vless-xhttp-0{1,2,3}.json` = `127.0.0.1` + `45630/31722/41721` + 路径 `/GwDaTZcFKRQgyjY/` … |
| Oct 8 21:20–21:55 | `out/vless-xhttp_{share,client,nginx}-0N.*` 生成（cdn 直连 + direct-ECH 时代的 `公网IP:节点端口` = 25333/26906/22168）；`out/vless-xhttp_nginx-01.conf` 里也是 `proxy_pass https://127.0.0.1:25333` |
| Oct 8 23:06:45 | 三个片段同一秒被改写，内容与 **Sep-21 备份逐字段相同**（`127.0.0.1` + 45630/31722/41721）→ 是"恢复旧备份/旧片段"回来的；**派生文件一个都没重建** |

生成链接的代码（修复前 `conf/vlessxhttpecn.sh:974-989`）只看 ECH 模式：

```bash
if [[ "$ECH_MODE" = "direct" ]]; then ... LINK_HOST="$PUBLIC_IP_V4"; LINK_PORT="$VLESS_PORT"
else                               LINK_HOST="$CERT_DOMAIN"; LINK_PORT="443"; fi
```

它**不看 `ACCESS_MODE`**，所以 nginx 档（回环）节点照样算出"公网IP:节点端口"；`rebuild_one` 也靠"上次选的是什么"猜，而不是读片段的 `listen`。另外派生文件与片段之间**没有任何一致性校验**，所以驱动它的操作没被发现。

### 修法

1. `conf/lib/nodes.py`：新增 `is_loopback_bound()` / `share_target()` —— 分享链接的对外目标**第一次把 `listen` 纳入判据**：
   - 只绑回环 + 无 `tier=nginx` → **拒绝发布**并给出原因（"外部访问不到 · 先配 nginx 反代或改绑 0.0.0.0"）
   - 只绑回环 + `tier=nginx` → 按 nginx 前端发布（`public_port` 或 443），并在"元数据把回环端口当对外端口"时给出提示
   - 公网节点 → 用元数据端口；元数据端口与片段端口不一致时提示（换了端口没重建元数据）
   - `build_share_link(..., notes=)` 把提示/原因带出来；REALITY 缺 pbk 也改成有原因
2. `conf/lib/share_payload.py`：新增第五类 **`refused`**（节点在、元数据在，但不该发布），`full=True` 才展开；**老四元组接口保持兼容**。
3. `conf/share.sh`：把 `refused` 与提示打到 stderr（`不该对外发布: <tag> —— <原因>`）。
4. `conf/vlessxhttpecn.sh`：
   - `render_client()` 的客户端连接目标**同时看接入方式与 ECH 模式**：nginx 档写 `域名:前端端口`（`NPORT` > `install_info.env` > 443），并显式警告"nginx 档 + direct-ECH 互斥"；
   - `rebuild_one()` 从**片段的 `listen`** 推接入方式（片段是事实，不猜）；
   - 目录/内核路径支持 `XRAY_BASE_DIR / XRAY_INSTALL_DIR`（与其余协议脚本一致，这条路径才能在沙箱里单独验产物）。

### 验证证据

**① 用 RN 真实数据在 `/tmp` 重跑同一条分享链路**（只读复制 `conf/vless-xhttp-0{1,2,3}.json` + `out/share/*.json`）：

修复前（HEAD 的 `conf/lib`）：

```
LINK: vless://760aaf87-…@107.173.154.178:45630?…#X-vless-xhttp01     ← 死链（只绑 127.0.0.1）
LINK: vless://48fc355e-…@107.173.154.178:9998?…#X-VLESS-WS_01        ← 死链（tier=nginx 却写节点回环端口）
missing: -  nometa: ['vless-xhttp02', 'vless-xhttp03']
```

修复后：

```
拒发: vless-xhttp01 —— 节点只监听 127.0.0.1, 外部访问不到, 分享元数据里也没有 tier=nginx · 先给它配 nginx 反代
      (conf/lib/nginx_apply.py) 或改绑 0.0.0.0
拒发: vless-xhttp02 —— （同上）
拒发: vless-xhttp03 —— （同上）
LINK: vless://48fc355e-…@107.173.154.178:443?…  #X-VLESS-WS_01       ← 按 nginx 前端 443 发布
提示: VLESS-WS_01: 元数据里的端口 9998 是节点自己的回环端口, 不是对外端口 —— 已按 nginx 前端的 443 发布
```

**② 沙箱跑 `conf/vlessxhttpecn.sh`（xhttp + nginx 档 + 自签证书 + 真内核）——三样产物互相指向一致**

```
node01: fragment=41012  nginx proxy_pass=41012  link=@moontv.test:443   CONSISTENT
node02: fragment=23899  nginx proxy_pass=23899  link=@moontv.test:443   CONSISTENT
分享链接: vless://…@moontv.test:443?encryption=none&security=tls&sni=moontv.test&type=xhttp&path=/BjXSjgxN/…
生成的客户端 JSON → xray run -test: Configuration OK
```

### 这三条该不该对外发布？

**不该（当前形态）**：片段绑 `127.0.0.1` 且本机没有任何 nginx 站点指过来（RN 生效站点里 X 的标记数 = 0）。正确做法二选一：

- **要发布** → 先给它建反代：`conf/lib/nginx_apply.py` 插 `location /<path>/ → https://127.0.0.1:<端口>`（用当前端口，不要抄那份写着 25333 的旧片段），再把分享元数据补成 `tier=nginx` + 域名 → 链接变成 `域名:443`；
- **不发布** → 改绑 `0.0.0.0`（cdn 档）让 CF/客户端直连，链接写 `公网IP:节点端口`。

修好之后，两种情形都**不会再生成必然连不上的链接**：没配反代就明确拒发并说明，配了就按前端端口发布。

### 遗留

- "节点是 nginx 档但站点里没有它"这个**反向孤儿检查**还没做（本轮只做到"发布前拒发/提示"）。上一轮调查里提过：`conf/node.sh check_orphan_nginx` 只查"站点里有标记但节点没了"。建议后续加到 `node.sh` 的体检菜单里。
- 换端口时重写 `out/*_nginx-*.conf` 片段这一条：`rebuild_client`（菜单 4）现在会按片段重算（含正确的对外目标），但没有做成"改端口时自动重建"。
- 生产那三条片段的派生文件（`out/*`）**没有真去重建**（那要写 RN 的生产路径，本轮禁止）—— 修的是根因与判据；RN 上要真正修复，需要执行 `conf/vlessxhttpecn.sh` 的"重建客户端文件"+ 视情况建 nginx 站点。

---

## P0-4 · 旧节点文件 `"ech": true`（bool）把整份配置搞挂

### 现象 / 根因

- `genconfig` 把 bool 写进 `tlsSettings.echConfigList` → 内核拒收**整份**配置（26.3.27 原文 `cannot unmarshal bool into Go struct field TLSConfig.outbounds[0].streamSettings.tlsSettings.echConfigList of type string`）。
- 单节点模式**当时不跑 `--validate-with`**（`actions.sh` / `run-xray.sh` 只在多出站用），于是坏配置直接落盘 → **切到该节点整个实例起不来**。
- **是否已修**：是，`1366804`（本仓库上一个 commit）已在 `Client/lib/genconfig.py` 里把 ech 处理成"仅当非空字符串才写 + 否则 stderr 说明"。本轮先复现确认（读代码 + 旧节点文件实测），再补同类路径与生成后校验。

### 本轮做了什么

1. **同类路径排查 + 类型体检**（`node_type_problems()`）：写出配置前对节点做全字段检查
   - 字符串字段（`name/protocol/address/uuid/password/method/encryption/flow/transport/security/sni/fingerprint/path/host/mode/extra/service_name/header_type/reality_*/pinned_cert_sha256/username/source`）
   - 整数字段（`port/ws_ed`）、布尔字段（`allow_insecure/mux/smux/udp/use_browser/ech_declared`）、`alpn`（字符串或数组）
   - **`ech` 保持"已知历史格式"待遇**：跳过 + 告知，不阻断（"没有 ECH 也能用"远好于"整份配置起不来"）
   - 其余类型不符 → **明确报错**（单节点 `fail()`；多出站剔除该节点并说明），**绝不照写**
2. **单节点模式也跑内核校验**：先写临时文件 → `xray run -test` → 通过才写 `$output`；失败**不覆盖**已有配置，并把内核原文（最后 6 行）打出来。
3. **顺手修掉两条同类旧写法**（都是旧节点文件里真实存在的）：
   - `ws_ed` 是数字字符串时 `ed <= 0` → `TypeError: '<=' not supported between instances of 'str' and 'int'`（现在走 `_as_int`）
   - `alpn` 写成数组时被 `str()` 成 `"['h2']"` 写进内核（内核照收、握手必失败）→ 现在数组直接透传
   - `port` 用 `_node_port` 取值（数字字符串也认），类型不对由体检报错而不是抛栈

### 验证证据（真内核 26.3.27）

```
① 旧节点文件 "ech": true
   genconfig: old-echbool.json: ech=True（bool，内核要 string）—— 已跳过 ECH（旧节点文件里 mihomo 的 enable 会落成 bool）；证书校验请用 pinned_cert_sha256
   {"ok": true, …}      rc=0        echConfigList: null        （配置可正常启动）
   CC 上真实节点 node-001-ccsxvless-xhttp-01.json（也是 ech:true）→ xray -test: OK
② 更一般的类型不符："sni": true
   genconfig: 节点 bad-sni.json 有字段类型不符合内核要求，不写配置（照写会让内核拒收**整份**配置）：
     - sni=True（bool，内核要 string）
   rc=2 ； ls out-badsni.json → No such file or directory
③ 旧写法（port 字符串 + alpn 数组 + ws_ed 字符串）
   修复前：alpn= ["['h2']"]（垃圾值被写进内核）；ws_ed 字符串 → TypeError（rc=1）
   修复后：rc=0、port= 443、alpn= ['h2', 'http/1.1']、ws path= /ws?ed=2048
④ 生成后校验挡住"类型对但值坏"的配置（reality 公钥写坏）
   genconfig: 生成的配置没通过内核校验（xray run -test），**未覆盖** out-badreality.json
     Failed to start: … failed to build outbound config with tag proxy > … invalid "password": SHORT
   rc=2 ； 原文件内容 "PRESERVE" 未被动过
```

### 遗留

- 类型体检覆盖的是**节点模型里已知的字段**；对"值合法但语义坏"（如 `pinned_cert_sha256` 给 base64 而不是 hex）靠的是写出前的内核 `-test` 兜底 —— 需要 `--validate-with`（两个调用方都传了：`actions.sh:1171`、`run-xray.sh:57`）。
- `dialer`（浏览器拨号）模式下的 `-test` 也跑，但那条路的 TLS 由 Chromium 完成，`-test` 只能证明"内核认这份 JSON"。
- 校验失败时 `genconfig` 返回 2、调用方 `die`（保留旧配置）—— 行为是"切不过去 + 明确报错"，不是"自动降级到别的节点"；多出站模式仍走 `prune_unbuildable` 的剔除逻辑。

---

## 门禁与回归

```
$ cd /root/deepseek/repos/xray--core && bash tools/check_libs.sh
═══ 结果: 620 通过, 0 失败 ═══              （连跑两次一致；`git archive HEAD` 的干净树里同样 620/0）
```

- 改动前基线：**576 通过 / 0 失败**（`git archive` 出来的 `1366804` 树里实测）。
- 本轮新增 44 条断言（`tools/check_libs.sh`，commit `0e396df`）：mux 决策矩阵 + compat2 判据键集合逐项比对 + `smux` 语义 + PSK 三种长度 + batch 退出码（用真实 `batch_main` + stub 协议脚本）+ 回环发布判据 + 老接口兼容 + ech bool/类型报错/不落盘/内核校验不覆盖。
- 说明：本机并行跑其它命令时曾出现 3–7 条 nginx 组门禁失败，隔离复跑（`conf/nginx_site.sh` 菜单组 13/13）与空载连跑两次均 **620/0** —— 那是并发负载 + 另一路 agent 正在改 `nginx_apply.py / nginx_site.sh` 导致的抖动，与本轮改动无关（本轮没碰这两个文件）。
- 新增门禁自身遵守本仓库的 pipefail 纪律（不用 `| grep -q` / `| head`，否则产出方吃 SIGPIPE，本文件末尾那条门禁会抓）。

## 未完成 + 原因（UNKNOWN 清单）

| # | 事项 | 原因 |
|---|---|---|
| 1 | 在 RN 生产上真正重建这三条节点（新片段 / 新 nginx location / 新分享链接） | 授权范围**禁止写生产路径**；本轮只改代码根因。修复路径已在 P0-3 给出（`nginx_apply.py` + `rebuild_client`） |
| 2 | 端到端证明"CC 生产实例切到 XHTTP 节点后不再有 mux" | CC 生产跑的是 14:29 的旧客户端包，未部署新代码（部署/更新不在本轮范围）。回环证据已足够证明策略生效 |
| 3 | CC 上跑 `Client/tools/interactive-test.sh client --read-only` | 未执行（该客户端测试与并行 agent 在 CC 上的 e2e 活动重叠，且本轮改动不涉及交互菜单）；`check_libs.sh` 620/0 已覆盖 Client 侧的静态契约 |
| 4 | mihomo `smux` 与 Xray `mux.cool` 之间是否存在"可等价"的组合 | **UNKNOWN**：两者协议不同（smux ≠ v1.mux.cool:9527），但都没有官方对照文档；本轮按"不冒充"处理 |
| 5 | `conf/vlessxhttpecn.sh` 交互菜单在 stdin EOF 时会无限循环（`read c` 没有 `\|\| exit 0`，兄弟脚本里已修过这一类） | 发现于沙箱验证过程，**不属于本轮 4 条**，未改。一行可修：`read c \|\| exit 0` |
| 6 | 三条死链的"派生文件为什么没被重建"的**操作者**是谁 | 只能证明是 23:06:45 同一秒恢复/改写了三个片段（内容 == Sep-21 备份），仓库里没有"批量重写 listen/port"的代码；具体是谁执行的那一步 **UNKNOWN**（可能是人工/外部脚本）。修的是"即使发生也不会再发出死链" |

## 附：本轮触碰的文件

`conf/lib/random.sh`、`conf/Shadowsocks.sh`、`conf/Reality.sh`、`conf/Trojan.sh`、`conf/XRevise.sh`、`conf/batch.sh`、`conf/vlessxhttpecn.sh`、`conf/lib/nodes.py`、`conf/lib/share_payload.py`、`conf/share.sh`、`Client/lib/genconfig.py`、`Client/lib/node.py`、`Client/lib/compat2.py`、`tools/check_libs.sh`（只加了本轮的门禁段）。
未触碰：`conf/lib/nginx_apply.py`、`conf/nginx_site.sh`、`conf/node.sh`、`conf/lib/deploy.py`、`conf/fd/xrayserver-reverse.sh`（另一路 agent 在改）、`mihomo--core/*`、`sing-box-core/*`。
