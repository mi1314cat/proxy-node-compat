"""Phase 4 验收测试 —— 用户指定的 18 个案例 + 版本边界红线。

运行: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from proxy_node_compat import (Field, NodeProfile, Presence, Provenance,  # noqa: E402
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
