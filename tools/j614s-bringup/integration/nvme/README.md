# NVMe inherited-session prerequisites on a separate branch

**PARTIAL. Actual SART/RTKit source is ported and host-tested; the ANS adoption
path is not wired yet. J614s NVMe probe remains BLOCKED by its early refusal.**
No target access, firmware execution, MMIO, reset, deployment or disk operation
is part of this lane. The frozen consolidated/DCP compile checkpoints remain
separate. The later DCP PRIME guard is deliberately not mixed into this branch.

The new source branch is `agent/gravity-j614s-nvme`. Its current immutable
prerequisite checkpoint is `75667cb3d42683108db115c5f94b46d4df51a244`.
`prerequisite-ledger.json` records the three source commits and per-file digests;
`patches/` reproduces them after the eight consolidated patches, using
`git apply --unidiff-zero`. The branch-local MTP fix commit has the identical
full tree as `ccb0647c779ec32f2549708ee3b57510700aaabb`; only history differs.

Comparison with f93 found a 1082-line-added/181-line-removed NVMe driver delta
and a 326-line-added/231-line-removed RTKit delta. These contain newer platform
families, teardown/quarantine and reset/recovery work as well as the relevant
inheritance path. Copying either entire driver would erase Gravity's distinct
endpoint7 and G16 controls. This checkpoint instead ports concrete prerequisites:

| Component | Actual source change | Evidence and remaining limit |
| --- | --- | --- |
| Protected SART range ownership | `cf7658de5`: exact f93 predicate, requiring a single protected allow entry covering a whole nonzero, nonoverflowing range | WORKS in 274 actual-function host cases, ASan/UBSan; RAM reservation/coherency not established by this predicate |
| Pre-RX inherited RTKit state | `9fa769e37`: add `apple_rtkit_init_adopted()`, prime known system endpoints and ON state before publishing mailbox RX; send no handshake/application INIT | WORKS in selected-function host fake with an immediate inherited log at mailbox start; real concurrency/hardware UNTESTED |
| Unknown inherited log geometry | ACK syslog without reading its unknown ring; unknown crash without a retained buffer latches failure rather than fabricating a log mapping | Syslog poison-pointer test passes; crash path hardware UNTESTED; a confirmed new session or explicitly validated reused geometry is still needed |
| Mailbox callback ownership | Claim under existing RX lock, reject another owner, detach before draining, release cookie after teardown | Host tests cover existing owner, failed allocation/workqueue/start and successful/free/retain paths; no concurrency proof |
| Live-buffer ownership | Keep identical requests; reject changed live geometry before another setup; setup failure cannot replace a live descriptor | Causal real-source baseline failure reproduced, fixed invariant exits1 before patch and passes after patch |
| Inherited normal-RAM reads | Add `needs_dma_sync` and retain f93 CPU/device streaming-cache synchronization; never apply it to iomem | Host fake checks both synchronization calls and clearing on safe retirement; real DMA coherency UNTESTED |
| Failed firmware shutdown | `apple_rtkit_free_retaining_buffers()` detaches/drains callbacks but retains every DMA-visible mapping until reboot | Host fake proves no destroy callback; caller lifetime/quarantine and no-reprobe integration still required |
| Existing Gravity controls | Preserve endpoint-list `apple_rtkit_adopt_running(rtk,endpoints,count)`, boot-AP/early-crashlog APIs, endpoint7 reply and G16 crash reply behavior | Old public signatures retained; host tests check endpoint7 and early-crash reply. No blanket RTKit replacement |
| Strict endpoint iteration | `75667cb3d`: use `size_t` for actual endpoint-array iteration | Fixes strict host signedness diagnostic without suppressing a warning |

No new protocol measurement is invented: a preinitialized inherited instance
keeps protocol version0 until a real HELLO is observed. This differs from
Gravity's preexisting endpoint-list adoption helper, whose public behavior is
retained. Unknown inherited syslog remains ACK-only until confirmed reinit or
explicit reused geometry; a fresh-looking INIT alone is not used to validate an
unobserved inherited ring. Existing shmem callbacks were checked: they retain
owned mapping objects in `private`, not the temporary descriptor pointer.

## Actual-source regressions

The scripts extract unchanged functions from immutable source commits and
compile them against fake host Linux/mailbox/DMA APIs. They do not reimplement
the selected source functions. Candidate type definitions are extracted too;
this is not an ARM layout or locking proof. The build lane is separately asked
to compile the complete RTKit/SART units and real generated AArch64 bindings.

```sh
python3 integration/nvme/test_sart_source.py --source /path/to/kernel \
  --commit cf7658de5dce4d89d5b8014df204cbbd77edb56e --output NEW_PRIVATE_DIR
python3 integration/nvme/test_rtkit_source.py --source /path/to/kernel \
  --candidate 75667cb3d42683108db115c5f94b46d4df51a244 --output NEW_PRIVATE_DIR
```

Both use warnings as errors, AddressSanitizer and fatal UndefinedBehaviorSanitizer.
Assertions remain enabled. No driver check or compiler diagnostic is disabled.
The baseline expected-bug run is separate from its fixed-invariant run; the latter
must fail specifically because a changed live request replaced the descriptor.
`rtkit-host-result.json` records that actual exit1, then the candidate's pass.
`sart-host-result.json` records all274 cases. Generated source, executable and
raw compiler logs remain private scratch artifacts.

## Remaining implementation, in dependency order

1. Port and host-test ANS inherited-session admission against actual measured
   CPU_RUN, BOOT_STATUS, CC/CSTS and explicit disabled-handoff state. No generic
   T8132 compatible alias or reset-based fallback.
2. Port borrowed-buffer validation: protected SART coverage **and** every page
   reserved, System RAM/linear-map coverage, cache alignment, no overflow,
   identity streaming DMA mapping and retained device context. A property alone
   cannot prove ownership; a bounce mapping must be rejected without syncing
   or copying into the live firmware allocation.
3. Close crash-during-initialization scheduling, lifetime/quarantine and unsafe
   remove/reprobe paths. Only then connect adopted RTKit before any controller
   disable, queue/NVMMU programming or other write. Keep unsupported states
   fail closed.
4. Compile exact immutable source/config, then require a separately supervised
   hardware test with independent recovery, read-only block guard and old
   qualified payload retained. Host tests and compilation never qualify writes,
   persistent storage or automatic boot.

## Staged ANS admission and borrowed buffers

Source checkpoint `9d9f94a00b6e4408cbfaf5051fc2caeb792f7260` adds the actual f93
admission and borrowed-buffer predicates/callbacks to Gravity's driver;
`borrowed-buffer-ledger.json` and patch4 record the delta. The only new admission
hook is behind the still-refused J614s board branch. Existing profiles retain
non-inherited allocation behavior. **The initial J614s refusal remains active.**
There is no controller write, new match alias, adopted initializer call, queue
handoff or reset activation in this checkpoint.

`nvme-host-result.json` records actual selected-source ASan/UBSan checks for:

- RUN/BOOT_STATUS/CC/CSTS combinations and the exact disabled-handoff contract;
- protected SART coverage plus complete System RAM and every-page reserved,
  PFN-valid, non-highmem and valid-linear-map coverage;
- cache alignment and overflow refusal before mapping;
- object/remap/DMA setup failures, identity success and nonidentity bounce
  rejection with SKIP_CPU_SYNC and no device synchronization or copy-back;
- independent mapping device references, including destruction with no ANV
  cookie, plus unchanged coherent allocation/error cleanup.

The output counts65597 checks;65536 are individual poison-buffer bytes checked
unchanged after bounce rejection, not65536 distinct hardware scenarios. All
MMIO, RAM, cache and DMA operations in these tests are fakes. Mapping
`get_device()` preserves its device context; it **does not retain ANV, queues,
requests, devres storage or controller ownership**. The separate kref/devres
reference and quarantine/no-reprobe port is still required before removing the
refusal. A device reference alone is never treated as that pin.

The real mailbox start was also inspected before considering speculative
failure cleanup (`mailbox-start-review.json`). Its only error occurs during
runtime-PM resume, before FIFO access or enabling the initially disabled IRQ.
After IRQ enable it returns0 without another error point; already-active start
also returns0. Thus this fresh failed-start path itself does not queue RX/buffer
work. Concurrent direct polling remains an explicit caller-exclusion issue,
not a proven hardware or locking guarantee. No cleanup behavior was changed
based solely on a hypothetical late start failure.

## Staged controller lifetime

Checkpoint `8acc4f6f7` replaces the controller's devres allocation with independent
controller/devres references and explicit queue/pool cleanup. Quarantine pins
outstanding DMA resources, tagsets, module callbacks and power-domain runtime
references; a physical-controller list refuses reprobe. The constructor's first
J614s refusal remains active. This is a staged prerequisite, not admitted storage.
The prior f93 behavior is reused narrowly; existing non-inherited disable and
RTKit teardown behavior remain separate.

`lifetime-host-result.json` records **58 checks across 17 host scenarios** using
selected actual source functions with ASan/UBSan and warnings as errors. They
exercise both reference-release orders, constructor failures, partial queue
allocation/action failures, ordinary cleanup and retained queue/pool/tag owners.
The fakes do not establish Linux devres concurrency, firmware DMA safety or a
working controller. Full timeout/recovery/reset/adoption integration remains in
progress; no target access or deployment has occurred.

## Complete strict source admission checkpoint

The newer [admission checkpoint](admission/README.md) supersedes the staged
refusal for the exact RAM-diagnostic profile only. It records the full source
chain, real selected-source host tests, reproduced/fixed failures, ordering
checks and a byte-exact 21-patch replay. This is PARTIAL source implementation;
new-kernel NVMe hardware and persistent installation remain unqualified. Earlier
staged proofs above remain historical and do not claim current hardware support.
