#!/usr/bin/env python3
"""
Stability merge for the published IPTV EPG.

Policy:
- Fresh candidate data wins whenever it contains programmes for a channel.
- If today's candidate loses a channel, preserve still-relevant programmes from
  the previously published guide.
- Never invent listings.
- Expired old programmes are not retained merely to inflate the count.

This turns transient upstream failures into graceful degradation instead of
immediate channel loss.
"""

from __future__ import annotations

import argparse
import copy
import gzip
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET


def parse_xml(path: Path):
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as f:
            return ET.parse(f).getroot()
    return ET.parse(path).getroot()


def write_gz(root: ET.Element, path: Path):
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(data)


def parse_xmltv_time(value: str | None):
    if not value:
        return None
    # XMLTV usually: YYYYMMDDHHMMSS +0000
    raw = value.strip()
    for fmt in ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M %z", "%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def index(root: ET.Element):
    channels = {}
    programmes = {}
    for ch in root.findall("channel"):
        cid = (ch.get("id") or "").strip()
        if cid:
            channels[cid] = ch
    for p in root.findall("programme"):
        cid = (p.get("channel") or "").strip()
        if cid:
            programmes.setdefault(cid, []).append(p)
    return channels, programmes


def relevant(programme: ET.Element, now: datetime):
    stop = parse_xmltv_time(programme.get("stop"))
    start = parse_xmltv_time(programme.get("start"))
    if stop is not None:
        return stop >= now
    if start is not None:
        return start >= now
    # Unknown date format: retain rather than accidentally discard valid data.
    return True


def covered_ids(programmes, now):
    return {
        cid for cid, ps in programmes.items()
        if any(relevant(p, now) for p in ps)
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--previous", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--status", required=True)
    args = ap.parse_args()

    previous_path = Path(args.previous)
    candidate_path = Path(args.candidate)
    output_path = Path(args.output)
    status_path = Path(args.status)

    now = datetime.now(timezone.utc)

    candidate_root = parse_xml(candidate_path)
    candidate_channels, candidate_programmes = index(candidate_root)

    if previous_path.exists() and previous_path.stat().st_size > 0:
        previous_root = parse_xml(previous_path)
        previous_channels, previous_programmes = index(previous_root)
    else:
        previous_channels, previous_programmes = {}, {}

    candidate_covered = covered_ids(candidate_programmes, now)
    previous_covered = covered_ids(previous_programmes, now)

    # Start with all fresh candidate channels/programmes.
    out = ET.Element("tv", dict(candidate_root.attrib))
    out.set("generator-info-name", "Stable Custom IPTV-org US EPG")

    for cid, ch in candidate_channels.items():
        out.append(copy.deepcopy(ch))

    for cid, ps in candidate_programmes.items():
        for p in ps:
            out.append(copy.deepcopy(p))

    preserved = set()

    # Preserve a previous channel only when candidate currently has no relevant
    # programming and the previous guide still has relevant programming.
    for cid in sorted(previous_covered - candidate_covered):
        old_programmes = [p for p in previous_programmes.get(cid, []) if relevant(p, now)]
        if not old_programmes:
            continue

        if cid not in candidate_channels and cid in previous_channels:
            out.append(copy.deepcopy(previous_channels[cid]))

        for p in old_programmes:
            out.append(copy.deepcopy(p))

        preserved.add(cid)

    final_programmes = {}
    for p in out.findall("programme"):
        cid = (p.get("channel") or "").strip()
        if cid:
            final_programmes.setdefault(cid, []).append(p)

    final_covered = covered_ids(final_programmes, now)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_gz(out, output_path)

    status_path.write_text(
        "\n".join([
            f"generated_utc={now.isoformat()}",
            f"candidate_channels_with_current_or_future_programmes={len(candidate_covered)}",
            f"previous_channels_with_current_or_future_programmes={len(previous_covered)}",
            f"preserved_channels_from_previous={len(preserved)}",
            f"published_channels_with_current_or_future_programmes={len(final_covered)}",
            "known_good_baseline_commit=4c6d667",
            "known_good_baseline_historical_matches=694",
            "",
        ]),
        encoding="utf-8",
    )

    print(status_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
