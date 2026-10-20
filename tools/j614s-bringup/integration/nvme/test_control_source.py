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
p.add_argument('--expect-timeout-idle-bug', action='store_true')
p.add_argument('--expect-poll-gate-bug', action='store_true')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
a.commit = subprocess.check_output(['git', '-C', str(a.source), 'rev-parse', a.commit], text=True).strip()
source = subprocess.check_output(['git', '-C', str(a.source), 'show', a.commit + ':drivers/nvme/host/apple.c'], text=True)
markers = ['static void apple_nvme_set_reset_ready(', 'static void apple_nvme_disable_queue(',
           'static void apple_nvme_quarantine(', 'static int apple_nvme_disable_locked(',
           'static int apple_nvme_disable(', 'static void apple_nvme_recovery_work(',
           'static enum blk_eh_timer_return apple_nvme_timeout(', 'static int apple_nvme_poll(',
           'static void apple_nvme_wait_freeze(', 'static inline void apple_nvme_writeq(',
           'static bool apple_nvme_can_adopt_rtkit(', 'static void apple_nvme_reset_work(']
actual = ''.join(extract(source, m) for m in markers)
(a.output / 'control-functions-under-test.c').write_text(actual)
harness = Path(__file__).with_name('control-host-harness.c').resolve()
exe = a.output.resolve() / 'control-test'
cmd = [a.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
       '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
       '-I', str(a.output.resolve()), str(harness), '-o', str(exe)]
if a.expect_timeout_idle_bug: cmd.append('-DEXPECT_TIMEOUT_IDLE_BUG')
if a.expect_poll_gate_bug: cmd.append('-DEXPECT_POLL_GATE_BUG')
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
          'expected_timeout_idle_bug': a.expect_timeout_idle_bug, 'expected_poll_gate_bug': a.expect_poll_gate_bug, 'compile_exit': b.returncode, 'run_exit': r.returncode, 'output': r.stdout.splitlines(),
          'scope': 'reset/timeout/recovery/stop/quarantine and ordered MMIO; no real devres, concurrency, firmware or DMA',
          'hardware': 'UNTESTED', 'target_access': False, 'full_adoption': ('BLOCKED; initial refusal remains' if 'J614s ANS inherited RTKit adoption has not been ported' in source else 'PARTIAL source-only strict diagnostic admission; hardware UNTESTED')}
(a.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
