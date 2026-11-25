#!/usr/bin/env python3
"""Inspect and control a prepared persona queue without dispatching model calls."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uxresearch.canonical import EngineError
from uxpersonas.swarm_queue import Queue
from uxpersonas.scale_entry import preview, render_status, render_preview
from uxpersonas.scale_report import current_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "status", "pause", "resume", "cancel", "approve"))
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--actor")
    parser.add_argument("--consent-reference")
    parser.add_argument("--expires-at", type=float)
    parser.add_argument("--budget-microusd", type=int)
    args = parser.parse_args(argv)
    try:
        queue = Queue(args.run)
        if args.action == "preview":
            result = preview(queue)
        elif args.action == "approve":
            if any(v is None for v in (args.plan_sha256, args.actor, args.consent_reference, args.expires_at, args.budget_microusd)):
                parser.error("approve requires the exact plan, amount, user consent reference, actor and expiry")
            queue.authorize(plan_sha256=args.plan_sha256, actor=args.actor,
                consent_reference=args.consent_reference, expires_at=args.expires_at, budget_microusd=args.budget_microusd)
            result = current_report(queue)
        elif args.action in {"pause", "resume", "cancel"}:
            queue.control(args.action)
            result = current_report(queue)
        else:
            result = current_report(queue)
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.action == "preview":
            print(render_preview(result))
        else:
            print(render_status(result))
        return 0
    except EngineError as exc:
        print(json.dumps(dict(error=exc.issue), ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
