#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile upstream's pure root encoder and check the actual output offline."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

PIN = "4fc326f6c25ccceb7515e2635c22e01fde5d3bac"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--source", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--inspector", type=Path, required=True)
a = p.parse_args()
source = a.source.resolve(strict=True)
output = a.output.resolve()
output.mkdir(parents=True, exist_ok=True)
commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
if commit != PIN:
    raise SystemExit(f"Unreviewed source commit {commit}; expected {PIN}")
paths = [source / "drivers/gpu/drm/asahi" / name for name in ("g16_fw.rs", "g16_queue.rs")]
if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--", *(str(x) for x in paths)]):
    raise SystemExit("Source encoder is modified")
wrapper = output / "gravity-root.rs"
wrapper.write_text(
    "use std::io::Write;\n"
    f"#[path = {json.dumps(str(paths[0]))}] mod upstream;\n"
    "fn main() { if std::env::args().nth(1).as_deref() == Some(\"main\") { std::io::stdout().write_all(&upstream::MainConfig::bootstrap(upstream::BUNDLE_ADDRESS).encode()).unwrap(); } else { std::io::stdout().write_all(&upstream::RootPointers::bootstrap().encode()).unwrap(); } }\n"
)
program = output / "gravity-root"
subprocess.run(["rustc", "--edition=2021", "--cap-lints", "allow", str(wrapper), "-o", str(program)], check=True)
root = subprocess.check_output([str(program)])
if len(root) != 0xc8:
    raise SystemExit(f"Unexpected encoded root size {len(root)}")
root_path = output / "gravity-encoded-root.bin"
root_path.write_bytes(root)
checked = subprocess.run([str(a.inspector.resolve(strict=True)), str(root_path)], capture_output=True, text=True)
version = struct.unpack_from("<4H", root)
if version != (0x04b8, 0x8392, 0xc357, 0x0c89) or checked.returncode != 1 or "error=4" not in checked.stderr:
    raise SystemExit("Expected version incompatibility was not reproduced")
result = {
    "status": "WORKS_OFFLINE",
    "hardware_tested": False,
    "source": "https://github.com/GravityLinux/linux",
    "source_commit": commit,
    "source_files_sha256": {x.name: hashlib.sha256(x.read_bytes()).hexdigest() for x in paths},
    "compiled_encoder_root_size": len(root),
    "compiled_encoder_interface": [f"0x{x:04x}" for x in version],
    "exact_25G83_g16s_required_interface": ["0x04c0", "0x0396", "0xa322", "0x0c8a"],
    "validator_exit_status": checked.returncode,
    "validator_result": checked.stderr.strip(),
    "conclusion": "Gravity root cannot be sent to the exact-build J614s firmware unchanged; changing version alone does not qualify its graph.",
}
(output / "gravity-root-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))

main = subprocess.check_output([str(program), "main"])
(output / "gravity-encoded-main.bin").write_bytes(main)
assert len(main) == 0x500
main_result = {
    "source_commit": commit, "hardware_tested": False,
    "compiled_encoder_main_size": len(main),
    "gravity_power_469": f"0x{struct.unpack_from('<Q', main, 0x469)[0]:016x}",
    "g16s_consumer_power_471": f"0x{struct.unpack_from('<Q', main, 0x471)[0]:016x}",
    "g16s_consumer_descriptor_2e0": f"0x{struct.unpack_from('<Q', main, 0x2e0)[0]:016x}",
    "g16s_consumer_descriptor_2f0": f"0x{struct.unpack_from('<Q', main, 0x2f0)[0]:016x}",
    "g16s_consumer_log_enable_250": struct.unpack_from('<I', main, 0x250)[0],
    "g16s_consumer_views_254": [f"0x{struct.unpack_from('<Q', main, 0x254+i*8)[0]:016x}" for i in range(5)],
    "conclusion": "Compiled upstream MainConfig has incompatible known pointer slots, independent of root interface version. Do not publish it to G16S.",
}
assert struct.unpack_from('<Q', main, 0x2f0)[0] == 0
assert struct.unpack_from('<Q', main, 0x471)[0] == 0
(output / "gravity-main-result.json").write_text(json.dumps(main_result, indent=2) + "\n")
print(json.dumps(main_result, indent=2))
