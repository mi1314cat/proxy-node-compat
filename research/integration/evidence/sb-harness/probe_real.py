#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实连通性实测: 每个节点起一个临时 sing-box（mixed 入站, 127.0.0.1 高位端口）,
curl 测 HTTP 码 / 耗时 / 出口 IP。

只在 /tmp 里写配置; 每个实例跑完立刻 kill。生产 sing-box 不动。
"""
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import time

V = "/tmp/sbc-verify"
KERNEL = "/opt/sb-client/core/sing-box"
RUNDIR = os.path.join(V, "run")
PROBE_URL = "https://www.gstatic.com/generate_204"
IP_URL = "https://api.ipify.org"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_port(port, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def probe(obs, label, extra_env=None):
    """obs: 该节点需要的出站列表（含 detour 依赖）。返回 (结果dict)"""
    port = free_port()
    d = os.path.join(RUNDIR, label.replace("/", "_").replace(" ", "_"))
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    cfg = {"log": {"level": "error"},
           "inbounds": [{"type": "mixed", "tag": "in", "listen": "127.0.0.1",
                         "listen_port": port}],
           "outbounds": list(obs) + [{"type": "direct", "tag": "direct"}]}
    cfgp = os.path.join(d, "cfg.json")
    with open(cfgp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False)
    # 先让内核自己 check 一遍: 配置期就拒绝的, 直接记下来（这是最硬的证据）
    chk = subprocess.run([KERNEL, "check", "-c", cfgp, "-D", d],
                         capture_output=True, text=True, timeout=30)
    res = {"label": label, "check_rc": chk.returncode,
           "check_err": (chk.stderr or chk.stdout or "").strip().splitlines()[-1:],
           "code": None, "secs": None, "ip": None, "err": ""}
    if chk.returncode != 0:
        return res
    p = subprocess.Popen([KERNEL, "run", "-c", cfgp, "-D", d],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        if not wait_port(port):
            try:
                _, e = p.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                e = b""
            res["err"] = "内核没起来: " + (e or b"").decode("utf-8", "replace").strip()[-160:]
            return res
        env = dict(os.environ)
        env["no_proxy"] = "127.0.0.1,localhost"
        if extra_env:
            env.update(extra_env)
        c = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-m", "15",
                            "--socks5-hostname", "127.0.0.1:%d" % port,
                            "-w", "%{http_code} %{time_total}", PROBE_URL],
                           capture_output=True, text=True, env=env)
        parts = (c.stdout or "").split()
        if len(parts) == 2:
            res["code"], res["secs"] = parts[0], parts[1]
        else:
            res["err"] = (c.stderr or "")[:120]
        if res["code"] == "204":
            c2 = subprocess.run(["curl", "-sS", "-m", "15", "--socks5-hostname",
                                 "127.0.0.1:%d" % port, IP_URL],
                                capture_output=True, text=True, env=env)
            res["ip"] = (c2.stdout or "").strip()[:40]
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
        shutil.rmtree(d, ignore_errors=True)
    return res


def load_nodes():
    """真实节点: RN 整份 profile 的 13 个出站（带 detour 依赖）。

    必须排除"被别的出站用 detour 引用的辅助层"（shadowtls 的 X-out）—— 它不是节点,
    单独拿来拨号只会挂住（客户端 node_count() 也是这么排除的）。
    """
    prof = json.load(open(os.path.join(V, "rn", "sb_client-all.json"), encoding="utf-8"))
    by_tag = {o.get("tag"): o for o in prof["outbounds"]}
    deps = {o.get("detour") for o in prof["outbounds"] if o.get("detour")}
    out = []
    for o in prof["outbounds"]:
        t = o.get("type")
        if t in ("selector", "urltest", "direct"):
            continue
        if o.get("tag") in deps:
            continue
        chain = [o]
        dep = o.get("detour")
        if dep and dep in by_tag:
            # 主节点必须排第一 —— mixed 入站的默认出站是 outbounds 列表里的第一个,
            # 把 helper(shadowtls) 放前面等于直接用它拨号（它只是拨号层, 会静默失败）
            chain = [o, by_tag[dep]]
        out.append((o.get("tag"), chain))
    return out


def main():
    os.makedirs(RUNDIR, exist_ok=True)
    nodes = load_nodes()
    print("真实节点 %d 个（RN 整份 profile, 每节点一个临时内核实例）" % len(nodes))
    print("%-28s %-10s %-6s %-8s %-16s %s" % ("节点", "type", "HTTP", "耗时", "出口 IP", "备注"))
    rows = []
    for tag, chain in nodes:
        r = probe(chain, tag)
        note = ""
        if r["check_rc"] != 0:
            note = "配置期被拒: " + (r["check_err"][0] if r["check_err"] else "")[:70]
        elif r["err"]:
            note = r["err"][:70]
        print("%-28s %-10s %-6s %-8s %-16s %s" %
              (tag, chain[-1].get("type"), r["code"] or "-", r["secs"] or "-",
               r["ip"] or "-", note))
        rows.append(r)
    json.dump(rows, open(os.path.join(V, "out", "probe.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = sum(1 for r in rows if r["code"] == "204")
    print("  → 实测 204 通过 %d / %d" % (ok, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
