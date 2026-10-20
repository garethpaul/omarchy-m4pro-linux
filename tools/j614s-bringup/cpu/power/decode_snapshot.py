#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Decode a primary-collected, read-only CPM snapshot. No hardware access."""
import argparse
import json
import time
from pathlib import Path
from layout import BASES, TABLES, qualify_j614s, require


def decode(layout, snapshot):
    qualify_j614s(layout)
    identity = snapshot['identity']
    require(identity == {'chip_id': 0x6040, 'board_id': 4, 'model': 'Mac16,8',
                         'source_adt_sha256': layout['source_sha256']}, 'snapshot identity/ADT mismatch')
    require(snapshot['exceptions_before'] == snapshot['exceptions_after'] == 0, 'proxy exception recorded')
    samples = snapshot['samples']
    require(len(samples) >= 2, 'two or more distinct samples required')
    previous_time = -1
    previous_states = None
    decoded = []
    for sample in samples:
        timestamp = sample['monotonic_ns']
        require(type(timestamp) is int and timestamp > previous_time, 'sample timestamps not strictly increasing')
        previous_time = timestamp
        registers = sample['registers']
        require(len(registers) == 3, 'exactly three CPM command reads required')
        rows, seen = [], set()
        for register in registers:
            cluster = register['cluster']
            require(type(cluster) is int and cluster in range(3) and cluster not in seen, 'invalid/duplicate cluster')
            seen.add(cluster)
            require(register['physical'] == BASES[cluster] + 0x20 and register['width_bits'] == 64,
                    'unqualified register address/width')
            raw = register['value']
            require(type(raw) is int and 0 <= raw < 2**64, 'invalid register word')
            require(not raw & (1 << 31), 'candidate M3 BUSY bit is set; stop')
            state = raw & 31
            table = layout['cpu_sram_tables'][TABLES[cluster]]
            require(state <= len(table), 'low5 state outside both candidate table-index ranges')
            rows.append({'cluster': cluster, 'raw_hex': f'0x{raw:016x}', 'low5': state,
                         'one_based_frequency_candidate_khz': table[state - 1]['frequency_candidate_khz'] if state else None,
                         'zero_based_frequency_candidate_khz': table[state]['frequency_candidate_khz'] if state < len(table) else None})
        rows.sort(key=lambda r: r['cluster'])
        states = [row['low5'] for row in rows]
        require(previous_states is None or previous_states == states, 'low5 state changed between samples; owner/state is unstable')
        previous_states = states
        decoded.append({'monotonic_ns': timestamp, 'registers': rows})
    return {'status': 'PARTIAL', 'hardware_frequency': 'UNTESTED', 'writes_performed': False,
            'interpretation': 'Stable low5 command candidates only. Index origin and T6040 status meaning remain unqualified; neither candidate is measured frequency.',
            'source_adt_sha256': layout['source_sha256'], 'samples': decoded}


def capture_with_reader(layout, read64, exception_count, chip_id, monotonic_ns=time.monotonic_ns):
    """Primary-only integration seam, using an already qualified idle proxy.

    The primary must pass a layout freshly decoded from this proxy's live ADT,
    verify chip identity and firmware-powered clusters, and preserve the existing
    watchdog/recovery setup. No transport is opened here. This helper performs
    only the six exact candidate reads; it never changes a register or policy.
    """
    qualify_j614s(layout)
    require(chip_id == 0x6040, 'live proxy chip ID mismatch')
    before = exception_count()
    require(before == 0, 'pre-existing proxy exception')
    snapshot = {'identity': {'chip_id': 0x6040, 'board_id': 4, 'model': 'Mac16,8',
                             'source_adt_sha256': layout['source_sha256']},
                'exceptions_before': before, 'samples': []}
    for _ in range(2):
        sample = {'monotonic_ns': monotonic_ns(), 'registers': []}
        for cluster, base in enumerate(BASES):
            value = read64(base + 0x20)
            require(exception_count() == 0, 'proxy exception after candidate CPM read; stop')
            require(type(value) is int and 0 <= value < 2**64 and not value & (1 << 31),
                    'invalid/busy CPM candidate; stop')
            require((value & 31) <= len(layout['cpu_sram_tables'][TABLES[cluster]]),
                    'CPM low5 outside candidate ranges; stop')
            sample['registers'].append({'cluster': cluster, 'physical': base + 0x20,
                                        'width_bits': 64, 'value': value})
        snapshot['samples'].append(sample)
    snapshot['exceptions_after'] = exception_count()
    decode(layout, snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    layout = json.loads(args.comparison.read_text())['layouts']['live_t6040']
    result = decode(layout, json.loads(args.snapshot.read_text()))
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
