# Architecture-independent Omarchy Neovim seed

## Later isolated runtime qualification

The packaging investigation below retains its original scope. Subsequent
[actual ARM runtime checks](runtime/README.md), [Neovim subprocess diagnosis](runtime/diagnostic/README.md)
and [real Conform integration](runtime/conform/README.md) now execute both signed
ARM formatters inside a read-only isolated userspace environment. Root independently
replayed automatic filetype selection, real subprocesses, buffer edits, idempotence
and unavailable-command refusal. The earlier test used an explicit QEMU prefix. A later [full-loader check](runtime/lazyvim/README.md) now passes52 packaged specs, real Mason setup and stock Conform commands under the host’s existing binfmt handler, with independent root replay. This supersedes the earlier runtime/command-lookup UNTESTED statements
only for that scope. Full Mason registry/install, native target execution, unsigned source6 package build/signing, existing-user migration and installation remain unqualified. Earlier statements below retain their original historical scope.

**PARTIAL:** the packaging defect is reproduced and fixed at the actual `package()` seam. A new signed package, native formatter runtime, and Neovim integration remain **UNTESTED**. Nothing was installed, no existing account was changed, and the frozen 117-package plans are unchanged.

The signed `omarchy-nvim-2026.9.21-5-any` archive contains exactly one ELF: an x86-64 `shfmt` binary under `/etc/skel/.local/share/nvim/mason/`, mode `0644`, plus its Mason symlink and installed receipt. See `archive-inspection.json` for archive and object hashes, ELF machine, permissions and receipt. This is a dormant new-account seed; it does not establish that an existing user executed the tool. The package-wide `chmod 644` also makes that binary non-executable.

The upstream `package()` copies the build machine's entire Neovim data tree. `site/` is emptied, but Mason's architecture-specific tools and receipts survive. Changing the package architecture alone would require separate native builds and retaining executable modes, and would still embed ephemeral installer state. The smaller fix removes the entire copied `data/mason` tree before generating the seed. Source Lua plugins and their Git worktree executable restoration remain intact.

The package now depends on native `shfmt` and `stylua`, the two defaults named by the exact cached LazyVim formatting and Mason configuration. A shipped `native-formatters.lua` override filters just those two names from Mason's automatic installation list, retaining all other requested tools and options. With the removed seed and native dependencies, Conform's existing `shfmt`/`stylua` command lookup can use the system tools. This command lookup has not been exercised in Neovim. Other Mason tools can still be installed by the user for their own machine.

The pinned ALARM `extra.db` contains aarch64 `shfmt 3.14.1-1` and `stylua 2.6.0-1`; `native-dependency-metadata.json` records its hash and exact entries. Neither formatter is installed in the captured baseline or included in the frozen current 117 selection. Availability in database metadata is not payload-signature, ABI or runtime qualification. A separate dependency closure and signed package build are required before deployment.

`SOURCE.json` pins upstream and patched commits and every copied source file. No repository `AGENTS.md` was present in the cloned upstream. `source/` is a minimal testable export, including the original setup script, package configuration, license and test. `0001-native-formatters.patch` applies to upstream commit `b412ff5bfb3b364498f935fffaedcc2070dfc3eb`.

Run the tests from any working directory:

```sh
python3 source/tests/test_omarchy_nvim_package.py
bash -n source/pkgbuilds/omarchy-nvim/PKGBUILD
```

The tests actually source the PKGBUILD and invoke only `package()` in disposable directories, leaving `HOME` unchanged. Fixtures contain real Clang-compiled ELF objects with `EM_X86_64` and `EM_AARCH64`, a Mason receipt and relative symlink, parser output, Lua source and a Git-tracked executable script. No fixture ELF or packaged command is executed. Tests assert that output contains no ELF or Mason state, site remains empty, Lua sources and mode restoration survive, setup commands have their expected modes, and the theme symlink and single-copy seed layout remain valid. A standalone Lua interpreter exercises only the new options callback, preserving unrelated tools, duplicates and options; it does not load Neovim or plugins.

The identical final test file fails against the unmodified upstream package and passes against the patched source (`before.txt`, `after.txt`; temporary paths are replaced and line-end whitespace is stripped). Bash syntax and Git whitespace checks pass. This is evidence rung **ran it** for packaging, not hardware or desktop verification.

Existing users' Mason directories are deliberately untouched. In particular, this change does not remove an old user-owned binary or receipt already copied into a home directory. The source package retains the existing unpinned networked `build()` and `Lazy! sync` behavior; neither was invoked or qualified here. Future plugin cache changes can add other native artifacts: the inspected archive has none outside Mason, but the fixture result does not prove every future cache architecture-independent. No production package archive was built or signed.
