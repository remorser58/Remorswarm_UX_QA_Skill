"""Execute existing saved research personas through ScaleExecution, local model router and owned headless Chrome.

This entry never creates personas or a product target. It refuses missing/stale
libraries and only opens an explicit loopback app URL in isolated Chrome profiles.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import sys
import time
import urllib.request
from types import SimpleNamespace

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))
from uxresearch.canonical import byte_digest, canonical
from uxresearch.storage import atomic, read_bytes, read_json, safe_path
from uxpersonas.library import Library
from uxpersonas.product_controls import bind_scale, revalidate
from uxpersonas.scale_entry import ScaleLimits, prepare_scale_goal, preview, required_fixture_keys, scale_job_id
from uxpersonas.scale_run import execute_scale
from uxpersonas.swarm_providers import ProviderSpec
from uxpersonas.model_router import ModelRoute, ModelRouter, RoutedScaleProvider
from uxpersonas.scale_browser_host import ScaleBrowserHost
from uxpersonas.agent_run import Tool

NODE_DEFAULT = shutil.which("node") or "node"
CHROME_DEFAULT = (
    shutil.which("google-chrome")
    or shutil.which("chromium")
    or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
BASE_URL = os.environ.get("REMORSEARCH_MODEL_BASE_URL", "http://127.0.0.1:10100/v1")

TOOLS = [
    Tool("observe", "Read the current page title, visible text and visible controls; capture a screenshot.", {}, "owned_fixture_write"),
    Tool("click", "Click one visible, enabled, non-submit control by exact CSS selector and its exact visible label. The label is rechecked at action time to avoid stale selectors.", {"selector":"string","label":"string"}, "owned_fixture_write"),
    Tool("type", "Enter synthetic non-sensitive text into a visible text or textarea control by exact CSS selector.", {"selector":"string","value":"string"}, "owned_fixture_write"),
    Tool("upload", "Choose one hash-verified synthetic fixture or one reviewed @group:<name> multi-file fixture from the manifest for a visible or hidden file input.", {"selector":"string","file":"string"}, "owned_fixture_write"),
    Tool("upload_cancel", "Upload only a reviewed large-valid-progress fixture and click its visible stop control while processing; capture actual interruption and saved-state hashes.", {"selector":"string","file":"string"}, "owned_fixture_write"),
    Tool("upload_save_failure", "Upload a reviewed small synthetic snapshot with one isolated snapshot-storage write failure; capture the real error and prior-state preservation, then use a separate visible retry click.", {"selector":"string","file":"string"}, "owned_fixture_write"),
    Tool("seed_legacy_unknown", "Once, before any mutating action in a legacy-state task, seed only the configured manifest legacy-seed fixture into this fresh owned synthetic profile; reload through the product loader and validate readback. This sets up a prerequisite, not a product pass. Never repeat after uncertain delivery.", {"file":"string"}, "owned_fixture_write"),
    Tool("scroll", "Scroll the current page by a bounded signed pixel delta.", {"delta":"integer"}, "owned_fixture_write"),
    Tool("wait", "Wait briefly for the current page to settle.", {"ms":"integer"}, "owned_fixture_write"),
]


def _route(ledger_path=None, *, base_url=None, provider_name=None, model=None):
    secret = os.environ.get("PROXY_API_KEY")
    if not isinstance(secret, str) or not secret or len(secret) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in secret):
        raise RuntimeError("local_gateway_auth_unavailable")
    resolved_base_url = base_url or BASE_URL
    resolved_provider = provider_name or os.environ.get("REMORSEARCH_PROVIDER_NAME", "local-gateway")
    resolved_model = model or os.environ.get("REMORSEARCH_MODEL_ID")
    if not isinstance(resolved_model, str) or not resolved_model.strip():
        raise RuntimeError("reviewed_model_id_required")
    request = urllib.request.Request(resolved_base_url + "/models", headers={
        "Accept":"application/json", "Authorization":"Bearer " + secret})
    with urllib.request.urlopen(request, timeout=10) as response:
        catalog = json.loads(response.read(2 * 1024 * 1024 + 1))
    if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
        raise RuntimeError("local_gateway_model_catalog_invalid")
    model_ids = {row.get("id") for row in catalog["data"] if isinstance(row, dict) and isinstance(row.get("id"), str)}
    if resolved_model not in model_ids:
        raise RuntimeError("reviewed_model_not_in_local_catalog")
    routes = [ModelRoute(resolved_provider, resolved_model, "0", "0", 30, (resolved_model,))]
    router = ModelRouter(resolved_base_url, routes, timeout=150, max_retries=2,
        backoff_initial=2, backoff_max=30, ledger_path=ledger_path)
    spec = _provider_spec(model=resolved_model)
    provider = RoutedScaleProvider(spec, router)
    return router, {"local-router": provider}, spec, [route.model for route in routes]


def _provider_spec(*, model=None):
    """The launcher's fixed route contract, available without contacting its catalog."""
    raw_name = (model or os.environ.get("REMORSEARCH_MODEL_ID") or "configured-free-model").lower()
    safe_model = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in raw_name).strip("-") or "configured-free-model"
    return ProviderSpec(key="local-router", protocol="callback", model=safe_model[:64],
        concurrency=2, requests_per_minute=30,
        input_price_per_million=0, output_price_per_million=0,
        input_token_cap=262144, output_token_cap=16384, timeout_seconds=180)


def _read_selection(path):
    if path is None:
        raise RuntimeError("reviewed_selection_required")
    # Reuse the CLI's bounded, strict JSON reader and controls integrity checks.
    # A proposal, cancellation or unconfirmed choice is not a selection receipt.
    return revalidate(read_json(path))


def _selection_preflight(selection, args, persona_ids, library):
    choice = selection["choice"]
    if choice["parallel"] > 2 or choice["budget_microusd"] != 0 or choice["turns"] != args.turns:
        raise RuntimeError("selection_exceeds_launcher_scope_or_turns_differ")
    if set(choice["assignments"].values()) != {"local-router"}:
        raise RuntimeError("selection_route_not_supported")
    limits = replace(live_limits(len(persona_ids), args.turns), parallel=choice["parallel"],
                     max_model_calls=choice["max_model_calls"])
    limits.validate()
    # Validate against the same fixed spec _route will construct, before its
    # authenticated catalog request. Preparation rechecks the real provider.
    bind_scale(selection, product_id=args.product_id, persona_ids=persona_ids,
        assignments=choice["assignments"], providers={"local-router": SimpleNamespace(spec=_provider_spec(model=getattr(args, "model", None)))},
        limits=limits, library=library)
    return limits


def _execution_consent(args):
    # Selection grants no execution/cost authority. Require the host's separate
    # current consent reference with the existing Queue.authorize field bounds.
    actor, reference = getattr(args, "approval_actor", None), getattr(args, "consent_reference", None)
    if (not isinstance(actor, str) or not actor.strip() or len(actor) > 160
            or not isinstance(reference, str) or not reference.strip() or len(reference) > 500):
        raise RuntimeError("explicit_execution_consent_required")
    return actor, reference


def _load_personas(library_path, product_id, count):
    if not (library_path / "library.json").is_file():
        raise RuntimeError("saved_persona_library_missing")
    with Library(library_path) as library:
        rows = library.list(product_id)["personas"]
        reusable = [row for row in rows if row.get("reusable")]
    if len(reusable) < count:
        raise RuntimeError("insufficient_current_saved_personas:"+str(len(reusable)))
    return [row["persona_id"] for row in reusable[:count]]


def live_limits(session_count, turns=16):
    limits = ScaleLimits(parallel=2, turns=turns, call_seconds=180, task_seconds=max(1800, turns * 45),
        lease_seconds=240, budget_microusd=0, max_model_calls=session_count*(turns+1))
    limits.validate()
    return limits


def fixture_preflight(fixtures, requirement_ids):
    """Fail before any provider call if a required fixture set is incomplete."""
    manifest_path = fixtures / "fixture-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != "ux-synthetic-fixtures.v1":
        raise RuntimeError("ux_fixture_manifest_invalid")
    files = {row["name"]: row for row in manifest.get("files", [])}
    groups = manifest.get("groups", {})
    catalog = set(files) | {"@group:" + name for name in groups}
    required = required_fixture_keys(requirement_ids)
    missing = sorted(set(required) - catalog)
    if missing:
        raise RuntimeError("required_fixture_missing:" + ",".join(missing))
    selected = set()
    for key in required:
        names = groups[key.removeprefix("@group:")] if key.startswith("@group:") else [key]
        if not isinstance(names, list) or not names:
            raise RuntimeError("required_fixture_group_invalid:" + key)
        for name in names:
            if name not in files or not safe_path(fixtures / name, fixtures).is_file():
                raise RuntimeError("required_fixture_file_missing:" + str(name))
            selected.add(name)
    total_bytes = 0
    for name in sorted(selected):
        row = files[name]
        path = safe_path(fixtures / name, fixtures)
        if type(row.get("bytes")) is not int or path.stat().st_size != row["bytes"]:
            raise RuntimeError("required_fixture_size_mismatch:" + name)
        actual = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                actual.update(chunk)
        if actual.hexdigest() != row.get("sha256"):
            raise RuntimeError("required_fixture_digest_mismatch:" + name)
        total_bytes += row["bytes"]
    return dict(required_fixture_keys=required, required_file_count=len(selected),
                verified_fixture_bytes=total_bytes,
                fixture_manifest_sha256=byte_digest(read_bytes(manifest_path)))


def _reject_forbidden_jobs(job_ids, forbidden_job_ids):
    overlap = set(job_ids) & set(forbidden_job_ids or ())
    if overlap:
        raise RuntimeError("prior_job_identity_overlap:" + str(len(overlap)))

async def _execute_with_shutdown(run_root, providers, host, router):
    """Preserve delivery and teardown evidence even when the stage cannot pass."""
    report = None
    execution_error = None
    shutdown_error = None
    try:
        report = await execute_scale(run_root, providers, host, reviewed=True, max_idle_seconds=30)
    except BaseException as exc:
        execution_error = exc
    try:
        stopped = await host.shutdown()
    except BaseException as exc:
        stopped = False
        shutdown_error = exc
    write_errors = []
    documents = [("model-router-ledger.json", router.report())]
    if report is not None:
        documents.append(("report.json", report))
    for name, value in documents:
        try:
            atomic(run_root / name, canonical(value))
        except (OSError, ValueError) as exc:
            write_errors.append(name + ":" + type(exc).__name__)
    diagnostics = {
        "schema_version": "owned-browser-shutdown.v1",
        "browser_shutdown_confirmed": stopped,
        "execution_error": ({"type": type(execution_error).__name__,
                             "reason": str(execution_error)[:240]} if execution_error else None),
        "shutdown_error": ({"type": type(shutdown_error).__name__,
                            "reason": str(shutdown_error)[:240]} if shutdown_error else None),
        "contexts": getattr(host, "lifecycle", {}),
        "unclosed_contexts": sorted(getattr(host, "processes", {})),
        "diagnostic_write_errors": list(write_errors),
    }
    try:
        atomic(run_root / "browser-lifecycle-summary.json", canonical(diagnostics))
    except (OSError, ValueError) as exc:
        write_errors.append("browser-lifecycle-summary.json:" + type(exc).__name__)
    if execution_error is not None:
        raise execution_error
    if shutdown_error is not None and not isinstance(shutdown_error, Exception):
        raise shutdown_error
    if not stopped:
        raise RuntimeError("browser_shutdown_unconfirmed")
    if write_errors:
        raise RuntimeError("browser_diagnostics_not_persisted:" + ",".join(write_errors))
    return report, stopped


async def run_stage(args, persona_ids, index, *, selection=None, expected_selection_sha256=None):
    run_root = safe_path(args.run_root / ("stage-"+str(index)))
    if run_root.exists():
        raise RuntimeError("stage_output_exists")
    if not persona_ids or len(persona_ids) != len(set(persona_ids)):
        raise RuntimeError("persona_cohort_identity_mismatch")
    with Library(args.library) as library:
        saved = {row["persona_id"]: row for row in library.list(args.product_id)["personas"] if row.get("reusable")}
        if any(pid not in saved for pid in persona_ids):
            raise RuntimeError("saved_persona_missing_or_stale")
        requirement_ids = {rid for pid in persona_ids
            for rid in library.get(args.product_id, pid, saved[pid]["revision"])["profile"]["requirement_ids"]}
    fixture_check = fixture_preflight(args.fixtures, requirement_ids)
    artifact_path = safe_path(args.build_artifact)
    build = dict(id=args.build_id, artifact_path=str(artifact_path),
        sha256=byte_digest(read_bytes(artifact_path)))
    forbidden_jobs = getattr(args, "forbidden_job_ids", ())
    _reject_forbidden_jobs((scale_job_id(args.product_id, pid, saved[pid]["revision"], args.goal, build)
                           for pid in persona_ids), forbidden_jobs)
    selection = _read_selection(selection)
    if expected_selection_sha256 is not None and selection["selection_sha256"] != expected_selection_sha256:
        raise RuntimeError("reviewed_selection_changed_before_stage")
    actor, consent_reference = _execution_consent(args)
    with Library(args.library) as library:
        limits = _selection_preflight(selection, args, persona_ids, library)
    router, providers, spec, configured_routes = _route(
        run_root / "model-router-ledger.live.json",
        base_url=getattr(args, "base_url", None),
        provider_name=getattr(args, "provider_name", None),
        model=getattr(args, "model", None),
    )
    host = ScaleBrowserHost(target_url=args.url, chrome=args.chrome, node=args.node,
        driver_path=SKILL / "drivers/web/scale_browser_cdp.mjs",
        adapter_path=SKILL / "uxpersonas/scale_browser_host.py",
        fixtures_path=args.fixtures, parallel_safe=True)
    resolved_model = configured_routes[0] if configured_routes else spec.model
    billing_review = {"input_token_cap":spec.input_token_cap,"output_token_cap":spec.output_token_cap,
        "input_price_per_million":spec.input_price_per_million,
        "output_price_per_million":spec.output_price_per_million,
        "no_unpriced_features":True,
        "free_tier":True,"billing_source":"free",
        "requested_model":resolved_model,
        "source":"User-confirmed zero-cost local model gateway route.",
        "checked_at":datetime.now(timezone.utc).isoformat()}
    started = time.monotonic()
    with Library(args.library) as library:
        queue = prepare_scale_goal(library, run_root, providers, host, TOOLS,
            product_id=args.product_id, target=args.target, goal=args.goal, build=build,
            limits=limits, persona_ids=persona_ids, assignments=selection["choice"]["assignments"],
            selection=selection,
            credential_scopes={"local-router":"local gateway configuration; no key material exposed"},
            reviewed=True, tool_provenance="owned_browser",
            billing_reviews={"local-router":billing_review},
            provider_destinations={"local-router":getattr(args, "base_url", None) or BASE_URL})
    _reject_forbidden_jobs((job["id"] for job in queue.plan["jobs"]), forbidden_jobs)
    plan_preview = preview(queue)
    atomic(run_root / "preview.json", canonical(plan_preview))
    approval_seconds = max(3600, ((len(persona_ids) + limits.parallel - 1) // limits.parallel)
                           * limits.task_seconds + 300)
    approval = queue.authorize(plan_sha256=queue.plan_sha256,
        actor=actor, consent_reference=consent_reference,
        budget_microusd=limits.budget_microusd,
        expires_at=time.time()+approval_seconds)
    queue.control("resume")
    atomic(run_root / "approval.json", canonical({"approval_id":approval,"plan_sha256":queue.plan_sha256,
        "budget_microusd":limits.budget_microusd,"expires_in_seconds":approval_seconds}))
    report, stopped = await _execute_with_shutdown(run_root, providers, host, router)
    usage = report.get("provider_usage", [])
    route_stats = router.report()["routes"]
    route_stats = {model: dict(stats, failure_rate=((stats["failures"]+stats["quality_rejections"]) / stats["attempts"] if stats["attempts"] else 0.0))
                   for model, stats in route_stats.items()}
    events = [event for event in router.report()["events"]
              if event.get("status") != "quality_rejected"]
    completed = sum(bool((task.get("result") or {}).get("operational_completed"))
                    for task in report.get("tasks", []))
    validation = report.get("evidence_validation", {})
    completed_summary = report.get("completed_receipt_summary", {})
    ready = (completed == len(persona_ids) and report["counts"]["complete"] == len(persona_ids)
        and validation.get("current_valid_sessions") == len(persona_ids)
        and not any(report["counts"][key] for key in ("queued", "running", "uncertain", "blocked", "cancelled")))
    summary = {
        "stage_cumulative_sessions":index,"sessions":len(persona_ids),"persona_ids":persona_ids,
        "counts":report["counts"],"elapsed_seconds":round(time.monotonic()-started,3),
        "actual_model_calls":report["actual_model_calls"],"actual_browser_tool_calls":sum(
            op["kind"]=="tool" and op["state"]=="done" for op in report["operations"]),
        "provider_usage":usage,"budget":report["budget"],
        "fallback_model_attempts":0,
        "model_attempts":route_stats,"configured_routes":configured_routes,
        "delivery_policy":{"uncertain_resends":0,"known_reply_retries":router.max_retries,
            "timeout_seconds":router.timeout,"durable_call_id_guard":router.ledger_path is not None},
        "fixture_manifest_sha256":byte_digest(read_bytes(args.fixtures / "fixture-manifest.json")),
        "browser_shutdown_confirmed":stopped,
        "current_evidence_validation":report.get("evidence_validation"),
        "completed_receipt_summary":completed_summary,
        "fixture_preflight":fixture_check,
        "operational_completed_sessions":completed,
        "stage_ready_for_expansion":ready,
        "input_tokens_all_attempts":sum(row["input_tokens"] for row in route_stats.values()),
        "output_tokens_all_attempts":sum(row["output_tokens"] for row in route_stats.values()),
        "cost_record":{"authorized_route":"user_confirmed_free_gateway",
            "policy_cost_usd":0,
            "provider_reported_cost_values":[event.get("provider_reported_cost") for event in events],
            "billing_source_values":[event.get("billing_source") for event in events],
            "missing_cost_responses":sum(event.get("provider_reported_cost") is None for event in events),
            "provider_invoice_verified":False},
        "real_user_evidence":False,"product_ready":False,
    }
    atomic(run_root / "stage-summary.json", canonical(summary))
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return summary


async def main(args):
    _execution_consent(args)
    receipt_paths = getattr(args, "selection", None)
    if not isinstance(receipt_paths, list) or len(receipt_paths) != len(args.stages):
        raise RuntimeError("one_reviewed_selection_required_per_stage")
    selections = [_read_selection(path) for path in receipt_paths]
    args.library = safe_path(args.library)
    args.run_root = safe_path(args.run_root)
    args.build_artifact = safe_path(args.build_artifact)
    args.fixtures = safe_path(args.fixtures)
    if not args.library.is_dir() or not args.build_artifact.is_file() or not args.fixtures.is_dir():
        raise RuntimeError("library_build_or_fixture_artifact_missing")
    if not (args.library / "library.json").is_file():
        raise RuntimeError("saved_persona_library_missing")
    fixture_manifest = json.loads((args.fixtures / "fixture-manifest.json").read_text())
    if fixture_manifest.get("schema_version") != "ux-synthetic-fixtures.v1" or not fixture_manifest.get("files"):
        raise RuntimeError("ux_fixture_manifest_invalid")
    if args.run_root.exists():
        raise RuntimeError("run_root_exists_preserved")
    if args.start_index < 0 or args.start_index >= 32:
        raise RuntimeError("persona_start_index_out_of_range")
    cursor, seen = args.start_index, set()
    with Library(args.library) as library:
        for count, selection in zip(args.stages, selections):
            ids = selection["choice"]["persona_ids"]
            if count <= cursor or count > 32 or len(ids) != count - cursor or seen.intersection(ids):
                raise RuntimeError("selected_stage_cohort_mismatch")
            _selection_preflight(selection, args, ids, library)
            seen.update(ids)
            cursor = count
    args.run_root.mkdir(parents=True,mode=0o700)
    stages=[]
    for count, selection, path in zip(args.stages, selections, receipt_paths):
        # Re-read at each stage so cancelled/changed/stale input cannot use a
        # cached confirmation after an earlier stage has run.
        summary=await run_stage(args,selection["choice"]["persona_ids"],count,selection=path,
                                expected_selection_sha256=selection["selection_sha256"])
        stages.append(summary)
        atomic(args.run_root / "stages.json", canonical({"stages":stages,
            "total_sessions":sum(x["sessions"] for x in stages),
            "actual_model_calls":sum(x["actual_model_calls"] for x in stages),
            "real_user_evidence":False,"product_ready":False}))
        if not summary["stage_ready_for_expansion"]:
            raise RuntimeError("stage_incomplete_preserved:"+str(count))


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--library",required=True,type=Path)
    p.add_argument("--product-id",required=True)
    p.add_argument("--url",required=True,help="Running owned product app on localhost/127.0.0.1")
    p.add_argument("--target",required=True)
    p.add_argument("--goal",required=True)
    p.add_argument("--build-id",required=True)
    p.add_argument("--build-artifact",required=True,type=Path)
    p.add_argument("--fixtures",required=True,type=Path)
    p.add_argument("--run-root",required=True,type=Path)
    p.add_argument("--selection", required=True, type=Path, action="append",
        help="Existing ux_personas select receipt; repeat once per stage in order. No default selection.")
    p.add_argument("--approval-actor", required=True, help="Actor for the separate current execution approval")
    p.add_argument("--consent-reference", required=True,
        help="Reference to explicit current execution consent for these exact stages and the zero-cost route")
    p.add_argument("--base-url", default=BASE_URL, help="OpenAI-compatible loopback model gateway URL")
    p.add_argument("--provider-name", default=os.environ.get("REMORSEARCH_PROVIDER_NAME", "local-gateway"))
    p.add_argument("--model", default=os.environ.get("REMORSEARCH_MODEL_ID"),
        help="Reviewed model selector for the configured local gateway")
    p.add_argument("--node",type=Path,default=Path(NODE_DEFAULT))
    p.add_argument("--chrome",type=Path,default=Path(CHROME_DEFAULT))
    p.add_argument("--stages",type=int,nargs="+",default=[4,16,32],
        help="cumulative persona indices to execute (e.g. 4 16 32)")
    p.add_argument("--start-index",type=int,default=0,
        help="Prior cumulative endpoint; receipts must explicitly name only new personas, never resume old queues")
    p.add_argument("--turns", type=int, default=16, help="bounded model decisions per persona (4..64); retention journeys require an explicit larger budget")
    args=p.parse_args(argv)
    if not 4 <= args.turns <= 64:
        p.error("turns must be from 4 to 64")
    if args.start_index < 0 or args.start_index >= 32:
        p.error("start-index must be between 0 and 31")
    if any(n<=args.start_index or n>32 for n in args.stages) or args.stages != sorted(set(args.stages)):
        p.error("cumulative stage endpoints must be strictly increasing values after start-index and at most 32")
    if len(args.selection) != len(args.stages):
        p.error("supply one --selection receipt per stage")
    return args

if __name__=="__main__":
    try:
        asyncio.run(main(parse_args()))
    except Exception as exc:
        print(json.dumps({"result":"blocked","error_type":type(exc).__name__,
            "reason":str(exc)[:240]},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(2)
