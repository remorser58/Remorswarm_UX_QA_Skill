#!/usr/bin/env python3
"""Wait for a fresh terminal 32-person run, audit it, and optionally publish raw reports.

No Queue instance, runner, model, browser, retry, resume, or worker-stop operation
is used. --check-only never waits, writes, commits, pushes, or accesses a remote.
Generated reports are raw receipts pending independent semantic review.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/remorsearch-ux-qa"))
from uxresearch.canonical import digest
import run_peekly_completion as completion
import report_peekly_completion as reporting

base = completion.base
BRANCH = "rem/peekly-coverage-completion-20261115"
OUTPUT = Path("docs/validation/peekly-coverage-completion-20261115")
AUDITOR = Path("docs/validation/peekly-coverage-20261114/audit_final_artifacts.py")
FILES = ("summary.json", "comparison.md", "not-run-23-baseline.json",
         "artifact-audit.json", "automated-outcome.json")
TERMINAL = {"complete", "incomplete_preserved", "stopped_preserved"}
COUNTS = ("complete", "uncertain", "blocked", "cancelled", "queued", "running")
SERVED_MODELS = {"deepseek-v4.1-flash", "deepseek-v4.1-flash-free"}


class FinalizerError(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise FinalizerError(reason)


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "required_regular_file:" + str(path))
    require(path.stat().st_size <= 64 * 1024 * 1024, "json_file_exceeds_reviewed_read_bound")
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return base.digest_file(path)


def exclusive_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def inside(repo, path, scope, *, existing=False):
    repo = Path(repo).resolve(strict=True)
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else repo / candidate
    require(".." not in candidate.parts, "parent_path_component_forbidden")
    require(not any(p.is_symlink() for p in (candidate, *candidate.parents)
                    if p != repo and p.is_relative_to(repo)), "symlink_path_forbidden")
    resolved = candidate.resolve(strict=existing)
    boundary = (repo / scope).resolve()
    require(resolved.is_relative_to(boundary) and resolved != boundary.parent,
            "path_outside_reviewed_scope")
    return resolved


def validate_paths(repo, run_root, output):
    run_root = inside(repo, run_root, ".ux-loop", existing=True)
    require(run_root.is_dir() and run_root.name.startswith("peekly-completion32-"),
            "fresh_completion32_root_required")
    output = inside(repo, output, OUTPUT)
    require(output != run_root and not output.is_relative_to(run_root),
            "report_output_must_be_outside_run")
    return run_root, output


def git(repo, *arguments, timeout=30, allow_failure=False):
    result = subprocess.run(["git", "-C", str(repo), *arguments], capture_output=True,
        text=True, timeout=timeout, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if result.returncode and not allow_failure:
        raise FinalizerError("git_" + arguments[0] + "_failed:" + result.stderr.strip()[-400:])
    return result


def git_paths(repo, *arguments):
    return set(filter(None, git(repo, *arguments).stdout.split("\0")))


def publish_preflight(repo, output, expected_branch):
    require(expected_branch == BRANCH, "explicit_exact_expected_branch_required")
    require(git(repo, "branch", "--show-current").stdout.strip() == BRANCH,
            "publish_branch_mismatch")
    permitted = {(output / name).relative_to(repo).as_posix() for name in FILES}
    staged = git_paths(repo, "diff", "--cached", "--name-only", "-z")
    require(staged <= permitted, "unrelated_staged_files_preserved")
    runtime = ("skills/remorsearch-ux-qa/", "scripts/", "tests/")
    dirty = git_paths(repo, "diff", "--name-only", "-z")
    untracked = git_paths(repo, "ls-files", "--others", "--exclude-standard", "-z",
                          "--", "skills/remorsearch-ux-qa", "scripts", "tests")
    require(not any(path.startswith(runtime) for path in dirty | staged | untracked),
            "runtime_or_tests_dirty")
    return sorted(permitted)


def queue_snapshot(stage):
    """Read one consistent terminal snapshot with SQLite query_only enabled."""
    path = stage / "queue.sqlite"
    require(path.is_file() and not path.is_symlink(), "queue_file_missing_or_symlink")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only = ON")
        db.execute("BEGIN")
        jobs = [dict(row) for row in db.execute(
            "SELECT id,status,provider FROM jobs ORDER BY id")]
        operations = [dict(row) for row in db.execute(
            "SELECT id,job_id,kind,state FROM operations ORDER BY id")]
        meta = dict(db.execute("SELECT key,value FROM meta WHERE key='plan_sha'"))
    return dict(jobs=jobs, operations=operations, meta=meta)


def zero_or_missing(value):
    return value is None or type(value) in (int, float) and value == 0


def free_delivery(plan, summary, ledger):
    require(plan.get("mode") == "live" and plan.get("limits", {}).get("budget_microusd") == 0,
            "zero_budget_live_plan_required")
    providers = plan.get("providers", {})
    require(set(providers) == {"local-router"}, "single_reviewed_provider_required")
    provider = providers["local-router"]
    spec, billing = provider.get("spec", {}), provider.get("billing_review", {})
    require(provider.get("mode") == "live" and spec.get("model") == "tokenmaxx-deepseek-v4-1-flash-free"
            and spec.get("input_price_per_million") == 0 and spec.get("output_price_per_million") == 0
            and billing.get("requested_model") == base.MODEL
            and billing.get("free_tier") is True and billing.get("billing_source") == "free"
            and billing.get("input_price_per_million") == 0 and billing.get("output_price_per_million") == 0,
            "reviewed_free_TOKENMAXX_provider_required")
    require(summary.get("configured_routes") == [base.MODEL]
            and summary.get("fallback_model_attempts") == 0
            and summary.get("delivery_policy") == base.DELIVERY_POLICY,
            "free_route_or_delivery_policy_mismatch")
    require(ledger.get("fallback_order") == [base.MODEL]
            and set(ledger.get("routes", {})) == {base.MODEL},
            "router_route_ledger_mismatch")
    # The live runner adds this derived field only to stage-summary.json.
    # Bind every raw counter and independently recompute the extra statistic.
    expected_stats = {}
    for route, stats in ledger["routes"].items():
        require(all(type(stats.get(key)) is int and stats[key] >= 0
                    for key in ("attempts", "failures", "quality_rejections")),
                "router_route_counters_invalid")
        expected_stats[route] = dict(stats, failure_rate=(
            (stats["failures"] + stats["quality_rejections"]) / stats["attempts"]
            if stats["attempts"] else 0.0))
    require(summary.get("model_attempts") == expected_stats,
            "router_route_summary_or_derived_rate_mismatch")
    cost = summary.get("cost_record", {})
    require(cost.get("authorized_route") == "user_confirmed_free_TOKENMAXX"
            and cost.get("policy_cost_usd") == 0
            and isinstance(cost.get("provider_reported_cost_values"), list)
            and all(zero_or_missing(v) for v in cost["provider_reported_cost_values"]),
            "unexpected_or_missing_cost_policy")
    for event in ledger.get("events", []):
        require(event.get("requested_model") == base.MODEL and event.get("provider") == "TOKENMAXX"
                and event.get("served_model") in SERVED_MODELS | {None}
                and event.get("status") != "served_model_mismatch"
                and zero_or_missing(event.get("provider_cost_microusd"))
                and zero_or_missing(event.get("provider_reported_cost")),
                "unapproved_or_priced_router_event")
    for usage in summary.get("provider_usage", []):
        require(usage.get("provider") == "TOKENMAXX" and usage.get("model") in SERVED_MODELS
                and usage.get("charged_or_estimated_microusd") == 0,
                "unapproved_or_priced_provider_usage")
    audit = base.router_delivery_audit(ledger)
    require(audit["valid"] is True and audit["uncertain_resend_violations"] == 0,
            "uncertain_resend_or_invalid_delivery_ledger")
    require(audit["actual_attempt_receipts"] > 0
            and all(value <= 3 for value in audit["attempts_by_call_id"].values()),
            "missing_attempts_or_known_reply_retry_limit_exceeded")
    return audit


def frozen_inputs(repo, provenance, status):
    require(Path(provenance.get("fixtures", "")).resolve() == completion.FIXTURES.resolve()
            and Path(provenance.get("library", "")).resolve() == completion.LIBRARY.resolve()
            and provenance.get("build", {}).get("artifact_path") == str(completion.BUILD.resolve())
            and provenance.get("build", {}).get("sha256") == completion.BUILD_SHA256,
            "frozen_input_path_mismatch")
    base.require_same_freeze(provenance["freeze"], completion.capture_freeze())
    completion.require_target_receipts(provenance, status)
    prior = provenance.get("prior_queues")
    require(isinstance(prior, list) and prior, "prior_queue_snapshots_required")
    for row in prior:
        path = inside(repo, row["path"], ".ux-loop", existing=True)
        require(path.name == "queue.sqlite", "prior_queue_path_invalid")
    integrity = base.prior_queue_integrity(prior)
    require(integrity["prior_queues_unchanged"] is True
            and all(status.get(key) == value for key, value in integrity.items()),
            "prior_queue_snapshot_changed")
    return integrity


def inspect_terminal(repo, run_root):
    stage = inside(repo, run_root / "stage-32", ".ux-loop", existing=True)
    paths = dict(provenance=run_root / "input-provenance.json",
        status=run_root / "run-status.json", report=stage / "report.json",
        summary=stage / "stage-summary.json", envelope=stage / "plan.json",
        ledger=stage / "model-router-ledger.json")
    values = {key: read_json(path) for key, path in paths.items()}
    hashes = {key: sha(path) for key, path in paths.items()}
    provenance, status, report, summary, envelope, ledger = (
        values[key] for key in ("provenance", "status", "report", "summary", "envelope", "ledger"))
    require(status.get("state") in TERMINAL, "run_not_terminal")
    require(provenance.get("schema_version") == "peekly-completion-run.v1"
            and provenance.get("stage") == "cohort"
            and provenance.get("route") == base.MODEL
            and provenance.get("parallel") == 2 and provenance.get("turns") == 80
            and provenance.get("turn_policy") == completion.TURN_POLICY
            and provenance.get("budget_microusd") == 0
            and provenance.get("prior_queues_opened_read_only") is True
            and provenance.get("uncertain_resend_authorized") is False,
            "reviewed_fresh_cohort_provenance_required")
    base.exact_personas(provenance.get("persona_ids", []), base.ALL_IDS)
    for field, key in (("input_provenance_sha256", "provenance"), ("report_sha256", "report"),
                       ("summary_sha256", "summary"), ("router_ledger_sha256", "ledger")):
        require(status.get(field) == hashes[key], "stale_terminal_hash:" + field)
    plan = envelope.get("plan", {})
    require(digest(plan) == envelope.get("sha256") == report.get("plan_sha256"),
            "plan_seal_mismatch")
    require(plan.get("limits", {}).get("parallel") == 2 and plan["limits"].get("turns") == 80,
            "reviewed_cohort_limits_required")
    jobs, tasks = plan.get("jobs", []), report.get("tasks", [])
    require(len(jobs) == len(tasks) == 32, "exact_32_planned_and_reported_jobs_required")
    base.exact_personas([job["task"]["persona_id"] for job in jobs], base.ALL_IDS)
    base.exact_personas([task["persona_id"] for task in tasks], base.ALL_IDS)
    job_ids = [job["id"] for job in jobs]
    base.reject_reused_jobs(job_ids, provenance.get("forbidden_job_ids", []))
    require(set(job_ids) == set(provenance.get("job_ids", []))
            and len(provenance["job_ids"]) == 32, "provenance_job_set_mismatch")
    for old in provenance.get("prior_queues", []):
        require(not set(job_ids) & {row["id"] for row in old["jobs"]},
                "prior_job_identity_overlap")
        require(not Path(old["path"]).resolve().is_relative_to(run_root),
                "fresh_queue_in_prior_snapshot")
    snapshot = queue_snapshot(stage)
    require(snapshot["meta"].get("plan_sha") == envelope["sha256"],
            "queue_plan_seal_mismatch")
    actual = {row["id"]: row for row in snapshot["jobs"]}
    require(set(actual) == set(job_ids) == {row["job_id"] for row in tasks},
            "queue_plan_report_job_set_mismatch")
    require(all(row["status"] in COUNTS and row["status"] not in {"queued", "running"}
                for row in actual.values()), "queue_not_terminal")
    counted = Counter(row["status"] for row in actual.values())
    counts = {key: counted[key] for key in COUNTS}
    for value in (status, report, summary):
        require(value.get("counts") == counts, "terminal_queue_counts_mismatch")
    for task in tasks:
        require(actual[task["job_id"]]["status"] == task.get("status")
                and actual[task["job_id"]]["provider"] == task.get("provider"),
                "report_task_status_or_provider_mismatch")
    require(not any(row["state"] == "intent" for row in snapshot["operations"]),
            "unsettled_active_queue_intent")
    require(summary.get("sessions") == 32
            and summary.get("browser_shutdown_confirmed") is True,
            "terminal_browser_closure_required")
    base.exact_personas(summary.get("persona_ids", []), base.ALL_IDS)
    require(summary.get("fixture_manifest_sha256")
            == provenance.get("freeze", {}).get("fixtures", {}).get("manifest_sha256"),
            "stage_fixture_freeze_mismatch")
    audit = free_delivery(plan, summary, ledger)
    require(status.get("router_delivery_audit") == audit, "saved_delivery_audit_mismatch")
    integrity = frozen_inputs(repo, provenance, status)
    require(all(sha(path) == hashes[key] for key, path in paths.items()),
            "inputs_changed_during_terminal_validation")
    return dict(run_root=run_root, stage=stage, paths=paths, hashes=hashes,
                values=values, counts=counts, audit=audit, prior_integrity=integrity)


def same_inputs(bundle):
    require(all(sha(path) == bundle["hashes"][key] for key, path in bundle["paths"].items()),
            "terminal_inputs_changed_after_validation")


def append_event(log, state, **fields):
    value = dict(schema_version="peekly-completion-finalizer-event.v1", at=now(), state=state, **fields)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return value


def wait_terminal(run_root, log, *, poll_seconds=30, max_wait_seconds=86400):
    require(1 <= poll_seconds <= 30 and 1 <= max_wait_seconds <= 172800,
            "bounded_polling_required")
    expected = sha(run_root / "input-provenance.json")
    deadline = time.monotonic() + max_wait_seconds
    while True:
        status = read_json(run_root / "run-status.json")
        require(status.get("input_provenance_sha256") == expected
                and sha(run_root / "input-provenance.json") == expected,
                "input_provenance_changed_while_waiting")
        state = status.get("state")
        if state in TERMINAL:
            return status
        require(state == "running", "unknown_run_state")
        remaining = deadline - time.monotonic()
        require(remaining > 0, "watch_timeout_worker_left_untouched")
        append_event(log, "waiting", run_state=state, counts=status.get("counts"))
        time.sleep(min(poll_seconds, remaining))


def validate_existing_outcome(output, bundle):
    outcome = read_json(output / FILES[-1])
    require(outcome.get("schema_version") == "peekly-completion-automated-outcome.v1"
            and outcome.get("source_hashes") == bundle["hashes"]
            and outcome.get("semantic_review_status") == "pending_manual_review"
            and outcome.get("postprocess_status") == "raw_report_and_byte_audit_completed"
            and set(outcome.get("generated_files", {})) == set(FILES[:-1]),
            "existing_output_not_owned_or_stale")
    for name, value in outcome["generated_files"].items():
        require(sha(output / name) == value, "existing_generated_file_changed:" + name)
    return outcome


def generate(repo, output, bundle, log):
    """New report names only; a fully sealed prior invocation can be verified."""
    existing = [name for name in FILES if os.path.lexists(output / name)]
    if existing:
        require(set(existing) == set(FILES), "partial_output_preserved_no_overwrite")
        return validate_existing_outcome(output, bundle)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    result = reporting.build_report(repo, bundle["stage"], output, requested=32)
    append_event(log, "raw_report_created", result=result)
    command = [sys.executable, str(repo / AUDITOR), str(bundle["stage"]), str(output / "artifact-audit.json")]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=1800,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    require(completed.returncode == 0, "artifact_audit_failed:" + completed.stderr[-400:])
    audited = read_json(output / "artifact-audit.json")
    require(audited.get("audit_passed") is True and audited.get("mismatches") == 0
            and audited.get("source_files_unchanged") is True
            and audited.get("prior_queues_unchanged") is True
            and audited.get("new_model_calls") == audited.get("new_browser_calls")
                == audited.get("queue_writes") == 0, "artifact_audit_not_clean")
    same_inputs(bundle)
    summary = read_json(output / "summary.json")
    verification = summary.get("verification", {})
    require(all(verification.get(key) is True for key in (
        "terminal_queue", "prior_queues_unchanged", "zero_uncertain_resends_verified",
        "browser_shutdown_confirmed")), "aggregate_verification_failed")
    outcome = dict(schema_version="peekly-completion-automated-outcome.v1", created_at=now(),
        run_root=bundle["run_root"].relative_to(repo).as_posix(),
        run_state=bundle["values"]["status"]["state"], queue_counts=bundle["counts"],
        source_hashes=bundle["hashes"],
        product_target=dict(frozen=bundle["values"]["provenance"]["freeze"]["product_target"],
            before=bundle["values"]["provenance"]["target_before"],
            after=bundle["values"]["status"]["target_after"],
            served_bytes_verified_before_and_after=True),
        postprocess_status="raw_report_and_byte_audit_completed",
        semantic_review_status="pending_manual_review", coverage_target_met=None,
        publication_status="Recorded separately in the ignored finalizer event ledger.",
        raw_candidate=dict(assessed_sessions=summary["candidate"]["assessed_completed_sessions"],
                           criteria_all=summary["candidate"]["criteria_all"]),
        raw_baseline_23_mapping=summary["baseline_23_mapping"]["weighted_statuses"],
        uncertain_attempts_excluded=True, automatic_verdict_overrides=False,
        generated_files={name: sha(output / name) for name in FILES[:-1]},
        limitations=["Byte/seal checks do not independently establish visual or semantic correctness.",
            "All new counts are raw receipts pending manual review; no near-zero or product-success claim is made.",
            "Uncertain, absent and N/A matches receive no executed-coverage credit.",
            "Prior queue integrity is the launcher's read-only job/status/pending-operation snapshot.",
            "Free routing and policy zero do not verify provider invoices; missing billed costs remain missing."],
        new_model_calls=0, new_browser_calls=0, queue_writes=0)
    exclusive_json(output / FILES[-1], outcome)
    append_event(log, "raw_report_and_byte_audit_completed", counts=bundle["counts"],
                 outcome_sha256=sha(output / FILES[-1]))
    return outcome


def remote_sha(repo):
    result = git(repo, "ls-remote", "--exit-code", "--heads", "origin",
                 "refs/heads/" + BRANCH, allow_failure=True)
    if result.returncode == 2 and not result.stdout:
        return None
    require(result.returncode == 0, "remote_ref_read_failed")
    rows = result.stdout.splitlines()
    require(len(rows) == 1 and rows[0].split()[1] == "refs/heads/" + BRANCH,
            "remote_ref_ambiguous")
    value = rows[0].split()[0]
    require(len(value) == 40 and all(c in "0123456789abcdef" for c in value),
            "remote_sha_invalid")
    return value


def publish(repo, output, bundle, expected_branch, log):
    paths = publish_preflight(repo, output, expected_branch)
    validate_existing_outcome(output, bundle)
    same_inputs(bundle)
    frozen_inputs(repo, bundle["values"]["provenance"], bundle["values"]["status"])
    dirty = git_paths(repo, "status", "--porcelain=v1", "-z", "--", *paths)
    message = "docs: record raw Peekly completion " + bundle["run_root"].name
    if dirty:
        git(repo, "add", "--", *paths)
        require(git_paths(repo, "diff", "--cached", "--name-only", "-z") == set(paths),
                "generated_documents_not_the_exact_staged_set")
        message_path = log.parent / ("commit-message-" + str(time.time_ns()) + ".txt")
        with message_path.open("x", encoding="utf-8") as stream:
            stream.write(message + "\n\nRaw receipts and byte audit; independent semantic review remains pending.\n")
        git(repo, "commit", "--only", "--file", str(message_path), "--", *paths, timeout=120)
    # Also check after a new commit: another process must not move HEAD to an
    # unrelated commit between our commit command and its read-back.
    require(git(repo, "log", "-1", "--format=%s").stdout.strip() == message,
            "existing_documents_not_at_owned_report_commit")
    require(git_paths(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD") == set(paths),
            "owned_report_commit_contains_other_changes")
    commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    append_event(log, "committed", commit=commit, branch=BRANCH)
    publish_preflight(repo, output, expected_branch)
    require(git(repo, "rev-parse", "HEAD").stdout.strip() == commit, "HEAD_changed_before_push")
    prior_remote = remote_sha(repo)
    if prior_remote != commit:
        if prior_remote is not None:
            require(git(repo, "merge-base", "--is-ancestor", prior_remote, commit,
                        allow_failure=True).returncode == 0, "remote_not_ancestor_no_force_push")
        append_event(log, "push_started", commit=commit, prior_remote_sha=prior_remote, branch=BRANCH)
        git(repo, "push", "origin", commit + ":refs/heads/" + BRANCH, timeout=180)
    confirmed = remote_sha(repo)
    require(confirmed == commit, "remote_sha_not_confirmed")
    append_event(log, "published", commit=commit, remote_sha=confirmed, branch=BRANCH,
                 semantic_review_status="pending_manual_review")
    return commit


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--expected-branch")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--repo", type=Path,
                        help="this finalizer's own approved archive checkout; required for report generation")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-wait-seconds", type=int, default=86400)
    args = parser.parse_args(argv)
    if args.repo is None and not args.check_only:
        parser.error("report generation requires --repo with an already-authorized private archive checkout")
    if args.repo is not None and args.repo.resolve() != ROOT.resolve():
        parser.error("--repo must name this finalizer's own checkout; run the script from the approved archive")
    return args


def run(args, *, repo):
    repo = Path(repo).resolve(strict=True)
    run_root, output = validate_paths(repo, args.run_root, args.output)
    require(1 <= args.poll_seconds <= 30 and 1 <= args.max_wait_seconds <= 172800,
            "bounded_polling_required")
    if args.publish:
        publish_preflight(repo, output, args.expected_branch)
    status = read_json(run_root / "run-status.json")
    if args.check_only:
        if status.get("state") == "running":
            require(sha(run_root / "input-provenance.json") == status.get("input_provenance_sha256"),
                    "input_provenance_hash_mismatch")
            return dict(state="waiting_for_terminal", ready=False, mutations=0)
        bundle = inspect_terminal(repo, run_root)
        if any(os.path.lexists(output / name) for name in FILES):
            validate_existing_outcome(output, bundle)
        return dict(state="terminal_checks_passed", ready=True, counts=bundle["counts"],
                    semantic_review_status="pending_manual_review", mutations=0)
    log_dir = repo / ".ux-loop" / "peekly-completion-finalizers" / run_root.name
    log_dir = inside(repo, log_dir, ".ux-loop")
    require(git(repo, "check-ignore", "--quiet", "--", str(log_dir / "events.jsonl"),
                allow_failure=True).returncode == 0, "finalizer_log_must_be_ignored")
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log = log_dir / "events.jsonl"
    require(not log.is_symlink() and not (log_dir / "lock").is_symlink(),
            "finalizer_log_or_lock_symlink")
    with (log_dir / "lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise FinalizerError("another_finalizer_owns_this_run")
        append_event(log, "started", run_root=str(run_root), output=str(output), publish=args.publish)
        try:
            wait_terminal(run_root, log, poll_seconds=args.poll_seconds,
                          max_wait_seconds=args.max_wait_seconds)
            bundle = inspect_terminal(repo, run_root)
            append_event(log, "terminal_checks_passed", counts=bundle["counts"], source_hashes=bundle["hashes"])
            outcome = generate(repo, output, bundle, log)
            commit = publish(repo, output, bundle, args.expected_branch, log) if args.publish else None
            result = dict(state="published_raw" if commit else "reported_raw", counts=bundle["counts"],
                output=str(output), commit=commit, semantic_review_status=outcome["semantic_review_status"],
                finalizer_log=str(log))
            append_event(log, "finished", result=result)
            return result
        except Exception as exc:
            try:
                raw_status = read_json(run_root / "run-status.json")
                run_state, raw_counts = raw_status.get("state"), raw_status.get("counts")
            except Exception:
                run_state, raw_counts = "unreadable_preserved", None
            append_event(log, "failed_preserved", error_type=type(exc).__name__, reason=str(exc)[:600],
                         run_state=run_state, raw_run_counts=raw_counts, counts_verified=False,
                         postprocess_status="failed_preserved", semantic_review_status="pending_manual_review")
            raise


if __name__ == "__main__":
    try:
        print(json.dumps(run(parse_args(), repo=ROOT), ensure_ascii=False, sort_keys=True), flush=True)
    except Exception as exc:
        print(json.dumps(dict(state="failed_preserved", error_type=type(exc).__name__,
                              reason=str(exc)[:600])), file=sys.stderr, flush=True)
        raise SystemExit(2)
