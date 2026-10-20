# Resolved: Neovim misclassifies the root-level dispatcher path

**WORKS, scoped:** actual ARM64 Neovim now launches the hash-pinned QEMU dispatcher as a subprocess inside the same strict sandbox, and the signed native `shfmt` and `stylua` binaries produce the expected fixture output and idempotent second passes. The unchanged source options callback also passes. This resolves the earlier isolated child-dispatch test blocker without a production patch, permission change, architecture-check suppression, host binfmt registration, installation or weaker namespace.

The cause was the root-level pathname `/qemu`. It was not an ARM-versus-x86 execution restriction or an owner/mode problem. The new direct observations establish all of these simultaneously:

| Path | `uv.fs_access(path, 'X')` | Neovim `executable()` | `exepath()` |
|---|---|---|---|
| `/qemu` | true | 0 | empty |
| `/usr/bin/qemu-aarch64-static` | true | 1 | same nested absolute path |
| `/usr/bin/shfmt` | true | 1 | same absolute path |

Both dispatcher paths contain the same complete SHA-256-pinned x86-64 ELF bytes, mode `0755` and UID 0 within the namespace. Both have readable, identical ELF headers. The native ARM formatter headers are recorded separately. The runner verifies all three ARM executable and eleven library/loader hashes against the prior immutable runtime proof before making a new private input-root copy, then verifies the added nested QEMU copy against the same full binary hash. The original verified root is untouched.

`attempt-02/guest-strace.txt` identifies the failed check: the direct libuv access check calls `faccessat(..., "/qemu", X_OK, ...) = 0`, but Neovim's own executable lookup subsequently calls `statx(..., "/usr/bin//qemu", ...) = -1 ENOENT`. The exact-version primary sources explain this routing. In `os_can_exe()`, direct path handling depends on `gettail_dir(name) != name`. `gettail_dir("/qemu")` returns the original pointer because its final directory separator is the initial slash. The function therefore selects PATH search, appends `/qemu` to `/usr/bin`, and looks for `/usr/bin//qemu`. A nested absolute path returns a different directory pointer and reaches the ordinary regular-file plus `uv_fs_access(X_OK)` check. There is no ELF-architecture check in this path. Relevant unmodified source excerpts, resolved annotated tag, immutable commit URLs and whole-file hashes are retained.

The downloaded `v0.12.6` tag resolves to commit `779c36969e31080503be2dfccbcc3f999e289606`. Downloads from that immutable commit were verified byte-identical to the tag downloads. `primary-neovim-relevant.c` is an excerpt for review, not a patch or standalone build. The original signed ARM executable remains unchanged throughout.

`attempt-06` is the final passing check. Real ARM64 Neovim invokes `/usr/bin/qemu-aarch64-static -L / /usr/bin/shfmt ...` and the analogous StyLua command through its actual `system()` subprocess implementation. Both first-pass and idempotence outputs are asserted. `probe-nested.lua` still asserts that `/qemu` fails Neovim's lookup while the byte-identical nested pathname passes; the defect is not hidden. The sandbox root is read-only, scratch is separate, all namespaces are unshared, capabilities are dropped, environment cleared, and host home/network/target access are absent. No command executes a packaged payload outside bubblewrap.

**UNTESTED:** full LazyVim, Mason, Conform, automatically selected formatter commands, the rebuilt source package, the whole 151-package transaction, target hardware and performance. Child commands explicitly use the nested QEMU prefix because this host has no new binfmt registration. Successful emulated subprocesses do not establish native target integration.

Run from this directory, supplying the earlier verified root/proof and a fresh owned scratch directory:

```sh
python3 run_probe.py --root VERIFIED_RUNTIME_ROOT \
  --proof ../attempt-10.json --probe probe-nested.lua \
  --work NEW_OWNED_WORK --output NEW_RESULT_DIRECTORY
```

For direct access/lookup diagnostics with guest syscall logging, use `--probe probe.lua --strace`. Each invocation is bounded by a 30-second subprocess timeout, with no unisolated fallback. Earlier diagnostic attempts remain recorded:

- Attempt 01 performed the decisive syscall checks but reporting called an unavailable `uv.geteuid()` binding. Attempt 02 removes that optional reporting call and captures the full successful direct-access observation.
- Attempt 03 validated the nested path and actually launched the formatter, but parent QEMU `-strace` output from the forked child entered Neovim's merged subprocess output and invalidated exact-output comparison. That instrumentation failure is preserved. Trace logging is now an explicit runner option; the direct diagnostic uses it, while exact formatter-output tests run without it.
- Attempt 04 passes the real child subprocess checks. Attempt 05 additionally runs the unchanged packaging fix's options callback in that same process and passes. Attempt 06 repeats the same assertions after removing source trailing whitespace, so its probe hash matches the final exported source. One trailing-space trace line is normalized as recorded in `trace-normalization.json`; the raw capture remains in the earlier immutable commit.

All earlier runtime evidence and source commits are preserved. This diagnostic supersedes the earlier unresolved root-cause note only for the isolated child dispatcher.
