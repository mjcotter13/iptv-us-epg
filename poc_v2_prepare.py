from pathlib import Path
import xml.etree.ElementTree as ET
from collections import defaultdict
import csv,re
EPG_REPO=Path('_iptv_epg'); OUT=Path('poc_v2_work'); OUT.mkdir(exist_ok=True)
TARGETS=['ESPNU.us@SD','NFLNetwork.us@SD','TennisChannel.us@SD','MTV.us@East','USANetwork.us@East']
found=defaultdict(list)
for path in EPG_REPO.glob('sites/**/*.channels.xml'):
    try: r=ET.parse(path).getroot()
    except: continue
    for ch in r.findall('channel'):
        xid=(ch.get('xmltv_id') or '').strip()
        if xid in TARGETS:
            found[xid].append({'site':(ch.get('site') or '').strip(),'lang':(ch.get('lang') or 'en').strip(),'xmltv_id':xid,'site_id':(ch.get('site_id') or '').strip(),'name':(ch.text or xid).strip(),'source_file':str(path)})
def rank(x):
    s=x['site'].lower()
    return (0 if 'ontvtonight.com' in s else 1 if 'tvguide.com' in s else 9 if 'epgshare01.online' in s else 3,x['site'],x['site_id'])
rows=[]
for xid in TARGETS:
    choices=[x for x in found[xid] if x['site'] and x['site_id']]; choices.sort(key=rank)
    chosen=choices[0] if choices else None
    safe=re.sub(r'[^A-Za-z0-9]+','_',xid).strip('_')
    root=ET.Element('channels')
    if chosen:
        el=ET.SubElement(root,'channel',{'site':chosen['site'],'lang':chosen['lang'],'xmltv_id':chosen['xmltv_id'],'site_id':chosen['site_id']}); el.text=chosen['name']
        rows.append({**chosen,'channel_file':f'{safe}.channels.xml'})
    else:
        rows.append({'site':'','lang':'','xmltv_id':xid,'site_id':'','name':'','source_file':'NO EXACT MAPPING FOUND','channel_file':f'{safe}.channels.xml'})
    ET.ElementTree(root).write(OUT/f'{safe}.channels.xml',encoding='utf-8',xml_declaration=True)
with (OUT/'selected_mappings.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['xmltv_id','name','site','site_id','lang','source_file','channel_file']); w.writeheader(); w.writerows(rows)
for r in rows: print(r['xmltv_id'],r['site'] or 'NO MAPPING',r['site_id'] or '-')
