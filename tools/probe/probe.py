#!/usr/bin/env python3
"""probe.py — 用**真内核**给能力库产出证据（本项目唯一可信的 "Runtime Support" 来源）。

设计原则（与 docs/00-design-principles.md 一致）:

* **数据驱动**: 内核怎么调用、用例长什么样都在 `cases.json` 里; 这里不写 `if kernel == ...`
  的判断地狱, 只负责"拼配置 → 跑内核 → 记录结论"。
* **不猜**: 拿不到结论就是 `harness_error`, 不许降级成 PASS/FAIL。
* **控制组**: 每个内核都有一条必然通过的对照用例。对照都不过 = 探针本身坏了,
  这一轮的结果整体作废(而不是让所有用例看起来"不支持")。

两层探针:

  Tier A `static`   —— 把片段拼成完整配置, 跑内核自己的校验器
                       (xray -test / mihomo -t / sing-box check)
  Tier B `loopback` —— 起真服务端 + 真客户端, 从客户端代理端口 curl 目标地址。
                       **这一层才能抓出"校验通过但运行时静默降级"**。

用法:
    python3 tools/probe/probe.py --kernels xray,mihomo,singbox \\
        --config tools/probe/kernels.example.json --out research/empirical
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CASES = os.path.join(HERE, "cases.json")


# --------------------------------------------------------------------------- 内核适配
@dataclass
class Kernel:
    """一个内核怎么被调用。全部来自配置文件, 不在代码里写死。"""

    name: str
    binary: str
    version_cmd: list[str]
    validate_cmd: list[str]  # 用 {config} / {workdir} 占位
    run_cmd: list[str]  # Tier B 起进程用
    config_suffix: str
    wrapper: dict[str, Any]  # 把片段包成完整配置的模板

    def version(self) -> str:
        try:
            out = subprocess.run(self.version_cmd, capture_output=True, text=True, timeout=30)
            text = (out.stdout or "") + (out.stderr or "")
            return text.strip().splitlines()[0] if text.strip() else "unknown"
        except Exception as exc:  # noqa: BLE001
            return f"<version error: {exc}>"


@dataclass
class CaseResult:
    case_id: str
    feature: str
    kernel: str
    verdict: str  # accepted | rejected | harness_error
    detail: str = ""
    evidence: str = "test"
    layer: str = "static"


def build_config(kernel: Kernel, fragment: dict[str, Any]) -> str:
    """按内核的 wrapper 模板把片段拼成完整配置。

    wrapper 里 `{"__fragment__": "<key>"}` 的占位会被片段替换 —— 这样
    "片段要塞到哪个键下面" 也是数据, 不是代码。
    """
    filled = json.loads(json.dumps(kernel.wrapper))  # deep copy

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "__fragment__" in node:
                key = node["__fragment__"]
                item = fragment.get(key)
                return item if item is not None else node.get("default")
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return json.dumps(walk(filled), ensure_ascii=False, indent=1)


def run_static(kernel: Kernel, case: dict[str, Any], workdir: str) -> CaseResult:
    frags = case["fragments"]
    if kernel.name not in frags:
        return CaseResult(case["id"], case["feature"], kernel.name, "harness_error",
                          "用例没有声明该内核（数据缺失, 不是内核行为）")
    fragment = frags[kernel.name]
    if fragment is None:
        # 这个内核的配置模型里**根本没有**对应字段 —— 这是结论, 不是错误。
        # 记成 not_representable: Kernel Representation 这一层缺失。
        return CaseResult(case["id"], case["feature"], kernel.name, "not_representable",
                          "该内核配置模型中无对应字段")
    text = build_config(kernel, fragment)
    path = os.path.join(workdir, f"{case['id'].replace('.', '_')}{kernel.config_suffix}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

    cmd = [c.replace("{config}", path) for c in kernel.validate_cmd]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        return CaseResult(case["id"], case["feature"], kernel.name, "harness_error",
                          f"内核调用失败: {exc}")
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode == 0:
        # 校验通过 ≠ 支持。有些字段内核根本不校验（实测 mihomo 不验 `network`）,
        # 这种用例的 accepted 必须降级成 accepted_unverified, 只有 Tier B 能定论。
        if kernel.name in (case.get("tier_b_required") or []):
            return CaseResult(case["id"], case["feature"], kernel.name, "accepted_unverified",
                              "校验通过, 但该字段不被此内核校验 —— 需回环验证 (Tier B)")
        return CaseResult(case["id"], case["feature"], kernel.name, "accepted",
                          _first_interesting(out))
    return CaseResult(case["id"], case["feature"], kernel.name, "rejected",
                      _first_interesting(out))


def _first_interesting(text: str) -> str:
    """从内核输出里挑一行最能说明问题的（错误优先）。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        low = ln.lower()
        if any(k in low for k in ("error", "fatal", "unknown", "invalid", "unsupport",
                                  "failed", "no such", "not support")):
            return ln[:240]
    return (lines[-1][:240] if lines else "")


# --------------------------------------------------------------------------- Tier B
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def run_loopback(scenario: dict[str, Any], kernels: dict[str, Kernel],
                 workdir: str, target_port: int) -> list[CaseResult]:
    """起服务端内核 + 客户端内核, 从客户端代理端口取回目标内容。

    scenario 需要提供: server_kernel / server_config / client_kernel / client_config
    / client_proxy_port / expect (期望取到的内容)
    """
    results: list[CaseResult] = []
    sk, ck = kernels.get(scenario["server_kernel"]), kernels.get(scenario["client_kernel"])
    if not sk or not ck:
        return [CaseResult(scenario["id"], scenario.get("feature", ""), "?", "harness_error",
                           "scenario 指定的内核不存在")]
    for label, k in (("server", sk), ("client", ck)):
        if not os.path.exists(k.binary):
            return [CaseResult(scenario["id"], scenario.get("feature", ""), k.name,
                               "harness_error", f"{label} 内核二进制不存在: {k.binary}")]

    sfile = os.path.join(workdir, f"{scenario['id']}-server{k_suffix(sk)}")
    cfile = os.path.join(workdir, f"{scenario['id']}-client{k_suffix(ck)}")
    with open(sfile, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(scenario["server_config"], ensure_ascii=False, indent=1))
    with open(cfile, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(scenario["client_config"], ensure_ascii=False, indent=1))

    procs: list[subprocess.Popen] = []
    try:
        procs.append(_spawn(sk, sfile, workdir, "server"))
        time.sleep(2.5)
        procs.append(_spawn(ck, cfile, workdir, "client"))
        time.sleep(3.0)

        proxy = f"socks5h://127.0.0.1:{scenario['client_proxy_port']}"
        url = f"http://127.0.0.1:{target_port}/"
        try:
            got = subprocess.run(["curl", "-s", "--max-time", "10", "-x", proxy, url],
                                 capture_output=True, text=True, timeout=25).stdout.strip()
        except Exception as exc:  # noqa: BLE001
            got = f"<curl error: {exc}>"
        expect = scenario.get("expect", "COMPAT-OK")
        # expect_connect=False 的用例是"静默降级探测器": **连不上才是预期**。
        # 连上了说明内核把不认识的字段当成默认值用了 —— 这正是最危险的一类。
        want_connect = scenario.get("expect_connect", True)
        connected = (got == expect)
        # 回环层四个结论各说各的事, 不混用 accepted/rejected ——
        # "静默降级"和"不支持"是完全不同的两件事, 混在一起客户端没法处理。
        if want_connect:
            if connected:
                verdict, detail = "works", "取回内容符合预期"
            else:
                verdict, detail = "unreachable", f"期望连通, 实际 {got[:120]!r}"
        else:
            if connected:
                verdict = "silent_fallback"
                detail = ("**连上了** —— 不认识的字段被静默当成默认值用了 "
                          f"(取回 {got[:60]!r})。这正是本项目要挡掉的情况。")
            else:
                verdict, detail = "refused", "未连通 —— 符合预期（不认识的配置没有被放行）"
        results.append(CaseResult(scenario["id"], scenario.get("feature", ""), ck.name,
                                  verdict, detail, layer="loopback"))
    finally:
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass
    return results


def k_suffix(k: Kernel) -> str:
    return k.config_suffix


def _spawn(kernel: Kernel, config: str, workdir: str, role: str) -> subprocess.Popen:
    cmd = [c.replace("{config}", config).replace("{workdir}", workdir)
           for c in kernel.run_cmd]
    log = open(os.path.join(workdir, f"{kernel.name}-{role}.log"), "w", encoding="utf-8")
    return subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=workdir)


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="用真内核探测能力支持情况")
    ap.add_argument("--kernels", default="xray,mihomo,singbox")
    ap.add_argument("--config", default=os.path.join(HERE, "kernels.example.json"))
    ap.add_argument("--cases", default=DEFAULT_CASES)
    ap.add_argument("--out", default="research/empirical")
    ap.add_argument("--only", default="", help="只跑 id 含该子串的用例")
    ap.add_argument("--skip-loopback", action="store_true")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        raw = json.load(fh)
    # 配置里 `_` 开头的键是注释/元数据, 不是内核
    kernels = {name: Kernel(name=name, **cfg)
               for name, cfg in raw.items() if not name.startswith("_")}
    with open(args.cases, encoding="utf-8") as fh:
        cases = json.load(fh)

    wanted = [k.strip() for k in args.kernels.split(",") if k.strip()]
    workdir = tempfile.mkdtemp(prefix="pnc-probe-")
    os.makedirs(args.out, exist_ok=True)

    versions = {k: kernels[k].version() for k in wanted if k in kernels}
    print("内核版本:")
    for k, v in versions.items():
        print(f"  {k:10s} {v}   ({kernels[k].binary})")
    missing = [k for k in wanted if not os.path.exists(kernels[k].binary)]

    results: list[CaseResult] = []
    controls_ok: dict[str, bool] = {}

    # ---- 控制组先行: 它不过, 后面所有结论都不可信
    for case in cases["static"]:
        if not case.get("control"):
            continue
        for name in wanted:
            if name not in kernels or name in missing:
                continue
            r = run_static(kernels[name], case, workdir)
            controls_ok[name] = (r.verdict == "accepted")
            if not controls_ok[name]:
                print(f"  !! 对照用例 {case['id']} 在 {name} 上没通过: {r.detail}", file=sys.stderr)

    for case in cases["static"]:
        if case.get("control") or (args.only and args.only not in case["id"]):
            continue
        for name in wanted:
            if name not in kernels or name in missing:
                continue
            if controls_ok.get(name) is False:
                results.append(CaseResult(case["id"], case["feature"], name, "harness_error",
                                          "该内核的对照用例未通过, 本轮结论不可信"))
                continue
            results.append(run_static(kernels[name], case, workdir))

    # ---- Tier B: 语义回环
    if not args.skip_loopback and "loopback" in cases:
        import http.server
        import threading

        www = os.path.join(workdir, "www")
        os.makedirs(www, exist_ok=True)
        with open(os.path.join(www, "index.html"), "w", encoding="utf-8") as fh:
            fh.write("COMPAT-OK")
        port = _free_port()

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):  # noqa: D102
                pass

        handler = lambda *a, **kw: Quiet(*a, directory=www, **kw)  # noqa: E731
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        for sc in cases["loopback"]:
            if args.only and args.only not in sc["id"]:
                continue
            if sc["server_kernel"] in missing or sc["client_kernel"] in missing:
                continue
            results.extend(run_loopback(sc, kernels, workdir, port))
        httpd.shutdown()

    # ---- 落盘
    stamp = time.strftime("%Y-%m-%d")
    payload = {
        "generated": stamp,
        "kernels": {k: {"version": v, "binary": kernels[k].binary} for k, v in versions.items()},
        "controls_ok": controls_ok,
        "results": [asdict(r) for r in results],
    }
    out_json = os.path.join(args.out, "probe-results.json")
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    # ---- 打印矩阵
    by_id: dict[str, dict[str, str]] = {}
    for r in results:
        by_id.setdefault(f"{r.case_id} [{r.layer}]", {})[r.kernel] = r.verdict
    print(f"\n{'用例':52s} " + " ".join(f"{k:>10s}" for k in wanted))
    for cid, row in by_id.items():
        marks = []
        for k in wanted:
            v = row.get(k, "-")
            marks.append({"accepted": "✅", "accepted_unverified": "✅?", "rejected": "❌",
                          "not_representable": "—", "harness_error": "⚠️",
                          "works": "✅通", "unreachable": "❌不通",
                          "silent_fallback": "🚨静默降级", "refused": "✅已拒绝",
                          "-": "·"}.get(v, v))
        print(f"{cid:52s} " + " ".join(f"{m:>10s}" for m in marks))
    unver = [r for r in results if r.verdict == "accepted_unverified"]
    bad = [r for r in results if r.verdict == "harness_error"]
    if unver:
        print(f"\n注意: {len(unver)} 条是 ✅?（校验器不验该字段, 只有回环能定论）: "
              + ", ".join(sorted({f"{r.case_id}/{r.kernel}" for r in unver})[:6]))
    print(f"\n结果: {len(results)} 条, 其中探针自身问题 {len(bad)} 条 → {out_json}")
    if bad:
        print("探针自身的问题(结论不可用, 需要修探针而不是记成'不支持'):")
        for r in bad[:8]:
            print(f"  - {r.case_id} / {r.kernel}: {r.detail[:100]}")
    shutil.rmtree(workdir, ignore_errors=True)
    return 0 if not any(r.verdict == "harness_error" for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
