"""Real Queue/ScaleExecution close contract, with authored IO and no browser/model."""
import unittest
from unittest.mock import AsyncMock

import test_scale_run as scale_fixture
import test_scale_browser_lifecycle as lifecycle_fixture


class BrowserCloseContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Composition avoids rediscovering/inheriting the existing scale suite.
        self.fixture = scale_fixture.ScaleRunTests(
            "test_two_independent_sessions_preserve_failure_and_reuse_completed_report")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.closed = []

    def route_real_browser_close(self, *, group_gone):
        original = self.fixture.host.call

        async def call(kind, request):
            if kind != "close":
                return await original(kind, request)
            host, process = lifecycle_fixture.fake_host(AsyncMock(
                return_value=b'{"id":1,"result":{"stopped":true,"browser_stopped":true,"proxy_stopped":true}}\n'))
            context = request["context_id"]
            host.processes[context] = host.processes.pop("context")
            host.owned_groups[context] = host.owned_groups.pop("context")
            # Fake OS ownership/exit facts only. The real call(), _exchange(),
            # response contract, queue dispatch and receipt finalization all run.
            host._group_alive = lambda value: not group_gone

            async def exited():
                process.returncode = 0
                return 0

            process.wait = AsyncMock(side_effect=exited)
            if not group_gone:
                host._terminate_owned = AsyncMock(return_value=False)
            reply = await host.call("close", request)
            self.closed.append((request, reply, host, process))
            return reply

        self.fixture.host.call = call

    async def test_confirmed_real_host_close_finalizes_two_current_valid_sessions(self):
        self.route_real_browser_close(group_gone=True)
        report = await self.fixture.run_scale()
        self.assertEqual(report["counts"]["complete"], 2, report["counts"])
        self.assertEqual(report["counts"]["blocked"], 0)
        self.assertEqual(report["counts"]["uncertain"], 0)
        self.assertEqual(len(self.closed), 2)
        self.assertEqual(len({row[0]["context_id"] for row in self.closed}), 2)
        for row in report["tasks"]:
            self.assertIsNone(row["problem"])
            self.assertTrue(row["current_valid"])
            self.assertTrue(row["result"]["operational_completed"])
            self.assertTrue(row["result"]["receipt"]["artifacts"])
        for request, reply, host, process in self.closed:
            context = request["context_id"]
            self.assertEqual(reply["result"], {"stopped": True})
            self.assertEqual(reply["operation_id"], request["operation_id"])
            self.assertEqual(reply["request_sha256"], request["request_sha256"])
            self.assertEqual(host.lifecycle[context]["phase"], "closed")
            self.assertEqual(host.lifecycle[context]["shutdown"], {
                "stopped": True, "driver_shutdown_confirmed": True,
                "owned_group_exit_confirmed": True, "forced_cleanup": False,
            })
            self.assertNotIn(context, host.processes)
            self.assertIn(context, host.closed_contexts)
            process.stdin.write.assert_called_once()
            process.stdout.readline.assert_awaited_once()
        closes = [row for row in report["operations"] if row["kind"] == "close"]
        self.assertEqual(len(closes), 2)
        self.assertTrue(all(row["state"] == "done" for row in closes))
        again = await self.fixture.run_scale()
        self.assertEqual(again, report)
        self.assertEqual(len(self.closed), 2, "Readback must not dispatch close again")

    async def test_unconfirmed_group_stays_blocked_with_ownership_retained(self):
        self.route_real_browser_close(group_gone=False)
        report = await self.fixture.run_scale()
        self.assertEqual(report["counts"]["complete"], 0)
        self.assertEqual(report["counts"]["blocked"], 2)
        self.assertEqual(len(self.closed), 2)
        self.assertTrue(all(row["problem"] == "worker_stop_unconfirmed" for row in report["tasks"]))
        for request, reply, host, process in self.closed:
            context = request["context_id"]
            self.assertEqual(reply["result"], {"stopped": False})
            self.assertIs(host.processes[context], process)
            self.assertEqual(host.lifecycle[context]["phase"], "shutdown_unconfirmed")
            self.assertFalse(host.lifecycle[context]["shutdown"]["owned_group_exit_confirmed"])
            self.assertNotIn(context, host.closed_contexts)


if __name__ == "__main__":
    unittest.main()

