# Scalable persona queue: observed results — 2026-11-13

Baseline: `main` swarm queue integration (`7fd5d8dc`).
Branch: `rem/scalable-swarm-20261113`, in a separate worktree.
Protocol: [scalable-swarm-protocol-20261113.md](scalable-swarm-protocol-20261113.md).

## Implemented scope

The shipped standard-library path prepares a reviewed goal from current saved
personas, then runs a SQLite-backed provider-neutral model/tool/own-review queue.
It separates session count from global/provider concurrency and request rate,
reserves cost before send intent, requires exact live-plan consent, preserves
checkpoints, quarantines unknown effects, and revalidates evidence on readback.
Each persona receives its own context and observations. The host still owns real
browser/data isolation, credential consent and reviewed product-tool integration.

The ordinary skill flow is goal → concrete preview → cost consent when needed →
progress/pause/resume → current findings and gaps. Operators can use the installed
`swarm` preview/status/control commands; end users do not need to write JSON.
HTTP wire formats support reviewed Chat Completions and Anthropic Messages routes.
No model ID, price, credential or automatic fallback is supplied. Luna remains an
unresolved label until a supported host route is identified.

## Staged simulation

Command, run in the new worktree with Python 3.14.7:

```sh
env PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -l python3 \
  skills/remorsearch-ux-qa/examples/agents/scale_fixture.py \
  --out .ux-loop/validation/scale-final --stages 8,32,100,300 --parallel 16
```

Exit code: **0**. All decisions are authored callbacks; all PNGs are generated
fixtures. Actual model calls: **0**. Actual browser calls in these stages: **0**.
No credentials, paid APIs, Codex, user screens or existing Chrome tabs were used.

| Sessions | Global concurrency | Provider peaks A/B | Elapsed seconds | Cumulative process peak RSS bytes | Authored model calls | Tool/close calls | Passed / expected failed |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 8 | 4 / 4 | 1.152 | 47,202,304 | 32 | 24 | 6 / 2 |
| 32 | 16 | 8 / 8 | 5.287 | 51,003,392 | 128 | 96 | 24 / 8 |
| 100 | 16 | 8 / 8 | 23.649 | 59,785,216 | 400 | 300 | 75 / 25 |
| 300 | 16 | 8 / 8 | 138.590 | 75,743,232 | 1,200 | 900 | 225 / 75 |

Every queue finished with zero queued, running, blocked or uncertain sessions.
Each had exactly the requested distinct contexts. Every fourth authored scenario
deliberately loses input during rejection; later recovery did not erase that
failure. These are known diagnostic outcomes, not newly discovered product bugs.
Reopening and reading each run added zero calls and preserved original library
bytes. Reservations and settled amounts were zero, as required for this fixture.

The whole command took 168.91 seconds wall time, 143.49 user and 20.59 system,
with `/usr/bin/time -l` maxRSS 75,759,616 bytes. Stage elapsed time includes persona
preparation, execution and readback; each RSS value is the process peak so far,
not an isolated stage's incremental memory. The 300-session stage took more time
per session than the smaller stages. Repeated current-source/library/evidence
validation is included, but its individual cost was not profiled. These numbers
measure local coordinator work only, not model latency,
provider throughput or aggregate browser/remote memory. Configuration bounds of
1,000 sessions and 64 concurrent operations are not claimed as tested capacity.

Per-stage plan, report and event-chain digests are retained in the
[companion JSON](scalable-swarm-results-20261113.json).
Full local receipts remain under `.ux-loop/validation/scale-final/`. The earlier
pre-projection run remains under `scale-initial/` with its separate digests in the
JSON. That historical run took 175.67 seconds; neither run is a live benchmark. Hashes
establish recorded byte identity, not independent witness authenticity.

## Corrections found while implementing

The first diagnostic preparation exposed random hexadecimal IDs being interpreted
as phone-like data by the existing privacy gate. IDs now use an alphabetic digest
encoding; the privacy gate itself was preserved. Recovery testing also exposed
an early worker-refill exit and a close-response replay ordering issue; both were
fixed before the final stages. Tests identified timeout overrides exceeding the
approved limit and a null billing-review error; admission now enforces the
approved cap and rejects incomplete live billing review. Unknown actual billing
can be settled conservatively, including an observed overage without hiding it.

A final read review found that local capture filenames could enter the next model
request. A dedicated outbound projection now keeps observation content and
evidence IDs/kinds/digests while retaining filenames only in local evidence.
The regression checks initial, subsequent and review callback requests and
confirms the original local PNGs and observation-log hashes are preserved.
All four scale stages were rerun after this change; earlier run artifacts are retained.

## Release verification

The first full attempt, `.ux-loop/validation/release-final`, ran 1,544 Python
tests in 206.083 seconds and reported four subtest failures of the same reading
budget check (42,038 bytes against 42,000), with one existing painted-state skip.
The new route link pushed the initial reading closure 38 bytes over its cap.
One duplicated introductory sentence was removed; the observed/inferred/unknown
rule remains in the mandatory rules. No limit or test expectation was relaxed.
The focused reading-budget suite then passed all 13 tests in 0.197 seconds.
That original candidate is retained as a failed attempt; its source changed
during the remaining checks, so it is not a current validated release.

The final full gate in `.ux-loop/validation/release-verified` returned **exit 0,
24/24 checks passed, `ready: true`**. It ran with the existing Python 3.14.7,
Node 22.16.0, Playwright 1.56.1, LangGraph 1.2.20 and SQLite checkpoint adapter
3.1.3, with `REMORSEARCH_REQUIRE_AGENT_RUNTIME=1`. No dependency download,
installed-skill change or model-provider credential was needed.

| Final check | Observed result |
| --- | --- |
| Complete Python suite | 1,544 tests in 209.891 s; OK, one existing skip |
| Chromium driver | 559 passed, zero failed |
| Browser bridge contract | 7 passed, zero failed |
| Extracted queue diagnostic | Eight completed sessions at concurrency four; six expected passes and two expected failures; no redispatch |
| Extracted launcher | Swarm help and Korean status passed |
| Packaging and existing workflows | Build, ZIP/tree integrity, relocated discovery/reference reads, smoke and local/research/browser journeys passed |
| Final package/source checks | Post-browser integrity, current-source match and unchanged validation inputs passed |

The Python skip requires `ERGO_PAINT_CAPTURES`, a separate actual capture input.
The browser log also explicitly excludes the optional shared-browser handshake
(`REMORSEARCH_BROWSER_WS`) and Python captured-font analysis (`ERGOQA_PYTHON`)
because those inputs were not configured. These gaps are not reported as passes.
The optional pinned graph runtime was present and required, not silently skipped.

The whole gate command took 516.67 seconds wall time; its reported maxRSS was
239,271,936 bytes. This is a regression/packaging command, not a live-swarm
performance measurement. Its headless browser diagnostics are separate from the
browser-free scale stages. No product readiness or user benefit follows from
these check counts.

The raw gate report SHA-256 is
`c02fa08f7be81b92810f39b6b472da86c1357f2fe841393772a308c04e63d3b7`.
The verified ZIP SHA-256 is
`e7a62b28076d8bfdd65e3297b920e3b225103a4462c631b15f98c4fff2d856f8`.
The companion JSON retains every final check and the earlier failed attempt.
The raw gate report is preserved unchanged. After the gate, only this results
note and its companion JSON were finalized; the publication check compares the
packaged sources and runtime manifest again and confines source-snapshot changes
to those two evidence documents.

The staged `git diff --cached --check` returned 2 solely for an extra final blank
line in the new protocol, scale fixture, scale report and scale-report test files.
These nonblocking formatting notes are retained to keep the validated source
bytes unchanged; no trailing-space or functional defect was reported by that check.

## Remaining acceptance conditions

Actual DeepSeek/Haiku/Luna model execution, provider-side rate behavior, invoice
accuracy, small-model persona fidelity and sustained live scale remain unverified.
The host must first identify exact routes/models, review caps/prices and preview
the complete plan for explicit paid-call approval. A human review reference is
an audit record supplied by the host, not machine authentication of consent.
The self-review phase is the same persona reviewing its sealed judgment, not an
independent rater. Logical context separation is not an OS/network sandbox.

This work does not establish representative research personas, fresh public
research acquisition, arbitrary-product navigation, real-user preferences or
measured UX improvement. Operational completion remains separate from task
pass/fail, source validity and product readiness.
