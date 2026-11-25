"""Report-only superseded history; no research gate bypass or real data."""
import copy
import unittest
from pathlib import Path

import _paths
from test_persona_library import profile_input
import test_persona_swarm
from uxpersonas.library import Library
from uxpersonas import swarm
from uxresearch.canonical import EngineError
from uxresearch.storage import atomic


class ReportHistoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_persona_swarm.SwarmTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.doc = profile_input(self.root)
        self.doc["review_days"] = 1
        self.now = 1000.0
        self.lib = Library(self.root / "library", clock=lambda: self.now)
        self.lib.__enter__()
        self.addCleanup(self.lib.__exit__, None, None, None)
        self.lib.import_profiles(self.doc)
        self.spec = self.fixture.spec
        self.spec["product_id"] = "sample"
        task = self.spec["tasks"][0]
        task.update(persona_id="PER-cautious", requirement_ids=["local-results"])
        coverage = self.fixture.coverage()
        coverage[0]["requirement_id"] = "local-results"
        task["requirement_coverage"] = coverage
        self.run = self.fixture.run

    def plan(self):
        swarm.create_plan(self.lib, self.run, self.spec)

    def complete(self, task="T1", outcome="passed"):
        claim = swarm.claim(self.lib, self.run, "worker-" + task, task)
        receipt = self.fixture.receipt(claim, outcome)
        swarm.record(self.lib, self.run, receipt)
        return receipt

    def revise(self):
        self.now = 2000.0
        updated = copy.deepcopy(self.doc)
        updated["personas"][0]["behaviors"] = ["Read the saved status carefully"]
        self.lib.import_profiles(updated)

    def test_superseded_pass_is_historical_not_current_coverage(self):
        self.plan()
        self.complete()
        self.revise()
        result = swarm.report(self.lib, self.run)
        row = result["tasks"][0]
        self.assertEqual(result["counts"]["passed"], 0)
        self.assertEqual(result["counts"]["blocked"], 1)
        self.assertEqual(result["historical_counts"]["passed"], 1)
        self.assertEqual(row["recorded_status"], "passed")
        self.assertEqual(row["blocker"]["code"], "stale_persona_revision")
        self.assertFalse(row["current_binding_valid"])
        self.assertIsNone(row["result"])
        self.assertIsNone(row["requirement_coverage"])
        self.assertEqual(row["requirement_results"][0]["status"], "unassessed")
        self.assertEqual(row["historical_requirement_results"][0]["status"], "passed")
        self.assertTrue(row["historical_result"]["criteria"])
        self.assertFalse(result["coverage_summary"]["all_declared_requirements_passed"])
        self.assertNotIn("profile", row)
        self.assertFalse(result["product_ready"])

    def test_unaffected_task_stays_current(self):
        other = copy.deepcopy(self.doc)
        other["personas"][0]["persona_id"] = "PER-other"
        self.lib.import_profiles(other)
        task = copy.deepcopy(self.spec["tasks"][0])
        task.update(id="T2", persona_id="PER-other", data_namespace="fixture2", resource_id="browser2")
        self.spec["tasks"].append(task)
        self.plan()
        self.complete("T1")
        self.complete("T2")
        self.revise()
        result = swarm.report(self.lib, self.run)
        self.assertEqual(result["counts"]["passed"], 1)
        self.assertEqual(result["counts"]["blocked"], 1)
        self.assertTrue(result["tasks"][1]["current_binding_valid"])
        self.assertEqual(result["tasks"][1]["requirement_results"][0]["status"], "passed")

    def assert_uncertain_history(self, outcome):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "uncertain-worker", "T1")
        if outcome == "inconclusive":
            receipt = self.fixture.receipt(claim, "inconclusive")
            receipt.update(reason="Synthetic fixture write outcome unknown.", steps=[], criteria=[], artifacts=[])
            swarm.record(self.lib, self.run, receipt)
        self.revise()
        before = (self.run / "swarm-state.json").read_bytes()
        result = swarm.report(self.lib, self.run)
        row = result["tasks"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["recorded_status"], outcome)
        self.assertEqual(result["historical_counts"][outcome], 1)
        self.assertEqual(result["counts"][outcome], 0)
        self.assertEqual(row["attempts"], 1)
        self.assertEqual(row["operation_id"], claim["operation_id"])
        self.assertIn("uncertain prior effects", row["blocker"]["next_step"])
        self.assertIn("does not authorize retry", row["blocker"]["next_step"])
        self.assertEqual(before, (self.run / "swarm-state.json").read_bytes())
        with self.assertRaises(EngineError):
            swarm.retry(self.lib, self.run, "T1")
        with self.assertRaises(EngineError):
            swarm.claim(self.lib, self.run, "new-worker")

    def test_running_write_history_does_not_authorize_new_execution(self):
        self.assert_uncertain_history("running")

    def test_inconclusive_write_history_keeps_attempt_and_effect_warning(self):
        self.assert_uncertain_history("inconclusive")

    def test_execution_gates_stay_closed(self):
        self.plan()
        receipt = self.complete(outcome="failed")
        self.revise()
        for action in (
            lambda: swarm.claim(self.lib, self.run, "new-worker"),
            lambda: swarm.record(self.lib, self.run, receipt),
            lambda: swarm.retry(self.lib, self.run, "T1"),
        ):
            with self.subTest(action=action), self.assertRaises(EngineError) as caught:
                action()
            self.assertEqual(caught.exception.issue["code"], "stale_persona_revision")

    def test_expired_original_revision_still_blocks(self):
        self.plan()
        self.complete()
        self.revise()
        self.now = 87900.0  # Old review deadline 87400; current 88400.
        self.lib.get("sample", "PER-cautious")
        with self.assertRaises(EngineError) as caught:
            swarm.report(self.lib, self.run)
        self.assertEqual(caught.exception.issue["code"], "persona_review_due")

    def test_retired_original_payload_is_not_reexposed(self):
        self.plan()
        self.complete()
        self.lib.retire("sample", "PER-cautious", "Synthetic source withdrawn")
        self.revise()
        self.lib.get("sample", "PER-cautious")
        with self.assertRaises(EngineError) as caught:
            swarm.report(self.lib, self.run)
        self.assertEqual(caught.exception.issue["code"], "persona_retired")

    def test_retired_current_revision_still_blocks(self):
        self.plan()
        self.complete()
        self.revise()
        self.lib.retire("sample", "PER-cautious", "Synthetic source withdrawn")
        with self.assertRaises(EngineError) as caught:
            swarm.report(self.lib, self.run)
        self.assertEqual(caught.exception.issue["code"], "persona_retired")

    def test_tampered_evidence_still_blocks_history(self):
        self.plan()
        receipt = self.complete()
        self.revise()
        atomic(self.run / receipt["artifacts"][0]["path"], b"changed")
        with self.assertRaises(EngineError):
            swarm.report(self.lib, self.run)

    def test_tampered_state_still_blocks_history(self):
        self.plan()
        self.complete()
        self.revise()
        atomic(self.run / "swarm-state.json", b'{"schema_version":"wrong"}')
        with self.assertRaises(EngineError):
            swarm.report(self.lib, self.run)

    def test_changed_prd_still_blocks_history(self):
        self.plan()
        self.complete()
        self.revise()
        Path(self.doc["context"]["prd_path"]).write_text("Changed PRD")
        with self.assertRaises(EngineError) as caught:
            swarm.report(self.lib, self.run)
        self.assertEqual(caught.exception.issue["code"], "stale_prd")

    def test_changed_build_still_blocks_history(self):
        self.plan()
        self.complete()
        self.revise()
        self.fixture.build.write_text("changed build")
        with self.assertRaises(EngineError) as caught:
            swarm.report(self.lib, self.run)
        self.assertEqual(caught.exception.issue["code"], "stale_build")

    def test_tampered_original_profile_still_blocks_history(self):
        self.plan()
        self.complete()
        self.revise()
        state = self.lib._state()
        state["entries"]["sample/PER-cautious"][0]["profile"]["label"] = "Tampered"
        self.lib._save(state)
        with self.assertRaises(EngineError) as caught:
            swarm.report(self.lib, self.run)
        self.assertEqual(caught.exception.issue["code"], "persona_integrity")
