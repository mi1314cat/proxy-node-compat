# M 客户端接入 proxy-node-compat · 本地双跑台原始输出

生成: 2026-10-10T23:58:47+08:00 ｜ 仓库 5467278

```
$ MIHOMO_BIN=<真内核桩> python3 tools/nodecompat-compare.py
   syn:smux                       旧=SUPPORTED            compat=SUPPORTED_WITH_LOSS  合并=SUPPORTED_WITH_LOSS  三方 mux 不同构（Xray=mux.cool / mihomo=smux / sing-box=multiplex），跨内核搬运无法保证语义一致；Xray 官方文档明确「使用 XHTTP 时不要启用 mux.cool」; vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效; mux 在三个内核里不是同一个东西；Xray 建议用 XHTTP 自带的多路复用（xhttpSettings.extra.xmux）而不是 mux.cool
   syn:flow                       旧=SUPPORTED            compat=SUPPORTED_WITH_WARNING 合并=SUPPORTED_WITH_WARNING 运行期条件 client_fingerprint_present 由节点自身显式字段满足: standard:reality.fingerprint=chrome（provenance=MIHOMO_YAML） —— 客户端导入时必须写进配置, 否则仍会运行期失败
   syn:unknown-network            旧=SUPPORTED            compat=SUPPORTED_WITH_WARNING 合并=SUPPORTED_WITH_WARNING vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效
   syn:vmess                      旧=SUPPORTED            compat=SUPPORTED_WITH_WARNING 合并=SUPPORTED_WITH_WARNING vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效
   syn:hy2                        旧=SUPPORTED            compat=SUPPORTED_WITH_WARNING 合并=SUPPORTED_WITH_WARNING vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效
   syn:tuic                       旧=SUPPORTED            compat=SUPPORTED_WITH_WARNING 合并=SUPPORTED_WITH_WARNING vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效
   syn:anytls                     旧=SUPPORTED            compat=SUPPORTED_WITH_WARNING 合并=SUPPORTED_WITH_WARNING vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效

── 回退旧判定 (compat 无确定结论) (6) ──
   syn:bad-type                   旧=UNSUPPORTED          compat=UNKNOWN              合并=UNSUPPORTED          vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效
   syn:snell                      旧=SUPPORTED_WITH_LOSS  compat=UNKNOWN              合并=SUPPORTED_WITH_LOSS  vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效
   syn:wireguard                  旧=SUPPORTED_WITH_LOSS  compat=UNKNOWN              合并=SUPPORTED_WITH_LOSS  有 1 个字段内核会静默忽略（导入时已剔除）: private-key
   syn:ssh                        旧=SUPPORTED            compat=UNKNOWN              合并=SUPPORTED            
   syn:mieru                      旧=SUPPORTED            compat=UNKNOWN              合并=SUPPORTED            
   syn:shadow-tls                 旧=UNSUPPORTED          compat=UNKNOWN              合并=UNSUPPORTED          mihomo 核心不支持该协议类型 shadow-tls

── 保险丝在起作用: compat 想放宽、被挡回旧判定 (fuse_fired) (1) ──
   syn:malformed                  旧=UNSUPPORTED          compat=SUPPORTED_WITH_WARNING 合并=UNSUPPORTED          vmess/vless 只有 servername；trojan/hysteria2/tuic/anytls 只有 sni —— 写错不报错只静默失效

── 信息: compat 比旧判定宽 7 条 ──
   两个引擎量的不是同一件事: 旧判定有一维 compat 按设计不管 ——
   字段名的对错 (trojan 写 servername 会被内核静默忽略)。
   这类差异不参与判定, 只由"取更差者"保留旧判定的保守结论。

═══ 结论 ═══
  语料 60 条: 收紧 44 | 回退旧判定 6 | 一致 10
  relaxed    : 0   <- 旧判定要剔除、合并后却能用: 必须 0
  fuse_fired : 1   期望 1  ✅
  字段完整   : ✅
  判定引擎  : compat

```

```
$ python3 tests/test_nodecompat.py
  [32m✓[0m 结果携带 compat.losses
  [32m✓[0m 结果携带 compat.unknowns
  [32m✓[0m 结果携带 compat.extensions
  [32m✓[0m 结果携带 compat.raw_uri
  [32m✓[0m 结果携带 compat.warnings
  [32m✓[0m 结果携带 compat.reason_codes
  [32m✓[0m 结果携带 compat.levels
  [32m✓[0m 结果携带 compat.rules_applied
  [32m✓[0m 结果携带 compat.evidence
  [32m✓[0m 结果携带 compat.detected_features
  [32m✓[0m 结果携带 compat.raw_fields
  [32m✓[0m 内核不认的键进了 extensions（不变式 I2）: ['some-key-the-kernel-ignores.nested', 'udp', 'ws-opts.path']
  [32m✓[0m 原始字典整份进 raw_fields
  [32m✓[0m NodeProfile 不变量自检: []
  [32m✓[0m 序列化往返无损（不静默丢信息）

[1mE. 一键回滚[0m
  [32m✓[0m MH_COMPAT_ENGINE=legacy: compat 完全不参与
  [32m✓[0m 回滚后判定 == 旧判定（SUPPORTED）
  [32m✓[0m 别名 XBD_COMPAT_ENGINE=legacy 同样生效
  [32m✓[0m 去掉环境变量后 compat 恢复参与

[1mF. 真探测（不写死、不猜）[0m
  [32m✓[0m 版本/发行版来自 `mihomo -v`: 1.19.32 / upstream
  [32m✓[0m build tags 来自内核输出: ['with_gvisor']
  [32m✓[0m 探测不到就是 None（不是 '默认支持'）
  [32m✓[0m 版本未知时版本无关的规则照常判定（vless+ws+tls = SUPPORTED_WITH_WARNING）
  [32m✓[0m 版本无关的组合规则在版本未知时仍然报出损失（ws × reality）
  [32m✓[0m 版本未知时版本相关的规则记入 unknowns（不是默认支持）
  [32m✓[0m 版本未知且无确定结论 → 退回旧判定（SUPPORTED）

[1mG. mihomo 上不产生假 UNSUPPORTED[0m
  [32m✓[0m 全协议扫描 756 个组合
  [32m✓[0m compat 多判出的 UNSUPPORTED: 0 个 []

[1mI. 分享链接通路（parse_uri, 保真最高）[0m
  [32m✓[0m raw_uri 与输入逐字节一致（不变式 I1）
  [32m✓[0m 分享链接: 旧判定不表态(交给内核), 结论全部来自 compat
  [32m✓[0m 分享链接里 network=kcp 的静默降级被抓到（['mihomo 无 mkcp 实现；network']）
  [32m✓[0m 未收录 scheme 的链接 → compat 判 UNKNOWN → 退回旧判定（不误剔）
  [32m✓[0m hysteria2 链接被判为可用（不是不支持）

[1mH. 语料双跑[0m
  [32m✓[0m nodecompat-compare.py 退出码 0
  [32m✓[0m 语料 relaxed = 0（无静默放宽）
  [32m✓[0m 保险丝触发次数与期望一致（fuse_fired : 1   期望 1  ✅）
  [32m✓[0m 语料非空

[1m结果[0m
  [32m49 通过[0m / [31m0 失败[0m
```

```
$ python3 src/lib/nodecompat.py kernel（真探测; CC/RN 上是真内核输出）
{
 "probe": {
  "version": "1.19.32",
  "distribution": "upstream",
  "build_tags": [
   "with_gvisor"
  ],
  "raw": "Mihomo Meta v1.19.32 linux arm64 with go1.26.8 Wed Sep 30 16:55:22 UTC 2026",
  "probed": true
 },
 "target": {
  "kernel": "mihomo",
  "distribution": "upstream",
  "version": "1.19.32",
  "build_tags": [
   "with_gvisor"
  ],
  "platform": null,
  "runtime_options": {},
  "evaluated_at": null
 }
}
```

```
$ 全协议扫描: 21 协议 × 9 传输 × 4 安全层 = 756 组合
SUPPORTED_WITH_LOSS 672 / UNKNOWN 168 / UNSUPPORTED 0（compat 多判 = 0）
```
