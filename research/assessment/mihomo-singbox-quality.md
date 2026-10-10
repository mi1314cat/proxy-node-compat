# RN mihomo + sing-box 一键全协议节点 —— 传输参数质量评估

评估对象：RN `107.173.154.178` 上**已部署运行**的 mihomo v1.19.32 与 sing-box 1.14.2 全协议节点。
评估口径：**参数选得好不好**（隐蔽性 / 安全性 / 速度），不是"配置能不能启动"。
评估方式：只读审计 + 主动探测对照实验 + 从第三方主机（CC）做端到端实测 + 受控因果隔离实验。
**未修改 RN 上任何正式服务配置**；所有实验在 `/tmp` 完成并已清理。

评估时间：2026-10-10（宿主机与 RN 时钟相差约 ±2 分钟，日志时间戳已按原样引用）

---

## 0. 结论摘要（先看这段）

- **实测了 32 个组合**（mihomo 19 个 listener + sing-box 13 个 listener），全部有连通性/延迟/吞吐实测，无一编造。
- **8 个 `out/*_share-*.txt` 分享链接指向的端口在 RN 上根本不存在**（陈旧产物），另有多份 `out/` 客户端片段与其声称的节点不一致 —— 详见 §1.3。
- **最严重的参数缺陷是 ECH**：mihomo 的 5 份 CDN 客户端片段全部写 `ech-opts: {enable: true}` 但**没有静态 `ech-opts.config`**，一旦客户端的 DNS 解析器不返回 HTTPS(type 65) 记录，mihomo **硬失败**（`resolve ECH config error: no ECH config found in DNS records`），不是降级而是直接连不上。已用受控实验 3/3 复现。
- **第二严重的是 7 个端口会向明文 HTTP 探测回吐 Go 专有错误页**（`Client sent an HTTP request to an HTTPS server.`），真站一律静默断连 —— 这是一个可直接扫描分类的自建代理特征。
- **第三严重的是 SNI 冒充**：`mAnyTLS03-TLS` 用自签 `www.apple.com` 证书 + 客户端 `skip-cert-verify: true`，既无 pinning 又关闭校验，是唯一真正可被 MITM 的节点。
- **速度维度最差的是 mihomo 的两个 CDN-WS 节点**（实测 0 字节，随附片段开 ECH 导致），**安全性最差的是 mihomo `mAnyTLS03-TLS`**，**隐蔽性最差的是 sing-box `shadowsocks01-plain`**（裸 SS，无 TLS 无混淆）。
- **速度维度最优的是 QUIC 系**（hysteria2 / TUIC）：mihomo hy2-02 达 4.49–5.13 MB/s，sing-box hy2 达 5.07–5.24 MB/s，约为同环境下 TCP 系（1.4–2.6 MB/s）的 **2 倍以上**，三次采样一致。
- **UNKNOWN 9 条**（见 §5）—— 主要在被动 DPI 判定、UDP 限速、抗封锁现状、DNS 泄露端到端这些**没有工具就无法验证**的项目上。

---

## 1. 节点清单

### 1.1 判定"存活"的依据

不是照抄配置文件，而是三重交叉验证：

1. `ss -tlnp` / `ss -ulnp` 确认进程与实际绑定（mihomo pid 119320，sing-box pid 60510）；
2. 从**外部主机 CC**（armbian aarch64，`ssh CC`，`192.168.1.178`，到 RN 平均 RTT **199.08 ms**）做 TCP 连通验证；
3. `openssl s_client` 实测 TLS 版本 / ALPN / 证书主体 / 签发者。

> **CC 无法从 RN 反向访问**（RN 上 `ssh CC` → `Could not resolve hostname cc`），所以所有端到端测试都是 **CC → RN 公网**单向发起，这是唯一可行的实测视角。

### 1.2 mihomo（v1.19.32，`/root/catmi/mihomo/`）

服务端真源：`conf/config.yaml` + `conf/config.d/*.yaml`。
证书目录：`conf/certs/`（4 套证书，其中 **2 套是自签**）。

| # | tag | 协议 | 端口 | 传输 | TLS 模式 | 实测 ALPN | 证书 | 关键参数 |
|---|-----|------|------|------|----------|-----------|------|----------|
| 1 | mAnyTLS01-TLS | anytls | 25684 | — | 真 TLS | **无** | `fullchain.pem` = LE `CN=hxicc.catmicos.dpdns.org` | user=pass=`0647a947-…` |
| 2 | mAnyTLS02-TLS | anytls | 28725 | — | 真 TLS | **无** | `cert-hxicc…crt` LE | pass=`f537cd20…`（独立） |
| 3 | mAnyTLS03-TLS | anytls | 22812 | — | 真 TLS（**假身份**） | **无** | **自签** `CN=www.apple.com`（issuer=自己，到 2036） | 客户端 `skip-cert-verify: true` |
| 4 | mHysteria201-TLS | hysteria2 | 25682/UDP | QUIC | 真 TLS | h3 | `fullchain.pem` LE | `masquerade: https://www.bing.com`；user1=pass=`0647a947-…`；**obfs 未设** |
| 5 | mHysteria202-TLS | hysteria2 | 20309/UDP | QUIC | 真 TLS（**假身份**） | h3 | **自签** `CN=www.amazon.com` | 客户端 `fingerprint: b8f8fc05…`（**实测与证书 SHA256 完全一致**）；`masquerade: bing`；**obfs 未设** |
| 6 | mTUIC01-TLS | tuic | 25683/UDP | QUIC | 真 TLS | h3 | `fullchain.pem` LE | `congestion-controller: bbr`；`max-idle-time: 15000`；**uuid == password == `0647a947-…`** |
| 7 | mTrojan01-REALITY | trojan | 25672 | tcp | REALITY | 无 | dest `www.microsoft.com:443` | sid `58896ecc5f8bf710`；无 flow（trojan 无此参数） |
| 8 | mTrojan02-REALITY-gRPC | trojan | 25673 | grpc | REALITY | (h2) | dest `www.microsoft.com:443` | `grpc-service-name: tg02286ead`；**同一** pk/sid |
| 9 | mTrojan03-TLS | trojan | 25674 | tcp | 真 TLS | **无** | `fullchain.pem` LE | **listener 未写 `server-name`**；无填充 |
| 10 | mTrojan04-CDN-WS | trojan | 25680 | ws | 真 TLS | h1.1 | `fullchain.pem` LE | `ws-path: /cdnws-0ab96db5`；nginx→CF |
| 11 | mTrojan05-CDN-gRPC | trojan | 25681 | grpc | 真 TLS | (h2) | `fullchain.pem` LE | `grpc-service-name: cg0599db34` |
| 12 | mVLESS01-REALITY | vless | 25669 | tcp | REALITY | 无 | dest `www.microsoft.com:443` | **`flow: xtls-rprx-vision`** ✓ |
| 13 | mVLESS01-TLS-WS | vless | 25675 | ws | 真 TLS | h1.1 | `fullchain.pem` LE | **`ws-path: /wss01`**（自述式路径） |
| 14 | mVLESS02-REALITY-gRPC | vless | 25670 | grpc | REALITY | (h2) | dest `www.microsoft.com:443` | `gs025a08f0` |
| 15 | mVLESS02-TLS-XHTTP | vless | 25676 | xhttp | 真 TLS | **h2** ✓ | `fullchain.pem` LE | `mode: auto`，`path: /xhttps-6ecedb76`，`x-padding-bytes: 100-1000` ✓ |
| 16 | mVLESS03-REALITY-XHTTP | vless | 25671 | xhttp | REALITY | — | dest `www.microsoft.com:443` | `path: /xhr-7e11f298`，padding ✓ |
| 17 | mVLESS03-TLS-XHTTP-CDN | vless | 25677 | xhttp | 真 TLS | — | `fullchain.pem` LE | `path: /xhc-bcd2a955` |
| 18 | mVLESS04-CDN-WS | vless | 25678 | ws | 真 TLS | — | `fullchain.pem` LE | `ws-path: /cdnws-7a34637f` |
| 19 | mVLESS05-CDN-gRPC | vless | 25679 | grpc | 真 TLS | — | `fullchain.pem` LE | `cg0523759e` |

**共用材料（重要）**：19 个 listener 里有 **13 个共用同一个秘密 `0647a947-6f77-4a91-8df0-8ff9f2d5e720`**（作 VLESS uuid / trojan 密码 / AnyTLS 密码 / hy2 密码 / TUIC uuid+密码）；**5 个 REALITY listener 共用同一对密钥**（`private-key: UP7tMv5WPGrsOqUW32EBwygGg4yQebsnpdZMJOvFkUw`，客户端 `pbk=uMcVRoEWeMAwPaj6e3jSVCZfbl-gj37MH9_XI9tL5wY`）与**同一个 `short-id: 58896ecc5f8bf710`**、**同一个 dest `www.microsoft.com:443`**。

### 1.3 sing-box（v1.14.2，`/root/catmi/sing-box/`）

服务端真源：`config/*.json`（用 `-C config` 目录合并加载）。`sing-box version` 的 `Tags:` 含 `with_utls,with_quic,with_acme,with_clash_api,with_naive_outbound,with_cloudflared,with_purego`（即 uTLS / QUIC / naive / ECH 相关能力齐全）。

| # | tag | 协议 | 端口 | 传输 | TLS 模式 | 实测 ALPN | 证书 | 关键参数 |
|---|-----|------|------|------|----------|-----------|------|----------|
| 20 | reality01-REALITY | vless | 31000 | tcp | REALITY | 无 | dest `apps.apple.com:443` | **`flow: xtls-rprx-vision`** ✓；sid `60656f4e153adc66`（8B） |
| 21 | hysteria201-TLS | hysteria2 | 31001/UDP | QUIC | 真 TLS | h3 | `/home/web/certs/hxicc…_cert.pem` LE | `up_mbps: 100 / down_mbps: 500`；**无 `masquerade`**；`mask: none`；`hop: ""` |
| 22 | anytls01-TLS | anytls | 31002 | — | 真 TLS | **h2** ✓ | LE | `alpn: [h2, http/1.1]`（服务端已配） |
| 23 | vless01-TLS-CDN | vless | 127.0.0.1:31003 | ws | 真 TLS | h1.1 | LE | `path: /5ac821b0`；`alpn: [http/1.1]` ✓ |
| 24 | shadowsocks01-plain | shadowsocks | 31004/TCP+UDP | — | **无 TLS** | — | — | `2022-blake3-aes-128-gcm`；无 obfs/无插件 |
| 25 | tuic01-TLS | tuic | 31005/UDP | QUIC | 真 TLS | h3 | LE | `congestion_control: bbr` |
| 26 | vmess01-TLS-CDN | vmess | 127.0.0.1:31006 | ws | 真 TLS | h1.1 | LE | `path: /cba311b5`；`max_early_data: 2560` |
| 27 | trojan01-TLS-CDN | trojan | 127.0.0.1:31007 | ws | 真 TLS | h1.1 | LE | `path: /322c087d`；`max_early_data: 2560` |
| 28 | naive01-TLS | naive | 31008/TCP+UDP | — | 真 TLS | **h2** ✓ | LE | user `e53bd040a419` / pass `f695c3946d09`（各 48 bit） |
| 29 | shadowtls01-TLS | shadowtls v3 | 31009 | — | 转发真握手 | 无 | 转发 `apps.apple.com:443` | `strict_mode: true` ✓；内层 SS2022 在 `127.0.0.1:31010`，`multiplex{padding:true}` ✓ |
| 30 | vmess02-REALITY | vmess | 31011 | ws | REALITY | 无 | dest `python.org:443` | sid `a3baeab74472c469`；`path: /7025f50c` |
| 31 | trojan02-REALITY | trojan | 31012 | ws | REALITY | 无 | dest `ibm.com:443` | sid `c1f47cd762b2fa17`；`path: /9b527228` |
| 32 | anytls02-REALITY | anytls | 31013 | — | REALITY | 无 | dest `apache.org:443` | sid `5c102aa54237286f`；`password: g4RoPGzW…` |

**共用材料**：4 个 REALITY inbound **共用同一把私钥**（`YHwHJHAd2omiXFq3cG8577b8tEZFX-2PawKS02mUdFE`，客户端 `pbk=tnXodgtAkqwGSZBIQu-O9hRj1VsFG4PwMriVzy0cHwA`），但 **shortId 4 个各不相同**（比 mihomo 好）。该私钥**同时明文存放在 `out/reality-keys.json`** 里（输出目录，不是密钥目录）。

### 1.4 陈旧 / 不一致的产物（必须点名）

| 产物 | 问题 | 证据 |
|------|------|------|
| `mihomo/out/anytls_share-01.txt` | 指向 `:50877`，**该端口在 RN 上不存在** | `ss -tlnp` 无 50877；外部连不通 |
| `mihomo/out/hysteria2_share-01.txt` | 指向 `:21168`，不存在 | 同上 |
| `mihomo/out/hysteria2_share-10.txt` | 指向 `:23512`，不存在 | 同上 |
| `mihomo/out/hysteria2_share-11.txt` | 指向 `[2001:470:c:cf:…]:22737`，不存在 | 同上 |
| `mihomo/out/reality_share-04.txt` | 指向 `:42099`，不存在 | 同上 |
| `mihomo/out/trojan_share-01.txt` | 指向 `:56676`，不存在 | 同上 |
| `mihomo/out/tuicv5_share-01.txt` | 指向 `:38899`，不存在 | 同上 |
| `mihomo/out/tuicv5_share-09.txt` | 指向 `[2001:…]:23451`，不存在 | 同上 |
| `mihomo/out/vless_share-01.txt` | `type=tcp` 却指向 **Cloudflare 的 `hxicc…:443`** —— CF 不会替你转发裸 TCP+VLESS，该链接结构上不可能工作 | CF 只代理 HTTP(S)/WS/gRPC；同域名的可工作路径是 `type=ws&path=/5ac821b0` |
| `mihomo/.fw-ports` | 记的是 `31857/56676/21168/38899/50877/…`，**与实际监听的 25669–25684/28725/22812 完全不相交** | 面板自身的端口账本已失真 |
| `mihomo/install_info.env` | `REALITY_PORT=37440`、`PUBLIC_KEY=7_zzCh0SL4…` 全与线上不符 | 陈旧 |
| `sing-box/out/sb_client-trojan01-TLS-CDN.json`、`sb_client-vless01-TLS-CDN.json`、`sb_client-vmess01-TLS-CDN.json`、`sb_client-all.json` | 三个 CDN 节点写成 `server: 107.173.154.178, server_port: 443`（**裸 IP**），而其入站在 `127.0.0.1:31003/31006/31007`，443 上是 nginx —— **实测 0 字节、0.64 s 即失败**；正确的 `sb_share-*.txt` 用的是域名 | 见 §4.3 `s_cdn_vmess01_ASIP` |
| `sing-box/out/sb_share-vmess02-REALITY.txt` | 节点是 **VMess**，分享链接却写成 **`vless://`** 且带 `encryption=aes-128-gcm`（Xray 早已移除的旧 VLESS 加密），`host=` 还是空 | `sb_client-vmess02-REALITY.json` = `"type": "vmess"`；`sb_meta-vmess02-REALITY.json` 也是 vmess/ws |
| `sing-box/out/sb_share-anytls02-REALITY.txt` | `anytls://…?pbk=…&sid=…` —— **mihomo 的 anytls 结构体里没有 Reality 字段**（官方声明永不支持 AnyTLS+Reality），导入 mihomo 时 REALITY 参数被静默丢弃 | 本仓库 `research/kernel-mihomo.md` §C12 / 第 247、427 行（基于源码 `adapter/outbound/anytls.go:27-49`） |
| `mihomo/out/pub/public_key.env` | `PUBKEY_04` 重复写 7 次 | 文件内容 |

> 结论：`out/` 目录**不能当作发布源**。10 份 mihomo 分享链接里只有 3 份（`anytls_share-02`、`anytls_share-03`、`hysteria2_share-02`）与线上节点一致（口令逐字节核对通过）。

---

## 2. 组合矩阵

评分口径（先定死，避免主观）：

- **隐蔽性**：抗主动探测（明文/错 SNI/无 SNI 探测的响应是否与真站一致）+ 抗流量识别（uTLS 指纹、ALPN 是否与传输匹配、REALITY 还是自签假证书、SNI 可信度、填充/混淆、协议自身特征、端口、是否 CDN、是否 vision、mux）。
- **安全性**：证书校验是否可关/是否 pinning、密钥与凭据强度及复用、ECH、SS 是否 2022（前向保密）、TLS 版本与套件、DNS/UDP 泄露面。
- **速度**：§4 实测 TTFB 与吞吐为主，传输开销/UDP 支持/拥塞控制为辅。
- 等级：**优**=无明显缺陷且实测处于最优组；**良**=有轻微可改进点；**中**=有明确缺陷；**差**=有严重缺陷或实测不可用。

| # | 组合（节点） | 隐蔽性 | 安全性 | 速度 | 一句话理由 |
|---|--------------|:------:|:------:|:----:|------------|
| 1 | mAnyTLS01-TLS 25684 | 中 | 中 | 良 | AnyTLS 有填充设计，但**服务端不协商 ALPN**、直连高端口无 CDN；凭据与 13 个节点共用 |
| 2 | mAnyTLS02-TLS 28725 | 中 | 良 | 良 | 同上 ALPN 缺陷；密码独立是加分项 |
| 3 | mAnyTLS03-TLS 22812 | **差** | **差** | 良 | **自签 `www.apple.com` 冒充 + 客户端 `skip-cert-verify: true`、无 pinning** —— 唯一真可 MITM 的节点 |
| 4 | mHysteria201-TLS 25682 | 中 | 良 | **优** | QUIC 高端口、**无 obfs、无端口跳跃**；真 LE 证书安全；实测 3.84–4.56 MB/s |
| 5 | mHysteria202-TLS 20309 | 中 | 良 | **优** | 自签 `www.amazon.com`（但 **pin 实测正确**，等效校验）；实测 4.49–5.13 MB/s |
| 6 | mTUIC01-TLS 25683 | 中 | 中 | **优** | bbr + h3 正确；但 **uuid 与密码是同一个值**，拆开任一半即全破 |
| 7 | mTrojan01-REALITY 25672 | 良 | 良 | 良 | REALITY dest 可信、sid 8B 随机；trojan 无 vision 类缓解；与 4 个节点共用 dest/sid/密钥 |
| 8 | mTrojan02-REALITY-gRPC 25673 | 良 | 良 | 良 | gRPC 特征被 REALITY 外壳掩盖；实测 2.03–4.09 MB/s |
| 9 | mTrojan03-TLS 25674 | 中 | 良 | 良 | **裸 trojan over TLS、无 ALPN、listener 未写 server-name、无填充**；真证书 |
| 10 | mTrojan04-CDN-WS 25680 | **优** | 良 | **差** | CF+443+自有域名+ECH 可用，隐蔽性最好；但**随附客户端片段开 ECH 导致实测 0 字节** |
| 11 | mTrojan05-CDN-gRPC 25681 | **优** | 良 | 中 | 同上隐蔽性；gRPC 片段同样带 ECH（未直测该片段的 ECH，但同批 WS/gRPC 已复现）；去掉 ECH 后 2.56–4.04 MB/s |
| 12 | mVLESS01-REALITY 25669 | 良 | 良 | 良 | **`flow=xtls-rprx-vision` ✓**、fp=chrome ✓、sid 8B ✓；扣分在 dest/sid/密钥被 5 个节点共用 |
| 13 | mVLESS01-TLS-WS 25675 | **差** | 良 | 良 | **`ws-path: /wss01` 是自述式路径**（字面写着 wss），且无 CDN、明文探测回吐 Go 400 |
| 14 | mVLESS02-REALITY-gRPC 25670 | 良 | 良 | 良 | 同 #8；实测 1.82–3.45 MB/s |
| 15 | mVLESS02-TLS-XHTTP 25676 | 中 | 良 | 良 | **xhttp padding 100-1000 ✓、ALPN=h2 匹配 ✓**（本批最讲究的传输参数）；扣分在无 CDN + 明文探测 Go 400 泄漏 |
| 16 | mVLESS03-REALITY-XHTTP 25671 | 良 | 良 | 良 | REALITY+xhttp 双层，padding 正确；实测 1.90–1.88 MB/s |
| 17 | mVLESS03-TLS-XHTTP-CDN 25677 | **优** | 良 | 中 | CF 前置隐蔽性最好；随附片段带 ECH 未验通；实测 1.69–1.78 MB/s（去掉 ECH 时） |
| 18 | mVLESS04-CDN-WS 25678 | **优** | 良 | **差** | **随附片段实测 3/3 失败**；去掉 ECH 后立刻恢复 1.09–1.41 MB/s |
| 19 | mVLESS05-CDN-gRPC 25679 | **优** | 良 | 中 | 同 #11；去掉 ECH 后 1.94–3.17 MB/s |
| 20 | reality01-REALITY 31000 | 良 | 良 | 良 | vision ✓、sid 8B ✓、dest `apps.apple.com` 可信；实测 1.68–1.97 MB/s |
| 21 | hysteria201-TLS 31001 | **中** | 良 | **优** | **无 `masquerade`** → HTTP/3 探测得到 Go 原生 `404 page not found`（强特征）；**obfs=none、无端口跳跃**；真证书；实测 **5.07–5.24 MB/s（本批最快）** |
| 22 | anytls01-TLS 31002 | 良 | 良 | 良 | **ALPN h2 协商正确** ✓；真 LE 证书；实测 2.35–3.71 MB/s |
| 23 | vless01-TLS-CDN 31003→CF | 良 | 良 | 中 | CF+443+自有域名、`alpn:[http/1.1]` 正确；**域名已发布 ECHConfig 却未启用 ECH**（白白浪费一个隐蔽性收益） |
| 24 | shadowsocks01-plain 31004 | **差** | 良 | 良 | **裸 SS：无 TLS、无 obfs、无插件、TCP+UDP 都开** —— 高熵字节流 + 无握手，特征最明显；安全性靠 SS2022（AEAD+前向保密）尚可 |
| 25 | tuic01-TLS 31005 | 中 | 良 | **优** | bbr+h3 正确、真证书；QUIC 高端口自建特征；实测 2.05–3.78 MB/s |
| 26 | vmess01-TLS-CDN 31006→CF | 良 | 中 | **差** | 分享链接（域名）可用；但**随附 `sb_client-*.json` 用裸 IP:443 → 实测 0 字节** |
| 27 | trojan01-TLS-CDN 31007→CF | 良 | 中 | **差** | 同 #26（同一处 IP:443 参数错误） |
| 28 | naive01-TLS 31008 | 良 | 中 | 良 | naive = 真 HTTPS/HTTP2 CONNECT 语义，伪装性天然好；但凭据仅各 48 bit |
| 29 | shadowtls01-TLS 31009 | 良 | 良 | 中 | ShadowTLS v3 + `strict_mode: true` ✓ + 内层 SS2022 + `multiplex.padding` ✓；代价是每次都要向 `apps.apple.com` 真握手，TTFB 偏高 |
| 30 | vmess02-REALITY 31011 | 良 | 良 | 良 | REALITY+ws，sid 独立 8B；**分享 URI 却是 `vless://…encryption=aes-128-gcm`（协议与加密都错）**；mihomo 侧 `ws+reality-opts` 会静默失效 |
| 31 | trojan02-REALITY 31012 | 良 | 良 | 良 | 同上；实测 1.69–1.71 MB/s |
| 32 | anytls02-REALITY 31013 | 良 | 良 | 良 | REALITY 保护得当；但 **mihomo 不支持 anytls+reality**，跨内核不可移植 |

**矩阵速览（统计）**

（逐格数出来的，与上表一一对应，合计各 32）

| 维度 | 优 | 良 | 中 | 差 |
|------|:--:|:--:|:--:|:--:|
| 隐蔽性 | 5 | 15 | 9 | 3 |
| 安全性 | 0 | 26 | 5 | 1 |
| 速度 | 5 | 18 | 5 | 4 |

- 隐蔽性 **差** 的 3 个：`mAnyTLS03-TLS`（自签冒充域名）、`mVLESS01-TLS-WS`（`/wss01` 自述路径）、`shadowsocks01-plain`（裸 SS）。
- 安全性 **没有"优"**：因为全站存在秘密复用（§P15），没有哪个节点在"凭据卫生"这一项上完全干净；**差** 只有 `mAnyTLS03-TLS`。
- 速度 **差** 的 4 个全部是"参数导致不可用"：`mTrojan04-CDN-WS`、`mVLESS04-CDN-WS`（ECH）、`vmess01-TLS-CDN`、`trojan01-TLS-CDN`（裸 IP:443）。

---

## 3. 参数级问题清单（最重要）

依据列给出：**实测**（本次实验）、**对照**（与真站/官方语义对比）、**文档/源码**（本仓库既有内核研究，基于真实源码与官方文档）。

| # | 节点 | 参数 | 现值 | 问题 | 建议值 | 依据 |
|---|------|------|------|------|--------|------|
| P1 | `mTrojan04-CDN-WS`、`mVLESS04-CDN-WS`、`mVLESS03-TLS-XHTTP-CDN`、`mVLESS05-CDN-gRPC`、`mTrojan05-CDN-gRPC`（随附客户端片段） | `ech-opts` | `enable: true` + `query-server-name: <域名>`，**无 `config`** | 客户端 DNS 解析器若不返回 HTTPS(type 65) 记录，mihomo **硬失败**：`resolve ECH config error: no ECH config found in DNS records`，节点直接不可用（非降级） | 二选一：①`ech-opts.config: AEX+DQBBDAAgACCryJDgUdOOMoGiT2M3FRRYHMTiXqEf5CEzN4O3g47uAQAEAAEAAQASY2xvdWRmbGFyZS1lY2guY29tAAA=`（从该域名 HTTPS RR 取到的静态 ECHConfigList，绑死解析器无关）；②在"节点片段"里去掉 `enable: true`，只在受控的整份客户端配置里开 | **实测**：WS+ECH 3/3 失败、gRPC+ECH 2/2 失败；去掉 ECH 后 WS 3/3 通过（1.09–1.41 MB/s）、gRPC 通过（2.56–4.04 MB/s）。日志原文见 §4.4。**对照**：`dig HTTPS hxicc.catmicos.dpdns.org @1.1.1.1` 确实返回 ECHConfig，但 CC 的解析器（192.168.1.1）返回 **0 字节**。生成器自己的注释（`src/client.sh:600-660`）也记录了同一现象 |
| P2 | 7 个端口：`mVLESS01-TLS-WS` 25675、`mVLESS02-TLS-XHTTP` 25676、`mVLESS03-TLS-XHTTP-CDN` 25677、`mVLESS04-CDN-WS` 25678、`mVLESS05-CDN-gRPC` 25679、`mTrojan04-CDN-WS` 25680、`mTrojan05-CDN-gRPC` 25681 | 明文 HTTP 探测响应 | `HTTP/1.0 400 Bad Request` + `Client sent an HTTP request to an HTTPS server.` | 这是 **Go `net/http` 的专有错误串**。真站对"往 443 发明文 HTTP"一律**静默断连**（对照组 4/4 全部 `<empty/closed>`）。扫描器只要 `GET /` 就能把这 7 个端口分类为"Go 写的自建 HTTPS" | 给这些监听套一个真实的 HTTP 前置（nginx/caddy 反代，或让 mihomo 的 http 层返回与目标站一致的响应）；至少不要让 Go 默认错误串外泄 | **实测**：24 个端口逐一探测，7 个回吐 Go 400，其余 closed/reset；**对照**：`www.microsoft.com:443`/`apps.apple.com:443`/`ibm.com:443`/`www.apple.com:443` 全部 `<empty/closed>` |
| P3 | `mAnyTLS03-TLS` 22812 | `sni` + 客户端 `skip-cert-verify` | 自签 `CN=www.apple.com`（issuer=自己，2036 到期）+ `skip-cert-verify: true` + `insecure=1` | ①冒充自己**不拥有**的域名；②**关闭证书校验且无 pinning** → 链路上任何人可 MITM 且客户端无感 | 换成自有域名 + 真 LE 证书（把 `fullchain.pem` 复用给它）；若必须自签，**必须**加 `fingerprint: <证书公钥 SHA256>`（学 `mHysteria202-TLS` 的做法），并把 SNI 改回 `hxicc.catmicos.dpdns.org` | **实测**：`openssl x509` 显示 `subject=CN=www.apple.com, issuer=CN=www.apple.com`；`openssl s_client -servername www.apple.com` 实测 `Verification:` 为空（校验失败）；对照真 `www.apple.com:443` 返回 Apple EV 证书 |
| P4 | `mVLESS01-TLS-WS` 25675 | `ws-path` | `/wss01` | 路径字面自述 "wss"，扫描器字典里排前列；同批其他节点都用随机 hex（`/cdnws-0ab96db5`、`/5ac821b0`），说明这是漏改的占位值 | 改成 ≥16 位随机 hex，如 `/cdnws-<8字节随机>`；并保持与客户端片段一致 | **对照**：`install_info.env` 里残留的 `WS_PATH=/v2dnz8raf1` 也是随机的，说明该工具本意就是随机路径 |
| P5 | `mAnyTLS01-TLS` 25684、`mAnyTLS02-TLS` 28725、`mAnyTLS03-TLS` 22812（mihomo 服务端） | `alpn` | listener **未配置**，实测**不协商任何 ALPN** | 客户端（`anytls_client-02.yaml`）明确声明 `alpn: [h2, http/1.1]`，服务端却回空 —— **声明与实际不符**，且浏览器场景下"客户端给了 ALPN、服务端不回"本身是一个可观测偏差 | 在 anytls listener 上补 `alpn: [h2, http/1.1]`，或把客户端片段的 `alpn` 一并去掉保持一致（**sing-box 侧 31002 已正确协商 h2，可作参照**） | **实测**：`openssl s_client -alpn h2,http/1.1` → 25684/28725/22812 全部 `<none>`；31002 → `ALPN protocol: h2` |
| P6 | `mTUIC01-TLS` 25683（服务端 `users: 0647a947-…: 0647a947-…`；客户端 `tuicv5_client-01.yaml` uuid==password） | `uuid` / `password` | 两者**同一个值** | TUIC 的 uuid 与 password 是两个独立凭据，取同一值等于把凭据强度减半：uuid 在分享链接/日志里是明文可见的，泄露 uuid 即同时泄露密码 | 生成独立随机 password（≥32 hex）；全局排查"一个秘密走遍 13 个节点"的问题 | **实测**：`conf/config.yaml` 中 `users: 0647a947-6f77-4a91-8df0-8ff9f2d5e720: 0647a947-6f77-4a91-8df0-8ff9f2d5e720`；客户端 YAML uuid/password 字段逐字相同。**对照**：sing-box 侧 TUIC 用的是独立 uuid+独立 password（正确样板） |
| P7 | `hysteria201-TLS` 31001（sing-box） | `masquerade` | **未配置** | HTTP/3 探测该端口得到 Go 原生 `404 page not found`（19 字节）—— 一个"QUIC 服务器 + 无伪装 + Go 404"的组合极易被主动探测分类 | 配 `"masquerade": "https://www.bing.com"`（与 mihomo 侧一致）或自建静态站；同时 `sb_meta-hysteria201-TLS.json` 里 `"mask": "none"` 说明面板根本没生成该参数 | **实测**：`curl --http3-only --resolve …:31001:127.0.0.1` → `code=404 size=19`，正文 `404 page not found`；同法测 mihomo 的 25682/20309 → 返回 `400 Invalid URL` 的上游站点页面（masquerade 生效），**两者对比明显** |
| P8 | 全部 hysteria2 节点：`mHysteria201-TLS` 25682、`mHysteria202-TLS` 20309、`hysteria201-TLS` 31001 | `obfs` / `ports`（端口跳跃） | `obfs: none`（`mask: none`）；`hop: ""` | ①无 Salamander 混淆 → QUIC 流量可被识别为"非标准 HTTP/3"；②**无端口跳跃**：UDP 单端口在 QoS/限速场景下最容易被整段掐掉，而端口跳跃正是 hy2 应对此场景的核心参数 | `obfs: salamander` + 强随机 `obfs-password`；`ports: 20000-40000` + `hop-interval`（服务端用同一区间）；两端参数必须配对 | **对照**：hy2 的 obfs/端口跳跃是官方设计用于抗 QoS 的参数；本部署 `sb_meta` 的 `"mask": "none"`、`"hop": ""` 明确为空 |
| P9 | `sing-box` 三个 CDN 客户端产物：`sb_client-trojan01-TLS-CDN.json`、`sb_client-vless01-TLS-CDN.json`、`sb_client-vmess01-TLS-CDN.json`、`sb_client-all.json` | `server` | `107.173.154.178`（裸 IP）+ `server_port: 443` | CDN 节点必须连 **Cloudflare 边缘的域名**。裸 IP:443 打的是源站 nginx，而这三个入站监听在 `127.0.0.1:31003/31006/31007` —— **结构上不可能连通** | `server: hxicc.catmicos.dpdns.org`（`sb_share-*.txt` 里就是对的，客户端产物与分享链接不一致） | **实测**：`s_cdn_vmess01_ASIP`（IP:443 变体）→ TTFB 0、下载 **0 字节**、0.64 s 失败；同节点域名变体 `s_cdn_vmess01` → 1.59/1.47 MB/s 正常 |
| P10 | 25 个 TLS 节点（除 `shadowsocks01-plain` 31004） | `alpn` | 见表；sing-box 三个 CDN 节点已正确写 `alpn: ["http/1.1"]`，**mihomo 的 5 个 CDN 片段全部未写 alpn** | WS 走 HTTP/1.1，若客户端 uTLS 声明 h2 而 CF 选 h2，WebSocket 升级会失败（RFC 8441 需 CONNECT） | mihomo CDN-WS 片段补 `alpn: [http/1.1]`；CDN-gRPC 补 `alpn: [h2]` | **实测**：源站 nginx 对 `/cdnws-*` 回 `HTTP/2 101`（curl 报 `Invalid HTTP header field … value: [101]`，即 WS-over-h2 非法）；sing-box 侧加 `alpn:[http/1.1]` 的 CDN 节点 3/3 可用，未加的则不稳定。**注意**：本项与 P1 是两条独立缺陷，P1 才是实测主因 |
| P11 | 全站 | 防火墙 | `ufw status: inactive`；`iptables -P INPUT ACCEPT`，**无任何规则** | 24 个代理端口全部对全网开放。日志显示它们**正在被扫**：`error-mihomo.log` 97 条握手错误，来源含 `212.102.40.218`（`unn-212-102-40-218.cdn77.com`，30 次）、`85.217.149.0/24` 网段多个地址、`183.210.249.163`、多个 DigitalOcean IP，探测内容包括 `tls: first record does not look like a TLS handshake` 与 `client sent an HTTP request to an HTTPS server` | 只放行真正使用的端口；对非白名单来源直接 DROP（不要 REJECT，避免回声）；把"高端口全开"改成按需开放 | **实测**：`ufw status` → inactive；`iptables -S` → 只有默认 ACCEPT；日志计数统计见上。**注意** `.fw-ports` 记录的端口与线上不符，说明防火墙账本已失真 |
| P12 | `mTrojan03-TLS` 25674 | listener `server-name` | **未配置** | mihomo 的 trojan listener 没有 `server-name` 时按任意 SNI 接受；实测用任意 SNI 都能完成握手，缺少 SNI 白名单这一层过滤 | 补 `server-name: [hxicc.catmicos.dpdns.org]` | **实测**：`openssl s_client -servername hxicc…` 与任意 SNI 均成功；对照 sing-box 的 TLS 入站多写了 `server_name` 字段 |
| P13 | `mTrojan03-TLS` 25674、`mTrojan01-REALITY` 25672、`mTrojan02-REALITY-gRPC` 25673 | 协议层填充 | trojan 无 `flow`/无 padding | trojan 协议本身在 TLS 之后是裸的"密码哈希 + 目标地址 + 原始流"，没有任何 TLS-in-TLS 或填充缓解；相比 VLESS+`xtls-rprx-vision` 缺少对"TLS-in-TLS 长度特征"的缓解 | 需要抗流量识别时，优先用 `vless + flow=xtls-rprx-vision`（本部署 `mVLESS01-REALITY`/`reality01-REALITY` 已正确使用）；trojan 节点保留作兼容即可 | **对照**：`mVLESS01-REALITY` 有 `flow: xtls-rprx-vision`，`reality01-REALITY` 也有；两个 trojan-REALITY 节点都没有（trojan 协议本身不支持该 flow） |
| P14 | mihomo 5 个 REALITY listener（25669/25670/25671/25672/25673） | `reality-opts` 的 `dest` / `short-id` / `private-key` | 全部同一个：dest `www.microsoft.com:443`、sid `58896ecc5f8bf710`、私钥 `UP7tMv5W…` | **相关性风险**：任何一个节点被识别/封锁，同一 dest+sid+密钥的另外 4 个同时暴露；且"一个 sid 打天下"失去了 sid 作为可轮换凭据的意义 | 每个节点独立 sid（≥8 字节随机，如 sing-box 侧的 4 个各不同）；dest 分散到 2–3 个与 VPS 同区域、同 AS 路径的可信站点 | **实测**：`conf/config.yaml` 5 处 `short-id: [58896ecc5f8bf710]` 与同一 `private-key`；对比 sing-box 的 4 个 sid 各自独立（`60656f4e…`/`5c102aa5…`/`a3baeab7…`/`c1f47cd7…`），是更好的做法 |
| P15 | 全站凭据 | 秘密复用 | `0647a947-6f77-4a91-8df0-8ff9f2d5e720` 出现在 **13 个 mihomo 入站**，并已出现在 `out/reality_share-04.txt` 这类可分发链接里 | 单点泄露即 13 个协议全失守；且该值同时充当 UUID、TUIC 密码、AnyTLS 密码、hy2 密码，跨协议可关联 | 每协议每节点独立随机凭据；已分发的旧链接全部作废重签 | **实测**：`conf/config.yaml` 与 `conf/config.d/*.yaml` 逐项核对；`out/reality_share-04.txt` 中该值明文可见 |
| P16 | `sing-box/out/reality-keys.json` | 私钥存放位置 | `{"private_key":"YHwHJHAd2omiXFq3cG8577b8tEZFX-2PawKS02mUdFE", …}` 放在 **`out/`（产物/分享目录）** | 私钥与"要分发出去的产物"同目录，任何"打包 out 目录"的动作都会连带泄露；泄露私钥 = 可完整冒充该 REALITY 服务 | 私钥只留在 `conf/` 或专门的密钥目录（`chmod 600`），产物目录只放 `public_key` | **实测**：`out/reality-keys.json` 内容如上；同目录下全是 `sb_share-*.txt` |
| P17 | 全部节点 | 端口选择 | 25669–25684、28725、22812、31000–31013 | 单 IP 上密集开放 24 个非标准高端口，本身就是"这是一台自建代理"的强信号（IP 信誉维度），且与 §P11 的无防火墙叠加 | 收敛端口数量；能用 443/CDN 的走 CDN；直连节点做端口跳跃或按需开放 | **实测**：`ss -tlnp` 全量枚举；外部可连通验证（CC 侧 `curl` 到 25669/25684/31000/31002/31008 全部 TCP 握手成功） |
| P18 | `sing-box` 三个 CDN 节点（`vless01-TLS-CDN`/`trojan01-TLS-CDN`/`vmess01-TLS-CDN`） | `ech` | **未启用** | 该域名的 HTTPS RR **已经发布了 Cloudflare 的 ECHConfig**（实测可见），mihomo 侧也在用；sing-box 侧白白浪费这个隐蔽性收益（ECH 能对上层的 SNI 做加密，直接削弱 SNI 明文这一最大暴露面） | 在 sing-box 客户端 `tls` 段加 `"ech": {"enabled": true, "config": "<base64 ECHConfigList>"}`（**务必用静态 config**，理由同 P1） | **实测**：`dig +short HTTPS hxicc.catmicos.dpdns.org @1.1.1.1` → `…ech=AEX+DQBBDAAgACCryJDgUdOOMoGiT2M3FRRYHMTiXqEf5CEzN4O3g47uAQAEAAEAAQASY2xvdWRmbGFyZS1lY2guY29tAAA=`；sing-box 三份 CDN 客户端 JSON 中 grep 无 `ech` |
| P19 | `shadowsocks01-plain` 31004 | 是否包 TLS / obfs | **无 TLS、无 obfs、无插件**，TCP+UDP 同端口 | 裸 SS 是特征最明显的组合：无握手、无证书、全高熵字节流，主动探测与被动识别都容易；本部署**同时**提供了带 ShadowTLS v3 的正确做法（31009），说明这是没套壳就上线的节点 | 用插件/前置包壳：`shadow-tls`（本机已有 31009 样板）或 `v2ray-plugin`/`restls`；或退一步只在内网/隧道内暴露 | **实测**：明文 HTTP 探测该端口 → 连接被 reset；`config/shadowsocks-01.json` 与 `sb_client-shadowsocks01-plain.json` 均无 `tls`/`plugin`；对照 `shadowtls-01.json` 的 `strict_mode: true` + 内层 SS2022 |
| P20 | `naive01-TLS` 31008 | 凭据长度 | user `e53bd040a419` / pass `f695c3946d09`（各 12 个 hex 字符 = 48 bit） | naive 用 HTTP Basic，凭据高熵但**长度偏短**；虽在 TLS 内，仍建议 ≥128 bit，避免离线暴破在弱口令策略下可行 | user/pass 各改为 ≥32 hex（128 bit） | **实测**：`config/naive-01.json` 与 `sb_client-naive01-TLS.json` 中该值；对照同部署其他协议均为 128 bit 级 |
| P21 | `vmess02-REALITY` 31011 / `trojan02-REALITY` 31012 | 传输选择（ws + REALITY） | `"transport": {"type": "ws", "path": "/<随机hex>"}` + REALITY | 在 REALITY 之上再叠 WS：①REALITY 已经提供了 TLS 层伪装，WS 不增加任何隐蔽性收益；②多一层 HTTP 升级握手与帧开销；③**跨内核陷阱**：mihomo 的 `reality-opts` 在 `network: ws` 分支会**静默失效**（ws 分支构造的 TLSConfig 不含 Reality 字段），把这两个节点导进 mihomo 会丢掉 REALITY 保护 | 需要伪装用 `vless + tcp + flow=xtls-rprx-vision + reality`（本部署 #20 的正确样板）；需要走 CDN 才用 ws | **对照/源码**：本仓库 `research/kernel-mihomo.md` 第 498 行（C2）与 247 行，基于 `adapter/outbound/vless.go`/`vmess.go`/`trojan.go` 的 ws 分支源码；**实测**：sing-box 侧该组合可用（1.69–2.21 MB/s），但不代表 mihomo 侧可用 |
| P22 | `mHysteria202-TLS` 20309 | pin 类型 | 客户端 `fingerprint: b8f8fc0516c1…` = **整张证书**的 SHA256 | **实测 pin 值正确**（无安全漏洞），但"整证书 pin"在证书轮换时会立刻失效（本证书 2036 才到期，风险低） | 改用公钥 pin（`certificate_public_key_sha256` / sing-box 侧）语义更稳 | **实测**：`openssl x509 -outform DER | sha256sum` = `b8f8fc0516c13230f65c2a4a728daa047353aaf8eadf76263562c60a9baa9a03`，与客户端 pin **逐字节相同** |
| P23 | mihomo 客户端片段 `hysteria2_hysteria2_client-01.yaml` | `up` / `down` | `up: "30"` / `down: "200"`（**无单位**），而同目录 `hysteria2_client-02.yaml` 用 `"50 Mbps"` | 写法不一致，易被误读为"漏了单位所以参数无效"。**经实测确认不是缺陷**：mihomo 把裸数字当 Mbps 解析 | 建议统一写成 `"30 Mbps"` / `"200 Mbps"` 以消除歧义（纯可读性，非功能问题） | **实测**（受控）：`down: "5"` → 0.535/0.545/0.525 MB/s = **4.20–4.36 Mbps**；`down: "5 Mbps"` → 0.555/0.546 MB/s = **4.37–4.44 Mbps**。两者一致 → 裸数字 == Mbps。**同时说明 **§5-U2 已解决 |
| P24 | `mHysteria201-TLS` 25682 / sing-box `hysteria201-TLS` 31001 | 带宽提示 | mihomo `up: "30" down: "200"`；sing-box 服务端 `up_mbps: 100 / down_mbps: 500`，客户端 `up_mbps: 100 / down_mbps: 500` | mihomo 客户端提示（30/200）**低于**服务端能力（100/500），会主动压低 brutal/BBR 的发送速率上限，浪费带宽 | 客户端提示对齐或高于服务端（如 100/500），或直接删掉让 hy2 自适应 | **实测**：同为 hy2，提示 200 Mbps 的 mHysteria202 达 4.49–5.13 MB/s，提示 200（同为 200，但 up 只有 30）的 mHysteria201 为 3.84–4.56 MB/s —— 差异在噪声范围内，**不作为强结论**，仅指出提示值与服务端不一致这一事实 |

---

## 4. 实测数据（命令与原始输出）

### 4.1 环境与基线

```bash
$ ssh rn 'openssl version; /root/catmi/mihomo/mihomo -v; /root/catmi/sing-box/sing-box version | head -3'
OpenSSL 3.5.7 9 Jun 2026 (Library: OpenSSL 3.5.7 9 Jun 2026)
Mihomo Meta v1.19.32 linux amd64 with go1.26.8 Wed Sep 30 16:55:19 UTC 2026
sing-box version 1.14.2
Environment: go1.26.8 linux/amd64
Tags: with_gvisor,with_quic,with_dhcp,with_wireguard,with_utls,with_acme,with_clash_api,with_tailscale,with_ccm,with_ocm,with_cloudflared,with_naive_outbound,with_usbip,with_openvpn,with_openconnect,badlinkname,tfogo_checklinkname0,with_purego
```

CC（测量客户端主机，`ssh CC`，armbian aarch64，4 核）：

```bash
$ ssh CC 'ping -c 6 -W 2 107.173.154.178 | tail -2'
6 packets transmitted, 6 packets received, 0% packet loss
round-trip min/avg/max/stddev = 198.766/199.076/199.298/0.191 ms

$ ssh CC 'curl -s -o /dev/null -w "connect=%{time_connect}\n" -k https://107.173.154.178/'
connect=0.194077                       # RN:443
$ ssh CC 'curl ... https://107.173.154.178:31000/'
port=31000 connect=0.194159 appconnect=0.421439   # REALITY 端口：握手 2 RTT，无额外往返
$ ssh CC 'curl -s -o /dev/null -w "appconnect=%{time_appconnect}\n" -k https://107.173.154.178:443/'
port=443   connect=0.194077 appconnect=0.410549   # 普通 TLS 端口
```

> **REALITY 不增加握手往返**：`31000`（REALITY）与 `443`（普通 TLS）的 `time_appconnect` 分别为 **0.4214 s / 0.4106 s**，在 199 ms RTT 下都是 2 RTT。这与"REALITY 需要在第一个 ClientHello 里带走认证、服务端可直接应答"的设计一致 —— **不需要**为 REALITY 额外扣分。

直连基线（CC 不走代理，n=3 / n=2）：

```
ttfb=0.412360 code=204 / ttfb=0.407968 code=204 / ttfb=0.366673 code=204
speed=300443 B/s  bytes=5000000 time=16.64 s
speed=2993207 B/s bytes=5000000 time=1.67 s      # ← 同一目标两次相差 10 倍
```

> ⚠ **测量局限（必须随数字一起读）**：CC 的出境链路**高度不稳定**，同一目标同一命令两次可差 10 倍。因此下表的**吞吐数字只能看量级与 PASS/FAIL**，不要把 1.5 与 2.0 MB/s 的差别当结论；TTFB 相对稳定，可用于比较。所有吞吐都是 `https://speed.cloudflare.com/__down?bytes=5000000`（5 MB），TTFB 是 `https://www.gstatic.com/generate_204`。

### 4.2 全量组合实测（32 个，各 2 次）

测量方式：CC 上 `/tmp/qeval/` 内运行 **mihomo v1.19.32 / sing-box 1.14.2**（arm64 官方 release），本地 `mixed` 入站 `127.0.0.1:18080`，用 `curl -x` 走代理。两个内核分两轮**串行**执行，互不并发。

| 组合 | TTFB(s) #1 / #2 | 吞吐(MB/s) #1 / #2 | 判定 |
|------|-----------------|--------------------|------|
| s_anytls01 | 0.845 / 0.487 | 2.35 / 3.71 | PASS |
| s_anytls02_reality | 0.860 / 0.580 | 1.75 / 3.58 | PASS |
| s_cdn_trojan01 | 2.244 / 1.375 | 1.43 / 1.52 | PASS |
| s_cdn_vless01 | 1.488 / 1.117 | 1.38 / 0.98 | PASS |
| s_cdn_vmess01 | 1.194 / 1.348 | 1.59 / 1.47 | PASS |
| **s_cdn_vmess01_ASIP** | **FAIL / FAIL** | **0 / 0** | **FAIL（IP:443 参数错误）** |
| **s_hy2_01** | 0.948 / 0.485 | **5.07 / 5.24** | PASS（最快） |
| s_naive01 | 0.965 / 0.557 | 1.98 / 3.67 | PASS |
| s_reality01 | 0.766 / 0.843 | 1.68 / 1.97 | PASS |
| s_shadowtls01 | 1.250 / 0.905 | 1.75 / 1.95 | PASS |
| s_ss_plain | 0.785 / 0.701 | 1.81 / 1.69 | PASS |
| s_trojan02_reality | 0.952 / 1.096 | 1.69 / 1.71 | PASS |
| s_tuic01 | 0.913 / 0.550 | 2.05 / 3.78 | PASS |
| s_vmess02_reality | 1.323 / 1.043 | 2.21 / 1.37 | PASS |
| m_anytls01 | 1.023 / 0.524 | 2.08 / 3.23 | PASS |
| m_anytls02 | 1.129 / 0.543 | 1.74 / 2.98 | PASS |
| m_anytls03_applesni | 1.421 / 0.450 | 2.05 / 3.77 | PASS |
| **m_cdn_trojan04_ws** | **FAIL / FAIL** | **0 / 0** | **FAIL（ECH）** |
| m_cdn_vless03_xhttp | 1.285 / 1.032 | 1.78 / 1.69 | PASS |
| **m_cdn_vless04_ws** | **FAIL / FAIL** | **0 / 0** | **FAIL（ECH）** |
| m_cdn_vless05_grpc | 1.118 / 1.143 | 1.94 / 3.17 | PASS |
| m_hy2_01 | 0.933 / 0.506 | 3.84 / 4.56 | PASS |
| **m_hy2_02_pin** | 1.010 / 0.500 | **4.49 / 5.13** | PASS |
| m_trojan01_reality | 0.761 / 1.042 | 2.01 / 1.38 | PASS |
| m_trojan03_tls | 0.918 / 0.983 | 2.57 / 1.75 | PASS |
| m_tuic01 | 0.662 / 0.487 | 2.27 / 3.73 | PASS |
| m_vless01_reality | 1.883 / 0.755 | 1.58 / 1.64 | PASS |
| m_vless01_tls_ws | 1.075 / 1.139 | 1.81 / 1.45 | PASS |
| m_vless02_xhttp_tls | 0.831 / 1.301 | 1.77 / 1.55 | PASS |
| m_vless03_reality_xhttp | 0.663 / 0.908 | 1.90 / 1.88 | PASS |
| x_m_vless02_reality_grpc | 0.913 / 0.518 | 1.82 / 3.45 | PASS |
| x_m_trojan02_reality_grpc | 0.851 / 0.472 | 2.03 / 4.09 | PASS |
| x_m_cdn_trojan05_grpc | FAIL / 0.920 | 2.56 / 4.04 | PASS |
| x_m_vless02_reality_grpc_NOWS（xhttp packet-up 变体） | 0.809 / 1.172 | 1.59 / 1.47 | PASS |

**由实测得到的三条稳健结论**：

1. **QUIC 系（hysteria2 / TUIC）明显更快**：hy2 三次采样 5.07/5.24、4.49/5.13、3.84/4.56 MB/s，全部高于 TCP 系最高的 2.57 MB/s。这是本次唯一跨样本一致的量级差异。
2. **CDN 组合 TTFB 系统性变差**：CDN 节点 TTFB 最小值 **1.032 s**（m_cdn_vless03_xhttp），直连节点最小 **0.450 s**；sing-box 侧 CDN 最小 1.117 s vs 直连最小 0.485 s。两端一致 → Cloudflare 回源确实带来 ≥0.5 s 的额外延迟。
3. **失败项都是参数所致，不是网络问题**：`s_cdn_vmess01_ASIP`（IP:443）、`m_cdn_trojan04_ws`/`m_cdn_vless04_ws`（ECH）在同批次同网络下，其"改对参数"的孪生配置全部 PASS。

### 4.3 IP:443 参数错误的直接证据

```bash
$ ssh CC 'curl -x http://127.0.0.1:18080 -w "speed=%{speed_download} bytes=%{size_download} time=%{time_total}\n" https://speed.cloudflare.com/__down?bytes=5000000'
# 节点 = sb_client-vmess01-TLS-CDN.json 原样（server: 107.173.154.178, port: 443）
speed=0 bytes=0 time=0.640048
speed=0 bytes=0 time=0.575035
# 同一节点，仅把 server 换成 hxicc.catmicos.dpdns.org
speed=1593414 bytes=5000000 time=3.137915
speed=1469100 bytes=5000000 time=3.403443
```

### 4.4 ECH 根因（受控隔离实验，单实例、3 次重复）

原站侧确认 ECHConfig **确实存在**：

```bash
$ ssh rn 'dig +short HTTPS hxicc.catmicos.dpdns.org @1.1.1.1'
1 . alpn="h3,h2" ipv4hint=104.21.51.73,172.67.177.62 \
  ech=AEX+DQBBDAAgACCryJDgUdOOMoGiT2M3FRRYHMTiXqEf5CEzN4O3g47uAQAEAAEAAQASY2xvdWRmbGFyZS1lY2guY29tAAA= \
  ipv6hint=2606:4700:3031::ac43:b13e,2606:4700:3035::6815:3349
```

但**客户端解析器不返回 type 65**，mihomo 于是硬失败。`log-level: debug` 原文：

```
level=debug   msg="[DNS] resolve hxicc.catmicos.dpdns.org HTTPS from udp://192.168.1.1:53"
level=debug   msg="[DNS] hxicc.catmicos.dpdns.org --> [] HTTPS from udp://192.168.1.1:53"
level=warning msg="[TCP] dial n (match Match/) 127.0.0.1:52084 --> www.gstatic.com:443 error: \
                 hxicc.catmicos.dpdns.org:443 connect error: \
                 resolve ECH config error: no ECH config found in DNS records"
```

受控实验矩阵（`/tmp/qeval/clean_exp.sh`，每例 3 次；HTTP/2 升级与 ALPN 作为协变量分离）：

| 例 | 配置 | 结果 |
|----|------|------|
| A2 | **随附片段原样**（无 alpn + ECH）→ `mh/m_cdn_vless04_ws.yaml` | **3/3 FAIL**（r1 在 0.7 ms 内即失败＝ECH 解析硬错；r2/r3 超时） |
| B | 无 alpn + **无 ECH** | **3/3 PASS**，1.21 / 1.12 / 1.09 MB/s，TTFB 1.06 / 1.10 / 1.06 |
| C | alpn `[http/1.1]` + **无 ECH** | **3/3 PASS**，0.45 / 1.15 / 1.41 MB/s |
| D | alpn `[http/1.1]` + **ECH** | **3/3 FAIL**（0 字节） |
| G | gRPC + **ECH** | **2/2 FAIL**（0 字节） |
| E | hy2 `down: "5"`（裸数字） | 3/3 PASS，4.20 / 4.36 / 4.28 Mbps |
| F | hy2 `down: "5 Mbps"` | 2/3 PASS，4.44 / 4.37 Mbps（r3 遇链路抖动） |

→ **B/C 通、D/G 失败 ⇒ ECH 是唯一主因，ALPN 不是**（P10 因此降级为次要项）。
→ **E ≈ F ⇒ 裸数字单位就是 Mbps**（P23 由"疑似缺陷"改判为"仅一致性建议"）。

### 4.5 主动探测对照实验

**(a) 明文 HTTP 打 TLS 端口**（Python raw socket，发送 `GET / HTTP/1.1\r\nHost: x\r\n\r\n`，5 s 超时）：

```
m-trojan03-TLS      <empty/closed>              m-vless01-REALITY   <empty/closed>
m-anytls01          <empty/closed>              s-reality01         <empty/closed>
s-shadowtls01       <ERR:TimeoutError>          CTRL-microsoft      <empty/closed>
s-anytls01          <ERR:ConnectionReset>       CTRL-apple          <empty/closed>
s-ss-plain          <ERR:ConnectionReset>       CTRL-ibm            <empty/closed>
s-naive01           <ERR:TimeoutError>          CTRL-www.apple      <empty/closed>
m-vless02-XHTTP     HTTP/1.0 400 Bad Request | Client sent an HTTP request to an HTTPS server.
```

24 端口全枚举结果：**7 个端口回吐 Go 专有 400**（25675/25676/25677/25678/25679/25680/25681），其余 closed/reset，**4 个真站对照全部静默断连**。

**(b) REALITY 主动探测**（含非白名单 SNI 与无 SNI）：

```
[m-vless01-REALITY]      sni=www.microsoft.com          => subject=…O=Microsoft Corporation, CN=www.microsoft.com
[m-vless01-offlist]      sni=www.google.com             => subject=…O=Microsoft Corporation, CN=www.microsoft.com
[m-vless01-bogus]        sni=nonexistent-abc123.example => subject=…O=Microsoft Corporation, CN=www.microsoft.com
[m-vless01-nosni]        sni=<none>                     => subject=…O=Microsoft Corporation, CN=www.microsoft.com
--- 对照：真 www.microsoft.com:443 ---
sni=nonexistent-abc123.example => subject=…O=Microsoft Corporation, CN=www.microsoft.com   Verify return code: 0 (ok)
sni=www.google.com             => subject=…O=Microsoft Corporation, CN=www.microsoft.com   Verify return code: 0 (ok)
--- 对照：真 ibm.com:443 ---
sni=nonexistent-abc123.example => subject=…O=International Business Machines Corporation, CN=ibm.com  Verify return code: 0 (ok)
```

> **重要：这一项是"通过"而不是"泄露"。** 我原本预期"任意 SNI 都回同一个证书"是 REALITY 的破绽，于是做了对照 —— 真的 `www.microsoft.com` / `ibm.com` 对错 SNI 也返回同一张证书且校验通过。**REALITY 的回落行为与真站一致 ⇒ 该向量上不可区分**，不扣分。（`s-reality01` 用 `-servername apps.apple.com` 时 `-brief` 显示 `CN=apps.apple.com`，完整输出为 `CN=itunes.apple.com`；后者与真站一致，前者是 `-brief` 的展示差异，非缺陷。）

**(c) hysteria2 的 HTTP/3 探测**：

```bash
$ ssh rn 'curl -sk --http3-only --resolve hxicc.catmicos.dpdns.org:31001:127.0.0.1 https://hxicc.catmicos.dpdns.org:31001/ -w "code=%{http_code} size=%{size_download}\n"'
code=404 size=19        body: 404 page not found          # sing-box：无 masquerade，Go 原生 404
$ ssh rn '… --resolve …:25682:127.0.0.1 …'
code=400 size=310       body: <HTML><HEAD><TITLE>Invalid URL</TITLE>…  # mihomo：masquerade 生效（上游页面）
```

### 4.6 证书 / 密钥 / 防火墙

```bash
$ ssh rn 'openssl x509 -in conf/certs/cert-www.apple.com.crt -noout -subject -issuer -dates'
subject=CN=www.apple.com
issuer=CN=www.apple.com                       # ← 自签
notBefore=Oct  9 08:55:53 2026 GMT / notAfter=Oct  6 08:55:53 2036 GMT
$ ssh rn 'openssl x509 -in conf/certs/fullchain.pem -noout -subject -issuer'
subject=CN=hxicc.catmicos.dpdns.org
issuer=C=US, O=Let's Encrypt, CN=YE1          # ← 真证书

$ ssh rn 'openssl x509 -in conf/certs/cert-www.amazon.com.crt -outform DER | sha256sum'
b8f8fc0516c13230f65c2a4a728daa047353aaf8eadf76263562c60a9baa9a03   # == 客户端 pin，逐字节一致

$ ssh rn 'ufw status; iptables -S | head -4'
Status: inactive
-P INPUT ACCEPT / -P FORWARD ACCEPT / -P OUTPUT ACCEPT

$ ssh rn 'grep -oE "from [0-9.]+:" error-mihomo.log | sort | uniq -c | sort -rn | head -4'
     30 212.102.40.218        # whois: unn-212-102-40-218.cdn77.com
      8 183.210.249.163
      5 67.207.95.230
      5 143.198.238.185
# 另有 85.217.149.0/24 网段 12 个不同地址；总计 97 条探测记录
```

### 4.7 TLS 版本 / ALPN / 内核调优

```bash
# 全部 25 个 TLS 端口实测：Protocol version: TLSv1.3（无 TLS1.2 及以下）；套件 TLS_AES_128_GCM_SHA256 或 TLS_AES_256_GCM_SHA384
# 源站 nginx 443 实测：TLSv1.3 / TLS_AES_256_GCM_SHA384 / X25519MLKEM768 / ALPN h2（含 --with-http_v3_module）
$ ssh rn 'sysctl net.ipv4.tcp_congestion_control net.core.default_qdisc net.ipv4.tcp_fastopen net.ipv4.tcp_mtu_probing'
net.ipv4.tcp_congestion_control = bbr
net.core.default_qdisc = fq_pie
net.ipv4.tcp_fastopen = 1
net.ipv4.tcp_mtu_probing = 0
$ ssh rn 'sysctl net.ipv4.tcp_rmem net.ipv4.tcp_wmem net.core.rmem_max net.core.wmem_max'
net.ipv4.tcp_rmem = 4096 131072 6291456
net.ipv4.tcp_wmem = 4096 16384 4194304
net.core.rmem_max = 212992      # 208 KB
net.core.wmem_max = 212992      # 208 KB
```

> BBR 已开 ✓。`net.core.rmem_max/wmem_max` 仅 208 KB，**但** `tcp_rmem/tcp_wmem` 的自动调优上限是 6 MB / 4 MB，内核 4.x+ 默认自动调优会绕过 `core.*_max`，所以**不能据此断言吞吐被 208 KB 卡死** —— 这一点我特意没有写成结论（见 §5-U8）。仍建议把 `core.*_max` 提到与 `tcp_*mem` 同量级，理由是应用一旦显式 `SO_SNDBUF` 就会被 208 KB 截断。

---

## 5. 证据等级与 UNKNOWN

### 5.1 证据等级

| 等级 | 含义 | 本文中的例子 |
|------|------|--------------|
| **A：实测直证** | 本机/外部主机真实往返得到的数据，命令与原始输出已贴 | §4.2 全量表、§4.3 IP:443、§4.4 ECH 受控实验、§4.5 探测对照、§4.6 pin 值校验、TTFB/吞吐 |
| **B：参数直读 + 对照** | 配置逐字段核对，并与官方语义/真站行为做对照 | ALPN 表、证书主体/issuer、凭据复用、sid/密钥复用、`obfs`/`masquerade`/`hop` 缺失、防火墙状态、日志探测统计 |
| **C：本仓库源码级研究（二手但可溯源）** | 基于真实内核源码与官方文档，非本次实测 | mihomo `ws + reality-opts` 静默失效（`kernel-mihomo.md:498`）、mihomo 不支持 AnyTLS+Reality（`:247/:427/:508`）、`trojan/anytls` 只有 `sni` 没有 `servername`（`:232`） |
| **D：生成器自述** | 部署工具自身的注释记录 | `src/client.sh:600-660` 关于 type 65 / fallback-filter 导致 ECH 失效的记录 |

> 凡评分表中的每一格，都能落到上表某一等级；没有"凭感觉"的格子。

### 5.2 UNKNOWN 清单（9 条）

| ID | 未知项 | 为什么不知道 | 需要什么才能知道 |
|----|--------|--------------|------------------|
| U1 | 被动 DPI 对这 32 个组合的**实际分类结果** | 手上没有 DPI/流量分类器，也没用第三方探测服务 | 用 GFW 探测类服务或本地 DPI 引擎（如 nDPI/Zeek + 规则）跑一遍 |
| U2 | ~~hy2 的 `up`/`down` 裸数字语义~~ | **已由本次受控实验解决**：裸数字 == Mbps | — |
| U3 | CC 侧 ISP 是否对 UDP/QUIC 限速或封锁 | 无效 QUIC 报文本就该被丢弃，`sendto` 无响应**不能**推出"被封"；而 hy2/TUIC 实测可用说明至少没被完全封 | 需要能完成真实 QUIC 握手的工具做前后对照，或换多个 ISP 采样 |
| U4 | 这些 IP/端口**当前**的抗封锁状态（是否已被墙） | 本次只从 CC 单点观测，CC 能连不代表其他地区能连 | 多点（多地/多运营商）可用性探测 |
| U5 | 节点侧是否存在 **DNS 泄露** | sing-box `config/` 未配置 `dns` 段、mihomo 服务端配置也无 `dns` 段，服务端不做 DNS 转发；实际解析发生在客户端与应用侧，本次未抓包 | 在客户端侧抓 DNS 出站流量，与 `tun`/`fake-ip` 配置联合验证 |
| U6 | ECH **真的隐藏了 SNI** 吗（线上效果） | 只验证了 ECHConfig 存在与 mihomo 会启用；没抓到线上 ClientHello 看外层 SNI 是否为 `cloudflare-ech.com` | 客户端侧抓包比对有无 ECH 两种情况的 ClientHello |
| U7 | 8 个陈旧分享链接对应的节点**是否曾在别处运行过** | RN 上已无监听，`.fw-ports` 与 `install_info.env` 也只是陈旧账本 | 部署历史/备份比对（`nodes.bak.*`、`backup/`） |
| U8 | `net.core.rmem_max=212992` 是否**真的**限制了吞吐 | TCP 自动调优上限是 6 MB，理论上绕过 208 KB；本次无法把链路噪声与窗口限制分离 | 在受控（低抖动）链路上抓 `ss -ti` 的 `cwnd`/`rwnd` 曲线 |
| U9 | `obfs=salamander` / 端口跳跃的**实际收益** | 未做前后对照实验 | 在同一节点上开/关 obfs 与 hop，比较被识别/被限速的差异 |

> 另外明确**排除在范围外**的一项：CC 上真实生产客户端（`/root/catmi/mihomo-client/`、`/opt/sb-client/`，203 个节点文件）订阅的 `der`/`ds-` 前缀节点指向 **`2001:470:1f04:128:ac83:f2c0:c06b:5759`（非 RN）**，RN 的 IPv6 是 `2001:470:c:cf::/64` 段且无 27852–27865 监听 —— 那是另一台服务器，**不属于本次评估对象**。顺带观察到该 `ds-` 批次存在 `short-id: 80c3898d`（仅 4 字节）等问题，但不在本次结论内。

---

## 6. 附：本次评估用到的命令与产物

- 只读审计：`ss -tlnp/-ulnp`、`nginx -T`、`docker exec nginx nginx -T`、`iptables -S`、`ufw status`、`sysctl`、`openssl x509/s_client`、`dig`、`whois`、`curl --http3-only`
- 临时实验：**全部在 `/tmp/` 内**（RN 侧 `s_client`/`dig`/`curl` 只读探测；CC 侧 `/tmp/qeval/` 跑官方 arm64 客户端）
- 未修改 RN 上任何服务配置、未 push 任何仓库、未改动 CC 上的生产客户端进程（`mihomo-client` 与 `/opt/sb-client` 进程 PID 1364829 / 1444214 全程存活，`ps -o lstart` 显示已连续运行 23 小时以上）
- 评估过程产物（本目录）：`raw/`（配置与分享链接转储）、`evidence/`（实测原始日志与 TSV）、`harness/`（测量脚本与全部客户端配置）
