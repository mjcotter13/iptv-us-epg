#!/usr/bin/env python3
import gzip, copy
import xml.etree.ElementTree as ET
root=ET.parse(gzip.open("public/guide.xml.gz","rb")).getroot()
pr=ET.parse("v9_priority_guide.xml").getroot()
ids={(p.get("channel") or "") for p in pr.findall("programme")}
existing={(c.get("id") or "") for c in root.findall("channel")}
for cid in ids:
    for p in list(root.findall("programme")):
        if (p.get("channel") or "")==cid: root.remove(p)
    if cid not in existing:
        c=next((x for x in pr.findall("channel") if (x.get("id") or "")==cid),None)
        if c is not None: root.append(copy.deepcopy(c))
    for p in pr.findall("programme"):
        if (p.get("channel") or "")==cid: root.append(copy.deepcopy(p))
with gzip.open("public/guide.xml.gz","wb",compresslevel=9) as f:
    f.write(ET.tostring(root,encoding="utf-8",xml_declaration=True))
