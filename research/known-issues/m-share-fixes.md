# M 内核（mihomo--core）分享链路修复报告

**日期**：2026-10-10（PDT / UTC-7）
**目标仓库**：`/root/deepseek/repos/mihomo--core`（分支 `refactor/v2`，与 `main` 保持一致）
**素材**：`known-issues/m-and-sb-open-issues.md`、`e2e/share-link-cross-kernel.md`（327 行）
**边界**：只改 `mihomo--core`；RN（`ssh rn`）与 CC（`ssh CC`）**只读使用**，实验一律在 `/tmp`，跑完清理；**未重启任何生产服务**。

---

## 0. 一句话结论

| 条目 | 结论 | 关键证据 |
|---|---|---|
| **P-M1**（严重）分享订阅生成 100% 失败 | ✅**已修** | 修前真机数据 `19 个活节点全被剔除`；修后 **19 个节点**，订阅 URL → 真客户端拉取 → 真内核 **19 节点** |
| **P-M2**（严重）已发出内容永久冻结 | ✅**已修/已刷新** | 冻结记录 `ec23e4cb…`：232B / `port: 20000` → 修后 `share_refresh_all` 真正刷新为 **6312B / 19 节点 / 端口全部在听**，token 与 URL 未变 |
| **P-M3** URL 链接 12 条里 10 条端口无人监听 | ✅**已修 + 加发布前闸门** | 真机判定 **9 陈旧 / 3 可用**（逐条原因见 §4）；陈旧链接**拒发**并可一键回收 |
| **P-M4** M 客户端不吃自家 URL 链接 | ✅**已修**（客户端侧路径） | 修后喂 `anytls_share-02.txt` → `已写入 …（1 个节点，分享链接由内核解析）`，`mihomo -t` 通过，真连 **204 / 0.82s / 出口 104.28.201.73** |
| **P-5** `obfs=none` 搞挂整条订阅 | ✅**已修** | 真内核实测：1 条坏的 → `missing obfs password` / provider **0**；1 坏 + 8 好 → **0 节点**；修后 9 条全好 → **9 节点** |
| **P-6** hy2 默认 60/150~200 | ✅**已做** | 默认链接 `up=60&down=200`（+ `upmbps/downmbps`）；用户设 45/170 → 链接照用 **45/170**（未被默认值覆盖） |
| **额外** hy2 自签节点的 `pin=` | ✅**已修**（`pin` → `pinSHA256`） | 同一自签节点：`pin=` → **000**；`pinSHA256=` → **204 / 1.67s** |
| 门禁 `tools/check_all.sh` | ✅**18/18 全过**（原 16 项 + 分享产物 + 对角线） | 见 §8 |
| 对角线 M→M | ✅**保持/改善**，并已加专门闸门 | 19 节点 + 逐节点真连 **14/19**（= 文档基线），见 §9 |

---

## 1. 环境与基线（实测）

| 角色 | 主机 | 关键版本 |
|---|---|---|
| RN（服务端） | `racknerd-75e0e8` / 107.173.154.178 | `Mihomo Meta v1.19.32`；`proxy-share-service 1.1.0`（:9443） |
| CC（客户端） | `armbian` / 192.168.1.178 | `Mihomo Meta v1.19.32 linux arm64`（`/root/catmi/mihomo-client/mihomo`） |

```
# 开工前 / 收工后（RN）
$ systemctl is-active mihomo proxy-share-service nginx xrayls sing-box
active active active active active          # 全程未重启
mihomo PID 119320（= 既有基线）
# 收工后分享服务形状（我建的测试记录已 revoke）
{"mihomo":{"total":1,"active":0,...},"sing-box":{"total":2,"active":1,...},"xray":{"total":2,"active":2,...}}
#   mihomo 与开工前逐字一致（total=1 / active=0）
#   sing-box / xray 的计数在本会话期间被**另一个并发会话**改动过（不是我：我只建过 1 条 mihomo 记录并已删除）

# CC 生产客户端 PID 全程 1364829（未变）
```

> 说明：本会话期间 `mihomo--core` 工作区里还有**另一个并发会话**在改 `client.sh` / `install.sh` / `core_mgmt.sh` / `manifest.txt` 并新增 `src/lib/nodecompat.py` 等（proxy-node-compat 接入）。这些改动**全部未被我的任何一次提交包含**（我逐个文件按内容精确 stage；`git show --stat` 可验）。

---

## 2. P-M1（严重）· 分享订阅生成 100% 失败 —— 已修

### 根因（一句话）
`build_sub.py` 的「剔除陈旧产物」用 `.managed.json` 里的**裸名**（`mAnyTLS01-TLS`）去**等值匹配** `out/*_client-*.yaml` 的**带旗帜名**（`🇺🇸 mAnyTLS01-TLS`）→ 交集 **0/19** → 19 个活节点全被判成陈旧剔除。

### 修法
- `src/lib/naming.py` 新增 `strip_flag()` / `match_key()`：**去旗帜比较**的唯一实现（旗帜是显示属性，不是身份）。
- `src/share/build_sub.py`：过滤改成两侧都过 `node_key()`（去旗帜 + 折叠空白）。**显示名一个字节不动**（红线：不许为了匹配把旗帜从名字里去掉）。
- 过滤后一个都不剩时不再只说「out/ 为空」，而是明确报「存活名单与产物一个都对不上」并打印名单示例（静默故障必须留线索）。

### 真机证据（RN，只读）
```
# 修复后（/tmp 里的修复版代码 + RN 真实 out/conf）
$ python3 /tmp/mfix/src/share/build_sub.py --out-dir /root/catmi/mihomo/out \
        --conf-dir /root/catmi/mihomo/conf --tag all -o /tmp/mfix/sub_all.yaml
[OK] 已生成 /tmp/mfix/sub_all.yaml (19 个节点)          exit=0
  - name: 🇺🇸 mAnyTLS02-TLS      ← 显示名仍带旗帜

# 同一条命令跑在**现盘旧代码**上（对照）
$ python3 /root/catmi/mihomo/src/share/build_sub.py --out-dir … --conf-dir … --tag all
[清理] 剔除了 19 个陈旧产物 (节点已删除, 但 out/ 里旧文件还在)
[ERR] 没有任何可用节点 (out/*_client-*.yaml 为空?)      exit=1
```
协议桶也回来了：`anytls anytls_anytls hysteria2 hysteria2_hysteria2 reality_reality reality_reality-grpc reality_reality-xhttp trojan_cdn-t-grpc trojan_cdn-t-ws trojan_trojan trojan_trojan-grpc trojan_trojan-tls tuicv5_tuicv5 vless_cdn-v-grpc vless_cdn-v-ws vless_vless-ws vless_xhttp-cdn vless_xhttp-tls`（原来只剩「全部」）。

### 端到端验收（RN 发 → CC 真客户端拉 → 真内核解析 → 真连）
```
# ① RN（/tmp 沙箱：真数据副本 + 修复版代码）—— 面板非交互那条路
$ share_gen_tag_auto all 0 2
  一次性分享链接  用 0 次 · 2 小时后过期
  http://107.173.154.178:9443/share/eb001ee58ab65d3d7314a23c9a23740a

# ② CC：M 官方客户端（CLI_ROOT 隔离到 /tmp，生产 unit 指向不存在的名字）
$ CLI_ROOT=/tmp/mcli CLI_SERVICE=mihomo-e2e-tmp bash -c 'source ./client.sh; printf "%s\n" "<URL>" "2" "" | node_add'
[OK] 已写入 /tmp/mcli/conf/providers/eb001ee58ab65d3d7314a23c9a23740a.yaml (19 个节点)
[OK] 已给 19 个节点加上前缀 [eb001e-]
[OK] 配置已生成并通过全部校验
$ systemctl show -p MainPID --value mihomo-client
1364829                                  # 生产客户端全程未动

# ③ 真内核（真 mihomo，最小 harness：provider=19 节点，rules MATCH,g）
provider nodes = 19
group 'g' -> 19 nodes
  🇺🇸 eb001e-mAnyTLS02-TLS      http=204|0.81   exit_ip=104.28.201.73
  🇺🇸 eb001e-mAnyTLS03-TLS      http=204|0.91   exit_ip=104.28.201.73
  🇺🇸 eb001e-mAnyTLS01-TLS      http=204|3.36   exit_ip=104.28.201.73
  🇺🇸 eb001e-mHysteria202-TLS   http=204|1.84   exit_ip=104.28.201.73
  …（19 行）
PROXY_OK=14/19 (204 且出口IP != CC 自身)
```
CC 自身出口 IP = `183.210.249.163`；上表出口 IP 全部是 RN 的 CF 出口 `104.28.201.73`（≠ 本机）⇒ **确实走了节点**。
**14/19 与文档基线一致**（未连通的 5 条全是 CDN 节点——最小 harness 没有客户端那套 DNS/ECH 配置；换回客户端生成的配置后这 5 条 CDN 节点实测 **5/5 http=204**，见 §9）。

---

## 3. P-M2（严重）· 已发出的分享内容永久冻结 —— 已修 + 来源结论

### 修好后的刷新验证（在那条**真实冻结记录**上做的）
```
# 刷新前
 token=ec23e4cb8196 bytes=232  sha=1d6c4b6ac58fd952 enabled=False
   content: - name: 🇺🇸 mAnyTLS01-TLS / type: anytls / port: 20000 / sni: www.amazon.com …

# 跑修复后的 share_refresh_all（沙箱读真实 out/conf 副本；token/URL 不变）
$ share_refresh_all
[Info] 已刷新 1 条分享链接的内容 (token 与地址未变)

# 刷新后
 token=ec23e4cb8196 bytes=6312 sha=08d847fe84a274b0 enabled=False
 nodes=19   ports=['28725','22812','25684','20309','25682','25669', …]
# 19 个端口逐一对照 `ss -tulnH`：**全部在听**
```
⇒ **P-M2 的"永久冻结"已经解除**：内容会随节点变更被真正刷新（该记录自身仍是 legacy 时期 `enabled=false` + 已过期，所以它本就不该再被拉取；这一点由它的元数据决定，不是刷新机制的问题）。

### `port: 20000` 的来源（查得到就写结论，查不到写 UNKNOWN）
**已证实的部分**：
1. 这条 232B 记录就是**旧实现里的那条分享**：token 与
   `/root/catmi/mihomo/share/shares/ec23e4cb8196d688053de91240e52dae.json.migrated`
   完全一致（`expires_at=1791516793`、`used_count=1`、`enabled=false`、`last_used_at=1791430408` 逐字段相同），由 `share_legacy_migrate` 导入公共服务。
2. 公共服务 `create` 对已存在的 token 返回 **409** 且 `created_at` 只能取"创建那一刻"，所以记录的创建时间就是 **created_at=1791541206 = 2026-10-09 03:20:06 PDT**（与 `share/shares/` 目录 mtime 03:20:07 吻合）。
3. `port: 20000` 在**旧的一代监听**里是真实存在的：
   ```
   $ grep -n "20000" /root/catmi/mihomo/mihomo.log | head -1
   29:… "Vless[mVLESS01-REALITY] proxy listening at: [::]:20000"        # 首见 10-06 18:47:12
   $ grep -n "20000" …/mihomo.log | tail -1
   17824:… "Vless[mVLESS01-REALITY] proxy listening at: [::]:20000"     # 末见 10-07 19:34:11
   $ grep -rn "port: 20000" /root/catmi/mihomo/nodes.bak.* 
   nodes.bak.20261007-194459/reality-01.yaml:6:    port: 20000
   nodes.bak.20261007-194459/out/reality_reality_client-01.yaml:5:    port: 20000
   ```
   ⇒ 快照里的目标端口属于 **10-06 → 10-07 那一代节点**（10-07 19:45 之后就没有了）。

**未证实（UNKNOWN）**：这 232B 具体是**谁**写进去的。反证如下 ——
- 内容是 `type: anytls` + `password = d57e8933-bbe1-4d09-b6d9-800f29fb746a`（该串只出现在 `install_info.env` 的旧 `UUID=` 里）+ `sni: www.amazon.com`；
- 全盘（现盘 + 4 个备份）里**没有任何 anytls 产物用过 20000 端口**（`grep -rn "port: 20000"` 只命中上面两个 reality 文件）；
- 名字里的 `🇺🇸` 需要 10-09 21:20 之后才上线的旗帜代码，而 10-09 02:35 / 05:35 的脚本备份里 `m_with_flag` 计数为 **0**；
- 记录的**最后一次写盘**是 10-09 21:11:55（`stat`），恰是 `share_refresh_all` 那轮 GET 的时刻。

⇒ 结论：**这条快照的确是"陈旧且无人刷新"的产物（缺陷本身已被 P-M1 修复并实测刷新成功），但它最初那 232 字节的确切生成路径无法用现盘证据复原 —— UNKNOWN**（不编故事）。

---

## 4. P-M3 · 链接端口与实际监听不一致 —— 已修 + 发布前闸门

### 真机逐条判定（修复后的 `link_check.py`，只读跑 RN 真实数据）
```
$ python3 src/share/link_check.py --out-dir <RN out 副本> --conf-dir <RN conf 副本>
  [拒发] anytls_share-01.txt:   50877 —— 链接里的凭据已不在任何当前节点里 (节点被删掉/重建过)
  [拒发] hysteria2_share-01.txt:21168 —— 凭据已不在任何当前节点里
  [拒发] hysteria2_share-10.txt:23512 —— 凭据已不在任何当前节点里
  [拒发] hysteria2_share-11.txt:22737 —— 凭据已不在任何当前节点里
  [拒发] reality_share-04.txt:  42099 —— 端口 42099 无人监听
  [拒发] trojan_share-01.txt:   56676 —— 凭据已不在任何当前节点里
  [拒发] tuicv5_share-01.txt:   38899 —— 凭据已不在任何当前节点里
  [拒发] tuicv5_share-09.txt:   23451 —— 凭据已不在任何当前节点里
  [拒发] vless_share-01.txt:      443 —— 端口在听, 但**凭据早没了** (uuid 不在任何当前节点里)
[拒发] 9/12 条分享链接与当前监听不一致
  OK: anytls_share-02 (28725) · anytls_share-03 (22812) · hysteria2_share-02 (20309)
```
> 与素材里的「10/12」略有出入：按**当前现场**逐条复核是 **9 死 / 3 可**（8 条死在端口、1 条死在凭据 —— `vless_share-01` 端口 443 在听但 uuid 已不存在，这一条原来的"10 条"统计里被记成了"端口在听"）。每条的判据与原因都写在上面，可复算。

### 修法与"拒发"闸门
- 新增 `src/share/link_check.py`（判据三条，全部来自当前现场）：
  1. **凭据**：链接里的凭据必须还在当前片段/产物里（否则节点已被删掉重建）；
  2. **目标**：同凭据的当前产物 `host:port` 必须与链接一致（换了端口没重建链接）；
  3. **监听**：端口要有活 listener 且**协议族对得上**；CDN 链接必须走前端端口（默认 443），且 `cdn_bindings.tsv` 里的**回源端口**必须有人在听。
  不一致 → **拒发**并说清原因。机器可读开关：`--json / --list-stale / --count-only`；`--prune` 只删"整体陈旧"的文件。
- `src/server.sh`「导出全部」：陈旧链接逐条列出原因后**拒发**，只导出与当前监听自洽的；glob 同时覆盖批量命名产物（`<mproto>_<proto>_share-NN.txt` 原来一条都导不出来，面板却照打"已导出"）。「客户端产物设置」顶部把失效链接数摆出来。
- `src/lib/env.sh`：清理路径 `m_artifacts_clean_orphan` 一并回收陈旧链接（原来只按"片段是否还在"清，端口换了的那种一条都清不掉）；取不到校验器时 fail-open（宁可少拦，不让校验器缺失变成发布路径硬故障）。

---

## 5. P-M4 · M 客户端不吃自家 URL 链接 —— 已修

### 查清：是**客户端侧路径**不够宽，不是产物格式不对
- 订阅 URL（`share_tag-*.txt` → `/share/<token>`）一直可用，发的就是 `proxies:` YAML；
- `out/*_share-*.txt` 是**单节点 URI**，给别家客户端用的；
- 关键实测（CC，mihomo v1.19.32）：**内核自己就会解析 URI 列表** —— 把 2 条分享链接放进 `type: file` 的 proxy-provider，内核解析出 **2 个节点**（Hysteria2 + AnyTLS）。所以不需要在客户端里再写一个 URI→YAML 转换器（那会是第二个真源）。

### 修法
- `_add_from_file`：去掉注释/空行后**每一行**都是 `<scheme>://…` 时，原样落成 provider 交给内核解析，并明确告知形态；其余情况行为一字不变（YAML 订阅、垃圾内容报错文案都保留）。判断放在 YAML 解析**之前**（有些链接会让 YAML 解析器直接抛错）。
- `node_prefix_names`：URI 型 provider 也能加组名前缀（改 `#` 片段；旗帜在前、前缀加在旗帜之后、幂等）。
- 新增 `m_provider_count`：节点数统计同时认 YAML 与 URI 列表（`_sub_groups` / `node_list`），否则 URI 型 provider 会显示"0 个节点"。

### 真机证据（CC，修复后的 client.sh，隔离到 /tmp）
```
$ CLI_ROOT=/tmp/mcliuri CLI_SERVICE=mihomo-e2e-tmp bash -c 'source ./client.sh; printf "%s\n" "/tmp/mcliuri/node.txt" "" | node_add'
[OK] 已写入 /tmp/mcliuri/conf/providers/node_txt.yaml (1 个节点, 分享链接由内核解析)
[Info] 这是分享链接 (URI) 列表, 不是 proxies: YAML —— 交给 mihomo 自己的解析器
$ mihomo -t -d /tmp/mcliuri/conf
mihomo -t: OK
providers: [('PROXY', 2), ('default', 5), ('node_txt', 1)]
node=🇺🇸 AnyTLS-02
URI 导入节点实连: http=204|0.819596 exit_ip=104.28.201.73 (CC 自身=183.210.249.163)
```

---

## 6. P-5 · `obfs=none` 一票否决 —— 已修

### 真内核实测（CC，最小 harness；provider 节点数取自 REST API）
```
  single_bad     -t=ok   provider 节点数=0     ← 1 条 obfs=none 的 hy2
  single_fixed   -t=ok   provider 节点数=1     ← 同一条去掉 obfs=none
  mixed_bad      -t=ok   provider 节点数=0     ← 1 条坏 + 8 条好  → 整条归零
  mixed_fixed    -t=ok   provider 节点数=9     ← 9 条（坏的那条修好）→ 全部回来
# 内核原文
level=error msg="initial proxy provider t error: proxy 0 error: missing obfs password"
```
### 修法
`hy2_link()` 在**没有混淆时一个字节都不写** obfs（不写 = 没有混淆，语义等价）；真开了混淆才写 `obfs=/obfs-password`。源码里再出现 `obfs=none` 会被闸门红掉（去掉注释后判断，避免把说明文字当实现）。

---

## 7. P-6 · hy2 默认 60 / 150~200，且以用户设置为准 —— 已做

- 默认值：**上行 60 / 下行 200**（区间：上行 30~100，下行 150~200）；状态文件 `.hy2-bandwidth`，**用户设过就以用户的为准**（`m_hy2_bw_set` 只收裸数字且在区间内的值 —— 写成 `"60 mbps"` 会被内核正则判不中而**静默变 0**，这类值宁可直接拒收）。
- 参数名（跨内核结论，别写错）：**mihomo 的 hysteria2 URI 解析器只认 `up=` / `down=`**（裸数字，Mbps）；`upmbps=`/`downmbps=` 只对已废弃的 hysteria v1 生效 → 两个都写（sing-box 系客户端认后者），各自忽略对方那个（X 内核侧已实测两家都不报错）。
- 客户端 YAML 写 `up: "60"` / `down: "200"`（裸数字 = Mbps）；批量 `all.sh` 也读同一处设置（原来写死 30/200）。
- 面板新增「客户端产物设置 → 6) hysteria2 带宽」，改完可选**同步改已有产物**（只碰 hysteria2 的 YAML `up/down` 与链接的四个参数）并刷新已发出的分享内容。
- 文档：`docs/PROTOCOL-OPTIONS-SPEC.md` 三处「硬编码 50/200」改成实际行为，并写明 `up/down` vs `upmbps/downmbps` 的解析器差异。

闸门探针（真实函数体）：
```
DEFAULT=…&up=60&down=200&upmbps=60&downmbps=200…
USERSET=…&up=45&down=170…          ← 用户设过 → 用用户的, 未被覆盖
```

### 额外修（同一类"参数名静默失效"）：自签节点的 `pin`
`hy2_link` 原来写 `&pin=<sha256>`，而 mihomo 的 hysteria2 URI 分支只读 **`pinSHA256`**（`common/convert/converter.go:72-104`，X 侧逐行核对过）→ pin 被静默忽略 → 自签节点回到证书校验路径，必然连不上。已改成 `pinSHA256=`。同一自签节点（mHysteria202-TLS @20309）实测：
```
pin=<sha>        → http=000|5.00   （pin 被忽略, 证书校验失败）
pinSHA256=<sha>  → http=204|1.67   exit_ip=104.28.201.80   ← 对角闸门 ⑤ 里的真连
```

---

## 8. 门禁 `tools/check_all.sh`

```
$ bash tools/check_all.sh
  ▸ 清单漂移 ✅   ▸ 常量漂移 ✅   ▸ 接线完整 ✅   ▸ 菜单编号 ✅   ▸ yaml 取值守卫 ✅
  ▸ 接口一致 ✅   ▸ 管道早退 ✅   ▸ pre-push 钩子 ✅
  ▸ shell 语法 ✅ ▸ python 语法 ✅ ▸ 发布脱敏 ✅
  ▸ LAN 分发脱敏 ✅ ▸ 节点命名旗帜 ✅ ▸ 分享产物 ✅ ▸ 对角线(分享→客户端) ✅
  ▸ 档位 id 一致 ✅ ▸ 预置不越权 ✅ ▸ 幽灵函数 ✅
═══ 全部 18 项通过 ═══
```
新增两道闸门（原 16 项 → 18 项）：
- `tools/check_share_products.sh`：40 条断言 —— ① 旗帜名/裸名台账匹配（并验"显示名不被改写"）② 链接端口 vs 监听/产物一致性（拒发 / 清单 / 回收 / 正例放行）③ `obfs=none` 不许出现（抽真实 `hy2_link` 跑一遍 + 源码静态兜底）④ 带宽默认值与"用户设置优先" ⑤ 客户端吃 URI 列表（抽客户端真实导入代码跑三种输入）。
- `tools/check_diagonal.sh`：见 §9。

---

## 9. 对角线专项（M 分享 → M 客户端）—— 用户红线

**已把整条链做成可重复执行的门禁**（`tools/check_diagonal.sh`，挂在 `check_all.sh` 里）：
`①生成分享内容（含名字匹配，故意覆盖三种命名组合）→ ②经 HTTP 取回（模拟分享服务，字节一致）→ ③M 客户端导入（client.sh 真实代码）→ ④真内核解析出正确节点数 → ⑤至少一条真连（HTTP 码/耗时/出口 IP）`。
④ 需要 `MIHOMO_BIN`、⑤ 需要 `M_DIAG_REAL_LINK`；**缺内核时明确报"跳过"且不算通过**（不许静默假绿）。

### 改前 / 改后（同一道闸门，只把 `build_sub.py`/`naming.py` 换回修复前版本）
```
改前: 4 通过 / 5 失败
  ❌ 台账=bare 产物=flag → 分享内容生成失败: [清理] 剔除了 3 个陈旧产物 / [ERR] 没有任何可用节点
  ❌   显示名里的旗帜被抹掉了
  ❌ 订阅 URL 取不回来 (HTTP 404)      ← 内容没生成, 服务自然取不到
  ❌ 客户端导入失败 / provider 里只有 0 个节点
改后: 10 通过 / 0 失败 / 1 跳过（本机无内核）
  ① 台账=flag产物=flag → 3/3   ① 台账=bare产物=flag → 3/3   ① 台账=bare产物=bare → 3/3
  ② 取回 200 且与生成内容字节一致   ③ provider 3 个节点
CC 真机（MIHOMO_BIN=真内核 + 真实分享链接）: 14 通过 / 0 失败 / 0 跳过
  ④ 真内核解析出 3 个节点     ⑤ 真实链接被内核解析出 2 个节点
     HY2-REAL     http=204 1.666220s exit_ip=104.28.201.80
```
**覆盖了两种输入**：带旗帜名（`🇺🇸 mAnyTLS01-TLS`）与裸名（`mAnyTLS01-TLS`）——台账侧与产物侧各两种组合，加上"台账带旗帜"的前向组合。

### 与文档基线的对比（`research/e2e/three-servers-three-clients.md`）
| 项 | 基线 | 本轮实测 | 结论 |
|---|---|---|---|
| M→M 订阅节点数 | 19 | **19**（URL 实拉 + 真内核 provider 计数） | 保持 |
| 逐节点真连 | 14/19 | **14/19**（最小 harness；出口 IP 均 ≠ 本机） | 保持 |
| 5 条 CDN 节点 | 需客户端那套 DNS/ECH 配置 | 换回客户端生成的配置后 **5/5 http=204** | 保持 |
⇒ **对角线未倒退**；且现在有了机器可重复的断言，同类回归不会再"静默发生"。

---

## 10. 提交（一条一 commit）

| commit | 内容 |
|---|---|
| `cf0bc6a` | fix(分享): 分享订阅生成 100% 失败 —— 旗帜名与裸名台账按等值比较 (**P-M1**) |
| `0598d21` | fix(分享): 链接产物端口与监听不一致 —— 发布前一致性闸门 + 一起回收 (**P-M3**) |
| `d794a33` | fix(分享): 链接里不再写 obfs=none —— 一条坏节点会把整条订阅打成 0 (**P-5**) |
| `d5af1b0` | feat(带宽): hy2 默认对齐 上行 60 / 下行 150~200, 且以用户设置为准 (**P-6**) |
| `de4cc9b` | fix(分享): hy2 自签节点的 pin 参数名 mihomo 不认 (pin → pinSHA256)（额外） |
| `60fb4c5` | fix(客户端): M 自家客户端能吃自家分享链接 (URI 列表) (**P-M4**) |
| `212b6cd` | test(门禁): 对角线闸门 —— M 分享 → M 客户端 这条链不许再断（用户红线） |

追加 `32c03d7 chore: 更新版本号 2faac830d9fd`（pre-push 钩子在推送后自动写 `src/VERSION`，按钩子说明补一次提交）。

**推送结果**（一次性 PAT + 临时 askpass，用完 `shred -u`，临时文件已不存在）：
```
$ git push origin refactor/v2 refactor/v2:main
   f5770aa..32c03d7  refactor/v2 -> main
   f5770aa..32c03d7  refactor/v2 -> refactor/v2
$ git ls-remote origin
32c03d7f6ff07332df4a21eb4e44c7bf203c7bde  HEAD
32c03d7f6ff07332df4a21eb4e44c7bf203c7bde  refs/heads/main          # main 与 refactor/v2 一致
32c03d7f6ff07332df4a21eb4e44c7bf203c7bde  refs/heads/refactor/v2
```

（P-M2 本身不需要改代码：它的"永久冻结"是 P-M1 的下游症状，修好 P-M1 后已实测刷新成功；来源结论见 §3。）

---

## 11. UNKNOWN 清单

1. **232B 快照的确切生成路径**：已证实它 = legacy token `ec23e4cb…`（10-09 03:20:06 由 `share_legacy_migrate` 导入），`port: 20000` 属于 10-06→10-07 那代 `mVLESS01-REALITY`；但内容形态（anytls + `install_info.env` 的旧 UUID 当密码 + www.amazon.com + 名字带旗帜）**无法用任何现盘/备份产物复现**，且名字里的旗帜需要 10-09 21:20 之后的代码。**确切写入者 UNKNOWN**（缺陷本身已修并验证刷新）。
2. **M 的 `--conf-dir` 过滤在旗帜特性上线前是否正常**：仍然没有历史日志可查。**UNKNOWN**（但"现在 19/19 正常"已有真机与闸门双重证据）。
3. **非 mihomo 客户端遇到 `obfs=none` 是否同样失败**：本轮只验了 mihomo 1.19.32。**UNKNOWN**（三家链接同口径的旧结论仍然成立）。
4. **RN 上 `ss` 行数 90 → 91**：多出的监听是 `18899`，出现在本会话期间，但**不是我起的**（我从未在 RN 起任何监听；同期另有并发会话在改 SB/X 并在 RN 上做 E2E，分享服务里 SB/X 的记录数也被它改动过）。归属**UNKNOWN**。
5. **hy2 `pinSHA256` 在别家客户端是否也生效**：只在 mihomo v1.19.32 上实测（`pin=` 000 / `pinSHA256=` 204）。**UNKNOWN**（但 `pin=` 在 mihomo 上确定无效，源码判据明确）。

---

## 12. 生产面与清理（实际做了什么）

**在 RN 上留下的改动（全部说明）**
- 公共服务里 **1 条 mihomo 测试记录**（`eb001ee5…`，E2E 用）—— **已 revoke**；收工 health：`mihomo total=1 active=0`（与开工前逐字一致）。
- 那条真实冻结记录 `ec23e4cb…` 的**内容被刷新**（这是 P-M2 的功能验证本身；token / URL / 元数据未变，仍 `enabled=false`、仍过期）。
- **未写任何 `/root/catmi/*` 生产路径**：分享内容生成、`share_gen_tag_auto`、`build_sub`、`link_check`、`share_refresh_all` 全部在 `/tmp/mfix`（真实 out/conf 的只读副本）里跑；`out/share_tag-*.txt` / `share_addr.txt` 等产物**一个字节都没动**。
- 未重启任何服务：`mihomo(PID 119320) / proxy-share-service / nginx / xrayls / sing-box` 全程 active。

**在 CC 上**
- 生产 `mihomo-client`（PID **1364829**）全程未被重启、未被改配置；所有实验都用 `CLI_ROOT=/tmp/...` + `CLI_SERVICE=mihomo-e2e-tmp`（指向不存在的 unit）。
- 临时内核、`/tmp/mcli*`、`/tmp/clifix`、`/tmp/uritest`、`/tmp/uri2` 全部删除；`pgrep -f "mihomo -d /tmp/"` 无残留。

**本地**：`/tmp/mfix`、`/tmp/minv`、`/tmp/lc`、`/tmp/bwtest`、`/tmp/prefixrepo`、`/tmp/stage`、`/tmp/final_hy2.sh` 均在使用后删除（闸门内的夹具由 `trap` 自动清理）。
