"""Owned offline intake fixtures: no actual collection or user-effect claims."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import _paths
import test_persona_comparison as comparison_helpers
from uxresearch.canonical import canonical, digest
from uxresearch.storage import Store, atomic, read_json


ENTRYPOINT = comparison_helpers.ENTRYPOINT


class PersonaResearchIntakeTests(unittest.TestCase):
    setUp = comparison_helpers.PersonaComparisonTests.setUp
    command = comparison_helpers.PersonaComparisonTests.command
    write_input = comparison_helpers.PersonaComparisonTests.write_input
    research_command = comparison_helpers.PersonaComparisonTests.research_command
    gated_fixture = comparison_helpers.PersonaComparisonTests.gated_fixture
    receipt = comparison_helpers.PersonaComparisonTests.receipt

    def exported(self, research=None):
        research = research or self.gated_fixture()
        self.research_command(research, "persona-starter", "--bundle", research / "bundle.json",
                              "--gate", research / "gate.json")
        starter = read_json(research / "persona.hypotheses.starter.json")
        claim_ids = [starter["claim_cards"][0]["claim_id"]]
        hypotheses = dict(
            schema_version="ux-research-persona-hypotheses.v1",
            bundle_id=starter["bundle_id"],
            gate_bundle_input_sha256=starter["gate_bundle_input_sha256"],
            authored=True, personas=[],
        )
        for index, persona in enumerate(self.doc["personas"], 1):
            hypotheses["personas"].append(dict(
                persona_id="PER-source-" + str(index), label_ko=persona["label"],
                situation_ko="Invented offline return to saved selections.",
                motivation_claim_ids=claim_ids, authored=True,
                assumptions_ko=["Owned synthetic task model; not a real participant."],
                scenario=dict(
                    scenario_id="SC-source-" + str(index),
                    task_goal_ko=persona["goals"][0], context_ko=persona["contexts"][0],
                    concrete_data={"choice": "owned-option-" + str(index)},
                    device_ids=[], a11y_conditions=[],
                    expected_behavior_ko=persona["behaviors"][0],
                    expected_decision_ko="Inspect the saved choice before proceeding.",
                    likely_failure_ko="The saved choice may be absent after return.",
                    falsifying_product_test_ko="Observe whether a changed choice survives return.",
                    falsifying_interview_question_ko="Would this saved state be useful in this situation?",
                    priority="P2",
                ),
            ))
        self.hypotheses = hypotheses
        self.research_command(
            research, "export-personas", "--bundle", research / "bundle.json",
            "--gate", research / "gate.json",
            "--hypotheses", self.write_input("hypotheses.json", hypotheses),
            "--audience-id", "AU-owned-intake",
        )
        with Store(research) as store:
            packet = store.committed("qa-personas.json")
            packet_sha = store.state()["outputs"]["qa-personas.json"]["sha256"]
        mapping = dict(
            schema_version="ux-persona-research-mapping.v1", product_id="sample",
            context=copy.deepcopy(self.doc["context"]),
            source_export=dict(bundle_id=packet["bundle_id"], sha256=packet_sha),
            personas=[
                dict(source_persona_id=entry["persona_id"], persona_id=target["persona_id"],
                     requirement_ids=["local-results"])
                for entry, target in zip(hypotheses["personas"], self.doc["personas"])
            ],
        )
        self.mapping = mapping
        self.research = research
        self.packet = packet
        return self.write_input("intake-mapping.json", mapping)

    def process(self, mapping=None, *, library=None, research=None):
        path = self.write_input("request-" + str(id(mapping)) + ".json", mapping or self.mapping)
        return subprocess.run(
            [sys.executable, str(ENTRYPOINT), *(["personas"] if ENTRYPOINT.name == "remorsearch.py" else []),
             "import-research", "--library", str(library or self.library_path),
             "--research-run", str(research or self.research), "--input", str(path)],
            capture_output=True, text=True, timeout=20, cwd=self.root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )

    def library_bytes(self):
        path = self.library_path / "library.json"
        return path.read_bytes() if path.exists() else None

    def blocked(self, mapping=None, *, code=None, **kwargs):
        before = self.library_bytes()
        result = self.process(mapping, **kwargs)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        response = json.loads(result.stderr)
        self.assertEqual(response["result"], "blocked")
        if code:
            self.assertEqual(response["issue"]["code"], code)
        self.assertEqual(before, self.library_bytes())
        return response

    def reexport(self):
        self.research_command(
            self.research, "export-personas", "--bundle", self.research / "bundle.json",
            "--gate", self.research / "gate.json",
            "--hypotheses", self.write_input("revised-hypotheses.json", self.hypotheses),
            "--audience-id", "AU-owned-intake",
        )
        with Store(self.research) as store:
            packet = store.committed("qa-personas.json")
            self.mapping["source_export"] = dict(
                bundle_id=packet["bundle_id"], sha256=store.state()["outputs"]["qa-personas.json"]["sha256"])

    def rewrite_library(self, mutation):
        path = self.library_path / "library.json"
        state = read_json(path)["state"]
        for history in state["entries"].values():
            row = history[-1]
            mutation(row)
            if "research_scenarios" in row["profile"] and "research_export" in row["provenance"]:
                row["provenance"]["research_export"]["projection_sha256"] = digest(row["profile"]["research_scenarios"])
            body = {key: row[key] for key in ("product_id", "persona_id", "basis", "review_days",
                                             "profile", "context", "provenance")}
            row["profile_sha256"] = digest(body)
        atomic(path, canonical(dict(state=state, sha256=digest(state))))

    def test_cli_export_to_persistent_profiles_restart_and_existing_claim(self):
        mapping_path = self.exported()
        imported = self.command("import-research", "--research-run", self.research,
                                "--input", mapping_path)
        self.assertEqual(imported["schema_version"], "ux-persona-research-intake.v1")
        self.assertEqual(imported["basis"], "synthetic")
        self.assertEqual(len(imported["imported"]), 2)
        before = (self.library_path / "library.json").read_bytes()
        again = self.command("import-research", "--research-run", self.research, "--input", mapping_path)
        self.assertTrue(all(not row["changed"] for row in again["imported"]))
        self.assertEqual(before, (self.library_path / "library.json").read_bytes())
        for index, target in enumerate(self.doc["personas"]):
            saved = self.command("reuse", "--product", "sample", "--persona", target["persona_id"])
            self.assertEqual(saved["provenance"]["mode"], "gated_research")
            scenario = saved["profile"]["research_scenarios"][0]
            expected = self.hypotheses["personas"][index]["scenario"]
            for field in ("expected_behavior_ko", "expected_decision_ko", "likely_failure_ko",
                          "falsifying_product_test_ko", "falsifying_interview_question_ko",
                          "concrete_data", "device_ids", "a11y_conditions", "priority"):
                self.assertEqual(scenario[field], expected[field])
            self.assertEqual(scenario["basis"], "synthetic")
            self.assertEqual(scenario["epistemic_status"], "inferred")
            self.assertEqual(scenario["verification_status"], "unverified")
            self.assertIn("population_share", scenario["unknowns"])
            self.assertEqual(saved["profile"]["assumptions"],
                             self.hypotheses["personas"][index]["assumptions_ko"])
        self.command("plan", "--run", self.baseline,
                     "--input", self.write_input("plan.json", self.specs["before"]))
        claim = self.command("claim", "--run", self.baseline, "--worker", "owned-intake", "--task", "T1")
        self.assertTrue(claim["claimed"])
        self.assertEqual(claim["provenance_mode"], "gated_research")
        self.assertEqual(claim["profile"]["research_scenarios"][0]["verification_status"], "unverified")
        self.assertEqual(claim["profile"]["research_scenarios"][0]["expected_decision_ko"],
                         self.hypotheses["personas"][0]["scenario"]["expected_decision_ko"])
        draft = self.command("receipt-starter", "--run", self.baseline,
                             "--claim", self.write_input("current-claim.json", claim))
        self.assertTrue(all(row["status"] == "not_run" for row in draft["criteria"]))
        receipt = self.receipt(self.baseline, claim, "passed")
        self.command("record", "--run", self.baseline,
                     "--input", self.write_input("owned-observation.json", receipt))
        report = self.command("report", "--run", self.baseline)
        self.assertEqual(report["counts"]["passed"], 1)
        self.assertEqual(report["counts"]["pending"], 1)
        self.assertFalse(report["product_ready"])

    def test_sparse_observed_context_preserves_lead_only_without_inventing_support(self):
        from test_persona_evidence_admission import research_fixture
        research, bundle, gate, _ = research_fixture(self.root, relation="context")
        self.assertEqual(gate["claims"][0]["status"], "lead_only")
        self.exported(research)
        result = self.process()
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = self.command("reuse", "--product", "sample", "--persona", "PER-cautious")
        scenario = saved["profile"]["research_scenarios"][0]
        self.assertEqual(scenario["motivation"][0]["gate_status"], "lead_only")
        self.assertIsNone(scenario["motivation"][0]["confidence"])
        self.assertEqual(scenario["motivation"][0]["counting_evidence_ids"], [])
        self.assertTrue(scenario["motivation"][0]["context_evidence_ids"])
        self.assertEqual(saved["provenance"]["mode"], "gated_research")
        self.assertFalse(self.baseline.exists())

    def test_export_source_ids_require_explicit_compatible_aliases(self):
        self.exported()
        self.hypotheses["personas"][0]["persona_id"] = "PER-source:with-colon"
        self.mapping["personas"][0]["source_persona_id"] = "PER-source:with-colon"
        self.reexport()
        self.assertEqual(self.process().returncode, 0)
        saved = self.command("reuse", "--product", "sample", "--persona", "PER-cautious")
        self.assertEqual(saved["provenance"]["research_export"]["source_persona_id"], "PER-source:with-colon")
        bad = copy.deepcopy(self.mapping)
        bad["personas"][0]["persona_id"] = "PER-source:with-colon"
        self.blocked(bad, code="persona_input")

    def test_invalid_second_mapping_cannot_partially_import_the_first(self):
        self.exported()
        bad = copy.deepcopy(self.mapping)
        bad["personas"][1]["requirement_ids"] = ["undeclared"]
        self.blocked(bad, code="prd_citation")
        self.assertIsNone(self.library_bytes())

    def test_missing_extra_duplicate_and_unknown_mapping_fields_are_refused(self):
        self.exported()
        mutations = [
            lambda m: m.pop("context"),
            lambda m: m.update(mode="prd_hypothesis"),
            lambda m: m["personas"][1].update(persona_id=m["personas"][0]["persona_id"]),
            lambda m: m["personas"][1].update(source_persona_id=m["personas"][0]["source_persona_id"]),
            lambda m: m["personas"][0].update(source_persona_id="PER-absent"),
            lambda m: m["personas"][0].update(expected_revision=True),
            lambda m: m["personas"][0].update(claim_ids=["CLM-12345678"]),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                bad = copy.deepcopy(self.mapping)
                mutation(bad)
                self.blocked(bad)
                self.assertIsNone(self.library_bytes())

    def test_wrong_packet_fingerprint_or_export_id_is_not_current(self):
        self.exported()
        for key, value in (("sha256", "0" * 64), ("bundle_id", "QAB-" + "0" * 24)):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.mapping)
                bad["source_export"][key] = value
                self.blocked(bad, code="stale_persona_export")

    def test_newer_export_blocks_an_old_mapping_then_explicit_revision_update_preserves_history(self):
        self.exported()
        self.assertEqual(self.process().returncode, 0)
        old_mapping = copy.deepcopy(self.mapping)
        before = self.library_bytes()
        self.hypotheses["personas"][0]["scenario"]["expected_decision_ko"] = "Read the preserved choice before choosing a new one."
        self.reexport()
        self.blocked(old_mapping, code="stale_persona_export")
        self.blocked(code="research_import_conflict")
        self.assertEqual(before, self.library_bytes())
        for row in self.mapping["personas"]:
            row["expected_revision"] = 1
        updated = self.process()
        self.assertEqual(updated.returncode, 0, updated.stderr)
        self.assertTrue(all(row["revision"] == 2 for row in json.loads(updated.stdout)["imported"]))
        state = read_json(self.library_path / "library.json")["state"]
        self.assertTrue(all(len(history) == 2 for history in state["entries"].values()))
        after = self.library_bytes()
        self.assertTrue(all(not row["changed"] for row in json.loads(self.process().stdout)["imported"]))
        self.assertEqual(after, self.library_bytes())

    def test_changed_prd_and_mismatched_excerpt_cannot_create_profiles(self):
        self.exported()
        bad = copy.deepcopy(self.mapping)
        bad["context"]["requirements"][0]["excerpt"] = "Not present in the owned PRD."
        self.blocked(bad, code="prd_citation")
        atomic(Path(self.mapping["context"]["prd_path"]), b"Changed owned requirement.")
        self.blocked(code="stale_prd")

    def test_failed_latest_export_blocks_prior_good_snapshot(self):
        self.exported()
        self.assertEqual(self.process().returncode, 0)
        from uxresearch.cli import main
        from test_persona_evidence_admission import command
        bad = copy.deepcopy(self.hypotheses)
        bad["authored"] = False
        code, result = command(main, [
            "export-personas", "--run", self.research, "--bundle", self.research / "bundle.json",
            "--gate", self.research / "gate.json",
            "--hypotheses", self.write_input("bad-hypotheses.json", bad), "--audience-id", "AU-owned-intake",
        ])
        self.assertNotEqual(code, 0, result)
        self.blocked(code="failed_export")

    def test_authoritative_capture_withdrawal_does_not_import_or_delete_existing_profiles(self):
        self.exported()
        self.assertEqual(self.process().returncode, 0)
        with Store(self.research) as store:
            bundle = store.committed("bundle.json")
            bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "withdrawn"
            store.publish("owned-intake-withdrawal", {"bundle.json": bundle}, invalidates_gate=True)
        self.blocked()
        self.assertIn(b"research_scenarios", self.library_bytes())

    def test_uncommitted_withdrawal_blocks_without_pruning(self):
        self.exported()
        self.assertEqual(self.process().returncode, 0)
        bundle = read_json(self.research / "bundle.json")
        bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "deleted"
        atomic(self.research / "bundle.json", canonical(bundle))
        self.blocked()
        self.assertIn(b"research_scenarios", self.library_bytes())

    def test_expired_research_cannot_import(self):
        import time
        from datetime import datetime, timezone
        from unittest import mock
        from uxpersonas.library import Library
        from uxpersonas.research_intake import import_research
        from uxresearch.canonical import EngineError
        from uxresearch.ledger import Run
        from uxresearch.merge import import_identity
        deadline = time.time() + 3600
        retention_until = datetime.fromtimestamp(deadline, timezone.utc).isoformat().replace("+00:00", "Z")
        original_build = comparison_helpers.factory.fixture.build
        def expiring_fixture(*args, **kwargs):
            run = original_build(*args, **kwargs)
            imports = read_json(run / "sanitized-imports.json")
            item = imports["imports"][0]
            item["retention_until"] = retention_until
            item["import_id"] = import_identity(item)
            returned = read_json(run / "returns/editors.json")
            returned["sources"][0]["retention_until"] = retention_until
            returned["sources"][0]["provenance"]["import_id"] = item["import_id"]
            returned["excerpts"][0]["capture_ref"] = item["import_id"]
            atomic(run / "sanitized-imports.json", canonical(imports))
            atomic(run / "returns/editors.json", canonical(returned))
            return run
        with mock.patch.object(comparison_helpers.factory.fixture, "build", side_effect=expiring_fixture):
            self.exported()
        self.assertIsNotNone(read_json(self.research / "gate.json")["valid_until"])
        with Library(self.library_path) as library:
            with mock.patch("uxpersonas.research_intake.Run",
                            side_effect=lambda path: Run(path, clock=lambda: deadline + 2)):
                with self.assertRaises(EngineError) as caught:
                    import_research(library, self.research, self.mapping)
        self.assertEqual(caught.exception.issue["code"], "expired")
        self.assertIsNone(self.library_bytes())

    def test_retired_destination_is_not_reactivated_by_the_same_export(self):
        self.exported()
        self.assertEqual(self.process().returncode, 0)
        self.command("retire", "--product", "sample", "--persona", "PER-cautious", "--reason", "Owned withdrawal.")
        self.blocked(code="persona_retired")

    def test_private_permissions_and_symlinks_are_checked_without_changing_them(self):
        self.exported()
        self.library_path.mkdir(mode=0o755)
        self.library_path.chmod(0o755)
        self.blocked(code="unsafe_mode")
        self.assertEqual(self.library_path.stat().st_mode & 0o777, 0o755)
        self.library_path.chmod(0o700)
        link = self.root / "research-link"
        link.symlink_to(self.research)
        self.blocked(research=link, code="unsafe_path")
        lock = self.research / "engine.lock"
        lock.chmod(0o644)
        self.blocked(code="unsafe_mode")
        self.assertEqual(lock.stat().st_mode & 0o777, 0o644)

    def test_packet_copy_without_authoritative_run_cannot_be_imported(self):
        self.exported()
        copied = self.root / "copied-packet"
        copied.mkdir(mode=0o700)
        atomic(copied / "qa-personas.json", canonical(self.packet))
        self.blocked(research=copied)
        self.assertIsNone(self.library_bytes())

    def test_strict_projection_validation_rejects_tampering_even_with_recomputed_fingerprints(self):
        self.exported()
        self.assertEqual(self.process().returncode, 0)
        original = self.library_bytes()
        mutations = [
            lambda r: r["profile"]["research_scenarios"][0].update(verification_status="verified"),
            lambda r: r["profile"]["research_scenarios"][0].update(actions=["Invented action"]),
            lambda r: r["profile"]["research_scenarios"][0].update(unknowns=[]),
            lambda r: r["profile"]["research_scenarios"][0].update(expected_decision_ko="Replaced decision"),
            lambda r: r["profile"].update(assumptions=[]),
            lambda r: r["provenance"].update(mode="prd_hypothesis"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                atomic(self.library_path / "library.json", original)
                self.rewrite_library(mutate)
                result = self.command("reuse", "--product", "sample", "--persona", "PER-cautious",
                                      expected=2, decode=False)
                self.assertEqual(json.loads(result.stderr)["result"], "blocked")

    def test_concurrent_identical_requests_publish_one_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        self.exported()
        requests = [copy.deepcopy(self.mapping), copy.deepcopy(self.mapping)]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.process, requests))
        self.assertTrue(all(result.returncode == 0 for result in results), [r.stderr for r in results])
        self.assertEqual(sum(any(row["changed"] for row in json.loads(r.stdout)["imported"]) for r in results), 1)
        state = read_json(self.library_path / "library.json")["state"]
        self.assertEqual(len(state["entries"]), 2)
        self.assertTrue(all(len(history) == 1 for history in state["entries"].values()))

    def test_concurrent_changed_requests_do_not_overwrite_the_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        self.exported()
        requests = [copy.deepcopy(self.mapping), copy.deepcopy(self.mapping)]
        requests[1]["review_days"] = 7
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.process, requests))
        self.assertEqual(sum(result.returncode == 0 for result in results), 1, [r.stdout + r.stderr for r in results])
        loser = next(result for result in results if result.returncode)
        self.assertEqual(json.loads(loser.stderr)["issue"]["code"], "research_import_conflict")
        state = read_json(self.library_path / "library.json")["state"]
        self.assertTrue(all(len(history) == 1 for history in state["entries"].values()))
        self.assertEqual(len({history[0]["review_days"] for history in state["entries"].values()}), 1)

    def test_failure_before_atomic_save_and_lost_ack_are_restart_safe(self):
        from unittest import mock
        from uxpersonas.library import Library
        from uxpersonas.research_intake import import_research
        self.exported()
        with Library(self.library_path) as library:
            with mock.patch.object(library, "_save", side_effect=OSError("Owned before-save failure")):
                with self.assertRaises(OSError):
                    import_research(library, self.research, self.mapping)
        self.assertIsNone(self.library_bytes())
        with Library(self.library_path) as library:
            original_save = library._save
            def lost_ack(state):
                original_save(state)
                raise OSError("Owned lost acknowledgement")
            with mock.patch.object(library, "_save", side_effect=lost_ack):
                with self.assertRaises(OSError):
                    import_research(library, self.research, self.mapping)
        committed = self.library_bytes()
        result = self.process()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(not row["changed"] for row in json.loads(result.stdout)["imported"]))
        self.assertEqual(committed, self.library_bytes())

    def test_final_recheck_detects_changed_research_before_library_publication(self):
        from unittest import mock
        from uxpersonas.library import Library
        from uxpersonas.research_intake import import_research
        from uxresearch.canonical import EngineError
        self.exported()
        with Library(self.library_path) as library:
            original_commit = library._commit_profiles
            def change_before_commit(*args, **kwargs):
                bundle = read_json(self.research / "bundle.json")
                bundle["records"]["claims"][0]["statement"] += " Changed owned input."
                atomic(self.research / "bundle.json", canonical(bundle))
                return original_commit(*args, **kwargs)
            with mock.patch.object(library, "_commit_profiles", side_effect=change_before_commit):
                with self.assertRaises(EngineError):
                    import_research(library, self.research, self.mapping)
        self.assertIsNone(self.library_bytes())

    def test_matching_research_lock_is_required_by_the_already_locked_validator(self):
        from uxpersonas.library import _research_binding_locked
        from uxresearch.canonical import EngineError
        from uxresearch.ledger import Run
        self.exported()
        other = self.root / "other-lock"
        other.mkdir(mode=0o700)
        refs = dict(run=str(self.research), bundle=str(self.research / "bundle.json"), gate=str(self.research / "gate.json"))
        with Store(other) as store:
            with self.assertRaises(EngineError) as caught:
                _research_binding_locked(refs, self.hypotheses["personas"][0]["motivation_claim_ids"],
                                         Run(self.research), store)
        self.assertEqual(caught.exception.issue["code"], "persona_lock")

    def test_busy_research_is_not_bypassed_or_partially_saved(self):
        self.exported()
        with Store(self.research):
            self.blocked(code="lock_busy")
        self.assertIsNone(self.library_bytes())

    def test_idempotent_import_cannot_claim_success_for_a_corrupt_existing_body(self):
        self.exported()
        self.assertEqual(self.process().returncode, 0)
        path = self.library_path / "library.json"
        state = read_json(path)["state"]
        state["entries"]["sample/PER-cautious"][-1]["profile"]["label"] = "Changed owned payload."
        # The envelope can be well formed while the record's original fingerprint
        # remains inconsistent. An unchanged-input retry must still detect it.
        atomic(path, canonical(dict(state=state, sha256=digest(state))))
        self.blocked(code="persona_integrity")

    def test_closed_research_preserves_restart_reuse_and_exact_reimport(self):
        self.exported()
        self.assertEqual(self.process().returncode, 0)
        before = self.library_bytes()
        self.research_command(self.research, "close")
        saved = self.command("reuse", "--product", "sample", "--persona", "PER-cautious")
        self.assertEqual(saved["provenance"]["mode"], "gated_research")
        self.assertEqual(saved["profile"]["research_scenarios"][0]["verification_status"], "unverified")
        self.assertEqual(before, self.library_bytes())
        repeated = self.process()
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertTrue(all(not row["changed"] for row in json.loads(repeated.stdout)["imported"]))
        self.assertEqual(before, self.library_bytes())

    def test_review_deadline_crossing_does_not_implicitly_renew_an_identical_import(self):
        from unittest import mock
        from uxpersonas.library import Library
        from uxpersonas.research_intake import import_research
        from uxresearch.canonical import EngineError
        self.exported()
        mapping = copy.deepcopy(self.mapping)
        mapping["personas"] = mapping["personas"][:1]
        self.assertEqual(self.process(mapping).returncode, 0)
        key = "sample/" + mapping["personas"][0]["persona_id"]
        original = read_json(self.library_path / "library.json")["state"]["entries"][key][-1]
        deadline = original["review_after"]
        before = self.library_bytes()
        # The same request begins before review is due and crosses the deadline
        # before publication. It must not gain an unrequested 30-day renewal.
        crossing_clock = mock.Mock(side_effect=[deadline - 0.001, deadline + 0.001])
        with Library(self.library_path, clock=crossing_clock) as library:
            result = import_research(library, self.research, mapping)
        self.assertEqual([(row["revision"], row["changed"]) for row in result["imported"]],
                         [(1, False)])
        self.assertEqual(before, self.library_bytes())
        # An already-due request still needs explicit acknowledgment of the
        # current revision; freezing the batch clock must not bypass review.
        expired_at = deadline + 0.001
        with Library(self.library_path, clock=lambda: expired_at) as library:
            with self.assertRaises(EngineError) as caught:
                import_research(library, self.research, mapping)
        self.assertEqual(caught.exception.issue["code"], "research_import_conflict")
        self.assertEqual(before, self.library_bytes())
        mapping["personas"][0]["expected_revision"] = 1
        with Library(self.library_path, clock=lambda: expired_at) as library:
            reviewed = import_research(library, self.research, mapping)
        self.assertEqual([(row["revision"], row["changed"]) for row in reviewed["imported"]],
                         [(2, True)])
        history = read_json(self.library_path / "library.json")["state"]["entries"][key]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0], original)
        self.assertEqual(history[1]["profile_sha256"], original["profile_sha256"])
        self.assertEqual(history[1]["review_after"], expired_at + 30 * 86400)


if __name__ == "__main__":
    unittest.main()
