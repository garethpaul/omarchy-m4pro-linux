#!/usr/bin/env python3
"""Compile actual ANS control functions against deterministic host MMIO/work fakes."""
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
markers = ['static bool apple_nvme_unmanaged_power_path(',
           'static bool apple_nvme_provider_matches(',
           'static int apple_nvme_check_j614s_resources(']
actual = ''.join(extract(source, m) for m in markers)
(a.output / 'topology-functions-under-test.c').write_text(actual)
harness = Path(__file__).with_name('topology-host-harness.c').resolve()
exe = a.output.resolve() / 'topology-test'
cmd = [a.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
       '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
       '-I', str(a.output.resolve()), str(harness), '-o', str(exe)]
b = subprocess.run(cmd, text=True, capture_output=True)
(a.output / 'compile.log').write_text(b.stdout + b.stderr)
if b.returncode:
    print(b.stderr)
    raise SystemExit('actual selected source host compilation failed')
r = subprocess.run([str(exe)], text=True, capture_output=True,
    env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1'))
(a.output / 'run.log').write_text(r.stdout + r.stderr)
if r.returncode:
    print(r.stdout + r.stderr)
    raise SystemExit('actual selected source host tests failed')
report = {'status': 'WORKS (selected actual source host fake only)', 'source_commit': a.commit,
          'bundle_sha256': hashlib.sha256(actual.encode()).hexdigest(),
          'harness_sha256': hashlib.sha256(harness.read_bytes()).hexdigest(),
          'compiler': subprocess.check_output([a.cc, '--version'], text=True).splitlines()[0],
          'compile_exit': b.returncode, 'run_exit': r.returncode, 'output': r.stdout.splitlines(),
          'scope': 'exact board/resource/provider and inherited power topology; no real devres, concurrency, firmware or DMA',
          'hardware': 'UNTESTED', 'target_access': False, 'full_adoption': ('BLOCKED; initial refusal remains' if 'J614s ANS inherited RTKit adoption has not been ported' in source else 'PARTIAL source-only strict diagnostic admission; hardware UNTESTED')}
(a.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
