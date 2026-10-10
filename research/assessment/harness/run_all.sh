#!/bin/bash
source /tmp/qeval/measure.sh
: > $RES
echo "=== SB nodes ==="
for f in /tmp/qeval/sb/*.json; do
  n=$(basename "$f" .json)
  run_one sb "$f" "$n"
done
echo "=== MH nodes ==="
for f in /tmp/qeval/mh/*.yaml; do
  n=$(basename "$f" .yaml)
  run_one mh "$f" "$n"
done
echo "=== DONE ==="
