# Terminal fixture-write recovery validation

Date: 2026-11-10. Base: `7adc69605a6a39b92c3368f0ad65fa061ffdcea5`.
Scope: local persona orchestration, not live research, human usability or product readiness.

## Delivered behavior

A final inconclusive fixture write previously left the same resource unavailable to
other tasks even after the host stopped the worker and inspected the actual state.
`personas settle` closes that attempt without retry. The task stays inconclusive;
its attempts, operation identity, receipt and history remain unchanged.
The host must bind its actual inspection to the current operation and attempt.
A fresh claim is still required for any other authorized task.

Current persona/PRD/research/build and receipt-integrity gates remain in force.
Exact repeated settlement is idempotent, conflicting inspection is rejected,
late receipts cannot become a pass, and any other unresolved write on the same
resource still blocks assignment. Settlement is explicitly a host attestation,
not independently verified inspection or new permission.

Only settled runs use state envelope v2. Legacy v1 runs remain readable, but an
old reader must reject a v2 run rather than ignore the terminal decision.

## Verification

- New settlement regressions: 16 passed.
- The same 16 passed from the extracted installation; runtime module origins
  were checked to exclude accidental imports from the source checkout.
- Persona suite: 87 passed on Python 3.14.7 and Python 3.10.20.
- Reading-budget suite: 13 passed without increasing its limits.
- Full Python suite: 1,130 run, 1,129 passed, 1 skipped; 65.673 seconds.
- Full candidate check: all 16 checks passed, including relocation, smoke,
  current-source match and post-browser integrity.
- Chromium driver: 559 passed, 0 failed; 271.23 seconds.
- Aggregate elapsed time: 341.78 seconds. Maximum resident set: 213,024,768 bytes
  (about 203.2 MiB); swaps: 0. This is the local test process measurement,
  not end-user application performance.
- `git diff --check`: passed.

The aggregate command was `python3 scripts/check_release.py --output
dist/terminal-recovery-20261110-r1`, with existing Node 22.23.4 and prepared driver
dependencies. No install, user browser tab, model/Codex task or remote product
mutation was used.

The skipped Python check lacked `ERGO_PAINT_CAPTURES`. Optional live browser
handshake and typography inputs were not supplied. Package `ready: true`
describes local candidate checks only; it is not a product-ready claim or remote CI.

Candidate ZIP SHA-256:
`6542fe0a97381c2f2073132d0dcf7924a56fc029f56a92bbcee74f40c18e5308`.

## Actual process comparison

The new integration test launches a separate Python process that writes one
isolated synthetic file and exits with code 23 before submitting any QA result.
The parent observes process exit and reads the file, then records an inconclusive
attempt. Before settlement, another task on that resource cannot claim it.
After CLI settlement, that task can claim it. The original file still contains
exactly the one write; the original task remains at one attempt and inconclusive,
with zero QA passes. CLI settlement took 0.2223 seconds in the aggregate run.

This demonstrates recovery of safe local task assignment, not improved defect
detection, completed browser QA or faster human task completion.

## Bounded scale measurement

Five local orchestration-only runs each used 128 tasks and a real file-backed
persona library. No worker was launched in this scale fixture. The intentionally
inconclusive orchestration entry was settled as not executed after inspection.

- Settlement: median 0.083142 seconds, maximum 0.170743 seconds.
- Report: median 0.084272 seconds, maximum 0.104998 seconds.
- All five retained zero task passes and allowed the next eligible claim.

These are descriptive measurements from one machine, not a performance SLA or
a comparison of model effectiveness.

## Independent review and remaining limits

Independent review reproduced three implementation defects before correction:
an old reader could retry a settled task, shared-resource quarantine reporting
ignored another task, and an earlier attempt's inspection could settle a later
attempt. The v2 boundary, resource-wide reporting and current-attempt binding
fixed them. The original reader's retry/claim/report now reject settled state
with `swarm_integrity`; the new reader preserves the inconclusive result.

No additional blocking defect was found in this scoped review. Inspection is
still host-provided and cannot prove an external worker stopped. Stale or missing
dependencies can still block settlement. Research permission/provenance gaps and
the previously reported Peekly findings remain unresolved. Existing weak-source
personas were not promoted or reimported. There is still no demonstrated
real-user effectiveness advantage over ordinary QA.
