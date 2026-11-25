# Python 3.10 browser timeout compatibility

## Scope and identity

- Base: `e8452f95778c4e89d27289acb9a585461755ce55` (PR #8).
- Final browser-host SHA-256: `26f3025294b8ddd54678e5c6ab916bb90dc619dae11d24d8f6e005684609c918`.
- OCI runtime used: Python 3.12.3. No installed Python 3.10 executable was found in PATH or the checked system, pyenv and uv runtime locations. **Actual Python 3.10 execution remains unverified locally.**
- No dependencies, model calls, live cohort runs, historical evidence changes, pushes or installations.

## Change and rationale

The two deadline scopes previously required `asyncio.timeout`, introduced in Python 3.11. The host now retains that native path when available and otherwise uses the existing standard-library `asyncio.wait` / owned-task pattern. The fallback explicitly raises built-in `TimeoutError`, so Python 3.10's distinct `asyncio.TimeoutError` cannot evade the action-window handler. External cancellation stays `CancelledError`; cancellation cleanup is drained and concurrent task errors are consumed without replacing caller cancellation.

The IO coroutine combines stdin drain and stdout reply under one exchange budget. The action coroutine keeps the click rejection plus follow-up observe under one overall action budget. Existing late-response checks, poisoned-channel rejection, no replay, owned process cleanup and exact close-result shape remain intact. No deadline or existing assertion was relaxed.

A direct `wait_for` replacement was not adopted because CPython documents a cancellation/completion race in the older implementation. Sources reviewed: [Python 3.10 waiting primitives](https://docs.python.org/3.10/library/asyncio-task.html#waiting-primitives), [Python 3.12 timeout API](https://docs.python.org/3.12/library/asyncio-task.html#timeouts), [CPython issue #86296](https://github.com/python/cpython/issues/86296). This uses standard-library APIs, not vendored upstream code.

## Executed checks

All commands below ran in the isolated worktree with `PYTHONDONTWRITEBYTECODE=1` and Python 3.12.3 unless indicated.

| Check | Observed result |
| --- | --- |
| Before-change `python3 -m unittest discover -s tests -p 'test_scale_browser_*.py'` | Exit 0, 23 tests, 5.209 seconds |
| Final same focused command | Exit 0, 35 tests, 5.789 seconds |
| `python3 skills/remorsearch-ux-qa/scripts/smoke_loop.py` | Exit 0, passed; 18 authored checks, no live integrations |
| `python3 skills/remorsearch-ux-qa/examples/research/run_fixture.py` | Exit 0, passed; invented content, zero network requests |
| `python3 scripts/release_files.py` | Exit 0; 284 distribution files |
| `git diff --check` | Exit 0 |

The focused suite includes the original lifecycle/process-group and close-contract tests, both native and forced-missing-`asyncio.timeout` action deadline tests, shared drain/reply budget, and real Task.cancel cases. The cancellation cases cover simultaneous reply completion, simultaneous overall-action completion, and reader cleanup that raises another exception. They assert cancellation, channel poisoning, no further dispatch, no admitted observation and completed reader cleanup.

During development, an all-version task-based prototype produced two focused-suite failures in the close-contract fixture (one of two sessions uncertain). Its inherited 20 ms synthetic close budget was not changed. The final implementation retains the original native in-task path on 3.11+. A separate diagnostic forcing the fallback through the existing close-contract scenario completed both sessions, with measured close exchanges of 2.44 ms and 1.40 ms. This diagnostic is not an actual Python 3.10 interpreter check or proof against all scheduler loads.

## Remaining verification

- The exact commit still needs the existing Python 3.10 CI matrix; local forced fallback is not an interpreter substitute.
- A full-suite run started before the final native-path adjustment is not counted as a final-source pass. Its output/termination must be checked separately.
- Full release/browser validation was not rerun: this worktree has no prepared pinned browser dependencies, and PATH Node is v24.20.0 rather than Node 22. No dependency installation was attempted.
- These authored checks do not establish live UX improvement, historical cohort results or product readiness.
