# Strict J614s inherited ANS source checkpoint

**PARTIAL: implemented and host-tested source. Hardware UNTESTED.** The immutable
source is `05af581d3bf7574d933044d509dd6c3617e8a111` on the separate
`agent/gravity-j614s-nvme` kernel branch. No payload, target, boot object, Recovery,
1TR, partition, firmware or desktop configuration was changed.

The initial blanket refusal is replaced only for the explicit
`apple,j614s-nvme-diagnostic` profile. Admission requires J614s/T6040, the measured
NVMe/ANS apertures and mailbox/SART providers, zero mailbox argument cells, and
no PM-domain/reset controls on the consumer, both providers or their ancestors.
A quarantined physical controller is refused before allocation. RUN, boot status,
LSQ and CC/CSTS must identify a healthy inherited session; a disabled controller
also requires the producer's existing explicit handoff contract. Generic M4
aliases and cold boot/reset fallbacks are absent.

The adopted initializer primes system endpoints before RX without fabricating a
firmware version. Queue pointers are replaced only after the inherited controller
is disabled, using the measured paired 32-bit address writes. The controller
retains its live RTKit session across subsequent queue resets. Inherited flushes
are synchronous and use BROKEN_FUA; persistent durability remains unqualified.
Legacy reset and timeout function bodies are retained byte for byte, as checked
by `source-wiring.json`.

A failed controller stop is not a DMA fence. It retains requests, queues, pools,
tagsets, owner/module references, diagnostic MMIO mappings and their reservations.
Quarantine publication and CQ polling share the CQ lock. RX/work is detached and
drained, while RTKit metadata, DMA and mailbox ownership remain reserved until
platform reset. This preserves objects referenced by an already-running timeout.
The successful-stop path relies on namespace/admin queue destruction to drain
timeout and queue readers before ordinary teardown; cancellation alone is not
claimed to do that. The existing already-dying admin-queue lifecycle assumption
remains explicit and needs hardware/concurrency validation.

## Executed checks

All selected-source C fixtures compiled with Clang, warnings as errors, ASan and
UBSan with fatal diagnostics:

| Fixture | Result |
| --- | --- |
| Exact topology and balanced fake OF references | 116 checks / 39 scenarios |
| Control/reset/stop/recovery and injected CQ-lock interleaving | 33 checks / 21 scenarios |
| Owner references, partial allocations, retained MMIO and cleanup | 79 checks / 23 scenarios |
| Admission and borrowed-buffer ownership/cache/DMA | 65,597 checks, including 65,536 individual unchanged-byte checks |
| RTKit inherited initialization, buffer identity, teardown and retained-state quiescence | PASS; original changed-live-buffer baseline fails corrected invariant |
| Failed-stop metadata teardown | PASS; paused-reader metadata remains valid after RX quiescence |
| Wiring/order and legacy-body assertions | 12 assertions |
| Sequential patch replay from b442 base | 21 patches; all 35 modified files byte-identical |

`idle-causal-baseline.json`, `poll-causal-baseline.json` and
`metadata-causal-baseline.json` preserve explicit reproductions. Each corresponding
old source also exits 1 on the corrected invariant. These are deterministic fake
interleavings and API contracts, not a real concurrent kernel or live DMA test.

The independent reviewer found the IDLE-completion and failed-stop reader issues
before admission acceptance. Its final review stopped automatically during
teardown analysis; earlier reviews and findings remain evidence, **not final
independent acceptance**. The primary agent subsequently inspected the ordinary
source contracts. Full AArch64 compilation, linking, reproducibility, actual
controller concurrency and hardware qualification remain separate gates.

## Reproduce

Use this integration commit's fixtures and a source repository containing the
immutable candidate and baseline commits. Give each invocation a new output path:

```sh
python3 integration/nvme/test_topology_source.py --source KERNEL --commit 05af581d3bf7574d933044d509dd6c3617e8a111 --output NEW_TOPOLOGY_OUTPUT
python3 integration/nvme/test_control_source.py --source KERNEL --commit 05af581d3bf7574d933044d509dd6c3617e8a111 --output NEW_CONTROL_OUTPUT
python3 integration/nvme/test_lifetime_source.py --source KERNEL --commit 05af581d3bf7574d933044d509dd6c3617e8a111 --output NEW_LIFETIME_OUTPUT
python3 integration/nvme/test_nvme_source.py --source KERNEL --commit 05af581d3bf7574d933044d509dd6c3617e8a111 --output NEW_BUFFER_OUTPUT
python3 integration/nvme/test_rtkit_source.py --source KERNEL --candidate 05af581d3bf7574d933044d509dd6c3617e8a111 --output NEW_RTKIT_OUTPUT
python3 integration/nvme/test_failed_stop_source.py --source KERNEL --commit 05af581d3bf7574d933044d509dd6c3617e8a111 --output NEW_READER_OUTPUT
python3 integration/nvme/validate_admission.py --source KERNEL --commit 05af581d3bf7574d933044d509dd6c3617e8a111
```

For the IDLE baseline use a430 with both `--expect-timeout-idle-bug` and
`--expect-poll-gate-bug`. For the isolated poll baseline use657 with only
`--expect-poll-gate-bug`; for metadata use657 and
`--expect-metadata-free-bug`. Omitting these flags requires the corrected
invariants and fails on those baselines. The recorded JSON contains full SHAs.

Apply the patches in `patch-roundtrip.json` **sequentially**, checking then
applying each with `--unidiff-zero --whitespace=error`. No firmware blob or raw
ADT is included. The exact candidate configuration remains SHA256
`6c5aba7745d918c528300c5a395fcd7db0c2b718acda7d1467af2816a8d56516`.
D's next compile-only combined source may add the independently reviewed checked
G16 MMIO and PRIME ownership fixes; those are not part of this immutable source.

Persistent installation stays BLOCKED pending a supervised read-only diagnostic,
real failure/teardown tests, independently available recovery, tested rollback
and later durability/encryption/snapshot qualification. Existing f93 hardware
results are not inherited by this new source.
