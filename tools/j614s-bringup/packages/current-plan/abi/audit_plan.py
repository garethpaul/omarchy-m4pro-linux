#!/usr/bin/env python3
"""Static audit of hash-bound package bytes over a private read-only image restore."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import tarfile
from audit_elf import parse_elf,check_edge,check_scope
from filesystem import validate_tree,read_cache,write_cache,cache_path

IMAGE_SHA='f6ceb11ef79914eaa10cc07637c929a99afe5982d216d8b89905c86e863b2491'
IMAGE_SIZE=14344519680

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def fields(text):
    result={};key=None
    for line in text.splitlines():
        if line.startswith('%') and line.endswith('%'):key=line.strip('%');result[key]=[]
        elif line and key:result[key].append(line)
    return result

def safe_member(name):
    while name.startswith('./'):name=name[2:]
    if not name or name.startswith('/') or '..' in PurePosixPath(name).parts:raise ValueError('unsafe archive member')
    return str(PurePosixPath(name)).rstrip('/')

def virtual_path(path):
    if not path.startswith('/'):path='/'+path
    parts=[]
    for part in path.split('/'):
        if part in ('','.'):continue
        if part=='..':
            if not parts:raise ValueError('virtual path escapes root')
            parts.pop()
        else:parts.append(part)
    return '/'.join(parts)

def resolve(entries,path):
    path=virtual_path(path)
    for _ in range(40):
        parts=path.split('/');changed=False
        for i in range(len(parts)):
            prefix='/'.join(parts[:i+1]);entry=entries.get(prefix)
            if entry and 'link' in entry:
                target=entry['link'];suffix='/'.join(parts[i+1:])
                path=virtual_path((target if target.startswith('/') else '/'+posixpath.dirname(prefix)+'/'+target)+'/'+suffix)
                changed=True;break
        if not changed:return (path,entries.get(path))
    raise ValueError('virtual symlink loop')

def restore_metadata():
    return {'image_sha256':IMAGE_SHA,'image_bytes':IMAGE_SIZE,'root':256,
            'extractor_sha256':sha(Path(__file__).with_name('restore_image.py')),
            'identity_helper_sha256':sha(Path(__file__).with_name('filesystem.py'))}

def snapshot(image,root,private):
    if image.stat().st_size!=IMAGE_SIZE or sha(image)!=IMAGE_SHA:raise ValueError('immutable image identity differs')
    seal,manifest_sha=validate_tree(root,restore_metadata())
    key={'image_sha256':IMAGE_SHA,'parser_sha256':sha(Path(__file__).with_name('audit_elf.py')),
         'auditor_sha256':sha(Path(__file__)),'restore_manifest_sha256':manifest_sha,
         'tree_entries_sha256':seal['tree']['entries_sha256']}
    cache=cache_path(private,'baseline',key)
    if cache.exists():
        result=read_cache(cache)
        if result['key']!=key:raise ValueError('baseline cache key changed')
        return result,cache,seal
    owners={};installed={}
    for folder in sorted((root/'var/lib/pacman/local').iterdir()):
        if not folder.is_dir():continue
        d=fields((folder/'desc').read_text());name=d['NAME'][0];installed[name]=d['VERSION'][0]
        for path in fields((folder/'files').read_text()).get('FILES',[]):
            if not path.endswith('/'):owners[path]=name
    entries={};errors=[]
    for sub in ('usr/bin','usr/lib','usr/libexec','opt'):
        for directory,dirs,files in os.walk(root/sub,followlinks=False):
            for name in dirs+files:
                path=Path(directory)/name;relative=path.relative_to(root).as_posix()
                if path.is_symlink():entries[relative]={'link':os.readlink(path),'owner':owners.get(relative)}
                elif path.is_file():
                    with path.open('rb') as stream:
                        magic=stream.read(4)
                        if magic!=b'\x7fELF':continue
                        data=magic+stream.read()
                    try:entry={'elf':parse_elf(data),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'owner':owners.get(relative)}
                    except Exception as error:
                        errors.append({'path':relative,'reason':type(error).__name__+': '+str(error)});continue
                    entries[relative]=entry
    result={'key':key,'entries':entries,'owners':owners,'installed':installed,'errors':errors}
    validate_tree(root,restore_metadata())
    write_cache(cache,result);return result,cache,seal

def incoming(qualification,cache):
    entries={};package_files={};errors=[];architectures=Counter();collisions=[]
    for package in qualification['packages']:
        if package['status']!='WORKS' or package['cryptographic_signature']!='WORKS' or package['signed_metadata_comparison']['status']!='WORKS':raise ValueError('package qualification incomplete')
        path=cache/'payloads'/package['sha256']/package['filename']
        if path.stat().st_size!=package['expected_bytes'] or sha(path)!=package['sha256']:raise ValueError('signed payload differs')
        names=[]
        with tarfile.open(path) as archive:
            for member in archive:
                name=safe_member(member.name)
                if member.isdir() or name.startswith('.'):continue
                names.append(name);entry={'owner':package['name'],'package_sha256':package['sha256']}
                if member.issym():entry['link']=member.linkname
                elif member.islnk():entry['link']='/'+safe_member(member.linkname)
                elif member.isfile():
                    if member.size>512*1024*1024:raise ValueError('oversized package regular member')
                    stream=archive.extractfile(member);magic=stream.read(4)
                    if magic==b'\x7fELF':
                        data=magic+stream.read()
                        if len(data)!=member.size:raise ValueError('short archive member')
                        try:
                            entry.update(elf=parse_elf(data),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data));architectures[str(entry['elf']['machine'])]+=1
                        except Exception as error:errors.append({'path':name,'package':package['name'],'reason':type(error).__name__+': '+str(error)})
                    else:entry['non_elf']=True
                else:raise ValueError('unsupported special package entry')
                if name in entries:collisions.append({'path':name,'owners':[entries[name]['owner'],package['name']]})
                entries[name]=entry
        package_files[package['name']]=names
    return entries,package_files,errors,architectures,collisions

def dependency(entries,consumer_path,elf,name):
    if '/' in name:
        if not name.startswith('/'):return None,None,'relative DT_NEEDED path'
        path,entry=resolve(entries,name);return path,entry,None
    search=elf['runpath'] or elf['rpath']
    candidates=[]
    for folder in search:
        if '$' in folder.replace('${ORIGIN}','').replace('$ORIGIN',''):return None,None,'unsupported dynamic loader token'
        folder=folder.replace('${ORIGIN}','/'+posixpath.dirname(consumer_path)).replace('$ORIGIN','/'+posixpath.dirname(consumer_path))
        if not folder.startswith('/'):return None,None,'relative/current-directory RPATH'
        candidates.append(folder)
    # Retained loader configuration is separately recorded. This bounded resolver
    # only interprets direct local RPATH/RUNPATH and canonical Arch default.
    candidates.append('/usr/lib')
    for folder in candidates:
        path,entry=resolve(entries,folder+'/'+name)
        if entry is not None:return path,entry,None
    return None,None,None

def closure(entries,path,seen=None):
    seen=set() if seen is None else seen
    if path in seen:return []
    if len(seen)>4096:raise ValueError('dependency closure exceeds bound')
    seen.add(path);entry=entries.get(path,{})
    if 'elf' not in entry:return []
    result=[entry['elf']]
    for name in entry['elf']['needed']:
        child,provided,gap=dependency(entries,path,entry['elf'],name)
        if provided is not None and 'elf' in provided:result+=closure(entries,child,seen)
    return result

def edges(entries,paths):
    result={};gaps=[];export_index={}
    for path in sorted(paths):
        entry=entries.get(path,{})
        if 'elf' not in entry:continue
        elf=entry['elf']
        scope=closure(entries,path)
        required={s['name']+'@'+s['version'] for s in elf['versioned_imports'] if not s['weak']}
        available=set()
        for member in scope:
            if not all(member[k]==elf[k] for k in ('class','endian','machine')):continue
            identity=id(member)
            if identity not in export_index:export_index[identity]={s['name']+'@'+str(s['version']) for s in member['exports']}
            available.update(required & export_index[identity])
        for needed in elf['needed']:
            try:provider,provided,gap=dependency(entries,path,elf,needed)
            except ValueError as error:provider,provided,gap=None,None,str(error)
            if gap:gaps.append({'consumer':path,'needed':needed,'reason':gap})
            issues=['unresolved_needed'] if provided is None else ['provider_not_parsed_ELF'] if 'elf' not in provided else check_scope(elf,provided['elf'],needed,scope,available)
            result[(path,needed)]={'consumer':path,'consumer_owner':entry.get('owner'),'needed':needed,'provider':provider,'provider_owner':provided.get('owner') if provided else None,'issues':issues,'resolution_gap':gap}
    return result,gaps

def public_edge(row):return row

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image',type=Path,required=True);p.add_argument('--restore',type=Path,required=True)
    p.add_argument('--qualification',type=Path,required=True);p.add_argument('--payload-cache',type=Path,required=True);p.add_argument('--private',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.private.mkdir(parents=True,exist_ok=True);a.output.mkdir(parents=True,exist_ok=True)
    q=json.loads(a.qualification.read_text())
    if q['counts']!={'selected':117,'payloads_qualified':117,'failed':0} or q['deployable'] is not False or q['execution_ready'] is not False or q['actions']!=[]:raise ValueError('not exact blocked117 proposal')
    baseline,baseline_cache,seal=snapshot(a.image,a.restore,a.private);old=baseline['entries']
    cachekey={'qualification':sha(a.qualification),'parser':sha(Path(__file__).with_name('audit_elf.py')),
              'auditor':sha(Path(__file__)),'identity_helper':sha(Path(__file__).with_name('filesystem.py'))}
    cache=cache_path(a.private,'incoming',cachekey)
    if cache.exists():
        cached=read_cache(cache)
        if cached['key']!=cachekey:raise ValueError('incoming cache key changed')
        new,files,errors,architectures,collisions=cached['data']
        for row in q['packages']:
            payload=a.payload_cache/'payloads'/row['sha256']/row['filename']
            if payload.stat().st_size!=row['expected_bytes'] or sha(payload)!=row['sha256']:raise ValueError('qualified payload changed')
    else:
        new,files,errors,architectures,collisions=incoming(q,a.payload_cache)
        write_cache(cache,{'key':cachekey,'data':[new,files,errors,architectures,collisions]})
    selected=set(files)
    resulting={path:entry for path,entry in old.items() if entry.get('owner') not in selected};resulting.update(new)
    changed_sonames={e['elf']['soname'] for e in old.values() if e.get('owner') in selected and 'elf' in e and e['elf']['soname']}
    changed_sonames|={e['elf']['soname'] for e in new.values() if 'elf' in e and e['elf']['soname']}
    reverse={path for path,e in old.items() if 'elf' in e and e.get('owner') not in selected and any(n in changed_sonames for n in e['elf']['needed'])}
    incoming_paths={path for path,e in new.items() if 'elf' in e}
    before,before_gaps=edges(old,reverse|incoming_paths);after,gaps=edges(resulting,reverse|incoming_paths)
    newly=[];preserved=[]
    for key,row in after.items():
        if not row['issues']:continue
        prior=before.get(key);row=dict(row);row['baseline_issues']=prior['issues'] if prior else None
        row['introduced_issue_set']=sorted(set(row['issues'])-set(prior['issues'] if prior else []))
        (newly if row['introduced_issue_set'] else preserved).append(row)
    # Direct untouched consumers that name symbols removed by the selected provider.
    # Unversioned symbol provenance is not encoded, so these are review candidates.
    removed=[]
    for path in sorted(reverse):
        consumer=old[path]['elf'];undefined={s['name'] for s in consumer['undefined'] if not s['weak']}
        for name in consumer['needed']:
            oldpath,oldentry,gap=dependency(old,path,consumer,name);newpath,newentry,gap2=dependency(resulting,path,consumer,name)
            if not oldentry or not newentry or 'elf' not in oldentry or 'elf' not in newentry or oldentry.get('owner') not in selected:continue
            lost={s['name'] for s in oldentry['elf']['exports']}-{s['name'] for s in newentry['elf']['exports']}
            required=sorted(lost & undefined)
            if required:removed.append({'consumer':path,'consumer_owner':old[path].get('owner'),'needed':name,'old_provider':oldpath,'new_provider':newpath,'required_names_removed':required,'status':'PARTIAL: name-only removed export intersection; exact versioned contracts are checked separately'})
    configs={}
    for folder in ('etc','usr/lib'):
        for path in sorted((a.restore/folder).glob('ld.so.conf*')):
            if path.is_file() and not path.is_symlink():configs[path.relative_to(a.restore).as_posix()]=path.read_text()
            elif path.is_dir():
                for child in sorted(path.glob('*.conf')):
                    if child.is_file() and not child.is_symlink():configs[child.relative_to(a.restore).as_posix()]=child.read_text()
    report={'schema':1,'status':'PARTIAL','deployable':False,'execution_ready':False,'actions':[],
        'scope':'static versioned contracts for all incoming ELFs and bounded retained usr/bin, usr/lib, usr/libexec and opt reverse consumers; direct version nodes plus recursive dependency symbol scope; no code execution',
        'cache_provenance':{'baseline':{'filename':baseline_cache.name,'sha256':sha(baseline_cache)},'incoming':{'filename':cache.name,'sha256':sha(cache)}},
        'sealed_restore':{'manifest_sha256':baseline['key']['restore_manifest_sha256'],'tree_entries_sha256':seal['tree']['entries_sha256'],'entry_count':seal['tree']['entry_count'],'extractor_sha256':seal['extractor_sha256'],'identity_helper_sha256':seal['identity_helper_sha256']},
        'image':{'sha256':IMAGE_SHA,'bytes':IMAGE_SIZE,'root':256,'extraction':'read-only btrfs restore -S -r256; no mount'},
        'qualification_sha256':sha(a.qualification),'proposal_sha256':q['proposal_sha256'],'parser_sha256':sha(Path(__file__).with_name('audit_elf.py')),'auditor_sha256':sha(Path(__file__)),
        'counts':{'installed_packages':len(baseline['installed']),'selected_packages':len(selected),'replaced_installed_packages':len(selected & set(baseline['installed'])),'incoming_ELFs':len(incoming_paths),'incoming_ELF_machines':dict(architectures),'baseline_ELFs':sum('elf' in e for e in old.values()),'resulting_ELFs':sum('elf' in e for e in resulting.values()),'untouched_reverse_consumers':len(reverse),'changed_SONAMEs':len(changed_sonames),'direct_edges_checked':len(after),'new_or_incoming_issues':len(newly),'preserved_issue_edges':len(preserved),'parse_gaps':len(errors)+len(baseline['errors']),'resolution_gaps':len(gaps),'removed_export_name_candidates':len(removed),'file_collisions':len(collisions)},
        'incoming_non_AArch64_ELFs':[{'path':p,'owner':e['owner'],'sha256':e['sha256'],'machine':e['elf']['machine']} for p,e in new.items() if 'elf' in e and e['elf']['machine']!=183],
        'changed_shared_SONAMEs':sorted(changed_sonames),'selected_installed_versions':{name:{'baseline':baseline['installed'][name],'incoming':next(x['version'] for x in q['packages'] if x['name']==name)} for name in sorted(selected & set(baseline['installed']))},
        'loader_config':configs,'new_or_incoming_issues':newly,'preserved_issue_edges':preserved,'removed_export_name_candidates':removed,
        'parse_gaps':baseline['errors']+errors,'resolution_gaps':gaps,'file_collisions':collisions,
        'limits':['No payload execution, ld.so, ldd, QEMU, hooks, install scripts, services or installs.',
                  'Static versioned symbol availability does not establish structure layout, calling convention, semantic ABI, plugins/dlopen, GL dispatch, CPU instructions or runtime hardware correctness.',
                  'Resolver handles direct local RPATH/RUNPATH and /usr/lib only; no inherited RPATH, ld.so.cache, hwcaps, environment, auxiliary namespaces or service-dependent search context.',
                  'Versioned symbols may resolve anywhere in this consumer dependency closure; actual global application lookup scope/preloads/interposition is not modeled. Unversioned removed-name candidates are review evidence, not proof of binding.',
                  'All incoming ELF regular files are scanned; retained baseline scan covers only usr/bin, usr/lib, usr/libexec and opt. Untouched /usr/share executable bundles, scripts, home files and generated files are outside scope.',
                  'Original whole-image hook/boot effects, protected holds, actual install and recovery remain BLOCKED.'],
        'runtime_ABI':'UNTESTED','installation':'BLOCKED'}
    (a.output/'static-abi.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    (a.private/'all-edges.json').write_text(json.dumps(list(after.values()),indent=2,sort_keys=True)+'\n')
    print(json.dumps(report['counts'],indent=2))

if __name__=='__main__':main()
