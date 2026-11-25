"""Offline completion guards: saved evidence projections and authored queue callbacks.

No browser, model, provider network call, or actual persona execution occurs.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import _paths
from ergoqa.png import encode, new_image
from uxpersonas import scale_run, swarm
from uxpersonas.agent_run import CallbackHost, Tool
from uxpersonas.library import Library
from uxpersonas.scale_entry import engine_manifest, per_task_turn_limit
from uxpersonas.swarm_providers import CallbackProvider, ProviderSpec, ProviderUncertain
from uxpersonas.swarm_queue import Queue, SCHEMA
from uxresearch.canonical import byte_digest, digest
from uxresearch.storage import atomic, read_bytes, read_json


RID = "R-SEARCH"
TASK = {"requirement_ids": [RID]}
TOOLS = {"observe", "click", "scroll", "type", "upload"}


def search_rows():
    return [
        {
            "id": "obs-5",
            "text": "Uploaded owned-search-ready.zip; 12 rows ready.",
            "facts": {
                "last_action": "upload",
                "uploaded_fixture": "owned-search-ready.zip",
                "fixture_uploads": ["owned-search-ready.zip"],
                "controls": [dict(selector="body>button:nth-of-type(1)", label="Open list (12)", visible=True, disabled=False, tag="button")],
            },
            "checks": [],
        },
        {
            "id": "obs-6",
            "text": "Opened list with 12 synthetic rows and enabled search input.",
            "facts": {
                "last_action": "click",
                "fixture_uploads": ["owned-search-ready.zip"],
                "controls": [dict(selector="body>input:nth-of-type(1)", tag="input", type="search", visible=True, disabled=False)],
                "list_rows": [{"key": f"synthetic_item_{i:02d}"} for i in range(12)],
            },
            "checks": [],
        },
        {
            "id": "obs-7",
            "text": "Filtered list to exact match synthetic_item_05.",
            "facts": {
                "last_action": "type",
                "fixture_uploads": ["owned-search-ready.zip"],
                "controls": [dict(selector="body>input:nth-of-type(1)", tag="input", type="search", visible=True, disabled=False)],
                "list_rows": [{"key": "synthetic_item_05"}],
            },
            "checks": [{"kind": "success", "index": 0, "status": "passed"}],
        },
    ]


def resolver(requirement_id, task, observations, tools):
    latest = observations[-1]
    facts = latest.get("facts", {})
    controls = facts.get("controls", [])
    if requirement_id != RID:
        return None, "This criterion has no reviewed continuation rule; retain the admitted verdict."
    search_field = next(
        (c for c in controls if c.get("tag") == "input" and c.get("type") == "search" and c.get("visible") and not c.get("disabled")),
        None,
    )
    if search_field and "type" in tools:
        return dict(tool="type", selector=search_field["selector"], value="synthetic_item_05",
                    reason="Observed visible search input."), None
    hidden = next((c for c in controls if c.get("visible") is False), None)
    if hidden and "scroll" in tools:
        return dict(tool="scroll", delta=400, target_label=hidden.get("label", ""),
                    reason="Required control is outside the visible area."), None
    return None, "Required control is unavailable."


def unresolved():
    return {"criteria": [{"kind": "success", "index": 0, "status": "not_run"}]}


def review(state, receipt=None, **kwargs):
    return scale_run._completion_review(TASK, state, receipt or unresolved(), TOOLS,
        kwargs.get("turn_limit", 64), kwargs.get("remaining_seconds", 1000), 30,
        completion_resolver=kwargs.get("completion_resolver", resolver))


class CompletionGuardTests(unittest.TestCase):
    def test_per_task_turn_limit_honors_bounded_request_under_approved_ceiling(self):
        for requested, expected in ((None, 80), (64, 64), (80, 80), (120, 80), (0, 80), (True, 80)):
            task = {"requirement_ids": [RID]}
            if requested is not None:
                task["turn_limit"] = requested
            for approved in (1, 12, 64, 80):
                self.assertEqual(per_task_turn_limit(task, approved), min(approved, expected))

    def test_actual_unfiltered_search_is_actionable_but_failed_and_recovery_are_not(self):
        state = {"turn": 6, "observations": search_rows()[:2]}
        original = copy.deepcopy(state)
        result = review(state)
        self.assertEqual(result["action"], "continue")
        self.assertEqual(result["next_step"]["tool"], "type")
        self.assertEqual(result["next_step"]["value"], "synthetic_item_05")
        self.assertEqual(result["observation_id"], "obs-6")
        self.assertEqual(result["model_turn"], 7)
        self.assertEqual(result["remaining_model_turns"], 57)
        for status in ("passed", "failed"):
            result = review(state, {"criteria": [{"kind": "success", "index": 0, "status": status}]})
            self.assertEqual(result["action"], "accept_final")
        result = review(state, {"criteria": [{"kind": "recovery", "index": 0, "status": "not_run"}]})
        self.assertEqual(result["action"], "accept_final")
        self.assertEqual(state, original)

    def test_same_page_new_observation_id_cannot_reset_continuation_cap(self):
        state = {"turn": 6, "observations": search_rows()[:2]}
        first = review(state)
        state["completion_attempts"] = [first]
        state["turn"] += 1
        state["observations"][-1]["id"] = "obs-new-same-page"
        result = review(state)
        self.assertEqual(result["action"], "accept_final")
        self.assertIn("No actionable page change", result["blockers"][0]["reason"])
        state["observations"][-1]["facts"]["controls"][0]["title"] = "New observed field state"
        second = review(state)
        self.assertEqual(second["action"], "continue")
        state["completion_attempts"].append(second)
        state["observations"][-1]["facts"]["controls"][0]["title"] = "Another state"
        result = review(state)
        self.assertEqual(result["action"], "accept_final")
        self.assertIn("two bounded", result["blockers"][0]["reason"])

    def test_actual_budget_and_rejected_action_preserve_explicit_blockers(self):
        state = {"turn": 61, "observations": search_rows()[:2]}
        result = review(state)
        self.assertEqual(result["action"], "accept_final")
        self.assertEqual(result["effective_turn_limit"], 64)
        self.assertEqual(result["remaining_model_turns"], 2)
        state["turn"] = 6
        result = review(state, remaining_seconds=4)
        self.assertEqual(result["action"], "accept_final")
        self.assertEqual(result["remaining_task_seconds"], 4)
        state["observations"][-1]["facts"]["rejected_action"] = {
            "name": "click", "click_dispatched": False, "reason": "target_not_allowed_or_visible"}
        result = review(state)
        self.assertEqual(result["action"], "accept_final")
        self.assertIn("rejected before dispatch", result["blockers"][0]["reason"])

    def test_hidden_result_gets_one_safe_scroll_but_not_after_two_no_movement_attempts(self):
        rows = search_rows()[:1]
        rows[0]["facts"]["controls"] = [{
            "selector": "body>button:nth-of-type(1)", "label": "Open list (12)",
            "visible": False, "disabled": False, "tag": "button"}]
        result = review({"turn": 6, "observations": rows})
        self.assertEqual(result["next_step"]["tool"], "scroll")
        for index in range(2):
            row = copy.deepcopy(rows[-1])
            row["id"] = "blocked-" + str(index)
            row["facts"].update(last_action="scroll", scroll_attempt={
                "scope": "page", "modal_selector": None, "requested_delta": 400,
                "before": {"selector": "html", "scroll_top": 0},
                "after": {"selector": "html", "scroll_top": 0},
                "moved": False, "outcome": "scroll_area_has_no_usable_height"})
            rows.append(row)
        result = review({"turn": 8, "observations": rows})
        self.assertEqual(result["action"], "accept_final")
        self.assertIn("Two admitted scroll", result["blockers"][0]["reason"])

    def test_default_without_host_resolver_does_not_guess_product_specific_steps(self):
        result = review({"turn": 6, "observations": search_rows()[:2]}, completion_resolver=None)
        self.assertEqual(result["action"], "accept_final")
        self.assertIn("no reviewed continuation rule", result["blockers"][0]["reason"])


class CompletionQueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        atomic(self.root / "PRD.md", b"Inspect ordered rows and exact search filtering.\n")
        atomic(self.root / "build.txt", b"Owned offline callback; no actual browser or model.\n")
        self.tools = [
            Tool("observe", "Inspect the authored fixture.", {}, "owned_fixture_write"),
            Tool("upload", "Upload the authored fixture.", {"selector": "string", "file": "string"}, "owned_fixture_write"),
            Tool("click", "Open the authored fixture list.", {"selector": "string", "label": "string"}, "owned_fixture_write"),
            Tool("type", "Filter the authored fixture list.", {"selector": "string", "value": "string"}, "owned_fixture_write"),
        ]
        persona = dict(persona_id="PER-SEARCH", label="Authored search behavior",
            goals=["Inspect a synthetic list"], behaviors=["Follow observed controls"],
            contexts=["Owned offline fixture"], assumptions=["Authored test hypothesis"],
            unknowns=["Real user behavior"], requirement_ids=[RID], claim_ids=[])
        task = dict(id="T-SEARCH", persona_id="PER-SEARCH", requirement_ids=[RID],
            goal="Inspect ordered rows and actual exact search filtering.",
            starting_state="Fresh owned fixture", actions=["Use current controls"],
            decisions=["Inspect own observations"], success_criteria=["Ordered rows and exact filtering"],
            recovery_criteria=["If input fails, inspect the available recovery control."], data_namespace="SEARCH", resource_id="SEARCH",
            side_effects="owned_fixture_write", stop_conditions=["Outside owned fixture"],
            requirement_coverage=[dict(requirement_id=RID, obligations=[
                dict(id="O-SEARCH", description="Inspect actual exact filtering",
                     criterion_refs=[dict(kind="success", index=0), dict(kind="recovery", index=0)], exclusion_reason=None)])])
        with Library(self.root / "library") as library:
            library.import_profiles(dict(schema_version="ux-persona-library-input.v1",
                product_id="owned-fixture", mode="prd_hypothesis",
                context=dict(prd_path=str(self.root / "PRD.md"),
                    prd_sha256=byte_digest(read_bytes(self.root / "PRD.md")),
                    requirements=[dict(id=RID, source_anchor="PRD", excerpt="Inspect ordered rows and exact search filtering.")]),
                personas=[persona]))
            swarm.create_plan(library, self.root / "run", dict(schema_version=swarm.SCHEMA,
                product_id="owned-fixture", build=dict(id="fixture-build",
                    artifact_path=str(self.root / "build.txt"), sha256=byte_digest(read_bytes(self.root / "build.txt"))),
                max_parallel=1, lease_seconds=300, max_attempts=1, tasks=[task]))
        self.contexts, self.calls, self.requests = {}, [], []
        self.uncertain_continuation = False
        self.repeat_final = False
        info = dict(name="completion-offline-fixture", mode="fixture", model="authored-callback",
                    adapter_sha256=byte_digest(read_bytes(Path(__file__))), isolated_contexts=True, parallel_safe=True)
        self.host = CallbackHost(info=info, call=self.tool_call)
        self.host.can_resume = lambda context_id, observations: context_id in self.contexts
        provider_spec = ProviderSpec(key="fixture", protocol="fixture", model="authored",
                                    requests_per_minute=10000, concurrency=1)
        self.provider = CallbackProvider(provider_spec, self.model_call, mode="fixture",
                                         adapter_sha256="a" * 64)
        old = read_json(self.root / "run/swarm-state.json", private=True)["payload"]
        plan = dict(schema_version=SCHEMA, mode="fixture", library_path=str(self.root / "library"),
            product_id="owned-fixture", target="owned-fixture", goal=task["goal"], build=old["build"],
            limits=dict(parallel=1, turns=12, call_seconds=5, task_seconds=60,
                        lease_seconds=30, budget_microusd=0, max_model_calls=13),
            providers={"fixture": dict(spec=provider_spec.validate(), mode="fixture",
                adapter_sha256=self.provider.adapter_sha256, credential_scope="fixture")},
            tools=[tool.spec() for tool in self.tools], tool_host=info,
            tool_provenance="authored_fixture", engine_manifest=engine_manifest(),
            jobs=[dict(id="job-search", provider="fixture", task=old["tasks"][0]["task"],
                       binding=old["tasks"][0]["binding"])])
        self.queue = Queue.create(self.root / "scale", plan)

    def reply(self, request, result, model=False):
        result = dict(operation_id=request["operation_id"], context_id=request["context_id"],
            request_sha256=request["request_sha256"], trace_id="fixture-" + request["operation_id"],
            result=result)
        if model:
            result["usage"] = dict(input_tokens=10, output_tokens=10, provider="fixture", model="authored",
                                   provider_cost_microusd=0, cost_basis="fixture_no_charge")
        return result

    def judgment(self, payload):
        passed = any(row["facts"].get("last_action") == "type" for row in payload["observations"])
        ids = [row["id"] for row in payload["observations"]] if passed else []
        return dict(reason="Authored offline decision; no browser/model execution.", criteria=[
            dict(kind="success", index=0, status="passed" if passed else "not_run",
                 observation="Observed exact filtering." if passed else "Stopped before exact search.",
                 observation_ids=ids),
            dict(kind="recovery", index=0, status="not_applicable",
                 observation="No input failure triggered conditional recovery.", observation_ids=[])])

    async def model_call(self, request):
        self.calls.append(("model", request["operation_id"]))
        self.requests.append(copy.deepcopy(request))
        payload = request["payload"]
        observations = payload["observations"]
        if payload["phase"] == "review":
            decision = dict(kind="final", judgment=self.judgment(payload))
        elif payload.get("completion_feedback") and not self.repeat_final:
            if self.uncertain_continuation:
                raise ProviderUncertain("authored_unknown_delivery")
            step = payload["completion_feedback"]["next_step"]
            decision = dict(kind="tool", tool="type",
                arguments={key: step[key] for key in ("selector", "value")},
                decision="Use the current observed search field.")
        elif not observations:
            decision = dict(kind="tool", tool="observe", arguments={}, decision="Inspect the owned input.")
        elif len(observations) == 1:
            decision = dict(kind="tool", tool="upload",
                arguments={"selector": "body>input:nth-of-type(1)", "file": "owned-search-ready.zip"},
                decision="Import the required owned fixture.")
        elif len(observations) == 2:
            decision = dict(kind="tool", tool="click",
                arguments={"selector": "body>button:nth-of-type(1)", "label": "Open list (12)"},
                decision="Open the owned twelve-row list.")
        else:
            decision = dict(kind="final", judgment=self.judgment(payload))
        return self.reply(request, decision, model=True)

    async def tool_call(self, kind, request):
        self.calls.append((kind, request["operation_id"]))
        rows = self.contexts.setdefault(request["context_id"], [])
        if kind == "close":
            return self.reply(request, {"stopped": True})
        name = request["payload"]["name"]
        if name == "observe":
            row = dict(text="Owned initial input.", facts=dict(last_action="observe",
                available_fixtures=["owned-search-ready.zip"],
                file_inputs=[dict(selector="body>input:nth-of-type(1)", disabled=False)],
                controls=[]), checks=[])
        else:
            row = copy.deepcopy(search_rows()[{"upload": 0, "click": 1, "type": 2}[name]])
            row["facts"]["available_fixtures"] = ["owned-search-ready.zip"]
        rows.append(copy.deepcopy(row))
        raw = encode(new_image(2, 2))
        path = Path(request["payload"]["evidence_path"]) / (request["operation_id"] + ".png")
        atomic(path, raw)
        return self.reply(request, dict(text=row["text"], facts=row["facts"], checks=row["checks"],
            captures=[dict(path=path.name, sha256=byte_digest(raw))]))

    async def run_queue(self):
        return await scale_run.execute_scale(self.queue.root, {"fixture": self.provider},
            self.host, reviewed=True, max_idle_seconds=0, completion_resolver=resolver)

    async def test_committed_early_final_continues_on_new_operation_and_preserves_original(self):
        report = await self.run_queue()
        self.assertEqual(report["counts"]["complete"], 1, report)
        result = report["tasks"][0]["result"]
        self.assertEqual(result["ux_outcome"], "passed")
        self.assertEqual(len(result["completion_attempts"]), 1)
        attempt = result["completion_attempts"][0]
        with self.queue._db() as db:
            finals = [json.loads(row["reply"]) for row in db.execute(
                "SELECT reply FROM operations WHERE kind='model' AND state='done' ORDER BY started")]
        finals = [reply["result"] for reply in finals if reply["result"]["kind"] == "final"]
        self.assertEqual(len(finals), 2)
        self.assertEqual(finals[0]["judgment"]["criteria"][0]["status"], "not_run")
        self.assertEqual(attempt["judgment_sha256"], digest(finals[0]["judgment"]))
        self.assertEqual(finals[-1]["judgment"]["criteria"][0]["status"], "passed")
        ids = [operation_id for _, operation_id in self.calls]
        self.assertEqual(len(ids), len(set(ids)))
        feedback_requests = [r for r in self.requests if r["payload"].get("completion_feedback")]
        self.assertEqual(len(feedback_requests), 1)
        self.assertEqual(result["effective_turn_limit"], 12)
        calls = len(self.calls)
        self.assertEqual(report, await self.run_queue())
        self.assertEqual(len(self.calls), calls)

    async def test_repeated_final_without_action_is_terminal_not_run_with_no_loop(self):
        self.repeat_final = True
        report = await self.run_queue()
        self.assertEqual(report["counts"]["complete"], 1, report)
        result = report["tasks"][0]["result"]
        self.assertEqual(result["ux_outcome"], "inconclusive")
        self.assertEqual(len(result["completion_attempts"]), 1)
        self.assertIn("No actionable page change", result["completion_guard"]["blockers"][0]["reason"])
        self.assertFalse(any(row["facts"].get("last_action") == "type"
                             for rows in self.contexts.values() for row in rows))

    async def test_uncertain_new_continuation_stops_and_is_never_resent(self):
        self.uncertain_continuation = True
        report = await self.run_queue()
        self.assertEqual(report["counts"]["uncertain"], 1, report)
        self.assertEqual(report["counts"]["complete"], 0)
        calls = len(self.calls)
        await self.run_queue()
        self.assertEqual(len(self.calls), calls)
        uncertain = [row for row in report["operations"] if row["state"] == "uncertain"]
        self.assertEqual(len(uncertain), 1)
        self.assertFalse(any(row["facts"].get("last_action") == "type"
                             for rows in self.contexts.values() for row in rows))


if __name__ == "__main__":
    unittest.main()
