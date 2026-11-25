# Persona-assisted QA comparison: preregistration

Frozen protocol authored 2026-11-11 00:36 UTC, before either evaluator starts or
the parent reads the hidden answer key. Base skill revision: `544615d`.

## Question and scope

In one new, controlled local UX fixture, does the saved/reused PRD-hypothesis
persona and explicit task-planning workflow help an independent QA worker find
reproducible behavioral defects under an equal interaction budget?

The treatment is the workflow package, not personas alone. Each condition uses
one worker, so this is not a swarm-versus-single-worker efficiency test. Synthetic
profiles are not real participants or evidence of population needs. Results
cannot establish real-user benefits, field effectiveness or whole-product readiness.

## Fixed design

- Six opaque cases in one small product, authored by a separate worker.
- Exactly three deterministic seeded behavioral defects and three clean controls.
- Product obligations are public in the same mini-PRD given to both conditions.
- The author privately verifies the fault/control oracle using actual isolated
  headless browser interaction before freezing the fixture.
- The public build, PRD, case list and harness are hash-frozen before evaluation.
  Neither evaluator may read source, answer keys, oracle artifacts, browser
  internal state or the other evaluator's conclusions.
- Both conditions get the same public inputs, case URLs and browser tools.
- Ordinary QA may choose its own strategy. Persona-assisted QA additionally gets
  pre-authored, explicitly synthetic PRD-hypothesis profiles, retrieved from the
  skill's persistent library, and mapped task obligations. Profiles are authored
  from the public PRD before the parent reads the answer key.
- Independent fresh-context workers use the same inherited model configuration.
  Model call/token totals may be unavailable; do not infer them from tool counts.
- Each worker has at most **60 user actions total** and **12 minutes from first
  interaction**. Count each navigation, click, fill, selection or key operation.
  Read-only DOM observations and screenshots are not user actions.
- Each condition uses a separate synthetic session/storage namespace. No external
  accounts, data, network collection, user browser profile, tabs or screen.
- No seeded target fix, added clue, budget adjustment or test modification after
  the first worker begins. A later correction requires a newly labeled experiment.

## First-pass output and freezing

Each worker reports case IDs actually exercised, reproducible defects, separate
hypotheses, expected/observed outcomes, reproduction steps, artifacts, action
counts, timing and untested/blocked states. Findings are frozen by hashes before
unblinding. Missing execution is never a clean control or a pass.

The parent does not reveal the hidden key or another worker's findings while a
first pass is underway. Condition labels are masked for adjudication where
possible; finding prose may reveal strategy, so do not claim perfect blinding.

## Adjudication and metrics

An independent reviewer checks actual findings against the pre-frozen oracle,
PRD and evidence. A defect match needs the same violated obligation and
reproducible behavior, not a similar keyword or speculative explanation.

Report per condition:
1. Unique seeded defects detected / 3, with individual misses.
2. Unsupported reproduced-defect claims, grouped by underlying claimed issue.
3. Clean-control cases with false alarms / 3.
4. Duplicate reports of the same underlying defect, separately.
5. Cases exercised and not exercised, counted actions, elapsed time and available
   execution costs. No invented token/cost measurements.

Hypotheses are shown separately and do not count as detected defects. Duplicate
findings do not inflate recall. A newly discovered genuine unseeded fixture defect
invalidates the primary controlled comparison for the affected scope; preserve it,
report the discrepancy and label any post-hoc analysis exploratory. Do not silently
remove inconvenient cases or change the answer key to favor either condition.

A condition that violates isolation, reads answers, exceeds a budget or lacks
execution receipts is incomplete/invalid, not a zero-defect success. Report partial
observations descriptively without claiming a complete head-to-head result.

## Interpretation committed in advance

A tie or regression is a legitimate outcome. Do not claim superiority without
higher unique detection or fewer false alarms under the stated comparable budget.
Even a favorable result is descriptive evidence from this small synthetic fixture,
not statistical evidence of general effectiveness. Do not tune the skill on this
answer key and call a rerun unseen validation. Once published, these cases become
development fixtures; future unseen claims require fresh held-out cases.
