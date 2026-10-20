#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile actual Gravity serializers before/after the explicit G16S ABI port."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

BASE = "4fc326f6c25ccceb7515e2635c22e01fde5d3bac"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--kernel-source", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--root-inspector", type=Path, required=True)
p.add_argument("--main-inspector", type=Path, required=True)
a = p.parse_args()
source = a.kernel_source.resolve(strict=True)
output = a.output.resolve()
output.mkdir(parents=True, exist_ok=True)
root_inspector = a.root_inspector.resolve(strict=True)
main_inspector = a.main_inspector.resolve(strict=True)
relative = Path("drivers/gpu/drm/asahi")
head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
changed = subprocess.check_output(["git", "-C", str(source), "diff", "--name-only", BASE, head], text=True).splitlines()
if changed != [str(relative / "g16_fw.rs")]:
    raise SystemExit("Expected an envelope-only source commit; review scope before replay")
if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"]):
    raise SystemExit("Require a clean candidate source checkout")
metadata = []
for name in ["baseline", "candidate"]:
    work = output / name
    work.mkdir(exist_ok=True)
    digests = {}
    for file in ["g16_fw.rs", "g16_queue.rs"]:
        data = subprocess.check_output(["git", "-C", str(source), "show", f"{BASE}:{relative / file}"]) if name == "baseline" else (source / relative / file).read_bytes()
        (work / file).write_bytes(data)
        digests[file] = hashlib.sha256(data).hexdigest()
    wrapper = '''#[path="g16_fw.rs"] mod driver;
fn main() {
    let out=std::path::PathBuf::from(std::env::args().nth(1).unwrap());
    let root=driver::RootPointers::bootstrap();
    let main=driver::MainConfig::bootstrap(driver::BUNDLE_ADDRESS);
    std::fs::write(out.join("legacy-root.bin"),root.encode()).unwrap();
    std::fs::write(out.join("legacy-main.bin"),main.encode()).unwrap();
'''
    if name == "candidate":
        wrapper += '''
    // Synthetic pointer inputs, not captured hardware-data or a bootable graph.
    let pointers=driver::G16SMainPointers26_6_2 {
        views: [0xfffffc2000300000,0xfffffc2000304000,0xfffffc2000308000,0xfffffc200030c000,0xfffffc2000310000],
        zero_page: 0xfffffc2000314000,
        pb_low: 0x7000100000, pb_gpu: 0xfffffc2000318000,
        page_pool_low: 0x7000104000, page_pool_gpu: 0xfffffc200031c000,
        power: 0xfffffc2000320000, log_enable: 0,
        opaque_300: 4, opaque_3e0: 0xff,
    };
    let current=main.encode_g16s_26_6_2(&pointers);
    assert_eq!(&current[..0x240],&main.encode()[..0x240]);
    assert_eq!(&current[0x4c0..],&main.encode()[0x4c0..]);
    assert_eq!(u64::from_le_bytes(current[0x471..0x479].try_into().unwrap()),pointers.power);
    std::fs::write(out.join("current-root.bin"),root.encode_interface(driver::InitInterface::V26_6_2)).unwrap();
    std::fs::write(out.join("current-main.bin"),current).unwrap();
'''
    wrapper += "}\n"
    (work / "replay.rs").write_text(wrapper)
    subprocess.run(["rustc", "--edition=2021", "--cap-lints", "allow", str(work / "replay.rs"), "-o", str(work / "replay")], check=True)
    subprocess.run([str(work / "replay"), str(work)], check=True)
    metadata.append({"name": name, "source_sha256": digests})
for file in ["legacy-root.bin", "legacy-main.bin"]:
    if (output / "baseline" / file).read_bytes() != (output / "candidate" / file).read_bytes():
        raise SystemExit("Existing serializer output changed")
root = subprocess.run([str(root_inspector), str(output / "candidate/current-root.bin")], capture_output=True, text=True)
main = subprocess.run([str(main_inspector), str(output / "candidate/current-root.bin"), str(output / "candidate/current-main.bin")], capture_output=True, text=True)
if root.returncode or main.returncode:
    raise SystemExit("Current envelope replay failed inspection")
parsed_root, parsed_main = json.loads(root.stdout), json.loads(main.stdout)
assert parsed_root["hardware_validated"] is False and parsed_main["safe_to_publish_init"] is False
result = {"status": "COMPILED_AND_REPLAYED_ENVELOPES_ONLY", "hardware_tested": False, "safe_to_publish_init": False, "baseline_commit": BASE, "candidate_commit": head, "source": metadata, "legacy_root_and_main_bit_identical": True, "current_root_inspection": parsed_root, "current_main_inspection": parsed_main, "opaque_body": "UNIMPLEMENTED; synthetic explicit pointers do not qualify hardware/power data or application publication"}
(output / "gravity-port-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
