"""Focused checks for denominator integrity and immutable offline reporting."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import report_peekly_completion as completion
import report_peekly_coverage as reporting


def zero(keys, **updates):
    return {**dict.fromkeys(keys, 0), **updates}


def inputs():
    jobs, tasks = [], []
    for number in (1, 2, 3):
        jid, persona = "J" + str(number), "P" + str(number)
        task = {"id": jid, "persona_id": persona,
                "success_criteria": ["A", "B"], "recovery_criteria": ["conditional"],
                "requirement_coverage": [
                    {"requirement_id": rid, "obligations": [
                        {"criterion_refs": [{"kind": "success", "index": index}]}]}
                    for index, rid in enumerate(("A", "B"))]}
        jobs.append({"id": jid, "task": task})
        criteria = [
            {"kind": "success", "index": 0, "status": "passed",
             "observation": "observed A", "evidence_ids": []},
            {"kind": "success", "index": 1, "status": "failed",
             "observation": "stored failure | exact\nreason", "evidence_ids": ["log-1"]},
            {"kind": "recovery", "index": 0, "status": "not_applicable",
             "observation": "no trigger", "evidence_ids": []}]
        receipt = {"task_id": jid, "outcome": "failed", "criteria": criteria,
                   "artifacts": [{"id": "log-1", "path": "evidence/" + jid + "/1/observation.json",
                                  "sha256": "a" * 64}]}
        tasks.append({"job_id": jid, "persona_id": persona,
                      "status": "uncertain" if number == 2 else "complete",
                      "current_valid": number != 3, "current_ux_outcome": "failed",
                      "problem": "host_protocol: refused" if number == 3 else None,
                      "result": {"operational_completed": True, "receipt": receipt,
                                 "ux_outcome": "failed"}})
    completed = {
        "completed_sessions": 2, "assessed_completed_sessions": 1,
        "distinct_completed_personas": 2, "persona_ids": ["P1", "P3"],
        "session_outcomes": zero(reporting.OUTCOMES, failed=1),
        "criteria_all": zero(reporting.CRITERIA, passed=1, failed=1, not_applicable=1),
        "criteria_by_kind": {
            "success": zero(reporting.CRITERIA, passed=1, failed=1),
            "recovery": zero(reporting.CRITERIA, not_applicable=1)},
        "excluded_attempt_statuses": {"uncertain": 1, "complete": 1},
        "host_protocol_on_completed_receipts": 1}
    report = {"tasks": tasks, "counts": {"complete": 2, "uncertain": 1, "running": 0},
              "completed_receipt_summary": copy.deepcopy(completed), "plan_sha256": "b" * 64}
    stage = {"sessions": 3, "persona_ids": ["P1", "P2", "P3"],
             "counts": copy.deepcopy(report["counts"]), "operational_completed_sessions": 3,
             "browser_shutdown_confirmed": True,
             "delivery_policy": dict(reporting.DELIVERY_POLICY),
             "completed_receipt_summary": copy.deepcopy(completed)}
    plan = {"plan": {"jobs": jobs, "build": {"sha256": "c" * 64}}, "sha256": "b" * 64}
    return report, stage, plan


def reseal(report, stage):
    expected = reporting.recompute_completed_summary(report)
    report["completed_receipt_summary"] = copy.deepcopy(expected)
    stage["completed_receipt_summary"] = copy.deepcopy(expected)


def baseline_rows():
    combinations = [("P1", "A"), ("P1", "A"), ("P1", "B"),
                    ("P1", "C"), ("P2", "A"), ("P1", "D")]
    return {"criterion_count": 6, "rows": [
        {"id": "NR-" + str(i), "queue": "r4" if i == 0 else "r6", "job": "OLD-" + str(i),
         "persona": persona, "requirement": rid, "kind": "success", "index": 0,
         "status": "not_run", "reason": "original reason " + str(i)}
        for i, (persona, rid) in enumerate(combinations)]}


def dummy_columns():
    result = []
    for label in ("696dbe3", "cb0188d", "ee4b145"):
        result.append({"label": label, "completed_sessions": 24 if label == "ee4b145" else 32,
                       "distinct_personas": 15 if label == "ee4b145" else 32,
                       "session_outcomes": {"passed": 0, "failed": 2, "inconclusive": 30},
                       "criteria_all": dict.fromkeys(reporting.CRITERIA),
                       "criteria_by_kind": {"success": None, "recovery": None},
                       "host_protocol_on_completed_receipts": None, "source_refs": []})
    return result


class CoverageReportTests(unittest.TestCase):
    def summarize(self, values=None):
        return reporting.summarize_candidate(*(values or inputs()), 3, ".ux-loop/cohort/stage-3")

    def test_report_entry_points_require_explicit_archive_before_resolving_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            stage, output = repo / "absent-stage", repo / "report"
            scripts = Path(reporting.__file__).parent
            for name, arguments in (
                ("report_peekly_coverage.py", [str(stage), str(output)]),
                ("report_peekly_completion.py", [str(stage), str(output)]),
                ("finalize_peekly_completion.py", ["--run-root", str(stage), "--output", str(output)]),
            ):
                with self.subTest(script=name):
                    cmd = [sys.executable, str(scripts / name), *arguments]
                    refused = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
                    self.assertEqual(refused.returncode, 2)
                    self.assertIn("--repo", refused.stderr)
                    self.assertNotIn(str(stage), refused.stderr)
                    selected = subprocess.run([*cmd, "--repo", str(repo)], cwd=repo,
                                              capture_output=True, text=True)
                    self.assertEqual(selected.returncode, 2)
                    if name == "finalize_peekly_completion.py":
                        self.assertIn("must name this finalizer's own checkout", selected.stderr)
                        self.assertNotIn(str(stage), selected.stderr)
                    else:
                        self.assertNotIn("--repo", selected.stderr)
                    self.assertFalse(output.exists())
            check = subprocess.run([sys.executable, str(scripts / "finalize_peekly_completion.py"),
                                    "--run-root", str(stage), "--output", str(output), "--check-only"],
                                   cwd=repo, capture_output=True, text=True)
            self.assertEqual(check.returncode, 2)
            self.assertNotIn("--repo", check.stderr)
            self.assertFalse(output.exists())

    def test_finalizer_rejects_foreign_checkout_before_stage_lookup_in_both_modes(self):
        script = Path(reporting.__file__).with_name("finalize_peekly_completion.py")
        checkout = script.parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            foreign = Path(tmp)
            stage, output = foreign / "absent-stage", foreign / "report"
            cmd = [sys.executable, str(script), "--run-root", str(stage), "--output", str(output)]
            for mode in ([], ["--check-only"]):
                with self.subTest(check_only=bool(mode)):
                    refused = subprocess.run([*cmd, *mode, "--repo", str(foreign)], cwd=foreign,
                                             capture_output=True, text=True)
                    self.assertEqual(refused.returncode, 2)
                    self.assertIn("must name this finalizer's own checkout", refused.stderr)
                    self.assertNotIn(str(stage), refused.stderr)
                    accepted = subprocess.run([*cmd, *mode, "--repo", str(checkout)], cwd=foreign,
                                              capture_output=True, text=True)
                    self.assertEqual(accepted.returncode, 2)
                    self.assertIn("FileNotFoundError", accepted.stderr)
                    self.assertIn(str(stage), accepted.stderr)
                    self.assertFalse(output.exists())

    def test_completion_reads_only_selected_pinned_baseline_and_refuses_changed_bytes(self):
        candidate = dict(criteria_all=dict(passed=71, failed=8, not_run=23, not_applicable=19),
                         assessed_completed_sessions=29,
                         criteria=[dict(status="not_run", requirement_ids=["R-fixture"],
                                        persona_id=f"P-fixture-{i}", kind="success", job_id=f"J-fixture-{i}",
                                        index=0, reason="Authored fixture only") for i in range(23)])
        raw = json.dumps({"candidate": candidate, "artifact_path": "/synthetic/archive/not-created"}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with patch.object(completion, "BASE_SHA", reporting.sha(raw)), \
                 patch.object(completion.subprocess, "run") as git:
                git.return_value = subprocess.CompletedProcess([], 0, raw)
                value, reference, remaining = completion.load_reviewed(repo)
                self.assertEqual(value["candidate"], candidate)
                self.assertEqual(len(remaining["rows"]), 23)
                self.assertEqual(reference["sha256"], reporting.sha(raw))
                self.assertEqual(git.call_args.args[0], [
                    "git", "-C", str(repo), "show", completion.BASE_COMMIT + ":" + completion.BASE_PATH])
                git.return_value = subprocess.CompletedProcess([], 0, raw + b" ")
                with self.assertRaisesRegex(reporting.ReportError, "digest changed"):
                    completion.load_reviewed(repo)

    def test_uncertain_and_current_invalid_receipts_never_enter_denominator(self):
        result = self.summarize()
        self.assertEqual(result["assessed_completed_sessions"], 1)
        self.assertEqual(result["distinct_assessed_personas"], 1)
        self.assertEqual(result["criteria_all"], {"passed": 1, "failed": 1,
                                                 "not_run": 0, "not_applicable": 1})
        self.assertEqual(result["criteria_by_kind"]["success"]["failed"], 1)
        self.assertEqual(result["host_protocol"], {"assessed_completed": 0,
                                                   "all_completed_receipts": 1,
                                                   "excluded_attempts": 1})
        self.assertEqual([x["queue_status"] for x in result["unassessed_attempts"]],
                         ["uncertain", "complete"])
        failure = result["failures"][0]
        self.assertEqual(failure["requirement_ids"], ["B"])
        self.assertEqual(failure["reason"], "stored failure | exact\nreason")
        self.assertEqual(failure["evidence"][0]["path"],
                         ".ux-loop/cohort/stage-3/sessions/J1/evidence/J1/1/observation.json")

    def test_missing_receipt_or_operational_flag_is_unassessed(self):
        for change in ("receipt", "operational_completed"):
            with self.subTest(change=change):
                report, stage, plan = inputs()
                report["tasks"][0]["result"].pop(change)
                if change == "operational_completed":
                    stage["operational_completed_sessions"] -= 1
                reseal(report, stage)
                result = self.summarize((report, stage, plan))
                self.assertEqual(result["assessed_completed_sessions"], 0)
                self.assertEqual(sum(result["criteria_all"].values()), 0)
                self.assertEqual(len(result["unassessed_attempts"]), 3)

    def test_summary_mismatch_missing_and_queue_count_mismatch_fail_closed(self):
        for mode in ("stage", "report", "missing", "queue"):
            with self.subTest(mode=mode):
                report, stage, plan = inputs()
                if mode == "stage":
                    stage["completed_receipt_summary"]["criteria_all"]["passed"] = 99
                elif mode == "report":
                    report["completed_receipt_summary"]["assessed_completed_sessions"] = 3
                elif mode == "missing":
                    stage.pop("completed_receipt_summary")
                else:
                    report["counts"]["complete"] = 3
                with self.assertRaises(reporting.ReportError):
                    self.summarize((report, stage, plan))

    def test_final_shutdown_and_no_running_jobs_are_required(self):
        for mode in ("shutdown", "running", "requested"):
            report, stage, plan = inputs()
            if mode == "shutdown":
                stage["browser_shutdown_confirmed"] = False
            elif mode == "running":
                report["tasks"][1]["status"] = "running"
                report["counts"] = stage["counts"] = {"complete": 2, "running": 1}
                reseal(report, stage)
            else:
                stage["sessions"] = 32
            with self.subTest(mode=mode), self.assertRaises(reporting.ReportError):
                self.summarize((report, stage, plan))

    def test_job_persona_and_receipt_binding_must_match(self):
        for mode in ("missing_job", "duplicate_persona", "task_persona", "receipt", "plan_hash"):
            report, stage, plan = inputs()
            if mode == "missing_job":
                report["tasks"][0]["job_id"] = "unknown"
            elif mode == "duplicate_persona":
                plan["plan"]["jobs"][2]["task"]["persona_id"] = "P1"
            elif mode == "task_persona":
                report["tasks"][0]["persona_id"] = "other"
                reseal(report, stage)
            elif mode == "receipt":
                report["tasks"][0]["result"]["receipt"]["task_id"] = "other"
            else:
                report["plan_sha256"] = "d" * 64
            with self.subTest(mode=mode), self.assertRaises(reporting.ReportError):
                self.summarize((report, stage, plan))

    def test_duplicate_criterion_and_missing_requirement_binding_are_rejected(self):
        for mode in ("duplicate", "unbound"):
            report, stage, plan = inputs()
            if mode == "duplicate":
                criteria = report["tasks"][0]["result"]["receipt"]["criteria"]
                criteria.append(copy.deepcopy(criteria[0]))
                reseal(report, stage)
            else:
                plan["plan"]["jobs"][0]["task"]["requirement_coverage"] = []
            with self.subTest(mode=mode), self.assertRaises(reporting.ReportError):
                self.summarize((report, stage, plan))

    def test_unsafe_or_unregistered_evidence_is_rejected(self):
        for mode in ("traversal", "absolute", "unregistered"):
            report, stage, plan = inputs()
            receipt = report["tasks"][0]["result"]["receipt"]
            if mode == "unregistered":
                receipt["criteria"][1]["evidence_ids"] = ["unknown"]
            else:
                receipt["artifacts"][0]["path"] = "../escape" if mode == "traversal" else "/outside"
            with self.subTest(mode=mode), self.assertRaises(reporting.ReportError):
                self.summarize((report, stage, plan))

    def test_weighted_mapping_retains_duplicates_and_unique_view_does_not(self):
        candidate = {"criteria": [
            {"persona_id": "P1", "requirement_ids": [rid], "kind": "success",
             "status": status, "reason": "new reason"}
            for rid, status in (("A", "passed"), ("B", "failed"),
                                ("C", "not_run"), ("D", "not_applicable"))]}
        result = reporting.map_baseline(baseline_rows(), candidate)
        self.assertEqual(result["weighted_count"], 6)
        self.assertEqual(result["weighted_statuses"],
                         {"passed": 2, "failed": 1, "not_run": 1, "unassessed": 2})
        self.assertEqual(result["unique_persona_requirement_count"], 5)
        self.assertEqual(result["unique_statuses"],
                         {"passed": 1, "failed": 1, "not_run": 1, "unassessed": 2})
        self.assertEqual(result["weighted_rows"][1]["baseline_reason"], "original reason 1")
        self.assertEqual(result["weighted_rows"][-1]["unassessed_reason"], "candidate_not_applicable")

    def test_old_ledger_and_baseline_record_identity_are_cross_checked(self):
        baseline = baseline_rows()
        sessions = []
        for row in baseline["rows"]:
            sessions.append({"queue": row["queue"], "job_id": row["job"], "persona_id": row["persona"],
                             "outcome": "inconclusive", "host_protocol": False,
                             "criteria": [{"kind": row["kind"], "index": row["index"],
                                           "requirement_id": row["requirement"], "status": "not_run"}]})
        ledger = {"completed_sessions": sessions, "aggregate": reporting._aggregate_sessions(sessions)}
        result = reporting.verify_old_ledger(ledger, baseline)
        self.assertEqual(result["completed_sessions"], 6)
        self.assertEqual(result["distinct_completed_personas"], 2)
        baseline["rows"][0]["job"] = "changed"
        with self.assertRaises(reporting.ReportError):
            reporting.verify_old_ledger(ledger, baseline)
        baseline = baseline_rows()
        ledger["aggregate"]["criteria_all"]["not_run"] = 0
        with self.assertRaises(reporting.ReportError):
            reporting.verify_old_ledger(ledger, baseline)

    def test_cost_disclosure_preserves_missing_provider_costs(self):
        stage = {"configured_routes": ["TOKENMAXX/free"],
                 "model_attempts": {"TOKENMAXX/free": {"attempts": 3}},
                 "fallback_model_attempts": 0,
                 "cost_record": {"policy_cost_usd": 0, "missing_cost_responses": 2,
                                 "provider_reported_cost_values": [None, None, 0],
                                 "provider_invoice_verified": False}}
        cost = reporting.summarize_cost(stage)
        self.assertEqual(cost["policy_cost_usd"], 0)
        self.assertEqual(cost["missing_cost_responses"], 2)
        self.assertFalse(cost["provider_invoice_verified"])
        self.assertIsNone(reporting.summarize_cost({})["policy_cost_usd"])
        stage["cost_record"]["missing_cost_responses"] = 0
        with self.assertRaises(reporting.ReportError):
            reporting.summarize_cost(stage)

    def make_repository(self, root):
        stage = root / ".ux-loop" / "candidate" / "stage-3"
        stage.mkdir(parents=True)
        values = inputs()
        for name, value in zip(("report.json", "stage-summary.json", "plan.json"), values):
            (stage / name).write_text(json.dumps(value), encoding="utf-8")
        ledger = {"call_delivery": {"call-a": "reply_received"},
                  "events": [{"call_id": "call-a", "status": "success"}]}
        (stage / "model-router-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        run_status = {"state": "incomplete_preserved", "prior_queues_unchanged": True,
                      "router_delivery_audit": reporting.router_delivery_audit(ledger)}
        for name, key in (("report.json", "report_sha256"),
                          ("stage-summary.json", "summary_sha256"),
                          ("model-router-ledger.json", "router_ledger_sha256")):
            run_status[key] = hashlib.sha256((stage / name).read_bytes()).hexdigest()
        (stage.parent / "run-status.json").write_text(json.dumps(run_status), encoding="utf-8")
        baseline = root / "baseline.json"
        baseline.write_text(json.dumps(baseline_rows()), encoding="utf-8")
        return stage, baseline

    def test_explicit_publish_is_new_only_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage, baseline = self.make_repository(root)
            paths = [*stage.iterdir(), baseline, stage.parent / "run-status.json"]
            before = {p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in paths}
            output = root / "reports" / "new"
            output.mkdir(parents=True)
            (output / "STATUS.md").write_text("preserve existing checkpoint\n")
            with patch.object(reporting, "load_baselines", return_value=(dummy_columns(), {}, [])):
                result = reporting.build_report(root, stage, output, requested=3, baseline_path=baseline)
                self.assertEqual(result["assessed_completed"], 1)
                summary = json.loads((output / "summary.json").read_text())
                markdown = (output / "comparison.md").read_text()
                self.assertEqual(len(summary["comparison_columns"]), 4)
                self.assertIn("24세션은 고유 페르소나 15명", markdown)
                self.assertIn("미보존 / 미확인", markdown)
                self.assertIn("stored failure \\| exact reason", markdown)
                self.assertEqual(summary["new_model_calls"], 0)
                self.assertEqual(summary["new_browser_calls"], 0)
                self.assertTrue(summary["router_delivery"]["zero_uncertain_resends_verified"])
                self.assertTrue(summary["router_delivery"]["stored_run_status"]["audit_and_hashes_match"])
                self.assertEqual(summary["router_delivery"]["ledger_source_ref"]["sha256"],
                                 before[stage / "model-router-ledger.json"][0])
                self.assertEqual(summary["sources"][0]["sha256"], before[stage / "report.json"][0])
                self.assertEqual((output / "STATUS.md").read_text(), "preserve existing checkpoint\n")
                with self.assertRaises(reporting.ReportError):
                    reporting.build_report(root, stage, output, requested=3, baseline_path=baseline)
            after = {p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in paths}
            self.assertEqual(before, after)

    def test_changed_input_and_incomplete_stage_create_no_output(self):
        for mode in ("changed", "incomplete"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, baseline = self.make_repository(root)
                output = root / "new"
                if mode == "incomplete":
                    value = json.loads((stage / "stage-summary.json").read_text())
                    value["browser_shutdown_confirmed"] = False
                    (stage / "stage-summary.json").write_text(json.dumps(value))
                def historical(*args):
                    if mode == "changed":
                        baseline.write_text(baseline.read_text() + "\n")
                    return dummy_columns(), {}, []
                with patch.object(reporting, "load_baselines", side_effect=historical):
                    with self.assertRaises(reporting.ReportError):
                        reporting.build_report(root, stage, output, requested=3, baseline_path=baseline)
                self.assertFalse(output.exists())

    def test_delivery_audit_distinguishes_known_quality_repairs_from_uncertain_resends(self):
        ledger = {"call_delivery": {"quality": "reply_received", "timeout": "uncertain"},
                  "events": [{"call_id": "quality", "status": status} for status in
                             ("success", "quality_rejected", "success", "quality_rejected", "success")]
                  + [{"call_id": "timeout", "status": "delivery_uncertain"}]}
        ref = {"path": "stage/model-router-ledger.json", "sha256": "a" * 64}
        stage = {"delivery_policy": dict(reporting.DELIVERY_POLICY)}
        delivery = reporting.summarize_delivery(stage, ledger, ref)
        audit = delivery["audit"]
        self.assertEqual(audit["actual_attempt_receipts"], 4)
        self.assertEqual(audit["quality_diagnostic_count"], 2)
        self.assertEqual(audit["known_quality_repair_count"], 2)
        self.assertEqual(audit["uncertain_guard_call_ids"], ["timeout"])
        self.assertEqual(audit["uncertain_resend_violations"], 0)
        self.assertTrue(delivery["zero_uncertain_resends_verified"])
        ledger["events"].append({"call_id": "timeout", "status": "success"})
        delivery = reporting.summarize_delivery(stage, ledger, ref)
        self.assertEqual(delivery["audit"]["uncertain_resend_violations"], 1)
        self.assertEqual(delivery["audit"]["violation_call_ids"], ["timeout"])
        self.assertEqual(delivery["audit"]["known_quality_repair_count"], 2)
        self.assertFalse(delivery["zero_uncertain_resends_verified"])

    def test_invalid_guard_or_policy_never_verifies_zero_uncertain_resends(self):
        ref = {"path": "router.json", "sha256": "a" * 64}
        stage = {"delivery_policy": dict(reporting.DELIVERY_POLICY)}
        missing_guard = {"events": [{"call_id": "call-a", "status": "success"}]}
        result = reporting.summarize_delivery(stage, missing_guard, ref)
        self.assertFalse(result["audit"]["valid"])
        self.assertFalse(result["zero_uncertain_resends_verified"])
        ledger = {"call_delivery": {"call-a": "reply_received"}, "events": missing_guard["events"]}
        stage["delivery_policy"]["uncertain_resends"] = 1
        result = reporting.summarize_delivery(stage, ledger, ref)
        self.assertTrue(result["audit"]["valid"])
        self.assertFalse(result["policy_matches_expected"])
        self.assertFalse(result["zero_uncertain_resends_verified"])

    def test_missing_router_ledger_refuses_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage, baseline = self.make_repository(root)
            (stage / "model-router-ledger.json").unlink()
            output = root / "new"
            with patch.object(reporting, "load_baselines", return_value=(dummy_columns(), {}, [])):
                with self.assertRaises(FileNotFoundError):
                    reporting.build_report(root, stage, output, requested=3, baseline_path=baseline)
            self.assertFalse(output.exists())

    def test_run_status_audit_or_source_hash_mismatch_refuses_output(self):
        for field in ("router_ledger_sha256", "report_sha256", "summary_sha256", "router_delivery_audit"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, baseline = self.make_repository(root)
                path = stage.parent / "run-status.json"
                status = json.loads(path.read_text())
                status[field] = {} if field == "router_delivery_audit" else "f" * 64
                path.write_text(json.dumps(status))
                output = root / "new"
                with patch.object(reporting, "load_baselines", return_value=(dummy_columns(), {}, [])):
                    with self.assertRaisesRegex(reporting.ReportError, "run-status"):
                        reporting.build_report(root, stage, output, requested=3, baseline_path=baseline)
                self.assertFalse(output.exists())

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(reporting.ReportError):
            reporting._json(b'{"tasks":[],"tasks":[1]}')


if __name__ == "__main__":
    unittest.main()
