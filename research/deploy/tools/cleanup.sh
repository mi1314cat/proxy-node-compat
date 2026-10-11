#!/usr/bin/env bash
# ============================================================================
#  推送前清理 —— RN + CC
#
#  用户 2026-07-11 的决定（原话：两个都删，RN 上不留备份）+ 既有的
#  "配置完就清掉临时物" 纪律。
#
#  ⚠ 运行前请确认：四个仓库的推送已经成功（否则备份还有用）。
#  用法: bash cleanup.sh          # 真删
#        DRY=1 bash cleanup.sh    # 只列不删
# ============================================================================
set -uo pipefail
DRY="${DRY:-0}"

remote_script() { cat <<'REMOTE'
set -uo pipefail
DRY="${DRY:-0}"
say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
gone(){ printf '  \033[31m✗ 仍在\033[0m %s\n' "$*"; }
run() {
  if [[ "$DRY" == "1" ]]; then printf '  [dry] %s\n' "$*"; else eval "$@"; fi
}

say "1. 服务/内核进程基线（删除前后必须一致）"
REMOTE
}

LOCAL_STATE=/tmp/.cleanup-baseline-$$.txt

echo "═══════════════════════════ RN ═══════════════════════════"
timeout 300 ssh rn "DRY=$DRY bash -s" <<'REMOTE'
set -uo pipefail
DRY="${DRY:-0}"
say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
gone(){ printf '  \033[31m✗ 仍在\033[0m %s\n' "$*"; }
run() { if [[ "$DRY" == "1" ]]; then printf '  [dry] %s\n' "$*"; else eval "$@"; fi; }
svc() { for s in xrayls mihomo sing-box proxy-share-service nginx; do
          printf '%s pid=%s %s\n' "$s" \
            "$(systemctl show -p MainPID --value $s 2>/dev/null)" \
            "$(systemctl is-active $s 2>/dev/null)"; done; }

say "0. 服务基线"
svc | tee /tmp/.cleanup-before.txt | sed 's/^/  /'

say "1. 目标（删前体积）"
TARGETS=(/root/backup-20261010-085825 /root/backup-prepush-20261010-184809
         /tmp/dist-prepush /tmp/.prepush-backup-dir)
shopt -s nullglob
TARGETS+=(/tmp/*-col /tmp/*-col-* /tmp/x-col /tmp/m-col /tmp/sb-col)
shopt -u nullglob
for p in "${TARGETS[@]}"; do [[ -e "$p" ]] && du -sh "$p" 2>/dev/null | sed 's/^/  /'; done

say "2. 删除"
run "rm -rf $(printf '%q ' "${TARGETS[@]}")"
echo "  done"

say "3. 残留核查"
for p in "${TARGETS[@]}"; do [[ -e "$p" ]] && gone "$p" || ok "已清 $p"; done

say "4. 服务复核（必须与第 0 步逐字节相同）"
svc | tee /tmp/.cleanup-after.txt >/dev/null
if diff -q /tmp/.cleanup-before.txt /tmp/.cleanup-after.txt >/dev/null; then
  ok "五个服务 PID / 状态完全未变"
  sed 's/^/  /' /tmp/.cleanup-after.txt
else
  echo "  \033[31m服务变了:\033[0m"; diff /tmp/.cleanup-before.txt /tmp/.cleanup-after.txt | sed 's/^/    /'
fi
rm -f /tmp/.cleanup-before.txt /tmp/.cleanup-after.txt
REMOTE

echo
echo "═══════════════════════════ CC ═══════════════════════════"
timeout 300 ssh CC "DRY=$DRY bash -s" <<'REMOTE'
set -uo pipefail
DRY="${DRY:-0}"
say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
gone(){ printf '  \033[31m✗ 仍在\033[0m %s\n' "$*"; }
run() { if [[ "$DRY" == "1" ]]; then printf '  [dry] %s\n' "$*"; else eval "$@"; fi; }
procs() { for p in xray sing-box mihomo; do
            printf '%s %s\n' "$p" "$(pgrep -d, -f "$p" 2>/dev/null | head -c 200)"; done; }

say "0. 客户端内核进程基线"
procs | tee /tmp/.cleanup-before.txt | sed 's/^/  /'

say "1. 目标（删前体积）"
shopt -s nullglob
TARGETS=(/root/backup-cc-* /root/backup-prepush-cc-*
         /tmp/x-col /tmp/m-col /tmp/sb-col)
TARGETS+=(/tmp/*-col /tmp/*-col-*)
shopt -u nullglob
for p in "${TARGETS[@]}"; do [[ -e "$p" ]] && du -sh "$p" 2>/dev/null | sed 's/^/  /'; done

say "2. 删除"
run "rm -rf $(printf '%q ' "${TARGETS[@]}")"
echo "  done"

say "3. 残留核查"
for p in "${TARGETS[@]}"; do [[ -e "$p" ]] && gone "$p" || ok "已清 $p"; done

say "4. 进程复核"
procs | tee /tmp/.cleanup-after.txt >/dev/null
if diff -q /tmp/.cleanup-before.txt /tmp/.cleanup-after.txt >/dev/null; then
  ok "客户端内核进程未变"
else
  echo "  \033[33m进程列表有变化（可能只是临时 curl）:\033[0m"
  diff /tmp/.cleanup-before.txt /tmp/.cleanup-after.txt | sed 's/^/    /'
fi
rm -f /tmp/.cleanup-before.txt /tmp/.cleanup-after.txt
REMOTE
