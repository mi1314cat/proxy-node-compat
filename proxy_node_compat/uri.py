"""Phase 4C · URI 解析与表达能力。

纪律:
  * 解析成功 ≠ 内核支持（本模块只产出 profile, 不做兼容性判断）
  * 原始 URI 与无法识别的参数必须可追溯（raw.uri / raw.fields / extensions）
  * 未知 scheme 也必须能保存并标记, 不能让整批解析失败
  * 回写时: INFERRED 字段不写、extensions 默认不写（除非显式 allow_extensions）
  * 绝不改换传输方式（xhttp 不会变成 ws）
"""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qsl, quote, unquote, urlsplit

from .model import Field, Feature, NodeProfile, Presence, Provenance

# scheme -> (protocol feature id, 已知参数集合)
SCHEMES: dict[str, tuple[str, set[str]]] = {
    "vless": ("standard:vless", {
        "type", "security", "sni", "servername", "alpn", "fp", "flow", "path", "host",
        "mode", "serviceName", "headerType", "seed", "pbk", "sid", "spx", "ech", "pqv",
        "pcs", "vcn", "fm", "encryption", "allowInsecure", "insecure", "extra", "mtu", "tti"}),
    "trojan": ("standard:trojan", {
        "type", "security", "sni", "alpn", "fp", "path", "host", "serviceName",
        "allowInsecure", "insecure", "pbk", "sid", "spx", "ech"}),
    "hysteria2": ("standard:hysteria2", {
        "sni", "insecure", "obfs", "obfs-password", "pinSHA256", "alpn", "mport", "ech"}),
    "hy2": ("standard:hysteria2", {"sni", "insecure", "obfs", "obfs-password", "pinSHA256"}),
    "tuic": ("standard:tuic", {"sni", "alpn", "congestion_control", "udp_relay_mode",
                              "allow_insecure", "insecure", "zero_rtt_handshake"}),
    "anytls": ("standard:anytls", {"sni", "insecure", "fp", "alpn"}),
    "socks": ("standard:socks", {"type"}),
    "socks5": ("standard:socks", {"type"}),
    "http": ("standard:http", {"type"}),
    "https": ("standard:http", {"type"}),
    "ss": ("standard:shadowsocks", {"plugin", "type", "security", "pbk", "sid", "spx"}),
}

# 哪些 query 参数对应哪个 feature
SECURITY_PARAMS = {"security": None, "tls": "standard:tls", "reality": "standard:reality"}
TRANSPORT_MAP = {
    "tcp": "standard:transport.tcp", "raw": "standard:transport.tcp",
    "ws": "standard:transport.ws", "websocket": "standard:transport.ws",
    "grpc": "standard:transport.grpc", "gun": "standard:transport.grpc",
    "h2": "standard:transport.http_h2", "http": "standard:transport.http_h2",
    "httpupgrade": "standard:transport.httpupgrade",
    "xhttp": "standard:xhttp", "splithttp": "standard:xhttp",
    "kcp": "standard:mkcp", "mkcp": "standard:mkcp", "quic": "standard:transport.quic",
}

# 这些参数属于哪个 feature 的 params（用于把值挂到正确的 feature 上）
PARAM_OWNER = {
    "path": "transport", "host": "transport", "serviceName": "transport",
    "mode": "standard:xhttp", "extra": "standard:xhttp", "headerType": "transport",
    "seed": "transport", "mtu": "transport", "tti": "transport",
    "pbk": "standard:reality", "sid": "standard:reality", "spx": "standard:reality",
    "ech": "standard:ech", "pqv": "standard:ech", "pcs": "standard:ech",
    "vcn": "standard:ech",
    "sni": "standard:tls", "servername": "standard:tls", "alpn": "standard:tls",
    "fp": "standard:tls", "allowInsecure": "standard:tls", "insecure": "standard:tls",
    "flow": "standard:flow",
    "mux": "standard:mux", "mux-enabled": "standard:mux", "smux": "standard:mux",
    "allowInsecure": "standard:tls.allow_insecure", "insecure": "standard:tls.allow_insecure", "obfs": "standard:hysteria2.obfs",
    "obfs-password": "standard:hysteria2.obfs", "pinSHA256": "standard:tls",
    "plugin": "standard:shadowsocks.plugin",
}


def _b64pad(s: str) -> str:
    return s + "=" * (-len(s) % 4)


def parse_uri(uri: str) -> NodeProfile:
    """解析分享链接。未知 scheme / 未知参数都不会导致失败。"""
    uri = uri.strip()
    parts = urlsplit(uri)
    scheme = (parts.scheme or "").lower()
    raw_fields: dict[str, object] = {}
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        raw_fields[k] = v
    frag_text = unquote(parts.fragment) if parts.fragment else ""

    profile = NodeProfile(raw_uri=uri, source_format="URI", raw_fields=raw_fields)

    if frag_text:
        profile.metadata["name"] = Field.explicit(frag_text, Provenance.URI, "#")

    if scheme not in SCHEMES:
        # ★ 未知协议也要能保存并标记
        profile.protocol = Feature(id=f"unknown:{scheme or 'noscheme'}",
                                   presence=Presence.EXPLICIT,
                                   provenance=Provenance.URI)
        for k, v in raw_fields.items():
            profile.add_extension(k, v, "URI", "未知协议, 参数原样保留")
        if parts.hostname:
            profile.endpoint["host"] = Field.explicit(parts.hostname, Provenance.URI, "host")
        if parts.port:
            profile.endpoint["port"] = Field.explicit(parts.port, Provenance.URI, "port")
        profile.diagnostics.append({"code": "UNKNOWN_SCHEME",
                                    "detail": f"未收录的 scheme: {scheme}"})
        return profile

    proto_id, known = SCHEMES[scheme]
    profile.protocol = Feature(id=proto_id, presence=Presence.EXPLICIT,
                               provenance=Provenance.URI)

    host = parts.hostname or ""
    if scheme == "ss":  # SIP002: userinfo 是 base64(method:password)
        try:
            decoded = base64.urlsafe_b64decode(_b64pad(parts.username or "")).decode()
            method, _, password = decoded.partition(":")
            profile.auth["method"] = Field.explicit(method, Provenance.URI, "userinfo")
            profile.auth["password"] = Field.explicit(password, Provenance.URI, "userinfo")
        except Exception:
            profile.diagnostics.append({"code": "SS_USERINFO_UNPARSED",
                                        "detail": "userinfo 不是合法 base64"})
    else:
        if parts.username:
            key = "uuid" if proto_id in ("standard:vless",) else "password"
            if proto_id == "standard:vmess":
                key = "uuid"
            profile.auth[key] = Field.explicit(unquote(parts.username), Provenance.URI, "userinfo")
        if parts.password:
            profile.auth["password"] = Field.explicit(unquote(parts.password),
                                                      Provenance.URI, "userinfo")
    profile.endpoint["host"] = Field.explicit(host, Provenance.URI, "host")
    profile.endpoint["port"] = Field.explicit(parts.port or (443 if parts.port is None else None),
                                              Provenance.URI, "port")

    # ---- transport / security / 其它 feature
    q = dict(raw_fields)
    tname = (q.get("type") or q.get("net") or "").strip().lower()
    if tname:
        tid = TRANSPORT_MAP.get(tname)
        if tid is None:
            # 未知传输: 保留原值, 记为 vendor/unknown feature, 绝不改换
            profile.add_feature(Feature(id=f"unknown:transport.{tname}",
                                        presence=Presence.EXPLICIT,
                                        provenance=Provenance.URI,
                                        note=f"未收录的传输方式 type={tname}"))
            profile.add_extension("type", q["type"], "URI", "未知传输方式, 原样保留")
        else:
            profile.add_feature(Feature(id=tid, presence=Presence.EXPLICIT,
                                        provenance=Provenance.URI))
    else:
        profile.add_feature(Feature(id="standard:transport.tcp", presence=Presence.DEFAULTED,
                                    provenance=Provenance.INFERRED,
                                    note="未写 type, 按规范默认 raw/tcp"))
    sec = (q.get("security") or "").strip().lower()
    if sec == "tls":
        profile.add_feature(Feature(id="standard:tls", presence=Presence.EXPLICIT,
                                    provenance=Provenance.URI))
    elif sec == "reality":
        profile.add_feature(Feature(id="standard:reality", presence=Presence.EXPLICIT,
                                    provenance=Provenance.URI))
    elif sec in ("", "none"):
        if proto_id in ("standard:trojan", "standard:hysteria2", "standard:tuic",
                        "standard:anytls"):
            profile.add_feature(Feature(id="standard:tls", presence=Presence.DEFAULTED,
                                        provenance=Provenance.INFERRED,
                                        note=f"{proto_id} 默认走 TLS"))
    if q.get("allowInsecure") or q.get("insecure"):
        profile.add_feature(Feature(id="standard:tls.allow_insecure",
                                    presence=Presence.EXPLICIT, provenance=Provenance.URI))
    if q.get("mux") or q.get("mux-enabled") or q.get("smux"):
        profile.add_feature(Feature(id="standard:mux", presence=Presence.EXPLICIT,
                                    provenance=Provenance.URI))
    if q.get("flow"):
        profile.add_feature(Feature(id="standard:flow", presence=Presence.EXPLICIT,
                                    provenance=Provenance.URI))
    if q.get("ech") or q.get("pqv") or q.get("pcs") or q.get("vcn"):
        profile.add_feature(Feature(id="standard:ech", presence=Presence.EXPLICIT,
                                    provenance=Provenance.URI))

    # ---- 参数归属（挂到对应 feature 上, 否则进 extensions）
    for k, v in q.items():
        if k in ("type", "security", "encryption"):
            continue
        owner = PARAM_OWNER.get(k)
        if owner == "transport":
            tid = TRANSPORT_MAP.get(tname)
            feat = profile.get_feature(tid) if tid else None
        elif owner is None:
            feat = None
        else:
            feat = profile.get_feature(owner)
            if feat is None and owner.startswith("standard:") and owner not in (
                    "standard:xhttp", "standard:ech", "standard:reality"):
                feat = None
        if feat is not None:
            feat.params[k] = Field.explicit(v, Provenance.URI, k)
        elif owner in ("standard:xhttp", "standard:ech", "standard:reality"):
            # 对应 feature 不存在 → 用参数本身反推一个 feature（如 pbk 隐含 reality）
            implied = {"standard:reality": "standard:reality", "standard:ech": "standard:ech",
                       "standard:xhttp": "standard:xhttp"}[owner]
            if profile.get_feature(implied) is None:
                profile.add_feature(Feature(id=implied, presence=Presence.INFERRED,
                                            provenance=Provenance.INFERRED,
                                            note=f"由参数 {k} 反推"))
            profile.get_feature(implied).params[k] = Field.explicit(v, Provenance.URI, k)
        elif k not in known:
            profile.add_extension(k, v, "URI")   # ★ 未知参数进 extensions, 绝不丢
        else:
            profile.add_extension(k, v, "URI", "已收录但未建模到具体 feature")

    # AnyReality: 组合特征（vendor 命名空间, 无特例分支）
    if (profile.get_feature("standard:reality") is not None
            and proto_id == "standard:shadowsocks"):
        profile.add_feature(Feature(
            id="mi1314cat:anyreality.ss-reality", presence=Presence.EXPLICIT,
            provenance=Provenance.INFERRED,
            requires=["standard:shadowsocks", "standard:reality"],
            note="SS2022 叠加 REALITY（由 security=reality 推断）"))
    return profile


def generate_uri(profile: NodeProfile, *, allow_extensions: bool = False) -> str:
    """回写链接。INFERRED 字段不写回（不伪装成用户显式提供）。"""
    proto = profile.protocol.id if profile.protocol else "unknown"
    scheme = {"standard:vless": "vless", "standard:trojan": "trojan",
              "standard:shadowsocks": "ss", "standard:hysteria2": "hysteria2",
              "standard:tuic": "tuic", "standard:anytls": "anytls",
              "standard:socks": "socks", "standard:http": "http"}.get(proto, "")
    if not scheme:
        raise ValueError(f"无法为该 protocol 生成标准链接: {proto}")

    host = profile.endpoint.get("host")
    port = profile.endpoint.get("port")
    user = ""
    for key in ("uuid", "password"):
        f = profile.auth.get(key)
        if f is not None and f.presence is Presence.EXPLICIT:
            user = quote(str(f.v))
            break
    if scheme == "ss":
        m = profile.auth.get("method")
        pw = profile.auth.get("password")
        if m and pw and m.presence is Presence.EXPLICIT:
            blob = base64.urlsafe_b64encode(f"{m.v}:{pw.v}".encode()).decode().rstrip("=")
            user = blob

    q: list[tuple[str, str]] = []
    for feat in profile.features:
        for pk, pf in feat.params.items():
            if pf.presence is Presence.EXPLICIT:   # 只写显式值
                q.append((pf.raw_key or pk, str(pf.v)))
        if feat.id == "standard:transport.ws":
            q.append(("type", "ws"))
        elif feat.id == "standard:xhttp":
            q.append(("type", "xhttp"))
        elif feat.id == "standard:transport.grpc":
            q.append(("type", "grpc"))
        elif feat.id == "standard:reality":
            q.append(("security", "reality"))
        elif feat.id == "standard:tls" and feat.presence is Presence.EXPLICIT:
            q.append(("security", "tls"))
    if allow_extensions:
        for e in profile.extensions:
            q.append((e["key"], str(e["value"])))

    name = profile.metadata.get("name")
    frag = ""
    if name is not None and name.presence is Presence.EXPLICIT:
        frag = "#" + quote(str(name.v))
    query = "&".join(f"{k}={v}" for k, v in q)
    return f"{scheme}://{user}@{host.v if host else ''}:{port.v if port else ''}" \
           + (f"?{query}" if query else "") + frag


def parse_json_node(data: dict, fmt: str) -> NodeProfile:
    """从内核配置片段（Xray/sing-box 出站 / mihomo proxy）建 profile。"""
    prof = NodeProfile(source_format=fmt, raw_fields=dict(data))
    prof.diagnostics.append({"code": "JSON_IMPORT", "detail": f"来自 {fmt} 配置片段"})
    for k, v in data.items():
        prof.add_extension(k, v, fmt, "尚未建模到 profile")
    return prof
