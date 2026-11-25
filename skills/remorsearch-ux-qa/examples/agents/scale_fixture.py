"""Staged authored simulation of the shipped queue, never actual model/browser QA."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
from pathlib import Path
import resource
import sys
import time

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL))
from uxresearch.canonical import byte_digest, canonical, digest
from uxresearch.storage import atomic, read_bytes, safe_path
from uxpersonas.agent_run import CallbackHost, Tool
from uxpersonas.library import Library
from uxpersonas.scale_entry import ScaleLimits, prepare_scale_goal, preview, render_status
from uxpersonas.scale_run import execute_scale
from uxpersonas.swarm_providers import CallbackProvider, ProviderSpec
from uxpersonas.swarm_queue import Queue
from ergoqa.png import encode, new_image

TOOLS = [Tool("inspect", "Observe the owned authored draft rejection", {}),
         Tool("recover", "Correct and save the owned authored draft", {}, "owned_fixture_write")]


def judgment(observations):
    rejected = next(o for o in observations if o["facts"]["stage"] == "rejected")
    recovered = next(o for o in observations if o["facts"]["stage"] == "recovered")
    return dict(reason="Authored diagnostic only; no actual model, browser or participant.", criteria=[
        dict(kind="success", index=0, status="passed" if rejected["facts"]["retained"] else "failed",
             observation="The authored rejection retained the draft." if rejected["facts"]["retained"] else "The authored rejection lost the draft.",
             observation_ids=[rejected["id"]]),
        dict(kind="recovery", index=0, status="passed", observation="The authored corrected draft was saved.",
             observation_ids=[recovered["id"]])])


class Models:
    def __init__(self):
        self.active, self.peak, self.calls, self.contexts = {}, {}, [], {}

    async def respond(self, key, request):
        self.active[key] = self.active.get(key, 0) + 1
        self.peak[key] = max(self.peak.get(key, 0), self.active[key])
        try:
            await asyncio.sleep(0.003)
            payload = request["payload"]
            observations = payload["observations"]
            # Each normalized request contains only its own observations. An
            # individual trace is not an independent participant or survey vote.
            task = payload["task"]
            previous = self.contexts.setdefault(request["context_id"], task["persona_id"])
            assert previous == task["persona_id"]
            assert "peer_results" not in payload and "other_personas" not in payload
            self.calls.append(dict(operation=request["operation_id"], context=request["context_id"],
                persona=task["persona_id"], request_sha256=request["request_sha256"], provider=key))
            if payload.get("phase") == "review" or len(observations) >= 2:
                result = dict(kind="final", judgment=judgment(observations))
            else:
                result = dict(kind="tool", tool="inspect" if not observations else "recover", arguments={},
                              decision="Advance only this persona's authored draft scenario.")
            return dict(operation_id=request["operation_id"], context_id=request["context_id"],
                request_sha256=request["request_sha256"], trace_id="fixture-" + request["operation_id"],
                result=result, usage=dict(input_tokens=100, output_tokens=40))
        finally:
            self.active[key] -= 1


class OwnedFixture(CallbackHost):
    def __init__(self):
        self.states, self.calls = {}, []
        super().__init__(info=dict(name="scale-authored-fixture", mode="fixture", model="authored-fixture",
            adapter_sha256=byte_digest(read_bytes(Path(__file__))), isolated_contexts=True, parallel_safe=True),
            call=self.respond)

    def can_resume(self, context_id, observations):
        return context_id in self.states

    async def respond(self, kind, request):
        await asyncio.sleep(0.002)
        payload = request["payload"]
        self.calls.append((kind, request["operation_id"], request["context_id"]))
        if kind == "close":
            self.states.pop(request["context_id"], None)
            result = dict(stopped=True)
        elif kind == "tool":
            task = payload["task"]
            number = int(task["persona_id"].split("-")[-1])
            state = self.states.setdefault(request["context_id"], dict(owner=task["persona_id"]))
            assert state["owner"] == task["persona_id"]
            stage = "rejected" if payload["name"] == "inspect" else "recovered"
            state.update(stage=stage, retained=number % 4 != 0)
            raw = encode(new_image(2, 2))
            base = safe_path(payload["evidence_path"])
            path = safe_path(base / (request["operation_id"] + ".png"), base)
            if path.exists():
                assert read_bytes(path, private=True) == raw
            else:
                atomic(path, raw)
            checks = [dict(kind="success" if stage == "rejected" else "recovery", index=0,
                status="failed" if stage == "rejected" and not state["retained"] else "passed")]
            result = dict(text="Authored owned fixture state: " + stage,
                facts=dict(stage=stage, retained=state["retained"]),
                captures=[dict(path=path.name, sha256=byte_digest(raw))], checks=checks)
        else:
            raise ValueError("Only owned tool and close callbacks are supported.")
        return dict(operation_id=request["operation_id"], context_id=request["context_id"],
            request_sha256=request["request_sha256"], trace_id="fixture-" + request["operation_id"], result=result)


def prepare(root, count, parallel):
    root = safe_path(root)
    if root.exists():
        raise ValueError("Choose a new diagnostic output directory.")
    root.mkdir(parents=True, mode=0o700)
    atomic(root / "PRD.md", b"Keep a draft after rejection and save corrected input.\n")
    atomic(root / "build.txt", b"Authored simulation with a deliberate input loss every fourth persona.\n")
    context = dict(prd_path=str(root / "PRD.md"), prd_sha256=byte_digest(read_bytes(root / "PRD.md")),
        requirements=[dict(id="R-STATE", source_anchor="PRD", excerpt="Keep a draft after rejection and save corrected input.")])
    models, host = Models(), OwnedFixture()
    providers = {}
    for key in ("fixture-a", "fixture-b"):
        async def call(request, key=key):
            return await models.respond(key, request)
        providers[key] = CallbackProvider(ProviderSpec(key=key, protocol="fixture", model="authored-small-model",
            concurrency=max(1, parallel // 2), requests_per_minute=100000), call, mode="fixture",
            adapter_sha256=byte_digest(read_bytes(Path(__file__))))
    with Library(root / "library") as library:
        for offset in range(0, count, 32):
            profiles = [dict(persona_id=f"PER-SCALE-{i:04d}", label=f"Authored scenario {i}",
                goals=["Recover an owned draft"], behaviors=[f"Exercise the authored correction condition {i}."],
                contexts=["Isolated offline test data"], assumptions=["Authored diagnostic hypothesis"],
                unknowns=["Actual user behavior"], requirement_ids=["R-STATE"], claim_ids=[])
                for i in range(offset, min(count, offset + 32))]
            library.import_profiles(dict(schema_version="ux-persona-library-input.v1", product_id="scale-fixture",
                mode="prd_hypothesis", context=context, personas=profiles))
        before = byte_digest(read_bytes(library.root / "library.json", private=True))
        queue = prepare_scale_goal(library, root / "run", providers, host, TOOLS,
            product_id="scale-fixture", target="Owned offline diagnostic", goal="Keep an owned draft and recover from rejection.",
            build=dict(id="scale-fixture-build", artifact_path=str(root / "build.txt"), sha256=byte_digest(read_bytes(root / "build.txt"))),
            limits=ScaleLimits(parallel=parallel, turns=6, call_seconds=30, task_seconds=600,
                               max_model_calls=count * 7), reviewed=True)
        assert byte_digest(read_bytes(library.root / "library.json", private=True)) == before
    atomic(root / "preview.json", canonical(preview(queue)))
    return queue, providers, host, models, before


async def stage(root, count, parallel):
    started = time.monotonic()
    queue, providers, host, models, original_library_sha = prepare(root, count, parallel)
    report = await execute_scale(queue.root, providers, host, reviewed=True, max_idle_seconds=5)
    calls = len(models.calls) + len(host.calls)
    repeated = await execute_scale(queue.root, providers, host, reviewed=True, max_idle_seconds=0.1)
    assert len(models.calls) + len(host.calls) == calls, "readback must not dispatch"
    assert report["counts"] == repeated["counts"]
    assert report["counts"]["complete"] == count, report["counts"]
    assert not report["actual_model_execution"] and report["actual_model_calls"] == 0
    assert len({task["context_id"] for task in report["tasks"]}) == count
    assert all(t["result"]["operational_completed"] for t in report["tasks"])
    outcomes = {status: sum(t["result"]["ux_outcome"] == status for t in report["tasks"])
                for status in ("passed", "failed", "inconclusive")}
    assert outcomes["failed"] == (count + 3) // 4, outcomes
    assert outcomes["passed"] + outcomes["failed"] == count
    assert byte_digest(read_bytes(root / "library" / "library.json", private=True)) == original_library_sha
    assert all(models.peak[key] <= providers[key].spec.concurrency for key in providers)
    assert len({call["operation"] for call in models.calls}) == len(models.calls)
    assert queue.audit_events() == report["event_chain_head"]
    atomic(root / "report.json", canonical(report))
    atomic(root / "report.md", render_status(report).encode("utf-8"))
    elapsed = time.monotonic() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    summary = dict(sessions=count, concurrency=parallel, elapsed_seconds=round(elapsed, 3),
        process_peak_rss_bytes=rss if sys.platform == "darwin" else rss * 1024,
        counts=report["counts"], authored_model_calls=len(models.calls), tool_and_close_calls=len(host.calls),
        actual_model_calls=0, actual_browser_calls=0, mode="fixture", generated_pngs_not_browser_captures=True,
        outcomes=outcomes, peak_provider_callbacks=models.peak, unique_contexts=len(models.contexts),
        readback_added_calls=0, original_library_unchanged=True, budget=report["budget"],
        event_chain_head=report["event_chain_head"], plan_sha256=queue.plan_sha256,
        report_sha256=digest(report), product_ready=False, real_user_evidence=False)
    atomic(root / "stage.json", canonical(summary))
    return summary


async def main_async(args):
    root = safe_path(args.out)
    if root.exists():
        raise ValueError("The staged diagnostic requires a new output directory.")
    root.mkdir(parents=True, mode=0o700)
    stages = []
    for count in args.stages:
        summary = await stage(root / f"stage-{count}", count, min(args.parallel, count))
        stages.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        atomic(root / "stages.json", canonical(dict(mode="fixture", stages=stages,
            actual_model_calls=0, actual_browser_calls=0, product_ready=False)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--stages", type=lambda value: [int(x) for x in value.split(",")], default=[8, 32, 100, 300])
    parser.add_argument("--parallel", type=int, default=16)
    args = parser.parse_args()
    if len(set(args.stages)) != len(args.stages) or not all(1 <= n <= 1000 for n in args.stages) or not 1 <= args.parallel <= 64:
        parser.error("use unique stages from 1 to 1000 and concurrency from 1 to 64")
    asyncio.run(main_async(args))

