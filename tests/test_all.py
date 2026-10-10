"""Phase 4 验收测试 —— 用户指定的 18 个案例 + 版本边界红线。

运行: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from proxy_node_compat import (Feature, Field, NodeProfile, Presence, Provenance,  # noqa: E402
                               Registry, Target, check_node, evaluate, generate_uri,
                               parse_uri)
from proxy_node_compat.registry import Rule, default_registry_path  # noqa: E402

REG = Registry.load(default_registry_path())


def T(kernel, version=None, **kw):
    return Target(kernel=kernel, version=version, **kw)


def U(uri, kernel, version=None, **kw):
    return check_node(uri, T(kernel, version, **kw), REG)


# ---------------------------------------------------------------- Phase 4A
class TestProfile(unittest.TestCase):
    def test_15_unknown_field_survives_roundtrip(self):
        uri = "vless://u@h:443?type=xhttp&evilField=1&another=%E4%B8%AD#n"
        p = parse_uri(uri)
        self.assertIn("evilField", [e["key"] for e in p.extensions])
        rp = p.roundtrip()
        self.assertEqual(p.to_dict(), rp.to_dict())          # 序列化不丢信息
        self.assertEqual(rp.raw_uri, uri)                     # 原文不变（I1）
        self.assertIn("evilField", rp.raw_fields)
        self.assertEqual(rp.check_invariants(), [])

    def test_presence_semantics(self):
        self.assertRaises(ValueError, Field, Presence.ABSENT, "x")
        self.assertRaises(ValueError, Field, Presence.INFERRED, "x")  # 缺 basis
        p = parse_uri("vless://u@h:443")                     # 没写 type
        t = p.get_feature("standard:transport.tcp")
        self.assertIsNotNone(t)
        self.assertIs(t.presence, Presence.DEFAULTED)
        self.assertIs(t.provenance, Provenance.INFERRED)

    def test_feature_namespace_and_no_kernel_version_field(self):
        p = parse_uri("vless://u@h:443?security=reality&pbk=K")
        blob = json.dumps(p.to_dict())
        for bad in ("xray_version", "mihomo_version", "sing_box_version", "kernel"):
            self.assertNotIn(bad, blob)                       # 不变式 I7
        self.assertTrue(all(":" in f.id for f in p.features))

    def test_unknown_scheme_is_preserved_not_fatal(self):
        p = parse_uri("magic://abc@h:443?foo=1#x")
        self.assertTrue(p.protocol.id.startswith("unknown:"))
        self.assertEqual(p.raw_fields.get("foo"), "1")
        res = evaluate(p, T("mihomo", "1.19.32"), REG)
        self.assertIn(res.status, ("UNKNOWN", "UNSUPPORTED"))  # 绝不让整批解析失败
        self.assertEqual(res.raw_uri, p.raw_uri)


# ---------------------------------------------------------------- Phase 4B
class TestEngine(unittest.TestCase):
    def test_1_vless_tcp_reality(self):
        r = U("vless://u@h:443?security=reality&pbk=K&sid=01&type=tcp", "singbox", "1.14.2",
              build_tags=["with_utls"])
        self.assertEqual(r.status, "SUPPORTED")
        self.assertEqual(r.levels["config"], "SUPPORTED")

    def test_2_vless_xhttp(self):
        uri = "vless://u@h:443?type=xhttp&path=%2Fx"
        self.assertEqual(U(uri, "mihomo", "1.19.32").status, "SUPPORTED_WITH_WARNING")
        sb = U(uri, "singbox", "1.14.2")
        self.assertEqual(sb.status, "UNSUPPORTED")
        self.assertIn("KERNEL_NEVER_SUPPORTED", sb.reason_codes)

    def test_3_vless_mkcp(self):
        uri = "vless://u@h:443?type=kcp"
        self.assertEqual(U(uri, "xray", "26.1.23").status, "SUPPORTED")
        self.assertEqual(U(uri, "xray", "26.3.27").status, "UNSUPPORTED")     # 硬报错段
        self.assertEqual(U(uri, "xray", "26.9.30").status, "SUPPORTED_WITH_LOSS")  # 静默丢弃段
        self.assertEqual(U(uri, "singbox", "1.14.2").status, "UNSUPPORTED")
        m = U(uri, "mihomo", "1.19.32")
        self.assertEqual(m.status, "SUPPORTED_WITH_LOSS")
        self.assertEqual(m.failure_mode, "silent_ignore")

    def test_4_anyreality(self):
        uri = "ss://QUJD@h:8388?security=reality&pbk=K&sid=01"
        p = parse_uri(uri)
        self.assertIsNotNone(p.get_feature("mi1314cat:anyreality.ss-reality"))
        sb = evaluate(p, T("singbox", "1.14.2"), REG)
        self.assertEqual(sb.status, "UNSUPPORTED")
        self.assertIn("KERNEL_NEVER_SUPPORTED", sb.reason_codes)   # 实测 unknown field "tls"
        self.assertTrue(any(l["feature"].endswith("reality") for l in sb.losses)
                        or sb.levels["uri"] == "SUPPORTED_WITH_LOSS")  # URI 也表达不了

    def test_5_ech(self):
        r = U("vless://u@h:443?type=tcp&security=tls&ech=AEX", "singbox", "1.14.2")
        self.assertTrue(any(w["code"] == "SEMANTIC_MISMATCH" for w in r.warnings))

    def test_6_custom_unknown_feature(self):
        p = parse_uri("vless://u@h:443?type=tcp")
        from proxy_node_compat import Feature
        p.add_feature(Feature(id="mi1314cat:magic-transport", provenance=Provenance.USER_DEFINED))
        res = evaluate(p, T("mihomo", "1.19.32"), REG)
        self.assertEqual(res.status, "UNKNOWN")          # 未知 ≠ 不支持
        self.assertIn("UNKNOWN_CAPABILITY", res.reason_codes)
        self.assertEqual(res.raw_uri, p.raw_uri)         # 信息一字未丢

    def test_7_removed_feature(self):
        r = U("vless://u@h:443?type=h2", "xray", "26.3.27")
        self.assertEqual(r.status, "UNSUPPORTED")
        self.assertIn("KERNEL_REMOVED", r.reason_codes)

    def test_8_never_supported(self):
        r = U("vless://u@h:443?type=xhttp", "singbox", "1.14.2")
        self.assertIn("KERNEL_NEVER_SUPPORTED", r.reason_codes)
        self.assertNotIn("KERNEL_REMOVED", r.reason_codes)

    def test_9_kernel_ok_uri_cannot_express(self):
        r = U("ss://QUJD@h:8388?security=reality&pbk=K", "xray", "26.3.27")
        self.assertEqual(r.levels["uri"], "SUPPORTED_WITH_LOSS")
        self.assertTrue(any("reality" in l.get("feature", "") for l in r.losses))

    def test_10_silent_ignore(self):
        r = U("vless://u@h:443?type=kcp", "mihomo", "1.19.32")
        self.assertEqual(r.status, "SUPPORTED_WITH_LOSS")
        self.assertEqual(r.failure_mode, "silent_ignore")
        self.assertTrue(r.losses)

    def test_11_silent_drop(self):
        r = U("vless://u@h:443?type=kcp", "xray", "26.9.30")
        self.assertEqual(r.failure_mode, "silent_drop")
        self.assertEqual(r.status, "SUPPORTED_WITH_LOSS")

    def test_12_runtime_fail(self):
        r = U("vless://u@h:443?security=reality&pbk=K", "mihomo", "1.19.32")  # 缺 fingerprint
        self.assertIn("RUNTIME_CONDITION_NOT_MET", r.reason_codes)
        self.assertEqual(r.status, "SUPPORTED_WITH_LOSS")
        r2 = U("vless://u@h:443?security=reality&pbk=K", "mihomo", "1.19.32",
               runtime_options={"client_fingerprint_present": True})
        self.assertNotIn("RUNTIME_CONDITION_NOT_MET", r2.reason_codes)

    def test_17_combination_not_implied_by_parts(self):
        ok = U("vless://u@h:443?type=tcp&security=reality&pbk=K", "xray", "26.3.27")
        self.assertNotEqual(ok.status, "UNSUPPORTED")
        bad = U("vless://u@h:443?type=h2&security=reality&pbk=K", "xray", "26.0.0")
        self.assertEqual(bad.levels["config"], "UNSUPPORTED")   # 组合不成立

    def test_14_fork_build_platform(self):
        uri = "vless://u@h:443?type=xhttp"
        self.assertEqual(U(uri, "singbox", "1.14.2").status, "UNSUPPORTED")
        self.assertEqual(U(uri, "singbox", "1.14.2",
                           distribution="sing-box-lx").status, "UNKNOWN")  # fork 不继承上游
        r = U("vless://u@h:443?type=tcp&security=reality&pbk=K", "singbox", "1.14.2",
              build_tags=[])
        self.assertIn("BUILD_NOT_ENABLED", r.reason_codes)
        r2 = U("vless://u@h:443?type=tcp&security=reality&pbk=K", "singbox", "1.14.2")
        self.assertTrue(True)  # build_tags 未知 → 相关层级 UNKNOWN（在 test_unknown_build 里断言）


# ---------------------------------------------------------------- 红线与不确定性
class TestVersionBoundaries(unittest.TestCase):
    """用户指定的验收红线: 证据只到两端时, 中间版本必须 UNKNOWN。"""

    FIXTURE = {
        "evidence": [{"id": "e-old", "type": "SRC", "confidence": "MEDIUM", "claim": "1.18.0 有",
                      "how": "源码", "where": "fixture", "limits": "单点"},
                     {"id": "e-new", "type": "SRC", "confidence": "MEDIUM", "claim": "1.19.32 无",
                      "how": "源码", "where": "fixture", "limits": "单点"}],
        "rules": [{
            "rule_id": "fx.feature.boundary",
            "target": {"kernel": "fxkernel", "distribution": "upstream"},
            "selector": {"feature": "standard:xhttp"},
            "segments": [
                {"range": "<= 1.18.0", "verdict": {"config": "SUPPORTED", "runtime": "SUPPORTED"},
                 "evidence": ["e-old"]},
                {"range": ">= 1.19.32", "verdict": {"config": "UNSUPPORTED", "runtime": "UNSUPPORTED"},
                 "failure_mode": "silent_drop", "reason_code": "KERNEL_REMOVED",
                 "evidence": ["e-new"]}],
            "transition": "UNKNOWN",
            "unknown_range": [{"range": "> 1.18.0, < 1.19.32",
                               "why": "两端各有证据, 中间无任何一版被验证"}],
            "evidence": ["e-old", "e-new"]}],
        "uri_rules": []}

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self.FIXTURE, fh)
        self.reg = Registry.load(path)
        self.uri = "vless://u@h:443?type=xhttp"

    def _run(self, version):
        return check_node(self.uri, T("fxkernel", version), self.reg)

    def test_redline_middle_version_is_unknown(self):
        r = self._run("1.19.5")
        self.assertEqual(r.status, "UNKNOWN")            # ★ 不得向区间外推断
        self.assertTrue(any("1.18.0" in u["what"] or "未知" in u["why"] for u in r.unknowns))
        self.assertNotIn("KERNEL_REMOVED", r.reason_codes)

    def test_known_ends(self):
        self.assertEqual(self._run("1.18.0").status, "SUPPORTED")
        self.assertEqual(self._run("1.19.32").status, "UNSUPPORTED")

    def test_no_version_evidence_at_all(self):
        reg = Registry.load(default_registry_path())
        r = check_node(self.uri, T("mihomo"), reg)
        self.assertIn(r.levels["config"], ("UNKNOWN",))

    def test_unknown_build_stays_unknown_but_siblings_still_resolve(self):
        # sing-box: xhttp 是版本无关的事实 → 缺 build_tags 也不该被抹成 UNKNOWN
        r = U("vless://u@h:443?type=xhttp", "singbox", "1.14.2")
        self.assertEqual(r.levels["config"], "UNSUPPORTED")
        # reality 需要 with_utls, 但没给 tags → 只影响 runtime 层
        r2 = U("vless://u@h:443?type=tcp&security=reality&pbk=K", "singbox", "1.14.2")
        self.assertEqual(r2.levels["config"], "SUPPORTED")
        self.assertTrue(any("build" in u["what"] for u in r2.unknowns))

    def test_inference_only_evidence_cannot_be_plain_supported(self):
        fixture = {
            "evidence": [{"id": "e-inf", "type": "INFERENCE", "confidence": "LOW",
                          "claim": "由相邻版本推断", "how": "推断", "where": "fixture",
                          "limits": "无直接证据"}],
            "rules": [{
                "rule_id": "fx.inference.only",
                "target": {"kernel": "fx2", "distribution": "upstream"},
                "selector": {"feature": "standard:xhttp"},
                "segments": [{"range": "*", "verdict": {"config": "SUPPORTED", "runtime": "SUPPORTED"},
                              "evidence": ["e-inf"]}],
                "version_independent": True, "evidence": ["e-inf"]}],
            "uri_rules": []}
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(fixture, fh)
        reg = Registry.load(path)
        r = check_node("vless://u@h:443?type=xhttp", T("fx2", "1.0.0"), reg)
        self.assertNotEqual(r.status, "SUPPORTED")        # 案例 18
        self.assertTrue(any(w["code"] == "INFERENCE_ONLY_EVIDENCE" for w in r.warnings))


# ---------------------------------------------------------------- 更正: Xray hysteria2 出站
class TestXrayHysteria2Outbound(unittest.TestCase):
    """Xray 有 hysteria 出站（settings.version=2 即 Hysteria2）—— 实测 204。

    原来的规则 `xray.protocol.hysteria2.never`（KERNEL_NEVER_SUPPORTED）来自探针套件里
    按 mihomo/sing-box 形状写的 hysteria2 用例，从没试过 Xray 自己的
    `protocol: hysteria` + `settings.version: 2` 形状。CC 上 26.3.27 的真机回环
    （xray -test → Configuration OK，经该出站 curl → 204）把它证伪了。
    证据: e-xray-hysteria2-outbound。**只覆盖出站方向。**
    """

    def test_26327_outbound_supported(self):
        r = check_node("hysteria2://pw@h.example:443?sni=h.example#hy", T("xray", "26.3.27"))
        self.assertEqual(r.status, "SUPPORTED")
        self.assertIn("xray.protocol.hysteria2", r.rules_applied)
        self.assertNotIn("KERNEL_NEVER_SUPPORTED", r.reason_codes)

    def test_older_version_is_unknown_not_supported(self):
        # 证据只到 26.3.27 —— 更早的版本不许外推成"支持"
        r = check_node("hysteria2://pw@h.example:443?sni=h.example#hy", T("xray", "25.1.1"))
        self.assertEqual(r.status, "UNKNOWN")

    def test_other_kernels_unaffected(self):
        r = check_node("hysteria2://pw@h.example:443?sni=h.example#hy", T("singbox", "1.14.2"))
        self.assertIn(r.status, ("SUPPORTED", "SUPPORTED_WITH_WARNING", "SUPPORTED_WITH_LOSS"))


# ---------------------------------------------------------------- Phase 4C
class TestUri(unittest.TestCase):
    def test_16_inferred_not_written_back(self):
        p = parse_uri("hysteria2://pw@h:443#n")
        tls = p.get_feature("standard:tls")
        self.assertIs(tls.provenance, Provenance.INFERRED)      # 默认 TLS 是推断来的
        uri2 = generate_uri(p)
        self.assertNotIn("security=tls", uri2)                  # 推断值不得伪装成显式
        p.add_extension("evilField", "1", "URI")
        self.assertNotIn("evilField", generate_uri(p))          # extensions 默认不写回

    def test_explicit_params_are_written_back(self):
        p = parse_uri("vless://u@h:443?type=xhttp&path=%2Fx&mode=auto#n")
        uri2 = generate_uri(p)
        self.assertIn("type=xhttp", uri2)
        self.assertIn("path=/x", uri2)
        self.assertIn("#n", uri2)

    def test_never_switches_transport(self):
        p = parse_uri("vless://u@h:443?type=xhttp")
        self.assertIn("type=xhttp", generate_uri(p))
        p2 = parse_uri("vless://u@h:443?type=magic")
        self.assertTrue(p2.get_feature("unknown:transport.magic"))
        res = evaluate(p2, T("mihomo", "1.19.32"), REG)
        self.assertNotIn("standard:transport.ws", json.dumps(res.to_dict()))


# ---------------------------------------------------------------- 真实链接验收
# RN 上三个内核实际产出的四条链接（Xray / mihomo / sing-box 的分享系统输出）
REAL_LINKS = {
    "vless_pq": (
        "vless://c521fd45-5cb8-406f-bc83-ba92efa5e8e6@107.173.154.178:22726"
        "?encryption=mlkem768x25519plus.native.0rtt.ABC&security=tls&sni=cloudflare.com"
        "&type=xhttp&path=/&ech=AGH+DQBdAAAgACCRE8kdV65r7OZoo9WgdkRM44Te7b/73CcbZQOJfFgq"
        "AgAkAAEAAQABAAIAAQADAAIAAQACAAIAAgADAAMAAQADAAIAAwADAA5jbG91ZGZsYXJlLmNvbQAA#n1"),
    "trojan_reality": (
        "trojan://8nb23TSPeSQSazq4DS4U@107.173.154.178:37944?security=reality"
        "&sni=addons.mozilla.org&type=tcp&fp=chrome"
        "&pbk=a8cp3JmCFQK1CovT4d8tAbzJ9mkYjz7N8OWOwTYhvHk&sid=d14d8225#n2"),
    "ss2022": (
        "ss://MjAyMi1ibGFrZTMtYWVzLTEyOC1nY206NnZqRVJpWGRab2VkSDVVaW9JV0R6UT09"
        "@107.173.154.178:31004#n3"),
    "vmess_ws_tls": (
        "vmess://eyJhZGQiOiJoeGljYy5jYXRtaWNvcy5kcGRucy5vcmciLCJwb3J0IjoiNDQzIiwidXVpZCI6"
        "IjQ4YWYyOGVhLTNjZDAtNDc1Ny1hZGM5LTgxNWE3YjFjMWUzNiIsImFpZCI6IjAiLCJuZXQiOiJ3cyIs"
        "InBhdGgiOiIvY2JhMzExYjUiLCJob3N0IjoiaHhpY2MuY2F0bWljb3MuZHBkbnMub3JnIiwic2VjdXJp"
        "dHkiOiJhdXRvIiwidGxzIjoidGxzIiwic25pIjoiaHhpY2MuY2F0bWljb3MuZHBkbnMub3JnIiwiYWxw"
        "biI6Imh0dHAvMS4xIn0=#n4"),
}

KERNELS = {"xray": "26.3.27", "mihomo": "1.19.32", "singbox": "1.14.2"}


def vmess_body_of(uri: str) -> dict:
    payload = uri.split("://", 1)[1].split("#", 1)[0]
    blob = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    return json.loads(blob.decode())


class TestRealLinkVmess(unittest.TestCase):
    """缺口 1: vmess:// 是 base64(JSON), 必须解析成 endpoint/auth/transport/tls。"""

    def test_body_parsed_into_profile(self):
        p = parse_uri(REAL_LINKS["vmess_ws_tls"])
        self.assertEqual(p.protocol.id, "standard:vmess")        # 不再是 unknown:vmess + 空 profile
        self.assertEqual(p.endpoint["host"].v, "hxicc.catmicos.dpdns.org")
        self.assertEqual(p.endpoint["host"].raw_key, "add")      # 生态通用键名
        self.assertEqual(p.endpoint["port"].v, 443)              # JSON 里是字符串 "443"
        self.assertEqual(p.auth["uuid"].v, "48af28ea-3cd0-4757-adc9-815a7b1c1e36")
        self.assertEqual(p.auth["uuid"].raw_key, "uuid")         # uuid / id 两种写法都认
        self.assertEqual(p.auth["alter_id"].v, "0")
        self.assertEqual(p.auth["method"].v, "auto")             # 旧写法 security= 就是加密方式
        ws = p.get_feature("standard:transport.ws")
        self.assertIsNotNone(ws)
        self.assertEqual(ws.params["path"].v, "/cba311b5")
        self.assertEqual(ws.params["host"].v, "hxicc.catmicos.dpdns.org")
        tls = p.get_feature("standard:tls")
        self.assertIsNotNone(tls)
        self.assertIs(tls.presence, Presence.EXPLICIT)
        self.assertEqual(tls.params["sni"].v, "hxicc.catmicos.dpdns.org")
        self.assertEqual(tls.params["alpn"].v, "http/1.1")
        self.assertEqual(p.extensions, [])                       # 全部建模, 没有残留
        self.assertEqual(p.raw_uri, REAL_LINKS["vmess_ws_tls"])  # P6: 原文一字不动
        self.assertEqual(p.check_invariants(), [])

    def test_vmess_is_not_unknown_scheme_anymore(self):
        p = parse_uri(REAL_LINKS["vmess_ws_tls"])
        self.assertNotIn("UNKNOWN_SCHEME", [d["code"] for d in p.diagnostics])
        for kernel, version in KERNELS.items():
            r = evaluate(p, T(kernel, version), REG)
            self.assertNotEqual(r.status, "UNKNOWN")             # 原来三家都是 UNKNOWN
            self.assertEqual(r.raw_uri, REAL_LINKS["vmess_ws_tls"])

    def test_unknown_keys_kept_and_never_generated(self):
        cfg = {"add": "h", "port": "443", "id": "u", "net": "ws", "v": "2",
               "evilField": "1", "scy": "auto"}
        blob = base64.urlsafe_b64encode(json.dumps(cfg).encode()).decode()
        p = parse_uri("vmess://" + blob + "#x")
        keys = [e["key"] for e in p.extensions]
        self.assertIn("evilField", keys)                         # 未知键必须登记
        self.assertIn("v", keys)                                 # 读了但未建模 → 也登记
        self.assertIn("evilField", p.raw_fields)                 # I2: extensions 或 raw.fields
        out = generate_uri(p)
        self.assertNotIn("evilField", vmess_body_of(out))        # 默认不写回
        self.assertNotIn("v", vmess_body_of(out))                # 未建模的 v 也不写回
        out2 = generate_uri(p, allow_extensions=True)            # 显式要求才写
        self.assertEqual(vmess_body_of(out2)["evilField"], "1")

    def test_roundtrip_semantics(self):
        p = parse_uri(REAL_LINKS["vmess_ws_tls"])
        p2 = parse_uri(generate_uri(p))
        self.assertEqual(p2.raw_fields, p.raw_fields)            # 语义等价（字段可恢复）
        self.assertEqual([f.id for f in p2.features], [f.id for f in p.features])
        self.assertEqual({k: f.to_dict() for k, f in p2.auth.items()},
                         {k: f.to_dict() for k, f in p.auth.items()})
        self.assertEqual({k: f.to_dict() for k, f in p2.endpoint.items()},
                         {k: f.to_dict() for k, f in p.endpoint.items()})
        self.assertEqual(p2.extensions, [])

    def test_unparsable_body_is_not_fatal(self):
        uri = "vmess://!!!not-base64-json!!!#x"
        p = parse_uri(uri)
        self.assertEqual(p.protocol.id, "standard:vmess")
        self.assertIn("VMESS_BODY_UNPARSED", [d["code"] for d in p.diagnostics])
        self.assertEqual(p.raw_uri, uri)                          # 原文保留
        self.assertEqual(p.raw_fields["_vmess_body"], "!!!not-base64-json!!!")
        self.assertIsNotNone(p.get_feature("unknown:vmess.body-unparsed"))  # 未解析 = 未知 feature
        self.assertRaises(ValueError, generate_uri, p)            # 拒绝用空 JSON 覆盖原文
        r = evaluate(p, T("mihomo", "1.19.32"), REG)
        self.assertIn(r.status, ("UNKNOWN", "UNSUPPORTED"))       # 未知不猜, 也不让整批失败


class TestRealLinkVlessEncryption(unittest.TestCase):
    """缺口 2: encryption= 必须建模（原来只在 raw.fields → 能力判定看不见）。"""

    def test_feature_and_uri_rule(self):
        p = parse_uri(REAL_LINKS["vless_pq"])
        feat = p.get_feature("standard:vless.encryption")
        self.assertIsNotNone(feat)
        self.assertIs(feat.presence, Presence.EXPLICIT)
        self.assertEqual(feat.params["encryption"].v, "mlkem768x25519plus.native.0rtt.ABC")
        self.assertEqual(feat.params["encryption"].raw_key, "encryption")
        self.assertNotIn("encryption", [e["key"] for e in p.extensions])
        self.assertIn("encryption=mlkem768x25519plus.native.0rtt.ABC", generate_uri(p))
        rule = REG.uri_rule("vless", "standard:vless.encryption")
        self.assertIsNotNone(rule)                                # URI 表达力规则存在
        self.assertEqual(rule["representation"], "FULL")
        self.assertIsNone(rule.get("spec_added_at"))               # 查不到日期 → UNKNOWN, 不猜
        r = evaluate(p, T("xray", "26.3.27"), REG)
        self.assertIn({"id": "standard:vless.encryption", "presence": "EXPLICIT"},
                      r.detected_features)                        # 判定看得见它了
        self.assertNotEqual(r.levels["uri"], "UNKNOWN")            # 这条 URI 规则参与了判定

    def test_ech_value_is_byte_faithful(self):
        # 真实链接的 ech 是 base64, 含 '+' —— 解析期绝不能被改成空格
        p = parse_uri(REAL_LINKS["vless_pq"])
        self.assertTrue(p.raw_fields["ech"].startswith("AGH+DQBd"))
        self.assertEqual(p.get_feature("standard:ech").params["ech"].v,
                         p.raw_fields["ech"])


class TestRealLinkRealityIdentity(unittest.TestCase):
    """缺口 3: security=reality 的 sni/fp 必须挂到 reality 上（不是 extensions）。"""

    def test_sni_fp_are_reality_params(self):
        p = parse_uri(REAL_LINKS["trojan_reality"])
        reality = p.get_feature("standard:reality")
        self.assertEqual(reality.params["server_name"].v, "addons.mozilla.org")
        self.assertEqual(reality.params["server_name"].raw_key, "sni")
        self.assertEqual(reality.params["fingerprint"].v, "chrome")
        self.assertEqual(reality.params["fingerprint"].raw_key, "fp")
        self.assertEqual(p.extensions, [])                        # 不再掉进 extensions
        tls = p.get_feature("standard:tls")
        self.assertTrue(tls is None or tls.presence is not Presence.EXPLICIT)  # 不伪造显式 TLS
        out = generate_uri(p)
        self.assertIn("sni=addons.mozilla.org", out)
        self.assertIn("fp=chrome", out)
        self.assertEqual(p.check_invariants(), [])

    def test_mihomo_client_fingerprint_condition_now_decidable(self):
        r = U(REAL_LINKS["trojan_reality"], "mihomo", "1.19.32")
        self.assertNotIn("RUNTIME_CONDITION_NOT_MET", r.reason_codes)   # fp 是链接里显式的
        self.assertTrue(any(w["code"] == "RUNTIME_CONDITION_FROM_PROFILE" for w in r.warnings))
        # 没有 fp 时不得弱化: 仍按"缺 client-fingerprint 会运行期失败"判（= 原 test_12 行为）
        r2 = U("vless://u@h:443?security=reality&pbk=K", "mihomo", "1.19.32")
        self.assertIn("RUNTIME_CONDITION_NOT_MET", r2.reason_codes)
        self.assertNotIn("RUNTIME_CONDITION_FROM_PROFILE",
                         [w["code"] for w in r2.warnings])


class TestRealLinkShadowsocks(unittest.TestCase):
    """顺手修的一处: ss://(base64 userinfo, 无 query) 的 features 不许为空。"""

    def test_base64_userinfo_keeps_default_transport(self):
        p = parse_uri(REAL_LINKS["ss2022"])
        self.assertEqual(p.protocol.id, "standard:shadowsocks")
        self.assertEqual(p.auth["method"].v, "2022-blake3-aes-128-gcm")
        self.assertEqual(p.auth["password"].v, "6vjERiXdZoedH5UioIWDzQ==")
        self.assertIn("standard:transport.tcp", [f.id for f in p.features])
        tcp = p.get_feature("standard:transport.tcp")
        self.assertIs(tcp.presence, Presence.DEFAULTED)           # 默认传输 ≠ 用户显式要求
        self.assertIs(tcp.provenance, Provenance.INFERRED)
        self.assertEqual(p.check_invariants(), [])
        for kernel, version in KERNELS.items():
            self.assertEqual(evaluate(p, T(kernel, version), REG).status, "SUPPORTED")


class TestRealLinksEndToEnd(unittest.TestCase):
    """四条真实链接 × 三个内核：不炸、原文不丢、不变式成立、往返可重放。"""

    def test_all_links_all_kernels(self):
        for name, uri in REAL_LINKS.items():
            p = parse_uri(uri)
            self.assertEqual(p.raw_uri, uri, name)                # P6
            self.assertEqual(p.check_invariants(), [], name)
            self.assertEqual(p.roundtrip().to_dict(), p.to_dict(), name)
            for kernel, version in KERNELS.items():
                r = evaluate(p, T(kernel, version), REG)
                self.assertEqual(r.raw_uri, uri, f"{name}/{kernel}")
                self.assertIn(r.status, ("SUPPORTED", "SUPPORTED_WITH_WARNING",
                                         "SUPPORTED_WITH_LOSS", "UNSUPPORTED", "UNKNOWN"))
                # 任何未建模的键都必须能在 extensions 或 raw.fields 里找到（I2）
                for e in p.extensions:
                    self.assertIn(e["key"], p.raw_fields, f"{name}/{kernel}")


# ------------------------------------------------ 跨内核 compat: 逐内核 uri_rule
TROJAN_REALITY_URI = (
    "trojan://LV7CpzX9Jc8vWuhP0YV0@107.173.154.178:29602?security=reality&type=tcp"
    "&sni=audio-ssl.itunes.apple.com&fp=chrome&sid=b860a9f0"
    "&pbk=GiR4k0uVRhKEWlfD9oRjjv-C0STrp5M0uP3kRIT2pgU#TROJAN-03")


class TestPerKernelUriRule(unittest.TestCase):
    """`target_kernel`: 同一条 URI 规则对不同内核给不同结论, 且**绝不外溢**。

    事实来源: mihomo 的 trojan 分享链接解析器不读 pbk/sid（converter.go `case "trojan"`
    全文不出现 security/pbk/sid/reality, 与 upstream Meta 逐字相同）, 而同一条
    trojan+REALITY 链接 Xray/sing-box 都能用 ⇒ 这一行必须按内核分叉。
    """

    def test_row_shape(self):
        row = REG.uri_rule("trojan", "standard:reality", "mihomo")
        self.assertIsNotNone(row)
        self.assertEqual(row["uri_rule_id"], "uri.trojan.reality@mihomo")
        self.assertEqual(row["target_kernel"], "mihomo")
        self.assertEqual(row["representation"], "NONE")            # 该内核上表达力 = 无
        self.assertEqual(len(row["loss"]), 3)                      # 逐字段 loss
        self.assertTrue(row["workaround"])                         # 必须给可行替代
        self.assertTrue(row["note"])
        for eid in row["evidence"]:
            self.assertIn(eid, REG.evidence)                       # 证据可解析

    def test_same_link_two_kernels_two_verdicts(self):
        m = U(TROJAN_REALITY_URI, "mihomo", "1.19.32")
        self.assertEqual(m.status, "SUPPORTED_WITH_LOSS")
        self.assertEqual(m.levels["uri"], "SUPPORTED_WITH_LOSS")
        self.assertEqual(len(m.losses), 3)                          # losses 为 3 条
        self.assertEqual({l["rule"] for l in m.losses}, {"uri.trojan.reality@mihomo"})
        # 同一条链接, 换成 xray 仍是干净的 SUPPORTED（uri 层不因这颗规则降级）
        x = U(TROJAN_REALITY_URI, "xray", "26.3.27")
        self.assertEqual(x.status, "SUPPORTED")
        self.assertEqual(x.losses, [])
        self.assertNotEqual(x.levels["uri"], "SUPPORTED_WITH_LOSS")

    def test_no_spillover_to_other_kernels(self):
        for kernel, version in (("xray", "26.3.27"), ("singbox", "1.14.2")):
            r = U(TROJAN_REALITY_URI, kernel, version)
            self.assertNotIn("uri.trojan.reality@mihomo",
                             [l.get("rule") for l in r.losses], kernel)
            self.assertNotEqual(r.levels["uri"], "SUPPORTED_WITH_LOSS", kernel)
            # 别的内核上"没有 URI 规则"只记 UNKNOWN, 不拿 mihomo 的结论顶替
            self.assertEqual(r.levels["uri"], "UNKNOWN", kernel)
            self.assertTrue(any("没有覆盖该 scheme × feature" in u["why"]
                                for u in r.unknowns), kernel)

    def test_kernel_dimension_is_never_guessed(self):
        # 不给 kernel → 逐内核行既不返回、也不当回退（不猜）
        self.assertIsNone(REG.uri_rule("trojan", "standard:reality"))
        # 逐内核行只对它声明的内核返回
        self.assertIsNotNone(REG.uri_rule("trojan", "standard:reality", "mihomo"))
        self.assertIsNone(REG.uri_rule("trojan", "standard:reality", "xray"))
        self.assertIsNone(REG.uri_rule("trojan", "standard:reality", "singbox"))
        # 全局行（不带 target_kernel）在给了/不给 kernel 时都是回退 —— 旧调用形式行为不变
        for kernel in (None, "mihomo", "singbox"):
            row = REG.uri_rule("ss", "standard:reality", kernel)
            self.assertIsNotNone(row)
            self.assertEqual(row["uri_rule_id"], "uri.ss.reality")

    def test_target_kernel_vocabulary_is_controlled(self):
        kernels = {u.get("target_kernel") for u in REG.uri_rules if u.get("target_kernel")}
        self.assertTrue(kernels)                                   # 至少这一颗
        self.assertTrue(kernels <= {"xray", "mihomo", "singbox"})
        # 逐内核行也必须能被自带 scheme 取到（不是只写不用的死数据）
        for u in REG.uri_rules:
            if u.get("target_kernel"):
                self.assertIs(REG.uri_rule(u["scheme"], u["feature"], u["target_kernel"]), u)


# ------------------------------------------------ SB 接入实测回灌: encryption 哨兵值
SENTINEL_VLESS = ("vless://45468dde-d4e8-4aff-9428-87649b6ecd90@h:443"
                  "?encryption=none&security=tls&sni=a.com&fp=chrome&type=ws&path=/x#w")
SENTINEL_VLESS_REALITY = ("vless://893e7017-96a7-45bd-95b2-fce4b242c5b8@h:443"
                          "?encryption=none&flow=xtls-rprx-vision&security=reality"
                          "&sni=a.com&fp=chrome&pbk=K&sid=76efc989&type=tcp#r")


class TestVlessEncryptionSentinel(unittest.TestCase):
    """`encryption=none` 是分享链接规范的**哨兵值**（= 不做 VLESS Encryption）, 不是特性。

    假 UNSUPPORTED 比 UNKNOWN 更糟: 修前每一条常规 vless 链接都会被
    `singbox.vless.encryption.never` 判死（CC 上 13 条真实链接 2 条中招, 两条都 204 可用）。
    """

    def test_sentinel_does_not_create_the_feature(self):
        p = parse_uri(SENTINEL_VLESS)
        self.assertIsNone(p.get_feature("standard:vless.encryption"))
        self.assertEqual(p.raw_fields["encryption"], "none")       # 原值仍逐字保留（I2）
        self.assertNotIn("encryption", [e["key"] for e in p.extensions])  # 也不当未建模键
        self.assertEqual(p.check_invariants(), [])
        self.assertEqual(p.roundtrip().to_dict(), p.to_dict())

    def test_sentinel_is_written_back_verbatim(self):
        # 哨兵值不建 feature, 但用户显式写过 → 回写时不许静默丢参数
        p = parse_uri(SENTINEL_VLESS)
        out = generate_uri(p)
        self.assertIn("encryption=none", out)
        p2 = parse_uri(out)
        self.assertEqual(p2.raw_fields, p.raw_fields)
        self.assertEqual([f.id for f in p2.features], [f.id for f in p.features])

    def test_sentinel_link_is_not_false_unsupported(self):
        for uri in (SENTINEL_VLESS, SENTINEL_VLESS_REALITY):
            for kernel, version in KERNELS.items():
                tags = ["with_utls"] if kernel == "singbox" else None
                r = U(uri, kernel, version, build_tags=tags)
                self.assertNotEqual(r.status, "UNSUPPORTED", f"{uri}/{kernel}")
                self.assertNotIn("KERNEL_NEVER_SUPPORTED", r.reason_codes,
                                 f"{uri}/{kernel}")
        # 修正前这条是 UNSUPPORTED（SB 侧实测 204 可用的节点被判死）
        r = U(SENTINEL_VLESS_REALITY, "singbox", "1.14.2", build_tags=["with_utls"])
        self.assertEqual(r.status, "SUPPORTED")

    def test_sentinel_is_case_insensitive_and_only_the_literal_none(self):
        p = parse_uri("vless://u@h:443?encryption=NONE&security=tls")
        self.assertIsNone(p.get_feature("standard:vless.encryption"))
        for real in ("mlkem768x25519plus.native.0rtt.ABC", "aes-128-gcm", "none2"):
            p2 = parse_uri(f"vless://u@h:443?encryption={real}&security=tls")
            feat = p2.get_feature("standard:vless.encryption")
            self.assertIsNotNone(feat, real)                       # 真特性照旧建模
            self.assertEqual(feat.params["encryption"].v, real)     # 值原样
            self.assertIn(f"encryption={real}", generate_uri(p2))

    def test_real_vless_encryption_is_still_judged(self):
        # 这条**必须**保持现状: 真 VLESS Encryption 不受哨兵值修正的影响
        for real in ("mlkem768x25519plus.native.0rtt.ABC", "aes-128-gcm"):
            uri = f"vless://u@h:443?encryption={real}&security=tls&type=ws&path=/x"
            s = U(uri, "singbox", "1.14.2", build_tags=["with_utls"])
            self.assertEqual(s.status, "UNSUPPORTED", real)         # sing-box 完全没有
            self.assertIn("KERNEL_NEVER_SUPPORTED", s.reason_codes, real)
            self.assertEqual(U(uri, "xray", "26.3.27").status, "SUPPORTED", real)
            self.assertEqual(U(uri, "mihomo", "1.19.32").status,
                             "SUPPORTED_WITH_WARNING", real)
            # uri 层判定确实参与了（不是"没规则 → 靠 UNKNOWN 蒙过去"）
            self.assertNotEqual(s.levels["uri"], "UNKNOWN", real)


# ------------------------------------------------ SB 接入实测回灌: build tag 门控
class TestSingboxBuildTagRequirements(unittest.TestCase):
    """hysteria2/tuic 要 `with_quic`, naive 要 `with_naive_outbound`（源码门控 + stub 报错）。"""

    HY2 = "hysteria2://pw@h:443?sni=a.com"
    TUIC = "tuic://u:p@h:443?sni=a.com"

    def test_hysteria2_and_tuic_need_with_quic(self):
        for uri in (self.HY2, self.TUIC):
            bad = U(uri, "singbox", "1.14.2", build_tags=["with_utls", "with_naive_outbound"])
            self.assertEqual(bad.status, "UNSUPPORTED", uri)         # 明确没有 with_quic → 判死
            self.assertIn("BUILD_NOT_ENABLED", bad.reason_codes, uri)
            ok = U(uri, "singbox", "1.14.2", build_tags=["with_utls", "with_quic"])
            self.assertNotIn("BUILD_NOT_ENABLED", ok.reason_codes, uri)
            self.assertEqual(ok.status, "SUPPORTED", uri)            # 这俩在 sing-box 上是支持的

    def test_missing_tags_stay_unknown_not_build_not_enabled(self):
        # tags 缺失 = **未知**（不是"确定没有"）→ 不许判 BUILD_NOT_ENABLED
        for uri in (self.HY2, self.TUIC):
            r = U(uri, "singbox", "1.14.2")
            self.assertNotIn("BUILD_NOT_ENABLED", r.reason_codes, uri)
            self.assertNotEqual(r.status, "UNSUPPORTED", uri)
            self.assertTrue(any("build" in u["what"] for u in r.unknowns), uri)
        # 同一条语义的先例（reality 要 with_utls）行为一致
        pre = U("vless://u@h:443?type=tcp&security=reality&pbk=K", "singbox", "1.14.2")
        self.assertNotIn("BUILD_NOT_ENABLED", pre.reason_codes)
        self.assertTrue(any("build" in u["what"] for u in pre.unknowns))
        # tags=[] 是"确定没有", 与缺失必须区别对待（反向验证机制有效）
        empty = U("vless://u@h:443?type=tcp&security=reality&pbk=K", "singbox", "1.14.2",
                  build_tags=[])
        self.assertIn("BUILD_NOT_ENABLED", empty.reason_codes)

    def test_naive_rule_pins_with_naive_outbound(self):
        rule = next(r for r in REG.rules if r.rule_id == "singbox.protocol.naive")
        self.assertEqual(rule.target.get("kernel"), "singbox")
        self.assertEqual(rule.selector, {"protocol": "standard:naive"})
        self.assertEqual([s.requires_build_tags for s in rule.segments],
                         [["with_naive_outbound"]])
        self.assertTrue(rule.evidence)
        for eid in rule.evidence:
            self.assertIn(eid, REG.evidence)
        # 行为验证: compat 还没有 naive:// 解析, 只能把 protocol 换成 naive 来驱动这条规则
        p = parse_uri("vless://u@h:443")
        p.protocol = Feature(id="standard:naive", presence=Presence.EXPLICIT,
                             provenance=Provenance.URI)
        r = evaluate(p, T("singbox", "1.14.2", build_tags=[]), REG)
        self.assertIn("BUILD_NOT_ENABLED", r.reason_codes)           # 缺 tag → 绝不放行
        r2 = evaluate(p, T("singbox", "1.14.2", build_tags=["with_naive_outbound"]), REG)
        self.assertNotIn("BUILD_NOT_ENABLED", r2.reason_codes)
        r3 = evaluate(p, T("singbox", "1.14.2"), REG)                # tags 未知
        self.assertNotIn("BUILD_NOT_ENABLED", r3.reason_codes)
        self.assertTrue(any("build" in u["what"] for u in r3.unknowns))


class TestCliLoadUnknownScheme(unittest.TestCase):
    """CLI 不许把认不出的 scheme 当文件路径崩掉。

    实测: RN 上真实的 `naive+https://…`（sb_share-naive01-TLS.txt）不在原来那张硬编码
    白名单里 → `check` 直接 FileNotFoundError（整批检查崩掉）。库层一直是对的
    （unknown: 协议 → UNKNOWN），坏的只是 CLI 的入口判断。
    """

    NAIVE = ("naive+https://e53bd040a419:f695c3946d09@107.173.154.178:31008"
             "?sni=hxicc.catmicos.dpdns.org#rn naive01-TLS")

    def test_unknown_scheme_uri_is_parsed_not_opened(self):
        from proxy_node_compat.cli import _load
        p = _load(self.NAIVE)
        self.assertTrue(p.protocol.id.startswith("unknown:"))        # 不猜成已知协议
        r = evaluate(p, T("singbox", "1.14.2"), REG)
        self.assertIn(r.status, ("UNKNOWN", "UNSUPPORTED"))           # 不假 SUPPORTED
        self.assertEqual(r.raw_uri, self.NAIVE)                      # 原文不丢

    def test_real_file_and_json_paths_still_load(self):
        from proxy_node_compat.cli import _load
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("vless://u@h:443?security=tls#from-file\n")
            name = fh.name
        try:
            self.assertEqual(_load(name).protocol.id, "standard:vless")
        finally:
            os.unlink(name)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump(parse_uri("vless://u@h:443?security=tls").to_dict(), fh)
            name2 = fh.name
        try:
            self.assertEqual(_load(name2).protocol.id, "standard:vless")
        finally:
            os.unlink(name2)
        self.assertRaises(FileNotFoundError, _load, "no-such-file.txt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
