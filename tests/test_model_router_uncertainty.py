"""Offline post-dispatch uncertainty regressions; all HTTP openers are fakes."""
import ast
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import _paths
from uxpersonas.model_router import ModelRoute, ModelRouter, RoutedScaleProvider
from uxpersonas.swarm_providers import DefinitelyNotSent, ProviderUncertain
import test_scale_run as scale_fixtures


class Response:
    status = 200
    def __init__(self, value): self.value = json.dumps(value).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size): return self.value


def reply():
    return {"id": "response-known", "model": "free-model",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0}}


def routes():
    return [ModelRoute("local-gateway", "local-gateway/free-model", allowed_served_models=("free-model",)),
            ModelRoute("offline-alternate", "must-not-dispatch")]


class RouterUncertaintyTests(unittest.TestCase):
    def setUp(self):
        auth = patch.dict(os.environ, {"PROXY_API_KEY": "offline-test-only"})
        auth.start()
        self.addCleanup(auth.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Path(self.temp.name) / "router.json"

    def router(self, opener, **kwargs):
        max_retries = kwargs.pop("max_retries", 3)
        return ModelRouter("http://127.0.0.1:10100/v1", routes(), opener=opener,
                           respect_rpm=False, sleep=lambda seconds: None, max_retries=max_retries,
                           ledger_path=self.ledger, **kwargs)

    def test_timeout_dispatches_once_and_same_id_is_quarantined_after_restart(self):
        opener = Mock(side_effect=TimeoutError("offline_timeout"))
        router = self.router(opener, max_retries=2)
        for _ in range(2):
            with self.assertRaises(ProviderUncertain) as caught:
                router.complete([], call_id="op-timeout")
            self.assertFalse(caught.exception.can_retry)
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(router.report()["routes"]["must-not-dispatch"]["attempts"], 0)
        self.assertEqual(router.report()["call_delivery"]["op-timeout"], "uncertain")
        before = self.ledger.read_bytes()
        restarted = self.router(opener)
        with self.assertRaises(ProviderUncertain):
            restarted.complete([], call_id="op-timeout")
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(restarted.report()["events"][0]["delivery_state"], "uncertain")

    def test_dispatch_intent_survives_process_exit_without_response(self):
        def opener(request, timeout):
            saved = json.loads(self.ledger.read_text())
            self.assertEqual(saved["call_delivery"]["op-intent"], "intent")
            raise KeyboardInterrupt("synthetic_process_exit")
        with self.assertRaises(KeyboardInterrupt):
            self.router(opener).complete([], call_id="op-intent")
        never = Mock(side_effect=AssertionError("must_not_redispatch"))
        with self.assertRaises(ProviderUncertain):
            self.router(never).complete([], call_id="op-intent")
        never.assert_not_called()

    def test_transport_and_gateway_timeout_never_retry_or_fallback(self):
        cases = [URLError("unknown_connection_state"), OSError("connection_reset"),
                 HTTPError("http://127.0.0.1:10100/v1/chat/completions", 408, "timeout", {}, None),
                 HTTPError("http://127.0.0.1:10100/v1/chat/completions", 504, "timeout", {}, None),
                 HTTPError("http://127.0.0.1:10100/v1/chat/completions", 599, "gateway_unknown", {}, None)]
        for index, error in enumerate(cases):
            with self.subTest(error=type(error).__name__, index=index):
                opener = Mock(side_effect=error)
                router = self.router(opener)
                with self.assertRaises(ProviderUncertain):
                    router.complete([], call_id="op-transport-" + str(index))
                self.assertEqual(opener.call_count, 1)
                self.assertEqual(json.loads(opener.call_args[0][0].data)["model"], routes()[0].model)
                self.assertEqual(router.report()["routes"]["must-not-dispatch"]["attempts"], 0)

    def test_response_read_timeout_is_uncertain_not_a_known_rejection(self):
        class ReadTimeout(Response):
            def read(self, size): raise TimeoutError("response_body_timeout")
        opener = Mock(return_value=ReadTimeout(reply()))
        with self.assertRaises(ProviderUncertain):
            self.router(opener).complete([], call_id="op-read-timeout")
        self.assertEqual(opener.call_count, 1)

    def test_invalid_protocol_envelopes_cannot_trigger_second_send(self):
        payloads = [[], {"choices": []},
                    {"usage": [], "choices": [{"message": {"content": "ok"}}]},
                    dict(reply(), choices=[{"message": []}]),
                    dict(reply(), choices=[{"message": {"content": None, "tool_calls": "bad"}}])]
        for index, payload in enumerate(payloads):
            with self.subTest(index=index):
                opener = Mock(return_value=Response(payload))
                router = self.router(opener)
                with self.assertRaises(ProviderUncertain):
                    router.complete([], call_id="op-protocol-" + str(index))
                self.assertEqual(opener.call_count, 1)
                self.assertEqual(router.report()["routes"]["must-not-dispatch"]["attempts"], 0)

    def test_legacy_uncertainty_remains_absorbing_after_later_success(self):
        saved = self.router(Mock()).report()
        saved.pop("call_delivery")
        saved["events"] = [
            {"call_id": "op-legacy", "status": "transport_or_protocol_error", "error_type": "TimeoutError"},
            {"call_id": "op-legacy", "status": "success", "response_id": "later-retried-reply"},
        ]
        self.ledger.write_text(json.dumps(saved))
        before = self.ledger.read_bytes()
        opener = Mock(side_effect=AssertionError("legacy_uncertain_must_not_send"))
        router = self.router(opener)
        with self.assertRaises(ProviderUncertain):
            router.complete([], call_id="op-legacy")
        opener.assert_not_called()
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_known_quality_rejection_remains_distinct_from_uncertainty(self):
        first = reply()
        first["choices"][0]["message"]["content"] = "rejected"
        opener = Mock(side_effect=[Response(first), Response(reply())])
        router = self.router(opener)
        content, _ = router.complete([], call_id="op-known", quality_check=lambda content: content == "ok")
        self.assertEqual(content, "ok")
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(router.report()["call_delivery"]["op-known"], "reply_received")
        self.assertTrue(any(row["status"] == "quality_rejected" for row in router.report()["events"]))

    def test_invalid_ledger_fails_closed_without_replacing_it(self):
        self.ledger.write_text("not valid json")
        opener = Mock()
        with self.assertRaisesRegex(RuntimeError, "model_router_ledger_invalid"):
            self.router(opener)
        opener.assert_not_called()
        self.assertEqual(self.ledger.read_text(), "not valid json")

    def test_failed_intent_persistence_prevents_any_dispatch(self):
        opener = Mock()
        router = self.router(opener)
        with patch.object(router, "_persist", side_effect=OSError("offline_disk_failure")):
            with self.assertRaises(DefinitelyNotSent):
                router.complete([], call_id="op-no-durable-intent")
        opener.assert_not_called()

    def test_known_rejected_reply_followed_by_timeout_stops_all_further_attempts(self):
        first = reply()
        first["choices"][0]["message"]["content"] = "rejected"
        opener = Mock(side_effect=[Response(first), TimeoutError("unknown_second_send"), Response(reply())])
        router = self.router(opener)
        with self.assertRaises(ProviderUncertain):
            router.complete([], call_id="op-quality-then-unknown", quality_check=lambda value: value == "ok")
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(router.report()["routes"]["must-not-dispatch"]["attempts"], 0)
        with self.assertRaises(ProviderUncertain):
            router.complete([], call_id="op-quality-then-unknown")
        self.assertEqual(opener.call_count, 2)

    def test_live_policy_bounds_known_reply_repairs_and_transport_deadline(self):
        path = Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa/scripts/live_scale_browser.py"
        tree = ast.parse(path.read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        router_call = next(node for node in calls if node.func.id == "ModelRouter")
        provider_call = next(node for node in calls if node.func.id == "ProviderSpec")
        values = {kw.arg: ast.literal_eval(kw.value) for kw in router_call.keywords if kw.arg in {"timeout", "max_retries"}}
        provider_timeout = next(ast.literal_eval(kw.value) for kw in provider_call.keywords if kw.arg == "timeout_seconds")
        self.assertEqual(values, {"timeout": 150, "max_retries": 2})
        self.assertLess(values["timeout"], provider_timeout)

    def test_live_repair_budget_allows_two_known_reply_repairs_and_no_fourth_send(self):
        first = reply()
        first["choices"][0]["message"]["content"] = "rejected"
        for accepted in (True, False):
            with self.subTest(accepted=accepted):
                sequence = [Response(first), Response(first), Response(reply() if accepted else first)]
                opener = Mock(side_effect=sequence)
                router = ModelRouter("http://127.0.0.1:10100/v1", routes()[:1], opener=opener,
                                     timeout=150, max_retries=2, respect_rpm=False, sleep=lambda seconds: None)
                if accepted:
                    content, _ = router.complete([], call_id="op-repair", quality_check=lambda value: value == "ok")
                    self.assertEqual(content, "ok")
                else:
                    with self.assertRaisesRegex(RuntimeError, "all_model_routes_failed"):
                        router.complete([], call_id="op-repair", quality_check=lambda value: value == "ok")
                self.assertEqual(opener.call_count, 3)
                self.assertEqual(router.report()["call_delivery"]["op-repair"], "reply_received")

    def test_known_reply_repair_uses_remaining_original_deadline(self):
        clock, timeouts = [100.0], []
        first = reply()
        first["choices"][0]["message"]["content"] = "rejected"
        def opener(request, timeout):
            timeouts.append(timeout)
            clock[0] += 6 if len(timeouts) == 1 else 1
            return Response(first if len(timeouts) == 1 else reply())
        def sleep(seconds):
            clock[0] += seconds
        router = ModelRouter("http://127.0.0.1:10100/v1", routes()[:1], opener=opener,
                             timeout=150, max_retries=2, backoff_initial=1,
                             respect_rpm=False, sleep=sleep)
        with patch("uxpersonas.model_router.time.time", side_effect=lambda: clock[0]):
            router.complete([], call_id="op-remaining-budget", deadline=110,
                            quality_check=lambda value: value == "ok")
        self.assertEqual(timeouts, [10.0, 3.0])


class RouterQueueUncertaintyTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_uncertainty_reaches_queue_and_no_resume_resends_it(self):
        case = scale_fixtures.ScaleRunTests(methodName="test_two_independent_sessions_preserve_failure_and_reuse_completed_report")
        case.setUp()
        self.addCleanup(case.doCleanups)
        opener = Mock(side_effect=TimeoutError("offline_router_timeout"))
        router = ModelRouter("http://127.0.0.1:10100/v1", routes(), opener=opener,
                             max_retries=3, respect_rpm=False, sleep=lambda seconds: None,
                             ledger_path=case.root / "router-ledger.json")
        routed = RoutedScaleProvider(case.provider.spec, router)
        # Keep the fixture plan/transport identity; exercise the actual router adapter.
        case.provider.call = routed.call
        with patch.dict(os.environ, {"PROXY_API_KEY": "offline-router-queue-test"}):
            report = await case.run_scale()
            self.assertEqual(report["counts"]["uncertain"], 2)
            self.assertEqual(report["counts"]["complete"], 0)
            model_ops = [row for row in report["operations"] if row["kind"] in {"model", "review"}]
            self.assertEqual(len(model_ops), 2)
            self.assertTrue(all(row["state"] == "uncertain" for row in model_ops))
            self.assertTrue(all(row.get("problem") == "model_delivery_uncertain" for row in model_ops))
            self.assertEqual(opener.call_count, 2)  # Exactly one opener per distinct operation.
            self.assertFalse(case.host.calls)
            again = await case.run_scale()
            self.assertEqual(again["counts"]["uncertain"], 2)
            self.assertEqual(opener.call_count, 2)
            self.assertEqual(router.report()["routes"]["must-not-dispatch"]["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
