# Isolated ARM64 formatter and Neovim checks

**WORKS, scoped:** signed ARM64 `shfmt 3.14.1-1` and `stylua 2.6.0-1` format owned fixtures and produce identical output on a second pass. Signed ARM64 `Neovim 0.12.6-1` runs headless, loads the unchanged `native-formatters.lua` callback from source commit `e8f5ede`, removes just the two native formatter defaults, preserves other Mason options/tools, and resolves `/usr/bin/shfmt` and `/usr/bin/stylua`.

**PARTIAL:** these are userspace checks under the already installed, hash-pinned QEMU, using a minimal dependency root. They do not qualify full LazyVim, Mason, Conform, a freshly built `omarchy-nvim` package, the whole 151-package transaction, target execution or performance. No editor plugin loader runs. The options callback is exercised directly inside real ARM64 Neovim; no simulated Neovim API is used for that callback.

`attempt-10.json` is the final successful run: eight commands returned zero, with exact output; ten explicit Neovim callback/isolation checks are recorded as true. The three executable package archives are selected from the immutable signed 151-package qualification and rechecked for byte size, SHA-256 and ARM64 ELF machine before extraction. The qualification, retained baseline manifest, emulator and options source are pinned in `exercise_native.py`. Each of the eleven required library/loader files is copied only after checking its bytes against the sealed baseline image manifest. The result records all fourteen executable/library file hashes. Runtime dependencies here come from the verified baseline, not a materialized whole-transaction overlay.

The sandbox has a read-only root containing just those files, a hash-verified copy of the static QEMU executable, this lane's Lua probe, and a synthetic `/etc/passwd`. Bubblewrap creates new user, mount, PID, IPC, UTS and network namespaces, drops every capability, clears the environment and exposes no host home, root tree, sockets or target devices. Writable paths are the lane-owned `/work` directory and sandbox `/tmp`/`dev`/`proc`. `HOME` is never overridden; the environment has no `HOME`, and the synthetic account resolves to `/work/home`. XDG paths point inside scratch. Neovim verifies read-only input writes fail with `EROFS`, host home paths are absent, no network route exists, effective capabilities are zero, and owned scratch remains writable. No archive extraction runs package installation scripts or hooks. The host's packages, trust store and binfmt configuration are unchanged.

Reproduce with the original private, read-only inputs supplied to the parent agent; paths below are arguments, not host configuration changes:

```sh
python3 exercise_native.py \
  --qualification QUALIFIED_151_JSON \
  --payload-cache QUALIFIED_PAYLOAD_CACHE \
  --baseline VERIFIED_BASELINE_ROOT \
  --source ../source/pkgbuilds/omarchy-nvim/lua/plugins/native-formatters.lua \
  --work NEW_OWNED_SCRATCH_DIRECTORY \
  --evidence NEW_RESULT_JSON
```

Each command has a 30-second subprocess timeout. There is no fallback to execution outside the namespace. Failed and earlier successful attempts are retained:

- `preparation-failure-01.json`: the first dependency copier rejected Neovim's absolute `DT_NEEDED` lpeg path before any payload execution. It now accepts only `/usr/lib/` paths, retains their subdirectories and checks canonical baseline file hashes.
- `attempt-02.json`: bubblewrap refused a bind destination absent from the read-only root; no payload ran. Mount destinations are now prepared before entering the sandbox.
- `attempt-03.json` and `attempt-04.json`: formatters passed, but probe reporting used a Neovim version API unavailable without its Lua runtime and then an unavailable API binding. The final probe uses the actual `nvim --version` result already captured by a separate command; no formatter or options check was weakened.
- `attempt-05.json`: the first successful bounded callback/isolation check.
- `attempt-06.json` through `attempt-08.json`: optional Neovim-to-QEMU child dispatch failed at Neovim's executable check. `child-dispatch-observation.json` records that `/qemu` was mode `0755` yet `executable('/qemu')` returned zero, whereas the native formatter returned one. Copying QEMU into the owned root did not repair this. The underlying executable-check cause remains unresolved. This lane therefore makes **no editor-to-formatter subprocess integration claim**. Reproduce that separate failure by adding `--probe probe-child-dispatch.lua`.
- `attempt-09.json`: successful original callback/isolation scope after preserving the separate child-dispatch failure.
- `attempt-10.json`: successful final harness with additional exact baseline-manifest and harness/probe provenance pins.

The source packaging fix and its original fixtures are unchanged. Existing user Mason directories remain untouched. Full offline LazyVim/Conform integration needs a separate validated ARM child-execution mechanism or a native ARM test environment; installing host binfmt rules or exposing host filesystem execution is outside this lane.
