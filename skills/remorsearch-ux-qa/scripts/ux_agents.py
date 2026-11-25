#!/usr/bin/env python3
"""Diagnose optional agent execution and read its current evidence-backed report."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uxpersonas.agent_run import doctor, render
from uxpersonas.library import Library
from uxpersonas import swarm
from uxresearch.canonical import EngineError, digest
from uxresearch.storage import read_json, safe_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("doctor")
    probe.add_argument("--format", choices=("text", "json"), default="text")
    report = sub.add_parser("report")
    report.add_argument("--library", required=True, type=Path)
    report.add_argument("--run", required=True, type=Path)
    report.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor()
            text = ("선택적 LangGraph 실행 환경: " + ("준비됨" if result["runtime_ready"] else "미준비") +
                    "\n실제 모델 연결: 호스트 어댑터 확인 필요\n기존 기본 명령은 그대로 사용할 수 있습니다.")
            code = 0 if result["runtime_ready"] else 2
        else:
            root = safe_path(args.run)
            if not (safe_path(args.library) / "library.json").is_file():
                raise EngineError("persona_missing", "Existing reviewed persona library is required.")
            with Library(args.library) as library:
                current = swarm.report(library, root)
            result = read_json(root / "agent-runtime/report.json", private=True)
            if any(result.get(k) != current.get(k) for k in current):
                raise EngineError("stale_report", "Stored execution report no longer matches current validated bindings and evidence.")
            envelope = read_json(root / "agent-runtime/state.json", private=True)
            if digest(envelope.get("payload")) != envelope.get("sha256"):
                raise EngineError("execution_integrity", "Execution journal changed.")
            if digest(result) != envelope["payload"].get("report_sha256"):
                raise EngineError("execution_integrity", "Execution report does not match its journal.")
            text, code = render(result), 0
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else text)
        return code
    except (EngineError, OSError, ValueError, KeyError) as exc:
        issue = exc.issue if isinstance(exc, EngineError) else {"code": "input_or_io", "reason": "Required private evidence is unavailable."}
        print(json.dumps({"result": "blocked", "issue": issue}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
