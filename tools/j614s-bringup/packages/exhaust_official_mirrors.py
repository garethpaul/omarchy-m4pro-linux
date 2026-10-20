#!/usr/bin/env python3
"""Probe every currently published ALARM mirror for two unchanged package pins."""
import argparse
import concurrent.futures
import datetime
import hashlib
import html
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
from audit_transaction import audit_one, key_material, load_tools, pin_rows, sha, write_evidence

DOC='https://archlinuxarm.org/about/mirrors'
JS='https://archlinuxarm.org/public/js/mirrors.js'
LIST='https://archlinuxarm.org/data/mirrors/list'
NAMES={'marisa','graphicsmagick'}
PREVIOUS={
 'transaction-audit.json':'d63559fc4cad4c7e3974cbc71acaee9ddfc9d1b4b6d67b6eff13e44a17d16eb7',
 'official-mirror-checks.json':'93e7586ed4f1ff3f10caf0cf769fb72ff1deb496343dd3d704e5436b2868eba2',
 'summary.json':'443546e77dfaaa4dbede4d9a1eb53dcc29057c19b040f65e8148f44563122277',
}


def fetch(url, cache, name, *, ajax=False):
    headers={'X-Requested-With':'XMLHttpRequest','Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','Referer':DOC} if ajax else {}
    request=urllib.request.Request(url,data=b'' if ajax else None,headers=headers,method='POST' if ajax else 'GET')
    with urllib.request.urlopen(request,timeout=30) as response:
        data=response.read(2*1024*1024+1)
        if len(data)>2*1024*1024:raise ValueError('oversized public documentation')
        (cache/name).write_bytes(data)
        return data,{'url':url,'method':request.method,'status':response.status,'final_url':response.geturl(),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}


def published_domains(data):
    rows=json.loads(data)['data'];domains=[]
    for row in rows:
        domain=row[2]
        if not re.fullmatch(r'[a-z0-9.-]+\.mirror\.archlinuxarm\.org',domain):raise ValueError('unreviewed official mirror domain')
        domains.append(domain)
    if not domains or len(domains)!=len(set(domains)):raise ValueError('empty/duplicate official mirror list')
    return domains


def package_page(data):
    text=data.decode();heading=re.search(r'<h1>([^<]+)</h1>',text)
    downloads=[html.unescape(x) for x in re.findall(r'href="([^"]+)"[^>]*>Download</a>',text)]
    if not heading or len(downloads)!=1:raise ValueError('official package page format changed')
    parts=urllib.parse.urlparse(downloads[0]).path.strip('/').split('/')
    if len(parts)!=3 or parts[0]!='aarch64':raise ValueError('unreviewed official package route')
    return {'heading':html.unescape(heading[1]),'documented_download_url':downloads[0],
            'architecture':parts[0],'repository':parts[1],'current_filename':parts[2],
            'new_version_payload_requested':False}


def probe(item, domain, cache, keys):
    row,fields,_=item
    url='http://'+domain+'/aarch64/'+row['repository']+'/'+urllib.parse.quote(row['filename'])
    result={**row,'expected_bytes':int(fields['CSIZE'][0]),'requested_url':url,'status':'BLOCKED','checks_disabled':False}
    folder=cache/'routes'/domain/row['sha256'];folder.mkdir(parents=True,exist_ok=True)
    path=folder/row['filename'];partial=path.with_name(path.name+'.partial')
    try:
        with urllib.request.urlopen(url,timeout=30) as response,partial.open('wb') as stream:
            result.update(http_status=response.status,final_url=response.geturl())
            total=0
            while block:=response.read(1048576):
                total+=len(block)
                if total>int(fields['CSIZE'][0]):raise ValueError('larger than exact pinned CSIZE')
                stream.write(block)
        if total!=int(fields['CSIZE'][0]) or sha(partial)!=row['sha256']:raise ValueError('exact pinned size/SHA mismatch')
        partial.replace(path)
        # Reuse the full auditor for architecture, signed identity, PGP and retained anchor rules.
        # Each route gets an isolated cache; recovered payloads are never installed.
        qualified=folder/'qualification';qualified.mkdir(exist_ok=True)
        payload=qualified/'payloads'/row['sha256'];payload.mkdir(parents=True,exist_ok=True)
        import shutil
        shutil.copyfile(path,payload/row['filename'])
        local_keys={**keys,'rings':keys['rings']}
        (qualified/'gnupg').mkdir(exist_ok=True,mode=0o700)
        pinned=audit_one((row,fields,url),qualified,local_keys)
        pinned.pop('payload_paths',None)
        # Also fetch the mirror's detached .sig. Both must verify; no signature assumptions.
        detached_fields={**fields};detached_fields.pop('PGPSIG',None)
        detached=audit_one((row,detached_fields,url),qualified,local_keys)
        detached.pop('payload_paths',None)
        result['pinned_signature_qualification']=pinned;result['mirror_detached_signature_qualification']=detached
        result['status']='WORKS' if pinned['status']==detached['status']=='WORKS' else 'BLOCKED'
    except urllib.error.HTTPError as error:
        with error:body=error.read(4096)
        result.update(http_status=error.code,final_url=error.geturl(),error_body_sha256=hashlib.sha256(body).hexdigest(),failure=f'HTTPError: HTTP Error {error.code}: {error.reason}')
    except Exception as error:result['failure']=type(error).__name__+': '+str(error)
    finally:partial.unlink(missing_ok=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.cache.mkdir(exist_ok=True,parents=True)
    prior=Path(__file__).resolve().parent/'evidence'
    for name,digest in PREVIOUS.items():
        if sha(prior/name)!=digest:raise ValueError('previous failure evidence changed: '+name)
    original_audit=json.loads((prior/'transaction-audit.json').read_text())
    records,protected=load_tools(a.source)
    plan=json.loads((a.source/'evidence/pacman-print-resolution.json').read_text())
    provenance=json.loads((a.source/'evidence/repositories/provenance.json').read_text())
    items=[item for item in pin_rows(plan,provenance,a.source,records,protected) if item[0]['name'] in NAMES]
    if {item[0]['name'] for item in items}!=NAMES:raise ValueError('exact pinned two-package selection missing')
    docs=[]
    page,proof=fetch(DOC,a.cache,'mirrors.html');docs.append(proof)
    if b'/public/js/mirrors.js' not in page:raise ValueError('mirror list discovery changed')
    js,proof=fetch(JS,a.cache,'mirrors.js');docs.append(proof)
    if b'url:"/data/mirrors/list",type:"POST"' not in js:raise ValueError('official AJAX mirror source changed')
    listing,proof=fetch(LIST,a.cache,'mirror-list.json',ajax=True);docs.append(proof)
    domains=published_domains(listing)
    pages=[]
    for row,_,_ in items:
        data,proof=fetch('https://archlinuxarm.org/packages/aarch64/'+row['name'],a.cache,row['name']+'.html');docs.append(proof)
        pages.append({'name':row['name'],**package_page(data),'source_url':proof['url']})
    if any(urllib.parse.urlparse(p['documented_download_url']).scheme!='http' for p in pages):raise ValueError('documented protocol changed; route review required')
    if any(p['repository']!=next(r['repository'] for r,_,_ in items if r['name']==p['name']) for p in pages):
        raise ValueError('documented repository migration needs explicit route review')
    keys=key_material(a.source/'evidence/package-root/usr/share/pacman/keyrings',a.cache)
    if keys['files']!=original_audit['keyring_files']:raise ValueError('retained image keyring evidence changed')
    routes=['mirror.archlinuxarm.org',*domains]
    result={'schema':1,'status':'IN_PROGRESS','scope':'supplemental current official routes; original plan and prior failures retained',
            'previous_evidence':{'commit':'07ecb175cbeeb01061665c0bc347f45f54e371b3','sha256':PREVIOUS},'documentation':docs,'official_mirrors':domains,'current_package_page_observations':pages,'checks':[],
            'metadata_refresh':False,'substitution':False,'deployable':False,'execution_ready':False,'actions':[]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        jobs=[(item,domain) for item in items for domain in routes]
        for row in pool.map(lambda args:probe(*args,a.cache,keys),jobs):
            result['checks'].append(row);write_evidence(a.output,result)
            print(row['name'],row['requested_url'],row['status'],row.get('failure',''),flush=True)
    result['counts']={'routes_per_package':len(routes),'checks':len(result['checks']),'recovered_qualified':sum(r['status']=='WORKS' for r in result['checks'])}
    recovered={r['name'] for r in result['checks'] if r['status']=='WORKS'}
    result['status']='WORKS (same pinned bytes recovered; installation still blocked)' if recovered==NAMES else 'PARTIAL' if recovered else 'BLOCKED'
    result['conclusion']='All published mirror routes tested for the original extra/aarch64 pins. No exact pinned payload recovered.' if not recovered else 'Exact pinned bytes recovered for: '+', '.join(sorted(recovered))
    result['category_migration']='No evidence: both current official pages remain aarch64/extra; their release numbers are newer than the pinned plan.'
    result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();write_evidence(a.output,result)
if __name__=='__main__':main()
