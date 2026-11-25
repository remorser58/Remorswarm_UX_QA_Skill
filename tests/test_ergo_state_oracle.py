"""Generic visible-state contracts; these fixtures are not a product-defect benchmark."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from ergoqa import checks
from ergoqa.snapshot import SnapshotError, load_run_dir, validate_run, validate_scenario
from test_ergo_pipeline import make_run
from test_ergo_task_integrity import task_result


BASIS = {"kind": "product", "reference": "Generic fixture policy: one record per approved draft; cancellation does not save."}


def count_check(identifier, **assertion):
    return {"id": identifier, "selector": ".record", "container": "#history", "property": "count",
            "basis": BASIS, "severity": "P1", "consequence": "Visible record relation must hold.", **assertion}


def scenario(checks_list, steps=None):
    return {"schema_version": "ergo-scenario.v1", "scenario_id": "SC-generic-state",
            "surface": {"kind": "web", "url": "http://127.0.0.1/generic"},
            "task_goal_ko": "Generic visible request state", "device_ids": ["galaxy-s24"],
            "steps": steps if steps is not None else [{"action": "snapshot"}, {"action": "click", "target": "#approve"}],
            "success": {"task_checks": checks_list}}


class StateScenarioTests(unittest.TestCase):
    def test_visible_count_delta_and_selection_equality(self):
        authored = [count_check("before", expected=0, after_step=1),
                    count_check("approved", from_check="before", delta=1, after_step=2)]
        self.assertEqual(validate_scenario(scenario(authored)), [])
        selection = [{"id": "selected", "selector": "#option", "property": "checked", "expected": True,
                      "after_step": 1, "severity": "P2", "consequence": "Selection is retained.", "basis": BASIS},
                     {"id": "retained", "selector": "#option", "property": "checked", "from_check": "selected",
                      "severity": "P2", "consequence": "Selection is retained.", "basis": BASIS}]
        self.assertEqual(validate_scenario(scenario(selection)), [])

    def test_invalid_relations_and_count_sources_are_rejected(self):
        base = [count_check("before", expected=0, after_step=1),
                count_check("after", from_check="before", delta=1)]
        for update in ({"from_check": "unknown"}, {"from_check": "after"}, {"after_step": 1},
                       {"property": "value"}, {"delta": True}, {"delta": 0.5}, {"delta": 2**53},
                       {"expected": 1}, {"container": "input[value=private]"}, {"container": None}):
            candidate = copy.deepcopy(base)
            candidate[1].update(update)
            self.assertTrue(validate_scenario(scenario(candidate)), update)
        for value in (-1, True, "1", 2**53):
            self.assertTrue(validate_scenario(scenario([count_check("bad", expected=value)])))

    def test_fresh_replay_is_explicit_owned_and_bounded(self):
        follow = {"fixture": True, "changes": ["back", "cancel", "reentry", "edit_resubmit"],
                  "insertions": [{"after_step": 1, "steps": [{"action": "click", "target": "#cancel"}]}]}
        check = count_check("replay", expected=1, follow_up=follow)
        self.assertEqual(validate_scenario(scenario([check])), [])
        for update in ({"fixture": False}, {"changes": ["unknown"]}, {"changes": ["back", "back"]},
                       {"insertions": []}, {"insertions": [{"after_step": 3, "steps": [{"action": "snapshot"}]}]},
                       {"insertions": [{"after_step": 1, "steps": [{"action": "not-an-action"}]}]},
                       {"hidden_storage": "forbidden"}):
            candidate = copy.deepcopy(check)
            candidate["follow_up"].update(update)
            self.assertTrue(validate_scenario(scenario([candidate])), update)

    def test_structured_inputs_use_authored_rules_not_domain_guessing(self):
        steps = [{"action": "type", "target": "#entry", "text": text} for text in ("", "ab", "alternate-12", "!!")]
        cases = [
            {"step": 1, "kind": "blank", "expectation": "reject", "basis": BASIS},
            {"step": 2, "kind": "boundary", "expectation": "accept", "boundary": "Exactly the documented lower bound.", "basis": BASIS},
            {"step": 3, "kind": "documented_valid", "expectation": "accept", "basis": BASIS},
            {"step": 4, "kind": "invalid", "expectation": "reject", "basis": BASIS},
        ]
        authored = count_check("input-contract", expected=0, input_cases=cases)
        self.assertEqual(validate_scenario(scenario([authored], steps)), [])
        for index, update in ((0, {"step": 2}), (1, {"boundary": ""}), (2, {"expectation": "reject"}),
                              (3, {"expectation": "accept"}), (3, {"basis": None}),
                              (3, {"kind": "guessed-valid"}), (3, {"step": 99})):
            candidate = copy.deepcopy(authored)
            candidate["input_cases"][index].update(update)
            self.assertTrue(validate_scenario(scenario([candidate], steps)), update)
        replay = count_check("input-replay", expected=0, follow_up={"fixture": True, "changes": ["edit_resubmit"],
            "insertions": [{"after_step": 1, "steps": [{"action": "type", "target": "#entry", "text": ""}]}],
            "input_cases": [{"step": 2, "kind": "blank", "expectation": "reject", "basis": BASIS}]})
        self.assertEqual(validate_scenario(scenario([replay])), [])

    def test_missing_basis_is_allowed_as_a_question_not_an_implicit_rule(self):
        authored = count_check("question", expected=0)
        del authored["basis"]
        self.assertEqual(validate_scenario(scenario([authored])), [])
        for value in ("paper says so", {}, {"kind": "paper", "reference": "A publication"}, {"kind": "task", "reference": ""}):
            authored["basis"] = value
            self.assertTrue(validate_scenario(scenario([authored])))


class StateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run_dir = make_run(self.root)
        self.run = json.loads((self.run_dir / "run.json").read_text())
        self.run.update(success=False, success_basis="measured")
        self.source = task_result(id="before", property="count", selector=".record", container="#history",
                                  checkpoint=1, step_index=1, basis=BASIS, passed=True, result="pass")
        self.after = task_result(id="after", property="count", selector=".record", container="#history",
                                 checkpoint="final", step_index=1, basis=BASIS,
                                 relation={"kind": "delta", "source_check_id": "before", "delta": 1,
                                           "snapshot_id": "S-R-1-001", "step_index": 1})
        # Add a designated final capture at the same final action index.
        original = json.loads((self.run_dir / "S-R-1-001.json").read_text())
        final = {**original, "snapshot_id": "S-R-1-002", "notes": ["task_check_final"]}
        (self.run_dir / "S-R-1-002.json").write_text(json.dumps(final))
        self.after["snapshot_id"] = final["snapshot_id"]
        self.run.setdefault("snapshots", []).append({"snapshot_id": final["snapshot_id"], "step_index": 1,
                                                    "path": "S-R-1-002.json", "png": original["screenshot"]["path"]})
        self.run["success_detail"] = {"criteria": [self.source, self.after], "unevaluable": []}

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        (self.run_dir / "run.json").write_text(json.dumps(self.run))

    def test_count_relation_uses_capture_order_not_only_action_index(self):
        self.assertEqual(validate_run(self.run), [])
        self.save()
        loaded, snapshots = load_run_dir(self.run_dir)
        observations = checks.check_task_integrity(loaded, {"profile_id": "EP-01"}, {s["snapshot_id"]: s for s in snapshots})
        self.assertEqual([o.passed for o in observations], [True, False])
        self.assertEqual(observations[1].measurement["relation"]["delta"], 1)
        self.assertEqual(observations[1].measurement["basis"], BASIS)
        self.assertEqual(observations[1].extra["anchor_selectors"], ["#history"])

    def test_missing_or_mismatched_relation_capture_rejected(self):
        for update in ({"snapshot_id": "S-missing"}, {"source_check_id": "unknown"}, {"step_index": 0}):
            with self.subTest(update=update):
                self.after["relation"] = {"kind": "delta", "source_check_id": "before", "delta": 1,
                                          "snapshot_id": "S-R-1-001", "step_index": 1, **update}
                self.save()
                with self.assertRaisesRegex(SnapshotError, "task relation"):
                    load_run_dir(self.run_dir)

    def test_candidate_never_produces_defect_observation(self):
        candidate = task_result(basis=None, passed=None, result="unevaluable",
                                reason="expectation_basis_missing", comparison="fail")
        self.run["success_detail"]["criteria"] = [candidate]
        self.run["success"] = None
        self.assertEqual(validate_run(self.run), [])
        observed = checks.check_task_integrity(self.run, {"profile_id": "EP-01"}, {"S-R-1-001": {"snapshot_id": "S-R-1-001"}})
        self.assertEqual(observed, [])
        candidate.update(passed=False, result="fail", reason=None)
        self.assertTrue(validate_run(self.run))
        candidate.pop("comparison")
        self.assertEqual(checks.check_task_integrity(self.run, {"profile_id": "EP-01"}, {"S-R-1-001": {"snapshot_id": "S-R-1-001"}}), [])

    def add_replay(self):
        relative = "state-oracle/before"
        child_dir = self.run_dir / relative
        child_dir.parent.mkdir()
        shutil.copytree(self.run_dir, child_dir, ignore=shutil.ignore_patterns("state-oracle"))
        child = copy.deepcopy(self.run)
        child.update(run_id="R-fresh", success=False)
        child_result = copy.deepcopy(self.source)
        child_result.update(passed=False, result="fail", checkpoint="final", snapshot_id="S-R-1-002")
        child["success_detail"] = {"criteria": [child_result], "unevaluable": []}
        for p in child_dir.glob("S-*.json"):
            doc = json.loads(p.read_text())
            doc["run_id"] = child["run_id"]
            p.write_text(json.dumps(doc))
        (child_dir / "run.json").write_text(json.dumps(child))
        self.source.update(passed=False, result="fail", replay={
            "relation": "equal", "source_result": "pass", "changes": ["cancel", "reentry"], "run_id": "R-fresh",
            "run_path": f"{relative}/run.json", "check_id": "before", "snapshot_id": child_result["snapshot_id"],
            "step_index": 1, "result": "fail", "passed": False, "reason": None})
        self.run["success_detail"]["criteria"] = [self.source]
        self.save()
        return child_dir

    def test_fresh_replay_has_independent_linked_run_and_verified_capture(self):
        self.add_replay()
        self.assertEqual(validate_run(self.run), [])
        loaded, _ = load_run_dir(self.run_dir)
        self.assertIs(loaded["success_detail"]["criteria"][0]["replay"]["passed"], False)

    def test_fresh_replay_missing_capture_wrong_owner_and_unsafe_path_rejected(self):
        child_dir = self.add_replay()
        child_run = json.loads((child_dir / "run.json").read_text())
        child_run["profile_id"] = "wrong-owner"
        (child_dir / "run.json").write_text(json.dumps(child_run))
        with self.assertRaisesRegex(SnapshotError, "task fresh replay"):
            load_run_dir(self.run_dir)
        child_run["profile_id"] = self.run["profile_id"]
        (child_dir / "run.json").write_text(json.dumps(child_run))
        (child_dir / "S-R-1-001.json").unlink()
        with self.assertRaises(SnapshotError):
            load_run_dir(self.run_dir)
        self.source["replay"]["run_path"] = "../outside/run.json"
        self.assertTrue(validate_run(self.run))

    def test_replay_outcomes_cannot_claim_unmeasured_success(self):
        self.add_replay()
        self.source.update(result="pass", passed=True)
        self.run["success"] = True
        self.assertTrue(validate_run(self.run))
        self.source.update(result="unevaluable", passed=None, reason="replay_failed")
        self.run["success"] = None
        self.source["replay"].update(result="unevaluable", passed=None, reason="replay_failed",
                                     snapshot_id=None, step_index=None)
        self.assertEqual(validate_run(self.run), [])
        self.source["replay"].update(result="pass", passed=True)
        self.assertTrue(validate_run(self.run))


if __name__ == "__main__":
    unittest.main()
