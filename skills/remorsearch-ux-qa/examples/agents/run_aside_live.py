"""Maintainer diagnostic using an already approved owned Aside route, never user tabs."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from uxpersonas.aside_cli import AsideCli
from uxresearch.storage import safe_path
from aside_live import run_owned


async def run(args):
    root = safe_path(Path(args.out).resolve())
    transport = root.with_name(root.name + "-transport")
    if not args.reviewed_owned_route:
        raise ValueError("Review the existing route and owned diagnostic tools before execution")
    if root.exists() or transport.exists():
        raise ValueError("Existing execution must be inspected; no implicit replay")
    transport.mkdir(mode=0o700)
    clients = []
    run_started = False
    try:
        for index in range(2):
            cli = AsideCli(alias=args.ssh_alias, profile=args.aside_profile,
                           journal=transport / ("context-" + str(index + 1)))
            clients.append(cli)
            neutral = await cli.start()
            opened = await cli.open_owned()
            print(json.dumps(dict(context=index + 1, session_id=cli.remote_session_id,
                                  neutral=neutral, owned_tabs=opened["ownedTabs"])), flush=True)
        run_started = True
        result = await run_owned(clients, root, node=args.node,
                                 playwright=args.playwright, browsers=args.browsers)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result["completion"] else 2
    finally:
        for cli in clients:
            if not cli.closed:
                # run_owned closes every constructed chat on a preflight failure.
                # Unknown in-flight work is never declared cancelled here.
                result = await cli.close_owned(model_quiescent=not run_started)
                print(json.dumps(dict(remaining_cleanup=result)), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ssh-alias", "aside-profile", "out", "node", "playwright", "browsers"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--reviewed-owned-route", action="store_true")
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
