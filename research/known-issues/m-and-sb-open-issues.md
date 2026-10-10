# M / SB 内核：待修问题清单（跨内核 E2E 实测发现）

> 来源：`research/e2e/share-link-cross-kernel.md`（327 行，每格带命令与原文）。
> 基线通过数（同一 mihomo harness / 真内核实测）：**M 19/19** ✅ · **SB 13/13** ✅ · **X 1/5** ❌ · M 的 URL 链接 3/12。
> 状态：这些都在 `mihomo--core` / `sing-box-core` 里，**当前没有这两个仓库的推送权限**，故先记录，拿到 token 再修。

## P-M1（严重）· M 的分享订阅生成 **100% 失败** —— 疑似我们自己的旗帜特性引入的回归

- **现象**：面板 `[Error] 生成分享内容失败 (没有可分享的节点?)`；`share_gen_tag_auto all` 返回 `0 0`；
  `build_sub.py` 日志 `[清理] 剔除了 19 个陈旧产物` + `[ERR] 没有任何可用节点`。
- **根因**：`live_node_names()` 用 `.managed.json` 的**裸名**（`mAnyTLS01-TLS`）去**等值匹配** `out/*_client-*.yaml`
  的**带旗帜名**（`🇺🇸 mAnyTLS01-TLS`）→ **交集 0/19**。
- **时间线**：旗帜命名特性 **10-09 21:20 上线**，此前的分享生成是否正常**无历史日志可查（UNKNOWN）**。
- **影响**：M 的分享功能整体不可用 → 用户拿不到新订阅。

## P-M2（严重）· 已发出的分享内容**永久冻结在陈旧快照**

- 内容 232B，指向 `@107.173.154.178:20000`，而**该端口无人监听**（真实监听 25684）。
- `share_refresh_all` 因 P-M1 **永远刷不动** → 用户手上的订阅是死的且无法自愈。
- UNKNOWN：232B 快照里 `port 20000` 的来源（现盘上没有，只存在于 10-07 备份）。

## P-M3 · M 的 URL 链接产物 12 条里 10 条端口无人监听

50877 / 21168 / 23512 / 22737 / 42099 / 56676 / 38899 / 23451 等 —— 与 X 的"死链"**同后果、不同成因**（陈旧产物，非端口算错）。

## P-M4 · M 客户端**不吃自家 URL 链接**

`out/*_share-*.txt` 喂给 M 官方客户端报：`[ERR] 不是合法的 Mihomo 订阅 (需要顶层 proxies: 列表)`。
→ 这些产物对 M 自己没用（SB 侧无此问题：分享内容 = 客户端产物 `cp`，字节一致）。

## 生态共有 · 硬编码 `obfs=none` 会让**整条订阅归零**

- 三家全中：X（已修）、**M 6 条**（`hysteria2_share-01/02/10/11` 等）、**SB 1 条**（`sb_share-hysteria201-TLS`）。
- mihomo 原文：`initial proxy provider t error: proxy 0 error: missing obfs password` → **provider 0 节点**。
- **最狠的一点**：M 的「1 条坏 hy2 + 8 条好链接」放同一订阅 → **整条订阅 0 节点，好节点一起消失**。
- 修法：链接里**不要写** `obfs=none`（不写即无混淆）；SB 侧照 X 的做法删掉该参数。
- UNKNOWN：非 mihomo 客户端（如 sing-box）遇到 `obfs=none` 是否同样失败。

## 参照实现（SB 值得直接抄的一条）

公网 CA 不写 pin，SB 的判据一句话：

```sh
[[ "$CERT_TRUSTED" == "false" ]] && pin=…
```

M 的做法也对：pin 只出现在自签节点（`mHysteria202-TLS`，`sni=www.amazon.com`），
真证书节点与**全部 CDN 节点零 pin**。

## 附：X 侧对照结论（供修 M 时参照）

| 问题 | X | M | SB |
|---|---|---|---|
| 分享层丢 SNI | ❌ 有 | ✅ 无 | ✅ 无 |
| CDN 端口/目标不一致 | ❌ 有 | ⚠️ 陈旧产物 | ✅ 无 |
| 公网 CA 也 pin | ❌ 有 | ✅ 无 | ✅ 无 |
| 客户端解析丢 reality 参数 | ❌ 有（`xbd parse_trojan`） | ✅ 无 | ✅ 无 |
| 硬编码 `obfs=none` | ❌ 有（已修） | ❌ 有 | ❌ 有 |
