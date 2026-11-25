"""Offline preparation and real evidence admission; no model or browser calls."""
import copy
from pathlib import Path
import tempfile
import unittest

import _paths
from ergoqa.png import encode, new_image
from test_scale_run import fixture
from uxpersonas import product_controls as controls
from uxpersonas.library import Library
from uxpersonas.scale_entry import ScaleLimits, prepare_scale_goal
from uxpersonas.scale_run import ScaleExecution
from uxpersonas.swarm_providers import CallbackProvider, ProviderSpec


def evaluate_sample_stub(task, _facts, text):
    if "PRD-START-SAMPLE" in task.get("requirement_ids", []) and "Sample preview" in text:
        return [dict(kind="success", index=0, status="passed")]
    return []
from uxresearch.canonical import byte_digest
from uxresearch.storage import atomic


class AuthoredCriterionScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        excerpt = "Show the sample entry."
        atomic(self.root / "PRD.md", excerpt.encode())
        atomic(self.root / "build.txt", b"Owned offline sample fixture")
        atomic(self.root / "baseline.json", b'{}')
        context = dict(prd_path=str(self.root / "PRD.md"),
            prd_sha256=byte_digest((self.root / "PRD.md").read_bytes()),
            requirements=[dict(id="PRD-START-SAMPLE", source_anchor="PRD", excerpt=excerpt)])
        with Library(self.root / "library") as library:
            library.import_profiles(dict(schema_version="ux-persona-library-input.v1",
                product_id="sample-fixture", mode="prd_hypothesis", context=context,
                personas=[dict(persona_id="PER-SAMPLE", label="Inspect the sample entry",
                    goals=["Find the sample"], behaviors=["Inspect the entry"],
                    contexts=["Owned synthetic fixture"], assumptions=["Authored hypothesis"],
                    unknowns=["Real user behavior"], requirement_ids=["PRD-START-SAMPLE"], claim_ids=[])]))
        self.host = fixture.FixtureHost()

        async def forbidden(request):
            raise AssertionError("This regression must never call a model.")

        self.providers = {"fixture": CallbackProvider(
            ProviderSpec(key="fixture", protocol="fixture", model="authored"), forbidden,
            mode="fixture", adapter_sha256="a" * 64)}
        self.spec = dict(schema_version=controls.SCHEMA, product_id="sample-fixture",
            context=context, personas=[dict(persona_id="PER-SAMPLE", revision=1)],
            models=[dict(key="fixture", label="Offline", model="authored", reasoning_effort="none")],
            tasks=[dict(id="TASK-BADGE", requirement_ids=["PRD-START-SAMPLE"],
                goal="Inspect the sample and the authored badge", actions=["Inspect the entry", "Inspect the badge"],
                success=["The authored badge is visible"], recovery=["Recover only after a triggering failure"])],
            style=dict(platform="web", baseline=dict(path=str(self.root / "baseline.json"),
                sha256=byte_digest((self.root / "baseline.json").read_bytes())),
                preserve=["Keep the sample entry"], components=[dict(id="entry", path="Entry.module.css",
                    properties=["padding"], requirement_ids=["PRD-START-SAMPLE"])]),
            limits=dict(max_personas=1, max_parallel=1, max_turns=4, max_model_calls=5,
                budget_microusd=0, max_iterations=1, allowed_models=["fixture"]))

    def prepare(self, *, selected=True):
        choice = dict(proposal_sha256=controls.propose(self.spec)["proposal_sha256"], confirmed=True,
            persona_ids=["PER-SAMPLE"], assignments={"PER-SAMPLE": "fixture"}, parallel=1, turns=4,
            max_model_calls=5, budget_microusd=0, max_iterations=1)
        selection = controls.select(self.spec, choice) if selected else None
        with Library(self.root / "library") as library:
            queue = prepare_scale_goal(library, self.root / ("selected" if selected else "native-only"),
                self.providers, self.host, fixture.TOOLS, product_id="sample-fixture", target="owned-fixture",
                goal="Inspect selected scope" if selected else "Inspect native scope",
                build=dict(id="fixture-build", artifact_path=str(self.root / "build.txt"),
                    sha256=byte_digest((self.root / "build.txt").read_bytes())),
                limits=ScaleLimits(parallel=1, turns=4, max_model_calls=5),
                persona_ids=choice["persona_ids"], assignments=choice["assignments"],
                reviewed=True, selection=selection)
        execution = ScaleExecution(queue, self.providers, self.host)
        job = queue.plan["jobs"][0]
        worker, evidence = execution.worker_projection(dict(job=job, job_id=job["id"],
            context_id="sample-context", owner="sample-worker", lease_token="b" * 64))
        return queue, worker, evidence

    def observe(self, worker, evidence, text, checks, index):
        raw = encode(new_image(2, 2))
        filename = f"authored-{index}.png"
        atomic(Path(worker["claim"]["evidence_path"]) / filename, raw)
        result = evidence.observation(worker, "Inspect owned synthetic UI",
            dict(text=text, facts={}, captures=[dict(path=filename, sha256=byte_digest(raw))], checks=checks), index)
        worker["observations"].append(result)
        return result

    def receipt(self, *, selected=True, author_status="not_run", interrupted=False):
        queue, worker, evidence = self.prepare(selected=selected)
        task = worker["claim"]["task"]
        text = "Sample preview"
        checks = evaluate_sample_stub(task, {}, text)
        self.assertEqual(checks, [dict(kind="success", index=0, status="passed")])
        self.observe(worker, evidence, text, checks, 1)
        author = None
        if author_status != "not_run":
            author = self.observe(worker, evidence, "The authored badge is visible" if author_status == "passed"
                else "The authored badge is absent", [], 2)
        criteria = [dict(kind="success", index=i, status="not_run", observation="Not assessed by model",
            observation_ids=[]) for i in range(len(task["success_criteria"]))]
        if author is not None:
            self.assertEqual(len(criteria), 2)
            criteria[1].update(status=author_status, observation=author["text"], observation_ids=[author["id"]])
        criteria.append(dict(kind="recovery", index=0, status="not_applicable",
            observation="No recovery trigger occurred", observation_ids=[]))
        before = copy.deepcopy(queue.plan)
        receipt = evidence.receipt(worker, {"observations": worker["observations"]}, queue.plan,
            judgment=None if interrupted else dict(reason="Owned offline evidence only", criteria=criteria))
        self.assertEqual(queue.plan, before)
        self.assertEqual(self.host.calls, [])
        return receipt, task

    def test_native_pass_does_not_cover_unobserved_authored_success(self):
        receipt, task = self.receipt()
        self.assertEqual(receipt["outcome"], "inconclusive")
        self.assertEqual([c["status"] for c in receipt["criteria"]], ["passed", "not_run", "not_applicable"])
        self.assertEqual(receipt["criteria"][1]["evidence_ids"], [])
        obligations = task["requirement_coverage"][0]["obligations"]
        self.assertEqual([o["criterion_refs"] for o in obligations],
            [[dict(kind="success", index=0)], [dict(kind="success", index=1)]])
        self.assertEqual(obligations[1]["description"], "The authored badge is visible")

    def test_interruption_preserves_native_pass_without_promoting_authored_success(self):
        receipt, _ = self.receipt(interrupted=True)
        self.assertEqual(receipt["outcome"], "inconclusive")
        self.assertEqual([c["status"] for c in receipt["criteria"]], ["passed", "not_run", "not_run"])

    def test_authored_failure_survives_native_pass(self):
        receipt, _ = self.receipt(author_status="failed")
        self.assertEqual(receipt["outcome"], "failed")
        self.assertEqual([c["status"] for c in receipt["criteria"]], ["passed", "failed", "not_applicable"])
        self.assertEqual(receipt["criteria"][1]["evidence_ids"], ["log-2", "png-2-0"])

    def test_exact_authored_observation_can_complete_its_own_slot(self):
        receipt, _ = self.receipt(author_status="passed")
        self.assertEqual(receipt["outcome"], "passed")
        self.assertEqual(receipt["criteria"][1]["evidence_ids"], ["log-2", "png-2-0"])

    def test_native_only_plan_keeps_original_slots_and_native_promotion(self):
        receipt, task = self.receipt(selected=False)
        self.assertEqual(len(task["success_criteria"]), 1)
        self.assertEqual(receipt["outcome"], "passed")
        self.assertEqual([c["status"] for c in receipt["criteria"]], ["passed", "not_applicable"])


if __name__ == "__main__":
    unittest.main()
