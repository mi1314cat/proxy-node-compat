#!/bin/bash
source /tmp/qeval/measure.sh
for f in /tmp/qeval/mh/m_vless02_reality_grpc.yaml /tmp/qeval/mh/m_trojan02_reality_grpc.yaml /tmp/qeval/mh/m_cdn_trojan05_grpc.yaml /tmp/qeval/mihomo/m_vless02_reality_grpc_NOWS.yaml; do
  [ -f "$f" ] || continue
  n=x_$(basename "$f" .yaml)
  run_one mh "$f" "$n"
done
echo "=== DONE-EXTRA ==="
