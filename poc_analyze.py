from pathlib import Path
import xml.etree.ElementTree as ET
from collections import Counter
import csv

GUIDE = Path("poc_guide.xml")
STATUS = Path("poc_status.txt")
DETAIL = Path("poc_program_counts.csv")
TARGETS = ["ESPNU.us@SD","NFLNetwork.us@SD","TennisChannel.us@SD","MTV.us@East","USANetwork.us@East"]
counts = Counter()
parse_error = ""

if GUIDE.exists() and GUIDE.stat().st_size > 0:
    try:
        root = ET.parse(GUIDE).getroot()
        for p in root.findall("programme"):
            counts[(p.get("channel") or "").strip()] += 1
    except Exception as exc:
        parse_error = str(exc)
else:
    parse_error = "poc_guide.xml missing or empty"

with DETAIL.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["channel_id","programmes","success"])
    w.writeheader()
    for cid in TARGETS:
        w.writerow({"channel_id":cid,"programmes":counts.get(cid,0),"success":"YES" if counts.get(cid,0)>0 else "NO"})

working = sum(counts.get(cid,0)>0 for cid in TARGETS)
with STATUS.open("w", encoding="utf-8") as f:
    f.write(f"targets={len(TARGETS)}\nchannels_with_programmes={working}\nchannels_without_programmes={len(TARGETS)-working}\n")
    if parse_error: f.write(f"parse_error={parse_error}\n")
    for cid in TARGETS: f.write(f"{cid}={counts.get(cid,0)} programmes\n")
print(STATUS.read_text())
