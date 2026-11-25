"""Actual OSS graph/checkpoint tests; decision and PNG fixtures are not live AI."""
import asyncio
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import _paths
from uxpersonas import agent_run, swarm
from uxpersonas.library import Library
from uxresearch.canonical import EngineError
from uxresearch.storage import read_json

FIXTURE = Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa/examples/agents/fixture.py"
spec = importlib.util.spec_from_file_location("agent_fixture", FIXTURE)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
READY = agent_run.doctor()["runtime_ready"]


class OptionalAgentTests(unittest.TestCase):
    def test_dependency_probe_is_explicit_and_default_import_is_stdlib(self):
        with patch.object(agent_run.metadata, "version", side_effect=agent_run.metadata.PackageNotFoundError):
            value = agent_run.doctor()
            self.assertFalse(value["runtime_ready"])
            self.assertFalse(value["actual_model_execution"])
            with self.assertRaises(EngineError) as error:
                agent_run._runtime()
            self.assertEqual(error.exception.issue["code"], "optional_runtime_unavailable")

    def test_required_optional_gate_cannot_silently_skip(self):
        if os.environ.get("REMORSEARCH_REQUIRE_AGENT_RUNTIME") == "1":
            self.assertTrue(READY, agent_run.doctor())

    def test_no_implicit_model_provider(self):
        with self.assertRaises(EngineError) as error:
            agent_run._host_info(None)
        self.assertEqual(error.exception.issue["code"], "host_unavailable")

    def test_tool_argument_types_and_effect_are_strict(self):
        for bad in ({}, {"value": 7}, {"value": "x", "script": "unexpected"}):
            with self.subTest(bad=bad), self.assertRaises(EngineError):
                fixture.TOOLS[1].validate(bad)
        with self.assertRaises(EngineError):
            agent_run.Tool("bad", "Bad scope", {}, "live_write").spec()

    def test_metadata_hashes_are_not_treated_as_personal_text(self):
        host = fixture.FixtureHost()
        host.info["adapter_sha256"] = "8" * 64
        self.assertEqual(agent_run._host_info(host)["adapter_sha256"], "8" * 64)
        with self.assertRaises(EngineError):
            agent_run._data({"text": "Contact test@example.com"})


@unittest.skipUnless(READY, "Optional pinned LangGraph environment is not installed")
class AgentExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = fixture.build(Path(self.temp.name).resolve() / "owned")
        self.host = fixture.FixtureHost()
        self.lib = Library(self.root / "library").__enter__()
        self.addCleanup(self.lib.__exit__, None, None, None)

    async def execute(self, **kw):
        return await agent_run.execute(self.lib, self.root / "run", self.host, fixture.TOOLS, reviewed=True, **kw)

    async def test_two_saved_personas_parallel_control_defect_and_blind_judgments(self):
        report = await self.execute()
        self.assertEqual(report["counts"]["passed"], 1, report)
        self.assertEqual(report["counts"]["failed"], 1, report)
        execution = report["agent_execution"]
        self.assertTrue(execution["parallel_observed"])
        self.assertFalse(execution["actual_model_execution"])
        self.assertEqual(execution["actual_model_calls"], 0)
        self.assertGreater(execution["authored_decision_calls"], 0)
        self.assertFalse(execution["two_persona_model_tool_execution"])
        self.assertFalse(execution["actual_model_parallel_observed"])
        self.assertEqual(execution["peak_calls_by_kind"]["model"], 2)
        self.assertEqual(len(execution["first_judgments"]), 2)
        self.assertEqual(len({w["context_id"] for w in execution["workers"]}), 2)
        self.assertEqual(len(self.lib.list("agent-fixture")["personas"]), 2)
        for payload in self.host.model_inputs:
            peer = "PER-RETURN" if payload["task"]["persona_id"] == "PER-CAUTIOUS" else "PER-CAUTIOUS"
            self.assertNotIn(peer, str(payload))
        self.assertEqual(len(list((self.root / "run/evidence").glob("*/*/agent-graph.sqlite"))), 2)
        review = execution["observation_review"]
        self.assertFalse(review["consensus_complete"])
        self.assertTrue(any(r["outcome_conflict"] for r in review["groups"]))
        self.assertTrue(any(r["duplicate_observations"] for r in review["groups"]))

    async def test_serial_host_is_reported_as_serial(self):
        self.host = fixture.FixtureHost(parallel=False)
        report = await self.execute()
        self.assertEqual(report["agent_execution"]["peak_host_calls"], 1)
        self.assertFalse(report["agent_execution"]["parallel_observed"])
        self.assertEqual(report["agent_execution"]["peak_calls_by_kind"]["model"], 1)

    async def test_rejected_callbacks_are_not_completed_parallel_models(self):
        # Protocol simulation, never a live-model validation claim.
        self.host.info["mode"] = "model_tools"
        original = self.host.call
        async def call(kind, request):
            if kind == "model":
                await asyncio.sleep(0.02)
                raise RuntimeError("Pre-send rejection")
            return await original(kind, request)
        self.host.call = call
        report = await self.execute()
        execution = report["agent_execution"]
        self.assertEqual(execution["peak_calls_by_kind"]["model"], 2)
        self.assertEqual(execution["actual_model_calls"], 0)
        self.assertEqual(execution["actual_review_calls"], 0)
        self.assertFalse(execution["actual_model_parallel_observed"])

    async def test_repeated_execution_reads_results_without_calls_or_attempts(self):
        first = await self.execute()
        calls = copy.deepcopy(self.host.calls)
        second = await self.execute()
        self.assertEqual(first, second)
        self.assertEqual(calls, self.host.calls)
        self.assertTrue(all(t["attempts"] == 1 for t in second["tasks"]))

    async def test_partial_failure_keeps_other_persona_result(self):
        original = self.host.call
        async def call(kind, request):
            if kind == "tool" and request["payload"]["task"]["persona_id"] == "PER-RETURN":
                raise RuntimeError("Injected tool failure")
            return await original(kind, request)
        self.host.call = call
        report = await self.execute()
        self.assertEqual(report["counts"]["passed"], 1)
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertTrue(next(t for t in report["tasks"] if t["task_id"] == "T-RETURN")["resource_quarantined"])

    async def test_timeout_does_not_repeat_uncertain_call(self):
        original = self.host.call
        async def call(kind, request):
            if kind == "tool":
                await asyncio.sleep(2)
            return await original(kind, request)
        self.host.call = call
        limits = agent_run.Limits(call_seconds=1)
        report = await self.execute(limits=limits)
        self.assertEqual(report["counts"]["inconclusive"], 2)
        count = len(self.host.calls)
        await self.execute(limits=limits)
        self.assertEqual(len(self.host.calls), count)

    async def test_interrupted_model_preserves_native_failed_checkpoint(self):
        original = self.host.call
        async def call(kind, request):
            if kind == "model" and any(c["status"] == "failed"
                    for o in request["payload"]["observations"] for c in o["checks"]):
                raise RuntimeError("Model interrupted after verified rejection")
            return await original(kind, request)
        self.host.call = call
        report = await self.execute()
        self.assertEqual(report["counts"]["passed"], 1)
        self.assertEqual(report["counts"]["inconclusive"], 1)
        state = read_json(self.root / "run/agent-runtime/state.json", private=True)["payload"]
        worker = next(w for w in state["workers"] if w["claim"]["task"]["id"] == "T-RETURN")
        self.assertNotIn("first_judgment_sha256", worker)
        criterion = next(c for c in worker["receipt"]["criteria"] if c["kind"] == "success")
        self.assertEqual(criterion["status"], "failed")
        self.assertTrue(criterion["evidence_ids"])
        self.assertEqual(worker["receipt"]["outcome"], "inconclusive")

    async def test_cancel_blocks_further_dispatch_and_late_admission(self):
        cancel = asyncio.Event()
        late_returned = asyncio.Event()
        original = self.host.call
        async def call(kind, request):
            if kind == "tool":
                cancel.set()
                try:
                    await asyncio.sleep(0.1)
                except asyncio.CancelledError:
                    pass  # Simulate a transport that cannot retract an in-flight reply.
                reply = await original(kind, request)
                late_returned.set()
                return reply
            return await original(kind, request)
        self.host.call = call
        report = await self.execute(cancel=cancel)
        await asyncio.wait_for(late_returned.wait(), 1)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertFalse(any(kind == "review" for kind, _, _ in self.host.calls))
        state = read_json(self.root / "run/agent-runtime/state.json", private=True)["payload"]
        self.assertTrue(all(c["status"] == "intent" for w in state["workers"]
                            for k, c in w["calls"].items() if k.startswith("tool-")))

    async def test_stale_transport_envelope_cannot_admit_results(self):
        original = self.host.call
        async def call(kind, request):
            result = await original(kind, request)
            if kind == "model":
                result["context_id"] = "old-context"
            return result
        self.host.call = call
        report = await self.execute()
        self.assertEqual(report["counts"]["inconclusive"], 2)
        self.assertEqual(report["agent_execution"]["tool_calls"], 0)

    async def test_png_tamper_blocks_receipt(self):
        original = self.host.call
        async def call(kind, request):
            reply = await original(kind, request)
            if kind == "tool":
                path = Path(request["payload"]["evidence_path"]) / reply["result"]["captures"][0]["path"]
                path.write_bytes(b"not a PNG")
            return reply
        self.host.call = call
        report = await self.execute()
        self.assertEqual(report["counts"]["inconclusive"], 2)

    async def test_stop_unconfirmed_cannot_pass(self):
        original = self.host.call
        async def call(kind, request):
            reply = await original(kind, request)
            if kind == "close":
                reply["result"] = {"stopped": False}
            return reply
        self.host.call = call
        report = await self.execute()
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertTrue(all(w["problem"] == "worker_stop_unconfirmed" for w in report["agent_execution"]["workers"]))

    async def test_earlier_native_failure_cannot_be_erased_by_review(self):
        original = self.host.call
        async def call(kind, request):
            reply = await original(kind, request)
            if kind == "review":
                reply["result"]["criteria"][0]["status"] = "passed"
            return reply
        self.host.call = call
        report = await self.execute()
        self.assertEqual(report["counts"]["passed"], 1)
        self.assertEqual(report["counts"]["inconclusive"], 1)

    async def test_committed_receipt_response_loss_readback_does_not_repeat(self):
        original = swarm.record
        def record(*args, **kw):
            original(*args, **kw)
            raise OSError("Response lost after commit")
        with patch.object(swarm, "record", side_effect=record):
            await self.execute()
        calls = len(self.host.calls)
        report = await self.execute()
        self.assertEqual(len(self.host.calls), calls)
        self.assertTrue(all(w["phase"] == "recorded" for w in report["agent_execution"]["workers"]))

    async def test_changed_build_is_not_reused(self):
        await self.execute()
        (self.root / "build.txt").write_text("Different build")
        calls = len(self.host.calls)
        with self.assertRaises(EngineError):
            await self.execute()
        self.assertEqual(len(self.host.calls), calls)

    async def test_config_change_does_not_reset_limits(self):
        await self.execute()
        with self.assertRaises(EngineError) as error:
            await self.execute(limits=agent_run.Limits(turns=13))
        self.assertEqual(error.exception.issue["code"], "execution_conflict")

    async def test_goal_entry_uses_saved_personas_and_reserves_one_run(self):
        from uxpersonas.agent_entry import prepare_goal
        build = swarm.report(self.lib, self.root / "run")["build"]
        args = dict(product_id="agent-fixture", target="owned-fixture", goal="Check draft recovery",
                    build=build, reviewed=True)
        run = self.root / "goal-run"
        report = prepare_goal(self.lib, run, **args)
        self.assertEqual(len(report["tasks"]), 2)
        self.assertEqual(prepare_goal(self.lib, run, **args), report)
        with self.assertRaises(EngineError) as error:
            prepare_goal(self.lib, self.root / "duplicate-run", **args)
        self.assertEqual(error.exception.issue["code"], "goal_reserved")

    async def test_private_content_is_rejected_before_result_journaling(self):
        original = self.host.call
        async def call(kind, request):
            reply = await original(kind, request)
            if kind == "tool":
                reply["result"]["text"] = "Contact test@example.com"
            return reply
        self.host.call = call
        await self.execute()
        raw = (self.root / "run/agent-runtime/state.json").read_text()
        self.assertNotIn("test@example.com", raw)

    async def test_cli_report_rejects_altered_execution_classification(self):
        await self.execute()
        path = self.root / "run/agent-runtime/report.json"
        doc = read_json(path, private=True)
        doc["agent_execution"]["actual_model_execution"] = True
        from uxresearch.storage import atomic
        from uxresearch.canonical import canonical
        atomic(path, canonical(doc))
        self.lib.__exit__(None, None, None)
        result = subprocess.run([sys.executable, str(FIXTURE.parents[2] / "scripts/ux_agents.py"),
            "report", "--run", str(self.root / "run"), "--library", str(self.root / "library")],
            timeout=15, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"execution_integrity", result.stderr)

    async def test_turn_limit_is_inconclusive(self):
        report = await self.execute(limits=agent_run.Limits(turns=1))
        self.assertEqual(report["counts"]["inconclusive"], 2)

    async def test_process_exit_and_restart_preserve_unknown_effects(self):
        # A different isolated root avoids inheriting this test's Library lock.
        child_root = Path(self.temp.name).resolve() / "crash"
        code = """import asyncio, importlib.util, os, sys
from pathlib import Path
s=importlib.util.spec_from_file_location('fixture',sys.argv[1]); f=importlib.util.module_from_spec(s); s.loader.exec_module(f)
root=f.build(Path(sys.argv[2]))
host=f.FixtureHost()
async def crash(kind, request):
    if kind=='tool' and request['payload']['name']=='enter':
        with (root/'owned-effect-count.txt').open('x') as effect:
            effect.write('1')
            effect.flush()
            os.fsync(effect.fileno())
        os._exit(73)
    return await host.respond(kind,request)
host.call=crash
async def run():
    with f.Library(root/'library') as lib:
        await f.execute(lib,root/'run',host,f.TOOLS,reviewed=True)
asyncio.run(run())
"""
        result = subprocess.run([sys.executable, "-c", code, str(FIXTURE), str(child_root)], timeout=30, capture_output=True)
        self.assertEqual(result.returncode, 73, result.stderr.decode())
        effect = child_root / "owned-effect-count.txt"
        self.assertEqual(effect.read_text(), "1")
        original_stat = effect.stat()
        host = fixture.FixtureHost()
        with Library(child_root / "library") as lib:
            report = await agent_run.execute(lib, child_root / "run", host, fixture.TOOLS, reviewed=True)
        self.assertEqual(host.calls, [])
        self.assertEqual(report["counts"]["inconclusive"], 2)
        self.assertTrue(all(t["resource_quarantined"] for t in report["tasks"]))
        self.assertTrue(all(t["attempts"] == 1 for t in report["tasks"]))
        self.assertEqual(effect.read_text(), "1")
        self.assertEqual(effect.stat().st_mtime_ns, original_stat.st_mtime_ns)
