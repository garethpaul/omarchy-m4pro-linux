import copy
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import layout
import decode_snapshot


class PowerTests(unittest.TestCase):
    def setUp(self):
        self.comparison = json.loads((BASE / 'evidence/adt-cpu-comparison.json').read_text())
        self.live = self.comparison['layouts']['live_t6040']

    def snapshot(self):
        return {'identity': {'chip_id': 0x6040, 'board_id': 4, 'model': 'Mac16,8',
                             'source_adt_sha256': self.live['source_sha256']},
                'exceptions_before': 0, 'exceptions_after': 0,
                'samples': [{'monotonic_ns': n, 'registers': [{'cluster': c, 'physical': base + 0x20,
                              'width_bits': 64, 'value': 1} for c, base in enumerate(layout.BASES)]} for n in (1, 2)]}

    def test_actual_saved_projection(self):
        layout.qualify_j614s(self.live)
        self.assertEqual([len(self.live['cpu_sram_tables'][name]) for name in layout.TABLES], [7, 19, 19])
        for key in ('static_t8112', 'static_t8122'):
            old = self.comparison['layouts'][key]
            self.assertEqual([a['physical'] for a in old['cpu_apertures']], layout.BASES[:2])
            self.assertEqual([a['size'] for a in old['cpu_apertures']], [0x2000] * 2)
            self.assertEqual(len(old['cpus']), 8)
            self.assertFalse(old['cpu_sram_tables'])
        self.assertNotIn('perf-regs', self.live['pmgr_structure'])
        self.assertIn('perf-groups', self.live['pmgr_structure'])

    def test_wrong_board_or_missing_table(self):
        for field, value in [('chip_id', 0x8132), ('board_id', 6), ('model', ['Mac16,7']), ('pmgr_compatible', ['pmgr1,t8122'])]:
            bad = copy.deepcopy(self.live)
            bad[field] = value
            with self.assertRaises(layout.LayoutError):
                layout.qualify_j614s(bad)
        bad = copy.deepcopy(self.live)
        bad['cpu_sram_tables'].pop(layout.TABLES[0])
        with self.assertRaises(layout.LayoutError):
            layout.qualify_j614s(bad)

    def test_bad_geometry(self):
        for change in ('missing_cluster', 'duplicate_base', 'bad_size', 'bad_cpu'):
            bad = copy.deepcopy(self.live)
            if change == 'missing_cluster': bad['cpu_apertures'].pop()
            if change == 'duplicate_base': bad['cpu_apertures'][1]['physical'] = layout.BASES[0]
            if change == 'bad_size': bad['cpu_apertures'][0]['size'] = 0x1000
            if change == 'bad_cpu': bad['cpus'][-1]['cluster_id'] = 1
            with self.assertRaises(layout.LayoutError):
                layout.qualify_j614s(bad)

    def test_bad_frequency_geometry(self):
        for change in ('zero', 'descending', 'too_fast', 'bad_voltage'):
            bad = copy.deepcopy(self.live)
            table = bad['cpu_sram_tables'][layout.TABLES[0]]
            if change == 'zero': table[0]['frequency_candidate_khz'] = 0
            if change == 'descending': table[1]['frequency_candidate_khz'] = table[0]['frequency_candidate_khz']
            if change == 'too_fast': table[-1]['frequency_candidate_khz'] = 9999999
            if change == 'bad_voltage': table[0]['sram_value'] = 0
            with self.assertRaises(layout.LayoutError):
                layout.qualify_j614s(bad)

    def test_synthetic_snapshot_keeps_uncertainty(self):
        result = decode_snapshot.decode(self.live, self.snapshot())
        self.assertEqual(result['hardware_frequency'], 'UNTESTED')
        self.assertEqual(result['status'], 'PARTIAL')
        row = result['samples'][0]['registers'][0]
        self.assertEqual(row['one_based_frequency_candidate_khz'], 1020000)
        self.assertEqual(row['zero_based_frequency_candidate_khz'], 1404000)

    def test_snapshot_negative_cases(self):
        for change in ('board', 'adt', 'exception', 'address', 'width', 'duplicate', 'busy', 'state', 'unstable', 'timestamp'):
            bad = self.snapshot()
            reg = bad['samples'][0]['registers'][0]
            if change == 'board': bad['identity']['board_id'] = 6
            if change == 'adt': bad['identity']['source_adt_sha256'] = '0' * 64
            if change == 'exception': bad['exceptions_after'] = 1
            if change == 'address': reg['physical'] += 0x30
            if change == 'width': reg['width_bits'] = 32
            if change == 'duplicate': bad['samples'][0]['registers'][1] = reg.copy()
            if change == 'busy': reg['value'] = (1 << 31) | 1
            if change == 'state': reg['value'] = 31
            if change == 'unstable': reg['value'] = 2
            if change == 'timestamp': bad['samples'][1]['monotonic_ns'] = 1
            with self.subTest(change=change), self.assertRaises(layout.LayoutError):
                decode_snapshot.decode(self.live, bad)

    def test_reader_seam_exact_six_reads(self):
        reads = []
        def read(address):
            reads.append(address)
            return 1
        ticks = iter((100, 200))
        snapshot = decode_snapshot.capture_with_reader(self.live, read, lambda: 0, 0x6040, lambda: next(ticks))
        self.assertEqual(reads, [base + 0x20 for base in layout.BASES] * 2)
        self.assertEqual(decode_snapshot.decode(self.live, snapshot)['hardware_frequency'], 'UNTESTED')

    def test_reader_stops_after_exception(self):
        reads = []
        def read(address):
            reads.append(address)
            return 1
        counts = iter((0, 1))
        with self.assertRaises(layout.LayoutError):
            decode_snapshot.capture_with_reader(self.live, read, lambda: next(counts), 0x6040)
        self.assertEqual(reads, [layout.BASES[0] + 0x20])

    def test_address_span_guards(self):
        self.assertEqual(layout.translate([(0, 0x200000000, 0x100000000)], 0x10e20000, 0x2000), layout.BASES[0])
        for ranges, address, size in [([(0, 0, 32)], 0, 0), ([(0, 0, 32)], 31, 2),
                                      ([(0, 0, 32), (0, 64, 32)], 1, 1), ([(0, 2**64 - 1, 32)], 0, 1)]:
            with self.assertRaises(layout.LayoutError):
                layout.translate(ranges, address, size)

    def test_parser_truncation_and_nonzero_padding(self):
        for raw in (b'', struct.pack('<II', 100000, 0), struct.pack('<II', 1, 0) + b'x' * 20):
            with self.assertRaises(layout.LayoutError):
                layout.parse_adt(raw)
        prop = b'name' + b'\0' * 28 + struct.pack('<I', 12) + b'device-tree\0'
        minimal = struct.pack('<II', 1, 0) + prop
        self.assertEqual(set(layout.parse_adt(minimal)), {'/'})
        padded = minimal + b'\0' * (16384 - len(minimal))
        self.assertEqual(set(layout.parse_adt(padded)), {'/'})
        with self.assertRaises(layout.LayoutError):
            layout.parse_adt(padded[:-1] + b'x')


if __name__ == '__main__':
    unittest.main(verbosity=2)
