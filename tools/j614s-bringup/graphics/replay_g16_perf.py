#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline replay of actual kernel performance decoder on pinned private ADTs.

Reads files only. No target modules, firmware execution, or raw ADT export.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

TARGET_SHA = 'ee5d2412e0cee64ad8861bcdc3cb2301e393041b746355c8fd3759062f3cf96a'
BASELINES = {
    'j413ap': '2a0c26929ef8afbe7835816183f919a2bcfdc42a662429e67526f64babc9c88e',
    'j613ap': '6430fdc6da49c64025d038d50fdcff3c57dfe2b1f3d37052c12f1dc27e988c2f',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def select(root, path):
    found = []
    def walk(node, parent=''):
        names = [p.value for p in node.properties if p.name == 'name']
        require(len(names) == 1, 'Ambiguous node name')
        here = (parent + '/' + names[0].rstrip(b'\0').decode('ascii')).removeprefix('/device-tree')
        if here == path:
            found.append(node)
        for child in node.children:
            walk(child, here)
    walk(root)
    require(len(found) == 1, 'Ambiguous or missing SGX node')
    result = {}
    for prop in found[0].properties:
        require(prop.name not in result, 'Duplicate SGX property')
        result[prop.name] = prop.value
    return result


RUNNER = r'''
#[path="g16_perf.rs"] mod perf;
fn main() {
    let b=std::fs::read(std::env::args().nth(1).unwrap()).unwrap();
    assert_eq!(b.len(),792);
    let w=|i|u32::from_le_bytes(b[i..i+4].try_into().unwrap());
    let p=perf::Inputs::decode(w(0),w(4),w(8),&b[24..280],&b[280..536],&b[536..664],&b[664..792],w(12),w(16),w(20)).unwrap();
    for bank in 0..2 { for i in 0..16 {
        let off=24+(bank*16+i)*8;
        assert_eq!(p.core[bank][i].frequency_hz,w(off));
        assert_eq!(p.core[bank][i].voltage_mv,w(off+4));
        assert_eq!(p.sram[bank][i].frequency_hz,w(off+256));
        assert_eq!(p.sram[bank][i].voltage_mv,w(off+260));
    }}
    assert_eq!(p.period_clocks,w(12));assert_eq!(p.period_ms,w(16));assert_eq!(p.active_mcc_mask,w(20));
    println!("PASS: actual Rust decoder preserved all64 states and exact sampling inputs");
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kernel-source', type=Path, required=True)
    ap.add_argument('--m1n1-source', type=Path, required=True)
    ap.add_argument('--target-adt', type=Path, required=True)
    ap.add_argument('--baseline-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    require(not a.output.exists(), 'Refusing existing output')
    data = a.target_adt.read_bytes()
    require(digest(data) == TARGET_SHA, 'Target ADT differs')
    sys.path.insert(0, str(a.m1n1_source.resolve() / 'proxyclient'))
    from m1n1.adt import ADTNodeStruct
    props = select(ADTNodeStruct.parse(data), '/arm-io/sgx')
    def scalar(p, key):
        require(len(p[key]) == 4, 'Wrong scalar size')
        return struct.unpack('<I', p[key])[0]
    scalars = [scalar(props, key) for key in ('perf-state-count', 'gpu-num-perf-states', 'perf-state-table-count', 'gpu-pwr-sample-period-aic-clks', 'gpu-power-sample-period', 'active-mcc-bit-vector')]
    names = ('perf-states', 'perf-states-sram', 'perf-states1', 'perf-states-sram1')
    raw = struct.pack('<6I', *scalars) + b''.join(props[k] for k in names)
    baseline = {}
    for board, expected in BASELINES.items():
        b = (a.baseline_root / board / 'DeviceTree.adt').read_bytes()
        require(digest(b) == expected, 'Baseline ADT differs')
        p = select(ADTNodeStruct.parse(b), '/arm-io/sgx')
        baseline[board] = {
            'adt_sha256': expected, 'source': 'vendor static ADT; not a runtime capture',
            'perf_state_count': scalar(p, 'perf-state-count'),
            'gpu_num_perf_states': scalar(p, 'gpu-num-perf-states'),
            'perf_state_table_count_present': 'perf-state-table-count' in p,
            'table_byte_lengths': {key: len(p[key]) if key in p else None for key in names},
            'runtime_shape_qualified': False,
        }
    src = a.kernel_source / 'drivers/gpu/drm/asahi/g16_perf.rs'
    source = src.read_bytes()
    harness = Path(__file__).with_name('test_g16_perf.rs').read_bytes()
    with tempfile.TemporaryDirectory(prefix='g16-perf-replay-') as temp:
        work = Path(temp)
        (work / 'g16_perf.rs').write_bytes(source)
        (work / 'test.rs').write_bytes(harness)
        (work / 'runner.rs').write_text(RUNNER)
        (work / 'input.bin').write_bytes(raw)
        outputs = []
        for name, flags in [('test', ['--test']), ('runner', [])]:
            build = subprocess.run(['rustc', '--edition=2021', '-Dwarnings', *flags, str(work / (name + '.rs')), '-o', str(work / name)], capture_output=True, text=True)
            require(build.returncode == 0, 'Rust build failed: ' + build.stderr)
            run = subprocess.run([str(work / name), *([str(work / 'input.bin')] if name == 'runner' else [])], capture_output=True, text=True)
            require(run.returncode == 0 and not run.stderr, 'Rust replay failed: ' + run.stdout + run.stderr)
            outputs.append(run.stdout)
        # A real no_std AArch64 object checks core-only dependencies and target codegen.
        (work / 'lib.rs').write_text('#![no_std]\n#[path="g16_perf.rs"] pub mod perf;\n')
        build = subprocess.run(['rustc', '--edition=2021', '-Dwarnings', '--crate-type=lib', '--target=aarch64-unknown-none-softfloat', '--emit=obj', str(work / 'lib.rs'), '-o', str(work / 'perf.o')], capture_output=True, text=True)
        require(build.returncode == 0, 'AArch64 no_std build failed: ' + build.stderr)
        object_sha = digest((work / 'perf.o').read_bytes())
    frequencies = [x[0] for x in struct.iter_unpack('<II', props['perf-states'][:128])]
    result = {
        'status': 'ACTUAL_ADT_RUST_DECODE_ONLY', 'hardware_tested': False,
        'firmware_init_enabled': False, 'runtime_caller_added': False,
        'target_adt_sha256': TARGET_SHA, 'decoder_sha256': digest(source),
        'test_harness_sha256': digest(harness), 'harness_tests': 7,
        'aarch64_no_std_object_sha256': object_sha, 'state_records_verified': 64,
        'object_target': 'aarch64-unknown-none-softfloat',
        'state_count': scalars[0], 'active_state_count': scalars[1], 'table_count': scalars[2],
        'period_clocks': scalars[3], 'period_ms': scalars[4],
        'clocks_lost_if_reconstructed_from_ms': scalars[3] - scalars[4] * 24000,
        'active_mcc_mask': scalars[5],
        'repeated_frequency_indices': [i for i in range(1, 16) if frequencies[i] == frequencies[i-1]],
        'descending_frequency_indices': [i for i in range(1, 16) if frequencies[i] < frequencies[i-1]],
        'distinct_core_voltage_banks': props['perf-states'][:128] != props['perf-states'][128:],
        'mirror_properties_verified': True, 'baselines': baseline,
        'raw_properties_exported': False, 'source_license': 'GPL-2.0-only',
        'blocked': 'Firmware hwdata/power layout, UAT and first APP INIT still require earliest coherent T6040 capture; this decoder does not serialize or submit them',
        'stdout': outputs,
    }
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: 7 host tests, 64 actual ADT records, AArch64 no_std object; no runtime enablement')


if __name__ == '__main__':
    main()
