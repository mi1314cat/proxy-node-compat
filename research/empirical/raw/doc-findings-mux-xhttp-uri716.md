# Cross-kernel proxy compatibility — verbatim evidence collection

**Date accessed (all items): 2026-10-10 UTC.**
All quotes below are verbatim (Chinese kept in original). Where a claim could not be verified, it is marked **NOT FOUND**.

---

## Item 1 — Xray docs page `config/outbounds.html`: mux object + the "don't use mux.cool with XHTTP" sentence

### 1.0 URL status (checked 2026-10-10)

| URL | HTTP | note |
|---|---|---|
| `https://xtls.github.io/config/outbounds.html` | **404** | page no longer exists (site restructured) |
| `https://xtls.github.io/en/config/outbounds.html` | **404** | same |
| `https://xtls.github.io/config/outbound.html` | 200 | current ZH page = "出站代理（Mux、XUDP）" |
| `https://xtls.github.io/en/config/outbound.html` | 200 | current EN page = "Outbound Proxy (Mux, XUDP)" |
| source markdown: `docs/config/outbound.md`, `docs/en/config/outbound.md` in `XTLS/Xray-docs-next` | 200 | verified via raw.githubusercontent.com |

### 1.1 FINDING A — the XHTTP/mux.cool sentence is **NOT FOUND** on `config/outbounds.html` (current **or** historical)

Method: cloned `XTLS/Xray-docs-next` (full history, 1168 commits, earliest 2021-03-13) and grepped the working tree and all history.

* Current tree: the **only** docs page containing a mux.cool advice sentence is `docs/config/transports/grpc.md` (EN/ZH/RU). No `outbound.md` / `outbounds.md` in any language contains one.
* History (`git log --all -i -S "mux.cool"`, `-S "不要启用 mux.cool"`): the **only** file that ever contained `不要启用 mux.cool` is `docs/config/transports/splithttp.md`. No file matching an outbound(s) page ever gained such a sentence.

**Verdict: NOT FOUND on `config/outbounds.html`.** The user's premise is misplaced: the sentence lived on the **XHTTP (SplitHTTP) transport page**, section `## XmuxObject`, and was deleted on 2024-12-13.

### 1.2 FINDING B — where the sentence actually was (historical official docs), with section heading

* Historical file: `docs/en/config/transports/splithttp.md` / `docs/config/transports/splithttp.md`, page title/heading `# XHTTP (SplitHTTP)`, section heading `## XmuxObject`.
* Permanent links (parent commit of the removal, full sha `dcc39472dd7fd8772cdd453fdbc13176f5857ca8`):
  * `https://github.com/XTLS/Xray-docs-next/blob/dcc39472dd7fd8772cdd453fdbc13176f5857ca8/docs/en/config/transports/splithttp.md`
  * `https://github.com/XTLS/Xray-docs-next/blob/dcc39472dd7fd8772cdd453fdbc13176f5857ca8/docs/config/transports/splithttp.md`
* Provenance: EN sentence added in commit `cd99e25f1840901516f524854cc89bf77f0c0e29` ("SplitHTTP: Use xmux documentation from chinese document", 2024-09-19); ZH sentence added in `3b280cfb1a6bb474f08439d4e770b89cc6538eba` ("Add new xmux default value", 2024-10-16); **both removed** in `a6af837cb516717a42386e621f96fc4ffaa03cb9` ("XHTTP: Beyond REALITY", 2024-12-13).

EN, section `## XmuxObject` (verbatim):

```
## XmuxObject

<Badge text="v24.9.19+" type="warning"/>

Allows users to control the multiplexing behavior in h2 and h3. If not set, the default behavior is to multiplex all requests to one TCP/QUIC connection.

```json
{
  "maxConcurrency": 0,
  "maxConnections": 0,
  "cMaxReuseTimes": 0,
  "cMaxLifetimeMs": 0
}
```

Since the default is unlimited reuse, `xmux` actually limits this. It's not recommended to enable `mux.cool` at the same time.
```

ZH, section `## XmuxObject` (verbatim):

```
## XmuxObject

<Badge text="v24.9.19+" type="warning"/>

仅客户端，允许用户对 XHTTP 在 h2 与 h3 中的多路复用行为进行控制。使用该功能时不要启用 mux.cool。
```

ZH, same page, `maxConcurrency` bullet (verbatim):

```
> `maxConcurrency`: int/string

默认值为 0(即无限) 每个连接中复用的流的最大数量，连接中流的数量达到该值后核心会新建更多连接以容纳更多的流，类似于 mux.cool 的 concurrency.
```

EN, same page, `maxConcurrency` bullet (verbatim) — this is the historical EN "cannot be used together" wording:

```
> `maxConcurrency`: int | string

Default 0 = infinite. The maximum number of streams reused in each connection. After the number of streams in the connection reaches this value, the core will create more connections to accommodate more streams, similar to the concurrency of mux.cool. Mutually exclusive with `maxConnections`.
```

**relevance:** the "do not enable mux.cool with XHTTP" advice is official XTLS text, but it was on the XHTTP transport page (deleted in the 2024-12-13 rewrite), not on the outbounds page; `xmux` was explicitly introduced as the replacement for mux.cool on XHTTP.

### 1.3 FINDING C — where the XHTTP advice lives now: discussion #4113 (the official XHTTP "doc")

`https://xtls.github.io/en/config/transports/xhttp.html` renders only (verbatim, whole page body):

```
# XHTTP: Beyond REALITY

See[XHTTP: Beyond REALITY](https://github.com/XTLS/Xray-core/discussions/4113)Contributors(1)
- 

RPRX· 1 commits

[@RPRX](https://github.com/RPRX)
```

(Source markdown `docs/en/config/transports/xhttp.md` is exactly: `# XHTTP: Beyond REALITY` + `See [XHTTP: Beyond REALITY](https://github.com/XTLS/Xray-core/discussions/4113)`.)

So the authoritative current XHTTP text — including the mux.cool sentence — is discussion #4113 (see Item 2/3).

### 1.4 FINDING D — current official docs, analogous gRPC sentence (still live)

`https://xtls.github.io/en/config/transports/grpc.html` (source `docs/en/config/transports/grpc.md`, line 6) — verbatim:

```
gRPC (HTTP/2) has built-in multiplexing. It is not recommended to enable mux.cool when using gRPC and HTTP/2.
```

ZH equivalent (`docs/config/transports/grpc.md`, line 6) — verbatim:

```
gRPC（HTTP/2）内置多路复用，不建议使用 gRPC 与 HTTP/2 时启用 mux.cool。
```

### 1.5 The `mux` outbound object as documented today (EN + ZH), section `### MuxObject`

Sources: `https://raw.githubusercontent.com/XTLS/Xray-docs-next/main/docs/en/config/outbound.md`, `.../docs/config/outbound.md` (rendered at `https://xtls.github.io/en/config/outbound.html`, `https://xtls.github.io/config/outbound.html`), section `### MuxObject`.

EN (verbatim, all four fields):

```
The Mux function distributes data from multiple TCP connections over a single TCP connection. For implementation details, see [Mux.Cool](../development/protocols/muxcool.md). Mux is designed to reduce TCP handshake latency, not to increase connection throughput. Using Mux for watching videos, downloading, or speed testing usually has a negative effect. Mux only needs to be enabled on the client side; the server side adapts automatically. The second use of Mux is to distribute multiple UDP connections, i.e., XUDP.

`MuxObject` corresponds to the `mux` item in `OutboundObject`.

```json
{
  "enabled": true,
  "concurrency": 8,
  "xudpConcurrency": 16,
  "xudpProxyUDP443": "reject"
}
```

> `enabled`: true | false

Whether to enable Mux for forwarding requests. Default is `false`.

> `concurrency`: number

Maximum concurrent connections. Minimum `1`, maximum `128`. If omitted or set to `0`, it equals `8`. Values greater than `128` are treated as 128, because once a connection reaches the maximum reuse count of 128, it will no longer be assigned any new sub-connections.

This value represents the maximum number of sub-connections carried on a single TCP connection. For example, if `concurrency=8` is set, when the client issues 8 TCP requests, Xray will only issue one actual TCP connection, and all 8 requests from the client are transmitted over this TCP connection.

When the maximum sub-connection capacity of all Mux connections is fully occupied, the core will initiate new connections to carry sub-connections. If a large number of sub-connections are concurrent in a short time and subsequently decrease, the internal scheduler of the core will tend to distribute requests to 2 connections alternately and leave other connections idle, waiting for all their sub-connections to end naturally before closing them to save resources. If the total number of sub-connections continues to be lower than `concurrency` for a long time, after one of the connections reaches the maximum reuse count, the core will revert to a single connection state.

::: tip
When set to a negative number, such as `-1`, the Mux module is not used to carry TCP traffic.
:::

> `xudpConcurrency`: number

Use a new XUDP aggregation tunnel (i.e., another Mux connection) to proxy UDP traffic. Fill in the maximum number of concurrent sub-UoT. Minimum `1`, maximum `1024`.
If omitted or set to `0`, it will follow the same path as TCP traffic, which is the traditional behavior.

::: tip
When set to a negative number, such as `-1`, the Mux module is not used to carry UDP traffic. The proxy protocol's original UDP transmission method will be used. For example, `Shadowsocks` will use native UDP, and `VLESS` will use UoT.
:::

> `xudpProxyUDP443`: string

Controls how Mux handles proxied UDP/443 (QUIC) traffic:

- Default `reject`: Rejects traffic (browsers typically fall back to TCP HTTP2 automatically).
- `allow`: Allows traffic to go through the Mux connection.
- `skip`: Does not use the Mux module to carry UDP 443 traffic. The proxy protocol's original UDP transmission method will be used. For example, `Shadowsocks` will use native UDP, and `VLESS` will use UoT.
```

ZH (verbatim, mux intro + the two defaults, section `### MuxObject`):

```
Mux 功能是在一条 TCP 连接上分发多个 TCP 连接的数据。实现细节详见 [Mux.Cool](../development/protocols/muxcool.md)。Mux 是为了减少 TCP 的握手延迟而设计，而非提高连接的吞吐量。使用 Mux 看视频、下载或者测速通常都有反效果。Mux 只需要在客户端启用，服务器端自动适配。Mux 的第二个用途是分发多个 UDP 连接，即 XUDP。

`MuxObject` 对应 `OutboundObject` 中的 `mux` 项。

```json
{
  "enabled": true,
  "concurrency": 8,
  "xudpConcurrency": 16,
  "xudpProxyUDP443": "reject"
}
```

> `enabled`: true | false

是否启用 Mux 转发请求，默认值 `false`。

> `concurrency`: number

最大并发连接数。最小值 `1`，最大值 `128`。省略或者填 `0` 时都等于 `8`, 大于 `128` 的值都将视为 128, 因为当一个连接达到最大复用次数 128 后其将不会再被分配任何新的子连接。
```

**relevance:** `mux.enabled` default = `false`; `mux.concurrency` omitted/`0` ⇒ `8` (min 1, max 128, >128 clamped). Distinct from XHTTP `xmux.maxConcurrency` (default `"16-32"`), which is a different mechanism — hence "double-layer mux" being rejected by the maintainer (Item 2).

**URL(s) for Item 1**
* `https://xtls.github.io/en/config/outbound.html`, `https://xtls.github.io/config/outbound.html` (current; `.../outbounds.html` = 404)
* `https://raw.githubusercontent.com/XTLS/Xray-docs-next/main/docs/en/config/outbound.md`, `.../docs/config/outbound.md`
* `https://github.com/XTLS/Xray-docs-next/blob/dcc39472dd7fd8772cdd453fdbc13176f5857ca8/docs/en/config/transports/splithttp.md`
* `https://github.com/XTLS/Xray-docs-next/blob/dcc39472dd7fd8772cdd453fdbc13176f5857ca8/docs/config/transports/splithttp.md`
* `https://xtls.github.io/en/config/transports/grpc.html`

**relevance:** the docs' own advice is not on the page the request named; it moved from the SplitHTTP/XHTTP transport page into discussion #4113, and today's `outbound.html` only documents the legacy `mux` object.

---

## Item 2 — XTLS/Xray-core discussion #4113

**URL:** `https://github.com/XTLS/Xray-core/discussions/4113`
**Title (verbatim):** `XHTTP: Beyond REALITY`
**Author:** `RPRX` — API field `"author_association": "MEMBER"` ⇒ Xray-core project maintainer (GitHub UI shows the *Maintainer* + *Author* badges on his comments). Created `2024-12-05T04:45:06Z`; 353 comments; last updated `2026-09-03T05:59:50Z`.

### 2.1 Key statements in the article body (Chinese original, by RPRX — maintainer)

From section `## 快速上手指南`:

```
**XHTTP 默认有多路复用，延迟比 Vision 低但多线程测速不如它，除非测速前设了 `"maxConcurrency": 1`，参考 XMUX 小节。**
```

From section `## XMUX` (the mux.cool prohibition — this is the verbatim sentence):

```
**此外，使用 XHTTP 时不要启用 mux.cool，并且新版 Xray 服务端已有检查，只接受纯 XUDP。**
```

From section `## XMUX`, the quoted defaults rationale (author's own words, quoted in his article):

```
> - 我特地选了两个在 TLS 外不太能看出来的选项即 maxConcurrency 加 cMaxReuseTimes（而不是 maxConnections 加 cMaxLifetimeMs），并且这两个选项的默认值都是 range 取随机，最大程度上消除了潜在特征。
> - 我选择 maxConcurrency 而不是 maxConnections，就是为了防止连接数成为 fixed pattern，当然如果你喜欢后者也可以手动设置
```

```
> - XMUX 和 Nginx 的计数对象不同，maxConcurrency 和 cMaxReuseTimes 都是基于“被代理连接”计数的，只有 stream-one 会产生一个 HTTP 请求，而 stream-up 一个上行一个下行是两个，packet-up 则是 N 个
> - 不过我不确定 stream-one 会不会在某些情况下自动多产生一个 HTTP 请求，**还有我觉得追求一条连接复用到底没有太大的意义，因为你是运营商的话你也会限速、清理旧的连接，不然资源都被旧连接慢慢占完了，所以 XMUX 的默认参数就是限制复用+定期换连接**
```

From section `## 上下行分离` (on asymmetric upload/download xmux settings):

```
比如你可以再给上行设 `"maxConnections": 1`，给下行设 `"maxConcurrency": 1`，**实现上行的少量数据都走同一条底层连接，而下行的大量数据分散到不同的底层连接上，同时兼具反审查、低延迟、高速度**，有点像 Switch，搭配 Vision Seed 食用效果更佳。
```

### 2.2 Key maintainer comment in the same discussion (verbatim, with permalinks)

User `lxhao61`, 2024-12-06 — comment id `11486182`, `https://github.com/XTLS/Xray-core/discussions/4113#discussioncomment-11486182`:

```
我实际使用发现 mux 不开启，xmux 不配置（使用本链接文章中参数）连接最稳定。
```

**RPRX (maintainer, badge "Maintainer Author"), 2024-12-07 — comment id `11491701`, `https://github.com/XTLS/Xray-core/discussions/4113#discussioncomment-11491701`** (Chinese original; the first line of his comment body is a quote of lxhao61's text above):

```
我实际使用发现 mux 不开启，xmux 不配置（使用本链接文章中参数）连接最稳定。
双层 mux 肯定不合适，准备在 XHTTP 服务端禁掉了，XMUX 选那些参数是有原因的，也准备在文章中说明
```

(An English rendering posted later in the thread by user `ssmetall`, 2024-12-12 — **not** by RPRX — reads: `The double-layer mux is definitely not suitable, and I plan to disable it on the XHTTP server. There are reasons for choosing those parameters in XMUX, and I plan to explain them in the article.`)

A user question earlier in the same thread (`Smallthing`, 2024-12-06) uses `"mux": { "enabled": true, "concurrency": -1, "xudpConcurrency": 1, "xudpProxyUDP443": "reject" }` and asks: `这种配置算“关闭了mux.cool(我理解是tcp的mux)纯xudp”吗？…`

**relevance:** the "don't enable mux.cool with XHTTP" rule, and the "double-layer mux is inappropriate / will be disabled server-side" rationale, are stated by the Xray-core maintainer RPRX himself — in the discussion that the docs page `config/transports/xhttp.html` links to as the official XHTTP documentation.

---

## Item 3 — XHTTP `xmux` / `maxConcurrency` / `maxConnections` docs

There is **no** standalone XHTTP doc page with these fields: `docs/en/config/transports/xhttp.md` is a stub (quoted in Item 1.3) that points to discussion #4113, and the whole docs repo contains **no** occurrence of `xmux` outside `docs/about/news.md` (verified by grep over the full clone). The definition is therefore the `## XMUX` section of discussion #4113 — **NOT FOUND anywhere else in the official docs.**

**URL:** `https://github.com/XTLS/Xray-core/discussions/4113` — section heading `## XMUX`
**Date accessed:** 2026-10-10

Verbatim (Chinese original; this is the current, 2026 revision of the XMUX list):

```
- `maxConcurrency`：每条 TCP/QUIC 连接中最多同时存在多少代理请求，**连接中的代理请求数量达到该值后 core 会建立新的连接**，以容纳更多的代理请求。**XMUX 全为 0 时该项默认值为 "16-32"，每次随机。**

- `maxConnections`：最多同时存在多少条连接，**连接数达到该值前每个新的代理请求都会开启一条新的连接**，此后 core 会开始复用已有的连接。该值与 `maxConcurrency` 冲突，只能二选一。默认值 0，即不限制，支持填写范围，每次随机。

- `cMaxReuseTimes`：一条连接最多被复用几次，**复用该次数后将不会被分配新的代理请求**，将在内部最后一条代理请求关闭后断开。默认值 0，即不限制，支持填写范围，每次随机。

- `hMaxRequestTimes`：@xqzr 发现 Nginx 默认最多允许每条 TCP/QUIC 连接累计承载 1000 个 HTTP 请求，**XMUX 全为 0 时该项默认值为 "600-900" 取随机**，否则该项默认 0 即不限制。……

- `hMaxReusableSecs`：@xqzr 发现 Nginx 默认最多允许每条 TCP/QUIC 连接被复用一个小时，**XMUX 全为 0 时该项默认值为 "1800-3000" 取随机**，否则该项默认 0 即不限制。……

- `hKeepAlivePeriod`：H2 / H3 连接空闲时客户端每隔多少秒发一次保活包，默认 0，即 Chrome H2 的 45 秒，或 quic-go H3 的 10 秒。……
```

Additional verbatim statements from the same section:

```
即使你懒得研究也没事，**当这些值全为 0 时就会取到上面写的三个默认值，相当于隔段时间就换个新的 H2/H3 主连接，相当丝滑**，不会有 gRPC、HTTP 传输层始终复用同一条连接导致的“断流”体验。同样，这些参数都可以通过 `extra` 下发给客户端。

注：全不填也相当于全为零，会取到三个默认值，**但若填了任一项，其它项就没有默认值了，全都要自己填**，除前两项外其它项均可同时填。
```

The "cannot be specified at the same time" statement is therefore literally **`该值与 maxConcurrency 冲突，只能二选一。`** (for `maxConnections`). The older EN docs phrased the same rule as *"Mutually exclusive with `maxConnections`."* (Item 1.2). Note that for the current field set, only `maxConcurrency` ↔ `maxConnections` are mutually exclusive ("除前两项外其它项均可同时填" = apart from the first two, the others can all be set together).

The complete parameter example in the same article (verbatim, section `## 上下行分离`):

```
        "xmux": { // h2/h3 mainly, client only
            "maxConcurrency": "16-32",
            "maxConnections": 0,
            "cMaxReuseTimes": 0,
            "hMaxRequestTimes": "600-900",
            "hMaxReusableSecs": "1800-3000",
            "hKeepAlivePeriod": 0
        },
```

**relevance:** XHTTP's own multiplexing (`xmux`) mirrors mux.cool's `concurrency` knob but is a distinct, transport-level mechanism with randomized defaults; `maxConcurrency` and `maxConnections` are mutually exclusive ("只能二选一").

---

## Item 4 — VLESS/VMess share-link (URI) specification, discussion #716

**URL:** `https://github.com/XTLS/Xray-core/discussions/716`
**Title (verbatim):** `VMessAEAD / VLESS 分享链接标准提案` (title in the discussion list is the same; it is *not* titled "VLESS URI scheme")
**Author:** `DuckSoft` (`@DuckSoft (@Qv2ray)` per the spec's own §0), API `"author_association": "MEMBER"`; contributors listed: `@huyz`, `@rprx` (审校/review). Created `2020-12-19T16:21:16Z`, 76 comments, updated `2026-08-25T17:46:18Z`. Label: `enhancement`.
**Date accessed:** 2026-10-10

### 4.1 Complete list of query parameters defined by the spec (verbatim section headings from the discussion body)

The spec's structure is `protocol://$(uuid)@remote-host:remote-port?<protocol-specific fields><transport-specific fields><tls-specific fields>#$(descriptive-text)`.

Verbatim headings defining each parameter (all are query-string parameters except where noted):

```
##### 4.2.1 传输方式 `type` （@RPRX 修改于 2024-03-05，2024-06-18，2024-11-11）
##### 4.2.2 (VMess/VLESS) `encryption` （@RPRX 修改于 2026-1-18）
##### 4.2.3 (VLESS) `flow` （@RPRX 添加于 2026-1-18）
##### 4.3.1 底层传输安全 `security` （@RPRX 修改于 2023-03-19）
##### 4.3.4 (WebSocket) `path`
##### 4.3.5 (WebSocket) `host`
##### 4.3.6 (mKCP) `mtu` （@RPRX 添加于 2026-03-27）
##### 4.3.7 (mKCP) `tti` （@RPRX 添加于 2026-03-27）
##### 4.3.11 (gRPC) `serviceName` （@RPRX 修改于 2024-03-05）
##### 4.3.12 (gRPC) `mode`
##### 4.3.13 (gRPC) `authority` （@RPRX 添加于 2024-03-05）
##### 4.3.14 (HTTPUpgrade) `path` （@RPRX 添加于 2024-03-05）
##### 4.3.15 (HTTPUpgrade) `host` （@RPRX 添加于 2024-03-05）
##### 4.3.16 (XHTTP) `path` （@RPRX 添加于 2024-06-18，修改于 2024-11-11）
##### 4.3.17 (XHTTP) `host` （@RPRX 添加于 2024-06-18，修改于 2024-11-11）
##### 4.3.18 (XHTTP) `mode` （@RPRX 添加于 2024-11-11）
##### 4.3.19 (XHTTP) `extra` （@RPRX 添加于 2024-11-11）
##### 4.3.20 (Finalmask) `fm` （@RPRX 添加于 2026-01-31）
##### 4.4.0 `fp` （@RPRX 添加于 2023-02-01，修改于 2023-03-19）
##### 4.4.1 `sni` （@RPRX 修改于 2026-1-18）
##### 4.4.2 `alpn`
##### 4.4.3 `ech` （@RPRX 添加于 2025-07-26）
##### 4.4.4 `pcs` & `vcn` （@RPRX 添加于 2026-1-18，修改于 2026-2-2）
##### 4.4.5 (REALITY) `pbk` （@RPRX 添加于 2023-03-19，修改于 2025-07-22）
##### 4.4.6 (REALITY) `sid` （@RPRX 添加于 2023-03-19）
##### 4.4.7 (REALITY) `pqv` （@RPRX 添加于 2025-07-22）
##### 4.4.8 (REALITY) `spx` （@RPRX 添加于 2023-03-19）
```

Non-query components are also defined: `protocol` (§4.1.1, must be `vmess` or `vless`), `uuid` (§4.1.2), `remote-host` (§4.1.3), `remote-port` (§4.1.4), `descriptive-text` (§4.1.5, the `#` fragment).

Selected verbatim definitions that matter for cross-kernel work:

```
##### 4.2.1 传输方式 `type` （@RPRX 修改于 2024-03-05，2024-06-18，2024-11-11）

协议的传输方式。对应配置文件出站中 `settings.vnext[0].streamSettings.network` 的值。

当前的取值必须为 `tcp`、`kcp`、`ws`、`http`、`grpc`、`httpupgrade`、`xhttp` 其中之一，
分别对应 RAW、mKCP、WebSocket、HTTP/2/3、gRPC、HTTPUpgrade、XHTTP 传输方式。
```

```
##### 4.3.19 (XHTTP) `extra` （@RPRX 添加于 2024-11-11）

XHTTP 的 `extra`：https://github.com/XTLS/Xray-core/pull/4000

必须使用 `encodeURIComponent` 转义。
```

```
##### 4.3.1 底层传输安全 `security` （@RPRX 修改于 2023-03-19）

设定底层传输所使用的 TLS 类型。当前可选值有 `none`，`tls` 和 `reality`。
```

```
##### 4.4.5 (REALITY) `pbk` （@RPRX 添加于 2023-03-19，修改于 2025-07-22）

REALITY 的密码，对应配置文件中的 `password` 项目。
```

### 4.2 EXPLICIT ANSWER — is any multiplexing/mux/smux parameter defined? **NO.**

* The spec body defines **no** `mux`, `smux`, `multiplex`, `concurrency`, `max-streams` or equivalent URI parameter. There is no §4.x heading for one, and the body's JSON/YAML correspondences never mention mux.
* Mechanically verified: the full body text of discussion #716 contains **zero** occurrences of `mux`, `smux` or `multiplex` (case-insensitive). The rendered page (body + rendered comments) contains exactly **one** case-insensitive `mux` match, inside another user's comment about a *planned* feature, not a URI parameter:
  `计划中 XTLS 还会有些合并与优化，VLESS 则至少会有两类 UDP 增强：UDP over TCP 的 MUX 隧道、纯 UDP 多倍发包 + 长度填充`
  `smux`: 0 occurrences; `multiplex`: 0 occurrences.
* Multiplexing-related XHTTP settings are instead smuggled opaquely through the single `extra` parameter (a URL-encoded JSON blob) — see §4.3.19 above — and #4113 states the XHTTP share link contains only four XHTTP fields:
  `**`extra` 是 `host`、`path`、`mode` 以外的所有参数的原始 JSON 分享方案，当 `extra` 存在时，只有该四项会生效。且分享链接中只有这四项，GUI 一般也只有这四项……**`

### 4.3 Two caveats about the parameter list (important for exactness)

1. **Section numbering has gaps**: headings `4.3.2`, `4.3.3`, `4.3.8`, `4.3.9`, `4.3.10` no longer exist in the current body (removed by later edits), and `4.2.3` is used twice (for VMess `alterId`/`aid` and for VLESS `flow`).
2. **`seed` and `headerType` appear only in the §5 examples, not as defined sections** — verbatim from the body's §5 example block:
   ```
   # VLESS + mKCP + Seed
   vless://399ce595-894d-4d40-add1-7d87f1a3bd10@qv2ray.net:50288?type=kcp&seed=69f04be3-d64e-45a3-8550-af3172c63055#VLESSmKCPSeed
   # VLESS + mKCP + Seed，伪装成 Wireguard
   vless://399ce595-894d-4d40-add1-7d87f1a3bd10@qv2ray.net:41971?type=kcp&headerType=wireguard&seed=69f04be3-d64e-45a3-8550-af3172c63055#VLESSmKCPSeedWG
   ```
   Their definition sections are among the missing numbers, so `seed` is *used* in an example but not *defined* in the current revision. Likewise one example still shows legacy values `security=xtls` / `flow=rprx-xtls-splice` that contradict §4.3.1's current allowed set (`none`, `tls`, `reality`).

**v2rayN / v2rayNG docs:** not needed — #716 was available and is the canonical spec. (No fallback check performed.)

**relevance:** the Xray share-link standard has no multiplexing switch at all; a client cannot express "mux on/off" in a `vless://` URI, and XHTTP mux behaviour travels opaquely inside `extra`, which most GUIs never surface.

---

## Item 5 — sing-box official docs, `configuration/shared/multiplex`

> Note: the canonical URL is `https://sing-box.sagernet.org/configuration/shared/multiplex/` (EN) and `https://sing-box.sagernet.org/zh/configuration/shared/multiplex/` (ZH). `configuration/outbound/multiplex/` returns **404**.
> Provenance note: the sing-box docs source markdown is **not** public (`SagerNet/sing-box` has no `docs/` tree on `dev`; `*.md` raw paths 404), so the quotes below were extracted from the rendered official pages. Extraction normalises whitespace (the JSON blocks render one token per line); the protocol list is a real two-column table on the page and is reproduced as such here. Wording is verbatim; only layout is reconstructed.
**Date accessed:** 2026-10-10

### 5.1 Allowed `protocol` values and the default (verbatim, EN)

Section headings: `Multiplex` → `Outbound Fields` → `protocol`.

```
Outbound

{ 
 "enabled" : true , 
 "protocol" : "smux" , 
 "max_connections" : 4 , 
 "min_streams" : 4 , 
 "max_streams" : 0 , 
 "padding" : false , 
 "brutal" : {} 
}
```

```
protocol
Multiplex protocol.
Protocol 	Description
smux 	https://github.com/xtaci/smux
yamux 	https://github.com/hashicorp/yamux
h2mux 	https://golang.org/x/net/http2
h2mux is used by default.
```

ZH (verbatim, same section):

```
protocol
多路复用协议
协议 	描述
smux 	https://github.com/xtaci/smux
yamux 	https://github.com/hashicorp/yamux
h2mux 	https://golang.org/x/net/http2
默认使用 h2mux。
```

So the allowed set is exactly **`smux` | `yamux` | `h2mux`**, documented default **`h2mux`**. No `mux.cool`.

### 5.2 Statement about `mux.cool` being unsupported — **NOT FOUND in the official docs**

* The `Multiplex` page (EN + ZH) contains **zero** occurrences of `mux.cool` / `cool` (verified on the fetched page text).
* Whole-site verification: the sing-box sitemap contains exactly 300 URLs (150 EN + 150 ZH). A page-by-page fetch of **all 300 pages** (150 EN and 150 ZH) found **zero** occurrences of `mux.cool` on any documentation page.
* The closest official-ish statement is a **GitHub issue, not documentation** — `https://github.com/SagerNet/sing-box/issues/1876`, title `[Bug]: Incompatibility with servers using Mux.Cool` (2024-06-17). Verbatim:
  * Issue body by `radiumatic` (user), 2024-06-17:
    ```
    sing-box clients (and sing-box used as a client, in general) cannot connect to servers running xray-core with multiplex that only support the Mux.Cool algorithm.
    ```
  * `Mahdi-zarei` (**CONTRIBUTOR** to sing-box), 2024-06-18:
    ```
    Xray clients cannot connect to sing-box with mux. The Mux cool protocol is not compatible with the sing-box's mux protocols.
    ```
  * `dyhkwong` (**CONTRIBUTOR**), 2024-06-27:
    ```
    Support for vmess/vless mux.cool is server only, and it exists only for compatibility reason. Don't use that ugly thing in real life. Mux.cool server is compatible with client without mux.cool.
    ```
  These are issue comments, **not** official documentation — the docs themselves make no mux.cool statement.

### 5.3 Which side must support it (verbatim)

The page documents **separate inbound (server) and outbound (client) field sets** — i.e. both sides implement it:

```
Inbound Fields
enabled
Enable multiplex support.
padding
If enabled, non-padded connections will be rejected.
brutal
See TCP Brutal for details.
Outbound Fields
enabled
Enable multiplex.
```

```
padding
Info
Requires sing-box server version 1.3-beta9 or later.
Enable padding.
```

ZH equivalents (verbatim): `入站字段 / enabled / 启用多路复用支持。` · `出站字段 / enabled / 启用多路复用。` · `需要 sing-box 服务器版本 1.3-beta9 或更高。`

Conflict statements (bonus, verbatim EN from the same page):

```
max_connections
Maximum connections.
Conflict with max_streams .
min_streams
Minimum multiplexed streams in a connection before opening a new connection.
Conflict with max_streams .
max_streams
Maximum multiplexed streams in a connection before opening a new connection.
Conflict with max_connections and min_streams .
```

**relevance:** sing-box has no mux.cool compatibility mode and never mentions it in the docs; `protocol` = smux/yamux/h2mux only (default h2mux). Multiplex is documented on both inbound (server) and outbound (client) sides, whereas mux.cool is client-only in practice — an asymmetry that breaks mixed-kernel setups.

---

## Item 6 — mihomo (MetaCubeX) docs: `smux` protocols + `reality-opts` on `ss`

Docs source repository: `MetaCubeX/Meta-Docs` (`docs/config/proxies/…`); rendered at `https://wiki.metacubex.one/...`.
**Date accessed:** 2026-10-10

### 6.1 `smux` allowed `protocol` values and default (verbatim, EN)

**URL:** `https://wiki.metacubex.one/en/config/proxies/` (page: *Common Fields*), raw source `https://raw.githubusercontent.com/MetaCubeX/Meta-Docs/main/docs/config/proxies/index.en.md` (the `## smux` section).

```
## smux

sing-mux, only for protocols using TCP transport.

### smux.enabled

Whether to enable multiplexing.

### smux.protocol

Multiplexing protocol. The following protocols are supported. Default: `h2mux`.

| Protocol | Description                            |
|----------|----------------------------------------|
| `smux`   | <https://github.com/xtaci/smux>        |
| `yamux`  | <https://github.com/hashicorp/yamux>   |
| `h2mux`  | <https://golang.org/x/net/http2>       |

### smux.max-connections

Maximum number of connections.

Conflicts with `max-streams`.

### smux.min-streams

Minimum number of multiplexed streams in a connection before opening a new connection.

Conflicts with `max-streams`.

### smux.max-streams

Maximum number of multiplexed streams in a connection before opening a new connection.

Conflicts with `max-connections` and `min-streams`.
```

ZH (verbatim, `https://raw.githubusercontent.com/MetaCubeX/Meta-Docs/main/docs/config/proxies/index.md`):

```
## smux

sing-mux，仅限使用 tcp 传输的协议

### smux.enabled

是否启用多路复用

### smux.protocol

多路复用协议，支持如下协议，默认使用 `h2mux`

| 协议     | 描述                                  |
|---------|--------------------------------------|
| `smux`  | <https://github.com/xtaci/smux>      |
| `yamux` | <https://github.com/hashicorp/yamux> |
| `h2mux` | <https://golang.org/x/net/http2>     |
```

**Documented default protocol: `h2mux`. Allowed: `smux`, `yamux`, `h2mux`.** No mux.cool value. (Note the mihomo CRS/legacy `ss` options block for ShadowsocksR at the end of the `ss` page separately exposes `smuxver`, `smuxbuf`, `framesize`, `streambuf` — those are ShadowsocksR protocol parameters, not the mux protocol selector.)

### 6.2 Is `reality-opts` documented on the `ss` (shadowsocks) proxy type? **NO.**

* **URL checked:** `https://wiki.metacubex.one/en/config/proxies/ss/` and `https://wiki.metacubex.one/config/proxies/ss/`; raw sources `docs/config/proxies/ss.en.md`, `docs/config/proxies/ss.md`.
* Result: **0 occurrences** of `reality` (and of `reality-opts`) in both the EN and ZH `ss` pages (case-insensitive grep over raw markdown and rendered HTML).
* The EN `ss` page's complete config example (verbatim) contains only:

```
proxies:
- name: "ss1"
  type: ss
  server: server
  port: 443
  cipher: aes-128-gcm
  password: "password"
  udp: true
  udp-over-tcp: false
  udp-over-tcp-version: 2
  ip-version: ipv4
  plugin: obfs
  plugin-opts:
    mode: tls
  smux:
    enabled: false
```

  (`ss` supports `plugin` values `obfs`/`v2ray-plugin`/`gost-plugin`/`shadow-tls`/`restls`/`kcptun`/`jls` and `smux` — but no TLS/REALITY option block.)

### 6.3 Where `reality-opts` **is** documented

Repository-wide grep over `MetaCubeX/Meta-Docs` (`grep -rl "reality-opts" docs`), files with the term:
* `docs/config/proxies/vless.{md,en.md,ru.md}` (1 occurrence each — in the YAML example, `reality-opts:` with `public-key` / `short-id`)
* `docs/config/proxies/trojan.{md,en.md,ru.md}` (1 each)
* `docs/config/proxies/vmess.{md,en.md,ru.md}` (1 each)
* `docs/config/proxies/tls.{md,en.md,ru.md}` (the shared **TLS Configuration** fields page, 5 occurrences)
* `docs/config/proxies/transport.{md,en.md,ru.md}` (2 occurrences, commented example under an XHTTP example)

i.e. as a proxy-type field it is documented **only for vless / trojan / vmess** (plus the shared TLS-fields page), consistent with the `client-fingerprint` note on the same page — verbatim from `tls.en.md`:

```
## client-fingerprint

Client uTLS fingerprint, applicable only to [`VMess`](./vmess.md)/[`VLESS`](./vless.md)/[`Trojan`](./trojan.md)/[`AnyTLS`](./anytls.md) protocols.
```

```
## reality-opts

Configuration for reality; if not empty, reality will be enabled.
```

**Bonus, highly relevant to this research project** — the same mihomo TLS page documents an intentional incompatibility with current Xray-core (verbatim, `https://raw.githubusercontent.com/MetaCubeX/Meta-Docs/main/docs/config/proxies/tls.en.md`):

```
!!! warning
    Due to xray-core's deliberately [incompatible behavior](https://github.com/XTLS/Xray-core/commit/af7eb68028732a8ee3c0e5d6ab2b8a657bb2e770), we will not consider compatibility with xray v26.7.11+ versions. If it cannot be used, replace the server (such as [mihomo native listener](../inbound/listeners/index.md), sing-box, or an older xray-core version) or use another protocol instead.
```

and the sub-fields:

```
### reality-opts.public-key

Public key corresponding to the reality server's private key.

### reality-opts.short-id

One of the server's short IDs.

### reality-opts.support-x25519mlkem768

Support for X25519-MLKEM768 key exchange.
```

**relevance:** mihomo's mux protocol selector (`smux.protocol`) also has no mux.cool; `reality-opts` is documented only on vless/trojan/vmess (and not on `ss`), while mihomo explicitly refuses compatibility with Xray-core v26.7.11+ REALITY behaviour — directly relevant to cross-kernel REALITY compatibility.

---

## Staged evidence files (workspace)

| File | Content |
|---|---|
| `evidence/outbound_en.md` | raw EN Xray outbound doc (MuxObject) as fetched 2026-10-10 |
| `evidence/outbound_zh.md` | raw ZH Xray outbound doc (MuxObject) as fetched 2026-10-10 |
| `evidence/xray_splithttp_EN_pre2024-12-13.md` | full EN XHTTP (SplitHTTP) page as of `a6af837^` (contains the deleted mux.cool sentence) |
| `evidence/xray_splithttp_ZH_pre2024-12-13.md` | full ZH XHTTP (SplitHTTP) page as of `a6af837^` |
| `evidence/mihomo_proxies_common_en.md` | mihomo Common Fields page source (smux section) |
| `evidence/singbox_multiplex_en.txt` / `singbox_multiplex_zh.txt` | sing-box Multiplex page text (EN/ZH) |
