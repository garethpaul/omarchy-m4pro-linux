#!/usr/bin/env python3
"""Create a private UNRELOCATED diagnostic DT template; never contact a target."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import types

HERE = Path(__file__).resolve().parent
PROFILE_SHA = '4ad1e0c76532744bb9c424930c8fc0f1158c40389f26f03dc6e7e53ebc8448bc'
U64 = 1 << 64


class CompilerDiagnostics(ValueError):
    def __init__(self, result):
        super().__init__('Reference template compiler diagnostics retained in exception')
        self.stdout=result.stdout
        self.stderr=result.stderr
        self.returncode=result.returncode


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def decode(data):
    require(len(data) <= 2 << 20, 'Input JSON too large')
    return json.loads(data.decode(), object_pairs_hook=pairs)


def load(path):
    return decode(path.read_bytes())


def load_capture(path, expected_sha256):
    data=path.read_bytes()
    require(type(expected_sha256) is str and re.fullmatch('[0-9a-f]{64}',expected_sha256) and hashlib.sha256(data).hexdigest() == expected_sha256, 'Capture file differs from explicit expected hash')
    return decode(data)


def integer(value):
    return type(value) is int and 0 <= value < U64


def extent(base, size):
    return integer(base) and integer(size) and size > 0 and base + size < U64


def inside(base, size, outer, total):
    return extent(base, size) and extent(outer, total) and outer <= base and base + size <= outer + total


def overlap(a, n, b, m):
    return a < b + m and b < a + n


def profile():
    path = HERE/'source-profile-v1.json'
    require(sha(path) == PROFILE_SHA, 'Source profile changed; review/version/re-pin required')
    p = load(path)
    for name, expected in p['templates'].items():
        require(sha(HERE/name) == expected, 'Versioned template changed')
    require(sha(HERE/'comparison-index.json') == p['comparison_index_sha256'], 'Comparison index changed')
    return p


def validate_capture(c, p, expected_session, observer_sha, bootargs_sha, adt_sha, synthetic=False):
    for value in (observer_sha, bootargs_sha, adt_sha):
        require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'Expected evidence hash missing/invalid')
    require(observer_sha == p['observer_sha256'] == c['observer_sha256'], 'Observer source hash differs')
    require(c['bootargs_sha256'] == bootargs_sha and c['adt_sha256'] == adt_sha, 'Paired bootargs/ADT hash differs')
    require(type(expected_session) is str and re.fullmatch('[0-9]+', expected_session) and c['usb_enumeration'] == expected_session, 'USB session differs')
    require(c.get('synthetic_fixture', False) is synthetic, 'Synthetic fixture must be explicitly labeled and selected')
    require(c['binary_sha256'] == p['resident_binary_sha256'], 'Resident helper binary differs')
    require(c['model'] == 'Mac16,8' and type(c['board_id']) is int and c['board_id'] == 4 and c['system_firmware_version'] == 'mBoot-18000.161.10', 'Board/firmware differs')
    require(c['boot_cpu'] == 4 and c['boot_mpidr'] == 0x80010100, 'Boot CPU differs')
    require(c['target_memory_written'] is False and c['code_executed_via_call'] is False and c['cores_started'] is False and c['watchdog_action'] == 'unchanged' and type(c['exceptions']) is int and c['exceptions'] == 0, 'Capture is not an exception-free read-only observation')
    cpus = p['cpus']; rows = c['cpus']
    require(type(rows) is list and len(rows) == len(cpus), 'CPU slot count differs')
    require([r['cpu_id'] for r in rows] == [x[0] for x in cpus], 'CPU slot order/identity differs')
    for row, (cpu, mpidr, _) in zip(rows, cpus):
        require(type(row['cpu_id']) is int and type(row['expected_mpidr']) is int and row['expected_mpidr'] == mpidr, 'Live ADT CPU identity differs')
        require(integer(row['resident_flag']) and integer(row['observed_mpidr']), 'Invalid CPU slot fields')
        require(row['target_zero'] in (True, False) and type(row['target_zero']) is bool and type(row['arguments_zero']) is bool, 'Invalid CPU slot flags')
        if row['resident_flag'] or cpu == 4:
            require(row['observed_mpidr'] == mpidr, 'Active slot MPIDR differs')
    secondaries = [r for r in rows if r['cpu_id'] != 4]
    idle = all(r['resident_flag'] and r['target_zero'] and r['arguments_zero'] for r in secondaries)
    require(c['secondary_slots_idle'] is True and idle and type(c['secondary_flags_set']) is int and c['secondary_flags_set'] == 11 and c['resident_wfe_mode'] is True, 'Secondary slots are not all idle in WFE mode; no template produced')
    q = c['private_session']
    for key in ('resident_base', 'resident_end', 'ram_base', 'ram_size', 'physical_ram_base', 'physical_ram_size', 'table_address'):
        require(integer(q[key]), 'Invalid private address/size field')
    base, end = q['resident_base'], q['resident_end']
    require(end > base and inside(base, end-base, q['ram_base'], q['ram_size']), 'Resident outside usable RAM')
    require(inside(q['ram_base'], q['ram_size'], q['physical_ram_base'], q['physical_ram_size']) and q['physical_ram_base'] == q['ram_base'] & ~((1 << 32)-1) and q['physical_ram_size'] == 24 << 30, 'Physical/usable RAM ownership differs')
    require(q['ram_base'] % 0x4000 == 0 and q['ram_size'] % 0x4000 == 0 and q['ram_size'] >= (1 << 32) + end-base, 'Usable RAM envelope cannot hold loader allocation')
    require(inside(q['table_address'], 14*64, base, end-base), 'Spin table outside resident ownership')
    releases = q['release_addresses']
    require(type(releases) is dict and set(releases) == {str(cpu) for cpu, _, _ in cpus}, 'Release-address identity set differs')
    for cpu, _, _ in cpus:
        address = releases[str(cpu)]
        require(integer(address) and address % 8 == 0 and address == q['table_address'] + cpu*64 + 16 and inside(address, 8, base, end-base), 'Release pointer outside exact owned slot')
    v = q['boot_video']
    require(set(v) == {'base','display','stride','width','height','depth'} and all(integer(x) for x in v.values()), 'Invalid paired boot-video schema')
    # Exact guard in pinned6249, not a copied output address. Render still uses capture values.
    require(v['base'] == 1124735713280 and v['display'] != 0 and v['stride'] == 12096 and v['width'] == 3024 and v['height'] == 1964 and v['depth'] & 0xff == 30, 'Video differs from exact loader guard')
    size = v['stride']*v['height']
    require(v['stride'] == v['width']*4 and v['base'] % 0x4000 == 0 and inside(v['base'], size, q['physical_ram_base'], q['physical_ram_size']), 'Framebuffer geometry/physical ownership invalid')
    require(not overlap(v['base'], size, q['ram_base'], q['ram_size']) and not overlap(v['base'], size, base, end-base), 'Framebuffer overlaps usable allocation or resident')
    return q


def run(*args):
    return subprocess.check_output(list(map(str, args)), stderr=subprocess.PIPE)


def execute_verified_source(path, expected_sha256, name):
    """Execute exactly the checked bytes; never consult a timestamp .pyc cache."""
    data=path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected_sha256, 'Python helper source hash differs')
    module=types.ModuleType(name)
    module.__file__=str(path.resolve())
    exec(compile(data,str(path), 'exec',dont_inherit=True,optimize=0),module.__dict__)
    return module


def verify_sources(a, p):
    require(sha(a.observer_source) == p['observer_sha256'], 'Supplied observer source differs')
    for source, commit in ((a.kernel_source, p['kernel_commit']), (a.loader_source, p['loader_commit'])):
        require(run('git','-C',source,'rev-parse','HEAD').decode().strip() == commit and not run('git','-C',source,'status','--porcelain'), 'Exact clean source checkout required')
    for name, expected in p['kernel_files'].items():
        require(sha(a.kernel_source/name) == expected, 'Kernel resource/compatible source differs')
    require(sha(a.loader_source/'src/j614s_native.c') == p['loader_source_sha256'] and sha(a.loader_binary) == p['loader_binary_sha256'], 'Loader source or reproduced binary differs')
    kb=execute_verified_source(HERE.parent/'kernel_build.py',p['python_helpers']['kernel_build.py'],'native_dt_kernel_build')
    kb.verify(a.kernel_bundle)
    contract = load(a.kernel_bundle/'contract.json')
    require(contract['source']['head'] == p['kernel_commit'] and contract['source']['dirty_diff_sha256'] == hashlib.sha256(b'').hexdigest() and not contract['source']['untracked'], 'Kernel artifact source differs')
    require(sha(a.kernel_bundle/'Image') == p['Image_sha256'] and sha(a.kernel_bundle/'.config') == p['config_sha256'], 'Kernel Image/config differs')
    require(sha(a.resident_source/'build/m1n1.bin') == p['resident_binary_sha256'] and sha(a.resident_source/'build/m1n1-raw.elf') == p['resident_elf_sha256'], 'Resident ELF/binary pair differs')
    with tempfile.TemporaryDirectory(prefix='dt-resident-pair-') as temp:
        flat = Path(temp)/'resident.bin'
        run('llvm-objcopy','-O','binary','--strip-debug',a.resident_source/'build/m1n1-raw.elf',flat)
        require(sha(flat) == p['resident_binary_sha256'], 'Resident ELF flattening differs')
    symbols = {}
    for line in run('llvm-nm','-S',a.resident_source/'build/m1n1-raw.elf').decode().splitlines():
        words = line.split()
        if len(words) == 4:
            symbols[words[3]] = (int(words[0],16), int(words[1],16))
    require(symbols['spin_table'][1] >= 14*64, 'Local spin table too small')
    return symbols


def verify_inputs(a, p):
    """Preferred offline bundler entry; returned capture contains PRIVATE addresses."""
    c=load_capture(a.capture,a.expected_capture_sha256)
    q=validate_capture(c,p,a.expected_usb_session,a.expected_observer_sha256,a.expected_bootargs_sha256,a.expected_adt_sha256,a.synthetic_fixture)
    symbols=verify_sources(a,p)
    require(q['resident_end'] == q['resident_base']+symbols['_end'][0] and q['table_address'] == q['resident_base']+symbols['spin_table'][0], 'Captured resident ownership differs from paired ELF symbols')
    return c


def cells(*values):
    return ' '.join(f'0x{x >> 32:x} 0x{x & 0xffffffff:x}' for x in values)


def render(c, p, nonce, storage):
    q = c['private_session']; v = q['boot_video']; nodes = []
    for cpu, mpidr, compatible in p['cpus']:
        method = '' if cpu == 4 else f'\n            enable-method = "spin-table";\n            cpu-release-addr = <{cells(q["release_addresses"][str(cpu)])}>;'
        nodes.append(f'        cpu@{mpidr:x} {{ compatible = "{compatible}"; device_type = "cpu"; reg = <{cells(mpidr)}>;{method}\n        }};')
    values = {'NONCE':nonce,'VIDEO_BASE_HEX':f'{v["base"]:x}','VIDEO_REG':cells(v['base'],v['stride']*v['height']),
              'VIDEO_WIDTH':str(v['width']),'VIDEO_HEIGHT':str(v['height']),'VIDEO_STRIDE':str(v['stride']),
              'CPUS':'\n'.join(nodes),'STORAGE':(HERE/'ans-v1.dts.in').read_text() if storage else ''}
    text = (HERE/'minimal-v1.dts.in').read_text()
    for key, value in values.items():
        require(text.count('@'+key+'@') == 1, 'Template substitution count differs')
        text = text.replace('@'+key+'@', value)
    require(not re.search('@[A-Z_]+@', text), 'Unexpanded template field')
    if c.get('synthetic_fixture') is True:
        text=text.replace('Apple J614s RAM diagnostic UNRELOCATED TEMPLATE','SYNTHETIC ONLY Apple J614s UNRELOCATED TEMPLATE')
    return text


def get(dtb, node, prop, kind='x'):
    return run('fdtget','-t',kind,dtb,node,prop).decode().strip()


def nums(dtb, node, prop):
    return [int(x,16) for x in get(dtb,node,prop).split()]


def verify_dtb(dtb, c, p, nonce, storage, diagnostic_dir=None):
    # Semantic checks below are useful diagnostics, not an exhaustive generic DT
    # validator. Exact fresh compilation closes arbitrary extra-property gaps.
    require(p == profile() and type(storage) is bool and re.fullmatch('[0-9a-f]{32}',nonce),'DT verification profile/nonce differs')
    with tempfile.TemporaryDirectory(prefix='dt-exact-reference-') as temp:
        root=Path(temp);src=root/'reference.dts';binary=root/'reference.dtb'
        src.write_text(render(c,p,nonce,storage))
        compiled=subprocess.run(['dtc','-I','dts','-O','dtb','-o',str(binary),str(src)],capture_output=True)
        if compiled.returncode != 0 or compiled.stderr:
            if diagnostic_dir is not None:
                (diagnostic_dir/'reference-dtc.stderr').write_bytes(compiled.stderr)
                (diagnostic_dir/'reference-dtc.stdout').write_bytes(compiled.stdout)
            raise CompilerDiagnostics(compiled)
        require(dtb.read_bytes() == binary.read_bytes(),'Supplied DTB differs from exact fresh template compilation')
    q = c['private_session']; v = q['boot_video']; fb = '/chosen/framebuffer@'+format(v['base'],'x')
    expected = {'/','/chosen',fb,'/cpus','/memory@0','/reserved-memory','/reserved-memory/retention-control@3fe00000','/reserved-memory/ramoops@3ff00000','/interrupt-controller@502400000','/phy@38aa90000','/iommu@38af00000','/iommu@38af80000','/usb@38a280000','/watchdog-clock','/watchdog@50836c000','/timer'}
    expected.update('/cpus/cpu@'+format(m,'x') for _,m,_ in p['cpus'])
    if storage:expected.update(['/mailbox@409608000','/iommu@40dc50000','/nvme@44dcc0000'])
    actual = set()
    def walk(node):
        actual.add(node)
        for name in run('fdtget','-l',dtb,node).decode().split():walk(node.rstrip('/')+'/'+name)
    walk('/')
    require(actual == expected, 'DT node allowlist differs')
    require(get(dtb,'/','compatible','s').split() == ['apple,j614s','apple,t6040','apple,arm-platform'], 'Root compatibles differ')
    bootargs = f'console=tty0 loglevel=7 nokaslr rdinit=/init panic=0 j614s_test_nonce={nonce}'
    require(get(dtb,'/chosen','bootargs','s') == bootargs and not any(x in bootargs for x in ['earlycon','keep_bootcon','maxcpus','nr_cpus','idle=','cpuidle','nohlt']), 'Boot workaround/early console differs')
    require(nums(dtb,'/memory@0','reg') == [0,0,1,0] and nums(dtb,'/chosen','linux,initrd-start') == nums(dtb,'/chosen','linux,initrd-end') == [0,0], 'Unrelocated patch widths/placeholders differ')
    require(get(dtb,'/memory@0','device_type','s') == 'memory','Loader memory-node discovery differs')
    require(nums(dtb,'/reserved-memory/ramoops@3ff00000','record-size') == [0x20000] and nums(dtb,'/reserved-memory/ramoops@3ff00000','console-size') == [0x80000] and nums(dtb,'/reserved-memory/ramoops@3ff00000','pmsg-size') == [0] and nums(dtb,'/reserved-memory/ramoops@3ff00000','ftrace-size') == [0],'Ramoops layout differs')
    require(set(run('fdtget','-p',dtb,'/reserved-memory/retention-control@3fe00000').decode().split()) == {'reg','no-map'} and set(run('fdtget','-p',dtb,'/reserved-memory/ramoops@3ff00000').decode().split()) == {'compatible','reg','record-size','console-size','pmsg-size','ftrace-size'},'Loader reservation property allowlist differs')
    regs = {'/reserved-memory/retention-control@3fe00000':[0,0x3fe00000,0,0x4000],'/reserved-memory/ramoops@3ff00000':[0,0x3ff00000,0,0x100000],'/interrupt-controller@502400000':[5,0x02400000,0,0x1cc000,5,0x02440000,0,4],'/phy@38aa90000':[3,0x8aa90000,0,0x4000,3,0x8aa84000,0,0x4000],'/iommu@38af00000':[3,0x8af00000,0,0xc000],'/iommu@38af80000':[3,0x8af80000,0,0xc000],'/usb@38a280000':[3,0x8a280000,0,0x11800],'/watchdog@50836c000':[5,0x0836c000,0,0x4000],fb:[v['base']>>32,v['base']&0xffffffff,0,v['stride']*v['height']]}
    if storage:regs.update({'/mailbox@409608000':[4,0x09608000,0,0x4000],'/iommu@40dc50000':[4,0x0dc50000,0,0xc000],'/nvme@44dcc0000':[4,0x4dcc0000,0,0x30000,4,0x09600000,0,0x4000]})
    for node, value in regs.items():require(nums(dtb,node,'reg') == value, 'Resource extent differs: '+node.split('@')[0])
    compatibles = {fb:['simple-framebuffer'],'/interrupt-controller@502400000':['apple,t6040-aic3','apple,t8122-aic3'],'/phy@38aa90000':['apple,t6040-usb2-inherited'],'/iommu@38af00000':['apple,t8110-dart'],'/iommu@38af80000':['apple,t8110-dart'],'/watchdog-clock':['fixed-clock'],'/watchdog@50836c000':['apple,wdt'],'/timer':['arm,armv8-timer'],'/usb@38a280000':['snps,dwc3'],'/reserved-memory/ramoops@3ff00000':['ramoops']}
    if storage:compatibles.update({'/mailbox@409608000':['apple,asc-mailbox-v4'],'/iommu@40dc50000':['apple,t6000-sart'],'/nvme@44dcc0000':['apple,j614s-nvme-diagnostic']})
    for node,value in compatibles.items():require(get(dtb,node,'compatible','s').split() == value,'Compatible differs: '+node.split('@')[0])
    expected_model='SYNTHETIC ONLY Apple J614s UNRELOCATED TEMPLATE' if c.get('synthetic_fixture') is True else 'Apple J614s RAM diagnostic UNRELOCATED TEMPLATE'
    require(get(dtb,'/','model','s') == expected_model,'Synthetic/unrelocated model label differs')
    require(get(dtb,fb,'format','s') == 'x2r10g10b10' and nums(dtb,fb,'width') == [v['width']] and nums(dtb,fb,'height') == [v['height']] and nums(dtb,fb,'stride') == [v['stride']],'Framebuffer mode differs')
    vectors={'/usb@38a280000':[0,1651,4],'/iommu@38af00000':[0,1655,4],'/iommu@38af80000':[0,1655,4],'/timer':[1,2,4,1,3,4,1,0,4,1,1,4]}
    if storage:vectors.update({'/mailbox@409608000':[0,1530,4,0,1531,4,0,1532,4,0,1533,4],'/nvme@44dcc0000':[0,2583,4]})
    for node,value in vectors.items():require(nums(dtb,node,'interrupts') == value and nums(dtb,node,'interrupt-parent') == nums(dtb,'/interrupt-controller@502400000','phandle'),'Interrupt vector/provider differs')
    require(get(dtb,'/interrupt-controller@502400000','reg-names','s').split() == ['core','event'] and nums(dtb,'/interrupt-controller@502400000','#interrupt-cells') == [3],'AIC resource schema differs')
    require(get(dtb,'/phy@38aa90000','reg-names','s').split() == ['usb2phy','pipehandler'] and nums(dtb,'/watchdog-clock','clock-frequency') == [24000000],'PHY/clock profile differs')
    for node in ['/iommu@38af00000','/iommu@38af80000']:require(nums(dtb,node,'apple,dma-range') == [0,0,1,0] and nums(dtb,node,'#iommu-cells') == [1],'DART DMA extent/schema differs')
    if storage:require(get(dtb,'/nvme@44dcc0000','reg-names','s').split() == ['nvme','ans'] and nums(dtb,'/mailbox@409608000','#mbox-cells') == [0] and get(dtb,'/mailbox@409608000','interrupt-names','s').split() == ['send-empty','send-not-empty','recv-empty','recv-not-empty'],'ANS/mailbox schema differs')
    for cpu, mpidr, compatible in p['cpus']:
        node='/cpus/cpu@'+format(mpidr,'x');require(nums(dtb,node,'reg') == [0,mpidr] and get(dtb,node,'compatible','s') == compatible and get(dtb,node,'device_type','s') == 'cpu','CPU identity differs')
        if cpu != 4:require(get(dtb,node,'enable-method','s') == 'spin-table' and nums(dtb,node,'cpu-release-addr') == [q['release_addresses'][str(cpu)]>>32,q['release_addresses'][str(cpu)]&0xffffffff], 'Spin release differs')
    # The source profile hashes cover the remaining fixed property text. Independently
    # verify all cross-device phandle edges, resources, and forbidden power controls.
    for node in actual:
        props=set(run('fdtget','-p',dtb,node).decode().split())
        require(not props & {'power-domains','resets','firmware-name','firmware','memory-region','iommu-addresses'}, 'Unexpected firmware/power/ownership control')
    ph=lambda n:nums(dtb,n,'phandle')[0]
    require(nums(dtb,'/usb@38a280000','phys') == [ph('/phy@38aa90000')] and nums(dtb,'/usb@38a280000','iommus') == [ph('/iommu@38af00000'),0,ph('/iommu@38af80000'),1] and get(dtb,'/usb@38a280000','dr_mode','s') == 'peripheral','USB inherited path differs')
    require(nums(dtb,'/watchdog@50836c000','clocks') == [ph('/watchdog-clock')] and nums(dtb,'/watchdog@50836c000','timeout-sec') == [60], 'Watchdog profile differs')
    if storage:require(nums(dtb,'/nvme@44dcc0000','mboxes') == [ph('/mailbox@409608000')] and nums(dtb,'/nvme@44dcc0000','apple,sart') == [ph('/iommu@40dc50000')], 'ANS provider edges differ')
    return len(actual)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('capture','observer-source','resident-source','loader-source','loader-binary','kernel-source','kernel-bundle','output'):
        ap.add_argument('--'+name,required=True,type=Path)
    for name in ('expected-usb-session','expected-capture-sha256','expected-observer-sha256','expected-bootargs-sha256','expected-adt-sha256','nonce'):
        ap.add_argument('--'+name,required=True)
    ap.add_argument('--storage-diagnostic',action='store_true')
    ap.add_argument('--synthetic-fixture',action='store_true')
    a=ap.parse_args();os.umask(0o077)
    try:
        p=profile();require(not a.output.exists(),'Refusing existing output directory')
        require(re.fullmatch('[0-9a-f]{32}',a.nonce),'Invalid diagnostic nonce')
        c=verify_inputs(a,p)
        text=render(c,p,a.nonce,a.storage_diagnostic)
        require(sha(a.capture) == a.expected_capture_sha256, 'Capture changed before output')
        a.output.mkdir(mode=0o700,parents=True)
        dts=a.output/'UNRELOCATED-template.dts';dtb=a.output/'UNRELOCATED-template.dtb';dts.write_text(text)
        proc=subprocess.run(['dtc','-I','dts','-O','dtb','-o',str(dtb),str(dts)],capture_output=True)
        (a.output/'dtc.stderr').write_bytes(proc.stderr);(a.output/'dtc.stdout').write_bytes(proc.stdout)
        if proc.returncode != 0 or proc.stderr:
            (a.output/'compiler-failure.json').write_text(json.dumps({'status':'REFUSED_COMPILER_DIAGNOSTICS','exit_code':proc.returncode,'stderr_bytes':len(proc.stderr),'warnings_disabled':False,'runtime_fdt':False})+'\n')
            raise ValueError('DTC compile failure/warnings retained; no qualified template')
        header=dtb.read_bytes()
        require(40 <= len(header) <= 0x10000 and struct.unpack('>II',header[:8]) == (0xd00dfeed,len(header)), 'FDT header/total extent violates exact loader input contract')
        count=verify_dtb(dtb,c,p,a.nonce,a.storage_diagnostic,diagnostic_dir=a.output)
        require(sha(a.capture) == a.expected_capture_sha256, 'Capture changed during compilation')
        require(profile() == p, 'Source profile changed during compilation')
        verify_sources(a,p)
        report={'status':'UNRELOCATED_TEMPLATE_ONLY','synthetic_fixture':a.synthetic_fixture,'hardware':'UNTESTED','runtime_fdt':False,'deployment_authorized':False,'profile_sha256':PROFILE_SHA,'generator_sha256':sha(Path(__file__)),'dtb_bytes':len(header),'host_tools':{n:{'sha256':sha(Path(shutil.which(n))),'version':run(n,'--version').decode().strip()} for n in ('dtc','fdtget')},'capture_sha256':sha(a.capture),'observer_sha256':p['observer_sha256'],'bootargs_sha256':a.expected_bootargs_sha256,'adt_sha256':a.expected_adt_sha256,'usb_session':a.expected_usb_session,'loader_commit':p['loader_commit'],'kernel_commit':p['kernel_commit'],'dtb_sha256':sha(dtb),'nodes_checked':count,'storage_diagnostic':a.storage_diagnostic,'dtc_stderr_bytes':len(proc.stderr),'warnings_disabled':False,'scope':'Private session-derived template. Loader still relocates memory/initrd/reservations; freshness, live ownership and recovery require primary recheck.'}
        (a.output/'template-result.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        print('UNRELOCATED template validated; hardware UNTESTED; no deployment authority')
    except (ValueError,KeyError,TypeError,subprocess.CalledProcessError,OSError) as error:
        # Do not print exception details containing private addresses/paths/tool output.
        if isinstance(error,ValueError):print('REFUSED: '+str(error))
        else:print('REFUSED: malformed/unverifiable input or host-tool failure')
        raise SystemExit(1)


if __name__=='__main__':main()
