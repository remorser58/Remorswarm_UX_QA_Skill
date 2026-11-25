# Post-trial portable launcher

`run.cjs` is new operational tooling, not part of the frozen PE-1 target or original comparison. The six inputs in `SHA256.json` are unchanged. The original `harness.cjs` still has its historical sibling-worktree dependency default; this launcher overrides it explicitly. These checks do not complete, repair, or rerun the historical comparison.

## Requirements and launch

Use Node.js 22 and an already prepared Playwright dependency/browser. No installation occurs. By default the launcher resolves `skills/remorsearch-ux-qa/drivers/web/node_modules/playwright` relative to this repository, independent of the caller's current directory. Alternatively set `PLAYWRIGHT_MODULE` to an existing absolute Playwright module directory or entry file. Relative overrides are resolved against the caller's current directory.

```sh
EVIDENCE_DIR=/absolute/path/to/new-run node benchmarks/persona-effectiveness/run.cjs
```

The evidence directory must not exist, even empty; its parent must already exist. Creation is exclusive and stale/colliding paths are rejected without overwriting. In a checkout without prepared dependencies, use:

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/prepared/node_modules/playwright \
EVIDENCE_DIR=/absolute/path/to/new-run \
node benchmarks/persona-effectiveness/run.cjs
```

Send JSON-lines commands as documented in the frozen README. For example:

```json
{"op":"goto","case":"K4M"}
{"op":"observe"}
```

Keep the launcher process/session alive while using the harness. It owns a loopback-only server on an OS-assigned ephemeral port, checks its HTTP response before starting the browser, and waits for the harness's ready message before forwarding input. The readiness check does not navigate the browser or consume a UI action. It never injects, retries, changes, or resets input commands or the frozen harness budget (60 attempted actions; 12 minutes from first counted interaction). Closing stdin ends the harness after queued commands, then closes the server. SIGINT/SIGTERM and startup failures close only this launcher's owned subprocess/server. Standard Playwright launches a fresh isolated headless browser, never a personal profile. A 30-second browser-readiness timeout fails the run rather than silently restarting it.

## Evidence and interpretation

- `lifecycle.jsonl`: wall-clock timestamps and monotonic milliseconds since launcher start, server readiness/port, harness readiness/exit, each raw forwarded command with a sequence, outputs, EOF and shutdown. Forwarding time is not necessarily UI execution start when commands are queued.
- `stdout.jsonl`, `stderr.txt`: harness output and errors.
- `browser/actions.jsonl` and PNGs: the frozen harness's actual action outcomes and screenshots.

A failed UI operation is still counted by the frozen harness. A launcher exit of zero means the harness completed, not that every UI action or obligation passed: inspect individual `ok` fields. Do not treat setup time as browser interaction time or claim exact per-action execution duration from forwarding timestamps. This runner provides lifecycle evidence, not OS crash recovery: SIGKILL, machine loss, or filesystem failure can prevent final cleanup records. Keep synthetic inputs only; raw commands are recorded.

The Mac environment used for validation required approved unsandboxed execution for isolated Chromium startup; normal sandbox launch had a MachPort permission failure. A permission failure is not a passing UI check. No dependencies, permissions, global browser settings, or existing servers are changed by this launcher.

## Focused tests

```sh
node --test benchmarks/persona-effectiveness/tests/runner.test.cjs
```

Tests cover loopback readiness, missing dependencies, mandatory fresh evidence, no-clobber, and an explicitly injected browser-launch error with owned-server cleanup. This failure stub does not represent a successful browser run. Actual browser validation must use the prepared Playwright module and a separate fresh evidence directory.
