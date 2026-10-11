# X 内核回退：**已在 GitHub 上执行完毕**

> 2026-10-11 ｜ 用户要求"把 X 内核（`xray--core`）回退到优化三端之前（`7dfe2a5`），但保留与互通无关的真修复"。**已完成并推送。**
> 配套的是 M 的 `m-rollback-executed.md` 与 SB 的 `sb-rollback-executed.md` —— 三家都退完了。

---

## 1 · 结果

| 项 | 值 |
|---|---|
| 仓库 | `mi1314cat/xray--core` |
| **远端 `main`** | **`411a01f`** |
| 回退前的 main | `957e603`（本地留档 tag **`pre-rollback-backup`**） |
| 内容基线 | `7dfe2a5`（tag `pre-three-way-interop`） |
| 推送方式 | **fast-forward**（提交的父就是 `957e603`），**没有 `--force`** |
| 净变化 | 27 个文件：删 17 个互通文件；`+55 / −8554` 行 |
| 行数 | `conf/share.sh` 1193 → **846**；`Client/lib/actions.sh` 3585 → **3527**；`tools/check_libs.sh` 4889 → **4389** |
| 门禁分组 | 79 → **73** 组（删掉的 6 组全是互通组） |
| 远端互通文件数 | **0** |

---

## 2 · 做法（与 SB 相同，与 M 不同）

SB 那次已经用**实测数据**否掉了"从回退点挑修复"这条路：非互通修复大多做在**互通提交之后**，
文件上下文已变，cherry-pick 必冲突（SB 6 个里 5 个冲突）。X 的互通区间更长（**32 个提交**），
所以同样走「**从当前 main 出发，把互通摘掉**」—— 修好的东西**一个都不用挑、天然全在**。

摘掉的东西：

```
删 17 个文件: conf/lib/interop.py, conf/lib/native.py, Client/lib/interop.py,
              Client/lib/compat2.py, Client/lib/proxy_node_compat/**(8),
              tools/interop-corpus.py, tools/interop-e2e.sh,
              Client/tools/cc-verify-v2.sh, Client/tools/dualkernel-compare.py,
              Client/tools/compat-corpus.json
conf/share.sh               ← 用 7dfe2a5 做基线（单产品、地址上无声明），再贴回它的两条真修复
Client/lib/actions.sh       ← 摘掉互通决策链（_sub_interop_decide/_field/fetch_by_declaration/
                              report_choice 与调用点），保留"不认的链接必须可见"
Client/lib/compat.py        ← 回到 7dfe2a5 的 legacy 判定（无 compat2 依赖），★但单独捞回
                              9ecbc17 的 blocking_reason()（见 §3）
tools/check_libs.sh         ← 摘 6 个互通断言组 + compat2 判据一致性块；"三个消费者"→"两个消费者"
xray-panel.sh               ← _XRAY_LIB_FILES 去掉 interop.py / native.py（保留 hy2_products.py）
Client/tools/make-release.sh← 必需文件表与 vendored 校验段去掉互通项（保留 lib/compat.py）
Client/xbd-client.tar.{gz,xz} + .sha256 ← 按回退后的源码重打（62 项，包内零互通）
```

**行为变化**：分享地址回到**只发普通话 URI 列表**（地址上**没有内核声明**），服务端**不再产出原生
Xray JSON 产品**；客户端回到"直接拉取 + 按自身规则解析"，不再有"读声明 → 决定原生还是普通话"
的分派与回退链。

### 2.1 一个坑：跨内核 compat 组**嵌在别的组里面**

`group "跨内核 compat: mihomo 的 trojan 链接解析器丢 reality"` 那一组，是插在
**`group "分享链接 SNI / 证书 pin / hy2 参数"` 组的 `if ! command -v openssl … else` 分支内部**的 ——
它的收尾 `fi` 属于**外层组**。按 `group` 边界整段删会把这个 `fi` 一起删掉，`bash -n` 报
`syntax error: unexpected end of file`。正确切法是**按 278089d 的插入块**删（行 2197..2275），
把那两个非互通的块（真内核校验 + 证书 pin）留下。

> 教训：`group "…"` 只是设置标签的函数调用，**不等于语法块边界**。摘组时要用
> `shellcheck -s bash` 复核解析层（它直接指出"Expected 'fi' matching previously mentioned 'if'"），
> 光看 `bash -n` 只知道"文件末尾少了东西"。

---

## 3 · ★ 最容易丢的一条真修复：`blocking_reason()`

`Client/lib/compat.py` 若**整文件**取 `7dfe2a5` 版本，会丢掉 `9ecbc17`
（fix(客户端): parse_trojan 丢 pbk/sid → Trojan+REALITY 节点被静默丢弃）加进去的
**`blocking_reason()`** —— 而 `Client/lib/nodefilter.py:83` **仍在调它**：

```python
reason = m.blocking_reason(n, caps)      # nodefilter.py:83
```

后果不是"少一句提示"，而是**节点过滤这条路径直接 AttributeError**。
已从 HEAD 原样补回该函数（放在 `capability_tags` 之后、`want_browser_dialer` 之前，与 HEAD 同位置），
其余部分照旧走 legacy 判定。复核：

```
Client/lib/compat.py : def blocking_reason 1 处, compat2 0 处
Client/lib/nodefilter.py : blocking_reason 2 处（调用点未变）
Client/tools/selftest-compat.py : 114 项 PASS
```

> 这是本轮**唯一**一处"整文件照搬会出事"的地方。判据：**凡是被整体还原的文件，都要反查
> 它在互通区间里有没有收到过非互通修复**（`git log --reverse 7dfe2a5..HEAD -- <file>`），
> 以及**现存的调用方是否还在调被还原掉的符号**。

---

## 4 · 保留的 12 组非互通修复（都在远端逐组复核过）

`tools/check_libs.sh` 里**互通期新增、但与互通无关**的断言组，一组没少：

| # | 断言组 | 来源 |
|---|---|---|
| 1 | 载荷 ↔ per-node 产物一致性 + ECH 同源 | `55c736a` |
| 2 | 分享链接 SNI / 证书 pin / hy2 参数 (实机三证) | `e4b8b5f` |
| 3 | hy2 客户端链路: 链接参数不静默消失 (解析 → 生成) | `568c8f7` |
| 4 | Xray JSON 导入: 自己生成的 hy2 客户端产物能被自己读回 | `99c11ec` |
| 5 | nginx 生命周期: 选块 / 精确删除 / 回收 | `ae338cd` |
| 6 | mux 策略 (P0-1: 默认关 / 节点字段生效 / XHTTP 拒开) | `ead7e3c` + `0e396df` |
| 7 | SS2022 PSK 与 batch 退出码 (P0-2) | `36fa2b8` + `0e396df` |
| 8 | 分享链接发布 (P0-3: 回环节点不得按公网 host:port 发布) | `8a37e36` + `0e396df` |
| 9 | 旧格式字段与新校验 (P0-4) | `39623d9` + `0e396df` |
| 10 | 孤儿链已移除 (防回归) | `22d5d81` |
| 11 | 订阅解析: 不认的链接不许静默丢（M 的 # 注释方言也要吃） | `5b094c4` |
| 12 | hysteria2 带宽口径与产物只重建 (60/200 · .hy2-bandwidth · 无损拒绝) | `c0ad7f6` + `c3902a3` |

★ 其中 **1 / 8 / 9 / 11 是线上真事故的根因修复**（载荷与产物漂移、回环死链、内核拒收整份配置、
订阅静默少节点）——回退时最容易被连带丢掉，这里逐条保留。

**代码侧**（与 HEAD 逐字节一致，未经改动）：

```
conf/lib/nodes.py  conf/lib/share_payload.py  conf/lib/cert.sh  conf/lib/hy2_products.py
conf/lib/nginx_apply.py  conf/hysteria2.sh  conf/batch.sh  conf/Shadowsocks.sh …
Client/lib/node.py  Client/lib/genconfig.py  Client/lib/nodefilter.py
```

**两个文件是"回到基线再贴修复"的**（其余全部原样取自 HEAD）：

| 文件 | 相对回退点 `7dfe2a5` | 说明 |
|---|---|---|
| `conf/share.sh` | `+105 / −20` | 贴回 `8a37e36`（P0-3）与 `55c736a`（补 ECH + 一致性闸门），两条 `git apply` 均干净应用；逐行看过**只含这两条修复**，无互通概念（声明 / version / 原生路径） |
| `Client/lib/compat.py` | `+34 / −0` | 基线 + **`blocking_reason()` 一个函数**（见 §3），多出来的 34 行就是它 |

另：`Client/tools/selftest-compat.py` 与 `7dfe2a5` **逐字节相同**（互通区间没碰过它，早前曾误删、
已原样恢复）。

---

## 5 · 验证

| 检查 | 结果 |
|---|---|
| `bash tools/check_libs.sh` | **748 通过, 0 失败**，exit 0；含最后一组「门禁自检：没有检查被静默跳过」✓（没有假绿） |
| 分组完整性 | 回退后 73 组 ⊇ `7dfe2a5` 的 **61 组一组不少**；多出来的 12 组正好是 §4 那张表 |
| 功能冒烟：订阅解析（4 条 URI + 2 行 `#` 注释） | 解析出 **2 个节点**（vless / hysteria2）；`anytls` / `naive+https` 被判**未识别且可见**（有账，不静默丢）；**注释行既不算节点也不算未识别** ✓ |
| `python3 Client/tools/selftest-compat.py` | **114 项 PASS**（回退后的 compat.py 自洽） |
| `share.sh` 外部契约 | 调用方用到的 `create / list / refresh / migrate / retag / affected` **全部存在**于分派表 |
| 发布包 `Client/xbd-client.tar.{gz,xz}` | 重打后 **62 项**；包内 `compat2 / proxy_node_compat / interop / native.py / cc-verify / dualkernel` **0 命中**；两个格式解包后 **sha256 逐字节一致** |
| 全仓库残留互通引用 | **0**（`interop` / `compat2` / `proxy_node_compat` / `XBD_COMPAT_ENGINE` / `build_document` / `三家互通` 全清；只剩注释里的历史叙述，见 §7） |
| 远端复核 | `git ls-remote`：`main` = `411a01f`；`feat/client-groups-dns` = `a01fa68`（**未动**） |

---

## 6 · 凭据处理

用户提供**一次性** PAT，按本项目一贯做法：**临时 askpass + token 只放临时文件（`umask 077`）
→ `GIT_ASKPASS=… git push` → `shred -u`**。**没有写进 `git config`，也没有写进仓库任何文件**；
推送后两个临时文件已 `shred -u` 并复查 `/tmp` 无残留（`git config --get credential.helper` 为空）。

---

## 7 · 本地留档（`/root/deepseek/repos/xray--core`）

```
tag    pre-rollback-backup   → 957e603   回退前那条 main（随时可回）
tag    pre-three-way-interop → 7dfe2a5   互通前的最后一个版本
branch rollback/pre-interop  → 411a01f   = 远端 main（同名提交）
branch main                  → 411a01f   已对齐远端
branch feat/three-way-interop→ be4ec8e   互通实现分支，**只留本地**（未推送，供对照）
```

---

## 8 · UNKNOWN / 代价（没做、要知道的）

1. **线上 RN 的部署态没换**：本次只改 GitHub。RN 上跑的还是互通版（四个服务 PID 全程未动）。
   要把回退版生效到线上，得再分发到 RN + 重跑验收 —— 另一件事。
2. **`Client/VERSION` 没有动**：`7dfe2a5` 与 `957e603` 都是 `2.8.3`（互通区间**没有**碰过它）。
   所以回退后的包虽然内容变了，版本号仍是 2.8.3 —— **已经在 2.8.3 的客户端不会自动更新**。
   要让线上换版，需要手动分发，或按你们的发布习惯再决定是否升号（本轮**没升**，因为回退不是新发布）。
3. **`Client/lib/node.py` 留了一个互通期的"输入容忍"**：`parse_xray_json_many()`
   （多出站 Xray JSON 文档 → 节点列表，`32f65ef` 引入）。它**不含任何互通引用**、
   是"订阅内容不认识就报空"这一类通用缺陷的补丁，且是保留下来的
   `Xray JSON 导入` / `hy2 客户端链路` 两组门禁的依赖，故**有意保留**。
   同文件还有 4 处注释以"三家互通"作背景叙述（历史说明，不影响行为）。
4. **门禁覆盖的损失只在互通本身**：删掉的 6 组断言全是互通断言（声明决策 / 原生产品配对 /
   分享刷新补声明 / vendored 一致性 / 跨内核 compat 规则行 / compat2 判据漂移）。
   **没有**非互通断言被连带删掉 —— 判据是 §5 的"61 组一组不少"。
   随互通一起消失的工具：`tools/interop-e2e.sh`（端到端互通验证台）、
   `Client/tools/cc-verify-v2.sh` / `dualkernel-compare.py`（旧 vs 新判定双跑对比）。
5. **`conf/lib/share_payload.py` 里那段 base64 是原本就有的**（文件头写着"载荷格式一字未改"），
   不是互通产物 —— 本轮**没动**它（沿用 `README.md` §5 第 5 条的提醒）。
