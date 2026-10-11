# -*- coding: utf-8 -*-
"""数据文件的脱敏卫生（canonical 自己的责任）。

`proxy_node_compat/data/rules.json` 会被**逐字节 vendor** 进三个内核各自的公开仓库。
那些仓库的脱敏口径并不相同（有的会把真机地址全部替换成占位符），于是只要 canonical
里写了一个真值，副本就面临二选一：**要么破坏自己的脱敏门禁，要么让"逐字节相同"
这条最好写最好跑的门禁带一个例外** —— 而例外机制就是漂移的入口。

所以脱敏是 **canonical 自己的责任**，不是下游的：

* 这个文件里不许出现真机公网地址 / DDNS 域名 / 凭据 / 节点标识；
* 证据要证的是"出口是那台机器的 CDN 出口，不是本机"这类**性质**，
  具体数值留在 `research/` 下的真机原始记录里（那些文件不 vendor）。

这条测试是**可移植的**：它不依赖任何下游仓库的私有规则表，只用公开可判定的模式。
（下游还有自己更严的规则，那是下游的事；这里保证的是"canonical 不往里塞东西"。）

运行: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "proxy_node_compat", "data", "rules.json")

# 公网 IPv4：排除 RFC1918 / 回环 / 链路本地 / 文档用段 / TEST-NET / 保留
SAFE4 = (r"0\.|10\.|127\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\."
         r"|192\.0\.2\.|198\.51\.100\.|203\.0\.113\.|22[4-9]\.|23\d\.|24\d\.|255\.")

DDNS_SUFFIX = (r"dpdns\.org|duckdns\.org|no-ip\.(?:org|com)|dynv6\.net|ddns\.net"
               r"|my\.to|hopto\.org|zapto\.org|serveftp\.com|3utilities\.com")

PATTERNS = [
    ("公网 IPv4",
     re.compile(r"(?<![\d.])(?!(?:" + SAFE4 + r"))"
                r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
                r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b")),
    ("动态域名", re.compile(r"\b[a-z0-9][-a-z0-9.]*\.(?:" + DDNS_SUFFIX + r")\b", re.I)),
    ("GitHub PAT", re.compile(r"\b(?:github_pat_|ghp_)[A-Za-z0-9_]{20,}")),
    ("UUID", re.compile(r"(?<![0-9a-fA-F-])(?![0-9a-f-]{36}\b\s*(?:示例|placeholder|占位))"
                        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                        r"(?![0-9a-fA-F-])")),
    ("32 位十六进制（分享 token / 指纹）", re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{32}(?![0-9a-fA-F])")),
]


class TestDataHygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(DATA, encoding="utf-8") as fh:
            cls.text = fh.read()
        cls.doc = json.loads(cls.text)

    def test_no_real_machine_identifiers(self):
        hits = []
        for name, pat in PATTERNS:
            for m in pat.finditer(self.text):
                s = max(0, m.start() - 70)
                hits.append("%s: %r  ← …%s…"
                            % (name, m.group(0),
                               self.text[s:m.end() + 70].replace("\n", " ")))
        self.assertEqual(hits, [],
                         "canonical 数据文件里出现了真机标识 —— 它会被逐字节 vendor 进"
                         "三个公开仓库，写真值就会逼下游给门禁开例外：\n  "
                         + "\n  ".join(hits))

    def test_placeholder_convention_is_documented(self):
        """占位符约定要写在文件头 —— 否则下一个人会把真值填回来。"""
        head = self.doc["_comment"]
        blob = "\n".join(head) if isinstance(head, list) else str(head)
        self.assertIn("<CDN_IP>", blob)
        self.assertIn("vendor", blob)

    def test_counts_unchanged(self):
        """脱敏不该动数据语义。"""
        self.assertEqual(len(self.doc["rules"]), 68)
        self.assertEqual(len(self.doc["evidence"]), 29)
        self.assertEqual(len(self.doc["uri_rules"]), 13)


if __name__ == "__main__":
    unittest.main(verbosity=2)
