#!/usr/bin/env python3
from pathlib import Path
import csv, re, unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from difflib import SequenceMatcher

EPG_REPO = Path("_iptv_epg")
INPUT = Path("public/high_value_unmatched.csv")
WORK = Path("v7_work")
WORK.mkdir(exist_ok=True)

MAX_EXACT = 5
MAX_FUZZY = 3
FUZZY_THRESHOLD = 0.91

CATEGORY_PRIORITY = {
    "Sports":0,"News":1,"Entertainment":2,"Movies":3,"Series":4,
    "Kids":5,"Documentary":6,"Comedy":7,"Animation":8
}

def source_rank(site):
    s=(site or "").lower()
    if "tvpassport.com" in s: return 0
    if "ontvtonight.com" in s: return 1
    if "tvguide.com" in s: return 2
    if "watchyour.tv" in s: return 3
    if "gatotv.com" in s: return 4
    if "whaletv.com" in s: return 5
    if "i.mjh.nz" in s: return 6
    if "plex" in s: return 7
    if "tvtv.us" in s: return 20
    if "distro.tv" in s: return 21
    if "epgshare01.online" in s: return 22
    return 10

STOP = {
    "hd","sd","uhd","4k","east","west","eastern","western","feed","channel",
    "network","tv","television","usa","us","united","states","live"
}

def norm(s):
    s=unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower()
    s=s.replace("&"," and ")
    toks=re.findall(r"[a-z0-9]+",s)
    toks=[x for x in toks if x not in STOP]
    return " ".join(toks)

def similarity(a,b):
    na,nb=norm(a),norm(b)
    if not na or not nb: return 0.0
    if na==nb: return 1.0
    ta,tb=set(na.split()),set(nb.split())
    jac=len(ta&tb)/len(ta|tb) if ta|tb else 0
    seq=SequenceMatcher(None,na,nb).ratio()
    # Conservative: both token overlap and string similarity matter.
    return max(seq, 0.55*seq+0.45*jac)


def compact(s):
    return "".join(re.findall(r"[a-z0-9]+", norm(s)))

def fuzzy_accept(query_name, candidate_name, score):
    nq, nc = norm(query_name), norm(candidate_name)
    if not nq or not nc:
        return False, "empty"

    tq, tc = set(nq.split()), set(nc.split())
    cq, cc = compact(query_name), compact(candidate_name)

    # Exact normalized/compact identity is excellent.
    if nq == nc or (cq and cq == cc):
        return True, "normalized_exact"

    # Short names/acronyms are dangerous: MMA-TV vs MATV, Tin TV vs TNTV, etc.
    if len(cq) <= 6 or len(cc) <= 6:
        return (score >= 0.985 and cq == cc), "short_name_strict"

    overlap = len(tq & tc)
    union = len(tq | tc)
    jaccard = overlap / union if union else 0.0

    # Require meaningful token agreement for non-short names.
    if score >= 0.95 and jaccard >= 0.50:
        return True, "high_token_agreement"
    if score >= 0.93 and overlap >= 2 and jaccard >= 0.60:
        return True, "multi_token_agreement"

    return False, "insufficient_agreement"


rows=list(csv.DictReader(INPUT.open(encoding="utf-8")))
def pri(r):
    groups=[x.strip() for x in (r.get("group") or "").split(";")]
    return (min([CATEGORY_PRIORITY.get(x,99) for x in groups] or [99]),r.get("name",""),r.get("id",""))
rows.sort(key=pri)
wanted={r["id"] for r in rows}

exact=defaultdict(list)
catalog=[]

for path in EPG_REPO.glob("sites/**/*.channels.xml"):
    try: root=ET.parse(path).getroot()
    except Exception: continue
    for ch in root.findall("channel"):
        item={
            "site":(ch.get("site") or "").strip(),
            "lang":(ch.get("lang") or "en").strip(),
            "xmltv_id":(ch.get("xmltv_id") or "").strip(),
            "site_id":(ch.get("site_id") or "").strip(),
            "site_name":(ch.text or "").strip(),
            "source_file":str(path)
        }
        if not item["site"] or not item["site_id"]: continue
        catalog.append(item)
        if item["xmltv_id"] in wanted:
            exact[item["xmltv_id"]].append(item)

channels=[]
attempts=[]

def add_attempt(row, choice, kind, score, n):
    safe=re.sub(r"[^A-Za-z0-9]+","_",row["id"]).strip("_")
    chfile=f"{safe}.attempt{n}.channels.xml"
    guide=f"{safe}.attempt{n}.guide.xml"
    root=ET.Element("channels")
    el=ET.SubElement(root,"channel",{
        "site":choice["site"],"lang":choice["lang"],
        # IMPORTANT: output programme IDs must match OUR playlist ID.
        "xmltv_id":row["id"],"site_id":choice["site_id"]
    })
    el.text=choice["site_name"] or row.get("name","")
    ET.ElementTree(root).write(WORK/chfile,encoding="utf-8",xml_declaration=True)
    attempts.append({
        "id":row["id"],"name":row.get("name",""),"group":row.get("group",""),
        "attempt":n,"match_kind":kind,"match_score":f"{score:.4f}",
        "candidate_xmltv_id":choice["xmltv_id"],"candidate_name":choice["site_name"],
        "site":choice["site"],"site_id":choice["site_id"],
        "channel_file":chfile,"guide_file":guide,"source_file":choice["source_file"]
    })

for row in rows:
    xid=row["id"]
    ex=exact.get(xid,[])
    unique={(x["site"],x["site_id"]):x for x in ex}
    ex=sorted(unique.values(),key=lambda x:(source_rank(x["site"]),x["site"],x["site_id"]))
    n=0
    for choice in ex[:MAX_EXACT]:
        n+=1; add_attempt(row,choice,"exact",1.0,n)

    fuzzy_candidates=[]
    if not ex:
        # Search by both playlist display name and ID stem.
        queries=[row.get("name",""), xid.split(".")[0]]
        for item in catalog:
            # Keep fuzzy discovery US-oriented where possible.
            cid=item["xmltv_id"]
            if cid and ".us" not in cid.lower() and "@us" not in cid.lower():
                continue
            score=max(similarity(q,item["site_name"]) for q in queries)
            # Also compare against candidate channel ID stem.
            if cid:
                score=max(score, similarity(xid.split(".")[0], cid.split(".")[0]))
            if score>=FUZZY_THRESHOLD:
                ok, reason = fuzzy_accept(row.get("name","") or xid.split(".")[0], item["site_name"], score)
                if ok:
                    item = dict(item)
                    item["fuzzy_reason"] = reason
                    fuzzy_candidates.append((score,item))
        # De-dupe source mapping, highest score first, then source quality.
        seen=set()
        fuzzy_candidates.sort(key=lambda z:(-z[0],source_rank(z[1]["site"]),z[1]["site"]))
        for score,item in fuzzy_candidates:
            key=(item["site"],item["site_id"])
            if key in seen: continue
            seen.add(key)
            n+=1; add_attempt(row,item,"fuzzy",score,n)
            if n>=MAX_FUZZY: break

    channels.append({
        "id":xid,"name":row.get("name",""),"group":row.get("group",""),
        "exact_mappings":len(ex),"attempts_prepared":n
    })

with (WORK/"channels.csv").open("w",newline="",encoding="utf-8") as f:
    fields=["id","name","group","exact_mappings","attempts_prepared"]
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(channels)
with (WORK/"attempts.csv").open("w",newline="",encoding="utf-8") as f:
    fields=["id","name","group","attempt","match_kind","match_score","candidate_xmltv_id","candidate_name","site","site_id","channel_file","guide_file","source_file","confidence_reason"]
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(attempts)

print(f"High-value unmatched: {len(channels)}")
print(f"Attempts prepared: {len(attempts)}")
print(f"Channels with attempts: {sum(int(x['attempts_prepared'])>0 for x in channels)}")
print(f"Fuzzy attempts: {sum(x['match_kind']=='fuzzy' for x in attempts)}")


# V7.4 source-discovery inventory for planning V8.
attempts_by_id = defaultdict(list)
for x in attempts:
    attempts_by_id[x["id"]].append(x)

with (WORK/"remaining_source_matrix.csv").open("w", newline="", encoding="utf-8") as f:
    fields=["id","name","group","exact_mapping_count","safe_candidate_count","discovery_class","best_candidate","best_site","best_score"]
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    for row in rows:
        xid=row["id"]
        ex_count=len(exact.get(xid,[]))
        aa=attempts_by_id.get(xid,[])
        fuzzy=[x for x in aa if x["match_kind"]=="fuzzy"]
        if ex_count:
            cls="EXACT_IPTVORG"
        elif fuzzy:
            cls="SAFE_FUZZY_IPTVORG"
        else:
            cls="NEW_SOURCE_NEEDED"
        best=fuzzy[0] if fuzzy else None
        w.writerow({
            "id":xid,"name":row.get("name",""),"group":row.get("group",""),
            "exact_mapping_count":ex_count,"safe_candidate_count":len(fuzzy),
            "discovery_class":cls,
            "best_candidate":best["candidate_name"] if best else "",
            "best_site":best["site"] if best else "",
            "best_score":best["match_score"] if best else ""
        })
