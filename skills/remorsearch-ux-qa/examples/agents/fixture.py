"""Authored, offline decisions and generated PNGs. No actual model or browser."""
from __future__ import annotations
import asyncio
import copy
from pathlib import Path
import sys

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL))
from uxpersonas.agent_run import CallbackHost, Tool, Limits, execute
from uxpersonas.library import Library
from uxpersonas import swarm
from uxresearch.canonical import byte_digest, canonical
from uxresearch.storage import atomic, safe_path
from ergoqa.png import encode, new_image

TOOLS = [
    Tool("inspect", "Observe the owned note fixture", {}),
    Tool("enter", "Enter an owned synthetic note", {"value": "string"}, "owned_fixture_write"),
    Tool("reject", "Try the persona's invalid-input path", {}, "owned_fixture_write"),
    Tool("save", "Save the corrected owned note", {}, "owned_fixture_write"),
]


def build(root):
    root = safe_path(root)
    root.mkdir(mode=0o700)
    atomic(root / "PRD.md", b"Keep a draft after rejection. Save corrected input.\n")
    atomic(root / "build.txt", b"Owned offline control and deliberate retention defect.\n")
    profiles, tasks = [], []
    for name, behavior in (("CAUTIOUS", "Inspect the ordinary correction path."),
                           ("RETURN", "Resume the alternative error path after interruption.")):
        profiles.append(dict(persona_id="PER-" + name, label=behavior,
            goals=["Recover an entered note"], behaviors=[behavior], contexts=["Owned synthetic fixture"],
            assumptions=["Authored test hypothesis"], unknowns=["Real user behavior"],
            requirement_ids=["R-STATE"], claim_ids=[]))
        tasks.append(dict(id="T-" + name, persona_id="PER-" + name,
            requirement_ids=["R-STATE"], goal="Keep a draft after rejection and save corrected input.",
            starting_state="Empty isolated note", actions=["Choose next action from own observations"],
            decisions=[behavior], success_criteria=["Keep a draft after rejection."],
            recovery_criteria=["Save corrected input."], data_namespace=name, resource_id=name,
            side_effects="owned_fixture_write", stop_conditions=["Outside owned fixture"],
            requirement_coverage=[dict(requirement_id="R-STATE", obligations=[
                dict(id="O-RETAIN", description="Keep the draft", criterion_refs=[dict(kind="success", index=0)], exclusion_reason=None),
                dict(id="O-RECOVER", description="Save corrected input", criterion_refs=[dict(kind="recovery", index=0)], exclusion_reason=None)])]))
    with Library(root / "library") as library:
        library.import_profiles(dict(schema_version="ux-persona-library-input.v1", product_id="agent-fixture",
            mode="prd_hypothesis", context=dict(prd_path=str(root / "PRD.md"),
                prd_sha256=byte_digest(read(root / "PRD.md")),
                requirements=[dict(id="R-STATE", source_anchor="PRD", excerpt="Keep a draft after rejection. Save corrected input.")]),
            personas=profiles))
        swarm.create_plan(library, root / "run", dict(schema_version=swarm.SCHEMA,
            product_id="agent-fixture", build=dict(id="fixture-build", artifact_path=str(root / "build.txt"),
                sha256=byte_digest(read(root / "build.txt"))), max_parallel=2, lease_seconds=300,
            max_attempts=2, tasks=tasks))
    return root


def read(path):
    from uxresearch.storage import read_bytes
    return read_bytes(path)


def judgment(observations):
    rejected = next(o for o in observations if o["facts"]["stage"] == "rejected")
    saved = next(o for o in observations if o["facts"]["stage"] == "saved")
    return dict(reason="Owned fixture observations; authored decisions, no real user evidence.",
        criteria=[
            dict(kind="success", index=0, status="passed" if rejected["facts"]["retained"] else "failed",
                 observation="The rejection checkpoint retained the draft." if rejected["facts"]["retained"] else "The rejection checkpoint lost the draft.",
                 observation_ids=[rejected["id"]]),
            dict(kind="recovery", index=0, status="passed", observation="Corrected input was saved.",
                 observation_ids=[saved["id"]])])


class FixtureHost(CallbackHost):
    def __init__(self, parallel=True):
        self.states, self.calls, self.model_inputs = {}, [], []
        super().__init__(info=dict(name="owned-offline-fixture", mode="fixture",
            model="authored-decision-function", adapter_sha256=byte_digest(read(Path(__file__))),
            isolated_contexts=True, parallel_safe=parallel), call=self.respond)

    async def respond(self, kind, request):
        await asyncio.sleep(0.01)
        self.calls.append((kind, request["operation_id"], request["context_id"]))
        result = await self.result(kind, request)
        return dict(operation_id=request["operation_id"], context_id=request["context_id"],
                    request_sha256=request["request_sha256"], trace_id="fixture-" + request["operation_id"],
                    result=result)

    async def result(self, kind, request):
        payload = request["payload"]
        state = self.states.setdefault(request["context_id"], dict(stage="empty", note="", saved="", retained=None))
        if kind == "close":
            return dict(stopped=True)
        if kind == "review":
            return judgment(payload["observations"])
        if kind == "model":
            self.model_inputs.append(copy.deepcopy(payload))
            observations = payload["observations"]
            if not observations:
                tool, args = "inspect", {}
            else:
                stage = observations[-1]["facts"]["stage"]
                if stage == "empty":
                    tool, args = "enter", {"value": "Owned draft"}
                elif stage == "entered":
                    tool, args = "reject", {}
                elif stage == "rejected":
                    tool, args = "enter", {"value": "Owned corrected note"}
                elif stage == "corrected":
                    tool, args = "save", {}
                else:
                    return dict(kind="final", judgment=judgment(observations))
            return dict(kind="tool", tool=tool, arguments=args, decision="Inspect and advance this persona's own note.")
        if kind != "tool":
            raise ValueError("Unsupported fixture call")
        tool = payload["name"]
        if tool == "enter":
            state["note"] = payload["arguments"]["value"]
            state["stage"] = "corrected" if state["stage"] == "rejected" else "entered"
        elif tool == "reject":
            state["retained"] = payload["task"]["persona_id"] != "PER-RETURN"
            if not state["retained"]:
                state["note"] = ""
            state["stage"] = "rejected"
        elif tool == "save":
            state["saved"], state["stage"] = state["note"], "saved"
        raw = encode(new_image(2, 2))
        path = safe_path(Path(payload["evidence_path"]) / (request["operation_id"] + ".png"))
        atomic(path, raw)
        checks = []
        if state["stage"] == "rejected":
            checks = [dict(kind="success", index=0, status="passed" if state["retained"] else "failed")]
        if state["stage"] == "saved":
            checks = [dict(kind="recovery", index=0, status="passed")]
        return dict(text="Observed owned fixture state: " + state["stage"], facts=copy.deepcopy(state),
                    captures=[dict(path=path.name, sha256=byte_digest(raw))], checks=checks)


async def run(root, parallel=True):
    host = FixtureHost(parallel=parallel)
    with Library(root / "library") as library:
        report = await execute(library, root / "run", host, TOOLS, reviewed=True)
        calls = len(host.calls)
        again = await execute(library, root / "run", host, TOOLS, reviewed=True)
        assert len(host.calls) == calls
        assert report == again
    assert report["counts"]["passed"] == 1 and report["counts"]["failed"] == 1
    assert report["agent_execution"]["actual_model_execution"] is False
    assert len(report["agent_execution"]["first_judgments"]) == 2
    atomic(root / "diagnostic.json", canonical(dict(
        fixture_passed=True, actual_model_execution=False, actual_browser_execution=False,
        generated_pngs_not_captures=True, readback_without_redispatch=True, report=report)))
    return report


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--serial", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(run(build(args.out), not args.serial))
    print(json.dumps(dict(counts=result["counts"], execution=result["agent_execution"]), indent=2))
