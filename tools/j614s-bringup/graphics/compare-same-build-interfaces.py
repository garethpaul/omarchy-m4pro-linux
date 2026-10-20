#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare derived root ABI constants from private same-build firmware views."""
import argparse
import hashlib
import json
from pathlib import Path
import re

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--g16g-view", type=Path, required=True)
p.add_argument("--g16s-view", type=Path, required=True)
p.add_argument("--g16g-image", type=Path, required=True)
p.add_argument("--g16s-image", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
def version(path):
    raw = path.read_bytes()
    instructions = []
    for line in raw.decode().splitlines():
        m = re.match(r"([0-9a-f]{16}):\s+(?:[0-9a-f]{2}\s+){4}(.+)", line)
        if m:
            instructions.append((int(m[1],16),re.sub(r"\s+"," ",m[2]).split(" ;")[0]))
    found = []
    for i in range(len(instructions)-4):
        first = re.fullmatch(r"mov (x[0-9]+), #(0x[0-9a-f]+)",instructions[i][1])
        if not first: continue
        register, low = first[1], int(first[2],16)
        if low not in (0x04b8,0x04c0): continue
        words = [low]
        for j in range(1,4):
            next_part = re.fullmatch(r"movk (x[0-9]+), #(0x[0-9a-f]+), lsl #([0-9]+)",instructions[i+j][1])
            if not next_part or next_part[1]!=register or int(next_part[3])!=16*j: break
            words.append(int(next_part[2],16))
        if len(words)==4 and instructions[i+4][1].startswith("cmp "):
            found.append({"constant_load_pc":hex(instructions[i][0]),"interface":[f"0x{x:04x}" for x in words]})
    if len(found)!=1: raise SystemExit("Root interface constant is ambiguous; inspect privately")
    return {"view_sha256":hashlib.sha256(raw).hexdigest(),**found[0]}
g16g,g16s=version(a.g16g_view),version(a.g16s_view)
expected=["0x04c0","0x0396","0xa322","0x0c8a"]
if g16g["interface"]!=expected or g16s["interface"]!=expected:
    raise SystemExit("Unexpected same-build ABI; do not select the candidate envelope")
result={"status":"SAME_BUILD_ROOT_ABI_MATCH", "hardware_tested":False,"restore_build":"25G83","g16g_j700ap_b100":{**g16g,"image_sha256":hashlib.sha256(a.g16g_image.read_bytes()).hexdigest()},"g16s_j614sap_b000":{**g16s,"image_sha256":hashlib.sha256(a.g16s_image.read_bytes()).hexdigest()},"conclusion":"The legacy Gravity root mismatch is not a G16G-versus-G16S distinction. Root ABI equality does not establish hardware-data/power/job-format compatibility.","provenance":"This work used public source plus private vendor firmware analysis. No clean-room provenance is claimed."}
a.output.write_text(json.dumps(result,indent=2)+"\n")
print("PASS: same25G83 G16G B1 and G16S root interface constants match; no vendor bytes exported")
