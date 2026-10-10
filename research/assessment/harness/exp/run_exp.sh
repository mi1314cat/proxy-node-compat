#!/bin/bash
source /tmp/qeval/measure.sh
: >> $RES
for f in /tmp/qeval/exp/*.yaml; do
  n=exp_$(basename "$f" .yaml)
  cp "$f" /tmp/qeval/exp/../tmpcfg.yaml 2>/dev/null
  run_one mh "$f" "$n"
done
echo "=== DONE-EXP ==="
