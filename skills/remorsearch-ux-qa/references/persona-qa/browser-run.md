# Run saved-persona tasks in an owned static browser

This is the bounded browser alternative to [local-run.md](local-run.md).
The host prepares it from the user's product folder and ordinary-language goal.
The user does not write a scenario, manifest, receipt, runtime path or lease.

## 1. Choose the supported surface

Read the PRD, relevant source and existing persona/research evidence first.
Use this path for reviewed, owned static HTML/CSS/JavaScript and synthetic inputs.
Reuse the original Library and current research gates. The installed driver
operates fixed tasks; it does not invent research or role-play an autonomous user.

A production account, backend, arbitrary URL, existing localhost service, user
browser, persistent profile or unreviewed executable is outside this path.
If a product requires those surfaces, report that exact gap and continue the
authorized analysis. Do not turn a backend into a fake successful fixture.

Review the actual page behavior and every included file. The runtime serves only
the frozen file bytes at https://remorsearch.invalid/. HTTP/WebSocket requests
have no forwarding fallback, RTC/WebTransport constructors are disabled before
page code, and unexpected popups/downloads block the session. These controls are
not an OS network sandbox or permission to execute untrusted repository code.
No package installation happens inside a journey.

## 2. Prepare and execute

Use the existing start/run/status commands. The host selects each exact relative
file through repeated --include options, chooses current saved persona versions
and writes the plan from the inspected product goal. Keep source, original
Library, optional reviewed research and execution workspace separate.

The browser plan has the same five fields as the Python plan:

- schema_version: ux-journey-browser-plan.v1
- product_id: current Library product
- runner: reviewed copied JSON adapter, not a command or executable
- timeout_seconds: integer 1–30
- tasks: existing swarm task records, including predeclared PRD obligations

The adapter is ux-journey-browser-adapter.v1 with a journeys array. Each item has
exactly task_id, scenario, device_id and criteria. Every task appears once.

Reuse the existing ergo-scenario.v1 schema. Set a reviewed static HTML URL at the
fixed origin, one device ID, the exact task goal and 1–16 explicit actions.
Omit surface.build_id; the host engine injects the current prepared-build hash.
Only measured success.task_checks are accepted. Each check has an explicit
1-based after_step, and every success/recovery criterion maps one-to-one through
{kind, index, check_id}. Unmapped checks and criteria are rejected before claim.
Action input and check values must be owned synthetic data.

The existing driver defines exact value/text/checked comparisons, from_step,
redaction and capture timing. Native success is reconstructed from those
checkpoints. A later successful recovery never erases an earlier mismatch.
Missing targets, unvisited checkpoints and targets absent/offscreen/obscured or
with unsupported visible geometry remain not_run. A DOM match alone does not
prove the user saw a successful result, understood it or found the task easy.

The host's --allow-reviewed-local-runner flag records existing source/input
review authority. It does not grant new permissions or require another user
approval when that scope is already authorized.

## 3. Runtime and finite ownership

Use already prepared Node 22, Playwright 1.56.1 and its matching Chromium.
The host can select an existing Node binary with REMORSEARCH_JOURNEY_NODE and
existing package/cache locations with NODE_PATH and PLAYWRIGHT_BROWSERS_PATH.
Canonicalize those locations at preflight. The initial probe launches no browser.

Freeze the resolved Node, driver, Chromium executable, Playwright/core package
roots and hashes before dispatch. Each execution loads the exact pinned package
and core, with a sanitized environment; it does not inherit browser attachment
endpoints, Node options, credentials or the user's home. Runtime changes block
new dispatch without consuming a new attempt. Historical readback validates the
saved evidence without requiring the old runtime to remain installed.

The existing limit is 1–16 tasks, serial dispatch, one attempt per task and at
most 240 seconds of configured browser time. One owned headless Chromium is
closed before another task starts. Browser close and process termination are
required; parent timeout allows up to five seconds for graceful cleanup.
If closure cannot be confirmed, keep the intent and stop subsequent dispatch.
Never signal stored PIDs after restart or reset attempts through a new workspace.

Limits also include 64 static files, 2 MiB per file, 16 MiB total, 64 task checks,
256 KiB request/pipe output and 64 MiB native browser evidence per task.
Typing defaults to zero per-character delay in this finite scripted path.

## 4. Evidence, failure and readback

The engine binds each native run to task, operation, attempt, build, scenario
and exact persona/profile/PRD revision. Step before/after anchors, measured
checkpoints, snapshot identities, reviewed page URLs and PNG hashes are checked.
The existing swarm receipt gate decodes PNGs and requires log/capture evidence.
The independent deterministic audit reconstructs the receipt from stored native
evidence; it is not an independent human/model evaluation of the product.

Confirmed-cleanup timeout or cancellation may preserve earlier valid checkpoint
failures. An incomplete tail action and unvisited recovery remain unobserved.
A stopped/partial run cannot pass, even if its earlier checks passed.

Completed run/start/status calls read back the same content-derived reports
without browser execution or file rewrites. The current report lists exact saved
personas, criterion outcomes, reproduction actions, evidence paths, duplicates,
conflicts, gaps and next steps. It sets real_user_evidence and product_ready to
false. ui_observed means admissible owned static browser observations exist.

run exits 0 only when the measured task scope, declared requirements and audit
are all complete and passing; this is not product readiness. Failure, conflict,
partial or Python-only scope exits 1. Invalid input/runtime/preparation exits 2.
Status exits 0 for a generated report regardless of the QA verdict.

## 5. Installed diagnostic

Run examples/journey/run_browser_fixture.py --out NEW_DIRECTORY with an already
prepared runtime. Add --research to reuse the bundled invented research export
through the real merge/gate/Library path. Existing directories are refused.

The diagnostic uses an intentionally defective input-retention path and a normal
control. Expected product-task outcomes are failure 1 / pass 1. It verifies
the earlier failure survives final recovery, original source/Library/research
preservation, and identical readback with no redispatch.

This is real browser execution of an authored synthetic page with known answers.
It is not live-product execution, public community acquisition, actual participants,
an effectiveness comparison or measured real-user UX improvement.
