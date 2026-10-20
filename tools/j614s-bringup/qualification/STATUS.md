# Native M4 Pro qualification checkpoint

Overall **PARTIAL**. The target is Mac16,8 / J614sAP / T6040 (not T8132),
4 efficiency + 8 performance CPUs, 24 GiB physical RAM. Experiments currently
expose 4 GiB RAM. The machine is now in the installed m1n1 proxy, not a running
desktop. Previously observed test boots remain distinct from current state.

WORKS applies only to the named test scope. Compilation, synthetic serializer
replay and another Mac's GPU results do not qualify this hardware.

## Hardware source and comparison

[448-node ADT comparison](adt-node-comparison.json) supersedes the earlier
Linux-DTS-only comparison limitation. The machine's runtime ADT is compared
with vendor static M2/T8112, M3/T8122 and M4/T6040 trees from the same restore.
This preserves duplicate node occurrences with a #2 suffix. It records property
names/counts, not raw values or identifiers. Static-versus-runtime differences
are not automatically hardware changes. [Independent parser cross-check](../cpu/power/evidence/parser-crosscheck.json)
and [CPU/PMGR/CPM comparison](../cpu/power/evidence/adt-cpu-comparison.json)
provide narrower evidence. Per-client ownership, firmware state and register
semantics still require validation before driver reuse.

## All phases

| Phase / item | Status and measured scope | Missing piece / M3 or M2 reuse |
| --- | --- | --- |
| 0: m1n1 stage1 / RAM chainload | WORKS for existing test chain; [current cached metadata](proxy-current.json) has zero exceptions; tests51/56 reached Linux | Installed8e0cf28 object preserved. New source candidates are not automatically qualified. |
| 0: ADT / board DTS | PARTIAL: runtime capture and448-node comparison complete; test56 generated DTS booted | Complete T6040 domain/clock/client graph missing. Runtime firmware addresses must be regenerated, never copied across boots. |
| 0: CPU / AIC | WORKS in test51: all12 online,12M atomics,12K SIMD sleeps,12 pinned checksums; [result](cpu-test51.json) | M3 AIC3/secondary framework reused with actual MPIDRs; M4 WFIT/WFxT register corruption fixed by automatic platform quirk. |
| 0: PMGR / PMU / watchdog | PARTIAL: timer/interrupt/watchdog transport used; remote reset recently failed | Complete runtime PM and independent remote recovery missing; M3 layouts cannot be substituted wholesale. |
| 0: U-Boot / reboot / poweroff | UNTESTED for desired persistent path | Current tests RAM-chainload Linux directly. Existing U-Boot framework needs T6040 handoff and repeated cold-boot/rollback qualification. |
| 0: XNU hypervisor tracing | PARTIAL: owned RAM EL1/HVC and read-only MMIO tracing observed in prior exported HV evidence; XNU UNTESTED | Synchronous RAM hook completed then faulted. FMO correction compiled, not run; remote recovery and separately approved XNU boot required. |
| 0: firmware | PARTIAL: exact25G83 GPU/MTP firmware verified and transport tested | Firmware availability alone does not establish DCP/ISP/audio interfaces. Vendor payloads are not redistributed. |
| 1: NVMe / SART / DART | WORKS within read-only test52 scope:5.89GiB Btrfs scrub, no errors; [output](storage-test52.txt); test56 reports zero writes | Apple NVMe/RTKit/SART framework with J614s diagnostic offsets; writable persistence and recovery unqualified. |
| 1: PCIe | BLOCKED: no qualified controller enumeration in captured Linux baseline | T6040 power/reset/PHY/controller DT; apple-pcie framework reusable after node comparison. |
| 1: USB data / debug | WORKS for direct USB proxy and prior Linux gadget; [proxy identity](proxy-current.json) | USB2 inherited-state diagnostic path; this does not qualify SuperSpeed, PD or arbitrary ports. |
| 1: USB-C role / serial | PARTIAL: proxy/debug available; full Type-C host/device role UNTESTED | ATC PHY/role/PD integration missing; reuse DWC3 core, validate T6040 PHY sequences. |
| 2: internal display / Hyprland | PARTIAL: test52 stock desktop through inherited framebuffer; [sample](desktop-test52.json) | Native apple-dcp modesetting,120Hz/notch modes and DCP firmware ABI unqualified. RTKit/DART transport reusable, display profile is new work. |
| 2: brightness / ALS | BLOCKED: no qualified DCP brightness or AOP ALS path | DCP/AOP service and model integration; existing frameworks candidate only. |
| 2: GPU transport | WORKS for startup/quiesce only: protocol12, RUN clear; [dmesg](gpu-test56-dmesg.txt), [test56](gpu-test56.json) | Application INIT, full body/power graph and job submission still missing. This is not DRM acceleration. |
| 2: GPU ABI port | PARTIAL: actual Gravity source serializer compiled/replayed; [evidence](../graphics/gravity-port-result.json) | Current envelope implemented; coherent T6040 body/power/handshake capture required. Legacy output retained byte-for-byte. M3 data cannot be copied. |
| 2: OpenGL / Vulkan / compute | BLOCKED: no qualified AGX render node or completed M4 Pro GPU job | Matching Gravity kernel/Mesa compute path selected. Exact G16S configuration and INIT/first-kick capture needed before shader readback. Earlier Vulkan smoke crashed before a GPU job. |
| 2: external DP / HDMI | BLOCKED: captured KVM external display has no usable Linux signal | DCP-ext, ATC/DP crossbar and model routing; M3 transport framework candidate, no connector qualification. |
| 2: AVD / PipeWire capture | UNTESTED | AVD firmware/DT/DART and compositor capture path not qualified. |
| 3: keyboard / trackpad | PARTIAL: MTP keyboard physical input observed earlier; trackpad reports and pointer motion observed, user reported jumpiness | M2/M3 DockChannel-HID/magicmouse reused after reset/packet checks. Post-SMP physical smoothness, full Fn layout, backlight, gestures/palm rejection UNTESTED. |
| 3: Touch ID | BLOCKED: no qualified Linux SEP biometric interface | No reusable M3 fingerprint authentication implementation identified in inspected tree. |
| 4: SMC / battery | WORKS for read-only test42 telemetry; [sysfs output](battery-test42.txt) | Existing macsmc framework useful. Capacity/current/health are observations; charge-control writes deliberately unqualified. |
| 4: AC / charging / MagSafe | PARTIAL: captured supply status; power transition sampled earlier | USB kept supplying power, so complete AC/MagSafe removal not established. |
| 4: lid / power events | UNTESTED | macsmc-input event routing and controlled event capture needed. |
| 4: fans / temperatures | UNTESTED | Read-only hwmon binding/limits before thermal load; no fan curve qualification. |
| 4: cpufreq | BLOCKED: CONFIG_CPU_FREQ unset; [config](../infra/configs/j614s-clean-candidate.config) | Three T6040 CPM windows and changed PMGR/PMP need a qualified OPP/clock driver. Timer1000MHz is not CPU speed. [Power audit](../cpu/power/README.md). |
| 4: cpuidle / runtime PM | PARTIAL: ordinary scheduler idle and SIMD retention tested; CPU_IDLE unset | Formal cpuidle/runtime domain states missing. M4 wait-state quirk does not itself implement deep idle. |
| 4: suspend /20 cycles / drain | BLOCKED: CONFIG_SUSPEND unset;0/20 qualified cycles | Device suspend/wake plus reliable recovery required before lid cycles/drain measurement. |
| 5: Wi-Fi | BLOCKED: no qualified PCI enumeration / brcmfmac connection | ADT bcm4387 compatibility is not a measured PCI revision. Match PCI ID, board firmware/NVRAM/CLM before WPA3/5/6GHz/resume tests. |
| 5: Bluetooth | BLOCKED: no qualified HCI device/pairing | PCIe and exact device/firmware qualification first; hci_bcm4377 family is a reuse candidate, not a pass. |
| 6: MCA / ADMAC / speakers | BLOCKED: no qualified PCM/protected speaker path | Split T6040 ADMAC/SIO/audio routing and model DSP limits; speakersafetyd must protect speakers before playback. Existing M2/M3 framework candidate. |
| 6: headphones / mic / ISP | UNTESTED | ADT cs42l84 jack, AOP mic and ISP require device/firmware/model integration; no output/capture pass. Host observation webcam is unrelated to Mac ISP. |
| 7: ARM packages | PARTIAL:986-package image audit, signed native editor tests and116-package print-only resolution; [package plan](../omarchy/evidence/arm-package-plan.json) | vi unresolved; boot requests held; remaining payload signatures/hooks/live ABI not qualified. No full system upgrade run. |
| 7: shell / keys / notch / battery | PARTIAL: stock Hyprland/Quickshell/Foot test52 | Native brightness/volume providers, notch modes and final model profile depend on hardware qualification. No cosmetic workaround substitutes for acceleration. |
| 7: updates / persistence | BLOCKED: desired default boot not installed or qualified | Versioned kernel/DT/initramfs/firmware package, U-Boot cold boots and rollback; protected boot changes require separate authority. |
| 7: FEX / muvm / LUKS / snapshots | UNTESTED on the desired persistent installation | Device-mapper/encrypted initramfs, snapshot rollback and compatibility workload tests still required. No destructive conversion performed. |

## Build and performance evidence

CPU startup failure is fixed in the tested kernel, but there is **no matched
before/after desktop benchmark**. The earlier80–100% single-core report is not
comparable to test52's8.398% of one CPU over10.002seconds. Test52 used llvmpipe;
software-rendering environment variables in its evidence describe the old test,
not a proposed acceleration workaround.

The clean candidate is kernel f93a3416c60f26c68084134dc6c1d205becd5753,
release7.1.12-j614s-clean-candidate+. Full Image and15 modules compiled and passed
strict artifact/config/ABI/path audits. Two independent fresh builds are byte-identical for Image and all15 modules;
[comparison](../infra/clean-candidate-reproducibility.json). The earlier recipe1
comparison failed due to Rust absolute paths and remains recorded.
[Build recipe and retained failures](../infra/README.md).

[Crash-state draft PR](https://github.com/garethpaul/omarchy-m4pro-linux/pull/1)
is host-regression-tested and AArch64-object-compiled, not hardware-qualified.
Gravity envelope source is also build/replay-only. Original qualified payloads,
macOS/Recovery/1TR and storage layout remain unchanged by this checkpoint.

The [minimal Metal capture trigger](../capture/README.md) compiled on a separate
M1 Pro builder and verified its one/two-job readbacks. It has not run on this
M4 Pro. Its source/build protocol and14 corruption tests are retained separately.

## Next executable work, by dependency

1. Finish real Gravity module build with layout assertions enabled. The clean
   candidate rebuild comparison passed; publish reviewed experimental branches.
2. Prepare T6040-gated early APP INIT/first-kick observation using the published
   capture stack and a minimal source-built compute job. Body/power values need
   coherent evidence, not T8132 constants.
3. Independently verify a recovery method in a supervised window before another
   boot-sensitive test. Manual restart is currently the only proven fallback;
   the KVM Fingerbot belongs to another machine and must never be used.
4. Under separately approved XNU/capture scope, capture earliest initialization,
   port the justified body/power/UAT handshake, then run one fenced compute job
   with exact output and guard-region readback. Iterate on causal failures.
5. Qualify native render node/OpenGL/Vulkan and DCP modes, then repeat a matched
   Hyprland/input benchmark. Package the hardware profile only after real passes.
6. Qualify storage/reboot/U-Boot rollback and propose the concrete persistent
   installation separately. Protected boot/disk actions remain unapproved.
