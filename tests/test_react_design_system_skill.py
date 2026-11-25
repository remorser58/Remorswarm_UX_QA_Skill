"""Offline packaging and bounded-lookup integration tests for the react-design-system companion skill."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import _paths

REPO = _paths.REPO
PRIMARY_SKILL = _paths.SKILL
COMPANION_SKILL = REPO / "skills" / "react-design-system"
REF_SCRIPT = PRIMARY_SKILL / "scripts" / "ref.py"
LOOP_REFERENCE = PRIMARY_SKILL / "references" / "loop" / "react-design-system.md"
READING_JSON = PRIMARY_SKILL / "references" / "reading.json"

spec = importlib.util.spec_from_file_location("remorsearch_ref_check", REF_SCRIPT)
ref = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ref
spec.loader.exec_module(ref)


class ReactDesignSystemIntegrationTests(unittest.TestCase):
    def test_companion_skill_provenance_matches_all_files(self):
        provenance_path = COMPANION_SKILL / "PROVENANCE.json"
        self.assertTrue(provenance_path.is_file())
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        self.assertEqual(
            provenance["source_repository"],
            "https://github.com/remorser58/react-design-system-skill",
        )
        expected = provenance["files"]
        self.assertEqual(len(expected), 22)
        actual = {
            p.relative_to(COMPANION_SKILL).as_posix()
            for p in COMPANION_SKILL.rglob("*")
            if p.is_file() and p.name != "PROVENANCE.json"
        }
        self.assertEqual(actual, set(expected))
        for rel, receipt in expected.items():
            raw = (COMPANION_SKILL / rel).read_bytes()
            self.assertEqual(len(raw), receipt["bytes"], rel)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt["sha256"], rel)

    def test_companion_skill_frontmatter_pairs_and_eval_cases(self):
        for name in ("SKILL.md", "SKILL.ko.md"):
            raw = (COMPANION_SKILL / name).read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), name)
            text = raw.decode("utf-8")
            self.assertTrue(text.startswith("---\n"), name)
            self.assertIn('name: "react-design-system"', text, name)
        evals = [
            line
            for line in (COMPANION_SKILL / "assets" / "evals" / "react-design-system-cases.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        self.assertEqual(len(evals), 20)

    def test_companion_audit_script_runs_strict_clean_and_dirty(self):
        script = COMPANION_SKILL / "scripts" / "audit-react-ds.sh"
        syntax = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        if not shutil.which("jq"):
            self.skipTest("jq not available")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            (clean / "src" / "design-system" / "motion").mkdir(parents=True)
            (clean / "src" / "design-system" / "patterns").mkdir(parents=True)
            (clean / "src" / "design-system" / "stories").mkdir(parents=True)
            (clean / ".storybook").mkdir()
            shutil.copy2(COMPANION_SKILL / "assets" / "templates" / "index.html", clean / "index.html")
            shutil.copy2(
                COMPANION_SKILL / "assets" / "templates" / "glass-and-motion.css",
                clean / "src" / "design-system" / "motion" / "motion.css",
            )
            (clean / "src" / "design-system" / "patterns" / "skeleton.tsx").write_text(
                "export function Skeleton(){return <div className='min-h-dvh' />}\n",
                encoding="utf-8",
            )
            (clean / "src" / "design-system" / "stories" / "button.stories.tsx").write_text(
                "export default { title: 'Button' };\n",
                encoding="utf-8",
            )
            (clean / "package.json").write_text(
                json.dumps(
                    {
                        "dependencies": {
                            "react": "19",
                            "@base-ui/react": "1",
                            "motion": "12",
                            "@tanstack/react-query": "5",
                            "@tanstack/react-router": "1",
                            "@tanstack/react-table": "8",
                            "zustand": "5",
                            "ky": "1",
                        },
                        "devDependencies": {"vite": "6", "@storybook/react-vite": "9"},
                    }
                ),
                encoding="utf-8",
            )
            res = subprocess.run(
                ["bash", str(script), "--root", str(clean), "--strict", "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(json.loads(res.stdout)["ok"])

    def test_loop_reference_is_registered_lookup_only_and_bounded(self):
        self.assertTrue(LOOP_REFERENCE.is_file())
        manifest = json.loads(READING_JSON.read_text(encoding="utf-8"))
        for mode in ("research", "persona-qa", "ergonomics", "loop"):
            self.assertIn("references/loop/react-design-system.md", manifest["modes"][mode]["lookup_only"], mode)
            self.assertNotIn(
                "references/loop/react-design-system.md",
                manifest["modes"][mode]["before_first_action"],
                mode,
            )
        for sec in ("1", "2", "3", "4", "5", "6"):
            with self.subTest(section=sec):
                out = ref.reference_output(LOOP_REFERENCE, sec)
                self.assertIn(f"ID: {sec}\n", out)
                self.assertLessEqual(len(out.encode("utf-8")), ref.MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
