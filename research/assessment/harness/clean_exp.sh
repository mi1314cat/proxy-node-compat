#!/bin/bash
# CLEAN controlled experiment: strict single-instance isolation
cd /tmp/qeval
SB=./sing-box-1.14.2-linux-arm64/sing-box
MH=./mihomo
RES=/tmp/qeval/clean_results.tsv
pkill -f "/tmp/qeval/mihomo" 2>/dev/null; sleep 2
: > $RES
run() { # $1 cfg $2 label $3 rep
  local cfg=$1 label=$2 rep=$3 pid
  pkill -f "/tmp/qeval/mihomo" 2>/dev/null; sleep 1.5
  mkdir -p /tmp/qeval/dc
  $MH -f "$cfg" -d /tmp/qeval/dc >/tmp/qeval/clog_$label.txt 2>&1 &
  pid=$!
  local up=0
  for i in $(seq 1 25); do (echo > /dev/tcp/127.0.0.1/18080) 2>/dev/null && { up=1; break; }; sleep 0.4; done
  if [ $up -eq 0 ]; then printf "%s\tr%s\tNOLISTEN\t-\t-\n" "$label" "$rep" >> $RES; echo "$label r$rep NOLISTEN"; kill -9 $pid 2>/dev/null; return; fi
  local t d
  t=$(curl -s -o /dev/null -x http://127.0.0.1:18080 -w "%{time_starttransfer}" --max-time 25 "https://www.gstatic.com/generate_204" 2>/dev/null)
  d=$(curl -s -o /dev/null -x http://127.0.0.1:18080 -w "%{speed_download}|%{size_download}|%{time_total}" --max-time 45 "https://speed.cloudflare.com/__down?bytes=3000000" 2>/dev/null)
  printf "%s\tr%s\t%s\t%s\n" "$label" "$rep" "${t:-FAIL}" "${d:-FAIL}" >> $RES
  echo "$label r$rep ttfb=${t:-FAIL} dl=$d"
  kill $pid 2>/dev/null; sleep 0.8; kill -9 $pid 2>/dev/null; wait $pid 2>/dev/null
}
for rep in 1 2 3; do
  run /tmp/qeval/exp/m_cdn_vless04_ws.yaml            A_ws_SHIPPED_noalpn_ECH  $rep
  run /tmp/qeval/exp/e2_ws_noalpn_noech.yaml          B_ws_noalpn_noECH        $rep
  run /tmp/qeval/exp/m_cdn_vless04_ws_ALPN.yaml       C_ws_alpn_noECH          $rep
  run /tmp/qeval/exp/e2_ws_ech_debug.yaml             D_ws_alpn_ECH            $rep
  run /tmp/qeval/exp/m_hy2_cap_5.yaml                 E_hy2_down_bare5         $rep
  run /tmp/qeval/exp/m_hy2_cap_5Mbps.yaml             F_hy2_down_5Mbps         $rep
  run /tmp/qeval/exp/e2_grpc_ech.yaml                 G_grpc_ECH               $rep
done
echo "=== CLEAN DONE ==="
