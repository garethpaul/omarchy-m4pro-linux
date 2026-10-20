#!/usr/bin/env python3
"""Portable archive negatives + opt-in real pinned-bundle input negatives.

Never executes init, mounts filesystems, or touches host device interfaces.
"""
import gzip
import importlib.util
import marshal
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import build_probe as probe


def fixture():
    entries = {p: probe.entry(stat.S_IFDIR | 0o755) for p in probe.DIRS}
    entries.update({p: probe.entry(stat.S_IFCHR | 0o600, rdev=d) for p, d in probe.NODES.items()})
    for p in probe.REGULAR:
        entries[p] = probe.entry(stat.S_IFREG | (0o755 if p in ('init', 'bin/busybox') else 0o644), b'fixture')
    entries.update({'bin/' + a: probe.entry(stat.S_IFLNK | 0o777, b'busybox') for a in probe.APPLETS})
    return entries


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.entries = fixture()

    def reject(self, entries):
        with self.assertRaises(ValueError):
            probe.unpack(probe.archive(entries))

    def test_exact_archive_roundtrip(self):
        raw = probe.archive(self.entries)
        self.assertEqual(probe.unpack(raw), self.entries)
        self.assertEqual(gzip.decompress(gzip.compress(raw, mtime=0)), raw)

    def test_parent_escape(self):
        self.entries['../init'] = probe.entry(stat.S_IFREG | 0o755, b'bad')
        self.reject(self.entries)

    def test_absolute_path(self):
        self.entries['/init'] = probe.entry(stat.S_IFREG | 0o755, b'bad')
        self.reject(self.entries)

    def test_extra_kernel_module(self):
        self.entries['lib/modules/appledrm.ko'] = probe.entry(stat.S_IFREG | 0o644, b'bad')
        self.reject(self.entries)

    def test_missing_nvme_module(self):
        del self.entries['lib/modules/nvme-apple.ko']
        self.reject(self.entries)

    def test_symlink_escape(self):
        self.entries['bin/sh'] = probe.entry(stat.S_IFLNK | 0o777, b'../../tmp/evil')
        self.reject(self.entries)

    def test_setuid(self):
        self.entries['init'] = probe.entry(stat.S_IFREG | 0o4755, b'bad')
        self.reject(self.entries)

    def test_block_device(self):
        self.entries['dev/nvme0n1'] = probe.entry(stat.S_IFBLK | 0o600, rdev=(259, 0))
        self.reject(self.entries)

    def test_wrong_console_device(self):
        self.entries['dev/console'] = probe.entry(stat.S_IFCHR | 0o600, rdev=(1, 1))
        self.reject(self.entries)

    def test_truncated_archive(self):
        raw = probe.archive(self.entries)
        with self.assertRaises(ValueError):
            probe.unpack(raw[:-120])

    def test_hidden_second_archive(self):
        raw = probe.archive(self.entries)
        with self.assertRaises(ValueError):
            probe.unpack(raw + raw)

    def test_modified_payload_detected(self):
        original = dict(self.entries)
        self.entries['init'] = probe.entry(stat.S_IFREG | 0o755, b'modified')
        with self.assertRaises(ValueError):
            probe.validate_archive(probe.archive(self.entries), original)

    def test_non_arm64_elf(self):
        raw = bytearray(64); raw[:6] = b'\x7fELF\x02\x01'; raw[18:20] = b'\x3e\x00'
        with self.assertRaises(ValueError):
            probe.arm64_elf(raw)

    def test_dynamic_busybox_refused(self):
        raw = bytearray(120); raw[:6] = b'\x7fELF\x02\x01'; raw[18:20] = b'\xb7\x00'
        struct.pack_into('<Q', raw, 32, 64); struct.pack_into('<HHH', raw, 52, 64, 56, 1)
        struct.pack_into('<I', raw, 64, 3)
        with self.assertRaises(ValueError):
            probe.arm64_elf(raw, static=True)



class ClassificationTests(unittest.TestCase):
    def classify(self, *args):
        result = subprocess.run(['sh', '-c', '. "$1"; shift; classify_ro "$@"', 'check', str(probe.HERE / 'probe-state.sh'), *args], capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def test_no_devices_is_partial(self):
        self.assertEqual(self.classify('0', '0', '0'), 'PARTIAL')

    def test_clean_visible_devices_are_ro(self):
        self.assertEqual(self.classify('3', '0', '0'), 'ENUMERATED_RO')

    def test_current_failure_blocks(self):
        self.assertEqual(self.classify('3', '1', '0'), 'BLOCKED')

    def test_recovered_current_state_cannot_erase_sticky_failure(self):
        self.assertEqual(self.classify('3', '0', '1'), 'BLOCKED')

    def test_no_devices_does_not_erase_failure(self):
        self.assertEqual(self.classify('0', '0', '1'), 'BLOCKED')

    def test_unknown_failure_state_blocks(self):
        self.assertEqual(self.classify('3', '0', 'unknown'), 'BLOCKED')

    def test_missing_argument_blocks(self):
        self.assertEqual(self.classify('3', '0'), 'BLOCKED')

    def test_non_numeric_device_count_blocks(self):
        self.assertEqual(self.classify('oops', '0', '0'), 'BLOCKED')



class WatchdogSnapshotTests(unittest.TestCase):
    @staticmethod
    def function(name):
        # Extract only this actual read-only helper; never source or run init.
        source = (probe.HERE / 'init').read_text()
        return name + '() {' + source.split(name + '() {', 1)[1].split('\n}', 1)[0] + '\n}\n'

    def read_fixture(self, path):
        source = self.function('read_status_file')
        return subprocess.run(['sh', '-c', source + 'read_status_file "$1"', 'check', str(path)], capture_output=True, text=True, check=True).stdout

    def test_existing_fixture_contents_and_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'timeout'; path.write_bytes(b'60\n')
            self.assertEqual(self.read_fixture(path), str(path) + '=60\n')
            self.assertEqual(path.read_bytes(), b'60\n')

    def test_absent_fixture_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing'
            self.assertEqual(self.read_fixture(path), str(path) + '=ABSENT\n')
            self.assertFalse(path.exists())

    def test_unreadable_fixture_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'not-a-file'; path.mkdir()
            self.assertEqual(self.read_fixture(path), str(path) + '=UNREADABLE\n')

    def test_snapshot_source_contains_requested_paths_and_fields(self):
        source = self.function('watchdog_snapshot')
        self.assertIn('/sys/class/watchdog/watchdog*', source)
        self.assertIn('identity state timeout timeleft nowayout bootstatus', source)
        self.assertIn('handle_boot_enabled open_timeout', source)
        self.assertIn('/sys/module/watchdog/parameters/$parameter', source)
        self.assertIn('/sys/class/watchdog/watchdog*=ABSENT', source)
        self.assertNotIn('/dev/watchdog', (probe.HERE / 'init').read_text())
        self.assertIn('this init does not arm/feed watchdogs; recovery remains unverified', (probe.HERE / 'init').read_text())


@unittest.skipUnless(os.environ.get('J614S_KERNEL_BUNDLE') and os.environ.get('J614S_KERNEL_VERIFIER'), 'Set pinned bundle and verifier paths for actual input negative controls')
class QualifiedInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = Path(os.environ['J614S_KERNEL_BUNDLE']).resolve()
        cls.verifier = Path(os.environ['J614S_KERNEL_VERIFIER']).resolve()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='j614s-package-negative-')
        self.addCleanup(self.tmp.cleanup)
        self.copy = Path(self.tmp.name) / 'bundle'; self.copy.mkdir()
        import json
        manifest = json.loads((self.bundle / 'manifest.json').read_text())
        for name in ['manifest.json', 'contract.json', *[a['path'] for a in manifest['artifacts']]]:
            dest = self.copy / name; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.bundle / name, dest)

    def mutate_and_refuse(self, name):
        path = self.copy / name
        data = path.read_bytes(); path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        with self.assertRaises(ValueError):
            probe.validate_kernel(self.copy, self.verifier)

    def test_actual_bundle_accepted(self):
        self.assertEqual(set(probe.validate_kernel(self.copy, self.verifier)), {'nvme-core.ko', 'nvme-apple.ko'})

    def test_changed_source_contract_refused(self):
        self.mutate_and_refuse('contract.json')

    def test_changed_manifest_refused(self):
        self.mutate_and_refuse('manifest.json')

    def test_changed_config_refused(self):
        self.mutate_and_refuse('.config')

    def test_changed_image_refused(self):
        self.mutate_and_refuse('Image')

    def test_changed_module_refused(self):
        self.mutate_and_refuse('modules/drivers/nvme/host/nvme-apple.ko')

    def test_changed_release_refused(self):
        self.mutate_and_refuse('kernel.release')

    def test_unsigned_busybox_never_executed(self):
        bb = Path(self.tmp.name) / 'busybox'; bb.write_bytes(b'untrusted')
        out = Path(self.tmp.name) / 'output'
        with patch.object(probe.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                probe.build(self.copy, self.verifier, bb, Path('/nonexistent-emulator'), out)
        run.assert_not_called()
        self.assertFalse(out.exists())

    def test_changed_verifier_never_imported(self):
        v = Path(self.tmp.name) / 'verifier.py'
        v.write_text('raise RuntimeError("must never import this")')
        with self.assertRaises(ValueError):
            probe.validate_kernel(self.copy, v)

    def test_pinned_verifier_source_ignores_unverified_cached_bytecode(self):
        verifier = Path(self.tmp.name) / 'copied_verifier.py'
        source = self.verifier.read_bytes(); verifier.write_bytes(source)
        cached = Path(importlib.util.cache_from_source(str(verifier)))
        cached.parent.mkdir()
        # Controlled fixture only: timestamp-valid cache whose sole action raises.
        poison = compile('raise RuntimeError("unverified cached verifier executed")', '<fixture-cache>', 'exec')
        raw = importlib.util.MAGIC_NUMBER + struct.pack('<III', 0, int(verifier.stat().st_mtime), len(source)) + marshal.dumps(poison)
        cached.write_bytes(raw)
        modules = probe.validate_kernel(self.copy, verifier)
        self.assertEqual(set(modules), {'nvme-core.ko', 'nvme-apple.ko'})
        self.assertEqual(cached.read_bytes(), raw)
        self.assertEqual(list(cached.parent.iterdir()), [cached])

    def test_existing_output_not_overwritten(self):
        out = Path(self.tmp.name) / 'output'; out.mkdir(); (out / 'precious').write_text('preserve')
        with self.assertRaises(ValueError):
            probe.build(self.copy, self.verifier, Path('/not-used'), Path('/not-used'), out)
        self.assertEqual((out / 'precious').read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main(verbosity=2)
