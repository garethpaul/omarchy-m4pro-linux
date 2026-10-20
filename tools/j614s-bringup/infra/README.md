# J614s reproducible kernel builds

This lane owns host build infrastructure. None of these tools contacts USB,
SSH, KVM or the physical Mac, deploys artifacts, reboots, or changes storage or
boot policy. Compilation is separate from hardware qualification.

The current candidate is clean kernel commit
`f93a3416c60f26c68084134dc6c1d205becd5753`: archived diagnostic source, removed
fixed-address early framebuffer writes, and the reviewed G16 crash-state latch.
Its exact config is `configs/j614s-clean-candidate.config`, SHA-256
`1b622a928e6c7b4bf06d3eeb9066002e9562b91b9d3749e316593741b72c8c92`.
Normalization changed **only** `CONFIG_LOCALVERSION` to
`-j614s-clean-candidate`; `clean-candidate-config.diff` records the change.
No feature or validation setting was dropped.

## Build contract

`kernel_build.py` captures the source commit, binary dirty diff fingerprint,
every untracked file hash, exact configuration, critical tool binary hashes and
recipe version. Corrected bindgen 0.73.2 must have SHA-256
`7fdf32940891781eb742fb4a69775a0b39de4a48d0a168dfb3f740fb547fceda`.
Version text alone does not identify this corrected generator.

A build creates a fresh source snapshot and separate `O=` output tree. It checks
for source/config/tool drift before and after snapshotting and compilation,
rejects pre-existing output directories, drops inherited compiler flags, and
uses explicit compiler/linker/Rust paths and fixed build metadata. Existing
contracts cannot be overwritten by `lock`. Kconfig must preserve the normalized
input configuration byte-for-byte. The explicit `LOCALVERSION=+` suffix is part
of the recipe, including for the clean candidate source.

Recipe 2 maps Rust source, output and sysroot prefixes to stable relative paths.
The kernel's conditional `--remap-path-scope=macro` probe fails on the actual
Rust 1.91.1 toolchain, leaving absolute paths in recipe 1's Rust objects.
`rust-path-remap-probe.json` reproduces the compiler failure and demonstrates
that stable prefix mapping makes two independently compiled objects identical.

The recipe retains unconditional Rust size/alignment/field-offset assertions.
It rejects absent assertions, a missing AArch64 generator target, or
`--no-layout-tests` in the actual saved Kbuild command. `layout-evidence.json`
records 3,191 unconditional layout blocks and 16,546 offset checks compiled for
the baseline. Five valid-input corrected-generator fixtures also compile.

## Exact next build

Run from this worktree with Python 3.12 or newer (these runs used 3.14.8):

```sh
python3 infra/kernel_build.py check \
  --source ../overnight-clean-kernel \
  --config infra/configs/j614s-clean-candidate.config \
  --localversion=-j614s-clean-candidate \
  --bindgen ../toolchains/aurora-bindgen-qualified/rust-bindgen-0.73.2/target/release/bindgen \
  --tool-dir ../build-tools \
  --contract infra/clean-candidate-contract.json

python3 infra/kernel_build.py build \
  --source ../overnight-clean-kernel \
  --config infra/configs/j614s-clean-candidate.config \
  --localversion=-j614s-clean-candidate \
  --bindgen ../toolchains/aurora-bindgen-qualified/rust-bindgen-0.73.2/target/release/bindgen \
  --tool-dir ../build-tools \
  --contract infra/clean-candidate-contract.json \
  --output ../overnight-infra-clean-build-03 --jobs 8

python3 infra/kernel_build.py verify --output ../overnight-infra-clean-build-03
python3 infra/kernel_build.py path-check --output ../overnight-infra-clean-build-03
```

Review source/tool/config/recipe changes and capture a **new** contract using
`lock` and a new filename. Do not re-lock merely to conceal a failed check.
The immutable recipe 1 contract remains as historical evidence; rebuilding it
requires the old helper from commit `a274183`. The current helper rejects its
old schema for new builds rather than silently changing that recipe.

## Artifact verification and regression tests

Successful bundles contain `Image`, exact config, release, all matching modules,
contract, layout evidence, log and checksummed manifest. The verifier checks
hashes, lengths, path containment, required files, config/contract agreement,
AArch64 Image magic, little endian 16 KiB page flag, embedded IKCONFIG, and each
module's AArch64 ELF header and kernel release. The dedicated path audit rejects
actual host-home/build-directory prefixes in distributable Image/modules.

```sh
python3 -m unittest discover -s infra -p 'test_*.py' -v
python3 infra/kernel_build.py layout-check --output ../overnight-infra-clean-build-01/build
python3 infra/kernel_build.py compare \
  --output ../overnight-infra-clean-build-01 \
  --against ../overnight-infra-clean-build-02
```

Comparison first verifies both bundles and requires identical contracts and
kernel releases. It rejects the same directory or Image inode and compares the
actual Image and every module, excluding logs and directory-dependent command
files. A difference returns nonzero with exact artifact hashes. Checksums detect
mixing/corruption against a retained manifest; they are not signatures.

## Captured status

| Item | Status | Evidence |
| --- | --- | --- |
| Historical baseline full Image + 15 matching modules | WORKS (compile only) | `build-results.json`; exact and embedded config match |
| Historical baseline byte reproducibility | BLOCKED in recipe 1: absolute Rust paths | `reproducibility-before.json`: Image and Asahi module differ; 14 C modules match |
| Rust path-remap fix | WORKS (build reproducibility) | `clean-candidate-reproducibility.json`: independent full Image and 15 modules are byte-identical |
| AArch64 unconditional Rust layout checks | WORKS (compile only) | `layout-evidence.json`, `bindgen-test-results.json` |
| Wrong tool/config/corrupt/mixed artifact rejection | WORKS (host tests) | `check-results.json`, `regression-results.json`, `build-results.json` |
| Reviewed standalone G16 crash-latch object | PARTIAL | `g16-object-result.json`; AArch64 object compiled; hardware UNTESTED |
| Clean candidate full kernel | WORKS (compile only) | `clean-candidate-build-01.json`, `clean-candidate-build-02.json`; both pass complete verification |
| Hardware/deployment/recovery | UNTESTED by this lane | Primary agent owns physical target operations |

The original source tree and reference Image remain unchanged. Historical
recipe 1 bundles embed absolute Rust source/sysroot paths; retain them privately.
The first build preceded later verifier/layout audits; those audits were run
independently afterward. Results retain that distinction and failed comparisons.

`compile_g16_object.py` separately snapshots a clean reviewed commit, records
configuration normalization, runs `modules_prepare`, compiles only the bootstrap
object, and verifies ELF64 AArch64 output. Its result does not establish linking,
firmware operation, race behavior or hardware functionality.

This is a pinned critical-tool recipe, not a hermetic toolchain container.
Retain host utilities, dynamic libraries, Clang resource headers and Rust
source/sysroot packages for archival reproduction. Cross-machine reproducibility
and deployment remain unproven. Local build logs contain private paths and need
sanitizing before publication. Never publish raw firmware, ADTs, credentials or
unreviewed source snapshots. No unattended boot is permitted until the primary
agent independently verifies recovery and the known-good fallback.

The corrected full builds both produce Image SHA-256
`7683e4f6254026370ceecf4e64a5e9905344df658dea5f5d3e6679aebaf068f1`,
release `7.1.12-j614s-clean-candidate+`. All 15 modules also match byte-for-byte.
This establishes same-toolchain reproducibility for this exact clean source and
configuration; hardware behavior and cross-machine reproduction remain untested.


## Gravity G16S source port qualification

`qualify_gravity.py` compiles the entire `asahi_m4` Rust crate for AArch64 at
commit `db9f2f8f00986e3ef03fddbdaad55a861e793123`, not only the host serializer
wrapper. The sole isolated source overlay removes upstream `--no-layout-tests`;
`patches/gravity-enable-binding-layouts.patch` records it as a valid zero-context
patch. Apply it with `git apply --unidiff-zero` to a separate complete source
checkout. The shared sparse source is unchanged.

```sh
python3 infra/qualify_gravity.py \
  --source ../overnight-infra-gravity-source \
  --commit b442be4b28f3720daff6c5f26fe8b1ab3aef28f1 --full-kernel \
  --bindgen ../toolchains/aurora-bindgen-qualified/rust-bindgen-0.73.2/target/release/bindgen \
  --tool-dir ../build-tools \
  --tool-contract infra/baseline-contract.json \
  --output ../overnight-infra-gravity-build-04 --jobs 8
```

The tool contract is used only for critical binary fingerprints. This script
records its own source/overlay/config/recipe proof. The compile profile enables
modules, uses 16 CPUs and clears upstream's T8132 UART/`maxcpus=1` command line.
It does not establish a J614s boot configuration or widen any driver match.
The exact normalized config and zero-context diff are retained under
`configs/gravity-g16s-compile.config` and `gravity-compile-config.diff`.

`gravity-crate-result.json` records **WORKS (compile only)**: the complete
ELF64 AArch64 crate with 3,170 unconditional binding layout blocks and 16,284
field-offset checks. Three unused G16S API warnings remain, confirming that
runtime callers have not been connected; one existing kernel lint expectation
warning also remains. No warning suppression was added. Module linking and all
firmware/GPU/hardware behavior remain **UNTESTED** at this checkpoint.
`gravity-attempts.json` retains the rejected initial profile, where upstream
`MODULES=n` prevented the requested modular driver setting.


The first full Image link exposed an actual dependency bug; it did not pass.
`gravity-full-link-before.json` retains the `apple_mbox_*` undefined symbols.
`RUST_APPLE_RTKIT=y` selected `APPLE_RTKIT=y` while its mailbox provider remained
modular. Clean source commit `b442be4b28f3720daff6c5f26fe8b1ab3aef28f1` adds the
missing mailbox selection. The full command above requires both providers to
normalize to `y`; it does not force the mailbox setting. The source fix is
separate from the layout-enabling overlay. `gravity-kernel-after.json` records the corrected full Image and seven modules
linked successfully, including `asahi_m4.ko`. `gravity-mailbox-config.diff` shows
that the provider changed from module to built-in. Full artifact verification,
embedded config comparison and private-prefix auditing pass.
`gravity-artifact-negative-results.json` retains actual-artifact tamper, config
and mismatched-module rejection tests. Hardware remains untested. C debug paths now map exact compilation directories and their
children to stable `src`/`build` paths; debug information remains enabled.

`gravity-dcp-object-result.json` records an independent display checkpoint:
actual `iomfb.o` and complete `appledrm.o` compiled as ELF64 AArch64. Its source
`be6225839fe98158ce677d9424ce255aeedbb406` combines display source commit
`8e27e3edbf57903da4d62ab52f3b77df23801772` and the mailbox dependency fix;
the binding-layout overlay is again separate. The DCP compile profile enables
`BACKLIGHT_CLASS_DEVICE=y` and `DRM_APPLE=m`. The subsequent module/Image attempt failed modpost;
`gravity-dcp-module-failure.json` retains the four unexported direct-map/cache
symbols and exact source/config/object evidence. `gravity-dcp-mapping-review.md`
explains the existing no-map alternative and its unverified bootloader
preconditions. All display hardware behavior remains untested.
Reproduce in a fresh output directory using the command above with
`--source ../overnight-infra-gravity-dcp-source`,
`--commit be6225839fe98158ce677d9424ce255aeedbb406 --display`, and
`--output ../overnight-infra-gravity-dcp-build-02`.

For an independently reviewed J614s configuration, add `--config PATH`,
`--config-sha256 SHA256` and `--localversion=-REVIEWED-TAG`. Exact-input mode
copies that file without applying the generic compile-profile edits. After
`olddefconfig`, any checksum change stops qualification for explicit review and
re-locking. The input is rechecked after compilation. Full builds require
embedded IKCONFIG verification. With `--display`, both GPU and DCP remain
compiled as modules; source/device-tree matching and module loading are outside
this helper's scope. A clean source commit that already enables binding layout
assertions is accepted, as is the exact isolated layout overlay.
`gravity-helper-input-guards.json` records actual rejected source/tool/config
and LOCALVERSION inputs; the 20 host verifier regressions also pass.

The subsequent typed DCP callback patch `8c93f2c2576b4d53d11c064f8cbd5a45095fa71d`
also compiles all Apple DRM translation units and the full composite with strict
binding assertions (`gravity-dcp-typed-result.json`). It does not resolve the
separate mapping-interface link failure.

The primary agent then authorized source fix
`124fd0633bb8932bbf68845ecbe8a5ffc53dfb43`: modules explicitly require the existing
bootloader no-map pool; built-in direct-map fallback/restore stay unchanged.
Pool type/no-map metadata, aligned pool extent and 42-bit aligned IOVA range are
checked before reserved-memory attachment and component binding. Per-allocation
extent checks remain. No private arch helpers are exported and no pool/DART
metadata is fabricated. `gravity-dcp-restricted-kernel-after.json` records
the complete Image and ten modules linking successfully, including actual
`appledrm.ko` and `asahi_m4.ko`, under the exact same config as the failed DCP
modpost attempt. Strict artifact/embedded-config/module-version and private-path
checks pass. This establishes restricted modular compilation/linking; native
display remains blocked by unverified live no-map/DART handoff.

```sh
python3 infra/test_dcp_scanout.py \
  --source ../overnight-infra-gravity-dcp-nomap \
  --baseline 8c93f2c2576b4d53d11c064f8cbd5a45095fa71d
```

`dcp-nomap-host-results.json` records 16 actual-source pool/bind cases in each
GCC/Clang and module/built-in variant, under ASan/UBSan. It checks missing/invalid
metadata and failed attachment refuse before component binding; a valid fixture
binds afterward. Actual built-in fallback functions preprocess identically to
the baseline under both compilers, while module functions contain no private
arch calls. These are host API/metadata stubs, not live DART/DT/display tests.
The J614s no-map/DART handoff remains unverified and native DCP remains blocked.

Additional `--object PATH.o` options compile reviewed platform objects before
the GPU/DCP/full-kernel targets and record their actual ELF64 AArch64 hashes.


The first consolidated J614s exact-config attempt is retained in
`j614s-gravity-platform-attempt-01.json`: nine platform objects compile, while
the MTP object fails on a const device-node ownership mismatch in `of_node_put`.
No checks were disabled. The supplied config survives normalization exactly.
A follow-up clean source fixes the owned field type; qualification uses a new
pinned source snapshot and fresh output, leaving the failed build intact.
The helper now also saves `build-request.json` before compilation and records
source/tool/config state automatically in `failure.json` on make failure.

`dcp-prime-host-results.json` adds a causal import regression. It runs the actual
DRM ownership helper, full default import functions and the real FD-dispatch
snippet against host DMA API stubs. Source124 reproduces a foreign buffer
reaching attach/map; candidate `cf9836359cb60e7e53324b922fb44bd6c5c6ec21` refuses
before either operation. Actual no-map allocation sets the ownership marker;
authenticated exported pool BOs keep the default refcount-only self-import.
Built-in foreign/default behavior stays intact. GCC and Clang pass ASan/UBSan.
Run `test_dcp_prime.py --source ../overnight-infra-gravity-dcp-prime --baseline
124fd0633bb8932bbf68845ecbe8a5ffc53dfb43` using Python3. This temporary module
profile rejects foreign AGX-to-DCP PRIME buffers, so cross-device zero-copy
accelerated presentation is unavailable until a real DART import design exists.

The corrected MTP source passes all ten selected platform objects
(`j614s-gravity-platform-attempt-02.json`), but its full size-config build fails
modpost on `rust_build_error`. `j614s-gravity-kernel-attempt-02-failure.json`
retains the exact failure, relocation and unchanged source/config/tool checks.
The assertion is the MMIO compile-time offset check. `g16-mmio-object-after.json`
records source fix `6340620747e221ea415ddee944afccacff3953ee` compiling without
that unresolved trap under the exact same size configuration. Runtime loop
accesses now use checked reads/writes with error propagation; constant accesses,
features and assertions remain. A zero-context export is retained as
`patches/g16-runtime-mmio.patch`; apply with `git apply --unidiff-zero`.
`j614s-gravity-kernel-after-mmio.json` now records the complete Image and all
18 modules linking under the exact same size config6c5aba. Image, embedded
config, module versions and private-path audits pass. Hardware remains untested.

`j614s-gravity-nvme-objects.json` qualifies actual RTKit/SART AArch64 objects at
source75667 with exact reviewed config and compiled binding checks. Its
`--platform-only` qualification does not compile or claim GPU/module linking;
that source still carries the independent MMIO assertion issue. No runtime
storage claim follows, and J614s ANS remains explicitly fail-closed. The helper
now rejects unresolved Rust build assertions immediately after GPU compilation;
22 host regressions pass, including that guard and the actual failed object.


`gravity-dcp-prime-object-result.json` records the ownership callback compiling
against real kernel headers in the full Apple DRM composite, including all
12.3/13.3/26.6 translation units. Combined full-module verification remains a
separate step; this does not establish cross-device zero-copy or hardware use.

The two host sanitizer harnesses now make findings fatal with
`-fno-sanitize-recover=all` and require empty stderr for every executed variant.
Their results were rerun under that policy. `sanitizer-fatal-probe.json` verifies
that deliberately injected signed overflow and heap use-after-free both terminate
nonzero under GCC and Clang with the same flags. Earlier host result records did not establish that UBSan findings were fatal.
The rerun replaces those records with enforced failure rules and empty stderr.


`j614s-gravity-ans-staged-objects.json` records the staged source9d9 ANS object
compiling as ELF64 AArch64 with the exact reviewed config and 3,174 binding
layout blocks / 16,413 field-offset checks. This is parser/type/code-generation
qualification of the selected object; staged callbacks remain behind the early
J614s refusal. It establishes no admitted storage probe, devres quarantine or
hardware operation. `baseline-preservation-final.json` confirms the original
source fingerprint, known Image and original config remain unchanged after the
new builds. This lane performed no physical target access or deployment.
