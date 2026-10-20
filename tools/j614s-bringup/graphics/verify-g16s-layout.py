#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify narrow consumer data-flow anchors without exporting vendor assembly."""
import argparse
import hashlib
import json
from pathlib import Path
import re

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--disassembly", type=Path, required=True)
p.add_argument("--g17-initdata", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
raw = a.disassembly.read_bytes()
lines = {}
for line in raw.decode().splitlines():
    match = re.match(r"([0-9a-f]{16}):\s+(?:[0-9a-f]{2}\s+){4}(.+)", line)
    if match:
        lines[int(match[1], 16)] = re.sub(r"\s+", " ", match[2].split(" ;")[0]).strip()
# Interface facts keyed by consumer PC. These are derived operand facts,
# not instruction bytes or a vendor assembly listing. The parser only checks
# short local dependencies; this is not a whole-function control-flow proof.
loads = {
    0xfffffc000002f314: ("x10", "x19", 0, 8),
    0xfffffc000002f318: ("q0", "x10", 0xe90, 16),
    0xfffffc000002f7bc: ("x8", "x19", 0x2e0, 8),
    0xfffffc000002f7c4: ("x8", "x19", 0x2f0, 8),
    0xfffffc0000003734: ("x8", "x8", 0x4c0, 8),
    0xfffffc000000373c: ("x8", "x8", 0, 8),
    0xfffffc0000033e10: ("x8", "x20", 0x4c0, 8),
    0xfffffc0000033e14: ("w9", "x8", 0x250, 4),
    0xfffffc000000582c: ("x10", "x10", 0x4c0, 8),
    0xfffffc0000005834: ("x10", "x10", 0, 8),
    0xfffffc00000038d4: ("x8", "x9", 0x1a0, 8),
    0xfffffc0000003930: ("x21", "x9", 0x1b8, 8),
    0xfffffc0000003934: ("x9", "x9", 0x1a8, 8),
    0xfffffc0000035d80: ("x8", "x8", 0x1b0, 8),
}
adds = {
    0xfffffc0000003738: ("x8", "x8", 0x471),
    0xfffffc0000005830: ("x10", "x10", 0x254),
}
for pc, expected in loads.items():
    found = re.fullmatch(r"ldr ([xwq][0-9]+), \[([xw][0-9]+)(?:, #(0x[0-9a-f]+))?\]", lines.get(pc, ""))
    if not found:
        raise SystemExit(f"Consumer load anchor changed at {pc:#x}; inspect privately")
    register, base, offset = found.groups()
    width = {"x": 8, "w": 4, "q": 16}[register[0]]
    if (register, base, int(offset or "0", 16), width) != expected:
        raise SystemExit(f"Consumer field changed at {pc:#x}; inspect privately")
for pc, expected in adds.items():
    found = re.fullmatch(r"add (x[0-9]+), (x[0-9]+), #(0x[0-9a-f]+)", lines.get(pc, ""))
    if not found or (found[1], found[2], int(found[3], 16)) != expected:
        raise SystemExit(f"Consumer address anchor changed at {pc:#x}; inspect privately")
anchor_count = len(loads) + len(adds)
g17 = a.g17_initdata.read_text()
for field, offset in [("log_enable", "0x250"), ("view_va", "0x254"), ("power_config_va", "0x471")]:
    if not re.search(rf"offset_of!\(MainConfig, {field}\) == {offset}\)", g17):
        raise SystemExit(f"G17 comparison changed for field {field}")
result = {
    "status": "VERIFIED_STATIC_ANCHORS",
    "hardware_tested": False,
    "scope": "Narrow read offsets only; not a complete control-flow proof or initialization graph qualification",
    "disassembly_sha256": hashlib.sha256(raw).hexdigest(),
    "g17_source_sha256": hashlib.sha256(a.g17_initdata.read_bytes()).hexdigest(),
    "consumer_anchor_count": anchor_count,
    "g16s_consumer": {
        "main_config_stored_at": "0xfffffc000018e4c0",
        "first_body_chain": {"root_pointer_offset": "0x18", "main_pointer_offset": "0x0", "body_offset": "0xe90", "bytes": 16, "consumer_pc": "0xfffffc000002f318"},
        "control_channel": {"entry": 12, "state_offsets": ["0x1a0", "0x1a8", "0x1b0"], "ring_offset": "0x1b8", "counter_access_bytes": 4},
        "log_enable": "0x250", "view_base": "0x254",
        "descriptor_pointers": ["0x2e0", "0x2f0"], "power_pointer": "0x471",
    },
    "g17_static_assertions_match": ["log_enable", "view_va", "power_config_va"],
    "unknowns": ["T6040 hardware-data contents and extents", "power/clocks/voltage tables", "remaining opaque main fields", "PPL/UAT publication and application handshake", "work-ring registration and completion protocol"],
}
a.output.write_text(json.dumps(result, indent=2) + "\n")
print(f"PASS: {anchor_count} private consumer anchors; three existing G17 offset assertions; no vendor bytes exported")
