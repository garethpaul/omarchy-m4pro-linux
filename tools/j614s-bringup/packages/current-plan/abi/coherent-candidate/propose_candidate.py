#!/usr/bin/env python3
"""Separate frozen Qt/SONAME/native-formatter closure; no refresh or install."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from propose import original_inputs,ORDER,transaction_diff
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_plan import sha
import baseline as baseline_identity

EXTRA={
 'qt6-5compat':'existing Qt family coherence','qt6-multimedia-ffmpeg':'lost private Qt imports',
 'qt6-networkauth':'lost private Qt imports','qt6-positioning':'lost private Qt imports',
 'qt6-shadertools':'existing Qt family coherence','qt6-speech':'lost private Qt imports',
 'qt6-translations':'existing Qt family coherence','qt6-webchannel':'lost private Qt imports',
 'qt6-webengine':'existing Qt family coherence',
 'gnome-desktop':'incoming Evince requires libgnome-desktop-3.so.21',
 'libnfs':'incoming gvfsd-nfs requires libnfs.so.17',
 'openexr':'incoming libvips/ImageMagick require OpenEXR3_5.so.34',
 'jbigkit':'incoming GraphicsMagick/ImageMagick JBIG modules require libjbig.so.2.2',
 'libwmf':'incoming GraphicsMagick WMF module requires libwmflite-0.2.so.7',
 'qt5-base':'incoming fcitx5 Qt5 modules require Qt5 Core/DBus/Gui/Widgets',
 'qt6-quick3d':'incoming optional Qt6Quick3DSpatialAudio module requires Qt6Quick3D',
 'webkitgtk-6.0':'incoming Sushi extension requires libwebkitgtk-6.0.so.4',
 'lttng-ust2.12':'incoming optional CoreCLR tracing provider requires liblttng-ust.so.0',
 'shfmt':'explicit unsigned omarchy-nvim source-candidate dependency',
 'stylua':'explicit unsigned omarchy-nvim source-candidate dependency'}
NVIM_COMMIT='e8f5edeabdaa0efe30760f47bc5c93467ac45490'
NVIM_PKGBUILD_SHA='4a03f84d600c70e5b74893ee5d2ec461701ae9e07d470f97daaa4e59b13cd4c8'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','current','nvim-source','private','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--extra-canonical',action='append',default=[],metavar='NAME=REASON')
    a=p.parse_args()
    if a.private.exists()or a.output.exists():raise ValueError('new candidate private/output directories required')
    records,protected,resolver,planner,original=original_inputs(a.source)
    paths={name:a.current/'evidence'/('configured-current-'+name+'.json')for name in ('proposal','request-review','repositories','payload-qualification')}
    prior=json.loads(paths['proposal'].read_text());review=json.loads(paths['request-review'].read_text());provenance=json.loads(paths['repositories'].read_text());qualified=json.loads(paths['payload-qualification'].read_text())
    if sha(paths['proposal'])!=qualified['proposal_sha256'] or sha(paths['repositories'])!=qualified['repository_provenance_sha256']or qualified['counts']!={'selected':117,'payloads_qualified':117,'failed':0}:raise ValueError('original signed117 binding differs')
    if hashlib.sha256(json.dumps(review,sort_keys=True).encode()).hexdigest()!=prior['request_review_sha256']:raise ValueError('current request review binding differs')
    if review['protected_installed_pins']!=original['protected_installed_pins']or review['held_requests']!=original['held_requests']:raise ValueError('original20/fourholds differ')
    repositories=[]
    for row in prior['repositories']:
        path=a.current/'.private/capture-01/configured-current/repositories'/(row['name']+'.db')
        if sha(path)!=row['sha256']or provenance[row['name']]['sha256']!=row['sha256']:raise ValueError('frozen current DB changed')
        repositories.append((row['name'],path))
    if [n for n,_ in repositories]!=list(ORDER):raise ValueError('frozen repository order differs')
    complete_baseline=baseline_identity.verify(a.source/'evidence/package-root/var/lib/pacman/local',baseline_identity.default_qualification())
    index,_=planner.index_repositories(repositories)
    newreview=copy.deepcopy(review);canonical={r['candidate']['name']for r in newreview['resolved_requests']};additions=[]
    extras=dict(EXTRA)
    for item in a.extra_canonical:
        name,separator,reason=item.partition('=')
        if not separator or not re.fullmatch(r'[a-z0-9@_][a-z0-9@._+-]*',name) or not reason:raise ValueError('invalid explicit closure request')
        extras[name]=reason
    for name,reason in extras.items():
        if protected(name):raise ValueError('extra protected package requires separate authority')
        row=index.get(name)
        if row is None or row['name']!=name or row['architecture']not in ('aarch64','any'):raise ValueError('exact native extra package unavailable; no provider substitute selected')
        if name not in canonical:newreview['resolved_requests'].append({'requested':name,'resolved':name,'candidate':row,'resolution_evidence':'explicit separate closure request: '+reason});canonical.add(name)
        additions.append({'name':name,'reason':reason,'candidate':row})
    content=subprocess.check_output(['git','-C',str(a.nvim_source),'show',NVIM_COMMIT+':pkgbuilds/omarchy-nvim/PKGBUILD'])
    if hashlib.sha256(content).hexdigest()!=NVIM_PKGBUILD_SHA:raise ValueError('unsigned nvim source candidate differs')
    text=content.decode()
    if not all(value in text for value in ('pkgver=2026.9.21','pkgrel=6',"'shfmt'","'stylua'")):raise ValueError('source-only native dependency declaration differs')
    a.private.mkdir(parents=True);a.output.mkdir(parents=True)
    result=resolver.resolve(newreview,repositories,a.source/'evidence/package-root/var/lib/pacman/local',a.private/'resolver')
    result.update(execution_ready=False,proposal_variant='coherent-qt-soname-native-formatters-01',historical_snapshot_replaced=False,current117_snapshot_replaced=False,
                  proposal_builder_sha256=sha(Path(__file__)),original117_proposal_sha256=sha(paths['proposal']),original117_qualification_sha256=sha(paths['payload-qualification']),original_request_review_sha256=sha(paths['request-review']),
                  extra_canonical_requests=additions,recorded_original_request_count=len(review['resolved_requests']),extended_request_count=len(newreview['resolved_requests']),
                  baseline_description_identity=complete_baseline,baseline_qualification_sha256=sha(baseline_identity.default_qualification()),metadata_authentication=prior['metadata_authentication'],metadata_freshness_completeness='UNPROVEN; same previously frozen metadata, no refresh',
                  transaction_differences=transaction_diff(prior['resolved_transaction'],result['resolved_transaction'])if result['print_exit']==0 else None,
                  source_candidate={'name':'omarchy-nvim','source_commit':NVIM_COMMIT,'pkgbuild_sha256':NVIM_PKGBUILD_SHA,'source_version':'2026.9.21-6','status':'BLOCKED: unsigned source placeholder; not built, signed, released or selected instead of official row','native_dependencies':['shfmt','stylua'],'official_frozen_row_remains':next(r for r in prior['resolved_transaction']if r['name']=='omarchy-nvim'),'existing_user_migration':'UNTESTED; source fix only affects new template homes'},
                  remaining_closure_gates=['Complete exact payload PGP/signed metadata qualification for new frozen rows','Normal dependency/conflict preparation with explicit hypothetical removals','Re-run sealed-image ELF/ABI graph including newly replaced-library reverse consumers','Unsigned source-candidate build/signature/static/runtime gates; original signed nvim row retains foreign asset','Original protected20/fourholds, boot effects, removal hooks, target, recovery and runtime remain blocked'])
    (a.output/'request-review.json').write_text(json.dumps(newreview,indent=2)+'\n')
    (a.output/'proposal.json').write_text(json.dumps(result,indent=2)+'\n')
    (a.output/'repositories.json').write_text(paths['repositories'].read_text())
    print('separate candidate print exit',result['print_exit'],'packages',result.get('transaction_package_count'),'explicit extras',len(additions))
if __name__=='__main__':main()
