# -*- coding: utf-8 -*-
"""协议语料自检。

`tools/interop-vectors.json` 是三家互通的**公共判据**：X / M / SB 各自独立实现
同一份协议，靠这份语料对齐。语料本身如果烂掉（占位符打错、want 写成自由文本、
向量重名），比对台会**静默地少判**——那正是本项目最忌讳的一类失败。

所以这里只做一件事：把语料当数据校验，不跑任何内核实现（内核实现在各自的
仓库里、由各自的 CI 跑；跨实现比对见 `tools/interop-conformance.py`）。

运行: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VEC = os.path.join(ROOT, "tools", "interop-vectors.json")

# `interop.py` 的 R_* 常量一一对应的 reason 家族
REASON_FAMILIES = {"none", "schema", "kernel", "cross", "dist", "nourl",
                   "badurl", "self"}
PLACEHOLDERS = {"{{K}}", "{{KUP}}", "{{D}}", "{{DUP}}", "{{OTHER}}",
                "{{U}}", "{{UUP}}", "{{FTP}}"}
FORMS = {"raw", "bare", "bare-q", "full-url"}


class TestInteropCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(VEC, encoding="utf-8") as fh:
            cls.doc = json.load(fh)
        cls.vectors = cls.doc["vectors"]

    def test_schema_and_kernels(self):
        self.assertEqual(self.doc["schema"], 1)
        self.assertEqual(sorted(self.doc["kernels"]), ["mihomo", "sing-box", "xray"])

    def test_enough_vectors_and_unique_names(self):
        self.assertGreaterEqual(len(self.vectors), 20,
                                "语料太少：少于 20 条挡不住漂移")
        names = [v["name"] for v in self.vectors]
        self.assertEqual(len(names), len(set(names)), "向量重名")

    def test_every_want_in_allowed_families(self):
        for v in self.vectors:
            with self.subTest(v=v["name"]):
                parts = v["want"].split(":")
                self.assertTrue(parts, "want 不能为空")
                self.assertIn(parts[0], ("native", "uri"))
                if parts[0] == "uri":
                    self.assertEqual(len(parts), 2,
                                     "uri 家族必须写出为什么（uri:<reason>）")
                    self.assertIn(parts[1], REASON_FAMILIES)
                else:
                    self.assertEqual(len(parts), 1, "native 不带后缀")

    def test_placeholders_are_known_and_balanced(self):
        for v in self.vectors:
            with self.subTest(v=v["name"]):
                found = set(re.findall(r"\{\{[A-Z]+\}\}", v["query"]))
                self.assertTrue(found <= PLACEHOLDERS,
                                "用了没定义的占位符: %s" % (found - PLACEHOLDERS))
                # 花括号必须成对且只以 {{X}} 形式出现
                stripped = re.sub(r"\{\{[A-Z]+\}\}", "", v["query"])
                self.assertNotIn("{{", stripped)
                self.assertNotIn("}}", stripped)

    def test_forms_are_known(self):
        for v in self.vectors:
            for f in v.get("forms", []):
                with self.subTest(v=v["name"], form=f):
                    self.assertIn(f, FORMS)

    def test_declaration_vectors_cover_both_input_forms(self):
        """带 interop= 的向量必须在三种形态下都跑。

        形态敏感是真实缺陷（`://` 当判据那次就是这样），所以声明向量**默认**
        必须 `bare` / `bare-q` / `full-url` 三种形态都验。确实有语义只属于某一种
        形态的向量可以收窄，但**必须带 `_note` 写清为什么** —— 否则"收窄"就成了
        悄悄少判一条的合法借口。
        """
        n = 0
        for v in self.vectors:
            if not v["query"].upper().startswith("INTEROP="):
                continue
            forms = v.get("forms") or ["bare", "bare-q", "full-url"]
            with self.subTest(v=v["name"]):
                if forms != ["bare", "bare-q", "full-url"]:
                    self.assertIn("_note", v,
                                  "收窄入参形态必须写明理由（_note）")
                    self.assertTrue(v["_note"].strip())
                else:
                    self.assertIn("bare", forms)
                    self.assertIn("bare-q", forms, "入参形态少一种就会漏掉一类静默失败")
                    self.assertIn("full-url", forms)
            n += 1
        self.assertGreaterEqual(n, 15, "声明向量太少")

    def test_edge_vectors_present(self):
        """几条边界必须在场 —— 它们各自对应一类静默失败。"""
        names = " ".join(v["name"] for v in self.vectors)
        for must in ("无声明", "跨内核", "规范版本", "内核不在词表", "发行版不在 formats",
                     "原生地址不是 http(s)", "片段里放同名声明", "重复参数",
                     "多出不认识的参数", "同内核同发行版"):
            with self.subTest(must=must):
                self.assertIn(must, names)

    def test_declaration_equivalence_block(self):
        eq = self.doc["declaration_equivalence"]
        self.assertEqual(sorted(eq["must_param_names"]),
                         ["distribution", "formats", "interop", "kernel",
                          "url-dist-self", "version"])
        self.assertEqual(eq["formats"][0], "uri", "uri 必须排在格式清单首位")
        self.assertTrue(eq["urls"]["dist-self"].startswith("https://"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
