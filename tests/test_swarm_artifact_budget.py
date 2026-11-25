"""Real offline evidence registration and receipt admission at the 80-turn bound.

All PNGs and decisions are authored test fixtures, never browser/model evidence.
"""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import _paths
import test_scale_run as support
from ergoqa.png import encode, new_image
from uxpersonas import swarm
from uxpersonas.agent_run import Execution, Limits, _validated_observation_content
from uxpersonas.library import Library
from uxpersonas.scale_entry import engine_manifest
from uxpersonas.scale_report import current_report
from uxpersonas.scale_run import Evidence
from uxpersonas.swarm_providers import ProviderSpec
from uxpersonas.swarm_queue import Queue, SCHEMA, checkpoint_data, data
from uxresearch.canonical import EngineError, byte_digest, canonical, digest
from uxresearch.storage import MAX_BYTES, atomic, read_json


class ArtifactReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = support.fixture.build(Path(self.temp.name).resolve() / "owned")
        self.png = encode(new_image(2, 2))
        self.old = read_json(self.root / "run/swarm-state.json", private=True)["payload"]

    def queue(self, name):
        spec = ProviderSpec(key="fixture", protocol="fixture", model="authored",
                            requests_per_minute=10000, concurrency=1)
        original = self.old["tasks"][0]
        plan = dict(schema_version=SCHEMA, mode="fixture",
            library_path=str(self.root / "library"), product_id="agent-fixture",
            target="owned-fixture", goal="Register eighty authored observations",
            build=self.old["build"],
            limits=dict(parallel=1, turns=80, call_seconds=5, task_seconds=180,
                        lease_seconds=120, budget_microusd=0, max_model_calls=81),
            providers={"fixture": dict(spec=spec.validate(), mode="fixture",
                adapter_sha256="a" * 64, credential_scope="fixture")},
            tools=[tool.spec() for tool in support.fixture.TOOLS],
            tool_host=support.fixture.FixtureHost().info,
            tool_provenance="authored_fixture", engine_manifest=engine_manifest(),
            jobs=[dict(id="job-artifacts", provider="fixture",
                       task=copy.deepcopy(original["task"]), binding=copy.deepcopy(original["binding"]))])
        return Queue.create(self.root / name, plan)

    def register(self, evidence, worker, index, captures=2, queue=None, claim=None):
        base = Path(worker["claim"]["evidence_path"])
        images = []
        for ordinal in range(captures):
            path = base / f"authored-{index}-{ordinal}.png"
            atomic(path, self.png)
            images.append(dict(path=path.name, sha256=byte_digest(self.png)))
        result = dict(text="Owned offline observation. " + "A saved synthetic control remains visible. " * 20,
            facts={"sequence": index, "authored_fixture": True}, captures=images,
            checks=[dict(kind="success", index=0, status="passed"),
                    dict(kind="recovery", index=0, status="passed")] if index == 80 else [])
        _validated_observation_content(result)
        if queue is not None:
            request = queue.begin(claim, "tool", str(index),
                                  {"name": "inspect", "arguments": {}})["request"]
            reply = {key: request[key] for key in ("operation_id", "context_id", "request_sha256")}
            reply.update(trace_id=f"authored-observation-{index}", result=result)
            queue.finish(claim, request, reply)
        observation = evidence.observation(worker, "Inspect an owned control.", result, index)
        worker["observations"].append(observation)
        return observation

    @staticmethod
    def judgment():
        return dict(reason="Authored offline evidence registration completed.",
                    criteria=[dict(kind=kind, index=0, status="passed",
                                   observation="The authored checkpoint was observed.",
                                   observation_ids=["obs-80"])
                              for kind in ("success", "recovery")])

    def test_eighty_tools_register_real_logs_and_pngs_finalize_and_revalidate(self):
        for captures in (1, 2):
            with self.subTest(pngs_per_tool=captures):
                queue = self.queue(f"scale-{captures}")
                claim = queue.claim("artifact-worker")
                session = queue.root / "sessions" / claim["job_id"]
                base = session / "evidence" / claim["job"]["task"]["id"] / "1"
                for path in (session.parent, session, session / "evidence", base.parent, base):
                    path.mkdir(mode=0o700, exist_ok=True)
                worker = dict(queue_claim=claim, context_id=claim["context_id"], observations=[],
                    claim=dict(task=claim["job"]["task"], binding=claim["job"]["binding"],
                               evidence_path=str(base), attempt=1))
                evidence = Evidence(session)
                state = dict(turn=0, phase="tool", observations=worker["observations"])
                for index in range(1, 81):
                    self.register(evidence, worker, index, captures, queue, claim)
                    state["turn"] = index
                    # Production creates a receipt preview after each admitted
                    # tool response. This catches the former 65th-observation crash.
                    state["receipt_preview"] = evidence.receipt(worker, state, queue.plan)
                    self.assertEqual(len(state["receipt_preview"]["artifacts"]), index * (captures + 1))
                    queue.checkpoint(claim, state)
                judgment = self.judgment()
                receipt = evidence.receipt(worker, state, queue.plan, judgment=judgment)
                self.assertEqual(receipt["outcome"], "passed")
                self.assertEqual(len(receipt["steps"]), 80)
                self.assertEqual(len(receipt["artifacts"]), 80 * (captures + 1))
                self.assertLess(len(canonical(receipt)), 262144)
                self.assertTrue(all(len(item["evidence_ids"]) <= 64 for item in receipt["criteria"]))
                for artifact in receipt["artifacts"]:
                    self.assertEqual(byte_digest((session / artifact["path"]).read_bytes()), artifact["sha256"])
                state.update(phase="finalize", first_judgment=judgment,
                             first_judgment_sha256=digest(judgment), judgment=judgment)
                queue.checkpoint(claim, state)
                result = dict(mode="fixture", tool_provenance="authored_fixture",
                    operational_completed=True, ux_outcome="passed", receipt=receipt,
                    first_judgment=judgment, first_judgment_sha256=digest(judgment),
                    judgment=judgment, review=dict(same_persona=True, independent_rater=False),
                    evidence_root=str(session), product_ready=False, real_user_evidence=False)
                self.assertLess(len(canonical(result)), 262144)
                # Existing request/final-result limits remain independent of
                # the count of filesystem artifacts.
                with self.assertRaises(EngineError):
                    data({"oversize": "x" * 262144})
                with self.assertRaises(EngineError):
                    queue.complete(claim, {"oversize": "x" * (1024 * 1024)})
                queue.complete(claim, result)
                report = current_report(queue)
                self.assertEqual(report["counts"]["complete"], 1)
                self.assertTrue(report["tasks"][0]["current_valid"])
                self.assertEqual(len([op for op in report["operations"] if op["kind"] == "tool"]), 80)
                self.assertTrue(all(op["state"] == "done" for op in report["operations"]))
                self.assertEqual(current_report(queue), report)
                changed = session / receipt["artifacts"][-1]["path"]
                atomic(changed, self.png + b"tampered")
                self.assertFalse(current_report(queue)["tasks"][0]["current_valid"])

    def test_legacy_receipt_path_accepts_the_same_eighty_observation_ledger(self):
        with Library(self.root / "library") as library:
            claim = swarm.claim(library, self.root / "run", "legacy-artifact-worker", "T-CAUTIOUS")
            execution = Execution(library, self.root / "run", support.fixture.FixtureHost(),
                                  support.fixture.TOOLS, Limits(), None)
            worker = dict(claim=claim, context_id="legacy-artifacts", observations=[])
            for index in range(1, 81):
                self.register(execution, worker, index, 2)
            receipt = execution.make_receipt(worker, self.judgment())
            self.assertEqual(len(receipt["artifacts"]), 240)
            self.assertLess(len(canonical(receipt)), 262144)
            self.assertEqual(swarm.record(library, self.root / "run", receipt)["status"], "passed")
            self.assertEqual(swarm.report(library, self.root / "run")["counts"]["passed"], 1)

    def test_exact_artifact_boundary_and_existing_file_path_hash_and_privacy_bounds(self):
        root = self.root / "count-boundary"
        base = root / "evidence" / "T-boundary" / "1"
        base.mkdir(mode=0o700, parents=True)
        entry = dict(task=dict(id="T-boundary", success_criteria=["Observe"], recovery_criteria=[]), attempts=1)
        artifacts = []
        for index in range(256):
            path = base / f"log-{index}.json"
            raw = canonical({"authored": True, "index": index})
            atomic(path, raw)
            artifacts.append(dict(id=f"log-{index}", kind="execution_log",
                                  path=str(path.relative_to(root)), sha256=byte_digest(raw)))
        self.assertEqual(swarm.MAX_RECEIPT_ARTIFACTS, 256)
        self.assertEqual(len(swarm._artifacts(root, entry, {"artifacts": artifacts})), 256)
        with self.assertRaisesRegex(EngineError, "Artifact list exceeds"):
            swarm._artifacts(root, entry, {"artifacts": artifacts + [dict(artifacts[0], id="log-256")]})
        for modified in (dict(artifacts[0], sha256="0" * 64),
                         dict(artifacts[0], path="../outside.json")):
            with self.assertRaises(EngineError):
                swarm._artifacts(root, entry, {"artifacts": [modified]})
        private = root / artifacts[0]["path"]
        private.chmod(0o644)
        with self.assertRaises(EngineError) as error:
            swarm._artifacts(root, entry, {"artifacts": [artifacts[0]]})
        self.assertEqual(error.exception.issue["code"], "unsafe_mode")
        private.chmod(0o600)
        with self.assertRaisesRegex(EngineError, "bounded PNG"):
            swarm._artifacts(root, entry, {"artifacts": [dict(artifacts[0], kind="screenshot")]})
        header = struct.pack(">II", 4001, 4000) + self.png[24:29]
        image = self.png[:16] + header + struct.pack(">I", zlib.crc32(b"IHDR" + header)) + self.png[33:]
        huge_png = base / "too-many-pixels.png"
        atomic(huge_png, image)
        with self.assertRaisesRegex(EngineError, "bounded PNG"):
            swarm._artifacts(root, entry, {"artifacts": [dict(id="pixels", kind="screenshot",
                path=str(huge_png.relative_to(root)), sha256=byte_digest(image))]})
        self.assertEqual(MAX_BYTES, 16 * 1024 * 1024)
        oversized = base / "oversized.json"
        with oversized.open("wb") as stream:
            stream.truncate(MAX_BYTES + 1)
        oversized.chmod(0o600)
        with self.assertRaises(EngineError) as error:
            swarm._artifacts(root, entry, {"artifacts": [dict(
                id="oversized", kind="execution_log", path=str(oversized.relative_to(root)), sha256="a" * 64)]})
        self.assertEqual(error.exception.issue["code"], "unsafe_file")
        receipt = dict(schema_version="ux-persona-swarm-receipt.v1", task_id="T-boundary",
            worker_id="boundary-worker", lease_token="unit", build_sha256="a" * 64,
            persona_revision=1, profile_sha256="b" * 64, outcome="inconclusive",
            reason="Authored boundary checks.", steps=[dict(action="Observe", observation="Recorded",
                evidence_ids=["log-0"])], criteria=[dict(kind="success", index=0, status="passed",
                observation="Authored file observed.", evidence_ids=[row["id"] for row in artifacts[:65]])],
            artifacts=artifacts)
        with self.assertRaises(EngineError):
            swarm._receipt(root, entry, receipt)
        receipt["criteria"][0]["evidence_ids"] = ["log-0"]
        receipt["reason"] = "private customer@example.test"
        with self.assertRaisesRegex(EngineError, "personal identifiers"):
            swarm._receipt(root, entry, receipt)
        with self.assertRaises(EngineError):
            _validated_observation_content(dict(text="Owned", facts={"large": "x" * 65536}, checks=[]))
        with self.assertRaises(EngineError):
            checkpoint_data({"turn": 80, "observations": [{}] * 81}, 80)


if __name__ == "__main__":
    unittest.main()
