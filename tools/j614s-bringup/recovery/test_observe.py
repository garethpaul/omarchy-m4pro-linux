# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import observe


class ObserverTests(unittest.TestCase):
    def test_usb_filter_never_reads_serial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, vid, pid in [('proxy', '1209', '316d'), ('other', '1234', '5678')]:
                path = root / name
                path.mkdir()
                for key, value in dict(idVendor=vid, idProduct=pid, product='test',
                                       busnum='1', devnum='9', serial='DO-NOT-EXPORT').items():
                    (path / key).write_text(value)
            result = observe.usb_snapshot(root)
            self.assertEqual(len(result), 1)
            self.assertNotIn('DO-NOT-EXPORT', json.dumps(result))

    def test_disappearing_device_does_not_fabricate_a_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'gone').mkdir()
            self.assertEqual(observe.usb_snapshot(Path(directory)), [])

    def test_camera_failure_is_partial_and_does_not_claim_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'new'
            with patch.object(observe, 'usb_snapshot', return_value=[]), \
                 patch.object(observe, 'capture', side_effect=RuntimeError('camera busy')):
                result = observe.observe(output, 0.001, 1, True)
            self.assertEqual(result['status'], 'PARTIAL')
            self.assertGreater(result['camera_errors'], 0)
            self.assertFalse(result['recovery_verified'])
            self.assertIn('camera_error', (output / 'events.jsonl').read_text())

    def test_existing_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaises(FileExistsError):
                observe.observe(output, 0.001, 1, False)


if __name__ == '__main__':
    unittest.main()
