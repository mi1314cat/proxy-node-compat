# AnyReality 验收：我们自己的组合能力能不能进模型

> 这是本项目最重要的一条验收用例（用户指定）。AnyReality 不是某个内核的标准协议，
> 而是**我们自己的组合能力**：同一套传输/认证之上，把 REALITY 当成可叠加的安全层。
> 如果架构正确，它应该能被完整表达、能被逐内核判定，**而不是让解析失败或丢字段**。

## AnyReality 在我们仓库里的三个真实变体

| 变体 | 出处 | 组合 | 现有处理方式 |
|---|---|---|---|
| **ss + REALITY** | `xray--core/conf/Shadowsocks.sh:256,395,405` | SS2022 + REALITY | 硬编码注释：分享链接**只有** method+PSK+地址（"无标准 ss:// URI 语义"），Reality 参数（target/serverNames/pbk/sid）只写在**注释里**；并注明"mihomo 的 ss 出站不支持 Reality（AnyReality），请使用 X 内核客户端" |
| **trojan + REALITY** | `xray--core/conf/Trojan.sh:12` | Trojan + none/tls/reality | "不良林 AnyReality 三层模型" |
| **AnyTLS + REALITY** | `sing-box-core/src/conf/anytls.sh:1-20` | AnyTLS + REALITY | 硬编码注释引用 mihomo 官方原文：<br>`Mihomo does not support AnyTLS+Reality, and will not support this combination in the future` → 该变体**不产出** mihomo YAML |

**现状的问题**（正是本项目要解决的）：

1. 兼容性结论以**人类注释**的形式散落在三个仓库的脚本里 —— 没有机器可读载体，
   客户端无法据此自动分组/禁用，改一次要改三处。
2. **URI 表达力缺口**被当成"注释说明"而不是**结构化损失**：
   ss+reality 的 `ss://` 链接**物理上装不下** Reality 参数，这是个
   `URI Representation = partial` 的典型，必须进 `losses[]`，而不是写句注释了事。
3. 注释本身可能是**错的** —— 见下面实测。

## 实测（真内核，Xray 26.3.27 / mihomo v1.19.32 / sing-box 1.14.2）

### 配置层（已确认）

| 内核 | 能否**表达** ss+REALITY | 证据 |
|---|---|---|
| Xray | ✅ 能 | `shadowsocks` outbound + `streamSettings.security=reality` → `Configuration OK` |
| sing-box | ❌ **不能** | `tls` 字段在 shadowsocks outbound 上根本不存在：<br>`FATAL: outbounds[0].tls: json: unknown field "tls"` |
| mihomo | ⚠️ 能写进配置、`-t` 通过，但**是否真按 reality 处理未知** | 见下 |

### ⚠️ 我们自己的注释是错的

`xray--core/conf/Shadowsocks.sh:396` 写着「sing-box / v2rayN **可直接叠加 Reality**」。
**真内核给出的答案是不能**：sing-box 的 shadowsocks outbound 没有 `tls` 字段，直接 FATAL。

→ 这在生产上就是"用户照着我们的说明去用 sing-box 客户端，结果节点根本起不来"。
靠人写注释维护兼容性结论，迟早出错；这正是要把它变成**带证据的数据**的理由。

### 运行层：UNKNOWN（不猜）

> **【已结案 · 2026-10-10】** 见 `cross-kernel-matrix.md` §2。回环后来跑通了，当时的失败原因
> 不在内核：reality **服务端**的 mimicry 读循环有 8192 字节缓冲上限，用真实站点
> （`www.microsoft.com`，Certificate 记录 8273B）当 `dest` 时会 `break` 掉握手流程；
> 换成证书记录 ~466B 的本地 Go TLS 服务端作 `dest` 后，同一套 ss+reality 配置立刻回环成功。
> 三个内核的最终结论：**Xray 能配且能用（回环实证）／ mihomo 静默忽略 `reality-opts`
> （`ss` 上根本没这字段）／ sing-box 配置层硬报错（无模型）**。下面这段保留为当时的原始记录。

用 Xray 起「SS2022 + REALITY」服务端 + socks 客户端做回环（同一密钥、SNI、shortId）：
服务端确认在监听（`ss -tln` 命中），但客户端取内容为空，**回环未跑通**。
可能原因尚未定位（reality handshake 细节 / uTLS 指纹 / 测试配置）。

按本项目的纪律：**没有证据就是 UNKNOWN**，不许写成"不支持"，也不许写成"支持"：

```
feature: mi1314cat:anyreality.ss-reality
kernel:  mihomo
status:  UNKNOWN
reason:  配置层接受（-t 通过），但因该内核不校验 transport/security 类字段，
         静态校验不能证明它们被真正使用；运行层回环实验尚未跑通。
```

## 顺带发现：Xray 26.3.27 正在弃用 Shadowsocks

服务端与客户端启动时都打印：

```
The feature Shadowsocks (with no Forward Secrecy, etc.) is deprecated,
not recommended for using and might be removed.
Please migrate to VLESS Encryption as soon as possible.
```

这对 AnyReality 变体 #1 是长期风险（协议本身可能被移除），**必须进能力库的
`deprecated` 维度**，否则我们的 ss 系节点会在某次内核升级后集体失效。
（注：SS2022 本身是带前向保密的，这条警告仍被打印 —— 具体判定条件待查，标 UNKNOWN。）

## 反向发现：Xray 对 SS 密钥长度不校验

用 **32 字节**密钥配 `2022-blake3-aes-128-gcm`（该算法要求 **16 字节**）：

- Xray：`Configuration OK`（**放行**，运行期才可能失败）
- mihomo：明确拒绝 —— `bad key length, required 16, got 32`
- sing-box：未测

又一次「能解析 ≠ 能用」，而且这次是 Xray 侧不严格。这类字段在能力库里必须带
`validation: lax` 标记，静态层结论只能给 `accepted_unverified`。

## 结论：AnyReality 应该怎么进模型

1. **它是 feature 组合，不是协议**。模型里应是
   `protocol: shadowsocks` + `features: [security.reality, ...]`，
   而不是新增一个 `protocol: anyreality`。
2. **需要 vendor 命名空间**：`mi1314cat:anyreality.ss-reality` /
   `mi1314cat:anyreality.anytls-reality` / `mi1314cat:anyreality.trojan-reality`。
   第三方项目不认识它 → 结果是 `UNKNOWN`（**不是** UNSUPPORTED，更不是解析失败）。
3. **URI 表达力必须显式建模**：`ss://` 对 reality 参数是 `partial` → 进 `losses[]`；
   原始链接 + 完整节点信息（含 reality 参数）都要保留，换内核后仍可用。
4. **绝不为它加特例 hack**：兼容性结论来自「feature 组合 × 内核能力表」的**组合判定**，
   三个变体不需要三份硬编码判断。
