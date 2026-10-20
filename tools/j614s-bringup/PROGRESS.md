# M4 Pro native Omarchy engineering

Goal: native accelerated, responsive, persistently bootable Omarchy. Overall INCOMPLETE.

## Current engineering checkpoint

- Hardware remains at m1n1 Running proxy; no target boot after manual recovery.
  Supervised availability is pending; remote recovery remains unverified.
- Combined Gravity source8f2f3d1 builds Image+18 modules twice independently,
  byte-identical across all19 artifacts. Exact6c config/layout checks retained.
  This source is hardware UNTESTED, not an installable boot bundle.
- Native GPU INIT/rendering, native DCP and persistent default boot are incomplete.
  Prior12-core and GPU-transport hardware passes remain separately evidenced.
- A separate151 signed-package candidate closes all24 newly introduced bounded
  ELF issue edges, preserving original117 rows and protected holds. Root verifies
  all151 archive hashes and34 tests. Normal preparation binds all986 descriptions;
  four removals remain hypothetical. Runtime, native nvim and boot hooks are unqualified.
- Source fixes are reviewable in kernel draft PR6, nvim package draft PR1 and
  m1n1 RAM-loader draft PR1.
  Minimal USB/RO probe is packaged and36 host tests pass; init is unexecuted; protected boot/disk changes
  remain outside current authorization.

## Baseline

Mac16,8 / J614sAP / T6040 M4 Pro, 4 efficiency and 8 performance cores, 24 GiB RAM. ADT is the hardware source of truth. macOS firmware 26.6.2 / 25G83, mBoot-18000.161.10. Installed custom boot object remains m1n1 8e0cf28. Experimental payloads use RAM chainloading with a restricted 4 GiB Linux allocation and read-only SSD plus RAM overlays.

Kernel fork: https://github.com/garethpaul/omarchy-m4pro-linux/tree/codex/j614s-native-diagnostics
Latest kernel commit: 4ff8816df8c4bc81b1652eca17fc8c0e9e1928cc.
Build: 7.1.12-j614s-gpu-bringup+; Image SHA256 a114bb3a927918b54c25ed31b3ea102b9ac08d404fdd793a1f75d99845259883.
Corrected aurora-bindgen 0.73.2 is required; layout assertions remain enabled.

## Verified improvements

- CPU WORKS: all 12 online, correct secondary MPIDRs, per-CPU 64 MiB checksums, 12 million shared atomics, 12,000 SIMD-preserving sleeps. Automatic M4 wait-state quirk fixes WFxT corruption; idle=nop and arm64.nowfxt test flags removed. Commit 1d78f77f80529c5323619a40b3280e82546ea841.
- GPU transport WORKS: exact G16S B1 ID 0x0a031100, 16 active cores; guarded Linux RTKit protocol 12 startup, receive IRQ count 0 to 6, quiesce, CPU RUN readback zero. Tests 55/56; commit 4ff8816df. GPU rendering remains UNIMPLEMENTED.
- Desktop PARTIAL: native Hyprland/Quickshell/Foot on inherited framebuffer, llvmpipe. Test 52 sampled Hyprland at 8.398% of one CPU over 10.002 seconds, with 12 cores available. This is not a matched before/after benchmark.
- Storage WORKS within tested scope: Btrfs scrub 5.89 GiB with no errors, block read-only on disk and all partitions, zero NVMe write requests/sectors during current tests.
- Input PARTIAL: internal MTP keyboard and trackpad registered; earlier user report was jumpy. Smoothness after CPU fix is UNTESTED.
- Hypervisor PARTIAL: owned EL1 RAM guest/HVC and read-only AFR MMIO trace work. Synchronous RAM hook write/read completed, then guest faulted at vector 0x300. Correction to set normal HCR.FMO is compiled but hardware UNTESTED. XNU tracing UNTESTED.

## Current blocker

The operator manually power-cycled the Mac after the failed watchdog recovery. Webcam now shows Running proxy and the exact m1n1 8e0cf28 enumerated as USB device 63. Read-only resident metadata confirms T6040, boot CPU4/MPIDR0x80010100, zero exceptions and no NVMe/DCP initialization. A transient SPMI read with watchdog state unchanged measured PMU counter0; no counter byte was written. This does not establish its value before the restart. Remote recovery is still NOT independently verified. No unattended reboot is allowed under the overnight instructions. The KVM Fingerbot controls ANOTHER machine and must never be used for this target.

Candidate cause: the experimental HV harness omitted m1n1's normal PMU panic-counter clear across several watchdog resets. This is a hypothesis, not measured. Boot-object bytes were not replaced during these tests.

## Active work

Independent lanes: CPU qualification, graphics ABI support, Omarchy ARM64 profile, reproducible build/test infrastructure. Only primary agent controls target.

## Exact next hardware action

The manual restart restored proxy access, but did not independently verify remote recovery. Do not run the prepared FMO/hypervisor test or chainload another kernel unattended. The next hardware operation is limited to fresh webcam/USB and cached metadata observations. The FMO test remains prepared for a supervised recovery window; XNU/macOS boot and protected changes need explicit approval. The unrelated Fingerbot must never be used.

## Recovery

Use webcam for all screen reading. Built-in Apple menu Restart is preferred when accessible; otherwise physical power cycle. Never select Reinstall, change Startup Disk/security policy or write protected volumes under overnight authorization. KVM is not yet an independently proven recovery path. Existing successful watchdog recoveries do not override the current failed recovery.

## Evidence

Prior exported artifacts: outputs/m4-smp-enablement, outputs/m4-gpu-bootstrap, outputs/m4-hypervisor-enablement in the parent task workspace. Raw ADTs and firmware stay private. The Windows SanDisk compressed verified backup remains preserved.

## Overnight engineering checkpoint

- CPU suite committed 2035d635f6689321cb43aec329fde7617d959b1b; ten host tests and AArch64 workload builds passed. New runner hardware execution remains UNTESTED.
- ARM integration committed 7092eccc1da76ba3bae7d16a748f2ac3071225f5; sixteen host tests and native/AArch64 EGL probe builds passed. Installed image has986 packages and satisfies all163 existing Asahi base requests. Official current list gaps are version gaps, not blanket ARM unavailability. Broad kernel/bootloader updates must not replace this qualified boot chain.
- Crash readiness race fix candidate 0fb65dbd66f9b91a43096ecbabd52b81f73bea5c; preserves a terminal crash state across readiness publication. Isolated object build underway; hardware UNTESTED.
- Isolated full baseline Image/modules build underway with exact corrected bindgen and layout checks retained.
- Read-only USB/webcam observer implemented; four host tests and real webcam capture passed. It never infers OS/recovery success from enumeration alone and cannot reboot or pet a watchdog.

- Power audit: CPU_FREQ and CPU_IDLE are unset in the tested config. The 1000MHz timer line is not a measured CPU frequency. T6040 has three CPM windows and changed PMGR/PMP layouts; a writable M3 alias is not justified.
- Exact formerly dirty test56 source archived separately at kernel commit867fae4ca; a new candidate will remove fixed-address framebuffer instrumentation before further qualification. Original source/build/boot object remain unchanged.

## Primary graphics route

The user reiterated through the other chat that Gravity's working kernel,
matching Mesa and published capture/replay tools are the starting point. The
source message was verified in that chat's user turn; its six-hour follow-up
automation is already owned by that chat and must not be duplicated.

Kernel source GravityLinux/linux gravity-m4 commit4fc326f6c25ccceb7515e2635c22e01fde5d3bac;
matching Mesa is GravityLinux/mesa (niklassheth/mesa redirects). RE references are
ADevWithAnIdea/agx-re and niklassheth/agx-re, described at https://codyho.dev/blog/gpu-driver/.

The actual old Gravity root/MainConfig serializers were compiled and replayed.
Their output differs from the exact25G83 G16S consumer: version mismatch, null
new-consumer descriptor+0x2f0 and power-pointer+0x471. This proves incompatibility
of those serialized objects, not that the complete current stack cannot be
ported. Check later overrides/FW substitution and compare exact25G83 G16G versus
G16S before attributing every delta to the SKU. Minimal compute job/output is
the next runtime milestone; no full independent graphics stack is planned.

Graphics validators now decode the measured envelope/MainConfig and plan the
first unsupported pointer chain root+0x18 -> main+0 -> hardware-data+0xe90 (16bytes),
with RAM-only bounded page traversal. Source provenance includes ADT and vendor
firmware observations; do not describe these additions as clean-room work.

The real driver race regression reproduced false readiness on4ff8816df and
passed on0fb65dbd, including a crash after is_running but before cmpxchg. Tests
compile actual driver source with mocked Linux/RTKit/MMIO, not a copied model.
These are host control-flow results, not induced firmware-crash hardware tests.

Reproducibility check01vs02 FAILED:14Cmodules match, Image and RustAsahi differ.
The build agent traced absolute output paths in Rust objects and is fixing
KRUSTFLAGS remapping before another independent comparison. Do not call the
builds bit-for-bit reproducible until the actual hashes match.

## Latest integration checkpoint

Recipe2 build tooling is integrated, including stable Rust source/output/sysroot prefix mapping. Clean full kernel and independent repeat comparison are still running. Gravity kernel ABI and Mesa compute fixtures are being developed against the matching published stack; source-only envelope validation does not establish a successful firmware INIT or GPU job. Minimal Metal capture tooling is compiling on a separate Mac builder, not the M4 target.

The publication worktree initially had an uninitialized sparse index showing unrelated kernel deletions. No such change was committed or pushed. Its index was restored to its base, missing sparse root files restored from HEAD, and status checked to contain only the new tools package.

## Reproducible candidate and capture tooling

Clean kernel f93a3416c60f26c68084134dc6c1d205becd5753 now has two independently
built, byte-identical Images and all15 modules. Image SHA256
7683e4f6254026370ceecf4e64a5e9905344df658dea5f5d3e6679aebaf068f1;
release7.1.12-j614s-clean-candidate+. Both builds pass embedded config, AArch64
module ABI and actual private-prefix audits. Hardware boot remains UNTESTED.
Earlier recipe1 reproducibility failure is retained.

Gravity kernel envelope candidate db9f2f8f00986e3ef03fddbdaad55a861e793123
compiles/replays actual serializers with legacy output unchanged; no runtime
caller activates it. Full Gravity module qualification is in progress with real
layout assertions enabled, not disabled to accept a build.

Capture source ba285fb664f8ca9920c0deb357ff7259c04b9f2c has builder-only
validation on M1 Pro: three tiny Metal jobs across one/two-job cases, exact
readback and causal START/COMMIT gates;14 host corruption tests pass. It has not
run on the target or staged onto macOS.

The bootstrap crash fix draft is https://github.com/garethpaul/omarchy-m4pro-linux/pull/1.
A gh fork --fork-name attempt unexpectedly renamed the existing Linux fork.
The original name was restored after verifying repository identity; commits,
branches and the draft PR remain intact. No further naming changes are planned.

Fresh webcam and cached proxy metadata still show Running proxy, USB63 and zero
exceptions. No unattended boot, watchdog change or protected-volume action was
performed. qualification/STATUS.md supersedes stale one-core and missing-battery
claims in the initial audit.

## Exact next safe engineering actions

- Gravity full Image/module link is running after the strict complete crate
  passed. Pinned current source db9f2f8f retains a separate layout-enabling build
  overlay; no runtime profile was enabled.
- Mesa offline compute fixture compiled384 host gtests. Root review found two
  accepted shader/record overlaps; actual failing gtests reproduced them and an
  explicit shader-size/range fix is being qualified. AArch64 tool/compiler
  builds and a release-build explicit model guard are in progress.
- Signed vi provider ex-vi-compat was found and actually invoked in an isolated
  namespace; the package lane is finalizing exact-name precedence and provider
  proof before revising the earlier unresolved-vi result.
- Early T6040 capture adapter is integrated and tested offline. Root additionally
  passed its identity guards against the real captured ADT using fake tracer
  registration and zero physical reads. Overlap consistency does not establish
  an atomic graph against other CPUs/firmware. Native capture remains UNTESTED.
- Display lane is now investigating the changed T6040 DCP interface and a narrow
  justified source change or exact capture decoder. No compatible-only alias,
  DCP reset or target operation is authorized by that lane.

Published tooling branch tip2769eca7d6fd9eaf15873f0c78168db4b2ade8ec includes
reviewed source/evidence; newer integrated work will follow after review.
The clean source and historical test56 archive are also pushed separately.
Local outputs/m4-overnight-enablement contains matching Image+15 modules, exact
config and checksums; it is explicitly not an installable boot bundle.

## Package and link failure updates

The vi gap is resolved through the signed official ex-vi-compat payload and
actual unchanged-script execution, not an invented alias. Exact-package names
now take precedence over virtual providers, confirmed against pacman. Latest
print-only solve:167 ARM-compatible requests, four held boot/firmware requests,
zero unresolved,117 transaction packages,66 already-current. Four signed
editor/provider payloads verified;113 selected signatures/hooks still unverified.
All38 package/preflight tests pass; no installation occurred.

The full Gravity crate compile passed with all3170 layout blocks/16284 offset
checks. Full linking then exposed RUST_APPLE_RTKIT=y with APPLE_MAILBOX=m, leaving
built-in rtkit.o mailbox symbols unresolved. Build lane is fixing the real
Kconfig dependency and retaining before/after evidence; linking is not yet a pass.

## Latest compile/source milestones

Gravity source b442be4b28f3720daff6c5f26fe8b1ab3aef28f1 plus recorded layout
overlay builds complete Image and seven modules, including asahi_m4. Image
f7be0d5a6ceb07a43e47a1e41a2fe66e33b2a584c54bab30e479a5dd1b15f96c;
all artifact/config/vermagic/path checks pass. This is compile-only, not the
J614s boot candidate. Source draft PRs are kernel#2(envelopes), kernel#3(RTKit
mailbox dependency) and Gravity Mesa#1(offline fixture/release model guard).

Mesa source86c4942d3cd passes387 host and AArch64 QEMU gtests plus six Python
cases; generated shader and all job artifacts match across architectures. Root
regenerated the fixture in the integrated tree and passed its six tests.
G16S production runtime stays rejected even with NDEBUG; no GPU job ran on Mac.

Metal store42 source458429a matches256-word/local256/poison/42 fixture and
passed separate M1 Pro builder readbacks and27 transcript tests. Original XOR
evidence is unchanged. M4/native first-capture/BO canaries remain UNTESTED.

DCP source8e27e3e adds structural bounds;8c93f2c adds minimum typed extents.
Root reproduced the actual D006 typed bug before the latter and passed both
typed and original envelope/ACK regressions plus14 offline decoder cases.
All Apple DRM translation units compile AArch64. Full modular linking exposed
private direct-map helper references in existing scanout fallback. A separate
no-map-only module fix is authorized, preserving built-in behavior and requiring
real reserved-pool/DART prerequisites; no exports or fake mappings permitted.

Package audit found selected Plymouth file paths match installed initramfs
regeneration hooks despite protected package-name filtering. No hooks/install
have run. Two exact pinned archives returned404; remaining large archive is
being verified. Keep the original117-row plan and failures, not substitutions.

Consolidated Gravity/J614s source work is underway in a separate branch. It
ports tested CPU/input/USB/battery/bootstrap changes narrowly. NVMe must remain
refused before side effects until inherited RTKit adoption exists; old hardware
storage pass does not qualify this new source. A separate adoption port follows.

Physical target remains proxy63; no boot/reset/watchdog or protected action
performed after the manual restart. Original4ff dirty-source fingerprint and qualified reference Image/config
remain unchanged. Clean f93 itself is build-qualified, not hardware-qualified.


## Integrated DCP link and pinned-payload audit

Restricted DCP source124fd0633bb8932bbf68845ecbe8a5ffc53dfb43 builds a complete
Image and ten modules including appledrm/asahi_m4, with the exact configuration
that failed the earlier modpost. Image897617e90867c28572b6fe42061ed64abf5c0b5fa08f303a6f429318612014e5;
layout3170/16284, embedded config/module/path audits pass. No arch-helper
exports or checks bypassed. Live J614s no-map/DART handoff remains BLOCKED.

Consolidated ccb0647c779ec32f2549708ee3b57510700aaabb fixes the actual MTP
owned device-node type error without a cast or disabled warning. All ten
platform objects passed and full Image/modules build is running in its own
snapshot. Its source/config invariant suite passed12 tests in the integrated
workspace. NVMe stays refused before hardware operations; a separate actual
inherited-state/RTKit adoption port is in development.

Pinned117-package audit verified115 payloads with exact size/SHA/architecture
and retained-image PGP anchors. Both missing old versions returned404 across
GeoIP and all12 official mirrors (26/26 requests). Their newer release numbers
are documented, not silently substituted. A separate current-metadata proposal
is now being prepared while the original plan and failures remain immutable.
Twenty integrated package tests pass. Plymouth paths match two installed
initramfs-generating hooks; no hooks/install were executed and transaction
execution_ready/deployable remain false.

No target boot, watchdog change, firmware operation, disk write or protected
change was made. Remote recovery still needs independent verification before
the next physical boot-sensitive experiment.

Post-link source review identified a real remaining no-map ownership gap:
foreign PRIME imports bypass the custom dumb-buffer pool path and can reach
scanout through dma_addr. A separate import-boundary fix/regression is underway;
124fd's link pass does not qualify module loading or all buffer ownership.


## Published and independently rechecked checkpoint

Tooling branchcodex/j614s-overnight-tooling now points to346dcc9c172d5e6d7337d272d687cd427cd4d423, exporting
275 reviewed committed workspace files from78b3cb5 with an exact per-file
manifest. Publication scan found only public hashes/source identifiers, public
URLs, configuration assignments and package/system paths; no actual credential,
private-host or private-path disclosure was found. All source patches are
tracked explicitly despite the kernel repository's patch ignore rule.

DCP receive/typed source8c93f2c is published as draft kernel PR4; actual-source
host regressions/AArch64 compilation support its limited claims. It does not
activate T6040 or qualify native modesetting. Root verified the PRIME followup
uses the public GEM exporter ownership helper before private casts and keeps
own pool self-import on the normal reference path. Foreign AGX/DCP buffer
sharing remains unsupported in this temporary owned-pool module profile.

Integrated host checks:38 Omarchy tests,27 capture transcript tests,20 payload
audit tests and12 source/config tests pass. The newest ccb064 source/config
validator also passes explicitly with deployment false. A fresh webcam capture
at2026-10-20T05:48:18Z still shows Running proxy and USB enumeration63.
No target boot/reset was performed.

Full ccb064 linking then failed on rust_build_error in M4Gpu::probe. Relocation
and message identify rust/kernel/io.rs offset_valid build assertion: g16.rs
uses infallible MMIO operations with a runtime loop offset. The size config
retains the assertion that the generic performance build optimized away. The
build lane is changing those dynamic accesses to checked APIs and propagating
errors, while retaining exact config and all assertions.


## Complete consolidated build and current package proposal

Source6340620747e221ea415ddee944afccacff3953ee now passes complete Image and18
matching modules with the unchanged reviewed size config6c5aba. Image SHA
8b09c3a584ab41d36c10e605d5b9e02acf1ace6abe07dde78ea5865bd5849dc4, release
7.1.13-j614s-gravity-candidate+. All3174 layout blocks/16412 offsets and strict
embedded-config/module/path audits pass. Earlier MTP and Rust assertion failures
are retained. Exact source is draft kernel PR5, based on immutableccb checkpoint;
no new hardware boot or independent full634 reproducibility claim.

Verified Image/config/18module copy and curated manifests/checksums are in the
user-facing kernel-gravity-compile output directory. Raw private build.log,
build/bin trees and all firmware/DT/initramfs/boot entries are omitted. This is
compile-only and explicitly not an installation bundle. It predates separate
PRIME ownership correction and still refuses J614s NVMe before hardware access.

PRIME sourcecf983 now authenticates same-device exported GEM ownership and
validated pool provenance before module imports. Own pool self-import is kept;
foreign AGX/DCP imports are refused. Actual AArch64 composite and causal host
checks pass; native locked-DART mapping/import design remains missing. Root
identified recoverable UBSan behavior in the first harness and required fatal
sanitizers. Both host harnesses now use fatal checks plus empty-stderr checks;
actual injected UB/UAF controls terminate, and root reran all variants/64cases
successfully. No driver diagnostic or bound check was disabled.

The separate current ARM proposal uses the same167 requests/117 selections.
All117 payloads qualify exact size/SHA/retained-key PGP and signed PKGINFO vs DB
metadata. Four versions change explicitly; marisa moves gcc-libs dependency to
libgcc+libstdc++, with no package/dependency-name additions/removals. Root ran
all ten actual parser/resolver tests successfully. Five DBs remain unsigned
under the actual Required DatabaseOptional policy; Asahi DB signature qualifies.
HTTPS/payload PGP do not prove metadata freshness/completeness/rollback absence.
Plymouth boot effects, held boot pins and reverse-dependency ABI remain blockers;
no install or hook executed. Original115/117 audit and26/26 HTTP404s are intact.

NVMe SART/RTKit prerequisites75667 now compile AArch64 with3174/16413 actual
layout/offset checks, plus actual-source host regressions independently rerun
by root. Full ANS admission/lifetime integration is not yet wired; current
refusal stays. An independent read-only review is tracing actual DMA/devres
lifetime and mailbox contracts before any future test.

## Strict ANS admission and combined build failure

The immutable05af581d3bf7574d933044d509dd6c3617e8a111 source replaces the initial
blanket refusal only for the exact measured J614s inherited-session profile.
Six actual-source host suites,12 wiring assertions and21 sequential patch
replays/all35 modified files pass. The IDLE-completion and failed-stop reader
regressions retain causal baseline failures. Final independent review stopped
automatically; the primary inspected ordinary source contracts, without claiming
independent acceptance or real concurrency/hardware qualification.

Build-only combined sourcea652cf765b6749b268af16ddbcf29ce314dfab85 adds checked
GPU MMIO and owned-pool PRIME fixes with exact per-file and patch-ID provenance.
Its real AArch64 build FAILED at apple.c:2679: NVME_QUIRK_BROKEN_FUA is undeclared
in the Gravity core. Configuration6c5aba, source and tools did not drift; RTKit
and SART objects compiled. The failed source/build remain intact. Next executable
action is a separate narrow core dependency correction, actual-source regression,
fresh full build and only then an independent fresh reproduction. No combined
boot bundle or hardware pass is claimed.

The Mac remains at the installed m1n1 proxy. A supervised availability question
is pending; absent an answer, no boot-sensitive operation is authorized.

## Actual package ABI blockers

The separate signed117-payload plan now has an actual ELF audit:1256 incoming
ELFs,328 untouched reverse consumers and12,596 direct edges. Eight Qt consumers
lose12 mandatory Qt_6_PRIVATE_API imports under the partial6.12 upgrade; exact
GNU readelf before/after proofs identify the bytes. Sixteen incoming/new direct
SONAME edges are unresolved in the bounded model;52 existing issue edges remain
separate. The new-home Omarchy nvim template contains a dormant mode0644 x86_64
shfmt asset, not evidence of an existing user's running foreign code.

The initial model only replaces same-name packages; signed conflicts involving
dotnet-host-bin, mise-bin and quickshell still need real removal modeling.
Root reran14 actual ELF/virtual-root tests successfully. Root also identified
replay-cache identity gaps; the package lane is adding restored-byte and auditor
identity validation before a new audit. Current original bytes are not known to
have changed. Installation, hooks, protected holds and runtime remain blocked.

A fresh webcam observation at2026-10-20T06:20:25Z still shows Running proxy,
USB1209:316d installed8e0cf28, enumeration63. No boot/reset action occurred.

## FUA correction and boot-preparation contract

Separate source dd3f608d60ed503b87a9400255286d1c8fe5ac2d adds the missing FUA
core enum/name and clears only BLK_FEAT_FUA while retaining WRITE_CACHE. Actual
namespace/block-flush functions pass16 literal scenarios and queue POSTFLUSH
after simulated DATA completion. Root reran the fixture successfully. This
does not qualify physical I/O or durability. New combined source
8f2f3d13600aacadd93d577855b7e212b8ae57ff is building with exact6c configuration;
a652 and its failed build remain intact. No target action occurred.

Root inspected the qualified private native-loader source during preparation:
it publishes only the newly owned4GiB as Linux memory, excluding predecessor
allocations. The new borrowed-RTKit guard requires SystemRAM, valid reserved
pages and linear mapping. The comment about predecessor-prefix reservation
is not established by that loader. The integration lane is checking old captured
buffer evidence and a minimal explicit RAM/reservation/cache contract. Do not
weaken the guard or reuse old firmware addresses to conceal the mismatch.

Reviewed source/evidence checkpoint7aa8f7c is published on the experimental
tooling branch at9f43a9f0f. All387 publication paths match its manifest and
passed classified secret/private-data checks. Local outputs carry the same
committed source; old artifact directories remain distinct.

## Complete combined kernel link

Combined8f2f3d13600aacadd93d577855b7e212b8ae57ff now passes full Image and18
matching modules with exact6c5aba configuration and zero normalization drift.
Image SHA256 f9d7b637bc70fcab77b5806c43c39ae333e633fcc63fa6ccaa77cd22c91d4604,
release7.1.13-j614s-gravity-candidate+. All3174 layout blocks/16413 offsets,
embedded config, AArch64 ELF/module version, assertions and private-path checks
pass. A fresh independent source/output build is running; no reproducibility
claim yet for8f2. Source published on codex/j614s-gravity-combined-fua; the
separate inherited-ANS source branch includes the comment-only correction
de1231473a4682cd465397a6e9ed519560ce0893. New artifacts exported separately as
outputs/m4-overnight-enablement/kernel-gravity-combined with complete file hashes.

This is compile-only and hardware UNTESTED, with no matching boot bundle or
permission to deploy. Old borrowed-buffer execution/cache ownership is not
proven by52/56: the saved logs show HELLO and storage activity, which can work
without borrowed mapping. The strict mapping gate remains unchanged. No target
boot, firmware action or protected-volume modification occurred.

## ARM seed fix and evidence replay correction

Sourcee8f5edeabdaa0efe30760f47bc5c93467ac45490 fixes the actual Omarchy nvim
packaging seam: remove builder Mason data, add native shfmt/stylua dependencies,
and filter only those Mason defaults. Root reran all3 package/Lua regressions
with real x86/ARM ELF fixtures, bash syntax and all15 portable-source hashes.
A missing unchanged metadata export was added explicitly. Draft source is
https://github.com/garethpaul/omarchy-pkgs/pull/1; signed build, runtime, existing
user migration and installation remain unqualified. No original117-plan change.

Inherited ANS is reviewable as draft kernel PR6,8 scoped files, based on a
source-tree-equivalent pinned checkpoint; the default branch is unchanged. Both
created PRs are attached. No final independent review acceptance is claimed.

Package audit replay now seals every restored file/link/directory and binds
auditor/parser/extractor identities, with integrity-checked data-only JSON
caches. The original stale-tree acceptance was actually reproduced; a one-byte
QtCore change and changed reused-provider file are now rejected by the real CLI.
After exact bytes were restored, the117-payload replay is byte-identical and
retains24 new/incoming issue edges. Root reran20 tests and verified all public
evidence hashes. Actual normal libalpm conflict/removal preparation is a
separate ongoing step; print-only results did not establish removals.

## Combined build reproducibility passes

Two fresh source/output builds of8f2f3d13600aacadd93d577855b7e212b8ae57ff have
identical Image and all18 modules,19 independent artifact inodes, zero differences.
Both exact configurations/critical tools/contracts match; layout assertions and
strict verification/path audits pass. The new artifact export includes the
comparison and refreshed hashes. Same-host reproducibility does not establish
hermetic or cross-machine builds, hardware behavior, storage durability or boot.

## Concrete RAM probe, still unexecuted

The minimal source8f2 initramfs is packaged:1,097,147bytes, SHA256
a3a01204b0310877dd41fd24c6f6ce803344cb48c4e9ef49a9bc4c994f1c39e8. Two fresh
archives match. It validates the exact kernel contract/module digests and signed
Debian BusyBox provenance. Root reran32 tests and signature/payload verification,
then independently checked LF/CR behavior of the native BusyBox read builtin.
Init was never executed. Root decompressed the actual archive and verified its
init/helper bytes against committed source and both module/BusyBox digests.
The local ram-probe export has complete checksums and explicit scope.

The physical ACM dispatcher must exist and receive literal probe before loading
either NVMe module. Review corrected a hidden-transient-failure risk: RO errors
now stay sticky, first/latest details remain visible, and the loader waits for
guardian first-scan acknowledgement/liveness. EOF reads back off instead of
spinning. Scheduling, USB reconnect, actual RO timing, cache ownership and recovery
remain hardware UNTESTED. There is no DT/loader/firmware/boot entry or new boot
authority. The target remains at the installed proxy.

Normal package preparation now captures117 adds and four hypothetical removals
with conflict/version/dependency checks enabled. The removal-aware virtual
filesystem still has24 new/incoming ABI issues. Root reran26 tests. A further
full986-description baseline identity check is being added before the next
freeze; current original inputs are not known to have changed. Coherent package
closure remains separate ongoing work, with original holds/plan unchanged.

## Complete package baseline and safe loader preparation

Package source85b0ab6 (central541d37f) binds preparation to all986 original
package descriptions, not only20 protected pins. Root reran29 tests and verified
42 ABI plus17 transaction evidence hashes with no mismatch. An actual changed
non-held description is refused before transaction setup; four removals remain
hypothetical metadata answers, not installation authority. The original117
proposal still has24 new/incoming bounded ELF issue edges. A separate145-row
closure retains those117 rows and28 additions; its full audit is ongoing.

`infra/watchdog-handoff-source.json` records the exact8f2 source/config facts:
APPLE_WATCHDOG=y, open_timeout=15, pre-userspace handler defaults disabled.
The Apple driver's probe resets the counter and applies its timeout before
registration. A loader timer and an init script that never opens watchdog
cannot by themselves prove recovery. No target timer or boot was exercised.

An isolated RAM-loader source cleanup is active: remove fixed-address display
debug writes and replace PMU counter clearing with a read-only zero requirement.
Original dirty loader source and qualified binary remain preserved. A new
loader build, any replacement DT and the actual combined kernel boot are
UNTESTED; supervised availability remains pending.

## Signed dependency closure and read-only probe revision

Integrated c84b863 as13ce34b: a separate151 signed-package closure preserves
all original117 rows and all holds. Root reran34 tests, verified76+17+32
evidence-file hashes and all151 actual cached archives. Normal preparation
accepts151 additions/four hypothetical removals with all986 descriptions fixed.
Static model reports zero newly introduced edges across14,734 direct edges and
310 untouched consumers, with57 old issues/344 Guile gaps/foreign dormant Mason
asset retained explicitly. GNU readelf independently checks12 actual ELF files.
The unsigned nvim6 source remains outside the signed model; no install occurred.

Probe source5c96ab8 (centralb52f4a5) now correctly says only this init avoids
arming/feeding watchdogs; predecessor/kernel behavior is separate. It reads
existing watchdog state and actual parameters, with absence/unreadability
explicit. Root reran36 tests; init never executed. Fresh03/04 archives match
d9fac843a55e2ea5e7f955704b3e8f5bfe9f16c49e38c7bdb747a8ca7831b52f
(1,097,496 bytes); earlier frozena3a012 pair remains unchanged.

Loader source6249e0ec removes debug framebuffer writes and changes PMU health
clearing into read-only zero admission before watchdog arm. Root reran26 PMU
and27 ordering cases under both fatal-sanitized GCC/Clang. First full compile
passes; its independent repeat exposed real path-dependent Rust/C strings.
Both failed reproduction artifacts remain preserved while the map precedence
fix is validated. This source has never run on the Mac. Webcam at06:49:52UTC
still shows Running proxy, unchangedUSB enumeration63. No new boot or target
write occurred.

## Final safe preparation checkpoint

Loader recipe2 fixes actual path-map precedence. Root directly compared all
seven distinct artifact pairs from two fresh clean6249 source checkouts: exact
bytes/SHA match, including both complete ELF files. Current flat loader SHA
2309dfbb368c5feadfc0ae70e0fbb11ac8e28132c815ab1c3eb63a66821a0e00.
The earlier failed pair remains preserved. Original source/binary are unchanged.
Draft source: https://github.com/garethpaul/omarchy-m4pro-m1n1/pull/1
No loader, kernel or initrd has been staged/executed on the Mac this turn.

Integrated isolated runtime sourcecae2768 as7303d8e. Root reran eight actual
ARM userspace commands in an empty read-only bwrap root: signed formatters
produce correct/idempotent fixtures and actual Neovim executes the unchanged
options callback; ten isolation/behavior checks pass. Scope uses eleven verified
baseline libraries, not the whole151 overlay. Optional editor-to-QEMU child
dispatch fails; no full LazyVim/Mason/Conform or target performance pass is claimed.
No host installation/trust/binfmt change occurred.

Remaining critical-path hardware work requires supervised physical recovery.
The pending availability request is unanswered; manual restart is the only
proven fallback. XNU/macOS staging/boot and protected persistence need separately
scoped authority. These are external gates, not reasons to mark the goal complete.

## Current resident CPU handoff observation

Added read-only slot observer after finding that the legacy capture helper
arms a watchdog and calls a helper that clears argument slots. Eight host
controls pass (initial decoder red phase preserved in tool output). Actual
07:04:19UTC observation verifies the paired installedfb31 binary/ELF, live
Mac16,8/board4/firmware, ADT-derived12 CPU identities, stable bounded RAM reads
and zero exceptions. USB63 has0 secondary flags and WFEfalse; no core, timer,
release slot or target code was changed. This is proxy state, not a Linux SMP
failure. Old USB45 release metadata must not be reused for this session.
Current observer source/evidence is in recovery/read_resident_cpus.py and
recovery/resident-cpu-observation.json; ASLR-dependent addresses remain private.
The next handoff still requires supervised core initialization and a newly
validated session DT before any RAM kernel boot.

## External hardware gate audit

Safe source/build/package lanes are checkpointed. The live readonly observer
confirms that current-session CPU startup/release qualification is still needed
before a new kernel handoff. The pending operator-availability request remains
unanswered, and remote recovery is unverified. This is the first recorded
consecutive goal-turn audit after this iteration's independent work completed;
no completion or blocked goal status is inferred from earlier compacted turns.
`recovery/NEXT-TEST.md` records exact prepared inputs and the supervised sequence.
No aggregate work/time/token/turn limit is imposed.

## Continued safe test-loop preparation

Previous goal turn classified PROGRESS: source/build/package changes and actual
readonly resident evidence changed the next test requirements. This continuation
is preparing two missing reproducibility pieces without booting: a bounded,
nonce-correlated physical-serial host collector with complete-frame evidence,
and a versioned minimal DT template generator that refuses stale/unready CPU
slots. Both workers are confirmed running, not inferred from old lock files.

Observer revision d8043381 adds source/bootargs identity plus private boot-video,
RAM envelope and resident bounds without adding target API calls. Eight controls
pass; actual07:12:06UTC capture again showsUSB63,zero secondaryflags,WFEfalse,
zero exceptions. ADT and slot digests match the previous observation. Private
video/address fields are omitted from public observation02. These new inputs
are for offline rejection tests; no current template or hardware permission
is inferred. Current profile must fail before producing a boot template.

## Physical versus usable RAM correction

An actual geometry check rejected the hypothesis that the inherited framebuffer
is inside bootargs usable RAM. Usable memory is25,095,569,408 bytes; the display
begins75,399,168 bytes beyond that pool. Do not enlarge normal Linux RAM to make
that check pass. Extended observer now reads resident ram_base/mem_size_actual
and verifies them against bootargs physical size and aligned physical base.
Actual07:14:18UTC observation03 establishes24GiB physical RAM and valid separate
framebuffer resource geometry, outside usable pool/resident image. No mapping,
cache, ownership or handoff success is inferred. Sourcefce3a310 and10 host tests
pass; all target calls remain metadata queries/RAM reads. Failed hypothesis and
corrected address-free checks are preserved in recovery/dt-input-geometry-*.json.
The DT generator still must refuse current0secondary/WFEfalse capture.

## Actual editor child execution resolved offline

Integrated diagnostic source1271866/dda8bbc as8ab88a0/7f1def5. Root verifies all27
source/evidence hashes and independently replays actual ARM64 Neovim under the
same read-only isolated root. Both signed formatters launch as real subprocesses
and exact output/idempotence plus the unchanged options callback pass. Neovim's
root-level /qemu pathname lookup caused the prior failure; identical bytes at a
nested absolute path pass without a permission/architecture bypass, binfmt or
namespace change. Earlier causal traces/failures remain intact. Full Conform
automatic selection is a separate running worker, not an inferred pass. No target
code, watchdog, core or protected storage action occurred.

## Complete physical-serial evidence transport prepared

Integrated944f643 as03fe1f5: strict length/SHA256/nonce response framing over
frozen RAM snapshots, atomic publication, exact physical-port/USB/ACM identity
matching and private partial-byte retention. Root reruns all75 controls with
actual pinned kernel/verifier/native BusyBox inputs, zero skips. A new root
rebuild matches archive8fd6f861…d16be1 (1,098,565 bytes). Prior a3a012/d9fac
archives remain unchanged. Controlled unverified-pyc execution is reproduced
and fixed by compiling exact pinned verifier source bytes without cache lookup.
Actual currentUSB63 proxy identity is rejected by discovery with no serial
open/transmission, as recorded in recovery/collector-proxy-rejection.json. This
is a negative identity test, not a working live Linux channel. No init or probe
ran. Webcam07:25:45UTC still reads Running proxy; no reboot or target state
change. New physical framing/guardian/USB and recovery remain UNTESTED.

## Real Conform integration independently replayed

Integratedd8b23ac as8db9eba. Root verifies13 source/evidence hashes, replays
actual signed ARM Neovim + real signed-package Conform plugin under the strict
read-only namespace, and matches all2,374 extracted member rows exactly.
conform.format() receives no explicit formatter list: actual filetype selection,
builtin argument handling, vim.system execution, buffer diff/edits, idempotent
no-edit result and missing-command refusal pass. Only supported command/prefix
overrides provide QEMU dispatch; plugin/runner checks are unchanged. Full
LazyVim/Mason, native target dispatch and whole-transaction installation are
UNTESTED. This is actual plugin execution, not mocked options-callback evidence.

## Pinned DT generation and current-input refusal

Integrated66557cd as52241f6. Root runs all65 controls using exact qualified
source/artifacts and frozen private input03: PASS, original capture unchanged,
actual input refuses before DT/output creation. Positive minimal and strictANS
fixtures are independently constructed, synthetic and UNRELOCATED. Exact
canonical re-render/compile equality closes reproduced semantic-only validator
gaps; pinned source-byte execution closes reproduced helper-cache bypass. DTC
warnings/errors stay fatal with diagnostics retained, not disabled. Current
0secondary/WFEfalse observation is a prerequisite failure, not a regression of
the prior12-core Linux result. No target access, core start, watchdog, staging
or boot occurred. Separate offline bundle framing is the remaining active
preparation lane; hardware qualification still needs supervised recovery.

## Separate resident/child placement remains mandatory

Read-only source audit confirms that the generic6249 proxyclient chainloader
chooses resident u.base and its copy stub overwrites that image. It cannot be
used with a DT that preserves the installed resident's release table. Historical
test52 instead allocated a separate PIC child beyond resident end; its legacy
helper is still unsafe to reuse unchanged because it includes PMU --reset and
old artifact/session/watchdog operations. recovery/staging-source-hazard.json
records both exact source hashes and required future live placement checks.
The offline container builder provides no staging/placement qualification.
No helper was executed and no target state changed.

## Final offline native container preparation

Integratedda631b8 as68a0b63. Root verifies five source hashes and independently
runs all30 controls, no skips, with central DT/observer/probe proofs and actual
qualified loader/ELF/Image/initrd inputs. Complete flat3538944 bytes and payload
offset0x360000 are distinct from file_end0x140000; Image memory16121856 fits
the exact32MiB copy offset. Six host-only pinned C checksum vectors match zlib.
Current frozen capture03 API and assemble CLI refuse secondary/WFE admission
before reading DT proof or creating diagnostics/container output. Captures and
all older artifacts remain unchanged. Synthetic positive bytes never combine
real candidate components or qualify a native consumer/placement/boot.
The earlier model-capacity failure was resumed in the same worker/scope; no
model change, target access or authority change occurred.

This goal continuation is PROGRESS, not an external-gate-only turn: actual ARM
Neovim/Conform execution, serial framing, pinned DT generation, CRC/container
checks and resident-overwrite hazard documentation were completed and replayed.
All safe preparation lanes are now frozen. The pending physical-recovery
availability question remains unanswered. No next RAM boot is authorized while
that supervised window is missing and remote recovery remains unverified.
GPU/DCP XNU capture and protected persistence remain separate later scope.
The goal is incomplete; this checkpoint does not claim ongoing unseen work.

Final07:45:43UTC webcam readout still shows Running proxy; USB63/8e0cf28
identity unchanged. The capture returned a minor MJPEG decoder warning; actual
JPEG was viewed and text readable. Address-free observation/hash is retained
in qualification/proxy-checkpoint-0745.json; raw screen stays private. No
Fingerbot, reboot, core, PMU, timer, target code or protected write was used.

## Read-only staging geometry prerequisite

Previous goal continuation classified PROGRESS. A remaining concrete source gap
was found after that checkpoint: no reviewed separate-child placement model
exists yet. The generic helper overwrites resident memory and the legacy PIC
helper cannot be reused unchanged. Safe offline planner development is now
active in the build lane; it has no target/stager/boot interface.

Root added a separate RAM-only observer without altering pinnedfce3 source or
old inputs. Twelve host controls pass after the initial red helper stubs.
Actual07:54:40UTC capture01 preserves199 ADT ranges and double-stable resident
heap/CPU/bootargs/ADT metadata,USB63,zero exceptions. It reads rawheap_base and
limit rather than calling mutating heapblock_alloc(0); address-only bootargs
query avoids the old helper's hidden physical read8. Rawprivate inputs/hash
bindings are retained; public recovery/staging-memory-observation-01.json has
no absolute target addresses. Secondaryflags0/WFEfalse still prevent handoff.

Host llvm-objdump aborted on the paired ELF. Original artifact is unchanged.
Narrow raw-function decoding via llvm-mc succeeds and independently resolves
the high-water load to the paired heap_base symbol; no ELF parser or allocator
execution pass is inferred. No target allocation/write, core/WFE/PMU/timer
change, staging or boot occurred. The pending physical availability request
still has no answer.

## Lossless T6040 performance inputs and strict staging checkpoint

The requested Gravity-first follow-up compares the current working M4 code to
this actual T6040, rather than changing a model ID. Current upstream kernel
4fc326f6 and Mesa87ac51d refs are unchanged. A new source patch eb40b68 adds a
core-only Rust decoder/module for the measured16-state/two-bank ADT shape.
Actual replay verifies all64 core/SRAM records, repeated/descending index
order, distinct voltage banks and mirrored secondary properties. Exact200000
sampling clocks remain intact alongside8ms; deriving clocks from ms loses8000.
Seven host tests pass after an observed red preservation test; no_std AArch64
object compile passes. The first Linux target compile lacked its core library;
the installed softfloat core target succeeds without suppressing checks.
Actual kernel-crate compilation now passes on combined-source5628d35c with exact6c config and3174 layout blocks/16413 field checks. No runtime caller, GPU model
admission, register window or firmware serializer changed. GPU INIT/compute,
DCP and accelerated desktop remain UNTESTED/BLOCKED on coherent early capture.
M2/M3 static SGX inputs were compared first; their unpopulated counts cannot
qualify runtime ladder reuse. See graphics/PERF-INPUTS.md and result JSON. Root independently verifies source/object/config/build-log identities, ELF64/AArch64 and the exact2-file diff; the actual compile is not independently repeated. All12 warnings retained. Historical abbreviated-ref refusal/aborted baseline build are preserved in infra/g16-perf/attempts.json. Full Image/module link remains UNTESTED for5628d35c; original8f2 artifacts unchanged.

Integrated build-lane11a3450 as f3ec24b. Root replays ten interval tests and the
actual6249 find_ram function's six cases under both GCC and Clang with fatal
ASan/UBSan. Frozen capture01 reproduces the strict full-advance refusal: current
heap lies inside a protected range; CPU slots/WFE also unready. No placement,
reservation or actual container exists. A nonwriting allocator-advance contract
is deliberately deferred, not silently assumed to own skipped firmware memory.
See infra/staging-plan/README.md and qualification/staging-plan-root.json.

Fresh11:17:06UTC webcam image was viewed: Running proxy. Both camera samples
have no decoder diagnostic and USB63/8e0cf28 unchanged. Raw images remain private;
address-free qualification/proxy-checkpoint-1117.json records this observation.
No proxy code execution, target allocation/write, watchdog/core/PMU change,
Fingerbot, boot or protected write occurred. Physical recovery availability is
still unanswered. The current work made offline code/build progress; overall
native accelerated persistent Omarchy is incomplete.

## Supervised RAM boot01: executed; USB configuration failure isolated

User explicitly returned and authorized supervised RAM boot/hardware tests,
physical power fallback, webcam monitoring and no Fingerbot/protected changes.
Initial screen black/USB absent; user power-cycled. Fresh proxyUSB66 returned.
A new startup helper's first attempt failed before CPU changes because it
omitted protocol feature negotiation after the observer's sentinel mode. Failed
source/result retained privately. Explicit feature0 negotiation keeps real
transfer checksums enabled; second invocation starts eleven resident secondaries
with exact ADT MPIDRs, idle slots/WFEtrue and zero exceptions. No payload upload
or watchdog action belongs to that startup step.

Fresh CPU and bounded staging captures bind new BA/ADT identities. Actual
session DT and19,414,811-byte native container55f46da9 assembled/independently
verified. Separate clear64MiB child passed reviewed nonwriting-advance contract;
reserved gaps were skipped, never made writable. Actual allocator instruction
bytes/high-water and resident release slots rechecked. Container/BA read back
twice, caches maintained, vector acknowledged. A code review caught duplicate
state-attempt, durability and stale-DT linkage gaps before staging; process
lock, fsync/atomic intent and full current-capture canonical-DT revalidation
resolve them. Only copied BA top_of_kernel_data changes; all padding retained.
See qualification/supervised-ram-boot-01.json.

Linux reached diagnostic init and exposed the exact RAM-probe gadget descriptor.
Host SET_CONFIGURATION1 timed out-110; no ACM interfaces/tty, so no framed
status or Linux online-mask observation. NO storage probe command was issued.
The webcam showed Linux messages then the installed proxy again. Host timeline
has gadget disconnect about63s after original proxy disconnect; USB71 returned.
User confirms no further power action. This establishes one automatic recovery
cycle for this exact diagnostic, not all kernels. Read-only PMU count is1;
loader's existing zero-health guard remains. Separate exact one-byte clear
operation is prepared/mock-tested and awaits explicit user approval; no clear
or policy write has occurred.

Root measured USB1 DART PARAMS3 at both actual ADT-bound banks:0x2a2a0202,
version2.2,42-bit PA/VA, zero exceptions, no DART write. The previously working
4ff source has v2.2 command/IRQ handling absent from8f2. USB topology matches;
EP0 differences are formatting only; gadget/core/f_acm/u_serial/configfs match.
Build lane is porting the narrow versioned command/exception path, preserving
legacy behavior and mapping/locked-root/display code. Hardware causality remains
a hypothesis until the next test. Integration lane prepares exact new kernel
probe bindings without changing init/collector behavior. Original artifacts and
unrelated working-tree omarchy/j614s_preflight.py edit remain untouched.

## USB DART v2 candidate: prepared, awaiting one-byte approval

Integrated USB lane63af59c. Source5cbc8c64 changes only apple-dart.c above8f2;
measured2.2 command/exception regression controls pass under both fatal-sanitizer
compilers, legacy/mapping code preserved. One full Image+18module build passes;
root independently verifies artifact integrity, exact config and source bindings.
Image09a52425; all18modules unchanged. This is not a hardware USB fix claim.
Probe6311976c changes embedded metadata only; init/collector/modules unchanged.

Root updates DT/bundle/stager hashes deliberately;65 DT and30 native-bundle
host controls pass with new artifacts and no skips. Actual USB71 CPU-ready and
staging captures bind session BA/ADT and resident slots. Initial DT invocation
omitted storage-diagnostic flag; bundle refused before output. Preserved failed
inputs/report, regenerated a separate correct storage template, then assembled
and independently verified19,414,812-byte container40bec115. Reviewed separate
64MiB geometry remains clear; pure plan opened no target interface. New candidate
NOT staged/vector-executed. Webcam shows installed proxy after11core startup.

Exactly one PMU diagnostic-byte clear1->0 still awaits the explicit question's
answer. No clear has occurred. The loader's zero-health check remains intact.
Once approved, root uses only clear_supervised_health.py with current USB71 and
new private result; then rechecks session/slots and executes the single-use
RAM-only stage/vector. Establish fully framed status first, qualify Linux masks
and empty module state, then at most one separately framed diagnostic probe.
Do not repeat a health clear from this one grant, weaken guards, touch protected
boot/disk state, or use Fingerbot. Candidate hardware result remains UNTESTED.

Independent fresh source/build02 at exact5cbc reproduces Image and all18modules,
plus seven supplemental artifacts. All24manifest entries compared; rawlog alone
differs, with path-normalized line-multiset equality. Integrated lane8ebf952.
Root independently verifies23artifact pairs, distinct inodes and two clean source
checkouts; qualification/usb-dart-reproduction-root.json. No hardware action.
Exact5cbc branch codex/j614s-usb-dart-v22 is published under the authorized
garethpaul/omarchy-m4pro-linux fork; remote SHA verified. Pending one-byte clear
approval still prevents next handoff. No diagnostic-byte write has occurred.

User reported power-cycle. Fresh14:29UTC observation still sees USB71, identical
BA/ADT/slots,11resident flags/WFEtrue/idle,0exceptions. Webcam Running proxy;
MJPEG decoder diagnostics preserved. Do not infer another reset from this state.
Read-only PMU counter remains1; power-cycle report does not grant its clear.
The precise one-byte approval question was clarified; no write/stage/vector.
Fresh actual inputs/template/container39564332 verify; pure plan matches the
reviewed64MiB geometry. Initial host diagnostics path was inside capture parent;
guard refused. Exact unchanged capture copied to its own evidence directory,
input pathname corrected, validation passes; no guard weakened or target write.
See qualification/supervised-powercycle-check-03.json. Latest private context
is supervised-ram-03/context.json; supersedes02 only for a later approved test.

## Independent continuation while PMU approval is pending

Previous turn is PROGRESS: fresh actual observations, canonical template/container
and plan verified, saved asbb629e0. It did not grant or perform the byte clear.
Current kernel/mesa upstream refs remain4fc326f6/87ac51d. Public same-board
Wallace55f116dd compared to this fresh ADT: all45OPP frequency candidates match
its7/19/19tables, but14vs12CPU topology and current-machine power semantics
remain distinct. Its32-bit rate overflow fix is already present in5cbc; no
duplicate patch or guessed cpufreq alias was introduced. Exact source/evidence
hashes recorded in cpu/power/evidence/wallace-source-comparison.json.

Two independently safe source lanes resumed: C tests the remaining actual full
LazyVim/Mason startup gap in the isolated ARM runtime; D implements the host-only
canonical preparation step of the requested automated test loop after the two
observed ad-hoc packaging refusals. Both have no physical target authority.
The hardware-ready5cbc artifact/pins are frozen; stage/vector and byte clear
remain root-only, pending the unanswered exact approval. No new target action.

## Host preparation and full packaged editor: root-completed continuation

Both source workers hit a service-capacity error after leaving complete code
and runtime observations. They are terminal, not silently running. Root took
over without model change: reviewed/frozeff50dcb host helper, integrated529d074,
replayed15unit controls then performed the first full actual-input canonical
generator/assemble/verify/PLAN run. Context0b5642c6, new container revalidated;
independent old/new geometry and original/final BA comparison agrees. Two full
CLI negative cases refuse a false storage-diagnostic flag or mismatched USB before
output. No stage state/target interface. See qualification/preparation-root-04.
Root's initial local cherry-pick preceded fetching the separate clone; no helper
executed in that failed integration attempt. Exact branch fetch resolved it.

Full packaged52spec LazyVim, actual Mason setup and stock Conform shell/Lua
commands pass in lane12 and independent root13. Signed native ARM64 formatter
bytes produce expected edits and idempotent second passes. Existing kernel
binfmt PF handler permits implicit QEMU dispatch; registry unchanged before/after,
current interpreter pathname hash verified, but registered F FD bytes unobserved.
No native Mac/performance claim. Missing Git/parser inputs in the minimal test
root were supplied from declared signed/sealed sources; no production defect
survived. Sealed-baseline Curl8.22 closure is verified; actual DNS/registry
lookup exits6 in unshared network. No8.23 download,151model change, install or
Mason registry pass. Frozen104103a integrated6404535,10,023member manifest rows
identical. Earlier failures retained; final checker refuses optimized Python.

Main hardware gate is unchanged: PMU byte1, exact one-byte clear unanswered,
new5cbc never staged/vector-executed. Protected boot/storage and Fingerbot
untouched. Latest host-prepared private context is preparation-root-04/context.
Live rechecks and concrete approval remain mandatory before its use.

Bounded nvim6 build prerequisite probe: the upstream starter main803bc181
archive still exactly matches pinned d865d502 (7570bytes). No source checksum
was bypassed. Host dependency query reports shfmt/stylua/nodejs/npm absent; no
host install. Existing Docker socket denies access; no escalation. Sealed ABI
extraction deliberately omits executable modes/root aliases/non-ABI files; it
is not a runnable rootfs. Three disposable namespace probes retain mountpoint,
mode and loader failures; only tmp-overlay metadata changed, original hash/mode
unchanged. No source build/package ran. qualification/nvim-build-prerequisites-01
records this honestly; a complete disposable build environment remains needed.
The5cbc hardware candidate is unaffected; pending PMU clear is still unanswered.
