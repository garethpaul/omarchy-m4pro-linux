#!/usr/bin/env python3
"""Build an immutable native-loader candidate offline in its own checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(source, *args):
    return subprocess.check_output(['git', *args], cwd=source)


def write(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--commit', required=True)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--linker', required=True, type=Path)
    p.add_argument('--jobs', type=int, default=8)
    a = p.parse_args(); s=a.source.resolve(); out=a.output.resolve()
    if git(s,'rev-parse','HEAD').decode().strip()!=a.commit or git(s,'status','--porcelain') or (s/'build').exists() or a.jobs<1:
        raise SystemExit('FAIL: exact clean candidate and unused source build directory required')
    tree=git(s,'rev-parse','HEAD^{tree}').decode().strip()
    files={n:digest(s/n) for n in git(s,'ls-files','-z').decode().strip('\0').split('\0') if (s/n).is_file()}
    paths={n:Path(shutil.which(n)).resolve() for n in ('make','clang','llvm-objcopy','llvm-readelf','llvm-nm')}
    for n in ('rustc','cargo'):
        paths[n]=Path(subprocess.check_output(['rustup','which',n],text=True).strip())
    paths['ld.lld']=a.linker.resolve()
    tools={n:{'sha256':digest(path),'version':subprocess.check_output([str(path),*(['-flavor','gnu','--version'] if n=='ld.lld' else ['--version'])],text=True).splitlines()[0]} for n,path in paths.items()}
    if not tools['clang']['version'].startswith('clang version 23.1.3') or not tools['rustc']['version'].startswith('rustc 1.91.1'):
        raise SystemExit('FAIL: unreviewed native compiler version')
    out.mkdir(parents=True,exist_ok=False);bindir=out/'bin';bindir.mkdir()
    for n,path in paths.items():(bindir/n).symlink_to(path)
    tag='j614s-native-readonly-'+a.commit[:12]
    flags=['USE_CLANG=1','ARCH=aarch64-linux-gnu-','CHAINLOADING=1','T6040_STAGE1_CDC=1','J614S_NATIVE=1','BUILTIN_LOGO=aurora']
    remaps=['--remap-path-prefix='+str(Path.home())+'=home','--remap-path-prefix='+str(s)+'=source']
    env={k:v for k,v in os.environ.items() if k in ('HOME','USER','LOGNAME','TMPDIR','CARGO_HOME')}
    env.update(PATH=str(bindir)+':/usr/bin:/bin',LANG='C',LC_ALL='C',CARGO_NET_OFFLINE='true',
               M1N1_VERSION_TAG=tag,RUSTFLAGS=' '.join(remaps))
    command=[str(paths['make']),'-j'+str(a.jobs),'V=1',*flags,'TOOLCHAIN='+str(bindir)+'/',
             'LLDDIR='+str(bindir)+'/', 'EXTRA_CFLAGS=-ffile-prefix-map='+str(Path.home())+'=home -ffile-prefix-map='+str(s)+'=source']
    request={'source_commit':a.commit,'source_tree':tree,'source_manifest_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
             'source_files':files,'tools':tools,'config_arguments':flags,'version_tag':tag,'target':'aarch64-unknown-none-softfloat',
             'path_remap_recipe':2,
             'additional_flags':{'C':'-ffile-prefix-map=HOME=home -ffile-prefix-map=SOURCE=source','Rust':'--remap-path-prefix=HOME=home --remap-path-prefix=SOURCE=source'},
             'network':'CARGO_NET_OFFLINE=true','hardware':'UNTESTED','deployment_authorized':False}
    write(out/'request.json',request)
    with (out/'build.log').open('wb') as log:
        run=subprocess.run(command,cwd=s,env=env,stdout=log,stderr=subprocess.STDOUT)
    if run.returncode:
        write(out/'failure.json',{'status':'BUILD_FAILED','exit_code':run.returncode,'source_commit':a.commit,'source_clean':not bool(git(s,'status','--porcelain'))})
        raise SystemExit('FAIL: compile failure preserved')
    if git(s,'status','--porcelain') or any(digest(s/n)!=value for n,value in files.items()) or any(digest(paths[n])!=v['sha256'] for n,v in tools.items()):
        raise SystemExit('FAIL: source/tool drift')
    artifacts=[]
    for name in ['m1n1.bin','m1n1.macho','m1n1.elf','m1n1-raw.elf','j614s_native.o','build_cfg.h','build_tag.h']:
        f=s/'build'/name;record={'path':'build/'+name,'bytes':f.stat().st_size,'sha256':digest(f)}
        if name.endswith(('.elf','.o')):
            h=f.read_bytes()[:20]
            if h[:6]!=b'\x7fELF\x02\x01' or h[18:20]!=b'\xb7\x00':raise ValueError('Not ELF64 AArch64: '+name)
        if name.endswith(('.bin','.macho')):
            record['host_home_prefix_matches']=f.read_bytes().count(str(Path.home()).encode()+b'/')
            if record['host_home_prefix_matches']:raise ValueError('Private host prefix remains in flat loader')
            record['source_checkout_name_matches']=f.read_bytes().count(s.name.encode())
            if record['source_checkout_name_matches']:raise ValueError('Checkout-dependent paths remain in flat loader')
        artifacts.append(record)
    expected='#define CHAINLOADING\n#define T6040_STAGE1_CDC\n#define J614S_NATIVE\n#define BUILTIN_LOGO aurora\n'
    if (s/'build/build_cfg.h').read_text()!=expected:raise ValueError('Native build configuration drift')
    if 'spmi_ext_write_long' in subprocess.check_output([str(paths['llvm-nm']),'-u',str(s/'build/j614s_native.o')],text=True):
        raise ValueError('PMU-write reference remains in native helper object')
    request.update(status='LOADER_COMPILED',source_clean_after=True,artifacts=artifacts,
                   pmu_write_reference_in_native_object=False,
                   scope='Offline loader build only; no appended kernel/initramfs/DT; no target execution or recovery proof')
    write(out/'result.json',request)
    print('PASS: offline native loader build, configuration and flat-artifact path checks; hardware UNTESTED')


if __name__=='__main__':
    main()
