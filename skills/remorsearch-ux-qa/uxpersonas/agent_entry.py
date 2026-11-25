"""Goal entry for a host that already reviewed the target, PRD and saved personas."""
from __future__ import annotations
import copy
from pathlib import Path

from uxresearch.canonical import canonical, digest
from uxresearch.storage import atomic, read_json, safe_path
from . import swarm
from .agent_run import Limits, execute, fail


def prepare_goal(library, run_path, *, product_id, target, goal, build, limits=Limits(), reviewed=False):
    """Users provide target/goal; the host resolves Library/build and records review.

    PRD excerpts are exploratory success criteria, not a semantic completeness
    claim. The host must narrow unsuitable criteria before selecting this entry.
    """
    if reviewed is not True:
        fail("review_required", "Host must review the target, current PRD and task fit of the selected saved personas.")
    swarm.ident(product_id)
    swarm.text(target)
    swarm.text(goal)
    if swarm.clean(goal) != goal:
        fail("goal_privacy", "Use a goal without personal identifiers.")
    limits.validate()
    build = swarm._build(build)
    run = safe_path(run_path)
    # The Library context owns its single writer lock. Reserve the target/goal/
    # build once so a different path cannot silently reset an uncertain run.
    reservation = safe_path(library.root / "agent-goals.json")
    saved = {}
    if reservation.exists():
        envelope = read_json(reservation, private=True)
        if (envelope.get("schema_version") != "ux-agent-goals.v1"
                or digest(envelope.get("payload")) != envelope.get("sha256")):
            fail("goal_integrity", "Goal reservation integrity failed.")
        saved = envelope["payload"]
    key = digest(dict(product_id=product_id, target=target, goal=goal, build=build))
    if key in saved:
        record = saved[key]
        if record["run"] != str(run) or record["limits"] != vars(limits):
            fail("goal_reserved", "This goal/build already has a reserved execution; inspect it rather than reset its budget.")
        if (run / "swarm-state.json").exists():
            # Revalidate all current bindings; no historical pass becomes current.
            return swarm.report(library, run)
        if run.exists():
            fail("partial_goal", "The reserved run is incomplete; preserve it for inspection.")
        swarm.create_plan(library, run, record["plan"])
        return swarm.report(library, run)
    candidates = library.list(product_id)["personas"]
    eligible = [p for p in candidates if p["reusable"]]
    if len(eligible) < 2:
        fail("personas_required", "Two current saved personas for this product are required; the host must complete permitted persona preparation.")
    if len(eligible) > 8:
        fail("persona_scope_required", "Host must narrow the reviewed product scope to at most eight personas.")
    tasks = []
    for candidate in eligible:
        profile = library.get(product_id, candidate["persona_id"], candidate["revision"])
        requirements = [r for r in profile["context"]["requirements"]
                        if r["id"] in profile["profile"]["requirement_ids"]]
        if not 1 <= len(requirements) <= 16:
            fail("requirement_scope", "Host must review a bounded set of current persona requirements.")
        tid = "T-" + digest([key, candidate["persona_id"]])[:20]
        tasks.append(dict(id=tid, persona_id=candidate["persona_id"],
            requirement_ids=[r["id"] for r in requirements], goal=goal,
            starting_state="Fresh isolated owned context for the host-reviewed target.",
            actions=["Choose the next permitted action from actual observations; no authored action script."],
            decisions=copy.deepcopy(profile["profile"]["behaviors"]),
            success_criteria=[r["excerpt"] for r in requirements],
            recovery_criteria=["Exercise an applicable safe recovery and verify its outcome; mark not_run if not exercised."],
            data_namespace=tid, resource_id=tid, side_effects="owned_fixture_write",
            stop_conditions=["Stop on unapproved scope, real account data, deadline or uncertain effects."],
            requirement_coverage=[dict(requirement_id=r["id"], obligations=[
                dict(id="O-PRD", description=r["excerpt"], criterion_refs=[dict(kind="success", index=i)], exclusion_reason=None)])
                for i, r in enumerate(requirements)]))
    plan = dict(schema_version=swarm.SCHEMA, product_id=product_id, build=build,
                max_parallel=limits.parallel, lease_seconds=min(1800, max(30, limits.task_seconds + 30)),
                max_attempts=1, tasks=tasks)
    swarm._prepare_plan(library, plan)  # Validate everything before reserving.
    if run.exists():
        fail("run_exists", "Choose a new goal workspace; existing contents are preserved.")
    saved[key] = dict(run=str(run), limits=vars(limits), plan=plan)
    atomic(reservation, canonical(dict(schema_version="ux-agent-goals.v1", payload=saved, sha256=digest(saved))))
    swarm.create_plan(library, run, plan)
    return swarm.report(library, run)


async def run_goal(library, run_path, host, tools, *, product_id, target, goal, build,
                   limits=Limits(), reviewed=False, cancel=None):
    # Diagnose unavailable model transport before changing a library or claiming.
    from .agent_run import _host_info, _runtime
    _host_info(host)
    _runtime()
    prepare_goal(library, run_path, product_id=product_id, target=target, goal=goal,
                 build=build, limits=limits, reviewed=reviewed)
    return await execute(library, run_path, host, tools, limits=limits, reviewed=reviewed, cancel=cancel)
