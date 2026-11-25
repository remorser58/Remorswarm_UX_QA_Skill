"""Keep capture cleanup authority in committed state, using offline fixtures."""
from __future__ import annotations

import copy
import unittest

import test_persona_persistence_swarm_regression_20261111 as retention_fixture
from uxresearch.storage import Store, atomic, canonical


class CaptureRetentionAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = retention_fixture.CaptureRetentionPersistenceRegressionTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def assert_pending_status_preserves_payload(self, status):
        fixture = self.fixture
        pending = copy.deepcopy(fixture.bundle)
        pending["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = status
        atomic(fixture.research / "bundle.json", canonical(pending))
        before = (fixture.library_path / "library.json").read_bytes()
        self.assertEqual(fixture.assert_assignment_blocked(), "retention_review_pending")

        code, result = fixture.prune_cli()

        self.assertEqual(code, 1)
        self.assertEqual(result["result"], "blocked")
        self.assertFalse(result["library_cleanup_complete"])
        self.assertEqual(result["retired"], [])
        self.assertEqual(result["blockers"][0]["code"], "retention_review_pending")
        self.assertEqual((fixture.library_path / "library.json").read_bytes(), before)
        self.assertEqual(
            [row["revision"] for row in fixture.persisted_history() if "profile" in row],
            [1, 2],
        )
        with Store(fixture.research) as store:
            self.assertEqual(store.committed("bundle.json"), fixture.bundle)

    def test_uncommitted_capture_deleted_does_not_authorize_erasure(self):
        self.assert_pending_status_preserves_payload("deleted")

    def test_uncommitted_capture_redacted_does_not_authorize_erasure(self):
        self.assert_pending_status_preserves_payload("redacted")

    def test_committed_capture_withdrawal_is_not_reversed_by_retained_mirror(self):
        fixture = self.fixture
        confirmed = copy.deepcopy(fixture.bundle)
        confirmed["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "withdrawn"
        fixture.committed_update(confirmed)
        atomic(fixture.research / "bundle.json", canonical(fixture.bundle))

        fixture.assert_cleanup_removed_both_revisions()

        with Store(fixture.research) as store:
            self.assertEqual(store.committed("bundle.json"), confirmed)


if __name__ == "__main__":
    unittest.main()

