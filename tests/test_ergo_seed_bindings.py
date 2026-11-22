"""Portable, offline provenance checks against the shipped NVIDIA seed pack."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import _paths  # noqa: F401
from ergoqa.profiles import sample_profiles
from uxpersonas.product_controls import seed_catalog
from uxresearch.canonical import byte_digest, digest


SKILL = Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa"
PACK = SKILL / "uxpersonas/data/korea-seeds.v1.json"
PACK_SHA = "677aba0ac8324b2006aad33a079b37c054a1fbabe905b83305917e6d00df31c1"
REVISION = "ada0f5b53a38bb5a30cce09358adde883c1ab63a"
DATASET = "nvidia/Nemotron-Personas-Korea"


class SeedBindings(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profiles_path = self.root / "profiles.json"
        self.binding_path = self.root / "bindings.json"
        self.out = self.root / "receipt.json"
        self.profiles = sample_profiles(3, 7, ["galaxy-s24"])
        self.profiles[0]["attributes"]["thumb_length_mm"] = None
        self.doc = {
            "schema_version": "ergo-seed-bindings.v1",
            "dataset": DATASET,
            "dataset_revision": REVISION,
            "seed_pack_sha256": PACK_SHA,
            "bindings": [
                {"seed_id": "KR-8f116c3c5b57", "profile_id": "EP-01"},
                {"seed_id": "KR-101792479254", "profile_id": "EP-03"},
            ],
        }

    def write_inputs(self, doc=None, profiles=None):
        self.binding_path.write_text(json.dumps(self.doc if doc is None else doc), encoding="utf-8")
        self.profiles_path.write_text(json.dumps({"profiles": self.profiles if profiles is None else profiles}),
                                      encoding="utf-8")

    def invoke(self, out=None):
        return subprocess.run(
            [sys.executable, str(SKILL / "scripts/ergo_qa.py"), "bind-seeds", "--profiles", str(self.profiles_path),
             "--bindings", str(self.binding_path), "--out", str(self.out if out is None else out)],
            text=True, capture_output=True, check=False, cwd=self.root,
        )

    def test_canonical_pack_has_32_distinct_ids_and_separate_digest_domains(self):
        pack = seed_catalog()
        self.assertEqual(len(pack["records"]), 32)
        self.assertEqual(len({row["id"] for row in pack["records"]}), 32)
        self.assertEqual((pack["dataset"], pack["retrieval"]["revision"], digest(pack)),
                         (DATASET, REVISION, PACK_SHA))
        self.assertNotIn(PACK_SHA, (byte_digest(PACK.read_bytes()), pack["retrieval"]["response_sha256"]))

    def test_receipt_uses_explicit_ids_is_order_stable_and_does_not_assess_reach(self):
        self.write_inputs()
        before = self.profiles_path.read_bytes(), self.binding_path.read_bytes()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.profiles_path.read_bytes(), self.binding_path.read_bytes()), before)
        receipt = json.loads(self.out.read_bytes())
        self.assertEqual(receipt["schema_version"], "ergo-seed-binding-receipt.v1")
        self.assertEqual(receipt["seed_pack_sha256"], PACK_SHA)
        self.assertEqual(receipt["binding_basis"], "authored")
        self.assertEqual(receipt["reach_input_status"], "unknown")
        self.assertNotIn("profiles", receipt)  # This is not score input.
        self.assertEqual(receipt["bindings"], [
            {"seed_id": "KR-101792479254", "profile_id": "EP-03", "profile_sha256": digest(self.profiles[2])},
            {"seed_id": "KR-8f116c3c5b57", "profile_id": "EP-01", "profile_sha256": digest(self.profiles[0])},
        ])
        second = self.root / "second.json"
        self.write_inputs(dict(self.doc, bindings=list(reversed(self.doc["bindings"]))),
                          list(reversed(self.profiles)))
        result = self.invoke(second)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.out.read_bytes(), second.read_bytes())

    def test_seed_receipt_and_recording_cli_agree_only_on_the_profile_content(self):
        self.write_inputs()
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(self.out.read_bytes())
        self.assertEqual(receipt["reach_input_status"], "unknown")
        self.assertFalse(receipt["analysis_performed"])

        profile = self.profiles[0]
        link = next(row for row in receipt["bindings"] if row["profile_id"] == profile["profile_id"])
        command = [sys.executable, "-B", str(SKILL / "scripts/ergo_qa.py"), "profile-binding"]
        raw = json.dumps(profile, indent=2).encode("utf-8")
        recorded = subprocess.run(command, input=raw, capture_output=True, cwd=self.root)
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        recording = json.loads(recorded.stdout)
        self.assertEqual(recording["profile_id"], link["profile_id"])
        self.assertEqual(recording["binding"]["profile_sha256"], link["profile_sha256"])
        self.assertEqual(recording["binding"]["profile_file_sha256"], byte_digest(raw))

        # A provenance link does not turn the seed receipt into a recording profile.
        invalid = subprocess.run(command, input=self.out.read_bytes(), capture_output=True, cwd=self.root)
        self.assertEqual(invalid.returncode, 2, invalid.stderr)
        self.assertIn(b"invalid recording profile", invalid.stderr)
        self.assertEqual(invalid.stdout, b"")

    def test_wrong_pack_ambiguity_and_missing_ids_fail_without_receipt(self):
        first, second = self.doc["bindings"]
        for override, expected in [
            ({"seed_pack_sha256": byte_digest(PACK.read_bytes())}, "seed_pack_sha256"),
            ({"seed_pack_sha256": seed_catalog()["retrieval"]["response_sha256"]}, "seed_pack_sha256"),
            ({"dataset_revision": "latest"}, "dataset_revision"),
            ({"dataset": "another-dataset"}, "dataset"),
            ({"bindings": [first, dict(second, seed_id=first["seed_id"])]}, "duplicate seed_id"),
            ({"bindings": [first, dict(second, profile_id=first["profile_id"])]}, "duplicate profile_id"),
            ({"bindings": [dict(first, seed_id="KR-unknown")]}, "unknown seed_id"),
            ({"bindings": [dict(first, profile_id="EP-missing")]}, "unknown profile_id"),
            ({"bindings": [dict(first, thumb_length_mm=85)]}, "binding fields"),
            ({"bindings": [dict(first, seed_id=1)]}, "seed_id"),
        ]:
            with self.subTest(expected=expected, override=override):
                self.write_inputs(dict(self.doc, **override))
                result = self.invoke()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertFalse(self.out.exists())

    def test_rejects_duplicate_profile_ids_conflicting_ref_and_existing_output(self):
        self.write_inputs(profiles=[self.profiles[0], self.profiles[0], self.profiles[2]])
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate profile id", result.stderr)
        self.assertFalse(self.out.exists())
        conflict = copy.deepcopy(self.profiles)
        conflict[0]["persona_ref"] = {"dataset": DATASET, "revision": REVISION, "record_id": "KR-101792479254"}
        self.write_inputs(profiles=conflict)
        result = self.invoke()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("conflicting persona_ref", result.stderr)
        self.assertFalse(self.out.exists())
        self.write_inputs()
        before = self.profiles_path.read_bytes()
        result = self.invoke(self.profiles_path)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.profiles_path.read_bytes(), before)

    def test_manifest_matching_an_altered_pack_does_not_make_it_canonical(self):
        from ergoqa.seed_bindings import bind

        altered = copy.deepcopy(seed_catalog())
        altered["records"][0]["id"] = "KR-other"
        changed_doc = dict(self.doc, seed_pack_sha256=digest(altered))
        with patch("ergoqa.seed_bindings.seed_catalog", return_value=altered):
            with self.assertRaisesRegex(ValueError, "pack integrity"):
                bind(self.doc, self.profiles)
            with self.assertRaisesRegex(ValueError, "seed_pack_sha256"):
                bind(changed_doc, self.profiles)
