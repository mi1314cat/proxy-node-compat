# hysteria2 走 IPv6 不通 —— 通配绑定 UDP 入站的回包源地址被 WARP 策略路由夺走

> 调查时间：2026-10-11 / 12（本地 CST）
> 调查对象：RN（`ssh rn`，107.173.154.178，**授权测试服**）+ CC（`ssh CC`，192.168.1.178，客户端）
> 触发问题：**sing-box 内核建的 hysteria2 节点，只有走 IPv6 不通**；同一节点走 IPv4 完全正常；服务器上另外 17 个节点无论 v4/v6 都正常。
> 相关脚本：`catmi-warp3`（RN 上 `/usr/local/bin/catmi-warp3`，243894 字节，2026-09-16）；GitHub 侧 `mi1314cat/One-click-script` → `warp/catmi-warp3.sh`
> **本次已对上一版文档做了一处重要更正**（规则归属），见 §0 末尾与 §3.3。

---

## 0 · 一句话结论

RN 的策略路由对 **IPv4 和 IPv6 采用了相反的默认策略**：

```
v4  32765: not from all fwmark 0xc350 lookup main    ← 未打标 → 直连（WARP 是"白名单 opt-in"）
v6  32765: not from all fwmark 0xc350 lookup cw3     ← 未打标 → WARP（cw3 的默认路由是 dev warp）
```

而 **hysteria2 的回包是从"通配地址监听 socket"发出的**：这类 socket 在回包时**没有指定源地址**，
源地址要由**路由决策**来定。于是：

1. 内核问路由表"发往客户端 `2409:8a20:…` 该用什么源？"
2. 源地址此刻**还不知道** ⇒ 按源地址分流的保护规则 `32762: from 2001:470:c:cf::/64 lookup main` **永远匹配不上**；
3. 掉进 `32765` ⇒ 走 `cw3` ⇒ `dev warp` ⇒ 源地址被选成 **`2606:4700:110:822e:a614:76df:2b40:41fb`**（WARP 的地址）；
4. 客户端 QUIC 只认自己发过去的地址 `2001:470:c:cf:bf47:d1e0:cd4d:c6db`，回包源不对 ⇒ **直接丢弃** ⇒ 握手永远完不成 ⇒ 15 秒超时。

**抓包实证（同进程内 hy2/tuic 双入站，两者都 `listen: "::"`）**：

```
hy2  :35926   he-ipv6 In  2409:8a20:…:30777 > 2001:470:c:cf:bf47:….35926
              warp    Out 2606:4700:110:822e:a614:76df:2b40:41fb.35926 > 2409:8a20:…:30777   ← ★ 源被夺走
tuic :35930   he-ipv6 In  2409:8a20:…:29480 > 2001:470:c:cf:bf47:….35930
              he-ipv6 Out 2001:470:c:cf:bf47:d1e0:cd4d:c6db.35930 > 2409:8a20:…:29480           ← ★ 源正确
```

**为什么只有这一个节点？** 因为**全服务器上只有它在 IPv6 上监听**：

| 内核 | 同类 UDP 节点 | 监听地址 |
|---|---|---|
| **sing-box**（`-C /root/catmi/sing-box/config`） | **hysteria2 :25926** | **`::`（v4+v6 通配）← 全服务器唯一** |
| sing-box | tuic :25930 | `::`（协议栈自己回填目的地址，**免疫**，见 §2.3） |
| mihomo（`/root/catmi/mihomo/conf/config.yaml`） | hysteria2 :20534、tuic :20535 | **`0.0.0.0`（纯 IPv4）** |
| xrayls（`-confdir /root/catmi/xray/conf`） | hysteria :15110 / 40784 / 31879 / 29604 | **`0.0.0.0`（纯 IPv4）** |

⇒ 另外两个内核的 hysteria2/hysteria 节点**根本不接受 IPv6 连接**，所以永远遇不到这个失效模式。
**它们是"没监听"，不是"没问题"** —— 哪天把它们的 `listen` 改成 `::`，同样的失效会立刻出现（§7.3）。

> **对上一版的更正**：上一版把 `not fwmark 0xc350 → cw3` 归因于 **fscarmen warp-go 注入**。
> 这是**错的**。经查 `catmi-warp3` 第 1892–1938 行，**这条规则是 V3 自己装的**，而且是**按地址族参数化**的
> （`[[ "$f" == "6" && "$DEFAULT_OUTBOUND_V6" == "warp" ]]`）—— 这恰好解释了 v4/v6 那条相反的行为。
> 详见 §3.3 的三条独立佐证。

---

## 1 · 现象与差分实测（从 CC 用真 sing-box 1.14.2 客户端）

| 节点 | 协议 / 传输 | 走 IPv4 `107.173.154.178` | 走 IPv6 `2001:470:c:cf:bf47:d1e0:cd4d:c6db` |
|---|---|---|---|
| anytls01-TLS | TCP + TLS | ✅ 204 | ✅ 204 |
| tuic01-TLS | **UDP / QUIC** | ✅ 204 | ✅ 204 |
| **hysteria2-01-TLS** | **UDP / QUIC** | ✅ **204**（出口 `104.28.201.80`） | ❌ **000**（`context deadline exceeded`，15s） |

- 服务端全部正常：`sing-box check` 通过、`ss -lunp` 里 `*:25926` 在听、防火墙放行、证书有效（`/home/web/certs/moontv.6896698.xyz_cert.pem`，到期 2027-01）。
- 同一份客户端参数（密码 / `obfs=salamander` / `sni` / `alpn=h3`）**只换服务器地址**，IPv4 就 204 ⇒ **hy2 自己的配置没有错**。
- **端口无关**：在备用端口 35926 上复现同一现象（§3.5）。

---

## 2 · 根因

### 2.1 v4 / v6 策略相反，而且这是同一份配置产生的

`/etc/catmi/warp3/config/main.conf`：

```
DEFAULT_OUTBOUND_V4=warp
DEFAULT_OUTBOUND_V6=warp
```

**两个都写着 warp，装出来的规则却是相反的** —— 因为脚本里那条规则带了地址族条件
（`/usr/local/bin/catmi-warp3` 第 1904–1909 行，原文照抄）：

```bash
# C 规则按 v6 默认方向参数化:
#   V6=warp: 未标 → cw3 (v6 默认走 WARP; 关键: 让决策期就选 warp 接口的合法源地址,
#            否则 main 选 he 源 → reroute 后源不变 → CF 拒绝非账号源 → v6 超时)
#   其余:    未标 → main (原生)
local c_dst="main"
[[ "$f" == "6" && "$DEFAULT_OUTBOUND_V6" == "warp" ]] && c_dst="$TABLE_NAME"
```

`DEFAULT_OUTBOUND_V4=warp` **在这条规则上完全不生效**（`f == "6"` 把它挡掉了），
所以 v4 侧"未打标 → main"、v6 侧"未打标 → cw3"。

### 2.2 决策期没有源地址，按源地址的保护就是循环依赖

脚本第 1910–1912 行的注释说明作者**知道这个坑**，并做了保护：

```bash
# v6: 原生 v6 上游接口 (he-ipv6 等) 的全局地址段 → main, 优先级压在前置 (need-3) 之前。
# 入站服务回包源是这些地址, 若被 C 规则抓进 WARP, CF 拒收非账号源 → 入站死。
# 必须在决策期就命中原口; 老版本位置一并清理。
```

装出来的就是 `32762: from 2001:470:c:cf::/64 lookup main`。
**它救得了回包源地址已知的情况，救不了"源地址等着路由来定"的通配 UDP socket**：

> 规则要匹配 `from 2001:470:c:cf::/64`，可这个包**正因为源地址还没确定才来查路由** ——
> 谁先谁后是个死循环。于是它必然落到 `32765`，源地址被选成 WARP 的。

这是**结构性缺口**，不是"保护装漏了"。

### 2.3 为什么 TCP 和 tuic 都没事 —— 同进程对照实验（本轮新增，关键）

在 RN 上起了**一个临时 sing-box 进程**，里面放**两个入站**：hy2 :35926 与 tuic :35930，
**同一个进程、同一份证书、同样的 `listen: "::"`**，从同一个客户端打：

| 入站（同进程） | 绑定 | 结果 |
|---|---|---|
| hysteria2 :35926 | `::` | ❌ **000**（15s 超时） |
| tuic :35930 | `::` | ✅ **204**（出口 `104.28.201.80`） |

⇒ **差异不在绑定地址、不在进程/服务环境、不在证书、不在端口**，而在**协议栈自己的发送路径**：

* **TCP 类（anytls / vless / trojan / vmess / naive / shadowtls）**：accept 出来的连接 socket 本地地址已固定，
  回包源地址取自 socket 而不是路由 ⇒ **天然免疫**。
* **tuic**：回包时**带上了收到包时的目的地址**（`IPV6_PKTINFO` 语义），源地址正确 ⇒ 免疫。
* **hysteria2**：回包**没有指定源地址** ⇒ 交给内核按路由挑 ⇒ 被 `cw3` 抓走 ⇒ 源地址漂移。

> **诚实标注**：上面三行的**行为差异是实测的**（同进程对照 + 抓包）；
> "tuic 回填了目的地址、hy2 没回填"是**对实测行为最合理的机制解释**，
> **我没有逐行核对上游 sing-box 源码**（见 §8.1）。

### 2.4 自锁：conntrack / mangle 那一层为什么也救不回来

源地址错了以后，事情会**自我锁死**（这是一次尝试里出现的**两条** conntrack 表项）：

```
① src=2409:8a20:…:2(CC) dst=2001:470:c:cf:bf47:… sport=44917 dport=25926 [UNREPLIED]
   回程元组 src=2001:470:c:cf:bf47:… → mark=4   ← 入站打标成功
② src=2606:4700:110:822e:…(WARP) dst=2409:8a20:…:2 sport=25926 dport=44917 [UNREPLIED]
   回程元组 src=2409:8a20:…:2 → mark=3          ← 回包换了源，另起一条
```

mangle 计数器（一次 hy2 尝试前后差值）：

```
hy2  尝试: +2 包 → MARK set 0x3（兜底送 WARP）; connmark match 0x4/0x4 命中 0
tuic 尝试: +20 包 → connmark match 0x4/0x4 → MARK set 0x4 → RETURN
INPUT -i he-ipv6 CONNMARK --set-xmark 0x4/0x4: hy2 尝试 +12 包（打标本身是成功的）
```

⇒ **入站打标成功，但回包那一步的 connmark 匹配永远不命中**（回包 tuple 已经不是 ① 了），
落到兜底 `MARK 0x3`，继续走 WARP。**源地址错 → conntrack 对不上 → 保护用不上 → 源地址继续错。**

这一层是 §2.2 那个结构性缺口的**后果**，不是独立原因。

---

## 3 · 证据清单（每一步都有当次原始输出）

### 3.1 抓包：回包源地址被换掉

**（a）生产节点对照**（`tcpdump -ni any 'udp and (port 25926 or port 25930)'`）：

```
he-ipv6 In  2409:8a20:…:29655 > 2001:470:c:cf:bf47:….25926
warp    Out 2606:4700:110:822e:a614:76df:2b40:41fb.25926 > 2409:8a20:…:29655   ← hy2：源被夺走
he-ipv6 In  2409:8a20:…:65154 > 2001:470:c:cf:bf47:….25930
he-ipv6 Out 2001:470:c:cf:bf47:d1e0:cd4d:c6db.25930 > 2409:8a20:…:65154         ← tuic：源正确
```

**（b）同进程对照**（§2.3 的临时实例，两个入站都 `listen: "::"`）：
- 端口 35926：`he-ipv6 In` 若干 → **`warp Out` 源 `2606:4700:110:822e:…`**
- 端口 35930：**`he-ipv6 In` 15 包 / `he-ipv6 Out` 15 包**，无任何 warp 出口报文

### 3.2 路由决策期：内核自己说会这么选

```console
$ ip -6 route get 2409:8a20:1c93:5460::2 from ::
  2409:8a20:1c93:5460::2 from :: dev warp table cw3 src 2606:4700:110:822e:… metric 1024

$ ip -6 route show table cw3
  default dev warp
```

### 3.3 规则归属：是 V3 装的，不是 fscarmen（对上一版的更正）

三条独立佐证：

1. **优先级算术完全吻合**。脚本第 1937 行是 `rule add prio $((need - 1)) not fwmark 0xc350 lookup "$c_dst"`，
   其中 `need` 取"最小 prio 的、不含 fwmark/oif 的 `lookup main` 规则"（第 1893–1896 行）。
   当前该值为 `32766`（`from all lookup main`），于是 C 规则正好落在 **32765**；
   同一批"前置规则"的 `oif warp → cw3` 落在 `need-3`＝**32763**、`fwmark 0x3 → cw3` 落在 `need-2`＝**32764**。
   **三条规则的位置与脚本算术一一对应**：

   ```
   0:     from all lookup local
   17:    from all fwmark 0x4/0x4 lookup main       ← V3 的 IMARK 入站保护
   50:    from all oif he-ipv6 lookup main          ← V3 的 bind 保护
   32762: from 2001:470:c:cf::/64 lookup main       ← V3 的入站保护 (need-4)
   32763: from all oif warp lookup cw3              ← V3 (need-3)
   32764: from all fwmark 0x3 lookup cw3            ← V3 (need-2)
   32765: not from all fwmark 0xc350 lookup cw3     ← V3 (need-1) ★
   32766: from all lookup main
   ```

2. **地址族条件行为吻合**。v4 侧同一条规则是：

   ```
   v4  32765: not from all fwmark 0xc350 lookup main
   ```

   同样是 `need-1`（v4 的 `need` 也是 32766），但目标是 **`main`** —— 与 `[[ "$f" == "6" && "$DEFAULT_OUTBOUND_V6" == "warp" ]]` 完全一致。
   如果是 fscarmen 注入的，v4/v6 不会出现这种"正好按地址族相反"的形态。

3. **脚本自带说明**。第 1905–1907 行注释原文："V6=warp: 未标 → cw3 (v6 默认走 WARP…)"，
   第 1938 行的日志串是 `前置规则 (fam$f): oif/fwmark→cw3 + 未标→$c_dst @ prio …` —— 装的就是这一组。

> fscarmen warp-go 的冲突确实存在，但脚本第 1856/1861 行说得很清楚，它注入的是
> `not fwmark 0xc350 lookup 50000`（**另一张表**）—— 与本题这条 `→ cw3` 不是同一条。

### 3.4 入站保护"装了、也在打标，但救不了"

见 §2.4 的计数：`INPUT -i he-ipv6 CONNMARK --set-xmark 0x4/0x4` 对 hy2 尝试 **+12 包**（打标成功），
而回包侧 `connmark match 0x4/0x4` **命中 0 次**。⇒ 是"保护被绕过"，不是"没装保护"。

### 3.5 A/B 实验：全部在**备用端口 + 临时进程**上做，生产零影响

| # | 配置 | 从 CC 走 IPv6 | 说明 |
|---|---|---|---|
| A | `listen: "::"`，无任何额外规则 | ❌ 000 | 基线复现 |
| B | `listen: "2001:470:c:cf:bf47:d1e0:cd4d:c6db"` | ✅ 204 | 绑具体地址即可 |
| C | 同 A，另加 `sport 35926 lookup main` | ✅ **204**（出口 `104.28.201.80`） | §4-C |
| D | 同 A，撤掉该规则再测 | ❌ 000 | **因果闭合（A→C→A）** |

**端口与本题无关**：A 用 35926、B 用 35927，差别只在 `listen`。

---

## 4 · 已验证的修法（含验证状态与部署风险）

| # | 做法 | 验证状态 | 部署风险 |
|---|---|---|---|
| **A** | **这条链接改走 IPv4**（面板「客户端产物 → 9) 切换产物地址族」；或只把 hy2 这条链接的地址改成 `107.173.154.178`） | ✅ 已实测（hy2/anytls/tuic v4 全 204） | 无。但等于放弃该节点的 IPv6 |
| **B** | **hy2 入站 `listen` 绑具体 IPv6 地址**，再加一个 `0.0.0.0` 的同端口入站保留 v4 | ✅ 已实测（v6 204 + **v4 204**），**已应用在 RN 生产节点上** | ⚠ **面板重建这个节点时会被覆盖回 `::`**，v6 会**静默**再次失效（v4 照常，不易发现） |
| **C** | **按源端口在路由决策期改走原生表**：`ip -6 rule add prio 32761 sport <hy2端口> lookup 100` + 表 100 里放 he-ipv6 的默认路由 | ✅ 已实测 A/B/A（000→204→000），区间写法 `sport 35920-35930` 也实测通过 | ⚠ 规则**重启即失效**，需配套 systemd 单元；**必须用独立表**，原因见 §5 |
| **D** | 把 `not fwmark 0xc350` 的 v6 目标从 `cw3` 改回 `main` | ⚠ **未实测**（从路由表推导可行） | ❗ 这会**改变 v6 的默认走向**（原本"未打标 → WARP"是 V3 有意为之，注释第 1905 行写着 CF 只认账号源），**影响面是全局 v6 出口，需你拍板** |
| **E** | **面板侧修法**：让面板生成 hy2 节点时直接写具体监听地址（+ v4 第二个入站），即把 B 变成"面板的默认产物" | ⚠ **未实现**（属于 `sing-box-core` 面板改动） | 需要改面板模板并重建节点；但这是**唯一从源头消除**的办法 |

**推荐组合**：**先 C（三台服务器立刻可用、不碰节点配置）→ 再 E（治本）。**
B 是应急，**单独用会留一颗雷**（面板一重建就复发）。

**C 的可复制片段**（`/usr/local/sbin/catmi-inbound-reply-source`）：

```bash
#!/bin/bash
# 让"通配绑定 UDP 入站"的回包在路由决策期就拿到本机原生源地址。
set -u
TABLE_ID=100
PORTS="25925-25941"     # 各内核节点端口段；用实际配置核对，别照抄
UP=he-ipv6              # v6 原生上游接口
GW=$(ip -6 route show default dev "$UP" 2>/dev/null \
     | awk '{for(i=1;i<=NF;i++) if($i=="via") print $(i+1)}' | head -1)
[ -n "$GW" ] || { echo "找不到 $UP 的默认网关"; exit 1; }
ip -6 rule del prio 32761 2>/dev/null
ip -6 route replace default via "$GW" dev "$UP" table "$TABLE_ID"
ip -6 rule add prio 32761 sport "$PORTS" lookup "$TABLE_ID"
echo "ok: sport $PORTS → table $TABLE_ID (via $GW dev $UP)"
```

配套单元（`/etc/systemd/system/catmi-inbound-reply-source.service`）：

```ini
[Unit]
Description=catmi: inbound reply source fix (wildcard UDP over IPv6)
After=network-online.target catmi-warp3-restore.service
Wants=catmi-warp3-restore.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/catmi-inbound-reply-source

[Install]
WantedBy=multi-user.target
```

**注意设计取舍（试过、不行，写下来免得再试）**：
**不要**用 `... lookup main` 这种朴素写法 —— 会在下次开机被 V3 反超（§5.1）。

---

## 5 · 部署时必须知道的坑

### 5.1 V3 的"need 计算"会**追着**你新加的 `lookup main` 规则跑（实测）

脚本第 1893–1896 行把 `need` 定义为"**最小 prio 的、不含 `fwmark|oif` 的 `lookup main` 规则**"，
然后把 C 规则插到 `need-1`（**正好插在你前面**）。所以：

* 你加 `prio 32761 sport … lookup main` → 下次开机 `need` 变成 32761 → **C 规则装到 32760 → 你的规则被反超 → 修法失效**。
* **实测确认**：模拟它的取数逻辑，`need` 确实从 32766 变成 32761。
* 想靠"规则里带 `fwmark` 字样"骗过它的 `grep -vE 'fwmark|oif'`：**也不行** ——
  `ip -6 rule add … fwmark 0/0 lookup main` 虽然被接受，但 iproute2 **打印时把 `fwmark 0/0` 丢掉了**，
  `ip -6 rule show` 出来仍是 `from all sport 35926 lookup main`，照样被算进 `need`。

**⇒ 结论：要么用独立路由表（`lookup 100`，字面上不含 `lookup main`，已实测 `need` 保持 32766），
要么直接改 V3 脚本**（把这类规则加进第 1892–1894 行的排除列表，和它处理自己那条 `from <段> lookup main` 的方式一样）。

### 5.2 B 方案会被面板覆盖

`hysteria2-01.json` 是面板生成的产物。下次在面板里重建/编辑这个节点，`listen` 会变回 `::`，
**v6 立刻静默失效而 v4 正常**。要么改面板模板（E），要么叠一层 C 兜底。

### 5.3 临时实例一定要用 PID 精确清理

`pkill -f "<关键词>"` 会匹配到**承载这条命令的 ssh/bash 自身**（本次又踩了一次，
在 CC 上把清场命令自己杀了，导致 `/tmp` 残留）。用 `ps -eo pid,args | grep '[s]ing-box'` 取 PID 再 `kill`。

---

## 6 · 对三台服务器的建议

| 目标 | 动作 |
|---|---|
| **立刻可用** | 在**跑 sing-box 且 hy2 监听 v6** 的机器上装 §4-C（脚本 + 单元）。RN 上已在备用端口完整验证，未改任何全局路由 |
| **治本** | 改面板模板（§4-E）：hy2 生成时就绑具体地址 + 补一个 `0.0.0.0` 入站 |
| **顺手确认** | `ip -6 rule show \| grep 0xc350` —— 只要 v6 那条指向 `cw3`，这台机器上"通配绑定 UDP 走 v6"的节点就有同样风险 |
| **X / M 机器** | 它们的 hysteria 类节点目前只绑 `0.0.0.0`（**不接受 v6**），所以**现在不会发作**。若将来要开 v6 监听，先按 §7.3 确认其实现的回包源地址行为 |

---

## 7 · 明确未验证 / 存疑

1. **tuic 与 hysteria2 在 sing-box 内部的具体代码差异** —— 只证到"同进程、同绑定、同证书下行为不同"，
   **没有逐行核对上游源码**。（机制解释见 §2.3 的诚实标注）
2. **D 方案（`not fwmark 0xc350` 的 v6 目标改回 `main`）没有实测**，只从路由表推导。
3. **mihomo / Xray 的 hysteria 实现若绑 `::` 会不会同样失效**：**没有实测**（它们当前只绑 `0.0.0.0`，不构成现状问题）。
4. **上游 sing-box 是否已有开关/版本修复**（让 hy2 回填回包源地址）：**没有查**。
5. **RN 上装的 V3 是否与 GitHub 当前 main 逐字节一致**：只比过文件大小与目录时间，**没有逐字节比对**。
6. **独立表方案跨重启的持久性**：只验证了"不会被 V3 的 need 计算追上"，
   **没有真的重启验证**（配套单元已给出，但未在重启后回归）。

---

## 8 · 可复现的最小命令集

```bash
# 1) 看"未打标流量"这条规则指向哪（v6 指向 cw3 就是元凶形态）
ip -6 rule show | grep -E "0xc350"
ip     rule show | grep -E "0xc350"        # 对照：v4 通常指向 main
ip -6 route show table cw3

# 2) 决策期预测：这条命令的输出源地址，就是通配 UDP 回包会用的源地址
ip -6 route get <客户端IPv6> from ::                    # → dev warp table cw3 src 2606:4700:…  ★
ip -6 route get <客户端IPv6> from :: sport <节点端口>    # → dev he-ipv6 src 2001:470:…（被规则救回时）

# 3) V3 的入站保护在不在、有没有命中
ip6tables -t mangle -S INPUT | grep CONNMARK
ip6tables -t mangle -L CATMI3-OUT -n -v -x | grep -E "connmark match 0x4|MARK set 0x3"

# 4) conntrack：一次尝试里应当出现"两条表项"（mark=4 源正确 / mark=3 源是 WARP）
grep -a "dport=25926" /proc/net/nf_conntrack

# 5) 抓包看回包源地址（最直接的证据）
tcpdump -ni any "udp and (port 25926 or port 25930)"

# 6) 修法 C 的效果验证（加规则前后各跑一次客户端）
ip -6 rule add prio 32761 sport <节点端口> lookup 100
ip -6 route replace default via <he-ipv6 网关> dev he-ipv6 table 100
```

---

## 9 · 本次调查中做过、且已清理的操作（RN 侧）

| 操作 | 状态 |
|---|---|
| 备用端口临时 sing-box 实例（35926/35927/35930） | ✅ 已按 PID 清理，`/tmp/hy2*` 已删 |
| 试验性 `ip -6 rule`（32761）与路由表 100 | ✅ 已撤，规则表回到基线 8 条、表 100 已 flush |
| **生产 hy2 节点配置改动**（§4-B，备份 `/root/catmi/sing-box/backup/hysteria2-01.json.pre-hy2v6fix-20261011-105002`，回滚即 `cp` 回去 + 重启 sing-box） | ⚠ **保留**（这是当前让节点可用的状态）；面板一重建即回退，见 §5.2 |
| 生产进程 | `sing-box` / `mihomo` / `xrayls` / `nginx` 全程未受影响；改配置时仅 `sing-box` 重启一次（属预期） |
| **收尾复核（真客户端，CC → RN 生产节点）** | ✅ **hy2 走 IPv6 → HTTP 204**、**走 IPv4 → HTTP 204**，出口均为 `104.28.201.80`（RN 的真实 CF 出口）；`share.sh check all` → `[OK] 分享内容与真实配置一致`，分享链接未变 |

**终态**：v6 规则表 8 条 / v4 规则表 8 条（均回到基线），试验规则与路由表 100 零残留，
`/tmp/hy2*` 零残留；服务 `sing-box` / `mihomo` / `xrayls` / `nginx` 全部 active。

---

*本文档由调查方（AI 助手）整理。凡"实测/已验证"字样均有当次原始输出支撑；凡未实测者已在 §4/§7 显式标注。*
