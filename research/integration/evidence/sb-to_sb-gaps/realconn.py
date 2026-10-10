#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真连验证器（只写 /tmp）: 逐 outbound 起一个隔离 sing-box 实例, 走它发真实请求。

判据（用户点名）: curl generate_204 的 HTTP 码 + 出口 IP。
  * 204 单独不算成功 —— 出口 IP 必须是 RN 的 CF 出口 104.28.x.x
  * 出口 IP 不是 104.28.x.x（或拿不到）→ NOT_CF
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time

BIN = os.environ.get("SB_BIN", "/tmp/sbgap/sing-box-1.14.2")
WAIT = float(os.environ.get("SB_WAIT", "4"))
CURL_T = os.environ.get("SB_CURL_T", "8")


def free_base():
    return int(os.environ.get("SB_PORT_BASE", "21500"))


def wait_listen(port, proc, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False
        s = socket.socket()
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except OSError:
            time.sleep(0.05)
        finally:
            s.close()
    return False


def curl(port, url):
    p = subprocess.run(["curl", "-s", "-m", CURL_T, "-o", "/dev/null",
                        "-w", "%{http_code}", "-x", "http://127.0.0.1:%d" % port, url],
                       capture_output=True, text=True)
    return (p.stdout or "").strip() or "000"


def curl_body(port, url):
    p = subprocess.run(["curl", "-s", "-m", CURL_T, "-x", "http://127.0.0.1:%d" % port, url],
                       capture_output=True, text=True)
    return (p.stdout or "").strip()


def run_one(ob, idx, workdir):
    tag = ob.get("tag") or ("node%d" % idx)
    port = free_base() + idx
    d = os.path.join(workdir, "n%02d" % idx)
    os.makedirs(d, exist_ok=True)
    cfg = {"log": {"level": "error", "timestamp": True},
           "inbounds": [{"type": "mixed", "tag": "mix",
                         "listen": "127.0.0.1", "listen_port": port}],
           "outbounds": [ob, {"type": "direct", "tag": "direct"}],
           "route": {"final": ob.get("tag")}}
    cp = os.path.join(d, "config.json")
    with open(cp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=1)

    # 1) 内核自己的 check
    chk = subprocess.run([BIN, "check", "-c", cp], capture_output=True, text=True, timeout=30)

    # 2) 真跑
    lp = os.path.join(d, "kernel.log")
    with open(lp, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen([BIN, "run", "-c", cp], stdout=lf, stderr=lf)
    rec = {"tag": tag, "type": ob.get("type"), "check_rc": chk.returncode,
           "check_err": (chk.stderr or "").strip()[:400], "port": port}
    try:
        if not wait_listen(port, proc, WAIT):
            rec["started"] = False
        else:
            rec["started"] = True
            rec["http204"] = curl(port, "http://www.gstatic.com/generate_204")
            rec["ipify"] = curl_body(port, "https://api.ipify.org")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
    with open(lp, encoding="utf-8", errors="replace") as fh:
        rec["kernel_log"] = fh.read()[-700:]
    ip = rec.get("ipify") or ""
    rec["cf_exit"] = bool(ip.startswith("104.28."))
    rec["ok"] = bool(rec.get("started") and rec.get("http204") == "204" and rec["cf_exit"])
    return rec


def main():
    obs_path, out_path = sys.argv[1], sys.argv[2]
    only = sys.argv[3] if len(sys.argv) > 3 else ""
    data = json.load(open(obs_path, encoding="utf-8"))
    obs = data["outbounds"] if isinstance(data, dict) else data
    work = out_path + ".work"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    recs = []
    for i, ob in enumerate(obs):
        if only and only not in (ob.get("tag") or ""):
            continue
        r = run_one(ob, i, work)
        recs.append(r)
        print("%-4s %-34s check=%s start=%-5s 204=%-4s ip=%-16s %s"
              % ("OK" if r["ok"] else "FAIL", r["tag"][:34], r["check_rc"],
                 r.get("started"), r.get("http204", "-"), r.get("ipify", "-"),
                 "" if r["ok"] else (r["kernel_log"].strip().splitlines()[-1][:120]
                                     if r["kernel_log"].strip() else r["check_err"][:120])),
              flush=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(recs, fh, ensure_ascii=False, indent=1)
    ok = sum(1 for r in recs if r["ok"])
    print("\n== 真连(204 + 出口 104.28.x.x) %d/%d ==" % (ok, len(recs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
