#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Supervised separate-child RAM staging/vector; no disk or boot-policy API.

Root supplies a reviewed private context after complete offline bundle validation.
Stage and vector are separate, single-use invocations with live RAM rechecks.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import tempfile
import types


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    data = Path(path).read_bytes()
    require(sha(data) == expected, 'Pinned file changed')
    return data


def module_bytes(path, expected, name):
    data = checked(path, expected)
    module = types.ModuleType(name); module.__file__ = str(Path(path).resolve())
    sys.modules[name] = module
    exec(compile(data, module.__file__, 'exec', dont_inherit=True, optimize=0), module.__dict__)
    return module


def copied_bootargs(original, old_top, new_top):
    require(len(original) == 1152 and struct.unpack_from('<H', original)[0] == 3,
            'BootArgs revision/size differs')
    require(struct.unpack_from('<Q', original, 32)[0] == old_top, 'Original top differs')
    require(type(new_top) is int and old_top < new_top < 1 << 64, 'New top invalid')
    result = bytearray(original)
    struct.pack_into('<Q', result, 32, new_top)
    require(result[:32] == original[:32] and result[40:] == original[40:], 'Unexpected BootArgs delta')
    return bytes(result)


def durable_state(path, state):
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.next.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(state, stream, indent=2); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['plan', 'stage', 'vector'])
    ap.add_argument('--context', type=Path, required=True)
    ap.add_argument('--expected-context-sha256', required=True)
    ap.add_argument('--operator-present', action='store_true')
    a = ap.parse_args()
    require(__debug__ and a.operator_present, 'Supervised invocation required')
    os.umask(0o077)
    context = json.loads(checked(a.context, a.expected_context_sha256))
    state_path = Path(context['state'])
    lock_fd = os.open(str(state_path)+'.lock', os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    tooling = Path(context['tooling']); resident = Path(context['resident_source'])
    require(context['reservation_source_sha256'] == '8388b68a1afd6a71829b2a3f5e9ce2924649b301e474dce4fee20ada7b9e6017',
            'Reviewed reservation source differs')
    reservation = module_bytes(tooling/'infra/staging-reservation/reservation.py', context['reservation_source_sha256'], 'checked_reservation')
    binary_paths = {'planner':tooling/'infra/staging-plan/planner.py', 'source':resident/'src/heapblock.c',
                    'flat':resident/'build/m1n1.bin', 'elf':resident/'build/m1n1-raw.elf',
                    'instructions':tooling/'recovery/allocator-instructions.json'}
    capture_bytes = checked(context['capture'], context['capture_sha256']); capture = json.loads(capture_bytes)
    original = checked(context['original_bootargs'], capture['session']['bootargs_sha256'])
    blob = checked(context['container'], context['container_sha256'])
    bundle = module_bytes(tooling/'integration/native-bundle/bundle.py', '6e67500997fffbd19da35254bd1d2bd4f908ada0ddadf45d328bcd2401e8d0da', 'checked_native_bundle')
    fmt = bundle.fmt
    # Re-run full pinned bundle/DT checks against the current CPU capture. A
    # prior receipt alone has no current-session release-address binding.
    path_keys = {'loader_binary','loader_elf','loader_source','kernel_source','kernel_bundle',
                 'initrd','probe_manifest','dt_generator','capture','observer_source',
                 'resident_source','diagnostics','dtb','dt_evidence'}
    ns = types.SimpleNamespace(**{k:Path(v) if k in path_keys else v for k,v in context['bundle_inputs'].items()})
    require(ns.expected_capture_sha256 == context['cpu_capture_sha256'] and
            ns.expected_usb_session == capture['session']['usb_enumeration'] and
            ns.expected_bootargs_sha256 == capture['session']['bootargs_sha256'] and
            ns.expected_adt_sha256 == capture['session']['adt_sha256'], 'Bundle/session pins differ')
    require(ns.capture.resolve() == Path(context['cpu_capture']).resolve() and
            ns.resident_source.resolve() == resident.resolve(), 'Bundle capture/resident path differs')
    ns.diagnostics = ns.diagnostics.with_name(ns.diagnostics.name+'.stager-'+a.mode+'-'+secrets.token_hex(8))
    paths = bundle.tools()
    validated = bundle.validate_all(ns, paths, bundle.independent_inputs(ns, paths))
    bundle.recheck(ns, paths, validated)
    flat, layout, _, _, dtb = validated[:5]
    require(sha(dtb) == context['dtb_sha256'], 'Current session DT differs')
    report = json.loads(checked(context['bundle_verification'], context['bundle_verification_sha256']))
    require(report['status'] == 'OFFLINE_FORMAT_VERIFIED_ONLY' and report['container_sha256'] == sha(blob) and report['container_bytes'] == len(blob), 'Independent bundle verification differs')
    fmt.parse(blob, flat, layout, bundle.expected_parts(validated))
    expected = dict(capture['session'], capture_sha256=context['capture_sha256'], synthetic_fixture=False)
    plan = reservation.plan_private(capture_bytes, expected,
        binary_inputs={key:path.read_bytes() for key,path in binary_paths.items()},
        container_sha256=sha(blob), container_length=len(blob), bootargs_bytes=original,
        bootargs_sha256=sha(original), expected_raw_heap=capture['memory']['heap_base'])
    require(capture['cpu_state'] == {'secondary_flags_set':11, 'secondary_slots_idle':True, 'resident_wfe_mode':True}, 'CPU/WFE readiness absent')
    symbols = {}
    for line in subprocess.check_output(['llvm-nm', '-S', str(resident/'build/m1n1-raw.elf')], text=True).splitlines():
        words = line.split()
        if len(words) == 4 and words[3] in ('spin_table', 'wfe_mode', '_end'):
            require(words[3] not in symbols, 'Duplicate resident symbol')
            symbols[words[3]] = (int(words[0], 16), int(words[1], 16))
    require(set(symbols) == {'spin_table', 'wfe_mode', '_end'}, 'Resident symbol absent')
    require(symbols['spin_table'][0] == 0xb0198 and symbols['spin_table'][1] >= 14*64 and
            symbols['spin_table'][0]+14*64 <= symbols['_end'][0] and
            0 < symbols['wfe_mode'][0] < symbols['_end'][0] and symbols['wfe_mode'][1] == 1,
            'Resident slot/WFE extent differs')
    cpu_capture = json.loads(checked(context['cpu_capture'], context['cpu_capture_sha256']))
    q = cpu_capture['private_session']; memory = capture['memory']
    require(q['resident_base'] == memory['resident_base'] and q['resident_end'] == memory['resident_end'] and
            q['table_address'] == memory['resident_base']+symbols['spin_table'][0] and
            q['ram_base'] == memory['usable_base'] and q['ram_size'] == memory['usable_size'] and
            q['boot_video'] == memory['boot_video'], 'CPU/geometry captures differ')
    final_args = copied_bootargs(original, capture['memory']['bootargs_top'], plan['expected_heap_after'])
    # Direct patching preserves reserved/padding bytes, unlike a struct rebuild.
    base = capture['memory']['resident_base']
    metadata = {row['name']:row for row in capture['protected_metadata']}
    if a.mode == 'plan':
        output = state_path.with_suffix('.plan.json')
        require(not output.exists(), 'Preserve prior plan')
        planner = reservation.verify_binary_contract({key:path.read_bytes() for key,path in binary_paths.items()})
        _, protected, _ = planner._capture(capture_bytes, expected)
        # Feasibility only; child startup may allocate before find_ram runs.
        future = planner.choose_base(plan['expected_heap_after'], 4 << 30,
            memory['usable_base']+memory['usable_size'], protected+[(plan['child_base'], plan['expected_heap_after'])])
        plan.update(final_bootargs_sha256=sha(final_args),
                    future_4g_geometry_candidate=future, future_4g_allocation_qualified=False)
        durable_state(output, plan)
        print('PRIVATE_PLAN_REVIEW_READY: clear64MiB child; no target interface opened or allocation performed')
        return
    sys.path.insert(0, str(resident/'proxyclient'))
    sys.path.insert(0, str(tooling/'recovery'))
    from m1n1.proxy import M1N1Proxy, UartInterface
    from read_pmu_counter import primary_device
    port = primary_device(); usb = (Path('/sys/class/tty')/port.name/'device').resolve()
    while not (usb/'idVendor').exists() and usb != usb.parent:
        usb = usb.parent
    require((usb/'devnum').read_text().strip() == capture['session']['usb_enumeration'], 'USB session changed')
    require(usb.name == context['physical_usb_port'], 'Physical USB port changed')
    if a.mode == 'stage':
        require(not state_path.exists(), 'Single-use stage output already exists')
        state = {'status':'STAGE_NOT_ATTEMPTED', 'context_sha256':a.expected_context_sha256,
                 'plan':plan, 'final_bootargs_sha256':sha(final_args), 'vector_attempted':False}
    else:
        state = json.loads(state_path.read_bytes())
        require(state['status'] == 'STAGED_AND_READ_BACK' and state['context_sha256'] == a.expected_context_sha256 and state['plan'] == plan and state['final_bootargs_sha256'] == sha(final_args) and state['vector_attempted'] is False, 'Stage is not eligible for a single vector attempt')
    def save():
        durable_state(state_path, state)
    interface = UartInterface(str(port)); interface.dev.exclusive = True
    with state_path.with_suffix('.console.txt').open('a') as console, contextlib.redirect_stdout(console):
        try:
            interface.tty_enable = False; interface.tty_log = console
            interface.cmd(interface.REQ_NOP, struct.pack('<Q', 0))
            require(struct.unpack('<QQQ', interface.reply(interface.REQ_NOP))[0] == 0,
                    'Transfer checksum negotiation differs')
            interface.enabled_features = type(interface.enabled_features)(0)
            proxy = M1N1Proxy(interface); proxy.nop()
            require(proxy.get_chipid() == 0x6040 and proxy.get_base() == base and proxy.get_exc_count() == 0, 'Live identity differs')
            require(proxy.get_bootargs() == metadata['live-bootargs']['base'], 'BootArgs pointer changed')
            require(interface.readmem(metadata['live-bootargs']['base'], 1152) == original, 'Live BootArgs changed')
            require(sha(interface.readmem(metadata['live-adt']['base'], metadata['live-adt']['size'])) == capture['session']['adt_sha256'], 'Live ADT changed')
            for _, (offset, size, expected_sha) in reservation.FUNCTIONS.items():
                require(sha(interface.readmem(base+offset, size)) == expected_sha, 'Live allocator code differs')
            # Exact ELF-relative globals and spin-table location are source/binary bound.
            heap = lambda: struct.unpack('<Q', interface.readmem(base+0x134368, 8))[0]
            require(struct.unpack('<Q', interface.readmem(base+0x134370, 8))[0] == capture['memory']['heap_limit'], 'Heap limit changed')
            table = base+0xb0198
            def slots_ready():
                b = interface.readmem(table, 14*64)
                require(interface.readmem(table, 14*64) == b, 'Resident slots unstable')
                expected_cpus = {str(row['cpu_id']):row['expected_mpidr'] for row in cpu_capture['cpus']}
                require(set(expected_cpus) == {'0','1','2','3','4','5','6','7','10','11','12','13'}, 'CPU identity set differs')
                for key, mpidr in expected_cpus.items():
                    cpu = int(key); actual, flag, target, *args = struct.unpack_from('<8Q', b, cpu*64)
                    require(actual == mpidr, 'Resident MPIDR differs')
                    if cpu != 4:
                        require(flag and target == 0 and not any(args[:4]), 'Resident release slot busy')
                require(interface.readmem(base+symbols['wfe_mode'][0], 1) == b'\1', 'Resident WFE changed')
            slots_ready()
            destinations = [(plan['container_destination'], blob), (plan['bootargs_destination'], final_args)]
            for address, data in destinations:
                require(plan['child_base'] <= address < address+len(data) <= plan['expected_heap_after'], 'Write outside clear child')
            if a.mode == 'stage':
                require(heap() == plan['raw_heap'], 'High-water changed before reservation')
                state['status'] = 'RESERVATION_ATTEMPTED'; save()
                returned = proxy.heapblock_alloc(plan['allocation_bytes'])
                require(returned == plan['expected_allocation_return'] and heap() == plan['expected_heap_after'], 'Allocator return/high-water differs; stop')
                state['status'] = 'CHILD_RESERVED'; save()
                for address, data in destinations:
                    interface.writemem(address, data)
                    require(interface.readmem(address, len(data)) == data and interface.readmem(address, len(data)) == data, 'RAM readback differs')
                    proxy.dc_civac(address, len(data))
                proxy.ic_ivau(plan['child_base'], len(flat))
                slots_ready()
                require(heap() == plan['expected_heap_after'] and proxy.get_exc_count() == 0, 'Post-stage state differs')
                state.update(status='STAGED_AND_READ_BACK', reservation_claimed=True); save()
            else:
                require(heap() == plan['expected_heap_after'], 'High-water changed after staging')
                for address, data in destinations:
                    require(interface.readmem(address, len(data)) == data, 'Staged payload changed')
                slots_ready()
                require(proxy.get_exc_count() == 0, 'Exceptions before vector')
                # The child performs its own read-only health check before arming
                # its existing watchdog. No PMU reset or resident watchdog action.
                state.update(status='VECTOR_ATTEMPTED_UNKNOWN', vector_attempted=True); save()
                require(proxy.request(proxy.P_VECTOR, plan['pic_entry'], plan['bootargs_destination'], 0, 0, 0) == 0, 'Vector was not acknowledged')
                state.update(status='VECTOR_ACKNOWLEDGED'); save()
        except Exception as error:
            state['error_type'] = type(error).__name__; save(); raise
        finally:
            interface.dev.close()
    print(state['status']+'; installed boot object and protected storage untouched')


if __name__ == '__main__':
    main()
