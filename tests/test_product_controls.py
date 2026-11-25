"""Existing fixture queue integration; no model service, browser or worker creation."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import _paths
from test_scale_run import fixture
from uxpersonas import product_controls as controls
from uxpersonas.library import Library, PROFILE_FIELDS
from uxpersonas.scale_entry import ScaleLimits, prepare_scale_goal, preview
from uxpersonas.scale_run import ScaleExecution, execute_scale
from uxpersonas.swarm_providers import CallbackProvider, ProviderSpec
from uxresearch.canonical import EngineError, byte_digest
from uxresearch.storage import atomic


class ProductControlsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = fixture.build(Path(self.temp.name).resolve() / "owned")
        self.host = fixture.FixtureHost()
        self.baseline = self.root / "ui-baseline.json"
        atomic(self.baseline, b'{"layout":"owned fixed fixture"}\n')
        with Library(self.root / "library") as library:
            first = library.get("agent-fixture", "PER-CAUTIOUS")
            refs = [dict(persona_id=pid, revision=library.get("agent-fixture", pid)["revision"])
                    for pid in ("PER-CAUTIOUS", "PER-RETURN")]
        self.spec = dict(schema_version=controls.SCHEMA, product_id="agent-fixture",
            context=first["context"], personas=refs,
            models=[dict(key="fixture", label="Offline fixture only", model="authored", reasoning_effort="none")],
            tasks=[dict(id="TASK-RECOVER", requirement_ids=["R-STATE"], goal="Keep the owned draft",
                        actions=["Inspect the draft", "Correct the owned input"],
                        success=["The rejected draft remains"], recovery=["Save corrected input"])],
            style=dict(platform="web", baseline=dict(path=str(self.baseline), sha256=byte_digest(self.baseline.read_bytes())),
                       preserve=["Brand color and primary layout"],
                       components=[dict(id="draft", path="src/Draft.module.css", properties=["min-height", "padding"],
                                        requirement_ids=["R-STATE"])]),
            limits=dict(max_personas=2, max_parallel=2, max_turns=12, max_model_calls=100,
                        budget_microusd=0, max_iterations=3, allowed_models=["fixture"]))
        self.choice = dict(proposal_sha256=controls.propose(self.spec)["proposal_sha256"], confirmed=True,
            persona_ids=["PER-CAUTIOUS", "PER-RETURN"], assignments={"PER-CAUTIOUS":"fixture", "PER-RETURN":"fixture"},
            parallel=2, turns=12, max_model_calls=100, budget_microusd=0, max_iterations=2)
        self.limits = ScaleLimits(parallel=2, turns=12, call_seconds=5, task_seconds=60,
                                  lease_seconds=30, budget_microusd=0, max_model_calls=100)

        async def respond(request):
            kind = request["payload"]["phase"]
            result = await self.host.respond(kind, request)
            judgment = (result["result"] if kind == "review" else
                        result["result"].get("judgment") if result["result"].get("kind") == "final" else None)
            if judgment is not None:
                # The selected authored obligation has its own binding. Evaluate
                # that exact fixture statement from its rejection observation;
                # do not let the native requirement check certify it implicitly.
                self.assertEqual(request["payload"]["task"]["success_criteria"][1:],
                                 ["[TASK-RECOVER] The rejected draft remains"])
                rejected = next(o for o in request["payload"]["observations"] if o["facts"]["stage"] == "rejected")
                judgment["criteria"].append(dict(kind="success", index=1,
                    status="passed" if rejected["facts"]["retained"] else "failed",
                    observation="The rejected draft remains" if rejected["facts"]["retained"] else "The rejected draft was lost",
                    observation_ids=[rejected["id"]]))
            if kind == "review":
                result["result"] = dict(kind="final", judgment=result["result"])
            result["usage"] = dict(input_tokens=10, output_tokens=10, provider="fixture", model="authored",
                                   provider_cost_microusd=0, cost_basis="fixture_no_charge")
            return result
        self.provider = CallbackProvider(ProviderSpec(key="fixture", protocol="fixture", model="authored",
            requests_per_minute=10000, concurrency=2), respond, mode="fixture", adapter_sha256="a"*64)
        self.providers = {"fixture": self.provider}

    def select(self):
        return controls.select(self.spec, self.choice)

    def prepare(self, selection=None):
        with Library(self.root / "library") as library:
            return prepare_scale_goal(library, self.root / "selected-run", self.providers, self.host,
                fixture.TOOLS, product_id="agent-fixture", target="owned-fixture",
                goal="Check owned note recovery",
                build=dict(id="fixture-build", artifact_path=str(self.root / "build.txt"),
                           sha256=byte_digest((self.root / "build.txt").read_bytes())),
                limits=self.limits, persona_ids=self.choice["persona_ids"], assignments=self.choice["assignments"],
                reviewed=True, selection=selection if selection is not None else self.select())

    def test_proposal_and_cancel_have_no_execution_or_cost_authority(self):
        proposal = controls.propose(self.spec)
        self.assertTrue(proposal["requires_explicit_response"])
        self.assertFalse(proposal["silence_is_approval"])
        self.assertFalse(proposal["ui_rendered"])
        self.assertFalse(proposal["cost_approval_granted"])
        calls = []
        result = controls.request_selection(self.spec, lambda p: calls.append(p))
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.host.calls, [])

    def test_host_answer_binds_selected_count_and_exact_routes(self):
        selection = controls.request_selection(self.spec, lambda p: self.choice)
        self.assertEqual(selection, self.select())
        self.assertEqual(len(selection["choice"]["persona_ids"]), 2)

    def test_explicit_response_and_current_proposal_required(self):
        for key, value in (("confirmed", False), ("confirmed", None), ("proposal_sha256", "0"*64)):
            with self.subTest(key=key, value=value):
                choice = {**self.choice, key:value}
                with self.assertRaises(EngineError):
                    controls.select(self.spec, choice)

    def test_missing_duplicate_or_unmapped_personas_refused(self):
        for change in ({"persona_ids":[]}, {"persona_ids":["PER-RETURN", "PER-RETURN"]},
                       {"persona_ids":["PER-UNKNOWN"]}, {"assignments":{"PER-RETURN":"fixture"}},
                       {"assignments":dict.fromkeys(self.choice["persona_ids"], "unapproved")}):
            with self.subTest(change=change), self.assertRaises(EngineError):
                controls.select(self.spec, {**self.choice, **change})

    def test_selected_budget_and_parallel_cannot_exceed_offer(self):
        for name, value in (("parallel",3), ("turns",13), ("budget_microusd",1),
                            ("max_iterations",4), ("max_model_calls",101), ("parallel",True)):
            with self.subTest(name=name), self.assertRaises(EngineError):
                controls.select(self.spec, {**self.choice, name:value})

    def test_changed_prd_and_ui_baseline_invalidate_selection(self):
        selection = self.select()
        for path in (self.root / "PRD.md", self.baseline):
            original = path.read_bytes()
            atomic(path, original + b"changed\n")
            with self.assertRaises(EngineError):
                controls.revalidate(selection)
            atomic(path, original)
        self.assertEqual(controls.revalidate(selection), selection)

    def test_selection_checksum_and_unknown_fields_refused(self):
        selection = self.select()
        selection["choice"]["turns"] = 11
        with self.assertRaises(EngineError):
            controls.revalidate(selection)
        with self.assertRaises(EngineError):
            controls.validate({**self.spec, "auto_start":True})

    def test_prd_obligations_cannot_silently_disappear(self):
        spec = copy.deepcopy(self.spec)
        spec["tasks"][0]["requirement_ids"] = ["UNRELATED"]
        with self.assertRaises(EngineError):
            controls.propose(spec)
        spec = copy.deepcopy(self.spec)
        spec["context"]["requirements"].append(dict(id="R-SECOND", source_anchor="PRD",
                                                   excerpt="Save corrected input."))
        with self.assertRaises(EngineError):
            controls.propose(spec)
        spec["excluded_requirements"] = [dict(requirement_id="R-SECOND", reason="Not observed in this scope")]
        self.assertEqual(controls.propose(spec)["excluded_requirements"], spec["excluded_requirements"])

    def test_style_manifest_is_scoped_but_never_claims_computed_css_proof(self):
        selection = self.select()
        result = controls.check_style_scope(selection, ["src/Draft.module.css"],
                                            {"src/Draft.module.css":["padding"]})
        self.assertTrue(result["scope_valid"])
        self.assertFalse(result["computed_css_verified"])
        self.assertTrue(result["figma_and_replay_required"])
        for paths, props in ((["src/global.css"], {"src/global.css":["padding"]}),
                             (["src/Draft.module.css"], {"src/Draft.module.css":["color"]})):
            with self.assertRaises(EngineError):
                controls.check_style_scope(selection, paths, props)

    def test_global_styles_and_duplicate_component_boundaries_rejected(self):
        for value in ("src/global.css", "../outside.module.css"):
            spec = copy.deepcopy(self.spec)
            spec["style"]["components"][0]["path"] = value
            with self.assertRaises((EngineError, ValueError)):
                controls.validate(spec)
        spec = copy.deepcopy(self.spec)
        spec["style"]["components"].append(copy.deepcopy(spec["style"]["components"][0]))
        with self.assertRaises(EngineError):
            controls.validate(spec)

    def test_actual_catalog_is_minimized_attributed_and_unique(self):
        catalog = controls.seed_catalog()
        self.assertEqual(catalog["license"], "CC-BY-4.0")
        self.assertEqual(len(catalog["records"]), 32)
        self.assertEqual(catalog["retrieval"]["revision"], "ada0f5b53a38bb5a30cce09358adde883c1ab63a")
        self.assertEqual(len({r["id"] for r in catalog["records"]}), 32)
        for row in catalog["records"]:
            self.assertEqual(set(row["attributes"]), {"age","province","occupation","education_level","family_type"})
            self.assertGreaterEqual(row["attributes"]["age"], 19)

    def seed_document(self):
        with Library(self.root / "library") as library:
            saved = library.get("agent-fixture", "PER-CAUTIOUS")
        row = {k:copy.deepcopy(v) for k,v in saved["profile"].items() if k in PROFILE_FIELDS}
        row.update(persona_id="PER-SEED", seed_id=controls.seed_catalog()["records"][0]["id"])
        return dict(product_id="agent-fixture", context=self.spec["context"], personas=[row])

    def test_seed_composition_enters_existing_versioned_library_as_hypothesis(self):
        result = controls.seed_input(self.seed_document())
        self.assertFalse(result["population_representativeness"])
        self.assertEqual(result["input"]["mode"], "prd_hypothesis")
        with Library(self.root / "library") as library:
            library.import_profiles(result["input"])
            saved = library.get("agent-fixture", "PER-SEED")
        self.assertIn("unobserved", " ".join(saved["profile"]["unknowns"]))
        self.assertIn("NVIDIA synthetic seed", " ".join(saved["profile"]["contexts"]))

    def test_duplicate_seed_is_not_counted_as_new_population_coverage(self):
        doc = self.seed_document()
        doc["personas"].append({**doc["personas"][0], "persona_id":"PER-ANOTHER"})
        with self.assertRaises(EngineError):
            controls.seed_input(doc)

    def test_malformed_seed_lists_are_not_coerced_into_apparently_valid_profiles(self):
        for field in ("contexts", "assumptions", "unknowns", "seed_id"):
            for value in (None, {}, "abc" if field != "seed_id" else []):
                doc = self.seed_document()
                doc["personas"][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(EngineError):
                    controls.seed_input(doc)

    def test_preparation_persists_selection_and_criteria_in_existing_queue(self):
        selection = self.select()
        with patch.object(controls, "revalidate", wraps=controls.revalidate) as validate:
            queue = self.prepare(selection)
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(queue.plan["product_selection"], selection)
        self.assertEqual(queue.plan["limits"]["max_model_calls"], 26)
        self.assertEqual(preview(queue)["product_selection_sha256"], selection["selection_sha256"])
        self.assertFalse(preview(queue)["selection_ui_verified"])
        for job in queue.plan["jobs"]:
            self.assertIn("Inspect the draft", job["task"]["actions"])
            self.assertIn("Keep the owned draft", job["task"]["goal"])
            self.assertEqual(job["task"]["requirement_coverage"][0]["obligations"][0]["criterion_refs"][0],
                             dict(kind="success", index=0))
        self.assertEqual(self.host.calls, [])

    def test_new_persona_revision_requires_a_new_selection(self):
        selection = self.select()
        with Library(self.root / "library") as library:
            saved = library.get("agent-fixture", "PER-CAUTIOUS")
            row = {k:copy.deepcopy(v) for k,v in saved["profile"].items() if k in PROFILE_FIELDS}
            row.update(persona_id="PER-CAUTIOUS", claim_ids=[], label="Changed authored goal context")
            library.import_profiles(dict(schema_version="ux-persona-library-input.v1", product_id="agent-fixture",
                mode="prd_hypothesis", context=self.spec["context"], personas=[row]))
        with self.assertRaises(EngineError):
            self.prepare(selection)
        self.assertFalse((self.root / "selected-run").exists())

    def test_unattested_reasoning_effort_cannot_be_substituted(self):
        self.spec["models"][0]["reasoning_effort"] = "ultra"
        self.choice["proposal_sha256"] = controls.propose(self.spec)["proposal_sha256"]
        with self.assertRaises(EngineError):
            self.prepare()
        self.assertEqual(self.host.calls, [])

    def test_new_live_plan_without_selection_is_refused_before_billing_or_dispatch(self):
        # No live adapter exists: this sentinel must fail before provider spec/call access.
        self.providers = {"fixture": SimpleNamespace(mode="live")}
        with Library(self.root / "library") as library:
            with self.assertRaises(EngineError) as error:
                prepare_scale_goal(library, self.root / "unselected", self.providers, self.host,
                    fixture.TOOLS, product_id="agent-fixture", target="owned-fixture", goal="Check recovery",
                    build=dict(id="fixture-build", artifact_path=str(self.root / "build.txt"),
                               sha256=byte_digest((self.root / "build.txt").read_bytes())),
                    limits=self.limits, reviewed=True)
        self.assertEqual(error.exception.issue["code"], "controls_selection")
        self.assertFalse((self.root / "unselected").exists())
        self.assertEqual(self.host.calls, [])

    def test_dispatch_checks_current_prd_and_ui_before_any_call(self):
        queue = self.prepare()
        execution = ScaleExecution(queue, self.providers, self.host)
        atomic(self.baseline, b"Independent UI change\n")
        with self.assertRaises(EngineError):
            execution.validate_adapters()
        self.assertEqual(self.host.calls, [])

    def test_dispatch_checks_reasoning_effort_after_plan_preparation(self):
        self.spec["models"][0]["reasoning_effort"] = "ultra"
        self.choice["proposal_sha256"] = controls.propose(self.spec)["proposal_sha256"]
        self.provider.reasoning_effort = "ultra"
        queue = self.prepare()
        execution = ScaleExecution(queue, self.providers, self.host)
        self.provider.reasoning_effort = "high"
        with self.assertRaises(EngineError):
            execution.validate_adapters()

    async def test_selected_plan_runs_only_the_existing_authored_fixture_route(self):
        queue = self.prepare()
        report = await execute_scale(queue.root, self.providers, self.host,
                                     reviewed=True, max_idle_seconds=0)
        self.assertEqual(report["counts"]["complete"], 2, report)
        self.assertFalse(report["actual_model_execution"])
        self.assertEqual(report["actual_model_calls"], 0)
        self.assertEqual(sorted(row["result"]["ux_outcome"] for row in report["tasks"]), ["failed","passed"])

    def test_configure_cli_returns_proposal_without_starting_execution(self):
        path = self.root / "controls.json"
        atomic(path, json.dumps(self.spec).encode())
        script = _paths.SKILL / "scripts/ux_personas.py"
        result = subprocess.run([sys.executable, str(script), "configure", "--input", str(path)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        proposal = json.loads(result.stdout)
        self.assertFalse(proposal["model_execution_started"])
        self.assertEqual(proposal["proposal_sha256"], self.choice["proposal_sha256"])


if __name__ == "__main__":
    unittest.main()
