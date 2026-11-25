"""Reviewed static browser journeys using the existing measured web driver.

The host owns source review and semantic task selection. This module connects
current saved personas to bounded browser observations; it is not a user study,
an OS sandbox, a general URL launcher or a model/agent transport.
"""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import time

from uxresearch.canonical import EngineError, byte_digest, canonical, digest, loads
from uxresearch.storage import safe_path
from . import swarm, workspace

PLAN = "ux-journey-browser-plan.v1"
ADAPTER = "ux-journey-browser-adapter.v1"
DRIVER = Path(__file__).resolve().parents[1] / "drivers/web"
BRIDGE = DRIVER / "journey_bridge.mjs"
ORIGIN = "https://remorsearch.invalid/"
STATIC = {".html", ".css", ".js", ".mjs", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".woff", ".woff2"}
MAX_OUTPUT = 256 * 1024


def stop(code, reason):
    workspace.stop(code, reason, "호스트가 검토한 합성 웹 파일·기준 연결·브라우저 런타임을 확인합니다. 기존 시도를 자동 반복하지 않습니다.")


def manifest(prepared, plan):
    """Freeze exact reviewed static inputs and criterion/check mappings."""
    raw = workspace.read_file(Path(prepared["source"]), plan["runner"], sensitive_check=True)
    if byte_digest(raw) != prepared["inputs"][plan["runner"]]:
        stop("browser_source_changed", "검토한 브라우저 계획 파일이 바뀌었습니다.")
    adapter = loads(raw)
    tasks = {t["id"]: t for t in plan["tasks"]}
    if (not isinstance(adapter, dict) or set(adapter) != {"schema_version", "journeys"}
            or adapter["schema_version"] != ADAPTER or not isinstance(adapter["journeys"], list)
            or len(adapter["journeys"]) != len(tasks)):
        stop("browser_manifest", "각 과제에 정확히 하나의 검토된 브라우저 여정이 필요합니다.")
    files = {name: sha for name, sha in prepared["inputs"].items()
             if Path(name).suffix in STATIC and prepared["destinations"][name] == "product/" + name}
    if not 1 <= len(files) <= 64:
        stop("browser_files", "브라우저가 읽을 검토된 정적 파일 범위가 없습니다.")
    journeys = {}
    for journey in adapter["journeys"]:
        if not isinstance(journey, dict) or set(journey) != {"task_id", "scenario", "device_id", "criteria"}:
            stop("browser_manifest", "브라우저 여정의 필드가 맞지 않습니다.")
        tid = journey["task_id"]
        if tid not in tasks or tid in journeys:
            stop("browser_mapping", "브라우저 여정의 과제 연결이 중복되거나 누락됐습니다.")
        task, scenario = tasks[tid], journey["scenario"]
        if not isinstance(scenario, dict) or scenario.get("task_goal_ko") != task["goal"]:
            stop("browser_goal", "브라우저 여정과 고정한 사용자 목표가 다릅니다.")
        surface = scenario.get("surface", {})
        url = surface.get("url") if isinstance(surface, dict) else None
        if (not isinstance(url, str) or not url.startswith(ORIGIN) or url[len(ORIGIN):] not in files
                or not url.endswith(".html") or "build_id" in surface):
            stop("browser_scope", "검토한 합성 페이지 밖의 주소 또는 임의 빌드 연결은 실행하지 않습니다.")
        success = scenario.get("success")
        checks = success.get("task_checks") if isinstance(success, dict) and set(success) == {"task_checks"} else None
        if not isinstance(checks, list) or not 1 <= len(checks) <= 64:
            stop("browser_checks", "실제 행동 후 측정할 기준이 필요합니다.")
        ids = [c.get("id") if isinstance(c, dict) else None for c in checks]
        if any(not isinstance(cid, str) for cid in ids) or len(set(ids)) != len(ids):
            stop("browser_checks", "측정 기준 식별자가 중복되거나 잘못됐습니다.")
        expected = {(kind, i) for kind in ("success", "recovery") for i in range(len(task[kind + "_criteria"]))}
        refs = journey["criteria"]
        if not isinstance(refs, list) or len(refs) != len(expected) or len(refs) != len(checks):
            stop("browser_mapping", "모든 성공·복구 기준을 별도의 실제 측정에 연결해야 합니다.")
        seen, used = set(), set()
        for ref in refs:
            if (not isinstance(ref, dict) or set(ref) != {"kind", "index", "check_id"}
                    or type(ref["index"]) is not int or not isinstance(ref["kind"], str)
                    or (ref["kind"], ref["index"]) not in expected
                    or (ref["kind"], ref["index"]) in seen
                    or ref["check_id"] not in ids or ref["check_id"] in used):
                stop("browser_mapping", "성공·복구 기준과 측정의 연결이 중복되거나 맞지 않습니다.")
            seen.add((ref["kind"], ref["index"]))
            used.add(ref["check_id"])
        if swarm.clean(journey) != journey:
            stop("browser_privacy", "브라우저 계획에 개인 식별 형식이 있습니다.")
        journeys[tid] = copy.deepcopy(journey)
    return dict(journeys=journeys, files=files, manifest_sha256=byte_digest(raw))


def _file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _driver_hash():
    return digest({p.name: _file_hash(p) for p in sorted(DRIVER.glob("*.mjs")) if not p.name.endswith(".test.mjs")})


def _package_hash(root):
    root = Path(root)
    if not root.is_dir() or root.resolve() != root:
        stop("browser_runtime_changed", "고정한 브라우저 패키지 위치가 달라졌습니다.")
    files = {}
    for base, directories, names in os.walk(root, followlinks=False):
        for name in directories + names:
            if (Path(base) / name).is_symlink():
                stop("browser_runtime_changed", "브라우저 패키지에 검토하지 않은 링크가 있습니다.")
        for name in names:
            path = Path(base) / name
            files[str(path.relative_to(root))] = _file_hash(path)
    return digest(files)


def environment(runtime, cwd):
    env = {"PATH": os.path.dirname(runtime["node"]) + os.pathsep + os.defpath,
           "HOME": str(cwd), "TMPDIR": str(cwd), "LANG": "C", "LC_ALL": "C"}
    for key in ("NODE_PATH", "PLAYWRIGHT_BROWSERS_PATH"):
        if runtime.get(key):
            env[key] = runtime[key]
    if runtime.get("info"):
        env["REMORSEARCH_JOURNEY_PLAYWRIGHT"] = runtime["info"]["playwright_path"]
        env["REMORSEARCH_JOURNEY_PLAYWRIGHT_CORE"] = runtime["info"]["playwright_core_path"]
        env["REMORSEARCH_JOURNEY_CHROMIUM"] = runtime["info"]["chromium_executable"]
    return env


def runtime(work):
    node = os.environ.get("REMORSEARCH_JOURNEY_NODE") or shutil.which("node")
    if not node or not Path(node).is_file():
        stop("browser_runtime", "Node 22와 고정된 Playwright·Chromium이 준비되지 않았습니다.")
    node = str(Path(node).resolve())
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        cache = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    elif os.sys.platform == "darwin":
        cache = str(Path.home() / "Library/Caches/ms-playwright")
    else:
        cache = str(Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ms-playwright")
    cache = "0" if cache == "0" else str(Path(cache).expanduser().resolve())
    module_dirs = [str(Path(p).expanduser().resolve()) for p in os.environ.get("NODE_PATH", "").split(os.pathsep) if p]
    config = {"node": node, "NODE_PATH": os.pathsep.join(module_dirs), "PLAYWRIGHT_BROWSERS_PATH": cache}
    try:
        result = subprocess.run([node, str(BRIDGE), "--probe"], env=environment(config, work),
                                cwd=work, capture_output=True, timeout=10)
        info = loads(result.stdout)
        if (result.returncode or len(result.stdout) > 16384 or len(result.stderr) > 16384
                or set(info) != {"schema_version", "node_version", "playwright_version", "chromium_executable",
                                 "playwright_path", "playwright_core_path"}
                or info["schema_version"] != "ux-journey-browser-runtime.v1"
                or not info["node_version"].startswith("22.") or info["playwright_version"] != "1.56.1"):
            raise ValueError()
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        stop("browser_runtime", "Node 22·Playwright 1.56.1·Chromium 준비를 확인하지 못했습니다. 실행 시도는 만들지 않았습니다.")
    config.update(info=info, node_sha256=_file_hash(node), driver_sha256=_driver_hash(),
                  chromium_sha256=_file_hash(info["chromium_executable"]),
                  playwright_sha256=_package_hash(info["playwright_path"]),
                  playwright_core_sha256=_package_hash(info["playwright_core_path"]))
    return config


def verify_runtime(config):
    info = config["info"]
    if (_file_hash(config["node"]) != config["node_sha256"] or _driver_hash() != config["driver_sha256"]
            or _file_hash(info["chromium_executable"]) != config["chromium_sha256"]
            or _package_hash(info["playwright_path"]) != config["playwright_sha256"]
            or _package_hash(info["playwright_core_path"]) != config["playwright_core_sha256"]):
        stop("browser_runtime_changed", "브라우저 실행을 고정한 뒤 런타임 또는 드라이버 코드가 바뀌었습니다.")


def request_for(work, browser, task_id, binding, output, seconds):
    journey = browser["journeys"][task_id]
    scenario = copy.deepcopy(journey["scenario"])
    scenario["surface"]["build_id"] = binding["build_sha256"]
    return dict(schema_version="ux-journey-browser-request.v1", binding=binding, source=str(work / "product"),
                files=browser["files"], output=str(output), scenario=scenario,
                device_id=journey["device_id"], timeout_seconds=seconds)


def prepare(work, prepared, plan, personas, build_hash):
    browser = manifest(prepared, plan)
    config = runtime(work)
    for task in plan["tasks"]:
        record = personas["state"]["entries"][plan["product_id"] + "/" + task["persona_id"]][-1]
        # Non-executable preflight input, never a claim, receipt or observation.
        binding = dict(task_id=task["id"], attempt=1, operation_id="preflight", build_sha256=build_hash,
                       persona_id=task["persona_id"], revision=record["revision"],
                       profile_sha256=record["profile_sha256"], prd_sha256=record["context"]["prd_sha256"])
        req = request_for(work, browser, task["id"], binding, work / "browser-preflight", plan["timeout_seconds"])
        raw = canonical(req)
        if len(raw) > MAX_OUTPUT:
            stop("browser_request", "브라우저 여정 요청이 허용 크기를 넘었습니다.")
        try:
            checked = subprocess.run([config["node"], str(BRIDGE), "--validate"], input=raw,
                env=environment(config, work), cwd=work, capture_output=True, timeout=10)
            if checked.returncode or loads(checked.stdout) != {"schema_version": "ux-journey-browser-validation.v1", "valid": True}:
                raise ValueError()
        except (OSError, ValueError, subprocess.TimeoutExpired):
            stop("browser_plan", "고정한 브라우저 행동·기준 또는 정적 파일 검증이 실패했습니다. 과제를 배정하지 않았습니다.")
    browser["runtime"] = config
    return browser


def _response(raw, binding):
    value = loads(raw)
    if (not isinstance(value, dict) or set(value) != {"schema_version", "binding", "problem", "cleanup_confirmed", "run"}
            or value["schema_version"] != "ux-journey-browser-result.v1" or value["binding"] != binding
            or type(value["cleanup_confirmed"]) is not bool
            or (value["problem"] is not None and (not isinstance(value["problem"], str)
                or not re.fullmatch(r"[a-z_]{1,64}", value["problem"])))):
        raise ValueError("browser_response")
    run = value["run"]
    if run is not None and (not isinstance(run, dict) or set(run) != {"path", "sha256"}
            or run["path"] != "run.json" or not re.fullmatch(r"[a-f0-9]{64}", str(run["sha256"]))):
        raise ValueError("browser_run_reference")
    return value


def invoke(browser, cwd, request, seconds, on_spawn):
    """Bounded pipes; graceful close acknowledgement is required for descendants."""
    from .local_run import _cancellation
    config, payload = browser["runtime"], canonical(request)
    if len(payload) > MAX_OUTPUT:
        stop("browser_request", "브라우저 실행 요청이 허용 크기를 넘었습니다.")
    start, process = time.monotonic(), None
    output, errors = bytearray(), bytearray()
    problem, forced = None, False
    try:
        with _cancellation(), selectors.DefaultSelector() as selector:
            process = subprocess.Popen([config["node"], str(BRIDGE)], cwd=cwd,
                env=environment(config, cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, start_new_session=True, close_fds=True)
            on_spawn()
            for pipe, events in ((process.stdin, selectors.EVENT_WRITE), (process.stdout, selectors.EVENT_READ), (process.stderr, selectors.EVENT_READ)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, events)
            offset, stopping = 0, False
            deadline = start + seconds + 2
            while selector.get_map() or process.poll() is None:
                try:
                    if time.monotonic() >= deadline:
                        if stopping:
                            forced = True
                            break
                        problem, stopping = "timeout", True
                        process.terminate()
                        deadline = time.monotonic() + 5
                    for key, _ in selector.select(0.05):
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
                                (output if pipe is process.stdout else errors).extend(chunk)
                                if len(output) + len(errors) > MAX_OUTPUT:
                                    problem, forced = "output_limit", True
                                    break
                    if forced:
                        break
                except KeyboardInterrupt:
                    if stopping:
                        forced = True
                        break
                    problem, stopping = "cancelled", True
                    process.terminate()
                    deadline = time.monotonic() + 5
            if not forced:
                process.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        problem = problem or "process_unavailable"
    except KeyboardInterrupt:
        problem, forced = "cancelled", True
    finally:
        if process is not None:
            if process.poll() is None:
                forced = True
                try:
                    process.kill()  # Direct child only; never saved PIDs or process groups.
                    process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe and not pipe.closed:
                    pipe.close()
    response = None
    try:
        response = _response(bytes(output), request["binding"])
    except (EngineError, ValueError, TypeError, KeyError):
        problem = problem or "invalid_browser_response"
    cleanup = bool(process is not None and process.poll() is not None and not forced
                   and response and response["cleanup_confirmed"])
    if response:
        problem = problem or response["problem"]
    if not problem and (process.returncode != 0 or response["run"] is None):
        problem = "browser_result_missing"
    diagnostic = dict(problem=problem, cleanup_confirmed=cleanup,
        returncode=process.returncode if process else None, elapsed_seconds=round(time.monotonic() - start, 6),
        stdout_bytes=len(output), stderr_bytes=len(errors),
        stdout_sha256=byte_digest(output), stderr_sha256=byte_digest(errors))
    return response, diagnostic


def observations(run_root, state, claim, response, diagnostic):
    """Reconstruct receipts from native checkpoints, never from process success."""
    binding = dict(task_id=claim["task"]["id"], attempt=claim["attempt"], operation_id=claim["operation_id"],
                   build_sha256=claim["build"]["sha256"], **claim["binding"])
    _response(canonical(response), binding)
    partial_problems = {None, "timeout", "cancelled", "browser_execution_failed"}
    if (response["problem"] not in partial_problems or diagnostic["problem"] not in partial_problems
            or not response["cleanup_confirmed"] or not diagnostic["cleanup_confirmed"] or response["run"] is None):
        raise ValueError("browser_not_completed")
    browser = state["browser"]
    journey = browser["journeys"][claim["task"]["id"]]
    scenario = journey["scenario"]
    base = Path(claim["evidence_path"]) / "scratch/browser"
    base = safe_path(base, run_root)
    artifacts = []
    def artifact(name, aid, kind, expected=None):
        workspace.relative(name)
        if "/" in name:
            raise ValueError("nested_browser_artifact")
        path = base / name
        raw = workspace.read_file(base, name, sensitive_check=kind == "execution_log")
        if path.stat().st_mode & 0o077 or not raw or (expected and byte_digest(raw) != expected):
            raise ValueError("browser_artifact_integrity")
        artifacts.append(dict(id=aid, kind=kind, path=str(path.relative_to(run_root)), sha256=byte_digest(raw)))
        return raw
    raw = artifact("run.json", "browser-run", "execution_log", response["run"]["sha256"])
    native = loads(raw)
    expected_run = "R-" + binding["operation_id"]
    driver = native.get("driver", {})
    if (native.get("schema_version") != "ergo-run.v1" or native.get("run_id") != expected_run
            or native.get("scenario_id") != scenario["scenario_id"] or native.get("profile_id") != binding["persona_id"]
            or native.get("surface", {}).get("build_id") != binding["build_sha256"]
            or native.get("surface", {}).get("url") != scenario["surface"]["url"]
            or native.get("mode") != "scripted" or driver.get("name") != "playwright-web"
            or driver.get("version") != "1.56.1" or driver.get("browser_connected") is not False
            or native.get("success_basis") != "measured"):
        raise ValueError("browser_native_binding")
    captures = {}
    snapshots = native.get("snapshots")
    if not isinstance(snapshots, list) or not 1 <= len(snapshots) <= 48:
        raise ValueError("browser_snapshots")
    for i, snap in enumerate(snapshots):
        sid = snap.get("snapshot_id")
        if not isinstance(sid, str) or sid in captures:
            raise ValueError("browser_snapshot_id")
        doc = loads(artifact(snap["path"], "snapshot-" + str(i), "execution_log"))
        page_url = doc.get("surface", {}).get("url")
        if (doc.get("schema_version") != "ergo-snapshot.v1" or doc.get("snapshot_id") != sid
                or doc.get("run_id") != expected_run or doc.get("step_index") != snap.get("step_index")
                or doc.get("surface", {}).get("build_id") != binding["build_sha256"]
                or not isinstance(page_url, str) or not page_url.startswith(ORIGIN)
                or page_url[len(ORIGIN):] not in browser["files"] or not page_url.endswith(".html")
                or doc.get("screenshot", {}).get("path") != snap["png"]):
            raise ValueError("browser_snapshot_binding")
        png = artifact(snap["png"], "capture-" + str(i), "screenshot", doc["screenshot"]["sha256"])
        # swarm.record/report decode these exact private PNG bytes at admission;
        # this reconstruction adds binding/hash checks without a duplicate decode.
        captures[sid] = dict(refs=["execution", "browser-run", "snapshot-" + str(i), "capture-" + str(i)],
                             step=snap["step_index"], ordinal=i, notes=doc.get("notes", []),
                             elements=doc.get("elements", []))
    steps = native.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= len(scenario["steps"]):
        raise ValueError("browser_steps")
    receipt_steps, executed = [], {}
    redacted_inputs = {c.get("from_step") for c in scenario["success"]["task_checks"] if c.get("redact")}
    private_values = [a["text"] for i, a in enumerate(scenario["steps"], 1)
                       if (a.get("redact") or i in redacted_inputs) and a.get("text")]
    private_values += [c["expected"] for c in scenario["success"]["task_checks"]
                       if c.get("redact") and isinstance(c.get("expected"), str) and c["expected"]]
    private_values = list(dict.fromkeys(private_values))
    def displayed(value, key):
        if isinstance(value, str) and key in {"text", "value", "selected", "described_by_text", "name", "title",
                "error", "message", "stack", "intent", "expected", "observed", "consequence", "description", "note", "notes"}:
            for private in private_values:
                value = "[redacted]".join(part.replace(private, "[redacted]") for part in value.split("[redacted]"))
        return value
    for i, step in enumerate(steps, 1):
        authored = scenario["steps"][i - 1]
        actual = step.get("action", {})
        if (step.get("step_index") != i or step.get("result") not in {"ok", "no_target", "error"}
                or any(actual.get(k) != ("[redacted]" if k == "text" and (authored.get("redact") or i in redacted_inputs) else displayed(v, k))
                       for k, v in authored.items())):
            raise ValueError("browser_step_binding")
        before = captures.get(step.get("before"))
        previous_id = snapshots[0]["snapshot_id"] if i == 1 else executed[i - 1]["after"]
        previous = captures.get(previous_id)
        if (before is None or previous is None or previous["step"] != i - 1
                or (i > 1 and executed[i - 1]["result"] != "ok")):
            raise ValueError("browser_step_chain")
        if step["before"] != previous_id:
            # WebSession refreshes the before capture when a target scrolls into
            # view or appears late. It is the next capture, at this action index.
            reason = "pre_action_auto_scroll" if step.get("auto_scrolled") is True else "pre_action_target_appeared"
            if (before["step"] != i or before["ordinal"] != previous["ordinal"] + 1
                    or not isinstance(before["notes"], list) or displayed(reason, "notes") not in before["notes"]):
                raise ValueError("browser_step_chain")
        after = captures.get(step.get("after"))
        if after is None:
            if i != len(steps) or step["result"] == "ok" or step.get("after") is not None:
                raise ValueError("browser_step_capture")
            refs = ["execution", "browser-run"]
            message = "No confirmed after-action capture; this tail action remains uncertain."
        else:
            if after["step"] != i or after["ordinal"] != before["ordinal"] + 1:
                raise ValueError("browser_step_capture")
            refs = after["refs"]
            message = "Captured current page state."
        executed[i] = step
        receipt_steps.append(dict(action=f"Browser action {i}: {authored['action']}",
            observation=f"Action result: {step['result']}; {message}", evidence_ids=refs))
    measured = native.get("success_detail", {}).get("criteria")
    checks = scenario["success"]["task_checks"]
    if not isinstance(measured, list) or len(measured) != len(checks):
        raise ValueError("browser_measured_criteria")
    by_id = {}
    for item in measured:
        if item.get("kind") != "task_check" or item.get("id") in by_id:
            raise ValueError("browser_check_duplicate")
        by_id[item["id"]] = item
    receipt_criteria = []
    for ref in journey["criteria"]:
        check = next(c for c in checks if c["id"] == ref["check_id"])
        item = by_id[ref["check_id"]]
        if any(item.get(k) != check[k] for k in ("id", "selector", "property", "severity")) or item.get("checkpoint") != check["after_step"]:
            raise ValueError("browser_check_binding")
        if item.get("consequence") != displayed(check["consequence"], "consequence"):
            raise ValueError("browser_check_description")
        status = {"pass": "passed", "fail": "failed", "unevaluable": "not_run"}.get(item.get("result"))
        if status is None or item.get("passed") is not {"passed": True, "failed": False, "not_run": None}[status]:
            raise ValueError("browser_check_result")
        refs = []
        message = f"Measured {check['property']} check at action {check['after_step']}: {item['result']}."
        if status != "not_run":
            checkpoint, sid = check["after_step"], item.get("snapshot_id")
            if (checkpoint not in executed or executed[checkpoint]["result"] != "ok"
                    or sid not in captures or captures[sid]["step"] != checkpoint
                    or item.get("step_index") != checkpoint or executed[checkpoint]["after"] != sid):
                raise ValueError("browser_checkpoint")
            if "from_step" in check and (check["from_step"] not in executed or executed[check["from_step"]]["result"] != "ok"):
                raise ValueError("browser_source_action")
            refs = captures[sid]["refs"]
            elements = [e for e in captures[sid]["elements"] if e.get("id") == item.get("element_id")]
            if (len(elements) != 1 or elements[0].get("visible") is not True
                    or elements[0].get("in_viewport") is not True or elements[0].get("occluded_fraction") != 0
                    or elements[0].get("visible_geometry") != "measured"
                    or not isinstance(elements[0].get("visible_box"), dict)
                    or elements[0]["visible_box"].get("w", 0) <= 0 or elements[0]["visible_box"].get("h", 0) <= 0):
                status, refs = "not_run", []
                message = "DOM comparison exists, but its target is missing, outside the capture or obscured; visible task completion remains unobserved."
        receipt_criteria.append(dict(kind=ref["kind"], index=ref["index"], status=status,
            observation=message, evidence_ids=refs))
    failed = any(c["status"] == "failed" for c in receipt_criteria)
    all_passed = all(c["status"] == "passed" for c in receipt_criteria)
    outcome = "failed" if failed else "passed" if (all_passed and response["problem"] is None
        and diagnostic["problem"] is None and native.get("status") == "completed"
        and native.get("success") is True and len(steps) == len(scenario["steps"])) else "inconclusive"
    reason = ("Owned browser measured a failed task criterion; later recovery does not erase it." if failed else
              "Owned browser observed all fixed task criteria; real-user effect remains unmeasured." if outcome == "passed" else
              "Some browser actions or criteria remain unobserved; no task pass.")
    observation = dict(schema_version="ux-journey-observation.v1", binding=binding, reason=reason,
        steps=[{k: v for k, v in row.items() if k != "evidence_ids"} for row in receipt_steps],
        criteria=[{k: v for k, v in row.items() if k != "evidence_ids"} for row in receipt_criteria])
    return dict(observation=observation, steps=receipt_steps, criteria=receipt_criteria,
                artifacts=artifacts, outcome=outcome, reason=reason)


def record(work, library, state, claim, response, diagnostic):
    from .local_run import DIRECTORY, _immutable
    root = work / DIRECTORY / "run"
    receipt = swarm.receipt_starter(library, root, claim)
    receipt.pop("drafting_guidance")
    receipt["schema_version"] = "ux-persona-swarm-receipt.v1"
    parsed = None
    if response and response.get("run") is not None and diagnostic["cleanup_confirmed"]:
        try:
            parsed = observations(root, state, claim, response, diagnostic)
        except (EngineError, OSError, ValueError, KeyError, TypeError, AttributeError):
            diagnostic["problem"] = "invalid_browser_evidence"
    binding = dict(task_id=claim["task"]["id"], attempt=claim["attempt"], operation_id=claim["operation_id"],
                   build_sha256=claim["build"]["sha256"], **claim["binding"])
    evidence = dict(schema_version="ux-journey-browser-log.v1", binding=binding,
        diagnostic=diagnostic, observation=parsed["observation"] if parsed else None,
        browser_response=response, ui_observed=bool(parsed), real_user_evidence=False)
    path = Path(claim["evidence_path"]) / "observation.json"
    raw = canonical(evidence)
    _immutable(root, str(path.relative_to(root)), raw)
    receipt["artifacts"] = [dict(id="execution", kind="execution_log", path=str(path.relative_to(root)), sha256=byte_digest(raw))]
    if parsed:
        receipt.update({key: parsed[key] for key in ("steps", "criteria", "outcome", "reason")})
        receipt["artifacts"].extend(parsed["artifacts"])
    else:
        receipt["outcome"] = "inconclusive"
        receipt["reason"] = "Browser execution has no admissible observations: " + diagnostic["problem"] + "."
        for row in receipt["criteria"]:
            row["observation"] = "No valid browser observation; infrastructure uncertainty."
    swarm.record(library, root, receipt)


def audit(work, state, claim, receipt):
    """Independent readback reconstruction; never trusts a receipt's own success."""
    from .local_run import DIRECTORY
    root = work / DIRECTORY / "run"
    artifacts = receipt["artifacts"]
    logs = [a for a in artifacts if a["id"] == "execution" and a["kind"] == "execution_log"]
    if len(logs) != 1:
        raise ValueError("browser_execution_log")
    raw = workspace.read_file(root, logs[0]["path"], sensitive_check=True)
    if byte_digest(raw) != logs[0]["sha256"]:
        raise ValueError("browser_execution_digest")
    evidence = loads(raw)
    binding = dict(task_id=claim["task"]["id"], attempt=claim["attempt"], operation_id=claim["operation_id"],
                   build_sha256=claim["build"]["sha256"], **claim["binding"])
    if (set(evidence) != {"schema_version", "binding", "diagnostic", "observation", "browser_response", "ui_observed", "real_user_evidence"}
            or evidence["schema_version"] != "ux-journey-browser-log.v1" or evidence["binding"] != binding
            or evidence["real_user_evidence"] is not False or evidence["diagnostic"]["cleanup_confirmed"] is not True):
        raise ValueError("browser_execution_binding")
    if evidence["observation"] is not None:
        parsed = observations(root, state, claim, evidence["browser_response"], evidence["diagnostic"])
        if (evidence["ui_observed"] is not True or evidence["observation"] != parsed["observation"]
                or artifacts != logs + parsed["artifacts"]
                or any(receipt[k] != parsed[k] for k in ("steps", "criteria", "outcome", "reason"))):
            raise ValueError("browser_receipt_disagreement")
    elif (evidence["observation"] is not None or evidence["ui_observed"] is not False
            or len(artifacts) != 1 or receipt["steps"] or receipt["outcome"] != "inconclusive"
            or any(c["status"] != "not_run" or c["evidence_ids"] for c in receipt["criteria"])):
        raise ValueError("browser_uncertain_receipt")
    return evidence["observation"]
