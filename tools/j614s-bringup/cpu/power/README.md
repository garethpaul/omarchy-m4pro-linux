# T6040 CPU frequency: measurement before a writable driver

Current frequency is **UNTESTED**. The tested kernel has `CONFIG_CPU_FREQ` and `CONFIG_CPU_IDLE` unset. The saved `1000MHz` line identifies the architectural reference timer; `2000 BogoMIPS` is calculated from that timer. Neither establishes a 1GHz CPU clock. See `evidence/source-evidence.json` and `evidence/test56-clock-evidence.txt`.

A low inherited CPU operating point could limit CPU throughput; no captured command/status register or matched benchmark currently establishes that cause. The known GPU renderer remains llvmpipe. This lane does not claim that frequency policy fixes the desktop, and changes no clocks, voltage, thermal policy or hardware state.

## Status

| Item | Status | Evidence |
| --- | --- | --- |
| Decode this machine's saved live ADT | WORKS offline | `evidence/adt-cpu-comparison.json`, live source SHA `77cedfd555eb507e0cac4d28354d4bd7532d6e4d409328ae4d50ddd74a53fd23` |
| Independent parser equivalence | WORKS offline | `evidence/parser-crosscheck.json`: all raw properties internally equal to m1n1 reference over 448 live / 362 M2 / 414 M3 / 546 static-M4 nodes; no payloads exported |
| Read-only register decoder and collection seam | WORKS against synthetic inputs | `evidence/host-tests.txt`: ten tests, including exact six-read sequence and stop after first exception |
| Actual J614s CPM register capture | UNTESTED | No target access performed |
| Reuse M3 address geometry | PARTIAL | First two physical apertures match, third added; all span 0x2000 in ADTs |
| Reuse M3 status/current-state field or writable driver | BLOCKED: missing J614s register semantics, indexing, ownership and thermal evidence | No T6040 alias or kernel patch added |
| cpufreq/cpuidle/power/suspend enablement | UNTESTED | No driver, clock or power transitions tested |

## Actual M2/M3 comparison

All selected CPU, PMGR, PMP and PMP-DART nodes have per-property differences recorded in `node_diffs`. Only property names and selected hardware data are exported. Full raw ADTs, calibration payloads, device identifiers and keys remain private. M2/M3/static-M4 baselines are manifest-verified **25G76 / 26.6.1** vendor trees; live M4 is a runtime capture. Absent runtime-populated properties in static trees cannot be called an SoC incompatibility.

| Field | T8112 M2 / J413 | T8122 M3 / J613 | Live T6040 M4 Pro / J614s |
| --- | --- | --- | --- |
| CPU nodes / clusters | 8 / 2 | 8 / 2 | 12 / 3, four cores each |
| CPU compatibles | blizzard / avalanche | sawtooth / everest | sawtooth / everest / everest |
| PMGR compatible | pmgr1,t8112 | pmgr1,t8122 | pmgr1,t6041 |
| Physical CPM apertures | 0x210e20000, 0x211e20000 | same | same plus 0x212e20000 |
| CPM aperture span | 0x2000 each | 0x2000 each | 0x2000 each |
| PMGR reg indexes of CPM apertures | 5,14 | 5,14 | 6,15,26 |
| perf-regs / perf-groups | perf-regs 64 bytes | perf-regs 96 bytes | perf-groups 756 bytes; no perf-regs |
| perf-domains bytes | 168 | 168 | 252 |
| cluster-ctl-offset value | 0x80000 | 0 | 0x20000 |
| PMP wrapper | ascwrap-v4 | ascwrap-v6 | ascwrap-v6; register window sizes changed |

Static M4 confirms the new perf-groups/domain/control layout, so those structural differences are not solely runtime population. Its SRAM tables remain unpopulated; the live tables contain 7 / 19 / 19 entries under `voltage-states1-sram`, `voltage-states5-sram`, and `voltage-states13-sram`. Their first/last frequency **candidates in kHz** are 1020000/2592000, 1260000/4512000, and 1260000/4512000. This interpretation follows the existing J616s m1n1 source and is not measured frequency or a proven J614s pstate index mapping.

The inspected Linux M3 DTS uses the T8112 fallback compatible and maps the first 0x1000 bytes of each CPM aperture. That driver obtains current pstate from status offset 0x50, bits 9:5, and sends writes at offset 0x20 using low5 state, SET bit25 and BUSY bit31. T6040 ADT geometry cannot prove those bit meanings. The generic command fallback explicitly ignores boost limitations, so request readback must not be reported as actual clock.

The exact installed-source revision `8e0cf288beec26defb196f23599ea2f6f1bd504e` contains a separate T6040 implementation guarded to **board6 / J616sAP**. It rejects this machine's **board4 / J614sAP** before CPM reads. Its comment says only states1/2 have been tested on J616s; that is source history, not hardware evidence for J614s. Preserve that guard. No writable M3-compatible alias or guessed OPP table is justified yet, so this lane provides the decoder and read plan instead of a kernel/DTS patch. No candidate node is enabled.

## Reproduce offline

From the lane root, with private source files supplied by the primary:

```sh
python3 cpu/power/layout.py \
  --live LIVE_ADT \
  --m2 J413_ADT \
  --m3 J613_ADT \
  --static-m4 J614S_STATIC_ADT \
  --output COMPARISON_JSON
python3 -m unittest discover -s cpu/power/tests -v
```

The parser follows m1n1's MIT ADT format reference and adds strict bounds, duplicate-field and span checks. Runtime capture has a 11920-byte zero allocation tail within a 16KiB boundary; only that bounded zero-padding form is accepted. Truncated or nonzero trailing bytes fail. `crosscheck_adt.py` independently compares parsing to `ADTNodeStruct`; it requires the existing m1n1 proxyclient dependencies and emits hashes/counts only. Original Asahi MIT notice is preserved in `LICENSE.m1n1`; no Linux GPL driver source is copied.

## Exact next probe: primary only, after recovery

`next_probe` in `evidence/adt-cpu-comparison.json` specifies exactly three candidate 64-bit addresses: **0x210e20020, 0x211e20020, 0x212e20020**. Collect twice without writes. This is an untested access plan, not evidence that read access is safe on J614s. The primary must first restore the known-good resident proxy and independent recovery, establish idle proxy identity, preserve its existing watchdog, freshly decode its live ADT, and verify that firmware already powers each relevant cluster aperture. Do not power a block merely to probe it. Stop on any exception, candidate BUSY bit, changing low5 or geometry mismatch. Do not probe status/PLL offsets until access and semantics are independently justified.

After those preconditions, this exact integration seam uses the primary's already-qualified proxy objects:

```python
from layout import project
from decode_snapshot import capture_with_reader, decode

live_layout = project(fresh_live_adt_bytes)
snapshot = capture_with_reader(
    live_layout, p.read64, p.get_exc_count, p.get_chipid()
)
interpretation = decode(live_layout, snapshot)
```

The helper opens no transport and touches no watchdog. Tests prove its callback sequence contains only six exact command reads plus exception-count queries. The primary supplies the fresh ADT bytes from its existing checked BootArgs routine, and saves `snapshot` privately. `decode_snapshot.py --comparison COMPARISON_JSON --snapshot SNAPSHOT_JSON --output DECODED_JSON` is an offline CLI alternative. It rejects identity/hash/width/address/exception/state mismatches and preserves both zero-based and one-based table-index hypotheses. Even a stable low5 value yields `PARTIAL` and `hardware_frequency=UNTESTED`.

For actual frequency, compare independent CPU cycle counts against the architectural timer under a pinned workload if a qualified PMU/perf path exists. A pstate request is insufficient: firmware may throttle below it. Collect available Linux frequency/thermal/load snapshots using the companion qualification suite, and repeated per-core timings under matched conditions. Missing counters or policy exports remain UNTESTED. Before any DVFS writes, establish state indexing, current-state status semantics, retained PMP/CLPC ownership, limits, transition timing and a working temperature/thermal rollback policy. Do not bypass these gaps by exposing all SRAM entries as operating points.

## Same-board public source cross-check

The public [Wallace checkpoint55f116dd](https://github.com/damsleth/wallace/tree/55f116dd0e0f28d1412c6be728a101f7d861c473)
provides a useful independent comparison, not qualification of this Mac. Its
three OPP frequency sequences match all45 entries in our freshly captured
ADT7/19/19 SRAM tables. Its14CPU consumer topology differs from this12CPU bin
and cannot be copied. The shared numeric frequency inputs do not prove our
state indexing, access safety, retained ownership, actual clocks or thermal
limits. [Exact comparison](evidence/wallace-source-comparison.json).

Wallace's reported32-bit kHz-to-Hz overflow repair is already present as
`1000UL` in the exact5cbc candidate's cpufreq source. Reapplying that repair
would add no support. CONFIG_CPU_FREQ remains unset and the RAM diagnostic DT
contains no cpufreq consumers. No runtime driver/DT/voltage/clock change was
made. Gravity kernel4fc326f6 and Mesa87ac51d upstream refs also remain unchanged
from the previous checkpoint; no new T6040 profile was found by that check.
