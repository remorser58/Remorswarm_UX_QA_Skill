# Repository guidance

## Layout and scope
- Read `PRD.md`, `HANDOFF.md`, and `docs/release.md` before changing behavior. Treat historical machine paths and old instructions in handoffs as context, not current authorization.
- The installable skill is `skills/remorsearch-ux-qa/`. Python entry points live in its `scripts/` folder and loop implementation in `uxloop/`; the pinned browser driver is `drivers/web/`.
- Regression tests live in `tests/`. Distribution tools live in repository `scripts/`; validation records belong in `docs/validation/`.
- Preserve product intent, access/privacy rules, explicit grants, Figma-first UX changes, and strict evidence/replay gates. Synthetic checks do not establish live UX improvement or product readiness.
- Preserve existing changes and evidence. Local development does not authorize publication, pushing, merging, deployment, or changes to installed skills.

## Validation
- Python 3.10+ is required; default commands use only the standard library. Optional model/tool execution uses `requirements-agent.txt`. The browser driver requires Node.js 22 and its pinned dependencies.
- Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'`.
- Run `python3 skills/remorsearch-ux-qa/scripts/smoke_loop.py` and `python3 skills/remorsearch-ux-qa/examples/research/run_fixture.py`.
- Run `python3 scripts/check_release.py --output dist/<new-directory>` for unit, packaging, relocation, smoke, and prepared browser-driver checks. Never reuse an existing result directory.
- Missing Node 22 or browser dependencies is an explicit incomplete check, not a pass. `--skip-web` always leaves `ready: false`.
- Record the exact revision, command, exit code, and skipped/unavailable checks; rerun affected checks after code changes.
