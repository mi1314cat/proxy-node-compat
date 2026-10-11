# X 列（xray--core）：服务端分享产物 + CC 客户端更新 与 真机验收

日期: 2026-10-11（本地时钟比 RN 快约 88–91 秒，下文时间戳凡来自 RN 的都是 RN 时钟）
范围: **只做 X 一列**。M / SB 的 RN 路径（`/root/catmi/mihomo/**`、`/root/catmi/sing-box/**`）
与 CC 上它们的客户端目录一个字节都没碰；`ssh ds`（生产）全程只读、未登录改动。

---

## 0 · 结论速览

| 项 | 结果 |
|---|---|
| RN X 分享记录 | **2 条 = 1 组「主 + 原生」成对**，均显示「最新」；声明 URL 带全字段（见 §3.2） |
| 旧分享是否原地升级 | 是。`f64f61ce…`（互通前建的）**token 与地址不变**，refresh 后补出原生产品与声明 |
| CC 客户端 | `/opt/xray-browser-dialer/` 已更新；`lib/` 26/26 逐字节一致；`VERSION=2.8.3`；`xbd` 可运行 |
| 同列验收（逐节点真连） | **5/6** 通过（204 + 出口 `104.28.x.x`）；1 条真连失败且**根因在节点侧参数**（§6.1） |
| 负对照 | 3/3 按预期失败（死端口 / 死代理 / 坏凭据） |
| 回退链 | 裸地址→普通话、原生 404→回退普通话并打出原因：**真跑通过** |
| 门禁 | 本地 **813 通过 / 0 失败**；改前（新门禁 + 旧实现）**794 / 19 失败** |
| RN 上门禁 | **817 / 3 失败**，3 条全在一个与本次改动无关的组（§7） |
| 本地 commit | 10 个，**未 push**（`origin/main..HEAD` = 10，全部是本次会话产生的） |
| **第二轮（部署态）** | 部署态重跑全部关键路径通过；`refresh` **幂等**；新建**永久**全节点分享 `7dd1e7a5…`（TTL 0，**未撤销**，见 §11.5） |
| **本轮新发现并修** | hy2 带宽口径（默认 50/200 + 无处可设 → **60/200 + `.hy2-bandwidth`**）；hy2 产物**只重建**路径（此前不存在，且**无损拒绝**） |

**一句话**：已部署代码本身能产出「带声明 + 成对」的新分享，但**它自己的 `refresh`
路径不能把这件事做完** —— 旧记录永远补不出声明/原生，且旧 refresh 会把互通字段
整体抹掉。这条已修（含门禁与反向验证），但**修复还没分发到 RN**（§8 有必办项）。

---

## 1 · 改了什么（文件 + 行级要点 + 修复前后行为）

全部改动只落在本地仓库 `/root/deepseek/repos/xray--core`（分支 `main`）。
**`/root/conf/`（RN 上被钉死的脚本层）没有改**：RN 上的修复是用 `/tmp/x-col/fix/`
里同一份代码跑 `share.sh refresh` 产生产物的（§3.3），脚本层与 be4ec8e 的逐字节
一致性因此保持不变（§2.1）。

### 1.1 FIX A —— `conf/lib/interop.py` + `Client/lib/interop.py`（两份逐字节相同）

`parse_declaration()` 判「完整地址 / 裸查询串」用的是**子串**判据：

```python
# 修复前
if "?" in s and "://" in s or s.startswith("?"): ...
elif "=" in s and "://" not in s:  q = s      # 裸查询串
else: q = ""                                  # 没有查询串 → 没有声明
```

- **修复前行为**：`interop=1&…&url-xray=http://h:9443/share/n`（url-* 值未编码的裸
  查询串，docstring 明确承诺支持）→ 落到 `else` → `q=""` → 返回 `None` →
  客户端判 **`no-declaration` → 静默走普通话，不报错、不打印任何原因**。
- **修复后行为**：改成真探测 scheme（`elif urllib.parse.urlsplit(s).scheme:`）。
  三种形态（裸查询串 / `"?"+裸查询串` / 完整订阅地址）的 `decide()` 三项
  `choice/reason/url` 逐字段相同：`('native','native-listed','http://h:9443/share/bbbb')`。
- ⚠ **踩过的错修法（值得留档）**：把判据换成「看子串 `://`」**修不好** —— 裸查询串
  里 `url-xray=http://…` 自带字面 `://`，会命中完整地址分支，而
  `urlsplit("interop=1&…&url-xray=http://h/b").query == ""`，症状一字不差。
  实测证据：

  ```
  vector: interop=1&kernel=xray&distribution=xray&formats=uri,xray&url-xray=http://h:9443/share/bbbb
  urlsplit().query = ''
  urlsplit() parts  = SplitResult(scheme='', netloc='', path='interop=1&...&url-xray=http://h:9443/share/bbbb', query='', fragment='')
  ```

- 顺带改**注释**（不改行为）：原注释写 interop 的 `distribution`「与 compat2 的
  distribution 同源」，**不成立** —— interop 取版本行首词小写（官方 → `xray`），
  `compat2.xray_target()` 对**同一个**二进制给 `distribution=None`（compat 当
  `upstream`）。现在如实写明「两套词表刻意分开，`decide()` 不跨层比较」。

### 1.2 FIX B —— `conf/share.sh` `share_refresh_all()`

- **修复前行为**（三处静默，退出码都是 0）：
  1. 只按 `role` 重建内容，**从不补原生产品、从不补声明**。互通代码（`da5fff0`/
     `32f65ef`）之前发出的分享，用户手里的地址**永远**不带内核声明 → 同内核客户端
     永远走普通话（URI 装不下的 ech/xhttp mode/pin 一直丢），而面板、链接、日志全部正常。
  2. 重建 meta 时 `m = {"name","tags","payload_schema"}` —— `share_service.py` 是
     `rec["meta"] = data["meta"]`（**整体替换**），于是 `role`/`native_token`/
     `distribution`/`formats` 被抹掉：撤销/停用/改次数再也连带不到原生产品
     （那条链接还活着），地址上的 `url-xray` 悄悄消失。
  3. 原生记录不带 `payload_schema` → `share_list` 把**每条原生**都标成「陈旧!」并劝
     用户去 refresh（假警报）。实测第一轮 refresh 后 RN 列表里就出现了这条假警报。
- **修复后行为**：
  - 主记录缺原生产品且本机发行版探测得到 → **原地补成对**：建同 `expires_at`/
    同 `max_uses` 的原生产品，`parent` 指向主记录，主记录 **token 与地址不变**；
  - meta 重写时保留互通字段（`role/kernel/distribution/kernel_version/formats/
    native_token/parent`）；
  - 原生记录也写 `payload_schema`，且**两个产品共用同一个号**（刻意不引第二个号：
    面板与记录更新不同步的窗口里，两个号会互相报「陈旧」，正是这里要消灭的假警报。
    残留缺口见 §7.3）；
  - 无法产出原生时也写「只提供 uri」的诚实声明（与创建路径同规则）。
- 顺带修掉本轮自己踩的坑：刷新循环的字段分隔符从 **TAB 改成 US(0x1f)**。TAB 是 IFS
  的空白字符，bash 会把连续分隔符**并成一个并吃掉空字段**，导致整行串列 —— 实测
  复现：`role` 读成 native 标志位、`content_sha256` 被当成 `distribution` 写进 meta。
  这条修完后 RN 上的 refresh 才写出正确声明。

### 1.3 FIX C —— `conf/lib/native.py` `build_document()`

- **修复前行为**：原生路径只跑**第一道**发布闸门（`build_share_link()` 的「不该发布」：
  绑回环 / REALITY 缺公钥…），**没跑第二道** `nodes.verify_against_products()`
  （载荷 ↔ per-node 产物一致性）。实测生产后果（RN，修复前抓到的原生正文）：
  URI 产品 **6** 个节点、原生 **7** 个，多出来的正是 URI 侧因「端点不一致」拒发的
  `SS2022-01`（产物 `107.173.154.178:39839` vs 载荷 `mensura.cdn-apple.com:39839`）。
  两条产品给不同的人、发布的节点却不一样 —— 而 `native.py` 开头就写明这是
  **不许发生**的事。客户端还会把多出来的那条按自己的规则过滤掉（实测「解析出 7 个 /
  已导入 6 个」），看起来像客户端 bug。
- **修复后行为**：`build_document()` 对每条已构建节点取回 `build_share_link()` 的链接，
  过同一个 `verify_against_products()`；不一致的既不进文档、也算 `refused` **报出来**。
  RN 上复跑后：URI 6 / 原生 **6**，同一个集合（客户端解析器逐名比对相等）。

### 1.4 vendored 同步 —— `Client/lib/proxy_node_compat/**`（8 个文件）

canonical = `/root/deepseek/repos/proxy-node-compat/proxy_node_compat/`。同步前实测
**5 个文件**滞后（不是 3 个 —— 我比对时 canonical 正被其他列改，`engine.py`/
`registry.py` 也在 10:03–10:04 被改过）：

| 文件 | 同步前 vendored | canonical |
|---|---|---|
| `uri.py` | `b495d3a3850af927…` | `53bc1796aedb87d2…` |
| `cli.py` | `bac30c4409130560…` | `8e8d3d9679c6697c…` |
| `engine.py` | `e502d0409b8c151e…` | `d0ae72285625af16…` |
| `registry.py` | `61bbc9cdb84ac207…` | `39692d275a59c06b…` |
| `data/rules.json` | `813424de95179c56…`（67 规则/27 证据） | `58b864920a97f8c4…`（68/29） |

同步后零差异（`for f in …; do cmp -s … || echo DIFF $f; done` 输出为空），8 个文件。

**实测行为差异**（同一批真机链接，`proxy-node-compat check-many --kernel {xray,sing-box}
--version 1.14.2`，6 条来自 RN 测试分享的 URI）：

- 滞后副本给常规 vless 链接凭空建出 `standard:vless.encryption` feature（`encryption=none`
  是规范哨兵，不是「要求加密」）→ 该 feature 命中 `singbox.vless.encryption.never`
  （UNSUPPORTED），xray 侧则让 config 层变成「版本未知 → UNKNOWN」。
- 判定变化（6 条 × 2 内核 = 12 格，**只有 1 格变了**）：
  `xray × X-VLESS-WS_01`：同步前 **UNKNOWN**（分层 `uri=SUPPORTED / config=UNKNOWN`）
  → 同步后 **SUPPORTED**（`uri=UNKNOWN / config=SUPPORTED / runtime=SUPPORTED /
  semantic=SUPPORTED`）。
  ⚠ 同一格里 **uri 层从 SUPPORTED 变成 UNKNOWN**，原因是注册表没有覆盖
  `scheme=vless × 基础 feature 集合`的 URI 表达力规则（报文原文：「层级 uri（scheme=vless）
  —— 没有覆盖该 scheme × feature 的 URI 表达力规则」）。这是 canonical 的**注册表覆盖缺口**，
  不是本次改动引入的（uri_rules 两边逐字节相同），留档给 compat 列（§7.4）。
- `cli.py` 白名单外的 scheme（如 `naive+https://…`）在滞后副本里会被当文件路径 →
  `FileNotFoundError` 崩掉整批；canonical 泛化成 `<scheme>://` → 走 `unknown:` → UNKNOWN。
  *本次只在构造向量上核对了代码路径，没跑出「崩掉整批」的端到端复现（UNKNOWN，§7.5）。*

### 1.5 重打发布包

`Client/xbd-client.tar.gz` / `.tar.xz`：`bash Client/tools/make-release.sh` 重打
（359,988 → 391,358 字节 gz；271,120 → 294,452 字节 xz）。新包内含
`lib/interop.py`（与 `conf/lib/interop.py` 逐字节相同）、8 个文件的 vendored compat、
共 77 项；`.sha256` 与实际一致（`e153c8c9609c2c00…`）。**没有用
`Client/tools/push-client.sh`，没有推任何远端。**

---

## 2 · RN 事实核验（先分清「事实」与「我以为的事实」）

### 2.1 脚本层 = 仓库 be4ec8e（逐字节，不是"看起来一样"）

```
$ find conf -type f -not -path '*__pycache__*' | wc -l      # 本地
52
$ ssh rn 'cd /root/conf && find . -type f … | wc -l'        # RN
52
$ diff a.sha b.sha && echo IDENTICAL
IDENTICAL: all 52 conf files match byte-for-byte
$ sha256sum /root/xray-panel.sh   # 与本地仓库 xray-panel.sh 相同
c47da3692b15c3439854b9237049736464ae70aa38785b80871cdaa36dd8bd51
```

（任务书写的「52 个文件」= 排除 `__pycache__` 后的计数，实测一致。）

### 2.2 `xray_fetch` 的实际行为（面板取文件优先级）

`xray-panel.sh:100-112` 的实码：

```bash
xray_fetch() {
    # 1) 从仓库检出目录直接跑
    self="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
    [[ -f "$self/$rel" ]] && { printf '%s' "$self/$rel"; return 0; }
    # 2) 本次会话的缓存
    … 3) 镜像链
```

**我一开始测错了**：用 `source <(sed -n '1,112p' /root/xray-panel.sh)` 复现，因为
`BASH_SOURCE` 变成 `/dev/fd/63`，`self=/dev/fd` → 本地不命中 → 走了镜像下载
（`/tmp/.xray-panel.92locN/conf_share.sh`）。**这个测法无效**。
换成「探针脚本就放在 `/root`」（与面板同目录、同一份函数体）后：

```
$ bash /root/.x-col-probe.sh            # 函数体取自 /root/xray-panel.sh:1-192，XRAY_RAW 指向不可达地址
xray_fetch conf/share.sh -> /root/conf/share.sh
$ sha256sum "$P" /root/conf/share.sh
547e8626fe52cdcf85c0  /root/conf/share.sh      ← 同一文件
547e8626fe52cdcf85c0  /root/conf/share.sh
```

另外直接跑 `/root/conf/share.sh`、同时把 `XRAY_RAW` 指向不可达地址：

```
$ XRAY_RAW=http://127.0.0.1:1/nonexistent bash /root/conf/share.sh list
  [--] 拉取地址 (带内核声明; 客户端据此决定拉原生还是普通话):
    1) http://107.173.154.178:9443/share/f64f61ce…?interop=1&kernel=xray&distribution=xray&…
```

→ **结论成立**：面板（`/root/xray-panel.sh`）取 `conf/share.sh` 走优先级 1
（脚本自身目录 `/root` 下的 `/root/conf/`）；`share.sh` 自己的依赖查找
（`_x_ensure_lib`/`_x_ensure_client`）同样本地优先（`/root/conf/lib`、`/root/conf/share_client.py`），
**不依赖网络**。

### 2.3 服务与进程（全程未重启任何服务）

```
$ ps -o pid,cmd -p 165517,119320,60510,69727
 60510  1-14:47:42 /root/catmi/sing-box/sing-box -D /root/catmi/sing-box …
119320  21:38:35   /root/catmi/mihomo/mihomo -d /root/catmi/mihomo/conf
165517  13:09:47   /root/catmi/xray/xrayls -confdir /root/catmi/xray/conf
 69727  1-13:42:17 /usr/bin/python3 /opt/proxy-share-service/share_service.py
```

X 的节点片段目录是 **`/root/catmi/xray/conf/`**（29 个文件；`/root/conf/` 是脚本层）。
本轮所有 share 操作只经 `conf/share_client.py` 的 HTTP API 与 `conf/lib/*`，
`conf/share.sh`、`conf/lib/native.py` 里**没有** `systemctl` / `restart` / `kill`
（已 grep 确认），实际也没重启任何东西。

---

## 3 · RN 服务端：真实命令与原始输出

### 3.1 修复前（钉死的 be4ec8e 代码读到的旧记录）

```
$ bash /root/conf/share.sh list
    1    f64f61ce35e42b39a5  e2e-allproto    23/∞  永久  active  最新  普通话  hysteria-04,SS2022-02,TROJAN-03,vless-xh
    1) http://107.173.154.178:9443/share/f64f61ce35e42b39a5f928d1c6d15ae5?interop=1&kernel=xray&version=26.3.27&formats=uri
```
meta 里 `role=native_token=formats=None` → **只声明「我只有普通话」**，没有原生产品。

### 3.2 修复后（同一 token，地址不变，声明补全）

```
$ XRAY_BASE=/root/catmi/xray bash /tmp/x-col/fix/conf/share.sh refresh
    [--] 已刷新 1 条分享链接的内容与声明 (token 与地址未变)
    [--] 其中补建原生产品 1 条 (同到期时间/同次数上限)

$ bash /root/conf/share.sh list          # ← 仍用钉死的面板代码读，证明产物可被已部署代码正确展示
    1    498f192bf0f72d43ae  e2e-allproto (原  0/∞  永久  active  最新  原生      hysteria-04,SS2022-02,TROJAN-03,…
    2    f64f61ce35e42b39a5  e2e-allproto     23/∞ 永久  active  最新  普通话+xray hysteria-04,…
    [--] 拉取地址 (带内核声明; 客户端据此决定拉原生还是普通话):
      1) http://107.173.154.178:9443/share/f64f61ce35e42b39a5f928d1c6d15ae5?interop=1&kernel=xray&distribution=xray&version=26.3.27&formats=uri%2Cxray&url-xray=http%3A%2F%2F107.173.154.178%3A9443%2Fshare%2F498f192bf0f72d43aec6edd8b1bfdf8b
```

主记录内容哈希未变（`2bebe127…`），新增原生记录 `498f192b…`（`content_type=application/json`，
`role=native`，`parent=f64f61ce…`，`expires_at=0` / `max_uses=0` 与主记录同源）。

### 3.3 一次性测试分享（覆盖全部**可发布**节点）

用面板自己的创建路径（钉死代码）：`printf '\nx-col-e2e-all\n0\n0\n' | bash /root/conf/share.sh create`
（选择留空 = 全部 24 个 tag；不可发布的由发布闸门挡下并逐条报出）。原始输出要点：

```
      不该对外发布: REALITY-01 —— REALITY 缺公钥(pbk)
      提示: SS2022-01: 拒发 —— 载荷与 ss2022-share-01.txt 不一致: 端点不同: 产物 107.173.154.178:39839 / 载荷 mensura.cdn-apple.com:39839
      提示: 与 per-node 产物一致性校验: 6 条通过, 1 条被拒发
    [OK] 分享已生成
      http://107.173.154.178:9443/share/a4b340b4a3cfc7a2b998bbeec5be415a?interop=1&kernel=xray&distribution=xray&version=26.3.27&formats=uri%2Cxray&url-xray=http%3A%2F%2F107.173.154.178%3A9443%2Fshare%2F5050a3c5409a101dae29742aed87bf77
```

- 24 个 tag 里**可发布 6 个**：`hysteria-04 / VLESS-WS_01 / SS2022-02 / TROJAN-03 /
  vless-xhttp07 / vless-xhttp08`；其余 18 个被逐条报出原因（绑回环无 nginx、
  REALITY 缺 pbk、缺对外地址/端口）+ `SS2022-01` 因双路径不一致被拒发。
  ⚠ 面板那句「节点: <24 个 tag>」打的是**请求的 tag 列表**，不是实际发布的节点集合；
  与实际集合的差异靠上面那一串「不该对外发布/拒发」交代（不是静默）。
- 该分享**已按纪律撤销**（§9），撤销后两条 URL 都是 **HTTP 404**。

### 3.4 修复 C 之后的两条产品（同一个分享）

```
URI   产品: 6 条    ← curl …/share/a4b340b4… | base64 -d | grep -c .
NATIVE 产品: 6 个 outbounds
   🇺🇸 X-hysteria-04 / X-VLESS-WS_01 / X-SS2022-02 / X-TROJAN-03 / X-vless-xhttp07 / X-vless-xhttp08
（修复前: NATIVE = 7 个, 多 SS2022-01）
用客户端解析器逐名比对: URI set == native set: True
```

---

## 4 · CC 客户端更新与复核

```
# 备份（更新前）
cp -a /opt/xray-browser-dialer/. /root/backup-prepush-cc-20261011-101740/     # 326M
# 同步（保留 CC 上的运行时目录: nodes/runtime/logs/generated/backup/config/xbd-dist）
rsync -a --exclude='xbd-client.tar.*' --exclude='__pycache__' Client/ CC:/opt/xray-browser-dialer/
```

| 复核项 | 结果 |
|---|---|
| `lib/` 逐文件 sha256 | 本地清单 26 条 ↔ CC 清单 26 条，`diff` **无差异** |
| `VERSION` | `2.8.3`（与仓库 `Client/VERSION` 一致） |
| `xbd` 能否起来 | `xbd version` → `Xray Client Web Manager v2.8.3` |
| 运行时确实加载新代码（防陈旧 `.pyc`） | `interop.__file__=…/lib/interop.py` sha `c6cc8d0be1e7ebd6`（= 仓库）；`proxy_node_compat.uri` `53bc1796aedb87d2`（= canonical）；`engine` `d0ae72285625af16`（= canonical） |
| `/usr/local/bin/xbd` shim | 未改动（63 字节，`exec /opt/xray-browser-dialer/bin/xbd "$@"`） |
| 可执行位 | 与官方包 `tar tvzf` 逐项一致（`bin/xbd` `-rwxr-xr-x`；`lib/*.sh` `-rw-r--r--`） |

客户端入口实测（**本次验收最关键的一行**）：

```
$ xbd node sub "http://107.173.154.178:9443/share/a4b340b4…?interop=1&kernel=xray&distribution=xray&version=26.3.27&formats=uri%2Cxray&url-xray=http%3A%2F%2F107.173.154.178%3A9443%2Fshare%2F5050a3c5409a101dae29742aed87bf77" x-col-e2e
✓ 本次拉取: 原生 Xray JSON —— 同内核同发行版 (xray/xray) → 取原生
✓ 解析出 7 个节点
✓ 已导入 6 个节点，归入分组「x-col-e2e」(6 个)
```

> `解析出 7 / 已导入 6` 是修复 C 之前那次运行的输出（当时原生产品多带 `SS2022-01`，
> 被客户端自己的过滤器丢掉）。修复 C 之后两条产品都是 6 个节点。

---

## 5 · 同列验收

### 5.1 逐节点真连（客户端自己的 `lib/genconfig.py` + `bin/xray`，每节点独立实例/独立 socks 端口）

判据 = `http://www.gstatic.com/generate_204` **204** 且出口 IP = RN 的 CF 出口 `104.28.x.x`。

| 节点 | HTTP | 出口 IP | 判定 |
|---|---|---|---|
| X-hysteria-04 | 204 | `104.28.195.192` | ✅ |
| X-SS2022-02 | 204 | `104.28.195.192` | ✅ |
| X-TROJAN-03 | 204 | `104.28.195.192` | ✅ |
| X-VLESS-WS_01 | **000** | — | ❌ 见 §6.1（节点侧参数问题） |
| X-vless-xhttp07 | 204 | 首测 `2a09:bac5:6368:2da5::48c:5`（RN 的 WARP **IPv6**）；复测 `104.28.195.192` | ⚠ 首测不满足 IPv4 判据，复测通过（§6.2） |
| X-vless-xhttp08 | 204 | `104.28.195.192` | ✅ |

**直连基线（不经节点，同一台 CC）**：`generate_204 = 204`，而 `cloudflare trace` 的
`ip=183.210.249.163`（CC 自己的出口），`ifconfig.me` 给 `2409:8a20:1c93:5460::2`。
→ **204 单独确实不算成功**：直连也拿 204，出口却是 CC 自己。判据必须带出口 IP 才有意义。

### 5.2 负对照（必须失败，否则判据是假的）

| 负对照 | 结果 |
|---|---|
| 死端口（把可用节点的 port 改成 1） | `http=000 exit_ip=<none>` → 按预期失败 ✅ |
| 死代理（没有实例的 socks 端口） | `code=000`（拿不到 204）✅ |
| 坏凭据（有效地址 + 随机 uuid） | `http=000 exit_ip=<none>` → 按预期失败 ✅ |

### 5.3 回退链（真跑，不是看代码）

```
### A · 声明缺失（裸地址）
  url=http://107.173.154.178:9443/share/a4b340b4a3cfc7a2b998bbeec5be415a
  本次拉取: 普通话 URI 列表 —— 地址上没有内核声明
  ✓ 解析出 6 个节点

### B · 声明在但原生取件 404
  本次拉取: 普通话 URI 列表 —— 同内核同发行版 (xray/xray) → 取原生；
            原生取件失败(http://107.173.154.178:9443/share/99999999999999999999999999999999) → 回退
  ✓ 解析出 6 个节点
```

两条都拿到 6 个节点、都**没有报错**；B 还把「为什么回退」打了出来。
（`已导入 0 个` 是因为这 6 个节点在第一次导入时就已存在，客户端按既有去重规则跳过 ——
不是失败。）

---

## 6 · 本轮挖出的、**没有**修掉的东西（诚实清单）

### 6.1 `VLESS-WS_01` 是**已发布但连不通**的节点（节点侧参数问题，未修）

- 事实：它的**两条产品都**声明 `107.173.154.178:443` + `type=ws` + **`security=none`**：

  ```json
  {"protocol":"vless","settings":{"vnext":[{"address":"107.173.154.178","port":443,…}]},
   "streamSettings":{"network":"ws","security":"none","wsSettings":{"path":"/bk4poo5e1q"}}}
  ```

- 而 RN 的 443 是 **TLS 终结**的：`openssl s_client` 能完成握手（证书是占位证书
  `CN=Common Name`），TCP 也通；但以 `security=none` 的 ws 去拨 TLS 端口拿不到任何
  HTTP（本机 curl 对 443 的 http/https/路径请求全是 000，节点链路上也是 000）。
- `share_meta` 写的是 `{"host":"107.173.154.178","port":9998,"tier":"nginx"}`（9998 是
  **回环**入站端口），分享层按 `tier=nginx` 把对外端点改写成 nginx 前端端口 443，
  但 `security` 仍取片段里的 `none` —— **「TLS 前端 + 明文 ws」这个组合本身不成立**。
- 为什么门禁抓不到：两条产品**错得一模一样**，一致性闸门（比对两条生成路径）只能发现
  「不一致」，发现不了「一致地错」。发布闸门只查绑回环/缺 pbk，不查「传输安全性与前端端口是否匹配」。
- 未修原因：修它要动的是**节点自己的发布参数**（该节点应声明 `security=tls` + 正确的
  nginx `server_name`/SNI，或发布在非 TLS 端口），不属于分享层代码；本轮纪律不允许我
  改 RN 的节点配置。**UNKNOWN**：加上正确 SNI 后它是否可用，没有验证。

### 6.2 `x-vless-xhttp07` 的出口地址族不稳定（同一节点两次不同）

首测出口是 RN 的 WARP **IPv6** `2a09:bac5:6368:2da5::48c:5`，复测同一条链接出口是
`104.28.195.192`。两次都是 RN 的 Cloudflare WARP（CC 自己的出口是 183.210.249.163 /
2409:8a20:…），只是地址族由 RN 侧每连接决定。按「必须 = 104.28.x.x」的严格判据，
这条属于**时好时坏**，不是稳定通过。想要稳定判据需要给出口定族（客户端有 `--family`，
但那管的是本机出站族，RN 侧 WARP 选族不在客户端控制内）。

### 6.3 `refresh` 的残留缺口（已写进代码注释，未做成第二个版本号）

本轮只在「同一个号」的方案下修好了假「陈旧」。真正的缺口是：`native.py` 单方面改动而
**内容逐字节不变**时，`payload_schema` 不会动，只能靠内容哈希发现（真漏报）。
彻底解决要给原生生成器自己的号，但那是一次**跨版本**改动（面板代码与分享记录要同时换），
在「面板脚本层已钉死」的前提下做会制造更新窗口里的假陈旧 —— 留作后续。

### 6.4 canonical 注册表缺 `scheme=vless × 基础 feature`的 URI 表达力规则

见 §1.4：同步后 `xray × X-VLESS-WS_01` 的 `uri` 层从 SUPPORTED 变成 **UNKNOWN**
（报文原文见 §1.4）。`uri_rules` 两边逐字节相同，所以这是 canonical 的覆盖缺口，
不是 X 侧的漂移。**没有**为此改任何规则（那属于 compat 列）。

### 6.5 其它 UNKNOWN

- 没有验证「`encryption=none` 假 UNSUPPORTED」在 **sing-box** 目标上的端到端复现：
  我构造的 6 条真机链接里，sing-box 目标全部因「组合未被规则覆盖」判 UNKNOWN
  （`UNKNOWN_CAPABILITY` 优先于那条 `singbox.vless.encryption.never`），所以只取到了
  **机制证据**（凭空多出的 feature）与 **xray 侧的判定变化**，没有取到 SB 侧
  「UNKNOWN→假 UNSUPPORTED」的现场。规则本身在同步前后的 `rules.json` 里都在。
- `/root/catmi/xray/conf/nginx.json` 是 Xray 的 inbound 集合（不是 nginx 配置）；
  真正给 443 提供服务的 nginx 跑在 **docker 容器**里（`docker ps` 有 `nginx:alpine`），
  我没有进容器核对 server_name/证书链 —— 「该节点应如何正确发布」的确切参数**未验证**。
- CC 的 `/root/backup-prepush-cc-20261011-101740/` 我**没有做恢复演练**（只确认备份存在、
  326M、lib 42 个文件）。

---

## 7 · 门禁前后对比（数字）

### 7.1 本地全套 `bash tools/check_libs.sh`

| 运行 | 实现 | 门禁 | 结果 |
|---|---|---|---|
| 改前 | HEAD `be4ec8e` | **新**（本轮新增断言） | **794 通过 / 19 失败**（RC=1） |
| 改后 | 本轮修复 | 新 | **813 通过 / 0 失败**（RC=0） |

改前 19 条失败的分类（行号取自最终日志）：

- **FIX A（互通组 ②b）** 3 条：`裸查询串… → 认得出声明并走原生`（得到 `UNRECOGNIZED`）、
  `『?』+裸查询串 与裸查询串: 决策三项相同`、`完整订阅地址 与裸查询串: 决策三项相同`。
- **FIX B（分享刷新组 + e2e §9/§10）** 12 条：`没有补出原生产品(native=0)`、
  `声明没补上或地址变了`、`主记录 meta 不对: bad role=None interop=None`、
  `成对语义不一致`、`幂等被破坏`、`互通字段被抹掉了`、`版本号不对`，以及 6 条
  `刷新断言没有覆盖: …`（e2e 汇总本身也红：`结果: 14 通过, 7 失败`）。
- **FIX C（两条产品的节点集合组）** 4 条：`URI 拒发的节点**不在**原生文档里`
  （得到 1 = 在）、`原生路径也把这条报成拒发`（得到空）、`原生集合 ⊆ URI 集合`（0）、
  `节点数关系 10 = 9 + 1`（得到 `10/10/1`）。
- **vendored 一致性组** 5 条漂移（`uri.py` / `cli.py` / `engine.py` / `registry.py` / `rules.json`）。

### 7.2 「路径不存在 → 必须失败，不许跳过」的反向验证

把 tree 放到 `../proxy-node-compat` 解析不到的目录再跑全套：

```
vendored proxy_node_compat 与 canonical 逐字节一致
  ✗ canonical 目录不存在: /tmp/x-col/run-nocanon/x/../proxy-node-compat/proxy_node_compat
    —— 这一组**不许跳过**（vendored 一致性没有验证）
═══ 结果: 786 通过, 11 失败 ═══   RC=1
```

### 7.3 改后 / 改前的其它数字

- `Client/tools/selftest-compat.py`：改前 **PASS（114 项）** / 改后 **PASS（114 项）**。
  `Client/tools/compat-corpus.json` 的期望值**没有改**（没有为了让门禁变绿动期望）。
- `bash tools/interop-e2e.sh`（合成语料，真 share.sh + 真分享服务 + 真 xbd）：
  改前 `14 通过 / 7 失败` → 改后 **21 通过 / 0 失败**。

### 7.4 RN 上跑 `tools/check_libs.sh`

先把**完整**仓库树（`git archive HEAD`：含 `xray-panel.sh`/`install.sh`/`bin/`）+ canonical
快照放到 `/tmp/x-col/rns2/`（第一次只放了 `conf/ tools/ Client/`，于是面板菜单/安装脚本/
`README.md` 探测那几组全红 —— 那是**我摆错树**，不是环境问题）：

```
═══ 结果: 817 通过, 3 失败 ═══   RC=1
  ✗ 没查出孤儿片段 / ✗ 告警没说清后果 / ✗ 明明有孤儿却报'没有发现'
```

3 条全在**同一个**既有组「nginx 片段生命周期 (node.sh)」。该组只依赖
`conf/node.sh` + `conf/lib/nginx_apply.py`，而这两个文件**不在本轮改动清单里**
（`git diff --name-only be4ec8e..HEAD` 里没有它们）。根因是环境差异：RN 上 nginx
**真跑在 docker 容器里**（`docker ps` → `nginx  nginx:alpine`），该组断言「扫描目标只有
临时目录」的前提在 RN 上不成立。→ **RN 上跑得通**（817 条绿），这 3 条与本次改动无关，
留档给以后需要时再修（未修）。

---

## 8 · 必办项 / 交接（第二轮结束时的状态）

1. **分发：已完成。** 协调方分发 `810b538`；本轮我把新增的 `c0ad7f6`（hy2）与更新后的
   `xray-panel.sh` 按同一条不变量分发到 RN —— 现在 **RN 的 `/root/conf`（53 文件）与
   `xray-panel.sh` 都 == 本地 HEAD**（逐字节核过），四个服务 PID 全程未变
   （xrayls 165517 / mihomo 119320 / sing-box 60510 / proxy-share-service 69727）。
2. **hy2 三个节点的产物重建被"无损拒绝"挡住** → 需要先做 §11.2 的 A/B/C 决策
   （改片段证书路径 / 加 `_serverName` / 什么都不做）。决策后：
   `bash /root/conf/hysteria2.sh sync-products --apply` 即可把产物重建到 60/200 且正确。
3. **`VLESS-WS_01` 是"可发布但连不通"的节点**（443 是 TLS 前端却声明 `security=none`，
   两轮真连都是 000）。修它要动节点自己的发布参数（`security=tls` + 正确 SNI，或换端口），
   属节点层；不修则矩阵里按已知失败处理（它仍在永久分享里，因为两条产品一致）。
4. **永久全节点地址见 §11.5**（TTL 0，**未撤销**；撤销命令也写在那里）。
5. **CC 上的验收残留**：`/opt/xray-browser-dialer/nodes/` 里 6 个来自 X 分享的节点
   （`node-001-x-*.json`，分组 `x-col-e2e`）与几个空组（第一次导入时用过的
   `x-col-bare`/`x-col-404`，本轮又建了 `x-col-bare2`/`x-col-404b`/`xray-interop-all`）。
   故意留着便于复验；不想要就用面板自己的节点/分组删除路径删掉。

## 9 · 临时物清单与清理

| 位置 | 内容 | 状态 |
|---|---|---|
| 本地 `/tmp/x-col/` | `prefix/`、`run-nocanon/`、`noncanon/`（反向验证树）、`e2e*.log`、`gate-*.log`、`v2 快照`、`*cmsg*.txt`、`dual-check.py`、`cc-node-test.sh`、`proxy-node-compat` 符号链接 | **已删除**（见下） |
| RN `/tmp/x-col/` | `fix/`（修复后代码）、`rns/`、`rns2/`（门禁树 + canonical 快照）、`local-conf.sha`、`rn-conf-raw.sha`、`rn-suite*.log` | **已删除** |
| CC `/tmp/x-col/` 与 `/tmp/x-col-cc-node-test.sh` | 逐节点测试的配置/日志/脚本 | **已删除** |
| RN `/root/.x-col-probe.sh` | 取文件优先级的探针脚本 | **已删除** |
| 本地 `/tmp/x-col/`（第二轮新增） | `prefix/`（HEAD 树，FIX D/F 反向验证基线）、`headtree/`、`hy2t/`（hy2 夹具）、`hy2-local-test.sh`、`cc-node-test2.sh`、`gate-*.log`、`*cmsg*.txt`、`*.sha` | **已删除**（收尾清理） |
| RN `/tmp/x-col/`、`/tmp/x-col-hy204.orig`、`/tmp/x-col/hy2_share-0*.snap` | hy2 实验与快照 | **已删除** |
| CC `/tmp/x-col/`（含 `cc2/` 实例配置与日志） | 部署态逐节点验收的产物 | **已删除** |
| RN 上一次性测试分享 `a4b340b4…`（第一轮） | 公共服务记录 | 第一轮**已撤销**（404） |
| RN 上**永久**分享 `7dd1e7a5…` + 原生 `ff3022fb…` | 对外形态（协调方要求**不撤销**） | **保留**（撤销命令见 §11.5） |
| RN 一次性测试分享 `a4b340b4…` + 原生 `5050a3c5…` | 公共服务上的记录 | **已撤销**（面板自己的 `share_revoke`，两条 URL 均 404） |
| CC `/root/backup-prepush-cc-20261011-101740/` | **X 客户端**更新前备份（326M，含 `VERSION/bin/lib/...`） | **保留**（按纪律备份不删，供回退） |
| CC 另两个 `backup-prepush-cc-*` | `100556`（`sb-client`，284K）与 `101946`（`src`，1.4M）—— **其它列**的备份，我一个字节都没动 | 未触碰 |
| RN `/root/backup-prepush-20261010-184809/` | 分发前备份 | 未触碰 |

未产生 `/tmp/dist-*`。

---

## 10 · 本地 commit（`main`，**未 push**）

```
957e603 feat(互通/声明): 地址缩短 —— 不写 version, 同源时 url-<fmt> 写相对路径 /share/<token>
5b094c4 fix(客户端): 订阅里"解析器不认的链接"被静默丢掉 —— 服务端 19 条, 客户端只说 15 个
c3902a3 fix(hy2): 三个消费者必须同一个带宽口径（native.py 漏读 .hy2-bandwidth）+ 门禁
b559365 chore(客户端): 再 vendor 一次 canonical 的 data/rules.json（脱敏占位符）
c0ad7f6 fix(hy2): 带宽默认 50→60 且无处可设 —— 对齐 mihomo 口径 (.hy2-bandwidth)
810b538 chore(客户端): 重打发布包（旧包不含 mux 修复, 也不含 interop 与同步后的 vendored）
f4cef31 chore(客户端): vendored proxy_node_compat 与 canonical 逐字节同步 + 一致性门禁
f641f76 fix(原生): 原生路径少跑一道发布闸门 —— URI 拒发的节点照样发出去了
d8aa2d9 fix(分享): refresh 只重建内容 —— 互通前发出的分享永远拿不到声明/原生配对
c02e109 fix(互通): 裸查询串带字面 :// 时被判成「没有声明」—— 认 scheme, 不认子串
```

**RN 部署态与本仓库的关系**：第一轮由协调方分发 `810b538`；本轮新增的
`c0ad7f6`（hy2）我按同一条不变量把 `conf/`（53 个文件）与 `xray-panel.sh`
分发到 RN 并逐字节核过 —— **RN X 脚本层 == 本地 HEAD**。四个服务 PID 全程未变。

每处修复都补了门禁并做了**反向验证**（新断言在旧实现上必须红，§7.1/§7.2）。
`git push` 一次都没执行（`origin/main..HEAD` = 8 个提交，其中 3 个是分发前就存在的）。

### 附：新增/改动的门禁断言（都在 `tools/check_libs.sh`）

| 组 | 断言 | 反向验证 |
|---|---|---|
| 三家互通 ②b | 裸查询串 / `?`+裸 / 完整地址 三形态 `decide()` 三项逐字段相同；`declaration_query()` 产物可被读回 | 改前红 3 条 ✅ |
| 三家互通 ②c | `interop.self_facts().distribution == "xray"` **且** `compat2.xray_target().distribution is None`（两套词表刻意分开） | 该组钉的是**未变**行为，改前也是绿（如实说明，未伪造反向验证） |
| 分享刷新 | 6 条覆盖面断言（补成对 / 地址带声明且 token 不变 / 内容未被改动 / 成对语义 / 幂等 / 互通字段不被抹）+ 面板不谎报陈旧 | 改前红 6+1 条 ✅ |
| 两条产品的节点集合 | 构造端点上不一致的 per-node 产物，断言 URI 拒发的节点不在原生里、原生 ⊆ URI、差集恰为报出的 unsupported | 改前红 4 条 ✅ |
| vendored 一致性 | 8 文件逐个 `cmp`；canonical 缺失 = **失败不跳过**；vendored 文件数必须正好 8 | 改前红 5 条；canonical 缺席时红 ✅ |


---

# 第二轮 · 部署态重跑 + hysteria-04 定性 + hy2 带宽/产物

> 触发：协调方把 `810b538` 逐字节分发到 RN 后跑了一次部署态 `refresh`，发现
> `hysteria-04` 被发布闸门拒发（`sni: 载荷=缺 产物=有`），分享从 5 节点变 4 节点；
> 并指出 X 侧 hy2 带宽口径与产物双重滞后。本节是这三件事的结论。

## 11.1 部署态 vs 上一轮（本地 /tmp 树）逐条对照

上一轮的验收是用 `/tmp/x-col/fix/` 里的**同源代码**跑的（当时 `/root/conf` 还是
`be4ec8e`）；本轮 `/root/conf` 已是修复后代码（先 `810b538`，后本轮又分发到 HEAD）。

| 验收项 | 上一轮（/tmp 同源代码） | 本轮（**部署态** `/root/conf`） | 一致？ |
|---|---|---|---|
| 旧分享 refresh：token/地址不变、补出原生与声明 | 通过（1 组配对出现） | 通过（2 条记录 role/interop/native_token 齐） | ✅ 一致 |
| `refresh` **幂等** | 未单测 | 第二次 refresh **无输出**（无事可做），内容 sha 未变 | 本轮补上 |
| `create` 成对（新分享） | 通过（`a4b340b4` + `5050a3c5`） | 通过（`7dd1e7a5` + `ff3022fb`） | ✅ 一致 |
| 客户端取**原生** | 通过（`本次拉取: 原生 …`，解析 7 / 导入 6） | 通过（`本次拉取: 原生 …`，解析 5） | ✅ 一致（节点集变化见 §11.2） |
| 逐节点真连 | 5/6（WS_01 失败；xhttp07 走 WARP v6） | 4/5（WS_01 失败；**xhttp07 本轮 IPv4 通过**） | ✅ 一致（WS_01 两轮都失败；xhttp07 属地址族抖动，§6.2） |
| 负对照（死端口/死代理/坏凭据） | 3/3 按预期失败 | 3/3 按预期失败 | ✅ 一致 |
| 裸地址 → 普通话 | 通过 | 通过（5 节点，无报错） | ✅ 一致 |
| 原生 404 → 回退并打原因 | 通过 | 通过（原因里带 404 地址） | ✅ 一致 |
| **发布节点集合** | 6（含 hysteria-04） | **5**（hysteria-04 被拒发） | ❌ **不一致**，原因见 §11.2（证书文件在两次运行之间被删） |

部署态逐节点结果（判据 = 204 且出口 `104.28.x.x`；直连基线仍是 204 + 出口
`183.210.249.163`，所以 204 单独不算成功）：

| 节点 | HTTP | 出口 IP | 判定 |
|---|---|---|---|
| X-SS2022-02 | 204 | `104.28.195.192` | ✅ |
| X-TROJAN-03 | 204 | `104.28.195.192` | ✅ |
| X-vless-xhttp07 | 204 | `104.28.195.192` | ✅（上一轮是 WARP IPv6，本轮 IPv4） |
| X-vless-xhttp08 | 204 | `104.28.195.192` | ✅ |
| X-VLESS-WS_01 | **000** | — | ❌ 节点侧参数问题（§6.1，两轮一致） |
| X-hysteria-04（**不在分享里**，直接用 CC 上已导入的节点验） | 204 | `104.28.195.192` | ✅ 节点本身可用 —— 见 §11.2 |

## 11.2 hysteria-04 定性：不是元数据"丢了 sni"，是**证书文件被删了** + 片段里没有域名兜底

**结论**：`hy2_share-04.txt` 里的 `sni=moontv.6896698.xyz` 来自**节点创建那一刻**
（10-10 05:40）；而订阅载荷的 sni 是**每次现算**的 —— `nodes.link_sni()` 的候选顺序是
`片段 _serverName → tlsSettings.serverName → 证书文件 SAN/CN → certificates[].domain`，
最后才退到 `meta.host`（是 IP 就丢弃）。这条节点四路全空 → sni 为空 → 与旧产物不一致。

时间线（RN 时钟 = PDT；与本地 +08:00 的换算已在括号里标出）：

| 时刻（PDT） | 事件 | 证据 |
|---|---|---|
| 10-10 05:40:13 | hysteria-04 建节点；`hy2_share-04.txt` 写入（带 sni） | 产物 mtime |
| 10-10 05:40:32 | `xrayls` 启动 —— 证书此时被读进内存 | `ps -o lstart` |
| 10-10 05:46:11 | `node.sh` 写 share_meta（**只有 host/port/name**，无 sni/域名） | `out/share/hysteria-04.json` |
| 10-10 **19:27:15** | `/home/web/certs/` 变动：`*_cert.pem` 被删（key 与 `.auto-renewal` 留下）；真证书现在在 `/etc/letsencrypt/live/moontv.6896698.xyz/`（SAN=`moontv.6896698.xyz`，有效至 2026-12-14） | 目录 mtime + `cert_domain()` 实测 |
| 10-11 19:05（本地 10:05） | **我上一轮**的 refresh：证书还在 → 载荷有 sni → 5 条全过（0 拒发） | 上一轮输出 |
| 10-11 19:27 之后 | **协调方**的部署态 refresh：证书已删 → 载荷无 sni → 拒发 | 本轮复现 |

实测（同一节点、同一时刻，CC 上）：

```
sni=moontv.6896698.xyz → HTTP 204 + 出口 104.28.195.192
sni 为空                → HTTP 000
```

所以要回答"为什么旧的 refresh 没把它带过来"：**refresh 从来不重写 per-node 产物**
（它重写的是订阅内容），`hy2_share-04.txt` 一直是 05:40 的快照；两侧只是**在证书
文件还在的时候看起来一致**。证书被删把这条潜伏的分歧暴露出来了 —— 发布闸门拒发
是**正确行为**（拦下了一条载荷缺 sni 的链接）。

**修法（需要用户/协调方拍板，我不替选）** —— 三条路，代价写清：

| 选项 | 做法 | 代价 / 风险 |
|---|---|---|
| **A（最小、推荐面最大）** | 把三个 hy2 片段的 `certificateFile` 改到续期流程**真正维护**的路径（`/etc/letsencrypt/live/<域名>/fullchain.pem`，已知 moontv 存在且 SAN 正确；hxicc 未核） | 改 3 个节点片段（节点层数据）；分享层立刻能推出 sni（无需重启），但**运行中的内核要重载才用新路径**（本轮不许重启；证书内容相同，重载前行为不变） |
| **B（最稳，不依赖文件存在）** | 给片段加 `_serverName`（或 `certificates[].domain`）= 域名 | 同上；Xray 不认这些根键、部署路径本就剥掉，但"多一个非 schema 键"需要有人确认剥除逻辑覆盖它 |
| **C（零改动）** | 什么都不做 → 三个 hy2 节点保持"未发布" | 订阅少 1 个可用节点（当前状态，安全、不静默） |
| D（未验证） | 把证书文件恢复到被引用的路径（从 `/etc/letsencrypt/archive` 复制） | 动证书文件本身；下次续期是否又删掉 **UNKNOWN** |

**我没有做的事**：没有改任何片段 / 没有把没 sni 的产物写下去。原因就是上面那组
204/000 —— 写了等于把一条"客户端必然校验失败"的链接发布出去，而且两条产品会
**一致地错**，发布闸门反而放行。

## 11.3 hy2 带宽口径：默认 50/200（且无处可设）→ **60/200 + `.hy2-bandwidth`**

旧实现两头都不对：`conf/lib/nodes.py` `DEFAULT_HY2_UP=50`（分享链接路径），
`conf/hysteria2.sh` **六处硬编码** `up=50&down=200&upmbps=50&downmbps=200`
（链接 ×2 / Xray 客户端 JSON ×2 / mihomo YAML ×2）—— 硬编码意味着"用户设过"
根本无处可设。现在（与 mihomo 侧 `src/lib/env.sh` 同形状、逐字对齐）：

- **显式设置 = `${XRAY_BASE}/.hy2-bandwidth`**（两列空白分隔的 Mbps 文本，`45 170`）；
- 优先级：`.hy2-bandwidth` → `share_meta.upmbps/downmbps`（逐节点记录，
  **生产上目前为空** —— 我核过所有 share_meta，没有一份带带宽字段）→ 默认 **60/200**；
- 逐字段校验：两列写坏一个，另一个照常生效；
- 链接与两份客户端产物**共用同一次取值**（`hysteria2.sh` 里 `read` 一次）。

RN 部署态实验（**最终态：不留覆盖文件、回到 60/200**）：

```
### 1) 无覆盖文件      NODE hysteria-04 verdict=refused lost=sni changed=up:-->60,down:-->200,upmbps:50->60
### 2) 写 45 170       NODE hysteria-04 verdict=refused lost=sni changed=up:-->45,down:-->170,upmbps:50->45,downmbps:200->170
### 3) 删掉覆盖文件    NODE hysteria-04 verdict=refused lost=sni changed=up:-->60,down:-->200,upmbps:50->60
### 4) ls .hy2-bandwidth → No such file or directory
```

> `up:-->60` 那一列同时说明第二个问题：旧产物只有 `upmbps/downmbps`，**没有
> `up/down`** —— 而 mihomo 只认 `up/down`（`upmbps=` 是废弃的 hysteria v1 名字，
> 写了会被静默忽略）。新链接四个名字都写。

## 11.4 hy2 per-node 产物重建：路径此前**不存在**，本轮补上并**拒绝**了三个节点

`hy2_share-*.txt` 唯一的写入方是 `hysteria2.sh` 的 `add_config`（新增节点），
所以口径改过之后已发出的产物永远是旧的 —— **没有任何面板路径能重建它**
（`add_config` 会新建一个节点，不是重建；它也不重启内核，但会改片段/端口/uuid）。
本轮新增：

```
conf/lib/hy2_products.py          # 只重建 out/hy2_share-<NN>.txt
conf/hysteria2.sh sync-products    # 非交互入口；默认 dry-run，--apply 才写盘
```

- 链接**只从 `nodes.build_share_link()` 一处取** —— 与订阅载荷同一份实现
  （门禁断言：重建产物与订阅载荷**逐字节相同**）；
- **无损拒绝**：旧产物里有、新链接里没有的安全参数（`sni`/`pin`/`insecure`/`alpn`/
  非 none 的 `obfs`）一律拒绝写并报出原因。

RN 部署态实跑结果（三个 hy2 节点**全部拒绝**，产物一字未动）：

```
NODE hysteria-02 verdict=refused lost=<链接构不出来> changed= written=0
NODE hysteria-03 verdict=refused lost=<链接构不出来> changed= written=0
NODE hysteria-04 verdict=refused lost=sni           changed=up:-->60,down:-->200,upmbps:50->60 written=0
SUMMARY total=3 rebuilt=0 refused=3 unchanged=0
```

- **02/03 连链接都构不出来**：它们的 share_meta 里没有对外地址/端口 → 本来就不在
  任何分享里（本轮全节点分享也把它们列为"缺对外地址/端口"）。它们手里却各有一份
  旧产物 —— 这是另一处"产物比发布状态更旧"的遗留，本轮只记录、不改。
- **04 是 §11.2 那条**：拒绝写"没有 sni"的产物。

**因此"重建后 hy2 的 sni 不一致是否消失"的答案是：没有消失 —— 因为我（按设计）
拒绝重建它。** 如果强行重建，不一致会"消失"，但消失的方式是**两边一起丢掉 sni**，
而实测那样客户端是 000。要让它真正消失且正确，得先在 A/B/C 里选一条（§11.2）。

## 11.5 永久全节点带声明地址（**未撤销**）

用**部署态**的 `bash /root/conf/share.sh create`（选择留空 = 全部节点，TTL 0 永久，
次数不限）新建，name = `xray-interop-all`：

```
DECLARED_SHARE_URL:
http://107.173.154.178:9443/share/7dd1e7a55a631fa5bd1f8446dbf118fc?interop=1&kernel=xray&distribution=xray&version=26.3.27&formats=uri%2Cxray&url-xray=http%3A%2F%2F107.173.154.178%3A9443%2Fshare%2Fff3022fb954c1df70e69389b1dc595d5
```

- 主记录 `7dd1e7a55a631fa5bd1f8446dbf118fc` / 原生记录 `ff3022fb954c1df70e69389b1dc595d5`
- 两条产品**同为 5 个节点、集合逐名相等**：`SS2022-02 / TROJAN-03 / VLESS-WS_01 /
  vless-xhttp07 / vless-xhttp08`（`hysteria-04` 因 §11.2 拒发、`SS2022-01` 因端点不一致拒发）
- CC 端确认（部署态）：
  `✓ 本次拉取: 原生 Xray JSON —— 同内核同发行版 (xray/xray) → 取原生` / `解析出 5 个节点`
- **撤销命令**（需要时由协调方执行；本轮**故意不撤销**，它是对外形态）：
  ```
  ssh rn 'cd /root && bash -c "source /root/conf/share.sh >/dev/null 2>&1; share_revoke 7dd1e7a55a631fa5bd1f8446dbf118fc"'
  ```
  （`share_revoke` 会连带撤销原生产品 `ff3022fb…`；撤销后两条 URL 应为 HTTP 404。）
- 注意它覆盖的是**当前可发布**的 5 个节点；其中 `VLESS-WS_01` 实测 000（§6.1），
  即"可发布"≠"可连通"—— 节点侧参数问题未修，矩阵里请按已知失败处理。

## 11.6 部署态门禁与新增断言

- 门禁套件（本地）：改后 **824 通过 / 0 失败**（RC=0）。
- 反向验证：在 `810b538` 那份实现上（无 FIX D/F）跑**同一套**门禁 →
  **810 通过 / 13 失败**，13 条红**逐条都是本轮要钉的东西**：
  口径（`up=60` 两条 + 源码级"两个名字都写且不许再硬编码 50"一条）、
  新 hy2 组的 8 条（默认 60/200、默认生效、**无损拒绝**、覆盖生效、
  三消费者同口径、`--apply` 写盘、产物与载荷逐字节相同、`sync-products` 入口存在）、
  以及 vendored `rules.json` 漂移一条（那棵树里是 vendor 之前的副本）。
- **三消费者一个口径**（本轮自己踩到并修的）：`native.py` 原来只读
  `share_meta`/默认值，**不读** `.hy2-bandwidth` —— 覆盖文件一出现，URI 链接写
  45/170 而原生文档写 60/200（两条产品对不上）。已改成三个消费者
  （链接 / 原生文档 / 脚本产物）都走 `.hy2-bandwidth → meta → 默认`，
  并加断言：覆盖文件在时，链接的 `up/down/upmbps/downmbps` 与原生文档的
  `brutalUp/brutalDown` 必须同为 45/170。
- 因口径变更而**必须改**的既有期望值（不是"为了变绿而改期望"，两条都写明理由）：
  1. `tools/check_libs.sh:1854-1855` `S_GET hy2 up|upmbps` 期望 `50` → `60`：
     这两条钉的是"链接里 `up=` 与 `upmbps=` 两个名字都写"，值来自新的默认口径；
  2. `tools/check_libs.sh:1979` 源码级断言原来 grep 字面量
     `up=50&down=200&upmbps=50&downmbps=200` → 改成
     `grep 'up=$hy2_up&down=$hy2_down&upmbps=$hy2_up&downmbps=$hy2_down'`
     **且** `! grep 'up=50&down=200'`（顺带把"不许再写死"钉成回归断言）。
- **CC 客户端又同步了一次**：canonical 第二次前进后，`Client/lib/proxy_node_compat/
  data/rules.json` 变了（`c1dc188a…` → `5e11b094…`），CC 上那份会落后 —— 已重新
  rsync，`lib/` 26 个文件再次逐文件 sha256 一致（`VERSION=2.8.3` 未变）。
- `xray-panel.sh` 的 `_XRAY_LIB_FILES` 补了 `hy2_products.py` —— 这是门禁先发现的：
  漏了它，全新安装时面板不会把该文件铺到缓存，菜单项会报"库加载失败"。
- **canonical 在本轮又前进了一次**：我按协调方给的 `40a9441`（`rules.json`
  `c1dc188a…`）vendor 之后，canonical 变成 `692566c`（`5e11b094…`：占位符块不点名
  下游仓库 + canonical 自己的脱敏卫生门禁）→ 门禁当场报漂移，我又 vendor 了一次并
  重打发布包。**结论：vendored 一致性是有时效的**，canonical 一动就要重跑门禁 ——
  这正是那条"逐字节相同"门禁该有的行为（不是噪声）。

## 11.7 本轮新增/更新的 UNKNOWN

- §11.2 的 **A/B/C/D 四条路都没有执行**，因此"hy2 三个节点的产物何时能重建到
  正确口径"**UNKNOWN**（取决于选哪条）。
- `hxicc.catmicos.dpdns.org` 的证书是否也在 `/etc/letsencrypt/live/` 下、
  SAN 是否匹配：**未核**（只核了 moontv）。
- `hysteria-02/03` 各有一份旧产物却不在任何分享里：它们的对外地址本该是什么、
  要不要发布，**UNKNOWN**（本轮只记录）。
- `/home/web/certs/*_cert.pem` 是被谁删的（续期脚本 / 人工清理 / 别的列的动作）：
  只有目录 mtime 与 `.auto-renewal` 痕迹，**没有找到删除者**（journal 里没查到
  19:27 附近的证书相关行）。这不改变结论（载荷拿不到 sni），但**责任方 UNKNOWN**。
- **重发（`native.py` 带宽口径修复）之后，永久分享的主记录被 refresh 重写了 1 次**
  （服务日志：`PUT /api/v1/shares/7dd1e7a5…`）。重写后的内容与当前部署代码重算结果
  **逐字节一致**（`cf6cba8a8457`），随后连续两次 refresh 都无输出（幂等）→ 状态是
  自洽且稳定的；但**创建时(19:52)与重发后(20:04)之间 `nodes.py` 并未变化**，
  那一次重写的确切触发字段**没有定位到（UNKNOWN）**。记录在此，不当作"已解释"。
- 443 上 `openssl s_client` 拿到的是占位证书（`CN=Common Name`）—— 与上述证书
  缺失一致；nginx 站点（容器内 `nginx:alpine`）是否也因缺证书回落默认证书、
  以及 `VLESS-WS_01` 是否由此受影响，**UNKNOWN**（未进容器核对）。


---

# § 九宫格（X 客户端行）

执行者：CC 上**部署态**的 `xbd`（`/opt/xray-browser-dialer`，`VERSION=2.8.3`）。
三条地址原样使用，**一条都没改**（它们是三家共用的）。

| 项 | **X 服务端** | **M 服务端** | **SB 服务端** |
|---|---|---|---|
| 地址 | `…/share/7dd1e7a5…?interop=1&kernel=xray&distribution=xray&version=26.3.27&formats=uri%2Cxray&url-xray=…ff3022fb…` | `…/share/dbfffb5c…?interop=1&kernel=mihomo&distribution=upstream&version=1.19.32&formats=uri%2Cupstream&url-upstream=…40b83e65…` | `http://[2001:470:c:cf:…]:9443/share/ab03704a…?interop=1&kernel=sing-box&…&url-sing-box=…8526f930…` |
| **决策行** | `✓ 本次拉取: 原生 Xray JSON —— 同内核同发行版 (xray/xray) → 取原生` | `本次拉取: 普通话 URI 列表 —— 服务端内核 mihomo ≠ 本机 xray` | `本次拉取: 普通话 URI 列表 —— 服务端内核 sing-box ≠ 本机 xray` |
| 普通话**方言** | base64 单行（原生那路是 Xray JSON） | **明文 + 头两行 `#` 注释** | 明文，无注释 |
| 服务端产品条数 → xbd 解析 | 5 → **5** | 19（+2 注释）→ **15** | 13 → **8** |
| 导入数（首次 / 复跑） | 0 / 0（5 条早已在册 → 全部去重） | **15** / 0（复跑全去重） | **6** / 0（复跑全去重） |
| 被丢掉的**逐条**理由 | 5 条全是去重：`与已有节点或本批前面的条目重复（同协议/地址/端口/凭据）` + 指向已有节点文件 | **4 条解析器不认**：`anytls×3, tuic×1`（修复前**静默**，见下）；compat 拦下 0 条 | **5 条解析器不认**：`anytls×2, naive+https, shadowtls, tuic`；**2 条 compat 拦下**：`rn trojan02-REALITY`（REALITY 不支持 websocket）、`rn vmess02-REALITY`（Xray 内核不支持 vmess） |
| 真连（子集规则见下） | 6 测 **5 过**（`X-VLESS-WS_01` 000，节点侧问题 §6.1） | **3/3 过** | **5/5 过** |
| UNKNOWN | `VLESS-WS_01` 的节点侧修法（§6.1） | anytls / tuic 节点本身在 M 侧是否可用（本客户端不支持，未测） | naive+https / shadowtls / anytls / tuic 同上；`rn trojan02-REALITY` 到底是"节点参数不完整"还是 compat 过严（未定） |

**子集规则**（M/SB 节点太多）：**每个 (服务端, scheme) 取第一条**（按产品里出现顺序，
且只从 nodefilter 保留下来的节点里选）；**X 格全测**。选出的 14 条：M 3（hysteria2/vless/trojan）、
SB 5（hysteria2/vless/ss/trojan/vmess）、X 6（含不在本分享里的 hysteria-04）。

## 九宫格 · 逐节点真连（判据：204 且出口 ∈ RN 的 CF 出口集合 = `104.28.*` 或 `2a09:bac5:*`）

```
直连基线: 204=204 出口=<none>          ← CC 直连也拿得到 204, 所以 204 单独不算成功
M-mHysteria201-TLS      http=204  exit_ip=104.28.201.80      ✓
M-mTrojan01-REALITY     http=204  exit_ip=104.28.201.80      ✓
M-mVLESS01-REALITY      http=204  exit_ip=104.28.201.80      ✓
SB-rn hysteria201-TLS   http=204  exit_ip=104.28.201.80      ✓
SB-rn reality01-REALITY http=204  exit_ip=104.28.201.80      ✓
SB-rn shadowsocks01     http=204  exit_ip=104.28.201.80      ✓
SB-rn trojan01-TLS-CDN  http=204  exit_ip=104.28.201.80      ✓
SB-rn vmess01-TLS-CDN   http=204  exit_ip=104.28.201.80      ✓
X-hysteria-04           http=204  exit_ip=2a09:bac5:6368:2da5::48c:5   ✓ (RN 的 WARP IPv6)
X-SS2022-02             http=204  exit_ip=104.28.195.192     ✓
X-TROJAN-03             http=204  exit_ip=104.28.195.192     ✓
X-VLESS-WS_01           http=000  exit_ip=<none>             ✗ 节点侧参数问题(§6.1)
X-vless-xhttp07         http=204  exit_ip=2a09:bac5:6368:2da5::48c:5   ✓
X-vless-xhttp08         http=204  exit_ip=2a09:bac5:6368:2da5::48c:5   ✓
结果: 16 通过, 1 失败
```

**负对照**：

```
死地址(404)  http://…/share/9999…   → xbd 退出码 1, 明确 `✗ 订阅里没有解析出节点`   ✓
死端口节点   可用节点 port→1         → http=000 exit_ip=<none>                      ✓
```

## 九宫格的重点：三种方言 + 一个**真缺陷**

- **`#` 注释（协调方重点怀疑的那条）**：M 的普通话头两行 `# mihomo--core 自动生成的…` /
  `# 共 19 条…` 被 `parse_subscription` **正确跳过** —— 不产生节点、不计入"未识别"、
  也不影响解析数。**注释这一路没有问题。**
- **真正的缺陷是"不认的链接静默消失"**：M 发 **19** 条，xbd 只说"解析出 **15** 个"；
  SB 发 **13** 条，只说"解析出 **8** 个"。少的 4 / 5 条是 `parse_subscription` 里
  `except Exception: continue` 吃掉的 —— **没有计数、没有理由、没有痕迹**。
  实测消失清单：

  | 服务端 | 产品条数 | 解析 | 差的条数 | 差在哪（逐条） |
  |---|---|---|---|---|
  | X | 5（base64） | 5 | 0 | — |
  | M | 19（+2 注释） | 15 | **4** | `anytls×3`, `tuic×1` |
  | SB | 13 | 8 | **5** | `anytls×2`, `naive+https`, `shadowtls`, `tuic` |

  逐条单测证据（`parse_node` 抛的异常）：

  ```
  FAIL anytls  ValueError: 无法识别的输入格式（支持 vless/vmess/trojan/ss/hysteria2 链接、Xray JSON、Mihomo YAML）
  FAIL tuic    ValueError: 无法识别的输入格式（…）
  ```

  这些 scheme 本内核确实**不支持**（所以"不导入"是对的），但它们必须**有账**：
  用户看到"解析出 15 个"时无从判断是服务端只发了 15 条，还是客户端吞了 4 条。
  这正是本项目最忌讳的一类（静默丢弃 / 只有一个数字）。

**修复（commit `5b094c4`，本地 commit，未 push）**：

- `Client/lib/node.py`：`parse_subscription(text, unrecognized=None)` 把不认的行记进
  `unrecognized`（**只记有 `scheme://` 形态的** —— 顺带修掉一个新引入的噪声：404 的
  `{"error": …}` 错误体会被当成"1 条不认的链接（?×1）"，那是误导）；CLI 加 `--report PATH`。
- `Client/lib/actions.sh`：`_sub_fetch_nodes` 接上 `--report`，清单非空就打到 **stderr**
  （就在"解析出 N 个"旁边），逐条给出 scheme + 前 76 字符：
  ```
  [!] 订阅里有 4 条本客户端**解析器不认**的链接（anytls×3, tuic×1）—— 没有导入, 也不在下面那句「解析出 N 个」里
        · anytls:// anytls://f537cd201a21c199f874f254f9ac6c8b@107.173.154.178:28725?sni=hxicc.ca
        · tuic:// tuic://0647a947-6f77-4a91-8df0-8ff9f2d5e720:0647a947-…@…
  ```
- **门禁**（`tools/check_libs.sh` 新组「订阅解析: 不认的链接不许静默丢（M 的 # 注释方言也要吃）」）：
  注释被正确跳过 / 不认的逐条落盘可查 / 抓取路径真的接上了 `--report`。
  **反向验证**：同一组跑在修复前的 `node.py`+`actions.sh` 上 → **2 条红**
  （清单为 `missing`；抓取路径没有 `--report`）。
- 客户端已重新部署到 CC 并**重跑三格**：决策行与解析数不变，但 M/SB 两格现在都打出
  上面那条 `[!]` 告警（X 格没有，因为它没有不认的链接）。

## 九宫格 · 其它观察（未修，记录）

- **去重是"静默但可查"的**：三条地址的复跑导入数都是 0，理由逐条写进
  `/tmp/.xbd_skipped.json`（`与已有节点或本批前面的条目重复（同协议/地址/端口/凭据）`
  + 已有节点路径）。比"0 个"一个数字好，但**用户在终端上只看到"已导入 0 个"** ——
  这份清单没有任何入口展示。属 UX 缺口，本轮不改（改它要动 `cmd_node_subscription` 的
  输出，属于产品决策）。
- **M 的 anytls/tuic 与 SB 的 naive+https/shadowtls**：Xray 内核都没有这些出站协议，
  所以"不导入"是正确行为；修复只是让它们**可见**。
- SB 的 `rn trojan02-REALITY` 被 compat 判"REALITY 不支持 websocket"（理由给得很具体，
  不是笼统的"内核不支持"）—— 这条判定本身是否正确（该节点用 ws+reality 是否真不可用），
  本轮**没有**实测（UNKNOWN）。


---

# § 声明缩短（本轮最后一件）

用户拍的板：分享链接太长。两条改动，三家契约逐条相同。

## 改了什么

| # | 契约 | 实现位置 |
|---|---|---|
| 1 | **不再在地址上产出 `version`**（参数保留、默认空；解析侧仍**接受** `version`，只是不参与决策） | `conf/share.sh` 的 `x_share_declare_url()` 不再传 `--version`；`declaration_query()` 本来就不写空值 |
| 2 | `url-<fmt>` 与主地址**同源**时写相对引用 `/share/<token>`；异源仍写绝对地址 | `conf/lib/interop.py` 新增 `relative_native_url()`（产出侧，`declare` CLI 调用它） |
| 3 | 解析侧把相对引用拼回绝对 —— **放在 `parse_declaration()` 里**，所以 `decide()` 签名与逻辑都不用改 | `conf/lib/interop.py` `parse_declaration()`（只认"以 `/` 开头"；**不做**通用 urljoin） |
| 4 | 客户端同一份定义 | `Client/lib/interop.py` 与服务端**逐字节相同**（`b1c59dfb…`） |

**内核版本没有丢**：原生产品里自描述 —— 部署态实测（未重新部署，直接读线上原生文档）：

```
{"interop": 1, "kernel": "xray", "distribution": "xray", "version": "26.3.27", "source": "xray--core"}   outbounds=5
```

**不需要 bump schema**：旧实现看到相对路径会判 `bad-native-url` → 回退普通话（安全、可见、有 reason）。

## 实际长度（同一条分享、同输入）

| | 地址 | 长度 |
|---|---|---|
| 旧（**部署态真实产出**，取自 RN `share_list`） | `…/share/7dd1e7a5…?interop=1&kernel=xray&distribution=xray&**version=26.3.27**&formats=uri%2Cxray&url-xray=**http%3A%2F%2F107.173.154.178%3A9443%2Fshare%2F**ff3022fb…` | **229** |
| 新（同一 token / 同 host，用新代码跑 `interop.py declare`） | `…/share/7dd1e7a5…?interop=1&kernel=xray&distribution=xray&formats=uri%2Cxray&url-xray=**%2Fshare%2F**ff3022fb…` | **178** |

**缩短 51 字节（−22%）**。⚠ RN **没有重新部署**（按指示）—— 线上此刻仍是 229 字节那条；
分发之后再量一次才是线上真值。`share_list` 里打印的地址同样是"现算"的，分发后自动变短。

## 门禁（`tools/check_libs.sh` 新组「声明缩短…」，**9 条**）

```
✓ 声明格式对空 version 不输出（declaration_query 不写空值）
✓ 服务端产出侧（conf/share.sh）不再向 declare 传 --version（版本仍在原生产品里自描述）
✓ 同源 → url-xray 写成相对引用 /share/<token>（不再重复 host:port）
✓ 异源 → 仍然写绝对地址（相对引用跨源没有意义）
✓ 解析侧把相对引用拼成绝对地址, decide() 判 native（签名未改）
✓ 向后兼容: 旧格式（绝对地址 + 带 version）照样判 native
✓ 解析侧: 手写的相对引用声明也要拼成绝对并判 native      ← 单独构造的向量
✓ 空 token（/share/）不猜 → 保持原样 → bad-native-url
✓ 协议相对（//other.host/x）不猜 → 保持原样 → bad-native-url
```

**反向验证**（同一组跑在 HEAD 的 `interop.py`+`share.sh` 上）：**3 条红** ——
`conf/share.sh 仍在传 --version`、`同源未写相对`、`手写的相对向量判成 uri|bad-native-url`。

两条"不猜"的判据各判成什么（逐条）：

| 输入 | 判定 |
|---|---|
| `url-xray=/share/`（空 token） | 解析侧**不拼**（原样保留）→ `decide()` = `uri|bad-native-url` |
| `url-xray=//other.host/x`（协议相对） | 解析侧**不拼**（以 `//` 开头即拒）→ `uri|bad-native-url` |

> ⚠ 这两条我自己第一版写错了：判据先 `rstrip("/")` 再看末段，`/share/` 于是变成
> "末段 = `share`" 被判成合法路径 → 拼出 `http://h:9443/share/` 这条**看起来合法**的
> 死链。门禁当场红（`得到 'native|native-listed|http://h:9443/share/'`），已改成看
> **原样**末段。留档：这就是"不猜"这类判据最容易被写反的地方。

## 客户端与 CC

- `Client/lib/interop.py` 与服务端逐字节相同（`b1c59dfb…`）；
- CC `/opt/xray-browser-dialer/` 已 rsync，**`lib/` 26 个文件逐文件 sha256 一致**；
- CC 上实测两种格式都能读（RN 未重发前仍是旧格式）：
  `相对引用 → native|native-listed|http://h:9443/share/bbbb`、
  `旧格式（绝对+version）→ native|native-listed|http://h:9443/share/bbbb`。

## 全量门禁总数

`bash tools/check_libs.sh` → **836 通过 / 0 失败**（RC=0）。
（本轮之前的 824/0 + 新增的"声明缩短"组 9 条 + 三消费者断言 1 条 + 若干计数差异。）

### 分发后的**线上真值**（协调方分发 `957e603` 之后，部署态实测）

⚠ **修正一处预期**：`refresh` **不需要**、也不会"把地址从 229 改成 178" ——
**声明地址从来不落盘**（`share_list` 每次现算，这是 FIX B 的设计：地址族切换会改
对外 host，落盘的会变死链）。所以**代码一换，地址立刻就是缩短版**：

```
$ bash /root/conf/share.sh list          # 未 refresh，分发后第一次读
  1) http://107.173.154.178:9443/share/7dd1e7a55a631fa5bd1f8446dbf118fc?interop=1&kernel=xray&distribution=xray&formats=uri%2Cxray&url-xray=%2Fshare%2Fff3022fb954c1df70e69389b1dc595d5
  2) http://107.173.154.178:9443/share/f64f61ce35e42b39a5f928d1c6d15ae5?interop=1&kernel=xray&distribution=xray&formats=uri%2Cxray&url-xray=%2Fshare%2F498f192bf0f72d43aec6edd8b1bfdf8b
```

两条都是 **178 字节**（`229 → 178`，−51）。都对外可拉（HTTP 200，查询串被公共服务
剥掉后正文照常返回）。

| 复核项 | 结果 |
|---|---|
| 声明地址（线上真值） | 上面两条，各 **178 字节**；token 与分发前完全一致（没有重发） |
| 成对 | `7dd1e7a5`↔`ff3022fb`、`f64f61ce`↔`498f192b`：`role`/`parent`/`native_token` 全部齐全 |
| TTL / 次数 | 四条记录 `expires_at=0`、`max_uses=0`（永久、不限） |
| payload **未变** | 正文 sha256 一字未动：主产品 `cf6cba8a8457…`（5 行）/ `2ab20475669b…`（4 行）；原生 `af42095032cc…`（5 outbounds）/ `c525f666b25f…`（4 outbounds） |
| CC `xbd node sub`（用缩短地址） | `✓ 本次拉取: 原生 Xray JSON —— 同内核同发行版 (xray/xray) → 取原生` / `✓ 解析出 5 个节点` |
| `bash /root/conf/share.sh refresh` 幂等 | 连跑两次**都是无输出**（无事可做）—— 地址现算、内容与 meta 都已是当前口径 |
| 旧分享 | `f64f61ce…` **保留**（撤销与否是用户的决定，本轮没动） |

## UNKNOWN

- 三家一致性台（协调方持有）对本节的逐条比对结果**我这里没有**（我只能证明 X 侧行为）。
- 三家一致性台（协调方持有）对本节的逐条比对结果**我这里没有**（我只能证明 X 侧行为）。
