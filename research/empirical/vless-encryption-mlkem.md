# VLESS Encryption（`mlkem768x25519plus`，后量子）跨内核实测

> 被测节点：RN 上的 **vless-xhttp-04**，我们自己的 Xray 生成的真实分享链接：
>
> ```
> vless://c521fd45-…@107.173.154.178:22726?encryption=mlkem768x25519plus.native.0rtt.<1610字符>…
>   &security=tls&sni=cloudflare.com&type=xhttp&path=/&ech=<base64>#vless-xhttp-04
> ```
>
> 这条链接的 `encryption=` 是 **Xray 26.x 的 VLESS Encryption**，不是任何其它内核的字段。
> 本文件回答一个问题：**这个参数交给其它内核，它们是"认识"还是"不认识"，不认识时会发生什么。**

## 被测版本与方法

| 内核 | 版本 | 二进制 |
|---|---|---|
| Xray | 26.3.27 (`d2758a0`, go1.26.1) | `/usr/local/bin/xray` |
| mihomo | Mihomo Meta v1.19.32 (go1.26.8, with_gvisor) | `/root/catmi/mihomo/mihomo` |
| sing-box | 1.14.2 (go1.26.8) | `/root/catmi/sing-box/sing-box` |

**两层证据**（沿用 `research/empirical/README.md` 的方法纪律）：

- **Tier A · CONFIG_VALIDATION**：`xray -test` / `mihomo -t` / `sing-box check`
- **Tier B · RUNTIME_TEST**：真服务端 + 真客户端回环，从客户端代理端口取回目标内容

**本轮独有的方法要点 —— 「被识别」与「被静默忽略」的判别法**：
mihomo 对未知键/未知 transport 名**静默忽略**（实测 M3/M4 均 `-t` 通过）。
所以「`-t` 通过」**不能**证明 `encryption` 被支持。判别方法是**控制组对照**：

> 同一个 `-t`，对**根本不存在的键**（M4）返回成功，却对**非法 `encryption` 值**（M2/M2b/M2c）返回失败
> ⇒ 说明 `encryption` 是**被声明、被解析、被校验**的字段，而不是被丢掉的未知键。

**环境卫生**：全部实验在 `/tmp/vlessenc-test/` 下进行；结束后已 `kill -9` 全部自起进程（含 13 个孤儿
Xray 进程，按 `/proc/*/cwd` 精确匹配）并 `rm -rf` 测试目录。生产服务 `xrayls`(pid 29307)、
`sing-box`(60510)、`mihomo`(119320) 全程未重启，`/root/catmi/xray/conf/vless-xhttp-04.json` mtime
仍为 `2026-10-08 21:20:31`（实验前）。

---

## 1. Xray 26.3.27 — 原生支持（这是它自己的字段）

### 字段名与写法

| 位置 | 字段 | 源码 |
|---|---|---|
| **客户端出站** | `outbounds[].settings.vnext[].users[].encryption` | `infra/conf/vless.go:241` |
| **服务端入站** | `inbounds[].settings.decryption` | `infra/conf/vless.go:34` |
| 入站 `clients[]` | `encryption` **被明令禁止** | `infra/conf/vless.go:78` |

写法（由 `xray vlessenc` 生成，输出成对的 decryption/encryption）：

```
mlkem768x25519plus.<xorMode>.<rtt>.<key 或 padding>[.<…>]
  xorMode : native | xorpub | random
  rtt     : 客户端 0rtt | 1rtt   ；服务端是时间窗 <NNN>s 或 <NNN>-<NNN>s
```

`xray vlessenc` 原文输出（两种认证，**不要混用**）：

```
Choose one Authentication to use, do not mix them. Ephemeral key exchange is Post-Quantum safe anyway.

Authentication: X25519, not Post-Quantum
"decryption": "mlkem768x25519plus.native.600s.GAEgstA4BEHHIm5G-VCP1chB7gbnrIHOlCm7uM7loF8"
"encryption": "mlkem768x25519plus.native.0rtt.P9MXi11tNrvrA48zS9byWORzmOFehBmhRtNt580LF0w"

Authentication: ML-KEM-768, Post-Quantum
"decryption": "mlkem768x25519plus.native.600s.MSeBfO7x…"
"encryption": "mlkem768x25519plus.native.0rtt.jhkVXtx6iAMqE3…"     ← 长度 1610
```

真实分享链接 → Xray 客户端配置的**权威映射**由 Xray 自己产出，本节点就是：
`/root/catmi/xray/out/vless-xhttp_share-04.txt`（URI）↔ `/root/catmi/xray/out/vless-xhttp_client-04.json`
（`users[0].encryption` = 链接里 `encryption=` 的**同一个字符串**，长 1610）。

### 实测结果

| # | 用例 | 原文输出（关键片段） | exit |
|---|---|---|---|
| X1 | **真实生产客户端配置** | `Configuration OK.` | 0 |
| X2 | 客户端 **不写** `encryption` | `VLESS users: please add/set "encryption":"none" for every user` | 23 |
| X3 | `encryption: "none"` | `Configuration OK.` | 0 |
| X4 | 垃圾值 `TOTALLY-GARBAGE-VALUE` | `VLESS users: unsupported "encryption": TOTALLY-GARBAGE-VALUE` | 23 |
| X5 | 未知 scheme `foobar.native.0rtt.…` | `VLESS users: unsupported "encryption": foobar.native.0rtt.AAA…` | 23 |
| X6 | 合法 scheme + 非法 base64 | **`panic: runtime error: slice bounds out of range [19:18]`** | **2** |
| X7 | 合法 scheme + 合法 base64 但长度 11 | **`panic: runtime error: slice bounds out of range [12:11]`** | **2** |
| X8 | 服务端 `decryption` 非法 base64 | **`panic: runtime error: slice bounds out of range [10:9]`** | **2** |
| X9 | 服务端**不写** `decryption` | `VLESS settings: please add/set "decryption":"none" to every settings` | 23 |
| X10 | 服务端 `decryption: "none"` | `Configuration OK.` | 0 |
| X16 | 入站 `clients[]` 带 `encryption` | `VLESS clients: "encryption" should not be in inbound settings` | 23 |

**X6/X7/X8 是上游真 bug，已定位到行**：`infra/conf/vless.go:343-355` 把
「长度 < 20 的段」当成 padding 处理（`padding += len(r) + 1`），随后
`account.Encryption = account.Encryption[padding:]` **越界 panic**。
我算出的越界下标与实测 panic 完全一致（`[19:18]` / `[12:11]`），确认是同一处。

**回环（RUNTIME_TEST，`network: xhttp`，同一密钥对）**：

```
R1  xray(enc=对1) → xray(dec=对1)      payload = TUNNEL-PAYLOAD-OK          ✅ 真生效
R2  xray(enc=对2) → xray(dec=对1)      服务端: proxy/vless/inbound: ML-KEM-768 handshake failed
                                              > chacha20poly1305: message authentication failed
R4  xray(enc=对1) → xray(dec=none)     服务端: proxy/vless/encoding: invalid request version
                                              + "from … rejected"
R*  xray(enc="none") → xray(dec=对1)   配置层 Configuration OK，运行时服务端:
                                              ML-KEM-768 handshake failed > chacha20poly1305: message authentication failed
R3  xray(不写 encryption) → 服务端     客户端**起不来**（即 X2，配置层就拒绝）
```

### 证据等级
`RUNTIME_TEST` / `SRC` / `CONFIG_VALIDATION` — **HIGH**

---

## 2. mihomo v1.19.32 — 原生支持（真生效，不是静默忽略）

### 字段名与源码位置

```go
// adapter/outbound/vless.go:71
Encryption        string            `proxy:"encryption,omitempty"`
```

而且它**真的接进了握手路径**，不是只声明不用：

```go
// adapter/outbound/vless.go:511
v.encryption, err = encryption.NewClient(option.Encryption)

// adapter/outbound/vless.go:276-277
if v.encryption != nil {
    c, err = v.encryption.Handshake(c)
```

解析器 `transport/vless/encryption/factory.go`（`NewClient`）：

```go
switch encryption {
case "", "none": // We will not reject empty string like xray-core does, because we need to ensure compatibility
    return nil, nil                      // ← 静默 no-op：不加密，继续连
}
… s[0]=="mlkem768x25519plus"；s[1] native|xorpub|random；s[2] 1rtt|0rtt
… 每段长度 >= 20 时按 base64 RawURL 解码，长度必须 == 32 (X25519) 或 == 1184 (ML-KEM-768)
… 否则 return nil, fmt.Errorf("invaild vless encryption value: %s", encryption)   // ← 上游拼写错误 "invaild"
```

mihomo 侧字段名是 **`proxies[].encryption`**（URI 里同名，直接对应）。

### 实测结果（Tier A）

| # | 用例 | 原文输出 | exit |
|---|---|---|---|
| M1 | **真实生产 `encryption` 值**（1610 字符） | `configuration file … test is successful` | 0 |
| M2 | 垃圾值 | `level=error msg="proxy 0: invaild vless encryption value: TOTALLY-GARBAGE-VALUE"` → `test failed` | 1 |
| M2b | 合法 scheme + 非法 base64 | `level=error msg="proxy 0: failed to use encryption: empty nfsPKeysBytes"` | 1 |
| M2c | 未知 xorMode `…BOGUS.0rtt.…` | `level=error msg="proxy 0: invaild vless encryption value: mlkem768x25519plus.BOGUS.…"` | 1 |
| M3 | **控制组**：`network: definitely-not-a-transport` | `test is successful` ← 静默忽略 | 0 |
| M4 | **控制组**：未知键 `this-key-does-not-exist-anywhere` | `test is successful` ← 静默忽略 | 0 |
| M5 | `encryption: "none"` | `test is successful` | 0 |
| M6 | **真实生产 mihomo 片段** `/root/catmi/xray/out/vless-xhttp_client-01.yaml`（含 `encryption`） | `test is successful` | 0 |

**M3/M4 vs M2/M2b/M2c 就是本节的结论**：同一把尺子（`mihomo -t`），对不存在的键宽容，
对非法 `encryption` 失败 ⇒ `encryption` **被识别**。

### 实测结果（Tier B 回环，真在线上跑）

```
R5  mihomo(enc=对1) → xray(dec=对1)     payload = TUNNEL-PAYLOAD-OK          ✅ 真生效
R6  mihomo(enc=对2) → xray(dec=对1)     服务端: ML-KEM-768 handshake failed > chacha20poly1305:
                                              message authentication failed
                                        mihomo: [TCP] dial t … connect error: EOF  （重试3次）
R7  mihomo(enc="none") → xray(dec=对1)  服务端: ML-KEM-768 handshake failed > unexpected EOF
```

R6 是关键：**换成另一对合法密钥就连不上** ⇒ mihomo 确实用配置里的那个公钥做了 ML-KEM 封装，
不是"配了个寂寞"。

**真实生产节点（RW 组，连 `107.173.154.178:22726` 这个活着的 vless-xhttp-04）**：

```
RW1 mihomo + 真实 encryption（无 ECH）  → 出口 IP 104.28.195.192    ✅ 通了
RW2 mihomo + 真实 encryption + ECH      → 出口 IP 104.28.195.192    ✅ 通了
RW3 同一份配置，仅删掉 encryption 一行  → <FAILED>                  ← 唯一变量就是 encryption
（RN 直连出口 IP 为 104.28.201.80，与隧道出口不同 ⇒ 流量确实过了节点）
```

### 证据等级
`SRC` + `CONFIG_VALIDATION` + `RUNTIME_TEST` — **HIGH**

---

## 3. sing-box 1.14.2 — 不支持（且**拒绝得最彻底**）

### 字段名：**没有**

```go
// option/vless.go  (tag v1.14.2, 全文 27 行)

type VLESSUser struct {
    Name string `json:"name"`
    UUID string `json:"uuid"`
    Flow string `json:"flow,omitempty"`
}                                    // ← 没有 Encryption

type VLESSOutboundOptions struct {
    DialerOptions
    ServerOptions
    UUID    string      `json:"uuid"`
    Flow    string      `json:"flow,omitempty"`
    Network NetworkList `json:"network,omitempty"`
    OutboundTLSOptionsContainer
    Multiplex      *OutboundMultiplexOptions `json:"multiplex,omitempty"`
    Transport      *V2RayTransportOptions    `json:"transport,omitempty"`
    PacketEncoding *string                   `json:"packet_encoding,omitempty"`
}                                    // ← 没有 Encryption；出站也**没有 users[] 数组**
```

即：sing-box 的 VLESS 是**扁平 `uuid`** 模型，**连"写在哪里"都不存在** —— 这比"有个字段但我不认"更彻底。

严格校验来自 `option/options.go:41`：

```go
func (o *Options) UnmarshalJSONContext(ctx context.Context, content []byte) error {
        …
        decoder.DisallowUnknownFields()
```

顺带钉死另一件事（同一条链接上的 `type=xhttp`）—— transport 枚举里根本没 xhttp：

```go
// option/v2ray_transport.go:15
Type string `json:"type" enum:"http,ws,quic,grpc,httpupgrade"`
```

### 实测结果（Tier A）

| # | 用例 | 原文输出 | exit |
|---|---|---|---|
| S0 | **控制组**：朴素 vless outbound | （无输出） | 0 |
| S1 | 出站顶层 `encryption` | `FATAL[0000] decode config at s1.json: outbounds[0].encryption: json: unknown field "encryption"` | 1 |
| S2 | 出站 `users[]`（Xray 形状） | `FATAL … outbounds[0].users: json: unknown field "users"` | 1 |
| S3 | `encryption: "none"`（Xray 的"关闭"哨兵值） | `FATAL … outbounds[0].encryption: json: unknown field "encryption"` | 1 |
| S4 | `transport.type = "xhttp"` | `FATAL … outbounds[0].transport: unknown transport type: xhttp` | 1 |
| S5 | **入站** `users[0].encryption`（接收方） | `FATAL … inbounds[0].users[0].encryption: json: unknown field "encryption"` | 1 |
| S6 | **严格性控制组**：任意未知键 | `FATAL … outbounds[0].totally_unknown_key: json: unknown field "totally_unknown_key"` | 1 |

S0 通 + S1/S2/S3/S5 全 FATAL ⇒ FATAL **可归因于该字段本身**，不是我的配置写坏了。
S3 尤其重要：**连 `"none"` 都不接受** —— 没有"降级到明文"的选项。

### 实测结果（Tier B 跨内核回环）

sing-box 客户端**根本无法表达** `encryption`（S1/S3 FATAL），所以只能验"表达不了会怎样"：

```
S7  sing-box(无 encryption，因为它写不出来) → xray 服务端要求 dec
        服务端: proxy/vless/inbound: ML-KEM-768 handshake failed > unexpected EOF
        结果: <EMPTY/TIMEOUT>                                        ❌ 不通

S8  控制组：同一个 sing-box 客户端 → 同一个 xray 服务端，仅把 decryption 改成 none
        payload = SINGBOX-CROSS-TUNNEL-OK                             ✅ 通
```

**S8 是关键对照**：sing-box 客户端本身完全能连这台 Xray 服务端、能过 xhttp/tcp，
**唯一的变量就是 ML-KEM 加密要求** —— 加上它就不通。

### 证据等级
`SRC` + `CONFIG_VALIDATION` + `RUNTIME_TEST` — **HIGH**

---

## 4. 结论表：内核 × 是否支持 × 失败模式 × 证据

| 内核 (版本) | `encryption` 字段 | 是否支持 | **失败模式**（内核不认识这个参数时） | 证据 |
|---|---|---|---|---|
| **Xray** 26.3.27 | `users[].encryption` / `settings.decryption` | ✅ **支持**（原生，运行时真生效 R1） | — | `SRC` vless.go:34/241 · `CONFIG_VALIDATION` X1 · `RUNTIME_TEST` R1 |
| **mihomo** v1.19.32 | `proxies[].encryption` | ✅ **支持**，**且非静默忽略**（R5 真生效 / R6 换密钥即失败 / RW1 真实节点通） | 值是 `none`/空 → **配置层静默 no-op**，运行时对要求加密的服务端失败：`ML-KEM-768 handshake failed > unexpected EOF`（R7）。值非法 → **配置层硬拒绝** `invaild vless encryption value`（M2） | `SRC` vless.go:71,276,511 · `CONFIG_VALIDATION` M1/M2/M3/M4 · `RUNTIME_TEST` R5/R6/R7/RW1-3 |
| **sing-box** 1.14.2 | **不存在** | ❌ **不支持** | **配置层 FATAL 硬拒绝**：`json: unknown field "encryption"`（出站顶层 / 出站 users[] / 入站 users[] 三处全拒，**连 `"none"` 也拒**）。若把参数丢掉再生成配置 → 客户端连上，服务端拒绝：`ML-KEM-768 handshake failed > unexpected EOF` | `SRC` option/vless.go（无字段）+ options.go:41（DisallowUnknownFields）· `CONFIG_VALIDATION` S0/S1/S2/S3/S5 · `RUNTIME_TEST` S7/S8 |

### 失败模式归一化（给能力注册表用）

把三家的行为压成五个可枚举的 `failure_mode`：

| failure_mode | 含义 | 谁 |
|---|---|---|
| `REJECT_AT_CONFIG_LOAD` | 配置加载即失败，节点根本建不起来（最安全：用户立刻知道） | sing-box 全部；mihomo 值非法；Xray 值非法/缺字段 |
| `SILENT_NOOP_THEN_RUNTIME_FAIL` | 配置层当"不加密"放过，运行时握手被服务端拒，连接建立不起来 | mihomo `encryption: none`/空 |
| `RUNTIME_HANDSHAKE_REJECT` | 配置层能过，运行时被对端拒（带内核原文） | 所有"没加密/加错密"的组合 |
| `PANIC_CRASH` | 内核**崩溃**（非优雅报错） | Xray 26.3.27 对畸形 `encryption`/`decryption`（`infra/conf/vless.go:355`） |
| `SILENT_DOWNGRADE` | 配置层忽略、运行时**仍能通**（最危险） | 本轮 **未在任何内核观察到**（mihomo 的 `none` 是 no-op 但**不通**） |

> ⚠️ **本轮没有发现"静默降级到明文且仍然连通"的路径**。这是好消息，但要写清 limits：
> 只证明了 `mlkem768x25519plus` 这一个 scheme；且"配置能过"与"真的用了加密"在 mihomo 上
> 是靠回环（R5/R6）区分的，静态校验单独不足。

### 给能力注册表的建议数据行

```yaml
- feature: vless.encryption.mlkem768x25519plus
  uri_param: encryption          # 分享链接 query 参数名（三家 URI 层同名）
  kernel_field:
    xray:    outbounds[].settings.vnext[].users[].encryption   # 服务端: settings.decryption
    mihomo:  proxies[].encryption
    sing-box: null                # 字段不存在，且出站无 users[] 数组
  reason_code: KERNEL_FIELD_ABSENT          # sing-box
  failure_mode: REJECT_AT_CONFIG_LOAD       # sing-box / mihomo(非法值) / xray(非法值)
  # mihomo + value in {"", "none"} 时: failure_mode = SILENT_NOOP_THEN_RUNTIME_FAIL
  # xray + 畸形值(<20字符段) 时:        failure_mode = PANIC_CRASH
  accepted_values: [mlkem768x25519plus.<native|xorpub|random>.<0rtt|1rtt>.<b64url>,
                    none]
  runtime_verified: {xray: true, mihomo: true, sing-box: false}
```

---

## 5. 证据条目（标准形状）

```yaml
- id: e-xray-vlessenc-config-shape
  type: SRC
  confidence: HIGH
  date: 2026-10-10
  target: {kernel: xray, version: "26.3.27", platform: linux/amd64}
  claim: "Xray 客户端用 users[].encryption、服务端用 settings.decryption；入站 clients[].encryption 被明令禁止"
  how: "读 tag v26.3.27 的 infra/conf/vless.go，并逐条用 xray -test 复现报错原文"
  where: "infra/conf/vless.go:34,78,241,360,362"
  limits: "只证明配置层字段位置与校验文案；未证明 25.x 及更早版本是否同名"

- id: e-xray-mlkem-loopback
  type: RUNTIME_TEST
  confidence: HIGH
  date: 2026-10-10
  target: {kernel: xray, version: "26.3.27", platform: linux/amd64}
  claim: "Xray 的 mlkem768x25519plus 在 xhttp 上真生效（回环接通并取回 payload）"
  how: "xray vlessenc 生成密钥对 → 服务端 decryption + 客户端 encryption 回环(xhttp, 127.0.0.1) → curl 取回 TUNNEL-PAYLOAD-OK"
  where: "本文件 §1 RUNTIME_TEST R1"
  limits: "只证明该版本该构建、且 xhttp 传输；未验证其它 transport；未抓包确认无明文回退"

- id: e-xray-vlessenc-malformed-panic
  type: CONFIG_VALIDATION
  confidence: HIGH
  date: 2026-10-10
  target: {kernel: xray, version: "26.3.27", platform: linux/amd64}
  claim: "畸形 encryption/decryption 值导致 Xray panic（exit 2），不是优雅报错"
  how: "喂入合法 scheme + 非法 base64 / 过短 payload，观察 panic 与栈顶函数"
  where: "infra/conf/vless.go:343-355；实测 panic: slice bounds out of range [19:18] / [12:11] / [10:9]"
  limits: "只证明 26.3.27；未确认 25.x 是否同样；未提 issue 给上游"

- id: e-mihomo-vlessenc-recognized-not-ignored
  type: CONFIG_VALIDATION
  confidence: HIGH
  date: 2026-10-10
  target: {kernel: mihomo, version: "1.19.32", build: "with_gvisor", platform: linux/amd64}
  claim: "mihomo 的 encryption 是被解析校验的字段，不是被静默忽略的未知键"
  how: "同一 mihomo -t：未知键(M4)/未知transport(M3) 通过；非法 encryption 值(M2/M2b/M2c) 失败"
  where: "adapter/outbound/vless.go:71,511,276；transport/vless/encryption/factory.go"
  limits: "证明的是『被校验』；『真生效』由 e-mihomo-vlessenc-loopback 单独证明"

- id: e-mihomo-vlessenc-loopback
  type: RUNTIME_TEST
  confidence: HIGH
  date: 2026-10-10
  target: {kernel: mihomo, version: "1.19.32", build: "with_gvisor", platform: linux/amd64}
  claim: "mihomo 1.19.32 能真正使用 Xray 的 mlkem768x25519plus（含连真实生产节点）"
  how: "mihomo(enc) → xray(dec) 回环取回 payload；且 mihomo+真实encryption → 活的 107.173.154.178:22726 出口IP改变"
  where: "本文件 §2 RUNTIME_TEST R5 / RW1 / RW2；反证 R6（换另一对合法密钥即失败）、RW3（删掉encryption即失败）"
  limits: "只证明 ML-KEM-768(native) 与 0rtt 客户端形态；未验证 xorpub/random、未验证 X25519 非PQ形态、未验证 mihomo 作服务端"

- id: e-singbox-vless-encryption-absent
  type: SRC
  confidence: HIGH
  date: 2026-10-10
  target: {kernel: sing-box, version: "1.14.2", platform: linux/amd64}
  claim: "sing-box 1.14.2 的 VLESS 模型里没有 encryption，出站也没有 users[] 数组"
  how: "读 tag v1.14.2 的 option/vless.go 全文（27 行）+ option/options.go:41 DisallowUnknownFields"
  where: "option/vless.go（VLESSUser/VLESSOutboundOptions）；option/options.go:41；option/v2ray_transport.go:15"
  limits: "只证明 1.14.2；未查更早/更新版本是否引入；未区分『尚未支持』与『明确拒绝支持』"

- id: e-singbox-vless-encryption-fatal
  type: CONFIG_VALIDATION
  confidence: HIGH
  date: 2026-10-10
  target: {kernel: sing-box, version: "1.14.2", platform: linux/amd64}
  claim: "sing-box 对 encryption 在出站顶层/出站users[]/入站users[] 三处全部 FATAL；连 \"none\" 也拒"
  how: "sing-box check；控制组 S0 通过、S6 未知键同样 FATAL，排除『配置写坏』"
  where: "本文件 §3 S0/S1/S2/S3/S5/S6"
  limits: "只证明 1.14.2 的 check 行为"

- id: e-crosskernel-singbox-vs-xray-mlkem
  type: RUNTIME_TEST
  confidence: HIGH
  date: 2026-10-10
  target: {kernel: sing-box + xray, version: "1.14.2 / 26.3.27", platform: linux/amd64}
  claim: "sing-box 客户端连不上要求 ML-KEM 的 Xray 服务端；同一客户端对 decryption=none 的服务端完全正常"
  how: "同端口同传输，仅切换服务端 decryption：S7 失败(unexpected EOF) vs S8 成功(SINGBOX-CROSS-TUNNEL-OK)"
  where: "本文件 §3 RUNTIME_TEST S7/S8"
  limits: "只测 tcp 传输；xhttp 因 sing-box 无该 transport 无法参与对照（另见 S4）"
```

---

## 6. 甄别记录（我自己犯的错，必须先说清楚）

**每个 `❌` 都读内核原文才定性。本轮抓到 4 个自己的坑，其中 3 个曾产出过错误结论：**

| 现象 | 真实原因 | 修正 |
|---|---|---|
| 第一轮回环里"换另一对密钥"居然也通了（MR2），而 Xray 侧同名用例却不通过 | **我的 `enc2.txt` 用了与 `enc.txt` 完全相同的生成表达式** → 两份"不同"的密钥其实是同一对 | 重新跑 `xray vlessenc`，并**断言 `ENC != ENC2`**（R1–R7 已带此断言） |
| X12–X15 / MR1–MR2 整批失败或整批"成功"，结果自相矛盾 | `pkill -f "vlessenc-test/srv.json"` **从未匹配**（配置文件用了相对路径，cmdline 里没有目录名）→ 旧进程一直占着端口，后续服务端起不来 / 客户端连到了**上一轮的旧进程** | 改用**每用例唯一端口** + 绝对配置路径 + `kill -9 $PID` + 启动前断言端口空闲 |
| 清理脚本一执行就断线 | `pkill -9 -f "vlessenc-test"` 的 pattern **匹配到了我自己 ssh shell 的 cmdline**，把自己杀了 | 改为扫 `/proc/*/cwd` 精确匹配 + 显式 PID kill（并确认生产进程未受影响） |
| `mihomo -t -f /root/catmi/all-clients.yaml` → `yaml: line 5: did not find expected key` | **与 `encryption` 无关**：该文件是 `catmi-export.sh` 把 **13 个片段**首尾相接拼出来的，有 **13 个顶层 `proxies:` 键**（`grep -c '^proxies:' = 13`），本身就不是合法 YAML | **不得**把它当作 `encryption` 的证据；改用**单节点真片段** `/root/catmi/xray/out/vless-xhttp_client-01.yaml` → `test is successful`（M6） |

> 最后一条尤其要留档：`all-clients.yaml` 解析失败看起来像"mihomo 不支持我们的配置"，
> 实际是**我们自己的导出脚本把文件拼坏了**。这正是 `docs/evidence-model.md` §6 说的
> "结论与证据脱钩"的典型 —— 差一点就把它记成内核问题。

---

## 7. UNKNOWN（没有证据，不许猜）

| 项 | 为什么没结论 |
|---|---|
| mihomo 从**哪个版本**开始支持 `encryption` | 只验了 1.19.32。按 `docs/evidence-model.md` R2，不得插值；需逐版验证 |
| mihomo 的 `xorpub` / `random` xorMode 与 Xray 是否**运行时**互通 | 源码里 `factory.go` 认这三个值（SRC），但只回环验了 `native` |
| mihomo 能否作**服务端**接受 ML-KEM（`NewServer` 存在） | `factory.go` 有 `NewServer`（SRC），但 mihomo 的 vless **入站**未做回环 |
| Xray 的 **X25519 非后量子** auth 形态（32 字节密钥）与 mihomo 是否互通 | 只测了 ML-KEM-768（1184 字节）那一种 |
| 服务端 `decryption` 时间窗（`600s`）与客户端 `0rtt` ticket 复用的**跨内核**行为 | 首连已通；ticket 复用路径未单独验证 |
| RW1 vs RW2 里 ECH **是否真的生效**（而不是回退了） | 两者都通，但我没有抓包/服务端日志证明 ECH 被实际使用 → ECH 是否生效属 UNKNOWN |
| sing-box 是否有**更新版本**引入 `encryption` | 只读/验了 1.14.2 |
| `xray vlessenc` 输出的 padding 语法全集、`600s-1200s` 区间语义 | 只验证了生成器输出的形态，未穷举解析边界 |
| Xray 那个 panic 是否已在更高版本修复 | 未查上游 commit / issue |
