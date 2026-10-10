#!/bin/bash
source /tmp/qeval/measure.sh
for f in /tmp/qeval/exp/e2_*.yaml; do
  n=exp2_$(basename "$f" .yaml)
  run_one mh "$f" "$n"
done
echo "=== DONE-E2 ==="
