# 推送前验证 · 部署态复核 + 跨实现一致性（本轮）

> 时间：2026-10-11 ｜ 范围：RN（`ssh rn`，已授权自由配置）+ CC（`ssh CC`）。
> **DS（`ssh ds`，107.174.201.250）全程未触碰。**
> 目的：用户规矩「一定要测试到没什么问题之后，再上传 GitHub」。本文件记录**推送前**这一轮
> 的复核；推送本身与推送后的状态见文末。

---

## 0 · 为什么还需要一轮"推送前复核"

上一轮（`research/deploy/rn-reconcile-and-deploy.md`）把三个内核的仓库 HEAD **受控分发**到了 RN，
并跑了 3×3。但那之后：

* `xray--core` 的三家互通实现提交在**本地分支** `feat/three-way-interop` 上（**没合进 `main`，也没推**）；
* `mihomo--core`（`c446d3f`）、`sing-box-core`（`a7150e2`）的三家互通提交**只在本地**；
* 三家的 interop 报告都写了"真机验收"，但**验收跑在隔离副本里**，不是 RN 的部署路径
  （三家报告的更正说明见各自文件顶部横幅）。

也就是说：**「仓库里是对的」和「线上跑的是对的」当时并不等价**，而且这一点在报告里是含糊的。
本轮把这条含糊消掉。

---

## 1 · 分发前的部署态对账（用 sha256 说话）

对 RN 上的部署内容与仓库 HEAD 逐文件 sha256 比对：

| 内核 | 部署路径 | 分发前实际等于 | 与仓库 HEAD 的差 |
|---|---|---|---|
| X | `/root/conf/`（52 个文件）+ `/root/xray-panel.sh` | `55c736a`（50 个文件） | 缺 `conf/lib/interop.py`、`conf/lib/native.py`；`conf/share.sh` 旧；`xray-panel.sh` 缺两行库清单 |
| M | `/root/catmi/mihomo/src/` | `54672782`（2026-10-10 08:58 PDT） | 缺 `src/lib/interop.py`、`src/share/build_uri.py`；`client.sh`/`hysteria2.sh`/`core_mgmt.sh`/`share.sh`/`build_sub.py`/`manifest.txt`/`proxy_node_compat/**` 滞后 |
| SB | `/root/catmi/sing-box/conf/` + `install.sh` + `sing-box.sh` | `2c209b0`（2026-10-10 08:55 PDT） | 缺 `conf/interop.py`、`conf/link_guard.py`、`conf/uri_express.py`；`conf/share.sh` 滞后 |

判定方法不是看时间戳，而是：**在 RN 上 `find /root -name interop.py` 返回空**、
以及逐文件 sha256 与仓库各历史提交比对。X 的两份 interop 副本在登录机上都不存在。

> 这也解释了"报告说验过了、线上却没生效"：报告验的是**代码**（在隔离实例 + 真公共服务
> `:9443` + 真节点上跑），不是**部署**。两者都要做，缺一就是这次的教训。

---

## 2 · 受控分发（钉死 commit，先备份，后逐字节复核）

钉死并分发（`git archive` 冻结快照，不碰工作区）：

| 内核 | commit | tarball sha256（前 16） | 内容数 |
|---|---|---|---|
| X | `be4ec8e` | `ec12277a6b5f3fac` | 57 |
| M | `c446d3f` | `2ffac93a6f299678` | 59 |
| SB | `a7150e2` | `d934ab553a00b4d8` | 56 |

备份：RN `/root/backup-prepush-20261010-184809/`（`conf.tar.gz` / `xray-panel.sh` /
`mihomo-src.tar.gz` / `sb-conf.tar.gz` / `pids-before.txt`）。

分发后复核（脚本 `rn-deploy.sh` 自带，不是人眼看）：

```
X/conf/ 共 52  相同 52  不同 0  缺失 0
M/src/  共 53  相同 53  不同 0  缺失 0
SB/conf/ 共 35 相同 35  不同 0  缺失 0
xray-panel.sh 逐字节一致
```

**四个服务 PID 全程未变**：`xrayls 165517` / `mihomo 119320` / `sing-box 60510` /
`proxy-share-service 69727`（`nginx 958`）—— 分发只换管理脚本，不重启任何东西。

> 沿用了上一轮"先备份、再逐文件比对、只补差异"的做法，并且在脚本里把**服务 PID 不变**
> 做成一条会红的断言（而不是靠人不看）。

---

## 3 · 跨实现协议一致性（本轮新发现的两类真缺陷）

三家独立实现了同一份「声明 / 决策」协议，独立是刻意的，代价是会**静默漂移**。
本轮为此新建了 compat 侧的两个台子（见 `docs/interop-conformance.md`）：

* `tools/interop-vectors.json` —— 24 条向量 × 入参形态的**公共语料**；
* `tools/interop-conformance.py` —— 把语料喂给 X/M/SB **五份**实现，比对 `decide()` /
  参数名集合 / 交叉可读性；
* `tools/grid-audit.py` —— 对**线上**三条分享地址做声明合法性 + "带声明 vs 裸地址逐字节
  相同"的**现测**惰性证明 + 载荷形态识别。

### 3.1 `://` 当"是不是裸查询串"的判据（三家都有）

`parse_declaration()` 用 `"://" not in s` 判"这是裸查询串"。而裸查询串里**本身就有**
`url-<fmt>=http://…`：

* M 保留 `://` 原样（`URL_SAFE = "/:@[]"`，为可读性），于是 **M 自己产出的声明 M 自己读不回来**
  → `no-declaration` → **静默走普通话**；
* X / SB 把 url 值全编码，踩不到自己；但同一个外部入参（第三方未编码）一样被判成"没有查询串"。

**修法上有过一个坑，值得留档**：第一版修法把判据改成 `"://" in s` —— 那**没用**，
因为裸查询串里也有 `://`，`urlsplit(裸查询串).query` 是空串，症状一模一样。
正确的判据是**真探测 scheme**（`urlsplit(s).scheme`），不是换一个子串。
详细复盘：`docs/interop-conformance.md §3.1`。

三家均已修（X `0dc3b7f5…` 两份副本逐字节相同；SB `248744aa…` 两份逐字节相同；
M `44fc269`），并各自补了"三形态读回 + 决策一致"的断言（含**修前必须红**的反向证据）。
修后一致性台：**24 组向量 × 5 份实现，零分歧**。

### 3.2 canonical ↔ 内核 vendor 副本静默滞后

`proxy_node_compat/` 是唯一权威，三个内核各 vendor 一份只读副本。逐字节比对发现：

| 内核 | 结论 |
|---|---|
| `sing-box-core` | 8/8 文件与 canonical **逐字节相同** |
| `mihomo--core` | 只差 1 处：证据 `e-xray-hysteria2-outbound` 的出口 IP 被脱敏成 `<CDN_IP>` |
| `xray--core` | **3 处滞后**：`uri.py`（缺 `encryption=none` 哨兵值处理）、`cli.py`（还是硬编码 scheme 白名单）、`data/rules.json` 67/27 vs 68/29 |

X 那两处的实际后果不是风格问题：

* `encryption=none` 是 vless 分享链接规范的**必填默认哨兵**，不是"要求后量子加密"。
  旧代码把它建成 feature → `singbox.vless.encryption.never` 把**每一条常规 vless 链接**
  判成假 `UNSUPPORTED`（SB 侧实测 13 条真实链接里 2 条中招，且两条都真连 204 可用）；
* `cli.py` 的白名单外 scheme（如 `naive+https://…`）会被当成文件路径 → `FileNotFoundError`
  **整批崩掉**。

为此新增 `tools/check-vendored-sync.py`（本仓库持有 canonical，所以这个检查天然属于这里）。

---

## 4 · 分发脚本自己的一个缺口（SB 列实测暴露）

第一版 `rn-deploy.sh` 对 SB 分的是 `src/conf` + `src/sing-box.sh` + `install.sh`。
但服务端 `conf/share.sh` 的发布链要 import `compat2`（`conf/uri_express.py:49`），
而 **`compat2.py` 与 `lib/proxy_node_compat/` 在仓库里属于 `src/client/`，不在 `src/conf/`** ——
`install.sh` 也没有把它们放进部署 `conf/`。

真机上就炸在这里：

```
$ bash conf/share.sh create-all 0 2
[Error] URI 表达力标注跑不起来 (rc=1) —— 拒绝静默发布
    File "/root/catmi/sing-box/conf/uri_express.py", line 49, in <module>
        import compat2
ModuleNotFoundError: No module named 'compat2'
```

两条都值得记：

1. **部署清单必须包含跨目录的依赖**。"按目录分发"看起来干净，实际会漏掉
   "服务端要用客户端目录里的文件"这种情况 —— 而这只有**真跑一次发布**才会暴露，
   静态看文件列表看不出来。
2. **失败方式是好的**：发布闸门没有"跳过标注照常发布"，而是 `拒绝静默发布`。
   这正是本项目要的行为 —— 同一个缺口在别的项目里通常表现为"链接发出去了、
   原生格式那一条永远 404"。

修法在 `sing-box-core` 的 `d8b41c1`（install.sh 把两者装进部署 `conf/`），
`rn-deploy.sh` 侧同步补齐。

---

## 5 · 与服务端产物 / 客户端有关的验收

（见 `research/integration/three-way-interop-{x,m,sb}-deployed.md` 与 §6 的九宫格。）

---

## 6 · 九宫格（部署态，3 服务端 × 3 客户端）

三条带声明地址（全部**来自部署态代码**，永久有效、次数不限）：

| 服务端 | 主产品 | 原生产品 | 节点 | 普通话方言 |
|---|---|---|---|---|
| X | `…/share/7dd1e7a55a631fa5bd1f8446dbf118fc` | `…/share/ff3022fb954c1df70e69389b1dc595d5` | 5 | **base64** 的 URI 列表 |
| M | `…/share/dbfffb5ccf7d49065c09bc6faa49e552` | `…/share/40b83e65448445151ae9088eea8c46db` | 19 | 明文 URI 列表 **+ 2 行 `#` 注释** |
| SB | `…/share/ab03704acc0f2632201530d705660766`（IPv6） | `…/share/8526f930c8305cddb148c127497b10d9` | 13 | 明文 URI 列表，无注释 |

**我的中立台先验了服务端一侧**（`tools/grid-audit.py`，只读、不依赖任何一家的客户端）：

```
三条声明全部合法，且惰性已现测可证。
  X  主产品 base64(URI 列表, 5 行) / 原生 Xray JSON(outbounds=5, interop=1/kernel=xray)
  M  主产品 URI 列表(19 行, 另有 2 行 # 注释) / 原生 mihomo YAML(proxies≈19)
  SB 主产品 URI 列表(13 行) / 原生 sing-box JSON(outbounds=16)
```
"惰性"是**现测**的：同一 token 带声明与去掉查询串，两次 GET 的响应体 sha256 逐字节相同。

### 6.1 三个客户端各自跑出来的行

| 客户端 \ 服务端 | **X**（5） | **M**（19） | **SB**（13） |
|---|---|---|---|
| **xbd**（X 客户端） | **原生**（同内核同发行版）；5→5；真连 **5/6** | 普通话；19+2注释→**15**；真连 3/3（子集） | 普通话；13→**8**；真连 5/5（子集） |
| **mihomo 客户端**（M） | **✗ 死在格式闸门**：`不是合法的 Mihomo 订阅 (需要顶层 proxies: 列表)`。内核**直吃**同一份 base64 → 3/5 | **原生**；内核真加载 **19**；真连 **14/19** | 普通话；文件 13 → 内核真加载 **11**；真连 8/11 |
| **sb-client**（SB） | 普通话；`共=5 成功=4`；真连 3/4 | 普通话；`共=19 成功=16`；真连 14/16 | **原生**；13；真连 **13/13** |

读法：**对角线（同内核）三格全部走原生且可用**——这正是方案 A 的目的。
非对角线全部走普通话，且每一格都能说清"少了哪几条、为什么"。

### 6.2 这一轮九宫格真正买到的东西

不是"三个都能用"这个结论，而是**四条只有交叉跑才会暴露的缺陷**：

| # | 缺陷 | 表现 | 状态 |
|---|---|---|---|
| G1 | **M 客户端读不了 base64 的普通话列表** | `grep base64` 在 M 的 `client.sh` 里 0 处；而同一份 base64 喂**内核**能出 5 节点 ⇒ 缺口 100% 在客户端预检，不在内核能力 | **未修**（下一轮） |
| G2 | **xbd 把"解析器不认的链接"静默吃掉** | M 发 19 条只说"解析出 15 个"、SB 发 13 条只说"8 个"：没有计数、没有理由、没有痕迹 | **已修**（`xray--core 5b094c4` + 门禁 + 反向验证） |
| G3 | **SB 的 `to_sb` 无声丢掉 `anytls://` 与 `socks5://`** | `uri_to_outbound` 的分派元组漏项（`URI_RE` 认、`_std_uri` 里有死代码分支、只有分派表漏了）；后果是 M 丢 3 条、SB 自家普通话产品丢 2 条 | **已修**（`sing-box-core e861ab7`，门禁 38/4 → 42/0；M 13→16、SB 自家 9→11） |
| G4 | **部分成功时"丢了几个"看不见** | 不匹配 `URI_RE` 的行是裸 `continue`（连 `total` 都不加）；客户端只在"整份归零"时才回显跳过原因 | **已修**（同上；现在逐条报出） |

**一个被证伪的怀疑**：我们本来担心 **M 那两行 `#` 注释**会让别家客户端少导入或报错。
三行各自独立验过：xbd 正确跳过、sb-client 正确跳过（`to_sb` 显式跳过并已钉进门禁）、
用 canonical `parse_uri` 这个**独立实现**当中立裁判也是 19/19。
⇒ **注释不是问题**，写在这里免得下一轮再怀疑一次。

### 6.3 出口判据的教训（一次就够）

真连判据必须写成**出口 IP ∈ RN 的 CF 出口集合**（`104.28.*` **或** `2a09:bac5:*`），
不能写"等于某一个固定 IP"：实测同一批节点里 9 条经 `104.28.201.80`、5 条经 RN 的
WARP IPv6 `2a09:bac5:…`，X 格里还出现过 `104.28.195.192`。写成单值会把绝大多数判错。
**`204` 单独仍然不算成功** —— CC 直连本身就是 204（出口 `183.210.249.163`）。

### 6.4 还没有结论的（UNKNOWN，不许猜）

* M 客户端补上 base64 支持后，X 格会是多少（G1 修完才谈得上）；
* KB 级 scheme（`anytls` / `tuic` / `naive+https` / `shadowtls`）在**各家客户端**上的可用性 —— 各自的内核支不支持是另一件事，本轮只验到"不发出去/发出去读不读"；
* `X-VLESS-WS_01` 的 000/400 是**节点侧参数**还是**转换侧**（两家客户端都失败，未分离）；
* 三条"URI 里写了、出站里没有、compat 没提"的转换损失（tuic `alpn`、hy2 `pinSHA256`、hy2 `down_mbps`）—— 已登记为 `registry-gaps.md` 的 U-6/U-7/U-8。

---

## 7 · 第二轮分发（修复落地）—— 为什么必须有第二轮

第一轮分发的是 `be4ec8e` / `c446d3f` / `a7150e2`。之后三列各自又在**部署路径上**
修掉了真缺陷（X 的 `refresh` 会抹掉互通字段、SB 的 `install.sh` 从不装 `compat2`、
M 的 vendor 漂移与"导入成功但内核 0 节点"、三家共有的 `parse_declaration` 形态判据）。
如果只推 GitHub 不分发，**"仓库是对的、线上是旧的"这条就又回来了** —— 而消掉它正是本轮的全部意义。

第二轮 pin：

| 内核 | commit | 说明 |
|---|---|---|
| X | `810b538` | `c02e109` 形态判据 · `d8aa2d9` refresh 补成对且不抹声明 · `f641f76` 原生补第二道发布闸门 · `f4cef31` vendor 同步 · `810b538` 重打发布包 |
| M | `1896f24` | `44fc269` 形态判据 · `00ca35e` vendor 同步+门禁 · `4b09b7e` 「导入成功以内核真加载数为准」 · `1896f24` vendor `c2343b6` |
| SB | `e0ec3a1` | `5ed6206` 形态判据 · `6f23d65` 三形态门禁 · `d8b41c1` install.sh 装 compat2+lib · `f994b38` vendor · `ba1e670` 端口探活正则 · `e0ec3a1` 验证台 `ss` 桩 |

分发结果（同第一轮：脚本自带逐字节复核 + 服务 PID 断言）：

```
X/conf/ 共 52  相同 52  不同 0  缺失 0
M/src/  共 53  相同 53  不同 0  缺失 0
SB/conf/ 共 35 相同 35  不同 0  缺失 0
SB/conf/lib/ 共 9 相同 9  不同 0  缺失 0
SB conf/compat2.py 逐字节一致
五个服务 PID 全部未变
```

### 7.1 我自己在这一步踩的坑（留档）

第二轮我先把脚本改成"可以只分发其中一两家"，只上传了 `x-head.tar.gz` 与 `sb-head.tar.gz`。
但远端 `rn-deploy.sh` **无条件解包三个** —— 而 RN 的 `/tmp/dist-prepush/m-head.tar.gz`
还是**第一轮留在那里的旧文件**。于是它把 **M 的部署代码从 `1896f24` 回退成了 `c446d3f`**
（`src/lib/interop.py` 的 sha256 从 `53700a95…` 变回 `f15cf3f6…`）。

三条教训，都已经变成机制而不是注释：

1. **"上传了我才处理"不是优化，是正确性。** 旧的冻结快照留在远端就是一个陷阱 ——
   它长得跟新的一模一样。现在 `rn-deploy.sh` 取 `ONLY` 开关，`rn-redeploy.sh` 会**主动删掉**
   本次不分发的那些远端 tarball。
2. **复核必须只覆盖本次真的分发过的内核。** 当时 `verify` 段没有跟着 `ONLY` 走，
   它会拿**上一次**留下的 `dist-*` 目录去比 —— 那一次恰好内容相同所以没暴露，
   但那是运气。现在每一段（备份/差异/落盘/复核）都独立受 `ONLY` 约束。
3. **发现得比造成晚了一步，这是脚本的错不是人的错。** 我是在 `git show 1896f24:... | sha256sum`
   与 RN 现值的对比里发现回退的；如果只信脚本自己打印的"逐字节一致"，它永远不会红。

第三轮（M 修完 F-A2 与 TTL 之后）仍会按同一套走。

---

## 8 · 一条方法论教训：**"推没推"不能用本地 remote-tracking ref 回答**

本轮我犯过一次判错，值得单独留档，因为它会重复发生：

| 我以为 | 事实 |
|---|---|
| `xray--core` 的三条互通提交只在本地分支 `feat/three-way-interop` 上，**一个字节都没推** | `git ls-remote` 现查 `refs/heads/main` = **`be4ec8e`**，三条提交**早已在 GitHub 上**（约 `2026-10-11 00:17` 推送） |

**判错的机制**：我看的是 `git status -sb` 的 `## main...origin/main`（没有 ahead/behind）
和 `git log origin/main`。这两个都基于 **remote-tracking ref**，而它只在 `fetch` 时更新。
本地最后一次 `fetch` 停在 `2026-10-11 00:16:21`（当时远端是 `55c736a`），紧接着
`00:16:52` 才提交、`00:17` 左右推送 —— 之后**再没有人 fetch 过**，
于是本地视图永远停在"推送之前"。reflog 把这条时间线记得清清楚楚：

```
be4ec8e refs/remotes/origin/main@{2026-10-11 10:45:01}: fetch origin main: fast-forward   ← 本次现查
55c736a refs/remotes/origin/main@{2026-10-11 00:16:21}: fetch origin main: fast-forward   ← 最后一次 fetch
cf810be refs/remotes/origin/main@{2026-10-10 23:22:27}: update by push
```

**规则**（这条要写进纪律，不是"注意一下"）：

* 任何"已经推上去了吗 / 远端是什么"的判断，**必须用 `git ls-remote` 或先 `git fetch`**；
  `git status -sb` 的 ahead/behind 只回答"相对**我上次看到的**远端"，不回答"相对**现在的**远端"。
* 报告里凡写"未 push / 已 push"，都要附上**取证命令与它的原始输出**，而不是一句结论。
* 这条与本项目其它纪律同源：**结论必须挂在可复现的证据上**，
  而"本地缓存"是最容易被当成证据的那一类脏数据。

> 影响面：`three-way-interop-x.md` 顶部的更正横幅已经被我改过两次（第二次是改回来）。
> 现在那份横幅把"我判错 + 为什么判错"都留在正文里，而不是把错的那版删掉了事。

---

## 9 · 声明地址收束（用户拍板，本轮最后一件）

用户看到分享地址变长后拍板两件事，三家实现逐条对齐：

1. **地址上不再写 `version`**（它从不参与 `decide()`；解析侧仍必须接受它，第三方可能写）；
2. **同源时 `url-<fmt>` 写成以 `/` 开头的相对引用**（`/share/<token>`），异源仍写绝对地址。

| 内核 | 收束前 | 收束后 | 变化 |
|---|---|---|---|
| X | 229 | **178** | −51（−22%） |
| M | 231 | **188** | −43（−19%） |
| SB（IPv6 字面量） | 302 | **214** | −88（−29%） |

两个协议层面的判断：

* **不 bump schema**：旧实现读到相对路径会走 `_usable_url` → `bad-native-url` → 回退普通话。
  安全、可见、有 reason —— 正是要的降级方向。反向也验了：**旧格式（绝对地址 + `version`）
  仍判 native**，所以已经把地址发出去的人不会坏。
* **相对引用只在"完整订阅地址"这一形态下可解析**（裸查询串没有 base）。语料里那条向量
  因此显式收窄为 `forms: ["full-url"]` 并写 `_note`；裸形态下原样保留判 `bad-native-url`
  是**正确**行为。跨实现一致性台现在 **27 向量 × 5 份实现零分歧**。

### 9.1 三家的实现里各踩了一个坑（都留了档）

| 谁 | 坑 | 怎么发现的 |
|---|---|---|
| X | 判"末段非空"时先 `rstrip("/")`，于是 `/share/` 变成"末段=share"被判成合法路径，拼出 `http://h:9443/share/` 这条**看起来合法**的死链 | 门禁当场红（`native\|native-listed\|http://h:9443/share/`） |
| M | 同源判定只比 host 不比 **port**，会把同机另一个分享服务误判成同源 | 设计阶段自查，改成按 `(scheme, host, port)` 比 |
| SB | 把 X 那个 `rstrip` 版**故意植回去**做反向验证 → 门禁 48/1，红行正是"畸形相对形态被误拼" | 主动复现别人的坑，证明自己的实现躲开了 |

### 9.2 一处前提被证伪（SB 侧，如实记）

我在下发任务时写了"版本不会丢 —— 原生产品里本来就有自描述"。**SB 侧这句话不成立**：
`out/sb_client-all.json` 的顶层键只有 `['outbounds','route']`，单节点只有 `['outbounds']`；
`out/sb_meta-*.json` 是节点参数不是内核自描述。自描述**只存在于分享 meta**。

真实影响：只看地址的第三方不再能读到内核版本号（它本来也从不参与决策），
meta 里仍可读。"给原生产品补自描述"属于**新需求**，本轮不做，记在这里。

---

## 10 · 推送与清理（收尾）

四个仓库推送后**用 `git ls-remote` 现查**（不看本地 tracking ref，见 §8）：

```
✓ proxy-node-compat  远端 = 本地 = 752fd2f418ce
✓ xray--core         远端 = 本地 = 957e603c50e7
✓ mihomo--core       远端 = 本地 = 01890ef1bf01
✓ sing-box-core      远端 = 本地 = b25f5a0464f0
```

`mihomo--core` 那条多了一次提交：它的 `pre-push` hook 会按内容哈希重写 `src/VERSION`，
所以推完要**再补一个提交再推一次**才收敛（推送后 hook 不再改写，工作区干净）。

### 清理（用户决定：RN 上不留备份）

`research/deploy/tools/cleanup.sh`（可 `DRY=1` 预演）执行结果：

| 位置 | 清掉的东西 |
|---|---|
| RN | `/root/backup-20261010-085825`（70 MB，上一轮整棵内核目录）、`/root/backup-prepush-*`（本轮脚本层备份 3 个）、`/tmp/dist-prepush`、`/tmp/{x,m,sb}-col*`、`/tmp/.prepush-backup-dir` |
| CC | `/root/backup-cc-*`、`/root/backup-prepush-cc-*`（5 个，其中 SB 客户端那份 326 MB）、`/tmp/{x,m,sb}-col*` |

**服务与生产进程在删除前后逐行比对，完全未变**：

```
RN: xrayls 165517 / mihomo 119320 / sing-box 60510 / proxy-share-service 69727 / nginx 958
CC: xray 968528（10809/10808/1080 在听）/ sing-box 1444214（2080）/ mihomo 1364829（7890）
```

> 没有回滚点了 —— 这是用户明确选的（"两个都删，RN 上不留备份"）。
> 要说清的是：**删掉的都是可复现或未改动的东西** —— 三个内核的脚本层可由上表那四个
> commit 随时重放；节点配置本轮一个字节都没改。唯一不可再生的只有"当时的现场"。
