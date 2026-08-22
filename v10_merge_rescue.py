#!/usr/bin/env python3
import copy,gzip
import xml.etree.ElementTree as ET
with gzip.open("public/guide.xml.gz","rb") as f:root=ET.parse(f).getroot()
rr=ET.parse("v10_rescue_guide.xml").getroot()
by={}
for p in rr.findall("programme"):by.setdefault((p.get("channel") or "").strip(),[]).append(p)
existing={(c.get("id") or "").strip() for c in root.findall("channel")}
for cid,ps in by.items():
    if not cid or not ps:continue
    for p in list(root.findall("programme")):
        if (p.get("channel") or "").strip()==cid:root.remove(p)
    if cid not in existing:
        c=next((x for x in rr.findall("channel") if (x.get("id") or "").strip()==cid),None)
        if c is not None:root.append(copy.deepcopy(c));existing.add(cid)
    for p in ps:root.append(copy.deepcopy(p))
with gzip.open("public/guide.xml.gz","wb",compresslevel=9) as f:
    f.write(ET.tostring(root,encoding="utf-8",xml_declaration=True))
