"""Offline admission regression for the observed missing-save-retry verdict."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import _paths
from ergoqa.png import encode, new_image
from uxpersonas.agent_run import Execution
from uxpersonas.scale_run import Evidence, _project_model_observations
from uxresearch.canonical import EngineError, byte_digest


NOTICE = "Storage quota exceeded while saving result; prior result retained without retry button."


def _check_save_failure(facts, text):
    attempt = facts.get("import_attempt", {})
    fault = attempt.get("storage_fault", {})
    controls = facts.get("controls", [])
    has_retry = any(c.get("label") == "Retry save" for c in controls)
    if fault.get("consumed") and fault.get("restored") and attempt.get("persistence_unchanged") and not has_retry:
        return [{"kind": "success", "index": 0, "status": "failed",
                 "reason": "The write-failure notice and unchanged persisted state were observed, but the required direct save-retry control was absent."}]
    return []


def save_failure_result():
    snapshot = {"available": True, "keys": ["owned_state_v7"], "sha256": "a" * 64}
    facts = {
        "last_action": "upload_save_failure", "import_attempt_id": "upload-7",
        "storage_snapshot": copy.deepcopy(snapshot),
        "controls": [{"tag": "button", "label": "Choose another file", "visible": True, "disabled": False}],
        "import_attempt": {
            "schema_version": "ux-import-attempt.v1", "attempt_id": "upload-7",
            "tool": "upload_save_failure", "fixture": "owned-sample-previous.zip",
            "fixture_sha256": "f" * 64, "storage_before": copy.deepcopy(snapshot),
            "storage_after": copy.deepcopy(snapshot), "persistence_unchanged": True,
            "storage_fault": {"key": "owned_state_v7", "consumed": True, "restored": True},
            "terminal_state": "storage_fault_consumed",
        },
    }
    checks = _check_save_failure(facts, NOTICE)
    return {"text": NOTICE, "facts": facts, "captures": [], "checks": checks}


class NativeCheckReasonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.evidence = self.root / "evidence/task-test/1"
        self.evidence.mkdir(parents=True)
        self.worker = {
            "context_id": "ctx-test", "observations": [],
            "claim": {
                "task": {"id": "task-test", "success_criteria": ["Save failure exposes direct retry"],
                         "recovery_criteria": []},
                "binding": {"revision": 1, "profile_sha256": "a" * 64},
                "evidence_path": str(self.evidence), "attempt": 1,
            },
            "queue_claim": {"owner": "worker", "lease_token": "b" * 64},
        }

    def executor(self, kind):
        if kind == "scale":
            return Evidence(self.root)
        execution = Execution.__new__(Execution)
        execution.root = self.root
        return execution

    def result_with_png(self):
        result = save_failure_result()
        raw = encode(new_image(2, 2))  # Authored offline artifact, never a browser capture.
        path = self.evidence / "synthetic-screen.png"
        path.write_bytes(raw)
        path.chmod(0o600)
        result["captures"] = [{"path": path.name, "sha256": byte_digest(raw)}]
        return result

    def test_actual_failed_save_retry_verdict_is_admitted_by_both_paths_and_retained(self):
        result = self.result_with_png()
        self.assertEqual(result["checks"][0]["status"], "failed")
        self.assertIn("direct save-retry control was absent", result["checks"][0]["reason"])
        for index, kind in enumerate(("execution", "scale"), 1):
            with self.subTest(kind=kind):
                admitted = self.executor(kind).observation(self.worker, "inspect storage failure", result, index)
                self.assertEqual(admitted["checks"], result["checks"])
                saved = json.loads((self.evidence / f"agent-observation-{index}.json").read_text())
                self.assertEqual(saved["observation"]["checks"], result["checks"])
                projected, _ = _project_model_observations([admitted])
                self.assertEqual(projected[0]["checks"], result["checks"])

    def test_reason_length_boundary_remains_320_for_failed_and_not_run(self):
        for index, status in enumerate(("failed", "not_run"), 1):
            result = {"text": "Bounded synthetic observation.", "facts": {}, "captures": [],
                      "checks": [{"kind": "success", "index": 0, "status": status, "reason": "r" * 320}]}
            admitted = self.executor("execution").observation(self.worker, "inspect", result, index)
            self.assertEqual(len(admitted["checks"][0]["reason"]), 320)

    def test_passed_blank_non_string_oversized_and_extra_fields_stay_rejected(self):
        base = {"kind": "success", "index": 0, "status": "failed", "reason": "Diagnostic."}
        cases = [
            dict(base, status="passed"), dict(base, reason=""), dict(base, reason="  "),
            dict(base, reason=None), dict(base, reason=7), dict(base, reason="r" * 321),
            dict(base, extra="unexpected"), dict(base, index=1),
        ]
        for kind in ("execution", "scale"):
            for index, check in enumerate(cases, 1):
                with self.subTest(kind=kind, check=check):
                    result = {"text": "Synthetic observation.", "facts": {}, "captures": [], "checks": [check]}
                    with self.assertRaises(EngineError) as caught:
                        self.executor(kind).observation(self.worker, "inspect", result, index)
                    self.assertEqual(caught.exception.issue["code"], "observation_invalid")

    def test_private_identifiers_in_failed_reason_stay_rejected(self):
        result = {"text": "Synthetic observation.", "facts": {}, "captures": [], "checks": [
            {"kind": "success", "index": 0, "status": "failed", "reason": "Contact synthetic.person@example.com."}]}
        for kind in ("execution", "scale"):
            with self.subTest(kind=kind), self.assertRaises(EngineError) as caught:
                self.executor(kind).observation(self.worker, "inspect", result, 1)
            self.assertEqual(caught.exception.issue["code"], "host_privacy")

    def test_admitted_native_failure_survives_interruption_and_cannot_be_erased(self):
        result = self.result_with_png()
        evidence = self.executor("scale")
        observed = evidence.observation(self.worker, "inspect storage failure", result, 1)
        self.worker["observations"] = [observed]
        state = {"observations": [observed]}
        plan = {"build": {"sha256": "c" * 64}}
        execution = self.executor("execution")
        base_receipt = {"drafting_guidance": {}, "criteria": [
            {"kind": "success", "index": 0, "status": "not_run", "observation": "Not observed.", "evidence_ids": []}],
            "outcome": "inconclusive"}
        execution.validate_claim = lambda worker: copy.deepcopy(base_receipt)
        with patch("uxpersonas.scale_run.swarm._receipt", side_effect=lambda root, job, value: value):
            partial = evidence.receipt(self.worker, state, plan, judgment=None)
            old_partial = execution.make_receipt(self.worker, judgment=None)
            self.assertEqual(partial["criteria"][0]["status"], "failed")
            self.assertEqual(old_partial["criteria"][0]["status"], "failed")
            for status in ("passed", "not_run"):
                judgment = {"reason": "Synthetic model tries to omit the failure.", "criteria": [
                    {"kind": "success", "index": 0, "status": status, "observation": "Model proposal.",
                     "observation_ids": ["obs-1"] if status == "passed" else []}]}
                for make in (
                    lambda: evidence.receipt(self.worker, state, plan, judgment=judgment),
                    lambda: execution.make_receipt(self.worker, judgment=judgment),
                ):
                    with self.subTest(status=status), self.assertRaises(EngineError) as caught:
                        make()
                    self.assertEqual(caught.exception.issue["code"], "erased_failure")


if __name__ == "__main__":
    unittest.main()
