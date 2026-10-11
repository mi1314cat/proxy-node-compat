# 三家互通 · SB(sing-box) 侧实施与真机验收报告

> 日期：2026-10-10/11 ｜ 实施对象：`sing-box-core`（服务端 `src/conf/` + 客户端 `src/client/`）
> 设计依据：`docs/three-way-interop.md`（X 侧同一份规范）｜ 参照实现：`xray--core` 分支
> `feat/three-way-interop`（`conf/lib/interop.py` / `conf/lib/native.py` / `Client/lib/interop.py`，
> **只读**）
> 真机：RN（SB 服务端真实部署 `/root/catmi/sing-box`，分享走 9443 `proxy-share-service`）
> ＋ CC（xbd / mihomo / sb-client 三个客户端）
> 提交：`sing-box-core` 本地 commit（**未 push**，见 §12）

---

## 0. 一句话结论

SB 服务端现在也在**它自己生成的订阅地址**上声明「我是 sing-box 的哪个发行版、我提供哪些
格式、每种格式从哪取」，并**同时产出两条产品**：主产品 = **URI 列表**（普通话，谁都能读）、
附带产品 = **原生 sing-box JSON**（只有同内核同发行版的客户端读）。真机三格全部按设计走：

| 格 | 改前（`research/e2e/three-servers-three-clients.md` §3.3） | 改后（本报告 §4–§6） |
|---|---|---|
| **SB→xbd** | `✗ 订阅里没有解析出节点`（**0 导入**） | 决策行 `本次拉取: 普通话 URI 列表 —— 服务端内核 sing-box ≠ 本机 xray`；解析 **8** / 导入 **6**（13 条链接）；**逐节点真连 6/6 = `204` + 出口 `104.28.201.80`** |
| **SB→mihomo** | provider **0 节点**：`file must have a 'proxies' field` | 真 mihomo file provider 加载 **11 节点**（13 行链接；`naive+https` / `shadowtls` 是 mihomo 自己的解析器不认）；真连 **8/11** = `204` + 出口 `104.28.201.80`（3 条失败的逐条原因见 §5.3） |
| **SB→SB** | 13 节点 + check 通过 + 真连 | **一字未退**：13 节点 + check 通过 + **逐节点真连 13/13**（`204` + `104.28.201.80`）；原生正文与改前**逐字节相同**（sha256 `3c3e63c4…`） |

---

## 1. 服务端实现了什么（文件清单）

| 文件 | 内容 |
|---|---|
| `src/conf/interop.py`（新，权威 428 行） | 声明构建 / 解析 / 决策 + 本机内核事实**真探测**（`sing-box version` 首词）。字段名、决策规则、reason code 与 X 侧 `interop.py` **逐条相同**（同一份规范只允许一套语义），只把自探测从 `xray version` 换成 `sing-box version` |
| `src/client/lib/interop.py`（新，vendored） | 与上面**逐字节相同**（`sha256 0d173763…`，门禁 F1 断言）|
| `src/conf/share.sh`（改） | 创建时两条记录（主=**普通话 URI 列表** / 附带=**原生 sing-box JSON**）+ 地址上带声明；发布前四道闸门（节点集合一致 / **链接校验** / URI 表达力标注 / 与真实配置一致）；列表打印**带声明的地址**；刷新按 `role` 分派；停用/撤销/改次数/重建 token **成对**生效 |
| `src/conf/link_guard.py`（新） | **链接校验的唯一真源**（5 条"整条订阅归零"规则 + `scheme ↔ 出站类型` 一致性）：`tools/check_share_links.sh` 与发布闸门共用同一份规则 |
| `src/conf/uri_express.py`（新） | **URI 表达力标注**：注册表 `uri_rules` 驱动（不另写表），报损失 / 由其它 feature 承载 / **UNKNOWN** / 取件地址不一致 |
| `src/client/client.sh`（改） | `add` 前读声明 → 同内核同发行版走**原生**，其余走**普通话**；原生取件失败**回退**并把原因打出来；`本次拉取: …` 一行让用户一眼看出这次拉的是哪种 |
| `install.sh`（改） | 客户端安装补 `share-state/lib/interop.py`（缺了的表现是**静默全走普通话**） |
| `tools/interop-e2e.sh`（新） | 端到端验证台：真 `share.sh create` + 真分享服务代码（独立实例/端口/数据目录）+ 真 `client.sh add`；合成语料与**真实部署只读拷贝**两种模式 |
| `tools/check_share_links.sh`（改） | 新增 **F 段 15 条**断言（声明/决策矩阵/片段不算声明/发布闸门接线）+ **E5**（真实分享地址上决策必须可见）；校验器改为调用 `link_guard.py`（规则不再写两份） |
| `tools/check_compat_wiring.sh`（改） | 新增 **6 条**接线断言（认 `SB_INTEROP_PY` / 决策日志 / 回退链 / install 装 interop.py / 两份实现逐字节相同 / share.sh 产出声明）|

**声明长这样**（RN 真机创建时打印，实测）：

```
http://107.173.154.178:9443/share/26ef50d255161001f7fa68213ca0555d
  ?interop=1&kernel=sing-box&distribution=sing-box&version=1.14.2
  &formats=uri%2Csing-box
  &url-sing-box=http%3A%2F%2F107.173.154.178%3A9443%2Fshare%2Fd4617c7e85d5699c6eadecb89d56161b
```

> **格式名为什么是 `sing-box` 而不是任务书里写的 `singbox`**：设计文档 §2 规定
> `formats` 里的非 `uri` 项是**发行版标签**（不是"格式名"），客户端规则才退化成一句
> `我的发行版标签 ∈ formats`（少一张映射表就少一处漂移）。本机事实真探测取
> `sing-box version` 首行首词 = `sing-box`，所以声明是 `formats=uri,sing-box` /
> `url-sing-box=`。写成 `url-singbox` 就必须再引入一套"标签 → 格式名"的映射，
> 那正是设计文档明确否掉的东西。跨内核客户端**不看**这个键（它们只看 `kernel`）。

---

## 2. 真机环境与复现锚点

| 项 | 值 |
|---|---|
| SB 服务端版本 | `sing-box version 1.14.2`（`/root/catmi/sing-box/sing-box`）|
| SB 节点数（生产） | 13（anytls×2 / hysteria2 / naive / vless(reality) / ss / shadowtls / trojan×2 / tuic / vless-CDN / vmess-CDN / vmess-REALITY）|
| 公共分享服务 | `proxy-share-service 1.1.0`，RN `:9443`，`provider=sing-box` |
| 客户端 | CC：`xbd`（X 客户端，`xray--core` 分支 `feat/three-way-interop` 只读部署到 `/tmp`）、`mihomo Meta v1.19.32`、`sb-client`（仓库版 `client.sh`，`/opt/sb-client/core/sing-box`）|
| 测试分享 | 主 token `26ef50d2…` / 原生 token `d4617c7e…`（**测后已删**，见 §13）|
| 原生正文 sha256 | `3c3e63c4ed07237ef563a03ab5e822904a68290da52f697614fb28474840de2a`（= 生产 `out/sb_client-all.json`）|
| 普通话正文 sha256 | `33501a90eded99d0f2e3f9509fd0ae82abe0a7c4fdbb5eb89bee789fdb73e208`（13 行 URI）|

---

## 3. SB→xbd：跨内核 → 拉 URI（真机）

```
$ xbd node sub "<带声明的地址>" sb
==> 下载订阅
本次拉取: 普通话 URI 列表 —— 服务端内核 sing-box ≠ 本机 xray     ← 决策可见
✓ 解析出 8 个节点
✓ 已导入 6 个节点，归入分组「sb」(6 个)
```

* **改前**：同一份内容（sing-box JSON）→ `✗ 订阅里没有解析出节点`（3x3 报告 §3.3①）。
* **导入数为什么是 6**（逐条可解释，不是"少了几个"）：
  * 13 条链接里 **xbd 的解析器认 8 条**；认不出的 5 条：`anytls×2` / `naive+https` / `shadowtls` / `tuic`（X 客户端 `node.py` 没有这几个 scheme 的解析器）。
  * 认出的 8 条里被 compat 拦下 2 条，**理由都打印了**：
    `["🇺🇸 rn trojan02-REALITY", "节点参数不完整，不是内核不支持 trojan（trojan 是内核原生支持的协议）：REALITY × 传输 —— REALITY 不支持 websocket"]`、
    `["🇺🇸 rn vmess02-REALITY", "Xray 内核不支持该节点（vmess）"]`（vmess+REALITY 不在 Xray 支持范围）。
* **逐节点真连**（X 客户端自己的 `lib/genconfig.py` + `bin/xray`，每节点一个隔离实例，独立 socks 端口）：

| 节点 | generate_204 | 出口 IP |
|---|---|---|
| rn-hysteria201-tls | 204 | 104.28.201.80 |
| rn-reality01-reality | 204 | 104.28.201.80 |
| rn-shadowsocks01-plain | 204 | 104.28.201.80 |
| rn-trojan01-tls-cdn | 204 | 104.28.201.80 |
| rn-vless01-tls-cdn | 204 | 104.28.201.80 |
| rn-vmess01-tls-cdn | 204 | 104.28.201.80 |

  **6 通过 / 0 未通过**（`204` **且**出口 `104.28.x.x`；CC 直连本身就 `204`，所以 204 不单独计成功）。

* 声明缺失（裸地址）时 xbd 也照常工作：`本次拉取: 普通话 URI 列表 —— 地址上没有内核声明`
  （导入数是 0 只是因为同一批节点已经导入过、被去重）。

---

## 4. SB→mihomo：真 mihomo 用 file provider 读 URI 列表（真机）

CC 上真 `mihomo Meta v1.19.32`，**file provider** 指向"带声明地址"拉到的那份 URI 列表：

```
拉到的 URI 列表: 13 行 / 2879 字节（sha256 33501a90eded99d0）
provider 节点数: 11
```

| 结果 | 节点 | http | 出口 |
|---|---|---|---|
| ✅ | 🇺🇸 rn anytls01-TLS | 204 | 104.28.201.80 |
| ❌ | 🇺🇸 rn anytls02-REALITY | 000 | — |
| ✅ | 🇺🇸 rn hysteria201-TLS | 204 | 104.28.201.80 |
| ✅ | 🇺🇸 rn reality01-REALITY | 204 | 104.28.201.80 |
| ✅ | 🇺🇸 rn shadowsocks01-plain | 204 | 104.28.201.80 |
| ✅ | 🇺🇸 rn trojan01-TLS-CDN | 204 | 104.28.201.80 |
| ❌ | 🇺🇸 rn trojan02-REALITY | 000 | — |
| ✅ | 🇺🇸 rn tuic01-TLS | 204 | 104.28.201.80 |
| ✅ | 🇺🇸 rn vless01-TLS-CDN | 204 | 104.28.201.80 |
| ✅ | 🇺🇸 rn vmess01-TLS-CDN | 204 | 104.28.201.80 |
| ❌ | 🇺🇸 rn vmess02-REALITY | 000 | — |

**8 通过 / 3 未通过**。三条失败的**归因**（都不是"内容坏"，而是消费端解析器）：

* `trojan02-REALITY`：mihomo 日志 `connect error: unexpected status: 301 Moved Permanently`
  —— 这正是注册表里已入册的 `uri.trojan.reality@mihomo`（**mihomo 的 trojan 链接解析器不读
  `pbk`/`sid`**，于是按裸 TLS 拨号，握手被 REALITY 服务端转给 fallback 站）。发布时这条损失
  **被逐条标注**（见 §5.1）。
* `anytls02-REALITY`、`vmess02-REALITY`：mihomo 的 `anytls` / `vmess` 链接解析器同样不读
  REALITY 参数 → 超时。注册表**没有**这两行 → 本报告的标注把它们记进
  `[UNKNOWN] 原生有、URI 侧查不到且注册表没这一行`（**不折算成"没损失"**）。
* provider 只装进 **11/13**：`naive+https://` 与 `shadowtls://` 是 mihomo 自己的解析器不认的
  scheme（实测：只放这两条时 mihomo 直接
  `initial proxy provider error: yaml: unmarshal errors … convert v2ray subscribe error: format invalid`
  → **0 节点**；混在全量列表里则**静默跳过**、debug 级日志一行都不打）。
  → "URI 是普通话"不等于"每个客户端都认得每个 scheme"；**这条差异必须在产品上说出来**，
  不能假装 13 条人人可读（本报告 §5.2 已按此写）。

---

## 5. 不静默：URI 表达力损失与"两条产品不一致"都打出来

### 5.1 发布时的标注（真机原文，13 节点）

```
[标注] URI 表达力标注: 逐节点查过 13 个; 损失 3 条; UNKNOWN 8 项 (注册表 uri_rules 逐节点查; UNKNOWN 不折算成'没损失')
[注意] URI 路径表达力损失 3 条（原生路径没有这些损失）:
  · rn-trojan02-REALITY  standard:reality  只能表达一部分  [uri.trojan.reality@mihomo] （仅 mihomo 的链接解析实现）mihomo 的 trojan 分支解析器不读 pbk → 拿不到公钥
  · …（同上 sid / 裸 TLS 拨号两条）
[UNKNOWN] scheme 没入册, 表达力判不了: naive+https, shadowtls
[UNKNOWN] 原生有、URI 侧查不到且注册表没这一行（UNKNOWN, 不猜）: standard:mux, standard:naive, standard:shadowsocks, standard:tls, standard:transport.tcp
[注意] rn-trojan01-TLS-CDN: 取件地址不一致 —— 原生=107.173.154.178:443 / 链接=hxicc.catmicos.dpdns.org:443（陈旧产物…）
[注意] rn-vless01-TLS-CDN: 同上      [注意] rn-vmess01-TLS-CDN: 同上
```

* 标注真源是 vendored 注册表 `proxy_node_compat/data/rules.json` 的 `uri_rules` +
  `docs/uri-representation.md`；`uri_express.py` 只做"出站 ↔ URI"映射与查表，
  **没有第二张表**。出站映射用的是客户端同一份 `compat2.profile_from_sb_outbound`。
* `standard:tls ← standard:reality` 那条被记为"由其它 feature 承载"（注册表 `uri.vless.reality`
  = `FULL`，链接装得下）——**唯一一条**有据可依的蕴含关系，写死在 `uri_express.py` 并注明出处。
* **UNKNOWN 照原样报出来**，不折算成"没有损失"。

### 5.2 两条产品发布的节点集合必须一致（发布闸门）

`share.sh` 发布前逐项检查，任何一条不过就**拒绝发布**（不许发一份少节点的订阅）：

| 闸门 | 不通过时 |
|---|---|
| URI 产品能不能建出来（每个非控制型 outbound 都要有对应 `sb_share-<tag>.txt`） | 拒绝 + 点名节点 |
| **链接本身**（`link_guard.py`：hy2 obfs / alpn、vmess 格式与 `#片段`、sni 是 IP、`scheme ↔ 出站类型`） | 拒绝 + 点名节点与规则 |
| URI 表达力标注跑不起来 | 拒绝（"没标注"= 静默发布） |
| 与真实配置一致（原有 `sb_share_consistency_check`） | 拒绝 |

**这条闸门在真机上抓到了东西**：RN 部署里 3 条陈旧的 vmess/shadowtls 链接先是让创建直接
**失败**（`[FAIL] vmess01-TLS-CDN: vmess 链接带了 #片段` / `JSON 缺 ps 字段` /
`vmess02-REALITY: vless 链接的 encryption='aes-128-gcm' 非法` / `链接 scheme=vless 与节点类型
vmess 不符`），修好之后（§5.4）才发得出去。—— 也就是说：**"发出去 = 已经过了链接校验"**。

### 5.3 消费者差异实测表（同一份 13 行 URI 列表）

| 消费方 | 能解析/装载 | 逐条原因 |
|---|---|---|
| **xbd**（X 客户端解析器） | 8 条 → 导入 6 条 | 认不出 `anytls×2 / naive+https / shadowtls / tuic`；compat 再拦 `trojan+ws+REALITY`、`vmess+REALITY` |
| **SB 客户端**（`to_sb.py`） | 9 条 | 认不出 `anytls×2 / naive+https / shadowtls` |
| **mihomo 1.19.32** | 11 条（静默跳过 2） | 不认 `naive+https / shadowtls` |
| **SB 原生 JSON** | **13 条**（同内核路径） | —— |

> 这张表就是"URI 是普通话，但普通话也有方言"的实测版；每一行的差异都能在发布标注或
> 客户端日志里找到对应的一句话（§5.1 / §4）。

### 5.4 两处**陈旧产物**（改前就坏，本次修好并验证）

改前 RN 的 `out/sb_share-vmess0*.txt` 是**旧生成器**留下的：

| 产物 | 改前（陈旧） | 问题 | 改后 |
|---|---|---|---|
| `sb_share-vmess01-TLS-CDN.txt` | `vmess://<base64>` + `#🇺🇸 rn vmess01-TLS-CDN` 片段，payload **缺 `ps`/`id`/`v`/`scy`/`type`** | mihomo：`error:url.Port() is empty` → 该条（及整表在只含坏行时）**0 节点** | 按 `src/conf/vmess.sh:253-270` 当前模板重建（`ps`/`id`/`scy`/`type` 齐全、**不带片段**） |
| `sb_share-vmess02-REALITY.txt` | `vless://…?encryption=aes-128-gcm&security=reality…`（**协议名错**） | mihomo：`invaild vless encryption value: aes-128-gcm` → **整条订阅 0 节点** | 重建为 `vmess://base64(JSON)`（`tls:"reality"` + `pbk`/`sid`/`fp`），与 §5.5 的原生产物逐字段一致 |

* 两个文件与 `sb_links-all.txt` 里对应两行已修（RN 授权配置；改动前内容见上表左列，
  可用 `src/conf/vmess.sh` 的模板重算）。
* 修好后的证据链：`link_guard` 通过 → `to_sb.py` 转换回来与**原生产物逐字段一致**
  （仅差 URI 本就装不下的 `User-Agent` / `utls fingerprint`）→ mihomo provider 从 **0 节点**
  变成 **11 节点**、`vmess01` 真连 `204/104.28.201.80` → xbd 从 `✗ 解析不出节点` 变成
  导入 6 条（含 `vmess01-TLS-CDN` 真连 204）。
* **未修、只标注**的一类：3 个 CDN 节点的**原生 JSON** 里 `server` 是 `107.173.154.178:443`
  （陈旧；从 CC 实测 `https://107.173.154.178:443` → `000`），而链接是
  `hxicc.catmicos.dpdns.org:443`（Cloudflare，实测 `200`）。**链接那侧是对的**。
  这类差异在发布时逐条打 `取件地址不一致`（§5.1），本次**不改产物**（不许偷偷改），
  要修得重建这 3 个节点的 CDN 产物。

---

## 6. SB→SB：零退步（逐字节 + 逐节点 + 门禁）

1. **正文逐字节相同**：原生记录的 `sha256 = 3c3e63c4ed07237ef563a03ab5e822904a68290da52f697614fb28474840de2a`
   == 改前作为分享正文的那个文件 `out/sb_client-all.json` 的 sha256
   （改前 `_sb_share_content_file` 就是 `cp -f` 该文件 → 同一串字节）。
   e2e 里也有这条断言（"原生正文与 `sb_client-all.json` 逐字节相同"）。
2. **决策走原生**：真客户端日志 `本次拉取: 原生 sing-box JSON —— 同内核同发行版 (sing-box/sing-box) → 取原生`；
   `✓ 已导入 13 个节点`；`sing-box check` 通过。
3. **逐节点真连 13/13**（每节点一个隔离实例，独立 mixed 端口）：

```
anytls01-TLS 204 / anytls02-REALITY 204 / hysteria201-TLS 204 / naive01-TLS 204 /
reality01-REALITY 204 / shadowsocks01-plain 204 / shadowtls01-TLS 204 /
trojan01-TLS-CDN 204 / trojan02-REALITY 204 / tuic01-TLS 204 /
vless01-TLS-CDN 204 / vmess01-TLS-CDN 204 / vmess02-REALITY 204     出口全 = 104.28.201.80
```

4. **门禁 E 段（真分享地址、真客户端、真连）**：

```
[OK] E1: client.sh add 导入 13 个节点 (非 0), exit=0
[OK] E5: 带声明的地址 → 客户端走原生（日志里有'本次拉取: 原生'）
[OK] E2: 导入后的客户端配置 sing-box check 通过
[OK] E3: 真连 http=204|0.487212 (走节点, 端口 63741)
[OK] E4: 生产 sb-client MainPID 未变 (1444214) —— 隔离生效, 未碰生产
```

> **E 段必须跑在"客户端能 `check` 这份配置"的机器上**：RN 的二进制是**服务端**构建，
> 对含 `naive` 出站的配置直接 `FATAL initialize outbound[3]: cronet: library not found`
> → 客户端按设计走转换器分支 → 非交互时前缀提问读不到输入 → 中止。CC 的客户端构建没有
> 这个问题（E1/E2/E3 全绿）。这是**环境/二进制能力**差异，不是本次改动引入的（改前同样如此）。

---

## 7. 声明缺失 / 原生 404 → 回退普通话（真机原文）

```
# 裸地址（声明缺失）
[SB-Client] 本次拉取: 普通话 URI 列表 —— 地址上没有内核声明
[OK]   识别为 share-uri 格式, 转换出 9 个节点        ← 不报错
# 声明在、原生 404
[SB-Client] 本次拉取: 普通话 URI 列表 —— 同内核同发行版 (sing-box/sing-box) → 取原生；
        原生取件失败(http://107.173.154.178:9443/share/9999…, HTTP 404) → 回退
[OK]   识别为 share-uri 格式, 转换出 9 个节点
```

**声明对第三方客户端可证惰性**：同一 token 带声明 / 裸地址返回**逐字节相同**
（e2e 实测 `sha256 33501a90eded99d0f2e3f9509fd0ae82abe0a7c4fdbb5eb89bee789fdb73e208`；
另用一份 `kernel=xray` 的声明再测一次，同样相同）。公共服务路由先剥查询串
（`share_service.py:768`），带声明的地址对任何客户端零影响。

---

## 8. 门禁（真实值）

| 门禁 | 基线 | 本次 | 说明 |
|---|---|---|---|
| `tools/check_compat_wiring.sh`（本机） | **22 / 0** | **28 / 0** | +6 条三家互通接线断言（含两份 `interop.py` 逐字节相同）|
| `tools/check_share_links.sh`（本机，无 `--share-url`） | 全部通过（A 5 / D 3，E 跳过） | **全部通过** | 新增 F 段 **15/15**；校验器改走 `link_guard.py`（规则只有一份）|
| `tools/check_share_links.sh`（CC，真客户端 + 真分享地址） | —— | **43 OK / 0 FAIL**（`结果: [OK] 全部通过`） | A 5 / D 3 / **F 15** / **E 5**（E1 13 节点、E5 原生、E2 check、E3 204、E4 生产 PID 未变）/ B 14 个真实产物文件全部通过 |
| `tools/interop-e2e.sh`（合成语料，本机） | 新增 | **27 / 0** | 声明 / 两条产品 / 逐字节相同 / 标注 / 决策 / 回退 / 跨内核 / 成对生命周期 |
| `tools/interop-e2e.sh`（**真实部署只读拷贝**，CC） | 新增 | **27 / 0** | 同一份验证台直接吃 RN 的 `config/`+`out/`+`share-state/` |

---

## 9. UNKNOWN（没证据就不猜）

| # | 事项 | 为什么没结论 |
|---|---|---|
| S1 | 第三方客户端（v2rayN / Shadowrocket / 机场面板）对 `naive+https://` / `shadowtls://` 这两条的处理 | 本环境只有 xbd / mihomo / sb-client 三家；mihomo 实测跳过、SB 转换器实测不支持、xbd 解析器不认 —— 其余客户端未验 |
| S2 | `anytls+REALITY` / `vmess+REALITY` 经 URI 的损失**该不该入册** | 实测 mihomo 读不出（超时），但注册表里只有 `uri.trojan.reality@mihomo` 一行；按纪律**不自己加行**（那要 compat 侧的证据与决策） |
| S3 | 3 个 CDN 节点原生 JSON 的陈旧 `IP:443` 是"哪一次地址族切换改的" | 只证明了现象与影响（从 CC 实测 IP:443 不通、域名:443 通 200）；没有产物生成时间线 |
| S4 | 同内核**不同发行版**（fork）之间原生产物能否无损互读 | 与 X 侧 U2 同一个 UNKNOWN，本次没有新证据 → 规则仍保守走 URI |
| S5 | M 侧服务端声明实现 | 本次只改 SB；M 的服务端声明落地后才能验"M→SB/SB→M 的声明口径" |
| S6 | 非交互场景下客户端"前缀提问读不到输入就中止" | 面板交互路径不受影响；cron/脚本路径需要 `SB_SUBS_PREFIX`（既有约定），本次未改 |
| S7 | 原生产物的**运行期**可用性是否对每个协议都等价 | 13/13 节点真连已验（本报告 §6.3），但没有对每个协议的**每条可选字段**做端到端 |

---

## 10. 复现方式

```bash
# 1) 门禁（不需要内核二进制）
bash tools/check_compat_wiring.sh          # 28 通过 / 0 失败
bash tools/check_share_links.sh            # 含 F 段 15 条

# 2) 端到端验证台（合成语料; 独立服务实例/端口/数据目录, 只写 /tmp）
SB_E2E_CLIENT_BIN=/path/to/sing-box bash tools/interop-e2e.sh

# 3) 拿真实部署的片段跑（只读拷贝, 仍是独立服务实例）
SB_E2E_CORPUS=/root/catmi/sing-box SB_E2E_CLIENT_BIN=/root/catmi/sing-box/sing-box \
  bash tools/interop-e2e.sh

# 4) 真实分享地址上的对角线（E 段）
bash tools/check_share_links.sh --share-url "<带声明的地址>" \
     --client-bin /path/to/sing-box --out-dir /root/catmi/sing-box/out

# 5) 单点调试
python3 src/conf/interop.py self
python3 src/conf/interop.py decide '<订阅地址>'
python3 src/conf/link_guard.py check <链接文件> --label 标签
python3 src/conf/uri_express.py report out/sb_client-all.json --links-dir out
```

---

## 11. 本地 commit

`sing-box-core` 提交见本报告发布时的 commit（**未 push** —— 用户规矩：验证干净再推）。
改动文件：`src/conf/{interop,uri_express,link_guard}.py`（新）、`src/client/lib/interop.py`（新）、
`src/conf/share.sh`、`src/client/client.sh`、`install.sh`、`tools/{check_share_links,check_compat_wiring}.sh`、
`tools/interop-e2e.sh`（新）。

---

## 12. 纪律记录（可核查）

* **只改 `sing-box-core`**；X / M 仓库**只读**（X 的客户端是 `git archive` 到 CC `/tmp` 下跑的，
  仓库本身一字未动）。本报告写在 `proxy-node-compat/research/`。
* **未重启任何生产服务**：RN 的 `sing-box` / `xrayls` / `mihomo` / `proxy-share-service`、
  CC 的 `xray` / `mihomo` / `sb-client` 全程未重启（CC 生产 `sb-client` MainPID `1444214`
  在 E4 里被断言未变；客户端侧真连一律用 `/tmp` 下的隔离实例+空闲端口）。
* **未写生产配置**；除**已授权的 RN 配置**下那次陈旧产物修复（2 个链接文件 + `sb_links-all.txt`
  两行，§5.4）之外没有动 `/root/catmi/*`。分享记录（`provider=sing-box`）测后删除 →
  回到 0 条；`xray` / `mihomo` 记录未动。
* **实验目录已清理**：RN 与 CC 的 `/tmp/vfy*`、`/tmp/tw-sb`、`/tmp/fixvm`、`/tmp/mtest`、
  `/tmp/sb-repair-*`、本机 `/tmp/rncorpus*`、`/tmp/sb-e2e-*`、`/tmp/sbbin` 等已删；
  隔离实例全部结束（未留残留进程）。
* **未 push**。
```
