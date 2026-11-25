# Persona workflow comparison, 2026-11-11

**Incomplete comparison. No demonstrated superiority or completed tie.**
Ordinary QA (Q) and saved/reused PRD-hypothesis persona + task-plan QA (R)
each reported the same three supported seeded defects. R's final clean case
was unobserved after a transport disconnect; its eight submitted commands were
not repeated. Exact total interaction times are unavailable for both conditions.

| Observed metric | Q | R |
| --- | ---: | ---: |
| Unique seeded defects | 3/3 | 3/3 |
| Unsupported unique claims / duplicate claims | 0 / 0 | 0 / 0 |
| Clean controls with evidence | 3/3 | 2/3 |
| Observed false alarms | 0 | 0, final control unknown |
| Verified attempted UI actions | 60 | 45 |
| Additional submitted but unconfirmed commands | 0 | 8 |
| Saved screenshot interval, not total time | 107.584 s | 289.428 s |

This is one worker per condition on six synthetic cases, not a swarm efficiency
trial or real-user study. The treatment includes both personas and task planning;
it does not isolate persona effects. Q and R exercised different bounded paths.
Model calls, tokens and costs were not measured. Do not rank efficiency from these
partial action/time totals. The ordinary QA condition is not a straw-man baseline:
it used the same PRD and was free to choose its strategy.

## What was actually executed

Three synthetic personas were imported, reimported unchanged at revision 1, and
retrieved from the persistent library in separate CLI calls. Six tasks were
planned with one concurrent worker. R produced five evidence-backed receipts;
a sixth was recorded honestly as inconclusive after recovery. The shared
resource remains quarantined, not silently released or passed.

The initial server refused both first navigations. The same frozen target was
restored without resetting budgets. R also had receipt-authoring friction and
one read-only navigation before its accepted task claim; it then began that case
fresh. Full deviations and integrity limits are in [adjudication.md](adjudication.md).

## Evidence index and publication subset

- [Preregistered protocol](../persona-workflow-preregistration-20261111.md)
- [Frozen target and hash manifest](../../../../benchmarks/persona-effectiveness/SHA256.json)
- [Public target requirements](../../../../benchmarks/persona-effectiveness/PRD.md)
- [Pretrial oracle, revealed after reports froze](answer-key.json)
- [Independent adjudication](adjudication.md) and [structured results](adjudication.json)
- [Q frozen findings](condition-q/findings.json), [Q summary](condition-q/summary.md),
  [Q minimized action trace](condition-q/actions.minimized.jsonl)
- [R frozen findings](condition-r/findings.json), [R summary](condition-r/summary.md),
  [R minimized action trace](condition-r/actions.minimized.jsonl)
- [Publication manifest and transformations](manifest.json)

Frozen findings and summaries retain their original bytes and references. Their
`evidence/actions.jsonl` and most screenshot references name **local private
artifacts, not files included in this publication**. Public traces are named
`actions.minimized.jsonl`; six selected PNGs per condition are included in each
`evidence/` directory. Every trace screenshot carries its source digest, including
omitted captures. The independent reviewer inspected additional original captures
and checked all 48 artifacts used by the five evidence-backed receipts. A digest
alone is not a substitute for access to an omitted image.

Public traces remove absolute screenshot paths and replace verbose error output
with reason codes. Commands, action counters, success flags and visible text are
retained. No raw task-state/lease tokens, research content, personal browser data
or user-supplied studies are included. Original logs remain unchanged locally.
Manifest hashes establish byte consistency, not independent authenticity.

The oracle key existed before execution, but its hash was not separately committed
before the trial. R's first-pass freeze was conversational and only materialized
into files after recovery. These provenance limits remain; later hashing does not
repair them.

## Improvements prompted by this run

The post-trial implementation adds field-specific, privacy-safe receipt diagnostics
without weakening privacy/evidence gates. A separate [portable launcher](../../../../benchmarks/persona-effectiveness/RUNNING.md)
checks its own server before browser startup, keeps lifecycle timestamps and closes
its owned resources. Neither change repairs the historical comparison. The six
frozen target files remain unchanged. Later checks of these published cases are
development validation, not fresh held-out effectiveness evidence.

DC written permission, authorized YouTube API access and suitable user-provided
native research remain separate evidence gaps. This synthetic experiment does not
clear those gates or turn exploratory personas into empirically supported users.
