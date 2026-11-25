"""Offline CLI workflow and paired journey comparison regressions.

The evidence, people, screenshots and application builds here are invented.
These checks exercise Remorsearch's real local persistence and CLI, not public
collection, browser behavior, independent evidence authenticity or UX benefit.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import _paths
import engine_release_factory as factory
from ergoqa.png import encode, new_image
from uxpersonas import swarm
from uxpersonas.library import Library
from uxresearch.canonical import byte_digest, canonical, digest
from uxresearch.ledger import Run
from uxresearch.personas import claim_cards
from uxresearch.storage import atomic, read_json
from test_persona_library import profile_input


ENTRYPOINT = Path(os.environ.get(
    "REMORSEARCH_PERSONA_TEST_ENTRYPOINT", str(_paths.SKILL / "scripts/ux_personas.py")
))


class PersonaComparisonTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="remorsearch-comparison-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.library_path = self.root / "library"
        self.baseline = self.root / "before"
        self.candidate = self.root / "after"
        self.doc = profile_input(self.root)
        other = copy.deepcopy(self.doc["personas"][0])
        other.update(persona_id="PER-returner", label="Returning comparer",
                     goals=["Compare saved choices"], behaviors=["Recheck saved selections"],
                     contexts=["Return to an interrupted shortlist"])
        self.doc["personas"].append(other)
        self.specs = {}
        for name in ("before", "after"):
            build = self.root / (name + "-build.txt")
            atomic(build, ("Invented offline " + name + " build; no application launched.\n").encode())
            tasks = []
            for index, persona in enumerate(self.doc["personas"], 1):
                tasks.append(dict(
                    id="T" + str(index), persona_id=persona["persona_id"],
                    requirement_ids=["local-results"],
                    goal=persona["goals"][0], starting_state="Fresh synthetic choices",
                    actions=["Save a choice", "Interrupt and return"],
                    decisions=persona["behaviors"],
                    success_criteria=["Selected choice is retained"],
                    recovery_criteria=["Return shows the saved selection"],
                    data_namespace=name + "-fixture" + str(index),
                    resource_id=name + "-session" + str(index),
                    side_effects="owned_fixture_write",
                    stop_conditions=["Real customer data appears"],
                    requirement_coverage=[dict(requirement_id="local-results", obligations=[
                        dict(id="retain", description="Keep the selected choice",
                             criterion_refs=[dict(kind="success", index=0)], exclusion_reason=None),
                        dict(id="return", description="Restore the saved selection on return",
                             criterion_refs=[dict(kind="recovery", index=0)], exclusion_reason=None),
                    ])],
                ))
            self.specs[name] = dict(
                schema_version=swarm.SCHEMA, product_id="sample",
                build=dict(id=name, artifact_path=str(build), sha256=byte_digest(build.read_bytes())),
                max_parallel=2, lease_seconds=300, max_attempts=2, tasks=tasks,
            )

    def command(self, command, *args, expected=0, decode=True):
        result = subprocess.run(
            [sys.executable, str(ENTRYPOINT), *(["personas"] if ENTRYPOINT.name == "remorsearch.py" else []),
             command, "--library", str(self.library_path),
            *map(str, args)], capture_output=True, text=True, timeout=20, cwd=self.root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout) if decode else result

    def write_input(self, name, value):
        path = self.root / name
        atomic(path, canonical(value))
        return path

    def prepare(self):
        with Library(self.library_path) as library:
            library.import_profiles(self.doc)
            swarm.create_plan(library, self.baseline, self.specs["before"])
            swarm.create_plan(library, self.candidate, self.specs["after"])

    def receipt(self, root, claim, outcome):
        artifacts = []
        for aid, kind, raw in (
            ("log", "execution_log", b"Invented offline observation: save, interrupt, return.\n"),
            ("png", "screenshot", encode(new_image(2, 2))),
        ):
            path = Path(claim["evidence_path"]) / aid
            atomic(path, raw)
            artifacts.append(dict(id=aid, kind=kind, path=str(path.relative_to(root)),
                                  sha256=byte_digest(raw)))
        return dict(
            schema_version="ux-persona-swarm-receipt.v1",
            task_id=claim["task"]["id"], worker_id=claim["lease"]["worker_id"],
            lease_token=claim["lease"]["lease_token"], build_sha256=claim["build"]["sha256"],
            persona_revision=claim["binding"]["revision"],
            profile_sha256=claim["binding"]["profile_sha256"], outcome=outcome,
            reason="Invented offline observation, not live product evidence.",
            steps=[dict(action="Save, interrupt and return", observation="Synthetic fixture observation.",
                        evidence_ids=["log", "png"])],
            criteria=[dict(
                kind=kind, index=0,
                status="failed" if outcome == "failed" and kind == "recovery" else "passed",
                observation="Synthetic expectation mismatch." if outcome == "failed" and kind == "recovery"
                            else "Synthetic expected result observed.",
                evidence_ids=["log", "png"],
            ) for kind in ("success", "recovery")],
            artifacts=artifacts,
        )

    def complete(self, root, task_id, outcome, *, cli=False):
        if cli:
            claim = self.command("claim", "--run", root, "--worker", "fixture-worker", "--task", task_id)
            receipt = self.receipt(root, claim, outcome)
            self.command("record", "--run", root, "--input", self.write_input("receipt.json", receipt))
        else:
            with Library(self.library_path) as library:
                claim = swarm.claim(library, root, "fixture-worker", task_id)
                receipt = self.receipt(root, claim, outcome)
                swarm.record(library, root, receipt)
        return receipt

    def complete_pair(self):
        self.prepare()
        for root, outcomes in ((self.baseline, ("failed", "passed")),
                               (self.candidate, ("passed", "failed"))):
            for index, outcome in enumerate(outcomes, 1):
                self.complete(root, "T" + str(index), outcome)

    def snapshot(self):
        return {str(path.relative_to(self.root)): byte_digest(path.read_bytes())
                for path in self.root.rglob("*") if path.is_file()}

    def research_command(self, root, *args):
        packaged = ENTRYPOINT.name == "remorsearch.py"
        entrypoint = ENTRYPOINT if packaged else ENTRYPOINT.with_name("ux_research.py")
        result = subprocess.run(
            [sys.executable, str(entrypoint), *(["research"] if packaged else []),
             str(args[0]), "--run", str(root), *map(str, args[1:])],
            capture_output=True, text=True, timeout=20, cwd=self.root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def gated_fixture(self):
        now = time.time()
        research = factory.fixture.build(self.root / "research", clock=lambda: now)
        self.research_command(
            research, "merge", "--manifest", research / "axes.json",
            "--search-ledger", research / "search-ledger.jsonl",
            "--imports", research / "sanitized-imports.json",
            "--returns", research / "returns/editors.json",
        )
        bundle = read_json(research / "bundle.json")
        bundle["records"]["sources"][0]["summary"] = "Invented offline comparison input."
        stamp = Run(research, clock=lambda: now).now_iso()
        for records in bundle["records"].values():
            for record in records:
                for field in ("summary", "statement"):
                    if field in record:
                        bundle["research"]["summary_attestations"].append(dict(
                            record_id=record["id"], field=field, content_sha256=digest(record[field]),
                            reviewed_by="self", reviewed_at=stamp,
                        ))
        atomic(research / "bundle.json", canonical(bundle))
        self.research_command(research, "gate", "--bundle", research / "bundle.json", "--write-bundle")
        bundle, gate = read_json(research / "bundle.json"), read_json(research / "gate.json")
        self.assertEqual(gate["result"], "pass")
        cards = claim_cards(bundle, gate)
        self.assertTrue(cards[0]["exportable"])
        self.doc.update(mode="gated_research", research=dict(
            run=str(research), bundle=str(research / "bundle.json"), gate=str(research / "gate.json")))
        for persona in self.doc["personas"]:
            persona["claim_ids"] = [cards[0]["claim_id"]]
        return research

    def test_cli_gated_multi_persona_persistence_to_paired_journey_report(self):
        self.gated_fixture()
        imported = self.command("import", "--input", self.write_input("personas.json", self.doc))
        self.assertEqual(len(imported["imported"]), 2)
        # Every command is a new process; reuse must read the persisted library.
        listed = self.command("list", "--product", "sample")
        self.assertEqual(len(listed["personas"]), 2)
        self.assertTrue(all(row["reusable"] for row in listed["personas"]))
        for persona in self.doc["personas"]:
            reused = self.command("reuse", "--product", "sample", "--persona", persona["persona_id"])
            self.assertEqual(reused["provenance"]["mode"], "gated_research")
            self.assertEqual(reused["revision"], 1)
        for name, root, outcomes in (
            ("before", self.baseline, ("failed", "passed")),
            ("after", self.candidate, ("passed", "failed")),
        ):
            self.command("plan", "--run", root, "--input", self.write_input(name + ".json", self.specs[name]))
            for index, outcome in enumerate(outcomes, 1):
                self.complete(root, "T" + str(index), outcome, cli=True)
            report = self.command("report", "--run", root)
            self.assertEqual(report["counts"]["passed"], 1)
            self.assertEqual(report["counts"]["failed"], 1)
        before = self.snapshot()
        compared = self.command("compare", "--baseline", self.baseline, "--run", self.candidate,
                                "--format", "json")
        self.assertEqual(compared["schema_version"], "ux-persona-swarm-comparison.v1")
        self.assertTrue(compared["comparison_complete"])
        self.assertEqual(compared["counts"]["failed_to_passed"], 1)
        self.assertEqual(compared["counts"]["passed_to_failed"], 1)
        self.assertEqual(compared["counts"]["not_compared"], 0)
        self.assertFalse(compared["product_ready"])
        self.assertFalse(compared["measured_ux_improvement"])
        self.assertEqual(before, self.snapshot())
        rendered = self.command("compare", "--baseline", self.baseline, "--run", self.candidate, decode=False)
        self.assertIn("failed -> passed", rendered.stdout)
        self.assertIn("passed -> failed", rendered.stdout)
        self.assertNotIn("lease_token", rendered.stdout)
        self.assertEqual(before, self.snapshot())

    def comparison(self, *, baseline=None, candidate=None):
        from uxpersonas.comparison import compare
        with Library(self.library_path) as library:
            return compare(library, baseline or self.baseline, candidate or self.candidate)

    def change_state(self, root, change):
        state = read_json(root / "swarm-state.json")["payload"]
        change(state)
        atomic(root / "swarm-state.json", canonical(dict(
            schema_version="ux-persona-swarm-state.v3", payload=state, sha256=digest(state))))

    def test_partial_cli_report_can_be_reopened_after_existing_work_continues(self):
        self.prepare()
        self.complete(self.baseline, "T1", "failed")
        self.complete(self.baseline, "T2", "passed")
        self.complete(self.candidate, "T1", "passed")
        before = self.snapshot()
        partial = self.command("compare", "--baseline", self.baseline, "--run", self.candidate,
                               "--format", "json", expected=1)
        self.assertFalse(partial["comparison_complete"])
        self.assertEqual(partial["counts"]["failed_to_passed"], 1)
        self.assertEqual(partial["counts"]["not_compared"], 1)
        self.assertEqual(partial["tasks"][1]["candidate_status"], "pending")
        self.assertEqual(before, self.snapshot())
        baseline_bytes = (self.baseline / "swarm-state.json").read_bytes()
        self.complete(self.candidate, "T2", "failed", cli=True)
        finished = self.command("compare", "--baseline", self.baseline, "--run", self.candidate,
                                "--format", "json")
        self.assertTrue(finished["comparison_complete"])
        self.assertEqual(finished["counts"]["passed_to_failed"], 1)
        self.assertEqual(baseline_bytes, (self.baseline / "swarm-state.json").read_bytes())

    def test_changed_journey_fields_are_additional_coverage_not_improvement(self):
        self.complete_pair()
        changes = {
            "goal": lambda task: task.update(goal="Inspect a different result"),
            "starting_state": lambda task: task.update(starting_state="Previously populated synthetic choices"),
            "actions": lambda task: task.update(actions=["Save only"]),
            "decisions": lambda task: task.update(decisions=["Choose the first visible option"]),
            "success_criteria": lambda task: task.update(success_criteria=["A different expectation"]),
            "recovery_criteria": lambda task: task.update(recovery_criteria=["A different recovery expectation"]),
            "stop_conditions": lambda task: task.update(stop_conditions=["Stop before saving"]),
            "side_effects": lambda task: task.update(side_effects="read_only"),
            "requirement_coverage": lambda task: task["requirement_coverage"][0]["obligations"][0].update(
                description="A different declared obligation"),
        }
        for index, (field, change) in enumerate(changes.items()):
            with self.subTest(field=field):
                spec = copy.deepcopy(self.specs["after"])
                change(spec["tasks"][0])
                root = self.root / ("variant" + str(index))
                with Library(self.library_path) as library:
                    swarm.create_plan(library, root, spec)
                self.complete(root, "T1", "passed")
                self.complete(root, "T2", "failed")
                result = self.comparison(candidate=root)
                self.assertFalse(result["comparison_complete"])
                self.assertEqual(result["counts"]["failed_to_passed"], 0)
                self.assertEqual(result["counts"]["not_compared"], 1)
                self.assertIn("task." + field, result["tasks"][0]["issues"][0]["fields"])

    def test_different_execution_budgets_do_not_form_a_paired_comparison(self):
        self.specs["after"].update(max_parallel=1, lease_seconds=30, max_attempts=1)
        self.complete_pair()
        result = self.comparison()
        self.assertEqual(result["counts"]["not_compared"], 2)
        self.assertEqual(result["counts"]["failed_to_passed"], 0)
        self.assertEqual(result["tasks"][0]["issues"][0]["code"], "different_limits")

    def test_missing_and_added_journeys_remain_visible(self):
        self.specs["after"]["tasks"][0]["id"] = "ADDED"
        self.complete_pair_renamed()
        result = self.comparison()
        self.assertEqual(result["counts"]["total"], 3)
        self.assertEqual(result["counts"]["compared"], 1)
        self.assertEqual(result["counts"]["not_compared"], 2)
        self.assertEqual(result["counts"]["failed_to_passed"], 0)
        self.assertEqual({row["task_id"] for row in result["tasks"]}, {"ADDED", "T1", "T2"})

    def complete_pair_renamed(self):
        self.prepare()
        for root, ids, outcomes in (
            (self.baseline, ("T1", "T2"), ("failed", "passed")),
            (self.candidate, ("ADDED", "T2"), ("passed", "failed")),
        ):
            for task_id, outcome in zip(ids, outcomes):
                self.complete(root, task_id, outcome)

    def test_unobserved_criterion_is_not_a_failure_to_pass_improvement(self):
        self.prepare()
        with Library(self.library_path) as library:
            claim = swarm.claim(library, self.baseline, "fixture-worker", "T1")
            receipt = self.receipt(self.baseline, claim, "failed")
            receipt["criteria"] = [row for row in receipt["criteria"] if row["kind"] == "recovery"]
            swarm.record(library, self.baseline, receipt)
        self.complete(self.baseline, "T2", "passed")
        self.complete(self.candidate, "T1", "passed")
        self.complete(self.candidate, "T2", "passed")
        result = self.comparison()
        self.assertFalse(result["comparison_complete"])
        self.assertEqual(result["criterion_counts"]["not_compared"], 1)
        unobserved = result["tasks"][0]["criteria"][0]
        self.assertEqual(unobserved["baseline"]["status"], "not_run")
        self.assertEqual(unobserved["change"], "not_compared")
        self.assertEqual(unobserved["baseline"]["evidence"], [])

    def test_excluded_and_unassessed_requirements_never_become_verified(self):
        for spec in self.specs.values():
            obligation = spec["tasks"][0]["requirement_coverage"][0]["obligations"][0]
            obligation.update(criterion_refs=[], exclusion_reason="Outside this explicitly bounded fixture check.")
            spec["tasks"][1].pop("requirement_coverage")
        self.prepare()
        for root in (self.baseline, self.candidate):
            self.complete(root, "T1", "passed")
            self.complete(root, "T2", "passed")
        result = self.comparison()
        coverage = result["source_runs"]["candidate"]["coverage_summary"]
        self.assertFalse(coverage["all_declared_requirements_passed"])
        self.assertEqual(coverage["requirement_assignments"]["incomplete"], 1)
        self.assertEqual(coverage["requirement_assignments"]["unassessed"], 1)
        self.assertEqual(result["tasks"][0]["requirements"][0]["candidate"]["obligations"][0]["status"], "excluded")
        self.assertFalse(result["product_ready"])

    def test_expired_lease_is_reported_without_changing_or_renewing_it(self):
        self.prepare()
        self.complete(self.baseline, "T1", "failed")
        self.complete(self.baseline, "T2", "passed")
        with Library(self.library_path) as library:
            swarm.claim(library, self.candidate, "unfinished-worker", "T1")
        self.change_state(self.candidate, lambda state: state["tasks"][0]["lease"].update(expires_at=0))
        before = self.snapshot()
        result = self.comparison()
        self.assertEqual(result["tasks"][0]["candidate_status"], "running")
        self.assertEqual(result["counts"]["failed_to_passed"], 0)
        self.assertIn("do not launch a duplicate worker", result["tasks"][0]["issues"][-1]["next_step"])
        self.assertEqual(before, self.snapshot())
        state = read_json(self.candidate / "swarm-state.json")["payload"]
        self.assertEqual(state["tasks"][0]["status"], "running")
        self.assertEqual(state["tasks"][0]["attempts"], 1)
        self.assertEqual(state["tasks"][0]["lease"]["expires_at"], 0)

    def test_quarantined_shared_resource_cannot_be_compared_as_current_success(self):
        self.specs["after"]["tasks"][1]["resource_id"] = self.specs["after"]["tasks"][0]["resource_id"]
        self.prepare()
        self.complete(self.baseline, "T1", "failed")
        self.complete(self.baseline, "T2", "passed")
        self.complete(self.candidate, "T2", "passed")
        with Library(self.library_path) as library:
            claim = swarm.claim(library, self.candidate, "uncertain-worker", "T1")
            receipt = self.receipt(self.candidate, claim, "inconclusive")
            receipt.update(steps=[], criteria=[], artifacts=[], reason="Synthetic fixture write outcome unknown.")
            swarm.record(library, self.candidate, receipt)
        before = self.snapshot()
        result = self.comparison()
        self.assertEqual(result["counts"]["not_compared"], 2)
        self.assertTrue(all(any(issue["code"] == "candidate_resource_quarantined" for issue in task["issues"])
                            for task in result["tasks"]))
        self.assertEqual(before, self.snapshot())

    def test_superseded_persona_does_not_reuse_old_success(self):
        self.complete_pair()
        self.doc["personas"][0]["behaviors"] = ["Review another synthetic decision path"]
        with Library(self.library_path) as library:
            library.import_profiles(self.doc)
        before = self.snapshot()
        result = self.comparison()
        self.assertEqual(result["counts"]["failed_to_passed"], 0)
        self.assertEqual(result["counts"]["not_compared"], 1)
        row = result["tasks"][0]
        self.assertTrue(any(issue["code"] == "historical_not_current" for issue in row["issues"]))
        self.assertEqual(row["criteria"], [])
        self.assertEqual(row["requirements"], [])
        self.assertEqual(before, self.snapshot())

    def test_retired_persona_blocks_comparison_without_exposing_old_payload(self):
        from uxresearch.canonical import EngineError
        self.complete_pair()
        with Library(self.library_path) as library:
            library.retire("sample", "PER-cautious", "Invented source withdrawal.")
        before = self.snapshot()
        with self.assertRaises(EngineError) as caught:
            self.comparison()
        self.assertEqual(caught.exception.issue["code"], "persona_retired")
        self.assertEqual(before, self.snapshot())

    def test_authoritative_capture_withdrawal_blocks_comparison_without_pruning(self):
        from uxresearch.canonical import EngineError
        from uxresearch.storage import Store
        research = self.gated_fixture()
        self.complete_pair()
        with Store(research) as store:
            bundle = store.committed("bundle.json")
            bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "withdrawn"
            store.publish("comparison-fixture-withdrawal", {"bundle.json": bundle}, invalidates_gate=True)
        before = self.snapshot()
        with self.assertRaises(EngineError) as caught:
            self.comparison()
        self.assertEqual(caught.exception.issue["code"], "persona_retention_due")
        self.assertEqual(before, self.snapshot())

    def test_changed_or_corrupt_inputs_block_without_partial_output(self):
        self.complete_pair()
        cases = [
            (self.root / "PRD.md", b"Changed requirement", "stale_prd"),
            (self.root / "before-build.txt", b"Changed build", "stale_build"),
            (self.baseline / "evidence/T1/1/log", b"PRIVATE_SENTINEL_not_for_output", "evidence_integrity"),
            (self.baseline / "swarm-state.json", b'{"schema_version":"wrong"}', "swarm_integrity"),
        ]
        for path, changed, code in cases:
            with self.subTest(code=code):
                original = path.read_bytes()
                atomic(path, changed)
                before = self.snapshot()
                result = self.command("compare", "--baseline", self.baseline, "--run", self.candidate,
                                      "--format", "json", expected=2, decode=False)
                self.assertEqual(result.stdout, "")
                self.assertEqual(json.loads(result.stderr)["issue"]["code"], code)
                self.assertNotIn("PRIVATE_SENTINEL", result.stderr)
                self.assertEqual(before, self.snapshot())
                atomic(path, original)

    def test_receipt_build_binding_must_match_its_verified_run(self):
        from uxresearch.canonical import EngineError
        self.complete_pair()
        self.change_state(self.baseline, lambda state: state["tasks"][0]["receipt"].update(build_sha256="a" * 64))
        before = self.snapshot()
        with self.assertRaises(EngineError) as caught:
            self.comparison()
        self.assertEqual(caught.exception.issue["code"], "comparison_receipt_binding")
        self.assertEqual(before, self.snapshot())

    def test_same_run_and_different_products_are_refused(self):
        from uxresearch.canonical import EngineError
        self.complete_pair()
        with self.assertRaises(EngineError) as caught:
            self.comparison(candidate=self.baseline)
        self.assertEqual(caught.exception.issue["code"], "comparison_same_run")
        other_doc = copy.deepcopy(self.doc)
        other_doc["product_id"] = "another-product"
        other_spec = copy.deepcopy(self.specs["after"])
        other_spec["product_id"] = "another-product"
        root = self.root / "other-product"
        with Library(self.library_path) as library:
            library.import_profiles(other_doc)
            swarm.create_plan(library, root, other_spec)
        with self.assertRaises(EngineError) as caught:
            self.comparison(candidate=root)
        self.assertEqual(caught.exception.issue["code"], "comparison_product_mismatch")

    def test_missing_library_and_run_are_not_created_by_comparison(self):
        result = self.command("compare", "--baseline", self.baseline, "--run", self.candidate,
                              expected=2, decode=False)
        self.assertEqual(json.loads(result.stderr)["issue"]["code"], "persona_missing")
        self.assertFalse(self.library_path.exists())
        self.assertFalse(self.baseline.exists())
        self.assertFalse(self.candidate.exists())
        self.prepare()
        missing = self.root / "does-not-exist"
        before = self.snapshot()
        result = self.command("compare", "--baseline", missing, "--run", self.candidate,
                              expected=2, decode=False)
        self.assertEqual(json.loads(result.stderr)["issue"]["code"], "comparison_run_missing")
        self.assertFalse(missing.exists())
        self.assertEqual(before, self.snapshot())

    def test_identical_build_bytes_are_labeled_repeated_runs_not_a_fix(self):
        self.specs["after"]["build"] = copy.deepcopy(self.specs["before"]["build"])
        self.complete_pair()
        result = self.comparison()
        self.assertFalse(result["build_changed"])
        self.assertFalse(result["measured_ux_improvement"])
        rendered = self.command("compare", "--baseline", self.baseline, "--run", self.candidate, decode=False)
        self.assertIn("repeated-run comparison, not evidence of a code fix", rendered.stdout)

    def test_comparison_carries_reopenable_evidence_references_without_lease_secrets(self):
        self.complete_pair()
        result = self.comparison()
        for row in result["tasks"]:
            for criterion in row["criteria"]:
                for side in ("baseline", "candidate"):
                    for evidence in criterion[side]["evidence"]:
                        path = Path(evidence["run_path"]) / evidence["path"]
                        self.assertEqual(byte_digest(path.read_bytes()), evidence["sha256"])
        encoded = json.dumps(result)
        for root in (self.baseline, self.candidate):
            state = read_json(root / "swarm-state.json")["payload"]
            for entry in state["tasks"]:
                self.assertNotIn(entry["lease"]["lease_token"], encoded)
        self.assertNotIn('"profile":', encoded)

    def test_uncommitted_capture_change_blocks_comparison_without_deleting_data(self):
        from uxresearch.canonical import EngineError
        research = self.gated_fixture()
        self.complete_pair()
        bundle = read_json(research / "bundle.json")
        bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "deleted"
        atomic(research / "bundle.json", canonical(bundle))
        before = self.snapshot()
        with self.assertRaises(EngineError) as caught:
            self.comparison()
        self.assertEqual(caught.exception.issue["code"], "retention_review_pending")
        self.assertEqual(before, self.snapshot())

    def test_due_persona_review_cannot_be_bypassed_by_comparison(self):
        from uxpersonas.comparison import compare
        from uxresearch.canonical import EngineError
        self.complete_pair()
        before = self.snapshot()
        with Library(self.library_path, clock=lambda: time.time() + 31 * 86400) as library:
            with self.assertRaises(EngineError) as caught:
                compare(library, self.baseline, self.candidate)
        self.assertEqual(caught.exception.issue["code"], "persona_review_due")
        self.assertEqual(before, self.snapshot())

    def test_duplicate_saved_task_ids_cannot_silently_drop_a_journey(self):
        from uxresearch.canonical import EngineError
        self.complete_pair()
        self.change_state(self.baseline, lambda state: state["tasks"].append(copy.deepcopy(state["tasks"][0])))
        before = self.snapshot()
        with self.assertRaises(EngineError) as caught:
            self.comparison()
        self.assertEqual(caught.exception.issue["code"], "comparison_task_identity")
        self.assertEqual(before, self.snapshot())
