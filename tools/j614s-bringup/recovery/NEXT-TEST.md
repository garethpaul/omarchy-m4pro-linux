# Next supervised RAM test

**PARTIAL: host preparation complete; pending exact one-byte PMU clear approval.**
The operator explicitly authorized supervised RAM boot/testing and can power-cycle.
Boot01 reached diagnostic Linux and then returned automatically once, confirmed
by the operator taking no further power action. That is not general recovery
qualification. Never touch Fingerbot or protected boot/storage configuration.

| Component | Candidate / evidence |
| --- | --- |
| Preserved resident |8e0cf28, flatfb31c765; current USB71,11idle resident secondary flags/WFEtrue,0exceptions |
| RAM loader |6249e0ec, flat2309dfbb, unchanged; independent reproducibility proof in infra/native-loader |
| Kernel |5cbc8c64, Image09a52425, exact6c config; narrow measured DART2.2 command/exception port |
| Initrd |6311976c, only metadata differs from earlier8fd6 archive; init/collector/module bytes unchanged |
| Session template / container |Actual USB71 storage template, container39564332,19,414,812bytes; independently verified |
| Host checks |65DT controls,30native-bundle controls, new components independently verified; no skips |
| Placement |Separate clear64MiB child, reviewed nonwriting heap advance; pure plan only, candidate not staged |

See [boot01 evidence](../qualification/supervised-ram-boot-01.json),
[preparation](../qualification/supervised-ram-02-preparation.json),
[fresh recheck](../qualification/supervised-powercycle-check-03.json) and
[DART source/build evidence](../infra/usb-configuration/README.md). Private
context contains exact paths/hashes and dynamic addresses; do not publish it.
Historical USB63/66 captures and addresses cannot substitute for current checks.

Root-only continuation:

1. Await the already asked exact PMU diagnostic-byte clear1->0 decision. If
   approved, use only clear_supervised_health.py, currentUSB71 and a new private
   result. Preserve write intent and readback. No watchdog reset helper or retry.
2. Recheck webcam/USB/resident identity and all live data/allocator/idle slots.
   Run supervised_child.py stage with the explicitly hashed private context;
   complete full readbacks and cache maintenance. Then its single-use vector.
3. Watch webcam and physicalUSB1-9.3. Obtain one complete framed status response,
   validate Linux online/present masks and no NVMe modules before proceeding.
4. If eligible, issue at most one exact framed diagnostic probe, collect results
   and logs; no mount/data workload/reset/reprobe or weakening ownership checks.
5. Observe automatic return; if it fails use the available operator. Do not infer
   successful recovery from a countdown. Preserve every failure and uncertain
   vector state; no automatic second attempt or repeated health clear.

The watchdog may be reprogrammed by the kernel. Init neither arms nor feeds it.
The50ms read-only guardian is non-atomic, not a write-proof guarantee. GPU INIT,
XNU capture and persistent installation remain separately gated later work.
