#!/usr/bin/env python3
"""Host controls for preparation guard failures; no target APIs or actual positive replay."""
import ast
import copy
import hashlib
import json
import os
import stat
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
SOURCE=(HERE/'prepare_supervised.py').read_bytes()
m=types.ModuleType('preparation_tested');m.__file__=str(HERE/'prepare_supervised.py')
exec(compile(SOURCE,m.__file__,'exec',dont_inherit=True,optimize=0),m.__dict__)


def observations():
    # Wholly synthetic model of shared fields, never an admissible real capture.
    base=16<<20;ids=(0,1,2,3,4,5,6,7,10,11,12,13);table=base+0xb0198
    video=dict(base=0x90000000,display=1,stride=12096,width=3024,height=1964,depth=30)
    memory=dict(resident_base=base,resident_end=base+0x350000,usable_base=0x1000,
      usable_size=1<<30,physical_base=0,physical_size=24<<30,boot_video=video,bootargs_top=base+(4<<20))
    boot=bytearray((i*17)%256 for i in range(1152));struct.pack_into('<H',boot,0,3)
    struct.pack_into('<QQQ',boot,16,memory['usable_base'],memory['usable_size'],memory['bootargs_top'])
    boot=bytes(boot);adt=b'SYNTHETIC ONLY ADT bytes'
    summary=dict(secondary_flags_set=11,secondary_slots_idle=True,resident_wfe_mode=True)
    session=dict(usb_enumeration='99999',bootargs_sha256=m.sha(boot),adt_sha256=m.sha(adt),resident_binary_sha256='2'*64)
    stage=dict(synthetic_fixture=True,session=session,memory=memory,cpu_state=summary,
      helper_sources={'cpu_observer_sha256':'1'*64},protected_metadata=[dict(name='live-bootargs',size=1152),dict(name='live-adt',size=len(adt))])
    q=dict(resident_base=base,resident_end=memory['resident_end'],ram_base=memory['usable_base'],ram_size=memory['usable_size'],
      physical_ram_base=0,physical_ram_size=24<<30,boot_video=video,table_address=table,
      release_addresses={str(cpu):table+cpu*64+16 for cpu in ids})
    cpu=dict(synthetic_fixture=True,usb_enumeration='99999',bootargs_sha256=m.sha(boot),adt_sha256=m.sha(adt),
      binary_sha256='2'*64,observer_sha256='1'*64,private_session=q,cpus=[dict(cpu_id=cpu) for cpu in ids],slot_snapshot_sha256='3'*64,**summary)
    return cpu,stage,boot,adt


class Preparation(unittest.TestCase):
    def test_missing_storage_flag_refused(self):
        with self.assertRaisesRegex(ValueError,'STORAGE_DIAGNOSTIC_EXPLICIT_TRUE_REQUIRED'):
            m.require_storage({'bundle_inputs':{}})

    def test_false_storage_flag_refused(self):
        for value in (False,None,0,1,'true'):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'STORAGE_DIAGNOSTIC_EXPLICIT_TRUE_REQUIRED'):
                m.require_storage({'bundle_inputs':{'storage_diagnostic':value}})
        m.require_storage({'bundle_inputs':{'storage_diagnostic':True}})

    def test_storage_refusal_precedes_outputs(self):
        with tempfile.TemporaryDirectory(prefix='preparation-host-') as tmp:
            root=Path(tmp);seed=root/'seed.json';out=root/'must-remain-absent'
            for options in ({},{'storage_diagnostic':False}):
                raw=json.dumps(dict(bundle_inputs=options)).encode();seed.write_bytes(raw)
                args=types.SimpleNamespace(seed=seed,expected_seed_sha256=m.sha(raw),output=out)
                with self.assertRaisesRegex(ValueError,'STORAGE_DIAGNOSTIC_EXPLICIT_TRUE_REQUIRED'):m.prepare(args)
                self.assertFalse(out.exists())

    def test_dirty_seed_hash_refused_before_outputs(self):
        with tempfile.TemporaryDirectory(prefix='preparation-host-') as tmp:
            root=Path(tmp);seed=root/'seed.json';raw=b'{"bundle_inputs":{"storage_diagnostic":true}}';seed.write_bytes(raw+b' ')
            args=types.SimpleNamespace(seed=seed,expected_seed_sha256=m.sha(raw),output=root/'absent')
            with self.assertRaisesRegex(ValueError,'INPUT_SHA256_DIFFERS'):m.prepare(args)
            self.assertFalse(args.output.exists())

    def test_output_under_capture_parent_or_source_refused(self):
        with tempfile.TemporaryDirectory(prefix='preparation-host-') as tmp:
            root=Path(tmp);capture=root/'capture';capture.mkdir();source=root/'source';source.mkdir()
            for output in (capture/'diagnostics',source/'new-work'):
                with self.subTest(output=output.name),self.assertRaisesRegex(ValueError,'OUTPUT_INSIDE_INPUT_OR_SOURCE'):
                    m.separated(output,[capture,source])
                self.assertFalse(output.exists())
            link=root/'linked-capture';link.symlink_to(capture,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'OUTPUT_INSIDE_INPUT_OR_SOURCE'):m.separated(link/'new-work',[capture])
            self.assertEqual(m.separated(root/'sibling',[capture,source]),root/'sibling')

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory(prefix='preparation-host-') as tmp:
            p=Path(tmp)/'existing';p.write_bytes(b'preserve-exact')
            with self.assertRaisesRegex(ValueError,'FRESH_DESTINATION'):m.separated(p,[])
            self.assertEqual(p.read_bytes(),b'preserve-exact')

    def test_shared_field_model_and_honest_slot_limit(self):
        result=m.shared_observations(*observations())
        self.assertEqual(result['shared_fields'],'MATCH')
        self.assertEqual(result['raw_slot_snapshot_cross_capture'],'UNPROVABLE_FROM_FROZEN_STAGING_SCHEMA')
        self.assertEqual(result['liveness'],'UNQUALIFIED')

    def test_session_hash_identity_geometry_and_slots_mismatch(self):
        changes=[lambda c,s:s['session'].update(usb_enumeration='99998'),
          lambda c,s:s['session'].update(bootargs_sha256='0'*64),lambda c,s:s['session'].update(adt_sha256='0'*64),
          lambda c,s:s['session'].update(resident_binary_sha256='0'*64),lambda c,s:c.update(observer_sha256='0'*64),
          lambda c,s:c['private_session'].update(resident_base=0),lambda c,s:c['private_session'].update(ram_size=0),
          lambda c,s:c['private_session'].update(table_address=0),lambda c,s:c['private_session']['release_addresses'].update({'1':0}),
          lambda c,s:s['cpu_state'].update(resident_wfe_mode=False),lambda c,s:c.update(slot_snapshot_sha256='invalid')]
        for index,change in enumerate(changes):
            with self.subTest(index=index),self.assertRaises(ValueError):
                cpu,stage,boot,adt=observations();change(cpu,stage);m.shared_observations(cpu,stage,boot,adt)

    def test_original_metadata_must_match_exact_bytes(self):
        cpu,stage,boot,adt=observations()
        with self.assertRaisesRegex(ValueError,'ORIGINAL_BOOTARGS_OR_ADT_DIFFERS'):m.shared_observations(cpu,stage,boot[:-1]+b'changed',adt)
        with self.assertRaisesRegex(ValueError,'ORIGINAL_BOOTARGS_OR_ADT_DIFFERS'):m.shared_observations(cpu,stage,boot,adt+b'changed')
        changed=bytearray(boot);struct.pack_into('<Q',changed,32,123);changed=bytes(changed)
        cpu['bootargs_sha256']=stage['session']['bootargs_sha256']=m.sha(changed)
        with self.assertRaisesRegex(ValueError,'ORIGINAL_BOOTARGS_REVISION_OR_TOP_DIFFERS'):m.shared_observations(cpu,stage,changed,adt)

    def test_exact_helper_pins_and_cache_independence(self):
        with tempfile.TemporaryDirectory(prefix='preparation-host-') as tmp:
            root=Path(tmp)
            for name in m.SOURCE_PINS:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((REPO/name).read_bytes())
            self.assertEqual(set(m.checked_sources(root)),set(m.SOURCE_PINS))
            path=root/'recovery/supervised_child.py';path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'INPUT_SHA256_DIFFERS'):m.checked_sources(root)
            module=m.execute(b'value=7\n',root/'not-cached.py','fixture_exact_source');self.assertEqual(module.value,7)

    def test_namespace_preserves_seed_and_explicit_storage_command(self):
        seed={'bundle_inputs':{key:'/synthetic/input' for key in m.BUNDLE_KEYS}}
        seed['bundle_inputs']['storage_diagnostic']=True;before=copy.deepcopy(seed);cpu=observations()[0]
        ns=m.namespace(seed,Path('/synthetic/fresh-cpu.json'),cpu,'4'*64)
        argv=m.bundle_argv(ns,'assemble',Path('/synthetic/separate-work/diagnostics'),output=Path('/synthetic/separate-work/container'))
        self.assertEqual(seed,before);self.assertEqual(argv.count('--storage-diagnostic'),1)
        self.assertIn('/synthetic/separate-work/diagnostics',argv)
        self.assertEqual(ns.expected_usb_session,'99999')

    def test_no_target_interface_inputs_or_cli_modes(self):
        # Lexical rejection happens before any attempted stat/open of these paths.
        for path in ('/dev/ttyACM0','/sys/class/tty/example','/proc/example'):
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'TARGET_OR_KERNEL_INTERFACE_INPUT_FORBIDDEN'):
                m.read_bound(Path(path),4096)
        tree=ast.parse(SOURCE)
        forbidden={'m1n1','serial','usb','read_pmu_counter'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):self.assertFalse(any(n.name.split('.')[0] in forbidden for n in node.names))
            elif isinstance(node,ast.ImportFrom):self.assertNotIn((node.module or '').split('.')[0],forbidden)
        helptext=subprocess.check_output([sys.executable,str(HERE/'prepare_supervised.py'),'--help'],text=True)
        self.assertNotIn('--operator-present',helptext);self.assertNotIn('--mode',helptext)
        self.assertNotIn('--vector',helptext);self.assertNotIn('--stage ',helptext)

    def test_original_bootargs_padding_preserved_by_pinned_plan_helper(self):
        # Execute only the pinned pure BootArgs function, never the stager entry.
        path=REPO/'recovery/supervised_child.py';raw=m.pinned(path,m.SOURCE_PINS['recovery/supervised_child.py'])
        selected=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in ('require','copied_bootargs')]
        namespace={'struct':struct};exec(compile(ast.Module(body=selected,type_ignores=[]),'pure-pinned-bootargs','exec'),namespace)
        cpu,stage,original,_=observations();new_top=stage['memory']['bootargs_top']+(64<<20)
        copied=namespace['copied_bootargs'](original,stage['memory']['bootargs_top'],new_top)
        self.assertEqual(copied[:32],original[:32]);self.assertEqual(copied[40:],original[40:])
        self.assertEqual(struct.unpack_from('<Q',copied,32)[0],new_top)
        self.assertNotEqual(m.sha(copied),m.sha(original))

    def test_phase_allowlist_forbids_target_modes(self):
        stager=types.SimpleNamespace(__file__=str(REPO/'recovery/supervised_child.py'))
        valid=['plan','--context','/synthetic/context.json','--expected-context-sha256','0'*64,'--operator-present']
        m.validate_phase(stager,valid,'plan-only')
        for mode in ('stage','vector'):
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'HOST_PHASE_MODE_FORBIDDEN'):
                m.validate_phase(stager,[mode,*valid[1:]],'plan-only')
        with self.assertRaisesRegex(ValueError,'HOST_PHASE_NOT_ALLOWED'):m.validate_phase(stager,valid,'stage')
        bundle=types.SimpleNamespace(__file__=str(REPO/'integration/native-bundle/bundle.py'))
        for mode in ('assemble','verify'):m.validate_phase(bundle,[mode,'--storage-diagnostic'],mode)
        generator=types.SimpleNamespace(__file__=str(REPO/'infra/native-dt/generate.py'))
        m.validate_phase(generator,['--capture','/synthetic/input','--storage-diagnostic'],'generate-dt')
        with self.assertRaisesRegex(ValueError,'HOST_PHASE_DIAGNOSTIC_FLAG_DIFFERS'):
            m.validate_phase(generator,['--capture','/synthetic/input'],'generate-dt')
        self.assertEqual(set(m.PHASES),{'generate-dt','assemble','verify','plan-only'})

    def test_phase_failure_retains_fd_stderr_and_private_trace(self):
        with tempfile.TemporaryDirectory(prefix='preparation-host-') as tmp:
            root=Path(tmp);before=list(sys.argv)
            def fake_host_main():
                print('synthetic host phase stdout')
                os.write(2,b'synthetic host subprocess stderr\n')
                raise ValueError('SYNTHETIC_PRIVATE_PHASE_REASON')
            module=types.SimpleNamespace(__file__=str(REPO/'recovery/supervised_child.py'),main=fake_host_main)
            try:
                m.invoke(module,['plan','--context','/synthetic/context','--expected-context-sha256','0'*64,'--operator-present'],root,'plan-only')
            except ValueError as error:m.record_failure(root,error)
            else:self.fail('phase exception was hidden')
            self.assertEqual(sys.argv,before)
            self.assertIn('synthetic host subprocess stderr',(root/'plan-only.stderr').read_text())
            self.assertIn('SYNTHETIC_PRIVATE_PHASE_REASON',(root/'FAILED.traceback.txt').read_text())
            self.assertEqual(stat.S_IMODE((root/'FAILED.traceback.txt').stat().st_mode),0o600)
            self.assertFalse((root/'stage-state.json').exists())
            with self.assertRaises(FileExistsError):m.record_failure(root,ValueError('preserve previous failure'))


if __name__=='__main__':
    if not __debug__:raise SystemExit('Optimized Python prohibited')
    unittest.main()
