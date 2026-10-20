#!/usr/bin/env python3
"""Exercise actual staged ANS predicates and borrowed-DMA callbacks on the host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def extract(source, marker):
    start = source.index(marker)
    cursor = source.index('{', start) + 1
    depth = 1
    while depth:
        if source[cursor] == '{': depth += 1
        if source[cursor] == '}': depth -= 1
        cursor += 1
    return source[start:cursor] + '\n'


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--commit', required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--cc', default='clang')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
a.commit = subprocess.check_output(['git', '-C', str(a.source), 'rev-parse', a.commit], text=True).strip()
source = subprocess.check_output(['git', '-C', str(a.source), 'show', a.commit + ':drivers/nvme/host/apple.c'], text=True)
markers = ['static bool apple_nvme_can_adopt_rtkit(', 'static int apple_nvme_read_handoff(',
           'static bool apple_nvme_in_inherited_rtkit_range(', 'struct apple_nvme_rtkit_mapping {',
           'static int apple_nvme_sart_dma_setup(', 'static void apple_nvme_sart_dma_destroy(']
actual = ''.join(extract(source, marker) + (';\n' if marker.startswith('struct ') else '') for marker in markers)
(a.output / 'nvme-functions-under-test.c').write_text(actual)
harness = Path(__file__).with_name('nvme-host-harness.c').resolve()
exe = a.output.resolve() / 'nvme-host-test'
command = [a.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
           '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
           '-I', str(a.output.resolve()), str(harness), '-o', str(exe)]
built = subprocess.run(command, capture_output=True, text=True)
(a.output / 'compile.log').write_text(built.stdout + built.stderr)
if built.returncode:
    print(built.stderr)
    raise SystemExit('actual NVMe host compile failed')
r = subprocess.run([str(exe)], capture_output=True, text=True,
                   env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                            UBSAN_OPTIONS='halt_on_error=1'))
(a.output / 'run.log').write_text(r.stdout + r.stderr)
if r.returncode or 'actual NVMe admission/borrowed-buffer host checks' not in r.stdout:
    print(r.stdout + r.stderr)
    raise SystemExit('actual NVMe host checks failed')
report = {'status': 'WORKS (actual selected source host fake only)', 'source_commit': a.commit,
          'source_bundle_sha256': hashlib.sha256(actual.encode()).hexdigest(),
          'harness_sha256': hashlib.sha256(harness.read_bytes()).hexdigest(),
          'compiler': subprocess.check_output([a.cc, '--version'], text=True).splitlines()[0],
          'compile_exit': built.returncode, 'run_exit': r.returncode, 'output': r.stdout.splitlines(),
          'scope': 'fake MMIO reads, pages, SART, cache and DMA; no real hardware or concurrency',
          'controller_writes': False, 'target_access': False, 'hardware': 'UNTESTED',
          'full_adopted_probe': ('BLOCKED; initial J614s refusal remains active' if 'J614s ANS inherited RTKit adoption has not been ported' in source else 'PARTIAL source-only strict diagnostic admission; hardware UNTESTED')}
(a.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
