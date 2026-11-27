"""CLI contracts for scenario binding and capture-dependent heatmaps."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import _paths  # noqa: F401  (puts the skill folder on sys.path)
from test_ergo_pipeline import make_run  # the owned synthetic recorded run fixture

from ergoqa import checks, cli, png
from ergoqa.profiles import sample_profiles
from ergoqa.snapshot import sha256_file
from test_ergo_fixes import ctx, el


class ReachHeatmapContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.profile = next(p for p in sample_profiles(14, 7, ["iphone-15"])
                            if p["attributes"]["grip"] == "one_hand_right")
        self.profile["attributes"]["thumb_length_mm"] = 102.6
        (self.root / "profiles.json").write_text(json.dumps([self.profile]))
        self.shot = self.root / "crop.png"
        png.write_png(self.shot, png.new_image(393, 828, 3, (255, 255, 255)))
        # Place a tiny synthetic primary target precisely at a rendered cell's sample.
        self.x, self.y = 27.5 * 393 / 49, 36.5 * 828 / 103
        self.context = ctx([el("apply", "button", (self.x - .5, self.y - .5, 1, 1),
                               interactive=True, roles=("primary",))], self.profile, "iphone-15")
        self.snap = self.context.snapshot
        self.snap["device"]["viewport_css"] = [393, 828]
        self.snap.update(viewport_alignment={"basis": "observed-landmarks", "origin_css": [0, 24],
                                            "reference": "synthetic landmark in full display"})
        self.snap["screenshot"] = dict(path=self.shot.name, width_px=393, height_px=828,
                                       sha256=sha256_file(self.shot), viewport_raster_reference="authored viewport-only crop")
        self.out = self.root / "heat.png"

    def render(self, kind="reach"):
        snapshot = self.root / "snapshot.json"
        snapshot.write_text(json.dumps(self.snap))
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = cli.main(["heatmap", "--snapshot", str(snapshot), "--profiles", str(self.root / "profiles.json"),
                             "--profile", self.profile["profile_id"], "--kind", kind, "--out", str(self.out)])
        return code, err.getvalue()

    def test_crop_cell_color_matches_rh01_at_same_display_point(self):
        rh = next(o for o in checks.check_reach(self.context) if o.check_id == "RH-01")
        self.assertEqual(rh.measurement["value"], 0.0)
        self.assertEqual(self.render(), (cli.EXIT_OK, ""))
        image = png.read_png(self.out)
        self.assertEqual(image.pixel(int(self.x), int(self.y)), (255, 255, 255, 255))
        self.assertNotEqual(image.pixel(4, 4), (255, 255, 255, 255))  # not an empty overlay

    def test_unknown_origin_blocks_only_physical_reach(self):
        self.snap.pop("viewport_alignment")
        code, err = self.render()
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("missing_viewport_alignment", err)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.render("gaze"), (cli.EXIT_OK, ""))
        self.assertTrue(self.out.is_file())

    def test_display_origin_does_not_prove_viewport_to_raster_coverage(self):
        self.snap["screenshot"].pop("viewport_raster_reference")
        self.assertEqual(self.render()[0], cli.EXIT_USAGE)
        self.assertFalse(self.out.exists())  # even an identical aspect ratio does not establish coverage

    def test_raster_claim_is_bound_to_actual_bytes_and_viewport_scale(self):
        self.snap["screenshot"]["sha256"] = "0" * 64
        self.assertEqual(self.render()[0], cli.EXIT_USAGE)
        self.assertFalse(self.out.exists())
        png.write_png(self.shot, png.new_image(393, 852, 3, (255, 255, 255)))
        self.snap["screenshot"].update(sha256=sha256_file(self.shot), height_px=852)
        self.assertEqual(self.render()[0], cli.EXIT_USAGE)
        self.assertFalse(self.out.exists())


class GazeHeatmapCSSContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.profile = sample_profiles(1, 7, ["iphone-15"])[0]
        (self.root / "profiles.json").write_text(json.dumps([self.profile]))
        self.original = self.root / "source.png"
        # A nonuniform original provides contrast away from the position prior.
        pixels = bytes(v for y in range(96) for x in range(128)
                       for v in ((0, 0, 0) if 12 <= x < 44 and 48 <= y < 76 else (255, 255, 255)))
        png.write_png(self.original, png.make_image(128, 96, 3, pixels))
        self.css = self.root / "css.png"
        self.shot = dict(path=self.original.name, sha256=sha256_file(self.original))

    def render(self):
        snap = self.root / "snapshot.json"
        snap.write_text(json.dumps({
            "device": {"id": "iphone-15", "viewport_css": [64, 48], "dpr": 2},
            "screenshot": self.shot,
        }))
        out = self.root / "heat.png"
        out.unlink(missing_ok=True)
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = cli.main(["heatmap", "--kind", "gaze", "--snapshot", str(snap),
                             "--profiles", str(self.root / "profiles.json"), "--profile",
                             self.profile["profile_id"], "--out", str(out)])
        self.assertEqual(code, cli.EXIT_OK, err.getvalue())
        return out.read_bytes(), err.getvalue()

    def bind_css(self):
        self.shot["css"] = {"path": self.css.name, "sha256": sha256_file(self.css)}

    def test_unreadable_css_uses_original_and_does_not_poison_valid_css(self):
        original, original_err = self.render()
        self.assertEqual(original_err, "")
        self.css.write_bytes(b"not a PNG")
        self.bind_css()
        restored, err = self.render()
        self.assertTrue(restored == original, "fallback must preserve contrast from the original")
        self.assertIn("using the original screenshot", err)
        png.write_png(self.css, png.new_image(64, 48, 3, (255, 255, 255)))
        self.bind_css()
        using_css, err = self.render()
        self.assertFalse(using_css == original, "valid CSS capture should still take precedence")
        self.assertEqual(err, "")

    def test_unverified_css_uses_original_and_warns(self):
        original, _ = self.render()
        png.write_png(self.css, png.new_image(64, 48, 3, (255, 255, 255)))
        self.bind_css()
        self.shot["css"]["sha256"] = "0" * 64
        fallback, err = self.render()
        self.assertTrue(fallback == original)
        self.assertIn("using the original screenshot", err)


def scenario_doc(scenario_id: str) -> dict:
    return {
        "schema_version": "ergo-scenario.v1",
        "scenario_id": scenario_id,
        "surface": {"kind": "web", "url": "http://127.0.0.1/checkout.html"},
        "task_goal_ko": "결제를 완료한다",
        "device_ids": ["galaxy-s24"],
        "targets": {"primary": ["#pay"], "destructive": ["#delete"], "critical_message": ["#error"]},
        "steps": [{"action": "tap", "target": "#pay"}],
        "timing_windows": [{"id": "toast-1", "selector": "#toast", "measure": "visible_duration"}],
        "success": {"selector_visible": "#done"},
    }


class ScenarioBindingContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_dir = make_run(self.root)
        self.profiles_path = self.root / "profiles.json"
        self.profiles_path.write_text(json.dumps({"profiles": sample_profiles(3, 7, ["galaxy-s24"])}), encoding="utf-8")
        self.matching = self.root / "scenario-matching.json"
        self.matching.write_text(json.dumps(scenario_doc("SC-checkout"), ensure_ascii=False), encoding="utf-8")
        self.mismatching = self.root / "scenario-mismatching.json"
        self.mismatching.write_text(json.dumps(scenario_doc("SC-other"), ensure_ascii=False), encoding="utf-8")

    def run_cli(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def analyze(self, *scenario_args):
        return self.run_cli("analyze", "--runs", str(self.run_dir), "--profiles", str(self.profiles_path),
                            "--no-gaze", "--out", str(self.root / "analyses.json"), *scenario_args)

    def analyses(self):
        return json.loads((self.root / "analyses.json").read_text(encoding="utf-8"))["analyses"]

    def test_matching_scenario_is_bound_and_reaches_run_health(self):
        code, _, err = self.analyze("--scenario", str(self.matching))
        self.assertEqual(code, cli.EXIT_OK, err)
        # The declared timing window only produces this note through the bound scenario.
        self.assertTrue(any("toast-1" in note for note in self.analyses()[0]["limitations"]))

    def test_omitted_scenario_mode_stays_valid(self):
        code, _, err = self.analyze()
        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertFalse(any("toast-1" in note for note in self.analyses()[0]["limitations"]))

    def test_mismatched_scenario_is_rejected_for_analyze_and_swarm(self):
        code, _, err = self.analyze("--scenario", str(self.mismatching))
        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertIn("'SC-checkout'", err)
        self.assertIn("omit --scenario", err)
        self.assertFalse((self.root / "analyses.json").exists())
        code, _, err = self.run_cli("swarm", "--runs", str(self.run_dir), "--profiles", str(self.profiles_path),
                                    "--scenario", str(self.mismatching), "--no-gaze",
                                    "--out", str(self.root / "swarm-out"))
        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertIn("'SC-checkout'", err)
        self.assertFalse((self.root / "swarm-out").exists())

    def test_conflicting_duplicate_scenario_ids_are_rejected(self):
        clash = self.root / "scenario-clash.json"
        doc = scenario_doc("SC-checkout")
        doc["task_goal_ko"] = "다른 과제"
        clash.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        code, _, err = self.analyze("--scenario", str(self.matching), "--scenario", str(clash))
        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertIn("conflicting duplicate scenario id 'SC-checkout'", err)
        self.assertFalse((self.root / "analyses.json").exists())
        code, _, err = self.analyze("--scenario", str(self.matching), "--scenario", str(self.matching))
        self.assertEqual(code, cli.EXIT_OK, err)  # an identical repeat stays idempotent

    def test_explicit_paths_yielding_no_valid_scenarios_are_rejected(self):
        invalid = self.root / "scenario-invalid.json"
        invalid.write_text(json.dumps({"schema_version": "ux-audience-draft.v1", "scenario_id": "SC-checkout"}),
                           encoding="utf-8")
        empty_dir = self.root / "scenarios-empty"
        empty_dir.mkdir()
        for scenario_arg in (str(invalid), str(empty_dir)):
            code, _, err = self.analyze("--scenario", scenario_arg)
            self.assertEqual(code, cli.EXIT_USAGE, err)
            self.assertIn("no valid ergo-scenario.v1 documents", err)
            self.assertIn("omit --scenario", err)
            self.assertFalse((self.root / "analyses.json").exists())

    def test_attach_rejects_a_scenario_file_that_does_not_match_the_run(self):
        qa = json.loads((Path(__file__).parent / "fixtures" / "valid-bundle.json").read_text(encoding="utf-8"))
        qa["records"]["findings"][0]["severity"] = "P2"  # no second-pass reviews needed for this rejection
        qa_path = self.root / "qa.json"
        qa_path.write_text(json.dumps(qa, ensure_ascii=False), encoding="utf-8")
        out_path = self.root / "attached.json"
        code, _, err = self.run_cli("attach", "--bundle", str(qa_path), "--runs", str(self.run_dir),
                                    "--profiles", str(self.profiles_path), "--scenario", str(self.mismatching),
                                    "--bind", "scenario-1=EP-01", "--receipts-dir", str(self.root / "receipts"),
                                    "--no-gaze", "--out", str(out_path))
        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertIn("'SC-checkout'", err)
        self.assertFalse(out_path.exists())
        self.assertFalse((self.root / "receipts").exists())


if __name__ == "__main__":
    unittest.main()
