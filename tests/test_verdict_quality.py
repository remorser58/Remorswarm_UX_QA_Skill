"""Verdict-state semantics, projection bounds, and per-persona task design regressions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import _paths
from uxpersonas.agent_run import Execution, Tool
from uxpersonas.scale_entry import _persona_journey_goal
from uxpersonas.scale_run import Evidence, ScaleExecution
from uxpersonas.scale_browser_host import ScaleBrowserHost
from uxpersonas.model_router import _clean_decision


class VerdictQualityTests(unittest.TestCase):
    def test_browser_observation_tolerates_storage_access_denial(self):
        driver = Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa/drivers/web/scale_browser_cdp.mjs"
        source = driver.read_text(encoding="utf-8")
        self.assertIn("let storageKeys=[],storageAccess='denied';try{storageKeys=Object.keys(localStorage);storageAccess='available';}catch{}", source)
        self.assertIn("storage_access:storageAccess", source)
        self.assertNotIn("storage_keys:Object.keys(localStorage)", source)

    def test_model_observation_projection_deduplicates_fixture_catalog_and_cumulative_uploads(self):
        catalog = [f"boundary-extra-{i:03d}.json" for i in range(531)]
        observations = []
        for i in range(16):
            observations.append({
                "id": f"obs-{i + 1}", "action": "observe", "text": "A bounded synthetic observation.",
                "facts": {
                    "available_fixtures": catalog,
                    "fixture_uploads": [f"fixture-{j}.zip" for j in range(i + 1)],
                    "fixture_validation": [{"fixture": f"fixture-{j}.zip", "archive_valid": True}
                                           for j in range(i + 1)],
                    "viewport": {"width": 756, "height": 413},
                },
                "checks": [], "captures": [{"id": f"png-{i}", "kind": "screenshot", "sha256": "a" * 64,
                                               "path": f"private-{i}.png"}],
                "artifacts": [{"id": f"png-{i}", "kind": "screenshot", "sha256": "a" * 64,
                               "path": f"private-{i}.png"}],
            })
        execution = ScaleExecution.__new__(ScaleExecution)
        execution.plan = {"tools": [], "limits": {"turns": 24}}
        task = {"id": "S-test", "goal": "test bounded request", "requirement_ids": []}
        state = {"observations": observations, "turn": 10}
        record = {"profile": {}, "provenance": {"mode": "synthetic", "research": {"claims": []}},
                  "context": {"requirements": []}}
        payload = execution.payload({"job": {"task": task}}, state, record, "model")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        projected = payload["observations"]
        projected_catalog = payload["fixture_catalog"]
        self.assertLess(len(encoded), 262144)
        self.assertEqual(projected_catalog, catalog)
        self.assertEqual(sum(len(row["facts"]["fixture_uploads_delta"]) for row in projected), 16)
        self.assertEqual([row["facts"]["fixture_uploads_delta"] for row in projected[:3]],
                         [["fixture-0.zip"], ["fixture-1.zip"], ["fixture-2.zip"]])
        self.assertEqual(sum(len(row["facts"]["fixture_validation_delta"]) for row in projected), 16)
        self.assertNotIn("available_fixtures", projected[-1]["facts"])
        self.assertNotIn("fixture_uploads", projected[-1]["facts"])
        self.assertNotIn("path", projected[-1]["captures"][0])

    def test_structural_dom_selectors_are_typed_metadata_not_free_user_text(self):
        tool = Tool("upload", "Select an owned fixture.", {
            "selector": "string", "file": "string"}, "owned_fixture_write")
        valid = {"selector": "body>div:nth-of-type(2)>section:nth-of-type(1)>input:nth-of-type(1)",
                 "file": "@group:owned-loose-512-valid"}
        self.assertEqual(tool.validate(valid), valid)
        with self.assertRaises(Exception):
            tool.validate({"selector": "#account-123456", "file": "owned-sample-current.zip"})
        with self.assertRaises(Exception):
            tool.validate({"selector": "body>input:nth-of-type(1)", "file": "../outside.zip"})

    def test_privacy_scrubber_preserves_typed_fixture_group_keys(self):
        selector = "body>div:nth-of-type(1)>input:nth-of-type(1)"
        group = "@group:owned-loose-total-over"
        raw = {"kind": "tool", "tool": "upload", "decision": "Upload the approved group.",
               "arguments": {"selector": selector, "file": group}}
        cleaned = _clean_decision(raw)
        self.assertEqual(cleaned["arguments"]["file"], group)
        self.assertEqual(cleaned["arguments"]["selector"], selector)
        tool = Tool("upload", "Select an owned fixture.",
                    {"selector": "string", "file": "string"}, "owned_fixture_write")
        self.assertEqual(tool.validate(cleaned["arguments"]), cleaned["arguments"])

    def test_only_conditional_recovery_can_be_not_applicable(self):
        task = {"success_criteria": ["Show imported result"],
                "recovery_criteria": ["Recover from a real failure"]}
        judgment = {"reason": "No failure occurred.", "criteria": [
            {"kind": "success", "index": 0, "status": "passed",
             "observation": "Imported result is visible.", "observation_ids": ["obs-1"]},
            {"kind": "recovery", "index": 0, "status": "not_applicable",
             "observation": "No triggering failure occurred in this run.", "observation_ids": []}]}
        observation = {"id": "obs-1", "artifacts": [
            {"id": "log-1", "kind": "execution_log"},
            {"id": "png-1", "kind": "screenshot"}]}
        result = Execution.criteria(None, {"claim": {"task": task}}, judgment, [observation])
        self.assertEqual([x["status"] for x in result], ["passed", "not_applicable"])

    def test_success_criterion_cannot_be_not_applicable(self):
        task = {"success_criteria": ["Show imported result"], "recovery_criteria": []}
        judgment = {"reason": "Not tested.", "criteria": [
            {"kind": "success", "index": 0, "status": "not_applicable",
             "observation": "The fixture was not available.", "observation_ids": []}]}
        with self.assertRaises(Exception):
            Execution.criteria(None, {"claim": {"task": task}}, judgment, [])

    def test_persona_requirements_expand_from_optional_product_catalog(self):
        catalog = {
            "R-SEARCH": {
                "screen": "search list",
                "selector": "input[type=search]",
                "text": ["Filter items"],
                "value": "search narrows rows to exact match",
                "precondition": "load owned-search-ready.zip",
                "action": "type synthetic query in search input",
                "timeout_seconds": 30,
                "scope": "desktop",
            }
        }
        fixtures = {"R-SEARCH": ("owned-search-ready.zip",)}
        goal = _persona_journey_goal("Verify owned product search.", ["R-SEARCH"],
                                     criteria_catalog=catalog, fixture_requirements=fixtures)
        self.assertIn("owned-search-ready.zip", goal)
        self.assertIn("type synthetic query in search input", goal)
        self.assertIn("not_applicable", goal)
        self.assertIn("not_run", goal)

    def test_browser_fixture_audit_detects_incomplete_and_complete_html_documents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            host = ScaleBrowserHost.__new__(ScaleBrowserHost)
            host.fixtures = root
            with zipfile.ZipFile(root / "incomplete.zip", "w") as archive:
                archive.writestr("followers.html", "<!doctype html><div>followers</div>")
            with zipfile.ZipFile(root / "complete.zip", "w") as archive:
                archive.writestr("followers.html", "<!doctype html><html><body>followers</body></html>")
            incomplete = host._validate_fixture_upload("incomplete.zip")
            complete = host._validate_fixture_upload("complete.zip")
        self.assertFalse(incomplete["complete_html_documents"])
        self.assertTrue(complete["complete_html_documents"])

    def test_native_browser_pass_closes_model_not_run(self):
        worker = {"claim": {"task": {"id": "task", "success_criteria": ["show result"],
            "recovery_criteria": []}, "binding": {"revision": 1, "profile_sha256": "a" * 64}},
            "queue_claim": {"owner": "worker", "lease_token": "b" * 64}}
        observation = {"id": "obs-1", "action": "observe", "text": "deterministic result", "checks": [
            {"kind": "success", "index": 0, "status": "passed"}],
            "artifacts": [{"id": "png-1", "kind": "screenshot"}]}
        judgment = {"reason": "No model judgment for this criterion.", "criteria": [
            {"kind": "success", "index": 0, "status": "not_run",
             "observation": "Not observed by model.", "observation_ids": []}]}
        with patch("uxpersonas.scale_run.swarm._receipt", side_effect=lambda root, job, value: value):
            receipt = Evidence(".").receipt(worker, {"observations": [observation]},
                {"build": {"sha256": "c" * 64}}, judgment=judgment)
        self.assertEqual(receipt["criteria"][0]["status"], "passed")
        self.assertEqual(receipt["criteria"][0]["evidence_ids"], ["png-1"])

    def test_optional_criteria_guard_hook_receives_receipt_criteria(self):
        worker = {"claim": {"task": {"id": "task", "requirement_ids": ["R-1"],
            "success_criteria": ["show result"], "recovery_criteria": []},
            "binding": {"revision": 1, "profile_sha256": "a" * 64}},
            "queue_claim": {"owner": "worker", "lease_token": "b" * 64}}
        observation = {"id": "obs-1", "action": "observe", "text": "obs",
            "checks": [], "artifacts": [{"id": "png-1", "kind": "screenshot"}]}
        seen = []

        def guard(task, criteria, observations):
            seen.append((task["id"], len(observations)))
            return criteria

        with patch("uxpersonas.scale_run.swarm._receipt", side_effect=lambda root, job, value: value):
            Evidence(".", criteria_guard=guard).receipt(worker, {"observations": [observation]},
                {"build": {"sha256": "c" * 64}}, judgment=None)
        self.assertEqual(seen, [("task", 1)])

    def test_native_not_run_reason_is_preserved_in_receipt(self):
        worker = {"claim": {"task": {"id": "task", "success_criteria": ["retention"],
            "recovery_criteria": []}, "binding": {"revision": 1, "profile_sha256": "a" * 64}},
            "queue_claim": {"owner": "worker", "lease_token": "b" * 64}}
        observation = {"id": "obs-1", "action": "observe", "text": "History not opened.",
            "checks": [{"kind": "success", "index": 0, "status": "not_run",
                        "reason": "Eleven distinct snapshots were not imported."}],
            "artifacts": [{"id": "png-1", "kind": "screenshot"}]}
        with patch("uxpersonas.scale_run.swarm._receipt", side_effect=lambda root, job, value: value):
            receipt = Evidence(".").receipt(worker, {"observations": [observation]},
                {"build": {"sha256": "c" * 64}}, judgment=None)
        self.assertEqual(receipt["criteria"][0]["status"], "not_run")
        self.assertEqual(receipt["criteria"][0]["observation"], "Eleven distinct snapshots were not imported.")
        self.assertEqual(receipt["criteria"][0]["evidence_ids"], [])

    def test_native_not_run_reason_is_admitted_but_reason_cannot_mask_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence_root = root / "evidence" / "task-test" / "1"
            evidence_root.mkdir(parents=True)
            execution = Execution.__new__(Execution)
            execution.root = root
            worker = {"context_id": "ctx-test", "observations": [], "claim": {
                "task": {"id": "task-test", "success_criteria": ["Open history"], "recovery_criteria": []},
                "binding": {"revision": 1, "profile_sha256": "a" * 64},
                "evidence_path": str(evidence_root), "attempt": 1}}
            valid = {"text": "History was not opened.", "facts": {}, "captures": [],
                "checks": [{"kind": "success", "index": 0, "status": "not_run",
                            "reason": "History screen was not reached; click action unavailable."}]}
            observed = execution.observation(worker, "inspect history", valid, 1)
            self.assertEqual(observed["checks"][0]["reason"], valid["checks"][0]["reason"])
            invalid = {**valid, "checks": [{"kind": "success", "index": 0, "status": "passed",
                                             "reason": "This must not hide missing evidence."}]}
            with self.assertRaises(Exception):
                execution.observation(worker, "inspect history", invalid, 2)


if __name__ == "__main__":
    unittest.main()
