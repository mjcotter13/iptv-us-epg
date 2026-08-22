#!/usr/bin/env python3
from pathlib import Path
import json, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

TARGETS=[
("ParamountMovieChannel.us","Paramount Movie Channel","5cb0cae7a461406ffe3f5213"),
("NFLChannel.us","NFL Channel","5ced7d5df64be98e07ed47b6"),
("PlutoTVTheTwilightZone.us","Pluto TV The Twilight Zone","67352ed93a61d4000881f9fa"),
]
def xt(dt): return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")
def fetch(pid):
    now=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    q=urllib.parse.urlencode({"start":(now-timedelta(hours=1)).isoformat().replace("+00:00","Z"),
                              "stop":(now+timedelta(hours=12)).isoformat().replace("+00:00","Z"),
                              "channelIds":pid})
    last=None
    for base in ("https://service-channels.clusters.pluto.tv/v2/guide/timelines?",
                 "https://service-channels.clusters.pluto.tv/v1/guide/timelines?"):
        try:
            req=urllib.request.Request(base+q,headers={"User-Agent":"Mozilla/5.0"})
            return json.loads(urllib.request.urlopen(req,timeout=30).read())
        except Exception as e: last=e
    raise last
def timelines(x):
    out=[]
    def walk(v):
        if isinstance(v,dict):
            if isinstance(v.get("timelines"),list): out.extend(v["timelines"])
            for z in v.values(): walk(z)
        elif isinstance(v,list):
            for z in v: walk(z)
    walk(x); return out

tv=ET.Element("tv",{"generator-info-name":"V9 Priority Rescue"}); report=[]
for cid,name,pid in TARGETS:
    ch=ET.SubElement(tv,"channel",{"id":cid}); ET.SubElement(ch,"display-name").text=name
    n=0
    try:
        for item in timelines(fetch(pid)):
            st=item.get("start") or item.get("startTime")
            en=item.get("stop") or item.get("end") or item.get("endTime")
            title=item.get("title")
            ep=item.get("episode")
            if not title and isinstance(ep,dict): title=ep.get("name")
            if not (st and en and title): continue
            try:
                s=datetime.fromisoformat(st.replace("Z","+00:00")); e=datetime.fromisoformat(en.replace("Z","+00:00"))
            except: continue
            p=ET.SubElement(tv,"programme",{"channel":cid,"start":xt(s),"stop":xt(e)})
            ET.SubElement(p,"title",{"lang":"en"}).text=str(title); n+=1
        report.append(f"{name}={n}")
    except Exception as e: report.append(f"{name}=ERROR {e}")
ET.ElementTree(tv).write("v9_priority_guide.xml",encoding="utf-8",xml_declaration=True)
Path("v9_priority_status.txt").write_text("\n".join(report)+"\n")
print("\n".join(report))
