import copy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from loop_factory import ROOT, SKILL, make_packet
from uxloop.engine import report, run
from uxloop.io import ContractError, GateStop, code_snapshot, digest
from uxloop.patching import finish_intent
from uxloop.rollback import _plan, apply, preview, validate_pending
from uxloop.storage import event, load, save


class RollbackTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".ux-loop").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".ux-loop")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "site"
        self.workspace.mkdir()
        self.evidence = self.root / "evidence"
        self.checkpoint = self.root / "checkpoint.json"
        shutil.copy2(SKILL / "examples/loop/site/index.html", self.workspace / "index.html")
        self.original = (self.workspace / "index.html").read_bytes()
        self.packet = make_packet(self.evidence)
        self.state = run(self.packet, self.checkpoint, self.workspace, self.evidence,
                         grants=["code_write"], actor="fixture-owner", reason="owned fixture")
        self.assertEqual(self.state["status"], "complete")

    def undo(self, proposal=None, ids=None):
        ids = ids or ["fix-1"]
        proposal = proposal or preview(self.checkpoint, ids)
        return apply(self.checkpoint, ids, proposal["confirmation_sha256"],
                     actor="fixture-owner", reason="explicit selected rollback")

    def test_preview_is_read_only_and_restore_invalidates_acceptance(self):
        before = self.checkpoint.read_bytes()
        changed = (self.workspace / "index.html").read_bytes()
        proposal = preview(self.checkpoint, ["fix-1"])
        self.assertEqual(self.checkpoint.read_bytes(), before)
        self.assertEqual((self.workspace / "index.html").read_bytes(), changed)
        result = self.undo(proposal)
        self.assertEqual(result["status"], "rolled_back")
        self.assertEqual((self.workspace / "index.html").read_bytes(), self.original)
        state = load(self.checkpoint)
        self.assertEqual(state["accepted_fix_ids"], [])
        self.assertEqual(report(state)["improvements"][0]["status"], "reverted")
        self.assertFalse(report(state)["product_complete"])
        resumed = run(None, self.checkpoint)
        self.assertEqual(resumed["status"], "blocked")
        self.assertEqual((self.workspace / "index.html").read_bytes(), self.original)

    def test_original_contents_are_not_exposed_in_public_report(self):
        value = report(self.state)
        self.assertTrue(value["improvements"][0]["rollback_available"])
        self.assertEqual(value["improvements"][0]["reason"], self.packet["fixes"][0]["rationale"])
        self.assertEqual(value["improvements"][0]["replay_ids"], ["replay-set-1"])
        self.assertNotIn("rollback_snapshot", value["applied_fixes"][0])

    def test_wrong_or_absent_confirmation_never_writes(self):
        before = (self.workspace / "index.html").read_bytes()
        for confirmation in ("", "0" * 64):
            with self.assertRaises(GateStop):
                apply(self.checkpoint, ["fix-1"], confirmation, actor="owner", reason="test")
        self.assertEqual((self.workspace / "index.html").read_bytes(), before)

    def test_unrecorded_edit_is_preserved(self):
        proposal = preview(self.checkpoint, ["fix-1"])
        (self.workspace / "index.html").write_text("independent human edit\n")
        with self.assertRaises(GateStop):
            self.undo(proposal)
        self.assertEqual((self.workspace / "index.html").read_text(), "independent human edit\n")

    def test_checkpoint_change_expires_confirmation(self):
        proposal = preview(self.checkpoint, ["fix-1"])
        state = load(self.checkpoint)
        event(state, state["phase"], "interrupted", "Review changed")
        save(self.checkpoint, state)
        with self.assertRaises(GateStop):
            self.undo(proposal)
        self.assertNotEqual((self.workspace / "index.html").read_bytes(), self.original)

    def test_revoked_code_permission_blocks_rollback(self):
        state = load(self.checkpoint)
        state["permissions"].pop("code_write")
        save(self.checkpoint, state)
        proposal = preview(self.checkpoint, ["fix-1"])
        self.assertTrue(proposal["requires_code_write"])
        with self.assertRaises(GateStop):
            self.undo(proposal)

    def test_legacy_receipt_cannot_claim_rollback(self):
        state = load(self.checkpoint)
        state["applied_fixes"][0].pop("rollback_snapshot")
        save(self.checkpoint, state)
        self.assertFalse(report(state)["improvements"][0]["rollback_available"])
        with self.assertRaises(GateStop):
            preview(self.checkpoint, ["fix-1"])

    def test_snapshot_corruption_blocks_before_write(self):
        state = load(self.checkpoint)
        state["applied_fixes"][0]["rollback_snapshot"]["before_files"]["index.html"] = "wrong\n"
        save(self.checkpoint, state)
        with self.assertRaises(ContractError):
            preview(self.checkpoint, ["fix-1"])

    def test_interrupt_after_file_write_resumes_original_selection(self):
        proposal = preview(self.checkpoint, ["fix-1"])

        def crash_after_write(workspace, intent):
            finish_intent(workspace, intent)
            raise KeyboardInterrupt()

        with patch("uxloop.rollback.finish_intent", side_effect=crash_after_write):
            with self.assertRaises(KeyboardInterrupt):
                self.undo(proposal)
        state = load(self.checkpoint)
        self.assertIsNotNone(state["pending_rollback"])
        self.assertEqual((self.workspace / "index.html").read_bytes(), self.original)
        self.assertTrue(preview(self.checkpoint, ["fix-1"])["pending"])
        self.assertEqual(self.undo(proposal)["status"], "rolled_back")
        self.assertEqual(len(load(self.checkpoint)["rollback_events"]), 1)

    def test_duplicate_unknown_and_repeated_selection_rejected(self):
        for ids in ([], ["fix-1", "fix-1"], ["unknown"]):
            with self.assertRaises(ContractError):
                preview(self.checkpoint, ids)
        self.undo()
        with self.assertRaises(ContractError):
            preview(self.checkpoint, ["fix-1"])

    def test_symlink_checkpoint_rejected(self):
        linked = self.root / "linked.json"
        linked.symlink_to(self.checkpoint)
        with self.assertRaises(ContractError):
            preview(linked, ["fix-1"])

    def test_workspace_lock_excludes_simultaneous_writer(self):
        from uxloop.storage import lock
        with lock(self.workspace / ".ux-loop/workspace.lock"):
            with self.assertRaises(GateStop):
                preview(self.checkpoint, ["fix-1"])

    def test_dependent_later_fix_must_be_explicitly_selected(self):
        state = copy.deepcopy(self.state)
        original = self.original.decode()
        first = (self.workspace / "index.html").read_text()
        later = first + "\n<!-- later improvement -->\n"
        (self.workspace / "index.html").write_text(later)
        fix2 = {**state["packet"]["fixes"][0], "id": "fix-2"}
        state["packet"]["fixes"].append(fix2)
        body = {"before_files": {"index.html": first}, "after_files": {"index.html": later}}
        state["applied_fixes"].append({"fix_id": "fix-2", "rollback_snapshot": {**body, "sha256": digest(body)}})
        with self.assertRaises(GateStop) as error:
            _plan(state, ["fix-1"])
        self.assertIn("fix-2", str(error.exception))
        proposal, intent = _plan(state, ["fix-1", "fix-2"])
        self.assertEqual(proposal["fix_ids"], ["fix-1", "fix-2"])
        finish_intent(self.workspace, intent)
        self.assertEqual((self.workspace / "index.html").read_text(), original)

    def test_independent_file_is_preserved(self):
        state = copy.deepcopy(self.state)
        state["packet"]["goal"]["code_paths"].append("unrelated.css")
        (self.workspace / "unrelated.css").write_text(".brand { color: blue; }\n")
        _, intent = _plan(state, ["fix-1"])
        finish_intent(self.workspace, intent)
        self.assertEqual((self.workspace / "index.html").read_bytes(), self.original)
        self.assertEqual((self.workspace / "unrelated.css").read_text(), ".brand { color: blue; }\n")

    def test_multifile_selection_blocks_before_any_content_write(self):
        state = copy.deepcopy(self.state)
        state["packet"]["goal"]["code_paths"].append("second.css")
        state["packet"]["fixes"][0]["changed_paths"].append("second.css")
        (self.workspace / "second.css").write_text("after\n")
        receipt = state["applied_fixes"][0]
        snapshot = receipt["rollback_snapshot"]
        snapshot["before_files"]["second.css"] = "before\n"
        snapshot["after_files"]["second.css"] = "after\n"
        snapshot["sha256"] = digest({k: v for k, v in snapshot.items() if k != "sha256"})
        current = (self.workspace / "index.html").read_bytes()
        with self.assertRaisesRegex(GateStop, "Atomic multi-file"):
            _plan(state, ["fix-1"])
        self.assertEqual((self.workspace / "index.html").read_bytes(), current)
        self.assertEqual((self.workspace / "second.css").read_text(), "after\n")
        self.assertFalse(report(state)["improvements"][0]["rollback_available"])

    def test_malformed_pending_intent_is_rejected_without_writes(self):
        proposal = preview(self.checkpoint, ["fix-1"])
        with patch("uxloop.rollback.finish_intent", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.undo(proposal)
        state = load(self.checkpoint)
        state["pending_rollback"]["intent"]["changed_paths"] = ["outside.css"]
        save(self.checkpoint, state)
        with self.assertRaises(ContractError):
            self.undo(proposal)
        self.assertNotEqual((self.workspace / "index.html").read_bytes(), self.original)

    def test_deleted_file_without_original_metadata_is_not_recreated(self):
        state = copy.deepcopy(self.state)
        proposal, intent = _plan(state, ["fix-1"])
        snapshot = state["applied_fixes"][0]["rollback_snapshot"]
        snapshot["after_files"]["index.html"] = None
        snapshot["sha256"] = digest({k: v for k, v in snapshot.items() if k != "sha256"})
        (self.workspace / "index.html").unlink()
        with self.assertRaisesRegex(GateStop, "metadata"):
            _plan(state, ["fix-1"])
        self.assertFalse((self.workspace / "index.html").exists())
        row = report(state)["improvements"][0]
        self.assertFalse(row["rollback_available"])
        self.assertIn("metadata", row["rollback_limit"])
        state["pending_rollback"] = dict(preview=proposal, intent=intent, actor="owner", reason="selected",
                                         authorization_event=state["permissions"]["code_write"]["id"])
        with self.assertRaisesRegex(ContractError, "metadata"):
            validate_pending(state)

    def test_oversized_checkpoint_never_replaces_readable_state(self):
        state = load(self.checkpoint)
        original = self.checkpoint.read_bytes()
        state["reason"] = "x" * (8 * 1024 * 1024)
        with self.assertRaises(ContractError):
            save(self.checkpoint, state)
        self.assertEqual(self.checkpoint.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
