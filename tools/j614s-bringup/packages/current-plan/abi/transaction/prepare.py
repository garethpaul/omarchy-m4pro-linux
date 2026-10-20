#!/usr/bin/env python3
"""Prepare a frozen package metadata transaction with real conflicts; never commit."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from filesystem import tree_identity
from audit_plan import sha
import baseline as baseline_identity
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from propose import original_inputs,ORDER

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--proposal',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True)
    p.add_argument('--repositories',type=Path,required=True);p.add_argument('--scenario',type=Path,required=True)
    p.add_argument('--baseline-qualification',type=Path,default=baseline_identity.default_qualification())
    p.add_argument('--private',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.private.exists():raise ValueError('new isolated preparation directory required')
    records,protected,resolver,planner,old_review=original_inputs(a.source)
    proposal=json.loads(a.proposal.read_text());qualification=json.loads(a.qualification.read_text());scenario=json.loads(a.scenario.read_text())
    if qualification['proposal_sha256']!=sha(a.proposal) or not qualification['audit_complete'] or qualification['deployable'] is not False or qualification['execution_ready'] is not False or qualification['actions']!=[]:raise ValueError('qualified blocked proposal binding differs')
    if proposal['protected_installed_pins']!=old_review['protected_installed_pins'] or proposal['held_original_requests']!=old_review['held_requests']:raise ValueError('20 installed/four request holds changed')
    rows=proposal['resolved_transaction'];qualified={r['name']:r for r in qualification['packages']}
    if len(rows)!=len(qualified) or any(r['status']!='WORKS' or r['cryptographic_signature']!='WORKS' or r['signed_metadata_comparison']['status']!='WORKS' for r in qualified.values()):raise ValueError('payload qualification incomplete')
    repos=[];metadata={}
    if [r['name']for r in proposal['repositories']]!=list(ORDER):raise ValueError('repository order differs')
    for row in proposal['repositories']:
        path=a.repositories/(row['name']+'.db')
        if sha(path)!=row['sha256']:raise ValueError('frozen DB changed')
        repos.append((row['name'],path));metadata[row['name']]={r['NAME'][0]:r for r in records(path,[])}
    for row in rows:
        if protected(row['name']):raise ValueError('protected target rejected')
        signed=qualified[row['name']]
        if any(signed[key]!=row[key] for key in ('name','version','filename','repository','sha256','architecture')):raise ValueError('proposal/signed payload identity mismatch')
        fields=metadata[row['repository']][row['name']]
        if fields['VERSION']!=[row['version']] or fields['SHA256SUM']!=[row['sha256']]:raise ValueError('exact metadata target mismatch')
    baseline=a.source/'evidence/package-root/var/lib/pacman/local'
    complete_baseline=baseline_identity.verify(baseline,a.baseline_qualification)
    from package_audit import desc_fields
    installed_fields={desc_fields(path.read_text())['NAME'][0]:desc_fields(path.read_text())for path in baseline.glob('*/desc')}
    installed={desc_fields(path.read_text())['NAME'][0]:{'version':desc_fields(path.read_text())['VERSION'][0],'description_sha256':sha(path)}for path in baseline.glob('*/desc')}
    for name,pin in proposal['protected_installed_pins'].items():
        if installed.get(name)!={'version':pin['version'],'description_sha256':pin['description_sha256']}:raise ValueError('protected installed baseline changed')
    if scenario.get('schema')!=1 or scenario.get('deployable') is not False or scenario.get('actions')!=[]:raise ValueError('requires blocked metadata-only removal scenario')
    removals=scenario['allow_conflict_removals'];seen=set()
    for row in removals:
        new,old=row['incoming'],row['retained']
        if new not in qualified or old not in installed or protected(new) or protected(old) or old in proposal['protected_installed_pins'] or (new,old) in seen:raise ValueError('unqualified/protected removal scenario')
        signed_conflicts=qualified[new]['signed_pkginfo'].get('conflict',[])
        retained_names={old}|{re.split(r'[<>=]',p,maxsplit=1)[0]for p in installed_fields[old].get('PROVIDES',[])}
        if not any(re.split(r'[<>=]',p,maxsplit=1)[0] in retained_names for p in signed_conflicts):raise ValueError('removal lacks signed package conflict against retained name/provides; libalpm still checks exact versions')
        seen.add((new,old))
    a.private.mkdir(parents=True);(a.private/'root').mkdir();(a.private/'db').mkdir();(a.private/'db/sync').mkdir();shutil.copytree(baseline,a.private/'db/local')
    baseline_identity.assert_identity(a.private/'db/local',complete_baseline)
    for folder in ('root','db'):(a.private/folder/'.abi-prepare-only').write_text('metadata-only\n')
    for name,path in repos:shutil.copyfile(path,a.private/'db/sync'/(name+'.db'))
    index,_=planner.index_repositories(repos)
    ignored=sorted({row['name']for row in index.values()if protected(row['name'])}|set(proposal['protected_installed_pins']))
    (a.private/'protected').write_text('\n'.join(ignored)+'\n')
    (a.private/'targets').write_text(''.join(r['repository']+'\t'+r['name']+'\t'+r['version']+'\n'for r in rows))
    (a.private/'scenario').write_text(''.join(r['incoming']+'\t'+r['retained']+'\n'for r in removals))
    (a.private/'repositories').write_text('\n'.join(ORDER)+'\n')
    source=Path(__file__).with_name('prepare.c');binary=a.private/'prepare'
    compile_args=['cc','-std=c11','-D_GNU_SOURCE','-Wall','-Wextra','-Werror',str(source),'-lalpm','-o',str(binary)]
    compile_run=subprocess.run(compile_args,capture_output=True,text=True);(a.private/'compile.log').write_text(compile_run.stdout+compile_run.stderr)
    if compile_run.returncode:raise ValueError('strict prepare-only helper compilation failed')
    imports=subprocess.run(['nm','-u',str(binary)],capture_output=True,text=True,check=True).stdout
    if 'alpm_trans_prepare' not in imports or any(n in imports for n in ('alpm_trans_commit','alpm_sync_sysupgrade','alpm_pkg_load','execve')):raise ValueError('unexpected helper imports')
    before=tree_identity(a.private/'db/local')
    run=subprocess.run([str(binary.resolve()),*[str((a.private/x).resolve())for x in ('root','db','targets','protected','scenario','repositories')]],capture_output=True,text=True)
    (a.private/'stdout.json').write_text(run.stdout);(a.private/'stderr.log').write_text(run.stderr)
    if run.returncode:raise ValueError('prepare-only metadata helper failed; inspect private stderr')
    result=json.loads(run.stdout)
    baseline_identity.assert_identity(a.private/'db/local',complete_baseline)
    if tree_identity(a.private/'db/local')!=before:raise ValueError('metadata preparation changed local DB')
    if result['flags']!=((1<<17)|(1<<13)) or not result['dependency_checks'] or not result['conflict_checks'] or result['committed'] or result['fetch_attempts']:raise ValueError('preparation flags/side effects differ')
    expected={(r['repository'],r['name'],r['version'])for r in rows};actual={(r['repository'],r['name'],r['version'])for r in result['add']}
    result.update(status='PARTIAL' if result['prepared'] and actual==expected else 'BLOCKED',deployable=False,execution_ready=False,actions=[],proposal_sha256=sha(a.proposal),qualification_sha256=sha(a.qualification),scenario_sha256=sha(a.scenario),helper_source_sha256=sha(source),helper_binary_sha256=sha(binary),wrapper_sha256=sha(Path(__file__)),header_sha256=sha(Path('/usr/include/alpm.h')),binary_imports_sha256=__import__('hashlib').sha256(imports.encode()).hexdigest(),protected_installed_pin_count=len(proposal['protected_installed_pins']),held_request_count=len(proposal['held_original_requests']),protected_names_ignored=len(ignored),local_db_before_after_entries_sha256=before['entries_sha256'],baseline_description_digest=complete_baseline['digest'],baseline_description_count=complete_baseline['count'],baseline_qualification_sha256=sha(a.baseline_qualification),baseline_identity_helper_sha256=sha(Path(baseline_identity.__file__)),target_set_matches_qualified_plan=actual==expected,extra_targets=[dict(repository=r,name=n,version=v)for r,n,v in sorted(actual-expected)],missing_targets=[dict(repository=r,name=n,version=v)for r,n,v in sorted(expected-actual)],signature_policy='Required DatabaseOptional; frozen DBs and externally qualified signed payload identities; no signature bypass/key import',limits=['Metadata dependency/conflict preparation only; no alpm_trans_commit, sysupgrade, payload loading, downloads, package execution or host/target changes.','File conflicts, hooks, actual install and runtime ABI remain unqualified.','Allowed answers are a separate hypothetical removal scenario, not authorization for real removal.'])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],'prepared',result['prepared'],'add',len(result['add']),'remove',len(result['remove']))
if __name__=='__main__':main()
