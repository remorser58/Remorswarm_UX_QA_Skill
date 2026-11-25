"""Current evidence readback never turns historical completion into fresh proof."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import _paths
import test_scale_run as support
from uxpersonas.library import Library
from uxpersonas.scale_report import current_report
from uxresearch.canonical import canonical, digest
from uxresearch.storage import atomic


class CurrentScaleReportTests(unittest.IsolatedAsyncioTestCase):
    setUp = support.ScaleRunTests.setUp
    run_scale = support.ScaleRunTests.run_scale

    async def completed(self):
        report = await self.run_scale()
        self.assertEqual(report["evidence_validation"]["current_valid_sessions"], 2, report)
        self.assertEqual(report["evidence_validation"]["blocked_sessions"], 0)
        self.assertEqual(report["evidence_validation"]["ux_outcomes"]["passed"], 1)
        self.assertEqual(report["evidence_validation"]["ux_outcomes"]["failed"], 1)
        return report

    def assert_history_kept(self, before, after):
        self.assertEqual([r["result"] for r in before["tasks"]],
                         [r["result"] for r in after["tasks"]])
        self.assertEqual(before["counts"], after["counts"])
        self.assertEqual(before["event_chain_head"], after["event_chain_head"])

    async def test_changed_png_blocks_current_outcome_without_dispatch(self):
        before = await self.completed()
        row = before["tasks"][0]
        result = row["result"]
        artifact = next(a for a in result["receipt"]["artifacts"] if a["kind"] == "screenshot")
        path = Path(result["evidence_root"]) / artifact["path"]
        atomic(path, b"Changed PNG bytes")
        calls = len(self.host.calls)
        after = await self.run_scale()
        self.assertEqual(calls, len(self.host.calls))
        self.assert_history_kept(before, after)
        self.assertFalse(after["tasks"][0]["current_valid"])
        self.assertIsNone(after["tasks"][0]["current_ux_outcome"])
        self.assertEqual(after["tasks"][0]["current_issue"]["code"], "evidence_integrity")
        self.assertEqual(after["evidence_validation"]["blocked_sessions"], 1)
        self.assertEqual(sum(after["evidence_validation"]["ux_outcomes"].values()), 1)

    async def test_changed_prd_preserves_historical_results_but_excludes_current_outcomes(self):
        before = await self.completed()
        atomic(self.root / "PRD.md", b"Changed product requirements")
        calls = len(self.host.calls)
        after = current_report(self.queue)
        self.assertEqual(calls, len(self.host.calls))
        self.assert_history_kept(before, after)
        self.assertEqual(after["evidence_validation"]["blocked_sessions"], 2)
        self.assertEqual(after["evidence_validation"]["current_valid_sessions"], 0)
        self.assertEqual(sum(after["evidence_validation"]["ux_outcomes"].values()), 0)
        self.assertTrue(all(r["current_issue"]["code"] == "stale_prd" for r in after["tasks"]))

    async def test_retired_profile_blocks_only_its_current_result(self):
        before = await self.completed()
        with Library(self.root / "library") as library:
            library.retire("agent-fixture", "PER-RETURN", "Fixture retirement after review")
        calls = len(self.host.calls)
        after = current_report(self.queue)
        self.assertEqual(calls, len(self.host.calls))
        self.assert_history_kept(before, after)
        retired = next(r for r in after["tasks"] if r["persona_id"] == "PER-RETURN")
        self.assertFalse(retired["current_valid"])
        self.assertEqual(retired["current_issue"]["code"], "persona_retired")
        self.assertEqual(after["evidence_validation"]["ux_outcomes"]["failed"], 0)
        self.assertEqual(after["evidence_validation"]["ux_outcomes"]["passed"], 1)

    async def test_changed_build_blocks_current_evidence(self):
        before = await self.completed()
        atomic(self.root / "build.txt", b"Another build")
        after = current_report(self.queue)
        self.assert_history_kept(before, after)
        self.assertEqual(after["evidence_validation"]["blocked_sessions"], 2)
        self.assertTrue(all(r["current_issue"]["code"] == "stale_build" for r in after["tasks"]))

    async def test_first_judgment_seal_is_revalidated_beyond_bookkeeping_hash(self):
        before = await self.completed()
        row = before["tasks"][0]
        result = copy.deepcopy(row["result"])
        result["first_judgment"]["reason"] = "Changed after sealing"
        with self.queue._db(write=True) as db:
            db.execute("UPDATE jobs SET result=?,result_sha=? WHERE id=?",
                       (canonical(result).decode(), digest(result), row["job_id"]))
        after = current_report(self.queue)
        self.assertFalse(after["tasks"][0]["current_valid"])
        self.assertEqual(after["tasks"][0]["current_issue"]["code"], "judgment_integrity")

    async def test_error_details_never_echo_private_paths(self):
        await self.completed()
        with patch("uxpersonas.scale_report._receipt", side_effect=OSError("/private/user/secret-source")):
            report = current_report(self.queue)
        for row in report["tasks"]:
            self.assertFalse(row["current_valid"])
            self.assertNotIn("/private", json.dumps(row["current_issue"]))
            self.assertEqual(row["current_issue"]["code"], "current_validation_failed")

    async def test_queued_jobs_remain_unassessed_without_source_access(self):
        with patch("uxpersonas.scale_report._library_view", side_effect=AssertionError("No source access expected")):
            report = current_report(self.queue)
        self.assertEqual(report["evidence_validation"]["unassessed_sessions"], 2)
        self.assertEqual(report["evidence_validation"]["current_valid_sessions"], 0)
        self.assertTrue(all(row["current_valid"] is None for row in report["tasks"]))
        self.assertFalse(self.host.calls)


if __name__ == "__main__":
    unittest.main()

