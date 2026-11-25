"""Host-facing live diagnostic: actual Pro decisions and owned Chromium tools.

Two stored PRD hypotheses, a normal control and a known defect. This example
proves the transport/execution path, not live research, product readiness or
real-user improvement. It never calls the offline FixtureHost.
"""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import time

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL))
from uxpersonas.agent_run import Limits, Tool, doctor, execute
from uxpersonas.aside_chatgpt import AsideChatHost, OwnedProChat
from uxpersonas.library import Library
from uxpersonas import swarm
from uxresearch.canonical import byte_digest, canonical
from uxresearch.storage import atomic, read_bytes, read_json, safe_path

TOOLS = [
    Tool("inspect", "Read the current note, saved note and feedback in your isolated owned page.", {}),
    Tool("enter", "Replace the note with your chosen synthetic text: start with 'Owned ' and use 1-80 ASCII letters, digits, spaces or .,!?'-. No personal data.",
         {"value": "string"}, "owned_fixture_write"),
    Tool("reject", "Exercise the assigned invalid-input rejection path and observe whether the entered draft remains.", {}, "owned_fixture_write"),
    Tool("save", "Save the current corrected note and inspect the exact saved value.", {}, "owned_fixture_write"),
]
LIMITS = Limits(parallel=2, turns=12, call_seconds=180, task_seconds=1500, close_seconds=15)


def build(root):
    root = safe_path(root)
    root.mkdir(mode=0o700)
    spec = importlib.util.spec_from_file_location("owned_live_page_source", SKILL / "examples/journey/browser_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = root / "owned-page.html"
    atomic(source, module.PAGE.encode())
    prd = b"Keep the entered draft when invalid input is rejected. Save the exact corrected note after recovery.\n"
    atomic(root / "PRD.md", prd)
    profiles, tasks = [], []
    identities = [
        ("CAUTIOUS", "Cautious first-time note writer",
         "Inspect unfamiliar state before committing. Prefer reversible steps. Seek reassurance that a rejected action has not lost work.",
         "No prior experience with this synthetic note tool."),
        ("RETURN", "Returning note writer after interruption",
         "Check what survived interruption. Avoid unnecessary retyping. If work disappears, describe the loss and rebuild only enough to verify recovery.",
         "Returning to a task after attention was interrupted."),
    ]
    for name, label, behavior, context in identities:
        profiles.append(dict(persona_id="PER-" + name, label=label,
            goals=["Keep entered work and recover safely from rejection"],
            behaviors=[behavior], contexts=[context, "Owned synthetic local note page"],
            assumptions=["Authored PRD hypothesis; no claim of observed human behavior"],
            unknowns=["Real user behavior and usefulness in production"],
            requirement_ids=["R-STATE"], claim_ids=[]))
        tasks.append(dict(id="T-" + name, persona_id="PER-" + name,
            requirement_ids=["R-STATE"], goal="Assess draft retention after rejection and exact saving after correction.",
            starting_state="Fresh isolated owned note page. No shared browser state.",
            actions=["Choose allowed actions and synthetic wording from your own observations."],
            decisions=[behavior], success_criteria=["Keep the entered draft when invalid input is rejected."],
            recovery_criteria=["After correction, save the exact corrected note."],
            data_namespace=name, resource_id=name, side_effects="owned_fixture_write",
            stop_conditions=["Unapproved scope, real data, uncertain effects or exhausted budget"],
            requirement_coverage=[dict(requirement_id="R-STATE", obligations=[
                dict(id="O-RETAIN", description="Retain the draft on rejection",
                     criterion_refs=[dict(kind="success", index=0)], exclusion_reason=None),
                dict(id="O-RECOVER", description="Save exact corrected content",
                     criterion_refs=[dict(kind="recovery", index=0)], exclusion_reason=None)])]))
    with Library(root / "library") as library:
        library.import_profiles(dict(schema_version="ux-persona-library-input.v1",
            product_id="aside-live-owned-note", mode="prd_hypothesis",
            context=dict(prd_path=str(root / "PRD.md"), prd_sha256=byte_digest(prd),
                requirements=[dict(id="R-STATE", source_anchor="PRD", excerpt=prd.decode().strip())]),
            personas=profiles))
        swarm.create_plan(library, root / "run", dict(schema_version=swarm.SCHEMA,
            product_id="aside-live-owned-note",
            build=dict(id="owned-browser-live-build", artifact_path=str(source), sha256=byte_digest(read_bytes(source))),
            max_parallel=2, lease_seconds=1800, max_attempts=1, tasks=tasks))
    return source


class OwnedNoteTools:
    """Only tool I/O; model decisions and reviews are never authored here."""
    def __init__(self, source, *, node, playwright, browsers, journal):
        self.source = safe_path(source)
        self.source_hash = byte_digest(read_bytes(source))
        self.node, self.playwright, self.browsers = [str(safe_path(p)) for p in (node, playwright, browsers)]
        self.journal = Path(journal)
        self.journal.mkdir(mode=0o700)
        self.driver = Path(__file__).with_name("browser_tools.mjs")
        self.processes, self.locks, self.states = {}, {}, {}
        self.serial = 0
        self.runtime_receipts = []
        self.events = []

    async def exchange(self, context, kind, payload):
        async with self.locks.setdefault(context, asyncio.Lock()):
            self.serial += 1
            ident = self.serial
            process = self.processes[context]
            event = dict(id=ident, context_id=context, kind=kind, status="intent", started_at=time.time())
            self.events.append(event)
            atomic(self.journal / "events.json", canonical(self.events))
            try:
                process.stdin.write(json.dumps(dict(id=ident, kind=kind, payload=payload)).encode() + b"\n")
                await process.stdin.drain()
                raw = await process.stdout.readline()
                if not raw or len(raw) > 65536:
                    raise RuntimeError("Owned browser transport ended or exceeded its bound")
                response = json.loads(raw)
                if response.get("id") != ident or set(response) != {"id", "result"}:
                    raise RuntimeError("Owned browser response mismatch; no retry")
                event.update(status="done", ended_at=time.time(), result=copy.deepcopy(response["result"]))
                return response["result"]
            except BaseException:
                event.update(status="uncertain", ended_at=time.time())
                raise
            finally:
                atomic(self.journal / "events.json", canonical(self.events))

    async def tool(self, request):
        context, payload = request["context_id"], request["payload"]
        if context not in self.processes:
            self.processes[context] = await asyncio.create_subprocess_exec(
                self.node, str(self.driver), cwd=payload["evidence_path"],
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin", "REMORSEARCH_AGENT_PLAYWRIGHT": self.playwright,
                     "PLAYWRIGHT_BROWSERS_PATH": self.browsers})
            self.runtime_receipts.append(await self.exchange(context, "start",
                dict(source=str(self.source), sha256=self.source_hash)))
        previous = self.states.get(context, dict(note="", saved="No note saved", feedback="Ready"))
        result = await self.exchange(context, "act", dict(name=payload["name"],
            value=payload["arguments"].get("value"),
            target="#reject-broken" if payload["task"]["persona_id"] == "PER-RETURN" else "#reject-control"))
        if result["source_sha256"] != self.source_hash:
            raise RuntimeError("Owned build binding changed")
        facts = {k: result[k] for k in ("note", "saved", "feedback")}
        facts["action"] = payload["name"]
        checks = []
        if payload["name"] == "reject":
            facts["before_note"] = previous["note"]
            facts["retained"] = bool(previous["note"]) and facts["note"] == previous["note"]
            # Empty rejection is unobserved retention, not an invented failure.
            if previous["note"]:
                checks.append(dict(kind="success", index=0, status="passed" if facts["retained"] else "failed"))
        elif payload["name"] == "save" and previous["note"]:
            checks.append(dict(kind="recovery", index=0,
                               status="passed" if facts["saved"] == previous["note"] else "failed"))
        self.states[context] = copy.deepcopy(facts)
        return dict(text="Actual owned Chromium observation: " + facts["feedback"],
                    facts=facts, captures=[result["capture"]], checks=checks)

    async def close(self, request):
        context = request["context_id"]
        if context not in self.processes:
            return {"stopped": True}
        process = self.processes[context]
        try:
            response = await self.exchange(context, "close", {})
            process.stdin.close()
            await asyncio.wait_for(process.wait(), 3)
            return {"stopped": response == {"stopped": True} and process.returncode == 0}
        except Exception:
            if process.returncode is None:
                process.terminate()
            return {"stopped": False}


def source_manifest():
    files = [Path(__file__), Path(__file__).with_name("browser_tools.mjs"),
             Path(__file__).with_name("run_aside_live.py"),
             SKILL / "uxpersonas/aside_cli.py", SKILL / "uxpersonas/aside_chatgpt.py",
             SKILL / "uxpersonas/agent_run.py", SKILL / "drivers/web/journey_bridge.mjs",
             SKILL / "examples/journey/browser_fixture.py"]
    return {str(p.relative_to(SKILL)): byte_digest(read_bytes(p)) for p in files}


async def run_owned(clients, root, *, node, playwright, browsers, probes=None):
    if len(clients) != 2:
        raise RuntimeError("This validation needs exactly two fresh owned contexts")
    if not doctor()["runtime_ready"]:
        raise RuntimeError("Pinned optional LangGraph runtime unavailable")
    started = time.monotonic()
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    source = build(root)
    manifest = source_manifest()
    atomic(root / "source-manifest.json", canonical(manifest))
    chats = [OwnedProChat(cli, evidence=root / ("model-" + str(i + 1))) for i, cli in enumerate(clients)]
    try:
        for i, chat in enumerate(chats):
            if probes:
                await chat.adopt_reviewed_probe(probes[i])
            else:
                await chat.initialize()
        if not probes:
            await asyncio.gather(*(c.transport_probe() for c in chats))
    except BaseException as exc:
        stopped = await asyncio.gather(*(c.close() for c in chats), return_exceptions=True)
        atomic(root / "preflight-failure.json", canonical(dict(
            actual_model_execution=False, actual_browser_execution=False,
            error_type=type(exc).__name__, error_reason=str(exc)[:300],
            cleanup=[r if isinstance(r, dict) else {"stopped": False} for r in stopped])))
        raise
    tool_host = OwnedNoteTools(source, node=node, playwright=playwright, browsers=browsers, journal=root / "browser")
    host = AsideChatHost(chats, tool_call=tool_host.tool, tool_close=tool_host.close,
                         evidence=root / "host", adapter_sha256=byte_digest(canonical(manifest)))
    atomic(root / "run-start.json", canonical(dict(wall_time=time.time(), limits=vars(LIMITS),
        actual_model_execution=False, source_manifest=manifest, probes_are_persona_execution=False)))
    print(json.dumps({"live_started": True, "output": str(root), "limits": vars(LIMITS)}), flush=True)
    with Library(root / "library") as library:
        report = await execute(library, root / "run", host, TOOLS, limits=LIMITS, reviewed=True)
        dispatches = len(host.events)
        again = await execute(library, root / "run", host, TOOLS, limits=LIMITS, reviewed=True)
        readback = again == report and len(host.events) == dispatches
        stored = library.list("aside-live-owned-note")
    intervals = [[dict(start=s, end=e, kind=k, operation_id=o) for s, e, k, o in c.model_intervals] for c in chats]
    overlaps = [dict(left=a["operation_id"], right=b["operation_id"],
                     seconds=min(a["end"], b["end"]) - max(a["start"], b["start"]))
                for a in intervals[0] for b in intervals[1]
                if a["kind"] == b["kind"] == "model" and max(a["start"], b["start"]) < min(a["end"], b["end"])]
    usage_after = resource.getrusage(resource.RUSAGE_SELF)
    diagnostic = dict(schema="remorsearch-aside-live.v1",
        report=report, runtime_receipts=tool_host.runtime_receipts, stored_personas=stored,
        actual_browser_execution=bool(tool_host.runtime_receipts),
        actual_model_execution=report["agent_execution"]["actual_model_execution"],
        decision_source="actual_owned_chatgpt_pro_responses", authored_model_decisions=0,
        transport_probe_calls=len(probes or []) + sum(k == "probe" for c in chats for _, _, k, _ in c.model_intervals),
        model_intervals=intervals,
        model_send_to_reply_overlap=overlaps, readback_without_redispatch=readback,
        source_manifest=manifest, sources_unchanged=source_manifest() == manifest,
        limits=vars(LIMITS), elapsed_seconds=time.monotonic() - started,
        mac_coordinator_maxrss_bytes=usage_after.ru_maxrss,
        coordinator_user_seconds=usage_after.ru_utime - usage_before.ru_utime,
        coordinator_system_seconds=usage_after.ru_stime - usage_before.ru_stime,
        measurement_scope="MacBook coordinator process only; excludes remote Pro and aggregate Chromium memory",
        actual_user_evidence=False, product_ready=False, observed_model="Pro",
        provider_screenshots=False, product_png_pixels_sent_to_model=False,
        provider_model_version=None, daemon_multiagent_setting_changed=False,
        completion=(report["agent_execution"]["two_persona_model_tool_execution"]
                    and report["counts"]["passed"] == 1 and report["counts"]["failed"] == 1
                    and readback and source_manifest() == manifest))
    atomic(root / "diagnostic.json", canonical(diagnostic))
    return {k: v for k, v in diagnostic.items() if k not in {"stored_personas", "model_intervals", "report", "source_manifest"}} | {
        "counts": report["counts"], "execution": report["agent_execution"]}


async def run_existing(clients, repository):
    """Continue exactly the two sample-tested live objects held by the parent."""
    config = read_json(repository / ".ux-loop/aside-live-config.json", private=True)
    return await run_owned(clients, repository / ".ux-loop/aside-live-model-20261112-01",
        node=config["node"], playwright=config["playwright"], browsers=config["browsers"],
        probes=["remorsearch-owned-probe-A-20261112-7ec2", "remorsearch-owned-probe-B-20261112-9bd4"])
