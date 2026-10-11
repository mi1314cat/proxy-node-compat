# 注册表缺口清单（**有证据、但还不够写规则**）

这份清单存在的意义：把"我们知道这里有洞"和"我们有证据可以补"分开。

本项目对注册表的纪律是 **证据决定精度，禁止伪造版本边界** ——
没有证据的组合必须老老实实返回 `UNKNOWN`（`不猜`），而不是补一条"看起来合理"的规则。
所以下面每一条都**不**写成规则；它们等的是**证据**，不是工作量。

> 判断标准（缺一不可）：
> ① 官方文档或源码能指出字段/版本；② 真内核实测能复现；③ 能说清适用边界（版本区间或未知区间）。
> 只有①②不满足时，正确做法就是让它继续 UNKNOWN。

---

## 1. URI 表达力（`uri_rules`）

| # | 缺口 | 现在的行为 | 已有证据 | 还缺什么 |
|---|---|---|---|---|
| U-1 | `scheme=vless × 基础 feature`（`standard:tls` / `standard:transport.*` 等） | `uri` 层判 **UNKNOWN**（"没有覆盖该 scheme × feature 的 URI 表达力规则"） | X 列报告 §6.4：同步 vendored 副本后，xray×VLESS-WS_01 的 uri 层从 `SUPPORTED` 变成 `UNKNOWN` | 需要逐 feature 核 `vless://` 参数能否表达（如 `type=`/`security=` 与各家解析器实际读法），不能靠"vless 是万能的"这种直觉 |
| U-2 | `scheme=naive+https`（全部 feature） | `unknown_scheme`：表达力判不了 → UNKNOWN | SB 列：普通话路径因此丢 4 个节点（13→9） | naive 的 URI 形态各客户端支持度差异极大，需要至少两家客户端的真实解析行为 |
| U-3 | `scheme=shadowtls`（`standard:mux` / `standard:shadowsocks` / `standard:transport.tcp`） | 同上 | 同上 | 同上 |
| U-4 | `hysteria2 × 带宽`（`up`/`down`/`upmbps`/`downmbps`） | **完全没有规则** → 原生与 URI 两条路给客户端的速率提示不同，而没有任何一处说出来 | SB 列：原生 JSON 有 `up_mbps:100/down_mbps:500`，`hysteria2://` URI 里**一个带宽参数都没有**；X/M 的 URI 侧写了 `up/down`+`upmbps/downmbps` | 需要核清三家客户端分别读哪些参数名（M 认 `up/down`、SB 面板认 `upmbps/downmbps`），以及"没有该参数时内核用什么默认" |
| U-5 | `standard:mux` / `standard:naive` / `standard:shadowsocks` / `standard:tls` / `standard:transport.tcp` 五行的 (scheme × feature) 对应 | UNKNOWN | SB 列 `unregistered` 列表 | 同 U-1 |
| U-6 | `tuic × tls.alpn` | 出站 `tls` 里**没有 `alpn`**，而 URI 里有 | SB 列九宫格 §9.8：`mTUIC01-TLS` 真连报 `CRYPTO_ERROR 0x178: tls: no application protocol` | 需要"各客户端把 `alpn` 写在出站的哪个字段"的证据（三家字段名不同） |
| U-7 | `hysteria2 × 证书 pin` | 出站**没有任何 pin 字段**，而 URI 里有 `pinSHA256` / `pin` | 同上：`mHysteria202-TLS` 真连报 `x509: certificate signed by unknown authority` | 同上；另需核哪几家客户端认 URI 里的 pin |
| U-8 | `hysteria2 × down_mbps` | 出站只有 `up_mbps`，**没有 `down_mbps`** | 同上 | 与 U-4 同一族，一起补 |

| U-9 | **`trojan × REALITY 的 `fp` → 出站 `tls.utls`** | 普通话产物里三个 REALITY 出站**只有 trojan 那个 `tls.utls=None`**（vless/vmess 都有 `{enabled,fingerprint:chrome}`） | SB 列 §10：**原生取件失败→回退普通话时，整份配置 `sing-box check` FATAL**：`initialize outbound[6]: uTLS is required by reality client` | 需要"`trojan://…&security=reality&fp=…` 的 `fp` 该写进出站哪个字段"的证据 |

> **U-9 比 U-6/U-7/U-8 更重**：那三条是**单节点**连不上，U-9 是**回退路径整体不可用** ——
> 客户端"因为原生 404 而优雅回退到普通话"，拿到的却是一份起不来的配置。
> 也就是说：**降级路径本身也必须被验证**，不能只验"主路径 + 每节点"。

> U-6/U-7/U-8 的共同点值得单独说：**三条都是"URI 里写了、出站里没有、而 compat 的告警一个字没提"**。
> 它们的表现是**真连失败**（不是"少个参数"），所以正是"绝不静默丢失能力"最该覆盖的一类。
> 补它们不需要新机制 —— 需要的是"URI 参数 → 出站字段"的对应证据（哪家读哪个名字）。

## 2. 能力规则（`rules`）

| # | 缺口 | 说明 |
|---|---|---|
| C-1 | `anytls` / `vmess+REALITY` 在 **URI 侧**的损失 | 原生格式能表达、URI 装不下或解析器不读的组合，需要按 scheme×feature 补 `uri_rules`，不是补 `rules` |
| C-2 | mihomo 的 `vless × network=h2` | 需要先证"mihomo 的 vless 链接解析器怎么处理 `network=h2`"（`-t` 通过与否**证明不了**运行期行为，见 `research/empirical/`） |
| C-3 | `shadowtls` / `naive` 的**内核支持**边界 | 目前部分预留；缺真内核版本矩阵 |

## 3. 本清单的用法

* **不要**用"补一条规则"来让某个 UNKNOWN 消失 —— 那正是本项目最反对的做法。
* 有了证据就把它变成：`evidence[]` 一条 + `rules[]`/`uri_rules[]` 一条（带明确的
  `segments` 或 `unknown_range` + `transition: UNKNOWN`），并补测试。
* 每次真实验收里冒出来的 `unregistered` / `unknown_scheme` 都应该回到这张表里来 ——
  它们是"坑被看见了"，不是"任务没做完"。
