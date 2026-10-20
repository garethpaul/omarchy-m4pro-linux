# J614s CPU qualification

This lane adds repeatable qualification around the existing CPU fix. It does not modify the kernel, boot chain, disk, frequency, voltage, fan policy, or thermal policy. No new target measurements were made in this lane.

| Item | Status | Evidence |
| --- | --- | --- |
| Existing twelve-core startup / wait-state fix | WORKS within prior test51 scope | Parent `outputs/m4-smp-enablement/status.json`, kernel commit `1d78f77f80529c5323619a40b3280e82546ea841`; prior exact atomic/SIMD outputs retained under `tests/fixtures/` |
| Qualification source and AArch64 build | WORKS on development host | `test-results/aarch64-elf.txt`, `test-results/validation.json`; static AArch64 executables with no interpreter |
| Runner parsing and refusal checks | WORKS on development host | `test-results/host-tests.txt`; ten tests including corrupted saved evidence and wrong hardware |
| This runner on T6040 | UNTESTED | Target recovery is required; no lane access to hardware |
| New comparative performance result | UNTESTED | No matched baseline has been measured |
| cpufreq, cpuidle residency implementation, power / suspend | UNTESTED by this suite | Read-only observations are collected where exported; no driver functionality is inferred |

## Source preservation and attribution

`src/coherency.c`, `src/coherency-start.S`, `src/simd-context.c` and `src/simd-sleep.S` are byte-for-byte copies of the existing task's `work/j614s-smp/` files. Original comments and conditional code are retained. The qualification build never defines `HOST_VALIDATION`: target affinity checks remain enabled. No license or external authorship is invented for those previously existing local test sources. `test-results/validation.json` records source and fixture hashes. The CPU workaround itself remains in the existing kernel commit, including its existing attribution; this lane does not reimplement it.

The baseline tests established unchanged T6040 SMP behavior after the existing fix. This suite adds no M2/M3 hardware nodes or drivers, so it makes no new reuse claim. The exact 4E/8P MPIDR/type mapping comes from the ADT-derived test56 DTS and prior resident CPU qualification, not a generic M4 assumption.

## Build and host checks

Run from this lane's root:

```sh
LD_LLD=/path/to/ld.lld ./cpu/build.sh
python3 -m unittest discover -s cpu/tests -v
```

`CLANG` defaults to `clang`; `LD_LLD` defaults to `ld.lld`. Current build evidence uses clang 23.1.3 and Rust's bundled LLD 21.1.2. Both workloads are freestanding Linux AArch64 binaries with no target sysroot requirement. Build outputs remain untracked under `cpu/build/`. Cross-compilation is not an ARM execution test. The host has no `qemu-aarch64` executable available, and this lane did not run these binaries through emulation.

## Invocation when hardware recovers

Only the primary agent may operate the target. First recover the exact known-good proxy, verify independent remote recovery, and boot the separately qualified twelve-core Linux environment with its existing watchdog and read-only-disk protections. This suite neither arms nor disables a watchdog and never reboots. Do not run it from macOS, Recovery, a new unqualified payload, or an active m1n1 hypervisor context.

Transfer `qualify.py`, `build/coherency`, and `build/simd-context` to a **fresh executable tmpfs** directory `/run/j614s-cpu-suite/`. Then run this exact command on the Linux target, as a user permitted to read `dmesg` (normally root):

```sh
python3 /run/j614s-cpu-suite/qualify.py \
  --binaries /run/j614s-cpu-suite/build \
  --output "/run/j614s-cpu-result-$(date -u +%Y%m%dT%H%M%SZ)" \
  --samples 3
```

The output directory must be fresh and on tmpfs; persistent filesystem destinations are refused before any files are created. Keep the evidence in RAM until the primary collects it. Review/redact kernel CPU lines before publication. Do not transfer raw ADTs or arbitrary full kernel logs.

The runner requires AArch64, both `apple,j614s` and `apple,t6040`, exactly twelve present/online/allowed CPUs, the measured twelve DT MPIDRs with four `apple,sawtooth` and eight `apple,everest` CPU types, and no CPU-count/ordinary-idle workaround flags. It records logical topology exported by sysfs, and leaves missing logical-to-DT links as null rather than inventing them. It repeats topology checks after workloads.

The unchanged coherency binary pins twelve processes and requires the exact 12,000,000 shared atomic count. The unchanged SIMD binary pins twelve processes, checks all 32 vector registers over 1,000 nanosleeps each, and fails on any mismatch. Missing, repeated, unknown or failed-child output is rejected, even if a PASS marker appears. Each subprocess has a recovery timeout that kills its process group; that is a per-command safety bound, not a mission work limit.

SHA256 sampling runs twelve concurrent pinned processes, hashing the same 64 MiB on each CPU per sample. Each sample records digest, affinity, CPU seconds, wall seconds and MiB/second. Three independent samples are the default. It also records load average, available frequency-policy values, thermal sensors and cpuidle counters before/after. These are observations rather than requests to alter the machine. The timings include Python/OpenSSL overhead and do not establish native instruction throughput or a speedup. Compare only matched kernel, payload, workload, power, temperature and background-load conditions.

Ordinary-idle accounting must increase on every CPU during a two-second observation. This establishes accounting activity, not an electrical idle state or suspend reliability. Existing or new kernel BUG/WARNING/Oops/panic/SError evidence, unavailable logs, or rotated logs block a clean result. The output contains hashes of full logs and only relevant CPU lines; it never clears the log. Any exception records its failed phase and leaves `qualification_passed=false`. An explicit nonzero exit accompanies failure. A successful CPU-only result cannot establish GPU acceleration, smooth input, storage safety, persistent default boot, power management or overall Omarchy completion.

## Hypothesis / evidence ledger

| Question | Evidence | Interpretation / next discriminating test |
| --- | --- | --- |
| Are secondary CPUs still the desktop bottleneck? | Prior test51: online 0-11, shared counter 12M, 12K SIMD sleeps; parent status records software renderer | CPU-start failure was fixed. Run this suite on the next qualified payload to detect regressions. Do not attribute current GPU rendering limitations to single-core operation. |
| Does the automatic wait-state quirk preserve execution? | Prior CPU commit plus saved SIMD PASS; ordinary-idle flags absent in test51 | Existing measured fix; this runner rechecks the same workload without temporary workaround flags. |
| Has per-core performance improved? | No matched before/after dataset exists; old desktop process sample was 8.398% of one CPU over 10.002s | UNTESTED. Collect repeated sample JSON under matched conditions before claiming a speedup. |
| Do cpufreq / thermals / cpuidle operate correctly? | No fresh hardware reads in this lane | UNTESTED. Missing sysfs exports remain missing, and observation snapshots must not be treated as driver validation. |
| Can this lane perform the next hardware test? | Primary's baseline says recovery currently unavailable; lane is prohibited from hardware access | BLOCKED on recovery and primary execution. Sources, executables and commands are ready; no protected boot or storage changes are required by this suite. |
