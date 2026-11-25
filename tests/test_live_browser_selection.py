"""CLI-to-queue selection regressions; every live boundary is replaced or forbidden."""
from contextlib import closing
import copy
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import _paths
from test_scale_run import fixture
from uxpersonas import product_controls as controls
from uxpersonas.library import Library, PROFILE_FIELDS
from uxpersonas.swarm_queue import Queue
from uxresearch.canonical import EngineError, byte_digest, canonical
from uxresearch.storage import atomic, read_json

ENTRY = _paths.SKILL / "scripts/live_scale_browser.py"
spec = importlib.util.spec_from_file_location("live_selection_test", ENTRY)
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveSelectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = fixture.build(Path(temp.name).resolve() / "owned")
        self.baseline = self.root / "ui-baseline.json"
        atomic(self.baseline, b'{"layout":"owned fixture"}\n')
        with Library(self.root / "library") as library:
            first = library.get("agent-fixture", "PER-CAUTIOUS")
            refs = [dict(persona_id=pid, revision=library.get("agent-fixture", pid)["revision"])
                    for pid in ("PER-CAUTIOUS", "PER-RETURN")]
        self.controls = dict(schema_version=controls.SCHEMA, product_id="agent-fixture",
            context=first["context"], personas=refs,
            models=[dict(key="local-router", label="Reviewed free route",
                         model=live._provider_spec().model, reasoning_effort="none")],
            tasks=[dict(id="TASK-RECOVER", requirement_ids=["R-STATE"], goal="Keep the owned draft",
                        actions=["Inspect the draft", "Correct the owned input"],
                        success=["The rejected draft remains"], recovery=["Save corrected input"])],
            style=dict(platform="web", baseline=dict(path=str(self.baseline),
                sha256=byte_digest(self.baseline.read_bytes())), preserve=["Fixed owned layout"],
                components=[dict(id="draft", path="src/Draft.module.css", properties=["padding"],
                                 requirement_ids=["R-STATE"])]),
            limits=dict(max_personas=2, max_parallel=2, max_turns=16, max_model_calls=40,
                        budget_microusd=0, max_iterations=1, allowed_models=["local-router"]))
        # Intentionally reverse library order: the launcher must use the choice,
        # not its historical first-N library slicing.
        self.choice = dict(proposal_sha256=controls.propose(self.controls)["proposal_sha256"],
            confirmed=True, persona_ids=["PER-RETURN", "PER-CAUTIOUS"],
            assignments={"PER-RETURN":"local-router", "PER-CAUTIOUS":"local-router"},
            parallel=1, turns=16, max_model_calls=30, budget_microusd=0, max_iterations=1)
        self.receipt = self.root / "selection.json"
        self.save_receipt()
        fixtures = self.root / "fixtures"
        fixtures.mkdir()
        atomic(fixtures / "fixture-manifest.json", canonical(dict(
            schema_version="ux-synthetic-fixtures.v1",
            files=[dict(name="unused-owned-fixture.txt", bytes=0, sha256=byte_digest(b""))], groups={})))
        self.argv = ["--library", str(self.root / "library"), "--product-id", "agent-fixture",
            "--model", live._provider_spec().model, "--provider-name", "local-gateway",
            "--url", "http://127.0.0.1:4173/", "--target", "owned-fixture",
            "--goal", "Check the reviewed owned draft", "--build-id", "fixture-build",
            "--build-artifact", str(self.root / "build.txt"), "--fixtures", str(fixtures),
            "--run-root", str(self.root / "new-live-run"), "--stages", "2",
            "--selection", str(self.receipt), "--approval-actor", "fixture-reviewer",
            "--consent-reference", "Explicit authored test consent; not permission for real execution"]
        self.args = live.parse_args(self.argv)

    def save_receipt(self):
        value = controls.select(self.controls, self.choice)
        atomic(self.receipt, canonical(value))
        return value

    async def assert_blocked_before_live(self, args=None):
        with patch.object(live, "_route") as route, patch.object(live, "ScaleBrowserHost") as host, \
                patch.object(live, "execute_scale", new_callable=AsyncMock) as execute:
            with self.assertRaises((EngineError, RuntimeError, ValueError, TypeError)):
                await live.main(args or self.args)
            route.assert_not_called()
            host.assert_not_called()
            execute.assert_not_awaited()
        self.assertFalse(self.args.run_root.exists())
        self.assertFalse((self.root / "library/scale-goals.json").exists())

    async def test_missing_receipt_cannot_use_default_personas(self):
        self.args.selection = None
        await self.assert_blocked_before_live()

    async def test_empty_library_is_not_initialized(self):
        empty = self.root / "empty-library"
        empty.mkdir()
        self.args.library = empty
        await self.assert_blocked_before_live()
        self.assertEqual(list(empty.iterdir()), [])

    async def test_missing_file_cancel_unconfirmed_and_tampered_receipts_stop_before_live(self):
        valid = read_json(self.receipt)
        invalid = [
            {"status":"cancelled", "model_execution_started":False},
            {**valid, "choice":{**valid["choice"], "confirmed":False}},
            {**valid, "selection_sha256":"0" * 64},
        ]
        for value in invalid:
            with self.subTest(value=value):
                atomic(self.receipt, canonical(value))
                await self.assert_blocked_before_live()
        self.args.selection = [self.root / "absent.json"]
        await self.assert_blocked_before_live()

    async def test_duplicate_json_keys_use_existing_strict_reader(self):
        raw = self.receipt.read_text()
        atomic(self.receipt, ('{"choice":null,' + raw[1:]).encode())
        await self.assert_blocked_before_live()

    async def test_stale_prd_or_style_stops_before_live(self):
        for path in (self.root / "PRD.md", self.baseline):
            original = path.read_bytes()
            atomic(path, original + b"changed\n")
            await self.assert_blocked_before_live()
            atomic(path, original)

    async def test_new_persona_revision_stops_before_live(self):
        with Library(self.root / "library") as library:
            saved = library.get("agent-fixture", "PER-CAUTIOUS")
            row = {k:copy.deepcopy(v) for k,v in saved["profile"].items() if k in PROFILE_FIELDS}
            row.update(persona_id="PER-CAUTIOUS", claim_ids=[], label="Revised owned fixture")
            library.import_profiles(dict(schema_version="ux-persona-library-input.v1",
                product_id="agent-fixture", mode="prd_hypothesis",
                context=self.controls["context"], personas=[row]))
        await self.assert_blocked_before_live()

    async def test_model_or_reasoning_change_stops_before_catalog(self):
        for field, value in (("model", "unreviewed-model"), ("reasoning_effort", "high")):
            original = self.controls["models"][0][field]
            self.controls["models"][0][field] = value
            self.choice["proposal_sha256"] = controls.propose(self.controls)["proposal_sha256"]
            self.save_receipt()
            await self.assert_blocked_before_live()
            self.controls["models"][0][field] = original

    async def test_selection_does_not_supply_execution_consent(self):
        for field in ("approval_actor", "consent_reference"):
            previous = getattr(self.args, field)
            setattr(self.args, field, "")
            await self.assert_blocked_before_live()
            setattr(self.args, field, previous)

    async def test_later_stage_is_validated_before_any_earlier_live_activity(self):
        self.args.stages = [2, 3]
        missing = self.root / "missing-next-stage.json"
        self.args.selection = [self.receipt, missing]
        await self.assert_blocked_before_live()

    async def test_duplicate_or_wrong_sized_stage_cohort_is_not_reselected(self):
        self.args.stages = [1]
        await self.assert_blocked_before_live()
        self.args.stages = [2, 4]
        self.args.selection = [self.receipt, self.receipt]
        await self.assert_blocked_before_live()

    async def test_direct_stage_without_selection_remains_blocked(self):
        with patch.object(live, "_route") as route, patch.object(live, "ScaleBrowserHost") as host:
            with self.assertRaisesRegex(RuntimeError, "reviewed_selection_required"):
                await live.run_stage(self.args, self.choice["persona_ids"], 2)
            route.assert_not_called()
            host.assert_not_called()
        self.assertFalse(self.args.run_root.exists())

    async def test_changed_receipt_between_stages_is_not_silently_adopted(self):
        original = self.save_receipt()
        self.choice["max_model_calls"] = 29
        self.save_receipt()
        with patch.object(live, "_route") as route:
            with self.assertRaisesRegex(RuntimeError, "reviewed_selection_changed_before_stage"):
                await live.run_stage(self.args, self.choice["persona_ids"], 2,
                    selection=self.receipt, expected_selection_sha256=original["selection_sha256"])
            route.assert_not_called()

    def test_cli_requires_selection_and_separate_consent(self):
        for flag in ("--selection", "--approval-actor", "--consent-reference"):
            argv = list(self.argv)
            index = argv.index(flag)
            del argv[index:index+2]
            result = subprocess.run([sys.executable, str(ENTRY), *argv],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn(flag, result.stderr)
            self.assertFalse(self.args.run_root.exists())

    async def test_real_select_cli_receipt_reaches_exact_queue_without_live_dispatch(self):
        config_path, choice_path = self.root / "controls.json", self.root / "choice.json"
        atomic(config_path, canonical(self.controls))
        atomic(choice_path, canonical(self.choice))
        result = subprocess.run([sys.executable, str(_paths.SKILL / "scripts/ux_personas.py"),
            "select", "--input", str(config_path), "--choice", str(choice_path)],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        atomic(self.receipt, result.stdout.encode())
        selection = read_json(self.receipt)

        async def forbidden_call(*_):
            raise AssertionError("No real model or browser call is allowed in this test")

        provider_spec = live._provider_spec()
        provider = SimpleNamespace(mode="live", spec=provider_spec, adapter_sha256="a"*64,
                                   call=forbidden_call)
        host = SimpleNamespace(info=dict(name="offline-launcher-sentinel", mode="model_tools",
            model="owned browser", adapter_sha256="b"*64, isolated_contexts=True, parallel_safe=True),
            call=forbidden_call)
        # The queue and approval are real disposable local artifacts. Deliberately
        # stop at the execution boundary, not a fabricated successful live report.
        with patch.object(live, "_route", return_value=(object(), {"local-router":provider}, provider_spec, [])), \
                patch.object(live, "ScaleBrowserHost", return_value=host), \
                patch.object(live, "_execute_with_shutdown", new_callable=AsyncMock,
                             side_effect=RuntimeError("offline_stop_before_dispatch")) as execute:
            with self.assertRaisesRegex(RuntimeError, "offline_stop_before_dispatch"):
                await live.main(self.args)
            execute.assert_awaited_once()

        queue = Queue(self.args.run_root / "stage-2")
        self.assertEqual(queue.plan["product_selection"], selection)
        self.assertEqual([row["task"]["persona_id"] for row in queue.plan["jobs"]], self.choice["persona_ids"])
        self.assertEqual({row["task"]["persona_id"]:row["provider"] for row in queue.plan["jobs"]},
                         self.choice["assignments"])
        self.assertEqual(queue.plan["limits"]["parallel"], 1)
        self.assertEqual(queue.plan["limits"]["max_model_calls"], 30)
        self.assertIn("Inspect the draft", queue.plan["jobs"][0]["task"]["actions"])
        self.assertFalse(read_json(queue.root / "preview.json")["selection_ui_verified"])
        with closing(sqlite3.connect(queue.path)) as db:
            approval = db.execute("SELECT actor,consent_reference,ceiling FROM approvals").fetchone()
            operations = db.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        self.assertEqual(approval, (self.args.approval_actor, self.args.consent_reference, 0))
        self.assertEqual(operations, 0)


if __name__ == "__main__":
    unittest.main()
