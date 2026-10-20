# M4 Pro native Omarchy engineering

Goal: native accelerated, responsive, persistently bootable Omarchy. Overall INCOMPLETE.

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
