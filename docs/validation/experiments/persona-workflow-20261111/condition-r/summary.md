# Frozen condition R first pass

Frozen in evaluator conversation before recovery. No first-pass findings were added after recovery. This is synthetic fixture QA using three revision-1 PRD-hypothesis personas, not real-user research or a product-readiness claim.

## Reproduced conflicts

- P8R, C1: choose Cedar, sort by cost, review. Expected Cedar selected and reviewed. Actual selection changes to Maple and review says Maple. Impact: unintended room enters review. Actions13–15, screenshots13-1794357989375.png,14-1794357989407.png,15-1794357989491.png. Back retained the resulting Maple/cost state; choosing Willow replaced it, reviewed and confirmed Willow.
- B7N, D2 with propagated D1 failure: edit title to Ribbon planets and seats23, pause, resume, review, back, review, confirm. Expected both edits preserved. Actual resume seat input14; both reviews and confirmation14; title preserved. Impact: unintended seat limit confirmed. Actions31–38, screenshots32-1794358080351.png,34-1794358080469.png,35-1794358080519.png,38-1794358090153.png. Back retained already incorrect14; no separate back-loss defect claimed.
- D5Q, I1/I2: enter whitespace-padded Blue paper, blank line, Gold cord; preview; Back without applying. Expected current materials Starter kit. Actual Starter kit, Blue paper, Gold cord. Impact: canceled materials added. Actions39–42, screenshots39-1794358115108.png,41-1794358115201.png,42-1794358115252.png. Internal mutation timing uninspected. Revised Silver ribbon/Wood beads applied once and cleared input; unwanted prior names remained.

Screenshot paths above are relative to evidence/. Accepted receipts also reference SHA-256-hashed copies in ../swarm/evidence/CASE/1/.

## Outcomes and limits

K4M accepted passed: Folded stars and21 preserved through pause/resume, review/back, confirmation. P8R failed. T2V accepted passed: normalized preview, unchanged Starter kit after back, retained input visible, revised apply once and empty input. B7N failed. D5Q failed. H9S claim succeeded but eight submitted commands returned no result; execution uncertain, not a failure or proof of nonexecution.

Duplicate input names excluded in both import tasks exactly as planned. Exact retained whitespace not independently measured. Current materials not visible during preview, so observations concern the preview/back transition, not transient internals. No real-user or population-effect conclusions; no invented token/cost measurements.

45 verified attempted actions including two failures, plus8 submitted/unconfirmed H9S commands. Original harness and budget retained. Initial navigation connection-refused counted. P8R action11 was premature read-only navigation after claim blocked by unaccepted K4M receipt; action12 restarted that case after actual claim. Both count. T2V action21 exact visible-label fill timed out; Material names label succeeded later. Empty preview/back also counted.

Earliest saved observation timestamp1794357835372; last verified screenshot1794358124800, interval289.428s. This is not exact first-action-to-final elapsed time: initial failed navigation has no screenshot timestamp.

## CLI friction

K4M receipt attempts rejected with 'Receipt text contains personal identifiers.' and 'A bounded nonempty string is required.' Dependent P8R claim attempts rejected with 'Worker already holds an active task.' Full raw observations contained local paths; timestamp-derived screenshot IDs also triggered scrubbing. Authoring corrected to concise truthful observations, descriptive screenshot IDs and nonempty blank-page observation. No gate/validator edits. Raw logs retained. Five receipts then accepted. Rejected intermediate receipt files were overwritten by corrected receipts; exact rejection messages survive in the evaluator transcript, not independently retained input snapshots.

## Disconnect at first-pass freeze

Final H9S submission was goto, choose Cedar, cost sort, review, back, choose Willow, review, confirm. write_stdin failed: 'exec-server transport disconnected; failed to resume exec-server session: recovery timed out after45s'. Environment unavailable; PTY38390 could not be closed, findings/summary file creation and hashes blocked. Conversation froze findings at that point.

## Post-freeze reconciliation appendix

Recovery performed only read-only inspection and bookkeeping, no UI actions. Empty poll of original PTY38390 returned 'Unknown process id38390'. Existing actions.jsonl and screenshot listing end at action45, with no H9S results. This does not prove the submitted commands never executed. An escalated process-list inspection found no persona-effectiveness/harness or playwright_chromiumdev_profile process. No EOF could be delivered to the lost PTY; no matching harness/browser remains observable.

H9S honest inconclusive receipt accepted post-freeze, attempt1. Its criterion status not_run is the schema representation of missing observations, not a factual assertion of nonexecution. No retry or settlement attestation invented. Original exact first-action clock remains unrecoverable from existing logs. Final task state:2 passed,3 failed,1 inconclusive; H9S resource remains quarantined. No new first-pass findings.
