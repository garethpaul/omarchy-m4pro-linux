# Full packaged LazyVim loader under isolated ARM64 emulation

**WORKS within this scope:**52 actual packaged LazyVim plugin specs load, the
real Mason command/setup resolves an empty default install list through the
unchanged native-formatters overlay, and real Conform automatically selects
stock `shfmt`/`stylua` commands for shell/Lua buffers. Both signed ARM64
formatters execute, produce independently expected edits and make no edit on a
second pass. No mock plugin API, command override or explicit formatter emulator
prefix is installed. Root independently rebuilt the input tree and replayed all
checks in a new owned directory. [Result](result.json).

Execution still uses emulation. This host already has an enabled AArch64
`binfmt_misc` handler with PF flags, pointing to the same hash-qualified QEMU
pathname. Its registry bytes are captured before/after and remain identical;
this work never registers or changes a handler. The already opened interpreter
FD behind the F flag was not inspected. Its bytes cannot be inferred solely
from the current pathname hash. Native Mac execution and performance remain
**UNTESTED**. The earlier explicit-prefix tests remain valid within their own
scope.

Signed archive identities remain those in frozen151 qualification30ce5339:
Neovim19d5b204, omarchy-nvim b46d4197 and Git b152a20e. The same verified
minimal executable/library root and source overlay from prior proof000030a4
are checked before copying. Git's needed pcre2/z-ng libraries, declared native
Tree-sitter parser files/aliases and Curl8.22 plus its dependency closure come
from sealed baseline manifest30a72f46/imagef6ceb11e. Every copied regular file
is hashed and checked as ARM64 ELF where applicable; symlink targets are
explicitly bounded. No newer Curl payload was downloaded or added to151.
The10,023 signed runtime/config/plugin member rows are identical across both
final runs and are retained once in [members.jsonl](evidence/members.jsonl).
The reviewed source candidate's native-formatters overlay is applied; copied
Mason binaries/receipts are omitted. This tests that source configuration, not
a rebuilt/signed nvim6 archive or existing-user migration.

The namespace root is read-only, all capabilities dropped and environment
cleared; host homes, network and target devices are absent. Only owned scratch
and namespace temporary/proc/device filesystems are writable. Scoped Git
configuration disables hooks, fsmonitor and automatic maintenance. Full
packaged init.lua/plugin-manager/filetype and formatter paths run unchanged.
Only DEBUG logging is enabled for observability.

**BLOCKED within this deliberately offline harness:** Mason registry/cache
refresh. The verified native Curl actually runs and exits6; DNS/registry are
unavailable in the unshared network environment. This neither qualifies
network/TLS behavior nor proves a production Mason defect. No Mason package,
whole151 transaction, hook or target installation ran.

Replay with original immutable inputs and a new owned path:

```sh
python3 run_startup.py --root "$VERIFIED_RUNTIME_ROOT" --proof "$PROOF" \
  --qualification "$QUALIFIED_151" --native-archive "$SIGNED_NEOVIM" \
  --seed-archive "$SIGNED_NVIM_SEED" --git-archive "$SIGNED_GIT" \
  --baseline "$SEALED_BASELINE" --baseline-curl --options "$SOURCE_OVERLAY" \
  --probe probe.lua --work "$NEW_PRIVATE_WORK"
python3 check_result.py "$NEW_PRIVATE_WORK"
```

The checker independently asserts exact formatter hashes,52specs, actual
Mason options, expected buffers/idempotence, stock DEBUG command lines and
exit statuses, isolation observations, unchanged handler state and the actual
registry failure. Optimized Python is refused. [Lane run12](evidence/lane-12/result.json)
and [independent root run13](evidence/root-13/result.json) have no stderr or
editor messages; their actual command logs and observations are retained.

[Attempt history](attempt-history.json) retains initial read-only bind, missing
Git and missing parser failures. These were incomplete test-input problems, so
no production package change was justified by them. Earlier raw attempts stay
private; not every early source revision has a retained snapshot. Final source
is frozen and independently replayed. Both source workers ended on a service
capacity error; root completed review, replay and curation without changing
model or target authority.
