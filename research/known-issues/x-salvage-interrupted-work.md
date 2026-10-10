# X 内核（`xray--core`）：被平台重启打断的 18 个未提交改动 —— 收口报告

**范围**：只动 `/root/deepseek/repos/xray--core/`。`mihomo--core` / `sing-box-core` 只读，未触碰。
**基线**：`22d5d81`（删旧脚本 8 个，已推送）→ **收口后 `9ecbc17`（已推送）**。
**规模**：18 files changed, **+1243 / −142**（与任务给的数字逐字节吻合）。

---

## 0 结论速览

| 项 | 结果 |
|---|---|
| 18 个文件处置 | **A 完整 18 / B 半成品 0 / C 有风险 0** |
| 回退的 hunk | **0** |
| 补完的 hunk | **0**（无一处需要补） |
| 门禁 | **645 通过 / 0 失败**（基线 620；本批自身把 nginx 那组断言从 0 扩到 13 条） |
| commit | 3 个（按主题分开），已推送到 `origin/main` |
| 真 nginx 沙箱 | **23 通过 / 0 失败**（nginx 1.26.2，源码编到 `/tmp`，只监听 `127.0.0.1:18080/18443`） |
| 纪律 | 全程未写任何生产路径；一次 canary 报警已定位并**完全复原**（见 §4.8） |
| 原定目标未达成 | **6 项**（见 §6），其中 2 项（P1-4 SNI、P2-7 CDN pin）是任务点名要查、但**本批 diff 里根本没有** |
| UNKNOWN | **8 条**（见 §7） |

**一句话**：这 18 个文件不是"半成品堆"，而是三件**各自做完**的事被重启一起按住了 ——
两个主题在仓库既有报告里已有完整意图记录（`x-nginx-and-ports.md` §3/§4、
`research/e2e/interactive-all-protocol-cdn.md` P1-5），第三个主题（菜单 EOF）虽然
没有报告，但 9 个文件的改法完全同构、可独立验证。**没有发现"加了功能加到一半"的东西。**

---

## 1 任务给的三分类，与 diff 实际的对照（先说清偏差）

任务描述里的三类工作与 diff 实际内容有出入，**以 diff 为准**：

| 任务里的说法 | diff 实际 | 处置 |
|---|---|---|
| 分享链路：`conf/node.sh`、`conf/vlessxhttpecn.sh`、`Client/lib/node.py`、`Client/lib/nodefilter.py`（***SNI 丢失、端口/产物一致性、CDN pin***） | `conf/node.sh` 改的**全是 nginx 清理**（按 path 精确摘除 + 孤儿判定），与分享链接无关；`conf/vlessxhttpecn.sh` 只改了 2 处 `read`（EOF）；`Client/lib/*` 是**客户端导入侧**的 trojan+REALITY 修复。**SNI 丢失 / CDN pin 在 diff 里一处都没有** | 按 diff 主题重新分 3 组；SNI/pin 记为未达成（§6-1、§6-2） |
| Nginx：`nginx_site.sh`、`nginx_apply.py`、`deploy.py`、`dns.sh`、`http.sh`、`logs.sh`、`sock5.sh`、`tunnel.sh`、`fd/**` | 其中 `dns.sh / http.sh / logs.sh / sock5.sh / tunnel.sh` **不是 nginx 改动**，是菜单 EOF 空转修复 | 拆到「菜单」主题 |
| 客户端：`Client/lib/compat.py` | 对；与 `node.py / nodefilter.py` 是同一件事的三面 | 合并为「客户端」主题 |

真主题（3 个）：

1. **菜单 EOF 空转**（9 文件 / +79 −35）
2. **Nginx location 按节点 path 精确插入·摘除**（6 文件 / +1096 −106）
3. **客户端 trojan+REALITY 参数丢失 + 丢弃原因说谎**（3 文件 / +68 −1）

---

## 2 逐个文件处置（A/B/C）

判定口径：**A** = 逻辑自洽 + 与已有报告/目标一致 + 能过门禁 + 我独立复现过它的主张；
**B** = 引用了不存在的函数/变量、菜单没接上、缺验证；**C** = 改了行为但看不出依据、
或可能破坏现有功能。

### 主题 1 · 菜单 EOF 空转（9 个，全 A）

根因（统一）：`read` 在 EOF 上返回非 0 **且不修改**变量 → `case` 落到 `*)` 打印
"无效选项" → 回循环顶再 `read` → 再一次失败 …… 永不退出。触发路径全是常规操作
（`</dev/null`、Ctrl-D、管道喂完按键、cron/CI 非交互）。

| 文件 | 类 | 改法 | 证据 |
|---|---|---|---|
| `conf/dns.sh` | **A** | `read -r c \|\| return 0` | 修前 rc=124/1179 行 → 修后 rc=0 |
| `conf/http.sh` | **A** | 同上 + 3 处 `read \|\| return 0` | 修前 rc=124/1059 行 → 修后 rc=0 |
| `conf/logs.sh` | **A** | `read -r c \|\| return 0` | 修前 rc=124/1086 行 → 修后 rc=0 |
| `conf/sock5.sh` | **A** | 同 http.sh | 修前 rc=124/1099 行 → 修后 rc=0 |
| `conf/tunnel.sh` | **A** | `read -p ... c \|\| return 0` | 修前 rc=124/4449 行 → 修后 rc=0 |
| `conf/vlessecn.sh` | **A** | 同 http.sh | 修前 rc=124/1069 行 → 修后 rc=0 |
| `conf/vlessxhttpecn.sh` | **A** | 2 处 `read \|\| return 0` | 修前 rc=124/1403 行 → 修后 rc=0 |
| `conf/fd/legacy/client-reverse.sh` | **A** | `read c \|\| { echo 退出; exit 0; }`（与同文件已有的 `0)` 分支同语义） | 修前 rc=124/1179 行 → 修后 rc=0 |
| `conf/fd/legacy/server-reverse.sh` | **A** | 同上（含 `4) 显示客户端链接` 分支） | 修前 rc=124/1308 行 → 修后 rc=0 |

**核对过的两件事**

- **不是半成品**：我把整个面板可达的菜单脚本都跑了一遍 `</dev/null`。
  `conf/outbound.sh` 与 `conf/verify.sh` 也 rc=124，但它们是**挂起**不是**刷屏**
  （输出分别只有 20 行 / 4 行 —— 等 systemd 与不存在的 xray 二进制），
  与本类无关，**未改**（改了才是越界加功能）。其余菜单脚本 rc=0。
- **改法有更"正统"的住处**：仓库里已有 `conf/lib/read.sh`（提供 `xr_choice`，
  注释里把这个坑写得很清楚："conf/ 下十几个脚本各自复制了一份 …… 漏掉的那个就会
  在自动化里刷屏到超时"），`outbound.sh`/`split.sh` 已经 source 它。
  本批选了**逐文件内联**而不是改用共享 helper。这是风格不一致、**不是缺陷**：
  9 处改动各自正确且可独立验证，改成 `source read.sh` 会扩大爆炸半径
  （`read.sh` 用 `exit 0`，而其中 7 个文件是 `return 0` 语义，直接换会改变
  被 source 时的行为）。**故不动**，只在此记录。

### 主题 2 · Nginx location 按 path 精确插入·摘除（6 个，全 A）

意图有仓库内报告完整背书：`x-nginx-and-ports.md` §3 第 4/5 行、§4 文件级清单、
§6.1「新增 13 条覆盖」——与本批 `tools/check_libs.sh` 的 +180 行逐条对得上。

| 文件 | 类 | 改了什么 | 证据 |
|---|---|---|---|
| `conf/lib/nginx_apply.py` | **A** | +786。按 `server_name` 选块（多块优先 TLS 回源入口，认不出就**拒绝**不猜）；注释感知括号计数；`tag = 域名` 或 `域名\|/路径` + 三档删除粒度；同名 location **前置**拒绝 rc=4；老标记按"正文里就是那条 location"精确升级；内容未变则零副作用；备份轮转与只回收自家命名的历史备份；`--prune-orphans` 只认自家 BEGIN/END 标记段 | 真 nginx 23/0（§4.4）；门禁新增 13 条全绿 |
| `conf/lib/deploy.py` | **A** | nginx 记录带 `path`（ws/httpupgrade/xhttp/h2 用节点自己的 path，tcp/raw 仍 `/`）；`apply_plan` 把同一个 `--path` 传下去（插入与摘除同一标识） | 沙箱：片段落进 443 块；站点首页未被抢走（GET / = SITE-ROOT） |
| `conf/node.sh` | **A** | 删节点时从片段读 path 后 `--path` 精确摘除，读不到退 `--path /`（老标记）；孤儿判定按域名（`N.tag_domain()` 取竖线左边）；给出 `--prune-orphans` 清理命令 | `tag_domain` 确在 `nginx_apply.py:83` 定义（**非悬空引用**）；`LIB_DIR` 在 `node.sh:20` 定义 |
| `conf/nginx_site.sh` | **A** | 菜单 2 列出全部段；菜单 4 支持"全部 / 只一条路径"；**新增菜单 6**（备份回收）**菜单 7**（孤儿清理，先 dry-run 再确认） | 新入口已接线：`nginx_site.sh:332-333`；`local dom scope="" path=""` 已给初值，`set -u` 下不会 unbound |
| `conf/fd/xrayserver-reverse.sh` | **A** | `nginx_wire` 传 `--path <隧道路径>`；`nginx_unwire` 支持按路径摘，带不到退回整域名；`del_tunnel` 读 `REV_SERVER_PATH` | `nginx_wire` 入口已有 `[[ -z "$loc" ]] && return 1`，不会退化成 `--path ""` |
| `tools/check_libs.sh` | **A** | +180：13 条断言覆盖选块/多站点/拒绝 rc=3/同名冲突 rc=4/两路径共存与精确删除/零副作用/备份上限与别人的备份/孤儿只删标记/老标记升级/容器模式/`node.sh` 接线 | 645/0。**没有削弱任何既有断言**，只新增 |

**逐项排掉的 B 类嫌疑（都查过了）**

- 悬空引用：新增的 21 个函数全部有调用点；`tag_path()` 是唯一例外（全仓库无调用，
  与在用的 `tag_domain()` 成对）→ **冗余但无害，未动**。
- `--all / remove_all` 声明了但 `apply()` **从不读**。它是"`--remove` 不带 `--path`"
  的同义开关，帮助文本已写明"不带 --path 时的默认行为"→ **不骗人、无风险，未动**。
- 菜单没接上：`check_orphan_nginx`（`node.sh:497` 菜单 4、`:510` `orphans` 子命令）、
  `_ng_do_backups`/`_ng_do_orphans`（`nginx_site.sh:332-333`）**都已接线**。
- `deploy.py` 的 `opts`：函数开头已 `opts = dict(opts or {})`，`opts.get("path")` 安全。
- **`--remove` 默认语义变化（本批最大的行为改动）**：由"只摘域名那一段"变成
  "该域名全摘"。我把全仓库所有 `--remove` 调用方都过了一遍 ——
  `node.sh` / `nginx_site.sh` / `xrayserver-reverse.sh` 现在**都显式传 `--path`
  或带 yes 确认**，`deploy.py` 只插入不删除。**没有会突然多删的隐藏调用方。**
  （仓库外的历史手抄命令仍有风险，见 §7-3。）

### 主题 3 · 客户端 trojan+REALITY（3 个，全 A）

意图有仓库内报告完整背书：`research/e2e/interactive-all-protocol-cdn.md` P1-5
（含真实链接夹具与复现输出）。

| 文件 | 类 | 改了什么 | 证据 |
|---|---|---|---|
| `Client/lib/node.py` | **A** | `parse_trojan` 收齐 `pbk/sid/spx`（+ 同族 `pin=` → `pinned_cert_sha256`）；`build_link` 的 REALITY 参数移出 `if proto == "vless"`，改为与协议无关 | 夹具往返：pbk/sid 一致，`can_use_xray` True |
| `Client/lib/compat.py` | **A** | 新增 `blocking_reason()`：从判定结果本身取原因；协议真不支持就照实说，协议支持但缺参数就逐条点名缺什么；排除汇总行 | `"内核兼容性"` 字面量与 `compat2.py:603` 一致（已核对）；`bad` 为空时返回 `""`，有兜底 |
| `Client/lib/nodefilter.py` | **A** | 丢弃原因改用 `blocking_reason()`，取不到才退回旧文案 | 5 节点实跑：TROJAN-03 **不再被丢**；另一条真该丢的节点给出真实原因 |

**放回全函数里看过**：`build_link` 的 REALITY 块位于**共用的扁平参数区**
（在 `q = []` 之后、`vmess` 提前 return 之后），所有非 vmess 协议都有 `q` ——
不存在 `NameError` 路径。

---

## 3 补完清单 / 回退清单

**补完：无。回退：无。**

这不是"懒得动"，是**逐项查过没有可补/该退的东西**：

- 没有引用了不存在的函数/变量（`tag_domain`、`LIB_DIR` 都存在；`loc`、`opts`、
  `scope` 都有初值或前置校验）。
- 没有菜单没接上的入口（4 个新入口全部接线）。
- 没有"加了功能加到一半"的东西 —— 三个主题各自闭环，且都有独立可复现的验证。
- 没有"改了行为但看不出依据"的 hunk：Nginx 那批的每一条都能在
  `x-nginx-and-ports.md` §3 找到对应行，客户端那批能在 e2e 报告 P1-5 找到对应行，
  EOF 那批在 9 个文件里同构重复。
- **不确定的一律没提交**：真正不敢确定的 SNI/pin 两项，因为**根本不在 diff 里**，
  我也没有替原作者"顺手补上"（那是新工作，需要单独一轮 + 自己的验证），
  只在 §6 记为未达成。

---

## 4 验证记录

### 4.1 门禁（`bash tools/check_libs.sh`）

```
$ bash tools/check_libs.sh
═══ 结果: 645 通过, 0 失败 ═══      (exit 0；无任何 ✗ 行)
```
- 基线 620 → **645**。差值 25 = 本批 `check_libs.sh` 新增的断言（13 条 nginx 生命周期
  覆盖 + 容器模式等）。
- 在**提交后的干净树**上复跑一次，同为 645/0（`git status` 干净 ⇒ 验证内容与提交内容
  同一份 blob）。
- **未削弱任何断言**：本批对 `check_libs.sh` 只做**新增**，既有断言一字未删；
  唯一被"调整"的是两处既有调用的**入参**（插入夹具时补 `--path /node`），
  原因是那份夹具站里本来就有 `location /`，不补前缀会撞上 `duplicate location`
  —— 这正是本批要修的形态，注释里写明了。

### 4.2 语法与静态检查

```
$ for f in $(git diff --name-only | grep '\.sh$'); do bash -n "$f"; done     # 13 个, 全 OK
$ python3 -m py_compile <5 个改动 .py>                                        # 全 OK
$ shellcheck -S error  (改动前后逐文件对比)                                   # 13 个 .sh 全部 0→0, 无新增
```

### 4.3 面板干净退出

```
$ printf '0\n' | timeout 20 bash xray-panel.sh ; echo $?
0        (38 行输出, 正常打印主菜单后退出)
```

### 4.4 Nginx：真 `nginx -t` 沙箱（`/tmp`，**未碰生产 nginx**）

本机原本没有 nginx（`apt-get download` 也 404）。为做**真实**校验，从源码编了一份到 `/tmp`：

```
nginx 1.26.2   --without-http_rewrite_module --without-http_gzip_module
               --with-http_ssl_module --with-openssl=<源码编的 openssl 3.0.15>
沙箱: -p /tmp/ngxsbx -c /tmp/ngxsbx/conf/nginx.conf
      只监听 127.0.0.1:18080 (80 跳转块) 与 127.0.0.1:18443 (ssl 真站点)
      site.conf 里预先就放着 `location / { index index.html; }`
```

**结果：23 通过 / 0 失败。** 关键几条：

```
== 1) 载重假设: 同一个 server 块里两个 location / 会不会真的 emerg?
      nginx: [emerg] duplicate location "/" in /tmp/ngxsbx/conf/dup.conf:8
  PASS  重复 location / 真会 emerg (rc=1)
        ← 这条证明"按节点 path 落 location"是**必需**的，不是风格偏好
== 2) 按节点 path 插入 (--path /HaaDoJ29/)
  PASS  插入 rc=0 / 真 nginx -t 通过 / 片段插进 443 块 (标记行 14 > 80块 2, 443块 8)
  PASS  站点自己的首页仍由 nginx 提供 (没被 location / 抢走)   [GET / = SITE-ROOT]
  PASS  节点路径精确命中并回源 (无后端 -> 502)                 [GET /HaaDoJ29/ = 502]
== 3) 幂等: 再插 2 次        PASS 标记仍只有 1 段 / -t 通过
== 4) 同域名第二条路径        PASS 两段共存 (不互相替换) / -t 通过
== 5) 只摘 /tunnel-a          PASS 摘除 rc=0 / 另一条 (/HaaDoJ29/) 完好 / -t 通过
== 6) 站点已有 location / 时默认 path=/  PASS rc=4 提前拒绝 / 文件未动 / 报错点名 duplicate location
== 7) 后置校验失败 -> 回滚     PASS rc=1 / -t 恢复通过 (已回滚)
== 8) 整域名摘除              PASS 与原始文件逐字节一致 / -t 通过
== 9) 前置校验: 站点本来就坏   PASS rc=3 前置拒绝 / 文件未动
```

**过程中两个"假失败"，都是我的夹具问题，已排除并如实记录**：

1. 首版夹具缺 `$connection_upgrade` 的 `map` → 插入 rc=1 回滚。核对后确认该变量
   **在 HEAD 里就有**（`git show HEAD:conf/lib/nginx_apply.py | grep -c connection_upgrade`
   = 1，本批 `git diff | grep '^+.*connection_upgrade'` = 0），即**既有行为**，
   发行版 nginx.conf 自带这个 map。补上 map 后通过。
   *顺带白捡一条证据*：这次失败把**后置校验失败 → 回滚**这条路径在真 nginx 上跑通了
   （rc=1 + `[信息] 已恢复到 …` + 文件确实回到原样）。
2. 第二次跑出现 `GET /HaaDoJ29/ = 404`：原因是**两个沙箱 nginx master 同时在跑**
   （第一轮的 4356 占着端口、拿着旧配置，第二轮的 4463 才是被 reload 的那个）。
   清干净单实例重跑 → 502，符合预期。

### 4.5 分享链接：三条点名判据（`/tmp` 沙箱）

用 `conf/lib/nodes.py` 的 `extract()` + `build_share_link()` 造了 4 种形态。

| 判据 | 结果 | 证据 |
|---|---|---|
| **链接端口与监听一致** | **达成**（本批未触碰，属既有 P0-3 修复） | 回环 + `tier=nginx` 节点：`vless://…@node.example.com:443?…` —— 发布的是**前端 443**，不是回环端口 23456；并显式给出 note「元数据里的端口 23456 是节点自己的回环端口, 不是对外端口 —— 已按 nginx 前端的 443 发布」 |
| **TLS 节点链接里有域名 SNI（不是 IP）** | **未达成**（**不在本批 diff 里**） | trojan+ws+TLS（证书 CN=node.example.com）→ 链接 **完全没有 `sni=`**：`trojan://pw1@107.173.154.178:29601?security=tls&type=ws&path=%2Fabc#…`。vless+ws+TLS 同样丢。hysteria2 → **`sni=107.173.154.178`（是 IP）**：`hysteria2://pw3@107.173.154.178:29604?sni=107.173.154.178&insecure=0#…` |
| **CDN 节点不被错误写 pin** | **未达成**（**不在本批 diff 里**） | `conf/vlessxhttpecn.sh:1120` 的判据只有 `[ -f "$CERT_FILE" ]` —— 注释自己写着"用公网 CA 签的证书走正常校验, 不需要 pin"，实现却不区分自签/公网 CA；`CERT_FILE` 的来源含 `/root/catmi/cert-$dom.crt`（`:452`），即公网 CA 证书也会被无条件 pin。库路径 `conf/lib/node_build.py:94` 是干净的（只在显式传入时才写 pin） |

**第 2、3 条的根因在未触碰的文件里**（`conf/lib/nodes.py:95-97` 的 `sni` 只从 REALITY
`serverNames` 取；`:362` 的 `q = {"sni": meta.get("host")}`；`vlessxhttpecn.sh`
的 `render_client`）。**我没有替原作者"顺手补上"** —— 那是新工作，需要单独一轮
+ 自己的验证（§6-1、§6-2）。

### 4.6 EOF 修前/修后对照（9 个文件，逐文件）

`git show HEAD:<f>` 落成临时文件（跑完即删，`git status` 回到 18 个改动），
`stdin=/dev/null`、8s 超时。完整结果见 §2 主题 1 的表。
代表值：`conf/dns.sh` 修前 **rc=124 / 1261 行** → 修后 **rc=0 / 20 行**。

### 4.7 客户端往返（`/tmp` 沙箱，夹具取 e2e 报告原文链接）

```
夹具: trojan://LV7CpzX9Jc8vWuhP0YV0@107.173.154.178:29602?security=reality&type=tcp&
      sni=audio-ssl.itunes.apple.com&fp=chrome&sid=b860a9f0&pbk=GiR4k0uVRhKEWlfD9oRjjv…

1) parse_trojan  → reality_public_key='GiR4…2pgU'  reality_short_id='b860a9f0'
                   sni='audio-ssl.itunes.apple.com'  can_use_xray=True
2) build_link    → 链接含 pbk=/sid=；再解析回来 pbk/sid 完全一致, can_use_xray 仍 True
3) nodefilter 5 个节点实跑 → kept=['TROJAN-03','A','B','D']（TROJAN-03 不再被丢）
   skipped=[['C','节点参数不完整，不是内核不支持 shadowsocks（shadowsocks 是内核原生
             支持的协议）：传输 —— 未知 不在本 Xray 版本支持的传输里']]
             ← 原因来自判定本身，不再是千篇一律的"内核不支持该协议"
```

### 4.8 副作用与纪律（含一次**如实记录的事故**）

- **未写任何生产路径**：`/root/catmi/*`、`/opt/*`、RN/CC 正式配置全程未动；
  `mihomo--core` / `sing-box-core` 只读。
- **一次 canary 报警，已完全复原**：我做"全面板 EOF 扫描"时，`conf/hysteria2.sh`
  在**加载期**就 `mkdir -p`，于是创建了两个**空目录**
  `/root/catmi/xray/Hysteria2` 与 `/root/catmi/xray/state`。
  已 `rmdir`（两者都是空的），并复查 `find /root/catmi -newermt` 确认
  **没有任何文件被新增/修改/删除**，只剩 `/root/catmi/xray` 目录自身的 mtime
  因 mkdir+rmdir 而变。此后所有扫描改用"路径+大小"指纹（不含 mtime）做 canary，
  并**不再**跑会产生加载期副作用的脚本。
- 实验目录已清理：`/tmp/ngxbuild`、`/tmp/ngxinst`、`/tmp/ngxbin`、`/tmp/ngxsbx`、
  `/tmp/xsb`、`/tmp/xsh`、`/tmp/eof_*.sh`、各类临时日志均已删除；
  沙箱 nginx 已 `pkill`（`pgrep -xc nginx` = 0，18080/18443 无监听）。
- 仓库工作区无残留：`git status --porcelain` = 0 行（`__pycache__/` 已被 `.gitignore`）。

### 4.9 推送与凭据

```
$ GIT_PAT=<…> GIT_ASKPASS=<mktemp 700> GIT_TERMINAL_PROMPT=0 git push origin main
   0e396df..9ecbc17  main -> main          (RC=0)
$ shred -u <askpass>; ls /tmp/.gitask.*    → 0 个
$ local HEAD == origin/main == 9ecbc1777d7bb4340b4a20286a6119a7d75be651
```
- askpass 脚本本身**不含密文**（只 `printf '%s' "$GIT_PAT"`，令牌只经环境变量传递），
  用完立刻 `shred -u`。
- 令牌**未落任何文件**：`grep -rl 'github_pat_'` 在 `xray--core/`、`proxy-node-compat/`、
  指定 `/tmp` 产物中均为空；`git config` 无 `credential.*`，remote URL 无内嵌凭据。
- 用了 **1 次** push（三个 commit 一次推完）。

---

## 5 commit 号

| # | commit | 主题 | 规模 |
|---|---|---|---|
| 1 | **`bd2d07d`** | `fix(菜单): stdin 关闭时 read 返回非 0 且不改值 → 菜单 EOF 空转刷屏` | 9 files, +79 −35 |
| 2 | **`ae338cd`** | `fix(nginx): location 按节点 path 精确插入/摘除 (标记带路径) + 备份回收 + 孤儿清理` | 6 files, +1096 −106 |
| 3 | **`9ecbc17`** | `fix(客户端): parse_trojan 丢 pbk/sid → Trojan+REALITY 节点被静默丢弃` | 3 files, +68 −1 |
| | | **合计** | **18 files, +1243 −142** |

三个 commit message 均按任务要求写全了：**原本要做什么（从 diff + 报告推断）/
补完与回退 / 怎么验证的（命令 + 结果）**。

---

## 6 仍未达成的原定目标（留给后续，按优先级）

> 这 6 项**都不是本批引入的回归**，而是"任务描述里点名、但 diff 里根本没有"或
> "报告里明确记为不在本轮范围"的工作。我**没有**替原作者实现，理由见 §3。

1. **P1-4 分享层丢 SNI（最高优先，会让 TLS 类节点经订阅后完全不可用）**
   证据见 §4.5：`conf/lib/nodes.py:95-97` —— `node["sni"]` 只在 REALITY
   `serverNames` 非空时才赋值，普通 TLS 节点恒为 `None`；于是 `build_share_link`
   的 `elif n.get("security") == "tls"` 分支写不出 `sni=`，客户端拿 IP 去校验证书 →
   `x509: cannot validate certificate for <IP> because it doesn't contain any IP SANs`。
   hysteria2 更糟：`:362` 直接把 `meta["host"]`（连接地址）当 SNI，
   实测生成 `sni=107.173.154.178`。**建议**：TLS 类节点的 sni 从
   `tlsSettings.serverName` / 证书 CN 取；hy2 的 `sni` 与 `host` 分离。
   注意 `share_target()`（`:213`）的 `host = meta.host or n.sni` 也吃这个坑。
2. **P2-7 对公网 CA 证书也强制 pin**
   `conf/vlessxhttpecn.sh:1120` 判据只有 `[ -f "$CERT_FILE" ]`，注释与实现相反。
   任何走 CDN/中转或证书轮换的节点都会因此连不上（与 P0-3-B 同源）。
   `conf/hysteria2.sh:713` 有同样的无条件计算。**建议**：判据改成"证书是否自签"
   （issuer == subject 或不在系统信任链里）后再决定 pin。
3. **P1-4 附带**：hy2 分享链接还丢了生成器链接里的 `alpn=h3&upmbps=&downmbps=`
   （e2e 报告 P1-4 第三段），同一轮一起做。
4. **报告明确记为"不在本轮范围"的 4 项**（`x-nginx-and-ports.md` §3 末尾）：
   宝塔配置根（`/www/server/nginx/conf`、`/www/server/panel/vhost/nginx`）；
   server 级 `client_max_body_size` 自动补（xhttp 上行 >1m 会 413）；
   `--block` 的"片段比节点配置旧"检测；**gRPC 过 nginx**
   （`render_block` 对 grpc 只写 `proxy_pass`、没有 `grpc_pass`，本来就不通）。
5. **两处冗余（无风险，本轮故意未动）**：`nginx_apply.py` 的 `--all/remove_all`
   从不被读（与 `--remove` 不带 `--path` 同义）；`tag_path()` 全仓库无调用。
   若下游要清理，属于纯删除的独立小 commit。
6. **菜单 EOF 修复未改用共享 helper**：`conf/lib/read.sh` 已经有 `xr_choice()` 并
   在注释里点名这个坑；本批 9 处是内联改法。若统一，需要一套门禁保证
   `return 0` / `exit 0` 语义在各文件被 source 时不被改变。

---

## 7 UNKNOWN（未验证项）

1. **生产站点上的 nginx 行为未实测**。我只在 `/tmp` 沙箱（单域名、两个 server 块、
   `location /` 一条）验过；宝塔多域名共用站点文件、容器挂载、`include` 嵌套、
   `stream{}` 并存的形态**未跑**。容器模式只有门禁里的假 `docker` shim 覆盖
   （`x-nginx-and-ports.md` §6.2 记过作者在 RN 上跑过真容器，但**那不是我验的**）。
2. **`duplicate location` 只在 nginx 1.26.2 上复现过**，且是我自己编的构建
   （`--without-http_rewrite_module --without-http_gzip_module`）。生产 nginx
   版本/模块不同时的行为未直接验证 —— 但该检查在 location 解析核心，版本差异风险低。
3. **`--remove` 默认语义变化的仓库外影响面未验证**。仓库内所有调用方已核对（§2 主题 2），
   但用户手上/别的机器上**旧版脚本或手抄命令**里的 `--remove --domain D` 现在会多删
   同域名下别的路径段。是否有这种调用方、有多少，**未查**（无从查）。
4. **门禁计数对不上 1**：`x-nginx-and-ports.md` §6.1 记的是 **644**，我实测 **645**。
   差 1 未定位（可能在报告写完后作者又加了一条断言；也可能与
   "本机没有 xray 二进制 → 跳过内核校验用例"那组有关）。不影响"0 失败"的结论。
5. **`conf/fd/legacy/*.sh` 是否仍是用户可达入口未确认**。仓库内无调用方
   （只有 `conf/lib/addr.sh:9`、`conf/lib/random.sh:8`、`conf/vlessxhttpecn.sh:80`
   的**注释**提到它们；`vlessxhttpecn.sh:80` 还说 `random_path` "这里调到的是空"）。
   若确属死代码，这两个文件的 EOF 修复对现行面板**没有实际影响** ——
   修复本身正确，但价值未知。
6. **`blocking_reason()` 依赖跨文件字面量**：它用 `c.get("item") != "内核兼容性"`
   排除汇总行，而该字面量由 `compat2.py:603` 产生。当前两边一致（已核对），
   但**没有门禁断言钉住这个契约** —— 将来任一侧改名，会静默退化成
   "把汇总行当原因念出来"。是否要加断言，未定。
7. **备份保留份数在生产上的合理性未评估**：`BAK_KEEP_DEFAULT` 是按"别只增不减"
   的思路定的，没有按真实站点的改动频率/磁盘占用评估过。
8. **`--prune-orphans` 传空存活列表（= 所有标记段都算孤儿）未在真实站点演练**。
   有 `--dry-run` + 二次确认兜底（`nginx_site.sh` 菜单 7），`node.sh` 在
   "一个存活节点都没有"时也只打印提示、不给自动命令 —— 但"一次删掉所有标记段"
   仍是大动作，**未实测**。

---

## 8 复现命令（只读 / `/tmp`）

```bash
# ---- 门禁 ----
cd /root/deepseek/repos/xray--core && bash tools/check_libs.sh      # 645 通过 / 0 失败

# ---- EOF 修前/修后（不写任何东西）----
cd /root/deepseek/repos/xray--core
git show HEAD~2:conf/dns.sh > /tmp/x.sh && timeout 8 bash /tmp/x.sh </dev/null | wc -l   # 1261 行 (挂)
timeout 8 bash conf/dns.sh   </dev/null | wc -l                                          # 20 行   (干净)
rm -f /tmp/x.sh

# ---- 客户端往返（PoC，不写仓库）----
cd /root/deepseek/repos/xray--core/Client/lib
python3 -c "
import importlib.util,sys
def L(n,p):
    s=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
N=L('node','node.py'); C=L('compat','compat.py')
u='trojan://LV7CpzX9Jc8vWuhP0YV0@107.173.154.178:29602?security=reality&type=tcp&sni=audio-ssl.itunes.apple.com&fp=chrome&sid=b860a9f0&pbk=GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU#TROJAN-03'
n=N.parse_trojan(u); print(n['reality_public_key'][:12], C.check_all(n)['can_use_xray'])
print(N.build_link(n))"

# ---- 分享层 SNI（现存缺陷，§6-1）----
cd /root/deepseek/repos/xray--core && sed -n '93,98p;208,216p;357,366p' conf/lib/nodes.py

# ---- CDN pin（现存缺陷，§6-2）----
cd /root/deepseek/repos/xray--core && sed -n '1116,1126p' conf/vlessxhttpecn.sh
```
