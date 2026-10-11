# 双端端到端验证：RN 交互式生成全协议 + CDN 节点 → CC 分享拉取实测 → ECH 抓包

**日期**：2026-10-10（PDT / UTC-7）
**执行方式**：面板菜单按键驱动（FIFO + pty），非直接调用 `conf/<proto>.sh add`
**同目录证据文件**：
- `evidence/panel-interactive-transcript.log`（789 行，面板完整回显 + 喂键实录）
- `evidence/share-payload-and-links.txt`（订阅原文 / base64 / 各节点分享链接）
- `evidence/ech-tshark-evidence.txt`（ECH 抓包关键字段原文）

---

## 1. 环境与版本

### 1.1 主机

| 角色 | 主机 | 地址 | 系统 |
|---|---|---|---|
| RN（服务端） | racknerd-75e0e8 | 107.173.154.178 | Linux 5.x，uptime 7d20h |
| CC（客户端） | armbian | 192.168.1.178 | Armbian |

### 1.2 内核与面板版本

| 组件 | 版本 / 证据 |
|---|---|
| X 内核 | `Xray 26.3.27 (Xray, Penetrates Everything.) d2758a0 (go1.26.1 linux/amd64)` |
| X 面板 | `/root/xray-panel.sh`（24871 B，2026-10-09 22:25）；**脚本不在本地**，每个菜单项用 `xray_run <repo相对路径>` 从 GitHub 现拉后执行 |
| X 服务 | `xrayls.service`，`/root/catmi/xray/xrayls -confdir /root/catmi/xray/conf` |
| M 内核 | `Mihomo Meta v1.19.32 linux amd64 with go1.26.8` / `Use tags: with_gvisor` |
| SB 内核 | `sing-box version 1.14.2`，`Revision: af6e64c3b69e6132ebaee0e1a3d24e93903f6709` |
| CC 客户端 | `Xray Client Web Manager v2.8.3`（`xbd`），内核 `26.3.27` |
| 抓包工具 | RN：`tcpdump`、`tshark 4.4.18`（分析在此机完成）；CC：`tcpdump`、`tshark 4.2.2`。**两端均已预装，未安装任何软件包** |

### 1.3 三个仓库 HEAD（便于复现）

| 仓库 | 位置 | HEAD / 版本标识 |
|---|---|---|
| **X** `mi1314cat/xray--core` | 面板运行期从 `raw.githubusercontent.com` 现拉（本地无 checkout） | `0e396dfb6a197db543fd191eea8fdb1dadc36cc4`（`git ls-remote … refs/heads/main`） |
| **M** `mihomo--core` | `/root/catmi/mihomo/src` | `src/VERSION` = `2d4a088c71b2` |
| **SB** `mi1314cat/sing-box-core` | `/root/catmi/sing-box/src-upstream`（git） | `629a957871c9b6ae68a5aeb693b615e2943836dc`（2026-10-05 12:30:12 +0800） |
| 参考：SB 部署 checkout | `/opt/sing-box-core`（git） | `439c97ee7d57b8aaaa37d127ac3875677a2d64eb` |

### 1.4 生成前基线（记录于操作之前）

- `conf/*.json` 片段：**22** 个（`00-base / hysteria-01..03 / nginx / out-01..03 / out-direct / out-routing / reality-01,03 / socks-01 / ss2022-01 / trojan-01,02 / vless-xhttp-01..06`）
- `ss -tuln` 行数：**85**
- 已占端口（抽样）：xrayls 19212/19595/22726/27474/28936/37944/38066/39839/50330 + 本地 31722/33934/41721/45630/9997/9998/9999；mihomo 22812/25669-25681/25684/28725；sing-box 31000/31002/31004/31008/31009/31011-31013；nginx 80/443；share 服务 9443；9393；59001；8074；8787；6541；53
- 全量快照：`/tmp/e2e/baseline-conf-out.tar.gz`（`conf/ out/ config.json`，已随 /tmp 清理）

### 1.5 关键既有设施（决定 CDN 方案）

- CDN 域名：**`moontv.6896698.xyz`**，解析到 Cloudflare 边缘（`104.21.88.196 / 172.67.152.157`）
- 证书：`/home/web/certs/moontv.6896698.xyz_cert.pem` / `_key.pem`（公网 CA 真证书；nginx 容器内路径为 `/etc/nginx/certs/`）
- nginx（docker `nginx:alpine`，宿主 pid 1833）站点 `/home/web/conf.d/moontv.6896698.xyz.conf` 用 **路径前缀 location → `proxy_pass https://127.0.0.1:<xray端口>`** 回源
- 分享服务：`proxy-share-service 1.1.0`，`:9443`，`providers` 里 `xray` 原有 0 条

---

## 2. A. RN 侧：交互式生成实录

### 2.0 驱动方法与一次失败（如实记录）

面板用 `read` 逐行取键，故用 **FIFO + pty** 驱动：`mkfifo /tmp/e2e/in`，一个持有写端的后台进程防止 EOF，`script -qefc "bash /root/xray-panel.sh" panel.log < /tmp/e2e/in`（`-f` 必须加，否则 typescript 全缓冲，看不到实时回显），然后**一次只发一个按键**、读回显再决定下一个键。

**首次尝试的两次失败（保留原文）**：

1. 直接把 18 行按键一次性 `script -qec … < keys.txt` →
   ```
   Script started on 2026-10-10 05:15:27-07:00
   …（菜单打印后立即）
   Script done on 2026-10-10 05:15:29-07:00 [COMMAND_EXIT_CODE="0"]
   ```
   原因：`script` 一次写完后立刻 EOF，`show_menu` 的 `read … || exit 0` 读到 EOF 直接退出。

2. 修正为慢速喂键后仍失败：主菜单 `read` 收到空行 → `case "" in 0|"") exit 0`。
   原因：**我误以为 `_srv_ask_name` 会先问"服务器标识"**，把空行放在了第一位。实际该函数因取不到 `naming.sh` 而提前 `return 0`（`_srv_ask_name` 里 `[[ -f "$lib" ]] || return 0`），**这个提示并不会出现**。清空按键序列后正常。

一次按键错位还导致误入 Hysteria2 菜单（面板回显 `无效选项:` 后 `按选择: 2` 落到了 Hysteria2）。已确认**未产生任何片段**（`conf/` 与基线 diff 一致）后重新开始。

### 2.1 生成的 5 个节点（全部为新编号、新端口）

| # | 片段 | tag | 协议 | 传输 | 安全 | 监听 |
|---|---|---|---|---|---|---|
| 1 | `conf/vless-xhttp-07.json` | `vless-xhttp07` | vless | xhttp | tls | **0.0.0.0:8443** （接入=CDN 直连, ECH=CDN-ECH） |
| 2 | `conf/vless-xhttp-08.json` | `vless-xhttp08` | vless | ws | tls | **0.0.0.0:29601** （接入=CDN 直连, ECH=**直连原生**） |
| 3 | `conf/trojan-03.json` | `TROJAN-03` | trojan | tcp | reality | **0.0.0.0:29602** |
| 4 | `conf/ss2022-02.json` | `SS2022-02` | shadowsocks | — | — | **0.0.0.0:29603**（2022-blake3-aes-256-gcm） |
| 5 | `conf/hysteria-04.json` | `hysteria-04` | hysteria | hysteria | tls | **0.0.0.0:29604/UDP** |

### 2.2 逐节点按键序列与回显

#### N1 — VLESS-xHTTP + CDN + CDN-ECH（端口 8443）

按键（`/` 分隔，`⏎`=回车）：
```
1 / 6 / 2 / 2 / 1 / n / 1 / 8443 / ⏎ / ⏎ / 2 / <crt> / <key> / ⏎ / n / ⏎ / 0 / ⏎ / 0
```
即：主菜单`1 添加节点` → `6 VLESS-xHTTP` → 脚本子菜单`2 新增配置` → `2 XHTTP` → `1 CDN 直连` → `n` 关 ML-KEM → `1` CDN-ECH → 端口 `8443`。

回显（原文节选）：
```
  传输方式 (二选一):
  1) WS (WebSocket, CDN 最兼容, 推荐)
  2) XHTTP (XHTTP+CDN, 抗识别更强)
  选择 (默认1): 2
  接入方式:
  1) CDN 直连 (监听 0.0.0.0, Cloudflare 回源到端口, 最直接)
  2) Nginx 转发 (监听 127.0.0.1, 走 nginx 路径匹配统一入口)
  选择 (默认1): 1
启用 ML-KEM-768 后量子加密 (vlessenc)? (Y/n): n
  ECH 形态:
  1) CDN-ECH (Cloudflare 边缘处理 ECH, 无需服务器密钥, 推荐)
  2) 直连 ECH (Xray 原生 echServerKeys, 需 TLS1.3)
  选择 (默认1): 1
请输入监听端口 (默认: 42194): 8443
[Info] 检测到 IP: 107.173.154.178
使用此IP？(回车默认): 
请输入 XHTTP 路径 (带尾斜杠) (默认: /aVCR3P0A): 
[Info] XHTTP 路径: /aVCR3P0A/ (mode: auto)
  选择 (默认1): 2                      ← 手动输入证书路径
  证书 crt 路径: /home/web/certs/moontv.6896698.xyz_cert.pem
  证书 key 路径: /home/web/certs/moontv.6896698.xyz_key.pem
[OK]  使用证书: moontv.6896698.xyz
请输入访问域名 (客户端 server/sni 使用, 默认: moontv.6896698.xyz): 
[Info] CDN-ECH 模式: 请确认 Cloudflare zone 已为 moontv.6896698.xyz 开启 ECH
是否将域名 moontv.6896698.xyz 的 DNS 绑定到本机 IP (107.173.154.178)？（y/N）
n
[OK] include 已确保: /root/catmi/xray/conf/vless-xhttp-*.json
[Info] CDN-ECH: 自动获取 Cloudflare ECHConfigList (96 字符)
[Info] 客户端 pin 自签证书 SHA256: 48165d74269bc097...
[OK]  客户端 JSON (xray): /root/catmi/xray/out/vless-xhttp_client-07.json
[OK]  分享链接: /root/catmi/xray/out/vless-xhttp_share-07.txt
[OK]  VLESS 配置生成成功
编号: 07
监听: 0.0.0.0:8443
UUID: 1fa7c981-16b4-4963-9ef6-9bb13ad25053
XHTTP 路径: /aVCR3P0A/ (mode: auto)
```

> **注意两处**：① 证书是公网 CA 真证书，脚本却仍打印并写入 `pin 自签证书 SHA256`（见问题 P2-7）；② 面板随后 `systemctl restart xrayls.service`（这是面板"新增节点"的标准流程，非我手工重启）。

#### N2 — VLESS-WS + **直连 ECH**（端口 29601）

按键：`⏎`(返回) `/ 6 / 2 / 1 / 1 / n / 2 / 29601 / ⏎ / ⏎ / 2 / <crt> / <key> / ⏎ / n / ⏎ / 0`

回显关键段：
```
  选择 (默认1): 2                      ← 直连 ECH (Xray 原生 echServerKeys)
请输入监听端口 (默认: 19617): 29601
请输入 WS 路径 (默认: /8KLD3cNj): 
[Info] WS 路径: /8KLD3cNj
[OK]  使用证书: moontv.6896698.xyz
[Info] 正在生成 ECH (Encrypted Client Hello) 密钥对...
[OK]  ECH 密钥生成成功 (serverName: moontv.6896698.xyz)
[OK]  客户端 JSON (xray): /root/catmi/xray/out/vless-xhttp_client-08.json
[OK]  分享链接: /root/catmi/xray/out/vless-xhttp_share-08.txt
编号: 08
传输: ws
接入: cdn
ECH: direct
监听: 0.0.0.0:29601
UUID: 278502fc-8e95-4558-a6ae-bd8a39c500f9
```
服务端片段含 `echServerKeys`（184 字符）与 `minVersion: 1.3` —— 这是后面 ECH 抓包用的节点。

#### N3 — Trojan + REALITY（端口 29602）

按键：`⏎ / 9 / 2 / 29602 / ⏎ / ⏎ / ⏎ / ⏎ / ⏎`（`1→9 Trojan` → `2 新增配置` → 端口 → 回车=自动密码 → 回车=REALITY → 回车=伪装网址空 → 回车=IPv4 → 回车=伪装域名）

回显关键段：
```
║ Trojan 配置管理                        ║
2) 新增配置（默认最高配置：Trojan + REALITY）
请输入监听端口 (默认: 25716): 29602
是否自定义 Trojan 密码？回车=自动生成(推荐): 
选择 (默认回车=REALITY): 
[Info] 正在检测/更新 Reality 伪装域名（domains.sh）...
请输入Reality伪装网址: 
random_website: 完成, 健康候选 4 个, 选定 audio-ssl.itunes.apple.com
[Info] 正在生成 ML-KEM（后量子加密 PQ）参数...
伪装域名 (回车使用 domains.sh 优选的 audio-ssl.itunes.apple.com): 
[OK]  新增 Trojan 配置成功（默认最高配置）
编号: 03
监听: 0.0.0.0:29602
安全层: REALITY（target=audio-ssl.itunes.apple.com:443 pbk=GiR4k0uVRh... sid=b860a9f0）
密码: LV7CpzX9Jc8vWuhP0YV0
```
（该流程会 `source` 并更新 `/root/catmi/xray/install_info.env` 与 `/root/catmi/catmi.env` 中的 UUID/Reality 参数——属面板既有行为。）

#### N4 — Shadowsocks-2022（端口 29603）—— **首次失败，原文保留**

按键：`⏎ / 8 / 2 / 29603 / ⏎ / ⏎`
```
║ Shadowsocks-2022 配置管理              ║
2) 新增配置（默认最高配置：aes-256-gcm + UDP 开启）
请输入监听端口 (默认: 18718): 29603
回车 = 使用最高配置 (aes-256-gcm)
选择: 
/tmp/.xray-panel.40fRso/conf_Shadowsocks.sh: line 232: gen_psk: command not found
是否自定义 PSK？回车=自动生成(推荐): 
[Error] PSK 长度错误：2022-blake3-aes-256-gcm 需要 32 字节 (获得 0 字节)
按回车继续...
```
**节点未创建**。改用自定义 PSK 重试成功：`⏎ / 2 / 29603 / ⏎ / <44 字符 base64 PSK> / ⏎ / ⏎`
```
是否自定义 PSK？回车=自动生成(推荐): smzMYvuGFIM3YHksV1eAJNFzeWuR+Gg9qT3JwluUWTU=
UDP 中继默认开启（SS2022 UDP 为 session 化中继）。不启用 UDP 请输入 1 (默认启用): 
选择 (默认回车=裸 SS2022): 
[OK]  新增 Shadowsocks-2022 配置成功（最高配置）
编号: 02    监听: 0.0.0.0:29603    方法: 2022-blake3-aes-256-gcm
```

#### N5 — Hysteria2（UDP 29604）

按键：`⏎ / 2 / 2 / ⏎ / 1 / 29604 / n / 2 / <crt> / <key>`
```
║ 新增 Hysteria2 配置                    ║
服务器 IP (默认: 107.173.154.178): 
请选择监听地址：1) IPv4 (0.0.0.0) … 选择 (默认 1): 1
请输入本地监听端口 (默认: 35585): 29604
是否开启 UDP 端口跳跃? (默认: 否, y/N): n
  证书方案： … 选择 (默认1): 2
  证书 crt 路径: /home/web/certs/moontv.6896698.xyz_cert.pem
  证书 key 路径: /home/web/certs/moontv.6896698.xyz_key.pem
编号: 04    端口: 29604
UUID: 05615ce2-4bf4-4f4e-908e-c99a16a803e8
域名: moontv.6896698.xyz   证书: /home/web/certs/moontv.6896698.xyz_cert.pem CA可信真证书
```

### 2.3 生成后核对（RN）

**配置校验**（等价 `xray -test`）：
```
# /root/catmi/xray/xrayls run -confdir /root/catmi/xray/conf -test
… (Warning: Trojan deprecated / WebSocket deprecated / REALITY 提示)
Configuration OK.
```

**监听**（`ss`）：
```
LISTEN  *:8443   users:(("xrayls",pid=…))          # vless-xhttp07
LISTEN  *:29601  users:(("xrayls",pid=…))          # vless-xhttp08
LISTEN  *:29602  users:(("xrayls",pid=…))          # TROJAN-03
LISTEN  *:29603  users:(("xrayls",pid=…))          # SS2022-02
UNCONN  *:29604  users:(("xrayls",pid=…))          # hysteria-04 (UDP)
```

**回归**：`conf/*.json` 22 → 27；`ss -tuln` 85 → 91 行；基线 43 个端口**全部仍在**（`missing count = 0`）；**mihomo(119320)/sing-box(60510)/nginx(1833) 进程 PID 未变**，仅 `xrayls` 按面板流程重启（PID 29307→…→165517）。`xrayls / mihomo / sing-box / nginx` 均 `active`。

---

## 3. B. CC 侧：分享拉取实录

### 3.1 分享服务的实际可用地址（先探明）

```
# SHARE_PROVIDER=xray python3 share_client.py health
{"status": "ok", "service": "proxy-share-service", "version": "1.1.0",
 "api_version": 1, "port": 9443, "types": ["node","config","file"],
 "providers": {"mihomo": {"total": 2, …}, "sing-box": {"total": 0, …}}}
```
→ X 侧订阅地址形态为 `http://<host>:9443/share/<token>`（服务端本地 `127.0.0.1:9443`，`X` 的 `SHARE_ADDR` 默认 localhost）。

### 3.2 第一次生成分享：**失败（原文保留）**

面板路径 `4 分享管理 → 1 生成分享链接`，选 `4 13 16 23 24`（即 5 个新节点），名称 `e2e-allproto`，次数 0，有效期 0：
```
  选择要分享的节点 (编号, 空格分隔; 留空=全部): 4 13 16 23 24
  分享名称 [分享-]: e2e-allproto
  最多可拉取次数 [0=不限]: 0
  有效期天数 [0=永久]: 0
    无可分发内容 (片段没了? 缺对外地址?)
  [X] 生成订阅内容内容失败 (看上面对应原因)
```
根因定位（`conf/lib/share_payload.py: build_links → build_share_link`）：每个节点需要 `out/share/<tag>.json` 分享元数据提供 `host/port`，而 **仓库里没有任何生成器写这份元数据**（只有 3 个 10-09 的历史残留文件：`TROJAN-01.json / VLESS-WS_01.json / vless-xhttp01.json`）。

**为不阻断验证**，用项目自带的 `conf/lib/share_meta.py`（同一 schema、官方库）补写了 5 个新节点的元数据：
```python
share_meta.save("/root/catmi/xray/out/share", tag,
                {"host":"107.173.154.178", "port":<真实监听端口>, "name":tag,
                 "schema":1, "tag":tag})   # TROJAN-03 additionally: public_key/short_id/fingerprint/spx
```

### 3.3 第二次生成分享：**成功**

```
    http://107.173.154.178:9443/share/f64f61ce35e42b39a5f928d1c6d15ae5
    节点: hysteria-04 SS2022-02 TROJAN-03 vless-xhttp07 vless-xhttp08
    次数: 不限   有效期: 永久 天
```

### 3.4 CC 用 `curl` 拉一遍（HTTP 拉取，看格式）

```
$ curl -sS -w "[http_code=%{http_code} time=%{time_total}s size=%{size_download}]" \
    http://107.173.154.178:9443/share/f64f61ce35e42b39a5f928d1c6d15ae5
[http_code=200 time=1.516938s size=944]
```
返回内容是 **base64 的一整行**（标准订阅载荷）。解码后 5 条：
```
hysteria2://05615ce2-4bf4-4f4e-908e-c99a16a803e8@107.173.154.178:29604?sni=107.173.154.178&insecure=0#hysteria-04
ss://MjAyMi1ibGFrZTMtYWVzLTI1Ni1nY206c216TVl2dUdGSU0zWUhrc1YxZUFKTkZ6ZVd1UitHZzlxVDNKd2x1VVdUVT0@107.173.154.178:29603#SS2022-02
trojan://LV7CpzX9Jc8vWuhP0YV0@107.173.154.178:29602?security=reality&type=tcp&sni=audio-ssl.itunes.apple.com&fp=chrome&sid=b860a9f0&pbk=GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU#TROJAN-03
vless://1fa7c981-16b4-4963-9ef6-9bb13ad25053@107.173.154.178:8443?encryption=none&security=tls&type=xhttp&path=%2FaVCR3P0A%2F#vless-xhttp07
vless://278502fc-8e95-4558-a6ae-bd8a39c500f9@107.173.154.178:29601?encryption=none&security=tls&type=ws&path=%2F8KLD3cNj#vless-xhttp08
```

### 3.5 CC 用 `xbd` 导入（我们自己的客户端机制）

```
$ xbd node sub "http://107.173.154.178:9443/share/f64f61ce35e42b39a5f928d1c6d15ae5"
==> 下载订阅
✓ 解析出 5 个节点
✓ 已导入 4 个节点          ← 少 1 个！
```
`/tmp/.xbd_skipped.json`：
```
[["TROJAN-03", "Xray 内核不支持该协议（trojan）"]]
```
→ 见问题 **P1-5**（客户端 `parse_trojan` 丢 `pbk/sid` 导致误判"不支持"）。

导入后 `xbd node list` 新增 `hysteria-04 / SS2022-02 / vless-xhttp07 / vless-xhttp08`（原 7 个 → 11 个）。

### 3.6 实测方法说明

- **经 `xbd` 实测**：`xbd node use <编号>` → `curl -x socks5h://127.0.0.1:10808`
  （注：`127.0.0.1:1080` 不是 xbd 的本机入口，本机 SOCKS 是 `127.0.0.1:10808`，HTTP 是 `127.0.0.1:10809`（仅绑 192.168.1.178））
- **经临时内核客户端实测**（任务允许的第二种方式）：在 CC `/tmp/e2e/` 用 `xray run -c <cfg>` 起独立实例（各自独立 SOCKS 端口），配置取自 RN 面板/PROTO 脚本生成的 `out/*client*` 文件；**不动 xbd 的正式实例**，测完全部 kill
- 出网判据：`https://www.gstatic.com/generate_204` 的 HTTP 码 + 耗时；出口 IP 用 `https://api.ipify.org`

---

## 4. 逐协议结论表

| 节点（协议/传输/安全） | RN 真实监听 | 链接端口 vs 监听 | CC 实测（路径） | 码/耗时 | 出口 IP | 判定 | 证据 |
|---|---|---|---|---|---|---|---|
| **VLESS-xHTTP + TLS + CDN-ECH**（07，CDN 节点） | `0.0.0.0:8443` | **不一致**：PROTO 生成链接 `moontv.6896698.xyz:443`；分享层链接 `107.173.154.178:8443`（但丢 sni） | ① 生成客户端按原样（域:443） ② 域:8443 去掉证书 pin | ① `000`（`bad status code:307 Temporary Redirect` → `unexpected response version`）② **`204` / 1.73s** | ① — ② `104.28.195.192` | **节点本身可用；按生成结果/分享链接不可用（死链）** | 见下 §4.1 |
| **VLESS-WS + TLS + 直连 ECH**（08） | `0.0.0.0:29601` | **一致**（29601 = 29601） | ① 生成客户端（含 sni+ECH+pin） ② 分享链接参数原样（无 sni） | ① **`204` / 1.27s** ② `000` | ① `104.28.195.192` | **节点可用；经分享链接不可用**（分享层丢 sni） | ① `transport/internet/websocket: creating connection to tcp:107.173.154.178:29601` → `tunneling request …`；② `tls: failed to verify certificate: x509: cannot validate certificate for 107.173.154.178 because it doesn't contain any IP SANs` |
| **Trojan + REALITY**（03） | `0.0.0.0:29602` | **一致**（29602 = 29602） | ① 临时 Xray 客户端（用 `out/trojan-03.json`） ② 经 `xbd` 分享订阅 | ① **`204` / 0.82s** ② 未能导入 | ① `104.28.195.192` | **节点可用；经 `xbd` 订阅被误丢弃** | ① 见 §4.1；② `/tmp/.xbd_skipped.json` = `[["TROJAN-03","Xray 内核不支持该协议（trojan）"]]` |
| **Shadowsocks-2022**（02，aes-256-gcm，UDP 开） | `0.0.0.0:29603` | **一致**（29603 = 29603） | ① 临时 Xray 客户端（用分享链接同款 `ss://`） ② `xbd` 订阅 | ① **`204` / 0.67s** ② 导入成功 | ① `104.28.195.192` | **可用**（但节点生成需人工喂 PSK，见 P0-1） | ① 见 §4.1 |
| **Hysteria2**（04，UDP） | `0.0.0.0:29604/UDP` | **一致**（29604 = 29604） | ① 临时 Xray 客户端（用 `out/hy2_client-04.xray.json`，`sni=moontv.6896698.xyz`） ② 分享链接参数原样（`sni=<IP>&insecure=0`） | ① **`204` / 1.46s** ② `000` | ① `104.28.195.192` | **节点可用；经分享链接不可用**（分享层把 SNI 写成 IP） | ② `tls: failed to verify certificate: x509: cannot validate certificate for 107.173.154.178 because it doesn't contain any IP SANs` |

### 4.1 原始输出片段

**4 个可用节点（临时内核客户端，一次跑完）**
```
[trojan] http=204|0.823961 exit_ip=104.28.195.192
[ss]     http=204|0.673579 exit_ip=104.28.195.192
[hy2]    http=204|1.461141 exit_ip=104.28.195.192
```
```
[cdn-8443-nopin] http=204|1.729033 exit_ip=104.28.195.192
2026/10/10 20:59:26 [Info] transport/internet/splithttp: XHTTP is dialing to tcp:moontv.6896698.xyz:8443,
                            mode packet-up, HTTP version 2, host moontv.6896698.xyz
2026/10/10 20:59:26 [Info] proxy/vless/outbound: tunneling request to tcp:api.ipify.org:443
                            via moontv.6896698.xyz:8443
```

**CDN 节点按生成结果（域:443）失败**
```
[cdn-443] http=000
2026/10/10 20:59:20 [Info] transport/internet/splithttp: failed to send upload
        > transport/internet/splithttp: bad status code:307 Temporary Redirect
2026/10/10 20:59:20 [Info] app/proxyman/outbound: failed to process outbound traffic
        > proxy/vless/outbound: failed to decode response header
        > proxy/vless/encoding: unexpected response version. Expecting 0 but actually 60
```
（307 → 说明 443 上应答的是 nginx 后面的 moontv 网页应用，不是 xray 的 xhttp 入站。）

**CDN 节点带 pin 时失败（生成器默认行为）**
```
transport/internet/tls: peer cert is unrecognized (against pinnedPeerCertSha256)
```

**CDN 回源可达性（CC → Cloudflare → 源站）**
```
=== CF edge port 8443 (origin pull via CF)
code=400 time=2.235991s ip=2606:4700:3032::ac43:989d      ← CF 边缘，且确实回源到了 xray(8443)
=== CF 443 same path
code=308 time=3.101802s ip=2606:4700:3032::ac43:989d      ← 443 落到 moontv 网页应用
=== direct origin 8443
code=400 time=0.628799s ip=107.173.154.178                ← 源站 xray 直接应答，TLS 正常
```

### 4.2 分享链接 vs 真实监听（任务点名的"死链"核对）

| 节点 | 片段真实监听 | 生成器 `out/*share*.txt` | 分享订阅（share 层） | 一致? |
|---|---|---|---|---|
| vless-xhttp07 | 8443 | `@moontv.6896698.xyz:443` | `@107.173.154.178:8443`（无 sni） | ❌ **生成器链接端口 443 ≠ 监听 8443** |
| vless-xhttp08 | 29601 | `@107.173.154.178:29601` ✅ | `@107.173.154.178:29601`（无 sni） | ✅ 端口一致 |
| TROJAN-03 | 29602 | `@107.173.154.178:29602` ✅ | `@107.173.154.178:29602` | ✅ |
| SS2022-02 | 29603 | `@107.173.154.178:29603` ✅ | `@107.173.154.178:29603` | ✅ |
| hysteria-04 | 29604/UDP | `sni=moontv.6896698.xyz&alpn=h3&upmbps=50&downmbps=200` | `sni=107.173.154.178&insecure=0`（无 alpn/up/down） | 端口 ✅ / **SNI ❌** |

**结论：上一轮的"链接端口与片段端口不符"问题在本轮 CDN 路径上复现（8443 vs 443），且伴随第二个独立缺陷（证书 pin）。非 CDN 的 4 个节点端口全部一致。**

---

## 5. C. ECH 抓包验证（重点）

### 5.1 方法与判据

- **被测链路**：CC（临时 Xray 客户端，配置 `out/vless-xhttp_client-08.json`）→ RN `107.173.154.178:29601`（VLESS-WS + TLS，`tlsSettings.echServerKeys` 已生效，`-test` = Configuration OK）
- **抓包点**：RN `tcpdump -i any -s 0 -w /tmp/e2e/ech-clean.pcap 'tcp port 29601'`
- **解析**：RN `tshark 4.4.18`
- **隔离**：抓包前先把 `xbd` 恢复回原节点（Chromium dialer 关闭），保证 pcap 里只有被测客户端的流量；然后只发 2 个请求（`generate_204` + `api.ipify.org`）

**判据（RFC 9849 / draft-ietf-tls-esni）**
1. **客户端有没有发 ECH** = ClientHello 里存在扩展类型 `0xfe0d (65037)`，且其内部 `Client Hello type = Outer Client Hello (0)`；
2. **服务端有没有接受 ECH** = ServerHello 里存在 `0xfe0d` 扩展，且其 8 字节内容 = `ServerHello.random` 的最后 8 字节；**ServerHello 没有该扩展 = ECH 未被接受（rejected）**；
3. **真实 SNI 是否可见** = 明文 `server_name(0)` 扩展的内容应是 ECHConfig 里的 `public_name`（诱饵名）；真实名应在加密的 ClientHelloInner 里。

### 5.2 抓包规模
```
=== packets: 93
=== ClientHellos
frame 52  stream 1  SNI=moontv.6896698.xyz   ext_types=6682,35,10,11,65037,27,17613,43,65281,23,16,13,18,45,0,5,51,39578
```
（另有 1 个抓包前遗留连接的 ServerHello，其 ClientHello 不在本 pcap 内，不影响结论。两次请求复用同一条 WS 连接，故只有 1 个 ClientHello。）

### 5.3 关键字段原文

**① ClientHello 里的 ECH 扩展（帧 52）**
```
            Extension: encrypted_client_hello (len=186)
                Type: encrypted_client_hello (65037)
                Length: 186
                Client Hello type: Outer Client Hello (0)
                Cipher Suite: HKDF-SHA256/AES-128-GCM
                    KDF Id: HKDF-SHA256 (1)
                    AEAD Id: AES-128-GCM (1)
                Config Id: 0
                Enc length: 32
                Enc: 4e27ad5d603302a6acccd04c74498bce1d7863587edbd9898abe50f0d60a5d04
                Payload length: 144
                Payload […]: 5338bd7b3454b43ebdbc7b7ac6fcfd33…
```

**② 明文的 SNI（同一个 ClientHello）**
```
            Extension: server_name (len=23) name=moontv.6896698.xyz
                Type: server_name (0)
                Length: 23
                Server Name list length: 21
                Server Name Type: host_name (0)
                Server Name length: 18
                Server Name: moontv.6896698.xyz
```

**③ 字节级核对（不信赖 dissector 的二次确认）**
```
$ tshark -r ech-clean.pcap -q -z follow,tcp,raw,1 | grep -c fe0d
1                                  ← 客户端→服务端重组流里 0xfe0d 出现 1 次
$ tshark -r ech-clean.pcap -Y "tls.handshake.type==2" -T fields -e tcp.payload | tr -d ':' | grep -c fe0d
0                                  ← ServerHello 里 0 次
```

**④ ServerHello 扩展列表（帧 54，原文 hex）**
```
16030304ba020004b6030349d40a6684d1…130100046e002b000203040033046411ec04600579879…
                                   ↑ ext 0x002b(supported_versions)  ↑ ext 0x0033(key_share)
$ tshark -r ech-clean.pcap -Y "tls.handshake.type==2" -T fields -e frame.number -e tcp.stream -e tls.handshake.extension.type
54	1	43,51
```
→ ServerHello 只有 `supported_versions(43)` + `key_share(51)`，**没有 65037**。

**⑤ 服务端 ECHConfig 解出来的 `public_name`（客户端配置 `echConfigList`，140 字符 base64）**
```
version      : 0xfe0d
config_id    : 0
kem_id       : 0x0020  (ML-KEM-768)
max_name_len : 0
PUBLIC_NAME  : moontv.6896698.xyz
```

**⑥ 握手成功（功能性事实）**
```
--- req1  code=204 time=1.475070s
--- req2  104.28.195.192
```

### 5.4 结论（明确）

**ECH 在这条链路上未生效（判定：NOT IN EFFECT / rejected）。**

- **客户端侧：ECH 确实发出去了**。ClientHello 带 `0xfe0d`，`Outer Client Hello (0)`，HPKE 密文 144 字节，`Enc`（32B 封装密钥）都在；字节级也能在重组流里搜到 `fe0d`。
- **服务端侧：没有任何 ECH 接受信号**。ServerHello 扩展只有 `43,51`，`0xfe0d` 在 ServerHello 原始 hex 里 0 次命中 → 按 RFC 9849 的判据就是 **ECH 被拒**，服务端按 `ClientHelloOuter` 完成了握手（因此握手仍成功、业务可用）。
- **SNI 可见性：在"最理想情况"下也藏不住**。`public_name` 被生成成 `moontv.6896698.xyz`，与真实站点名**完全相同**，所以明文 `server_name` 里直接就是真实域名。也就是说：即便服务端接受了 ECH，这条链路的域名对旁路观察者依然完全可见。
- 服务端为什么没回确认 → **UNKNOWN**（未深入 Xray-core 内部实现；`echServerKeys` 已在片段中、合并配置 `-test` = Configuration OK，仅能证明"配置合法"，不能证明"服务端会确认 ECH"）。

> 备注（未归属观察，不计入结论）：第一次未隔离的抓包里出现过 8 个 ClientHello，其中 7 个带 `0xfe0d` 但**完全没有 SNI 扩展**、`Config Id: 167`，另 1 个 `Config Id: 0` + SNI=`moontv.6896698.xyz`。后者可确认为本次临时客户端；前者无法归属到具体进程（当时 xbd/Chromium 在运行），故不纳入判定。

---

## 6. 发现的问题清单（按严重度，含复现）

### P0-1　Shadowsocks-2022 菜单项完全不可用：`gen_psk` 未定义
- **现象**：面板 `1 添加节点 → 8 Shadowsocks-2022 → 2 新增配置 → 端口 → 回车(最高配置)` 必然失败，节点创建不出来。
- **复现**：
  ```
  /tmp/.xray-panel.40fRso/conf_Shadowsocks.sh: line 232: gen_psk: command not found
  [Error] PSK 长度错误：2022-blake3-aes-256-gcm 需要 32 字节 (获得 0 字节)
  ```
- **根因**：`conf/Shadowsocks.sh:232` `PSK=$(gen_psk "$method")`，但 `gen_psk` 在脚本与它 source 的 `conf/lib/{print,naming,ports,addr}.sh` 里**都没有定义**（逐个 grep 计数均为 0）。REPL 手动 `openssl rand -base64 32` 喂进去即可成功 → 证明只差这个函数。
- **影响**：唯一一个"最高配置 SS2022"入口失效；用户只能自己造 PSK。

### P0-2　"生成分享链接"对任何新建节点都失败：分享元数据没有写入方
- **现象**：选任意新节点生成分享 → `无可分发内容 (片段没了? 缺对外地址?)`。
- **根因**：`share_payload.build_links()` → `nodes.build_share_link()` 需要 `out/share/<tag>.json` 的 `host/port`；`share_meta.save()` 在整个仓库里**只有 `conf/node.sh` 的改名分支**在调用（从旧 tag 复制），没有任何节点生成路径写它。基线仅 3 个 10-09 的历史残留元数据。
- **复现**：面板 `4 → 1`，选新节点 → 上述报错；`ls out/share/` 只有 `TROJAN-01.json / VLESS-WS_01.json / vless-xhttp01.json`。
- **附带**：`share_payload.build_payload()` 在 `payload is None` 时**先 `raise SystemExit(1)`**，把 `missing/nometa/bad` 三类诊断吞掉了（`share.sh` 里那段 `sed 's/^/    /' /tmp/.xshare.err` 因此什么都打不出来）→ 用户只看到一句无因可查的错误。

### P0-3　CDN 节点（接入=CDN 直连）生成即死链，且被证书 pin 二次杀死
- **现象 A（端口不符）**：服务端片段监听 `0.0.0.0:8443`，但 `out/vless-xhttp_share-07.txt` 与 `out/vless-xhttp_client-07.json` 都写 `moontv.6896698.xyz:443`。443 上是 nginx→moontv 网页应用：
  ```
  bad status code:307 Temporary Redirect
  failed to decode response header … unexpected response version. Expecting 0 but actually 60
  ```
  脚本把 nginx location 片段写到 `out/vless-xhttp_nginx-07.conf` 就结束，**从不应用**到 `/home/web/conf.d/moontv.6896698.xyz.conf`；`ACCESS_MODE=cdn` 期待"CF 直接回源到该端口"，但 CF 默认只回源 443（要改端口得配 Origin Rule）。
- **现象 B（证书 pin）**：`render_client()` 在 `CERT_FILE` 存在时**无条件**写 `pinnedPeerCertSha256`（本例是公网 CA 真证书，脚本还打印 `客户端 pin 自签证书 SHA256: 48165d74…`）。CDN 路径上 TLS 对端是 Cloudflare 边缘，指纹必然不匹配：
  ```
  transport/internet/tls: peer cert is unrecognized (against pinnedPeerCertSha256)
  ```
  **去掉 pin、并把端口改成 8443 后立刻 `204 / 1.73s`** → 节点本身完好，是生成结果的两处缺陷叠加。
- **正面证据**：Cloudflare 确实能回源到源站该端口 —— `curl https://moontv.6896698.xyz:8443/aVCR3P0A/` = `400`（CF 边缘 IP，xray 拒绝裸 HTTP 探测），直连源站 `https://107.173.154.178:8443/aVCR3P0A/` = `400`。

### P1-4　分享层的链接丢 SNI（TLS 类节点经订阅即不可用）
- **vless/trojan + TLS**：`nodes.py: build_share_link()` 里 `host = meta.host or n.sni`，而 `n.sni` 只从 REALITY 的 `serverNames` 取（`nodes.py:84,95`）→ 普通 TLS 节点拿不到 sni，生成的链接**没有 `sni=`**：
  ```
  transport/internet/websocket: failed to dial to 107.173.154.178:29601
    > tls: failed to verify certificate: x509: cannot validate certificate for 107.173.154.178 because it doesn't contain any IP SANs
  ```
- **hysteria2**：`q = {"sni": meta.get("host")}` 把"连接地址"当成了"SNI"，于是 `sni=107.173.154.178`：
  ```
  proxy/hysteria: RoundTrip err > CRYPTO_ERROR 0x12a (local):
    tls: failed to verify certificate: x509: cannot validate certificate for 107.173.154.178 because it doesn't contain any IP SANs
  ```
  （同时丢了生成器链接里的 `alpn=h3&upmbps=50&downmbps=200`。）
- **对比**：同一个节点的生成器链接是正确的（`out/hy2_share-04.txt` 里 `sni=moontv.6896698.xyz&alpn=h3&upmbps=50&downmbps=200`）。

### P1-5　`xbd` 的 `parse_trojan()` 丢 `pbk/sid`，Trojan+REALITY 节点被静默丢弃
- **现象**：订阅 5 个节点只导入 4 个；`/tmp/.xbd_skipped.json` 给出**误导性原因**"Xray 内核不支持该协议（trojan）"。
- **根因**：`lib/node.py: parse_trojan()` 没有把 query 里的 `pbk/sid` 写进 `reality_public_key/reality_short_id`（`parse_vless()` 有：`"reality_public_key": q.get("pbk") or ""`）；随后 `compat.check_xray()` 命中 `security == "reality" and not node.get("reality_public_key")` → `NOT_SUPPORTED` → `nodefilter.py` 以 `can_use_xray=False` 跳过。
- **复现**（CC）：
  ```
  $ python3 -c "… import node as N, compat as C …"
  can_use_xray: False
      协议 SUPPORTED TROJAN      地址 SUPPORTED 107.173.154.178:29602
      指纹 SUPPORTED chrome      凭据 SUPPORTED 完整
      传输 SUPPORTED raw         安全 SUPPORTED reality
      Reality 公钥 NOT_SUPPORTED security=reality 但缺少 pbk
  解析结果: "reality_public_key": "", "reality_short_id": ""
  ```

### P2-6　面板"添加节点"菜单 4/5 项与派发脚本错位
`ui_menu 4 "HTTP（无加密，同上）"` 实际执行 `conf/vlessecn.sh`；`ui_menu 5 "VLESS-ECN（tcp 传输 + ML-KEM-768）"` 实际执行 `conf/http.sh`（`/root/xray-panel.sh` 内 `case` 分支与菜单文案互换）。用户按 4 想建 HTTP，建出来的是 VLESS-ECN。

### P2-7　对公网 CA 证书也强制 pin
`render_client()` 只判断 `[ -f "$CERT_FILE" ]`，注释里写明"用公网 CA 签的证书走正常校验，不需要 pin —— 那时 pin 反而多余"，实现却无条件写 `pinnedPeerCertSha256`。任何走 CDN/中转或证书轮换的节点都会因此连不上（见 P0-3-B）。

### P2-8　"全协议一键生成"在本机是空操作，且不覆盖 VLESS
`conf/batch.sh` 的 `BATCH_PROTOS=(Reality Trojan Shadowsocks hysteria2)` 且按片段前缀幂等；本机 `reality-*/trojan-*/ss2022-*/hysteria-*` 都已存在 → 菜单 12 会**逐个 `[已存在] 跳过`**，一点新东西都不会生成；它也不含 VLESS-xHTTP/WS。用户若想"一键全协议"会得到"什么都没发生"。

### P3-9　`分享名称 [分享-]` 提示里带未闭合的 ANSI 复位
`printf "  分享名称 [分享-${_RST}]: "` → 终端回显为 `分享名称 [分享-]:`（默认值字样错位/颜色复位丢失），实测原文见 §3.2。

### P3-10　ECHConfig 的 `public_name` 用了真实域名
`generate_ech()` 调 `xray tls ech --serverName "$CERT_DOMAIN"`，public_name 因此等于真实站点名 → 外层 SNI 明文即真实域名（见 §5.4）。用于"隐藏 SNI"的 ECH 在这里失去了意义。

### P3-11　`_srv_ask_name` 的"服务器标识"提示实际不会出现
`xray_ensure_lib` 之后 `[[ -f "$_XRAY_CACHE/lib/naming.sh" ]] || return 0` 静默返回，导致菜单项 1/2 少了节点名前缀这一步（也直接导致我第一版按键序列错位）。属"取不到库就悄悄降级"。

---

## 7. UNKNOWN 清单

1. **Xray 服务端为何不回 ECH 确认**：`echServerKeys` 在片段里、`-test` 为 `Configuration OK`、密钥由 `xray tls ech` 正常生成，但 ServerHello 无 `0xfe0d`。是 Xray 26.3.27 的实现只做"接受密文但不回确认"，还是需要额外开关/条件 —— **UNKNOWN**（未读 Xray-core 源码，未做对照实验）。
2. **Cloudflare zone 的 SSL 模式**（Full / Full(strict) / Flexible）：只证明了 CF 在 8443 上能回源到 xray、且源站 TLS 正常；具体 SSL 模式**UNKNOWN**（未调用 CF API，未查 zone 配置）。
3. **Argo（固定/临时）路径是否可用**：**未执行**。`conf/GDargo.sh` 会 `update_env /root/catmi/catmi.env`（生产 env 文件）、写死 `BASE_DIR=/root/catmi/xray`、还依赖外部 `One-click-script` 的 `argo/url_argo.sh` 与 CF Tunnel 凭据；`GDargo.sh` 的 `flow=xtls-rprx-vision` 与 `network=ws` 组合本身也非法。CDN 覆盖已由 VLESS-xHTTP `接入=CDN 直连` 完成，故未冒风险执行 → Argo 结论 **UNKNOWN**。
4. **给 CF 加 Origin Rule 把源站端口指到 8443 后，生成器那条 `:443` 链接是否就能通**：**UNKNOWN**（未改 CF 配置；仅证明了 `域:8443` 手工可达）。
5. **M / SB 两家的分享层是否有同样的"元数据缺失 / 丢 SNI"问题**：本轮只测了 X → **UNKNOWN**。
6. **第一次未隔离抓包里 `Config Id: 167`、无 SNI 的 7 个 ClientHello 出自哪个进程**：**UNKNOWN**（当时 `xbd` + Chromium dialer 在跑；无法归属，故未用于任何结论）。
7. **`out/vless-xhttp_client-07.json` 里 96 字符的 CF ECHConfigList 在 `CDN-ECH` 模式下是否真的会被客户端用于发起 ECH**：**UNKNOWN**（本轮 C 项只验证了 `直连 ECH` 那条链路）。

---

## 8. 收尾与清理（已执行）

- RN：面板后台会话（FIFO holder + `script` + `bash xray-panel.sh`）全部停止；`tcpdump` 停止；`/tmp/e2e`、`/tmp/e2e_repo`、当日 `.xray-panel.*` / `.xshare*` 临时目录删除
- CC：10 个临时 Xray 实例全部 kill；`/tmp/e2e` 删除；**`xbd` 恢复原节点 `CCSmHysteria2-01`、Chromium dialer 关闭、节点列表恢复原始 7 个**（导入的 4 个测试节点已 `xbd node remove`）
- 服务状态：RN `xrayls / mihomo / sing-box / nginx` 全部 `active`；CC `xbd` 运行中
- 基线回归：43 个基线端口一个不少；mihomo/sing-box/nginx 进程 PID 未变（仅 `xrayls` 按面板新增节点的标准流程重启过）
- **保留物**：RN 上新增的 5 个节点（任务授权的动作）与其分享令牌 `f64f61ce35e42b39a5f928d1c6d15ae5`；`out/share/` 下我为 5 个新节点补写的元数据
