#!/usr/bin/env python3
from pathlib import Path
import csv
import xml.etree.ElementTree as ET
from collections import Counter

WORK = Path("v7_work")
CHANNELS = WORK / "channels.csv"
ATTEMPTS = WORK / "attempts.csv"
OUT = Path("v7_targeted_guide.xml")
REPORT = Path("v7_targeted_status.csv")
ATTEMPT_REPORT = Path("v7_attempt_status.csv")

channels = list(csv.DictReader(CHANNELS.open(encoding="utf-8"))) if CHANNELS.exists() else []
attempts = list(csv.DictReader(ATTEMPTS.open(encoding="utf-8"))) if ATTEMPTS.exists() else []

# Analyze every attempt.
attempt_results = []
for a in attempts:
    guide = WORK / a["guide_file"]
    count = 0
    parsed = None
    if guide.exists() and guide.stat().st_size > 0:
        try:
            parsed = ET.parse(guide).getroot()
            for p in parsed.findall("programme"):
                if (p.get("channel") or "").strip() == a["id"]:
                    count += 1
        except Exception:
            parsed = None

    attempt_results.append({
        **a,
        "programmes": count,
        "success": "YES" if count > 0 else "NO",
    })

with ATTEMPT_REPORT.open("w", newline="", encoding="utf-8") as f:
    fields = ["id","name","group","attempt","site","site_id","programmes","success"]
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(attempt_results)

# Pick first successful attempt per channel.
tv = ET.Element("tv", {"generator-info-name": "IPTV-org targeted V7.1"})
seen_channels = set()
final_rows = []

for ch in channels:
    cid = ch["id"]
    successes = [
        r for r in attempt_results
        if r["id"] == cid and r["success"] == "YES"
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
    root = ET.parse(guide).getroot()

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

ET.ElementTree(tv).write(OUT, encoding="utf-8", xml_declaration=True)

with REPORT.open("w", newline="", encoding="utf-8") as f:
    fields = ["id","name","group","site","site_id","attempt_used","programmes","success"]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(final_rows)

working = sum(1 for r in final_rows if r["success"] == "YES")
print(f"V7.1 targeted: {working}/{len(final_rows)} channels returned programmes")
for r in final_rows:
    if r["success"] == "YES":
        print(f"{r['id']}: {r['programmes']} programmes via {r['site']} (attempt {r['attempt_used']})")
    else:
        print(f"{r['id']}: 0 programmes")
