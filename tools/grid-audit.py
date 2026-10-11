#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三家互通 · 九宫格中立复核台（只读）。

    python3 grid-audit.py --x <URL> --m <URL> --sb <URL> [--json]

做三件事，全部只读、不依赖任何一家客户端的实现：

  ① **声明合法性**：把三条带声明的订阅地址按 `docs/three-way-interop.md` 的规范
     解析一遍 —— 缺 `interop` 标记、内核词表不在 `{xray,sing-box,mihomo}`、
     `formats` 里没有 `uri`、声明了格式却没给 `url-<fmt>`、地址不是 http(s)，
     逐条报出来。**不认识就说不知道**，不替它补默认值。
  ② **惰性可证性**：同一 token 带声明 vs 去掉查询串，两次 GET 的响应体 sha256
     必须逐字节相同 —— 这是"第三方客户端原样拉走带声明的地址仍然拿到原载荷"的
     唯一证据，必须在真服务上现测，不能引用历史结论。
  ③ **载荷形态**：正文是 base64 的 URI 列表 / 明文 URI 列表 / mihomo YAML /
     sing-box JSON —— 只按可验证的结构判，判不出来记 UNKNOWN，并给出前后几十字节
     让人自己看。

退出码：0 = 三条声明全部合法且惰性可证；1 = 有不合法项（逐条打印）。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request

KERNELS = ("xray", "sing-box", "mihomo")
URI_SCHEMES = ("vless", "vmess", "trojan", "ss", "ssr", "hysteria2", "hy2",
               "hysteria", "tuic", "anytls", "naive", "naive+https", "shadowtls",
               "socks", "http", "https", "wireguard", "ssh")


def http_get(url: str, timeout: float = 20.0):
    """→ (status, headers, body_bytes, err)。**不跟随重定向**（要看见真实的取件行为）。"""
    req = urllib.request.Request(url, headers={"User-Agent": "grid-audit/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(), ""
    except urllib.error.HTTPError as e:                       # noqa: PERF203
        return e.code, dict(e.headers or {}), e.read(), ""
    except Exception as exc:                                  # noqa: BLE001
        return 0, {}, b"", "%s: %s" % (type(exc).__name__, exc)


def parse_decl(url: str) -> dict:
    """把一个订阅地址拆成 (裸地址, 声明 dict)。声明缺失 → decl=None。"""
    u = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qs(u.query, keep_blank_values=True)
    flat = {k: v[-1] for k, v in q.items()}
    base = urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, "", ""))
    if "interop" not in flat:
        return {"base": base, "decl": None, "query": flat}
    return {"base": base, "decl": flat, "query": flat}


def resolve_ref(ref: str, base: str) -> str:
    """把 `url-<fmt>` 的相对引用按**主地址的 scheme://netloc** 拼成绝对地址。

    契约（2026-10-11，三家逐条相同）：只认"**单个 `/` 开头且原样末段非空**"。
    `//other.host/x`（协议相对）、`/share/`、`../x`、`x/y` 一律**原样返回** ——
    不许猜、不许 urljoin。拼不出来就让下游按 `bad-native-url` 处理。

    ★ 判据必须看**原样**末段：先 `rstrip("/")` 再看末段的话，`/share/` 会变成
      "末段=share" 被判成合法路径，拼出 `http://h:9443/share/` 这条**看起来合法**的死链
      （X 侧第一版就是这么错的，门禁当场红）。
    """
    if not ref.startswith("/") or ref.startswith("//"):
        return ref
    last = ref.rsplit("/", 1)[-1]
    if not last:
        return ref
    u = urllib.parse.urlsplit(base)
    if not u.scheme or not u.netloc:
        return ref
    return "%s://%s%s" % (u.scheme, u.netloc, ref)


def check_decl(name: str, url: str) -> tuple[list[str], dict]:
    """→ (问题列表, 归一化后的声明)。问题为空 = 合法。"""
    bad: list[str] = []
    p = parse_decl(url)
    d = p["decl"]
    print("\n── ① %s 声明合法性 ──" % name)
    print("   裸地址      : %s" % p["base"])
    if d is None:
        bad.append("地址上没有 interop 标记 —— 这不是一条声明")
        print("   \033[31m✗\033[0m 没有声明（客户端只能走普通话，且不知道自己为什么走）")
        return bad, {}

    print("   规范化查询串: %s" % "&".join(
        "%s=%s" % (k, d[k]) for k in sorted(d)))
    ver = d.get("interop", "")
    if ver != "1":
        bad.append("interop=%r 不是本实现认识的规范版本 1" % ver)
        print("   \033[31m✗\033[0m interop=%r（规范版本不认识 → 客户端必须整条不认）" % ver)
    else:
        print("   \033[32m✓\033[0m interop=1（规范版本）")

    k = d.get("kernel", "")
    if k not in KERNELS:
        bad.append("kernel=%r 不在词表 %s" % (k, list(KERNELS)))
        print("   \033[31m✗\033[0m kernel=%r 不在词表 %s" % (k, list(KERNELS)))
    else:
        print("   \033[32m✓\033[0m kernel=%s" % k)

    dist = d.get("distribution", "")
    if not dist:
        bad.append("缺 distribution")
        print("   \033[31m✗\033[0m 缺 distribution（服务端不知道自己的发行版 → 不该产出声明）")
    else:
        print("   \033[32m✓\033[0m distribution=%s" % dist)

    fmts = [x for x in d.get("formats", "").split(",") if x]
    if "uri" not in fmts:
        bad.append("formats=%r 里没有 uri（uri 必须恒在）" % d.get("formats", ""))
        print("   \033[31m✗\033[0m formats=%r 里没有 uri" % d.get("formats", ""))
    else:
        print("   \033[32m✓\033[0m formats=%s（uri 在）" % ",".join(fmts))
    for f in fmts:
        if f == "uri":
            continue
        raw = d.get("url-%s" % f, "")
        if not raw:
            bad.append("声明了格式 %s 却没给 url-%s" % (f, f))
            print("   \033[31m✗\033[0m 声明了 %s 却没有 url-%s" % (f, f))
            continue
        u = resolve_ref(raw, p["base"])
        rel = "" if u == raw else "  （相对引用，按主地址 origin 拼成绝对地址）"
        if not re.match(r"^https?://", u):
            bad.append("url-%s 不是可用的 http(s) 地址: %r" % (f, u))
            print("   \033[31m✗\033[0m url-%s 不是可用的 http(s) 地址: %r" % (f, u))
        else:
            print("   \033[32m✓\033[0m url-%s = %s%s" % (f, u, rel))
        d["url-%s" % f] = u
    if dist and fmts and dist not in fmts:
        # 不是错误：fork 的客户端本来就不该拿原生。但要看得见。
        print("   \033[33m!\033[0m distribution=%s 不在 formats 里 —— 同内核同发行版的客户端也拿不到原生" % dist)
    return bad, d


def body_kind(body: bytes) -> str:
    """只按可验证的结构判载荷形态；判不出来 → UNKNOWN。"""
    if not body:
        return "EMPTY"
    txt = None
    for enc in ("utf-8", "latin-1"):
        try:
            txt = body.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if txt is None:
        return "UNKNOWN(非文本)"
    s = txt.strip()
    # base64 的 URI 列表
    if re.fullmatch(r"[A-Za-z0-9+/\n\r=_\-]+", s) and len(s) > 16:
        try:
            dec = base64.b64decode(s + "=" * (-len(s) % 4), validate=False).decode("utf-8", "replace")
            lines = [x for x in dec.strip().splitlines() if x.strip()]
            if lines and all(any(x.startswith(sc + "://") for sc in URI_SCHEMES) for x in lines):
                return "base64(URI 列表, %d 行)" % len(lines)
        except Exception:                                     # noqa: BLE001
            pass
    # 明文 URI 列表：允许 `#` 注释行与空行（**但要把注释数报出来** ——
    # "普通话"如果三家各带各的方言，第三方解析器的容忍度就是个必须验证的前提，
    # 而不是可以假设的东西）。
    body = [x for x in s.splitlines() if x.strip() and not x.lstrip().startswith("#")]
    comments = sum(1 for x in s.splitlines() if x.strip().startswith("#"))
    if body and all(any(x.startswith(sc + "://") for sc in URI_SCHEMES) for x in body):
        return "URI 列表(%d 行, 明文%s)" % (
            len(body), ", 另有 %d 行 # 注释" % comments if comments else "")
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and "outbounds" in obj:
            ob = obj["outbounds"] or []
            # Xray 的出站用 `protocol`；sing-box 用 `type`。两家都叫 outbounds，
            # 不区分的话会把 Xray 原生产物报成 sing-box —— 这正是"看起来像"的坑。
            if ob and isinstance(ob[0], dict) and "protocol" in ob[0]:
                fam = "Xray JSON"
            elif ob and isinstance(ob[0], dict) and "type" in ob[0]:
                fam = "sing-box JSON"
            else:
                fam = "outbounds JSON(家族不明)"
            return "%s(outbounds=%d%s)" % (
                fam, len(ob),
                ", interop=%s/kernel=%s" % (obj.get("interop"), obj.get("kernel"))
                if "interop" in obj else "")
        if isinstance(obj, dict) and "proxies" in obj:
            return "mihomo YAML/JSON(proxies=%d)" % len(obj["proxies"])
    except Exception:                                         # noqa: BLE001
        pass
    if re.search(r"^proxies:", s, re.M):
        n = len(re.findall(r"^\s*-\s*\{?\s*name:", s, re.M)) or \
            len(re.findall(r"^\s*-\s*name:", s, re.M))
        return "mihomo YAML(proxies≈%d)" % n
    if re.search(r"^outbounds:", s, re.M):
        return "sing-box JSON/YAML(outbounds=…)"
    return "UNKNOWN(前 60 字节: %r)" % s[:60]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--x"), ap.add_argument("--m"), ap.add_argument("--sb")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    urls = [("X (xray--core)", a.x), ("M (mihomo--core)", a.m), ("SB (sing-box-core)", a.sb)]
    urls = [(n, u) for n, u in urls if u]
    if not urls:
        print("至少要给一条 --x/--m/--sb 地址")
        return 1

    report, allbad = {}, []
    for name, url in urls:
        bad, decl = check_decl(name, url)
        allbad += ["%s: %s" % (name, b) for b in bad]
        base = parse_decl(url)["base"]

        print("\n── ② %s 惰性可证（带声明 vs 去查询串） ──" % name)
        s1, h1, b1, e1 = http_get(url)
        s2, h2, b2, e2 = http_get(base)
        n1, n2 = hashlib.sha256(b1).hexdigest(), hashlib.sha256(b2).hexdigest()
        print("   带声明: HTTP %s  %d B  sha256 %s%s" % (s1, len(b1), n1[:16], (" ERR " + e1) if e1 else ""))
        print("   裸地址: HTTP %s  %d B  sha256 %s%s" % (s2, len(b2), n2[:16], (" ERR " + e2) if e2 else ""))
        if s1 == s2 and n1 == n2 and b1:
            print("   \033[32m✓\033[0m 逐字节相同 —— 声明对载荷零影响（第三方拉走也拿到原载荷）")
            inert = True
        else:
            print("   \033[31m✗\033[0m 两次响应不同 —— 声明不是惰性的（或服务本身不稳定）")
            allbad.append("%s: 声明非惰性 (HTTP %s vs %s, sha %s vs %s)" % (name, s1, s2, n1[:8], n2[:8]))
            inert = False

        print("\n── ③ %s 载荷形态 ──" % name)
        kind = body_kind(b1)
        print("   主产品: %s" % kind)
        if h1:
            print("   Content-Type: %s" % h1.get("Content-Type", "-"))

        # 原生产品：声明里的 url-<非 uri 格式>
        for f in [x for x in (decl.get("formats", "").split(",") if decl else []) if x and x != "uri"]:
            nu = decl.get("url-%s" % f, "")
            if not nu:
                continue
            print("\n── ③b %s 原生产品（%s） ──" % (name, f))
            s3, h3, b3, e3 = http_get(nu)
            print("   HTTP %s  %d B  sha256 %s%s" % (s3, len(b3), hashlib.sha256(b3).hexdigest()[:16], (" ERR " + e3) if e3 else ""))
            if s3 == 200 and b3:
                print("   形态: %s" % body_kind(b3))
                print("   自描述: %s" % (b3[:180].decode("utf-8", "replace").replace("\n", " ")))
            else:
                allbad.append("%s: 原生产品 url-%s 取不到 (HTTP %s)" % (name, f, s3))
                print("   \033[31m✗\033[0m 声明了原生却取不到")
        report[name] = {"base": base, "decl": decl, "inert": inert,
                        "primary": {"status": s1, "bytes": len(b1), "sha256": n1, "kind": kind}}

    print("\n" + "=" * 66)
    if allbad:
        print("\033[31m不合法 %d 条:\033[0m" % len(allbad))
        for b in allbad:
            print("  · %s" % b)
    else:
        print("\033[32m三条声明全部合法，且惰性已现测可证。\033[0m")
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if allbad else 0


if __name__ == "__main__":
    sys.exit(main())
