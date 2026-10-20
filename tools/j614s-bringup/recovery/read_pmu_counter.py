#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read the qualified J614s PMU count without changing it or any watchdog."""
import argparse
import json
import os
from pathlib import Path
import struct
import sys
import time


def profile(nodes):
    u32 = lambda value: struct.unpack('<I', value)[0]
    assert nodes['/']['model'].rstrip(b'\0') == b'Mac16,8'
    assert u32(nodes['/chosen']['board-id']) == 4
    assert nodes['/chosen']['system-firmware-version'].rstrip(b'\0') == b'mBoot-18000.161.10'
    spmi = nodes['/arm-io/nub-spmi0']
    assert u32(spmi['gen']) == 3 and spmi['compatible'].rstrip(b'\0') == b'aapl,spmi'
    reg, size = struct.unpack('<QQ', spmi['reg'][:16])
    assert (reg, size) == (0x309014000, 0x4000)
    translated = [parent+reg-child for child, parent, length in
                  struct.iter_unpack('<QQQ', nodes['/arm-io']['ranges'])
                  if child <= reg and reg+size <= child+length]
    assert translated == [0x509014000]
    primary = [props for path, props in nodes.items()
               if path.startswith('/arm-io/nub-spmi0/') and
               props.get('is-primary') == struct.pack('<I', 1)]
    assert len(primary) == 1
    pmu = primary[0]
    assert b'pmu,spmi' in pmu['compatible'].split(b'\0')
    assert struct.unpack_from('<I', pmu['reg'])[0] == 14
    assert u32(pmu['info-leg_scrpad']) == 0xf800
    return translated[0], 14, 0xf802


def empty(status):
    return bool(status & (1 << 24)) and bool(status & (1 << 8)) and not status & 0xff00ff


def read_counter(proxy, mmio, slave, address):
    before = proxy.read32(mmio)
    assert empty(before), 'SPMI busy: do not consume another owner reply'
    irq_before = proxy.read32(mmio+0x80)
    assert not irq_before & (1 << 27) and proxy.get_exc_count() == 0
    # One transient SPMI read request. Never emit write opcode 0x30 or data.
    proxy.write32(mmio+4, (address << 16) | (1 << 15) | (slave << 8) | 0x38)
    deadline = time.monotonic()+1

    def word():
        while time.monotonic() < deadline:
            if not proxy.read32(mmio) & (1 << 24):
                return proxy.read32(mmio+8)
        raise TimeoutError('SPMI response incomplete; stop without resetting target')

    reply = word()
    assert reply & 0xff == 0x38 and (reply >> 8) & 0x7f == slave
    assert reply >> 16 == 1 and not reply & (1 << 15)
    data = word()
    assert 0 <= data < 256
    after = proxy.read32(mmio)
    irq_after = proxy.read32(mmio+0x80)
    assert empty(after) and not irq_after & (1 << 27) and proxy.get_exc_count() == 0
    return dict(pmu_error_count_byte=data, pmu_register_written=False,
                watchdog_action='unchanged', response_verified=True, exceptions=0,
                status_before=hex(before), status_after=hex(after),
                irq_before=hex(irq_before), irq_after=hex(irq_after))


def primary_device():
    found = []
    for tty in Path('/sys/class/tty').glob('ttyACM*'):
        interface = (tty/'device').resolve()
        while interface != interface.parent and not (interface/'bInterfaceNumber').exists():
            interface = interface.parent
        if not (interface/'bInterfaceNumber').exists() or (interface/'bInterfaceNumber').read_text().strip() != '00':
            continue
        usb = interface
        while usb != usb.parent and not (usb/'idVendor').exists():
            usb = usb.parent
        expected = dict(idVendor='1209', idProduct='316d', product='m1n1 uartproxy 8e0cf28')
        if all((usb/key).exists() and (usb/key).read_text().strip() == value
               for key, value in expected.items()):
            found.append(Path('/dev')/tty.name)
    assert len(found) == 1, 'require exactly one qualified primary m1n1 proxy'
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--m1n1-source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='new private result file')
    args = parser.parse_args()
    # Optimized Python removes asserts; never permit hardware checks to disappear.
    if not __debug__:
        parser.error('optimized Python is prohibited')
    if args.output.exists():
        parser.error('refusing to overwrite evidence')
    sys.path.insert(0, str(args.m1n1_source.resolve()/'proxyclient'))
    from m1n1.proxy import M1N1Proxy, UartInterface
    from m1n1.tgtypes import BootArgs_r3
    from m1n1.adt import ADTNodeStruct
    interface = UartInterface(str(primary_device()))
    try:
        interface.tty_enable = False
        interface.nop()
        proxy = M1N1Proxy(interface)
        assert proxy.get_chipid() == 0x6040 and proxy.get_exc_count() == 0
        ptr, revision = proxy.get_bootargs_rev()
        assert revision == 3
        boot = BootArgs_r3.parse(interface.readmem(ptr, BootArgs_r3.sizeof()))
        address = boot.devtree-boot.virt_base+boot.phys_base
        assert boot.phys_base <= address < address+boot.devtree_size <= boot.phys_base+boot.mem_size
        root = ADTNodeStruct.parse(interface.readmem(address, boot.devtree_size))
        nodes = {}

        def walk(node, parent=''):
            props = {p.name: p.value for p in node.properties}
            path = parent+'/'+props['name'].rstrip(b'\0').decode('ascii')
            nodes[path.removeprefix('/device-tree') or '/'] = props
            for child in node.children:
                walk(child, path)

        walk(root)
        result = read_counter(proxy, *profile(nodes))
        with open(args.output, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as out:
            out.write(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, indent=2))
    finally:
        interface.dev.close()


if __name__ == '__main__':
    main()
