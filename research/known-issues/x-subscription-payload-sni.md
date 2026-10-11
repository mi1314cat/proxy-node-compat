# X 订阅载荷丢 SNI/ECH —— 载荷与 per-node 产物为什么不一致，以及修法

- 日期：2026-10-10（CC CST 23:30–24:00 / RN PDT 08:30–09:00）
- 起因：`research/e2e/three-servers-three-clients.md` §5-①（3×3 验收里最严重的一条）
- 目标仓库：`/root/deepseek/repos/xray--core`（**只改这一个**；`mihomo--core` / `sing-box-core` 全程只读）
- 真机：`ssh rn`（107.173.154.178：`xrayls` 26.3.27、mihomo v1.19.32、sing-box 1.14.2、`proxy-share-service`）、
  `ssh CC`（192.168.1.178：xbd/Xray 26.3.27 + Client、mihomo 客户端、sb-client）
- 本轮改动：**1 个提交** `55c736a`（`main`，已推送；`git ls-remote origin main` = `55c736afaaab6aafd59f34b7e99d7688ca5087b3`）
- 门禁：`bash tools/check_libs.sh` → **756 通过 / 0 失败**（基线 737/0，新增 19 条断言）
- 证据原始件：`research/known-issues/evidence/`（`x-payload-before-stale.txt`、`x-payload-fix-3clients.log`、
  `x-payload-fix-gate.log`）

---

## 0. 结论一览

| # | 问题 | 结论 | 依据 |
|---|---|---|---|
| ① | 载荷为什么丢 SNI/ECH | **根因是两条**: (a) 载荷是**一次性快照**，服务端代码修好之后没人刷新，线上那条分享继续发老内容；(b) 载荷生成路径**从头到尾没有 ECH 概念** —— 即使重新生成也补不回 `ech=` | §2 |
| ② | 为什么 per-node 产物是对的 | 产物由**协议脚本自己**（`conf/vlessxhttpecn.sh:render_client`）在创建节点时写，字段来自脚本变量，天然有 sni+ech；载荷是**另一份实现**从 `conf/*.json` 重建 | §2.1 |
| ③ | 修法 | 取值同源（`_serverName` 进 SNI 候选 + 新增 ECH 还原）+ **载荷↔产物一致性校验（不一致就拒发并说明差在哪个字段）** + 载荷版本号让"陈旧订阅"可见 | §3 |
| ④ | `vless-xhttp07` 修好 SNI 后仍 503 | **三者都不是**（不是 ECH、不是 CDN、不是节点状态）：503 来自**客户端把 mux.cool 开在 xhttp 出站上**，而 Xray 的 http 入站在上游失败时正好回 **HTTP 503**。同机同配置只差 mux：关 204 / 开 000；该缺陷在 `Client/lib/genconfig.py` 里**已修**（本提交未再动），CC 上部署的客户端仍是旧的 | §5 |
| ⑤ | 三客户端真连（改后） | xbd **5/5**、mihomo **4/5**、sing-box **4/5**（出口全部变成 RN 的 CF 出口 `104.28.195.192`）；改前分别是 2/5、1/5、2/5 | §4 |
| ⑥ | 门禁 | **756 通过 / 0 失败**；反向验证：把**事故当时的真实载荷**喂进校验，恰好拒发坏的 3 条 | §6 |

---

## 1. 现象与判定口径

**判定口径（用户点名）**：CC 直连 `http://www.gstatic.com/generate_204` 本身就是 `204/0.056s`
（本机有拦截/透明代理，出口 = CC 自己的 `107.174.201.250`），所以 **204 不能当成功判据**。
本文所有"真连成功"一律要求 **出口 IP 变成 RN 的 CF 出口 `104.28.x.x`**：

```
CC 直连基线:  gstatic=http 204 / 0.055s   egress=107.174.201.250   ← 假阳性来源
经节点成功:   gstatic=http 204 / 0.37–2.26s   egress=104.28.195.192  ← 真判据
```

**改前/改后载荷原文**（同一批 5 个 tag，`hysteria-04 / SS2022-02 / TROJAN-03 / vless-xhttp07 / vless-xhttp08`）：

```
改前（线上 f64f61ce… 的真实内容，944 B）:
  hysteria2://05615ce2-…@107.173.154.178:29604?sni=107.173.154.178&insecure=0            ← sni 是 IP, 且丢 alpn/带宽
  ss://MjAyMi1ibGFrZTMt…@107.173.154.178:29603#SS2022-02
  trojan://LV7CpzX9Jc8vWuhP0YV0@107.173.154.178:29602?security=reality&type=tcp&sni=audio-ssl.itunes.apple.com&fp=chrome&sid=b860a9f0&pbk=GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU#TROJAN-03
  vless://1fa7c981-…@107.173.154.178:8443?encryption=none&security=tls&type=xhttp&path=%2FaVCR3P0A%2F#vless-xhttp07   ← 无 sni / 无 ech
  vless://278502fc-…@107.173.154.178:29601?encryption=none&security=tls&type=ws&path=%2F8KLD3cNj#vless-xhttp08        ← 无 sni / 无 ech

改后（同一台机器、同一批节点，1472 B）:
  hysteria2://…@107.173.154.178:29604?sni=moontv.6896698.xyz&insecure=0&alpn=h3&up=50&down=200&upmbps=50&downmbps=200
  vless://1fa7c981-…@107.173.154.178:8443?encryption=none&security=tls&type=xhttp&sni=moontv.6896698.xyz&path=%2FaVCR3P0A%2F
  vless://278502fc-…@107.173.154.178:29601?encryption=none&security=tls&type=ws&sni=moontv.6896698.xyz&ech=AGX%2BDQBhACA…&path=%2F8KLD3cNj
```

> `vless-xhttp07` 的 `ech=` **故意不写**：载荷发布的是**直连源站 `107.173.154.178:8443`**，
> 而源站没有 `echServerKeys`（ECH 只在 CDN 边缘那侧有意义）。给源站发 CDN 的 ECH 配置，
> 等于让客户端发一个源站解不开的 ClientHello —— 见 §3.2 的绑定规则。

---

## 2. 根因（代码级）

### 2.1 同一个节点有**两条**生成链接的路径

```
路径 A ── per-node 产物  out/<proto>_share-<NN>.txt        （对）
   conf/vlessxhttpecn.sh : render_client() / rebuild_one()
     CERT_DOMAIN   = extract_cert_domain(证书) 再被片段 _serverName 覆盖
     ECH_SERVER_KEYS = 片段 tlsSettings.echServerKeys
     ech  = direct: `xrayls tls ech -i <keys>` 还原的 ECHConfigList
            cdn   : cloudflare-ech.com+https://dns.alidns.com/dns-query
     端点 = 按 listen 推: 绑回环→nginx / 否则→CDN 域名:443
   —— 字段来自脚本自己的变量，创建时就写好了。

路径 B ── 订阅载荷  base64(多行 URI)                      （错）
   conf/share.sh : share_create / share_refresh_all
     → conf/lib/share_payload.py : build_payload()
       → conf/lib/nodes.py : collect() + build_share_link()
          端点  = out/share/<tag>.json 元数据的 host:port
          sni   = tlsSettings.serverName → 证书 SAN/CN → 证书项 domain
          ech   = ★ 完全没有这个概念（修之前一行都没有）
   —— 从内核片段 + 元数据**重建**，与路径 A 是无共享实现的第二份实现。
```

**用户的症状与这个结构一一对应**：per-node 产物（A）一直是对的，订阅载荷（B）是另一份实现，
它既没有 ECH，SNI 取值也少一条来源（片段的 `_serverName`）。

### 2.2 为什么"SNI 的修复已经在仓库里了，线上却还是坏的"

这是**第二个独立缺陷**，而且正是验收当天踩到的：

- 分享内容**一次性生成、存在 `proxy-share-service` 里**（`content_sha256` 是存下来的快照）。
- `share_refresh_all()` 只在 **① 面板加了节点、② 手工跑 `share.sh refresh`** 时执行；
  **没有任何机制在"生成载荷的代码被修好"之后去刷新已发出的链接**。
- 时间线（可核查）：

| 时刻 (CST) | 事件 | 证据 |
|---|---|---|
| 20:47:04 | 线上那条 X 分享被创建（内容 = 上面"改前"5 条） | `GET /api/v1/shares` → `created_at=1791636424` |
| 22:33:36 | `7bb3d8b` 修好 SNI 取值；22:33:51 `9231b52` 补齐 hy2 `alpn/带宽` | `git log` |
| 23:08–23:28 | 3×3 验收读到的仍是 20:47 的快照 | 验收报告 §3.1 |

所以现象是：**服务端代码已修 + 面板/链接全绿 + 用户手里还是老订阅**。
本轮新增的载荷版本号（§3.4）就是为了让这个窗口**可见**：

```
$ bash conf/share.sh list          # 只读，打的是线上真实记录
  编号  TOKEN               名称            …  状态    内容    节点
  1     f64f61ce35e42b39a5  e2e-allproto    …  active  陈旧!   hysteria-04,SS2022-02,TROJAN-03,vless-xh
  [陈旧] f64f61ce… 的内容是旧版生成器建的 (schema=无, 现为 2) —— 里面可能带着已经修掉的缺陷
         (丢 sni / 丢 ech / sni 写成 IP)。客户端拉到的是老内容，而列表/链接看起来一切正常;
         跑一次 `conf/share.sh refresh` 即可原地重建 (token 与地址不变)。
```

---

## 3. 修法

### 3.1 取值同源（`conf/lib/nodes.py`）

| 改动 | 作用 |
|---|---|
| `extract(inbound, source_file, frag=None)` | 把**片段根**一起读进来 —— `_serverName` / `_clientEncryption` 这类"给人看、内核不认"的字段写在根上 |
| `tls_domains(tls, declared)` | SNI 候选**新增第一条**：片段自带的 `_serverName`（脚本侧本来就是优先用它 —— `rebuild_one()` 里 `_serverName` 覆盖证书域名） |
| `node["declared_server_name"]` / `node["ech_server_keys"]` | 把"这个节点支持 ECH"的来源标记与直连 ECH 密钥带进节点视图 |

### 3.2 ECH 补齐，且**与端点绑定**（`nodes.py`）

```python
ech_config_list(server_keys)   # 2 字节密钥长度 + 密钥 + ECHConfigList → 后半段
ech_param(n, host)             # 有 echServerKeys → 还原出的 ECHConfigList
                               # 没有 + 片段有 _serverName + 本次发布的是域名(CDN 边缘) → CDN-ECH DNS 查询串
                               # 其余 → 不写
```

- `ech_config_list()` **实测与 `xrayls tls ech -i <keys>` 逐字节相同**（RN 生产 `vless-xhttp-08.json`）——
  所以分享层不需要调用 xray 二进制就能写出与脚本产物同一个值。
- **ECH 是端到端绑定的**：客户端发的 ECH 只有"它以为在连的那个服务端"能解开。
  发布源站（IP:端口）时不写 CDN 的 ECH；发布 CDN 边缘（域名:443）时才写。
  这条规则写进了 `ech_param()` 的 docstring，也被闸门锁住。
- 非法/空/长度不一致的 `echServerKeys` **返回空**，不返回半截配置（半截 ECHConfigList 比没有更糟）。
- vless / trojan 的 `tls` 分支与 vmess 都接上了；REALITY 分支不受影响。

### 3.3 一致性校验：载荷 ↔ per-node 产物（新增，`nodes.py` + `share_payload.py`）

```
product_links(out_dir)        扫描 out/*share-*.txt, 按**凭据**建索引
                              （文件名与 tag 没有可靠机械映射: hy2_share-04 ↔ hysteria-04,
                                vless-xhttp_share-07 ↔ vless-xhttp07, ss2022-share-02 ↔ SS2022-02;
                                而且两处命名风格不同 —— 只认 `*_share-*` 会漏掉 ss/trojan/reality）
compare_payload_link(...)     逐字段比对, 返回 ok / endpoint-cdn-vs-origin / mismatch
verify_against_products(...)  返回 (kept, refused, checked, unchecked)
```

**比对规则**（写死在代码注释里，闸门逐条锁）：

| 类别 | 字段 | 不一致时 |
|---|---|---|
| 关键（任一声明就必须相等；**缺也算不一致**） | `security` `type` `sni` `ech` `alpn` `path` `pbk` `sid` `fp` | **拒发**该节点，原因里点名"载荷=… 产物=…"与产物文件名 |
| 提示性 | `spx` `host` `insecure` `mport` `flow` `encryption` | 只在提示里列出 |
| 端点 | `host:port` | 相等 → ok；**唯一允许的差异**是"产物=CDN 域名:443 / 载荷=源站 IP:端口"这一对 → 允许但**每次留痕**；其它情况拒发 |
| 端点绑定 | `ech` | 端点相同 → 严格相等；CDN 对 → 载荷连源站时**必须不写** CDN 的 ECH |
| 显示名 | `#fragment` | **刻意不比**：载荷带旗帜+服务器前缀（naming），产物不带，这是有意的 |

**没有产物可比对 ≠ 不一致**：照常发布，但必须报出 `没有 per-node 产物可比对 (未校验): …`
（否则"少一条防线"会被静默吞掉；闸门专门锁了这条，避免把没有产物的部署搞成"一条都发不出去"）。

载荷里因此多出**第五类**结果 `inconsistent`（与 `refused` 分开报）：
`full=True` 的返回值由 6 元组变 **7 元组**，`share.sh` 的 `x_share_build_payload` 同步更新
（老四元组接口保持不变，闸门锁着）。

### 3.4 让"陈旧订阅"可见（`share_payload.py` + `conf/share.sh`）

- 新增 `PAYLOAD_SCHEMA = 2`；`share_create` 把它写进分享记录的 `meta`。
- `share_refresh_all`：**哈希不同 _或_ schema 不同**就重建（并把 schema 一起写回。
  注意 `proxy-share-service` 的 `--meta` 是**整体替换**不是 merge —— `share_service.py:735`；
  代码里已按"一次 update 带全 name/tags/schema"处理，否则会把刷新用的 tags 抹掉）。
- `share_list`：schema 不一致（或老记录缺该字段）→ 标记 **`陈旧!`** + 一段说明与修复命令。

---

## 4. 验证：真机 3 客户端 × 逐节点（含出口 IP 判据）

**分享地址**：改前 = 线上 `http://107.173.154.178:9443/share/f64f61ce35e42b39a5f928d1c6d15ae5`（未动过）；
改后 = 用**修好的代码**新建的一条临时分享 `…/share/6cf6d8de2339cb0e115aa4edbe57e7c0`（1472 B，
`payload_schema=2`，**测完已 DELETE**，见 §9）。三客户端都从**真实订阅 URL** 拉取。

### 4.1 客户端解析（改前 → 改后）

| 客户端 | 解析结果 | 改前 | 改后 |
|---|---|---|---|
| **xbd**（CC 部署版 `lib/node.py`） | 5 / 5 | hy2 `sni=107.173.154.178`；xhttp07/08 `sni=''`、`ech=''` | 三个都是 `sni=moontv.6896698.xyz`；xhttp08 `ech='AGX+DQBhAAAgACA/rO…'` |
| **mihomo**（provider） | 5 / 5 | 5 个节点（值错，导入数看不出问题 —— 与验收报告一致） | 5 个节点，名字 `🇺🇸 X-…` |
| **sing-box**（`to_sb.py` → 内核） | 5 / 5 | xhttp07/08 的 sni 退化成地址 | sni 正确；**`ech` 仍被转换器整段丢掉**（见 §8-②） |

### 4.2 逐节点真连（出口 IP 必须 = `104.28.x.x`）

| 节点 | xbd / Xray（仓库 HEAD Client/lib） | mihomo | sing-box |
|---|---|---|---|
| `hysteria-04` | ✗000 → **✅204 / 1.48s / 104.28.195.192** | ✗000(5.0s) → **✅204 / 0.93s / CF** | ✗000 → **✅204 / 0.71s / CF** |
| `SS2022-02` | ✅204/0.49s/CF → ✅204/0.37s/CF | ✅204/0.42s/CF → ✅204/1.06s/CF | ✅204/0.37s/CF → ✅204/0.36s/CF |
| `TROJAN-03` | ✅204/1.67s/CF → ✅204/0.85s/CF | ✗000 → ✗000（**mihomo 侧既有缺陷**，见下） | ✅204/0.84s/CF → ✅204/0.70s/CF |
| `vless-xhttp07` | ✗000 → **✅204 / 1.31s / CF** | ✗000(5.0s) → **✅204 / 2.26s / CF** | ✗000 → ✗000（**客户端丢 xhttp 传输**，见 §8-②） |
| `vless-xhttp08` | ✗000 → **✅204 / 1.27s / CF** | ✗000(5.0s) → **✅204 / 1.41s / CF** | ✗000 → **✅204 / 0.73s / CF** |
| **合计** | **2/5 → 5/5** | **1/5 → 4/5** | **2/5 → 4/5** |

- `mihomo` 的 `TROJAN-03` 改前改后都 000，与仓库已有记录一致
  （`278089d`：mihomo 的 trojan 链接解析器丢 reality），**不是本轮引入、也不在 X 侧**。
- `xbd` 一列用的是**仓库 HEAD 的 `Client/lib`**（CC 上部署的是旧构建，见 §5）；
  它写出的出站全部是 `nomux`（`mux_decision` 生效），这正是 xhttp07 从 000 变 204 的原因。
- 三家的"改后"成功**全部**满足出口 IP = `104.28.195.192`（RN 的 CF 出口），不是 CC 直连兜底。

### 4.3 反向验证：把事故载荷喂进校验

用**线上那条真实的老载荷**（`sni=IP` / 无 sni / 无 ech）跑新的校验器：

```
checked = [hysteria-04, SS2022-02, TROJAN-03, vless-xhttp07, vless-xhttp08]
KEPT = 2   REFUSED = 3
  [拒发] hysteria-04   —— sni: 载荷=107.173.154.178 产物=moontv.6896698.xyz; alpn: 载荷=缺 产物=有 (h3)
  [拒发] vless-xhttp07 —— sni: 载荷=缺 产物=有 (moontv.6896698.xyz)
  [拒发] vless-xhttp08 —— sni: 载荷=缺 产物=有 (moontv.6896698.xyz); ech: 载荷=缺 产物=有 (AGX+DQBhACA…)
```

**恰好拒发验收报告里实测连不通的那 3 条，留下能用的 2 条** —— 闸门与现象一一对应。
而把**同一批节点用修好的代码重建**（改后载荷）喂进去：`5 条通过, 0 条被拒发`。

---

## 5. `vless-xhttp07` "修正 SNI 后仍 503" 的结论

**不是 ECH、不是 CDN 路径、也不是节点坏了。是客户端把 `mux.cool` 开在了 xhttp 出站上。**

同机同配置（CC，Xray 26.3.27，直连源站 `107.173.154.178:8443`，`sni=moontv.6896698.xyz`，路径 `/aVCR3P0A/`），
**只差 mux 一个字段**：

| 变体 | socks 出口 | HTTP 入站 | 出口 IP |
|---|---|---|---|
| mux 关 | **204 / 0.98s** | 204 | **104.28.195.192** |
| **mux 开**（`{enabled:true, concurrency:8}`） | 000 | **503** | — |
| mux 开（去掉 http 入站，只看 socks） | 000 | — | — |
| 对照：同一份 mux 关配置、路径未 URL 解码（`%2FaVCR3P0A%2F`） | 000 | — | — |

**503 就是 Xray 自己的 http 入站在"上游连不通"时回的状态码** —— 这解释了验收报告里
为什么 hy2、xhttp08、xhttp07 三个不同故障都显示 `http=503`（那一格用的是 HTTP 代理入口）。

补齐其余旁证：

- 直连源站（不经 mux）用真客户端实测：`A-origin-noech` → **204 / 0.79s / 104.28.195.192**；
  `stream-one` 模式 → 204。源站对 `GET /aVCR3P0A/` 裸请求回 **400**（Xray xhttp 服务端特征头 `x-padding` 可见），
  错路径回 404、未解码的 `%2FaVCR3P0A%2F` 回 404 ⇒ **节点本身完全正常**。
- 用**部署版** xbd 的 `genconfig.py` 生成配置（它**无条件**写 `mux:{enabled:true}`）：
  sni 改对之前 **000**、改对之后**仍然 000** —— 与验收报告"修好 SNI 后 xhttp07 仍 503"逐字对应。
- 换**仓库 HEAD** 的 `Client/lib/genconfig.py`（`mux_decision()` 对 xhttp/quic/mkcp 硬拒 mux）：
  同一节点 **204 / 1.31s / 104.28.195.192**。
  这条修复早就落地了（`ead7e3c` "fix(客户端): mux.cool 默认给每个出站开、节点里的 mux:false 被吞、
  XHTTP 也照开 (P0-1)"，实现见该文件 65–104 行的说明与"实测 mux 关 204 / mux 开 000"），
  **CC 上部署的客户端是旧构建**（`genconfig.py e3c2bdaf…` ← 部署 / `73df2cca…` ← 仓库 HEAD），
  不是服务端问题，也不是本轮新增的缺陷。

**与另一路核查对齐（CDN/443 那条是另一回事）**：per-node 产物写的是 `moontv.6896698.xyz:443`
（CDN 边缘），而源站 `:443` 是 **nginx 托管的 LunaTV 站点**，不是这个节点：

```
源站 :443 → nginx  → 307 location: /login?redirect=%2F      （LunaTV 未登录跳转）
源站 :8443 → xrayls → 400（xhttp 服务端对裸 GET 的正常应答）
nginx -T | grep -c aVCR3P0A  →  0                            （节点的 nginx 片段从未贴进站点）
Cloudflare 边缘 https://moontv.6896698.xyz/aVCR3P0A/ → 308 location: /aVCR3P0A（尾斜杠被 CF 规则改写）
```

即：**产物指的 CDN 端点确实是死的（缺 nginx 映射，与本次 503 无关）**，而**载荷指的直连源站是活的**。
两者是两条独立结论，本轮把载荷侧修好并让它每次都为这条端点差异留痕
（`端点不同: 产物 moontv.6896698.xyz:443 / 载荷 107.173.154.178:8443 —— 按既有规则允许 (CDN 边缘 ↔ 直连源站)`）。

---

## 6. 门禁

```
bash tools/check_libs.sh   →   ═══ 结果: 756 通过, 0 失败 ═══
```

- 基线 **737 / 0**（**本轮实测**：`git archive cf810be` 到干净目录后跑门禁 → `737 通过, 0 失败`）。
- 改动后 **756 / 0**，新增 **19 条**断言，组成新组 `载荷 ↔ per-node 产物一致性 + ECH 同源`：

| 断言 | 守什么 |
|---|---|
| `echServerKeys → ECHConfigList（与 xray tls ech -i 逐字节相同）` | 用 RN 生产真值对（184 字符 keys → `AGX+DQBhACA…`） |
| `坏/空 echServerKeys 不猜值` | 空/非法 base64/长度不符 → 空，不给半截配置 |
| `TLS 节点链接带上 sni（片段 _serverName 参与取值）` | SNI 取值同源 |
| `直连 ECH 节点链接带上 ech（与产物同值）` / `与产物一致的节点不被误拒` / `校验结果有报出` | ECH 补齐且不误伤 |
| `发布 CDN 边缘时写 CDN-ECH` / `发布源站时不写 CDN 的 ECH` / `端点差异被留痕` | ECH 与端点绑定 |
| `丢 sni/ech 的载荷被拒发（正是事故形态）` / `正确的那条照常发布` / `拒发原因点出字段名` / `sni 被写成 IP 时也被拒` | **反向验证**：拒发必须精确、必须说话 |
| `连字符命名的产物也参与校验` / `下划线命名的产物参与校验` | 命名风格差异不许静默漏一半节点（`ss2022-share-02.txt`） |
| `没有产物时照常发布` / `没有产物可比对这件事被报出来` | 不许把"没法校验"变成"拒发"或"静默通过" |
| `旧版生成器建的分享被标成陈旧` / `当前版本的分享不被误标` | 陈旧判定既不漏也不恒真 |
| `full=7`（老四元组 `four=4` 不变） | 接口兼容 |

反向验证（把断言打在修复前的代码上）在开发过程中真实发生过：本轮**未提交的中间态**曾让门禁变红，
逐条修掉之后归零 —— 过程见 §7。

---

## 7. 仓库状态与协作

**本轮改动的文件清单（4 个，全部属于本任务）**：

| 文件 | 改动 | 说明 |
|---|---|---|
| `conf/lib/nodes.py` | +336 | `_serverName` 进 SNI 候选；`ech_config_list()` / `ech_param()`；一致性校验（`product_links` / `compare_payload_link` / `verify_against_products`） |
| `conf/lib/share_payload.py` | +46 | 新增 `OUT_DIR` / `PAYLOAD_SCHEMA`；接入一致性校验；`full=True` 6 元组 → 7 元组（第五类 `inconsistent`） |
| `conf/share.sh` | +115 | `XRAY_OUT_DIR`；分类报出"载荷与产物不一致, 已拒发"；`payload_schema` 写进分享 meta；refresh 按 schema 重建；list 标"陈旧!" |
| `tools/check_libs.sh` | +225 | 新组 19 条断言；`full=6` → `full=7`（接口确实变了，断言跟着改，**没有削弱任何原有断言**） |

**HEAD 与提交**：本轮基于 `cf810be`（`main`）；提交 `55c736a` 已推送 →
`git ls-remote origin main` = `55c736afaaab6aafd59f34b7e99d7688ca5087b3`。
`git status` 在提交后干净；`git status --porcelain -uall` 只有这 4 个文件。

**门禁数值变化过程（真实记录，不是一路全绿）**：

| 次序 | 数值 | 原因 |
|---|---|---|
| 1 | **737 / 0** | 改动前基线（`git archive cf810be` 干净树实测） |
| 2 | **733 / 4**（含并发读到我编辑中的中间态） | 3 条 fragment 断言 + `full=6` 接口断言。前者是**真 bug**：`verify_against_products` 把"没有产物可比对"的节点 **drop 掉**了，会让"没有 per-node 产物的部署一条都发不出去" —— 已改为"保留发布 + 记账报出" |
| 3 | **752 / 4**（另一 agent 观测到的中间态） | 4 条全在新 ECH 组 |
| 4 | **751 / 5** | 修好上述 bug 后暴露 5 条真问题：3 条是**测试常量被截断**（`ECH_KEYS` 183 字符，base64 非法 → `ech_config_list` 正确地返回空，是断言的数据错、不是实现错，已用 RN 的 184 字符真值替换并加了长度校验）；1 条是 `ech_config_list("AAAA")` 返回 `AA==` —— 实现该更严（长度前缀不自洽就返回空），**改的是实现不是断言**；1 条是门禁自检报我新写的 `grep -q … | sed` 早退管道，改成 `grep … >/dev/null` |
| 5 | **756 / 0** | 收口（提交后同一棵树复跑一致） |

**协作**：同一棵工作树上另有 agent（three-way-interop）在做"服务端声明内核 + 客户端选载荷"。
对方做了**非破坏性快照**（`git stash create` → `wip/xray-ech-uncommitted` @`91bd831`，
补丁 `/tmp/xray-wip/ech-work-20261010-234855.patch`），**没有回退我的文件**；
我提交时按内容精确 stage 了上述 4 个文件，未夹带任何其它新文件。

---

## 8. UNKNOWN（没验证到的一律不写结论）

1. **mihomo 是否真的采纳 `ech=`**：改后 xhttp08 带 `ech=` 且连得通，但它改前失败的原因是 SNI（不是 ECH），
   所以 ECH 的**增量效果**在 mihomo 侧没有被单独隔离出来（缺"有 ech/无 ech"的负控实验）。
   需要一份 mihomo 的 vless URI 解析器源码级确认。
2. **sing-box 客户端把 `xhttp` 传输与 `ech` 都丢了**（本次实测）：
   `/opt/sb-client/share-state/to_sb.py`（属于 `sing-box-core`，**本轮只读**）产出的 outbound 里
   `vless-xhttp07` **没有 `transport` 字段**（→ 内核按裸 TCP+VLESS 说话，报 `unknown version: 72`），
   `ech` 字段也从不写。所以**本轮补的 ECH 对 sing-box 客户端暂时无效**：它在链路更下游被丢掉。
   若要覆盖，需要在 `sing-box-core` 侧修转换器（不在本任务边界内）。
3. **`xbd` 已发布的构建里有没有 `mux_decision`**：我只验证了**仓库 HEAD 的 `Client/lib`** 能连上
   （xhttp07 204）。CC 上部署的 `xbd` 仍是旧构建（`genconfig.py e3c2bdaf…`），
   发布物与仓库 HEAD 的对应关系未查（与验收报告 UNKNOWN-6 同一条）。
4. **`hy2` 的 `up/down` 是否降速生效**：沿用上一轮结论（服务端决定拥塞控制，观察不到），未复测。
5. **线上那条 `f64f61ce…` 分享仍是老内容**：本轮**没有**替任何人执行 `share.sh refresh`
   （它会写 `proxy-share-service` 的运行时数据）。这是**待办**不是未知：
   修好的代码跑一次 refresh 即会原地重建（token/URL 不变），list 现在也会标"陈旧!"。

---

## 9. 纪律执行记录（可核查）

- **只改 `xray--core`**：`mihomo--core` / `sing-box-core` 全程只读（`to_sb.py` / mihomo 二进制只被读取与执行）。
- **没有写任何生产配置**：RN 的 `/root/catmi/xray/conf/*`、`out/*`、`out/share/*`、nginx 配置、
  CC 的 `/root/catmi/mihomo-client/conf`、`/opt/xray-browser-dialer/*`、`/opt/sb-client/*` 全部只读。
  唯一的写是 `proxy-share-service` **自有的分享记录目录**（其运行时数据）：
  新建 **1 条临时分享** `6cf6d8de…` 用于三客户端拉取，**测完已 DELETE** →
  `provider=xray` 回到 **1 条**（只剩原有的 `f64f61ce…`，内容未被改动）。
- **没有重启任何生产服务**：RN 的 `xrayls` / `mihomo` / `sing-box` / `proxy-share-service`、
  CC 的三个客户端进程全程未重启（收尾复查仍在跑：CC `xray` PID 968528、`mihomo` PID 1364829、
  `sing-box` PID 1444214，与验收报告一致；RN `xrayls` active）。
- **实验一律在 `/tmp` 且已清理**：RN `/tmp/xsubfix`（已删）、CC `/tmp/xver`、`/tmp/xh07`、`/tmp/xsub`
  与全部临时 xray/mihomo/sing-box 进程（PID 1260221/1260222/1260223/1261262/1261263/1264235/1264244/
  1264490/1264491/1264492）已 kill，端口已释放，本地 `/tmp/live-payload.txt` 等只进证据目录。
- **推送凭据一次性使用**：未落盘（无 `~/.git-credentials`、无 `credential.helper`、
  `.git/config` 里无 token），无需 `shred` 的文件。
