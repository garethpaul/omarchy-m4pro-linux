import copy
import importlib.util
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('g16s_geometry', BASE / 'g16s_geometry.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class GeometryTests(unittest.TestCase):
    def observation(self):
        return {'id_registers': {'0xd04000': '0xa031100', '0xd04010': '0x11020a',
                                 '0xe01500': '0xf6fdb', '0xe01504': '0x0', '0xe01508': '0x0'},
                'exceptions': 0, 'firmware_started': False}

    def test_measured_two_cluster_projection(self):
        result = g.candidate(self.observation())
        self.assertEqual(result['expected_known_uapi_fields']['core_masks'], [0x3db, 0x3db])
        self.assertEqual(result['measured']['enabled_per_cluster'], [8, 8])
        self.assertFalse(result['runtime_enabled'])
        self.assertEqual(result['shader_execution'], 'UNTESTED')

    def test_rejects_other_id_geometry_masks(self):
        for offset, value in [('0xd04000', '0xa011100'), ('0xd04010', '0x11010a'),
                              ('0xe01500', '0xfffff'), ('0xe01504', '0x1'), ('0xe01508', '0x1')]:
            bad = self.observation()
            bad['id_registers'][offset] = value
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                g.candidate(bad)

    def test_rejects_faulted_or_active_measurement(self):
        for field, value in [('exceptions', 1), ('firmware_started', True)]:
            bad = self.observation()
            bad[field] = value
            with self.assertRaises(ValueError):
                g.candidate(bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
