#!/usr/bin/env python3
"""
Custom IPTV-org US EPG Builder — Version 5.0

Goal:
  Build one XMLTV guide whose channel IDs exactly match the tvg-id values in
  IPTV-org's US playlist.

Primary source:
  IPTV-EPG.org US XMLTV feed (large multi-source US guide)

Fallback sources:
  EPGShare US2
  EPGShare US Locals

Outputs:
  public/guide.xml.gz
  public/match_report.csv
  public/unmatched_channels.csv
  public/status.txt
"""

from __future__ import annotations

import csv
import gzip
import io
import re
import tempfile
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

PLAYLIST_URL = "https://iptv-org.github.io/iptv/countries/us.m3u"

PRIMARY_EPG_URL = "https://iptv-epg.org/files/epg-us.xml.gz"

FALLBACK_EPG_URLS = [
    ("EPGShare US2", "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz"),
    ("EPGShare US Locals", "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz"),
    ("EPGShare US Sports", "https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz"),
    ("EPGShare Plex", "https://epgshare01.online/epgshare01/epg_ripper_PLEX1.xml.gz"),
    ("EPGShare Peacock", "https://epgshare01.online/epgshare01/epg_ripper_PEACOCK1.xml.gz"),
    ("EPGShare DistroTV", "https://epgshare01.online/epgshare01/epg_ripper_DISTROTV1.xml.gz"),
    ("EPGShare FanDuel", "https://epgshare01.online/epgshare01/epg_ripper_FANDUEL1.xml.gz"),
    ("EPGShare TBN+", "https://epgshare01.online/epgshare01/epg_ripper_TBNPLUS1.xml.gz"),

    # Version 5: actively generated FAST-platform guides.
    ("Pluto TV US", "https://i.mjh.nz/PlutoTV/us.xml.gz"),
    ("Samsung TV Plus US", "https://i.mjh.nz/SamsungTVPlus/us.xml.gz"),
]

OUTDIR = Path("public")
OUTDIR.mkdir(exist_ok=True)

UA = "Mozilla/5.0 Custom-IPTV-EPG-Builder/5.0"
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')

# Curated aliases for high-value channels whose playlist branding differs from EPG branding.
# Values are alternate normalized/display names to test; matches remain ambiguity-checked.
CHANNEL_ALIASES = {
    "ESPNU.us": ["ESPNU"],
    "ESPNDeportes.us": ["ESPN Deportes"],
    "NFLNetwork.us": ["NFL Network"],
    "TennisChannel.us": ["Tennis Channel"],
    "NBCSportsNOW.us": ["NBC Sports NOW", "NBC Sports Now"],
    "USANetwork.us": ["USA Network", "USA"],
    "E.us": ["E!", "E Entertainment"],
    "MTV.us": ["MTV"],
    "MTV2.us": ["MTV2"],
    "Oxygen.us": ["Oxygen"],
    "NBCUniverso.us": ["NBC Universo", "Universo"],
    "CheddarNews.us": ["Cheddar News"],
    "EntertainmentTonight.us": ["Entertainment Tonight"],
    "ABCNewsLive10.us": ["ABC News Live"],
    "CBSNewsPhilly.us": ["CBS News Philadelphia"],
    "TheFirstTV.us": ["The First", "The First TV"],
    "TheYoungTurks.us": ["The Young Turks"],
    "ColdCaseFiles.us": ["Cold Case Files"],
    "CSI.us": ["CSI"],
    "StarTrek.us": ["Star Trek"],
    "Survivor.us": ["Survivor"],
    "ThreesCompany.us": ["Three's Company", "Threes Company"],
    "WildNOut.us": ["Wild 'N Out", "Wild N Out"],
    "BattlestarGalactica.us": ["Battlestar Galactica"],
    "Cinevault80s.us": ["Cinevault 80s", "CineVault 80s"],
    "Runtime.us": ["Runtime"],
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()

    replacements = {
        "&": " and ",
        "+": " plus ",
        " television ": " tv ",
        " network ": " ",
        " channel ": " ",
        " hd ": " ",
        " fhd ": " ",
        " uhd ": " ",
        " 4k ": " ",
        " east ": " ",
        " west ": " ",
        " feed ": " ",
    }

    s = f" {s} "
    for a, b in replacements.items():
        s = s.replace(a, b)

    # Remove common playlist decorations that should not affect guide matching.
    s = re.sub(r"\((?:[^)]*?(?:360p|480p|540p|576p|720p|1080p|1440p|2160p|4k|uhd|fhd|hd|sd)[^)]*?)\)", " ", s)
    s = re.sub(r"\b(?:360p|480p|540p|576p|720p|1080p|1440p|2160p|4k|uhd|fhd|hd|sd)\b", " ", s)
    s = re.sub(r"\b(?:us|usa|united states)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def id_base(s: str) -> str:
    if not s:
        return ""
    return normalize(s.rsplit(".", 1)[0])


def parse_m3u(data: bytes):
    text = data.decode("utf-8", errors="replace")
    lines = [x.strip() for x in text.splitlines()]
    rows = []

    for line in lines:
        if not line.startswith("#EXTINF:"):
            continue

        attrs = dict(ATTR_RE.findall(line))
        display = line.split(",", 1)[1].strip() if "," in line else ""
        tvg_id = attrs.get("tvg-id", "").strip()
        if not tvg_id:
            continue

        rows.append(
            {
                "id": tvg_id,
                "name": display,
                "tvg_name": attrs.get("tvg-name", "").strip(),
                "group": attrs.get("group-title", "").strip(),
            }
        )

    seen = set()
    out = []
    for row in rows:
        if row["id"] not in seen:
            seen.add(row["id"])
            out.append(row)

    return out


def clone(el):
    return ET.fromstring(ET.tostring(el, encoding="utf-8"))


def channel_display_names(ch):
    out = []
    for el in ch.findall("display-name"):
        if el.text and el.text.strip():
            out.append(el.text.strip())
    return out


def playlist_keys(row):
    base_id = re.sub(r"@.*$", "", row["id"])
    vals = [
        row["name"],
        row["tvg_name"],
        row["id"],
        row["id"].rsplit(".", 1)[0],
        base_id,
        base_id.rsplit(".", 1)[0],
    ]

    # Version 4 curated alternate branding.
    vals.extend(CHANNEL_ALIASES.get(base_id, []))

    return {normalize(v) for v in vals if normalize(v)}


def load_small_epg(source_name: str, url: str):
    if url.startswith("file://"):
        path = Path(url[7:])
        raw = path.read_bytes()
    else:
        raw = fetch(url)

    if url.endswith(".gz"):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
            root = ET.parse(gz).getroot()
    else:
        root = ET.fromstring(raw)

    channels = {}
    programmes = defaultdict(list)

    for ch in root.findall("channel"):
        sid = (ch.get("id") or "").strip()
        if sid:
            channels[sid] = {
                "element": ch,
                "names": channel_display_names(ch),
            }

    for p in root.findall("programme"):
        sid = (p.get("channel") or "").strip()
        if sid:
            programmes[sid].append(p)

    return {
        "name": source_name,
        "channels": channels,
        "programmes": programmes,
    }


def build_primary_indexes(gz_path: Path):
    """
    First pass through the large primary guide:
      - capture all channel metadata
      - build exact-id and normalized-name indexes

    We do NOT keep all programmes in memory.
    """
    channels = {}
    exact_id = {}
    name_index = defaultdict(list)

    with gzip.open(gz_path, "rb") as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            if elem.tag != "channel":
                continue

            sid = (elem.get("id") or "").strip()
            if sid:
                names = channel_display_names(elem)
                channels[sid] = {
                    "xml": ET.tostring(elem, encoding="utf-8"),
                    "names": names,
                }
                exact_id[sid] = sid
                exact_id[sid.lower()] = sid

                for n in names:
                    k = normalize(n)
                    if k:
                        name_index[k].append(sid)

                ib = id_base(sid)
                if ib:
                    name_index[ib].append(sid)

            elem.clear()

    return channels, exact_id, name_index


def choose_primary_match(row, channels, exact_id, name_index):
    # 1) Exact XMLTV ID == IPTV-org tvg-id.
    sid = exact_id.get(row["id"])
    if sid:
        return sid, 100, "primary-exact-id"

    sid = exact_id.get(row["id"].lower())
    if sid:
        return sid, 99, "primary-case-insensitive-id"

    # 2) Exact normalized display-name / ID-base match.
    candidates = set()
    for key in playlist_keys(row):
        candidates.update(name_index.get(key, []))

    ranked = []
    row_keys = playlist_keys(row)
    row_id_base = id_base(row["id"])

    for sid in candidates:
        meta = channels.get(sid)
        if not meta:
            continue

        source_names = {normalize(x) for x in meta["names"] if normalize(x)}
        source_id_base = id_base(sid)

        if row_keys & source_names:
            ranked.append((95, sid, "primary-exact-normalized-name"))
        elif row_id_base and source_id_base == row_id_base:
            ranked.append((94, sid, "primary-exact-id-base"))

    ranked.sort(reverse=True)

    if not ranked:
        return None

    # Refuse ambiguous equal-score name matches.
    top_score = ranked[0][0]
    top = [r for r in ranked if r[0] == top_score]
    if len(top) != 1:
        return None

    score, sid, method = top[0]
    return sid, score, method



def safe_fuzzy_score(a: str, b: str) -> int:
    """
    Conservative fuzzy score for long channel names only.
    Returns 0 unless the strings are distinctive enough to compare safely.
    """
    from difflib import SequenceMatcher

    if not a or not b:
        return 0
    if min(len(a), len(b)) < 8:
        return 0

    ratio = SequenceMatcher(None, a, b).ratio()

    # Very high threshold: fuzzy matching is only a last resort.
    if ratio >= 0.94:
        return 90
    if ratio >= 0.91 and min(len(a), len(b)) >= 12:
        return 89
    return 0


def feed_stem(s: str) -> str:
    """
    Turn IPTV-org feed IDs such as:
      ESPNDeportes.us@SD -> espndeportes
      NationalGeographic.us@HDEast -> nationalgeographic
    into a comparable network/station stem.
    """
    if not s:
        return ""
    s = re.sub(r"@.*$", "", s)
    s = re.sub(r"\.[A-Za-z]{2,3}$", "", s)
    return normalize(s)


def choose_fallback_match(row, fallback_sources):
    row_keys = playlist_keys(row)
    row_id_base = id_base(row["id"])
    row_feed_stem = feed_stem(row["id"])

    ranked = []

    for src in fallback_sources:
        for sid, meta in src["channels"].items():
            prog_count = len(src["programmes"].get(sid, []))
            if prog_count == 0:
                continue

            if sid == row["id"]:
                ranked.append((100, prog_count, src["name"], sid, "fallback-exact-id"))
                continue

            if sid.lower() == row["id"].lower():
                ranked.append((99, prog_count, src["name"], sid, "fallback-case-insensitive-id"))
                continue

            source_names = {normalize(x) for x in meta["names"] if normalize(x)}
            source_feed_stem = feed_stem(sid)

            if row_keys & source_names:
                ranked.append((95, prog_count, src["name"], sid, "fallback-exact-normalized-name"))
                continue

            if row_id_base and id_base(sid) == row_id_base:
                ranked.append((94, prog_count, src["name"], sid, "fallback-exact-id-base"))
                continue

            # Version 3: feed-aware stem matching.  This safely connects
            # @East/@West/@HD/@SD variants to a guide ID for the base channel.
            if row_feed_stem and source_feed_stem and row_feed_stem == source_feed_stem:
                ranked.append((93, prog_count, src["name"], sid, "fallback-feed-stem"))
                continue

            # Version 3: extremely conservative fuzzy name fallback.
            best_fuzzy = 0
            for rk in row_keys:
                for sn in source_names:
                    best_fuzzy = max(best_fuzzy, safe_fuzzy_score(rk, sn))
            if best_fuzzy:
                ranked.append((best_fuzzy, prog_count, src["name"], sid, "fallback-safe-fuzzy"))

    ranked.sort(reverse=True)

    if not ranked:
        return None

    top_score = ranked[0][0]
    tied = [r for r in ranked if r[0] == top_score]

    # Never accept an ambiguous fuzzy/feed/name match.
    if len(tied) > 1 and top_score < 99:
        # If all tied records point to the exact same source ID, it is harmless.
        tied_ids = {(r[2], r[3]) for r in tied}
        if len(tied_ids) > 1:
            return None

    # For fuzzy matches, require a meaningful gap over the runner-up.
    if top_score <= 90 and len(ranked) > 1:
        if ranked[1][0] >= top_score - 2:
            return None

    score, prog_count, source_name, sid, method = ranked[0]
    return source_name, sid, score, method, prog_count


print("Downloading IPTV-org US playlist...", flush=True)
playlist = parse_m3u(fetch(PLAYLIST_URL))
print(f"Playlist has {len(playlist)} unique tvg-id values.", flush=True)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    primary_path = tmp / "primary.xml.gz"

    print("Downloading primary US guide from IPTV-EPG.org...", flush=True)
    download(PRIMARY_EPG_URL, primary_path)

    print("Indexing primary guide channels...", flush=True)
    primary_channels, primary_exact_id, primary_name_index = build_primary_indexes(primary_path)
    print(f"Primary guide contains {len(primary_channels)} channel IDs.", flush=True)

    primary_matches = {}
    unresolved = []

    for row in playlist:
        match = choose_primary_match(
            row,
            primary_channels,
            primary_exact_id,
            primary_name_index,
        )

        if match:
            sid, score, method = match
            primary_matches[row["id"]] = {
                **row,
                "source": "IPTV-EPG.org US",
                "source_id": sid,
                "method": method,
                "score": score,
                "programmes": 0,
            }
        else:
            unresolved.append(row)

    print(
        f"Primary metadata matched {len(primary_matches)} of "
        f"{len(playlist)} channel IDs.",
        flush=True,
    )

    print("Loading fallback guides...", flush=True)
    fallback_sources = []

    # Version 5: targeted guide generated by the official iptv-org/epg grabber.
    targeted = Path("iptvorg_targeted.xml")
    if targeted.exists() and targeted.stat().st_size > 100:
        print("  IPTV-org targeted grab", flush=True)
        try:
            fallback_sources.append(
                load_small_epg("IPTV-org targeted grab", f"file://{targeted.resolve()}")
            )
        except Exception as exc:
            print(f"  WARNING: could not load targeted guide: {exc}", flush=True)

    for source_name, url in FALLBACK_EPG_URLS:
        print(f"  {source_name}", flush=True)
        try:
            fallback_sources.append(load_small_epg(source_name, url))
        except Exception as exc:
            # One flaky external feed should never break the whole daily guide.
            print(f"  WARNING: skipped {source_name}: {exc}", flush=True)

    fallback_matches = {}
    still_unmatched = []

    for row in unresolved:
        match = choose_fallback_match(row, fallback_sources)
        if match:
            source_name, sid, score, method, prog_count = match
            fallback_matches[row["id"]] = {
                **row,
                "source": source_name,
                "source_id": sid,
                "method": method,
                "score": score,
                "programmes": prog_count,
            }
        else:
            still_unmatched.append({**row, "reason": "no-safe-match"})

    print(f"Fallback added {len(fallback_matches)} matches.", flush=True)

    all_matches = {}
    all_matches.update(primary_matches)
    all_matches.update(fallback_matches)

    # Build output XML.
    tv = ET.Element(
        "tv",
        {
            "generator-info-name": "Custom IPTV-org US EPG Builder v5.0",
            "generator-info-url": "https://github.com/iptv-org/iptv",
        },
    )

    # Channels first, in playlist order.
    for row in playlist:
        m = all_matches.get(row["id"])
        if not m:
            continue

        out_ch = ET.SubElement(tv, "channel", {"id": row["id"]})
        dn = ET.SubElement(out_ch, "display-name")
        dn.text = row["name"] or row["id"]

        if m["source"] == "IPTV-EPG.org US":
            src_xml = primary_channels[m["source_id"]]["xml"]
            src_ch = ET.fromstring(src_xml)
        else:
            src = next(s for s in fallback_sources if s["name"] == m["source"])
            src_ch = src["channels"][m["source_id"]]["element"]

        for tag in ("icon", "url"):
            for child in src_ch.findall(tag):
                out_ch.append(clone(child))

    # Primary programmes: streaming second pass to avoid holding huge guide in RAM.
    wanted_primary = {
        m["source_id"]: playlist_id
        for playlist_id, m in primary_matches.items()
    }

    primary_program_count = defaultdict(int)

    print("Extracting programmes from primary guide...", flush=True)
    with gzip.open(primary_path, "rb") as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            if elem.tag != "programme":
                continue

            source_id = (elem.get("channel") or "").strip()
            playlist_id = wanted_primary.get(source_id)

            if playlist_id:
                cp = clone(elem)
                cp.set("channel", playlist_id)
                tv.append(cp)
                primary_program_count[playlist_id] += 1

            elem.clear()

    # Drop primary matches that had no actual programme data.
    dead_primary_ids = {
        pid for pid in primary_matches if primary_program_count.get(pid, 0) == 0
    }

    if dead_primary_ids:
        print(
            f"{len(dead_primary_ids)} primary channel matches had zero programmes; "
            "they will be removed from the final guide.",
            flush=True,
        )

        # Rebuild TV root without dead channels/programmes.
        new_tv = ET.Element(
            "tv",
            {
                "generator-info-name": "Custom IPTV-org US EPG Builder v5.0",
                "generator-info-url": "https://github.com/iptv-org/iptv",
            },
        )

        for child in list(tv):
            if child.tag == "channel":
                if child.get("id") not in dead_primary_ids:
                    new_tv.append(child)
            elif child.tag == "programme":
                if child.get("channel") not in dead_primary_ids:
                    new_tv.append(child)

        tv = new_tv

        for pid in dead_primary_ids:
            row = primary_matches.pop(pid)
            all_matches.pop(pid, None)
            still_unmatched.append({
                "id": row["id"],
                "name": row["name"],
                "tvg_name": row["tvg_name"],
                "group": row["group"],
                "reason": "matched-but-zero-programmes",
            })

    for pid, count in primary_program_count.items():
        if pid in primary_matches:
            primary_matches[pid]["programmes"] = count
            all_matches[pid]["programmes"] = count

    # Fallback programmes.
    for playlist_id, m in fallback_matches.items():
        src = next(s for s in fallback_sources if s["name"] == m["source"])
        for p in src["programmes"].get(m["source_id"], []):
            cp = clone(p)
            cp.set("channel", playlist_id)
            tv.append(cp)

    # Final reports.
    final_matches = [
        all_matches[row["id"]]
        for row in playlist
        if row["id"] in all_matches
    ]

    unmatched_by_id = {row["id"]: row for row in still_unmatched}
    final_unmatched = [
        unmatched_by_id[row["id"]]
        for row in playlist
        if row["id"] in unmatched_by_id
    ]

    xml_bytes = ET.tostring(tv, encoding="utf-8", xml_declaration=True)

    with gzip.open(OUTDIR / "guide.xml.gz", "wb", compresslevel=9) as gz:
        gz.write(xml_bytes)

    with open(OUTDIR / "match_report.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "name",
                "tvg_name",
                "group",
                "source",
                "source_id",
                "method",
                "score",
                "programmes",
            ],
        )
        w.writeheader()
        w.writerows(final_matches)

    with open(OUTDIR / "unmatched_channels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["id", "name", "tvg_name", "group", "reason"],
        )
        w.writeheader()
        w.writerows(final_unmatched)

    # Version 4: focused report of remaining channels where EPG coverage is most useful.
    high_value_categories = {
        "News", "Sports", "Entertainment", "Movies", "Series",
        "Kids", "Documentary", "Comedy", "Animation"
    }
    high_value_unmatched = [
        row for row in final_unmatched
        if any(part.strip() in high_value_categories for part in (row["group"] or "").split(";"))
    ]

    with open(OUTDIR / "high_value_unmatched.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["id", "name", "tvg_name", "group", "reason"],
        )
        w.writeheader()
        w.writerows(high_value_unmatched)

    method_counts = defaultdict(int)
    for m in final_matches:
        method_counts[m["method"]] += 1

    with open(OUTDIR / "match_methods.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["method", "matched_channels"])
        w.writeheader()
        for method, count in sorted(method_counts.items(), key=lambda x: (-x[1], x[0])):
            w.writerow({"method": method, "matched_channels": count})

    # Category-level coverage report.
    category_totals = defaultdict(int)
    category_matches = defaultdict(int)

    matched_ids = {m["id"] for m in final_matches}
    for row in playlist:
        category = row["group"] or "Undefined"
        category_totals[category] += 1
        if row["id"] in matched_ids:
            category_matches[category] += 1

    with open(OUTDIR / "category_status.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["category", "playlist_channels", "matched_channels", "unmatched_channels", "match_pct"],
        )
        w.writeheader()
        for category in sorted(category_totals):
            total = category_totals[category]
            matched = category_matches[category]
            w.writerow({
                "category": category,
                "playlist_channels": total,
                "matched_channels": matched,
                "unmatched_channels": total - matched,
                "match_pct": round((matched / total) * 100, 1) if total else 0,
            })

    with open(OUTDIR / "status.txt", "w", encoding="utf-8") as f:
        f.write(f"playlist_channels={len(playlist)}\n")
        f.write(f"matched_channels={len(final_matches)}\n")
        f.write(f"unmatched_channels={len(final_unmatched)}\n")
        f.write(f"primary_matches={len(primary_matches)}\n")
        f.write(f"fallback_matches={len(fallback_matches)}\n")
        f.write(f"high_value_unmatched={len(high_value_unmatched)}\n")
        targeted_count = sum(
            1 for m in final_matches if m["source"] == "IPTV-org targeted grab"
        )
        pluto_count = sum(1 for m in final_matches if m["source"] == "Pluto TV US")
        samsung_count = sum(1 for m in final_matches if m["source"] == "Samsung TV Plus US")
        f.write(f"targeted_iptvorg_matches={targeted_count}\n")
        f.write(f"pluto_matches={pluto_count}\n")
        f.write(f"samsung_matches={samsung_count}\n")

    print(f"FINAL: matched {len(final_matches)} of {len(playlist)}.", flush=True)
    print(f"Wrote {OUTDIR / 'guide.xml.gz'}", flush=True)
