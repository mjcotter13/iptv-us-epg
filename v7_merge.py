#!/usr/bin/env python3
from pathlib import Path
import csv
import xml.etree.ElementTree as ET
from collections import Counter

WORK = Path("v7_work")
TARGETS = WORK / "targets.csv"
OUT = Path("v7_targeted_guide.xml")
REPORT = Path("v7_targeted_status.csv")

tv = ET.Element("tv", {"generator-info-name": "IPTV-org targeted V7"})
seen_channels = set()
counts = Counter()

targets = list(csv.DictReader(TARGETS.open(encoding="utf-8"))) if TARGETS.exists() else []

for item in targets:
    guide = WORK / item["guide_file"]
    if not guide.exists() or guide.stat().st_size == 0:
        continue
    try:
        root = ET.parse(guide).getroot()
    except Exception as exc:
        print(f"Skipping {guide}: {exc}")
        continue

    for ch in root.findall("channel"):
        cid = (ch.get("id") or "").strip()
        if cid and cid not in seen_channels:
            tv.append(ch)
            seen_channels.add(cid)

    for p in root.findall("programme"):
        cid = (p.get("channel") or "").strip()
        if cid:
            tv.append(p)
            counts[cid] += 1

ET.ElementTree(tv).write(OUT, encoding="utf-8", xml_declaration=True)

with REPORT.open("w", newline="", encoding="utf-8") as f:
    fields = ["id","name","group","site","site_id","programmes","success"]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for item in targets:
        cid = item["id"]
        w.writerow({
            "id": cid,
            "name": item["name"],
            "group": item["group"],
            "site": item["site"],
            "site_id": item["site_id"],
            "programmes": counts[cid],
            "success": "YES" if counts[cid] > 0 else "NO",
        })

working = sum(1 for item in targets if counts[item["id"]] > 0)
print(f"V7 targeted: {working}/{len(targets)} channels returned programmes")
for item in targets:
    print(f"{item['id']}: {counts[item['id']]} programmes")
