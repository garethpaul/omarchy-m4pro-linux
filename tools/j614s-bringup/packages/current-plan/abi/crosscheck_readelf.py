#!/usr/bin/env python3
"""Independently compare selected actual ELF contracts with GNU readelf output."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
from audit_elf import parse_elf
from audit_plan import sha,safe_member

def inspect(path,label,private):
    data=path.read_bytes();parsed=parse_elf(data)
    run=subprocess.run(['readelf','--wide','--file-header','--dynamic','--version-info',str(path)],check=True,capture_output=True,text=True)
    if run.stderr:raise ValueError('readelf warnings: '+run.stderr)
    text=run.stdout
    needed=re.findall(r'\(NEEDED\).*?\[([^\]]+)\]',text)
    soname=re.findall(r'\(SONAME\).*?\[([^\]]+)\]',text)
    if needed!=parsed['needed'] or soname!=([parsed['soname']] if parsed['soname'] else []):raise ValueError('readelf dynamic contract disagrees')
    if parsed['machine']!=183 or not re.search(r'Machine:\s+AArch64',text):raise ValueError('not actual AArch64')
    required={};defined=[];mode=None;filename=None
    for line in text.splitlines():
        if line.startswith('Version needs section'):mode='need'
        elif line.startswith('Version definition section'):mode='def'
        elif line.startswith('Version symbols section'):mode=None
        if mode=='need':
            file=re.search(r'File: (\S+)\s+Cnt:',line)
            if file:filename=file.group(1);required[filename]=[]
            name=re.search(r'Name: (\S+)\s+Flags:',line)
            if name:required[filename].append(name.group(1))
        elif mode=='def':
            name=re.search(r'Index:\s+\d+\s+Cnt:\s+\d+\s+Name: (\S+)',line)
            if name:defined.append(name.group(1))
    required={k:sorted(set(v)) for k,v in required.items()}
    if required!=parsed['version_requirements'] or sorted(set(defined))!=parsed['version_definitions']:raise ValueError('readelf version contracts disagree')
    output=private/(hashlib.sha256(label.encode()).hexdigest()+'.readelf.txt');output.write_text(text)
    return {'path':label,'elf_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'machine':183,'needed':needed,'soname':parsed['soname'],'required_version_node_count':sum(map(len,required.values())),'defined_version_node_count':len(defined),'independent_readelf_output_sha256':sha(output),'result':'WORKS: static parser and GNU readelf agree on machine, NEEDED, SONAME and version node requirements/exports'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--restore',type=Path,required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.private.mkdir(parents=True,exist_ok=True)
    q=json.loads(a.qualification.read_text());rows=[]
    for package in q['packages']:
        if package['name'] not in ('marisa','graphicsmagick','imagemagick','postgresql-libs'):continue
        path=a.cache/'payloads'/package['sha256']/package['filename']
        if sha(path)!=package['sha256']:raise ValueError('qualified payload differs')
        with tarfile.open(path) as archive:
            for member in archive:
                name=safe_member(member.name)
                if not member.isfile() or not name.startswith('usr/lib/lib') or '.so.' not in name:continue
                if member.size>128*1024*1024:raise ValueError('oversized independent-check ELF')
                stream=archive.extractfile(member);magic=stream.read(4)
                if magic!=b'\x7fELF':continue
                data=magic+stream.read();target=a.private/(hashlib.sha256(data).hexdigest()+'.elf');target.write_bytes(data)
                row=inspect(target,name,a.private);row.update(package=package['name'],package_version=package['version'],package_sha256=package['sha256']);rows.append(row)
    for path in ('usr/lib/libc.so.6','usr/lib/libstdc++.so.6.0.35'):
        target=a.restore/path
        if not target.exists():continue
        if target.is_symlink():raise ValueError('baseline crosscheck must name physical regular file')
        row=inspect(target,'baseline/'+path,a.private);row['source']='retained immutable image';rows.append(row)
    a.output.write_text(json.dumps({'status':'WORKS (static crosscheck only)','deployable':False,'execution_ready':False,'actions':[],'tool':subprocess.run(['readelf','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0],'qualification_sha256':sha(a.qualification),'rows':rows},indent=2)+'\n')
    print('crosschecked',len(rows),'actual AArch64 ELF files')
if __name__=='__main__':main()
