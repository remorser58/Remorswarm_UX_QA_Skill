"""Owned offline CLI regressions for preparing the same journeys on a new build.

All source material, personas, build bytes, observations and PNGs are invented.
The real CLI and persistence run; no browser, public collection, real participant
or measured UX improvement is represented by these fixtures.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest

import _paths
import test_persona_comparison as comparison_helpers
from uxresearch.canonical import byte_digest, canonical, digest
from uxresearch.storage import atomic, read_json


ENTRYPOINT = comparison_helpers.ENTRYPOINT


class PersonaReplayTests(unittest.TestCase):
    # Reuse owned fixture builders, not the other class's test methods.
    setUp = comparison_helpers.PersonaComparisonTests.setUp
    command = comparison_helpers.PersonaComparisonTests.command
    write_input = comparison_helpers.PersonaComparisonTests.write_input
    receipt = comparison_helpers.PersonaComparisonTests.receipt
    complete = comparison_helpers.PersonaComparisonTests.complete
    research_command = comparison_helpers.PersonaComparisonTests.research_command
    gated_fixture = comparison_helpers.PersonaComparisonTests.gated_fixture

    def tree_bytes(self, root):
        return {str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def prepare_baseline(self, *, gated=False):
        if gated:
            self.gated_fixture()
        for task in self.specs["before"]["tasks"]:
            task["resource_id"] = "shared-baseline-fixture"
        self.command("import", "--input", self.write_input("profiles.json", self.doc))
        self.command("plan", "--run", self.baseline,
                     "--input", self.write_input("baseline-plan.json", self.specs["before"]))
        receipts = {}
        for index, outcome in enumerate(("failed", "passed"), 1):
            receipts["T" + str(index)] = self.complete(self.baseline, "T" + str(index), outcome, cli=True)
        return receipts

    def replay_arguments(self, *, run=None, build_id="after", artifact=None, isolation_id="next",
                         confirm_starting_state=True, confirm_isolation=True, output_format="json"):
        args = ["--baseline", str(self.baseline), "--run", str(run or self.candidate),
                "--build-id", build_id, "--artifact", str(artifact or self.specs["after"]["build"]["artifact_path"]),
                "--isolation-id", isolation_id]
        if confirm_starting_state:
            args.append("--confirm-starting-state")
        if confirm_isolation:
            args.append("--confirm-isolation")
        if output_format is not None:
            args.extend(["--format", output_format])
        return args

    def test_cli_gated_two_personas_replay_to_new_receipts_and_comparison(self):
        old_receipts = self.prepare_baseline(gated=True)
        baseline_bytes = self.tree_bytes(self.baseline)
        library_bytes = (self.library_path / "library.json").read_bytes()
        original = read_json(self.baseline / "swarm-state.json")["payload"]

        # This is the missing product connection: no candidate plan document,
        # copied run folder, private state mutation or second profile import.
        prepared = self.command("replay", *self.replay_arguments())
        self.assertEqual(prepared["schema_version"], "ux-persona-replay.v1")
        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(Path(prepared["run_path"]), self.candidate)
        self.assertEqual(prepared["task_count"], 2)
        self.assertIsInstance(prepared["replay_origin"], dict)
        self.assertTrue(prepared["replay_origin"])
        self.assertEqual(prepared["replay_origin"]["schema_version"], "ux-persona-replay-origin.v1")
        self.assertEqual(prepared["replay_origin"]["baseline_run"], str(self.baseline))
        self.assertEqual(prepared["replay_origin"]["baseline_state_sha256"], digest(original))
        self.assertEqual(prepared["replay_origin"]["candidate_sha256"], self.specs["after"]["build"]["sha256"])
        self.assertEqual(prepared["replay_origin"]["isolation"]["verification"], "host_attestation_only")
        self.assertFalse(prepared["product_ready"])
        self.assertFalse(prepared["measured_ux_improvement"])
        self.assertTrue(prepared["next_steps"])
        self.assertTrue(prepared["limitations"])
        candidate = read_json(self.candidate / "swarm-state.json")["payload"]
        self.assertEqual(candidate["build"], self.specs["after"]["build"])
        for limit in ("max_parallel", "lease_seconds", "max_attempts"):
            self.assertEqual(candidate[limit], original[limit])
        self.assertEqual(len(candidate["tasks"]), len(original["tasks"]))
        old_namespaces = {entry["task"]["data_namespace"] for entry in original["tasks"]}
        old_resources = {entry["task"]["resource_id"] for entry in original["tasks"]}
        new_namespaces, new_resources = set(), set()
        for before, after in zip(original["tasks"], candidate["tasks"]):
            self.assertEqual(after["binding"], before["binding"])
            for key, value in before["task"].items():
                if key not in {"data_namespace", "resource_id"}:
                    self.assertEqual(after["task"][key], value, key)
            new_namespaces.add(after["task"]["data_namespace"])
            new_resources.add(after["task"]["resource_id"])
            self.assertEqual(after["status"], "pending")
            self.assertEqual(after["attempts"], 0)
            self.assertEqual(after["history"], [])
            self.assertFalse(set(after) & {"receipt", "lease", "operation_id", "settlement", "reconciliation", "grant"})
        self.assertEqual(len(new_namespaces), 2)
        self.assertTrue(new_namespaces.isdisjoint(old_namespaces))
        self.assertEqual(len(new_resources), 1, "previously shared resources must remain serialized")
        self.assertTrue(new_resources.isdisjoint(old_resources))
        self.assertEqual(baseline_bytes, self.tree_bytes(self.baseline))
        self.assertEqual(library_bytes, (self.library_path / "library.json").read_bytes())

        report = self.command("report", "--run", self.candidate)
        self.assertEqual(report["counts"]["pending"], 2)
        self.assertEqual(report["counts"]["passed"], 0)
        self.assertEqual(report["counts"]["failed"], 0)
        self.assertFalse(report["product_ready"])
        self.assertEqual(report["replay_origin"], prepared["replay_origin"])
        comparison = self.command("compare", "--baseline", self.baseline, "--run", self.candidate,
                                  "--format", "json", expected=1)
        self.assertFalse(comparison["comparison_complete"])
        self.assertEqual(comparison["counts"]["not_compared"], 2)

        for index, outcome in enumerate(("passed", "failed"), 1):
            task_id = "T" + str(index)
            claim = self.command("claim", "--run", self.candidate,
                                 "--worker", "owned-replay-worker", "--task", task_id)
            self.assertTrue(claim["claimed"])
            self.assertEqual(claim["provenance_mode"], "gated_research")
            self.assertEqual(claim["replay_origin"], prepared["replay_origin"])
            old_entry = original["tasks"][index - 1]
            self.assertNotEqual(claim["operation_id"], old_entry["operation_id"])
            self.assertNotEqual(claim["lease"]["lease_token"], old_entry["lease"]["lease_token"])
            claim_path = self.write_input("current-claim.json", claim)
            starter = self.command("receipt-starter", "--run", self.candidate, "--claim", claim_path)
            self.assertEqual(starter["schema_version"], "ux-persona-swarm-receipt-draft.v1")
            self.assertEqual(starter["steps"], [])
            self.assertEqual(starter["artifacts"], [])
            self.assertTrue(all(item["status"] == "not_run" for item in starter["criteria"]))
            before_rejection = self.tree_bytes(self.candidate)
            rejected = self.command("record", "--run", self.candidate,
                         "--input", self.write_input("old-receipt.json", old_receipts[task_id]), expected=2, decode=False)
            self.assertEqual(json.loads(rejected.stderr)["result"], "blocked")
            self.assertEqual(before_rejection, self.tree_bytes(self.candidate))
            receipt = self.receipt(self.candidate, claim, outcome)
            self.command("record", "--run", self.candidate,
                         "--input", self.write_input("new-receipt.json", receipt))

        compared = self.command("compare", "--baseline", self.baseline, "--run", self.candidate,
                                "--format", "json")
        self.assertTrue(compared["comparison_complete"])
        self.assertEqual(compared["counts"]["failed_to_passed"], 1)
        self.assertEqual(compared["counts"]["passed_to_failed"], 1)
        self.assertFalse(compared["product_ready"])
        self.assertFalse(compared["measured_ux_improvement"])
        self.assertEqual(baseline_bytes, self.tree_bytes(self.baseline))
        self.assertEqual(library_bytes, (self.library_path / "library.json").read_bytes())


    def run_cli(self, command, *args, library=None):
        return subprocess.run(
            [sys.executable, str(ENTRYPOINT), *(["personas"] if ENTRYPOINT.name == "remorsearch.py" else []),
             command, "--library", str(library or self.library_path), *map(str, args)],
            capture_output=True, text=True, timeout=20, cwd=self.root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )

    def blocked_replay(self, *args, library=None):
        before = self.tree_bytes(self.baseline)
        result = self.run_cli("replay", *(args or self.replay_arguments()), library=library)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        failure = json.loads(result.stderr)
        self.assertEqual(failure["result"], "blocked")
        self.assertTrue(failure["issue"]["code"])
        self.assertEqual(before, self.tree_bytes(self.baseline))
        return failure

    def change_baseline(self, change):
        state = read_json(self.baseline / "swarm-state.json")["payload"]
        change(state)
        atomic(self.baseline / "swarm-state.json", canonical(dict(
            schema_version="ux-persona-swarm-state.v3", payload=state, sha256=digest(state))))

    def prepare_incomplete_baseline(self, outcome):
        self.command("import", "--input", self.write_input("profiles.json", self.doc))
        self.command("plan", "--run", self.baseline,
                     "--input", self.write_input("baseline-plan.json", self.specs["before"]))
        self.complete(self.baseline, "T2", "passed", cli=True)
        if outcome == "pending":
            return None
        claim = self.command("claim", "--run", self.baseline, "--worker", "owned-fixture", "--task", "T1")
        if outcome in {"running", "expired-running"}:
            if outcome == "expired-running":
                self.change_baseline(lambda state: state["tasks"][0]["lease"].update(expires_at=1))
            return claim
        receipt = dict(
            schema_version="ux-persona-swarm-receipt.v1", task_id="T1",
            worker_id=claim["lease"]["worker_id"], lease_token=claim["lease"]["lease_token"],
            build_sha256=claim["build"]["sha256"], persona_revision=claim["binding"]["revision"],
            profile_sha256=claim["binding"]["profile_sha256"], outcome=outcome,
            reason="Owned fixture has no established executed outcome.", steps=[], criteria=[], artifacts=[],
        )
        self.command("record", "--run", self.baseline, "--input", self.write_input("incomplete.json", receipt))
        return claim

    def assert_incomplete_blocked(self, outcome):
        self.prepare_incomplete_baseline(outcome)
        before_library = self.tree_bytes(self.library_path)
        self.blocked_replay()
        self.assertFalse(self.candidate.exists())
        self.assertEqual(before_library, self.tree_bytes(self.library_path))

    def test_missing_confirmations_never_create_a_run_or_reservation(self):
        self.prepare_baseline()
        before_library = self.tree_bytes(self.library_path)
        for starting, isolation in ((False, True), (True, False), (False, False)):
            with self.subTest(starting=starting, isolation=isolation):
                self.blocked_replay(*self.replay_arguments(
                    confirm_starting_state=starting, confirm_isolation=isolation))
                self.assertFalse(self.candidate.exists())
                self.assertEqual(before_library, self.tree_bytes(self.library_path))

    def test_build_identity_and_bytes_must_both_change(self):
        self.prepare_baseline()
        before_library = self.tree_bytes(self.library_path)
        self.blocked_replay(*self.replay_arguments(build_id="before"))
        self.blocked_replay(*self.replay_arguments(artifact=self.specs["before"]["build"]["artifact_path"]))
        self.assertFalse(self.candidate.exists())
        self.assertEqual(before_library, self.tree_bytes(self.library_path))

    def test_restart_and_exact_rerun_keep_pending_running_and_completed_state(self):
        self.prepare_baseline()
        first = self.command("replay", *self.replay_arguments())
        initial = self.tree_bytes(self.candidate)
        repeated = self.command("replay", *self.replay_arguments())
        self.assertEqual(repeated["status"], "existing")
        self.assertEqual(repeated["replay_origin"], first["replay_origin"])
        self.assertEqual(initial, self.tree_bytes(self.candidate))
        claim = self.command("claim", "--run", self.candidate, "--worker", "owned-restarted", "--task", "T1")
        running = self.tree_bytes(self.candidate)
        repeated = self.command("replay", *self.replay_arguments())
        self.assertEqual(repeated["status"], "existing")
        self.assertEqual(running, self.tree_bytes(self.candidate))
        self.assertEqual(claim["attempt"], 1)
        receipt = self.receipt(self.candidate, claim, "passed")
        self.command("record", "--run", self.candidate, "--input", self.write_input("current.json", receipt))
        completed = self.tree_bytes(self.candidate)
        repeated = self.command("replay", *self.replay_arguments())
        self.assertEqual(repeated["status"], "existing")
        self.assertEqual(completed, self.tree_bytes(self.candidate))
        state = read_json(self.candidate / "swarm-state.json")["payload"]
        self.assertEqual(state["tasks"][0]["status"], "passed")
        self.assertEqual(state["tasks"][0]["attempts"], 1)

    def test_candidate_alias_and_new_isolation_cannot_allocate_a_second_budget(self):
        self.prepare_baseline()
        self.command("replay", *self.replay_arguments())
        alias = self.root / "same-candidate-different-path.txt"
        atomic(alias, Path(self.specs["after"]["build"]["artifact_path"]).read_bytes())
        other = self.root / "another-replay"
        before_index = (self.library_path / "replay-index.json").read_bytes()
        before_candidate = self.tree_bytes(self.candidate)
        args = self.replay_arguments(run=other, build_id="different-alias", artifact=alias, isolation_id="different-isolation")
        failure = self.blocked_replay(*args)
        self.assertEqual(failure["issue"]["code"], "replay_duplicate")
        # Normalization must not turn the same original run into a new identity.
        args[args.index("--baseline") + 1] = str(self.baseline / ".." / "before")
        self.blocked_replay(*args)
        self.assertFalse(other.exists())
        self.assertEqual(before_index, (self.library_path / "replay-index.json").read_bytes())
        self.assertEqual(before_candidate, self.tree_bytes(self.candidate))

    def test_same_destination_with_changed_replay_options_is_not_silently_rebound(self):
        self.prepare_baseline()
        self.command("replay", *self.replay_arguments())
        before = self.tree_bytes(self.candidate)
        self.blocked_replay(*self.replay_arguments(isolation_id="different"))
        self.assertEqual(before, self.tree_bytes(self.candidate))

    def test_existing_destination_content_is_preserved(self):
        self.prepare_baseline()
        self.candidate.mkdir(mode=0o700)
        atomic(self.candidate / "owned-existing.txt", b"Preserve this owned fixture content.")
        before = self.tree_bytes(self.candidate)
        self.blocked_replay()
        self.assertEqual(before, self.tree_bytes(self.candidate))

    def test_missing_library_is_not_initialized_by_failed_replay(self):
        self.prepare_baseline()
        missing = self.root / "missing-library"
        self.blocked_replay(library=missing)
        self.assertFalse(missing.exists())
        self.assertFalse(self.candidate.exists())

    def test_public_baseline_directory_is_rejected_without_changing_its_permissions(self):
        self.prepare_baseline()
        self.baseline.chmod(0o755)
        self.blocked_replay()
        self.assertEqual(self.baseline.stat().st_mode & 0o777, 0o755)
        self.assertFalse(self.candidate.exists())

    def test_symlinked_baseline_is_not_followed(self):
        self.prepare_baseline()
        alias = self.root / "baseline-alias"
        alias.symlink_to(self.baseline, target_is_directory=True)
        args = self.replay_arguments()
        args[args.index("--baseline") + 1] = str(alias)
        self.blocked_replay(*args)
        self.assertTrue(alias.is_symlink())
        self.assertFalse(self.candidate.exists())

    def test_symlinked_destination_does_not_modify_the_target(self):
        self.prepare_baseline()
        target = self.root / "owned-existing-target"
        target.mkdir(mode=0o700)
        atomic(target / "keep.txt", b"Preserve owned target.")
        before = self.tree_bytes(target)
        self.candidate.symlink_to(target, target_is_directory=True)
        self.blocked_replay()
        self.assertTrue(self.candidate.is_symlink())
        self.assertEqual(before, self.tree_bytes(target))

    def test_public_replay_index_blocks_even_an_exact_rerun(self):
        self.prepare_baseline()
        self.command("replay", *self.replay_arguments())
        index = self.library_path / "replay-index.json"
        index.chmod(0o644)
        before = self.tree_bytes(self.candidate)
        self.blocked_replay()
        self.assertEqual(index.stat().st_mode & 0o777, 0o644)
        self.assertEqual(before, self.tree_bytes(self.candidate))

    def test_symlinked_replay_index_never_rewrites_its_target(self):
        self.prepare_baseline()
        self.command("replay", *self.replay_arguments())
        index = self.library_path / "replay-index.json"
        preserved = self.root / "owned-original-index.json"
        index.rename(preserved)
        index.symlink_to(preserved)
        original = preserved.read_bytes()
        self.blocked_replay()
        self.assertTrue(index.is_symlink())
        self.assertEqual(original, preserved.read_bytes())

    def test_corrupt_replay_index_cannot_reset_duplicate_protection(self):
        self.prepare_baseline()
        self.command("replay", *self.replay_arguments())
        index = self.library_path / "replay-index.json"
        atomic(index, b"{}")
        other = self.root / "must-not-be-created"
        self.blocked_replay(*self.replay_arguments(run=other, isolation_id="another"))
        self.assertFalse(other.exists())
        self.assertEqual(index.read_bytes(), b"{}")

    def test_pending_baseline_cannot_be_replayed(self):
        self.assert_incomplete_blocked("pending")

    def test_running_baseline_cannot_be_replayed(self):
        self.assert_incomplete_blocked("running")

    def test_expired_running_baseline_is_not_expired_or_replayed_as_a_side_effect(self):
        self.assert_incomplete_blocked("expired-running")

    def test_blocked_baseline_cannot_be_replayed(self):
        self.assert_incomplete_blocked("blocked")

    def test_inconclusive_baseline_cannot_be_replayed(self):
        self.assert_incomplete_blocked("inconclusive")

    def test_skipped_baseline_cannot_be_replayed(self):
        self.assert_incomplete_blocked("skipped")

    def test_retried_pending_baseline_does_not_receive_a_new_budget(self):
        self.prepare_baseline()
        self.command("retry", "--run", self.baseline, "--task", "T1")
        before = read_json(self.baseline / "swarm-state.json")["payload"]
        self.assertEqual(before["tasks"][0]["attempts"], 1)
        self.blocked_replay()
        self.assertFalse(self.candidate.exists())
        after = read_json(self.baseline / "swarm-state.json")["payload"]
        self.assertEqual(after["tasks"][0]["attempts"], 1)
        self.assertEqual(after["tasks"][0]["history"], before["tasks"][0]["history"])

    def test_settled_uncertainty_is_not_a_completed_baseline(self):
        claim = self.prepare_incomplete_baseline("inconclusive")
        inspection = dict(operation_id=claim["operation_id"], attempt=claim["attempt"],
                          outcome="not_executed", note="Owned fixture inspection; no external worker was launched.",
                          worker_stopped=True)
        self.command("settle", "--run", self.baseline, "--task", "T1",
                     "--inspection", self.write_input("inspection.json", inspection))
        self.blocked_replay()
        self.assertFalse(self.candidate.exists())

    def test_superseded_persona_cannot_silently_change_the_replayed_journey(self):
        self.prepare_baseline()
        changed = copy.deepcopy(self.doc)
        changed["personas"][0]["behaviors"].append("A separately authored new behavior.")
        self.command("import", "--input", self.write_input("new-profile.json", changed))
        self.blocked_replay()
        self.assertFalse(self.candidate.exists())

    def test_retired_persona_stays_retired(self):
        self.prepare_baseline()
        persona_id = self.doc["personas"][0]["persona_id"]
        self.command("retire", "--product", "sample", "--persona", persona_id,
                     "--reason", "Owned fixture withdrawal.")
        before_library = (self.library_path / "library.json").read_bytes()
        self.blocked_replay()
        self.assertFalse(self.candidate.exists())
        self.assertEqual(before_library, (self.library_path / "library.json").read_bytes())

    def test_authoritative_capture_withdrawal_blocks_replay_without_pruning(self):
        from uxresearch.storage import Store
        research = self.gated_fixture()
        self.prepare_baseline()
        with Store(research) as store:
            bundle = store.committed("bundle.json")
            bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "withdrawn"
            store.publish("replay-fixture-withdrawal", {"bundle.json": bundle}, invalidates_gate=True)
        before_baseline = self.tree_bytes(self.baseline)
        before_library = self.tree_bytes(self.library_path)
        failure = self.blocked_replay()
        self.assertEqual(failure["issue"]["code"], "persona_retention_due")
        self.assertFalse(self.candidate.exists())
        self.assertFalse((self.library_path / "replay-index.json").exists())
        self.assertEqual(before_baseline, self.tree_bytes(self.baseline))
        self.assertEqual(before_library, self.tree_bytes(self.library_path))

    def test_due_persona_review_cannot_be_bypassed_by_replay(self):
        import time
        from uxpersonas.library import Library
        from uxresearch.canonical import EngineError
        self.prepare_baseline()
        before_baseline = self.tree_bytes(self.baseline)
        before_library = self.tree_bytes(self.library_path)
        with Library(self.library_path, clock=lambda: time.time() + 31 * 86400) as library:
            with self.assertRaises(EngineError) as caught:
                self.prepare_via_api(library)
        self.assertEqual(caught.exception.issue["code"], "persona_review_due")
        self.assertFalse(self.candidate.exists())
        self.assertFalse((self.library_path / "replay-index.json").exists())
        self.assertEqual(before_baseline, self.tree_bytes(self.baseline))
        self.assertEqual(before_library, self.tree_bytes(self.library_path))

    def test_changed_prd_blocks_replay(self):
        self.prepare_baseline()
        path = Path(self.doc["context"]["prd_path"])
        atomic(path, path.read_bytes() + b"\nChanged owned PRD requirement.\n")
        self.blocked_replay()
        self.assertFalse(self.candidate.exists())

    def test_changed_original_build_blocks_replay(self):
        self.prepare_baseline()
        path = Path(self.specs["before"]["build"]["artifact_path"])
        atomic(path, path.read_bytes() + b"\nChanged original build bytes.\n")
        self.blocked_replay()
        self.assertFalse(self.candidate.exists())

    def test_tampered_current_receipt_binding_is_detected_even_with_a_valid_state_digest(self):
        self.prepare_baseline()
        self.change_baseline(lambda state: state["tasks"][0]["receipt"].update(task_id="T2"))
        self.blocked_replay()
        self.assertFalse(self.candidate.exists())

    def test_tampered_execution_artifact_is_detected(self):
        self.prepare_baseline()
        state = read_json(self.baseline / "swarm-state.json")["payload"]
        artifact = self.baseline / state["tasks"][0]["receipt"]["artifacts"][0]["path"]
        atomic(artifact, b"Changed owned observation bytes.")
        self.blocked_replay()
        self.assertFalse(self.candidate.exists())

    def test_concurrent_same_candidate_different_destinations_have_exactly_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        self.prepare_baseline()
        other = self.root / "other-concurrent-replay"
        arguments = [self.replay_arguments(), self.replay_arguments(run=other, isolation_id="other")]
        baseline = self.tree_bytes(self.baseline)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda args: self.run_cli("replay", *args), arguments))
        self.assertEqual(sum(result.returncode == 0 for result in results), 1,
                         [result.stdout + result.stderr for result in results])
        winner = next(result for result in results if result.returncode == 0)
        loser = next(result for result in results if result.returncode != 0)
        prepared = json.loads(winner.stdout)
        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(json.loads(loser.stderr)["result"], "blocked")
        self.assertEqual(sum(path.exists() for path in (self.candidate, other)), 1)
        self.assertEqual(baseline, self.tree_bytes(self.baseline))
        winning_path = Path(prepared["run_path"])
        state = read_json(winning_path / "swarm-state.json")["payload"]
        self.assertTrue(all(entry["status"] == "pending" and entry["attempts"] == 0 for entry in state["tasks"]))

    def test_default_report_is_readable_and_does_not_claim_execution(self):
        self.prepare_baseline()
        result = self.command("replay", *self.replay_arguments(output_format=None), decode=False)
        self.assertIn("claim", result.stdout)
        self.assertIn("compare", result.stdout)
        self.assertNotIn("lease_token", result.stdout)
        self.assertNotIn("product_ready: true", result.stdout)
        state = read_json(self.candidate / "swarm-state.json")["payload"]
        self.assertTrue(all(entry["status"] == "pending" for entry in state["tasks"]))
        # Execute the printed claim without a shell; verify the command itself
        # remains usable from both the checkout and an extracted launcher.
        commands = []
        for line in result.stdout.splitlines():
            try:
                args = shlex.split(line.strip())
            except ValueError:
                continue
            if len(args) > 2 and args[0] == sys.executable and "claim" in args:
                commands.append(args)
        self.assertEqual(len(commands), 1, result.stdout)
        args = commands[0]
        self.assertIn(Path(args[1]).name, {"ux_personas.py", "remorsearch.py"})
        self.assertEqual(args[args.index("--library") + 1], str(self.library_path))
        self.assertEqual(args[args.index("--run") + 1], str(self.candidate))
        claimed = subprocess.run(args, capture_output=True, text=True, timeout=20, cwd=self.root,
                                 env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(claimed.returncode, 0, claimed.stderr)
        claim = json.loads(claimed.stdout)
        self.assertTrue(claim["claimed"])
        self.assertEqual(claim["provenance_mode"], "prd_hypothesis")

    def test_exact_replay_reopen_does_not_expire_a_running_candidate_lease(self):
        self.prepare_baseline()
        self.command("replay", *self.replay_arguments())
        self.command("claim", "--run", self.candidate, "--worker", "owned-expired", "--task", "T1")
        state = read_json(self.candidate / "swarm-state.json")["payload"]
        state["tasks"][0]["lease"]["expires_at"] = 1
        atomic(self.candidate / "swarm-state.json", canonical(dict(
            schema_version="ux-persona-swarm-state.v3", payload=state, sha256=digest(state))))
        before = self.tree_bytes(self.candidate)
        reopened = self.command("replay", *self.replay_arguments())
        self.assertEqual(reopened["status"], "existing")
        self.assertEqual(before, self.tree_bytes(self.candidate))
        current = read_json(self.candidate / "swarm-state.json")["payload"]["tasks"][0]
        self.assertEqual(current["status"], "running")
        self.assertEqual(current["attempts"], 1)
        self.assertEqual(current["lease"]["expires_at"], 1)

    def test_comparison_refuses_a_different_baseline_even_when_its_payload_is_identical(self):
        self.prepare_baseline()
        self.command("replay", *self.replay_arguments())
        alternate = self.root / "other-baseline"
        shutil.copytree(self.baseline, alternate)
        before = self.tree_bytes(self.candidate)
        result = self.run_cli("compare", "--baseline", alternate, "--run", self.candidate, "--format", "json")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["issue"]["code"], "replay_baseline_mismatch")
        self.assertEqual(before, self.tree_bytes(self.candidate))

    def test_comparison_refuses_a_changed_baseline_snapshot_without_rewriting_the_replay(self):
        self.prepare_baseline()
        self.command("replay", *self.replay_arguments())
        self.change_baseline(lambda state: state["tasks"][0].update(reason="Updated owned baseline annotation."))
        before = self.tree_bytes(self.candidate)
        result = self.run_cli("compare", "--baseline", self.baseline, "--run", self.candidate, "--format", "json")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["issue"]["code"], "replay_baseline_mismatch")
        self.assertEqual(before, self.tree_bytes(self.candidate))

    def prepare_via_api(self, library):
        from uxpersonas import replay
        return replay.prepare(
            library, self.baseline, self.candidate, build_id="after",
            artifact_path=self.specs["after"]["build"]["artifact_path"], isolation_id="next",
            confirm_starting_state=True, confirm_isolation=True,
        )

    def test_reserved_only_failure_resumes_only_the_original_absent_destination(self):
        from unittest import mock
        from uxpersonas.library import Library
        self.prepare_baseline()
        before = self.tree_bytes(self.baseline)
        with Library(self.library_path) as library:
            with mock.patch("uxpersonas.replay.swarm._create_plan", side_effect=OSError("Owned precreation failure")) as interrupted:
                with self.assertRaises(OSError):
                    self.prepare_via_api(library)
                interrupted.assert_called_once()
        self.assertFalse(self.candidate.exists())
        self.assertTrue((self.library_path / "replay-index.json").is_file())
        other = self.root / "different-after-interruption"
        self.blocked_replay(*self.replay_arguments(run=other))
        self.assertFalse(other.exists())
        result = self.command("replay", *self.replay_arguments())
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(before, self.tree_bytes(self.baseline))
        state = read_json(self.candidate / "swarm-state.json")["payload"]
        self.assertTrue(all(entry["attempts"] == 0 and entry["status"] == "pending" for entry in state["tasks"]))

    def test_partial_creation_failure_preserves_owned_files_and_cannot_create_another_budget(self):
        from unittest import mock
        from uxpersonas import swarm
        from uxpersonas.library import Library
        self.prepare_baseline()
        original_save = swarm._save
        def interrupted_save(root, state):
            if Path(root) == self.candidate:
                raise OSError("Owned partial creation failure")
            return original_save(root, state)
        with Library(self.library_path) as library:
            with mock.patch.object(swarm, "_save", side_effect=interrupted_save):
                with self.assertRaises(OSError):
                    self.prepare_via_api(library)
        self.assertTrue(self.candidate.is_dir())
        self.assertFalse((self.candidate / "swarm-state.json").exists())
        atomic(self.candidate / "preserve-owned-partial.txt", b"Owned partial evidence must survive.")
        before = self.tree_bytes(self.candidate)
        self.blocked_replay()
        self.assertEqual(before, self.tree_bytes(self.candidate))
        other = self.root / "different-after-partial"
        self.blocked_replay(*self.replay_arguments(run=other))
        self.assertFalse(other.exists())


if __name__ == "__main__":
    unittest.main()
