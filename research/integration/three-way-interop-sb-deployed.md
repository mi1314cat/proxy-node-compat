# SB 列 · 服务端分享产物 + CC 客户端 更新到已部署代码：实施与真机验收

- 仓库：`/root/deepseek/repos/sing-box-core`，分支 `main`，起点 `a7150e2`，终点 **`b25f5a0`**（本地 10 个 commit，**未 push**）
- 机器：`rn` 107.173.154.178（测试服务端，SB 列可改）／`CC` 192.168.1.178（客户端）／`ds` **全程未触碰**
- 本轮核心结论：**服务端"声明 + 两条产品"这条链在真实部署机上原本 100% 不可用**（发布闸门每次必拒），已找到根因、修好、补门禁、真机跑通。同列验收 **13/13 真连 + 负对照全失败**。
- **收尾批（`ba1e670` + `e0ec3a1`）**：把两个"从来不红"的盲点做成了会红的门禁 —— 端口探活的全量误报（11/11 假告警 + 假绿）、对角线在非交互环境下的静默失败。`check_compat_wiring` 由 **32/0 走到 38/0**。
- **第三批（`6f59a0d` + `30944fa`）**：canonical 两轮脱敏同步（各只有 `rules.json` 一个文件），pin 同步前进；`38/0` 持平。
- **第四批（`e861ab7`）**：九宫格（SB 客户端 × X/M/SB 三个服务端）—— 见 **§9**。挖出并修掉两条「静默丢节点」缺陷（`anytls`/`socks5` 分派漏项、跳过理由被吞），门禁 **42/0**。
- **第五批（`b25f5a0`）**：声明缩短（去 `version` + 同源相对路径，**302→214 字节**）—— 见 **§10**。门禁 **49/0**。**尚未分发 RN**（按指示不重新部署）。

### 对外可用形态（当前）

`DECLARED_SHARE_URL`（`max_uses=0`，**永久**，13 节点全量）：

```
http://[2001:470:c:cf:bf47:d1e0:cd4d:c6db]:9443/share/ab03704acc0f2632201530d705660766?interop=1&kernel=sing-box&distribution=sing-box&version=1.14.2&formats=uri%2Csing-box&url-sing-box=http%3A%2F%2F%5B2001%3A470%3Ac%3Acf%3Abf47%3Ad1e0%3Acd4d%3Ac6db%5D%3A9443%2Fshare%2F8526f930c8305cddb148c127497b10d9
```

撤销：`ssh rn 'cd /root/catmi/sing-box && bash conf/share.sh del ab03704acc0f2632201530d705660766'`（会**连带**删掉原生记录）。

> 本条是**在部署态代码下重发的**（`grep` 出 RN `conf/share.sh` = `d31fc815…` 之后才执行 `create-all 0 0`），见 §5.5-③。

---

## 0 · 先摆事实：动手前的事实 vs 我出发时的假设

| 我被告知 / 以为的 | 只读侦察得到的**事实** | 证据 |
|---|---|---|
| RN SB 服务端代码是最新、可直接用 | `conf/` 35 个文件确实 == `a7150e2`，但 **`create-all` 直接 RC=1**（发布闸门永远拒绝发布） | §2.1 |
| RN 上有一条现成的聚合分享 | **0 条** —— `SHARE_PROVIDER` 三个命名空间里 `sing-box`=0、`xray`=1、`mihomo`=1，是真的空而不是命名空间遮罩 | `share.sh list` → "当前没有任何分享链接" |
| CC 的 `to_sb.py` "不一致，需要查清哪边新" | CC 的是 **`2c209b0`/`4fccbc6` 的 27579 字节版**（sha `b176f881…`），比仓库旧一档：**缺 `45fd108` 的三条实测修复** | §4.2 |
| CC 的 `client.sh` 只是"旧一点" | CC 的是 **`188c6a5`（2026-10-04）**，比 `a7150e2` 落后 **4 档**；`share-state/` 里**根本没有 `lib/`，也没有 `compat2.py`** | sha 逐档比对 |
| `out/sb_links-all.txt` 需要重新生成 | 它是各协议脚本 **append** 出来的旁路产物，`regen-aggregate` 不碰它；真正需重建的是 `sb_client-all.json`（重建结果与旧文件**逐字节相同** sha `3c3e63c4…`） | §2.2 |
| `interop-e2e.sh` 本地 exit=3 是"只验了服务端" | **不是**。那个 `exit 3` 发生在**任何验证之前**（`tools/interop-e2e.sh:60`），所以本地那次**什么都没验** | 代码 |
| hy2 带宽"形态"可能不对 | 产物 `up_mbps:100/down_mbps:500` 与**服务端 inbound 真实配置完全一致**；URI 里不写 up/down 正是 `hysteria2.sh:323` 的设计。`fe47df8` 改的是**新节点默认值**，不动已有节点 | §2.3 |

> 纪律上最要紧的一条：**`share.sh check all` 返回 0 不等于节点健康**。它这次一边 RC=0 一边对 **11/11 个非 loopback 节点**打出"服务端当前没有监听"——而那 11 条**全是误报**（§5.1）。

---

## 1 · 改了什么（文件 + 行级要点）

十个本地 commit：

```
b25f5a0 收束: 声明去掉 version + 同源取件地址写相对路径（302→214 字节, −88）
e861ab7 修(客户端): URI 路径的静默丢节点 —— anytls/socks5 分派漏项 + 跳过理由被吞
30944fa vendor: rules.json 前进到 692566c（脱敏归 canonical 自己管）
6f59a0d vendor: rules.json 前进到 40a9441（真机地址改 <CDN_IP> 占位符）
e0ec3a1 修(验证台): interop-e2e 给 ss 桩 —— 死端口升为拒发后, 拿别人语料跑会在第 2 段就死
ba1e670 修(分享+客户端): 端口探活的全量误报 + 对角线非交互静默失败（各补行为门禁）
f994b38 vendor: proxy_node_compat 前进到 c2343b6（注册表字段三分类 + 认不出就抛错）
d8b41c1 修(服务端): install.sh 把 compat2 + lib/proxy_node_compat 装进部署 conf/
6f23d65 加(门禁): 8b 段覆盖三形态 × 编码/未编码 —— 并把"换个位置判 ://"这条假修也钉死
5ed6206 修(互通): parse_declaration 判"完整地址"改看 scheme
```

### 1.0 收尾批 `ba1e670`（三处，含委托方点名的 ① ②）

**（a）`src/conf/share.sh:_sb_share_verify_file` —— 探活正则写错 + 死端口不拦发布 + `ss` 全瞎**

```diff
- grep -qE "[:]]${lport}$"                       # ERE: 字符类[:](只有冒号) + 字面 ]
+ grep -qE "[]:]${lport}$"                       # ] 或 : 任一个 → *:P / 0.0.0.0:P / [::]:P
- ... || print_warn "服务端当前没有监听 ..."      # 只告警 → check all RC=0
+ if ! ...; then print_error "服务端当前没有监听 ..."; bad=1; fi   # 升为拒发
```
后果不是漏报而是**全量误报**：真机实测 **11/11** 个非 loopback 节点全被判"没在听"，而它同时是 `create_share` 的**发布闸门** → 假绿 + 告警疲劳（真挂掉时告警长得一模一样）。

顺带修了一个我改 `bad=1` 时**自己引入又自己发现**的坑：`ss` 一条套接字都看不到时（容器/权限/netns/没有 ss），逐端口判死会把**每个**节点判死 → **全量拒发**。那不是发现死节点，是我们瞎了却假装看见。加 `ss_dim` 守卫：明确告警"探活跳过，这项本轮没验"并 fail-open，与既有的"配置目录为空就跳过"同一条原则。**这条不是纸上推演——跑门禁的这台机器上 `ss` 存在但输出为空，而同端口 `/dev/tcp` 连得上。**

**（b）`src/client/client.sh` —— 非交互缺前缀时的静默失败**

```diff
- read -r -p "  这条订阅的节点名前缀 (默认 $guess): " sp || { echo; rm -f "$tmp"; return 1; }
+ if ! read -r -p "  这条订阅的节点名前缀 (默认 $guess): " sp; then
+     rm -f "$tmp"
+     print_err "读不到节点名前缀: stdin 不可用（非交互 / </dev/null）, 而这条订阅还没有前缀"
+     print_err "  节点名不加前缀会与本机已有节点重名 —— 重名的后果是静默覆盖旧节点, 面板还报 [OK]"
+     print_err "  非交互调用请显式指定: SB_SUBS_PREFIX=<前缀> bash sb-client add <地址>"
+     return 1
+ fi
```
保持 `return 1`（不替调用方猜前缀），但把**原因和出路**打出来。

> 成因链值得记一笔：那段前缀 prompt 只在**内核拒绝了取回的内容**时才走到
> （`if ! "$CLIENT_BIN" check -c "$tmp" && ! "$CLIENT_BIN" check "$tmp"`）。在 RN 上
> 恰恰因为 §5.3 的 cronet 缺陷让 `check` 失败，才掉进这条带 prompt 的分支 ——
> 两个缺陷是**互相咬合**的，单独看任何一个都不像根因。

**（c）`tools/check_share_links.sh:run_diagonal` —— 不传前缀 + 失败不给原因**

```diff
+ SB_SUBS_PREFIX="diag"                     # 显式给, 不依赖交互式 read
  ...
  bad "E1: 自家的分享自家客户端吃不下 (rc=$rc, 导入 ${n:-0} 个节点)"
  printf '%s\n' "$out" | grep -E "ERR|Error|失败|FATAL" | tail -3 | sed 's/^/         /'
+ printf '%s\n' "$out" | tail -6 | sed 's/^/         | /'      # 无条件贴尾巴
```

**（d）`tools/check_compat_wiring.sh`** 新增 **8d（2 条）+ 8e（4 条）**；并把已失效的
"`conf/share.sh` 归另一个 agent"判据换成只守 `share_client.py`（所有权本轮已移交本任务）。

### 1.1 `src/conf/interop.py` + `src/client/lib/interop.py`（各 +15/−6）— `5ed6206`

`parse_declaration()` 判"是不是完整地址"改看 **有没有 scheme**：

```python
_u = urllib.parse.urlsplit(s)
if s.startswith("?"):
    q = s.lstrip("?")          # `?a=1&b=2` 形态
elif _u.scheme:                # ★ 真探测 scheme, 不是"换个地方判子串"
    q = _u.query               # 完整地址 → 取它的查询串
elif "=" in s:
    q = s                      # 裸查询串
else:
    q = ""
```

**踩点报告（重要）**：委托方第一条给我的修法是「`s.startswith("?")` → 否则 `"://" in s` → 否则 `"=" in s`」。**照字面写不通过**——裸查询串里未编码的取件地址本身就含 `://`，第二支命中后 `urlsplit("interop=1&…&url-sing-box=http://h/n")` 的 `scheme`/`netloc` 皆空、整串当 path、`.query` 是**空串**。我先用 Python 实测确认了这一点（`raw-bare → recognized=None`）才动手，没有照抄。委托方随后也发来更正，与我的实现一致。两份拷贝逐字节同步（`248744aa…`）。

### 1.2 `install.sh`（+24）— `d8b41c1` ★本轮最要紧的修复

新增 `install_server_compat()`，在 `rsync_files()` 与 `do_server()` 两处调用：

```bash
install_server_compat() {
    cp -f "$SRC_DIR/src/client/compat2.py" "$SRV_ROOT/conf/compat2.py"
    rm -rf "$SRV_ROOT/conf/lib/proxy_node_compat"
    mkdir -p "$SRV_ROOT/conf/lib"
    cp -r "$SRC_DIR/src/client/lib/proxy_node_compat" "$SRV_ROOT/conf/lib/"
    find "$SRV_ROOT/conf/lib" -name '__pycache__' -type d -exec rm -rf {} +
}
```

### 1.3 `tools/check_compat_wiring.sh`（+98）— `6f23d65` + `d8b41c1` + `f994b38`

- **8b 段**：声明解析的三种入参形态 × 编码/未编码，共 4 格，每格要求 `recognized` 为真且 `decide()` 的 `(choice, reason, url)` 与完整地址**逐字段相同**。
- **8c 段**：把 `install.sh` 自己的 `rsync_files()` **抠出来真跑到沙箱**（不是"模拟它的行为"），再按 `share.sh` 的方式调 `uri_express.py`。
- **2 段**：canonical pin `9b73cc9` → `c2343b6`。

### 1.4 `src/client/lib/proxy_node_compat/{cli,engine,registry}.py` — `f994b38`

从 `git -C ../proxy-node-compat show c2343b6:proxy_node_compat/<f>` **逐字节**取（先验证过上游工作区干净且与 `c2343b6` 全 8 文件一致）。`uri.py` / `data/rules.json` 未动。
`install.sh` 那条是 `cp -r` 整目录 + `find … __pycache__ -delete`，**不带文件清单**，所以新增/改名文件不需要同步改清单（已确认）。

---

## 2 · RN 服务端：真实命令与原始输出

### 2.1 动手前的失败（这就是"分享功能整体不可用"）

```
$ cd /root/catmi/sing-box && bash conf/share.sh create-all 0 2
[OK] 分享内容与真实配置一致: all (16 个 outbound)
  [注意] rn-trojan01-TLS-CDN: 取件地址不一致 —— 原生=107.173.154.178:443 / 链接=hxicc.catmicos.dpdns.org:443 (陈旧产物)
  [注意] rn-vless01-TLS-CDN: …（同上）
  [注意] rn-vmess01-TLS-CDN: …（同上）
[Error] URI 表达力标注跑不起来 (rc=1) —— 拒绝静默发布
    Traceback (most recent call last):
      File "/root/catmi/sing-box/conf/uri_express.py", line 49, in <module>
        import compat2                                                       # noqa: E402
    ModuleNotFoundError: No module named 'compat2'
[Error] URI 表达力标注失败 —— 拒绝发布
RC=1
```

**根因**：`conf/uri_express.py` 是发布前的 URI 表达力闸门，它 `import compat2`；而 `compat2.py` 又把**它自己同目录**下的 `lib/` 加进 `sys.path` 再去 `import proxy_node_compat`。所以 `compat2.py` 与 `lib/proxy_node_compat/` 必须**成对落在 `conf/` 里**。但 `install.sh` 服务端分支只 `cp -rf src/conf/.`，而部署树上**没有** `src/client/`：

```
$ ls -d /root/catmi/sing-box/client /root/catmi/sing-box/conf/lib
ls: cannot access '/root/catmi/sing-box/client': No such file or directory
ls: cannot access '/root/catmi/sing-box/conf/lib': No such file or directory
```

因为这是**发布闸门**（按设计"不过就不发"），它坏掉时 `create`/`create-all` **一律 RC=1**，声明与两条产品全废；面板只吐一句 traceback。这正是"看起来成功"的反面同类：**每次操作都失败，却没有一句像样的提示**。

### 2.2 修复后：非交互面板路径全程走通

```
$ bash conf/share.sh regen-aggregate          # RC=0
  sb_client-all.json: 与重跑前**逐字节相同** sha=3c3e63c4ed07237e…（7360 字节）

$ bash conf/share.sh check all                # RC=0
[OK] 分享内容与真实配置一致: all (16 个 outbound)
（另有 11 行 "服务端当前没有监听 310XX" —— 全部为误报, 见 §5.1）

$ bash conf/share.sh create-all 0 2           # RC=0  ← 修好后不再被拒
[OK] 分享内容与真实配置一致: all (16 个 outbound)
  [标注] URI 表达力标注: 逐节点查过 13 个; 损失 3 条; UNKNOWN 8 项 (注册表 uri_rules 逐节点查; UNKNOWN 不折算成'没损失')
  [注意] URI 路径表达力损失 3 条（原生路径没有这些损失）:
    · rn-trojan02-REALITY  standard:reality  只能表达一部分  [uri.trojan.reality@mihomo] （仅 mihomo 的链接解析实现）mihomo 的 trojan 分支解析器不读 pbk → 拿不到公钥
    · …（同上不读 sid → 拿不到 shortId）
    · …（sni 读得到, 但没有 reality-opts 时只按裸 TLS 拨号: 握手完成但流量进了 fallback → 必然连不通）
  [UNKNOWN] scheme 没入册, 表达力判不了: naive+https, shadowtls
  [UNKNOWN] 原生有、URI 侧查不到且注册表没这一行（UNKNOWN, 不猜）: standard:mux, standard:naive, standard:shadowsocks, standard:tls, standard:transport.tcp
[Info] 格式: 普通话(URI 列表, N 行) + 原生(sing-box JSON) —— 同内核同发行版的客户端自动拉原生, 其余走普通话
[Info] 带声明的地址(客户端据此决策, 从**这里**复制): http://[2001:470:c:cf:bf47:d1e0:cd4d:c6db]:9443/share/25dd75eb253fdc30295abd428c0132d5?interop=1&kernel=sing-box&distribution=sing-box&version=1.14.2&formats=uri%2Csing-box&url-sing-box=http%3A%2F%2F%5B2001%3A470%3Ac%3Acf%3Abf47%3Ad1e0%3Acd4d%3Ac6db%5D%3A9443%2Fshare%2F3a181c47d03a8b41c792fde523799393
[OK] max_uses=0, 有效期 12 小时
```

声明形状与要求**逐参数对齐**：`interop=1` / `kernel=sing-box` / `distribution=sing-box` / `version=1.14.2` / `formats=uri,sing-box` / `url-sing-box=…`（`version` 是真探测：`python3 conf/interop.py self` → `{"kernel":"sing-box","distribution":"sing-box","version":"1.14.2","ok":true}`）。

### 2.3 两条产品成对 + 产物口径

```
$ SHARE_PROVIDER=sing-box python3 conf/share_client.py list
  role=primary  tag=all  ct=text/plain; charset=utf-8   token=25dd75eb253fdc30
  role=native   tag=all  ct=application/json            token=3a181c47d03a8b41
主产品行数 = 13
原生正文 sha256 = 3c3e63c4ed07237ef563a03ab5e822904a68290da52f697614fb28474840de2a
out/sb_client-all.json  = 3c3e63c4ed07237ef563a03ab5e822904a68290da52f697614fb28474840de2a   ← 逐字节相同
带声明地址 vs 裸地址响应体 sha256 = 33501a90eded99d0f2e3f9509fd0ae82abe0a7c4fdbb5eb89bee789fdb73e208（两边相同）
```

口径逐条核过：

| 要求 | 结果 |
|---|---|
| 不再出现 `obfs=none` | `grep -l obfs=none out/sb_share-*.txt out/sb_links-all.txt out/sb_client-all.json` → **无** ✓ |
| hy2 带宽参数形态 | 产物 `up_mbps:100/down_mbps:500` == 服务端 `config/hysteria2-01.json` 真实值（逐字相同）；URI 不含 up/down，符合 `hysteria2.sh:323` 的设计 ✓ |
| `tls.enabled` | 全部产物中带 `tls` 块的 outbound 共 **24** 个，**全部** `enabled: true`，无一缺失 ✓ |
| 节点数两产品一致 | 16 outbounds = 2 控制型（PROXY/AUTO）+ **13 节点** + 1 个 detour 辅助 `rn-shadowtls01-TLS-out`；主产品 13 行 URI ✓ |
| 无 `encryption=none` 之类脏参数 | 13 个 `sb_share-*.txt` + `sb_links-all.txt`(13 行) 全部通过 `check_share_links.sh` B 段 ✓ |

---

## 3 · 逐节点真连表（CC 上真 `sing-box 1.14.2`）

判据按委托要求：**`generate_204` == 204 且出口 IP == RN 的 CF 出口 `104.28.x.x`**。

**先钉死"204 不等于成功"这个前提**：

```
$ curl -s -o /dev/null -w '%{http_code}' https://www.gstatic.com/generate_204      # CC 直连, 不经任何代理
204
$ curl -s https://ipinfo.io/ip        → 183.210.249.163     # CC 直连出口（与任务书一致）
$ curl -s https://ifconfig.me/ip      → 2409:8a20:1c93:5460::2
```

即：**CC 直连本来就 204**。所以"204"单独完全不能算通过，判据必须叠加出口 IP。

| 节点名 | HTTP | 出口 IP | 判定 |
|---|---|---|---|
| rn-anytls01-TLS | 204 | 104.28.201.80 | OK |
| rn-anytls02-REALITY | 204 | 104.28.201.80 | OK |
| rn-hysteria201-TLS | 204 | 104.28.201.80 | OK |
| rn-naive01-TLS | 204 | 104.28.201.80 | OK |
| rn-reality01-REALITY | 204 | 104.28.201.80 | OK |
| rn-shadowsocks01-plain | 204 | 104.28.201.80 | OK |
| rn-shadowtls01-TLS | 204 | 104.28.201.80 | OK |
| rn-trojan01-TLS-CDN | 204 | 104.28.201.80 | OK |
| rn-trojan02-REALITY | 204 | 104.28.201.80 | OK |
| rn-tuic01-TLS | 204 | 104.28.201.80 | OK |
| rn-vless01-TLS-CDN | 204 | 104.28.201.80 | OK |
| rn-vmess01-TLS-CDN | 204 | 104.28.201.80 | OK |
| rn-vmess02-REALITY | 204 | 104.28.201.80 | OK |

**13 / 13 通过**（`104.28.201.80` ≠ `183.210.249.163`，所以每一条都是"真的从 RN 的 CF 出去了"）。

### 3.1 负对照（同一台测试内核、同一个 selector、同一条链路）

```
NODE             TRY    CURL_RC    HTTP             EXIT_IP
neg-control-good 1      0          204              104.28.201.80     ← 阳性对照: 没动过的真节点, 必须成功
neg-control-good 2      0          204              104.28.201.80
neg-deadport     1      35         000              none              ← 死端口 RN:31099
neg-deadport     2      35         000              none
neg-deadproxy    1      35         000              none              ← 死代理 192.0.2.1 (TEST-NET-1, 不可路由)
neg-deadproxy    2      35         000              none
neg-badnode      1      35         000              none              ← 故意坏的节点 (REALITY uuid 改错)
neg-badnode      2      35         000              none
```

三个负对照**全部失败**（curl rc=35 / http=000 / 无出口 IP），各跑 2 次结果一致。三条负对照都是**从真节点克隆、只改一样东西**（端口 / 服务器地址 / uuid），所以失败只能归因于改的那一样。

★ **`neg-control-good` 是关键**：没有它，"三个负对照全失败"完全可能只是测试台自己坏了（全链路不通）。它在**同一个 selector、同一条链路**里成功，证明这套判定是真判据，不是"看起来对的失败"。

---

## 4 · 同列验收：SB 客户端 ← SB 服务端

### 4.1 决策行（委托要求的原文）

```
[OK]   本次拉取: 原生 sing-box JSON —— 同内核同发行版 (sing-box/sing-box) → 取原生]
  compat 判定: 14 个节点, 跳过 0, 转换有损失 0 (内核 1.14.2 tags=with_gvisor,…)
[OK]   已导入 13 个节点 (单个链接全量分享); 现 13 个可用节点]
```

### 4.2 两条回退路径（都真跑过）

```
── [bare] 裸地址（声明缺失）   RC=0  节点=9
     1:[SB-Client] 本次拉取: 普通话 URI 列表 —— 地址上没有内核声明]
     7:[OK]   已导入 9 个节点 (单个链接全量分享); 现 9 个可用节点]

── [fallback404] 声明在、原生地址 404   RC=0  节点=9
     1:[SB-Client] 本次拉取: 普通话 URI 列表 —— 同内核同发行版 (sing-box/sing-box) → 取原生；
        原生取件失败(http://107.173.154.178:9443/share/9999…, HTTP 404) → 回退]
```

两条都把**原因和 HTTP 码**打了出来，不是静默降级。

> ★ **顺带挖出的实质差距**：普通话（URI 列表）路径只有 **9/13** 个节点，原生路径 **13/13**。差的 4 个是
> `rn-anytls01-TLS`、`rn-anytls02-REALITY`、`rn-naive01-TLS`、`rn-shadowtls01-TLS`
> —— 与发布时打的 `[UNKNOWN] scheme 没入册: naive+https, shadowtls` 一一对应。
> 也就是说 native 路径不只是"零损失"，它**多带 4 个节点**；跨内核客户端拿到的确实是打折的普通话。

### 4.3 CC 客户端更新（备份 → 落地 → 逐文件复核）

- 备份：`/root/backup-prepush-cc-20261011-100556/`（`sb-client` + `share-state/{to_sb.py,sub_server.py}`；备份时 `share-state/lib` **不存在**，已如实记录）
- 落地映射**以 `install.sh` 的 `do_client()` 实际代码为准**（任务书说的 `install_client` 在文件里其实叫 `do_client`，第 369 行）：

| 仓库源 | CC 目标 | 部署后 sha256 | 与仓库 |
|---|---|---|---|
| `src/client/client.sh` | `/usr/local/bin/sb-client` | `3bd3c1f57814e2d8…` | 一致 |
| `src/client/to_sb.py` | `share-state/to_sb.py` | `6fe77447055c4eb3…` | 一致 |
| `src/client/compat2.py` | `share-state/compat2.py` | `c8186d565f70c532…` | 一致 |
| `src/client/lib/interop.py` | `share-state/lib/interop.py` | `248744aa005582ba…` | 一致 |
| `src/client/sub_server.py` | `share-state/sub_server.py` | `1ac89ef1bd480ab4…` | 一致 |
| `src/client/lib/proxy_node_compat/*` | `share-state/lib/proxy_node_compat/` | 7 个源文件 + `data/rules.json` 全部 OK | 一致 |

`__pycache__/*.pyc` 在 CC 上**不存在是正确行为**——`install.sh` 的 `find … -name __pycache__ -exec rm -rf {} +` 就是要把它们删掉，别把它当漂移。另外我顺手删掉了 `share-state/__pycache__/`（旧 `to_sb.py` 的 `.pyc`），这是 install.sh 没覆盖到的陈旧缓存隐患。

**门禁要求的那条**：`src/conf/interop.py` 与 `src/client/lib/interop.py` sha256 **相同**（都是 `248744aa…`）✓

**`to_sb.py` 两边差异的定性**：CC 原文件 sha `b176f881…` == `git show 2c209b0:src/client/to_sb.py`，**逐字节相同**——即它是 `45fd108` **之前**的版本（27579 字节），缺的正是那三条实测缺口修复：`tls.enabled`、未知传输静默降级成 tcp、ECH 只认 PEM。方向明确是 **仓库 → CC**。这一档差异有真机后果：`45fd108` 修的就是"TLS 被静默降级成明文"，在本次验收的 13 个节点里会命中所有 TLS/REALITY 节点。

**没有重启任何 CC 服务**：`sb-client-sub.service` 的 `sub_server.py` 更新前后 sha 都是 `1ac89ef1…`（本来就一致，运行中的进程无需换代）；`sb-client.service` 跑的是 sing-box 二进制 + `/opt/sb-client/conf/`（本轮未改）。生产 MainPID 全程 `sb-client=1444214`、`sub=1801` 未变。

---

## 5 · 三条门禁：真实数字 + 反向证据

### 5.1 `share.sh check all` 的**全量误报** —— 已修（`ba1e670`）

`bash conf/share.sh check all` 返回 **RC=0**，但同时打出 **11 行**"服务端当前没有监听 310XX"。**这 11 行全是误报**：

```
$ ss -tulnH | grep ':31000'
tcp LISTEN 0      4096           *:31000       *:*
$ ss -tulnH | awk '{print $5}' | grep -cE ':31000$'      → 1     # 端口确实在听
$ ss -tulnH | awk '{print $5}' | grep -cE '[:]]31000$'   → 0     # ← 检查用的正则, 永远匹配不到
$ ss -tulnH | awk '{print $5}' | grep -cE '[]:]31000$'   → 1     # ← 本意是这个
```

`share.sh:_sb_share_verify_file` 里写的是 `grep -qE "[:]]${lport}$"`。在 ERE 里 `[:]` 是字符类（只有 `:`），后面接一个字面 `]`，于是它只在匹配 `:]31000` 时成立——`ss` 从不输出这种形状。**结果：每个非 loopback 节点都会被判"没有监听"**（本轮 11/11 全中；3 个 CDN 节点因为 listen 是 `127.0.0.1` 被前面那句 `continue` 跳过，所以恰好 11 个）。

危害有两层，第二层更要紧：`check all` 一边 RC=0 一边刷 11 条惊悚告警 → 告警疲劳；而**真的端口挂掉时告警长得一模一样**，于是"`check all` RC=0"在当时是**假绿** —— 那 11 条告警之下，一个真的死节点不会被拦。

**已修**（`[]:]` + 死端口升为 `bad=1` + `ss` 全瞎守卫）。真机复核：

```
$ ssh rn 'cd /root/catmi/sing-box && bash conf/share.sh check all'
[OK] 分享内容与真实配置一致: all (16 个 outbound)
RC=0
$ ... | grep -c "没有监听"
0            ← 11 条假告警归零（13 个节点确实都在听）
```

"端口真的挂掉时 `check all` 必须非 0"的证据由门禁 8e 出（见 §5.2）：死端口用例修前 `RC=0`、修后 `RC=1` 且报出"没有监听"。

### 5.2 `tools/check_compat_wiring.sh` — 28/0 → 32/0 → **38/0**

| 阶段 | 结果 |
|---|---|
| 起点 `a7150e2` | 通过 28 / 失败 0 |
| 加 8b 段（未修 `interop.py`） | **通过 29 / 失败 1**（exit=1） |
| 加 8c 段（`install.sh` 未修） | **通过 30 / 失败 2**（exit=1） |
| 只挪 canonical pin、未 vendor | **通过 31 / 失败 3** |
| vendor + 前两批修完 | **通过 32 / 失败 0**（exit=0） |
| 加 8d/8e 段（① ② 未修） | **通过 32 / 失败 6**（exit=1） |
| 收尾批（`ba1e670`） | **通过 38 / 失败 0**（exit=0） |

反向证据（每条新断言都在**修复前的代码**上红过，且**只有它红**）：

```
# 8b —— 修前 29/1, 编码那条绿、未编码那条红（说明断言是准的, 不是"永远红"）
  ✓ 编码裸查询串 / '?' 前缀形态 → 与完整地址同解（choice/reason/url）
  ✗ 未编码裸查询串被判成没有声明: recognized 为假（静默 no-declaration → 悄悄走普通话）

# 8b —— "假修"（把子串判据换个位置）也照样被拦: 28/2
  ✗ 未编码裸查询串被判成没有声明: recognized 为假

# 8c —— 修前 30/2, 沙箱里复现的正是 RN 上那句
  ✗ install.sh 装完 conf/ 仍缺 compat2.py / lib/proxy_node_compat —— 部署机上发布闸门必失败
  ✗ 部署布局下 conf/uri_express.py 跑不起来, create/create-all 会一律拒绝发布:
      Traceback (most recent call last): File "…/deploy/conf/uri_express.py", line 49, in <module>
        import compat2                                                     # noqa: E402

# 2 段 —— 只挪 pin 不 vendor: 31/3
  ✗ vendored cli.py 与 proxy-node-compat@c2343b6 不一致
  ✗ vendored engine.py 与 proxy-node-compat@c2343b6 不一致
  ✗ vendored registry.py 与 proxy-node-compat@c2343b6 不一致
# vendor 后
  ✓ vendored 副本 == proxy-node-compat@c2343b6（8 个文件, 逐字节）

# 8d/8e —— 把 ba1e670 的三个文件 `git checkout HEAD --` 回退后跑同一条门禁: 32/6
  ✗ 对角线不传 SB_SUBS_PREFIX —— stdin 是 /dev/null, 客户端会撞上交互式 read
  ✗ 非交互缺前缀时客户端没把原因打出来（rc=1, 匹配行 0 条）—— 这叫静默失败
  ✗ 端口在听的节点被判没在听 (RC=0, IPv4 通配 *:PORT): [Warn] 服务端当前没有监听 31000 …
  ✗ 端口在听的节点被判没在听 (RC=0, IPv6 方括号 [::]:PORT): [Warn] … 没有监听 41871 …
  ✗ 端口没在听的节点仍然 check RC=0 —— 死节点会被当作'一致'发出去（假绿）
  ✗ ss 全瞎时被当成'每个端口都没在听' (RC=0) —— 会全量拒发, 那不是发现死节点而是我们瞎了
# 修好后
  ✓ 8d 两条 + 8e 四条全绿 → 38/0
```

★ 注意 8e 那两条红里的 **`RC=0`** —— 那正是"假绿"的现场：端口明明在听，
`check` 却一边报"没有监听"一边返回 0。断言写的不是"有没有这句话"，而是
**返回码 + 文案**一起判，所以它同时钉住了误报和假绿两件事。

★ 8e **不依赖本机真的 `ss`**：往 `PATH` 前面塞一个 `ss` 桩，吐**真机（RN）捕获的**
三种输出形状（`*:P` / `[::]:P` / `127.0.0.1:P`）。原因是这台跑门禁的机器
`ss` 存在但**一条套接字都看不到**（`ss -tulnH` 空输出，而同端口 `/dev/tcp` 连得上）
—— 拿它当夹具会把"工具瞎"误判成"端口挂了"（我第一次就是这么假红了一次）。
用桩之后这条断言到哪台机器都成立，而且钉住的正是"解析真实 ss 输出"本身。

独立佐证：委托方的跨实现一致性台（`proxy-node-compat/tools/interop-conformance.py`，我**只读运行、未改**）对**当前工作区**报
**「全部一致：24 组向量 × 5 份实现，决策 / 参数名 / 交叉可读性零分歧。」**，其中
`✓ [bare] 同内核同发行版 sb-server=native/native-listed sb-client=native/native-listed`。

> 中间有一个**我自己造成的竞态**要交代：为取"假修"那格反向证据，我**故意**把 `interop.py` 临时改成字面子串版、跑完门禁立刻还原，那版在磁盘上只存在约 1 秒。委托方恰在那 1 秒采样，看到 `sb-server=uri/no-declaration` 报了红（并据此发来"你用的是错的那一版"）。当前工作区/HEAD 自始至终是正确版；已回报并请其复跑确认。

### 5.3 `tools/check_share_links.sh`

**无 `--share-url`（产物扫描 + 动态自测）**：`结果: [OK] 全部通过`，exit 0。F 段 15 条全绿；B 段 13 个 `sb_share-*.txt` 各 1 条链接 + `sb_links-all.txt` 13 条，全部通过。

**带 `--share-url`（对角线 SB 分享 → SB 客户端）—— 在 CC 上**：

```
== E. 对角线: SB 分享 -> SB 客户端 ==
  [OK]   E1: client.sh add 导入 13 个节点 (非 0), exit=0
  [OK]   E5: 带声明的地址 → 客户端走原生（日志里有'本次拉取: 原生'）
  [OK]   E2: 导入后的客户端配置 sing-box check 通过
  [OK]   E3: 真连 http=204|0.476468 (走节点, 端口 33329)
  [OK]   E4: 生产 sb-client MainPID 未变 (1444214) —— 隔离生效, 未碰生产
结果: [OK] 全部通过
```

**同一命令在 RN 上跑是 `[FAIL] E1 … rc=1, 导入 0 个节点`** —— 我把它查到底了，是**跑测机器**的问题，不是产物的问题，两个独立原因（**第 2 条已在 `ba1e670` 修掉**）：

1. RN 的内核是 `CGO: disabled` + 多一个 `with_purego` tag；CC 的是 `CGO: enabled`。同一份原生配置在 RN 上 `sing-box check` 报 `FATAL[0000] initialize outbound[3]: cronet: library not found`（naive 出站的 cronet 后端），在 CC 上顺利通过并真连 204。**仍是环境事实，保持 UNKNOWN（§6-3）。**
2. ~~`run_diagonal()` 调 `client.sh add` 时**没有传 `SB_SUBS_PREFIX``~~ → **已修**。`client.sh` 在缺前缀且 stdin 是 `</dev/null>` 时会走到交互式 `read -r -p '  这条订阅的节点名前缀 (默认 sub): '` → EOF → 原来只 `echo` 一个空行就**静默 `return 1`**（`bash -x` 实证：`+ read -r -p …` → `+ echo` → `+ return 1`，全程无错误行）。现在改为打出原因+出路并保持 `return 1`，且 `run_diagonal` 显式传 `SB_SUBS_PREFIX=diag`、失败时无条件贴客户端输出尾巴。由门禁 8d 两条钉死（见 §5.2）。

**最终一次（`ba1e670` 之后，用新的永久地址重跑，CC 上）**：

```
== E. 对角线: SB 分享 -> SB 客户端 ==
  [OK]   E1: client.sh add 导入 13 个节点 (非 0), exit=0
  [OK]   E5: 带声明的地址 → 客户端走原生（日志里有'本次拉取: 原生'）
  [OK]   E2: 导入后的客户端配置 sing-box check 通过
  [OK]   E3: 真连 http=204|0.454503 (走节点, 端口 22185)
  [OK]   E4: 生产 sb-client MainPID 未变 (1444214) —— 隔离生效, 未碰生产
结果: [OK] 全部通过   （B 段 13 个 sb_share-*.txt + sb_links-all.txt(13) 全部通过）
```

### 5.4 `tools/interop-e2e.sh`（带 `SB_E2E_CLIENT_BIN`，客户端侧**没有**跳过）

- **CC 上（最终 `e0ec3a1`，吃 RN 真实语料）**：`=== 结果: 27 通过, 0 失败 ===`，`E2E_EXIT=0`。第 6/7/8/9/10 段全部真跑：原生决策、裸地址回退、原生 404 回退、跨内核回退、成对生命周期（停用连带 / 撤销连带 / provider 清空 0 条）。客户端侧 `sing-box check 通过`。
- **RN 上**：`26 通过, 1 失败`，唯一的失败就是 §5.3 那条 `cronet: library not found`（机器缺 naive 后端），其余全绿。

> 更正一处任务书描述：`interop-e2e.sh` 的 `exit 3`（缺 `SB_E2E_CLIENT_BIN`）发生在 `tools/interop-e2e.sh:60`，**在任何验证之前**。所以本地那次不是"只验了服务端"，而是**什么都没验**。

> **`e0ec3a1`（本轮第 6 个 commit）是 `ba1e670` 的直接后果**：死端口从告警升为 `bad=1` 之后，
> 验证台吃**另一台机器**的语料时，发布闸门会正确地拒绝发布（CC 上 `ss` 正常、63 行，
> 而 31000 确实不在听）—— 于是它在第 2 段就 `✗ 创建分享失败 … (rc=1)`。
> 修法不是放宽断言，而是去掉一个**偶然的宿主依赖**：给验证台一个 `ss` 桩，输出从语料
> 自己的 `config/*.json` 生成，并**打一行说明**（"ss 桩声明语料里 16 个端口在听
> （本机不是那台服务器）"），不静默替换。端口探活的语义由 8e 段与真机 `check all` 各自钉住。

---

## 5.5 部署态复核（委托方审计 ① ② ③）

委托方把 `e0ec3a1` 逐字节分发到 RN 后提出一个正当的质疑：**我报的"真机"数字，跑的是
部署态还是我手上的树？** 我按项复核，结论如下 —— 先给一张**出处表**，把"哪些数字来自
部署态、哪些来自本地树"逐条摊开，不替上一轮圆场。

### 出处表（审计结论）

| 数字 / 结论 | 实际跑的是 | 判定 |
|---|---|---|
| `create-all` 修前 RC=1（`ModuleNotFoundError: compat2`） | RN 部署态 `conf/share.sh`（当时 = `a7150e2`）+ 我手工补的 `conf/compat2.py` · `conf/lib/` | **部署态** ✓（§2.1） |
| `create-all` 修后 RC=0 / 带声明地址 / 两条产品 | 同上（部署态） | **部署态** ✓（§2.2） |
| `check all` RC=0 + **11 条"没有监听"误报** | RN 部署态（`a7150e2` 版 share.sh） | **部署态** ✓（§5.1） |
| 13/13 逐节点真连表（204 + `104.28.201.80`） | CC 部署态 `/opt/sb-client/core/sing-box` + `/opt/sb-client/share-state/**` | **部署态** ✓（§3） |
| 负对照 + 阳性对照 | 同上（CC 部署态内核与产物） | **部署态** ✓（§3.1） |
| 两条回退（裸地址 / 原生 404） | 同上 | **部署态** ✓（§4.2） |
| `check all` 修后 RC=0 且误报归零 | RN 部署态 `conf/share.sh`（**我已 scp 并回读 sha `d31fc815…` 才跑的**） | **部署态** ✓（§5.1） |
| `check_compat_wiring` 28/0 → 38/0 | **本地树**（这本来就是个本地门禁，不在分发集里） | **本地树**（性质如此） |
| `interop-e2e` 27/0 | CC 上 `/tmp` 里**仓库的暂存副本**（该工具不在分发集，必须从仓库跑） | **本地树代码 + 部署态内核/语料** |
| `check_share_links --share-url` E1..E5 | CC 上仓库暂存副本的 `src/client/client.sh`；它与部署态 `/usr/local/bin/sb-client` **逐字节相同**（都 `0f72963e…`） | **本地树代码（与部署态同字节）** |

> 一句话：**上一轮那些"真机"数字绝大多数确实来自部署态**；只有两个门禁工具是本地树跑
> 的 —— 而这两个工具本来就不在分发集里（RN 上连 `tools/` 目录都没有，见 ② ），
> 它们必须从仓库跑。**没有任何数字来自"仓库代码假装成部署态"**，唯一需要补的是
> `ba1e670` 之后**没有在部署态上单独验过"死端口 → RC≠0"**这一条 —— 本轮补上了（①）。

### ① `ba1e670` 在部署态上的复核 —— 已补，结论成立

```
$ ssh rn 'sha256sum /root/catmi/sing-box/conf/share.sh'
d31fc8150e79573932bf1918e702a618f9dcb648c3f7742d0ac29e50b018710e   ← == 仓库 HEAD

$ ssh rn 'cd /root/catmi/sing-box && bash /root/catmi/sing-box/conf/share.sh check all'
[OK] 分享内容与真实配置一致: all (16 个 outbound)
RC=0        没有监听 出现次数: 0
```

死端口用例（**不碰运行中的服务、不碰真实 `config/`**：把真实 `config/`+`out/` 拷进
`/tmp` 沙箱，只把 `shadowsocks01-plain` 的端口在**配置与产物两处同时**改成 `31999`，
保证"端口一致但没人听" → 走的正是探活那一支）：

```
$ ss -tulnH | awk '{print $5}' | grep -cE "[]:]31999$"     → 0     # 确认真的没在听
$ SB_ROOT=/tmp/sb-dead bash /root/catmi/sing-box/conf/share.sh check all     ← 部署态代码
[Error] 服务端当前没有监听 31999 (配置里有, 套接字不在 —— 这个节点现在连不上): rn-shadowsocks01-plain
RC=1        没有监听 出现次数: 1

# 对照: 拿**修复前**的 share.sh (f994b38) 跑**同一个夹具**
[Warn] 服务端当前没有监听 31002 …（共 11 条）
RC=0        ← 死端口却 RC=0, 这就是"假绿"
# 对照2: 修复前的 share.sh 跑**健康**夹具 (真实部署)
RC=0        没有监听 出现次数: 11     ← 13 个节点全在听却报 11 条, 全量误报实锤
```

做完清理：`rm -rf /tmp/sb-dead /tmp/sb-dead-old`；复核真实部署 `check all` 回到 **RC=0 / 0 条**，
且真实 `config/shadowsocks-01.json` 仍是 `31004`、产物仍是 `31004`（**未被夹具污染**，已用 Python 读回确认）。
RN 四个 PID 全程未变。

### ② `ss` 桩只在验证台里，部署态路径不含桩 —— 证据

桩只存在于两处，**都在仓库 `tools/` 下，而 `tools/` 根本不在分发集里**：

```
$ ssh rn 'ls -d /root/catmi/sing-box/tools'      → No such file or directory
$ ssh rn 'grep -rIl "FAKE_SS_FILE\|fakebin" /root/catmi/sing-box/'   → （空）
$ ssh rn 'grep -n "ss -tulnH" /root/catmi/sing-box/conf/share.sh'
708:        ss_tbl=$(ss -tulnH 2>/dev/null | awk '{print $5}')      ← 部署态用的是**真 ss**
$ cd sing-box-core && grep -rln 'fakebin' . | grep -v '^./.git/'
./tools/check_compat_wiring.sh      ← 8e 段的桩 (cat "$FAKE_SS_FILE")
./tools/interop-e2e.sh              ← 验证台的桩 (从语料 config/*.json 生成)
```

结论：**线上路径 100% 用真 `ss`；桩只在两个验证工具自己的进程里生效**（`export PATH="$WORK/fakebin:$PATH"` 只作用于该脚本进程，脚本结束即消失）。部署集是 `src/conf/`(35) + `install.sh` + `sing-box.sh`，不含 `tools/`。

### ③ 永久分享 —— 已是部署态代码下发，并**在部署态重发过一次**

复核顺序（先证明再动作，不靠回忆）：

1. `ssh rn sha256sum conf/share.sh` → `d31fc815…` == 仓库 HEAD `ba1e670` 的版本 ✓
2. 在这个已核 hash 的部署态上跑 `bash conf/share.sh create-all 0 0` → **重发**（旧的 12h `25dd75eb` 与上一版永久 `cbad5c54` 都被同 tag 自动下架）
3. 复核：记录恰好 **2 条**成对、`expires=永久`；旧 token `cbad5c54`/`bd7ed23c` → **HTTP 404**；
   `check all` **RC=0**；主产品 **13 行**；原生正文 sha `3c3e63c4…` == `out/sb_client-all.json` **逐字节相同**
4. CC 端拉一次：`客户端 RC=0` / `本次拉取: 原生 sing-box JSON —— 同内核同发行版` / `已导入 13 个节点` / `sing-box check 通过`
5. `rules.json` 脱敏同步（§5.6）后再复核：`uri_express` RC=0、`check all` RC=0、原生正文 sha **未变**（`3c3e63c4…`）—— 与"语义零变化"的预期一致

**所以：`DECLARED_SHARE_URL`（本页顶部那条 `ab03704a…`）来自部署态代码，可以直接拿去跑九宫格。**

### 5.6 canonical 脱敏同步（两轮：`40a9441` → `692566c`，本地 commit `6f59a0d` / `30944fa`）

两轮都**只动 `data/rules.json` 一个文件**，其余 7 个文件不变；两轮都按同一条纪律走：
**先挪 pin（取红）→ 再逐字节 vendor（转绿）**，vendor 一律从 `git show <commit>:…` 取而非工作区。

| 轮次 | rules.json 哈希 | pin | 反向证据 | 结果 |
|---|---|---|---|---|
| `40a9441` | `58b86492…` → **`c1dc188a7988022f`** | `c2343b6` → `40a9441` | 只挪 pin **37/1** → vendor 后 **38/0** | ✓ |
| `692566c` | `c1dc188a…` → **`5e11b094ea18aa8a`** | `40a9441` → `692566c` | 只挪 pin **37/1** → vendor 后 **38/0** | ✓ |

- `40a9441`：证据里的真机 CDN 出口 IPv4 → `<CDN_IP>` 占位符（脱敏原来是"下游各自处理"）。
- `692566c`：上一版占位符说明里**点了下游仓库的名**，撞上 `mihomo--core` 自己的脱敏规则表
  （`对标项目|sing-box-core`）把它那条门禁弄红了 → canonical 改成"占位符块不点名下游"，
  并**把脱敏变成 canonical 自己的责任**：新增可移植门禁 `tests/test_data_hygiene.py`
  （数据文件不许有公网 IPv4 / DDNS 域名 / PAT / UUID / 32 位 hex；占位符约定必须写在文件头；
  反向验证过，注入真值会红）。**这一步是对的**：脱敏是数据本身的属性，散给下游就必然要开例外，
  而例外就是漂移入口。

**我没有只信转述，自己扫了一遍新文件**：公网 IPv4 → **无命中**；`<CDN_IP>` 占位符在；
文件头有占位符约定；`68 规则 / 29 证据 / 13 URI 规则`逐条可加载。

**同步范围（三处，每处回读 sha 确认）**：

```
src/client/lib/proxy_node_compat/data/rules.json                          5e11b094ea18aa8a…
rn:/root/catmi/sing-box/conf/lib/proxy_node_compat/data/rules.json        5e11b094ea18aa8a…
CC:/opt/sb-client/share-state/lib/proxy_node_compat/data/rules.json       5e11b094ea18aa8a…
```

仓库侧 `src/conf/` 下**没有**这份副本（只有 `src/client/lib/` 一份），所以仓库侧只此一处；
部署侧那两份正是 `install_server_compat()` / `do_client()` 的落点，一并同步。
按委托方要求，两轮都**不动** `src/conf/uri_express.py:191` 注释里那处真机地址 —— 那是 SB 自己的口径，不在 canonical 同步范围。

**部署态复核（换完新 `rules.json` 之后）**：`uri_express.py report` **RC=0**；
`bash conf/share.sh check all` **RC=0 且"没有监听" 0 次**；分享正文 **未变**
（原生 sha 仍 `3c3e63c4ed07237e…` == `out/sb_client-all.json`，主产品 13 行）；
记录仍是**成对 2 条、永久**。**即 canonical 的脱敏改动对线上产物零影响**，与"数据语义零变化"一致。

---

## 6 · UNKNOWN 清单（不知道就说不知道）

> **注册表类缺口已由委托方汇总到 `research/known-issues/registry-gaps.md`**（只读引用，我没有改它）：
> 本清单的 2/3/6 三条分别对应那里的 **U-2 / U-3 / U-4**，另 U-1 / U-5 对应本清单第 3 条那五行 unregistered。
> 这里保留 SB 侧的**原始证据**（谁观测到的、观测到什么），判定与补规则的时机归那份清单。

> 委托方明确：naive/shadowtls 未入注册表、CDN 取件地址不一致、RN 无 cronet 后端
> **保持 UNKNOWN**，不许为了好看去补。原 ①②（端口探活正则 / 对角线静默失败）本轮已修，
> 从本清单移出。

1. **RN 的内核二进制没有可用的 naive/cronet 后端**（`CGO: disabled` + `with_purego`，`sing-box check` 报 `cronet: library not found`）。**这是环境事实，不是代码缺陷**；但它意味着"在 RN 上跑任何吃 naive 出站的客户端侧验证"都会假红。
2. **`naive+https` / `shadowtls` 两个 scheme 没进 URI 表达力注册表** —— 发布时如实打 `[UNKNOWN]`，没有折算成"没损失"。它们在普通话路径上丢 4 个节点（13→9）。**这两个 scheme 到底能不能无损表达，我不知道，注册表也没说。**
3. **`standard:mux` / `standard:naive` / `standard:shadowsocks` / `standard:tls` / `standard:transport.tcp` 五项在注册表里没有对应行** —— 发布时照原样报 UNKNOWN，未猜。
4. **3 个 CDN 节点的"取件地址不一致"是陈旧产物还是有意为之，我没有权威结论**：原生写 `107.173.154.178:443`、URI 写 `hxicc.catmicos.dpdns.org:443`。发布时**显式标注**了（未静默），但两条产品确实把用户带到两个地方。本轮**未重生成**这 3 个节点（那要动节点配置，超出"重建分享产物"的范围）。
5. **`hysteria2` 带宽 `100/500`** —— **定性已定：旧默认遗留，不是显式设置**（证据见 §5.7）。
   但**对齐动作被一条硬约束挡住**：面板的生效路径是 `lib.sh:2807 sb_reload()` → `systemctl restart "$SB_SERVICE"`
   （sing-box **不支持** SIGHUP 热重载，`lib.sh:2824-2830` 明确写了这件事：unit 里的
   `ExecReload=/bin/kill -HUP` 永远"成功"但什么也不做）。而本任务的硬纪律是
   **"不许重启或 stop 任何服务"**。所以我**没有动它**，把它作为待决项交回（§5.7 给了两个选项）。
   *（更正：本清单上一版把它写成"节点自身的显式设置、产物忠实"—— 那个说法是错的。
   "节点文件里写着 100/500" ≠ "有人显式设过 100/500"，我把两者混为一谈了。）*
6. **★ URI 侧拿不到 hy2 带宽 —— 一个没有被任何地方说出来的表达力损失（compat 侧缺口）**：
   同一节点的**原生 JSON 有 `up_mbps`/`down_mbps`**，而 **`hysteria2://` URI 里完全没有带宽参数**
   （`hysteria2.sh:323` 的模板里就没有 up/down）→ 走普通话的客户端拿到的速率提示与走原生的不同，
   而**没有任何一处说出来**。我核过分享记录 meta：`uri_losses` 的 `losses` 只有 3 条
   （全是 `rn-trojan02-REALITY standard:reality uri.trojan.reality@mihomo`），
   `unregistered` 是 `standard:mux / naive / shadowsocks / tls / transport.tcp`，
   `unknown_scheme` 是 `naive+https / shadowtls` —— **整份 meta 里 `mbps` / `up` / `down` / `带宽` 一个都不出现**。
   也就是说：**同一个节点的两条路，客户端拿到的速率提示不同，而注册表没登记、发布时不标注、客户端也不知道。**
   按委托方要求只登记不改 compat；这属于**注册表缺口**，已汇总为
   `research/known-issues/registry-gaps.md` 的 **U-4**（本次我按指示只引用、未改那个文件）。
   **这是本轮唯一一处"两条产品语义不同且无人声明"的地方。**
7. **RN 的 `.addr-family = v6`**，下发的地址是 IPv6 字面量。CC 走 IPv6 取到 `HTTP=200 ip=2001:470:c:cf:bf47:d1e0:cd4d:c6db`，同一 token 走 `107.173.154.178` 也 200（委托方实测，同为 ~0.57s）。但**纯 IPv4 环境下的第三方面板能不能用这条地址，我没有验证**。
8. `ds`（生产 107.174.201.250）**全程一个字节都没写**，也没有做任何只读以外的动作 —— 但它当前的实际状态我不知道，本轮没有连过。
9. **跑门禁的这台机器上 `ss` 存在但输出为空**（`ss -tulnH` 0 行，而同端口 `/dev/tcp` 连得上）。所以我给 `share.sh` 加了"ss 全瞎 → 告警跳过（fail-open）"的守卫，8e 段也改用 ss 桩。**这类环境还有哪些变体（netns、seccomp、精简 busybox）我没有穷举**；真机 RN 上 `ss` 正常。

### 5.7 `hysteria2` 带宽 `100/500` 的定性（证据链）

**结论：旧默认遗留（old-default leftover），不是有人显式设过。**

| 证据 | 内容 |
|---|---|
| 变更点唯一 | `git log -S'SB_HY2_UP_MBPS' -- src/conf/` → **只有 `fe47df8`** 一个 commit（2026-10-10 23:34:41 **+0800** = **2026-10-10 08:34:41 PDT**） |
| 变更前无任何入口 | `git show fe47df8^:src/conf/hysteria2.sh` → `"up_mbps": 100,` / `"down_mbps": 500,` 是**硬编码字面量**（出现两处：inbound 与 outbound）；全文件 grep `MBPS` **无命中**，`read -r -p` 只问了节点类型 / UDP 跳跃 / obfs，**没有一句问带宽** → 当时**不存在**把它设成别的值的路径 |
| 当时的部署脚本备份 | `/root/catmi/sing-box/backup/scripts-20261004-044145/conf/hysteria2.sh` 与 `scripts-20261006-000139/…` 里都是 `"up_mbps": 100` / `"down_mbps": 500`，且**没有** `SB_HY2_UP_MBPS` |
| 节点比变更早 6.5 天 | 最早 hy2 产物 `sb_meta-hysteria201-TLS.json` = **2026-10-03 20:39:43 PDT**；`config/hysteria2-01.json` mtime = 2026-10-09 04:02（certpath 迁移）。两者都 **早于** 08:34:41 PDT 的 `fe47df8` |
| 从未被环境变量覆盖过 | `grep -rIl SB_HY2 /etc /root/.bashrc /root/.profile` → 只命中 `conf/hysteria2.sh` 与 `conf/lib.sh` 两个**定义处**，**没有任何地方设置它** |

⇒ 这个节点建于"100/500 是唯一可能值"的时代。**它保留 100/500 不是因为有人要 100/500，而是没人回头改。**

**当前字段现状（复核值）**：

```
config/hysteria2-01.json   inbound  hysteria201-TLS  up=100 down=500
out/sb_client-all.json     outbound rn-hysteria201-TLS up=100 down=500   （原生忠实）
out/sb_client-hysteria201-TLS.json     同上
out/sb_share-hysteria201-TLS.txt  → hysteria2://…?sni=…&alpn=h3    ← URI 里**没有**带宽参数（见 UNKNOWN 6）
```

**为什么我没有执行"对齐到 60/200"**：面板自己的重建路径（`hysteria2.sh` add 流程）末尾是
`sb_reload`，而 `sb_reload` = `systemctl restart sing-box`（`lib.sh:2807-2850`；sing-box 没有
热重载子命令，SIGHUP 无效 —— `lib.sh:2824-2830` 有明确注释）。执行它就会**重启 sing-box**、
PID 60510 变化，直接违反本任务的硬纪律"不许重启或 stop 任何服务"。
**只改文件不重载**也不行：那会造成"文件写 60/200、运行时仍是 100/500"的**静默分歧** ——
正是这个项目反复要消灭的东西，我不愿意制造它。

**两个选项（等委托方定，我不擅自选）**：

- **A（推荐，零风险）**：**保持 100/500**，在报告里写清"这是旧默认遗留；服务端带宽维持 100/500，
  且 URI 侧拿不到这个值（属表达力损失，已登记为注册表缺口，见 UNKNOWN 6）"。
  理由：`fe47df8` 自己的提交说明写着"这两个字段**不是限速**，是给内核的链路速率提示"，
  实际影响是速率提示偏低（100/500 甚至比 60/200 更宽），不影响连通性、不影响 13/13 真连结论。
- **B（要动服务）**：解开"不许重启"这条约束后，我跑
  `cd /root/catmi/sing-box && SB_HY2_UP_MBPS=60 SB_HY2_DOWN_MBPS=200 bash conf/hysteria2.sh <重建该节点>`
  （或面板重建该节点并回车取默认），随后 `check all` + CC 端拉一次复核。
  代价：sing-box 重启一次，13 个节点短暂断连，PID 60510 变化。


---

## 7 · 临时物清单与清理状态

| 临时物 | 位置 | 状态 |
|---|---|---|
| 一次性测试分享（overlay 全部 13 节点，`4303248e…`） | RN 公共服务 `provider=sing-box` | **已用面板路径撤销**：`bash conf/share.sh del 4303248e…` → `[OK] 已删除…` + `[OK] 连带: 已删除原生产物 1332ff0a2313…`；撤销后命名空间记录数 **0**，两个 token 直接取件均 **HTTP 404** |
| 12 小时期的中间分享（`25dd75eb…`） | 同上 | **已被 `create-all` 自动下架**（同 tag 旧 token 全下架），复核 `HTTP 404`；已被 TTL=0 的正式分享取代 |
| 验证用临时内核实例（CC: 端口 2081/2082/2083/2084/2085/2086 + clash 19099/19098） | CC `/tmp/sb-col/**`、`/tmp/sb-final*` | **已杀并复核**：`ss` 上这些端口全清；生产端口 2080/19090/9293 仍在原 PID 上 |
| 隔离客户端根 / 负对照配置 / 沙箱 / e2e 工作目录 / 暂存的修复版 | CC `/tmp/sb-col/`、`/tmp/sbx/`、RN `/tmp/sb-col/`、本地 `/tmp/sb-col/`、`/tmp/sb-fixed/`、`/tmp/sb-gate-*.txt`、`/tmp/sb-proto*` | **三台全部 `rm -rf`**，复核均 `No such file or directory`（本地 `/tmp` 下剩下的 `sb-arm64.tgz`/`sb-main/`/`sb-repo.tgz` 等 mtime 早于本会话，**不是我的**，未动） |
| RN 上供 e2e 用的仓库只读副本 | RN `/tmp/sb-col/sing-box-core` | 随 `/tmp/sb-col` 一并删除 |
| CC 上供 e2e 用的仓库副本 / 语料 / 服务源码 | CC `/tmp/sb-col/…`、`/tmp/sbx/…` | 一并删除 |
| 门禁沙箱 | `/tmp/sb-compat-gate.*`、`/tmp/sb-check-links.*`、`/tmp/sb-interop-e2e` | 门禁自带 `trap … EXIT` 清理；已复核无残留 |

**留在机器上的（有意，非临时物）**：

- **一条常驻的 `all` 分享**（主 `cbad5c54…` + 原生 `bd7ed23c…`，`max_uses=0`，**永久 TTL=0**）——这就是本页顶部那条 `DECLARED_SHARE_URL`，承担"SB 服务端对外可用形态"的角色，给委托方做跨内核矩阵用。不是"测试分享"：测试分享与 12h 中间分享都已撤销/下架。撤销：`bash conf/share.sh del cbad5c54e9c6a7ba44f7178e32cbaa4d`（会连带原生记录）。
- **部署同步**：RN `conf/share.sh`、`conf/interop.py`、`conf/compat2.py`、`conf/lib/proxy_node_compat/**`、`install.sh`；CC `/usr/local/bin/sb-client` 与 `share-state/**` —— 均与仓库 HEAD `e0ec3a1` 逐文件 sha256 一致（`share.sh` = `d31fc815…`、`client.sh` = `0f72963e…`）。
- **CC 备份**：`/root/backup-prepush-cc-20261011-100556/`（更新前原文件，供回滚；含 `sb-client.pre-ba1e670`）。
- **RN 回滚件**：`/root/backup-prepush-share.sh.bak`（`ba1e670` 之前的 `conf/share.sh`）。更早的 `conf/interop.py` 用 `git show a7150e2:src/conf/interop.py` 即可复现 `0d173763…`。

**服务与边界**：RN 四个 PID 全程未变（`xrayls 165517` / `mihomo 119320` / `sing-box 60510` / `proxy-share-service 69727`），未重启未 stop 任何服务；`/root/conf/**`、`/root/xray-panel.sh`、`/root/catmi/mihomo/**`、CC 的 `/opt/xray-browser-dialer/**`、`/usr/local/bin/xbd`、`/root/catmi/mihomo-client/**` **一个字节都没碰**；`proxy-node-compat` 只写了本文件，未动其 git。

---

## 8 · 复现清单（交给下一个人）

```bash
# 门禁（本地）
cd /root/deepseek/repos/sing-box-core
bash tools/check_compat_wiring.sh                     # 期望 38/0

# 服务端：重建聚合 + 校验 + 发布（RN）
ssh rn 'cd /root/catmi/sing-box && bash conf/share.sh regen-aggregate && bash conf/share.sh check all'
#   check all 期望 RC=0 且**一行"没有监听"都没有**（13 个节点确实都在听）
ssh rn 'cd /root/catmi/sing-box && bash conf/share.sh create-all 0 0'   # TTL=0 永久, 打印带声明地址

# 门禁（客户端真机：必须带 SB_E2E_CLIENT_BIN，否则 exit 3 且什么都没验）
#   注意：要在有可用 naive/cronet 后端的机器上跑（CC 可以, RN 不行 —— §5.3）
SB_E2E_SERVICE=/tmp/.../share_service.py \
SB_E2E_CLIENT_BIN=/opt/sb-client/core/sing-box \
SB_E2E_CORPUS=/root/catmi/sing-box \
bash tools/interop-e2e.sh                             # 期望 27/0

# 对角线
bash tools/check_share_links.sh --no-gen --out-dir /root/catmi/sing-box/out \
     --share-url "<带声明地址>" --client-bin /opt/sb-client/core/sing-box   # 期望 E1..E5 全绿
```

**排障备忘（本轮踩过的两个"看起来像内容问题、其实是环境"）**：

- 在**不是那台服务器**的机器上跑 `interop-e2e` / `check_share_links` 时，端口探活会
  如实报"没在听"并拒绝发布 —— `interop-e2e.sh` 已自带 `ss` 桩处理；
  `check_share_links.sh --share-url` 走的是**线上真地址**，不受影响。
- 在 RN 上跑客户端侧验证会因为缺 naive/cronet 后端假红（§6-1）。客户端侧的
  真机判据请用 **CC**。

---

## 9 · 九宫格（SB 客户端行）

**被测**：CC 部署态 `/usr/local/bin/sb-client` + `/opt/sb-client/share-state/**`（`client.sh` = `01ca9276…`、
`to_sb.py` = `138170f3…`，与仓库 HEAD `e861ab7` 逐字节一致），内核 `/opt/sb-client/core/sing-box` 1.14.2。
**三条地址原样未改**，各在一套**全新隔离 root**（`CLIENT_ROOT=/tmp/sbgrid/<格>`）里跑一次 `sb-client add`；
生产 `/opt/sb-client` 的 `conf/`、`nodes/`、`subscriptions.json` 全程未被写（生产 MainPID 1444214 未变）。

### 9.1 三列总表

| | **X（xray 服务端）** | **M（mihomo 服务端）** | **SB（sing-box 服务端）** |
|---|---|---|---|
| **决策行** | `本次拉取: 普通话 URI 列表 —— 服务端内核 xray ≠ 本机 sing-box` | `本次拉取: 普通话 URI 列表 —— 服务端内核 mihomo ≠ 本机 sing-box` | `本次拉取: 原生 sing-box JSON —— 同内核同发行版 (sing-box/sing-box) → 取原生` |
| **reason** | 跨内核 → 普通话（正确） | 跨内核 → 普通话（正确） | 同内核同发行版 → 原生（正确） |
| **方言** | **base64**（单行 1408B，无 `://`） | **明文 + 2 行 `#` 注释**（21 行） | **明文无注释**（13 行） |
| **订阅里的条数** | 5 | 19（+2 注释） | 13 |
| **解析（to_sb）** | `共=5 成功=4 跳过=1` | `共=19 成功=16 跳过=3` | 原生解析 13（走 JSON，非 URI） |
| **导入** | **4** | **16** | **13** |
| **真连通过** | **3/4** | **14/16**（首轮 10/16，4 个复测即通，见 9.4） | **13/13** |
| **丢掉的逐条理由** | ✗ `X-vless-xhttp07`：`不支持的传输方式 type='xhttp'`（sing-box 内核从来没有 xhttp/splithttp 出站）<br>⚠ `X-vless-xhttp08`：`standard:ech` 在链接里有、写出的出站里没有 | ✗ `mVLESS03-REALITY-XHTTP`、`mVLESS03-TLS-XHTTP-CDN`、`mVLESS02-TLS-XHTTP`：同为 xhttp<br>⚠ 5 条 `standard:ech` / `standard:tls.allow_insecure` 转换损失 | 无跳过；1 条 `⚠ rn-shadowtls01-TLS`：mux 三家内核不同构（跨内核搬运不保证语义） |
| **UNKNOWN** | `X-VLESS-WS_01` 连不上（`unexpected HTTP response status: 400`）——**是节点侧还是转换侧，我没有结论**（X 列的事） | `mHysteria202-TLS` / `mTUIC01-TLS` 连不上，机制已定位到**转换损失**（见 9.5）但"节点本身是否也坏"未分离 | 无 |

### 9.2 原始输出片段（部署态真机）

```
===== [X] RC=0 节点文件=4 =====
  [SB-Client] 本次拉取: 普通话 URI 列表 —— 服务端内核 xray ≠ 本机 sing-box]
  [OK]   识别为 share-uri 格式, 转换出 4 个节点]
  [WARN] 转换器跳过了 1 条（订阅里的节点数与实际导入数因此不同）:]
      格式=share-uri 共=5 成功=4 跳过=1 跳过原因={"compat[KERNEL_NEVER_SUPPORTED] 不支持的传输方式 type='xhttp' …": 1}
      ✗ gX-🇺🇸 X-vless-xhttp07 -> 不支持的传输方式 type='xhttp'…
      ⚠ gX-🇺🇸 X-vless-xhttp08: 分享链接里有 standard:ech, 写出的出站里没有 —— 客户端转换环节丢了
  [OK]   已导入 4 个节点 (单个链接全量分享); 现 4 个可用节点]

===== [M] RC=0 节点文件=16 =====
  [SB-Client] 本次拉取: 普通话 URI 列表 —— 服务端内核 mihomo ≠ 本机 sing-box]
  [OK]   识别为 share-uri 格式, 转换出 16 个节点]
  [WARN] 转换器跳过了 3 条（订阅里的节点数与实际导入数因此不同）:]
      格式=share-uri 共=19 成功=16 跳过=3 跳过原因={"compat[KERNEL_NEVER_SUPPORTED] 不支持的传输方式 type='xhttp' …": 3}
    compat 判定: 19 个节点, 跳过 3, 转换有损失 10
      ✗ gM-🇺🇸 mVLESS03-REALITY-XHTTP / mVLESS03-TLS-XHTTP-CDN / mVLESS02-TLS-XHTTP -> xhttp
      ⚠ gM-🇺🇸 mAnyTLS02-TLS / mAnyTLS01-TLS / mHysteria201-TLS / mTrojan03-TLS / mTUIC01-TLS: standard:tls.allow_insecure 丢了
      ⚠ gM-🇺🇸 mTrojan05-CDN-gRPC / mTrojan04-CDN-WS / mVLESS05-CDN-gRPC: standard:ech 丢了
  [OK]   已导入 16 个节点 (单个链接全量分享); 现 16 个可用节点]

===== [SB] RC=0 节点文件=13 =====
  [OK]   本次拉取: 原生 sing-box JSON —— 同内核同发行版 (sing-box/sing-box) → 取原生]
    compat 判定: 14 个节点, 跳过 0, 转换有损失 0
  [OK]   已导入 13 个节点 (单个链接全量分享); 现 13 个可用节点]
```

### 9.3 ★ 关于 M 的 `#` 注释行：**不是缺陷**（专门验过）

委托方的假设是"M 的两行 `#` 注释可能让 SB 少导入/报错/把注释当节点"。**逐条验完：都不是。**

| 检验 | 结果 |
|---|---|
| 注释被当成节点了吗 | **没有**。`to_sb` 报 `共=19`（不是 21）；`compat 判定 19 个节点`；导入 16 = 19 − 3 个 xhttp。注释行**一条都没进节点计数**。 |
| 注释导致报错了吗 | **没有**。M 格 `RC=0`。 |
| 注释让 SB 少导入了吗 | **没有**。修完 9.4 的两条缺陷后导入 **16**，与"19 条 URI − 3 条 xhttp"完全对上。 |

`to_sb.py` 对 `#` 是有意显式跳过的（`if l.startswith("#"): continue`，不计入 total）——
这条我同时在门禁 8f 里钉住了（断言 `total=2` 而非 3）。**SB 客户端三种方言全部吃得下。**

### 9.4 但真机上挖出了**两条真缺陷**（已修 + 门禁 + 反向验证，本地 commit `e861ab7`）

M 的 19 条里，**有 3 条 anytls 无声消失**（`mAnyTLS01/02/03-TLS`）；SB 自己的普通话产品 13 条里
**有 2 条 anytls 无声消失**。挖到底：

| # | 缺陷 | 根因 | 证据 |
|---|---|---|---|
| ① | `anytls://` / `socks5://` 被当成"不支持的 URI"丢掉 | `to_sb.py:uri_to_outbound` 的分派元组漏了 `anytls`（`URI_RE` 认它、`_std_uri` 里**有**分支→死代码、`_URI_TYPE` 也映射了），`socks5` 同理（`URI_RE` 写 `socks5?`，分派只有 `"socks"`）。**同一件事三份清单各写一次** | 修前 `to_sb` 直读：M `共=19 成功=13`、SB `共=11 成功=9`；修后 M `成功=16`、SB `成功=11` |
| ② | 丢节点**看不见** | 不匹配 `URI_RE` 的行是裸 `continue`，连 `total` 都不加 → 在 to_sb 自己的报告里**根本不存在**（SB 自己 13 行却报 `共=11`，naive+https/shadowtls 就这样消失）；且 `client.sh` **只在"整份转换出 0 个节点"时**才回显跳过原因 → 部分成功时少几个节点是静默的 | 修前 `共=11`，修后 `共=13` 且显式 `URI 协议未收录: naive+https / shadowtls`；客户端新增 `[WARN] 转换器跳过了 N 条` |

**修后效果**：X 4→4（不变，xhttp 该拒就拒）；**M 13→16**；**SB 自己的普通话产品 9→11**。
即 SB 客户端对自家明文产品的可用率 **9/13 → 11/13**；剩下 2 条是 `naive+https` / `shadowtls`
**没有 URI 解析器**（注册表缺口 U-2/U-3），现在至少**说得出来**而不是消失。

**门禁**：`check_compat_wiring` 新增 8f 段 4 条 —— 从 `URI_RE` 的**模式展开**候选 scheme
（`socks5?` → socks/socks5）逐个要求可转换（不写死清单，以后漏项会红）、`anytls://` 必须真转换、
未收录 scheme 必须可见且 `#` 注释不被计数、`client.sh` 部分成功时必须回显跳过。
**反向验证：修前 38/4（4 条全红，明指 `socks5,anytls`）→ 修后 42/0。**

### 9.5 逐节点真连表（判据：204 **且** 出口 IP ∈ CF 集合 `104.28.*` / `2a09:bac5:*`）

选取规则：**全部节点，不做子集**（4 + 16 + 13 = 33）。每格独立内核实例 + clash API 逐节点切换。
首轮 1 次尝试；对首轮失败者复测 2 次（节点刚切过去有连不上的时序假阴性：复测里 6 个 FAIL 有 4 个随即 204）。
下表取**所有尝试中的最好一次**。

| 格 | 节点 | HTTP | 出口 IP | 判定 |
|---|---|---|---|---|
| X | X-SS2022-02 | 204 | `2a09:bac5:6368:2da5::48c:5…` | OK |
| X | X-TROJAN-03 | 204 | `104.28.195.192` | OK |
| X | X-vless-xhttp08 | 204 | `104.28.195.192` | OK |
| X | **X-VLESS-WS_01** | 000 | none | **FAIL**（首轮+复测共 5 次全败） |
| M | mAnyTLS01-TLS | 204 | `2a09:bac5:6210:3050::4d0:4f` | OK |
| M | mAnyTLS02-TLS | 204 | `104.28.201.80` | OK |
| M | mAnyTLS03-TLS | 204 | `2a09:bac5:6210:3050::4d0:4f` | OK |
| M | mHysteria201-TLS | 204 | `104.28.201.80` | OK |
| M | **mHysteria202-TLS** | 000 | none | **FAIL**（一致复现） |
| M | **mTUIC01-TLS** | 000 | none | **FAIL**（一致复现） |
| M | mTrojan01-REALITY | 204 | `104.28.201.80` | OK |
| M | mTrojan02-REALITY-gRPC | 204 | `104.28.201.80` | OK |
| M | mTrojan03-TLS | 204 | `104.28.201.80` | OK |
| M | mTrojan04-CDN-WS | 204 | `104.28.201.80` | OK（复测通） |
| M | mTrojan05-CDN-gRPC | 204 | `104.28.201.80` | OK（复测通） |
| M | mVLESS01-REALITY | 204 | `104.28.201.80` | OK |
| M | mVLESS01-TLS-WS | 204 | `104.28.201.80` | OK |
| M | mVLESS02-REALITY-gRPC | 204 | `104.28.201.80` | OK |
| M | mVLESS04-CDN-WS | 204 | `104.28.201.80` | OK（复测通） |
| M | mVLESS05-CDN-gRPC | 204 | `2a09:bac5:6210:3050::4d0:4f` | OK（复测通） |
| SB | rn-anytls01-TLS | 204 | `104.28.201.80` | OK |
| SB | rn-anytls02-REALITY | 204 | `104.28.201.80` | OK |
| SB | rn-hysteria201-TLS | 204 | `104.28.201.80` | OK |
| SB | rn-naive01-TLS | 204 | `104.28.201.80` | OK |
| SB | rn-reality01-REALITY | 204 | `104.28.201.80` | OK |
| SB | rn-shadowsocks01-plain | 204 | `104.28.201.80` | OK |
| SB | rn-shadowtls01-TLS | 204 | `104.28.201.80` | OK |
| SB | rn-trojan01-TLS-CDN | 204 | `104.28.201.80` | OK |
| SB | rn-trojan02-REALITY | 204 | `104.28.201.80` | OK |
| SB | rn-tuic01-TLS | 204 | `104.28.201.80` | OK |
| SB | rn-vless01-TLS-CDN | 204 | `104.28.201.80` | OK |
| SB | rn-vmess01-TLS-CDN | 204 | `104.28.201.80` | OK |
| SB | rn-vmess02-REALITY | 204 | `104.28.201.80` | OK |

**合计 30/33 通过**（X 3/4、M 14/16、SB 13/13）。**"204 不等于成功"仍然成立**：
CC 直连本身就是 `ip=183.210.249.163`，表里没有一行是这个 IP。

### 9.6 负对照（都真跑，都失败/回退且有原因）

| 用例 | RC | 节点 | 打出来的原因 |
|---|---|---|---|
| 死地址（token 全 0，服务端 404） | **1** | 0 | `[ERR] 链接不存在` |
| 死端口（`107.173.154.178:9999` 无人监听） | **1** | 0 | `[ERR] 网络错误, 下载失败` + `[WARN] 可重试并在提示时选择走本机代理` |
| 声明在、原生 404 → 回退 | **0** | **11** | `本次拉取: 普通话 URI 列表 —— 同内核同发行版 (sing-box/sing-box) → 取原生；原生取件失败(http://…/share/000…0, HTTP 404) → 回退` |

第三条顺带印证 9.4 的修复：回退到普通话后导入 **11** 条（修此缺陷前是 9 条）。

### 9.7 反向：SB 自己那条"明文无注释"方言对第三方解析器的友好度

**有据的部分**：
- 用**独立实现**的中立解析器（canonical `proxy_node_compat.uri.parse_uri`，逐字节 vendored，不是 SB 自己写的）喂三个方言：**X 5/5、M 19/19（2 行注释正确跳过）、SB 13/13** —— SB 这条 **13/13 全部解析成功**。
- SB 的方言是三种里**最"素"**的：不需要 base64 嗅探（X 需要）、不需要注释跳过（M 需要）。对"按行读 `scheme://`"的实现，它就是零特判的输入。
- vmess 条目的形态是**刻意选的**：`vmess://base64(JSON)` 且名字写在 JSON 的 `ps` 里、**不带 `#` 片段**（`to_sb.py:418-421` 注释写明理由：mihomo 会把 `#` 片段一起塞进 base64 解码，解不开就把整条订阅判成 0 节点）。`tools/check_share_links.sh` 的 B 段规则 3 也在钉这条。

**UNKNOWN（没据就不猜）**：xbd / mihomo / 其他第三方面板**实测**吃得怎么样，我这轮**没有测**
（那要动它们的客户端，超出 SB 组权限）。上面只有"中立解析器 13/13 + 形态上零特判"两条证据，
**不构成对第三方实测兼容性的结论**。

### 9.8 本轮新暴露、**尚未被任何地方声明**的转换损失（登记，不在本轮修）

逐节点看失败原因时撞到的：URI 里有的东西，`to_sb` 写出的出站里**没有**，而 compat 的 `⚠` 清单**没提**：

| URI 里的 | 出站里的 | 后果（实测） |
|---|---|---|
| `tuic://…&alpn=h3` | `tls={"enabled":true,"server_name":…}`，**无 `alpn`** | `mTUIC01-TLS` → `CRYPTO_ERROR 0x178 (remote): tls: no application protocol` |
| `hysteria2://…&pinSHA256=b8f8fc…&pin=b8f8fc…` | **无任何证书 pin 字段** | `mHysteria202-TLS` → `x509: certificate signed by unknown authority` |
| `hysteria2://…&down=200&downmbps=200` | 只有 `up_mbps:60`，**无 `down_mbps`** | 速率提示只剩一半（本条节点仍能连，属静默的能力损失） |

这三条与 UNKNOWN §6-6（hy2 带宽）是**同类**：URI 表达力/转换损失没有被声明出来。
按纪律登记，**本轮不改**（要动 compat 的注册表与 `to_sb` 的映射，且需要先有"各客户端到底读哪个参数名"的证据）。

---

## 10 · 收束：声明缩短（去 `version` + 同源相对路径）— 本地 commit `b25f5a0`

用户拍板缩短下发地址。三家契约必须逐条相同，SB 侧按同一口径做完三条。

### 10.1 改了什么

| # | 契约 | 落点 |
|---|---|---|
| ① | **不再产出 `version`** | `share.sh:sb_share_declare_url` 不再传 `--version`。参数**保留**（`build_declaration` 仍接受、默认空），解析侧**仍接受** `version`——只是不参与决策。**不 bump schema**，旧地址照样判 native |
| ② | **同源 → 相对路径** | `sb_share_declared_url` 里判定同源则把 `url-sing-box` 写成 `/share/<token>`；异源仍写绝对地址。新 `sb_same_origin()` 严格按 **(scheme, host, port)** 比 —— **必须比端口**，并把 http→80 / https→443 归一 |
| ③ | **解析侧拼回绝对** | `parse_declaration()` 新增 `_is_rel_path()`；`decide()` 签名不动。两份 `interop.py` 逐字节相同 |

`_is_rel_path()` **只认「单个 `/` 开头 且 原样末段非空」**：`//other.host/x`、`/share/`、`/`、`../x`、`x/y`
一律**原样保留** → `bad-native-url`。**不引入 urljoin 语义、不猜**；裸查询串形态**没有 base**，同样不猜。

> ★ 委托方提醒的 X 侧那个坑（先 `rstrip("/")` 再判末段 → `/share/` 被看成末段="share" →
> 拼出 `http://h:9443/share/` 这条"看起来完全合法"的死链）我避开了，**并且把它做成了反向验证**：
> 故意植入 rstrip 版后跑门禁 → **48 / 1 红**，红行正是「畸形相对形态被误拼或误判」，
> 且实测打印出 `/share/ → 拼成 http://h:9443/share/  decide: ('native','native-listed')`。

### 10.2 实测长度（用真 token，真代码算）

| | 长度 |
|---|---|
| 旧（部署态：含 `version` + 绝对 `url-sing-box`） | **302 字节** |
| 新（去 `version` + 相对路径） | **214 字节** |
| **缩短** | **88 字节** |

新地址形态（token 未变，**尚未分发到 RN** —— 按指示不重新部署）：

```
http://[2001:470:c:cf:bf47:d1e0:cd4d:c6db]:9443/share/ab03704acc0f2632201530d705660766?interop=1&kernel=sing-box&distribution=sing-box&formats=uri%2Csing-box&url-sing-box=%2Fshare%2F8526f930c8305cddb148c127497b10d9
```

同源判定对本例的结果：**同源** → `sb_rel_path` → `/share/8526f930c8305cddb148c127497b10d9` ✓

### 10.3 门禁数字

| 门禁 | 修前 | 修后 |
|---|---|---|
| `check_compat_wiring.sh` | **通过 46 / 失败 3**（3 条新行为断言全红：仍产出 version、相对路径没拼回来 `uri/bad-native-url`、同源 helper 不存在） | **通过 49 / 失败 0** |
| `check_share_links.sh --no-gen` | `[OK] 全部通过` exit=0（16 条 OK / 0 条 FAIL / 2 条跳过） | 同左（本机无 `out/` 产物，B 段跳过；它的断言不含这次的相对路径契约） |

8g 段 7 条里：**3 条是新行为**（产出侧无 version、相对→绝对且判 native、同源判定含端口不同这一格），
**已反向验证**；另外 **4 条是回归钉**（旧格式仍 native、四种畸形形态原样保留、裸查询串不猜、空 version 不出参数）
—— 它们**按设计改前就是绿的**，作用是防"将来被改坏"，不是被这次改动变绿。这一点写清楚，不混算成 7 条反向验证。

### 10.4 ★ 一处与委托方前提不符的事实（如实报）

委托方说「版本不会丢 —— 原生产品里本来就有自描述（`kernel` / `distribution` / `kernel_version`）」。
**SB 侧实测：这个前提对 SB 不成立。**

```
$ grep -rl "kernel_version|distribution|kernel" /root/catmi/sing-box/out/
  （空 —— out/ 里没有任何文件带这些字段）
$ python3 -c 'import json;print(list(json.load(open("out/sb_client-all.json")).keys()))'
  ['outbounds', 'route']                       ← 就是一份普通 sing-box 配置
$ python3 -c '...out/sb_client-hysteria201-TLS.json...'
  ['outbounds']
$ cat out/sb_meta-hysteria201-TLS.json
  {"tag","port","hop","cert","cert_trusted","auth","mask"}   ← 是节点参数, 不是内核自描述
```

内核自描述**只存在于分享 meta**，实测仍在：

```
kernel = 'sing-box'   distribution = 'sing-box'   kernel_version = '1.14.2'   formats = ['uri','sing-box']
```

所以去 `version` 的**真实影响**是：**只看地址的第三方客户端不再能读到内核版本号**（它本来也只用
`kernel` / `distribution` 决策，`version` 从未参与 `decide()`）；版本号仍可从分享 meta 读到，
服务端侧没丢。**"原生产品里也有"这一条在 SB 不成立** —— 要不要在原生产品里补自描述，
属于新需求，本轮**未做**（委托方明确本轮只做这一件）。

### 10.5 分发后真值（RN 已分发 `b25f5a0`）

部署态核对（`conf/share.sh` = `bf74174442273525`、`conf/interop.py` = `e8885712801b41a1`，均 == 仓库 HEAD）。

**① 线上真实的声明地址（原样，214 字节）**

```
http://[2001:470:c:cf:bf47:d1e0:cd4d:c6db]:9443/share/ab03704acc0f2632201530d705660766?interop=1&kernel=sing-box&distribution=sing-box&formats=uri%2Csing-box&url-sing-box=%2Fshare%2F8526f930c8305cddb148c127497b10d9
```

```
$ printf '%s' "$D" | wc -c   →  214
   含 version + 绝对 url 的旧形态          →  302   （缩短 88）
```

> **声明不需要"重新发布"**：按设计它**从不落盘**，每次由 `sb_share_declared_url()` 现算
> （理由写在代码里：地址族切换会改对外 host，落盘的声明会留旧 host 变成死链）。
> 所以 `b25f5a0` 一分发，同一条 token 的声明就**自动变成缩短版**——**token 未变、无需重发**。

**② 复核（全部真跑）**

| 项 | 结果 |
|---|---|
| 记录 | **2 条成对**：`8426f930…:native` + `ab03704a…:primary`；`expires_at=0`、`max_uses=0`、`enabled=True`；token **未变** |
| `check all` | **RC=0**，"没有监听" **0 次** |
| payload 未变 | 主产品 **13 行**；原生 sha **`3c3e63c4ed07237e…`** == `out/sb_client-all.json` |
| 带声明 vs 裸地址 | 响应体 sha **IDENTICAL**（声明对返回内容零影响） |
| 面板刷新路径 | `bash conf/share.sh regen-aggregate` **RC=0** |
| **幂等** | 连跑两次，全部指纹**逐一相同**：`declared_len` / `primary_lines=13` / `native_sha` / `product_sha` / `share_tag-all.txt` 的 sha **与 mtime** / 记录集合 |

**③ `out/share_tag-all.txt` 的实际形态（与委托措辞的一处出入，如实报）**

该文件里是 **裸地址（87 字节）**，**不是** 214 字节那条：

```
http://[2001:470:c:cf:bf47:d1e0:cd4d:c6db]:9443/share/ab03704acc0f2632201530d705660766
```

这是**设计如此**，不是漏刷新：`create_share` 只在此处落盘（`share.sh:652`），且刻意只落**裸地址** ——
带声明的地址里嵌着一条百分号编码的原生地址，落盘后一旦地址族切换就会变成死链。
`share_refresh_all()`（`regen-aggregate` 调的刷新）**不写** `share_tag-*.txt`（只刷服务端内容），
所以它的 mtime 在刷新前后不变 —— 幂等检查里也把它当指纹之一验过。
**214 字节那条是"声明地址"，它在 `share.sh list` 的"拉取地址"里现算给出**（用户是从那里复制的），
两者并存且各司其职。**我没有为了让文件"看起来是 214 字节"去改这个设计。**

**④ CC 端拉取（用缩短版地址）**

```
[OK]   本次拉取: 原生 sing-box JSON —— 同内核同发行版 (sing-box/sing-box) → 取原生]
[OK]   已导入 13 个节点 (单个链接全量分享); 现 13 个可用节点]
节点数: 13      sing-box check: 通过        RC=0
```

> **这一步先暴露了我自己的一个部署遗漏**：第一次拉取时 CC 上的 `lib/interop.py` 还是
> **`248744aa…`（缩短前那版）**，于是它把 `/share/…` 判成取件地址不可用 →
> `本次拉取: 普通话 URI 列表 —— 原生取件地址不是可用的 http(s) 地址: /share/8526f930…`
> → 回退普通话、导入 11 条。**这恰好正面验证了"旧实现读相对路径 → 回退普通话、安全可见"
> 这条设计**（不是静默出错，也不是误判 native）。我把 `src/client/lib/interop.py`
> （`e8885712…`）补部署到 CC `/opt/sb-client/share-state/lib/interop.py` 后重跑即 13/13 原生。
> 备份留在 `/root/backup-prepush-cc-20261011-100556/interop.py.pre-b25f5a0`。

**⑤ 顺带撞到、**未修**的一处（新 UNKNOWN，按"其它一律不做"只登记）

第一次那趟**回退到普通话**时，客户端导入 11 条后 `sing-box check` **失败**：

```
FATAL[0000] initialize outbound[6]: uTLS is required by reality client
```

定位（一条命令，止于此）：普通话路径的产物里，三个 REALITY 出站只有 **trojan 那个缺 `utls`**：

```
🇺🇸 rn reality01-REALITY   type=vless    tls.utls={'enabled': True, 'fingerprint': 'chrome'}
🇺🇸 rn trojan02-REALITY    type=trojan   tls.utls=None        ← sing-box: reality 客户端必须 uTLS
🇺🇸 rn vmess02-REALITY     type=vmess    tls.utls={'enabled': True, 'fingerprint': 'chrome'}
```

即 **`trojan://…&security=reality` 的 `fp` 没有进 `tls.utls`**（vless/vmess 都进了）。
后果比 §9.8 那三条更重：它不是"单个节点连不上"，而是**整份配置 `check` 直接 FATAL**
—— 也就是说**原生取件失败时回退到普通话，得到的是一份起不来的配置**。
属同一类（URI→出站字段丢失、且无人声明），**本轮未修**（委托方明确"其它一律不做"），登记在此。
