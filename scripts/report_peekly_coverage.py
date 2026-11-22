#!/usr/bin/env python3
"""Offline, immutable-input comparison for the Peekly coverage cohort.

Run only after report.json, plan.json and stage-summary.json exist. This script
never executes a queue, contacts a model, revalidates against mutable source, or
rewrites a receipt. Current-valid means the final report's recorded admission.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

from run_peekly_coverage import DELIVERY_POLICY, router_delivery_audit

CRITERIA = ("passed", "failed", "not_run", "not_applicable")
OUTCOMES = ("passed", "failed", "inconclusive", "blocked", "skipped")
MAPPING = ("passed", "failed", "not_run", "unassessed")
COMMITS = {
    "696dbe3": "696dbe34e92247ed1b139662577f799b8595baaa",
    "cb0188d": "cb0188ddf420b3b019facbafef75bde619365a41",
    "ee4b145": "ee4b14571930af428d5a52e0e133deebedba485d",
}
OLD = "docs/validation/peekly-ux-findings-20261113/run-summary-32.json"
QUALITY = "docs/validation/peekly-verdict-quality-20261113/verdict-quality-summary.json"
EXPLICIT = "docs/validation/peekly-explicit-success-20261113/"
NOT_RUN = "docs/validation/peekly-coverage-20261114/not-run-baseline.json"


class ReportError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReportError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def counts(values, keys):
    counter = Counter(values)
    require(not (counter.keys() - set(keys)), "unknown status")
    return {key: counter[key] for key in keys}


def same_counts(actual, expected, message):
    require(isinstance(expected, dict), message)
    require(all(actual.get(key, 0) == value for key, value in expected.items())
            and all(expected.get(key, 0) == value for key, value in actual.items()), message)


def _json(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise ReportError("invalid JSON input") from exc


def read_json(path, repo):
    path = Path(path).resolve(strict=True)
    require(path.is_relative_to(repo), "input is outside repository")
    raw = path.read_bytes()
    value = _json(raw)
    require(isinstance(value, dict), "input JSON must be an object")
    return value, {"path": path.relative_to(repo).as_posix(),
                   "sha256": sha(raw), "bytes": len(raw)}


def git_json(repo, revision, path):
    commit = COMMITS[revision]
    result = subprocess.run(["git", "-C", str(repo), "show", commit + ":" + path],
                            capture_output=True, check=False)
    require(result.returncode == 0, "pinned baseline git blob is unavailable")
    return _json(result.stdout), {"commit": commit, "path": path,
                                 "sha256": sha(result.stdout), "bytes": len(result.stdout)}


def _aggregate_sessions(sessions):
    criteria = [item for session in sessions for item in session["criteria"]]
    return {
        "completed_sessions": len(sessions),
        "distinct_completed_personas": len({s["persona_id"] for s in sessions}),
        "session_outcomes": counts((s["outcome"] for s in sessions), OUTCOMES),
        "criteria_all": counts((c["status"] for c in criteria), CRITERIA),
        "criteria_by_kind": {kind: counts((c["status"] for c in criteria
                                         if c["kind"] == kind), CRITERIA)
                             for kind in ("success", "recovery")},
        "host_protocol_on_completed_receipts": sum(bool(s["host_protocol"]) for s in sessions),
    }


def verify_old_ledger(ledger, baseline):
    sessions = ledger["completed_sessions"]
    aggregate = _aggregate_sessions(sessions)
    for key in ("completed_sessions", "distinct_completed_personas",
                "host_protocol_on_completed_receipts"):
        require(aggregate[key] == ledger["aggregate"][key], "old ledger aggregate mismatch")
    for key in ("session_outcomes", "criteria_all"):
        same_counts(aggregate[key], ledger["aggregate"][key], "old ledger count mismatch")
    for kind in ("success", "recovery"):
        same_counts(aggregate["criteria_by_kind"][kind],
                    ledger["aggregate"]["criteria_by_kind"].get(kind, {}),
                    "old ledger criterion kind mismatch")
    old_rows = {
        (s["queue"], s["job_id"], s["persona_id"], c["kind"], c["index"], c["requirement_id"])
        for s in sessions for c in s["criteria"] if c["status"] == "not_run"
    }
    rows = baseline["rows"]
    keys = [(r["queue"], r["job"], r["persona"], r["kind"], r["index"], r["requirement"])
            for r in rows]
    require(len(keys) == len(set(keys)), "duplicate baseline criterion record")
    require(len({r["id"] for r in rows}) == len(rows), "duplicate baseline record id")
    require(set(keys) == old_rows and len(rows) == baseline["criterion_count"],
            "not-run baseline does not match original session ledger")
    require(all(r["status"] == "not_run" for r in rows), "baseline contains non-not-run row")
    return aggregate


def load_baselines(repo, baseline):
    old, old_ref = git_json(repo, "696dbe3", OLD)
    quality, quality_ref = git_json(repo, "cb0188d", QUALITY)
    history, history_ref = git_json(repo, "ee4b145", EXPLICIT + "summary.json")
    ledger, ledger_ref = git_json(repo, "ee4b145", EXPLICIT + "final-session-ledger-20261114.json")
    aggregate = verify_old_ledger(ledger, baseline)
    runs = history["runs"]
    require(len(runs) == 3, "unexpected historical comparison")
    columns = []
    for index, revision in enumerate(("696dbe3", "cb0188d", "ee4b145")):
        row = runs[index]
        success = row.get("success_criteria_units")
        if success is not None:
            success = dict(success)
            if "not_applicable_desktop" in success:
                success["not_applicable"] = success.pop("not_applicable_desktop")
        columns.append({
            "label": revision, "reference_commit": COMMITS[revision],
            "completed_sessions": row["completed_sessions"],
            "distinct_personas": row["distinct_personas"],
            "session_outcomes": row["session_ux_outcomes"],
            "criteria_all": row["criteria_all"],
            "criteria_by_kind": {
                "success": success,
                "recovery": row.get("recovery_criteria_units")},
            "host_protocol_on_completed_receipts": row["host_protocol_on_completed_receipts"],
            "source_refs": [dict(history_ref, selector="runs[" + str(index) + "]")],
            "note": row["note"],
        })
    require(old["distinct_personas"] == columns[0]["distinct_personas"] == 32,
            "initial cohort identity mismatch")
    same_counts(columns[0]["session_outcomes"],
                {key: quality["before"][key] for key in ("passed", "failed", "inconclusive")},
                "whole32 historical outcome mismatch")
    require(columns[0]["completed_sessions"] == quality["before"]["sessions"] == 32,
            "initial cohort size mismatch")
    columns[0]["source_refs"] += [dict(old_ref, selector="distinct_personas"),
                                  dict(quality_ref, selector="before")]
    same_counts(columns[1]["session_outcomes"],
                {key: quality["after"][key] for key in ("passed", "failed", "inconclusive")},
                "verdict cohort outcome mismatch")
    qc = quality["criteria"]
    same_counts(columns[1]["criteria_all"],
                {"passed": qc["passed"], "failed": qc["failed"],
                 "not_run": qc["applicable_not_run"],
                 "not_applicable": qc["desktop_native_share_sheet_not_applicable"]
                                   + qc["conditional_recovery_not_applicable"]},
                "verdict cohort criterion mismatch")
    require(columns[1]["completed_sessions"] == quality["after"]["sessions"] == 32,
            "verdict cohort size mismatch")
    columns[1]["source_refs"].append(dict(quality_ref, selector="after; criteria"))
    for key, aggregate_key in (("completed_sessions", "completed_sessions"),
                               ("distinct_personas", "distinct_completed_personas"),
                               ("host_protocol_on_completed_receipts",
                                "host_protocol_on_completed_receipts")):
        require(columns[2][key] == aggregate[aggregate_key], "final baseline count mismatch")
    same_counts(columns[2]["session_outcomes"], aggregate["session_outcomes"],
                "final baseline outcome mismatch")
    same_counts(columns[2]["criteria_all"], aggregate["criteria_all"],
                "final baseline criterion mismatch")
    require(aggregate["completed_sessions"] == 24
            and aggregate["distinct_completed_personas"] == 15
            and aggregate["criteria_all"]["not_run"] == 46, "unexpected frozen baseline")
    columns[2]["criteria_by_kind"] = aggregate["criteria_by_kind"]
    columns[2]["source_refs"].append(dict(ledger_ref, selector="completed_sessions; aggregate"))
    columns[2]["unassessed_attempts"] = history["unassessed_attempts"]
    return columns, ledger, [old_ref, quality_ref, history_ref, ledger_ref]


def _host_protocol(task):
    result = task.get("result") or {}
    return any("host_protocol" in str(value) for value in
               (task.get("problem"), result.get("problem"), task.get("current_issue")))


def recompute_completed_summary(report):
    """Mirror the report's published denominator contract without live imports."""
    completed, assessed, excluded = [], [], Counter()
    for task in report["tasks"]:
        result = task.get("result") or {}
        complete = (task["status"] == "complete"
                    and result.get("operational_completed") is True
                    and isinstance(result.get("receipt"), dict))
        if complete:
            completed.append(task)
        if complete and task.get("current_valid") is True:
            assessed.append(task)
        else:
            excluded[task.get("status") or "unknown"] += 1
    criteria = [c for task in assessed for c in task["result"]["receipt"].get("criteria", [])]
    return {
        "completed_sessions": len(completed), "assessed_completed_sessions": len(assessed),
        "distinct_completed_personas": len({t["persona_id"] for t in completed}),
        "persona_ids": sorted({t["persona_id"] for t in completed}),
        "session_outcomes": counts((t.get("current_ux_outcome")
                                    or t["result"]["receipt"]["outcome"] for t in assessed), OUTCOMES),
        "criteria_all": counts((c["status"] for c in criteria), CRITERIA),
        "criteria_by_kind": {kind: counts((c["status"] for c in criteria if c["kind"] == kind),
                                          CRITERIA) for kind in ("success", "recovery")},
        "excluded_attempt_statuses": dict(excluded),
        "host_protocol_on_completed_receipts": sum(_host_protocol(t) for t in completed),
    }


def _requirement_map(task):
    result = defaultdict(set)
    for coverage in task.get("requirement_coverage", []):
        rid = coverage["requirement_id"]
        for obligation in coverage.get("obligations", []):
            for ref in obligation.get("criterion_refs", []):
                result[(ref["kind"], ref["index"])].add(rid)
    for index in range(len(task["recovery_criteria"])):
        result[("recovery", index)].add("CONDITIONAL-RECOVERY")
    return result


def _safe_relative(value):
    require(isinstance(value, str) and value and "\\" not in value,
            "unsafe evidence path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(part not in ("", ".", "..")
                                          for part in value.split("/")),
            "unsafe evidence path")
    return path.as_posix()


def _criterion_record(task, criterion, refs, stage_path):
    receipt = task["result"]["receipt"]
    artifacts = {a["id"]: a for a in receipt.get("artifacts", [])}
    evidence = []
    for identifier in criterion.get("evidence_ids", []):
        require(identifier in artifacts, "criterion evidence id is not registered")
        artifact = artifacts[identifier]
        relative = _safe_relative(artifact["path"])
        evidence.append({"id": identifier,
                         "path": stage_path + "/sessions/" + _safe_relative(task["job_id"]) + "/" + relative,
                         "sha256": artifact.get("sha256")})
    return {"persona_id": task["persona_id"], "job_id": task["job_id"],
            "kind": criterion["kind"], "index": criterion["index"],
            "requirement_ids": sorted(refs), "status": criterion["status"],
            "reason": criterion.get("observation", ""),
            "evidence": evidence,
            "report_selector": ("tasks[job_id=" + task["job_id"] + "].result.receipt.criteria"
                                + "[kind=" + criterion["kind"] + ",index="
                                + str(criterion["index"]) + "]")}


def summarize_candidate(report, stage, plan_envelope, requested, stage_path):
    require(stage.get("browser_shutdown_confirmed") is True, "final shutdown summary required")
    require(type(requested) is int and requested > 0, "requested cohort size invalid")
    plan = plan_envelope.get("plan", plan_envelope)
    jobs = {job["id"]: job["task"] for job in plan["jobs"]}
    tasks = report["tasks"]
    require(len(jobs) == len(plan["jobs"]), "duplicate planned job")
    require(len({t["job_id"] for t in tasks}) == len(tasks), "duplicate report job")
    require(set(jobs) == {t["job_id"] for t in tasks}, "report and plan job sets differ")
    planned_personas = [task["persona_id"] for task in jobs.values()]
    require(len(set(planned_personas)) == len(planned_personas),
            "candidate plan repeats a persona; choose one immutable cohort")
    require(len(tasks) == stage["sessions"] == requested, "requested and planned cohort sizes differ")
    require(set(stage["persona_ids"]) == set(planned_personas), "stage persona set mismatch")
    actual_counts = dict(Counter(t["status"] for t in tasks))
    same_counts(actual_counts, report["counts"], "report queue counts mismatch")
    same_counts(actual_counts, stage["counts"], "stage queue counts mismatch")
    require(actual_counts.get("running", 0) == 0, "cohort still has running tasks")
    require(stage["operational_completed_sessions"] ==
            sum((t.get("result") or {}).get("operational_completed") is True for t in tasks),
            "stage operational completion mismatch")
    if "plan_sha256" in report and "sha256" in plan_envelope:
        require(report["plan_sha256"] == plan_envelope["sha256"], "report plan hash binding mismatch")
    completed = recompute_completed_summary(report)
    checks = {}
    for name, data in (("report", report), ("stage", stage)):
        stored = data.get("completed_receipt_summary")
        require(isinstance(stored, dict) and all(stored.get(k) == v for k, v in completed.items()),
                name + " completed_receipt_summary mismatch or missing")
        checks[name + "_completed_receipt_summary_matches"] = True
    assessed, excluded, criteria = [], [], []
    for task in tasks:
        planned = jobs[task["job_id"]]
        require(task["persona_id"] == planned["persona_id"], "persona task binding mismatch")
        result = task.get("result") or {}
        receipt = result.get("receipt")
        reasons = []
        if task["status"] != "complete":
            reasons.append("queue_" + task["status"])
        if result.get("operational_completed") is not True:
            reasons.append("operational_completion_missing")
        if not isinstance(receipt, dict):
            reasons.append("receipt_missing")
        if task.get("current_valid") is not True:
            reasons.append("current_evidence_not_valid")
        if reasons:
            excluded.append({"job_id": task["job_id"], "persona_id": task["persona_id"],
                             "queue_status": task["status"], "reasons": reasons,
                             "host_protocol": _host_protocol(task)})
            continue
        require(receipt.get("task_id") == planned["id"], "receipt task binding mismatch")
        outcome = task.get("current_ux_outcome") or receipt["outcome"]
        require(outcome == receipt["outcome"] == result.get("ux_outcome"),
                "receipt outcome binding mismatch")
        expected = {(kind, index) for kind in ("success", "recovery")
                    for index in range(len(planned[kind + "_criteria"]))}
        actual = [(c["kind"], c["index"]) for c in receipt["criteria"]]
        require(set(actual) == expected and len(actual) == len(expected),
                "receipt criterion set mismatch")
        refs = _requirement_map(planned)
        session_criteria = []
        for criterion in receipt["criteria"]:
            key = criterion["kind"], criterion["index"]
            require(criterion["status"] in CRITERIA and refs[key],
                    "criterion status or requirement binding missing")
            record = _criterion_record(task, criterion, refs[key], stage_path)
            criteria.append(record)
            session_criteria.append(record)
        assessed.append({"persona_id": task["persona_id"], "job_id": task["job_id"],
                         "outcome": outcome, "host_protocol": _host_protocol(task),
                         "criteria": session_criteria, "result_sha256": task.get("result_sha256")})
    aggregate = _aggregate_sessions(assessed)
    require(aggregate["completed_sessions"] == completed["assessed_completed_sessions"],
            "assessed denominator mismatch")
    return {
        "requested_sessions": requested, "planned_unique_personas": len(set(planned_personas)),
        "fixture_manifest_sha256": stage.get("fixture_manifest_sha256"),
        "plan_sha256": report.get("plan_sha256"),
        "product_build": plan.get("build"),
        "queue_counts": actual_counts, "completed_receipts_before_current_validation": completed["completed_sessions"],
        "assessed_completed_sessions": aggregate["completed_sessions"],
        "distinct_assessed_personas": aggregate["distinct_completed_personas"],
        "session_outcomes": aggregate["session_outcomes"], "criteria_all": aggregate["criteria_all"],
        "criteria_by_kind": aggregate["criteria_by_kind"],
        "host_protocol": {"assessed_completed": aggregate["host_protocol_on_completed_receipts"],
                          "all_completed_receipts": completed["host_protocol_on_completed_receipts"],
                          "excluded_attempts": sum(t["host_protocol"] for t in excluded)},
        "unassessed_attempts": excluded, "sessions": assessed, "criteria": criteria,
        "failures": [c for c in criteria if c["status"] == "failed"],
        "not_run_by_requirement": _not_run_by_requirement(criteria), "validation": checks,
    }


def _not_run_by_requirement(criteria):
    groups = defaultdict(list)
    for criterion in criteria:
        if criterion["status"] == "not_run":
            for rid in criterion["requirement_ids"]:
                groups[rid].append(criterion)
    return {rid: {"criterion_units": len(rows), "rows": rows} for rid, rows in sorted(groups.items())}


def map_baseline(baseline, candidate):
    index = defaultdict(list)
    for criterion in candidate["criteria"]:
        for rid in criterion["requirement_ids"]:
            index[(criterion["persona_id"], rid, criterion["kind"])].append(criterion)
    weighted, unique = [], {}
    for row in baseline["rows"]:
        matches = index[(row["persona"], row["requirement"], row["kind"])]
        statuses = {item["status"] for item in matches}
        if not matches or "not_applicable" in statuses:
            status = "unassessed"
        elif "failed" in statuses:
            status = "failed"
        elif "not_run" in statuses:
            status = "not_run"
        else:
            status = "passed"
        item = {"baseline_id": row["id"], "baseline_queue": row["queue"],
                "baseline_job_id": row["job"], "persona_id": row["persona"],
                "requirement_id": row["requirement"], "baseline_reason": row["reason"],
                "status": status, "candidate_criteria": matches,
                "unassessed_reason": ("no_assessed_matching_criterion" if not matches
                                      else "candidate_not_applicable" if "not_applicable" in statuses
                                      else None)}
        weighted.append(item)
        key = row["persona"], row["requirement"]
        if key not in unique:
            unique[key] = {"persona_id": key[0], "requirement_id": key[1],
                           "status": status, "baseline_ids": [], "baseline_weight": 0}
        require(unique[key]["status"] == status, "ambiguous unique baseline mapping")
        unique[key]["baseline_ids"].append(row["id"])
        unique[key]["baseline_weight"] += 1
    unique_rows = list(unique.values())
    return {"weighted_count": len(weighted), "weighted_statuses": counts((r["status"] for r in weighted), MAPPING),
            "weighted_rows": weighted, "unique_persona_requirement_count": len(unique_rows),
            "unique_statuses": counts((r["status"] for r in unique_rows), MAPPING),
            "unique_rows": unique_rows,
            "note": "Repeated baseline session rows retain their weight; candidate work is not duplicated. N/A earns no execution credit."}


def summarize_cost(stage):
    cost = stage.get("cost_record") or {}
    values = cost.get("provider_reported_cost_values")
    missing = (sum(value is None for value in values) if isinstance(values, list) else None)
    if missing is not None and "missing_cost_responses" in cost:
        require(missing == cost["missing_cost_responses"], "provider missing-cost count mismatch")
    route_stats = stage.get("model_attempts") or {}
    return {
        "configured_routes": stage.get("configured_routes"),
        "attempted_routes": {route: stats.get("attempts") for route, stats in route_stats.items()
                             if stats.get("attempts", 0) > 0},
        "served_provider_models": [{"provider": row.get("provider"), "model": row.get("model"),
                                    "calls": row.get("calls"), "cost_bases": row.get("cost_bases")}
                                   for row in stage.get("provider_usage", [])],
        "fallback_model_attempts": stage.get("fallback_model_attempts"),
        "policy_cost_usd": cost.get("policy_cost_usd"),
        "missing_cost_responses": cost.get("missing_cost_responses", missing),
        "provider_cost_response_count": len(values) if isinstance(values, list) else None,
        "provider_invoice_verified": cost.get("provider_invoice_verified") is True,
        "cost_record_missing": not bool(cost),
        "disclosure": "A configured free route and policy cost of zero do not verify provider billing; missing cost values remain missing.",
    }


def summarize_delivery(stage, ledger, ledger_ref, *, run_status=None,
                       run_status_ref=None, report_ref=None, stage_ref=None):
    """Audit final persisted events; importing the helper never loads the runner."""
    audit = router_delivery_audit(ledger)
    policy = stage.get("delivery_policy")
    policy_matches = policy == DELIVERY_POLICY
    saved_status = None
    if run_status is not None:
        require(run_status.get("router_ledger_sha256") == ledger_ref["sha256"],
                "run-status router ledger hash mismatch")
        require(run_status.get("router_delivery_audit") == audit,
                "run-status router delivery audit mismatch")
        require(report_ref is not None and run_status.get("report_sha256") == report_ref["sha256"],
                "run-status report hash mismatch")
        require(stage_ref is not None and run_status.get("summary_sha256") == stage_ref["sha256"],
                "run-status stage-summary hash mismatch")
        saved_status = {"state": run_status.get("state"),
                        "prior_queues_unchanged": run_status.get("prior_queues_unchanged"),
                        "audit_and_hashes_match": True, "source_ref": run_status_ref}
    return {
        "schema_version": "peekly-coverage-delivery-report.v1",
        "scope": "candidate final router ledger only; historical attempts are preserved separately",
        "configured_policy": policy, "expected_policy": dict(DELIVERY_POLICY),
        "policy_matches_expected": policy_matches,
        "ledger_source_ref": ledger_ref, "audit": audit,
        "zero_uncertain_resends_verified": (policy_matches and audit["valid"] is True
                                              and audit["uncertain_resend_violations"] == 0),
        "stored_run_status": saved_status,
        "disclosure": "Known completed-reply repairs are distinct from resending an uncertain delivery. Quality-rejected diagnostics are not additional provider attempts.",
    }


def _cell(value):
    if value is None:
        return "미보존 / 미확인"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _vector(value, keys):
    if value is None or any(value.get(key) is None for key in keys):
        return "미보존 / 미확인"
    return " / ".join(str(value.get(key, 0)) for key in keys)


def render_markdown(summary):
    columns = summary["comparison_columns"]
    rows = [
        ("완료·평가 세션 / 고유 페르소나", [str(c["completed_sessions"]) + " / " + str(c["distinct_personas"]) for c in columns]),
        ("세션 통과 / 실패 / 미결론", [_vector(c["session_outcomes"], ("passed", "failed", "inconclusive")) for c in columns]),
        ("전체 기준 통과 / 실패 / 미실행 / N/A", [_vector(c["criteria_all"], CRITERIA) for c in columns]),
        ("성공 기준 통과 / 실패 / 미실행 / N/A", [_vector(c["criteria_by_kind"]["success"], CRITERIA) for c in columns]),
        ("복구 기준 통과 / 실패 / 미실행 / N/A", [_vector(c["criteria_by_kind"]["recovery"], CRITERIA) for c in columns]),
        ("완료·평가 세션의 host_protocol", [c["host_protocol_on_completed_receipts"] for c in columns]),
    ]
    lines = ["# Peekly coverage comparison", "",
             "| 항목 | " + " | ".join(_cell(c["label"]) for c in columns) + " |",
             "|---|" + "---:|" * len(columns)]
    lines += ["| " + label + " | " + " | ".join(_cell(v) for v in values) + " |" for label, values in rows]
    candidate, mapping = summary["candidate"], summary["baseline_46_mapping"]
    lines += ["", "## 집계 범위", "",
              "신규 요청 " + str(candidate["requested_sessions"]) + "명 중 완료·평가 "
              + str(candidate["assessed_completed_sessions"]) + "세션을 분모로 사용했습니다. 미평가 "
              + str(len(candidate["unassessed_attempts"])) + "건은 세션·기준 판정에서 제외했습니다.",
              "ee4b145의 24세션은 고유 페르소나 15명입니다. 기존 46행은 동일 페르소나의 반복 세션을 포함합니다.",
              "696dbe3의 전체32 결과는 cb0188d.before로 교차 확인했습니다. 696dbe3 run-summary의 마지막16 결과와 혼합하지 않았습니다.",
              "cb0188d의 성공 기준 N/A 7개는 당시 데스크톱 범위 판단을 보존합니다. 신규 영수증의 N/A를 임의로 재분류하지 않았습니다.",
              "", "## 기존 미실행 기준의 대응 결과", "",
              "| 집계 | 기준 수 | 통과 | 실패 | 미실행 | 미평가 |",
              "|---|---:|---:|---:|---:|---:|"]
    for label, number, statuses in (
            ("기존 세션 가중치 유지", mapping["weighted_count"], mapping["weighted_statuses"]),
            ("고유 페르소나·요구사항", mapping["unique_persona_requirement_count"], mapping["unique_statuses"])):
        lines.append("| " + label + " | " + str(number) + " | "
                     + " | ".join(str(statuses[key]) for key in MAPPING) + " |")
    lines += ["", "실패로 바뀐 기준도 실행 범위에는 포함되지만 제품 개선을 뜻하지 않습니다. 신규 N/A는 실행 감소 성과로 세지 않습니다.",
              "", "## 신규 미실행", ""]
    if candidate["not_run_by_requirement"]:
        lines += ["| 요구사항 | 기준 수 | 페르소나 |", "|---|---:|---|"]
        for rid, group in candidate["not_run_by_requirement"].items():
            personas = sorted({r["persona_id"] for r in group["rows"]})
            lines.append("| " + _cell(rid) + " | " + str(group["criterion_units"])
                         + " | " + ", ".join(personas) + " |")
        lines.append("\n정확한 저장 사유와 증거 참조는 summary.json의 not_run_by_requirement에 보존했습니다.")
    else:
        lines.append("완료·평가 세션의 미실행 기준이 없습니다.")
    lines += ["", "## 저장된 실패 판정", ""]
    if not candidate["failures"]:
        lines.append("완료·평가 세션에 실패 판정이 없습니다.")
    for failure in candidate["failures"]:
        refs = ", ".join(item["path"] for item in failure["evidence"]) or failure["report_selector"]
        lines.append("- " + _cell(failure["persona_id"]) + " / "
                     + ", ".join(failure["requirement_ids"]) + ": " + _cell(failure["reason"])
                     + " — 증거: " + _cell(refs))
    lines += ["", "실패 목록은 저장된 판정이며 제품 결함·실행기 결함·판정기 오판의 최종 분류는 별도 검토가 필요합니다.",
              "", "## 경로와 비용", ""]
    cost = summary["provider_cost"]
    lines += ["- 설정 경로: " + _cell(cost["configured_routes"]),
              "- 실제 시도 경로: " + _cell(cost["attempted_routes"]),
              "- 대체 모델 시도: " + _cell(cost["fallback_model_attempts"]),
              "- 정책 비용 USD: " + _cell(cost["policy_cost_usd"]),
              "- 비용 필드 누락 응답: " + _cell(cost["missing_cost_responses"]),
              "- 공급자 청구 확인: " + ("확인됨" if cost["provider_invoice_verified"] else "미확인"),
              "", cost["disclosure"]]
    delivery = summary["router_delivery"]
    audit = delivery["audit"]
    lines += ["", "## 신규 코호트 전달 감사", "",
              "- 저장된 전달 정책: " + _cell(delivery["configured_policy"]),
              "- 정책 일치 / 원장 감사 유효: " + str(delivery["policy_matches_expected"])
              + " / " + str(audit["valid"]),
              "- 실제 요청 응답 기록: " + str(audit["actual_attempt_receipts"]),
              "- 완료 응답 재시도 / 품질 복구: " + str(audit["known_reply_retry_count"])
              + " / " + str(audit["known_quality_repair_count"]),
              "- 품질 거절 진단 기록: " + str(audit["quality_diagnostic_count"]),
              "- 불확실 재전송 위반: " + (str(audit["uncertain_resend_violations"])
              if audit["valid"] else "미검증 — 원장 감사 오류 있음"),
              "- 불확실 재전송 0 검증: " + str(delivery["zero_uncertain_resends_verified"]),
              "- 불확실 이벤트 call ID: " + _cell(audit["uncertain_event_call_ids"]),
              "- 불확실 / 미결 전달 guard call ID: " + _cell(audit["uncertain_guard_call_ids"])
              + " / " + _cell(audit["in_flight_guard_call_ids"]),
              "- 위반 call ID: " + _cell(audit["violation_call_ids"]),
              "- 감사 오류: " + _cell(audit["errors"]),
              "- 원장 SHA-256: " + delivery["ledger_source_ref"]["sha256"],
              "", delivery["disclosure"],
              "이 감사는 신규 코호트 원장에만 적용되며 이전 smoke의 재전송 사고 기록을 변경하지 않습니다.",
              "", "## 숫자 출처", ""]
    for source in summary["sources"]:
        lines.append("- " + (source.get("commit", "") + ":" if source.get("commit") else "")
                     + source["path"] + " — SHA-256 " + source["sha256"])
    lines += ["", "각 비교 열의 source_refs.selector가 사용한 JSON 필드를 명시합니다.",
              "입력 report의 current_valid 기록을 사용했으며 새로운 모델·브라우저 호출이나 이전 영수증 변경은 없습니다.", ""]
    return "\n".join(lines)


def build_report(repo, stage_directory, output_directory, *, requested=32, baseline_path=None):
    repo = Path(repo).resolve(strict=True)
    stage_directory = Path(stage_directory).resolve(strict=True)
    output_directory = Path(output_directory)
    require(not output_directory.is_symlink(), "output directory is a symlink")
    require(not output_directory.exists() or output_directory.is_dir(), "output path is not a directory")
    destination = output_directory.resolve()
    require(destination.is_relative_to(repo) and not destination.is_relative_to(stage_directory),
            "output must be a repository directory outside immutable stage")
    require(not any(os.path.lexists(destination / name) for name in ("summary.json", "comparison.md")),
            "report output files already exist")
    sources = []
    loaded = []
    for name in ("report.json", "stage-summary.json", "plan.json"):
        value, reference = read_json(stage_directory / name, repo)
        loaded.append(value)
        sources.append(reference)
    report, stage, plan = loaded
    baseline, baseline_ref = read_json(baseline_path or repo / NOT_RUN, repo)
    sources.append(baseline_ref)
    columns, _, historical_refs = load_baselines(repo, baseline)
    sources += historical_refs
    candidate = summarize_candidate(report, stage, plan, requested,
                                    stage_directory.relative_to(repo).as_posix())
    mapping = map_baseline(baseline, candidate)
    cost = summarize_cost(stage)
    # A missing ledger must never silently become a zero-resend assertion.
    router_ledger, ledger_ref = read_json(stage_directory / "model-router-ledger.json", repo)
    sources.append(ledger_ref)
    run_status, run_status_ref = None, None
    status_path = stage_directory.parent / "run-status.json"
    if status_path.exists():
        run_status, run_status_ref = read_json(status_path, repo)
        sources.append(run_status_ref)
    delivery = summarize_delivery(stage, router_ledger, ledger_ref,
                                  run_status=run_status, run_status_ref=run_status_ref,
                                  report_ref=sources[0], stage_ref=sources[1])
    columns.append({
        "label": "신규 요청 " + str(requested) + "명",
        "completed_sessions": candidate["assessed_completed_sessions"],
        "distinct_personas": candidate["distinct_assessed_personas"],
        "session_outcomes": candidate["session_outcomes"], "criteria_all": candidate["criteria_all"],
        "criteria_by_kind": candidate["criteria_by_kind"],
        "host_protocol_on_completed_receipts": candidate["host_protocol"]["assessed_completed"],
        "source_refs": [dict(sources[0], selector="tasks: complete + operational_completed + receipt + current_valid"),
                        dict(sources[1], selector="completed_receipt_summary; counts; sessions")],
    })
    summary = {
        "schema_version": "peekly-coverage-comparison.v1",
        "counting_rule": "Only queue-complete, operationally-completed, receipted and recorded-current-valid tasks are assessed.",
        "comparison_columns": columns, "candidate": candidate,
        "baseline_46_mapping": mapping, "provider_cost": cost,
        "router_delivery": delivery, "sources": sources,
        "limitations": ["Different cohort sizes and repeated baseline people prevent an unqualified overall improvement rate.",
                        "Not-run reduction measures exercised criteria, not the number of fixed product defects.",
                        "Evidence paths and recorded artifact hashes are preserved; artifact bytes are not independently revalidated here.",
                        "Historical missing criterion or host_protocol values remain null."],
        "new_model_calls": 0, "new_browser_calls": 0,
    }
    # Refuse a concurrent report rewrite before creating any deliverable.
    for reference in sources:
        if "commit" not in reference:
            require(sha((repo / reference["path"]).read_bytes()) == reference["sha256"],
                    "input changed during offline aggregation")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700, exist_ok=True)
    for name, content in (
            ("summary.json", json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n"),
            ("comparison.md", render_markdown(summary))):
        with (destination / name).open("x", encoding="utf-8") as stream:
            stream.write(content)
    return {"output": destination.relative_to(repo).as_posix(),
            "requested": requested, "assessed_completed": candidate["assessed_completed_sessions"],
            "criteria_all": candidate["criteria_all"], "baseline_46": mapping["weighted_statuses"],
            "baseline_unique": mapping["unique_statuses"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repo", type=Path, required=True,
                        help="already-authorized private archive checkout containing the pinned baselines")
    parser.add_argument("--requested", type=int, default=32)
    parser.add_argument("--not-run-baseline", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build_report(args.repo, args.stage, args.output,
                                      requested=args.requested, baseline_path=args.not_run_baseline),
                         ensure_ascii=False, sort_keys=True))
    except (ReportError, OSError, KeyError, TypeError) as exc:
        print("Offline report refused: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
