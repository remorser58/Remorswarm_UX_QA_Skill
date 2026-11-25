"""Entry regressions use owned fixtures, never real-product or real-user evidence."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/remorsearch-ux-qa"))
from uxpersonas import workspace, swarm
from uxpersonas.library import Library
from uxresearch.canonical import EngineError, byte_digest, canonical, digest
from uxresearch.storage import atomic


class JourneyEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "owned-source"
        self.product = self.source / "product"
        self.work = self.root / "review"
        self.product.mkdir(parents=True, mode=0o700)
        files = {"README.md": b"Owned fixture only.\n",
                 "docs/PRD.md": b"Keep prior data if import fails.\n",
                 "src/core.ts": b"export const owned = true;\n"}
        for name, raw in files.items():
            p = self.product / name
            p.parent.mkdir(parents=True, exist_ok=True)
            atomic(p, raw)
        self.recipe = dict(id="owned-entry-test", product_id="owned-product",
                           source_manifest_sha256="owned-fixed-source",
                           files={k: byte_digest(v) for k, v in files.items()})
        self.binding = dict(files=self.recipe["files"], source_manifest_sha256="owned-fixed-source")
        atomic(self.source / "product-binding.json", canonical(self.binding))

    def prepare(self, **kw):
        return workspace.prepare(self.source, self.work, selected=self.recipe, **kw)

    def hashes(self, folder):
        return {str(p.relative_to(folder)): byte_digest(p.read_bytes())
                for p in folder.rglob("*") if p.is_file() and not p.is_symlink()}

    def saved(self):
        prd = self.product / "docs/PRD.md"
        spec = dict(schema_version="ux-persona-library-input.v1", product_id="owned-product",
                    mode="prd_hypothesis",
                    context=dict(prd_path=str(prd), prd_sha256=byte_digest(prd.read_bytes()),
                                 requirements=[dict(id="R-KEEP", source_anchor="Owned", excerpt="Keep prior data if import fails.")]),
                    personas=[dict(persona_id="PER-KEEP", label="Owned interrupted comparer",
                                   goals=["Keep the earlier comparison"], behaviors=["Retry after a fault"],
                                   contexts=["Owned interrupted input"], assumptions=["Synthetic test condition"],
                                   unknowns=["Human behavior is not measured"], requirement_ids=["R-KEEP"], claim_ids=[])])
        task = dict(id="T-KEEP", persona_id="PER-KEEP", requirement_ids=["R-KEEP"],
                    goal="Keep the earlier owned comparison", starting_state="Owned fixture",
                    actions=["Attempt the owned operation"], decisions=["Inspect the owned outcome"],
                    success_criteria=["The candidate is accepted"], recovery_criteria=["Prior data stays"],
                    data_namespace="fixture", resource_id="fixture", side_effects="read_only",
                    stop_conditions=["Stop outside owned input"])
        build = dict(id="owned-build", artifact_path=str(self.source / "product-binding.json"),
                     sha256=byte_digest((self.source / "product-binding.json").read_bytes()))
        run = self.source / "persona-run"
        with Library(self.source / "persona-library") as library:
            imported = library.import_profiles(spec)["imported"][0]
            swarm.create_plan(library, run, dict(schema_version=swarm.SCHEMA, product_id="owned-product",
                                                build=build, max_parallel=1, max_attempts=2, tasks=[task]))
            claim = swarm.claim(library, run, "fixture-worker")
            log = Path(claim["evidence_path"]) / "owned.log"
            raw = b"Owned harness fixture: candidate absent; earlier data retained."
            atomic(log, raw)
            receipt = dict(schema_version="ux-persona-swarm-receipt.v1", task_id="T-KEEP",
                           worker_id=claim["lease"]["worker_id"], lease_token=claim["lease"]["lease_token"],
                           build_sha256=build["sha256"], persona_revision=imported["revision"],
                           profile_sha256=imported["profile_sha256"], outcome="failed",
                           reason="Owned harness fixture failure, not product evidence.",
                           steps=[dict(action="Inspect owned fixture", observation="Candidate absent, earlier data retained", evidence_ids=["log"])],
                           criteria=[dict(kind="success", index=0, status="failed", observation="Owned candidate absent", evidence_ids=["log"]),
                                     dict(kind="recovery", index=0, status="passed", observation="Owned earlier data retained", evidence_ids=["log"])],
                           artifacts=[dict(id="log", kind="execution_log", path=str(log.relative_to(run)), sha256=byte_digest(raw))])
            swarm.record(library, run, receipt)
        return imported

    def test_empty_start_creates_private_report_without_source_mutation(self):
        self.work.mkdir()
        before = self.hashes(self.source)
        report = self.prepare()
        self.assertTrue(report["preparation_complete"])
        self.assertFalse(report["execution_performed"])
        self.assertIsNone(report["prior_counts"])
        self.assertEqual(before, self.hashes(self.source))
        self.assertTrue(Path(report["report_path"]).is_file())
        self.assertEqual((self.work / "workspace.json").stat().st_mode & 0o077, 0)
        self.assertFalse((self.work / "product/node_modules").exists())

    def test_generic_cli_prepares_reviewed_files_without_manifest_or_metadata_reads(self):
        (self.product / "product-binding.json").symlink_to(self.root / "unapproved.json")
        command = [sys.executable, str(ROOT / "skills/remorsearch-ux-qa/scripts/ux_personas.py"),
                   "start", "--source", str(self.product), "--work", str(self.work),
                   "--include", "README.md", "--include", "docs/PRD.md", "--format", "json"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["source_files"], 2)
        self.assertIsNone(report["prior_counts"])
        self.assertFalse(report["execution_performed"])
        self.assertFalse((self.work / "product/product-binding.json").exists())
        self.assertFalse((self.work / "product/src/core.ts").exists())
        status = subprocess.run([sys.executable, str(ROOT / "skills/remorsearch-ux-qa/scripts/ux_personas.py"),
                                 "status", "--work", str(self.work), "--format", "json"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout), report)

    def test_world_writable_workspace_is_refused_without_permission_changes(self):
        self.work.mkdir()
        self.work.chmod(0o777)
        with self.assertRaises(EngineError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.issue["code"], "workspace_permissions")
        self.assertEqual(self.work.stat().st_mode & 0o777, 0o777)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_real_library_reuse_preserves_failure_and_exact_version(self):
        imported = self.saved()
        before = self.hashes(self.source)
        report = self.prepare()
        self.assertEqual(report["personas_reused"][0]["profile_sha256"], imported["profile_sha256"])
        self.assertEqual(report["personas_reused"][0]["revision"], imported["revision"])
        self.assertEqual(report["prior_counts"]["failed"], 1)
        self.assertEqual(report["prior_counts"]["passed"], 0)
        self.assertEqual(report["prior_tasks"][0]["attempts"], 1)
        self.assertEqual(report["findings"][0]["failed_criteria"][0]["status"], "failed")
        self.assertFalse(report["product_ready"])
        self.assertEqual(before, self.hashes(self.source))

    def test_repeated_start_does_not_replace_copied_files_or_report(self):
        first = self.prepare()
        p = self.work / "product/README.md"
        stamp = p.stat().st_mtime_ns
        second = self.prepare()
        self.assertEqual(first, second)
        self.assertEqual(p.stat().st_mtime_ns, stamp)
        self.assertEqual(len(list((self.work / "reports").glob("*.md"))), 1)

    def test_interrupted_copy_resumes_without_overwriting_completed_file(self):
        def interrupt(_):
            raise OSError("Owned copy interruption")
        with self.assertRaises(OSError):
            self.prepare(fault=interrupt)
        p = self.work / "product/README.md"
        before = (p.read_bytes(), p.stat().st_mtime_ns)
        with self.assertRaises(EngineError) as caught:
            workspace.status(self.work)
        self.assertEqual(caught.exception.issue["code"], "preparation_interrupted")
        report = self.prepare()
        self.assertTrue(report["preparation_complete"])
        self.assertEqual(before, (p.read_bytes(), p.stat().st_mtime_ns))

    def test_changed_source_during_copy_is_not_published_as_ready(self):
        def mutate(name):
            if name == "product/README.md":
                atomic(self.product / "README.md", b"Changed owned input")
        with self.assertRaises(EngineError) as caught:
            self.prepare(fault=mutate)
        self.assertEqual(caught.exception.issue["code"], "source_changed")
        self.assertEqual(workspace._state(self.work)["phase"], "copying")
        self.assertFalse((self.work / "reports").exists())

    def test_changed_copy_is_not_overwritten(self):
        self.prepare()
        p = self.work / "product/README.md"
        atomic(p, b"Independent owned edit")
        with self.assertRaises(EngineError):
            self.prepare()
        self.assertEqual(p.read_bytes(), b"Independent owned edit")

    def test_nonempty_foreign_workspace_is_untouched(self):
        self.work.mkdir()
        atomic(self.work / "existing.txt", b"Keep")
        before = self.hashes(self.work)
        with self.assertRaises(EngineError):
            self.prepare()
        self.assertEqual(before, self.hashes(self.work))

    def test_overlapping_workspace_is_refused(self):
        with self.assertRaises(EngineError):
            workspace.prepare(self.source, self.source / "review", selected=self.recipe)
        self.assertFalse((self.source / "review").exists())

    def test_missing_source_has_actionable_cli_error_not_traceback(self):
        result = subprocess.run([sys.executable, str(ROOT / "skills/remorsearch-ux-qa/scripts/ux_personas.py"),
                                 "start", "--source", str(self.root / "missing"), "--work", str(self.work)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertIn("다음 단계", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.work.exists())

    def test_traversal_and_sensitive_names_are_not_opened(self):
        for path in ("../private.txt", "/private.txt", "src/../../private.txt", ".env",
                     "node_modules/pkg/index.js", "credentials.json", "data/key.pem"):
            with self.subTest(path=path), self.assertRaises(EngineError):
                workspace.read_file(self.source, path)

    def test_symlink_file_and_parent_are_not_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        atomic(outside / "file.txt", b"Do not copy")
        (self.source / "file.txt").symlink_to(outside / "file.txt")
        (self.source / "linked").symlink_to(outside, target_is_directory=True)
        for rel in ("file.txt", "linked/file.txt"):
            with self.subTest(rel=rel), self.assertRaises(EngineError):
                workspace.read_file(self.source, rel)

    def test_symlink_source_root_is_refused(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(EngineError):
            workspace.prepare(alias, self.work, selected=self.recipe)
        self.assertFalse(self.work.exists())

    def test_hardlink_and_special_file_are_refused(self):
        atomic(self.root / "outside.txt", b"Owned external file")
        os.link(self.root / "outside.txt", self.source / "hard.txt")
        os.mkfifo(self.source / "pipe")
        for rel in ("hard.txt", "pipe"):
            with self.subTest(rel=rel), self.assertRaises(EngineError):
                workspace.read_file(self.source, rel)

    def test_key_content_and_large_file_are_refused(self):
        atomic(self.source / "owned.txt", ("sk-proj-" + "a" * 24).encode())
        with self.assertRaises(EngineError) as caught:
            workspace.read_file(self.source, "owned.txt", sensitive_check=True)
        self.assertEqual(caught.exception.issue["code"], "sensitive_content")
        with (self.source / "large.txt").open("wb") as stream:
            stream.truncate(workspace.MAX_FILE + 1)
        with self.assertRaises(EngineError):
            workspace.read_file(self.source, "large.txt")

    def test_extra_keys_dependencies_and_unreferenced_logs_are_not_copied(self):
        atomic(self.source / ".env", b"Owned exclusion")
        (self.source / "node_modules").symlink_to(self.root, target_is_directory=True)
        atomic(self.source / "unrelated.json", b"Owned excluded record")
        self.prepare()
        self.assertFalse((self.work / ".env").exists())
        self.assertFalse((self.work / "node_modules").exists())
        self.assertFalse((self.work / "unrelated.json").exists())

    def test_external_prd_binding_is_blocked_before_library_reads(self):
        self.saved()
        path = self.source / "persona-library/library.json"
        envelope = json.loads(path.read_text())
        record = next(iter(envelope["state"]["entries"].values()))[-1]
        record["context"]["prd_path"] = str(self.root / "unapproved.md")
        envelope["sha256"] = digest(envelope["state"])
        atomic(path, canonical(envelope))
        with self.assertRaises(EngineError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.issue["code"], "saved_scope")
        self.assertFalse(self.work.exists())

    def test_expired_persona_cannot_be_reused_to_refresh_a_result(self):
        self.saved()
        path = self.source / "persona-library/library.json"
        envelope = json.loads(path.read_text())
        next(iter(envelope["state"]["entries"].values()))[-1]["review_after"] = 0
        envelope["sha256"] = digest(envelope["state"])
        atomic(path, canonical(envelope))
        before = self.hashes(self.source)
        with self.assertRaises(EngineError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.issue["code"], "persona_review_due")
        self.assertEqual(before, self.hashes(self.source))
        self.assertFalse((self.work / "reports").exists())

    def test_changed_saved_evidence_is_refused(self):
        self.saved()
        atomic(self.source / "persona-run/evidence/T-KEEP/1/owned.log", b"Altered owned evidence")
        with self.assertRaises(EngineError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.issue["code"], "evidence_changed")

    def test_external_build_binding_is_refused(self):
        self.saved()
        path = self.source / "persona-run/swarm-state.json"
        envelope = json.loads(path.read_text())
        envelope["payload"]["build"]["artifact_path"] = str(self.root / "unapproved.json")
        envelope["sha256"] = digest(envelope["payload"])
        atomic(path, canonical(envelope))
        with self.assertRaises(EngineError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.issue["code"], "saved_scope")

    def test_artifact_path_cannot_escape_its_attempt(self):
        self.saved()
        path = self.source / "persona-run/swarm-state.json"
        envelope = json.loads(path.read_text())
        envelope["payload"]["tasks"][0]["receipt"]["artifacts"][0]["path"] = "evidence/T-KEEP/1/../../../outside.log"
        envelope["sha256"] = digest(envelope["payload"])
        atomic(path, canonical(envelope))
        with self.assertRaises(EngineError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.issue["code"], "source_path")

    def test_active_prior_task_cannot_be_cloned_to_reset_attempts(self):
        self.saved()
        with Library(self.source / "persona-library") as library:
            swarm.retry(library, self.source / "persona-run", "T-KEEP")
        before = self.hashes(self.source)
        with self.assertRaises(EngineError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.issue["code"], "run_active")
        self.assertEqual(before, self.hashes(self.source))

    def test_two_callers_cannot_publish_different_workspaces(self):
        def start(_):
            try:
                return self.prepare()["preparation_complete"]
            except EngineError as exc:
                self.assertIn(exc.issue["code"], {"workspace_occupied", "lock_busy"})
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(start, range(2)))
        self.assertIn(True, results)
        self.assertTrue(self.prepare()["preparation_complete"])
        self.assertEqual(len(list((self.work / "reports").glob("*.md"))), 1)


if __name__ == "__main__":
    unittest.main()
