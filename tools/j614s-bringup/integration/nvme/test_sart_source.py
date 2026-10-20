#!/usr/bin/env python3
"""Run the actual immutable kernel SART predicate in a host-only fake."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--commit', required=True)
parser.add_argument('--output', type=Path, required=True, help='new private scratch directory')
parser.add_argument('--cc', default='clang')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
source = subprocess.check_output(['git', '-C', str(args.source), 'show',
                                  args.commit + ':drivers/soc/apple/sart.c'], text=True)
start = source.index('bool apple_sart_is_inherited_region(')
end = source.index('EXPORT_SYMBOL_GPL(apple_sart_is_inherited_region);', start)
end += len('EXPORT_SYMBOL_GPL(apple_sart_is_inherited_region);')
actual = source[start:end] + '\n'
(args.output / 'sart-predicate-under-test.c').write_text(actual)
harness = Path(__file__).with_name('sart-host-harness.c').resolve()
executable = args.output.resolve() / 'sart-host-test'
command = [args.cc, '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
           '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
           '-I', str(args.output.resolve()), str(harness), '-o', str(executable)]
compiled = subprocess.run(command, capture_output=True, text=True)
(args.output / 'compile.log').write_text(compiled.stdout + compiled.stderr)
if compiled.returncode:
    raise SystemExit('FAIL: actual SART predicate compile failed; see private compile.log')
result = subprocess.run([str(executable)], capture_output=True, text=True,
                        env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                                 UBSAN_OPTIONS='halt_on_error=1'))
(args.output / 'run.log').write_text(result.stdout + result.stderr)
if result.returncode or 'PASS: 274 actual SART predicate cases' not in result.stdout:
    raise SystemExit('FAIL: actual SART predicate execution failed; see private run.log')
report = {'status': 'WORKS (actual-source host fake only)', 'source_commit': args.commit,
          'function_sha256': hashlib.sha256(actual.encode()).hexdigest(),
          'harness_sha256': hashlib.sha256(harness.read_bytes()).hexdigest(),
          'compiler': subprocess.check_output([args.cc, '--version'], text=True).splitlines()[0],
          'compile_exit': compiled.returncode, 'run_exit': result.returncode,
          'output': result.stdout.splitlines(), 'hardware': 'UNTESTED',
          'target_access': False, 'sart_entry_writes': False, 'nvme_adoption': 'UNTESTED'}
(args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
