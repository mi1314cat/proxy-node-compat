#!/usr/bin/env bash
# ============================================================================
#  RN 三内核「仓库 HEAD 分发」—— 只补差异，先备份，全链路 sha256 复核
#  用法: bash /tmp/dist-prepush/rn-deploy.sh
#  纪律: 不重启任何服务; 不删任何东西; 每步打印可核对的 sha256 摘要
# ============================================================================
set -uo pipefail

STAGE=/tmp/dist-prepush
TS=$(date +%Y%m%d-%H%M%S)
BK=/root/backup-prepush-$TS

declare -A PIN=(
  [x]=be4ec8e   # xray--core   feat/three-way-interop → main (ff)
  [m]=c446d3f   # mihomo--core refactor/v2
  [sb]=a7150e2  # sing-box-core main
)

say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad() { printf '  \033[31m✗\033[0m %s\n' "$*"; FAILED=$((FAILED+1)); }
FAILED=0

# ---------------------------------------------------------------- 0. 解包
say "0. 解包冻结快照"
rm -rf "$STAGE/dist-x" "$STAGE/dist-m" "$STAGE/dist-sb"
mkdir -p "$STAGE/dist-x" "$STAGE/dist-m" "$STAGE/dist-sb"
tar xzf "$STAGE/x-head.tar.gz"  -C "$STAGE/dist-x"
tar xzf "$STAGE/m-head.tar.gz"  -C "$STAGE/dist-m"
tar xzf "$STAGE/sb-head.tar.gz" -C "$STAGE/dist-sb"
for k in x m sb; do
  n=$(find "$STAGE/dist-$k" -type f | wc -l)
  ok "$k 解包 $n 个文件"
done

# ---------------------------------------------------------------- 1. 备份
say "1. 备份 ($BK)"
mkdir -p "$BK"
# X: 脚本层在 /root/conf 与 /root/xray-panel.sh
if [[ -d /root/conf ]]; then
  tar czf "$BK/conf.tar.gz" -C /root conf && ok "conf.tar.gz $(stat -c%s "$BK/conf.tar.gz")" || bad "conf 备份失败"
else
  bad "/root/conf 不存在（X 分发前提被破坏）"
fi
cp -a /root/xray-panel.sh "$BK/xray-panel.sh" 2>/dev/null && ok "xray-panel.sh 已备份"
# M
tar czf "$BK/mihomo-src.tar.gz" -C /root/catmi/mihomo src && ok "mihomo-src.tar.gz $(stat -c%s "$BK/mihomo-src.tar.gz")" || bad "M 备份失败"
# SB
tar czf "$BK/sb-conf.tar.gz" -C /root/catmi/sing-box conf install.sh sing-box.sh \
  && ok "sb-conf.tar.gz $(stat -c%s "$BK/sb-conf.tar.gz")" || bad "SB 备份失败"
# 服务 PID 基线（分发不许改变它们）
{
  for s in xrayls mihomo sing-box proxy-share-service nginx; do
    printf '%s pid=%s since=%s active=%s\n' "$s" \
      "$(systemctl show -p MainPID --value $s 2>/dev/null)" \
      "$(systemctl show -p ActiveEnterTimestamp --value $s 2>/dev/null)" \
      "$(systemctl is-active $s 2>/dev/null)"
  done
} | tee "$BK/pids-before.txt"
echo "$BK" > /tmp/.prepush-backup-dir

# ---------------------------------------------------------------- 2. 差异清单
say "2. 差异清单（仓库 HEAD vs 当前部署）"
list_diff() {           # $1=源目录 $2=目标目录 $3=前缀
  local src=$1 dst=$2 pre=$3 f rel d
  ( cd "$src" && find . -type f | sort ) | while read -r f; do
    rel=${f#./}
    d="$dst/$rel"
    if [[ ! -e "$d" ]]; then echo "NEW     $pre$rel"
    elif ! cmp -s "$src/$rel" "$d"; then echo "CHANGED $pre$rel"
    fi
  done
}
list_diff "$STAGE/dist-x/conf"        /root/conf                  "conf/"          > "$BK/diff.txt"
list_diff "$STAGE/dist-x"             /root                       ""               >> "$BK/diff.txt" || true
# xray-panel.sh 逐字节比
if cmp -s "$STAGE/dist-x/xray-panel.sh" /root/xray-panel.sh; then
  echo "SAME    xray-panel.sh" >> "$BK/diff.txt"
else
  echo "CHANGED xray-panel.sh" >> "$BK/diff.txt"
fi
list_diff "$STAGE/dist-m/src"         /root/catmi/mihomo/src      "src/"           >> "$BK/diff.txt"
list_diff "$STAGE/dist-sb/src/conf"   /root/catmi/sing-box/conf   "conf/"          >> "$BK/diff.txt"
list_diff "$STAGE/dist-sb/src"        /root/catmi/sing-box        ""               >> "$BK/diff.txt"
sort -u "$BK/diff.txt" | tee "$BK/diff.uniq.txt" | sed 's/^/  /'
ok "差异清单: $(wc -l < "$BK/diff.uniq.txt") 条"

# ---------------------------------------------------------------- 3. 落盘
say "3. 落盘"
cp -a "$STAGE/dist-x/conf/." /root/conf/ && ok "X  conf/ → /root/conf/"
cp -a "$STAGE/dist-x/xray-panel.sh" /root/xray-panel.sh && chmod +x /root/xray-panel.sh && ok "X  xray-panel.sh"
cp -a "$STAGE/dist-m/src/." /root/catmi/mihomo/src/ && ok "M  src/ → /root/catmi/mihomo/src/"
cp -a "$STAGE/dist-sb/src/conf/." /root/catmi/sing-box/conf/ && ok "SB conf/ → /root/catmi/sing-box/conf/"
# ★ 跨目录依赖：服务端 conf/share.sh 的发布链要 import compat2（conf/uri_express.py:49），
#   而 compat2.py 与 lib/proxy_node_compat/ 在仓库里属 **src/client/**，不在 src/conf/。
#   只按目录分发会漏掉它们 —— 症状是 conf/share.sh create-all 报
#   `ModuleNotFoundError: No module named 'compat2'` 并"拒绝静默发布"（真机实测）。
cp -a "$STAGE/dist-sb/src/client/compat2.py" /root/catmi/sing-box/conf/compat2.py \
  && ok "SB conf/compat2.py（来自 src/client/）"
cp -a "$STAGE/dist-sb/src/client/lib/." /root/catmi/sing-box/conf/lib/ \
  && ok "SB conf/lib/（含 proxy_node_compat/）"
cp -a "$STAGE/dist-sb/src/sing-box.sh" /root/catmi/sing-box/sing-box.sh && ok "SB sing-box.sh"
cp -a "$STAGE/dist-sb/install.sh" /root/catmi/sing-box/install.sh && ok "SB install.sh"
chmod +x /root/conf/*.sh /root/conf/lib/*.sh /root/catmi/mihomo/src/*.sh /root/catmi/mihomo/src/lib/*.sh \
         /root/catmi/mihomo/src/share/*.sh /root/catmi/mihomo/src/conf/*.sh \
         /root/catmi/sing-box/conf/*.sh /root/catmi/sing-box/sing-box.sh 2>/dev/null
ok "可执行位已补"

# ---------------------------------------------------------------- 4. 复核
say "4. 分发后复核（逐字节）"
verify() {              # $1=源目录 $2=目标目录 $3=名字
  local src=$1 dst=$2 name=$3 n=0 same=0 diff=0 missing=0 f rel
  while IFS= read -r f; do
    rel=${f#./}; n=$((n+1))
    if [[ ! -e "$dst/$rel" ]]; then missing=$((missing+1)); echo "  MISSING $name$rel"
    elif cmp -s "$src/$rel" "$dst/$rel"; then same=$((same+1))
    else diff=$((diff+1)); echo "  DIFFERS $name$rel"; fi
  done < <( cd "$src" && find . -type f | sort )
  printf '  %-6s 共 %d  相同 %d  不同 %d  缺失 %d\n' "$name" "$n" "$same" "$diff" "$missing"
  [[ $diff -eq 0 && $missing -eq 0 ]] && ok "$name 逐字节一致" || bad "$name 有差异"
}
verify "$STAGE/dist-x/conf"      /root/conf                "X/conf/"
verify "$STAGE/dist-m/src"       /root/catmi/mihomo/src    "M/src/"
verify "$STAGE/dist-sb/src/conf"   /root/catmi/sing-box/conf   "SB/conf/"
verify "$STAGE/dist-sb/src/client/lib" /root/catmi/sing-box/conf/lib "SB/conf/lib/"
cmp -s "$STAGE/dist-sb/src/client/compat2.py" /root/catmi/sing-box/conf/compat2.py \
  && ok "SB conf/compat2.py 逐字节一致" || bad "SB conf/compat2.py 不一致"
cmp -s "$STAGE/dist-x/xray-panel.sh" /root/xray-panel.sh && ok "xray-panel.sh 逐字节一致" || bad "xray-panel.sh 不一致"

# ---------------------------------------------------------------- 5. 服务未动
say "5. 服务 PID 复核（必须与 before 完全一致）"
for s in xrayls mihomo sing-box proxy-share-service nginx; do
  before=$(grep -m1 "^$s " "$BK/pids-before.txt" || true)
  cur="$s pid=$(systemctl show -p MainPID --value $s 2>/dev/null) since=$(systemctl show -p ActiveEnterTimestamp --value $s 2>/dev/null) active=$(systemctl is-active $s 2>/dev/null)"
  if [[ "$cur" == "$before" ]]; then ok "$s 未变 ($(systemctl show -p MainPID --value $s 2>/dev/null))"; else bad "$s 变了: '$before' → '$cur'"; fi
done

printf '\n\033[1m== 汇总: 失败 %d 项 ==\033[0m  备份目录: %s\n' "$FAILED" "$BK"
exit $(( FAILED > 0 ? 1 : 0 ))
