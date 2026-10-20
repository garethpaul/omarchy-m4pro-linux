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
