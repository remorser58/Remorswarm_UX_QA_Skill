"""Offline tests for release packaging and the safe self-updater CLI."""
from __future__ import annotations

from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
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
            manifest["payload_sha256"] = hashlib.sha256(
                json.dumps(manifest["files"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
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

    def test_release_assets_checksums_and_exec_bits_are_valid(self):
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
                if key == "remorsearch-ux-qa":
                    info = zf.getinfo("remorsearch-ux-qa/scripts/update_skill.py")
                    self.assertTrue((info.external_attr >> 16) & stat.S_IXUSR)
                else:
                    self.assertIn("react-design-system/manifest.react-design-system.json", zf.namelist())
                    info = zf.getinfo("react-design-system/scripts/audit-react-ds.sh")
                    self.assertTrue((info.external_attr >> 16) & stat.S_IXUSR)
        sums = (self.server_root / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("remorsearch-ux-qa.zip", sums)
        self.assertIn("react-design-system.zip", sums)

    def test_semver_ordering_and_latest_url_pinning(self):
        self.assertLess(self.updater.parse_version("1.2.0-rc.1"), self.updater.parse_version("1.2.0"))
        self.assertLess(self.updater.parse_version("1.1.0"), self.updater.parse_version("1.2.0-rc.1"))
        with self.assertRaises(ValueError):
            self.updater.parse_version("not-a-semver")
        pinned = self.updater.resolve_asset_url(
            "https://github.com/remorser58/Remorswarm_UX_QA_Skill/releases/latest/download/release-manifest.json",
            "remorsearch-ux-qa.zip",
            repo="remorser58/Remorswarm_UX_QA_Skill",
            tag="v1.1.1",
        )
        self.assertEqual(
            pinned,
            "https://github.com/remorser58/Remorswarm_UX_QA_Skill/releases/download/v1.1.1/remorsearch-ux-qa.zip",
        )

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

            disabled = self.run_updater(
                skill_dir, "check", "--cached", "--target", str(skill_dir), "--manifest-url", self.manifest_url,
                env_extra={**env, "REMORSEARCH_NO_UPDATE_CHECK": "1"},
            )
            self.assertEqual(disabled.returncode, 0)
            self.assertEqual(json.loads(disabled.stdout)["status"], "disabled")
            self.assertEqual(self.updater.detect_local_modifications(skill_dir), [])

            (skill_dir / "VERSION").write_text(self.manifest["version"] + "\n", encoding="utf-8")
            current = self.run_updater(skill_dir, "check", "--target", str(skill_dir), "--manifest-url", self.manifest_url, env_extra=env)
            self.assertEqual(current.returncode, 0)
            self.assertFalse(json.loads(current.stdout)["update_available"])

    def test_apply_rejects_local_edits_and_preserves_runtime_and_ds_store_compat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = self.install_legacy_copy(root, version="1.0.0")
            edited = skill_dir / "references/loop/provider-contract.md"
            edited.write_text(edited.read_text(encoding="utf-8") + "\n# local edit\n", encoding="utf-8")

            refused = self.run_updater(skill_dir, "apply", "--target", str(skill_dir), "--manifest-url", self.manifest_url)
            self.assertEqual(refused.returncode, 3, refused.stdout + refused.stderr)
            refused_json = json.loads(refused.stdout)
            self.assertFalse(refused_json["updated"])
            self.assertEqual(refused_json["reason"], "local_modifications_detected")
            self.assertTrue(any("references/loop/provider-contract.md" in row for row in refused_json["modified_files"]))

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
            self.assertTrue((skill_dir / "scripts/update_skill.py").stat().st_mode & stat.S_IXUSR)
            self.assertTrue((root / "react-design-system/scripts/audit-react-ds.sh").stat().st_mode & stat.S_IXUSR)
            self.assertEqual(
                (skill_dir / "drivers/web/node_modules/playwright/sentinel.txt").read_text(encoding="utf-8"),
                "keep-pw",
            )
            self.assertEqual((skill_dir / ".ux-loop/state.json").read_text(encoding="utf-8"), '{"keep":true}\n')

            # macOS Finder .DS_Store files must not break verification or updates.
            (skill_dir / ".DS_Store").write_bytes(b"finder")
            verified = subprocess.run(
                [sys.executable, str(skill_dir / "scripts/remorsearch.py"), "verify"],
                capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=20,
            )
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertTrue(json.loads(verified.stdout)["valid"])

            # Local edit inside sibling react-design-system is protected without --force.
            ds_skill = root / "react-design-system"
            (ds_skill / "SKILL.md").write_text("# modified locally\n", encoding="utf-8")
            ds_refused = self.run_updater(
                skill_dir, "apply", "--target", str(skill_dir), "--manifest-url", self.manifest_url,
                "--with-design-system",
            )
            self.assertEqual(ds_refused.returncode, 3, ds_refused.stdout + ds_refused.stderr)
            self.assertEqual(json.loads(ds_refused.stdout)["reason"], "local_modifications_detected")

    def test_with_design_system_installs_sibling_when_primary_is_already_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = self.install_legacy_copy(root, version=self.manifest["version"])
            self.assertFalse((root / "react-design-system").exists())
            applied = self.run_updater(
                skill_dir, "apply", "--target", str(skill_dir), "--manifest-url", self.manifest_url,
                "--with-design-system",
            )
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            data = json.loads(applied.stdout)
            self.assertTrue(data["updated"])
            self.assertFalse(data["primary_updated"])
            self.assertTrue(data["design_system_updated"])
            self.assertTrue((root / "react-design-system/SKILL.md").is_file())

    def test_tampered_secondary_asset_leaves_primary_untouched_and_supports_local_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = self.install_legacy_copy(root, version="1.0.0")
            bad_ds = json.loads(json.dumps(self.manifest))
            bad_ds["assets"]["react-design-system"]["sha256"] = "0" * 64
            bad_path = self.server_root / "tampered-ds-manifest.json"
            bad_path.write_text(json.dumps(bad_ds), encoding="utf-8")
            self.addCleanup(lambda: bad_path.unlink(missing_ok=True))

            failed = self.run_updater(
                skill_dir, "apply", "--target", str(skill_dir),
                "--manifest-url", f"http://127.0.0.1:{self.port}/tampered-ds-manifest.json",
                "--with-design-system",
            )
            self.assertEqual(failed.returncode, 2)
            self.assertEqual((skill_dir / "VERSION").read_text(encoding="utf-8").strip(), "1.0.0")

            # Local manifest + local primary zip install without fetching primary over HTTP.
            res = self.run_updater(
                skill_dir, "apply", "--target", str(skill_dir),
                "--local-manifest", str(self.server_root / "release-manifest.json"),
                "--local-primary-zip", str(self.server_root / "remorsearch-ux-qa.zip"),
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertTrue(json.loads(res.stdout)["updated"])
            self.assertEqual((skill_dir / "VERSION").read_text(encoding="utf-8").strip(), self.manifest["version"])

    def test_rejects_symlinks_git_checkouts_and_redirect_downgrade(self):
        with self.assertRaises(ValueError):
            self.updater.validate_url("http://example.com/release-manifest.json")
        with self.assertRaises(ValueError):
            self.updater.validate_url("file:///etc/passwd")

        class DowngradeRedirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "http://example.com/evil-manifest.json")
                self.end_headers()
            def log_message(self, *args):
                pass

        redir_srv = ThreadingHTTPServer(("127.0.0.1", 0), DowngradeRedirect)
        t = threading.Thread(target=redir_srv.serve_forever, daemon=True)
        t.start()
        try:
            with self.assertRaises(ValueError):
                self.updater.fetch_bytes(f"http://127.0.0.1:{redir_srv.server_address[1]}/release-manifest.json")
        finally:
            redir_srv.shutdown()
            redir_srv.server_close()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            sym = root / "sym-skill"
            sym.symlink_to(real)
            res_sym = self.run_updater(
                _paths.SKILL, "apply", "--target", str(sym), "--manifest-url", self.manifest_url
            )
            self.assertEqual(res_sym.returncode, 2)
            self.assertIn("symlink", res_sym.stderr.lower())

            git_dir = root / "cloned-skill"
            git_dir.mkdir()
            (git_dir / ".git").mkdir()
            res_git = self.run_updater(
                _paths.SKILL, "apply", "--target", str(git_dir), "--manifest-url", self.manifest_url
            )
            self.assertEqual(res_git.returncode, 2)
            self.assertIn("git checkout", res_git.stderr.lower())


if __name__ == "__main__":
    unittest.main()
