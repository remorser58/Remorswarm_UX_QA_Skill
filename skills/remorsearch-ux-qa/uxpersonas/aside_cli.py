"""Documented Aside REPL over an explicitly reviewed SSH route.

Only the caller's newly opened REPL page may be used. No attach, account switch,
HTTP/model API, cookies, desktop input or settings changes exist in this module.
This is a transport restriction, not an OS/network sandbox.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import shlex
import time
import uuid

from uxresearch.canonical import canonical, digest
from uxresearch.storage import atomic

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MAX_OUTPUT = 2 * 1024 * 1024


class AsideError(RuntimeError):
    pass


def ssh_argv(alias, profile, verb="repl"):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", alias):
        raise AsideError("Invalid reviewed SSH alias")
    if not re.fullmatch(r"u[0-9]+:[a-f0-9-]{36}", profile):
        raise AsideError("An exact approved Aside profile is required")
    if verb not in {"repl", "guide", "guide repl", "skills list", "skills show aside", "--version"}:
        raise AsideError("Only documented read-only discovery and REPL commands are supported")
    command = "$HOME/.local/bin/aside --account " + shlex.quote(profile) + " --host local " + verb
    return ["ssh", "-tt", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", alias, command]


def response_from_output(raw, marker):
    """Accept exactly one standalone correlated JSON line, never a PTY echo."""
    text = ANSI.sub("", raw.decode("utf-8", errors="replace")).replace("\r", "")
    lines = [line[len(marker):] for line in text.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise AsideError("Missing or duplicate correlated REPL response")
    value = json.loads(lines[0])
    if not isinstance(value, dict) or set(value) != {"ok", "value"} or type(value["ok"]) is not bool:
        raise AsideError("Invalid REPL response envelope")
    if not value["ok"]:
        raise AsideError("Aside REPL rejected the owned operation: " + str(value["value"])[:600])
    return value["value"]


class AsideCli:
    """One process, one newly opened page, no implicit retry after dispatch."""
    def __init__(self, *, alias, profile, journal):
        self.argv = ssh_argv(alias, profile)
        self.journal = Path(journal)
        if self.journal.exists():
            raise AsideError("Existing transport journal must be inspected, never restarted implicitly")
        self.journal.mkdir(parents=True, mode=0o700)
        self.process = None
        self.lock = asyncio.Lock()
        self.sequence = 0
        self.uncertain = False
        self.owned = False
        self.closed = False
        self.page_closed = False
        self.records = []
        self.remote_session_id = None
        self.process_id = None
        self.save()

    def save(self):
        state = dict(schema="remorsearch-aside-cli.v1", argv=self.argv,
                     owned=self.owned, closed=self.closed, uncertain=self.uncertain,
                     operations=self.records, remote_session_id=self.remote_session_id,
                     process_id=self.process_id, page_closed=self.page_closed,
                     process_returncode=self.process.returncode if self.process else None)
        atomic(self.journal / "state.json", canonical(dict(payload=state, sha256=digest(state))))

    async def _until_prompt(self, timeout):
        async def read():
            output = bytearray()
            while True:
                chunk = await self.process.stdout.read(8192)
                if not chunk:
                    raise AsideError("Aside REPL ended before confirming the operation")
                output.extend(chunk)
                if len(output) > MAX_OUTPUT:
                    raise AsideError("Aside output exceeded its bound")
                if ANSI.sub("", output.decode("utf-8", errors="replace")).endswith("repl > "):
                    return bytes(output)
        return await asyncio.wait_for(read(), timeout)

    async def start(self):
        if self.process is not None:
            raise AsideError("Transport already started")
        self.process = await asyncio.create_subprocess_exec(
            *self.argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, limit=MAX_OUTPUT)
        # Startup banner may contain account identity. Never persist/return it.
        banner = await self._until_prompt(20)
        identity = re.search(rb"/sessions/[0-9]{4}-[0-9]{2}-[0-9]{2}_([A-Za-z0-9_-]+)", banner)
        if not identity:
            self.uncertain = True
            self.save()
            raise AsideError("CLI did not identify its newly created REPL session")
        self.remote_session_id = identity.group(1).decode("ascii")
        self.process_id = self.process.pid
        self.save()
        state = await self.rpc("return {pageBound: typeof page !== 'undefined' && page !== null, ownedTabs: tabs.length};",
                               label="neutral-session")
        if state != {"pageBound": False, "ownedTabs": 0}:
            self.uncertain = True
            self.save()
            raise AsideError("REPL was not neutral; no existing page may be attached")
        return state

    async def rpc(self, body, *, label, timeout=20, cleanup=False):
        if self.process is None or self.process.returncode is not None:
            raise AsideError("Transport is not connected")
        async with self.lock:
            if self.uncertain and not cleanup:
                raise AsideError("Prior dispatch is uncertain; automatic retries are forbidden")
            self.sequence += 1
            marker = "REMORSEARCH_ASIDE_" + uuid.uuid4().hex + ":"
            # Body is reviewed adapter code, never model-supplied JavaScript.
            script = "try { const v = await (async () => {" + body + "})(); console.log(" + json.dumps(marker) +                      "+JSON.stringify({ok:true,value:v})); } catch(e) { console.log(" + json.dumps(marker) +                      "+JSON.stringify({ok:false,value:String(e)})); }"
            record = dict(sequence=self.sequence, label=label, request_sha256=digest(script),
                          started_at=time.time(), status="intent")
            self.records.append(record)
            self.save()
            try:
                self.process.stdin.write(script.encode() + b"\n")
                await self.process.stdin.drain()
                raw = await self._until_prompt(timeout)
                value = response_from_output(raw, marker)
                record.update(status="done", ended_at=time.time(), response_sha256=digest(value))
                self.save()
                return value
            except BaseException:
                self.uncertain = True
                record.update(status="uncertain", ended_at=time.time())
                self.save()
                raise

    async def open_owned(self):
        if self.owned or any(r["label"] == "open-owned" for r in self.records):
            raise AsideError("A context can open only one fresh page")
        value = await self.rpc(
            "await openTab('https://chatgpt.com'); const s = await snapshot(page, {interactive:true}); "
            "return {url:page.url(), ownedTabs:tabs.length, tree:s.tree};", label="open-owned", timeout=30)
        if value.get("ownedTabs") != 1 or not value.get("url", "").startswith("https://chatgpt.com/"):
            self.uncertain = True
            self.save()
            raise AsideError("New page ownership could not be confirmed")
        self.owned = True
        self.save()
        return value

    async def close_owned(self, *, model_quiescent):
        if self.closed:
            return {"stopped": bool(model_quiescent)}
        stopped = False
        try:
            if self.owned and not self.page_closed:
                result = await self.rpc("await closeTab(page); return {ownedTabs:tabs.length};",
                                        label="close-owned", timeout=8, cleanup=True)
                self.page_closed = result == {"ownedTabs": 0}
                self.save()
            stopped = self.page_closed and model_quiescent
            if self.process and self.process.returncode is None:
                self.process.stdin.write(b"exit\n")
                await self.process.stdin.drain()
                await asyncio.wait_for(self.process.wait(), 5)
            stopped = stopped and self.process is not None and self.process.returncode == 0
        finally:
            self.closed = stopped
            self.save()
        return {"stopped": stopped}
