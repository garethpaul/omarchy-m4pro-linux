# Offline native RAM diagnostic DT template

**PARTIAL:** 12-CPU synthetic fixtures and an actual USB71 session template compile and pass host validation.
**BLOCKED for frozen input03:** its secondary slots are not idle and WFE is
false, so generation refuses before creating an output directory.
**UNTESTED:** execution of the newly pinned DART v2 kernel. The preceding8f2 pair reached diagnostic Linux in supervised boot01, failed USB configuration, and returned automatically once; that result does not qualify this candidate. See [boot01](../../qualification/supervised-ram-boot-01.json) and [new preparation](../../qualification/supervised-ram-02-preparation.json).
No target access, staging, boot or publication is performed by these tools.

`generate.py` consumes a private observer capture, explicit expected capture /
USB-session / observer / bootargs / ADT pins, exact source checkouts and existing
qualified artifacts. It has no serial, proxy, sysfs or network API. A capture is
an observation, not authorization or proof that state is still current.

## Profile and source binding

`source-profile-v1.json` and the two reviewed `.dts.in` files are versioned and
hash-bound by the generator. No arbitrary previous DTS or caller bootargs are
accepted. The profile binds:

- Kernel source `5cbc8c64748b480f7da4dac87b92450b80124594`, Image `09a52425…db8e8`,
  config `6c5aba…6516`, and ten relevant driver/platform source hashes.
- Reproduced loader source `6249e0ecdb7677b6afa01989c23344962253e954` and flat
  binary `2309dfbb…21a0e00`; the exact native helper source is checked.
- Observer source `fce3a310…55d7`, resident helper `fb31c765…f3afb` and its exact
  local ELF. Flattening the ELF must reproduce that resident binary.
- The artifact verifier's Python source hash. It executes only those checked
  source bytes in a fresh module, ignoring timestamp-valid `.pyc` files.

The profile retains only the old measured test52 minimal topology: all twelve
ADT CPU identities, AIC3, USB1 peripheral mode with its inherited USB2 PHY and
two DARTs, watchdog, timer and simple framebuffer. Optional storage adds only
the exact J614s diagnostic NVMe, SART and four-interrupt mailbox resources.
Host USB, SMC, MTP, GPU and DCP nodes and firmware payload addresses are omitted.
No single-core flags, idle overrides, `j614sfb`, or early-console override remain.

The pinned configuration has SMP/16 CPU capacity, AIC, architectural timer,
DART, inherited USB2 PHY, DWC3/configfs, simpledrm, watchdog, SART and mailbox
built in. NVMe is modular; an independently verified initramfs must provide the
matching modules and probe policy. A DT alone does not provide userspace.

`comparison-index.json` narrows the existing 448-node runtime-versus-static
M2/T8112, M3/T8122 and M4 comparison to these twenty ADT nodes. It preserves
property-name differences and original comparison hashes without raw ADT data.
Its runtime capture is historical, not the current input03 ADT hash.

| Block | Reuse evidence and uncertainty |
| --- | --- |
| CPUs | Historical live ADT has four sawtooth and eight everest identities. M3 spin-table framework is reused; M2 CPU identities differ. The new kernel and template remain hardware untested. |
| AIC | M4 uses the measured AIC3 topology and M3-compatible driver. M2 is AIC2; its offsets are not substituted. Complete T6040 power/clock graph remains absent. |
| USB1 / DART | Historical ADT comparison and test52 topology support this narrow inherited path. The pinned PHY driver checks exact J614s resources and inherited state. This does not qualify current PHY state, SuperSpeed, Type-C roles or other ports. |
| Watchdog / timer | Existing frameworks and measured resource profile are retained. Linux probe can reprogram the watchdog; the DT timeout is not recovery proof. |
| ANS / SART / mailbox | Exact resources and provider links match the new strict source checks. M2/M3 structures have measured differences. Firmware-buffer ownership/cache state and current runtime admission remain independently unqualified. |

## Capture ownership checks

All dynamic video and release addresses come from the supplied capture. The
resident base, end, spin-table offset/size and every `cpu * 64 + 16` release
pointer must match the pinned resident ELF. No release pointer is taken from
the child loader's separate table. All eleven secondary slots must already have
matching MPIDRs, nonzero resident flags, zero targets/arguments, and WFE mode.
The program never starts cores or changes WFE.

Boot-video fields must satisfy the exact6249 guard and checked multiplication /
alignment / extent rules. The framebuffer must lie within separately observed
physical RAM and outside both usable allocation RAM and the resident. Physical
RAM and usable RAM are different envelopes; the framebuffer is never exposed
as ordinary usable memory to make a check pass. The physical-base alignment and
24-GiB physical size are part of this J614s profile.

Expected hashes bind the capture bytes before parsing and are checked again
before/after compilation. They cannot establish live coherency, freshness,
authenticity or permission. Primary-side rechecks are still required later.
The generator does not alter captures02/03 or derive a passing fixture by
editing either. `synthetic-capture.json` was constructed independently from
source constants, invented locations, session99999 and invented evidence hashes.
Positive fixture outputs say **SYNTHETIC ONLY** and **UNRELOCATED TEMPLATE**.

## Template versus runtime FDT

The output is deliberately **UNRELOCATED**, never a final runtime FDT:

- `/memory@0/reg` is the 16-byte placeholder `<0 0 1 0>`.
- Chosen initrd start/end are separate eight-byte zero placeholders.
- The only reserved-memory children are `retention-control@3fe00000` and
  `ramoops@3ff00000`, with the exact sizes/property shapes in the profile.
- Loader6249 later selects a 4-GiB allocation above its heap, excluding live ADT
  carveouts; copies the kernel/initrd/DT; patches memory and initrd addresses;
  patches retention to end−2MiB/16KiB and ramoops to end−1MiB/1MiB.
- Initrd and FDT copy offsets are 32MiB and 40MiB. The FDT must be 40..65536
  bytes with an exact header total size. The loader does not rename unit-address
  node names when patching their `reg` values.

The minimal profile deliberately excludes the loader's optional MTP reservation
path. No firmware pointers are transplanted. Future child staging placement,
loader allocation, carveout ownership and cross-stage state still need separate
validation. A template must never be executed directly or described as the
final runtime FDT.

## Validation and regression controls

DTC runs with checks enabled. Any compiler stderr or nonzero exit refuses
qualification and retains source/stdout/stderr plus failure metadata privately.
`fdtget` checks nodes, resources, CPU/release properties, compatibles, provider
links, interrupts and patch shapes. Those semantic checks are **not** claimed
as an exhaustive generic DT validator. The validator also renders the exact
expected profile/capture/nonce and compiles it fresh, requiring byte-for-byte
DTB equality. Thus arbitrary extra or disabled properties are refused.
`validator-before.json` preserves the real earlier gap: semantic-only checking
incorrectly accepted a disabled USB node and changed CPU address-cell count.

`test-result.json` records all controls, including unchanged input03 refusal,
synthetic minimal/ANS compilation, stale/session/hash/type/ownership negatives,
extra nodes/properties, changed resources/interrupts/bootargs, actual compiler
warning/error retention and a timestamp-valid forged Python-cache control.
That cache control first reproduces the old loader bypassing verification even
though source bytes hash correctly; the candidate executes the checked source
and rejects the missing bundle. External helper files are never edited.

## Read-only API for the separate bundle lane

Load this generator from verified source bytes using `compile` into a fresh
module; do not use a cache-sensitive import and assume a source hash binds code.
All filesystem arguments below are `pathlib.Path` objects.

- `profile()` validates the fixed profile, templates and comparison index.
- `verify_inputs(namespace, profile)` is the preferred complete input gate.
  Namespace fields are `capture`, `expected_capture_sha256`,
  `expected_usb_session`, `expected_observer_sha256`, `expected_bootargs_sha256`,
  `expected_adt_sha256`, `synthetic_fixture`, `observer_source`, `resident_source`,
  `loader_source`, `loader_binary`, `kernel_source`, `kernel_bundle`.
  It returns the parsed capture, which contains **PRIVATE addresses**.
- `verify_dtb(path, capture, profile, nonce, storage_bool, diagnostic_dir=None)`
  checks exact fresh compilation plus the diagnostic semantic checks. It does
  not relocate the tree or accept arbitrary additional nodes/properties.
- A `CompilerDiagnostics` exception retains `stdout`, `stderr`, `returncode`.
  Bundle callers must preserve those privately; `diagnostic_dir` additionally
  writes reference compiler logs. No warning is disabled to get a pass.

The bundle lane must recheck capture/source/artifact stability itself around
assembly. An expected hash and USB session are caller-supplied pins, not an
excuse to mutate a nonqualifying capture. Input03 must still refuse end to end.

Run all host controls from the tooling repository, using the existing workspace
layout; this reads the original private capture and creates only synthetic DTs
in temporary host directories:

```sh
python3 infra/native-dt/test_generator.py \
  --observer-source ../overnight-bringup/recovery/read_resident_cpus.py \
  --resident-source ../m1n1 \
  --loader-source ../overnight-native-loader-remap-source-01 \
  --loader-binary ../overnight-native-loader-remap-source-01/build/m1n1.bin \
  --kernel-source ../overnight-infra-gravity-combined-source-03 \
  --kernel-bundle ../overnight-infra-gravity-combined-build-02 \
  --actual-capture ../hardware-private/resident-cpu-readonly-03.json \
  --output ../native-dt-next-host-result.json
```
