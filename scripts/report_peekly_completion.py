#!/usr/bin/env python3
"""Offline five-column comparison with the pinned 65f52f7 remaining-23 baseline."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import report_peekly_coverage as old

BASE_COMMIT = "65f52f78918d097c39ac8eb5ec49ed6daea537bc"
BASE_PATH = "docs/validation/peekly-coverage-20261114/reviewed-summary.json"
BASE_SHA = "f803cd44fcad79d203c826d36ee2f8e1409538e6f67ae06a240e8c634c21b4dc"


def baseline23(reviewed, reference):
    candidate = reviewed["candidate"]
    old.same_counts(candidate["criteria_all"],
        dict(passed=71, failed=8, not_run=23, not_applicable=19), "65f baseline counts differ")
    old.require(candidate["assessed_completed_sessions"] == 29, "65f baseline denominator differs")
    rows, keys = [], set()
    for item in candidate["criteria"]:
        if item["status"] != "not_run":
            continue
        old.require(len(item["requirement_ids"]) == 1, "remaining criterion has ambiguous requirement")
        requirement = item["requirement_ids"][0]
        key = item["persona_id"], item["kind"], requirement
        old.require(key not in keys, "remaining baseline contains duplicate identity")
        keys.add(key)
        rows.append(dict(id="NR65-" + str(len(rows)+1).zfill(2),
            queue=".ux-loop/peekly-coverage32-20261114/stage-32",
            job=item["job_id"], persona=item["persona_id"], requirement=requirement,
            kind=item["kind"], reason=item["reason"], evidence=item.get("evidence", []),
            source_ref=dict(reference, selector="candidate.criteria[persona_id="
                + item["persona_id"] + ",kind=" + item["kind"] + ",index=" + str(item["index"]) + "]")))
    old.require(len(rows) == 23, "remaining baseline is not 23 distinct criteria")
    return dict(schema_version="peekly-remaining-baseline.v1", baseline_commit=BASE_COMMIT,
                counting_rule="Distinct persona, requirement and criterion kind; no N/A credit.",
                source_ref=reference, rows=rows)


def load_reviewed(repo):
    result = subprocess.run(["git", "-C", str(repo), "show", BASE_COMMIT + ":" + BASE_PATH],
                            capture_output=True, check=False)
    old.require(result.returncode == 0 and old.sha(result.stdout) == BASE_SHA,
                "pinned 65f reviewed baseline unavailable or digest changed")
    reference = dict(commit=BASE_COMMIT, path=BASE_PATH, sha256=BASE_SHA, bytes=len(result.stdout))
    value = old._json(result.stdout)
    return value, reference, baseline23(value, reference)


def comparison_column(label, candidate, refs):
    return dict(label=label, completed_sessions=candidate["assessed_completed_sessions"],
                distinct_personas=candidate["distinct_assessed_personas"],
                session_outcomes=candidate["session_outcomes"], criteria_all=candidate["criteria_all"],
                criteria_by_kind=candidate["criteria_by_kind"],
                host_protocol_on_completed_receipts=candidate["host_protocol"]["assessed_completed"],
                source_refs=refs)


def render_markdown(summary):
    text = old.render_markdown(summary)
    mapping = summary["baseline_23_mapping"]
    totals = mapping["weighted_statuses"]
    lines = ["## 직전 65f52f7의 미실행 23개 대응", "",
        "| 기존 기준 | 통과 | 실패 | 미실행 | 미평가 |", "|---:|---:|---:|---:|---:|",
        "| 23 | " + " | ".join(str(totals[key]) for key in old.MAPPING) + " |", "",
        "실행 확인은 통과와 실패의 합입니다. 미평가에는 불확실 세션·누락 기준·조건부 N/A가 포함되며 감소 성과로 세지 않습니다.",
        "전체 신규 미실행 수와 기존 23개의 대응 결과를 함께 표시합니다. 분모가 다른 결과를 단순한 제품 개선율로 해석하지 않습니다.", "",
        "| 페르소나 | 기준 | 새 결과 |", "|---|---|---|"]
    for row in mapping["weighted_rows"]:
        lines.append("| " + row["persona_id"] + " | " + row["requirement_id"]
                     + " | " + row["status"] + " |")
    return text + "\n" + "\n".join(lines) + "\n"


def build_report(repo, stage_directory, output_directory, *, requested=32):
    repo = Path(repo).resolve(strict=True)
    stage_directory = Path(stage_directory).resolve(strict=True)
    destination = Path(output_directory)
    old.require(not destination.is_symlink(), "output is a symlink")
    destination = destination.resolve()
    old.require(destination.is_relative_to(repo) and not destination.is_relative_to(stage_directory),
                "output must be in repository outside immutable stage")
    names = ("summary.json", "comparison.md", "not-run-23-baseline.json")
    old.require(not any(os.path.lexists(destination / name) for name in names), "report output already exists")
    values, sources = [], []
    for name in ("report.json", "stage-summary.json", "plan.json"):
        value, reference = old.read_json(stage_directory / name, repo)
        values.append(value)
        sources.append(reference)
    report, stage, plan = values
    original, original_ref = old.read_json(repo / old.NOT_RUN, repo)
    sources.append(original_ref)
    columns, _, historical = old.load_baselines(repo, original)
    sources += historical
    reviewed, reviewed_ref, remaining = load_reviewed(repo)
    sources.append(reviewed_ref)
    columns.append(comparison_column("65f52f7·직전 증거감사", reviewed["candidate"],
        [dict(reviewed_ref, selector="candidate: independent evidence review of the previous 29 completed sessions")]))
    candidate = old.summarize_candidate(report, stage, plan, requested,
                                        stage_directory.relative_to(repo).as_posix())
    columns.append(comparison_column("신규 " + str(requested) + "명·실제 실행", candidate,
        [dict(sources[0], selector="tasks: complete + operational_completed + receipt + current_valid"),
         dict(sources[1], selector="completed_receipt_summary; counts; sessions")]))
    ledger, ledger_ref = old.read_json(stage_directory / "model-router-ledger.json", repo)
    sources.append(ledger_ref)
    status, status_ref = old.read_json(stage_directory.parent / "run-status.json", repo)
    sources.append(status_ref)
    delivery = old.summarize_delivery(stage, ledger, ledger_ref, run_status=status,
        run_status_ref=status_ref, report_ref=sources[0], stage_ref=sources[1])
    provenance, provenance_ref = old.read_json(stage_directory.parent / "input-provenance.json", repo)
    sources.append(provenance_ref)
    old.require(status["input_provenance_sha256"] == provenance_ref["sha256"], "input provenance digest differs")
    old.require(stage.get("fixture_manifest_sha256") == provenance["freeze"]["fixtures"]["manifest_sha256"],
                "stage fixture manifest differs from frozen provenance")
    old.require(provenance.get("uncertain_resend_authorized") is False, "unexpected uncertain resend authorization")
    summary = dict(schema_version="peekly-completion-comparison.v1",
        counting_rule="Only queue-complete, operationally-completed, receipted and recorded-current-valid sessions are assessed.",
        comparison_columns=columns, candidate=candidate,
        baseline_46_mapping=old.map_baseline(original, candidate),
        baseline_23_mapping=old.map_baseline(remaining, candidate),
        baseline_23_source=reviewed_ref, provider_cost=old.summarize_cost(stage),
        router_delivery=delivery, input_provenance=provenance_ref, sources=sources,
        limitations=[
            "The 65f column includes its published independent semantic review; the new column uses the new run receipts.",
            "No prior case-specific judgment override is automatically applied to a new job.",
            "Different completed cohorts prevent treating total not_run reduction as a causal product improvement.",
            "N/A and unassessed matches earn no coverage credit.",
            "Recorded artifact hashes require a separate byte and semantic audit.",
            "Historical unknown criterion values remain null."],
        verification=dict(terminal_queue=not any(candidate["queue_counts"].get(key, 0) for key in ("queued", "running")),
            prior_queues_unchanged=status.get("prior_queues_unchanged") is True,
            zero_uncertain_resends_verified=delivery["zero_uncertain_resends_verified"],
            browser_shutdown_confirmed=stage.get("browser_shutdown_confirmed") is True),
        call_count_scope="The following zero counts describe this offline aggregation only; actual run calls are in stage-summary.json and router_delivery.audit.",
        new_model_calls=0, new_browser_calls=0)
    for reference in sources:
        if "commit" not in reference:
            old.require(old.sha((repo / reference["path"]).read_bytes()) == reference["sha256"],
                        "input changed during aggregation")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    contents = (json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                render_markdown(summary),
                json.dumps(remaining, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    for name, content in zip(names, contents):
        with (destination / name).open("x", encoding="utf-8") as stream:
            stream.write(content)
    return dict(output=destination.relative_to(repo).as_posix(), requested=requested,
                assessed=candidate["assessed_completed_sessions"], criteria_all=candidate["criteria_all"],
                prior23=summary["baseline_23_mapping"]["weighted_statuses"],
                original46=summary["baseline_46_mapping"]["weighted_statuses"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repo", type=Path, required=True,
                        help="already-authorized private archive checkout containing the pinned baseline")
    parser.add_argument("--requested", type=int, default=32)
    args = parser.parse_args()
    try:
        print(json.dumps(build_report(args.repo, args.stage, args.output, requested=args.requested),
                         ensure_ascii=False, sort_keys=True))
    except (old.ReportError, OSError, KeyError, TypeError) as exc:
        print("Offline report refused: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
