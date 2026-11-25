"""Owned receipt-admission regressions; no live-product, browser or user-effect evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

SKILL_ROOT = Path(os.environ.get(
    "REMORSEARCH_TEST_SKILL_ROOT",
    Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa")).resolve()
sys.path.insert(0, str(SKILL_ROOT))
from uxpersonas import swarm
from uxresearch.canonical import EngineError, byte_digest, digest
from uxresearch.storage import read_json

# Reuse the existing owned fixture, without importing its TestCase into discovery.
import test_persona_swarm as existing


class ReceiptAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.f = existing.SwarmTests("test_pass_and_report_limits")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.spec["tasks"][0]["requirement_coverage"] = self.f.coverage()
        self.now = [1000.0]
        clock = patch.object(swarm.time, "time", side_effect=lambda: self.now[0])
        clock.start()
        self.addCleanup(clock.stop)

    def prepare(self, outcome="passed", name="run"):
        self.f.run = self.f.root / name
        self.f.plan()
        claim = swarm.claim(self.f.lib, self.f.run, "owned-worker")
        return claim, self.f.receipt(claim, outcome)

    def snapshot(self):
        return {str(p.relative_to(self.f.run)): byte_digest(p.read_bytes())
                for p in self.f.run.rglob("*") if p.is_file()}

    def state(self):
        return read_json(self.f.run / "swarm-state.json")["payload"]

    def late_receipt(self, claim, receipt, *, during="artifacts", offset=0):
        before = self.snapshot()
        function = "_artifacts" if during == "artifacts" else "_state_bytes"
        original = getattr(swarm, function)

        def finish(*args, **kwargs):
            result = original(*args, **kwargs)
            self.now[0] = claim["lease"]["expires_at"] + offset
            return result

        with patch.object(swarm, function, side_effect=finish):
            with self.assertRaises(EngineError) as caught:
                swarm.record(self.f.lib, self.f.run, receipt)
        self.assertEqual(caught.exception.issue["code"], "lease_expired")
        self.assertIn("next_step", caught.exception.issue)
        self.assertEqual(self.snapshot(), before)

    def test_loaded_module_is_the_selected_source_or_extracted_bundle(self):
        self.assertTrue(Path(swarm.__file__).resolve().is_relative_to(SKILL_ROOT))

    def test_expiry_during_artifact_validation_is_rejected_before_save(self):
        claim, receipt = self.prepare()
        self.late_receipt(claim, receipt)

    def test_expiry_during_state_encoding_is_rejected_before_atomic_handoff(self):
        claim, receipt = self.prepare()
        self.late_receipt(claim, receipt, during="encoding")

    def test_every_terminal_outcome_obeys_the_same_final_deadline(self):
        for outcome in ("passed", "failed", "blocked", "inconclusive", "skipped"):
            with self.subTest(outcome=outcome):
                self.now[0] = 1000.0
                claim, receipt = self.prepare(outcome, "run-" + outcome)
                self.late_receipt(claim, receipt, offset=1)

    def test_valid_handoff_before_deadline_preserves_the_reviewed_journey(self):
        claim, receipt = self.prepare()
        original = swarm._state_bytes

        def encode_before_deadline(state):
            raw = original(state)
            self.now[0] = claim["lease"]["expires_at"] - 0.001
            return raw

        with patch.object(swarm, "_state_bytes", side_effect=encode_before_deadline):
            result = swarm.record(self.f.lib, self.f.run, receipt)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(self.state()["tasks"][0]["task"], self.f.spec["tasks"][0])
        report = swarm.report(self.f.lib, self.f.run)
        self.assertEqual(report["counts"]["passed"], 1)
        self.assertTrue(report["coverage_summary"]["all_declared_requirements_passed"])
        self.assertFalse(report["product_ready"])

    def test_saved_receipt_is_the_same_detached_snapshot_that_was_validated(self):
        _, supplied = self.prepare()
        expected = copy.deepcopy(supplied)
        original = swarm._receipt

        def validate_then_mutate_caller(root, entry, receipt):
            result = original(root, entry, receipt)
            supplied["reason"] = "Unvalidated replacement after inspection."
            supplied["outcome"] = "blocked"
            supplied["worker_id"] = "unvalidated-caller"
            supplied["criteria"][0]["status"] = "failed"
            supplied["steps"][0]["observation"] = "Changed outside the checked snapshot."
            supplied["steps"][0]["evidence_ids"].clear()
            return result

        with patch.object(swarm, "_receipt", side_effect=validate_then_mutate_caller):
            swarm.record(self.f.lib, self.f.run, supplied)
        saved = self.state()["tasks"][0]["receipt"]
        self.assertEqual(digest(saved), digest(expected))
        self.assertNotEqual(digest(supplied), digest(expected))

    def test_caller_mutation_cannot_bypass_the_checked_privacy_boundary(self):
        _, supplied = self.prepare()
        expected = copy.deepcopy(supplied)
        original = swarm._receipt

        def validate_then_mutate_caller(root, entry, receipt):
            result = original(root, entry, receipt)
            supplied["reason"] = "owned-synthetic-marker@example.invalid"
            return result

        with patch.object(swarm, "_receipt", side_effect=validate_then_mutate_caller):
            swarm.record(self.f.lib, self.f.run, supplied)
        self.assertEqual(digest(self.state()["tasks"][0]["receipt"]), digest(expected))
        self.assertNotIn(b"owned-synthetic-marker", (self.f.run / "swarm-state.json").read_bytes())

    def test_fresh_report_retains_unknown_attempt_and_no_pass_after_late_rejection(self):
        claim, receipt = self.prepare()
        self.late_receipt(claim, receipt)
        artifacts = {a["path"]: (self.f.run / a["path"]).read_bytes() for a in receipt["artifacts"]}
        report = swarm.report(self.f.lib, self.f.run)
        row = report["tasks"][0]
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertEqual(row["attempts"], 1)
        self.assertEqual(row["operation_id"], claim["operation_id"])
        self.assertIsNone(row["result"])
        self.assertTrue(row["resource_quarantined"])
        self.assertEqual(row["requirement_results"][0]["status"], "incomplete")
        self.assertEqual(self.state()["tasks"][0]["task"], self.f.spec["tasks"][0])
        for path, raw in artifacts.items():
            self.assertEqual((self.f.run / path).read_bytes(), raw)

    def test_expired_receipt_never_renews_or_silently_retries_the_attempt(self):
        claim, receipt = self.prepare()
        self.late_receipt(claim, receipt)
        swarm.report(self.f.lib, self.f.run)
        self.assertFalse(swarm.claim(self.f.lib, self.f.run, "second-worker")["claimed"])
        with self.assertRaises(EngineError):
            swarm.retry(self.f.lib, self.f.run, "T1")
        inspection = dict(operation_id=claim["operation_id"], attempt=1,
                          outcome="not_executed", worker_stopped=True,
                          note="Inspected the owned fixture; no product action ran.")
        swarm.retry(self.f.lib, self.f.run, "T1", reconciliation=inspection)
        self.now[0] += 1
        next_claim = swarm.claim(self.f.lib, self.f.run, "second-worker")
        self.assertEqual(next_claim["operation_id"], claim["operation_id"])
        self.assertEqual(next_claim["attempt"], 2)
        before = self.snapshot()
        with self.assertRaises(EngineError):
            swarm.record(self.f.lib, self.f.run, receipt)
        self.assertEqual(self.snapshot(), before)
        swarm.record(self.f.lib, self.f.run, self.f.receipt(next_claim))
        report = swarm.report(self.f.lib, self.f.run)
        self.assertEqual(report["tasks"][0]["prior_outcomes"], ["inconclusive"])
        self.assertEqual(report["counts"]["passed"], 1)
        self.assertFalse(report["product_ready"])

    def test_new_process_reads_the_preserved_attempt_as_inconclusive(self):
        claim, receipt = self.prepare()
        self.late_receipt(claim, receipt)
        child = """
import json, sys
from pathlib import Path
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from uxpersonas import swarm
from test_persona_swarm import FakeLibrary
report = swarm.report(FakeLibrary(), sys.argv[3])
row = report['tasks'][0]
print(json.dumps(dict(module=str(Path(swarm.__file__).resolve()),
    counts=report['counts'], product_ready=report['product_ready'],
    status=row['status'], attempts=row['attempts'], operation_id=row['operation_id'],
    result=row['result'], resource_quarantined=row['resource_quarantined'])))
"""
        result = subprocess.run(
            [sys.executable, "-c", child, str(SKILL_ROOT),
             str(Path(__file__).resolve().parent), str(self.f.run)],
            text=True, capture_output=True, timeout=10,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        recovered = json.loads(result.stdout)
        self.assertTrue(Path(recovered["module"]).is_relative_to(SKILL_ROOT))
        self.assertEqual(recovered["counts"]["passed"], 0)
        self.assertEqual(recovered["counts"]["inconclusive"], 1)
        self.assertEqual(recovered["status"], "inconclusive")
        self.assertEqual(recovered["attempts"], 1)
        self.assertEqual(recovered["operation_id"], claim["operation_id"])
        self.assertIsNone(recovered["result"])
        self.assertTrue(recovered["resource_quarantined"])
        self.assertFalse(recovered["product_ready"])

    def test_writer_lock_and_expired_write_quarantine_fence_competing_claims(self):
        for task_id, resource in (("T2", "browser1"), ("T3", "separate-fixture")):
            task = copy.deepcopy(self.f.spec["tasks"][0])
            task.update(id=task_id, data_namespace="owned-" + task_id, resource_id=resource)
            self.f.spec["tasks"].append(task)
        claim, receipt = self.prepare()
        entered, release = threading.Event(), threading.Event()
        original, store = swarm._artifacts, swarm.Store

        def inspect_and_wait(*args, **kwargs):
            result = original(*args, **kwargs)
            self.now[0] = claim["lease"]["expires_at"]
            entered.set()
            if not release.wait(timeout=3):
                raise AssertionError("Owned contender failed to release its gate.")
            return result

        def record():
            try:
                swarm.record(self.f.lib, self.f.run, receipt)
            except EngineError as exc:
                return exc.issue["code"]
            return "incorrectly_accepted"

        with patch.object(swarm, "_artifacts", side_effect=inspect_and_wait), \
                patch.object(swarm, "Store", side_effect=lambda root: store(root, timeout=0.1)):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(record)
                try:
                    self.assertTrue(entered.wait(timeout=3))
                    with self.assertRaises(EngineError) as caught:
                        swarm.claim(self.f.lib, self.f.run, "contender", task_id="T2")
                    self.assertEqual(caught.exception.issue["code"], "lock_busy")
                finally:
                    release.set()
                self.assertEqual(pending.result(timeout=3), "lease_expired")
        self.assertFalse(swarm.claim(self.f.lib, self.f.run, "contender", task_id="T2")["claimed"])
        self.assertTrue(swarm.claim(self.f.lib, self.f.run, "independent", task_id="T3")["claimed"])
        report = swarm.report(self.f.lib, self.f.run)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertEqual(report["counts"]["inconclusive"], 1)

    def test_wrong_lease_is_refused_before_any_artifact_inspection(self):
        _, receipt = self.prepare()
        receipt["lease_token"] = "wrong-owned-token"
        before = self.snapshot()
        with patch.object(swarm, "_artifacts", side_effect=AssertionError("Must not inspect")):
            with self.assertRaises(EngineError) as caught:
                swarm.record(self.f.lib, self.f.run, receipt)
        self.assertEqual(caught.exception.issue["code"], "lease_mismatch")
        self.assertEqual(self.snapshot(), before)

    def test_missing_capture_and_unsafe_evidence_remain_rejections(self):
        _, receipt = self.prepare()
        before = self.snapshot()
        wrong = copy.deepcopy(receipt)
        wrong["artifacts"] = wrong["artifacts"][:1]
        with self.assertRaises(EngineError):
            swarm.record(self.f.lib, self.f.run, wrong)
        self.assertEqual(self.snapshot(), before)
        path = self.f.run / receipt["artifacts"][0]["path"]
        path.chmod(0o644)
        try:
            with self.assertRaises(EngineError):
                swarm.record(self.f.lib, self.f.run, receipt)
            self.assertEqual(self.snapshot(), before)
        finally:
            path.chmod(0o600)

    def test_publication_failure_preserves_the_attempt_and_can_be_inspected(self):
        _, receipt = self.prepare()
        before = self.snapshot()
        with patch.object(swarm, "atomic", side_effect=OSError("owned pre-publication failure")):
            with self.assertRaises(OSError):
                swarm.record(self.f.lib, self.f.run, receipt)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(swarm.record(self.f.lib, self.f.run, receipt)["status"], "passed")

    def test_lost_save_ack_keeps_one_recorded_result_without_replay(self):
        _, receipt = self.prepare()
        atomic = swarm.atomic

        def write_then_lose_ack(path, raw):
            atomic(path, raw)
            raise OSError("owned acknowledgement loss")

        with patch.object(swarm, "atomic", side_effect=write_then_lose_ack):
            with self.assertRaises(OSError):
                swarm.record(self.f.lib, self.f.run, receipt)
        before = self.snapshot()
        report = swarm.report(self.f.lib, self.f.run)
        self.assertEqual(report["counts"]["passed"], 1)
        with self.assertRaises(EngineError):
            swarm.record(self.f.lib, self.f.run, receipt)
        self.assertEqual(self.snapshot(), before)

    def test_expiry_after_atomic_handoff_does_not_erase_an_accepted_result(self):
        claim, receipt = self.prepare()
        atomic = swarm.atomic

        def dispatched_write(path, raw):
            self.now[0] = claim["lease"]["expires_at"] + 1
            return atomic(path, raw)

        with patch.object(swarm, "atomic", side_effect=dispatched_write):
            self.assertEqual(swarm.record(self.f.lib, self.f.run, receipt)["status"], "passed")
        self.assertEqual(swarm.report(self.f.lib, self.f.run)["counts"]["passed"], 1)

    def test_entry_already_expired_keeps_existing_inconclusive_behavior(self):
        claim, receipt = self.prepare()
        self.now[0] = claim["lease"]["expires_at"]
        with self.assertRaises(EngineError):
            swarm.record(self.f.lib, self.f.run, receipt)
        state = self.state()
        self.assertEqual(state["tasks"][0]["status"], "inconclusive")
        self.assertNotIn("receipt", state["tasks"][0])
        self.assertEqual(state["tasks"][0]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
