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
