import json
from pathlib import Path
import unittest

from verify_transcript import FIRST, INPUT, POISON, STORE42, verify


EVIDENCE = Path(__file__).parent / "evidence/builder-validation"


def load(name, directory=EVIDENCE):
    return [json.loads(line) for line in (directory / (name + ".jsonl")).read_text().splitlines()]


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


STORE_EVIDENCE = Path(__file__).parent / "evidence/store42-builder"


class Store42TranscriptTests(unittest.TestCase):
    def fixture(self, second=False):
        return load("store42-two-jobs" if second else "store42-one-job", STORE_EVIDENCE)

    def test_actual_builder_checks_all_256_literal_values(self):
        rows = self.fixture()
        result = verify(rows, workload="store42-256")
        self.assertEqual(result["words_per_submission"], 256)
        self.assertEqual(result["m4_pro_hardware"], "UNTESTED")
        values = next(row["words"] for row in rows if row["event"] == "READBACK")
        self.assertEqual(len(values), 256)
        self.assertTrue(all(int(value, 16) == 42 for value in values))
        self.assertEqual(next(row["input"] for row in rows if row["event"] == "BUFFER_READY"), POISON)

    def test_second_store_keeps_literal_42_rather_than_restoring_poison(self):
        rows = self.fixture(True)
        self.assertEqual(verify(rows, 2, "store42-256")["submissions"], 2)
        self.assertEqual([row["words"] for row in rows if row["event"] == "READBACK"], [STORE42, STORE42])

    def test_store_requires_explicit_contract_selection(self):
        with self.assertRaises(ValueError): verify(self.fixture())
        with self.assertRaises(ValueError): verify(load("one-job"), workload="store42-256")

    def test_any_wrong_word_or_truncated_output_is_rejected(self):
        for index in (0, 127, 255):
            rows = self.fixture()
            next(row for row in rows if row["event"] == "READBACK")["words"][index] = "a5a5a5a5"
            with self.subTest(index=index):
                with self.assertRaises(ValueError): verify(rows, workload="store42-256")
        rows = self.fixture()
        next(row for row in rows if row["event"] == "READBACK")["words"].pop()
        with self.assertRaises(ValueError): verify(rows, workload="store42-256")

    def test_self_consistent_wrong_expected_and_readback_cannot_pass(self):
        rows = self.fixture()
        rows[0]["expected_first_output"] = ["0000002b"] * 256
        next(row for row in rows if row["event"] == "READBACK")["words"] = ["0000002b"] * 256
        with self.assertRaises(ValueError): verify(rows, workload="store42-256")

    def test_input_must_be_all_poison_including_last_word(self):
        rows = self.fixture()
        next(row for row in rows if row["event"] == "BUFFER_READY")["input"][255] = "0000002a"
        with self.assertRaises(ValueError): verify(rows, workload="store42-256")

    def test_exact_buffer_geometry_and_dispatch_are_required(self):
        for key, value in (("words", 255), ("buffer_bytes", 4096), ("store_value", 43),
                           ("initial_word_hex", "00000000"), ("threadgroups", [2, 1, 1]),
                           ("threads_per_threadgroup", [128, 1, 1]), ("grid", [512, 1, 1]),
                           ("dispatch_api", "dispatchThreads")):
            rows = self.fixture()
            rows[0][key] = value
            with self.subTest(field=key):
                with self.assertRaises(ValueError): verify(rows, workload="store42-256")

    def test_unsupported_pipeline_maximum_is_rejected(self):
        for value in (255, None, True, "1024"):
            rows = self.fixture()
            next(row for row in rows if row["event"] == "PIPELINE_READY")["max_threads_per_threadgroup"] = value
            with self.subTest(maximum=value):
                with self.assertRaises(ValueError): verify(rows, workload="store42-256")

    def test_start_and_commit_cannot_be_claimed_without_exact_tokens(self):
        for gate in ("WAIT_START", "WAIT_COMMIT"):
            rows = self.fixture()
            next(row for row in rows if row["event"] == "GATE_ACCEPTED" and row["gate"] == gate)["accepted_stdin"] = "NO"
            with self.subTest(gate=gate):
                with self.assertRaises(ValueError): verify(rows, workload="store42-256")

    def test_second_store_requires_its_own_gates(self):
        for gate in ("WAIT_SECOND", "WAIT_COMMIT"):
            rows = self.fixture(True)
            next(row for row in rows if row["event"] == "GATE_ACCEPTED" and row["gate"] == gate and row["submission"] == 1)["submission"] = 0
            with self.subTest(gate=gate):
                with self.assertRaises(ValueError): verify(rows, 2, "store42-256")

    def test_incomplete_command_or_false_pass_cannot_succeed(self):
        for event, key, value in (("COMMAND_COMPLETED", "status", 5), ("READBACK", "pass", False),
                                  ("DONE", "verified_words_per_submission", 255)):
            rows = self.fixture()
            next(row for row in rows if row["event"] == event)[key] = value
            with self.subTest(event=event):
                with self.assertRaises(ValueError): verify(rows, workload="store42-256")

    def test_actual_builder_store_refusals_have_no_causal_submission(self):
        for name in ("store42-wrong-model", "store42-refused-start", "store42-eof-start"):
            with self.subTest(name=name):
                self.assertNotIn("BEFORE_DEVICE", [row["event"] for row in load(name, STORE_EVIDENCE)])
        events = [row["event"] for row in load("store42-refused-commit", STORE_EVIDENCE)]
        self.assertIn("WAIT_COMMIT", events)
        self.assertNotIn("BEFORE_COMMIT", events)
        self.assertNotIn("COMMAND_COMPLETED", events)

    def test_updated_binary_preserves_xor_contract(self):
        self.assertEqual(verify(load("one-job", STORE_EVIDENCE))["words_per_submission"], 16)
        self.assertEqual(verify(load("two-jobs", STORE_EVIDENCE), 2)["words_per_submission"], 16)


if __name__ == "__main__":
    unittest.main()
