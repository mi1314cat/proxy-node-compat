#!/bin/bash
# read-only measurement harness (runs only in /tmp/qeval on CC)
cd /tmp/qeval
SB=./sing-box-1.14.2-linux-arm64/sing-box
MH=./mh
TARGET_LAT="https://www.gstatic.com/generate_204"
TARGET_DL="https://speed.cloudflare.com/__down?bytes=5000000"
RES=/tmp/qeval/results.tsv
PROXY="http://127.0.0.1:18080"

start() { # $1 engine $2 cfg $3 label
  if [ "$1" = sb ]; then $SB run -c "$2" >/tmp/qeval/log_$3.txt 2>&1 &
  else $MH -f "$2" -d /tmp/qeval/mhdir_$3 >/tmp/qeval/log_$3.txt 2>&1 & fi
  echo $!
}
wait_up() { for i in $(seq 1 25); do (echo > /dev/tcp/127.0.0.1/18080) 2>/dev/null && return 0; sleep 0.4; done; return 1; }

measure() { # $1 label
  local label=$1
  local lat1 lat2 dl1 dl2
  lat1=$(curl -s -o /dev/null -x "$PROXY" -w "%{time_starttransfer}" --max-time 20 "$TARGET_LAT" 2>/dev/null)
  lat2=$(curl -s -o /dev/null -x "$PROXY" -w "%{time_starttransfer}" --max-time 20 "$TARGET_LAT" 2>/dev/null)
  dl1=$(curl -s -o /dev/null -x "$PROXY" -w "%{speed_download}|%{time_total}|%{size_download}" --max-time 90 "$TARGET_DL" 2>/dev/null)
  dl2=$(curl -s -o /dev/null -x "$PROXY" -w "%{speed_download}|%{time_total}|%{size_download}" --max-time 90 "$TARGET_DL" 2>/dev/null)
  printf "%s\t%s\t%s\t%s\t%s\n" "$label" "${lat1:-FAIL}" "${lat2:-FAIL}" "${dl1:-FAIL}" "${dl2:-FAIL}" >> "$RES"
  echo "$label  ttfb=$lat1/$lat2  dl=$dl1  dl2=$dl2"
}

run_one() { # $1 engine $2 cfg $3 label $4 workdir
  local pid
  pid=$(start "$1" "$2" "$3")
  if wait_up; then measure "$3"; else
    printf "%s\tNO-LISTEN\t-\t-\t-\n" "$3" >> "$RES"; echo "$3 NO-LISTEN"
  fi
  kill $pid 2>/dev/null; sleep 0.6; kill -9 $pid 2>/dev/null; wait $pid 2>/dev/null
  sleep 0.4
}
