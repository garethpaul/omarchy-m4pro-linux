import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qualify', BASE / 'qualify.py')
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


class QualificationTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(dir=BASE / 'test-results')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        dt = root / 'sys/firmware/devicetree/base'
        dt.mkdir(parents=True)
        (dt / 'compatible').write_bytes(b'apple,j614s\0apple,t6040\0')
        for mpidr in q.MPIDRS:
            node = dt / 'cpus' / f'cpu@{mpidr:x}'
            node.mkdir(parents=True)
            (node / 'reg').write_bytes(mpidr.to_bytes(8, 'big'))
            (node / 'device_type').write_bytes(b'cpu\0')
            (node / 'compatible').write_bytes(b'apple,sawtooth\0' if mpidr < 4 else b'apple,everest\0')
        cpus = root / 'sys/devices/system/cpu'
        cpus.mkdir(parents=True)
        for name in ('online', 'present'):
            (cpus / name).write_text('0-11\n')
        (root / 'proc').mkdir()
        (root / 'proc/cmdline').write_text('console=tty0\n')
        return root

    def test_saved_coherency_evidence(self):
        text = (BASE / 'tests/fixtures/coherency-test51.txt').read_text()
        q.validate_workload('coherency', text, 0)
        for corrupt in (text.replace('12000000 EXPECTED', '11999999 EXPECTED'),
                        text.replace('CHILD 4 STATUS 0', 'CHILD 4 STATUS 256'),
                        text.replace('CHILD 0 STATUS 0\n', ''), text + 'SHARED_ATOMIC_PASS\n',
                        text + 'AFFINITY_FAIL\n'):
            with self.subTest(corrupt=corrupt):
                with self.assertRaises(q.QualificationError):
                    q.validate_workload('coherency', corrupt, 0)
        with self.assertRaises(q.QualificationError):
            q.validate_workload('coherency', text, 1)

    def test_saved_simd_evidence(self):
        text = (BASE / 'tests/fixtures/simd-test51.txt').read_text()
        q.validate_workload('simd-context', text, 0)
        with self.assertRaises(q.QualificationError):
            q.validate_workload('simd-context', text.replace('1000_SLEEPS', '100_SLEEPS'), 0)
        with self.assertRaises(q.QualificationError):
            q.validate_workload('simd-context', text + 'SIMD_MISMATCH CPU 1 ITER 1 LANE 1\n', 0)

    def test_topology_accepts_exact_fixture(self):
        result = q.topology(self.fixture(), 'aarch64', set(range(12)))
        self.assertEqual(len(result['adt_derived_dt_cpus']), 12)
        self.assertEqual(sum('apple,sawtooth' in item['compatible'] for item in result['adt_derived_dt_cpus']), 4)
        self.assertEqual(sum('apple,everest' in item['compatible'] for item in result['adt_derived_dt_cpus']), 8)

    def test_wrong_hardware(self):
        root = self.fixture()
        (root / 'sys/firmware/devicetree/base/compatible').write_bytes(b'apple,j713\0apple,t8132\0')
        with self.assertRaises(q.QualificationError):
            q.topology(root, 'aarch64', q.CPUS)
        with self.assertRaises(q.QualificationError):
            q.topology(root, 'x86_64', q.CPUS)

    def test_offline_or_disallowed_cpu(self):
        root = self.fixture()
        for affinity in (q.CPUS - {4}, q.CPUS | {12}):
            with self.assertRaises(q.QualificationError):
                q.topology(root, 'aarch64', affinity)
        (root / 'sys/devices/system/cpu/online').write_text('0-10')
        with self.assertRaises(q.QualificationError):
            q.topology(root, 'aarch64', q.CPUS)

    def test_bad_dt_cpu_or_workaround(self):
        root = self.fixture()
        node = root / 'sys/firmware/devicetree/base/cpus/cpu@10203'
        (node / 'reg').write_bytes((0x10202).to_bytes(8, 'big'))
        with self.assertRaises(q.QualificationError):
            q.topology(root, 'aarch64', q.CPUS)
        (node / 'reg').write_bytes((0x10203).to_bytes(8, 'big'))
        for arg in ('maxcpus=12', 'nr_cpus=12', 'idle=nop', 'nosmp', 'arm64.nowfxt', 'arm64.nowfxt=1', 'idle=poll', 'cpuidle.off=1'):
            (root / 'proc/cmdline').write_text('console=tty0 ' + arg)
            with self.assertRaises(q.QualificationError):
                q.topology(root, 'aarch64', q.CPUS)

    def test_idle_and_cpu_list(self):
        text = '\n'.join(f'cpu{i} 100 0 2 {i + 1} 3 0 0 0' for i in range(12))
        self.assertEqual(q.idle_snapshot(text), {i: i + 1 for i in range(12)})
        with self.assertRaises(q.QualificationError):
            q.idle_snapshot(text.replace('cpu11 ', 'cpu12 '))
        with self.assertRaises(q.QualificationError):
            q.idle_snapshot(text + '\ncpu0 100 0 2 1 3 0 0 0')
        self.assertEqual(q.cpulist('0-3,4-7,8-11'), q.CPUS)
        for value in ('11-0', '0-99999', '0-1-2'):
            with self.assertRaises(q.QualificationError):
                q.cpulist(value)

    def test_kernel_fault_patterns(self):
        for line in ('[3] BUG: corrupt', '[3] WARNING: fault', 'Oops: fatal',
                     'Kernel panic - not syncing', 'Internal error: Oops', 'SError Interrupt'):
            self.assertIsNotNone(q.BAD_LOG.search(line))
        self.assertIsNone(q.BAD_LOG.search('SMP: Total of 12 processors activated.'))

    def test_process_timeout_raises(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            q.command([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=0.05)

    def test_generic_hash_worker_on_host_cpu(self):
        # This validates runner plumbing only, not T6040 CPU functionality.
        original = os.sched_getaffinity(0)
        self.addCleanup(os.sched_setaffinity, 0, original)
        cpu = min(original)
        context = mp.get_context('fork')
        queue = context.Queue()
        self.addCleanup(queue.close)
        q.hash_worker(cpu, context.Barrier(1), queue)
        sample = queue.get(timeout=2)
        self.assertEqual(sample['affinity'], [cpu])
        self.assertEqual(sample['bytes'], 64 * 1024 * 1024)
        self.assertGreater(sample['cpu_seconds'], 0)
        self.assertGreater(sample['wall_seconds'], 0)
        self.assertEqual(len(sample['digest']), 64)


if __name__ == '__main__':
    unittest.main(verbosity=2)
