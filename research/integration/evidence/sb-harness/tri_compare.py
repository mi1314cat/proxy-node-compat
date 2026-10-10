#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐节点三方对比: 旧判定 / compat / 合并。数据全部是 CC 上的真实产物。"""
import glob
import json
import os
import sys

V = os.environ.get("CLIENT_ROOT", "/tmp/sbc-verify/client")
sys.path.insert(0, os.path.join(V, "share-state"))
sys.path.insert(0, os.path.join(V, "share-state", "lib"))
import compat2  # noqa: E402

RN = "/tmp/sbc-verify/rn"
KERNEL = "/opt/sb-client/core/sing-box"


def tgt():
    t, meta = compat2.target_of(KERNEL)
    return t, meta


def main():
    t, meta = tgt()
    print("目标: kernel=%s distribution=%s version=%s" % (t.kernel, t.distribution, t.version))
    print("build_tags (%d): %s" % (len(t.build_tags or []), ",".join(t.build_tags or [])))
    print("revision=%s" % (meta.get("revision") or "?"))
    print()

    # ---------------- 表 A: 真实分享链接（RN 自己生成的 13 条）
    links = []
    for f in sorted(glob.glob(os.path.join(RN, "sb_share-*.txt"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if "://" in line:
                links.append((os.path.basename(f)[8:-4], line))
    print("== 表 A · URI 路径（RN 真实分享链接 %d 条）" % len(links))
    print("%-22s %-12s %-14s %-14s %-10s %s" %
          ("节点", "旧判定", "compat", "合并", "依据", "说明"))
    tally = {"relax": 0, "tighten": 0, "same": 0, "fallback": 0}
    rows = []
    for tag, uri in links:
        r = compat2.judge(uri=uri, tgt=t)
        lv = (r["legacy"] or {}).get("verdict")
        cv = (r["compat"] or {}).get("status")
        mv = r["verdict"]
        if lv == "UNSUPPORTED" and mv != "UNSUPPORTED":
            tally["relax"] += 1
        if lv == "SUPPORTED" and mv == "UNSUPPORTED":
            tally["tighten"] += 1
        if lv == mv:
            tally["same"] += 1
        if "legacy（" in (r["verdict_source"] or ""):
            tally["fallback"] += 1
        note = "; ".join(r["message"])[:88]
        if r["client_losses"]:
            note = (note + " ⚠转换丢: " + r["client_losses"][0]["what"])[:110]
        print("%-22s %-12s %-14s %-14s %-10s %s" %
              (tag, lv, cv, mv, r["verdict_source"][:9], note))
        rows.append({"tag": tag, "uri": uri, "legacy": lv, "compat": cv,
                     "merged": mv, "src": r["verdict_source"],
                     "rc": r["reason_codes"], "msg": r["message"],
                     "losses": (r["compat"] or {}).get("losses"),
                     "unknowns": (r["compat"] or {}).get("unknowns"),
                     "ext": r["extensions"], "raw_uri": r["raw_uri"],
                     "client_losses": r["client_losses"],
                     "rules": (r["compat"] or {}).get("rules_applied")})
    print("  → 小计: 一致 %d / 收紧 %d / 放松 %d（必须 0）/ 回退旧判定 %d"
          % (tally["same"], tally["tighten"], tally["relax"], tally["fallback"]))

    # ---- 表 A2: 关掉已知缺陷绕行（SB_COMPAT_NO_SHIMS=1）会怎样
    os.environ["SB_COMPAT_NO_SHIMS"] = "1"
    flip = []
    for tag, uri in links:
        r = compat2.judge(uri=uri, tgt=t)
        old = [x for x in rows if x["tag"] == tag][0]
        if old["merged"] != r["verdict"]:
            flip.append((tag, old["merged"], r["verdict"], r["reason_codes"]))
    del os.environ["SB_COMPAT_NO_SHIMS"]
    print()
    print("== 表 A2 · 关掉绕行（SB_COMPAT_NO_SHIMS=1）后翻转的节点: %d" % len(flip))
    for tag, a, b, rc in flip:
        print("   %-24s %s → %s  %s" % (tag, a, b, rc))
    json.dump(rows, open("/tmp/sbc-verify/out/tri-uri.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---------------- 表 B: sing-box JSON 路径（RN 整份 profile + CC 生产节点文件）
    print()
    print("== 表 B · JSON 路径（客户端以前逐节点不判）")
    obs = []
    prof = json.load(open(os.path.join(RN, "sb_client-all.json"), encoding="utf-8"))
    for o in prof["outbounds"]:
        if o.get("type") not in ("selector", "urltest", "direct"):
            obs.append(("RN:" + o.get("tag", "?"), o))
    nfiles = 0
    for f in sorted(glob.glob("/opt/sb-client/nodes/node-*.json")):
        nfiles += 1
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for o in j.get("outbounds", []):
            if o.get("type") not in ("selector", "urltest", "direct"):
                obs.append((os.path.basename(f)[5:-5] + "/" + (o.get("tag") or "?"), o))
    print("  生产节点文件 %d 个, 出站 %d 个（含 RN 整份 profile 的 %d 个）"
          % (nfiles, len(obs), len(prof["outbounds"]) - 3))
    print("%-40s %-11s %-14s %-8s %s" % ("节点", "type", "compat", "合并", "依据/说明"))
    tally2 = {"unsup": 0, "loss": 0, "ok": 0, "unk": 0}
    rows2 = []
    for tag, o in obs:
        r = compat2.judge(outbound=o, tag=tag, tgt=t)
        cv = (r["compat"] or {}).get("status")
        note = (r["message"] or [""])[0][:80]
        if not r["ok"]:
            tally2["unsup"] += 1
        elif (r["compat"] or {}).get("losses"):
            tally2["loss"] += 1
        elif cv == "UNKNOWN":
            tally2["unk"] += 1
        else:
            tally2["ok"] += 1
        if not r["ok"] or (r["compat"] or {}).get("losses") or cv == "UNKNOWN":
            print("%-40s %-11s %-14s %-8s %s" % (tag[:40], o.get("type"), cv, r["verdict"], note))
        rows2.append({"tag": tag, "type": o.get("type"), "compat": cv,
                      "merged": r["verdict"], "ok": r["ok"], "rc": r["reason_codes"],
                      "msg": r["message"], "losses": (r["compat"] or {}).get("losses"),
                      "unknowns": (r["compat"] or {}).get("unknowns"),
                      "ext": r["extensions"],
                      "rules": (r["compat"] or {}).get("rules_applied")})
    print("  → 小计: 无问题 %d / 有确定损失 %d / 判不支持 %d / 未知 %d"
          % (tally2["ok"], tally2["loss"], tally2["unsup"], tally2["unk"]))
    json.dump(rows2, open("/tmp/sbc-verify/out/tri-json.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---------------- 假 UNSUPPORTED / 退步 检查
    print()
    print("== 检查项")
    relax = [r for r in rows if r["legacy"] == "UNSUPPORTED" and r["merged"] != "UNSUPPORTED"]
    print("  放松（旧说不支持→新说支持）: %d" % len(relax))
    unsup = [r for r in rows2 if not r["ok"]]
    print("  JSON 路径判不支持的出站: %d %s" % (len(unsup), [r["tag"] for r in unsup][:8]))
    unk = [r for r in rows2 if r["compat"] == "UNKNOWN"]
    print("  compat 判 UNKNOWN（回退旧判定, 不算判死）: %d" % len(unk))
    return 0


if __name__ == "__main__":
    sys.exit(main())
