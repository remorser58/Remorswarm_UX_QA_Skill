"""Offline regressions for final-judgment binding errors in the live cohort."""
import copy
import json
import unittest

import _paths
from uxpersonas.model_router import ModelRoute, RoutedScaleProvider
from uxpersonas.swarm_providers import ProviderSpec


def decision():
    return {"kind": "final", "judgment": {"reason": "Not exercised.",
        "criteria": [{"kind": kind, "index": index, "status": "not_run",
            "observation": "Not exercised.", "observation_ids": []}
            for kind, index in [("success", 0), ("success", 1), ("recovery", 0)]]}}


class BindingTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, invalid, reason, response=None):
        case = self
        class Router:
            routes = [ModelRoute("local-gateway", "local-gateway/free-model")]
            def __init__(self): self.events = []; self.projected = None
            def complete(self, messages, **options):
                self.projected = json.loads(messages[1]["content"])
                checked = options["quality_check"](json.dumps(invalid))
                if response is not None:
                    case.assertIs(checked, True)
                else:
                    case.assertIn(reason, checked)
                value = copy.deepcopy(response) if response is not None else decision()
                case.assertIs(options["quality_check"](json.dumps(value)), True)
                receipt = {"call_id": options["call_id"], "response_id": "offline-reply",
                    "provider": "local-gateway", "requested_model": self.routes[0].model,
                    "served_model": "free-model", "input_tokens": 12,
                    "output_tokens": 6, "provider_cost_microusd": None,
                    "cost_basis": "provider_cost_not_reported", "status": "success"}
                self.events.append(receipt)
                return json.dumps(value), receipt
            def report(self): return {"events": self.events}
        router = Router()
        provider = RoutedScaleProvider(ProviderSpec(key="local-router", protocol="callback", model="free"), router)
        request = {"operation_id": "offline-op", "context_id": "offline-context",
            "request_sha256": "a" * 64, "payload": {"phase": "model", "observations": [],
            "task": {"success_criteria": ["A", "B"], "recovery_criteria": ["Recovery"]}}}
        before = copy.deepcopy(request)
        reply = await provider.call(request)
        self.assertEqual(request, before)
        self.assertEqual(reply["result"], response if response is not None else decision())
        self.assertEqual(router.projected["final_criterion_bindings"], [
            {"kind": "success", "index": 0, "requirement": "A"},
            {"kind": "success", "index": 1, "requirement": "B"},
            {"kind": "recovery", "index": 0, "requirement": "Recovery"}])

    async def test_recovery_index_is_independent_not_global(self):
        invalid = decision(); invalid["judgment"]["criteria"][-1]["index"] = 2
        await self.exercise(invalid, "criterion_binding_expected")

    async def test_string_index_is_not_silently_coerced(self):
        invalid = decision(); invalid["judgment"]["criteria"][0]["index"] = "0"
        await self.exercise(invalid, "criterion_binding_expected")

    async def test_duplicate_and_missing_bindings_remain_rejections(self):
        invalid = decision(); invalid["judgment"]["criteria"][-1] = copy.deepcopy(invalid["judgment"]["criteria"][0])
        await self.exercise(invalid, "criterion_binding_duplicate")
        missing = decision(); missing["judgment"]["criteria"].pop()
        await self.exercise(missing, "criterion_bindings_missing")

    async def test_invalid_status_is_not_rewritten_as_passed(self):
        invalid = decision(); invalid["judgment"]["criteria"][0]["status"] = "pass"
        await self.exercise(invalid, "criterion_status_requires")

    async def test_recovery_not_applicable_is_valid_but_success_not_applicable_is_not(self):
        valid = decision()
        valid["judgment"]["criteria"][-1]["status"] = "not_applicable"
        await self.exercise(valid, "criterion_binding_expected", response=valid)
        invalid = decision()
        invalid["judgment"]["criteria"][0]["status"] = "not_applicable"
        await self.exercise(invalid, "not_applicable_only_for_conditional_recovery")

    async def test_failed_judgment_cannot_describe_an_unexecuted_condition(self):
        invalid = decision()
        invalid["judgment"]["criteria"][0].update(
            status="failed", observation="목록을 열지 않아 확인하지 못했다.",
            observation_ids=["obs-1"])
        await self.exercise(invalid, "failed_without_executed_evidence")

    async def test_label_wording_drift_is_not_a_functional_failure_when_action_succeeds(self):
        invalid = decision()
        invalid["judgment"]["criteria"][0].update(
            status="failed", observation="문구는 요구와 다르지만 눌러서 3/3단계로 이동했다.",
            observation_ids=["obs-1"])
        await self.exercise(invalid, "failed_without_executed_evidence")
