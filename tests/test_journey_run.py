"""Owned subprocess observations, not human or browser UX evidence."""
import json
import os
import copy
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/remorsearch-ux-qa"))
from uxpersonas import workspace, local_run, swarm
from uxpersonas.library import Library
from uxresearch.canonical import EngineError, byte_digest, canonical, digest
from uxresearch.storage import atomic

_spec = importlib.util.spec_from_file_location("journey_fixture", ROOT / "skills/remorsearch-ux-qa/examples/journey/fixture.py")
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)
RUNNER = fixture.RUNNER


class JourneyRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.__dict__.update(fixture.build(self.root / "case"))
        workspace.prepare(self.source, self.work, reviewed_files=["PRD.md", "product.py", "adapter.py"])

    def command(self, *extra):
        return [sys.executable, str(ROOT / "skills/remorsearch-ux-qa/scripts/ux_personas.py"),
                "run", "--work", str(self.work), "--format", "json", *extra]

    def test_installed_entry_executes_goals_and_reports_observed_failure(self):
        result = subprocess.run(self.command("--library", str(self.library), "--input", str(self.plan_path),
                                "--allow-reviewed-local-runner"), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema_version"], "ux-journey-run-report.v1")
        self.assertTrue(report["execution_performed"])
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertEqual(len(report["personas_reused"]), 2)
        self.assertFalse(report["ui_observed"])
        self.assertFalse(report["real_user_evidence"])
        self.assertFalse(report["product_ready"])
        self.assertTrue(Path(report["report_path"]).is_file())

    def execute(self, **kw):
        return local_run.execute(self.work, library_path=self.library, input_path=self.plan_path, approved=True, **kw)

    def variant(self, runner, *, one_task=False, timeout=3):
        # An independently reviewed fixture workspace, never mutate a live run.
        atomic(self.source / "adapter.py", runner.encode())
        self.work = self.root / "variant"
        self.plan["timeout_seconds"] = timeout
        if one_task:
            self.plan["tasks"] = self.plan["tasks"][:1]
        atomic(self.plan_path, canonical(self.plan))
        workspace.prepare(self.source, self.work, reviewed_files=["PRD.md", "product.py", "adapter.py"])

    def test_repeated_run_start_status_preserve_evidence_and_original_library(self):
        before = {p.name: p.read_bytes() for p in self.library.iterdir()}
        first = self.execute()
        files = {str(p.relative_to(self.work)): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.work.rglob("*") if p.is_file()}
        with patch.object(local_run, "_invoke", side_effect=AssertionError("duplicate dispatch")):
            self.assertEqual(first, local_run.execute(self.work))
            self.assertEqual(first, workspace.status(self.work))
            self.assertEqual(first, workspace.prepare(self.source, self.work, reviewed_files=["PRD.md", "product.py", "adapter.py"]))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.library.iterdir()})
        for rel, expected in files.items():
            p = self.work / rel
            self.assertEqual(expected, (p.read_bytes(), p.stat().st_mtime_ns), rel)
        self.assertEqual(first["coverage"]["obligations"]["failed"], 1)
        self.assertEqual(first["coverage"]["obligations"]["not_run"], 2)
        self.assertFalse(first["coverage"]["all_declared_requirements_passed"])

    def test_report_links_actual_observation_and_exact_existing_personas(self):
        report = self.execute()
        expected = {r["persona_id"]: (r["revision"], r["profile_sha256"]) for r in self.imported["imported"]}
        for row in report["personas_reused"]:
            self.assertEqual((row["revision"], row["profile_sha256"]), expected[row["persona_id"]])
        failed = next(t for t in report["tasks"] if t["status"] == "failed")
        artifact = failed["result"]["artifacts"][0]
        evidence = self.work / local_run.DIRECTORY / "run" / artifact["path"]
        self.assertEqual(byte_digest(evidence.read_bytes()), artifact["sha256"])
        observed = json.loads(evidence.read_bytes())
        self.assertIsNone(observed["diagnostic"]["problem"])
        self.assertEqual(observed["observation"]["criteria"][0]["observation"], "Earlier item lost after rejected input")
        markdown = Path(report["report_path"]).read_text()
        self.assertIn("Keep earlier items", markdown)
        self.assertIn(artifact["path"], markdown)
        self.assertIn("not_run", markdown)

    def test_multi_persona_report_exposes_a_separate_swarm_evidence_audit(self):
        report = self.execute()
        audit = report["evidence_audit"]
        self.assertEqual(audit["basis"], "deterministic_receipt_and_cross_persona_audit")
        self.assertEqual(audit["integrity"], "consistent")
        self.assertFalse(audit["independent_reviewer"])
        self.assertEqual(audit["obligations"]["conflicted"], 0)
        self.assertEqual(audit["obligations"]["definition_conflicts"], 1)
        self.assertGreaterEqual(audit["obligations"]["incomplete"], 2)

    def _shared_obligation_report(self, runner):
        self.variant(runner)
        for task in self.plan["tasks"]:
            task["requirement_coverage"][0]["obligations"][0]["description"] = "Preserve the same existing item after validation."
        atomic(self.plan_path, canonical(self.plan))
        return self.execute()

    def test_identical_observations_from_two_personas_are_not_counted_as_two_signals(self):
        report = self._shared_obligation_report(RUNNER.replace('if request["task"]["id"] == "T-RETURN":', "if False:"))
        audit = report["evidence_audit"]
        self.assertEqual(audit["obligations"]["duplicated"], 1)
        duplicate = audit["duplicates"][0]
        self.assertEqual(set(duplicate["task_ids"]), {"T-EXPLORE", "T-RETURN"})
        self.assertEqual(duplicate["distinct_observations"], 1)
        self.assertIn("중복 관측", Path(report["report_path"]).read_text())

    def test_contradictory_persona_observations_remain_unresolved(self):
        report = self._shared_obligation_report(RUNNER)
        audit = report["evidence_audit"]
        self.assertEqual(audit["obligations"]["conflicted"], 1)
        conflict = audit["conflicts"][0]
        self.assertEqual(set(conflict["statuses"]), {"passed", "failed"})
        self.assertEqual(set(conflict["task_ids"]), {"T-EXPLORE", "T-RETURN"})
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertIn("상충 관측", Path(report["report_path"]).read_text())
        self.assertIn("종합 판정을 보류", report["next_action"])

    def test_same_obligation_id_and_wording_with_different_criteria_is_not_compared(self):
        self.variant(RUNNER)
        for task in self.plan["tasks"]:
            task["requirement_coverage"][0]["obligations"][0]["description"] = "Same wording, different criterion mapping."
        self.plan["tasks"][1]["requirement_coverage"][0]["obligations"][0]["criterion_refs"] = [
            {"kind": "recovery", "index": 0}]
        atomic(self.plan_path, canonical(self.plan))
        report = self.execute()
        audit = report["evidence_audit"]
        self.assertEqual(audit["obligations"]["definition_conflicts"], 1)
        self.assertEqual(audit["obligations"]["conflicted"], 0)

    def test_receipt_artifact_hash_cannot_hide_observation_receipt_disagreement(self):
        self.execute()
        state = local_run._read(self.work)
        task_id = "T-EXPLORE"
        run = self.work / local_run.DIRECTORY / "run"
        swarm_path = run / "swarm-state.json"
        envelope = json.loads(swarm_path.read_bytes())
        swarm_state = envelope["payload"]
        entry = next(row for row in swarm_state["tasks"] if row["task"]["id"] == task_id)
        artifact = entry["receipt"]["artifacts"][0]
        evidence_path = run / artifact["path"]
        evidence = json.loads(evidence_path.read_bytes())
        evidence["observation"]["criteria"][0]["observation"] = "A different observation not present in the receipt."
        raw = canonical(evidence)
        atomic(evidence_path, raw)
        artifact["sha256"] = byte_digest(raw)
        atomic(swarm_path, swarm._state_bytes(swarm_state))
        report = local_run.execute(self.work)
        audit = report["evidence_audit"]
        self.assertEqual(audit["integrity"], "blocked")
        self.assertIn(dict(code="execution_evidence_mismatch", task_id=task_id), audit["issues"])
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertIn("로그와 receipt", report["next_action"])

    def test_missing_approval_and_missing_persona_never_create_execution(self):
        with self.assertRaises(EngineError) as caught:
            local_run.execute(self.work, library_path=self.library, input_path=self.plan_path)
        self.assertEqual(caught.exception.issue["code"], "runner_approval")
        self.assertFalse((self.work / local_run.MARKER).exists())
        self.plan["tasks"][0]["persona_id"] = "PER-MISSING"
        atomic(self.plan_path, canonical(self.plan))
        with self.assertRaises(EngineError):
            self.execute()
        self.assertFalse((self.work / local_run.MARKER).exists())

    def test_unmapped_obligation_and_unknown_plan_fields_refused_before_dispatch(self):
        for mutation in (lambda p: p.update(command="unsafe"), lambda p: p["tasks"][0].pop("requirement_coverage")):
            plan = copy.deepcopy(self.plan)
            mutation(plan)
            atomic(self.plan_path, canonical(plan))
            with self.assertRaises(EngineError):
                self.execute()
            self.assertFalse((self.work / local_run.MARKER).exists())

    def test_source_and_copied_runner_changes_refused_before_dispatch(self):
        for path in (self.source / "adapter.py", self.work / "product/adapter.py"):
            original = path.read_bytes()
            atomic(path, original + b"\n# changed\n")
            with self.assertRaises(EngineError), patch.object(local_run, "_invoke", side_effect=AssertionError("unreviewed")):
                self.execute()
            atomic(path, original)
        self.assertFalse((self.work / local_run.MARKER).exists())

    def test_library_change_after_completed_run_blocks_readback_without_overwrite(self):
        report = self.execute()
        old_report = Path(report["report_path"]).read_bytes()
        with Library(self.library) as library:
            library.retire("owned-product", "PER-RETURN", "Synthetic review withdrawal")
        with self.assertRaises(EngineError):
            local_run.execute(self.work)
        self.assertEqual(Path(report["report_path"]).read_bytes(), old_report)

    def test_stale_persona_is_not_relabelled_as_current(self):
        path = self.library / "library.json"
        env = json.loads(path.read_bytes())
        env["state"]["entries"]["owned-product/PER-RETURN"][-1]["review_after"] = 1
        env["sha256"] = digest(env["state"])
        atomic(path, canonical(env))
        with self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "persona_review_due")
        self.assertFalse((self.work / local_run.MARKER).exists())

    def test_external_prd_and_research_reference_refused_before_validation_reads(self):
        path = self.library / "library.json"
        original = path.read_bytes()
        for research in (False, True):
            env = json.loads(original)
            record = env["state"]["entries"]["owned-product/PER-EXPLORE"][-1]
            if research:
                record["provenance"] = dict(mode="gated_research", claim_ids=[], research={"run": "/unapproved/research"})
            else:
                record["context"]["prd_path"] = str(self.root / "unreviewed-PRD.md")
            env["sha256"] = digest(env["state"])
            atomic(path, canonical(env))
            with patch.object(Library, "_validate", side_effect=AssertionError("external read")), self.assertRaises(EngineError) as caught:
                self.execute()
            self.assertEqual(caught.exception.issue["code"], "persona_scope")

    def test_nonzero_exit_is_infrastructure_uncertainty(self):
        self.variant("raise SystemExit(7)\n", one_task=True)
        report = self.execute()
        task = report["tasks"][0]
        self.assertEqual(task["status"], "inconclusive")
        self.assertIn("nonzero_exit", task["reason"])
        self.assertTrue(all(r["status"] == "not_run" for r in task["result"]["criteria"]))

    def test_exit_zero_without_observations_never_passes(self):
        self.variant("pass\n", one_task=True)
        report = self.execute()
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertEqual(report["counts"]["failed"], 0)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertIn("invalid_or_private_observation", report["tasks"][0]["reason"])

    def test_wrong_attempt_binding_never_becomes_product_failure(self):
        self.variant(RUNNER.replace('"binding": request["binding"]', '"binding": {**request["binding"], "attempt": 99}'), one_task=True)
        report = self.execute()
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertEqual(report["counts"]["failed"], 0)

    def test_sensitive_output_is_not_saved_or_echoed(self):
        secret = "sk-proj-" + "X" * 36
        self.variant('print("sk-" + "proj-" + "X" * 36)\n', one_task=True)
        report = self.execute()
        self.assertEqual(report["counts"]["inconclusive"], 1)
        for base in (self.work / "reports", self.work / local_run.DIRECTORY):
            for path in base.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret.encode(), path.read_bytes())

    def test_environment_credentials_and_python_path_are_not_inherited(self):
        self.variant('import os\nassert "JOURNEY_PRIVATE_SENTINEL" not in os.environ\nassert "PYTHONPATH" not in os.environ\n' + RUNNER, one_task=True)
        with patch.dict(os.environ, {"JOURNEY_PRIVATE_SENTINEL": "owned-only", "PYTHONPATH": "/unapproved"}):
            report = self.execute()
        self.assertIn("Local core observations", report["tasks"][0]["reason"])

    def test_output_limit_and_timeout_remain_bounded_inconclusive(self):
        self.variant('import sys\nwhile True: sys.stdout.write("x" * 16384); sys.stdout.flush()\n', one_task=True, timeout=1)
        start = time.monotonic()
        report = self.execute()
        self.assertLess(time.monotonic() - start, 5)
        self.assertIn("output_limit", report["tasks"][0]["reason"])

    def test_timeout_stops_only_owned_child_and_no_retry_on_repeat(self):
        self.variant('import os, pathlib, time\npathlib.Path("child-pid").write_text(str(os.getpid()))\ntime.sleep(30)\n', one_task=True, timeout=1)
        report = self.execute()
        self.assertIn("timeout", report["tasks"][0]["reason"])
        pid_file = next((self.work / local_run.DIRECTORY).rglob("child-pid"))
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)
        with patch.object(local_run, "_invoke", side_effect=AssertionError("timeout replay")):
            self.assertEqual(report, local_run.execute(self.work))

    def test_dispatch_intent_crash_is_unknown_never_automatically_replayed(self):
        def crash(point):
            if point == "intent":
                raise RuntimeError("owned crash injection")
        with self.assertRaises(RuntimeError):
            self.execute(fault=crash)
        with patch.object(local_run, "_invoke", side_effect=AssertionError("unknown replay")):
            report = local_run.execute(self.work)
            self.assertEqual(report, workspace.status(self.work))
        self.assertEqual(report["uncertain_dispatches"], ["T-EXPLORE"])
        self.assertFalse(report["execution_complete"])
        self.assertIsNone(report["execution_performed"])
        self.assertEqual(report["tasks"][0]["attempts"], 1)
        self.assertEqual(report["tasks"][1]["attempts"], 0)

    def test_claim_journal_gap_is_not_a_new_attempt(self):
        save = local_run._save
        def crash(work, state):
            if state["dispatches"]:
                raise RuntimeError("owned journal failure")
            save(work, state)
        with patch.object(local_run, "_save", side_effect=crash), self.assertRaises(RuntimeError):
            self.execute()
        with patch.object(local_run, "_invoke", side_effect=AssertionError("claim replay")):
            report = local_run.execute(self.work)
        self.assertEqual(report["uncertain_dispatches"], ["T-EXPLORE"])
        self.assertEqual(report["tasks"][0]["attempts"], 1)

    def test_receipt_ack_loss_recovers_by_readback_then_only_runs_pending_task(self):
        def crash(point):
            if point == "recorded":
                raise RuntimeError("owned ACK loss")
        with self.assertRaises(RuntimeError):
            self.execute(fault=crash)
        log = self.work / local_run.DIRECTORY / "run/evidence/T-EXPLORE/1/observation.json"
        original = (log.read_bytes(), log.stat().st_mtime_ns)
        invoke = local_run._invoke
        requests = []
        def track(*args):
            requests.append(args[2]["binding"]["task_id"])
            return invoke(*args)
        with patch.object(local_run, "_invoke", side_effect=track):
            report = local_run.execute(self.work)
        self.assertEqual(requests, ["T-RETURN"])
        self.assertTrue(report["execution_complete"])
        self.assertEqual(original, (log.read_bytes(), log.stat().st_mtime_ns))
        self.assertTrue(all(t["attempts"] == 1 for t in report["tasks"]))

    def test_concurrent_cli_callers_do_not_dispatch_twice(self):
        self.variant('import pathlib, time\np = pathlib.Path("launches")\np.write_text(p.read_text() + "one\\n" if p.exists() else "one\\n")\ntime.sleep(0.2)\n' + RUNNER)
        command = self.command("--library", str(self.library), "--input", str(self.plan_path), "--allow-reviewed-local-runner")
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        outputs = [p.communicate(timeout=15) for p in processes]
        self.assertEqual([p.returncode for p in processes], [1, 1], outputs)
        self.assertEqual(json.loads(outputs[0][0]), json.loads(outputs[1][0]))
        launches = list((self.work / local_run.DIRECTORY).rglob("launches"))
        self.assertEqual(len(launches), 2)
        self.assertTrue(all(p.read_text() == "one\n" for p in launches))

    def test_cancel_owned_execution_publishes_uncertainty_and_stops_child(self):
        self.variant('import os, pathlib, time\npathlib.Path("child-pid").write_text(str(os.getpid()))\ntime.sleep(30)\n', one_task=True, timeout=10)
        process = subprocess.Popen(self.command("--library", str(self.library), "--input", str(self.plan_path), "--allow-reviewed-local-runner"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not list((self.work / local_run.DIRECTORY).rglob("child-pid")) and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(list((self.work / local_run.DIRECTORY).rglob("child-pid")))
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 1, stderr)
            report = json.loads(stdout)
            self.assertIn("cancelled", report["tasks"][0]["reason"])
            pid = int(next((self.work / local_run.DIRECTORY).rglob("child-pid")).read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def test_changed_plan_and_occupied_execution_directory_preserve_existing_files(self):
        occupied = self.work / local_run.DIRECTORY
        occupied.mkdir(mode=0o700)
        atomic(occupied / "keep.txt", b"owned unrelated state")
        with self.assertRaises(EngineError):
            self.execute()
        self.assertEqual((occupied / "keep.txt").read_bytes(), b"owned unrelated state")
        self.assertFalse((self.work / local_run.MARKER).exists())

    def test_frozen_plan_cannot_change_after_a_recorded_failure(self):
        self.execute()
        self.plan["tasks"][1]["success_criteria"] = ["Changed after seeing the result"]
        atomic(self.plan_path, canonical(self.plan))
        with self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "execution_contract")
        self.assertEqual(workspace.status(self.work)["counts"]["failed"], 1)

    def test_symlink_or_hardlinked_library_is_refused(self):
        for hard in (False, True):
            alternate = self.root / ("hard" if hard else "link")
            alternate.mkdir(mode=0o700)
            if hard:
                os.link(self.library / "library.json", alternate / "library.json")
            else:
                (alternate / "library.json").symlink_to(self.library / "library.json")
            with self.assertRaises((EngineError, OSError)):
                local_run.execute(self.work, library_path=alternate, input_path=self.plan_path, approved=True)
        self.assertFalse((self.work / local_run.MARKER).exists())

    def test_empty_directory_preparation_runs_without_changing_its_permissions(self):
        self.work = self.root / "empty-directory"
        self.work.mkdir(mode=0o755)
        mode = self.work.stat().st_mode
        workspace.prepare(self.source, self.work, reviewed_files=["PRD.md", "product.py", "adapter.py"])
        report = self.execute()
        self.assertTrue(report["execution_complete"])
        self.assertEqual(self.work.stat().st_mode, mode)
        self.assertEqual((self.work / local_run.MARKER).stat().st_mode & 0o077, 0)
        self.assertEqual((self.work / local_run.DIRECTORY).stat().st_mode & 0o077, 0)

    def test_world_writable_work_is_refused_without_permission_changes(self):
        self.work.chmod(0o777)
        with self.assertRaises(EngineError):
            self.execute()
        self.assertEqual(self.work.stat().st_mode & 0o777, 0o777)
        self.assertFalse((self.work / local_run.MARKER).exists())

    def test_interrupted_execution_preparation_resumes_same_fixed_plan(self):
        with patch.object(local_run, "_finish_preparation", side_effect=RuntimeError("owned preparation interruption")), self.assertRaises(RuntimeError):
            self.execute()
        status = workspace.status(self.work)
        self.assertEqual(status["counts"]["pending"], 2)
        self.assertFalse(status["execution_performed"])
        report = local_run.execute(self.work)
        self.assertTrue(report["execution_complete"])
        self.assertEqual(report["plan_sha256"], status["plan_sha256"])

    def test_unknown_attempt_stays_unknown_after_lease_expiry(self):
        with self.assertRaises(RuntimeError):
            self.execute(fault=lambda point: (_ for _ in ()).throw(RuntimeError("owned interruption")))
        with patch("uxpersonas.swarm.time.time", return_value=time.time() + 200), patch.object(local_run, "_invoke", side_effect=AssertionError("expired replay")):
            report = local_run.execute(self.work)
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertEqual(report["uncertain_dispatches"], ["T-EXPLORE"])
        self.assertEqual(report["tasks"][0]["attempts"], 1)

    def test_unconfirmed_cleanup_keeps_dispatch_unknown_and_blocks_remaining_work(self):
        stop_owned = local_run._stop_owned
        def unconfirmed(process):
            self.assertTrue(stop_owned(process))
            return False  # Exercise the uncertainty branch with no leaked process.
        with patch.object(local_run, "_stop_owned", side_effect=unconfirmed), self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "execution_cleanup")
        with patch.object(local_run, "_invoke", side_effect=AssertionError("unconfirmed replay")):
            report = local_run.execute(self.work)
        self.assertEqual(report["uncertain_dispatches"], ["T-EXPLORE"])
        self.assertEqual(report["tasks"][1]["attempts"], 0)

    def test_existing_saved_experiment_cannot_reset_its_attempt_budget(self):
        import test_journey_entry as fixtures
        prior = fixtures.JourneyEntryTests("test_empty_start_creates_private_report_without_source_mutation")
        prior.setUp()
        self.addCleanup(prior.doCleanups)
        prior.saved()
        prior.prepare()
        before = prior.hashes(prior.source)
        with self.assertRaises(EngineError) as caught:
            local_run.execute(prior.work, library_path=prior.source / "persona-library", input_path=self.plan_path, approved=True)
        self.assertEqual(caught.exception.issue["code"], "prior_run_preserved")
        self.assertEqual(before, prior.hashes(prior.source))
        self.assertFalse((prior.work / local_run.MARKER).exists())

    def test_all_observed_core_criteria_still_cannot_claim_full_qa_pass(self):
        self.plan["tasks"] = self.plan["tasks"][:1]
        self.plan["tasks"][0]["recovery_criteria"] = ["Candidate remains readable in memory"]
        atomic(self.plan_path, canonical(self.plan))
        self.variant(RUNNER.replace('"status": "not_run", "observation": "Browser recovery was not observed"',
                                   '"status": "passed" if items == ["candidate"] else "failed", "observation": "Candidate read from memory"'), one_task=True)
        report = self.execute()
        self.assertTrue(all(row["status"] == "passed" for row in report["tasks"][0]["result"]["criteria"]))
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertFalse(report["coverage"]["all_declared_requirements_passed"])

    def test_uncertain_owned_write_does_not_release_shared_resource(self):
        for task in self.plan["tasks"]:
            task["side_effects"] = "owned_fixture_write"
            task["resource_id"] = "shared-owned-fixture"
        atomic(self.plan_path, canonical(self.plan))
        report = self.execute()
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertEqual(report["counts"]["pending"], 1)
        self.assertTrue(report["quarantined_tasks"])
        self.assertIn("settle", report["next_action"])
        with patch.object(local_run, "_invoke", side_effect=AssertionError("quarantine bypass")):
            self.assertEqual(report, local_run.execute(self.work))

    def test_unreviewed_added_file_in_copy_is_preserved_but_blocks_dispatch(self):
        extra = self.work / "product/unreviewed.py"
        atomic(extra, b"UNREVIEWED = True\n")
        with patch.object(local_run, "_invoke", side_effect=AssertionError("unreviewed scope")), self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "reviewed_copy_scope")
        self.assertEqual(extra.read_bytes(), b"UNREVIEWED = True\n")
        self.assertFalse((self.work / local_run.MARKER).exists())

    def test_unreviewed_directory_link_is_never_followed_or_deleted(self):
        outside = self.root / "outside-reviewed-source"
        outside.mkdir(mode=0o700)
        atomic(outside / "keep.txt", b"owned unreviewed input")
        link = self.work / "product/added-directory"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "reviewed_copy_scope")
        self.assertTrue(link.is_symlink())
        self.assertEqual((outside / "keep.txt").read_bytes(), b"owned unreviewed input")
        self.assertFalse((self.work / local_run.MARKER).exists())


if __name__ == "__main__":
    unittest.main()
