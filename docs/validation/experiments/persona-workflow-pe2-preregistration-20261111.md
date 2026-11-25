# Persona workflow PE-2: preregistration

Authored before evaluation and before the coordinator sees the hidden oracle.
This is a new six-case synthetic product, not a rerun of published PE-1 cases.
The separate author is not given either condition's findings or persona packet.

## Question and interpretation

Under equal interaction/time limits, how do ordinary task QA and the complete
saved/reused PRD-hypothesis persona + explicit task-plan workflow compare on
supported behavioral defect detection and false alarms? The treatment includes
planning and receipt tooling, not personas alone. One independent worker runs
each condition, so this is not a multi-worker efficiency experiment.

Synthetic profiles are test conditions, not empirical people or population
estimates. A tie, regression or incomplete result is legitimate. No statistical,
real-user, production-performance or whole-product-readiness claim follows from
this small authored fixture. Detection advantages, if any, remain descriptive.

## Freeze before dispatch

1. The independent author creates three deterministic behavioral defects and
   three clean controls, with public obligations applying to the corresponding
   workflows in all cases. Exact mapping is private until reports freeze.
2. The author verifies all six through actual isolated browser execution.
3. Public target, PRD, harness and launcher file hashes, hidden answer-key hash,
   oracle trace hash, this protocol and the exact skill-source hashes are saved
   in a separate commitment record and local Git commit before either evaluator
   starts. No target/tooling/skill edits during execution. Verify hashes again
   before unblinding. A change requires a newly labeled experiment, not a repair
   to this result. Committing a digest is not proof of external authenticity.
4. The coordinator authors treatment profiles and task obligations from public
   PRD only, without reading app source or hidden answers. Profiles are explicitly
   `prd_hypothesis`, actually imported, reimported and retrieved from the library.
5. Each evaluator is a fresh-context worker with the same inherited model
   configuration and public inputs. Neither reads the other condition, target
   implementation, browser internals, oracle or prior comparison findings.

## Equal execution limits

- At most **60 attempted UI actions** and **12 minutes from the first counted
  interaction** per condition, across all six cases. Goto, click, fill, selection
  and key operations each count, including failures. Observations/screenshots do
  not increment the action count; no compound key actions to evade the budget.
- Each condition uses its own fresh evidence directory, ephemeral loopback server
  and isolated headless browser, never a user profile, screen, tab or real account.
- The same readiness-checked launcher/harness is used. It records first-action
  time plus each command's start/end, including failures. No automatic retry,
  clock reset or invisible extra UI actions. Both follow the same tool interface.
- Ordinary QA chooses its strategy. Persona QA receives pre-authored synthetic
  profiles and mapped task criteria, reuses them, claims tasks before performing
  UI actions and records honest evidence-backed receipts. Preparation before the
  first UI action is disclosed separately, not silently counted as zero cost.
- CLI authoring/claim time between first and last UI actions is part of the wall
  window. Report writing may finish later, but no new UI actions may be performed
  after exhaustion. Do not retroactively interpret an unknown operation as not run.
- No unrelated full test suite runs concurrently with the comparison. A disconnect
  or missing output is retained; inspect the original logs/session before any
  retry. Do not rerun a condition to obtain a more favorable outcome.

## Freeze and independent scoring

Each evaluator freezes findings, steps, expected/actual outcomes, evidence links,
coverage, failed/uncertain actions, timing and file hashes before unblinding.
A conversational freeze after transport loss is separately identified and does
not substitute for missing execution evidence. The independent reviewer compares
frozen reports with the precommitted oracle, PRD and actual logs/captures. Strategy
may be apparent from prose, so do not claim perfect reviewer blinding.

Score per condition: unique seeded defects / 3; unsupported unique reproduced
claims; false-alarm clean cases / 3; duplicates separately; cases/obligations
actually exercised; attempted/successful/failed/unknown actions; exact available
execution interval; receipt/claim failures and available preparation evidence.
Do not count propagated consequences twice. Hypotheses are separate. No inferred
model-token, call or financial cost metrics.

A claimed failure must violate the same obligation with reproducible behavior,
not a keyword match. Genuine unseeded defects invalidate the controlled comparison
for the affected scope and remain visible, not relabeled to favor either method.
Missing controls, budget/isolation violations or unverified evidence make the
primary comparison incomplete/invalid; report partial observations descriptively.
Do not call two partial 3/3 detection totals a completed head-to-head tie. A full
result requires all planned controls observed and independently verified timing,
within the limits, with explicit remaining obligation exclusions.

The baseline and treatment may cover different bounded paths; report those rather
than implying whole-PRD equivalence. Effectiveness and evidence integrity are
separate: a valid receipt alone is not an independently observed outcome.

Once PE-2 is published, it becomes a development fixture. Future unseen evaluation
needs new held-out cases and a new precommitment. Access/source/privacy gates remain
unchanged; this experiment does not certify real research or grant missing rights.
