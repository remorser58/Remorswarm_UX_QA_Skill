"""Transport uncertainty and owned teardown regressions; no model or browser."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import _paths
from uxpersonas.scale_browser_host import ScaleBrowserHost

ROOT = Path(__file__).resolve().parents[1]


def fake_host(stdout):
    host = object.__new__(ScaleBrowserHost)
    for name in ("processes", "locks", "context_paths", "serials", "context_tasks",
                 "context_uploads", "context_observations", "context_fixture_validation",
                 "context_seed_attempts", "owned_groups", "lifecycle"):
        setattr(host, name, {})
    host.poisoned, host.closed_contexts = set(), set()
    process = SimpleNamespace(pid=987654, returncode=None,
        stdin=SimpleNamespace(write=Mock(), drain=AsyncMock()),
        stdout=SimpleNamespace(readline=stdout), wait=AsyncMock(return_value=0))
    host.processes["context"] = process
    host.owned_groups["context"] = process.pid
    host.EXCHANGE_TIMEOUTS = {"start": .02, "act": .02, "close": .02}
    return host, process


def close_request():
    return dict(operation_id="close-owned", context_id="context",
                request_sha256="0" * 64, payload={})


class HostLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_reply_is_never_consumed_and_close_uses_owned_cleanup(self):
        async def stalled():
            await asyncio.sleep(60)
        host, process = fake_host(AsyncMock(side_effect=stalled))
        with self.assertRaises(TimeoutError):
            await host._exchange("context", "act", {"name": "observe"})
        process.stdout.readline = AsyncMock(return_value=b'{"id":1,"result":{"late":true}}\n')
        with self.assertRaisesRegex(RuntimeError, "transport_uncertain"):
            await host._exchange("context", "act", {"name": "observe"})
        process.stdout.readline.assert_not_awaited()
        self.assertEqual(process.stdin.write.call_count, 1)
        host._wait_owned_exit = AsyncMock(return_value=False)
        host._terminate_owned = AsyncMock(return_value=True)
        reply = await host.call("close", close_request())
        self.assertTrue(reply["result"]["stopped"])
        self.assertEqual(reply["result"], {"stopped": True})
        self.assertTrue(host.lifecycle["context"]["shutdown"]["forced_cleanup"])
        self.assertEqual(process.stdin.write.call_count, 1)
        self.assertNotIn("context", host.processes)
        self.assertIn("context", host.closed_contexts)
        with self.assertRaisesRegex(RuntimeError, "context_closed"):
            await host._exchange("context", "start", {})

    async def test_failed_teardown_keeps_ownership_and_cannot_resume(self):
        host, process = fake_host(AsyncMock())
        host.poisoned.add("context")
        host._wait_owned_exit = AsyncMock(return_value=False)
        host._terminate_owned = AsyncMock(return_value=False)
        self.assertFalse(await host.shutdown())
        self.assertIs(host.processes["context"], process)
        self.assertEqual(host.owned_groups["context"], process.pid)
        self.assertFalse(host.can_resume("context", []))
        self.assertEqual(host.lifecycle["context"]["phase"], "shutdown_unconfirmed")
        process.stdin.write.assert_not_called()

    async def test_missing_group_ownership_never_signals_any_pid(self):
        host, process = fake_host(AsyncMock())
        host.owned_groups.clear()
        with patch("uxpersonas.scale_browser_host.os.killpg") as kill:
            self.assertFalse(await host._terminate_owned("context"))
        kill.assert_not_called()

    async def test_cancellation_after_dispatch_poisons_channel(self):
        async def cancelled():
            raise asyncio.CancelledError()
        host, process = fake_host(AsyncMock(side_effect=cancelled))
        with self.assertRaises(asyncio.CancelledError):
            await host._exchange("context", "act", {})
        self.assertIn("context", host.poisoned)
        self.assertEqual(process.stdin.write.call_count, 1)

    async def test_identity_mismatch_poisons_but_known_driver_rejection_does_not(self):
        host, process = fake_host(AsyncMock(return_value=b'{"id":99,"result":{}}\n'))
        with self.assertRaisesRegex(RuntimeError, "identity_mismatch"):
            await host._exchange("context", "act", {})
        self.assertIn("context", host.poisoned)
        host, process = fake_host(AsyncMock(return_value=b'{"id":1,"error":"click_target_not_allowed_or_visible"}\n'))
        with self.assertRaisesRegex(RuntimeError, "click_target_not_allowed_or_visible"):
            await host._exchange("context", "act", {})
        self.assertNotIn("context", host.poisoned)

    @patch("uxpersonas.scale_browser_host.asyncio.timeout", None, create=True)
    async def test_external_cancellation_drains_reader_even_if_cleanup_raises(self):
        for cleanup_error in (False, True):
            with self.subTest(cleanup_error=cleanup_error):
                entered, drained = asyncio.Event(), asyncio.Event()
                readers = []
                async def stalled():
                    readers.append(asyncio.current_task())
                    entered.set()
                    try:
                        await asyncio.Future()
                    finally:
                        drained.set()
                        if cleanup_error:
                            raise RuntimeError("reader_cleanup_failed")
                host, process = fake_host(AsyncMock(side_effect=stalled))
                host.EXCHANGE_TIMEOUTS["act"] = 5
                caller = asyncio.create_task(host._exchange("context", "act", {}))
                await asyncio.wait_for(entered.wait(), 1)
                caller.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await caller
                self.assertTrue(drained.is_set())
                self.assertTrue(all(task.done() for task in readers))
                self.assertIn("context", host.poisoned)
                self.assertEqual(host.lifecycle["context"]["error_type"], "CancelledError")
                with self.assertRaisesRegex(RuntimeError, "transport_uncertain"):
                    await host._exchange("context", "act", {})
                process.stdin.write.assert_called_once()

    @patch("uxpersonas.scale_browser_host.asyncio.timeout", None, create=True)
    async def test_external_cancellation_wins_concurrent_reply_completion(self):
        entered, release = asyncio.Event(), asyncio.Event()
        readers = []
        async def reply():
            readers.append(asyncio.current_task())
            entered.set()
            await release.wait()
            return b'{"id":1,"result":{}}\n'
        host, process = fake_host(AsyncMock(side_effect=reply))
        host.EXCHANGE_TIMEOUTS["act"] = 5
        caller = asyncio.create_task(host._exchange("context", "act", {}))
        await asyncio.wait_for(entered.wait(), 1)
        release.set()
        # Finish the reader, then cancel its caller before result admission.
        asyncio.get_running_loop().call_soon(caller.cancel)
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(all(task.done() for task in readers))
        self.assertIn("context", host.poisoned)
        self.assertEqual(host.lifecycle["context"]["error_type"], "CancelledError")
        with self.assertRaisesRegex(RuntimeError, "transport_uncertain"):
            await host._exchange("context", "act", {})
        process.stdin.write.assert_called_once()

    async def test_stdin_backpressure_is_bounded_and_not_replayed(self):
        host, process = fake_host(AsyncMock())
        async def stalled():
            await asyncio.sleep(60)
        process.stdin.drain = AsyncMock(side_effect=stalled)
        with self.assertRaises(TimeoutError):
            await host._exchange("context", "act", {})
        self.assertIn("context", host.poisoned)
        process.stdout.readline.assert_not_awaited()

    @unittest.skipUnless(os.name == "posix", "Owned process groups require POSIX")
    async def test_real_owned_descendant_group_is_gone_after_poisoned_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fixtures = root / "fixtures"; fixtures.mkdir()
            (fixtures / "fixture-manifest.json").write_text('{"files":[]}')
            evidence = root / "evidence"; evidence.mkdir()
            driver = root / "fake_driver.py"
            driver.write_text(
                "import sys,json,subprocess,time\n"
                "from pathlib import Path\n"
                "for line in sys.stdin:\n"
                " p=json.loads(line)\n"
                " if p['kind']=='start':\n"
                "  c=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])\n"
                "  Path('child.pid').write_text(str(c.pid))\n"
                "  print(json.dumps({'id':p['id'],'result':{'started':True}}),flush=True)\n"
                " else: time.sleep(60)\n")
            host = ScaleBrowserHost(target_url="http://127.0.0.1:4175/",
                chrome=sys.executable, node=sys.executable, driver_path=driver,
                adapter_path=Path(__file__), fixtures_path=fixtures)
            host.EXCHANGE_TIMEOUTS = {"start": 5, "act": .1, "close": .1}
            host.TERMINATE_SECONDS, host.KILL_SECONDS = .2, 3
            try:
                await host._exchange("context", "start", {"evidence_path": str(evidence)})
                pgid = host.owned_groups["context"]
                self.assertEqual(os.getpgid(host.processes["context"].pid), pgid)
                with self.assertRaises(TimeoutError):
                    await host._exchange("context", "act", {"name": "observe"})
                result = await host.call("close", close_request())
                self.assertEqual(result["result"], {"stopped": True})
                self.assertTrue(host.lifecycle["context"]["shutdown"]["owned_group_exit_confirmed"])
                with self.assertRaises(ProcessLookupError):
                    os.killpg(pgid, 0)
                record = json.loads((evidence / "browser-host-lifecycle.json").read_text())
                self.assertEqual(record["phase"], "closed")
                self.assertTrue(record["channel_poisoned"])
            finally:
                if host.processes:
                    await host.shutdown()


class FailurePreservationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        path = ROOT / "skills/remorsearch-ux-qa/scripts/live_scale_browser.py"
        spec = importlib.util.spec_from_file_location("live_lifecycle_test", path)
        self.live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.live)

    async def test_diagnostic_disk_error_does_not_mask_original_execution_failure(self):
        host = SimpleNamespace(shutdown=AsyncMock(return_value=False),
                               lifecycle={}, processes={"ctx": object()})
        router = SimpleNamespace(report=lambda: {"events": []})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.object(self.live, "execute_scale", AsyncMock(side_effect=ValueError("original"))), \
                 patch.object(self.live, "atomic", side_effect=OSError("disk-error")) as write:
                with self.assertRaisesRegex(ValueError, "original"):
                    await self.live._execute_with_shutdown(root, {}, host, router)
                self.assertEqual(write.call_count, 2)
            host.shutdown.assert_awaited_once()

    async def test_shutdown_cancellation_is_recorded_then_reraised(self):
        host = SimpleNamespace(shutdown=AsyncMock(side_effect=asyncio.CancelledError()),
                               lifecycle={}, processes={"ctx": object()})
        router = SimpleNamespace(report=lambda: {"events": []})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.object(self.live, "execute_scale", AsyncMock(return_value={"tasks": []})):
                with self.assertRaises(asyncio.CancelledError):
                    await self.live._execute_with_shutdown(root, {}, host, router)
            saved = json.loads((root / "browser-lifecycle-summary.json").read_text())
            self.assertEqual(saved["shutdown_error"]["type"], "CancelledError")
            self.assertTrue((root / "report.json").is_file())

    async def test_shutdown_failure_keeps_received_report_and_ledger(self):
        host = SimpleNamespace(shutdown=AsyncMock(return_value=False),
                               lifecycle={"ctx": {"phase": "shutdown_unconfirmed"}},
                               processes={"ctx": object()})
        router = SimpleNamespace(report=lambda: {"events": [{"delivery_state": "uncertain"}]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            report = {"counts": {"uncertain": 2}, "tasks": []}
            with patch.object(self.live, "execute_scale", AsyncMock(return_value=report)):
                with self.assertRaisesRegex(RuntimeError, "browser_shutdown_unconfirmed"):
                    await self.live._execute_with_shutdown(root, {}, host, router)
            self.assertEqual(json.loads((root / "report.json").read_text()), report)
            self.assertTrue((root / "model-router-ledger.json").is_file())
            saved = json.loads((root / "browser-lifecycle-summary.json").read_text())
            self.assertEqual(saved["unclosed_contexts"], ["ctx"])
            self.assertFalse(saved["browser_shutdown_confirmed"])
            self.assertIsNone(saved["execution_error"])

    async def test_original_execution_error_survives_failed_shutdown(self):
        host = SimpleNamespace(shutdown=AsyncMock(side_effect=RuntimeError("teardown-error")),
                               lifecycle={}, processes={"ctx": object()})
        router = SimpleNamespace(report=lambda: {"events": []})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.object(self.live, "execute_scale", AsyncMock(side_effect=ValueError("original-tool-error"))):
                with self.assertRaisesRegex(ValueError, "original-tool-error"):
                    await self.live._execute_with_shutdown(root, {}, host, router)
            self.assertFalse((root / "report.json").exists())
            saved = json.loads((root / "browser-lifecycle-summary.json").read_text())
            self.assertEqual(saved["execution_error"]["reason"], "original-tool-error")
            self.assertEqual(saved["shutdown_error"]["reason"], "teardown-error")


if __name__ == "__main__":
    unittest.main()
