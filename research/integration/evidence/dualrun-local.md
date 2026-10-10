# 双跑对比 —— 语料 53 条；目标 kernel=xray version=26.3.27 distribution=upstream
# runtime_options={'mux_cool': True}

| 节点 | 协议/传输/安全 | 旧判定 | compat | 合并 | 来源 | reason_codes | 多判出的 |
|---|---|---|---|---|---|---|---|
| 🇺🇸 | hysteria2/quic/tls | SUPPORTED | UNKNOWN | SUPPORTED_WITH_WARNING | compat（总状态 UNKNOWN，但该结论是确定的） | UNKNOWN_CAPABILITY | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:UNKNOWN_CAPABILITY; ext:upmbps,downmbps,obfs |
| 🇺🇸 | hysteria2/quic/tls | SUPPORTED | UNKNOWN | SUPPORTED_WITH_WARNING | compat（总状态 UNKNOWN，但该结论是确定的） | UNKNOWN_CAPABILITY | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:UNKNOWN_CAPABILITY; ext:upmbps,downmbps,obfs |
| 🇺🇸 | hysteria2/quic/tls | SUPPORTED | UNKNOWN | SUPPORTED_WITH_WARNING | compat（总状态 UNKNOWN，但该结论是确定的） | UNKNOWN_CAPABILITY | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:UNKNOWN_CAPABILITY; ext:upmbps,downmbps,obfs |
| 🇺🇸 | hysteria2/quic/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; ext:obfs,obfs-password |
| 🇺🇸 | hysteria2/quic/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; ext:pin,upmbps,downmbps,obfs |
| hy3 | hysteria2/quic/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; ext:mport |
| hy3 | hysteria2/quic/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; ext:mport |
| 🇺🇸 | shadowsocks/tcp/none | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| 🇺🇸 | trojan/websocket/reality | NOT_SUPPORTED | UNSUPPORTED | NOT_SUPPORTED | compat | SEMANTIC_MISMATCH | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:SEMANTIC_MISMATCH |
| 🇺🇸 | trojan/websocket/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| 🇺🇸 | trojan/tcp/reality | NOT_SUPPORTED | SUPPORTED_WITH_LOSS | NOT_SUPPORTED | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| TrojanReality | trojan/grpc/reality | NOT_SUPPORTED | SUPPORTED_WITH_LOSS | NOT_SUPPORTED | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| h.example | trojan/tcp/reality | NOT_SUPPORTED | SUPPORTED_WITH_LOSS | NOT_SUPPORTED | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| h.example | trojan/tcp/reality | NOT_SUPPORTED | SUPPORTED_WITH_LOSS | NOT_SUPPORTED | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| 🇺🇸 | vless/tcp/reality | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | RUNTIME_CONDITION_NOT_MET | 丢:standard:mux,standard:flow,standard:mux.enabled,standard:mux.protocol; 码:RUNTIME_CONDITION_NOT_MET |
| VLESSmKCPSeedWG | vless/mkcp/none | SUPPORTED | UNSUPPORTED | NOT_SUPPORTED | compat | KERNEL_REMOVED | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:KERNEL_REMOVED |
| VLESSmKCPSeed | vless/mkcp/none | SUPPORTED | UNSUPPORTED | NOT_SUPPORTED | compat | KERNEL_REMOVED | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:KERNEL_REMOVED |
| 🇺🇸 | vless/websocket/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| 🇺🇸 | vless/websocket/reality | NOT_SUPPORTED | UNSUPPORTED | NOT_SUPPORTED | compat | SEMANTIC_MISMATCH | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:SEMANTIC_MISMATCH |
| 🇺🇸 | vless/tcp/reality | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | RUNTIME_CONDITION_NOT_MET | 丢:standard:mux,standard:flow,standard:mux.enabled,standard:mux.protocol; 码:RUNTIME_CONDITION_NOT_MET |
| 🇺🇸 | vless/tcp/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| vless-tcp-tls | vless/tcp/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| vless-xtls-legacy | vless/tcp/xtls | NOT_SUPPORTED | UNKNOWN | NOT_SUPPORTED | compat（总状态 UNKNOWN，但该结论是确定的） | UNKNOWN_CAPABILITY | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:UNKNOWN_CAPABILITY; ext:sni |
| vless-h2-removed | vless/h2/tls | NOT_SUPPORTED | UNSUPPORTED | NOT_SUPPORTED | compat | KERNEL_REMOVED | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:KERNEL_REMOVED |
| vless-http-removed | vless/h2/tls | NOT_SUPPORTED | UNSUPPORTED | NOT_SUPPORTED | compat | KERNEL_REMOVED | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:KERNEL_REMOVED |
| vless-quic-removed | vless/quic/tls | NOT_SUPPORTED | SUPPORTED_WITH_LOSS | NOT_SUPPORTED | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| vless-mkcp-header-seed | vless/mkcp/none | SUPPORTED | UNSUPPORTED | NOT_SUPPORTED | compat | KERNEL_REMOVED | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:KERNEL_REMOVED |
| vless-mkcp-plain | vless/mkcp/none | SUPPORTED | UNSUPPORTED | NOT_SUPPORTED | compat | KERNEL_REMOVED | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:KERNEL_REMOVED |
| vless-ws-reality | vless/websocket/reality | NOT_SUPPORTED | UNSUPPORTED | NOT_SUPPORTED | compat | SEMANTIC_MISMATCH | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:SEMANTIC_MISMATCH |
| vless-xhttp-reality | vless/xhttp/reality | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | SEMANTIC_MISMATCH | 丢:standard:mux,standard:mux,standard:mux.enabled,standard:mux.protocol; 码:SEMANTIC_MISMATCH |
| vless-grpc-reality | vless/grpc/reality | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| vless-flow-no-tls | vless/tcp/none | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | RUNTIME_CONDITION_NOT_MET | 丢:standard:mux,standard:flow,standard:mux.enabled,standard:mux.protocol; 码:RUNTIME_CONDITION_NOT_MET |
| vless-xhttp-mux | vless/xhttp/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | SEMANTIC_MISMATCH | 丢:standard:mux,standard:mux,standard:mux.enabled,standard:mux.protocol; 码:SEMANTIC_MISMATCH |
| vless-xhttp-streamup | vless/xhttp/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | SEMANTIC_MISMATCH | 丢:standard:mux,standard:mux,standard:mux.enabled,standard:mux.protocol; 码:SEMANTIC_MISMATCH |
| vless-xhttp-ech | vless/xhttp/tls | SUPPORTED | UNKNOWN | SUPPORTED_WITH_WARNING | compat（总状态 UNKNOWN，但该结论是确定的） | SEMANTIC_MISMATCH | 丢:standard:mux,standard:mux,standard:ech.query_server_name,standard:mux.enabled,standard:mux.protocol; 码:SEMANTIC_MISMATCH; ext:ech_declared |
| vless-unknown-transport | vless/magic-transport/tls | NOT_SUPPORTED | UNKNOWN | NOT_SUPPORTED | compat（总状态 UNKNOWN，但该结论是确定的） | UNKNOWN_CAPABILITY | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:UNKNOWN_CAPABILITY; ext:type |
| vless-unknown-params | vless/tcp/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; ext:someNewParam,evilField |
| vless-fp-flow | vless/tcp/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | RUNTIME_CONDITION_NOT_MET | 丢:standard:mux,standard:flow,standard:mux.enabled,standard:mux.protocol; 码:RUNTIME_CONDITION_NOT_MET |
| vless-bad-fp | vless/tcp/tls | NOT_SUPPORTED | SUPPORTED_WITH_LOSS | NOT_SUPPORTED | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| vless-allow-insecure | vless/tcp/tls | SUPPORTED_WITH_WARNING | UNKNOWN | SUPPORTED_WITH_WARNING | compat（总状态 UNKNOWN，但该结论是确定的） | UNKNOWN_CAPABILITY | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; 码:UNKNOWN_CAPABILITY |
| trojan-tls | trojan/tcp/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| trojan-reality | trojan/tcp/reality | NOT_SUPPORTED | SUPPORTED_WITH_LOSS | NOT_SUPPORTED | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| trojan-ws | trojan/websocket/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| ss-plain | shadowsocks/tcp/none | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| ss2022 | shadowsocks/tcp/none | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| ss-plugin | shadowsocks/tcp/none | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; ext:plugin |
| hy2-plain | hysteria2/quic/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| hy2-obfs | hysteria2/quic/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; ext:obfs,obfs-password |
| hy2-pin | hysteria2/quic/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol |
| hy2-mport | hysteria2/quic/tls | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux,standard:mux.enabled,standard:mux.protocol; ext:mport |
| socks-simple | socks/tcp/none | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux |
| socks-auth | socks/tcp/none | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux |
| http-simple | http/tcp/none | SUPPORTED | SUPPORTED_WITH_LOSS | SUPPORTED_WITH_WARNING | compat | - | 丢:standard:mux |

## 客户端不支持导入（不是判定差异）: 14 条
    - 客户端不支持导入该 scheme: anytls://6f1addc6af5a11c1b535b1ce1b06490a@107.173.154.178:50877?sni=cloudflare.c
    - 客户端不支持导入该 scheme: anytls://d3cc09aa867186e5887515fcc95d8628@107.173.154.178:22812?sni=www.apple.co
    - 客户端不支持导入该 scheme: anytls://f537cd201a21c199f874f254f9ac6c8b@107.173.154.178:28725?sni=hxicc.catmic
    - 客户端不支持导入该 scheme: anytls://g4RoPGzW3QLIHJNPgS8CoVB1@107.173.154.178:31013?sni=apache.org&insecure=
    - 客户端不支持导入该 scheme: anytls://pass@example.com:443?sni=a.com&zzz=3#a1
    - 客户端不支持导入该 scheme: anytls://tjO9yFXg2zSmMh2ejDe6AZ0v@107.173.154.178:31002?sni=hxicc.catmicos.dpdns
    - 客户端不支持导入该 scheme: tuic://0891ed4d-491c-407b-92ff-5ad27c2e5336:9e874ff1faa7a0ff642af541b4fffc53@107
    - 客户端不支持导入该 scheme: tuic://ab93a62d-99f2-41c2-9a95-df3c82edd3e9:2aac4f1ed898b9fc1f5e9992@[2001:470:c
    - 客户端不支持导入该 scheme: tuic://f803e8bd-e20a-4487-9db9-bc686ee3511d:db554c9a63d4b7e62dfdc2fc@107.173.154
    - 客户端不支持导入该 scheme: vmess://eyJhZGQiOiJoeGljYy5jYXRtaWNvcy5kcGRucy5vcmciLCJwb3J0IjoiNDQzIiwidXVpZCI6
    - 客户端不支持导入该 scheme: tuic://u:p@a.example:443?sni=a.example&congestion_control=bbr#tuic
    - 客户端不支持导入该 scheme: anytls://pw@a.example:443?sni=a.example&fp=chrome#anytls
    - 客户端不支持导入该 scheme: wireguard://x@a.example:51820#unknown-scheme
    - 客户端不支持导入该 scheme: vmess://eyJhZGQiOiJhLmV4YW1wbGUiLCJwb3J0IjoiNDQzIiwidXVpZCI6InUiLCJuZXQiOiJ3cyIs

## 分类
- **same**: 15
- **tightened**: 38
    - 🇺🇸 [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']  原因码=['UNKNOWN_CAPABILITY']
    - 🇺🇸 [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']  原因码=['UNKNOWN_CAPABILITY']
    - 🇺🇸 [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']  原因码=['UNKNOWN_CAPABILITY']
    - 🇺🇸 [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']
    - 🇺🇸 [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']
    - hy3 [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']
    - hy3 [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']
    - 🇺🇸 [shadowsocks/tcp/none] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.protocol.shadowsocks', 'xray.mux.semantics']
    - 🇺🇸 [trojan/websocket/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.support.transport_ws', 'xray.protocol.trojan', 'xray.mux.semantics']
    - 🇺🇸 [vless/tcp/reality] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.combo.reality_transports', 'xray.support.flow', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.vless.encryption', 'xray.combo.flow_without_tls']  原因码=['RUNTIME_CONDITION_NOT_MET']
    - VLESSmKCPSeedWG [vless/mkcp/none] SUPPORTED → NOT_SUPPORTED  规则=['xray.mkcp.header_seed', 'xray.protocol.vless', 'xray.mux.semantics']  原因码=['KERNEL_REMOVED']
    - VLESSmKCPSeed [vless/mkcp/none] SUPPORTED → NOT_SUPPORTED  规则=['xray.mkcp.header_seed', 'xray.protocol.vless', 'xray.mux.semantics']  原因码=['KERNEL_REMOVED']
    - 🇺🇸 [vless/websocket/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.support.transport_ws', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.vless.encryption']
    - 🇺🇸 [vless/tcp/reality] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.combo.reality_transports', 'xray.support.flow', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.vless.encryption', 'xray.combo.flow_without_tls']  原因码=['RUNTIME_CONDITION_NOT_MET']
    - 🇺🇸 [vless/tcp/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.vless.encryption']
    - vless-tcp-tls [vless/tcp/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.protocol.vless', 'xray.mux.semantics']
    - vless-mkcp-header-seed [vless/mkcp/none] SUPPORTED → NOT_SUPPORTED  规则=['xray.mkcp.header_seed', 'xray.protocol.vless', 'xray.mux.semantics']  原因码=['KERNEL_REMOVED']
    - vless-mkcp-plain [vless/mkcp/none] SUPPORTED → NOT_SUPPORTED  规则=['xray.mkcp.header_seed', 'xray.protocol.vless', 'xray.mux.semantics']  原因码=['KERNEL_REMOVED']
    - vless-xhttp-reality [vless/xhttp/reality] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.combo.reality_transports', 'xray.support.xhttp', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.combo.xhttp_muxcool']  原因码=['SEMANTIC_MISMATCH']
    - vless-grpc-reality [vless/grpc/reality] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.combo.reality_transports', 'xray.support.transport_grpc', 'xray.protocol.vless', 'xray.mux.semantics']
    - vless-flow-no-tls [vless/tcp/none] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.flow', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.combo.flow_without_tls']  原因码=['RUNTIME_CONDITION_NOT_MET']
    - vless-xhttp-mux [vless/xhttp/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.xhttp', 'xray.support.tls', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.combo.xhttp_muxcool']  原因码=['SEMANTIC_MISMATCH']
    - vless-xhttp-streamup [vless/xhttp/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.xhttp', 'xray.support.tls', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.combo.xhttp_muxcool']  原因码=['SEMANTIC_MISMATCH']
    - vless-xhttp-ech [vless/xhttp/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.ech.config_lax', 'xray.support.xhttp', 'xray.support.tls', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.combo.xhttp_muxcool']  原因码=['SEMANTIC_MISMATCH']
    - vless-unknown-params [vless/tcp/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.protocol.vless', 'xray.mux.semantics']
    - vless-fp-flow [vless/tcp/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.support.flow', 'xray.protocol.vless', 'xray.mux.semantics', 'xray.combo.flow_without_tls']  原因码=['RUNTIME_CONDITION_NOT_MET']
    - trojan-tls [trojan/tcp/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.protocol.trojan', 'xray.mux.semantics']
    - trojan-ws [trojan/websocket/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.support.transport_ws', 'xray.protocol.trojan', 'xray.mux.semantics']
    - ss-plain [shadowsocks/tcp/none] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.protocol.shadowsocks', 'xray.mux.semantics']
    - ss2022 [shadowsocks/tcp/none] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.protocol.shadowsocks', 'xray.mux.semantics']
    - ss-plugin [shadowsocks/tcp/none] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.protocol.shadowsocks', 'xray.mux.semantics']
    - hy2-plain [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']
    - hy2-obfs [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']
    - hy2-pin [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']
    - hy2-mport [hysteria2/quic/tls] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.support.tls', 'xray.mux.semantics', 'xray.protocol.hysteria2']
    - socks-simple [socks/tcp/none] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.mux.semantics']
    - socks-auth [socks/tcp/none] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.mux.semantics']
    - http-simple [http/tcp/none] SUPPORTED → SUPPORTED_WITH_WARNING  规则=['xray.mux.semantics']
- **fallback**: 0
- **relaxed**: 0
- **dialer_bug**: 0

结论: ✓ 无放宽（新判定只收紧或一致）；收紧 38 条；回退旧判定 0 条
