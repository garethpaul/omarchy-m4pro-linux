#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One explicitly approved clear of J614s PMU diagnostic byte 0xf802, 1 -> 0.

No watchdog, boot-policy, partition or storage operation. No automatic retry.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import types


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def clear_one(proxy, helper, mmio, slave, address):
    require((mmio, slave, address) == (0x509014000, 14, 0xf802), 'Exact PMU profile required')
    before = helper.read_counter(proxy, mmio, slave, address)
    require(before['pmu_error_count_byte'] == 1, 'Expected diagnostic byte exactly one; stop')
    require(helper.empty(proxy.read32(mmio)) and proxy.get_exc_count() == 0, 'SPMI not idle')
    # Same one-byte operation as m1n1 PMU.reset_panic_counter, without its
    # surrounding watchdog or other setup. No other PMU address is selectable.
    proxy.write32(mmio+4, (address << 16) | (1 << 15) | (slave << 8) | 0x30)
    proxy.write32(mmio+4, 0)
    deadline = time.monotonic()+1
    while proxy.read32(mmio) & (1 << 24):
        require(time.monotonic() < deadline, 'Write acknowledgement timed out; do not retry')
    reply = proxy.read32(mmio+8)
    require(reply & 0xff == 0x30 and (reply >> 8) & 0x7f == slave and reply >> 16 == 0 and reply & (1 << 15),
            'Write acknowledgement differs; do not retry')
    require(helper.empty(proxy.read32(mmio)), 'SPMI not empty after write')
    after = helper.read_counter(proxy, mmio, slave, address)
    require(after['pmu_error_count_byte'] == 0, 'Zero readback absent; do not retry')
    return {'before':1, 'after':0, 'pmu_register_written':True,
            'watchdog_action':'unchanged', 'protected_boot_configuration_changed':False,
            'scope':'Exactly one diagnostic scratch byte; no storage or security-policy write'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--m1n1-source', type=Path, required=True)
    ap.add_argument('--expected-usb-session', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--approved-one-byte-clear', action='store_true')
    a = ap.parse_args()
    require(__debug__ and a.approved_one_byte_clear, 'Explicit approval gate required')
    require(not a.output.exists(), 'Preserve earlier evidence; no automatic retry')
    helper_path = Path(__file__).with_name('read_pmu_counter.py');raw = helper_path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == 'a77f207bc1142265f20b343384b58f0621e441a80e863e24db0677333a1dd3f7', 'Reader source differs')
    helper = types.ModuleType('pinned_pmu_reader');helper.__file__ = str(helper_path)
    exec(compile(raw, str(helper_path), 'exec', dont_inherit=True, optimize=0), helper.__dict__)
    source = a.m1n1_source.resolve();sys.path.insert(0, str(source/'proxyclient'))
    from m1n1.proxy import UartInterface, M1N1Proxy
    from m1n1.adt import ADTNodeStruct
    from m1n1.tgtypes import BootArgs_r3
    port = helper.primary_device();usb = (Path('/sys/class/tty')/port.name/'device').resolve()
    while not (usb/'idVendor').exists() and usb != usb.parent:
        usb = usb.parent
    require((usb/'devnum').read_text().strip() == a.expected_usb_session, 'Proxy session changed')
    os.umask(0o077)
    # Durable intent is published before any register mutation, including read
    # command submission. An uncertain write never gets an automatic second try.
    with a.output.open('x') as stream:
        json.dump({'status':'APPROVED_SINGLE_CLEAR_ATTEMPTED', 'usb_session':a.expected_usb_session}, stream)
        stream.flush();os.fsync(stream.fileno())
    directory = os.open(a.output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    f = UartInterface(str(port));f.tty_enable = False;f.dev.exclusive = True
    try:
        f.cmd(f.REQ_NOP, struct.pack('<Q', 0))
        require(struct.unpack('<QQQ', f.reply(f.REQ_NOP))[0] == 0, 'Checksum negotiation differs')
        proxy = M1N1Proxy(f);proxy.nop()
        require(proxy.get_chipid() == 0x6040 and proxy.get_exc_count() == 0, 'Chip/exception state differs')
        ptr = proxy.get_bootargs()
        require(1 << 40 <= ptr < ptr+1152 <= (1 << 40)+(24 << 30), 'BootArgs outside physical RAM')
        boot = BootArgs_r3.parse(f.readmem(ptr, 1152))
        require(boot.revision == 3, 'BootArgs revision differs')
        address = boot.devtree-boot.virt_base+boot.phys_base
        require(0 < boot.devtree_size <= 1 << 20 and boot.phys_base <= address < address+boot.devtree_size <= boot.phys_base+boot.mem_size, 'ADT outside usable RAM')
        tree = ADTNodeStruct.parse(f.readmem(address, boot.devtree_size));nodes = {}
        def walk(node, parent=''):
            props = {p.name:p.value for p in node.properties}
            here = (parent+'/'+props['name'].rstrip(b'\0').decode('ascii')).removeprefix('/device-tree') or '/'
            if here in ('/','/chosen','/arm-io','/arm-io/nub-spmi0') or here.startswith('/arm-io/nub-spmi0/'):
                require(here not in nodes, 'Duplicate selected ADT node');nodes[here] = props
            for child in node.children:
                walk(child, here.rstrip('/'))
        walk(tree)
        mmio, slave, register = helper.profile(nodes)
        result = clear_one(proxy, helper, mmio, slave, register)
        require((usb/'devnum').read_text().strip() == a.expected_usb_session and proxy.get_exc_count() == 0, 'Final session/exception differs')
        result.update(status='SINGLE_BYTE_CLEAR_VERIFIED', usb_session=a.expected_usb_session, exceptions=0)
        with a.output.open('w') as stream:
            json.dump(result, stream, indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        print(json.dumps(result, indent=2))
    finally:
        f.dev.close()


if __name__ == '__main__':
    main()
