#!/usr/bin/env python3
"""Model exact prepared additions/removals without changing an installation."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit_plan as data
import baseline as baseline_identity
from filesystem import read_cache,write_cache,cache_path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('image','restore','proposal','qualification','payload-cache','preparation','private','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--baseline-qualification',type=Path,default=baseline_identity.default_qualification())
    a=p.parse_args();q=json.loads(a.qualification.read_text());proposal=json.loads(a.proposal.read_text());prep=json.loads(a.preparation.read_text())
    if not prep['prepared'] or not prep['target_set_matches_qualified_plan'] or prep['committed'] or prep['fetch_attempts'] or prep['unexpected_question'] or prep['protected_changed'] or prep['flags']!=139264:raise ValueError('requires successful normal-check prepare-only scenario')
    if prep['qualification_sha256']!=data.sha(a.qualification) or prep['proposal_sha256']!=data.sha(a.proposal) or q['proposal_sha256']!=data.sha(a.proposal):raise ValueError('prepared/signed plan binding mismatch')
    if prep['helper_source_sha256']!=data.sha(Path(__file__).with_name('prepare.c')) or prep['wrapper_sha256']!=data.sha(Path(__file__).with_name('prepare.py')):raise ValueError('preparation source version differs')
    for artifact in (q,proposal,prep):
        if artifact['deployable'] is not False or artifact['actions']!=[]:raise ValueError('requires blocked data-only artifacts')
    selected={r['name']for r in q['packages']};exact={(r['repository'],r['name'],r['version'])for r in q['packages']}
    if len(selected)!=len(q['packages']) or exact!={(r['repository'],r['name'],r['version'])for r in prep['add']}:raise ValueError('prepared target set differs from exact qualified packages')
    if q['counts']!={'selected':len(selected),'payloads_qualified':len(selected),'failed':0}:raise ValueError('incomplete selected payload qualification')
    if prep['protected_installed_pin_count']!=20 or prep['held_request_count']!=4:raise ValueError('original protected hold counts differ')
    removed={r['name']for r in prep['remove']}
    if removed & set(proposal['protected_installed_pins']):raise ValueError('protected installed removal forbidden')
    a.private.mkdir(parents=True,exist_ok=True)
    baseline,baseline_cache,seal=data.snapshot(a.image,a.restore,a.private);old=baseline['entries']
    complete_baseline=baseline_identity.verify(a.restore/'var/lib/pacman/local',a.baseline_qualification)
    if prep.get('baseline_description_count')!=complete_baseline['count'] or prep.get('baseline_description_digest')!=complete_baseline['digest'] or prep.get('baseline_qualification_sha256')!=data.sha(a.baseline_qualification) or prep.get('baseline_identity_helper_sha256')!=data.sha(Path(baseline_identity.__file__)):raise ValueError('prepared baseline does not match all sealed-image local descriptions')
    for row in prep['remove']:
        if baseline['installed'].get(row['name'])!=row['version']:raise ValueError('prepared removal differs from immutable image')
    key={'qualification':data.sha(a.qualification),'data_parser':data.sha(Path(data.__file__)),'parser':data.sha(Path(data.__file__).with_name('audit_elf.py')),'model_auditor':data.sha(Path(__file__)),'identity_helper':data.sha(Path(data.__file__).with_name('filesystem.py'))}
    cache=cache_path(a.private,'model-incoming',key)
    if cache.exists():
        captured=read_cache(cache)
        if captured['key']!=key:raise ValueError('model cache key differs')
        new,files,errors,architectures,collisions=captured['data']
        for row in q['packages']:
            path=a.payload_cache/'payloads'/row['sha256']/row['filename']
            if path.stat().st_size!=row['expected_bytes'] or data.sha(path)!=row['sha256']:raise ValueError('signed payload changed')
    else:
        new,files,errors,architectures,collisions=data.incoming(q,a.payload_cache)
        write_cache(cache,{'key':key,'data':[new,files,errors,architectures,collisions]})
    discarded=selected|removed
    resulting={path:entry for path,entry in old.items()if entry.get('owner')not in discarded};resulting.update(new)
    changed={e['elf']['soname']for e in old.values()if e.get('owner')in discarded and 'elf'in e and e['elf']['soname']}
    changed|={e['elf']['soname']for e in new.values()if 'elf'in e and e['elf']['soname']}
    reverse={path for path,e in old.items()if 'elf'in e and e.get('owner')not in discarded and any(n in changed for n in e['elf']['needed'])}
    incoming_paths={path for path,e in new.items()if 'elf'in e}
    before,before_gaps=data.edges(old,reverse|incoming_paths);after,gaps=data.edges(resulting,reverse|incoming_paths)
    issues=[];preserved=[]
    for key,row in after.items():
        if not row['issues']:continue
        prior=before.get(key);row=dict(row);row['baseline_issues']=prior['issues']if prior else None
        row['introduced_issue_set']=sorted(set(row['issues'])-set(prior['issues']if prior else []))
        (issues if row['introduced_issue_set']else preserved).append(row)
    owner_conflicts=[]
    for path,entry in new.items():
        owner=baseline['owners'].get(path)
        if owner and owner not in discarded and owner!=entry['owner']:owner_conflicts.append({'path':path,'retained_owner':owner,'incoming_owner':entry['owner']})
    removed_scripts=[]
    for folder in sorted((a.restore/'var/lib/pacman/local').iterdir()):
        if not folder.is_dir():continue
        fields=data.fields((folder/'desc').read_text());name=fields['NAME'][0]
        if name in removed:
            path=folder/'install'
            removed_scripts.append({'name':name,'version':fields['VERSION'][0],'installed_remove_script_present':path.exists(),'script_sha256':data.sha(path)if path.is_file()and not path.is_symlink()else None,'execution':'UNTESTED; no script executed'})
    result={'schema':1,'status':'PARTIAL','deployable':False,'execution_ready':False,'actions':[],
      'filesystem_model':'Exact successful normal libalpm metadata add/remove scenario over sealed image; still a virtual model, no actual installation',
      'proposal_sha256':data.sha(a.proposal),'qualification_sha256':data.sha(a.qualification),'preparation_sha256':data.sha(a.preparation),'model_source_sha256':data.sha(Path(__file__)),'data_parser_source_sha256':data.sha(Path(data.__file__)),
      'baseline_description_identity':complete_baseline,'baseline_qualification_sha256':data.sha(a.baseline_qualification),'baseline_identity_helper_sha256':data.sha(Path(baseline_identity.__file__)),
      'image':{'sha256':data.IMAGE_SHA,'bytes':data.IMAGE_SIZE,'root':256},'sealed_restore':{'manifest_sha256':baseline['key']['restore_manifest_sha256'],'tree_entries_sha256':seal['tree']['entries_sha256'],'entry_count':seal['tree']['entry_count']},
      'cache_provenance':{'baseline':{'filename':baseline_cache.name,'sha256':data.sha(baseline_cache)},'incoming':{'filename':cache.name,'sha256':data.sha(cache)}},
      'accepted_hypothetical_removals':prep['remove'],'protected_installed_pin_count':20,'held_request_count':4,
      'counts':{'selected_packages':len(selected),'baseline_packages':len(baseline['installed']),'prepared_removals':len(removed),'incoming_ELFs':len(incoming_paths),'incoming_ELF_machines':dict(architectures),'resulting_ELFs':sum('elf'in e for e in resulting.values()),'untouched_reverse_consumers':len(reverse),'direct_edges_checked':len(after),'new_or_incoming_issue_edges':len(issues),'preserved_issue_edges':len(preserved),'parse_gaps':len(errors)+len(baseline['errors']),'resolution_gaps':len(gaps),'incoming_file_collisions':len(collisions),'retained_owner_path_collisions':len(owner_conflicts)},
      'new_or_incoming_issues':issues,'preserved_issue_edges':preserved,'retained_owner_path_collisions':owner_conflicts,'incoming_file_collisions':collisions,'parse_gaps':baseline['errors']+errors,'resolution_gaps':gaps,'removed_package_install_scripts':removed_scripts,
      'prior_incoming_boot_effects':q['boot_effects'],'prior_execution_blockers':q['execution_blockers'],
      'limits':['Normal dependency/conflict preparation does not commit, validate all file conflicts, execute hooks/scripts, or establish runtime ABI.','Static resolution remains bounded to all incoming ELFs and retained usr/bin,usr/lib,usr/libexec,opt; original audited resolver limitations remain.','Removal-hook operation matching is UNTESTED; incoming qualification retains its boot-generation blockers.','No source-candidate unsigned package can replace a signed frozen row in this model.','Protected holds, boot hooks, original boot/recovery and actual hardware acceptance remain BLOCKED.']}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result['counts'],indent=2))
if __name__=='__main__':main()
