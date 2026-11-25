"""Temporal observations are bounded evidence, not automatic WCAG failures."""
import copy
import json
import unittest
from pathlib import Path

import _paths  # noqa: F401
from ergoqa import analyze, checks
from ergoqa.devices import get_device
from ergoqa.snapshot import validate_scenario


class TemporalTests(unittest.TestCase):
    def test_observation_end_and_capped_probe_are_explicit_coverage_limits(self):
        health, notes = analyze.run_health({
            "run_id": "R", "status": "completed", "temporal_candidates_dropped": 2, "temporal_sampling_truncated": True,
            "timing_windows": [{"id": "notice", "open_interval_ms": 500}],
            "probe_replays": [{"id": "detail", "walks": [{"direction": "Tab", "ended": "time_budget"}]}],
        }, [], None)
        self.assertEqual(health, "degraded")
        self.assertTrue(any("이후 소멸 여부는 미검사" in note for note in notes))
        self.assertTrue(any("time_budget" in note for note in notes))
        self.assertTrue(any("2개 후보" in note for note in notes))
        self.assertTrue(any("후보 관찰이 불완전" in note for note in notes))

    def observe(self, **updates):
        measured = {"id": "notice", "selector": "#notice", "kind": "transient_text",
                    "intervals_ms": [700], "text": "Saved request reference 2468.", **updates}
        return [o for o in checks.check_run_timing(
            {"run_id": "R", "steps": [], "timing_windows": [measured]},
            {"profile_id": "P", "attributes": {}}, get_device("desktop-1920"),
            {"S": {"elements": []}}, {"timing_windows": []}) if o.check_id == "CG-02"]

    def test_open_interval_never_implies_disappearance(self):
        self.assertEqual(self.observe(intervals_ms=[], open_interval_ms=700), [])

    def test_same_information_recovered_is_not_information_loss(self):
        row = self.observe(recovery={"status": "available", "basis": "same_visible_text", "snapshot_id": "S"})[0]
        self.assertTrue(row.passed)
        self.assertIsNone(row.severity)

    def test_recovered_text_does_not_prove_recovered_action(self):
        row = self.observe(has_action=True, recovery={"status": "available", "basis": "same_visible_text", "snapshot_id": "S"})[0]
        self.assertFalse(row.passed)
        self.assertEqual(row.measurement["wcag_verdict"], "not_determined")

    def test_unanchored_recovery_and_claimed_exception_do_not_pass(self):
        row = self.observe(recovery={"status": "available", "basis": "same_visible_text", "snapshot_id": "missing"},
                           exception={"kind": "essential", "basis": "Task specification"})[0]
        self.assertFalse(row.passed)
        self.assertEqual(row.extra["verdict"], "modeled_risk")
        self.assertIn("AAA", row.extra["wcag_level"])

    def test_scenario_validates_replay_authority_and_visible_targets(self):
        scenario = json.loads((Path(__file__).parent / "fixtures/ergo/sample_scenario.json").read_text())
        scenario["focus_walks"] = [{"id": "modal", "after_step": 1, "state": "modal", "selector": "#dialog", "fixture": True}]
        scenario["timing_windows"] = [{"id": "notice", "selector": "#notice", "measure": "visible_duration",
                                       "recovery": {"selector": "#receipt"}, "exception": {"kind": "extend", "basis": "Visible Extend button"}}]
        self.assertEqual(validate_scenario(scenario), [])
        for field, value in (("fixture", False), ("after_step", 9999), ("selector", 'input[value="secret"]'), ("state", "guessed")):
            invalid = copy.deepcopy(scenario)
            invalid["focus_walks"][0][field] = value
            self.assertTrue(validate_scenario(invalid), field)
