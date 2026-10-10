#!/bin/bash
source /tmp/qeval/measure.sh
echo "=== MH nodes (rerun) ===" >> $RES
for f in /tmp/qeval/mh/*.yaml; do
  n=$(basename "$f" .yaml)
  run_one mh "$f" "$n"
done
echo "=== DONE-MH ==="
