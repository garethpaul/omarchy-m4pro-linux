#!/usr/bin/env python3
"""Read-only J614s CPU qualification; evidence is written only to tmpfs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import time

CPUS = set(range(12))
MPIDRS = list(range(4)) + list(range(0x10100, 0x10104)) + list(range(0x10200, 0x10204))
BAD_LOG = re.compile(r'\b(?:BUG:|WARNING:|Oops:|Kernel panic|Internal error:|SError Interrupt)')


class QualificationError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise QualificationError(message)


def cpulist(value):
    result = set()
    for item in value.strip().split(','):
        bounds = item.split('-')
        require(1 <= len(bounds) <= 2, 'malformed CPU list')
        first, last = int(bounds[0]), int(bounds[-1])
        require(0 <= first <= last < 4096, 'invalid CPU range')
        result.update(range(first, last + 1))
    return result


def strings(path):
    return [x.decode('ascii') for x in path.read_bytes().split(b'\0') if x]


def topology(root=Path('/'), machine=None, affinity=None):
    machine = machine or platform.machine()
    require(machine == 'aarch64', 'refusing non-AArch64 host')
    dt = root / 'sys/firmware/devicetree/base'
    compatible = strings(dt / 'compatible')
    require({'apple,j614s', 'apple,t6040'} <= set(compatible), 'refusing hardware other than J614s/T6040')
    cpu_root = root / 'sys/devices/system/cpu'
    online = cpulist((cpu_root / 'online').read_text())
    present = cpulist((cpu_root / 'present').read_text())
    require(online == present == CPUS, 'all and only CPUs 0-11 must be present and online')
    allowed = set(os.sched_getaffinity(0) if affinity is None else affinity)
    require(allowed == CPUS, 'runner affinity/cpuset must permit all and only CPUs 0-11')
    nodes = []
    for node in (dt / 'cpus').glob('cpu@*'):
        if strings(node / 'device_type') != ['cpu']:
            continue
        reg = (node / 'reg').read_bytes()
        require(len(reg) == 8, 'CPU reg must contain two DT address cells')
        mpidr = int.from_bytes(reg, 'big')
        cpu_type = strings(node / 'compatible')
        expected_type = 'apple,sawtooth' if mpidr in range(4) else 'apple,everest'
        require(expected_type in cpu_type, 'CPU compatible differs from measured T6040 ADT mapping')
        nodes.append({'dt_node': node.name, 'mpidr': mpidr, 'compatible': cpu_type})
    require(sorted(x['mpidr'] for x in nodes) == MPIDRS, 'DT CPU MPIDRs differ from measured 4E/8P T6040 topology')
    cmdline = (root / 'proc/cmdline').read_text().strip()
    for word in cmdline.split():
        require(not word.startswith(('maxcpus=', 'nr_cpus=')) and not word.startswith(('idle=', 'arm64.nowfxt', 'cpuidle.off=1')) and word != 'nosmp',
                'CPU/idle workaround boot flag prevents qualification: ' + word)
    logical = []
    for cpu in sorted(CPUS):
        base = cpu_root / f'cpu{cpu}'
        item = {'cpu': cpu}
        for key in ('core_id', 'physical_package_id', 'cluster_id', 'core_cpus_list'):
            path = base / 'topology' / key
            item[key] = path.read_text().strip() if path.exists() else None
        # Expose mapping where the kernel exports it; never invent logical->MPIDR.
        node = base / 'of_node'
        item['dt_node'] = node.resolve().name if node.exists() else None
        logical.append(item)
    return {'compatible': compatible, 'online': sorted(online), 'allowed': sorted(allowed),
            'adt_derived_dt_cpus': sorted(nodes, key=lambda n: n['mpidr']), 'logical_topology': logical,
            'cmdline_sha256': hashlib.sha256(cmdline.encode()).hexdigest()}


def validate_workload(kind, output, returncode):
    require(returncode == 0, f'{kind} exited {returncode}')
    lines = output.splitlines()
    require(len(lines) == len(set(lines)), f'{kind}: duplicate evidence lines')
    expected_children = {f'CHILD {i} STATUS 0' for i in CPUS}
    children = {line for line in lines if line.startswith('CHILD ')}
    require(children == expected_children, f'{kind}: missing/failed/unexpected child')
    if kind == 'coherency':
        expected = expected_children | {'ATOMIC_COUNTER 12000000 EXPECTED 12000000', 'SHARED_ATOMIC_PASS'}
    elif kind == 'simd-context':
        expected = expected_children | {'SIMD_CONTEXT_PASS 12_CPUS 1000_SLEEPS_EACH 32_VECTOR_REGISTERS'}
    else:
        raise QualificationError('unknown workload')
    require(set(lines) == expected, f'{kind}: incomplete or unexpected evidence')


def command(args, timeout=90):
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    return process.returncode, output


def idle_snapshot(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if re.fullmatch(r'cpu\d+', fields[0]):
            require(len(fields) >= 6, 'short /proc/stat CPU line')
            cpu = int(fields[0][3:])
            require(cpu not in result, 'duplicate /proc/stat CPU line')
            result[cpu] = int(fields[4])
    require(set(result) == CPUS, '/proc/stat must contain exactly twelve CPUs')
    return result


def read_policy():
    result = {}
    for path in sorted(Path('/sys/devices/system/cpu/cpufreq').glob('policy*')):
        result[path.name] = {}
        for name in ('affected_cpus', 'scaling_driver', 'scaling_governor', 'scaling_cur_freq', 'cpuinfo_cur_freq'):
            try:
                result[path.name][name] = (path / name).read_text().strip()
            except OSError:
                result[path.name][name] = None
    return result


def read_telemetry():
    result = {'loadavg': Path('/proc/loadavg').read_text().strip(), 'thermal': {}, 'cpuidle': {}}
    for zone in sorted(Path('/sys/class/thermal').glob('thermal_zone*')):
        try:
            result['thermal'][zone.name] = {'type': (zone / 'type').read_text().strip(),
                                           'temp_millicelsius': int((zone / 'temp').read_text())}
        except (OSError, ValueError):
            result['thermal'][zone.name] = {'status': 'UNTESTED', 'cause': 'sensor not readable'}
    for cpu in sorted(CPUS):
        result['cpuidle'][cpu] = {}
        for state in sorted(Path(f'/sys/devices/system/cpu/cpu{cpu}/cpuidle').glob('state*')):
            values = {}
            for name in ('name', 'usage', 'time', 'disable'):
                try:
                    values[name] = (state / name).read_text().strip()
                except OSError:
                    values[name] = None
            result['cpuidle'][cpu][state.name] = values
    return result


def hash_worker(cpu, barrier, queue):
    try:
        os.sched_setaffinity(0, {cpu})
        require(os.sched_getaffinity(0) == {cpu}, 'affinity readback failed')
        block = bytes(range(256)) * 4096
        barrier.wait(15)
        wall_start, cpu_start = time.perf_counter(), time.process_time()
        digest = hashlib.sha256()
        for _ in range(64):
            digest.update(block)
        cpu_time, wall_time = time.process_time() - cpu_start, time.perf_counter() - wall_start
        queue.put({'cpu': cpu, 'digest': digest.hexdigest(), 'bytes': 64 * len(block),
                   'cpu_seconds': cpu_time, 'wall_seconds': wall_time,
                   'MiB_per_wall_second': 64 / wall_time, 'affinity': sorted(os.sched_getaffinity(0))})
    except BaseException as exc:
        queue.put({'cpu': cpu, 'error': repr(exc)})
        raise


def sample_hashes():
    context = mp.get_context('fork')
    barrier, queue = context.Barrier(13), context.Queue()
    children = [context.Process(target=hash_worker, args=(cpu, barrier, queue)) for cpu in sorted(CPUS)]
    expected = hashlib.sha256(bytes(range(256)) * (4096 * 64)).hexdigest()
    try:
        for child in children:
            child.start()
        barrier.wait(15)
        samples = [queue.get(timeout=45) for _ in CPUS]
        for child in children:
            child.join(10)
        require(all(child.exitcode == 0 for child in children), 'hash worker failed or stalled')
        require({x['cpu'] for x in samples} == CPUS, 'hash sample CPU set is incomplete')
        for sample in samples:
            require('error' not in sample, 'hash worker reported error: ' + repr(sample))
            require(sample['digest'] == expected and sample['affinity'] == [sample['cpu']], 'hash/affinity mismatch')
        return sorted(samples, key=lambda x: x['cpu'])
    finally:
        for child in children:
            if child.pid and child.is_alive():
                child.kill()
            if child.pid:
                child.join()
        queue.close()


def assert_tmpfs(path):
    # Refuse persistent evidence writes. Decode the mountinfo octal escape form.
    def unescape(value):
        return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)
    mounts = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split()
        mount = Path(unescape(fields[4]))
        if path == mount or mount in path.parents:
            mounts.append((len(mount.parts), fields[fields.index('-') + 1]))
    require(mounts and max(mounts)[1] == 'tmpfs', 'evidence directory must be on tmpfs; use /run or /dev/shm')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='fresh directory on tmpfs')
    parser.add_argument('--samples', type=int, default=3, help='positive number of per-CPU hash samples (default 3)')
    parser.add_argument('--binaries', type=Path, default=Path(__file__).resolve().parent / 'build')
    args = parser.parse_args()
    require(args.samples > 0, '--samples must be positive')
    out = args.output.resolve()
    assert_tmpfs(out)
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    result = {'schema': 1, 'status': 'UNTESTED', 'hardware_workloads_started': False, 'checks': {},
              'kernel': platform.release(), 'start_utc': datetime.now(timezone.utc).isoformat(),
              'start_monotonic': time.monotonic(),
              'scope': 'CPU qualification only; no GPU, suspend, cpufreq or persistent boot qualification',
              'performance_method': 'Concurrent pinned SHA256, 64 MiB/core/sample; CPU and wall time. Frequency/thermal snapshots are observational. No matched baseline.'}
    def save():
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    save()
    phase = 'topology'
    try:
        result['topology'] = topology()
        result['checks']['topology'] = 'WORKS'
        save()
        phase = 'kernel_log_before'
        rc, before = command(['dmesg', '--color=never'])
        require(rc == 0, 'kernel log access required; dmesg failed')
        require(not BAD_LOG.search(before), 'pre-existing kernel fault; refusing clean qualification')
        result['kernel_log_before_sha256'] = hashlib.sha256(before.encode()).hexdigest()
        result['policy_before'] = read_policy()
        result['telemetry_before'] = read_telemetry()
        for kind in ('coherency', 'simd-context'):
            phase = kind
            binary = (args.binaries / kind).resolve()
            data = binary.read_bytes()
            require(data[:6] == b'\x7fELF\x02\x01' and int.from_bytes(data[18:20], 'little') == 183,
                    kind + ': not a little-endian AArch64 ELF64 binary')
            result.setdefault('binary_sha256', {})[kind] = hashlib.sha256(data).hexdigest()
            result['hardware_workloads_started'] = True
            save()
            rc, text = command([str(binary)])
            (out / (kind + '.txt')).write_text(text)
            validate_workload(kind, text, rc)
            result['checks'][kind] = 'WORKS'
            save()
        phase = 'per_cpu_sha256'
        result['hash_samples'] = []
        for sample_index in range(args.samples):
            result['hash_samples'].append({'sample': sample_index, 'cpus': sample_hashes()})
            save()
        result['checks']['per_cpu_sha256'] = 'WORKS'
        phase = 'ordinary_idle_accounting'
        before_idle = idle_snapshot(Path('/proc/stat').read_text())
        idle_start = time.monotonic()
        time.sleep(2)
        after_idle = idle_snapshot(Path('/proc/stat').read_text())
        result['idle'] = {'sample_seconds': time.monotonic() - idle_start,
                          'before': before_idle, 'after': after_idle,
                          'delta_ticks': {cpu: after_idle[cpu] - before_idle[cpu] for cpu in sorted(CPUS)}}
        require(all(value > 0 for value in result['idle']['delta_ticks'].values()), 'idle accounting did not increase on every CPU')
        result['checks']['ordinary_idle_accounting'] = 'WORKS'
        phase = 'final_topology'
        result['final_topology'] = topology()
        result['checks']['final_topology'] = 'WORKS'
        result['policy_after'] = read_policy()
        result['telemetry_after'] = read_telemetry()
        phase = 'kernel_log_after'
        rc, after = command(['dmesg', '--color=never'])
        require(rc == 0, 'post-test dmesg failed')
        require(before in after, 'kernel log rotated or changed; kernel fault coverage incomplete')
        require(not BAD_LOG.search(after), 'kernel fault found after workloads')
        result['kernel_log_after_sha256'] = hashlib.sha256(after.encode()).hexdigest()
        result['checks']['kernel_fault_scan'] = 'WORKS'
        # Relevant CPU lines only: do not export full logs or arbitrary ADT properties.
        cpu_lines = [line for line in after.splitlines() if re.search(r'SMP:|smp:|CPU[0-9]+:|WFxT|WFIT|Booted secondary', line)]
        (out / 'kernel-cpu-lines.txt').write_text('\n'.join(cpu_lines) + '\n')
        result['status'] = 'WORKS'
    except BaseException as exc:
        result['status'] = 'BLOCKED' if not result['checks'] else 'PARTIAL'
        result['failure'] = {'check': phase, 'type': type(exc).__name__, 'message': str(exc)}
        result['qualification_passed'] = False
        raise
    finally:
        result['finish_monotonic'] = time.monotonic()
        result.setdefault('qualification_passed', result['status'] == 'WORKS')
        save()
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
