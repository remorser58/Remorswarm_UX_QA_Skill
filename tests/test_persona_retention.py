"""Local cleanup mechanics; authored mirrors never authorize deletion."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _paths
from test_persona_library import profile_input
from uxpersonas.cli import main
from uxpersonas.library import Library, retention_reason
from uxresearch.canonical import EngineError, canonical
from uxresearch.storage import Store, atomic


class RetentionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.run = self.root / "research"
        self.run.mkdir()
        self.library_path = self.root / "library"
        self.bundle = {"bundle_id": "BND-offline-test", "records": {"sources": [{
            "id": "SRC-example", "retention_status": "retained", "retention_until": None,
            "captures": [{"capture_ref": "IMP-example", "metadata": {
                "retention_status": "retained", "retention_until": None}}]}]}}
        with Store(self.run) as store:
            store.publish("invented-retention-test", {"bundle.json": self.bundle})
        self.binding = {
            "run": str(self.run), "bundle": str(self.run / "bundle.json"),
            "gate": str(self.run / "gate.json"), "valid_until": None,
            "claims": [{"source_ids": ["SRC-example"]}],
        }
        self.doc = profile_input(self.root)
        self.doc.update(mode="gated_research", research={
            key: self.binding[key] for key in ("run", "bundle", "gate")})
        self.doc["personas"][0]["claim_ids"] = ["CLM-12345678"]
        # These unit fixtures test retention, not research truth or passing gates.
        with patch("uxpersonas.library._research_binding", return_value=self.binding):
            with Library(self.library_path) as library:
                library.import_profiles(self.doc)

    def record(self):
        with Library(self.library_path) as library:
            return library.get("sample", "PER-cautious", revalidate=False)

    def write_mirror(self, bundle):
        atomic(self.run / "bundle.json", canonical(bundle))

    def test_pending_retention_markers_block_without_deleting(self):
        mutations = [
            lambda source: source.update(retention_status="withdrawn"),
            lambda source: source.update(retention_until="2000-01-01T00:00:00Z"),
            lambda source: source.update(research_tombstone={"reason": "uncommitted"}),
            lambda source: source["captures"][0]["metadata"].update(retention_status="withdrawn"),
            lambda source: source["captures"].clear(),
        ]
        original = (self.library_path / "library.json").read_bytes()
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                live = copy.deepcopy(self.bundle)
                mutate(live["records"]["sources"][0])
                self.write_mirror(live)
                with Library(self.library_path) as library:
                    result = library.prune()
                self.assertEqual(result["result"], "blocked")
                self.assertFalse(result["library_cleanup_complete"])
                self.assertEqual(result["blockers"][0]["code"], "retention_review_pending")
                self.assertTrue(result["blockers"][0]["next_step"])
                self.assertEqual(result["retired"], [])
                self.assertEqual((self.library_path / "library.json").read_bytes(), original)

    def test_missing_and_duplicate_mirror_sources_are_not_clean_success(self):
        for sources in ([], self.bundle["records"]["sources"] * 2):
            self.write_mirror({**self.bundle, "records": {"sources": sources}})
            with Library(self.library_path) as library:
                self.assertEqual(library.prune()["blockers"][0]["code"], "retention_review_pending")
        self.assertIn("profile", self.record())

    def test_nonretention_annotation_does_not_authorize_or_block_cleanup(self):
        live = copy.deepcopy(self.bundle)
        live["records"]["sources"][0]["summary"] = "Uncommitted safe summary"
        self.write_mirror(live)
        with Library(self.library_path) as library:
            result = library.prune()
        self.assertEqual(result["result"], "pass")
        self.assertTrue(result["library_cleanup_complete"])
        self.assertEqual(result["retired"], [])
        self.assertIn("profile", self.record())

    def test_missing_authoritative_source_requires_review(self):
        with Store(self.run) as store:
            store.publish("invented-source-missing", {"bundle.json": {
                **self.bundle, "records": {"sources": []}}})
        with Library(self.library_path) as library:
            result = library.prune()
        self.assertEqual(result["blockers"][0]["code"], "retention_source_missing")
        self.assertIn("profile", self.record())

    def test_authoritative_withdrawal_is_not_overridden_by_retained_mirror(self):
        committed = copy.deepcopy(self.bundle)
        committed["records"]["sources"][0]["retention_status"] = "withdrawn"
        with Store(self.run) as store:
            store.publish("invented-confirmed-withdrawal", {"bundle.json": committed})
        self.write_mirror(self.bundle)
        with Library(self.library_path) as library:
            result = library.prune()
        self.assertEqual(result["result"], "pass")
        self.assertEqual(len(result["retired"]), 1)
        self.assertNotIn("profile", self.record())

    def test_malformed_mirror_is_blocked_without_echo_or_deletion(self):
        self.write_mirror({"records": {"sources": [{"id": "SRC-example", "captures": [
            {"capture_ref": "IMP-example", "metadata": None}]}]}, "bundle_id": self.bundle["bundle_id"]})
        with Library(self.library_path) as library:
            result = library.prune()
        self.assertEqual(result["blockers"][0]["code"], "retention_check_unavailable")
        self.assertIn("profile", self.record())

    def test_cli_reports_incomplete_cleanup_with_nonzero_exit(self):
        live = copy.deepcopy(self.bundle)
        live["records"]["sources"][0]["retention_status"] = "withdrawn"
        self.write_mirror(live)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main(["prune", "--library", str(self.library_path)])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result["result"], "blocked")
        self.assertFalse(result["library_cleanup_complete"])

    def test_unavailable_old_revision_does_not_hide_confirmed_current_expiry(self):
        updated = copy.deepcopy(self.doc)
        updated["personas"][0]["label"] = "Revised synthetic profile"
        with patch("uxpersonas.library._research_binding", return_value=self.binding):
            with Library(self.library_path) as library:
                library.import_profiles(updated)
        def reason(record, now):
            if record["revision"] == 1:
                raise EngineError("io", "Old research unavailable")
            return "Authoritative current test deadline expired"
        with patch("uxpersonas.library.retention_reason", side_effect=reason):
            with Library(self.library_path) as library:
                result = library.prune()
        self.assertEqual(len(result["retired"]), 1)
        self.assertEqual(result["blockers"], [])
        self.assertTrue(result["library_cleanup_complete"])
        self.assertNotIn("profile", self.record())

    def test_partial_cleanup_keeps_confirmed_retirement_and_reports_unchecked(self):
        other = copy.deepcopy(self.doc)
        other["personas"][0]["persona_id"] = "PER-other"
        with patch("uxpersonas.library._research_binding", return_value=self.binding):
            with Library(self.library_path) as library:
                library.import_profiles(other)
        def reason(record, now):
            if record["persona_id"] == "PER-cautious":
                return "Authoritative test deadline expired"
            raise EngineError("retention_review_pending", "Pending test change", next_step="Review it")
        with patch("uxpersonas.library.retention_reason", side_effect=reason):
            with Library(self.library_path) as library:
                result = library.prune()
        self.assertEqual(result["result"], "partial")
        self.assertFalse(result["library_cleanup_complete"])
        self.assertEqual(len(result["retired"]), 1)
        self.assertEqual(len(result["blockers"]), 1)
        self.assertNotIn("profile", self.record())
        with Library(self.library_path) as library:
            self.assertIn("profile", library.get("sample", "PER-other", revalidate=False))


if __name__ == "__main__":
    unittest.main()
