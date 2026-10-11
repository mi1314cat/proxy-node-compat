# M 内核回退：**已在 GitHub 上执行完毕**

> 2026-10-11 ｜ 用户要求"把 M 内核回退到三家互通之前，但保留与互通无关的真修复"。**已完成并推送。**
> 本文件替换掉之前那份 `m-rollback-built-pending-push.md`（那份是"等凭据"时的状态）。

---

## 1 · 结果

| 项 | 值 |
|---|---|
| 仓库 | `mi1314cat/mihomo--core` |
| **远端 `main`** | **`606d049`**（= 回退提交 `4a24f16` + 版本号补提交） |
| **远端 `refactor/v2`** | **`606d049`**（与 main 保持一致 —— 这是本仓库的约定） |
| 回退前的 main | `01890ef`（本地留档 tag **`pre-rollback-backup`**） |
| 净变化 | **+233 / −9967**，删 16 个互通文件，无新增文件 |
| 推送方式 | **两次都是 fast-forward，没有用 `--force`**（历史未改写） |
| `src/VERSION` | 内容哈希收敛为 `7e9a21f6406c` |

---

## 2 · 推送时撞到的**自有门禁**（值得记，以后还会遇到）

第一次推 `main` 被仓库自己的 `pre-push` 钩子**拒绝**了：

```
✘ 拒绝推送 refs/heads/main
  本地 main      = 4a24f16
  refactor/v2    = 01890ef
  本地 main 落后于 refactor/v2。直接推 main 会让**远端 main 倒退**。
```

**这个钩子是对的**（它挡的是"本地 main 过期 → 把远端 main 推回退"这个历史上踩过三次的坑），
只是它不知道这次是**故意回退**。它的规则是：**推 `main` 前要求本地 `main` == 本地 `refactor/v2`**。

**正确解法**（不是绕过钩子）：把**两个分支一起**指到回退提交，让仓库自身的约定继续成立 ——
即 `main` 与 `refactor/v2` 同时落到 `4a24f16`，两边都是 fast-forward。这样钩子放行，约定不破。

> 附带教训：**别用 `--no-verify` 绕它**。那个钩子还负责写 `src/VERSION`（内容哈希）——
> 绕过去就少了版本号这一步。

`src/VERSION` 是**内容哈希**（`sha1(manifest.txt 里除 VERSION 外的所有文件)`），
按设计"推送后才算最终值，所以要再补一个提交"。已按此补提交 `606d049`，并复核**已收敛**
（重算仍为 `7e9a21f6406c`，因为 VERSION 自己被排除在哈希外）。

---

## 3 · 保留了哪 4 条真修复（都在远端 main 上复核过）

| # | 修复 | 远端复核 |
|---|---|---|
| 1 | `1c23d1b` 重建节点 SNI 静默为空（7 处 `cert_` 前缀） | `src/conf/hysteria2.sh` 里 `cert_` 出现 14 次 ✓ |
| 2 | `23fe60f` 坏产物不许压过好产物 | `src/share/build_sub.py` 里"拒收/证书文件名"7 处 ✓ |
| 3 | `4b09b7e` 可移植部分：`_provider_load_count()` + 以内核真加载数为准 | 出现 2 处（定义 + 调用）；内核加载 0 个 → **报错并返回失败**，不再假成功 |
| 4 | `0c3fde2` 夹带的管道修复：`\| head` → `\| awk` | `awk 'NR<=` 2 处，`\| head` **0 处** ✓ |

**不保留的**：兼容层判定（`nodecompat.py` + vendored `proxy_node_compat/**`）、声明/两条产品、
URI 表达力标注/链接校验/对角线等互通期门禁；以及 `4b09b7e` 的「unbound variable」半条
（它修的是互通函数里的 `local x`，那函数随回退消失）。

---

## 4 · 验证

| 检查 | 结果 |
|---|---|
| 本仓库自带门禁 `bash tools/check_all.sh`（推送前在回退树上跑） | **19 / 19 全部通过** |
| 远端 `main` 互通文件数 | **0**（原 `01890ef` 有 13） |
| 远端 `main` 的 `src/client.sh` 互通符号 | `_sub_interop_decide` / `interop.py` / `MH_COMPAT_ENGINE` / `nodecompat` **各 0 次** |
| 两次推送 | 均为 fast-forward（用 `git merge-base --is-ancestor` 逐个核过） |

**移植过程先红后绿**（说明门禁有用）：先 3/19 未通过 —— `管道早退`（cherry-pick 带进来的
`| head`）、`幽灵函数`（我用了下划线开头的局部变量 `_loaded`，撞上本仓库"私有函数用 `_name`"
的约定）、`调用有定义`（我写了 `print_err`，而 M 的函数叫 `print_error`）。修完 → 19/19。

---

## 5 · 凭据处理

用户提供**一次性** PAT（`github_pat_…`），按本项目一贯做法：
**临时 askpass 脚本 + token 只放临时文件（`umask 077`）→ `GIT_ASKPASS=… git push` → `shred -u`**。
**没有写进 `git config`，也没有写进仓库任何文件**；推送完成后两个临时文件已 `shred -u`，
并复查 `/tmp` 下无残留。

---

## 6 · 本地留档（都在 `/root/deepseek/repos/mihomo--core`）

```
tag    pre-rollback-backup   → 01890ef   回退前的那条 main（随时可回）
tag    pre-three-way-interop → 32c03d7   互通前的最后一个版本
branch rollback/pre-interop  → 012ad3e   4 条修复的**逐条历史**（未推 GitHub；要留档可 `git push origin rollback/pre-interop`）
branch rollback/main-squash  → 4a24f16   被推送的那个回退提交
（main 与 refactor/v2 本地也已指到 606d049，与远端一致）
```

---

## 7 · 回退后会发生什么 / 还没验的

**预期行为**：分享订阅回到**只发 mihomo 原生 YAML**；地址上不再带 `?interop=1&kernel=mihomo&…`；
客户端回到普通订阅解析（不读声明、没有原生/普通话分派与回退链）；跨内核互认能力消失。

**UNKNOWN（没实测）**：**已经发出去的带声明分享地址**在服务端换回旧版之后会怎样 ——
按代码看新客户端会把它当普通订阅（声明不被解析），取回的是原生 YAML；
但**线上 RN 的部署态还没换**（本次只改了 GitHub），所以这条**没有验证**。
要验就得把回退版分发到 RN 再拉一次 —— 那是另一件事，未做。
