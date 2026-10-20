#!/usr/bin/env python3
"""Offline packaging only. Never executes init or accesses a target device."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess

HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / 'pins.json').read_text())
APPLETS = set('sh mount sleep cat printf timeout uname tr grep gzip sha256sum ls wc mkdir ln stty blockdev insmod usleep mv dmesg kill'.split())
DIRS = ['bin', 'dev', 'proc', 'sys', 'sys/kernel', 'sys/kernel/config', 'run', 'etc', 'lib', 'lib/modules']
REGULAR = {'init', 'bin/busybox', 'etc/expected-release', 'etc/expected-config-sha256',
           'etc/probe-manifest.json', 'lib/probe-state.sh', 'lib/modules/nvme-core.ko', 'lib/modules/nvme-apple.ko'}
NODES = {'dev/console': (5, 1), 'dev/null': (1, 3)}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pinned_file(path, expected):
    require(path.is_file() and not path.is_symlink(), 'Missing or symbolic input: ' + path.name)
    data = path.read_bytes()
    require(sha(data) == expected, 'Unreviewed input digest: ' + path.name)
    return data


def arm64_elf(data, static=False):
    require(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01' and data[18:20] == b'\xb7\0', 'Expected little-endian AArch64 ELF64')
    require(struct.unpack_from('<H', data, 52)[0] == 64, 'Invalid ELF header')
    if static:
        offset = struct.unpack_from('<Q', data, 32)[0]
        size, count = struct.unpack_from('<HH', data, 54)
        require(size >= 56 and count > 0 and offset + size * count <= len(data), 'Invalid ELF program headers')
        require(all(struct.unpack_from('<I', data, offset + i * size)[0] != 3 for i in range(count)), 'BusyBox must have no dynamic interpreter')


def validate_kernel(bundle, verifier):
    # Exact manifest and contract qualification precede importing any helper code.
    manifest = json.loads(pinned_file(bundle / 'manifest.json', PINS['manifest_sha256']))
    contract = json.loads(pinned_file(bundle / 'contract.json', PINS['contract_sha256']))
    require(contract['schema'] == 2 and contract['source']['head'] == PINS['source'], 'Unexpected source contract')
    require(contract['source']['untracked'] == {} and contract['source']['dirty_diff_sha256'] == sha(b''), 'Dirty source contract')
    pinned_file(verifier, PINS['verifier_sha256'])
    spec = importlib.util.spec_from_file_location('qualified_kernel_verifier', verifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify(bundle)  # Every original artifact + ARMd16K + embedded config + ELF/vermagic.
    pinned_file(bundle / '.config', PINS['config_sha256'])
    pinned_file(bundle / 'Image', PINS['image_sha256'])
    require((bundle / 'kernel.release').read_text() == PINS['release'] + '\n', 'Wrong kernel release')
    config = (bundle / '.config').read_text().splitlines()
    for name in ['BLK_DEV_INITRD', 'RD_GZIP', 'DEVTMPFS', 'PROC_FS', 'SYSFS', 'TMPFS', 'CONFIGFS_FS',
                 'USB_DWC3_APPLE', 'USB_CONFIGFS', 'USB_CONFIGFS_ACM', 'USB_F_ACM', 'TTY']:
        require('CONFIG_' + name + '=y' in config, 'Missing built-in probe capability ' + name)
    for name in ['NVME_CORE', 'NVME_APPLE']:
        require('CONFIG_' + name + '=m' in config, 'NVMe must remain modular')
    require('# CONFIG_UEVENT_HELPER is not set' in config, 'Re-review device RO strategy')
    modules = {}
    for name, digest in PINS['modules'].items():
        data = pinned_file(bundle / 'modules/drivers/nvme/host' / name, digest)
        arm64_elf(data)
        vermagic = b'vermagic=' + (PINS['release'] + ' SMP preempt aarch64').encode() + b'\0'
        require(vermagic in data, 'Exact module vermagic mismatch')
        dependency = b'depends=' + (b'nvme-core' if name == 'nvme-apple.ko' else b'') + b'\0'
        require(dependency in data, 'Module dependency changed')
        modules[name] = data
    return modules


def entry(mode, data=b'', rdev=(0, 0)):
    return (mode, data, rdev)


def archive(entries):
    out = bytearray()
    for ino, (name, (mode, data, rdev)) in enumerate([*entries.items(), ('TRAILER!!!', entry(0))], 1):
        name = name.encode('ascii') + b'\0'
        values = [ino, mode, 0, 0, 1, 0, len(data), 0, 0, *rdev, len(name), 0]
        out.extend(b'070701' + ''.join(f'{v:08x}' for v in values).encode())
        out.extend(name)
        out.extend(b'\0' * (-len(out) % 4))
        out.extend(data)
        out.extend(b'\0' * (-len(out) % 4))
    return bytes(out)


def unpack(raw):
    require(len(raw) <= 8 * 1024 * 1024, 'Archive exceeds bounded probe size')
    entries = {}; off = 0
    for _ in range(100):
        require(raw[off:off+6] == b'070701', 'Expected newc header')
        header = raw[off+6:off+110]
        require(len(header) == 104, 'Truncated newc header')
        fields = [int(header[i:i+8], 16) for i in range(0, 104, 8)]
        _, mode, uid, gid, links, mtime, size, major, minor, rmajor, rminor, length, check = fields
        require(uid == gid == mtime == major == minor == check == 0 and links == 1, 'Noncanonical archive metadata')
        require(1 < length <= 256 and 0 <= size <= 3 * 1024 * 1024, 'Unbounded entry')
        off += 110
        encoded = raw[off:off+length]
        require(len(encoded) == length and encoded[-1:] == b'\0' and b'\0' not in encoded[:-1], 'Invalid archive name')
        name = encoded[:-1].decode('ascii')
        off = (off + length + 3) & ~3
        data = raw[off:off+size]
        require(len(data) == size, 'Truncated archive body')
        off = (off + size + 3) & ~3
        if name == 'TRAILER!!!':
            require(mode == size == rmajor == rminor == 0 and not any(raw[off:]), 'Invalid archive trailer')
            required = set(DIRS) | set(NODES) | REGULAR | {'bin/' + app for app in APPLETS}
            require(set(entries) == required, 'Incomplete probe payload set')
            return entries
        require(name not in entries and not name.startswith('/') and str(PurePosixPath(name)) == name and
                all(p not in ('.', '..') for p in name.split('/')), 'Unsafe or duplicate archive path')
        require(not mode & 0o7000, 'Set-ID/sticky archive entry')
        kind = stat.S_IFMT(mode)
        if name in DIRS:
            require(mode == stat.S_IFDIR | 0o755 and not data and (rmajor, rminor) == (0, 0), 'Invalid directory')
        elif name in NODES:
            require(mode == stat.S_IFCHR | 0o600 and not data and (rmajor, rminor) == NODES[name], 'Invalid device node')
        elif name.startswith('bin/') and name[4:] in APPLETS:
            require(mode == stat.S_IFLNK | 0o777 and data == b'busybox' and (rmajor, rminor) == (0, 0), 'Unsafe applet link')
        else:
            require(name in REGULAR and kind == stat.S_IFREG and
                    mode == stat.S_IFREG | (0o755 if name in ('init', 'bin/busybox') else 0o644) and
                    (rmajor, rminor) == (0, 0), 'Unexpected archive payload')
        entries[name] = (mode, data, (rmajor, rminor))
    raise ValueError('Missing archive trailer')


def validate_archive(raw, expected):
    actual = unpack(raw)
    require(actual == expected, 'Archive differs from qualified payload set')
    return {name: {'sha256': sha(data), 'bytes': len(data), 'mode': oct(mode), 'rdev': list(rdev)}
            for name, (mode, data, rdev) in actual.items()}


def build(bundle, verifier, busybox, emulator, output):
    require(not output.exists(), 'Output must be a new directory')
    require(not output.resolve().is_relative_to(bundle.resolve()), 'Do not write inside kernel bundle')
    modules = validate_kernel(bundle, verifier)
    bb = pinned_file(busybox, PINS['busybox_sha256'])
    arm64_elf(bb, static=True)
    # Execute only qualified public BusyBox --list and parse-only sh -n under an
    # existing explicitly supplied emulator. Never execute init, even in chroot.
    result = subprocess.run([str(emulator), str(busybox), '--list'], check=True, capture_output=True, text=True)
    available = set(result.stdout.splitlines())
    require(APPLETS <= available, 'Missing required BusyBox applet(s): ' + ', '.join(sorted(APPLETS - available)))
    for script in ['init', 'probe-state.sh']:
        subprocess.run([str(emulator), str(busybox), 'sh', '-n', str(HERE / script)], check=True)
    manifest = {'schema': 1, 'purpose': 'RAM-only manual NVMe enumeration probe', 'pins': PINS,
                'hardware': 'UNTESTED', 'gadget_runtime': 'UNTESTED',
                'limits': ['No loader/DT/firmware/boot entry provided', 'No recovery/watchdog guarantee',
                           'Only physical USB diagnostics; no arbitrary shell or networking',
                           'RO polling interval 50ms; not atomic kernel RO-at-creation',
                           'No disk filesystem mounts or read/write workloads',
                           'USB configured plus explicit probe command required before NVMe load']}
    entries = {name: entry(stat.S_IFDIR | 0o755) for name in DIRS}
    entries.update({name: entry(stat.S_IFCHR | 0o600, rdev=dev) for name, dev in NODES.items()})
    entries['init'] = entry(stat.S_IFREG | 0o755, (HERE / 'init').read_bytes())
    entries['lib/probe-state.sh'] = entry(stat.S_IFREG | 0o644, (HERE / 'probe-state.sh').read_bytes())
    entries['bin/busybox'] = entry(stat.S_IFREG | 0o755, bb)
    for name in sorted(APPLETS):
        entries['bin/' + name] = entry(stat.S_IFLNK | 0o777, b'busybox')
    for name, data in modules.items():
        entries['lib/modules/' + name] = entry(stat.S_IFREG | 0o644, data)
    for name, data in {'expected-release': PINS['release'] + '\n',
                       'expected-config-sha256': PINS['config_sha256'] + '\n',
                       'probe-manifest.json': json.dumps(manifest, indent=2, sort_keys=True) + '\n'}.items():
        entries['etc/' + name] = entry(stat.S_IFREG | 0o644, data.encode())
    raw = archive(entries)
    records = validate_archive(raw, entries)
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    require(gzip.decompress(compressed) == raw, 'Compression round-trip mismatch')
    output.mkdir(parents=True)
    (output / 'initrd.cpio.gz').write_bytes(compressed)
    record = {'schema': 1, 'status': 'OFFLINE_VALIDATED', 'hardware': 'UNTESTED',
              'kernel_source': PINS['source'], 'kernel_image_sha256': PINS['image_sha256'],
              'initrd_sha256': sha(compressed), 'initrd_bytes': len(compressed),
              'cpio_sha256': sha(raw), 'cpio_bytes': len(raw), 'entries': records,
              'checks': ['full pinned kernel bundle verification', 'two exact AArch64 modules/vermagic/dependencies',
                         'pinned static AArch64 BusyBox and required applets', 'BusyBox sh -n only',
                         'bounded canonical newc archive with exact payload equality', 'gzip round-trip'],
              'emulator_sha256': sha(emulator.read_bytes()), 'busybox_provenance_sha256': sha((HERE / 'busybox-provenance.json').read_bytes())}
    (output / 'packaging.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['bundle', 'verifier', 'busybox', 'emulator', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    record = build(args.bundle.resolve(), args.verifier.resolve(), args.busybox.resolve(), args.emulator.resolve(), args.output)
    print(json.dumps({k: record[k] for k in ['status', 'hardware', 'initrd_sha256', 'initrd_bytes']}, sort_keys=True))


if __name__ == '__main__':
    main()
