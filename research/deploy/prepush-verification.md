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

## 4 · 与服务端产物 / 客户端有关的验收

（见 `research/integration/three-way-interop-{x,m,sb}-deployed.md` 与 §5 的九宫格。）

---

## 5 · 九宫格（部署态）

（待填：三条带声明地址 + 3 客户端 × 3 服务端的解析/导入/真连结果。）
