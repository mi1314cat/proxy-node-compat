# X 内核客户端链路断点：hy2 参数在「解析」和「生成」两跳都丢

- 日期：2026-10-10
- 目标仓库：`/root/deepseek/repos/xray--core`（**只改这一个**；`mihomo--core` / `sing-box-core` 全程只读）
- 真机：`ssh rn`（107.173.154.178，Xray 26.3.27 = `d2758a0`，生产 hy2 节点 `hysteria-04` / UDP 29604）、
  `ssh CC`（192.168.1.178，Xray 26.3.27 arm64 = `d2758a0`，客户端装在 `/opt/xray-browser-dialer`）
- 上游背景：`research/known-issues/x-share-sni-and-pin.md`（上一轮把 `alpn` / `up` / `down` /
  `upmbps` / `downmbps` 补进了**分享链接**，遗留项 2 明确写着「本项目自己的 Client 不采纳 hy2 的
  up/down」—— 本轮就是去修那一截）
- 实验全部在 `/tmp`（本机 `/tmp/revcheck`、CC `/tmp/xhy2`），**没有写任何生产路径**；
  RN / CC 正式服务复查 `active`（见文末「边界」）
- 字段名判定用的内核源码：本机 `/tmp/xraycore` 的 tag **`v26.3.27` = `d2758a02`**，
  与 RN/CC 上二进制的 `d2758a0` 是同一个提交

---

## 0 · 结论一览

| # | 断点 | 现状 | commit |
|---|---|---|---|
| ① | **链接 → `Client/lib/node.py` 节点 JSON** | ❌→✅ `up`/`down`/`upmbps`/`downmbps`/`mport`/`pin` 只落在 `raw_params`，顶层一个都没有 | 本轮 |
| ② | **节点 JSON → `Client/lib/genconfig.py` 配置** | ❌→✅ 生成器里**根本没有写带宽的代码**；现在写 `finalmask.quicParams` | 本轮 |
| ③ | 内核对字段名的要求 | `hysteriaSettings.up/down` **已废弃**（只警告就丢）；真字段是 `finalmask.quicParams.brutalUp/brutalDown` | 实证 |
| ④ | 旁证：`conf/hysteria2.sh` 自己的客户端产物 | ❌→✅ 同一个节点，脚本发的 Xray 客户端 JSON 也在写被丢弃的 `hysteriaSettings.up/down` | 本轮 |
| ⑤ | 旁证：`hysteria2.sh` 的分享链接 | ❌→✅ 只有 `upmbps/downmbps`，mihomo **整条丢掉**（与上一轮 `nodes.py` 修的是同一个坑，脚本这份漏了） | 本轮 |
| ⑥ | 另一条输入路径 `parse_xray_json` 认不出 `protocol:"hysteria"` | **未修，另行记录**（见 UNKNOWN 1，失败是响的，不是静默的） | — |

---

## 1 · 逐跳定位（每一跳都单独跑过）

### 跳①：链接 → `Client/lib/node.py` → 节点 JSON —— **断在这里**

拿 RN 生产那条 hy2 链接（`/root/catmi/xray/out/hysteria.txt` 第 4 条 + 上一轮补的 `up/down`）：

```
hysteria2://05615ce2-...@107.173.154.178:29604?sni=moontv.6896698.xyz&insecure=0&alpn=h3&up=50&down=200&upmbps=50&downmbps=200#hysteria-04
```

```
$ python3 Client/lib/node.py parse "<上面那条>"
  up        MISSING        ← 修复前
  down      MISSING
  upmbps    MISSING
  downmbps  MISSING
  mport     MISSING
  alpn      'h3'           ← alpn/sni 是好的（上一轮修过），所以只有带宽这一类丢
  sni       'moontv.6896698.xyz'
  raw_params: {"sni": ..., "insecure": "0", "alpn": "h3",
               "up": "50", "down": "200", "upmbps": "50", "downmbps": "200"}
```

- `parse_hysteria2()` 读的键只有 `sni`/`peer`、`alpn`、`insecure`；带宽三兄弟**一个都没读**。
  它们只活在 `raw_params` 里，而 **`genconfig.py` 从不读 `raw_params`** —— 等于进了回收站。
- mihomo YAML 输入路径同样丢：`_yaml_entry_to_node()` 不读 `up`/`down`/`ports`。

**实机现场（这是最硬的证据，不是我构造的）**：CC 上正在跑的那个节点
`/opt/xray-browser-dialer/nodes/node-001-ccsmhysteria2-01.json`，它自己的 `raw` 里明明白白写着

```json
{"type": "hysteria2", ..., "up": "45 Mbps", "down": "150 Mbps", "sni": "bing.com", "alpn": ["h3"]}
```

而同一个文件**顶层没有 `up`/`down` 这两个键**。也就是说：来源声明了、解析器吃了、模型里没了。

### 跳②：节点 JSON → `Client/lib/genconfig.py` → Xray 配置 —— **也断**

即使手工把 `up/down` 塞进节点 JSON，生成器也写不出来 —— `build_stream()` 的 hysteria 分支
只写 `network` / `method` / `hysteriaSettings{version,auth}` / `tlsSettings{serverName,alpn,pin}`：

```json
"streamSettings": {
  "network": "hysteria", "method": "hysteria",
  "hysteriaSettings": { "version": 2, "auth": "05615ce2-..." },
  "security": "tls",
  "tlsSettings": { "serverName": "moontv.6896698.xyz", "alpn": ["h3"] }
}
```

所以是**两跳都断**，不是"只差最后一跳"。①不修的话②永远没数据可写。

### 跳③：Xray outbound 里的字段到底叫什么 —— **必须以真内核为准**

先说结论：**`up`/`down` 这个名字在 Xray 里存在，但已经废了** ——
它被接受、被解析、然后被丢掉，只留一行 Warning，而 `xray run -test` 返回 **rc=0
"Configuration OK"**。这就是本仓库吃过的「能解析 ≠ 支持」：

```
[A] hysteriaSettings: {version:2, auth:..., up:"50", down:"200"}
    rc=0  [Warning] infra/conf: congestion & up & down & udphop move to finalmask/quicParams
          Configuration OK.        ← 看着完全正常，其实一个字节都没生效
```

真正指挥内核的是 **`streamSettings.finalmask.quicParams.brutalUp` / `brutalDown`**
（端口跳跃是 `...quicParams.udpHop.ports`）。

#### 怎么验的：错误反证法（会报错才说明键真的被读了）

在 CC 上拿**同一个真内核** `d2758a0` 跑 11 个变体，只改 hysteria 出站的 streamSettings：

| 变体 | rc | 内核原话 |
|---|---|---|
| A `hysteriaSettings.up/down` 裸数字 | 0 | `[Warning] congestion & up & down & udphop move to finalmask/quicParams` / Configuration OK |
| B `hysteriaSettings.up/down` 带单位 | 0 | 同上（**带不带单位都一样被丢**） |
| C `finalmask.quicParams.brutalUp:"50"` | **23** | `infra/conf: BrutalUp must be at least 65536 bytes per second` |
| D `finalmask.quicParams.brutalUp:"bogus"` | **23** | `strconv.ParseFloat: parsing "": invalid syntax` |
| E `finalmask.quicParams.brutalUp:"50 mbps"` | 0 | Configuration OK |
| F `brutalUpXX`（拼错的键，对照） | 0 | Configuration OK ← **未知键静默丢弃，"OK" 不是证据** |
| G `hysteriaSettings.upXX`（对照） | 0 | Configuration OK |
| H 随便加一个未知 streamSettings 键（对照） | 0 | Configuration OK |
| I `finalmask.quicParams.udpHop.ports:"20000-30000"` | 0 | Configuration OK |
| J `congestion:"force-brutal"` 不给 up | **23** | `infra/conf: force-brutal requires up` |
| K `congestion:"bogus"` | **23** | `unknown congestion control: bogus, valid values: reno, bbr, brutal, force-brutal` |

C/D 会报错、F/G/H 不会 —— 这一对对照就把「哪个键是真的」钉死了。
顺带钉死一条**会毁配置的坑**：`brutalUp` 的裸数字是**字节/秒**且有 `>= 65536` 下限，
把链接里的 `up=50`（Mbps）原样透传进去 → 内核**拒收整份配置**（不是"限速没生效"）。
`"50 mbps"` 才是对的。

#### 源码侧对照（tag `v26.3.27` = `d2758a02`，与二进制同提交）

| 位置 | 内容 |
|---|---|
| `infra/conf/transport_internet.go:522-533` | `HysteriaConfig{Version, Auth, Congestion, Up, Down, UdpHop, UdpIdleTimeout, Masquerade}` —— `Up *Bandwidth \`json:"up"\`` **确实存在** |
| 同文件 `:535-556` | `Build()`：`if c.Congestion != nil \|\| c.Up != nil \|\| c.Down != nil \|\| c.UdpHop != nil { LogWarning(...) }`，然后 `config := &hysteria.Config{}` **只赋 Version/Auth/UdpIdleTimeout/Masq\*** —— `Up`/`Down` **一次都没被读走** |
| 同文件 `:1720-1731` | `type FinalMask{Tcp, Udp, QuicParams *QuicParamsConfig \`json:"quicParams"\`}`；`StreamConfig.FinalMask \`json:"finalmask"\`` |
| 同文件 `:629-643` | `QuicParamsConfig.BrutalUp/BrutalDown Bandwidth \`json:"brutalUp"/"brutalDown"\`` |
| 同文件 `:453-502` | `Bandwidth.Bps()`：`""/"b"/"bps"` → `Byte = 1`（字节），`k/m/g/t` → 1024 进制，`/8` 换算成字节/秒 |
| 同文件 `:1897-1910` | `BrutalUp` 非 0 且 `< 65536` → 报错退出 |
| `transport/internet/hysteria/config.proto` | 传输层 Config 只有 `version/auth/udp_idle_timeout/masq_*` —— **带宽根本不在这层** |
| `transport/internet/hysteria/dialer.go:274,294-313` | 客户端把 `BrutalDown` 放进 `Hysteria-CC-RX` 头；`case "brutal",""`：服务端广播了带宽才用 brutal，否则退回 BBR |
| `transport/internet/hysteria/udphop/conn.go:19-36` | `intervalMin/Max == 0` → `defaultHopInterval = 30s`（所以 `ports` 单独写是安全的） |

#### 行为侧反证（不是只读源码）

`up/down` 到底有没有**真的被用**，用两个行为实验证明（都在 CC 上对着 RN 生产节点跑）：

1. **端口跳跃真的生效**：同一条链接加 `mport=30000-31000` → **HTTP 000（0.27s 就断）**；
   不加 mport（RN 只在 29604 监听）→ **204**。跳到没人听的端口范围立刻连不上 ⇒ `udpHop` 被采纳。
2. **带宽真的进了拥塞控制**：`brutalUp:"1 mbps"` + `congestion:"force-brutal"`，debug 日志原文

   ```
   [Debug] transport/internet/hysteria: congestion brutal bytes per second 131072
   ```

   `1 Mbps = 1*1048576/8 = 131072 B/s` —— 与配置里的字符串**逐位对上**。
3. **吞吐实测（2 MB 上行经代理上传，`speed.cloudflare.com/__up`）**：

   | 拥塞控制 | 配置 | 实测 | 耗时 |
   |---|---|---|---|
   | `bbr` | brutalUp 被忽略 | **515012 B/s** (≈4.1 Mbps) | 3.88 s |
   | `force-brutal` | `brutalUp: "1 mbps"` | **115817 B/s** (≈0.93 Mbps) | 17.27 s |

   4.4× 的差距、且 0.93 ≈ 配的 1 Mbps ⇒ 这个字段**端到端真的在指挥内核**，不是"解析通过"。

---

## 2 · 改了什么

### `Client/lib/node.py`

| 新增 | 作用 |
|---|---|
| `DEFAULT_NODE["up"] / ["down"]` | 带宽提示，存**带单位的规范写法**（`"50 mbps"`），未声明 = `""` |
| `DEFAULT_NODE["mport"]` | 端口跳跃范围，原样保留 |
| `bandwidth_hint(v)` | 把来源写法归一成 Xray 的 Bandwidth 语法。`50`/`"50"`/`"50mbps"`/`"50 Mbps"`/`"1.5g"` 都认；**裸数字按链接侧约定补 `mbps`**（内核裸数字是字节/秒，语义相反，绝不能透传）；`"50bps"` 这种没写数量级的不猜；认不出返回 `""` |
| `bandwidth_mbps(v)` | 上面的逆函数，只用于"生成链接"方向（还原成裸数字） |
| `port_hop_range(v)` | 端口范围合法性校验（`a-b` / `a,b` / 单端口；越界就整个丢） |
| `parse_hysteria2()` 增 4 项 | `up`（优先 `upmbps`，退回 `up`）/ `down` / `mport` / **`pinned_cert_sha256` ← `pin=`** |
| `_yaml_entry_to_node()` 增 1 块 | mihomo `hysteria2` 的 `up`/`down`/`ports` 也收（**CC 实机那个节点就是这么丢的**） |
| `build_link()` 增 1 块 | 反向补齐：hy2 写 `up=`/`down=`/`upmbps=`/`downmbps=`/`mport=`/`pin=`（否则手动添加表单填了也白填） |

`pin=` 是**顺带发现并修掉的同类静默丢弃**：`conf/hysteria2.sh` 自签分支发的链接带
`pin=<证书 DER hex sha256>`（与 Xray 的 `pinnedPeerCertSha256` 同一个值），而客户端解析器
**从来没读它** —— 自签节点经链接导入后必然证书校验失败。`parse_trojan` 早就读了同一个键，
只有 hy2 分支漏了。

### `Client/lib/genconfig.py`

- 新增 `_bandwidth_value()` / `_port_hop()`：规范写法直接下发；裸数字/带单位的旧写法补单位；
  认不出的**跳过并在 stderr 说明**（不硬塞）。
- `build_stream()` 的 hysteria 分支：把 `up`/`down`/`mport` 写进

  ```json
  "finalmask": { "quicParams": { "brutalUp": "50 mbps", "brutalDown": "200 mbps",
                                 "udpHop": { "ports": "30000-31000" } } }
  ```

  **不写 `congestion`**：缺省（`""`）在 dialer 里就是 brutal 家族、且跟随服务端是否广播带宽
  （服务端 `BrutalDown=0` 时自动退回 BBR）。写死会把"跟随服务端"变成"单方面强制"，那是另一个语义。
  **不写** `hysteriaSettings.up/down` —— 那是"能过 -test 但内核丢掉"的假成功。
- `node_type_problems()`：只拦内核绝对收不下的类型（对象/数组/布尔）。
  **故意不放进 `_NODE_STR_FIELDS`** —— 那里是"不是 string 就毙掉整个节点"，
  而 `up: 50` 是能救的写法，为一个能救的写法毙掉节点比静默丢弃还糟。
- 没有 `up/down` 的节点：**生成的配置与改动前逐字节相同**（不写 `finalmask`，不编默认值）。

### `conf/hysteria2.sh`（旁证，同一个坑的两处）

- 客户端 JSON 片段的 `hysteriaSettings:{..., "up":"50mbps","down":"200mbps"}`
  → `finalmask.quicParams.brutalUp/brutalDown`（自签档的 `tlsSettings` 原样不动）。
- 分享链接补 `up=50&down=200`（mihomo 只认这两个名字；只写 `upmbps` 会被 mihomo 整条丢掉）。
  两档产物都用真内核 `xray run -test` 验过 → 都 **Configuration OK**。

---

## 3 · CC 真机端到端（改前 vs 改后）

链路：RN 生产链接 → `Client/lib/node.py` → 节点 JSON → `Client/lib/genconfig.py`
（带 `--validate-with` 真内核）→ CC 真内核 `xray run` → `curl` 经 socks5h 出网 → 目标站。
配置、日志一律落 `/tmp/xhy2`，socks 端口 11080。

| 目标 | 改前 | 改后 |
|---|---|---|
| `https://www.gstatic.com/generate_204` | 204 / 1.99s，204 / 0.48s | 204 / 1.25s，204 / 0.50s |
| `https://cp.cloudflare.com/` | 204 / 0.80s，204 / 0.90s | 204 / 1.12s，204 / 1.13s |
| `https://www.cloudflare.com/cdn-cgi/trace` | 200 / 1.13s，200 / 0.67s | 200 / 0.88s，200 / 1.12s |

两次 `xray run -test` 都是 `Configuration OK`；改后配置里多了

```json
"finalmask": {"quicParams": {"brutalUp": "50 mbps", "brutalDown": "200 mbps"}}
```

**HTTP 码与耗时没有回归**（差异在 0.3–0.4s 的抖动范围内，样本各 2 次，不足以声称提速或退化）。
对 RN 这条节点，`up/down` 在当前**是行为中性**的：RN 的 hysteria 入站没有配
`brutalDown`，服务端广播 `Hysteria-CC-RX: 0` ⇒ 客户端按源码走 BBR 分支。
带宽真正起作用要在**服务端也广播带宽**或显式 `force-brutal` 时 —— 见 §1 的两个行为实验。
这正是上一轮"改前改后测不出速率差"的原因，本轮用 `force-brutal` 把它变成了可测的 4.4× 差距。

---

## 4 · 回归断言（`tools/check_libs.sh`）

新增一组 `hy2 客户端链路: 链接参数不静默消失 (解析 → 生成)`，共 **21 条**：

- 解析跳 5 条：`up`/`down`/`mport`/`alpn`/`pin=` 必须落在**节点 JSON 顶层**（不是只进 `raw_params`）；
- 生成跳 8 条：`brutalUp`/`brutalDown`/`udpHop.ports` 的值；**一个字段都不许写**已废弃的
  `hysteriaSettings.up/down`；值必须匹配内核语法 `^[0-9.]+ [kmgt]bps$`（裸数字会被当字节/秒 →
  整份配置起不来）；裸数字 `50` / `"150 Mbps"` 要被补成带单位；非法端口范围不写进内核但不影响带宽；
  认不出的写法跳过；**链接没写带宽时不许编默认值**；
- 反向 2 条：节点 → 链接 → 节点，`up`/`down` 不丢；
- 服务端 3 条：`hysteria2.sh` 的客户端 JSON 改用 `finalmask`、不再写 `hysteriaSettings.up/down`、
  链接同时带 `up=/down=` 与 `upmbps=/downmbps=`。

| | 通过 | 失败 |
|---|---|---|
| 改动前基线（上一轮遗留的 662/0 复核） | **662** | **0** |
| 改动后（含新增 21 条） | **683** | **0** |
| 把新增断言打在**修复前**的代码上（`git archive HEAD` 干净树 + 新门禁） | 667 | **16** |

16 条失败**全部落在新增组内**，且逐条指向真实缺陷（`up`→`None`、`brutalUp`→`None`、
`pin`→`''`、`deprecated`→`True` …），反向验证成立。

---

## 5 · 边界与遗留

- 只改 `xray--core`；`mihomo--core` / `sing-box-core` 全程只读。
- **没有写任何生产路径**：本机只在仓库工作树 + `/tmp`；CC 只在 `/tmp/xhy2`（配置、日志、2MB 测试文件全在里面）；
  RN 只跑了 `cat`/`grep`/`ls` 这类只读命令。
  有 `mkdir` 的脚本（`conf/hysteria2.sh`、`conf/lib/cert.sh` 等）**没有被 source** ——
  `hysteria2.sh` 的两个 heredoc 是把 shell 变量替换成具体值后单独抽出来验的。
- RN / CC 正式服务跑完复查：RN `xrayls`/`mihomo`/`sing-box` 全 `active`；
  CC `xray-client` `active`、`/opt/xray-browser-dialer` 未被写入。
- CC 上 `/opt/xray-browser-dialer/lib/{node,genconfig}.py` 与仓库版本**不一致**（安装副本落后于仓库，
  缺 mux/REALITY 那几轮的修复）。本轮的验证一律用**仓库版**代码在 `/tmp` 里跑；
  **生产客户端要生效需要重新分发安装**（本轮没碰，属于部署动作）。

### UNKNOWN

1. **`parse_xray_json` 认不出 `protocol:"hysteria"`**（未修）。把 `conf/hysteria2.sh` 生成的
   `hy2_client-*.xray.json` 喂给 `Client/lib/node.py parse`，得到
   `解析失败: Xray 配置里没有可识别的出站` —— 白名单里写的是 `"hysteria2"`，内核写的却是
   `"hysteria"`（与 `conf/lib/nodes.py` 里已修过的那处是同一个命名坑，客户端这份漏了）。
   它是**响着失败**的，不是静默丢参数，且属于"Xray JSON 导入"这条与本轮不同的输入路径，
   故未动。同一函数对 hysteria 出站也不会读 `settings.address/port` 与 `hysteriaSettings.auth`
   （那两个字段是扁平的，不是 `servers[]`），修的话要一起改。
2. **`up/down` 在 RN 当前节点上是行为中性**（服务端不广播带宽 ⇒ 走 BBR）。
   "RN 环境下的实际提速"未测出、也不该声称；能证明的是字段被内核采纳并在
   `force-brutal` 下逐位生效。
3. **mihomo 的 `hop-interval` 没下发**：Xray 的 `udpHop.interval` 要 `{"from":N,"to":M}` 或
   `"N-M"` 形状（实测写裸数字 `30` 会被静默忽略成默认），而 mihomo 的 `hop-interval` 是秒数；
   由于内核缺省就是 30s（= mihomo 默认），本轮只下发 `ports`。要打通需先实测 `interval` 的确切
   形状 —— **未做**。
4. **`xray -test` 对未知 streamSettings 键返回 OK** 这条性质只在 26.3.27 上验过（变体 F/G/H）；
   更高版本是否变严未验。本轮的断言因此不依赖 `-test`，只依赖生成物结构。
5. **旧版内核（不认识 `finalmask` 的）**：配置不会被拒（未知键静默丢弃，变体 H），
   但带宽也不会生效 —— 与改动前等价，未做版本矩阵实测。
