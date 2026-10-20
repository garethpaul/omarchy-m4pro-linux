# Inherited ANS memory/cache handoff: offline finding and proposal

**BLOCKED: borrowed-buffer mapping qualification.** This does not establish that
the new NVMe probe must fail. An inherited session may need only ACKs for logs,
or may request fresh host buffers; neither requires Linux to read an excluded
predecessor buffer. The driver continues to refuse any borrowed span that lacks
its existing ownership/cache prerequisites.

`cached-source-evidence.json` binds the saved sources, old manifests and logs by
hash without exporting firmware or runtime addresses. `audit_cached_handoff.py`
only reads those files and can reproduce the address-free evidence. No target,
loader, known-qualified binary, kernel, DT or boot object was modified.

## What the saved evidence establishes

- The current qualified base binary matches both saved test 52/test 56 manifest
  digests. This audit does not independently bind that binary to a source build.
- `j614s_native_run()` replaces `memory.reg` with exactly its newly owned 4 GiB.
  Its reservation allowlist handles ramoops, retention control and MTP; it does
  not add the predecessor allocation prefix as a mapped/reserved RAM bank.
- Both saved boot logs report 4 GiB total RAM and three reservation nodes. Their
  pre-handoff DTs describe one RAM bank. The MTP reservation is explicitly
  `no-map` and is not an ANS borrowed-memory contract.
- The saved test56 archival Apple NVMe driver exactly matches its source
  manifest and contains the same strict inherited-buffer predicate. Its comment
  asserting that native m1n1 reserves the predecessor prefix is not true of the
  native handoff source inspected here. Generic kboot's retained-heap handling
  is guarded for T8140 and is bypassed by the native early-return route.
- Both old NVMe logs show RTKit protocol 12 initialization, whose source message
  belongs to HELLO handling. Together with scrub/read-only storage evidence,
  this establishes old storage activity, not execution or cache qualification
  of the adopted borrowed-buffer path. No per-buffer page/cache proof appears
  in these selected artifacts.

The current predicate requires full protected SART coverage, alignment, normal
System RAM, valid PFNs, every page reserved, and a valid linear mapping. A
predecessor buffer outside the advertised bank cannot satisfy that path under
this handoff. Adding an FDT reservation alone would not create System RAM or a
normal linear mapping; `no-map` would deliberately prevent the latter.

## Cache attributes remain a separate missing contract

m1n1 source initially maps DRAM as Normal WB, removes MCC carveouts, and also
creates explicit Normal-NC mappings for protected/firmware or framebuffer
ranges. Its owned RTKit buffers are separately heap allocated. A Normal-NC
firmware mapping observed elsewhere does not identify the attributes of an
actual ANS shared buffer. Conversely, an ADT RAM interval or protected SART entry
does not prove that buffer may be accessed through a new WB alias.

The kernel's existing `memremap(MEMREMAP_WB)` plus normal linear-map and streaming
DMA path assumes a compatible WB ownership contract. System RAM/PageReserved
classification alone cannot establish that contract. Do not expose excluded
firmware pages as System RAM merely to satisfy the predicate.

Before choosing a mapping, capture or recover evidence for each actual buffer:

1. Same-session RTKit endpoint, physical span, size, identity IOVA, owner and
   ownership lifetime; distinguish heap-owned host buffers from firmware/SRAM,
   crash, syslog, ioreport and oslog spans. Keep addresses/content private.
2. ADT DRAM/carveout classification, complete protected SART allow coverage,
   16KiB page boundaries, cache-line boundaries and exclusion of resident code,
   stacks, secondary-core RO, framebuffer, MTP and other protected regions.
3. The effective attributes and permissions of every CPU alias over those
   exact pages: active translation descriptors, MAIR, shareability and relevant
   resident EL2 mappings, bound to the same session. Generic source defaults or
   a screenshot of another region do not substitute for this evidence.
4. Which CPU/device can still write, the predecessor's last cache ownership
   operation, and the synchronization/ordering protocol with the live IOP.
   Blindly cleaning dirty predecessor lines could overwrite firmware writes;
   blindly changing NC to WB would create a different aliasing contract.
5. The final, patched FDT and Linux memory-resource/page state from a supervised
   future boot. Validate System RAM, PFNs, PageReserved, linear-map eligibility
   and identity DMA mapping before synchronization or data access. Preserve
   SKIP_CPU_SYNC on unverified/rejected mappings and never copy bounce data back.

## Minimal choices for a separately reviewed loader branch

- **If compatible WB host-owned shared pages are proven:** add only those exact
  page-rounded spans as additional RAM-bank entries and mapped, non-reusable
  reservations. Preserve every live allocation; never expose the whole resident
  prefix or all DRAM. Validate overlaps and cache ownership before modifying DT.
  A reservation must cover the complete added bank so Linux cannot allocate it.
  Reuse generic kboot's mapped-reservation/bank idea where applicable, with an
  explicit native-path schema and capacity/overflow tests; the current fixed
  in-place single-bank template cannot silently grow.
- **If actual shared pages require Normal-NC:** keep them outside ordinary RAM
  and normal WB aliases. A separately designed ownership-checked I/O mapping
  adapter, matching the proven attributes and access/barrier rules, would be
  needed. Do not feed an NC/I/O pointer to `dma_map_single`, and do not weaken
  the WB predicate or treat `PageReserved` as a cache-compatibility certificate.
- **If attributes, ownership, endpoint span or overlap cannot be proven:** keep
  mapping refused. Preserve the known-qualified environment and existing
  ACK-only handling; do not reset/re-negotiate a live IOP to hide the gap.

No loader implementation is proposed for immediate activation. The primary
agent owns the decision and any separate boot-preparation source branch. Existing
kernel compilation and fake mapping checks do not qualify this handoff, firmware
coherency, native storage durability or persistent installation.
