"""Attempt-specific reconciliation; synthetic fault injection is not live QA."""
import copy
import json
import unittest
from concurrent.futures import ThreadPoolExecutor

import _paths
import test_persona_swarm
from uxpersonas import swarm
from uxresearch.canonical import EngineError
from uxresearch.storage import atomic, read_json


class RetryBindingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_persona_swarm.SwarmTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lib, self.run = self.fixture.lib, self.fixture.run
        self.fixture.spec["max_attempts"] = 3
        second = copy.deepcopy(self.fixture.spec["tasks"][0])
        second.update(id="T2", data_namespace="fixture2")
        self.fixture.spec["tasks"].append(second)
        self.fixture.plan()
        self.first = self.unknown("first")
        self.inspection = dict(operation_id=self.first["operation_id"], attempt=1,
                               outcome="not_executed", worker_stopped=True,
                               note="First synthetic attempt inspected; no product write executed.")

    def unknown(self, worker):
        claim = swarm.claim(self.lib, self.run, worker, "T1")
        receipt = self.fixture.receipt(claim, "inconclusive")
        receipt.update(steps=[], criteria=[], artifacts=[],
                       reason="Synthetic unknown result; no product write executed.")
        swarm.record(self.lib, self.run, receipt)
        return claim

    def retry(self, inspection=None):
        return swarm.retry(self.lib, self.run, "T1",
                           self.inspection if inspection is None else inspection)

    def next_unknown(self):
        self.retry()
        return self.unknown("second")

    def raw(self):
        return (self.run / "swarm-state.json").read_bytes()

    def legacy(self, version):
        envelope = read_json(self.run / "swarm-state.json")
        envelope["schema_version"] = version
        atomic(self.run / "swarm-state.json", json.dumps(envelope).encode())

    def legacy_pending(self):
        self.next_unknown()
        self.retry(dict(self.inspection, attempt=2, note="Second attempt inspected."))
        state = read_json(self.run / "swarm-state.json")["payload"]
        old = dict(self.inspection)
        old.pop("attempt")
        state["tasks"][0]["history"][-1]["reconciliation"] = old
        swarm._save(self.run, state)
        self.legacy("ux-persona-swarm-state.v1")
        return copy.deepcopy(state["tasks"][0])

    def test_old_inspection_does_not_release_second_attempt_or_resource(self):
        second = self.next_unknown()
        self.assertEqual(second["operation_id"], self.first["operation_id"])
        before = self.raw()
        with self.assertRaises(EngineError) as ctx:
            self.retry()
        self.assertEqual(ctx.exception.issue["code"], "reconciliation_required")
        self.assertEqual(self.raw(), before)
        self.assertFalse(swarm.claim(self.lib, self.run, "third", "T1")["claimed"])
        self.assertFalse(swarm.claim(self.lib, self.run, "other", "T2")["claimed"])
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["tasks"][0]["attempts"], 2)
        self.assertTrue(report["tasks"][0]["resource_quarantined"])
        self.assertEqual(report["counts"]["passed"], 0)

    def test_fresh_second_attempt_inspection_allows_one_bounded_retry(self):
        self.next_unknown()
        current = dict(self.inspection, attempt=2, outcome="effects_inspected_safe_to_retry",
                       note="Second worker stopped and second attempt state inspected.")
        result = self.retry(current)
        self.assertEqual(result["attempts"], 2)
        third = self.unknown("third")
        self.assertEqual(third["attempt"], 3)
        self.assertEqual(third["operation_id"], self.first["operation_id"])
        with self.assertRaises(EngineError):
            self.retry(dict(current, attempt=3))
        entry = read_json(self.run / "swarm-state.json")["payload"]["tasks"][0]
        self.assertEqual([h["reconciliation"]["attempt"] for h in entry["history"]], [1, 2])
        self.assertEqual([h["status"] for h in entry["history"]], ["inconclusive", "inconclusive"])
        self.assertEqual(entry["status"], "inconclusive")

    def test_missing_or_invalid_attempt_and_binding_preserve_state(self):
        missing = dict(self.inspection)
        missing.pop("attempt")
        invalid = [missing, dict(self.inspection, attempt=True),
                   dict(self.inspection, attempt=1.0), dict(self.inspection, attempt="1"),
                   dict(self.inspection, attempt=0), dict(self.inspection, attempt=2),
                   dict(self.inspection, operation_id="other"),
                   dict(self.inspection, outcome=[]), dict(self.inspection, worker_stopped=False),
                   dict(self.inspection, extra="ignored")]
        before = self.raw()
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(EngineError):
                self.retry(value)
            self.assertEqual(self.raw(), before)

    def test_private_note_still_rejected(self):
        before = self.raw()
        with self.assertRaises(EngineError):
            self.retry(dict(self.inspection, note="Contact private@example.com"))
        self.assertEqual(self.raw(), before)

    def test_new_state_rejectable_by_v1_and_v2_readers(self):
        self.assertEqual(read_json(self.run / "swarm-state.json")["schema_version"],
                         "ux-persona-swarm-state.v3")
        self.retry()
        self.assertEqual(read_json(self.run / "swarm-state.json")["schema_version"],
                         "ux-persona-swarm-state.v3")

    def test_legacy_v1_read_preserves_bytes_and_valid_retry_upgrades(self):
        self.legacy("ux-persona-swarm-state.v1")
        before = self.raw()
        self.assertEqual(swarm.report(self.lib, self.run)["counts"]["inconclusive"], 1)
        self.assertEqual(self.raw(), before)
        self.retry()
        self.assertEqual(read_json(self.run / "swarm-state.json")["schema_version"],
                         "ux-persona-swarm-state.v3")
        self.assertEqual(swarm.claim(self.lib, self.run, "second", "T1")["attempt"], 2)

    def test_legacy_invalid_inspection_cannot_upgrade_or_reset_task(self):
        self.legacy("ux-persona-swarm-state.v1")
        before = self.raw()
        missing = dict(self.inspection)
        missing.pop("attempt")
        with self.assertRaises(EngineError):
            self.retry(missing)
        self.assertEqual(self.raw(), before)

    def test_legacy_v2_settlement_remains_terminal(self):
        swarm.settle(self.lib, self.run, "T1", dict(self.inspection))
        self.legacy("ux-persona-swarm-state.v2")
        before = self.raw()
        self.assertFalse(swarm.report(self.lib, self.run)["tasks"][0]["retry_allowed"])
        with self.assertRaises(EngineError) as ctx:
            self.retry()
        self.assertEqual(ctx.exception.issue["code"], "task_settled")
        self.assertEqual(self.raw(), before)

    def test_unavailable_current_binding_still_blocks(self):
        before = self.raw()
        self.lib.stale = True
        with self.assertRaises(EngineError):
            self.retry()
        self.assertEqual(self.raw(), before)

    def test_legacy_operation_fallback_still_requires_attempt(self):
        state = read_json(self.run / "swarm-state.json")["payload"]
        entry = state["tasks"][0]
        entry.pop("operation_id")
        swarm._save(self.run, state)
        inspection = dict(self.inspection, operation_id=entry["lease"]["lease_token"])
        self.retry(inspection)
        self.assertEqual(swarm.claim(self.lib, self.run, "second", "T1")["attempt"], 2)

    def test_duplicate_concurrent_retry_cannot_double_advance(self):
        def request(_):
            try:
                return self.retry()["status"]
            except EngineError:
                return "rejected"
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(request, range(4)))
        self.assertEqual(results.count("pending"), 1)
        self.assertEqual(results.count("rejected"), 3)
        entry = read_json(self.run / "swarm-state.json")["payload"]["tasks"][0]
        self.assertEqual(entry["attempts"], 1)
        self.assertEqual(len(entry["history"]), 1)

    def test_legacy_pending_stale_inspection_blocks_task_and_shared_resource(self):
        self.legacy_pending()
        before = self.raw()
        self.assertFalse(swarm.claim(self.lib, self.run, "third", "T1")["claimed"])
        self.assertFalse(swarm.claim(self.lib, self.run, "other", "T2")["claimed"])
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["tasks"][0]["status"], "pending")
        self.assertEqual(report["tasks"][0]["retry_blocker"]["code"], "pending_retry_inspection_required")
        self.assertTrue(report["tasks"][1]["resource_quarantined"])
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertEqual(self.raw(), before)

    def test_legacy_pending_fresh_review_preserves_original_attempt_and_receipt(self):
        original = self.legacy_pending()
        current = dict(self.inspection, attempt=2, note="Latest worker stopped and latest fixture inspected.")
        result = self.retry(current)
        self.assertTrue(result["changed"])
        entry = read_json(self.run / "swarm-state.json")["payload"]["tasks"][0]
        self.assertEqual(entry["attempts"], original["attempts"])
        self.assertEqual(len(entry["history"]), len(original["history"]))
        for key, value in original["history"][-1].items():
            self.assertEqual(entry["history"][-1][key], value)
        self.assertEqual(entry["history"][-1]["reconciliation_review"], current)
        self.assertEqual(swarm.claim(self.lib, self.run, "third", "T1")["attempt"], 3)
        self.assertEqual(swarm.report(self.lib, self.run)["counts"]["passed"], 0)

    def test_legacy_pending_review_is_idempotent_and_conflict_preserving(self):
        self.legacy_pending()
        current = dict(self.inspection, attempt=2, note="Fresh inspection of second attempt.")
        self.retry(current)
        before = self.raw()
        self.assertFalse(self.retry(current)["changed"])
        with self.assertRaises(EngineError) as ctx:
            self.retry(dict(current, note="Conflicting inspection."))
        self.assertEqual(ctx.exception.issue["code"], "reconciliation_conflict")
        self.assertEqual(before, self.raw())

    def test_legacy_pending_reinspection_cannot_exceed_budget(self):
        self.legacy_pending()
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["max_attempts"] = 2
        swarm._save(self.run, state)
        before = self.raw()
        with self.assertRaises(EngineError):
            self.retry(dict(self.inspection, attempt=2))
        self.assertFalse(swarm.claim(self.lib, self.run, "third", "T1")["claimed"])
        self.assertEqual(before, self.raw())

    def test_pending_review_revalidated_before_dispatch(self):
        self.legacy_pending()
        self.retry(dict(self.inspection, attempt=2))
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["tasks"][0]["history"][-1]["reconciliation_review"]["worker_stopped"] = False
        swarm._save(self.run, state)
        before = self.raw()
        self.assertFalse(swarm.claim(self.lib, self.run, "third", "T1")["claimed"])
        with self.assertRaises(EngineError):
            self.retry(dict(self.inspection, attempt=2))
        self.assertEqual(before, self.raw())

    def test_legacy_pending_uses_original_lease_if_operation_id_absent(self):
        self.legacy_pending()
        state = read_json(self.run / "swarm-state.json")["payload"]
        entry = state["tasks"][0]
        entry.pop("operation_id")
        expected = entry["history"][-1]["lease"]["lease_token"]
        swarm._save(self.run, state)
        self.retry(dict(self.inspection, operation_id=expected, attempt=2))
        self.assertEqual(swarm.claim(self.lib, self.run, "third", "T1")["attempt"], 3)

    def test_independent_resource_can_continue_while_legacy_pending_is_blocked(self):
        self.legacy_pending()
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["tasks"][1]["task"]["resource_id"] = "independent"
        swarm._save(self.run, state)
        self.assertTrue(swarm.claim(self.lib, self.run, "other", "T2")["claimed"])
        self.assertFalse(swarm.claim(self.lib, self.run, "third", "T1")["claimed"])

    def test_claim_also_checks_budget_for_otherwise_valid_pending(self):
        self.retry()
        state = read_json(self.run / "swarm-state.json")["payload"]
        state["max_attempts"] = 1
        swarm._save(self.run, state)
        before = self.raw()
        self.assertFalse(swarm.claim(self.lib, self.run, "second", "T1")["claimed"])
        self.assertEqual(before, self.raw())


if __name__ == "__main__":
    unittest.main()
