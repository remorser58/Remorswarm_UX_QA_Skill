"""Actual owned Chromium tools with authored decisions, not live model execution."""
from __future__ import annotations
import argparse
import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture
from uxpersonas.agent_run import execute, Limits
from uxresearch.canonical import byte_digest, canonical
from uxresearch.storage import atomic, read_bytes, safe_path

source_spec = importlib.util.spec_from_file_location("owned_page", fixture.SKILL / "examples/journey/browser_fixture.py")
owned_page = importlib.util.module_from_spec(source_spec)
source_spec.loader.exec_module(owned_page)


class BrowserFixtureHost(fixture.FixtureHost):
    def __init__(self, source, *, node, playwright, browsers, parallel=True):
        super().__init__(parallel)
        self.source = safe_path(source)
        self.source_hash = byte_digest(read_bytes(source))
        self.node, self.playwright, self.browsers = map(lambda p: str(Path(p).resolve()), (node, playwright, browsers))
        self.processes, self.locks, self.transport_count = {}, {}, 0
        self.driver = Path(__file__).with_name("browser_tools.mjs")
        self.info.update(name="owned-browser-fixture", adapter_sha256=byte_digest(
            read_bytes(self.driver) + read_bytes(Path(__file__)) + read_bytes(Path(fixture.__file__))))
        self.runtime_receipts = []

    async def exchange(self, context_id, kind, payload):
        async with self.locks.setdefault(context_id, asyncio.Lock()):
            process = self.processes[context_id]
            self.transport_count += 1
            ident = self.transport_count
            process.stdin.write(json.dumps(dict(id=ident, kind=kind, payload=payload)).encode() + b"\n")
            await process.stdin.drain()
            while True:
                raw = await process.stdout.readline()
                if not raw or len(raw) > 65536:
                    raise RuntimeError("Browser transport stopped")
                response = json.loads(raw)
                # A timed-out action may precede the correlated close response.
                if response.get("id") != ident:
                    continue
                if "error" in response:
                    raise RuntimeError("Owned browser action failed")
                return response["result"]

    async def result(self, kind, request):
        context_id, payload = request["context_id"], request["payload"]
        if kind == "close":
            if context_id not in self.processes:
                return {"stopped": True}
            process = self.processes[context_id]
            try:
                closed = await self.exchange(context_id, "close", {})
                process.stdin.close()
                await asyncio.wait_for(process.wait(), 1)
                return {"stopped": closed == {"stopped": True} and process.returncode == 0}
            except Exception:
                if process.returncode is None:
                    process.terminate()
                return {"stopped": False}
        if kind != "tool":
            return await super().result(kind, request)
        if context_id not in self.processes:
            self.processes[context_id] = await asyncio.create_subprocess_exec(
                self.node, str(self.driver), cwd=payload["evidence_path"],
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin", "REMORSEARCH_AGENT_PLAYWRIGHT": self.playwright,
                     "PLAYWRIGHT_BROWSERS_PATH": self.browsers})
            self.runtime_receipts.append(await self.exchange(context_id, "start",
                dict(source=str(self.source), sha256=self.source_hash)))
        value = await self.exchange(context_id, "act", dict(
            name=payload["name"], value=payload["arguments"].get("value"),
            target="#reject-broken" if payload["task"]["persona_id"] == "PER-RETURN" else "#reject-control"))
        state = self.states.setdefault(context_id, dict(stage="empty", note="", saved="", retained=None))
        state["note"], state["saved"] = value["note"], value["saved"]
        checks = []
        if payload["name"] == "enter":
            state["stage"] = "corrected" if state["stage"] == "rejected" else "entered"
        elif payload["name"] == "reject":
            state.update(stage="rejected", retained=value["note"] == "Owned draft")
            checks = [dict(kind="success", index=0, status="passed" if state["retained"] else "failed")]
        elif payload["name"] == "save":
            state["stage"] = "saved"
            checks = [dict(kind="recovery", index=0, status="passed" if value["saved"] == "Owned corrected note" else "failed")]
        return dict(text="Observed owned browser: " + value["feedback"], facts=copy.deepcopy(state),
                    captures=[value["capture"]], checks=checks)


async def main(args):
    root = fixture.build(args.out)
    source = root / "owned-page.html"
    atomic(source, owned_page.PAGE.encode())
    # Bind the actual HTML as the tested build, before any dispatch.
    with fixture.Library(root / "library") as library:
        from uxpersonas import swarm
        state = swarm._load(root / "run", library)
        state["build"] = dict(id="owned-browser-build", artifact_path=str(source), sha256=byte_digest(read_bytes(source)))
        swarm._save(root / "run", state)
        host = BrowserFixtureHost(source, node=args.node, playwright=args.playwright, browsers=args.browsers, parallel=not args.serial)
        report = await execute(library, root / "run", host, fixture.TOOLS, limits=Limits(call_seconds=30), reviewed=True)
        count = len(host.calls)
        again = await execute(library, root / "run", host, fixture.TOOLS, limits=Limits(call_seconds=30), reviewed=True)
        assert count == len(host.calls) and report == again
    diagnostic = dict(actual_browser_execution=True, actual_model_execution=False,
        decision_source="authored_fixture", source_sha256=host.source_hash,
        runtime_receipts=host.runtime_receipts, readback_without_redispatch=True,
        report=report, fixture_passed=report["counts"]["passed"] == 1 and report["counts"]["failed"] == 1)
    atomic(root / "diagnostic.json", canonical(diagnostic))
    print(json.dumps({k: v for k, v in diagnostic.items() if k != "report"}, indent=2))
    return 0 if diagnostic["fixture_passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--node", required=True, type=Path)
    parser.add_argument("--playwright", required=True, type=Path)
    parser.add_argument("--browsers", required=True, type=Path)
    parser.add_argument("--serial", action="store_true")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
