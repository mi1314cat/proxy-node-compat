# M 侧（mihomo--core）· 已部署代码的产物重建 + CC 客户端更新 + 同列验收

> 日期：2026-10-11 ｜ 对象：**已部署到 RN 的服务端**（`/root/catmi/mihomo`，代码 = `c446d3f`）+ **CC 上的 M 客户端**（`/root/catmi/mihomo-client`）
> 前置报告：`three-way-interop-m.md`（实现与首轮验收）、`m-client-integration.md`（compat 接入）
> 门禁：`bash tools/check_all.sh` → **20/20**；`bash tools/check_interop.sh` → **45 断言 / 0 失败 / 0 跳过**；
> `bash tools/check_share_products.sh` → **43 断言 / 0 失败**（本轮 39→45、40→43）
> 本地 commit（**均未 push**）：`44fc269`（裸查询串声明）/ `00ca35e`（rules.json + ⑨ 门禁）/
> `4b09b7e`（客户端两处修复 + ⑩ 门禁）/ `1896f24`（vendor canonical `c2343b6` 三个文件 + 脱敏扫描面显式排除）/
> `23fe60f`（坏产物不许压过好产物 —— 收集端拒收）/ `0c3fde2`（撤销脱敏例外 + 重 vendor）/
> `accf189`（vendor canonical `692566c`，点名串去掉，零例外）

---

## 0. 一句话结论

服务端代码早就是最新的，**产物不是**：RN 上 hy2 的分享产物还是改造前的旧字节（死端口 + `upmbps=50` + `obfs=none`）。
本轮**只用面板自己的路径**把产物重建到与已部署代码一致（`up=60&down=200&upmbps=60&downmbps=200`，无 obfs 时**不写** obfs），
并验证 `.hy2-bandwidth` 覆盖真的生效（45/170 → 生效；删掉 → 回到 60/200）；CC 客户端更新到 `c446d3f`（52/52 文件逐字节一致），
同列验收：**声明 → 原生 19 节点，逐节点真连 14/19 通过**（5 条失败 = 既有基线的 CDN 节点），负对照 4/4 失败，
声明缺失/原生 404 两条回退路都对。顺带修掉 3 个真缺陷（含 2 个**静默假成功**），全部带反向验证的门禁。

---

## 1. 改了什么（文件 + 行级要点）

### 1.1 `src/lib/interop.py` —— 裸查询串形态的声明读不回来（`44fc269`）

`parse_declaration()` 原判据是 `if "?" in s and "://" in s or s.startswith("?")` /
`elif "=" in s and "://" not in s`。而 `url-*` 的值按设计**保留 `://` 原样**（`URL_SAFE = "/:@[]"`，供"切换地址族"的 sed 替换），
于是**裸查询串里也有 `://`** → 掉进 `else: q = ""` → 返回 `None` → `decide()` 落到 `no-declaration` → **静默走普通话**。

修法（`src/lib/interop.py:202-222`）：判据改成"**有没有 scheme**"，用 `urlsplit(s).scheme` 真探测：

```python
if s.startswith("?"):                      q = s.lstrip("?")
elif urllib.parse.urlsplit(s).scheme:      q = urllib.parse.urlsplit(s).query
elif "=" in s:                             q = s
else:                                      q = ""
```

★ 一处必须写下来的**纠偏**：上级给的等价修法是"否则 `"://" in s` → 当完整地址"。**照字面写不通过** ——
裸查询串里本身含 `://`，那个分支会命中并把 `urlsplit(裸查询串).query` 解析成**空串**，依然静默。
实测：按该写法 `parse(bare) -> None`、`decide(bare) = ('uri','no-declaration','')`。所以这里用的是 scheme 真探测。

**`URL_SAFE` 的取舍**：**保留 `://` 可读性**，不为对齐 X/SB 改成全编码 —— 它的唯一代价（裸查询串里出现 `://`）已被本次修复消除，
而"切换地址族"的 `m_share_links_switch_family` 依赖它原样。

### 1.2 `src/lib/proxy_node_compat/**` 对齐 canonical + 「副本 vs 真源」门禁（`00ca35e`）

* `data/rules.json`：证据 `e-xray-hysteria2-outbound` 的 `how` 里 `出口 <CDN_IP>` → `出口 104.28.195.192`，副本 **8/8 文件逐字节相同**。
* `cli.py` / `engine.py` / `registry.py`：canonical 提交 `c2343b6` 后重新 vendor（三个文件，逐字节）。
* `tools/check_interop.sh` ⑨（新）：副本 vs canonical **逐字节**比对；基线取 canonical 的**已提交真源**（HEAD blob）而不是工作区 ——
  真源写一半时把副本判红 = **假红**，假红会被人习惯性忽略，等于闸门失效；真源有未提交 WIP 时**显式打出来**并计入跳过；
  不在 HEAD 里的文件（新加的 `data/rules.json`）只能比工作区；canonical 不存在 → 明确理由 + 跳过，**不静默通过**。

**取舍（必须留着的那句）**：`rules.json` 原本把真机出口 IP 脱敏成 `<CDN_IP>`，动机是"报告里别撒真机地址"；
代价是"副本与 canonical 逐字节相同"这条最好写最好跑的门禁**必须带例外**，而**例外机制就是漂移的入口**（X 的副本滞后多处正是靠逐字节比对才发现的）。
一度按"向 canonical 看齐"把真值写回副本（`00ca35e`），于是 M 的 `发布脱敏` 变红，我又给扫描面加了一条"排除 vendored 目录"的例外（`1896f24`）。

**★ 这两步都撤销了，正确解法是第三条路**：canonical `40a9441` 把 `104.28.195.192` 改回占位符 `<CDN_IP>` ——
那条证据要证的是「出口是 RN 的 CDN 出口，不是本机」，**这个 claim 不需要具体地址**。
于是 `0c3fde2`：副本重新逐字节 vendor（canonical `c1dc188a7988022f`，仍 **8/8 相同**）、
`发布脱敏` 的扫描面**恢复完整**（只留 `tools/scrub-private.py` 那条既有排除），一个例外都不需要。
`check_all.sh` 的注释里写死了"排除面永远是零，不要在这里加 `grep -v`"。

**仍然卡住的一件事（同一类，待 canonical 处理）**：canonical `40a9441` 新加的 `_comment` 头部点名了三个仓库，
其中 `sing-box-core` 命中本仓库 `tools/scrub.py` 的既有规则 `对标项目|sing-box-core`（"对标引用"）→ `发布脱敏` 因此仍红。
这条**不能靠加例外解决**（加例外正是刚撤销的东西），也不该让副本单方面改（会破坏 8/8）。
已回报 canonical；`692566c` 把那句改成"三个内核各自的公开仓库"，并给 canonical 自己补了
`tests/test_data_hygiene.py`（公网 IPv4 / DDNS 域名 / PAT / UUID / 32 位 hex 一律不许进数据文件）
—— **脱敏从此是 canonical 自己的责任**，本仓库 `发布脱敏` 扫描面保持完整即可。收尾 commit `accf189`。

### 1.3 `src/client.sh` —— 两个"看起来成功"的失败（`4b09b7e`）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| ① | **本地文件形态必崩**：provider 写好了（文件 2 行），客户端却报 `[Error] 订阅里没有解析出节点`、退出 1 | `local pick choice reason rurl detail body tmp code n=0 mode=uri` —— bash 的 `local x`（**不赋值**）留的是"未设置"而非空串，`set -u` 下引用直接 `x: unbound variable` 把函数打断；走本地文件分支时 `detail` 从没被赋过值。实测原样：`src/client.sh: line 1156: detail: unbound variable` | 每个 local 显式赋值 `=""`（`src/client.sh:1109-1116`） |
| ② | **静默假成功**：内核组里 **0 个节点**，客户端照打 `[OK] 已写入 2 个节点` + `[OK] 解析出 2 个节点` | 成功判据是"文件里有几行"（`m_provider_count`），而内核会因**一条**坏条目**整批拒绝** provider（实测 `hy2&obfs=none` → `initial proxy provider error: … missing obfs password`） | 新增 `_provider_load_count()`（`src/client.sh:1108-1180`）：起一个**隔离内核实例**（随机端口、临时 `-d`、只读用现成二进制），问它 `/providers/proxies/<名字>` 真加载到几个；比文件数少就**以内核数字为准并说清原因**；拿不到内核 → `-1`，**不猜也不假装验过** |

★ **`<内核> -t` 证明不了任何事**：同一份坏 provider 上 `mihomo -t` 报 `configuration file … test is successful`、退出码 **0**（实测）。
  原因：配置测试**不加载 provider**。这就是为什么修法必须真起一次内核。验收钩子 `M_PROVIDER_LOAD_PROBE`
  的 provider 路径走环境变量 `$M_PROVIDER_LOAD_PROBE_FILE` 而不是当参数追加 —— 追加会让 `echo 0` 印出 `0 <路径>`，
  解析不出来 → 钩子**静默失效**、看起来还像通过了（这是本轮踩到的第二个"钩子自己假通过"）。

### 1.4 `tools/check_interop.sh` / `tools/check_all.sh` —— 断言

* ③ 新增：`parse_declaration(declaration_query(build_declaration(...)))` 必须**recognized**，且裸查询串 / `?`+裸查询串 / 完整地址三种形态 `decide()` 逐字段相同。
* ⑩ 新增 4 条：本地文件形态正常收场 · 内核整批拒绝时说出 `0/2` · 此时按失败收场 · 拿不到内核（`-1`）时不误报。
* `check_all.sh:127-161`：`发布脱敏` 的扫描面**显式排除** `src/lib/proxy_node_compat/`，并把"扫了多少 / 排除了多少"打出来。
  理由：该路径的内容被 ⑨ **逐字节钉在 canonical 上**（多一个文件、改一个字节都红），比脱敏扫描管得更死 —— 排除**不会**变成藏东西的口子。
  同时把自己门禁里误用的真机 IP 换成 RFC 5737 文档地址 `198.51.100.77`。

### 1.5 `src/share/build_sub.py` —— 坏产物不许压过好产物（`23fe60f`，对应 F-A2）

`collect()` / `collect_dir()` 在**去重之前**加一道拒收（两条产品共用这个收集口，`build_uri.py` 也走它）：

```python
def bad_product_reason(item):        # 内核**一定**用不了的产物 → 原因; 否则空串
    for field in ("server", "sni", "servername"):
        v = str(item.get(field) or "").strip()
        if v and "/" not in v and _CERT_FILE_RE.search(v):
            return f"{field} 是证书文件名 ({v}) —— 字段位置解析错位的典型症状"
    if "reality-opts" in item:
        ro = item.get("reality-opts")
        if not isinstance(ro, dict) or not str(ro.get("public-key") or "").strip():
            return "reality 节点缺 public-key —— 只按裸 TLS 拨号, 必然连不通"
    return ""
```

命中就打 `[拒收] <文件>: <节点> —— <原因>` 并跳过（**不静默丢**，文件仍留在 `out/` 里可查）。

**为什么选收集端而不是改 11 个协议脚本**：逐个修"按字段位置取值"的解析是另一件事，风险与工作量都大得多；
而两条产品共用一个收集口 —— 把坏产物挡在这里，好产物自然在"同名去重"里赢。**写入端不动**，
即协议脚本仍然会把那些文件写进 `out/`（只是再也进不了产品）；这一点如实留在 §9 F-A2 与 U9。

**范围**（只判"一定用不了"，不判"好不好"）：证书文件名当 `server`/`sni`/`servername`；
`reality-opts` 在但 `public-key` 为空。真机上跑修后代码：**19 节点 / 0 条被拒**（没有误伤任何合法产物）。

---

## 2. RN：真实命令与原始输出片段

### 2.1 缺陷确认（改前）

```
$ cd /root/catmi/mihomo && python3 src/share/link_check.py --out-dir out --conf-dir conf
  [拒发] anytls_share-01.txt: anytls://107.173.154.178:50877 —— 链接里的凭据已不在任何当前节点里 …
  [拒发] hysteria2_share-01.txt: hysteria2://107.173.154.178:21168 —— 链接里的凭据已不在任何当前节点里 …
  [拒发] hysteria2_share-10.txt: … 23512 …   [拒发] hysteria2_share-11.txt: … 22737 …
  [拒发] reality_share-04.txt: vless://107.173.154.178:42099 —— 端口 42099 无人监听 …
  [拒发] trojan_share-01.txt … [拒发] tuicv5_share-01.txt … [拒发] tuicv5_share-09.txt … [拒发] vless_share-01.txt …
[拒发] 9/12 条分享链接与当前监听不一致 (这些都是连不上的死链)
```

改前 hy2 产物（**原样**）：

```
hysteria2://a2c318238c743fb6021d99c6e7939acd@107.173.154.178:21168?sni=hxicc.catmicos.dpdns.org&insecure=0&alpn=h3&upmbps=50&downmbps=200&obfs=none#🇺🇸 HY2-01
hysteria2://f71c235e1b5e8a510bd33f24dd0212f1@107.173.154.178:20309?sni=www.amazon.com&alpn=h3&pin=…&upmbps=50&downmbps=200&obfs=none#🇺🇸 HY2-02
```

**"谁在听"的独立事实**（`ss -ulpn`，pid 119320）：只有 `25682`（mHysteria201-TLS）与 `20309`（mHysteria202-TLS）在听；
`conf/config.d/hysteria2-01.yaml` 的真实端口是 **25682**、密码 **0647a947-…** —— 与改前产物（21168 / a2c31823…）**根本不是同一个节点**：
产物不是"旧值"，是**指向已不存在节点的死链**。`hysteria2-10/11` 连子配置都没有（孤儿产物）。

### 2.2 重建走的是哪条路径（**没有手改任何一个字节**）

* 逐节点产物重建 = `hysteria2 面板 → 5) 导出所有节点订阅` → `export_subscription()` → `rebuild_client_silent()` → `hy2_link()`。
  用 PTY 驱动真菜单（面板自己就是这么调 `BASE_DIR=… bash src/conf/hysteria2.sh`）。
* "同步改已有产物" = `server.sh 13→6` 里那两个函数：`m_hy2_bw_set()` / `m_artifacts_apply_hy2_bw()`。
* 清理陈旧产物 = `server.sh 13→4` 的两个函数：`m_artifacts_clean_orphan 1`（只报告）/ `m_artifacts_clean_orphan`（执行）。
* 建分享 = `share_gen_tag_auto all 0 24`（`src/share/share.sh` 末尾那条；与面板「生成分享链接」**同一条** `_share_create_records()` 创建路径）。

> 说明：完整 `server.sh` 面板通过 PTY 驱动时 SSH 会话两次被远端关闭（`Connection to … closed by remote host`，与面板交互无关的会话层问题），
> 因此除 hysteria2 子面板（稳定）外，其余步骤直接调用面板菜单**调用的那几个函数**（同一份代码，少了 `read` 与菜单派发）。
> 中途一次的残留进程（`drive.py` + `server.sh`）已 kill，`.hy2-bandwidth` 当时已被面板 setter 写成 `45 170`，正好接上下面的实验。

### 2.3 改后 hy2 产物（**完整一行**，密码未脱敏，与仓库口径一致）

```
hysteria2://0647a947-6f77-4a91-8df0-8ff9f2d5e720@107.173.154.178:25682?sni=hxicc.catmicos.dpdns.org&insecure=0&alpn=h3&up=60&down=200&upmbps=60&downmbps=200#HY2-01
hysteria2://f71c235e1b5e8a510bd33f24dd0212f1@107.173.154.178:20309?sni=www.amazon.com&alpn=h3&pinSHA256=b8f8fc0516c13230f65c2a4a728daa047353aaf8eadf76263562c60a9baa9a03&up=60&down=200&upmbps=60&downmbps=200#HY2-02
```

### 2.4 hy2 重建前后逐参数对比

| 参数 | 改前 HY2-01 | 改后 HY2-01 | 改前 HY2-02 | 改后 HY2-02 |
|---|---|---|---|---|
| password | `a2c318238c743fb6021d99c6e7939acd`（**不在任何节点里**） | `0647a947-6f77-4a91-8df0-8ff9f2d5e720`（= `config.yaml` 里真在跑的） | `f71c235e…` ✓ | `f71c235e…` ✓ |
| port | `21168`（**无人监听**） | `25682`（**在听**） | `20309` ✓ | `20309` ✓ |
| `up` | **缺** | `60` | **缺** | `60` |
| `down` | **缺** | `200` | **缺** | `200` |
| `upmbps` | `50` | `60` | `50` | `60` |
| `downmbps` | `200` | `200` | `200` | `200` |
| `obfs` | `none` ← 一条坏条目让整批 0 节点 | **不写** | `none` | **不写** |
| pin 键名 | — | — | `pin`（mihomo 不认 → 自签节点必失败） | `pinSHA256`（+ 普通话产品里 `pin` 也写，给 Xray 系） |
| tag | `#🇺🇸 HY2-01` | `#HY2-01` | `#🇺🇸 HY2-02` | `#HY2-02` |

`hysteria2_client-0{1,2}.yaml` 与旧批量命名 `hysteria2_hysteria2_client-01.yaml` 的 `up/down` 也都落到 `"60"/"200"`。

### 2.5 清理结果

```
$ … m_artifacts_clean_orphan 1     →  10 0      (只报告: 10 个陈旧)
$ … m_artifacts_clean_orphan       →  10 10     (执行)
剩余分享链接: anytls_share-02/03, hysteria2_share-01/02, reality_share-01/02/03,
              trojan_share-01..05, tuicv5_share-01                    (13 条)
$ python3 src/share/link_check.py --out-dir out --conf-dir conf
[OK] 13 条分享链接全部与当前监听一致
```

被回收的 10 个：`hysteria2_share-10/11`（孤儿）、`reality_share-04`（孤儿）、`tuicv5_share-09`（孤儿+IPv6 死链）、
`anytls_share-01`（凭据已不在任何节点里）、`vless_share-01..05`（见 §6 的缺陷 F-A3，我自己那条面板跑出来的垃圾链接）。
`payload` 复测：`build_sub.py` 19 节点、`build_uri.py` 19 行、**0 重复**。

---

## 3. `.hy2-bandwidth` 覆盖实验（面板 setter 写 / 删 / 再重建）

| 步骤 | 动作（都是面板路径） | `.hy2-bandwidth` | 产物实测 |
|---|---|---|---|
| A | 面板 setter 写 `45 170` → hysteria2 面板 5 重建 | `45 170` | `up=45&down=170&upmbps=45&downmbps=45`？→ 实测 `up=45&down=170&upmbps=45&downmbps=170`；`hysteria2_client-01/02.yaml` 与旧批量文件均 `45/170` ✅ **覆盖生效** |
| B | 面板 13→6 的 apply 函数（`m_artifacts_apply_hy2_bw`） | `45 170` | dry-run `0` 处 / apply `0` 处（重建已是最新，无谓写盘被正确省掉） |
| C | 删掉状态文件 | **absent** | `m_hy2_bw_get` → `60 200`（回默认） |
| D | hysteria2 面板 5 再重建 | absent | `up=60&down=200&upmbps=60&downmbps=200`，**不写 obfs** ✅ |
| E | 面板 apply 函数 | absent | apply `3` 处 → 旧批量产物 `up: "30"` → `"60"`、`down: "200"` ✅ |
| 终态 | — | **absent** | 全部 hy2 产物 60/200；无 `obfs=none`（`hysteria2.txt` 聚合除外，见 §5 U2） |

**为什么最终不留 `.hy2-bandwidth`**：默认值本身就是 `M_HY2_UP_DEFAULT=60` / `M_HY2_DOWN_DEFAULT=200`（`src/lib/env.sh:753-755`），
留着文件是**冗余**且会把"用户设置过"这件事记成既成事实（覆盖实验本身就是用户设置）。所以按题目要求**删掉**，终态 = 默认 60/200。
（如果将来默认值要改，用户需要重新"设置过一次"才会被尊重 —— 这是留白的代价，记在 §5 U1。）

---

## 4. 带声明的测试分享（**交付地址**）

```
$ share_gen_tag_auto all 0 24        # = 面板「生成分享链接」同一条创建路径
   [OK] 已生成 /tmp/tmp.… (19 条链接, 13 处损失已报)
   (带内核声明: 同内核同发行版拉原生, 其余走普通话)
```

```
DECLARED_SHARE_URL:
http://107.173.154.178:9443/share/dbfffb5ccf7d49065c09bc6faa49e552?interop=1&kernel=mihomo&distribution=upstream&version=1.19.32&formats=uri%2Cupstream&url-upstream=http://107.173.154.178:9443/share/40b83e65448445151ae9088eea8c46db
```

* 主记录（普通话）= `dbfffb5ccf7d49065c09bc6faa49e552`（19 行分享链接）；原生附带 = `40b83e65448445151ae9088eea8c46db`（mihomo YAML）。两条成对。
* **`max_uses=0（不限）`、TTL=0（永久）** —— 它承担的是"M 服务端对外可用形态"的角色，不能到期就 404。
  实测记录字段：`primary role=primary max_uses=0 uses=None expires=0` / `native role=native max_uses=0 uses=None expires=0`。
* **上一版（24h）已按纪律撤销干净**：`share_delete` 报 `已删除分享链接 (主 46e88581225d... + 原生附带记录, 共 2 条)`；
  回读两条 `get --token` 都失败，**`curl` 旧地址 = HTTP 404**。`out/share_tag-all.txt` 已改写成新地址（内容复核过）。
* **内容哈希与重建结果一致**（上一版记录，重建逻辑未变）：
  `记录 content_sha256 = 3765dab2d4dd84e3a054a0b2…` == `build_uri.py --tag all 重建 sha256 = 3765dab2d4dd84e3a054a0b2…` ✅
* `share_list` 现状（3 条）：

```
编号 类型 / 范围        Token                              状态   已用/上限 过期时间     格式
1    [节点] all           40b83e65448445151ae9088eea8c46db   可用    0/∞       永久           原生
2    [节点] all           dbfffb5ccf7d49065c09bc6faa49e552   可用    0/∞       永久           普通话+upstream
3    [节点] all           ec23e4cb8196d688053de91240e52dae   已禁用 1/1         2026-10-08 20:33 旧记录(YAML)
```

* **CC 端用新地址拉一次**（真内核）：

```
[OK] 已写入 …/conf/providers/m-rn-declared.yaml (19 个节点)
[OK] 本次拉取: 原生 (mihomo YAML) —— 同内核同发行版 (mihomo/upstream) → 取原生
[OK] 解析出 19 个节点 (组名 m-rn-declared)
```

* **撤销路径也真跑过**（第一次重发时另建的一条一次性分享）：`share_delete` 成对删两条，回读两条都消失。

---

## 5. CC 客户端更新

* **更新前**：`src/VERSION = e71bf685c410`、`client.sh` sha256 `6f9f9cd7…`（2026-10-10 12:22 的构建，早于 `60fb4c5`），
  **没有** `src/lib/interop.py`、**没有** `src/lib/proxy_node_compat/`。
* **备份**：`/root/backup-prepush-cc-20261011-101946/src`（42 个文件，另存 `src-before.sha256` 逐文件哈希）。
* **更新方式**：`git archive HEAD src` 出一棵干净树（不是工作区，避免把 `M src/VERSION` 带过去）→ 按仓库 `src/manifest.txt`（**唯一真源**，52 条）逐个拷贝。
* **复核**：52/52 文件 sha256 与仓库 HEAD `src/` **逐字节相同**；`VERSION = 2faac830d9fd`；`client.sh = fc6555b9…`（= 仓库 HEAD）。
  客户端的 `src/conf/*.sh` 是服务端协议脚本、客户端不用，但它们在 manifest 里，**一起同步**以求整棵树可逐文件核对（不影响客户端行为）。
* 本轮修复 `4b09b7e` 后**只重推了 `client.sh`**（sha 复核一致）。

---

## 6. 同列验收（M 客户端 ← M 服务端，CC 真机）

CC：`mihomo Meta v1.19.32 linux arm64 with_gvisor`（pid 1364829，全程未重启）。
**CC 直连出口 = `183.210.249.163`（只有 v4、没有 v6）** → 所以 **`204` 单独不算成功**。
RN 的 CF 出口实测两个：v4 `104.28.201.80`、v6 `2a09:bac5:6210:3050::4d0:4f`（`curl -4/-6 cdn-cgi/trace`，`warp=on`）。

### 6.1 带声明地址 → 原生（19 节点）

```
$ cd /root/catmi/mihomo-client && bash src/client.sh node-sub "<DECLARED_SHARE_URL>" m-rn-declared
[OK] 已写入 …/conf/providers/m-rn-declared.yaml (19 个节点)
[OK] 本次拉取: 原生 (mihomo YAML) —— 同内核同发行版 (mihomo/upstream) → 取原生
[OK] 解析出 19 个节点 (组名 m-rn-declared)
```

### 6.2 逐节点真连（隔离内核实例 + 真 provider，判据 = 204 **且** 出口属于 RN 的 CF 出口）

| # | 节点 | HTTP | 出口 IP | 判定 |
|---|---|---|---|---|
| 1 | 🇺🇸 mAnyTLS02-TLS | 204 | `2a09:bac5:6210:3050::4d0:4f` | ✅ |
| 2 | 🇺🇸 mAnyTLS03-TLS | 204 | `104.28.201.80` | ✅ |
| 3 | 🇺🇸 mAnyTLS01-TLS | 204 | `104.28.201.80` | ✅ |
| 4 | 🇺🇸 mHysteria201-TLS | 204 | `104.28.201.80` | ✅ |
| 5 | 🇺🇸 mHysteria202-TLS | 204 | `2a09:bac5:6210:3050::4d0:4f` | ✅ |
| 6 | 🇺🇸 mVLESS01-REALITY | 204 | `104.28.201.80` | ✅ |
| 7 | 🇺🇸 mVLESS02-REALITY-gRPC | 204 | `104.28.201.80` | ✅ |
| 8 | 🇺🇸 mVLESS03-REALITY-XHTTP | 204 | `104.28.201.80` | ✅ |
| 9 | 🇺🇸 mTrojan05-CDN-gRPC | `000` | — | ❌（CDN 档位，与既有基线一致） |
| 10 | 🇺🇸 mTrojan04-CDN-WS | `000` | — | ❌（同上） |
| 11 | 🇺🇸 mTrojan01-REALITY | 204 | `104.28.201.80` | ✅ |
| 12 | 🇺🇸 mTrojan02-REALITY-gRPC | 204 | `104.28.201.80` | ✅ |
| 13 | 🇺🇸 mTrojan03-TLS | 204 | `104.28.201.80` | ✅ |
| 14 | 🇺🇸 mTUIC01-TLS | 204 | `104.28.201.80` | ✅ |
| 15 | 🇺🇸 mVLESS05-CDN-gRPC | `000` | — | ❌（CDN） |
| 16 | 🇺🇸 mVLESS04-CDN-WS | `000` | — | ❌（CDN） |
| 17 | 🇺🇸 mVLESS01-TLS-WS | 204 | `2a09:bac5:6210:3050::4d0:4f` | ✅ |
| 18 | 🇺🇸 mVLESS03-TLS-XHTTP-CDN | `000` | — | ❌（CDN） |
| 19 | 🇺🇸 mVLESS02-TLS-XHTTP | 204 | `104.28.201.80` | ✅ |

**=== declared: 14 通过 / 5 失败 ===**
5 条失败全是 CDN 档位节点，**与改造前基线逐条相同**（`three-way-interop-m.md` §4.3：CDN 节点 `delay=0`）。

★ 判据迭代一次，如实记下：首轮我把判据写成"出口 `104.28.*`"，得到 9/19，其中 5 条是"204 + 出口 `2a09:bac5:…`"。
查 RN 自身 `curl -6 cdn-cgi/trace` → 那正是 **RN 的 CF IPv6 出口**（RN 默认路由出 v6），而 CC 没有 v6 直连 → 这 5 条是真通过。
判据改成"出口 ∈ RN 的两个 CF 出口 且 ≠ CC 直连"后为 **14/19**。**没有为了好看而放水，也没有把 204 当成功**。

### 6.3 负对照（**必须失败，全部失败**）

| 负对照节点 | 构造 | HTTP | 判定 |
|---|---|---|---|
| `NEG-dead-port-hy2` | RN 上**早已没人听**的 21168（改前产物里那个死端口） | `000` | ✅ 正确失败 |
| `NEG-wrong-password-hy2` | 活端口 25682 + 错密码 `deadbeef…` | `000` | ✅ 正确失败 |
| `NEG-dead-socks` | `socks5://127.0.0.1:1` | `000` | ✅ 正确失败 |
| `NEG-bad-host-trojan` | host/sni = `fullchain.pem`（证书文件名当主机名） | `000` | ✅ 正确失败 |

### 6.4 声明缺失 / 原生 404 / URI 列表导入

```
# ① 裸主地址（地址上没有声明）
[Info] 本次拉取: 普通话 (URI 列表) —— 地址上没有内核声明
[OK] 解析出 19 个节点 (组名 m-rn-bare)          ← 不报错

# ② 声明在、原生地址 404（url-upstream 指向不存在的 token）
[Info] 本次拉取: 普通话 (URI 列表) —— 同内核同发行版 (mihomo/upstream) → 取原生；原生取件失败(HTTP 404) → 回退
[OK] 解析出 19 个节点 (组名 m-rn-404)          ← 回退且把原因打出来
```

**交叉验证（M 客户端自己吃 URI 列表）**：`①` 那条就是真跑的——provider 落盘为 **19 行 URI 列表**（非 YAML），
`[OK] 已写入 … (19 个节点, 分享链接由内核解析)`。**局限**：这条路径只验到"导入正确"，
没有对它再跑一遍逐节点真连（逐节点真连跑在原生 payload 上），见 §7 U1。

---

## 7. 缺陷 B / C 的复现与判定

### 7.1 B：`导入成功但 provider 里 0 个节点`（**c446d3f 没修好，本轮修掉**）

复现（真内核 + 真客户端，本地文件形态）：

```
[OK] 已写入 …/m-rn-veto2.yaml (2 个节点, 分享链接由内核解析)     ← 一条好节点 + 一条 hy2&obfs=none
[Warn] 内核只加载到 0/2 个节点 —— 这份订阅里有内核**整批拒绝**的条目
[Info] 一条坏条目就能让整组归零 (实测: hysteria2 写了 obfs 却没有 obfs-password)
[Info] 注意: 内核 -t **不加载 provider**, 它报 test is successful 不代表能用
[Error] 订阅里没有解析出节点
```

上面是**修后**。**修前（= `c446d3f`）**同一输入、同一内核：

```
[OK] 已写入 … (2 个节点, 分享链接由内核解析)
[OK] 解析出 2 个节点 (组名 …)          ← 内核实际 0 个 —— 静默假成功
```

结论：**触发源在服务端已被 `d794a33` 修掉**（新产物不写 `obfs=none`），但**客户端的"成功判据"没修** ——
它数文件行数，不数内核加载数。本轮 `4b09b7e` 把判据换成内核真加载数（见 §1.3）。

### 7.2 C：`FIELD_NAME_TRAP` 对每条 TLS 节点都触发（**确认是噪音，未改**）

带声明地址导入时，19 个节点里 **15 个**被判成 `SUPPORTED → 支持!`，理由文本**逐字相同**：

```
[兼容] 能力判定比旧判定更严 15/19 个:
       - 🇺🇸 mAnyTLS02-TLS: SUPPORTED → 支持!  (vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效)
       - 🇺🇸 mHysteria201-TLS: … 同上 …        - 🇺🇸 mVLESS01-REALITY: … 同上 …
       … 另外 3 个见 .compat.json
```

这些节点的 `sni`/`servername` 明明都写对了，却全部命中 —— 即**"每次 TLS 节点都报"的噪音**，与 `m-client-integration.md` 的 U2 一致
（规则选择器只有 `standard:tls`，没有"且键名写错"这个条件）。按纪律**未改规则语义**，如实记录。

---

## 8. 门禁前后数字

| 门禁 | 改动前 | 改动后 |
|---|---|---|
| `bash tools/check_all.sh` | **20/20**（本轮起点基线，实跑确认） | **20/20**（rc=0）。中途出现过 19/20（`发布脱敏`：canonical `40a9441` 的 `_comment` 点名 `sing-box-core`，命中本仓库既有规则 `对标项目\|sing-box-core`）—— **没有加例外、没有改副本**，而是回报 canonical 去掉点名；canonical `692566c` 改完并补了自己的数据卫生门禁后回到 20/20 |
| `bash tools/check_interop.sh` 断言数 | 39 通过 / 0 失败 | **45 通过 / 0 失败 / 0 跳过**（③+1、⑨+1、⑩+4） |
| `bash tools/check_share_products.sh` 断言数 | 40 通过 / 0 失败 | **43 通过 / 0 失败**（⑥ 新增 3 条） |
| 中途一次 19/20 / 一次 18/20 | — | `发布脱敏`（canonical 真值，已按第三条路解决）+ `管道早退`（我自己在 ⑥ 里写的 `\| head`，`141` 早退管道，已改 `awk 'NR<=N'`）+ `三家互通`（canonical 提交后副本真落后，已重新 vendor）。三次都是"我自己引入/真源变化"，逐条修掉 |

**反向证据（新断言在修前代码上必须红）**

```
① 声明往返（③）  —— 修前 interop.py (HEAD 版):
     bare parse -> None
     AssertionError: REVERSE-EVIDENCE: 修前这条断言红了 (裸查询串读不回声明)      [退出码 1]

② vendored（⑨）  —— 把 `出口 <CDN_IP>` 那版放回去:
     ❌ vendored 副本与 canonical 真源漂移: 与已提交真源漂移 1: data/rules.json
     (40 通过 / 1 失败, 退出码 1); 改回后 40 通过 / 0 失败

③ 客户端（⑩）    —— 同一套断言跑在修前的 client.sh 上:
     断言①  ❌ /tmp/m-col/rev/src/client.sh: line 1156: detail: unbound variable
              + [Error] 订阅里没有解析出节点
     断言②  ❌ 没说内核真加载数
     HTTP 形态（修前不崩, 因此这条最能说明"假成功"）:
       修前: [OK] 已写入 2 个节点 → [OK] 解析出 2 个节点     ← 内核实际 0 个
       修后: [Warn] 内核只加载到 0/2 个节点 → [Error] 订阅里没有解析出节点
```

---

## 9. 本轮发现的既有缺陷（**未修，如实列出**）

| # | 缺陷 | 证据 | 为什么没修 |
|---|---|---|---|
| **F-A1** | `out/hysteria2.txt` **聚合**文件没有任何重建/清理路径 | 部署版源码里对它的引用只有 5 处：`add_config` 的"去重追加"（`hysteria2.sh:716-718`）、`delete_config` 的 `sed "/#HY2-$pad$/d"`（`:829`，节点已不存在时根本不执行）、`export_subscription` 里的 `cat`（`:945`）。`link_check` 只认 `*_share-*.txt`，`m_artifacts_clean_orphan` / `m_artifacts_rm_artifacts` 也只碰 `*_client-*.txt` / `*_share-*.txt`。**面板里没有任何一步能重写它**。 | 题目要求"只能用面板路径重建，不许手改" —— 没有面板路径，就**不手改**。它的实际影响面有限：分享 payload（`build_uri.py`/`build_sub.py`）不读它，只有 `hysteria2_subscribe.yaml` 的尾部"分享链接"段会带上它（因此该文件里仍有 5 行旧值 + 重复的 HY2-02 + `obfs=none`） |
| **F-A2** | 单协议 `rebuild_client_silent` 对 `all.sh` 批量生成的节点**产出无效产物** | 我跑面板 5 之后：`vless_client-01..05.yaml` = **非法 YAML**（`vless://uuid:@fullchain.pem:…`，UUID 解析成字面量 `uuid:`，主机名解析成证书文件名）；`trojan_client-01..05.yaml` = `name:`/`sni:` **空**；`reality_client-01..03.yaml` = `reality-opts.public-key` **空**；`tuicv5_client-01.yaml` = `sni: fullchain.pem` + `skip-cert-verify: true`（本该 false）。根因是 `grep -E "uuid:" … awk '{print $2}'` 这类**按字段位置取值**的解析遇上 `all.sh` 的列表形态（`- uuid: xxx` → `$2` = `uuid:`）。 | **已修（收集端，`23fe60f`）**：坏产物再也**压不过**好产物（§1.5）。**写入端未动** —— 协议脚本仍会把这些文件写进 `out/`，只是进不了两条产品；11 个脚本的字段位置解析未逐个改（范围取舍，见 U9）。我先把自己这次跑出来的无效产物删掉（15 个文件，改前不存在）并复核 payload 回到 19 节点且 `pbk`/`sni` 正确 |
| **F-A3** | 5 条 CDN 档位节点真连 `000` | §6.2 | 与改造前基线逐条相同（既有已入册结论），本轮不扩范围 |
| **F-A4** | `share_gen_tag_auto <非 all 的 tag>` 静默不产出 | `share_gen_tag_auto testrv 1 1` → 既没有 `out/share_tag-testrv.txt` 也没有任何报错，`printf '0'` 的返回被调用方忽略 | 未深挖（时间/范围），记 U3 |

---

## 10. UNKNOWN（没证据就不猜）

| # | 事项 | 为什么没结论 |
|---|---|---|
| **U1** | 普通话（URI 列表）provider 的**逐节点真连** | 只验到"导入 19 节点且形态是 URI 列表"；逐节点真连跑在原生 payload 上。既有报告在 mihomo 上验过 URI 列表是 17/19（trojan+REALITY 那两条丢 reality），本轮未复跑 |
| **U2** | `out/hysteria2.txt` 聚合（含重复 HY2-02 / `obfs=none` / 旧值）**本轮未清** | 没有面板路径（F-A1）；按"不许手改"留原样。若允许加一条面板清理路径（例如让 `m_artifacts_clean_orphan` 也按 `link_check` 重写聚合），下一轮可清 |
| **U3** | `share_gen_tag_auto` 在**非 `all`** 的 tag 上为何静默无产出 | 未深挖；影响是"想只分享某个协议桶时可能拿到空结果且无提示" |
| **U4** | 单协议重建缺陷（F-A2）的完整影响面 | 只逐字段比对了有同名节点的那 3 组（hy2/tuic/reality-01）；`trojan_client-*`（name 空）与 `vless_client-*`（非法 YAML）被 `build_sub` 丢弃所以没进 payload，但**别的协议/别的节点形态**是否还有同类字段位置解析问题，未逐脚本审 |
| **U5** | 我删掉的 15 个无效产物"本该由谁清" | 面板没有"删除无效产物"的路径（`m_artifacts_clean_orphan` 只删孤儿/死链）；本轮由我按"改前不存在"的事实清理并留证 |
| **U6** | `.hy2-bandwidth` 长期留白的代价 | 终态按题目要求不留文件（默认 = 60/200）。将来若改默认值，只有"用户在面板设过一次"才会被尊重；是否该在首次生成时落盘，未定 |
| **U7** | CC `subscriptions.json` 的 3 条测试台账由我清理（不是面板路径） | 客户端的删除走交互 `node_delete`；我删掉 provider 后台账会悬空，故按前缀移除并前后打印清单留证（`config.yaml` 已从测试前快照还原） |
| **U9** | F-A2 的**写入端**（11 个协议脚本的字段位置解析）未改 | 收集端已能挡住坏产物（`23fe60f`），但面板「重建客户端文件」仍会把那些文件写进 `out/`（只是进不了两条产品）。逐个改解析是另一件事，本轮按"范围由负责人定"只做最小可行的一半 |
| ~~**U10**~~ | ~~`发布脱敏` 与 canonical 逐字节的第二个冲突点~~ | **已解决（不是 UNKNOWN 了）**：canonical `692566c` 去掉点名 + 自建数据卫生门禁；M 侧重新逐字节 vendor（`accf189`），`check_all` = **20/20**，扫描面完整、零例外 |

| **U8** | 完整 `server.sh` 面板 PTY 驱动时 SSH 会话被远端关闭 | 两次，均在驱动真面板时；sshd 日志只记 `session closed for user root`，无 error。改用"直接调面板菜单调用的那些函数"绕过，未定位根因（不是服务异常：4 个 PID 与启动时间全程未变） |

---

## 11. 临时物清单与清理状态

| 位置 | 内容 | 状态 |
|---|---|---|
| RN `/tmp/m-col*`、`/tmp/m-col-drive.py`、`/tmp/m-col-s*.sh` | 菜单驱动、日志、before/after 哈希 | **已删**（`ls -d /tmp/m-col*` 无输出） |
| RN 残留进程 | 一次 PTY 驱动留下的 `drive.py` + `server.sh` | **已 kill**（`stray=0`） |
| RN 服务 | `xrayls 165517` / `mihomo 119320` / `sing-box 60510` / `proxy-share-service 69727` | **PID 与启动时间全程未变**（`Fri Oct 9 04:02:37` / `21:11:44` / `Fri Oct 9 05:08:02` / `Sat Oct 10 05:40:32`），未重启、未 stop |
| RN 测试分享 | 临时分享 `23141ef69fe3…` + 原生 `5c73b0d3…` | **已用面板 `share_delete` 撤销**，回读两条都已消失 |
| RN 交付分享 | `46e88581…` + `25b968f0…` | **保留**（上级要用它跑跨内核矩阵；TTL 24h，撤销见 §4） |
| CC `/tmp/m-col*`、`/tmp/cc-src-head.tar.gz`、`/tmp/mf-list.txt` | 真连夹具、日志、传输包 | **已删** |
| CC 测试组 | 5 个 provider + `nodes/*` + 3 条台账 + `config.yaml` 里的组 | **已清**（`config.yaml` 从测试前快照还原；`providers/` 与 `nodes/` 回到测试前 1 + 3 个文件；`subscriptions.json` 回到 3 条原有记录，`grep -c m-rn-` = 0） |
| CC 备份 | `/root/backup-prepush-cc-20261011-101946/src` + `src-before.sha256` | **保留**（回滚用，按题目要求） |
| CC 生产内核 | pid 1364829（`Fri Oct 9 18:45:42`） | **未重启**（只还原了磁盘上的 `config.yaml`；运行中的实例保持不动） |
| 本地 `/tmp/m-col` | 反向验证夹具（`/tmp/m-col/rev` 修前 client.sh）、哈希清单、check_all 日志 | 报告落盘后删除 |
| 生产 `ssh ds`（107.174.201.250） | — | **全程未连接、未写入任何字节** |

## 12. 复现方式

```bash
# 门禁（本地）
bash tools/check_all.sh            # 20/20
bash tools/check_interop.sh        # 45 断言 / 0 失败
PNC_CANONICAL=<other>/proxy_node_compat bash tools/check_interop.sh   # 指定 canonical 检出

# RN: 产物重建（面板路径）
BASE_DIR=/root/catmi/mihomo SELF_DIR=/root/catmi/mihomo/src/conf \
  bash /root/catmi/mihomo/src/conf/hysteria2.sh       # → 5) 导出所有节点订阅
# RN: 带宽覆盖（面板函数）/ 清理 / 建分享
source src/lib/env.sh; m_hy2_bw_set 45 170; m_artifacts_apply_hy2_bw
m_artifacts_clean_orphan 1 ; m_artifacts_clean_orphan ; share_gen_tag_auto all 0 24

# CC: 同列验收
cd /root/catmi/mihomo-client && bash src/client.sh node-sub '<DECLARED_SHARE_URL>' m-rn-declared
# 逐节点真连: 隔离内核实例 + 真 provider, 判据 = 204 且出口 ∈ {104.28.201.80, 2a09:bac5:6210:3050::4d0:4f}
```

---

# § 九宫格（M 客户端行）

> 执行机器：CC（armbian/arm64）｜客户端：**部署态** `/root/catmi/mihomo-client`（`client.sh` sha256 `fc6555b9…`，= 仓库 HEAD）
> 内核：`mihomo Meta v1.19.32`（生产 pid 1364829 全程未重启；逐节点真连用**隔离实例**，随机端口 + 临时 `-d`）
> 三条地址**原样使用**、一条都没动；三格各跑一次 `bash src/client.sh node-sub "<地址>" <分组>`。
> 出口判据（本行口径）：**204 且出口 IP ∈ RN 的 CF 出口集合**（IPv4 `104.28.*` 或 IPv6 `2a09:bac5:*`），且 ≠ CC 直连 `183.210.249.163`。
> ⚠ 前置事实：该客户端的**下载通道**是 `global=custom` → `http://192.168.1.178:2080`（`/root/catmi/mihomo-client/.dl-route`）。三格的取件都经过它。

## 1. 三格总表

| 项 | **X 服务端**（`kernel=xray`, 5 节点） | **M 服务端**（`kernel=mihomo`, 19 节点） | **SB 服务端**（`kernel=sing-box`, 13 节点） |
|---|---|---|---|
| 地址方言（服务端发出的） | **base64**(整体编码, 0 行 `://`) | **明文 URI 列表 + 2 行 `#` 注释** | **明文 URI 列表, 无注释** |
| 客户端决策 | **没有决策行** —— 在"读声明/报选择"之前就死在格式闸门 | `原生 (mihomo YAML) —— 同内核同发行版 (mihomo/upstream) → 取原生` | `普通话 (URI 列表) —— 服务端内核 sing-box ≠ 本机 mihomo` |
| reason | （未走到）`cross-kernel` 本该成立 | `native-listed` | `cross-kernel` |
| 解析数（客户端报） | **0** | **19** | 文件 13 行 → **报 11** |
| **内核真加载数**（`_provider_load_count`） | **没落盘**（provider 文件不存在） | **19**（= 文件行数，无差额） | **11**（**差额 2** ← 本轮最想看的格） |
| 逐节点真连 | 客户端路径无法跑（无 provider）；**改用内核直吃 base64**：5 节点 → **3 通过 / 2 失败** | **14 通过 / 5 失败** | **8 通过 / 3 失败** |
| 被丢掉的逐条理由 | 整体拒收：`[ERR] 不是合法的 Mihomo 订阅 (需要顶层 proxies: 列表)`（客户端预检，非内核） | **无**（19 条全保留） | 文件 13 → 内核 11：**`naive+https://…`(naive01-TLS)** 与 **`shadowtls://…`(shadowtls01-TLS)** 被内核**静默跳过**；另外 3 条 REALITY 真连失败 |
| UNKNOWN | 客户端补 base64 后 5 条真连会是多少（本轮只到 3/5） | 5 条 CDN 节点 `000` 的根因（与既有基线逐条相同） | 内核**为什么**跳过这两个 scheme（无任何日志行）/ 是否该由 SB 侧不发它们 |

## 2. 那一格：文件 13 行，内核只加载 11 个

```
$ bash src/client.sh node-sub "<SB 地址>" m-grid-sb
[OK] 已写入 …/conf/providers/m-grid-sb.yaml (13 个节点, 分享链接由内核解析)
[Warn] 内核只加载到 11/13 个节点 —— 这份订阅里有内核**整批拒绝**的条目
[Info] 一条坏条目就能让整组归零 (实测: hysteria2 写了 obfs 却没有 obfs-password)
[Info] 本次拉取: 普通话 (URI 列表) —— 服务端内核 sing-box ≠ 本机 mihomo
[OK] 解析出 11 个节点 (组名 m-grid-sb)
```

**差额的根因（挖到底了，不是猜）**：把同一个 provider 喂给隔离内核问它 `/providers/proxies/g`，

```
内核加载: 11
 ✓ 🇺🇸 rn anytls01-TLS   ✓ 🇺🇸 rn anytls02-REALITY   ✓ 🇺🇸 rn hysteria201-TLS
 ✓ 🇺🇸 rn reality01-REALITY   ✓ 🇺🇸 rn shadowsocks01-plain   ✓ 🇺🇸 rn trojan01-TLS-CDN
 ✓ 🇺🇸 rn trojan02-REALITY   ✓ 🇺🇸 rn tuic01-TLS   ✓ 🇺🇸 rn vless01-TLS-CDN
 ✓ 🇺🇸 rn vmess01-TLS-CDN   ✓ 🇺🇸 rn vmess02-REALITY
── 内核日志里的 provider 报错 ──
 level=info msg="Start initial compatible provider default"
 level=info msg="Start initial provider g"          ← **没有任何 error**
```

缺的两条是 `naive+https://…` 与 `shadowtls://…`。也就是说：**内核的订阅转换器对不认识的 scheme 是"静默跳过这一行"，既不报错、也不影响别的行**——
与 `obfs=none` 那种"一条坏条目让**整批**归零"不是同一个机制。两处都被这条钩子看见了，但**机制不同**：

* 整批归零（`obfs=none`）→ 内核直接拒绝整个 provider（前面 §7.1 实测 `missing obfs password`），加载数 0；
* 逐行静默跳过（不认识的 scheme）→ 加载数 0 < M < N，日志里**一个字都没有**。

★ **我这条钩子的提示文案对第二种情况是错的**：它写的是"内核**整批拒绝**的条目"，而这里并没有整批拒绝。
判据（以内核数字为准）是对的，**文案不精确** —— 本轮不顺手改（改代码要重新部署 + 重跑这一格），
如实记在这里，建议下一步把文案按 `loaded == 0` / `0 < loaded < N` 分成两句。

## 3. 方言交叉验证（本轮重点）

| 谁吃谁 | 结果 | 证据 |
|---|---|---|
| **M 客户端 ← SB 明文无注释** | ✅ **吃得下**，13 行 → 内核 11 | `[OK] 已写入 … (13 个节点, 分享链接由内核解析)`；provider 落盘 = **13 行 URI、0 注释、0 `proxies:`** |
| **M 客户端 ← X base64** | ❌ **吃不下**：`[ERR] 不是合法的 Mihomo 订阅 (需要顶层 proxies: 列表)` → 解析 0、**provider 未落盘** | 客户端预检要求"每行都是 `<scheme>://…`"或"顶层 `proxies:`"，base64 两条都不满足 |
| **内核 ← X base64**（同一份字节直接落成 provider） | ✅ **内核自己吃**：**5 节点** | 见下表；说明缺口**100% 在客户端预检**，不在内核能力 |
| M 自己发出的明文**带 2 行 `#` 注释** ← 别的客户端 | **本轮验不了**（不是我的客户端）→ 见下面的"payload 确切形态" | — |

**M 那条 payload 的确切形态**（给另外两行的人对照，逐字节）：

```
HTTP 200  content-type: text/plain; charset=utf-8   bytes=4834   lines=21
第 1 行: # mihomo--core 自动生成的分享链接 (URI 列表, tag=all)
第 2 行: # 共 19 条; 与原生 YAML 产品同一批节点
第 3..21 行: <scheme>://…  (19 条, 每行一条)
# 注释行数 = 2；含 "://" 的行数 = 19；没有任何空行、没有 base64、没有顶层 "proxies:"
```

即：**"2 行 `#` 注释 + 19 行明文 URI"是 M 普通话产品的固定形态**（注释由生产者写在文件头，见 `src/share/build_uri.py`）。
对端只要按"跳过 `#` 开头的行"处理即可；若对端把整份内容当 base64 解或要求首行即链接，就会失败。

## 4. 逐节点真连原始输出

### 4.1 M 格（原生 YAML，内核真加载 19）

```
🇺🇸 mAnyTLS02-TLS        204  104.28.201.80                    ✅
🇺🇸 mAnyTLS03-TLS        204  104.28.201.80                    ✅
🇺🇸 mAnyTLS01-TLS        204  104.28.201.80                    ✅
🇺🇸 mHysteria201-TLS     204  104.28.201.80                    ✅
🇺🇸 mHysteria202-TLS     204  104.28.201.80                    ✅
🇺🇸 mVLESS01-REALITY     204  104.28.201.80                    ✅
🇺🇸 mVLESS02-REALITY-gRPC 204 104.28.201.80                    ✅
🇺🇸 mVLESS03-REALITY-XHTTP 204 104.28.201.80                   ✅
🇺🇸 mTrojan05-CDN-gRPC   000  -                                ❌ CDN 档位(既有基线)
🇺🇸 mTrojan04-CDN-WS     000  -                                ❌ CDN 档位
🇺🇸 mTrojan01-REALITY    204  2a09:bac5:6210:3050::4d0:4f      ✅
🇺🇸 mTrojan02-REALITY-gRPC 204 104.28.201.80                   ✅
🇺🇸 mTrojan03-TLS        204  104.28.201.80                    ✅
🇺🇸 mTUIC01-TLS          204  104.28.201.80                    ✅
🇺🇸 mVLESS05-CDN-gRPC    000  -                                ❌ CDN 档位
🇺🇸 mVLESS04-CDN-WS      000  -                                ❌ CDN 档位
🇺🇸 mVLESS01-TLS-WS      204  104.28.201.80                    ✅
🇺🇸 mVLESS03-TLS-XHTTP-CDN 000 -                               ❌ CDN 档位
🇺🇸 mVLESS02-TLS-XHTTP   204  104.28.201.80                    ✅
=== gridM: 14 通过 / 5 失败 (内核真加载 19) ===
```

### 4.2 SB 格（明文 URI，内核真加载 11）

```
🇺🇸 rn anytls01-TLS       204  104.28.201.80                    ✅
🇺🇸 rn anytls02-REALITY   000  -                                ❌ REALITY 走链接形态
🇺🇸 rn hysteria201-TLS    204  104.28.201.80                    ✅
🇺🇸 rn reality01-REALITY  204  104.28.201.80                    ✅
🇺🇸 rn shadowsocks01-plain 204 104.28.201.80                    ✅
🇺🇸 rn trojan01-TLS-CDN   204  104.28.201.80                    ✅
🇺🇸 rn trojan02-REALITY   000  -                                ❌ REALITY 走链接形态
🇺🇸 rn tuic01-TLS         204  104.28.201.80                    ✅
🇺🇸 rn vless01-TLS-CDN    204  104.28.201.80                    ✅
🇺🇸 rn vmess01-TLS-CDN    204  104.28.201.80                    ✅
🇺🇸 rn vmess02-REALITY    000  -                                ❌ REALITY 走链接形态
=== gridSB: 8 通过 / 3 失败 (内核真加载 11) ===
```

（另 2 条 `naive+https` / `shadowtls` 根本不在内核的节点表里，所以连"失败"都轮不上 —— 它们是被静默跳过的。）

### 4.3 X 格（客户端不吃 base64；改由**内核直接吃同一份字节**）

```
内核直接吃 base64 payload → 加载: 5
🇺🇸 X-VLESS-WS_01         000  -                                ❌
🇺🇸 X-SS2022-02          204  2a09:bac5:6368:2da5::48c:5        ✅
🇺🇸 X-TROJAN-03          000  -                                ❌
🇺🇸 X-vless-xhttp07      204  2a09:bac5:6368:2da5::48c:5        ✅
🇺🇸 X-vless-xhttp08      204  104.28.195.192                    ✅
=== gridX: 3 通过 / 2 失败 (内核真加载 5) ===
```

★ 这两格的出口 IP 与 M/SB 格不同（`2a09:bac5:6368:…` / `104.28.195.192`），但都**落在 RN 的 CF 出口段内**
（`104.28.*` / `2a09:bac5:*`），且都不等于 CC 直连 —— 所以判通过。**这正是不该用"等于某一个固定 IP"当判据的原因**。

## 5. 负对照

| 负对照 | 期望 | 实测 |
|---|---|---|
| 死地址（不存在的 token） | 失败 + 说出原因 | 客户端路径 `[Error] 拉取失败 (HTTP **502**) —— 地址上没有内核声明`；**同一地址直连 curl = 404**。差异来源已定位：客户端下载通道是 `custom → http://192.168.1.178:2080`，502 由那一跳产生（直连与该代理各测一次：404 / 404，而客户端取件链路上得到 502）。**判据满足（失败且打出原因）**；502 的具体产生者未逐跳定位 → U11 |
| 死端口（RN 上早已无人听的 21168 + `127.0.0.1:1` 死 socks） | 全部失败 | `=== gridNEG: 0 通过 / 2 失败 (内核真加载 2) ===` ✅ |

## 6. 选取规则（逐节点真连没有取子集）

三格都是**全量**：M 19/19、SB 内核加载的 11/11、X 内核加载的 5/5，**没有取子集**，所以不需要选取规则。

## 7. 本节的 UNKNOWN（新增）

| # | 事项 | 为什么没结论 |
|---|---|---|
| **U11** | 死地址在客户端链路上得到 502（直连是 404） | 已定位到"下载通道 `custom → 192.168.1.178:2080`"这一跳是差异来源，但没逐跳抓包确认那个代理为什么把 404 变 502 |
| **U12** | 内核为何**静默跳过** `naive+https://` 与 `shadowtls://`（零日志） | 只测到事实（11/13，无 error 行）；没查 mihomo 订阅转换器的 scheme 白名单，也没确认"是不是该由 SB 侧不发这两个 scheme" |
| **U13** | X 格 5 条真连里那 2 条失败（`X-VLESS-WS_01` / `X-TROJAN-03`）的根因 | 客户端吃不下 base64，我是**绕过客户端**直接把字节落成 provider 跑的；对 X 产品的字段口径没有逐条核对（不是 M 客户端行该下的结论） |
| **U14** | M 客户端补上 base64 支持后，X 格 5 条真连会是多少 | 只证明了"内核能吃 5 条"，没证明"客户端补完能 5/5" |
| **U15** | M 那 2 行 `#` 注释，X/SB 的客户端是否容忍 | 不是我的客户端，本轮验不了；payload 确切形态已写在 §3 供对端对照 |

---

# § 地址收束（去掉 `version` + 同源原生地址写相对路径）

> commit `47f869e`（本地，未 push）｜**未重新部署 RN**（按要求，缩短效果在最后一轮统一分发时验）
> 门禁：`check_interop.sh` 45 → **49 断言 / 0 失败 / 0 跳过**；`check_all.sh` **20/20**

## 1. 三条契约与落点

| # | 契约 | 落点 |
|---|---|---|
| 1 | **不再产出 `version`** | `src/share/share.sh:_share_declare_url()` 的 `ver` 形参整个去掉，4 个调用点同步改（`share_regen` / `share_show_url` / `_share_create_records` ×2）。`build_declaration(version=…)` 参数**保留**（默认空）。**解析侧仍接受 `version`**（第三方可能写），只是不参与决策 |
| 2 | **同源 → 相对路径** `/share/<token>`，异源 → 绝对地址 | `share.sh:_share_native_ref()`：严格按 `(scheme, host:port)` 比同源。★ 只比 host 不比**端口**的话，同一台机器上不同端口的分享服务会被误判成同源，拼出来的相对路径会指向**另一个服务** |
| 3 | **解析侧拼回绝对地址**，位置在 `parse_declaration()`（`decide()` 签名不变） | `interop.py:_resolve_native_ref(ref, base)`：只认"以**单个** `/` 开头且末段非空"的路径引用；`//other.host/x`（协议相对，属于别的源）、`/share/`（目录）、`/x`（单段）、`../x` 一律**原样保留** → `decide()` 判 `bad-native-url`。**不引入完整 `urljoin` 语义，不猜** |

**不需要 bump schema**：旧实现看到相对路径 → `bad-native-url` → 回退普通话（安全、可见）。
`URL_SAFE = "/:@[]"` **保留不动**（绝对地址那条路还在；相对路径里只有 `/`，编码问题自然消失）。

## 2. 新地址实际长度

用 RN 现有那对 token（`dbfffb5c…` + `40b83e65…`）按新契约拼出来（**未在 RN 重发**）：

```
http://107.173.154.178:9443/share/dbfffb5ccf7d49065c09bc6faa49e552?interop=1&kernel=mihomo&distribution=upstream&formats=uri%2Cupstream&url-upstream=/share/40b83e65448445151ae9088eea8c46db
```

| | 长度 | 差 |
|---|---|---|
| 收束前（绝对 + `version=1.19.32`） | **231** 字符 | — |
| 收束后 | **188** 字符 | **−43 字符（−18.6%）** |

（门禁夹具里 host 是 `h:1`，所以那条断言显示 150 字符 —— 同一套形态，长度差来自 host/token 长度。）

## 3. 版本没有丢（契约 §1 的自证）

`version` 从**地址上**去掉，但原生产品的 record meta 里本来就自描述 —— RN 真机**只读**复核（未重发、未改）：

```
native  记录 40b83e65…:  interop=1  kernel=mihomo  distribution=upstream
                         kernel_version=1.19.32  role=native
                         parent=dbfffb5ccf7d49065c09bc6faa49e552  tag=all
                         content_type=text/yaml; charset=utf-8
primary 记录 dbfffb5c…:  formats=['uri','upstream']  native_token=40b83e65448445151ae9088eea8c46db
                         kernel_version=1.19.32
```

## 4. 门禁（每条都反向验证过，改回去必红）

**纯函数 1 条**（`check_interop.sh` ③）：无 `version` / 相对引用解析成绝对并判 native / **旧格式（绝对 + 带 `version`）仍判 native** / 5 个畸形相对路径必须 `bad-native-url` **且原样保留** / 裸查询串无 base 时也不猜。

**真 `share.sh` 产出上 3 条**（⑧，用假公共服务驱动真代码）：

```
✓ 声明里不再有 version (版本仍留在原生 record 的 meta 里)
✓ 同源时原生产品地址写成相对路径 (url-upstream=/share/…)
✓ 地址长度 150 字符 (收束前同形态是 231)
```

**反向证据（真跑，原始输出）**

```
① 纯函数断言跑在改前的 interop.py 上:
   parse(urls) = {'upstream': '/share/nat'}
   decide      = ('uri', 'bad-native-url')
   ❌ 红在『相对引用要解析成绝对地址』: 改前原样保留 `/share/nat`

② 生产者断言跑在改前的形态上 (真 token):
   改前地址: …?interop=1&kernel=mihomo&distribution=upstream&version=1.19.32
             &formats=uri%2Cupstream&url-upstream=http://107.173.154.178:9443/share/40b83e65…
   长度 = 231   改后 = 188
   ❌ 红在『声明里不再有 version』      → 改前命中(断言失败)
   ❌ 红在『同源写相对路径』            → 改前不命中
   ❌ 红在『地址长度 < 220』            → 改前不命中 (231)
```

**向后兼容单向量**（改前改后都必须**通过**，本例是"不许把旧地址读坏"）：旧格式绝对地址 + `version=1.19.32` → `parse` 里 `version` 仍被读成 `1.19.32`，`decide` = `native/native-listed` ✓
⇒ **RN 上现存的旧格式声明地址仍然可用**（这正是"不重新部署也不会坏"的保证）。

## 5. 本轮明确没做的事

* **没有重新部署 RN**（按要求）：RN 现在发出的声明仍是**旧的长格式**；它照样判 native（上一条）。
* 没有动 `URL_SAFE`（契约要求保留）。
* 没有顺手改上一轮那条钩子文案（`0 < loaded < N` 时"整批拒绝"不准确）—— 按要求留在 U12。
* 畸形相对路径的**取件端行为**（真去 curl `//other.host/x` 会怎样）没测：解析层已判 `bad-native-url`，取件根本不会发生。

## 6. 分发后真值（RN 已分发到 `47f869e`，线上声明已刷新）

RN 部署态核对（与仓库 HEAD 逐字节）：

```
/root/catmi/mihomo/src/lib/interop.py    7e1935bd4d8d9c62   == 仓库 HEAD
/root/catmi/mihomo/src/share/share.sh    35e12512299f8cc0   == 仓库 HEAD
四个服务 PID 未变 (60510 / 69727 / 119320 / 165517)
```

**刷新动作**：用**部署态**的 `_share_declare_url()`（= 面板「查看分享链接」`share_show_url` 里那条调用）现算同一条分享的声明，
落到 `out/share_tag-all.txt`。**没有动任何记录**（token / TTL / 次数 / 内容都没碰）。

```
刷新前: http://107.173.154.178:9443/share/dbfffb5ccf7d49065c09bc6faa49e552?interop=1&kernel=mihomo&distribution=upstream&version=1.19.32&formats=uri%2Cupstream&url-upstream=http://107.173.154.178:9443/share/40b83e65448445151ae9088eea8c46db
        231 字符

刷新后: http://107.173.154.178:9443/share/dbfffb5ccf7d49065c09bc6faa49e552?interop=1&kernel=mihomo&distribution=upstream&formats=uri%2Cupstream&url-upstream=/share/40b83e65448445151ae9088eea8c46db
        188 字符   ← 线上真值 (out/share_tag-all.txt 现为此行)
```

**幂等**：同一套输入再算一次 → 字符串相同、落盘字节相同（`cmp` 通过）。

**记录未变**：

```
token=40b83e65448445151ae9088eea8c46db role=native  enabled=True max_uses=0 uses=None expires=0
token=dbfffb5ccf7d49065c09bc6faa49e552 role=primary enabled=True max_uses=0 uses=None expires=0
token=ec23e4cb8196d688053de91240e52dae role=None    enabled=False max_uses=1          (旧禁用记录)
total: 3
```

**payload 未变（按**真实取回**对账，不只信服务端字段）**：

```
主产品  HTTP=200 bytes=4834 sha256=3765dab2d4dd84e3a054a0b2815bc2b0…  21 行 = 2 行 # + 19 行 URI
原生    HTTP=200 bytes=6321 sha256=71420ded8fdad3f64c6787ffc5d97062…  proxies(- name:) = 19
对账: 记录 content_sha256 与**实际取回** sha256 逐字节一致 (两条都 ✅)；且与刷新前记录的 sha256 相同
```

**CC 端真机（这一轮最重要的一个发现）**：

* **第一次拉：客户端 `interop.py` 还停在 `00ca35e`**（服务端分发了 `47f869e`，客户端没跟着分），于是：

```
[Info] 本次拉取: 普通话 (URI 列表) —— 原生取件地址不是可用的 http(s) 地址: /share/40b83e65448445151ae9088eea8c46db
[OK] 解析出 19 个节点
```

  ⇒ 这**正是契约 §2 预测的行为**：旧实现看到相对路径判 `bad-native-url` → **回退普通话**，
  **安全（19 个节点照样可用）且可见（原因原样打出来）**。契约的向后兼容不是纸面推论，是在一台**真落后的客户端**上实测到的。

* **同步 `src/lib/interop.py` 到 `47f869e`**（只这一个文件；旧文件存入 `/root/backup-prepush-cc-20261011-101946/src/lib/interop.py.pre-47f869e`，
  新文件 sha256 `7e1935bd4d8d9c62` == 仓库 HEAD）后重跑：

```
[OK] 已写入 …/conf/providers/m-rn-final.yaml (19 个节点)
[OK] 本次拉取: 原生 (mihomo YAML) —— 同内核同发行版 (mihomo/upstream) → 取原生
[OK] 解析出 19 个节点 (组名 m-rn-final)
内核真加载 = 19 节点 ; provider 形态 = mihomo YAML (19 proxies)
```

* **幂等**：同一条地址第二次 `node-sub` → 同样走原生、19 节点；去掉客户端自己加的时间戳注释后，两次落盘的 provider **逐字节相同**。
* CC 残留已清零（providers / nodes / 台账回跑前态，`config.yaml` 用客户端自己的序列化器还原），生产内核 pid 1364829 未重启。
