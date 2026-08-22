#!/usr/bin/env python3
from __future__ import annotations
import csv, copy, gzip, re, unicodedata, urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

PLAYLIST_URL="https://iptv-org.github.io/iptv/countries/us.m3u"
GUIDE=Path("public/guide.xml.gz")
OUT_GUIDE=Path("v10_rescue_guide.xml")
OUT_REPORT=Path("v10_rescue_report.csv")
OUT_STATUS=Path("v10_rescue_status.txt")

SOURCES=[
 ("Pluto TV US","https://i.mjh.nz/PlutoTV/us.xml.gz"),
 ("Plex US","https://i.mjh.nz/Plex/us.xml.gz"),
 ("Samsung TV Plus US","https://i.mjh.nz/SamsungTVPlus/us.xml.gz"),
 ("Roku","https://i.mjh.nz/Roku/all.xml.gz"),
 ("PBS","https://i.mjh.nz/PBS/all.xml.gz"),
 ("MJH Combined","https://i.mjh.nz/all/epg.xml.gz"),
]
ALIASES={
 "ParamountMovieChannel.us":["Paramount Movie Channel"],
 "NFLChannel.us":["NFL Channel"],
 "PlutoTVTheTwilightZone.us":["The Twilight Zone","Pluto TV The Twilight Zone"],
}
ATTR_RE=re.compile(r'([\w-]+)="([^"]*)"')
STOP={"hd","sd","uhd","4k","east","west","eastern","western","feed","channel","network","television","usa","us","united","states","live"}

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 V10-EPG-Rescue"})
    return urllib.request.urlopen(req,timeout=90).read()

def norm(s):
    if not s:return ""
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower().replace("&"," and ")
    toks=[t for t in re.findall(r"[a-z0-9]+",s) if t not in STOP]
    return " ".join(toks)

def compact(s): return "".join(norm(s).split())

def id_stem(s):
    s=re.sub(r"@.*$","",s or "")
    s=re.sub(r"\.[A-Za-z]{2,3}$","",s)
    return norm(s)

def parse_time(v):
    if not v:return None
    for fmt in ("%Y%m%d%H%M%S %z","%Y%m%d%H%M %z","%Y%m%d%H%M%S","%Y%m%d%H%M"):
        try:
            d=datetime.strptime(v.strip(),fmt)
            if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc)
        except ValueError:pass
    return None

def relevant(p,now):
    stop=parse_time(p.get("stop")); start=parse_time(p.get("start"))
    if stop:return stop>=now
    if start:return start>=now
    return True

def parse_m3u(raw):
    rows=[]; seen=set()
    for line in raw.decode("utf-8",errors="replace").splitlines():
        line=line.strip()
        if not line.startswith("#EXTINF:"):continue
        attrs=dict(ATTR_RE.findall(line)); cid=(attrs.get("tvg-id") or "").strip()
        if not cid or cid in seen:continue
        seen.add(cid)
        rows.append({"id":cid,"name":line.split(",",1)[1].strip() if "," in line else "",
                     "tvg_name":(attrs.get("tvg-name") or "").strip(),
                     "group":(attrs.get("group-title") or "").strip()})
    return rows

def covered_ids():
    now=datetime.now(timezone.utc)
    with gzip.open(GUIDE,"rb") as f: root=ET.parse(f).getroot()
    return {(p.get("channel") or "").strip() for p in root.findall("programme") if relevant(p,now)}

def load_source(label,url):
    raw=fetch(url)
    if url.endswith(".gz"):raw=gzip.decompress(raw)
    root=ET.fromstring(raw)
    channels={}; programmes=defaultdict(list); name_index=defaultdict(set); compact_index=defaultdict(set); stem_index=defaultdict(set)
    for ch in root.findall("channel"):
        cid=(ch.get("id") or "").strip()
        if not cid:continue
        names=[(x.text or "").strip() for x in ch.findall("display-name") if (x.text or "").strip()]
        channels[cid]={"element":ch,"names":names}
        for name in names:
            if norm(name):name_index[norm(name)].add(cid)
            if compact(name):compact_index[compact(name)].add(cid)
        if id_stem(cid):stem_index[id_stem(cid)].add(cid)
    now=datetime.now(timezone.utc)
    for p in root.findall("programme"):
        cid=(p.get("channel") or "").strip()
        if cid and relevant(p,now):programmes[cid].append(p)
    return {"label":label,"channels":channels,"programmes":programmes,"name_index":name_index,"compact_index":compact_index,"stem_index":stem_index}

def queries(row):
    q=[row["name"],row["tvg_name"],row["id"],id_stem(row["id"])]
    q.extend(ALIASES.get(row["id"],[]))
    return [x for x in q if x]

def long_score(a,b):
    ca,cb=compact(a),compact(b)
    if len(ca)<8 or len(cb)<8:return 0.0
    na,nb=norm(a),norm(b)
    seq=SequenceMatcher(None,na,nb).ratio()
    ta,tb=set(na.split()),set(nb.split())
    jac=len(ta&tb)/len(ta|tb) if ta|tb else 0
    if seq>=.965 and jac>=.5:return seq
    if seq>=.945 and len(ta&tb)>=2 and jac>=.65:return seq
    return 0.0

def find(row,src):
    if row["id"] in src["channels"] and src["programmes"].get(row["id"]):
        return row["id"],"exact-id",1.0
    cand=set()
    for q in queries(row):
        cand |= src["name_index"].get(norm(q),set())
    cand={x for x in cand if src["programmes"].get(x)}
    if len(cand)==1:return next(iter(cand)),"exact-normalized-name",1.0
    cand=set()
    for q in queries(row):
        cand |= src["compact_index"].get(compact(q),set())
    cand={x for x in cand if src["programmes"].get(x)}
    if len(cand)==1:return next(iter(cand)),"exact-compact-name",.995
    st=id_stem(row["id"]); cand=set(src["stem_index"].get(st,set())) if st else set()
    cand={x for x in cand if src["programmes"].get(x)}
    if len(cand)==1:return next(iter(cand)),"exact-id-stem",.99
    ranked=[]
    for cid,meta in src["channels"].items():
        if not src["programmes"].get(cid):continue
        best=0
        for q in queries(row):
            for sn in meta["names"]:best=max(best,long_score(q,sn))
        if best:ranked.append((best,cid))
    ranked.sort(reverse=True)
    if ranked:
        second=ranked[1][0] if len(ranked)>1 else 0
        if ranked[0][0]>=.945 and ranked[0][0]-second>=.03:
            return ranked[0][1],"safe-long-name",ranked[0][0]
    return None

playlist=parse_m3u(fetch(PLAYLIST_URL)); covered=covered_ids()
missing=[r for r in playlist if r["id"] not in covered]
out=ET.Element("tv",{"generator-info-name":"V10 Generic Multi-Platform Rescue"})
report=[]; rescued=set()
for label,url in SOURCES:
    try:src=load_source(label,url)
    except Exception as e:
        print("WARNING",label,e);continue
    added=0
    for row in [r for r in missing if r["id"] not in rescued]:
        m=find(row,src)
        if not m:continue
        sid,method,score=m
        ch=ET.SubElement(out,"channel",{"id":row["id"]});ET.SubElement(ch,"display-name").text=row["name"] or row["id"]
        for tag in ("icon","url"):
            for child in src["channels"][sid]["element"].findall(tag):ch.append(copy.deepcopy(child))
        pc=0
        for p in src["programmes"][sid]:
            cp=copy.deepcopy(p);cp.set("channel",row["id"]);out.append(cp);pc+=1
        rescued.add(row["id"]);added+=1
        report.append({"playlist_id":row["id"],"playlist_name":row["name"],"group":row["group"],"source":label,"source_id":sid,"match_method":method,"score":round(score,4),"programmes":pc})
    print(f"{label}: +{added}")
ET.ElementTree(out).write(OUT_GUIDE,encoding="utf-8",xml_declaration=True)
with OUT_REPORT.open("w",newline="",encoding="utf-8") as f:
    fields=["playlist_id","playlist_name","group","source","source_id","match_method","score","programmes"]
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(report)
counts=defaultdict(int)
for r in report:counts[r["source"]]+=1
lines=[f"playlist_channels={len(playlist)}",f"covered_before_v10={len(covered)}",f"eligible_for_rescue={len(missing)}",f"v10_rescued_channels={len(rescued)}"]
for label,_ in SOURCES:lines.append(f"{re.sub(r'[^a-z0-9]+','_',label.lower()).strip('_')}_matches={counts[label]}")
lines.append(f"remaining_after_v10={len(missing)-len(rescued)}")
OUT_STATUS.write_text("\n".join(lines)+"\n")
print(OUT_STATUS.read_text())
