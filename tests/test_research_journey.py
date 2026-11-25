"""Owned offline research contracts + actual local adapters; no real user evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import _paths
from test_journey_run import fixture
from test_persona_evidence_admission import research_fixture
from uxpersonas import local_run, workspace
from uxpersonas.library import Library, PROFILE_FIELDS
from uxresearch.canonical import EngineError, canonical, digest
from uxresearch.storage import Store, atomic, read_json


def attach_research(case, root, *, relation="support"):
    root.mkdir(mode=0o700)
    research, bundle, gate, _ = research_fixture(root, relation=relation)
    claim_id = bundle["records"]["claims"][0]["id"]
    with Library(case["library"]) as library:
        originals = [library.get("owned-product", task["persona_id"]) for task in case["tasks"]]
        profiles = []
        for record in originals:
            profile = {key: copy.deepcopy(record["profile"][key]) for key in PROFILE_FIELDS}
            profile["assumptions"] = ["Owned offline research-contract fixture; not actual public research"]
            profiles.append(dict(persona_id=record["persona_id"], claim_ids=[claim_id], **profile))
        imported = library.import_profiles(dict(
            schema_version="ux-persona-library-input.v1", product_id="owned-product",
            mode="gated_research", context=originals[0]["context"], personas=profiles,
            research=dict(run=str(research), bundle=str(research / "bundle.json"), gate=str(research / "gate.json"))))
    return research, imported


class ResearchJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.case = fixture.build(self.root / "case")
        self.research, self.imported = attach_research(self.case, self.root / "evidence")
        workspace.prepare(self.case["source"], self.case["work"], reviewed_files=fixture.FILES)

    def command(self, *, review=True):
        return [sys.executable, str(_paths.SKILL / "scripts/ux_personas.py"),
                "run", "--work", str(self.case["work"]), "--library", str(self.case["library"]),
                "--input", str(self.case["plan_path"]), "--allow-reviewed-local-runner",
                "--format", "json", *(["--reviewed-research-run", str(self.research)] if review else [])]

    def test_reviewed_research_personas_reach_current_execution_and_report(self):
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["execution_performed"])
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(report["counts"]["inconclusive"], 1)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertEqual(len(report["personas_reused"]), 2)
        self.assertFalse(report["ui_observed"])
        self.assertFalse(report["real_user_evidence"])
        for persona in report["personas_reused"]:
            self.assertEqual(persona["provenance_mode"], "gated_research")
            self.assertTrue(persona["research"]["claims"])
            self.assertIn("source_bundle_id", persona["research"])


    def execute(self, **extra):
        return local_run.execute(self.case["work"], library_path=self.case["library"],
            input_path=self.case["plan_path"], approved=True, reviewed_research_runs=[self.research], **extra)

    def snapshot(self, root):
        return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode & 0o777, path.stat().st_mtime_ns)
                for path in root.rglob("*") if path.is_file() and not path.is_symlink()}

    def withdraw(self, *, committed=True):
        bundle = read_json(self.research / "bundle.json")
        bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "withdrawn"
        if committed:
            with Store(self.research) as store:
                store.publish("owned-withdrawal", {"bundle.json": bundle})
        else:
            atomic(self.research / "bundle.json", canonical(bundle))

    def test_unreviewed_research_never_runs_or_follows_reference(self):
        with patch("uxpersonas.research_access.inspect_files", side_effect=AssertionError("unapproved read")):
            with self.assertRaises(EngineError) as caught:
                local_run.execute(self.case["work"], library_path=self.case["library"],
                    input_path=self.case["plan_path"], approved=True)
        self.assertEqual(caught.exception.issue["code"], "persona_scope")
        self.assertFalse((self.case["work"] / local_run.MARKER).exists())

    def test_original_research_library_modes_and_cache_are_preserved_on_restart(self):
        page = self.research / "pages/F-000000000001.txt"
        atomic(page, b"Owned expired cache; must not be inspected or removed by QA.")
        os.utime(page, (1, 1))
        before_research, before_library = self.snapshot(self.research), self.snapshot(self.case["library"])
        report = self.execute()
        before_work = self.snapshot(self.case["work"])
        with patch.object(local_run, "_invoke", side_effect=AssertionError("duplicate dispatch")):
            self.assertEqual(local_run.execute(self.case["work"]), report)
            self.assertEqual(workspace.status(self.case["work"]), report)
            self.assertEqual(workspace.prepare(self.case["source"], self.case["work"], reviewed_files=fixture.FILES), report)
        self.assertEqual(before_research, self.snapshot(self.research))
        self.assertEqual(before_library, self.snapshot(self.case["library"]))
        self.assertEqual(before_work, self.snapshot(self.case["work"]))
        self.assertTrue(page.is_file())
        self.assertFalse(any(path.name in {"pages", ".engine", "bundle.json", "gate.json"}
                             for path in self.case["work"].rglob("*")))

    def test_missing_or_extra_review_scope_cannot_create_original_state(self):
        missing = self.root / "missing"
        with self.assertRaises(EngineError):
            local_run.execute(self.case["work"], library_path=self.case["library"],
                input_path=self.case["plan_path"], approved=True, reviewed_research_runs=[missing])
        self.assertFalse(missing.exists())
        extra = self.root / "unused"
        extra.mkdir(mode=0o700)
        with self.assertRaises(EngineError) as caught:
            local_run.execute(self.case["work"], library_path=self.case["library"],
                input_path=self.case["plan_path"], approved=True, reviewed_research_runs=[self.research, extra])
        self.assertEqual(caught.exception.issue["code"], "research_scope")
        self.assertEqual(list(extra.iterdir()), [])

    def test_duplicate_nested_and_symlink_review_roots_are_refused(self):
        link = self.root / "research-link"
        link.symlink_to(self.research, target_is_directory=True)
        for roots in ([self.research, self.research], [self.research, self.research.parent], [link], [self.case["source"]]):
            with self.subTest(roots=roots), self.assertRaises(EngineError):
                local_run.execute(self.case["work"], library_path=self.case["library"],
                    input_path=self.case["plan_path"], approved=True, reviewed_research_runs=roots)
        self.assertTrue(link.is_symlink())
        self.assertFalse((self.case["work"] / local_run.MARKER).exists())

    def test_external_bundle_reference_is_refused_before_research_validation(self):
        path = self.case["library"] / "library.json"
        envelope = read_json(path)
        envelope["state"]["entries"]["owned-product/PER-EXPLORE"][-1]["provenance"]["research"]["bundle"] = str(self.root / "unreviewed.json")
        envelope["sha256"] = digest(envelope["state"])
        atomic(path, canonical(envelope))
        with patch("uxpersonas.research_access.inspect_files", side_effect=AssertionError("external read")), self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "research_scope")

    def test_missing_lock_is_not_created(self):
        lock = self.research / "engine.lock"
        lock.unlink()
        with self.assertRaises((EngineError, OSError)):
            self.execute()
        self.assertFalse(lock.exists())

    def test_unsafe_modes_are_not_repaired(self):
        lock = self.research / "engine.lock"
        lock.chmod(0o644)
        with self.assertRaises(EngineError):
            self.execute()
        self.assertEqual(lock.stat().st_mode & 0o777, 0o644)

    def test_hardlink_and_symlink_metadata_are_refused(self):
        path = self.research / "hosts.json"
        original = path.read_bytes()
        target = self.root / "owned-hosts.json"
        atomic(target, original)
        for kind in ("hard", "symbolic"):
            path.unlink()
            if kind == "hard":
                os.link(target, path)
            else:
                path.symlink_to(target)
            with self.subTest(kind=kind), self.assertRaises(EngineError):
                self.execute()
            path.unlink()
            atomic(path, original)
        self.assertEqual(target.read_bytes(), original)

    def test_oversized_metadata_is_not_loaded(self):
        path = self.research / "hosts.json"
        with path.open("r+b") as stream:
            stream.truncate(workspace.MAX_FILE + 1)
        with self.assertRaises(EngineError):
            self.execute()
        self.assertFalse((self.case["work"] / local_run.MARKER).exists())

    def test_generation_reference_cannot_escape_fixed_snapshot_names(self):
        path = self.research / "engine-state.json"
        state = read_json(path)
        state["outputs"]["gate.json"]["generation_path"] = ".engine/unreviewed.txt"
        atomic(path, canonical(state))
        with self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "research_snapshot")

    def test_corrupt_generation_blocks_before_dispatch(self):
        state = read_json(self.research / "engine-state.json")
        path = self.research / state["outputs"]["gate.json"]["generation_path"]
        atomic(path, path.read_bytes() + b" ")
        with patch.object(local_run, "_invoke", side_effect=AssertionError("dispatch")), self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "snapshot")

    def test_failed_latest_gate_is_not_rescued_by_saved_personas(self):
        atomic(self.research / "gate_failed.json", canonical({"owned": "failed attempt"}))
        with self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "failed_gate")
        self.assertFalse((self.case["work"] / local_run.MARKER).exists())

    def test_invalid_policy_returns_safe_cli_blocker_without_traceback(self):
        path = self.research / "run.json"
        state = read_json(path)
        state["policy_sha256"] = "0" * 64
        atomic(path, canonical(state))
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["issue"]["code"], "research_policy")
        self.assertNotIn("Traceback", result.stderr)

    def test_committed_and_pending_withdrawal_preserve_original_and_reports(self):
        report = self.execute()
        old_report = Path(report["report_path"]).read_bytes()
        self.withdraw(committed=False)
        before = self.snapshot(self.case["work"])
        with self.assertRaises(EngineError) as caught:
            workspace.status(self.case["work"])
        self.assertEqual(caught.exception.issue["code"], "retention_review_pending")
        self.assertEqual(self.snapshot(self.case["work"]), before)
        self.withdraw(committed=True)
        original = self.snapshot(self.case["library"])
        with self.assertRaises(EngineError) as caught:
            local_run.execute(self.case["work"])
        self.assertEqual(caught.exception.issue["code"], "persona_retention_due")
        self.assertEqual(self.snapshot(self.case["library"]), original)
        self.assertEqual(Path(report["report_path"]).read_bytes(), old_report)

    def test_current_source_retention_expiry_blocks_without_pruning(self):
        with Store(self.research) as store:
            bundle = store.committed("bundle.json")
            bundle["records"]["sources"][0]["retention_until"] = "2000-01-01T00:00:00Z"
            store.publish("owned-expiry", {"bundle.json": bundle})
        original = self.snapshot(self.case["library"])
        with self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "persona_retention_due")
        self.assertEqual(self.snapshot(self.case["library"]), original)

    def test_reviewed_research_change_before_spawn_keeps_intent_without_dispatch(self):
        def fault(phase):
            if phase == "intent":
                self.withdraw()
        with patch.object(local_run, "_invoke", side_effect=AssertionError("revoked dispatch")), self.assertRaises(EngineError):
            self.execute(fault=fault)
        state = local_run._read(self.case["work"])
        self.assertEqual(len(state["dispatches"]), 1)
        self.assertFalse(next(iter(state["dispatches"].values()))["spawned"])

    def test_research_change_during_owned_execution_leaves_unknown_attempt(self):
        original_bundle = read_json(self.research / "bundle.json")
        invoke = local_run._invoke
        def changed(*args):
            result = invoke(*args)
            self.withdraw()
            return result
        with patch.object(local_run, "_invoke", side_effect=changed), self.assertRaises(EngineError):
            self.execute()
        state = local_run._read(self.case["work"])
        self.assertEqual(len(state["dispatches"]), 1)
        self.assertEqual(next(iter(state["dispatches"].values()))["phase"], "intent")
        with Store(self.research) as store:
            store.publish("owned-restore-for-recovery-check", {"bundle.json": original_bundle})
        with patch.object(local_run, "_invoke", side_effect=AssertionError("uncertain replay")):
            report = local_run.execute(self.case["work"])
        self.assertEqual(len(report["uncertain_dispatches"]), 1)
        self.assertFalse(report["execution_complete"])
        self.assertEqual(report["counts"]["passed"], 0)

    def test_lost_acknowledgement_readback_does_not_repeat_recorded_adapter(self):
        def lost(phase):
            if phase == "recorded":
                raise OSError("Owned response loss")
        with self.assertRaises(OSError):
            self.execute(fault=lost)
        first = local_run._read(self.case["work"])
        operation = next(iter(first["dispatches"].values()))["claim"]["operation_id"]
        real_invoke = local_run._invoke
        calls = []
        def count(*args):
            calls.append(args[2]["binding"]["operation_id"])
            return real_invoke(*args)
        with patch.object(local_run, "_invoke", side_effect=count):
            report = local_run.execute(self.case["work"])
        self.assertNotIn(operation, calls)
        self.assertEqual(len(calls), 1)
        self.assertTrue(report["execution_complete"])

    def test_changed_review_scope_cannot_rebind_existing_run(self):
        report = self.execute()
        before = self.snapshot(self.case["work"])
        with self.assertRaises(EngineError) as caught:
            local_run.execute(self.case["work"], reviewed_research_runs=[])
        self.assertEqual(caught.exception.issue["code"], "execution_contract")
        self.assertEqual(before, self.snapshot(self.case["work"]))
        self.assertTrue(Path(report["report_path"]).is_file())

    def test_mixed_prd_and_research_personas_are_distinct_in_readable_report(self):
        with Library(self.case["library"]) as library:
            record = library.get("owned-product", "PER-EXPLORE")
            profile = {key: record["profile"][key] for key in PROFILE_FIELDS}
            library.import_profiles(dict(schema_version="ux-persona-library-input.v1", product_id="owned-product",
                mode="prd_hypothesis", context=record["context"],
                personas=[dict(persona_id="PER-EXPLORE", claim_ids=[], **profile)]))
        report = self.execute()
        modes = {row["persona_id"]: row["provenance_mode"] for row in report["personas_reused"]}
        self.assertEqual(modes, {"PER-EXPLORE": "prd_hypothesis", "PER-RETURN": "gated_research"})
        text = Path(report["report_path"]).read_text()
        self.assertIn("PRD 합성 가설", text)
        self.assertIn("연구 근거를 연결한 합성 가설", text)
        self.assertIn("gate input", text)
        self.assertIn("SRC-", text)
        self.assertIn("CLM-", text)

    def test_concurrent_cli_callers_share_one_attempt_and_current_report(self):
        first = subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            first_out, first_err = first.communicate(timeout=20)
            second_out, second_err = second.communicate(timeout=20)
        finally:
            for process in (first, second):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=3)
        self.assertEqual(first.returncode, 1, first_err)
        self.assertEqual(second.returncode, 1, second_err)
        self.assertEqual(json.loads(first_out), json.loads(second_out))
        state = local_run._read(self.case["work"])
        self.assertEqual(len(state["dispatches"]), 2)
        self.assertTrue(all(row["claim"]["attempt"] == 1 and row["phase"] == "recorded" for row in state["dispatches"].values()))

    def test_read_only_store_and_research_view_cannot_publish_or_clean(self):
        from uxpersonas.research_access import ResearchView
        from uxresearch.storage import inspection_lock
        before = self.snapshot(self.research)
        with patch("os.fchmod", side_effect=AssertionError("permission change")):
            with Store(self.research, read_only=True) as store:
                self.assertTrue(store.committed("bundle.json"))
                for operation in (lambda: store.publish("forbidden", {}), lambda: store.failure("gate_failed.json", {})):
                    with self.assertRaises(EngineError):
                        operation()
            view = ResearchView(self.research)
            self.assertEqual(view.purge_pages(), 0)
            with view._state() as state:
                self.assertIn("hosts", state)
            for operation in (view.close, lambda: view.save_page("F-000000000001", "owned"), lambda: view.log({})):
                with self.assertRaises(EngineError):
                    operation()
            with self.assertRaises(EngineError):
                with view._state() as state:
                    state["unexpected"] = True
        with Store(self.research):
            with self.assertRaises(EngineError) as caught:
                with inspection_lock(self.research / "engine.lock", timeout=0):
                    pass
        self.assertEqual(caught.exception.issue["code"], "lock_busy")
        self.assertEqual(before, self.snapshot(self.research))

    def test_sparse_context_remains_lead_only_in_current_run(self):
        self.case = fixture.build(self.root / "context-case")
        self.research, _ = attach_research(self.case, self.root / "context-evidence", relation="context")
        workspace.prepare(self.case["source"], self.case["work"], reviewed_files=fixture.FILES)
        report = self.execute()
        for persona in report["personas_reused"]:
            claim = persona["research"]["claims"][0]
            self.assertEqual(claim["gate_status"], "lead_only")
            self.assertEqual(claim["counting_evidence_ids"], [])
            self.assertTrue(claim["context_evidence_ids"])
        self.assertEqual(report["counts"]["passed"], 0)

    def test_structured_export_import_to_installed_entry_and_report(self):
        target = self.root / "projected-diagnostic"
        result = subprocess.run([sys.executable, str(_paths.SKILL / "examples/journey/run_fixture.py"),
            "--research", "--out", str(target)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        diagnostic = json.loads(result.stdout)
        self.assertEqual(diagnostic["research_contract"], "invented_offline_input")
        self.assertFalse(diagnostic["actual_public_acquisition"])
        self.assertTrue(diagnostic["original_research_unchanged"])
        self.assertTrue(diagnostic["original_library_unchanged"])
        for row in diagnostic["personas_reused"]:
            self.assertEqual(row["revision"], 2)
            self.assertTrue(row["research"]["export"]["scenario_ids"])
        self.assertFalse(diagnostic["product_qa_passed"])
        self.assertFalse(diagnostic["ui_observed"])

    def test_interrupted_preparation_keeps_review_scope_for_restart(self):
        with patch.object(local_run, "_finish_preparation", side_effect=OSError("Owned preparation interruption")), self.assertRaises(OSError):
            self.execute()
        before = local_run._read(self.case["work"])
        self.assertEqual(before["research_runs"], [str(self.research)])
        self.assertEqual(before["phase"], "preparing")
        report = local_run.execute(self.case["work"])
        self.assertTrue(report["execution_complete"])
        after = local_run._read(self.case["work"])
        self.assertEqual(before["personas"], after["personas"])
        self.assertEqual(before["plan"], after["plan"])

    def test_missing_runner_approval_precedes_research_reads(self):
        with patch("uxpersonas.research_access.inspect_files", side_effect=AssertionError("premature read")), self.assertRaises(EngineError) as caught:
            local_run.execute(self.case["work"], library_path=self.case["library"],
                input_path=self.case["plan_path"], reviewed_research_runs=[self.research])
        self.assertEqual(caught.exception.issue["code"], "runner_approval")
        self.assertFalse((self.case["work"] / local_run.MARKER).exists())

    def test_expired_research_persona_review_never_renews_itself(self):
        path = self.case["library"] / "library.json"
        envelope = read_json(path)
        envelope["state"]["entries"]["owned-product/PER-EXPLORE"][-1]["review_after"] = 1
        envelope["sha256"] = digest(envelope["state"])
        atomic(path, canonical(envelope))
        before = path.read_bytes()
        with self.assertRaises(EngineError) as caught:
            self.execute()
        self.assertEqual(caught.exception.issue["code"], "persona_review_due")
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
