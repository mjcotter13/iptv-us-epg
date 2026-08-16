#!/usr/bin/env python3
from pathlib import Path
import csv
import xml.etree.ElementTree as ET

WORK = Path("v7_work")
OUT = Path("v7_targeted_guide.xml")
REPORT = Path("v7_targeted_status.csv")
ATTEMPT_REPORT = Path("v7_attempt_status.csv")

channels = list(csv.DictReader((WORK / "channels.csv").open(encoding="utf-8")))
runtime_file = WORK / "attempt_status_runtime.csv"
runtime = list(csv.DictReader(runtime_file.open(encoding="utf-8"))) if runtime_file.exists() else []

# Preserve detailed runtime diagnostics.
with ATTEMPT_REPORT.open("w", newline="", encoding="utf-8") as f:
    if runtime:
        fields = list(runtime[0].keys())
    else:
        fields = [
            "id","name","group","attempt","site","site_id","xmltv_id",
            "channel_file","guide_file","source_file",
            "programmes","success","timed_out","return_code"
        ]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(runtime)

tv = ET.Element("tv", {"generator-info-name": "IPTV-org targeted V7.2"})
seen_channels = set()
final_rows = []

for ch in channels:
    cid = ch["id"]

    successes = [
        r for r in runtime
        if r["id"] == cid and r.get("success") == "YES"
    ]
    successes.sort(key=lambda r: int(r["attempt"]))

    if not successes:
        final_rows.append({
            "id": cid,
            "name": ch["name"],
            "group": ch["group"],
            "site": "",
            "site_id": "",
            "attempt_used": "",
            "programmes": 0,
            "success": "NO",
        })
        continue

    best = successes[0]
    guide = WORK / best["guide_file"]

    try:
        root = ET.parse(guide).getroot()
    except Exception:
        final_rows.append({
            "id": cid,
            "name": ch["name"],
            "group": ch["group"],
            "site": "",
            "site_id": "",
            "attempt_used": "",
            "programmes": 0,
            "success": "NO",
        })
        continue

    for channel_el in root.findall("channel"):
        source_id = (channel_el.get("id") or "").strip()
        if source_id == cid and cid not in seen_channels:
            tv.append(channel_el)
            seen_channels.add(cid)

    prog_count = 0
    for p in root.findall("programme"):
        source_id = (p.get("channel") or "").strip()
        if source_id == cid:
            tv.append(p)
            prog_count += 1

    final_rows.append({
        "id": cid,
        "name": ch["name"],
        "group": ch["group"],
        "site": best["site"],
        "site_id": best["site_id"],
        "attempt_used": best["attempt"],
        "programmes": prog_count,
        "success": "YES",
    })

ET.ElementTree(tv).write(
    OUT,
    encoding="utf-8",
    xml_declaration=True,
)

with REPORT.open("w", newline="", encoding="utf-8") as f:
    fields = [
        "id","name","group","site","site_id",
        "attempt_used","programmes","success"
    ]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(final_rows)

working = sum(1 for r in final_rows if r["success"] == "YES")
print(f"V7.2 targeted success: {working}/{len(final_rows)}")
