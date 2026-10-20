# RAM-only staging observation

**WORKS within observation scope:** capture01 reads paired resident metadata and
199 raw16-byte ADT range entries without calling the allocator. **PARTIAL:** this
supports a future offline placement review. **BLOCKED:** current secondary/WFE
prerequisites are false. **UNTESTED:** reservation, staging, firmware handoff,
cache ownership, execution and recovery.

`read_staging_memory.py` is separate from the already pinned CPU observer; the
older observer/captures and kernel/loader/DT/initrd inputs remain unchanged.
Its source and both pure helpers are hash-bound. The installed resident's local
ELF must flatten to the pinned binary. Required metadata symbols must be unique
and bounded within that image; irrelevant compiler aliases are not confused
with those symbols. The source tree atb3df851 differs from8e0cf28 only in its
checkpoint documentation; the relevant allocator/startup/proxy sources match.

`heapblock_alloc(0)` is not a read-only high-water query: its alignment changes
the pointer. The new reader instead reads `heap_base` and `heap_limit` directly.
It preserves an unaligned value and treats limit0 as no explicit allocator
limit. It does not call either allocator function. Source semantics are
cross-checked with offline instruction bytes from the pinned flat image:
[instruction evidence](allocator-instructions.json). The high-water function's
direct load resolves to the paired `heap_base` symbol. No function was run.

The first attempted host `llvm-objdump` ELF disassembly aborted with exit134.
That failure is retained; its root cause is unresolved. The successful narrow
fallback decodes only three bounded function byte spans using `llvm-mc` and
independently checks the high-water ADRP/LDR target. This is not a successful
ELF parser test or execution of the allocator/native consumer.

The reader obtains the RAM envelope from the resident's bounded bootargs copy
before dereferencing the external bootargs or ADT. Both copies must match the
explicit expected hash. It uses address-only `get_bootargs()` because
`get_bootargs_rev()` hides physical `read8` operations. All direct target API
calls are checked by an AST regression: metadata queries, NOP and `readmem` only.
All `readmem` extents are checked against paired resident or usable RAM bounds.

Both ADT memory sections are required. Every16-byte property is retained with
its original section/name/raw little-endian bytes, including sentinel, zero and
out-of-range entries. Duplicates/overflow refuse capture. The observer makes no
range exemption or placement decision. Exact full-RAM-envelope interpretation
belongs to the separate planner. Bootargs/ADT extents are separately protected.
All selected resident globals, CPU slots, ADT and bootargs are read twice;
changes or exception/session mismatch refuse observation. Stable repeated
reads do not establish atomic coherence or continuing freshness.

Capture01 at07:54:40UTC hasUSB63, zero exceptions,199 ranges, zero initialized
secondary slots and WFEfalse. It contains no reservation or real container.
[Address-free result](staging-memory-observation-01.json) records hashes and
scope. Raw ADT, bootargs and address-bearing capture stay private in a new0700
directory with0600 files. They must never be published.

Twelve host controls pass, including the initial red helper-stub phase, bounds,
raw range preservation, symbol ambiguity, source-section identity and target-API
allowlist. Pure tests do not discover/open a target:

```sh
python3 recovery/test_staging_memory.py
```

Only the primary may invoke the actual observer. It requires explicit expected
USB-session, ADT and bootargs hashes and a new private output directory. This
does not start cores, change WFE, clear PMU state, allocate RAM, write target
memory, alter watchdogs, stage a payload or grant permission to boot.
