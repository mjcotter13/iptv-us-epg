#!/usr/bin/env python3
from pathlib import Path
import csv, xml.etree.ElementTree as ET
WORK=Path("v7_work")
channels=list(csv.DictReader((WORK/"channels.csv").open(encoding="utf-8")))
runtime_path=WORK/"attempt_status_runtime.csv"
runtime=list(csv.DictReader(runtime_path.open(encoding="utf-8"))) if runtime_path.exists() else []

with open("v7_attempt_status.csv","w",newline="",encoding="utf-8") as f:
    fields=list(runtime[0].keys()) if runtime else ["id"]
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(runtime)

tv=ET.Element("tv",{"generator-info-name":"IPTV-org targeted V7.3"})
seen=set(); final=[]
for ch in channels:
    cid=ch["id"]
    wins=[r for r in runtime if r["id"]==cid and r["success"]=="YES"]
    wins.sort(key=lambda x:int(x["attempt"]))
    if not wins:
        final.append({"id":cid,"name":ch["name"],"group":ch["group"],"match_kind":"","match_score":"","candidate_xmltv_id":"","candidate_name":"","site":"","attempt_used":"","programmes":0,"success":"NO"})
        continue
    best=wins[0]; root=ET.parse(WORK/best["guide_file"]).getroot()
    for ce in root.findall("channel"):
        if (ce.get("id") or "").strip()==cid and cid not in seen:
            tv.append(ce); seen.add(cid)
    pc=0
    for p in root.findall("programme"):
        if (p.get("channel") or "").strip()==cid:
            tv.append(p); pc+=1
    final.append({"id":cid,"name":ch["name"],"group":ch["group"],
                  "match_kind":best["match_kind"],"match_score":best["match_score"],
                  "candidate_xmltv_id":best["candidate_xmltv_id"],"candidate_name":best["candidate_name"],
                  "site":best["site"],"attempt_used":best["attempt"],"programmes":pc,"success":"YES"})
ET.ElementTree(tv).write("v7_targeted_guide.xml",encoding="utf-8",xml_declaration=True)
fields=["id","name","group","match_kind","match_score","candidate_xmltv_id","candidate_name","site","attempt_used","programmes","success"]
with open("v7_targeted_status.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(final)
print("V7.3 successes:",sum(r["success"]=="YES" for r in final))
print("V7.3 fuzzy successes:",sum(r["success"]=="YES" and r["match_kind"]=="fuzzy" for r in final))
