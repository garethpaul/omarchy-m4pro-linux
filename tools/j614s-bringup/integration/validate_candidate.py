#!/usr/bin/env python3
"""Check an immutable compile-only candidate; this never operates the target."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def without_comments(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def check_invariants(files, settings):
    for name, value in {
        'CONFIG_ARM64': 'y', 'CONFIG_ARCH_APPLE': 'y', 'CONFIG_SMP': 'y',
        'CONFIG_NR_CPUS': '16', 'CONFIG_ARM64_16K_PAGES': 'y',
        'CONFIG_RUST': 'y', 'CONFIG_MODULES': 'y', 'CONFIG_DRM_ASAHI_M4': 'm',
        'CONFIG_DRM_APPLE': 'm', 'CONFIG_DRM_ASAHI_G16_BOOTSTRAP': 'm',
        'CONFIG_IKCONFIG': 'y', 'CONFIG_IKCONFIG_PROC': 'y', 'CONFIG_CMDLINE': '""',
    }.items():
        if settings.get(name) != value:
            raise ValueError('candidate config changed: ' + name)
    for name, data in files.items():
        if name.startswith(('drivers/gpu/drm/asahi/', 'drivers/gpu/drm/apple/')):
            # Dedicated transport diagnostic has its own non-rendering match.
            if name.endswith('g16-bootstrap.c'):
                continue
            if re.search(r'apple,(?:t6040|j614s)[^"\s]*', data):
                raise ValueError('new board alias/activation in dormant GPU/DCP: ' + name)
    nvme = without_comments(files['drivers/nvme/host/apple.c'])
    alloc = nvme[nvme.index('static struct apple_nvme *apple_nvme_alloc('):]
    prolog = alloc[:alloc.index('anv = devm_kzalloc')]
    if not re.search(r'if\s*\(of_machine_is_compatible\("apple,j614s"\)\)\s*'
                     r'return ERR_PTR\(dev_err_probe\(dev, -EOPNOTSUPP,', prolog):
        raise ValueError('J614s NVMe refusal must precede allocation and hardware operations')
    calls = re.findall(r'\b([a-zA-Z_]\w*)\s*\(', prolog[prolog.index('{') + 1:])
    if set(calls) - {'if', 'of_machine_is_compatible', 'ERR_PTR', 'dev_err_probe'}:
        raise ValueError('operation before J614s NVMe refusal')
    idle = files['arch/arm64/kernel/idle.c']
    if idle.index('fpsimd_save_and_flush_cpu_state();') > idle.index('apple_cpu_wfi();'):
        raise ValueError('FP/SIMD must be saved before WFI')
    override = files['arch/arm64/kernel/pi/idreg-override.c']
    if override.index('parse_cmdline(fdt, chosen);') > override.index('__parse_cmdline("id_aa64isar2.wfxt=0", false);'):
        raise ValueError('boot args could re-enable unsafe timed waits')
    if '--no-layout-tests' in files['rust/Makefile']:
        raise ValueError('binding layout assertions disabled')
    bootstrap = files['drivers/gpu/drm/asahi/g16-bootstrap.c']
    if 'drm_dev_register' in bootstrap or 'apple_rtkit_send_message' in bootstrap:
        raise ValueError('transport diagnostic unexpectedly activates rendering/application INIT')


def validate(source, config, ledger):
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
    if head != ledger['candidate_commit'] or dirty:
        raise ValueError('source commit differs or checkout is dirty')
    if hashlib.sha256(config.read_bytes()).hexdigest() != ledger['config_sha256']:
        raise ValueError('config digest differs')
    files = {}
    for row in ledger['files']:
        data = (source / row['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['candidate_sha256']:
            raise ValueError('source digest differs: ' + row['path'])
        files[row['path']] = data.decode()
    settings = dict(line.split('=', 1) for line in config.read_text().splitlines()
                    if line.startswith('CONFIG_') and '=' in line)
    check_invariants(files, settings)
    return {'status': 'WORKS (source/config invariants only)', 'source_commit': head,
            'config_sha256': ledger['config_sha256'], 'hardware': 'UNTESTED',
            'storage': 'BLOCKED (inherited RTKit adoption not ported in this checkpoint)',
            'gpu_rendering': 'BLOCKED (no qualified T6040 application INIT/job path)',
            'native_display': 'BLOCKED (T6040 handoff/firmware unqualified)',
            'deployment_allowed': False, 'target_access': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path(__file__).parent / 'configs/j614s-gravity-candidate.config')
    parser.add_argument('--ledger', type=Path, default=Path(__file__).parent / 'port-ledger.json')
    args = parser.parse_args()
    print(json.dumps(validate(args.source, args.config, json.loads(args.ledger.read_text())), indent=2))


if __name__ == '__main__':
    main()
