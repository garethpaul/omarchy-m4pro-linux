#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture bounded resident RAM metadata only; never allocate, stage or execute."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types

BINARY_SHA='fb31c765c54b2c8108ac7598c8307f663b91fb25ef9cbeb88e75bafffc0f3afb'
ELF_SHA='4a32c15fbda69acc47175f1e6b514cfb7d5920916df7630dec216c29177fc28f'
CPU_READER_SHA='fce3a31052563734305b5c475bce7d247cf0c716fb0d0f177b81acf1da3c55d7'
MEMORY_HELPER_SHA='42860b7b024cb14dfcfd0c81dcaa460cba79f0f121f03a750ee14da76f464a8a'

def require(value,message):
    if not value:raise ValueError(message)

def sha(data):return hashlib.sha256(data).hexdigest()

def checked_helper(name,digest):
    path=Path(__file__).with_name(name);data=path.read_bytes()
    require(len(data)<65536 and sha(data)==digest,'Helper source differs')
    module=types.ModuleType('checked_'+path.stem);module.__file__=str(path)
    exec(compile(data,str(path),'exec',dont_inherit=True,optimize=0),module.__dict__)
    return module

def primary_device():
    matches=[]
    for tty in Path('/sys/class/tty').glob('ttyACM*'):
        interface=(tty/'device').resolve(strict=True)
        while interface!=interface.parent and not (interface/'bInterfaceNumber').exists():interface=interface.parent
        if not (interface/'bInterfaceNumber').exists() or (interface/'bInterfaceNumber').read_text().strip()!='00':continue
        usb=interface
        while usb!=usb.parent and not (usb/'idVendor').exists():usb=usb.parent
        expected={'idVendor':'1209','idProduct':'316d','product':'m1n1 uartproxy 8e0cf28'}
        if all((usb/k).exists() and (usb/k).read_text().strip()==v for k,v in expected.items()):matches.append((Path('/dev')/tty.name,usb))
    require(len(matches)==1,'Exactly one pinned primary proxy required')
    return matches[0]

def sections_from_tree(root):
    wanted={'/chosen/memory-map','/chosen/carveout-memory-map'};found={}
    def walk(node,parent=''):
        names=[x.value for x in node.properties if x.name=='name']
        require(len(names)==1,'ADT node name ambiguous')
        name=names[0].rstrip(b'\0').decode('ascii');path=(parent+'/'+name).removeprefix('/device-tree') or '/'
        if path in wanted:
            require(path not in found,'ADT source node ambiguous')
            found[path]=[(x.name,x.value) for x in node.properties]
        for child in node.children:walk(child,path.rstrip('/'))
    walk(root)
    require(set(found)==wanted,'Required ADT memory sections absent')
    return found

def resident_symbols(lines):
    wanted={'_end','heap_base','heap_limit','boot_cpu_idx','boot_cpu_mpidr','ram_base','mem_size_actual','wfe_mode','spin_table','boot_args_addr','cur_boot_args'}
    symbols={};sizes={}
    for line in lines:
        words=line.split()
        if len(words)==4 and words[3] in wanted:
            require(words[3] not in symbols,'Duplicate required ELF symbol')
            symbols[words[3]]=int(words[0],16);sizes[words[3]]=int(words[1],16)
    require(set(symbols)==wanted,'Missing required ELF symbol')
    return symbols,sizes

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--m1n1-source',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True,help='New private directory only')
    for name in ('expected-usb-session','expected-adt-sha256','expected-bootargs-sha256'):ap.add_argument('--'+name,required=True)
    a=ap.parse_args();require(__debug__,'Optimized Python prohibited');os.umask(0o077)
    require(not a.output.exists(),'Refusing existing output')
    cpu_reader=checked_helper('read_resident_cpus.py',CPU_READER_SHA)
    memory_helper=checked_helper('staging_memory.py',MEMORY_HELPER_SHA)
    source=a.m1n1_source.resolve();elf=source/'build/m1n1-raw.elf';binary=source/'build/m1n1.bin'
    require(sha(elf.read_bytes())==ELF_SHA and sha(binary.read_bytes())==BINARY_SHA,'Resident ELF/binary pin differs')
    with tempfile.TemporaryDirectory(prefix='staging-observer-pair-') as temp:
        flat=Path(temp)/'paired.bin'
        subprocess.run(['llvm-objcopy','-O','binary','--strip-debug',str(elf),str(flat)],check=True,capture_output=True)
        require(sha(flat.read_bytes())==BINARY_SHA,'Resident ELF flattening differs')
    symbols,sizes=resident_symbols(subprocess.check_output(['llvm-nm','-S',str(elf)],text=True).splitlines())
    end_offset=symbols['_end']
    widths={'heap_base':8,'heap_limit':8,'boot_cpu_idx':4,'boot_cpu_mpidr':8,'ram_base':8,'mem_size_actual':8,'wfe_mode':1,'spin_table':14*64,'boot_args_addr':8}
    for name,width in widths.items():require(sizes[name]>=width and 0<=symbols[name]<symbols[name]+width<=end_offset,'Metadata symbol outside paired image')
    sys.path.insert(0,str(source/'proxyclient'))
    from m1n1.proxy import UartInterface,M1N1Proxy
    from m1n1.tgtypes import BootArgs_r3
    from m1n1.adt import load_adt,ADTNodeStruct
    widths['cur_boot_args']=BootArgs_r3.sizeof()
    require(sizes['cur_boot_args']>=widths['cur_boot_args'] and 0<=symbols['cur_boot_args']<symbols['cur_boot_args']+widths['cur_boot_args']<=end_offset,'Resident bootargs outside paired image')
    port,usb=primary_device();enumeration=(usb/'devnum').read_text().strip()
    require(enumeration==a.expected_usb_session,'USB session differs')
    interface=UartInterface(str(port))
    try:
        interface.tty_enable=False;interface.nop();proxy=M1N1Proxy(interface)
        require(proxy.get_chipid()==0x6040 and proxy.get_exc_count()==0,'Wrong chip/exception state')
        base=proxy.get_base();require(type(base) is int and 0<base<base+end_offset<1<<64,'Invalid resident extent')
        # Establish the RAM envelope from the bounded resident copy first. Never
        # dereference the external bootargs pointer before its extent is known.
        resident_boot_bytes=interface.readmem(base+symbols['cur_boot_args'],widths['cur_boot_args'])
        require(sha(resident_boot_bytes)==a.expected_bootargs_sha256,'Resident bootargs bytes differ')
        require(struct.unpack_from('<H',resident_boot_bytes)[0]==3,'Wrong bootargs revision')
        resident_boot=BootArgs_r3.parse(resident_boot_bytes)
        # get_bootargs_rev() performs hidden physical read8 operations. Use the
        # address-only metadata query, then bound its span before readmem.
        address=proxy.get_bootargs()
        require(resident_boot.phys_base<=address<address+BootArgs_r3.sizeof()<=resident_boot.phys_base+resident_boot.mem_size<1<<64,'External bootargs outside RAM')
        boot_bytes=interface.readmem(address,BootArgs_r3.sizeof());require(boot_bytes==resident_boot_bytes,'External/resident bootargs differ')
        boot=BootArgs_r3.parse(boot_bytes);ram_end=boot.phys_base+boot.mem_size
        require(boot.phys_base<ram_end<1<<64,'Invalid usable RAM')
        require(boot.phys_base<=base<base+end_offset<=ram_end,'Resident outside RAM')
        for field,width in widths.items():require(base<=base+symbols[field]<base+symbols[field]+width<=base+end_offset,'Invalid bounded RAM read')
        first={k:interface.readmem(base+symbols[k],v) for k,v in widths.items()}
        scalar=lambda k:struct.unpack('<I' if widths[k]==4 else '<Q',first[k])[0]
        require(scalar('boot_args_addr')==address and first['cur_boot_args']==resident_boot_bytes,'Resident bootargs metadata differs')
        require(scalar('boot_cpu_idx')==4 and scalar('boot_cpu_mpidr')==0x80010100,'Boot CPU differs')
        physical_base,physical_size=scalar('ram_base'),scalar('mem_size_actual')
        require(physical_base==boot.phys_base&~((1<<32)-1) and physical_size==boot.mem_size_actual,'Physical metadata differs')
        geometry=cpu_reader.memory_geometry(physical_base,physical_size,int(boot.phys_base),int(boot.mem_size))
        adt_address=boot.devtree-boot.virt_base+boot.phys_base
        require(0<boot.devtree_size<=1<<20 and boot.phys_base<=adt_address<adt_address+boot.devtree_size<=ram_end,'ADT outside usable RAM')
        adt_bytes=interface.readmem(adt_address,boot.devtree_size);require(sha(adt_bytes)==a.expected_adt_sha256,'ADT bytes differ')
        adt=load_adt(adt_bytes)
        require(adt.model=='Mac16,8' and adt['/chosen'].board_id==4 and adt['/chosen'].system_firmware_version=='mBoot-18000.161.10','ADT board/firmware differs')
        expected={n.cpu_id:n.reg|(0x10000 if n.cluster_id else 0) for n in adt['/cpus']}
        sections=sections_from_tree(ADTNodeStruct.parse(adt_bytes));ranges=memory_helper.decode_ranges(sections)
        require(interface.readmem(adt_address,boot.devtree_size)==adt_bytes and interface.readmem(address,len(boot_bytes))==boot_bytes,'Bootargs/ADT changed during observation')
        second={k:interface.readmem(base+symbols[k],v) for k,v in widths.items()}
        require(first==second,'Resident/allocator metadata changed during observation')
        state=cpu_reader.decode_slots(first['spin_table'],second['spin_table'],expected)
        require(first['wfe_mode'] in (b'\0',b'\1'),'Invalid resident WFE flag')
        memory={'usable_base':geometry['ram_base'],'usable_size':geometry['ram_size'],'physical_base':geometry['physical_ram_base'],'physical_size':geometry['physical_ram_size'],
                'resident_base':base,'resident_end':base+end_offset,'heap_base':scalar('heap_base'),'heap_limit':scalar('heap_limit'),'bootargs_top':int(boot.top_of_kernel_data),
                'boot_video':{n:int(boot.video[n]) for n in ('base','display','stride','width','height','depth')}}
        metadata=[dict(name='live-bootargs',base=int(address),size=len(boot_bytes)),dict(name='live-adt',base=int(adt_address),size=len(adt_bytes))]
        memory_helper.validate_heap(memory,metadata)
        require(proxy.get_bootargs()==address and proxy.get_base()==base and proxy.get_exc_count()==0 and (usb/'devnum').read_text().strip()==enumeration,'Proxy identity/state changed')
        result={'schema':1,'kind':'readonly-j614s-staging-geometry','synthetic_fixture':False,'captured_utc':datetime.now(timezone.utc).isoformat(),
                'session':{'usb_enumeration':enumeration,'observer_sha256':sha(Path(__file__).read_bytes()),'resident_binary_sha256':BINARY_SHA,'resident_elf_sha256':ELF_SHA,'bootargs_sha256':sha(boot_bytes),'adt_sha256':sha(adt_bytes)},
                'memory':memory,'ranges':ranges,'protected_metadata':metadata,'bootargs_bytes':len(boot_bytes),
                'cpu_state':{'secondary_flags_set':state['secondary_flags_set'],'secondary_slots_idle':bool(state['secondary_slots_idle']),'resident_wfe_mode':bool(first['wfe_mode'][0])},
                'helper_sources':{'cpu_observer_sha256':CPU_READER_SHA,'staging_memory_sha256':MEMORY_HELPER_SHA},
                'target_memory_written':False,'code_executed_via_call':False,'allocator_called':False,'cores_started':False,'watchdog_action':'unchanged','exceptions':0,'deployment_authorized':False,'recovery_verified':False}
        a.output.mkdir(mode=0o700)
        for name,data in [('capture.json',(json.dumps(result,indent=2)+'\n').encode()),('adt.bin',adt_bytes),('bootargs.bin',boot_bytes)]:
            with open(a.output/name,'xb') as stream:stream.write(data)
        print(json.dumps({'status':'READONLY_METADATA_OBSERVED','captured_utc':result['captured_utc'],'usb_session':enumeration,'range_count':len(ranges),'cpu_state':result['cpu_state'],'heap_and_adt_stable':True,'target_memory_written':False,'allocator_called':False,'hardware_handoff':'UNTESTED','deployment_authorized':False},indent=2))
    finally:interface.dev.close()

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('READONLY_CAPTURE_REFUSED ('+type(error).__name__+')',file=sys.stderr)
        raise SystemExit(1)
