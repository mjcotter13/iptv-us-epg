#!/usr/bin/env python3
"""
Build a custom XMLTV guide whose channel IDs exactly match the IPTV-org US playlist.

Sources:
  Playlist: https://iptv-org.github.io/iptv/countries/us.m3u
  EPG:
    https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz
    https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz

Outputs:
  public/guide.xml.gz
  public/match_report.csv
  public/unmatched_channels.csv
"""

from __future__ import annotations
import csv
import gzip
import io
import re
import shutil
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

PLAYLIST_URL = "https://iptv-org.github.io/iptv/countries/us.m3u"
EPG_URLS = [
    ("EPGShare US2", "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz"),
    ("EPGShare US Locals", "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz"),
]

OUTDIR = Path("public")
OUTDIR.mkdir(exist_ok=True)

UA = "Mozilla/5.0 Custom-IPTV-EPG-Builder/1.0"

ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()

def normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    replacements = {
        "&": " and ",
        "+": " plus ",
        " hd": " ",
        " fhd": " ",
        " uhd": " ",
        " 4k": " ",
        " east": " ",
        " west": " ",
        " feed": " ",
        " network": " ",
        " channel": " ",
        " television": " tv ",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    s = re.sub(r"\b(us|usa|united states)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

def id_base(s: str) -> str:
    # IPTV-org IDs commonly look like "ABCNewsLive.us"
    s = (s or "").rsplit(".", 1)[0]
    return normalize(s)

def parse_m3u(data: bytes):
    text = data.decode("utf-8", errors="replace")
    lines = [x.strip() for x in text.splitlines()]
    rows = []
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        attrs = dict(ATTR_RE.findall(line))
        display = line.split(",", 1)[1].strip() if "," in line else ""
        tvg_id = attrs.get("tvg-id", "").strip()
        if not tvg_id:
            continue
        rows.append({
            "id": tvg_id,
            "name": display,
            "tvg_name": attrs.get("tvg-name", "").strip(),
            "group": attrs.get("group-title", "").strip(),
        })
    # de-dupe by tvg-id, preserving first playlist appearance
    seen = set()
    out = []
    for row in rows:
        if row["id"] not in seen:
            seen.add(row["id"])
            out.append(row)
    return out

def read_xml_gz(data: bytes):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
        return ET.parse(gz).getroot()

def channel_names(ch):
    names = []
    for el in ch.findall("display-name"):
        if el.text and el.text.strip():
            names.append(el.text.strip())
    return names

def clone_element(el):
    return ET.fromstring(ET.tostring(el, encoding="utf-8"))

def candidate_keys(row):
    vals = [row["name"], row["tvg_name"], row["id"]]
    keys = {normalize(v) for v in vals if v}
    keys.add(id_base(row["id"]))
    return {k for k in keys if k}

print("Downloading IPTV-org US playlist...", flush=True)
playlist = parse_m3u(fetch(PLAYLIST_URL))
print(f"Playlist has {len(playlist)} unique tvg-id values.", flush=True)

# Load EPG sources into a compact index.
sources = {}
name_index = defaultdict(list)
id_index = defaultdict(list)

for source_name, url in EPG_URLS:
    print(f"Downloading {source_name}...", flush=True)
    root = read_xml_gz(fetch(url))

    channel_meta = {}
    programs = defaultdict(list)

    for ch in root.findall("channel"):
        sid = ch.get("id", "").strip()
        if not sid:
            continue
        names = channel_names(ch)
        channel_meta[sid] = {"element": ch, "names": names}
        id_index[sid].append((source_name, sid))
        id_index[sid.lower()].append((source_name, sid))
        for n in names:
            k = normalize(n)
            if k:
                name_index[k].append((source_name, sid))

    for p in root.findall("programme"):
        sid = p.get("channel", "").strip()
        if sid:
            programs[sid].append(p)

    sources[source_name] = {
        "channels": channel_meta,
        "programs": programs,
    }
    print(f"  {len(channel_meta)} channels, {sum(len(v) for v in programs.values())} programmes.", flush=True)

def score_candidate(row, source_name, sid):
    meta = sources[source_name]["channels"].get(sid)
    if not meta:
        return -1, ""
    keys = candidate_keys(row)
    sid_norm = normalize(sid)
    sid_base = id_base(sid)
    name_norms = {normalize(x) for x in meta["names"] if x}

    # Exact XMLTV ID match — strongest and safest.
    if sid == row["id"]:
        return 100, "exact-id"
    if sid.lower() == row["id"].lower():
        return 99, "case-insensitive-id"

    # Exact normalized source display-name against playlist display/tvg-name/id base.
    if keys & name_norms:
        return 95, "exact-normalized-name"

    # Source XMLTV id base vs IPTV-org id base.
    if sid_base and sid_base == id_base(row["id"]):
        return 94, "exact-id-base"

    # Conservative containment for sufficiently long, distinctive names.
    best = 0
    why = ""
    for pk in keys:
        if len(pk) < 7:
            continue
        if sid_norm and (pk in sid_norm or sid_norm in pk):
            ratio = min(len(pk), len(sid_norm)) / max(len(pk), len(sid_norm))
            val = 75 + int(ratio * 10)
            if val > best:
                best, why = val, "normalized-containment"
        for sn in name_norms:
            if len(sn) >= 7 and (pk in sn or sn in pk):
                ratio = min(len(pk), len(sn)) / max(len(pk), len(sn))
                val = 78 + int(ratio * 10)
                if val > best:
                    best, why = val, "name-containment"
    return best, why

matches = []
unmatched = []

for row in playlist:
    candidates = set()

    # Direct id candidates.
    for key in (row["id"], row["id"].lower()):
        candidates.update(id_index.get(key, []))

    # Exact normalized-name candidates.
    for key in candidate_keys(row):
        candidates.update(name_index.get(key, []))

    # If no direct candidate, scan IDs/display names only by exact id-base key.
    if not candidates:
        ib = id_base(row["id"])
        if ib:
            for source_name, src in sources.items():
                for sid in src["channels"]:
                    if id_base(sid) == ib:
                        candidates.add((source_name, sid))

    ranked = []
    for source_name, sid in candidates:
        sc, why = score_candidate(row, source_name, sid)
        if sc > 0:
            prog_count = len(sources[source_name]["programs"].get(sid, []))
            ranked.append((sc, prog_count, source_name, sid, why))

    ranked.sort(reverse=True)

    if ranked and ranked[0][0] >= 88 and ranked[0][1] > 0:
        sc, prog_count, source_name, sid, why = ranked[0]
        # Avoid ambiguous fuzzy ties.
        if len(ranked) > 1 and ranked[1][0] == sc and ranked[1][2:] != ranked[0][2:] and sc < 95:
            unmatched.append({**row, "reason": "ambiguous"})
        else:
            matches.append({
                **row,
                "source": source_name,
                "source_id": sid,
                "method": why,
                "score": sc,
                "programmes": prog_count,
            })
    else:
        unmatched.append({**row, "reason": "no-safe-match"})

print(f"Matched {len(matches)} of {len(playlist)} playlist channel IDs.", flush=True)

# Build final XMLTV with IPTV-org IDs.
tv = ET.Element("tv", {
    "generator-info-name": "Custom IPTV-org US EPG Builder",
    "generator-info-url": "https://github.com/iptv-org/iptv",
})

for m in matches:
    ch = ET.SubElement(tv, "channel", {"id": m["id"]})
    dn = ET.SubElement(ch, "display-name")
    dn.text = m["name"] or m["id"]
    # Preserve icons/URLs from source channel where useful.
    src_ch = sources[m["source"]]["channels"][m["source_id"]]["element"]
    for tag in ("icon", "url"):
        for child in src_ch.findall(tag):
            ch.append(clone_element(child))

for m in matches:
    for p in sources[m["source"]]["programs"].get(m["source_id"], []):
        cp = clone_element(p)
        cp.set("channel", m["id"])
        tv.append(cp)

xml_bytes = ET.tostring(tv, encoding="utf-8", xml_declaration=True)
with gzip.open(OUTDIR / "guide.xml.gz", "wb", compresslevel=9) as gz:
    gz.write(xml_bytes)

with open(OUTDIR / "match_report.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=[
        "id","name","tvg_name","group","source","source_id","method","score","programmes"
    ])
    w.writeheader()
    w.writerows(matches)

with open(OUTDIR / "unmatched_channels.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["id","name","tvg_name","group","reason"])
    w.writeheader()
    w.writerows(unmatched)

with open(OUTDIR / "status.txt", "w", encoding="utf-8") as f:
    f.write(f"playlist_channels={len(playlist)}\n")
    f.write(f"matched_channels={len(matches)}\n")
    f.write(f"unmatched_channels={len(unmatched)}\n")

print(f"Wrote {OUTDIR/'guide.xml.gz'} ({len(xml_bytes):,} XML bytes before gzip).", flush=True)
