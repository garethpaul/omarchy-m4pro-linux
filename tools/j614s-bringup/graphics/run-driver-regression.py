#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile unchanged historical/candidate kernel driver sources in a host fake."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

BASE = "4ff8816df8c4bc81b1652eca17fc8c0e9e1928cc"
CANDIDATE = "0fb65dbd66f9b91a43096ecbabd52b81f73bea5c"
DRIVER = "drivers/gpu/drm/asahi/g16-bootstrap.c"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--kernel-repo", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--cc", default="clang")
a = p.parse_args()
output = a.output.resolve()
output.mkdir(parents=True, exist_ok=True)
harness = Path(__file__).with_name("driver-host-harness.c").resolve(strict=True)
result = {"scope": "Host causal regression using actual unchanged driver sources with fake Linux/DT/MMIO/RTKit; hardware UNTESTED", "hardware_tested": False, "harness_sha256": hashlib.sha256(harness.read_bytes()).hexdigest(), "compiler": subprocess.check_output([a.cc, "--version"], text=True).splitlines()[0], "runs": []}
for name, commit, arguments in [("baseline", BASE, ["--expect-baseline-bug"]), ("candidate", CANDIDATE, [])]:
    work = output / name
    work.mkdir(exist_ok=True)
    source = subprocess.check_output(["git", "-C", str(a.kernel_repo.resolve(strict=True)), "show", f"{commit}:{DRIVER}"])
    (work / "g16-bootstrap-under-test.c").write_bytes(source)
    # All behavior stays in the actual driver and single test TU. These scratch
    # include files only satisfy the kernel include paths, with no stub logic.
    for include in re.findall(rb"#include <([^>]+)>", source):
        relative = Path(include.decode())
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "linux":
            raise SystemExit("Unexpected driver include")
        stub = work / "include" / relative
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("/* Generated empty include: host fake declarations are in the test TU. */\n")
    executable = work / "driver-host-test"
    command = [a.cc, "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-I", str(work), "-I", str(work / "include"), str(harness), "-o", str(executable)]
    compiled = subprocess.run(command, capture_output=True, text=True)
    (work / "compile.log").write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise SystemExit(f"{name} compile failed; see local compile.log")
    environment = dict(os.environ, UBSAN_OPTIONS="halt_on_error=1", ASAN_OPTIONS="detect_leaks=1:halt_on_error=1")
    executed = subprocess.run([str(executable), *arguments], capture_output=True, text=True, env=environment)
    (work / "run.log").write_text(executed.stdout + executed.stderr)
    if executed.returncode:
        raise SystemExit(f"{name} regression failed; see local run.log")
    if name == "baseline" and "REPRODUCED: baseline publishes RTKIT_READY" not in executed.stdout:
        raise SystemExit("Baseline bug not reproduced")
    if name == "candidate" and "PASS: candidate rejects crash-during-wake" not in executed.stdout:
        raise SystemExit("Candidate fix not observed")
    strict_failure = None
    if name == "baseline":
        strict = subprocess.run([str(executable)], capture_output=True, text=True, env=environment)
        (work / "fixed-invariant.log").write_text(strict.stdout + strict.stderr)
        if strict.returncode != 1 or "FAIL: probe returned 0 after crash; observed RTKIT_READY" not in strict.stderr:
            raise SystemExit("Baseline did not fail the fixed invariant in the expected way")
        strict_failure = {"exit": strict.returncode, "output": strict.stderr.splitlines()}
    result["runs"].append({"name": name, "source_commit": commit, "driver_source_sha256": hashlib.sha256(source).hexdigest(), "compile_exit": compiled.returncode, "run_exit": executed.returncode, "output": executed.stdout.splitlines(), "fixed_invariant_failure": strict_failure})
result["status"] = "FAILURE_REPRODUCED_BEFORE_FIX_PASS_AFTER_FIX"
(output / "driver-regression-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
