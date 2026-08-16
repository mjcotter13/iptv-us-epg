#!/usr/bin/env python3
from pathlib import Path
import csv, gzip, json, re, urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

MATRIX=Path("public/v7/remaining_source_matrix.csv")
OUTDIR=Path("v8_work")
OUTDIR.mkdir(exist_ok=True)
OUT=OUTDIR/"source_discovery.csv"

def norm(s):
    s=(s or "").lower().replace("&"," and ")
    s=re.sub(r"\b(hd|sd|uhd|4k|east|west|eastern|western|feed|channel|network|tv|television|usa|us|live)\b"," ",s)
    return " ".join(re.findall(r"[a-z0-9]+",s))

def score(a,b):
    a,b=norm(a),norm(b)
    if not a or not b: return 0.0
    if a==b: return 1.0
    ta,tb=set(a.split()),set(b.split())
    jac=len(ta&tb)/len(ta|tb) if ta|tb else 0
    seq=SequenceMatcher(None,a,b).ratio()
    return max(seq,.55*seq+.45*jac)

rows=list(csv.DictReader(MATRIX.open(encoding="utf-8")))
targets=[r for r in rows if r.get("discovery_class")=="NEW_SOURCE_NEEDED"]

# Public guide families already exposed by EPGShare and useful to our remaining US/FAST/sports pool.
feeds = {
 "EPGShare_US1":"https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz",
 "EPGShare_US_LOCALS2":"https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS2.xml.gz",
 "EPGShare_US_SPORTS1":"https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz",
 "EPGShare_RALLY_TV1":"https://epgshare01.online/epgshare01/epg_ripper_RALLY_TV1.xml.gz",
 "EPGShare_PLEX1":"https://epgshare01.online/epgshare01/epg_ripper_PLEX1.xml.gz",
 "EPGShare_SAMSUNG1":"https://epgshare01.online/epgshare01/epg_ripper_SAMSUNG1.xml.gz",
}

catalog=[]
for label,url in feeds.items():
    try:
        print("Downloading",label,flush=True)
        data=urllib.request.urlopen(url,timeout=45).read()
        if url.endswith(".gz"): data=gzip.decompress(data)
        root=ET.fromstring(data)
        for ch in root.findall("channel"):
            cid=ch.get("id","")
            names=[(x.text or "") for x in ch.findall("display-name")]
            for name in names or [cid]:
                catalog.append((label,cid,name,url))
    except Exception as e:
        print("WARN",label,e,flush=True)

results=[]
for t in targets:
    q=t.get("name") or t.get("id","").split(".")[0]
    cand=[]
    for label,cid,name,url in catalog:
        sc=max(score(q,name),score(t.get("id","").split(".")[0],cid))
        if sc>=0.90:
            cand.append((sc,label,cid,name,url))
    cand.sort(reverse=True)
    for rank,c in enumerate(cand[:5],1):
        sc,label,cid,name,url=c
        results.append({
          "playlist_id":t["id"],"playlist_name":t.get("name",""),"group":t.get("group",""),
          "rank":rank,"score":f"{sc:.4f}","source":label,"source_channel_id":cid,
          "source_channel_name":name,"source_url":url,
          "auto_merge":"YES" if sc>=0.985 and norm(q)==norm(name) else "REVIEW"
        })

with OUT.open("w",newline="",encoding="utf-8") as f:
    fields=["playlist_id","playlist_name","group","rank","score","source","source_channel_id","source_channel_name","source_url","auto_merge"]
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(results)

print("NEW_SOURCE_NEEDED targets:",len(targets))
print("Discovery candidates:",len(results))
print("Targets with candidates:",len(set(r["playlist_id"] for r in results)))
print("Exact normalized auto-merge candidates:",sum(r["auto_merge"]=="YES" for r in results))
