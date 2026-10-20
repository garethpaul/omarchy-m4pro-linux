#!/usr/bin/env python3
"""Read-only J614s desktop qualification. No installer or boot-policy operations."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess


def cpu_set(value):
    result = set()
    for part in value.strip().split(","):
        if "-" in part:
            first, last = map(int, part.split("-"))
            if not 0 <= first <= last < 4096:
                raise ValueError("invalid CPU range")
            result.update(range(first, last + 1))
        elif part:
            number = int(part)
            if not 0 <= number < 4096:
                raise ValueError("invalid CPU number")
            result.add(number)
    return result


def text(path):
    try:
        return path.read_text().strip("\0\n ")
    except OSError:
        return ""


def collect_metadata():
    """Read identity, topology and candidate nodes without starting GPU work."""
    compatible = text(Path("/sys/firmware/devicetree/base/compatible")).split("\0")
    devices = []
    for path in sorted(Path("/sys/class/drm").glob("renderD*")):
        node = Path("/dev/dri") / path.name
        driver = (path / "device/driver").resolve().name
        exists = node.exists() and stat.S_ISCHR(node.stat().st_mode)
        devices.append({"node": str(node), "driver": driver, "character_device": exists})
    env = {key: os.environ[key] for key in (
        "LIBGL_ALWAYS_SOFTWARE", "GALLIUM_DRIVER", "MESA_LOADER_DRIVER_OVERRIDE",
        "MESA_VK_DEVICE_SELECT", "AQ_DRM_DEVICES") if key in os.environ}
    return {"schema": 1, "architecture": platform.machine(),
            "compatible": compatible,
            "model": text(Path("/sys/firmware/devicetree/base/model")),
            "kernel": platform.release(),
            "online_cpus": text(Path("/sys/devices/system/cpu/online")),
            "present_cpus": text(Path("/sys/devices/system/cpu/present")),
            "render_environment": env, "render_devices": devices}


def metadata_reasons(snapshot):
    """Shared pre-work guards: rejecting a result later cannot undo GPU work."""
    reasons = []
    if snapshot.get("schema") != 1:
        reasons.append("unsupported evidence schema")
    if snapshot.get("architecture") != "aarch64":
        reasons.append("requires native aarch64")
    compatible = snapshot.get("compatible", [])
    if not isinstance(compatible, list) or not {"apple,j614s", "apple,t6040"} <= set(compatible):
        reasons.append("requires both apple,j614s and apple,t6040 root compatibles")
    try:
        online = cpu_set(snapshot.get("online_cpus", ""))
        present = cpu_set(snapshot.get("present_cpus", ""))
        if online != set(range(12)) or present != online:
            reasons.append("requires present and online CPU sets exactly 0-11")
    except (ValueError, TypeError, AttributeError):
        reasons.append("invalid CPU topology evidence")
    environment = snapshot.get("render_environment", {})
    # Overrides hide the natural driver selection and can invalidate node binding.
    if environment:
        reasons.append("remove rendering overrides before qualification")
    return reasons


def collect(probe):
    snapshot = collect_metadata()
    if not probe or metadata_reasons(snapshot):
        return snapshot
    for info in snapshot["render_devices"]:
        if (info["driver"] != "asahi" or info["character_device"] is not True
                or not re.fullmatch(r"/dev/dri/renderD[0-9]+", info["node"])):
            continue
        try:
            run = subprocess.run([str(probe.resolve()), info["node"]], capture_output=True,
                                 text=True, timeout=30, check=False)
            info["probe_exit"] = run.returncode
            if run.returncode == 0:
                info["probe"] = json.loads(run.stdout)
            else:
                info["probe_error"] = run.stderr.strip()[:512]
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            info["probe_error"] = str(error)
    return snapshot


def evaluate(snapshot):
    reasons = metadata_reasons(snapshot)
    qualified = []
    for device in snapshot.get("render_devices", []):
        probe = device.get("probe", {})
        renderer = probe.get("renderer", "")
        software = re.search(r"llvmpipe|softpipe|lavapipe|swrast|software|swiftshader|virgl|virtio", renderer, re.I)
        if (device.get("driver") == "asahi" and device.get("character_device") is True
                and re.fullmatch(r"/dev/dri/renderD[0-9]+", device.get("node", ""))
                and device.get("probe_exit") == 0
                and probe.get("node") == device["node"]
                and probe.get("vendor") == "Mesa"
                and re.search(r"\bApple M4 Pro\b", renderer)
                and not software and probe.get("pixel_test") is True):
            qualified.append(device["node"])
    if len(qualified) != 1:
        reasons.append("requires one asahi render node with bound M4 Pro EGL pixel readback")
    return {"status": "WORKS" if not reasons else "BLOCKED",
            "scope": "native renderer preflight only; compositor, display and boot remain unqualified",
            "ready_to_stage": not reasons, "reasons": reasons,
            "qualified_render_node": qualified[0] if len(qualified) == 1 else None,
            "persistent_installation": "UNTESTED", "compositor_acceleration": "UNTESTED"}


def stage(snapshot, result, destination):
    if not result["ready_to_stage"]:
        raise ValueError("refusing to stage an unqualified renderer")
    # A brand-new review folder only. Never copies into /etc, HOME or Omarchy.
    destination.mkdir(parents=False, exist_ok=False)
    encoded = json.dumps(snapshot, sort_keys=True, indent=2) + "\n"
    manifest = {"profile": "j614s-t6040-experimental", "release_authorized": False,
                "render_node": result["qualified_render_node"],
                "evidence_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
                "actions": [], "requires": ["qualified DCP/KMS and native display modes",
                "measured Hyprland acceleration and input latency", "validated thermal protection",
                "tested independent recovery and rollback", "explicit persistent boot authorization"]}
    (destination / "evidence.json").write_text(encoded)
    (destination / "profile.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, help="compiled render_probe executable")
    parser.add_argument("--snapshot", type=Path, help="offline replay; cannot stage")
    parser.add_argument("--capture", type=Path, help="write evidence to a new file")
    parser.add_argument("--stage", type=Path, help="new review folder; no installation")
    args = parser.parse_args()
    if args.snapshot and args.stage:
        parser.error("offline replay cannot authorize staging")
    snapshot = json.loads(args.snapshot.read_text()) if args.snapshot else collect(args.probe)
    result = evaluate(snapshot)
    if args.capture:
        with args.capture.open("x") as output:
            json.dump(snapshot, output, indent=2)
            output.write("\n")
    if args.stage:
        try:
            stage(snapshot, result, args.stage)
        except (ValueError, OSError) as error:
            parser.exit(2, f"{error}\n")
    print(json.dumps(result, indent=2))
    return 0 if result["ready_to_stage"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
