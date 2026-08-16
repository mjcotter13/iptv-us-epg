#!/usr/bin/env python3
from pathlib import Path
import csv, re
import xml.etree.ElementTree as ET
from collections import defaultdict

EPG_REPO = Path("_iptv_epg")
INPUT = Path("public/high_value_unmatched.csv")
WORK = Path("v7_work")
WORK.mkdir(exist_ok=True)

LIMIT = 25
CATEGORY_PRIORITY = {
    "Sports": 0,
    "News": 1,
    "Entertainment": 2,
    "Movies": 3,
    "Series": 4,
    "Kids": 5,
    "Documentary": 6,
    "Comedy": 7,
    "Animation": 8,
}

if not INPUT.exists():
    raise SystemExit("public/high_value_unmatched.csv not found; run production guide first")

rows = list(csv.DictReader(INPUT.open(encoding="utf-8")))

def priority(row):
    groups = [x.strip() for x in (row.get("group") or "").split(";")]
    p = min((CATEGORY_PRIORITY.get(g, 99) for g in groups), default=99)
    return (p, row.get("name") or "", row.get("id") or "")

rows.sort(key=priority)
wanted_ids = {r["id"] for r in rows if r.get("id")}

found = defaultdict(list)
for path in EPG_REPO.glob("sites/**/*.channels.xml"):
    try:
        root = ET.parse(path).getroot()
    except Exception:
        continue
    for ch in root.findall("channel"):
        xid = (ch.get("xmltv_id") or "").strip()
        if xid in wanted_ids:
            found[xid].append({
                "site": (ch.get("site") or "").strip(),
                "lang": (ch.get("lang") or "en").strip(),
                "xmltv_id": xid,
                "site_id": (ch.get("site_id") or "").strip(),
                "name": (ch.text or xid).strip(),
                "source_file": str(path),
            })

def source_rank(item):
    site = item["site"].lower()
    if "ontvtonight.com" in site:
        return 0
    if "tvguide.com" in site:
        return 1
    if "tvtv.us" in site:
        return 2
    if "epgshare01.online" in site:
        return 9
    return 3

selected = []
for row in rows:
    xid = row["id"]
    choices = [x for x in found.get(xid, []) if x["site"] and x["site_id"]]
    choices.sort(key=lambda x: (source_rank(x), x["site"], x["site_id"]))
    if not choices:
        continue
    chosen = choices[0]
    safe = re.sub(r"[^A-Za-z0-9]+", "_", xid).strip("_")
    selected.append({
        **row,
        **chosen,
        "safe": safe,
        "channel_file": f"{safe}.channels.xml",
        "guide_file": f"{safe}.guide.xml",
    })
    if len(selected) >= LIMIT:
        break

for item in selected:
    root = ET.Element("channels")
    el = ET.SubElement(root, "channel", {
        "site": item["site"],
        "lang": item["lang"],
        "xmltv_id": item["xmltv_id"],
        "site_id": item["site_id"],
    })
    el.text = item["name"]
    ET.ElementTree(root).write(
        WORK / item["channel_file"], encoding="utf-8", xml_declaration=True
    )

with (WORK / "targets.csv").open("w", newline="", encoding="utf-8") as f:
    fields = ["id","name","group","site","site_id","xmltv_id","safe","channel_file","guide_file","source_file"]
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(selected)

print(f"Selected {len(selected)} exact-mapped high-value channels for V7")
for item in selected:
    print(f"{item['id']} | {item['group']} | {item['site']} | {item['site_id']}")
