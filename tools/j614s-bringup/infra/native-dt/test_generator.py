#!/usr/bin/env python3
"""Synthetic host controls; no target APIs, target writes or live session edits."""
import argparse
import copy
import contextlib
import io
import sys
from unittest.mock import patch
import hashlib
import importlib.util
import marshal
import struct
import types
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
g=types.ModuleType('native_dt_generator');g.__file__=str(HERE/'generate.py')
exec(compile((HERE/'generate.py').read_bytes(),str(HERE/'generate.py'),'exec',dont_inherit=True,optimize=0),g.__dict__)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('observer-source','resident-source','loader-source','loader-binary','kernel-source','kernel-bundle','actual-capture','output'):
        ap.add_argument('--'+name,required=True,type=Path)
    if not __debug__:raise SystemExit('Optimized Python prohibited for host controls')
    a=ap.parse_args();p=g.profile();fixture=g.load(HERE/'synthetic-capture.json');results=[]
    def validate(c):return g.validate_capture(c,p,'99999',p['observer_sha256'],'1'*64,'2'*64,True)
    def negative(label,change):
        c=copy.deepcopy(fixture);change(c)
        try:validate(c)
        except (ValueError,KeyError,TypeError):results.append({'case':label,'status':'REFUSED'});return
        raise AssertionError('Accepted negative: '+label)
    validate(fixture);results.append({'case':'invented_12_cpu_fixture','status':'PASS','synthetic':True})
    cases=[('old_USB_session',lambda c:c.update(usb_enumeration='45')),
           ('observer_hash',lambda c:c.update(observer_sha256='0'*64)),
           ('bootargs_pair_hash',lambda c:c.update(bootargs_sha256='0'*64)),
           ('ADT_pair_hash',lambda c:c.update(adt_sha256='0'*64)),
           ('resident_helper_hash',lambda c:c.update(binary_sha256='0'*64)),
           ('board_identity',lambda c:c.update(board_id=3)),
           ('firmware_identity',lambda c:c.update(system_firmware_version='other')),
           ('target_write_capture',lambda c:c.update(target_memory_written=True)),
           ('exception_state',lambda c:c.update(exceptions=1)),
           ('all_secondary_flags_zero',lambda c:[r.update(resident_flag=0) for r in c['cpus'] if r['cpu_id']!=4]),
           ('summary_idle_false',lambda c:c.update(secondary_slots_idle=False)),
           ('WFE_false',lambda c:c.update(resident_wfe_mode=False)),
           ('secondary_target_pending',lambda c:c['cpus'][0].update(target_zero=False)),
           ('secondary_arguments_pending',lambda c:c['cpus'][0].update(arguments_zero=False)),
           ('live_mpidr_changed',lambda c:c['cpus'][0].update(expected_mpidr=2)),
           ('observed_mpidr_changed',lambda c:c['cpus'][0].update(observed_mpidr=2)),
           ('duplicate_CPU_slot',lambda c:c['cpus'].__setitem__(1,copy.deepcopy(c['cpus'][0]))),
           ('missing_CPU_slot',lambda c:c['cpus'].pop()),
           ('bool_as_integer',lambda c:c['private_session'].update(ram_size=True)),
           ('RAM_extent_overflow',lambda c:c['private_session'].update(ram_size=1<<64)),
           ('wrong_physical_size',lambda c:c['private_session'].update(physical_ram_size=16<<30)),
           ('usable_exceeds_physical',lambda c:c['private_session'].update(ram_size=25<<30)),
           ('resident_outside_usable',lambda c:c['private_session'].update(resident_end=c['private_session']['ram_base']+(17<<30))),
           ('table_outside_resident',lambda c:c['private_session'].update(table_address=c['private_session']['resident_end'])),
           ('missing_release_slot',lambda c:c['private_session']['release_addresses'].pop('10')),
           ('old_other_slot_release_pointer',lambda c:c['private_session']['release_addresses'].__setitem__('10',c['private_session']['release_addresses']['11'])),
           ('release_unaligned',lambda c:c['private_session']['release_addresses'].__setitem__('0',c['private_session']['release_addresses']['0']+1)),
           ('wrong_depth',lambda c:c['private_session']['boot_video'].update(depth=32)),
           ('display_inactive',lambda c:c['private_session']['boot_video'].update(display=0)),
           ('wrong_stride',lambda c:c['private_session']['boot_video'].update(stride=12100)),
           ('wrong_width',lambda c:c['private_session']['boot_video'].update(width=3025)),
           ('foreign_framebuffer_address',lambda c:c['private_session']['boot_video'].update(base=0x1000)),
           ('framebuffer_exposed_as_usable',lambda c:c['private_session'].update(ram_size=(24<<30)-0x1000000)),
           ('synthetic_label_missing',lambda c:c.pop('synthetic_fixture'))]
    for label,change in cases:negative(label,change)
    common=['--observer-source',str(a.observer_source),'--resident-source',str(a.resident_source),'--loader-source',str(a.loader_source),'--loader-binary',str(a.loader_binary),'--kernel-source',str(a.kernel_source),'--kernel-bundle',str(a.kernel_bundle),'--expected-observer-sha256',p['observer_sha256'],'--nonce','a'*32]
    with tempfile.TemporaryDirectory(prefix='native-dt-host-') as temp:
        root=Path(temp)
        def cli(extra):return subprocess.run(['python3',str(HERE/'generate.py'),*common,*extra],capture_output=True,text=True)
        actual_hash=g.sha(a.actual_capture);actual=g.load(a.actual_capture)
        current=cli(['--capture',str(a.actual_capture),'--output',str(root/'actual-refused'),'--expected-usb-session','63','--expected-capture-sha256',actual_hash,'--expected-bootargs-sha256',actual['bootargs_sha256'],'--expected-adt-sha256',actual['adt_sha256']])
        assert current.returncode==1 and 'Secondary slots are not all idle in WFE mode' in current.stdout and not current.stderr and not (root/'actual-refused').exists()
        assert g.sha(a.actual_capture)==actual_hash
        results.append({'case':'actual_session63_original_capture','status':'REFUSED_BEFORE_OUTPUT','secondary_idle':False,'WFE':False,'capture_unchanged':True,'hardware':'NOT_QUALIFIED'})
        syn=['--capture',str(HERE/'synthetic-capture.json'),'--expected-capture-sha256',g.sha(HERE/'synthetic-capture.json'),'--synthetic-fixture','--expected-usb-session','99999','--expected-bootargs-sha256','1'*64,'--expected-adt-sha256','2'*64]
        for storage in (False,True):
            out=root/('storage' if storage else 'minimal');run=cli([*syn,'--output',str(out),*(['--storage-diagnostic'] if storage else [])]);assert run.returncode==0 and not run.stderr,(run.stdout,run.stderr)
            report=g.load(out/'template-result.json');assert report['synthetic_fixture'] and report['runtime_fdt'] is False and report['deployment_authorized'] is False
            results.append({'case':'dtc_fdtget_synthetic_'+('ANS' if storage else 'minimal'),'status':'PASS','nodes_checked':report['nodes_checked'],'dtc_diagnostics_bytes':(out/'dtc.stderr').stat().st_size,'warnings_disabled':False,'synthetic':True})
        good=root/'storage'/'UNRELOCATED-template.dtb'
        def mutate_dtb(label,args):
            dst=root/(label+'.dtb');shutil.copyfile(good,dst);subprocess.run(['fdtput',*args[:1],str(dst),*args[1:]],check=True,capture_output=True)
            try:g.verify_dtb(dst,fixture,p,'a'*32,True)
            except (ValueError,subprocess.CalledProcessError):results.append({'case':label,'status':'REFUSED'});return
            raise AssertionError('Mutated DT accepted: '+label)
        mutate_dtb('added_SMC_node',['-c','/smc@1234'])
        mutate_dtb('allowed_node_disabled',['-ts','/usb@38a280000','status','disabled'])
        mutate_dtb('CPU_address_cells_changed',['-tx','/cpus','#address-cells','1'])
        mutate_dtb('added_MTP_reservation',['-c','/reserved-memory/mtp-firmware@0'])
        mutate_dtb('wrong_initrd_width',['-tx','/chosen','linux,initrd-start','0'])
        mutate_dtb('wrong_memory_discovery',['-ts','/memory@0','device_type','other'])
        mutate_dtb('extra_loader_reservation_property',['-tx','/reserved-memory/ramoops@3ff00000','no-map','0'])
        mutate_dtb('runtime_memory_before_loader_patch',['-tx','/memory@0','reg','8','0','1','0'])
        mutate_dtb('forbidden_one_CPU_flag',['-ts','/chosen','bootargs','maxcpus=1'])
        mutate_dtb('wrong_ANS_register',['-tx','/nvme@44dcc0000','reg','4','4dcc0000','0','30004','4','09600000','0','4000'])
        mutate_dtb('forbidden_ANS_power_control',['-tx','/nvme@44dcc0000','power-domains','1'])
        mutate_dtb('wrong_USB_interrupt',['-tx','/usb@38a280000','interrupts','0','1652','4'])
        mutate_dtb('GPU_compatible_on_allowed_node',['-ts','/nvme@44dcc0000','compatible','apple,agx-t6040'])
        mutate_dtb('wrong_DART_DMA_extent',['-tx','/iommu@38af00000','apple,dma-range','0','0','2','0'])
        mutate_dtb('wrong_framebuffer_stride',['-tx','/chosen/framebuffer@'+format(fixture['private_session']['boot_video']['base'],'x'),'stride','12100'])
        for label, extra in [('wrong_kernel_source',['--kernel-source',str(a.loader_source)]),('wrong_loader_binary',['--loader-binary',str(root/'bad-loader')]),('wrong_USB_CLI',['--expected-usb-session','45']),('wrong_capture_hash',['--expected-capture-sha256','0'*64]),('existing_output',[])]:
            out=root/label
            if label=='wrong_loader_binary':(root/'bad-loader').write_bytes(b'bad')
            if label=='existing_output':out.mkdir()
            run=cli([*syn,'--output',str(out),*extra]);assert run.returncode==1 and not run.stderr
            assert label=='existing_output' or not out.exists()
            results.append({'case':label,'status':'REFUSED_BEFORE_DT'})
        # Reproduce a timestamp-valid forged cache against actual helper source,
        # then prove checked-byte execution ignores it and runs real verification.
        helper=root/'kernel_build.py';helper.write_bytes((HERE.parent/'kernel_build.py').read_bytes());helper_hash=g.sha(helper)
        cache=Path(importlib.util.cache_from_source(str(helper)));cache.parent.mkdir()
        forged=compile('CACHE_EXECUTED=True\ndef verify(bundle): return None\n',str(helper),'exec')
        stamp=int(helper.stat().st_mtime)&0xffffffff
        cache.write_bytes(importlib.util.MAGIC_NUMBER+struct.pack('<III',0,stamp,helper.stat().st_size)+marshal.dumps(forged))
        oldspec=importlib.util.spec_from_file_location('cache_red_control',helper);old=importlib.util.module_from_spec(oldspec);oldspec.loader.exec_module(old)
        assert g.sha(helper)==helper_hash and old.CACHE_EXECUTED and old.verify(root/'missing-bundle') is None
        fixed=g.execute_verified_source(helper,helper_hash,'cache_green_control')
        assert not hasattr(fixed,'CACHE_EXECUTED')
        try:fixed.verify(root/'missing-bundle')
        except (ValueError,OSError):pass
        else:raise AssertionError('Real artifact verifier did not reject missing bundle')
        try:g.execute_verified_source(helper,'0'*64,'wrong_source_hash')
        except ValueError:pass
        else:raise AssertionError('Changed Python helper source accepted')
        results.append({'case':'timestamp_valid_forged_helper_pyc','before':'FORGED_CACHE_INCORRECTLY_BYPASSES_ARTIFACT_VERIFICATION','after':'HASHED_SOURCE_BYTES_EXECUTED_AND_MISSING_BUNDLE_REFUSED','source_sha256':helper_hash,'external_helper_edited':False})
        results.append({'case':'wrong_Python_helper_source_hash','status':'REFUSED_BEFORE_EXECUTION'})
        malformed=root/'duplicate.json';malformed.write_text('{"observer_sha256":"a","observer_sha256":"b"}')
        try:g.load(malformed)
        except ValueError:results.append({'case':'duplicate_JSON_key','status':'REFUSED'})
        else:raise AssertionError('duplicate JSON accepted')
        with patch.object(g,'render',return_value='/dts-v1/; / { bad@0 { }; };'):
            try:g.verify_dtb(good,fixture,p,'a'*32,True,diagnostic_dir=root)
            except g.CompilerDiagnostics as error:
                assert error.returncode==0 and b'unit_address_vs_reg' in error.stderr and (root/'reference-dtc.stderr').read_bytes()==error.stderr
            else:raise AssertionError('Reference compiler warning accepted/lost')
        results.append({'case':'exact_reference_compiler_warning','status':'REFUSED_AND_DIAGNOSTICS_RETAINED','render_injection':'synthetic host fault only'})
        # Real compiler warning control, not a fabricated success or disabled check.
        warning_dts=root/'warning.dts';warning_dts.write_text('/dts-v1/; / { bad@0 { }; };')
        warning=subprocess.run(['dtc','-I','dts','-O','dtb','-o',str(root/'warning.dtb'),str(warning_dts)],capture_output=True)
        assert warning.returncode==0 and b'unit_address_vs_reg' in warning.stderr
        results.append({'case':'real_dtc_warning_control','status':'DIAGNOSTIC_OBSERVED','warning_check':'unit_address_vs_reg','diagnostic_bytes':len(warning.stderr),'generator_policy':'Any compiler stderr refuses qualification; no -Wno flags'})
        (a.output.parent/'compiler-warning-control.txt').write_text(warning.stderr.decode().replace(str(root),'<synthetic-fixture>'))
        for label, injected in [('warning','/dts-v1/; / { bad@0 { }; };'),('syntax-error','/dts-v1/; / {')]:
            out=root/('pipeline-'+label)
            argv=['generate.py',*common,*syn,'--output',str(out)]
            with patch.object(sys,'argv',argv), patch.object(g,'render',return_value=injected), contextlib.redirect_stdout(io.StringIO()):
                try:g.main()
                except SystemExit as error:assert error.code == 1
                else:raise AssertionError('Compiler diagnostics were accepted')
            failure=g.load(out/'compiler-failure.json');assert failure['stderr_bytes'] and failure['status']=='REFUSED_COMPILER_DIAGNOSTICS' and not (out/'template-result.json').exists()
            assert (out/'dtc.stderr').exists() and (out/'UNRELOCATED-template.dts').read_text()==injected
            results.append({'case':'actual_generator_compiler_'+label+'_fault_control','status':'REFUSED_AND_DIAGNOSTICS_RETAINED','render_injection':'synthetic host fault only','compiler_exit_code':failure['exit_code'],'warnings_disabled':False})
    report={'status':'PASS','hardware':'UNTESTED','synthetic_fixture_only_for_positive_generation':True,'checks':results,'checks_count':len(results),'actual_capture_not_modified':True,'tools':{name:{'sha256':g.sha(Path(shutil.which(name))),'version':subprocess.check_output([name,'--version'],text=True).splitlines()[0]} for name in ('dtc','fdtget','fdtput')},'scope':'Offline input refusal, exact-source binding and actual dtc/fdtget/fdtput controls; no target operation or runtime FDT qualification'}
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(f'PASS: {len(results)} offline controls; actual capture refused; positive outputs synthetic/unrelocated')


if __name__=='__main__':main()
