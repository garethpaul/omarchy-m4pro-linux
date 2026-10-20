#!/usr/bin/env python3
"""Read-only ARM inputs; all payload execution occurs inside bubblewrap."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import tarfile

QEMU_SHA = '66bdc286fd30970a1c3d2029b460605a3dc843ed6b397f4cd9825f9c19551507'
QUAL_SHA = '30ce53399b1029787133348e2c0074d4ac85a76d3c867dc744a71f3b2b2ade2c'
BASELINE_MANIFEST_SHA = '30a72f4608f94d7a4487e3529e7343bdf962a412d9c961b637a7bf196b54b947'
SOURCE_SHA = 'ee1c37fef7f501807d87b6700ffb6fc40da69982afd302f9b88333b78593feee'

def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(cmd, **kwargs):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('qualification', 'payload-cache', 'baseline', 'source', 'work', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--probe', type=Path, default=Path(__file__).with_name('probe.lua'))
    args = parser.parse_args()
    assert sha(Path('/usr/bin/qemu-aarch64-static').read_bytes()) == QEMU_SHA
    assert sha(args.qualification.read_bytes()) == QUAL_SHA
    check = checked(['pacman', '-Qkk', 'qemu-user-static'])
    assert '45 total files, 0 altered files' in check.stdout
    source_data = args.source.read_bytes()
    assert sha(source_data) == SOURCE_SHA, 'options callback source changed'
    proof = json.loads(args.qualification.read_text())
    records = {row['name']: row for row in proof['packages']}
    manifest_file = args.baseline / '_abi-restore-manifest.json'
    assert sha(manifest_file.read_bytes()) == BASELINE_MANIFEST_SHA
    manifest = json.loads(manifest_file.read_text())
    assert manifest['image_sha256'] == 'f6ceb11ef79914eaa10cc07637c929a99afe5982d216d8b89905c86e863b2491'
    entries = {row['path']: row for row in manifest['tree']['entries']}
    args.work.mkdir(exist_ok=False)
    root = args.work / 'root'
    (root / 'usr/bin').mkdir(parents=True)
    (root / 'usr/lib').mkdir()
    scratch = args.work / 'scratch'
    scratch.mkdir()
    (scratch / 'home').mkdir()
    (scratch / 'xdg').mkdir()
    inputs = []
    pending = []
    packages = []
    for name, executable in [('neovim', 'nvim'), ('shfmt', 'shfmt'), ('stylua', 'stylua')]:
        record = records[name]
        assert record['architecture'] == 'aarch64'
        assert record['cryptographic_signature'] == 'WORKS'
        assert record['pkginfo_identity'] == 'WORKS'
        package = args.payload_cache / record['sha256'] / record['filename']
        assert sha(package.read_bytes()) == record['sha256']
        assert package.stat().st_size == record['bytes']
        with tarfile.open(package) as archive:
            member = archive.getmember('usr/bin/' + executable)
            assert member.isfile() and member.mode & 0o111
            data = archive.extractfile(member).read()
        assert data[:4] == b'\x7fELF' and struct.unpack_from('<H', data, 18)[0] == 183
        dest = root / 'usr/bin' / executable
        dest.write_bytes(data)
        dest.chmod(0o755)
        pending.append(dest)
        inputs.append({'path': 'usr/bin/' + executable, 'sha256': sha(data), 'origin': record['filename']})
        packages.append({key: record[key] for key in ('name', 'version', 'sha256', 'filename', 'architecture', 'signing_fingerprint')})
    copied = set()
    while pending:
        binary = pending.pop()
        dynamic = checked(['readelf', '-d', str(binary)]).stdout
        headers = checked(['readelf', '-l', str(binary)]).stdout
        libraries = re.findall(r'\(NEEDED\).*\[([^]]+)\]', dynamic)
        interp = re.search(r'Requesting program interpreter: ([^]]+)\]', headers)
        if interp:
            libraries.append(PurePosixPath(interp.group(1)).name)
        for library in libraries:
            if library.startswith('/usr/lib/'):
                library = library.removeprefix('/usr/lib/')
            assert not library.startswith('/') and '..' not in PurePosixPath(library).parts and library not in ('', '.')
            source = (args.baseline / 'usr/lib' / library).resolve(strict=True)
            relative = source.relative_to(args.baseline.resolve())
            assert str(relative).startswith('usr/lib/')
            identity = entries[str(relative)]
            data = source.read_bytes()
            assert sha(data) == identity['sha256'], str(relative)
            destination = root / 'usr/lib' / library
            if library in copied:
                assert destination.read_bytes() == data
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            destination.chmod(0o755)
            copied.add(library)
            pending.append(destination)
            inputs.append({'path': 'usr/lib/' + library, 'sha256': sha(data), 'origin': 'verified baseline image: ' + str(relative)})
    (root / 'lib').symlink_to('usr/lib')
    (root / 'lib64').symlink_to('usr/lib')
    (root / 'native-formatters.lua').write_bytes(source_data)
    (root / 'etc').mkdir()
    (root / 'etc/passwd').write_text('root:x:0:0:Sandbox:/work/home:/nonexistent\n')
    lua = args.probe.read_bytes()
    (root / 'probe.lua').write_bytes(lua)
    for mountpoint in ('work', 'tmp', 'dev', 'proc'):
        (root / mountpoint).mkdir()
    (root / 'qemu').write_bytes(Path('/usr/bin/qemu-aarch64-static').read_bytes())
    (root / 'qemu').chmod(0o755)
    assert sha((root / 'qemu').read_bytes()) == QEMU_SHA
    # No host root, home, sockets or network is exposed. Only owned scratch is writable.
    command = ['bwrap', '--unshare-all', '--uid', '0', '--gid', '0', '--cap-drop', 'ALL',
               '--die-with-parent', '--new-session', '--ro-bind', str(root.resolve()), '/',
               '--bind', str(scratch.resolve()), '/work', '--tmpfs', '/tmp',
               '--dev', '/dev', '--proc', '/proc', '--chdir', '/work', '--clearenv',
               '--setenv', 'PATH', '/usr/bin', '--setenv', 'LANG', 'C',
               '--setenv', 'XDG_CONFIG_HOME', '/work/xdg/config', '--setenv', 'XDG_DATA_HOME', '/work/xdg/data',
               '--setenv', 'XDG_CACHE_HOME', '/work/xdg/cache', '--setenv', 'XDG_STATE_HOME', '/work/xdg/state',
               '--setenv', 'NVIM_LOG_FILE', '/work/nvim.log', '--']
    cases = []
    def invoke(name, argv, stdin=None, expected=0):
        result = subprocess.run(command + ['/qemu', '-L', '/', *argv], input=stdin,
                                capture_output=True, text=True, timeout=30)
        cases.append({'case': name, 'argv': ['/qemu', '-L', '/', *argv],
                      'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        assert result.returncode == expected, name + ': ' + result.stderr
        return result.stdout
    try:
        for name in ('shfmt', 'stylua', 'nvim'):
            invoke(name + '-version', ['/usr/bin/' + name, '--version'])
        sh_input = 'if true;then echo "arm64";fi\n'
        sh_output = invoke('shfmt-format', ['/usr/bin/shfmt', '-i', '2'], sh_input)
        assert sh_output == 'if true; then echo "arm64"; fi\n'
        assert invoke('shfmt-idempotent', ['/usr/bin/shfmt', '-i', '2'], sh_output) == sh_output
        lua_input = 'local  x={1,2}\nreturn x\n'
        lua_output = invoke('stylua-format', ['/usr/bin/stylua', '--indent-type', 'Spaces', '--indent-width', '2', '-'], lua_input)
        assert lua_output == 'local x = { 1, 2 }\nreturn x\n'
        assert invoke('stylua-idempotent', ['/usr/bin/stylua', '--indent-type', 'Spaces', '--indent-width', '2', '-'], lua_output) == lua_output
        invoke('neovim-native-options-and-isolation', ['/usr/bin/nvim', '--headless', '-u', 'NONE', '-i', 'NONE', '-n', '-l', '/probe.lua'])
        probe = json.loads((scratch / 'probe.json').read_text())
        assert all(probe['checks'].values()), probe
        status = 'WORKS (isolated ARM64 userspace checks only)'
    finally:
        result = {'schema': 1, 'status': locals().get('status', 'FAILED; see cases'),
                  'harness_sha256': sha(Path(__file__).read_bytes()),
                  'scope': 'Native formatter binaries and Neovim options callback under QEMU, not full LazyVim or target hardware',
                  'qualification_sha256': QUAL_SHA, 'baseline_manifest_sha256': sha(manifest_file.read_bytes()),
                  'baseline_image_sha256': manifest['image_sha256'], 'options_sha256': SOURCE_SHA, 'probe_sha256': sha(lua),
                  'emulator_sha256': QEMU_SHA, 'packages': packages, 'input_files': sorted(inputs, key=lambda row: row['path']),
                  'cases': cases, 'neovim_probe': locals().get('probe'), 'HOME_env_overridden': False,
                  'host_installation': False, 'target_access': False, 'network_namespace': True,
                  'full_lazyvim': 'UNTESTED', 'hardware': 'UNTESTED'}
        args.evidence.write_text(json.dumps(result, indent=2) + '\n')
    print(status)

if __name__ == '__main__':
    main()
