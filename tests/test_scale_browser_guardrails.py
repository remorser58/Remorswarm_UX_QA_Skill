"""Owned-driver guardrails; no browser, provider, or product process is started."""
import copy
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock

import _paths
from uxpersonas.scale_browser_host import ScaleBrowserHost, _preserve_driver_hashes


class DriverLogicTests(unittest.TestCase):
    def test_node_guardrail_behavior(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is unavailable; owned-driver unit checks not run")
        scripts = [Path(__file__).with_name(name) for name in ("scale_browser_guardrails.test.mjs", "scale_browser_scroll.test.mjs", "scale_browser_legacy_seed.test.mjs", "scale_browser_lifecycle.test.mjs", "scale_browser_action_deadline.test.mjs")]
        result = subprocess.run([node, "--test", "--test-reporter=tap", *(str(script) for script in scripts)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# fail 0", result.stdout)

    def test_typed_sha256_metadata_survives_free_text_scrubbing(self):
        digest = "1234567890123456" * 4
        original = {
            "storage_snapshot": {"sha256": digest},
            "import_attempt": {"fixture_sha256": digest,
                "storage_before": {"sha256": digest}, "storage_after": {"sha256": digest}},
        }
        cleaned = copy.deepcopy(original)
        cleaned["storage_snapshot"]["sha256"] = "[redacted]"
        cleaned["import_attempt"]["fixture_sha256"] = "[redacted]"
        cleaned["import_attempt"]["storage_before"]["sha256"] = "[redacted]"
        cleaned["import_attempt"]["storage_after"]["sha256"] = "[redacted]"
        _preserve_driver_hashes(original, cleaned)
        self.assertEqual(cleaned, original)
        original["storage_snapshot"]["sha256"] = "private text must not be restored"
        cleaned["storage_snapshot"]["sha256"] = "[redacted]"
        _preserve_driver_hashes(original, cleaned)
        self.assertEqual(cleaned["storage_snapshot"]["sha256"], "[redacted]")


class CompoundHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_compound_uploads_keep_real_facts_and_upload_provenance(self):
        for name in ("upload_cancel", "upload_save_failure"):
            with self.subTest(tool=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                capture = root / "observed.png"
                capture.write_bytes(b"synthetic-driver-unit-evidence")
                capture.chmod(0o600)
                digest = hashlib.sha256(capture.read_bytes()).hexdigest()
                state_digest = "1234567890123456" * 4
                observed = {
                    "text": "Actual bounded result",
                    "facts": {"uploaded_fixture": "owned-sample-current.zip",
                        "storage_snapshot": {"available": True, "keys": ["owned_state_v1"], "sha256": state_digest},
                        "import_attempt_id": "upload-19",
                        "import_attempt": {"attempt_id": "upload-19", "tool": name, "fixture_sha256": state_digest,
                            "storage_before": {"sha256": state_digest}, "storage_after": {"sha256": state_digest},
                            "cancel_dispatched": False, "terminal_state": "already_completed"}},
                    "captures": [{"path": capture.name, "sha256": digest}], "checks": [],
                }
                host = object.__new__(ScaleBrowserHost)
                host.processes = {"context": object()}
                host._exchange = AsyncMock(return_value=observed)
                host._validate_fixture_upload = lambda fixture: None
                request = {"operation_id": "compound-upload", "context_id": "context", "request_sha256": "b" * 64,
                    "payload": {"name": name, "arguments": {"selector": "body>input:nth-of-type(1)",
                        "file": "owned-sample-current.zip"}, "evidence_path": str(root)}}
                reply = await host.call("tool", request)
                facts = reply["result"]["facts"]
                self.assertEqual(facts["fixture_uploads"], ["owned-sample-current.zip"])
                self.assertFalse(facts["import_attempt"]["cancel_dispatched"])
                self.assertEqual(facts["import_attempt"]["terminal_state"], "already_completed")
                self.assertEqual(facts["storage_snapshot"]["sha256"], state_digest)
                self.assertEqual(facts["import_attempt"]["fixture_sha256"], state_digest)
                self.assertEqual(host._exchange.await_count, 1)


if __name__ == "__main__":
    unittest.main()
