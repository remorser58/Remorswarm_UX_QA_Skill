"""Offline tests for release packaging and the safe self-updater CLI."""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile

import _paths

REPO = _paths.REPO
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_release_assets  # noqa: E402


def load_updater():
    path = _paths.SKILL / "scripts/update_skill.py"
    spec = importlib.util.spec_from_file_location("remorsearch_update_skill", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ReleaseUpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="remorswarm-release-test-")
        cls.server_root = Path(cls.temp.name) / "assets"
        cls.manifest = build_release_assets.build_release(
            cls.server_root,
            tag="v1.1.0",
            commit="0" * 40,
            published_at="2026-11-26T00:00:00Z",
        )
        cls.extracted_skill = cls.server_root / "bundle" / "remorsearch-ux-qa"

        handler = partial(SimpleHTTPRequestHandler, directory=str(cls.server_root))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.manifest_url = f"http://127.0.0.1:{cls.port}/release-manifest.json"
        cls.updater = load_updater()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.temp.cleanup()

    def install_legacy_copy(self, dest_parent: Path, *, version: str = "1.0.0") -> Path:
        skill_dir = dest_parent / "remorsearch-ux-qa"
        shutil.copytree(self.extracted_skill, skill_dir)
        version_bytes = (version + "\n").encode("utf-8")
        (skill_dir / "VERSION").write_bytes(version_bytes)
        manifest_path = skill_dir / "manifest.remorsearch.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if "engine" in manifest:
                manifest["engine"]["version"] = version
            manifest.setdefault("files", {})["VERSION"] = {
                "bytes": len(version_bytes),
                "sha256": hashlib.sha256(version_bytes).hexdigest(),
            }
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        # Seed runtime dirs that must survive upgrades untouched.
        (skill_dir / "drivers/web/node_modules/playwright").mkdir(parents=True)
        (skill_dir / "drivers/web/node_modules/playwright/sentinel.txt").write_text("keep-pw", encoding="utf-8")
        (skill_dir / ".ux-loop").mkdir()
        (skill_dir / ".ux-loop/state.json").write_text('{"keep":true}\n', encoding="utf-8")
        return skill_dir

    def run_updater(self, skill_dir: Path, *args: str, env_extra: dict[str, str] | None = None):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(skill_dir / "scripts/update_skill.py"), *args],
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_release_assets_and_checksums_are_valid_and_complete(self):
        self.assertEqual(self.manifest["schema_version"], "remorswarm-release-manifest.v1")
        for key in ("remorsearch-ux-qa", "react-design-system"):
            entry = self.manifest["assets"][key]
            path = self.server_root / entry["filename"]
            self.assertTrue(path.is_file())
            sha, size = build_release_assets.sha256_file(path)
            self.assertEqual(sha, entry["sha256"])
            self.assertEqual(size, entry["bytes"])
            with zipfile.ZipFile(path) as zf:
                self.assertIn(f"{entry['top_directory']}/SKILL.md", zf.namelist())
                self.assertIn(f"{entry['top_directory']}/VERSION", zf.namelist())
        sums = (self.server_root / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("remorsearch-ux-qa.zip", sums)
        self.assertIn("react-design-system.zip", sums)

    def test_check_detects_available_update_uptodate_and_cached_optout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = self.install_legacy_copy(root, version="1.0.0")
            cache_home = root / "xdg-cache"
            env = {"XDG_CACHE_HOME": str(cache_home)}
            res = self.run_updater(skill_dir, "check", "--target", str(skill_dir), "--manifest-url", self.manifest_url, env_extra=env)
            self.assertEqual(res.returncode, 0, res.stderr)
            payload = json.loads(res.stdout)
            self.assertTrue(payload["update_available"])
            self.assertEqual(payload["current_version"], "1.0.0")
            self.assertEqual(payload["latest_version"], self.manifest["version"])

            # Respect opt-out env in cached mode without modifying the skill directory.
            disabled = self.run_updater(
                skill_dir, "check", "--cached", "--target", str(skill_dir), "--manifest-url", self.manifest_url,
                env_extra={**env, "REMORSEARCH_NO_UPDATE_CHECK": "1"},
            )
            self.assertEqual(disabled.returncode, 0)
            self.assertEqual(json.loads(disabled.stdout)["status"], "disabled")
            self.assertEqual(self.updater.detect_local_modifications(skill_dir), [])

            # Already up to date check.
            (skill_dir / "VERSION").write_text(self.manifest["version"] + "\n", encoding="utf-8")
            current = self.run_updater(skill_dir, "check", "--target", str(skill_dir), "--manifest-url", self.manifest_url, env_extra=env)
            self.assertEqual(current.returncode, 0)
            self.assertFalse(json.loads(current.stdout)["update_available"])

    def test_apply_rejects_local_edits_without_force_and_preserves_files_and_runtime_on_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = self.install_legacy_copy(root, version="1.0.0")
            # Simulate a local edit to a tracked file.
            edited = skill_dir / "references/loop/provider-contract.md"
            edited.write_text(edited.read_text(encoding="utf-8") + "\n# local edit\n", encoding="utf-8")

            refused = self.run_updater(skill_dir, "apply", "--target", str(skill_dir), "--manifest-url", self.manifest_url)
            self.assertEqual(refused.returncode, 3, refused.stdout + refused.stderr)
            refused_json = json.loads(refused.stdout)
            self.assertFalse(refused_json["updated"])
            self.assertEqual(refused_json["reason"], "local_modifications_detected")
            self.assertTrue(any("references/loop/provider-contract.md" in row for row in refused_json["modified_files"]))

            # Applying with --force and --with-design-system upgrades cleanly, creates backup, preserves runtime dirs.
            applied = self.run_updater(
                skill_dir, "apply", "--target", str(skill_dir), "--manifest-url", self.manifest_url,
                "--with-design-system", "--force",
            )
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            data = json.loads(applied.stdout)
            self.assertTrue(data["updated"])
            self.assertEqual(data["to_version"], self.manifest["version"])
            self.assertTrue(data["design_system_updated"])
            self.assertTrue(Path(data["backup_path"]).is_dir())
            self.assertEqual(
                (skill_dir / "drivers/web/node_modules/playwright/sentinel.txt").read_text(encoding="utf-8"),
                "keep-pw",
            )
            self.assertEqual((skill_dir / ".ux-loop/state.json").read_text(encoding="utf-8"), '{"keep":true}\n')
            self.assertTrue((root / "react-design-system/SKILL.md").is_file())

            # Extracted and updated install passes remorsearch.py verify!
            verified = subprocess.run(
                [sys.executable, str(skill_dir / "scripts/remorsearch.py"), "verify"],
                capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=20,
            )
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertTrue(json.loads(verified.stdout)["valid"])

            # Launcher update subcommand also works end-to-end.
            via_launcher = subprocess.run(
                [sys.executable, str(skill_dir / "scripts/remorsearch.py"), "update", "check",
                 "--manifest-url", self.manifest_url],
                capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=20,
            )
            self.assertEqual(via_launcher.returncode, 0, via_launcher.stderr)
            self.assertFalse(json.loads(via_launcher.stdout)["update_available"])

    def test_apply_rejects_tampered_archive_and_insecure_remote_urls(self):
        with self.assertRaises(ValueError):
            self.updater.validate_url("http://example.com/release-manifest.json")
        with self.assertRaises(ValueError):
            self.updater.validate_url("file:///etc/passwd")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = self.install_legacy_copy(root, version="1.0.0")
            # Serve a tampered manifest expecting a different sha256.
            bad_manifest = json.loads(json.dumps(self.manifest))
            bad_manifest["assets"]["remorsearch-ux-qa"]["sha256"] = "0" * 64
            bad_path = self.server_root / "tampered-manifest.json"
            bad_path.write_text(json.dumps(bad_manifest), encoding="utf-8")
            self.addCleanup(lambda: bad_path.unlink(missing_ok=True))

            bad_url = f"http://127.0.0.1:{self.port}/tampered-manifest.json"
            failed = self.run_updater(skill_dir, "apply", "--target", str(skill_dir), "--manifest-url", bad_url)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("SHA-256 mismatch", failed.stderr)
            # Original 1.0.0 VERSION untouched.
            self.assertEqual((skill_dir / "VERSION").read_text(encoding="utf-8").strip(), "1.0.0")


if __name__ == "__main__":
    unittest.main()
