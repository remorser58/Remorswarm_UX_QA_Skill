"""Prepare a new build's journeys from verified prior evidence; never execute them."""
from __future__ import annotations

import copy
from contextlib import ExitStack
from pathlib import Path
import re
import shlex
import sys

from uxresearch.canonical import EngineError, byte_digest, canonical, digest
from uxresearch.storage import Store, atomic, read_bytes, read_json, safe_path
from . import swarm
from .comparison import JOURNEY_FIELDS, LIMIT_FIELDS, _existing_run, _snapshot

ORIGIN_SCHEMA = "ux-persona-replay-origin.v1"
INDEX_SCHEMA = "ux-persona-replay-index.v1"
LIMITATIONS = swarm.LIMITATIONS + [
    "Replay prepares pending work only; it does not execute journeys or copy previous observations.",
    "Starting-state equivalence and isolation are host attestations, not independently verified facts or permission grants.",
    "Generated resource identifiers preserve sharing groups but do not create, reset or inspect actual fixtures.",
    "Duplicate prevention covers this library's replay command, not manually authored plans or remote side effects.",
]


def _fail(code, reason, next_step="Preserve existing runs and correct the replay input."):
    raise EngineError(code, reason, next_step=next_step)


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        _fail("replay_integrity", "Replay provenance contains an invalid digest.")
    return value


def _key(baseline, candidate_sha256):
    # Names, isolation aliases, mutable state and destination cannot reset a budget.
    return digest(dict(baseline_run=str(baseline), candidate_sha256=candidate_sha256))


def _journey_digest(state):
    return digest(dict(
        product_id=state["product_id"],
        limits={key: state[key] for key in LIMIT_FIELDS},
        tasks=[dict(id=entry["task"]["id"], binding=entry["binding"],
                    journey={key: entry["task"].get(key) for key in JOURNEY_FIELDS})
               for entry in sorted(state["tasks"], key=lambda e: e["task"]["id"])],
    ))


def validate_origin(state):
    """Lineage is audit provenance, never an execution authority or a result."""
    origin = state["replay_origin"]
    fields = {"schema_version", "baseline_run", "baseline_state_sha256", "baseline_build",
              "candidate_sha256", "journey_sha256", "replay_key", "isolation"}
    if not isinstance(origin, dict) or set(origin) != fields or origin["schema_version"] != ORIGIN_SCHEMA:
        _fail("replay_integrity", "Replay provenance has an unsupported shape.")
    for key in ("baseline_state_sha256", "candidate_sha256", "journey_sha256", "replay_key"):
        _hash(origin[key])
    baseline = Path(swarm.text(origin["baseline_run"]))
    if not baseline.is_absolute() or ".." in baseline.parts or str(baseline) != origin["baseline_run"]:
        _fail("replay_integrity", "Replay baseline identity is not an absolute normalized path.")
    build = origin["baseline_build"]
    if not isinstance(build, dict) or set(build) != {"id", "sha256"}:
        _fail("replay_integrity", "Replay baseline build is invalid.")
    swarm.ident(build["id"])
    _hash(build["sha256"])
    isolation = origin["isolation"]
    if (not isinstance(isolation, dict)
            or set(isolation) != {"id", "starting_state_confirmed", "isolated_resources_confirmed", "verification"}
            or isolation["starting_state_confirmed"] is not True
            or isolation["isolated_resources_confirmed"] is not True
            or isolation["verification"] != "host_attestation_only"):
        _fail("replay_integrity", "Replay host attestations are missing or invalid.")
    swarm.ident(isolation["id"])
    if swarm.clean(isolation["id"]) != isolation["id"]:
        _fail("replay_integrity", "Use a synthetic isolation identifier.")
    if (origin["candidate_sha256"] != state["build"]["sha256"]
            or build["sha256"] == state["build"]["sha256"] or build["id"] == state["build"]["id"]
            or origin["journey_sha256"] != _journey_digest(state)
            or origin["replay_key"] != _key(baseline, state["build"]["sha256"])):
        _fail("replay_integrity", "Replay provenance does not match the bound build and journeys.")
    return origin


def _index(library):
    path = safe_path(library.root / "replay-index.json")
    if not path.exists():
        return {"schema_version": INDEX_SCHEMA, "entries": {}}
    envelope = read_json(path, private=True)
    state = envelope.get("state") if isinstance(envelope, dict) else None
    if (not isinstance(state, dict) or set(state) != {"schema_version", "entries"}
            or state["schema_version"] != INDEX_SCHEMA or digest(state) != envelope.get("sha256")
            or not isinstance(state["entries"], dict) or len(state["entries"]) > 4096):
        _fail("replay_integrity", "The replay reservation index is invalid; nothing was reset.")
    for key, entry in state["entries"].items():
        _hash(key)
        if not isinstance(entry, dict) or set(entry) != {"baseline_run", "candidate_sha256", "run_path", "intent_sha256"}:
            _fail("replay_integrity", "The replay reservation entry is invalid.")
        _hash(entry["candidate_sha256"])
        _hash(entry["intent_sha256"])
        for field in ("baseline_run", "run_path"):
            path = Path(swarm.text(entry[field]))
            if not path.is_absolute() or ".." in path.parts or str(path) != entry[field]:
                _fail("replay_integrity", "The replay reservation path is invalid.")
        if key != _key(entry["baseline_run"], entry["candidate_sha256"]):
            _fail("replay_integrity", "The replay reservation identity is invalid.")
    return state


def _save_index(library, state):
    raw = canonical(dict(state=state, sha256=digest(state)))
    if len(raw) > 16 * 1024 * 1024:
        _fail("replay_index_full", "The replay reservation index reached its storage bound.")
    atomic(library.root / "replay-index.json", raw)


def _identifier(kind, isolation_id, key, original):
    # Letters-only digest avoids phone/account-like identifiers in privacy checks.
    suffix = digest([isolation_id, key, original])[:32].translate(
        str.maketrans("0123456789abcdef", "abcdefghijklmnop"))
    return "replay-" + kind + "-" + suffix


def _result(library, root, state, status):
    args = ["--library", str(library.root), "--run", str(root)]
    steps = [
        dict(action="claim", argv=["claim", *args, "--worker", "replay-worker"],
             note="Verify the assigned owned fixtures first. Save the returned claim privately and perform the journey."),
        dict(action="receipt-starter", argv=["receipt-starter", *args, "--claim", "private-claim.json"],
             note="This draft is not a result. Fill it with fresh actual observations and artifacts."),
        dict(action="record", argv=["record", *args, "--input", "private-receipt.json"],
             note="Repeat claim and record for every available journey; preserve lease and retry rules."),
        dict(action="report", argv=["report", *args], note="Inspect current observations and remaining work."),
        dict(action="compare", argv=["compare", *args, "--baseline", state["replay_origin"]["baseline_run"]],
             note="Compare only after new observations exist; no real-user effect is inferred."),
    ]
    counts = {name: sum(e["status"] == name for e in state["tasks"])
              for name in ("pending", "running", "passed", "failed", "blocked", "inconclusive", "skipped")}
    return dict(
        schema_version="ux-persona-replay.v1", status=status, run_path=str(root),
        task_count=len(state["tasks"]), persona_count=len({e["task"]["persona_id"] for e in state["tasks"]}),
        counts=counts, replay_origin=copy.deepcopy(state["replay_origin"]),
        assignments=[dict(task_id=e["task"]["id"], data_namespace=e["task"]["data_namespace"],
                          resource_id=e["task"]["resource_id"]) for e in state["tasks"]],
        next_steps=steps, product_ready=False, measured_ux_improvement=False, limitations=LIMITATIONS,
    )


def prepare(library, baseline_path, run_path, *, build_id, artifact_path, isolation_id,
            confirm_starting_state=False, confirm_isolation=False):
    """Reserve and create one pending replay, or return its existing unchanged run."""
    library._state()  # Require the same exclusive Library context used by all CLI writers.
    if library.root.stat().st_mode & 0o077:
        _fail("unsafe_mode", "Replay requires a private existing persona library directory.")
    if confirm_starting_state is not True or confirm_isolation is not True:
        _fail("replay_confirmation", "Confirm equivalent starting conditions and owned fixture isolation.",
              "Review the starting data, device/input conditions and isolation, then supply both confirmation flags. These do not grant permissions.")
    swarm.ident(isolation_id)
    if swarm.clean(isolation_id) != isolation_id:
        _fail("replay_confirmation", "Use a synthetic isolation identifier.")
    artifact = safe_path(artifact_path)
    build = swarm._build(dict(id=build_id, artifact_path=str(artifact), sha256=byte_digest(read_bytes(artifact))))
    baseline, root = _existing_run(baseline_path), safe_path(run_path)
    if (root.is_relative_to(baseline) or baseline.is_relative_to(root)
            or root.is_relative_to(library.root) or library.root.is_relative_to(root)):
        _fail("replay_path", "Use a separate run directory outside the baseline and persona library.")
    if not root.parent.is_dir():
        _fail("replay_path", "The new run's parent directory must already exist.")
    key = _key(baseline, build["sha256"])
    index = _index(library)
    reservation = index["entries"].get(key)
    if reservation and reservation["run_path"] != str(root):
        _fail("replay_duplicate", "This baseline and candidate build already have a reserved replay destination.",
              "Use the original replay destination and its existing claim, retry or settlement flow; do not create a new budget.")
    if root.exists() and not reservation:
        _fail("run_exists", "Run folder already exists; no existing folder may be reused.")
    existing = root.exists()
    if existing and (not root.is_dir() or not all((root / name).is_file() for name in ("engine.lock", "swarm-state.json"))):
        _fail("replay_incomplete", "The reserved run was only partially created; its files were preserved.",
              "Inspect the original destination. Do not delete it, overwrite evidence or create a second replay to bypass uncertain state.")
    roots = [baseline] + ([root] if existing else [])
    # Preflight every existing file before Store can create or chmod a lock.
    for path in roots:
        _existing_run(path)
        if path.stat().st_mode & 0o077:
            _fail("unsafe_mode", "Replay requires private existing run directories.")
    with ExitStack() as locks:
        for path in sorted(roots):
            locks.enter_context(Store(path))
        before = _snapshot(baseline, library)
        old = before["state"]
        if build["id"] == old["build"]["id"] or build["sha256"] == old["build"]["sha256"]:
            _fail("replay_build_unchanged", "Replay requires both a different build ID and different artifact bytes.")
        for entry in old["tasks"]:
            row = before["rows"][entry["task"]["id"]]
            if (not row["current_binding_valid"] or entry["status"] not in {"passed", "failed"}
                    or not isinstance(entry.get("receipt"), dict)
                    or entry["receipt"]["outcome"] != entry["status"]
                    or row["resource_quarantined"] or "settlement" in entry):
                _fail("replay_baseline_incomplete", "Every baseline journey must have a current validated passed or failed observation.",
                      "Finish or inspect the original run using its existing limits. Replay cannot resolve active, missing or uncertain execution.")
        tasks = []
        original_ids = {e["task"][field] for e in old["tasks"] for field in ("data_namespace", "resource_id")}
        for entry in old["tasks"]:
            task = copy.deepcopy(entry["task"])
            task["data_namespace"] = _identifier("n", isolation_id, key, task["data_namespace"])
            task["resource_id"] = _identifier("r", isolation_id, key, task["resource_id"])
            if task["data_namespace"] in original_ids or task["resource_id"] in original_ids:
                _fail("replay_isolation", "Generated isolation identifiers overlap the baseline.")
            tasks.append(task)
        spec = dict(schema_version=swarm.SCHEMA, product_id=old["product_id"], build=build, tasks=tasks,
                    **{field: old[field] for field in LIMIT_FIELDS})
        state = swarm._prepare_plan(library, spec)
        if any(new["binding"] != previous["binding"] for new, previous in zip(state["tasks"], old["tasks"])):
            _fail("stale_persona", "The replay must retain the exact validated persona versions.")
        state["replay_origin"] = dict(
            schema_version=ORIGIN_SCHEMA, baseline_run=str(baseline), baseline_state_sha256=digest(old),
            baseline_build={field: old["build"][field] for field in ("id", "sha256")},
            candidate_sha256=build["sha256"], journey_sha256=_journey_digest(state), replay_key=key,
            isolation=dict(id=isolation_id, starting_state_confirmed=True, isolated_resources_confirmed=True,
                           verification="host_attestation_only"),
        )
        validate_origin(state)
        swarm._state_bytes(state)  # Check the final envelope limit before consuming a reservation.
        intent = dict(baseline_run=str(baseline), candidate_sha256=build["sha256"], run_path=str(root),
                      intent_sha256=digest(dict(spec=spec, origin=state["replay_origin"])))
        if reservation and reservation != intent:
            _fail("replay_conflict", "The reserved replay's immutable preparation inputs have changed.")
        if existing:
            current = _snapshot(root, library)["state"]  # Never expire a lease on an idempotent replay call.
            if (current.get("replay_origin") != state["replay_origin"]
                    or current["build"] != state["build"]
                    or [e["task"] for e in current["tasks"]] != tasks
                    or [e["binding"] for e in current["tasks"]] != [e["binding"] for e in state["tasks"]]
                    or any(current[field] != state[field] for field in LIMIT_FIELDS)):
                _fail("replay_conflict", "Existing replay does not match its original preparation; nothing was reset.")
            return _result(library, root, current, "existing")
        if not reservation:
            if len(index["entries"]) >= 4096:
                _fail("replay_index_full", "The replay reservation index reached its entry bound.")
            index["entries"][key] = intent
            _save_index(library, index)
        # Reservation first: an interrupted creation cannot mint a second attempt budget.
        # Only an absent destination can resume; partial directories are never overwritten.
        swarm._create_plan(root, state)
        return _result(library, root, state, "prepared")


def render_text(result):
    origin = result["replay_origin"]
    lines = [
        "Remorsearch: next-build journey replay",
        "Status: " + result["status"] + "; no journey was executed by this command.",
        f"Journeys: {result['task_count']}; persistent persona versions reused: {result['persona_count']}",
        "Current states: " + ", ".join(f"{name}={count}" for name, count in result["counts"].items() if count),
        "Run: " + result["run_path"], "Baseline: " + origin["baseline_run"],
        "Verify these owned fixture assignments before claim:",
    ]
    for assignment in result["assignments"]:
        lines.append("  " + assignment["task_id"] + ": " + assignment["data_namespace"] + " / " + assignment["resource_id"])
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    launcher = scripts / "remorsearch.py"
    prefix = ([sys.executable, str(launcher), "personas"] if launcher.is_file()
              else [sys.executable, str(scripts / "ux_personas.py")])
    lines.extend(["", "Next steps (save claim/draft JSON privately; filenames below are placeholders):"])
    for step in result["next_steps"]:
        lines.extend(["  " + shlex.join(prefix + step["argv"]), "  " + step["note"]])
    lines.extend(["", *LIMITATIONS])
    return "\n".join(lines)
