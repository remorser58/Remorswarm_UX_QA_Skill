"""Host-resolved entry from a goal and saved personas to a reviewable swarm.

The user supplies product and goal. Provider routing, current source checks,
owned tools and Python bindings are host work. This entry never approves cost.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import copy

from uxresearch.canonical import byte_digest, canonical, digest
from uxresearch.storage import atomic, read_bytes, read_json, safe_path
from .agent_run import Tool, _host_info
from . import swarm
from .swarm_queue import Queue, SCHEMA, bounded, fail, quote


@dataclass(frozen=True)
class ScaleLimits:
    parallel: int = 4
    turns: int = 12
    call_seconds: int = 30
    task_seconds: int = 600
    lease_seconds: int = 60
    budget_microusd: int = 0
    max_model_calls: int = 10000

    def validate(self):
        for name, low, high in (("parallel", 1, 64), ("turns", 1, 80),
                ("call_seconds", 1, 180), ("task_seconds", 1, 3600),
                ("lease_seconds", 10, 600), ("budget_microusd", 0, 10**12),
                ("max_model_calls", 1, 50000)):
            bounded(getattr(self, name), low, high, name)
        return vars(self).copy()


def engine_manifest():
    root = Path(__file__).resolve().parent
    files = ("swarm_queue.py", "swarm_providers.py", "model_router.py", "scale_run.py", "scale_entry.py", "scale_report.py",
             "agent_run.py", "swarm.py", "library.py", "product_controls.py")
    return {name: byte_digest(read_bytes(root / name)) for name in files}


def criterion_checklist(requirement_ids, *, criteria_catalog=None, fixture_requirements=None):
    """Return an ordered execution checklist from optional host-supplied metadata."""
    catalog = criteria_catalog if isinstance(criteria_catalog, dict) else {}
    fixtures = fixture_requirements if isinstance(fixture_requirements, dict) else {}
    rows = []
    for index, rid in enumerate(requirement_ids):
        spec = catalog.get(rid) or {}
        action = spec.get("action") or "Observe the relevant surface and verify the requirement directly on the target product."
        steps = list(spec["steps"]) if isinstance(spec.get("steps"), (list, tuple)) and spec["steps"] else [action]
        rows.append(dict(
            kind="success",
            index=index,
            requirement_id=rid,
            precondition=spec.get("precondition") or "Fresh isolated owned context",
            scope=spec.get("scope") or "desktop",
            required_fixtures=list(fixtures.get(rid) or spec.get("required_fixtures") or ()),
            steps=steps,
        ))
    return rows


def required_fixture_keys(requirement_ids, *, fixture_requirements=None):
    fixtures = fixture_requirements if isinstance(fixture_requirements, dict) else {}
    return sorted({name for rid in requirement_ids
                   for name in fixtures.get(rid, ())})


def per_task_turn_limit(task, approved_turns):
    """Honor an optional bounded per-task turn limit within the approved ceiling."""
    requested = task.get("turn_limit") if isinstance(task, dict) else None
    if isinstance(requested, int) and not isinstance(requested, bool) and 1 <= requested <= approved_turns:
        return min(approved_turns, requested)
    return approved_turns


def _criterion_actions(requirement_ids, *, criteria_catalog=None, fixture_requirements=None):
    return [f"[{row['requirement_id']}] Required fixtures: "
            + (", ".join(name.replace("@group:", "manifest group ") for name in row["required_fixtures"]) or "none")
            + ". Steps: " + " -> ".join(row["steps"])
            for row in criterion_checklist(requirement_ids, criteria_catalog=criteria_catalog, fixture_requirements=fixture_requirements)]


def _persona_journey_goal(base_goal, requirement_ids, *, criteria_catalog=None, fixture_requirements=None):
    """Turn each saved persona's mapped PRD requirements into generic executable actions.

    Do not declare unrelated, untriggered recovery paths as success requirements.
    Missing evidence for an applicable success requirement remains not_run.
    """
    catalog = criteria_catalog if isinstance(criteria_catalog, dict) else {}
    criteria = []
    for rid in requirement_ids:
        spec = catalog.get(rid)
        if isinstance(spec, dict):
            text = ", ".join(spec.get("text") or ())
            criteria.append(
                f"- [{rid}] screen={spec.get('screen', 'current')}; selector={spec.get('selector', 'observed')}; "
                f"text={text}; value={spec.get('value', '')}; precondition={spec.get('precondition', '')}; "
                f"action={spec.get('action', '')}; timeout_seconds={spec.get('timeout_seconds', 30)}; scope={spec.get('scope', 'desktop')}"
            )
    sections = [
        base_goal,
        "기준별 필수 단계 체크리스트:\n" + ("\n".join(_criterion_actions(requirement_ids, criteria_catalog=catalog, fixture_requirements=fixture_requirements)) or "- None"),
    ]
    if criteria:
        sections.append("명시적 성공 기준과 기계 판정 계약:\n" + "\n".join(criteria))
    sections.append(
        "실행 규칙: 새 브라우저의 현재 DOM을 먼저 관찰하고 기준마다 선행조건을 충족한 뒤 제한시간 안에 지정 행동을 실제 수행한다. "
        "기준에 적힌 텍스트만 보였다는 이유로 통과시키지 말고 숫자·상태·목록까지 확인한다. "
        "기계 판정 checks가 존재하면 그 결과를 반드시 따른다. 기계 판정이 없는 기준은 관측 ID와 스크린샷을 인용한다. "
        "필수 fixture나 하위 흐름을 건너뛰고 최종 판단하지 않는다. 성공 기준을 실행하지 않았거나 전제조건이 확인되지 않으면 not_run으로 남기고 다음 실행 행동을 먼저 시도한다. "
        "조건부 복구 기준은 실제 실패가 발생했을 때만 실행하며 실패가 전혀 발생하지 않았으면 not_applicable로 남긴다. 실행하지 않은 조건을 failed로 판정하지 않는다. "
        "현재 관측에서 visible:true인 control만 클릭한다. "
        "같은 영역·방향으로 scroll한 결과 위치와 가시 control이 2회 연속 그대로면 더 반복하지 않고 해당 기준을 not_run으로 남긴다. "
        "행동 도구가 이미 최신 DOM을 반환했으면 같은 화면의 observe를 반복하지 않는다. 파일 이름/selector는 현재 fixture_catalog와 controls에서만 고른다."
    )
    return "\n\n".join(sections)


def scale_job_id(product_id, persona_id, revision, goal, build):
    """Use the same reviewed identity for preparation and no-replay preflight."""
    return "S-" + digest([product_id, persona_id, revision, goal, build])[:24].translate(
        str.maketrans("0123456789abcdef", "abcdefghijklmnop"))


def prepare_scale_goal(library, run_path, providers, tool_host, tools, *, product_id,
                       target, goal, build, limits=ScaleLimits(), persona_ids=None,
                       assignments=None, credential_scopes=None, reviewed=False,
                       tool_provenance="authored_fixture", billing_reviews=None,
                       provider_destinations=None, selection=None,
                       criteria_catalog=None, fixture_requirements=None):
    if reviewed is not True:
        fail("review_required", "The host must review task fit, current persona sources, data destinations and owned tools.")
    swarm.ident(product_id)
    swarm.text(target)
    swarm.text(goal)
    if swarm.clean(goal) != goal:
        fail("goal_privacy", "Supply a goal without personal identifiers.")
    if tool_provenance not in {"authored_fixture", "owned_browser", "reviewed_host_tools"}:
        fail("tool_provenance", "Name the actual tool evidence origin.")
    limits_dict = limits.validate()
    build = swarm._build(build)
    host_info = _host_info(tool_host)
    if not host_info["parallel_safe"] and limits.parallel != 1:
        fail("tool_parallel", "This tool host requires a serial plan.")
    if not providers or not isinstance(providers, dict):
        fail("provider_required", "A reviewed provider route is required; no default paid provider is chosen.")
    modes = {provider.mode for provider in providers.values()}
    if len(modes) != 1 or not modes <= {"fixture", "live"}:
        fail("mixed_provenance", "Fixture and actual-provider execution require separate runs.")
    mode = next(iter(modes))
    if mode == "live" and selection is None:
        fail("controls_selection", "New live plans require explicit current persona/model selection before preparation.")
    if host_info["mode"] != ("fixture" if mode == "fixture" else "model_tools"):
        fail("mixed_provenance", "The tool host must disclose the same execution mode as the plan.")
    specs = {}
    credential_scopes = credential_scopes or {}
    billing_reviews = billing_reviews or {}
    provider_destinations = provider_destinations or {}
    for key, provider in sorted(providers.items()):
        swarm.ident(key)
        spec = provider.spec.validate()
        if spec["key"] != key:
            fail("provider_binding", "Provider routing key differs from its reviewed specification.")
        scope = credential_scopes.get(key, "offline-no-credential" if mode == "fixture" else None)
        if not scope or not isinstance(scope, str) or len(scope) > 160:
            fail("credential_scope", "Resolve a non-secret account scope before presenting paid-call approval.")
        destination = spec["endpoint"] or provider_destinations.get(key, "offline authored callback" if mode == "fixture" else None)
        review = copy.deepcopy(billing_reviews.get(key, {}))
        if mode == "live":
            fields = ("input_token_cap", "output_token_cap", "input_price_per_million", "output_price_per_million")
            if (not isinstance(destination, str) or not destination.strip()
                    or not isinstance(review, dict) or any(review.get(name) != spec[name] for name in fields)
                    or review.get("no_unpriced_features") is not True
                    or not isinstance(review.get("source"), str) or not review["source"].strip()
                    or not isinstance(review.get("checked_at"), str) or not review["checked_at"].strip()):
                fail("billing_review_required", "Resolve documented model context limits, current prices, unpriced features and provider destination before live preparation.")
            if spec["input_price_per_million"] == 0 or spec["output_price_per_million"] == 0:
                if not (spec["protocol"] == "callback"
                        and spec["input_price_per_million"] == 0
                        and spec["output_price_per_million"] == 0
                        and review.get("free_tier") is True
                        and review.get("billing_source") == "free"
                        and isinstance(review.get("requested_model"), str)
                        and bool(review["requested_model"].strip())):
                    fail("billing_review_required", "Zero-priced live routes require explicit free-tier billing review metadata (free_tier=true, billing_source='free', requested_model).")
        specs[key] = dict(spec=spec, mode=mode, adapter_sha256=provider.adapter_sha256, credential_scope=scope,
                         destination=destination, billing_review=review)
    tools = [tool.spec() for tool in tools]
    if not 1 <= len(tools) <= 16 or len({t["name"] for t in tools}) != len(tools):
        fail("tool_scope", "Select one to sixteen uniquely named owned tools.")
    candidates = library.list(product_id)["personas"]
    eligible = {p["persona_id"]: p for p in candidates if p["reusable"]}
    selected = sorted(eligible) if persona_ids is None else list(persona_ids)
    if (not 1 <= len(selected) <= 1000 or len(selected) != len(set(selected))
            or any(pid not in eligible for pid in selected)):
        fail("personas_required", "Select current saved personas. Missing or stale personas are not cloned to inflate session count.")
    assignments = assignments or {pid: list(specs)[i % len(specs)] for i, pid in enumerate(selected)}
    if set(assignments) != set(selected) or any(key not in specs for key in assignments.values()):
        fail("provider_binding", "Every selected persona needs exactly one reviewed provider assignment.")
    if selection is not None:
        from .product_controls import bind_scale
        selection = bind_scale(selection, product_id=product_id, persona_ids=selected,
                               assignments=assignments, providers=providers, limits=limits, library=library)
    # Identical profiles retain independent execution but do not become diverse
    # research evidence merely through new IDs or labels.
    behavioral_hashes, jobs = [], []
    for pid in selected:
        profile = library.get(product_id, pid, eligible[pid]["revision"])
        requirements = [r for r in profile["context"]["requirements"] if r["id"] in profile["profile"]["requirement_ids"]]
        if not 1 <= len(requirements) <= 16:
            fail("requirement_scope", "Review one to sixteen applicable requirements per persona.")
        # Typed internal identifiers contain no digit runs that could resemble
        # phone/account identifiers in the existing whole-task privacy gate.
        jid = scale_job_id(product_id, pid, profile["revision"], goal, build)
        requirement_ids = [r["id"] for r in requirements]
        catalog = criteria_catalog if isinstance(criteria_catalog, dict) else {}
        task = dict(id=jid, persona_id=pid, requirement_ids=requirement_ids,
            goal=_persona_journey_goal(goal, requirement_ids, criteria_catalog=catalog, fixture_requirements=fixture_requirements),
            starting_state="Fresh isolated owned context for the reviewed product.",
            actions=["Choose a permitted next action from your own current observations."]
                    + _criterion_actions(requirement_ids, criteria_catalog=catalog, fixture_requirements=fixture_requirements),
            decisions=copy.deepcopy(profile["profile"]["behaviors"]),
            success_criteria=[r["excerpt"] + (" [" + r["id"] + "] " + catalog[r["id"]]["value"]
                if r["id"] in catalog and catalog[r["id"]].get("value") else "") for r in requirements],
            recovery_criteria=["If a recoverable browser/import failure actually occurs, perform the safe recovery and verify it. If no triggering failure occurs, report not_applicable; do not manufacture a failure."],
            data_namespace=jid, resource_id=jid,
            side_effects="owned_fixture_write" if any(t["effect"] == "owned_fixture_write" for t in tools) else "read_only",
            stop_conditions=["Stop at real accounts, payment, unapproved resources, uncertain effects or exhausted limits."],
            requirement_coverage=[dict(requirement_id=r["id"], obligations=[dict(id=f"O-PRD-{i+1}", description=r["excerpt"],
                criterion_refs=[dict(kind="success", index=i)], exclusion_reason=None)]) for i, r in enumerate(requirements)])
        if selection is not None:
            from .product_controls import _task_controls
            controls = _task_controls(selection["spec"], requirement_ids)
            task["goal"] += "\n\nReviewed project task goals:\n" + "\n".join(row["goal"] for row in controls)
            task["actions"] = list(dict.fromkeys([action for row in controls for action in row["actions"]]
                                                + _criterion_actions(requirement_ids, criteria_catalog=catalog, fixture_requirements=fixture_requirements)))
            task["recovery_criteria"] = [criterion for row in controls for criterion in row["recovery"]]
            # Native checks bind only the original requirement-index slots.
            # A selected task may add obligations those checks never evaluate;
            # keep them separate so a native pass cannot certify the whole task.
            for control_index, row in enumerate(controls):
                for success_index, criterion in enumerate(row["success"]):
                    index = len(task["success_criteria"])
                    task["success_criteria"].append(f"[{row['id']}] {criterion}")
                    for requirement_index, coverage in enumerate(task["requirement_coverage"]):
                        if coverage["requirement_id"] in row["requirement_ids"]:
                            coverage["obligations"].append(dict(
                                id=f"O-CONTROL-{control_index+1}-{success_index+1}-{requirement_index+1}",
                                description=criterion,
                                criterion_refs=[dict(kind="success", index=index)], exclusion_reason=None))
        # Reuse the existing plan/PRD/research gates in bounded single-task chunks;
        # the new queue, not a raised old eight-worker constant, schedules them.
        prepared = swarm._prepare_plan(library, dict(schema_version=swarm.SCHEMA, product_id=product_id,
            build=build, max_parallel=1, lease_seconds=30, max_attempts=1, tasks=[task]))
        entry = prepared["tasks"][0]
        jobs.append(dict(id=jid, provider=assignments[pid], task=entry["task"], binding=entry["binding"]))
        behavioral_hashes.append(digest({k: v for k, v in profile["profile"].items() if k != "label"}))
    limits_dict["max_model_calls"] = min(limits.max_model_calls, len(jobs) * (limits.turns + 1))
    plan = dict(schema_version=SCHEMA, mode=mode, library_path=str(library.root), product_id=product_id,
        target=target, goal=goal, build=build, limits=limits_dict, providers=specs, tools=tools,
        tool_host=host_info, tool_provenance=tool_provenance, jobs=jobs, engine_manifest=engine_manifest(),
        diversity=dict(distinct_saved_personas=len(jobs), distinct_behavioral_profiles=len(set(behavioral_hashes)),
                       population_representativeness=False),
        evidence_policy="current_sources_own_observations_png_and_native_checks_no_peer_answers")
    if selection is not None:
        plan["product_selection"] = copy.deepcopy(selection)
    run = safe_path(run_path)
    # Reservation is held by the caller's Library single-writer context. A new
    # folder cannot silently reset the same goal's unknown effects or budget.
    reservation = library.root / "scale-goals.json"
    saved = {}
    if reservation.exists():
        envelope = read_json(reservation, private=True)
        if envelope.get("schema_version") != SCHEMA or digest(envelope.get("payload")) != envelope.get("sha256"):
            fail("goal_integrity", "The goal reservation changed; preserve it for inspection.")
        saved = envelope["payload"]
    key = digest(dict(product_id=product_id, target=target, goal=goal, build=build, mode=mode,
                      personas=[j["binding"] for j in jobs]))
    if key in saved:
        record = saved[key]
        if record != dict(run=str(run), plan_sha256=digest(plan)):
            fail("goal_reserved", "This goal and persona set already has a run. Review it instead of resetting budget or uncertain sends.")
        if not (run / "queue.sqlite").exists():
            fail("partial_goal", "The reserved run was interrupted during creation; preserve and inspect its files.")
        queue = Queue(run)
        if queue.plan_sha256 != digest(plan):
            fail("plan_integrity", "The reserved run no longer matches the reviewed plan.")
        return queue
    if run.exists():
        fail("run_exists", "The destination already exists and will not be replaced.")
    saved[key] = dict(run=str(run), plan_sha256=digest(plan))
    atomic(reservation, canonical(dict(schema_version=SCHEMA, payload=saved, sha256=digest(saved))))
    return Queue.create(run, plan)


def preview(queue):
    plan = queue.plan
    rows = []
    maximum = 0
    for key, provider in plan["providers"].items():
        sessions = sum(job["provider"] == key for job in plan["jobs"])
        calls = sessions * (plan["limits"]["turns"] + 1)
        cost = calls * quote(provider["spec"])
        maximum += cost
        rows.append(dict(provider=key, model=provider["spec"]["model"], destination=provider.get("destination", provider["spec"]["endpoint"]),
            credential_scope=provider["credential_scope"], sessions=sessions,
            concurrency=provider["spec"]["concurrency"], request_ceiling=calls, conservative_microusd=cost))
    return dict(plan_sha256=queue.plan_sha256, mode=plan["mode"], sessions=len(plan["jobs"]),
        parallel_calls=plan["limits"]["parallel"], provider_routes=rows,
        approved_budget_microusd=plan["limits"]["budget_microusd"],
        full_run_conservative_microusd=maximum,
        may_stop_before_all_sessions=maximum > plan["limits"]["budget_microusd"],
        data_sent="Each persona's scrubbed profile, cited requirements, allowed tool schema and own observations only.",
        diversity=plan["diversity"], tool_provenance=plan["tool_provenance"],
        product_selection_sha256=plan.get("product_selection", {}).get("selection_sha256"),
        selection_ui_verified=False,
        cost_approval_required=plan["mode"] == "live",
        no_automatic_retry_after_uncertain_send=True,
        next_action="실제 실행은 이 계획과 최대 비용을 확인한 사용자 승인 후 시작합니다." if plan["mode"] == "live"
                    else "유료 호출 없는 모의 실행입니다. 실제 모델 성능·사용자 효과를 입증하지 않습니다.")


def render_status(report):
    counts, budget = report["counts"], report["budget"]
    title = "모의 페르소나 실행" if report["mode"] == "fixture" else "실제 모델 페르소나 실행"
    lines = [f"# {title}", "",
        f"전체 {report['total_sessions']} · 완료 {counts['complete']} · 실행 {counts['running']} · 대기 {counts['queued']}",
        f"확인 필요 {counts['uncertain']} · 중단 {counts['blocked']} · 취소 {counts['cancelled']}",
        f"비용: 기록/보수적 정산 USD {budget['charged_or_settled']/1000000:.6f} · 예약 USD {budget['reserved']/1000000:.6f} · 한도 USD {budget['ceiling']/1000000:.6f}",
        f"실제 모델 완료 호출 {report['actual_model_calls']} · 작성된 모의 응답 {report['authored_model_calls']}",
        "", report["next_action"], "", "실행 완료는 제품 UX 통과나 실제 사용자 효과를 의미하지 않습니다.", ""]
    validation = report.get("evidence_validation")
    if validation:
        outcomes = validation["ux_outcomes"]
        lines += [f"현재 근거: 유효 {validation['current_valid_sessions']} · 확인 필요 {validation['blocked_sessions']} · 미관측 {validation['unassessed_sessions']}",
                  f"현재 과업 관측: 통과 {outcomes['passed']} · 실패 {outcomes['failed']} · 판정 보류 {outcomes['inconclusive']}", ""]
    status_names = {"queued": "대기", "running": "실행 중", "complete": "실행 완료", "blocked": "중단", "uncertain": "결과 확인 필요", "cancelled": "취소"}
    outcomes_ko = {"passed": "관측 기준 통과", "failed": "실패 관측", "inconclusive": "판정 보류", "blocked": "검증 중단", "skipped": "미실행"}
    for task in report["tasks"]:
        result = task.get("result") or {}
        verdict = ("원본 자료 또는 관측 근거를 다시 확인해야 합니다" if task.get("current_valid") is False
                   else outcomes_ko.get(result.get("ux_outcome"), "실행 상태 확인 필요" if task.get("problem") else "판정 대기"))
        lines.append(f"- {task['persona_id']}: {status_names[task['status']]} · {verdict}")
    return "\n".join(lines) + "\n"


def render_preview(value):
    lines = ["# 페르소나 실행 계획", "", f"독립 세션 {value['sessions']}개 · 동시 요청 최대 {value['parallel_calls']}개",
        "실행 방식: " + ("유료 호출 없는 모의 실행" if value["mode"] == "fixture" else "승인이 필요한 실제 모델 실행"),
        f"실행 예산 한도: USD {value['approved_budget_microusd']/1000000:.6f}",
        f"모든 허용 턴을 끝낼 때의 보수적 계산: USD {value['full_run_conservative_microusd']/1000000:.6f}", ""]
    for route in value["provider_routes"]:
        lines.append(f"- {route['provider']} / {route['model']}: {route['sessions']}세션 · 동시 {route['concurrency']} · 전송 대상 {route['destination']}")
    if value["may_stop_before_all_sessions"]:
        lines += ["", "모든 세션이 끝나기 전에 예산 한도에서 멈출 수 있습니다."]
    lines += ["", "전송 내용: 각 페르소나의 비식별 프로필, 관련 요구사항, 허용된 도구 정보와 자신의 관측.",
              value["next_action"]]
    return "\n".join(lines) + "\n"
