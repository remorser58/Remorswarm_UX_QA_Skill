"""Offline transport regressions; no credentials, model requests or network."""
import asyncio
from email.utils import formatdate
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa"))
from uxpersonas import swarm_providers as p
from uxresearch.canonical import canonical, digest


def spec(protocol="openai-chat", **kw):
    data = dict(key="reviewed", protocol=protocol, model="reviewed-exact-model",
                endpoint="https://provider.example/chat/completions",
                input_price_per_million=1000000, output_price_per_million=3000000)
    if protocol in ("fixture", "callback"):
        data["endpoint"] = ""
    data.update(kw)
    return p.ProviderSpec(**data)


def request():
    payload = dict(persona={"label": "synthetic"}, goal="Finish", tools=[], observations=[])
    return dict(operation_id="op-1", context_id="ctx-1", request_sha256=digest(payload),
                deadline=time.time() + 10, payload=payload)


def result():
    return {"kind": "final", "judgment": {"outcome": "inconclusive"}}


def envelope(req):
    out = {k: req[k] for k in ("operation_id", "context_id", "request_sha256")}
    out.update(trace_id="fixture-trace", result=result(), usage=dict(input_tokens=10, output_tokens=4))
    return out


def wire(protocol="openai-chat", **kw):
    if protocol == "openai-chat":
        data = dict(id="trace-1", model="reviewed-exact-model", object="chat.completion",
                    choices=[dict(index=0, finish_reason="stop", message=dict(role="assistant", content=json.dumps(result())))],
                    usage=dict(prompt_tokens=10, completion_tokens=4, total_tokens=14))
    else:
        data = dict(id="trace-1", model="reviewed-exact-model", type="message", role="assistant",
                    stop_reason="end_turn", content=[dict(type="text", text=json.dumps(result()))],
                    usage=dict(input_tokens=10, output_tokens=4))
    data.update(kw)
    return data


class ProviderSpecTests(unittest.TestCase):
    def test_retry_after_numeric_date_invalid_and_bounded(self):
        with patch.object(p.time, "time", return_value=1700000000):
            cases = (("12", 12), (".5", 0), ("1.5", 2), ("999999999", 86400),
                     (formatdate(1700000030, usegmt=True), 30),
                     (formatdate(1699999990, usegmt=True), 0),
                     ("NaN", 0), ("Infinity", 0), ("-4", 0), ("sensitive-body", 0),
                     ("9" * 129, 0), (None, 0))
            for value, expected in cases:
                with self.subTest(value=value):
                    self.assertEqual(p._retry_after(value), expected)

    def test_cost_integer_upward_and_full_context_reservation(self):
        value = spec(input_price_per_million=2, output_price_per_million=3)
        self.assertEqual(value.cost(1, 0), 1)
        self.assertEqual(value.cost(0, 0), 0)
        self.assertEqual(value.reserve_microusd, 1)
        self.assertEqual(spec().reserve_microusd, 8192 + 1024 * 3)
        self.assertEqual(value.validate()["input_token_cap"], 8192)
        with self.assertRaises(p.DefinitelyNotSent):
            value.cost(8193, 0)

    def test_endpoint_and_billable_limits_reject_before_dispatch(self):
        for endpoint in ("http://provider.example/x", "https://u:p@provider.example/x",
                         "https://provider.example/x?q=1", "https://provider.example/x#x",
                         "https://provider.example/x?", "https://provider.example/x#",
                         "https://provider.example:444/x", "https://provider.example/\r\nx",
                         "https://provider.example\\@evil.example/x"):
            with self.subTest(endpoint=endpoint), self.assertRaises(p.DefinitelyNotSent):
                spec(endpoint=endpoint).validate()
        for kw in ({"input_price_per_million": 0}, {"output_price_per_million": -1},
                   {"concurrency": True}, {"requests_per_minute": 0}, {"timeout_seconds": 301},
                   {"input_token_cap": 0}, {"output_token_cap": 1.5}):
            with self.subTest(kw=kw), self.assertRaises(p.DefinitelyNotSent):
                spec(**kw).validate()

    def test_constructor_never_resolves_secret_or_network(self):
        resolver = Mock(side_effect=AssertionError("must not access credentials"))
        with patch.object(p.http.client, "HTTPSConnection", side_effect=AssertionError("no network")):
            transport = p.HTTPProvider(spec(), resolver, approved_endpoint=spec().endpoint)
            self.assertEqual(transport.mode, "live")
            self.assertEqual(len(transport.adapter_sha256), 64)
            self.assertFalse(transport.supports_idempotency)
            self.assertFalse(transport.supports_reconciliation)
        resolver.assert_not_called()
        with self.assertRaises(p.DefinitelyNotSent):
            p.HTTPProvider(spec(), resolver, approved_endpoint="https://other.example/x")

    def test_protocol_headers_are_explicit_and_redacted_on_rejection(self):
        headers = p._headers(spec(), "synthetic-secret")
        self.assertEqual(headers["Authorization"], "Bearer synthetic-secret")
        self.assertNotIn("x-api-key", headers)
        headers = p._headers(spec("anthropic-messages"), "synthetic-secret")
        self.assertEqual(headers["x-api-key"], "synthetic-secret")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertNotIn("Authorization", headers)
        with self.assertRaises(p.DefinitelyNotSent) as caught:
            p._headers(spec(), "sensitive\r\ninjected")
        self.assertNotIn("sensitive", str(caught.exception))


class HTTPFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_shape_result_and_correlation(self):
        observed = []
        def exchange(s, packet, timeout):
            observed.append((json.loads(packet), timeout))
            return canonical(wire())
        transport = p._FixtureHTTPProvider(spec(), exchange)
        req = request()
        response = await transport.call(req)
        body, timeout = observed[0]
        self.assertEqual(transport.mode, "fixture")
        with self.assertRaises(AttributeError):
            transport.mode = "live"
        self.assertEqual(body["model"], transport.spec.model)
        self.assertEqual(body["max_tokens"], 1024)
        self.assertFalse(body["stream"])
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(json.loads(body["messages"][1]["content"]), req["payload"])
        self.assertNotIn("tools", body)
        self.assertGreater(timeout, 0)
        for key in ("operation_id", "context_id", "request_sha256"):
            self.assertEqual(response[key], req[key])
        self.assertEqual(response["usage"], {"input_tokens": 10, "output_tokens": 4})

    async def test_anthropic_shape_and_text_json(self):
        def exchange(s, packet, timeout):
            body = json.loads(packet)
            self.assertIn("system", body)
            self.assertEqual([x["role"] for x in body["messages"]], ["user"])
            self.assertNotIn("tools", body)
            self.assertNotIn("response_format", body)
            return canonical(wire("anthropic-messages"))
        out = await p._FixtureHTTPProvider(spec("anthropic-messages"), exchange).call(request())
        self.assertEqual(out["result"], result())

    async def test_bad_hash_expired_deadline_and_size_never_dispatch(self):
        exchange = Mock(side_effect=AssertionError("dispatch forbidden"))
        transport = p._FixtureHTTPProvider(spec(), exchange)
        variants = []
        for field, value in (("request_sha256", "0" * 64), ("deadline", time.time() - 1),
                             ("deadline", float("nan")), ("context_id", "wrong\ncontext")):
            req = request()
            req[field] = value
            variants.append(req)
        req = request()
        req["payload"]["large"] = "x" * p.MAX_REQUEST_BYTES
        req["request_sha256"] = digest(req["payload"])
        variants.append(req)
        for req in variants:
            with self.subTest(field=req["context_id"]), self.assertRaises(p.DefinitelyNotSent):
                await transport.call(req)
        exchange.assert_not_called()

    async def test_utf8_request_fits_but_escaped_http_body_never_dispatches(self):
        req = request()
        req["payload"]["large"] = "가" * 50_000 + '"' * 30_000
        req["request_sha256"] = digest(req["payload"])
        self.assertLess(len(canonical(req)), p.MAX_REQUEST_BYTES)

        for protocol in ("openai-chat", "anthropic-messages"):
            with self.subTest(protocol=protocol):
                bodies = []

                def record_body(document):
                    raw = canonical(document)
                    if "messages" in document:
                        bodies.append(raw)
                    return raw

                exchange = Mock(side_effect=AssertionError("dispatch forbidden"))
                transport = p._FixtureHTTPProvider(spec(protocol), exchange)
                # Observe the adapter's actual encoded body; leave both limits intact.
                with (
                    patch.object(p, "canonical", side_effect=record_body),
                    patch.object(p.http.client, "HTTPSConnection", side_effect=AssertionError("network forbidden")) as https,
                ):
                    with self.assertRaises(p.DefinitelyNotSent) as caught:
                        await transport.call(req)
                self.assertEqual(caught.exception.code, "provider_request_too_large")
                body, = bodies
                self.assertGreater(len(body), p.MAX_REQUEST_BYTES)
                exchange.assert_not_called()
                https.assert_not_called()

    async def test_protocol_model_usage_and_native_tools_fail_uncertain(self):
        variants = [wire(model="different"), wire(usage={"prompt_tokens": 8193, "completion_tokens": 4}),
                    wire(usage={"prompt_tokens": True, "completion_tokens": 4}),
                    wire(usage={"prompt_tokens": 10, "completion_tokens": 1025}),
                    wire(usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 15}),
                    wire(usage={"prompt_tokens": 10, "completion_tokens": 4,
                                "completion_tokens_details": {"reasoning_tokens": 1}})]
        for field, value in (("tool_calls", [{"id": "native"}]), ("reasoning_content", "hidden reasoning")):
            item = wire()
            item["choices"][0]["message"][field] = value
            variants.append(item)
        item = wire()
        item["choices"][0]["finish_reason"] = "length"
        variants.append(item)
        for item in variants:
            transport = p._FixtureHTTPProvider(spec(), lambda *_, data=item: canonical(data))
            with self.subTest(item=item), self.assertRaises(p.ProviderUncertain):
                await transport.call(request())

    async def test_anthropic_native_cache_and_reasoning_extras_rejected(self):
        variants = [wire("anthropic-messages", stop_reason="tool_use"),
                    wire("anthropic-messages", content=[{"type": "thinking", "thinking": "hidden"}]),
                    wire("anthropic-messages", usage={"input_tokens": 10, "output_tokens": 4, "cache_creation_input_tokens": 1}),
                    wire("anthropic-messages", usage={"input_tokens": 10, "output_tokens": 4, "server_tool_use": {"web_search_requests": 1}})]
        for item in variants:
            transport = p._FixtureHTTPProvider(spec("anthropic-messages"), lambda *_, data=item: canonical(data))
            with self.assertRaises(p.ProviderUncertain):
                await transport.call(request())

    async def test_duplicate_json_malformed_and_oversize_uncertain(self):
        for raw in (b'{"model":"a","model":"b"}', b"private-error-body", b"x" * (p.MAX_RESPONSE_BYTES + 1)):
            with self.assertRaises(p.ProviderUncertain) as caught:
                await p._FixtureHTTPProvider(spec(), lambda *_, data=raw: data).call(request())
            self.assertNotIn("private-error-body", str(caught.exception))

    async def test_json_tool_decision_is_not_executed(self):
        item = wire()
        decision = {"kind": "tool", "tool": "observe", "arguments": {}, "decision": "Inspect current state"}
        item["choices"][0]["message"]["content"] = json.dumps(decision)
        out = await p._FixtureHTTPProvider(spec(), lambda *_: canonical(item)).call(request())
        self.assertEqual(out["result"], decision)

    async def test_redirect_and_http_error_are_uncertain_without_retry(self):
        for status in (302, 307, 429, 500):
            connection = Mock()
            response = connection.getresponse.return_value
            response.status = status
            def exchange(s, packet, timeout):
                return p._https_post(s.endpoint, p._headers(s, "fixture-secret"), packet, timeout)
            with patch.object(p.http.client, "HTTPSConnection", return_value=connection) as constructor:
                with self.assertRaises(p.ProviderUncertain):
                    await p._FixtureHTTPProvider(spec(), exchange).call(request())
            self.assertEqual(constructor.call_count, 1)
            self.assertEqual(connection.request.call_count, 1)
            connection.close.assert_called_once()
            response.read1.assert_not_called()

    async def test_wire_body_is_bounded_and_connection_closed(self):
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.getheader.side_effect = lambda key, default=None: {"Content-Type": "application/json", "Content-Length": str(p.MAX_RESPONSE_BYTES + 1)}.get(key, default)
        with patch.object(p.http.client, "HTTPSConnection", return_value=connection):
            with self.assertRaises(p.ProviderUncertain):
                p._https_post(spec().endpoint, {}, b"{}", 1)
        connection.close.assert_called_once()
        response.read1.assert_not_called()


    async def test_429_cooldown_preserved_without_retry_or_body_read(self):
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 429
        response.getheader.return_value = "123"
        def exchange(s, packet, timeout):
            return p._https_post(s.endpoint, p._headers(s, "fixture-secret"), packet, timeout)
        with patch.object(p.http.client, "HTTPSConnection", return_value=connection):
            with self.assertRaises(p.ProviderUncertain) as caught:
                await p._FixtureHTTPProvider(spec(), exchange).call(request())
        self.assertEqual(caught.exception.retry_after, 123)
        self.assertTrue(caught.exception.can_retry)
        self.assertEqual(connection.request.call_count, 1)
        response.read1.assert_not_called()
        self.assertNotIn("fixture-secret", str(caught.exception))


    async def test_direct_https_post_uses_exact_path_and_single_bounded_read(self):
        raw = canonical(wire())
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.getheader.side_effect = lambda key, default=None: {"Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(raw))}.get(key, default)
        response.read1.side_effect = [raw, b""]
        def exchange(s, packet, timeout):
            return p._https_post(s.endpoint, p._headers(s, "fixture-secret"), packet, timeout)
        with patch.object(p.http.client, "HTTPSConnection", return_value=connection) as constructor:
            out = await p._FixtureHTTPProvider(spec(), exchange).call(request())
        self.assertEqual(out["result"], result())
        self.assertEqual(constructor.call_args.args, ("provider.example", 443))
        self.assertEqual(connection.request.call_args.args, ("POST", "/chat/completions"))
        self.assertEqual(connection.request.call_args.kwargs["headers"]["Authorization"], "Bearer fixture-secret")
        self.assertLessEqual(max(call.args[0] for call in response.read1.call_args_list), 16384)
        connection.close.assert_called_once()


class CallbackTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, callback, **kw):
        return p.CallbackProvider(spec("callback"), callback, mode=kw.get("mode", "fixture"), adapter_sha256="a" * 64)

    async def test_sync_and_async_callbacks_detach_and_bind(self):
        async def async_callback(req):
            req["payload"]["goal"] = "callback mutation"
            return envelope(req)
        for callback in (envelope, async_callback):
            req = request()
            out = await self.provider(callback).call(req)
            self.assertEqual(req["payload"]["goal"], "Finish")
            self.assertEqual(out["request_sha256"], req["request_sha256"])
            self.assertEqual(out["result"], result())

    async def test_response_correlation_is_required(self):
        for field in ("context_id", "operation_id", "request_sha256"):
            def callback(req):
                out = envelope(req)
                out[field] = "mismatched"
                return out
            with self.assertRaises(p.ProviderUncertain):
                await self.provider(callback).call(request())

    async def test_callback_failure_cannot_claim_no_charge_or_leak_details(self):
        for error in (RuntimeError("secret-private-provider-body"), p.DefinitelyNotSent("untrusted-claim")):
            def callback(req):
                raise error
            with self.assertRaises(p.ProviderUncertain) as caught:
                await self.provider(callback).call(request())
            self.assertNotIn("secret", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

    async def test_callback_timeout_remains_uncertain(self):
        async def callback(req):
            await asyncio.sleep(1)
            return envelope(req)
        req = request()
        req["deadline"] = time.time() + .02
        with self.assertRaises(p.ProviderUncertain) as caught:
            await self.provider(callback).call(req)
        self.assertEqual(caught.exception.code, "provider_timeout")

    def test_fixture_cannot_be_live_and_live_requires_prices(self):
        with self.assertRaises(p.DefinitelyNotSent):
            p.CallbackProvider(spec("fixture"), envelope, mode="live", adapter_sha256="a" * 64)
        with self.assertRaises(p.DefinitelyNotSent):
            p.CallbackProvider(spec("callback", input_price_per_million=0), envelope, mode="live", adapter_sha256="a" * 64)
        self.assertEqual(self.provider(envelope, mode="live").mode, "live")
        self.assertNotEqual(self.provider(envelope).adapter_sha256, "a" * 64)


if __name__ == "__main__":
    unittest.main()
