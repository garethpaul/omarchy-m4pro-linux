# Consolidated J614s Gravity source: first immutable checkpoint

**PARTIAL. Compile-only source candidate; hardware UNTESTED and deployment
prohibited.** This checkpoint preserves the known-qualified m1n1 boot object,
RAM payload, macOS/Recovery/1TR, storage and existing source worktrees. It creates
source commits, patch exports and a normalized build configuration only.

The new kernel branch is `agent/gravity-j614s`, based on Gravity envelope and
mailbox dependency commit `b442be4b28f3720daff6c5f26fe8b1ab3aef28f1`.
Checkpoint HEAD is `a5a5ba8f56c9ab9192bbe9d3e9ae006cdcca661f`.
Its full, per-file origin/comparison digests, unchanged framework tree IDs and
per-component decisions are in `port-ledger.json`; four numbered patches
reproduce the source commits. They use zero context to preserve source whitespace
without format-patch context being mistaken for new-file whitespace; apply with
`git apply --unidiff-zero` in series order to the exact recorded base.
`evidence/patch-roundtrip.json` records replay onto actual base file blobs and
byte-for-byte agreement with every ledger file. No newer general driver was overwritten wholesale.

| Component | Source decision | Qualification of this checkpoint |
| --- | --- | --- |
| CPU / ordinary WFI | `c44269c50`: carry tested `1d78` saved-register assembly, FP/SIMD flush, static key and automatic post-bootargs WFxT override; reuse Gravity's existing Donan CPU IDs | PARTIAL: actual code ported; compile and hardware qualification separate |
| USB2 | `dc28adf00`: add unchanged narrow inherited USB1 device-state admission and separately opt-in USB0/USB2 host diagnostic; preserve general Gravity ATC/DPTX | UNTESTED on this source; prior gadget observation does not qualify full Type-C |
| MTP / trackpad reset | `dc28adf00`: add board-gated non-ring method2/reset ownership and measured 4-byte gp1c/pin28 reset; retain Gravity T8132 ring code | PARTIAL: ported; physical input and smoothness UNTESTED |
| Battery | `dc28adf00`: retain Gravity telemetry, suppress all charging-control/probe-reset writes on J614s, expose setters as unwritable | UNTESTED on this source; prior read-only test42 remains separate |
| NVMe / ANS | `dc28adf00`: explicitly refuse J614s before allocation/power/MMIO/reset/RTKit rather than copy a match entry | BLOCKED: Gravity lacks Aurora's inherited RTKit/adopted-system-endpoint and firmware-memory ownership path |
| G16S bootstrap | `c87d7552a`: exact f93/0fb crash-latched transport-only driver plus read-only RTKit version accessor | UNTESTED on this source; prior test56 proves only old startup/quiesce |
| Full GPU / DCP | Retain Gravity source and existing compatible/firmware gates; both modules requested, no new T6040 aliases/DT activation | BLOCKED: native T6040 INIT/body/job and display handoff unqualified; existing DCP modular direct-map symbol gap pending separate fix |
| Reset / watchdog | Existing Gravity framework retained unchanged | UNTESTED; ordinary boot/reboot and independent recovery still required |
| Rust bindings | `a5a5ba8f5`: commit assertion-enabling overlay, use corrected qualified bindgen | PARTIAL: source invariant verified; actual AArch64 build results supplied by build lane |

Old evidence is linked from `../qualification/STATUS.md` and remains scoped to
its named test. In particular, f93's read-only NVMe pass does **not** transfer to
this checkpoint. NVMe's first branch inside `apple_nvme_alloc()` returns
`-EOPNOTSUPP` for J614s. Probe calls that allocator before reset scheduling; no
power-domain attachment, MMIO access, reset acquisition or RTKit wake is reached.
The next storage task is an actual inherited-state/ownership port on a separate
branch, with host causal regression tests before any future hardware test.

No new M4 DTS nodes are introduced. The measured M2/T8112, M3/T8122 and live
T6040 node comparison remains `../qualification/adt-node-comparison.json`; a
new runtime handoff must validate per-client ownership before any driver
activation. Static PHY/ASC register apertures in the old narrow diagnostics are
retained; **no runtime firmware physical address, raw ADT or vendor blob** is
exported. The bootstrap receives its bounded DATA resource from a future loader;
this checkpoint provides no such DT or loader. It sends no application INIT and
registers no render device. Fixed-address early framebuffer diagnostics from
archival867 are excluded; `head.S` and serial build plumbing are unchanged from
Gravity. Full GPU/DCP driver sources and firmware gates are also unchanged.

## Exact build input and review

`configs/j614s-gravity-candidate.config` SHA256:
`6c5aba7745d918c528300c5a395fcd7db0c2b718acda7d1467af2816a8d56516`.
The configuration starts from the qualified f93 profile and requests the dormant
Gravity GPU and DCP modules, backlight class support, embedded config and a
unique `-j614s-gravity-candidate` release. `config-request.diff` records those
requests. `config-normalization.diff` records every Kconfig change under the
same pinned compiler/Rust/bindgen tools as the build lane, with no inherited
compiler flags. It does not silently turn off DCP to get a successful link.

Kconfig removes symbols absent from this Gravity tree (Apple MCC/PMC/CIO reset,
Rust Apple mailbox selector, optional serial DockChannel and MTP haptic option),
adds DCP's DMA/video helpers and optional panel/backlight menus, and keeps the
required actual C RTKit/mailbox providers built in. These differences are
source-tree/configuration differences, not hardware qualifications. All 12
actual cores fit `NR_CPUS=16`; SMP and 16KiB pages remain enabled, and CMDLINE is
empty. No `idle=nop`, `arm64.nowfxt`, `maxcpus=1` or speed-clamping workaround is
introduced. Formal cpuidle/cpufreq remain disabled as in the prior profile and
are unimplemented bring-up work, distinct from ordinary scheduler WFI.

```sh
python3 integration/validate_candidate.py --source /path/to/gravity-j614s
J614S_CANDIDATE_SOURCE=/path/to/gravity-j614s \
  python3 -m unittest discover -s integration -p 'test_*.py' -v
```

The validator binds the clean source commit, per-file hashes and exact config,
checks CPU wait ordering and pre-hardware NVMe refusal, rejects full GPU/DCP
board aliases and disabled binding assertions, and always reports hardware as
UNTESTED/deployment false. Twelve host regression tests reject changed source,
config, single-core/workaround flags, aliases, reordered WFxT/SIMD handling,
pre-refusal MMIO/reset/wake calls and attempts to call bootstrap rendering.
These are source/config invariant checks, not driver execution or hardware tests.
`evidence/source-config-check.json`, `evidence/config.json` and
`evidence/unit-tests.txt` retain their actual output.

The build lane owns full Image/modules qualification with this exact commit and
configuration, including actual binding layout assertions and module ELF/release
checks. The known DCP modular failure remains visible until its separately
reviewed no-map-only module fix is integrated; switching it built-in or exporting
private architecture helpers to mask the failure is excluded. No module is
loaded, no new firmware path is activated, and no payload is deployed here.

## Follow-up checkpoint: dormant modular DCP

The original source/config above remain immutable. A separate candidate branch
`agent/gravity-j614s-dcp` has HEAD
`82b931a908746280edb4120fab78a3a060fc343e`, with the same exact configuration.
`dcp-port-ledger.json` extends the origins and per-file comparisons;
`patches-dcp/` contains patches5–7, applied after the original four with
`--unidiff-zero`. All seven patches replay onto the base file blobs and match
all ledger files (`evidence/dcp-patch-roundtrip.json`).

The additional source commits are:

- `53ceaf8ba` from graphics `8e27e3edbf57903da4d62ab52f3b77df23801772`: validate
  IOMFB callback envelopes before shared-buffer access.
- `f43b09c30` from graphics `8c93f2c2576b4d53d11c064f8cbd5a45095fa71d`: validate
  typed callback extents for the selected26.6 ABI.
- `82b931a90` from build lane `124fd0633bb8932bbf68845ecbe8a5ffc53dfb43`:
  require a validated existing no-map scanout pool for modular DCP, before
  component binding. Preserve built-in direct-map fallback and restoration;
  export no private architecture helpers and create no new DART mapping.

**PARTIAL:** exact source/config invariants and patch replay pass; the build
lane is qualifying all actual CPU/peripheral/bootstrap/GPU/DCP objects and full
Image/modules. Its build result is pending here. **BLOCKED:** native T6040 DCP
still needs a measured, valid bootloader no-map/DART handoff and firmware ABI;
this source supplies neither. Driver matches and firmware gates remain intact,
no T6040 alias is added, no module is loaded and no target operation occurs.
The earlier NVMe refusal remains in place with storage BLOCKED.

```sh
python3 integration/validate_candidate.py --source /path/to/gravity-j614s-dcp \
  --ledger integration/dcp-port-ledger.json
```

The first targeted strict compile of82b9 **failed** on DockChannel HID's new
error cleanup: Gravity's interface field was `const struct device_node *`,
while `of_node_put()` takes the mutable owned reference returned by
`of_get_child_by_name()`. Nine other requested platform objects compiled; a
failed compile is not a full build pass. Source commit
`ccb0647c779ec32f2549708ee3b57510700aaabb` corrects that field's ownership type
without a cast or warning suppression. Patch8 and
`dcp-fixed-port-ledger.json` record this next immutable checkpoint; its config
is unchanged. `evidence/dcp-fixed-source-config-check.json` passes source/config
invariants only. The build lane retains the failure and is compiling a separate
snapshot atccb0, so later branch changes cannot alter its build inputs.
