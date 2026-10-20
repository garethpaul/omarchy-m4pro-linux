#!/usr/bin/env python3
"""Offline G16S observation projection. Never selects a Mesa runtime profile."""
import argparse
import hashlib
import json
from pathlib import Path


def candidate(observation):
    regs = observation['id_registers']
    def value(offset):
        raw = regs[offset]
        return int(raw, 0) if isinstance(raw, str) else raw
    gpu_id, counts = value('0xd04000'), value('0xd04010')
    masks = [value(key) for key in ('0xe01500', '0xe01504', '0xe01508')]
    if gpu_id != 0x0a031100 or counts != 0x11020a or masks != [0xf6fdb, 0, 0]:
        raise ValueError('observation differs from measured J614s G16S ID/count/mask')
    if observation['exceptions'] != 0 or observation['firmware_started']:
        raise ValueError('expected exception-free, firmware-not-started identity measurement')
    cluster_masks = [(masks[0] >> (10 * c)) & 0x3ff for c in range(2)]
    if [mask.bit_count() for mask in cluster_masks] != [8, 8]:
        raise ValueError('expected eight enabled cores in each of two physical ten-core clusters')
    return {'status': 'PARTIAL', 'runtime_enabled': False, 'shader_execution': 'UNTESTED',
            'measured': {'id': hex(gpu_id), 'core_counts': hex(counts), 'packed_core_mask': hex(masks[0]),
                         'cluster_masks': [hex(v) for v in cluster_masks], 'enabled_per_cluster': [8, 8]},
            'expected_known_uapi_fields': {'gpu_generation': 16, 'gpu_variant': ord('S'), 'chip_id': 0x6040,
                                           'num_dies': 1, 'num_clusters_total': 2, 'num_cores_per_cluster': 10,
                                           'core_masks': cluster_masks},
            'unknown_required_fields': ['VM limits and kernel carveout', 'firmware/power state',
                                        'fragment geometry', 'USC execution semantics on G16S'],
            'warning': 'Identity/geometry candidates only; do not alias G16S to G16G or open a full runtime profile.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = args.observation.read_bytes()
    result = candidate(json.loads(data))
    result['source_sha256'] = hashlib.sha256(data).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
