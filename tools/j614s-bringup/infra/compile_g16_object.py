#!/usr/bin/env python3
"""Compile one reviewed G16 bootstrap candidate without deploying or claiming a full kernel."""
import argparse
import difflib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import kernel_build as kb

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source', required=True, type=Path)
ap.add_argument('--commit', required=True)
ap.add_argument('--config', required=True, type=Path)
ap.add_argument('--bindgen', required=True, type=Path)
ap.add_argument('--tool-dir', required=True, type=Path)
ap.add_argument('--baseline-contract', required=True, type=Path)
ap.add_argument('--output', required=True, type=Path)
ap.add_argument('--jobs', type=int, default=2)
a = ap.parse_args()
source = a.source.resolve()
state, diff = kb.source_state(source)
if state['head'] != a.commit or diff or state['untracked']:
    raise SystemExit('FAIL: candidate must be the exact clean reviewed commit')
paths = kb.tool_paths(a)
baseline = kb.read_json(a.baseline_contract)
if kb.tool_state(paths) != baseline['tools']:
    raise SystemExit('FAIL: candidate toolchain differs from qualified baseline')
if kb.config_state(a.config) != baseline['config']:
    raise SystemExit('FAIL: input config differs from qualified baseline')
if a.jobs < 1:
    raise SystemExit('FAIL: positive jobs required')
dest = a.output.resolve()
dest.mkdir(parents=True, exist_ok=False)
snapshot = dest / 'source'
snapshot.mkdir()
with tempfile.TemporaryFile() as archive:
    subprocess.run(['git', 'archive', a.commit], cwd=source, stdout=archive, check=True)
    archive.seek(0)
    with tarfile.open(fileobj=archive) as tf:
        tf.extractall(snapshot, filter='data')
if kb.source_state(source)[0] != state:
    raise SystemExit('FAIL: candidate source drift during snapshot')
out = dest / 'build'
out.mkdir()
shutil.copyfile(a.config, out / '.config')
bin_dir = dest / 'bin'
bin_dir.mkdir()
for name, path in paths.items():
    (bin_dir / name).symlink_to(path)
env = {k: v for k, v in os.environ.items() if k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR')}
env.update(PATH=str(bin_dir) + ':/usr/bin:/bin', LANG='C', LC_ALL='C',
           KBUILD_BUILD_USER='j614s', KBUILD_BUILD_HOST='builder',
           KBUILD_BUILD_TIMESTAMP='Mon Oct 19 00:00:00 UTC 2026',
           KBUILD_BUILD_VERSION='1', SOURCE_DATE_EPOCH='1792368000')
command = [str(paths['make']), '-C', str(snapshot), 'O=' + str(out),
           'ARCH=arm64', 'LLVM=1', 'LOCALVERSION=+',
           'KRUSTFLAGS=' + kb.rust_remap_flags(snapshot, out, paths['rustc'])]
for tool, variables in kb.TOOL_VARS.items():
    command += [v + '=' + str(bin_dir / tool) for v in variables]
object_name = 'drivers/gpu/drm/asahi/g16-bootstrap.o'
with open(dest / 'build.log', 'wb') as log:
    for targets in (['olddefconfig'], ['-j' + str(a.jobs), 'modules_prepare'],
                    ['-j' + str(a.jobs), object_name]):
        subprocess.run(command + targets, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
normalized = kb.config_state(out / '.config')
if kb.tool_state(kb.tool_paths(a)) != baseline['tools'] or kb.source_state(source)[0] != state:
    raise SystemExit('FAIL: source or tools drift after compilation')
input_config = a.config.read_text().splitlines(keepends=True)
output_config = (out / '.config').read_text().splitlines(keepends=True)
config_diff = ''.join(difflib.unified_diff(input_config, output_config, fromfile='baseline.config', tofile='candidate.config'))
(dest / 'config.diff').write_text(config_diff)
obj = out / object_name
with obj.open('rb') as stream:
    header = stream.read(20)
if header[:4] != b'\x7fELF' or header[4:6] != b'\x02\x01' or header[18:20] != b'\xb7\x00':
    raise SystemExit('FAIL: compiled object is not ELF64 little-endian AArch64')
report = {'recipe': kb.RECIPE, 'status': 'OBJECT_COMPILED', 'hardware': 'UNTESTED', 'full_kernel': 'UNTESTED',
          'source': state, 'tools': baseline['tools'],
          'input_config_sha256': baseline['config']['sha256'],
          'normalized_config': normalized, 'config_changed': bool(config_diff),
          'object': kb.artifact_record(obj, dest),
          'source_file_sha256': kb.digest(snapshot / 'drivers/gpu/drm/asahi/g16-bootstrap.c'),
          'binding_layouts': kb.layout_state(out),
          'scope': 'C compiler qualification only; no linking, deployment, firmware execution, or reboot'}
kb.write_json(dest / 'result.json', report)
print('PASS: G16 bootstrap candidate compiled as ELF64 AArch64; hardware UNTESTED')
