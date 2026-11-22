"""Pinned authored profile/model inputs and analytical re-score, offline only."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _paths import SKILL
from ergoqa import analyze, bundle, swarm
from ergoqa.profile_binding import prepare
from ergoqa.profiles import sample_profiles
from ergoqa.snapshot import SnapshotError, load_run_dir
from test_ergo_pipeline import bind_fixture_profile, el, make_run
from validate_bundle import validate_bundle


class ProfileBinding(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.run_dir = make_run(self.root)
        self.run_path = self.run_dir / "run.json"
        self.profiles = sample_profiles(3, 7, ["galaxy-s24"])
        self.profile = self.profiles[0]
        self.profile["attributes"]["thumb_length_mm"] = 102.6
        for path in self.run_dir.glob("S-*.json"):
            snap = json.loads(path.read_text())
            snap["elements"].append(el("reach-probe", "button", (132, 220, 44, 44), text="합성 도달 조건",
                                       interactive=True, roles=("primary",), tag="button"))
            path.write_text(json.dumps(snap))
        self.binding = bind_fixture_profile(self.run_dir, self.profile)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SKILL / "scripts/ergo_qa.py"), *map(str, args)],
                              cwd=self.root, capture_output=True, text=True)

    def reach(self, result):
        return next(o for o in result["observations"]
                    if o["check_id"] == "RH-01" and o["element_key"].startswith("#reach-probe"))

    def test_cli_matches_then_rejects_changed_thumb_until_explicit_analytical_rescore(self):
        pfile = self.root / "profiles.json"
        qa = self.root / "qa.json"
        qdoc = json.loads((Path(__file__).parent / "fixtures/valid-bundle.json").read_text())
        qdoc["records"]["findings"][0]["severity"] = "P2"
        qa.write_text(json.dumps(qdoc))
        before = {p: p.read_bytes() for p in self.run_dir.iterdir()}
        pfile.write_text(json.dumps(list(reversed(self.profiles)), sort_keys=True))
        out = self.root / "analysis.json"
        args = ("--runs", self.run_dir, "--profiles", pfile, "--no-gaze")
        result = self.cli("analyze", *args, "--cross-profile", "--out", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        exact = json.loads(out.read_text())["analyses"][0]
        self.assertEqual(exact["verified_owner_profile_id"], "EP-01")
        self.assertEqual(exact["profiles_evaluated"], ["EP-01", "EP-03", "EP-02"])
        rh = self.reach(exact)
        self.assertEqual((rh["measurement"]["value"], rh["severity"], rh["basis"], rh["epistemic_status"]),
                         (0.725, "P2", "model", "inferred"))
        changed = copy.deepcopy(self.profiles)
        changed[0]["attributes"]["thumb_length_mm"] = 111.4
        pfile.write_text(json.dumps(changed))
        blocked = self.root / "blocked.json"
        for command in ("analyze", "swarm"):
            attempt = self.cli(command, *args, "--out", blocked)
            self.assertEqual(attempt.returncode, 2)
            self.assertIn("profile_digest_mismatch", attempt.stderr)
            self.assertFalse(blocked.exists())
        receipts = self.root / "receipts"
        attempt = self.cli("attach", *args, "--bundle", qa, "--bind", "scenario-1=EP-01",
                           "--receipts-dir", receipts, "--out", blocked)
        self.assertEqual(attempt.returncode, 2)
        self.assertIn("profile_digest_mismatch", attempt.stderr)
        self.assertFalse(receipts.exists())
        self.assertFalse(blocked.exists())
        export_dir = self.root / "swarm"
        result = self.cli("swarm", *args, "--analytical-rescore", "--bundle", "--out", export_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        changed_analysis = json.loads((export_dir / "analyses.json").read_text())["analyses"][0]
        rh = self.reach(changed_analysis)
        self.assertEqual((rh["measurement"]["value"], rh["severity"], rh["analysis_kind"]),
                         (0.515, "P3", "analytical_cross_profile"))
        self.assertIsNone(changed_analysis["verified_owner_profile_id"])
        self.assertEqual(changed_analysis["run_success"], exact["run_success"])
        doc = json.loads((export_dir / "bundle.json").read_text())
        self.assertEqual(validate_bundle(doc), [])
        self.assertTrue(all(r["cross_profile_evaluation"] for r in doc["records"]["runs"]))
        self.assertTrue(all(f["verification_status"] == "unverified" for f in doc["records"]["findings"]))
        machine_findings = json.loads((export_dir / "findings.json").read_text())
        self.assertTrue(machine_findings["findings"])
        self.assertTrue(all(f["analysis_kind"] == "analytical_cross_profile" for f in machine_findings["findings"]))
        self.assertTrue(all(f["analysis_kind"] == "analytical_cross_profile" for f in machine_findings["units"]))
        # Even an exact analysis cannot re-promote a replaced profile at bundle export.
        swapped = bundle.to_evidence_bundle("swap", [exact], swarm.aggregate([exact], self.profiles), changed)
        self.assertTrue(all(r["cross_profile_evaluation"] for r in swapped["records"]["runs"]))
        analytical_only = copy.deepcopy(exact)
        for observation in analytical_only["observations"]:
            observation["analysis_kind"] = "analytical_cross_profile"
        exported = bundle.to_evidence_bundle("no-promotion", [analytical_only],
                                            swarm.aggregate([analytical_only], self.profiles), self.profiles)
        self.assertTrue(all(o["analysis_kind"] == "analytical_cross_profile" for o in exported["records"]["observations"]))
        self.assertTrue(all(f["verification_status"] == "unverified" for f in exported["records"]["findings"]))
        self.assertEqual({p: p.read_bytes() for p in self.run_dir.iterdir()}, before)

    def test_model_revision_is_independent_and_malformed_binding_is_not_legacy(self):
        run = json.loads(self.run_path.read_text())
        run["profile_binding"]["model_revision_sha256"] = "0" * 64
        self.run_path.write_text(json.dumps(run))
        with self.assertRaisesRegex(ValueError, "model_revision_mismatch"):
            analyze.analyze_run(self.run_dir, [self.profile], gaze_enabled=False)
        value = analyze.analyze_run(self.run_dir, [self.profile], gaze_enabled=False, analytical_rescore=True)
        self.assertEqual(value["profile_binding_status"], "model_revision_mismatch")
        self.assertIsNone(value["verified_owner_profile_id"])
        for bad in ({"profile_file_sha256": "not-a-hash"}, {"device": {}}, {"schema_version": "unexpected"}):
            run["profile_binding"] = {**self.binding, **bad}
            self.run_path.write_text(json.dumps(run))
            with self.assertRaisesRegex(SnapshotError, "profile_binding"):
                load_run_dir(self.run_dir)
        run.update(profile_id="no-profile", profile_binding=self.binding)
        self.run_path.write_text(json.dumps(run))
        with self.assertRaisesRegex(SnapshotError, "profile_binding"):
            load_run_dir(self.run_dir)

    @unittest.skipUnless(shutil.which("node"), "Node is required for the local recorder preflight")
    def test_node_derives_the_same_binding_from_bytes_and_checks_real_catalog_config(self):
        pfile = self.root / "profile.json"
        raw = json.dumps(self.profile, ensure_ascii=False, sort_keys=True).encode("utf-8")
        pfile.write_bytes(raw)
        web = SKILL / "drivers/web"
        script = f"""
import {{ resolveDevice }} from {json.dumps((web / 'devices.mjs').as_uri())};
import {{ readJsonFileWithBytes }} from {json.dumps((web / 'util.mjs').as_uri())};
import {{ prepareProfileBinding }} from {json.dumps((web / 'profile_binding.mjs').as_uri())};
const {{ bytes, document }} = readJsonFileWithBytes(process.argv[1], 'owned fixture');
const device = resolveDevice({{id: 'galaxy-s24', orientation: 'portrait'}}).snapshotDevice;
const binding = prepareProfileBinding(bytes, document, device);
for (const change of [{{orientation:'landscape'}}, {{dpr: 1}}]) {{
  let rejected = false;
  try {{ prepareProfileBinding(bytes, document, {{...device,...change}}); }} catch {{ rejected = true; }}
  if (!rejected) throw Error('mismatched recorder condition accepted');
}}
process.stdout.write(JSON.stringify(binding));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script, str(pfile)], cwd=self.root,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value, prepare(raw)["binding"])
        self.assertEqual(value["profile_file_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(value["profile_file_sha256"], self.binding["profile_file_sha256"])
        self.assertEqual(value["profile_sha256"], self.binding["profile_sha256"])
