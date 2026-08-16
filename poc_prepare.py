from pathlib import Path
import xml.etree.ElementTree as ET
from collections import defaultdict
import csv

EPG_REPO = Path("_iptv_epg")
OUT = Path("poc.channels.xml")
REPORT = Path("poc_mappings.csv")
TARGETS = ["ESPNU.us@SD","NFLNetwork.us@SD","TennisChannel.us@SD","MTV.us@East","USANetwork.us@East"]

found = defaultdict(list)
for path in EPG_REPO.glob("sites/**/*.channels.xml"):
    try:
        root = ET.parse(path).getroot()
    except Exception:
        continue
    for ch in root.findall("channel"):
        xid = (ch.get("xmltv_id") or "").strip()
        if xid in TARGETS:
            found[xid].append({
                "site": (ch.get("site") or "").strip(),
                "lang": (ch.get("lang") or "en").strip(),
                "xmltv_id": xid,
                "site_id": (ch.get("site_id") or "").strip(),
                "name": (ch.text or xid).strip(),
                "source_file": str(path),
            })

channels_root = ET.Element("channels")
report_rows = []
for xid in TARGETS:
    choices = found.get(xid, [])
    choices.sort(key=lambda x: ("epgshare01.online" in x["site"], x["site"], x["site_id"]))
    used_sites, kept = set(), 0
    for item in choices:
        if not item["site"] or not item["site_id"] or item["site"] in used_sites:
            continue
        used_sites.add(item["site"])
        el = ET.SubElement(channels_root, "channel", {
            "site": item["site"], "lang": item["lang"],
            "xmltv_id": item["xmltv_id"], "site_id": item["site_id"],
        })
        el.text = item["name"]
        report_rows.append(item)
        kept += 1
        if kept >= 2:
            break
    if kept == 0:
        report_rows.append({"site":"","lang":"","xmltv_id":xid,"site_id":"","name":"","source_file":"NO EXACT MAPPING FOUND"})

ET.ElementTree(channels_root).write(OUT, encoding="utf-8", xml_declaration=True)
with REPORT.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["xmltv_id","name","site","site_id","lang","source_file"])
    w.writeheader(); w.writerows(report_rows)

for xid in TARGETS:
    matches = [r for r in report_rows if r["xmltv_id"] == xid and r["site"]]
    print(f"{xid}: {len(matches)} mapping(s)")
    for m in matches:
        print(f"  {m['site']} -> {m['site_id']} ({m['name']})")
