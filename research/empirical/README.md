# 真内核实测证据（Phase 1）

这里的结论**不是读文档得来的**，是把配置喂给真内核跑出来的。
`probe-results.json` 是机器可读的原始结论，本文件是它的解读与**甄别记录**。

## 被测版本

| 内核 | 版本 | 二进制 |
|---|---|---|
| Xray | 26.3.27 (d2758a0, go1.26.1) | `/usr/local/bin/xray` |
| mihomo | Mihomo Meta v1.19.32 (go1.26.8) | `/root/catmi/mihomo/mihomo` |
| sing-box | 1.14.2 | `/root/catmi/sing-box/sing-box` |

## 方法

复现：`python3 tools/probe/probe.py --out research/empirical`（`tools/probe/README.md`）

**两层探针**，因为一层不够：

- **Tier A · 静态校验**：片段 → 完整配置 → 内核自己的校验器
  （`xray -test` / `mihomo -t` / `sing-box check`）
- **Tier B · 语义回环**：起真服务端 + 真客户端，从客户端代理端口取回目标内容。
  **只有这一层能抓出"校验通过但运行时静默降级"。**

**三条方法纪律**（否则结论会自欺）：

1. **控制组先行**：每个内核都有一条必然通过的用例。三个控制组全部 `True` 才算本轮有效。
   控制组不过 = 探针坏了，**不是**"内核不支持"。
2. **`✅?` = 校验通过但不可信**：该字段内核根本不校验时，静态层的 accepted 必须降级
   （`accepted_unverified`），只有 Tier B 能定论。实测 mihomo 对 `network` 就是这样。
3. **每个 `❌` 都必须读内核原文甄别**：是"内核不支持"，还是"我的测试数据写错了"？
   下面「甄别记录」里三个错误全是后者。

## 结论矩阵

`✅` 通过 · `✅?` 校验通过但该字段不被校验（需回环）· `❌` 明确拒绝 · `—` 该内核配置模型里**没有**这个字段

| 用例 | xray 26.3.27 | mihomo 1.19.32 | sing-box 1.14.2 |
|---|---|---|---|
| vless + tcp | ✅ | ✅ | ✅ |
| vless + ws | ✅ | ✅? | ✅ |
| vless + grpc | ✅ | ✅? | ✅ |
| vless + http(h2) | **❌ 已移除** | ✅? | ✅ |
| vless + httpupgrade | ✅ | ✅? | ✅ |
| vless + xhttp | ✅ | ✅? | **—** |
| vless + splithttp（旧名） | ✅ | ✅? | **—** |
| vless + mkcp | ✅ | ✅? | **❌ unknown transport** |
| mkcp 的 header/seed 老字段 | **❌ 已移除** | — | — |
| REALITY | ✅ | ✅ | ✅ |
| REALITY + Vision(flow) | ✅ | ✅ | ✅ |
| TLS + ECH | ✅ | ✅ | ✅（**要 PEM**） |
| VMess + WS + TLS | ✅ | ✅ | ✅ |
| Trojan + gRPC + TLS | ✅ | ✅ | ✅ |
| Shadowsocks 2022 | ✅ | ✅ | ✅ |
| Hysteria2 + obfs | — | ✅ | ✅ |
| TUIC v5 | — | ✅ | ✅ |
| AnyTLS | — | ✅ | ✅ |
| uTLS 指纹 | ✅ | ✅ | ✅ |
| mux / multiplex | ✅ | ✅ | ✅ |
| **回环** xray(tcp) → mihomo(tcp) | · | ✅通 | · |
| **回环** xray(tcp) → mihomo(**乱写 transport**) | · | 🚨**静默降级** | · |
| **回环** xray(**xhttp**) → mihomo(xhttp) | · | ✅通 | · |

## 已确认的发现

### F1 · Xray 26.x 移除了 HTTP(h2) transport —— 内核原文

```
The feature HTTP transport (without header padding, etc.) has been removed
and migrated to XHTTP stream-one H2 & H3. Please update your config(s)
according to release note and documentation.
```

**跨内核后果**：mihomo / sing-box **仍然支持** h2。所以「M 或 SB 服务端产出的 h2 节点，
交给 X 客户端」= `UNSUPPORTED`（版本相关：老 Xray 能用，26.x 不能）。
这类"对方还支持、我这边已经删了"是最容易让用户困惑的一类。

### F2 · Xray 26.x 移除了 mKCP 的 header/seed —— 内核原文

```
Failed to build mKCP config. > The feature mkcp header & seed has been removed
and migrated to finalmask/udp header-* & mkcp-original & mkcp-aes128gcm.
```

**后果**：**老配置加载即失败**（不是降级，是起不来）。所以"某节点以前能用、升级内核后用不了"
的根因可以定位到这一类。注意：不带 header/seed 的 mkcp 本身仍然 ✅。

### F3 · mihomo 对 `network` **完全不校验**，运行时静默当 tcp —— 回环实测

```
network: tcp（正确）             -t=0   连通 ✅
network: totally-nonsense        -t=0   连通 ✅   ← 根本不存在的值
network: mkcp                    -t=0   连通 ✅   ← mihomo 不支持
network: splithttp               -t=0   连通 ✅   ← Xray 旧名
```

对照 sing-box：同样的乱写 `FATAL: unknown transport type`。

**这是本项目最核心的存在理由**：接收方不会告诉你它没看懂。静态校验通过的 7 条用例
（`transport.ws/grpc/http_h2/httpupgrade/xhttp/splithttp_legacy/mkcp` × mihomo）必须靠回环才能定论，
本轮只回环验证了 `xhttp`（✅ 真支持）。

### F4 · 同一个能力，三个内核的**表示法不同**（URI→Kernel 映射的真实损失点）

ECH 实测：

| 内核 | 字段 | 需要的格式 |
|---|---|---|
| Xray | `tlsSettings.echConfigList` | base64 ECHConfigList |
| mihomo | `ech-opts.config` | base64 ECHConfigList |
| sing-box | `tls.ech.config[]` | **PEM**（`-----BEGIN ECH CONFIGS-----`） |

用同一个 base64 喂 sing-box → `FATAL: initialize outbound[0]: invalid ECH configs pem`；
换成 PEM → ✅。**同一个节点，同一份 ECHConfig，换个内核就要换表示法** ——
这正是 Node Profile 必须把 `URI Representation` 和 `Kernel Representation` 分开建模的原因。

### F5 · Xray 对 ECH **内容**不做校验（又一处"能解析 ≠ 支持"）

用一个**编造的** base64（`AEX+DQBB3gAgACC`，非合法 ECHConfigList）喂 xray → `Configuration OK`。
说明 xray 只做 base64 解码层面的接受，内容合法性留给运行时。
→ 这类字段在能力库里必须标成 `accepted_unverified`，不许记成 SUPPORTED。

### F6 · 协议覆盖面的结构性差异

- `hysteria2` / `tuic` / `anytls`：xray **没有**对应的 outbound 类型（`—`），mihomo 与 sing-box 都有。
- `xhttp` / `splithttp`：sing-box **完全没有**（不是"拒绝"，是配置模型里没这个字段）。
- `mkcp`：sing-box 明确拒绝；mihomo 静默降级（F3）。

## 甄别记录（我自己的三个测试数据错误）

**每个 `❌` 都被读过原文才定性**，否则会把"我写错了"记成"内核不支持"。本轮抓到三次：

| 现象 | 真实原因 | 修正 |
|---|---|---|
| `security.ech` 在 mihomo 上 ❌ `base64 decode ech config string failed` | 我编的 base64 不合法 | 换成 Cloudflare 真实发布的 ECHConfigList（取自 `crypto.cloudflare.com` 的 HTTPS RR）→ ✅ |
| `security.ech` 在 sing-box 上 ❌ `invalid ECH configs pem` | **不是**测试值问题也行——sing-box 要 PEM | 改用例为 PEM → ✅（这就是 F4 的发现） |
| mihomo 重测 ECH 时 `rules[0] [MATCH] error: format invalid` | 我的 YAML 写成 `rules: [MATCH,DIRECT]`，被解析成两个列表项 | 写成 `- MATCH,DIRECT` → ✅ |

结论：**"内核不支持"这个结论必须由内核原文支撑**，不能由"我的配置没通过"推出。

## UNKNOWN（本轮没有结论，不许猜）

| 项 | 为什么没结论 |
|---|---|
| mihomo 上 `ws/grpc/http_h2/httpupgrade/mkcp/splithttp` 是否**真能用** | 静态层不可信（F3），需逐个回环 |
| xray 的 ECH 运行时是否真生效 | F5：配置层不校验内容 |
| mux / multiplex 跨内核互通（smux vs h2mux 的具体协商） | 需要 A 内核服务端 + B 内核客户端的回环 |
| h2 被移除的**确切版本**、以及 25.x 是否还有过渡期兼容 | 需要查 changelog/release note |
| REALITY 的 `spiderX`、`shortId` 边界行为跨内核是否一致 | 未测 |
| mihomo 静默降级时**到底**用了什么默认值（tcp vs 协议默认） | 目前只能证明"连通了"，需要抓包确认 |
| sing-box 是否存在任何等价于 mkcp 的传输 | 已确认 `kcp` 不存在，是否另有等价物未查 |

> `UNKNOWN` 是这个项目的**合法输出**，不是失败。宁可返回 UNKNOWN，也不许猜成 SUPPORTED。
