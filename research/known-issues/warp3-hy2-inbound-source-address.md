# hysteria2(IPv6) 入站回包源地址漂移 —— catmi-warp3 策略路由导致的"单协议单地址族不通"

> 调查时间：2026-10-11 / 12（本地 CST）｜调查对象：RN（`ssh rn`，107.173.154.178）+ CC（`ssh CC`，192.168.1.178）
> 触发问题：**SB 内核建的 hysteria2 节点，只有走 IPv6 时不通**；同一个节点走 IPv4 完全正常。
> 相关脚本：`mi1314cat/One-click-script` → `warp/catmi-warp3.sh`（sha256 前 16 位 `9cc809e6dac553fb`，4457 行）
> RN 上实际安装的版本：`/usr/local/bin/catmi-warp3`（243894 字节，2026-09-16）

---

## 0 · 一句话结论

**不是 hy2 参数错，也不是"IPv6 坏了"。** 是 RN 上的策略路由有一条"**未打标的 IPv6 流量默认送 WARP**"的规则，
而 hysteria2 的回包是从**通配地址 socket**发出的 —— 内核给它选了 WARP 的源地址
（`2606:4700:…`），客户端发的却是 `2001:470:…`，QUIC 客户端**只认自己发过去的那个地址**，
回包一律丢弃 ⇒ 握手永远完不成 ⇒ 15 秒超时。

这条规则**不是 catmi-warp3 装的**（V3 是白名单 `fwmark 0x3 → cw3`），是 **fscarmen warp-go 注入的**
`not fwmark 0xc350 → cw3` —— V3 的代码里**明确记录过这个冲突**（第 1856–1937 行），也提供了处置方案。
**但 V3 现有的那道"入站保护"救不了 hysteria2**：它是**基于 conntrack** 的，而 hy2 的失效恰好发生在
conntrack 能匹配上之前。**这一条按你"禁止影响入站"的标准，算必须修的缺陷。**

---

## 1 · 现象与差分实测（从 CC 用真 sing-box 1.14.2 客户端）

| 节点 | 协议 / 传输 | 走 IPv4 `107.173.154.178` | 走 IPv6 `2001:470:c:cf:bf47:d1e0:cd4d:c6db` |
|---|---|---|---|
| anytls01-TLS | TCP + TLS | ✅ 204 | ✅ 204 |
| tuic01-TLS | **UDP / QUIC** | ✅ 204 | ✅ 204 |
| **hysteria2-01-TLS** | **UDP / QUIC** | ✅ **204**（出口 `104.28.201.80`） | ❌ **000**（`context deadline exceeded`，15s） |

- 服务端一侧全部正常：`sing-box check` 通过、`ss -lunp` 里 `*:25926` 在听、防火墙 UDP/TCP 都放行、
  证书有效（`/home/web/certs/moontv.6896698.xyz_cert.pem`，到期 2027-01）。
- 同一份客户端参数（密码 / `obfs=salamander` / `sni` / `alpn=h3`）**只换服务器地址**，IPv4 就 204。
  ⇒ **hy2 自己的配置没有错。**

---

## 2 · 证据链（层层收窄，每一步都有原始输出）

### 2.1 抓包：回包源地址被换掉了

RN 上 `tcpdump -ni any "udp and (port 25926 or port 25930)"`，同时让 CC 尝试两个节点：

```
# hy2（不通）
he-ipv6 In  2409:8a20:…:29655 > 2001:470:c:cf:bf47:d1e0:cd4d:c6db.25926   UDP 1258
warp    Out 2606:4700:110:822e:a614:76df:2b40:41fb.25926 > 2409:8a20:…:29655  ← ★ 源地址变成 WARP 的
# tuic（通，对照）
he-ipv6 In  2409:8a20:…:65154 > 2001:470:c:cf:bf47:d1e0:cd4d:c6db.25930   UDP 1280
he-ipv6 Out 2001:470:c:cf:bf47:d1e0:cd4d:c6db.25930 > 2409:8a20:…:65154       ← 源地址正确
```

### 2.2 路由表：内核自己说会这么选

```console
$ ip -6 route get 2409:8a20:1c93:5460::2
  2409:8a20:1c93:5460::2 from :: dev warp table cw3 src 2606:4700:110:822e:… metric 1024

$ ip -6 rule show
  0:     from all lookup local
  17:    from all fwmark 0x4/0x4 lookup main          ← 入站回程标记 → main（V3 的 IMARK 保护）
  50:    from all oif he-ipv6 lookup main             ← bind 保护（V3 装的）
  32762: from 2001:470:c:cf::/64 lookup main          ← 按源地址走 main（V3 装的）
  32763: from all oif warp lookup cw3
  32764: from all fwmark 0x3 lookup cw3               ← ★ V3 的白名单：只有打了 0x3 的才走 WARP
  32765: not from all fwmark 0xc350 lookup cw3        ← ★★ 元凶：没有 0xc350 的**全**走 cw3
  32766: from all lookup main

$ ip -6 route show table cw3
  default dev warp
```

关键在 **32765** 这一条：它是"**黑名单式**"的 —— 只要流量没打上 `0xc350` 标记，就被送进 `cw3` 表，
而 `cw3` 的默认路由是 `dev warp`。对一个**通配地址**（`listen: "::"`）的 UDP socket，
回包时源地址要到路由选完之后才定 —— 于是 `32762`（按源地址走 main）**匹配不上**，掉进 `32765` → warp。

> 顺带确认：**防火墙不是原因**。两个端口在 `ip6tables` 里都没有专门规则，而 tuic 通；
> 抓包也证明 hy2 的入站包**已经到达本机**（nft 里那条 `udp dport 25926 … accept` 计数 49 包，与抓包吻合）。

### 2.3 mangle 计数器：V3 的入站保护对 hy2 **一次都没命中**

RN 上 `ip6tables -t mangle -L CATMI3-OUT -n -v -x` 在"一次 hy2 尝试"前后的差值：

```
hy2  尝试:  +2 包 → MARK set 0x3（兜底：送 WARP）        ；connmark 0x4 那条规则命中 **0**
tuic 尝试:  +20 包 → connmark match 0x4/0x4 → MARK set 0x4 → RETURN（走 main）
INPUT -i he-ipv6 CONNMARK --set-xmark 0x4/0x4：hy2 尝试 +12 包（**打标是成功的**）
```

也就是说：**入站打标成功了，但回包那一步匹配不上那条 connmark 规则**。

### 2.4 conntrack：一次尝试里出现了**两条**表项

`/proc/net/nf_conntrack` 采样（同一次 hy2 尝试）：

```
① src=2409:8a20:…:2 (CC) dst=2001:470:c:cf:bf47:… sport=44917 dport=25926 [UNREPLIED]
   回程元组: src=2001:470:c:cf:bf47:… dst=2409:8a20:…:2 sport=25926 dport=44917
   mark=4        ← 入站标记成功（V3 的 INPUT 规则起了作用）

② src=2606:4700:110:822e:… (WARP) dst=2409:8a20:…:2 sport=25926 dport=44917 [UNREPLIED]
   回程元组: src=2409:8a20:…:2 dst=2606:4700:110:822e:… sport=44917 dport=25926
   mark=3        ← 回包从 WARP 源地址出去，另起了一条表项，没有入站标记
```

**这就是机制**：回包的源地址被换成了 WARP 的地址之后，它**不再匹配 ① 的回程元组**，
于是 conntrack 新建了 ②；而 V3 的保护规则查的是 connmark（`-m connmark --mark 0x4/0x4`），
② 上没有这个标记 ⇒ 保护失效 ⇒ 落到兜底 `MARK 0x3` ⇒ 继续走 WARP ⇒ 源地址一直是错的。

**这是一条自锁的环路**：源地址错了 → conntrack 匹配不上 → 保护用不上 → 源地址继续错。

### 2.5 A/B 实验（在**备用端口**上起独立实例，不动生产）

| 实例 | `listen` | 从 CC 走 IPv6 | 内核预测 |
|---|---|---|---|
| A（= 现配置） | `"::"` | ❌ 000 | `dev warp table cw3 src 2606:4700:…` |
| B | `"2001:470:c:cf:bf47:d1e0:cd4d:c6db"` | ✅ **204** | `dev he-ipv6 src 2001:470:…` |

**换端口没用**：A 用 35926、B 用 35927，差别只在 `listen` 是通配还是具体地址 —— 端口与本题无关。

---

## 3 · 为什么"只有 hy2"？（tuic 同样是 UDP/QUIC 却没事）

这是整件事里最关键、也最反直觉的一点。实测结论是：

* **TCP 类（anytls / vless / trojan）**：入站连接的路由在三次握手时就固定了，回包天然带着入接口的源地址 ⇒ 不受影响。
* **tuic**：**回包保住了正确的源地址**（抓包与 conntrack 都证实）⇒ 回包匹配得上 ① 号表项 ⇒
  V3 的 `connmark 0x4` 保护命中（计数器 +20）⇒ 走 main ⇒ 通。
* **hysteria2**：回包是从**共享的通配地址 QUIC socket** 发出的，源地址由路由现选 ⇒ 被 32765 抓进 WARP ⇒ 源地址漂移 ⇒ 保护失效 ⇒ 不通。

> **未验证**：sing-box 内部为什么 tuic 与 hysteria2 在这点上不同（推测是 tuic 每个会话用独立的
> 已连接/已绑定 UDP socket，而 hysteria2 复用监听 socket 回包）。**这一条我没有证到**，
> 只是"实测行为不同"这一点是确定的。

---

## 4 · 这是不是 catmi-warp3 的问题？

**分三层说清楚，不推责也不揽责：**

1. **V3 的设计本身没问题，而且是"对的方向"。**
   - V3 装的是**白名单**：`ip -6 rule add prio $RT_ANCHOR fwmark 0x3 table cw3`（脚本 1675 行）——
     只有显式打了 0x3 的流量才走 WARP，其余落回 `main`。这种写法**不会**影响入站。
   - V3 还专门为这个失效模式做了保护，脚本第 46–48 行的原话：
     ```
     IMARK="4"   # fwmark 0x4 = 入站回程标记: 入站连接(he/eth0)的回包走 main,
                 # 源=入站接口地址 — 防止 UDP 通配 socket 回包被 C 规则抓进 WARP 源漂移
     ```
     并且 `iptables/ip6tables -t mangle -I INPUT 1 -i "$up" -j CONNMARK --set-xmark 0x4/0x4`
     在 RN 上**确实装了、也确实在打标**（2.3/2.4 有原始计数）。

2. **真正闯祸的是 fscarmen warp-go 注入的那条"黑名单"规则**，V3 的注释里点名过它：
   ```
   脚本 1856 行: # fscarmen warp-go (重)启时会注入 "not fwmark 0xc350 lookup 50000" (无标流量→其 WARP 表)
   脚本 1861 行: #   C: not fwmark 0xc350 → main (未打标流量归原生; 0xc350 是 fscarmen 自用防环 mark, 不受影响)
   ```
   RN 上这条规则**存在，而且指向的是 `cw3`**（不是 `main`）—— 于是"没打标 = 默认走 WARP"生效了。

3. **但 V3 有一个真实缺口**：它的入站保护**是基于 conntrack 的**，
   而通配 socket 的回包会在 conntrack 匹配**之前**就把源地址定成 WARP 的地址，
   从而绕过这层保护。**对 hysteria2 这类协议，V3 的"禁止影响入站"承诺目前是破的。**
   按你的标准，这算必须修的一条。

---

## 5 · 修复选项（含每一条的验证状态）

| # | 做法 | 验证状态 |
|---|---|---|
| **A** | **把这个节点改成走 IPv4**（面板「客户端产物 → 9) 切换产物地址族」是全局开关；或只改 hy2 这一条链接的地址为 `107.173.154.178`） | ✅ **已实测**：hy2/anytls/tuic 三个节点走 IPv4 全部 204 |
| **B** | **让 hy2 入站 `listen` 绑具体 IPv6 地址**（而不是 `"::"`）。代价：该节点的 IPv4 路径会没有，除非再加一个绑 `0.0.0.0` 的同端口入站 | ✅ **已实测**：备用端口 35927 上 `listen=具体v6` → 204 |
| **C** | **把 fscarmen 那条规则从 `cw3` 改指 `main`** —— 这正是 V3 自己写的"冲突处置 C 选项"。改完：未打标流量落 `main`（原生、源地址正确），V3 的白名单 `fwmark 0x3 → cw3` 照旧把该走 WARP 的送 WARP | ⚠ **未实测**（从路由表推导应当可行；**动的是全局 WARP 分流，会影响 X/M 的 WARP 行为，我没有碰**） |
| **D** | 在 V3 里加一条优先级更高的、按"本机出口地址 + 入站流"分流的规则 | ⚠ **未设计**（conntrack 路线已被证明不够，需要换机制） |

**建议顺序**：先 A（立刻可用、零风险）→ 再评估 C（治本，但要在你有空盯着的窗口里做，并且先备份路由/规则）。

---

## 6 · 调查过程中踩过的坑（也写下来，免得下次重复）

1. **在 CC 上用 glob**：CC 的登录 shell 是 **zsh**，`rm -f /tmp/hy2t/*.log` 在文件不存在时会
   `no matches found` 并**直接中断整条命令**（而不是像 bash 那样原样传参）。
   ⇒ 后来一律改成 `ssh CC 'bash -s' <<'REMOTE'` 喂脚本。
2. **`pkill -f` 匹配到自己的 ssh 命令行**：`pkill -f "sing-box run -c /tmp/hy2t"` 把承载这条命令的
   bash 自己也杀了，ssh 会话断开、后半段命令没执行。出现过**两次**（一次在 CC，一次在 RN）。
   ⇒ 改用 `[s]ing-box` 方括号技巧 + PID 文件。
3. **在错误的机器上找文件**：把 RN 的 `/root/catmi/sing-box/out/` 路径拿到 CC 上去 `head`，全是空。
4. **测试脚本里密码留空**：一个 anytls 对照用例把 `password` 拼成了空串，得到 000，
   差点被当成"IPv4 也不通"的证据。⇒ 凭据从服务端配置里读，不要手抄。
5. **`ping6 -W` 在 CC 上不存在**（busybox/coreutils 差异），第一次可达性测试直接报参数错。
6. **PyYAML 会静默接受重复键**（另一个不相干的调查里踩到）：判断 YAML 合法性**不能**用
   `yaml.safe_load` 是否抛异常，得用真内核（mihomo 用 go-yaml，会报
   `mapping key "proxies" already defined`）。

---

## 7 · 明确未验证 / 存疑

1. **tuic 与 hysteria2 在 sing-box 内部为何表现不同** —— 只证到"行为不同"，没证到机制。
2. **C 方案（把 `not fwmark 0xc350` 改指 `main`）没有实测**，只是从路由表推出来的。
3. **改 `listen` 绑具体地址后**，该节点在 IPv4 客户端上的行为**没有实测**（推测是不再监听 IPv4）。
4. **RN 上 `/etc/catmi/warp3/` 里装的是不是与 GitHub 当前 main 完全同一版**：只比了文件大小
   （都是 243894 字节）与目录时间，**没有逐字节比对**（时间 2026-09-16，GitHub 那份可能已更新）。
5. 其它内核（X/M）的 UDP 入站协议是否也有同类风险：**没有逐个排查**。
   （`xrayls` 的 hy2 入站同理值得怀疑，但那是另一套实现、另一套监听方式。）

---

## 8 · 可复现的最小命令集

```bash
# 1) 看这条"黑名单"规则在不在（这是元凶）
ip -6 rule show | grep -E "0xc350|fwmark"
ip -6 route get <客户端IPv6>                 # 看是不是 dev warp table cw3

# 2) 看 V3 的入站保护在不在（在的话说明是"保护被绕过"，不是"没装"）
ip6tables -t mangle -S INPUT | grep CONNMARK
ip6tables -t mangle -S CATMI3-OUT

# 3) 计数差：跑一次 hy2 尝试前后各取一次，比这两条的增量
ip6tables -t mangle -L CATMI3-OUT -n -v -x | grep -E "connmark match 0x4|MARK set 0x3"

# 4) conntrack：一次尝试里应当出现"两条表项"（一条 mark=4 源正确，一条 mark=3 源是 WARP）
grep -a "dport=25926" /proc/net/nf_conntrack

# 5) 抓包看回包源地址
tcpdump -ni any "udp and port 25926"
```

---

*本文档由调查方（AI 助手）整理，所有"实测"字样均有当次原始输出支撑；凡未实测者已在 §5/§7 显式标注。*
