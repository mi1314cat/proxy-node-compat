p="/tmp/qeval/measure.sh"
s=open(p).read()
old='  else $MH -f "$2" -d /tmp/qeval/d_$3 >/tmp/qeval/log_$3.txt 2>&1 & fi'
new='  else mkdir -p /tmp/qeval/d_$3; $MH -f "$2" -d /tmp/qeval/d_$3 >/tmp/qeval/log_$3.txt 2>&1 & fi'
if old in s:
    s=s.replace(old,new); open(p,"w").write(s); print("PATCHED OK")
else:
    print("NOT FOUND"); i=s.find("start()"); print(s[i:i+300])
