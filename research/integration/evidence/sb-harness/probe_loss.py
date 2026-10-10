#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把"客户端转换损失"落到真实链路上验证: 损失到底是纸面结论还是真会断。

三个对照:
  A. to_sb.py 按 RN 真实 trojan01-TLS-CDN 链接转出来的出站（**丢了 TLS**）
  B. 同一节点补上 TLS（内核支持的形状）→ 作为对照
  C. RN 整份 profile 里的 shadowtls 节点（mux 那条 SUPPORTED_WITH_LOSS 的对象）
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time

V = "/tmp/sbc-verify"
KERNEL = "/opt/sb-client/core/sing-box"
RUN = os.path.join(V, "run2")
PROBE = "https://www.gstatic.com/generate_204"


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def wait_port(port, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def run_case(label, obs, debug=False):
    d = os.path.join(RUN, label.replace("/", "_").replace(" ", "_"))
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d, exist_ok=True)
    port = free_port()
    cfg = {"log": {"level": "debug" if debug else "error"},
           "inbounds": [{"type": "mixed", "tag": "in", "listen": "127.0.0.1",
                         "listen_port": port}],
           "outbounds": list(obs) + [{"type": "direct", "tag": "direct"}]}
    cfgp = os.path.join(d, "cfg.json")
    json.dump(cfg, open(cfgp, "w", encoding="utf-8"), ensure_ascii=False)
    chk = subprocess.run([KERNEL, "check", "-c", cfgp, "-D", d], capture_output=True, text=True)
    if chk.returncode != 0:
        return {"label": label, "code": "CHECK-FAIL",
                "err": (chk.stderr or chk.stdout).strip().splitlines()[-1:]}
    errf = open(os.path.join(d, "err.log"), "w")
    p = subprocess.Popen([KERNEL, "run", "-c", cfgp, "-D", d],
                         stdout=subprocess.DEVNULL, stderr=errf)
    code = secs = None
    try:
        if not wait_port(port):
            time.sleep(1)
        c = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-m", "15",
                            "--socks5-hostname", "127.0.0.1:%d" % port,
                            "-w", "%{http_code} %{time_total}", PROBE],
                           capture_output=True, text=True,
                           env={**os.environ, "no_proxy": "127.0.0.1,localhost"})
        parts = (c.stdout or "").split()
        if len(parts) == 2:
            code, secs = parts
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
        errf.close()
    err = ""
    try:
        lines = [l for l in open(os.path.join(d, "err.log"), encoding="utf-8",
                                 errors="replace").read().splitlines()
                 if "ERROR" in l or "FATAL" in l or "WARN" in l]
        err = " | ".join(lines[-2:])[:180]
    except OSError:
        pass
    return {"label": label, "code": code, "secs": secs, "err": err}


def main():
    os.makedirs(RUN, exist_ok=True)
    sys.path.insert(0, os.path.join(V, "client", "share-state"))
    import to_sb
    results = []

    # A: to_sb 转出来的（丢 TLS）
    link = open(os.path.join(V, "rn", "sb_share-trojan01-TLS-CDN.txt"), encoding="utf-8").read().strip()
    a_ob = to_sb.uri_to_outbound(link)
    results.append(run_case("A-tosb-trojan-noTLS", [a_ob], debug=True))
    # B: 同一节点补上 TLS
    b_ob = json.loads(json.dumps(a_ob))
    b_ob["tls"] = {"enabled": True, "server_name": "hxicc.catmicos.dpdns.org", "alpn": ["http/1.1"]}
    results.append(run_case("B-trojan-withTLS", [b_ob]))
    # 顺便: 补上 TLS 后再加 utls 指纹（客户端没写, 但服务端未必要求）
    # C: shadowtls 节点（整份 profile 里的原样）
    prof = json.load(open(os.path.join(V, "rn", "sb_client-all.json"), encoding="utf-8"))
    by = {o.get("tag"): o for o in prof["outbounds"]}
    c = [by["rn-shadowtls01-TLS"], by["rn-shadowtls01-TLS-out"]]
    results.append(run_case("C-shadowtls-chain", c, debug=True))
    # D: shadowtls 去掉 multiplex（对照 mux 那条"确定损失"）
    d_node = json.loads(json.dumps(by["rn-shadowtls01-TLS"])); d_node.pop("multiplex", None)
    results.append(run_case("D-shadowtls-no-mux", [d_node, by["rn-shadowtls01-TLS-out"]], debug=True))

    # E: RN 那条 sb_share-vmess02-REALITY.txt 其实是 **vless://...encryption=aes-128-gcm**
    #    （服务端分享层写错了 scheme）。compat 判 UNSUPPORTED; 验证"它真的连不通"。
    try:
        link2 = open(os.path.join(V, "rn", "sb_share-vmess02-REALITY.txt"), encoding="utf-8").read().strip()
        e_ob = to_sb.uri_to_outbound(link2)
        if e_ob:
            results.append(run_case("E-vmess02-link(vless)", [e_ob], debug=True))
    except Exception as ex:                                     # noqa: BLE001
        print("E 用例跳过:", ex)

    print("%-28s %-6s %-9s %s" % ("用例", "HTTP", "耗时", "内核日志/说明"))
    for r in results:
        print("%-28s %-6s %-9s %s" % (r["label"], r.get("code") or "-",
                                      r.get("secs") or "-", (r.get("err") or "")[:150]))
    json.dump(results, open(os.path.join(V, "out", "probe-loss.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 客户端"根本转不出来"的 scheme（compat 判 SUPPORTED 但 to_sb 直接返回 None）
    print()
    print("客户端转换器 scheme 白名单实测（to_sb.uri_to_outbound）:")
    for f in sorted(os.listdir(os.path.join(V, "rn"))):
        if not f.startswith("sb_share-"):
            continue
        link = open(os.path.join(V, "rn", f), encoding="utf-8").read().strip()
        try:
            ob = to_sb.uri_to_outbound(link)
        except Exception as ex:                                 # noqa: BLE001
            ob = "异常 %s" % ex
        scheme = link.split("://", 1)[0]
        print("   %-24s %-14s -> %s" % (f[8:-4], scheme,
                                        ("type=" + ob["type"]) if isinstance(ob, dict) else "None（转不出来）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
