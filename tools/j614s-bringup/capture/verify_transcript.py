#!/usr/bin/env python3
"""Validate workload markers and readback, without treating logs as hardware attestation."""
import argparse
import json
import re


FIRST = ["6145a55a", "6145a55b", "6145a558", "6145a559",
         "6145a55e", "6145a55f", "6145a55c", "6145a55d",
         "6145a552", "6145a553", "6145a550", "6145a551",
         "6145a556", "6145a557", "6145a554", "6145a555"]
INPUT = [f"{value:08x}" for value in range(16)]


def verify(records, submissions=1):
    if submissions not in (1, 2):
        raise ValueError("only the one/two job protocol is defined")
    before = ["PLAN", "WAIT_START", "GATE_ACCEPTED", "BEFORE_DEVICE", "DEVICE_READY", "BEFORE_LIBRARY",
              "BEFORE_PIPELINE", "PIPELINE_READY", "BEFORE_BUFFER", "BUFFER_READY", "BEFORE_QUEUE"]
    job = ["BEFORE_ENCODING", "WAIT_COMMIT", "GATE_ACCEPTED", "BEFORE_COMMIT", "COMMAND_COMPLETED", "READBACK"]
    expected_events = before + job + (["WAIT_SECOND", "GATE_ACCEPTED"] + job if submissions == 2 else []) + ["DONE"]
    if [row.get("event") for row in records] != expected_events:
        raise ValueError("missing/reordered/extra capture marker")
    previous = 0
    for row in records:
        timestamp = row.get("monotonic_ns", 0)
        if row.get("schema") != 1 or not isinstance(timestamp, int) or timestamp < previous or timestamp <= 0:
            raise ValueError("invalid marker schema or monotonic clock")
        previous = timestamp
    plan = records[0]
    if (plan.get("words") != 16 or plan.get("buffer_bytes") != 64
            or plan.get("xor_hex") != "6145a55a" or plan.get("submissions") != submissions
            or plan.get("expected_first_output") != FIRST):
        raise ValueError("workload differs from the independently specified 16-word XOR")
    if records[1].get("expect_stdin") != "START":
        raise ValueError("first Metal API must follow the START gate")
    if (records[2].get("gate") != "WAIT_START" or records[2].get("accepted_stdin") != "START"
            or records[2].get("submission") != 0):
        raise ValueError("START acceptance must precede device creation")
    buffer = next(row for row in records if row["event"] == "BUFFER_READY")
    address = buffer.get("gpu_address_hex", "")
    if (not re.fullmatch(r"[0-9a-f]{16}", address) or int(address, 16) == 0
            or buffer.get("gpu_address_le") != int(address, 16).to_bytes(8, "little").hex()
            or buffer.get("input") != INPUT):
        raise ValueError("buffer identity/input markers are inconsistent")
    cursor = len(before)
    for submission in range(submissions):
        if submission:
            gate = records[cursor]
            if gate.get("expect_stdin") != "SECOND" or gate.get("submission") != submission:
                raise ValueError("second job must be separately gated")
            accepted = records[cursor + 1]
            if (accepted.get("gate") != "WAIT_SECOND" or accepted.get("accepted_stdin") != "SECOND"
                    or accepted.get("submission") != submission):
                raise ValueError("second job lacks explicit gate acceptance")
            cursor += 2
        group = records[cursor:cursor + len(job)]
        cursor += len(job)
        if any(row.get("submission") != submission for row in group):
            raise ValueError("submission identity changed")
        if group[1].get("expect_stdin") != f"COMMIT{submission}":
            raise ValueError("command commit gate mismatch")
        if group[2].get("gate") != "WAIT_COMMIT" or group[2].get("accepted_stdin") != f"COMMIT{submission}":
            raise ValueError("command commit lacks explicit gate acceptance")
        if group[4].get("status") != 4:
            raise ValueError("Metal command did not reach Completed")
        if group[5].get("pass") is not True or group[5].get("words") != (FIRST if submission == 0 else INPUT):
            raise ValueError("GPU readback does not match the independent expected vector")
    if records[-1].get("submissions") != submissions or records[-1].get("verified_words_per_submission") != 16:
        raise ValueError("completion count mismatch")
    return {"status": "WORKS", "scope": "this transcript's Metal workload/readback only",
            "submissions": submissions, "words_per_submission": 16,
            "earliest_global_firmware_job": "UNTESTED", "m4_pro_hardware": "UNTESTED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript")
    parser.add_argument("--submissions", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    with open(args.transcript) as source:
        records = [json.loads(line) for line in source if line.strip()]
    print(json.dumps(verify(records, args.submissions), indent=2))


if __name__ == "__main__":
    main()
