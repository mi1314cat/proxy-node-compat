# -*- coding: utf-8 -*-
"""注册表字段的"不许静默躺在数据里"契约。

`rules.json` 是公开数据文件。里面出现一个**看起来记录了事实**、但没有任何代码读的
字段，是这类项目最难发现的失真：读者会以为这层的精度比实际高。

所以本项目对 URI 规则字段的契约是：

  · 引擎读得出的 → 在 `registry.URI_RULE_KEYS` 里；
  · 读得出但**不参与判定**的 → 在 `registry.URI_RULE_INFORMATIONAL` 里，
    并且**必须**由 `EvaluationResult.informational` 原样带出来、带
    `affects_verdict=False`（"显式告诉用户它不影响结论"，而不是留在 JSON 里）；
  · 认不出的 → `Registry.load` 直接抛错（不许静默忽略）。

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

from proxy_node_compat import Registry, Target, evaluate, parse_uri  # noqa: E402
from proxy_node_compat.registry import (URI_RULE_INFORMATIONAL,  # noqa: E402
                                        URI_RULE_KEYS, default_registry_path)

REG = Registry.load(default_registry_path())


class TestUriRuleFieldContract(unittest.TestCase):
    def test_shipped_data_uses_only_known_keys(self):
        with open(default_registry_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        for ur in data["uri_rules"]:
            with self.subTest(rule=ur.get("uri_rule_id")):
                self.assertEqual(sorted(set(ur) - URI_RULE_KEYS), [],
                                 "数据里有认不出的字段（载入时本该报错）")

    def test_informational_is_subset_of_known(self):
        self.assertTrue(set(URI_RULE_INFORMATIONAL) <= URI_RULE_KEYS)

    def test_unknown_key_is_rejected_loudly(self):
        """加了字段但没人读 → 必须**载入即失败**，不许静默忽略。"""
        with open(default_registry_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        data["uri_rules"][0]["totally_new_field"] = "看起来像个事实"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
            name = fh.name
        try:
            with self.assertRaises(ValueError) as cm:
                Registry.load(name)
            self.assertIn("totally_new_field", str(cm.exception))
        finally:
            os.unlink(name)

    def test_informational_fields_reach_the_result(self):
        """有 `workaround` 的那条规则，结果里必须看得到它，且标明不影响判定。"""
        # uri.ss.reality 带 workaround；用一个 ss+reality 链接触发
        prof = parse_uri("ss://YWVzLTI1Ni1nY206cGFzcw==@1.2.3.4:8388"
                         "?security=reality&pbk=AAA&sid=00#SS-REALITY")
        res = evaluate(prof, Target(kernel="mihomo", version="1.19.32"), REG)
        hits = [i for i in res.informational if i.get("workaround")]
        self.assertTrue(hits, "带 workaround 的 URI 规则没有把 workaround 透出到结果里")
        for i in hits:
            self.assertIs(i.get("affects_verdict"), False,
                          "透出的参考信息必须显式标明不影响判定")
            self.assertTrue(i.get("rule"))
        self.assertIn("informational", res.to_dict())

    def test_informational_never_changes_verdict(self):
        """抽掉信息性字段，判定结果必须**逐字节不变** —— 证明它真的不参与判定。

        这是"读得出但不影响结论"这句话的**唯一**可验证形式：不是说它写在
        `INFORMATIONAL` 里就算数，而是把它删掉之后结论一模一样。
        """
        uri = ("ss://YWVzLTI1Ni1nY206cGFzcw==@1.2.3.4:8388"
               "?security=reality&pbk=AAA&sid=00#SS-REALITY")
        tgt = Target(kernel="mihomo", version="1.19.32")
        base = evaluate(parse_uri(uri), tgt, REG).to_dict()

        with open(default_registry_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        removed = 0
        for ur in data["uri_rules"]:
            for k in URI_RULE_INFORMATIONAL:
                if k in ur:
                    ur.pop(k)
                    removed += 1
        self.assertGreater(removed, 0, "数据里根本没有信息性字段，这条测试是空转")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
            name = fh.name
        try:
            reg2 = Registry.load(name)
            stripped = evaluate(parse_uri(uri), tgt, reg2).to_dict()
        finally:
            os.unlink(name)

        # informational 本身当然会变空，除此之外必须完全一致
        base.pop("informational")
        stripped.pop("informational")
        self.assertEqual(base, stripped,
                         "删掉信息性字段后判定变了 —— 那它就不是信息性的")



if __name__ == "__main__":
    unittest.main(verbosity=2)
