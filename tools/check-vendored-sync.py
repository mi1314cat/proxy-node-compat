#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""canonical ↔ 各内核 vendor 副本一致性（只读）。

`proxy_node_compat/` 是本仓库的**唯一权威**（canonical）。三个内核各自 vendor 一份
只读副本（它们不依赖本仓库、也不联网）：

    xray--core       Client/lib/proxy_node_compat/
    mihomo--core     src/lib/proxy_node_compat/
    sing-box-core    src/client/lib/proxy_node_compat/

副本会**静默滞后** —— 而滞后的表现是"内核给出的能力判定比 canonical 旧"，
不会报错：

  · `uri.py` 少了 `encryption=none` 哨兵值处理 → 每一条常规 vless 链接被
    `singbox.vless.encryption.never` 判成**假 UNSUPPORTED**（实测 13 条真实链接里 2 条中招，
    两条都真连 204 可用）；
  · `cli.py` 还是硬编码 scheme 白名单 → 白名单外的真实链接（`naive+https://…`）
    被当成文件路径 → `FileNotFoundError` **整批崩掉**；
  · `data/rules.json` 少几条规则/证据 → 某类节点从"明确不支持"退化成"未知"或反过来。

这些都不是"少个文件"那种一眼能看出来的缺失，所以必须**逐字节**比。

用法:
    python3 tools/check-vendored-sync.py \
        --vendor xray:../xray--core/Client/lib/proxy_node_compat \
        --vendor mihomo:../mihomo--core/src/lib/proxy_node_compat \
        --vendor sing-box:../sing-box-core/src/client/lib/proxy_node_compat

    # 只要某些目录缺失就视为失败（默认行为）；确实只装了一部分时可加 --allow-missing
退出码 0 = 全部逐字节相同；1 = 有滞后/缺失。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

# canonical 里"必须被 vendor 走"的清单 —— 少一个都会让内核侧静默退化。
# `__pycache__` 之类的编译副产物不算。
FILES = [
    "__init__.py",
    "__main__.py",
    "cli.py",
    "engine.py",
    "model.py",
    "registry.py",
    "uri.py",
    os.path.join("data", "rules.json"),
]


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 16), b""):
            h.update(blk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proxy_node_compat"))
    ap.add_argument("--vendor", action="append", required=True, help="name:path")
    ap.add_argument("--allow-missing", action="store_true",
                    help="目录不存在时记 SKIP 而不是 FAIL（默认 FAIL：静默跳过正是要防的）")
    ap.add_argument("--extra", action="append", default=[],
                    help="除清单外还要比的相对路径（可重复）")
    a = ap.parse_args()

    canon = os.path.abspath(a.canonical)
    if not os.path.isdir(canon):
        print("\033[31mcanonical 目录不存在: %s\033[0m" % canon)
        return 2
    files = list(FILES) + list(a.extra)

    print("canonical: %s" % canon)
    for f in files:
        p = os.path.join(canon, f)
        if not os.path.isfile(p):
            print("  \033[31mcanonical 自己缺 %s —— 门禁无法成立\033[0m" % f)
            return 2
    print("要比 %d 个文件" % len(files))

    bad = 0
    for spec in a.vendor:
        name, _, path = spec.partition(":")
        path = os.path.abspath(path or "")
        print("\n── %s  %s ──" % (name, path))
        if not os.path.isdir(path):
            if a.allow_missing:
                print("  \033[33mSKIP\033[0m 目录不存在（--allow-missing）")
                continue
            print("  \033[31mFAIL\033[0m 目录不存在 —— 不是『没有差异』，是『没能验』")
            bad += 1
            continue
        for f in files:
            cp, vp = os.path.join(canon, f), os.path.join(path, f)
            if not os.path.isfile(vp):
                print("  \033[31mMISSING\033[0m %s" % f)
                bad += 1
                continue
            hc, hv = sha(cp), sha(vp)
            if hc == hv:
                print("  \033[32m✓\033[0m %-18s %s" % (f, hc[:16]))
            else:
                print("  \033[31m✗\033[0m %-18s canonical %s / vendor %s" % (f, hc[:16], hv[:16]))
                bad += 1
        # 反向：vendor 里多出来的 .py 也算漂移（多一份旧实现比少一份更危险）
        for root, _dirs, fs in os.walk(path):
            if "__pycache__" in root:
                continue
            for fn in fs:
                rel = os.path.relpath(os.path.join(root, fn), path)
                if rel in files or not fn.endswith(".py"):
                    continue
                print("  \033[31mEXTRA\033[0m %s（canonical 里没有，可能是旧实现残留）" % rel)
                bad += 1

    print("\n" + "=" * 62)
    if bad:
        print("\033[31m滞后/缺失 %d 处 —— 内核的能力判定与 canonical 不一致，且不会报错。\033[0m" % bad)
    else:
        print("\033[32m全部副本与 canonical 逐字节一致。\033[0m")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
