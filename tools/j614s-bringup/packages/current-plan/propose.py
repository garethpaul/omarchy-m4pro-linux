#!/usr/bin/env python3
"""Separate current-metadata proposal: fetch, print-resolve, compare; never install."""
import argparse
import concurrent.futures
import copy
import datetime
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_transaction import load_tools, key_material, signature_result, sha, write_evidence
from prepare_image import IMAGE_SHA, IMAGE_SIZE, restore

REVIEW_SHA='e5ee78dcbb16f888f6e618658afb4124657bb9ad3e9c0ea78c594432127d4cc2'
RESOLVER_SHA='6d93d58ba88edfad2c0a4b8d0309723af9405d33366ad676a0cbe5190c101c2b'
PUBLIC_COMMIT='81fd2d23ca6e3462183a4dc8360de3113fa8d80c'
ORDER=('omarchy','asahi-alarm','core','extra','alarm','aur')
CONFIGURED={
 'omarchy':'https://pkgs.omarchy.org/edge/aarch64/omarchy.db',
 'asahi-alarm':'https://github.com/asahi-alarm/asahi-alarm/releases/download/aarch64/asahi-alarm.db',
 **{n:f'https://arm-mirror.omarchy.org/aarch64/{n}/{n}.db' for n in ORDER[2:]}}
OFFICIAL={**CONFIGURED,**{n:f'https://ca.us.mirror.archlinuxarm.org/aarch64/{n}/{n}.db' for n in ORDER[2:]}}


def safe_url(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.username or parsed.password:raise ValueError('credential-bearing URL rejected')
    return urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))


def fetch(url,path,limit):
    proof={'url':safe_url(url),'tls_required':True,'tls_verification_disabled':False}
    try:
        with urllib.request.urlopen(url,timeout=45) as response:
            final=urllib.parse.urlsplit(response.geturl())
            if final.scheme!='https':raise ValueError('TLS downgrade rejected')
            data=response.read(limit+1)
            if len(data)>limit:raise ValueError('bounded metadata response exceeded')
            path.write_bytes(data)
            proof.update(status='retrieved',http_status=response.status,final_url=safe_url(response.geturl()),
                         final_query_redacted=bool(final.query),sha256=sha(path),bytes=len(data),
                         response_date=response.headers.get('Date'),last_modified=response.headers.get('Last-Modified'),etag=response.headers.get('ETag'))
    except urllib.error.HTTPError as error:
        with error:body=error.read(4096)
        proof.update(status='unavailable',http_status=error.code,final_url=safe_url(error.geturl()),failure=f'HTTPError: HTTP Error {error.code}: {error.reason}',error_body_sha256=hashlib.sha256(body).hexdigest())
    except Exception as error:proof.update(status='unavailable',failure=type(error).__name__+': '+str(error))
    proof['retrieved_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    return proof


def verify_db(path,sig,keys,home):
    command=['gpgv','--homedir',str(home),'--status-fd','1']
    for ring in keys['rings']:command+=['--keyring',ring]
    run=subprocess.run(command+[str(sig),str(path)],capture_output=True,text=True)
    result={'gpg_status':run.stdout.splitlines()}
    try:
        result.update(signature_result(run.returncode,run.stdout,keys))
        result['status']='WORKS' if result['retained_explicit_anchor_keyrings'] else 'BLOCKED'
    except ValueError as error:result.update(status='BLOCKED',failure=str(error))
    return result


def capture_repo(item,folder,keys,home):
    name,url=item;folder.mkdir(parents=True,exist_ok=True)
    path=folder/(name+'.db');sig=folder/(name+'.db.sig')
    proof=fetch(url,path,32*1024*1024)
    proof['signature_download']=fetch(url+'.sig',sig,16384)
    if proof['status']!='retrieved':proof['metadata_authentication']='BLOCKED (DB unavailable)'
    elif proof['signature_download']['status']=='retrieved':
        proof['database_signature']=verify_db(path,sig,keys,home)
        proof['metadata_authentication']=proof['database_signature']['status']
    elif proof['signature_download'].get('http_status')==404:
        proof['metadata_authentication']='UNSIGNED (DatabaseOptional; TLS origin only)'
    else:proof['metadata_authentication']='BLOCKED (signature availability unresolved)'
    proof['freshness_completeness']='UNPROVEN; retrieval time/TLS/signature do not prove repository completeness or newest state'
    return name,proof


def original_inputs(source):
    records,protected=load_tools(source)
    for relative,digest in [('evidence/arm-package-plan.json',REVIEW_SHA),('resolve_package_review.py',RESOLVER_SHA)]:
        if sha(source/relative)!=digest:raise ValueError('original compatibility/resolver input changed')
    resolver=importlib.import_module('resolve_package_review')
    planner=importlib.import_module('arm_package_plan')
    review=json.loads((source/'evidence/arm-package-plan.json').read_text())
    if len(review['resolved_requests'])!=167:raise ValueError('recorded167 requests changed')
    return records,protected,resolver,planner,review


def review_for_metadata(original,repositories,planner):
    index,provenance=planner.index_repositories(repositories)
    review=copy.deepcopy(original);review['repositories']=provenance
    review['resolved_requests']=[];review['unresolved_requests']=[];differences=[]
    for old in original['resolved_requests']:
        canonical=old['candidate']['name']
        candidate=index.get(canonical)
        # Keep recorded compatibility mapping explicit. Never silently choose another provider.
        if candidate is None or candidate['name']!=canonical:
            review['unresolved_requests'].append({'requested':old['requested'],'canonical':canonical,'reason':'recorded canonical package unavailable; no replacement selected'})
            continue
        row={**old,'candidate':candidate,'resolution_evidence':'current metadata candidate for the explicitly recorded canonical compatibility mapping; signed alias proof still required'}
        review['resolved_requests'].append(row)
        if candidate!=old['candidate']:differences.append({'requested':old['requested'],'old':old['candidate'],'new':candidate})
    return review,differences


def transaction_diff(old,new):
    previous={r['name']:r for r in old};current={r['name']:r for r in new}
    return {'added':[current[n] for n in sorted(current.keys()-previous.keys())],
            'removed':[previous[n] for n in sorted(previous.keys()-current.keys())],
            'changed':[{'name':n,'old':previous[n],'new':current[n]} for n in sorted(previous.keys()&current.keys()) if previous[n]!=current[n]],
            'unchanged_count':sum(previous[n]==current[n] for n in previous.keys()&current.keys())}


def frozen_policy(image,folder):
    if image.stat().st_size!=IMAGE_SIZE or sha(image)!=IMAGE_SHA:raise ValueError('frozen image identity mismatch')
    if folder.exists():raise ValueError('new frozen-policy extraction required')
    restore(image,folder,[('etc/pacman.conf',False),('etc/pacman.d/mirrorlist',False)])
    result={'image_sha256':IMAGE_SHA,'image_bytes':IMAGE_SIZE,'root':256,'files':{}}
    for rel in ('etc/pacman.conf','etc/pacman.d/mirrorlist'):
        path=folder/rel
        if path.is_symlink() or not path.is_file():raise ValueError('frozen policy file unavailable')
        text=path.read_text()
        for url in re.findall(r'https?://[^\s]+',text):safe_url(url)
        result['files'][rel]={'sha256':sha(path),'text':text}
    config=result['files']['etc/pacman.conf']['text']
    siglevels=re.findall(r'^\s*SigLevel\s*=\s*(.+)$',config,re.M)
    result['observed_siglevel_directives']=siglevels
    result['scope']='retained immutable image configuration; not live target config'
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--public-source',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.private.exists():raise ValueError('new capture directory required; frozen captures are not overwritten')
    a.private.mkdir(parents=True);a.output.mkdir(parents=True,exist_ok=True)
    records,protected,resolver,planner,old_review=original_inputs(a.source)
    if subprocess.check_output(['git','-C',str(a.public_source),'rev-parse','HEAD'],text=True).strip()!=PUBLIC_COMMIT:raise ValueError('reviewed public source commit changed')
    public={}
    for rel in ('default/pacman/aarch64-apple/pacman-edge.conf','default/pacman/aarch64-apple/mirrorlist-edge'):
        public[rel]={'sha256':sha(a.public_source/rel),'source_url':f'https://github.com/omacom/omarchy/blob/{PUBLIC_COMMIT}/{rel}'}
    # Compare retained keys byte-for-byte with the previous fully audited frozen-image evidence.
    parent=Path(__file__).resolve().parents[1]
    prior=json.loads((parent/'evidence/transaction-audit.json').read_text())
    keys=key_material(a.source/'evidence/package-root/usr/share/pacman/keyrings',a.private)
    if keys['files']!=prior['keyring_files']:raise ValueError('frozen-image public keyring policy changed')
    policy=frozen_policy(a.image,a.private/'image-policy')
    write_evidence(a.output/'frozen-policy.json',policy)
    old_transaction=prior['packages']
    old_rows=[{key:r[key] for key in ('repository','name','version','filename','sha256','architecture')} for r in old_transaction]
    all_metadata={}
    for variant,urls in [('configured-current',CONFIGURED),('official-alarm-current',OFFICIAL)]:
        folder=a.private/variant/'repositories';folder.mkdir(parents=True)
        if variant=='configured-current':todo=list(urls.items())
        else:
            todo=list(urls.items())[2:]
            for name in ORDER[:2]:
                import shutil
                shutil.copyfile(a.private/'configured-current/repositories'/(name+'.db'),folder/(name+'.db'))
            all_metadata[variant]={n:copy.deepcopy(all_metadata['configured-current'][n]) for n in ORDER[:2]}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            capture=dict(pool.map(lambda item:capture_repo(item,folder,keys,a.private/'gnupg'),todo))
        all_metadata.setdefault(variant,{}).update(capture)
        provenance=all_metadata[variant]
        write_evidence(a.output/(variant+'-repositories.json'),provenance)
        if any(provenance[n]['status']!='retrieved' for n in ORDER):
            write_evidence(a.output/(variant+'-proposal.json'),{'status':'BLOCKED','reason':'repository unavailable','deployable':False,'execution_ready':False,'actions':[]})
            continue
        if any(sha(folder/(n+'.db'))!=provenance[n]['sha256'] for n in ORDER):raise ValueError('captured repository bytes changed')
        repositories=[(n,folder/(n+'.db')) for n in ORDER]
        review,differences=review_for_metadata(old_review,repositories,planner)
        result=resolver.resolve(review,repositories,a.source/'evidence/package-root/var/lib/pacman/local',a.private/variant/'resolver')
        result.update(proposal_variant=variant,execution_ready=False,metadata_authentication={n:provenance[n]['metadata_authentication'] for n in ORDER},
                      recorded_compatibility_request_count=167,current_resolved_request_count=len(review['resolved_requests']),
                      request_candidate_differences=differences,source_commit=PUBLIC_COMMIT,public_source=public,
                      historical_snapshot_replaced=False,payload_qualification='Separate payload evidence required; this file is metadata-only',metadata_freshness_completeness='UNPROVEN',
                      reverse_dependency_ABI='UNTESTED: untouched image reverse dependencies may be incompatible with a partial upgrade',
                      required_isolated_test='Disposable full-image/ABI qualification required before any real install; no -Syu or target changes authorized in this lane')
        result['transaction_differences']=transaction_diff(old_rows,result['resolved_transaction']) if result.get('print_exit')==0 else {'status':'UNTESTED (resolver failed; no complete transaction to compare)'}
        result['dependency_differences']={'old_added_dependencies':json.loads((a.source/'evidence/pacman-print-resolution.json').read_text())['new_dependency_packages'],'new_added_dependencies':result.get('new_dependency_packages',[])}
        write_evidence(a.output/(variant+'-request-review.json'),review)
        write_evidence(a.output/(variant+'-proposal.json'),result)
    print(json.dumps({variant:{n:proof['metadata_authentication'] for n,proof in values.items()} for variant,values in all_metadata.items()},indent=2))
if __name__=='__main__':main()
