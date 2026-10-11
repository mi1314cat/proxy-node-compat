# SB 内核回退：**已在 GitHub 上执行完毕**

> 2026-10-11 ｜ 用户要求"把 SB 内核回退到优化三端之前（`c0a5c19`），但保留与互通无关的真修复"。**已完成并推送。**
> 配套的是 M 的那份 `m-rollback-executed.md`。

---

## 1 · 结果

| 项 | 值 |
|---|---|
| 仓库 | `mi1314cat/sing-box-core` |
| **远端 `main`** | **`1388b97`** |
| 回退前的 main | `b25f5a0`（本地留档 tag **`pre-rollback-backup`**） |
| 内容基线 | `c0a5c19`（tag `pre-three-way-interop`） |
| 推送方式 | **fast-forward**（提交的父就是 `b25f5a0`），**没有 `--force`** |
| 净变化 | 删 15 个互通文件；`share.sh` 1143 → **672 行** |
| 远端互通文件数 | **0** |

---

## 2 · 做法（与 M 那次**不同**，这里说清为什么）

M 那次是「**从回退点重建 + 挑修复**」（因为 M 的修复只有 3 条、且 2 条能干净 cherry-pick）。
SB 这次反过来 —— 「**从当前 main 出发，把互通摘掉**」。原因是**实测数据**：

> 在一次性 clone 里把 SB 的 6 条非互通修复逐个 cherry-pick 到 `c0a5c19` 上：
> **只有 1 条干净应用，5 条冲突**（冲突根因：这些修复做在互通提交**之后**，
> 文件上下文已变；而且它们改的门禁文件在回退点上根本不存在）。

所以"挑修复"在 SB 上不可行。改成**摘互通**之后，修好的东西**一个都不用挑、天然全在** ——
这也正好对上你的要求"除了互通无关的真修复进行保留"。

摘掉的东西：

```
删 15 个文件: src/conf/interop.py, src/client/lib/interop.py, src/client/compat2.py,
              src/client/lib/proxy_node_compat/**(8), src/conf/link_guard.py,
              src/conf/uri_express.py, tools/interop-e2e.sh, tools/check_compat_wiring.sh
src/conf/share.sh          ← 用 c0a5c19 做基线（单产品），再贴回它的两条真修复
src/client/client.sh       ← 摘掉 compat 适配层 + "读声明决定拉原生/普通话"决策链
src/client/to_sb.py        ← 摘掉 compat 判定层（保留转换闸门）
install.sh                 ← 摘掉 compat2 / vendored / interop.py 的安装段
tools/check_share_links.sh ← 回到 406afcc 版（去掉互通期声明断言与对角线）
```

**行为变化**：分享 token 回到**只发原生 sing-box JSON**，地址上**没有内核声明**；
客户端回到"直接拉取 + 按状态码报错"，不再有原生/普通话分派与回退链。

---

## 3 · 保留的 7 条真修复（都在远端逐条复核过）

| # | 修复 | 远端复核 |
|---|---|---|
| 1 | `4fccbc6` 分享链接不再写无效参数（hy2 去掉 `obfs=none`、vmess 改回标准）—— mihomo 遇到 `obfs` 非空却没密码会**把整条订阅判成 0 节点** | 链接模板用 `obfs_q`（未开混淆时为空）✓；`obfs=none` 只剩注释 |
| 2 | `fe47df8` hy2 带宽默认对齐 60/200 | `SB_HY2_UP_MBPS:-60` / `SB_HY2_DOWN_MBPS:-200` ✓ |
| 3 | `406afcc` 分享生成后一致性校验 + 删节点下架分享 | `sb_share_consistency_check` 4 处；动词含 `check` / `revoke-tag` ✓ |
| 4 | `45fd108` `to_sb` 三条实测缺口：**`tls.enabled` 补齐（缺了 TLS 被静默降级成明文）** / 未知传输**不再静默降级成 tcp** / ECH 只认 PEM | `"enabled": True` 10 处；`_unwritable_reason` 2 处 ✓ |
| 5 | `ba1e670` 端口探活**全量误报**（`[:]]`→`[]:]`）+ 死端口升为拒发 + `ss` 全瞎守卫 | 实际判据是 `[]:]` ✓（`[:]]` 只剩注释）；`ss_dim` 守卫 3 处 ✓ |
| 6 | `e861ab7` URI 路径**静默丢节点**（`anytls`/`socks5` 分派漏项）+ 跳过原因**必须可见** | `anytls` 10 处；`URI 协议未收录` 1 处；`转换器跳过了` 1 处 ✓ |
| 7 | `2c209b0` 里"删掉 `encryption=none` 绕行"的部分 | 保留 ✓ |

★ 其中 **4 / 5 / 6 是线上真事故的根因修复**（TLS 静默降级成明文 / `check all` 假绿 / 静默丢节点）——
回退时最容易被连带丢掉，这里逐条保留并复核。

---

## 4 · 验证

| 检查 | 结果 |
|---|---|
| `bash tools/check_share_links.sh --no-gen` | **结果: [OK] 全部通过**，exit 0 |
| 功能冒烟：`to_sb.py` 直读含三种"坏形态"的订阅 | `共=3 成功=1 跳过=2`：`anytls://` **转换成功**；`naive+https` → `URI 协议未收录`（**可见**）；`xhttp` → `本转换器不会写 transport 'xhttp' —— 明确拒绝, 不静默降级成 tcp`；`#` 注释行**未被计数**（共=3 而非 4） |
| 沙箱跑部署态 `share.sh check` | `[OK] 分享内容与真实配置一致`，RC=0。（本机 `ss` 是瞎的，正好验到 `ba1e670` 的守卫：明确告警"探活跳过"并 fail-open） |
| 全仓库残留互通引用 | **0**（只剩两处说明性注释） |
| 外部契约 | `share.sh` 动词表 `create / create-all / regen-aggregate / list / check / revoke-tag / del / toggle / regen` 与 `lib.sh` 的调用（`sb_regen_aggregate`、`revoke-tag`）一致 |

---

## 5 · 凭据处理

用户提供**一次性** PAT，按本项目一贯做法：**临时 askpass + token 只放临时文件（`umask 077`）
→ `GIT_ASKPASS=… git push` → `shred -u`**。**没有写进 `git config`，也没有写进仓库任何文件**；
推送后两个临时文件已 `shred -u` 并复查 `/tmp` 无残留。

---

## 6 · 本地留档（`/root/deepseek/repos/sing-box-core`）

```
tag    pre-rollback-backup   → b25f5a0   回退前那条 main（随时可回）
tag    pre-three-way-interop → c0a5c19   互通前的最后一个版本
branch rollback/pre-interop  → 1388b97   = 远端 main（同名提交）
（本地 main 已对齐到 1388b97）
```

---

## 7 · UNKNOWN / 代价（没做、要知道的）

1. **门禁覆盖有损失**：删掉的 `tools/check_compat_wiring.sh` 里，有两段断言**测的是真修复**而不
   只是互通 —— 8e 段（端口探活：在听/没在听/ss 全瞎三种）与 8f 段（`URI_RE` 的每个 scheme
   都要能被分派转换、未收录 scheme 必须可见）。**它们跟着互通门禁一起没了**。
   建议：把这两段移植到一个非互通的门禁里（例如 `tools/check_share_links.sh`）——**本轮未做**。
2. **线上 RN 的部署态没换**：本次只改 GitHub。所以"换回旧版之后已发出的带声明分享地址会怎样"
   **没有实测**。要把回退版生效到线上，得再分发到 RN + 重跑验收 —— 另一件事。
3. **X 内核没动**（用户只要求 M 与 SB）。`xray--core` 仍在 `957e603`（含互通）。
