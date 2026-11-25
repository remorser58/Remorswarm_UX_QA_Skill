"""Current-source and artifact admission for historical scalable-run reports.

This reader never claims work, renews a lease, sends a request, or rewrites a
historical result. Operational completion and current evidence validity differ.
"""
from __future__ import annotations

import copy
import json
import re
from contextlib import contextmanager

from uxresearch.canonical import EngineError, digest
from uxresearch.storage import Store, safe_path
from . import swarm
from .library import Library


def fail(code, reason):
    raise EngineError(code, reason)


def _issue(exc):
    # Never echo an exception string: file errors and rejected content can embed
    # private native paths, identifiers or source text.
    code = exc.issue.get("code", "") if isinstance(exc, EngineError) else ""
    if not isinstance(code, str) or not re.fullmatch(r"[a-z0-9_]{1,80}", code):
        code = "current_validation_failed"
    return dict(code=code, reason="Current sources or evidence could not be validated; historical results are preserved.",
                next_step="Inspect the original source or evidence and its binding. Do not redispatch or overwrite the historical run.")


@contextmanager
def _library_view(path):
    library = Library(path, reference_guard=lambda record: None)
    # A non-None guard selects the existing Library's read-only research
    # validation path. The authoritative PRD/persona/research checks still run.
    # Store inspection never creates a missing lock or changes its permissions.
    with Store(library.root, read_only=True) as lock:
        library.lock = lock
        try:
            yield library
        finally:
            library.lock = None


def _receipt(queue, row, receipt, result, checkpoint):
    plan, job = queue.plan, queue.jobs[row["job_id"]]
    task, binding = job["task"], job["binding"]
    swarm.ident(row["job_id"])
    swarm.ident(task["id"])
    root = safe_path(queue.root / "sessions" / row["job_id"], queue.root)
    if not root.is_dir() or root.stat().st_mode & 0o077:
        fail("evidence_integrity", "The original private session evidence directory is unavailable.")
    if not isinstance(receipt, dict):
        fail("receipt_binding", "Historical receipt is missing.")
    expected = dict(task_id=task["id"], build_sha256=plan["build"]["sha256"],
                    persona_revision=binding["revision"], profile_sha256=binding["profile_sha256"])
    if any(receipt.get(key) != value for key, value in expected.items()):
        fail("receipt_binding", "Historical receipt no longer matches its planned task, build and persona.")
    swarm._receipt(root, dict(task=task, attempts=1), receipt)
    if result is not None:
        if (result.get("evidence_root") != str(root) or result.get("mode") != plan["mode"]
                or result.get("ux_outcome") != receipt["outcome"]):
            fail("result_binding", "Historical result classification or evidence root is inconsistent.")
        first = result.get("first_judgment")
        sealed = result.get("first_judgment_sha256")
        if result.get("operational_completed") is True and (not sealed or not first):
            fail("judgment_integrity", "Operational completion requires a sealed first judgment.")
    else:
        first, sealed = checkpoint.get("first_judgment"), row.get("first_judgment_sha256")
    if sealed is not None and (not isinstance(first, dict) or digest(first) != sealed):
        fail("judgment_integrity", "The judgment sealed before same-persona review changed.")
    return receipt["outcome"]


def completed_receipt_summary(report):
    """A completed-only denominator alongside, never instead of, partial evidence."""
    statuses = ("passed", "failed", "inconclusive", "blocked", "skipped")
    criterion_statuses = ("passed", "failed", "not_run", "not_applicable")
    summary = dict(completed_sessions=0, assessed_completed_sessions=0,
        distinct_completed_personas=0, persona_ids=[],
        session_outcomes={key: 0 for key in statuses},
        criteria_all={key: 0 for key in criterion_statuses},
        criteria_by_kind={kind: {key: 0 for key in criterion_statuses}
                          for kind in ("success", "recovery")},
        excluded_attempt_statuses={},
        host_protocol_on_completed_receipts=0)
    personas = []
    for row in report.get("tasks", []):
        result = row.get("result") or {}
        receipt = result.get("receipt")
        complete = (row.get("status") == "complete"
                    and result.get("operational_completed") is True
                    and isinstance(receipt, dict))
        if complete:
            summary["completed_sessions"] += 1
            personas.append(row["persona_id"])
            if any("host_protocol" in str(value) for value in
                   (row.get("problem"), result.get("problem"), row.get("current_issue"))):
                summary["host_protocol_on_completed_receipts"] += 1
        if not complete or row.get("current_valid") is not True:
            key = row.get("status") or "unknown"
            summary["excluded_attempt_statuses"][key] = summary["excluded_attempt_statuses"].get(key, 0) + 1
            continue
        summary["assessed_completed_sessions"] += 1
        outcome = row.get("current_ux_outcome") or receipt["outcome"]
        summary["session_outcomes"][outcome] += 1
        for criterion in receipt.get("criteria", []):
            kind, status = criterion["kind"], criterion["status"]
            summary["criteria_all"][status] += 1
            summary["criteria_by_kind"][kind][status] += 1
    summary["persona_ids"] = sorted(set(personas))
    summary["distinct_completed_personas"] = len(set(personas))
    return summary

def current_report(queue):
    """Return historical bookkeeping plus separately revalidated evidence status.

    Unstarted jobs are unassessed, not evidence-valid. A valid partial receipt can
    retain a known UX failure without claiming operational completion.
    """
    queue.audit_events()
    queue.audit_operations()
    report = queue.report()
    evidence_rows = [row for row in report["tasks"]
                     if row["result"] is not None or row.get("receipt_preview") is not None]
    checkpoints = {}
    if evidence_rows:
        with queue._db() as db:
            for record in db.execute("SELECT id,checkpoint,checkpoint_sha FROM jobs"):
                value = json.loads(record["checkpoint"])
                if digest(value) != record["checkpoint_sha"]:
                    fail("checkpoint_integrity", "The historical checkpoint changed.")
                checkpoints[record["id"]] = value
    counts = dict(current_valid_sessions=0, blocked_sessions=0, unassessed_sessions=0,
                  ux_outcomes={outcome: 0 for outcome in ("passed", "failed", "inconclusive", "blocked", "skipped")})
    build_problem = None
    if evidence_rows:
        try:
            swarm._build(queue.plan["build"])
        except Exception as exc:
            build_problem = _issue(exc)
    for row in report["tasks"]:
        row.update(current_valid=None, current_issue=None, current_ux_outcome=None)
        result = row["result"]
        receipt = result.get("receipt") if isinstance(result, dict) else row.get("receipt_preview")
        if result is None and receipt is None:
            counts["unassessed_sessions"] += 1
            continue
        try:
            if build_problem is not None:
                row["current_issue"] = copy.deepcopy(build_problem)
                raise EngineError(build_problem["code"], "Current build validation failed.")
            job = queue.jobs[row["job_id"]]
            with _library_view(queue.plan["library_path"]) as library:
                swarm._binding(library, queue.plan["product_id"], job["task"], expected=job["binding"])
            outcome = _receipt(queue, row, receipt, result, checkpoints[row["job_id"]])
        except Exception as exc:
            row["current_valid"] = False
            row["current_issue"] = row["current_issue"] or _issue(exc)
            counts["blocked_sessions"] += 1
        else:
            row["current_valid"], row["current_ux_outcome"] = True, outcome
            counts["current_valid_sessions"] += 1
            counts["ux_outcomes"][outcome] += 1
    report["evidence_validation"] = counts
    report["completed_receipt_summary"] = completed_receipt_summary(report)
    if counts["blocked_sessions"]:
        report["next_action"] = ("Historical completion is preserved, but current source or evidence validation is blocked. "
                                 "Review each current_issue; stale outcomes are excluded from current UX totals.")
    return report
