# Everyday Desk: PE-2 public requirements

This is a self-contained synthetic product, not a live service or a product redesign. Six independent sessions expose three bounded everyday workflows. Case IDs are opaque. There are no accounts, uploads, real files, purchases, or external services. All names and inputs are synthetic. Reloading a case starts its page state over; it does not reset the evaluation budget.

Cases in presentation order: **V7Q, J2N, H8C, R5B, L9F, D3W**. Inspect each through the UI. The same requirements below apply to every case exposing that workflow. No case-specific exemptions exist.

## Case directory

| Case | Workflow |
|---|---|
| V7Q | Plant care note |
| J2N | Listening queue |
| H8C | Park walk plan |
| R5B | Plant care note |
| L9F | Listening queue |
| D3W | Park walk plan |

## Plant care note
The user records how often a fern needs water. The default interval is 7 days; initially nothing is saved. A whole-number interval from 1 through 14 is valid, inclusive. Empty, nonnumeric, fractional, zero and out-of-range input must not save. Submission of invalid input gives actionable validation. A user must be able to correct invalid input to a valid value and successfully save without reloading, losing the entered correction, or being trapped by an earlier error. A successful save removes obsolete error text and visibly confirms Fern and the submitted interval. Further valid edits can be saved in the same page. The core recovery check is an invalid submission followed by correction and resubmission; use representative inputs rather than exhaustively testing integers.

## Listening queue
Initially the ordered queue contains Morning Birds, then River Sounds, with a count of 2. The user may remove Morning Birds. Selecting removal opens a confirmation dialog without changing the queue. Cancel closes the dialog and preserves both episodes, their order, and count. A subsequent removal request must still be possible after cancellation. Confirm removal closes the dialog, removes only Morning Birds, retains River Sounds and changes the count to 1. The core check includes both cancel and a later confirmed removal. There is no add, playback, undo, or reorder feature in scope.

## Park walk plan
The user chooses between Shortest path and Avoid stairs. Default is Shortest path, with no initial preview. In each newly loaded page the first preview intentionally produces a temporary simulated outage and an explicit Retry preview action. This outage itself is required, not a defect. Neither the failed attempt nor retry may change the chosen preference. Retry succeeds without requiring re-entry. Avoid stairs must yield Riverside ramp, 1.2 km, no stairs. Shortest path must yield Hill steps, 0.8 km, includes stairs. A successful retry clears the outage message. The user can then change preference and preview the other route without another outage. The core check includes a nondefault choice before the initial preview, recovery with retry, and an ordinary subsequent choice change.

## Scope and acceptance
Evaluate observable completion, validation recovery, choice preservation, and cancellation semantics. Default visual styling is not a defect. No persistence across navigation is promised. No claims about production UX or real-user effectiveness follow from this fixture. All core transitions across six cases fit comfortably within 60 attempted actions; observation is free. Report independently evidenced violations with case ID, actions, expected versus observed behavior, impact and evidence reference. Do not infer one case's outcome from another.
