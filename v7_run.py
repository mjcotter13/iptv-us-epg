#!/usr/bin/env python3
from pathlib import Path
import csv, os, subprocess, time
import xml.etree.ElementTree as ET

WORK=Path("v7_work")
channels=list(csv.DictReader((WORK/"channels.csv").open(encoding="utf-8")))
attempts=list(csv.DictReader((WORK/"attempts.csv").open(encoding="utf-8")))
byid={}
for a in attempts: byid.setdefault(a["id"],[]).append(a)

BUDGET=48*60
PER_ATTEMPT=120
start=time.monotonic()
status=[]

def count_programmes(path,cid):
    if not path.exists() or path.stat().st_size==0: return 0
    try: root=ET.parse(path).getroot()
    except Exception: return 0
    return sum(1 for p in root.findall("programme") if (p.get("channel") or "").strip()==cid)

for ch in channels:
    cid=ch["id"]
    if time.monotonic()-start>=BUDGET:
        print("GLOBAL BUDGET REACHED",flush=True); break
    choices=sorted(byid.get(cid,[]),key=lambda x:int(x["attempt"]))
    if not choices:
        print(f"===== {cid}: NO SAFE CANDIDATES =====",flush=True); continue
    for a in choices:
        if time.monotonic()-start>=BUDGET: break
        print(f"===== {cid} | {a['match_kind']} {a['match_score']} | {a['candidate_name']} | {a['site']} =====",flush=True)
        env=os.environ.copy(); env["NODE_OPTIONS"]="--max-old-space-size=2048"
        cmd=["npm","run","grab","---",
             f"--channels=../v7_work/{a['channel_file']}",
             f"--output=../v7_work/{a['guide_file']}",
             "--days=1","--maxConnections=1","--delay=750","--timeout=25000"]
        timed=False; rc=""
        try:
            r=subprocess.run(cmd,cwd="_iptv_epg",env=env,check=False,timeout=PER_ATTEMPT)
            rc=r.returncode
        except subprocess.TimeoutExpired:
            timed=True
        cnt=count_programmes(WORK/a["guide_file"],cid)
        rec={**a,"programmes":cnt,"success":"YES" if cnt else "NO",
             "timed_out":"YES" if timed else "NO","return_code":rc}
        status.append(rec)
        if cnt:
            print(f"SUCCESS: {cid} -> {cnt} via {a['site']} [{a['match_kind']} {a['match_score']}]",flush=True)
            break

fields=list(status[0].keys()) if status else ["id"]
with (WORK/"attempt_status_runtime.csv").open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(status)
print(f"Executed {len(status)} attempts; successful channels={len({x['id'] for x in status if x['success']=='YES'})}")
