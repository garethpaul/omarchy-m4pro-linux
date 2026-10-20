import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_plan import edges

spec=importlib.util.spec_from_file_location('audit_elf',Path(__file__).resolve().parents[1]/'audit_elf.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class ActualElf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        def write(n,s): (cls.root/n).write_text(s)
        write('provider.c','int api(void) { return 42; }\n')
        write('consumer.c','extern int api(void); int entry(void) { return api(); }\n')
        write('v1.map','API_1.0 { global: api; local: *; };\n')
        write('v2.map','API_2.0 { global: api; local: *; };\n')
        write('forward.c','extern int api(void); int placeholder(void) { return api(); }\n')
        def cc(*args):subprocess.run(['cc','-shared','-fPIC','-nostdlib',*args],cwd=cls.root,check=True,capture_output=True)
        cc('provider.c','-Wl,-soname,libcontract.so.1','-Wl,--version-script=v1.map','-o','libcontract.so.1')
        cc('consumer.c','-L.','-l:libcontract.so.1','-Wl,--no-as-needed','-o','consumer.so')
        cc('provider.c','-Wl,-soname,libcontract.so.1','-Wl,--version-script=v2.map','-o','wrong.so')
        cc('provider.c','-Wl,-soname,libimpl.so.1','-Wl,--version-script=v1.map','-o','libimpl.so.1')
        cc('forward.c','-L.','-l:libimpl.so.1','-Wl,--no-as-needed','-Wl,-soname,libcontract.so.1','-Wl,--version-script=v1.map','-o','forward.so')
        cls.impl=(cls.root/'libimpl.so.1').read_bytes()
        cls.forward=(cls.root/'forward.so').read_bytes()
        cls.provider=(cls.root/'libcontract.so.1').read_bytes();cls.consumer=(cls.root/'consumer.so').read_bytes();cls.wrong=(cls.root/'wrong.so').read_bytes()
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_real_versioned_dependency(self):
        p=audit.parse_elf(self.provider);c=audit.parse_elf(self.consumer)
        self.assertEqual(p['soname'],'libcontract.so.1')
        self.assertIn('libcontract.so.1',c['needed'])
        self.assertEqual(c['version_requirements']['libcontract.so.1'],['API_1.0'])
        self.assertEqual(audit.check_edge(c,p,'libcontract.so.1'),[])
    def test_same_soname_missing_version_and_symbol_contract(self):
        c=audit.parse_elf(self.consumer);p=audit.parse_elf(self.wrong)
        issues=audit.check_edge(c,p,'libcontract.so.1')
        self.assertIn('missing_version:API_1.0',issues)
        self.assertIn('missing_symbol:api@API_1.0',issues)
    def test_symbol_moved_to_loaded_dependency_scope(self):
        c=audit.parse_elf(self.consumer);forward=audit.parse_elf(self.forward);implementation=audit.parse_elf(self.provider)
        self.assertIn('missing_symbol:api@API_1.0',audit.check_edge(c,forward,'libcontract.so.1'))
        self.assertEqual(audit.check_scope(c,forward,'libcontract.so.1',[implementation]),[])
        wrong=audit.parse_elf(self.wrong)
        self.assertIn('missing_version:API_1.0',audit.check_scope(c,wrong,'libcontract.so.1',[implementation]))

    def test_actual_file_graph_forwarding_and_wrong_version(self):
        consumer=audit.parse_elf(self.consumer);forward=audit.parse_elf(self.forward);impl=audit.parse_elf(self.impl)
        entries={'usr/bin/consumer':{'elf':consumer},'usr/lib/libcontract.so.1':{'elf':forward},'usr/lib/libimpl.so.1':{'elf':impl}}
        result,gaps=edges(entries,{'usr/bin/consumer'})
        self.assertEqual(gaps,[])
        self.assertEqual(result[('usr/bin/consumer','libcontract.so.1')]['issues'],[])
        entries['usr/lib/libcontract.so.1']={'elf':audit.parse_elf(self.wrong)}
        result,gaps=edges(entries,{'usr/bin/consumer'})
        self.assertIn('missing_version:API_1.0',result[('usr/bin/consumer','libcontract.so.1')]['issues'])
        self.assertIn('missing_symbol:api@API_1.0',result[('usr/bin/consumer','libcontract.so.1')]['issues'])

    def test_machine_mismatch(self):
        p=audit.parse_elf(self.provider);c=audit.parse_elf(self.consumer)
        p['machine']=183
        self.assertIn('architecture_mismatch',audit.check_edge(c,p,'libcontract.so.1'))
    def test_truncated_rejected(self):
        for size in (0,4,12,63,100):
            with self.subTest(size=size),self.assertRaises(ValueError):audit.parse_elf(self.provider[:size])
    def test_section_out_of_bounds_rejected(self):
        data=bytearray(self.provider);data[40:48]=(len(data)+4096).to_bytes(8,'little')
        with self.assertRaises(ValueError):audit.parse_elf(data)


class CrossReadOnly(unittest.TestCase):
    def test_actual_aarch64_object_and_independent_readelf(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a.c').write_text('int answer(void) { return 42; }\n')
            subprocess.run(['clang','--target=aarch64-linux-gnu','-c',str(root/'a.c'),'-o',str(root/'a.o')],check=True,capture_output=True)
            data=(root/'a.o').read_bytes();parsed=audit.parse_elf(data)
            self.assertEqual(parsed['machine'],183)
            result=subprocess.run(['readelf','-h',str(root/'a.o')],check=True,capture_output=True,text=True)
            self.assertIn('AArch64',result.stdout)

if __name__=='__main__':unittest.main()
