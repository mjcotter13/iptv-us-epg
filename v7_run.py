#!/usr/bin/env python3
from pathlib import Path
import csv
import os
import subprocess
import xml.etree.ElementTree as ET
import time

WORK = Path("v7_work")
CHANNELS = list(csv.DictReader((WORK / "channels.csv").open(encoding="utf-8")))
ATTEMPTS = list(csv.DictReader((WORK / "attempts.csv").open(encoding="utf-8")))

ATTEMPT_TIMEOUT_SECONDS = 120
GLOBAL_BUDGET_SECONDS = 48 * 60  # leave time for merge/build/commit in a 60-min workflow
started = time.monotonic()

attempt_status = []

def programme_count(path: Path, channel_id: str) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return 0
    return sum(
        1 for p in root.findall("programme")
        if (p.get("channel") or "").strip() == channel_id
    )

attempts_by_id = {}
for a in ATTEMPTS:
    attempts_by_id.setdefault(a["id"], []).append(a)

for ch in CHANNELS:
    cid = ch["id"]

    if time.monotonic() - started >= GLOBAL_BUDGET_SECONDS:
        print("GLOBAL TIME BUDGET REACHED; stopping targeted grabs.", flush=True)
        break

    choices = sorted(attempts_by_id.get(cid, []), key=lambda x: int(x["attempt"]))

    if not choices:
        print(f"===== {cid}: NO EXACT MAPPINGS =====", flush=True)
        continue

    success = False

    for a in choices:
        if time.monotonic() - started >= GLOBAL_BUDGET_SECONDS:
            print("GLOBAL TIME BUDGET REACHED; stopping targeted grabs.", flush=True)
            break

        attempt = a["attempt"]
        print(f"===== {cid} | attempt {attempt} | {a['site']} =====", flush=True)

        env = os.environ.copy()
        env["NODE_OPTIONS"] = "--max-old-space-size=2048"

        cmd = [
            "npm", "run", "grab", "---",
            f"--channels=../v7_work/{a['channel_file']}",
            f"--output=../v7_work/{a['guide_file']}",
            "--days=1",
            "--maxConnections=1",
            "--delay=750",
            "--timeout=25000",
        ]

        timed_out = False
        return_code = None

        try:
            result = subprocess.run(
                cmd,
                cwd="_iptv_epg",
                env=env,
                check=False,
                timeout=ATTEMPT_TIMEOUT_SECONDS,
            )
            return_code = result.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            print(f"WARNING: timeout on {cid} attempt {attempt}", flush=True)

        guide = WORK / a["guide_file"]
        count = programme_count(guide, cid)

        attempt_status.append({
            **a,
            "programmes": count,
            "success": "YES" if count > 0 else "NO",
            "timed_out": "YES" if timed_out else "NO",
            "return_code": "" if return_code is None else return_code,
        })

        if count > 0:
            print(f"SUCCESS: {cid} -> {count} programmes via {a['site']}", flush=True)
            success = True
            break

        print(f"No programmes from {a['site']}; trying next mapping.", flush=True)

    if not success:
        print(f"NO WORKING MAPPING FOUND: {cid}", flush=True)

with (WORK / "attempt_status_runtime.csv").open("w", newline="", encoding="utf-8") as f:
    fields = [
        "id","name","group","attempt","site","site_id","xmltv_id",
        "channel_file","guide_file","source_file",
        "programmes","success","timed_out","return_code"
    ]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(attempt_status)

print(f"Runtime attempts executed: {len(attempt_status)}")
print(f"Successful targeted channels: {len({r['id'] for r in attempt_status if r['success']=='YES'})}")
