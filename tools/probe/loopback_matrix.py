#!/usr/bin/env python3
"""loopback_matrix.py — 跨内核能力矩阵的**真内核回环**探针（在 RN 主机上运行）。

设计纪律（与 docs/evidence-model.md 一致）:
  * Tier A: 内核自带校验器 (xray -test / mihomo -t / sing-box check) —— 只证明"配置层接受"
  * Tier B: 真服务端 + 真客户端回环, 从客户端 socks 口 curl 目标 —— 只这一层能证明"真能跑"
  * 控制组: 每个内核都有一条必然通过的用例; 控制组不过 => 本轮结果作废
  * 不猜: 跑不通就是 RUNTIME_FAIL, 拿不到结论就是 UNKNOWN, 不许降级成 PASS/FAIL

用法（在 rn 上）:
    python3 /tmp/xtest/loopback_matrix.py --only ctrl- --out /tmp/xtest/results.json
    python3 /tmp/xtest/loopback_matrix.py --all
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

XRAY = "/usr/local/bin/xray"
MIHOMO = "/root/catmi/mihomo/mihomo"
SINGBOX = "/root/catmi/sing-box/sing-box"

WORK = "/tmp/xtest"
CFGD = os.path.join(WORK, "cfg")
LOGD = os.path.join(WORK, "log")
ORIGIN_DIR = os.path.join(WORK, "origin")
ORIGIN_BODY = "COMPAT-OK-ORIGIN"

UUID = "b831381d-6324-4d53-ad4f-8cda48b30811"
SS_METHOD = "2022-blake3-aes-128-gcm"

# 由 setup() 填
SS_KEY = ""
RPRIV = ""
RPUB = ""
RPUB_OTHER = ""
SID = "0123456789abcdef"
SNI = "www.microsoft.com"          # reality 真站 SNI
DEST = "www.microsoft.com:443"     # reality steal-oneself 目标
ECH_INNER = "www.microsoft.com"
ECH_OUTER = "cover.example.com"
ECH_CONF = ""      # 与 ECH_SRVKEYS 配对
ECH_SRVKEYS = ""
ECH_CONF_OTHER = ""  # 另一个密钥对, 同 public name -> 负对照
ECH_SRVKEYS_OTHER = ""
CERT = os.path.join(WORK, "cert.pem")
KEY = os.path.join(WORK, "key.pem")
CERT_SHA256 = ""     # xray 26.x 移除了 allowInsecure -> 用 pinnedPeerCertSha256
ECH_PEM = ""         # sing-box 的 tls.ech.config 要 PEM("ECH CONFIGS"), 不是裸 base64
# REALITY 的 dest: 默认用**本地 Go/Xray TLS 服务端**做可控 dest。
# 原因(实测): 用真实站点做 dest 时, 若该站证书记录 > reality 模块的 8192 缓冲,
# 服务端会 `break` 掉 mimicry 循环 => 已认证连接也会 "handshake did not complete successfully"。
# 见 research/empirical/cross-kernel-matrix.md 的 dest 章节与 ctrl-xray-reality-realdest 用例。
DEST = ""            # 本地 dest, setup() 里填
DEST_PROC = None
DEST_PORT = 0
REAL_DEST = "www.microsoft.com:443"   # 真实 dest (8273B 证书记录, 会触发 8192 边界)
REAL_SNI = "www.microsoft.com"
ORIGIN_PORT = 0
ORIGIN_PROC = None


# --------------------------------------------------------------------------- 基础设施
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_port(port: int, timeout: float = 8.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = socket.socket()
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except OSError:
            s.close()
            time.sleep(0.1)
    return False


def sh(cmd: list[str], timeout: int = 30, cwd: str | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        return 124, "TIMEOUT: " + str(e)


KIND_EXT = {"xray": ".json", "mihomo": ".yaml", "singbox": ".json"}


def validate(kind: str, path: str) -> tuple[int, str]:
    d = os.path.dirname(path)
    if kind == "xray":
        return sh([XRAY, "-test", "-config", path], cwd=d)
    if kind == "mihomo":
        return sh([MIHOMO, "-t", "-f", path, "-d", d], cwd=d)
    if kind == "singbox":
        return sh([SINGBOX, "check", "-c", path, "-D", d], cwd=d)
    raise ValueError(kind)


def spawn(kind: str, path: str, logpath: str) -> subprocess.Popen:
    d = os.path.dirname(path)
    if kind == "xray":
        cmd = [XRAY, "run", "-config", path]
    elif kind == "mihomo":
        cmd = [MIHOMO, "-f", path, "-d", d]
    elif kind == "singbox":
        cmd = [SINGBOX, "run", "-c", path, "-D", d]
    else:
        raise ValueError(kind)
    f = open(logpath, "wb")
    return subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=d, start_new_session=True)


def kill(p: subprocess.Popen | None) -> None:
    if p is None or p.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except OSError:
        pass
    try:
        p.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except OSError:
            pass
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass


def tail(path: str, n: int = 40) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read().decode("utf-8", "replace")
        return "\n".join(data.strip().splitlines()[-n:])
    except OSError:
        return ""


# --------------------------------------------------------------------------- 配置构造
def jcfg(o) -> str:
    return json.dumps(o, indent=2, ensure_ascii=False)


def xray_stream_server(net="tcp", sec="none", *, path="/xyz", mode=None, xmux=None,
                       extra_stream=None, ech_server=False, dest=None) -> dict:
    st: dict = {"network": net, "security": sec}
    if sec == "reality":
        st["realitySettings"] = {"show": False, "dest": dest or DEST, "xver": 0,
                                 "serverNames": [SNI], "privateKey": RPRIV, "shortIds": [SID]}
    elif sec == "tls":
        st["tlsSettings"] = {"certificates": [{"certificateFile": CERT, "keyFile": KEY}]}
        if ech_server:
            st["tlsSettings"]["echServerKeys"] = ECH_SRVKEYS
            st["tlsSettings"]["rejectUnknownSni"] = True
            st["tlsSettings"]["serverName"] = ECH_INNER
    if net in ("xhttp", "splithttp"):
        xs: dict = {"path": path}
        if mode:
            xs["mode"] = mode
        if xmux is not None:
            xs["xmux"] = xmux
        st["xhttpSettings"] = xs
    if net == "ws":
        st["wsSettings"] = {"path": path}
    if extra_stream:
        st.update(extra_stream)
    return st


def xray_stream_client(net="tcp", sec="none", *, path="/xyz", mode=None, pbk=None, sid=None,
                       sni=None, flow_tls=False, ech=None, xmux=None, extra_stream=None) -> dict:
    st: dict = {"network": net, "security": sec}
    if sec == "reality":
        st["realitySettings"] = {"serverName": sni or SNI, "fingerprint": "chrome",
                                 "publicKey": pbk if pbk is not None else RPUB,
                                 "shortId": sid if sid is not None else SID, "spiderX": "/"}
    elif sec == "tls":
        tls = {"serverName": sni or SNI, "pinnedPeerCertSha256": CERT_SHA256}
        if flow_tls:
            tls["fingerprint"] = "chrome"
        if ech:
            tls["echConfigList"] = ech
        st["tlsSettings"] = tls
    if net in ("xhttp", "splithttp"):
        xs: dict = {"path": path}
        if mode:
            xs["mode"] = mode
        if xmux is not None:
            xs["xmux"] = xmux
        st["xhttpSettings"] = xs
    if net == "ws":
        st["wsSettings"] = {"path": path}
    if extra_stream:
        st.update(extra_stream)
    return st


def xray_cfg(inbounds: list, outbounds: list, loglevel="debug") -> str:
    return jcfg({"log": {"loglevel": loglevel}, "inbounds": inbounds, "outbounds": outbounds})


def xray_server_vless(port, net="tcp", sec="none", *, flow="", path="/xyz", mode=None,
                      xmux=None, extra_stream=None, ech_server=False, dest=None) -> str:
    return xray_cfg(
        [{"listen": "127.0.0.1", "port": port, "protocol": "vless",
          "settings": {"clients": [{"id": UUID, "flow": flow}], "decryption": "none"},
          "streamSettings": xray_stream_server(net, sec, path=path, mode=mode, xmux=xmux,
                                              extra_stream=extra_stream, ech_server=ech_server,
                                              dest=dest)}],
        [{"protocol": "freedom", "tag": "direct"}])


def xray_server_ss(port, sec="none") -> str:
    return xray_cfg(
        [{"listen": "127.0.0.1", "port": port, "protocol": "shadowsocks",
          "settings": {"method": SS_METHOD, "password": SS_KEY, "network": "tcp,udp"},
          "streamSettings": xray_stream_server("tcp", sec)}],
        [{"protocol": "freedom", "tag": "direct"}])


def xray_client_socks(socks_port, outbound: dict) -> str:
    return xray_cfg(
        [{"listen": "127.0.0.1", "port": socks_port, "protocol": "socks",
          "settings": {"udp": False, "auth": "noauth"}}],
        [outbound])


def xray_client_vless(socks_port, srv_port, net="tcp", sec="none", *, flow="", path="/xyz",
                      mode=None, pbk=None, sid=None, sni=None, mux=None, ech=None,
                      xmux=None, extra_stream=None, flow_tls=False) -> str:
    user: dict = {"id": UUID, "encryption": "none"}
    if flow:
        user["flow"] = flow
    out: dict = {"protocol": "vless",
                 "settings": {"vnext": [{"address": "127.0.0.1", "port": srv_port, "users": [user]}]},
                 "streamSettings": xray_stream_client(net, sec, path=path, mode=mode, pbk=pbk,
                                                      sid=sid, sni=sni, ech=ech, xmux=xmux,
                                                      flow_tls=flow_tls,
                                                      extra_stream=extra_stream)}
    if mux is not None:
        out["mux"] = mux
    return xray_client_socks(socks_port, out)


def xray_client_ss(socks_port, srv_port, sec="none", *, pbk=None, sid=None, sni=None) -> str:
    out = {"protocol": "shadowsocks",
           "settings": {"servers": [{"address": "127.0.0.1", "port": srv_port,
                                     "method": SS_METHOD, "password": SS_KEY}]},
           "streamSettings": xray_stream_client("tcp", sec, pbk=pbk, sid=sid, sni=sni)}
    return xray_client_socks(socks_port, out)


def mihomo_yaml(socks_port, proxy: dict, extra: str = "") -> str:
    lines = [f"mixed-port: {socks_port}", "allow-lan: false", "mode: global",
             "log-level: debug", "ipv6: false", "proxies:"]
    for k, v in proxy.items():
        if isinstance(v, dict):
            lines.append(f"  - {k}:")
            for kk, vv in v.items():
                lines.append(f"      {kk}: {json.dumps(vv) if not isinstance(vv, str) else vv}")
        else:
            lines.append(f"  - {k}: {json.dumps(v) if not isinstance(v, str) else v}")
    # 重新组织: 上面把 name 放在第一行了, 需要 name 是列表项的第一个键
    return "\n".join(lines) + "\n" + extra


def mihomo_cfg(socks_port, proxy: dict, head_extra: str = "") -> str:
    """一个 proxy = YAML 列表里的一项; 端口用 @SP@/@CP@ 占位符(渲染成裸数字)。"""
    def scalar(v) -> str:
        if isinstance(v, str) and "@" in v:
            return v  # 端口占位符
        return json.dumps(v, ensure_ascii=False)

    out = [f"mixed-port: {socks_port}", "allow-lan: false", "mode: rule",
           "log-level: debug", "ipv6: false"]
    if head_extra:
        out.append(head_extra)
    out.append("proxies:")
    for i, (k, v) in enumerate(proxy.items()):
        out.append(f"  - {k}: {scalar(v)}" if i == 0 else f"    {k}: {scalar(v)}")
    # 必须显式选路: mode=global 时 GLOBAL 组默认选 DIRECT, 流量会绕过代理(实测踩过)
    out += ['proxy-groups:', '  - name: "PROXY"', '    type: "select"',
            '    proxies: ["t"]', 'rules:', '  - "MATCH,PROXY"']
    return "\n".join(out) + "\n"


def singbox_cfg(socks_port, outbound: dict) -> str:
    return jcfg({"log": {"level": "debug", "timestamp": True},
                 "inbounds": [{"type": "socks", "tag": "in", "listen": "127.0.0.1",
                               "listen_port": socks_port}],
                 "outbounds": [outbound]})


def singbox_server_vless(port, *, tls=False, multiplex=None, net=None, transport=None,
                         reality=False, sni=None) -> str:
    ob: dict = {"type": "vless", "tag": "in", "listen": "127.0.0.1", "listen_port": port,
                "users": [{"name": "u", "uuid": UUID}]}
    if net == "ws":
        ob["transport"] = {"type": "ws", "path": "/xyz"}
    if transport:
        ob["transport"] = transport
    if reality:
        ob["tls"] = {"enabled": True, "server_name": sni or SNI,
                     "reality": {"enabled": True,
                                 "handshake": {"server": "127.0.0.1", "server_port": DEST_PORT},
                                 "private_key": RPRIV, "short_id": [SID]}}
    elif tls:
        ob["tls"] = {"enabled": True, "certificate_path": CERT, "key_path": KEY,
                     "server_name": ECH_INNER}
    if multiplex:
        ob["multiplex"] = multiplex
    return jcfg({"log": {"level": "debug"}, "inbounds": [ob],
                 "outbounds": [{"type": "direct", "tag": "direct"}]})


def sb_tls(inner=SNI, ech=None, utls=False, insecure=True) -> dict:
    t = {"enabled": True, "server_name": inner, "insecure": insecure}
    if utls:
        t["utls"] = {"enabled": True, "fingerprint": "chrome"}
    if ech:
        t["ech"] = {"enabled": True, "config": [ech if "BEGIN ECH" in ech else ECH_PEM]}
    return t


# --------------------------------------------------------------------------- 用例表
# 每个用例: name, server(None|(kind, text)), client((kind, text)), expect, note
# 端口占位符: @SP@ = 服务端口, @CP@ = 客户端 socks 端口, @ORIGIN@ = 目标 http 端口
CASES: list[dict] = []


def case(name, *, server=None, client=None, expect="PASS", note="", tier="AB"):
    CASES.append({"name": name, "server": server, "client": client,
                  "expect": expect, "note": note, "tier": tier})


def build_cases() -> None:
    CASES.clear()

    # ---- 控制组 ----
    case("ctrl-xray-vless-tcp-none", server=("xray", xray_server_vless("@SP@")),
         client=("xray", xray_client_vless("@CP@", "@SP@")), expect="PASS",
         note="控制组: xray vless tcp none 回环")
    case("ctrl-mihomo-vless-tcp-none", server=("xray", xray_server_vless("@SP@")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "tcp", "udp": True})),
         expect="PASS", note="控制组: mihomo vless tcp 回环")
    case("ctrl-singbox-vless-tcp-none", server=("xray", xray_server_vless("@SP@")),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID})),
         expect="PASS", note="控制组: sing-box vless tcp 回环")
    case("ctrl-xray-ss", server=("xray", xray_server_ss("@SP@")),
         client=("xray", xray_client_ss("@CP@", "@SP@")), expect="PASS",
         note="控制组: xray ss2022 回环(无 reality)")
    case("ctrl-mihomo-ss", server=("xray", xray_server_ss("@SP@")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "ss", "server": "127.0.0.1", "port": "@SP@",
             "cipher": SS_METHOD, "password": SS_KEY, "udp": True})),
         expect="PASS", note="控制组: mihomo ss2022 回环(无 reality)")
    case("ctrl-singbox-ss", server=("xray", xray_server_ss("@SP@")),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "shadowsocks", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "method": SS_METHOD, "password": SS_KEY})),
         expect="PASS", note="控制组: sing-box ss2022 回环(无 reality)")
    case("ctrl-xray-reality", server=("xray", xray_server_vless("@SP@", "tcp", "reality")),
         client=("xray", xray_client_vless("@CP@", "@SP@", "tcp", "reality")), expect="PASS",
         note="控制组: xray vless tcp reality 回环(本地 Go TLS dest)")
    case("ctrl-xray-reality-realdest",
         server=("xray", xray_server_vless("@SP@", "tcp", "reality", dest=REAL_DEST)),
         client=("xray", xray_client_vless("@CP@", "@SP@", "tcp", "reality", sni=REAL_SNI)),
         expect="?", note="dest=真实站点(microsoft, 8273B 证书记录): 探 reality 的 8192 缓冲边界")

    # ---- 死代理负对照: 证明"流量真的走代理"(mihomo mode=global 曾默认 DIRECT, 导致假 PASS) ----
    case("neg-xray-deadproxy", server=None,
         client=("xray", xray_client_vless("@CP@", 1)), expect="FAIL", tier="B",
         note="负对照: 代理指向死端口 1, 必须失败")
    case("neg-mihomo-deadproxy", server=None,
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": 1,
             "uuid": UUID, "network": "tcp"})), expect="FAIL", tier="B",
         note="负对照: mihomo 代理指向死端口 1, 必须失败")
    case("neg-singbox-deadproxy", server=None,
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": 1,
             "uuid": UUID})), expect="FAIL", tier="B",
         note="负对照: sing-box 代理指向死端口 1, 必须失败")

    # ---- A. SS + REALITY ----
    case("a1-xray-ss-reality", server=("xray", xray_server_ss("@SP@", "reality")),
         client=("xray", xray_client_ss("@CP@", "@SP@", "reality")), expect="PASS",
         note="A1 xray ss2022 + reality 回环")
    case("a1-neg-xray-ss-reality-wrongpbk",
         server=("xray", xray_server_ss("@SP@", "reality")),
         client=("xray", xray_client_ss("@CP@", "@SP@", "reality", pbk=RPUB_OTHER)),
         expect="FAIL", note="A1 负对照: 错误 publicKey 必须失败(reality 真被校验)")
    case("a2-mihomo-ss-reality", server=("xray", xray_server_ss("@SP@", "reality")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "ss", "server": "127.0.0.1", "port": "@SP@",
             "cipher": SS_METHOD, "password": SS_KEY, "udp": True,
             "client-fingerprint": "chrome", "servername": SNI,
             "reality-opts": {"public-key": RPUB, "short-id": SID}})),
         expect="?", note="A2 mihomo ss + reality-opts vs xray ss+reality 服务端")
    case("a2b-mihomo-ss-reality-vs-plain", server=("xray", xray_server_ss("@SP@")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "ss", "server": "127.0.0.1", "port": "@SP@",
             "cipher": SS_METHOD, "password": SS_KEY, "udp": True,
             "client-fingerprint": "chrome", "servername": SNI,
             "reality-opts": {"public-key": RPUB, "short-id": SID}})),
         expect="?", note="A2 判别: 若通过 => mihomo 忽略 reality-opts 只发裸 ss")
    case("a2c-mihomo-ss-plain-vs-reality-server",
         server=("xray", xray_server_ss("@SP@", "reality")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "ss", "server": "127.0.0.1", "port": "@SP@",
             "cipher": SS_METHOD, "password": SS_KEY, "udp": True})),
         expect="FAIL", note="A2 对照: 不带 reality 的 mihomo ss 打 reality 服务端必失败")
    case("a3-singbox-ss-reality", server=None,
         client=("singbox", singbox_cfg("@CP@", {
             "type": "shadowsocks", "tag": "out", "server": "127.0.0.1", "server_port": 443,
             "method": SS_METHOD, "password": SS_KEY,
             "tls": {"enabled": True, "server_name": SNI}})),
         expect="FAIL", tier="A", note="A3 sing-box ss 出站没有 tls 字段(模型缺席)")

    # ---- B1. vless + tcp + vision + reality ----
    case("b1-xray-vision-reality",
         server=("xray", xray_server_vless("@SP@", "tcp", "reality", flow="xtls-rprx-vision")),
         client=("xray", xray_client_vless("@CP@", "@SP@", "tcp", "reality",
                                           flow="xtls-rprx-vision")),
         expect="PASS", note="B1 xray vision+reality 回环")
    case("b1-mihomo-vision-reality",
         server=("xray", xray_server_vless("@SP@", "tcp", "reality", flow="xtls-rprx-vision")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "tcp", "tls": True, "udp": True,
             "flow": "xtls-rprx-vision", "client-fingerprint": "chrome",
             "servername": SNI, "reality-opts": {"public-key": RPUB, "short-id": SID}})),
         expect="?", note="B1 mihomo vision+reality 回环")
    case("b1-singbox-vision-reality",
         server=("xray", xray_server_vless("@SP@", "tcp", "reality", flow="xtls-rprx-vision")),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID, "flow": "xtls-rprx-vision",
             "tls": {"enabled": True, "server_name": SNI, "utls": {"enabled": True, "fingerprint": "chrome"},
                     "reality": {"enabled": True, "public_key": RPUB, "short_id": SID}}})),
         expect="?", note="B1 sing-box vision+reality 回环")

    # ---- B2. vless + xhttp + reality ----
    case("b2-xray-xhttp-reality",
         server=("xray", xray_server_vless("@SP@", "xhttp", "reality")),
         client=("xray", xray_client_vless("@CP@", "@SP@", "xhttp", "reality")),
         expect="?", note="B2 xray xhttp+reality 回环")
    case("b2-mihomo-xhttp-reality",
         server=("xray", xray_server_vless("@SP@", "xhttp", "reality")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "xhttp", "tls": True, "udp": True,
             "client-fingerprint": "chrome", "servername": SNI,
             "reality-opts": {"public-key": RPUB, "short-id": SID},
             "xhttp-opts": {"path": "/xyz"}})),
         expect="?", note="B2 mihomo xhttp+reality 回环")
    case("b2-singbox-xhttp-reality", server=None,
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": 443,
             "uuid": UUID, "transport": {"type": "xhttp", "path": "/xyz"},
             "tls": {"enabled": True, "server_name": SNI}})),
         expect="FAIL", tier="A", note="B2 sing-box 有没有 xhttp transport 模型")

    # ---- B3. xhttp mode ----
    case("b3-xray-xhttp-packetup",
         server=("xray", xray_server_vless("@SP@", "xhttp", "reality")),
         client=("xray", xray_client_vless("@CP@", "@SP@", "xhttp", "reality", mode="packet-up")),
         expect="?", note="B3 xray xhttp mode=packet-up 回环")
    case("b3-xray-xhttp-streamone",
         server=("xray", xray_server_vless("@SP@", "xhttp", "reality", mode="stream-one")),
         client=("xray", xray_client_vless("@CP@", "@SP@", "xhttp", "reality", mode="stream-one")),
         expect="?", note="B3 xray xhttp mode=stream-one 回环")
    case("b3-mihomo-xhttp-packetup",
         server=("xray", xray_server_vless("@SP@", "xhttp", "reality")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "xhttp", "tls": True, "udp": True,
             "client-fingerprint": "chrome", "servername": SNI,
             "reality-opts": {"public-key": RPUB, "short-id": SID},
             "xhttp-opts": {"path": "/xyz", "mode": "packet-up"}})),
         expect="?", note="B3 mihomo xhttp mode=packet-up 回环")
    case("cfg-xray-xmux-both", server=None,
         client=("xray", xray_client_vless("@CP@", 443, "xhttp", "none",
                                           xmux={"maxConcurrency": "1-3", "maxConnections": "1-2"})),
         expect="FAIL", tier="A", note="B3 xmux: maxConcurrency+maxConnections 同时指定(硬报错?)")
    case("cfg-xray-xmux-maxconn-only", server=None,
         client=("xray", xray_client_vless("@CP@", 443, "xhttp", "none",
                                           xmux={"maxConnections": "1-2"})),
         expect="PASS", tier="A", note="B3 xmux: 只指定 maxConnections")
    case("cfg-xray-xmux-maxconc-only", server=None,
         client=("xray", xray_client_vless("@CP@", 443, "xhttp", "none",
                                           xmux={"maxConcurrency": "16-32"})),
         expect="PASS", tier="A", note="B3 xmux: 只指定 maxConcurrency(文档默认值)")

    # ---- B4. vless + ws + reality ----
    case("b4-xray-server-ws-reality", server=("xray", xray_server_vless("@SP@", "ws", "reality")),
         client=None, expect="FAIL", tier="A",
         note="B4 xray 服务端 ws+reality: 配置层是否接受")
    case("b4-xray-client-ws-reality", server=None,
         client=("xray", xray_client_vless("@CP@", 443, "ws", "reality")),
         expect="FAIL", tier="A", note="B4 xray 客户端 ws+reality: 配置层是否接受")
    case("b4-singbox-server-ws-reality-singbox",
         server=("singbox", singbox_server_vless("@SP@", tls=True, net="ws",
                                                 reality=True, sni=SNI)),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID, "transport": {"type": "ws", "path": "/xyz"},
             "tls": {"enabled": True, "server_name": SNI,
                     "utls": {"enabled": True, "fingerprint": "chrome"},
                     "reality": {"enabled": True, "public_key": RPUB, "short_id": SID}}})),
         expect="?", note="B4 ws+reality: sing-box 服务端 + sing-box 客户端 回环")
    case("b4-singbox-server-ws-reality-mihomo",
         server=("singbox", singbox_server_vless("@SP@", tls=True, net="ws",
                                                 reality=True, sni=SNI)),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "ws", "tls": True, "udp": True,
             "client-fingerprint": "chrome", "servername": SNI,
             "reality-opts": {"public-key": RPUB, "short-id": SID},
             "ws-opts": {"path": "/xyz"}})),
         expect="?", note="B4 ws+reality: sing-box 服务端 + mihomo 客户端 跨内核回环")
    case("b4-singbox-server-ws-plain-mihomo",
         server=("singbox", singbox_server_vless("@SP@", net="ws")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "ws", "udp": True,
             "ws-opts": {"path": "/xyz"}})),
         expect="PASS", note="B4 对照: mihomo ws(无 TLS) -> sing-box ws 服务端")

    # ---- B5. ECH ----
    case("b5-xray-ech",
         server=("xray", xray_server_vless("@SP@", "tcp", "tls", ech_server=True)),
         client=("xray", xray_client_vless("@CP@", "@SP@", "tcp", "tls", sni=ECH_INNER,
                                           flow_tls=True, ech=ECH_CONF)),
         expect="?", note="B5 xray ECH: 两端同内核 + rejectUnknownSni(外层 SNI 会不匹配)")
    case("b5-xray-ech-wrongkey",
         server=("xray", xray_server_vless("@SP@", "tcp", "tls", ech_server=True)),
         client=("xray", xray_client_vless("@CP@", "@SP@", "tcp", "tls", sni=ECH_INNER,
                                           flow_tls=True, ech=ECH_CONF_OTHER)),
         expect="FAIL", note="B5 负对照: ECH 密钥不匹配 => 退化成外层 SNI 被 rejectUnknownSni 拒")
    case("b5-mihomo-ech",
         server=("xray", xray_server_vless("@SP@", "tcp", "tls", ech_server=True)),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "tcp", "tls": True, "udp": True,
             "client-fingerprint": "chrome", "servername": ECH_INNER,
             "skip-cert-verify": True,
             "ech-opts": {"enable": True, "config": ECH_CONF}})),
         expect="?", note="B5 mihomo ech-opts 对 xray ECH 服务端")
    case("b5-singbox-ech",
         server=("xray", xray_server_vless("@SP@", "tcp", "tls", ech_server=True)),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID, "tls": sb_tls(ECH_INNER, ech=ECH_CONF)})),
         expect="?", note="B5 sing-box tls.ech 对 xray ECH 服务端")
    case("b5-mihomo-ech-wrongkey",
         server=("xray", xray_server_vless("@SP@", "tcp", "tls", ech_server=True)),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "tcp", "tls": True, "udp": True,
             "client-fingerprint": "chrome", "servername": ECH_INNER,
             "skip-cert-verify": True,
             "ech-opts": {"enable": True, "config": ECH_CONF_OTHER}})),
         expect="FAIL", note="B5 负对照: mihomo 用不匹配的 ECH 密钥 => 证明它真的在发 ECH")
    case("b5-singbox-ech-wrongkey",
         server=("xray", xray_server_vless("@SP@", "tcp", "tls", ech_server=True)),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID, "tls": sb_tls(ECH_INNER, ech="-----BEGIN ECH CONFIGS-----\n"
                                         + ECH_CONF_OTHER + "\n-----END ECH CONFIGS-----\n")})),
         expect="FAIL", note="B5 负对照: sing-box 用不匹配的 ECH 密钥")
    case("b4-mihomo-tcp-reality-vs-singbox-server",
         server=("singbox", singbox_server_vless("@SP@", reality=True, sni=SNI)),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "tcp", "tls": True, "udp": True,
             "client-fingerprint": "chrome", "servername": SNI,
             "reality-opts": {"public-key": RPUB, "short-id": SID}})),
         expect="?", note="B4 隔离: mihomo tcp+reality -> sing-box reality 服务端(不带 ws)")
    case("b4-singbox-tcp-reality-vs-singbox-server",
         server=("singbox", singbox_server_vless("@SP@", reality=True, sni=SNI)),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID,
             "tls": {"enabled": True, "server_name": SNI,
                     "utls": {"enabled": True, "fingerprint": "chrome"},
                     "reality": {"enabled": True, "public_key": RPUB, "short_id": SID}}})),
         expect="?", note="B4 隔离: sing-box tcp+reality -> sing-box reality 服务端(控制)")
    case("b5-control-xray-tls-noech",
         server=("xray", xray_server_vless("@SP@", "tcp", "tls")),
         client=("xray", xray_client_vless("@CP@", "@SP@", "tcp", "tls", sni=SNI)),
         expect="PASS", note="B5 控制: xray 普通 TLS(无 ECH) 回环, 证明 TLS 服务端可用")

    # ---- B6. mux ----
    case("b6-ctrl-xray-mux",
         server=("xray", xray_server_vless("@SP@")),
         client=("xray", xray_client_vless("@CP@", "@SP@",
                                           mux={"enabled": True, "concurrency": 8})),
         expect="PASS", note="B6 xray mux.cool 同内核回环(服务端日志找 v1.mux.cool 证据)")
    case("b6-mihomo-smux-vs-xray-server",
         server=("xray", xray_server_vless("@SP@")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "tcp", "udp": True,
             "smux": {"enabled": True, "protocol": "yamux", "max-connections": 2}})),
         expect="FAIL", note="B6 mihomo smux(yamux) -> xray 服务端(xray 只认 mux.cool)")
    case("b6-singbox-smux-vs-xray-server",
         server=("xray", xray_server_vless("@SP@")),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID, "multiplex": {"enabled": True, "protocol": "smux"}})),
         expect="FAIL", note="B6 sing-box multiplex(smux) -> xray 服务端")
    case("b6-xray-mux-vs-singbox-server",
         server=("singbox", singbox_server_vless("@SP@")),
         client=("xray", xray_client_vless("@CP@", "@SP@",
                                           mux={"enabled": True, "concurrency": 8})),
         expect="FAIL", note="B6 xray mux.cool -> sing-box 服务端(sing-box 无 mux.cool)")
    case("b6-xray-plain-vs-singbox-server",
         server=("singbox", singbox_server_vless("@SP@")),
         client=("xray", xray_client_vless("@CP@", "@SP@")),
         expect="PASS", note="B6 控制: xray 客户端(无 mux) -> sing-box 服务端 必须通")
    case("b6-singbox-smux-self",
         server=("singbox", singbox_server_vless("@SP@", multiplex={"enabled": True})),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID, "multiplex": {"enabled": True, "protocol": "smux"}})),
         expect="PASS", note="B6 sing-box multiplex 自洽回环(证明 smux 本身可用)")
    case("b6-mihomo-smux-vs-singbox-server",
         server=("singbox", singbox_server_vless("@SP@", multiplex={"enabled": True})),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "tcp", "udp": True,
             "smux": {"enabled": True, "protocol": "yamux"}})),
         expect="?", note="B6 mihomo smux(yamux) -> sing-box(multiplex enabled) 跨厂商 smux")
    case("b6-singbox-h2mux-default-vs-self",
         server=("singbox", singbox_server_vless("@SP@", multiplex={"enabled": True})),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID, "multiplex": {"enabled": True}})),
         expect="?", note="B6 sing-box multiplex 不写 protocol(文档默认 h2mux) 自洽回环")
    case("cfg-singbox-muxcool", server=None,
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": 443,
             "uuid": UUID, "multiplex": {"enabled": True, "protocol": "mux.cool"}})),
         expect="FAIL", tier="A", note="B6 sing-box multiplex.protocol=mux.cool")
    case("cfg-mihomo-bogus-network", server=None,
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": 443,
             "uuid": UUID, "network": "no-such-transport-xyz", "tls": True})),
         expect="PASS", tier="A", note="B6 复核: mihomo 不校验 network")
    case("cfg-mihomo-ss-reality-badkey", server=None,
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "ss", "server": "127.0.0.1", "port": 443,
             "cipher": SS_METHOD, "password": SS_KEY,
             "reality-opts": {"public-key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                              "short-id": SID}})),
         expect="?", tier="A", note="B6/A: mihomo 对 ss 上的 reality-opts 是否校验(非法 pk)")
    case("cfg-mihomo-smux-bogus-protocol", server=None,
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": 443,
             "uuid": UUID, "network": "tcp",
             "smux": {"enabled": True, "protocol": "no-such-mux"}})),
         expect="?", tier="A", note="B6 mihomo smux 是否校验 protocol 名")

    case("b6-xray-xhttp-with-muxcool",
         server=("xray", xray_server_vless("@SP@", "xhttp", "reality")),
         client=("xray", xray_client_vless("@CP@", "@SP@", "xhttp", "reality",
                                           mux={"enabled": True, "concurrency": 8})),
         expect="?", note="B6 XHTTP + mux.cool 同时开(#4113 称服务端有检查, 只接受纯 XUDP)")
    case("b6-xray-xhttp-without-mux",
         server=("xray", xray_server_vless("@SP@", "xhttp", "reality")),
         client=("xray", xray_client_vless("@CP@", "@SP@", "xhttp", "reality")),
         expect="PASS", note="B6 对照: XHTTP 不启用 mux.cool")

    # ---- B7. flow=vision + security=none ----
    case("b7-xray-vision-none",
         server=("xray", xray_server_vless("@SP@", "tcp", "none")),
         client=("xray", xray_client_vless("@CP@", "@SP@", "tcp", "none",
                                           flow="xtls-rprx-vision")),
         expect="FAIL", note="B7 xray flow=vision + security=none")
    case("b7-mihomo-vision-none",
         server=("xray", xray_server_vless("@SP@", "tcp", "none")),
         client=("mihomo", mihomo_cfg("@CP@", {
             "name": "t", "type": "vless", "server": "127.0.0.1", "port": "@SP@",
             "uuid": UUID, "network": "tcp", "udp": True, "flow": "xtls-rprx-vision"})),
         expect="FAIL", note="B7 mihomo flow=vision + 无 TLS")
    case("b7-singbox-vision-none",
         server=("xray", xray_server_vless("@SP@", "tcp", "none")),
         client=("singbox", singbox_cfg("@CP@", {
             "type": "vless", "tag": "out", "server": "127.0.0.1", "server_port": "@SP@",
             "uuid": UUID, "flow": "xtls-rprx-vision"})),
         expect="FAIL", note="B7 sing-box flow=vision + 无 TLS")


# --------------------------------------------------------------------------- 运行
def setup() -> None:
    global SS_KEY, RPRIV, RPUB, RPUB_OTHER, ECH_CONF, ECH_SRVKEYS, ECH_CONF_OTHER, ECH_SRVKEYS_OTHER, ORIGIN_PORT, ORIGIN_PROC
    for d in (CFGD, LOGD, ORIGIN_DIR):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    with open(os.path.join(ORIGIN_DIR, "index.html"), "w") as f:
        f.write(ORIGIN_BODY + "\n")

    rc, out = sh(["openssl", "rand", "-base64", "16"])
    SS_KEY = out.strip()
    assert len(SS_KEY) == 24, SS_KEY

    rc, out = sh([XRAY, "x25519"])
    for line in out.splitlines():
        if line.startswith("PrivateKey:"):
            RPRIV = line.split(":", 1)[1].strip()
        if line.startswith("Password (PublicKey):"):
            RPUB = line.split(":", 1)[1].strip()
    assert RPRIV and RPUB, out
    rc, out = sh([XRAY, "x25519"])
    for line in out.splitlines():
        if line.startswith("Password (PublicKey):"):
            RPUB_OTHER = line.split(":", 1)[1].strip()
    assert RPUB_OTHER and RPUB_OTHER != RPUB, out

    # ECH: 外层 public name = cover.example.com, 内层 serverName = www.microsoft.com
    rc, out = sh([XRAY, "tls", "ech", "--serverName", ECH_OUTER])
    lines = out.splitlines()
    ECH_CONF = lines[1].strip()
    ECH_SRVKEYS = lines[3].strip()
    rc, out = sh([XRAY, "tls", "ech", "--serverName", ECH_OUTER])
    lines = out.splitlines()
    ECH_CONF_OTHER = lines[1].strip()
    ECH_SRVKEYS_OTHER = lines[3].strip()
    assert ECH_CONF and ECH_SRVKEYS, out

    # 自签证书 (xray tls cert 需要 domain 参数; 用 openssl 更直接)
    rc, out = sh(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                  "-nodes", "-keyout", KEY, "-out", CERT, "-days", "30", "-subj", f"/CN={SNI}",
                  "-addext", f"subjectAltName=DNS:{SNI}"])
    assert os.path.exists(CERT), out

    global CERT_SHA256, ECH_PEM
    rc, out = sh([XRAY, "tls", "hash", "--cert", CERT])
    CERT_SHA256 = out.split("SHA256:")[1].strip()
    assert len(CERT_SHA256) == 64, out
    import base64 as _b64
    _raw = _b64.b64decode(ECH_CONF)
    _pem = "-----BEGIN ECH CONFIGS-----\n" + "\n".join(
        _b64.b64encode(_raw[i:i + 48]).decode() for i in range(0, len(_raw), 48)) + "\n-----END ECH CONFIGS-----\n"
    ECH_PEM = _pem

    # 本地 REALITY dest: 一个 xray vless+tcp+tls 服务端 (Go TLS, 证书记录 ~466B)
    global DEST_PROC, DEST, DEST_PORT
    DEST_PORT = free_port()
    dest_cfg = jcfg({
        "log": {"loglevel": "warning"},
        "inbounds": [{"listen": "127.0.0.1", "port": DEST_PORT, "protocol": "vless",
                      "settings": {"clients": [{"id": UUID}], "decryption": "none"},
                      "streamSettings": {"network": "tcp", "security": "tls",
                                         "tlsSettings": {"certificates": [
                                             {"certificateFile": CERT, "keyFile": KEY}],
                                             "serverName": SNI}}}],
        "outbounds": [{"protocol": "freedom"}]})
    dpath = os.path.join(CFGD, "_reality_dest.json")
    with open(dpath, "w") as f:
        f.write(dest_cfg)
    DEST_PROC = spawn("xray", dpath, os.path.join(LOGD, "_reality_dest.log"))
    assert wait_port(DEST_PORT, 5), "local reality dest did not start"
    DEST = f"127.0.0.1:{DEST_PORT}"

    ORIGIN_PORT = free_port()
    ORIGIN_PROC = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(ORIGIN_PORT), "--bind", "127.0.0.1",
         "--directory", ORIGIN_DIR],
        stdout=open(os.path.join(LOGD, "origin.log"), "wb"), stderr=subprocess.STDOUT,
        start_new_session=True)
    assert wait_port(ORIGIN_PORT, 5), "origin http server did not start"


def teardown() -> None:
    kill(ORIGIN_PROC)
    kill(DEST_PROC)


def run_case(c: dict) -> dict:
    name = c["name"]
    res: dict = {"name": name, "note": c["note"], "expect": c["expect"], "tier": c["tier"]}
    sp, cp = free_port(), free_port()
    subst = {"@SP@": str(sp), "@CP@": str(cp), "@ORIGIN@": str(ORIGIN_PORT)}
    srv = cli = None
    srv_log = os.path.join(LOGD, f"{name}.server.log")
    cli_log = os.path.join(LOGD, f"{name}.client.log")

    def render(spec, role):
        kind, text = spec
        for k, v in subst.items():          # JSON: 带引号的占位符 -> 裸数字(uint16)
            text = text.replace('"' + k + '"', v)
            text = text.replace(k, v)
        path = os.path.join(CFGD, f"{name}.{role}{KIND_EXT[kind]}")
        with open(path, "w") as f:
            f.write(text)
        return kind, path

    try:
        if c["server"]:
            skind, spath = render(c["server"], "server")
            res["server_kind"] = skind
            with open(os.path.join(CFGD, name + ".server.rendered.txt"), "w") as f:
                f.write(open(spath).read())
            vrc, vout = validate(skind, spath)
            res["server_validate"] = {"rc": vrc, "out": vout[-1500:]}
            if vrc != 0:
                res["verdict"] = "CONFIG_REJECTED_SERVER"
                return res
            srv = spawn(skind, spath, srv_log)
            if not wait_port(sp, 8):
                res["verdict"] = "SERVER_NOT_LISTENING"
                res["server_log"] = tail(srv_log, 30)
                return res
            res["server_listening"] = True

        ckind, cpath = render(c["client"], "client")
        res["client_kind"] = ckind
        with open(os.path.join(CFGD, name + ".client.rendered.txt"), "w") as f:
            f.write(open(cpath).read())
        vrc, vout = validate(ckind, cpath)
        res["client_validate"] = {"rc": vrc, "out": vout[-1500:]}
        if vrc != 0:
            res["verdict"] = "CONFIG_REJECTED_CLIENT"
            return res

        cli = spawn(ckind, cpath, cli_log)
        if not wait_port(cp, 8):
            res["verdict"] = "CLIENT_SOCKS_NOT_LISTENING"
            res["client_log"] = tail(cli_log, 30)
            return res

        url = f"http://127.0.0.1:{ORIGIN_PORT}/"
        crc, cout = sh(["curl", "-s", "-m", "8", "--socks5-hostname", f"127.0.0.1:{cp}", url], timeout=20)
        res["curl"] = {"rc": crc, "out": cout.strip()[:200]}
        if ORIGIN_BODY in cout:
            res["verdict"] = "PASS"
        else:
            res["verdict"] = "RUNTIME_FAIL"
    finally:
        kill(cli)
        kill(srv)
        res["server_log"] = tail(srv_log, 25) if c["server"] else ""
        res["client_log"] = tail(cli_log, 40)
        res["client_alive_at_end"] = bool(cli and cli.poll() is None)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="子串过滤用例名")
    ap.add_argument("--out", default=os.path.join(WORK, "results.json"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    setup()
    build_cases()
    cases = [c for c in CASES if not a.only or a.only in c["name"]]
    if a.list:
        for c in cases:
            print(c["name"], "|", c["expect"], "|", c["note"])
        teardown()
        return 0

    results = []
    try:
        for c in cases:
            t0 = time.time()
            try:
                r = run_case(c)
            except Exception as exc:  # noqa: BLE001
                r = {"name": c["name"], "verdict": "HARNESS_ERROR", "error": repr(exc)}
            r["secs"] = round(time.time() - t0, 1)
            results.append(r)
            mark = {"PASS": "PASS", "RUNTIME_FAIL": "FAIL", "CONFIG_OK_SERVER_ONLY": "CFG-OK-SRV",
                    "CONFIG_REJECTED_CLIENT": "CFG-REJ",
                    "CONFIG_REJECTED_SERVER": "CFG-REJ-SRV", "SERVER_NOT_LISTENING": "SRV-DEAD",
                    "CLIENT_SOCKS_NOT_LISTENING": "CLI-DEAD", "HARNESS_ERROR": "ERR"}.get(r["verdict"], "?")
            print(f"[{mark:10}] {r['name']:45} {r.get('secs')}s  {c['note']}", flush=True)
    finally:
        teardown()
        with open(a.out, "w") as f:
            json.dump({"kernels": {"xray": "26.3.27", "mihomo": "1.19.32", "singbox": "1.14.2"},
                       "results": results}, f, indent=2, ensure_ascii=False)
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
