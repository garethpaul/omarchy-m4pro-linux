#!/usr/bin/env python3
"""Qualify frozen current payloads and signed metadata; never execute/install them."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import tarfile
import urllib.parse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_transaction import (audit_one, baseline_hooks, execution_gate, hook_matches,
                               image_snapshot, key_material, pkginfo, sha, write_evidence)
from propose import ORDER, CONFIGURED, OFFICIAL, original_inputs, transaction_diff, verify_db

SIGNED_FIELDS={'DEPENDS':'depend','OPTDEPENDS':'optdepend','PROVIDES':'provides',
 'CONFLICTS':'conflict','REPLACES':'replaces','LICENSE':'license','BASE':'pkgbase',
 'DESC':'pkgdesc','URL':'url','ISIZE':'size','BUILDDATE':'builddate','PACKAGER':'packager'}


def signed_metadata(fields,info):
    differences={key:{'repository_metadata':fields.get(key,[]),'signed_pkginfo':info.get(signed,[])}
                 for key,signed in SIGNED_FIELDS.items()
                 if sorted(set(fields.get(key,[])))!=sorted(set(info.get(signed,[])))}
    if differences:raise ValueError('signed .PKGINFO disagrees with selected repository metadata: '+json.dumps(differences,sort_keys=True))
    return {'status':'WORKS','fields_compared':SIGNED_FIELDS,
            'signed_dependencies':{key:info.get(value,[]) for key,value in SIGNED_FIELDS.items() if key in ('DEPENDS','OPTDEPENDS','PROVIDES','CONFLICTS','REPLACES')},
            'scope':'authenticates this package identity/metadata; does not authenticate DB completeness, ordering or freshness'}


def exact_items(proposal,provenance,folder,records,protected):
    if proposal.get('deployable') is not False or proposal.get('execution_ready') is not False or proposal.get('print_exit')!=0:
        raise ValueError('current proposal is not a blocked successful print-only resolution')
    expected={r['name']:r['sha256'] for r in proposal['repositories']}
    byrepo={}
    for name in ORDER:
        path=folder/(name+'.db')
        if sha(path)!=expected[name] or expected[name]!=provenance[name]['sha256']:raise ValueError('current metadata identity changed')
        proof=provenance[name]
        if proof['metadata_authentication'] not in ('WORKS','UNSIGNED (DatabaseOptional; TLS origin only)'):raise ValueError('repository signature policy failure or unresolved metadata trust')
        if proof['metadata_authentication']=='WORKS' and proof['database_signature'].get('status')!='WORKS':raise ValueError('unqualified DB signature')
        byrepo[name]={r['NAME'][0]:r for r in records(path,[])}
    selected=[]
    for row in proposal['resolved_transaction']:
        if protected(row['name']):raise ValueError('protected selection remains rejected')
        fields=byrepo[row['repository']][row['name']]
        for key,db in [('name','NAME'),('version','VERSION'),('architecture','ARCH'),('filename','FILENAME'),('sha256','SHA256SUM')]:
            if fields.get(db)!=[row[key]]:raise ValueError('current plan/DB selection mismatch')
        if row['architecture'] not in ('aarch64','any') or Path(row['filename']).name!=row['filename']:raise ValueError('architecture/path rejected')
        url=urllib.parse.urljoin(provenance[row['repository']]['url'],urllib.parse.quote(row['filename']))
        selected.append((row,fields,url))
    return selected


def one(item,cache,keys,oldcache):
    row,fields,url=item
    # Reuse only byte-identical old cache objects, in a separate current-proposal cache.
    old=oldcache/'payloads'/row['sha256']/row['filename']
    target=cache/'payloads'/row['sha256']/row['filename']
    if old.is_file() and not target.exists() and sha(old)==row['sha256']:
        target.parent.mkdir(parents=True,exist_ok=True);os.link(old,target)
    result=audit_one(item,cache,keys)
    if result['status']!='WORKS':return result
    try:
        with tarfile.open(target) as archive:
            member=next(m for m in archive if m.name.removeprefix('./')=='.PKGINFO')
            info=pkginfo(archive.extractfile(member).read().decode())
        result['signed_metadata_comparison']=signed_metadata(fields,info)
        result['signed_pkginfo']=info
    except Exception as error:
        result['status']='BLOCKED';result['failure']=type(error).__name__+': '+str(error)
    return result


def old_new_dependency_diffs(items,source,old_review,records):
    olddb={}
    for entry in old_review['repositories']:
        path=source/'evidence/repositories'/(entry['name']+'.db')
        if sha(path)!=entry['sha256']:raise ValueError('historical DB changed')
        olddb[entry['name']]={f['NAME'][0]:f for f in records(path,[])}
    differences=[]
    for row,fields,_ in items:
        old=olddb.get(row['repository'],{}).get(row['name'])
        if not old:continue
        changes={key:{'old':old.get(key,[]),'new':fields.get(key,[])} for key in ('DEPENDS','OPTDEPENDS','PROVIDES','CONFLICTS','REPLACES')
                 if sorted(set(old.get(key,[])))!=sorted(set(fields.get(key,[])))}
        if changes:differences.append({'name':row['name'],'old_version':old['VERSION'][0],'new_version':row['version'],'changes':changes,
                                      'old_scope':'historical pinned repository metadata; missing old payloads are not newly authenticated'})
    return differences


def alias_evidence(review, packages, cache):
    byname={r['name']:r for r in packages};evidence=[]
    for request in review['resolved_requests']:
        name=request['candidate']['name'];alias=request['requested']
        if alias==name:continue
        package=byname.get(name)
        row={'requested':alias,'recorded_canonical':name,'status':'BLOCKED','runtime':'UNTESTED in this proposal; no payload execution'}
        try:
            if not package or package['status']!='WORKS':raise ValueError('selected alias payload not qualified')
            info=package['signed_pkginfo'];provided={x.split('=',1)[0] for x in info.get('provides',[])}
            if alias not in provided:raise ValueError('signed provider claim missing')
            row['signed_provides']=info.get('provides',[]);row['payload_sha256']=package['sha256']
            entry={'nvim':'usr/bin/nvim','vi':'usr/bin/vi'}.get(alias)
            if entry:
                path=cache/'payloads'/package['sha256']/package['filename']
                with tarfile.open(path) as archive:
                    member=next(m for m in archive if m.name.removeprefix('./')==entry)
                    if not member.isfile() or not member.mode & 0o111 or not 0<member.size<=64*1024*1024:raise ValueError('provider does not own required executable regular file')
                    data=archive.extractfile(member).read()
                row['owned_executable']={'path':entry,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
            if alias=='vi':
                deps={re.split(r'[<>=]',x,1)[0] for x in info.get('depend',[])}
                if not {'bash','vim'}<=deps:raise ValueError('signed vi wrapper dependencies missing')
            row['status']='WORKS (signed provider/ownership evidence only)'
        except Exception as error:row['failure']=type(error).__name__+': '+str(error)
        evidence.append(row)
    return evidence

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--variant',choices=('configured-current','official-alarm-current'),required=True)
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--old-cache',type=Path,required=True);p.add_argument('--image-hooks',type=Path,required=True)
    a=p.parse_args();a.cache.mkdir(parents=True,exist_ok=True)
    records,protected,resolver,planner,old_review=original_inputs(a.source)
    proposal_path=a.evidence/(a.variant+'-proposal.json');provenance_path=a.evidence/(a.variant+'-repositories.json')
    proposal=json.loads(proposal_path.read_text());provenance=json.loads(provenance_path.read_text())
    items=exact_items(proposal,provenance,a.capture/a.variant/'repositories',records,protected)
    keys=key_material(a.source/'evidence/package-root/usr/share/pacman/keyrings',a.cache)
    parent=Path(__file__).resolve().parents[1]
    previous=json.loads((parent/'evidence/transaction-audit.json').read_text())
    if keys['files']!=previous['keyring_files']:raise ValueError('frozen retained trust anchors changed')
    signature_rechecks={}
    expected_urls=CONFIGURED if a.variant=='configured-current' else OFFICIAL
    for name,proof in provenance.items():
        if proof['url']!=expected_urls[name] or not proof['tls_required'] or proof['tls_verification_disabled']:raise ValueError('source/TLS provenance changed')
        if proof['metadata_authentication']=='WORKS':
            signature=a.capture/a.variant/'repositories'/(name+'.db.sig')
            if not signature.exists():signature=a.capture/'configured-current/repositories'/(name+'.db.sig')
            if sha(signature)!=proof['signature_download']['sha256']:raise ValueError('frozen DB signature bytes changed')
            checked=verify_db(a.capture/a.variant/'repositories'/(name+'.db'),signature,keys,a.cache/'gnupg')
            if checked['status']!='WORKS':raise ValueError('current DB signature no longer qualifies')
            signature_rechecks[name]=checked
    manifest=image_snapshot(a.image_hooks,a.source);baseline=baseline_hooks(a.image_hooks)
    from package_audit import desc_fields
    installed={desc_fields(path.read_text())['NAME'][0] for path in (a.source/'evidence/package-root/var/lib/pacman/local').glob('*/desc')}
    result={'schema':1,'audit_complete':False,'deployable':False,'execution_ready':False,'actions':[],
            'proposal_sha256':sha(proposal_path),'repository_provenance_sha256':sha(provenance_path),'variant':a.variant,
            'historical_snapshot_replaced':False,'retained_keyring_files':keys['files'],'image_snapshot_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
            'metadata_authentication':proposal['metadata_authentication'],'database_signature_rechecked':signature_rechecks,'database_freshness_completeness':'UNPROVEN',
            'reverse_dependency_ABI':'UNTESTED: current packages against untouched986-package image may be a partial upgrade; dependency solving and PGP do not prove binary compatibility',
            'required_isolated_test':'Use a disposable full-image clone/ABI qualification environment before proposing any real install; do not use -Syu or alter the target in this lane',
            'old_new_dependency_metadata_differences':old_new_dependency_diffs(items,a.source,old_review,records),'packages':[]}
    output=a.evidence/(a.variant+'-payload-qualification.json')
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for row in pool.map(lambda item:one(item,a.cache,keys,a.old_cache),items):
            result['packages'].append(row);write_evidence(output,result)
            print(row['name'],row['status'],row.get('failure',''),flush=True)
    request_review=json.loads((a.evidence/(a.variant+'-request-review.json')).read_text())
    result['compatibility_alias_evidence']=alias_evidence(request_review,result['packages'],a.cache)
    matches=[hook_matches(h,result['packages'],installed) for h in baseline['effective']]
    result.update(execution_gate(result['packages'],baseline,matches))
    result['counts']={'selected':len(items),'payloads_qualified':sum(r['status']=='WORKS' for r in result['packages']),'failed':sum(r['status']!='WORKS' for r in result['packages'])}
    result['status']='WORKS (payload/metadata identity only)' if not result['counts']['failed'] else 'PARTIAL'
    if any(not r['status'].startswith('WORKS') for r in result['compatibility_alias_evidence']):
        result['status']='PARTIAL';result['execution_blockers'].append({'reason':'signed compatibility alias evidence incomplete'})
    result['installation_status']='BLOCKED: held boot requests, boot effects, untouched reverse-dependency ABI, live target and rollback unqualified'
    for row in result['packages']:
        paths=row.pop('payload_paths',[]);row['archive_path_count']=len(paths);row['archive_paths_sha256']=hashlib.sha256(json.dumps(paths,separators=(',',':')).encode()).hexdigest()
    result['audit_complete']=True;write_evidence(output,result)
if __name__=='__main__':main()
