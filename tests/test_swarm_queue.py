"""Offline queue safety regressions; no model, browser, or network dispatch.

The small plans exercise queue storage directly. Persona evidence and execution
admission are covered independently by the runner and evidence suites.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa"))
from uxpersonas.swarm_providers import ProviderSpec
from uxpersonas.swarm_queue import Queue, SCHEMA
from uxresearch.canonical import EngineError, canonical


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def provider(key="a", mode="fixture", **overrides):
    values = dict(key=key, protocol="callback" if mode == "live" else "fixture",
                  model="offline-exact-model", concurrency=8, requests_per_minute=60,
                  input_price_per_million=1000000, output_price_per_million=2000000,
                  input_token_cap=10, output_token_cap=5, timeout_seconds=5)
    values.update(overrides)
    value = dict(spec=ProviderSpec(**values).validate(), mode=mode,
                 adapter_sha256="a" * 64, credential_scope="offline-scope" if mode == "live" else None)
    if mode == "live":
        fields = ("input_token_cap", "output_token_cap",
                  "input_price_per_million", "output_price_per_million")
        value["billing_review"] = {name: value["spec"][name] for name in fields}
        value["billing_review"].update(no_unpriced_features=True,
                                       source="offline-authored-billing-assumptions",
                                       checked_at="2026-11-13T00:00:00Z")
        value["destination"] = "offline-callback-no-network"
    return value


def plan(count=3, routes=None, mode="fixture", providers=None, **limits):
    providers = providers or {"a": provider(mode=mode)}
    routes = routes or ["a"] * count
    settings = dict(parallel=4, turns=4, call_seconds=5, task_seconds=60,
                    lease_seconds=10, budget_microusd=1000, max_model_calls=100)
    settings.update(limits)
    return dict(schema_version=SCHEMA, mode=mode, limits=settings, providers=providers,
                jobs=[dict(id=f"job-{i:03}", provider=route,
                           task={"persona_id": f"saved-persona-{i:03}"})
                      for i, route in enumerate(routes)])


def reply(request, *, input_tokens=2, output_tokens=1, billed=True):
    value = {k: request[k] for k in ("operation_id", "context_id", "request_sha256")}
    value.update(trace_id="offline-trace", result={"kind": "final", "judgment": {"outcome": "inconclusive"}})
    if billed:
        value["usage"] = dict(input_tokens=input_tokens, output_tokens=output_tokens)
    return value


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="swarm-queue-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "queue"
        self.clock = Clock()

    def create(self, **kwargs):
        return Queue.create(self.root, plan(**kwargs), clock=self.clock)

    def reopen(self):
        return Queue(self.root, clock=self.clock)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(EngineError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.issue["code"], code)

    def sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.root / "queue.sqlite")) as db, db:
            db.execute(statement, parameters)

    def authorize(self, queue, *, expires=None):
        return queue.authorize(plan_sha256=queue.plan_sha256, actor="offline-reviewer",
                               consent_reference="offline-test-approval", expires_at=expires or self.clock() + 30,
                               budget_microusd=queue.plan["limits"]["budget_microusd"])

    def test_connection_closes_when_setup_fails_before_yield(self):
        queue = self.create()
        for write, statement in ((False, "PRAGMA foreign_keys=ON"), (True, "BEGIN IMMEDIATE")):
            with self.subTest(write=write):
                error = sqlite3.OperationalError("injected SQLite setup failure")
                connection = Mock(spec=sqlite3.Connection)

                def execute(sql):
                    if sql == statement:
                        raise error

                connection.execute.side_effect = execute
                with patch("uxpersonas.swarm_queue.sqlite3.connect", return_value=connection):
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        with queue._db(write=write):
                            self.fail("A caller must not receive a connection whose setup failed")
                self.assertIs(caught.exception, error)
                connection.close.assert_called_once_with()
                connection.commit.assert_not_called()
                connection.rollback.assert_not_called()

    def test_twelve_distinct_sessions_keep_context_and_checkpoint_isolation(self):
        queue = self.create(count=12)
        contexts, personas = set(), set()
        for index in range(12):
            claim = queue.claim(f"worker-{index}")
            self.assertIsNotNone(claim)
            self.assertEqual(claim["checkpoint"], {})
            contexts.add(claim["context_id"])
            personas.add(claim["job"]["task"]["persona_id"])
            state = {"observations": [index]}
            queue.checkpoint(claim, state)
            state["observations"].append("caller mutation")
            self.assertEqual(queue.assert_claim(claim)["checkpoint"], json.dumps({"observations": [index]}, separators=(",", ":")))
            queue.complete(claim, {"outcome": "inconclusive", "index": index})
        report = self.reopen().report()
        self.assertEqual(len(contexts), 12)
        self.assertEqual(len(personas), 12)
        self.assertEqual(report["counts"]["complete"], 12)
        self.assertIsNone(queue.claim("after-completion"))
        self.assertFalse(report["actual_model_execution"])
        self.assertFalse(report["product_ready"])
        self.assertFalse(report["real_user_evidence"])
        self.assertEqual(queue.audit_events(), report["event_chain_head"])

    def test_duplicate_persona_or_job_rejected_before_creating_directory(self):
        for field in ("id", "persona_id"):
            value = plan()
            if field == "id":
                value["jobs"][1]["id"] = value["jobs"][0]["id"]
            else:
                value["jobs"][1]["task"][field] = value["jobs"][0]["task"][field]
            self.assert_code("queue_input", Queue.create, self.root, value, clock=self.clock)
            self.assertFalse(self.root.exists())

    def test_final_affordable_reservation_is_atomic_across_queue_objects(self):
        count = 6
        queue = self.create(count=count, parallel=count, budget_microusd=20)
        claims = [queue.claim(f"worker-{i}") for i in range(count)]
        barrier = threading.Barrier(count, timeout=10)

        def compete(claim):
            reopened = Queue(self.root, clock=self.clock)
            barrier.wait()
            try:
                return reopened.begin(claim, "model", 0, {"persona": claim["job_id"]})
            except EngineError as error:
                return error.issue["code"]

        with ThreadPoolExecutor(max_workers=count) as pool:
            outcomes = list(pool.map(compete, claims))
        winners = [outcome for outcome in outcomes if isinstance(outcome, dict)]
        self.assertEqual(len(winners), 1, outcomes)
        self.assertEqual(outcomes.count("admission_wait"), count - 1)
        report = self.reopen().report()
        self.assertEqual(len(report["operations"]), 1)
        self.assertEqual(report["budget"]["reserved"], 20)
        self.assertEqual(report["budget"]["remaining"], 0)
        request = winners[0]["request"]
        winner = next(claim for claim in claims if claim["job_id"] == request["payload"]["persona"])
        queue.finish(winner, request, reply(request, input_tokens=10, output_tokens=5))
        loser = next(claim for claim in claims if claim["job_id"] != winner["job_id"])
        self.assert_code("budget_exhausted", self.reopen().begin, loser, "model", 0,
                         {"persona": loser["job_id"]})
        self.assertEqual(queue.report()["budget"]["charged_or_settled"], 20)
        self.assertEqual(queue.report()["budget"]["reserved"], 0)

    def test_claim_race_never_assigns_one_session_twice(self):
        queue = self.create(count=12, parallel=12)
        barrier = threading.Barrier(12, timeout=10)

        def claim(index):
            reopened = Queue(self.root, clock=self.clock)
            barrier.wait()
            return reopened.claim(f"worker-{index}")

        with ThreadPoolExecutor(max_workers=12) as pool:
            claims = list(pool.map(claim, range(12)))
        self.assertEqual(len({item["job_id"] for item in claims}), 12)
        self.assertEqual(len({item["lease_token"] for item in claims}), 12)
        self.assertIsNone(queue.claim("overflow"))

    def test_provider_uncertain_operation_is_quarantined_without_holding_inflight_slot(self):
        queue = self.create(routes=["a", "a", "b"],
                            providers={"a": provider(concurrency=1), "b": provider("b", concurrency=1)})
        first = queue.claim("first")
        request = queue.begin(first, "model", 0, {})["request"]
        queue.uncertain(first, request["operation_id"], "transport_lost")
        second = self.reopen().claim("second")
        self.assertEqual(second["provider"], "a")
        request_a = queue.begin(second, "review", 0, {})["request"]
        queue.finish(second, request_a, reply(request_a))
        third = queue.claim("third")
        request_b = queue.begin(third, "model", 0, {})["request"]
        self.assertEqual(third["provider"], "b")
        queue.finish(third, request_b, reply(request_b))
        report = queue.report()
        self.assertEqual(report["providers"]["a"]["active_or_uncertain"], 1)
        self.assertEqual(report["budget"]["uncertain_reserved"], 20)

    def test_global_uncertain_operation_is_preserved_but_releases_inflight_slot_after_restart(self):
        queue = self.create(count=3, parallel=2)
        first = queue.claim("first")
        request = queue.begin(first, "tool", 0, {})["request"]
        queue.uncertain(first, request["operation_id"], "tool_may_have_run")
        second = queue.claim("second")
        queue.begin(second, "model", 0, {})
        third = self.reopen().claim("third")
        self.assertIsNotNone(third)
        third_request = queue.begin(third, "close", 0, {})["request"]
        self.assertEqual(third_request["payload"], {})
        report = queue.report()
        self.assertEqual(len(report["operations"]), 3)
        self.assertEqual(report["counts"]["uncertain"], 1)
        self.assertEqual(sum(op["state"] == "uncertain" for op in report["operations"]), 1)

    def test_verified_pre_dispatch_upload_rejection_reopens_fresh_model_decision(self):
        queue = self.create(count=1, parallel=2)
        claim = queue.claim("worker")
        checkpoint = {"phase": "tool", "turn": 15,
            "decision": {"kind": "tool", "tool": "upload", "arguments": {"file": "owned.zip"}},
            "observations": [], "problem": None}
        queue.checkpoint(claim, checkpoint)
        request = queue.begin(claim, "tool", 15, {"name": "upload", "file": "owned.zip"})["request"]
        queue.uncertain(claim, request["operation_id"],
                        "host_execution_failed:browser_action_failed:upload_target_missing")
        with self.assertRaises(EngineError):
            self.reopen().resolve_verified_pre_dispatch_rejection(request["operation_id"],
                actor="offline-test", evidence_reference="driver line 137 before DOM.setFileInputFiles",
                host_context_live=False, no_effect_confirmed=True)
        report = self.reopen().resolve_verified_pre_dispatch_rejection(request["operation_id"],
            actor="offline-test", evidence_reference="driver line 137 before DOM.setFileInputFiles",
            host_context_live=True, no_effect_confirmed=True)
        self.assertEqual(report["counts"]["queued"], 1)
        self.assertEqual(report["counts"]["uncertain"], 0)
        self.assertEqual(report["operations"][0]["state"], "not_sent")
        resumed = self.reopen().claim("fresh-worker")
        state = resumed["checkpoint"]
        self.assertEqual(state["phase"], "model")
        self.assertEqual(state["turn"], 15)
        self.assertIsNone(state["decision"])
        self.assertIn("no fixture was selected", state["observations"][-1]["text"])
        fresh = self.reopen().begin(resumed, "model", 15, {"phase": "model", "turn": 15})
        self.assertFalse(fresh["cached"])
        self.assertNotEqual(fresh["request"]["operation_id"], request["operation_id"])

    def test_rate_window_survives_restart_and_does_not_starve_other_provider(self):
        queue = self.create(routes=["a", "a", "b"], parallel=1,
                            providers={"a": provider(requests_per_minute=1), "b": provider("b")})
        first = queue.claim("first")
        request = queue.begin(first, "model", 0, {})["request"]
        queue.finish(first, request, reply(request))
        queue.complete(first, {"outcome": "inconclusive"})
        queue = self.reopen()
        limited = queue.claim("rate-limited")
        self.assertEqual(limited["provider"], "a")
        self.assert_code("admission_wait", queue.begin, limited, "model", 0, {})
        queue.release(limited)
        self.clock.advance(0.1)
        other = queue.claim("other-provider")
        self.assertEqual(other["provider"], "b")
        request = queue.begin(other, "model", 0, {})["request"]
        queue.finish(other, request, reply(request))
        queue.complete(other, {"outcome": "inconclusive"})
        self.clock.advance(59.9)
        retried = self.reopen().claim("window-reopened")
        self.assertEqual(retried["job_id"], limited["job_id"])
        queue.begin(retried, "model", 0, {})
        self.assertEqual(len(queue.report()["operations"]), 3)

    def test_provider_cooldown_is_durable_and_unrelated_provider_proceeds(self):
        queue = self.create(routes=["a", "a", "b"],
                            providers={"a": provider(), "b": provider("b")})
        first = queue.claim("first")
        request = queue.begin(first, "model", 0, {})["request"]
        queue.uncertain(first, request["operation_id"], "rate_response_unknown", retry_after=30)
        reopened = self.reopen()
        claim = reopened.claim("other")
        self.assertEqual(claim["provider"], "b")
        self.assertEqual(reopened.report()["providers"]["a"]["cooldown_until"], self.clock() + 30)
        self.assertIsNone(reopened.claim("cooldown"))
        self.clock.advance(30)
        eligible = self.reopen().claim("after-cooldown")
        self.assertEqual(eligible["provider"], "a")

    def test_pause_allows_sent_reply_to_settle_but_prevents_new_send(self):
        queue = self.create(count=2)
        claim = queue.claim("worker")
        request = queue.begin(claim, "model", 0, {"turn": 0})["request"]
        queue.control("pause")
        self.assertIsNone(self.reopen().claim("new-worker"))
        queue.finish(claim, request, reply(request))
        queue.checkpoint(claim, {"turn": 1})
        self.assert_code("paused", queue.begin, claim, "model", 1, {"turn": 1})
        cached = self.reopen().begin(claim, "model", 0, {"turn": 0})
        self.assertTrue(cached["cached"])
        self.assertEqual(queue.report()["budget"]["charged_or_settled"], 4)
        self.assertEqual(queue.report()["budget"]["reserved"], 0)
        queue.control("resume")
        queue.begin(claim, "model", 1, {"turn": 1})

    def test_expired_safe_checkpoint_reclaims_with_fence_and_preserved_state(self):
        queue = self.create(count=1)
        old = queue.claim("old")
        queue.checkpoint(old, {"turn": 2, "observations": ["saved"]})
        self.clock.advance(11)
        fresh = self.reopen().claim("fresh")
        self.assertEqual(fresh["job_id"], old["job_id"])
        self.assertEqual(fresh["context_id"], old["context_id"])
        self.assertNotEqual(fresh["lease_token"], old["lease_token"])
        self.assertEqual(fresh["checkpoint"], {"turn": 2, "observations": ["saved"]})
        for action, args in ((queue.renew, (old,)), (queue.checkpoint, (old, {"turn": 99})),
                             (queue.release, (old,)), (queue.block, (old, "late")),
                             (queue.complete, (old, {"late": True})),
                             (queue.begin, (old, "model", 0, {}))):
            with self.subTest(action=action.__name__):
                self.assert_code("stale_lease", action, *args)
        self.assertEqual(queue.report()["counts"]["running"], 1)

    def test_process_exit_after_intent_is_quarantined_without_repeat(self):
        queue = self.create(count=1)
        skill = Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa"
        child = (
            "import os,sys\n"
            "sys.path.insert(0,sys.argv[1])\n"
            "from uxpersonas.swarm_queue import Queue\n"
            "q=Queue(sys.argv[2],clock=lambda:1000.0)\n"
            "c=q.claim('doomed-worker')\n"
            "q.begin(c,'model',0,{'offline':True})\n"
            "os._exit(23)\n"
        )
        process = subprocess.run([sys.executable, "-c", child, str(skill), str(self.root)],
                                 capture_output=True, text=True, timeout=20,
                                 env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(process.returncode, 23, process.stderr)
        self.clock.advance(11)
        reopened = self.reopen()
        self.assertIsNone(reopened.claim("restart"))
        report = reopened.report()
        self.assertEqual(report["counts"]["uncertain"], 1)
        self.assertEqual(report["operations"][0]["state"], "uncertain")
        self.assertEqual(report["budget"]["reserved"], 20)
        self.assertEqual(report["budget"]["uncertain_reserved"], 20)
        self.assertEqual(len(report["operations"]), 1)
        self.assertIsNone(self.reopen().claim("another-restart"))

    def test_completed_reply_replayed_after_crash_without_duplicate_charge(self):
        queue = self.create(count=1)
        old = queue.claim("old")
        request = queue.begin(old, "model", 0, {"turn": 0})["request"]
        expected = reply(request)
        queue.finish(old, request, expected)
        self.clock.advance(11)
        restarted = self.reopen()
        fresh = restarted.claim("restart")
        cached = restarted.begin(fresh, "model", 0, {"turn": 0})
        self.assertTrue(cached["cached"])
        self.assertEqual(cached["request"], request)
        self.assertEqual(cached["reply"], expected)
        self.assertEqual(len(restarted.report()["operations"]), 1)
        self.assertEqual(restarted.report()["budget"]["charged_or_settled"], 4)
        self.assert_code("operation_conflict", restarted.begin, fresh, "model", 0, {"turn": "changed"})
        restarted.complete(fresh, {"outcome": "inconclusive"})
        again = self.reopen()
        self.assertIsNone(again.claim("third-worker"))
        self.assertEqual(again.report()["tasks"][0]["result"], {"outcome": "inconclusive"})

    def test_cancel_retains_uncertain_budget_and_is_final(self):
        queue = self.create(count=3, budget_microusd=40)
        sent = queue.claim("sent")
        safe = queue.claim("safe")
        request = queue.begin(sent, "model", 0, {})["request"]
        queue.control("cancel")
        reopened = self.reopen()
        report = reopened.report()
        self.assertEqual(report["counts"]["uncertain"], 1)
        self.assertEqual(report["counts"]["cancelled"], 2)
        self.assertEqual(report["budget"]["reserved"], 20)
        self.assertEqual(report["budget"]["uncertain_reserved"], 20)
        self.assertIsNone(reopened.claim("new"))
        self.assert_code("cancelled", reopened.control, "resume")
        self.assert_code("cancelled", self.authorize, reopened)
        self.assert_code("stale_lease", reopened.begin, safe, "model", 0, {})
        self.assert_code("stale_lease", reopened.finish, sent, request, reply(request))
        self.assertEqual(len(reopened.report()["operations"]), 1)

    def test_live_claim_requires_exact_approval_and_expiry_stops_new_sends(self):
        queue = self.create(count=2, mode="live")
        self.assertIsNone(queue.claim("unapproved"))
        self.assert_code("approval_required", queue.control, "resume")
        base = dict(plan_sha256=queue.plan_sha256, actor="offline-reviewer",
                    consent_reference="offline-test", expires_at=self.clock() + 2,
                    budget_microusd=1000)
        for changes in ({"plan_sha256": "f" * 64}, {"budget_microusd": 999},
                        {"expires_at": self.clock()}, {"actor": ""}):
            with self.subTest(changes=changes):
                self.assert_code("approval_invalid", queue.authorize, **dict(base, **changes))
        self.authorize(queue, expires=self.clock() + 2)
        queue.control("resume")
        claim = queue.claim("approved")
        request = queue.begin(claim, "model", 0, {})["request"]
        self.assertEqual(queue.report()["actual_model_dispatch_intents"], 1)
        self.assertEqual(queue.report()["actual_model_calls"], 0)
        self.clock.advance(2)
        reopened = self.reopen()
        self.assertFalse(reopened.report()["approved"])
        self.assertIsNone(reopened.claim("expired"))
        self.assert_code("approval_required", reopened.begin, claim, "model", 1, {})
        reopened.finish(claim, request, reply(request))
        self.assertEqual(reopened.report()["budget"]["reserved"], 0)
        self.assertEqual(len(reopened.report()["operations"]), 1)
        self.assertEqual(reopened.report()["actual_model_calls"], 1)

    def test_live_plan_rejects_missing_malformed_or_mismatched_billing_review(self):
        cases = (
            ("missing", None),
            ("malformed", None),
            ("malformed", []),
            ("input_token_cap", 11),
            ("output_token_cap", 6),
            ("input_price_per_million", 1000001),
            ("output_price_per_million", 2000001),
            ("no_unpriced_features", False),
            ("source", " "),
            ("checked_at", ""),
            ("destination", ""),
            ("destination", " "),
            ("destination", ["offline"]),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                candidate = plan(mode="live")
                route = candidate["providers"]["a"]
                if field == "missing":
                    del route["billing_review"]
                elif field == "malformed":
                    route["billing_review"] = value
                elif field == "destination":
                    route[field] = value
                else:
                    route["billing_review"][field] = value
                self.assert_code("billing_review_required", Queue.create,
                                 self.root, candidate, clock=self.clock)
                self.assertFalse(self.root.exists())

    def test_live_plan_cannot_label_fixture_protocol_or_zero_price_as_reviewed(self):
        for changes in ({"protocol": "fixture"}, {"input_price_per_million": 0},
                        {"output_price_per_million": 0}):
            with self.subTest(changes=changes):
                route = provider(mode="live", **changes)
                candidate = plan(mode="live", providers={"a": route})
                self.assert_code("billing_review_required", Queue.create,
                                 self.root, candidate, clock=self.clock)
                self.assertFalse(self.root.exists())

    def test_exact_free_tokenmaxx_route_allows_zero_cost_live_queue_only(self):
        route = provider(key="local-router", mode="live", model="tokenmaxx-deepseek-v4-1-flash-free",
                         input_price_per_million=0, output_price_per_million=0)
        review = route["billing_review"]
        review.update(free_tier=True, billing_source="free",
                      requested_model="TOKENMAXX/deepseek-v4.1-flash-free",
                      source="verified exact free route", checked_at="2026-11-13T15:30:00+09:00")
        candidate = plan(mode="live", providers={"local-router":route},
                         routes=["local-router"], budget_microusd=0)
        queue = Queue.create(self.root, candidate, clock=self.clock)
        self.assertEqual(queue.report()["budget"]["ceiling"], 0)
        self.assertEqual(queue.report()["budget"]["reserved"], 0)

    def test_zero_cost_live_route_rejects_any_other_provider_or_model(self):
        route = provider(key="local-router", mode="live", model="tokenmaxx-deepseek-v4-1-flash-free",
                         input_price_per_million=0, output_price_per_million=0)
        route["billing_review"].update(free_tier=True, billing_source="free",
            requested_model="TOKENMAXX/deepseek-v4.1-flash-free", source="verified", checked_at="2026-11-13")
        for key, model, requested in (
            ("other-router", "tokenmaxx-deepseek-v4-1-flash-free", "TOKENMAXX/deepseek-v4.1-flash-free"),
            ("local-router", "some-other-free-model", "TOKENMAXX/deepseek-v4.1-flash-free"),
            ("local-router", "tokenmaxx-deepseek-v4-1-flash-free", "inferhub/paid-model"),
        ):
            candidate_route = provider(key=key, mode="live", model=model,
                input_price_per_million=0, output_price_per_million=0)
            candidate_route["billing_review"].update(free_tier=True, billing_source="free",
                requested_model=requested, source="verified", checked_at="2026-11-13")
            candidate = plan(mode="live", providers={key:candidate_route}, routes=[key], budget_microusd=0)
            self.assert_code("billing_review_required", Queue.create, self.root, candidate, clock=self.clock)
            self.assertFalse(self.root.exists())

    def test_invalid_usage_and_response_correlation_cannot_release_reservation(self):
        queue = self.create(count=1)
        claim = queue.claim("worker")
        request = queue.begin(claim, "model", 0, {})["request"]
        for usage in ({"input_tokens": 11, "output_tokens": 0},
                      {"input_tokens": 0, "output_tokens": 6},
                      {"input_tokens": True, "output_tokens": 0},
                      {"input_tokens": -1, "output_tokens": 0},
                      {"input_tokens": 1}):
            response = reply(request)
            response["usage"] = usage
            with self.subTest(usage=usage), self.assertRaises(EngineError):
                queue.finish(claim, request, response)
            self.assertEqual(queue.report()["budget"]["reserved"], 20)
            self.assertEqual(queue.report()["budget"]["charged_or_settled"], 0)
        response = reply(request)
        response["context_id"] = "other-context"
        self.assert_code("response_binding", queue.finish, claim, request, response)
        queue.finish(claim, request, reply(request, input_tokens=10, output_tokens=5))
        self.assertEqual(queue.report()["budget"]["reserved"], 0)
        self.assertEqual(queue.report()["budget"]["charged_or_settled"], 20)

    def test_request_ceiling_includes_completed_and_uncertain_model_calls(self):
        queue = self.create(count=2, max_model_calls=2)
        first = queue.claim("first")
        completed = queue.begin(first, "model", 0, {})["request"]
        queue.finish(first, completed, reply(completed))
        unresolved = queue.begin(first, "review", 0, {})["request"]
        queue.uncertain(first, unresolved["operation_id"], "unknown")
        other = self.reopen().claim("other")
        self.assert_code("session_budget", queue.begin, other, "model", 0, {})
        self.assertEqual(len(queue.report()["operations"]), 2)

    def test_pre_dispatch_rejection_releases_budget_and_can_retry_same_slot(self):
        queue = self.create(count=1, budget_microusd=20, max_model_calls=1,
                            providers={"a": provider(requests_per_minute=1)})
        claim = queue.claim("worker")
        first = queue.begin(claim, "model", 0, {})["request"]
        queue.not_sent(claim, first["operation_id"], "local_validation")
        self.assertEqual(queue.report()["budget"]["reserved"], 0)
        again = self.reopen().begin(claim, "model", 0, {})["request"]
        self.assertEqual(again["operation_id"], first["operation_id"])
        queue.finish(claim, again, reply(again))
        self.assertEqual(len(queue.report()["operations"]), 1)
        self.assertEqual(queue.report()["budget"]["charged_or_settled"], 4)

    def test_reconciliation_releases_capacity_without_requeue_or_erasing_cost(self):
        queue = self.create(count=2, parallel=1)
        claim = queue.claim("worker")
        request = queue.begin(claim, "model", 0, {})["request"]
        queue.uncertain(claim, request["operation_id"], "unknown")
        self.assert_code("reconciliation_required", queue.resolve_unknown, request["operation_id"],
                         actor="reviewer", evidence_reference="offline-receipt", stopped=False)
        report = queue.resolve_unknown(request["operation_id"], actor="reviewer",
                                       evidence_reference="offline-receipt", stopped=True)
        self.assertEqual(report["budget"]["reserved"], 0)
        self.assertEqual(report["budget"]["charged_or_settled"], 20)
        self.assertEqual(report["counts"]["blocked"], 1)
        following = self.reopen().claim("following")
        self.assertNotEqual(following["job_id"], claim["job_id"])
        self.assertEqual(report["operations"][0]["state"], "settled")

    def test_late_response_remains_reserved_and_cannot_advance_checkpoint(self):
        queue = self.create(count=1)
        claim = queue.claim("worker")
        request = queue.begin(claim, "model", 0, {})["request"]
        self.clock.advance(5)
        self.assert_code("stale_result", queue.finish, claim, request, reply(request))
        for action, args in ((queue.checkpoint, (claim, {})), (queue.release, (claim,)),
                             (queue.complete, (claim, {}))):
            with self.subTest(action=action.__name__):
                self.assert_code("uncertain_execution", action, *args)
        self.assertEqual(queue.report()["budget"]["reserved"], 20)

    def test_observed_overage_is_recorded_honestly_and_pauses_new_sends(self):
        queue = self.create(count=2, budget_microusd=40)
        sent = queue.claim("sent")
        waiting = queue.claim("waiting")
        request = queue.begin(sent, "model", 0, {})["request"]
        queue.uncertain(sent, request["operation_id"], "provider_bill_pending")
        report = queue.resolve_unknown(request["operation_id"], actor="offline-reviewer",
                                       evidence_reference="offline-overage-receipt", stopped=True,
                                       charged_microusd=50)
        self.assertEqual(report["control"], "paused")
        self.assertEqual(report["budget"]["charged_or_settled"], 50)
        self.assertEqual(report["budget"]["reserved"], 0)
        self.assertEqual(report["budget"]["remaining"], 0)
        self.assertEqual(report["budget"]["exceeded_by"], 10)
        self.assertEqual(report["operations"][0]["charged"], 50)
        self.assertEqual(report["counts"]["blocked"], 1)
        reopened = self.reopen()
        self.assertIsNone(reopened.claim("new-worker"))
        self.assert_code("paused", reopened.begin, waiting, "model", 0, {})
        self.assertEqual(len(reopened.report()["operations"]), 1)

    def test_timeout_override_cannot_extend_approved_call_ceiling(self):
        queue = self.create(count=1, call_seconds=5, task_seconds=60)
        claim = queue.claim("worker")
        for value in (0, -1, True, float("nan"), float("inf"), "5"):
            with self.subTest(timeout=value):
                self.assert_code("queue_input", queue.begin, claim, "model", 0, {},
                                 timeout_seconds=value)
        self.assertEqual(queue.report()["operations"], [])
        request = queue.begin(claim, "model", 0, {}, timeout_seconds=59)["request"]
        self.assertLessEqual(request["deadline"] - self.clock(), 5)

    def test_exhausted_task_keeps_bounded_cleanup_without_new_model_allowance(self):
        queue = self.create(count=1, call_seconds=30, task_seconds=1)
        claim = queue.claim("worker")
        # Resume the persisted accounting boundary without spending real time.
        self.sql("UPDATE jobs SET elapsed=1 WHERE id=?", (claim["job_id"],))
        for kind in ("model", "review", "tool"):
            with self.subTest(kind=kind):
                self.assert_code("session_budget", queue.begin, claim, kind, 0, {})
        close = queue.begin(claim, "close", 0, {}, timeout_seconds=99)["request"]
        self.assertEqual(close["deadline"] - self.clock(), 15)
        self.clock.advance(1)
        queue.finish(claim, close, reply(close, billed=False))
        self.assertEqual(queue.report()["budget"]["charged_or_settled"], 0)
        self.assert_code("session_budget", queue.begin, claim, "model", 1, {})

    def test_plan_checkpoint_reply_result_and_event_tampering_are_detected(self):
        queue = self.create(count=1)
        claim = queue.claim("worker")
        self.sql("UPDATE jobs SET checkpoint=?", ('{"changed":true}',))
        self.assert_code("checkpoint_integrity", queue.assert_claim, claim)
        self.sql("UPDATE jobs SET checkpoint='{}'")
        request = queue.begin(claim, "model", 0, {})["request"]
        queue.finish(claim, request, reply(request))
        self.sql("UPDATE operations SET reply=?", ('{"changed":true}',))
        self.assert_code("response_integrity", queue.begin, claim, "model", 0, {})
        self.sql("UPDATE operations SET reply=?", (canonical(reply(request)).decode(),))
        queue.complete(claim, {"outcome": "inconclusive"})
        self.sql("UPDATE jobs SET result=?", ('{"outcome":"passed"}',))
        self.assert_code("result_integrity", queue.report)
        self.sql("UPDATE jobs SET result=?", ('{"outcome":"inconclusive"}',))
        self.sql("UPDATE events SET body='{}' WHERE seq=1")
        self.assert_code("event_integrity", queue.audit_events)
        envelope = json.loads((self.root / "plan.json").read_text())
        envelope["plan"]["limits"]["budget_microusd"] += 1
        (self.root / "plan.json").write_bytes(canonical(envelope))
        self.assert_code("plan_integrity", self.reopen)


if __name__ == "__main__":
    unittest.main()
