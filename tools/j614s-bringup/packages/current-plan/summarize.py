#!/usr/bin/env python3
"""Bind the separate current proposal, payload proof and immutable historical evidence."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_transaction import sha,write_evidence
from exhaust_official_mirrors import PREVIOUS
from propose import ORDER, original_inputs


def main():
    root=Path(__file__).resolve().parent;evidence=root/'evidence';parent=root.parent
    history={}
    for name,expected in PREVIOUS.items():
        actual=sha(parent/'evidence'/name)
        if actual!=expected:raise ValueError('historical audit changed')
        history[name]=actual
    historical='packages/evidence/exhaustive-official-mirror-checks.json'
    original=subprocess.check_output(['git','show','6fd31d77585457196a4bbf3bbff3da9634f43e29:'+historical],cwd=root)
    if hashlib.sha256(original).hexdigest()!=sha(parent/'evidence/exhaustive-official-mirror-checks.json'):raise ValueError('historical mirror exhaustion evidence changed')
    history['exhaustive-official-mirror-checks.json']=hashlib.sha256(original).hexdigest()
    source=root.parents[2]/'overnight-omarchy/omarchy'
    _,_,_,_,original_review=original_inputs(source)
    old_repository_hashes={r['name']:r['sha256'] for r in original_review['repositories']}
    configured=json.loads((evidence/'configured-current-proposal.json').read_text())
    official=json.loads((evidence/'official-alarm-current-proposal.json').read_text())
    metadata={n:json.loads((evidence/(n+'-repositories.json')).read_text()) for n in ('configured-current','official-alarm-current')}
    proof=json.loads((evidence/'configured-current-payload-qualification.json').read_text())
    if proof['proposal_sha256']!=sha(evidence/'configured-current-proposal.json') or proof['repository_provenance_sha256']!=sha(evidence/'configured-current-repositories.json'):
        raise ValueError('proposal/payload evidence association changed')
    if not proof['audit_complete']:raise ValueError('payload proof incomplete')
    equivalent={n:metadata['configured-current'][n]['sha256']==metadata['official-alarm-current'][n]['sha256'] for n in ORDER}
    selections_equal=configured['resolved_transaction']==official['resolved_transaction']
    if not all(equivalent.values()) or not selections_equal:raise ValueError('variant qualification reuse not justified')
    replay_path=root/'.private/replay-configured/resolution.json';replay=json.loads(replay_path.read_text())
    if replay['print_exit'] or replay['resolved_transaction']!=configured['resolved_transaction']:raise ValueError('frozen-metadata resolver replay changed')
    result={'schema':1,'status':'PARTIAL (reviewable current proposal; installation and ABI unqualified)',
            'historical_snapshot_replaced':False,'historical_evidence_sha256':history,
            'recorded_compatibility_requests':167,'current_print_transaction_packages':117,
            'version_changes':configured['transaction_differences']['changed'],
            'added_packages':configured['transaction_differences']['added'],'removed_packages':configured['transaction_differences']['removed'],
            'dependency_name_differences':configured['dependency_differences'],
            'signed_dependency_metadata_differences':proof['old_new_dependency_metadata_differences'],
            'payload_counts':proof['counts'],'signer_counts':dict(collections.Counter(r['primary_fingerprint'] for r in proof['packages'] if r['status']=='WORKS')),
            'repository_differences':[{'name':name,'old_sha256':old_repository_hashes[name],'current_sha256':metadata['configured-current'][name]['sha256'],'source_url':metadata['configured-current'][name]['url']} for name in ORDER if old_repository_hashes[name]!=metadata['configured-current'][name]['sha256']],
            'metadata_authentication':proof['metadata_authentication'],'metadata_freshness_completeness':'UNPROVEN',
            'signature_policy':'Retained image: Required DatabaseOptional. Missing DB signatures do not waive required retained-key package PGP or signed .PKGINFO comparison.',
            'variant_equivalence':{'repository_bytes_equal':equivalent,'selected_package_rows_equal':selections_equal,'qualification_scope':'Same frozen DB/package bytes; source URLs and TLS provenance remain distinct','payload_proof_sha256':sha(evidence/'configured-current-payload-qualification.json')},
            'actual_resolver_replay':{'status':'WORKS (print only)','resolution_sha256':sha(replay_path),'resolver':replay['resolver'],'selected_rows_equal':True},
            'compatibility_aliases':proof['compatibility_alias_evidence'],'boot_effects':proof['boot_effects'],
            'protected_installed_pin_count':len(configured['protected_installed_pins']),
            'held_original_requests':configured['held_original_requests'],
            'reverse_dependency_ABI':'UNTESTED; current libraries may break untouched image consumers despite declared dependency solve and valid signatures',
            'isolated_clone_validation':'Required before any real install: validate a disposable full-image clone and affected library/symbol/consumer ABI; no installation was attempted here',
            'full_upgrade_authorized':False,'deployable':False,'execution_ready':False,'actions':[],
            'claims':[
             {'status':'WORKS','claim':'Same recorded167 requests print-resolve against frozen current metadata through unmodified C resolver; frozen replay agrees','evidence':'configured-current-proposal.json'},
             {'status':'WORKS','claim':'117 selected payloads have exact SHA/size, retained-anchor PGP and matching signed identity/dependencies/metadata','evidence':'configured-current-payload-qualification.json'},
             {'status':'PARTIAL','claim':'Five DBs unsigned; Asahi DB signature valid. TLS and package signatures do not prove DB newest state/completeness','evidence':'configured-current-repositories.json'},
             {'status':'BLOCKED','claim':'Boot effects and held requests remain; no resulting system or rollback qualification','evidence':'configured-current-payload-qualification.json#/boot_effects'},
             {'status':'UNTESTED','claim':'Untouched reverse-dependency binary compatibility, actual install, hooks, services and target hardware','evidence':'No payload execution or installation in this lane'}]}
    write_evidence(evidence/'summary.json',result)
if __name__=='__main__':main()
