#!/usr/bin/env python3
"""Check one alternate official mirror for exact failed payload pins; no substitutions."""
import argparse
import datetime
import json
from pathlib import Path
import urllib.parse
from audit_transaction import audit_one, key_material, load_tools, pin_rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--cache',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();proof=json.loads(a.audit.read_text());rows=[]
    records,protected=load_tools(a.source)
    plan=json.loads((a.source/'evidence/pacman-print-resolution.json').read_text())
    provenance=json.loads((a.source/'evidence/repositories/provenance.json').read_text())
    items={r['name']:(r,f,u) for r,f,u in pin_rows(plan,provenance,a.source,records,protected)}
    a.cache.mkdir(exist_ok=True,parents=True)
    keys=key_material(a.source/'evidence/package-root/usr/share/pacman/keyrings',a.cache)
    # Fixed scope: one alternate for each of the two actually observed primary 404s.
    for item in proof['packages']:
        if item['name'] not in ('marisa','graphicsmagick'):continue
        pinned,fields,primary_url=items[item['name']]
        for key in ('name','version','filename','sha256','architecture'):
            if item[key]!=pinned[key]:raise ValueError('alternate check identity changed')
        if item['url']!=primary_url:raise ValueError('primary provenance changed')
        url='https://mirror.archlinuxarm.org/aarch64/extra/'+urllib.parse.quote(pinned['filename'])
        checked=audit_one((pinned,fields,url),a.cache,keys)
        checked.update(primary_url=primary_url,primary_failure=item.get('failure'),metadata_refresh=False,substitution=False)
        checked.pop('payload_paths',None)
        rows.append(checked)
    a.output.write_text(json.dumps({'schema':1,'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':rows,'actions':[]},indent=2)+'\n')
if __name__=='__main__':main()
