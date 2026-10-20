# Cached ADT property provenance and observation limits

`adt-property-provenance.json` was derived offline from the saved graphics ADT
whose digest it records. It exports node/property names and encoded lengths,
not values, physical addresses, UUID contents, keys or firmware bytes.

| Node/property names | Candidate meaning | Limit |
| --- | --- | --- |
| `/arm-io/ans/iop-ans-nub`: `region-base`, `region-size`, `segment-names`, `segment-ranges` | ANS firmware region and segment descriptors | These are not a per-endpoint shared-buffer inventory or cache ownership proof |
| Same nub: `running`, `pre-loaded`, `quiesced`, `shutdown-sleep`, `power-managed` | Captured firmware state hints | Cached property presence does not establish the current live handshake state |
| `/arm-io/ans`: `iommu-parent`; `/arm-io/sart-ans`: `AAPL,phandle`, `reg` | Protection-provider provenance | The captured parent resolves to SART-ANS; no current SART entry values were read |
| `/chosen/memory-map`: `RTBuddySeg` | Global firmware-allocation envelope | This is not exclusive ANS ownership or an endpoint mapping contract |
| `/chosen/carveout-memory-map`: `region-id-*` | Platform carveout inventory | Region names alone do not identify a shareable WB buffer |
| `/defaults`: `pmap-io-ranges` | Input to m1n1's identity mapping overrides | Current source translates some flags into NC/device attributes; this is not an active page-table capture |

The saved nub has two 32-byte `segment-ranges` records under the source's packed
ADT structure. Internally comparing those spans with the saved pmap inputs does
not identify a Normal-NC override for either declared segment: one is covered by
an unclassified pmap rule, one by none. Both lie outside the captured RTBuddy
allocation envelope. **None of that establishes WB, active mapping attributes,
or the locations of actual RTKit host buffers.** Do not generalize a Normal-NC
mapping shown for another carveout to these spans or to heap-allocated buffers.

The actual per-endpoint owner metadata lives instead in m1n1's private
`rtkit_dev` fields (`syslog_bfr`, `crashlog_bfr`, `ioreport_bfr`, `oslog_bfr`),
each containing `bfr`, `dva`, `sz`, `owned`. `nvme_rtkit` references the local
image's context only. It may be NULL or may not describe the resident predecessor.
Those fields would require a proven current owner, image identity and load bias,
not interpretation of an arbitrary ADT segment as a buffer.

## Existing observation capabilities, not an adapter

The saved raw ELF contains `nvme_rtkit`, `mmu_pt_L0`, `cur_boot_args` and `hv_Ltop`
symbols. Offline objcopy of that raw ELF matches the qualified base binary byte
for byte (`symbol-capability-evidence.json`). This does not prove it is the
currently running image, establish its load bias, or identify every resident
translation context.

- The existing `P_READ64` proxy operation performs a guarded RAM read and
  updates exception-guard bookkeeping. With independently established addresses
  and owner lifetimes it can read data/paging metadata without programming MMIO
  or changing page tables. Reading an unproven address is not automatically safe.
- `ProxyUtils.mrs()` is **not a read-only transport primitive**: it routes through
  `exec()`, writes a scratch instruction buffer, performs cache maintenance and
  calls that code. No such helper was invoked, generated or installed here.
- `P_HV_TRANSLATE` calls `hv_translate()`, which executes AT translation
  instructions and saves/restores PAR. It returns a translated address rather
  than a complete cache/ownership audit and presupposes the relevant HV context.
- `hv_pt_walk()` is a source-level table reader, but its block handling removes
  lower attribute bits from returned descriptors. Its result alone cannot prove
  effective cache attributes; its tables/context must first exist and be bound
  to the exact image/session. It was not invoked.

There is therefore no complete cache/ownership proof in the selected saved
artifacts and no established turnkey read-only source path for all required
active register/translation contexts. A future supervised inspection needs the
actual buffer owner/spans plus active TTBR/TCR/MAIR, descriptor/shareability and
resident alias metadata from every relevant stage, followed by an explicit
coherency/last-writer contract. Plain byte reads or a source mapping default
cannot supply the missing device-coherency proof.

This work is offline observation/proposal only. No bootstrap adapter, loader
patch, cache operation, page-table change, target read or hardware test was run.
