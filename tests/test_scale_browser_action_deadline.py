"""Action deadline contract and known-response timing, without browser/model calls."""
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import _paths
from uxpersonas.scale_browser_host import ScaleBrowserHost
import test_scale_browser_lifecycle as lifecycle_fixture

ROOT = Path(__file__).resolve().parents[1]


class ActionDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_drain_and_reply_share_one_exchange_budget(self):
        async def delayed_reply():
            await asyncio.sleep(.03)
            return b'{"id":1,"result":{}}\n'
        async def delayed_drain():
            await asyncio.sleep(.03)
        host, process = lifecycle_fixture.fake_host(AsyncMock(side_effect=delayed_reply))
        host.EXCHANGE_TIMEOUTS["act"] = .05
        process.stdin.drain = AsyncMock(side_effect=delayed_drain)
        with self.assertRaises(TimeoutError) as raised:
            await host._exchange("context", "act", {})
        # Python 3.10's asyncio.TimeoutError is not this built-in type.
        self.assertIs(type(raised.exception), TimeoutError)
        self.assertIn("context", host.poisoned)
        process.stdin.write.assert_called_once()
        process.stdout.readline.assert_awaited_once()

    @patch("uxpersonas.scale_browser_host.asyncio.timeout", None, create=True)
    async def test_action_completion_does_not_swallow_external_cancellation(self):
        host, process = lifecycle_fixture.fake_host(AsyncMock(return_value=
            b'{"id":1,"result":{"text":"ready","facts":{},"captures":[],"checks":[]}}\n'))
        host.EXCHANGE_TIMEOUTS["act"] = 5
        original = host._exchange
        async def exchange(*args):
            result = await original(*args)
            asyncio.get_running_loop().call_soon(caller.cancel)
            return result
        host._exchange = exchange
        with tempfile.TemporaryDirectory() as directory:
            request = dict(operation_id="one-observe", context_id="context", request_sha256="0" * 64,
                payload=dict(name="observe", arguments={}, evidence_path=str(Path(directory).resolve())))
            caller = asyncio.create_task(host.call("tool", request))
            with self.assertRaises(asyncio.CancelledError):
                await caller
        self.assertIn("context", host.poisoned)
        self.assertEqual(host.lifecycle["context"]["error_type"], "CancelledError")
        self.assertEqual(host.context_observations["context"], [])
        with self.assertRaisesRegex(RuntimeError, "transport_uncertain"):
            await original("context", "act", {})
        process.stdin.write.assert_called_once()

    async def test_delayed_single_reply_fits_new_budget_without_redispatch(self):
        # Millisecond-scaled former25s/new90s windows; the same authored reply
        # arrives once after40ms. This is not a claim about R5's blocking step.
        async def delayed():
            await asyncio.sleep(.04)
            return b'{"id":1,"result":{"observed":true}}\n'
        old, old_process = lifecycle_fixture.fake_host(AsyncMock(side_effect=delayed))
        old.EXCHANGE_TIMEOUTS["act"] = .025
        with self.assertRaises(TimeoutError):
            await old._exchange("context", "act", {"name": "observe"})
        self.assertIn("context", old.poisoned)
        old_process.stdin.write.assert_called_once()

        host, process = lifecycle_fixture.fake_host(AsyncMock(side_effect=delayed))
        host.EXCHANGE_TIMEOUTS["act"] = ScaleBrowserHost.EXCHANGE_TIMEOUTS["act"] / 1000
        self.assertEqual(await host._exchange("context", "act", {"name": "observe"}), {"observed": True})
        process.stdin.write.assert_called_once()
        process.stdout.readline.assert_awaited_once()
        self.assertNotIn("context", host.poisoned)
        self.assertGreater(host.lifecycle["context"]["command_elapsed_seconds"], .025)

    async def test_late_response_after_blocked_event_loop_is_not_admitted(self):
        async def late():
            time.sleep(.04)
            return b'{"id":1,"result":{"late":true}}\n'
        host, process = lifecycle_fixture.fake_host(AsyncMock(side_effect=late))
        with self.assertRaises(TimeoutError):
            await host._exchange("context", "act", {"name": "observe"})
        self.assertIn("context", host.poisoned)
        self.assertGreaterEqual(host.lifecycle["context"]["command_elapsed_seconds"], .02)
        self.assertEqual(host.lifecycle["context"]["command_timeout_seconds"], .02)
        process.stdin.write.assert_called_once()

    async def test_driver_deadline_reply_poisons_channel_without_next_dispatch(self):
        host, process = lifecycle_fixture.fake_host(AsyncMock(
            return_value=b'{"id":1,"error":"browser_action_timeout"}\n'))
        with self.assertRaisesRegex(RuntimeError, "browser_action_timeout"):
            await host._exchange("context", "act", {"name": "upload"})
        with self.assertRaisesRegex(RuntimeError, "transport_uncertain"):
            await host._exchange("context", "act", {"name": "observe"})
        process.stdin.write.assert_called_once()
        process.stdout.readline.assert_awaited_once()
        self.assertEqual(host.lifecycle["context"]["error_type"], "DriverActionDeadline")

    async def test_known_click_rejection_and_observe_share_one_action_window(self):
        replies = [
            b'{"id":1,"error":"click_target_not_allowed_or_visible"}\n',
            b'{"id":2,"result":{"text":"late","facts":{},"captures":[],"checks":[]}}\n',
        ]
        async def delayed():
            await asyncio.sleep(.03)
            return replies.pop(0)
        host, process = lifecycle_fixture.fake_host(AsyncMock(side_effect=delayed))
        host.EXCHANGE_TIMEOUTS["act"] = .05
        with tempfile.TemporaryDirectory() as directory:
            request = dict(operation_id="one-click", context_id="context", request_sha256="0" * 64,
                payload=dict(name="click", arguments=dict(selector="#button", label="Safe"),
                    evidence_path=str(Path(directory).resolve())))
            with self.assertRaises(TimeoutError):
                await host.call("tool", request)
        packets = [json.loads(call.args[0]) for call in process.stdin.write.call_args_list]
        self.assertEqual([row["payload"]["name"] for row in packets], ["click", "observe"])
        self.assertIn("context", host.poisoned)
        self.assertEqual(process.stdin.write.call_count, 2)

    async def test_total_action_deadline_rejects_late_second_reply_before_admission(self):
        clock = [0.0]
        replies = [
            b'{"id":1,"error":"click_target_not_allowed_or_visible"}\n',
            b'{"id":2,"result":{"text":"late","facts":{},"captures":[],"checks":[]}}\n',
        ]
        async def reply():
            clock[0] += .06
            return replies.pop(0)
        host, process = lifecycle_fixture.fake_host(AsyncMock(side_effect=reply))
        host.EXCHANGE_TIMEOUTS["act"] = .09
        fake_time = SimpleNamespace(monotonic=lambda: clock[0], time=time.time)
        with tempfile.TemporaryDirectory() as directory, \
             patch("uxpersonas.scale_browser_host.time", fake_time):
            request = dict(operation_id="one-click", context_id="context", request_sha256="0" * 64,
                payload=dict(name="click", arguments=dict(selector="#button", label="Safe"),
                    evidence_path=str(Path(directory).resolve())))
            with self.assertRaisesRegex(TimeoutError, "action_window_after_deadline"):
                await host.call("tool", request)
        self.assertEqual(process.stdin.write.call_count, 2)
        self.assertIn("context", host.poisoned)
        self.assertEqual(host.context_observations["context"], [])
        self.assertEqual(host.lifecycle["context"]["error_type"], "ActionWindowTimeout")
        self.assertAlmostEqual(host.lifecycle["context"]["action_elapsed_seconds"], .12)
        self.assertAlmostEqual(host.lifecycle["context"]["command_elapsed_seconds"], .06)

    async def test_expired_shared_window_does_not_dispatch_followup_observe(self):
        clock = [0.0]
        async def reply():
            clock[0] = .06
            return b'{"id":1,"error":"click_target_not_allowed_or_visible"}\n'
        host, process = lifecycle_fixture.fake_host(AsyncMock(side_effect=reply))
        host.EXCHANGE_TIMEOUTS["act"] = .09
        original = host._exchange
        async def exchange(*args):
            try:
                return await original(*args)
            except RuntimeError:
                clock[0] = .12
                raise
        host._exchange = exchange
        fake_time = SimpleNamespace(monotonic=lambda: clock[0], time=time.time)
        with tempfile.TemporaryDirectory() as directory, \
             patch("uxpersonas.scale_browser_host.time", fake_time):
            request = dict(operation_id="one-click", context_id="context", request_sha256="0" * 64,
                payload=dict(name="click", arguments=dict(selector="#button", label="Safe"),
                    evidence_path=str(Path(directory).resolve())))
            with self.assertRaisesRegex(TimeoutError, "action_window_after_deadline"):
                await host.call("tool", request)
        process.stdin.write.assert_called_once()
        self.assertIn("context", host.poisoned)
        self.assertEqual(host.context_observations["context"], [])


class Python310ActionDeadlineTests(ActionDeadlineTests):
    """Exercise the missing-asyncio.timeout path even on newer CI interpreters."""
    def setUp(self):
        missing_timeout = patch("uxpersonas.scale_browser_host.asyncio.timeout", None, create=True)
        missing_timeout.start()
        self.addCleanup(missing_timeout.stop)


class PhaseBudgetContractTests(unittest.TestCase):
    def test_actual_driver_host_and_live_queue_budgets_fit_one_first_tool_call(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable: driver deadline contract not executed")
        driver = ROOT / "skills/remorsearch-ux-qa/drivers/web/scale_browser_cdp.mjs"
        code = "import {DRIVER_DEADLINES_MS as d} from " + json.dumps(driver.as_uri()) + ";console.log(JSON.stringify(d));"
        result = subprocess.run([node, "--input-type=module", "-e", code],
            capture_output=True, text=True, check=True, timeout=10)
        deadlines = json.loads(result.stdout)
        spec = importlib.util.spec_from_file_location("live_deadline_contract",
            ROOT / "skills/remorsearch-ux-qa/scripts/live_scale_browser.py")
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        limits = live.live_limits(32, 80)
        host = ScaleBrowserHost.EXCHANGE_TIMEOUTS
        self.assertLess(host["start"] + host["act"], limits.call_seconds)
        self.assertLess((deadlines["start"] + deadlines["reply"]) / 1000 + 2, host["start"])
        self.assertLess((deadlines["act"] + deadlines["reply"]) / 1000 + 2, host["act"])
        self.assertEqual(limits.call_seconds, 180)
        self.assertEqual(host["act"], 90)
        self.assertEqual(deadlines["act"], 80000)


if __name__ == "__main__":
    unittest.main()
