# T6040 performance-input preparation

**PARTIAL:** an actual kernel-source Rust decoder preserves the captured ADT's
two banks and state indices. **WORKS:** seven host controls, exact replay of all
64 core/SRAM records, and a core-only AArch64 object compile.
**BLOCKED:** firmware body/power layout, UAT and APP INIT still need the earliest
coherent T6040 capture. **UNTESTED:** target execution and GPU jobs. This patch
does not enable a runtime caller, model binding, power state or initialization.

The [result](g16-perf-result.json) pins the kernel commit, source, patch and
captured ADT hashes. [Patch](g16-perf-inputs.patch) adds `g16_perf.rs` and its
module declaration to Gravity's kernel. The existing G16G driver and its
compatibility guards are unchanged. There is no voltage, clock, register or
firmware write in this decoder. It only consumes byte slices.

The captured J614s SGX node has16 indexed states,15 active states, and two
performance-table banks. Both the core and SRAM tables have32 records. Each
`*1` property exactly mirrors its respective second bank. The banks have
different voltage values. Frequency index9 repeats index8; indices11 and13
decrease from their predecessors. Sorting, deduplicating, truncating to11 or
sharing one voltage bank would lose observed inputs. SRAM frequencies are
checked against the corresponding core frequency at every index.

The ADT also supplies200000 sampling clocks and8 milliseconds. Reconstructing
the former by multiplying the latter by24000 loses8000 clocks. Both values are
preserved. MCC's active mask is15; it remains a raw mask, not a claimed map from
channel bits to physical register addresses. No G16G fixed MCC or other MMIO
window is imported into a T6040 profile.

Gravity's `g16_platform.rs` currently accepts fixed11-element ladders and requires
strictly increasing frequencies. Its core-mask check covers one10-core cluster,
whereas the previously measured G16S has two physical10-core clusters with
eight enabled cores each. Its fixed T8132 register windows and single-variant
power serializer remain unqualified for T6040. These are source/input differences;
this observation does not claim a newly attempted firmware initialization.

The same-restore M2/T8112 and M3/T8122 SGX nodes were compared first. Those vendor
static trees report `perf-state-count=0`, `gpu-num-perf-states=2`, and lack a
table-count field and the SRAM/second-bank properties. They are unpopulated
static inputs, not measured M2/M3 runtime ladders. The `<u32 frequency,u32 mV>`
record format and table-major indexing agree with the existing m1n1 ADT parser
and `kboot_gpu.c`; their power models and firmware encoders cannot be inferred
reusable from that structural agreement. No raw ADT is published.

The first focused test was run before implementation and failed because the
stub rejected a valid16-state/two-bank input. The implementation then passed
seven tests, including malformed lengths, count substitution, mismatched bank
aliases, SRAM misalignment, voltage conversion overflow and inconsistent
sampling. Tests are synthetic; the separate replay feeds the actual captured
bytes through the actual Rust kernel-source decoder and checks every field.
An initial cross-compile could not find the Linux AArch64 core target. The
installed bare-metal softfloat core target was used instead, without disabling
checks. [Actual AArch64 kernel-crate compilation](../infra/g16-perf/README.md) also passes on combined source5628d35c with the exact reviewed config and all3174 layout blocks/16413 field checks enabled. Root independently verifies source/object/config/log hashes and ELF architecture. Twelve warnings remain, including the deliberately uncalled decoder. Full Image/module linking and hardware are UNTESTED for this new source. Original combined8f2 artifacts are unchanged.

Reproduce offline, with the private captures and pinned source available:

```sh
python3 graphics/replay_g16_perf.py --kernel-source "$KERNEL_SOURCE" --m1n1-source "$M1N1_SOURCE" --target-adt "$PRIVATE_ADT" --baseline-root "$PRIVATE_BASELINES" --output "$FRESH_RESULT"
```

The tool requires the exact source ADT hashes, refuses an existing result, and
exports only selected derived facts. It does not contact the Mac. The next
driver step is a captured, version-specific T6040 body/power encoder, followed
by UAT/APP INIT and one fenced constant42 compute job with independent readback.
Do not wire this parser to the legacy G16G firmware serializer to manufacture
a successful initialization.
