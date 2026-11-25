"""Owned offline evidence-admission regressions, never public/user-effect proof.

The real merge, gate, persona library and CLI run against invented native input.
A live-mode local gate validates that input contract; it does not turn this
fixture into an authentic community source or a real participant.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import _paths
import engine_release_factory as fixture_factory
from test_persona_library import profile_input
from ergoqa.png import encode, new_image
from uxpersonas import swarm
from uxpersonas.cli import main as persona_main
from uxpersonas.library import Library, PROFILE_FIELDS
from uxresearch.canonical import byte_digest, canonical, digest
from uxresearch.cli import main as research_main
from uxresearch.grading import target_hash
from uxresearch.ledger import Run
from uxresearch.personas import claim_cards
from uxresearch.storage import Store, atomic, read_json


ENTRYPOINT = Path(os.environ.get(
    "REMORSEARCH_PERSONA_TEST_ENTRYPOINT", str(_paths.SKILL / "scripts/ux_personas.py")))


def command(main, arguments, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = main(list(map(str, arguments)), **kwargs)
    return code, json.loads(out.getvalue() or err.getvalue())


def research_fixture(root, relation="support", *, epistemic="observed"):
    now = time.time()
    run = fixture_factory.fixture.build(root / "research", clock=lambda: now)
    returned = read_json(run / "returns/editors.json")
    returned["excerpts"][0]["epistemic_status"] = epistemic
    claim = returned["candidate_claims"][0]
    claim.update(excerpt_ids=[], context_excerpt_ids=[], counter_excerpt_ids=[],
                 audience_values=[])
    if relation in {"support", "support_counter"}:
        claim["excerpt_ids"] = ["excerpt"]
    if relation in {"context", "context_counter"}:
        claim["context_excerpt_ids"] = ["excerpt"]
    if relation in {"counter", "support_counter", "context_counter"}:
        claim["counter_excerpt_ids"] = ["excerpt"]
    atomic(run / "returns/editors.json", canonical(returned))
    code, result = command(research_main, [
        "merge", "--run", run, "--manifest", run / "axes.json",
        "--search-ledger", run / "search-ledger.jsonl",
        "--imports", run / "sanitized-imports.json",
        "--returns", run / "returns/editors.json",
    ], clock=lambda: now)
    if code:
        raise AssertionError(result)
    bundle = read_json(run / "bundle.json")
    bundle["records"]["sources"][0]["summary"] = "Invented offline admission fixture."
    stamp = Run(run, clock=lambda: now).now_iso()
    for records in bundle["records"].values():
        for record in records:
            for field in ("summary", "statement"):
                if field in record:
                    bundle["research"]["summary_attestations"].append({
                        "record_id": record["id"], "field": field,
                        "content_sha256": digest(record[field]),
                        "reviewed_by": "owned-fixture", "reviewed_at": stamp,
                    })
    atomic(run / "bundle.json", canonical(bundle))
    code, result = command(research_main, [
        "gate", "--run", run, "--bundle", run / "bundle.json", "--write-bundle",
    ], clock=lambda: now)
    if code:
        raise AssertionError(result)
    bundle, gate = read_json(run / "bundle.json"), read_json(run / "gate.json")
    doc = profile_input(root)
    doc.update(mode="gated_research", research={
        "run": str(run), "bundle": str(run / "bundle.json"),
        "gate": str(run / "gate.json"),
    })
    doc["personas"][0]["claim_ids"] = [bundle["records"]["claims"][0]["id"]]
    return run, bundle, gate, doc


class PersonaEvidenceAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="remorsearch-admission-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.library = self.root / "library"

    def process(self, *args, library=None):
        result = subprocess.run(
            [sys.executable, str(ENTRYPOINT),
             *(["personas"] if ENTRYPOINT.name == "remorsearch.py" else []),
             str(args[0]), "--library", str(library or self.library), *map(str, args[1:])],
            cwd=self.root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True, text=True, timeout=20)
        return result.returncode, json.loads(result.stdout or result.stderr)

    def write_input(self, name, value):
        path = self.root / name
        atomic(path, canonical(value))
        return path

    def snapshot(self):
        return {str(path.relative_to(self.root)): byte_digest(path.read_bytes())
                for path in self.root.rglob("*") if path.is_file()}

    def legacy_snapshot(self, relation="counter", *, epistemic="observed"):
        """Serialize the old admission contract; all validation under test is real.

        No old executable, gate mock or live data is used. The fully hash-bound
        profile and completed receipts model records an earlier version accepted.
        """
        research, bundle, gate, doc = research_fixture(self.root, relation, epistemic=epistemic)
        row, item = gate["claims"][0], doc["personas"][0]
        binding = dict(doc["research"], source_bundle_id=bundle["bundle_id"],
            bundle_input_sha256=gate["bundle_input_sha256"],
            process_input_sha256=gate["process_input_sha256"], valid_until=gate["valid_until"],
            claims=[dict(claim_id=row["claim_id"], gate_status=row["status"],
                source_ids=[bundle["records"]["sources"][0]["id"]],
                counting_evidence_ids=row["counting_evidence_ids"],
                context_evidence_ids=row["context_evidence_ids"])])
        body = dict(product_id=doc["product_id"], persona_id=item["persona_id"],
            basis="synthetic", review_days=30, profile={key: item[key] for key in PROFILE_FIELDS},
            context=doc["context"], provenance=dict(mode="gated_research",
                claim_ids=item["claim_ids"], research=binding))
        now = time.time()
        record = dict(body, revision=1, profile_sha256=digest(body), status="active",
                      created_at=now, review_after=now + 30 * 86400)
        with Library(self.library) as library:
            library._save(dict(schema_version="ux-persona-library.v1",
                               entries={"sample/PER-cautious": [record]}))
        build = self.root / "build.txt"
        atomic(build, b"Owned legacy admission fixture, not a live product.\n")
        spec = dict(schema_version=swarm.SCHEMA, product_id="sample",
            build=dict(id="fixture", artifact_path=str(build), sha256=byte_digest(build.read_bytes())),
            tasks=[dict(id="T-one", persona_id="PER-cautious", requirement_ids=["local-results"],
                goal="Inspect local results", starting_state="Owned isolated fixture",
                actions=["Select", "Return"], decisions=["Inspect the saved choice"],
                success_criteria=["Choice retained"], recovery_criteria=["Return restores choice"],
                data_namespace="fixture-one", resource_id="owned-one", side_effects="read_only",
                stop_conditions=["Stop at real data or lease expiry"])])
        persona_binding = {key: record[key] for key in ("persona_id", "revision", "profile_sha256")}
        persona_binding["prd_sha256"] = doc["context"]["prd_sha256"]
        runs, receipts = [], []
        for name in ("before", "after"):
            run = self.root / name
            evidence_path = run / "evidence/T-one/1"
            evidence_path.mkdir(parents=True, mode=0o700)
            for path in (run, run / "evidence", run / "evidence/T-one"):
                path.chmod(0o700)
            artifacts = []
            for aid, kind, raw in (
                ("log", "execution_log", b"Invented legacy receipt: select and return.\n"),
                ("png", "screenshot", encode(new_image(2, 2))),
            ):
                path = evidence_path / aid
                atomic(path, raw)
                artifacts.append(dict(id=aid, kind=kind, path=str(path.relative_to(run)),
                                      sha256=byte_digest(raw)))
            lease = dict(worker_id="legacy-fixture", lease_token="a" * 48, expires_at=now + 300)
            receipt = dict(schema_version="ux-persona-swarm-receipt.v1", task_id="T-one",
                worker_id=lease["worker_id"], lease_token=lease["lease_token"],
                build_sha256=spec["build"]["sha256"], persona_revision=1,
                profile_sha256=record["profile_sha256"], outcome="passed",
                reason="Invented owned fixture receipt, not live UX proof.",
                steps=[dict(action="Select and return", observation="Invented retained value.",
                            evidence_ids=["log", "png"])],
                criteria=[dict(kind=kind, index=0, status="passed",
                    observation="Invented retained value.", evidence_ids=["log", "png"])
                    for kind in ("success", "recovery")], artifacts=artifacts)
            entry = dict(task=spec["tasks"][0], binding=persona_binding, status="passed",
                attempts=1, history=[], lease=lease, operation_id="uxop-" + "b" * 32,
                receipt=receipt, reason=receipt["reason"])
            # Establish that the receipt itself is valid; rejection must concern research.
            swarm._receipt(run, entry, receipt)
            state = dict(product_id="sample", build=spec["build"], max_parallel=1,
                         lease_seconds=300, max_attempts=2, tasks=[entry], created_at=now)
            with Store(run):
                swarm._save(run, state)
            runs.append(run)
            receipts.append(receipt)
        return research, bundle, spec, runs, receipts

    def test_counter_only_research_cannot_be_imported_as_motivation(self):
        _, bundle, gate, doc = research_fixture(self.root, "counter")
        row = gate["claims"][0]
        self.assertEqual(gate["result"], "pass")
        self.assertEqual(row["status"], "conflicting")
        self.assertEqual(row["counting_evidence_ids"], [])
        self.assertEqual(row["context_evidence_ids"], [])
        self.assertTrue(row["counter_evidence_ids"])
        path = self.root / "profile.json"
        atomic(path, canonical(doc))
        code, result = command(persona_main, [
            "import", "--library", self.library, "--input", path,
        ])
        self.assertEqual(code, 2, "Counter-only research was accepted and persisted: " + repr(result))
        self.assertEqual(result["issue"]["code"], "unsafe_motivation")
        self.assertFalse((self.library / "library.json").exists())

    def test_inference_only_research_cannot_be_imported_as_observed_context(self):
        for relation in ("support", "context"):
            for epistemic in ("inferred", "unknown"):
                with self.subTest(relation=relation, epistemic=epistemic):
                    root = self.root / (relation + "-" + epistemic)
                    root.mkdir()
                    _, bundle, gate, doc = research_fixture(root, relation, epistemic=epistemic)
                    self.assertEqual(gate["result"], "pass")
                    path = root / "profile.json"
                    atomic(path, canonical(doc))
                    code, result = command(persona_main, [
                        "import", "--library", root / "library", "--input", path,
                    ])
                    self.assertEqual(code, 2, result)
                    self.assertEqual(result["issue"]["code"], "unsafe_motivation")
                    self.assertFalse((root / "library" / "library.json").exists())

    def test_mixed_grade_e_evidence_is_not_rescued_by_aggregate_status(self):
        good = fixture_factory.source(1, "measured")
        bad = fixture_factory.source(2, "none")
        first, second = fixture_factory.evidence(1, good), fixture_factory.evidence(2, bad)
        bundle = fixture_factory.bundle([good, bad], [first, second],
            fixture_factory.claim(support=[first["id"], second["id"]]))
        rows, issues, _ = fixture_factory.grade(bundle)
        self.assertEqual(issues, [])
        self.assertEqual(rows[0]["status"], "supported_high")
        self.assertIn("E", [grade["final_grade"] for grade in rows[0]["grades"]])
        self.assertFalse(claim_cards(bundle, {"claims": rows})[0]["exportable"])

    def test_synthetic_context_is_not_research_motivation(self):
        source = fixture_factory.source(1, "none")
        evidence = fixture_factory.evidence(1, source)
        bundle = fixture_factory.bundle([source], [evidence], fixture_factory.claim(
            context_evidence_ids=[evidence["id"]], research_context_evidence_ids=[evidence["id"]]))
        rows, issues, _ = fixture_factory.grade(bundle)
        self.assertEqual(issues, [])
        self.assertFalse(claim_cards(bundle, {"claims": rows})[0]["exportable"])

    def test_explicit_llm_context_cannot_hide_behind_a_measured_family(self):
        source = fixture_factory.source(1, "measured", source_type="llm_output")
        evidence = fixture_factory.evidence(1, source)
        bundle = fixture_factory.bundle([source], [evidence], fixture_factory.claim(
            context_evidence_ids=[evidence["id"]], research_context_evidence_ids=[evidence["id"]]))
        rows, issues, _ = fixture_factory.grade(bundle)
        self.assertEqual(issues, [])
        self.assertFalse(claim_cards(bundle, {"claims": rows})[0]["exportable"])

    def test_observed_context_and_support_reuse_after_process_restart(self):
        for relation in ("support", "context"):
            with self.subTest(relation=relation):
                root = self.root / relation
                root.mkdir()
                _, _, _, doc = research_fixture(root, relation)
                extra = copy.deepcopy(doc["personas"][0])
                extra.update(persona_id="PER-returner", label="Returning comparison fixture")
                doc["personas"].append(extra)
                path = self.write_input(relation + ".json", doc)
                library = root / "library"
                code, imported = self.process("import", "--input", path, library=library)
                self.assertEqual(code, 0, imported)
                self.assertEqual(len(imported["imported"]), 2)
                before = (library / "library.json").read_bytes()
                code, repeated = self.process("import", "--input", path, library=library)
                self.assertEqual(code, 0, repeated)
                self.assertTrue(all(not row["changed"] for row in repeated["imported"]))
                for item in doc["personas"]:
                    code, reused = self.process("reuse", "--product", "sample",
                        "--persona", item["persona_id"], library=library)
                    self.assertEqual(code, 0, reused)
                    self.assertEqual(reused["revision"], 1)
                    self.assertEqual(reused["provenance"]["mode"], "gated_research")
                self.assertEqual((library / "library.json").read_bytes(), before)

    def test_prd_hypothesis_stays_exploratory_and_reusable(self):
        doc = profile_input(self.root)
        code, result = self.process("import", "--input", self.write_input("prd.json", doc))
        self.assertEqual(code, 0, result)
        code, reused = self.process("reuse", "--product", "sample", "--persona", "PER-cautious")
        self.assertEqual(code, 0, reused)
        self.assertEqual(reused["provenance"]["mode"], "prd_hypothesis")
        self.assertEqual(reused["basis"], "synthetic")

    def test_no_references_cannot_be_imported(self):
        _, _, _, doc = research_fixture(self.root, "none")
        code, result = self.process("import", "--input", self.write_input("empty.json", doc))
        self.assertEqual(code, 2, result)
        self.assertEqual(result["issue"]["code"], "unsafe_motivation")
        self.assertFalse((self.library / "library.json").exists())

    def test_legacy_counter_only_blocks_reuse_dispatch_record_report_and_compare(self):
        _, _, spec, runs, receipts = self.legacy_snapshot()
        plan = self.write_input("plan.json", spec)
        receipt = self.write_input("receipt.json", receipts[0])
        before = self.snapshot()
        for args in (
            ("reuse", "--product", "sample", "--persona", "PER-cautious"),
            ("plan", "--run", self.root / "new", "--input", plan),
            ("claim", "--run", runs[0], "--worker", "new-worker"),
            ("record", "--run", runs[0], "--input", receipt),
            ("retry", "--run", runs[0], "--task", "T-one"),
            ("report", "--run", runs[0]),
            ("compare", "--baseline", runs[0], "--run", runs[1], "--format", "json"),
        ):
            with self.subTest(command=args[0]):
                code, result = self.process(*args)
                self.assertEqual(code, 2, result)
                self.assertEqual(result["issue"]["code"], "unsafe_motivation")
                self.assertTrue(result["issue"]["next_step"])
                self.assertNotIn("Local data control", canonical(result).decode())
                self.assertEqual(self.snapshot(), before)
        code, result = self.process("list")
        self.assertEqual(code, 0)
        self.assertFalse(result["personas"][0]["reusable"])
        self.assertEqual(self.snapshot(), before)
        code, pruned = self.process("prune")
        self.assertEqual(code, 0, pruned)
        self.assertEqual(pruned["retired"], [])
        self.assertEqual(self.snapshot(), before)

    def test_legacy_inferred_context_cannot_restore_a_passing_report(self):
        _, _, _, runs, _ = self.legacy_snapshot("context", epistemic="inferred")
        before = self.snapshot()
        code, result = self.process("report", "--run", runs[0])
        self.assertEqual(code, 2, result)
        self.assertEqual(result["issue"]["code"], "unsafe_motivation")
        self.assertEqual(self.snapshot(), before)

    def test_confirmed_withdrawal_still_prunes_invalid_legacy_profile(self):
        research, bundle, _, _, _ = self.legacy_snapshot()
        bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "withdrawn"
        with Store(research) as store:
            store.publish("owned-confirmed-withdrawal", {"bundle.json": bundle})
        code, result = self.process("prune")
        self.assertEqual(code, 0, result)
        self.assertEqual(len(result["retired"]), 1)
        self.assertNotIn("Local data control", (self.library / "library.json").read_text())

    def test_pending_withdrawal_preserves_invalid_legacy_profile(self):
        research, bundle, _, _, _ = self.legacy_snapshot()
        bundle["records"]["sources"][0]["captures"][0]["metadata"]["retention_status"] = "withdrawn"
        atomic(research / "bundle.json", canonical(bundle))
        before = (self.library / "library.json").read_bytes()
        code, result = self.process("prune")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["blockers"][0]["code"], "retention_review_pending")
        self.assertEqual((self.library / "library.json").read_bytes(), before)

    def test_concurrent_safe_and_counter_only_import_preserves_safe_profile(self):
        inputs = []
        for relation in ("support", "counter"):
            root = self.root / relation
            root.mkdir()
            _, _, _, doc = research_fixture(root, relation)
            doc["personas"][0]["persona_id"] = "PER-" + relation
            inputs.append(self.write_input(relation + ".json", doc))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda path: self.process("import", "--input", path), inputs))
        self.assertEqual([code for code, _ in results], [0, 2], results)
        code, listed = self.process("list")
        self.assertEqual(code, 0, listed)
        self.assertEqual([p["persona_id"] for p in listed["personas"]], ["PER-support"])
        self.assertTrue(listed["personas"][0]["reusable"])

    def test_unsafe_library_permissions_are_not_bypassed(self):
        _, _, _, doc = research_fixture(self.root)
        code, imported = self.process("import", "--input", self.write_input("valid.json", doc))
        self.assertEqual(code, 0, imported)
        state = self.library / "library.json"
        original = state.read_bytes()
        state.chmod(0o644)
        code, result = self.process("reuse", "--product", "sample", "--persona", "PER-cautious")
        self.assertEqual(code, 2, result)
        self.assertEqual(result["issue"]["code"], "unsafe_mode")
        self.assertEqual(state.read_bytes(), original)

    def test_virtual_context_requires_exact_capture_review(self):
        for outcome, expected in ((None, False), ("confirmed", False), ("not_confirmed", True)):
            with self.subTest(outcome=outcome):
                source = fixture_factory.source(1, flags={"virtual_person_hits": [
                    dict(id="virtual", code="disclosed_virtual_person", position="body")]})
                # Real merge inherits capture flags into the evidence record.
                evidence = fixture_factory.evidence(1, source, flags=copy.deepcopy(source["flags"]))
                bundle = fixture_factory.bundle([source], [evidence], fixture_factory.claim(
                    context_evidence_ids=[evidence["id"]], research_context_evidence_ids=[evidence["id"]]))
                if outcome:
                    decision = dict(id="decision", kind="virtual_person", target_kind="source",
                        target_id=source["id"], capture_ref=evidence["capture_ref"], flag_ids=["virtual"],
                        reviewer_ref="owned-fixture", checked_at="2026-09-20T00:00:00Z",
                        outcome=outcome, basis_evidence_ids=[], reason="Owned review fixture.")
                    decision["target_sha256"] = target_hash(decision, bundle, fixture_factory.receipt(bundle))
                    bundle["research"]["verifier_decisions"] = [decision]
                rows, issues, _ = fixture_factory.grade(bundle)
                self.assertEqual(issues, [])
                self.assertEqual(claim_cards(bundle, {"claims": rows})[0]["exportable"], expected)
                if outcome == "not_confirmed":
                    # A source clearance must not clear a separate excerpt flag.
                    evidence["flags"]["virtual_person_hits"].append(
                        dict(id="excerpt-virtual", code="disclosed_virtual_person", position="body"))
                    rows, issues, _ = fixture_factory.grade(bundle)
                    self.assertEqual(issues, [])
                    self.assertFalse(claim_cards(bundle, {"claims": rows})[0]["exportable"])
                    extra = dict(decision, id="excerpt-decision", target_kind="evidence",
                                 target_id=evidence["id"], flag_ids=["excerpt-virtual"])
                    extra["target_sha256"] = target_hash(extra, bundle, fixture_factory.receipt(bundle))
                    bundle["research"]["verifier_decisions"].append(extra)
                    rows, issues, _ = fixture_factory.grade(bundle)
                    self.assertEqual(issues, [])
                    self.assertTrue(claim_cards(bundle, {"claims": rows})[0]["exportable"])

    def test_injection_context_is_not_hidden_by_safe_support(self):
        source = fixture_factory.source(1, "measured")
        good = fixture_factory.evidence(1, source)
        bad = fixture_factory.evidence(2, source, flags={"injection_flags": [
            dict(id="injection", code="instruction_override", position="body")]})
        bundle = fixture_factory.bundle([source], [good, bad], fixture_factory.claim(
            support=[good["id"]], research_context_evidence_ids=[bad["id"]],
            context_evidence_ids=[bad["id"]]))
        rows, issues, _ = fixture_factory.grade(bundle)
        self.assertEqual(issues, [])
        card = claim_cards(bundle, {"claims": rows})[0]
        self.assertFalse(card["exportable"])
        self.assertEqual(set(card), {"claim_id", "gate_status", "exportable", "blocked_reason"})

    def test_distinct_counter_is_preserved_but_overlap_is_not_counted_as_motivation(self):
        first, second = fixture_factory.source(1), fixture_factory.source(2)
        good, contrary = fixture_factory.evidence(1, first), fixture_factory.evidence(2, second)
        bundle = fixture_factory.bundle([first, second], [good, contrary], fixture_factory.claim(
            support=[good["id"]], counter=[contrary["id"]],
            context_evidence_ids=[contrary["id"]], research_context_evidence_ids=[contrary["id"]]))
        rows, issues, _ = fixture_factory.grade(bundle)
        self.assertEqual(issues, [])
        card = claim_cards(bundle, {"claims": rows})[0]
        self.assertTrue(card["exportable"], card)
        self.assertEqual(card["gate_status"], "conflicting")
        self.assertEqual(card["counting_evidence_ids"], [good["id"]])
        self.assertEqual(card["context_evidence_ids"], [])
        self.assertEqual(card["counter_evidence_ids"], [contrary["id"]])
        self.assertEqual(set(card["source_ids"]), {first["id"], second["id"]})

    def test_counter_cannot_be_relabelled_as_support_or_context(self):
        for relation in ("support_counter", "context_counter"):
            with self.subTest(relation=relation):
                root = self.root / relation
                root.mkdir()
                _, bundle, gate, _ = research_fixture(root, relation)
                self.assertEqual(gate["result"], "pass")
                card = claim_cards(bundle, gate)[0]
                self.assertFalse(card["exportable"], card)
                self.assertEqual(set(card), {
                    "claim_id", "gate_status", "exportable", "blocked_reason",
                })
                self.assertNotIn(bundle["records"]["claims"][0]["statement"],
                                 canonical(card).decode())


if __name__ == "__main__":
    unittest.main()
