# X 内核 Nginx 生命周期 (含删除/回收) 三方对照 + 9997/9998/9999 溯源

- 日期：2026-10-10
- 被查/被改仓库：`xray--core`（**只改这个**）；对照仓库：`sing-box-core`（SB）、`mihomo--core`（M）—— **只读，未改动**
- 真机：`ssh rn`（107.173.154.178）。RN 上的操作**全部只读**；所有实验在 `/tmp` 沙箱里做（宿主 nginx 1.26.3 + 一个 `127.0.0.1:18080/18443` 的临时 nginx master、假 `docker` shim、python 后端），跑完已删；RN 宿主 `/etc/nginx/conf.d` 复查仍为空，生产 `xrayls`/nginx 未动（见"RN 现场核对"）。
- 行文约定：每条结论后面给 `文件:行` / 命令 / 原文输出；查不动的写 UNKNOWN，不猜。
- **范围说明**：本轮"X 现行路径"= `conf/nginx_site.sh` + `conf/lib/nginx_apply.py`（+ 调用它的 `conf/lib/deploy.py`、`conf/node.sh`、`conf/fd/xrayserver-reverse.sh`）。旧链 `VEVLRE.sh` / `nginx.sh` / `caddy.sh` / `conf/{c,n}nconf.sh` 已被用户判定删除（另一路在删），本文只把它们当**历史做法**提及，一切修复都不依赖它们。

---

## 0 一览

| # | 事项 | 结论 |
|---|------|------|
| 1 | X 现行路径最要命的缺陷 | **插错 server 块**：插入取"文件里第一个 `server{}`"，于是片段会落进 80 口 `return 301` 跳转块、甚至**别的域名**的站里；`nginx -t` 全绿，节点静默不通。SB/M 都按 `server_name` 选块，只有 X 不是 |
| 2 | 第二类缺陷 | 标记只按**域名**索引：同域名下第二条 `location /前缀` 会**替换**掉第一条，删一条会**连坐**另一条（反向隧道链真实可达） |
| 3 | 第三类缺陷 | `location /` 撞车：站点里几乎都有 `location /`，X 默认插 `location /` → 真 nginx `duplicate location "/"` → 只能靠"写完再回滚"兜住，用户看到的是一条看不懂的报错 |
| 4 | 第四类缺陷 | 幂等只做了"文件内容一致"：`--remove` 一个没插过的域名照样覆盖备份槽 + 重写 + reload（把"插入前的原件"抹掉） |
| 5 | 第五类缺陷 | 备份只增不减（与 M 同病）、孤儿只报告不清理 |
| 6 | 已补齐 | 按 `server_name`+TLS 选块 / 同名 location 前置拒绝 / 标记带路径 / 三种删除粒度 / 零副作用幂等 / 备份回收（只回收自己的命名、站点没了不碰）/ 孤儿清理（只认自己的标记）/ 容器与宿主同口径 / 菜单入口。见 §3、§4 |
| 7 | 不要学 | SB `--remove` 忽略 `--domain`（**实测**：删 a 把 b 也删了）、SB `cdn_prune` 按形状认领**实测误删用户手写反代**、SB `--check-http2` **实测 TypeError**、M `-bak` 只增不减（RN 现场 3 个）、SB 探测只认容器名 `nginx`、SB 校验不可用仍照写 |
| 8 | 9997/9998/9999 | **历史遗留**，不是当前 X 生成：来自旧 `VEVLRE.sh → conf/nconf.sh → nginx.sh` 那条链。证据与清理方案见 §5 |

提交（`xray--core` `main`）：

| commit | 内容 |
|---|---|
| `c1` | `fix(nginx): 按 server_name/TLS 选块 + 同名 location 前置拒绝 + 部署按节点 path 落 location` |
| `c2` | `feat(nginx): 标记带 location 路径 + 三种删除粒度 + 零副作用幂等 + 备份回收 + 孤儿清理` |
| `c3` | `feat(nginx): 菜单与调用方接线（精确摘除/备份回收/孤儿清理/反向隧道带路径）` |

门禁：`bash tools/check_libs.sh` → **0 失败**（见 §6）。

---

## 1 三方逐项对照（生命周期 / 含删除）

"X" 列均为**改后**的现行路径；带 ★ 的格子是本轮新补的。

### 1.1 配置放哪 · 命名 · 是否独占片段

| 维度 | X（xray--core） | SB（sing-box-core） | M（mihomo--core） | X 采用哪种 |
|---|---|---|---|---|
| 放哪 | **不新建站点**，插进已有 `server{}`；探测顺序：容器 → `/etc/nginx/{conf.d,sites-enabled}` → `/usr/local/{nginx,openresty}/nginx/conf` → `/etc/nginx`（`nginx_apply.py:145`、`:259`） | 不新建站点；探测：**docker conf.d 的宿主挂载点** → `/etc/nginx/conf.d` → `sites-enabled` → 宝塔 `/www/server/nginx/conf`、`/www/server/panel/vhost/nginx`（`cdn_nginx.sh:96-105`） | 不新建站点；探测：docker conf.d 宿主挂载点 → `HOST_ROOTS`（`nginx_apply.py:66-71`、`:117-133`） | X 的根列表够用；**宝塔两个目录值得学**（记为待补，见 UNKNOWN-6） |
| 读写落在哪一侧 | **容器内**：`c_read/c_write/c_copy` 全走 `docker exec`（`nginx_apply.py:189-232`），容器没把 conf.d 挂出来也能改 | 写**宿主挂载路径**（`cdn_apply.py:137` + `cdn_nginx.sh:28-36`），挂不出来就 `continue`（放弃这个容器） | 写**宿主挂载路径**（`nginx_apply.py:100-113`） | X 更稳（不依赖挂载）；代价是 `--file` 给容器内路径 |
| 命名规则 | 标记 `# >>> xray-core BEGIN <域名>` / `# <<< xray-core END <域名> <<<`；★ 带路径时 tag 为 `<域名>|<location 路径>`（`nginx_apply.py:72-95`、`render_block` 的标记行 `:587`/`:631`）；另有一套 `=== xray-core BEGIN <name> (server 指令) ===`（`RE_BEGIN`：`:66-67`） | `# >>> SB-Panel CDN 开始 (自动生成, 请勿手改) >>>` / `# <<< SB-Panel CDN 结束 <<<` —— **标记里没有域名**（`cdn_apply.py:31-32`） | `# >>> mihomo-core-cdn BEGIN <域名> >>>` / END；外加 `# === mihomo-core-cdn BEGIN <域名> (server 指令) ===`（`nginx_apply.py:55-63`） | 三家都是"标记块"，X 与 M 带域名；**X 再带一层路径**，粒度最细 |
| 是否独占片段 | 不独占：一个站点文件里可以同时有 X / SB / M 三家的段（RN 现场物证：`safety-test.conf.mihomo-core-cdn-bak` 里同时留着 X 与 M 的标记） | 不独占（同上） | 不独占 | 三家一致，标记互不干扰 |

### 1.2 安装/启用 · 幂等

| 维度 | X | SB | M | X 采用哪种 |
|---|---|---|---|---|
| 选哪个 `server{}` | ★ **按 `server_name` 选**（精确 → 通配 → 单一 server 兜底并告警；多个候选优先 TLS 块），选不到就**拒绝**（rc=3，列出文件里的块）（`nginx_apply.py:351-466`、`:1090-1105`） | 按 `server_name` 选块（`cdn_apply.py:44-73`），找不到拒绝 | 按 `server_name` 选块（`nginx_apply.py:194-220`），找不到拒绝 | 三家同口径（X 本轮才对齐）；X 多一条"选中块没有 443/ssl 就提示"（`:1108-1110`） |
| 花括号配对 | ★ 先去注释与引号内容再数括号（`strip_comment`：`:325-349`） | 直接数原行（`cdn_apply.py:67-72`）—— 注释里的 `}` 会让块提前结束 | 先去注释（`nginx_apply.py:223-239`） | 学 M |
| 插入位置 | `server{}` 收尾 `}` 之前（`lines[ins:ins] = block`：`:1134-1136`） | 收尾 `}` 之前（`cdn_apply.py:203`） | `end-1` 之前（`nginx_apply.py:406`，注释里记着"插到 `}` 之后"那个旧 bug） | 三家一致 |
| 同名 location | ★ 插之前先查目标 `server{}` 里有没有同名 location，有就**拒绝并给三条出路**（rc=4）（`RE_LOCATION`：`:663`、`location_paths`：`:666`、`find_location_conflicts`：`:676`、调用点 `:1115-1132`） | 不做；靠写完 `nginx -t` 失败回滚 | 不做（它渲染的就是节点自己的 path，天然避开） | 学 M 的"用节点 path" + X 的提前拒绝（少一次"写了又回滚"） |
| 幂等（重复插入） | 先按 tag 摘旧段再插（`:1011-1048`）；连插 N 次 = 1 段（门禁 + 真机实测） | 先 `strip_existing` 再写 → 幂等，但**多域名共用一个文件时互相清掉**（`cdn_apply.py:75-81`：删的是全部 SB 段，不分域名） | `existing_span` + 替换 → 幂等（`nginx_apply.py:327-338`） | X 与 M 同档；SB 的"整段清"在多域名文件上会互相踩 |
| 禁用（临时关掉） | 无独立"禁用"概念：`--remove`（摘段）或重新插入；**刻意不发明第三态**（注释掉的配置既不参与 `nginx -t`，也没人知道该由谁恢复）（`nginx_apply.py:38-42` 生命周期注释） | 无 | 无（只有"只生成片段不写入"档） | 三家都没有；X 的取舍写在代码注释里 |

### 1.3 删除（本轮重点）

| 维度 | X | SB | M | X 采用哪种 |
|---|---|---|---|---|
| 按什么定位 | ★ **标记块 + tag**（tag = 域名，或 `域名\|/路径`）（`find_all_marked_spans`：`:494-525`） | 只按**标记**，`--domain` 在删除路径上**完全没用**（`strip_existing` 无域名参数：`cdn_apply.py:75-81`、`:146-151`） | 标记 + 域名（`existing_span/existing_dirs_span`：`nginx_apply.py:242-273`） | 学 M，但 X 的 tag 还带路径 |
| 粒度 | ★ 三档：`--remove`（该域名**所有**路径）/ `--path /p`（只那一条）/ `--path /`（只默认那段）（`apply()` 里算 targets：`:1011-1027`） | 只有一档：**该文件里所有 SB 段**（实测见 §2.1） | 一档：该域名的段（+ 自动补入的 server 指令段一起摘） | X 最细；M 的"dirs 段一起摘"值得学，X 已有 `===` 段的配套（`:1051-1056`） |
| 影响面 | ★ 只删自己标记段；同域名别的路径、别的内核的段、用户手写 content 一律不动（门禁断言） | **会连坐**：删 a 把 b 的段一起删（实测） | 只删自己那段；但**同域名多节点**时它靠 tag→域名绑定表重渲染解决（`src/lib/cdn.sh:160-171`），不靠标记 | X 学 M 的"同域名多节点各占一条"，实现方式换成"tag 带路径"（少一个需要维护的绑定文件） |
| 删除的原子性/零副作用 | ★ 没有可摘内容时**一个字节都不写**、不动备份、不 reload（`apply()`：`:1060-1066`；`commit(same_as_before=…)`：`:884-887`） | 没有可删内容时直接 return（`cdn_apply.py:149-151`），这点与 X 同 | 没有"无内容"短路（会照写+照 reload） | X 与 SB 同档 |
| 删节点自动联动 | `node.sh cleanup_nginx_for` 按**节点片段里的 path** 精确摘除，带不到再退回 `--path /`（老标记形态）（`node.sh:213-245`，收尾在 `:237`） | `sb_cdn_cleanup_stale` 一类钩子（`cdn.sh` 里按绑定清理） | `cdn_node_unregister`：按 tag 查绑定表 → 还有别的节点就**重渲染整个域名**，否则 `--remove`（`src/lib/cdn.sh:544-566`） | M 的"重渲染"更彻底（多个 location 一次写对）；X 用"一段一路径"达到同样的不连坐，改动面更小 |
| 残留清理 | ★ `--prune-orphans <存活域名>`：只删**没有对应节点**的标记段，并且**只认自己的标记**（`prune_orphans`：`:1145-1198`）；`node.sh` 孤儿检查会打印可照抄的命令（`node.sh:319-337`） | `cdn_prune.py` **自动删**：判据是"顶层 `location` + `proxy_pass http://127.0.0.1:<端口>` + 端口不在 `--live-ports`"——**按形状认领**（`cdn_prune.py:22-47`） | `cdn_bind_orphan_prune` 按绑定表与实际片段声明的 (路径,端口) 比对（`src/lib/cdn.sh:236-260`） | 学 SB 的"能自动清"这个**能力**，但判据必须换成标记（SB 的形状判据实测会误删用户配置，见 §2.2） |
| 空文件/孤立 upstream/cert | X 摘 upstream 段与 location 段是一套（`find_marked_dirs`：`:542-556`、`apply()` 里 `:1051-1056`）；**不碰** cert 指令（那是用户的） | 不处理 upstream | 有 `=== … (server 指令) ===` 段并随移除一起摘（`nginx_apply.py:329-345`） | X 已对齐 M |

### 1.4 备份 · 回收

| 维度 | X | SB | M | X 采用哪种 |
|---|---|---|---|---|
| 备份命名 | `<站点>.xray-core-bak`（规范一份，回滚用）+ `<站点>.xray-core-bak.<UTC 时间戳>`（历史）（`BAK_SUFFIX/RE_BAK_HIST`：`:697-700`、`rotate_backup`：`:794-828`、`commit` 里调用：`:890`） | `<站点>.sbpanel-bak`、`.sbpanel-prune.bak`（`cdn_apply.py:222`、`cdn_prune.py:91`） | `<站点>.mihomo-core-cdn-bak`（`nginx_apply.py:447`） | — |
| 回收 | ★ 每次写成功后自动回收历史备份，保留最近 N（默认 3）；**只回收自己命名的那一种**；**站点文件已不在时一份都不回收**（可能是唯一副本）（`prune_backups`：`:752-792`、`commit` 里调用：`:926`） | 无回收 | **无回收**（RN 现场 3 个 `.mihomo-core-cdn-bak`，见 §2.4） | X 独有 |
| 备份 ↔ 改动的关系 | 规范备份 = **上一次改动前**的内容（每次写前把旧备份转成历史，所以"插入前的原件"不会被下一次操作抹掉）（`rotate_backup`：`:794-828`） | 每次直接覆盖同一个名字 | 每次直接覆盖同一个名字 | X 独有 |
| 容器模式 | ★ 备份/回收/列目录/删除全走 `docker exec`（`_list_dir/c_remove`：`:703-720`），与宿主同口径（RN 假容器实测） | 宿主路径写 | 宿主路径写 | X 更稳 |

### 1.5 校验 · 回滚 · 环境一致性

| 维度 | X | SB | M | X 采用哪种 |
|---|---|---|---|---|
| 写前 `nginx -t` | ★ 有（`nginx_precheck`：`:831-863`，失败**不动一个字节**，rc=3；`--skip-precheck` 留"就是来修它"的出口） | **没有** | **没有** | X 独有 |
| 写后 `nginx -t` + 回滚 | 有，失败立刻从备份恢复（`reload`：`:930-966`） | 有（`write_and_check`：`cdn_apply.py:217-237`） | 有（`nginx_apply.py:466-497`） | 三家一致 |
| 校验不可用时 | 跳过并**明确告警**；★ `--require-check` 可要求"校验不了就别写"（`:845-863`） | **跳过且照样写**（`nginx_test` 返回 True：`cdn_apply.py:239-252`） | 跳过并提示手工 reload（`nginx_apply.py:468-477`） | X 的显式开关最清楚 |
| reload | `nginx -s reload`（容器 `docker exec <c> nginx -s reload`），**不 restart**（`:955-963`） | 同款（`cdn_nginx.sh:53-80`） | 同款（`nginx_apply.py:505-551`；reload 失败不回滚，注释解释了原因） | 三家一致 |
| 容器探测 | 容器名**或镜像名**含 nginx；`nginx`/`nginx-proxy` 优先（`:98-135`） | 名字或镜像含 nginx（`cdn_nginx.sh:19-37`） | 名字或镜像含 nginx（`nginx_apply.py:93-99`） | 三家同口径（X 上一轮才对齐） |
| 容器 reload/校验 | `docker exec <c> nginx -t` / `-s reload`（`nginx_cmd`：`:138`） | 同 | 同（`config_roots` 里带 `docker exec`） | 一致 |
| 宿主/容器一致性 | ★ 读写/校验/备份/回收全部按"真正跑 nginx 的那一侧"（`:175-232`、`:703-720`）；`NGINX_CONF_ROOTS` 只影响"去哪儿找站点" | 写宿主、校验容器（挂载不一致时**写的是没人读的文件**） | 同 SB | X 一致 |
| reload 后是否等生效 | 不等（reload 是异步的；门禁/文档已说明） | 不等 | 不等 | 一致（实测里我加了 `sleep 0.5` 才观察，见 §6 备注） |

### 1.6 CDN/回源配合

| 维度 | X | SB | M | X 采用哪种 |
|---|---|---|---|---|
| 回源站点识别 | 提示"选中的块看不到 443/ssl"（`:1108-1110`） | `cdn_site_has_tls()`、`--check-http2`（`cdn_nginx.sh:139-142`、`cdn_apply.py:92-115`） | 选块后提示"没看到 listen 443"（`nginx_apply.py:379-381`） | 三家都有；SB 的 `--check-http2` 思路好但实现有 bug（§2.3） |
| 回源 location 用哪个前缀 | ★ 用**节点自己的 path**（`deploy.py:131-154`），`location /` 只在 tcp/raw 这种没有 path 的传输上用 | 用渲染出的片段（`--block`） | 用**绑定表里的 path**（`src/lib/cdn.sh:428-460`） | 学 M（X 本轮对齐） |
| server 级必需指令 | 不自动补；`render_block` 把 `proxy_buffering off` 写进 location（`:613-629`） | `cdn_check_requirements` 只警告不补（`cdn_nginx.sh` 无 / `cdn.sh` 有警告） | 自动补 `client_max_body_size 0 / proxy_request_buffering off / proxy_buffering off` 到 server 块并打标记（`nginx_apply.py:292-309`、`:408-429`） | M 的"自动补 + 打标记 + 不覆盖已有值"是最好的形态；**X 未补**（见 UNKNOWN-5，X 的 ws/xhttp 片段自身已带 `proxy_buffering off`，`client_max_body_size` 仍未管） |
| 片段过期检测 | 无（但 `deploy.py` 一次规划里端口/域名只有一处，天然不会旧；手工 `--block` 才可能旧） | **有**：片段比节点配置旧就中止（`cdn_apply.py:116-136`） | 无（但绑定表会把 (路径,端口) 与片段比对） | SB 这条值得学（X 的 `--block` 路径没有"片段比节点旧"的检查）——记为未补项 |
| 分享元数据里的"经过 nginx" | `tier: nginx` 写在分享元数据里（`deploy.py:112-117`），`node.sh` 用它做清理与孤儿判定（`node.sh:180-190`、`:290-302`） | 无显式字段，靠"CDN 绑定表" | 靠 CDN 绑定表（tag→域名/站点/传输/路径/端口） | X 的 `tier` 够用；**但它只标"这节点在 nginx 后面"，不标"哪一段 location"** → 这是 9997/9998/9999 死链能长期存在的土壤（§5） |

---

## 2 不要学：三家各自的坑（含本轮实测）

### 2.1 SB `--remove` 忽略 `--domain`（实测：删 a 把 b 也删了）

夹具：一个文件里两个站点，各自有一段 SB 标记。命令与输出：

```
$ python3 sing-box-core/src/conf/cdn_apply.py --remove --domain a.example.com --file site.conf --nginx none
[Warn] 未检测到可用的 nginx 校验方式, 跳过语法检查。请自行执行 nginx -t 确认。
[OK] 已从 site.conf 移除 SB-Panel CDN 片段
剩余 SB 标记块: 0      # ← b.example.com 的那段也没了
```
根因：`strip_existing(text)` 只按固定的 BEGIN/END 正则删，**没有域名参数**（`cdn_apply.py:75-81`），`--remove` 分支直接把结果写回（`:146-151`）。`--domain` 在删除路径上是死参数。
**为什么不能学**：用户点"删 a"，b 的站点跟着 502，且现场没有任何提示。

### 2.2 SB `cdn_prune.py` 按形状认领 → **实测删掉用户手写的反代**

夹具（未缩进的 `location`，手写配置里极常见，语法完全合法）：

```
$ python3 sing-box-core/src/conf/cdn_prune.py --file prune.conf --live-ports 31003 --nginx none
将删除孤立 location location /myapp {  → 127.0.0.1:8080
[OK] 已清除 1 个孤立 location: prune.conf (备份 prune.conf.sbpanel-prune.bak)
用户手写的 /myapp: 0     # ← 没了
```
根因：`find_top_level_orphan_blocks` 的判据是"列 0 开始的 `location` + `proxy_pass http://127.0.0.1:<端口>` + 端口不在 live 集合"（`cdn_prune.py:22-47`），**不看标记**。
**为什么不能学**：这正是"用户自己写的反代"，它的端口当然可能不在"我的节点存活列表"里。X 的 `--prune-orphans` 只认 `# >>> xray-core BEGIN … >>>` 配对的段，段外一个字符都不动（门禁里有断言）。

### 2.3 SB `--check-http2` TypeError（实测）

```
$ python3 sing-box-core/src/conf/cdn_apply.py --check-http2 --domain zzz.example.com --file site.conf
  File ".../cdn_apply.py", line 106, in main
    start, end = find_server_block_span(lines, args.domain)
TypeError: cannot unpack non-iterable NoneType object
$ echo $?   # 1
```
根因：`find_server_block_span` 找不到块时返回 `None`（`:73`），调用点按二元组解包（`:106-108`）。
**为什么不能学**：一个只读检查在"域名不存在"这个最常见的输入上直接崩栈。

### 2.4 M 的 `-bak` 只增不减（RN 现场）

```
$ ssh rn 'ls -1 /home/web/conf.d/ | grep -cE "mihomo-core-cdn-bak"'
3
$ ssh rn 'ls -la /home/web/conf.d/ | grep -E "mihomo-core-cdn-bak|sbpanel-bak|xray-core-bak" | wc -l'
5
```
M 的 `commit()` 只 `shutil.copy2(path, bak)`（`nginx_apply.py:447`），没有任何回收；SB 同理（`.sbpanel-bak` / `.sbpanel-prune.bak`）。这些文件 nginx 不加载（不以 `.conf` 结尾），但会一直堆着，让人误判"站点里有我的配置"。
**X 的处置**：规范备份（回滚用）+ 有上限的历史备份；回收范围**只限本工具命名**，且站点文件已不在时一份都不动。

### 2.5 其它

- SB `detect_nginx_mode()` 只认容器名正好等于 `nginx`（`cdn_apply.py:264-276`）——容器叫 `web`、镜像 `nginx:alpine` 就探测不到，于是**校验被跳过、照样写**。X/M 已按"名字或镜像含 nginx"。
- SB 校验不可用时 `nginx_test` 返回"通过"（`cdn_apply.py:239-252`）——"没校验"和"校验通过"在返回值上不可区分。
- SB 帮助文本与代码矛盾：`cdn_menu.sh` 说"✗ 不自动重载 nginx"，而 `:254/:315` 实际调了 `cdn_nginx_reload`（M 的注释已经指出这点，`nginx_apply.py:31-36`）。
- M 的 `nginx_apply.py` 没有前置校验；站点本来就坏时，它会在坏文件上动手再回滚（X 的 `--skip-precheck` 注释里写了这个场景）。

---

## 3 X 现行路径的不足（改前）与补齐（改后）

| # | 不足（改前） | 证据（改前） | 改后 | 依据 |
|---|---|---|---|---|
| 1 | 插入取"第一个 `server{}`" | `find_server_block(lines)` 不看域名；夹具（80 跳转块在前）实测把片段插进 80 块；多站点文件里插进了 `other.example.com` 的块 | `find_server_block(lines, domain)`：按 `server_name`（精确→通配）→ 多候选取 TLS 块 → 无一匹配且文件只有一块则沿用并告警 → 多块匹配不上则**拒绝**（rc=3，列出块清单） | SB `cdn_apply.py:44-73`、M `nginx_apply.py:194-220` 都按域名选块 |
| 2 | 括号计数不认注释/引号 | 旧实现 `ln.count("{") - ln.count("}")` | `strip_comment()`（逐字符，识别引号与 `#`）后再计数 | M `nginx_apply.py:223-239` |
| 3 | 不校验选中的块是不是 443 回源口 | 无 | 选中块看不到 `listen 443/ssl/http2 on` 时提示 | M `nginx_apply.py:379-381` |
| 4 | 默认插 `location /`，站点已有 `location /` 时必然 `duplicate location` | 真机实测：`nginx: [emerg] duplicate location "/"` | ① 部署按**节点 path** 落 location；② 同名冲突**提前拒绝**（rc=4）并给三条出路；③ `--dry-run` 仍可预览 | M 按绑定表的 path 渲染 location |
| 5 | 标记只按域名 → 同域名多路径互相替换/连坐 | `render_block` 的 tag 只有域名；反向隧道 `nginx_wire` 不带 `--path` | tag = `域名` 或 `域名\|/路径`；三种删除粒度；老标记（只有域名）能按"正文里就是那条 location"精确升级 | M 用绑定表解决同域名多节点（`src/lib/cdn.sh:160-171`） |
| 6 | `--remove` 无可摘内容也照写：覆盖备份槽 + 重写 + reload | 旧 `apply()` 无条件 `commit()` | 无内容 → 打印"无需改动"直接返回；`commit()` 再用 `same_as_before` 兜一层 | 幂等的完整含义是"副作用也一致" |
| 7 | 备份只增不减 | 单一 `.xray-core-bak`，无回收 | 规范备份 + 有上限的历史备份（默认 3）+ `--prune-backups` + 菜单入口；**只回收自己命名**，站点没了不碰 | M/SB 的反面教材（§2.4） |
| 8 | 孤儿只报告不清理 | `check_orphan_nginx` 只打印 | 新增 `--prune-orphans <存活域名>`（只删自己的标记段）+ 菜单 7 + `node.sh` 打印可照抄命令 | 学 SB 的"能自动清"，判据换成标记 |
| 9 | 菜单 2"查看站点"只显示第一段 | `find_marked_span(lines, domain)` | 列出该域名**所有**段（含带路径的） | — |
| 10 | 菜单 4"摘除"没有粒度选择 | 只有整域名一档 | 有多段时才追问：全部 / 只一条路径 | — |
| 11 | 备份/孤儿在菜单里没有入口 | 无 | 菜单 6（备份与回收）、菜单 7（孤儿清理） | — |
| 12 | 孤儿检查把 `域名\|/路径` 整个当域名比对 → 带路径的段会被永久当成孤儿 | `re.finditer(r'>>>\s*xray-core\s+BEGIN\s+(\S+)')` 直接用捕获串 | 用 `N.tag_domain()` 取竖线左边 | — |

**未补（明确记录，不在本轮范围）**：宝塔配置根；server 级 `client_max_body_size` 自动补；`--block` 的"片段比节点配置旧"检测；gRPC 过 nginx（`render_block` 对 grpc 只是又写一遍 `proxy_pass`，没有 `grpc_pass`，gRPC 走 nginx 本来就不通）。见 UNKNOWN。

---

## 4 改动清单（文件级）

`xray--core`：

| 文件 | 改了什么 |
|---|---|
| `conf/lib/nginx_apply.py` | 选块按 `server_name`+TLS（`iter_server_blocks/_names_match/_block_is_tls/find_server_block/describe_blocks`）；注释感知括号计数；tag 带路径（`tag_for/tag_domain/norm_path`）；三种删除粒度 + 老标记升级（`find_all_marked_spans/span_declares_location`）；同名 location 前置拒绝（`RE_LOCATION/location_paths/find_location_conflicts`）；零副作用幂等（`same_as_before`）；备份轮转与回收（`rotate_backup/prune_backups/backup_paths/_list_dir/c_remove`）；孤儿清理（`prune_orphans/find_all_marked_spans_all`）；`--require-check`；`--prune-backups/--list-backups/--prune-orphans/--keep/--all` |
| `conf/lib/deploy.py` | nginx 记录带 `path`（ws/httpupgrade/xhttp/h2 用节点自己的 path，tcp/raw 仍 `/`）；`apply_plan` 把 `--path` 传给 nginx_apply（插入与摘除同一个标识） |
| `conf/node.sh` | `cleanup_nginx_for` 从节点片段读出 path 后按 `--path` 精确摘除，带不到再退 `--path /`（老标记）；`check_orphan_nginx` 按域名（tag 取竖线左边）判定，并打印 `--prune-orphans` 安全清理命令 |
| `conf/nginx_site.sh` | 菜单 4 支持"全部 / 只一条路径"；菜单 6 备份列表与回收；菜单 7 孤儿清理（先 `--dry-run` 再确认）；菜单 2 列出所有段 |
| `conf/fd/xrayserver-reverse.sh` | `nginx_wire` 传 `--path <隧道路径>`（否则同域名第二条隧道会替换第一条）；`nginx_unwire` 支持按路径摘（带不到退回整域名） |
| `tools/check_libs.sh` | 新增 13 条门禁（选块/多站点/拒绝/同名冲突/两路径共存与精确删除/零副作用/备份回收与边界/孤儿只删标记/老标记升级/调用方接线） |

---

## 5 9997 / 9998 / 9999：结论、证据、清理方案

### 5.1 结论

**这三个端口是历史遗留（旧 `VEVLRE.sh → conf/nconf.sh → nginx.sh` 那条链生成的），不是当前 X 内核（现行面板路径）生成的。** 结论由用户侧排查给出，本节只补 RN 现场的物证与"能否安全清理"。

### 5.2 证据（RN，全部只读）

**① 谁在听、绑在哪**

```
$ ssh rn 'ss -lntp | grep -E ":999[789]\b"'
LISTEN 0 4096 127.0.0.1:9998 0.0.0.0:* users:(("xrayls",pid=165517,fd=65))
LISTEN 0 4096 127.0.0.1:9999 0.0.0.0:* users:(("xrayls",pid=165517,fd=40))
LISTEN 0 4096 127.0.0.1:9997 0.0.0.0:* users:(("xrayls",pid=165517,fd=7))
```
三个都绑回环、属于同一个 `xrayls` 进程。

**② 谁定义它们 —— 一个文件、一次生成**

```
$ ssh rn 'python3 - <<PY  (读 /root/catmi/xray/conf/nginx.json)'
  tag=VLESS-WS_01        127.0.0.1:9998 proto=vless net=ws    path=/bk4poo5e1q
  tag=VMESS-WS_02        127.0.0.1:9999 proto=vmess net=ws    path=/chgb58f66v
  tag=XHTTP_INBOUND_03   127.0.0.1:9997 proto=vless net=xhttp path=
  tag=REALITY_INBOUND_04 0.0.0.0:19595 proto=vless net=tcp   reality
（四个入站的 uuid 前 8 位都是 48fc355e —— 同一次生成）
$ ssh rn 'stat -c "%y %n" /root/catmi/xray/conf/nginx.json'
2026-09-14 21:01:29 -0700  /root/catmi/xray/conf/nginx.json
```
文件 mtime 2026-09-14；现行面板建的节点片段是另一套命名（`hysteria-0x.json` / `reality-0x.json` / `ss2022-0x.json`，mtime 2026-09-19 ~ 2026-10-10）。

**③ 当前代码里没有出处**

- 现行 `conf/lib/deploy.py` 的 nginx 档只生成 `127.0.0.1:<节点端口>`，端口来自规划输入，没有任何 9997/9998/9999 常量。
- 现行路径里没有出处：`grep -rn "9997\|9998\|9999"` 对 `conf/nginx_site.sh`、`conf/lib/nginx_apply.py`、`conf/lib/deploy.py`、`conf/node.sh`、`conf/lib/node_build.py`、`conf/lib/nodes.py`、`conf/share.sh` **零命中**（原文输出：空）。
- 出处旧脚本在本轮已被另一路删除（`git status` 里是 `D`），用 git 历史取证：

  ```
  $ git show HEAD:conf/nconf.sh | grep -n "999[789]"
  44:      "port": 9998,
  69:      "port": 9999,
  93:      "port": 9997,
  $ git show HEAD:nginx.sh | grep -n "999[789]"
  241:            proxy_pass http://127.0.0.1:9999;
  249:            proxy_pass http://127.0.0.1:9998;
  258:        proxy_pass http://127.0.0.1:9997;
  ```

  RN 上还留着同一批产物：`/root/catmi/xray/conf.bak-20260916-041627/nginx.json`。
- 分享元数据只有一条指向它：`out/share/VLESS-WS_01.json` → `host=107.173.154.178, port=9998, tier=nginx`（mtime 2026-10-09，是现行 `share refresh` 又刷出来的 —— 所以"面板会提到它"，但**定义它的仍是旧片段**）。

**④ 面板认不认它（用现行 registry 读 RN 的真实片段）**

```
$ python3 conf/lib/nodes.py <含 RN conf/nginx.json 的目录>     # 当前仓库的 registry
TAG                  协议     端口    传输    加密      凭据
VLESS-WS_01          vless    9998    ws      -        48fc355e-80af-4ed1-a48c-
VMESS-WS_02          vmess    9999    ws      -        48fc355e-80af-4ed1-a48c-
XHTTP_INBOUND_03     vless    9997    xhttp   -        48fc355e-80af-4ed1-a48c-
REALITY_INBOUND_04   vless    19595   tcp     reality  48fc355e-80af-4ed1-a48c-
```
⇒ 现行 registry 会把这 4 个入站**当节点列出来**（`conf/nginx.json` 就在现行 `CONF_DIR` 里）。注意第 4 个 `REALITY_INBOUND_04` 绑的是 **0.0.0.0:19595**（公网），也是同一次旧生成，分享目录里没有任何东西指向 19595。

**⑤ nginx 里没有它们（死链）**

```
$ ssh rn 'docker exec nginx sh -c "grep -rn \"9997\|9998\|9999\" /etc/nginx/conf.d/"'
（只在 moontv.6896698.xyz.conf.bak-vless 与 .sbpanel-prune.bak 这两个 nginx **不加载**的备份里命中；live 站点零命中）
```

**⑥ 有没有流量**

```
$ ssh rn 'ss -tnp | grep -E ":999[789]\b"'      → 空（当前无连接）
$ ssh rn 'grep -h "999[789]" log/access.log'    → 命中的都是时间戳/端口里的数字巧合，没有这三个端口的请求行
$ ssh rn 'grep -h "999[789]" log/error.log | tail -3'
2026/10/10 05:40:34 [Info] ... listening TCP for XHTTP on 127.0.0.1:9997
2026/10/10 05:40:34 [Info] ... listening TCP(for WS) on 127.0.0.1:9999
2026/10/10 05:40:34 [Info] ... listening TCP(for WS) on 127.0.0.1:9998
```
⇒ 它们在**当前这次服务启动**时被绑定（所以是"活的监听"），但可见日志范围内没有请求行、当前无连接。

### 5.3 能否安全清理：能，但要按"改文件 + 重启服务"而不是"删文件"

要点：
1. **不能只删 `conf/nginx.json` 就完事**：同文件里还有 `REALITY_INBOUND_04`（0.0.0.0:19595）。要么一起摘（推荐，它同样是旧链产物、无分享引用），要么只摘前三个 —— **必须显式决定**。
2. **不要用现行 Node 管理直接删 `nginx` 这个"节点"**：现行 registry 从 `conf/*.json` 取节点，会把这个文件当**一个**节点（tag 名 `nginx`），删它等于整文件下架并 reload，而且它的分享记录文件名是 `VLESS-WS_01.json`（与节点名不一致），`revoke_shares_for nginx` 不一定能吊销到 → 会留下一条指向已消失节点的分享。
3. 三个端口的入站**绑回环、nginx 无站点、分享里 tier=nginx 却无处回源** → 它们对外本来就是不可达的死链；摘掉不会影响任何"能用的东西"。
4. **风险点**：`REALITY_INBOUND_04`(19595) 是公网口；若还有客户端直连 19595，摘掉会断。分享目录里没有任何指向它的记录（已查），但**用户手上可能留着旧链接** → 清理前请确认。

**清理步骤（需用户授权，本轮未执行）**

```bash
# 0) 记录现场（回滚依据）
ssh rn 'set -e
  cd /root/catmi/xray
  cp -a conf/nginx.json  conf/nginx.json.legacy-bak-$(date +%Y%m%d-%H%M%S)
  cp -a out/share/VLESS-WS_01.json out/share/VLESS-WS_01.json.bak-$(date +%Y%m%d-%H%M%S)
  ss -lntp | grep -E "999[789]|19595" > /tmp/before-ports.txt || true'

# 1) 再次确认没有流量（连续观察一会儿，别只看一眼）
ssh rn 'ss -tnp | grep -E ":999[789]\b" ; tail -200 /root/catmi/xray/log/access.log | grep -cE ":999[789]\b"'

# 2) 从配置里摘掉入站（**只改这一个文件，逐行确认后**）
#    直接用编辑器/python 删掉 VLESS-WS_01 / VMESS-WS_02 / XHTTP_INBOUND_03 三个 inbound 对象；
#    REALITY_INBOUND_04(19595) 是否一起删由用户决定（推荐一起删 —— 同一次旧生成、无分享引用）。

# 3) 校验（现行路径的校验命令，见 conf/verify.sh:71）
ssh rn '/root/catmi/xray/xrayls run -test -confdir /root/catmi/xray/conf'   # 期望 rc=0
#    ⚠ 具体开关按实际二进制核对：现行面板里是 `run -test -confdir <dir>`

# 4) 重启并复验
ssh rn 'systemctl restart xrayls && sleep 2
  ss -lntp | grep -E "999[789]|19595" || echo "已消失"
  ss -lntp | grep -c xrayls          # 其余节点仍应在听（清理前 20 个）
  journalctl -u xrayls -n 30 --no-pager | tail -20'

# 5) 摘掉分享残留（那条 tier=nginx 的死链）
ssh rn 'rm -f /root/catmi/xray/out/share/VLESS-WS_01.json'   # 已先备份；或走 share.sh 菜单确认
ssh rn 'bash /root/catmi/xray/conf/share.sh list'

# 6) 回滚（任何一步不对）
ssh rn 'cd /root/catmi/xray && cp -a conf/nginx.json.legacy-bak-<时间戳> conf/nginx.json && systemctl restart xrayls'
```

---

## 6 验证记录

### 6.1 门禁（`xray--core`）

```
$ bash tools/check_libs.sh
═══ 结果: 644 通过, 0 失败 ═══
```
新增 13 条覆盖：80 跳转块在前时插对块 / 多站点文件插进自己的块 / 域名不存在拒绝（rc=3，文件未动）/ 同名 location 拒绝（rc=4，文件未动，`--dry-run` 仍可预览）/ 同域名两路径共存 + `--path` 精确删 + 整域名收工逐字节还原 / 无内容时零副作用（文件与备份 mtime 都不变）/ 备份上限 + 别人备份不动 + 站点没了不回收 / 孤儿清理只删标记（用户手写反代保留）/ 老标记升级不留重复 location / 容器模式写进容器文件 / `node.sh` 带 `--path` 与孤儿清理命令。

### 6.2 RN 真机（真 nginx 1.26.3，`/tmp` 沙箱，只监听 `127.0.0.1:18080/18443`）

沙箱里跑完整个生命周期（`run2.sh`），关键输出：

```
== 1) 插入 (节点 path /HaaDoJ29/)          在 18443 块里: 1 ；-t rc=0 ；HTTP 回源=后端页面 ；站点自己的首页仍是 SITE-ROOT
== 2) 幂等 (再插 2 次)                     标记数=1 ；-t rc=0
== 3) 同域名第二条路径                     标记: BEGIN node.example.com|/HaaDoJ29/  BEGIN node.example.com|/tunnel-a ；-t rc=0
== 4) 只删 /tunnel-a                       本次摘除: node.example.com|/tunnel-a ；剩余 1 段 ；-t rc=0 ；回源仍在
== 5) 全删                                 逐字节还原 YES ；-t rc=0
== 6) 坏配置 -> 前置校验                   rc=3 ；文件未动 YES
== 7) 同名 location -> 前置拒绝             rc=4 ；文件未动 YES
== 8) 后置校验失败 -> 回滚                  rc=1 ；回滚 YES ；-t rc=0
== 9) 备份回收 (5 次改动)                  4 个备份 -> 回收 1 份, 保留 2 份历史 + 规范备份
== 10) 收尾                                -t 通过；临时 nginx 已 quit
```
容器模式（假 `docker` shim，把容器内 `/etc/nginx` 映射到 `/tmp`）：探测到 `web`+`nginx:alpine`、插入落在容器侧文件、宿主同名路径未被创建、容器内备份轮转与回收（保留 2 + 规范）、`--list-backups`、`--prune-orphans --dry-run`、摘除后逐字节还原 —— 全部通过。

**RN 现场核对（只读，清理后复查）**：测试沙箱已 `rm -rf`，测试后端进程 0 个，宿主 `/etc/nginx/conf.d` 为空、`nginx -t` 通过，生产 `xrayls` 监听数 20（与清理前一致），生产 nginx(容器) `nginx -t` 通过。

**一次测试自身的事故与处置（如实记录）**：我的第一版假 `docker` shim **只映射了 `-c` 的命令串、没映射路径参数**，于是传 `--file /etc/nginx/...` 的那几条命令在"容器里"找不到文件（模块正确地报了"站点文件不存在"）。复核 RN 宿主 `/etc/nginx/conf.d` 为空、无任何 `web.example.com.conf*` 残留 ⇒ **没有写进任何生产路径**；随后把 shim 改成"映射所有参数"并重跑，容器模式全部通过。

### 6.3 SB/M 的"不要学"部分

§2.1（`--remove` 忽略域名）、§2.2（prune 误删用户 location）、§2.3（`--check-http2` TypeError）都在 `/tmp` 夹具上用 SB 自己的脚本复现，输出原文见 §2。M 的备份累积数量来自 RN 只读 `ls`。

---

## 7 UNKNOWN（未验证项）

1. **RN 上正在跑的 panel 版本是否列出这四个入站**：RN 部署树里没有 `conf/lib/nodes.py`（是较旧快照），只能用**当前仓库**的 registry 读 RN 的同名文件得到"会列出"的结论 → 真机面板 UI 行为未直接观测。
2. **这三个端口历史上是否从未有过流量**：`ss` 当前无连接、`access.log` 可见范围内无请求行；但 Xray 的 access log 只记代理请求、且日志可能被轮转/清空过 → 只能断言"当前无连接、可见日志无记录"，不能断言"从未被使用"。
3. **`REALITY_INBOUND_04`(19595) 是否有客户端在用**：分享目录无引用（已查），但用户手上可能有旧链接 → 未验证，清理方案里要求用户先确认。
4. **`xrayls run -test -confdir` 的准确开关**：来自现行 `conf/verify.sh:71`，但 RN 上跑的是较旧快照的二进制，未实跑（属生产操作，本轮不做）。
5. **server 级必需指令自动补（M 的做法）未在 X 实现**：`client_max_body_size`（上行 >1m 会 413）目前靠 X 的片段自带 `proxy_buffering off` 兜一部分；xhttp 的 413 场景未在 RN 实测（需要往生产站点插片段）。
6. **宝塔（`/www/server/nginx/conf`、`/www/server/panel/vhost/nginx`）路径**：SB 支持、X 不支持；RN 上没有宝塔环境可测 → 未实现、未验证。
7. **SB `--block` 的"片段比节点配置旧"检测**：X 未实现；X 的 `deploy.py` 路径不存在这个问题（端口与域名一次规划），但手工 `--block` 路径没有防陈旧检查 → 未验证影响面。
8. **gRPC 过 nginx**：X 的 `render_block` 对 `transport=grpc` 只是再写一遍 `proxy_pass`（`nginx_apply.py:607/616/626` 三处 `proxy_pass`，没有 `grpc_pass`），没有 `grpc_pass`/HTTP2 到后端 —— gRPC 走 X 的 nginx 反代**本来就不通**；本轮未改、未实测。
9. **M/SB 在"容器没挂 conf.d 但 nginx 在容器里"的边界行为**：只读代码推断（它们会放弃/写宿主），未在 RN 实测。
10. **多域名共用一个站点文件时 SB 的互相清除影响面**：只读代码 + 夹具复现（§2.1），未在生产验证。

---

## 8 复现命令（只读 / `/tmp`）

```bash
# 选块与同名冲突（不需要 nginx）
cd /root/deepseek/repos/xray--core
python3 - <<'PY'
import importlib.util
spec=importlib.util.spec_from_file_location("na","conf/lib/nginx_apply.py")
na=importlib.util.module_from_spec(spec); spec.loader.exec_module(na)
raw=open('/tmp/two.conf').read(); lines=raw.split('\n')
print(na.describe_blocks(lines))                      # [(行号, server_name, 是否 TLS)]
print(na.find_server_block(lines,'node.example.com'))  # 选中的块
PY

# 真 nginx 沙箱（RN；只监听 127.0.0.1 高位端口）
ssh rn 'mkdir -p /tmp/ngxmod && cat > /tmp/ngxsbx/conf/nginx.conf ... '
# （完整脚本见本轮记录：run2.sh = 宿主沙箱生命周期；run3.sh = 假 docker 容器模式）

# SB 的三个坑（/tmp 夹具，见 §2）
python3 /root/deepseek/repos/sing-box-core/src/conf/cdn_apply.py --remove --domain a.example.com --file site.conf --nginx none
python3 /root/deepseek/repos/sing-box-core/src/conf/cdn_prune.py --file prune.conf --live-ports 31003 --nginx none
python3 /root/deepseek/repos/sing-box-core/src/conf/cdn_apply.py --check-http2 --domain zzz.example.com --file site.conf

# 9997/9998/9999 现场（只读）
ssh rn 'ss -lntp | grep -E ":999[789]\b"; python3 -c "import json;[print(i[\"tag\"],i[\"listen\"],i[\"port\"]) for i in json.load(open(\"/root/catmi/xray/conf/nginx.json\"))[\"inbounds\"]]"'
```
