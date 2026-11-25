"""Receipt authoring diagnostics preserve privacy, evidence and lease gates."""
import copy
import json
import unittest

import test_persona_swarm as fixtures
from uxpersonas import swarm
from uxresearch.canonical import EngineError


class ReceiptDiagnosticsTests(unittest.TestCase):
    setUp = fixtures.SwarmTests.setUp
    plan = fixtures.SwarmTests.plan
    receipt = fixtures.SwarmTests.receipt

    def prepare(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "worker1")
        return self.receipt(claim)

    def reject(self, receipt, location=None):
        state = (self.run / "swarm-state.json").read_bytes()
        original = copy.deepcopy(receipt)
        with self.assertRaises(EngineError) as caught:
            swarm.record(self.lib, self.run, receipt)
        self.assertEqual((self.run / "swarm-state.json").read_bytes(), state)
        self.assertEqual(receipt, original)
        issue = caught.exception.issue
        if location:
            self.assertEqual(issue["location"], location)
        self.assertNotIn(receipt["lease_token"], json.dumps(issue))
        return issue

    def test_contact_in_path_diagnostic_and_honest_correction(self):
        receipt = self.prepare()
        receipt["steps"][0]["observation"] = "Captured at /Users/person@example.com/evidence.png"
        issue = self.reject(receipt, "receipt.steps[0].observation")
        self.assertEqual(issue["reason"], "Receipt text contains personal identifiers.")
        self.assertNotIn("person@example.com", json.dumps(issue))
        receipt["steps"][0]["observation"] = "Input restored"
        self.assertEqual(swarm.record(self.lib, self.run, receipt)["status"], "passed")

    def test_timestamp_reference_is_still_rejected_without_echo(self):
        receipt = self.prepare()
        stamp = "shot-1794357835372"
        receipt["artifacts"][1]["id"] = stamp
        for item in receipt["steps"] + receipt["criteria"]:
            item["evidence_ids"] = ["log", stamp]
        issue = self.reject(receipt, "receipt.steps[0].evidence_ids[1]")
        self.assertNotIn(stamp, json.dumps(issue))
        self.assertIn("matching artifact references", issue["next_step"])

    def test_reason_and_criterion_pii_remain_rejected(self):
        receipt = self.prepare()
        for group in ("reason", "criterion"):
            candidate = copy.deepcopy(receipt)
            if group == "reason":
                candidate["reason"] = "Contact person@example.com"
                expected = "receipt.reason"
            else:
                candidate["criteria"][1]["observation"] = "Contact person@example.com"
                expected = "receipt.criteria[1].observation"
            with self.subTest(group=group):
                issue = self.reject(candidate, expected)
                self.assertNotIn("person@example.com", json.dumps(issue))

    def test_empty_fields_have_safe_specific_locations(self):
        receipt = self.prepare()
        for group, field, expected in (
                (None, "reason", "receipt.reason"),
                ("steps", "action", "receipt.steps[0].action"),
                ("steps", "observation", "receipt.steps[0].observation"),
                ("criteria", "observation", "receipt.criteria[0].observation")):
            candidate = copy.deepcopy(receipt)
            (candidate if group is None else candidate[group][0])[field] = ""
            with self.subTest(group=group, field=field):
                issue = self.reject(candidate, expected)
                self.assertEqual(issue["reason"], "A bounded nonempty string is required.")
                self.assertIn("observed blank page", issue["next_step"])

    def test_not_run_blank_observation_is_not_fabricated(self):
        receipt = self.prepare()
        receipt["outcome"] = "inconclusive"
        receipt["criteria"][0].update(status="not_run", observation="", evidence_ids=[])
        self.reject(receipt, "receipt.criteria[0].observation")

    def test_invalid_evidence_list_remains_rejected(self):
        receipt = self.prepare()
        receipt["steps"][0]["evidence_ids"] = []
        self.reject(receipt, "receipt.steps[0].evidence_ids")

    def test_unknown_keys_never_appear_in_diagnostics(self):
        receipt = self.prepare()
        for target in ("receipt", "steps", "criteria"):
            candidate = copy.deepcopy(receipt)
            row = candidate if target == "receipt" else candidate[target][0]
            row["person@example.com/private-secret"] = "hidden-value"
            with self.subTest(target=target):
                issue = self.reject(candidate)
                self.assertNotIn("person@example.com", json.dumps(issue))
                self.assertNotIn("private-secret", json.dumps(issue))
                self.assertNotIn("hidden-value", json.dumps(issue))

    def test_long_observation_and_missing_evidence_still_rejected(self):
        receipt = self.prepare()
        candidate = copy.deepcopy(receipt)
        candidate["steps"][0]["observation"] = "x" * 8001
        self.reject(candidate, "receipt.steps[0].observation")
        receipt["steps"][0]["evidence_ids"] = ["absent"]
        issue = self.reject(receipt)
        self.assertEqual(issue["reason"], "Observation refers to missing evidence.")


if __name__ == "__main__":
    unittest.main()
