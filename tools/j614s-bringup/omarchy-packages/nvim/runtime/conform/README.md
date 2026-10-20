# Real Conform integration under isolated ARM64 emulation

**WORKS, scoped:** actual Conform plugin code automatically selects `shfmt` for a shell buffer and `stylua` for a Lua buffer, runs the signed native ARM64 formatters, applies their edits to real ARM64 Neovim buffers, and reports no edit on an idempotent second pass. An unavailable-command negative case is omitted from the available list, reports unavailable, returns no formatting attempt and leaves the buffer unchanged. The unchanged native-formatter Mason options callback also passes in the same process.

`attempt-03/observations.json` records both selected formatter names, exact resulting buffer lines, successful callbacks, idempotence and the negative case. `attempt-03/conform.log` is the real plugin's debug output, including all four actual command lines and zero formatter exit statuses. `conform.format()` receives no `formatters` list: selection uses Conform's real filetype resolver, availability checks and built-in formatter definitions. Its normal argument construction, `vim.system()` execution, output processing, diff and buffer editing paths run unmodified. No fake plugin API, formatter callback, runner or `vim.system` replacement is used.

The harness explicitly configures the same two filetype mappings observed in the cached LazyVim defaults; it does not load LazyVim. Its only formatter-specific overrides are Conform's supported `command` and `prepend_args` settings, which prefix the unchanged native command with `/usr/bin/qemu-aarch64-static -L /`. This is required for ARM child execution on the x86 host without registering binfmt handlers. Built-in formatter arguments remain unchanged. This qualifies automatic **filetype-to-formatter selection through the explicit emulator prefix**, not stock native executable dispatch or automatically loaded full-LazyVim configuration.

The exact source input is the signed `omarchy-nvim-2026.9.21-5-any` archive SHA-256 `b46d41973cacfcf2d8be371351336a3f689e2eb7b9bacdb7ca81939354cbcbc9`. Only Conform's Lua files and license are extracted from it; Mason's cached foreign binary, other plugins, Git executables and install hooks are not extracted or run. Its cached Git metadata identifies Conform commit `016802de402556da54c36bd7359b441266b01cdd`; the distributed member hashes, rather than that metadata label alone, bind the tested code.

The native Neovim runtime is extracted from the same signed ARM64 `neovim-0.12.6-1` archive as the executable, SHA-256 `19d5b20499f038b51d32bd068c34a08238804f7253fa20002103a8d55627260d`. All 2,097 regular runtime files and 277 Conform Lua/license files have their archive member name, byte length, mode and SHA-256 recorded in `extracted-members.jsonl` (22,285,635 bytes total). Every written file is rehashed before execution and matched to its extracted signed bytes. The archives' exact sizes and SHA-256 are checked against the immutable signed 151-package qualification, itself pinned by hash. No package installation or hooks are involved.

The runner also rechecks the prior verified ARM executable/library root and unchanged options source, creates a new owned copy, and adds the same hash-pinned QEMU at the tested nested pathname. That root and the probe are read-only inside bubblewrap. All namespaces are unshared, capabilities dropped, environment cleared, and only separate owned scratch plus sandbox temporary/device/proc filesystems are writable. No host home, network connection, target device, host trust change, binfmt change, package installation or unisolated payload execution is available. The test runs headless with `-u NONE`, no plugin manager or download step, and a 30-second command timeout.

Reproduce from this directory with the original immutable inputs and new owned output locations:

```sh
python3 run_conform.py --root VERIFIED_RUNTIME_ROOT \
  --proof ../attempt-10.json --probe probe.lua \
  --qualification QUALIFIED_151_JSON \
  --native-archive SIGNED_NEOVIM_ARCHIVE \
  --seed-archive SIGNED_OMARCHY_NVIM_ARCHIVE \
  --work NEW_OWNED_WORK --output NEW_RAW_RESULT_DIRECTORY
```

The runner emits a full member manifest in its raw result. `curate_result.py` moves those identical rows into the shared JSONL file, preserves every execution field, and records the original raw-result SHA-256. This avoids duplicating the same 2,374-member list for each attempt. It does not redact or alter runtime outcomes.

The earlier checks are preserved. `preparation-failure-01.json` records a wrong harness assumption about Neovim's Lua module path; no payload ran. Attempt 02 successfully formats both buffers but its extra negative assertion incorrectly expected unavailable formatters to remain in `list_formatters()`. Inspection of the exact Conform implementation showed that this API filters unavailable entries. The final probe therefore checks both an empty available list and the separate `get_formatter_info().available == false`, plus the unchanged-buffer/no-attempt outcome. No plugin check was removed or patched.

**UNTESTED:** native execution on the Mac, the rebuilt and signed `omarchy-nvim` source candidate, existing-user migration, full LazyVim/Mason loading, stock formatter dispatch without an emulator prefix, all other formatters/languages, the entire 151-package transaction and desktop performance. No target access or publication occurred.
