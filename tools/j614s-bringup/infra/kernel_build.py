#!/usr/bin/env python3
"""Qualified, isolated J614s kernel builds; never contacts the physical target."""
import argparse
import gzip
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

BINDGEN_SHA = '7fdf32940891781eb742fb4a69775a0b39de4a48d0a168dfb3f740fb547fceda'
REQUIRED_CONFIG = {'CONFIG_ARM64': 'y', 'CONFIG_NR_CPUS': '16',
                   'CONFIG_RUST': 'y', 'CONFIG_DRM_ASAHI': 'm',
                   'CONFIG_DRM_ASAHI_G16_BOOTSTRAP': 'm',
                   'CONFIG_LOCALVERSION': '"-j614s-gpu-bringup"'}
TOOL_VARS = {'clang': ('CC', 'HOSTCC'), 'clang++': ('HOSTCXX',),
             'ld.lld': ('LD', 'HOSTLD'), 'llvm-ar': ('AR', 'HOSTAR'),
             'llvm-nm': ('NM',), 'llvm-objcopy': ('OBJCOPY',),
             'llvm-objdump': ('OBJDUMP',), 'llvm-readelf': ('READELF',),
             'llvm-strip': ('STRIP',), 'rustc': ('RUSTC',),
             'rustdoc': ('RUSTDOC',), 'bindgen': ('BINDGEN',)}
TOOLS = tuple(TOOL_VARS) + ('make', 'bc')
RECIPE = {'version': 2, 'rust_path_remapping': ['source/', 'output/', 'rust-sysroot/'],
          'rust_sysroot_replacement': 'rust-toolchain/', 'localversion_suffix': '+',
          'build_user': 'j614s', 'build_host': 'builder',
          'build_timestamp': 'Mon Oct 19 00:00:00 UTC 2026', 'build_version': '1'}


def run(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, stderr=subprocess.PIPE)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def encoded_digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def source_state(source):
    head = run(['git', 'rev-parse', 'HEAD'], source).decode().strip()
    diff = run(['git', 'diff', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD', '--'], source)
    names = run(['git', 'ls-files', '--others', '--exclude-standard', '-z'], source)
    untracked = {}
    for raw in filter(None, names.split(b'\0')):
        name = os.fsdecode(raw)
        p = source / name
        if p.is_symlink() or not p.is_file():
            raise ValueError('Untracked source must be a regular file: ' + name)
        untracked[name] = digest(p)
    return {'head': head, 'dirty_diff_sha256': encoded_digest(diff),
            'untracked': untracked}, diff


def config_state(config, localversion=None):
    required = dict(REQUIRED_CONFIG)
    if localversion is not None:
        required['CONFIG_LOCALVERSION'] = json.dumps(localversion)
    settings = {}
    for line in config.read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
            settings[key] = value
    for key, value in required.items():
        if settings.get(key) != value:
            raise ValueError('Required config mismatch: ' + key)
    # Do not accept configuration-level attempts to inject arbitrary build flags.
    for key in ('CONFIG_RUSTFLAGS', 'CONFIG_GCC_PLUGINS'):
        if settings.get(key) not in (None, '""', 'n'):
            raise ValueError('Unqualified config setting: ' + key)
    return {'sha256': digest(config), 'required': required}


def tool_paths(args):
    env_path = str(args.tool_dir.resolve()) + os.pathsep + os.environ['PATH']
    paths = {}
    for name in TOOLS:
        if name == 'bindgen':
            p = str(args.bindgen.resolve())
        elif name in ('rustc', 'rustdoc'):
            p = run(['rustup', 'which', name]).decode().strip()
        else:
            p = shutil.which(name, path=env_path)
        if not p or not Path(p).is_file():
            raise ValueError('Missing qualified build tool: ' + name)
        # Keep ld.lld invocation basename; multicall rust-lld needs it.
        paths[name] = Path(p).absolute()
    if digest(paths['bindgen']) != BINDGEN_SHA:
        raise ValueError('Corrected bindgen binary checksum mismatch')
    return paths


def tool_state(paths):
    return {name: {'sha256': digest(path)} for name, path in paths.items()}



def rust_remap_flags(snapshot, output, rustc):
    sysroot = Path(run([str(rustc), '--print', 'sysroot']).decode().strip()).resolve()
    paths = (snapshot.resolve(), output.resolve(), sysroot)
    if any(any(c.isspace() for c in str(path)) for path in paths):
        raise ValueError('Kbuild paths must not contain whitespace')
    return ' '.join('--remap-path-prefix=' + str(path) + '/=' + replacement
                    for path, replacement in zip(paths, ('', '', 'rust-toolchain/')))


def state(args):
    source, _ = source_state(args.source.resolve())
    return {'schema': 2, 'source': source, 'config': config_state(args.config, args.localversion),
            'tools': tool_state(tool_paths(args)), 'recipe': RECIPE,
            'scope': 'Build qualification only; deployment and hardware untested'}


def check(args, expected):
    actual = state(args)
    for key in ('schema', 'source', 'config', 'tools', 'recipe'):
        if actual.get(key) != expected.get(key):
            raise ValueError('Build contract mismatch: ' + key)
    return actual


def rust_assertion_state(obj, nm):
    """Reject the deliberate unresolved Rust compile-time assertion trap."""
    undefined = run([str(nm), '--undefined-only', str(obj)])
    if any(line.split() and line.split()[-1] == b'rust_build_error' for line in undefined.splitlines()):
        raise ValueError('Unresolved Rust compile-time assertion in driver object')
    return {'status': 'PASS', 'unresolved_build_assertion': False}


def artifact_record(path, root):
    return {'path': str(path.relative_to(root)), 'sha256': digest(path),
            'bytes': path.stat().st_size}


def verify(bundle):
    manifest = read_json(bundle / 'manifest.json')
    if manifest.get('schema') != 1 or manifest.get('status') != 'COMPILED':
        raise ValueError('Unqualified artifact manifest')
    if not manifest.get('artifacts'):
        raise ValueError('Empty artifact manifest')
    for item in manifest['artifacts']:
        p = (bundle / item['path']).resolve()
        if not p.is_relative_to(bundle.resolve()) or not p.is_file():
            raise ValueError('Invalid artifact path')
        if p.stat().st_size != item['bytes'] or digest(p) != item['sha256']:
            raise ValueError('Artifact checksum mismatch: ' + item['path'])
    if manifest['contract_sha256'] != digest(bundle / 'contract.json'):
        raise ValueError('Contract checksum mismatch')
    if manifest['config_sha256'] != digest(bundle / '.config'):
        raise ValueError('Artifact config checksum mismatch')
    contract = read_json(bundle / 'contract.json')
    if contract.get('config', {}).get('sha256') != manifest['config_sha256']:
        raise ValueError('Artifact config does not match build contract')
    required = {'.config', 'Image', 'kernel.release', 'build.log'}
    if not required.issubset({x['path'] for x in manifest['artifacts']}):
        raise ValueError('Missing required artifacts')
    with open(bundle / 'Image', 'rb') as image:
        header = image.read(64)
    if len(header) != 64 or header[56:60] != b'ARMd':
        raise ValueError('Image is not an uncompressed AArch64 Linux Image')
    flags = struct.unpack_from('<Q', header, 24)[0]
    if flags & 1 or ((flags >> 1) & 3) != 2:
        raise ValueError('Image must use little endian 16 KiB pages')
    image_data = (bundle / 'Image').read_bytes()
    config_start = image_data.find(b'IKCFG_ST\x1f\x8b\x08')
    config_end = image_data.find(b'IKCFG_ED', config_start + 8) if config_start >= 0 else -1
    if config_start < 0 or config_end < 0:
        raise ValueError('Image lacks an embedded IKCONFIG payload')
    embedded_config = gzip.decompress(image_data[config_start + 8:config_end])
    if encoded_digest(embedded_config) != manifest['config_sha256']:
        raise ValueError('Embedded Image config does not match build contract')
    release = (bundle / 'kernel.release').read_text().strip()
    for item in manifest['artifacts']:
        if not item['path'].startswith('modules/'):
            continue
        raw = (bundle / item['path']).read_bytes()
        if raw[:4] != b'\x7fELF' or raw[4:6] != b'\x02\x01' or raw[18:20] != b'\xb7\x00':
            raise ValueError('Module is not ELF64 little-endian AArch64: ' + item['path'])
        index = raw.find(b'vermagic=')
        if index < 0 or not raw[index + 9:].split(b'\0', 1)[0].startswith((release + ' ').encode()):
            raise ValueError('Module release does not match Image: ' + item['path'])
    return manifest





def path_state(bundle):
    files = [bundle / 'Image', *sorted((bundle / 'modules').rglob('*.ko'))]
    prefixes = {'home_directory': str(Path.home()).encode() + b'/',
                'build_directory': str(bundle.resolve()).encode() + b'/'}
    results = []
    for path in files:
        data = path.read_bytes()
        matches = {name: data.count(prefix) for name, prefix in prefixes.items()}
        if any(matches.values()):
            raise ValueError('Private absolute build paths remain in artifact: ' + str(path.relative_to(bundle)))
        results.append({'path': str(path.relative_to(bundle)), 'private_prefix_matches': matches})
    return {'status': 'PASS', 'artifacts': results, 'scope': 'Actual host home and build directory prefixes'}


def compare(first, second):
    if first.resolve() == second.resolve():
        raise ValueError('Independent build directories are required')
    a, b = verify(first), verify(second)
    if (first / 'Image').samefile(second / 'Image'):
        raise ValueError('Independent Image files are required')
    if read_json(first / 'contract.json') != read_json(second / 'contract.json'):
        raise ValueError('Build contracts differ; not a reproducibility comparison')
    if (first / 'kernel.release').read_bytes() != (second / 'kernel.release').read_bytes():
        raise ValueError('Kernel releases differ')
    select = lambda manifest: {x['path']: x['sha256'] for x in manifest['artifacts']
                               if x['path'] == 'Image' or x['path'].startswith('modules/')}
    left, right = select(a), select(b)
    differences = [{'path': name, 'first_sha256': left.get(name), 'second_sha256': right.get(name)}
                   for name in sorted(left.keys() | right.keys()) if left.get(name) != right.get(name)]
    return {'status': 'DIFFERENT' if differences else 'BYTE_IDENTICAL',
            'compared_artifacts': len(left.keys() | right.keys()),
            'differences': differences, 'hardware': 'UNTESTED',
            'scope': 'Image and every matching module; logs and build directory paths excluded'}


def layout_state(output):
    generated = output / 'rust/bindings/bindings_generated.rs'
    command = output / 'rust/bindings/.bindings_generated.rs.cmd'
    obj = output / 'rust/bindings.o'
    text = generated.read_text()
    flags = command.read_text()
    blocks = len(re.findall(r'const\s*_\s*:\s*\(\)\s*=', text))
    offsets = len(re.findall(r'offset_of\s*!', text))
    if '--target=aarch64-linux-gnu' not in flags or '--no-layout-tests' in flags:
        raise ValueError('Missing AArch64 target or disabled binding layout checks')
    if not blocks or not offsets or not obj.is_file() or not obj.stat().st_size:
        raise ValueError('Unconditional binding layout checks were not compiled')
    return {'status': 'PASS', 'target': 'aarch64-linux-gnu',
            'const_layout_blocks': blocks, 'field_offset_checks': offsets,
            'layout_checks_disabled': False,
            'generated_bindings_sha256': digest(generated),
            'compiled_bindings_object_sha256': digest(obj),
            'compiled_bindings_object_bytes': obj.stat().st_size,
            'hardware_executed': False}


def build(args, contract):
    check(args, contract)
    dest = args.output.resolve()
    dest.mkdir(parents=True, exist_ok=False)
    source = args.source.resolve()
    snapshot = dest / 'source'
    snapshot.mkdir()
    # Copy committed and dirty source into a standalone tree. The shared tree is read only.
    with tempfile.TemporaryFile() as archive:
        subprocess.run(['git', 'archive', contract['source']['head']], cwd=source,
                       stdout=archive, check=True)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as tf:
            tf.extractall(snapshot, filter='data')
    captured, diff = source_state(source)
    if captured != contract['source']:
        raise ValueError('Source drift before dirty snapshot')
    if diff:
        subprocess.run(['git', 'apply', '--binary', '-'], cwd=snapshot,
                       input=diff, check=True)
    for name in contract['source']['untracked']:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
        if digest(target) != contract['source']['untracked'][name]:
            raise ValueError('Untracked source changed during copy: ' + name)
    check(args, contract)  # Refuse source/config/tool drift during snapshotting.
    paths = tool_paths(args)
    out = dest / 'build'
    out.mkdir()
    shutil.copyfile(args.config, out / '.config')
    if digest(out / '.config') != contract['config']['sha256']:
        raise ValueError('Config changed during copy')
    bin_dir = dest / 'bin'
    bin_dir.mkdir()
    for name, p in paths.items():
        (bin_dir / name).symlink_to(p)
    env = {key: val for key, val in os.environ.items()
           if key in ('HOME', 'USER', 'LOGNAME', 'TMPDIR')}
    env.update(PATH=str(bin_dir) + ':/usr/bin:/bin', LANG='C', LC_ALL='C',
               KBUILD_BUILD_USER='j614s', KBUILD_BUILD_HOST='builder',
               KBUILD_BUILD_TIMESTAMP='Mon Oct 19 00:00:00 UTC 2026',
               KBUILD_BUILD_VERSION='1', SOURCE_DATE_EPOCH='1792368000')
    command = [str(paths['make']), '-C', str(snapshot), 'O=' + str(out),
               'ARCH=arm64', 'LLVM=1', 'LOCALVERSION=+',
               'KRUSTFLAGS=' + rust_remap_flags(snapshot, out, paths['rustc'])]
    for tool, variables in TOOL_VARS.items():
        for variable in variables:
            command.append(variable + '=' + str(bin_dir / tool))
    with open(dest / 'build.log', 'wb') as log:
        for targets in (['olddefconfig'], ['-j' + str(args.jobs), 'Image', 'modules']):
            result = subprocess.run(command + targets, env=env, stdout=log,
                                    stderr=subprocess.STDOUT)
            if result.returncode:
                raise ValueError('Kernel build failed; inspect local build.log')
    write_json(dest / 'layout-evidence.json', layout_state(out))
    check(args, contract)
    if digest(out / '.config') != contract['config']['sha256']:
        raise ValueError('Kconfig changed; review and re-lock normalized config')
    shutil.copyfile(out / '.config', dest / '.config')
    shutil.copyfile(out / 'arch/arm64/boot/Image', dest / 'Image')
    shutil.copyfile(out / 'include/config/kernel.release', dest / 'kernel.release')
    # Keep module paths and include every built module, not just the bootstrap driver.
    for module in out.rglob('*.ko'):
        target = dest / 'modules' / module.relative_to(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(module, target)
    write_json(dest / 'path-audit.json', path_state(dest))
    write_json(dest / 'contract.json', contract)
    artifacts = [dest / p for p in ('.config', 'Image', 'kernel.release', 'build.log', 'layout-evidence.json', 'path-audit.json')]
    artifacts += sorted((dest / 'modules').rglob('*.ko'))
    manifest = {'schema': 1, 'status': 'COMPILED', 'hardware': 'UNTESTED',
                'contract_sha256': digest(dest / 'contract.json'),
                'config_sha256': digest(dest / '.config'),
                'artifacts': [artifact_record(p, dest) for p in artifacts]}
    write_json(dest / 'manifest.json', manifest)
    verify(dest)
    print('COMPILED; artifact checks pass; hardware UNTESTED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('lock', 'check', 'build', 'verify', 'layout-check', 'compare', 'path-check'))
    parser.add_argument('--source', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--bindgen', type=Path)
    parser.add_argument('--tool-dir', type=Path)
    parser.add_argument('--contract', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--against', type=Path)
    parser.add_argument('--localversion', help='Reviewed CONFIG_LOCALVERSION profile override')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    try:
        if args.action == 'path-check':
            if args.output is None:
                parser.error('--output is required')
            print(json.dumps(path_state(args.output), indent=2, sort_keys=True))
            return
        if args.action == 'compare':
            if args.output is None or args.against is None:
                parser.error('--output and --against are required')
            result = compare(args.output, args.against)
            print(json.dumps(result, indent=2, sort_keys=True))
            if result['status'] != 'BYTE_IDENTICAL':
                sys.exit(1)
            return
        if args.action == 'layout-check':
            if args.output is None:
                parser.error('--output is required')
            print(json.dumps(layout_state(args.output), indent=2, sort_keys=True))
            return
        if args.action == 'verify':
            if args.output is None:
                parser.error('--output is required')
            verify(args.output)
            print('PASS: artifact integrity (not a hardware qualification)')
            return
        for name in ('source', 'config', 'bindgen', 'tool_dir', 'contract'):
            if getattr(args, name) is None:
                parser.error('--' + name.replace('_', '-') + ' is required')
        if args.action == 'lock':
            if args.contract.exists():
                raise ValueError('Refusing to overwrite an existing build contract')
            write_json(args.contract, state(args))
            print('PASS: build contract captured')
        elif args.action == 'check':
            check(args, read_json(args.contract))
            print('PASS: source, config, and critical tools match')
        else:
            if args.output is None or args.jobs < 1:
                parser.error('--output and positive --jobs required')
            build(args, read_json(args.contract))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
