#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare private host artifacts and a PLAN ONLY result; never operate a target."""
import argparse
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import struct
import sys
import traceback
import types

SOURCE_PINS={
 'integration/native-bundle/bundle.py':'6e67500997fffbd19da35254bd1d2bd4f908ada0ddadf45d328bcd2401e8d0da',
 'integration/native-bundle/native_format.py':'01cd865464162c3c12e0537cd4e30e394c3644ce7ff3d4b88552fb2abbd48bd5',
 'integration/native-bundle/pins.json':'24786b18734ddd9858d2276c1c490fd9d24aa7faa764af400136068bba451bc9',
 'infra/native-dt/generate.py':'b29110da5799e994238076a864a8e9f4ab98275225d7264ec51f6dd6683715c4',
 'infra/native-dt/source-profile-v1.json':'040a4e39048bc0da1963a1d622f3bc3c600c1c7a253e4e28c0fd33dfa341f425',
 'recovery/supervised_child.py':'f08c570a7757163569ce48e828484fa731c59a3d95b8cbd8f6bc1a4284779308',
 'infra/staging-reservation/reservation.py':'8388b68a1afd6a71829b2a3f5e9ce2924649b301e474dce4fee20ada7b9e6017',
 'infra/staging-plan/planner.py':'e8b9d4ce0da16f20ad0f205a3dbe2bfa0a6621b2b37ed86d6e9fca872e223363',
 'infra/kernel_build.py':'c84ae596247f9f08eff693d8234917fa0f90bea69659da20db2a5a047a6508eb',
 'recovery/allocator-instructions.json':'f6108800b09d763c76d19749119c91eea47e3532275ecea1d6e699bc5e55a201'}
SEED_KEYS={'bundle_inputs','bundle_verification','bundle_verification_sha256','capture','capture_sha256',
 'container','container_sha256','cpu_capture','cpu_capture_sha256','dtb_sha256','original_bootargs',
 'physical_usb_port','reservation_source_sha256','resident_source','state','tooling'}
PATH_KEYS={'loader_binary','loader_elf','loader_source','kernel_source','kernel_bundle','initrd',
 'probe_manifest','dt_generator','capture','observer_source','resident_source','diagnostics','dtb','dt_evidence'}
BUNDLE_KEYS=PATH_KEYS|{'expected_adt_sha256','expected_bootargs_sha256','expected_capture_sha256',
 'expected_dt_evidence_sha256','expected_dtb_sha256','expected_observer_sha256','expected_usb_session',
 'nonce','storage_diagnostic'}


def require(ok,reason):
    if not ok:raise ValueError(reason)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def pairs(items):
    result={}
    for key,value in items:
        require(key not in result,'DUPLICATE_JSON_KEY');result[key]=value
    return result


def decode(raw):
    require(type(raw) is bytes and len(raw)<=2<<20,'JSON_INPUT_EXCEEDS_BOUND')
    result=json.loads(raw,object_pairs_hook=pairs);require(type(result) is dict,'JSON_OBJECT_REQUIRED')
    return result


def read_bound(path,limit):
    forbidden=(Path('/dev'),Path('/sys'),Path('/proc'))
    require(not any(path.absolute().is_relative_to(root) for root in forbidden),'TARGET_OR_KERNEL_INTERFACE_INPUT_FORBIDDEN')
    require(not any(path.resolve().is_relative_to(root) for root in forbidden),'TARGET_OR_KERNEL_INTERFACE_INPUT_FORBIDDEN')
    require(path.is_file() and path.stat().st_size<=limit,'INPUT_FILE_MISSING_OR_TOO_LARGE')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'INPUT_GREW_BEYOND_BOUND');return raw


def pinned(path,expected,limit=2<<20):
    require(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected),'EXPLICIT_SHA256_REQUIRED')
    raw=read_bound(path,limit);require(sha(raw)==expected,'INPUT_SHA256_DIFFERS');return raw


def require_storage(seed):
    require(type(seed.get('bundle_inputs')) is dict and seed['bundle_inputs'].get('storage_diagnostic') is True,
            'STORAGE_DIAGNOSTIC_EXPLICIT_TRUE_REQUIRED')


def separated(destination,roots):
    destination=destination.resolve()
    require(not destination.exists() and destination.parent.is_dir(),'FRESH_DESTINATION_WITH_EXISTING_PARENT_REQUIRED')
    require(not any(destination.is_relative_to(root.resolve()) for root in roots),'OUTPUT_INSIDE_INPUT_OR_SOURCE')
    return destination


def checked_sources(tooling):
    return {name:pinned(tooling/name,digest) for name,digest in SOURCE_PINS.items()}


def execute(raw,path,name):
    module=types.ModuleType(name);module.__file__=str(path.resolve());sys.modules[name]=module
    exec(compile(raw,str(path),'exec',dont_inherit=True,optimize=0),module.__dict__)
    return module


def shared_observations(cpu,stage,bootargs,adt):
    """Compare available fields only; staging schema has no raw slot digest."""
    s=stage['session'];q=cpu['private_session'];m=stage['memory']
    require(cpu['usb_enumeration']==s['usb_enumeration'] and cpu['bootargs_sha256']==s['bootargs_sha256'] and
            cpu['adt_sha256']==s['adt_sha256'],'CPU_STAGING_SESSION_HASHES_DIFFER')
    require(cpu['binary_sha256']==s['resident_binary_sha256'] and
            cpu['observer_sha256']==stage['helper_sources']['cpu_observer_sha256'],'CPU_STAGING_SOURCE_IDENTITY_DIFFERS')
    fields={'resident_base':'resident_base','resident_end':'resident_end','ram_base':'usable_base',
            'ram_size':'usable_size','physical_ram_base':'physical_base','physical_ram_size':'physical_size','boot_video':'boot_video'}
    require(all(q[key]==m[other] for key,other in fields.items()),'CPU_STAGING_GEOMETRY_DIFFERS')
    require(q['table_address']==m['resident_base']+0xb0198,'CPU_RELEASE_TABLE_DIFFERS')
    ids={str(row['cpu_id']) for row in cpu['cpus']}
    require(set(q['release_addresses'])==ids and all(q['release_addresses'][key]==q['table_address']+int(key)*64+16 for key in ids),
            'CPU_RELEASE_POINTER_DIFFERS')
    require(all(cpu[key]==stage['cpu_state'][key] for key in ('secondary_flags_set','secondary_slots_idle','resident_wfe_mode')),
            'CPU_STAGING_READINESS_DIFFERS')
    require(stage['cpu_state']==dict(secondary_flags_set=11,secondary_slots_idle=True,resident_wfe_mode=True),'CPU_WFE_NOT_READY')
    require(re.fullmatch('[0-9a-f]{64}',cpu['slot_snapshot_sha256']) is not None,'CPU_SLOT_SNAPSHOT_HASH_REQUIRED')
    require(len(bootargs)==1152 and sha(bootargs)==s['bootargs_sha256'] and sha(adt)==s['adt_sha256'],
            'ORIGINAL_BOOTARGS_OR_ADT_DIFFERS')
    require(struct.unpack_from('<H',bootargs)[0]==3 and struct.unpack_from('<Q',bootargs,32)[0]==m['bootargs_top'],
            'ORIGINAL_BOOTARGS_REVISION_OR_TOP_DIFFERS')
    require(struct.unpack_from('<QQ',bootargs,16)==(m['usable_base'],m['usable_size']),'ORIGINAL_BOOTARGS_RAM_DIFFERS')
    metadata={r['name']:r for r in stage['protected_metadata']}
    require(metadata['live-bootargs']['size']==len(bootargs) and metadata['live-adt']['size']==len(adt),'ORIGINAL_METADATA_EXTENT_DIFFERS')
    return dict(shared_fields='MATCH',raw_slot_snapshot_cross_capture='UNPROVABLE_FROM_FROZEN_STAGING_SCHEMA',
      live_slot_authority='SEPARATE_STAGE_VECTOR_PAIRED_ELF_DOUBLE_READS',liveness='UNQUALIFIED')


def namespace(seed,cpu_path,cpu,capture_sha):
    values=copy.deepcopy(seed['bundle_inputs'])
    values.update(capture=str(cpu_path),expected_capture_sha256=capture_sha,
      expected_usb_session=cpu['usb_enumeration'],expected_observer_sha256=cpu['observer_sha256'],
      expected_bootargs_sha256=cpu['bootargs_sha256'],expected_adt_sha256=cpu['adt_sha256'])
    return types.SimpleNamespace(**{key:Path(value) if key in PATH_KEYS else value for key,value in values.items()})


def preflight(args):
    seed_raw=pinned(args.seed,args.expected_seed_sha256);seed=decode(seed_raw);require_storage(seed)
    require(set(seed)==SEED_KEYS and set(seed['bundle_inputs'])==BUNDLE_KEYS,'SEED_CONTEXT_SCHEMA_DIFFERS')
    tooling=Path(seed['tooling']);resident=Path(seed['resident_source'])
    require(tooling.is_absolute() and resident.is_absolute(),'ABSOLUTE_SOURCE_PATHS_REQUIRED')
    require(all(Path(seed['bundle_inputs'][key]).is_absolute() for key in PATH_KEYS),'ABSOLUTE_BUNDLE_PATHS_REQUIRED')
    require(Path(seed['bundle_inputs']['resident_source']).resolve()==resident.resolve(),'SEED_RESIDENT_SOURCE_DIFFERS')
    require(seed['reservation_source_sha256']==SOURCE_PINS['infra/staging-reservation/reservation.py'],'SEED_RESERVATION_PIN_DIFFERS')
    require(Path(seed['bundle_inputs']['dt_generator']).resolve()==(tooling/'infra/native-dt/generate.py').resolve(),'SEED_GENERATOR_PATH_DIFFERS')
    staging=args.staging_directory.resolve(strict=True);require(staging.is_dir(),'STAGING_DIRECTORY_REQUIRED')
    cpu_raw=pinned(args.cpu_capture,args.expected_cpu_sha256);cpu=decode(cpu_raw)
    stage_raw=pinned(staging/'capture.json',args.expected_staging_sha256);stage=decode(stage_raw)
    require(cpu.get('synthetic_fixture',False) is False and stage.get('synthetic_fixture') is False,'SYNTHETIC_INPUT_NOT_ACTUAL_PREPARATION')
    bootargs=read_bound(staging/'bootargs.bin',1152);adt=read_bound(staging/'adt.bin',64<<20)
    shared=shared_observations(cpu,stage,bootargs,adt)
    roots=[args.seed.resolve().parent,args.cpu_capture.resolve().parent,staging,tooling,resident]
    for key in PATH_KEYS-{'diagnostics','capture','dtb','dt_evidence'}:
        path=Path(seed['bundle_inputs'][key]);roots.append(path if path.is_dir() else path.resolve().parent)
    output=separated(args.output,roots)
    sources=checked_sources(tooling)
    bundle=execute(sources['integration/native-bundle/bundle.py'],tooling/'integration/native-bundle/bundle.py','preparation_bundle')
    reservation=execute(sources['infra/staging-reservation/reservation.py'],tooling/'infra/staging-reservation/reservation.py','preparation_reservation')
    binary_paths=dict(planner=tooling/'infra/staging-plan/planner.py',source=resident/'src/heapblock.c',
      flat=resident/'build/m1n1.bin',elf=resident/'build/m1n1-raw.elf',instructions=tooling/'recovery/allocator-instructions.json')
    geometry=reservation.verify_binary_contract({key:read_bound(path,64<<20) for key,path in binary_paths.items()})
    expected=dict(stage['session'],capture_sha256=args.expected_staging_sha256,synthetic_fixture=False)
    geometry._capture(stage_raw,expected)
    ns=namespace(seed,args.cpu_capture.resolve(),cpu,args.expected_cpu_sha256)
    ns.storage_diagnostic=True
    bundle.private_destination(ns,output)
    paths=bundle.tools();generator,profile=bundle.generator(ns)
    with bundle.tool_environment(paths):
        generator.verify_inputs(bundle.input_namespace(ns),profile)
        bundle.independent_inputs(ns,paths)
    return dict(seed=seed,seed_raw=seed_raw,tooling=tooling,sources=sources,cpu_raw=cpu_raw,stage_raw=stage_raw,
      bootargs=bootargs,adt=adt,cpu=cpu,stage=stage,shared=shared,output=output,bundle=bundle,
      generator=generator,profile=profile,paths=paths,namespace=ns,args=args)


PHASES={
 'generate-dt':('infra/native-dt/generate.py',None),
 'assemble':('integration/native-bundle/bundle.py','assemble'),
 'verify':('integration/native-bundle/bundle.py','verify'),
 'plan-only':('recovery/supervised_child.py','plan')}


def validate_phase(module,argv,name):
    require(name in PHASES,'HOST_PHASE_NOT_ALLOWED')
    relative,mode=PHASES[name];path=Path(module.__file__)
    require(path.parts[-len(Path(relative).parts):]==Path(relative).parts,'HOST_PHASE_SOURCE_PATH_DIFFERS')
    pinned(path,SOURCE_PINS[relative])
    if mode is not None:require(bool(argv) and argv[0]==mode,'HOST_PHASE_MODE_FORBIDDEN')
    else:require(bool(argv) and argv[0].startswith('--'),'GENERATOR_POSITIONAL_MODE_FORBIDDEN')
    if name!='plan-only':
        require(argv.count('--storage-diagnostic')==1 and '--synthetic-fixture' not in argv,'HOST_PHASE_DIAGNOSTIC_FLAG_DIFFERS')
    else:
        require(len(argv)==6 and argv[1]=='--context' and argv[3]=='--expected-context-sha256' and argv[5]=='--operator-present',
                'PLAN_ONLY_ARGUMENTS_DIFFER')


def invoke(module,argv,root,name):
    validate_phase(module,argv,name)
    before=sys.argv;exit_code=0
    stdout_path=root/(name+'.stdout');stderr_path=root/(name+'.stderr')
    # Capture file descriptors too, so a pinned host tool's stderr survives a
    # failure even when its subprocess does not use capture_output itself.
    saved_out=os.dup(1);saved_err=os.dup(2)
    try:
        with private_stream(stdout_path) as stdout,private_stream(stderr_path) as stderr:
            sys.stdout.flush();sys.stderr.flush()
            os.dup2(stdout.fileno(),1);os.dup2(stderr.fileno(),2)
            sys.argv=[str(module.__file__),*argv]
            try:
                with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
                    try:module.main()
                    except SystemExit as error:exit_code=error.code or 0
            finally:
                stdout.flush();stderr.flush()
    finally:
        sys.argv=before
        os.dup2(saved_out,1);os.dup2(saved_err,2);os.close(saved_out);os.close(saved_err)
    require(exit_code==0,'PINNED_HOST_PHASE_REFUSED_'+name)
    return stdout_path.read_text()


def bundle_argv(ns,mode,diagnostics,**extra):
    values=vars(ns)|extra|dict(diagnostics=diagnostics)
    keys=['loader_binary','loader_elf','loader_source','kernel_source','kernel_bundle','initrd','probe_manifest',
      'dt_generator','capture','observer_source','resident_source','diagnostics','expected_capture_sha256',
      'expected_usb_session','expected_observer_sha256','expected_bootargs_sha256','expected_adt_sha256','nonce',
      'dtb','dt_evidence','expected_dtb_sha256','expected_dt_evidence_sha256']
    result=[mode]
    for key in keys:result+=['--'+key.replace('_','-'),str(values[key])]
    for key in ('output','bundle'):
        if key in extra:result+=['--'+key,str(extra[key])]
    result+=['--storage-diagnostic']
    return result


def private_stream(path):
    return os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC,0o600),'w')


def record_failure(root,error):
    text=traceback.format_exc()
    for name in ('stdout','stderr'):
        data=getattr(error,name,None)
        if data:
            if isinstance(data,bytes):data=data.decode(errors='replace')
            text+='\nPRIVATE_EXCEPTION_'+name.upper()+'\n'+str(data)
    with private_stream(root/'FAILED.traceback.txt') as stream:stream.write(text)
    with private_stream(root/'FAILED.json') as stream:
        json.dump(dict(status='HOST_PREPARATION_REFUSED',error_type=type(error).__name__,hardware='UNTESTED',
          target_actions=False,partial_outputs_preserved=True),stream);stream.write('\n')


def prepare(args):
    require(__debug__,'OPTIMIZED_PYTHON_FORBIDDEN')
    state=preflight(args);root=state['output'];root.mkdir(mode=0o700)
    try:
        copies=root/'inputs';copies.mkdir(mode=0o700)
        for name,key in (('seed.json','seed_raw'),('cpu.json','cpu_raw'),('capture.json','stage_raw'),('bootargs.bin','bootargs'),('adt.bin','adt')):
            with (copies/name).open('xb') as stream:stream.write(state[key])
        ns=namespace(state['seed'],copies/'cpu.json',state['cpu'],args.expected_cpu_sha256)
        ns.nonce=secrets.token_hex(16);ns.storage_diagnostic=True
        ns.dtb=root/'dt/UNRELOCATED-template.dtb';ns.dt_evidence=root/'dt/template-result.json'
        g=state['generator'];bundle=state['bundle'];tools=state['paths']
        generator_args=[]
        for key in ('capture','observer_source','resident_source','loader_source','loader_binary','kernel_source','kernel_bundle',
                    'expected_usb_session','expected_capture_sha256','expected_observer_sha256','expected_bootargs_sha256','expected_adt_sha256','nonce'):
            generator_args+=['--'+key.replace('_','-'),str(getattr(ns,key))]
        with bundle.tool_environment(tools):invoke(g,[*generator_args,'--output',str(root/'dt'),'--storage-diagnostic'],root,'generate-dt')
        ns.expected_dtb_sha256=sha(ns.dtb.read_bytes());ns.expected_dt_evidence_sha256=sha(ns.dt_evidence.read_bytes())
        with bundle.tool_environment(tools):
            assembled=decode(invoke(bundle,bundle_argv(ns,'assemble',root/'assemble-diagnostics',output=root/'container'),root,'assemble').encode())
            verification=decode(invoke(bundle,bundle_argv(ns,'verify',root/'verify-diagnostics',bundle=root/'container/UNQUALIFIED-native-container.bin'),root,'verify').encode())
        require(assembled['status']=='OFFLINE_FORMAT_ASSEMBLED_ONLY' and verification['status']=='OFFLINE_FORMAT_VERIFIED_ONLY','HOST_BUNDLE_PHASE_NOT_VERIFIED')
        (root/'bundle-verification.json').write_text(json.dumps(verification,indent=2)+'\n')
        context=copy.deepcopy(state['seed'])
        ns.diagnostics=root/'plan-diagnostics'
        context.update(tooling=str(state['tooling']),capture=str(copies/'capture.json'),capture_sha256=args.expected_staging_sha256,
          cpu_capture=str(copies/'cpu.json'),cpu_capture_sha256=args.expected_cpu_sha256,original_bootargs=str(copies/'bootargs.bin'),
          container=str(root/'container/UNQUALIFIED-native-container.bin'),container_sha256=verification['container_sha256'],
          bundle_verification=str(root/'bundle-verification.json'),bundle_verification_sha256=sha((root/'bundle-verification.json').read_bytes()),
          dtb_sha256=ns.expected_dtb_sha256,state=str(root/'stage-state.json'),
          bundle_inputs={key:str(value) if isinstance(value,Path) else value for key,value in vars(ns).items()})
        context_raw=(json.dumps(context,indent=2)+'\n').encode();context_path=root/'context.json';context_path.write_bytes(context_raw)
        (root/'context.sha256').write_text(sha(context_raw)+'\n')
        stager=execute(state['sources']['recovery/supervised_child.py'],state['tooling']/'recovery/supervised_child.py','preparation_plan_only')
        with bundle.tool_environment(tools):invoke(stager,['plan','--context',str(context_path),'--expected-context-sha256',sha(context_raw),'--operator-present'],root,'plan-only')
        require(not (root/'stage-state.json').exists(),'HOST_PREPARATION_MUST_NOT_EMIT_STAGE_STATE')
        plan=decode((root/'stage-state.plan.json').read_bytes())
        final=stager.copied_bootargs(state['bootargs'],state['stage']['memory']['bootargs_top'],plan['expected_heap_after'])
        require(sha(final)==plan['final_bootargs_sha256'] and final[:32]==state['bootargs'][:32] and final[40:]==state['bootargs'][40:],'FINAL_BOOTARGS_DELTA_DIFFERS')
        (root/'final-bootargs.bin').write_bytes(final)
        require((copies/'bootargs.bin').read_bytes()==state['bootargs'],'ORIGINAL_BOOTARGS_COPY_DIFFERS')
        checked_sources(state['tooling'])
        pinned(args.seed,args.expected_seed_sha256);pinned(args.cpu_capture,args.expected_cpu_sha256)
        pinned(args.staging_directory/'capture.json',args.expected_staging_sha256)
        require(read_bound(args.staging_directory/'bootargs.bin',1152)==state['bootargs'] and read_bound(args.staging_directory/'adt.bin',64<<20)==state['adt'],'ORIGINAL_METADATA_CHANGED_DURING_PREPARATION')
        result=dict(schema=1,status='HOST_PREPARATION_ONLY',hardware='UNTESTED',target_actions=False,boot_permission=False,
          deployment_authorized=False,context_sha256=sha(context_raw),original_bootargs_sha256=sha(state['bootargs']),
          final_bootargs_sha256=sha(final),source_pins=SOURCE_PINS,shared_capture_checks=state['shared'])
        (root/'preparation.json').write_text(json.dumps(result,indent=2)+'\n');return result
    except Exception as error:
        record_failure(root,error)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('seed','cpu-capture','staging-directory','output'):parser.add_argument('--'+key,type=Path,required=True)
    for key in ('expected-seed-sha256','expected-cpu-sha256','expected-staging-sha256'):parser.add_argument('--'+key,required=True)
    args=parser.parse_args();os.umask(0o077)
    try:result=prepare(args)
    except Exception as error:
        reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z0-9_]+',str(error)) else 'PINNED_HOST_VALIDATION_REFUSED'
        print(json.dumps(dict(status='HOST_PREPARATION_REFUSED',reason=reason,error_type=type(error).__name__,target_actions=False,boot_permission=False)))
        raise SystemExit(1)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
