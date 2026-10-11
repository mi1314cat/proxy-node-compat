# 跨内核端到端验收：3 服务端 × 3 客户端 九宫格

> 验收方式（用户点名）：把 RN 上 **X / M / SB 三个服务端**产出的**分享链接**，分别喂给 CC 上**三个内核的客户端**
> （X 客户端 = xbd/Xray，M 客户端 = mihomo 官方，SB 客户端 = sing-box / sb-client），逐格记录
> **解析成功？导入几个节点？真连得上吗？**，并把不通的格子**归因到服务端还是客户端**。
>
> 测试时间：2026-10-10 23:08–23:28（CC CST / RN PDT 08:08–08:28）
> 证据原始件：`research/e2e/evidence/3x3/`（logs/ 与 payloads/，从 CC `/tmp/e2e-3x3` 打包拉回，原始目录已清理）

---

## 0. 可复现性锚点：三个仓库 HEAD + 部署侧哈希

**⚠ 本轮测试期间另有 agent 正在改这三个仓库**（HEAD 在测试窗口内移动过），所以同时记录**开测时**与**收测时**两个值。

### 仓库 HEAD（本地工作区 `/root/deepseek/repos/`）

| 仓库 | 开测时 HEAD | 收测时 HEAD | 备注 |
|---|---|---|---|
| `xray--core`（X） | `568c8f7` fix(客户端): hy2 带宽/端口跳跃在"解析"和"生成"两跳都丢 | `cf810be` test(门禁): 两个新断言组不许"生成器崩了就静默全绿" | 窗口内被推进 2 个提交 |
| `mihomo--core`（M） | `f5770aa` chore: 更新版本号 55acb0c7c1db | `d794a33` fix(分享): 链接里不再写 obfs=none —— 一条坏节点会把整条订阅打成 0 (P-5) | 窗口内推进 2 个提交（中间态 `e3d4888`）；仍有 5 个未提交改动 |
| `sing-box-core`（SB） | `c0a5c19` 修: 切换产物地址族只替换本机 IP | `c0a5c19`（未动） | 工作区有未提交改动：`src/conf/hysteria2.sh`（obfs 修复）、`src/client/to_sb.py`、`src/client/client.sh`、`src/conf/lib.sh`、`install.sh` |

```bash
git -C /root/deepseek/repos/xray--core      log --oneline -1   # 收测时 cf810be
git -C /root/deepseek/repos/mihomo--core    log --oneline -1   # 收测时 d794a33
git -C /root/deepseek/repos/sing-box-core   log --oneline -1   # 收测时 c0a5c19
```

### 部署侧（RN `/root/catmi/*`，三个目录本身都不是 git 仓库，用哈希对齐仓库版本）

| 部署文件 | sha256 前 16 | 等于哪个版本 | 结论 |
|---|---|---|---|
| `/root/catmi/mihomo/src/share/build_sub.py` | `7ce57bd1f661e1c8` | = 开测时 mihomo HEAD 内容 | **P-M1 过滤器缺陷仍在部署里**（见 §3.2 复测） |
| `/root/catmi/mihomo/src/share/share.sh` | `9b24796b8ea6a9b9` | = 仓库 HEAD 内容 | — |
| `/root/catmi/sing-box/conf/hysteria2.sh` | `ca21a6e59e2d89d3` | = `sing-box-core` **HEAD** 内容（`git show HEAD:src/conf/hysteria2.sh` 同哈希） | **obfs=none 修复只在工作区（`d1876626`），未部署** |
| `/root/catmi/sing-box/conf/share.sh` | `6d492039b7e968f2` | = 仓库 HEAD 内容 | — |

```bash
# 部署版 build_sub.py 现在再跑一次（只读，输出到 /tmp）
python3 /root/catmi/mihomo/src/share/build_sub.py --out-dir /root/catmi/mihomo/out \
        --conf-dir /root/catmi/mihomo/conf --tag all > /tmp/verify-m.out 2>/tmp/verify-m.err
# exit=1
# stderr: [清理] 剔除了 19 个陈旧产物 (节点已删除, 但 out/ 里旧文件还在)
#         [ERR] 没有任何可用节点 (out/*_client-*.yaml 为空?)
# stdout: 0 字节
```

> **先回答前提问题："服务端修复是否已落地？"**
> **没有。** M 的生产分享生成路径（部署版 `build_sub.py` + `--conf-dir` 过滤器）在收测时刻（23:27）**仍然 100% 失败**；
> SB 的 `obfs=none` 修复**尚在工作区、未部署**（部署文件哈希 = 未修的 HEAD 版本）。
> 因此 M 行、以及 SB 的"链接（非 JSON）"路径，测到的都是**未修状态**。

---

## 1. 三家的"真实分享地址"（怎么找到的）

分享的存储/生命周期统一归 RN 上的公共基础服务 **`proxy-share-service`**（`:9443`，`SHARE_DATA_DIR=/var/lib/proxy-share-service`）。
列表接口要 admin token（`/etc/proxy-share-service/admin.token`，仅回环可调）：

```bash
# RN 上（回环）
T=$(cat /etc/proxy-share-service/admin.token)
curl -s -H "Authorization: Bearer $T" "http://127.0.0.1:9443/api/v1/shares?provider=xray"
```

| 服务端 | 真实分享地址 | 状态 | 载荷 |
|---|---|---|---|
| **X** | `http://107.173.154.178:9443/share/f64f61ce35e42b39a5f928d1c6d15ae5` | `active`（本次全程可用） | 944 B，**base64 订阅**，5 条 URI（hysteria-04 / SS2022-02 / TROJAN-03 / vless-xhttp07 / vless-xhttp08） |
| **M** | 生产路径**产不出**新链接。现存唯一 M 记录 `…/share/ec23e4cb8196d688053de91240e52dae` | **HTTP 410**（`disabled`/过期，226 B 陈旧快照，指向无人监听的 `:20000`） | — |
| **M（旁路产物）** | `http://107.173.154.178:9443/share/eb001ee58ab65d3d7314a23c9a23740a`（测试期间由**另一个 agent 的修复验证**创建，非部署路径产出，见 §5-②） | `active`，`max_uses=0`，6312 B / 19 节点 / sha256 `08d847fe…` | mihomo YAML（`proxies:`） |
| **SB** | `http://107.173.154.178:9443/share/f49c679133cef191f4a07dba1fc7fbdd`（tag=all，7360 B，16 outbounds）<br>`http://107.173.154.178:9443/share/e38af5d872437814ee0b2421f1f60931`（tag=hysteria201-TLS，401 B，1 outbound） | 测试期间 `active`；**测后已按纪律删除**（见 §7） | sing-box 配置 JSON（`outbounds:`） |

SB 两条分享的创建方式（与 `conf/share.sh create` 完全同路径，只是不写 `out/share_tag-*.txt` 那个生产文件）：

```bash
cp /root/catmi/sing-box/out/sb_client-all.json /tmp/e2e-sb-all.json
python3 /root/catmi/sing-box/conf/share_client.py create --type node \
   --content-file /tmp/e2e-sb-all.json --ttl 10800 --max-uses 0 --meta '{"tag":"e2e3x3-all"}'
# -> token f49c679133cef191f4a07dba1fc7fbdd  bytes=7360 state=active
```

---

## 2. 九宫格结论（核心）

判定口径：**解析** = 客户端能否把该链接变成"有意义的节点"（不是空壳/空 provider）；
**导入** = 落盘/进 provider 的节点数；**真连** = 用该客户端自己的内核实例发真实请求（`generate_204` + `api.ipify.org` 出口 IP）。

| 服务端 ↓ / 客户端 → | **X 客户端（xbd / Xray）** | **M 客户端（mihomo）** | **SB 客户端（sing-box / sb-client）** |
|---|---|---|---|
| **X 分享**（base64，5 节点） | ⚠️ **部分可用**：解析 5 → 导入 **4**（TROJAN-03 被静默丢弃）；真连 ✅ SS2022-02 `204 / 0.43s / 出口 104.28.195.192`、❌ hysteria-04（503/tls）、❌ vless-xhttp07/08（"需浏览器"）；**hy2+xhttp08 改对 SNI 后立刻 ✅204** ⇒ **服务端载荷缺陷** | ✅ **可用**：provider **5 节点**，`mihomo -t` 通过；真连 ✅ SS2022-02 `204 / 0.41s / 出口 104.28.195.192`；默认（hy2）❌ `x509: cannot validate certificate for 107.173.154.178` ⇒ 同一**服务端载荷缺陷** | ✅ **可用且最全**：自带转换器 `共=5 成功=5`，`sing-box check rc=0`，7 出站；真连 ✅ SS2022-02 `204 / 0.40s / 出口 104.28.195.192`；默认 hy2 ❌ 同一 x509 错 |
| **M 分享**（mihomo YAML，19 节点） | ❌ **0/19 导入**：`✓ 解析出 19 个节点` / `✓ 已导入 0 个节点`；19 条全是**空壳**（`name=node, address=""`）⇒ **客户端缺陷** | ✅ **本行最佳**：provider **19 节点**；真连 **14/19** ✅（509–2710 ms），curl `204 / 0.21s / 出口 104.28.201.80`；5 条 CDN 节点 `delay=0` ❌ | ❌ **转换器崩溃、0 导入**：`NameError: name '_note' is not defined`（`to_sb.py:567`）⇒ **客户端缺陷**（触发源是服务端脏值，见 §5-④） |
| **SB 分享**（sing-box JSON，16 出站） | ❌ **解析不出节点**：`✗ 订阅里没有解析出节点` ⇒ **客户端缺陷**（xbd 不认 sing-box JSON） | ❌ **provider 0 节点**：`initial proxy provider prov error: file must have a `proxies` field`；⚠️ 但 `mihomo -t` 仍打印 *test is successful*（**假绿灯**）；此格的 `204` 是**直连兜底假阳性**（CC 直连 gstatic 本身就 `204/0.056s`）⇒ 跨生态格式不兼容 | ✅ **可用**：真实 CLI `sb-client add <url>` → `分享配置已获取` + `已导入 13 个节点`；`sb-client check` → `配置检查通过`；隔离实例 18 出站，真连 ✅ `rn-reality01-REALITY 204 / 1.22s / 出口 104.28.201.80`；单节点 hy2 分享也 ✅ `204 / 1.06s` |

**一眼结论**：**只有"同生态"三格全通**（X→X、M→M、SB→SB 各自都有真连证据）；
**跨生态 6 格里 5 格不通**（X→xbd 是"部分可用"，因为它至少认 base64 订阅），
其中 **2 格是纯客户端缺陷**（M→xbd、SB→xbd）、**1 格是客户端缺陷+服务端脏值**（M→SB）、
**1 格是格式不兼容**（SB→mihomo）、**1 格是服务端载荷缺陷**（X→mihomo 的 hy2 节点，见 §5-①）。

---

## 3. 每格关键原文（命令 + 输出）

### 3.1 X 分享 → 三家客户端

**分享载荷（真实链接拉下来的原文）**
```
hysteria2://05615ce2-...@107.173.154.178:29604?sni=107.173.154.178&insecure=0#hysteria-04
ss://MjAyMi1ibGFrZTMt...@107.173.154.178:29603#SS2022-02
trojan://LV7CpzX9Jc8vWuhP0YV0@107.173.154.178:29602?security=reality&type=tcp&sni=audio-ssl.itunes.apple.com&fp=chrome&sid=b860a9f0&pbk=GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU#TROJAN-03
vless://1fa7c981-...@107.173.154.178:8443?encryption=none&security=tls&type=xhttp&path=%2FaVCR3P0A%2F#vless-xhttp07
vless://278502fc-...@107.173.154.178:29601?encryption=none&security=tls&type=ws&path=%2F8KLD3cNj#vless-xhttp08
```

**① X → xbd**
```
$ xbd node sub "http://107.173.154.178:9443/share/f64f61ce35e42b39a5f928d1c6d15ae5"
==> 下载订阅
✓ 解析出 5 个节点
✓ 已导入 4 个节点
# /tmp/.xbd_skipped.json: TROJAN-03 | Xray 内核不支持该协议（trojan）
```
丢弃原因（直接查解析产物，`node.py subscription`）：
```json
{"name":"TROJAN-03","protocol":"trojan","security":"reality","sni":"audio-ssl.itunes.apple.com",
 "reality_public_key":"","reality_short_id":"",
 "raw_params":{"sid":"b860a9f0","pbk":"GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU"}}
# -> can_use_xray: False  ⇒ 被当"内核不支持"丢掉
```
真连（隔离实例：xbd 自己的节点 JSON + `lib/genconfig.py` + `bin/xray`）：
```
node-001-ss2022-02.json   generate_204: http=204 time=0.431503s | ipify: 104.28.195.192 | ip=104.28.195.192 loc=US
node-001-hysteria-04.json generate_204: http=503 time=0.503222s | ipify: http=000
node-001-vless-xhttp08.json 同 503；xbd 自带 latency 对 07/08 报"需浏览器…测速不适用"
```

**② X → mihomo（M 客户端）**
```
configuration file .../config.yaml test is successful
provider prov vehicleType File nodes 5
-- 切换 PROXY -> SS2022-02 [http=204]
generate_204: http=204 time=0.407840s | ipify: 200 | 出口 104.28.195.192
# 默认节点(hy2)时：
level=warning msg="... error: CRYPTO_ERROR 0x12a (local): tls: failed to verify certificate:
  x509: cannot validate certificate for 107.173.154.178 because it doesn't contain any IP SANs"
```

**③ X → sing-box（SB 客户端）**
```
[to_sb] 格式=share-uri 共=5 成功=5 跳过=0        # 比 xbd 多收了 TROJAN-03
sing-box check rc=0 ; 出站数: 7 ['GLOBAL','e2e-hysteria-04','e2e-SS2022-02','e2e-TROJAN-03','e2e-vless-xhttp07','e2e-vless-xhttp08','direct']
# 默认(hy2)：ERROR connection: open connection ... using outbound/hysteria2[e2e-hysteria-04]:
#   INTERNAL_ERROR (local): tls: failed to verify certificate: x509: cannot validate certificate for 107.173.154.178 ...
# 选定 e2e-SS2022-02：generate_204: http=204 time=0.403856s | 出口 104.28.195.192
```

**SNI 归因实验（决定性）**：把 /tmp 里的节点副本 `sni` 改成服务端 per-node 链接产物里的真实域名后重测 ——
```
服务端 per-node 产物 out/hy2_share-04.txt  : hysteria2://...?sni=moontv.6896698.xyz&insecure=0&alpn=h3&upmbps=50&downmbps=200
分享订阅里的同一条                          : hysteria2://...?sni=107.173.154.178&insecure=0            ← SNI 被写成 IP，且丢 alpn/带宽
生成出的客户端配置                          : "tlsSettings":{"serverName":"107.173.154.178"}
改 sni=moontv.6896698.xyz 后：hy2 → 204/1.33s/104.28.195.192 ✅ ; vless-xhttp08 → 204/3.03s ✅ ; vless-xhttp07 → 仍 503 ❌(见 UNKNOWN)
```
> 同一格的服务端产物还互相矛盾：per-node 链接有 `sni=` 与 `ech=`，订阅载荷里 **sni 缺失/被替换成 IP、ech 整段丢失**
> （vless-xhttp07 的 per-node 产物是 `moontv.6896698.xyz:443` + `ech=cloudflare-ech.com+https://dns.alidns.com/dns-query`，订阅里变成 `107.173.154.178:8443` 且无 sni/ech）。

### 3.2 M 分享 → 三家客户端

**先证明"生产路径产出的是什么"**（开测与收测各跑一次，见 §0）：`exit=1 / [ERR] 没有任何可用节点`；
**根因**（读 `out/*_client-*.yaml` 与 `.managed.json` 比对，交集 0）：
```
.managed.json                       : ["mAnyTLS01-TLS", ...]                       # 裸名 19 条
out/anytls_anytls_client-01.yaml    : - name: 🇺🇸 mAnyTLS01-TLS                     # 带旗帜 19 条
live_node_names() 用裸名等值匹配带旗帜名 → intersection: 0 / 19
```
**测试用的 M 载荷**：真实旁路链接 `eb001ee5…`（从 CC 直接拉）——
```
curl http://107.173.154.178:9443/share/eb001ee58ab65d3d7314a23c9a23740a
# http=200 bytes=6312  sha256=08d847fe84a274b05593ed08502e1b2c4fd50162c67276cf1d47eb04fd5fc88a（与服务端 content_sha256 一致）
# grep -c "^- name:" -> 19
```

**① M → xbd**
```
$ xbd node sub "http://107.173.154.178:9443/share/eb001ee5…"
✓ 解析出 19 个节点
✓ 已导入 0 个节点
# 跳过原因（19/19）：anytls×3 / hysteria2×2 / vless×8 / trojan×5 / tuic×1 —— 全部 "Xray 内核不支持该协议（…）"
```
解析产物是**空壳**（`node.py subscription` 对 mihomo YAML 的输出）：
```json
{"name":"node","protocol":"anytls","address":"","port":443,"password":"","sni":"","security":"none", ...}
# 名字集合: {'node'}  |  address 非空数: 0 / 19
```

**② M → mihomo（自家）**
```
test is successful ; provider prov vehicleType File nodes 19
[probe] 真实可用 14/19
  OK   623 ms mAnyTLS01-TLS / 621 ms mHysteria202-TLS / 705 ms mVLESS01-REALITY / 392 ms mTUIC01-TLS ...
  FAIL       mTrojan05-CDN-gRPC / mTrojan04-CDN-WS / mVLESS05-CDN-gRPC / mVLESS04-CDN-WS / mVLESS03-TLS-XHTTP-CDN  (delay=0)
generate_204: http=204 time=0.211915s | ipify: 200 | 出口 104.28.201.80
```

**③ M → sing-box（SB 客户端）**
```
$ python3 /opt/sb-client/share-state/to_sb.py p-m-real.yaml --prefix e2e --format json
rc=1, stdout 0 字节
Traceback (most recent call last):
  File "/opt/sb-client/share-state/to_sb.py", line 567, in _from_clash_list
    _note("不支持的 clash type: %s" % (d.get("type") if isinstance(d, dict) else "?"))
    ^^^^^
NameError: name '_note' is not defined
```
触发它的那一条（逐条调 `clash_to_outbound` 定位）：
```
坏条目: [('🇺🇸 mHysteria202-TLS', 'hysteria2', "ValueError:invalid literal for int() with base 10: '50 Mbps'")]
```
对照实验（只剔掉这一条节点）：`[to_sb] 格式=mihomo-yaml 共=18 成功=18 跳过=0` —— 即**一条脏值 = 整批归零**。

### 3.3 SB 分享 → 三家客户端

**分享载荷**：`{"outbounds":[16 条]}`（anytls×2 / hysteria2 / naive / vless / shadowsocks×2 / shadowtls / trojan×2 / tuic / vmess×2 / selector / urltest）。

**① SB → xbd**
```
$ xbd node sub "http://107.173.154.178:9443/share/f49c679133cef191f4a07dba1fc7fbdd"
==> 下载订阅
✗ 订阅里没有解析出节点
```

**② SB → mihomo**
```
test is successful                       ← ⚠️ 假绿灯
provider prov vehicleType File nodes 0
level=error msg="initial proxy provider prov error: file must have a `proxies` field"
-- 本格 curl 的 204 是直连兜底，不是走节点：
direct generate_204: http=204 time=0.055642s     ← CC 直连 gstatic 本身就 204
```

**③ SB → sing-box（自家，真实 CLI）**
```
$ SB_SUBS_PREFIX=e2e sb-client add "http://107.173.154.178:9443/share/f49c679133cef191f4a07dba1fc7fbdd"
[OK]   分享配置已获取
[OK]   已导入 13 个节点 (单个链接全量分享); 现 59 个可用节点
[SB-Client] 前缀「rn」已有订阅记录, 已更新其链接 (不重复登记)
$ sb-client check
[OK]   配置检查通过
# 隔离实例（同一内核 core/sing-box + 同载荷）：check rc=0，18 出站
# SB_FINAL=rn-reality01-REALITY → generate_204: http=204 time=1.221530s | ipify 200 | 出口 104.28.201.80
# 单节点 hy2 分享(SB_FINAL=hysteria201-TLS) → check rc=0 | generate_204: http=204 time=1.061670s
```

### 3.4 附：`obfs=none` 跨内核矩阵（用户点名的 SB/M 待查项）

载荷：M 的 `out/hysteria2_share-01.txt`（`…&obfs=none#🇺🇸 HY2-01`）、SB 的 `out/sb_links-all.txt` 里那条
（`…&obfs=none&obfs-password=&alpn=h3#🇺🇸 rn hysteria201-TLS`），以及去掉 obfs 参数的对照。

| 消费方 | M 的 `obfs=none` 链接 | SB 的 `obfs=none&obfs-password=` 链接 | 对照（不写 obfs） |
|---|---|---|---|
| **mihomo（M 客户端）** | ❌ provider **0 节点**：`initial proxy provider prov error: proxy 0 error: missing obfs password` | ❌ 同错，**0 节点** | ✅ 1 节点 |
| **sing-box（SB 客户端 to_sb.py）** | ✅ `共=1 成功=1` —— 参数被**静默丢弃**（转换产物里没有 obfs 字段） | ✅ 同 | ✅ |
| **Xray（xbd node.py）** | ✅ 解析 1 个节点，`extra=''`（obfs 无处安放，静默丢） | ✅ 同 | ✅ |

> 结论：**`obfs=none` 只对 mihomo 是硬失败，而且一条就够把整条 provider 打成 0 节点**；
> sing-box/Xray 侧是**静默忽略**（对 `mask=none` 无影响，但对真正启用 obfs 的节点会**静默丢掉混淆**）。
> SB 的 JSON 分享载荷里 obfs 是被正确删掉的（`sb_client-hysteria201-TLS.json` 无 obfs 段），**受害的是"链接"产物**。

---

## 4. 归因表（哪一格不通，是服务端的锅还是客户端的锅）

| 格 | 结论 | 归因 | 依据 |
|---|---|---|---|
| X → xbd | 部分可用（4/5 导入，1/5 真连不通） | **服务端载荷缺陷**（IP 当 SNI / 丢 ECH）+ **客户端缺陷**（丢 trojan pbk/sid） | SNI 修正后 hy2/xhttp08 立刻 204；TROJAN-03 `reality_public_key=""` 而 `raw_params.pbk` 有值 |
| X → mihomo | 可用（5 节点，可连） | 同一**服务端载荷缺陷**只影响 hy2 那条 | `x509 … doesn't contain any IP SANs`（serverName=IP） |
| X → SB | 可用（5/5 转换，可连） | 同上 | 同上 |
| M → xbd | **不通** | **客户端缺陷**（xbd 的订阅解析器对 mihomo YAML 产出 19 个空壳 + 过滤理由文案误导） | 解析产物 `address:"" ×19`；服务端内容在 mihomo 侧 14/19 可连 |
| M → mihomo | 可用（19 节点，14/19 可连） | 5 条 CDN 节点不可连：**服务端产物问题**（未深查，见 UNKNOWN-2） | `delay=0` 全落在 CDN 类节点 |
| M → SB | **不通（0 导入）** | **两侧都有份**：服务端写脏值 `up: 50 Mbps`（非整数）+ 客户端 `to_sb.py` 用未定义的 `_note` 把整批炸掉 | 剔掉那一条即 18/18 成功 |
| SB → xbd | **不通** | **客户端缺陷**（不认 sing-box JSON，也不做格式探测/转换） | `✗ 订阅里没有解析出节点` |
| SB → mihomo | **不通** | **跨生态格式不兼容（客户端）**：mihomo 的 provider 只认 `proxies:`（Clash YAML / base64 URI），不认 sing-box `outbounds:` | `file must have a `proxies` field`，provider 0 节点 |
| SB → SB | 可用 | — | add 13 节点 + check 通过 + 204/1.22s |

---

## 5. 已确认的问题清单（按严重度）

**① [严重·服务端 X] 分享订阅载荷丢 SNI/ECH，5 条里 3 条连不上（三家客户端同时中招）**
`conf/share.sh` 生成的订阅载荷与 per-node 链接产物**不一致**：hy2 的 `sni` 被写成节点 IP、`alpn`/带宽丢失；
vless-xhttp07/08 的 `sni` 与 `ech` 整段缺失（per-node 产物里都有）。
证据：`tlsSettings.serverName="107.173.154.178"` → mihomo/sing-box 双双报 `x509 … no IP SANs`；
把 SNI 改回 `moontv.6896698.xyz` 后 hy2 与 vless-xhttp08 **立刻 204**。
**影响**：X 的"分享给用户"这条路，用户拿到的 5 个节点里 3 个是坏的（X 自己客户端也一样坏）。

**② [严重·服务端 M] 生产分享路径仍然 100% 失败（P-M1 未落地）**
部署版 `build_sub.py`（`7ce57bd1f661e1c8`）收测时刻仍 `exit=1 [ERR] 没有任何可用节点`；
`share_create` 走的就是这条（`--conf-dir` 过滤），所以面板"生成分享内容失败"照旧。
线上那条可用的 `eb001ee5…`（19 节点/6312 B/sha `08d847fe`）**内容 = 绕过过滤器的产物**（与我用
`--out-dir … --tag all`（不带 `--conf-dir`）生成的字节完全一致），说明它**不是部署路径产出的**，
而是本次修复验证过程中由旁路（临时副本/直接 API）创建。**不要把"库里有链接了"当成 P-M1 已修**。

**③ [严重·客户端 SB] `to_sb.py` 的 `_note` 未定义：一条坏条目炸掉整批导入**
`/opt/sb-client/share-state/to_sb.py:567` 调用了一个**定义在别处局部作用域**的 `_note`（定义在 486 行），
异常被 `except Exception: o = None` 吞掉后进入该分支 → `NameError` 直接终止进程（rc=1、输出 0 字节）。
**影响**：只要 mihomo 订阅里有一条转换器处理不了的节点，**整条订阅 0 导入**（而非跳过它）。
（`sing-box-core` 工作区已在改 `src/client/to_sb.py`，但 CC 上部署的客户端仍是坏的。）

**④ [中·服务端 M] hysteria2 客户端产物写脏值 + 字段语义错位**
`out/hysteria2_hysteria2_client-01.yaml` 的 `up: "30" / down: "200"` 正常，但 `mHysteria202-TLS` 是
`up: 50 Mbps / down: 200 Mbps`（**带单位、非整数**）—— 这就是 ③ 的触发源；同一条还把自签节点的
证书 sha256 塞进了 `fingerprint:` 字段（mihomo 里 `fingerprint` 是 uTLS 指纹名，不是证书哈希）。

**⑤ [中·生态共有] 硬编码 `obfs=none`**
mihomo 报 `proxy 0 error: missing obfs password` 并把 **provider 打成 0 节点**（M 链接、SB 链接都复现；
对照组 1 节点正常）。SB 部署版 `hysteria2.sh` 仍是含该参数的版本（`ca21a6e5…` = 未修的 HEAD），
修复只在工作区；M 仓库刚提交了 P-5 修复（`d794a33`）但 `out/*_share-*.txt` 存量产物仍带 `obfs=none`。
X 侧（`hy2_share-04.txt` 无 obfs 参数）已修，与既往记录一致。

**⑥ [中·客户端 X] xbd 对 mihomo YAML 静默产出空壳节点**
`✓ 解析出 19 个节点 / ✓ 已导入 0 个节点`：解析器把每个 proxy 变成 `{name:"node", address:""}`，
再被"unsupported"过滤掉；而且部署版给出的是**误导性理由**（"Xray 内核不支持该协议（trojan/vless）"，
实际 Xray 原生支持这些协议）。部署版 `compat.py` 里**没有** `blocking_reason`（仓库 HEAD 有）。

**⑦ [中·客户端 X] xbd 丢 trojan+REALITY 的 `pbk`/`sid`**
解析产物 `reality_public_key=""`、`reality_short_id=""`，而 `raw_params` 里 `pbk`/`sid` 齐全 →
`can_use_xray: False` → TROJAN-03 被弃。部署版客户端 lib 落后仓库：
`node.py 6be89561… vs 仓库 HEAD 5ea56a69…`、`compat.py c71d4a13… vs 08b1eba5…`、`nodefilter.py a25d240a… vs 44001bf7…`。

**⑧ [低·工具判据] `mihomo -t` 不校验 provider 内容，"绿灯"会骗人**
SB JSON → `test is successful`，但运行时 `provider 0 节点`。**别把 `-t` 当成导入成功**（本报告所有 M 格都用
运行时 Clash API `/providers/proxies` 复核节点数）。

**⑨ [低·工具判据] `sing-box check` 的盲区**
`check rc=0` 但 `route.final` 指向不存在的 tag，运行期才 `FATAL start service: default outbound not found: …`
（我的隔离实例踩到；说明 check 通过 ≠ 配置可用）。

**⑩ [低·测量口径] CC 的"204"不能单独当成功判据**
CC 直连 `http://www.gstatic.com/generate_204` 本身就返回 `204 / 0.056s`（本机路径有拦截/透明代理）。
本报告所有真连结论都以**出口 IP**（`api.ipify.org` / `cloudflare/cdn-cgi/trace`）为准，SB→mihomo 那格的
`204` 已被识别为**直连兜底假阳性**。

---

## 6. UNKNOWN（没测到/没定论的，一律不猜）

1. **X 订阅载荷为何与 per-node 产物不一致**：是 `share_payload.py` 读 conf 片段时只拿到了 listen IP，
   还是生成时被"地址族/域名"逻辑覆盖 —— 未读代码定论（只证明了现象与影响）。
2. **`vless-xhttp07` 修正 SNI 后仍 503**：per-node 产物走的是 `moontv.6896698.xyz:443` + `ech=cloudflare-ech.com+…`，
   订阅里是 `107.173.154.178:8443` 且无 ECH —— 是"必须带 ECH"，还是该 CDN 路径本身已废，**未定论**。
3. **M 的 5 条 CDN 节点全部 `delay=0`**：是产物陈旧（端口/目标过期）还是 CDN 侧问题，未深查（`ss -ltnp` 只看了 X 的端口）。
4. **`eb001ee5…` 这条 M 链接的确切创建方式**：只证明了"不是部署路径产出"（部署版仍 exit=1、内容=绕过过滤器的字节）。
5. **SB 转换器静默丢弃 obfs 参数的影响面**：当前 SB 无非 `none` 的 obfs 节点，故"真启用 obfs 时会连不上"**未实测**。
6. **CC 上 xbd 部署版本对应的确切发布/commit**：只知它落后仓库 HEAD（缺 `blocking_reason`、`node.py` 哈希不同），
   `VERSION=2.8.3` 但发布物与仓库 HEAD 的对应关系未查。
7. **CC 直连为何对 gstatic 返回 204**（本机是否有透明代理/拦截）：未查，仅作为测量口径的注意事项。

---

## 7. 纪律执行记录（可核查）

- **未写任何生产配置**：没有改 `/root/catmi/*`（节点 conf/产物一律只读）、没有改 RN/CC 任何正式配置文件。
  唯一"写"是公共服务 `proxy-share-service` 自有的分享记录目录 `/var/lib/proxy-share-service`（其运行时数据），
  且**测完即删**（见下）。
- **未重启任何生产服务**：RN 上的 `xrayls` / `mihomo` / `sing-box` / `proxy-share-service`、CC 上的 xray / mihomo / sing-box
  **全程没有被重启**（收测时三个客户端进程仍在跑：xray PID 968528、mihomo PID 1364829、sing-box PID 1444214）。
  客户端侧的真连实测一律用**隔离临时实例**（xbd 自带 `genconfig.py`+`bin/xray`；`mihomo -d /tmp/…`；`sing-box -D /tmp/…`），
  端口先 `ss` 确认空闲、确认监听者是自己的进程，避免误测到别人起的代理。
- **CC 导入后已恢复原状（哈希校验）**：
  - xbd：导入 4 个节点 → 全部删除 + 用基线 tar 覆盖；`nodes/` 目录 sha256 `f7987a81…` **等于基线**；`current` 仍指向 `node-001-ccsmhysteria2-01.json`。
  - sb-client：`sb-client add` 更新了 13 个节点文件/`90-outbounds.json`/`subscriptions.json` → 全部还原；
    `90-outbounds.json` sha256 `751c84c3d7db3e07…` **等于基线**，`subscriptions.json` 与基线 `diff` 为空，`sb-client list` 回到 **59** 个节点。
  - mihomo 客户端（`/root/catmi/mihomo-client/conf`）**未被写入**，只做只读读取。
- **临时文件已清理**：CC `/tmp/e2e-3x3`（含基线 tar 与全部日志）已删除、无残留进程；
  RN `/tmp/m-*`、`/tmp/e2e-sb-*.json` 已删除；本地 `/tmp/e2e-stage` 已清理。
  证据件已拉回仓库：`research/e2e/evidence/3x3/e2e-evidence.tgz`（解包为 `logs/`、`payloads/`）。
- **分享记录回收**：测试用的两条 SB 分享已 `DELETE`（`share_client.py delete --token …`）→
  `provider=sing-box` 回到 **0 条**；`provider=xray` 仍 1 条（未动既有 `f64f61ce…`）；
  `provider=mihomo` 剩 2 条（**均非我创建**：`ec23e4cb…` 原有的 disabled + `eb001ee5…` 另一个 agent 的）。
- **未 push 任何仓库**，未提交任何改动。
