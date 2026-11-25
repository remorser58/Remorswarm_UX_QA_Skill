"""Offline regressions for capture recovery, projection bounding, and router deadlines."""
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import _paths
from uxpersonas import swarm
from uxpersonas.model_router import ModelRoute, ModelRouter, RoutedScaleProvider
from uxpersonas.scale_browser_host import ScaleBrowserHost
from uxpersonas.swarm_providers import ProviderSpec, ProviderUncertain


class CaptureRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_predispatch_click_rejection_is_observed_not_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data = b"observed-rejection-capture"
            path = root / "browser-00002.png"
            path.write_bytes(data); path.chmod(0o600)
            observed = {"text": "Current page", "facts": {"last_action": "observe"},
                "captures": [{"path": path.name, "sha256": hashlib.sha256(data).hexdigest()}],
                "checks": []}
            host = object.__new__(ScaleBrowserHost)
            host.processes = {"context": object()}
            host._exchange = AsyncMock(side_effect=[
                RuntimeError("browser_action_failed:click_target_not_allowed_or_visible"), observed])
            request = {"operation_id": "rejected-click", "context_id": "context",
                "request_sha256": "b" * 64, "payload": {"name": "click",
                    "arguments": {"selector": "#hidden", "label": "Hidden"}, "evidence_path": str(root)}}
            reply = await host.call("tool", request)
            self.assertFalse(reply["result"]["facts"]["rejected_action"]["click_dispatched"])
            self.assertIn("Click NOT dispatched", reply["result"]["text"])
            self.assertEqual(host._exchange.await_args_list[1].args[2], {"name": "observe", "arguments": {}})
            self.assertEqual(host._exchange.await_count, 2)
            host._exchange = AsyncMock(side_effect=RuntimeError("browser_action_failed:cdp_timeout"))
            with self.assertRaisesRegex(RuntimeError, "cdp_timeout"):
                await host.call("tool", request)
            self.assertEqual(host._exchange.await_count, 1)

    async def test_scrub_text_without_corrupting_hash_and_still_reject_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data = b"capture-regression-20"
            sha = hashlib.sha256(data).hexdigest()
            self.assertNotEqual(swarm.clean(sha), sha, "Regression must exercise a card-like hash")
            picture = root / "browser-00001.png"
            picture.write_bytes(data)
            picture.chmod(0o600)
            result = {"text": "Account @synthetic.test", "facts": {},
                "captures": [{"path": picture.name, "sha256": sha}], "checks": []}
            host = object.__new__(ScaleBrowserHost)
            host.processes = {"context": object()}
            host._exchange = AsyncMock(side_effect=lambda *args: copy.deepcopy(result))
            request = {"operation_id": "operation", "context_id": "context",
                "request_sha256": "a" * 64, "payload": {"name": "observe",
                    "arguments": {}, "evidence_path": str(root)}}
            reply = await host.call("tool", request)
            self.assertEqual(reply["result"]["captures"][0]["sha256"], sha)
            self.assertNotIn("@synthetic.test", reply["result"]["text"])
            picture.write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "capture_integrity:digest"):
                await host.call("tool", request)


class ProjectionRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_request_contains_one_checkpoint_without_duplicate_history(self):
        class Router:
            routes = [ModelRoute("local-gateway", "local-gateway/free-model")]
            def __init__(self):
                self.inputs, self.events = [], []
            def complete(self, messages, **kwargs):
                self.inputs.append(copy.deepcopy(messages))
                event = {"call_id": kwargs["call_id"], "response_id": kwargs["call_id"],
                    "provider": "local-gateway", "requested_model": self.routes[0].model,
                    "served_model": "free-model", "input_tokens": 10,
                    "output_tokens": 3, "provider_cost_microusd": None,
                    "cost_basis": "provider_cost_not_reported"}
                self.events.append(event)
                return json.dumps({"kind": "tool", "tool": "observe",
                    "arguments": {}, "decision": "Observe only"}), event
            def report(self):
                return {"events": self.events}
        router = Router()
        provider = RoutedScaleProvider(ProviderSpec(key="route", protocol="callback", model="free"), router)
        payload = {"phase": "model", "observations": [
            {"id": "obs-1", "text": "Original evidence", "facts": {"controls": ["stale"], "text": "Original evidence"}},
            {"id": "obs-2", "text": "Current evidence", "facts": {"controls": ["current"], "text": "Current evidence"}}]}
        for index in range(2):
            await provider.call({"operation_id": "op-" + str(index), "context_id": "same-persona",
                "request_sha256": "a" * 64, "payload": payload})
        self.assertEqual(len(router.inputs[1]), 2)
        projected = json.loads(router.inputs[1][1]["content"])
        self.assertEqual(len(projected["observations"]), 2)
        self.assertNotIn("controls", projected["observations"][0]["facts"])
        self.assertEqual(projected["observations"][1]["facts"]["controls"], ["current"])
        self.assertEqual(payload["observations"][0]["facts"]["controls"], ["stale"])
        self.assertEqual(provider.conversations, {})


class ProtocolRecoveryTests(unittest.TestCase):
    def test_live_limits_fit_the_existing_queue_ceiling(self):
        path = Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa/scripts/live_scale_browser.py"
        spec = importlib.util.spec_from_file_location("live_scale_recovery_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for count in (4, 12, 16):
            limits = module.live_limits(count)
            self.assertEqual(limits.validate()["call_seconds"], 180)
            self.assertEqual(limits.max_model_calls, count * 17)
            self.assertEqual(limits.budget_microusd, 0)
            self.assertLess(150, limits.call_seconds)

    def test_expired_deadline_does_not_dispatch_or_count_an_attempt(self):
        calls = []
        router = ModelRouter("http://127.0.0.1:10100/v1",
            [ModelRoute("local-gateway", "local-gateway/free-model")],
            opener=lambda *args, **kwargs: calls.append(True), respect_rpm=False)
        with patch("uxpersonas.model_router.time.time", return_value=100):
            with self.assertRaisesRegex(RuntimeError, "deadline_before_dispatch"):
                router.complete([{"role": "user", "content": "test"}], deadline=99)
        self.assertEqual(calls, [])
        self.assertEqual(router.report()["routes"][router.routes[0].model]["attempts"], 0)

    def test_error_receipt_keeps_usage_served_name_and_native_tool_diagnostic(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size):
                return json.dumps({"id": "rejected-response", "model": "free-model",
                    "usage": {"prompt_tokens": 9, "completion_tokens": 4, "cost": 0, "billing_source": "free"},
                    "choices": [{"message": {"content": None, "tool_calls": [{"function": {
                        "name": "unknown_tool", "arguments": "{}"}}]}}]}).encode()
        router = ModelRouter("http://127.0.0.1:10100/v1",
            [ModelRoute("local-gateway", "local-gateway/free-model",
                        allowed_served_models=("local-gateway/free-model", "free-model"))],
            opener=lambda *args, **kw: Response(), max_retries=0)
        with patch.dict(os.environ, {"PROXY_API_KEY": "offline-test-key"}):
            with self.assertRaises(ProviderUncertain):
                router.complete([{"role": "user", "content": "test"}])
        event = router.report()["events"][0]
        self.assertEqual(event["native_tool_names"], ["unknown_tool"])
        self.assertEqual(event["response_id"], "rejected-response")
        self.assertEqual(event["served_model"], "free-model")
        self.assertEqual(event["provider_reported_cost"], 0)
        self.assertEqual(event["billing_source"], "free")
        self.assertEqual(event["input_tokens"], 9)
        self.assertNotIn("offline-test-key", json.dumps(event))


if __name__ == "__main__":
    unittest.main()
