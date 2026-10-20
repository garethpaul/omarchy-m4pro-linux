#!/usr/bin/env python3
"""Create a local Mesa AArch64 cross file without changing host configuration."""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sysroot', type=Path, required=True)
parser.add_argument('--linker', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
sysroot = args.sysroot.resolve()
# Preserve ld.lld's invoked basename: resolving its rust-lld symlink changes
# LLD driver selection and makes Clang's linker detection fail.
linker = args.linker.absolute()
if not (sysroot / 'usr/include/stdio.h').is_file() or not linker.is_file():
    raise ValueError('expected existing target sysroot and ld.lld executable')
lines = ['[binaries]',
         f"c = ['clang', '--target=aarch64-unknown-linux-gnu', '--sysroot={sysroot}', '--gcc-toolchain={sysroot}/usr']",
         f"cpp = ['clang++', '--target=aarch64-unknown-linux-gnu', '--sysroot={sysroot}', '--gcc-toolchain={sysroot}/usr']",
         "ar = 'llvm-ar'", "strip = 'llvm-strip'", "pkg-config = 'pkg-config'", '',
         '[host_machine]', "system = 'linux'", "cpu_family = 'aarch64'", "cpu = 'armv8-a'", "endian = 'little'", '',
         '[properties]', f"sys_root = '{sysroot}'",
         f"pkg_config_libdir = ['{sysroot}/usr/lib/pkgconfig', '{sysroot}/usr/share/pkgconfig']",
         'needs_exe_wrapper = true', '', '[built-in options]',
         f"c_link_args = ['-fuse-ld={linker}']", f"cpp_link_args = ['-fuse-ld={linker}']", '']
if any("'" in str(path) or '\n' in str(path) for path in (sysroot, linker)):
    raise ValueError('cross-file paths may not contain quotes or newlines')
args.output.write_text('\n'.join(lines))
