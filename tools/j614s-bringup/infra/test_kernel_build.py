#!/usr/bin/env python3
"""Host-only regression tests; fixtures never access target hardware."""
import importlib.util
import gzip
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('kernel_build', Path(__file__).with_name('kernel_build.py'))
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def config(self):
        path = self.root / 'config'
        path.write_text('\n'.join(key + '=' + value for key, value in k.REQUIRED_CONFIG.items()) + '\n')
        return path

    def bundle(self):
        for name in ('.config', 'Image', 'kernel.release', 'build.log'):
            (self.root / name).write_text(name + '\n')
        image = bytearray(64)
        image[56:60] = b'ARMd'
        image[24] = 12
        image += b'IKCFG_ST' + gzip.compress((self.root / '.config').read_bytes(), mtime=0) + b'IKCFG_ED'
        (self.root / 'Image').write_bytes(image)
        k.write_json(self.root / 'contract.json', {'schema': 1, 'config': {'sha256': k.digest(self.root / '.config')}})
        manifest = {'schema': 1, 'status': 'COMPILED',
                    'contract_sha256': k.digest(self.root / 'contract.json'),
                    'config_sha256': k.digest(self.root / '.config'),
                    'artifacts': [k.artifact_record(self.root / name, self.root)
                                  for name in ('.config', 'Image', 'kernel.release', 'build.log')]}
        k.write_json(self.root / 'manifest.json', manifest)
        return manifest

    def test_valid_artifacts(self):
        self.bundle()
        self.assertEqual(k.verify(self.root)['status'], 'COMPILED')

    def test_tampered_image_same_length(self):
        self.bundle()
        image = bytearray((self.root / 'Image').read_bytes())
        image[-1] ^= 1
        (self.root / 'Image').write_bytes(image)
        with self.assertRaisesRegex(ValueError, 'checksum mismatch: Image'):
            k.verify(self.root)

    def test_config_tamper(self):
        self.bundle()
        (self.root / '.config').write_text('CONFIG_RUST=n\n')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            k.verify(self.root)

    def test_contract_tamper(self):
        self.bundle()
        (self.root / 'contract.json').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'Contract checksum'):
            k.verify(self.root)

    def test_path_escape(self):
        manifest = self.bundle()
        manifest['artifacts'][0]['path'] = '../outside'
        k.write_json(self.root / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'Invalid artifact path'):
            k.verify(self.root)

    def test_missing_image_entry(self):
        manifest = self.bundle()
        manifest['artifacts'] = [x for x in manifest['artifacts'] if x['path'] != 'Image']
        k.write_json(self.root / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'Missing required'):
            k.verify(self.root)

    def test_mixed_contract_config(self):
        manifest = self.bundle()
        contract = k.read_json(self.root / 'contract.json')
        contract['config']['sha256'] = 'different-config'
        k.write_json(self.root / 'contract.json', contract)
        manifest['contract_sha256'] = k.digest(self.root / 'contract.json')
        k.write_json(self.root / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'does not match build contract'):
            k.verify(self.root)

    def test_wrong_image_architecture(self):
        manifest = self.bundle()
        image = bytearray((self.root / 'Image').read_bytes())
        image[56:60] = b'NOPE'
        (self.root / 'Image').write_bytes(image)
        manifest['artifacts'] = [k.artifact_record(self.root / x['path'], self.root)
                                 for x in manifest['artifacts']]
        k.write_json(self.root / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'not an uncompressed AArch64'):
            k.verify(self.root)

    def test_lock_refuses_existing_contract(self):
        contract = self.root / 'contract.json'
        contract.write_text('retained-contract\n')
        result = subprocess.run([sys.executable, str(Path(k.__file__)), 'lock',
                                 '--source', str(self.root), '--config', str(self.root / 'config'),
                                 '--bindgen', sys.executable, '--tool-dir', str(self.root),
                                 '--contract', str(contract)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Refusing to overwrite', result.stderr)
        self.assertEqual(contract.read_text(), 'retained-contract\n')

    def test_disabled_layout_checks_rejected(self):
        bindings = self.root / 'rust/bindings'
        bindings.mkdir(parents=True)
        (bindings / 'bindings_generated.rs').write_text('const _: () = { offset_of!(Sample, value); };')
        (bindings / '.bindings_generated.rs.cmd').write_text('--target=aarch64-linux-gnu --no-layout-tests')
        (self.root / 'rust/bindings.o').write_bytes(b'fixture')
        with self.assertRaisesRegex(ValueError, 'disabled binding layout checks'):
            k.layout_state(self.root)

    def test_independent_identical_artifacts(self):
        self.bundle()
        second = self.root / 'second'
        second.mkdir()
        for name in ('.config', 'Image', 'kernel.release', 'build.log', 'contract.json', 'manifest.json'):
            shutil.copyfile(self.root / name, second / name)
        self.assertEqual(k.compare(self.root, second)['status'], 'BYTE_IDENTICAL')

    def test_changed_artifact_is_not_reproducible(self):
        self.bundle()
        second = self.root / 'second'
        second.mkdir()
        for name in ('.config', 'Image', 'kernel.release', 'build.log', 'contract.json', 'manifest.json'):
            shutil.copyfile(self.root / name, second / name)
        image = bytearray((second / 'Image').read_bytes())
        image[0] ^= 1
        (second / 'Image').write_bytes(image)
        manifest = k.read_json(second / 'manifest.json')
        manifest['artifacts'] = [k.artifact_record(second / x['path'], second)
                                 for x in manifest['artifacts']]
        k.write_json(second / 'manifest.json', manifest)
        result = k.compare(self.root, second)
        self.assertEqual(result['status'], 'DIFFERENT')
        self.assertEqual(result['differences'][0]['path'], 'Image')

    def test_same_build_not_independent(self):
        self.bundle()
        with self.assertRaisesRegex(ValueError, 'Independent build directories'):
            k.compare(self.root, self.root)

    def test_wrong_module_release_rejected(self):
        manifest = self.bundle()
        module = self.root / 'modules/example.ko'
        module.parent.mkdir()
        header = bytearray(20)
        header[:6] = b'\x7fELF\x02\x01'
        header[18:20] = b'\xb7\x00'
        module.write_bytes(header + b'vermagic=other-kernel SMP\0')
        manifest['artifacts'].append(k.artifact_record(module, self.root))
        k.write_json(self.root / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'Module release does not match'):
            k.verify(self.root)

    def test_embedded_config_mismatch_rejected(self):
        manifest = self.bundle()
        image = (self.root / 'Image').read_bytes()[:64]
        image += b'IKCFG_ST' + gzip.compress(b'other-config\n', mtime=0) + b'IKCFG_ED'
        (self.root / 'Image').write_bytes(image)
        manifest['artifacts'] = [k.artifact_record(self.root / x['path'], self.root)
                                 for x in manifest['artifacts']]
        k.write_json(self.root / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'Embedded Image config does not match'):
            k.verify(self.root)

    def test_private_absolute_artifact_paths_rejected(self):
        self.bundle()
        with (self.root / 'Image').open('ab') as stream:
            stream.write(str(Path.home()).encode() + b'/private-source/driver.rs')
        with self.assertRaisesRegex(ValueError, 'Private absolute build paths remain'):
            k.path_state(self.root)

    def test_wrong_config_cpu_count(self):
        config = self.config()
        config.write_text(config.read_text().replace('CONFIG_NR_CPUS=16', 'CONFIG_NR_CPUS=1'))
        with self.assertRaisesRegex(ValueError, 'CONFIG_NR_CPUS'):
            k.config_state(config)

    def test_dirty_source_fingerprint(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'driver.c').write_text('original\n')
        subprocess.run(['git', 'add', 'driver.c'], cwd=self.root, check=True)
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit', '-qm', 'fixture'], cwd=self.root, check=True)
        clean, _ = k.source_state(self.root)
        (self.root / 'driver.c').write_text('patched\n')
        dirty, _ = k.source_state(self.root)
        self.assertNotEqual(clean['dirty_diff_sha256'], dirty['dirty_diff_sha256'])
        (self.root / 'new-driver.c').write_text('new\n')
        untracked, _ = k.source_state(self.root)
        self.assertEqual(untracked['untracked']['new-driver.c'], k.digest(self.root / 'new-driver.c'))

    def test_wrong_tool_contract(self):
        expected = {'schema': 1, 'source': {}, 'config': {}, 'tools': {'clang': {'sha256': 'expected'}}}
        actual = dict(expected, tools={'clang': {'sha256': 'different'}})
        with patch.object(k, 'state', return_value=actual):
            with self.assertRaisesRegex(ValueError, 'mismatch: tools'):
                k.check(None, expected)

    def test_wrong_bindgen_binary_rejected(self):
        class Args:
            tool_dir = self.root
            bindgen = Path(sys.executable)
        with patch.object(k, 'run', return_value=(sys.executable + '\n').encode()), \
             patch.object(k.shutil, 'which', return_value=sys.executable):
            with self.assertRaisesRegex(ValueError, 'bindgen binary checksum'):
                k.tool_paths(Args)


if __name__ == '__main__':
    unittest.main(verbosity=2)
