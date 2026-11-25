"""Terminal recovery regressions; host attestations are not independent proof."""
import copy
import json
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import _paths
import test_persona_swarm
from test_persona_library import profile_input
from uxpersonas import swarm
from uxpersonas.library import Library
from uxresearch.canonical import EngineError
from uxresearch.storage import atomic, read_json


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_persona_swarm.SwarmTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lib, self.run, self.spec = self.fixture.lib, self.fixture.run, self.fixture.spec
        self.spec["max_attempts"] = 1
        second = copy.deepcopy(self.spec["tasks"][0])
        second.update(id="T2", data_namespace="fixture2")
        self.spec["tasks"].append(second)
        self.spec["tasks"][0]["requirement_coverage"] = self.fixture.coverage()
        swarm.create_plan(self.lib, self.run, self.spec)
        self.claim = swarm.claim(self.lib, self.run, "worker1", "T1")
        self.receipt = self.fixture.receipt(self.claim, "inconclusive")
        self.receipt.update(steps=[], criteria=[], artifacts=[], reason="Fixture write outcome unknown.")
        swarm.record(self.lib, self.run, self.receipt)
        self.inspection = dict(operation_id=self.claim["operation_id"], attempt=self.claim["attempt"], worker_stopped=True,
                               outcome="effects_inspected_safe_for_other_tasks",
                               note="Stopped fixture worker; inspected and reset isolated fixture state.")

    def settle(self, inspection=None):
        return swarm.settle(self.lib, self.run, "T1",
                            self.inspection if inspection is None else inspection)

    def test_exhausted_write_can_release_other_task_without_retry_or_pass(self):
        before = read_json(self.run / "swarm-state.json")["payload"]["tasks"][0]
        self.assertFalse(swarm.claim(self.lib, self.run, "worker2", "T2")["claimed"])
        result = self.settle()
        self.assertTrue(result["changed"])
        after = read_json(self.run / "swarm-state.json")["payload"]["tasks"][0]
        for key in ("status", "attempts", "history", "receipt", "operation_id", "lease"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(result["status"], "inconclusive")
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertEqual(report["tasks"][0]["requirement_results"][0]["status"], "incomplete")
        self.assertFalse(report["tasks"][0]["resource_quarantined"])
        self.assertFalse(report["tasks"][0]["retry_allowed"])
        self.assertFalse(report["product_ready"])
        self.assertEqual(report["tasks"][0]["settlement"]["basis"],
                         "host_attestation_not_independent_verification")
        self.assertTrue(swarm.claim(self.lib, self.run, "worker2", "T2")["claimed"])
        with self.assertRaises(EngineError) as ctx:
            swarm.retry(self.lib, self.run, "T1", reconciliation=dict(
                operation_id=self.claim["operation_id"], attempt=self.claim["attempt"], outcome="not_executed",
                worker_stopped=True, note="Stopped and inspected."))
        self.assertEqual(ctx.exception.issue["code"], "task_settled")

    def test_exact_repeat_is_idempotent_conflicting_repeat_preserves_first(self):
        self.settle()
        raw = (self.run / "swarm-state.json").read_bytes()
        self.assertFalse(self.settle()["changed"])
        self.assertEqual(raw, (self.run / "swarm-state.json").read_bytes())
        with self.assertRaises(EngineError):
            self.settle(dict(self.inspection, note="Different inspection claim."))
        self.assertEqual(raw, (self.run / "swarm-state.json").read_bytes())

    def test_invalid_inspection_never_releases_resource(self):
        invalid = [None, {}, dict(self.inspection, worker_stopped=False),
                   dict(self.inspection, worker_stopped=1),
                   dict(self.inspection, operation_id="wrong"),
                   dict(self.inspection, attempt=True), dict(self.inspection, attempt=2),
                   dict(self.inspection, outcome="effects_inspected_safe_to_retry"),
                   dict(self.inspection, outcome=[]),
                   dict(self.inspection, note=""), dict(self.inspection, extra=True),
                   dict(self.inspection, note="Contact private@example.com")]
        raw = (self.run / "swarm-state.json").read_bytes()
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(EngineError):
                swarm.settle(self.lib, self.run, "T1", value)
            self.assertEqual(raw, (self.run / "swarm-state.json").read_bytes())
        self.assertFalse(swarm.claim(self.lib, self.run, "worker2", "T2")["claimed"])

    def test_current_binding_and_build_are_still_required(self):
        self.lib.stale = True
        with self.assertRaises(EngineError):
            self.settle()
        self.lib.stale = False
        self.fixture.build.write_text("changed build")
        with self.assertRaises(EngineError):
            self.settle()

    def test_active_worker_and_readonly_task_cannot_be_settled(self):
        with self.assertRaises(EngineError):
            swarm.settle(self.lib, self.run, "T2", self.inspection)
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["tasks"][0]["task"]["side_effects"] = "read_only"
        swarm._save(self.run, state)
        with self.assertRaises(EngineError):
            self.settle()

    def test_prior_receipt_integrity_remains_required(self):
        state = read_json(self.run / "swarm-state.json")["payload"]
        corrupted = self.fixture.receipt(self.claim, "inconclusive")
        state["tasks"][0]["receipt"] = corrupted
        swarm._save(self.run, state)
        artifact = self.run / corrupted["artifacts"][0]["path"]
        atomic(artifact, b"tampered execution log")
        with self.assertRaises(EngineError):
            self.settle()
        self.assertNotIn("settlement", read_json(self.run / "swarm-state.json")["payload"]["tasks"][0])

    def test_late_receipt_cannot_turn_settlement_into_success(self):
        self.settle()
        with self.assertRaises(EngineError) as ctx:
            swarm.record(self.lib, self.run, self.fixture.receipt(self.claim))
        self.assertEqual(ctx.exception.issue["code"], "lease_mismatch")
        self.assertEqual(swarm.report(self.lib, self.run)["counts"]["passed"], 0)

    def test_concurrent_duplicate_settlements_commit_once(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.settle(), range(4)))
        self.assertEqual(sum(row["changed"] for row in results), 1)

    def test_expired_lease_needs_inspection_and_not_executed_is_supported(self):
        # Reset only this synthetic fixture to the previously recorded running state.
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["tasks"][0]["status"] = "running"
        state["tasks"][0].pop("receipt")
        swarm._save(self.run, state)
        with self.assertRaises(EngineError):
            self.settle()
        with patch.object(swarm.time, "time", return_value=self.claim["lease"]["expires_at"] + 1):
            result = self.settle(dict(self.inspection, outcome="not_executed"))
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(swarm.claim(self.lib, self.run, "worker2", "T2")["claimed"])

    def test_settlement_does_not_lift_another_uncertain_write(self):
        state = read_json(self.run / "swarm-state.json")["payload"]
        other = copy.deepcopy(state["tasks"][0])
        other["task"].update(id="T3", data_namespace="fixture3")
        other["operation_id"] = "uxop-other"
        state["tasks"].append(other)
        swarm._save(self.run, state)
        self.settle()
        self.assertFalse(swarm.claim(self.lib, self.run, "worker2", "T2")["claimed"])
        self.assertTrue(swarm.report(self.lib, self.run)["tasks"][0]["resource_quarantined"])

    def test_budget_is_preserved_even_if_settling_before_exhaustion(self):
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["max_attempts"] = 3
        swarm._save(self.run, state)
        self.settle()
        with self.assertRaises(EngineError) as ctx:
            swarm.retry(self.lib, self.run, "T1")
        self.assertEqual(ctx.exception.issue["code"], "task_settled")
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["max_attempts"], 3)
        self.assertEqual(report["tasks"][0]["attempts"], 1)

    def test_legacy_lease_identifier_is_bound_without_minting_new_operation(self):
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["tasks"][0].pop("operation_id")
        swarm._save(self.run, state)
        self.settle(dict(self.inspection, operation_id=self.claim["lease"]["lease_token"]))
        self.assertNotIn("operation_id", read_json(self.run / "swarm-state.json")["payload"]["tasks"][0])

    def test_malformed_persisted_settlement_fails_closed(self):
        self.settle()
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["tasks"][0]["settlement"]["inspection"]["worker_stopped"] = False
        swarm._save(self.run, state)
        with self.assertRaises(EngineError):
            swarm.claim(self.lib, self.run, "worker2", "T2")
        with self.assertRaises(EngineError):
            swarm.report(self.lib, self.run)

    def test_real_process_write_inspection_and_cli_recovery(self):
        root = self.fixture.root
        library = root / "real-library"
        doc = profile_input(root)
        with Library(library) as lib:
            lib.import_profiles(doc)
        spec = copy.deepcopy(self.spec)
        spec["product_id"] = "sample"
        for task in spec["tasks"]:
            task.update(persona_id="PER-cautious", requirement_ids=["local-results"])
            task.pop("requirement_coverage", None)
        run = root / "real-run"
        with Library(library) as lib:
            swarm.create_plan(lib, run, spec)
            claim = swarm.claim(lib, run, "real-worker", "T1")
        fixture = root / "owned-fixture.txt"
        worker = subprocess.run([sys.executable, "-c",
                                 "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('one write'); sys.exit(23)",
                                 str(fixture)], capture_output=True, timeout=10)
        self.assertEqual(worker.returncode, 23)
        # The process has actually terminated; the fixture actually contains its effect.
        self.assertEqual(fixture.read_text(), "one write")
        # No browser task was exercised, so this is not an executed QA pass.
        receipt = dict(schema_version="ux-persona-swarm-receipt.v1", task_id="T1",
                       worker_id=claim["lease"]["worker_id"], lease_token=claim["lease"]["lease_token"],
                       build_sha256=claim["build"]["sha256"], persona_revision=claim["binding"]["revision"],
                       profile_sha256=claim["binding"]["profile_sha256"], outcome="inconclusive",
                       steps=[], criteria=[], artifacts=[], reason="Fixture worker exited before QA result.")
        with Library(library) as lib:
            swarm.record(lib, run, receipt)
            self.assertFalse(swarm.claim(lib, run, "next-worker", "T2")["claimed"])
        inspection = root / "inspection.json"
        atomic(inspection, json.dumps(dict(operation_id=claim["operation_id"], attempt=claim["attempt"], worker_stopped=True,
               outcome="effects_inspected_safe_for_other_tasks",
               note="Process exited with code 23; inspected exactly one isolated fixture write.")).encode())
        command = [sys.executable, str(_paths.SKILL / "scripts/ux_personas.py"), "settle",
                   "--library", str(library), "--run", str(run), "--task", "T1", "--inspection", str(inspection)]
        started = time.perf_counter()
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        elapsed = time.perf_counter() - started
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["retry_allowed"])
        with Library(library) as lib:
            self.assertTrue(swarm.claim(lib, run, "next-worker", "T2")["claimed"])
            report = swarm.report(lib, run)
        self.assertEqual(fixture.read_text(), "one write")
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertEqual(report["tasks"][0]["attempts"], 1)
        self.assertFalse(report["product_ready"])
        print(json.dumps(dict(check="actual_process_terminal_recovery", worker_exit=worker.returncode,
                              cli_seconds=round(elapsed, 4), original_writes=1,
                              before_other_claim=False, after_other_claim=True,
                              task_passes=0, synthetic_fixture_only=True)))

    def test_new_runs_require_v3_and_invalid_settlement_downgrade_is_rejected(self):
        self.assertEqual(read_json(self.run / "swarm-state.json")["schema_version"], "ux-persona-swarm-state.v3")
        self.settle()
        envelope = read_json(self.run / "swarm-state.json")
        self.assertEqual(envelope["schema_version"], "ux-persona-swarm-state.v3")
        envelope["schema_version"] = "ux-persona-swarm-state.v1"
        atomic(self.run / "swarm-state.json", json.dumps(envelope).encode())
        with self.assertRaises(EngineError):
            swarm.claim(self.lib, self.run, "worker2", "T2")

    def test_prior_attempt_inspection_cannot_settle_later_attempt(self):
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["max_attempts"] = 2
        swarm._save(self.run, state)
        swarm.retry(self.lib, self.run, "T1", reconciliation=dict(
            operation_id=self.claim["operation_id"], attempt=self.claim["attempt"], outcome="not_executed",
            worker_stopped=True, note="First attempt inspected before retry."))
        second = swarm.claim(self.lib, self.run, "second-worker", "T1")
        receipt = self.fixture.receipt(second, "inconclusive")
        receipt.update(steps=[], criteria=[], artifacts=[], reason="Second attempt unknown.")
        swarm.record(self.lib, self.run, receipt)
        with self.assertRaises(EngineError) as ctx:
            self.settle()
        self.assertEqual(ctx.exception.issue["code"], "settlement_inspection_required")
        self.assertTrue(swarm.report(self.lib, self.run)["tasks"][0]["resource_quarantined"])
        self.settle(dict(self.inspection, attempt=second["attempt"],
                         note="Second worker stopped and its fixture state freshly inspected."))


if __name__ == "__main__":
    unittest.main()
