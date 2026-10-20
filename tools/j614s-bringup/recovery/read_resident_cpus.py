#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Observe qualified resident CPU slots using RAM reads only; never start cores."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

BINARY_SHA = 'fb31c765c54b2c8108ac7598c8307f663b91fb25ef9cbeb88e75bafffc0f3afb'
CPU_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13)
SLOT_BYTES = 64

def require(value, message):
    if not value:
        raise ValueError(message)

def decode_slots(first, second, expected):
    require(tuple(sorted(expected)) == CPU_IDS, 'CPU identity set differs')
    require(len(first) == len(second) == 14*SLOT_BYTES, 'Invalid slot snapshot size')
    require(first == second, 'Resident slots changed during capture')
    rows=[]
    for cpu in CPU_IDS:
        mpidr, flag, target, *values = struct.unpack_from('<8Q', first, cpu*SLOT_BYTES)
        require(not flag or mpidr == expected[cpu], 'Active resident MPIDR differs from live ADT')
        if cpu == 4:
            require(mpidr == expected[cpu], 'Boot MPIDR differs from live ADT')
        rows.append({'cpu_id':cpu, 'expected_mpidr':expected[cpu],
                     'observed_mpidr':mpidr, 'resident_flag':flag,
                     'target_zero':target == 0, 'arguments_zero':not any(values[:4])})
    secondary=[r for r in rows if r['cpu_id'] != 4]
    return {'cpus':rows, 'secondary_flags_set':sum(bool(r['resident_flag'])for r in secondary),
            'secondary_slots_idle':all(r['resident_flag'] and r['target_zero'] and r['arguments_zero']for r in secondary),
            'scope':'Resident software slots only; not a Linux online-core, physical liveness, atomic coherency or recovery test'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--m1n1-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='new private evidence file')
    args=parser.parse_args()
    if not __debug__:parser.error('optimized Python is prohibited')
    if args.output.exists():parser.error('refusing to overwrite evidence')
    os.umask(0o077)
    source=args.m1n1_source.resolve(); binary=source/'build/m1n1.bin';elf=source/'build/m1n1-raw.elf'
    sha=lambda data:hashlib.sha256(data).hexdigest()
    require(sha(binary.read_bytes()) == BINARY_SHA,'Local resident binary differs')
    with tempfile.TemporaryDirectory(prefix='resident-pair-')as temp:
        flat=Path(temp)/'paired.bin'
        subprocess.run(['llvm-objcopy','-O','binary','--strip-debug',str(elf),str(flat)],check=True,capture_output=True)
        require(sha(flat.read_bytes()) == BINARY_SHA,'Local ELF/binary pair differs')
    symbols={}
    for line in subprocess.check_output(['llvm-nm','-n',str(elf)],text=True).splitlines():
        words=line.split()
        if len(words)==3:symbols[words[2]]=int(words[0],16)
    sizes={}
    for line in subprocess.check_output(['llvm-nm','-S',str(elf)],text=True).splitlines():
        words=line.split()
        if len(words)==4:sizes[words[3]]=int(words[1],16)
    require(sizes['spin_table']>=14*SLOT_BYTES,'Qualified table extent too small')
    require(0<=symbols['spin_table']<symbols['spin_table']+14*SLOT_BYTES<=symbols['_end'],'Table outside local image')
    for name in ('boot_cpu_idx','boot_cpu_mpidr','wfe_mode'):
        require(0<=symbols[name]<symbols['_end']-8,'Metadata symbol outside image')
    sys.path.insert(0,str(source/'proxyclient'))
    from m1n1.proxy import UartInterface, M1N1Proxy
    from m1n1.tgtypes import BootArgs_r3
    from m1n1.adt import load_adt
    from read_pmu_counter import primary_device
    port=primary_device();usb=(Path('/sys/class/tty')/port.name/'device').resolve()
    while not (usb/'idVendor').exists() and usb != usb.parent:usb=usb.parent
    enumeration=(usb/'devnum').read_text().strip()
    interface=UartInterface(str(port))
    try:
        interface.tty_enable=False;interface.nop();proxy=M1N1Proxy(interface)
        require(proxy.get_chipid()==0x6040 and proxy.get_exc_count()==0,'Wrong chip/exception state')
        address,revision=proxy.get_bootargs_rev();require(revision==3,'Unsupported boot arguments')
        boot=BootArgs_r3.parse(interface.readmem(address,BootArgs_r3.sizeof()))
        ram_end=boot.phys_base+boot.mem_size
        require(boot.phys_base<ram_end<1<<64,'Invalid RAM envelope')
        base=proxy.get_base();require(boot.phys_base<=base<base+symbols['_end']<=ram_end,'Resident outside RAM')
        adt_address=boot.devtree-boot.virt_base+boot.phys_base
        require(0<boot.devtree_size<=1024*1024 and boot.phys_base<=adt_address<adt_address+boot.devtree_size<=ram_end,'Invalid live ADT extent')
        adt_bytes=interface.readmem(adt_address,boot.devtree_size)
        require(interface.readmem(adt_address,boot.devtree_size)==adt_bytes,'Live ADT changed')
        adt=load_adt(adt_bytes)
        require(adt.model=='Mac16,8' and adt['/chosen'].board_id==4,'Wrong model/board')
        require(adt['/chosen'].system_firmware_version=='mBoot-18000.161.10','Unqualified firmware')
        expected={node.cpu_id:node.reg | (0x10000 if node.cluster_id else 0)for node in adt['/cpus']}
        cpu=struct.unpack('<I',interface.readmem(base+symbols['boot_cpu_idx'],4))[0]
        mpidr=struct.unpack('<Q',interface.readmem(base+symbols['boot_cpu_mpidr'],8))[0]
        require(cpu==4 and mpidr==0x80010100,'Unexpected boot CPU')
        table_address=base+symbols['spin_table']
        first=interface.readmem(table_address,14*SLOT_BYTES)
        second=interface.readmem(table_address,14*SLOT_BYTES)
        result=decode_slots(first,second,expected)
        wfe=interface.readmem(base+symbols['wfe_mode'],1)
        require(wfe in (b'\0',b'\1'),'Invalid resident WFE flag')
        require(proxy.get_exc_count()==0 and (usb/'devnum').read_text().strip()==enumeration,'Proxy session changed')
        result.update(status='WORKS (read-only resident observation)',captured_utc=datetime.now(timezone.utc).isoformat(),
                      binary_sha256=BINARY_SHA,adt_sha256=sha(adt_bytes),slot_snapshot_sha256=sha(first),
                      usb_enumeration=enumeration,boot_cpu=cpu,boot_mpidr=mpidr,resident_wfe_mode=bool(wfe[0]),
                      target_memory_written=False,code_executed_via_call=False,watchdog_action='unchanged',
                      cores_started=False,recovery_verified=False,exceptions=0)
        # ASLR-dependent addresses stay only in private evidence, not stdout.
        result['private_session']={'resident_base':base,'table_address':table_address,
                                  'release_addresses':{str(i):table_address+i*SLOT_BYTES+16 for i in CPU_IDS}}
        with open(args.output,'x',opener=lambda path,flags:os.open(path,flags,0o600))as output:
            output.write(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items()if k!='private_session'},indent=2))
    finally:interface.dev.close()

if __name__=='__main__':main()
