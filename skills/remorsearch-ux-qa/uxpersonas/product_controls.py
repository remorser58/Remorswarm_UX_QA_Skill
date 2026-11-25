"""PRD-bound run choices for an existing host UI; never starts a worker or model."""
from __future__ import annotations

import copy
from pathlib import Path

from uxresearch.canonical import byte_digest, canonical, digest
from uxresearch.storage import read_bytes, read_json, safe_path
from .library import exact_keys, fail, identifier, prd_context, strings, text_value

SCHEMA = "ux-product-controls.v1"
SELECTION = "ux-product-selection.v1"


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        fail("controls_limits", f"{name} must be an integer from {low} to {high}.")
    return value


def _binding(value):
    exact_keys(value, {"path", "sha256"})
    path = safe_path(value["path"])
    if byte_digest(read_bytes(path)) != value["sha256"]:
        fail("controls_stale", "The reviewed UI baseline bytes changed.")
    return {"path": str(path), "sha256": value["sha256"]}


def validate(spec):
    exact_keys(spec, {"schema_version", "product_id", "context", "personas",
                      "models", "tasks", "style", "limits"}, {"excluded_requirements"})
    if spec["schema_version"] != SCHEMA:
        fail("controls_schema", "Unsupported product controls schema.")
    if len(canonical(spec)) > 1024 * 1024:
        fail("controls_limits", "The control proposal exceeds its 1 MiB resource limit.")
    identifier(spec["product_id"])
    result = copy.deepcopy(spec)
    result["context"] = prd_context(spec["context"])
    requirements = {r["id"] for r in result["context"]["requirements"]}
    refs = spec["personas"]
    if not isinstance(refs, list) or not 1 <= len(refs) <= 1000:
        fail("controls_personas", "Offer 1..1000 distinct saved personas.")
    seen = set()
    for row in refs:
        exact_keys(row, {"persona_id", "revision"})
        identifier(row["persona_id"])
        integer(row["revision"], "revision", 1, 10**9)
        if row["persona_id"] in seen:
            fail("controls_personas", "Duplicate persona IDs do not increase coverage.")
        seen.add(row["persona_id"])
    models = spec["models"]
    if not isinstance(models, list) or not 1 <= len(models) <= 32:
        fail("controls_models", "Supply the host's currently available model routes.")
    routes = set()
    for row in models:
        exact_keys(row, {"key", "label", "model", "reasoning_effort"})
        identifier(row["key"])
        text_value(row["label"], "model label", 160)
        text_value(row["model"], "model identity", 160)
        if row["reasoning_effort"] not in {"none", "low", "medium", "high", "xhigh", "max", "ultra"}:
            fail("controls_models", "Unknown reasoning effort.")
        if row["key"] in routes:
            fail("controls_models", "Duplicate model route.")
        routes.add(row["key"])
    limits = spec["limits"]
    bound_fields = {"max_personas": (1, 1000), "max_parallel": (1, 64),
                    "max_turns": (1, 80), "max_model_calls": (1, 50000),
                    "budget_microusd": (0, 10**12), "max_iterations": (1, 10)}
    exact_keys(limits, set(bound_fields) | {"allowed_models"})
    for name, bounds in bound_fields.items():
        integer(limits[name], name, *bounds)
    allowed = strings(limits["allowed_models"], "allowed model routes", maximum=32)
    if not set(allowed) <= routes:
        fail("controls_models", "The model allowlist references unavailable routes.")
    tasks = spec["tasks"]
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 64:
        fail("controls_tasks", "Provide 1..64 PRD-linked task definitions.")
    covered, task_ids = set(), set()
    for task in tasks:
        exact_keys(task, {"id", "requirement_ids", "goal", "actions", "success", "recovery"})
        identifier(task["id"])
        if task["id"] in task_ids:
            fail("controls_tasks", "Duplicate task ID.")
        task_ids.add(task["id"])
        text_value(task["goal"], "task goal")
        ids = strings(task["requirement_ids"], "task requirements", maximum=64)
        if not set(ids) <= requirements:
            fail("controls_prd", "Every task must cite the current target PRD.")
        for field in ("actions", "success", "recovery"):
            strings(task[field], field)
        covered.update(ids)
    exclusions = spec.get("excluded_requirements", [])
    if not isinstance(exclusions, list):
        fail("controls_prd", "Requirement exclusions must be explicit records.")
    excluded = set()
    for row in exclusions:
        exact_keys(row, {"requirement_id", "reason"})
        text_value(row["reason"], "exclusion reason")
        if row["requirement_id"] not in requirements or row["requirement_id"] in excluded | covered:
            fail("controls_prd", "Invalid or duplicate requirement exclusion.")
        excluded.add(row["requirement_id"])
    if covered | excluded != requirements:
        fail("controls_prd", "PRD obligations are missing from both tasks and explicit exclusions.")
    style = spec["style"]
    exact_keys(style, {"platform", "baseline", "preserve", "components"})
    if style["platform"] not in {"web", "native"}:
        fail("controls_style", "Name the target web or native style boundary.")
    result["style"]["baseline"] = _binding(style["baseline"])
    strings(style["preserve"], "UI invariants")
    if not isinstance(style["components"], list) or not 1 <= len(style["components"]) <= 128:
        fail("controls_style", "Declare bounded component style boundaries.")
    paths, components = set(), set()
    from uxloop.io import safe_relative
    for component in style["components"]:
        exact_keys(component, {"id", "path", "properties", "requirement_ids"})
        identifier(component["id"])
        path = safe_relative(component["path"])
        if style["platform"] == "web" and not path.endswith((".module.css", ".module.scss")):
            fail("controls_style", "Web UX style changes require component CSS Modules.")
        if path in paths or component["id"] in components:
            fail("controls_style", "Each component must have its own declared style path.")
        paths.add(path)
        components.add(component["id"])
        strings(component["properties"], "editable style properties")
        ids = strings(component["requirement_ids"], "component requirements", maximum=64)
        if not set(ids) <= requirements:
            fail("controls_prd", "Style changes must map to target PRD requirements.")
    return result


def propose(spec):
    spec = validate(spec)
    maximum = min(len(spec["personas"]), spec["limits"]["max_personas"])
    counts = sorted(set([min(8, maximum), min(16, maximum), maximum]))
    models = [m for m in spec["models"] if m["key"] in spec["limits"]["allowed_models"]]
    return {
        "schema_version": "ux-product-choice.v1",
        "proposal_sha256": digest(spec),
        "spec": spec,
        "questions": [
            {"id": "persona_count", "header": "페르소나", "question": "몇 명의 고유 페르소나로 검증할까요?",
             "options": [{"value": n, "label": f"{n}명", "description": "저장된 고유 프로필을 사용합니다."} for n in counts]},
            {"id": "model_routes", "header": "모델", "question": "검증에 사용할 모델과 매핑을 선택하세요.",
             "options": [{"value": m["key"], "label": m["label"],
                          "description": m["model"] + " / " + m["reasoning_effort"]} for m in models]},
        ],
        "limits": spec["limits"], "excluded_requirements": spec.get("excluded_requirements", []),
        "requires_explicit_response": True, "silence_is_approval": False,
        "cost_approval_granted": False, "model_execution_started": False,
        "ui_rendered": False,
    }


def select(spec, choice):
    proposal = propose(spec)
    spec = proposal["spec"]
    exact_keys(choice, {"proposal_sha256", "confirmed", "persona_ids", "assignments",
                        "parallel", "turns", "max_model_calls", "budget_microusd", "max_iterations"})
    if choice["confirmed"] is not True or choice["proposal_sha256"] != proposal["proposal_sha256"]:
        fail("controls_selection", "An explicit selection for the current proposal is required.")
    ids = strings(choice["persona_ids"], "selected personas", maximum=1000)
    offered = {p["persona_id"] for p in spec["personas"]}
    if not set(ids) <= offered or len(ids) > spec["limits"]["max_personas"]:
        fail("controls_selection", "Select available unique personas within the chosen count limit.")
    mapping = choice["assignments"]
    if not isinstance(mapping, dict) or set(mapping) != set(ids):
        fail("controls_selection", "Map every selected persona exactly once.")
    if any(route not in spec["limits"]["allowed_models"] for route in mapping.values()):
        fail("controls_models", "Selected route is unavailable or prohibited by current instructions.")
    limits = spec["limits"]
    for name, maximum in (("parallel", limits["max_parallel"]), ("turns", limits["max_turns"]),
                          ("max_model_calls", limits["max_model_calls"]),
                          ("max_iterations", limits["max_iterations"])):
        integer(choice[name], name, 1, maximum)
    integer(choice["budget_microusd"], "budget_microusd", 0, limits["budget_microusd"])
    body = {"schema_version": SELECTION, "spec": spec, "choice": copy.deepcopy(choice)}
    return {**body, "selection_sha256": digest(body)}


def revalidate(selection):
    exact_keys(selection, {"schema_version", "spec", "choice", "selection_sha256"})
    if selection["schema_version"] != SELECTION:
        fail("controls_selection", "Unsupported selection record.")
    current = select(selection["spec"], selection["choice"])
    if current != selection:
        fail("controls_selection", "Selection integrity or current PRD/UI binding changed.")
    return current


def request_selection(spec, ask):
    """The existing host renders the proposal; no external UI/runtime is installed."""
    proposal = propose(spec)
    if not callable(ask):
        fail("controls_ui", "The current host must provide its existing choice renderer.")
    answer = ask(proposal)
    if answer is None:
        return {"status": "cancelled", "model_execution_started": False}
    return select(proposal["spec"], answer)


def bind_scale(selection, *, product_id, persona_ids, assignments, providers, limits, library):
    selected = revalidate(selection)
    spec, choice = selected["spec"], selected["choice"]
    if (spec["product_id"] != product_id or list(persona_ids) != choice["persona_ids"]
            or assignments != choice["assignments"]):
        fail("controls_binding", "Execution scope differs from the explicit user selection.")
    for name in ("parallel", "turns", "max_model_calls", "budget_microusd"):
        if getattr(limits, name) != choice[name]:
            fail("controls_binding", "Execution limits differ from the explicit user selection.")
    refs = {r["persona_id"]: r["revision"] for r in spec["personas"]}
    routes = {r["key"]: r for r in spec["models"]}
    for pid in persona_ids:
        profile = library.get(product_id, pid)
        if profile["revision"] != refs[pid]:
            fail("controls_personas", "The selected persona revision is no longer current; review the new version.")
        if (profile["context"]["prd_sha256"] != spec["context"]["prd_sha256"]
                or profile["context"]["prd_path"] != spec["context"]["prd_path"]):
            fail("controls_prd", "Saved persona and selection cite different target PRDs.")
        route = routes[assignments[pid]]
        provider = providers[route["key"]]
        if (provider.spec.model != route["model"]
                or (route["reasoning_effort"] != "none"
                    and getattr(provider, "reasoning_effort", None) != route["reasoning_effort"])):
            fail("controls_models", "Host model identity/reasoning effort is unverified or changed.")
    return selected


def task_controls(selection, requirement_ids):
    return _task_controls(revalidate(selection)["spec"], requirement_ids)


def _task_controls(spec, requirement_ids):
    """Internal projection after one full validation, not N full proposal reads."""
    rows = [t for t in spec["tasks"] if set(t["requirement_ids"]) & set(requirement_ids)]
    if {rid for t in rows for rid in t["requirement_ids"]} & set(requirement_ids) != set(requirement_ids):
        fail("controls_prd", "Selected persona obligations are not covered by selected tasks.")
    return rows


def validate_runtime_selection(selection, providers):
    """Recheck mutable inputs before dispatch; the queue already freezes the plan."""
    spec, choice = selection["spec"], selection["choice"]
    prd_context(spec["context"])
    _binding(spec["style"]["baseline"])
    routes = {row["key"]: row for row in spec["models"]}
    for key in set(choice["assignments"].values()):
        route, provider = routes[key], providers.get(key)
        if (provider is None or provider.spec.model != route["model"]
                or (route["reasoning_effort"] != "none"
                    and getattr(provider, "reasoning_effort", None) != route["reasoning_effort"])):
            fail("controls_models", "The selected model/reasoning route changed before dispatch.")


def validate_plan_selection(plan, providers):
    selection = revalidate(plan["product_selection"])
    spec, choice = selection["spec"], selection["choice"]
    jobs = plan["jobs"]
    if (plan["product_id"] != spec["product_id"]
            or [row["task"]["persona_id"] for row in jobs] != choice["persona_ids"]
            or {row["task"]["persona_id"]: row["provider"] for row in jobs} != choice["assignments"]):
        fail("controls_binding", "The immutable queue does not match the selected personas and assignments.")
    for name in ("parallel", "turns", "budget_microusd"):
        if plan["limits"][name] != choice[name]:
            fail("controls_binding", "Queue limits differ from the explicit selection.")
    expected_calls = min(choice["max_model_calls"], len(jobs) * (choice["turns"] + 1))
    if plan["limits"]["max_model_calls"] != expected_calls:
        fail("controls_binding", "Queue model-call limit differs from the selected bounded limit.")
    refs = {row["persona_id"]: row["revision"] for row in spec["personas"]}
    for row in jobs:
        binding = row["binding"]
        if (binding["revision"] != refs[row["task"]["persona_id"]]
                or binding["prd_sha256"] != spec["context"]["prd_sha256"]):
            fail("controls_binding", "Queue persona or PRD binding differs from the selection.")
    validate_runtime_selection(selection, providers)


def check_style_scope(selection, changed_paths, properties):
    """Check an explicit diff manifest; the existing Figma/replay gates still apply."""
    spec = revalidate(selection)["spec"]
    components = {c["path"]: c for c in spec["style"]["components"]}
    if not isinstance(changed_paths, list) or not changed_paths or len(set(changed_paths)) != len(changed_paths):
        fail("controls_style", "Provide distinct changed style paths.")
    if not isinstance(properties, dict) or set(properties) != set(changed_paths):
        fail("controls_style", "The reviewed property diff must cover every changed style path.")
    for path in changed_paths:
        if path not in components:
            fail("controls_style", "A style change escapes the selected component boundary.")
        values = strings(properties[path], "changed style properties")
        if not set(values) <= set(components[path]["properties"]):
            fail("controls_style", "A style change alters a preserved property.")
    return {"scope_valid": True, "computed_css_verified": False, "figma_and_replay_required": True}


def seed_catalog():
    value = read_json(Path(__file__).parent / "data/korea-seeds.v1.json")
    if value.get("schema_version") != "ux-korea-seeds.v1" or value.get("license") != "CC-BY-4.0":
        fail("controls_seed", "Unsupported or unattributed Korean seed pack.")
    records = value["records"]
    if len({r["id"] for r in records}) != len(records) or any(type(r["attributes"]["age"]) is not int
            or r["attributes"]["age"] < 19 for r in records):
        fail("controls_seed", "Seed records must be distinct synthetic adult rows.")
    return value


def seed_input(doc):
    """Compose authored PRD hypotheses; research enrichment keeps its existing gated import."""
    exact_keys(doc, {"product_id", "context", "personas"})
    context = prd_context(doc["context"])
    identifier(doc["product_id"])
    catalog = seed_catalog()
    seeds = {r["id"]: r for r in catalog["records"]}
    if not isinstance(doc["personas"], list) or not 1 <= len(doc["personas"]) <= 32:
        fail("controls_seed", "Compose 1..32 seed-derived profiles per import.")
    rows, seen = [], set()
    for item in doc["personas"]:
        from .library import PROFILE_FIELDS
        exact_keys(item, PROFILE_FIELDS | {"persona_id", "seed_id"})
        identifier(item["seed_id"])
        for field in ("contexts", "assumptions", "unknowns"):
            strings(item[field], field)
        seed = seeds.get(item["seed_id"])
        if seed is None or item["seed_id"] in seen:
            fail("controls_seed", "Select distinct actual catalog seeds, not duplicated identities.")
        seen.add(item["seed_id"])
        row = {k: copy.deepcopy(v) for k, v in item.items() if k != "seed_id"}
        row["claim_ids"] = []
        attrs = seed["attributes"]
        source = (f"NVIDIA synthetic seed row {seed['row_index']}; "
                  f"age {attrs['age']}; province {attrs['province']}; occupation {attrs['occupation']}.")
        row["contexts"] = list(row["contexts"]) + [source]
        row["assumptions"] = list(row["assumptions"]) + [
            "Product behavior and physical conditions are authored hypotheses, not measured from demographic attributes."]
        row["unknowns"] = list(row["unknowns"]) + [
            "Actual user preference, grip, reach, vision and motor capability are unobserved."]
        rows.append(row)
    result = {"schema_version": "ux-persona-library-input.v1", "product_id": doc["product_id"],
              "mode": "prd_hypothesis", "context": context, "personas": rows}
    # The existing importer owns full profile validation, versioning and persistence.
    from .library import Library
    Library(Path("."))._prepare_profiles(result)
    return {"input": result, "dataset": catalog["dataset"], "seed_pack_sha256": digest(catalog),
            "dataset_revision": catalog["retrieval"]["revision"],
            "license": catalog["license"], "population_representativeness": False}
