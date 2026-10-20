#!/usr/bin/env python3
"""Classify exact static gaps without executing package payloads."""
import argparse
from collections import Counter
import hashlib
import json
import pickle
from pathlib import Path
import subprocess
import tarfile
from audit_plan import sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--restore',type=Path,required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.private.mkdir(parents=True,exist_ok=True)
    report=json.loads(a.report.read_text());q=json.loads(a.qualification.read_text());packages={x['name']:x for x in q['packages']}
    gaps=[]
    for row in report['parse_gaps']:
        path=a.restore/row['path']
        if path.is_symlink() or not path.is_file():raise ValueError('gap source not physical regular image data')
        with path.open('rb') as stream:data=stream.read(64)
        machine=int.from_bytes(data[18:20],'little');abi=data[7]
        if not (data[:4]==b'\x7fELF' and machine==0 and abi==255 and row['path'].startswith('usr/lib/guile/')):raise ValueError('unexpected unclassified parse gap')
        gaps.append({'path':row['path'],'elf_machine':machine,'osabi':abi,'classification':'Guile virtual-machine ELF; native ELF dynamic contract not interpreted'})
    foreign=[]
    for row in report['incoming_non_AArch64_ELFs']:
        package=packages[row['owner']];payload=a.cache/'payloads'/package['sha256']/package['filename']
        if sha(payload)!=package['sha256']:raise ValueError('qualified foreign asset payload differs')
        with tarfile.open(payload) as archive:
            member=archive.getmember(row['path'])
            if not member.isfile() or member.size>16*1024*1024:raise ValueError('foreign asset not bounded regular data')
            data=archive.extractfile(member).read()
            if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('foreign data differs')
            target=a.private/(row['sha256']+'.elf');target.write_bytes(data)
            header=subprocess.run(['readelf','--file-header',str(target)],capture_output=True,text=True,check=True)
            if 'Advanced Micro Devices X86-64' not in header.stdout:raise ValueError('independent machine check disagrees')
            link=archive.getmember('etc/skel/.local/share/nvim/mason/bin/shfmt')
            receipt=archive.getmember('etc/skel/.local/share/nvim/mason/packages/shfmt/mason-receipt.json');receipt_data=archive.extractfile(receipt).read(8193)
            if len(receipt_data)>8192 or not link.issym():raise ValueError('unexpected Mason template metadata')
            receipt_json=json.loads(receipt_data)
            foreign.append({**row,'signed_package_version':package['version'],'signed_package_architecture':package['architecture'],'signed_package_sha256':package['sha256'],'archive_mode':oct(member.mode),'archive_bytes':member.size,'template_link':{'path':link.name,'target':link.linkname},'receipt_sha256':hashlib.sha256(receipt_data).hexdigest(),'receipt_shfmt_link':receipt_json['links']['bin']['shfmt'],'independent_machine_check':'GNU readelf: Advanced Micro Devices X86-64','status':'PARTIAL: architecture-specific Mason asset in architecture=any ARM proposal; target0644; dormant /etc/skel data, not proof existing account executes it'})
    direct=[]
    for row in report['new_or_incoming_issues']:
        if row['issues']!=['unresolved_needed']:continue
        owner=row['consumer_owner'];info=packages[owner]['signed_pkginfo'] if owner in packages else {}
        direct.append({**row,'declared_dependencies':info.get('depend',[]),'declared_optional_dependencies':info.get('optdepend',[]),'qualification':'PARTIAL: required direct ELF lookup unresolved in modeled filesystem; plugin/optional feature use and runtime context are not inferred'})
    # Own parser caches contain no vendor code and stay ignored; input hashes are
    # recorded so this cross-owner check is reproducible after the static audit.
    baseline_cache=a.private/'baseline.pickle';incoming_cache=a.private/'incoming.pickle'
    baseline=pickle.loads(baseline_cache.read_bytes());incoming=pickle.loads(incoming_cache.read_bytes())['data'][0]
    selected={r['name'] for r in q['packages']};owner_conflicts=[]
    for path,entry in incoming.items():
        owner=baseline['owners'].get(path)
        if owner is not None and owner not in selected and owner!=entry['owner']:
            owner_conflicts.append({'path':path,'retained_owner':owner,'incoming_owner':entry['owner'],'incoming_signed_conflicts':packages[entry['owner']]['signed_pkginfo'].get('conflict',[]),'incoming_signed_provides':packages[entry['owner']]['signed_pkginfo'].get('provides',[]),'incoming_signed_replaces':packages[entry['owner']]['signed_pkginfo'].get('replaces',[]),'status':'UNTESTED removal/replacement transaction: retained name differs; signed conflicts do not by themselves prove an accepted removal'})
    result={'status':'PARTIAL','deployable':False,'execution_ready':False,'actions':[],'filesystem_model':'PARTIAL: same-name selected-package overlay; name-changing conflicts/removals are unresolved. Do not treat this as the final intended installation filesystem.','unchanged_package_path_owner_conflicts':owner_conflicts,'own_parser_cache_sha256':{'baseline':sha(baseline_cache),'incoming':sha(incoming_cache)},'static_report_sha256':sha(a.report),'qualification_sha256':sha(a.qualification),'parse_gap_classification':{'count':len(gaps),'machine_counts':dict(Counter(str(x['elf_machine']) for x in gaps)),'all_guile_VM_ELF':True,'native_host_parse_error_count_in_scanned_scope':0,'scope':'Guile VM bytecode remains unqualified; no native CPU binary was silently treated as compatible'},'foreign_assets':foreign,'unresolved_direct_edges':direct,'limitations':['Unresolved plugin dependencies can represent unavailable optional features. The direct consumer need is recorded without asserting every package entry point fails.','Exact Qt old/new private ABI loss is separately proven with readelf. No runtime ABI or installation qualification follows.']}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print('classified',len(gaps),'Guile VM gaps,',len(foreign),'foreign asset,',len(direct),'unresolved direct edges')
if __name__=='__main__':main()
