# Actual-driver crash-state regression

**WORKS on the host: failure reproduced before the fix and passing after it.
Kernel hardware behavior remains UNTESTED.**

The harness compiles the actual `g16-bootstrap.c` from two immutable kernel
commits into a host test translation unit. It does not reimplement the driver's
state transitions or substitute a simplified state-machine model.

- Baseline: `4ff8816df8c4bc81b1652eca17fc8c0e9e1928cc`.
- Candidate: `0fb65dbd66f9b91a43096ecbabd52b81f73bea5c`.

`run-driver-regression.py` extracts those exact source versions with `git show`,
generates empty Linux include placeholders inside its ignored build directory,
and compiles `driver-host-harness.c` with the selected driver included directly.
The single harness file supplies fake DT, MMIO, device management and RTKit
facilities. Atomic operations use C11 atomics. No generated include stubs or
extracted kernel source are committed.

## Causal failure and fix

Fake `apple_rtkit_wake` negotiates protocol 12, invokes the **real driver's
registered crash callback**, then returns success. The same event ordering runs
against both unchanged driver source versions.

The baseline reproduces the defect:

```
FAIL: probe returned 0 after crash; observed RTKIT_READY protocol=12 rendering=unimplemented
```

That fixed-invariant test exits **1**. A separate expected-bug run also verifies
that the fake RTKit is actually crashed while the real sysfs callback reports
ready, so an unrelated early probe failure cannot count as reproducing it.

The candidate returns `-EIO`, reports `CRASHED`, and clears CPU RUN. Another
controlled interleaving calls the real crash callback after RTKit's running
state has been observed but before probe publishes readiness. The candidate's
actual atomic compare/exchange rejects that transition. This exercises the
publication race beyond merely checking the RTKit running flag.

The test also executes the real driver paths for:

- normal probe, sysfs readiness, quiesce, CPU RUN clearing and NOT_READY;
- a later crash followed by removal, preserving CRASHED without quiescing a
  crashed firmware instance;
- bad GPU identity, firmware identifier, board identity or powered-off GFX
  domain, each rejected before any CPU RUN write or RTKit wake call.

These are deterministic host interleavings, not a proof of kernel memory
ordering or a firmware crash induced on the Mac. The fake MMIO array is not
hardware; it establishes that the actual driver writes RUN only after its
qualified guards and clears it on the tested paths.

## Reproduce

```sh
python3 graphics/run-driver-regression.py --kernel-repo /path/to/kernel/repository --output graphics/build/driver-regression
```

Both kernel objects must exist in that repository. The script does not change
its checkout, build or configuration. It runs Clang with warnings as errors,
AddressSanitizer and fatal UndefinedBehaviorSanitizer. Unused-parameter warnings
are suppressed because Linux callbacks intentionally carry unused arguments;
no driver checks or test assertions are disabled. Four fake API declarations
are marked unused because the baseline does not call the candidate's newer
atomic/status facilities.

`driver-regression-result.json` records source hashes, compiler identity,
baseline invariant failure and candidate pass. Sanitizer output is retained in
the ignored build directory. No target connection, firmware execution or reboot
is part of this test.
