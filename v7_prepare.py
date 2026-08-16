#!/usr/bin/env python3
from pathlib import Path
import csv
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

EPG_REPO = Path("_iptv_epg")
INPUT = Path("public/high_value_unmatched.csv")
WORK = Path("v7_work")
WORK.mkdir(exist_ok=True)

MAX_MAPPINGS_PER_CHANNEL = 3

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

# Empirical ranking from our successful V7/V7.1 runs.
# TVPassport was 19/19, OnTVTonight 3/3, TV Guide 4/4, i.mjh.nz strong,
# while TVTV and DistroTV were poor.
def source_rank(site: str):
    s = (site or "").lower()
    if "tvpassport.com" in s:
        return 0
    if "ontvtonight.com" in s:
        return 1
    if "tvguide.com" in s:
        return 2
    if "i.mjh.nz" in s:
        return 3
    if "watchyour.tv" in s:
        return 4
    if "plex.tv" in s or "plex" in s:
        return 5
    if "tvtv.us" in s:
        return 8
    if "distro.tv" in s:
        return 9
    if "epgshare01.online" in s:
        return 10
    return 6

if not INPUT.exists():
    raise SystemExit("public/high_value_unmatched.csv not found")

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
        if xid not in wanted_ids:
            continue

        found[xid].append({
            "site": (ch.get("site") or "").strip(),
            "lang": (ch.get("lang") or "en").strip(),
            "xmltv_id": xid,
            "site_id": (ch.get("site_id") or "").strip(),
            "name": (ch.text or xid).strip(),
            "source_file": str(path),
        })

selected_channels = []
attempt_rows = []

for row in rows:
    xid = row["id"]
    choices = [x for x in found.get(xid, []) if x["site"] and x["site_id"]]

    unique = {}
    for c in choices:
        unique[(c["site"], c["site_id"])] = c

    choices = list(unique.values())
    choices.sort(key=lambda x: (source_rank(x["site"]), x["site"], x["site_id"]))

    safe = re.sub(r"[^A-Za-z0-9]+", "_", xid).strip("_")

    selected_channels.append({
        "id": xid,
        "name": row.get("name", ""),
        "group": row.get("group", ""),
        "safe": safe,
        "mapping_count": min(len(choices), MAX_MAPPINGS_PER_CHANNEL),
    })

    for attempt_num, chosen in enumerate(choices[:MAX_MAPPINGS_PER_CHANNEL], start=1):
        ch_file = f"{safe}.attempt{attempt_num}.channels.xml"
        guide_file = f"{safe}.attempt{attempt_num}.guide.xml"

        root = ET.Element("channels")
        el = ET.SubElement(root, "channel", {
            "site": chosen["site"],
            "lang": chosen["lang"],
            "xmltv_id": chosen["xmltv_id"],
            "site_id": chosen["site_id"],
        })
        el.text = chosen["name"]

        ET.ElementTree(root).write(
            WORK / ch_file,
            encoding="utf-8",
            xml_declaration=True,
        )

        attempt_rows.append({
            "id": xid,
            "name": row.get("name", ""),
            "group": row.get("group", ""),
            "attempt": attempt_num,
            "site": chosen["site"],
            "site_id": chosen["site_id"],
            "xmltv_id": chosen["xmltv_id"],
            "channel_file": ch_file,
            "guide_file": guide_file,
            "source_file": chosen["source_file"],
        })

with (WORK / "channels.csv").open("w", newline="", encoding="utf-8") as f:
    fields = ["id","name","group","safe","mapping_count"]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(selected_channels)

with (WORK / "attempts.csv").open("w", newline="", encoding="utf-8") as f:
    fields = [
        "id","name","group","attempt","site","site_id","xmltv_id",
        "channel_file","guide_file","source_file"
    ]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(attempt_rows)

mapped = sum(1 for r in selected_channels if int(r["mapping_count"]) > 0)

print(f"High-value unmatched channels: {len(selected_channels)}")
print(f"Channels with at least one exact IPTV-org mapping: {mapped}")
print(f"Total mapping attempts prepared: {len(attempt_rows)}")
