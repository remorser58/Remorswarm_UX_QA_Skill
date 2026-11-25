"""Local persona library and host-driven UX task orchestration."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from uxresearch.canonical import EngineError
from uxresearch.storage import read_json
from .library import Library


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("configure", "select", "seed-input", "seed-catalog"):
        control = commands.add_parser(name, help="PRD-bound choices and attributed Korean seed profiles; no execution")
        if name != "seed-catalog":
            control.add_argument("--input", type=Path, required=True)
        if name == "select":
            control.add_argument("--choice", type=Path, required=True)
    for name in ("start", "status"):
        entry = commands.add_parser(name, help="Prepare reviewed source and explain existing QA results" if name == "start" else "Recheck a prepared workspace without rerunning tasks")
        entry.add_argument("--work", type=Path, required=True, help="Independent workspace; new or empty for first use")
        if name == "start":
            entry.add_argument("--source", type=Path, required=True, help="Approved source folder or saved owned pilot folder")
            entry.add_argument("--include", action="append", help="Exact relative file already reviewed by the host; repeat for each file, no glob or automatic discovery")
        entry.add_argument("--format", choices=("text", "json"), default="text")
    run = commands.add_parser("run", help="Execute an explicitly reviewed owned local adapter and report current observations")
    run.add_argument("--work", type=Path, required=True)
    run.add_argument("--library", type=Path, help="Explicit existing reviewed persona library; never the implicit global library")
    run.add_argument("--input", type=Path, help="Host-reviewed fixed goals, criteria and copied Python or static browser adapter")
    run.add_argument("--allow-reviewed-local-runner", action="store_true", help="Host attests review of exact owned code/input; this is not an OS sandbox")
    run.add_argument("--reviewed-research-run", action="append", type=Path, help="Exact existing research directory already reviewed by the host; repeat up to four; no discovery or collection")
    run.add_argument("--format", choices=("text", "json"), default="text")
    default = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "remorsearch-ux-qa/personas"
    for name in ("import", "import-research", "list", "retire", "reuse", "prune", "plan", "claim", "record", "report", "retry", "settle", "receipt-starter", "compare", "replay"):
        sub = commands.add_parser(name)
        sub.add_argument("--library", type=Path, default=default, help="private persistent persona directory")
        if name in {"import", "import-research", "plan", "record"}:
            sub.add_argument("--input", type=Path, required=True)
        if name == "import-research":
            sub.add_argument("--research-run", type=Path, required=True,
                             help="existing private research run with a current committed persona export")
        if name in {"plan", "claim", "record", "report", "retry", "settle", "receipt-starter", "compare", "replay"}:
            sub.add_argument("--run", type=Path, required=True)
        if name in {"compare", "replay"}:
            sub.add_argument("--baseline", type=Path, required=True, help="existing baseline run")
            sub.add_argument("--format", choices=("text", "json"), default="text",
                             help="readable output by default; JSON for host integrations")
        if name == "replay":
            sub.add_argument("--build-id", required=True, help="new candidate build identifier")
            sub.add_argument("--artifact", type=Path, required=True, help="local candidate artifact with changed bytes")
            sub.add_argument("--isolation-id", required=True, help="host-reviewed isolated fixture context")
            sub.add_argument("--confirm-starting-state", action="store_true",
                             help="attest equivalent starting data, device and input conditions; not independent proof")
            sub.add_argument("--confirm-isolation", action="store_true",
                             help="attest owned isolated fixtures; verify the returned assignments before claim, no new permission")
        if name in {"retire", "reuse"}:
            sub.add_argument("--product", required=True)
            sub.add_argument("--persona", required=True)
        if name == "list":
            sub.add_argument("--product")
        if name == "reuse":
            sub.add_argument("--revision", type=int)
        if name == "retire":
            sub.add_argument("--reason", required=True)
        if name == "claim":
            sub.add_argument("--worker", required=True)
            sub.add_argument("--task")
        if name == "receipt-starter":
            sub.add_argument("--claim", type=Path, required=True,
                             help="private saved current claim; produces a non-recordable draft without renewing the lease")
        if name == "retry":
            sub.add_argument("--task", required=True)
            sub.add_argument("--reconciliation", type=Path,
                             help="explicit host inspection attestation for an uncertain fixture-write outcome")
        if name == "settle":
            sub.add_argument("--task", required=True)
            sub.add_argument("--inspection", type=Path, required=True,
                             help="actual stopped-worker and fixture-state inspection; close without retry")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command in {"start", "status", "run"}:
        from . import workspace
        try:
            if args.command == "run":
                from . import local_run
                result = local_run.execute(args.work, library_path=args.library, input_path=args.input,
                                           approved=args.allow_reviewed_local_runner,
                                           reviewed_research_runs=args.reviewed_research_run)
            else:
                result = (workspace.prepare(args.source, args.work, reviewed_files=args.include,
                      progress=(lambda message: print(message, file=sys.stderr)) if args.format == "text" else None)
                      if args.command == "start" else workspace.status(args.work))
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
                  else workspace.render(result) + "\n보고서: " + result["report_path"])
            # A measured browser task scope can pass; product readiness stays false.
            return (0 if result.get("task_scope_passed") else 1) if args.command == "run" else 0
        except (EngineError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            result = workspace.error_result(exc)
            print(json.dumps(result, ensure_ascii=False) if args.format == "json"
                  else result["issue"]["reason"] + "\n다음 단계: " + result["issue"].get("next_step", "호스트가 기존 근거와 범위를 확인합니다."), file=sys.stderr)
            return 2
    try:
        if args.command in {"configure", "select", "seed-input", "seed-catalog"}:
            from . import product_controls as controls
            if args.command == "seed-catalog":
                result = controls.seed_catalog()
            elif args.command == "seed-input":
                result = controls.seed_input(read_json(args.input))
            elif args.command == "select":
                result = controls.select(read_json(args.input), read_json(args.choice))
            else:
                result = controls.propose(read_json(args.input))
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            return 0
        if args.command == "import-research":
            from .research_intake import validate_paths
            validate_paths(args.library, args.research_run)
            intake_mapping = read_json(args.input, private=True)
        if args.command in {"receipt-starter", "compare", "replay"}:
            # These commands consume existing personas; never initialize a missing library.
            from uxresearch.storage import read_bytes, safe_path
            if not all(safe_path(args.library / name).is_file() for name in ("library.json", "engine.lock")):
                reason = ("An existing persona library and current claim are required." if args.command == "receipt-starter"
                          else "An existing persona library is required.")
                raise EngineError("persona_missing", reason)
            if args.command in {"compare", "replay"}:
                for name in ("library.json", "engine.lock"):
                    read_bytes(args.library / name, private=True)
                if args.command == "replay" and safe_path(args.library).stat().st_mode & 0o077:
                    raise EngineError("unsafe_mode", "Replay requires a private existing persona library directory.")
        with Library(args.library) as library:
            if args.command == "import":
                result = library.import_profiles(read_json(args.input))
            elif args.command == "import-research":
                from .research_intake import import_research
                result = import_research(library, args.research_run, intake_mapping)
            elif args.command == "list":
                result = library.list(args.product)
            elif args.command == "retire":
                result = library.retire(args.product, args.persona, args.reason)
            elif args.command == "reuse":
                result = library.get(args.product, args.persona, args.revision)
            elif args.command == "prune":
                result = library.prune()
            else:
                from . import swarm
                if args.command == "plan":
                    result = swarm.create_plan(library, args.run, read_json(args.input))
                elif args.command == "replay":
                    from .replay import prepare
                    result = prepare(library, args.baseline, args.run, build_id=args.build_id,
                                     artifact_path=args.artifact, isolation_id=args.isolation_id,
                                     confirm_starting_state=args.confirm_starting_state,
                                     confirm_isolation=args.confirm_isolation)
                elif args.command == "claim":
                    result = swarm.claim(library, args.run, args.worker, args.task)
                elif args.command == "receipt-starter":
                    result = swarm.receipt_starter(library, args.run, read_json(args.claim, private=True))
                elif args.command == "record":
                    result = swarm.record(library, args.run, read_json(args.input))
                elif args.command == "retry":
                    result = swarm.retry(library, args.run, args.task,
                                         reconciliation=read_json(args.reconciliation) if args.reconciliation else None)
                elif args.command == "settle":
                    result = swarm.settle(library, args.run, args.task, read_json(args.inspection))
                elif args.command == "compare":
                    from .comparison import compare
                    result = compare(library, args.baseline, args.run)
                else:
                    result = swarm.report(library, args.run)
        if args.command in {"compare", "replay"} and args.format == "text":
            if args.command == "compare":
                from .comparison import render_text
            else:
                from .replay import render_text
            print(render_text(result))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if ((args.command == "prune" and result["blockers"])
                     or (args.command == "compare" and not result["comparison_complete"])) else 0
    except EngineError as exc:
        print(json.dumps({"result": "blocked", "issue": exc.issue}, ensure_ascii=False), file=sys.stderr)
        return exc.exit_code or 2
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"result": "blocked", "issue": {"code": "input_or_io", "reason": "Input or local state is missing, malformed or unsafe."}}), file=sys.stderr)
        return 2
