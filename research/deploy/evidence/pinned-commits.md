# 本轮分发钉死的 commit 与冻结快照

分发**不用 HEAD**（HEAD 会动），也不碰工作区 —— 全部用 `git archive` 从 commit 取冻结快照。

| 内核 | 仓库 | commit | 说明 |
|---|---|---|---|
| X | `xray--core` | `be4ec8e` | 三家互通 服务端+客户端+门禁（`da5fff0` → `32f65ef` → `be4ec8e`，本轮 fast-forward 合入 `main`） |
| M | `mihomo--core` | `c446d3f` | 三家互通 服务端+客户端（后续 `44fc269` 修 `parse_declaration` 形态判据） |
| SB | `sing-box-core` | `a7150e2` | 三家互通 服务端+客户端（后续 `5ed6206` / `6f23d65` / `d8b41c1`） |

冻结快照（`git archive --format=tar.gz`）：

```
x-head.tar.gz   sha256 ec12277a6b5f3facf4a36c474b0454c8b3c6025fa49efd21cfa1143913befa37   57 项   conf/ xray-panel.sh
m-head.tar.gz   sha256 2ffac93a6f29967896450b0aad4b02db69174dd7bd996794b7969a42634fc204   59 项   src/
sb-head.tar.gz  sha256 d934ab553a00b4d8460f0d7f6d7db28ecd4a400be1f3be615f224147223a5a60   56 项   src/conf src/sing-box.sh install.sh src/client
```

分发脚本：`research/deploy/tools/rn-deploy.sh`（先备份 → 列差异 → 落盘 → 逐字节复核 →
断言四个服务 PID 未变）。tarball 本身不入库（`.gitignore` 排除 `research/deploy/evidence/stage/`），
用上面三个 commit 随时可重放。
