#!/bin/bash
cd /tmp/qeval
source /tmp/qeval/measure.sh
# A-control: the ACTUAL shipped mihomo CDN WS client config (no alpn + ECH)
for rep in 1 2 3; do
  n="A2_shipped_vless_cdn_ws_ECH_r$rep"
  pid=$(start mh /tmp/qeval/mh/m_cdn_vless04_ws.yaml "$n")
  if wait_up; then measure "$n"; else printf "%s\tNO-LISTEN\t-\t-\n" "$n" >> $RES; echo "$n NO-LISTEN"; fi
  kill $pid 2>/dev/null; sleep 0.8; kill -9 $pid 2>/dev/null; wait $pid 2>/dev/null; sleep 0.6
done
# remaining unmeasured nodes
for f in /tmp/qeval/mh/m_vless02_reality_grpc.yaml /tmp/qeval/mh/m_trojan02_reality_grpc.yaml /tmp/qeval/mh/m_cdn_trojan05_grpc.yaml /tmp/qeval/mhx/m_vless02_reality_grpc_NOWS.yaml; do
  [ -f "$f" ] || { echo "MISSING $f"; continue; }
  n="x_$(basename "$f" .yaml)"
  run_one mh "$f" "$n"
done
echo "=== DONE-FINAL ==="
