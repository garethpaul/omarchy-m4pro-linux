#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import sys
from unittest.mock import patch
import types
import unittest
from g16s_early_capture import Observer, ASC_BASE, attach
from replay_early_capture import replay

HERE = Path(__file__).resolve().parent
LIBRARY = HERE / "build/g16s_capture.so"
VA = 0xfffffc2000100000

def memory_fixture():
    memory = bytearray(0x10000)
    root = bytearray(subprocess.check_output([str(HERE / "build/test_g16s_abi"), "--emit-fixture"]))
    main = bytearray(subprocess.check_output([str(HERE / "build/test_g16s_main"), "--emit-fixture"]))
    struct.pack_into("<Q", root, 0x18, VA + 0x400)
    struct.pack_into("<Q", main, 0, VA + 0x800)
    memory[0xc000:0xc000 + len(root)] = root
    memory[0xc400:0xc400 + len(main)] = main
    struct.pack_into("<4I", memory, 0xd690, 0x6040, 1, 1, 0)
    for location, value in [(0x10000 + ((VA >> 36) & 63) * 8, 0x14003),
                            (0x14000 + ((VA >> 25) & 2047) * 8, 0x18003),
                            (0x18000 + ((VA >> 14) & 2047) * 8, 0x1c403)]:
        struct.pack_into("<Q", memory, location - 0x10000, value)
    return memory

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.memory = memory_fixture()
        self.read_calls = []
    def reader(self, address, size):
        self.read_calls.append((address,size))
        self.assertGreaterEqual(address,0x10000)
        self.assertLessEqual(address+size,0x20000)
        return bytes(self.memory[address-0x10000:address-0x10000+size])
    def observer(self, ranges=None):
        return Observer(self.reader, ranges or [(0x10000,0x10000)],0x10000,LIBRARY,self.temp.name)
    def init(self, observer):
        self.assertIsNone(observer.feed(ASC_BASE+0x8800,0x00810c2000100000))
        return observer.feed(ASC_BASE+0x8808,0x20)
    def test_native_init_and_first_candidate_are_capture_only(self):
        observer = self.observer()
        self.assertFalse(self.read_calls)
        result = self.init(observer)
        self.assertEqual(result["capture_error"],0)
        self.assertFalse(result["safe_to_publish_init"])
        self.assertFalse(result["hardware_job_pass"])
        self.assertEqual(result["first_body_va"],hex(VA+0x1690))
        self.assertEqual((Path(self.temp.name)/"pre-first-init/first_body.bin").read_bytes(),struct.pack("<4I",0x6040,1,1,0))
        observer.feed(ASC_BASE+0x8800,0x0083000000000001)
        result = observer.feed(ASC_BASE+0x8808,0x21)
        self.assertEqual(result["phase"],"gravity-kick-candidate")
        self.assertFalse(result["hardware_job_pass"])
        self.assertEqual((Path(self.temp.name)/"pre-first-init").stat().st_mode & 0o777,0o700)
    def test_saved_capture_replays_without_target_and_rejects_modified_file(self):
        self.init(self.observer())
        phase=Path(self.temp.name)/"pre-first-init"
        result=replay(phase,Path(self.temp.name)/"replayed",LIBRARY)
        self.assertEqual(result["status"],"OFFLINE_REPLAY_MATCH")
        self.assertFalse(result["hardware_job_pass"])
        path=phase/"read-000.bin"
        data=bytearray(path.read_bytes()); data[0]^=1; path.write_bytes(data)
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            replay(phase,Path(self.temp.name)/"bad",LIBRARY)
    def test_wrong_body_chip_fails_closed(self):
        struct.pack_into("<I",self.memory,0xd690,0x8132)
        observer = self.observer()
        self.assertEqual(self.init(observer)["capture_error"],12)
        self.assertTrue(observer.disabled)
        self.assertFalse((Path(self.temp.name)/"pre-first-init/root.bin").exists())
    def test_table_outside_allowlist_never_reads(self):
        observer = self.observer([(0x14000,0xc000)])
        self.assertNotEqual(self.init(observer)["capture_error"],0)
        self.assertFalse(self.read_calls)
    def test_wrong_version_stops_before_main_read(self):
        self.memory[0xc000] ^= 1
        observer = self.observer()
        self.assertEqual(self.init(observer)["capture_error"],4)
        self.assertEqual(len(self.read_calls),4)
    def test_reordered_or_wrong_width_mailbox_stops(self):
        for events in [[(ASC_BASE+0x8808,0x20,3)],[(ASC_BASE+0x8800,1,2)],[(ASC_BASE+0x8800,1,3),(ASC_BASE+0x8800,2,3)]]:
            observer=self.observer()
            with self.assertRaises(ValueError):
                for event in events: observer.feed(*event)
            self.assertTrue(observer.disabled)
        self.assertFalse(self.read_calls)
    def test_attach_rejects_default_and_wrong_chip_before_tracer(self):
        hv=types.SimpleNamespace(p=types.SimpleNamespace(get_chipid=lambda:0x8132))
        with self.assertRaises(ValueError): attach(hv,ram_ranges=[(0x10000,0x10000)],library=LIBRARY,output=self.temp.name)
        with self.assertRaises(ValueError): attach(hv,ram_ranges=[(0x10000,0x10000)],library=LIBRARY,output=self.temp.name,approved_guest_session=True)
        self.assertFalse(self.read_calls)
    def test_exact_attach_contract_and_callback_rejection_without_target(self):
        class ADT(dict): model="Mac16,8"
        chosen=types.SimpleNamespace(board_id=4,system_firmware_version="mBoot-18000.161.10")
        adt=ADT({"/chosen":chosen,"/arm-io/gfx-asc":types.SimpleNamespace(get_reg=lambda index:(ASC_BASE,0x88000)),"/arm-io/sgx":types.SimpleNamespace(get_reg=lambda index:(0x288000000,0x3758000),gfx_shared_region_size=0x40000,gfx_shared_region_base=0x10000)})
        tracers=[]
        hv=types.SimpleNamespace(p=types.SimpleNamespace(get_chipid=lambda:0x6040),adt=adt,iface=types.SimpleNamespace(readmem=self.reader),add_tracer=lambda *args,**kwargs:tracers.append((args,kwargs)))
        chosen.system_firmware_version="wrong"
        with self.assertRaises(ValueError): attach(hv,ram_ranges=[(0x10000,0x10000)],library=LIBRARY,output=self.temp.name,approved_guest_session=True)
        self.assertFalse(tracers)
        chosen.system_firmware_version="mBoot-18000.161.10"
        modules={"m1n1":types.ModuleType("m1n1"),"m1n1.hv":types.ModuleType("m1n1.hv"),"m1n1.utils":types.ModuleType("m1n1.utils")}
        modules["m1n1.hv"].TraceMode=types.SimpleNamespace(SYNC="SYNC")
        modules["m1n1.utils"].irange=lambda address,size:(address,size)
        with patch.dict(sys.modules,modules):
            observer=attach(hv,ram_ranges=[(0x10000,0x10000)],library=LIBRARY,output=self.temp.name,approved_guest_session=True)
        self.assertEqual(len(tracers),1)
        self.assertEqual(tracers[0][0][0],(ASC_BASE+0x8800,0x10))
        self.assertFalse(self.read_calls)
        callback=tracers[0][1]["write"]
        callback(types.SimpleNamespace(addr=ASC_BASE+0x8800,data=0,flags=types.SimpleNamespace(WIDTH=3,MULTI=1)))
        self.assertTrue(observer.disabled)
        self.assertIn("multiword",observer.callback_error)
        self.assertFalse(self.read_calls)
    def test_changing_overlapping_graph_is_not_a_coherent_capture(self):
        def changing(address,size):
            if address==0x1c400 and size==0x479:
                self.memory[0xc400]^=1
            return self.reader(address,size)
        observer=Observer(changing,[(0x10000,0x10000)],0x10000,LIBRARY,self.temp.name)
        result=self.init(observer)
        self.assertEqual(result["capture_error"],9)
        self.assertIn("Incoherent",result["callback_error"])
        self.assertTrue(observer.disabled)
    def test_short_physical_read_disables_capture(self):
        observer=Observer(lambda address,size:b"",[(0x10000,0x10000)],0x10000,LIBRARY,self.temp.name)
        result=self.init(observer)
        self.assertEqual(result["capture_error"],9)
        self.assertIn("Short",result["callback_error"])
        self.assertTrue(observer.disabled)

if __name__ == "__main__": unittest.main()
