"""Context contracts for modeled reach observations and the corresponding CLI artifact."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import _paths  # noqa: F401
from ergoqa import checks, cli, png
from ergoqa.devices import device_for_snapshot
from ergoqa.snapshot import sha256_file
from test_ergo_fixes import ctx, el, profile


class ReachContext(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.shot = self.root / "crop.png"
        png.write_png(self.shot, png.new_image(64, 96, 3, (255, 255, 255)))

    def fixture(self, capture_id, grip, *, profile_device=None, orientation=None, capture_orientation=None):
        prof = profile(device_id=profile_device or capture_id, grip=grip)
        # Test authored, schema-valid inputs, not only the sampler's preferred combinations.
        prof["attributes"]["grip"] = grip
        if orientation:
            prof["attributes"]["orientation"] = orientation
        c = ctx([el("apply", "button", (3, 3, 2, 2), interactive=True, roles=("primary",))], prof, capture_id)
        block = c.snapshot["device"]
        if capture_orientation:
            block["orientation"] = capture_orientation
        c.device = device_for_snapshot(block)
        block.update(viewport_css=[64, 96], dpr=c.device.dpr)
        c.snapshot.update(viewport_alignment={"basis": "observed-landmarks", "origin_css": [0, 0],
                                             "reference": "synthetic top-left crop"},
                          screenshot={"path": self.shot.name, "width_px": 64, "height_px": 96,
                                      "sha256": sha256_file(self.shot), "viewport_raster_reference": "synthetic viewport crop"})
        return c

    def render(self, c, out):
        snap, profiles = self.root / "snapshot.json", self.root / "profiles.json"
        snap.write_text(json.dumps(c.snapshot))
        profiles.write_text(json.dumps([c.profile]))
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(["heatmap", "--snapshot", str(snap), "--profiles", str(profiles),
                             "--profile", c.profile["profile_id"], "--kind", "reach", "--out", str(out)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_rejected_inputs_do_not_write_an_overlay_or_emit_reach_observations(self):
        for c, reason in [
            (self.fixture("galaxy-tab-s9", "one_hand_right"), "tablet"),
            (self.fixture("galaxy-z-fold6-inner", "one_hand_left"), "tablet"),
            (self.fixture("galaxy-tab-s9", "mouse_right"), "grip"),
            (self.fixture("desktop-1920", "one_hand_left"), "touch"),
            (self.fixture("switch-handheld", "two_thumbs"), "touch"),
            (self.fixture("galaxy-tab-s9", "two_thumbs", profile_device="iphone-15"), "device"),
            (self.fixture("galaxy-tab-s9", "cradle_right", profile_device="iphone-15"), "device"),
            (self.fixture("galaxy-s24", "two_thumbs", orientation="landscape"), "orientation"),
        ]:
            with self.subTest(capture=c.device.id, attrs=c.profile["attributes"]["grip"], reason=reason):
                out = self.root / "rejected.png"
                self.assertEqual(checks.check_reach(c), [])
                self.assertFalse(checks.applicable("RH-01", c.profile, c.device))
                code, _, err = self.render(c, out)
                self.assertEqual(code, cli.EXIT_USAGE, err)
                self.assertIn(reason, err)
                self.assertFalse(out.exists())

    def test_missing_capture_orientation_does_not_use_catalog_default_or_overwrite_output(self):
        c = self.fixture("galaxy-s24", "one_hand_right")
        del c.snapshot["device"]["orientation"]
        self.assertEqual(checks.check_reach(c), [])
        out = self.root / "keep.png"
        out.write_bytes(b"already exists")
        code, _, err = self.render(c, out)
        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertIn("orientation", err)
        self.assertEqual(out.read_bytes(), b"already exists")

    def test_matched_cradle_has_no_modeled_penalty_and_no_scored_observation(self):
        # Preserve alpha as well as color; neutral is an unchanged raster.
        png.write_png(self.shot, png.new_image(64, 96, 4, (101, 111, 121, 128)))
        for grip in ("cradle_right", "cradle_left"):
            with self.subTest(grip=grip):
                c = self.fixture("galaxy-tab-s9", grip)
                self.assertEqual(checks.check_reach(c), [])
                self.assertFalse(checks.applicable("RH-01", c.profile, c.device))
                out = self.root / "neutral.png"
                code, msg, err = self.render(c, out)
                self.assertEqual(code, cli.EXIT_OK, err)
                self.assertIn("no modeled reach penalty", msg)
                self.assertNotIn("functional thumb input", msg)
                self.assertEqual(png.read_png(out), png.read_png(self.shot))

    def test_applicable_phone_and_two_thumb_tablet_keep_scored_pixels(self):
        for device, grip in [("galaxy-s24", "one_hand_right"), ("galaxy-tab-s9", "two_thumbs")]:
            with self.subTest(device=device):
                c = self.fixture(device, grip)
                self.assertTrue(checks.applicable("RH-01", c.profile, c.device))
                rh, = checks.check_reach(c)
                self.assertEqual((rh.check_id, rh.measurement["value"]), ("RH-01", 1.0))
                out = self.root / "modeled.png"
                code, _, err = self.render(c, out)
                self.assertEqual(code, cli.EXIT_OK, err)
                self.assertNotEqual(png.to_rgb(png.read_png(out)).pixel(4, 4), (255, 255, 255))

    def test_matched_landscape_game_still_uses_the_distinct_travel_metric(self):
        c = self.fixture("galaxy-s24", "two_thumbs", orientation="landscape", capture_orientation="landscape")
        c.snapshot["elements"][0]["roles"].append("game_control")
        gm, = checks.check_reach(c)
        self.assertTrue(checks.applicable("GM-02", c.profile, c.device))
        self.assertEqual((gm.check_id, gm.measurement["name"]), ("GM-02", "thumb_travel_mm"))

    def game_context(self, box, **geometry):
        c = self.fixture("galaxy-s24", "two_thumbs", orientation="landscape", capture_orientation="landscape")
        c.snapshot["device"]["viewport_css"] = [780, 360]
        c.snapshot["elements"] = [
            el("fire", "button", box, interactive=True, roles=("game_control",), **geometry),
        ]
        return c

    def test_gm02_measured_viewport_edge_uses_visible_center_but_size_uses_authored_box(self):
        c = self.game_context((750, 220, 200, 40), visible_geometry="measured",
                              visible_box={"x": 750, "y": 220, "w": 30, "h": 40})
        gm, = checks.check_reach(c)
        self.assertTrue(gm.passed)
        self.assertAlmostEqual(gm.measurement["value"], 22.3)
        self.assertEqual(gm.extra["point_mm"], [140.2, 44.0])
        self.assertEqual(gm.extra["point_basis"], "measured_viewport_visible_center")
        size, = checks.check_game_controls(c)
        self.assertEqual(size.measurement["value"], [36.7, 7.3])

    def test_gm02_does_not_score_unverified_or_ancestor_clipped_targets(self):
        for box, geometry in (
            ((750, 220, 200, 40), {}),
            ((750, 220, 200, 40), {"visible_geometry": "measured",
                                  "visible_box": {"x": 760, "y": 220, "w": 15, "h": 40}}),
            ((120, 20, 60, 340), {"visible_geometry": "ancestor_clipped",
                                "visible_box": {"x": 120, "y": 20, "w": 60, "h": 40}}),
            ((120, 20, 60, 340), {"visible_geometry": "unsupported", "visible_box": None}),
        ):
            with self.subTest(geometry=geometry):
                gm, = checks.check_reach(self.game_context(box, **geometry))
                self.assertFalse(gm.passed)
                self.assertIsNone(gm.measurement["value"])
                self.assertIsNone(gm.severity)
                self.assertEqual(gm.extra["verdict"], "inconclusive")

    def test_gm02_fully_in_view_preserves_the_authored_center(self):
        box = (720, 220, 40, 40)
        measured = self.game_context(box, visible_geometry="measured", visible_box=dict(zip("xywh", box)))
        legacy = self.game_context(box)
        a, = checks.check_reach(measured)
        b, = checks.check_reach(legacy)
        self.assertTrue(a.passed and b.passed)
        self.assertEqual(a.measurement, b.measurement)
        self.assertEqual(a.extra, b.extra)
        self.assertEqual(a.extra["point_mm"], [135.7, 44.0])

    def test_neutral_cradle_still_requires_alignment_and_verified_viewport_raster(self):
        for field, problem in (("alignment", "missing_viewport_alignment"), ("sha256", "SHA-256")):
            with self.subTest(field=field):
                c = self.fixture("galaxy-tab-s9", "cradle_right")
                if field == "alignment":
                    del c.snapshot["viewport_alignment"]
                else:
                    c.snapshot["screenshot"]["sha256"] = "0" * 64
                out = self.root / "unverified-neutral.png"
                code, _, err = self.render(c, out)
                self.assertEqual(code, cli.EXIT_USAGE)
                self.assertIn(problem, err)
                self.assertFalse(out.exists())
