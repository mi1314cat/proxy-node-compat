# RN 三内核「仓库 HEAD 受控分发 + 全链路验证」报告

> 执行时间：2026-10-10 23:53 – 2026-10-11 00:25（本地 CST）/ RN UTC-7 08:52–09:25
> 范围：RN（`ssh rn`，已授权自由配置）+ CC（`ssh CC`，192.168.1.178）。**全程未触碰 DS（生产）**。
> **未 push 任何仓库到 GitHub**（用户红线：验证干净后才由用户统一推送）。

---

## 0. 可复现性锚点：钉死的三个 commit

⚠️ **本轮工作期间仓库 HEAD 仍在移动**（`mihomo--core` 从开测的 `a3d1d4d` → `54672782`；`sing-box-core` `46105c0` → `2c209b0`）。
因此**不使用 HEAD 这个移动目标**，全部对账与分发钉死在下列 commit 上（已与上层确认）：

| 内核 | 仓库 | 钉死的 commit | 说明 |
|---|---|---|---|
| X | `xray--core` | `55c736afaaab6aafd59f34b7e99d7688ca5087b3` | fix(分享): 订阅载荷与 per-node 产物不一致 —— 补 ECH + 加一致性校验闸门 |
| M | `mihomo--core` | `54672782a1c06d962ac498d372c81672b0d9f5e9` | feat(客户端): 接入 proxy-node-compat |
| SB | `sing-box-core` | `2c209b0e017c26838bc7af5ba42849c0d341dd8c` | 收尾: 重新 vendor canonical 9b73cc9 + 删掉 encryption=none 绕行 |

分发用的冻结快照（本地 `git archive`，非工作区）：
```
x-head.tar.gz   sha256 964c26e651d8f3f82161f725cd6507bde28247293d01f4ed5ba8a0a3cb0fefda  (54 files)
m-head.tar.gz   sha256 8150c5518ee556388b18ed8f4387b85511f04aa15c135990bde407718bb98d94  (57 files)
sb-head.tar.gz  sha256 88d8a009e9fdabc0520bc6b99ca0ea01b0cd32050e04343cb56ef16ca0a3d2cf  (36 files)
```

> 注：`mihomo--core` 在本轮之后又新增了提交 `1c23d1b9c98c373d9e4448f498681383653275fb`（详见 §6 的 hy2 修复）。该提交是在本报告的分发**之后**产生的，未包含在上述 `m-head.tar.gz` 中。

---

## 1. 结论摘要（先看这里）

1. **用户担心的"线上已被更新过的内容"不存在。** 三个内核逐一比对 RN 部署文件 vs 仓库**全历史**（`git log --all`，不只 HEAD）：
   **X / M / SB 的 `LOCAL-CHANGE` 全部为 0** —— 每一个部署文件都能匹配到某个历史提交。
   ⇒ 没有任何"绕过仓库的手改"会被覆盖；也不存在"本地改动与修复冲突"需要你拍板的情况。
2. **但 X 的线上形态与我们原先的判断根本不同**（见 §3）：`/root/xray-panel.sh` 是**远程引导器**，
   `conf/*.sh` **从来没有落盘**，运行时从 GitHub raw `main` 拉。所以线上 X 跑的是 GitHub 上那版，
   仓库 HEAD 的修复**在线上完全没生效** —— 这解释了"仓库改好了、线上没变"。
3. 分发出去了。三个服务**全程没有重启过**（PID 从头到尾不变：xrayls 165517 / mihomo 119320 / sing-box 60510）。
4. **X 分享已原地刷新**（token 与地址不变），`陈旧!` → `最新`。
5. CC 侧 3×3：**X 列三格全部从"基本不通"变成"基本全通"**（详见 §5）。
6. 期间发现并修复了一个**仓库既有缺陷**（M 的 hy2 重建路径静默产出空 SNI），已提交未推送（§6）。
7. 清理完毕；备份保留在 RN/CC，删除时机见 §8。

---

## 2. 阶段 0 · 对账（三张表）

方法：RN 侧对每个文件取 `sha256 + size + mtime`（1725 个文件，`evidence/rn-manifest.tsv`），
与仓库**全历史**比对（`evidence/reconcile.py`，钉死 commit，逐文件跑 `git show <commit>:<path>` 与 `git log --all`）。
分类：`SAME` / `DIFFERS(stale，等于某个历史版本)` / `LOCAL-CHANGE(与任何历史版本都不一致)` / `RN-ONLY` / `REPO-ONLY`。

### 2.1 X（`xray--core` @ `55c736a`）

| 类别 | 数量 |
|---|---|
| SAME | **1**（`/root/xray-panel.sh` = `740fe1038cbac51d…` = HEAD 内容） |
| DIFFERS (stale) | 0 |
| **LOCAL-CHANGE** | **0** |
| RN-ONLY | 0 |
| REPO-ONLY | **50**（全部是 `conf/**`） |

**核心发现：X 的 `conf/**` 50 个脚本在 RN 上一个都没有。**
`/root/catmi/xray/` 里只有**运行时数据**：节点配置 `conf/*.json`（29 个）、产物 `out/**`（78 个）、二进制 `xrayls`、
`hy2gen.sh`/`outbound.sh`。管理脚本层是**不落盘**的。

证据 —— `xray-panel.sh` 的取文件优先级（`xray_fetch`，第 100–112 行）：
```bash
xray_fetch() {
    # 1) 从仓库检出目录直接跑 (开发时最常用)
    self="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
    [[ -f "$self/$rel" ]] && { printf '%s' "$self/$rel"; return 0; }
    # 2) 本次会话的缓存
    # 3) 镜像链  → XRAY_RAW=https://raw.githubusercontent.com/mi1314cat/xray--core/main
}
```
线上 `/root/conf` 不存在（已实测 `ls -d /root/conf` → No such file or directory），
⇒ 每次点菜单都走**第 3 条镜像链**，即 **GitHub main**。
而 GitHub main = `cf810be`，本地 HEAD = `55c736a`（那条载荷修复）。
**⇒ 修复在线上从未生效。**

### 2.2 M（`mihomo--core` @ `54672782`）

| 类别 | 数量 |
|---|---|
| SAME | 28 |
| DIFFERS (stale) | **13** |
| **LOCAL-CHANGE** | **0** |
| RN-ONLY | 4 |
| REPO-ONLY | **10** |

**13 个 stale**（都等于某个历史提交，安全覆盖）：`src/VERSION`、`src/client.sh`、`src/conf/TUIC.sh`、
`src/conf/all.sh`、`src/conf/hysteria2.sh`、`src/core_install.sh`、`src/lib/core_mgmt.sh`、`src/lib/env.sh`、
`src/lib/naming.py`、`src/manifest.txt`、`src/server.sh`、`src/share/build_sub.py`、`src/share/lan_config.py`。
（例：`src/conf/hysteria2.sh` 的部署内容 == `152bf55` 2026-10-08；`src/share/build_sub.py` == `152bf55`。）

**4 个 RN-ONLY —— 都不是独立手改，是重复/副产物**：
| 文件 | 判定 |
|---|---|
| `src/env.sh` | sha `fb14a25d…` **与 `src/lib/env.sh` 逐字节相同** → 错位重复副本（同为 stale） |
| `src/lib/manifest.txt` | sha `3751e000…` **与 `src/manifest.txt` 逐字节相同** → 错位重复副本 |
| `src/lib/__pycache__/naming.cpython-313.pyc` | 编译副产物 |
| `src/lib/cert.sh.bak-pre-certsync-20261009-005359` | 旧备份文件（2026-10-09 之前留的） |

**10 个 REPO-ONLY（HEAD 有、RN 没有 —— 本轮要新增）**：
`src/lib/nodecompat.py`、`src/lib/proxy_node_compat/**`（8 个）、`src/share/link_check.py`
（最后这个正是阶段 3 要用的验证工具，线上此前根本没有）。

### 2.3 SB（`sing-box-core` @ `2c209b0`）

| 类别 | 数量 |
|---|---|
| SAME | 25 |
| DIFFERS (stale) | **8** |
| **LOCAL-CHANGE** | **0** |
| RN-ONLY | 0 |
| REPO-ONLY | **1** |

**8 个 stale**：`src/conf/core.sh`(==`e32fb89` v1.0.43)、`src/conf/hysteria2.sh`(==`29243c0` v1.0.83)、
`src/conf/lib.sh`(==`b13b27d` 10-09)、`src/conf/outbound_uri.py`(==`b76d230` v1.0.60)、
`src/conf/share.sh`(==`b9c8814` 10-09)、`src/conf/uninstall.sh`(==`21df684` v1.0.50)、
`src/conf/vmess.sh`(==`b13b27d` 10-09)、`install.sh`(==`b9c8814` 10-09)。

**1 个 REPO-ONLY**：`src/conf/addr_family.py`（新增文件）。

> **注意**：`src/conf/hysteria2.sh` 的部署版本 == `29243c0`（**v1.0.83，10-04**），
> 即 §5 里 SB 链接 `obfs=none` 的那一版 —— 印证了"obfs 修复此前只在 HEAD、未部署"。

### 2.4 三张"独有/不同"汇总表

| 内核 | RN 独有（有 RN 无仓库） | 仓库独有（有仓库无 RN） | 内容不同 |
|---|---|---|---|
| X | 0（109 个运行时产物属设计内） | 50（`conf/**` 全部） | 0（面板 = HEAD） |
| M | 4（2 个重复副本 + 1 个 pyc + 1 个旧备份，**均非手改**） | 10（compat 层 + `link_check.py`） | 13（全部等于历史提交 = 旧版部署） |
| SB | 0 | 1（`addr_family.py`） | 8（全部等于历史提交 = 旧版部署） |

**⇒ 本地改动清单：空。没有需要你判断的条目。**（这是本阶段最关键的一条。）

---

## 3. 阶段 1 · 分发（各自正常路径，只补差异，先备份）

### 3.1 影响面（动手前记录）

| 动作 | 会重启什么 | 影响什么 |
|---|---|---|
| X：把 HEAD `conf/**` 放到 `/root/conf/` | **不重启任何服务** | 面板取脚本从"GitHub main"改为"本地 HEAD"（走面板自带优先级 1 路径） |
| M：把 HEAD `src/**` 覆盖到 `/root/catmi/mihomo/src/` | **不重启 mihomo** | 只换管理脚本；mihomo 读的是 `conf/`，不受影响 |
| SB：把 HEAD `src/conf/**` 覆盖到 `/root/catmi/sing-box/conf/` | **不重启 sing-box** | 只换管理脚本；sing-box 读的是 `config/` |

**重启前 PID 与状态**（阶段 0 采集，全 `active`）：
```
xrayls               pid=165517  since 2026-10-10 05:40:33 PDT
mihomo               pid=119320  since 2026-10-09 21:11:44 PDT
sing-box             pid=60510   since 2026-10-09 04:02:37 PDT
proxy-share-service  pid=69727   since 2026-10-09 05:08:03 PDT
nginx                pid=958     since 2026-10-02 08:31:19 PDT
```
**分发后与结束时这 5 个 PID 完全未变** ⇒ 全程零重启。

### 3.2 完整备份

```
/root/backup-20261010-085825/
├── xray-full.tar.gz      14 MB   (整棵 /root/catmi/xray，含 out/ conf/ 二进制)
├── mihomo-full.tar.gz    29 MB   (整棵 /root/catmi/mihomo)
├── sing-box-full.tar.gz  29 MB   (整棵 /root/catmi/sing-box)
├── units/                         xrayls.service / mihomo.service / sing-box.service + systemctl cat 快照
├── root-files/xray-panel.sh       /root/xray-panel.sh 原件
└── MANIFEST-before.tsv            1725 个文件的 sha256 + size + mtime
```
CC 侧备份：`/root/backup-cc-20261011-000528/{xbd-state.tar.gz, sb-client-state.tar.gz}`（58 MB）。

### 3.3 逐步命令与结果

**① 冻结快照**（本地，`git archive`，不碰工作区、不改仓库）
```bash
git -C xray--core    archive --format=tar.gz -o stage/x-head.tar.gz  55c736a conf
git -C mihomo--core  archive --format=tar.gz -o stage/m-head.tar.gz  54672782 src
git -C sing-box-core archive --format=tar.gz -o stage/sb-head.tar.gz 2c209b0 src/conf src/sing-box.sh install.sh
```
**② 传 RN 并解到 `/tmp/dist-*`**（`scp` + `tar xzf`）
**③ 差异清单**（RN 无 rsync，用 Python 逐文件 sha256 比对）

| 内核 | 目标路径 | NEW | CHANGED | SAME |
|---|---|---|---|---|
| X | `/root/conf/`（原不存在） | **50** | 0 | 0 |
| M | `/root/catmi/mihomo/src/` | **10** | **13** | 28 |
| SB | `/root/catmi/sing-box/conf/` | **1** | **7** | 24 |
| SB | `/root/catmi/sing-box/install.sh` | — | **1** | — |
| SB | `/root/catmi/sing-box/sing-box.sh` | — | 0（已同 HEAD） | — |

**④ 落盘**（`cp -a`，保持权限/属主；X 与 M 的 `.sh` 补 +x）
```bash
cp -a /tmp/dist-x/conf/.            /root/conf/
cp -a /tmp/dist-m/src/.             /root/catmi/mihomo/src/
cp -a /tmp/dist-sb/src/conf/.       /root/catmi/sing-box/conf/
cp -a /tmp/dist-sb/src/sing-box.sh  /root/catmi/sing-box/sing-box.sh
cp -a /tmp/dist-sb/install.sh       /root/catmi/sing-box/install.sh
```
**保留**：M 的 4 个 RN-ONLY 文件（`src/env.sh`、`src/lib/manifest.txt`、`__pycache__`、`cert.sh.bak-*`）**原样未删** —— 它们不属于本轮修复范围，删除需另行授权。

**⑤ 落盘校验**：X 50/50、M 51/51、SB 32/32 全部 sha256 逐一相同，0 mismatch。

**为什么这样算"正常路径"，不是"手改文件"**：
- **X**：`xray_fetch` 的**第 1 优先级**就是"仓库检出目录"（源码注释：「从仓库检出目录直接跑 (开发时最常用)」）。
  `/root/xray-panel.sh` 的 `dirname` = `/root`，所以 `/root/conf/<rel>` 正是它要找的位置。**这是面板自带机制，不是我发明的路径。**
  （另一条路是让面板去 GitHub 拉，但那必须 push —— 你的红线，所以走本地路径。）
- **M**：仓库 `docs/handover/deploy.md` §4「部署到服务器」原文就是 `tar czf /tmp/x.tgz src/` → `scp` → `tar xzf`。
- **SB**：`install.sh` 的 `rsync_files()` 原文就是 `cp -rf "$SRC_DIR/src/conf/." "$SRV_ROOT/conf/"` + `cp -f "$SRC_DIR/src/sing-box.sh" "$SRV_ROOT/"`。
  唯一差别：`$SRC_DIR` 从"GitHub clone"换成我冻结的 tar（因为不能 push）。已记录在案。

> **两条 GitHub 依赖路径本轮**不可用**（会拉到旧内容，因为不能 push）：
> M 的 `core_update_scripts()`（面板"更新脚本"）、SB 的 `install.sh`/`auto_update()`。**这两条路在验证干净并 push 之前，不要用来更新 RN。**

---

## 4. 阶段 2 · 重建受影响的节点与产物

### 4.1 X 订阅载荷 —— ✅ 已原地刷新（关键一步）

上线分享是**一次性快照**，只在创建/手工 refresh 时生成。线上那条 `f64f61ce…` 建于 20:47，而载荷修复 23:53 才到 ⇒ 不刷新的话"面板和链接全绿，用户拿到的还是老内容"。

```bash
cd /root && bash /root/conf/share.sh refresh
# → [--] 分享 f64f61ce35e4… 是旧版生成器建的 (schema=无, 现为 2), 重建内容
# → [--] 已刷新 1 条分享链接的内容 (token 与地址未变)
```

| | 刷新前 | 刷新后 |
|---|---|---|
| 字节 / sha256 | 944 B / `c09903d6014b87d2…` | **1472 B** / `2bebe127e2f31c04…` |
| hy2 `sni` | `sni=107.173.154.178`（**IP**） | **`sni=moontv.6896698.xyz`**（域名） |
| hy2 带宽/alpn | 缺 | **补回 `alpn=h3&up=50&down=200&upmbps=50&downmbps=200`** |
| xhttp07 | 无 `sni` | **补 `sni=moontv.6896698.xyz`** |
| xhttp08 | 无 `sni`/`ech` | **补 `sni=` + `ech=AGX+DQBhAAAgACA…`** |
| `share.sh list` | `陈旧!` | **`最新`** |

**一处例外（已留痕，非回归）**：xhttp07 载荷仍指向源站 `107.173.154.178:8443`，
不带 ECH。新脚本自己给出的判定：
> `提示: vless-xhttp07: 与 vless-xhttp_share-07.txt 核对通过 (endpoint-cdn-vs-origin); 端点不同: 产物 moontv.6896698.xyz:443 / 载荷 107.173.154.178:8443 —— 按既有规则允许 (CDN 边缘 ↔ 直连源站), 但两者可达性不同, 这里必须留痕; ech: 产物为 CDN 形态, 载荷连源站故不写 —— 符合规则`

⇒ 这是**设计内的端点选择规则**，不是丢字段。CC 侧实测该节点**可用**（§5.1）。

### 4.2 M 分享产物 —— ⚠️ **有意未重建**（发现阻断缺陷，见 §6）

原计划用 M 自己的 `rebuild_client_silent 01/02`（复用现有节点、不新增监听）重建 hy2 产物。
实测**它会把 SNI 清空**：
```
/dev/fd/63: line 619: extract_cert_domain: command not found
结果: sni:   ← 空（原为 hxicc.catmicos.dpdns.org）
```
**处置：不保留坏结果。** 已从备份精确还原，三个文件 sha256 与重建前逐一相同
（`85eda893…` / `63f8e63b…` / `f45b545b…`），并删除重建时多出的 `hysteria2_client-01.yaml`。

**M 产物维持原状。** 其存量缺陷因此仍在（`down: "200 Mbps"` 脏值、`hysteria2_share-*.txt` 带 `obfs=none`、
`hysteria2_client-02.yaml` 的 `fingerprint:` 塞了证书 sha256）—— 但**生成器已修好，等 §6 的修复进仓库后重建即可**。

### 4.3 SB 产物 —— 部分重建

**A) 生成器已修好（决定性证据）**：用仓库自带 `tools/check_share_links.sh` 的**动态自测**（在 `/tmp` 沙箱里用**已部署的** `conf/*.sh` 真实生成，不碰防火墙/systemd/公共服务）：
```
== A. 动态自测 (真实 conf/*.sh 在 /tmp 沙箱里生成) ==
  [OK]   A1 hy2 (无混淆): 1 条链接全部通过
  [OK]   A2 hy2 (开 obfs): 1 条链接全部通过
  [OK]   A3 vmess (TLS): 1 条链接全部通过
  [OK]   A4 vmess (REALITY): 1 条链接全部通过
  [OK]   A5 vless (TLS): 1 条链接全部通过
```

**B) 存量产物扫描发现真实缺陷**（生成器修好 ≠ 存量产物自动变好）：
```
  [FAIL] sb_share-hysteria201-TLS.txt: 带无效 obfs 参数 (obfs='none') → 对方 missing obfs password, 整条订阅 0 节点
  [FAIL] sb_share-vmess01-TLS-CDN.txt: vmess 链接带了 #片段 → mihomo format invalid → 0 节点
  [FAIL] sb_share-vmess01-TLS-CDN.txt: JSON 缺 ps 字段
  [FAIL] sb_share-vmess02-REALITY.txt: vless 链接的 encryption='aes-128-gcm' 非法 (vmess+REALITY 曾被误写成 vless://)
  [FAIL] sb_links-all.txt: 同上 3 类
```
`vmess02-REALITY` 那条**确实是以 `vless://` 发出的**（节点是 vmess+REALITY，链接却是 vless 且 `encryption=aes-128-gcm`）—— 正是任务里点名的"vmess 链接"缺陷。

**C) 已用仓库自带工具清理 obfs**（`--fix` 是工具文档化的功能，非手改）：
```bash
bash tools/check_share_links.sh --out-dir /root/catmi/sing-box/out --no-gen --fix
# → [FIX] sb_links-all.txt: 修掉 1 行 / sb_share-hysteria201-TLS.txt: 修掉 1 行
```
清理后：
```
-before  hysteria2://…@107.173.154.178:31001?sni=hxicc.catmicos.dpdns.org&obfs=none&obfs-password=&alpn=h3
+after   hysteria2://…@107.173.154.178:31001?sni=hxicc.catmicos.dpdns.org&alpn=h3#🇺🇸 rn hysteria201-TLS
```
**D) 未修复的存量项**：vmess 的 `#片段` / 缺 `ps` / vmess02 误发 vless —— 这三项**只能靠重新添加该节点来重生成**（SB 的协议脚本只有 `add/list/del/check`，没有"重建链接"入口）。
生成器侧已由 A3/A4 证明修好；**存量文件在重新添加节点前仍是旧的**，已如实记录。

### 4.4 本轮新建的东西（全部已记录）

| 类型 | 内容 | 现状 |
|---|---|---|
| 新建节点 | **无**。三个内核本轮**没有新建任何节点** | — |
| 新建分享 token | M `af94379eddc318e1b5e949ba183c1968`、SB `42037847b9011bc9c6c7ebcbeafacbcb` | **已在 §8 删除** |
| 刷新（非新建） | X `f64f61ce35e42b39a5f928d1c6d15ae5` | **保留**（是线上原有生产分享，token/地址未变） |

---

## 5. 阶段 4 · CC 侧跨内核验证（3 服务端 × 3 客户端）

**判据（硬性）**：`204` **不单独算成功**。每格都核对**出口 IP 是否为 RN 的 CF 出口 `104.28.x.x`**。
对照组实测 CC 直连 `generate_204` 就返回 `204` 且 `api.ipify.org` 为空 —— 证实"204 单独看会假阳性"，
本报告所有结论均以**出口 IP** 为准。

**CC 侧客户端构建（阶段 0 附带核对，你点名要的）**：

| 客户端 | 验证前 | 本轮动作 | 验证后 |
|---|---|---|---|
| X（xbd / Xray） | `lib/node.py 6be89561` / `compat.py c71d4a13` / `nodefilter.py a25d240a`，**无 `mux_decision`**（= 缺 mux/hy2/compat 三批） | 用 `Client/RUN.sh`（非破坏性覆盖，无 `rm -rf`）从**仓库 HEAD 目录**装（**绕过 stale tar**） | `node.py 5ea56a69` / `compat.py 08b1eba5` / `nodefilter.py 44001bf7`，**`mux_decision` 在场** |
| M（mihomo） | `/root/catmi/mihomo-client/mihomo` | 未改（本轮不涉及） | 未改 |
| SB（sb-client） | `share-state/to_sb.py 2625b600`（**旧构建，`_note` 崩溃版**） | 用 SB HEAD 的 `src/client/to_sb.py` 覆盖 | `b176f881`（含 `_skip_note` 模块级函数修复） |

> 客户端状态零改动：xbd `nodes/` 8 个、sb-client `nodes/` 203 个，与基线一致；三个客户端服务全程 `inactive`（真连一律用**隔离实例**）。

### 5.1 九宫格：本轮实测 vs 基线

| 服务端 ↓ / 客户端 → | **X（xbd / Xray）** | **M（mihomo）** | **SB（sing-box）** |
|---|---|---|---|
| **X 分享**（base64，5 节点） | **导入 5/5；真连 5/5 CF-OK**<br>hy2 / SS2022 / TROJAN-03 / xhttp07 / xhttp08 **全部 `204` + 出口 `104.28.195.192`**<br>基线：导入 4/5，真连 **1/5** ⇒ ✅ **转好** | **导入 5；真连 4/5 CF-OK**<br>SS2022 / **hy2** / **xhttp07** / **xhttp08** 全部 CF-OK；TROJAN-03 `000`<br>基线：真连 **1/5**（hy2 x509、xhttp07/08 503）⇒ ✅ **转好** | **导入 5/5；真连 4/5 CF-OK**<br>hy2 / SS2022 / TROJAN-03 / **xhttp08** CF-OK；**xhttp07 `000`**（见 5.2）<br>基线：真连 **1/5** ⇒ ✅ **转好** |
| **M 分享**（mihomo YAML，19 节点） | ❌ **导入 0/19**（19 条全被判"内核不支持"）<br>基线：同样 0/19 ⇒ ➖ **未变**（理由文案已变准） | **导入 19；真连 14/19 CF-OK**<br>5 条 CDN 节点失败（`mTrojan05-CDN-gRPC`/`mTrojan04-CDN-WS`/`mVLESS05-CDN-gRPC`/`mVLESS04-CDN-WS`/`mVLESS03-TLS-XHTTP-CDN`）<br>基线：14/19 ⇒ ➖ **持平** | ⚠️ **导入 18/19（不再崩溃）**，但**真连 0/18**<br>基线：`NameError: _note` **崩溃、0 字节输出** ⇒ **导入恢复，真连仍不通**（见 5.3） |
| **SB 分享**（sing-box JSON，16 出站） | ❌ **解析不出节点**<br>基线：同上 ⇒ ➖ **未变** | ❌ **provider 0 节点**（`file must have a 'proxies' field`）<br>基线：同上 ⇒ ➖ **未变** | **导入 14；真连 13/14 CF-OK**，出口 `104.28.201.80`<br>唯一失败 `rn-shadowtls01-TLS-out` 是 shadowtls 的**内层依赖跳**，本就不该单独使用<br>基线：13 导入、1 条测通 ⇒ ➖ **持平/更完整** |

**哪几格从不通变通 —— 明确清单**：
1. **X→xbd**：`hysteria-04`、`vless-xhttp07`、`vless-xhttp08` **三个节点从不通变通**（另加 TROJAN-03 从"被静默丢弃"变为"导入且可用"）。整格 **1/5 → 5/5**。
2. **X→mihomo**：`hysteria-04`（x509 错）、`vless-xhttp07`（503）、`vless-xhttp08`（503）**从不通变通**。整格 **1/5 → 4/5**。
3. **X→SB**：`hysteria-04`、`vless-xhttp08` **从不通变通**。（基线三格 hy2/xhttp07/xhttp08 同时报 503/503/x509，实为同一故障的两侧表现。）
4. **M→SB**：**整批导入从"崩溃 0 条"变为"18 条"** —— 但**尚未变成"真连得通"**，见 5.3。

**为什么 X 列会集体转好（三条独立原因，缺一不可）**：
- **服务端载荷**：`sni` 从 IP 改回域名 `moontv.6896698.xyz` → 消掉 mihomo/sing-box 的 `x509: cannot validate certificate for 107.173.154.178`（hy2 命中）。
- **服务端载荷**：xhttp07/08 补回 `sni=`（xhttp08 另补 `ech=`）→ 消掉 TLS 失败。
- **客户端 mux**：CC 的 X 客户端升到含 `ead7e3c` 的构建后，`mux_decision` 对 xhttp 硬拒 → 消掉"mux.cool 开在 xhttp 出站上"导致的 **503**（这就是基线里 hy2/xhttp07/xhttp08 三个"不同故障"都显示 503 的真因）。

### 5.2 归因：不通的格子分别是谁的锅

| 格 | 现状 | 归因 | 证据 |
|---|---|---|---|
| X→mihomo `TROJAN-03` | `000` | **客户端**（mihomo 的 trojan 链接解析器丢 reality） | 与 X 仓库 `278089d` 的既有结论一致；同节点在 xbd 与 SB 上均 CF-OK |
| X→SB `xhttp07` | `000`，日志 `connection download closed: unknown version: 72` | **客户端已知缺口**（`to_sb.py` **丢 xhttp 传输**） | 转换产物 `transport: null`（xhttp08 的 `ws` 则完整保留）；`tls.server_name` 正常。**你已点名此条另派修** |
| M→xbd | 0/19 | **客户端**（xbd 不解析 mihomo YAML，产出空壳） | 19/19 跳过理由均为"Xray 内核不支持该协议（anytls）" |
| SB→xbd | 解析不出 | **客户端**（xbd 不认 sing-box JSON，无格式探测/转换） | — |
| SB→mihomo | provider 0 | **跨生态格式不兼容（客户端）** | mihomo provider 只认 `proxies:`，不认 `outbounds:` |
| M→mihomo 5 条 CDN | `000` | **服务端产物 / CDN 侧**（未定论，同基线） | 与基线 5 条 CDN `delay=0` 完全重合，非本轮引入 |
| M→SB 全部 | 0/18 | **客户端**（`to_sb.py` 生成缺陷） | 见 5.3 |

### 5.3 M→SB 的精确归因（`to_sb.py` 缺 `tls.enabled=true`）

基线是**崩溃**（`NameError: _note`，rc=1、0 字节）→ 本轮 CC 换成 HEAD 版后**崩溃消失、成功转换 18/19**（唯一跳过的是 `mHysteria202-TLS`，即 M 存的 `up: "50 Mbps"` 脏值那条）。

但**真连 0/18**，逐条日志归因：

| 现象 | 条数 | 根因 |
|---|---|---|
| `FATAL create service: initialize outbound[0]: TLS required` | anytls×3 + tuic×1 | **`to_sb.py` 产出的 `tls` 块缺 `"enabled": true`** |
| `panic: nil pointer dereference` | vless/trojan REALITY ×5 | 同上（reality 也挂在没有 `enabled` 的 tls 上） |
| `unexpected HTTP response status: 400` / `http2: frame too large` / `bad HTTP protocol version` | CDN×4 + vless01-TLS-WS | 这些节点在 **mihomo 侧同样不通**（基线 5 条 CDN `delay=0`）⇒ 服务端产物侧问题，与转换器无关 |

实测证据（`sb-from-m.json` 里任取一条 anytls）：
```json
{"type":"anytls","tag":"e2e-🇺🇸 mAnyTLS02-TLS","server":"107.173.154.178","server_port":28725,
 "password":"f537cd20…",
 "tls":{"server_name":"hxicc.catmicos.dpdns.org","alpn":["h2","http/1.1"],"utls":{"enabled":true,…}}}
```
⇒ **有 `tls` 对象，但没有 `"enabled": true`**。sing-box 要求显式 `enabled`，因此报 `TLS required`。
**这是客户端转换器缺陷，不是服务端回归**（同一批节点在 mihomo 侧 14/19 可用）。
`to_sb.py` 的已知缺口清单应增至三条：① `xhttp` 传输丢失 ② `ech` 丢失 ③ **`tls.enabled` 未写**。

---

## 6. ⚠️ 期间发现并修复的仓库既有缺陷（M：hy2 重建路径静默产出空 SNI）

**现象**：M 的 `src/conf/hysteria2.sh` 调用 `extract_cert_domain`，但 `src/lib/cert.sh:230` 定义的函数名是
**`cert_extract_domain`**（少 `cert_` 前缀）。全树 `grep -rn "extract_cert_domain" /root/catmi/mihomo/` **只有调用、零定义**；
`git log --all -S "extract_cert_domain()"` 证明**全历史从未定义过**。

**既有缺陷，不是本轮引入**：备份里的旧版 `src/conf/hysteria2.sh`（sha `b630209ad1a23189`）**同样 7 处调用、0 处定义**。

**影响面**：7 处调用点（432/619/651/752/816/860/896），**只限 M 的 hy2**。
`all.sh` 与 `cert.sh` 用的是正确名 `cert_extract_domain`；其他协议脚本无此串；SB 侧同类扫描干净。

**实测后果**：`rebuild_client_silent 01/02` → `extract_cert_domain: command not found` →
`CERT_DOMAIN` 为空 → 产物 `sni:` **空**、分享链接变成 `?sni=&insecure=0`。
即"带宽/pin 修好了，却被 SNI 坏掉盖过去，比不重建更糟"。

**处置**（已获上层授权）：
1. **修 7 处调用点**：`extract_cert_domain` → `cert_extract_domain`（未加别名，避免两个名字日后分叉）。
   复查：全树该串 **0 命中**。
2. **补反向门禁** `tools/check_called_defined.sh`（新文件）：检出"**被调用但全仓库从未定义**"的内部函数，
   排除外部命令与 shell 内建；扫 `src/**/*.sh`。**反向验证**：在 `/tmp` 临时副本把名字改回去 → 门禁**变红并逐条列出 7 处**
   （临时副本已删）。形状覆盖已单独验证（10 种调用形态全部命中；引号内文本/注释/已定义函数/内建/外部命令不误报）。
3. 注册进 `tools/check_all.sh`：`run_gate "调用有定义" bash tools/check_called_defined.sh`
4. **门禁结果**：`bash tools/check_all.sh` → **`═══ 全部 19 项通过 ═══`**（exit 0）。
   > 说明：不是 18/18。加门禁**之前** `check_all.sh` **已经是 18/18** —— commit `212b6cd`（对角线闸门）在
   > "17"这个数字形成之后又加了一项；本次是 18 → 19，**没有删除/削弱任何断言**。
   `bash tools/check_diagonal.sh` → `10 通过 / 0 失败 / 1 跳过`（内核层因无 `MIHOMO_BIN` 跳过），无倒退。
5. **已提交，未推送**：`1c23d1b9c98c373d9e4448f498681383653275fb`
   —— *"fix(hy2): 重建节点 SNI 静默为空 —— 7 处调用名少了 cert_ 前缀 + 补反向闸门"*
   `git show --stat` 恰好 3 个文件：
   ```
    src/conf/hysteria2.sh         |  14 +-   (7 处 cert_extract_domain)
    tools/check_all.sh            |  15 +-   (注册 + 说明)
    tools/check_called_defined.sh | 525 +++   (新门禁)
   ```
   另一条工作流的未提交改动（`src/lib/proxy_node_compat/*` ×5、`tools/cc-verify-m.sh`）**未 stage、未触碰**。

**报告单列条目**：**「M 的 hy2 重建路径在修复前会静默产出空 SNI」—— 既有缺陷（备份中的旧版同样有），不是本轮引入。**

### 6.1 关于 M 的 P-M1 修复验证（确认副本是修复后的代码）

你要求确认。**确认：是修复后的代码。**
- 跑的二进制是 RN 上的 `/root/catmi/mihomo/src/share/build_sub.py`，它在 §3.3 已按 `54672782` 覆盖（差异表里 `CHANGED`），
  落盘校验 51/51 sha256 相同。
- 该文件第 69–70 行确实是归一化实现：`if naming is not None: return naming.match_key(name)`，
  且 `src/lib/naming.py:142: def match_key(name: str) -> str:` 在场 —— 即含 `naming.match_key()` 归一化的那版。
- 数据侧用的是**生产 `out/` 的副本**（`cp -a` 到 `/tmp/m-out-copy`，43 项），**没有动生产目录**。
- 结果：`--out-dir /tmp/m-out-copy --conf-dir /root/catmi/mihomo/conf --tag all` → **exit=0，stdout 6312 B，19 个节点**
  （基线同命令：`exit=1`、0 字节、`[ERR] 没有任何可用节点`）⇒ **P-M1 已修好**。

---

## 7. 阶段 3 · RN 侧验证结果

| 检查项 | 命令 | 结果 |
|---|---|---|
| 三服务 active | `systemctl is-active` | xrayls / mihomo / sing-box / proxy-share-service / nginx **全部 active** |
| X 配置测试（片段） | `xrayls -test -confdir /root/catmi/xray/conf` | **`Configuration OK.`** exit 0（仅 deprecation/REALITY 端口类 warning） |
| M 配置测试 | `mihomo -t -d /root/catmi/mihomo/conf` | **`test is successful`** exit 0 |
| SB 配置测试 | `sing-box check -D … -C …/config` | **exit 0** |
| 分享 URL 可取回、格式正确 | 见 §4.1 | X 1472 B / M 6312 B / SB 7360 B，均可取回 |
| **不再有 `obfs=none`** | 见 §4.3 | X 侧本就无；SB 链接 `--fix` 后已清；**M 链接存量仍有**（阻塞于 §6） |
| **hy2 有正确 SNI** | 见 §4.1 / §5 | X：`sni=moontv.6896698.xyz` ✅；SB：`sni=hxicc.catmicos.dpdns.org` ✅；**M：存量正确、但重建路径坏（§6）** ⚠️ |
| **vmess 有 `id`** | SB `check_share_links.sh` | 动态自测 A3/A4 **通过**（新生成器产出标准 `vmess://base64(JSON)` 且含 `ps`/`id`、无 `#片段`）；**存量 `vmess01` 仍缺 `ps` 且带片段**（需重新添加节点） |
| 产物端口/目标与真实监听一致 | **SB `tools/check_share_links.sh`** | 动态自测 A1–A5 **全 OK**；产物扫描 11 项 OK、4 项 FAIL（存量，见 §4.3） |
| M 链接/产物一致性 | **`src/share/link_check.py`** | 工具已随本轮分发**首次部署到 RN**（此前线上没有）；SB 侧同源闸门已覆盖 §4.3 的项 |

> `check_diagonal.sh` 与 `link_check.py --prune` 属 M 仓库本地工具、不在 RN 部署集内；
> `check_diagonal.sh` 已在本地仓库运行（§6：10 通过 / 0 失败 / 1 跳过）。

**SB 监听核实（纠正一次误判）**：SB 的 `share.sh create` 曾警告 31000–31013 未监听。
用**完整**（未截断）的 `ss -ltnp` 复核：TCP 12 个 + UDP 5 个，`31000–31013` **确实在监听**
（hy2/tuic 是 QUIC，走 **UDP**，只查 TCP 会漏）。此前"未监听"的警告来自工具判据只统计部分套接字。**节点是活的**，§5.1 的真连结果也印证了这点。

---

## 8. 阶段 5 · 清理

### 8.1 清理了什么

| 位置 | 内容 | 结果 |
|---|---|---|
| RN `/tmp` | `dist-x`/`dist-m`/`dist-sb`、`x-head.tar.gz`/`m-head.tar.gz`/`sb-head.tar.gz`、`m-out-copy`、`m-verify.*`、`oldm`、`mrestore`、`sbrepo`、`sb-check_share_links.sh`、`x-before.b64`、`x-after.b64`、`.xray-panel.*` | 已删 |
| RN 分享记录 | **本轮新建的 2 条测试 token**：M `af94379e…`、SB `42037847…`（各用 `share_client.py delete` 删除，返回 `{"deleted": …}`） | 已删 |
| CC `/tmp` | `xbd-head`、`xbd-iso*`、`m-iso-*`、`sb-iso-*`、`sbiso-*`、`c6-*`、`c9-*`、`xbd-rt-*`、`e2e`、`to_sb_head.py`、`.xbd_skipped.json`、`.xbd_node_err` | 已删 |
| 进程 | 全部隔离测试实例（mihomo / sing-box / xray × 数十次） | `pgrep` 复核**无残留** |

**清理后分享记录（只剩原有的）**：
```
xray    : 1 → f64f61ce35e4  active     ← 线上原有，本轮原地刷新（token/地址未变）
mihomo  : 1 → ec23e4cb8196  disabled   ← 原有，非本轮创建
sing-box: 0                            ← 本轮创建的已删净
```

### 8.2 保留了什么 / 为什么

| 保留项 | 位置 | 理由 |
|---|---|---|
| 分发后的 HEAD 脚本 | RN `/root/conf/`（50 个）、`/root/catmi/mihomo/src/`、`/root/catmi/sing-box/conf/` | **这就是本轮的交付物**，删了等于没分发 |
| X 分享 `f64f61ce…` | `proxy-share-service` | 线上**原有**生产分享；刷新只改内容，token/地址不变 |
| M 的 4 个 RN-ONLY 文件 | `src/env.sh`、`src/lib/manifest.txt`、`__pycache__`、`cert.sh.bak-*` | 非本轮修复范围，未经授权不删 |
| 原有服务与节点 | RN 三个服务 + 各自节点 conf | 生产资产，**本轮一个节点都没新建、没删除** |
| CC 客户端代码更新 | xbd `lib/*`、`to_sb.py` | 是验证前置条件（否则会把"客户端旧构建"误判成"服务端没修好"）；`to_sb.py` 留有 `to_sb.py.bak-pre3x3` |
| SB 产物 `--fix` 的 2 个文件 | `out/sb_links-all.txt`、`out/sb_share-hysteria201-TLS.txt` | 清理的是**无效参数**，属修复而非破坏 |
| **RN 全量备份** | `/root/backup-20261010-085825/`（70 MB，1725 文件） | 见下 |
| **CC 状态备份** | `/root/backup-cc-20261011-000528/`（58 MB） | 见下 |
| 证据件 | `research/deploy/evidence/`（本仓库） | 对账脚本、manifest、3×3 载荷原文 |

### 8.3 还原命令

**RN 整体回滚**（恢复分发前状态）：
```bash
# 0) 先看备份内容与清单
ls -la /root/backup-20261010-085825/
# 1) 回滚三棵目录（覆盖回分发前）
cd / && tar xzf /root/backup-20261010-085825/xray-full.tar.gz     -C /root/catmi
cd / && tar xzf /root/backup-20261010-085825/mihomo-full.tar.gz   -C /root/catmi
cd / && tar xzf /root/backup-20261010-085825/sing-box-full.tar.gz -C /root/catmi
# 2) 回滚 X 面板（本轮未改，但一并留档）
cp -a /root/backup-20261010-085825/root-files/xray-panel.sh /root/xray-panel.sh
# 3) 回滚服务单元（本轮未改）
cp -a /root/backup-20261010-085825/units/*.service /etc/systemd/system/ && systemctl daemon-reload
# 4) 撤销本轮新增的 X 本地脚本树（回到"面板从 GitHub 拉"的原始形态）
rm -rf /root/conf
# 5) 逐文件核对是否回到基线
diff <(sort -k4 /root/backup-20261010-085825/MANIFEST-before.tsv | cut -f1,4) \
     <(find /root/catmi/xray /root/catmi/mihomo /root/catmi/sing-box -type f -printf '%p\n' \
        | while read f; do printf '%s\t%s\n' "$(sha256sum "$f"|cut -d' ' -f1)" "$f"; done | sort -k2)
```
**SB 产物单独回滚**（只回 §4.3 的两个 `--fix` 文件）：
```bash
tar xzf /root/backup-20261010-085825/sing-box-full.tar.gz -C /tmp \
  sing-box/out/sb_links-all.txt sing-box/out/sb_share-hysteria201-TLS.txt
cp -a /tmp/sing-box/out/sb_links-all.txt /tmp/sing-box/out/sb_share-hysteria201-TLS.txt /root/catmi/sing-box/out/
```
**CC 回滚**：
```bash
# X 客户端代码
tar xzf /root/backup-cc-20261011-000528/xbd-state.tar.gz -C /opt/xray-browser-dialer
# SB 客户端
tar xzf /root/backup-cc-20261011-000528/sb-client-state.tar.gz -C /opt/sb-client
# 或只回 to_sb.py
cp -a /opt/sb-client/share-state/to_sb.py.bak-pre3x3 /opt/sb-client/share-state/to_sb.py
```

### 8.4 备份删除时机（建议）

- **`/root/backup-20261010-085825/`（RN）与 `/root/backup-cc-20261011-000528/`（CC）建议保留到**：
  1. 你确认 CC 侧 3×3 结论、并且
  2. §6 的修复决定好要不要 push、以及
  3. 线上观察 ≥ 24h（X 分享刷新后用户实际拉取正常）
  —— 三条都满足后即可删：`rm -rf /root/backup-20261010-085825` / `rm -rf /root/backup-cc-20261011-000528`。
- 磁盘占用：RN 70 MB / 14 G（5.9 G 可用），CC 58 MB。**不紧张，建议留满 24h。**

---

## 9. 复现本轮"新建测试分享"的一行命令（供你复核用）

已按纪律删除，需要时随时可重建（**不会**新增节点、**不会**重启服务）：
```bash
# M（复用 share_gen_tag_auto，参数：<tag> <次数 0=不限> <有效期小时 0=永久>）
cd /root/catmi/mihomo && bash -c '
  source src/lib/env.sh; source src/lib/ui.sh; source src/share/share.sh
  share_gen_tag_auto all 0 0'
# SB
cd /root/catmi/sing-box && bash conf/share.sh create all 0 0
# X（刷新已有分享的内容，token 不变）
cd /root && bash /root/conf/share.sh refresh
```

---

## 10. UNKNOWN（没测到 / 没定论的，一律不猜）

1. **X 的 `conf/**` 是否应该继续用"不落盘 + GitHub 拉"的形态**。本轮为了让 HEAD 生效，铺了 `/root/conf/`（面板优先级 1 路径）。
   长期看这是"本地检出"形态，与"线上从 GitHub 自助更新"是两种运维模型 —— **属产品决策，未替你定**。若要回到原形态：`rm -rf /root/conf`。
2. **xhttp07 载荷指向源站 `107.173.154.178:8443` 而非 CDN `moontv.6896698.xyz:443`**：新脚本自己判为"符合既有 CDN 边缘 ↔ 直连源站规则"并留痕。
   CC 侧实测该节点在 **xbd 与 mihomo 上都 CF-OK**，只在 **sing-box 上失败**（且已归因到 `to_sb.py` 丢 xhttp）。
   ⇒ **"端点选择规则本身是否最优"未定论**；"该节点可用"已实测。
3. **M 的 5 条 CDN 节点（`mTrojan05-CDN-gRPC` 等）为何不通**：本轮 14/19 与基线完全重合，**是产物陈旧还是 CDN 侧问题仍未深查**（沿用基线 UNKNOWN-2）。
4. **M 存量产物的 `down: "200 Mbps"` 脏值、`obfs=none`、`fingerprint:` 语义错位**：生成器已修好，但**存量产物仍未重建**
   （阻塞于 §6 的缺陷 —— 修好且 push 后即可用 `rebuild_client_silent` 安全重建）。**本轮有意未动。**
5. **SB 存量 `vmess01`（缺 `ps`、带 `#片段`）与 `vmess02`（误发 `vless://` + 非法 `encryption`）**：生成器已由动态自测 A3/A4 证明修好；
   **存量文件只能靠重新添加该节点来重生成**（SB 协议脚本无"重建链接"入口），本轮**未重新添加节点**（避免动生产节点），故存量文件仍是旧的。
6. **`to_sb.py` 的 `tls.enabled` 缺失**：本轮只做了归因（§5.3），**未修**（属客户端侧，你已另派）。
7. **CC 直连为何对 gstatic 返回 204**：本轮再次观测到（`204` 且 `api.ipify.org` 为空），未深查本机是否有透明代理/拦截 —— 仅作为测量口径注记。
8. **X 客户端 `xbd-client.tar.gz` 是 stale 的**（`lib/node.py == 6be89561`，**无 `mux_decision`**），落后于 `Client/` HEAD `5ea56a69`。
   本轮装 CC 时**绕过了这个 tar**（直接用 `Client/` 目录 + `RUN.sh`）。
   ⇒ **若 push 后不重新生成该 tar，`l.sh` / 方式二装出来的仍是旧的、无 mux 修复的客户端。**
   `Client/tools/make-release.sh` 应在 push 前重跑 —— **这条已写进"推 GitHub 前必做"清单**。
9. **`hysteria2.tar.gz` 之外的其余客户端产物**（如 `xbd-client.tar.xz`）是否同样 stale：**未逐一核对**。
10. **RN `/root/xray-t/`、`/root/x-batch-test/`** 等早期测试目录（Oct 9 之前遗留，内含旧版 X 脚本树）仍在原处。
    **不属"本轮新建"，未删** —— 如需清理请明确授权。
11. **`check_diagonal.sh` 的内核层**因 CC/RN 未设 `MIHOMO_BIN` 而跳过（`10 通过 / 0 失败 / 1 跳过`）⇒ 该工具在**真实内核**上的表现本轮未覆盖。
12. **M 的 `src/env.sh` / `src/lib/manifest.txt` 这两个错位重复副本**是否为某个部署脚本的 bug 产物：**未追根因**（只证明了内容 = 对应文件的旧版本）。

---

## 11. 推 GitHub 前必做清单（本轮结论汇总，供你决策）

1. **[已修待推]** M：`src/conf/hysteria2.sh` 7 处 `cert_extract_domain` + 新门禁 `tools/check_called_defined.sh`
   （commit `1c23d1b9`，`check_all.sh` 19/19）。**（§6）**
2. **[必须]** X：push 前重跑 `Client/tools/make-release.sh` 重生成 `xbd-client.tar.gz` —— 现 tar **无 mux 修复**。**（§10-8）**
3. **[建议]** 客户端 `to_sb.py` 三处缺口：丢 `xhttp` 传输、丢 `ech`、**缺 `tls.enabled=true`**。**（§5.3 / §10-6）**
4. **[建议]** M 的 hy2 生成器修复进仓后，在 RN 上用 `rebuild_client_silent` **重建存量 hy2 产物**，清掉
   `down: "200 Mbps"` / `obfs=none` / `fingerprint` 语义错位（生成器已修，产物未重建）。**（§4.2 / §10-4）**
5. **[建议]** SB 存量 `vmess01` / `vmess02` 链接：需**重新添加该节点**才能重生成（生成器已验证正确）。**（§4.3-D / §10-5）**

---

## 附：证据件索引

| 文件 | 内容 |
|---|---|
| `evidence/reconcile.py` | 对账引擎（钉死 commit；全历史匹配；分类 LOCAL-CHANGE/DIFFERS） |
| `evidence/rn-manifest.tsv` | RN 1725 个文件的 `label + sha256 + size + mtime + path` |
| `evidence/reconcile-out.txt` | 对账完整输出（三张表明细） |
| `evidence/stage/*.tar.gz` | 分发用的三个冻结快照 |
| `evidence/3x3/payloads.txt` | 三条分享的 API 记录 + X 分享解码原文（含 SNI/ECH）+ SB 链接（含 `--fix` 后） |

---

## 12. 附注：origin/main 的推送来源（**不是我推的**，但需要你知道）

收尾时核对远程引用，发现**钉死的两个 commit 已经在 GitHub main 上了**：

| 仓库 | origin/main | 该引用的 reflog 记录 | 是否我推的 |
|---|---|---|---|
| `xray--core` | `55c736a` | `00:16:21 fetch origin main: fast-forward`（此前 `cf810be` @23:22 是 `update by push`） | **否** |
| `sing-box-core` | `2c209b0` | `23:55:25 update by push` | **否** |
| `mihomo--core` | `5467278` | `23:58:39 update by push` | **否** |
| `mihomo--core` | HEAD `1c23d1b`（§6 的 hy2 修复） | **尚未推送** | 我/我的子代理创建，**明确未推** |

**审计结论**：
- 本轮我执行过的 git 操作只有：`rev-parse` / `log` / `show` / `ls-tree` / `diff` / `archive` / `cat-file` / `status` / `add`+`commit`（仅 mihomo 那 1 个提交）。
  **没有任何 `git push`**，「未 push 任何仓库」这条红线**成立**。
- 上述三条 push 发生在 **23:55–23:58**（我彼时正在做阶段 0 对账与备份，尚未分发），是**其他 agent / 上层**所为。
- ⚠️ 需要你留意：**`xray--core@55c736a`（X 载荷 SNI/ECH 修复）与 `sing-box-core@2c209b0` 已经公开在 GitHub main 上**。
  也就是说"验证干净之后再推"这个顺序，对这两个仓库**已经被别人提前打破**了 —— 我验证的正是这两个 commit，
  结论是好的（§5 的 X 列三格全部转好），但**时序上不是"先验证后推"**。若这与用户新规矩冲突，需要你那边对齐。
- 唯一**尚未推送**的是我这条：`mihomo--core@1c23d1b`（§6 的 hy2 空 SNI 修复 + 反向门禁），符合"验证干净前不推"。
