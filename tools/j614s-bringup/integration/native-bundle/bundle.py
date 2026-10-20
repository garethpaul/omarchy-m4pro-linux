#!/usr/bin/env python3
"""Offline native-format assembly/verification; no target API or boot authority."""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import types
import sys

HERE = Path(__file__).resolve().parent
PINSET_SHA256 = '24786b18734ddd9858d2276c1c490fd9d24aa7faa764af400136068bba451bc9'
_pin_path=HERE/'pins.json'
if not _pin_path.is_file() or _pin_path.stat().st_size>2<<20:
    raise ValueError('Reviewed native-bundle pinset missing or exceeds bound')
with _pin_path.open('rb') as _stream:_pins_bytes=_stream.read((2<<20)+1)
if len(_pins_bytes)>2<<20 or hashlib.sha256(_pins_bytes).hexdigest()!=PINSET_SHA256:
    raise ValueError('Reviewed native-bundle pinset differs')
PINS=json.loads(_pins_bytes)
_format_path=HERE/'native_format.py'
if not _format_path.is_file() or _format_path.stat().st_size>2<<20:
    raise ValueError('Format helper missing or exceeds bound')
with _format_path.open('rb') as _stream:_format_bytes=_stream.read((2<<20)+1)
if len(_format_bytes)>2<<20 or hashlib.sha256(_format_bytes).hexdigest()!=PINS['native_format_sha256']:
    raise ValueError('Pinned native-format source differs')
fmt=types.ModuleType('native_bundle_verified_format');fmt.__file__=str(_format_path)
sys.modules[fmt.__name__]=fmt  # dataclass resolves its defining module here.
exec(compile(_format_bytes,str(_format_path),'exec',dont_inherit=True,optimize=0),fmt.__dict__)


def read_bounded(path, limit):
    fmt.require(path.is_file() and path.stat().st_size <= limit, 'Input missing or exceeds bound')
    with path.open('rb') as stream:
        raw=stream.read(limit+1)
    fmt.require(len(raw) <= limit, 'Input changed beyond bound')
    return raw


def pinned(path, expected, limit):
    raw=read_bounded(path,limit)
    fmt.require(fmt.sha(raw)==expected,'Pinned input digest differs')
    return raw


def execute_source(path, expected, name):
    raw=pinned(path,expected,2<<20)
    module=types.ModuleType(name);module.__file__=str(path.resolve())
    exec(compile(raw,str(path),'exec',dont_inherit=True,optimize=0),module.__dict__)
    return module


def tools():
    result={}
    for name,expected in PINS['host_tools'].items():
        found=shutil.which(name)
        fmt.require(found is not None,'Required read-only host tool unavailable')
        path=Path(found).resolve();pinned(path,expected,64<<20);result[name]=path
    return result


@contextmanager
def tool_environment(paths):
    # Restrict helper subprocess names to already hash-checked host tools. Git
    # optional index updates/fsmonitor/hooks are disabled; no target code runs.
    with tempfile.TemporaryDirectory(prefix='native-bundle-tools-') as temp:
        for name,path in paths.items():(Path(temp)/name).symlink_to(path)
        changes={'PATH':temp,'GIT_OPTIONAL_LOCKS':'0','GIT_CONFIG_COUNT':'3',
                 'GIT_CONFIG_KEY_0':'core.fsmonitor','GIT_CONFIG_VALUE_0':'false',
                 'GIT_CONFIG_KEY_1':'core.untrackedCache','GIT_CONFIG_VALUE_1':'false',
                 'GIT_CONFIG_KEY_2':'core.hooksPath','GIT_CONFIG_VALUE_2':'/dev/null'}
        old={k:os.environ.get(k) for k in changes};os.environ.update(changes)
        try:yield
        finally:
            for key,value in old.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value


def loader_pair(loader,elf,paths):
    flat=pinned(loader,PINS['loader_sha256'],fmt.LOADER_LIMIT)
    raw=pinned(elf,PINS['loader_elf_sha256'],16<<20)
    fmt.require(len(flat)==PINS['loader_bytes'] and len(raw)==PINS['loader_elf_bytes'],'Pinned loader/ELF lengths differ')
    fmt.require(raw[:6]==b'\x7fELF\x02\x01' and raw[18:20]==b'\xb7\0' and struct.unpack_from('<H',raw,16)[0]==3,'Expected AArch64 ELF64 DYN loader')
    symbols=subprocess.run([str(paths['llvm-nm']),'--defined-only','--format=posix',str(elf)],capture_output=True,check=True)
    fmt.require(not symbols.stderr,'Unexpected symbol-tool diagnostics')
    layout=fmt.layout_from_nm(symbols.stdout,len(flat))
    fmt.require(asdict(layout)==PINS['elf_layout'],'Pinned ELF symbol offsets differ')
    with tempfile.TemporaryDirectory(prefix='native-loader-flat-') as temp:
        target=Path(temp)/'flattened.bin'
        result=subprocess.run([str(paths['llvm-objcopy']),'-O','binary','--strip-debug',str(elf),str(target)],capture_output=True,check=True)
        fmt.require(not result.stderr and read_bounded(target,fmt.LOADER_LIMIT)==flat,'Paired ELF flattening differs from complete flat loader')
    return flat,layout


def independent_inputs(a,paths):
    flat,layout=loader_pair(a.loader_binary,a.loader_elf,paths)
    pinned(a.loader_source/'src/j614s_native.c',PINS['loader_source_sha256'],2<<20)
    pinned(a.loader_source/'m1n1.ld',PINS['linker_source_sha256'],2<<20)
    pinned(a.kernel_bundle/'manifest.json',PINS['kernel_manifest_sha256'],2<<20)
    pinned(a.kernel_bundle/'contract.json',PINS['kernel_contract_sha256'],2<<20)
    pinned(a.kernel_bundle/'.config',PINS['config_sha256'],2<<20)
    verifier=execute_source(a.dt_generator.parent.parent/'kernel_build.py',PINS['kernel_verifier_sha256'],'native_bundle_kernel_verifier')
    verifier.verify(a.kernel_bundle)
    image=pinned(a.kernel_bundle/'Image',PINS['Image_sha256'],fmt.IMAGE_LIMIT)
    fmt.require(len(image)==PINS['Image_bytes'],'Image length differs');memory_size=fmt.image_contract(image)
    initrd=pinned(a.initrd,PINS['initrd_sha256'],fmt.INITRD_LIMIT)
    fmt.require(len(initrd)==PINS['initrd_bytes'] and initrd.startswith(b'\x1f\x8b\x08'),'Initrd length/gzip envelope differs')
    proof=json.loads(pinned(a.probe_manifest,PINS['probe_manifest_sha256'],2<<20))
    fmt.require(proof['initrd_sha256']==fmt.sha(initrd) and proof['kernel_image_sha256']==fmt.sha(image) and proof['hardware']=='UNTESTED','Probe manifest binding differs')
    facts={'loader':{'status':'BYTE_IDENTITY_VERIFIED','sha256':fmt.sha(flat),'bytes':len(flat),'elf_sha256':PINS['loader_elf_sha256'],**asdict(layout),'flat_matches_elf':True},
           'Image':{'status':'BYTE_IDENTITY_VERIFIED','sha256':fmt.sha(image),'bytes':len(image),'memory_bytes':memory_size},
           'initrd':{'status':'BYTE_IDENTITY_VERIFIED','sha256':fmt.sha(initrd),'bytes':len(initrd)},
           'scope':'Independent file/format identities only; no runtime handoff or deployment qualification'}
    return flat,layout,image,initrd,facts


def generator(a):
    g=execute_source(a.dt_generator,PINS['dt_generator_sha256'],'native_bundle_dt_generator')
    pinned(a.dt_generator.parent/'source-profile-v1.json',PINS['dt_profile_sha256'],2<<20)
    p=g.profile()
    fmt.require(p['loader_commit']==PINS['loader_commit'] and p['kernel_commit']==PINS['kernel_commit'] and p['Image_sha256']==PINS['Image_sha256'] and p['loader_binary_sha256']==PINS['loader_sha256'],'DT profile artifact bindings differ')
    return g,p


def input_namespace(a):
    return types.SimpleNamespace(capture=a.capture,expected_capture_sha256=a.expected_capture_sha256,
        expected_usb_session=a.expected_usb_session,expected_observer_sha256=a.expected_observer_sha256,
        expected_bootargs_sha256=a.expected_bootargs_sha256,expected_adt_sha256=a.expected_adt_sha256,
        synthetic_fixture=False,observer_source=a.observer_source,resident_source=a.resident_source,
        loader_source=a.loader_source,loader_binary=a.loader_binary,kernel_source=a.kernel_source,kernel_bundle=a.kernel_bundle)


def report_contract(report,a,dtb):
    # Explicit expected report/DT digests come from the primary, not this report.
    fmt.require(report['status']=='UNRELOCATED_TEMPLATE_ONLY' and report['synthetic_fixture'] is False and report['runtime_fdt'] is False and report['deployment_authorized'] is False and report['hardware']=='UNTESTED','Only an actual unrelocated/unqualified template report is accepted')
    pairs={'profile_sha256':PINS['dt_profile_sha256'],'generator_sha256':PINS['dt_generator_sha256'],
           'capture_sha256':a.expected_capture_sha256,'observer_sha256':a.expected_observer_sha256,
           'bootargs_sha256':a.expected_bootargs_sha256,'adt_sha256':a.expected_adt_sha256,'usb_session':a.expected_usb_session,
           'loader_commit':PINS['loader_commit'],'kernel_commit':PINS['kernel_commit'],'dtb_sha256':fmt.sha(dtb)}
    fmt.require(all(report.get(key)==value for key,value in pairs.items()),'DT evidence identities differ')
    fmt.require(type(report['dtc_stderr_bytes']) is int and type(report['storage_diagnostic']) is bool and type(report['nodes_checked']) is int and report['nodes_checked'] > 0,'DT evidence scalar types differ')
    fmt.require(type(report['dtb_bytes']) is int and report['dtb_bytes']==len(dtb) and report['storage_diagnostic'] is a.storage_diagnostic and report['dtc_stderr_bytes']==0 and report['warnings_disabled'] is False,'DT evidence size/storage/compiler controls differ')
    for name in ('dtc','fdtget'):
        fmt.require(report['host_tools'][name]['sha256']==PINS['host_tools'][name],'DT evidence host tool differs')


def private_destination(a,path):
    fmt.require(path is not None and not path.exists(),'New private destination required; preserve prior outputs')
    roots=(a.loader_source,a.kernel_source,a.kernel_bundle,a.resident_source,
           a.dt_generator.parent,a.probe_manifest.parent,a.capture.parent)
    fmt.require(not any(path.resolve().is_relative_to(root.resolve()) for root in roots),'Output must not be inside an input/source/evidence directory')


def validate_all(a,paths,independent=None):
    independent=independent or independent_inputs(a,paths)
    g,p=generator(a);namespace=input_namespace(a)
    # Intentionally precedes all DT/report reads/output creation: current03 must
    # refuse for its actual idle/WFE state, not merely a missing DT pathname.
    pinned(a.capture,a.expected_capture_sha256,2<<20)
    with tool_environment(paths):capture=g.verify_inputs(namespace,p)
    fmt.require(re.fullmatch('[0-9a-f]{32}',a.nonce) is not None,'Explicit diagnostic nonce required')
    fmt.require(a.dtb is not None and a.dt_evidence is not None and a.expected_dtb_sha256 is not None and a.expected_dt_evidence_sha256 is not None,'Validated future DT artifact/evidence and explicit byte pins required')
    dtb=pinned(a.dtb,a.expected_dtb_sha256,fmt.FDT_LIMIT)
    report=g.decode(pinned(a.dt_evidence,a.expected_dt_evidence_sha256,2<<20));report_contract(report,a,dtb)
    private_destination(a,a.diagnostics)
    a.diagnostics.mkdir(mode=0o700)
    try:
        with tool_environment(paths):nodes=g.verify_dtb(a.dtb,capture,p,a.nonce,a.storage_diagnostic,diagnostic_dir=a.diagnostics)
    except g.CompilerDiagnostics as error:
        (a.diagnostics/'compiler.stdout').write_bytes(error.stdout)
        (a.diagnostics/'compiler.stderr').write_bytes(error.stderr)
        (a.diagnostics/'compiler-failure.json').write_text(json.dumps({'status':'REFUSED_COMPILER_DIAGNOSTICS','returncode':error.returncode,'stdout_bytes':len(error.stdout),'stderr_bytes':len(error.stderr),'hardware':'UNTESTED'})+'\n')
        raise fmt.Refused('DT compiler diagnostics retained privately') from error
    fmt.require(type(report['nodes_checked']) is int and nodes==report['nodes_checked'],'DT evidence node count differs')
    return (*independent[:4],dtb,independent[4],g,p,namespace)


def recheck(a,paths,validated):
    flat,layout,image,initrd,dtb,_,g,p,namespace=validated
    fmt.require(pinned(a.loader_binary,PINS['loader_sha256'],fmt.LOADER_LIMIT)==flat and pinned(a.loader_elf,PINS['loader_elf_sha256'],16<<20),'Loader inputs changed')
    fmt.require(pinned(a.kernel_bundle/'Image',PINS['Image_sha256'],fmt.IMAGE_LIMIT)==image and pinned(a.initrd,PINS['initrd_sha256'],fmt.INITRD_LIMIT)==initrd,'Image/initrd inputs changed')
    fmt.require(pinned(a.dtb,a.expected_dtb_sha256,fmt.FDT_LIMIT)==dtb,'DT bytes changed')
    pinned(a.dt_evidence,a.expected_dt_evidence_sha256,2<<20)
    pinned(a.dt_generator,PINS['dt_generator_sha256'],2<<20)
    fmt.require(g.profile()==p,'DT profile/assets changed')
    with tool_environment(paths):g.verify_inputs(namespace,p)


def expected_parts(validated):
    return {'image':PINS['Image_sha256'],'initrd':PINS['initrd_sha256'],'dtb':fmt.sha(validated[4])}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['audit','assemble','verify'])
    for name in ('loader-binary','loader-elf','loader-source','kernel-source','kernel-bundle','initrd','probe-manifest','dt-generator','capture','observer-source','resident-source','diagnostics'):
        parser.add_argument('--'+name,type=Path,required=True)
    for name in ('expected-capture-sha256','expected-usb-session','expected-observer-sha256','expected-bootargs-sha256','expected-adt-sha256','nonce'):
        parser.add_argument('--'+name,required=True)
    for name in ('dtb','dt-evidence','output','bundle'):
        parser.add_argument('--'+name,type=Path)
    for name in ('expected-dtb-sha256','expected-dt-evidence-sha256'):
        parser.add_argument('--'+name)
    parser.add_argument('--storage-diagnostic',action='store_true')
    a=parser.parse_args();os.umask(0o077)
    result={'schema':1,'hardware':'UNTESTED','runtime_fdt':False,'deployment_authorized':False,'boot_permission':False}
    try:
        paths=tools();independent=independent_inputs(a,paths);result['components']=independent[4]
        validated=validate_all(a,paths,independent);flat,layout,image,initrd,dtb=validated[:5]
        expected=expected_parts(validated)
        if a.mode=='assemble':
            private_destination(a,a.output)
            blob=fmt.assemble(flat,layout,image,initrd,dtb,expected);recheck(a,paths,validated)
            a.output.mkdir(mode=0o700)
            (a.output/'UNQUALIFIED-native-container.bin').write_bytes(blob)
            result.update(status='OFFLINE_FORMAT_ASSEMBLED_ONLY',container_sha256=fmt.sha(blob),container_bytes=len(blob))
            (a.output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        elif a.mode=='verify':
            fmt.require(a.bundle is not None,'Existing container input required')
            blob=read_bounded(a.bundle,fmt.BUNDLE_LIMIT);fmt.parse(blob,flat,layout,expected);recheck(a,paths,validated)
            result.update(status='OFFLINE_FORMAT_VERIFIED_ONLY',container_sha256=fmt.sha(blob),container_bytes=len(blob))
        else:
            recheck(a,paths,validated);result['status']='OFFLINE_INPUTS_VERIFIED_ONLY'
    except (ValueError,KeyError,TypeError,OSError,subprocess.CalledProcessError) as error:
        result.update(status='BLOCKED',reason='SECONDARY_SLOTS_NOT_IDLE_WFE' if isinstance(error,ValueError) and 'Secondary slots are not all idle in WFE mode' in str(error) else 'INPUT_OR_FORMAT_CONTRACT_REFUSED',container_produced=False)
        # Deliberately do not print private capture data, raw tool output or paths.
    print(json.dumps(result,indent=2,sort_keys=True))
    raise SystemExit(1 if result['status']=='BLOCKED' else 0)


if __name__=='__main__':main()
