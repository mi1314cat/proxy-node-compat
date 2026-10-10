# X 内核部署侧：待查/待修清单（用户 2026-10-10 提出）

> 记录用。**未擅自修改任何脚本**。每条都标注：现象 → 证据 → 归属（脚本问题 / 测试期现象 / 设计如此）→ 状态。

## K1 · ECH 留空（`ech-opts.enable: true` 但没有静态 `config`）

- **现象**：mihomo 侧 5 个 CDN 客户端片段的 `ech-opts` 只写了 `enable: true`，没有 `config`。
- **实测后果**（`research/assessment/mihomo-singbox-quality.md` §1）：客户端 DNS 不返回 HTTPS(type 65) 记录时**硬失败** ——
  `resolve ECH config error: no ECH config found in DNS records`；受控实验 WS+ECH **3/3 FAIL**、gRPC+ECH **2/2 FAIL**；
  去掉 ECH 后立刻 PASS（1.09–1.41 MB/s）。
- **用户说明**：ECH 位置**可能是留给自己的 Cloudflare**（用 DNS 动态获取 ECHConfig），
  **不确定是当时测试期的问题还是脚本本身的缺陷**。
- **归属**：**未判定**（设计如此 vs 脚本缺陷）。
- **状态**：⏸ 待查 —— 不改动。需要确认：线上客户端的 DNS 是否会返回该域名的 HTTPS(type 65) 记录。
  若会返回 → 当前写法是对的（动态 ECH）；若不返回 → 应补静态 `config`（用户提到的那份 ECHConfig 已实测存在）。
- **注意**：sing-box 侧的要求不同（`tls.ech.config` 要 **PEM**，喂 base64 会 FATAL）—— 即使补 config，两个内核也要各写各的格式。

## K2 · X 分享链接里是 WARP 出口 IP 而不是服务器入口 IP

- **现象**：Reality 分享链接的地址是 `104.28.201.80`（`install_info.env` 里的 Cloudflare/WARP 出口 IP）。
- **实测**：该地址 25000 端口 **CLOSED/FILTERED**、curl 15s 超时；换 `107.173.154.178:25000` 通。
- **用户线索**：**参考 SB 的做法 —— SB 是从网卡上取地址的**。
- **归属**：脚本问题（取错了地址来源）。
- **状态**：🔧 待修 —— 待与 SB 的实现对照后再改（见下一条任务）。
- **影响面**：生产 `reality-share-01/03` 同病 → 链接发出去即死。

## K3 · 生产 `vless-xhttp-01/02/03` 三条死链

- **现象**：片段只绑 `127.0.0.1`，且分享链接端口（25333/26906/22168）与片段实际端口（45630/31722/41721）不符。
- **状态**：🔧 待修。

## K4 · `gen_psk` 未定义 → 一键全协议永远生成不出 SS2022

- **现象**：`Shadowsocks.sh:232: gen_psk: command not found` → `PSK 长度错误：2022-blake3-aes-256-gcm 需要 32 字节 (获得 0 字节)`。
- **根因**：`gen_psk` 在被 `1ef13f2`「删 317 行重复实现」时删掉，调用点遗留。
- **加重项**：**batch 仍以退出码 0 结束** → 失败被完全掩盖。
- **状态**：🔧 待修（一行函数 + 退出码）。

## K5 · 待答问题（用户提问，等待验证后回答）

1. X 内核的 **HY2 协议支持端口跳跃（port hopping）和混淆（obfs）吗？**
2. X 的节点绑定的**回环地址**是走 CDN 吗？是**通过 Nginx 转发**的吗？
3. **我们这套 Nginx 转发有没有问题？**（用户观察：SB 和 M 都能"很完美地直接配置 Nginx、删除也不影响其他"）
