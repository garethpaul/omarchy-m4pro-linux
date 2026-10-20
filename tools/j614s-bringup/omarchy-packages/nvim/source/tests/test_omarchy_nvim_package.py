#!/usr/bin/env python3
"""Exercise package() only; never run build(), Neovim or packaged binaries."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / 'pkgbuilds/omarchy-nvim'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


class PackageTests(unittest.TestCase):
    def test_seed_drops_machine_specific_mason_on_both_build_architectures(self):
        for target, expected_machine in [('x86_64-linux-gnu', 62), ('aarch64-linux-gnu', 183)]:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                config = root / 'config/nvim'
                data = root / 'data/nvim'
                config.mkdir(parents=True)
                (config / 'init.lua').write_text('return {}\n')
                shutil.copytree(PACKAGE / 'lua', config / 'lua')
                lazy = data / 'lazy/fixture'
                lazy.mkdir(parents=True)
                (lazy / 'plugin.lua').write_text('return {name="source plugin"}\n')
                (lazy / 'tool.sh').write_text('#!/bin/sh\nexit 23\n')
                (lazy / 'tool.sh').chmod(0o755)
                run('git', 'init', '-q', str(lazy))
                run('git', '-C', str(lazy), 'add', '.')
                run('git', '-C', str(lazy), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
                mason = data / 'mason/packages/shfmt'
                mason.mkdir(parents=True)
                source = root / 'fixture.c'
                source.write_text('int fixture(void) { return 42; }\n')
                binary = mason / 'shfmt-fixture'
                run('clang', '--target=' + target, '-c', str(source), '-o', str(binary))
                payload = binary.read_bytes()
                self.assertEqual(payload[:4], b'\x7fELF')
                self.assertEqual(struct.unpack_from('<H', payload, 18)[0], expected_machine)
                binary.chmod(0o755)
                receipt = mason / 'mason-receipt.json'
                receipt.write_text(json.dumps({'links': {'bin': {'shfmt': binary.name}}}))
                (data / 'mason/bin').mkdir()
                (data / 'mason/bin/shfmt').symlink_to('../packages/shfmt/' + binary.name)
                (data / 'site/parser').mkdir(parents=True)
                shutil.copyfile(binary, data / 'site/parser/fixture.so')
                package_root = root / 'package'
                env = os.environ.copy()
                # Do not repurpose HOME. package() needs only these explicit paths.
                env.update(srcdir=str(root), startdir=str(PACKAGE), pkgdir=str(package_root),
                           XDG_CONFIG_HOME=str(root / 'config'), XDG_DATA_HOME=str(root / 'data'))
                run('bash', '-euc', 'source "$startdir/PKGBUILD"; package', env=env)
                seed = package_root / 'etc/skel/.local/share/nvim'
                self.assertFalse((seed / 'mason').exists(), 'arch=any seed retains builder Mason binary/receipt/symlink')
                self.assertEqual(list((seed / 'site').iterdir()), [])
                self.assertEqual((package_root / 'etc/skel/.config/nvim/lua/plugins/native-formatters.lua').read_bytes(), (PACKAGE / 'lua/plugins/native-formatters.lua').read_bytes())
                self.assertEqual((seed / 'lazy/fixture/plugin.lua').read_text(), (lazy / 'plugin.lua').read_text())
                self.assertEqual((seed / 'lazy/fixture/tool.sh').stat().st_mode & 0o777, 0o755)
                self.assertEqual((seed / 'lazy/fixture/plugin.lua').stat().st_mode & 0o777, 0o644)
                self.assertEqual((package_root / 'usr/bin/omarchy-nvim-setup').stat().st_mode & 0o777, 0o755)
                self.assertTrue((package_root / 'usr/bin/omarchy-nvim-refresh').is_symlink())
                self.assertFalse((package_root / 'usr/share/omarchy-nvim/data').exists())
                self.assertTrue((package_root / 'etc/skel/.config/nvim/lua/plugins/theme.lua').is_symlink())
                for path in package_root.rglob('*'):
                    if path.is_file() and not path.is_symlink():
                        self.assertNotEqual(path.read_bytes()[:4], b'\x7fELF', path)
                # Packaging sanitizes the copy; build cache is not changed.
                self.assertEqual(hashlib.sha256(binary.read_bytes()).digest(), hashlib.sha256(payload).digest())
                self.assertTrue(receipt.exists())

    def test_native_formatters_are_dependencies(self):
        result = run('bash', '-euc', 'source "$1"; printf "%s\\n" "${depends[@]}"', 'test', str(PACKAGE / 'PKGBUILD'))
        self.assertIn('shfmt', result.stdout.splitlines())
        self.assertIn('stylua', result.stdout.splitlines())

    def test_lua_keeps_custom_mason_tools_without_redownloading_native_defaults(self):
        script = r'''
local specs = dofile(arg[1])
local mason
for _, spec in ipairs(specs) do
  if spec[1] == "mason-org/mason.nvim" then mason = spec end
end
assert(mason and type(mason.opts) == "function")
local opts = {ensure_installed = {"stylua", "shfmt", "shellcheck", "lua-language-server"}}
mason.opts(nil, opts)
assert(table.concat(opts.ensure_installed, ",") == "shellcheck,lua-language-server")
local empty = {}
mason.opts(nil, empty)
assert(#empty.ensure_installed == 0)
local custom = {ensure_installed = {"shellcheck", "shfmt", "stylua", "stylua", "shellcheck"}, PATH = "append"}
mason.opts(nil, custom)
assert(table.concat(custom.ensure_installed, ",") == "shellcheck,shellcheck")
assert(custom.PATH == "append")
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test.lua'
            path.write_text(script)
            run('lua', str(path), str(PACKAGE / 'lua/plugins/native-formatters.lua'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
