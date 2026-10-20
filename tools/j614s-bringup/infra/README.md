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
