"""Explicitly reviewed local adapters -> existing swarm receipts -> current report.

This is bounded trusted-code execution, not an OS/network sandbox. The host must
review the exact copied Python adapter and its selected inputs before approval.
The separate browser plan uses the bundled measured driver on reviewed static
copies. Neither path installs packages or calls a model.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import threading
import time

from uxresearch.canonical import EngineError, byte_digest, canonical, digest, loads
from uxresearch.storage import Store, atomic, safe_path
from .library import Library, SCHEMA as LIBRARY_SCHEMA
from .research_access import ReferenceScope, roots_for
from . import swarm, workspace, browser_run

PLAN = "ux-journey-local-plan.v1"
STATE = "ux-journey-local-state.v1"
BROWSER_STATE = "ux-journey-browser-state.v1"
MARKER = "local-execution.json"
DIRECTORY = "local-execution"
MAX_OUTPUT = 256 * 1024


def stop(code, reason):
    workspace.stop(code, reason, "호스트가 고정한 입력·실행 범위와 기존 근거를 확인합니다. 기존 작업을 자동 반복하지 않습니다.")


def _private(path):
    path = safe_path(path)
    if path.exists() and path.stat().st_mode & 0o077:
        stop("execution_permissions", "실행 상태와 페르소나 복사본은 비공개 경로여야 합니다.")
    return path


def _read(work):
    _private(work / MARKER)
    envelope = loads(workspace.read_file(work, MARKER))
    state = envelope.get("payload")
    expected = BROWSER_STATE if isinstance(state, dict) and state.get("plan", {}).get("schema_version") == browser_run.PLAN else STATE
    if envelope.get("schema_version") != expected or not isinstance(state, dict) or digest(state) != envelope.get("sha256"):
        stop("execution_integrity", "실행 상태의 무결성을 확인할 수 없습니다.")
    return state


def _save(work, state):
    schema = BROWSER_STATE if state["plan"]["schema_version"] == browser_run.PLAN else STATE
    atomic(work / MARKER, canonical(dict(schema_version=schema, payload=state, sha256=digest(state))))


def _immutable(root, name, raw):
    dest = safe_path(root / name, root)
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _private(dest.parent)
    if dest.exists():
        if workspace.read_file(root, name) != raw:
            stop("execution_conflict", "기존 실행 파일을 덮어쓰지 않았습니다.")
    else:
        atomic(dest, raw)


def _plan(path, prepared):
    path = safe_path(path)
    plan = loads(workspace.read_file(path.parent, path.name, sensitive_check=True))
    if (not isinstance(plan, dict) or set(plan) != {"schema_version", "product_id", "runner", "timeout_seconds", "tasks"}
            or plan["schema_version"] not in {PLAN, browser_run.PLAN}):
        stop("execution_plan", "호스트가 검토한 실행 계획 형식이 맞지 않습니다.")
    workspace.relative(plan["runner"])
    suffix = ".json" if plan["schema_version"] == browser_run.PLAN else ".py"
    if (not plan["runner"].endswith(suffix) or plan["runner"] not in prepared["inputs"]
            or prepared["destinations"][plan["runner"]] != "product/" + plan["runner"]):
        stop("runner_scope", "실행 어댑터가 검토하고 복사한 해당 실행 종류의 파일이 아닙니다.")
    swarm.ident(plan["product_id"])
    swarm.number(plan["timeout_seconds"], 1, 30)
    if (not isinstance(plan["tasks"], list) or not 1 <= len(plan["tasks"]) <= 16
            or len(plan["tasks"]) * plan["timeout_seconds"] > 240):
        stop("execution_budget", "과제 수 또는 전체 실행 한도가 너무 큽니다.")
    for task in plan["tasks"]:
        if not isinstance(task, dict) or "requirement_coverage" not in task:
            stop("execution_coverage", "실행 전에 목표별 PRD 의무와 성공·복구 기준 연결을 고정해야 합니다.")
    if swarm.clean(plan) != plan:
        stop("execution_privacy", "실행 계획에 개인 식별 형식이 있습니다.")
    if plan["schema_version"] == browser_run.PLAN:
        browser_run.manifest(prepared, plan)
    return plan


def _selection(library_path, prepared, plan, research_runs=()):
    library_path = _private(library_path)
    _private(library_path / "library.json")
    raw = workspace.read_file(library_path, "library.json", sensitive_check=True)
    envelope = loads(raw)
    state = envelope.get("state")
    if not isinstance(state, dict) or state.get("schema_version") != LIBRARY_SCHEMA or digest(state) != envelope.get("sha256"):
        stop("persona_integrity", "기존 페르소나 저장소 무결성을 확인할 수 없습니다.")
    selected = dict(schema_version=LIBRARY_SCHEMA, entries={})
    guard = ReferenceScope(prepared, research_runs)
    for task in plan["tasks"]:
        key = Library._key(plan["product_id"], task["persona_id"])
        if key in selected["entries"]:
            continue
        history = state["entries"].get(key, [])
        if not history:
            stop("persona_missing", "목표에 맞게 검토된 기존 페르소나가 없습니다. 자동 생성하지 않았습니다.")
        record = history[-1]
        # Refuse unreviewed references BEFORE existing validators can open them.
        guard(record)
        if record.get("product_id") != plan["product_id"] or record.get("persona_id") != task["persona_id"]:
            stop("persona_integrity", "페르소나 식별자가 저장소 연결과 다릅니다.")
        Library(library_path, reference_guard=guard)._validate(record)
        if swarm.clean(record["profile"]) != record["profile"]:
            stop("persona_privacy", "페르소나에 개인 식별 형식이 있습니다.")
        selected["entries"][key] = [copy.deepcopy(record)]
    if guard.used != set(research_runs):
        stop("research_scope", "선택한 페르소나가 사용하지 않는 연구 위치를 추가할 수 없습니다.")
    return byte_digest(raw), dict(state=selected, sha256=digest(selected))


class _SelectedLibrary:
    """Read-only validated selection for preflight; never lock/write the original."""
    def __init__(self, selected):
        self.selected = selected

    def get(self, product, persona, revision=None, revalidate=True):
        record = self.selected["state"]["entries"][Library._key(product, persona)][-1]
        if revision is not None and record["revision"] != revision:
            stop("stale_persona_revision", "페르소나 버전이 달라졌습니다.")
        return copy.deepcopy(record)


def _copy_scope(work, prepared):
    """Inspect only the owned copy's names; never walk the original or follow links."""
    expected = set()
    for name in prepared["destinations"].values():
        path = Path(name)
        if path.parts[0] != "product":
            continue
        while path != Path("."):
            expected.add(path.as_posix())
            path = path.parent
    pending = ["product"]
    while pending:
        name = pending.pop()
        with os.scandir(safe_path(work / name, work)) as entries:
            for entry in entries:
                relative = name + "/" + entry.name
                if relative not in expected or entry.is_symlink():
                    stop("reviewed_copy_scope", "복사본에 검토하지 않은 파일·디렉터리·링크가 있습니다. 삭제하거나 실행하지 않았습니다.")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(relative)


def _verify(work, prepared, state):
    _copy_scope(work, prepared)
    workspace._verify(work, prepared)
    if byte_digest(workspace.read_file(work, "workspace.json")) != state["workspace_sha256"]:
        stop("execution_build", "실행에 연결된 준비 상태가 달라졌습니다.")
    research_runs = roots_for(state.get("research_runs"), work=work, source=prepared["source"], library=state["library"])
    current_hash, selected = _selection(Path(state["library"]), prepared, state["plan"], research_runs)
    if current_hash != state["library_sha256"] or selected != state["personas"]:
        stop("execution_persona_changed", "실행을 고정한 뒤 기존 페르소나 저장소가 변경됐습니다.")
    if state["phase"] == "ready":
        _private(work / DIRECTORY)
        _private(work / DIRECTORY / "personas")
        if loads(workspace.read_file(work, DIRECTORY + "/personas/library.json")) != selected:
            stop("execution_persona_changed", "복사한 페르소나 버전이 변경됐습니다.")


def _initialize(work, prepared, library_path, input_path, approved, reviewed_research_runs):
    if not approved:
        stop("runner_approval", "호스트의 정확한 코드·범위 검토 확인이 없어 실행하지 않았습니다.")
    if library_path is None or input_path is None:
        stop("execution_input", "호스트가 기존 페르소나와 목표·기준을 연결해야 합니다. 사용자가 매니페스트를 작성할 필요는 없습니다.")
    if prepared["saved"]:
        stop("prior_run_preserved", "기존 실험이 있는 작업공간에서 실행 한도를 초기화하지 않습니다. 검토된 replay 흐름을 사용합니다.")
    plan = _plan(input_path, prepared)
    library_path = safe_path(library_path)
    if library_path.is_relative_to(work) or work.is_relative_to(library_path):
        stop("execution_overlap", "기존 페르소나 저장소와 실행 작업공간은 분리되어야 합니다.")
    research_runs = roots_for(reviewed_research_runs, work=work, source=prepared["source"], library=library_path)
    library_hash, personas = _selection(library_path, prepared, plan, research_runs)
    build_hash = byte_digest(workspace.read_file(work, "workspace.json"))
    spec = dict(schema_version=swarm.SCHEMA, product_id=plan["product_id"],
                build=dict(id="reviewed-" + build_hash[:16], artifact_path=str(work / "workspace.json"), sha256=build_hash),
                max_parallel=1, lease_seconds=120, max_attempts=1, tasks=plan["tasks"])
    seed = swarm._prepare_plan(_SelectedLibrary(personas), spec)
    if (work / DIRECTORY).exists():
        stop("execution_conflict", "기존 파일이 있는 실행 폴더를 사용하지 않았습니다.")
    state = dict(plan=plan, library=str(library_path), library_sha256=library_hash, personas=personas, research_runs=research_runs,
                 workspace_sha256=build_hash, seed=seed, phase="preparing", dispatches={})
    if plan["schema_version"] == browser_run.PLAN:
        state["browser"] = browser_run.prepare(work, prepared, plan, personas, build_hash)
    _save(work, state)  # Durable ownership and fixed criteria before any run files.
    return state


def _finish_preparation(work, state):
    base = _private(work / DIRECTORY)
    base.mkdir(mode=0o700, exist_ok=True)
    if set(p.name for p in base.iterdir()) - {"personas", "run"}:
        stop("execution_conflict", "실행 준비 폴더에 소유하지 않은 파일이 있습니다.")
    _immutable(base, "personas/library.json", canonical(state["personas"]))
    if set(p.name for p in (base / "personas").iterdir()) - {"library.json", "engine.lock"}:
        stop("execution_conflict", "페르소나 복사 폴더에 소유하지 않은 파일이 있습니다.")
    run = _private(base / "run")
    if not run.exists():
        swarm._create_plan(run, state["seed"])
    elif not (run / "swarm-state.json").exists():
        # Recover only our empty interrupted mkdir, never prior evidence/state.
        if set(p.name for p in run.iterdir()) - {"engine.lock", "evidence"}:
            stop("execution_conflict", "실행 준비 도중 기존 파일을 발견했습니다.")
        evidence = _private(run / "evidence")
        evidence.mkdir(mode=0o700, exist_ok=True)
        if any(evidence.iterdir()):
            stop("execution_conflict", "초기 상태 없이 남은 근거를 덮어쓰지 않았습니다.")
        with Store(run):
            swarm._save(run, state["seed"])
    else:
        with Library(base / "personas", reference_guard=ReferenceScope(workspace._state(work), state.get("research_runs", []))) as library:
            with Store(run):
                if swarm._load(run, library, expire_leases=False) != state["seed"]:
                    stop("execution_conflict", "준비가 끝나기 전에 실행 상태가 바뀌었습니다.")
    state["phase"] = "ready"
    _save(work, state)


@contextmanager
def _cancellation():
    prior = {}
    if threading.current_thread() is threading.main_thread():
        def cancel(*_):
            raise KeyboardInterrupt
        for sig in (signal.SIGTERM, signal.SIGINT):
            prior[sig] = signal.signal(sig, cancel)
    try:
        yield
    finally:
        for sig, handler in prior.items():
            signal.signal(sig, handler)


def _stop_owned(process):
    # Only the Popen child owned by this call, never groups or saved/reused PIDs.
    # Reviewed adapters must not launch background workers; this is not a sandbox.
    try:
        if process.poll() is not None:
            return True
        process.terminate()
        try:
            process.wait(timeout=0.3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=0.5)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _invoke(runner, cwd, request, seconds, on_spawn):
    payload = canonical(request)
    if len(payload) > MAX_OUTPUT:
        stop("execution_request", "실행 요청이 허용 크기를 넘었습니다.")
    start, process, output, error = time.monotonic(), None, bytearray(), bytearray()
    problem, cleanup_confirmed = None, True
    try:
        with _cancellation(), selectors.DefaultSelector() as selector:
            process = subprocess.Popen([sys.executable, "-I", "-S", "-B", str(runner)], cwd=cwd,
                env={"PATH": os.defpath, "HOME": str(cwd), "TMPDIR": str(cwd), "LANG": "C", "LC_ALL": "C"},
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, close_fds=True)
            on_spawn()
            for pipe, events in ((process.stdin, selectors.EVENT_WRITE), (process.stdout, selectors.EVENT_READ), (process.stderr, selectors.EVENT_READ)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, events)
            offset = 0
            while selector.get_map():
                remaining = seconds - (time.monotonic() - start)
                if remaining <= 0:
                    problem = "timeout"
                    break
                for key, _ in selector.select(min(remaining, 0.05)):
                    pipe = key.fileobj
                    if pipe is process.stdin:
                        try:
                            offset += os.write(pipe.fileno(), payload[offset:offset + 16384])
                        except BrokenPipeError:
                            offset = len(payload)
                        if offset == len(payload):
                            selector.unregister(pipe)
                            pipe.close()
                    else:
                        chunk = os.read(pipe.fileno(), 16384)
                        if not chunk:
                            selector.unregister(pipe)
                            pipe.close()
                        else:
                            (output if pipe is process.stdout else error).extend(chunk)
                            if len(output) + len(error) > MAX_OUTPUT:
                                problem = "output_limit"
                                break
                if problem:
                    break
            if not problem:
                try:
                    process.wait(timeout=max(0.001, seconds - (time.monotonic() - start)))
                except subprocess.TimeoutExpired:
                    problem = "timeout"
    except KeyboardInterrupt:
        problem = "cancelled"
    except OSError:
        problem = "process_unavailable"
    finally:
        if process is not None:
            cleanup_confirmed = _stop_owned(process)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
    if not problem and process.returncode != 0:
        problem = "nonzero_exit"
    return bytes(output), dict(problem=problem, cleanup_confirmed=cleanup_confirmed, returncode=process.returncode if process else None,
        elapsed_seconds=round(time.monotonic() - start, 6), stdout_bytes=len(output), stderr_bytes=len(error),
        stdout_sha256=byte_digest(output), stderr_sha256=byte_digest(error))


def _observation(raw, binding, task):
    if workspace.SECRET.search(raw):
        stop("observation_private", "실행 출력에 비밀 형식이 있어 원문을 저장하지 않았습니다.")
    doc = loads(raw)
    if (not isinstance(doc, dict) or set(doc) != {"schema_version", "binding", "reason", "steps", "criteria"}
            or doc["schema_version"] != "ux-journey-observation.v1" or doc["binding"] != binding):
        stop("observation_binding", "관측이 현재 과제·시도·빌드·페르소나와 일치하지 않습니다.")
    swarm.text(doc["reason"])
    if not isinstance(doc["steps"], list) or not 1 <= len(doc["steps"]) <= 256:
        stop("observation_steps", "실제 수행 단계가 없습니다.")
    for step in doc["steps"]:
        if not isinstance(step, dict) or set(step) != {"action", "observation"}:
            stop("observation_steps", "관측 단계 형식이 맞지 않습니다.")
        swarm.text(step["action"])
        swarm.text(step["observation"])
    expected = {(kind, i) for kind in ("success", "recovery") for i in range(len(task[kind + "_criteria"]))}
    if not isinstance(doc["criteria"], list) or len(doc["criteria"]) != len(expected):
        stop("observation_criteria", "고정한 성공·복구 기준마다 실제 관측 또는 미실행 사유가 필요합니다.")
    seen = set()
    for row in doc["criteria"]:
        if (not isinstance(row, dict) or set(row) != {"kind", "index", "status", "observation"}
                or type(row["index"]) is not int or row["status"] not in {"passed", "failed", "not_run"}
                or (row["kind"], row["index"]) not in expected or (row["kind"], row["index"]) in seen):
            stop("observation_criteria", "관측 기준이 누락·중복되거나 고정한 기준과 다릅니다.")
        seen.add((row["kind"], row["index"]))
        swarm.text(row["observation"])
    if swarm.clean({k: doc[k] for k in ("reason", "steps", "criteria")}) != {k: doc[k] for k in ("reason", "steps", "criteria")}:
        stop("observation_private", "관측에 개인 식별 형식이 있어 원문을 저장하지 않았습니다.")
    return doc


def _record(work, library, state, claim, request, raw, diagnostic):
    run = work / DIRECTORY / "run"
    receipt = swarm.receipt_starter(library, run, claim)
    receipt.pop("drafting_guidance")
    receipt["schema_version"] = "ux-persona-swarm-receipt.v1"
    observation = None
    if diagnostic["problem"] is None:
        try:
            observation = _observation(raw, request["binding"], claim["task"])
        except (EngineError, ValueError, KeyError, TypeError, AttributeError):
            diagnostic["problem"] = "invalid_or_private_observation"
    evidence = dict(schema_version="ux-journey-execution-log.v1", binding=request["binding"], diagnostic=diagnostic,
                    observation=observation, ui_observed=False, real_user_evidence=False)
    log = Path(claim["evidence_path"]) / "observation.json"
    log_raw = canonical(evidence)
    _immutable(run, str(log.relative_to(run)), log_raw)
    receipt["artifacts"] = [dict(id="execution", kind="execution_log", path=str(log.relative_to(run)), sha256=byte_digest(log_raw))]
    if observation:
        receipt["steps"] = [{**step, "evidence_ids": ["execution"]} for step in observation["steps"]]
        receipt["criteria"] = [{**row, "evidence_ids": [] if row["status"] == "not_run" else ["execution"]} for row in observation["criteria"]]
        receipt["outcome"] = "failed" if any(row["status"] == "failed" for row in observation["criteria"]) else "inconclusive"
        receipt["reason"] = observation["reason"] if receipt["outcome"] == "failed" else "Local core observations recorded; UI and real-user behavior remain unobserved."
    else:
        receipt["outcome"] = "inconclusive"
        receipt["reason"] = "Local execution could not supply valid observations: " + diagnostic["problem"] + ". No product verdict."
        for row in receipt["criteria"]:
            row["observation"] = "No valid observation; infrastructure uncertainty."
    swarm.record(library, run, receipt)


def _reconcile(state, current):
    """ACK recovery only: never convert dispatch intent into permission to spawn."""
    changed = False
    rows = {row["task_id"]: row for row in current["tasks"]}
    for task_id, dispatch in state["dispatches"].items():
        row = rows[task_id]
        if dispatch["phase"] == "intent" and row["result"] is not None:
            if row["attempts"] != dispatch["claim"]["attempt"] or row["operation_id"] != dispatch["claim"]["operation_id"]:
                stop("execution_attempt", "실행 시도 연결이 달라졌습니다.")
            dispatch["phase"] = "recorded"
            changed = True
    return changed


def _evidence_audit(work, state, tasks):
    """Read-only second-path audit of receipts and cross-persona obligation signals.

    This is deterministic consistency checking, not a human/LLM reviewer and not
    proof that an adapter's reported observation is true.
    """
    run = work / DIRECTORY / "run"
    specs = {task["id"]: task for task in state["plan"]["tasks"]}
    dispatches = state["dispatches"]
    rows = {row["task_id"]: row for row in tasks}
    issues, checked = [], 0
    observations = {}
    for task_id, row in rows.items():
        if not row.get("current_binding_valid", True):
            continue
        dispatch = dispatches.get(task_id)
        if row.get("result") is None:
            if row.get("attempts", 0) and dispatch is None:
                issues.append(dict(code="dispatch_missing", task_id=task_id))
            continue
        if not dispatch or dispatch.get("phase") not in {"intent", "recorded"}:
            issues.append(dict(code="dispatch_receipt_mismatch", task_id=task_id))
            continue
        claim = dispatch.get("claim")
        if not isinstance(claim, dict) or claim.get("task", {}).get("id") != task_id:
            issues.append(dict(code="dispatch_binding_invalid", task_id=task_id))
            continue
        if state["plan"]["schema_version"] == browser_run.PLAN:
            try:
                observations[task_id] = browser_run.audit(work, state, claim,
                    {**row["result"], "outcome": row["status"], "reason": row["reason"]})
                checked += 1
            except (EngineError, OSError, ValueError, KeyError, TypeError, AttributeError):
                issues.append(dict(code="execution_evidence_mismatch", task_id=task_id))
            continue
        artifacts = row["result"].get("artifacts")
        if (not isinstance(artifacts, list) or len(artifacts) != 1 or
                artifacts[0].get("id") != "execution" or artifacts[0].get("kind") != "execution_log"):
            issues.append(dict(code="execution_log_missing_or_duplicated", task_id=task_id))
            continue
        artifact = artifacts[0]
        try:
            raw = workspace.read_file(run, artifact["path"], sensitive_check=True)
            if len(raw) > 512 * 1024 or byte_digest(raw) != artifact["sha256"]:
                raise ValueError("digest_or_size")
            evidence = loads(raw)
            expected_binding = dict(task_id=task_id, attempt=claim["attempt"],
                operation_id=claim["operation_id"], build_sha256=claim["build"]["sha256"], **claim["binding"])
            if (not isinstance(evidence, dict) or
                    set(evidence) != {"schema_version", "binding", "diagnostic", "observation", "ui_observed", "real_user_evidence"} or
                    evidence["schema_version"] != "ux-journey-execution-log.v1" or
                    evidence["binding"] != expected_binding or evidence["ui_observed"] is not False or
                    evidence["real_user_evidence"] is not False):
                raise ValueError("binding_or_schema")
            diagnostic = evidence["diagnostic"]
            required_diagnostic = {"problem", "cleanup_confirmed", "returncode", "elapsed_seconds", "stdout_bytes",
                                   "stderr_bytes", "stdout_sha256", "stderr_sha256"}
            if (not isinstance(diagnostic, dict) or set(diagnostic) != required_diagnostic or
                    type(diagnostic["cleanup_confirmed"]) is not bool or
                    type(diagnostic["stdout_bytes"]) is not int or diagnostic["stdout_bytes"] < 0 or
                    type(diagnostic["stderr_bytes"]) is not int or diagnostic["stderr_bytes"] < 0):
                raise ValueError("diagnostic")
            observation = evidence["observation"]
            if diagnostic["problem"] is None:
                if diagnostic["cleanup_confirmed"] is not True or diagnostic["returncode"] != 0 or not isinstance(observation, dict):
                    raise ValueError("completion")
                parsed = _observation(canonical(observation), expected_binding, specs[task_id])
                expected_steps = [{**step, "evidence_ids": ["execution"]} for step in parsed["steps"]]
                expected_criteria = [{**criterion, "evidence_ids": [] if criterion["status"] == "not_run" else ["execution"]}
                                     for criterion in parsed["criteria"]]
                if row["result"]["steps"] != expected_steps or row["result"]["criteria"] != expected_criteria:
                    raise ValueError("receipt_observation_mismatch")
            else:
                if observation is not None or row["result"]["steps"] or any(
                        criterion["status"] != "not_run" or criterion["evidence_ids"]
                        for criterion in row["result"]["criteria"]):
                    raise ValueError("uncertain_result_mismatch")
            checked += 1
            observations[task_id] = observation
        except (EngineError, OSError, ValueError, KeyError, TypeError, AttributeError):
            issues.append(dict(code="execution_evidence_mismatch", task_id=task_id))

    buckets = {}
    incomplete = excluded = declared = 0
    for task_id, task in specs.items():
        row = rows.get(task_id, {})
        result = row.get("result")
        criteria = {(item["kind"], item["index"]): item for item in (result or {}).get("criteria", [])}
        steps = (result or {}).get("steps", [])
        step_fingerprint = [{"action": item["action"], "observation": item["observation"]} for item in steps]
        for requirement in task.get("requirement_coverage", []):
            for obligation in requirement.get("obligations", []):
                declared += 1
                key = (requirement["requirement_id"], obligation["id"])
                definition = dict(description=obligation["description"], criterion_refs=obligation["criterion_refs"],
                                  exclusion_reason=obligation["exclusion_reason"])
                bucket = buckets.setdefault(key, {"definitions": {}, "signals": []})
                bucket["definitions"][digest(definition)] = definition
                refs = obligation["criterion_refs"]
                if obligation["exclusion_reason"] is not None:
                    excluded += 1
                    continue
                if not refs or result is None or task_id not in observations or observations[task_id] is None:
                    incomplete += 1
                    continue
                evaluated = [criteria.get((ref["kind"], ref["index"])) for ref in refs]
                if any(item is None or item["status"] == "not_run" for item in evaluated):
                    incomplete += 1
                    continue
                status = "failed" if any(item["status"] == "failed" for item in evaluated) else "passed"
                signal = dict(task_id=task_id, persona_id=task["persona_id"], status=status,
                    criteria=[dict(kind=ref["kind"], index=ref["index"], status=item["status"],
                                   observation=item["observation"]) for ref, item in zip(refs, evaluated)],
                    observation_sha256=digest({"criteria": [{"kind": ref["kind"], "index": ref["index"],
                        "status": item["status"], "observation": " ".join(item["observation"].split())}
                        for ref, item in zip(refs, evaluated)], "steps": step_fingerprint}))
                bucket["signals"].append(signal)

    conflicts, duplicates, definition_conflicts = [], [], []
    distinct = 0
    for (requirement_id, obligation_id), bucket in sorted(buckets.items()):
        signals = bucket["signals"]
        distinct += len({signal["observation_sha256"] for signal in signals})
        if len(bucket["definitions"]) > 1:
            definition_conflicts.append(dict(requirement_id=requirement_id, obligation_id=obligation_id,
                definitions=[bucket["definitions"][key] for key in sorted(bucket["definitions"])],
                tasks=[signal["task_id"] for signal in signals]))
            # An ID collision is not evidence that the same obligation was tested.
            continue
        by_hash = {}
        for signal in signals:
            by_hash.setdefault(signal["observation_sha256"], []).append(signal)
        for fingerprint, repeated in sorted(by_hash.items()):
            if len(repeated) > 1:
                duplicates.append(dict(requirement_id=requirement_id, obligation_id=obligation_id,
                    observation_sha256=fingerprint, task_ids=[item["task_id"] for item in repeated],
                    persona_ids=sorted({item["persona_id"] for item in repeated}), distinct_observations=1))
        statuses = {signal["status"] for signal in signals}
        if statuses == {"passed", "failed"}:
            conflicts.append(dict(requirement_id=requirement_id, obligation_id=obligation_id,
                task_ids=[signal["task_id"] for signal in signals], statuses=sorted(statuses),
                signals=signals))

    return dict(basis="deterministic_receipt_and_cross_persona_audit",
        integrity="blocked" if issues else "consistent", issues=issues, receipts_checked=checked,
        independent_reviewer=False,
        obligations=dict(declared=declared, observed=sum(bool(bucket["signals"]) for bucket in buckets.values()),
            incomplete=incomplete, excluded=excluded, distinct_observations=distinct,
            duplicated=len(duplicates), conflicted=len(conflicts), definition_conflicts=len(definition_conflicts)),
        duplicates=duplicates, conflicts=conflicts, definition_conflicts=definition_conflicts,
        limitations=["Deterministic linkage and cross-persona consistency only; not a human or independent model reviewer.",
                     "Distinct observations are not independent participants or proof that adapter claims are true."])


def execute(work, *, library_path=None, input_path=None, approved=False, reviewed_research_runs=None, fault=None):
    work = safe_path(work)
    if not (work / "workspace.json").is_file():
        stop("workspace_missing", "대상 코드를 먼저 안전하게 준비해야 합니다.")
    if work.stat().st_mode & 0o022:
        stop("workspace_permissions", "다른 사용자가 쓸 수 있는 작업공간에서는 실행하지 않습니다.")
    with Store(work):
        prepared = workspace._state(work)
        if prepared["phase"] != "ready":
            stop("preparation_interrupted", "입력 준비가 끝나지 않았습니다. 같은 start로 먼저 준비를 이어갑니다.")
        _copy_scope(work, prepared)
        workspace._verify(work, prepared)
        state = (_read(work) if (work / MARKER).exists() else
                 _initialize(work, prepared, library_path, input_path, approved, reviewed_research_runs))
        if input_path is not None and _plan(input_path, prepared) != state["plan"]:
            stop("execution_contract", "실행을 고정한 뒤 목표·기준·어댑터를 바꿀 수 없습니다.")
        if library_path is not None and str(safe_path(library_path)) != state["library"]:
            stop("execution_contract", "기존 실행과 다른 페르소나 저장소입니다.")
        if reviewed_research_runs is not None and roots_for(reviewed_research_runs, work=work, source=prepared["source"], library=state["library"]) != state.get("research_runs", []):
            stop("execution_contract", "고정한 연구 범위를 바꿔 기존 실행을 이어갈 수 없습니다.")
        _verify(work, prepared, state)
        if state["phase"] == "preparing":
            _finish_preparation(work, state)
        with Library(work / DIRECTORY / "personas", reference_guard=ReferenceScope(prepared, state.get("research_runs", []))) as library:
            run = work / DIRECTORY / "run"
            current = swarm.report(library, run)
            if _reconcile(state, current):
                _save(work, state)
            # Includes a crash between claim and journal: attempts are never reset.
            if any(row["attempts"] and row["result"] is None for row in current["tasks"]):
                return report_locked(work, prepared, state, current)
            for task in state["plan"]["tasks"]:
                if next(row for row in current["tasks"] if row["task_id"] == task["id"])["status"] != "pending":
                    continue
                _verify(work, prepared, state)
                if state["plan"]["schema_version"] == browser_run.PLAN:
                    browser_run.verify_runtime(state["browser"]["runtime"])
                claim = swarm.claim(library, run, "reviewed-local-runner", task["id"])
                if not claim["claimed"]:
                    break
                dispatch = dict(phase="intent", spawned=False, claim=claim)
                state["dispatches"][task["id"]] = dispatch
                _save(work, state)
                if fault:
                    fault("intent")
                cwd = safe_path(Path(claim["evidence_path"]) / "scratch", run)
                cwd.mkdir(mode=0o700)
                binding = dict(task_id=task["id"], attempt=claim["attempt"], operation_id=claim["operation_id"],
                               build_sha256=claim["build"]["sha256"], **claim["binding"])
                request = dict(schema_version="ux-journey-request.v1", binding=binding, task=claim["task"],
                               profile=claim["profile"], requirement_context=claim["requirement_context"], source=str(work / "product"))
                def spawned():
                    dispatch["spawned"] = True
                    _save(work, state)
                _verify(work, prepared, state)
                is_browser = state["plan"]["schema_version"] == browser_run.PLAN
                if is_browser:
                    request = browser_run.request_for(work, state["browser"], task["id"], binding,
                        cwd / "browser", state["plan"]["timeout_seconds"])
                    raw, diagnostic = browser_run.invoke(state["browser"], cwd, request, state["plan"]["timeout_seconds"], spawned)
                else:
                    raw, diagnostic = _invoke(work / "product" / state["plan"]["runner"], cwd, request, state["plan"]["timeout_seconds"], spawned)
                if not diagnostic["cleanup_confirmed"]:
                    dispatch["diagnostic"] = diagnostic
                    _save(work, state)
                    stop("execution_cleanup", "소유 실행 프로세스의 종료를 확인하지 못했습니다. 결과를 확정하거나 다음 과제를 시작하지 않았습니다.")
                _verify(work, prepared, state)
                if is_browser:
                    browser_run.verify_runtime(state["browser"]["runtime"])
                    browser_run.record(work, library, state, claim, raw, diagnostic)
                else:
                    _record(work, library, state, claim, request, raw, diagnostic)
                if fault:
                    fault("recorded")
                dispatch.update(phase="recorded", diagnostic=diagnostic)
                _save(work, state)
                current = swarm.report(library, run)
                if diagnostic["problem"]:
                    break
            return report_locked(work, prepared, state, current)


def report_locked(work, prepared, state=None, current=None):
    state = state or _read(work)
    _verify(work, prepared, state)
    if current is None and state["phase"] == "ready":
        with Library(work / DIRECTORY / "personas", reference_guard=ReferenceScope(prepared, state.get("research_runs", []))) as library:
            current = swarm.report(library, work / DIRECTORY / "run")
    tasks = []
    for task in state["plan"]["tasks"]:
        row = next((row for row in (current or {}).get("tasks", []) if row["task_id"] == task["id"]), None)
        tasks.append(dict(goal=task["goal"], starting_state=task["starting_state"], actions=task["actions"],
            success_criteria=task["success_criteria"], recovery_criteria=task["recovery_criteria"],
            **(row or dict(task_id=task["id"], persona_id=task["persona_id"], status="pending", attempts=0, result=None, reason="Preparation interrupted."))))
    uncertain = [row["task_id"] for row in tasks if row["attempts"] and row["result"] is None]
    quarantined = [row["task_id"] for row in tasks if row.get("resource_quarantined")]
    personas = [{k: record[k] for k in ("persona_id", "revision", "profile_sha256", "basis")} |
                {"label": record["profile"]["label"], "provenance_mode": record["provenance"]["mode"], "prd_sha256": record["context"]["prd_sha256"]}
                for _, history in sorted(state["personas"]["state"]["entries"].items()) for record in history]
    for row in personas:
        record = state["personas"]["state"]["entries"][Library._key(state["plan"]["product_id"], row["persona_id"])][-1]
        if row["provenance_mode"] == "gated_research":
            binding = record["provenance"]["research"]
            row["research"] = {key: copy.deepcopy(binding[key]) for key in
                               ("source_bundle_id", "bundle_input_sha256", "process_input_sha256", "valid_until", "claims")}
            if "research_export" in record["provenance"]:
                origin = record["provenance"]["research_export"]
                row["research"]["export"] = {key: copy.deepcopy(origin[key]) for key in
                    ("source_persona_id", "scenario_ids", "packet_sha256", "projection_sha256")}
    counts = current["counts"] if current else {k: len(tasks) if k == "pending" else 0 for k in ("pending", "running", "passed", "failed", "blocked", "inconclusive", "skipped")}
    evidence_audit = _evidence_audit(work, state, tasks)
    audit_needs_review = (evidence_audit["integrity"] != "consistent" or
        evidence_audit["obligations"]["conflicted"] > 0 or
        evidence_audit["obligations"]["definition_conflicts"] > 0)
    is_browser = state["plan"]["schema_version"] == browser_run.PLAN
    ui_observed = bool(is_browser and evidence_audit["integrity"] == "consistent" and any(
        row.get("result") and any(a["kind"] == "screenshot" for a in row["result"]["artifacts"]) for row in tasks))
    summary = dict(schema_version="ux-journey-run-report.v1", preparation_complete=True,
        execution_performed=True if any(row["spawned"] for row in state["dispatches"].values()) else (None if uncertain else False),
        execution_complete=not uncertain and counts["pending"] == 0 and counts["running"] == 0,
        uncertain_dispatches=uncertain, quarantined_tasks=quarantined, counts=counts, tasks=tasks, personas_reused=personas,
        source_files=prepared["source_files"], plan_sha256=digest(state["plan"]), workspace_sha256=state["workspace_sha256"],
        evidence_kind="owned_static_browser_observations" if is_browser else "owned_local_core_observations",
        ui_observed=ui_observed, real_user_evidence=False, product_ready=False,
        coverage=current["coverage_summary"] if current else None,
        evidence_audit=evidence_audit,
        next_action=("중단된 실행의 실제 프로세스·근거·영향을 호스트가 먼저 확인해야 합니다. 자동 재실행하지 않습니다." if uncertain else
                     "쓰기 결과가 불확실한 자원이 격리되어 있습니다. 호스트가 실제 상태를 검사하고 기존 settle 규칙을 적용하기 전에는 같은 자원을 재사용하지 않습니다." if quarantined else
                     "저장된 실행 로그와 receipt가 일치하지 않습니다. 원본을 보존하고 각 과제의 현재 시도·근거를 호스트가 다시 검토해야 합니다. 자동 재실행하지 않습니다." if evidence_audit["integrity"] != "consistent" else
                     "같은 PRD 의무에 대한 페르소나 관측이 상충하거나 의무 ID 정의가 다릅니다. 원본 관측을 나란히 검토하고 해결 전에는 종합 판정을 보류합니다." if audit_needs_review else
                     "중복 관측은 독립된 추가 신호로 세지 않았습니다. 서로 다른 과업·기준의 추가 검증이 필요하면 새 범위를 검토합니다." if evidence_audit["obligations"]["duplicated"] else
                     "남은 과제가 있습니다. 실행 장애를 확인한 뒤 같은 run으로 아직 시작하지 않은 과제만 이어갑니다." if counts["pending"] else
                     "관측된 실패를 재현하고 수정 후보를 별도 검토합니다. 실제 UI·사용자 검증이 남아 있습니다."),
        limitations=["재사용한 페르소나는 PRD 또는 검토된 연구를 바탕으로 한 합성 가설이며 실제 참가자가 아닙니다.",
                     "연구 연결은 로컬 저장본의 현재 게이트·철회·보존 상태를 검사합니다. 출처 진위·원격 변경·사용자 수요나 효과를 독립적으로 입증하지 않습니다.",
                     "관측은 명시적으로 검토한 로컬 어댑터의 코어 실행 범위입니다. UI·서비스 수용·실사용자 효과를 검증하지 않았습니다.",
                     "어댑터 실행은 OS·네트워크 샌드박스가 아닙니다. 호스트의 코드·소유 입력 검토가 필수입니다.",
                     "검토한 단일 Python 프로세스만 지원합니다. 별도 자식·백그라운드 작업을 실행하는 어댑터는 지원하지 않습니다.",
                     "해시와 receipt는 연결·무결성을 검사하며 어댑터 관측의 진실성이나 PRD 해석의 완전성을 증명하지 않습니다.",
                     "실패 없는 코어 관측도 최종 통과가 아닙니다. 미실행 기준과 근거 부족을 그대로 표시합니다."])
    if is_browser:
        summary["limitations"] = [
            "검토한 정적 복사본을 소유 headless Chromium에서 실행한 자동화 관측입니다. 실제 사용자·실제 기기·실서비스 효과는 검증하지 않았습니다.",
            "페르소나는 PRD 또는 저장된 연구에 연결된 합성 가설입니다. 현재 연구·버전·기한 검사는 출처 진위나 대표성을 보장하지 않습니다.",
            "고정한 행동과 측정 기준만 실행하며 사람처럼 스스로 판단하거나 누락된 PRD 의미를 검증하지 않습니다.",
            "정적 파일 요청을 검토한 바이트로만 응답하고 외부 요청을 차단합니다. 코드 검토가 필수이며 OS 네트워크 샌드박스는 아닙니다.",
            "정상 종료는 소유 브라우저 close 응답과 Node 종료로 확인합니다. 강제 종료·응답 유실은 불확실하며 자동 재실행하지 않습니다.",
            "일부 과업 통과는 제품 준비 완료나 스웜의 실제 사용자 효과가 아닙니다. 미실행·중복·상충 관측은 보존합니다."]
        if not uncertain and not quarantined and not audit_needs_review and not counts["pending"]:
            summary["next_action"] = "측정한 실패와 미관측 조건을 검토합니다. 실제 제품·사용자 효과 검증은 별도 범위로 남아 있습니다."
    summary["task_scope_passed"] = bool(is_browser and not audit_needs_review and not uncertain and not quarantined
        and counts["passed"] == len(tasks) and current and current["coverage_summary"]["all_declared_requirements_passed"])
    legacy = render(summary, _legacy_duplicate_wording=True) if evidence_audit["duplicates"] else None
    return workspace.publish_report(work, summary, render(summary), legacy_markdown=legacy)


def render(summary, *, _legacy_duplicate_wording=False):
    def text(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
    labels = dict(failed="실패", inconclusive="판정 보류", pending="대기", running="실행 확인 필요", blocked="차단", skipped="미실행", passed="통과")
    c = summary["counts"]
    lines = ["# 사용자 목표별 로컬 QA 결과", "", f"실패 {c['failed']} · 판정 보류 {c['inconclusive']} · 대기 {c['pending']} · 통과 {c['passed']}.",
             ("검토한 정적 복사본의 실제 headless 브라우저 관측입니다. 실제 사용자 효과·제품 준비 완료는 미검증입니다."
              if summary["evidence_kind"] == "owned_static_browser_observations" else
              "실제 UI와 사용자 효과는 미검증입니다. 코어 실행 완료와 제품 통과를 구분합니다."), ""]
    audit = summary["evidence_audit"]
    counts = audit["obligations"]
    lines += ["## 다중 페르소나 증거 일관성 검사", "",
        f"무결성: {audit['integrity']} · receipt 재검사 {audit['receipts_checked']}건 · 의무 중복 {counts['duplicated']}건 · 상충 {counts['conflicted']}건 · 미관측/미실행 {counts['incomplete']}건.",
        "이 검사는 저장된 실행 로그와 receipt를 결정적으로 대조합니다. 독립적인 사람/모델 평가가 아니며, 서로 다른 관측도 독립 참가자나 사실성의 증거가 아닙니다."]
    for issue in audit["issues"]:
        lines.append(f"- 근거 무결성 차단: {issue['task_id']} · {issue['code']}")
    duplicate_wording = "독립 신호 1건으로만 계산" if _legacy_duplicate_wording else "같은 관측 1건으로 계산"
    for duplicate in audit["duplicates"]:
        lines.append(f"- 중복 관측: {duplicate['requirement_id']}/{duplicate['obligation_id']} · 과제 {', '.join(duplicate['task_ids'])} · {duplicate_wording}")
    for conflict in audit["conflicts"]:
        lines.append(f"- 상충 관측: {conflict['requirement_id']}/{conflict['obligation_id']} · 과제 {', '.join(conflict['task_ids'])} · {', '.join(conflict['statuses'])}")
    for conflict in audit["definition_conflicts"]:
        lines.append(f"- 의무 정의 충돌: {conflict['requirement_id']}/{conflict['obligation_id']} · 과제 {', '.join(conflict['tasks'])}")
    if audit["integrity"] != "consistent":
        lines.append("- 무결성 차단: 아래 과제의 관측 로그와 receipt를 일치시킬 수 없습니다. 기존 원본을 수정하거나 다시 실행하지 마세요.")
    lines += ["", "## 재사용한 페르소나", ""]
    for persona in summary["personas_reused"]:
        basis = "연구 근거를 연결한 합성 가설" if persona["provenance_mode"] == "gated_research" else "PRD 합성 가설"
        lines.append(f"- {text(persona['label'])} — {persona['persona_id']} v{persona['revision']}, {basis}, profile `{persona['profile_sha256']}`")
        if "research" in persona:
            research = persona["research"]
            lines.append(f"  - 연구 bundle `{text(research['source_bundle_id'])}`, gate input `{research['bundle_input_sha256']}`, 유효 기한: {text(research['valid_until'] or '기록된 기한 없음; 현재 상태는 매번 재검증')}")
            for claim in research["claims"]:
                lines.append(f"  - 주장 `{text(claim['claim_id'])}` · 상태 {text(claim['gate_status'])} · 출처 {text(', '.join(claim['source_ids']))} · 지지 근거 {text(', '.join(claim['counting_evidence_ids']) or '없음')} · 맥락 근거 {text(', '.join(claim['context_evidence_ids']) or '없음')}")
    for task in summary["tasks"]:
        lines += ["", "## " + text(task["goal"]), "", f"결과: {labels[task['status']]} · 시도 {task['attempts']} · {task['task_id']} / {task['persona_id']}",
                  "시작 상태: " + text(task["starting_state"]), "판정 근거: " + text(task["reason"])]
        result = task["result"]
        observed = {(row["kind"], row["index"]): row for row in result["criteria"]} if result else {}
        lines += ["", "| 고정한 기준 | 관측 상태 | 관측 / 미실행 사유 |", "| --- | --- | --- |"]
        for kind in ("success", "recovery"):
            for index, criterion in enumerate(task[kind + "_criteria"]):
                row = observed.get((kind, index), dict(status="not_run", observation="관측 없음"))
                lines.append(f"| {text(criterion)} | {row['status']} | {text(row['observation'])} |")
        if result:
            lines += ["", "재현 단계 및 근거:", ""]
            lines += ["- " + text(step["action"]) + ": " + text(step["observation"]) for step in result["steps"]]
            lines += [f"- [실행 근거](../{DIRECTORY}/run/{artifact['path']}) · SHA-256 `{artifact['sha256']}`" for artifact in result["artifacts"]]
    lines += ["", "## 다음 단계", "", summary["next_action"], "", "## 검증 경계", ""]
    lines += ["- " + row for row in summary["limitations"]]
    return "\n".join(lines) + "\n"
