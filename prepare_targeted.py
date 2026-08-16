#!/usr/bin/env python3
"""
Build targeted.channels.xml from the prior run's high_value_unmatched.csv
by searching official iptv-org/epg *.channels.xml mappings.

The resulting file is used by:
  npm run grab --- --channels=... --output=...
"""
from pathlib import Path
import csv
import xml.etree.ElementTree as ET
from collections import defaultdict

EPG_REPO = Path("_iptv_epg")
UNMATCHED = Path("public/high_value_unmatched.csv")
OUT = Path("targeted.channels.xml")

if not EPG_REPO.exists():
    raise SystemExit("Missing _iptv_epg clone")

wanted = set()
if UNMATCHED.exists():
    with UNMATCHED.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            cid = (row.get("id") or "").strip()
            if cid:
                wanted.add(cid)

if not wanted:
    raise SystemExit("No prior high-value unmatched IDs available")

# Prefer exact xmltv_id mappings and cap duplicates per channel.
found = defaultdict(list)

for path in EPG_REPO.glob("sites/**/*.channels.xml"):
    try:
        root = ET.parse(path).getroot()
    except Exception:
        continue
    for ch in root.findall("channel"):
        xid = (ch.get("xmltv_id") or "").strip()
        if xid in wanted:
            # Copy only required attributes/text.
            found[xid].append({
                "site": (ch.get("site") or "").strip(),
                "lang": (ch.get("lang") or "en").strip(),
                "xmltv_id": xid,
                "site_id": (ch.get("site_id") or "").strip(),
                "name": (ch.text or xid).strip(),
                "source_path": str(path),
            })

# Choose up to two mappings per channel, favoring non-epgshare sources because
# our Python builder already consumes EPGShare directly.
root = ET.Element("channels")
count = 0
mapped_ids = 0

for xid in sorted(found):
    choices = found[xid]
    choices.sort(key=lambda x: ("epgshare01.online" in x["site"], x["site"], x["site_id"]))
    used_sites = set()
    kept = 0
    for item in choices:
        if not item["site"] or not item["site_id"]:
            continue
        if item["site"] in used_sites:
            continue
        used_sites.add(item["site"])

        el = ET.SubElement(root, "channel", {
            "site": item["site"],
            "lang": item["lang"],
            "xmltv_id": item["xmltv_id"],
            "site_id": item["site_id"],
        })
        el.text = item["name"]
        count += 1
        kept += 1
        if kept >= 2:
            break
    if kept:
        mapped_ids += 1

ET.ElementTree(root).write(OUT, encoding="utf-8", xml_declaration=True)

print(f"Wanted high-value IDs: {len(wanted)}")
print(f"IDs with official iptv-org EPG mappings: {mapped_ids}")
print(f"Target channel records written: {count}")
print(f"Output: {OUT}")
