#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Replay bounded physical reads offline; never connect to a target."""
import argparse
import hashlib
import json
from pathlib import Path
from g16s_early_capture import Observer


def replay(source, output, library):
    source = Path(source).resolve(strict=True)
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest.get("capture_error") != 0:
        raise ValueError("Failed input capture is not replayable")
    records = manifest["reads"]
    if len(records) > 256:
        raise ValueError("Too many capture reads")
    memory = {}
    total = 0
    for record in records:
        name = record["file"]
        if Path(name).name != name or not name.startswith("read-") or not name.endswith(".bin"):
            raise ValueError("Invalid capture filename")
        path = (source / name).resolve(strict=True)
        if path.parent != source:
            raise ValueError("Capture path escapes its directory")
        size = int(record["bytes"])
        if size < 1 or size > 0x4000 or path.stat().st_size != size:
            raise ValueError("Invalid capture read size")
        total += size
        if total > 0x10000:
            raise ValueError("Capture byte bound exceeded")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("Capture hash mismatch")
        address = int(record["physical"],0)
        if address < 0 or address + size > 1 << 64:
            raise ValueError("Invalid physical interval")
        for offset, byte in enumerate(data):
            if address+offset in memory and memory[address+offset] != byte:
                raise ValueError("Conflicting capture bytes")
            memory[address+offset] = byte
    if total != manifest["read_bytes"]:
        raise ValueError("Read accounting mismatch")
    def read(address,size):
        return bytes(memory[address+i] for i in range(size))
    ranges = [(int(r["start"],0),int(r["size"])) for r in manifest["ram_ranges"]]
    observer = Observer(read,ranges,int(manifest["native_table"],0),library,output)
    observer.root_va = int(manifest["root_va"],0)
    observer.qualification = {"scope":"offline replay of captured reads", "input_manifest_sha256":hashlib.sha256((source/"manifest.json").read_bytes()).hexdigest()}
    result = observer._snapshot("offline-replay")
    if result["capture_error"]:
        raise ValueError("Offline capture traversal failed")
    return {"status":"OFFLINE_REPLAY_MATCH", "hardware_job_pass":False,"safe_to_publish_init":False,"read_bytes":result["read_bytes"],"main_va":result["main_va"],"first_body_va":result["first_body_va"]}

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase_directory",type=Path)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--library",type=Path,required=True)
    a = p.parse_args()
    print(json.dumps(replay(a.phase_directory,a.output,a.library),indent=2))
