import copy
import json
from pathlib import Path
import unittest

from verify_transcript import FIRST, INPUT, verify


EVIDENCE = Path(__file__).parent / "evidence/builder-validation"


def load(name):
    return [json.loads(line) for line in (EVIDENCE / (name + ".jsonl")).read_text().splitlines()]


class TranscriptTests(unittest.TestCase):
    def test_actual_builder_first_job(self):
        result = verify(load("one-job"))
        self.assertEqual(result["submissions"], 1)
        self.assertEqual(result["m4_pro_hardware"], "UNTESTED")
        self.assertEqual(result["earliest_global_firmware_job"], "UNTESTED")

    def test_actual_builder_two_jobs_restore_input(self):
        result = verify(load("two-jobs"), 2)
        self.assertEqual(result["submissions"], 2)
        readbacks = [row["words"] for row in load("two-jobs") if row["event"] == "READBACK"]
        self.assertEqual(readbacks, [FIRST, INPUT])

    def test_success_boolean_cannot_hide_wrong_output(self):
        rows = load("one-job")
        readback = next(row for row in rows if row["event"] == "READBACK")
        readback["words"][0] = "00000000"
        self.assertTrue(readback["pass"])
        with self.assertRaises(ValueError): verify(rows)

    def test_failed_readback_cannot_pass_with_correct_words(self):
        rows = load("one-job")
        next(row for row in rows if row["event"] == "READBACK")["pass"] = False
        with self.assertRaises(ValueError): verify(rows)

    def test_failed_command_status_is_rejected(self):
        rows = load("one-job")
        next(row for row in rows if row["event"] == "COMMAND_COMPLETED")["status"] = 5
        with self.assertRaises(ValueError): verify(rows)

    def test_wrong_commit_gate_is_rejected(self):
        rows = load("one-job")
        next(row for row in rows if row["event"] == "WAIT_COMMIT")["expect_stdin"] = "COMMIT1"
        with self.assertRaises(ValueError): verify(rows)

    def test_acceptance_without_exact_start_or_commit_token_is_rejected(self):
        for event in ("WAIT_START", "WAIT_COMMIT"):
            rows = load("one-job")
            accepted = next(row for row in rows if row["event"] == "GATE_ACCEPTED" and row["gate"] == event)
            accepted["accepted_stdin"] = "WRONG"
            with self.subTest(gate=event):
                with self.assertRaises(ValueError): verify(rows)

    def test_ungated_second_submission_is_rejected(self):
        rows = [row for row in load("two-jobs") if row["event"] != "WAIT_SECOND"]
        with self.assertRaises(ValueError): verify(rows, 2)

    def test_default_mode_cannot_admit_two_submissions(self):
        with self.assertRaises(ValueError): verify(load("two-jobs"))

    def test_reordered_or_missing_markers_are_rejected(self):
        rows = load("one-job")
        for variant in (rows[:-1], rows[:3] + [rows[4], rows[3]] + rows[5:]):
            with self.subTest(events=[row["event"] for row in variant]):
                with self.assertRaises(ValueError): verify(variant)

    def test_inconsistent_buffer_identity_is_rejected(self):
        rows = load("one-job")
        next(row for row in rows if row["event"] == "BUFFER_READY")["gpu_address_le"] = "0" * 16
        with self.assertRaises(ValueError): verify(rows)

    def test_nonmonotonic_time_is_rejected(self):
        rows = load("one-job")
        rows[-1]["monotonic_ns"] = rows[0]["monotonic_ns"] - 1
        with self.assertRaises(ValueError): verify(rows)

    def test_negative_builder_cases_never_reached_device_marker(self):
        for name in ("wrong-model", "refused-start", "eof-start"):
            with self.subTest(name=name):
                self.assertNotIn("BEFORE_DEVICE", [row["event"] for row in load(name)])

    def test_refused_commit_never_submitted_user_job(self):
        events = [row["event"] for row in load("refused-commit")]
        self.assertIn("WAIT_COMMIT", events)
        self.assertNotIn("BEFORE_COMMIT", events)
        self.assertNotIn("COMMAND_COMPLETED", events)


if __name__ == "__main__":
    unittest.main()
