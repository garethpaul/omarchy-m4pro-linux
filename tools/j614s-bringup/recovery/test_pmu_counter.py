# SPDX-License-Identifier: MIT
import struct
import unittest

from read_pmu_counter import empty, profile, read_counter


def fixture():
    u32 = lambda value: struct.pack('<I', value)
    return {'/': {'model': b'Mac16,8\0'},
            '/chosen': {'board-id': u32(4), 'system-firmware-version': b'mBoot-18000.161.10\0'},
            '/arm-io': {'ranges': struct.pack('<QQQ', 0x300000000, 0x500000000, 0x20000000)},
            '/arm-io/nub-spmi0': {'gen': u32(3), 'compatible': b'aapl,spmi\0',
                                    'reg': struct.pack('<QQ', 0x309014000, 0x4000)},
            '/arm-io/nub-spmi0/pmu': {'is-primary': u32(1), 'compatible': b'pmu,spmi\0',
                                    'reg': u32(14), 'info-leg_scrpad': u32(0xf800)}}


class Proxy:
    def __init__(self, count=3, busy=False, reply=None):
        self.count, self.busy, self.reply = count, busy, reply
        self.writes = []
        self.response = []

    def read32(self, address):
        if address == 0x509014080:
            return 0
        if address == 0x509014000:
            return 0 if self.busy else (0 if self.response else 0x1000100)
        if address == 0x509014008:
            return self.response.pop(0)
        raise AssertionError('unexpected register')

    def write32(self, address, value):
        self.writes.append((address, value))
        self.response = [self.reply if self.reply is not None else 0x10e38, self.count]

    def get_exc_count(self):
        return 0


class PMUCounterTests(unittest.TestCase):
    def test_exact_geometry(self):
        self.assertEqual(profile(fixture()), (0x509014000, 14, 0xf802))

    def test_wrong_board_and_translation_rejected(self):
        for path, key, value in [('/chosen', 'board-id', struct.pack('<I', 6)),
                                 ('/arm-io', 'ranges', struct.pack('<QQQ', 0x300000000, 0x400000000, 0x20000000)),
                                 ('/arm-io/nub-spmi0', 'gen', struct.pack('<I', 2)),
                                 ('/arm-io/nub-spmi0/pmu', 'reg', struct.pack('<I', 15))]:
            with self.subTest(key=key):
                nodes = fixture()
                nodes[path][key] = value
                with self.assertRaises(AssertionError):
                    profile(nodes)

    def test_read_preserves_nonzero_count_and_has_no_write_opcode(self):
        proxy = Proxy(count=3)
        result = read_counter(proxy, *profile(fixture()))
        self.assertEqual(result['pmu_error_count_byte'], 3)
        self.assertFalse(result['pmu_register_written'])
        self.assertEqual(result['watchdog_action'], 'unchanged')
        self.assertEqual(proxy.writes, [(0x509014004, 0xf8028e38)])

    def test_busy_bus_has_no_command(self):
        proxy = Proxy(busy=True)
        with self.assertRaises(AssertionError):
            read_counter(proxy, *profile(fixture()))
        self.assertEqual(proxy.writes, [])

    def test_bad_reply_is_not_a_counter(self):
        with self.assertRaises(AssertionError):
            read_counter(Proxy(reply=0x10d38), *profile(fixture()))

    def test_fifo_status_requires_both_empty_bits(self):
        self.assertTrue(empty(0x1000100))
        for status in [0, 0x1000000, 0x100, 0x1000101]:
            self.assertFalse(empty(status))


if __name__ == '__main__':
    unittest.main()
