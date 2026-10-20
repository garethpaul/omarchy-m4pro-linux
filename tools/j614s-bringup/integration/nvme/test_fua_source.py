#!/usr/bin/env python3
"""Compile actual quirk enum/name and execute the actual queue-limits fragment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def block(source, marker):
    start = source.index(marker)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        if source[end] == '{': depth += 1
        if source[end] == '}': depth -= 1
        end += 1
    return source[start:end]


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--commit', required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--expect-missing-quirk', action='store_true')
p.add_argument('--header-commit')
p.add_argument('--expect-fua-retained-bug', action='store_true')
p.add_argument('--cc', default='clang')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
commit = subprocess.check_output(['git', '-C', str(a.source), 'rev-parse', a.commit], text=True).strip()
def blob(path):
    return subprocess.check_output(['git', '-C', str(a.source), 'show', commit + ':' + path], text=True)
header = (subprocess.check_output(['git', '-C', str(a.source), 'show', a.header_commit + ':drivers/nvme/host/nvme.h'], text=True) if a.header_commit else blob('drivers/nvme/host/nvme.h'))
core = blob('drivers/nvme/host/core.c')
start = core.index('\tif ((ns->ctrl->vwc & NVME_CTRL_VWC_PRESENT) && !info->no_vwc)')
end = core.index('\n\t/*', start)
actual = block(header, 'enum nvme_quirks {') + ';\n' + block(header, 'static inline char *nvme_quirk_name(') + '\n'
actual += 'static void set_limits(struct nvme_ns *ns, struct info *info, struct queue_limits *out) {\nstruct queue_limits lim=*out;\n' + core[start:end] + '\n*out=lim;\n}\n'
flush = blob('block/blk-flush.c')
actual += block(blob('include/linux/blkdev.h'), 'static inline bool blk_queue_write_cache(') + '\n'
actual += block(flush, 'enum {') + ';\n'
actual += block(flush, 'static unsigned int blk_flush_cur_seq(') + '\n'
actual += block(flush, 'static void blk_flush_complete_seq(') + '\n'
actual += block(flush, 'static void blk_rq_init_flush(') + '\n'
actual += block(flush, 'bool blk_insert_flush(') + '\n'
(a.output / 'fua-source-under-test.c').write_text(actual)
harness = Path(__file__).with_name('fua-host-harness.c').resolve()
exe = a.output.resolve() / 'fua-test'
cmd = [a.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I', str(a.output.resolve()), str(harness), '-o', str(exe)]
if a.expect_fua_retained_bug: cmd.append('-DEXPECT_FUA_RETAINED_BUG')
b = subprocess.run(cmd, text=True, capture_output=True)
(a.output / 'compile.log').write_text(b.stdout + b.stderr)
report = {'source_commit': commit, 'bundle_sha256': hashlib.sha256(actual.encode()).hexdigest(),
          'harness_sha256': hashlib.sha256(harness.read_bytes()).hexdigest(), 'compile_exit': b.returncode,
          'compiler': subprocess.check_output([a.cc, '--version'], text=True).splitlines()[0],
          'header_commit': a.header_commit or commit, 'expected_fua_retained_bug': a.expect_fua_retained_bug,
          'scope': 'actual enum, namespace fragment and block flush sequence functions; fake queues/completion boundary, no real I/O or durability',
          'hardware': 'UNTESTED', 'target_access': False}
if a.expect_missing_quirk:
    if not b.returncode or "undeclared identifier 'NVME_QUIRK_BROKEN_FUA'" not in b.stderr:
        raise SystemExit('baseline did not reproduce the actual missing-quirk compile failure')
    report.update(status='REPRODUCED (actual enum lacks referenced quirk)', diagnostics=list(dict.fromkeys(line.split('error:',1)[1].strip() for line in b.stderr.splitlines() if 'error:' in line)), raw_diagnostics_sha256=hashlib.sha256(b.stderr.encode()).hexdigest())
else:
    if b.returncode:
        print(b.stderr)
        raise SystemExit('actual FUA core fragment compile failed')
    r = subprocess.run([str(exe)], text=True, capture_output=True, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1'))
    (a.output / 'run.log').write_text(r.stdout + r.stderr)
    if r.returncode:
        report.update(status='FAIL (corrected source behavior invariant)', run_exit=r.returncode, output=[line.split('fua-host-harness.c:',1)[-1] for line in (r.stdout+r.stderr).splitlines()])
        (a.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(r.stdout + r.stderr)
        raise SystemExit('actual FUA core fragment regression failed')
    report.update(status=('REPRODUCED (old namespace FUA retention bypasses explicit postflush)' if a.expect_fua_retained_bug else 'WORKS (actual source fragment host only)'), run_exit=r.returncode, output=r.stdout.splitlines())
(a.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
