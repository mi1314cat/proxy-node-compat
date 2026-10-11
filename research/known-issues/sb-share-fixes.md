# SB 内核分享层修复报告（`obfs=none` / 带宽偏好 / 一致性校验 / 对角线门禁）

**日期**：2026-10-10（PDT / UTC-7）
**仓库**：`sing-box-core`（只改这一个；`xray--core` / `mihomo--core` 只读）
**状态**：4 个提交**已推到 `origin/main`**（tip `46105c0`）；**线上部署尚未分发**（见 §10，两件事必须分清）
**方法**：真机 E2E + 真内核（mihomo 1.19.32 / sing-box 1.14.2），每格带命令与原文；没跑到证据的一律 UNKNOWN。

---

## 0. 一句话结论

| 项 | 结果 |
|---|---|
| `obfs=none` | 生成侧**找全 1 处**（`hysteria2.sh:294` 的链接模板，扇出 `sb_share-*.txt` + `sb_links-all.txt`），**改 1 处**；导入侧 2 处一并容忍老链接。**线上 13 条链接喂 mihomo = provider 0 节点**，修复后同一批 = **11 节点**（另 2 条 mihomo 本就不认，会跳过） |
| 严重性口径（更正） | `obfs=none` 对 **mihomo 是硬失败**（`missing obfs password` → 整条订阅归零）；对 **sing-box / xray 是静默忽略**（节点照常用）。旧结论"生态共有、三家同等严重"不准确，已按实测更正 |
| SB 分享层其它坑 | 逐条核对后**有 3 处真的会让对方整条订阅归零**（X 的清单覆盖不到）：vmess 用非标准 `uuid` 键、vmess 链接带 `#片段`、vmess+REALITY 被写成 `vless://`。IP 当 sni / 公网 CA 也 pin / 缺 alpn 三项 **SB 侧确认没有** |
| hy2 带宽偏好 | 默认改 **`up_mbps=60` / `down_mbps=200`**（用户偏好上行 60、下行 150~200 的上沿），环境变量与交互输入可显式覆盖；**分享链接不带带宽参数**（由客户端设置），README 写清 |
| 回归脚本 | 新增 `tools/check_share_links.sh`（A 动态生成自测 / B 产物扫描 / C `--fix` / D 客户端导入健壮性 / **E SB→SB 对角线**），对修复前代码**会红**，修复后全绿 |
| 两端解析 + 真连 | 真 mihomo：修复链接 **1 节点 + 真连 204/1.85s**；真 sing-box：分享内容 `check` 通过 + **真连 204/1.30s**；发布→拉取（HTTP 200/400B/sha256 一致）→ 两边解析 → 至少一条真连，全部有原文 |
| 对角线（SB→SB） | **没有倒退**：改后 13 节点导入 / check 通过 / 真连 204；改前 13 / 通过 / 204；线上部署版客户端 13 / 通过 / 204（基线 13+check+204/1.22s） |
| 端到端 | 已做（§9）：生成 → 发布 → 拉取 → mihomo + sing-box 双解析 → 真连 |

---

## 1. 环境与版本（实测取值）

| 角色 | 主机 | 关键版本 |
|---|---|---|
| 目标仓库 | 本机 | `sing-box-core` `/root/deepseek/repos/sing-box-core`；基线 HEAD `7009d93`，我的 4 个提交在其之上 |
| RN（服务端） | `racknerd-75e0e8` / 107.173.154.178 | SB `1.14.2`（`/root/catmi/sing-box/sing-box`，PID 60510 全程未变）；公共分享服务 `proxy-share-service 1.1.0`（:9443，`provider=sing-box`） |
| CC（客户端） | `armbian` / 192.168.1.178 | mihomo `Mihomo Meta v1.19.32 linux arm64`（`/root/catmi/mihomo-client/mihomo`，PID 1364829 全程未变）；sing-box `1.14.2 linux/arm64`（`/opt/sb-client/core/sing-box`，PID 1444214 全程未变） |
| 线上真实产物 | RN `/root/catmi/sing-box/out/` | 13 条链接（`sb_links-all.txt` + 12 个 `sb_share-*.txt`）；**全程只读**，`out/` mtime 收工后仍是 `Oct 10 06:55` |

---

## 2. 问题 1（主要）：`obfs=none` 会让**整条订阅**归零

### 2.1 grep 找全了几处（结论：生成侧 1 处，导入侧 2 处）

```bash
$ grep -rn 'obfs=none\|obfs-password=&' --include=*.sh --include=*.py --include=*.md .   # 仓库内
（无字面量：它是拼出来的）
$ grep -rn 'hysteria2://' --include=*.sh src/
src/conf/hysteria2.sh:294:    local link="hysteria2://…&obfs=$( [[ $mask != none ]] && echo salamander || echo none )&obfs-password=$( … )&alpn=h3"
```

**唯一生成点**：`src/conf/hysteria2.sh:294` 的链接模板。`mask="none"`（默认，即不开混淆）时它无条件吐
`&obfs=none&obfs-password=`，扇出到**两个产物**：`out/sb_share-<tag>.txt` 与 `out/sb_links-all.txt`
（`:328-330`）；`cdn_node.sh` 的 `.cdn.txt` 副本与 `addr_family.py` 的地址族重写都只是**复制/改写这两份**，
不另生成参数 —— 所以是 1 个源头，不是多处。

**导入侧 2 处**（别人家的老链接喂进来时）：`src/conf/outbound_uri.py::parse_hysteria2` 直接
`raise UriError("不支持的 obfs: 'none'")`；`src/client/to_sb.py::_std_uri` 会把
`obfs=salamander` 且**空密码**写成一个内核过不了的 outbound。

### 2.2 实测：一条坏链接打挂整条订阅（真 mihomo 1.19.32，CC）

把**线上真实的** `sb_links-all.txt`（13 条）喂给 mihomo 的 `proxy-providers`：

```
$ mihomo -t -d <cfg>            # 配置本身 test is successful（provider 是懒加载）
$ curl -s 127.0.0.1:<api>/providers/proxies/t | jq -c '{count:(.proxies|length)}'
{"count":0}
# run.log 原文
level=error msg="initial proxy provider t error: proxy 1 error: missing obfs password"
```

**13 条全好、1 条 hy2 脏 → provider 0 节点**，其它 12 条一起消失。逐条隔离（同 harness）：

| # | 链接 | mihomo 加载 | 报错 |
|---|---|---|---|
| 2 | `hysteria2://…&obfs=none&obfs-password=&alpn=h3` | **0 节点** | `proxy 0 error: missing obfs password` |
| 1+2 混合（1 条好 vless + 这条坏 hy2） | — | **0 节点** | 同上报错 |

对照：`vless + naive`、`vless + shadowtls` 这种"mihomo 不认识的 scheme"是**逐条跳过**（各 1 节点），
**只有 obfs 这类"参数非法"才是整条归零** —— 这就是它比"某条协议不支持"严重得多的原因。

### 2.3 严重性口径（按要求更正）

| 客户端 | 遇到 `obfs=none` 的行为 | 证据 |
|---|---|---|
| **mihomo 1.19.32** | **硬失败**：`missing obfs password` → provider **0 节点**，同订阅好节点全丢 | 上文原文 |
| **sing-box 1.14.2** | **静默忽略**：`to_sb.py` 只在 `obfs == "salamander"` 且密码非空时才写 obfs，`obfs=none` 等于没写 —— 节点照常可用 | `src/client/to_sb.py` 分支 + 实测：老链接（`obfs=none`）导入后 `has("obfs")=false`，真连 204 |
| **xray** | 静默忽略（同属"不认识就跳过该参数"） | 本轮未在 xray 内核上单测 —— 与 3×3 验收的口径一致：**UNKNOWN，但无反向证据** |

> 之前记的"生态共有、三家同等严重"**不准确**：正确说法是"**对 mihomo 硬失败、对另两家静默忽略**"。
> SB 自己（分享内容是 sing-box JSON）不受影响，受害面是"把 SB 的 **URI 链接**喂给 mihomo 订阅"。

### 2.4 修法（已提交 `4fccbc6`）

```bash
# 旧（会吐无效参数）
…&obfs=$( [[ $mask != none ]] && echo salamander || echo none )&obfs-password=$(…)
# 新：不开混淆就**不写** obfs（不写即无混淆）
local obfs_q=""
[[ -n "$mask" && "$mask" != "none" ]] && obfs_q="&obfs=salamander&obfs-password=$mask"
local link="hysteria2://$auth@$server_ip:$listen_port?${hop:+mport=$hop&}sni=$CERT_DOMAIN${obfs_q}&alpn=h3"
```

导入侧同时容忍老链接（`outbound_uri.py` / `to_sb.py`：`obfs=none|空|off…` 当"无混淆"；`salamander` 无密码也只跳过该参数）。
沙箱用**真实代码**跑同一个节点（改前 / 改后）：

```
改前: hysteria2://…@107.173.154.178:31001?sni=hxicc…&obfs=none&obfs-password=&alpn=h3#🇺🇸 rn hysteria201-TLS
改后: hysteria2://…@107.173.154.178:31001?sni=hxicc…&alpn=h3#🇺🇸 rn hysteria201-TLS
开混淆时（回归断言 A2）: …&obfs=salamander&obfs-password=<24位hex>&alpn=h3   ← 参数仍然照写
```

---

## 3. 顺带核对：SB 分享层还有没有"写了但对方必然报错"的参数

对着 X 侧刚修的清单逐条核对，并**逐条**把 13 条链接喂真 mihomo。

### 3.1 X 清单里的三项：SB 侧确认"没有"

| X 的问题 | SB 侧核对方法与结论 |
|---|---|
| 分享层丢 SNI | 13 条链接逐条 `grep`：TLS 型链接**全部带 `sni=`**（vmess 的在 base64 JSON 里），无一缺失。**没有** |
| 公网 CA 也 pin | 13 条链接 + 线上 14 个 outbound **零 pin**（`certificate_public_key_sha256` 全缺）；代码侧 `[[ "$CERT_TRUSTED" == "false" ]] && pin=…`。**没有** |
| 缺 alpn | hy2/tuic 全带 `alpn=h3`；CDN 节点 `alpn=http/1.1`；REALITY 型不带（内核语义如此）。**没有**（已固化成门禁断言） |

### 3.2 但**新发现 3 处 SB 自己的坑**，性质与 `obfs=none` 同级（整条订阅归零）

全部用真 mihomo 复现，全部已修（`4fccbc6`）：

| # | 现象 | mihomo 原文 | 影响 |
|---|---|---|---|
| a | `vmess://` 的 base64 JSON 只写了 `"uuid"`，**没有标准 `"id"`** | 单纯缺 `id` 不报错但 UUID 为空；配合 ② 直接整条挂 | 自家 `to_sb.py` 也读 `id` → **自家链接导入自家客户端得到空 UUID 的死节点**（实测：改前 `uuid=''`，改后 `48af28ea-…`） |
| b | vmess 链接末尾追 `#名字`（其它协议的正常写法） | `convert v2ray subscribe error: format invalid` → provider **0 节点**；`error:url.Port() is empty` | 1 条 vmess 打挂整条订阅 |
| c | vmess+REALITY 被写成 `vless://…&encryption=aes-128-gcm&security=reality…` | `proxy 1 error: invaild vless encryption value: aes-128-gcm` → provider **0 节点** | 协议名本身就是错的（服务端是 vmess inbound），且打挂整条订阅 |

隔离实验（真 mihomo，逐条）：

```
# b 的最小复现（标准 JSON，只多一个 # 片段）
w1 (标准, 无片段)      nodes=1
w2 (标准 + #FRAG)      nodes=0   ← # 片段是致命的
# 另测：把 "ps" 从 JSON 里删掉 → nodes=0（mihomo 靠 ps 识别这是 vmess 链接）
# a 的最小复现：cand1{add,port,id,aid,net,path,host,tls,sni} → nodes=0；加上 "ps" → nodes=1
```

修法（`vmess.sh`）：UUID 写标准 `"id"`（同时保留 `uuid` 兼容老读法）、名字进 `"ps"`、
**末尾不加任何后缀**、reality 写 `vmess://` + `tls:"reality"` + `pbk/sid/fp`、
gRPC 的 `service_name` 写进 `path`（原来 `TR_PATH` 为空 → 分享出去是空服务名，3 个 grpc 预置方案全中）。
客户端解析器（`to_sb.py`）与导入器（`outbound_uri.py`）同步支持 `id`/`uuid`、`tls:"reality"`、`ps`。

**修复后同一批链接的效果**（真 mihomo，`m_fixed13`）：

```
deployed13（线上原样）:  nodes=0     ← proxy 1 error: missing obfs password
fixed13（本次修复后）:   nodes=11    ← naive+https / shadowtls:// 两行被跳过（mihomo 无这两个独立出站）
逐条真连:  8/11 = 204（exit_ip=104.28.201.73 ≠ CC 自身 IP）
           连不通的 3 条: vmess02-REALITY / trojan02-REALITY / anytls02-REALITY
           —— REALITY 在 mihomo 里**只支持 vless**（与 README 已有的"REALITY 不能配 ws"同源）
```

### 3.3 顺带发现（同批提交，1 行）：`to_sb.py` 单条坏条目炸整批

`_from_clash_list` 是**模块级**函数，却调用只在 `convert()` 内部存在的闭包 `_note`：

```
$ python3 src/client/to_sb.py <4 条 YAML: 2 好 + 1 未知 type + 1 值非法>
  File "…/to_sb.py", line 567, in _from_clash_list
NameError: name '_note' is not defined          ← 整批 0 导入
```

这正是"M 的 19 节点分享喂 SB 客户端 → 0 导入"的成因。改为模块级
`_skip_note(rep, msg)`：单条异常只跳过自己并记原因。修复后同一份输入
`共=4 成功=2 跳过=2 跳过原因={"不支持的 clash type: totally-unknown-proto": 1, …}`。
已加断言（门禁 D1/D2/D3）。

---

## 4. 对角线（父亲要求：SB 分享 → SB 客户端，红线）

**为什么单列**：mihomo 侧真的断过一次（加旗帜命名把自家分享生成打成 0/19）。
本次改的正是链接内容与产物，最容易连带打断自家解析路径，所以做成**可重复执行的断言**（门禁 E 段）：

```bash
bash src/conf/share.sh create-all 8 1                     # 服务端发聚合分享
bash tools/check_share_links.sh --share-url http://<server>:9443/share/<token> \
     --client-bin /opt/sb-client/core/sing-box
```

断言：**E1** `client.sh add`（真实 CLI 入口 → `add_node`）导入**节点数非 0**；
**E2** `sing-box check` 通过；**E3** 真连 204；**E4** 生产 `sb-client` MainPID 前后不变。

### 改动前后各跑一次（CC 真机 arm64 + 真内核，隔离运行，生产 PID 全程 1444214 未变）

| 变体 | `to_sb.py` | compat | 导入节点数 | `sing-box check` | 真连 |
|---|---|---|---|---|---|
| 改后（本次 4 个提交，HEAD） | `46105c0` | 开 | **13** | 通过 | **204 / 1.54s** |
| 改后（关 compat，走旧路径） | `46105c0` | 关 | **13** | 通过 | 204 / 1.87s |
| 改前（父亲基线 `7009d93`） | `7009d93` | 开 | **13** | 通过 | 204 / 1.84s |
| 线上部署版客户端 | `/opt/sb-client/share-state/to_sb.py` | 关 | **13** | 通过 | 204 / 0.77s |

原文（改后、compat 开）：

```
[OK]   分享配置已获取
[OK]   已导入 13 个节点 (单个链接全量分享); 现 13 个可用节点
RESULT label=post import_rc=0 nodes=13 check_rc=0 connect=204|1.538534 exit_ip=104.28.201.73 prod_pid=1444214->1444214
```

⇒ **对角线保持，无倒退**（3×3 验收基线：13 节点导入、check 通过、真连 204/1.22s；本次 0.77~1.87s 属正常抖动，
全部 204 且 exit_ip = RN 出口 `104.28.201.73`）。

---

## 5. 问题 2：hy2 带宽偏好对齐（60 / 200）

| 项 | 改动 |
|---|---|
| 默认值 | `up_mbps=60` / `down_mbps=200`（原硬编码 `100 / 500`）；服务端 inbound 与客户端产物**都改**；下行按父亲明确要求统一 **200** |
| 显式覆盖 | `SB_HY2_UP_MBPS` / `SB_HY2_DOWN_MBPS`（批量/非交互）；交互建节点时新增一问，**回车即默认** —— 显式给的值不被默认覆盖；非法值（非正整数）回落默认 |
| 字段名对照 | sing-box：`up_mbps` / `down_mbps`；mihomo：裸 `up` / `down`（`to_mihomo.py` 写 `"200 Mbps"`）。**实测 mihomo 两种写法都收**：`up: 60 Mbps` 与 `up: 60` 都加载成功并真连 204 |
| 分享链接 | **不带**带宽参数（URI 里没有 up/down）—— 与"由客户端设置"一致；需要固定值就改客户端配置 |
| 未改（口径外） | TCP Brutal（多路复用里的 `brutal`）默认仍 100/200：那是**真限速**（填高会丢包），与 hy2 的速率提示不是一回事，已在 README 标注 |

沙箱证据（用真实 `hysteria2.sh` 生成）：

```
默认            -> "up_mbps": 60,  "down_mbps": 200
SB_HY2_UP_MBPS=77 SB_HY2_DOWN_MBPS=333 -> 77 / 333
SB_HY2_UP_MBPS=abc SB_HY2_DOWN_MBPS=-5 -> 60 / 200   （非法值回落）
mihomo YAML 产物 -> up: 60 Mbps / down: 200 Mbps     （真 mihomo 加载 + 真连 204）
```

---

## 6. 问题 3：分享产物 vs 真实监听 —— 有没有校验缺口？（有，已补）

### 6.1 缺口确认

SB 的做法（分享内容 = 客户端产物 `cp`，字节一致）**确实比 X 干净**：不存在"分享层再渲染一遍"导致的不一致。
但副本在创建那一刻**冻结**，于是有另一类不一致 —— **产物 vs 真实配置/监听**：

- `_sb_share_content_file` 原来只 `grep -q '"outbounds"'`，不校验内容里的节点是否还在 `config/*.json` 里；
- `cleanup_node_shares` 只扫**旧的本地目录** `share/shares/*.json`（迁移到公共服务后**空转**），
  所以 README 上"删除任何节点会自动清理其 share token"这句承诺**实际早已失效**；
- `share_refresh_all` 对"产物已不存在"的记录只能 `continue` ⇒ 那条链接**永远不会自愈**，
  用户手上的订阅是死的（与 mihomo 侧 P-M2 同后果、不同成因）。

### 6.2 补的三件事（`406afcc`）

1. `share.sh` 新增 `sb_share_consistency_check <tag|all>`：发布前校验
   ①内容里每个 outbound 的 tag 必须在 `config/*.json` 的 `inbounds[].tag` 里
   （兼容聚合的 `<前缀>-` 与 shadowtls 内层 `<tag>-out`）；
   ②直连节点 `server_port` 必须等于 `listen_port`（CDN 节点跳过：只听 `127.0.0.1`，客户端走 `域名:443`）；
   ③端口是否真在监听（`ss`）—— 只告警不拦。**不一致就拒绝发布**。
   CLI：`bash conf/share.sh check <tag|all>`。
2. `cleanup_node_shares` 补公共服务侧下架（新增 `share.sh revoke-tag`）；`share_refresh_all`
   对"产物已删"的记录**直接下架**。
3. 门禁脚本（下节）。

### 6.3 验证（沙箱 9 例 + 假服务全链路）

| 例 | 场景 | 期望 | 实测 |
|---|---|---|---|
| 1 | 产物与配置一致 | 0 | ✅（并正确告警"端口未监听"） |
| 2 | 产物端口 ≠ 真实监听 | 1 | ✅ `端口 (65500) 与真实监听配置 (31001) 不一致` |
| 3 | 配置目录里还有 json、但节点已删 | 1 | ✅ |
| 4 | 聚合里混进幽灵节点 | 1 | ✅ 点名 `xiaomi-ghost01-TLS` |
| 5 | 聚合干净 | 0 | ✅ |
| 6 | CDN 节点（监听 127.0.0.1，产物 443） | 0（跳过端口比对） | ✅ |
| 7 | 带服务器前缀的聚合 | 0 | ✅ |
| 8 | shadowtls 双层产物（内层 `-out`） | 0 | ✅ |
| 9 | 内层端口被改坏 | 1 | ✅ |

另用**假 proxy-share-service**（本地 HTTP，实现与 `share_client.py` 完全同接口）跑通全链路：
`发布 → 拒绝端口不符 → 拒绝幽灵产物 → 删节点后记录被下架 → 刷新时下架死记录`（原文见提交信息）。

---

## 7. 新增回归门禁：`tools/check_share_links.sh`

```bash
bash tools/check_share_links.sh                 # A+D+E(需 URL)+B 全跑
bash tools/check_share_links.sh --out-dir DIR   # 只扫某台机器的产物
bash tools/check_share_links.sh --no-gen        # 跳过沙箱自测
bash tools/check_share_links.sh --fix           # 把老产物里的无效 obfs 参数就地删掉
bash tools/check_share_links.sh --share-url URL --client-bin PATH   # 加跑对角线
```

| 段 | 内容 |
|---|---|
| A | 用**真实 `conf/*.sh`** 在 `/tmp` 沙箱生成 hy2(无/有混淆)、vmess(TLS/REALITY)、vless 链接并断言（沙箱替身：不碰防火墙/systemd/公共服务） |
| B | 扫 `$SB_OUT_DIR` 的 `sb_share-*.txt` / `sb_links-all.txt` |
| C | `--fix`：删掉老产物里的 `obfs=none` / 空 `obfs-password` |
| D | 客户端导入健壮性：单条坏条目**不得**中断整批；老 `obfs=none` hy2 与老 `uuid` vmess 仍能导入 |
| E | 对角线（§4） |

**负向验证（关键）**：把同一个脚本拿到**修复前**的代码与**线上真实产物**上跑 —— 它必须红：

```
$ bash tools/check_share_links.sh --out-dir <线上产物副本>      # 修复前代码
  [FAIL] A1 hy2 (无混淆): 带无效 obfs 参数 (obfs='none') …
  [FAIL] A1: 没开混淆却出现了 obfs 参数: hysteria2://…&obfs=none&obfs-password=&alpn=h3…
  [FAIL] A3 vmess (TLS): 带了 #片段 / 缺 ps 字段
  [FAIL] A4: vmess+REALITY 的链接写成了 vless:// …
  [FAIL] D1: 一条坏条目把整批导入炸掉了 (rc=1) … NameError: name '_note' is not defined
  [FAIL] D3: 老 vmess 链接导入后 UUID 为空
  [FAIL] sb_share-hysteria201-TLS.txt / sb_share-vmess01-TLS-CDN.txt / sb_share-vmess02-REALITY.txt / sb_links-all.txt …
  结果: [FAIL]

$ bash tools/check_share_links.sh --out-dir <同上>             # 修复后代码 (A/D 段)
  [OK] A1…A5, D1…D3      结果: [OK]
```

CC 真机整跑（含 E 段，见 §4 表）：`A1-A5 / D1-D3 / E1-E4 全绿，结果: [OK] 全部通过`。

---

## 8. 其它核对与顺手修

| 项 | 结论 |
|---|---|
| 地址族切换（`addr_family.py`）会不会漏改 vmess 链接 | **不会**：它已经能解 base64 里的 `add`（docstring 里就写着"vmess 链接的地址在 base64 里，文本替换碰不到"这个历史坑） |
| `vmess.sh` 非 reality 形态在 `set -u` 下 | 会 `REAL_PUB: unbound variable` 中断（`local REAL_PRIV REAL_PUB` 只声明不赋值）。生产入口不带 `-u` 所以没炸；已顺手补空初值（3 行） |
| `vless.sh:214` `TLS_TYPE: unbound variable` | 只在 `set -u` 下暴露；本轮**未改**（改动面外），仅记录 —— 门禁脚本因此显式用**不带 `-u`** 的子 shell 跑真实模块（复现面板真实运行方式） |
| mihomo 认不认 `naive+https://` / `shadowtls://` | **不认**，但只**跳过该行**（不会打挂订阅）。这两条只对 sing-box / xray 系客户端有意义 |

---

## 9. 端到端验收（真机证据）

链路：**用修复后的代码生成 → 发布到公共分享服务 → CC 拉取 → mihomo 与 sing-box 两边解析 → 真连**。

```
# 生成 (修复后的代码 + RN 真实节点参数; 与线上产物的 diff 只有预期的两处)
deployed link:  …?sni=hxicc…&obfs=none&obfs-password=&alpn=h3#…        （线上，旧代码）
fixed link:     …?sni=hxicc…&alpn=h3#…                                  （修复后）
deployed client json ↔ fixed:  仅 "up_mbps/down_mbps": 100/500 -> 60/200
聚合产物 diff:  仅 hy2 的 up_mbps/down_mbps 两行                     ← 其余字节一致

# 发布 (临时记录, 只 POST 公共服务, 不写任何生产路径)
$ python3 conf/share_client.py create --type node --content-file … --ttl 600 --max-uses 5
  {"token":"fb5cf0a1…","content_bytes":400,"content_sha256":"6a11626796a86e53…"}

# 拉取 (与 sb-client add_node 完全同一条 curl 语义)
$ curl -sSL -o pulled.json -w 'http=%{http_code}|bytes=%{size_download}\n' --max-time 20 \
       http://107.173.154.178:9443/share/<token>
http=200|bytes=400        sha256(pulled) = 6a116267…  ← 与服务的 content_sha256 逐字一致

# 两边解析
$ sing-box check -c pulled.json                     -> CHECK_OK (exit 0)
$ mihomo 加载修复后的 hy2 链接                       -> nodes=1

# 真连
sing-box (pulled.json, mixed 127.0.0.1:17941):  http=204|1.295609  exit_ip=104.28.201.73
mihomo   (修复后的 hy2 链接):                    http=204|1.849577  exit_ip=104.28.201.73
mihomo   (13 条修复后链接, 逐条):                8/11 = 204
sing-box (分享 JSON → to_mihomo.py → mihomo YAML): nodes=1, http=204|0.98s
```

生产面复核：RN `sing-box` PID 60510、`nginx`/`proxy-share-service` 全 active；CC `mihomo-client` 1364829、
`sb-client` 1444214 全程未变；测试用的临时内核进程与端口全部回收（`0` 残留）。

---

## 10. ★ 修复在 HEAD，还是已经分发到线上？（两件事必须分清）

| 层 | 状态 | 证据 |
|---|---|---|
| **仓库 HEAD** | ✅ **已修复并推送到 `origin/main`**（tip `46105c0`） | `git log origin/main`；`git push` 输出 `406afcc..46105c0 main -> main` |
| **线上部署（RN）** | ❌ **尚未分发** —— `conf/hysteria2.sh` = `ca21a6e5…`、`conf/vmess.sh` = `46ea084d…`、`conf/share.sh` = `6d492039…`，与**修复前** `7009d93` 的 sha256 逐字相同（修复后 HEAD 分别是 `04e0e0bd…` / `2b215776…` / `613f8e9c…`）；`out/` 里的链接还是旧快照 | `sha256sum` 只读比对 + 门禁 B 段扫描原文见下 |
| **线上部署（CC 客户端）** | ❌ 未分发（`/opt/sb-client/share-state/to_sb.py` 仍是部署版） | 本报告用"部署版"做过对角线对照跑 |

在 RN 上跑门禁的 **B 段（只读）**，直接指出线上产物仍有三类问题（`out/` mtime 收工后仍是 `Oct 10 06:55`）：

```
[FAIL] sb_share-hysteria201-TLS.txt: 带无效 obfs 参数 (obfs='none') —— 对方会 missing obfs password, 整条订阅 0 节点
[FAIL] sb_share-vmess01-TLS-CDN.txt: vmess 链接带了 #片段 / JSON 缺 ps 字段
[FAIL] sb_share-vmess02-REALITY.txt: vless 链接的 encryption='aes-128-gcm' 非法 (vmess+REALITY 曾被误写成 vless://)
[FAIL] sb_links-all.txt: 第 2 / 7 / 11 行同上
```

**分发步骤（需要用户/有权限的人执行，本轮未做 —— 边界禁止写生产路径）**：
1. 在 RN 用新代码覆盖 `conf/`（`install.sh` 的模块复制路径，或逐文件替换 `conf/{hysteria2,vmess,lib,share,outbound_uri}.sh`、`conf/outbound_uri.py`、客户端 `share-state/to_sb.py`）；
2. 重建受影响节点（hy2 + 两个 vmess）以刷新 `out/` 链接产物，或直接 `bash tools/check_share_links.sh --fix --out-dir /root/catmi/sing-box/out` 清掉老链接里的 obfs 参数（vmess 老链接无法原地修好，需重建节点）；
3. 重新发布分享（`share.sh create/regen`），然后跑一次门禁的 B 段与 E 段确认全绿。

---

## 11. UNKNOWN

1. **xray 客户端遇到 `obfs=none` 的确切行为**：本轮只在 mihomo 与 sing-box 上做了单测；xray 侧按"不认识就忽略"推断为静默忽略，**没有单测证据 → UNKNOWN**（无反向证据）。
2. **v2rayN / Nekoray / Shadowrocket 等非 mihomo 客户端对修复后 vmess 链接（`id`+`ps`，无片段）与 vmess+REALITY 链接的接受度**：只在 mihomo 1.19.32 与自家 `to_sb.py`/`outbound_uri.py` 上验过 → 其他客户端 **UNKNOWN**。
3. **mihomo 为何要求 vmess JSON 必须带 `ps`**（未带则 `format invalid`）：只做了行为级最小复现（加 `ps` → 解析成功），没有读 mihomo 源码定位判定逻辑 → **UNKNOWN**。
4. **`vless.sh:214` `TLS_TYPE` 未初始化在 `set -u` 下的影响面**：只证明门禁脚本以 `-u` 跑会中断，生产入口不带 `-u` 所以未观察到故障 → 线上影响 **UNKNOWN**。
5. **线上 `obfs` 混淆型 hy2 节点**（`mask != none`）本轮没有真实样本可测（RN 的 hy2 `mask=none`）：修复后"开混淆仍照写参数"只有沙箱断言（门禁 A2），**没有真机连通的混淆节点证据 → UNKNOWN**。
6. **`share_refresh_all` 下架死记录**只有假服务验证，**未在公共服务上制造"删节点 → 记录被自动下架"的真实场景**（那会动生产记录）→ 线上行为 **UNKNOWN**（代码路径与假服务一致）。

---

## 12. 本轮新增的生产面足迹与清理（全部已还原）

| 面 | 动作 | 还原 |
|---|---|---|
| RN 公共服务记录 | 新建 3 条临时记录（2 条聚合 + 1 条单节点，`meta.tag` 均为 `e2e-*`） | **3 条全部 `delete`**；收工时 `provider=sing-box` 回到 `total 0 / active 0` |
| RN 文件 | 临时 `/tmp/e2e-sb-fixed.json`、`/tmp/e2e-sb-all.json`、`/tmp/csl.sh` | 已删（**未写任何 `/root/catmi/*` 路径**；`out/` mtime 未变） |
| CC 文件/进程 | 隔离根、门禁脚本、测试用配置全在 `/tmp` | 已删；临时内核进程与端口 0 残留 |
| 本机 | 沙箱、假服务、测试产物全在 `/tmp` | 已删 |
| 服务/PID | RN `sing-box=60510`、`nginx`、`proxy-share-service` active；CC `mihomo-client=1364829`、`sb-client=1444214` | **全程未变**（每次测试都核对 PID，门禁 E4 固化了这一条） |
| 推送凭据 | 一次性 PAT 走临时 `GIT_ASKPASS`（token 只从环境变量读，不落文件） | 用完 `shred -u`，文件已不存在；未写入 `.git/config` |

> 说明：收工时 `health` 里 mihomo/xray 的计数与我开工时的基线不同 —— 那是**另一路并发会话**（3×3 验收）在其间增删记录所致，与本轮无关；SB 自己的 provider 已回到 0。

---

## 13. 复现命令速查

```bash
# 门禁 (本机/服务器均可跑; 只读 + /tmp 沙箱)
bash tools/check_share_links.sh                                  # 全量
bash tools/check_share_links.sh --out-dir /root/catmi/sing-box/out   # 只扫线上产物
bash tools/check_share_links.sh --fix --out-dir <out>            # 清老产物里的无效 obfs

# 对角线 (CC 这类真客户端机上)
bash src/conf/share.sh create-all 8 1        # 服务端拿 URL
bash tools/check_share_links.sh --share-url http://<server>:9443/share/<token> \
     --client-bin /opt/sb-client/core/sing-box

# 一票否决实验 (真 mihomo): 13 条链接喂 provider, 看节点数
#   providers.t.path = <链接文件>;  mihomo -d <cfg> &;  /providers/proxies/t | jq '.proxies|length'
#   线上原样 = 0；本次修复后 = 11
```

---

## 14. 提交清单（`origin/main`，作者/提交者 root@xiaomi.localdomain）

| commit | 主题 |
|---|---|
| `4fccbc6` | 修: 分享链接不再写无效参数 —— hy2 去掉 obfs=none, vmess 改回标准 vmess://（含导入侧容忍 + `to_sb.py` 单条坏条目不炸整批） |
| `fe47df8` | 改: hy2 带宽默认对齐用户偏好 60/200（显式设置不被覆盖） |
| `406afcc` | 加: 分享生成后一致性校验 + 删节点下架分享 + 链接回归检查脚本 |
| `46105c0` | 加: 门禁补「SB 分享 → SB 客户端」对角线断言 (E 段) + README 用法 |

**基线**：`7009d93`（另一路会话的 compat 层提交，已在其上）。
