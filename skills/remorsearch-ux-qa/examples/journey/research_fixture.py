"""Owned offline research contract. No network, actual source or participant.

Reuse the shipped native-input builder and real merge/gate/export/import code.
The gate's live-mode contract is exercised on invented local input; it is not
public acquisition or independent verification of that input's truth.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path

from uxpersonas.library import Library, PROFILE_FIELDS
from uxpersonas.research_intake import import_research
from uxresearch.canonical import canonical, digest
from uxresearch.cli import main as research_main
from uxresearch.storage import Store, atomic, read_json

SKILL = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("owned_native_research", SKILL / "examples/research/fixture.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def research_command(run, *args):
    with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
        code = research_main([str(args[0]), "--run", str(run), *map(str, args[1:])])
    if code:
        raise RuntimeError("Owned research diagnostic failed: " + err.getvalue())
    return json.loads(out.getvalue())


def attach(case, root, *, structured=False):
    root.mkdir(mode=0o700)
    research = native.build(root / "research")
    research_command(research, "merge", "--manifest", research / "axes.json",
                     "--search-ledger", research / "search-ledger.jsonl",
                     "--imports", research / "sanitized-imports.json",
                     "--returns", research / "returns/editors.json")
    bundle = read_json(research / "bundle.json")
    bundle["records"]["sources"][0]["summary"] = "Invented offline journey contract, not actual research."
    stamp = native.ledger.Run(research).now_iso()
    for records in bundle["records"].values():
        for record in records:
            for field in ("summary", "statement"):
                if field in record:
                    bundle["research"]["summary_attestations"].append(dict(
                        record_id=record["id"], field=field, content_sha256=digest(record[field]),
                        reviewed_by="owned-fixture", reviewed_at=stamp))
    atomic(research / "bundle.json", canonical(bundle))
    research_command(research, "gate", "--bundle", research / "bundle.json", "--write-bundle")
    bundle = read_json(research / "bundle.json")
    claims = [bundle["records"]["claims"][0]["id"]]
    with Library(case["library"]) as library:
        originals = [library.get("owned-product", task["persona_id"]) for task in case["tasks"]]
        if not structured:
            profiles = []
            for record in originals:
                profile = {key: copy.deepcopy(record["profile"][key]) for key in PROFILE_FIELDS}
                profile["assumptions"] = ["Owned offline research-contract fixture; not actual public research"]
                profiles.append(dict(persona_id=record["persona_id"], claim_ids=claims, **profile))
            imported = library.import_profiles(dict(
                schema_version="ux-persona-library-input.v1", product_id="owned-product",
                mode="gated_research", context=originals[0]["context"], personas=profiles,
                research=dict(run=str(research), bundle=str(research / "bundle.json"), gate=str(research / "gate.json"))))
        else:
            research_command(research, "persona-starter", "--bundle", research / "bundle.json", "--gate", research / "gate.json")
            starter = read_json(research / "persona.hypotheses.starter.json")
            hypotheses = dict(schema_version="ux-research-persona-hypotheses.v1",
                bundle_id=starter["bundle_id"], gate_bundle_input_sha256=starter["gate_bundle_input_sha256"],
                authored=True, personas=[])
            for index, record in enumerate(originals):
                profile = record["profile"]
                hypotheses["personas"].append(dict(persona_id="PER-owned-" + str(index),
                    label_ko=profile["label"], situation_ko="Owned synthetic recovery situation.",
                    motivation_claim_ids=claims, authored=True,
                    assumptions_ko=["Invented diagnostic hypothesis; no participant or public source."],
                    scenario=dict(scenario_id="SC-owned-" + str(index), task_goal_ko=profile["goals"][0],
                        context_ko=profile["contexts"][0], concrete_data={"choice": "owned"},
                        device_ids=[], a11y_conditions=[], expected_behavior_ko=profile["behaviors"][0],
                        expected_decision_ko="Inspect state before continuing.", likely_failure_ko="Earlier state may be lost.",
                        falsifying_product_test_ko="Check that earlier items survive rejected input.",
                        falsifying_interview_question_ko="Would preserved state help in this situation?", priority="P2")))
            path = root / "authored-hypotheses.json"
            atomic(path, canonical(hypotheses))
            research_command(research, "export-personas", "--bundle", research / "bundle.json",
                             "--gate", research / "gate.json", "--hypotheses", path, "--audience-id", "AU-owned-journey")
            with Store(research) as store:
                packet = store.committed("qa-personas.json")
                packet_sha = store.state()["outputs"]["qa-personas.json"]["sha256"]
            imported = import_research(library, research, dict(
                schema_version="ux-persona-research-mapping.v1", product_id="owned-product",
                context=originals[0]["context"], source_export=dict(bundle_id=packet["bundle_id"], sha256=packet_sha),
                personas=[dict(source_persona_id="PER-owned-" + str(index), persona_id=record["persona_id"],
                               requirement_ids=record["profile"]["requirement_ids"], expected_revision=record["revision"])
                          for index, record in enumerate(originals)]))
    return research, imported
