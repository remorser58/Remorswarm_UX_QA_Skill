"""Import current authored research hypotheses; never invent execution or support.

The optional structured profile projection is synthetic, inferred and unverified.
Only the committed export supplies its content. A mapping supplies product/PRD
links and explicit destination IDs, not replacement personas or claim grades.
"""
from __future__ import annotations

import copy
import re

from uxresearch.canonical import EngineError, canonical, digest
from uxresearch.commands import _persona_files
from uxresearch.engine import fresh
from uxresearch.ledger import Run, RunError
from uxresearch.merge import privacy_scan
from uxresearch.personas import ADAPTER as EXPORT_ADAPTER, UNKNOWN_FIELDS, claim_cards
from uxresearch.storage import Store, read_bytes, safe_path
from .library import (INPUT_SCHEMA, PROFILE_FIELDS, _research_binding_locked,
                      exact_keys, identifier, prd_context, strings, text_value)

MAPPING_SCHEMA = "ux-persona-research-mapping.v1"
ORIGIN_SCHEMA = "ux-persona-research-origin.v1"
ADAPTER = "uxpersonas-research-intake/1"
SCENARIO_FIELDS = {
    "id", "persona_id", "task", "task_id", "segment_id", "context_id", "priority",
    "motivation_claim_ids", "epistemic_status", "verification_status", "basis",
    "context_ko", "concrete_data", "device_ids", "a11y_conditions",
    "expected_behavior_ko", "expected_decision_ko", "likely_failure_ko",
    "falsifying_product_test_ko", "falsifying_interview_question_ko",
    "assumptions_ko", "motivation", "unknowns",
}
MOTIVATION_FIELDS = {
    "claim_id", "gate_status", "confidence", "counter_search_required",
    "counter_outcome", "counter_summary", "counter_call_ids", "counter_evidence_ids",
    "counter_source_ids", "counting_evidence_ids", "context_evidence_ids", "source_ids",
}
LIMITATIONS = [
    "Imported personas and scenarios remain authored synthetic hypotheses, not real participants.",
    "A passing local research gate does not independently authenticate source truth or user demand.",
    "No task, action, permission, lease, execution receipt or passing result is created.",
    "The host must author and review actual journey steps, PRD coverage and isolated execution conditions.",
]


def fail(code, reason):
    raise EngineError(code, reason,
                      next_step="Preserve existing research and personas. Correct the mapping or re-author against the current permitted export.")


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        fail("research_projection", "A lowercase SHA-256 fingerprint is required.")


def _source_id(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(prefix + r"[A-Za-z0-9_.:-]{1,64}", value):
        fail("research_mapping", "A source ID must match the exported persona/scenario format.")


def _unique(values):
    return list(dict.fromkeys(values))


def validate_paths(library_path, research_path):
    """Check existing permissions before Store opens or normalizes lock modes."""
    library, research = safe_path(library_path), safe_path(research_path)
    if library.is_relative_to(research) or research.is_relative_to(library):
        fail("research_import_path", "Library and research directories must be separate, non-nested locations.")
    for root in (library, research):
        if root.exists() and (not root.is_dir() or root.stat().st_mode & 0o077):
            fail("unsafe_mode", "Research intake requires private existing state directories.")
    if not research.is_dir():
        fail("research_missing", "An existing committed research run is required.")
    for name in ("engine.lock", "engine-state.json", "bundle.json", "gate.json"):
        read_bytes(research / name, private=True)
    for name in ("engine.lock", "library.json"):
        if (library / name).exists():
            read_bytes(library / name, private=True)
    return library, research


def _scenario(scenario, source_id, research_claims):
    exact_keys(scenario, SCENARIO_FIELDS)
    _source_id(scenario["id"], "SC-")
    if (scenario["persona_id"] != source_id or scenario["basis"] != "synthetic"
            or scenario["epistemic_status"] != "inferred"
            or scenario["verification_status"] != "unverified"
            or any(scenario[k] is not None for k in ("task_id", "segment_id", "context_id"))):
        fail("research_projection", "An imported scenario must remain an unexecuted authored hypothesis.")
    if scenario["priority"] not in {"P0", "P1", "P2", "P3"}:
        fail("research_projection", "Unknown authored scenario priority.")
    for field in ("task", "expected_behavior_ko", "expected_decision_ko", "likely_failure_ko",
                  "falsifying_product_test_ko", "falsifying_interview_question_ko"):
        text_value(scenario[field], field, 2000)
    if scenario["context_ko"] is not None:
        text_value(scenario["context_ko"], "context_ko", 1000)
    strings(scenario["assumptions_ko"], "assumptions_ko", maximum=16)
    if scenario["unknowns"] != list(UNKNOWN_FIELDS):
        fail("research_projection", "Population and frequency unknowns must remain explicit and unchanged.")
    for field in ("device_ids", "a11y_conditions"):
        strings(scenario[field], field, minimum=0, maximum=8)
    if not set(scenario["a11y_conditions"]) <= {"zoom", "screen_reader", "external_keyboard", "one_hand"}:
        fail("research_projection", "Unknown authored accessibility condition.")
    data = scenario["concrete_data"]
    if data is not None and not isinstance(data, dict):
        fail("research_projection", "Concrete task data must be an object or remain missing.")
    if len(canonical(data)) > 16384:
        fail("research_projection", "Concrete task data exceeds the bounded profile projection.")
    ids = strings(scenario["motivation_claim_ids"], "motivation_claim_ids", maximum=32)
    if any(cid not in research_claims for cid in ids):
        fail("research_projection", "Scenario motivation must match the stored current research binding.")
    motivation = scenario["motivation"]
    if not isinstance(motivation, list) or len(motivation) != len(ids):
        fail("research_projection", "Every scenario claim needs its unchanged motivation card.")
    seen = set()
    for card in motivation:
        exact_keys(card, MOTIVATION_FIELDS)
        cid = card["claim_id"]
        if cid in seen or cid not in ids:
            fail("research_projection", "Motivation cards must name the exact unique scenario claims.")
        seen.add(cid)
        bound = research_claims[cid]
        for field in ("gate_status", "counting_evidence_ids", "context_evidence_ids", "source_ids"):
            if card[field] != bound[field]:
                fail("research_projection", "Motivation status or evidence differs from the research binding.")
        if card["gate_status"] not in {
                "supported_high", "supported_medium", "single_voice", "lead_only",
                "conflicting", "stale", "needs_product_check"}:
            fail("research_projection", "Unfit research cannot become a saved scenario.")
        expected_confidence = {"supported_high": "high", "supported_medium": "medium"}.get(card["gate_status"])
        if card["confidence"] != expected_confidence or type(card["counter_search_required"]) is not bool:
            fail("research_projection", "Motivation confidence or counter-search state is invalid.")
        if card["counter_outcome"] not in {None, "none_found", "contradicts", "qualifies"}:
            fail("research_projection", "Unknown counter-search outcome.")
        if card["counter_summary"] is not None:
            text_value(card["counter_summary"], "counter_summary", 16000)
        for field in MOTIVATION_FIELDS - {
                "claim_id", "gate_status", "confidence", "counter_search_required", "counter_outcome", "counter_summary"}:
            strings(card[field], field, minimum=0, maximum=1024)
        if scenario["priority"] in {"P0", "P1"} and (
                card["gate_status"] not in {"supported_high", "supported_medium"}
                or not card["counter_search_required"] or not card["counter_call_ids"]):
            fail("research_projection", "High-priority scenarios retain their supported counter-search prerequisites.")


def validate_projection(record):
    """Strict additive validation on import and every later reuse/claim/report."""
    profile, provenance = record["profile"], record["provenance"]
    exact_keys(profile, PROFILE_FIELDS | {"research_scenarios"})
    if provenance.get("mode") != "gated_research" or "research_export" not in provenance:
        fail("research_projection", "A research scenario projection requires its gated research origin.")
    origin = provenance["research_export"]
    exact_keys(origin, {"schema_version", "adapter_revision", "source_bundle_id", "qa_bundle_id",
                        "packet_sha256", "source_persona_id", "scenario_ids", "projection_sha256"})
    if origin["schema_version"] != ORIGIN_SCHEMA or origin["adapter_revision"] != ADAPTER:
        fail("research_projection", "Unknown research projection version.")
    _source_id(origin["source_persona_id"], "PER-")
    _sha(origin["packet_sha256"])
    _sha(origin["projection_sha256"])
    if not isinstance(origin["qa_bundle_id"], str) or not re.fullmatch(r"QAB-[0-9a-f]{24}", origin["qa_bundle_id"]):
        fail("research_projection", "The origin must identify a committed persona export.")
    research = provenance["research"]
    if origin["source_bundle_id"] != research["source_bundle_id"]:
        fail("research_projection", "The projection refers to another research bundle.")
    scenarios = profile["research_scenarios"]
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 24 or len(canonical(scenarios)) > 131072:
        fail("research_projection", "A profile requires a bounded nonempty scenario projection.")
    source_id = origin["source_persona_id"]
    claims = {row["claim_id"]: row for row in research["claims"]}
    for scenario in scenarios:
        _scenario(scenario, source_id, claims)
    scenario_ids = [scenario["id"] for scenario in scenarios]
    if len(set(scenario_ids)) != len(scenario_ids) or origin["scenario_ids"] != scenario_ids:
        fail("research_projection", "Scenario IDs must match the origin without duplication.")
    if set(provenance["claim_ids"]) != {cid for scenario in scenarios for cid in scenario["motivation_claim_ids"]}:
        fail("research_projection", "Stored claims must exactly cover the imported scenarios.")
    if origin["projection_sha256"] != digest(scenarios):
        fail("research_projection", "Scenario content does not match its projection fingerprint.")
    text_value(profile["label"], "label", 160)
    for field in PROFILE_FIELDS - {"label"}:
        strings(profile[field], field)
    if profile["goals"] != _unique([s["task"] for s in scenarios]):
        fail("research_projection", "Profile goals must retain every imported scenario goal.")
    expected = _unique([value for s in scenarios for value in (
        "Expected behavior (hypothesis): " + s["expected_behavior_ko"],
        "Expected decision (hypothesis): " + s["expected_decision_ko"])])
    if profile["behaviors"] != expected:
        fail("research_projection", "Profile behaviors must retain the authored expectations as hypotheses.")
    if any(value not in profile["assumptions"] for s in scenarios for value in s["assumptions_ko"]):
        fail("research_projection", "Scenario assumptions cannot be omitted from the profile.")
    if any(value not in profile["unknowns"] for s in scenarios for value in s["unknowns"]):
        fail("research_projection", "Scenario unknowns cannot be omitted from the profile.")
    if privacy_scan(profile):
        fail("persona_privacy", "The imported projection contains personal identifier patterns.")


def _snapshot(run, store, expected):
    bundle, gate = fresh(run, store, run.path / "bundle.json", run.path / "gate.json")
    if gate["mode"] != "live":
        fail("research_not_live", "Only a current passing live research contract can be imported.")
    _persona_files(run, store, bundle, gate)
    packet = store.committed("qa-personas.json")
    actual = dict(bundle_id=packet["bundle_id"], sha256=store.state()["outputs"]["qa-personas.json"]["sha256"])
    if expected != actual:
        fail("stale_persona_export", "The mapping does not identify the current committed persona export.")
    return bundle, gate, packet


def import_research(library, research_path, mapping):
    """Hold Library then Research through one all-or-nothing library publication."""
    if library.lock is None:
        fail("persona_lock", "Use the existing Library context while importing research.")
    _, research_path = validate_paths(library.root, research_path)
    exact_keys(mapping, {"schema_version", "product_id", "context", "source_export", "personas"}, {"review_days"})
    if mapping["schema_version"] != MAPPING_SCHEMA:
        fail("research_mapping", "Unknown research-to-library mapping schema.")
    product = identifier(mapping["product_id"], "product id")
    context = prd_context(mapping["context"])
    exact_keys(mapping["source_export"], {"bundle_id", "sha256"})
    _sha(mapping["source_export"]["sha256"])
    rows = mapping["personas"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        fail("research_mapping", "Select 1..32 exported personas explicitly.")
    source_ids, destination_ids = set(), set()
    for row in rows:
        exact_keys(row, {"source_persona_id", "persona_id", "requirement_ids"}, {"expected_revision"})
        _source_id(row["source_persona_id"], "PER-")
        identifier(row["persona_id"], "destination persona id")
        if not row["persona_id"].startswith("PER-"):
            fail("research_mapping", "Destination persona IDs must start with PER-.")
        strings(row["requirement_ids"], "requirement_ids")
        if row["source_persona_id"] in source_ids or row["persona_id"] in destination_ids:
            fail("research_mapping", "Source and destination persona mappings must each be unique.")
        source_ids.add(row["source_persona_id"])
        destination_ids.add(row["persona_id"])
        expected = row.get("expected_revision")
        if expected is not None and (type(expected) is not int or expected < 0):
            fail("research_mapping", "Expected revisions must be nonnegative integers.")
    try:
        run = Run(research_path)
    except RunError as exc:
        raise EngineError("research_policy", "Research policy or run files are invalid.") from exc
    with Store(research_path) as store:
        bundle, gate, packet = _snapshot(run, store, mapping["source_export"])
        exported = {p["id"]: p for p in packet["records"]["personas"]}
        cards = {card["claim_id"]: card for card in claim_cards(bundle, gate)}
        profiles, projections = [], {}
        for row in rows:
            source = exported.get(row["source_persona_id"])
            if (not source or source.get("basis") != "synthetic" or source.get("adapter_revision") != EXPORT_ADAPTER
                    or source.get("stop_reason") != "authored_synthetic_no_dataset"):
                fail("research_mapping", "A selected source is not a current authored research-export persona.")
            attributes = source["original_attributes"]
            exact_keys(attributes, {"motivation_claim_ids", "situation_ko"})
            assumptions = source["scenario_assumptions"]
            exact_keys(assumptions, {"situation_ko", "assumptions_ko", "context_ko", "device_ids", "a11y_conditions"})
            if attributes["situation_ko"] != assumptions["situation_ko"]:
                fail("research_projection", "Exported situation annotations disagree.")
            scenarios = sorted(
                [copy.deepcopy(s) for s in packet["records"]["scenarios"] if s.get("persona_id") == source["id"]],
                key=lambda s: s["id"],
            )
            if not scenarios:
                fail("research_mapping", "The selected persona has no authored scenario.")
            ids = sorted({cid for scenario in scenarios for cid in scenario["motivation_claim_ids"]})
            if set(ids) != set(attributes["motivation_claim_ids"]):
                fail("research_projection", "Persona and scenario motivation links disagree.")
            for scenario in scenarios:
                for card in scenario["motivation"]:
                    current = cards.get(card["claim_id"])
                    if not current or not current["exportable"] or card != {k: current[k] for k in MOTIVATION_FIELDS}:
                        fail("unsafe_motivation", "An exported scenario no longer has its exact safe current motivation.")
            profiles.append(dict(
                persona_id=row["persona_id"], label=source["label_ko"],
                goals=_unique([s["task"] for s in scenarios]),
                behaviors=_unique([value for s in scenarios for value in (
                    "Expected behavior (hypothesis): " + s["expected_behavior_ko"],
                    "Expected decision (hypothesis): " + s["expected_decision_ko"])]),
                contexts=_unique([attributes["situation_ko"]] + [s["context_ko"] for s in scenarios if s["context_ko"]]),
                assumptions=_unique(assumptions["assumptions_ko"] + [value for s in scenarios for value in s["assumptions_ko"]]),
                unknowns=_unique([value for s in scenarios for value in s["unknowns"]]),
                requirement_ids=sorted(row["requirement_ids"]), claim_ids=ids,
            ))
            projections[row["persona_id"]] = (row, scenarios)
        research = dict(run=str(research_path), bundle=str(research_path / "bundle.json"), gate=str(research_path / "gate.json"))
        doc = dict(schema_version=INPUT_SCHEMA, product_id=product, context=context,
                   mode="gated_research", research=research, personas=profiles,
                   review_days=mapping.get("review_days", 30))
        prepared = library._prepare_profiles(
            doc, research_validator=lambda refs, ids: _research_binding_locked(refs, ids, run, store))
        current_state = library._state()
        # Eligibility and publication share one batch instant so a deadline
        # crossing cannot turn an unchanged retry into an unrequested renewal.
        now = library.clock()
        for key, body in prepared:
            row, scenarios = projections[body["persona_id"]]
            body["profile"]["research_scenarios"] = scenarios
            body["provenance"]["research_export"] = dict(
                schema_version=ORIGIN_SCHEMA, adapter_revision=ADAPTER,
                source_bundle_id=bundle["bundle_id"], qa_bundle_id=packet["bundle_id"],
                packet_sha256=mapping["source_export"]["sha256"],
                source_persona_id=row["source_persona_id"],
                scenario_ids=[s["id"] for s in scenarios], projection_sha256=digest(scenarios),
            )
            validate_projection(body)
            history = current_state["entries"].get(key, [])
            latest = history[-1] if history else None
            if latest and latest["status"] != "active":
                fail("persona_retired", "A retired persona cannot be reactivated by copying an export.")
            if latest:
                fields = ("product_id", "persona_id", "basis", "review_days", "profile", "context", "provenance")
                if any(field not in latest for field in fields) or digest(
                        {field: latest[field] for field in fields}) != latest.get("profile_sha256"):
                    fail("persona_integrity", "The existing destination content differs from its stored fingerprint.")
                if "research_scenarios" in latest["profile"] or "research_export" in latest["provenance"]:
                    validate_projection(latest)
            unchanged = latest and latest["profile_sha256"] == digest(body) and latest["review_after"] > now
            if not unchanged and row.get("expected_revision", 0) != (latest["revision"] if latest else 0):
                fail("research_import_conflict", "A destination revision changed or requires an explicit reviewed update.")
        def recheck():
            _snapshot(run, store, mapping["source_export"])
            prd_context(context)
        recheck()
        result = library._commit_profiles(prepared, before_save=recheck, now=now)
        return dict(schema_version="ux-persona-research-intake.v1", **result,
                    source_export=copy.deepcopy(mapping["source_export"]),
                    limitations=LIMITATIONS,
                    next_steps=["Use reuse to inspect the saved hypotheses and research_scenarios.",
                                "Author actual journey actions, criteria, PRD coverage and isolation, then use plan and claim."])
