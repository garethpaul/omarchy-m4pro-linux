#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline CPU/PMGR ADT projection. Never connects to hardware or writes MMIO.

ADT binary-format reference: Asahi m1n1 proxyclient/m1n1/adt.py (MIT,
The Asahi Linux Contributors). Only explicitly selected public hardware fields
are emitted; callers must never serialize the internal flat raw-property map.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


class LayoutError(ValueError):
    pass


def require(value, message):
    if not value:
        raise LayoutError(message)


def parse_adt(raw):
    require(8 <= len(raw) <= 16 * 1024 * 1024, 'ADT size out of bounds')
    offset, count = 0, 0
    nodes = {}
    def take(size):
        nonlocal offset
        require(0 <= size <= len(raw) - offset, 'truncated ADT')
        result = raw[offset:offset + size]
        offset += size
        return result
    def node(parent, depth):
        nonlocal count
        count += 1
        require(depth < 64 and count <= 4096, 'ADT nesting/node count out of bounds')
        props_count, children = struct.unpack('<II', take(8))
        require(props_count <= 1024 and children <= 4096, 'ADT node counts out of bounds')
        props = {}
        for _ in range(props_count):
            name = take(32).split(b'\0', 1)[0].decode('ascii')
            size = struct.unpack('<I', take(4))[0] & 0x7fffffff
            require(name not in props, 'duplicate ADT property')
            props[name] = take(size)
            take((-size) % 4)
        require('name' in props, 'ADT node has no name')
        name = props['name'].rstrip(b'\0').decode('ascii')
        require('/' not in name and name not in ('.', '..', ''), 'invalid ADT node name')
        full = parent + '/' + name
        key = full.removeprefix('/device-tree') or '/'
        candidate = key
        index = 1
        while candidate in nodes:
            index += 1
            candidate = f'{key}#{index}'
        nodes[candidate] = props
        for _ in range(children):
            node(full, depth + 1)
    node('', 0)
    # Runtime m1n1 capture includes a zero-filled 16KiB allocation tail.
    tail = raw[offset:]
    require(not tail or (len(raw) % 16384 == 0 and len(tail) < 16384 and not any(tail)),
            'unexpected non-padding bytes after ADT')
    return nodes


def strings(raw):
    return [part.decode('ascii') for part in raw.rstrip(b'\0').split(b'\0') if part]


def u32(raw):
    require(len(raw) == 4, 'expected one ADT u32')
    return struct.unpack('<I', raw)[0]


def records(raw, fmt):
    require(len(raw) % struct.calcsize(fmt) == 0, 'malformed ADT record geometry')
    return list(struct.iter_unpack(fmt, raw))


def translate(ranges, address, size):
    require(0 <= address < 2**64 and 0 < size <= 2**64 - address, 'invalid address span')
    found = []
    for child, parent, length in ranges:
        require(child + length <= 2**64 and parent + length <= 2**64, 'invalid ARM-IO range')
        if child <= address and address + size <= child + length:
            found.append(parent + address - child)
    require(len(found) == 1 and found[0] + size <= 2**64, 'CPU register span has no unique translation')
    return found[0]


BASES = [0x210e20000, 0x211e20000, 0x212e20000]
TABLES = ['voltage-states1-sram', 'voltage-states5-sram', 'voltage-states13-sram']


def project(raw):
    nodes = parse_adt(raw)
    root, pmgr = nodes['/'], nodes['/arm-io/pmgr']
    ranges = records(nodes['/arm-io']['ranges'], '<QQQ')
    apertures = []
    for index, (bus, size) in enumerate(records(pmgr['reg'], '<QQ')):
        physical = translate(ranges, bus, size)
        if physical in BASES:
            require(size == 0x2000, 'unexpected CPU CPM aperture size')
            apertures.append({'reg_index': index, 'bus': bus, 'physical': physical, 'size': size})
    require(len({a['physical'] for a in apertures}) == len(apertures), 'duplicate CPU CPM aperture')
    cpu_nodes = []
    for path, props in nodes.items():
        if path.startswith('/cpus/') and 'cpu-id' in props:
            cpu_nodes.append({'cpu_id': u32(props['cpu-id']), 'cluster_id': u32(props['cluster-id']),
                              'reg': u32(props['reg']), 'compatible': strings(props['compatible'])})
    tables = {}
    for name in TABLES:
        if name in pmgr:
            pairs = records(pmgr[name], '<II')
            require(2 <= len(pairs) <= 31, 'CPU SRAM table length out of bounds')
            # Zeros are expected in static vendor trees; only the runtime
            # qualification below interprets populated frequency candidates.
            tables[name] = [{'frequency_candidate_khz': f, 'sram_value': v} for f, v in pairs]
    structure = {}
    for name in ('perf-regs', 'perf-groups', 'perf-domains', 'clusters', 'cluster-ctl-offset', 'clpc'):
        if name in pmgr:
            structure[name] = {'bytes': len(pmgr[name]), 'sha256': hashlib.sha256(pmgr[name]).hexdigest()}
            if name in ('clusters', 'cluster-ctl-offset', 'clpc'):
                structure[name]['u32'] = [value[0] for value in records(pmgr[name], '<I')]
    related = {}
    for path in ('/arm-io/pmp', '/arm-io/dart-pmp'):
        props = nodes.get(path)
        if props is None:
            related[path] = {'present': False}
            continue
        related[path] = {'present': True, 'compatible': strings(props.get('compatible', b'')),
                         'registers': [{'physical': translate(ranges, bus, size), 'size': size}
                                       for bus, size in records(props.get('reg', b''), '<QQ')]}
    fingerprints = {}
    for path, props in nodes.items():
        if path in ('/arm-io/pmgr', '/arm-io/pmp', '/arm-io/dart-pmp') or path.startswith('/cpus/cpu'):
            fingerprints[path] = {name: hashlib.sha256(value).hexdigest() for name, value in props.items()}
    return {'source_sha256': hashlib.sha256(raw).hexdigest(), 'model': strings(root['model']),
            'root_compatible': strings(root['compatible']), 'board_id': u32(nodes['/chosen']['board-id']),
            'chip_id': u32(nodes['/chosen']['chip-id']),
            'pmgr_compatible': strings(pmgr['compatible']), 'cpu_apertures': sorted(apertures, key=lambda a: a['physical']),
            'cpus': sorted(cpu_nodes, key=lambda c: c['cpu_id']), 'cpu_sram_tables': tables,
            'pmgr_structure': structure, 'related_nodes': related, 'property_fingerprints': fingerprints}


def qualify_j614s(layout):
    require(layout['chip_id'] == 0x6040 and layout['model'] == ['Mac16,8'] and 'J614sAP' in layout['root_compatible'] and layout['board_id'] == 4,
            'not the captured J614s / Mac16,8 / board4')
    require(layout['pmgr_compatible'] == ['pmgr1,t6041'], 'unexpected PMGR compatible')
    require([(a['physical'], a['size']) for a in layout['cpu_apertures']] == [(base, 0x2000) for base in BASES],
            'expected exactly three T6040 CPM apertures')
    expected = [(i, 0, i) for i in range(4)] + [(i + 4, 1, 0x100 + i) for i in range(4)] + [(i + 10, 2, 0x200 + i) for i in range(4)]
    require([(c['cpu_id'], c['cluster_id'], c['reg']) for c in layout['cpus']] == expected,
            'J614s CPU cluster topology differs from captured ADT')
    for cpu in layout['cpus']:
        require(('apple,sawtooth' if cpu['cluster_id'] == 0 else 'apple,everest') in cpu['compatible'],
                'unexpected CPU compatible')
    require(set(layout['cpu_sram_tables']) == set(TABLES), 'missing per-cluster SRAM table')
    for name, rows in layout['cpu_sram_tables'].items():
        require(2 <= len(rows) <= 31, 'CPU SRAM table length out of bounds')
        frequencies = [row['frequency_candidate_khz'] for row in rows]
        require(all(0 < f <= 5000000 for f in frequencies), 'runtime frequency candidate is zero/out of bounds')
        require(all(a < b for a, b in zip(frequencies, frequencies[1:])), 'frequency candidates not strictly increasing')
        require(all(0 < row['sram_value'] < 5000 for row in rows), 'SRAM value out of bounds')
    return layout


def probe_plan(layout):
    qualify_j614s(layout)
    return {'status': 'UNTESTED', 'mode': 'READ_ONLY_CANDIDATE',
            'warning': 'Addresses are ADT-derived. J614s command semantics and access safety require primary qualification. Do not write or enable power.',
            'identity': {'chip_id': 0x6040, 'board_id': 4, 'model': 'Mac16,8', 'source_adt_sha256': layout['source_sha256']},
            'reads': [{'cluster': c, 'physical': base + 0x20, 'width_bits': 64,
                       'meaning': 'candidate CPM command register; low5 state is unqualified'} for c, base in enumerate(BASES)],
            'exclude': ['MMIO writes', 'power/clock enable', 'watchdog changes', 'DVFS transitions', 'M3 status/PLL assumptions'],
            'before': ['Exact idle resident proxy and live identity/ADT geometry recheck',
                       'Primary verifies existing watchdog/recovery condition; collector must not change it',
                       'Initial read only on CPU-cluster apertures already powered by firmware; do not power a block to read it'],
            'capture': ['Read all three registers twice, recording widths, monotonic timestamps and exception count',
                        'Stop on busy bit, inconsistent low5, exception or geometry change',
                        'Preserve raw register words. Decode candidate request state only; never label it measured MHz.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', type=Path, required=True)
    parser.add_argument('--m2', type=Path, required=True)
    parser.add_argument('--m3', type=Path, required=True)
    parser.add_argument('--static-m4', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    layouts = {name: project(path.read_bytes()) for name, path in [('live_t6040', args.live), ('static_t8112', args.m2),
                                                                  ('static_t8122', args.m3), ('static_t6040', args.static_m4)]}
    qualify_j614s(layouts['live_t6040'])
    diffs = {}
    live_nodes = layouts['live_t6040']['property_fingerprints']
    for label in ('static_t8112', 'static_t8122', 'static_t6040'):
        old_nodes = layouts[label]['property_fingerprints']
        diffs[label] = {}
        for path, props in live_nodes.items():
            other = old_nodes.get(path)
            diffs[label][path] = {'present': other is not None,
                                 'changed_properties': sorted(name for name in set(props) | set(other or {})
                                                              if props.get(name) != (other or {}).get(name))}
    # Property-name differences are reviewable; their raw payloads remain private.
    for item in layouts.values():
        del item['property_fingerprints']
    result = {'schema': 1, 'status': 'PARTIAL', 'hardware_semantics': 'UNTESTED', 'raw_adt_exported': False,
              'comparison_limit': 'M2/M3/M4 static trees are 25G76; live M4 is runtime. Static missing/populated tables do not establish an SoC difference.',
              'layouts': layouts, 'node_diffs': diffs, 'next_probe': probe_plan(layouts['live_t6040'])}
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
