# PE-2: completed bounded synthetic comparison

**Both conditions found the same three seeded behavioral defects, with no false
alarms on the three clean controls.** All six cases were executed within the
60-action / 12-minute limits. This is a descriptive detection tie, not evidence
of persona superiority, equivalent full coverage, statistical generalization or
real-user benefit.

| Verified measure | Ordinary QA (M) | Persona + plan workflow (N) |
| --- | ---: | ---: |
| Unique seeded defects | 3/3 | 3/3 |
| Clean-control false alarms | 0/3 | 0/3 |
| Cases exercised | 6/6 | 6/6 |
| Attempted actions | 60 | 37 |
| Successful operations / timeouts | 59 / 1 | 36 / 1 |
| First action through final evidence | 455.512 s | 321.832 s |
| Unknown execution outcomes | 0 | 0 |

The conditions took different paths. M also tested endpoint and invalid-input
variants and reloaded selected cases for extra checks. N used representative
zero/five/nine inputs and the supplied task plan. Preparation before first UI was
not separately timed. Model-call/token/financial costs were unavailable. **Fewer
actions or a shorter interval is not an equivalent-coverage efficiency claim.**

## What was observed

- J2N: Cancel removed Morning Birds, changing count to one and preventing the
  next removal request. The absent-control timeout corroborates the blocked step;
  it is not an additional independent defect.
- R5B: submitting invalid input left a persistent error that blocked valid
  corrections from saving. Further failed saves are the same recovery defect.
- D3W: retry reset Avoid stairs and returned a route containing stairs; the later
  nondefault preview repeated the preference failure, not a separate detection.

The required first simulated route outage was not counted as a defect. V7Q,
H8C and L9F supplied independently observed clean control paths. The supplied
personas are explicitly synthetic PRD hypotheses, not research-backed people.

## Actual workflow use

Three profiles were imported, reimported unchanged at revision one, and retrieved
in separate calls. N reused them and executed six claim → receipt-starter →
actual UI → completed receipt sequences. All six records passed validation on
first submission: three passed tasks and three failed tasks. The starter did not
create steps, evidence, a pass, a new lease or additional authority. The host still
authored observations and linked actual captures. Raw claim tokens stay private.

Core plan coverage was independently reviewed before unblinding. Initial defaults
and valid range endpoints were not explicitly mapped in the plan; the evaluator
observed defaults, but representative saves cannot establish the whole valid
range. The invalid-class matrix remained excluded in N. Paired requirement IDs
quote the same source paragraphs and are not independent complete requirements.
Passing selected criteria does not mean each whole paragraph passed. See
[coverage review](coverage-review.md) and [independent adjudication](adjudication.md).

## Freeze and evidence

Inputs and oracle hashes were committed locally in `37b9e89` before evaluator
dispatch. Both reports froze before unblinding; actual first/last timestamps,
action budgets and normal EOF shutdowns were retained. Frozen target and skill
hashes still match. No case or answer key was retuned after execution.

- [Protocol](../persona-workflow-pe2-preregistration-20261111.md)
- [Pre-dispatch commitment](../persona-workflow-pe2-commitment-20261111.json)
- [Public PRD](../../../../benchmarks/persona-effectiveness-pe2/PRD.md)
- [Runner instructions](../../../../benchmarks/persona-effectiveness-pe2/EVALUATOR.md)
- [Frozen manifest](../../../../benchmarks/persona-effectiveness-pe2/SHA256.json)
- [Unblinded answer key](answer-key.json)
- [M findings](condition-m/findings.json), [summary](condition-m/summary.md),
  [action log](condition-m/evidence/browser/actions.jsonl)
- [N findings](condition-n/findings.json), [summary](condition-n/summary.md),
  [action log](condition-n/evidence/browser/actions.jsonl)
- [Publication manifest](manifest.json)

The full synthetic UI action logs are included byte-for-byte. Twenty selected
screenshots are included; other references in the frozen reports identify local
private images not included here. Original image hashes remain in the reviewed
private receipts/trace manifests. Hashes are consistency checks, not substitutes
for omitted pixels or independent authenticity. M's report replaces its exact
private worktree prefix with `<worktree>`; other report bytes are unchanged.
The publication manifest records source and public hashes plus transformations.
No task-state/lease secrets, real-user data or research captures are included.

## Boundaries and next use

This completed benchmark does not repair PE-1's missing observations. It supports
a small synthetic detection tie, not the claim that persona QA is better than
ordinary QA. Published PE-2 cases now become development fixtures; future unseen
claims require new cases and a new preregistration. The 12-minute limit was enforced
by the harness, but its expiry path was not verified by a full 12-minute wait.
No external research was collected. DC permission, authorized YouTube API access
and suitable native study evidence remain separate unresolved requirements.
