# SPDX-License-Identifier: MIT
import struct
import ast
from pathlib import Path
import unittest
from read_resident_cpus import CPU_IDS, decode_slots

EXPECTED = {i: (i if i<4 else 0x10100+i-4 if i<8 else 0x10200+i-10) for i in CPU_IDS}

def fixture(started=True):
    raw=bytearray(14*64)
    for i,mpidr in EXPECTED.items():
        struct.pack_into('<8Q',raw,64*i,mpidr if started or i==4 else 0,3 if started and i!=4 else 0,0,0,0,0,0,0)
    return raw

class ResidentCPUs(unittest.TestCase):
    def test_started_slots_and_boot_cpu_are_distinct(self):
        raw=fixture();r=decode_slots(raw,raw,EXPECTED)
        self.assertEqual(r['secondary_flags_set'],11)
        self.assertTrue(r['secondary_slots_idle'])
        self.assertEqual(r['cpus'][4]['observed_mpidr'],0x10100)
    def test_stopped_flags_are_not_a_hardware_pass(self):
        raw=fixture(False);r=decode_slots(raw,raw,EXPECTED)
        self.assertEqual(r['secondary_flags_set'],0)
        self.assertFalse(r['secondary_slots_idle'])
    def test_torn_snapshot_rejected(self):
        a=fixture();b=fixture();b[8]^=1
        with self.assertRaisesRegex(ValueError,'changed'):decode_slots(a,b,EXPECTED)
    def test_size_and_cpu_identity_rejected(self):
        raw=fixture()
        for expected,a in [({**EXPECTED,14:0x10300},raw),(EXPECTED,raw[:-1])]:
            with self.assertRaises(ValueError):decode_slots(a,a,expected)
    def test_wrong_active_mpidr_rejected(self):
        raw=fixture();struct.pack_into('<Q',raw,64*5,0x20100)
        with self.assertRaisesRegex(ValueError,'MPIDR'):decode_slots(raw,raw,EXPECTED)
    def test_queued_target_and_stale_arguments_refuse_ready(self):
        for offset in (16,24,32,40,48):
            raw=fixture();struct.pack_into('<Q',raw,64*5+offset,1)
            self.assertFalse(decode_slots(raw,raw,EXPECTED)['secondary_slots_idle'])
    def test_direct_target_api_has_only_metadata_and_ram_reads(self):
        tree=ast.parse(Path(__file__).with_name('read_resident_cpus.py').read_text())
        calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call)
               and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
               and n.func.value.id in ('proxy','interface')}
        self.assertEqual(calls, {'nop','get_chipid','get_exc_count','get_bootargs_rev','get_base','readmem'})
    def test_flag_is_counter_not_fixed_magic(self):
        raw=fixture();struct.pack_into('<Q',raw,64*5+8,1025)
        self.assertTrue(decode_slots(raw,raw,EXPECTED)['secondary_slots_idle'])

if __name__=='__main__':unittest.main()
