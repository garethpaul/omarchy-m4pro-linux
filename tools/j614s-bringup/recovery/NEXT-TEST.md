# Next supervised RAM test

**BLOCKED on current operator availability.** Remote recovery remains unverified;
manual power-cycle is the only proven fallback. The overnight mission forbids
an unattended reboot in this state. The unrelated KVM Fingerbot must never be used.
No new loader/kernel/initrd has been staged or executed.

Inputs prepared and independently verified:

| Component | Exact candidate | Evidence |
| --- | --- | --- |
| Resident object, preserved |8e0cf28, flat SHAfb31c765…f3afb | `resident-cpu-observation-03.json`; paired local ELF, live identity, zero exceptions |
| Unappended RAM loader | source6249e0ec; flat SHA2309dfbb…a0e00 | `../infra/native-loader/repro-after.json`; seven artifact pairs match |
| Kernel/Image | source8f2f3d1; Image SHAf9d7b637…4604 | `../infra/gravity-combined-reproducibility.json`; Image+18 module pairs match |
| Offline initrd | SHA8fd6f861…d16be1 | `../integration/boot-probe/artifact-manifest.json`; two archives match,75 tests; root rebuild matches |

These separate artifacts are **not yet a complete boot bundle**. Before any
staging, the primary agent must bind a fresh DT and CPU-release table to the same
live session and verify all appended sizes/CRCs/addresses. The current readonly
observation is USB63 with zero secondary flags/WFEfalse. Old USB45 addresses and
old package/chainload scripts cannot substitute for new session checks.

The first safe continuation command is the read-only observer with an absolute
qualified development Python path, the retained m1n1 source and a new private
output filename. It performs no watchdog/core/release-slot changes.

Once the operator confirms physical recovery availability, primary-only work is:

1. Recheck webcam and pinned proxy/ELF identity. Qualify resident secondary startup
   and idle slots under supervision using the earlier proven CPU framework.
   Existing helpers that start cores or arm timers require this supervised scope.
   Do not call the legacy capture helper as a read-only operation.
2. Generate/validate the session DT from live ADT and qualified resident slots.
   Keep the restricted4GiB owned RAM, exact USB2 peripheral path and strict ANS
   diagnostic topology. No firmware/cache address can be copied across sessions.
3. Bind the reproduced loader/Image and current initrd, preserving every original
   object. Do not use the legacy chainloader's PMU `--reset` path. A nonzero PMU
   health byte must refuse; no health counter clear is authorized by this plan.
4. Review the concrete RAM-only staging/vector plan and its carveout/size/CRC
   checks before executing. No disk, protected container, persistent entry,
   firmware flash or security policy change belongs to this test.
5. Establish the new physical ACM channel and collect one fully framed `status`
   response before considering the separately gated single-shot `probe`. The
   host collector must match the exact physical port and gadget identity; the
   current proxy correctly fails discovery before any tty open.
   Record CPU masks, watchdog state, module/admission logs and RO block counters.
   Strict ownership refusal is a PARTIAL/blocked result; do not weaken admission.
6. If USB or the kernel fails, use the physically available operator. Do not infer
   recovery from a countdown or reuse another machine's Fingerbot.

The kernel may alter watchdog timing. Init neither arms nor feeds it; this does
not prove a reset deadline. The RO guardian is a50ms poll, not atomic media
protection. No data workload, mount, reset or reprobe is exposed in this init.
GPU INIT/body capture, XNU/macOS staging/boot and persistent installation remain
separate later gates. This plan grants none of their protected authority.
