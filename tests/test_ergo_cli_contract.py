"""CLI contracts for scenario binding and capture-dependent heatmaps."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import _paths  # noqa: F401  (puts the skill folder on sys.path)
from test_ergo_pipeline import bind_fixture_profile, make_run  # the owned synthetic recorded run fixture

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
        self.device = {"id": "iphone-15", "viewport_css": [64, 48], "dpr": 2}

    def render(self):
        snap = self.root / "snapshot.json"
        snap.write_text(json.dumps({
            "device": self.device,
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

    def test_valid_digest_crop_and_device_size_are_not_css_viewport_copies(self):
        baseline, _ = self.render()
        for width, height in ((32, 48), (64, 24), (128, 96)):
            with self.subTest(width=width, height=height):
                png.write_png(self.css, png.new_image(width, height, 3, (255, 255, 255)))
                self.bind_css()
                output, warning = self.render()
                self.assertTrue(output == baseline, "wrong extent must not reposition gaze contrast")
                self.assertIn("using the original screenshot", warning)

    def test_geometry_is_checked_even_after_a_companion_cache_hit(self):
        baseline, _ = self.render()
        png.write_png(self.css, png.new_image(64, 48, 3, (255, 255, 255)))
        self.bind_css()
        valid = dict(self.shot["css"], width_px=64, height_px=48, factor=2)
        self.shot["css"] = valid
        css_output, warning = self.render()
        self.assertTrue(css_output != baseline)
        self.assertEqual(warning, "")
        for key, value in (("factor", 1), ("factor", 2.0), ("factor", None),
                           ("factor", True), ("factor", 0), ("width_px", 63),
                           ("height_px", 48.0), ("width_px", True), ("height_px", None)):
            with self.subTest(key=key, value=value):
                self.shot["css"] = {**valid, key: value}
                output, warning = self.render()
                self.assertTrue(output == baseline)
                self.assertIn("using the original screenshot", warning)
        # The same bytes are valid for the old primary, not for this taller one.
        initial = png.read_png(self.original)
        png.write_png(self.original, png.make_image(128, 98, 3, initial.data + initial.row(0) * 2))
        self.shot = dict(path=self.original.name, sha256=sha256_file(self.original))
        taller, _ = self.render()
        self.shot["css"] = valid
        output, warning = self.render()
        self.assertTrue(output == taller)
        self.assertIn("using the original screenshot", warning)

    def test_recorder_fractional_dpr_uses_actual_primary_floor_not_nominal_viewport(self):
        # Odd 127x95 primary. A distinguishing white companion tests selection,
        # not authenticity of the pixels. Official recorder uses JS Math.round.
        original = png.read_png(self.original)
        data = b"".join(original.row(y)[:127 * 3] for y in range(95))
        png.write_png(self.original, png.make_image(127, 95, 3, data))
        self.shot["sha256"] = sha256_file(self.original)
        for dpr, factor in ((2.5, 3), (2.625, 3), (2.4999999999999996, 2)):
            with self.subTest(dpr=dpr):
                self.device.update(viewport_css=[51, 38], dpr=dpr)
                self.shot.pop("css", None)
                baseline, _ = self.render()
                width, height = 127 // factor, 95 // factor
                png.write_png(self.css, png.new_image(width, height, 3, (255, 255, 255)))
                self.bind_css()
                self.shot["css"].update(factor=factor, width_px=width, height_px=height)
                result, warning = self.render()
                self.assertTrue(result != baseline)
                self.assertEqual(warning, "")

    def test_css_must_be_a_regular_file_before_opening(self):
        original, _ = self.render()
        png.write_png(self.css, png.new_image(64, 48, 3, (255, 255, 255)))
        self.bind_css()
        # resolve_within canonicalizes before testing the file; the temporary
        # directory may have an alias (for example /var on macOS).
        resolved_css = self.css.resolve()
        real_is_file, real_open = Path.is_file, Path.open

        def open_without_css(path, *args, **kwargs):
            self.assertNotEqual(path, resolved_css, "unverified CSS must not be opened")
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "is_file", lambda path: path != resolved_css and real_is_file(path)), \
             patch.object(Path, "open", open_without_css):
            output, warning = self.render()
        self.assertTrue(output == original)
        self.assertIn("using the original screenshot", warning)

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

    def test_swarm_uses_original_gaze_measurements_for_valid_digest_crop(self):
        profile = json.loads(self.profiles_path.read_text())["profiles"][0]
        bind_fixture_profile(self.run_dir, profile)
        out = self.root / "swarm-out"

        def gaze_measurements():
            code, _, err = self.run_cli("swarm", "--runs", str(self.run_dir), "--profiles",
                                        str(self.profiles_path), "--out", str(out))
            self.assertEqual(code, cli.EXIT_OK, err)
            obs = json.loads((out / "analyses.json").read_text())["analyses"][0]["observations"]
            return [o["measurement"] for o in obs if o["check_id"] in ("GZ-01", "GZ-04")]

        baseline = gaze_measurements()
        self.assertTrue(baseline)
        for path in sorted(self.run_dir.glob("S-*.json")):
            snap = json.loads(path.read_text())
            source = png.downsample(png.read_png(self.run_dir / snap["screenshot"]["path"]), 3)
            width = source.width // 2
            crop = png.make_image(width, source.height, 3,
                                  b"".join(source.row(y)[:width * 3] for y in range(source.height)))
            css = path.with_suffix(".css.png")
            png.write_png(css, crop)
            snap["screenshot"]["css"] = dict(path=css.name, sha256=sha256_file(css),
                                               width_px=width, height_px=source.height, factor=3)
            path.write_text(json.dumps(snap))
        self.assertEqual(gaze_measurements(), baseline)

    def test_swarm_invalid_audience_leaves_existing_outputs_untouched(self):
        profile = json.loads(self.profiles_path.read_text())["profiles"][0]
        bind_fixture_profile(self.run_dir, profile)
        second_root = self.root / "second-run"
        second_root.mkdir()
        second_run = make_run(second_root)
        bind_fixture_profile(second_run, profile)
        for path in sorted(second_run.glob("S-*.json")):
            snapshot = json.loads(path.read_text())
            next(e for e in snapshot["elements"] if e["selector"] == "#hint")["selector"] = "#later-hint"
            path.write_text(json.dumps(snapshot), encoding="utf-8")

        def export(run, out, title, *extra):
            return self.run_cli("swarm", "--runs", str(run), "--profiles", str(self.profiles_path), "--no-gaze",
                                "--bundle", "--out", str(out), "--title", title, *extra)

        missing = self.root / "missing-audience.json"
        malformed = self.root / "malformed-audience.json"
        malformed.write_text("{", encoding="utf-8")
        for audience_path, diagnostic in ((missing, f"not a regular file: {missing}"), (malformed, "invalid JSON:")):
            with self.subTest(audience=audience_path.name):
                out = self.root / (audience_path.stem + "-output")
                code, _, err = export(self.run_dir, out, "First report")
                self.assertEqual(code, cli.EXIT_OK, err)
                (out / "notes.txt").write_text("unrelated user notes\n", encoding="utf-8")
                before = {p.name: sha256_file(p) for p in out.iterdir()}
                self.assertEqual(set(before), {"analyses.json", "findings.json", "report.md", "bundle.json", "notes.txt"})

                code, stdout, err = export(second_run, out, "Next report", "--audience", str(audience_path))
                self.assertEqual(code, cli.EXIT_USAGE, err)
                self.assertEqual(stdout, "")
                self.assertIn(diagnostic, err)
                self.assertEqual({p.name: sha256_file(p) for p in out.iterdir()}, before)

                code, _, err = export(second_run, out, "Next report")
                self.assertEqual(code, cli.EXIT_OK, err)
                self.assertIn("# Next report\n", (out / "report.md").read_text(encoding="utf-8"))
                self.assertNotEqual(sha256_file(out / "findings.json"), before["findings.json"])
                self.assertEqual(sha256_file(out / "notes.txt"), before["notes.txt"])

    def test_swarm_audience_report_error_preserves_outputs(self):
        audience_path = _paths.SKILL / "examples" / "audience" / "transit-card.audience.json"
        code, _, err = self.run_cli("personas", "--audience", str(audience_path), "--budget", "12",
                                    "--out", str(self.profiles_path))
        self.assertEqual(code, cli.EXIT_OK, err)
        profile = next(p for p in json.loads(self.profiles_path.read_text())["profiles"]
                       if p["attributes"]["device_id"] == "galaxy-s24" and p["attributes"]["orientation"] == "portrait")
        self.assertEqual(profile["origin"], "audience_composed")
        doc = json.loads(audience_path.read_text(encoding="utf-8"))
        segment = next(s for s in doc["segments"] if s["segment_id"] == profile["audience_ref"]["segment_id"])
        segment_name = segment.pop("name_ko")
        malformed = self.root / "missing-segment-name.json"
        malformed.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        second_root = self.root / "second-run"
        second_root.mkdir()
        second_run = make_run(second_root)
        for run in (self.run_dir, second_run):
            path = run / "run.json"
            run_doc = json.loads(path.read_text())
            run_doc["profile_id"] = profile["profile_id"]
            path.write_text(json.dumps(run_doc), encoding="utf-8")
            bind_fixture_profile(run, profile)
        for path in sorted(second_run.glob("S-*.json")):
            snapshot = json.loads(path.read_text())
            next(e for e in snapshot["elements"] if e["selector"] == "#hint")["selector"] = "#later-hint"
            path.write_text(json.dumps(snapshot), encoding="utf-8")

        def export(run, out, title, path):
            return self.run_cli("swarm", "--runs", str(run), "--profiles", str(self.profiles_path), "--no-gaze",
                                "--bundle", "--out", str(out), "--title", title, "--audience", str(path))

        def hashes(out):
            return {p.name: sha256_file(p) for p in out.iterdir()}

        reused = self.root / "report"
        empty = self.root / "empty"
        fresh = self.root / "fresh"
        empty.mkdir()
        code, _, err = export(self.run_dir, reused, "First report", audience_path)
        self.assertEqual(code, cli.EXIT_OK, err)
        (reused / "notes.txt").write_text("unrelated user notes\n", encoding="utf-8")
        before = hashes(reused)
        self.assertEqual(set(before), {"analyses.json", "findings.json", "report.md", "bundle.json", "notes.txt"})
        report_name = f"- {profile['profile_id']}: {segment_name} —"
        self.assertIn(report_name, (reused / "report.md").read_text(encoding="utf-8"))
        for out, expected in ((reused, before), (empty, {}), (fresh, None)):
            with self.subTest(out=out.name):
                code, stdout, err = export(second_run, out, "Next report", malformed)
                self.assertEqual((code, stdout, err), (cli.EXIT_USAGE, "", "ERROR: 'name_ko'\n"))
                self.assertEqual(hashes(out) if out.exists() else None, expected)

        code, _, err = export(second_run, reused, "Next report", audience_path)
        self.assertEqual(code, cli.EXIT_OK, err)
        after = hashes(reused)
        self.assertEqual(set(after), set(before))
        for name in ("analyses.json", "findings.json", "report.md"):
            self.assertNotEqual(after[name], before[name])
        self.assertEqual(after["notes.txt"], before["notes.txt"])
        report_text = (reused / "report.md").read_text(encoding="utf-8")
        self.assertIn("# Next report\n", report_text)
        self.assertIn(report_name, report_text)

    def test_swarm_marks_explicit_unmeasured_reflow_without_inventing_findings(self):
        profile = json.loads(self.profiles_path.read_text())["profiles"][0]
        bind_fixture_profile(self.run_dir, profile)
        run_path = self.run_dir / "run.json"
        original = json.loads(run_path.read_text())
        first, second = [p.stem for p in sorted(self.run_dir.glob("S-*.json"))]
        private = "https://synthetic.invalid/<private-reflow-error>"
        failed = {"snapshot_id": second, "url": private, "width": 320}
        measured = {"snapshot_id": first, "url": "http://127.0.0.1/checkout.html", "width": 320,
                    "client_width": 320, "scroll_width": 320, "viewport_overflow_x": "auto",
                    "root_clips": False, "offenders": [],
                    "lost": [{"dom_id": "pay", "tag": "button", "ancestor_ids": [], "visible_full": 1,
                              "visible_320": 0, "box": {"x": 330, "y": 250, "w": 90, "h": 44}, "text": "결제하기"}]}
        out = self.root / "swarm-reflow"

        def swarm(records, *flags, **changes):
            run_path.write_text(json.dumps({**original, **changes, "reflow": records}), encoding="utf-8")
            code, stdout, stderr = self.run_cli("swarm", "--runs", str(self.run_dir), "--profiles",
                                                 str(self.profiles_path), "--out", str(out), *flags)
            analysis = json.loads((out / "analyses.json").read_text())["analyses"][0]
            findings = json.loads((out / "findings.json").read_text())["findings"]
            report = (out / "report.md").read_text(encoding="utf-8")
            section1 = report.split("## 2.", 1)[0]
            self.assertNotIn(private, stdout + stderr + section1 + json.dumps(analysis["limitations"]))
            return code, stderr, analysis, findings, section1

        def rf01(rows):
            return [row for row in rows if row["check_id"] == "RF-01"]

        code, err, clean, clean_findings, clean_report = swarm([measured])
        self.assertEqual((code, err, clean["health"]), (cli.EXIT_OK, "", "ok"))
        self.assertEqual([f["severity"] for f in rf01(clean_findings)], ["P2"])
        self.assertNotIn("실행 상태 경고", clean_report)
        cases = [
            ({**failed, "error": f"copy timed out at {private}"}, "재현 오류 1건"),
            ({**failed, "styles_lost": {"live_rules": 40, "copy_rules": 12}}, "CSS 규칙 손실 1건"),
        ]
        for record, reason in cases:
            for mixed in (False, True):
                with self.subTest(reason=reason, mixed=mixed):
                    rows = [measured, record] if mixed else [record]
                    code, err, result, findings, section1 = swarm(rows)
                    self.assertEqual((code, result["health"]), (cli.EXIT_DEGRADED, "degraded"), err)
                    self.assertEqual((result["run_status"], result["run_success"], result["profile_binding_status"]),
                                     ("completed", True, "matched"))
                    self.assertIn("run health:", err)
                    self.assertIn("해당 실행의 '발견 없음'은 통과가 아닙니다", section1)
                    note = next(note for note in result["limitations"] if "RF-01" in note)
                    self.assertIn(reason, note)
                    self.assertIn(note, section1)
                    self.assertEqual(rf01(result["observations"]), rf01(clean["observations"]) if mixed else [])
                    self.assertEqual(rf01(findings), rf01(clean_findings) if mixed else [])
                    allow, allowed_err, allowed, allowed_findings, allowed_report = swarm(rows, "--allow-degraded")
                    self.assertEqual((allow, allowed_err, allowed, allowed_findings, allowed_report),
                                     (cli.EXIT_OK, err, result, findings, section1))
                    if mixed:
                        gate, gate_err, gated, gated_findings, gated_report = swarm(
                            rows, "--fail-on", "P2", "--fail-on-basis", "measured", "--allow-degraded")
                        self.assertEqual((gate, gate_err, gated, gated_findings, gated_report),
                                         (cli.EXIT_FINDINGS, err, result, findings, section1))

        code, err, result, _, section1 = swarm(
            [{**cases[0][0], "snapshot_id": first}, cases[1][0]], status="failed", success=False)
        self.assertEqual((code, result["health"], result["run_status"], result["run_success"]),
                         (cli.EXIT_DEGRADED, "failed", "failed", False))
        self.assertIn("run health:", err)
        self.assertIn("재현 오류 1건", section1)
        self.assertIn("CSS 규칙 손실 1건", section1)

        malformed = [
            {**failed, "error": True}, {**failed, "error": " \t "},
            {**failed, "styles_lost": {"live_rules": 40, "copy_rules": True}},
            {**failed, "styles_lost": {"live_rules": 40, "copy_rules": 36}},
            {**failed, "styles_lost": {"live_rules": 19, "copy_rules": 0}},
        ]
        for record in [None, *malformed]:
            with self.subTest(not_explicit_failure=record):
                code, err, result, findings, section1 = swarm(
                    [measured] if record is None else [measured, record], warnings=[f"unstructured hint {private}"])
                self.assertEqual((code, err, result["health"]), (cli.EXIT_OK, "", "ok"))
                self.assertEqual(rf01(findings), rf01(clean_findings))
                self.assertNotIn("실행 상태 경고", section1)
                self.assertFalse(any("RF-01" in note for note in result["limitations"]))

    def test_swarm_reports_prepass_reflow_budget_only_for_exact_web_dossier(self):
        profile = json.loads(self.profiles_path.read_text())["profiles"][0]
        bind_fixture_profile(self.run_dir, profile)
        run_path = self.run_dir / "run.json"
        original = json.loads(run_path.read_text())
        web = {**original["driver"], "name": "playwright-web"}
        warning = "reflow pass skipped: finish browser budget exhausted"
        unrelated = "unrelated hint https://synthetic.invalid/<private-warning>"
        out = self.root / "swarm-budget"

        def swarm(dossier, *flags):
            run_path.write_text(json.dumps({**original, "driver": web, **dossier}), encoding="utf-8")
            code, stdout, stderr = self.run_cli("swarm", "--runs", str(self.run_dir), "--profiles",
                                                 str(self.profiles_path), "--out", str(out), "--bundle", *flags)
            analysis = json.loads((out / "analyses.json").read_text())["analyses"][0]
            findings = json.loads((out / "findings.json").read_text())["findings"]
            report = (out / "report.md").read_text(encoding="utf-8").split("## 2.", 1)[0]
            bundle = json.loads((out / "bundle.json").read_text())
            self.assertNotIn(unrelated, stdout + stderr + report + json.dumps(analysis["limitations"]))
            self.assertEqual((analysis["profile_binding_status"], analysis["verified_owner_profile_id"]),
                             ("matched", "EP-01"))
            return code, stderr, analysis, findings, report, bundle

        _, _, clean, clean_findings, _, _ = swarm({"reflow": []})
        exact = {"warnings": [unrelated, warning], "reflow": []}
        for flags, expected_exit in (((), cli.EXIT_DEGRADED), (("--allow-degraded",), cli.EXIT_OK)):
            with self.subTest(flags=flags):
                code, err, result, findings, report, bundle = swarm(exact, *flags)
                self.assertEqual((code, result["health"]), (expected_exit, "degraded"))
                self.assertEqual((result["run_status"], result["run_success"]), ("completed", True))
                self.assertIn("run health:", err)
                note, = result["limitations"]
                self.assertIn("RF-01", note)
                self.assertIn("종료 시간 한도", note)
                self.assertIn("해당 실행의 '발견 없음'은 통과가 아닙니다", report)
                self.assertIn(note, report)
                self.assertIn(note, bundle["notes"]["limitations"])
                self.assertEqual(result["observations"], clean["observations"])
                self.assertEqual(findings, clean_findings)
        with self.subTest("already failed"):
            code, err, result, _, report, _ = swarm({**exact, "status": "failed", "success": False})
            self.assertEqual((code, result["health"], result["run_status"], result["run_success"]),
                             (cli.EXIT_DEGRADED, "failed", "failed", False))
            self.assertIn("run health:", err)
            self.assertIn("종료 시간 한도", report)

        measured = {"snapshot_id": "S-R-1-000", "width": 320, "client_width": 320, "scroll_width": 320,
                    "viewport_overflow_x": "auto", "root_clips": False, "offenders": [], "lost": []}
        for label, dossier in (
            ("no reflow key", {"warnings": [warning]}),
            ("null reflow", {**exact, "reflow": None}),
            ("other driver", {**exact, "driver": original["driver"]}),
            ("measured row", {**exact, "reflow": [measured]}),
            ("substring only", {"reflow": [], "warnings": [unrelated, f"{warning} details"]}),
            ("not a warning list", {"reflow": [], "warnings": warning}),
            ("unrelated warning", {"reflow": [], "warnings": [unrelated]}),
        ):
            with self.subTest(label):
                code, err, result, _, report, _ = swarm(dossier)
                self.assertEqual((code, err, result["health"], result["limitations"]),
                                 (cli.EXIT_OK, "", "ok", []))
                self.assertNotIn("실행 상태 경고", report)

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
