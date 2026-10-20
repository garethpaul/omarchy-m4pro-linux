#!/usr/bin/env python3
"""Validate only on the explicitly named development Mac, never the M4 target."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess

from verify_transcript import FIRST, STORE42, verify


def validate(binary, output, include_store42=False):
    actual = subprocess.check_output(["sysctl", "-n", "hw.model"], text=True).strip()
    if platform.machine() != "arm64" or actual != "MacBookPro18,3":
        raise ValueError("builder validation is restricted to the known M1 Pro development Mac")
    output.mkdir(exist_ok=False)
    cases = []

    def run(name, arguments, stdin, exit_code):
        child = subprocess.run([str(binary.resolve()), *arguments], input=stdin, capture_output=True,
                               text=True, timeout=40, check=False)
        if child.returncode != exit_code:
            raise ValueError(f"{name}: unexpected process exit {child.returncode}")
        records = [json.loads(line) for line in child.stdout.splitlines() if line.strip()]
        (output / (name + ".jsonl")).write_text(child.stdout)
        if child.stderr:
            (output / (name + ".stderr.txt")).write_text(child.stderr)
        cases.append({"name": name, "exit": child.returncode, "events": [row["event"] for row in records]})
        return records

    records = run("dry-run", ["--dry-run"], "", 0)
    if len(records) != 1 or records[0].get("expected_first_output") != FIRST:
        raise ValueError("dry-run must emit only the CPU plan")
    records = run("wrong-model", ["--run"], "START\nCOMMIT0\n", 78)
    if [row["event"] for row in records] != ["PLAN", "ERROR"]:
        raise ValueError("wrong model reached a Metal API marker")
    common = ["--run", "--expect-model", actual, "--expect-device-prefix", "Apple M1 Pro"]
    for name, stdin in (("refused-start", "NO\n"), ("eof-start", "")):
        records = run(name, common, stdin, 65)
        if [row["event"] for row in records] != ["PLAN", "WAIT_START", "ERROR"]:
            raise ValueError("START refusal reached a Metal API marker")
    records = run("refused-commit", common, "START\nNO\n", 65)
    if "BEFORE_COMMIT" in [row["event"] for row in records] or records[-1]["event"] != "ERROR":
        raise ValueError("refused commit still submitted workload")
    one = run("one-job", common, "START\nCOMMIT0\n", 0)
    first = verify(one)
    two = run("two-jobs", [*common, "--second"], "START\nCOMMIT0\nSECOND\nCOMMIT1\n", 0)
    second = verify(two, 2)
    store_results = {}
    if include_store42:
        fixture = [*common, "--fixture-store42"]
        dry = run("store42-dry-run", ["--dry-run", "--fixture-store42"], "", 0)
        if len(dry) != 1 or dry[0].get("expected_first_output") != STORE42:
            raise ValueError("store42 dry-run must emit only its independent CPU plan")
        wrong = run("store42-wrong-model", ["--run", "--fixture-store42"], "START\nCOMMIT0\n", 78)
        if [row["event"] for row in wrong] != ["PLAN", "ERROR"]:
            raise ValueError("store42 wrong model reached a Metal API marker")
        for name, stdin in (("store42-refused-start", "NO\n"), ("store42-eof-start", "")):
            refused = run(name, fixture, stdin, 65)
            if [row["event"] for row in refused] != ["PLAN", "WAIT_START", "ERROR"]:
                raise ValueError("store42 START refusal reached a Metal API marker")
        refused = run("store42-refused-commit", fixture, "START\nNO\n", 65)
        if "BEFORE_COMMIT" in [row["event"] for row in refused] or refused[-1]["event"] != "ERROR":
            raise ValueError("store42 refused commit still submitted workload")
        one_store = run("store42-one-job", fixture, "START\nCOMMIT0\n", 0)
        two_store = run("store42-two-jobs", [*fixture, "--second"], "START\nCOMMIT0\nSECOND\nCOMMIT1\n", 0)
        store_results = {"one_job": verify(one_store, workload="store42-256"),
                         "two_jobs": verify(two_store, 2, "store42-256"),
                         "surrounding_bo_canaries": "UNTESTED; outside the owned Metal buffer"}
    result = {"schema": 1, "status": "WORKS (builder validation only)",
              "builder_model": actual, "builder_architecture": platform.machine(),
              "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
              "cases": cases, "one_job": first, "two_jobs": second,
              "m4_pro_execution": "UNTESTED", "first_global_firmware_job": "UNTESTED",
              "target_access": False, "persistent_installation": False}
    if include_store42:
        result["store42_fixture"] = store_results
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument("--include-store42", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.binary, args.output, args.include_store42), indent=2))


if __name__ == "__main__":
    main()
