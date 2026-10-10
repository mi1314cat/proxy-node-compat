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
# DNS 用**生产那份的只读副本**: RN 的 profile 里带 domain_resolver=doh-main,
# 沙箱自己编一个 local-dns 会让 sing-box check 报 "default domain resolver not found"
# —— 那是沙箱的锅, 不是客户端的锅。对角线要验的是"导入 13 个节点后 check 通过"。
cp /opt/sb-client/conf/02-dns.json "$V/client/conf/02-dns.json"
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

log "3 · 对角线: SB 分享 → SB 客户端（自家 share JSON 路径）"
reset_nodes
sbx add http://127.0.0.1:18081/rn-profile.json 2>&1 | tail -20
echo "--- 落盘节点数: $(nodes)  (RN profile 里 13 个出站 + 1 个 shadowtls helper)"
if CHKOUT=$("$KERNEL" check -D "$V/client/conf" -C "$V/client/conf" 2>&1); then
    echo "--- sing-box check: 通过（13 节点 + 完整 conf 目录）"
else
    echo "--- sing-box check: **失败**"; printf '%s\n' "$CHKOUT" | tail -3
fi
cp "$V/client/share-state/.compat-last.json" "$OUT/report-json.json" 2>/dev/null || true

log "4 · 真 sb-client 导入 · 外部 share URI 路径（to_sb.py + compat）"
reset_nodes
SB_SUBS_PREFIX=rnurl sbx add http://127.0.0.1:18081/rn-links.txt 2>&1 | tail -20
N_NEW=$(nodes); tags > "$OUT/tags-new.txt"; echo "--- 落盘节点数(canonical): $N_NEW"
cp "$V/client/share-state/.compat-last.json" "$OUT/report-uri.json" 2>/dev/null || true

log "4b · 对照: 旧快照（7009d93 = 3a75ba5 副本 + encryption=none 绕行）"
# 只换 compat2.py 与 lib/ 两样, to_sb.py / client.sh 完全相同 —— 单一变量
rm -rf "$V/client-old"; mkdir -p "$V/client-old"/{conf,nodes,share-state,core,ui}
cp "$V/client/client.sh" "$V/client-old/client.sh"
cp "$V/client/share-state/to_sb.py" "$V/client-old/share-state/to_sb.py"
cp "$V/client/share-state/compat2.py" "$V/client-old/share-state/compat2.py"
cp -r "$V/client/share-state/lib" "$V/client-old/share-state/lib"
tar xzf /tmp/sb-compat-old.tgz -C /tmp        # compat2-old.py + lib-old/
cp /tmp/compat2-old.py "$V/client-old/share-state/compat2.py"
rm -rf "$V/client-old/share-state/lib"; cp -r /tmp/lib-old "$V/client-old/share-state/lib"
cp "$V/client/conf/00-mixed.json" "$V/client/conf/02-dns.json" "$V/client-old/conf/"
echo '{"outbounds":[]}' > "$V/client-old/conf/90-outbounds.json"
ln -sf "$KERNEL" "$V/client-old/core/sing-box"
printf 'off' > "$V/client-old/share-state/proxy-mode"
old_old_root="$CLIENT_ROOT"; export CLIENT_ROOT="$V/client-old"
SB_SUBS_PREFIX=rnurl bash "$V/client-old/client.sh" add http://127.0.0.1:18081/rn-links.txt 2>&1 | tail -10
N_OLD=$(ls "$V/client-old/nodes"/node-*.json 2>/dev/null | wc -l)
ls "$V/client-old/nodes"/node-*.json 2>/dev/null | sed 's|.*/node-||;s|\.json$||' \
  | sed -E 's/^(rnurl|noshim|legacy)-//' | sort > "$OUT/tags-old.txt"
export CLIENT_ROOT="$old_old_root"
echo "--- 落盘节点数(旧快照): $N_OLD"

log "5 · 回滚开关（SB_COMPAT_ENGINE=legacy）"
reset_nodes
SB_SUBS_PREFIX=legacy SB_COMPAT_ENGINE=legacy sbx add http://127.0.0.1:18081/rn-links.txt 2>&1 | tail -8
N_LEGACY=$(nodes); tags > "$OUT/tags-legacy.txt"
echo "--- 落盘节点数(回滚): $N_LEGACY"
echo
echo ">>> 节点数:  canonical(删 shim)=$N_NEW   旧快照(带 shim)=$N_OLD   回滚=$N_LEGACY"
echo "    ① 删 shim 后行为不变 ⇒ 前两个必须相等（逐条比, 不是只比个数）:"
if diff -q "$OUT/tags-new.txt" "$OUT/tags-old.txt" >/dev/null; then
    echo "       ✓ 节点名单逐条一致（$(wc -l < "$OUT/tags-new.txt") 条）"
else
    echo "       ✗ 节点名单不一致:"; diff "$OUT/tags-old.txt" "$OUT/tags-new.txt" | sed 's/^/         /'
fi
echo "    ② canonical 比回滚少的那 1 个, 只应是 compat 判死、旧判定会放进来的坏链接:"
comm -23 "$OUT/tags-new.txt" "$OUT/tags-legacy.txt" | sed 's/^/       - /'
echo "       （回滚比 canonical 多的）:"
comm -13 "$OUT/tags-new.txt" "$OUT/tags-legacy.txt" | sed 's/^/       + /' 

log "6 · 逐节点三方对比（旧判定 / compat / 合并）"
python3 "$V/tri_compare.py" 2>&1 | tee "$OUT/tri.txt" | tail -70
echo
echo "6b · 新旧快照逐条对比（同一份数据 + 同一个 to_sb.py, 只差 compat2.py/lib）"
COMPAT_CLIENT_ROOT="$V/client-old" COMPAT_TRI_OUT="$OUT/tri-uri-old.json" \
    python3 "$V/tri_compare.py" > "$OUT/tri-old.txt" 2>&1
python3 - "$OUT/tri-uri.json" "$OUT/tri-uri-old.json" <<'PY'
import json, sys
new = {r["tag"]: r for r in json.load(open(sys.argv[1], encoding="utf-8"))}
old = {r["tag"]: r for r in json.load(open(sys.argv[2], encoding="utf-8"))}
keys = ("legacy", "compat", "merged")
diff = []
for tag in sorted(set(new) | set(old)):
    a, b = old.get(tag), new.get(tag)
    if a is None or b is None:
        diff.append((tag, "缺一侧", a and a["merged"], b and b["merged"])); continue
    if any(a[k] != b[k] for k in keys) or a["rc"] != b["rc"]:
        diff.append((tag, "判定不同", "%s/%s/%s %s" % (a["legacy"], a["compat"], a["merged"], a["rc"]),
                     "%s/%s/%s %s" % (b["legacy"], b["compat"], b["merged"], b["rc"])))
print("    %d 条真实链接: 旧快照(带 shim) vs canonical(删 shim) 判定差异 %d 条"
      % (len(new), len(diff)))
for d in diff:
    print("      ✗ %s | %s | %s → %s" % d)
if not diff:
    print("      ✓ 逐条一致（legacy / compat / merged / reason_codes 四项全等）")
PY

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
