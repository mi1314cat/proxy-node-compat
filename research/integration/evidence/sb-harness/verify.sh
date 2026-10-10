#!/usr/bin/env bash
# ==============================================================================
# CC 验收台 — SB 客户端 × proxy-node-compat   （v2）
#
# 硬边界:
#   * 只在 /tmp/sbc-verify 里做事; **不写 /opt/sb-client 任何文件**
#   * 不启停任何生产服务; 生产 sing-box (PID 1444214) 全程不动
#   * 内核二进制只读使用（symlink 到 /opt/sb-client/core/sing-box）
#   * 临时内核实例一律绑 127.0.0.1 的高位端口, 跑完就 kill
# ==============================================================================
set -u
V=/tmp/sbc-verify
export CLIENT_ROOT="$V/client"
export CLIENT_BIN="/opt/sb-client/core/sing-box"
KERNEL="$CLIENT_BIN"
OUT="$V/out"
mkdir -p "$OUT"
log() { printf '\n\033[1m===== %s =====\033[0m\n' "$*"; }
sbx() { bash "$V/client/client.sh" "$@"; }
nodes() { ls "$V/client/nodes"/node-*.json 2>/dev/null | wc -l; }
# 去掉本次导入的订阅前缀（rnurl-/noshim-/legacy-）, 只比节点本身
tags() { ls "$V/client/nodes"/node-*.json 2>/dev/null | sed 's|.*/node-||;s|\.json$||' \
         | sed -E 's/^(rnurl|noshim|legacy)-//' | sort; }
reset_nodes() { rm -rf "$V/client/nodes"; mkdir -p "$V/client/nodes"; }

log "0 · 环境（真读）"
"$KERNEL" version
python3 -V

log "1 · 搭沙箱（全在 /tmp）"
pkill -f "http.server 18081" 2>/dev/null || true
rm -rf "$V/client" "$V/run" "$V/run2"; mkdir -p "$V/client"/{conf,nodes,share-state,core,ui} "$V/run"
tar xzf /tmp/sb-compat-client.tgz -C "$V/client/share-state" 2>/dev/null
mv "$V/client/share-state/client.sh" "$V/client/client.sh"
ln -sf "$KERNEL" "$V/client/core/sing-box"
printf 'off' > "$V/client/share-state/proxy-mode"       # 非交互: 下载通道强制直连
cat > "$V/client/conf/00-mixed.json" <<'EOF'
{"inbounds":[{"type":"mixed","tag":"mixed-in","listen":"127.0.0.1","listen_port":12080}]}
EOF
cat > "$V/client/conf/02-dns.json" <<'EOF'
{"dns":{"servers":[{"type":"local","tag":"local-dns"}]}}
EOF
echo '{"outbounds":[]}' > "$V/client/conf/90-outbounds.json"
echo "沙箱: $V/client  (生产 /opt/sb-client 未触碰)"

log "2 · RN 真实产物 → 本地 HTTP 镜像"
# 为什么是镜像: RN 的分享链接是**一次性**的（max_uses=1）, CC 上那条订阅的 token
# 已经用尽（实测 410）。所以把 RN **自己生成**的那份产物原样搬过来, 用本地 HTTP
# 服务发出去 —— 客户端的"HTTP 拉取 → 识别 → 转换 → compat → 落盘"整条路径都是真的。
mkdir -p "$V/rn" "$V/webroot"
tar xzf /tmp/rn-artifacts.tgz -C "$V/rn"
cp "$V"/rn/sb_client-all.json "$V/webroot/rn-profile.json"
cat "$V"/rn/sb_share-*.txt > "$V/webroot/rn-links.txt"
echo "RN 真实分享链接条数: $(ls "$V"/rn/sb_share-*.txt | wc -l)"
nohup python3 -m http.server 18081 --bind 127.0.0.1 -d "$V/webroot" >"$OUT/http.log" 2>&1 &
echo $! > "$V/http.pid"
sleep 1
curl -s -o /dev/null -w "镜像 HTTP: http=%{http_code}\n" http://127.0.0.1:18081/rn-profile.json

log "3 · 真 sb-client 导入 · 自家 share JSON 路径（compat 闸门）"
reset_nodes
sbx add http://127.0.0.1:18081/rn-profile.json 2>&1 | tail -20
echo "--- 落盘节点数: $(nodes)  (RN profile 里 13 个出站 + 1 个 shadowtls helper)"
cp "$V/client/share-state/.compat-last.json" "$OUT/report-json.json" 2>/dev/null || true

log "4 · 真 sb-client 导入 · 外部 share URI 路径（to_sb.py + compat）"
reset_nodes
SB_SUBS_PREFIX=rnurl sbx add http://127.0.0.1:18081/rn-links.txt 2>&1 | tail -20
N_SHIM=$(nodes); tags > "$OUT/tags-shim.txt"; echo "--- 落盘节点数(绕行开): $N_SHIM"
cp "$V/client/share-state/.compat-last.json" "$OUT/report-uri.json" 2>/dev/null || true

log "4b · 对照: 关掉已知缺陷绕行（SB_COMPAT_NO_SHIMS=1）"
reset_nodes
SB_SUBS_PREFIX=noshim SB_COMPAT_NO_SHIMS=1 sbx add http://127.0.0.1:18081/rn-links.txt 2>&1 | tail -14
N_NOSHIM=$(nodes); tags > "$OUT/tags-noshim.txt"; echo "--- 落盘节点数(绕行关): $N_NOSHIM"

log "5 · 回滚开关（SB_COMPAT_ENGINE=legacy）"
reset_nodes
SB_SUBS_PREFIX=legacy SB_COMPAT_ENGINE=legacy sbx add http://127.0.0.1:18081/rn-links.txt 2>&1 | tail -8
N_LEGACY=$(nodes); tags > "$OUT/tags-legacy.txt"
echo "--- 落盘节点数(回滚): $N_LEGACY"
echo
echo ">>> 节点数:  绕行开=$N_SHIM  绕行关=$N_NOSHIM  回滚=$N_LEGACY"
echo "    三者不必相等 —— 差异必须能一一对上（下面列出来）:"
echo "    [绕行开 - 回滚]  = 只有 compat 判死、旧判定会放进来（每条都要能解释）:"
comm -23 "$OUT/tags-shim.txt" "$OUT/tags-legacy.txt" | sed 's/^/       - /'
echo "    [回滚 - 绕行开]  只应是 legacy 能转但 compat 判死的:"
comm -13 "$OUT/tags-shim.txt" "$OUT/tags-legacy.txt" | sed 's/^/       + /'
echo "    [绕行开 - 绕行关]  就是**假 UNSUPPORTED**（关掉绕行会丢掉的真实可用节点）:"
comm -23 "$OUT/tags-shim.txt" "$OUT/tags-noshim.txt" | sed 's/^/       ! /' 

log "6 · 逐节点三方对比（旧判定 / compat / 合并）"
python3 "$V/tri_compare.py" 2>&1 | tee "$OUT/tri.txt" | tail -80

log "7 · 真实连通性（临时内核实例, 每节点一条出站）"
python3 "$V/probe_real.py" 2>&1 | tee "$OUT/probe.txt" | tail -25

log "8 · 转换损失的真实后果（对照实验）"
python3 "$V/probe_loss.py" 2>&1 | tee "$OUT/probe-loss.txt" | tail -10

log "9 · 收尾"
kill "$(cat "$V/http.pid")" 2>/dev/null || true
pkill -f "$V/run/" 2>/dev/null || true
pkill -f "$V/run2/" 2>/dev/null || true
rm -f "$V/http.pid"
echo "临时实例已清理; 生产进程检查:"
ps -p 1444214 -o pid=,etime=,cmd= 2>/dev/null || echo "  (生产 PID 1444214 不在了 —— 需要人工确认!)"
