# Scalable persona runtime acceptance protocol — 2026-11-13

Baseline: origin/rem/oss-swarm-20261112 at 7fd5d8dc731747ebd97a24946dc3f68324dd5e46.
New branch: rem/scalable-swarm-20261113. Work is isolated below the approved
repository; root and prior worktrees are preserved. This protocol is recorded
before staged scale execution. Provider/queue unit checks may already have run
while implementation was in progress; they are not the stage results.

## Scope

Implement a shipped, provider-neutral queue for current saved personas with
separate total-session and concurrent-call limits, durable budget reservations,
user cost approval, pause/resume, independent context/evidence, source validation
and an integrated model/tool/own-review loop. Keep fixture and live provenance
separate. Development does not authorize paid API use, provider logins, user
browser/screen access, Codex usage, installation or deployment.

## Required observations

- 8, 32, 100 and 300 authored sessions exercise the same installed core path.
  Record exact counts, own context IDs, per-provider callback peaks, elapsed time,
  coordinator process maxRSS, reports and plan/source hashes.
- Each authored scenario sees rejection and recovery. Every fourth deliberately
  loses input; final recovery must not erase that failure. These known authored
  outcomes are diagnostic oracles, not discovered product defects.
- Reopening and rereading completed runs adds no provider/tool dispatch and does
  not modify persona-library bytes.
- Concurrent database owners race for one affordable request. Only one reservation
  succeeds; other work waits or stops without overspending.
- Provider/global capacity and rate windows include unresolved requests; another
  eligible provider progresses. No unapproved fallback occurs.
- Pause blocks new admission while already sent work can settle. Committed state
  resumes; a missing stateful tool context is explicit rather than recreated.
- Kill an actual local child after committing an intent. Restart preserves the
  unknown outcome, reserved cost and permit, with no second dispatch.
- Reject stale owners, late/mismatched responses, changed code/plans/personas/PRD,
  expired/mismatched approval, malformed usage and cross-session artifacts.
- Preserve prior native failures when later execution/review becomes uncertain.
- Exercise installed/extracted entry and report commands without an added runtime
  dependency; retain existing regression/release gates and report any skips.

## Interpretation

All scale stages are offline authored simulation, with generated PNGs. Actual
DeepSeek/Haiku/Luna calls, provider-side concurrency, invoice accuracy, arbitrary
product navigation, public-source acquisition, independent human/model raters
and actual user benefit remain unverified. No test count substitutes for those
conditions. Results must name failures and corrections and distinguish operational
completion from UX pass/fail/inconclusive.

