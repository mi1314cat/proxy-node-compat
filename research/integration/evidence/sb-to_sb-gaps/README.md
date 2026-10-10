# 证据索引：SB 客户端 `to_sb.py` 三条缺口（M→SB 那一格）

> 对应报告：`research/integration/sb-to_sb-three-gaps.md` ｜ 代码：`sing-box-core` commit `45fd108`（本地，未推）
> 原始实验目录是 `/tmp/sbgap`（本机）与 CC `/tmp/cc-sbgap`，验收后已按纪律清理；这里是压缩后的存档。

## 载荷与内核

- 载荷：`research/e2e/evidence/3x3/payloads/p-m-surrogate.yaml`
  （6312 B / sha256 `08d847fe84a274b05593ed08502e1b2c4fd50162c67276cf1d47eb04fd5fc88a` / 19 节点，
  与九宫格 M→SB 那格用的是同一份 RN 上 M 的真实分享载荷）
- 内核：`sing-box 1.14.2`（amd64 取自 RN `/root/catmi/sing-box/sing-box`，sha256 `fc9c6e6ab345f045b16a0ed10d1ff28d68e8e56e7749fca30738d1406e98d7b8`；
  CC 用本机 `/opt/sb-client/core/sing-box` 1.14.2 aarch64）

## 文件

| 文件 | 内容 |
|---|---|
| `pre-outbounds.json` / `pre-report.json` | 改前（HEAD `2c209b0`）转换产物 / compat 报告：18 条出站，**每条 `tls` 都没有 `enabled`**，3 条 xhttp 节点 `"transport": null` |
| `post-outbounds.json` / `post-report.json` | 改后产物 / compat 报告：15 条出站，全部 `tls.enabled=true`，xhttp 由 compat 判死（`KERNEL_NEVER_SUPPORTED`），ECH 节点带 `standard:ech` 转换损失声明 |
| `pre-realconn.json` / `pre-realconn.log` | 改前真连（本机 xiaomi，逐节点隔离实例）：**0/18** |
| `post-realconn.json` / `post-realconn.log` | 改后真连（本机）：11/15（多出的 2 条 QUIC 失败是本机 TUN 环境：`invalid IPTOS size`） |
| `cc-pre.res` / `cc-pre.log` | 改前真连（CC，参考客户端机）：导入 18、check rc=1、**真连 0/18** |
| `cc-post.res` / `cc-post.log` | 改后真连（CC）：导入 15、check rc=0、**真连 13/15**（出口 104.28.201.80；剩 2 条 CDN gRPC 403，mihomo 侧同样不通） |
| `probe-anytls.json.res` | 单条修好的 anytls 直连探针（证明"缺 enabled"就是那一条）：204 + 104.28.201.80 |
| `tr-xhttp.json` / `tr-foobar.json` | 内核探针：`{"type":"xhttp"}` / 未知名 → `FATAL decode: unknown transport type`（所以绝不能硬造 transport） |
| `tr-httpupgrade.json` | 内核探针：`{"type":"httpupgrade","path":…,"host":…}` → rc=0（内核支持；转换器暂不写 ⇒ 现在是明确拒绝） |
| `ech-b64.json` / `ech-pem.json` / `tls-noenabled.json` | 内核探针：base64 ECH → `FATAL invalid ECH configs pem`；PEM → rc=0；vless 的 `tls:{server_name}`（无 enabled）**静默通过**（tls 段被忽略） |
| `gate-22-0.txt` | `bash tools/check_compat_wiring.sh` 全量输出：**通过 22 / 失败 0**（改前 19/0） |

## 复现命令

```bash
# 转换（改后代码）
python3 sing-box-core/src/client/to_sb.py p-m-surrogate.yaml --prefix e2e --compat-report r.json > out.json
# 逐节点真连（204 + 出口 IP 必须 104.28.x.x 才算成功）
python3 realconn.py out.json result.json          # SB_BIN=<sing-box 1.14.2>
# 门禁
bash sing-box-core/tools/check_compat_wiring.sh   # 22 / 0
```
