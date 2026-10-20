"""Offline source/pin/actual-input controls; never emits a real boot bundle."""
import ctypes
import hashlib
import importlib.util
import json
import marshal
import os
import shutil
from pathlib import Path
import struct
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
import zlib
import bundle
fmt=bundle.fmt
from test_format import synthetic


class LocalControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_read_bound_rejects_oversize(self):
        p=self.root/'bounded';p.write_bytes(b'x'*33)
        with self.assertRaises(fmt.Refused):bundle.read_bounded(p,32)

    def test_hash_pin_refuses_changed_file(self):
        p=self.root/'pinned';p.write_bytes(b'fixture')
        with self.assertRaises(fmt.Refused):bundle.pinned(p,'0'*64,100)

    def test_exact_source_ignores_timestamp_valid_cache(self):
        p=self.root/'source.py';raw=b'VALUE="VERIFIED_SOURCE_BYTES"\n';p.write_bytes(raw)
        cache=Path(importlib.util.cache_from_source(str(p)));cache.parent.mkdir()
        poison=compile('raise RuntimeError("unverified cache")','<controlled-fixture>','exec')
        encoded=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,int(p.stat().st_mtime),len(raw))+marshal.dumps(poison)
        cache.write_bytes(encoded)
        mod=bundle.execute_source(p,fmt.sha(raw),'fixture_verified_module')
        self.assertEqual(mod.VALUE,'VERIFIED_SOURCE_BYTES');self.assertEqual(cache.read_bytes(),encoded)

    def test_wrong_source_pin_never_executes(self):
        p=self.root/'bad.py';p.write_text('raise RuntimeError("must never run")')
        with self.assertRaises(fmt.Refused):bundle.execute_source(p,'0'*64,'fixture_refused')

    def copied_bootstrap(self):
        root=self.root/'copied';root.mkdir()
        for name in ('bundle.py','native_format.py','pins.json'):
            shutil.copyfile(bundle.HERE/name,root/name)
        return root

    def bootstrap(self,root):
        return subprocess.run(['python3','-B','-c','import sys;sys.path.insert(0,sys.argv[1]);import bundle;print(bundle.fmt.HEADER.size)',str(root)],capture_output=True,text=True)

    def test_native_format_timestamp_cache_ignored(self):
        root=self.copied_bootstrap();source=root/'native_format.py'
        cached=Path(importlib.util.cache_from_source(str(source)));cached.parent.mkdir()
        code=compile('raise RuntimeError("UNVERIFIED_NATIVE_FORMAT_CACHE_EXECUTED")','<controlled-fixture>','exec')
        encoded=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,int(source.stat().st_mtime),source.stat().st_size)+marshal.dumps(code)
        cached.write_bytes(encoded)
        result=self.bootstrap(root)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout,'48\n')
        self.assertEqual(cached.read_bytes(),encoded)

    def test_reviewed_pinset_tamper_refused_before_helper(self):
        root=self.copied_bootstrap();(root/'pins.json').write_text('{}\n')
        result=self.bootstrap(root)
        self.assertNotEqual(result.returncode,0);self.assertIn('Reviewed native-bundle pinset differs',result.stderr)

    def test_reviewed_pinset_oversize_refused(self):
        root=self.copied_bootstrap();(root/'pins.json').write_bytes(b'x'*((2<<20)+1))
        result=self.bootstrap(root)
        self.assertNotEqual(result.returncode,0);self.assertIn('pinset missing or exceeds bound',result.stderr)

    def test_format_helper_source_tamper_refused(self):
        root=self.copied_bootstrap();(root/'native_format.py').write_text('raise RuntimeError("UNREVIEWED_HELPER_EXECUTED")')
        result=self.bootstrap(root)
        self.assertNotEqual(result.returncode,0);self.assertIn('Pinned native-format source differs',result.stderr)
        self.assertNotIn('RuntimeError: UNREVIEWED_HELPER_EXECUTED',result.stderr)

    def test_destination_refuses_input_tree_and_existing_paths(self):
        src=self.root/'source';src.mkdir();(src/'capture').mkdir();(src/'evidence').mkdir()
        a=types.SimpleNamespace(loader_source=src,kernel_source=src,kernel_bundle=src,resident_source=src,dt_generator=src/'generator.py',probe_manifest=src/'evidence/manifest.json',capture=src/'capture/input.json')
        for path in (src/'new-output',src):
            with self.assertRaises(fmt.Refused):bundle.private_destination(a,path)
        bundle.private_destination(a,self.root/'separate-new-private-output')

    def test_future_report_rejects_synthetic_or_authorized_labels(self):
        a=types.SimpleNamespace(expected_capture_sha256='1'*64,expected_observer_sha256='2'*64,expected_bootargs_sha256='3'*64,expected_adt_sha256='4'*64,expected_usb_session='99999',storage_diagnostic=True)
        dtb=synthetic()[2]['dtb']
        report={'status':'UNRELOCATED_TEMPLATE_ONLY','synthetic_fixture':False,'runtime_fdt':False,'deployment_authorized':False,'hardware':'UNTESTED','profile_sha256':bundle.PINS['dt_profile_sha256'],'generator_sha256':bundle.PINS['dt_generator_sha256'],'capture_sha256':a.expected_capture_sha256,'observer_sha256':a.expected_observer_sha256,'bootargs_sha256':a.expected_bootargs_sha256,'adt_sha256':a.expected_adt_sha256,'usb_session':a.expected_usb_session,'loader_commit':bundle.PINS['loader_commit'],'kernel_commit':bundle.PINS['kernel_commit'],'dtb_sha256':fmt.sha(dtb),'dtb_bytes':len(dtb),'storage_diagnostic':True,'dtc_stderr_bytes':0,'nodes_checked':1,'warnings_disabled':False,'host_tools':{n:{'sha256':bundle.PINS['host_tools'][n]} for n in ('dtc','fdtget')}}
        # Metadata-only invented control. Never supplied to D or assembled with
        # real Image/initrd; it does not establish a validated DT.
        bundle.report_contract(report,a,dtb)
        for key,value in [('synthetic_fixture',True),('runtime_fdt',True),('deployment_authorized',True),('hardware','WORKS'),('capture_sha256','0'*64),('dtc_stderr_bytes',False),('warnings_disabled',True),('storage_diagnostic',1)]:
            with self.assertRaises(fmt.Refused):bundle.report_contract({**report,key:value},a,dtb)


@unittest.skipUnless(os.environ.get('J614S_NATIVE_INPUTS'),'Set private actual-input path for readonly real-input checks')
class ActualInputControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        values=json.loads(Path(os.environ['J614S_NATIVE_INPUTS']).read_text())
        pathkeys={'loader_binary','loader_elf','loader_source','kernel_source','kernel_bundle','initrd','probe_manifest','dt_generator','capture','observer_source','resident_source','diagnostics','dtb','dt_evidence'}
        cls.a=types.SimpleNamespace(**{k:Path(v) if k in pathkeys and v is not None else v for k,v in values.items()})
        cls.paths=bundle.tools()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_real_components_verify_independently(self):
        flat,layout,image,initrd,facts=bundle.independent_inputs(self.a,self.paths)
        self.assertEqual(layout.payload_offset,len(flat));self.assertLess(layout.file_end_offset,layout.payload_offset)
        self.assertEqual(fmt.sha(image),bundle.PINS['Image_sha256']);self.assertEqual(fmt.sha(initrd),bundle.PINS['initrd_sha256'])
        self.assertTrue(facts['loader']['flat_matches_elf'])

    def test_current03_refuses_before_dt_or_diagnostics(self):
        a=types.SimpleNamespace(**vars(self.a));a.diagnostics=self.root/'no-diagnostics';a.dtb=self.root/'does-not-exist.dtb';a.dt_evidence=self.root/'does-not-exist.json'
        capture_before=fmt.sha(a.capture.read_bytes())
        with self.assertRaisesRegex(ValueError,'Secondary slots are not all idle in WFE mode'):bundle.validate_all(a,self.paths)
        self.assertFalse(a.diagnostics.exists());self.assertEqual(fmt.sha(a.capture.read_bytes()),capture_before)

    def test_current03_cli_assemble_creates_no_bundle(self):
        command=['python3',str(bundle.HERE/'bundle.py'),'assemble']
        for key,value in vars(self.a).items():
            if value is None or key=='storage_diagnostic' or key=='diagnostics':continue
            command+=['--'+key.replace('_','-'),str(value)]
        output=self.root/'no-bundle';diagnostics=self.root/'no-diagnostics'
        command+=['--output',str(output),'--diagnostics',str(diagnostics),'--storage-diagnostic']
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertEqual(result.stderr,'')
        report=json.loads(result.stdout);self.assertEqual(report['reason'],'SECONDARY_SLOTS_NOT_IDLE_WFE')
        self.assertFalse(report['container_produced']);self.assertFalse(report['deployment_authorized'])
        self.assertFalse(output.exists());self.assertFalse(diagnostics.exists())

    def test_changed_real_loader_pin_stops_before_tools(self):
        wrong=self.root/'wrong-loader';wrong.write_bytes(b'NOT_THE_REAL_LOADER')
        with patch.object(bundle.subprocess,'run') as run:
            with self.assertRaises(fmt.Refused):bundle.loader_pair(wrong,self.a.loader_elf,self.paths)
        run.assert_not_called()

    def test_pinned_actual_c_crc_matches_python_on_small_fixtures(self):
        source=self.a.loader_source/'src/tinf/crc32.c';header=source.parent/'tinf.h'
        bundle.pinned(source,bundle.PINS['crc32_source_sha256'],2<<20)
        bundle.pinned(header,bundle.PINS['tinf_header_sha256'],2<<20)
        library=self.root/'host-crc32.so'
        subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror','-I',str(source.parent),str(source),'-o',str(library)],check=True,capture_output=True)
        native=ctypes.CDLL(str(library));native.tinf_crc32.argtypes=[ctypes.c_void_p,ctypes.c_uint];native.tinf_crc32.restype=ctypes.c_uint
        vectors=[b'',b'123456789',bytes(range(256)),*synthetic()[2].values()]
        for vector in vectors:
            data=ctypes.create_string_buffer(vector)
            self.assertEqual(native.tinf_crc32(data,len(vector)),zlib.crc32(vector))
        # This exercises only the architecture-independent checksum function;
        # not j614s_native_run, target instructions, placement or C handoff.
        self.assertEqual(fmt.sha(source.read_bytes()),bundle.PINS['crc32_source_sha256'])


if __name__=='__main__':unittest.main(verbosity=2)
