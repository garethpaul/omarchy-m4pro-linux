#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Supervised resident secondary startup; no allocator, payload, disk or watchdog."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from datetime import datetime, timezone

RESIDENT = 'fb31c765c54b2c8108ac7598c8307f663b91fb25ef9cbeb88e75bafffc0f3afb'
ELF = '4a32c15fbda69acc47175f1e6b514cfb7d5920916df7630dec216c29177fc28f'
OBSERVER = 'fce3a31052563734305b5c475bce7d247cf0c716fb0d0f177b81acf1da3c55d7'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--m1n1-source', type=Path, required=True)
    ap.add_argument('--capture', type=Path, required=True)
    ap.add_argument('--expected-capture-sha256', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--operator-present', action='store_true')
    a = ap.parse_args()
    require(__debug__ and a.operator_present, 'Explicit supervised invocation required')
    require(not a.output.exists(), 'Preserve prior outputs')
    raw = a.capture.read_bytes()
    require(sha(raw) == a.expected_capture_sha256, 'Capture bytes differ')
    capture = json.loads(raw)
    require(capture['observer_sha256'] == OBSERVER and capture['binary_sha256'] == RESIDENT,
            'Frozen observer/resident identity differs')
    require(capture['exceptions'] == 0 and capture['boot_cpu'] == 4 and capture['boot_mpidr'] == 0x80010100,
            'CPU/exception state differs')
    require(capture['secondary_flags_set'] == 0 and not capture['resident_wfe_mode'],
            'Require fresh unstarted secondary state')
    source = a.m1n1_source.resolve()
    require(sha((source/'build/m1n1.bin').read_bytes()) == RESIDENT and sha((source/'build/m1n1-raw.elf').read_bytes()) == ELF,
            'Paired resident files differ')
    symbols = {}
    for line in subprocess.check_output(['llvm-nm', '-S', str(source/'build/m1n1-raw.elf')], text=True).splitlines():
        w = line.split()
        if len(w) == 4 and w[3] in ('spin_table', 'wfe_mode'):
            require(w[3] not in symbols, 'Duplicate required symbol')
            symbols[w[3]] = int(w[0], 16)
    require(set(symbols) == {'spin_table', 'wfe_mode'}, 'Required symbols absent')
    q = capture['private_session']; base = q['resident_base']; table = q['table_address']
    require(table == base+symbols['spin_table'] and base <= table < table+14*64 <= q['resident_end'], 'Table outside resident')
    sys.path.insert(0, str(source/'proxyclient'))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from m1n1.proxy import UartInterface, M1N1Proxy
    from read_pmu_counter import primary_device
    port = primary_device(); usb = (Path('/sys/class/tty')/port.name/'device').resolve()
    while not (usb/'idVendor').exists() and usb != usb.parent:
        usb = usb.parent
    require((usb/'devnum').read_text().strip() == capture['usb_enumeration'], 'USB session changed')
    os.umask(0o077); a.output.mkdir(mode=0o700)
    result = {'status':'START_NOT_ATTEMPTED', 'operator_present':True, 'cores_started':False,
              'allocator_called':False, 'payload_executed':False, 'watchdog_action':'unchanged',
              'protected_writes':False, 'capture_sha256':sha(raw), 'usb_enumeration':capture['usb_enumeration']}
    def save():
        (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    interface = UartInterface(str(port))
    with (a.output/'console.txt').open('x') as console, contextlib.redirect_stdout(console):
        try:
            interface.tty_log = console; interface.tty_enable = False
            # Explicitly negotiate zero optional flags so both endpoints use
            # actual transfer checksums, including after another client used
            # the resident's optional sentinel mode.
            interface.cmd(interface.REQ_NOP, struct.pack('<Q', 0))
            require(struct.unpack('<QQQ', interface.reply(interface.REQ_NOP))[0] == 0,
                    'Transfer checksum negotiation differs')
            interface.enabled_features = type(interface.enabled_features)(0)
            proxy = M1N1Proxy(interface); proxy.nop()
            require(proxy.get_chipid() == 0x6040 and proxy.get_base() == base and proxy.get_exc_count() == 0, 'Live identity differs')
            first = interface.readmem(table, 14*64)
            require(sha(first) == capture['slot_snapshot_sha256'], 'Live slots changed')
            require(interface.readmem(base+symbols['wfe_mode'], 1) == b'\0', 'WFE changed')
            # Existing resident API; no uploaded code and no heap allocation.
            result['status'] = 'STARTING_SECONDARIES'; save()
            proxy.smp_set_wfe_mode(True)
            proxy.smp_start_secondaries()
            result['cores_started'] = True
            first = interface.readmem(table, 14*64)
            require(interface.readmem(table, 14*64) == first, 'Secondary slots unstable')
            for row in capture['cpus']:
                cpu = row['cpu_id']; mpidr, flag, target, *args = struct.unpack_from('<8Q', first, cpu*64)
                require(mpidr == row['expected_mpidr'], 'Secondary MPIDR differs')
                if cpu != 4:
                    require(flag and target == 0 and not any(args[:4]), 'Secondary slot not idle')
            require(interface.readmem(base+symbols['wfe_mode'], 1) == b'\1', 'WFE not enabled')
            require(proxy.get_exc_count() == 0 and (usb/'devnum').read_text().strip() == capture['usb_enumeration'], 'Live exception/session changed')
            result.update(status='RESIDENT_SECONDARIES_READY', secondary_flags_set=11,
                          secondary_slots_idle=True, resident_wfe_mode=True, exceptions=0,
                          slot_snapshot_sha256=sha(first), utc=datetime.now(timezone.utc).isoformat(),
                          scope='Resident software slot/MPIDR readiness only; Linux SMP not tested here')
            save()
        except Exception as error:
            result.update(status='STARTUP_FAILED', error_type=type(error).__name__); save(); raise
        finally:
            interface.dev.close()
    print('RESIDENT_SECONDARIES_READY: eleven idle slots, zero exceptions; no payload or watchdog action')


if __name__ == '__main__':
    main()
