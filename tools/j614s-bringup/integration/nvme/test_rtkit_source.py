#!/usr/bin/env python3
"""Causal host regression of actual unchanged old/new RTKit functions."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess


def extract(source, marker):
    start = source.index(marker)
    brace = source.index('{', start)
    depth = 1
    cursor = brace + 1
    while depth:
        if source[cursor] == '{': depth += 1
        if source[cursor] == '}': depth -= 1
        cursor += 1
    return source[start:cursor] + '\n'


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--baseline', default='cf7658de5dce4d89d5b8014df204cbbd77edb56e')
parser.add_argument('--candidate', required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--cc', default='clang')
a = parser.parse_args()
a.output.mkdir(parents=True, exist_ok=False)

def blob(commit, path):
    return subprocess.check_output(['git', '-C', str(a.source), 'show', commit + ':' + path], text=True)

header = blob(a.candidate, 'include/linux/soc/apple/rtkit.h')
internal = blob(a.candidate, 'drivers/soc/apple/rtkit-internal.h')
types = ''.join(line + '\n' for line in internal.splitlines() if line.startswith(('#define APPLE_RTKIT_MAX_ENDPOINTS ', '#define APPLE_RTKIT_APP_ENDPOINT_START ')))
types += ''.join(extract(text, 'struct ' + name + ' {') + ';\n' for text, name in
                [(header, 'apple_rtkit_shmem'), (header, 'apple_rtkit_ops'), (internal, 'apple_rtkit')])
harness = Path(__file__).with_name('rtkit-host-harness.c').resolve()
runs = []
for name, commit in [('baseline', a.baseline), ('candidate', a.candidate)]:
    work = a.output / name
    work.mkdir()
    code = blob(commit, 'drivers/soc/apple/rtkit.c')
    constants = code[code.index('enum {'):code.index('struct apple_rtkit_rx_work {')]
    functions = extract(code, 'static int apple_rtkit_common_rx_get_buffer(')
    if name == 'candidate':
        functions += ''.join(extract(code, signature) for signature in [
            'static void apple_rtkit_free_buffer(', 'static void apple_rtkit_memcpy(',
            'static bool should_crop_syslog_char(', 'static void apple_rtkit_syslog_rx_log(',
            'static void apple_rtkit_mark_system_running(', 'static int apple_rtkit_claim_rx(',
            'static void apple_rtkit_detach_rx(', 'static void apple_rtkit_stop_rx(',
            'static void apple_rtkit_release_rx(', 'static struct apple_rtkit *__apple_rtkit_init(',
            'struct apple_rtkit *apple_rtkit_init(', 'struct apple_rtkit *apple_rtkit_init_adopted(',
            'void apple_rtkit_free(', 'void apple_rtkit_free_retaining_buffers('])
    (work / 'rtkit-types-under-test.h').write_text(types)
    (work / 'rtkit-constants-under-test.h').write_text(constants)
    (work / 'rtkit-functions-under-test.c').write_text(functions)
    executable = work.resolve() / 'rtkit-test'
    command = [a.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
               '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
               '-I', str(work.resolve()), str(harness), '-o', str(executable)]
    if name == 'baseline': command.insert(1, '-DBASELINE')
    compiled = subprocess.run(command, capture_output=True, text=True)
    (work / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        print(compiled.stderr)
        raise SystemExit(name + ': actual-source host compile failed')
    result = subprocess.run([str(executable)] + (["--expect-baseline-bug"] if name == "baseline" else []), capture_output=True, text=True,
                            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                                     UBSAN_OPTIONS='halt_on_error=1'))
    (work / 'run.log').write_text(result.stdout + result.stderr)
    wanted = 'REPRODUCED:' if name == 'baseline' else 'PASS: actual RTKit'
    if result.returncode or wanted not in result.stdout:
        print(result.stdout + result.stderr)
        raise SystemExit(name + ': actual-source regression failed')
    strict_failure = None
    if name == 'baseline':
        strict = subprocess.run([str(executable)], capture_output=True, text=True,
                                env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                                         UBSAN_OPTIONS='halt_on_error=1'))
        (work / 'fixed-invariant.log').write_text(strict.stdout + strict.stderr)
        if strict.returncode != 1 or 'FAIL: changed live RTKit request replaced descriptor' not in strict.stderr:
            raise SystemExit('baseline did not fail the corrected invariant causally')
        strict_failure = {'exit': strict.returncode, 'output': strict.stderr.splitlines()}
    runs.append({'name': name, 'source_commit': commit,
                 'function_bundle_sha256': hashlib.sha256(functions.encode()).hexdigest(),
                 'compile_exit': compiled.returncode, 'run_exit': result.returncode,
                 'fixed_invariant_failure': strict_failure,
                 'output': result.stdout.splitlines()})
report = {'status': 'WORKS (baseline failure reproduced; candidate host invariants pass)',
          'scope': 'Actual selected RTKit functions with fake Linux types/mailbox/DMA; no real concurrency or device access',
          'harness_sha256': hashlib.sha256(harness.read_bytes()).hexdigest(),
          'candidate_type_bundle_sha256': hashlib.sha256(types.encode()).hexdigest(),
          'compiler': subprocess.check_output([a.cc, '--version'], text=True).splitlines()[0],
          'runs': runs, 'hardware': 'UNTESTED', 'target_access': False,
          'nvme_adoption': 'UNTESTED; J614s refusal remains'}
(a.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
