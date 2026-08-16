from pathlib import Path
import xml.etree.ElementTree as ET
from collections import Counter
import csv
W=Path('poc_v2_work'); O=Path('poc_v2_results'); O.mkdir(exist_ok=True)
TARGETS=['ESPNU.us@SD','NFLNetwork.us@SD','TennisChannel.us@SD','MTV.us@East','USANetwork.us@East']
tv=ET.Element('tv',{'generator-info-name':'IPTV-org Five Channel POC v2'}); c=Counter(); seen=set()
for g in W.glob('*.guide.xml'):
    try:r=ET.parse(g).getroot()
    except Exception as e: print('skip',g,e); continue
    for ch in r.findall('channel'):
        cid=(ch.get('id') or '').strip()
        if cid and cid not in seen: tv.append(ch); seen.add(cid)
    for p in r.findall('programme'):
        cid=(p.get('channel') or '').strip()
        if cid: tv.append(p); c[cid]+=1
ET.ElementTree(tv).write(O/'poc_guide_merged.xml',encoding='utf-8',xml_declaration=True)
with (O/'program_counts.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['channel_id','programmes','success']); w.writeheader()
    [w.writerow({'channel_id':x,'programmes':c[x],'success':'YES' if c[x] else 'NO'}) for x in TARGETS]
working=sum(bool(c[x]) for x in TARGETS)
with (O/'status.txt').open('w') as f:
    f.write(f'targets=5\nchannels_with_programmes={working}\nchannels_without_programmes={5-working}\n')
    [f.write(f'{x}={c[x]} programmes\n') for x in TARGETS]
(O/'selected_mappings.csv').write_bytes((W/'selected_mappings.csv').read_bytes())
print((O/'status.txt').read_text())
