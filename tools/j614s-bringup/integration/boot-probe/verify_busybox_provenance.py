#!/usr/bin/env python3
"""Reverify retained public Debian evidence; no network, install or init execution."""
import argparse
import io
import json
import lzma
from pathlib import Path
import subprocess
import tarfile
import tempfile
from build_probe import HERE, PINS, arm64_elf, pinned_file, require, sha


def verify(cache):
    provenance = json.loads((HERE / 'busybox-provenance.json').read_text())
    files = {name: pinned_file(cache / name, digest) for name, digest in provenance['files'].items()}
    with tempfile.TemporaryDirectory(prefix='j614s-public-keys-') as tmp:
        root = Path(tmp)
        keys = files['debian-archive-12.asc'] + files['debian-archive-13.asc']
        armored = root / 'archive.asc'; armored.write_bytes(keys)
        keyring = root / 'archive.gpg'
        subprocess.run(['gpg', '--no-options', '--homedir', tmp, '--batch', '--dearmor', '--output', str(keyring), str(armored)], check=True, capture_output=True)
        status = subprocess.run(['gpgv', '--homedir', tmp, '--status-fd', '1', '--keyring', str(keyring), str((cache / 'InRelease').resolve())], check=True, capture_output=True, text=True)
        valid = {line.split()[-1] for line in status.stdout.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')}
        require(valid == set(provenance['archive_primary_fingerprints']), 'Archive signer fingerprint mismatch')
    signed = files['InRelease'].decode()
    sha_section = signed.split('\nSHA256:\n', 1)[1].split('\n\n', 1)[0]
    matches = [line.split() for line in sha_section.splitlines() if line.endswith(' main/binary-arm64/Packages.xz')]
    require(len(matches) == 1, 'Missing unique signed package-index digest')
    digest, size, _ = matches[0]
    require(sha(files['Packages.xz']) == digest and len(files['Packages.xz']) == int(size), 'Signed package-index mismatch')
    paragraphs = lzma.decompress(files['Packages.xz']).decode().split('\n\n')
    package = [p for p in paragraphs if p.startswith('Package: busybox-static\n')]
    require(len(package) == 1, 'Expected one busybox-static paragraph')
    fields = dict(line.split(': ', 1) for line in package[0].splitlines() if ': ' in line and not line.startswith(' '))
    require(fields['Version'] == provenance['version'] and fields['Architecture'] == 'arm64', 'Wrong native package')
    deb = files['busybox-static.deb']
    require(sha(deb) == fields['SHA256'] and len(deb) == int(fields['Size']), 'Signed package payload mismatch')
    require(deb[:8] == b'!<arch>\n', 'Expected Debian ar container')
    off = 8; payloads = []
    while off < len(deb):
        header = deb[off:off+60]
        require(len(header) == 60 and header[-2:] == b'`\n', 'Invalid ar member')
        name = header[:16].decode().strip().rstrip('/'); size = int(header[48:58])
        data = deb[off+60:off+60+size]
        require(len(data) == size, 'Truncated ar member')
        if name.startswith('data.tar'):
            payloads.append(data)
        off += 60 + size + size % 2
    require(len(payloads) == 1, 'Expected exactly one Debian data archive')
    with tarfile.open(fileobj=io.BytesIO(payloads[0])) as archive:
        members = [m for m in archive.getmembers() if m.name.removeprefix('./') in ('bin/busybox', 'usr/bin/busybox')]
        require(len(members) == 1 and members[0].isfile(), 'Expected one regular BusyBox file')
        binary = archive.extractfile(members[0]).read()
    require(sha(binary) == PINS['busybox_sha256'] and binary == files['busybox'], 'Extracted BusyBox mismatch')
    arm64_elf(binary, static=True)
    return {'status': 'SIGNATURE_AND_PAYLOAD_VERIFIED', 'package': provenance['package'],
            'version': provenance['version'], 'architecture': 'arm64',
            'binary_sha256': sha(binary), 'signers': sorted(valid),
            'scope': 'Historical pinned signed repository evidence; no freshness or target execution claim'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    print(json.dumps(verify(parser.parse_args().cache), sort_keys=True))
