# Exact 25G83 G16S MainConfig checkpoint

**PARTIAL: known-field decoder and bounded capture planner implemented and tested
on the development host. No G16S application INIT has been constructed or sent.**

This step narrows the application-initialization gap rather than adding an
unqualified GPU profile. It uses the already captured J614s firmware and ADT;
no target connection or reboot occurred in this lane.

## What the exact consumer establishes

The decoded root's main pointer is at +0x18. The exact G16S startup function
stores that pointer at firmware VA `0xfffffc000018e4c0`. Its first unsupported
body access is the chain:

```
root +0x18 -> MainConfig +0x00 -> hardware-data +0xe90, read 16 bytes
```

The final read occurs at consumer PC `0xfffffc000002f318`. The G17 source calls
+0xe90 `chip_id`; Gravity's T8132 serializer writes its chip ID there too.
Those are useful source correspondences. They do not establish the remaining
T6040 hardware-data values, mapping list, voltages or power policy. The capture
planner retains these first 16 bytes as opaque data.

| Known main offset | Exact G16S consumer | Gravity compiled output | Existing G17 source |
| --- | --- | --- | --- |
| +0x00 | hardware-data pointer | bundle address | hardware-data pointer |
| +0x1a0/+0x1a8/+0x1b0 | three channel-12 counter pointers; observed counter accesses are 32-bit | three nonzero pointers | control channel's three counters |
| +0x1b8 | channel-12 ring pointer | nonzero ring pointer | control ring |
| +0x250 | 32-bit log-enable read | zero | log_enable at +0x250 |
| +0x254 | pointer-array base consumed by firmware | starts at Gravity's second addresses-array slot | view_va at +0x254 |
| +0x2e0 | descriptor pointer copied during init | 0x7000280000 | pb_descriptors_va |
| +0x2f0 | descriptor pointer copied during init | **zero** | page_pool_descriptors_va |
| +0x471 | power pointer dereferenced through published main pointer | **zero**; Gravity places its nonzero pointer at +0x469 | power_config_va at +0x471 |

0x471 minus 0x469 is **eight bytes**. Several offsets correspond to G17, but
that does not make the A18 dual-firmware hardware bundle appropriate for G16S.
Gravity's array representation also means this is not proof that every field
can be fixed by inserting eight zero bytes. The meanings of all opaque fields,
objects and publication sequencing still need evidence.

`gravity-main-result.json` records the actual output of the compiled, unchanged
Gravity serializer, not a reconstruction of it. `g16s-main-layout.json` records
16 checked consumer operand anchors plus the three G17 source offset assertions.
No vendor binary, raw ADT or assembly listing is distributed here. The verifier
contains derived field/register/offset facts and a generic assembly parser; its
output deliberately omits instructions and input paths.

## Implemented code

`g16s_main.h` adds:

- `g16s_decode_main`: parses only known offsets from a minimum 0x479-byte capture;
  0x479 describes the last known field's end, not an allocation-size claim.
- `g16s_check_main_pointers`: checks the known hardware-data, control, descriptor
  and power pointers for nonzero, address form and access-width alignment.
  **Success never permits INIT publication.** Mapping extents, contents and
  synchronization remain unqualified.
- `g16s_main_header_request`: emits one request for eight bytes at root.main.
- `g16s_hwdata_first_request`: consumes that captured pointer and emits the exact
  first 16-byte body request at +0xe90. It rejects null, malformed and wrapping
  pointers. Neither helper performs any read or follows another pointer.
- `g16s_read_virtual`: executes a caller-selected capture, limited to one 16-KiB
  page of requested data, through the explicit UAT root and physical RAM allowlist.
  Crossing a page boundary requires a separate checked translation. A missing
  second mapping fails before that page's data read. Returned data must be
  discarded on error; the destination may contain an earlier successful chunk.

`g16s-main-inspect` reads ordinary captured files only. Its JSON always reports
`hardware_validated=false` and `safe_to_publish_init=false`. The compiled Gravity
MainConfig fails the known-pointer check at +0x2f0. That comparison uses a
**synthetic current-format root solely to supply geometry**; it does not alter
Gravity's root version or imply that its root passes the exact firmware check.

## Replay

```sh
make -C graphics all test
UBSAN_OPTIONS=halt_on_error=1 make -C graphics test CC=clang BUILD=build-clang CFLAGS='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer'
graphics/build/test_g16s_abi --emit-fixture > graphics/build/synthetic-root.bin
graphics/build/test_g16s_main --emit-fixture > graphics/build/synthetic-main.bin
graphics/build/g16s-main-inspect graphics/build/synthetic-root.bin graphics/build/synthetic-main.bin
python3 graphics/check-gravity-root.py --source /path/to/gravity-linux --output graphics/build/gravity --inspector graphics/build/g16s-inspect
```

To verify the derived consumer offsets locally, supply the exact private
G16S disassembly and the G17 source file to `verify-g16s-layout.py`. A changed
anchor fails closed and requests private inspection. This limited verification
is not a complete disassembler or proof of every path through the firmware.

## Exact next capture and remaining blockers

The next useful hardware operation, exclusively owned by the primary lane,
is a coherent read-only observation of an existing valid G16S APP INIT:

1. Record the endpoint-0x20 message and exact firmware identity; decode its root
   address with the existing predicate.
2. Capture the root's 0xc8 bytes through independently validated RAM/UAT ranges.
3. Use `g16s_main_header_request` for the eight-byte hardware-data pointer.
4. Use `g16s_hwdata_first_request` for the exact first 16-byte body read.
5. Capture the known 0x479-byte main prefix. Check, but do not publish, pointers.
   Only after their extents are independently established should control counters
   or additional body slices be requested.

Capture into private storage: these are live memory objects and may contain
sensitive material. Publish only derived interface facts and redacted evidence.
The plan itself never starts XNU, starts GPU firmware, mutates page tables or
writes a mailbox. Protected-volume boot and target recovery constraints still
apply if acquiring a valid APP INIT needs those actions.

A safe complete initialization graph remains BLOCKED by the unqualified T6040
hardware-data/power contents and the APP INIT/PPL publication sequence. A
channel-pointer layout alone cannot supply those. The first body request and
precise shifted-pointer failures make the next evidence gap executable without
weakening compatibility checks.
