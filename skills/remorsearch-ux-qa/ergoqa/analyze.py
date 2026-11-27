"""Evaluate a recorded run (ergo-run.v1 directory) under one or more profiles.

A run is recorded once on a real surface by a driver. Ergonomic models are then
evaluated for the run's own profile and, with ``cross_profile=True``, for every
other profile that uses the same device and orientation: the screen geometry is
identical, only the human model differs. Actions chosen by an LLM persona are
not re-simulated for other profiles; judgment notes stay with their own run.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

from . import checks, png
from .devices import device_for_snapshot, get_device, rotate
from .hf import gaze
from .profiles import profile_index
from .profile_binding import match_status
from .snapshot import load_run_dir, resolve_within

SEVERITY_RANK = checks.SEVERITY_ORDER


def _route(url: Any) -> Any:
    """URL with digit runs in path, query and fragment masked; host and port stay exact."""
    if not isinstance(url, str):
        return url
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, *(re.sub(r"\d+", "{n}", p) for p in (parts.path, parts.query, parts.fragment))))


def screen_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Screen a warning belongs to: surface, route, device and visible headings.

    Control lists, toasts, form errors and record IDs in the route change on every
    state of the same screen, so they never split it. Headings, title and modal
    layers (the background turns inert) still separate distinct screens.
    """
    surface = snapshot.get("surface", {})
    headings = [(e.get("selector"), e.get("text")) for e in snapshot.get("elements", [])
                if e.get("visible") and not e.get("inert_by_modal") and e.get("role") == "heading"]
    route = _route(surface.get("url"))
    signature = [{**{key: surface.get(key) for key in ("kind", "title", "app_id", "build_id")}, "route": route},
                 snapshot.get("device"), headings]
    return {"key": "screen-" + hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:16],
            "route": route, "heading": next((text for _, text in headings if text), "") or surface.get("title") or ""}


_CONSPICUITY_CACHE: dict[tuple[str, str, int], list[list[float]]] = {}


def _conspicuity_grid(image: png.Image, factor: int) -> list[list[float]]:
    small = png.downsample(png.to_rgb(image), factor)
    data = small.data
    rows = []
    for y in range(small.height):
        base = y * small.width * 3
        rows.append([(data[base + 3 * x], data[base + 3 * x + 1], data[base + 3 * x + 2]) for x in range(small.width)])
    return gaze.conspicuity_map(rows)


def conspicuity_for_snapshot(
    snapshot: dict[str, Any], cell_css_px: int = 8, *, on_css_fallback: Callable[[], None] | None = None,
) -> list[list[float]] | None:
    """Prefer a decodable CSS-scale copy, then use the original at device scale."""
    shot = snapshot.get("screenshot", {})
    path = shot.get("resolved_path")
    if not path or not Path(path).is_file():
        return None
    css = shot.get("css")
    if css is not None:
        try:
            css_path = resolve_within(Path(path).parent, css["path"])
            with css_path.open("rb") as stream:
                raw = stream.read(png.MAX_FILE_BYTES + 1)
            if len(raw) > png.MAX_FILE_BYTES:
                raise png.PNGError("CSS screenshot exceeds the PNG size limit")
            digest = hashlib.sha256(raw).hexdigest()
            if css.get("sha256") and digest != css["sha256"]:
                raise png.PNGError("CSS screenshot does not match its recorded SHA-256")
            factor = max(1, int(round(cell_css_px)))
            key = ("css", digest, factor)
            if key not in _CONSPICUITY_CACHE:
                _CONSPICUITY_CACHE[key] = _conspicuity_grid(png.decode(raw), factor)
            return _CONSPICUITY_CACHE[key]
        except (KeyError, TypeError, ValueError, OSError):
            if on_css_fallback is not None:
                on_css_fallback()
    dpr = float(snapshot.get("device", {}).get("dpr") or 1.0)
    factor = max(1, int(round(cell_css_px * dpr)))
    key = ("original", str(shot.get("sha256") or path), factor)
    if key not in _CONSPICUITY_CACHE:
        try:
            _CONSPICUITY_CACHE[key] = _conspicuity_grid(png.read_png(path), factor)
        except (png.PNGError, OSError):
            return None
    return _CONSPICUITY_CACHE[key]


def _device_for(snapshot: dict[str, Any], profile: dict[str, Any]):
    device_block = snapshot.get("device", {})
    try:
        return device_for_snapshot(device_block)
    except Exception:  # noqa: BLE001 - fall back to the profile's device id
        device = get_device(profile["attributes"]["device_id"])
        if device_block.get("orientation") == "landscape":
            device = rotate(device, "landscape")
        return device


CLICK_ACTIONS = frozenset({"tap", "click", "double_tap", "long_press"})


def _path_selectors(run: dict[str, Any], snapshots_by_id: dict[str, dict[str, Any]], actions: frozenset[str] | None = None) -> set[str]:
    selectors: set[str] = set()
    for step in run.get("steps", []):
        if actions is not None and (step.get("action") or {}).get("action") not in actions:
            continue
        target_id = step.get("target_element_id")
        before = snapshots_by_id.get(step.get("before") or "")
        if before and target_id:
            element = next((e for e in before.get("elements", []) if e.get("id") == target_id), None)
            if element and element.get("selector"):
                selectors.add(element["selector"])
        target = (step.get("action") or {}).get("target")
        if isinstance(target, str):
            selectors.add(target)
    return selectors


def _dedupe(observations: list[checks.Observation]) -> list[checks.Observation]:
    """Keep the worst observation per check, element, profile, run and screen."""
    best: dict[tuple, checks.Observation] = {}
    order: list[tuple] = []
    for obs in observations:
        # A capture gap and a valid verdict are independent evidence. Preserve
        # the gap even when another snapshot of the same element was evaluable.
        key = (obs.check_id, obs.element_key, obs.profile_id, obs.run_id, obs.extra.get("verdict") == "inconclusive",
               (obs.extra.get("warning_group") or {}).get("screen_key"))
        current = best.get(key)
        if current is None:
            best[key] = obs
            order.append(key)
            continue
        if current.passed and not obs.passed:
            best[key] = obs
        elif not current.passed and not obs.passed and SEVERITY_RANK.get(obs.severity or "P3", 3) < SEVERITY_RANK.get(current.severity or "P3", 3):
            best[key] = obs
    return [best[k] for k in order]


def run_health(run: dict[str, Any], snapshots: list[dict[str, Any]], scenario: dict[str, Any] | None) -> tuple[str, list[str]]:
    """``ok``, ``degraded`` or ``failed`` plus human-readable reasons.

    A run that failed a step, lost off-origin resources, hit the element cap, or never
    saw a declared timing window cannot support a clean result; the report and the CI
    gate must say so (cross-review 2026-09-28).
    """
    rid = run.get("run_id")
    notes: list[str] = []
    health = "ok"
    if run.get("status") not in (None, "completed"):
        health = "failed"
        bad = [s for s in run.get("steps", []) if s.get("result") not in (None, "ok")]
        where = f" (step {bad[0].get('step_index')}: {bad[0].get('result')})" if bad else ""
        notes.append(f"{rid}: 실행 상태 {run.get('status')}, 성공 {run.get('success')}{where} — 이후 화면은 검사되지 않았습니다.")
    elif run.get("success") is False:
        notes.append(f"{rid}: 실행은 완료됐지만 과업 성공 조건을 충족하지 못했습니다. 기록된 화면의 검사 범위는 유지됩니다.")
    task_results = [c for c in (run.get("success_detail") or {}).get("criteria", []) if c.get("kind") == "task_check"]
    missing = [c["id"] for c in task_results if c.get("result") == "unevaluable"]
    if missing:
        health = "degraded" if health == "ok" else health
        notes.append(f"{rid}: 과업 값 검사 미확인: {', '.join(missing)}. 대상 또는 도달한 단계를 확인하세요.")
    driver = run.get("driver") or {}
    blocked = ((driver.get("network_policy") or {}).get("blocked_requests") or 0) if isinstance(driver, dict) else 0
    if blocked:
        health = "degraded" if health == "ok" else health
        notes.append(f"{rid}: 다른 출처 요청 {blocked}건을 차단했습니다(스타일/스크립트가 빠졌을 수 있음; 필요하면 --allow-origin).")
    capped = [n for snap in snapshots for n in (snap.get("notes") or []) if "capped" in str(n)]
    if capped:
        health = "degraded" if health == "ok" else health
        notes.append(f"{rid}: 요소 수 상한으로 일부 요소를 검사하지 못했습니다({capped[0]}).")
    for rec in run.get("adaptation", []):
        if rec.get("gaps"):
            health = "degraded" if health == "ok" else health
            notes.append(f"{rid}: {rec['kind']} 복제 검사 범위 미확인: {', '.join(rec['gaps'])}.")
    if run.get("reflow_screens_dropped"):
        health = "degraded" if health == "ok" else health
        notes.append(f"{rid}: 화면 수 상한으로 {run['reflow_screens_dropped']}개 화면의 복제 검사를 생략했습니다.")
    unassessed_visibility = [
        element for snapshot in snapshots for element in snapshot.get("elements", [])
        if element.get("visible") is None
    ]
    if unassessed_visibility:
        health = "degraded" if health == "ok" else health
        notes.append(f"{rid}: 요소 {len(unassessed_visibility)}개의 화면 표시 여부를 측정하지 않아 전체 결과를 정상 완료로 볼 수 없습니다.")
    declared = {w.get("id") for w in (scenario or {}).get("timing_windows", [])}
    for w in run.get("timing_windows", []):
        if w.get("id") in declared and not w.get("appearances") and not w.get("error"):
            notes.append(f"{rid}: 선언된 시간 창 '{w.get('id')}'이(가) 한 번도 나타나지 않았습니다(시나리오 경로 또는 선택자 확인).")
        if w.get("error"):
            health = "degraded" if health == "ok" else health
            notes.append(f"{rid}: 시간 창 '{w.get('id')}' 측정 오류: {w.get('error')}")
        elif w.get("open_interval_ms") is not None:
            notes.append(f"{rid}: 시간 창 '{w.get('id')}'은 관찰 종료 시 열려 있습니다. 이후 소멸 여부는 미검사입니다.")
    if run.get("temporal_candidates_dropped"):
        health = "degraded" if health == "ok" else health
        notes.append(f"{rid}: 시간 후보 상한으로 {run['temporal_candidates_dropped']}개 후보를 보존하지 못했습니다.")
    if run.get("temporal_sampling_truncated"):
        health = "degraded" if health == "ok" else health
        notes.append(f"{rid}: 페이지 변경/활성 시간 후보 상한에 도달해 후보 관찰이 불완전합니다.")
    for replay in run.get("probe_replays", []):
        for walk in replay.get("walks", []):
            if walk.get("ended") in ("time_budget", "max_stops", "opaque_frame"):
                health = "degraded" if health == "ok" else health
                notes.append(f"{rid}: 중간 상태 {replay.get('id')}의 {walk.get('direction')} 검사 범위 제한: {walk['ended']}.")
    game = (run.get("surface") or {}).get("kind") == "game" or any(w.get("kind") == "qte" for w in (scenario or {}).get("timing_windows", []))
    if game and not (run.get("flash_sampling") or {}).get("enabled"):
        notes.append(f"{rid}: 섬광(광과민성) 프레임 검사를 하지 않았습니다(--flash-sample-ms 없음). GM-04 결과가 없다는 것은 통과가 아닙니다.")
    return health, notes


def analyze_run(
    run_dir: str | Path,
    profiles: Iterable[dict[str, Any]],
    scenario: dict[str, Any] | None = None,
    cross_profile: bool = False,
    verify_screenshots: bool = True,
    gaze_enabled: bool = True,
    analytical_rescore: bool = False,
) -> dict[str, Any]:
    run, snapshots = load_run_dir(run_dir, verify_screenshots=verify_screenshots)
    if scenario is not None and (scenario.get("schema_version") != "ergo-scenario.v1" or scenario.get("scenario_id") != run.get("scenario_id")):
        raise ValueError("supplied scenario schema or ID does not match the recorded run")
    profile_list = list(profiles)
    by_id = profile_index(profile_list)
    own = by_id.get(run.get("profile_id"))
    no_profile = run.get("profile_id") == "no-profile"
    if no_profile and not cross_profile:
        raise ValueError(
            f"run {run['run_id']} was recorded with --device and no profile; "
            "add --cross-profile and supply --profiles with profiles for the recorded device, "
            "or record the run again with --profile"
        )
    if own is None and not no_profile:
        raise ValueError(f"profile {run.get('profile_id')!r} of run {run['run_id']} not supplied")
    if not snapshots:
        raise ValueError(f"run {run['run_id']} has no snapshots")
    if no_profile:
        recorded_device = run["device"]
        device_id = recorded_device["id"]
        orientation = recorded_device["orientation"]
        if not device_id:
            raise ValueError(f"run {run['run_id']} has no recorded device ID; record it again with --device ID")
        evaluated = [
            p for p in profile_list
            if p["attributes"]["device_id"] == device_id and p["attributes"].get("orientation", "portrait") == orientation
        ]
        if not evaluated:
            raise ValueError(
                f"run {run['run_id']}: no supplied profiles match recorded device {device_id!r} "
                f"and orientation {orientation!r}; supply --profiles with matching profiles and use --cross-profile"
            )
        own = None  # No profile owns this operator's judgment notes.
    else:
        device_id = own["attributes"]["device_id"]
        orientation = own["attributes"].get("orientation", "portrait")
        if run["device"]["id"] != device_id or run["device"]["orientation"] != orientation:
            raise ValueError(f"run {run['run_id']}: recorded device {run['device']['id']!r}/"
                             f"{run['device']['orientation']!r} does not match profile "
                             f"{own['profile_id']} ({device_id!r}/{orientation!r})")
        evaluated = [own]
    if cross_profile and not no_profile:
        evaluated += [
            p for p in profile_list
            if p is not own and p["attributes"]["device_id"] == device_id and p["attributes"].get("orientation", "portrait") == orientation
        ]
    binding = run.get("profile_binding")
    profile_status = "no_profile" if no_profile else match_status(binding, own)
    if binding is not None and profile_status != "matched" and not analytical_rescore:
        raise ValueError(f"run {run['run_id']}: recorded profile binding {profile_status}; "
                         "use --analytical-rescore for an analytical comparison")
    verified_owner = own if profile_status == "matched" else None
    snapshots_by_id = {s["snapshot_id"]: s for s in snapshots}
    live_snapshots = [s for s in snapshots if s.get("device", {}).get("probe") != "adaptation"]
    if not live_snapshots:
        raise ValueError(f"run {run['run_id']} has no live task captures")
    live_by_id = {s["snapshot_id"]: s for s in live_snapshots}
    # Probe captures are a separate execution. Never relabel their measurements
    # with the task run's snapshots or treat them as task completion evidence.
    probes = []
    probe_gaps = []
    for replay in run.get("probe_replays", []):
        if replay.get("status") != "observed":
            probe_gaps.append(f"{run['run_id']} focus replay {replay.get('id')}: {replay.get('reason') or 'not checked'}")
            continue
        if replay.get("source_snapshot_id") not in live_by_id:
            raise ValueError("focus replay source capture is not part of the task run")
        probe_path = resolve_within(Path(run_dir), replay["run_path"])
        probe_run, probe_snapshots = load_run_dir(probe_path.parent, verify_screenshots=verify_screenshots)
        if (probe_run["run_id"] != replay.get("run_id") or probe_run.get("status") != "completed"
                or probe_run.get("device") != run.get("device")
                or probe_run.get("surface", {}).get("url") != run.get("surface", {}).get("url")
                or probe_run.get("surface", {}).get("build_id") != run.get("surface", {}).get("build_id")):
            raise ValueError("focus replay identity, build, device or completion does not match")
        probes.append((probe_run, {s["snapshot_id"]: s for s in probe_snapshots}, replay))
    step_by_after = {s.get("after"): s for s in run.get("steps", []) if s.get("after")}
    selectors = _path_selectors(run, live_by_id)
    clicked = _path_selectors(run, live_by_id, CLICK_ACTIONS)
    conspicuity: dict[str, Any] = {}
    if gaze_enabled:
        for snap in live_snapshots:
            conspicuity[snap["snapshot_id"]] = conspicuity_for_snapshot(snap)
    observations: list[checks.Observation] = []
    for profile in evaluated:
        previous = None
        for snap in live_snapshots:
            device = _device_for(snap, profile)
            path_ids = {e["id"] for e in snap.get("elements", []) if e.get("selector") in selectors}
            ctx = checks.Context(
                run=run, snapshot=snap, previous=previous, step=step_by_after.get(snap["snapshot_id"]),
                profile=profile, device=device, scenario=scenario, conspicuity=conspicuity.get(snap["snapshot_id"]),
                path_element_ids=path_ids,
                clicked_element_ids={e["id"] for e in snap.get("elements", []) if e.get("selector") in clicked},
            )
            observations.extend(checks.run_snapshot_checks(ctx))
            previous = snap
        device = _device_for(live_snapshots[-1], profile)
        run_obs = (checks.check_run_timing(run, profile, device, live_by_id, scenario) + checks.check_focus_walks(run, profile, live_by_id)
                   + checks.check_reflow(run, profile, live_by_id) + checks.check_adaptation(run, profile, snapshots_by_id)
                   + checks.check_clicked_controls(run, profile, live_by_id)
                   + checks.check_task_integrity(run, profile, live_by_id))
        if profile is not verified_owner:
            run_obs = [o for o in run_obs if o.check_id != "PJ-01"]
        observations.extend(run_obs)
        for probe_run, probe_snapshots, replay in probes:
            for observation in checks.check_focus_walks(probe_run, profile, probe_snapshots):
                observation.extra.update({"probe_kind": "intermediate_focus", "source_run_id": run["run_id"],
                                          "source_snapshot_id": replay["source_snapshot_id"], "probe_path": replay["run_path"]})
                observations.append(observation)
    # A selector may be reused by a later screen. Preserve that evidence before
    # deduplication, while repeated captures of the same screen keep the worst
    # per-element observation. Every snapshot observation names its screen so
    # reports can summarize advisory warnings by rule and screen.
    for snap in live_snapshots:
        elements = snap.get("elements", [])
        screen = screen_identity(snap)
        by_id = {e["id"]: e for e in elements}
        for obs in observations:
            if obs.snapshot_id != snap["snapshot_id"]:
                continue
            obs.extra["screen"] = screen
            if obs.check_id not in checks.REPEATED_ELEMENT_CHECKS or len(obs.element_ids) != 1:
                continue
            element = by_id[obs.element_ids[0]]
            family = element.get("selector_family") or element.get("selector") or element["id"]
            obs.extra["warning_group"] = {
                "screen_key": screen["key"], "selector_family": family,
                "role": element.get("role", ""), "roles": sorted(element.get("roles") or []),
            }
    observations = _dedupe(observations)
    evidence_snapshots = snapshots + [s for _, probe_snapshots, _ in probes for s in probe_snapshots.values()]
    selector_of = {
        (snap["snapshot_id"], e.get("id")): e.get("selector")
        for snap in evidence_snapshots for e in snap.get("elements", []) if e.get("selector")
    }
    context_of = {
        (snap["snapshot_id"], e.get("id")): [f"#{a}" for a in (e.get("ancestor_ids") or []) if isinstance(a, str) and a]
        for snap in snapshots for e in snap.get("elements", [])
    }
    estimated = {snap["snapshot_id"] for snap in snapshots if snap.get("geometry_basis") == "estimated"}
    vision_elements = {(snap["snapshot_id"], e.get("id")) for snap in snapshots for e in snap.get("elements", []) if e.get("source") == "vision"}
    dicts = []
    for index, obs in enumerate(observations):
        record = obs.to_dict(index)
        if obs.snapshot_id in estimated or any((obs.snapshot_id, eid) in vision_elements for eid in obs.element_ids):
            # Geometry or colours estimated from a screenshot (spec section 11): never observed.
            record["epistemic_status"] = "inferred"
            record["geometry_basis"] = "estimated"
        record["selectors"] = [s for s in (selector_of.get((obs.snapshot_id, eid)) for eid in obs.element_ids) if s] or list(obs.extra.get("anchor_selectors") or [])
        record["context_selectors"] = sorted({c for eid in obs.element_ids for c in context_of.get((obs.snapshot_id, eid), [])}
                                             | set(obs.extra.get("context_selectors") or []))
        record["scenario_id"] = run.get("scenario_id")
        record["analysis_kind"] = ("captured_task" if obs.check_id == "TI-01" else
                                   "owner_execution" if verified_owner and obs.profile_id == verified_owner["profile_id"]
                                   else "analytical_cross_profile")
        dicts.append(record)
    coverage: dict[str, list[str]] = {}
    for obs in observations:
        coverage.setdefault(f"{obs.check_id}||{obs.element_key}", [])
        if obs.profile_id not in coverage[f"{obs.check_id}||{obs.element_key}"]:
            coverage[f"{obs.check_id}||{obs.element_key}"].append(obs.profile_id)
    limitations = [
        f"{run['run_id']} step {n.get('step_index')}: {n.get('failure_class')} — {n.get('observed', '')}"
        for n in run.get("persona_notes", []) if n.get("confusion") and n.get("failure_class") in ("agent_limitation", "environment")
    ]
    health, health_notes = run_health(run, snapshots, scenario)
    limitations += health_notes
    if profile_status not in ("matched", "no_profile"):
        limitations.append(f"{run['run_id']}: profile condition {profile_status}; captured task evidence is separate")
    limitations += probe_gaps
    if probe_gaps and health == "ok":
        health = "degraded"
    limitations += sorted({
        f"{obs.run_id} {obs.snapshot_id} {obs.check_id} {obs.element_key.split('|', 1)[0]}: {obs.message_ko}"
        for obs in observations if obs.extra.get("verdict") == "inconclusive"
    })
    limitations += sorted({
        f"{run['run_id']} {snap['snapshot_id']} {element.get('selector') or element['id']}: PC-02/PC-03 paint unverified ({', '.join(element['paint']['gaps'])})"
        for snap in snapshots for element in snap.get("elements", [])
        if element.get("enabled", True) and element.get("paint", {}).get("gaps")
    })
    limitations += sorted({
        f"{run['run_id']} {snap['snapshot_id']} {element.get('selector') or element['id']}: 화면 표시 여부를 측정하지 않았습니다. 숨김으로 판단하지 않습니다."
        for snap in snapshots for element in snap.get("elements", []) if element.get("visible") is None
    })
    return {
        "health": health,
        "limitations": limitations,
        "agent": run.get("agent", {}),
        "run_id": run["run_id"],
        "scenario_id": run.get("scenario_id"),
        "run_status": run.get("status"),
        "run_success": run.get("success"),
        "started_at": run["started_at"],
        "ended_at": run.get("ended_at"),
        "device_id": device_id,
        "orientation": orientation,
        # Historical recorded ID is not proof of profile content or observed anatomy.
        "owner_profile_id": None if no_profile else run.get("profile_id"),
        "verified_owner_profile_id": verified_owner["profile_id"] if verified_owner else None,
        "profile_binding_status": profile_status,
        "recorded_profile_binding": binding,
        "recorded_build_id": (run.get("surface") or {}).get("build_id", run.get("build_id")),
        "profiles_evaluated": [p["profile_id"] for p in evaluated],
        "observations": dicts,
        "coverage": coverage,
        "temporal_candidates": run.get("temporal_candidates", []),
        "probe_replays": run.get("probe_replays", []),
    }
