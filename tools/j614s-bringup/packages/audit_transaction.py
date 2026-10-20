#!/usr/bin/env python3
"""Offline package payload verification and static script/hook inventory. Never installs."""
import argparse
import base64
import concurrent.futures
import datetime
import hashlib
import fnmatch
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request

SOURCE_COMMIT = '4941c67dbab65ec9bd903c337863c10a51741542'
SOURCE_HASHES = {
 'verify_editor_packages.py': 'e9c54eac41a99f3b156a774993537673c71caa7a4f706683c444f5992367c912',
 'evidence/pacman-print-resolution.json': 'b46e656795b597b6d5182e5f29cb611fe25f525d868ac5da246d2d7be4558aea',
 'package_audit.py': 'd063181d5c821f8b5cd6a62c3c6ff99288816fe7ba283d5e6f4feaf904bfc24b',
 'arm_package_plan.py': 'd4b71f21cb44d683591486c6237da157e2aab478a913a52d703267bb68da5156',
}
BAD_SIG = {'BADSIG','ERRSIG','NO_PUBKEY','EXPSIG','EXPKEYSIG','REVKEYSIG','KEYEXPIRED','SIGEXPIRED'}
BOOT = re.compile(r'(?i)(m1n1|initramfs|mkinitcpio|dracut|limine|asahi-bless|firmware|/boot(?:/|\b)|/efi(?:/|\b)|\bbless\b|linux-modules|depmod|aurora)')
HOOK_ROOTS = ('usr/share/libalpm/hooks/', 'etc/pacman.d/hooks/')

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()

def load_tools(source):
    for path, expected in SOURCE_HASHES.items():
        if sha(source / path) != expected: raise ValueError('pinned source changed: ' + path)
    sys.dont_write_bytecode=True
    sys.path.insert(0, str(source.resolve()))
    return importlib.import_module('package_audit').repository_records, importlib.import_module('arm_package_plan').protected

def pin_rows(plan, provenance, source, records, protected):
    if plan.get('schema') != 1 or plan.get('deployable') is not False or plan.get('actions') != []:
        raise ValueError('plan must remain explicitly non-deployable and action-free')
    rows = plan['resolved_transaction']
    if len(rows) != plan['transaction_package_count'] or len({r['name'] for r in rows}) != len(rows):
        raise ValueError('transaction count or duplicate identity')
    pinned = {r['name']: r['sha256'] for r in plan['repositories']}
    dbs = {}
    for repo, digest in pinned.items():
        db = source / 'evidence/repositories' / (repo + '.db')
        if sha(db) != digest or provenance[repo]['sha256'] != digest:
            raise ValueError('repository digest mismatch: ' + repo)
        dbs[repo] = {f['NAME'][0]: f for f in records(db, [])}
    selected = []
    for row in rows:
        if protected(row['name']): raise ValueError('protected boot/system/graphics selection: ' + row['name'])
        if row['architecture'] not in ('aarch64', 'any'): raise ValueError('architecture rejected')
        filename = row['filename']
        if Path(filename).name != filename or filename in ('.','..') or '\\' in filename:
            raise ValueError('unsafe package filename')
        fields = dbs[row['repository']][row['name']]
        for key, field in [('name','NAME'),('version','VERSION'),('architecture','ARCH'),('filename','FILENAME'),('sha256','SHA256SUM')]:
            if fields.get(field) != [row[key]]: raise ValueError('plan/DB identity mismatch: '+key)
        if not re.fullmatch('[0-9a-f]{64}', row['sha256']): raise ValueError('invalid SHA256')
        size = int(fields['CSIZE'][0])
        if size <= 0 or size > 2**31: raise ValueError('invalid payload size')
        selected.append((row, fields, urllib.parse.urljoin(provenance[row['repository']]['url'], urllib.parse.quote(filename))))
    return selected

def key_material(keydir, cache):
    home = cache / 'gnupg'
    home.mkdir(exist_ok=True, mode=0o700)
    result = {'files':{}, 'anchors':{}, 'revoked':set(), 'rings':[]}
    for path in sorted(keydir.glob('*.gpg')):
        name = path.stem
        result['files'][path.name] = sha(path)
        binary = cache / (name + '-binary.gpg')
        if path.read_bytes().startswith(b'-----BEGIN PGP'):
            cmd = ['gpg','--homedir',str(home),'--batch','--yes','--dearmor','--output',str(binary),str(path)]
            subprocess.run(cmd, check=True, capture_output=True)
        else: binary.write_bytes(path.read_bytes())
        result['rings'].append(str(binary.resolve()))
        trusted = keydir / (name+'-trusted')
        revoked = keydir / (name+'-revoked')
        for policy in (trusted,revoked): result['files'][policy.name] = sha(policy)
        for line in trusted.read_text().splitlines():
            fpr = line.split(':')[0].strip()
            if re.fullmatch('[A-F0-9]{40}',fpr): result['anchors'].setdefault(fpr,[]).append(name)
        for line in revoked.read_text().splitlines():
            fpr = line.split('#')[0].split(':')[0].strip()
            if re.fullmatch('[A-F0-9]{40}',fpr): result['revoked'].add(fpr)
    if len(result['rings']) != 4: raise ValueError('expected four retained image public keyrings')
    return result

def signature_result(returncode, output, keys):
    statuses = [line.removeprefix('[GNUPG:] ').split() for line in output.splitlines() if line.startswith('[GNUPG:] ')]
    tags = {r[0] for r in statuses if r}
    valids = [r for r in statuses if r and r[0]=='VALIDSIG']
    if returncode or tags & BAD_SIG or len(valids)!=1: raise ValueError('PGP verification rejected: '+','.join(sorted(tags & BAD_SIG)))
    v = valids[0]
    if len(v)<10: raise ValueError('malformed VALIDSIG')
    signer, primary = v[1], v[10] if len(v)>10 else v[1]
    if signer in keys['revoked'] or primary in keys['revoked']: raise ValueError('retained image revocation')
    anchors = keys['anchors'].get(primary,[])
    return {'cryptographic_signature':'WORKS', 'signing_fingerprint':signer,'primary_fingerprint':primary,
            'hash_algorithm':int(v[8]),'retained_explicit_anchor_keyrings':anchors,
            'trust':'WORKS (explicit retained-image anchor)' if anchors else 'BLOCKED (signer trust path not established)',
            'trust_scope':'gpgv cryptographic verification plus retained -trusted membership; no host trustdb or fabricated local signing'}

def hook_data(path, data):
    text = data.decode('utf-8', errors='strict')
    sections = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        if line.startswith('[') and line.endswith(']'): sections.append({'section':line[1:-1],'fields':{}})
        elif sections:
            key, sep, val = line.partition('=')
            sections[-1]['fields'].setdefault(key.strip(),[]).append(val.strip() if sep else True)
        else: raise ValueError('hook content before section')
    return {'path':path,'sha256':hashlib.sha256(data).hexdigest(),'text':text,'sections':sections,
            'boot_sensitive_text':bool(BOOT.search(text)), 'execution':'UNTESTED; inspected as data only'}

def pkginfo(text):
    result = {}
    for line in text.splitlines():
        if ' = ' in line and not line.startswith('#'):
            key,value=line.split(' = ',1); result.setdefault(key,[]).append(value)
    return result

def archive_data(path, row):
    info = None; scripts=[]; hooks=[]; names=[]; seen=set(); boot_paths=[]
    with tarfile.open(path) as archive:
        for member in archive:
            name=member.name.removeprefix('./')
            parts=PurePosixPath(name).parts
            if name.startswith('/') or '..' in parts or name in seen: raise ValueError('unsafe/duplicate archive path')
            seen.add(name); names.append(name)
            if BOOT.search(name): boot_paths.append(name)
            if name=='.PKGINFO' or name=='.INSTALL' or (name.endswith('.hook') and name.startswith(HOOK_ROOTS)):
                if not member.isfile(): raise ValueError('script/hook metadata is not regular data')
                limit=1048576 if name in ('.PKGINFO','.INSTALL') else 262144
                if member.size>limit: raise ValueError('oversized script/hook metadata')
                data=archive.extractfile(member).read(limit+1)
                if len(data)!=member.size: raise ValueError('short archive data')
                if name=='.PKGINFO': info=pkginfo(data.decode())
                elif name=='.INSTALL': scripts.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'text':data.decode(),'boot_sensitive_text':bool(BOOT.search(data.decode()))})
                else: hooks.append(hook_data(name,data))
    for key, expected in [('pkgname',row['name']),('pkgver',row['version']),('arch',row['architecture'])]:
        if info is None or info.get(key)!=[expected]: raise ValueError('signed .PKGINFO identity mismatch: '+key)
    return {'pkginfo_identity':'WORKS','install_scripts':scripts,'hooks':hooks,'payload_paths':names,'boot_sensitive_paths':boot_paths}

def download(url, target, size, digest):
    if target.exists() and target.stat().st_size==size and sha(target)==digest: return 'verified cached payload'
    part=target.with_suffix(target.suffix+'.partial')
    try:
        with urllib.request.urlopen(url,timeout=60) as response, part.open('wb') as stream:
            count=0
            while block:=response.read(1048576):
                count+=len(block)
                if count>size: raise ValueError('payload larger than pinned CSIZE')
                stream.write(block)
        if count!=size or sha(part)!=digest: raise ValueError('payload size/SHA256 mismatch')
        part.replace(target)
        return 'downloaded pinned payload'
    finally:
        part.unlink(missing_ok=True)

def audit_one(item, cache, keys):
    row,fields,url=item
    result={**row,'expected_bytes':int(fields['CSIZE'][0]),'url':url,'status':'BLOCKED','signature_source':'UNTESTED'}
    try:
        folder=cache/'payloads'/row['sha256']; folder.mkdir(parents=True,exist_ok=True)
        path=folder/row['filename']
        result['retrieval']=download(url,path,int(fields['CSIZE'][0]),row['sha256'])
        result['bytes']=path.stat().st_size
        sig=path.with_name(path.name+'.sig')
        if fields.get('PGPSIG'):
            signature=base64.b64decode(fields['PGPSIG'][0],validate=True)
            result['signature_source']='PGPSIG in exact pinned downloaded repository DB'
        else:
            result['signature_source']='detached signature downloaded from pinned payload URL + .sig; authenticated by payload verification'
            result['signature_url']=url+'.sig'
            with urllib.request.urlopen(url+'.sig',timeout=60) as response:
                signature=response.read(16385)
            if not signature or len(signature)>16384: raise ValueError('invalid detached signature size')
        sig.write_bytes(signature)
        result['signature_sha256']=sha(sig)
        command=['gpgv','--homedir',str(cache/'gnupg'),'--status-fd','1']
        for ring in keys['rings']: command+=['--keyring',ring]
        checked=subprocess.run(command+[str(sig),str(path)],capture_output=True,text=True)
        result['gpg_status']=checked.stdout.splitlines()
        result.update(signature_result(checked.returncode,checked.stdout,keys))
        result.update(archive_data(path,row))
        result['status']='WORKS' if result['retained_explicit_anchor_keyrings'] else 'BLOCKED'
    except Exception as error:
        result['failure']=type(error).__name__+': '+str(error)
    return result

def baseline_hooks(root):
    effective={}; inventory=[]
    for relative in HOOK_ROOTS:
        folder=root/relative
        if not folder.is_dir(): raise ValueError('missing extracted baseline hook directory')
        for path in sorted(folder.glob('*.hook')):
            rel=path.relative_to(root).as_posix()
            if path.is_symlink():
                target=os.readlink(path)
                row={'path':rel,'symlink':target,'disabled':target=='/dev/null'}
                if target!='/dev/null': raise ValueError('unresolved baseline hook symlink')
            else: row=hook_data(rel,path.read_bytes())
            inventory.append(row); effective[path.name]=row
    return {'inventory':inventory,'effective':list(effective.values()),'scope':'verified retained OS image root256; not live target'}

def image_snapshot(root, source):
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest.get('image_sha256')!='f6ceb11ef79914eaa10cc07637c929a99afe5982d216d8b89905c86e863b2491' or manifest.get('root')!=256 or manifest.get('image_bytes')!=14344519680:
        raise ValueError('unqualified baseline image identity')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p!=root/'manifest.json' and (p.is_file() or p.is_symlink())}
    if actual!=set(manifest['entries']): raise ValueError('unmanifested or missing image extraction data')
    for relative,entry in manifest['entries'].items():
        path=root/relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts: raise ValueError('unsafe image manifest path')
        if 'symlink' in entry:
            if not path.is_symlink() or os.readlink(path)!=entry['symlink']: raise ValueError('image symlink mismatch')
        elif path.is_symlink() or sha(path)!=entry['sha256']: raise ValueError('image extraction digest mismatch')
    for path in (source/'evidence/package-root/usr/share/pacman/keyrings').iterdir():
        if sha(path)!=sha(root/'usr/share/pacman/keyrings'/path.name): raise ValueError('C keyring differs from verified image')
    return manifest

def hook_matches(hook, packages, installed):
    matches=[]
    for section in hook.get('sections',[]):
        if section['section']!='Trigger': continue
        f=section['fields'];kind=f.get('Type',[None])[0];operations=f.get('Operation',[]);patterns=f.get('Target',[])
        for row in packages:
            operation='Upgrade' if row['name'] in installed else 'Install'
            if operation not in operations: continue
            values=[row['name']] if kind=='Package' else row.get('payload_paths',[]) if kind=='Path' else []
            positive=[p for p in patterns if not p.startswith('!')];negative=[p[1:] for p in patterns if p.startswith('!')]
            found=[v for v in values if any(fnmatch.fnmatchcase(v,p) for p in positive) and not any(fnmatch.fnmatchcase(v,p) for p in negative)]
            if found:matches.append({'package':row['name'],'operation':operation,'type':kind,'matching_values':found})
    return {'path':hook['path'],'matches':matches,'would_match_incoming_paths':bool(matches),
            'limitations':'static incoming payload paths only; old upgrade/removal paths, runtime Depends and hook failure effects remain unqualified'}

def execution_gate(packages, baseline, matches):
    """Name holds alone cannot qualify a transaction with boot-related path effects."""
    indexed={h['path']:h for h in baseline['effective']}
    effects=[]
    for match in matches:
        hook=indexed[match['path']]
        if not match['would_match_incoming_paths'] or not hook.get('boot_sensitive_text'):continue
        commands=[cmd for section in hook.get('sections',[]) if section['section']=='Action'
                  for cmd in section['fields'].get('Exec',[])]
        generates=any(re.search(r'(?:limine-mkinitcpio-install|(?:^|/)mkinitcpio(?:\s|$)|update-m1n1|limine-install|omarchy-mac-limine-deploy)',cmd) for cmd in commands)
        effects.append({'effective_hook':hook['path'],'hook_sha256':hook['sha256'],'exec':commands,
                        'effect':'boot_artifact_generation' if generates else 'boot_related_hook_requires_review',
                        'incoming_matches':match['matches'],'execution':'UNTESTED; static retained-image evidence only'})
    blockers=[]
    failed=[r['name'] for r in packages if r['status']!='WORKS']
    if failed:blockers.append({'reason':'unqualified_payloads','packages':failed})
    if effects:blockers.append({'reason':'incoming_payload_triggers_boot_related_hooks','hooks':[e['effective_hook'] for e in effects]})
    blockers.append({'reason':'live_recovery_and_script_hook_execution_unqualified'})
    return {'execution_ready':False,'boot_effects':effects,'execution_blockers':blockers,
            'name_only_protection_sufficient':False}

def executable_inventory(root, manifest):
    rows=[]
    for relative in manifest['exec_first_argv']:
        path=root/relative
        row={'path':relative,'execution':'UNTESTED; static inspection only'}
        if path.is_symlink(): row['status']='BLOCKED (symlink target not followed)';row['symlink']=os.readlink(path)
        elif not path.is_file(): row['status']='BLOCKED (not extracted)'
        else:
            row['sha256']=sha(path);data=path.read_bytes()
            row['bytes']=len(data)
            if data.startswith(b'#!') and len(data)<=1048576:
                text=data.decode();row['text']=text;row['boot_sensitive_text']=bool(BOOT.search(text));row['status']='WORKS (script bytes inspected)'
            else: row['status']='PARTIAL (binary identity only)'
        rows.append(row)
    return rows

def write_evidence(path, result):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(result,indent=2)+'\n')
    temporary.replace(path)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True); p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--image-hooks',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=6)
    a=p.parse_args(); a.cache.mkdir(parents=True,exist_ok=True)
    records,protected=load_tools(a.source)
    plan=json.loads((a.source/'evidence/pacman-print-resolution.json').read_text())
    provenance=json.loads((a.source/'evidence/repositories/provenance.json').read_text())
    items=pin_rows(plan,provenance,a.source,records,protected)
    manifest=image_snapshot(a.image_hooks,a.source)
    keys=key_material(a.source/'evidence/package-root/usr/share/pacman/keyrings',a.cache)
    baseline=baseline_hooks(a.image_hooks)
    # Read exact installed package NAME instead of inferring hyphenated versions.
    from package_audit import desc_fields
    installed={desc_fields(path.read_text())['NAME'][0] for path in (a.source/'evidence/package-root/var/lib/pacman/local').glob('*/desc')}
    if not installed: raise ValueError('installed baseline unavailable')
    local_hashes={path.parent.name:sha(path) for path in (a.source/'evidence/package-root/var/lib/pacman/local').glob('*/desc')}
    result={'installed_image_local_description_digest':hashlib.sha256(json.dumps(local_hashes,sort_keys=True).encode()).hexdigest(),
            'installed_image_local_description_count':len(local_hashes),'schema':1,'source_commit':SOURCE_COMMIT,'source_hashes':SOURCE_HASHES,'deployable':False,'execution_ready':False,'audit_complete':False,'actions':[],
            'scope':'host-only payload verification/static data inspection; no install, target, service, script or hook execution',
            'keyring_files':keys['files'],'image_manifest':manifest,'baseline_hooks':baseline,'baseline_exec_data':executable_inventory(a.image_hooks,manifest),'packages':[]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        for row in pool.map(lambda item:audit_one(item,a.cache,keys),items):
            result['packages'].append(row)
            print(row['name']+': '+row['status']+((' '+row['failure']) if 'failure' in row else ''),flush=True)
            write_evidence(a.output,result)
    result['baseline_hook_matches']=[hook_matches(h,result['packages'],installed) for h in baseline['effective']]
    result.update(execution_gate(result['packages'],baseline,result['baseline_hook_matches']))
    for row in result['packages']:
        paths=row.pop('payload_paths',[])
        row['archive_path_count']=len(paths)
        row['archive_paths_sha256']=hashlib.sha256(json.dumps(paths,separators=(',',':')).encode()).hexdigest()
    result['counts']={'selected':len(items),'qualified':sum(r['status']=='WORKS' for r in result['packages']),
                      'failed':sum(r['status']!='WORKS' for r in result['packages'])}
    result['status']='WORKS (payload audit only)' if not result['counts']['failed'] else 'PARTIAL'
    result['installation_status']='BLOCKED (held protected requests; live recovery, script/hook execution and resulting system unqualified)'
    result['audit_complete']=True
    result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    write_evidence(a.output,result)

if __name__=='__main__': main()
