#!/usr/bin/env python3
"""AArch64 compile-only qualification of the complete Gravity G16 Rust crate."""
import argparse
import difflib
import os
from pathlib import Path
import shutil
import subprocess
import kernel_build as kb

COMMIT = 'db9f2f8f00986e3ef03fddbdaad55a861e793123'
REQUIRED = {'CONFIG_ARM64': 'y', 'CONFIG_ARCH_APPLE': 'y',
            'CONFIG_ARM64_16K_PAGES': 'y', 'CONFIG_NR_CPUS': '16',
            'CONFIG_RUST': 'y', 'CONFIG_DRM': 'y', 'CONFIG_DRM_ASAHI_M4': 'm',
            'CONFIG_PM': 'y', 'CONFIG_MODULES': 'y', 'CONFIG_CMDLINE': '""',
            'CONFIG_LOCALVERSION': '"-gravity-g16s-compile"'}
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source', required=True, type=Path)
ap.add_argument('--bindgen', required=True, type=Path)
ap.add_argument('--tool-dir', required=True, type=Path)
ap.add_argument('--tool-contract', required=True, type=Path)
ap.add_argument('--output', required=True, type=Path)
ap.add_argument('--jobs', type=int, default=8)
ap.add_argument('--commit', default=COMMIT)
ap.add_argument('--full-kernel', action='store_true')
ap.add_argument('--display', action='store_true', help='Include Apple DCP composite and module in compile profile')
ap.add_argument('--config', type=Path, help='Reviewed exact config; normalization must preserve its checksum')
ap.add_argument('--config-sha256', help='Required immutable checksum when --config is supplied')
ap.add_argument('--localversion', default='-gravity-g16s-compile')
ap.add_argument('--object', action='append', default=[], help='Additional reviewed driver/platform object to compile before full build')
ap.add_argument('--platform-only', action='store_true', help='Qualify only requested C/ASM platform objects and generated Rust bindings')
a = ap.parse_args()
if a.platform_only and (not a.object or a.full_kernel or a.display):
    raise SystemExit('FAIL: platform-only requires objects and cannot claim full kernel/display compilation')
for target in a.object:
    path = Path(target)
    if path.is_absolute() or '..' in path.parts or path.suffix != '.o' or path.parts[0] not in ('arch', 'drivers', 'kernel'):
        raise SystemExit('FAIL: invalid platform object target')
source = a.source.resolve()
state, overlay = kb.source_state(source)
if state['head'] != a.commit or state['untracked'] or a.jobs < 1:
    raise SystemExit('FAIL: wrong candidate commit, untracked source, or jobs')
original = kb.run(['git', 'show', 'HEAD:rust/Makefile'], source)
layout_options = original.count(b' --no-layout-tests')
if layout_options not in (0, 1):
    raise SystemExit('FAIL: unexpected upstream bindgen rule')
if (source / 'rust/Makefile').read_bytes() != original.replace(b' --no-layout-tests', b''):
    raise SystemExit('FAIL: expected layout-enabling source/overlay is absent or changed')
changed = kb.run(['git', 'diff', '--name-only', 'HEAD'], source).decode().splitlines()
if changed != (['rust/Makefile'] if layout_options else []):
    raise SystemExit('FAIL: unreviewed source overlay')
if bool(a.config) != bool(a.config_sha256):
    raise SystemExit('FAIL: exact config path and checksum must be supplied together')
if a.config and kb.digest(a.config) != a.config_sha256:
    raise SystemExit('FAIL: supplied config checksum mismatch')
paths = kb.tool_paths(a)
tools = kb.tool_state(paths)
if tools != kb.read_json(a.tool_contract)['tools']:
    raise SystemExit('FAIL: critical tools differ from qualified toolchain')
dest = a.output.resolve()
dest.mkdir(parents=True, exist_ok=False)
out = dest / 'build'
out.mkdir()
bin_dir = dest / 'bin'
bin_dir.mkdir()
for name, path in paths.items():
    (bin_dir / name).symlink_to(path)
base = a.config.read_bytes() if a.config else (source / 'arch/arm64/configs/m4_gpu_defconfig').read_bytes()
kb.write_json(dest / 'build-request.json', {'source': state, 'tools': tools,
              'input_config_sha256': kb.encoded_digest(base), 'config_mode': 'exact' if a.config else 'generated profile',
              'localversion': a.localversion, 'objects': a.object, 'display': a.display,
              'full_kernel': a.full_kernel, 'layout_overlay_sha256': kb.encoded_digest(overlay)})
(out / '.config').write_bytes(base)
if not a.config:
    subprocess.run([str(source / 'scripts/config'), '--file', str(out / '.config'),
                    '--set-str', 'LOCALVERSION', a.localversion,
                    '--set-val', 'NR_CPUS', '16', '--set-str', 'CMDLINE', '',
                    '--enable', 'MODULES', '--module', 'DRM_ASAHI_M4', '--enable', 'IKCONFIG',
                    '--enable', 'IKCONFIG_PROC'], check=True)
    if a.display:
        subprocess.run([str(source / 'scripts/config'), '--file', str(out / '.config'),
                        '--enable', 'BACKLIGHT_CLASS_DEVICE', '--module', 'DRM_APPLE'], check=True)
env = {k: v for k, v in os.environ.items() if k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR')}
env.update(PATH=str(bin_dir) + ':/usr/bin:/bin', LANG='C', LC_ALL='C',
           KBUILD_BUILD_USER='j614s', KBUILD_BUILD_HOST='builder',
           KBUILD_BUILD_TIMESTAMP='Mon Oct 19 00:00:00 UTC 2026',
           KBUILD_BUILD_VERSION='1', SOURCE_DATE_EPOCH='1792368000')
command = [str(paths['make']), '-C', str(source), 'O=' + str(out),
           'ARCH=arm64', 'LLVM=1', 'LOCALVERSION=+',
           'KRUSTFLAGS=' + kb.rust_remap_flags(source, out, paths['rustc']),
           'KCFLAGS=-ffile-prefix-map=' + str(source) + '=src -ffile-prefix-map=' + str(out) + '=build']
for tool, variables in kb.TOOL_VARS.items():
    command.extend(v + '=' + str(bin_dir / tool) for v in variables)
def execute(targets, log):
    result = subprocess.run(command + targets, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        after = kb.source_state(source)[0]
        kb.write_json(dest / 'failure.json', {
            'status': 'FAILED', 'hardware': 'UNTESTED', 'targets': targets,
            'exit_code': result.returncode, 'source_before': state, 'source_after': after,
            'source_drift': after != state, 'config_sha256': kb.digest(out / '.config'),
            'tools_unchanged': kb.tool_state(kb.tool_paths(a)) == tools,
            'scope': 'Build failure retained; inspect private local build.log'})
        raise SystemExit('FAIL: kernel target failed; evidence retained in failure.json and build.log')


obj_name = 'drivers/gpu/drm/asahi/asahi_m4.o'


def check_rust_assertions():
    obj = out / obj_name
    try:
        kb.rust_assertion_state(obj, paths['llvm-nm'])
    except ValueError:
        kb.write_json(dest / 'rust-build-assert-failure.json', {
            'status': 'BLOCKED (Rust build assertion)', 'hardware': 'UNTESTED',
            'source': state, 'config_sha256': kb.digest(out / '.config'),
            'object': kb.artifact_record(obj, dest), 'binding_layouts': kb.layout_state(out)})
        raise SystemExit('FAIL: Rust compile-time assertion remains unresolved in driver object')

with (dest / 'build.log').open('wb') as log:
    execute(['olddefconfig'], log)
    normalized = (out / '.config').read_text()
    settings = dict(line.split('=', 1) for line in normalized.splitlines() if line.startswith('CONFIG_') and '=' in line)
    required = dict(REQUIRED)
    required['CONFIG_LOCALVERSION'] = '"' + a.localversion + '"'
    if a.config:
        required.pop('CONFIG_CMDLINE')
    if a.display:
        required.update(CONFIG_BACKLIGHT_CLASS_DEVICE='y', CONFIG_DRM_APPLE='m')
    if a.full_kernel:
        required.update(CONFIG_APPLE_MAILBOX='y', CONFIG_APPLE_RTKIT='y',
                        CONFIG_IKCONFIG='y', CONFIG_IKCONFIG_PROC='y')
    for key, value in required.items():
        if settings.get(key) != value:
            raise SystemExit('FAIL: required compile profile missing ' + key)
    (dest / 'config.diff').write_text(''.join(difflib.unified_diff(base.decode().splitlines(True), normalized.splitlines(True), fromfile='reviewed-input.config' if a.config else 'gravity-m4_gpu_defconfig', tofile='normalized.config', n=0)))
    if a.config and kb.digest(out / '.config') != a.config_sha256:
        raise SystemExit('FAIL: Kconfig normalized supplied config; review config.diff and re-lock')
    targets_list = [['-j' + str(a.jobs), 'modules_prepare']]
    if a.object:
        targets_list.append(['-j' + str(a.jobs), *a.object])
    if not a.platform_only:
        targets_list.append(['-j' + str(a.jobs), obj_name])
    if a.display:
        targets_list.append(['-j' + str(a.jobs), 'drivers/gpu/drm/apple/iomfb.o', 'drivers/gpu/drm/apple/appledrm.o'])
    if a.full_kernel:
        targets_list.append(['-j' + str(a.jobs), 'Image', 'modules'])
    for targets in targets_list:
        execute(targets, log)
        if obj_name in targets:
            check_rust_assertions()
if a.config and kb.digest(a.config) != a.config_sha256:
    raise SystemExit('FAIL: reviewed input config drift during qualification')
if kb.source_state(source)[0] != state or kb.tool_state(kb.tool_paths(a)) != tools:
    raise SystemExit('FAIL: source/tool drift during qualification')
obj = out / obj_name
if not a.platform_only:
    header = obj.read_bytes()[:20]
    if header[:6] != b'\x7fELF\x02\x01' or header[18:20] != b'\xb7\x00':
        raise SystemExit('FAIL: complete crate is not ELF64 little-endian AArch64')
report = {'status': 'CRATE_COMPILED', 'hardware': 'UNTESTED', 'module_link': 'UNTESTED',
          'source': state, 'tools': tools, 'recipe': {**kb.RECIPE,
              'c_path_remapping': {'source': 'src', 'output': 'build'}},
          'layout_overlay_sha256': kb.encoded_digest(overlay),
          'config_sha256': kb.digest(out / '.config'), 'required_config': required,
          'config_mode': 'exact reviewed input' if a.config else 'generated compile-only profile',
          'layout_policy': 'isolated overlay' if layout_options else 'enabled in committed source',
          'binding_layouts': kb.layout_state(out),
          'scope': 'Complete asahi_m4 AArch64 crate; no firmware execution, target boot, or GPU capability claim'}
if a.platform_only:
    report.update(status='PLATFORM_OBJECTS_COMPILED',
                  scope='Requested platform objects and binding prerequisites only; GPU/kernel/module linking untested')
else:
    report['object'] = kb.artifact_record(obj, dest)
    report['rust_build_assert_unresolved'] = False
if a.object:
    for name in a.object:
        header = (out / name).read_bytes()[:20]
        if header[:6] != b'\x7fELF\x02\x01' or header[18:20] != b'\xb7\x00':
            raise SystemExit('FAIL: platform object is not ELF64 little-endian AArch64')
    report['platform_objects'] = [kb.artifact_record(out / name, dest) for name in a.object]
if a.display:
    report['scope'] += '; complete Apple DCP composite and IOMFB object also compiled'
    for name in ('drivers/gpu/drm/apple/iomfb.o', 'drivers/gpu/drm/apple/appledrm.o'):
        header = (out / name).read_bytes()[:20]
        if header[:6] != b'\x7fELF\x02\x01' or header[18:20] != b'\xb7\x00':
            raise SystemExit('FAIL: display object is not ELF64 little-endian AArch64')
    report['display_objects'] = [kb.artifact_record(out / name, dest) for name in
                                 ('drivers/gpu/drm/apple/iomfb.o', 'drivers/gpu/drm/apple/appledrm.o')]
if a.full_kernel:
    for name, origin in (('.config', out / '.config'), ('Image', out / 'arch/arm64/boot/Image'),
                         ('kernel.release', out / 'include/config/kernel.release')):
        shutil.copyfile(origin, dest / name)
    for module in out.rglob('*.ko'):
        target = dest / 'modules' / module.relative_to(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(module, target)
    contract = {'schema': 2, 'source': state, 'tools': tools, 'recipe': report['recipe'],
                'config': {'sha256': report['config_sha256'], 'required': required}}
    kb.write_json(dest / 'contract.json', contract)
    kb.write_json(dest / 'layout-evidence.json', report['binding_layouts'])
    kb.write_json(dest / 'path-audit.json', kb.path_state(dest))
    artifacts = [dest / p for p in ('.config', 'Image', 'kernel.release', 'build.log',
                                   'layout-evidence.json', 'path-audit.json')]
    artifacts += sorted((dest / 'modules').rglob('*.ko'))
    manifest = {'schema': 1, 'status': 'COMPILED', 'hardware': 'UNTESTED',
                'contract_sha256': kb.digest(dest / 'contract.json'),
                'config_sha256': report['config_sha256'],
                'artifacts': [kb.artifact_record(p, dest) for p in artifacts]}
    kb.write_json(dest / 'manifest.json', manifest)
    kb.verify(dest)
    report.update(status='KERNEL_AND_MODULES_COMPILED', module_link='PASS',
                  image=kb.artifact_record(dest / 'Image', dest),
                  modules=[r for r in manifest['artifacts'] if r['path'].startswith('modules/')],
                  release=(dest / 'kernel.release').read_text().strip(),
                  path_audit=kb.read_json(dest / 'path-audit.json'))
kb.write_json(dest / 'result.json', report)
print('PASS: ' + report['status'] + '; layout assertions enabled; hardware UNTESTED')
