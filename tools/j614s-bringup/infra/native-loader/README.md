# Offline J614s RAM-loader preparation

**PARTIAL:** source cleanup, actual-source host controls and AArch64 loader
compilation pass. **UNTESTED:** target execution, SPMI hardware behavior, USB
handoff, watchdog recovery and booting the paired kernel. Nothing here grants
permission to boot or changes the target.

The original checkout remains at `b3df851fb5f1d32bdff085b10049cb20e535c1a3`
with its exact six tracked modifications and two untracked sources.
`original-before.json` records all 674 regular source-file hashes, the original
tracked diff fingerprint, config, build tag and four binary hashes.
`original-after.json` verifies they remain unchanged. The preserved original
flat binary is SHA-256
`7536a712fcdfc3fcb71f134b21c9665598ddc45cb7aec3e4e5b4e2e003d139a5`.
Its relationship to the dirty source is **UNPROVEN**; recording both identities
is not a claim that this source produced that old binary.

`archive/original-tracked.patch` is a valid zero-context patch; apply with
`git apply --unidiff-zero` at the original base, then copy the two exact archived
`j614s_native.c` / `.h` files into `src/`. The archived source snapshot was
checked against all 674 original file hashes before editing.

The separate source commits are:

- `a9fb254`: exact diagnostic source archive.
- `8c9ad78`: removes the hardcoded framebuffer note/mark functions, every call,
  the USB debug wrapper and assembly entry marker. No replacement success stubs
  were added; actual USB stop/timeout checks remain.
- `6249e0ecdb7677b6afa01989c23344962253e954`: requires the PMU health byte to be
  zero on both reads, refuses identity/read errors and nonzero values, performs
  no health-byte writes, and checks health before arming the existing watchdog.

`remove-framebuffer-debug.patch` and `readonly-health-before-watchdog.patch`
export the separate changes. `source-checks.json` records removed symbols and
that the assembly entry file now exactly matches the original upstream base.

## Tests and their limits

`test_pmu.py` extracts the actual admission function and actual ADT iteration /
property macros. Only metadata, MMIO and SPMI boundaries are mocked. It runs
26 PMU scenarios under GCC and Clang with ASan/UBSan, fatal sanitizer recovery,
`-Wall -Wextra -Werror`, and empty-stderr requirements. The baseline control
reproduces writes that clear health values 1 and 255. The candidate refuses
both with zero PMU write calls. Missing/wrong identity, duplicate primary,
initial and second-read errors, positive error status, a changed health byte,
controller changes and already-zero health are covered.

The additional 27-case ordering control executes the actual source call window
from health admission through watchdog arm. Baseline PMU refusal still reaches
watchdog arm; the candidate refuses before reaching it. Valid zero health arms
the existing 60-second timer; arm failure is propagated. The full native handoff
function is not executed by this host harness.

The existing watchdog may already be armed by earlier loader initialization.
Its behavior after a successful guard is preserved and **not qualified**.
Later RAM/FDT failures after watchdog arm remain an existing unqualified risk.
No claim here establishes recovery or excludes PMU writes by other loader drivers.

Run the controls from the tooling repository:

```sh
python3 infra/native-loader/test_pmu.py \
  --source ../overnight-native-loader-candidate \
  --output ../native-pmu-next.json
python3 infra/native-loader/test_pmu.py \
  --source ../overnight-native-loader-candidate \
  --output ../native-ordering-next.json --handoff-window
```

Use the archived source checkout plus `--legacy-red-control` to reproduce the
old behavior. The results are `pmu-before.json`, `ordering-before.json`,
`pmu-after.json` and `ordering-after.json`.

## Build contract

`build-result.json` records the clean source/tree, every source file hash,
compiler/linker/Cargo hashes and versions, exact config arguments, flags and
seven build artifacts. Clang 23.1.3, Rust/Cargo 1.91.1 and LLD 21.1.2 were used.
The seven tools shared with the qualified kernel tool contract have matching
binary hashes. Cargo dependency resolution is offline and Cargo.lock remains
unchanged. No original build directory is used.

The original native config flags remain `CHAINLOADING=1`,
`T6040_STAGE1_CDC=1`, `J614S_NATIVE=1`, `BUILTIN_LOGO=aurora`, with the same
AArch64 soft-float target and optimization flags. Additional C/Rust path maps
remove host paths from flat output; the build tag explicitly identifies the
new candidate. These differences are recorded rather than implying original
binary reproduction.

The initial new unappended flat loader was SHA-256
`2be8e00074e3fd71940107a66c90abbf919dfd5fb6d32fc8e5ca7b53a73434de`.
That build passed compilation but failed independent reproduction: the broad
HOME map took precedence over SOURCE, leaving five checkout-specific fatfs
panic strings and a checkout-specific C DWARF compilation directory.
`repro-before.json` preserves both artifact sets and the actual path evidence.
The earlier host-home-prefix-only check did not catch this directory dependence.

The corrected recipe maps HOME first, then the more specific SOURCE.
`build-result-remapped.json` records the corrected full build;
`repro-after.json` compares two new clean checkouts/full output trees at the
same source, config and tools. **BYTE_IDENTICAL:** flat binary, Mach-O, native
object, both full ELFs and both generated headers (seven files), with distinct
inodes. The native object now has DWARF compilation directory `source`; both
flat formats contain zero checkout-name matches as well as zero home-prefix
matches. The corrected flat loader is 3,538,944 bytes, SHA-256
`2309dfbb368c5feadfc0ae70e0fbb11ac8e28132c815ab1c3eb63a66821a0e00`.
The first two unequal builds are retained. No further repeat is needed without
a new source, config, tool or recipe change.
Both flat formats contain zero host-home prefix matches. ELF/object architecture,
config equality, tool/source stability and absence of a PMU-write reference in
`j614s_native.o` pass. Other loader objects legitimately retain SPMI helpers.
Raw ELF/debug files and build logs are private intermediates.

For another build, use a new clean checkout at the full candidate commit with
no `build/` directory, plus a new metadata output directory:

```sh
python3 infra/native-loader/build_loader.py \
  --source ../native-loader-next-clean-checkout \
  --commit 6249e0ecdb7677b6afa01989c23344962253e954 \
  --output ../native-loader-next-build \
  --linker ../build-tools/ld.lld --jobs 8
```

The corrected matching checkouts are `overnight-native-loader-remap-source-01`
and `overnight-native-loader-remap-source-02`; their metadata outputs are
`overnight-native-loader-build-03` and `overnight-native-loader-build-04`.
The candidate build lives in its separate source checkout's `build/` directory;
this upstream Makefile has no external `O=` output support. Metadata and the
private verbose log live in the separate build output directory. The tool
refuses an existing source build directory or metadata output directory.

`intended-kernel.json` records the separate compile-qualified/reproduced kernel
Image `f9d7b637...4604`, source `8f2f3d13600aacadd93d577855b7e212b8ae57ff`,
config `6c5aba...6516`. That kernel is **not appended** to this loader. No
initramfs or DT was packaged, and compatibility/handoff remains untested.
