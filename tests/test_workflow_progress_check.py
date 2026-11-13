import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "workflow_progress_check", Path(__file__).resolve().parents[1] / "scripts/workflow_progress_check.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WorkflowProgressTest(unittest.TestCase):
    def review(self, **changes):
        data = {"action": "review", "review_key": "purpose:sha:deps:conditions",
                "accepted_review_keys": ["purpose:sha:deps:conditions"]}
        return MODULE.assess({**data, **changes})

    def work(self, **changes):
        data = {"action": "work", "unchanged_goal_turns": 3,
                "safe_next_action": False, "live_handle_verified": False}
        return MODULE.assess({**data, **changes})

    def test_accepted_unchanged_review_reused(self):
        self.assertEqual(self.review()["findings"], ["REUSE_ACCEPTED_REVIEW"])

    def test_actual_review_reopening_reasons_allowed(self):
        for field in ("new_evidence", "new_issue", "constraints_changed", "user_requested_repeat"):
            with self.subTest(field=field):
                self.assertNotIn("REUSE_ACCEPTED_REVIEW", self.review(**{field: True})["findings"])

    def test_different_version_or_purpose_allowed(self):
        self.assertEqual(self.review(review_key="different:sha:deps:conditions")["findings"], [])

    def test_consultation_count_not_limited(self):
        self.assertEqual(self.review(new_evidence=True, consultation_count=1000)["findings"], [])

    def test_large_decisive_packet_allowed(self):
        self.assertEqual(self.review(new_evidence=True, packet_chars=180354, packet_justified=True)["findings"], [])

    def test_large_packet_needs_background_trim_not_evidence_deletion(self):
        self.assertIn("TRIM_DUPLICATE_BACKGROUND_KEEP_DECISIVE_RAW", self.review(packet_chars=180354, duplicate_background_confirmed=True)["findings"])

    def test_large_packet_unknown_relevance_does_not_assume_duplicates(self):
        result = self.review(packet_chars=12001)["findings"]
        self.assertIn("VERIFY_PACKET_RELEVANCE_KEEP_DECISIVE_RAW", result)
        self.assertNotIn("TRIM_DUPLICATE_BACKGROUND_KEEP_DECISIVE_RAW", result)

    def test_unselected_threat_model_not_automatic_gate(self):
        for origin in ("review_suggestion", "unknown"):
            with self.subTest(origin=origin):
                result = self.work(added_threat_model="same_uid_tamper", threat_model_origin=origin)
                self.assertIn("RESOLVE_THREAT_SCOPE_BEFORE_ADDING_GATE", result["findings"])

    def test_explicit_safety_requirements_not_relaxed(self):
        for origin in ("contract", "user", "confirmed_failure"):
            with self.subTest(origin=origin):
                result = self.work(safe_next_action=True, added_threat_model="same_uid_tamper", threat_model_origin=origin)
                self.assertNotIn("RESOLVE_THREAT_SCOPE_BEFORE_ADDING_GATE", result["findings"])
                self.assertFalse(result["permission_granted"])

    def test_third_no_progress_turn_reports_blocker(self):
        self.assertIn("MARK_BLOCKED_IF_SAME_IMPEDIMENT_CONSECUTIVE", self.work()["findings"])

    def test_first_and_second_turn_not_blocked(self):
        for turns in (0, 1, 2):
            self.assertEqual(self.work(unchanged_goal_turns=turns)["findings"], [])

    def test_safe_work_not_stopped(self):
        self.assertEqual(self.work(unchanged_goal_turns=20, safe_next_action=True)["findings"], [])

    def test_verified_wait_keeps_same_job(self):
        self.assertEqual(self.work(live_handle_verified=True, live_handle_id="actual-live-job", minutes_without_progress=60)["findings"], ["WAIT_SAME_VERIFIED_LIVE_HANDLE"])

    def test_claimed_wait_without_handle_rejected(self):
        with self.assertRaises(ValueError):
            self.work(live_handle_verified=True)

    def test_twenty_minutes_is_checkpoint_not_permission(self):
        result = self.work(unchanged_goal_turns=1, minutes_without_progress=20)
        self.assertEqual(result["findings"], ["REASSESS_CRITICAL_PATH_NO_NEW_PAPERWORK"])
        self.assertFalse(result["permission_granted"])
        self.assertFalse(result["state_or_jobs_changed"])

    def test_malformed_state_not_silently_successful(self):
        for value in (None, [], {}, {"action": "work"}, {"action": "review"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.assess(value)
        with self.assertRaises(ValueError):
            self.work(unchanged_goal_turns=True)
        with self.assertRaises(ValueError):
            self.review(new_evidence="false")

    def test_short_circuit_does_not_hide_bad_fields(self):
        with self.assertRaises(ValueError):
            self.review(new_evidence=True, new_issue="false")
        with self.assertRaises(ValueError):
            self.review(packet_chars=0, packet_justified="false")

    def test_unhashable_enum_inputs_rejected_cleanly(self):
        with self.assertRaises(ValueError):
            MODULE.assess({"action": []})
        with self.assertRaises(ValueError):
            self.work(added_threat_model="tamper", threat_model_origin=[])


class WorkflowProgressCliTest(unittest.TestCase):
    def run_cli(self, raw, *args):
        result = subprocess.run(
            [sys.executable, str(Path(MODULE.__file__)), *args], input=raw,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        )
        self.assertEqual(result.stderr, b"")
        output = json.loads(result.stdout)
        self.assertFalse(output["permission_granted"])
        return result.returncode, output

    def test_valid_json_exit_zero(self):
        code, result = self.run_cli(b'{"action":"review","review_key":"p:v:d:c"}')
        self.assertEqual(code, 0)
        self.assertTrue(result["advisory_only"])
        self.assertFalse(result["state_or_jobs_changed"])

    def test_invalid_json_does_not_echo_input(self):
        for raw in (b"private-marker", b'{"action": [}', b"\xff"):
            with self.subTest(raw=raw):
                code, result = self.run_cli(raw)
                self.assertEqual(code, 2)
                self.assertNotIn("private-marker", result["error"])

    def test_deep_json_is_handled_error(self):
        raw = b'{"action":"work","extra":' + b"[" * 20000 + b"0" + b"]" * 20000 + b"}"
        code, result = self.run_cli(raw)
        self.assertEqual(code, 2)
        self.assertEqual(result["error"], "JSON nesting exceeds parser capacity")

    def test_size_boundary(self):
        base = b'{"action":"review","review_key":"p:v:d:c","extra":""}'
        for count, expected in ((65536, 0), (65537, 2)):
            with self.subTest(count=count):
                raw = base[:-2] + b"x" * (count - len(base)) + base[-2:]
                self.assertEqual(len(raw), count)
                code, _ = self.run_cli(raw)
                self.assertEqual(code, expected)

    def test_file_read_error_exit_two(self):
        missing = Path(__file__).resolve().parent / "missing-workflow-input" / "state.json"
        code, result = self.run_cli(b"", "--input", str(missing))
        self.assertEqual(code, 2)
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
