"""Reviewed source intake and honest prior-evidence review; never execute products.

Reuse Library, swarm, Store and canonical envelopes. Hosts explicitly select
minimal reviewed files or a reviewed source adapter; unknown products always
require host review. No dependency installation or recursive source walk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

from uxresearch.canonical import EngineError, byte_digest, canonical, digest
from uxresearch.storage import Store, atomic, safe_path
from .library import Library
from . import swarm

SCHEMA = "ux-journey-workspace.v1"
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
SECRET = re.compile(rb"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|sk-proj-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}")
FORBIDDEN = {".git", ".ssh", ".aws", ".env", "node_modules", "credentials.json", "secrets.json"}


def stop(code, reason, next_step):
    error = EngineError(code, reason)
    error.issue["next_step"] = next_step
    raise error


def relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        stop("source_path", "복사할 파일 경로가 안전하지 않습니다.", "호스트가 검토한 파일 범위를 다시 확인합니다.")
    parts = value.split("/")
    if value.startswith("/") or any(p in {"", ".", ".."} for p in parts):
        stop("source_path", "폴더 밖을 가리키는 파일은 읽지 않습니다.", "대상 폴더 안의 일반 파일만 선택합니다.")
    if any(p.startswith(".") or p in FORBIDDEN for p in parts) or Path(value).suffix.lower() in {".key", ".pem", ".p12", ".pfx"}:
        stop("sensitive_path", "키·설정·의존성 파일은 복사 범위에 포함할 수 없습니다.", "호스트가 필요한 공개 코드와 합성 자료만 선택합니다.")
    return parts


def read_file(root, name, *, sensitive_check=False):
    """Open every path component relative to a pinned descriptor, no link following."""
    parts = relative(name)
    root = safe_path(root)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:] + tuple(parts[:-1]):
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        handle = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
                stop("unsafe_source", "일반 파일이 아니거나 파일 크기·링크 조건이 맞지 않습니다.", "원본을 바꾸지 말고 호스트에게 필요한 파일 범위를 확인하도록 요청합니다.")
            chunks, size = [], 0
            while chunk := os.read(handle, 1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE:
                    stop("source_size", "파일 크기가 준비 한도를 넘었습니다.", "더 작은 검토 범위를 사용합니다.")
                chunks.append(chunk)
            after = os.fstat(handle)
            if (info.st_size, info.st_mtime_ns, info.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                stop("source_changed", "읽는 중 입력 파일이 바뀌었습니다.", "변경이 끝난 뒤 같은 준비 명령을 다시 실행합니다.")
            raw = b"".join(chunks)
            if sensitive_check and SECRET.search(raw):
                stop("sensitive_content", "선택한 파일에 키 형식의 내용이 있어 준비를 멈췄습니다.", "호스트가 비밀이 없는 최소 입력을 검토해야 합니다. 원본은 자동 수정하지 않습니다.")
            return raw
        finally:
            os.close(handle)
    except FileNotFoundError:
        raise
    except OSError as exc:
        stop("source_unreadable", "입력 파일을 안전하게 읽을 수 없습니다.", "경로·권한·외부 링크 여부를 확인합니다. 권한을 자동 확대하지 않습니다.")
    finally:
        os.close(fd)


def reviewed_recipe(source, files):
    """Freeze a host-reviewed exact selection; no manual hashes or recursive scan."""
    if not files or len(files) > 128 or len(set(files)) != len(files):
        stop("reviewed_selection", "검토한 파일은 중복 없이 1~128개를 지정해야 합니다.", "호스트가 실제로 검토한 최소 상대 경로만 선택합니다.")
    hashes, total = {}, 0
    for name in files:
        raw = read_file(source, name, sensitive_check=True)
        total += len(raw)
        if total > MAX_TOTAL:
            stop("source_size", "검토한 입력의 합계가 준비 한도를 넘었습니다.", "호스트가 필요한 파일 범위를 줄입니다.")
        hashes[name] = byte_digest(raw)
    return dict(id="host-reviewed-source", kind="reviewed-files", product_id="reviewed-source",
                files=hashes, source_manifest_sha256=digest(hashes))


def _json(raw):
    return json.loads(raw.decode("utf-8"))


def _saved_inputs(source, binding_raw):
    """Only exact state files and receipt-referenced artifacts, never claims/log trees."""
    lib_raw = read_file(source, "persona-library/library.json", sensitive_check=True)
    run_raw = read_file(source, "persona-run/swarm-state.json", sensitive_check=True)
    lib, run = _json(lib_raw), _json(run_raw)
    if digest(lib.get("state")) != lib.get("sha256") or digest(run.get("payload")) != run.get("sha256"):
        stop("saved_integrity", "저장된 페르소나 또는 결과의 무결성이 맞지 않습니다.", "이전 결과를 보존하고 원래 근거를 확인합니다.")
    state = run["payload"]
    if any(e["status"] in {"running", "pending"} for e in state["tasks"]):
        stop("run_active", "아직 진행 중이거나 미실행인 과제가 있습니다.", "기존 실행을 먼저 확인합니다. 새 실행으로 시도 한도를 초기화하지 않습니다.")
    expected_prd = str(source / "product/docs/PRD.md")
    for history in lib["state"]["entries"].values():
        for record in history:
            if record["provenance"]["mode"] != "prd_hypothesis" or record["context"]["prd_path"] != expected_prd or record["product_id"] != state["product_id"]:
                stop("saved_scope", "이 준비 경로에서 검토하지 않은 출처 연결이 있습니다.", "호스트가 원래 연구·PRD 재사용 경로에서 범위를 확인해야 합니다.")
    if state["build"]["artifact_path"] != str(source / "product-binding.json") or state["build"]["sha256"] != byte_digest(binding_raw):
        stop("saved_scope", "기존 결과의 빌드 연결이 선택한 입력과 다릅니다.", "동일한 빌드와 근거가 있는 승인된 입력을 사용합니다.")
    inputs = {"persona-library/library.json": lib_raw, "persona-run/swarm-state.json": run_raw}
    for entry in state["tasks"]:
        for attempt in entry["history"] + [entry]:
            for artifact in attempt.get("receipt", {}).get("artifacts", []):
                rel = artifact["path"]
                expected = f"evidence/{entry['task']['id']}/{attempt['attempts']}/"
                if not rel.startswith(expected) or artifact["kind"] not in {"execution_log", "screenshot"}:
                    stop("evidence_scope", "근거 파일이 원래 과제·시도 범위를 벗어납니다.", "기존 결과의 근거 연결을 확인합니다.")
                raw = read_file(source, "persona-run/" + rel, sensitive_check=True)
                if byte_digest(raw) != artifact["sha256"]:
                    stop("evidence_changed", "기존 실행 근거의 내용이 바뀌었습니다.", "원래 근거를 보존하고 변경 원인을 확인합니다.")
                inputs["persona-run/" + rel] = raw
    return inputs


def inspect(source, selected):
    source = safe_path(source)
    binding_raw = None
    if selected.get("kind") != "reviewed-files":
        try:
            binding_raw = read_file(source, "product-binding.json", sensitive_check=True)
        except FileNotFoundError:
            pass
    prefix = "product/" if binding_raw is not None else ""
    if binding_raw is not None:
        binding = _json(binding_raw)
        if set(binding) - {"schema_version", "base_head", "dirty_working_copy", "source_manifest_sha256",
                           "files", "source_is_read_only", "synthetic_fixtures_only"}:
            stop("binding_scope", "입력 연결 기록에 검토하지 않은 추가 내용이 있습니다.", "호스트가 필요한 빌드 연결만 확인해야 합니다. 추가 자료는 자동 복사하지 않습니다.")
        if binding.get("files") != selected["files"] or binding.get("source_manifest_sha256") != selected["source_manifest_sha256"]:
            stop("source_not_reviewed", "현재 입력은 검토해 고정한 복사본과 다릅니다.", "원본을 수정하지 말고 승인된 고정 복사본을 선택합니다.")
    inputs, destinations = {}, {}
    for rel, expected in selected["files"].items():
        raw = read_file(source, prefix + rel, sensitive_check=True)
        if byte_digest(raw) != expected:
            stop("source_changed", "검토한 코드와 입력 파일이 일치하지 않습니다.", "바뀐 제품은 새 범위 검토가 필요합니다. 이전 결과를 새 결과로 사용하지 않습니다.")
        inputs[prefix + rel] = raw
        destinations[prefix + rel] = "product/" + rel
    saved = False
    if binding_raw is not None:
        inputs["product-binding.json"] = binding_raw
        destinations["product-binding.json"] = "product-binding.json"
        # Either both saved components exist or neither exists. Missing half is not ignored.
        have_lib = (source / "persona-library").exists()
        have_run = (source / "persona-run").exists()
        if have_lib != have_run:
            stop("saved_incomplete", "기존 페르소나와 결과 중 일부가 없습니다.", "원래 실험 폴더를 선택하거나 호스트가 누락된 근거를 확인해야 합니다.")
        if have_lib:
            previous = _saved_inputs(source, binding_raw)
            for rel, raw in previous.items():
                inputs[rel] = raw
                destinations[rel] = "prior/" + rel
            saved = True
    if len(inputs) > 1024 or sum(map(len, inputs.values())) > MAX_TOTAL:
        stop("source_size", "준비할 파일이 고정한 한도를 넘었습니다.", "호스트가 필요한 코드와 근거만 좁혀야 합니다.")
    return inputs, destinations, saved


def _state(work):
    envelope = _json(read_file(work, "workspace.json"))
    state = envelope.get("payload")
    if envelope.get("schema_version") != SCHEMA or digest(state) != envelope.get("sha256"):
        stop("workspace_integrity", "작업공간 기록이 손상됐습니다.", "기존 파일을 보존하고 호스트가 상태를 확인해야 합니다.")
    return state


def _save(work, state):
    atomic(work / "workspace.json", canonical(dict(schema_version=SCHEMA, payload=state, sha256=digest(state))))


def _verify(work, state):
    source = safe_path(state["source"])
    for rel, expected in state["inputs"].items():
        if byte_digest(read_file(source, rel)) != expected:
            stop("source_changed", "준비 이후 원래 입력이 바뀌었습니다.", "기존 결과를 보존하고 새 입력을 별도로 검토합니다.")
        target = state["destinations"][rel]
        if byte_digest(read_file(work, target)) != expected:
            stop("workspace_changed", "복사본 또는 근거 파일이 바뀌었습니다.", "기존 근거를 덮어쓰지 말고 호스트가 변경을 확인해야 합니다.")


def _report(work, state):
    _verify(work, state)
    if (work / "local-execution.json").exists():
        from .local_run import report_locked
        return report_locked(work, state)
    personas, prior, goals, findings = [], None, {}, []
    if state["saved"]:
        saved_state = _json(read_file(work, "prior/persona-run/swarm-state.json"))["payload"]
        goals = {e["task"]["id"]: swarm.clean(e["task"]["goal"]) for e in saved_state["tasks"]}
        with Library(work / "prior/persona-library") as library:
            prior = swarm.report(library, work / "prior/persona-run")
            seen = set()
            for task in prior["tasks"]:
                pair = (task["persona_id"], task["binding"]["revision"])
                if pair not in seen:
                    record = library.get(prior["product_id"], *pair)
                    personas.append(dict(persona_id=pair[0], revision=pair[1],
                                         profile_sha256=record["profile_sha256"]))
                    seen.add(pair)
        for task in prior["tasks"]:
            if task["status"] == "failed" and task["result"]:
                findings.append(dict(goal=goals[task["task_id"]], task_id=task["task_id"],
                    failed_criteria=[row for row in task["result"]["criteria"] if row["status"] == "failed"],
                    evidence=task["result"]["artifacts"]))
    _verify(work, state)
    summary = dict(schema_version="ux-journey-entry-report.v1", preparation_complete=True,
                   source_files=state["source_files"], copied_files=len(state["inputs"]),
                   execution_performed=False, ui_observed=False, real_user_evidence=False,
                   product_ready=False, personas_reused=personas,
                   evidence_kind="revalidated_prior_synthetic_core" if prior else "source_preparation_only",
                   prior_counts=prior["counts"] if prior else None,
                   prior_tasks=[{**{k: t[k] for k in ("task_id", "persona_id", "status", "attempts", "reason",
                                                  "prior_outcomes", "requirement_results")},
                                 "goal": goals[t["task_id"]]} for t in prior["tasks"]] if prior else [],
                   findings=findings,
                   prior_coverage=prior["coverage_summary"] if prior else None,
                   next_action=("기존 실패와 미검증 범위를 검토합니다. 이 명령은 과제를 다시 실행하거나 대상 제품을 수정하지 않습니다."
                                if prior else "호스트가 이 복사본의 목표·실행 가능 경로를 검토하고 페르소나와 과제를 준비합니다."),
                   limitations=[("기존 코어 관측을 다시 검증한 결과이며 새로운 제품 실행이 아닙니다." if prior else "코드 준비만 완료했으며 제품 동작이나 과제 결과를 관측하지 않았습니다."),
                                "UI·실제 사용자 효과·제품 전체 준비 완료를 증명하지 않습니다.",
                                "의존성을 복사하거나 실행하지 않았으며 실제 계정과 외부 서비스에 접속하지 않았습니다."])
    return publish_report(work, summary, render(summary))


def publish_report(work, summary, text, *, legacy_markdown=None):
    """Publish immutable paired MD/JSON; shared by entry and current execution."""
    reports = safe_path(work / "reports", work)
    reports.mkdir(mode=0o700, exist_ok=True)
    stem = digest(summary)[:16]
    verified_json = False
    missing = []
    for suffix, raw in ((".json", canonical(summary)), (".md", text.encode("utf-8"))):
        dest = reports / (stem + suffix)
        if not dest.exists():
            missing.append((dest, raw))
            continue
        stored = read_file(work, str(dest.relative_to(work)))
        if stored != raw:
            # Only an existing, verified JSON companion can authorize an exact older rendering.
            if suffix == ".md" and verified_json and legacy_markdown is not None and stored == legacy_markdown.encode("utf-8"):
                continue
            stop("report_changed", "이전 보고서 내용이 바뀌었습니다.", "기존 보고서를 보존하고 변경을 확인합니다.")
        if suffix == ".json":
            verified_json = True
    # Do not create a missing companion until every existing artifact has been checked.
    for dest, raw in missing:
        atomic(dest, raw)
    return {**summary, "report_path": str(reports / (stem + ".md"))}


def render(summary):
    if summary.get("schema_version") == "ux-journey-run-report.v1":
        from .local_run import render as render_run
        return render_run(summary)
    lines = ["# 준비와 기존 결과 확인", "",
             f"검토한 코드 {summary['source_files']}개를 독립 작업공간에서 확인했습니다.",
             "새 제품 과제는 실행하지 않았습니다.\n"]
    if summary["prior_counts"] is not None:
        c = summary["prior_counts"]
        lines += [f"기존 페르소나 {len(summary['personas_reused'])}개의 정확한 버전을 재검증해 재사용했습니다.",
                  f"이전 결과: 실패 {c['failed']} · 판정 보류 {c['inconclusive']} · 통과 {c['passed']}.",
                  "이 숫자는 이전 실험 결과입니다. 재실행 통과나 실사용자 효과가 아닙니다.\n",
                  "| 사용자 목표 | 기록된 결과 | 시도 수 |",
                  "| --- | --- | --- |"]
        labels = {"failed": "실패", "inconclusive": "판정 보류", "passed": "통과",
                  "blocked": "차단", "skipped": "미실행", "pending": "대기", "running": "진행 중"}
        for task in summary["prior_tasks"]:
            goal = task["goal"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {goal} | {labels[task['status']]} | {task['attempts']} |")
    else:
        lines.append("재사용할 기존 페르소나·실험 결과는 연결되지 않았습니다. 아직 QA 결과는 없습니다.")
    lines += ["", "## 다음 단계", "", summary["next_action"], "", "## 확인 범위", ""]
    lines += ["- " + note for note in summary["limitations"]]
    return "\n".join(lines) + "\n"


def prepare(source, work, *, selected=None, reviewed_files=None, progress=None, fault=None):
    """Idempotent preparation; lock held through publication. No original writes."""
    source, work = safe_path(source), safe_path(work)
    if source == work or source.is_relative_to(work) or work.is_relative_to(source):
        stop("workspace_overlap", "입력 폴더와 작업공간은 서로 분리되어야 합니다.", "입력 폴더 밖의 새 작업공간을 사용합니다.")
    if work.exists() and (not work.is_dir() or (any(work.iterdir()) and not (work / "workspace.json").is_file())):
        stop("workspace_occupied", "이 폴더에 기존 파일이 있어 덮어쓰지 않았습니다.", "비어 있는 다른 폴더를 선택합니다. 기존 실험은 그대로 둡니다.")
    if work.exists() and work.stat().st_mode & 0o022:
        stop("workspace_permissions", "다른 사용자가 쓸 수 있는 폴더에는 준비하지 않습니다.", "쓰기 권한이 제한된 별도 작업공간을 선택합니다. 기존 폴더 권한은 자동 변경하지 않습니다.")
    if selected is not None and reviewed_files is not None:
        stop("reviewed_selection", "소스 어댑터와 별도 파일 선택을 함께 사용할 수 없습니다.", "호스트가 한 가지 검토 경로를 선택합니다.")
    if selected is None and reviewed_files is None:
        stop("reviewed_selection", "호스트가 검토한 파일 범위 또는 소스 어댑터를 지정해야 합니다.", "reviewed_files 또는 검토된 selected 어댑터를 명시적으로 전달합니다.")
    selected = selected or reviewed_recipe(source, reviewed_files)
    inputs, destinations, saved = inspect(source, selected)
    if progress:
        progress(f"검토한 코드 {len(selected['files'])}개와 연결된 근거만 준비합니다. 의존성·키·계정 자료는 복사하지 않습니다.")
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    with Store(work):
        identity = dict(source=str(source), recipe=digest(selected),
                        inputs={k: byte_digest(v) for k, v in inputs.items()},
                        destinations=destinations, saved=saved, source_files=len(selected["files"]))
        if (work / "workspace.json").exists():
            state = _state(work)
            if any(state.get(k) != v for k, v in identity.items()):
                stop("workspace_conflict", "이 작업공간은 다른 입력 또는 이전 상태에 연결돼 있습니다.", "기존 내용을 보존하고 새로운 입력에는 별도 작업공간을 사용합니다.")
        else:
            # The lock is the only entry permitted before publishing ownership.
            if set(p.name for p in work.iterdir()) != {"engine.lock"}:
                stop("workspace_occupied", "준비 중 다른 파일이 생겼습니다.", "다른 작업과 겹치지 않는 새 작업공간을 사용합니다.")
            state = {**identity, "phase": "copying"}
            _save(work, state)
        for rel, raw in inputs.items():
            dest = safe_path(work / destinations[rel], work)
            dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if dest.exists():
                if read_file(work, destinations[rel]) != raw:
                    stop("workspace_changed", "이미 복사된 파일이 달라 덮어쓰지 않았습니다.", "기존 내용을 보존하고 호스트가 변경을 확인해야 합니다.")
            else:
                atomic(dest, raw)
            if fault:
                fault(rel)
        summary = _report(work, state)
        if state["phase"] != "ready":
            state["phase"] = "ready"
            _save(work, state)
        return summary


def status(work):
    work = safe_path(work)
    if not (work / "workspace.json").is_file():
        stop("workspace_missing", "아직 준비한 작업공간이 없습니다.", "대상 폴더를 지정해 start를 실행하면 복사와 검증을 함께 진행합니다.")
    if work.stat().st_mode & 0o022:
        stop("workspace_permissions", "다른 사용자가 쓸 수 있는 작업공간은 재사용하지 않습니다.", "호스트가 작업공간 권한과 변경 여부를 확인해야 합니다. 권한을 자동 변경하지 않습니다.")
    with Store(work):
        state = _state(work)
        if state["phase"] != "ready":
            stop("preparation_interrupted", "파일 준비가 중간에 멈췄습니다.", "같은 대상과 작업공간으로 start를 다시 실행하면 검증한 복사부터 이어갑니다.")
        return _report(work, state)


def error_result(exc):
    if isinstance(exc, EngineError):
        issue = dict(exc.issue)
        messages = {
            "persona_review_due": ("저장된 페르소나의 검토 기한이 지났습니다.", "호스트가 현재 근거와 과업 적합성을 다시 검토해야 합니다. 과거 결과를 새 통과로 바꾸지 않습니다."),
            "persona_retired": ("이 페르소나는 현재 재사용할 수 없습니다.", "호스트가 폐기 사유와 현재 근거를 확인해야 합니다."),
            "stale_build": ("기존 결과와 현재 빌드 연결이 일치하지 않습니다.", "같은 빌드의 근거인지 확인하고 새로운 제품 검증과 구분합니다."),
            "lock_busy": ("다른 준비 작업이 이 작업공간을 사용하고 있습니다.", "진행 중인 작업이 끝나면 같은 명령으로 상태를 확인합니다. 별도 실행으로 한도를 초기화하지 않습니다."),
            "unsafe_path": ("선택한 경로에 외부 링크 또는 상위 폴더 이동이 있습니다.", "승인된 폴더 안의 실제 경로를 사용합니다. 링크를 자동으로 따라가지 않습니다."),
        }
        if issue["code"] in messages:
            issue["reason"], issue["next_step"] = messages[issue["code"]]
        return dict(result="blocked", issue=issue)
    if isinstance(exc, FileNotFoundError):
        return dict(result="blocked", issue=dict(code="source_missing",
                    reason="필요한 입력 파일이나 폴더가 없습니다.",
                    next_step="호스트가 대상 경로와 검토한 파일 범위를 확인합니다. 수동 매니페스트 작성은 필요하지 않습니다."))
    return dict(result="blocked", issue=dict(code="input_or_io",
                reason="입력 또는 작업공간을 안전하게 준비하지 못했습니다.",
                next_step="기존 파일과 결과는 보존했습니다. 호스트가 권한·입력 형식·남은 디스크 공간을 확인합니다."))
