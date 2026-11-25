"""Full-repository hygiene and version-sync checks for the public release tree."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest

import _paths

REPO = _paths.REPO
SKIPPED_DIRS = frozenset({".git", "__pycache__", "node_modules", ".pytest_cache", "dist", ".ux-loop", ".ux-research", ".ergo-bench", ".ergo-runs"})

# Assemble restricted literals dynamically so this test file stays self-clean.
FORBIDDEN_TERMS = (
    "peek" + "ly",
    "insta" + r"[-_]tracker",
    "uni" + "club",
    "m4" + "mini",
    "revolar" + r"_mini",
    "hyeon" + r"\.space",
    "token" + r"[_]?maxx",
    "open" + "codex",
    "remorsearch-ux-qa-" + "resume",
    "web-gpt-agent-rem-" + "daemon",
    r"/Users/r3m0" + r"r5e",
    r"/Users/m4" + r"mini",
    r"/Volumes/SanDisk" + r"2TB",
    "u0:19e8" + "a5aa",
    r"chatgpt\.com/(?:c/(?!11111111-|local-chatgpt)|local/)",
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"BEGIN [A-Z ]*PRIVATE KEY",
)
FORBIDDEN_RE = re.compile("|".join(FORBIDDEN_TERMS), re.IGNORECASE)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _tracked_files(repo: Path) -> list[Path]:
    self_path = Path(__file__).resolve()
    try:
        out = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo, timeout=10)
        paths = []
        for raw_rel in out.split(b"\x00"):
            if not raw_rel:
                continue
            rel = raw_rel.decode("utf-8", errors="surrogateescape")
            p = repo / rel
            if p.is_file() and not p.is_symlink() and p.resolve() != self_path:
                paths.append(p)
        # Also include untracked newly created non-gitignored files if any.
        extra = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=repo, timeout=10
        )
        for raw_rel in extra.split(b"\x00"):
            if not raw_rel:
                continue
            rel = raw_rel.decode("utf-8", errors="surrogateescape")
            p = repo / rel
            if p.is_file() and not p.is_symlink() and p.resolve() != self_path and p not in paths:
                paths.append(p)
        return sorted(paths)
    except (OSError, subprocess.SubprocessError):
        return sorted(
            p for p in repo.rglob("*")
            if p.is_file() and not p.is_symlink() and p.resolve() != self_path
            and not (SKIPPED_DIRS & set(p.relative_to(repo).parts))
        )


class RepoHygieneTests(unittest.TestCase):
    def test_no_private_product_or_personal_endpoint_leaks_remain(self):
        hits = []
        for path in _tracked_files(REPO):
            rel = path.relative_to(REPO).as_posix()
            if SKIPPED_DIRS & set(Path(rel).parts):
                continue
            path_match = FORBIDDEN_RE.search(rel)
            if path_match:
                hits.append(f"{rel}: path matched {path_match.group(0)!r}")
            raw = path.read_bytes()
            if b"\x00" in raw[:4096]:
                continue
            text = raw.decode("utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                match = FORBIDDEN_RE.search(line)
                if match:
                    hits.append(f"{rel}:{lineno}: matched {match.group(0)!r}")
        self.assertEqual(hits, [], "Private/personal references found:\n" + "\n".join(hits))

    def test_version_files_and_plugin_manifests_are_synchronized(self):
        root_ver = (REPO / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(root_ver, SEMVER_RE)
        self.assertEqual((REPO / "skills/remorsearch-ux-qa/VERSION").read_text(encoding="utf-8").strip(), root_ver)
        self.assertEqual((REPO / "skills/react-design-system/VERSION").read_text(encoding="utf-8").strip(), root_ver)
        plugin = json.loads((REPO / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        expected_repo = "https://github.com/remorser58/Remorswarm_UX_QA_Skill"
        self.assertEqual(plugin["version"], root_ver)
        self.assertEqual(plugin["repository"], expected_repo)
        self.assertEqual(plugin["homepage"], expected_repo)
        for entry in marketplace["plugins"]:
            self.assertEqual(entry["version"], root_ver)
            self.assertEqual(entry["repository"], expected_repo)
            self.assertEqual(entry["homepage"], expected_repo)


if __name__ == "__main__":
    unittest.main()
