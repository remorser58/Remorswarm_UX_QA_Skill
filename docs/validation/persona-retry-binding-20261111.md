# Attempt-bound retry validation

Date: 2026-11-11. Base: `771d63562573b6842fdddc77ec7461693fc4dc4f`.
Scope: local persona task bookkeeping and safe continuation, not live user research.

## Reproduced defect and correction

The task operation ID deliberately survives retries. Previously, reconciliation
only checked that stable ID, so an inspection from attempt 1 could be reused after
attempt 2 became inconclusive. A controlled synthetic reproduction on the base
revision incorrectly permitted attempt 3.

Retry now requires the current integer `attempt` together with the operation ID,
stopped-worker statement and fresh actual-state inspection. Missing, stale or
incorrect bindings leave the state unchanged and the resource quarantined.
Correct current-attempt inspection still permits a bounded retry; this is not a
blanket disablement of recovery.

Independent review also reproduced an upgrade gap: old software could have
already saved that unsafe retry as pending. Such a pending task now blocks its
own claim and shared-resource claims, with a report blocker. Fresh inspection
adds a separately labeled review beside the original historical reconciliation
and receipt. Attempts, budget and original history are preserved. Exact repeat
reviews are idempotent and conflicting reviews cannot overwrite them. Independent
resources may continue. Claim also independently checks the attempt ceiling.

New or mutated state uses envelope v3. The actual source of both older readers
(v1-only and v1/v2) rejected retry, claim and report against the new envelope.
Current code still reads unchanged legacy v1/v2 records, but does not silently
treat an unbound pending retry as safe.

## Verification

- New retry and migration regressions: 19 passed, including independent execution.
- Persona suite: 106 passed on Python 3.14.7 and Python 3.10.20.
- Relocated retry/settlement suites: 35 passed; module origins checked against the
  extracted package rather than the source checkout.
- Reading-budget suite: 13 passed; limits unchanged.
- Full Python suite: 1,149 run, 1,148 passed, 1 skipped; 55.060 seconds.
- Full candidate check: all 16 checks passed, including current-source match,
  relocation, smoke and post-browser integrity.
- Chromium driver: 559 passed, 0 failed; 264.08 seconds.
- Aggregate wall time: 322.81 seconds; maximum resident set 246,956,032 bytes
  (about 235.5 MiB); swaps 0. These describe the local test workload, not user speed.
- Diff whitespace check passed. Original source worktree HEAD/status and all
  310 previously dirty/untracked file hashes remained unchanged.

The final command was `python3 scripts/check_release.py --output
dist/retry-binding-20261111-r2`, with existing Node 22.23.4 and prepared Playwright
dependencies. The initial sandboxed browser launch closed before navigation;
that incomplete candidate remains separate. The final check used an approved,
isolated headless Chromium process, never a user's browser profile, tabs or screen.
No Codex model task, installation, live account mutation or research collection
was invoked for these checks.

The skipped Python check lacked `ERGO_PAINT_CAPTURES`. Optional live browser
handshake and typography inputs were not supplied. Candidate `ready: true` means
local packaging/regression checks, not product readiness or remote CI.

ZIP SHA-256:
`83fdca2c30df92a16938c7b967ba2e5f51d9bf7d6534df357694ffb33cb5fcfc`.

## Evidence limits

Before/after fault injection confirmed the earlier inspection was accepted on
the base and rejected after correction, with unchanged state on rejection.
A fresh current inspection then allowed the next attempt within the original
limit. Independent review used the actual old source to construct the legacy
pending state and confirmed both quarantine and reviewed recovery.

These are synthetic orchestration checks, not observed real-user behavior.
Host inspection remains an attestation, not independent proof. Previously
running/completed work is not retroactively certified or stopped by this change.
Research permissions/provenance gaps, known Peekly findings and the lack of a
demonstrated real-user effectiveness advantage over ordinary QA remain unchanged.
