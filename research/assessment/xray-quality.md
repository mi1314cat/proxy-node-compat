# X 内核（Xray 26.3.27）一键全协议 · 实跑与逐组合参数质量评估

- 评估对象：仓库 `/root/deepseek/repos/xray--core`（只读，未修改）；入口 `conf/batch.sh`（面板 `xray-panel.sh:615` → `xray_run conf/batch.sh`）
- 实测环境：RN `ssh rn`（107.173.154.178，RackNerd，Xray 26.3.27 d2758a0 go1.26.1）；客户端 `ssh CC`（192.168.1.178，armbian，Xray 26.3.27 arm64 + sing-box 1.14.2）
- 时间：2026-10-10（RN 本地时间 03:24–03:33 PDT）
- 纪律：`xray--core` 未修改；未 push；RN 正式服务（xrayls / mihomo / sing-box）全程未停未重启（收尾核对：三服务 active、`conf/*.json` 仍 22 个、xrayls 监听端口数仍 16）；本次自起的 xray 进程与 `/tmp/xb-*`、`/tmp/bare*`、`/tmp/x4-*` 全部清理，脚本自己产生的备份包 `conf-backup-batch-20261010-033225.tar.gz` 已删除（生产目录只剩原有 2 个备份包）

证据等级：**E1** 真机执行并观察到输出 ｜ **E2** 服务器上实读配置文件/日志 ｜ **E3** 仓库源码静态阅读（带行号） ｜ **E4** 外部规范/文档 ｜ **UNKNOWN** 未验证

---

## 1. 一键全协议实际执行结果

### 1.1 `conf/batch.sh` 到底做什么（E3）

| 项 | 事实 | 依据 |
|---|---|---|
| 协议列表 | `Reality Trojan Shadowsocks hysteria2` —— **只有 4 个**，且 hysteria2 走的也是 Xray 内核的 `protocol:"hysteria"` 入站，不是独立 hysteria 二进制 | `conf/batch.sh:38-39`；`conf/hysteria2.sh:35,685` |
| 是否覆盖"全协议" | 否。VLESS+XHTTP / WS / gRPC / httpupgrade / TCP+Vision / VMess / SOCKS 都不在 batch 里（在 `vlessxhttpecn.sh`、`nconf.sh`、`cconf.sh`、`preset.sh` 菜单里） | `conf/batch.sh:38`；`conf/vlessxhttpecn.sh:517-523` |
| 幂等规则 | `latest_fragment()` 只判断 `conf/<pfx>-*.json` 是否存在，存在即**跳过整个协议**，不追加新节点 | `conf/batch.sh:91,171-175` |
| 端口 | 唯一交互：端口区间；每个协议一个端口，游标写 `conf/.batch-ports`；区间耗尽回落 10000-59999 随机 | `conf/batch.sh:103-148,160`；`conf/lib/ports.sh:113-144` |
| 写盘位置 | 只写**入站片段** `conf/reality-NN.json` / `trojan-NN.json` / `ss2022-NN.json` / `hysteria-NN.json` + `out/*` 客户端文件 + 分享链接 | 实跑产物，见 §1.2 |
| 收尾 | 4 个协议跑完 → `verify.sh check`（`xray run -test -confdir`）→ **只在非沙箱下一次 `systemctl restart xrayls`** | `conf/batch.sh:198-241`；`conf/verify.sh:71,115` |
| 失败语义 | 单协议失败只记进 `BATCH_FAIL`，**最终仍 `return 0`** | `conf/batch.sh:176-186,243-245` |

### 1.2 实跑 A：干净沙箱（`XRAY_BASE_DIR=/tmp/xb-probe`，端口区间 25000-25100）

命令（脚本从仓库拷到 RN `/tmp/xb-scripts`，不改仓库）：

```
printf "1\n25000-25100\n" | XRAY_BASE_DIR=/tmp/xb-probe X_BATCH_LOG_DIR=/tmp/xb-logs \
  bash /tmp/xb-scripts/batch.sh          # 退出码 0
```

**结果：4 个协议 3 成功 1 失败；退出码 0。**

```
• Reality      [OK] 生成
• Trojan       [OK] 生成
• Shadowsocks  [失败] (详见 /tmp/xb-logs/x-batch-Shadowsocks.log)
• hysteria2    [OK] 生成
[OK]  Configuration OK.                     ← 统一校验通过（因为 SS 片段根本没生成）
生成成功: Reality Trojan hysteria2
失败(详情在日志末尾): Shadowsocks
[OK]  全协议一键生成流程结束                 ← 退出码 0
```

Shadowsocks 失败**原文**（E1，`/tmp/xb-logs/x-batch-Shadowsocks.log` 尾部）：

```
[Info] Batch 模式: 自动分配端口 = 25002
默认使用最高配置：2022-blake3-aes-256-gcm（AES-NI 硬件加速，防重放+防探测）。
选择: /tmp/xb-scripts/Shadowsocks.sh: line 232: gen_psk: command not found
是否自定义 PSK？回车=自动生成(推荐): [Error] PSK 长度错误：2022-blake3-aes-256-gcm 需要 32 字节 (获得 0 字节)
```

- 根因（E3）：`gen_psk` 只被调用、**全仓库无定义**。定义被 `1ef13f2`「端口分配收敛到 conf/lib/ports.sh, 删 317 行重复实现」删掉，调用点 `conf/Shadowsocks.sh:232` 留了下来（`1ef13f2^:conf/Shadowsocks.sh:76-83` 原有 `openssl rand -base64 16|32`）。`conf/lib/ports.sh` / `addr.sh`（该脚本仅 source 这两个）都不定义它。
- 后果：**一键全协议在干净机器上永远生成不出 SS2022 节点**，且不报错退出（误导调用方以为成功）。

生成的产物（3 个服务端片段 + `out/` 下 11 个文件，含 3 条分享链接、3 份 mihomo YAML、2 份 Xray 客户端 JSON）：

| 片段 | 端口 | Tag | 大小 | 内核是否接受 |
|---|---|---|---|---|
| `conf/reality-01.json` | 25000/tcp | REALITY-01 | 967B | ✅ |
| `conf/trojan-01.json` | 25001/tcp | TROJAN-01 | 732B | ✅ |
| `conf/hysteria-01.json` | 25002/**udp** | hysteria-01 | 714B | ✅（**Xray 26.3.27 接受 `protocol:"hysteria"` 入站**，实测监听 + 打通） |
| `conf/ss2022-01.json` | — | — | ❌ 未生成 |

`xray -test`（E1）：

```
$ /usr/local/bin/xray run -test -confdir /tmp/xb-probe/conf
Configuration OK.
```

关于「log 路径不存在会先报错」：**这 4 个协议片段根本没有 `log` 段**（E3：Reality.sh/Trojan.sh/Shadowsocks.sh/hysteria2.sh 全无 `log` 键），所以无需改 `null`。带 log 路径的只有 `conf/nconf.sh:18-23` / `conf/cconf.sh:20-24`（`$INSTALL_DIR/log/*.log`），生产机 `/root/catmi/xray/log/` 确实存在，故生产 confdir 的 `-test` 也通过（见 §1.3）。

**内核启动时对这批片段自己发出的告警（E1，原样）**：

```
[Warning] infra/conf: REALITY: Choosing apple, icloud, etc. as the target may get your IP blocked by the GFW   ← ×2
[Warning] infra/conf: REALITY: Listening on non-443 ports may get your IP blocked by the GFW                  ← ×2
[Warning] common/errors: The feature Trojan (with no Flow, etc.) is deprecated, ... Please migrate to VLESS with Flow & Seed ...
[Warning] infra/conf: congestion & up & down & udphop move to finalmask/quicParams                              ← 客户端 hysteriaSettings
```

### 1.3 实跑 B：RN 正式目录原地跑（不改动任何节点，禁重启）

```
# B1 直接 </dev/null 跑：只打印菜单就退出，什么都没做（read 遇 EOF → exit 0）
$ bash /tmp/xb-scripts/batch.sh </dev/null ; echo EXIT=$?        → EXIT=0（0 个节点被处理）
# B2 喂入菜单答案 + 端口区间，并禁用 systemd 重启
$ printf "1\n25000-25100\n" | X_BATCH_TEST_SKIP_RESTART=1 bash /tmp/xb-scripts/batch.sh
• Reality      [已存在] 跳过 (幂等)
• Trojan       [已存在] 跳过 (幂等)
• Shadowsocks  [已存在] 跳过 (幂等)
• hysteria2    [已存在] 跳过 (幂等)
[OK]  Configuration OK.
已存在(跳过): Reality Trojan Shadowsocks hysteria2
```

- 因幂等规则，**在已部署机器上"一键全协议"不会新增任何节点**：`conf/` 仍有 22 个 json、xrayls 未重启、未新增监听端口。
- 但它每次都会 `tar czf` 一份 `conf-backup-batch-<ts>.tar.gz`（本轮生成 `conf-backup-batch-20261010-033225.tar.gz`，已清理）。E1
- 顺带确认生产节点现状（汇总输出 + `conf/` 实读，E2）：Reality-01/03（50330 / 27474，SNI `one-piece.com` / `swdist.apple.com`）、Trojan-01/02（37944 / 19212，SNI `addons.mozilla.org` / `suse.com`）、SS2022-01（39839，**ss+REALITY 组合**）、hysteria-03（31879）、VLESS-XHTTP-01..06。

### 1.4 本轮产生的副作用（必须知会）

| 副作用 | 说明 | 依据 |
|---|---|---|
| `XRAY_BASE_DIR` 沙箱**不隔离** `XRevise.sh` | Reality/Trojan 的 `add` 会执行远程 `conf/XRevise.sh`，它把新 UUID/x25519 密钥/short_id 写进 `/root/catmi/xray/install_info.env` 与 `/usr/local/etc/xray/{privatekey,publickey,password,hash32}`，与 `XRAY_BASE_DIR` 无关 | 实跑后这四个文件 mtime 变为 2026-10-10 03:24:35/36；`Reality.sh:59,175` |
| 生产 env 被改写 | 运行中服务的配置不受影响（各片段内联自带密钥/UUID），但 env 现记录的是本轮 Trojan 那一份参数，与 `conf/reality-01.json` 里的旧 UUID 不一致 | E1+E2 |
| 沙箱 confdir 没有 outbound | `batch.sh` 只生成入站；裸 confdir 里 `xray -test` 通过，但真正转发时报 `app/dispatcher: default outbound handler not exist`（生产有 `out-*.json` 才正常） | E1 |

**未恢复原值的原因**：`install_info.env` 是可再生的中间状态文件，且在本轮之前就已与 `reality-01.json` 不一致（生产 xhttp 节点生成于 10-08）；没有可信的原始副本，强行回写风险更大。已在此明示。

---

## 2. 组合矩阵（隐蔽性 / 安全性 / 速度）

评分口径：优=同类最佳且已实测；良=无明显短板；中=有可被主动探测或降级的特征；差=有明显破绽或实测不可用。
"实测"列标注该行结论的证据来源；`—` 表示未做端到端实测（见 §5 UNKNOWN）。

| # | 组合（传输/安全） | 端口 | 隐蔽性 | 安全性 | 速度 | 关键理由 | 证据 |
|---|---|---|---|---|---|---|---|
| 1 | **VLESS+Vision+REALITY**（batch 生成，tcp，dest=apps.apple.com，fp=chrome，encryption=mlkem768x25519plus） | 25000 | **良** | **良** | **良** | 隐蔽：真 REALITY —— 用任意 SNI 探测都拿到**真 Apple 证书**（`CN=itunes.apple.com`，Apple Public EV Server RSA CA 1 - G1，verify ok），伪装可信；扣分项：非 443 端口、target 是 Apple CDN（内核自己警告可能被封）、sid 仅 4 字节 1 个。安全：REALITY 无自签证书、无 MITM 面，另叠加 ML-KEM VLESS Encryption；扣分项 `maxTimeDiff:40000`（40s 重放窗口）。速度：tcp+Vision 直连，实测 1.65 MB/s、CC 侧 total 0.85–1.14s（直连基线 0.40s） | E1 |
| 2 | **Trojan+REALITY**（batch 生成，tcp，dest=mensura.cdn-apple.com，无 flow） | 25001 | **中** | **良** | **良** | 隐蔽：REALITY 层同 #1 可信，但内核明示 `Trojan (with no Flow) is deprecated`，协议本身在退场；同样非 443 + Apple target。安全：20 字符 `[A-Za-z0-9]` 随机口令（`/dev/urandom`）、REALITY 无证书可 MITM。速度：实测 1.62 MB/s、0.83–0.89s（三组合里最稳） | E1 |
| 3 | **Hysteria2（Xray `protocol:"hysteria"` 入站）** udp+tls，自带真域名证书，alpn=h3，`obfs=none` | 25002/udp | **中→差** | **良** | **优/良** | 隐蔽：QUIC 明文 hysteria2 指纹、**无 obfs（salamander 关）、无 masquerade**、高位随机 UDP 端口、免费二级域名 SNI（`hxicc.catmicos.dpdns.org`）——UDP 在不少网络被 QoS/封锁。安全：真 CA 证书 + `insecure=0`（未关校验，未用 skip-cert-verify），无 pin 需求；扣分项客户端 `hysteriaSettings.up/down` 被 26.3.27 警告迁往 `finalmask/quicParams`。速度：实测最快 1.87 MB/s、部分请求 0.49s | E1 |
| 4 | **SS2022（batch 目标配置：2022-blake3-aes-256-gcm, tcp,udp, 无 TLS）** | — | **差**（若裸用） | **良** | **良** | 本次**未能生成**（`gen_psk` 缺失，见 §1.2），评分基于源码目标配置 + 生产已部署的 ss2022-01：裸 SS2022 无 TLS、流量特征明显（AEAD 长度/时序），可被主动探测；安全性本身不弱（2022 有前向保密、32B PSK，`Shadowsocks.sh:215,240-245` 长度校验正确），但同一份代码只发单用户 `password`，无多用户 iPSK/uPSK（`Shadowsocks.sh:343-347`） | E1+E3 |
| 5 | **SS2022+REALITY（生产 ss2022-01 实际形态 "AnyReality"）** | 39839 | **良** | **良** | **良** | SS 层被 REALITY 包住 → 探测看到的是 REALITY 伪装证书；`2022-blake3-aes-256-gcm` + 32 字节 PSK（实测 base64 解码 32B，正确）；短板：`maxTimeDiff:40000`、非 443 端口、ss:// 链接对 SIP022 不合规（该链接自带注释说明需叠加 streamSettings） | E2 |
| 6 | **VLESS+XHTTP+TLS（生产 04/05/06，0.0.0.0）** 自签 `cloudflare.com` 证书、`path:/`、`mode:auto`、`echServerKeys`、encryption=mlkem | 22726/38066/28936 | **中** | **差→中** | **良** | 隐蔽：ECH + h2 + 热门 SNI 是加分项，但**源站直接可达且出示自签 CN=cloudflare.com**（openssl 实测 verify code 18）；真实 cloudflare.com 从不自签 → 主动探测一眼识别；`path:/` 也是特征。安全：**分享链接里既没有 pin 也没有 allowInsecure**，严格客户端无法校验证书 → 实测「带 pin 204 / 不带 pin 失败」；仓库生成的 mihomo YAML 直接 `skip-cert-verify: true`（`vlessxhttpecn.sh:1017`）= 给 MITM 开门（Xray 客户端 JSON 反而正确 pin，`vlessxhttpecn.sh:1069-1077`）。速度：RN 本机 0.45s；WAN 未测 | E1+E2+E3 |
| 7 | **VLESS+XHTTP+TLS（生产 01/02/03）** | 45630/31722/41721（**仅 127.0.0.1**） | **中** | **中** | — | 安全面比 #6 好（回环绑定，只有 CDN/本机可达），但**分享链接里的端口是 25333/26906/22168，与片段实际端口完全不符** → 三条链接实测不可能连通（≥ 三条死链） | E2 |
| 8 | 仓库其它可选组合：VLESS+WS+TLS / VLESS+TCP(裸)+ML-KEM（`vlessecn.sh`）/ gRPC / httpupgrade / VMess | — | **UNKNOWN** | **UNKNOWN** | **UNKNOWN** | 不在 batch 范围内，本轮未部署未实测。静态已知：`vlessecn.sh` 裸 TCP 无 TLS 无 flow（`vlessecn.sh:329,368`）；`vlessecn.sh:48` 硬编码 `FALLBACK_ENC` 公开 ML-KEM 串，xrayls 不可用时会把**公开已知 PSK** 当节点密钥（E3，未实测） | E3 |

补充（速度口径）：所有吞吐数字都是 CC（家宽）→ RN(美国) → Cloudflare 的单次 5MB 采样，**受 CC 出口瓶颈影响**，不宜当作节点上限；RN 本机回环/公网直连均 <0.12s（E1）。

---

## 3. 参数级问题清单

`组合 | 参数 | 现值 | 问题 | 建议 | 依据`

### P0（会导致节点不可用 / 功能缺失）

| 组合 | 参数 | 现值 | 问题 | 建议 | 依据 |
|---|---|---|---|---|---|
| Reality（batch 生成 + 生产 reality-01/03） | 分享链接地址 `link_ip` | `104.28.201.80`（Cloudflare WARP 出口 IP，来自 `install_info.env`） | 服务器真实入口是 `107.173.154.178`；实测 CC→`104.28.201.80:25000` **TCP CLOSED/FILTERED、curl 15s 超时**，而 `107.173.154.178:25000` 204 通过 → **链接发出去就是死的**。生产 reality-share-01/03 同病 | 改用接口 IP（如 Trojan.sh 的 `hostname -I` 或 `x_public_addr`），并在写链接前校验该地址在本机接口上；env 里的 `PUBLIC_IP/link_ip` 已过期应重建 | E1+E2；`Reality.sh:365`（用 `link_ip`）、`Reality.sh:178-179`（读 env）、`install_info.env` 实读 |
| Shadowsocks（batch） | 函数 `gen_psk` | **未定义**（调用点 `Shadowsocks.sh:232`） | 干净机器上一键全协议**永远生成不出 SS2022**；且 batch 仍以退出码 0 收场 | 恢复被 `1ef13f2` 删掉的 `gen_psk`（`openssl rand -base64 16/32`），或改用 `lib/random.sh` 里的生成器 | E1（原文报错）+E3（`git show 1ef13f2^:conf/Shadowsocks.sh`） |
| VLESS+XHTTP（生产 01/02/03） | 分享链接端口 | 链接 25333/26906/22168 vs 片段 45630/31722/41721 | 链接与实际监听端口不一致，且这三个 inbound 只绑 `127.0.0.1` → 三条链接必然连不上 | 重新生成链接（从 conf 片段反推），或明确标注"仅 CDN 回源可达" | E2（`conf/vless-xhttp-0{1,2,3}.json` 实读 + `out/vless-xhttp_share-0{1,2,3}.txt` 实读） |
| VLESS+XHTTP（生产 04/05/06） | 证书校验信息 | 自签 `CN=cloudflare.com`，链接无 pin、无 allowInsecure | 严格客户端必然 TLS 校验失败（实测：带 pin=204，不带 pin=000）；而仓库另一条路（mihomo YAML）用 `skip-cert-verify: true` 绕过校验 = MITM 面 | 用真证书（ACME）或让 TLS 由 Cloudflare 终结；自签场景必须在客户端文档里给出 pin（`pinnedPeerCertSha256`）；不要用 `skip-cert-verify` | E1（pin/无 pin 对比实测）+E2（openssl verify 18）+E3（`vlessxhttpecn.sh:1017,1069-1077`） |

### P1（参数质量）

| 组合 | 参数 | 现值 | 问题 | 建议 | 依据 |
|---|---|---|---|---|---|
| Reality / Trojan / SS2022+REALITY | `maxTimeDiff` | `40000`（ms） | 40 秒的客户端时钟容忍窗口，明显放大 REALITY 重放攻击面（Xray 默认 0） | 删除或降到 ≤5000 | E2/E3：`Reality.sh:285`、`Trojan.sh:274`、`conf/ss2022-01.json` |
| Reality / Trojan（batch） | REALITY `target` / `serverNames` | `apps.apple.com` / `mensura.cdn-apple.com`（Apple CDN） | 内核自己告警 `Choosing apple, icloud, etc. as the target may get your IP blocked by the GFW`；Apple CDN 的 TLS 特征与大面积扫描目标都不利 | 换成非 Apple 的热门站点（且与 v6/证书链匹配），并保留内核告警 | E1（内核告警原文）+E3（`Reality.sh:281-282`、`Trojan.sh:270-272`） |
| 全部（batch 与生产） | 监听端口 | 25000/25001/25002、19212/27474/37944/39839/50330…（**无 443**） | 内核逐条告警 `REALITY: Listening on non-443 ports may get your IP blocked by the GFW`；高位端口本身就是弱特征 | 关键节点收敛到 443/8443，用 SNI 分流/回落复用 443 | E1（内核告警）+E2（`ss -tulnp` 实读） |
| Trojan（batch 与生产） | `flow` | 未设置 | 内核告警 `Trojan (with no Flow) is deprecated … migrate to VLESS with Flow & Seed` | 新节点改用 VLESS+Vision（batch 的 Reality 分支已经是这么做） | E1（内核告警）+E3（`Trojan.sh:306-311` 无 flow） |
| Hysteria2（batch 与生产） | `obfs` / `masquerade` | `obfs=none`、无 masquerade | QUIC 流量无任何混淆/伪装，Hysteria2 指纹明显；高位 UDP 端口也是特征 | 开 salamander obfs 或加 masquerade（伪装成真实网站），并把 UDP 放 443 | E2（`conf/hysteria-01.json`、hy2 分享链接）+E3（`hysteria2.sh:720,723`） |
| Hysteria2 | 客户端 `hysteriaSettings.up/down`（`50mbps/200mbps`） | 硬编码 | 26.3.27 实测告警 `congestion & up & down & udphop move to finalmask/quicParams` → 这些字段已被挪位、有被忽略风险；且带宽写死与实际链路无关 | 迁到新字段（`quicParams`/`finalmask`），或干脆不写带宽 | E1（内核告警原文）+E3（`hysteria2.sh:740,762`） |
| Hysteria2 | 分享链接参数 | `pin=`、`upmbps=`、`downmbps=`、`alpn=`、`mport=` | 与 Hysteria2 官方 URI Scheme 不符：pin 应为 `pinSHA256`，带宽参数"不应出现在 URI 里"，端口跳跃应在主机名写多端口而非 `mport=` → 规范客户端会忽略，自签场景直接失去 pin 保护 | 按官方 scheme 输出 `pinSHA256`，去掉带宽参数，跳跃改 `host:20000-50000` | E3（`hysteria2.sh:716-724`）+E4（v2.hysteria.network URI Scheme） |
| Shadowsocks | 分享链接编码 | `ss://base64url(method:password)@host:port#tag` | SIP022 明确要求 **2022 系列不得用 Base64URL 编码 userinfo**（应明文 + percent-encode） | 2022 方法改输出 `ss://2022-blake3-…:<pct-psk>@host:port#tag` | E3（`Shadowsocks.sh:391-392`）+E4（shadowsocks.org SIP002/SIP022） |
| batch 编排 | 端口游标 `.batch-ports` | 只写不读 | 失败的协议已占的端口不会被后续协议跳过 —— 实测 `.batch-ports` 内容 `25000 25001 25002 25002`，**25002 被分配两次**（SS 失败占一次、hysteria2 又拿一次） | `x_next_range_port` 应先读回游标文件再判占用 | E1（游标文件实读）+E3（`lib/ports.sh:113-132` 只 `>>` 不读） |
| batch 编排 | 退出码 | 有失败仍 `return 0` | 面板/CI 无法区分成功与部分失败 | `BATCH_FAIL` 非空时 `return 1` | E1（实跑 EXIT=0）+E3（`batch.sh:243-245`） |
| batch 编排 | 裸 confdir 无 outbound | 只有入站片段 | `xray -test` 通过但运行时 `default outbound handler not exist`（实测）；校验存在盲区 | 校验加一条"至少存在一个 outbound"的断言 | E1（服务端日志原文） |
| VLESS+XHTTP（生产 04/05/06） | SNI / 证书组合 | SNI `cloudflare.com` + 自签同名证书 | 热门域名 + 自签 = 主动探测最容易被识别的组合；且 `path:/` 无随机性 | 真证书 + 非根路径，或用 XHTTP 的 `extra`（如 `xPaddingBytes`）配合真实站点回落 | E1（openssl verify 18）+E2（`conf/vless-xhttp-04.json` 实读） |
| VLESS+XHTTP | `xhttpSettings.extra` | **未设置**（`{path,mode}`）；仅 `cconf.sh:117-123` 设了 `xPaddingBytes:"100-1000"`、`noSSEHeader`、`scMaxEachPostBytes` | 依赖内核默认（26.3.27 默认总是填充 100–1000、`Referer` 头），不写就失去可调的抗性旋钮，也无法随内核默认变化自保 | 显式写入 `extra`（含 `xPaddingBytes`），并纳入校验 | E3（`vlessxhttpecn.sh:810-813`）+E4（Xray XHTTP 默认行为，子代理读内核源码 26.3.27） |
| VLESS 系（XHTTP/WS，`vlessxhttpecn.sh`） | uTLS `fingerprint` | **未设置** | 客户端退化为 Go crypto/tls ClientHello（JA3 可识别）；服务端片段本身无此参数（fp 在客户端），但仓库生成的客户端 JSON/YAML 也没写 | 客户端明确 `fingerprint: chrome`（或随机主流值） | E3（`vlessxhttpecn.sh:1121-1131`） |
| 全协议 | ALPN | Reality/Trojan 未显式设置（默认协商 h2/http1.1，实测 reality 成功协商 h2）；hysteria2 设了 `h3`（与 QUIC 匹配 ✅） | Reality 未设 ALPN 属正常（靠 dest 目标语义），但 XHTTP/WS 同样未设 → 传输与 ALPN 匹配处于"无人管理"状态 | 按传输显式声明 ALPN（xhttp→h2/h3，ws→http/1.1） | E1（openssl 实测 h2）+E3（`vlessxhttpecn.sh` 无 alpn） |
| SS2022 | 多用户 | 单 `password`，无 `clients` | 无法按用户吊销/限流，一处泄露全员重发 | 用 2022 的 iPSK/uPSK 多用户结构 | E3（`Shadowsocks.sh:343-347`） |
| 全协议 | `mux` / `xudp` | **片段与分享链接均无 mux**（服务端默认关）；仓库客户端 `Client/lib/genconfig.py:274` 默认 `mux:{enabled:true,concurrency:8}` | 客户端一开 mux 就会与"服务端无 mux 配置"形成不对称：mux 自身有可识别特征，也是性能/稳定性变量 | 明确 mux 策略并写进节点元数据（要么统一不开，要么在链接/配置里显式声明） | E3（`genconfig.py:274`，各协议脚本均无 mux） |
| 全协议 | sniffing | Reality 片段 `routeOnly:true`，Trojan/SS `routeOnly:false`；hysteria 片段无 sniffing | 同类节点行为不一致，路由/落地上难预测 | 统一策略并写进生成器默认 | E2/E3（`conf/reality-01.json` vs `trojan-01.json`） |
| batch 编排 | 生产 env 副作用 | `XRevise.sh` 无视 `XRAY_BASE_DIR` 改写生产 `install_info.env` + `/usr/local/etc/xray/*` | 沙箱测试会污染生产密钥状态；虽不影响在跑的配置（片段内联），但会让后续生成用到"测试期"参数 | 让 XRevise 尊重 `XRAY_BASE_DIR`，或沙箱模式跳过 XRevise | E1（mtime 变化）+E3（`Reality.sh:59,175`） |

### 已核对、**没有**踩的 26.3.27 事实（逐条，E3）

| 事实 | 结论 | 依据 |
|---|---|---|
| 移除 HTTP(h2) transport | ✅ 干净：`conf/` 里只出现 `tcp`/`raw`/`ws`/`xhttp`，无 `network:"h2"/"http"` | 全仓 grep；`nconf.sh:137`=`tcp`、`cconf.sh:79`=`raw` |
| 移除 mKCP `header`/`seed` | ✅ 干净：无 `kcpSettings`、无 header/seed | 全仓 grep 0 命中 |
| `allowInsecure` 硬报错 | ✅ 干净：4 个协议脚本 0 处；`nconf.sh:198`/`cconf.sh:184`/`outbound.sh:410` 写的是 `false`（26.3.27 只对 `true` 硬报错，`false` 是无害空操作） | E3 + E4（XTLS/Xray-core#6247） |
| `streamSettings.method` 仅 ≥26.7.28 | ✅ 干净：无任何 streamSettings `method`（只有 SS 的 `settings.method`，那是另一回事） | 全仓 grep |
| REALITY 只允许 RAW/XHTTP/gRPC | ✅ 干净：Reality/Trojan/SS 全用 `network:"tcp"`（RAW 的旧别名），实测 26.3.27 接受并正常工作 | E1（内核启动 + 打通） |
| `packetEncoding` 任何版本都不存在 | ✅ 干净：全仓 0 命中 | 全仓 grep |
| ss2022 aes-128-gcm 必须 16 字节 | ✅ 校验正确（`expected=16`），默认 256-gcm 需 32 字节也正确；但生成器函数丢失（见 P0） | `Shadowsocks.sh:239-245` |
| HTTP transport 之外的另一条：**Xray 26.3.27 是否支持 `protocol:"hysteria"` 入站**（仓库文档自相矛盾：`docs/e2e-rn.md` 说支持、`docs/xray-progress.md` 说 ✗） | ✅ **实测支持**：`-test` 通过、UDP 25002 真实监听、经它出网 204 | E1 |

---

## 4. 连通性验证结果（全部 E1，真机）

拓扑：RN（107.173.154.178，临时 xray 服务端，端口 25000/tcp、25001/tcp、25002/udp）← CC（192.168.1.178）。
测试内容：`curl --socks5-hostname … https://www.gstatic.com/generate_204`（期望 204）+ `api.ipify.org` 取出口 IP + 5MB 下载测速。临时服务端收尾已停、端口已释放。

| # | 节点 | 客户端位置 | 结果 | 时延/速率 |
|---|---|---|---|---|
| 1 | Reality（VLESS+Vision+REALITY） | RN 127.0.0.1:25000 | ✅ 204 | 首次 5.13s（冷启动），再次 0.11s |
| 2 | Reality | RN → 公网 IP（107.173.154.178:25000） | ✅ 204 | 0.111s |
| 3 | Reality | RN → **分享链接里的地址 104.28.201.80:25000** | ❌ curl 000（15s 超时） | 同机 TCP 探测：`104.28.201.80:25000` CLOSED/FILTERED |
| 4 | Trojan+REALITY | RN 127.0.0.1:25001 | ✅ 204 | 0.060s |
| 5 | Hysteria2（UDP 25002） | RN 127.0.0.1:25002 | ✅ 204 | 0.116s |
| 6 | Reality | **CC → 107.173.154.178:25000** | ✅ 204 ×3（TCP OPEN） | total 1.14 / 0.85 / 0.93s |
| 7 | Trojan | **CC → 107.173.154.178:25001** | ✅ 204 ×3（TCP OPEN） | total 0.83 / 0.87 / 0.89s |
| 8 | Hysteria2 | **CC → 107.173.154.178:25002 (udp)** | ✅ 204 ×3 | total 0.96 / 0.49 / 0.51s（最快） |
| — | 直连基线（CC 不经代理） | CC → gstatic | ✅ 204 | 0.40s |
| 9 | 吞吐（5MB，speed.cloudflare.com） | CC 经 Reality | ✅ 200 | 1,646,396 B/s（≈13.2 Mbps） |
| 10 | 吞吐 | CC 经 Trojan | ✅ 200 | 1,615,868 B/s（≈12.9 Mbps） |
| 11 | 吞吐 | CC 经 Hysteria2 | ✅ 200 | 1,866,131 B/s（≈14.9 Mbps，最快） |
| — | 直连基线吞吐 | CC → speed.cloudflare.com | ⚠ 本次 60s 超时（同轮另一次 20MB 直连为 354,071 B/s）→ CC 出口不稳，速率对比仅供参考 | — |
| 12 | 生产 VLESS+XHTTP-04（127.0.0.1:22726） | RN，客户端**带 pin** | ✅ 204 | 0.45s |
| 13 | 同上 | RN，客户端**不带 pin**（= 链接所暗示的最小信息） | ❌ 证书校验失败 | 0.13s 快速失败 |
| 14 | 同上 | RN，客户端带 pin + ECH | ✅ 204 | 0.49s |

TLS 面实测（`openssl s_client`）：

| 目标 | SNI | 观察 |
|---|---|---|
| batch Reality 25000 | `apps.apple.com` / 任意（含 `example.com`） | 返回**真 Apple 证书** `CN=itunes.apple.com`，签发 `Apple Public EV Server RSA CA 1 - G1`，`TLSv1.3 / TLS_AES_256_GCM_SHA384`，ALPN h2，`Verify return code: 0 (ok)` → REALITY 回落行为正确、伪装可信 |
| 生产 reality 50330 | `one-piece.com` | 返回 `CN=one-piece.com`，签发 `Amazon RSA 2048 M01`（真站证书），TLSv1.3 |
| 生产 xhttp 22726 | `cloudflare.com` | **自签** `CN=cloudflare.com`（issuer 同），TLSv1.3 `TLS_AES_128_GCM_SHA256`，ALPN h2，`Verify return code: 18 (self-signed certificate)` |
| 同机 nginx 443 | `hxicc.catmicos.dpdns.org` | Let's Encrypt 真证书，TLSv1.3，**No ALPN negotiated** |

出口 IP：三种节点经 RN 出网的 `api.ipify.org` 都返回 `104.28.201.80` —— 说明 RN 的**出站**走 WARP/Cloudflare，正是 `install_info.env` 里 `PUBLIC_IP/link_ip` 被写成 Cloudflare 段的原因（也是 P0 头号问题的根因）。

---

## 5. 证据等级与 UNKNOWN

### 5.1 结论强度

- **E1（可直接复现的实测）**：batch 沙箱全流程与退出码、Shadowsocks `gen_psk` 报错原文、生产原地跑的幂等跳过、`xray -test` 结果、内核告警原文、`.batch-ports` 重复分配、三种节点的端到端 204/时延/吞吐、分享链接地址不可达、xhttp pin/无 pin 对比、openssl 证书与 TLS 版本、清理后的生产状态核对。
- **E2（服务器实读）**：生产 22 个 conf 片段、各分享链接、`vless-xhttp-04.json` 全文、`ss -tulnp`、xrayls 单元与日志、`install_info.env`。
- **E3（源码静态）**：各协议脚本的默认值、行号级依据、`gen_psk` 的 git 回归、batch 编排逻辑、26.3.27 兼容项逐条核对、`vlessxhttpecn.sh`/`vlessecn.sh` 的参数与 ECH/mux/fingerprint 现状。
- **E4（外部规范/文档）**：Hysteria2 URI Scheme、Shadowsocks SIP002/SIP022、Xray REALITY/XHTTP 行为、`allowInsecure` 仅 `true` 硬报错（XTLS/Xray-core#6247）。

### 5.2 UNKNOWN 清单（**未验证，不猜**）— 共 12 条

1. **生产 VLESS+XHTTP-04/05/06 走 Cloudflare CDN（客户端→CF→源站）是否可用**：只验证了本机直连源站（pin 下 204）。
2. **SS2022 batch 节点的真实参数质量**：本轮生成失败；§2 第 4 行是基于源码目标配置 + 生产 ss2022-01 的推断，不是实测产物。
3. **Hysteria2 `hysteriaSettings.up/down` 在 26.3.27 是否仍被采纳**（内核只说"move to finalmask/quicParams"）；`upmbps/downmbps` 对实际限速的影响未测。
4. **Hysteria2 在拥塞/多流/长连接下的表现**，以及 UDP QoS/封锁场景下的可用性（单次 5MB 采样不足以下结论）。
5. **CC 侧速率上限**：直连基线同轮超时，1.6–1.9 MB/s 不能代表节点上限（亦不能代表三者的真实排序）。
6. **生产 xhttp-04/05/06 的 ECH 实际效果（是否真的隐藏 SNI）**：源码注释与代码不一致（`vlessxhttpecn.sh:1028-1030` 宣称外层 SNI=cloudflare-ech.com，实际 `CLIENT_SNI=$CERT_DOMAIN`），未做抓包验证。
7. **`vlessxhttpecn.sh` 默认 WS 与 XHTTP 组合的端到端可用性**：未部署（batch 不含），仅有静态基线。
8. **gRPC / httpupgrade / VMess / SOCKS / 裸 TCP+ML-KEM（`vlessecn.sh`）**：完全未执行。
9. **`vlessecn.sh:48` 的公开 ML-KEM 兜底串是否真的会被用上**（需要 xrayls `vlessenc` 失败才触发），未构造该条件实测。
10. **26.3.27 对 Shadowsocks 的弃用告警是否会无条件打印**：生产 xrayls 日志里出现过 `Shadowsocks (with no Forward Secrecy…) is deprecated`，而生产唯一的 SS 入站是**有前向保密**的 2022-blake3-aes-256-gcm；本沙箱没生成出 SS 入站，无法复现 → 触发条件 UNKNOWN。
11. **发布侧（GFW 主动探测/流量识别）的真实抗性**：只能给出配置面与本地探测面证据，无法在受控的对抗环境验证。
12. **`install_info.env` / `/usr/local/etc/xray/*` 被本轮改写的具体前值**：无可信原始副本，未回滚（已在 §1.4 声明）。

### 5.3 最该先修的 5 件事（按影响排序）

1. **Reality 分享链接地址用错**（WARP 出口 IP）：链接发出去就是死的 —— 实测 `104.28.201.80:25000` 不可达，`107.173.154.178:25000` 通。
2. **`gen_psk` 缺失**：一键全协议在干净机器上永远缺 SS2022，且退出码仍为 0。
3. **batch 失败不改退出码 / 端口游标只写不读**：部分失败被当成成功，失败协议占用的端口被下一个协议重复分配（实测 25002 分配两次）。
4. **`maxTimeDiff: 40000`** 出现在 Reality / Trojan / SS+REALITY 三类节点：40 秒重放窗口，改掉成本最低、收益明确。
5. **REALITY target 选 Apple CDN + 全部节点非 443**：都是内核自己会告警的项；连同 XHTTP 自签 `cloudflare.com` 证书（无 pin 的链接 + mihomo `skip-cert-verify: true`）一起，是"配置面最容易被主动探测"的一组。

---

*报告结束。所有实测命令、输出、配置与日志摘录均取自 2026-10-10 RN/CC 上的实跑，收尾已清理临时进程与文件，未改动 `xray--core` 与 RN 正式服务。*
