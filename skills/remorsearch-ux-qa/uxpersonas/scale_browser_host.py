"""Owned loopback-only headless Chrome host for live ScaleExecution journeys.

Never attaches to a user browser. Each queue context owns a separate Chrome profile
and CDP process. Only localhost HTTP targets are accepted; cross-origin requests,
websockets, credentials and high-risk form controls are blocked.
"""
from __future__ import annotations
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import time
import zipfile

from uxresearch.canonical import byte_digest, canonical
from uxresearch.storage import safe_path, atomic
from . import swarm


async def _with_timeout(coro, seconds):
    """Bound one owned coroutine on Python 3.10+, preserving caller cancellation."""
    timeout = getattr(asyncio, "timeout", None)
    if timeout is not None:
        # Preserve the original in-task behavior on Python 3.11 and newer.
        async with timeout(seconds):
            return await coro
    task = asyncio.create_task(coro)
    try:
        # wait_for in Python 3.10 can swallow caller cancellation when the
        # child finishes concurrently (CPython #86296). wait keeps it distinct
        # from our deadline and avoids 3.10's separate asyncio.TimeoutError.
        done, _ = await asyncio.wait({task}, timeout=seconds)
        if task not in done:
            raise TimeoutError()
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            # Drain owned IO/action before releasing its channel lock; cleanup
            # errors must not replace the caller's cancellation or timeout.
            await asyncio.gather(task, return_exceptions=True)
        elif not task.cancelled():
            # Also consume a concurrently completed error on caller cancellation.
            task.exception()


def _preserve_driver_hashes(original, cleaned):
    """Keep typed, validated evidence digests out of free-text privacy redaction."""
    paths = (
        ("storage_snapshot", "sha256"),
        ("import_attempt", "fixture_sha256"),
        ("import_attempt", "storage_before", "sha256"),
        ("import_attempt", "storage_after", "sha256"),
        ("legacy_seed", "fixture_sha256"),
        ("legacy_seed", "product_loader_sha256"),
        ("legacy_seed", "product_validation_sha256"),
        ("legacy_seed", "storage_before", "sha256"),
        ("legacy_seed", "storage_after", "sha256"),
        ("legacy_state", "storage_sha256"),
    )
    for parts in paths:
        source, target = original, cleaned
        for key in parts[:-1]:
            source = source.get(key) if isinstance(source, dict) else None
            target = target.get(key) if isinstance(target, dict) else None
        if isinstance(source, dict) and isinstance(target, dict):
            value = source.get(parts[-1])
            if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
                target[parts[-1]] = value
    original_seed, clean_seed = original.get("legacy_seed"), cleaned.get("legacy_seed")
    if isinstance(original_seed, dict) and isinstance(clean_seed, dict):
        value = original_seed.get("product_commit")
        if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{40}", value):
            clean_seed["product_commit"] = value
    original_state, clean_state = original.get("legacy_state"), cleaned.get("legacy_state")
    if (isinstance(original_state, dict) and isinstance(clean_state, dict)
            and original_state.get("schema_version") == "ux-legacy-state.v1"):
        sources, targets = original_state.get("snapshots"), clean_state.get("snapshots")
        if isinstance(sources, list) and isinstance(targets, list) and len(sources) == len(targets) <= 10:
            for source, target in zip(sources, targets):
                if isinstance(source, dict) and isinstance(target, dict):
                    value = source.get("account_sha256")
                    if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
                        target["account_sha256"] = value


def _authorize_legacy_seed(task, arguments, uploads, attempted, *, legacy_seed_config=None):
    """Authorize only a host-configured legacy seed in its original owned context."""
    if not isinstance(legacy_seed_config, dict):
        raise RuntimeError("legacy_seed_not_configured")
    req_id = legacy_seed_config.get("requirement_id")
    fixture = legacy_seed_config.get("fixture")
    if not isinstance(req_id, str) or not req_id or not isinstance(fixture, str) or not fixture:
        raise RuntimeError("legacy_seed_not_configured")
    if (not isinstance(task, dict)
            or not isinstance(task.get("requirement_ids"), list)
            or req_id not in task.get("requirement_ids", [])):
        raise RuntimeError("legacy_seed_task_not_authorized")
    if arguments != {"file": fixture}:
        raise RuntimeError("legacy_seed_fixed_fixture_only")
    if attempted:
        raise RuntimeError("legacy_seed_already_attempted")
    if uploads:
        raise RuntimeError("legacy_seed_after_import_not_allowed")


class ScaleBrowserHost:
    # One Queue tool call may start a context then perform an action. Keep
    # 70 + 90 = 160 seconds inside the live Queue's 180-second call ceiling.
    EXCHANGE_TIMEOUTS = {"start": 70, "act": 90, "close": 12}
    TERMINATE_SECONDS = 4
    KILL_SECONDS = 3

    def __init__(self, *, target_url, chrome, node, driver_path, adapter_path, fixtures_path, parallel_safe=True,
                 criteria_evaluator=None, legacy_seed_config=None):
        from urllib.parse import urlsplit
        parsed = urlsplit(target_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("The live Scale browser target must be an explicit loopback HTTP origin without credentials/query.")
        if not Path(chrome).is_file() or not os.access(chrome, os.X_OK):
            raise ValueError("A dedicated Chrome executable is required.")
        if not Path(node).is_file() or not os.access(node, os.X_OK):
            raise ValueError("A dedicated Node executable is required.")
        self.target_url = target_url
        self.chrome, self.node = str(Path(chrome).resolve()), str(Path(node).resolve())
        self.driver = Path(driver_path).resolve()
        self.fixtures = safe_path(fixtures_path)
        self.criteria_evaluator = criteria_evaluator
        self.legacy_seed_config = copy.deepcopy(legacy_seed_config) if legacy_seed_config is not None else None
        if not self.fixtures.is_dir() or not (self.fixtures / "fixture-manifest.json").is_file():
            raise ValueError("A frozen synthetic fixture directory and manifest are required.")
        adapter = Path(adapter_path).resolve()
        manifest_bytes = (self.fixtures / "fixture-manifest.json").read_bytes()
        self.adapter_sha256 = hashlib.sha256(adapter.read_bytes() + self.driver.read_bytes() + manifest_bytes).hexdigest()
        self.info = dict(name="owned-headless-chrome-cdp", mode="model_tools",
            model="Configured local model gateway via RoutedScaleProvider",
            adapter_sha256=self.adapter_sha256, isolated_contexts=True,
            parallel_safe=bool(parallel_safe))
        self.processes = {}
        self.locks = {}
        self.context_paths = {}
        self.serials = {}
        self.context_tasks = {}
        self.context_uploads = {}
        self.context_observations = {}
        self.context_fixture_validation = {}
        self.context_seed_attempts = {}
        self.owned_groups = {}
        self.poisoned = set()
        self.closed_contexts = set()
        self.lifecycle = {}

    def _validate_fixture_upload(self, fixture_name):
        """Expose bounded fixture-shape metadata without leaking fixture contents."""
        if (not isinstance(fixture_name, str) or fixture_name.startswith("@group:")
                or not fixture_name.lower().endswith(".zip")):
            return None
        try:
            path = safe_path(self.fixtures / fixture_name, self.fixtures)
            with zipfile.ZipFile(path) as archive:
                html_members = [name for name in archive.namelist()
                                if name.lower().endswith(".html")]
                if not html_members:
                    return None
                documents = []
                for member in html_members[:32]:
                    raw = archive.read(member)
                    html = raw.decode("utf-8-sig", "replace")
                    complete = bool(
                        re.search(r"<html\b", html, re.I)
                        and re.search(r"<body\b", html, re.I)
                        and re.search(r"</body\s*>[\s\S]*</html\s*>", html, re.I)
                    )
                    documents.append({
                        "member": Path(member).name,
                        "complete_html_document": complete,
                    })
                return {
                    "fixture": fixture_name,
                    "archive_valid": True,
                    "html_documents": documents,
                    "complete_html_documents": bool(documents) and all(
                        row["complete_html_document"] for row in documents),
                }
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            return {"fixture": fixture_name, "archive_valid": False,
                    "reason": "fixture_archive_unreadable"}

    def can_resume(self, context_id, observations):
        process = self.processes.get(context_id)
        return bool(process and process.returncode is None
                    and context_id not in self.poisoned
                    and context_id not in self.closed_contexts)

    def _record_lifecycle(self, context, phase, **details):
        process = self.processes.get(context)
        record = dict(self.lifecycle.get(context, {}), schema_version="owned-browser-host.v1",
                      context_id=context, phase=phase, recorded_at=time.time(),
                      node_pid=process.pid if process else None,
                      owned_pgid=self.owned_groups.get(context),
                      profile_path=self.context_paths.get(context),
                      channel_poisoned=context in self.poisoned, **details)
        self.lifecycle[context] = record
        profile = self.context_paths.get(context)
        # Ownership and exceptional/terminal transitions are durable. Ordinary
        # command progress stays in memory to avoid two fsyncs per browser action.
        if profile and phase not in {"dispatching", "reply_received"}:
            try:
                atomic(Path(profile).parent / "browser-host-lifecycle.json", canonical(record))
            except (OSError, ValueError) as exc:
                # Retain ownership in memory even if the evidence volume stalls/fails.
                record["diagnostic_write_error"] = type(exc).__name__

    def _group_alive(self, context):
        pgid = self.owned_groups.get(context)
        if pgid is None:
            return True  # Missing ownership is never evidence of closure.
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    async def _wait_owned_exit(self, context, seconds):
        process = self.processes[context]
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if process.returncode is not None and not self._group_alive(context):
                return True
            await asyncio.sleep(.05)
        return process.returncode is not None and not self._group_alive(context)

    async def _terminate_owned(self, context):
        """Signal only a new session created by this host; verify the whole group."""
        process = self.processes.get(context)
        pgid = self.owned_groups.get(context)
        if process is None or pgid is None or pgid != process.pid:
            return False
        if await self._wait_owned_exit(context, .05):
            return True
        for sig, seconds in ((signal.SIGTERM, self.TERMINATE_SECONDS),
                             (signal.SIGKILL, self.KILL_SECONDS)):
            self._record_lifecycle(context, "terminating", signal=sig.name)
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:
                return False
            if await self._wait_owned_exit(context, seconds):
                return True
        return False

    async def _exchange(self, context_id, kind, payload):
        lock = self.locks.setdefault(context_id, asyncio.Lock())
        async with lock:
            if context_id in self.closed_contexts:
                raise RuntimeError("browser_context_closed")
            if context_id in self.poisoned:
                raise RuntimeError("browser_context_transport_uncertain")
            process = self.processes.get(context_id)
            if kind == "start" and process is None:
                evidence = safe_path(payload["evidence_path"])
                profile = evidence / "browser-profile"
                profile.mkdir(mode=0o700, exist_ok=False)
                if profile.stat().st_mode & 0o077:
                    raise RuntimeError("browser_profile_permissions")
                process = await asyncio.create_subprocess_exec(
                    self.node, str(self.driver), cwd=str(evidence),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
                self.processes[context_id] = process
                self.context_paths[context_id] = str(profile)
                self.owned_groups[context_id] = process.pid
                self._record_lifecycle(context_id, "spawned")
            if process is None or process.returncode is not None:
                raise RuntimeError("browser_context_not_running")
            ident = self.serials.get(context_id, 0) + 1
            self.serials[context_id] = ident
            packet = json.dumps({"id": ident, "kind": kind, "payload": payload}, ensure_ascii=False, separators=(",", ":"))
            command_started = time.monotonic()
            command_started_at = time.time()
            timeout = self.EXCHANGE_TIMEOUTS[kind]
            self._record_lifecycle(context_id, "dispatching", command=kind, command_id=ident,
                command_started_at=command_started_at, command_timeout_seconds=timeout,
                command_deadline_at=command_started_at + timeout, command_elapsed_seconds=0)
            try:
                # Once bytes may have left the process, a timeout/cancel/protocol
                # failure poisons this channel. Never consume a late reply as a
                # later command's response, and never resend the original action.
                async def exchange_io():
                    process.stdin.write(packet.encode() + b"\n")
                    await process.stdin.drain()
                    return await process.stdout.readline()
                raw = await _with_timeout(exchange_io(), timeout)
                if time.monotonic() - command_started >= timeout:
                    # An event-loop delay must not turn a late response into a
                    # within-budget acknowledgement merely by callback ordering.
                    raise TimeoutError("browser_response_after_deadline")
                if not raw or len(raw) > 65536:
                    raise RuntimeError("browser_transport_closed")
                reply = json.loads(raw)
                if not isinstance(reply, dict) or reply.get("id") != ident:
                    raise RuntimeError("browser_reply_identity_mismatch")
                if not reply.get("error") and "result" not in reply:
                    raise RuntimeError("browser_reply_result_missing")
            except BaseException as exc:
                self.poisoned.add(context_id)
                self._record_lifecycle(context_id, "transport_uncertain",
                    error_type=type(exc).__name__,
                    command_elapsed_seconds=time.monotonic() - command_started)
                raise
            self._record_lifecycle(context_id, "reply_received",
                command_elapsed_seconds=time.monotonic() - command_started)
            if reply.get("error"):
                if any(marker in str(reply["error"]) for marker in (
                        "browser_action_timeout", "browser_action_aborted",
                        "browser_action_transport_uncertain", "cdp_timeout:")):
                    self.poisoned.add(context_id)
                    self._record_lifecycle(context_id, "transport_uncertain",
                        error_type="DriverActionDeadline", driver_error=str(reply["error"])[:120])
                raise RuntimeError("browser_action_failed:" + str(reply.get("error", "unknown"))[:120])
            return reply["result"]

    async def call(self, kind, request):
        context = request["context_id"]
        payload = request["payload"]
        self.context_tasks = getattr(self, "context_tasks", {})
        self.context_uploads = getattr(self, "context_uploads", {})
        self.context_observations = getattr(self, "context_observations", {})
        self.context_fixture_validation = getattr(self, "context_fixture_validation", {})
        self.context_seed_attempts = getattr(self, "context_seed_attempts", {})
        if kind == "close":
            process = self.processes.get(context)
            if process is None:
                return {"operation_id":request["operation_id"],"context_id":context,
                    "request_sha256":request["request_sha256"],"trace_id":"browser-close-empty",
                    "result":{"stopped":True}}
            graceful = False
            close_error = None
            if context not in self.poisoned and process.returncode is None:
                try:
                    reply = await asyncio.wait_for(self._exchange(context, "close", {}), timeout=13)
                    graceful = reply.get("stopped") is True
                    await asyncio.wait_for(process.wait(), timeout=3)
                except Exception as exc:
                    close_error = type(exc).__name__
                    self.poisoned.add(context)
            stopped = await self._wait_owned_exit(context, .1)
            forced = not stopped
            if not stopped:
                stopped = await self._terminate_owned(context)
            result = {"stopped": stopped, "driver_shutdown_confirmed": graceful,
                      "owned_group_exit_confirmed": stopped, "forced_cleanup": forced}
            if close_error:
                result["close_error_type"] = close_error
            self._record_lifecycle(context, "closed" if stopped else "shutdown_unconfirmed",
                                   shutdown=result)
            if stopped:
                self.closed_contexts.add(context)
                for mapping in (self.processes, self.context_paths, self.owned_groups,
                                self.context_tasks, self.context_uploads, self.context_observations,
                                self.context_fixture_validation, self.context_seed_attempts):
                    mapping.pop(context, None)
            return {"operation_id":request["operation_id"],"context_id":context,
                "request_sha256":request["request_sha256"],"trace_id":"browser-close-"+context[-12:],
                # ScaleExecution and AgentExecution deliberately require this
                # exact wire shape. Rich teardown details stay in lifecycle.
                "result":{"stopped": stopped}}
        if kind != "tool":
            raise RuntimeError("unsupported_browser_host_operation")
        evidence = safe_path(payload["evidence_path"])
        task = payload.get("task")
        if isinstance(task, dict):
            self.context_tasks.setdefault(context, copy.deepcopy(task))
        self.context_uploads.setdefault(context, set())
        self.context_observations.setdefault(context, [])
        self.context_fixture_validation.setdefault(context, [])
        name = payload["name"]
        arguments = payload["arguments"]
        if name == "seed_legacy_unknown":
            _authorize_legacy_seed(self.context_tasks.get(context), arguments,
                                   self.context_uploads[context],
                                   self.context_seed_attempts.get(context, False),
                                   legacy_seed_config=getattr(self, "legacy_seed_config", None))
        if context not in self.processes:
            legacy_req_id = (getattr(self, "legacy_seed_config", None) or {}).get("requirement_id")
            legacy_allowed = bool(
                legacy_req_id and legacy_req_id in self.context_tasks.get(context, {}).get("requirement_ids", [])
            )
            await self._exchange(context, "start", {"url":self.target_url, "chrome":self.chrome,
                "profile_dir":str(evidence / "browser-profile"), "evidence_path":str(evidence),
                "fixtures_dir":str(self.fixtures),
                "legacy_seed_allowed": legacy_allowed})
        if name not in {"observe", "click", "type", "upload", "upload_cancel",
                        "upload_save_failure", "seed_legacy_unknown", "scroll", "wait"}:
            raise RuntimeError("tool_not_allowlisted")
        if name == "seed_legacy_unknown":
            self.context_seed_attempts[context] = True
        action_started = time.monotonic()
        try:
            # A known nondispatched click rejection may obtain a fresh observe,
            # but both exchanges share this one action window, never 90 + 90.
            async def action():
                try:
                    result = await self._exchange(context, "act", {"name":name, "arguments":arguments})
                except RuntimeError as exc:
                    if name != "click" or str(exc) != "browser_action_failed:click_target_not_allowed_or_visible":
                        raise
                    if time.monotonic() - action_started >= self.EXCHANGE_TIMEOUTS["act"]:
                        raise TimeoutError("browser_action_window_after_deadline")
                    result = await self._exchange(context, "act", {"name":"observe", "arguments":{}})
                    result["facts"]["rejected_action"] = {"name": name, "reason": "target_not_allowed_or_visible",
                        "click_dispatched": False, "automatic_click_retry": False}
                    result["text"] = ("Click NOT dispatched: target was not allowed or visible. "
                        "This is a failed action, not a successful navigation. Re-observe the current "
                        "controls and choose a safe recovery; no click was retried.\n" + result["text"])
                return result
            result = await _with_timeout(action(), self.EXCHANGE_TIMEOUTS["act"])
            if time.monotonic() - action_started >= self.EXCHANGE_TIMEOUTS["act"]:
                raise TimeoutError("browser_action_window_after_deadline")
        except (TimeoutError, asyncio.CancelledError) as exc:
            if context not in self.poisoned:
                self.poisoned.add(context)
                self._record_lifecycle(context, "transport_uncertain",
                    error_type="ActionWindowTimeout" if isinstance(exc, TimeoutError) else "CancelledError",
                    action_elapsed_seconds=time.monotonic() - action_started,
                    action_timeout_seconds=self.EXCHANGE_TIMEOUTS["act"])
            raise
        if name in {"upload", "upload_cancel", "upload_save_failure"} and isinstance(arguments, dict) and isinstance(arguments.get("file"), str):
            fixture_name = arguments["file"]
            self.context_uploads[context].add(fixture_name)
            validation = self._validate_fixture_upload(fixture_name)
            if validation and validation not in self.context_fixture_validation[context]:
                self.context_fixture_validation[context].append(validation)
        if set(result) != {"text","facts","captures","checks"}:
            raise RuntimeError("browser_observation_contract")
        result["facts"]["fixture_uploads"] = sorted(self.context_uploads[context])
        result["facts"]["fixture_validation"] = copy.deepcopy(
            self.context_fixture_validation[context])
        task = self.context_tasks.get(context)
        if task and callable(getattr(self, "criteria_evaluator", None)):
            result["checks"] = self.criteria_evaluator(task, result["facts"], result["text"],
                self.context_uploads[context], self.context_observations[context])
        # Product sample content may contain synthetic-looking account handles.
        # Scrub identifiers before the observation crosses into the model/queue;
        # screenshots remain private, hash-bound evidence and are not uploaded.
        # Hashes are machine metadata, not free text. A hexadecimal digest can
        # contain a digit run which the privacy scrubber mistakes for a card.
        # Verify original capture bytes and never rewrite their identifiers.
        original_facts = result["facts"]
        result = {**result, **swarm.clean({key: result[key]
            for key in ("text", "facts", "checks")})}
        _preserve_driver_hashes(original_facts, result["facts"])
        self.context_observations[context].append({"text": result["text"], "facts": result["facts"]})
        for capture in result["captures"]:
            if not isinstance(capture, dict) or set(capture) != {"path", "sha256"}:
                raise RuntimeError("browser_capture_integrity:metadata")
            path = safe_path(evidence / capture["path"], evidence)
            if not path.is_file():
                raise RuntimeError("browser_capture_integrity:missing")
            if path.stat().st_mode & 0o077:
                raise RuntimeError("browser_capture_integrity:permissions")
            if byte_digest(path.read_bytes()) != capture["sha256"]:
                raise RuntimeError("browser_capture_integrity:digest")
        return {"operation_id":request["operation_id"],"context_id":context,
            "request_sha256":request["request_sha256"],"trace_id":"browser-"+request["operation_id"][-16:],
            "result":result}

    async def shutdown(self):
        outcomes = await asyncio.gather(*[
            self.call("close", {"operation_id":"shutdown-"+key[-12:],"context_id":key,
                "request_sha256":"0"*64,"deadline":time.time()+30,"payload":{}})
            for key in list(self.processes)], return_exceptions=True)
        return all(isinstance(x,dict) and x.get("result",{}).get("stopped") is True for x in outcomes)
