from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import _paths  # adds the skill root to sys.path
from ergoqa import cli, png, scan
from ergoqa.profile_binding import prepare
from ergoqa.snapshot import sha256_file
from test_ergo_semantics import el


URL = "http://127.0.0.1/owned-scan-qa"
DEVICES = ("laptop-1440", "galaxy-s24")
COLORS = {"galaxy-s24": (32, 120, 200), "laptop-1440": (52, 150, 105)}


def fixture_driver(command, **_):
    """Stand in only for the browser; actual scan validates, measures and crops its inputs."""
    def arg(name):
        return command[command.index(name) + 1]

    scenario = json.loads(Path(arg("--scenario")).read_text(encoding="utf-8"))
    profile_bytes = Path(arg("--profile")).read_bytes()
    profile = json.loads(profile_bytes)
    binding = prepare(profile_bytes)["binding"]
    device = binding["device"]
    rid = arg("--run-id")
    out = Path(arg("--out")) / rid
    out.mkdir(parents=True)
    sid = f"S-{rid}-000"
    shot = out / f"{sid}.png"
    width, height = (round(n * device["dpr"]) for n in device["viewport_css"])
    png.write_png(shot, png.new_image(width, height, 3, COLORS[device["id"]]))
    cut = el("title", "paragraph", (10, 100, 120, 20), text="Owned synthetic title",
             clipped={"x": True, "y": False, "ellipsis": False})
    snap = {
        "schema_version": "ergo-snapshot.v1", "snapshot_id": sid, "run_id": rid, "step_index": 0,
        "captured_at": "2026-09-28T12:00:01Z",
        "surface": {"kind": "web", "url": URL, "title": "Owned synthetic", "app_id": None},
        "device": device, "viewport_alignment": {"basis": "emulated-full-viewport", "origin_css": [0, 0]},
        "screenshot": {"path": shot.name, "sha256": sha256_file(shot), "width_px": width, "height_px": height},
        "elements": [cut], "focus_point": None, "console_errors": [], "notes": [],
    }
    run = {
        "schema_version": "ergo-run.v1", "run_id": rid, "scenario_id": scenario["scenario_id"],
        "profile_id": profile["profile_id"], "profile_binding": binding,
        "driver": {"name": "owned-offline-fixture", "version": "1", "browser": None},
        "device": device, "mode": "scripted", "started_at": "2026-09-28T12:00:00Z",
        "ended_at": "2026-09-28T12:00:05Z", "status": "completed", "success": True, "steps": [],
    }
    for path, document in ((out / f"{sid}.json", snap), (out / "run.json", run)):
        path.write_text(json.dumps(document), encoding="utf-8")
    return CompletedProcess(command, 0, stdout="", stderr="")


def run_scan_fixture(out: Path, *, no_crop: bool = False):
    stdout = io.StringIO()
    crop_case = patch.object(scan, "_box_for", return_value=None) if no_crop else nullcontext()
    with patch.object(scan.subprocess, "run", side_effect=fixture_driver), \
         patch.object(scan.time, "time", return_value=123), crop_case, redirect_stdout(stdout):
        rc = cli.main(["scan", "--url", URL, "--out", str(out), "--tiles", "0",
                       "--device", DEVICES[0], "--device", DEVICES[1]])
    return rc, stdout.getvalue()


class ScanReportTests(unittest.TestCase):
    def test_representative_crop_names_its_actual_device_and_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "scan"
            rc, stdout = run_scan_fixture(out)
            self.assertEqual(rc, 1)
            result = json.loads((out / "scan.json").read_text(encoding="utf-8"))
            candidate, = [row for row in result["candidates"] if row["check_id"] == "LY-01"]
            self.assertEqual(tuple(result["devices"]), DEVICES)
            self.assertEqual(candidate["devices"], ["galaxy-s24", "laptop-1440"])
            crop = Path(candidate["crop"])
            # The higher-sorted device was requested first. The pixels, not device order,
            # establish the provenance of this representative crop.
            self.assertEqual(tuple(png.read_png(crop).data[:3]), COLORS["galaxy-s24"])
            self.assertEqual(candidate["snapshot"], "S-SCAN-galaxy-s24-000")
            self.assertNotIn("crop_source", candidate)
            markdown = (out / "scan.md").read_text(encoding="utf-8")
            line, = [line for line in markdown.splitlines() if "| LY-01 |" in line]
            self.assertIn(" | galaxy-s24, laptop-1440 | ", line)
            source = f"{crop.name} (source: `galaxy-s24`, `S-SCAN-galaxy-s24-000`)"
            self.assertTrue(line.endswith(f"| {source} |"), line)
            self.assertIn(line, stdout)
            self.assertNotIn(str(crop), line)
            self.assertNotIn("source:", scan.render_markdown(result))

    def test_without_a_crop_the_scan_does_not_claim_a_source(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "scan"
            rc, stdout = run_scan_fixture(out, no_crop=True)
            self.assertEqual(rc, 1)
            result = json.loads((out / "scan.json").read_text(encoding="utf-8"))
            candidate, = [row for row in result["candidates"] if row["check_id"] == "LY-01"]
            self.assertIsNone(candidate["crop"])
            self.assertEqual(candidate["snapshot"], "S-SCAN-galaxy-s24-000")
            markdown = (out / "scan.md").read_text(encoding="utf-8")
            line, = [line for line in markdown.splitlines() if "| LY-01 |" in line]
            self.assertTrue(line.endswith("| - |"))
            self.assertNotIn("source:", line)
            self.assertIn(line, stdout)
            self.assertEqual(list((out / "crops").iterdir()), [])
