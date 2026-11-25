"""Read-only comparison of current, evidence-backed persona journey records."""
from __future__ import annotations

from contextlib import ExitStack
import re

from uxresearch.canonical import EngineError, digest
from uxresearch.storage import Store, read_bytes, safe_path
from . import swarm


JOURNEY_FIELDS = (
    "persona_id", "requirement_ids", "goal", "starting_state", "actions",
    "decisions", "success_criteria", "recovery_criteria", "side_effects",
    "stop_conditions", "requirement_coverage",
)
LIMIT_FIELDS = ("max_parallel", "lease_seconds", "max_attempts")
TRANSITIONS = ("failed_to_passed", "passed_to_failed", "unchanged_passed", "unchanged_failed")
LIMITATIONS = swarm.LIMITATIONS + [
    "Comparison matches declared journeys and persona versions, not independently verified device, input or starting-data equivalence.",
    "Resource IDs and synthetic namespaces may differ for isolation; their real contents are not verified by this command.",
    "A failed-to-passed record is an observed outcome transition, not causal proof of a fix or measured user benefit.",
    "Only current attempts are compared; missing, superseded and unexecuted work never becomes improvement.",
]


def _existing_run(path):
    root = safe_path(path)
    if not root.is_dir():
        raise EngineError("comparison_run_missing", "Both comparison runs must already exist.",
                          next_step="Use the original baseline and replay run directories; no run was created.")
    # Reject unsafe/missing locks before Store can create or chmod one.
    for name in ("engine.lock", "swarm-state.json"):
        read_bytes(root / name, private=True)
    return root


def _snapshot(root, library):
    blockers = {}
    state = swarm._load(root, library, historical_blockers=blockers, expire_leases=False)
    if len({entry["task"]["id"] for entry in state["tasks"]}) != len(state["tasks"]):
        raise EngineError("comparison_task_identity", "Duplicate task IDs cannot be paired safely.")
    report = swarm._report_state(root, state, blockers)
    for entry in state["tasks"]:
        if set(entry["task"]) - set(JOURNEY_FIELDS) - {"id", "data_namespace", "resource_id"}:
            raise EngineError("comparison_task_schema", "Unsupported journey fields cannot be silently ignored.")
        for attempt in entry["history"] + [entry]:
            receipt = attempt.get("receipt")
            if receipt is not None and (
                receipt["task_id"] != entry["task"]["id"]
                or receipt["build_sha256"] != state["build"]["sha256"]
                or receipt["persona_revision"] != entry["binding"]["revision"]
                or receipt["profile_sha256"] != entry["binding"]["profile_sha256"]
            ):
                raise EngineError("comparison_receipt_binding", "Recorded evidence does not match its run and persona.")
    return dict(root=root, state=state, report=report,
                entries={entry["task"]["id"]: entry for entry in state["tasks"]},
                rows={row["task_id"]: row for row in report["tasks"]})


def _transition(before, after):
    if before == after and before in {"passed", "failed"}:
        return "unchanged_" + before
    if (before, after) in {("failed", "passed"), ("passed", "failed")}:
        return before + "_to_" + after
    return "not_compared"


def _observation(row, kind, index, root):
    result = row.get("result") or {}
    criterion = next((item for item in result.get("criteria", [])
                      if (item["kind"], item["index"]) == (kind, index)), None)
    if criterion is None:
        return dict(status="not_run", observation="No observation for this current attempt.", evidence=[])
    artifacts = {item["id"]: item for item in result.get("artifacts", [])}
    return dict(status=criterion["status"], observation=criterion["observation"],
                evidence=[dict(run_path=str(root), **artifacts[aid]) for aid in criterion["evidence_ids"]])


def _issue(code, reason, next_step, fields=None):
    result = dict(code=code, reason=reason, next_step=next_step)
    if fields:
        result["fields"] = fields
    return result


def _pair(task_id, before, after, changed_limits):
    left, right = before["rows"].get(task_id), after["rows"].get(task_id)
    a, b = before["entries"].get(task_id), after["entries"].get(task_id)
    row = dict(task_id=task_id, comparable=False, change="not_compared", issues=[],
               baseline_status=left["status"] if left else "missing",
               candidate_status=right["status"] if right else "missing",
               criteria=[], requirements=[])
    present = b or a
    row.update(persona_id=present["task"]["persona_id"], binding=present["binding"], goal=present["task"]["goal"])
    row["attempts"] = dict(baseline=a["attempts"] if a else None,
                           candidate=b["attempts"] if b else None)
    if a is None or b is None:
        row["issues"].append(_issue(
            "unpaired_task", "This journey is present in only one run.",
            "Keep missing work visible. Execute the same reviewed journey in a separate authorized run; do not copy old receipts."))
        return row
    if changed_limits:
        row["issues"].append(_issue(
            "different_limits", "The runs use different execution limits.",
            "Treat these results as different test scopes; compare runs with the same reviewed limits.", changed_limits))
    changed = ["task." + key for key in JOURNEY_FIELDS if a["task"].get(key) != b["task"].get(key)]
    changed += ["binding." + key for key in ("persona_id", "revision", "profile_sha256", "prd_sha256")
                if a["binding"].get(key) != b["binding"].get(key)]
    if changed:
        row["issues"].append(_issue(
            "different_journey", "The persona version, declared journey or requirement mapping differs.",
            "Keep this as additional coverage. Replay the same persona version, journey and criteria for a paired comparison.", changed))
    if not left["current_binding_valid"] or not right["current_binding_valid"]:
        row["issues"].append(_issue(
            "historical_not_current", "A superseded persona result is historical, not current comparison evidence.",
            "Review current persona bindings. Do not count historical passes or bypass revalidation."))
    for label, item in (("baseline", left), ("candidate", right)):
        if item["resource_quarantined"]:
            row["issues"].append(_issue(
                label + "_resource_quarantined", "An uncertain write still quarantines this run's resource.",
                "Inspect the actual worker and effects, then use the existing retry or settlement flow; comparison authorizes no execution."))
        if item["status"] not in {"passed", "failed"}:
            if item["status"] in {"running", "inconclusive"}:
                action = "Collect or inspect the existing attempt and actual effects before retry or settlement; do not launch a duplicate worker."
            else:
                action = "Complete the missing journey through the existing claim and record flow within its grants and limits."
            row["issues"].append(_issue(label + "_not_observed",
                                       "This run has no current passed or failed task observation.", action))
    if row["issues"]:
        return row
    row["comparable"] = True
    row["change"] = _transition(left["status"], right["status"])
    row["journey_sha256"] = digest({key: a["task"].get(key) for key in JOURNEY_FIELDS})
    for kind in ("success", "recovery"):
        for index, description in enumerate(a["task"][kind + "_criteria"]):
            first = _observation(left, kind, index, before["root"])
            second = _observation(right, kind, index, after["root"])
            row["criteria"].append(dict(kind=kind, index=index, description=description,
                                        baseline=first, candidate=second,
                                        change=_transition(first["status"], second["status"])))
    right_requirements = {item["requirement_id"]: item for item in right["requirement_results"]}
    for first in left["requirement_results"]:
        second = right_requirements[first["requirement_id"]]
        row["requirements"].append(dict(
            requirement_id=first["requirement_id"], baseline=first, candidate=second,
            change=_transition(first["status"], second["status"])))
    return row


def compare(library, baseline_path, candidate_path):
    """Hold existing run locks in a stable order; never expire, retry or save."""
    baseline, candidate = _existing_run(baseline_path), _existing_run(candidate_path)
    if baseline == candidate:
        raise EngineError("comparison_same_run", "Choose two distinct runs; a run cannot be its own replay.")
    with ExitStack() as stack:
        for root in sorted((baseline, candidate)):
            stack.enter_context(Store(root))
        before, after = _snapshot(baseline, library), _snapshot(candidate, library)
        origin = after["state"].get("replay_origin")
        if origin and (origin["baseline_run"] != str(baseline)
                       or origin["baseline_state_sha256"] != digest(before["state"])):
            raise EngineError("replay_baseline_mismatch",
                              "This candidate was prepared from a different baseline snapshot.",
                              next_step="Use the recorded original baseline. If that run changed, preserve both histories and review the recorded comparison scope; do not rewrite provenance.")
        if before["state"]["product_id"] != after["state"]["product_id"]:
            raise EngineError("comparison_product_mismatch", "Different products cannot form a paired journey comparison.")
        changed_limits = [key for key in LIMIT_FIELDS if before["state"][key] != after["state"][key]]
        tasks = [_pair(task_id, before, after, changed_limits)
                 for task_id in sorted(before["entries"].keys() | after["entries"].keys())]
        counts = {key: 0 for key in (*TRANSITIONS, "not_compared")}
        criteria_counts = dict(counts)
        for task in tasks:
            counts[task["change"]] += 1
            for criterion in task["criteria"]:
                criteria_counts[criterion["change"]] += 1
        counts.update(total=len(tasks), compared=sum(task["comparable"] for task in tasks))
        complete = bool(tasks) and counts["not_compared"] == 0 and criteria_counts["not_compared"] == 0
        source_runs = {}
        for label, snapshot in (("baseline", before), ("candidate", after)):
            source_runs[label] = dict(
                run_path=str(snapshot["root"]), state_sha256=digest(snapshot["state"]),
                build=snapshot["state"]["build"], counts=snapshot["report"]["counts"],
                coverage_summary=snapshot["report"]["coverage_summary"],
                limits={key: snapshot["state"][key] for key in LIMIT_FIELDS},
                **({"replay_origin": snapshot["state"]["replay_origin"]}
                   if "replay_origin" in snapshot["state"] else {}),
            )
        return dict(
            schema_version="ux-persona-swarm-comparison.v1", product_id=before["state"]["product_id"],
            result="complete" if complete else "partial" if counts["compared"] else "blocked",
            comparison_complete=complete, comparison_basis="same_declared_journey_current_recorded_evidence",
            build_changed=before["state"]["build"]["sha256"] != after["state"]["build"]["sha256"],
            source_runs=source_runs, counts=counts, criterion_counts=criteria_counts, tasks=tasks,
            criterion_comparison_scope="comparable_task_pairs_only",
            product_ready=False, measured_ux_improvement=False, limitations=LIMITATIONS,
        )


def _display(value):
    value = re.sub(r"[\x00-\x1f\x7f]", " ", str(value)).strip()
    return value if len(value) <= 240 else value[:237] + "..."


def render_text(result):
    """A usable default report; JSON remains available for host integrations."""
    counts = result["counts"]
    sources = result["source_runs"]
    lines = [
        "Remorsearch: paired journey comparison",
        "Result: " + result["result"] + " (recorded evidence only)",
        "Builds: " + _display(sources["baseline"]["build"]["id"]) + " -> "
        + _display(sources["candidate"]["build"]["id"]),
        f"Journeys compared: {counts['compared']}/{counts['total']}; not compared: {counts['not_compared']}",
        f"Failed -> passed: {counts['failed_to_passed']}; passed -> failed: {counts['passed_to_failed']}",
        "Unobserved criteria within matched journeys: " + str(result["criterion_counts"]["not_compared"]),
    ]
    if not result["build_changed"]:
        lines.append("The build bytes are identical; this is a repeated-run comparison, not evidence of a code fix.")
    coverage = sources["candidate"]["coverage_summary"]["requirement_assignments"]
    lines.append("Candidate PRD assignments: " + ", ".join(f"{key}={coverage[key]}" for key in
                 ("passed", "failed", "incomplete", "excluded", "unassessed")))
    for task in result["tasks"]:
        lines.extend(["", _display(task["goal"]) + " [" + _display(task["persona_id"])
                      + " v" + str(task["binding"]["revision"]) + ", " + _display(task["task_id"])
                      + "]: " + task["baseline_status"] + " -> " + task["candidate_status"]
                      + (" [not compared]" if not task["comparable"] else "")])
        for issue in task["issues"]:
            lines.append("  " + issue["reason"])
            if issue.get("fields"):
                lines.append("  Changed fields: " + ", ".join(issue["fields"]))
            lines.append("  Next: " + issue["next_step"])
        for criterion in task["criteria"]:
            if criterion["change"] not in {"unchanged_passed", "unchanged_failed"}:
                lines.append("  " + _display(criterion["description"]) + ": "
                             + criterion["baseline"]["status"] + " -> " + criterion["candidate"]["status"])
    lines.extend(["", "These are recorded outcomes for matching declared journeys. Confirm the same starting data, device and input conditions before treating a replay as equivalent.",
                  "Evidence integrity does not prove source authenticity, actual execution or user benefit. Product readiness and measured UX improvement remain unverified."])
    return "\n".join(lines)
