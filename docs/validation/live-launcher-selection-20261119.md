# Live launcher selection receipt binding, 2026-11-19

## Scope and completion boundary

Base: `4820629948793824576a9434353a1560d8034ea2` (PR #8).
The change is limited to the existing `live_scale_browser.py` launcher, its
launcher regressions and usage contract. It reuses `product_controls` and the
existing strict JSON/queue contracts. No change to `scale_entry.py` or
`scale_run.py`, no new runtime, Dots UI, model calls or historical cohort replay.

The launcher must consume an actual reviewed `ux_personas.py select` receipt,
preserve exact choices, and reject missing/cancelled/stale selections before any
catalog, browser or model boundary. Selection is distinct from current execution
consent; the historical hardcoded November 14 approval is removed.

## Verified evidence

On OCI Osaka, Python 3.12, before the final missing-Library guard/help-text addition:

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_live_browser_selection.py' -v`
  returned exit 0, 13 tests, 2.065 seconds.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_product_controls.py'`
  returned 22 tests, 3.424 seconds, OK within the subsequent command sequence.
- `git diff --check` returned exit 0.

The actual `ux_personas.py select` subprocess output was read by the launcher,
then the real `prepare_scale_goal` created a disposable local queue containing
the unchanged selection, reversed-from-Library persona order, exact assignments,
selected parallelism 1 and model-call ceiling 30. The real local queue approval
used the separate supplied actor/reference with zero ceiling. Execution was
deliberately stopped before dispatch; the queue had zero operations and
`selection_ui_verified: false`. This is offline integration evidence, not a
successful live browser/model run or proof of a rendered user-choice UI.

The negative tests reject missing file/receipt, cancellation, unconfirmed and
tampered selections, duplicate JSON keys, changed PRD/UI bytes or persona
revision, unsupported model/reasoning, missing execution consent, a missing later
stage receipt, overlapping/wrong-sized stages and receipt changes between stages.

## Incomplete result collection

After adding a fourteenth test for preserving an empty Library rather than
initializing it, the 14-test suite followed by smoke-loop/research fixtures was
started. Polling its process was refused with `EXEC_CALLER_UNIDENTIFIED`.
No result was inferred from process absence. An independent verification of the
final launcher source subsequently passed all 14 launcher tests in 2.049 seconds;
that command did not run the smoke/research fixtures.

The earlier regression command sequence proceeded into `test_coverage_planning.py`
after the 22 product-controls tests. It then scheduled
`test_model_router_uncertainty.py`, `test_live_browser_recovery.py` and
`test_scale_browser_lifecycle.py`. Only the product-controls result was retrieved;
later results are not counted as passed.

Full unit/release checks, Dots UI rendering, real model/browser journeys and
product readiness are not established by this record. Historical queues and
uncertain sends remain untouched.
