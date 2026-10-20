# J614s G16S graphics enablement

These changes implement a read-only G16S INIT decoder and a crash-state fix for
an already qualified RTKit bootstrap driver. They do not implement rendering.
The physical machine is Mac16,8 / J614s / T6040. This lane did not control it.

| Item | Status | Evidence |
| --- | --- | --- |
| Existing RTKit bootstrap and shutdown | WORKS for that earlier test | Primary lane's native tests 55 and 56; base kernel commit `4ff8816df8c4bc81b1652eca17fc8c0e9e1928cc` |
| Crash racing with readiness publication | PARTIAL: driver fix compiled; runtime untested | Kernel commit `0fb65dbd66f9b91a43096ecbabd52b81f73bea5c`; [actual-driver regression](DRIVER-REGRESSION.md); `g16-bootstrap-crash-state.patch`; `kernel-object-result.json` records the AArch64 object; checkpatch reports no errors, warnings or checks on the diff |
| Exact-build root-envelope decoder | WORKS offline; runtime capture untested | GCC and Clang sanitizer tests in `test-results.json`; `g16s_abi.h` |
| Read-only three-level UAT walker | WORKS on synthetic replay; M4 mappings untested | Synthetic translated page, canonical-address, out-of-range, malformed-descriptor and callback-failure checks |
| Gravity G16 root reuse unchanged | BLOCKED by exact interface mismatch | Compiled upstream encoder reproduced rejection; `gravity-root-result.json` |
| Application initialization / PPL handshake | BLOCKED by missing qualified G16S graph | No APP INIT sent. Earlier primary-lane measurement left firmware magic zero before APP INIT; this does not establish handshake failure after INIT |
| AGX rendering / GPU job submission | UNTESTED and unimplemented here | No render node or Mesa compatibility gate changed |
| DCP / native modesetting | UNTESTED here | This lane makes no display-driver claims |

## Build and replay

From this repository root:

```sh
make -C graphics all test
UBSAN_OPTIONS=halt_on_error=1 make -C graphics test CC=clang BUILD=build-clang CFLAGS='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer'
graphics/build/test_g16s_abi --emit-fixture > graphics/build/synthetic-root.bin
graphics/build/g16s-inspect graphics/build/synthetic-root.bin
```

`g16s-inspect` accepts exactly one 200-byte root. It opens ordinary files only,
follows no pointers and emits decoded metadata with `hardware_validated=false`.
`g16s_abi.h` has no allocator or write operation; its bounded walker accepts a
read callback and explicit physical RAM ranges. Every table must be aligned,
inside the encoded physical-address width and inside a complete approved
16-KiB RAM extent before the callback runs. Block PTEs are explicitly unsupported.
Unknown high PTE attributes remain in the walk result. Physical address bits
outside the encoded output width are rejected rather than truncated.

Caller responsibilities: obtain a coherent capture, choose the correct root
explicitly, use RAM-only allowlists established independently from this machine's
ADT, and treat error returns as failure. This is not an authorization to read
arbitrary target memory. Do not use the legacy m1n1 UAT constructor merely to
inspect G16: that constructor allocates and can modify published tables.

The exported patch uses zero context. Apply only to the recorded base commit with
`git apply --unidiff-zero`; the normal-context kernel commit is preferred for
integration. This avoids storing patch context whitespace as source-code changes
in this evidence repository. No kernel validation was disabled.

The crash-state patch compiled against the isolated clean kernel source using
the qualified Rust/bindgen toolchain. This is object-only evidence, not a linked
module, booted kernel or induced-firmware-crash test. The only normalized config
change removed a diagnostic PHY option absent from the clean source tree.

The header can use Linux integer types when included with `__KERNEL__`; user-space
tests exercise the same parsing and bounds logic. This is not a claim that a
G16 kernel initialization graph has been built or accepted by firmware.

## Source comparison before reuse

The primary's captured runtime ADT and its same-build M2/M3 baselines show:

| Block | M2 T8112 | M3 T8122 | M4 Pro T6040 | Reuse decision |
| --- | --- | --- | --- | --- |
| SGX compatibility | gpu,t8112 | gpu,t8122 | gpu,t6040 | Different identity/profile; no automatic match |
| GFX ASC | ascwrap-v4 | ascwrap-v6 | ascwrap-v6 | Existing mailbox transport reused only in earlier measured bootstrap |
| ASC aperture | 0x6c000 | 0x6c000 | 0x88000 | Do not reserve the old span blindly |
| ASC second region | 8 bytes | 8 bytes | 0x60000 | Changed; keep firmware extent checks |
| GFX mapper compatibility | iommu-mapper,gfx | iommu-mapper,gfx | iommu-mapper,gfx | Shared string is insufficient to establish unchanged UAT behavior |

Those facts come from the local private `apple-device-trees/graphics-comparison.json`.
Raw ADTs contain keys and are excluded. The decoder supports internally consistent
16-KiB, three-level descriptors rather than hardcoding an M2/M3 address width.
The synthetic fixture uses IAS/OAS 42, matching Gravity's G16 source; this width
is not asserted to have been observed in an actual J614s APP INIT capture.

Exact 25G83 G16S B firmware startup at VM address `0xfffffc000002f204`:

- receives endpoint 0x20 and checks the masked command type against 0x81;
- reconstructs the high firmware VA with `0xfffff00000000000`;
- requires interface `[04c0, 0396, a322, 0c8a]`;
- copies 0xc8 bytes and requires the 32-bit marker at root offset 0x2c nonzero.

The exact inspected GFX payload SHA-256 is
`22f7e4f9d87e6085be91d2872cd39870c247f95f366a8b1386f8f91e047a73a1`.
Private disassembly and binaries are not included. Fields at +0xb8/+0xc0 are kept
opaque. G17's secondary root has the same size, but its dual-coprocessor meanings
have not been established on the single G16S ASC.

## Actual upstream encoder check

[Gravity's kernel](https://github.com/GravityLinux/linux/tree/4fc326f6c25ccceb7515e2635c22e01fde5d3bac/drivers/gpu/drm/asahi)
has complete experimental G16 source. Its g16.rs firmware guard accepts
mBoot-18000.161.10, while its g16_fw.rs encoder emits the older interface
`[04b8, 8392, c357, 0c89]`. This mismatch was reproduced by compiling and running
that exact upstream RootPointers encoder, then passing its actual output to the
new validator. No source constants were changed to make it pass.

```sh
python3 graphics/check-gravity-root.py --source /path/to/checked-out/gravity-linux --output graphics/build/gravity --inspector graphics/build/g16s-inspect
```

The helper requires the reviewed source commit and unmodified encoder files.
It neither downloads nor executes a kernel. The upstream pure Rust serializer
runs on the development host. GPL notices in the upstream source are preserved;
no upstream source is redistributed here.

The public J713 Air source is useful reference, not evidence for T6040. Its
[GPU source packet](https://github.com/Kb2uka/Omarchy-M4-Native/releases/tag/v0.1.0-alpha.1)
contains four module changes and depends on a separate kernel-controller source.
The Air has G16G rather than this machine's G16S two-cluster, 16-enabled-core GPU.
Changing a firmware version or GPU compatibility gate alone does not port it.

## Hypothesis ledger and next probe

1. **Confirmed offline:** Gravity's unchanged root is rejected by the exact G16S
   interface predicate. Its graph cannot be activated as-is.
2. **Open:** newer G16S firmware may retain some Gravity main-config offsets while
   changing hardware/power bundle fields. Compare exact G16S producer and consumer
   offsets before constructing a candidate; do not simply replace the version.
3. **Open:** zero PPL firmware magic before APP INIT may be deferred initialization.
   It is not evidence that the post-INIT handshake is impossible.
4. **Implemented, hardware untested:** a crash callback can precede probe's final
   ready store. The atomic state transition makes CRASHED terminal for that probe
   instance and prevents stop from erasing it. It adds no reset/reprobe automation.

Next hardware probe belongs to the primary lane after independent recovery is
verified: capture a real endpoint-0x20 INIT message, its 0xc8-byte root and the
minimal UAT pages needed to translate it, with a read-only mailbox observation
hook. Check firmware identity and physical ranges against the live ADT, record
all pre/post state, then run this offline validator. Do not send an unqualified
INIT, mutate roots, change boot policy, or boot a protected volume just to obtain
this sample. If a suitable capture requires an additional protected-volume boot,
that remains authorization-gated; static producer/consumer comparison can continue.

The next application-layout step is implemented in [MAIN-CONFIG.md](MAIN-CONFIG.md):
known MainConfig fields, actual upstream encoded pointer mismatches, and a staged
read-only plan for the first hardware-data access. Its passing replay does not
qualify a firmware graph or permit application INIT.
