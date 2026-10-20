#!/usr/bin/env python3
"""Validate source-built artifact consistency without hardware or DRM access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def require(value, reason):
    if not value:
        raise ValueError(reason)


def verify(prefix):
    parts = {name: Path(str(prefix) + '.' + name).read_bytes()
             for name in ('shader.bin', 'entries.bin', 'resources.bin', 'launch.bin', 'cdm.bin', 'expected.bin')}
    manifest = json.loads(Path(str(prefix) + '.json').read_text())
    require(manifest['offline_template'] and not manifest['virtual_addresses_are_allocated'], 'template must retain unallocated status')
    require(manifest['hardware_execution'] == 'UNTESTED', 'hardware claim without execution evidence')
    sizes = {'shader.bin': manifest['shader_binary_size'], 'entries.bin': 0x400,
             'resources.bin': 0x100, 'launch.bin': 0x400, 'cdm.bin': 0x34, 'expected.bin': 1024}
    require(all(len(data) == sizes[name] for name, data in parts.items()), 'artifact sizes differ from source contract')
    profile = manifest['profile']
    require(profile['abi'] == 1 and profile['resource_binding'] == [0] and profile['resource_kind'] == [0] and
            profile['resource_write_mask'] == 1 and profile['resource_read_mask'] == 0 and profile['local_size'] == [256, 1, 1],
            'not the narrow one-output constant-store profile')
    require(profile['preamble_size'] == profile['scratch_size'] == profile['required_threadgroup_memory_bytes'] == 0,
            'unexpected shader runtime requirements')
    addresses = {key: int(value, 0) for key, value in manifest['addresses'].items()}
    resources = parts['resources.bin']
    require(struct.unpack_from('<QQ', resources) == (addresses['resource'] + 0xc0, addresses['output']), 'resource roots differ')
    require(struct.unpack_from('<III', resources, 0xc0) == (1, 1, 1), 'not one direct workgroup')
    require(struct.unpack_from('<I', parts['entries.bin'])[0] == 0x340 and
            struct.unpack_from('<I', parts['entries.bin'], 0x340)[0] == 0xc0, 'entry header/block size differs')
    cdm = parts['cdm.bin']
    require(struct.unpack_from('<IIIIII', cdm, 0x10) == (256, 1, 1, 256, 1, 1), 'CDM global/local geometry differs')
    require(struct.unpack_from('<I', cdm, 0x30)[0] == 0, 'terminator padding is nonzero')
    require(int(manifest['cmd_compute']['cdm_ctrl_stream_end'], 0) - addresses['cdm'] == 0x30,
            'UAPI end must match runtime first-terminator-word convention')
    require(struct.unpack('<256I', parts['expected.bin']) == (42,) * 256, 'expected output is not constant42')
    return {'status': 'WORKS for offline artifact consistency', 'hardware_execution': 'UNTESTED',
            'components': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in parts.items()},
            'expected_runtime_acceptance': 'Compare all256 u32 words to42 plus untouched BO/page canaries and successful completion fence; no such hardware result exists yet.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(verify(args.prefix), indent=2) + '\n')


if __name__ == '__main__':
    main()
