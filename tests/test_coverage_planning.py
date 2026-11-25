"""Coverage planning regressions use only owned offline fixtures."""
import asyncio
import copy
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import _paths
import test_scale_run as support
from uxpersonas.scale_entry import ScaleLimits, criterion_checklist, required_fixture_keys, _persona_journey_goal, scale_job_id
from uxpersonas import swarm
from uxpersonas.scale_report import completed_receipt_summary
from uxpersonas.scale_run import ScaleExecution, _criterion_progress, _validated_observation_facts
from uxpersonas.swarm_queue import Queue, checkpoint_data, CHECKPOINT_METADATA_BYTES, CHECKPOINT_OBSERVATION_BYTES
from uxresearch.canonical import EngineError, byte_digest, canonical

ENTRY = Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa/scripts/live_scale_browser.py"
SPEC = importlib.util.spec_from_file_location("coverage_live_entry", ENTRY)
live = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(live)


class ChecklistTests(unittest.TestCase):
    def test_custom_catalog_and_fixtures_preserve_requirement_indices_and_privacy(self):
        catalog = {
            "R-EXPORT": {
                "screen": "export tab", "selector": "button.export", "text": ["Export"],
                "value": "sample export is disabled", "precondition": "open sample",
                "action": "Inspect disabled export buttons.", "timeout_seconds": 20, "scope": "desktop",
            },
            "R-SEARCH": {
                "screen": "search list", "selector": "input[type=search]", "text": ["Search"],
                "value": "search narrows rows", "precondition": "import owned-search.zip",
                "action": "Type exact key in search input.", "timeout_seconds": 30, "scope": "desktop",
            },
        }
        fixtures = {"R-SEARCH": ("owned-search.zip",)}
        ids = ["R-EXPORT", "R-SEARCH", "R-UNKNOWN"]
        rows = criterion_checklist(ids, criteria_catalog=catalog, fixture_requirements=fixtures)
        self.assertEqual([r["requirement_id"] for r in rows], ids)
        self.assertEqual([r["index"] for r in rows], [0, 1, 2])
        self.assertEqual(rows[1]["required_fixtures"], ["owned-search.zip"])
        self.assertEqual(required_fixture_keys(ids, fixture_requirements=fixtures), ["owned-search.zip"])
        goal = _persona_journey_goal("Inspect the owned result.", ids,
                                     criteria_catalog=catalog, fixture_requirements=fixtures)
        self.assertEqual(swarm.clean(goal), goal)
        self.assertIn("Inspect disabled export buttons.", goal)
        self.assertIn("owned-search.zip", goal)
        self.assertLessEqual(len(goal), 8000)

    def test_only_reviewed_typed_hash_paths_bypass_prose_redaction(self):
        digest = "a" + "1234567890123456" + "b" * 47
        facts = {"storage_snapshot": {"available": True, "sha256": digest},
                 "import_attempt": {"fixture_sha256": digest,
                                    "storage_before": {"sha256": digest},
                                    "storage_after": {"sha256": digest}}}
        self.assertNotEqual(swarm.clean(facts), facts)
        self.assertEqual(_validated_observation_facts(facts), facts)
        for unsafe in ({**facts, "explanation": "customer@example.test"},
                       {**facts, "unreviewed": {"sha256": digest}},
                       {"storage_snapshot": {"sha256": "customer@example.test"}}):
            with self.assertRaises(EngineError) as raised:
                _validated_observation_facts(unsafe)
            self.assertEqual(raised.exception.issue["code"], "host_privacy")

    def test_fixture_group_keys_remain_typed_metadata_without_rejecting_task_privacy(self):
        ids = ["R-MULTI", "R-SIZE"]
        fixtures = {"R-MULTI": ("@group:owned-loose-512-valid",), "R-SIZE": ("owned-oversize.zip",)}
        goal = _persona_journey_goal("Use an owned fixture.", ids, fixture_requirements=fixtures)
        self.assertEqual(swarm.clean(goal), goal)
        self.assertIn("@group:owned-loose-512-valid", required_fixture_keys(ids, fixture_requirements=fixtures))
        self.assertIn("manifest group owned-loose-512-valid", goal)

    def test_native_failure_is_not_erased_by_later_pass(self):
        task = {"requirement_ids": ["R-SEARCH"]}
        observations = [{"id": "obs-1", "checks": [{"kind": "success", "index": 0, "status": "failed"}]},
                        {"id": "obs-2", "checks": [{"kind": "success", "index": 0, "status": "passed"}]}]
        row = _criterion_progress(task, observations, ["unrelated.zip"])[0]
        self.assertEqual(row["observed_status"], "failed")
        self.assertEqual(row["observation_ids"], ["obs-1"])
        self.assertEqual(_criterion_progress(task, [], [])[0]["observed_status"], "unobserved")

    def test_eighty_history_observations_fit_model_envelope_and_preserve_checks(self):
        observations = []
        for i in range(80):
            observations.append({"id": f"obs-{i+1}", "action": "Inspect owned result",
                "text": "Observed synthetic result " * 200,
                "facts": {"text": "Observed synthetic result " * 200,
                    "controls": [{"selector": f"#owned-control-{n}", "label": "Current view " * 10,
                                  "visible": True} for n in range(35)],
                    "fixture_uploads": [f"owned-retention-snapshot-{n:02d}.zip" for n in range(1, min(i+2, 12))],
                    "available_fixtures": [f"owned-retention-snapshot-{n:02d}.zip" for n in range(1, 12)],
                    "fixture_validation": [],
                    "list_rows": [{"key": f"synthetic-{n:02d}", "text": "Synthetic row " * 5} for n in range(40)],
                    "import_attempt": {"attempt_id": f"owned-{i}", "cancel_dispatched": False}},
                "checks": [{"kind": "success", "index": 0, "status": "not_run", "reason": "History not opened."}],
                "captures": [], "artifacts": []})
        original = copy.deepcopy(observations)
        execution = ScaleExecution.__new__(ScaleExecution)
        execution.plan = {"tools": [], "limits": {"turns": 80}}
        task = {"id": "S-test", "goal": "Inspect retention and boundary.",
                "requirement_ids": ["R-RETENTION", "R-BOUNDARY"], "turn_limit": 80}
        record = {"profile": {}, "provenance": {"mode": "synthetic"},
                  "context": {"requirements": []}}
        payload = execution.payload({"job": {"task": task}},
                                    {"observations": observations, "turn": 76}, record, "model")
        self.assertLess(len(json.dumps(payload, ensure_ascii=False).encode()), 262144)
        self.assertEqual(sum(len(o["checks"]) for o in payload["observations"]), 80)
        self.assertEqual(payload["effective_turn_limit"], 80)
        self.assertEqual(payload["remaining_model_turns"], 4)
        self.assertEqual([o["id"] for o in payload["observations"]],
                         [o["id"] for o in observations])
        self.assertNotIn("controls", payload["observations"][0]["facts"])
        self.assertEqual(payload["observations"][-1]["facts"]["controls"], observations[-1]["facts"]["controls"])
        self.assertEqual(payload["observations"][0]["facts"]["import_attempt"], observations[0]["facts"]["import_attempt"])
        self.assertTrue(payload["observations"][0]["text_excerpt"])
        self.assertEqual(observations, original)

    def test_completed_summary_excludes_valid_partial_previews_and_keeps_duplicates_visible(self):
        def row(job, persona, status, outcome, complete):
            receipt = {"outcome": outcome, "criteria": [
                {"kind": "success", "index": 0, "status": "not_run"}]}
            return {"job_id": job, "persona_id": persona, "status": status,
                    "current_valid": True, "current_ux_outcome": outcome,
                    "result": {"operational_completed": True, "receipt": receipt} if complete else None,
                    "receipt_preview": None if complete else receipt}
        report = {"tasks": [row("a", "P-one", "complete", "inconclusive", True),
                            row("b", "P-one", "complete", "inconclusive", True),
                            row("c", "P-two", "uncertain", "failed", False),
                            row("d", "P-three", "queued", "inconclusive", False)]}
        original = copy.deepcopy(report)
        summary = completed_receipt_summary(report)
        self.assertEqual(summary["completed_sessions"], 2)
        self.assertEqual(summary["distinct_completed_personas"], 1)
        self.assertEqual(summary["session_outcomes"]["failed"], 0)
        self.assertEqual(summary["session_outcomes"]["inconclusive"], 2)
        self.assertEqual(summary["criteria_all"]["not_run"], 2)
        self.assertEqual(summary["excluded_attempt_statuses"], {"uncertain": 1, "queued": 1})
        self.assertEqual(report, original)


class FixtureGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_preflight_requires_valid_manifest_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "fixture-manifest.json"
            manifest_path.write_text(json.dumps({"schema_version": "unexpected.v0", "files": [], "groups": {}}))
            with self.assertRaisesRegex(RuntimeError, "ux_fixture_manifest_invalid"):
                live.fixture_preflight(root, ["R-1"])
            manifest_path.write_text(json.dumps({"schema_version": "ux-synthetic-fixtures.v1", "files": [], "groups": {}}))
            checked = live.fixture_preflight(root, ["R-1"])
            self.assertEqual(checked["required_file_count"], 0)

    async def test_prior_job_identity_blocks_even_with_fresh_output_before_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "fixture-manifest.json").write_text(json.dumps({
                "schema_version": "ux-synthetic-fixtures.v1", "files": [], "groups": {}}))
            artifact = root / "owned-build.txt"
            artifact.write_bytes(b"owned-build")
            build = dict(id="coverage-build", artifact_path=str(artifact), sha256=byte_digest(artifact.read_bytes()))
            goal = "Inspect the reviewed owned flow."
            prior_id = scale_job_id("owned-product", "PER-one", 2, goal, build)
            self.assertNotEqual(prior_id, scale_job_id("owned-product", "PER-one", 2, goal + " Fresh cohort.", build))
            args = SimpleNamespace(run_root=root / "fresh-output", library=root / "library",
                                   product_id="owned-product", fixtures=root, turns=64,
                                   build_artifact=artifact, build_id=build["id"], goal=goal,
                                   forbidden_job_ids={prior_id})
            with patch.object(live, "Library") as library, patch.object(live, "_route") as route:
                context = library.return_value.__enter__.return_value
                context.list.return_value = {"personas": [{"persona_id": "PER-one", "revision": 2, "reusable": True}]}
                context.get.return_value = {"profile": {"requirement_ids": ["R-START"]}}
                with self.assertRaisesRegex(RuntimeError, "prior_job_identity_overlap:1"):
                    await live.run_stage(args, ["PER-one"], 2)
                route.assert_not_called()
                self.assertFalse(args.run_root.exists())


class BoundedLongJourneyTests(unittest.IsolatedAsyncioTestCase):
    setUp = support.ScaleRunTests.setUp
    run_scale = support.ScaleRunTests.run_scale

    async def test_extended_budget_finishes_long_owned_fixture_but_rejects_unbounded_plan(self):
        loop = asyncio.get_running_loop()
        self.addCleanup(setattr, loop, "slow_callback_duration", loop.slow_callback_duration)
        loop.slow_callback_duration = 2.0
        plan = json.loads(json.dumps(self.queue.plan))
        plan["limits"].update(turns=64, max_model_calls=130, task_seconds=180)
        self.queue = Queue.create(self.root / "long-scale", plan)
        original = self.host.result
        fixture_catalog = [f"owned-retention-fixture-{i:03d}.zip" for i in range(543)]
        controls = [{"selector": f"#owned-control-{i}", "label": "Inspect record " + str(i),
                     "visible": True, "enabled": True, "type": "button"} for i in range(36)]
        payload_sizes = []
        async def result(kind, request):
            if kind in {"model", "review"}:
                payload_sizes.append(len(canonical(request["payload"])))
                if kind == "model" and len(request["payload"]["observations"]) < 59:
                    self.host.states.setdefault(request["context_id"], dict(stage="empty", note="", saved="", retained=None))
                    return {"kind": "tool", "tool": "inspect", "arguments": {},
                            "decision": "Inspect the next owned prerequisite."}
            response = await original(kind, request)
            if kind == "tool":
                response["text"] += " Inspect saved synthetic record before advancing." * 20
                response["facts"].update(available_fixtures=fixture_catalog, controls=controls,
                    file_inputs=[{"selector": "#owned-file", "multiple": True}],
                    fixture_uploads=[f"owned-retention-snapshot-{i:02d}.zip" for i in range(1, 12)],
                    fixture_validation=[], list_rows=[{"key": f"synthetic_row_{i}", "text": "Synthetic row"} for i in range(12)])
                response["facts"]["storage_snapshot"] = {
                    "available": True, "sha256": "a" + "1234567890123456" + "b" * 47}
                self.assertLess(len(canonical({k: response[k] for k in ("text", "facts", "checks")})), 65536)
            return response
        self.host.result = result
        report = await self.run_scale()
        self.assertEqual(report["counts"]["complete"], 2,
                         {"counts": report["counts"], "calls": report["authored_model_calls"],
                          "problems": [(row["job_id"], row.get("problem")) for row in report["tasks"]]})
        self.assertEqual(report["authored_model_calls"], 130)
        self.assertEqual(report["completed_receipt_summary"]["assessed_completed_sessions"], 2)
        self.assertLessEqual(max(payload_sizes), 262144)
        self.assertEqual(len(payload_sizes), 130)
        with sqlite3.connect(self.queue.path.as_uri() + "?mode=ro", uri=True) as db:
            checkpoints = db.execute("SELECT checkpoint FROM jobs ORDER BY ordinal").fetchall()
        for (raw,) in checkpoints:
            self.assertGreater(len(raw.encode()), 1024 * 1024)
            state = json.loads(raw)
            self.assertEqual(state["turn"], 64)
            self.assertEqual(len(state["observations"]), 63)
            for observation in state["observations"]:
                self.assertEqual(observation["facts"]["available_fixtures"], fixture_catalog)
                self.assertEqual(observation["facts"]["controls"], controls)
        for row in report["tasks"]:
            evidence_root = Path(row["result"]["evidence_root"])
            for artifact in row["result"]["receipt"]["artifacts"]:
                self.assertEqual(byte_digest((evidence_root / artifact["path"]).read_bytes()), artifact["sha256"])
        invalid = copy.deepcopy(plan)
        invalid["limits"]["turns"] = 81
        with self.assertRaises(Exception):
            Queue.create(self.root / "too-long-scale", invalid)
        self.assertFalse((self.root / "too-long-scale").exists())
        for ceiling in (1, 12, 64, 65, 80):
            self.assertEqual(ScaleLimits(turns=ceiling).validate()["turns"], ceiling)
        with self.assertRaises(Exception):
            ScaleLimits(turns=81).validate()
        with self.assertRaises(Exception):
            ScaleLimits(turns=0).validate()
        self.assertEqual(live.live_limits(32).max_model_calls, 32 * 17)
        self.assertEqual(live.live_limits(32, 64).max_model_calls, 32 * 65)
        self.assertEqual(live.live_limits(32, 80).max_model_calls, 32 * 81)
        self.assertEqual(live.live_limits(32, 64).budget_microusd, 0)

    async def test_checkpoint_budget_does_not_expand_other_envelopes_or_observation_count(self):
        plan = copy.deepcopy(self.queue.plan)
        plan["limits"].update(turns=64, max_model_calls=130)
        queue = Queue.create(self.root / "bounded-checkpoint-scale", plan)
        claim = queue.claim("checkpoint-regression")
        valid = {"turn": 64, "observations": [{"text": "Owned observation", "facts": {}, "checks": []}] * 64}
        queue.checkpoint(claim, valid)
        stored = queue.assert_claim(claim)["checkpoint"]
        for invalid in (
                {"observations": valid["observations"] + [valid["observations"][0]]},
                {"observations": [{"text": "owned", "facts": {"large": "x" * 65536}, "checks": []}]},
                {"observations": ["x" * CHECKPOINT_OBSERVATION_BYTES]},
                {"metadata": "x" * CHECKPOINT_METADATA_BYTES},
                {"observations": [], "metadata": float("nan")}):
            with self.assertRaises(EngineError):
                queue.checkpoint(claim, invalid)
            self.assertEqual(queue.assert_claim(claim)["checkpoint"], stored)
        with self.assertRaises(EngineError):
            queue.begin(claim, "model", "large-request", {"large": "x" * 262144})
        with self.assertRaises(EngineError):
            queue.complete(claim, {"large": "x" * CHECKPOINT_METADATA_BYTES})
        with self.assertRaises(EngineError):
            checkpoint_data(valid, 63)


if __name__ == "__main__":
    unittest.main()
