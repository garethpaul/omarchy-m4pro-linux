import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_fixture', BASE / 'verify_fixture.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class ArtifactValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=BASE / 'evidence')
        self.addCleanup(self.temporary.cleanup)
        self.prefix = Path(self.temporary.name) / 'constant42'
        for source in (BASE / 'evidence/compute-fixture').glob('constant42.*'):
            Path(str(self.prefix) + source.name.removeprefix('constant42')).write_bytes(source.read_bytes())

    def test_actual_source_generated_fixture(self):
        result = v.verify(self.prefix)
        self.assertEqual(result['hardware_execution'], 'UNTESTED')
        self.assertEqual(result['components']['shader.bin']['bytes'], 42)

    def test_rejects_corrupt_output_and_cdm(self):
        for suffix, offset in [('expected.bin', 4), ('cdm.bin', 0x10)]:
            path = Path(str(self.prefix) + '.' + suffix)
            original = path.read_bytes()
            corrupt = bytearray(original)
            corrupt[offset] ^= 1
            path.write_bytes(corrupt)
            with self.assertRaises(ValueError):
                v.verify(self.prefix)
            path.write_bytes(original)

    def test_rejects_unfounded_hardware_claim(self):
        path = Path(str(self.prefix) + '.json')
        manifest = json.loads(path.read_text())
        manifest['hardware_execution'] = 'WORKS'
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            v.verify(self.prefix)
