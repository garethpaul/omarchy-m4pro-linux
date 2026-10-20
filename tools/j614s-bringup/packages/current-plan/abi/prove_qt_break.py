#!/usr/bin/env python3
"""Readelf-confirm unchanged Qt consumers losing versioned imports after overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
from audit_plan import sha
from filesystem import verify_or_write

def symbols(path):
    run=subprocess.run(['readelf','--wide','--dyn-syms',str(path)],check=True,capture_output=True,text=True)
    if run.stderr:raise ValueError('readelf warnings: '+run.stderr)
    return run.stdout

def has(text,name,undefined):
    # Readelf output includes symbol version suffix and optional version index.
    matching=[line for line in text.splitlines() if re.search(r'\b'+re.escape(name)+r'@@?Qt_6_PRIVATE_API(?:\s|$)',line)]
    return any((' UND ' in line)==undefined for line in matching)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--restore',type=Path,required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.private.mkdir(parents=True,exist_ok=True)
    report=json.loads(a.report.read_text());qualification=json.loads(a.qualification.read_text());packages={x['name']:x for x in qualification['packages']};proof=[];texts={}
    rows=[x for x in report['new_or_incoming_issues'] if x['baseline_issues']==[] and x['consumer_owner'].startswith('qt6-')]
    for row in rows:
        old_provider=next(x['old_provider'] for x in report['removed_export_name_candidates'] if x['consumer']==row['consumer'] and x['needed']==row['needed'])
        package=packages[row['provider_owner']];payload=a.cache/'payloads'/package['sha256']/package['filename']
        if sha(payload)!=package['sha256']:raise ValueError('payload identity changed')
        target=a.private/(package['sha256']+'-'+Path(row['provider']).name)
        with tarfile.open(payload) as archive:
            member=archive.getmember(row['provider'])
            if not member.isfile() or member.size>128*1024*1024:raise ValueError('provider is not bounded regular data')
            data=archive.extractfile(member).read()
        verify_or_write(target,data)
        consumer=a.restore/row['consumer'];old=a.restore/old_provider
        if consumer.is_symlink() or old.is_symlink():raise ValueError('proof must name physical regular data')
        for path in (consumer,old,target):
            if str(path) not in texts:texts[str(path)]=symbols(path)
        missing=[x.removeprefix('missing_symbol:').removesuffix('@Qt_6_PRIVATE_API') for x in row['introduced_issue_set'] if x.startswith('missing_symbol:') and x.endswith('@Qt_6_PRIVATE_API')]
        for name in missing:
            if not has(texts[str(consumer)],name,True) or not has(texts[str(old)],name,False) or has(texts[str(target)],name,False):raise ValueError('independent readelf did not reproduce old/new symbol loss')
        proof.append({'consumer':row['consumer'],'consumer_owner':row['consumer_owner'],'consumer_sha256':sha(consumer),'needed':row['needed'],'old_provider':old_provider,'old_provider_sha256':sha(old),'new_provider':row['provider'],'new_provider_sha256':sha(target),'new_provider_owner':row['provider_owner'],'new_provider_package_version':package['version'],'signed_package_sha256':package['sha256'],'missing_versioned_symbols':[name+'@Qt_6_PRIVATE_API' for name in missing],'baseline_edge_issues':[],'overlay_edge_issues':row['introduced_issue_set'],'independent_readelf':'WORKS: each consumer UND import exported by baseline and absent from selected provider'})
    for path,text in texts.items():
        (a.private/(hashlib.sha256(path.encode()).hexdigest()+'.symbols.txt')).write_text(text)
    a.output.write_text(json.dumps({'status':'BLOCKED (static Qt private ABI mismatch in separate117 proposal)','deployable':False,'execution_ready':False,'actions':[],'report_sha256':sha(a.report),'qualification_sha256':sha(a.qualification),'affected_untouched_package_owners':sorted({row['consumer_owner'] for row in proof}),'consumers':proof,'limit':'These exact mandatory symbol contracts break within the modeled dependency closure. Payloads were never run; global preloads/interposition, semantic ABI and affected runtime paths remain untested.'},indent=2)+'\n')
    print('readelf-confirmed',len(proof),'untouched Qt consumers')
if __name__=='__main__':main()
