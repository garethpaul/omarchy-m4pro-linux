# Read-only recovery observation

`observe.py` records candidate USB identities and fresh webcam frames around a
manually supervised experiment. It cannot reboot, send input, modify a disk or
renew a watchdog. Run it only from the primary hardware-control lane; the camera
must be free. Evidence directories must be new and should remain private because
screen images may contain personal data.

```sh
python3 recovery/observe.py --output /private/new-test-evidence --seconds 120 --camera
python3 -m unittest discover -s recovery -v
```

Each frame discards the first 15 incoming frames, records the image hash, host UTC
and elapsed time, and samples USB before and after capture. This reduces stale
first-frame confusion; it does not establish which OS is running. The collector
omits serial numbers and never treats a completed capture as a recovery pass.

Camera failures produce `PARTIAL` evidence and remain in the timeline. JPEG marker
checks establish a complete output file, not that every pixel is error-free;
`decoder_diagnostic` records when ffmpeg reported a decoding diagnostic.

The operator manually restarted the target after the Apple startup error; the
exact m1n1 proxy is available again. USB enumeration and KVM connectivity alone
do not meet the overnight requirement for independently verified recovery. No
unattended reboot is authorized on this evidence. The KVM Fingerbot is attached
to another machine and must not be used for this target.

## PMU observation without an automatic reset

```sh
python3 recovery/read_pmu_counter.py --m1n1-source /path/to/qualified-m1n1 \
  --output private-new-result.json
```

Use the development Python environment containing the m1n1 client's dependencies.
The reader requires the exact proxy product, T6040/J614s board4, firmware build,
ADT-translated generation3 SPMI geometry, primary slave and scratch address. It
sends one transient SPMI read request and validates its complete response. It
never sends a PMU data-write command, changes the counter, arms/disarms a watchdog
or reboots. An occupied FIFO is rejected before issuing a command. Optimized
Python is prohibited so assertions cannot silently disappear.

Host negative tests cover identity/translation mismatch, occupied FIFO, invalid
response and nonzero count preservation. The actual restored target returned
count0, no recorded proxy exception, and an empty FIFO before/after; watchdog
state was unchanged. This reads the count after a manual restart. It does not
establish what caused the preceding fallback.

## Resident CPU slots without starting cores

```sh
python3 recovery/read_resident_cpus.py --m1n1-source /path/to/qualified-m1n1 \
  --output new-private-cpu-observation.json
python3 -m unittest discover -s recovery -p test_resident_cpus.py -v
```

This observer pairs the exact local ELF with the pinned installed flat binary,
checks the live proxy/board/firmware and RAM bounds, double-reads live ADT and
resident slots, and derives CPU identities from that ADT. It never invokes CALL,
starts cores, changes WFE, arms a watchdog or writes a release slot. It computes
release addresses from the qualified table layout; it does not call
`smp_get_release_addr`, which clears argument slots. The older capture helper
also arms a watchdog and must not be treated as read-only.

Eight host controls cover stable/stopped/queued slots, torn reads, wrong active
MPIDRs, invalid extents/IDs, non-magic flag counters and direct API-call scope.
These controls do not prove atomic hardware coherence or physical core liveness.
The real07:04UTC observation in `resident-cpu-observation.json` has zero secondary
flags and WFE false after the manual restart. This is expected idle-proxy state,
not regression evidence against the earlier12-core Linux test. Old release-table
evidence from USB45 cannot qualify the currentUSB63 session. ASLR-dependent
addresses remain private. Recovery is still unverified and no cores were started.
