# X 内核三个未结项收口：hy2 产物自读 / TROJAN-03 经 mihomo / xhttp-07 经 CDN 307

- 日期：2026-10-10
- 目标仓库：`/root/deepseek/repos/xray--core`（**只改这一个**；`mihomo--core` / `sing-box-core` 全程只读）
- 真机：`ssh rn`（107.173.154.178，Xray 26.3.27 = `d2758a0`，mihomo **v1.19.32** 生产实例 pid 未动）、
  `ssh CC`（192.168.1.178，Xray 26.3.27 arm64 = `d2758a0`）
- 上一轮遗留清单：`research/known-issues/x-hy2-params-client-side.md` UNKNOWN 1（hy2 JSON 导入）、
  `research/known-issues/x-share-sni-and-pin.md` UNKNOWN 3（xhttp-07 CDN 307）与 UNKNOWN 4（TROJAN-03 mihomo 000）
- 本机内核源码：`/tmp/xsrc/xray` tag **`v260327.0` = `d2758a0 v26.3.27`**（与 RN/CC 二进制同提交）；
  mihomo 源码 `/tmp/xsrc/mihomo` tag **`v1.19.32`**（与 RN 上二进制同版本）

---

## 0 · 结论一览

| # | 问题 | 根因 | 修了没有 | commit |
|---|---|---|---|---|
| 1 | `parse_xray_json` 报"没有可识别的出站" | 白名单只有 `"hysteria2"`，内核与本脚本写的是 **`"hysteria"`**；且 hysteria 出站的 `settings` 是**扁平**的、带宽在 `finalmask.quicParams` | ✅ 修（含带宽/跳跃/pin 四处静默丢弃 + 内核下限防线） | `99c11ec` |
| 2 | TROJAN-03 经 mihomo 恒 **000** | **mihomo 侧**：trojan 的**分享链接解析器**不读 `security/pbk/sid` → `reality-opts` 永远缺失 → 只按**裸 TLS** 拨号。引擎本身支持（YAML 显式写 → 204） | ⛔ X 侧不可修（链接是标准格式，别家都能用）；已入册 compat 逐内核规则 + 保留 YAML 兜底 | `278089d` |
| 3 | xhttp-07 经 CDN 边缘 **307** | **与 CDN/边缘无关**：源站 443 上的 LunaTV/MoonTV 应用发的 307（未登录跳转）；443 上**没有** `/aVCR3P0A/` 的 location 映射，生成出来的 nginx 片段从未被贴进站点；CF 回源端口 = 443 而不是 8443 | 📄 只写方案（生产 nginx/CDN 配置未执行） | — |

门禁：**683 → 718（任务 1，+35）→ 735（任务 2，+17）→ 737（两组"生成器不静默跳过"兜底 +2），失败 0**。
反向验证：把新门禁打在本轮修复**前**的树上 → **691 通过 / 42 失败**，全部落在两组新断言里（见 §5）。

---

## 1 · `parse_xray_json` 认不出 `protocol:"hysteria"`

### 1.1 现象（真机原话，改前）

把 RN 上**脚本自己生成的**产物喂给自己的客户端：

```
$ ssh rn cat /root/catmi/xray/out/hy2_client-04.xray.json
{ "outbounds": [ { "tag": "hy2-04",
    "protocol": "hysteria",
    "settings": { "version": 2, "address": "107.173.154.178", "port": 29604 },
    "streamSettings": { "network": "hysteria", "security": "tls",
      "tlsSettings": { "serverName": "moontv.6896698.xyz", "alpn": ["h3"] },
      "hysteriaSettings": { "version": 2, "auth": "05615ce2-…",
                            "up": "50mbps", "down": "200mbps" } } } ] }

$ python3 Client/lib/node.py parse "$(cat 上面那份)"        # 改前
解析失败: Xray 配置里没有可识别的出站
```

RN 上现存的 `hy2_client-02/03/04.xray.json` 三份**全是这个形态**（即上一轮修复**之前**的世代）。

### 1.2 两个世代都要认

| 世代 | 来源 | 带宽在哪 | 端口跳跃 | pin |
|---|---|---|---|---|
| 旧（RN 上现存 02/03/04） | `conf/hysteria2.sh` 上一轮修复前 | `hysteriaSettings.up/down`（内核**静默丢弃**的位置） | 无 | 自签档在 `tlsSettings.pinnedPeerCertSha256` |
| 新（脚本现在写的） | `conf/hysteria2.sh` 512 行起 | `finalmask.quicParams.brutalUp/brutalDown` | `finalmask.quicParams.udpHop.ports` | 同上 |

### 1.3 改了什么（`Client/lib/node.py` / `Client/lib/genconfig.py`）

| 位置 | 改动 |
|---|---|
| `parse_xray_json` 白名单 | 加 `"hysteria"`（保留 `"hysteria2"`）；模型里统一记成 `hysteria2`，`transport=quic`（与 `parse_hysteria2` 同一个模型），原始写法留在 `transport_raw="hysteria"` 备查 |
| `parse_xray_json` 分支 | hysteria 出站按**扁平** `settings.address/port` 读（走 `servers[]` 分支会得到 **空地址 + 443** —— "解析成功"但连到不存在的节点）；`auth` 从 `streamSettings.hysteriaSettings.auth` 读 |
| 带宽 | **权威 = `finalmask.quicParams.brutalUp/brutalDown`**；逐字段回退到旧位置 `hysteriaSettings.up/down`，并把来源写进新字段 `bandwidth_source`（`finalmask` / `hysteriaSettings` / `mixed` / 空），回退时在 stderr 说明"内核 26.3.27 会静默丢弃这个位置" |
| 端口跳跃 | `finalmask.quicParams.udpHop.ports`（回退 `hysteriaSettings.udphop.ports`），过 `port_hop_range` 合法性校验 |
| pin | `tlsSettings.pinnedPeerCertSha256` —— **原来整个函数都不读它**（自签节点唯一的信任来源，导入即失败）。这一处在共享的 TLS 块里，所以非 hysteria 产物同样受益 |
| 新增 `bandwidth_xray(v)` | 按**内核**语义解释 Xray JSON 的 `Bandwidth`：数字 + 可选数量级(k/m/g/t, 1024 进制) + 可选 b/bps，**缺数量级 = bit/s**（`Bps()` 最后 `/8`）。与链接侧的 `bandwidth_hint`（裸数字 = Mbps）严格分开 |
| `genconfig._bandwidth_value` | 补**下限**检查：算出来 < 65536 B/s 一律不写并说明；支持 `"N bps"` 写法（`bandwidth_xray` 对 bit/s 形态的规范输出） |

**内核侧语法（本轮逐字读 `/tmp/xsrc/xray/infra/conf/transport_internet.go:462-501`）**：

```go
func (b Bandwidth) Bps() (uint64, error) {
    ... 数字前缀 + 单位后缀
    switch unit {
    case "", "b", "bps":            mul = Byte        // = 1
    case "k", "kb", "kbps":         mul = Kilobyte    // 1024
    case "m", "mb", "mbps":         mul = Megabyte    // 1024²
    ...
    }
    return uint64(val*float64(mul)) / 8, nil
}
```

⇒ `"50"` = 6 B/s，`"50 mbps"` = 6553600 B/s；`brutalUp/brutalDown` 另有
`>= 65536 B/s` 硬下限（上一轮实测：写小了内核**拒收整份配置**）。
所以"低于下限的值"在**导入侧**和**生成侧**都必须丢掉 —— 搬进去不是"限速不生效"，
是"整份配置起不来"。

### 1.4 验证（三条独立证据）

**① RN 上三份真产物全部解析出节点，带宽不丢**

```
$ for f in hy2_client-02/03/04.xray.json; do python3 Client/lib/node.py parse "$(cat $f)"; done
hy2_client-02  hysteria2 107.173.154.178:40784 auth=edd0b25c 50 mbps 200 mbps hysteriaSettings
hy2_client-03  hysteria2 107.173.154.178:31879 auth=02f17c46 50 mbps 200 mbps hysteriaSettings
hy2_client-04  hysteria2 107.173.154.178:29604 auth=05615ce2 50 mbps 200 mbps hysteriaSettings
```

（`bandwidth_source=hysteriaSettings` 如实标明"这是旧位置的回退值"；把同一份产物改成
`finalmask` 形态 → `bandwidth_source=finalmask`，且两个位置冲突时 finalmask 胜。）

**② 真内核 `xray run -test`：两代产物生成的配置都是 `Configuration OK`**

用的是与生产同提交的 `Xray 26.3.27 d2758a0`：

```
旧世代产物 → node → genconfig:  finalmask={brutalUp:"50 mbps",brutalDown:"200 mbps"}
                                  Configuration OK.   (rc=0)
新世代(自签+跳跃)  →              finalmask={...,udpHop:{ports:"30000-31000"}}
                                  tlsSettings={serverName,alpn,pinnedPeerCertSha256:"694e89c0…"}
                                  Configuration OK.   (rc=0)
```

**③ CC 真机端到端（经 RN 生产 hy2 节点 29604）**

| 目标 | 结果 |
|---|---|
| `https://www.gstatic.com/generate_204` | **204 / 1.85s** |
| `https://cp.cloudflare.com/` | **204 / 0.79s** |
| `https://www.cloudflare.com/cdn-cgi/trace` | **200 / 0.93s** |
| trace 出口 | `ip=104.28.195.192 loc=US`（RN 的 CF 出口，不是 CC 本地） |

CC 上 `xray run -test -c cfg04.json` → `Configuration OK`；配置与日志只落 `/tmp/xh2`，已删。

### 1.5 回归断言（门禁新增 35 条，组名 `Xray JSON 导入: 自己生成的 hy2 客户端产物能被自己读回`）

两组产物 JSON **逐字抄自真机**（旧世代抄 `hy2_client-04`，新世代抄 `hysteria2.sh` 现在写的形态），
断言覆盖：白名单/扁平 address+port/auth/sni/alpn/transport、旧位置带宽回退且标注来源、
新位置带宽+udpHop+pin、**finalmask 优先于旧位置**（权威性）、`"800000"`（bit/s）能原样往返、
`"40000"`（< 65536 B/s）被丢弃、认不出的单位不猜、没写带宽不编默认值、
白名单没放宽成"什么都收"、非 hysteria 产物的 pin 也读到；
有内核时再加两条：真机产物生成的配置 `-test` 通过 + 低于下限的带宽被跳过（配置照样起得来）。

---

## 2 · TROJAN-03 经 mihomo 恒 000 —— 根因：mihomo 的 trojan **链接解析器**丢 reality

### 2.1 现象与链接

```
trojan://LV7CpzX9Jc8vWuhP0YV0@107.173.154.178:29602?security=reality&type=tcp
        &sni=audio-ssl.itunes.apple.com&fp=chrome&sid=b860a9f0
        &pbk=GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU#TROJAN-03
```
参数**齐的**（上一轮已确认）；同一个节点用 Xray 客户端直连 **204 可用**；经 mihomo **000**（修复前后一致）。

### 2.2 源码定位（不是猜）

| 位置（`/tmp/xsrc/mihomo`，tag v1.19.32） | 事实 |
|---|---|
| `common/convert/converter.go:161-220` | `case "trojan"` 里读了 name/server/port/password/udp/skip-cert-verify/sni/alpn/network/ws/grpc/**fp**/**pcs** —— **全文不出现** `security` / `pbk` / `sid` / `reality` |
| 与 upstream `Meta` 分支 `common/convert/converter.go` 同段逐字 `diff` | **完全相同**（729 行版本）⇒ 不是"本地版本旧"，当前分支也没修 |
| `common/convert/v.go:46-56`（vless/vmess 走这个） | `if realityPublicKey := query.Get("pbk"); … { proxy["reality-opts"] = … }` ← **vless/vmess 读，trojan 不读** |
| `adapter/outbound/trojan.go:64 / :325 / :170,382` | `TrojanOption.RealityOpts` 存在且被 `Parse()` 并用于 TLS 配置 ⇒ **引擎支持 trojan+REALITY**，缺的只是"链接 → 配置"这一跳 |

### 2.3 回环对照实验（RN 本机，目标 `127.0.0.1:29602`，排除网络路径）

用 RN 上的**生产 mihomo 二进制**（`Mihomo Meta v1.19.32 linux amd64`）跑独立实例（`-d /tmp/mh2`，
端口 1150x/1950x），每组取 `/group/G/delay` + socks5 实连：

| 用例 | 配置形态 | delay 端点 | curl | mihomo 日志 |
|---|---|---|---|---|
| **A1** | 已发布链接（公网 IP）经 provider | `all proxies timeout` | **000** | **没有任何 REALITY 行**，只有 `use specified fingerprint:Chrome` |
| **A2** | 同一条链接，只把地址换成 `127.0.0.1` | `all proxies timeout` | **000** | 同上（⇒ 与网络路径无关） |
| **B** | 同节点 YAML **显式 `reality-opts`** | `{"T3":95}` | **204** | `REALITY localAddr: 127.0.0.1:29602 …` / `REALITY Authentication: true, AEAD: *gcm.GCM` |
| **C** | B **去掉 `reality-opts`**（= URI 解析器产出的形状） | `all proxies timeout` | **000** | 无 REALITY 行（与 A 同一种失败） |
| **D** | **vless**+REALITY 走**同一条 URI 通道**（provider） | `all proxies timeout` | 000（该服务端要 VLESS-Encryption，与本结论无关） | **`REALITY Authentication: true`** ← 证明"URI → reality"通道本身可用，差别只在解析器读不读 `pbk/sid` |

D 的关键价值：同一条 URI 通道、同一个 mihomo，vless 链接**进了 REALITY 握手**，trojan 链接
**连 REALITY 都没进** —— 与源码里两个分支的差异逐字对上。
C 的关键价值：把"URI 解析器产出的配置"单独拿出来，失败模式与 A 完全一致
⇒ 000 的成因就是**缺 reality-opts**，而不是密码/SNI/端口没读到。

### 2.4 结论与 X 侧处置

- **根因**：mihomo 侧限制（trojan 分享链接解析器不读 `pbk/sid`，`reality-opts` 永远缺失）。
  **不是**链接参数问题（Xray/sing-box 用同一条链接都正常），**不是**服务端问题（YAML 形态 204）。
- **X 侧不能通过改链接修**：`trojan://…?security=reality&pbk=…&sid=…` 是生态通用格式，
  改成别的写法会破坏 Xray/sing-box/v2rayN 这些能读它的客户端。
- **已有的兜底本来就是对的**：X 自己的 mihomo YAML 产物 `out/trojan-client-03.yaml` 逐字带

  ```yaml
  reality-opts:
    public-key: GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU
    short-id: b860a9f0
  ```
  （文件头注释甚至写着"mihomo trojan 的 SNI 字段是 sni（不是 servername），reality-opts 需配公钥"）
  ⇒ 对 mihomo 目标**发 YAML，不发链接**。

### 2.5 compat 能力规则怎么反映它（本轮已落地 + 建议数据行）

原来 compat 的"URI 表达力"表只有一层（链接**格式**装不装得下），而这里是第二层：
**某个内核的链接解析实现读不读**。本轮在 `xray--core` 的 vendored 引擎里加了逐内核维度：

1. `registry.uri_rule(scheme, feature, kernel=None)`：带 `target_kernel` 的行**只**对该内核返回；
   别的内核既不放行、也不拿它当回退；不给 kernel 时忽略它（不猜）。全局行仍是回退（旧调用形式行为不变）。
2. `engine._apply_uri_rules(..., target)`：按 `target.kernel` 取规则。
3. 数据行（`Client/lib/proxy_node_compat/data/rules.json`，**第一行带 `target_kernel` 的 uri_rule**）：

   ```json
   {
     "uri_rule_id": "uri.trojan.reality@mihomo",
     "scheme": "trojan", "feature": "standard:reality", "target_kernel": "mihomo",
     "representation": "NONE",
     "loss": [
       {"field": "standard:reality.public_key", "what": "mihomo 的 trojan 分支解析器不读 pbk → 拿不到公钥"},
       {"field": "standard:reality.short_id",   "what": "同上不读 sid → 拿不到 shortId"},
       {"field": "standard:reality.server_names","what": "sni 读得到, 但没有 reality-opts 时只按**裸 TLS** 拨号: 握手完成(REALITY 服务端把未认证客户端转发给目标站), 流量却进了 fallback → 必然连不通, 且错误信息与\"节点挂了\"无从区分"}
     ],
     "workaround": "改用 mihomo YAML 形态(reality-opts 显式写) —— 本项目 out/trojan-client-*.yaml 产物本来就是对的(逐字带 public-key/short-id)",
     "note": "trojan:// 链接**本身**能表达 reality(vless/sing-box/Xray 都读); 表达不出的是 mihomo 的 URI 解析实现 → 这一行必须按内核分叉, 不能进全局 uri_rules(否则会把 Xray/sing-box 判错)。",
     "evidence": ["e-mihomo-trojan-uri-reality"]
   }
   ```
4. 证据行 `e-mihomo-trojan-uri-reality`（type=BEHAVIOR、confidence=HIGH，how 里写全四个对照用例与源码位置，
   limits 写"只测 v1.19.32 + 当前 Meta 分支；vmess+reality 的 URI 路径未测"）。

实测这条规则的效果（引擎直接调用）：

```
kernel=xray   26.3.27 + 该链接 → status SUPPORTED,             uri 层 UNKNOWN,        losses 0
kernel=mihomo 1.19.32 + 该链接 → status SUPPORTED_WITH_LOSS,   uri 层 SUPPORTED_WITH_LOSS, losses 3
```

⚠️ **canonical 数据不在这一个仓库**：`rules.json` / 引擎的权威副本在
`/root/deepseek/repos/proxy-node-compat/proxy_node_compat/`（本轮边界外，未改）。
两处现在**内容不一致**（vendored 版 27 条证据 / 13 条 uri_rules；canonical 版 26 / 12）。
**需要把本次的三处改动同步过去**：`uri_rules` 那一行 + `evidence` 那一行 +
`registry.uri_rule` 的 `target_kernel` 支持 + `engine._apply_uri_rules` 的签名/取规则方式。
（`xray--core` 里 `compat2.py` 恒以 `kernel="xray"` 判定，所以这颗 mihomo 行在 X 自己的流程里是惰性的 ——
它的价值在共享注册表与"M/SB 侧读到同一份事实"。）

### 2.6 回归断言（门禁新增 17 条）

组名 `跨内核 compat: mihomo 的 trojan 链接解析器丢 reality (逐内核规则不外溢)`：
行的形状（target_kernel/representation/loss/workaround/证据可解析）、
mihomo 判定 → uri 层 `SUPPORTED_WITH_LOSS` 且损失条目指向该规则、
**xray 判定不受波及**（uri 层不是 SUPPORTED_WITH_LOSS、损失表里没有这颗规则、总判定仍 SUPPORTED）、
不给 kernel 取不到逐内核行、给了才取到、全局行（`uri.ss.reality`）仍是回退、
`target_kernel` 取值集合受控、旧调用形式向后兼容。

---

## 3 · xhttp-07 经 CDN 边缘 307 —— 与 CDN 无关，是**源站 443 上的应用**发的

（本节由子代理在 RN 上实测完成；所有写入只落 `/tmp`，已删；**生产路径零写入**。）

### 3.1 复现与对照

```
$ curl -s -o /dev/null -D - https://moontv.6896698.xyz/aVCR3P0A/
HTTP/2 308   location: /aVCR3P0A                    server: cloudflare  cf-ray: a486…-SJC
$ curl -s -o /dev/null -D - https://moontv.6896698.xyz/aVCR3P0A      # 无尾斜杠
HTTP/2 307   location: /login?redirect=%2FaVCR3P0A  server: cloudflare  cf-ray: a486…-SJC

真 Xray 26.3.27 客户端逐字报错:
transport/internet/splithttp: bad status code:307 Temporary Redirect
（xhttp 实际上传路径是 /aVCR3P0A/<uuid>/0，被应用当未登录路由 → 307，不是 308）
```

| 路径 | status | 关键 header | 判定 |
|---|---|---|---|
| 经 CDN `moontv:443` | 308 / 307 | `server: cloudflare`,`cf-ray` | 边缘透传 |
| 直连源站 nginx `:443`（`--resolve` 绕过 CF） | 308 / 307 | **`server: nginx`**，location 逐字相同 | **与经 CDN 完全一致 ⇒ 排除 CF Redirect Rule / Always-Use-HTTPS** |
| 直连源站 `127.0.0.1:8074`（绕过 nginx） | 308 / 307 | 同 location | **307 是应用发的**，不是 nginx 的 return/rewrite |
| 直连源站 Xray `:8443`（curl） | 400 | `x-padding: …`, `access-control-allow-origin: *` | 请求到得了 xhttp 入站 |
| 直连 `:8443` 真 Xray 客户端 | — | 隧道通 `ip=104.28.195.192 loc=US` | **8443 入站健康** |
| 经 CDN 真 Xray 客户端 | — | `bad status code:307` | 复现 |
| **直连源站 `:443` 真 Xray 客户端** | — | `bad status code:307` | **绕过 CF 仍复现 ⇒ 彻底排除边缘** |

源站 access.log：经 CF 的请求 peer = CF IP（`104.22.20.57`）且落在 `:443`
⇒ **CF 回源端口 = 443，不是 8443**。

### 3.2 307 的确切来源

- 443 的 vhost：`location / { proxy_pass http://backend_aqpDJaXb; }` → `127.0.0.1:8074`
  = docker `moontv-core`（LunaTV / Next.js）的鉴权中间件 → 未登录 → `307 /login?redirect=…`。
- 443 由 **docker 容器 `nginx:alpine`**（host 网络，pid 1833，配置 `/home/web/conf.d/`）提供，
  **不是** host nginx（host nginx 只听 8787，`nginx -T` 里没有 443/moontv 块）。
- 同一个 vhost 里 `/vA6c34fXpY8LER/`→31722、`/GwDaTZcFKRQgyjY/`→45630、`/13xhr79tl54LnFBp`→52341、
  `/eew7XngrxBUHc4`→12588 都有映射，**唯独 8443/xhttp-07 缺失**：
  `grep -r aVCR3P0A /home/web/conf.d/` = **NOT FOUND**；`cdn_bindings.tsv` 里也没有 xhttp-07/moontv 行。
- 项目生成器**已经产出**了片段 `out/vless-xhttp_nginx-07.conf`，但从未贴进站点
  （`conf/vlessxhttpecn.sh:593-620 render_nginx_conf` 的设计就是"生成片段供复制"，没有自动应用）。

⇒ **这不是分享链接生成的问题，也不是 CDN 的问题，是"回源到 8443"这一步在源站从未落地。**

### 3.3 修法（**只写方案，未执行**）

**A（推荐，走项目自己的设计）** 把已生成的片段贴进容器 nginx
`/home/web/conf.d/moontv.6896698.xyz.conf` 的 `server{}` 内：

```nginx
location /aVCR3P0A/ {
    proxy_ssl_server_name on;
    proxy_pass https://127.0.0.1:8443;
    proxy_http_version 1.1;
    proxy_request_buffering off;  proxy_buffering off;
    proxy_set_header Host $host;
    proxy_connect_timeout 30s; proxy_send_timeout 300s; proxy_read_timeout 300s;
}
```
再 `docker exec nginx nginx -t && docker exec nginx nginx -s reload`。
已在 `/tmp` 起的**隔离 nginx（18443/18444）**上验证：edge 侧 `http2 on;`
（生产已有，`/home/web/nginx.conf:48`）下，最小 4 行片段与增强片段**都能建起完整隧道**
（`ip=104.28.195.192`）。

**B（备选）** CF Origin Rule 把 `moontv.6896698.xyz` 的回源端口 rewrite 到 8443 ——
前提已验证：8443 公网可达（本地/CC 直连均得 Xray 400）。

**C（顺带，独立的一处陈旧产物）** `out/vless-xhttp_client-07.json` / `-08.json` 里
`pinnedPeerCertSha256=48165d74…ff955` **正是源站证书**的 SHA256 指纹，
经 CF 时边缘出示 CF 证书 → 永远对不上（就是上一轮从分享层移掉的那个 pin）。
**代码侧已经修好**（`conf/lib/cert.sh` 的 `x_cert_client_pin` 在"TLS 不在本节点终结"时返回空，
门禁有函数级 + **产物级**两条断言："CDN-ECH + 公网 CA 证书 → 客户端 JSON 里没有 pin"）；
这两份 JSON 是 **10-10 05:25/05:29** 生成的，而那处修复的 commit 是 **10-10 22:33**
⇒ **产物陈旧，重新生成即可，不是新缺陷**。

---

## 4 · 边界与清理

- 只改 `xray--core`；`mihomo--core` / `sing-box-core` 全程只读（读的是本机源码快照 `/tmp/xsrc/*`，不是这两个仓库）。
- **没有写任何生产路径**：本机只在仓库工作树 + `/tmp/xh1`、`/tmp/xh2`；
  RN 只在 `/tmp/mh2`（已 `rm -rf`）、`/tmp/mh_t3*.sh`、`/tmp/mh_ctl_vless.sh`（已删）；
  CC 只在 `/tmp/xh2`（已删）。RN 的 `/root/catmi/*` 与 CC 的 `/opt/*` 全程只读
  （`cat`/`grep`/`ls`/`python3 -c json.load`）。
- 有 `mkdir` 的项目脚本（`conf/hysteria2.sh`、`conf/lib/cert.sh` 等）**没有被 source/执行**；
  `hysteria2.sh` 的新形态产物是照源码逐字在 `/tmp` 重建的（不是跑脚本生成的）。
- 跑完复查：RN `xrayls` / `mihomo` / `sing-box` / `nginx` 全 `active`（mihomo 生产 pid 119320 未动，
  `/root/catmi/mihomo/conf` 未被触碰）；CC `xray-client` `active`；RN/CC 上的测试实例已全部退出
  （`ps` 只剩生产实例）。
- 未重启任何服务、未改任何 systemd 单元。

## 5 · 门禁

| 运行 | 通过 | 失败 |
|---|---|---|
| 本轮起点（`568c8f7`） | **683** | **0** |
| 任务 1 后（含 +35 条） | **718** | **0** |
| 任务 2 后（+17 条） | **735** | **0** |
| 兜底加固后（+2 条"生成器有输出"）= 最终 | **737** | **0** |

**反向验证**（`git archive 568c8f7` 干净树 + 本轮新 `check_libs.sh`）：**691 通过 / 42 失败**，
42 条**全部**落在本轮新增的两组里，逐条指向真实缺陷：

| 组 | 修复前 | 逐条证据 |
|---|---|---|
| `Xray JSON 导入: …能被自己读回` | 0 通过 / **34 失败** | 生成器直接抛 `ValueError: Xray 配置里没有可识别的出站`（就是 §1.1 那个现象），每条断言给出 `得到 '' , 期望 'hysteria2' / '107.173.154.178' / '29604' / '50 mbps' …` |
| `跨内核 compat: …逐内核规则不外溢` | 14 通过 / **8 失败** | 行不存在 5 条（`uri.trojan.reality@mihomo` 及其 target_kernel/representation/loss/workaround）＋ mihomo 判定 3 条（修复前 `status=SUPPORTED_WITH_WARNING`，uri 层不是 `SUPPORTED_WITH_LOSS`，损失表里没有这颗规则）。**xray 侧那 3 条在修复前也是通的** ⇒ 反向验证同时证明了"这颗逐内核规则不会把 Xray 判错"在改动前后都成立 |

加固原因（自查发现）：两组断言都靠一个 python 生成器取值，生成器一崩，
task-1 组会退化成"全部拿到 `<无>`"，compat 组（旧写法把 `OK/NO` 攒到最后一次性打印）会
**一条都不算、表面全绿** —— 正是本仓库之前吃过的"检查根本没跑却全绿"。
现在：compat 生成器逐条即时打印 + bash 侧"生成器有输出"兜底；task-1 组加"产出合法 JSON"兜底。

## 6 · UNKNOWN

1. **mihomo 未来版本**是否补上 trojan 链接的 `pbk/sid` —— 未验证（只核了 v1.19.32 与当前 `Meta` 分支源码，
   两者该段逐字相同；`limits` 已写进证据行）。
2. **vmess+REALITY 走 URI** 在 mihomo 上未测（`vmess` 在 converter 里也不走 `handleVShareLink`，
   但这轮没做实验，不写结论）。
3. 用例 D（vless+REALITY 经 URI）**没能拿到 204**：该服务端要求 VLESS-Encryption
   （`mlkem768x25519plus…`），而 mihomo 的 vless URI 分支不读 `encryption`/`flow`
   —— 这是**另一条**（未入册的）mihomo URI 表达力缺口，本轮只把它当作"REALITY 通道可用"的证据。
4. 任务 3 里"直连 8443 = 204"未复现：curl（GET/POST 带 `x_padding`）都是 **400 + `X-Padding`**，
   只有真实 xhttp 客户端才建得起隧道（隧道本身通）。上一轮那条 204 的口径属于 UNKNOWN。
5. CF 面板的具体设置**无凭据不可读**："回源 443"是由源站 access.log 里 CF peer IP + 443 命中推出的。
6. 方案 A/B 应用后的**真实 CF 全链路**未验证（按规定不碰生产）。
7. `rules.json` 的 canonical 副本（`proxy-node-compat/proxy_node_compat/`）**尚未同步**
   —— 见 §2.5 的 ⚠️（本轮边界只允许改 `xray--core`）。
