"""Offline SQLite/model/tool integration; no browser, paid call or optional graph."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import _paths
from uxpersonas import scale_run, swarm
from uxpersonas.library import Library
from uxpersonas.scale_entry import engine_manifest
from uxpersonas.swarm_providers import CallbackProvider, ProviderSpec
from uxpersonas.swarm_queue import Queue, SCHEMA
from uxresearch.canonical import EngineError, byte_digest
from uxresearch.storage import read_bytes, read_json

FIXTURE = Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa/examples/agents/fixture.py"
spec = importlib.util.spec_from_file_location("scale_fixture", FIXTURE)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class ScaleRunTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = fixture.build(Path(self.temp.name).resolve() / "owned")
        self.host = fixture.FixtureHost()
        self.host.can_resume = lambda context_id, observations: context_id in self.host.states

        async def model(request):
            kind = request["payload"]["phase"]
            response = await self.host.respond(kind, request)
            if kind == "review":
                response["result"] = dict(kind="final", judgment=response["result"])
            response["usage"] = dict(input_tokens=10, output_tokens=10, provider="fixture", model="authored-fixture",
                                     provider_cost_microusd=0, cost_basis="fixture_no_charge")
            return response

        provider_spec = ProviderSpec(key="fixture", protocol="fixture", model="authored",
            requests_per_minute=10000, concurrency=2)
        self.provider = CallbackProvider(provider_spec, model, mode="fixture", adapter_sha256="a" * 64)
        old = read_json(self.root / "run/swarm-state.json", private=True)["payload"]
        plan = dict(schema_version=SCHEMA, mode="fixture",
            library_path=str(self.root / "library"), product_id="agent-fixture",
            target="owned-fixture", goal="Check isolated note recovery", build=old["build"],
            limits=dict(parallel=2, turns=12, call_seconds=5, task_seconds=60,
                        lease_seconds=30, budget_microusd=0, max_model_calls=100),
            providers={"fixture": dict(spec=provider_spec.validate(), mode="fixture",
                adapter_sha256=self.provider.adapter_sha256, credential_scope="fixture")},
            tools=[t.spec() for t in fixture.TOOLS], tool_host=self.host.info,
            tool_provenance="authored_fixture", engine_manifest=engine_manifest(),
            jobs=[dict(id="job-" + str(i), provider="fixture", task=row["task"],
                       binding=row["binding"]) for i, row in enumerate(old["tasks"])])
        self.queue = Queue.create(self.root / "scale", plan)

    async def run_scale(self, **kwargs):
        return await scale_run.execute_scale(self.queue.root, {"fixture": self.provider},
            self.host, reviewed=True, max_idle_seconds=0, **kwargs)

    async def test_two_independent_sessions_preserve_failure_and_reuse_completed_report(self):
        report = await self.run_scale()
        self.assertEqual(report["counts"]["complete"], 2, report)
        self.assertFalse(report["actual_model_execution"])
        self.assertGreater(report["authored_model_calls"], 0)
        self.assertTrue(report["provider_usage"])
        self.assertEqual(report["provider_usage"][0]["provider"], "fixture")
        self.assertEqual(report["provider_usage"][0]["input_tokens"], report["authored_model_calls"] * 10)
        self.assertEqual(report["provider_usage"][0]["output_tokens"], report["authored_model_calls"] * 10)
        self.assertEqual(report["provider_usage"][0]["charged_or_estimated_microusd"], 0)
        results = [row["result"] for row in report["tasks"]]
        self.assertEqual(sorted(row["ux_outcome"] for row in results), ["failed", "passed"])
        self.assertTrue(all(row["operational_completed"] for row in results))
        self.assertTrue(all(row["review"] == dict(same_persona=True, independent_rater=False)
                            for row in results))
        for payload in self.host.model_inputs:
            peer = "PER-RETURN" if payload["task"]["persona_id"] == "PER-CAUTIOUS" else "PER-CAUTIOUS"
            self.assertNotIn(peer, str(payload))
        calls = len(self.host.calls)
        self.assertEqual(report, await self.run_scale())
        self.assertEqual(calls, len(self.host.calls))
        self.assertEqual(len(list((self.queue.root / "sessions").glob("*/evidence/*/1/*.png"))), 10)
        self.assertFalse((self.queue.root / "swarm-state.json").exists())

    async def test_pause_after_tool_checkpoint_resumes_without_replaying_tool(self):
        original = self.host.call
        paused = False

        async def call(kind, request):
            nonlocal paused
            reply = await original(kind, request)
            if kind == "tool" and not paused:
                paused = True
                self.queue.control("pause")
            return reply

        self.host.call = call
        first = await self.run_scale()
        self.assertEqual(first["control"], "paused")
        tool_ids = [op["id"] for op in first["operations"] if op["kind"] == "tool"]
        self.assertTrue(tool_ids)
        self.queue.control("resume")
        final = await self.run_scale()
        self.assertEqual(final["counts"]["complete"], 2, final)
        for operation_id in tool_ids:
            self.assertEqual(sum(call[1] == operation_id for call in self.host.calls), 1)

    async def test_model_requests_omit_private_evidence_paths_but_local_receipts_keep_them(self):
        original_tool, original_model = self.host.call, self.provider._callback
        requests = []
        private_name = "private.person@example.com"

        async def tool_call(kind, request):
            reply = await original_tool(kind, request)
            if kind == "tool":
                base = Path(request["payload"]["evidence_path"])
                for capture in reply["result"]["captures"]:
                    original = base / capture["path"]
                    private = base / (private_name + "-" + original.name)
                    original.rename(private)
                    capture["path"] = private.name
            return reply

        async def model_callback(request):
            # This is the actual normalized provider callback input, after the
            # provider has checked request correlation and its payload digest.
            requests.append(copy.deepcopy(request))
            return await original_model(request)

        self.host.call, self.provider._callback = tool_call, model_callback
        report = await self.run_scale()
        self.assertEqual(report["counts"]["complete"], 2, report)
        self.assertTrue(any(not r["payload"]["observations"] for r in requests))
        self.assertTrue(any(r["payload"]["observations"] and r["payload"]["phase"] == "model"
                            for r in requests))
        self.assertTrue(any(r["payload"]["phase"] == "review" for r in requests))
        for request in requests:
            serialized = json.dumps(request)
            self.assertNotIn(private_name, serialized)
            self.assertNotIn(str(self.root), serialized)
            self.assertNotIn("agent-observation-", serialized)
            self.assertNotIn("evidence/", serialized)
            for observation in request["payload"]["observations"]:
                self.assertTrue(observation["id"])
                self.assertIn("facts", observation)
                self.assertIn("checks", observation)
                for kind in ("captures", "artifacts"):
                    for artifact in observation[kind]:
                        self.assertEqual(set(artifact), {"id", "kind", "sha256"})
        retained = 0
        for row in report["tasks"]:
            result = row["result"]
            for artifact in result["receipt"]["artifacts"]:
                path = Path(result["evidence_root"]) / artifact["path"]
                self.assertEqual(byte_digest(read_bytes(path, private=True)), artifact["sha256"])
                if artifact["kind"] == "screenshot":
                    retained += 1
                    self.assertIn(private_name, artifact["path"])
                else:
                    observation = read_json(path, private=True)["observation"]
                    self.assertTrue(all(private_name in capture["path"] for capture in observation["captures"]))
        self.assertEqual(retained, 10)

    async def test_committed_response_lost_acknowledgement_reads_back(self):
        original = Queue.finish
        injected = False

        def finish(queue, claim, request, reply):
            nonlocal injected
            result = original(queue, claim, request, reply)
            if not injected:
                injected = True
                raise OSError("Acknowledgement lost after commit")
            return result

        with patch.object(Queue, "finish", finish):
            report = await self.run_scale()
        self.assertEqual(report["counts"]["complete"], 2, report)
        operations = [call[1] for call in self.host.calls]
        self.assertEqual(len(operations), len(set(operations)))

    async def test_native_failure_survives_reviewer_trying_to_erase_it(self):
        original = self.provider.call

        async def call(request):
            reply = await original(request)
            if request["payload"]["phase"] == "review":
                reply["result"]["judgment"]["criteria"][0]["status"] = "passed"
            return reply

        self.provider.call = call
        report = await self.run_scale()
        row = next(row for row in report["tasks"] if row["persona_id"] == "PER-RETURN")
        self.assertEqual(row["result"]["problem"], "erased_failure", report)
        self.assertFalse(row["result"]["operational_completed"])
        self.assertEqual(row["result"]["receipt"]["criteria"][0]["status"], "failed")
        self.assertEqual(row["result"]["ux_outcome"], "failed")

    async def test_unknown_tool_is_quarantined_and_never_retried(self):
        original = self.host.call

        async def call(kind, request):
            if kind == "tool":
                await original(kind, request)
                raise OSError("Tool effect happened; response unavailable")
            return await original(kind, request)

        self.host.call = call
        first = await self.run_scale()
        self.assertEqual(first["counts"]["uncertain"], 2, first)
        calls = len(self.host.calls)
        again = await self.run_scale()
        self.assertEqual(again, first)
        self.assertEqual(calls, len(self.host.calls))
        self.assertFalse(any(c[0] == "close" for c in self.host.calls))

    async def test_resumed_tool_context_requires_existing_host_attestation(self):
        original = self.host.call

        async def call(kind, request):
            reply = await original(kind, request)
            if kind == "tool":
                self.queue.control("pause")
            return reply

        self.host.call = call
        first = await self.run_scale()
        self.assertEqual(first["control"], "paused")
        self.queue.control("resume")
        self.host.can_resume = lambda context_id, observations: False
        before = len(self.host.calls)
        report = await self.run_scale()
        self.assertEqual(report["counts"]["blocked"], 2, report)
        self.assertEqual(before, len(self.host.calls))
        self.assertTrue(all(row["problem"] == "tool_context_unavailable" for row in report["tasks"]))

    async def test_changed_adapter_is_rejected_before_any_call(self):
        self.host.info["adapter_sha256"] = "b" * 64
        with self.assertRaises(EngineError) as error:
            await self.run_scale()
        self.assertEqual(error.exception.issue["code"], "host_conflict")
        self.assertFalse(self.host.calls)

    async def test_native_failure_remains_in_checkpoint_after_unknown_model(self):
        original = self.provider.call

        async def call(request):
            if any(c["status"] == "failed" for o in request["payload"]["observations"]
                   for c in o["checks"]):
                raise OSError("Unknown model response after failed native check")
            return await original(request)

        self.provider.call = call
        report = await self.run_scale()
        self.assertEqual(report["counts"]["uncertain"], 1, report)
        with self.queue._db() as db:
            import json
            checkpoint = json.loads(db.execute("SELECT checkpoint FROM jobs WHERE status='uncertain'").fetchone()[0])
        self.assertEqual(checkpoint["receipt_preview"]["criteria"][0]["status"], "failed")
        calls = len(self.host.calls)
        await self.run_scale()
        self.assertEqual(calls, len(self.host.calls))

    async def test_zero_idle_bound_still_refills_after_successful_serial_session(self):
        self.host.info["parallel_safe"] = False
        plan = copy.deepcopy(self.queue.plan)
        plan["tool_host"] = copy.deepcopy(self.host.info)
        self.queue = Queue.create(self.root / "serial-scale", plan)
        report = await self.run_scale()
        self.assertEqual(report["counts"]["complete"], 2, report)

    async def test_cached_close_needs_no_restored_tool_context(self):
        # Model a process stopping after close response commit but before its
        # phase checkpoint. Recovery must consume the response without closing
        # again or trying to restore a context which is already gone.
        original = Queue.checkpoint
        interrupted = False

        def checkpoint(queue, claim, state):
            nonlocal interrupted
            if state["phase"] == "finalize" and not interrupted:
                interrupted = True
                queue.release(claim)
                raise EngineError("stale_lease", "Simulated restart after close commit")
            return original(queue, claim, state)

        original_close = self.host.call

        async def call(kind, request):
            reply = await original_close(kind, request)
            if kind == "close":
                self.host.states.pop(request["context_id"], None)
            return reply

        self.host.call = call
        with patch.object(Queue, "checkpoint", checkpoint):
            report = await self.run_scale()
        self.assertEqual(report["counts"]["complete"], 2, report)
        closes = [c[1] for c in self.host.calls if c[0] == "close"]
        self.assertEqual(len(closes), 2)
        self.assertEqual(len(set(closes)), 2)

    async def test_cancelled_inflight_tool_never_admits_late_response(self):
        original = self.host.call

        async def call(kind, request):
            reply = await original(kind, request)
            if kind == "tool":
                self.queue.control("cancel")
            return reply

        self.host.call = call
        report = await self.run_scale()
        self.assertEqual(report["control"], "cancelled")
        self.assertEqual(report["counts"]["complete"], 0)
        self.assertTrue(all(o["state"] == "uncertain" for o in report["operations"] if o["kind"] == "tool"))
        self.assertFalse(any(c[0] == "review" for c in self.host.calls))


if __name__ == "__main__":
    unittest.main()
