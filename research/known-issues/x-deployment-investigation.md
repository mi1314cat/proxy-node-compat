# X 内核（xray--core）部署侧 4 个问题：调查 / 对照 / 修复

- 日期：2026-10-10
- 被查仓库：`xray--core`（可改，已改）；对照仓库：`sing-box-core`（SB）、`mihomo--core`（M），**只读，未改动**（`git status --porcelain` 均为空）。
- 真机对照：`ssh rn`（107.173.154.178）。**只读**查看三家的生产部署；所有实验在 `/tmp`、`ip netns`（一次性，已删）里做，跑完清理；**没有写 RN 上任何生产路径、没有动任何正式服务**。
- 纪律：每条结论后面都有 `文件:行` + 命令 + 原文输出。查不动的写进 UNKNOWN，不猜。
- 提交：`xray--core` **7dfe2a5**（`main`，已推送；`git ls-remote origin main` = `7dfe2a578cc46c783ce145d48017774382ba0f33`）。只提交了本次改动的 11 个文件；同工作区另一路并行 agent 的未跟踪文件（`Client/tools/cc-verify-v2*.sh` 等）**未纳入**。

## 一览

| # | 问题 | 结论 | 已修？ |
|---|------|------|--------|
| Q1 | 分享链接取的是 WARP 出口 IP | 取地址的**源头**（`conf/XRevise.sh` 问 `api.ipify.org`）取错了：那答的是出站出口。SB 的做法是**从网卡取**（`ip -4 -o addr show scope global` + 排除私网/隧道网卡，`sb_real_ipv6`/`default_server_ip_real`）。已把 X 的取址统一收进 `conf/lib/addr.sh`（默认路由网卡优先 + 排除 warp/tun/docker/私网 + 存量值必须过"客户端连得上"自检），并接上 6 个调用点 | ✅ 已修 |
| Q2 | 绑回环是不是走 CDN/Nginx？配置自洽吗？ | 绑回环 = 必须经 Nginx（或 CF→Nginx）才能被外部访问，**理解正确**；但 RN 上**不自洽**：6 个回环入站（9997/9998/9999/31722/41721/45630）+ `tier=nginx` 的分享元数据，而本机 nginx 里 **X 的站点配置一个都没有**（只有 SB/M 的 location）→ 这些节点是死链 | ⚠️ 代码未改（属部署与交互设计问题，见该节"建议"） |
| Q3 | 这套 Nginx 转发有没有问题 | X 的**插入/摘除本体是好的**（标记块 + 幂等 + 备份 + 写后 `nginx -t` + 回滚 + 容器感知），比 SB 的整片段插入更精细；缺陷在**周边**：容器探测只认容器名、孤儿检查只看宿主目录且把备份文件当站点、缺**写入前置** `nginx -t`。SB 有 `--remove` 忽略 `--domain`、整片段插入、prune 会误删用户 location；M 有 `-bak` 只增不减、`--check-http2` TypeError | ✅ 已修 3 处 |
| Q4 | X 的 HY2 支持 obfs / 端口跳跃吗 | X 的 `protocol:"hysteria"` 入站**是 Hysteria2 线协议兼容的**（官方 hy2 客户端实测连上并成功代理 TCP）；**不支持 obfs**（配置里写 obfs 被静默忽略：开 salamander 的客户端连不上、不开的能连上）；**端口跳跃不是内核能力**，靠 iptables REDIRECT + 链接里的 `mport=`。链接里硬编码的 `&obfs=none` 会让 **mihomo 整条订阅加载失败**（实测原文 `missing obfs password`） | ✅ 已修（去掉 `obfs=none`） |

改动文件：`conf/lib/addr.sh`、`conf/XRevise.sh`、`conf/Reality.sh`、`conf/Trojan.sh`、`conf/vlessecn.sh`、`conf/vlessxhttpecn.sh`、`conf/share.sh`、`conf/hysteria2.sh`、`conf/lib/nginx_apply.py`、`conf/node.sh`、`tools/check_libs.sh`（新增门禁）。
门禁：`bash tools/check_libs.sh` → **575 通过 / 1 失败**；唯一失败来自**兄弟 agent 新建的未跟踪文件** `Client/tools/cc-verify-v2.sh`（不在本次提交里，未动）；排除它后同一条门禁命中 0（见文末"门禁与验证"）。

---

## Q1 · 分享链接取的是 WARP 出口 IP，而不是服务器入口 IP

### 结论

X 里"分享链接用哪个地址"分两段：

1. **地址的源头是错的**（这是根因）：`conf/XRevise.sh` 用 `curl -s4 https://api.ipify.org` 取地址，写进 `install_info.env` 的 `PUBLIC_IP` / `link_ip`。`api.ipify.org` 答的是**出站出口**；RN 上开着 WARP，于是存进去的是 `104.28.201.80`。
2. **消费端照抄不校验**：`conf/Reality.sh` 从 env 读 `link_ip` 直接拼分享链接（`conf/Reality.sh:365`），`cconf.sh:196` / `nconf.sh:210` / `Conversion.sh` 同理。

### 证据

- 现象（RN 生产）：`/root/catmi/xray/install_info.env` →`link_ip="104.28.201.80"`、`PUBLIC_IP="104.28.201.80"`；`/root/catmi/xray/out/reality-share-01.txt` 与 `-03.txt` 的地址都是 `104.28.201.80`。而 `ip route get 1.1.1.1` → `via 107.173.154.1 dev eth0 src 107.173.154.178`。
- 源头代码（修复前）：`conf/XRevise.sh:103-104`
  ```bash
  PUBLIC_IP_V4=$(curl -s4 https://api.ipify.org || true)
  PUBLIC_IP_V6=$(curl -s6 https://api64.ipify.org || true)
  ```
- 消费端（修复前）：`conf/Reality.sh:178` 读 env → `:315` 写客户端 outbound 地址 → `:349` 写 mihomo YAML → `:365` 拼分享链接。
- 已存在的**部分**修复：`conf/lib/addr.sh`（`852a4ec`/`975acb3`）已把 hysteria2 / outbound / Shadowsocks / share / http 五处收口，但 **Reality / Trojan / XRevise / vlessecn / vlessxhttp 五处仍在自己取地址** —— 这正是用户看到的那条链接走的路。

### SB 是怎么取的（用户线索的答案）

- 单一实现都在 `sing-box-core/src/conf/lib.sh`：
  - 隧道网卡正则：`lib.sh:150` `SB_TUNNEL_IFACE_RE='^(warp|wg[0-9]*|tun[0-9]*|tap[0-9]*|utun[0-9]*|tailscale|ts[0-9]*|ppp[0-9]*|zt|meta|he-ipv6-tun)'`
  - 真实 IPv6：`lib.sh:157-169 sb_real_ipv6()` —— `ip -6 -o addr show scope global`，逐行取第 2 列接口名、第 4 列地址，**命中隧道正则就跳过**；注释原文：`为什么不能用 "问外部 API 拿出口 IP": 套了 WARP 时, 那条查询本身就走 WARP, 返回的是 WARP 地址 (2606:4700:...)`。
  - 对外地址：`lib.sh:180-187 default_server_ip_real()` —— `ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1 | grep -vE '^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)' | head -1`，没有 v4 再退 `sb_real_ipv6`；注释：`刻意不查外部 API —— 那会经 WARP 拿到 WARP 地址。宁可返回空, 也不要给用户一个连不通的地址`。
  - `sb_addr4()`（`lib.sh:211-217`）在网卡取不到时才 `curl -4 ip.sb` 兜底。
- M（mihomo）侧同类：`mihomo--core/src/lib/env.sh` 走 docker 挂载/宿主探测；M 的 CDN 片段与 nginx 集成见 Q3。
- **SB/M 都没有用"默认路由网卡优先"** —— 这一点是 X 这次做得比它们更严（见下）。

### 修复方案（已实现）

统一入口收在 `conf/lib/addr.sh`，所有产出地址的地方都走它：

| 位置 | 改法 |
|------|------|
| `conf/lib/addr.sh:104` | 新增 `x_default_route_iface()`：`ip -4/-6 route show default` 里取 `dev` |
| `conf/lib/addr.sh:116` | 新增 `_x_addr_pick <4\|6> <strict\|any>`：**两遍扫描**（先默认路由网卡、再全量），两遍都过 `X_TUNNEL_IFACE_RE` + 私网过滤 |
| `conf/lib/addr.sh:138-143` | `x_addr4_real` / `x_addr6_real` / `x_iface_public_addr` 改走 `_x_addr_pick`（停止"枚举顺序第一个"） |
| `conf/lib/addr.sh:85` | 新增 `x_addr_is_reachable()`：在"在本机接口上"之外再排除隧道网卡与私网 |
| `conf/lib/addr.sh:152` | `x_public_addr` 沿用存量值时改用 `x_addr_is_reachable`（**关键**：warp 上的地址"确实在本机"，旧自检放它过去） |
| `conf/lib/addr.sh:238` | 新增 `x_link_addr()`：`XRAY_PUBLIC_IP` > 存量值(过自检) > 网卡 > 外部探测(仍自检) |
| `conf/XRevise.sh:151-193` | 删掉 `curl ipify`，改 `x_addr4_real`/`x_addr6_real`；网卡确实没有才退回外部探测且**明确告警**；支持 `XRAY_PUBLIC_IP`；选中后过 `x_addr_is_reachable` 自检 |
| `conf/Reality.sh:94,207-215` | 新增 `resolve_public_ip()`，`prepare_env` 里现场校正 env 里的 `PUBLIC_IP`（不一致就告警换掉，并重建 `link_ip` 的 IPv6 方括号） |
| `conf/Trojan.sh:345-347,367,370` | `hostname -I \| awk NR==1` → `x_link_addr "$PUBLIC_IP"`；链接用 `x_url_host` 加方括号（原来 IPv6 会拼错） |
| `conf/vlessecn.sh:202` / `conf/vlessxhttpecn.sh:194` | 先读网卡，网卡没有才问外部服务（原来是 `api.ipify.org` 优先） |
| `conf/share.sh:289-297` | 分享 URL 的兜底从 `hostname -I` 换成 `x_iface_public_addr`（再兜底才用含私网的接口地址） |

### 验收（RN 真机，只读，`/tmp/addrtest` 已清理）

```
$ bash addr.sh ifaces            # eth0 107.173.154.178 ★ 可用 ... warp/docker0/br-*/awg0 隧道/虚拟(排除)
$ bash addr.sh route             # eth0
$ bash addr.sh show              # 107.173.154.178     <- 真实入口 IP（修复前是 104.28.201.80）
$ bash addr.sh v6addr            # 2001:470:c:cf:bf47:...  （HE 的真实地址，不是 warp 的 2606:4700:...）
$ x_public_addr "" 104.28.201.80 # 107.173.154.178     <- 存量 WARP 地址被否决
$ addr.sh check 104.28.201.80    # 不在本机接口上 ❌
$ x_public_addr "" 2606:4700:110:822e:...  # 107.173.154.178  <- warp 上的公网 v6 也被否决（旧自检会漏）
$ XRAY_PUBLIC_IP=1.2.3.4 x_link_addr 172.16.0.2  # 1.2.3.4  <- 显式指定最优先
```

### 多网卡 / 多 IP 时怎么选（判据顺序，写在代码注释里）

1. `XRAY_PUBLIC_IP` 显式指定 —— 永远最高优先（NAT/多出口只有用户知道哪个对外可达）。
2. 存量值（env 里那个）—— 必须过 `x_addr_is_reachable`：在本机接口上 **且** 不是隧道/虚拟网卡 **且** 不是私网。
3. 网卡地址 —— **默认路由所在网卡优先**（`ip route show default` 的 `dev`），同一张网卡上取第一个非隧道、非私网地址；该网卡没有就全量扫一遍同样的过滤。
4. 外部探测（`ip.sb` / `api.ipify.org` / `ifconfig.me`）—— 只有 1–3 全空才走，且答案仍要过 `x_addr_is_reachable`，不过就当"世界看到的我"并**告警**让用户核对。
5. 含私网的接口地址 —— 最后兜底（NAT 机器），告警提示需要端口转发或 `XRAY_PUBLIC_IP`。

IPv4 优先于 IPv6（`x_iface_public_addr` 先 v4 再 v6）；`x_addr4_real`/`x_addr6_real` 分开给需要显式选族的调用方（XRevise 的交互选择）。

---

## Q2 · 绑回环 = 走 CDN？经 Nginx 转发？

### 结论（三句话）

1. **哪些绑回环**：`vlessxhttpecn.sh` 的 `ACCESS_MODE=nginx` 档（`conf/vlessxhttpecn.sh:498,533,774` → `LISTEN_ADDR="127.0.0.1"`）与 `conf/nconf.sh`（`conf/nginx.json` 里 9997/9998/9999 三个入站，`conf/nconf.sh:43,68,92`）。其余协议（Reality / Trojan / SS2022 / hysteria / `ACCESS_MODE=cdn` 的 xhttp）绑 `0.0.0.0`。
2. **设计意图**：绑回环就是**只给本机反代回源**——要么给本机 Nginx，要么给 CF→Nginx 这条链。用户的"绑回环 = 必须经 Nginx/CDN 才能被外部访问"**理解正确**。
3. **当前配置不自洽**：RN 上 6 个回环入站**没有任何 Nginx 站点点它**，而且 X 的分享元数据还把其中 2 个当成可连节点对外发布 → **典型"绑了回环但没有 Nginx 转发"**。

### 证据

- X 侧设计：`conf/vlessxhttpecn.sh:573-604 render_nginx_conf()` 把片段写到 `$OUT_DIR/${PROTO}_nginx-$idx.conf`，内容是
  ```
  # vless-xhttp-01 (XHTTP, 端口 25333)
  location /HaaDoJ29/ { proxy_ssl_server_name on; proxy_pass https://127.0.0.1:25333; ... }
  ```
  并只**提示用户自己粘贴**（`:1252 提示: 将片段放入 nginx conf.d 里站点配置的 server{} 块中即可`）——不自动安装。
- RN 生产（只读）：
  - 监听：`ss -lntp` → `127.0.0.1:9997/9998/9999/31722/41721/45630` 全是 `xrayls`；`127.0.0.1:19595`? 见下。
  - 入站配置：`/root/catmi/xray/conf/nginx.json` → `vless 127.0.0.1:9998 tag=VLESS-WS_01; vmess 127.0.0.1:9999 tag=VMESS-WS_02; vless 127.0.0.1:9997 tag=XHTTP_INBOUND_03`；`vless-xhttp-01/02/03.json` → 分别 `127.0.0.1:45630 / 31722 / 41721`。
  - **本机 nginx 里 X 的站点配置：0 个**。宿主 `/etc/nginx/{conf.d,sites-available,sites-enabled}` 只有 `default` 与 `torrent-tool.conf`（8787→127.0.0.1:8788）；真正生效的站点在 nginx **容器**（`nginx:alpine`，`network_mode=host`，挂载 `/home/web/conf.d`）里，live 文件 `hxicc.catmicos.dpdns.org.conf` 的活跃 location 全部指向 **SB（31003/31006/31007）与 M（25677-25681）**，`grep -c xray-core` = **0**。
  - iptables 里也没有这些端口的转发：`iptables -t nat -S | grep -E '9998|45630|...'` → 空。
  - 分享元数据仍把它们当可用节点发布：`/root/catmi/xray/out/share/VLESS-WS_01.json` → `{"host":"107.173.154.178","port":9998,"tier":"nginx"}`（`tier=nginx` 说明 X 认为它在 nginx 后面）；`vless-xhttp01.json` → `{"host":"107.173.154.178","port":45630}`。→ 外部连 `107.173.154.178:9998` 必然失败。
  - 片段是**陈旧的**：`/root/catmi/xray/out/vless-xhttp_nginx-01.conf` 写的是 `proxy_pass https://127.0.0.1:25333`，而节点实际监听 45630（换端口时没有重写旧片段）→ 即使照抄粘进 nginx 也回源到空端口。

### 为什么"CDN 也救不了它"

Cloudflare 只能回源到**服务器公网地址上的端口**；入站只听 `127.0.0.1`，CF 怎么也到不了它 —— 必须先有一个本机反代（Nginx）把路径接出来。所以绑回环的节点**必须**配套 Nginx，二者缺一即死链。

### 建议（本次未改代码，属交互/校验设计）

- 生成 `ACCESS_MODE=nginx` 的节点后**立刻校验**：本机是否存在能匹配该域名的站点点（`nginx_apply.find_site`），没有就**显式警告并给出可粘贴的片段路径**，而不是静静地生成一条死链。
- 换端口时重写对应 `*_nginx-*.conf` 片段（或把片段里的端口标成"必须与节点一致"的校验项）。
- `check_orphan_nginx`（`conf/node.sh`）现在只查"站点里有标记但节点没了"；反向的"节点是 nginx 档但站点里没有它"目前没有检查 —— 这正是本次事故的形态。

---

## Q3 · 这套 Nginx 转发有没有问题？（对照 SB / M）

### 三家逐项对比

| 维度 | X（xray--core） | SB（sing-box-core） | M（mihomo--core） |
|---|---|---|---|
| 配置放哪 | **不新建站点**；插进用户已有 `server{}`（`conf/lib/nginx_apply.py`），路径探测：容器挂载 → `/etc/nginx/{conf.d,sites-enabled}` → `/usr/local/{nginx,openresty}` | 不新建站点；`src/conf/cdn_nginx.sh:96-105` 探测 docker→宿主→宝塔目录；片段产物 `out/sb_cdn-nginx-location.conf` | 不新建站点；`src/conf/nginx_apply.py:117 config_roots()` 同款探测 |
| 插入方式 | **只动自己的标记段**：`# >>> xray-core BEGIN <domain> >>> … # <<< xray-core END <domain> <<<`（`:322-397`），插在 `server{}` 的收尾 `}` 前（`:404-406` 注释记录了"插到 `}` 之后"那个旧 bug） | **整片段插入**：`cdn_apply.py:196-204` 把整个 `--block`（可能含多个域名）写进去，`strip_existing` 先摘自己的 BEGIN/END | 标记段插入，`MARK="mihomo-core-cdn"`，另有 server 级指令段 |
| 幂等 | 插入前先摘自己上一轮的段（`:522-533`）→ 连插 3 次仍 1 段（门禁实测） | 幂等（替换而非追加），但**多域名共用一个 .conf 时互相清掉** | 幂等（`existing_span` + 替换） |
| 删除 | `--remove` 按**标记+域名**摘除；删节点时 `node.sh cleanup_nginx_for` 自动摘（`conf/node.sh:214-221`） | `--remove` **忽略 `--domain`**（`cdn_apply.py:148-156` 只按标记删）→ 实测"删 a 把 b 也删了" | `--remove` 按标记+域名 |
| 备份/回滚 | `<file>.xray-core-bak`，写前备份 → 写后 `nginx -t` → 失败立刻回滚（`:461-499`） | `<file>.sbpanel-bak` 同理，prune 也有 `.sbpanel-prune.bak` | `<file>.mihomo-core-cdn-bak`，**只增不减**（RN 上 4 个） |
| `nginx -t` | 写后校验 + 回滚；**本次新增写入前置校验**（`:434 nginx_precheck`，失败不动文件、rc=3，`--skip-precheck` 留出口） | 只有写后校验；检测不到 nginx 时**跳过且照样写**（`cdn_apply.py:250-252`） | 写后校验 + 回滚 |
| 容器感知 | `probe_docker()` + `c_read/c_write/c_copy` 走 `docker exec`（原来只认容器名 `nginx`/`nginx-proxy`，**本次修**） | `cdn_probe_nginx` 按"容器名或镜像名含 nginx"匹配（本次把 X 对齐到它） | 同名/同镜像匹配 |
| 孤儿处理 | `check_orphan_nginx`（只报告不自动删）；**本次修**：改走 nginx_apply 的探测（容器/宿主一致、只认 `*.conf`） | `cdn_prune.py` 按"指向已死端口的 location"**自动删** —— 实测会**误删用户自己写的** `location /myapp { proxy_pass http://127.0.0.1:8080; }` | `cdn_check_residue` 只检测；另有 `cdn_bind_prune_orphan` |
| reload | `nginx -s reload`（容器则 `docker exec <c> nginx -s reload`），**不 restart** | 同款，不 restart | 同款 |

### X 的问题清单与处置

| # | 问题 | 证据 | 处置 |
|---|------|------|------|
| 1 | `probe_docker()` 只精确匹配容器名 `nginx`/`nginx-proxy`；容器叫 `web`、镜像是 `nginx:alpine` 时探测返回 None，于是又去改宿主上 nginx 根本不读的文件（提示写入成功、reload 也成功、站点毫无变化） | `conf/lib/nginx_apply.py:40-59`（修复前 `if name in ("nginx","nginx-proxy")`) | ✅ 改为"容器名或镜像名含 nginx"，精确名优先；门禁新增两条（`web`+`nginx:alpine`、多容器里挑 nginx 那个） |
| 2 | 孤儿检查直接 `grep -r` 宿主目录：① nginx 在容器里时**扫不到**真正生效的站点 → 报"没有发现"的假结论；② 把 `*.xray-core-bak`/`*.yaml` 这些 nginx 不加载的文件也算孤儿 | `conf/node.sh:231-245`（修复前 `for d in /etc/nginx/conf.d …; grep -rhoE …`） | ✅ 改走 `nginx_apply.site_files/c_read`（容器/宿主同口径、只列 `*.conf`）；门禁新增三条（宿主夹具 / 备份文件不算 / 假 docker 容器里查得到） |
| 3 | 只有**写后** `nginx -t`：站点本来就是坏的时候，会先改坏文件、再回滚，把"配置坏了"记在这次操作头上 | `conf/lib/nginx_apply.py:461-499` | ✅ 新增 `nginx_precheck()`（`:434`，`apply()` 在 `:566` 调用）：失败不动文件、返回 3；`--skip-precheck` 保留"就是来修它"的出口；门禁新增三条（rc=3 / 文件未动 / 无多余备份 / `--skip-precheck` 仍能回滚） |
| 4 | 备份文件 `<file>.xray-core-bak` 只增不减（每次写覆盖同一个）。**不是**加载项（不以 `.conf` 结尾），但会堆积 | `:428`；RN 上同类 M 文件 4 个 | ⏸ 未改（无害且是回滚依据；建议后续加 prune，见"顺带发现"） |
| 5 | `vlessxhttpecn.sh` 的 nginx 档只**打印片段**让用户手粘，不自动插入（与 node 路径的 `nginx_apply.py` 自动插入不一致）；片段还会在换端口后过期 | `conf/vlessxhttpecn.sh:573-604,1252`；RN `out/vless-xhttp_nginx-01.conf` 写 25333 而节点在 45630 | ⏸ 未改（涉及交互流程，建议见 Q2） |
| 6 | 兼容性观察（不是缺陷）：X 的标记是 `xray-core`，与 SB (`SB-Panel CDN`)、M (`mihomo-core-cdn`) 互不干扰 —— RN 的 live 站点里 M 的段与 SB 的段共存即是证据 | `/tmp/rnev/confd/hxicc.catmicos.dpdns.org.conf:9,408` | — |

### RN 上跟三个内核相关的 nginx 站点配置现状（只读）

- 生效站点在 **nginx 容器**：`/home/web/conf.d/`
  - `hxicc.catmicos.dpdns.org.conf`（live）：活跃 location → SB `31007/31003/31006`、M `25677-25681`；`# === mihomo-core-cdn BEGIN … (server 指令) ===`（`:9-13`）与 `# >>> mihomo-core-cdn BEGIN … >>>`（`:408-496`）。**X 的标记 0 个**。
  - `moontv.6896698.xyz.conf`（与本话题无关）。
- **孤儿 / 陈旧配置**（nginx 不加载，因为不以 `.conf` 结尾，但一直堆着）：
  `a.example.com.conf.mihomo-core-cdn-bak`、`safety-test.conf.mihomo-core-cdn-bak`、`hxicc....conf.mihomo-core-cdn-bak`、`hxicc....conf.mihomo-cdntest-bak`、`hxicc....conf.sbpanel-bak`、`hxicc....conf.testbak`、`moontv....conf.sbpanel-bak`、`moontv....conf.sbpanel-prune.bak`、`moontv....conf.bak-vless`。其中 `safety-test.conf.mihomo-core-cdn-bak` **同时**留着 X 的 `>>> xray-core BEGIN safety-test.example.com >>>` 与 M 的标记 —— 是"多工具在同一站点上作业"的直接物证（也不会被改后的孤儿检查误报）。
- 宿主 `/etc/nginx/`：`sites-available/{default,torrent-tool.conf}`，启用仅 `torrent-tool.conf`（8787）；`conf.d` 空。**没有 X 的站点配置。**

---

## Q4 · X 支持端口跳跃（port hopping）与混淆（obfs / salamander）吗？

### 结论

1. X 的 `protocol:"hysteria"` 入站（`settings.version: 2`）**是 Hysteria2 线协议兼容的**——官方 hysteria2 客户端能完成 QUIC+TLS 握手、认证并成功代理 TCP。
2. **不支持 obfs**：配置里写 `obfs` 会被**静默忽略**（`-test` 通过、启动成功、日志无警告），效果是"开 salamander 的客户端连不上、不开的能连上"。
3. **端口跳跃不是内核能力**：X 的实现是 `iptables -t nat PREROUTING/OUTPUT -p udp --dport 起:止 -j REDIRECT --to-ports <节点端口>`（`conf/hysteria2.sh:551-629`），链接里带 `mport=起-止` 让客户端跳。内核本身**也支持**监听端口范围（`"port": "a-b"` 会被接受并真的逐个 listen），但 X 的生成器没用这条路径。
4. **后果（实测）**：X 之前硬编码在链接里的 `&obfs=none` 会让 **mihomo 整条订阅加载失败**（不是忽略这一条），SB 自己的导入解析器也拒收 `obfs=none`；`mport=` 形态 mihomo 接受、SB 的解析器拒收（SB 自己的 bug，见下）。

### 证据 A —— 真内核 `xray -test`（RN，`/usr/local/bin/xray` = Xray 26.3.27，/tmp 夹具已清理）

```
### 1) baseline hysteria v2 inbound                      -> Configuration OK.
### 2) settings.obfs = {type:salamander,password:pw}     -> Configuration OK.   (接受，未报错)
### 3) settings.obfs = "salamander" + obfsPassword       -> Configuration OK.   (同上)
### 4) "port": "30000-31000"                             -> Configuration OK.
### 5) "ports": ["30000-31000"]                          -> Failed to start: … Listen on specific ip without port in InboundDetour.
```
→ 结论 2、3 的"接受"只是一半：`-test` 不证明字段被实现，所以做了下面的运行时不变量实验。

### 证据 B —— 运行时矩阵（真内核 + 官方 `hysteria` 客户端，全部在 `/tmp`，跑完删除）

服务端：Xray 26.3.27，三个入站 A(24601 无 obfs)、B(24602 声明 `obfs: salamander/pw`)、C(`port:"24610-24612"`)，`ss -ulnp` 确认 C 真的在 24610/24611/24612 三个端口上 LISTEN。
客户端：`/usr/local/bin/hysteria client`（官方 v2），逐个走 SOCKS5 请求 `https://api.ipify.org`。

```
A-plain-to-noobfs    connected=1 egress=104.28.201.80     <- 官方 hy2 客户端连上 X 内核 (线协议兼容 ✅)
B-obfs-to-obfs       connected=0 FATAL failed to initialize client {"error":"connect error: timeout: no recent network activity"}
C-plain-to-obfs      connected=1 egress=104.28.201.80     <- 服务端声明 obfs 但不开混淆的客户端照样通 => obfs 被忽略
D-range-to-range     connected=1 egress=104.28.201.80     <- 客户端 server 写范围 + 内核监听范围 => 可用
E-single-to-range    connected=1 egress=104.28.201.80
服务端日志：proxy/hysteria: tunnelling request to tcp:api.ipify.org:443
```
（第一次跑时我漏了 `outbounds`，内核报 `app/dispatcher: default outbound handler not exist` —— 那是我的夹具问题，补上 freedom 出站后即上面结果。）

### 证据 C —— X 的链接生成（修复前）

`conf/hysteria2.sh:716-724`（修复前）
```bash
link="hysteria2://$uuid@$server_ip:$hysteria_port?${mport}sni=$domain&insecure=0&alpn=h3&obfs=none&upmbps=50&downmbps=200#hysteria-$index"
link="hysteria2://$uuid@$server_ip:$hysteria_port?${mport}sni=$domain&alpn=h3&obfs=none&pin=$cert_hex_pin&upmbps=50&downmbps=200#hysteria-$index"
```
→ **永远带 `obfs=none`**。RN 产物 `out/hy2_share-02.txt` 即为该形态（`…&alpn=h3&obfs=none&upmbps=50&downmbps=200#hysteria-02`）。

### 证据 D —— 别的内核怎么处理（真内核实测）

**mihomo v1.19.32**（RN 上真内核，用一个本地 HTTP 订阅喂 `hysteria2://` 链接，`proxy-providers` 解析）：

```
hysteria2://…&obfs=none&…               -> level=error msg="initial proxy provider xsub error: proxy 0 error: missing obfs password"   （整条订阅 0 个节点）
hysteria2://…&obfs=none&obfs-password=  -> 同样 missing obfs password（空密码也不行）
hysteria2://…&mport=30000-31000&…       -> 正常加载（无 error）
hysteria2://…&obfs=salamander&obfs-password=abc&… -> 正常加载
hysteria2://…（完全不带 obfs 参数）      -> 正常加载     <- 对照组
```
mihomo 源码同判据（`MetaCubeX/mihomo` `adapter/outbound/hysteria2.go`，`NewHysteria2`）：
```go
if len(option.Obfs) > 0 {
    if option.ObfsPassword == "" { return nil, errors.New("missing obfs password") }
    switch option.Obfs {
    case hysteria2.ObfsTypeSalamander: ...
    case hysteria2.ObfsTypeGecko: ...
    default: return nil, fmt.Errorf("unknown obfs type: %s", option.Obfs)
    }
}
```
→ `obfs=none` 是**硬失败**（先撞"缺密码"，有密码也会撞"未知混淆类型"）。

**sing-box 1.14.2**（RN 真内核，配置层）：
```
$ sing-box check -c obfs_none.json   # obfs: {type:"none"}
FATAL[0000] decode config at /tmp/sbchk/obfs_none.json: outbounds[0].obfs: unknown obfs type: none
$ sing-box check -c obfs_sal.json    # obfs: {type:"salamander",password:"abc"}  -> 通过
$ sing-box check -c ports.json       # server_ports: ["30000:31000"]            -> 通过
```
（这是 sing-box **配置层**的行为；其分享链接导入器我未能取到源码，见 UNKNOWN。）

**SB 自己的解析器**（`sing-box-core/src/conf/outbound_uri.py:474-478`，由 SB 侧子调查用真实运行复现）：
```
$ python3 -B src/conf/outbound_uri.py 'hysteria2://…&obfs=none&obfs-password=&alpn=h3'
{"ok": false, "error": "无法解析该分享链接\n原因: 不支持的 obfs: 'none' (仅 salamander)"}
$ … 'hysteria2://…&mport=30000-31000&…'
{"ok": false, … "server_ports: 端口不是数字: '30000-31000'"}
```
→ SB 生成的链接自己都导不回去（`obfs=none` 恒在、`mport` 用了短横线）；这是 SB 的缺陷，但对 X 的含义相同：**别输出 `obfs=none`**。

### 证据 E —— 端口跳跃这条链在 RN 生产上的现状

- X 的两个 hy2 节点 `hop_range` 都是空（`out/hy2_meta-02.json` / `-03.json`），即**没开跳跃**。
- 但 iptables 里有一条**指向空端口的陈旧跳跃规则**（见"顺带发现"）：`-A PREROUTING -p udp --dport 59390:59400 -j REDIRECT --to-ports 29035`，而 `ss -lunp | grep 29035` = 无人监听、配置里也搜不到 29035。
- X 的实现自己在 `conf/hysteria2.sh:624` 就提醒过：`规则重启后不保留, 如需持久化请安装 iptables-persistent`。

### 修复（已实现）

`conf/hysteria2.sh:715-737`：两份链接都**去掉** `&obfs=none`（没混淆就不写这个参数 —— Hysteria2 URI 的语义如此），并把上面 mihomo/sing-box/SB 的实测结论写进注释；`mport=` 保持"只有开了跳跃才写"。
**未改**（记录为设计取舍）：obfs 在 X 内核里没实现，所以生成器不提供 obfs 是正确的；若将来要 obfs，必须换内核（或换到 SB/M 的 hy2 实现）——只在链接里写 obfs 而内核忽略它，等于制造 B 组那种"客户端连不上、服务端毫无日志"的现场。

---

## 顺带发现

1. **陈旧 iptables 跳跃规则（孤儿防火墙规则）**：RN `iptables -t nat -S PREROUTING` → `-A PREROUTING -p udp --dport 59390:59400 -j REDIRECT --to-ports 29035`；`ss -lunp` 无 29035，`grep -r 29035 /root/catmi/*/conf/` 无命中 → 删节点时规则没清（X 的 `remove_port_hopping` 依赖 `hy2_meta` 里的 hop_range，而那条记录的节点已不在）。
2. **X 的 6 个回环入站全部无 Nginx 前端**（Q2），其中 `VLESS-WS_01`（9998）在分享元数据里标着 `tier: nginx`。
3. **陈旧 nginx 片段**：`out/vless-xhttp_nginx-01.conf` 指向 25333，节点实际 45630；02–06 同样只反映生成那一刻的端口。
4. **nginx 容器 conf.d 里 9 个 `*.bak`/非 `.conf` 残留**（M 的 4 个、SB 的 4 个、老手工 1 个）——都在 nginx 的加载范围之外，不会生效，但会让人误判"站点里有我的配置"。
5. **X 的 `install_info.env` 里就是 WARP 地址**（`link_ip`/`PUBLIC_IP` = 104.28.201.80）。修后的 Reality 会在生成时现场纠正并告警，但**env 本身仍是脏的**；彻底修正需重跑安装，或 `XRAY_PUBLIC_IP=107.173.154.178` 生成。命令已写进 Reality 的告警文案。
6. **X 的 hy2 客户端产物不含 obfs**（`out/hy2_client-02.yaml` 无 obfs 字段）→ 那一份本来是对的，错只错在分享链接。
7. 兄弟 agent 的未跟踪文件 `Client/tools/cc-verify-v2.sh`（19:15 新建）会让 `check_libs.sh` 的"管道早退"门禁失败（5 处 `| head`）。**不是本次改动**，未动它；见文末。

## UNKNOWN

1. **sing-box 分享链接解析器对 `obfs=none` 的行为**：只验证到**配置层**（`sing-box check` 报 `unknown obfs type: none`）。sing-box 的 URI 导入实现（GUI/`option` 包）未取到源码，未实测 → 不下"链接级"结论。已确证的是 mihomo 链接级**硬失败**与 SB 解析器**拒收**。
2. **X 的端口跳跃端到端（mport + iptables REDIRECT）未在隔离环境实测**：内核监听端口范围本身已实测可用（D/E 组），但"客户端在 30000-31000 跳、服务器 REDIRECT 回单端口"这条链需要在防火墙里加临时规则；RN 是生产机，我没有改它的 iptables，也没有起 netns 做这条链（`ip netns` 仍属改动宿主网络状态，超出"只用 /tmp"的授权范围）。
3. **X 的 `protocol:"hysteria"` 实现细节**（是否有 BBR/带宽协商差异、是否与官方 hysteria 2.x 全版本互通）：只验证了认证与 TCP 代理成功；UDP 转发、拥塞控制行为未测。
4. **`conf/nconf.sh` / `conf/cconf.sh` 这条路在 RN 上是否还可达**（它们会生成 `conf/nginx.json` 与 caddy.json，且用 env 里的 `link_ip`）：本次只做了源码层面的地址来源修复（env 源头），没有逐个走一遍这两条菜单路径。
5. **M 的 `nginx_apply.py` 是否也有"只认容器名"的同类问题**：M 侧子调查给的是"同名/同镜像匹配"（`src/conf/nginx_apply.py:85-99`），与 SB 同口径；我没有在 RN 上用非 `nginx` 命名的容器实测过。

---

## 门禁与验证

```
$ bash tools/check_libs.sh          # 修复后
═══ 结果: 575 通过, 1 失败 ═══
✗ pipefail 脚本里没有早退管道 Client/tools/cc-verify-v2.sh:37,61,68,119,121
```
- 唯一失败来自**兄弟 agent 新建的未跟踪文件**（`git status` 显示 `?? Client/tools/cc-verify-v2.sh`），不是本次改动，我没有动它。
- 用门禁自己的扫描逻辑、把该文件排除后重跑：**命中 0**（本次改动的 11 个文件全部干净）。
- 本次新增/改写的门禁 12 条：地址族统一判定（3）、对外地址取值（12 条断言：默认路由优先/隧道与私网过滤/两档自检分家/存量 WARP 不被沿用/`XRAY_PUBLIC_IP` 覆盖）、`install_info.env` 写入来源（2 + NAT 兜底告警 1）、孤儿检查（宿主夹具/备份不算/假 docker 容器）、`nginx_apply` 前置校验（rc=3/未改动/无产物/`--skip-preecheck` 回滚）、容器探测（镜像名匹配）。
- 其它相关自测：`bash -n` 全部通过；`python3 -c "import ast; ast.parse(...)"` 对 `conf/lib/nginx_apply.py` 通过；`conf/lib/addr.sh` 直跑自检（`show/v4/v6/v4addr/v6addr/route/ifaces/check/rcheck`）在真实 `ip` 与假 `ip` 下都验证过。

## 复现命令（只读；RN 上全部可重跑）

```bash
# Q1 取地址
ssh rn 'ip -o addr show scope global; ip route get 1.1.1.1'          # eth0 107.173.154.178 + warp/docker/awg
scp conf/lib/addr.sh rn:/tmp/addrtest/addr.sh && ssh rn 'cd /tmp/addrtest && bash addr.sh ifaces && bash addr.sh show'
# Q2 回环绑定与 nginx 现状
ssh rn 'ss -lntp | grep -E "xrayls|sing-box|mihomo"; iptables -t nat -S PREROUTING'
ssh rn 'docker inspect nginx --format "{{.HostConfig.NetworkMode}}"; ls /home/web/conf.d'
# Q4 内核能力（/tmp 夹具，跑完删）
ssh rn 'xray -test -config /tmp/hy2.json'                            # 见文中的 5 个变体
ssh rn 'hysteria client -c /tmp/cli.yaml'                            # 官方客户端 → X 内核 入站
ssh rn 'sing-box check -c /tmp/obfs_none.json'                       # unknown obfs type: none
```
