"""Offline persistence/swarm regression for capture-level retention.

All research inputs are invented by the shipped fixture. The real merge/gate,
Library, Store and swarm code run without gate/library mocks. A passing local
gate is not evidence of public research, permission, real people or UX benefit.

Only TemporaryDirectory data is written at runtime. Store.publish models an
authoritative local retention update; no external source, worker, browser,
existing research run or managed-work ledger is contacted.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

import _paths
import engine_release_factory as fixture_factory
from uxpersonas import swarm
from uxpersonas.cli import main as persona_main
from uxpersonas.library import Library
from uxresearch.canonical import EngineError, byte_digest, canonical, digest
from uxresearch.cli import main as research_main
from uxresearch.ledger import Run
from uxresearch.personas import claim_cards
from uxresearch.storage import Store, atomic, read_json


class CaptureRetentionPersistenceRegressionTests(unittest.TestCase):
    """A clean result must not conceal retained derivatives of unsafe captures."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="remorsearch-retention-regression-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.now = time.time()
        self.research = fixture_factory.fixture.build(
            self.root / "research", clock=lambda: self.now
        )
        self.library_path = self.root / "personas"
        self.run_path = self.root / "swarm"

        self.research_command(
            "merge",
            "--manifest", self.research / "axes.json",
            "--search-ledger", self.research / "search-ledger.jsonl",
            "--imports", self.research / "sanitized-imports.json",
            "--returns", self.research / "returns/editors.json",
        )
        bundle = read_json(self.research / "bundle.json")
        bundle["records"]["sources"][0]["summary"] = (
            "Invented offline input for the capture-retention regression."
        )
        stamp = Run(self.research, clock=lambda: self.now).now_iso()
        for records in bundle["records"].values():
            for record in records:
                for field in ("summary", "statement"):
                    if field in record:
                        bundle["research"]["summary_attestations"].append({
                            "record_id": record["id"],
                            "field": field,
                            "content_sha256": digest(record[field]),
                            "reviewed_by": "self",
                            "reviewed_at": stamp,
                        })
        atomic(self.research / "bundle.json", canonical(bundle))
        self.research_command("gate", "--bundle", self.research / "bundle.json", "--write-bundle")
        self.bundle = read_json(self.research / "bundle.json")
        self.gate = read_json(self.research / "gate.json")
        self.assertEqual(self.gate["result"], "pass")
        cards = claim_cards(self.bundle, self.gate)
        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0]["exportable"])
        self.claim_id = cards[0]["claim_id"]

        prd = self.root / "product-prd.md"
        atomic(prd, b"# Offline test product\nRetain the selected input after interruption.\n")
        profile = {
            "persona_id": "PER-interrupted",
            "label": "Invented interrupted returner",
            "goals": ["Resume the unfinished synthetic task"],
            "behaviors": ["Check the retained input before continuing"],
            "contexts": ["Return after an interruption"],
            "assumptions": ["Invented fixture behavior, not a real participant"],
            "unknowns": ["Real-world frequency and benefit remain unknown"],
            "requirement_ids": ["retain-input"],
            "claim_ids": [self.claim_id],
        }
        document = {
            "schema_version": "ux-persona-library-input.v1",
            "product_id": "offline-regression",
            "mode": "gated_research",
            "context": {
                "prd_path": str(prd),
                "prd_sha256": byte_digest(prd.read_bytes()),
                "requirements": [{
                    "id": "retain-input",
                    "source_anchor": "Offline test product",
                    "excerpt": "Retain the selected input after interruption.",
                }],
            },
            "research": {
                "run": str(self.research),
                "bundle": str(self.research / "bundle.json"),
                "gate": str(self.research / "gate.json"),
            },
            "personas": [profile],
        }
        with Library(self.library_path) as library:
            first = library.import_profiles(document)
            self.assertEqual(first["imported"][0]["revision"], 1)
        revised = copy.deepcopy(document)
        revised["personas"][0]["behaviors"] = [
            "Inspect the retained input and the next available action"
        ]
        with Library(self.library_path) as library:
            second = library.import_profiles(revised)
            self.assertEqual(second["imported"][0]["revision"], 2)
            self.assertEqual(library.list()["personas"][0]["revisions"], 2)

        build = self.root / "build.txt"
        atomic(build, b"Invented offline build identity; no application is launched.\n")
        specification = {
            "schema_version": swarm.SCHEMA,
            "product_id": "offline-regression",
            "build": {
                "id": "offline-build",
                "artifact_path": str(build),
                "sha256": byte_digest(build.read_bytes()),
            },
            "max_parallel": 1,
            "lease_seconds": 30,
            "max_attempts": 1,
            "tasks": [{
                "id": "TASK-return",
                "persona_id": "PER-interrupted",
                "requirement_ids": ["retain-input"],
                "goal": "Inspect the retained synthetic selection after interruption",
                "starting_state": "A task-owned synthetic session with a saved selection",
                "actions": ["Inspect the saved selection", "Check the next action"],
                "decisions": ["Continue only when the expected selection is retained"],
                "success_criteria": ["The synthetic selection matches its starting value"],
                "recovery_criteria": ["The selection remains available after interruption"],
                "data_namespace": "offline-regression-task",
                "resource_id": "offline-regression-resource",
                "side_effects": "read_only",
                "stop_conditions": ["Stop at unexpected real data or lease expiry"],
                "requirement_coverage": [{
                    "requirement_id": "retain-input",
                    "obligations": [{
                        "id": "retained-after-return",
                        "description": "Retain the selected input after interruption",
                        "criterion_refs": [
                            {"kind": "success", "index": 0},
                            {"kind": "recovery", "index": 0},
                        ],
                        "exclusion_reason": None,
                    }],
                }],
            }],
        }
        with Library(self.library_path) as library:
            swarm.create_plan(library, self.run_path, specification)

    def research_command(self, name, *arguments):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                code = research_main(
                    [name, "--run", str(self.research), *map(str, arguments)],
                    clock=lambda: self.now,
                )
        self.assertEqual(code, 0, output.getvalue() + errors.getvalue())
        return json.loads(output.getvalue())

    def committed_update(self, bundle):
        # This is an explicit offline authoritative transition, not a mirror edit.
        with Store(self.research) as store:
            store.publish(
                "offline-capture-retention-regression",
                {"bundle.json": bundle},
                invalidates_gate=True,
            )
            self.assertEqual(store.committed("bundle.json"), bundle)
        self.assertEqual(read_json(self.research / "bundle.json"), bundle)

    def prune_cli(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                code = persona_main(["prune", "--library", str(self.library_path)])
        self.assertEqual(errors.getvalue(), "")
        return code, json.loads(output.getvalue())

    def persisted_history(self):
        # Reopen the on-disk state rather than inspecting an in-memory Library.
        envelope = read_json(self.library_path / "library.json", private=True)
        return envelope["state"]["entries"]["offline-regression/PER-interrupted"]

    def assert_assignment_blocked(self):
        state_path = self.run_path / "swarm-state.json"
        before = state_path.read_bytes()
        with Library(self.library_path) as library:
            self.assertFalse(library.list()["personas"][0]["reusable"])
            with self.assertRaises(EngineError) as caught:
                swarm.claim(library, self.run_path, "offline-worker")
        self.assertEqual(state_path.read_bytes(), before)
        return caught.exception.issue["code"]

    def assert_cleanup_removed_both_revisions(self):
        code, result = self.prune_cli()
        self.assertEqual(code, 0)
        self.assertEqual(result["result"], "pass")
        self.assertTrue(result["library_cleanup_complete"])
        self.assertEqual(len(result["retired"]), 1)
        history = self.persisted_history()
        self.assertEqual([row["revision"] for row in history], [1, 2])
        self.assertTrue(all(row["status"] == "retired" for row in history))
        self.assertTrue(all("profile" not in row for row in history))
        self.assertEqual(self.assert_assignment_blocked(), "persona_retired")

    def test_retained_capture_survives_reopen_and_can_be_assigned(self):
        before = (self.library_path / "library.json").read_bytes()
        with Library(self.library_path) as library:
            record = library.get("offline-regression", "PER-interrupted", revision=2)
            self.assertEqual(record["provenance"]["mode"], "gated_research")
            claim = swarm.claim(library, self.run_path, "offline-worker")
            self.assertTrue(claim["claimed"])
            self.assertEqual(claim["binding"]["revision"], 2)
            self.assertEqual(claim["research_claims"][0]["claim_id"], self.claim_id)
            report = swarm.report(library, self.run_path)
            self.assertEqual(report["counts"]["running"], 1)
            self.assertEqual(report["counts"]["passed"], 0)
            self.assertFalse(report["product_ready"])
        self.assertEqual((self.library_path / "library.json").read_bytes(), before)

    def test_pending_capture_withdrawal_blocks_without_deleting(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "withdrawn"
        atomic(self.research / "bundle.json", canonical(bundle))
        before = (self.library_path / "library.json").read_bytes()
        self.assertEqual(self.assert_assignment_blocked(), "retention_review_pending")
        code, result = self.prune_cli()
        self.assertEqual(code, 1)
        self.assertEqual(result["result"], "blocked")
        self.assertFalse(result["library_cleanup_complete"])
        self.assertEqual(result["retired"], [])
        self.assertEqual(result["blockers"][0]["code"], "retention_review_pending")
        self.assertEqual((self.library_path / "library.json").read_bytes(), before)

    def test_confirmed_source_withdrawal_removes_both_revisions(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["records"]["sources"][0]["retention_status"] = "withdrawn"
        self.committed_update(bundle)
        self.assert_cleanup_removed_both_revisions()

    def test_confirmed_capture_expiry_removes_both_revisions(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_until"] = (
            "2000-01-01T00:00:00Z"
        )
        self.committed_update(bundle)
        self.assert_cleanup_removed_both_revisions()

    def assert_terminal_capture_not_false_clean(self, status):
        bundle = copy.deepcopy(self.bundle)
        source = bundle["records"]["sources"][0]
        self.assertEqual(source["retention_status"], "retained")
        source["captures"][0]["metadata"]["retention_status"] = status
        self.committed_update(bundle)
        # The ordinary claim-card boundary already recognizes this unsafe capture.
        self.assertFalse(claim_cards(bundle, self.gate)[0]["exportable"])
        assignment_blocker = self.assert_assignment_blocked()
        code, result = self.prune_cli()
        remaining = [
            row["revision"] for row in self.persisted_history() if "profile" in row
        ]
        diagnostic = {
            "capture_status": status,
            "source_status": source["retention_status"],
            "assignment_blocker": assignment_blocker,
            "cli_exit": code,
            "cleanup_result": result["result"],
            "library_cleanup_complete": result["library_cleanup_complete"],
            "retired_count": len(result["retired"]),
            "retained_profile_revisions": remaining,
        }
        self.assertFalse(
            result["library_cleanup_complete"] and bool(remaining),
            "Unsafe committed capture left derived profiles but reported clean: "
            + json.dumps(diagnostic, sort_keys=True),
        )
        # A conservative blocker is acceptable if safe removal cannot be proved.
        if remaining:
            self.assertNotEqual(code, 0)
            self.assertIn(result["result"], {"blocked", "partial"})
            self.assertTrue(result["blockers"])
        else:
            self.assertEqual(code, 0)
            self.assertTrue(result["library_cleanup_complete"])

    def test_confirmed_capture_withdrawn_cannot_report_false_cleanup(self):
        self.assert_terminal_capture_not_false_clean("withdrawn")

    def test_confirmed_capture_deleted_cannot_report_false_cleanup(self):
        self.assert_terminal_capture_not_false_clean("deleted")

    def test_confirmed_capture_redacted_cannot_report_false_cleanup(self):
        self.assert_terminal_capture_not_false_clean("redacted")


if __name__ == "__main__":
    unittest.main()

