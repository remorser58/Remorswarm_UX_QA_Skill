"""Repository hygiene and version-sync checks for the public release tree."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

import _paths

REPO = _paths.REPO
SKIPPED_DIRS = frozenset({".git", "__pycache__", "node_modules", ".pytest_cache", "dist", ".ux-loop", ".ux-research"})
SCANNED_DIRS = ("skills", "scripts", "integrations", ".github", ".claude-plugin", "tests")
SCANNED_FILES = ("README.md", "README.ko.md", "docs/release.md", "VERSION")

# Assemble restricted literals dynamically so this test file stays self-clean.
FORBIDDEN_TERMS = (
    "peek" + "ly",
    "insta" + "-tracker",
    "m4" + "mini",
    "hyeon" + r"\.space",
    "token" + "maxx",
)
FORBIDDEN_RE = re.compile("|".join(FORBIDDEN_TERMS), re.IGNORECASE)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class RepoHygieneTests(unittest.TestCase):
    def test_no_private_product_or_personal_endpoint_leaks_remain(self):
        hits = []
        self_path = Path(__file__).resolve()
        for rel_dir in SCANNED_DIRS:
            root = REPO / rel_dir
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.resolve() == self_path:
                    continue
                if SKIPPED_DIRS & set(path.relative_to(REPO).parts):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for lineno, line in enumerate(text.splitlines(), 1):
                    match = FORBIDDEN_RE.search(line)
                    if match:
                        hits.append(f"{path.relative_to(REPO)}:{lineno}: matched {match.group(0)!r}")
        for rel_file in SCANNED_FILES:
            path = REPO / rel_file
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for lineno, line in enumerate(text.splitlines(), 1):
                    match = FORBIDDEN_RE.search(line)
                    if match:
                        hits.append(f"{rel_file}:{lineno}: matched {match.group(0)!r}")
        self.assertEqual(hits, [], "Private/personal references found:\n" + "\n".join(hits))

    def test_version_files_and_plugin_manifests_are_synchronized(self):
        root_ver = (REPO / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(root_ver, SEMVER_RE)
        self.assertEqual((REPO / "skills/remorsearch-ux-qa/VERSION").read_text(encoding="utf-8").strip(), root_ver)
        self.assertEqual((REPO / "skills/react-design-system/VERSION").read_text(encoding="utf-8").strip(), root_ver)
        plugin = json.loads((REPO / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], root_ver)
        self.assertEqual(marketplace["plugins"][0]["version"], root_ver)
        self.assertEqual(plugin["repository"], "https://github.com/remorser58/Remorswarm_UX_QA_Skill")


if __name__ == "__main__":
    unittest.main()
