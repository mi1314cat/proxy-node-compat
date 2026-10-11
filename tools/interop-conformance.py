#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三家互通 · 协议一致性台（跨实现比对，只读）。

三个内核各自独立实现了同一份「声明 / 决策」协议（X 两份逐字节副本、M 一份共用、
SB 两份逐字节副本）。**独立实现是刻意的**（各仓库不该互相依赖），代价是它们会漂移；
而漂移的表现是**静默**的：

    · 服务端写 `distribution=xray`、客户端读 `dist`   → 客户端永远走普通话，不报错
    · 一边把 `url-<fmt>` 写成 `url_<fmt>`             → 同上
    · 一边把"跨内核"判成 native                        → 客户端拿到读不懂的载荷

所以这个台子不看源码，只看**行为**：把同一批声明向量喂给每一份实现，
逐条比对 `decide()` 的 `(choice, reason, url)`；再看 `build_declaration()`
产出的查询串在**归一化之后**是否等价（参数集合、每个参数的值）。

用法:
    python3 tools/interop-conformance.py \
        --impl x-server:xray--core/conf/lib/interop.py \
        --impl x-client:xray--core/Client/lib/interop.py \
        --impl m:mihomo--core/src/lib/interop.py \
        --impl sb-server:sing-box-core/src/conf/interop.py \
        --impl sb-client:sing-box-core/src/client/lib/interop.py

退出码 0 = 全部逐条一致；1 = 有分歧（逐条打印分歧向量与两侧结果）。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.parse


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location("impl_" + name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 声明向量：每条给 (名字, 带占位符的查询串, 期望家族) ─────────────────────
# 「期望」只写**家族**（native / uri + 为什么），不写具体实现文案 —— 文案本来
# 就允许多写几个字，判据是"该不该拿原生"，那才是协议。
# 占位符（materialize 负责替换，全部带花括号，避免和正文撞车）:
#   {{K}} 本机内核名（小写）   {{KUP}} 本机内核名（大写）
#   {{D}} 本机发行版标签       {{DUP}} 发行版（大写）
#   {{OTHER}} 另一个内核名     {{U}} 原生取件地址（https，已转义）
#   {{UUP}} 原生地址 scheme 写成大写 HTTPS
#   {{FTP}} 不是 http(s) 的地址
_VEC_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "interop-vectors.json")
VECTORS_INLINE = [
    ("无声明",                 "",                                                       "uri:none"),
    ("有地址但无查询串",        "{{U}}",                                                   "uri:none"),
    ("同内核同发行版",          "interop=1&kernel={{K}}&distribution={{D}}&version=1&formats=uri,{{D}}&url-{{D}}={{U}}", "native"),
    ("规范版本=2(不认识)",      "interop=2&kernel={{K}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}", "uri:schema"),
    ("规范版本非数字",          "interop=x&kernel={{K}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}", "uri:schema"),
    ("内核不在词表",            "interop=1&kernel=nonsense&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}", "uri:kernel"),
    ("缺 kernel",              "interop=1&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}", "uri:kernel"),
    ("跨内核",                 "interop=1&kernel={{OTHER}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}", "uri:cross"),
    ("发行版不在 formats",      "interop=1&kernel={{K}}&distribution={{D}}&formats=uri&url-{{D}}={{U}}", "uri:dist"),
    ("发行版在 formats 但无地址", "interop=1&kernel={{K}}&distribution={{D}}&formats=uri,{{D}}",  "uri:nourl"),
    ("原生地址不是 http(s)",    "interop=1&kernel={{K}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{FTP}}", "uri:badurl"),
    ("原生地址只有 scheme",     "interop=1&kernel={{K}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}=https:", "uri:badurl"),
    ("formats 里多一个别的格式", "interop=1&kernel={{K}}&distribution={{D}}&formats=uri,{{D}},other&url-{{D}}={{U}}", "native"),
    ("大写内核名",             "interop=1&kernel={{KUP}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}", "native"),
    ("内核名带前后空白",        "interop=1&kernel=%20{{K}}%20&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}", "native"),
    ("发行版/参数名大小写混写",  "INTEROP=1&KERNEL={{KUP}}&DISTRIBUTION={{DUP}}&FORMATS=uri,{{DUP}}&URL-{{DUP}}={{U}}", "native"),
    ("原生地址 scheme 大写",    "interop=1&kernel={{K}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{UUP}}", "native"),
    ("片段里放同名声明(不算)",   "interop=1&kernel={{K}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}#kernel={{OTHER}}", "native"),
    ("重复参数取第一个",        "interop=1&kernel={{OTHER}}&kernel={{K}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}", "uri:cross"),
    ("formats 为空",           "interop=1&kernel={{K}}&distribution={{D}}&formats=&url-{{D}}={{U}}", "uri:dist"),
    ("多出不认识的参数",        "interop=1&kernel={{K}}&distribution={{D}}&formats=uri,{{D}}&url-{{D}}={{U}}&whatever=1&ssid=2", "native"),
]

def load_vectors() -> list:
    """优先读 tools/interop-vectors.json（协议语料的唯一真源）；读不到用内联表。"""
    try:
        with open(_VEC_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        vs = d.get("vectors") or []
        if vs:
            return vs
    except (OSError, ValueError):
        pass
    return VECTORS_INLINE


VECTORS = load_vectors()

SELF_DIST = "dist-self"
SELF_URL = "https://example.invalid/native"
_OTHER = {"xray": "mihomo", "mihomo": "sing-box", "sing-box": "xray"}


def materialize(qs: str, impl, my: str = "") -> str:
    """把向量里的占位符换成这份实现的真实词表值（长占位符先换）。"""
    my = my or getattr(impl, "MY_KERNEL", None) or ""
    other = _OTHER.get(my, "xray")
    rep = [
        ("{{KUP}}", my.upper()),
        ("{{K}}", my),
        ("{{DUP}}", SELF_DIST.upper()),
        ("{{D}}", SELF_DIST),
        ("{{OTHER}}", other),
        ("{{UUP}}", urllib.parse.quote("HTTPS://example.invalid/native", safe="")),
        ("{{FTP}}", urllib.parse.quote("ftp://x/y", safe="")),
        ("{{U}}", urllib.parse.quote(SELF_URL, safe="")),
    ]
    for k, v in rep:
        qs = qs.replace(k, v)
    return qs


def kernel_of(impl, path: str = "") -> str:
    """这份实现认为"我是哪个内核"。

    优先 `MY_KERNEL`（M 有）；X / SB 把内核名写死在 `self_facts()` 里，所以退一步
    调 `self_facts()` —— 它在**探测不到二进制**时也会如实返回 `kernel` 字段
    （只是 `ok=False`），正好是我们要的那个词表值。两条都不行就扫源码里的词表字面量。
    """
    k = getattr(impl, "MY_KERNEL", None)
    if k:
        return str(k)
    try:
        f = impl.self_facts() or {}
        if f.get("kernel"):
            return str(f["kernel"])
    except Exception:                                        # noqa: BLE001
        pass
    if path:
        try:
            src = open(path, encoding="utf-8").read()
        except OSError:
            src = ""
        for cand in ("xray", "sing-box", "mihomo"):
            if '"%s"' % cand in src:
                return cand
    return ""


FULL_URL_PREFIX = "http://subscribe.invalid/share/main-token"


def _forms_of(v: dict) -> list:
    """每条向量跑哪几种入参形态。

    `raw` = 把 query 字段原样当输入（用于"整条地址"或"什么都没有"这两条）；
    `bare` = 裸查询串（协议承诺支持的形态）；
    `bare-q` = `?` + 裸查询串（还有一种入参是"问号开头的查询串"）；
    `full-url` = 把它拼在一个完整订阅地址的 `?` 后面（生产主路径）。
    **同一条向量在三种形态下有不同决策，本身就是缺陷** —— 所以默认三种都跑。
    """
    f = v.get("forms")
    if f:
        return list(f)
    if v.get("query", "").upper().startswith("INTEROP="):
        return ["bare", "bare-q", "full-url"]
    return ["raw"]


def run_impl(impl, path: str):
    out = []
    my = kernel_of(impl, path)
    for v in VECTORS:
        name, want = v["name"], v["want"]
        for form in _forms_of(v):
            q = materialize(v["query"], impl, my)
            if form == "full-url":
                raw = FULL_URL_PREFIX + "?" + q
            elif form == "bare-q":
                raw = "?" + q
            else:
                raw = q
            decl = impl.parse_declaration(raw) if raw else None
            choice, reason, url, detail = impl.decide(decl, my, SELF_DIST)
            got = "native" if choice == impl.CHOICE_NATIVE else "uri"
            fam = want.split(":")[0]
            out.append({
                "key": "%s|%s" % (name, form), "vector": name, "form": form,
                "want": want, "choice": got, "reason": reason,
                "url": url, "detail": detail, "ok": got == fam,
            })
    return out


def norm_decl(qs: str) -> dict:
    """归一化一条声明查询串 → {参数: 值}（用于 build_declaration 的等价比对）。"""
    flat = {k: v[-1] for k, v in urllib.parse.parse_qs(qs, keep_blank_values=True).items()}
    return flat


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", action="append", required=True,
                    help="name:path，可重复（同一份实现出现多次会各自单独验）")
    a = ap.parse_args()
    loaded = []
    for spec in a.impl:
        name, _, path = spec.partition(":")
        if not path:
            print("--impl 要写成 name:path", file=sys.stderr)
            return 2
        try:
            loaded.append((name, load(name, path), path))
        except Exception as exc:                              # noqa: BLE001
            print("\033[31m加载失败\033[0m %s (%s): %s" % (name, path, exc))
            return 2

    print("═══ 实现清单 ═══")
    for name, mod, path in loaded:
        print("  %-12s kernel=%-9s schema=%s  %s"
              % (name, kernel_of(mod, path) or "?",
                 getattr(mod, "INTEROP_SCHEMA", "?"), path))

    results = {name: run_impl(mod, path) for name, mod, path in loaded}

    print("\n═══ ① decide() 行为一致性（语料 %d 条 × 入参形态） ═══" % len(VECTORS))
    bad = 0
    keys = [r["key"] for r in results[loaded[0][0]]]
    for i, key in enumerate(keys):
        cells = []
        for name, _mod, _p in loaded:
            r = results[name][i]
            cells.append("%s=%s/%s" % (name, r["choice"], r["reason"]))
        choices = {results[n][i]["choice"] for n, _m, _p in loaded}
        # 期望家族也一起判：实现自己跑错（与设计不符）同样要红
        selfbad = [n for n, _m, _p in loaded if not results[n][i]["ok"]]
        mark = "\033[32m✓\033[0m"
        if len(choices) > 1 or selfbad:
            mark = "\033[31m✗\033[0m"
            bad += 1
        r0 = results[loaded[0][0]][i]
        print("  %s [%-8s] %-26s 期望=%-12s %s"
              % (mark, r0["form"], r0["vector"], r0["want"], "  ".join(cells)))
        if len(choices) > 1:
            for n, _m, _p in loaded:
                print("        %-12s url=%r detail=%s"
                      % (n, results[n][i]["url"], results[n][i]["detail"]))
        elif selfbad:
            for n in selfbad:
                print("        %-12s 与设计不符: got=%s want=%s"
                      % (n, results[n][i]["choice"], r0["want"]))

    # 同一向量在"裸查询串"与"完整地址"两种形态下决策不同 → 单独报（形态敏感）
    print("\n═══ ①b 入参形态敏感性（裸查询串 / ?+裸查询串 / 完整地址 必须同判） ═══")
    by_name = {}
    for i, key in enumerate(keys):
        r0 = results[loaded[0][0]][i]
        by_name.setdefault(r0["vector"], {})[r0["form"]] = i
    for vname, forms in by_name.items():
        if len(forms) < 2:
            continue
        diff = []
        for n, _m, _p in loaded:
            seen = {}
            for f in sorted(forms):
                r = results[n][forms[f]]
                seen.setdefault((r["choice"], r["reason"], r["url"]), []).append(f)
            if len(seen) > 1:
                diff.append("%s[%s]" % (n, " vs ".join(
                    "%s=%s/%s" % ("+".join(fl), k[0], k[1]) for k, fl in seen.items())))
        if diff:
            bad += 1
            print("  \033[31m✗\033[0m %-26s 形态敏感: %s" % (vname, "; ".join(diff)))
        else:
            print("  \033[32m✓\033[0m %-26s %d 种形态决策逐字段一致" % (vname, len(forms)))

    print("\n═══ ② build_declaration() 产出一致性（归一化后逐参数比） ═══")
    decls = {}
    for name, mod, _p in loaded:
        qs = mod.declaration_query(mod.build_declaration(
            kernel_of(mod, _p), SELF_DIST, "9.9.9",
            formats=(mod.FORMAT_URI, SELF_DIST), urls={SELF_DIST: SELF_URL}))
        decls[name] = norm_decl(qs)
        print("  %-12s %s" % (name, qs))
    keysets = {frozenset(d) for d in decls.values()}
    if len(keysets) > 1:
        bad += 1
        print("  \033[31m✗\033[0m 参数名集合不一致:")
        for k in sorted(set().union(*keysets)):
            who = [n for n, d in decls.items() if k in d]
            if len(who) != len(decls):
                print("        %-14s 只有 %s 有" % (k, ",".join(who)))
    else:
        print("  \033[32m✓\033[0m 参数名集合一致: %s" % ", ".join(sorted(keysets.pop())))
    # 同内核同发行版 → 互相认得（把 A 的声明喂给 B 的 parse+decide）
    print("\n═══ ③ 交叉可读性（A 产出的声明，B 读懂并判 native） ═══")
    for a_name, a_mod, _p in loaded:
        for b_name, b_mod, _p2 in loaded:
            ak, bk = kernel_of(a_mod, _p), kernel_of(b_mod, _p2)
            if ak != bk:
                continue          # 跨内核本来就该走 uri，不在这里判
            qs = a_mod.declaration_query(a_mod.build_declaration(
                ak, SELF_DIST, "9.9.9",
                formats=(a_mod.FORMAT_URI, SELF_DIST), urls={SELF_DIST: SELF_URL}))
            d = b_mod.parse_declaration(qs)
            c, reason, url, _detail = b_mod.decide(d, bk, SELF_DIST)
            okc = c == b_mod.CHOICE_NATIVE and url == SELF_URL
            if not okc:
                bad += 1
            print("  %s %-12s → %-12s %s/%s url=%r"
                  % ("\033[32m✓\033[0m" if okc else "\033[31m✗\033[0m",
                     a_name, b_name, c, reason, url))

    print("\n" + "=" * 66)
    if bad:
        print("\033[31m分歧/不符 %d 条 —— 独立实现已经漂移，且这类漂移在运行期是静默的。\033[0m" % bad)
    else:
        print("\033[32m全部一致：%d 组向量 × %d 份实现，决策 / 参数名 / 交叉可读性零分歧。\033[0m"
              % (len(VECTORS), len(loaded)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
