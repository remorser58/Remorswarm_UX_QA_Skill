from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import _paths
from uxpersonas.library import Library, digest_bytes
from uxpersonas.cli import main
from uxresearch.canonical import EngineError, canonical
from uxresearch.storage import atomic


def profile_input(root):
    prd = root / "PRD.md"
    prd.write_text("# Product\nKeep results on device.\nAllow cancellation and recovery.\n")
    return {
        "schema_version": "ux-persona-library-input.v1",
        "product_id": "sample", "mode": "prd_hypothesis",
        "context": {"prd_path": str(prd), "prd_sha256": digest_bytes(prd.read_bytes()),
                    "requirements": [{"id": "local-results", "source_anchor": "Product",
                                      "excerpt": "Keep results on device."}]},
        "personas": [{"persona_id": "PER-cautious", "label": "Local data control",
                      "goals": ["Inspect local results"], "behaviors": ["Check before proceeding"],
                      "contexts": ["Interrupted return"], "assumptions": ["Synthetic fixture user"],
                      "unknowns": ["Real user prevalence"], "requirement_ids": ["local-results"], "claim_ids": []}],
    }


class PersonaLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "library"
        self.doc = profile_input(self.root)
        self.now = 1000.0

    def tearDown(self):
        self.temp.cleanup()

    def library(self):
        return Library(self.path, clock=lambda: self.now)

    def test_import_reuse_and_idempotence(self):
        with self.library() as lib:
            result = lib.import_profiles(self.doc)
            self.assertTrue(result["imported"][0]["changed"])
            self.assertEqual(lib.get("sample", "PER-cautious")["basis"], "synthetic")
            self.assertFalse(lib.import_profiles(self.doc)["imported"][0]["changed"])
            self.assertTrue(lib.list()["personas"][0]["reusable"])
        self.assertEqual((self.path / "library.json").stat().st_mode & 0o777, 0o600)

    def test_revision_history_and_old_revision_cannot_execute(self):
        with self.library() as lib:
            lib.import_profiles(self.doc)
            updated = copy.deepcopy(self.doc)
            updated["personas"][0]["behaviors"] = ["Read the local status before continuing"]
            lib.import_profiles(updated)
            self.assertEqual(lib.get("sample", "PER-cautious")["revision"], 2)
            with self.assertRaises(EngineError):
                lib.get("sample", "PER-cautious", 1)

    def test_expiry_requires_review_and_new_revision(self):
        with self.library() as lib:
            lib.import_profiles(self.doc)
            self.now += 31 * 86400
            with self.assertRaises(EngineError):
                lib.get("sample", "PER-cautious")
            lib.import_profiles(self.doc)
            self.assertEqual(lib.get("sample", "PER-cautious")["revision"], 2)

    def test_stricter_review_interval_creates_revision(self):
        with self.library() as lib:
            lib.import_profiles(self.doc)
            self.doc["review_days"] = 1
            self.assertTrue(lib.import_profiles(self.doc)["imported"][0]["changed"])
            record = lib.get("sample", "PER-cautious")
            self.assertEqual(record["revision"], 2)
            self.assertEqual(record["review_after"], self.now + 86400)

    def test_prune_expired_research_removes_derivatives(self):
        self.doc.update(mode="gated_research", research={"run": str(self.root), "bundle": "bundle.json", "gate": "gate.json"})
        self.doc["personas"][0]["claim_ids"] = ["CLM-12345678"]
        binding = {"run": str(self.root), "bundle": "bundle.json", "gate": "gate.json", "valid_until": "1970-01-01T00:30:00Z"}
        with patch("uxpersonas.library._research_binding", return_value=binding):
            with self.library() as lib:
                lib.import_profiles(self.doc)
                self.assertTrue(lib.list()["personas"][0]["reusable"])
                self.now = 2000.0
                with self.assertRaises(EngineError):
                    lib.get("sample", "PER-cautious")
                self.assertEqual(len(lib.prune()["retired"]), 1)
        self.assertNotIn("Local data control", (self.path / "library.json").read_text())

    def test_prune_transient_failure_preserves_profile(self):
        with self.library() as lib:
            lib.import_profiles(self.doc)
            with patch("uxpersonas.library.retention_reason", side_effect=EngineError("io", "unavailable")):
                self.assertEqual(len(lib.prune()["blockers"]), 1)
            self.assertEqual(lib.get("sample", "PER-cautious")["profile"]["label"], "Local data control")

    def test_authoritative_tombstone_triggers_retention(self):
        from uxpersonas.library import retention_reason
        record = {"provenance": {"mode": "gated_research", "research": {
            "run": str(self.root), "claims": [{"source_ids": ["SRC-example"]}]}}}
        with patch("uxpersonas.library.Store.committed", return_value={"records": {"sources": [
            {"id": "SRC-example", "research_tombstone": {"reason": "withdrawn"}}]}}):
            self.assertIn("withdrawn", retention_reason(record, self.now))

    def test_prd_change_blocks_reuse(self):
        with self.library() as lib:
            lib.import_profiles(self.doc)
            Path(self.doc["context"]["prd_path"]).write_text("changed")
            with self.assertRaises(EngineError):
                lib.get("sample", "PER-cautious")
            self.assertFalse(lib.list()["personas"][0]["reusable"])

    def test_citation_must_be_in_actual_prd(self):
        self.doc["context"]["requirements"][0]["excerpt"] = "Invented requirement"
        with self.library() as lib, self.assertRaises(EngineError):
            lib.import_profiles(self.doc)

    def test_unknown_requirement_and_extra_demographic_fields_refused(self):
        with self.library() as lib:
            for mutation in (
                {"requirement_ids": ["invented"]},
                {"age": 27},
                {"label": "Contact test@example.com"},
                {"claim_ids": ["CLM-12345678"]},
                {"assumptions": []},
            ):
                bad = copy.deepcopy(self.doc)
                bad["personas"][0].update(mutation)
                with self.subTest(mutation=mutation), self.assertRaises(EngineError):
                    lib.import_profiles(bad)
            self.assertEqual(lib.list()["personas"], [])

    def test_import_is_transactional(self):
        self.doc["personas"].append({**self.doc["personas"][0], "persona_id": "PER-other", "label": ""})
        with self.library() as lib, self.assertRaises(EngineError):
            lib.import_profiles(self.doc)
        with self.library() as lib:
            self.assertEqual(lib.list()["personas"], [])

    def test_retire_removes_all_derived_profile_payloads(self):
        with self.library() as lib:
            lib.import_profiles(self.doc)
            self.doc["personas"][0]["label"] = "Second safe label"
            lib.import_profiles(self.doc)
            lib.retire("sample", "PER-cautious", "Source withdrawn")
            with self.assertRaises(EngineError):
                lib.get("sample", "PER-cautious")
            self.assertFalse(lib.list()["personas"][0]["reusable"])
        raw = (self.path / "library.json").read_text()
        self.assertNotIn("Local data control", raw)
        self.assertNotIn("Second safe label", raw)
        self.assertNotIn("Keep results on device", raw)

    def test_cross_product_does_not_auto_reuse(self):
        with self.library() as lib:
            lib.import_profiles(self.doc)
            with self.assertRaises(EngineError):
                lib.get("different-product", "PER-cautious")

    def test_identifiers_are_compatible_with_swarm(self):
        with self.library() as lib:
            for invalid in ("PER-demo:1", "PER-" + "a" * 61):
                doc = copy.deepcopy(self.doc)
                doc["personas"][0]["persona_id"] = invalid
                with self.subTest(invalid=invalid), self.assertRaises(EngineError):
                    lib.import_profiles(doc)

    def test_symlink_and_skill_state_rejected(self):
        link = self.root / "linked"
        link.symlink_to(self.root / "elsewhere")
        with self.assertRaises(EngineError):
            Library(link)
        with self.assertRaises(EngineError):
            Library(_paths.SKILL / ".ux-personas")

    def test_state_tampering_refused(self):
        with self.library() as lib:
            lib.import_profiles(self.doc)
        state_path = self.path / "library.json"
        state = json.loads(state_path.read_text())
        state["state"]["entries"]["sample/PER-cautious"][0]["profile"]["label"] = "changed"
        atomic(state_path, canonical(state))
        with self.library() as lib, self.assertRaises(EngineError):
            lib.list()

    def test_concurrent_imports_preserve_both_entries(self):
        def add(index):
            doc = copy.deepcopy(self.doc)
            doc["personas"][0]["persona_id"] = f"PER-persona-{index}"
            with self.library() as lib:
                lib.import_profiles(doc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(add, (1, 2)))
        with self.library() as lib:
            self.assertEqual(len(lib.list()["personas"]), 2)

    def test_research_change_or_withdrawal_blocks_reuse(self):
        self.doc.update(mode="gated_research", research={"run": str(self.root), "bundle": "bundle.json", "gate": "gate.json"})
        self.doc["personas"][0]["claim_ids"] = ["CLM-12345678"]
        binding = {"run": str(self.root), "bundle": "bundle.json", "gate": "gate.json", "version": 1}
        with patch("uxpersonas.library._research_binding", return_value=binding):
            with self.library() as lib:
                lib.import_profiles(self.doc)
                self.assertTrue(lib.list()["personas"][0]["reusable"])
        with patch("uxpersonas.library._research_binding", return_value={**binding, "version": 2}):
            with self.library() as lib, self.assertRaises(EngineError):
                lib.get("sample", "PER-cautious")
        with patch("uxpersonas.library._research_binding", side_effect=EngineError("expired", "Source expired")):
            with self.library() as lib:
                self.assertFalse(lib.list()["personas"][0]["reusable"])

    def test_cli_round_trip(self):
        input_path = self.root / "input.json"
        atomic(input_path, canonical(self.doc))
        for command in [
            ["import", "--input", str(input_path)],
            ["list"],
            ["reuse", "--product", "sample", "--persona", "PER-cautious"],
            ["retire", "--product", "sample", "--persona", "PER-cautious", "--reason", "No longer relevant"],
        ]:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([*command, "--library", str(self.path)]), 0)
            self.assertIsInstance(json.loads(out.getvalue()), dict)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["reuse", "--library", str(self.path), "--product", "sample", "--persona", "PER-cautious"]), 2)


class ResearchBindingTests(unittest.TestCase):
    def test_authoritative_gate_and_exportability_are_required(self):
        from uxpersonas.library import _research_binding
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            research = {k: str(root / k) for k in ("run", "bundle", "gate")}
            (root / "run").mkdir()
            card = {"claim_id": "CLM-12345678", "exportable": True, "gate_status": "insufficient",
                    "source_ids": ["SRC-example"], "counting_evidence_ids": [], "context_evidence_ids": ["EV-example"]}
            gate = {"mode": "live", "result": "pass", "bundle_input_sha256": "a" * 64, "process_input_sha256": "b" * 64}
            with patch("uxresearch.ledger.Run"), patch("uxresearch.engine.fresh", return_value=({"bundle_id": "B-example"}, gate)), patch("uxresearch.personas.claim_cards", return_value=[card]):
                binding = _research_binding(research, ["CLM-12345678"])
                self.assertEqual(binding["claims"][0]["gate_status"], "insufficient")
                for mutation in ({"mode": "fixture"}, {"result": "fail"}):
                    with patch("uxresearch.engine.fresh", return_value=({"bundle_id": "B-example"}, {**gate, **mutation})), self.assertRaises(EngineError):
                        _research_binding(research, ["CLM-12345678"])
                with patch("uxresearch.personas.claim_cards", return_value=[{**card, "exportable": False}]), self.assertRaises(EngineError):
                    _research_binding(research, ["CLM-12345678"])
