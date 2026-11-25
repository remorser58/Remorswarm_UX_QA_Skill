"""Offline orchestration regressions; fixture evidence is not live UX proof."""
import copy
import multiprocessing
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/remorsearch-ux-qa"))
from uxpersonas import swarm
from ergoqa.png import encode, new_image
from uxresearch.canonical import EngineError, byte_digest, digest
from uxresearch.storage import atomic, canonical, read_json


class FakeLibrary:
    stale = False
    def get(self, product_id, persona_id, revision=None, revalidate=True):
        if self.stale:
            raise EngineError("stale", "Source is no longer current.")
        profile = dict(label="Interrupted explorer", goals=["Finish"], behaviors=["Compare options"],
                       contexts=["Interrupted"], assumptions=["Synthetic"], unknowns=["Real frequency"],
                       requirement_ids=["R1"])
        return dict(product_id=product_id, persona_id=persona_id, revision=1,
                    profile_sha256=digest(profile), profile=profile,
                    context=dict(prd_sha256="p" * 64, requirements=[dict(id="R1")]),
                    provenance=dict(mode="prd_hypothesis"))


def process_worker(run, worker, ready, release, results, outcome):
    """Real separate-process scheduler client; no model/browser simulation."""
    claim = swarm.claim(FakeLibrary(), run, worker)
    results.put((os.getpid(), claim))
    ready.wait(timeout=15)
    if not claim["claimed"] or outcome == "crash":
        return
    if not release.wait(timeout=15):
        raise RuntimeError("Parent did not release process")
    receipt = dict(schema_version="ux-persona-swarm-receipt.v1",
                   task_id=claim["task"]["id"], worker_id=worker,
                   lease_token=claim["lease"]["lease_token"], build_sha256=claim["build"]["sha256"],
                   persona_revision=claim["binding"]["revision"],
                   profile_sha256=claim["binding"]["profile_sha256"], outcome=outcome,
                   reason="Tool denied before execution." if outcome == "blocked" else "Tool outcome unknown.",
                   steps=[], criteria=[], artifacts=[])
    swarm.record(FakeLibrary(), run, receipt)


class SwarmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.lib = FakeLibrary()
        self.build = self.root / "build.txt"
        self.build.write_text("fixture build")
        self.run = self.root / "run"
        task = dict(id="T1", persona_id="P1", requirement_ids=["R1"], goal="Finish comparison",
                    starting_state="Fresh synthetic session", actions=["Choose", "Return"],
                    decisions=["Compare visible choices"], success_criteria=["Choice retained"],
                    recovery_criteria=["Return restores input"], data_namespace="fixture1",
                    resource_id="browser1", side_effects="owned_fixture_write",
                    stop_conditions=["Real customer data appears"])
        self.spec = dict(schema_version=swarm.SCHEMA, product_id="demo",
                         build=dict(id="b1", artifact_path=str(self.build),
                                    sha256=byte_digest(self.build.read_bytes())),
                         max_parallel=2, lease_seconds=30, max_attempts=2, tasks=[task])

    def plan(self):
        return swarm.create_plan(self.lib, self.run, self.spec)

    def receipt(self, claim, outcome="passed"):
        artifacts = []
        for aid, kind, raw in (("log", "execution_log", b"Choose: selected option; Return: value restored"),
                               ("png", "screenshot", encode(new_image(2, 2)))):
            path = Path(claim["evidence_path"]) / aid
            atomic(path, raw)
            artifacts.append(dict(id=aid, kind=kind, path=str(path.relative_to(self.run)), sha256=byte_digest(raw)))
        return dict(schema_version="ux-persona-swarm-receipt.v1", task_id=claim["task"]["id"],
                    worker_id=claim["lease"]["worker_id"], lease_token=claim["lease"]["lease_token"],
                    build_sha256=claim["build"]["sha256"], persona_revision=claim["binding"]["revision"],
                    profile_sha256=claim["binding"]["profile_sha256"], outcome=outcome,
                    reason="Observed fixture behavior.", artifacts=artifacts,
                    steps=[dict(action="Choose and return", observation="Input restored", evidence_ids=["log", "png"])],
                    criteria=[dict(kind=k, index=0, status="failed" if outcome == "failed" else "passed", observation="Fixture expectation mismatch" if outcome == "failed" else "Input restored",
                                   evidence_ids=["log", "png"]) for k in ("success", "recovery")])

    def test_failed_outcome_cannot_contradict_passed_criteria(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim)
        receipt["outcome"] = "failed"
        with self.assertRaises(EngineError):
            swarm.record(self.lib, self.run, receipt)

    def test_claim_carries_requirement_and_uncertain_claim_context(self):
        original = self.lib.get
        def get(*args, **kwargs):
            row = original(*args, **kwargs)
            row["context"]["requirements"][0].update(source_anchor="Section 1", excerpt="Keep state")
            row["provenance"] = {"mode": "gated_research", "research": {"claims": [
                {"claim_id": "CLM-12345678", "gate_status": "insufficient", "source_ids": ["SRC-example"]}]}}
            return row
        with patch.object(self.lib, "get", side_effect=get):
            self.plan()
            claim = swarm.claim(self.lib, self.run, "w1")
        self.assertEqual(claim["research_claims"][0]["gate_status"], "insufficient")
        self.assertEqual(claim["requirement_context"][0]["excerpt"], "Keep state")

    def test_pass_and_report_limits(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "worker1")
        swarm.record(self.lib, self.run, self.receipt(claim))
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["counts"]["passed"], 1)
        self.assertFalse(report["product_ready"])

    def test_claim_recovers_empty_orphan_after_failed_save(self):
        self.plan()
        with patch.object(swarm, "_save", side_effect=OSError("injected commit failure")):
            with self.assertRaises(OSError):
                swarm.claim(self.lib, self.run, "w1")
        orphan = self.run / "evidence" / "T1" / "1"
        self.assertTrue(orphan.is_dir())
        self.assertEqual(list(orphan.iterdir()), [])
        claim = swarm.claim(self.lib, self.run, "w2")
        self.assertTrue(claim["claimed"])
        self.assertEqual(claim["attempt"], 1)
        self.assertFalse(swarm.claim(self.lib, self.run, "w3")["claimed"])

    def test_claim_preserves_nonempty_orphan_and_refuses_symlink(self):
        self.plan()
        orphan = self.run / "evidence" / "T1" / "1"
        orphan.parent.mkdir(mode=0o700)
        orphan.mkdir(mode=0o700)
        atomic(orphan / "capture", b"preserve")
        with self.assertRaises(EngineError):
            swarm.claim(self.lib, self.run, "w1")
        self.assertEqual((orphan / "capture").read_bytes(), b"preserve")
        (orphan / "capture").unlink()
        orphan.rmdir()
        orphan.symlink_to(self.root)
        with self.assertRaises(EngineError):
            swarm.claim(self.lib, self.run, "w1")

    def test_png_signature_only_and_bad_crc_are_rejected(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim)
        artifact = receipt["artifacts"][1]
        path = self.run / artifact["path"]
        valid = path.read_bytes()
        corrupt = bytearray(valid)
        corrupt[29] ^= 1
        for raw in (b"\x89PNG\r\n\x1a\nfixture", bytes(corrupt), valid + b"trailer"):
            atomic(path, raw)
            artifact["sha256"] = byte_digest(raw)
            with self.assertRaises(EngineError):
                swarm.record(self.lib, self.run, receipt)

    def test_refuse_overwrite_duplicate_namespace_and_live_writes(self):
        self.plan()
        with self.assertRaises(EngineError):
            self.plan()
        self.spec["tasks"][0]["side_effects"] = "live_write"
        with self.assertRaises(EngineError):
            swarm.create_plan(self.lib, self.root / "bad", self.spec)

    def test_concurrent_claim_is_single_owner(self):
        self.plan()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda i: swarm.claim(self.lib, self.run, "w" + str(i)), range(4)))
        self.assertEqual(sum(r["claimed"] for r in results), 1)

    def test_resource_exclusion_and_parallel_bound(self):
        second = copy.deepcopy(self.spec["tasks"][0])
        second.update(id="T2", data_namespace="fixture2")
        self.spec["tasks"].append(second)
        self.plan()
        self.assertTrue(swarm.claim(self.lib, self.run, "w1")["claimed"])
        self.assertFalse(swarm.claim(self.lib, self.run, "w2")["claimed"])

    def test_expiry_requires_explicit_bounded_retry(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        with patch.object(swarm.time, "time", return_value=claim["lease"]["expires_at"] + 1):
            self.assertEqual(swarm.report(self.lib, self.run)["counts"]["inconclusive"], 1)
        self.assertFalse(swarm.claim(self.lib, self.run, "w2")["claimed"])
        with self.assertRaises(EngineError):
            swarm.record(self.lib, self.run, self.receipt(claim))
        with self.assertRaises(EngineError):
            swarm.retry(self.lib, self.run, "T1")
        swarm.retry(self.lib, self.run, "T1", reconciliation=dict(
            operation_id=claim["operation_id"], attempt=claim["attempt"], outcome="not_executed",
            note="Inspected isolated fixture and stopped worker.", worker_stopped=True))
        claim2 = swarm.claim(self.lib, self.run, "w2")
        self.assertEqual(claim["operation_id"], claim2["operation_id"])
        receipt = self.receipt(claim2, "blocked")
        swarm.record(self.lib, self.run, receipt)
        with self.assertRaises(EngineError):
            swarm.retry(self.lib, self.run, "T1")
        self.assertEqual(swarm.report(self.lib, self.run)["tasks"][0]["prior_outcomes"], ["inconclusive"])

    def test_distinct_resources_obey_parallel_limit(self):
        for i in (2, 3):
            task = copy.deepcopy(self.spec["tasks"][0])
            task.update(id="T" + str(i), data_namespace="fixture" + str(i), resource_id="browser" + str(i))
            self.spec["tasks"].append(task)
        self.plan()
        self.assertTrue(swarm.claim(self.lib, self.run, "w1")["claimed"])
        self.assertTrue(swarm.claim(self.lib, self.run, "w2")["claimed"])
        self.assertEqual(swarm.claim(self.lib, self.run, "w3")["reason"], "parallel_limit")

    def test_duplicate_namespace_rejected(self):
        task = copy.deepcopy(self.spec["tasks"][0])
        task["id"] = "T2"
        self.spec["tasks"].append(task)
        with self.assertRaises(EngineError):
            self.plan()

    def test_private_evidence_and_historical_integrity(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim, "failed")
        evidence = self.run / receipt["artifacts"][0]["path"]
        evidence.chmod(0o644)
        with self.assertRaises(EngineError):
            swarm.record(self.lib, self.run, receipt)
        evidence.chmod(0o600)
        swarm.record(self.lib, self.run, receipt)
        swarm.retry(self.lib, self.run, "T1")
        atomic(evidence, b"edited historical evidence")
        with self.assertRaises(EngineError):
            swarm.report(self.lib, self.run)

    def test_stale_build_and_persona_fail_closed(self):
        self.plan()
        self.lib.stale = True
        with self.assertRaises(EngineError):
            swarm.claim(self.lib, self.run, "w1")
        self.lib.stale = False
        self.build.write_text("changed")
        with self.assertRaises(EngineError):
            swarm.report(self.lib, self.run)

    def test_receipt_binding_and_replay(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim)
        wrong = dict(receipt, worker_id="w2")
        with self.assertRaises(EngineError):
            swarm.record(self.lib, self.run, wrong)
        swarm.record(self.lib, self.run, receipt)
        with self.assertRaises(EngineError):
            swarm.record(self.lib, self.run, receipt)

    def test_evidence_injection_traversal_symlink_and_tampering(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim)
        wrong = copy.deepcopy(receipt)
        wrong["artifacts"][0]["path"] = "../build.txt"
        with self.assertRaises(EngineError):
            swarm.record(self.lib, self.run, wrong)
        original = self.run / receipt["artifacts"][0]["path"]
        original.unlink()
        original.symlink_to(self.build)
        with self.assertRaises(EngineError):
            swarm.record(self.lib, self.run, receipt)
        original.unlink()
        receipt = self.receipt(claim)
        swarm.record(self.lib, self.run, receipt)
        atomic(original, b"tampered log")
        with self.assertRaises(EngineError):
            swarm.report(self.lib, self.run)

    def test_pass_needs_steps_recovery_and_capture(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim)
        for key, value in (("steps", []), ("criteria", receipt["criteria"][:1]),
                           ("artifacts", receipt["artifacts"][:1])):
            wrong = dict(receipt, **{key: value})
            with self.assertRaises(EngineError):
                swarm.record(self.lib, self.run, wrong)
        png = self.run / receipt["artifacts"][1]["path"]
        atomic(png, b"not PNG")
        receipt["artifacts"][1]["sha256"] = byte_digest(png.read_bytes())
        with self.assertRaises(EngineError):
            swarm.record(self.lib, self.run, receipt)

    def test_blocked_without_evidence_preserved(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim, "blocked")
        receipt.update(reason="Browser unavailable before execution.", artifacts=[], steps=[], criteria=[])
        swarm.record(self.lib, self.run, receipt)
        self.assertEqual(swarm.report(self.lib, self.run)["counts"]["blocked"], 1)

    def test_state_digest_and_requirement_binding(self):
        self.spec["tasks"][0]["requirement_ids"] = ["UNKNOWN"]
        with self.assertRaises(EngineError):
            self.plan()
        self.spec["tasks"][0]["requirement_ids"] = ["R1"]
        self.plan()
        atomic(self.run / "swarm-state.json", canonical(dict(payload={}, sha256="wrong")))
        with self.assertRaises(EngineError):
            swarm.report(self.lib, self.run)

    def test_unknown_plan_and_build_fields_rejected(self):
        for scope in ("plan", "build"):
            spec = copy.deepcopy(self.spec)
            (spec if scope == "plan" else spec["build"])["max_paralell"] = 8
            with self.assertRaises(EngineError):
                swarm.create_plan(self.lib, self.run, spec)
        self.assertFalse(self.run.exists())

    def test_requirement_coverage_links_and_legacy_status(self):
        coverage = [dict(requirement_id="R1", obligations=[
            dict(id="save", description="Persist selected input",
                 criterion_refs=[dict(kind="success", index=0)], exclusion_reason=None),
            dict(id="landing", description="Landing indicates resumable work",
                 criterion_refs=[], exclusion_reason="Outside this scenario; requires separate landing check.")])]
        self.spec["tasks"][0]["requirement_coverage"] = coverage
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        self.assertEqual(claim["coverage_status"], "declared_host_review_required")
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["tasks"][0]["requirement_coverage"], coverage)
        self.assertFalse(report["product_ready"])

    def test_bad_requirement_coverage_rejected(self):
        base = [dict(requirement_id="R1", obligations=[dict(
            id="save", description="Persist input",
            criterion_refs=[dict(kind="success", index=0)], exclusion_reason=None)])]
        variants = []
        for key, value in (("requirement_id", "R2"), ("obligations", [])):
            value_copy = copy.deepcopy(base)
            value_copy[0][key] = value
            variants.append(value_copy)
        for refs, exclusion in (([], None), ([dict(kind="success", index=99)], None),
                                ([dict(kind="success", index=0)], "Excluded")):
            value_copy = copy.deepcopy(base)
            value_copy[0]["obligations"][0].update(criterion_refs=refs, exclusion_reason=exclusion)
            variants.append(value_copy)
        for coverage in variants:
            self.spec["tasks"][0]["requirement_coverage"] = coverage
            with self.assertRaises(EngineError):
                self.plan()
        self.spec["tasks"][0].pop("requirement_coverage")
        self.plan()
        self.assertEqual(swarm.report(self.lib, self.run)["tasks"][0]["coverage_status"], "coverage_unassessed")

    def test_unknown_write_reconciliation_rejects_unstopped_worker(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim, "inconclusive")
        receipt.update(steps=[], criteria=[], artifacts=[], reason="Tool outcome unknown.")
        swarm.record(self.lib, self.run, receipt)
        for operation_id, stopped in (("wrong", True), (claim["operation_id"], False)):
            with self.assertRaises(EngineError):
                swarm.retry(self.lib, self.run, "T1", reconciliation=dict(
                    operation_id=operation_id, attempt=claim["attempt"], outcome="not_executed", note="Host attestation.", worker_stopped=stopped))
        self.assertEqual(swarm.report(self.lib, self.run)["counts"]["inconclusive"], 1)

    def coverage(self, excluded=False):
        return [dict(requirement_id="R1", obligations=[
            dict(id="save", description="Persist selected input",
                 criterion_refs=[dict(kind="success", index=0)], exclusion_reason=None),
            dict(id="landing", description="Show resumable work after returning",
                 criterion_refs=[] if excluded else [dict(kind="recovery", index=0)],
                 exclusion_reason="Landing prompt was not exercised." if excluded else None)])]

    def test_passing_task_keeps_excluded_prd_obligation_visible(self):
        self.spec["tasks"][0]["requirement_coverage"] = self.coverage(excluded=True)
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        swarm.record(self.lib, self.run, self.receipt(claim))
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["counts"]["passed"], 1)
        requirement = report["tasks"][0]["requirement_results"][0]
        self.assertEqual(requirement["status"], "incomplete")
        self.assertEqual([o["status"] for o in requirement["obligations"]], ["passed", "excluded"])
        self.assertEqual(requirement["obligations"][1]["exclusion_reason"], "Landing prompt was not exercised.")
        self.assertEqual(report["coverage_summary"]["obligations"]["excluded"], 1)
        self.assertFalse(report["coverage_summary"]["all_declared_requirements_passed"])

    def test_legacy_task_pass_does_not_invent_requirement_coverage(self):
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        swarm.record(self.lib, self.run, self.receipt(claim))
        report = swarm.report(self.lib, self.run)
        row = report["tasks"][0]["requirement_results"][0]
        self.assertEqual(row, dict(requirement_id="R1", status="unassessed", obligations=[]))
        self.assertEqual(report["coverage_summary"]["requirement_assignments"]["unassessed"], 1)
        self.assertEqual(report["coverage_summary"]["obligations"]["declared"], 0)
        self.assertFalse(report["coverage_summary"]["all_declared_requirements_passed"])

    def test_requirement_outcomes_follow_actual_criterion_receipts(self):
        self.spec["tasks"][0]["requirement_coverage"] = self.coverage()
        self.plan()
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["coverage_summary"]["obligations"]["not_run"], 2)
        self.assertEqual(report["tasks"][0]["requirement_results"][0]["status"], "incomplete")
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim)
        receipt["outcome"] = "failed"
        receipt["criteria"][1].update(status="failed", observation="No resume guidance appeared.")
        swarm.record(self.lib, self.run, receipt)
        report = swarm.report(self.lib, self.run)
        row = report["tasks"][0]["requirement_results"][0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual([o["status"] for o in row["obligations"]], ["passed", "failed"])
        self.assertEqual(report["coverage_summary"]["requirement_assignments"]["failed"], 1)
        self.assertEqual(report["coverage_summary"]["obligations"]["failed"], 1)
        self.assertFalse(report["coverage_summary"]["all_declared_requirements_passed"])

    def test_retry_does_not_reuse_prior_criterion_passes(self):
        self.spec["tasks"][0]["requirement_coverage"] = self.coverage()
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        swarm.record(self.lib, self.run, self.receipt(claim, "failed"))
        swarm.retry(self.lib, self.run, "T1")
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["coverage_summary"]["obligations"]["not_run"], 2)
        claim = swarm.claim(self.lib, self.run, "w2")
        swarm.record(self.lib, self.run, self.receipt(claim))
        report = swarm.report(self.lib, self.run)
        self.assertEqual(report["tasks"][0]["prior_outcomes"], ["failed"])
        self.assertEqual(report["coverage_summary"]["obligations"]["passed"], 2)
        self.assertTrue(report["coverage_summary"]["all_declared_requirements_passed"])
        self.assertFalse(report["product_ready"])

    def test_blocked_task_with_partial_criteria_is_not_requirement_pass(self):
        self.spec["tasks"][0]["requirement_coverage"] = self.coverage()
        self.plan()
        claim = swarm.claim(self.lib, self.run, "w1")
        receipt = self.receipt(claim, "blocked")
        receipt["criteria"] = receipt["criteria"][:1]
        swarm.record(self.lib, self.run, receipt)
        report = swarm.report(self.lib, self.run)
        row = report["tasks"][0]["requirement_results"][0]
        self.assertEqual(row["status"], "incomplete")
        self.assertEqual([o["status"] for o in row["obligations"]], ["passed", "not_run"])
        self.assertFalse(report["coverage_summary"]["all_declared_requirements_passed"])

    def test_multiprocess_claim_record_and_crash_resume(self):
        for i, resource in ((2, "browser1"), (3, "browser2"), (4, "browser3")):
            task = copy.deepcopy(self.spec["tasks"][0])
            task.update(id="T" + str(i), data_namespace="fixture" + str(i), resource_id=resource)
            self.spec["tasks"].append(task)
        self.plan()
        ctx = multiprocessing.get_context("spawn")
        ready, release, results = ctx.Barrier(4), ctx.Event(), ctx.Queue()
        workers = [ctx.Process(target=process_worker, args=(
            str(self.run), "process" + str(i), ready, release, results, outcome))
            for i, outcome in enumerate(("crash", "blocked", "inconclusive"))]
        workers[0].start()
        first_message = results.get(timeout=15)
        for worker in workers[1:]:
            worker.start()
        try:
            ready.wait(timeout=15)
            messages = [first_message] + [results.get(timeout=15) for _ in workers[1:]]
            self.assertEqual(len({pid for pid, _ in messages}), 3)
            claimed = [c for _, c in messages if c["claimed"]]
            self.assertEqual(len(claimed), 2)
            self.assertEqual(len({c["task"]["resource_id"] for c in claimed}), 2)
            self.assertEqual(swarm.report(self.lib, self.run)["counts"]["running"], 2)
            state = read_json(self.run / "swarm-state.json")["payload"]
            for claim in claimed:
                saved = next(e for e in state["tasks"] if e["task"]["id"] == claim["task"]["id"])
                self.assertEqual(saved["operation_id"], claim["operation_id"])
            release.set()
            for worker in workers:
                worker.join(15)
                self.assertEqual(worker.exitcode, 0)
            # A stopped process with no receipt remains running until expiry.
            with patch.object(swarm.time, "time", return_value=max(c["lease"]["expires_at"] for c in claimed) + 1):
                summary = swarm.report(self.lib, self.run)
            self.assertEqual(summary["counts"]["running"], 0)
            self.assertEqual(summary["counts"]["passed"], 0)
            self.assertFalse(swarm.claim(self.lib, self.run, "conflicting", "T2")["claimed"])
            uncertain = next((t for t in summary["tasks"] if t["status"] == "inconclusive"), None)
            if uncertain is not None:
                task_id = uncertain["task_id"]
                with self.assertRaises(EngineError):
                    swarm.retry(self.lib, self.run, task_id)
                swarm.retry(self.lib, self.run, task_id, reconciliation=dict(
                    operation_id=uncertain["operation_id"], attempt=uncertain["attempts"], outcome="not_executed",
                    note="All fixture child processes joined; no fixture action was invoked.", worker_stopped=True))
                resumed = swarm.claim(self.lib, self.run, "resumed", task_id)
                self.assertEqual(resumed["attempt"], 2)
                receipt = self.receipt(resumed, "blocked")
                receipt.update(steps=[], criteria=[], artifacts=[], reason="Denied before execution.")
                swarm.record(self.lib, self.run, receipt)
                with self.assertRaises(EngineError):
                    swarm.retry(self.lib, self.run, task_id)
        finally:
            release.set()
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                worker.join(5)
            results.close()


if __name__ == "__main__":
    unittest.main()
