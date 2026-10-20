# DCP modular link restriction

Status: **BLOCKED (modular link)**. Source `be6225839fe98158ce677d9424ce255aeedbb406`
compiles the complete DCP composite and all 12.3/13.3/26.6 translation units;
modpost rejects four unresolved arch internals. Exact object/config/source proof
is in `gravity-dcp-module-failure.json`. No export or validation suppression was
added. Hardware remains untested.

The only DCP callers are the scanout direct-map fallback and its cleanup:
`drivers/gpu/drm/apple/apple_drv.c:71` restores direct mappings;
`:175` checks page-level mapping support, cleans/invalidate caches, invalidates
linear-map aliases and flushes the TLB. `arch/arm64/mm/pageattr.c:90,254,266`
and `arch/arm64/mm/cache.S:115` define the four symbols without exports.
Those complete arch files match the qualified f93 source byte-for-byte:
pageattr SHA256 `1452752535516773053d392994c391b572e0de551690574a053dd6b3033dacf0`,
cache SHA256 `d12b5be41e3b6355e87640353b87dabe1c63b26beaeaa0084aa50865c85e89c4`.
This failure is a driver/module-interface mismatch, not evidence of a changed
M4 memory-management block.

The existing alternative at `apple_drv.c:220` allocates from a no-map reserved
pool via public DMA/reserved-memory APIs. The driver requires an available
`shared-dma-pool` with `no-map`, attaches the named `scanout-pool`, checks each
allocation lies inside it, and reads `apple,scanout-iova-base`. Its comment
requires m1n1 to have installed the entire locked realtime DART mapping before
Linux. Source DTS search for `scanout-memory-is-nomap`, `scanout-iova-base` and
`scanout-pool` returns no matches; that does not establish the live device tree,
which this lane has not accessed. Ordinary DMA/cache synchronization is not a
proven substitute for retiring the direct-map alias required by this driver.

Recommendation sent to the primary agent: retain the failure and avoid blindly
exporting private arch helpers. A module can be explicitly restricted to the
existing no-map path, with an early probe refusal when its pool preconditions
are absent; preserve direct-map fallback only for a built-in driver. That would
require a reviewed source change and independent bootloader/DT/DART validation.
The built-in alternative is a distinct untested profile that may probe during
boot; it must not be reported as a successful dormant module. No proposed
mapping change has been implemented by this lane.
