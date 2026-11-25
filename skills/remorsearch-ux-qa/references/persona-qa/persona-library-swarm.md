# Versioned personas and bounded UX task QA

## Purpose and boundaries

Build multiple behavioral synthetic personas from the product PRD and contextual research, retain useful versions, and assign real product tasks to isolated host-native workers. This is UX task QA, not screenshot-only critique or simulated market research. Personas are test conditions, never real participants, prevalence estimates or proof of human benefit.

Read `workflow.md` for actual execution, severity, second-pass and replay requirements. Research still follows `references/research/workflow.md`, access/evidence cards and `community-to-test.md`. Local library and assignment records organize work; they do not execute browsers, verify source truth, certify accessibility or declare product readiness.

## 1. Derive the research question from the PRD

Record product identity, PRD version/source, intended audience, need, feature, concrete task, success criteria, preserved decisions and unknowns. Inspect the actual product and current build. If the PRD is missing, use confirmed product context and label assumptions; do not ask the user to invent a brief or block feasible QA.

Seek task-changing situations: what someone needs to decide, compare or retain; what they already know; what interrupts them; how they recover; when they abandon. Initial product QA refines these questions. Do not derive behavior from demographic decoration or assume forum membership identifies a product user.

## 2. Research public context without broadening access

Use insane-search discovery and the packaged collection methods within the existing research budget. Read parent context, comments/replies and relevant video context where permitted; distinguish firsthand experience, promotion, inference, duplicates and counterexamples. Record actual read scope and gaps. “DC and YouTube research” never means exhaustive scraping.

- DC Inside stays stopped until its required recorded terms checks and applicable written permission are present.
- YouTube comments use the authorized Data API route and required key, not page rendering or substitute frontends. Retention deadlines still bind derived exports.
- No parallel external requests to the same host, stop bypass, private history collection, identification or raw source text in persona prompts.
- Unsupported captures stay leads. Only the research gate assigns support statuses. Missing or blocked sources do not prevent unrelated product QA.

Use current route rules, not this summary as a permission grant. Source withdrawal, final stops and retention limits apply to library copies and every later assignment too.

For authorized original team research, see `../research/native-inputs.md`. Preparation reduces input errors; unchanged merge, gate and claim-export rules still apply.

## 3. Compose behavioral personas

Use gated scrubbed claim cards and the existing research export pipeline:

```sh
python3 scripts/ux_research.py persona-starter --run RUN --bundle RUN/bundle.json --gate RUN/gate.json
python3 scripts/ux_research.py export-personas --run RUN --bundle RUN/bundle.json --gate RUN/gate.json --hypotheses persona.hypotheses.json --audience-id AU-product
python3 scripts/ux_research.py persona-intake --run RUN --bundle RUN/bundle.json --gate RUN/gate.json
```

These commands run from the skill folder. Use the returned verified QA packet and scenario paths, not guessed or stale review copies. Author safe concrete inputs and real task steps; templates do not prove execution.

Each persona must separate:
- Source-supported facts: claim IDs, current gate, source scope and dates.
- Synthetic behavioral assumptions: goal, context, familiarity, constraints, decision criteria, expected recovery and falsifying tests.
- Unknowns: frequency, population share, unsupported preferences and missing research.
- Product binding: product/PRD and task IDs, fit rationale, version and safe input conditions.

Create a small diverse set of meaningful task behaviors rather than many cosmetic variants. A comparison-focused returner and an interrupted first-time user are useful only when they change the tested path. Brief-derived scenarios remain explicitly synthetic and exploratory when research is unavailable.

Research gate success validates a process; it does not make every claim usable.
Use only current exportable cards with observed counting/context evidence that
is not also counter-evidence. Counter-only claims, including the same evidence
relabeled as support or context, cannot motivate a research persona. Keep every
counter link and the original claim history. Safe separate support/context plus
counter-evidence stays explicitly conflicting; it is not upgraded to support.

Reject inferred/unknown motivation evidence, explicit synthetic or LLM sources,
grade-E material even in mixed claims, and unresolved or confirmed virtual-person
captures. Source review applies only to that exact capture and inherited flags;
additional excerpt flags need their own review. Existing injection, stop,
privacy and withdrawal checks still apply. Blocked cards expose no source prose.
Do not change an evidence type/status or invent a clearance to obtain a pass:
review actual permitted evidence, remerge/regate and author a reviewed version.
Safe single-voice and lead-only context remain exploratory, never population
evidence. With no usable research, retain the scenario as a PRD hypothesis
without research claim IDs; do not call it a researched persona.

## 4. Retain versions and explicitly approve reuse

Use a task-owned local library. Keep stable persona IDs with immutable versions, provenance references, creation/review dates and lifecycle state. Store minimized summaries, never copied raw posts, identity data or secrets. Retain the prior version's history; changes create a new version rather than silently changing the basis of earlier QA.

Before every reuse and again before dispatch:
1. Recheck current source/gate state, file integrity, withdrawal/stop flags and retention deadlines through the supported source intake.
2. Reconfirm product, PRD and task fit. Another product requires explicit remapping and a new reviewed version, never automatic transfer of assumptions.
3. Bind the selected exact version to the new build, task, safe data and scenario.
4. Refuse stale, retired, withdrawn, stopped or unverifiable dependencies. Revalidate through permitted research or keep the scenario unverified; never relabel an old snapshot as current.
5. Apply content deletion/minimization when required while keeping non-content audit history where permitted. A retirement record alone does not satisfy retention cleanup.

The CLI commands for local lifecycle and assignment bookkeeping are described below. These checks are not a perpetual source monitor: the host must obtain current permitted source state and semantic fit before relying on a stored persona.

Updated admission also applies after restart to previously stored profiles and
their runs, including report/compare. A rejected old motivation blocks reuse and
current results; it does not silently downgrade a sourced persona or delete its
payload. Review and explicitly import a corrected revision. Admission failures
alone do not authorize pruning; confirmed retention disposition remains separate.
Unchanged valid bindings retain their revision and fingerprint. Use this updated
skill for continuing old runs; older installed copies do not enforce this boundary.

## 5. Plan isolated bounded workers

Fix the task matrix, worker ceiling, total time and retry limits before dispatch. Assignment identity is persona ID/version × PRD task × test condition. Each row includes current build, scenario ID, starting state, synthetic fixture, device/input, expected outcome, interruption/recovery checks, stop conditions and evidence directory.

For each mapped PRD excerpt, enumerate its separate obligations before dispatch. Map each obligation to criterion indices or explicitly exclude it with a concrete reason. A saved step, visible resume guidance and restoration after clicking are three different obligations. Independently review this coverage against the whole excerpt; the validator cannot detect an omitted meaning. New host-authored runs must declare this coverage. Legacy plans remain readable with `coverage_unassessed`, never full requirement coverage. Passing selected criteria does not pass an omitted obligation.

Use available host-native workers, without hardcoded models/providers or an autonomous network scheduler. Claim a row once and track its owner and status. Give workers separate sessions, synthetic fixture namespaces and evidence directories. Do not share mutable accounts, browser state or test records. If isolation or same-host request serialization cannot be guaranteed, run serially. Worker concurrency does not lift external research access rules.

Each handoff carries only the selected scrubbed persona, task-specific facts/assumptions, safe inputs, grants, applicable access/evidence rules and stop conditions. Do not expose other workers' conclusions before their first pass. Consolidation and priority second-pass review happen afterward. A timeout, missing tool, unsafe gate or crashed worker yields blocked/incomplete work, not a successful test. Reassignment retains the failed attempt and stays within the original budget.

## 6. Exercise decisions and recovery, then replay

For every assigned task, collect actual actions and observed transitions:
- Entry state and the information used for the next choice.
- Inputs and choices before/after back navigation, validation and rerender.
- Interruption, return, error feedback, retry/cancel and recovery.
- Final outcome compared with intended values, plus failure/abandonment conditions.
- Build, device/input, capture times, artifact receipts and untested states.

For keyboard error/retry tasks, use `keyboard-recovery.md`. Check transient busy
and failure states, not only modal entry/exit or eventual completion.

Screenshots supplement action traces; they do not replace them. Separate synthetic persona reasoning from observed product behavior and the technical accessibility audit. A worker's “success” statement is not outcome evidence. Use the existing bundle validator and second-pass requirements; inspect provenance and observations, not only schema acceptance.

After an authorized change, replay the same persona version, task, start data, device and input on the new build. Link baseline, change and replay; test adjacent regressions and preserved intent. A changed persona or task is additional coverage, not the original task's replay. Keep stale evidence as history, never a current pass.

## 7. Local tool contract

The local `scripts/ux_personas.py` entry point and `uxpersonas/` package provide library lifecycle and assignment bookkeeping. Run from the skill folder. Inputs below are authored local JSON files, not CLI-generated research or execution evidence; inspect shipped help and input validation before use:

```sh
python3 scripts/ux_personas.py --help
python3 scripts/ux_personas.py import --library LIBRARY --input profile-input.json
python3 scripts/ux_personas.py import-research --library LIBRARY --research-run RESEARCH_RUN --input research-mapping.json
python3 scripts/ux_personas.py list --library LIBRARY --product PRODUCT_ID
python3 scripts/ux_personas.py reuse --library LIBRARY --product PRODUCT_ID --persona PERSONA_ID --revision 1
python3 scripts/ux_personas.py plan --library LIBRARY --run NEW_RUN --input swarm-input.json
python3 scripts/ux_personas.py claim --library LIBRARY --run NEW_RUN --worker WORKER_ID
# Host worker performs the real assigned task before authoring a receipt.
python3 scripts/ux_personas.py record --library LIBRARY --run NEW_RUN --input receipt.json
python3 scripts/ux_personas.py report --library LIBRARY --run NEW_RUN
python3 scripts/ux_personas.py replay --library LIBRARY --baseline BEFORE_RUN --run AFTER_RUN --build-id build-2 --artifact build-2.bin --isolation-id fixture-v2 --confirm-starting-state --confirm-isolation
python3 scripts/ux_personas.py compare --library LIBRARY --baseline BEFORE_RUN --run AFTER_RUN
# Only retry eligible incomplete work within the original budget.
python3 scripts/ux_personas.py retry --library LIBRARY --run NEW_RUN --task TASK_ID
# An uncertain fixture-write outcome needs actual inspection and an explicit attestation.
python3 scripts/ux_personas.py retry --library LIBRARY --run NEW_RUN --task TASK_ID --reconciliation inspected-outcome.json
# Close an uncertain write without another attempt, after actual host inspection.
python3 scripts/ux_personas.py settle --library LIBRARY --run NEW_RUN --task TASK_ID --inspection inspected-final-attempt.json
python3 scripts/ux_personas.py retire --library LIBRARY --product PRODUCT_ID --persona PERSONA_ID --reason 'Source withdrawn; block reuse'
python3 scripts/ux_personas.py prune --library LIBRARY
```

Import distinguishes `prd_hypothesis` from `gated_research`; both remain synthetic. Retain exact PRD excerpt/hash mappings and, for gated research, authoritative research-run references. Missing live research may justify a separately labeled PRD hypothesis, never a silent downgrade of a rejected research persona. Reuse, claim and report revalidate local PRD/research dependencies and the active current persona revision. These are integrity and lifecycle checks, not independent live network verification. Retirement removes derived profile payloads from retained library revisions and leaves a non-content tombstone; research-run cleanup still follows its own retention contract.

`prune` reports `result: pass|blocked|partial` and
`library_cleanup_complete`. Any blocker returns CLI exit 1; partial results
retain the confirmed retirements already completed. Uncommitted source-retention
edits, missing bound sources or unreadable state are not a clean success and
never authorize deletion. Review the recorded blocker. For confirmed withdrawal,
use explicit `retire`; restore verified state for other check failures.
A mirror may invalidate reuse but cannot replace authoritative cleanup evidence.
Neither result certifies cleanup of research runs or separately exported copies.

Only invoke commands present in that installed revision. Missing commands are an implementation gap, not permission to invent files that look like successful receipts. Existing `ux_research.py export-personas` exports a gated packet; it is not itself a persistent library or a worker scheduler. Host tools perform the real QA. A local report describes recorded assignments and their evidence limits, not independently verified task success.

## 8. Library input contract

There are no standalone JSON Schema files for these inputs. The installed validators are authoritative: `uxpersonas/library.py` (`import_profiles`, `prd_context`) and `uxpersonas/swarm.py` (`create_plan`, `_receipt`). The following is a structural template, not runnable evidence. Replace paths, hashes and excerpts with actual inspected artifacts.

```json
{
  "schema_version": "ux-persona-library-input.v1",
  "product_id": "demo",
  "mode": "prd_hypothesis",
  "review_days": 30,
  "context": {
    "prd_path": "/absolute/product/PRD.md",
    "prd_sha256": "<SHA-256 of current PRD bytes>",
    "requirements": [
      {"id": "REQ-1", "source_anchor": "Recovery", "excerpt": "<exact substring of current PRD>"}
    ]
  },
  "personas": [
    {
      "persona_id": "PER-interrupted",
      "label": "Interrupted comparer",
      "goals": ["Compare two options"],
      "behaviors": ["Return to the list before choosing"],
      "contexts": ["An interruption during comparison"],
      "assumptions": ["The user resumes the unfinished task"],
      "unknowns": ["Frequency of this situation"],
      "requirement_ids": ["REQ-1"],
      "claim_ids": []
    }
  ]
}
```

Top-level required fields are exactly `schema_version`, `product_id`, `mode`, `context`, `personas`; optional fields are `review_days` and `research`. Context and persona objects use exactly the fields above. Import 1–32 personas. Each profile list other than `claim_ids` has 1–24 unique nonempty strings; labels are at most 160 characters. Requirement IDs must reference the 1–64 unique cited requirements, whose excerpts match current PRD bytes. The anchor is an authored locator, not independently verified semantics.

For `gated_research`, add `"research": {"run": "/absolute/RUN", "bundle": "/absolute/RUN/bundle.json", "gate": "/absolute/RUN/gate.json"}` and supply nonempty exportable `claim_ids` matching `CLM-[0-9a-f]{8}` (at most 32). PRD hypotheses require an empty claim list and forbid `research`. No user-written support status is accepted.

`review_days` is an integer 1–90, default 30; changing it creates a new revision, not an in-place deadline extension. An identical, still-current active import is idempotent. Reuse permits only the latest active revision and fails closed when PRD bytes, research binding or review validity changes. `list` marks invalid rows `reusable: false` with a blocker rather than returning their payloads. Keep the library outside the installed skill tree.

## 9. Swarm input contract

This template assumes the current `demo/PER-interrupted` persona maps to `REQ-1`. Replace build identity and artifact hash with actual inspected values:

```json
{
  "schema_version": "ux-persona-swarm-input.v1",
  "product_id": "demo",
  "build": {
    "id": "build-1",
    "artifact_path": "/absolute/product/build-artifact",
    "sha256": "<SHA-256 of current artifact bytes>"
  },
  "max_parallel": 2,
  "lease_seconds": 300,
  "max_attempts": 2,
  "tasks": [
    {
      "id": "TASK-1",
      "persona_id": "PER-interrupted",
      "requirement_ids": ["REQ-1"],
      "goal": "Compare options without losing the selected filter",
      "starting_state": "Fresh synthetic session at the product list",
      "actions": ["Select a filter", "Open a detail", "Return to the list"],
      "decisions": ["Choose a detail using the visible comparison information"],
      "success_criteria": ["The final list retains the selected filter"],
      "recovery_criteria": ["After interruption and return the selection remains"],
      "data_namespace": "fixture-task-1",
      "resource_id": "product-host-a",
      "side_effects": "read_only",
      "stop_conditions": ["Stop at login, real-account mutation or lease expiry"]
    }
  ]
}
```

Required top-level fields: `schema_version`, `product_id`, `build`, `tasks`. Limits are optional: `max_parallel` 1–8 (default 2), `lease_seconds` 30–1800 (default 300), `max_attempts` 1–3 (default 2). Unknown top-level/build fields are rejected, including misspelled limits. A plan has 1–128 tasks. Each task has the fields shown plus optional `requirement_coverage`; the six string-list fields have 1–64 unique nonempty strings. IDs use letters/digits and `_.-`, start with a letter/digit and have at most 64 characters. Task IDs and data namespaces must be unique. Requirement IDs must belong to both the selected persona and current PRD.

New host-authored runs add `requirement_coverage` to each task:

```json
[{"requirement_id":"REQ-1","obligations":[
  {"id":"preserve-filter","description":"Retain the selected filter after returning",
   "criterion_refs":[{"kind":"success","index":0}],"exclusion_reason":null},
  {"id":"keyboard-flow","description":"Complete the flow with keyboard alone",
   "criterion_refs":[],"exclusion_reason":"This task uses pointer input; full keyboard flow remains untested"}
]}]
```

Declared coverage must include exactly the mapped requirement IDs, unique obligation IDs and valid zero-based criterion references. Each obligation has either references or an exclusion, never both. Claims/reports label it `declared_host_review_required`; absent coverage is `coverage_unassessed`. Neither status proves semantic completeness.

Reports add `requirement_results`: each declared obligation resolves to `passed`, `failed`, `not_run` or `excluded` using only the current attempt's criterion observations. Missing observations and previous-attempt results cannot supply a pass. A requirement is `passed` only when all its declared obligations and the task pass; exclusions/missing observations remain `incomplete` (or `excluded` if every obligation is excluded). Legacy undeclared coverage remains `unassessed`. `coverage_summary` counts requirement assignments, not unique PRD requirements or people, and separately counts obligations. `all_declared_requirements_passed` never proves that the PRD interpretation was complete or the product is ready. Surface excluded obligations and their reasons even when task counts show all passed.

`report` can read a superseded persona revision only when both the original and
current revisions still pass existing validation. Its task is currently blocked
with `current_binding_valid: false`; current results are empty and coverage is
unassessed. Prior evidence is explicitly `historical_result`,
`historical_requirement_results` and `historical_requirement_coverage`, with
`recorded_status` and separately labeled `historical_counts`. Other valid tasks
retain their current results. Expiry, withdrawal, changed research/PRD/build and
integrity failures still block reporting. Claim/record/retry never use this
exception. History does not authorize a retry or a new run to evade uncertain
effects or attempt limits; preserve and reconcile prior work first.

`side_effects` is `read_only` or `owned_fixture_write`; the latter still needs the existing scoped grant. The run path must not exist and its parent must exist. The tool creates a private run/evidence directory. Build artifact hashes bind supplied local bytes, not a deployed URL's identity; the host must verify that correspondence.

Assign one `resource_id` to every task sharing a browser/account/data fixture or external product host so leases serialize them. Different arbitrary IDs do not prove isolation. Use parallel slots only for verified independent resources; same-host external requests remain serial. Claims return the current persona binding, attempt, private evidence path and lease. The CLI does not launch a worker or navigate a browser. Stop at lease expiry; the next state read records `inconclusive`. Only failed/blocked/inconclusive tasks can be explicitly retried within `max_attempts`, retaining earlier receipts and captures.

Each task has a stable `operation_id` persisted before dispatch and kept across retries. It is not automatic idempotency at the application. An inconclusive `owned_fixture_write` quarantines its resource so other tasks cannot reuse uncertain state. Before retry, stop the current attempt's worker, inspect actual fixture state and provide exactly `operation_id`, integer `attempt` from its claim (or `attempts` in the report), `outcome` (`not_executed` or `effects_inspected_safe_to_retry`), `note`, and `worker_stopped: true`. An earlier attempt's inspection or an input without `attempt` is rejected without releasing quarantine. Do not merely update an old document's number: inspect the current attempt first. Legacy state without an operation ID uses its recorded lease token; keep tokens private. Reconciliation is a host attestation, not independently verified proof. A timeout or lost acknowledgement never establishes non-execution. The scheduler cannot terminate host workers or authorize denied actions.

The task ID is a correlation namespace, not a universal API idempotency key. Different mutations need distinct stable per-action keys in the target tool's required format; reuse a key only for the identical action retry. Never raise the budget or create a new run to evade uncertain effects.

For an inconclusive owned-fixture write, `settle` closes that task permanently without retry, including after `max_attempts` is exhausted. First stop the current attempt's worker and inspect actual fixture state. Supply exactly `operation_id`, integer `attempt` from its claim, `worker_stopped: true`, `outcome` (`not_executed` or `effects_inspected_safe_for_other_tasks`), and a concrete `note`. An old attempt's inspection is invalid. This host attestation is not independently verified or permission for a denied action; never manufacture one to unblock work.

Settlement preserves the inconclusive outcome, attempts, receipts and history; later receipts and retries remain blocked. Exact repeats are idempotent; conflicting inspections are rejected. Other tasks can claim the resource only if no other uncertain write or active lease blocks it, their starting state is safe and their existing authorization still applies. Current PRD/research/build and receipt-integrity checks remain required. Reports show the settlement separately, `retry_allowed: false`, and shared-resource `resource_quarantined`; none is a QA pass.

Newly created or mutated runs use `ux-persona-swarm-state.v3`. Older readers must reject them rather than use an unbound inspection or ignore settlement. Current code reads legacy v1/v2 runs without rewriting a read-only, unexpired report. A valid state mutation upgrades the envelope while preserving existing attempts and history. Use the current tool to continue those runs; old software cannot enforce the new rules. Do not downgrade envelopes. Legacy inspection documents lacking the current attempt must be replaced only after fresh host inspection.

A legacy task already marked pending after an inconclusive write is not automatically safe. If its last inspection is unbound, claims for that task and its shared resource stay blocked; reports retain pending status with `retry_blocker`. After actual current-attempt inspection, the same `retry --reconciliation` command adds a `reconciliation_review` beside the original historical inspection/receipt without changing attempts or budget. Exact repeats are idempotent; conflicts preserve the first review. The review is checked again before dispatch. No command can stop a worker already launched by old software; the host must inspect existing execution before continuing.

## 10. Receipt and cleanup contract

`ux-persona-swarm-receipt.v1` requires exactly `schema_version`, `task_id`, `worker_id`, `lease_token`, `build_sha256`, `persona_revision`, `profile_sha256`, `outcome`, `reason`, `steps`, `criteria`, `artifacts`. Copy actual identity/binding values from the claim, never invent a lease. Outcomes: `passed`, `failed`, `blocked`, `inconclusive`, `skipped`.

- Steps (0–256): `{action, observation, evidence_ids}`.
- Criteria (0–128): `{kind, index, status, observation, evidence_ids}`. Kind is `success` or `recovery`; zero-based index refers to the authored criterion. Status is `passed`, `failed` or `not_run`; not-run rows use no evidence IDs.
- Artifacts (0–128): `{id, kind, path, sha256}`. Kind is `execution_log` or `screenshot`. Paths are relative to the run but must resolve inside this task/attempt's claimed evidence directory. Files must be private, nonempty and hash-matching. Logs are UTF-8; screenshots are validated bounded PNGs.

A pass requires observed steps, every success/recovery criterion passed, and referenced execution-log plus screenshot evidence. A failed executed task requires observed steps and at least one evidence-backed failed criterion; use blocked/inconclusive for no execution. `record` validates the active worker lease and current build/persona binding. `report` rechecks stored receipts and artifacts, including prior attempts, and always returns `product_ready: false`. These checks cannot determine whether an authored observation honestly describes the image or whether the browser truly ran; host review remains required.

`record` detaches caller input before checking identity and observations, then saves that same validated snapshot. After artifact validation and complete state serialization, it rechecks the original lease immediately before handing bytes to atomic storage. Reaching the exact deadline or finishing later rejects every outcome with `lease_expired`, preserving the saved run and evidence. Preserve the original captures, inspect the worker and possible effects, and read the run report; the next read records the existing inconclusive transition and quarantines an uncertain owned-fixture write. Existing explicit retry/settlement rules still apply. A rejected receipt neither renews a lease nor authorizes replay. If the lease was already expired on entry, the existing load-time inconclusive transition remains in effect.

The cutoff is the handoff to the atomic writer, not the completion time of filesystem writes. A write admitted before expiry can finish later. After a storage error or lost acknowledgement, inspect the saved state before deciding whether another record attempt is appropriate; never rerun the product action merely because the save response was lost. This boundary does not stop external workers, authenticate evidence or upgrade synthetic fixtures into product/user observations. Older tool revisions cannot enforce this final admission check even though the state schema remains compatible.

The host can prepare a starter from its saved current claim, so the user does not need to hand-copy bindings or author JSON:

```sh
umask 077
python3 scripts/ux_personas.py receipt-starter --library LIBRARY --run NEW_RUN --claim claim.json > receipt-draft.json
```

Keep the claim and draft private: both contain the existing worker lease token. This command checks the current build, persona and exact active claim, but assigns nothing, renews no lease, records no outcome and does not save expiry transitions. It uses existing local validation locks. An expired, stale or mismatched claim is blocked; it never creates a missing library or run. `ux-persona-swarm-receipt-draft.v1` is deliberately not recordable. All current criteria start `not_run`, with no steps or artifacts; this means the draft has not assessed them, not that the product actions never happened. Criterion wording is separate drafting guidance, not evidence or authority.

The host uses actual observations and captured evidence to finish the draft, preserves any unknown outcome, chooses the supported outcome, removes `drafting_guidance`, and explicitly changes the schema to `ux-persona-swarm-receipt.v1` before `record`. Merely generating or renaming a draft cannot establish a pass. Existing receipt, privacy, evidence and lease gates still apply; the starter does not stop workers or reconcile uncertain effects.

Receipt authoring errors identify fixed schema locations (for example, `receipt.steps[0].observation`) without echoing rejected values. Describe an actually observed blank page explicitly rather than submitting an empty observation or inventing success. Privacy diagnostics remain rejections: use concise privacy-safe observations and descriptive evidence IDs, updating their matching artifact references. Timestamp-like IDs can trigger the conservative identifier check. Do not copy raw tool output or private local paths into prose; retain original evidence separately. Diagnostics do not automatically scrub content, alter results, renew leases or validate the truth of a rewritten observation.

`prune --library LIBRARY` explicitly removes derived profile payloads across all revisions of an affected persona when authoritative local source records show expiry/withdrawal. It retains retirement tombstones. Missing or transiently unreadable evidence produces a blocker without deleting payloads. Source/profile reuse remains blocked while current validity cannot be established.

No command detects remote deletion or schedules background cleanup. Review current permitted source state before reuse. Library retirement/pruning does not remove independently exported captures, QA profiles or reports; those require their own retention review and authorized cleanup. Neither a stale revision nor a locally retained capture may reactivate withdrawn support.

## 11. Compare the same journeys across builds

After recording a baseline and a replay, the host uses two existing run paths.
The user does not need to merge JSON reports or copy criteria, persona bindings
or evidence references:

```sh
python3 scripts/ux_personas.py compare --library LIBRARY --baseline BEFORE_RUN --run AFTER_RUN
# Packaged launcher: python3 scripts/remorsearch.py personas compare ...
# Structured output for integrations:
python3 scripts/ux_personas.py compare --library LIBRARY --baseline BEFORE_RUN --run AFTER_RUN --format json
```

The default is a readable report of each journey and its failed-to-passed,
passed-to-failed or unchanged recorded outcome. JSON also links the current
criterion observations to their verified artifact paths/hashes and includes
both runs' fingerprints and declared requirement coverage. A missing task,
changed persona version/journey/criteria/coverage/limit or an unobserved outcome
is explicitly not compared. Missing criterion observations remain not-run,
never improvements. Excluded/unassessed PRD obligations stay visible and cannot
become requirement passes.

The command revalidates both existing runs, active personas, local PRD/research
and retention state, build artifacts and receipt evidence. Keep the original
verified build artifact for each run; replacing its bytes in place blocks the
comparison. Resource IDs and synthetic namespaces may differ for isolation,
but the host must verify actual starting-data, device and input equivalence.
Matching declared text does not independently establish those conditions.

Comparison is read-only: it does not create runs, expire/renew leases, retry,
settle, prune or start workers. It preserves current attempts and all history.
An incomplete run can be compared again after the host safely continues the
existing work. Unknown writes still require the existing inspection/retry or
settlement boundary; opening another comparison grants no execution rights.

Exit 0 means all task and criterion outcomes were compared, including any
reported regressions; it does not mean the candidate passed. Exit 1 returns a
partial/blocked comparison when work cannot be paired or observations remain
missing. Invalid, stale or unsafe inputs are rejected with the existing error
codes (normally exit 2). Both product readiness and measured UX improvement
remain false. Separately saved comparison exports need their own retention
review.

**For hosts that summarize the JSON:** Pair the report and exit status from the
same invocation. Show task coverage, criterion gaps, and the directions of
observed changes separately. An exit of 1 can still carry a usable partial
report; keep its observed changes and mark what was not compared. If the report
is unavailable, say so instead of reporting no regressions. Use only permitted
evidence references. The comparison summary is not an acceptance decision.

| Synthetic input | Expected summary from an existing consumer |
| --- | --- |
| Exit 0, `complete`, 3/3 tasks, one failed-to-passed and one passed-to-failed | Show both directions, including the regression. Do not label the candidate as passed. |
| Exit 1, `partial`, 3/3 tasks, one baseline criterion `not_run` and candidate criterion `passed` | Keep observed task changes. Mark the criterion `not_compared`, not improved. Do not present the report as complete or discard it. |

## 12. Prepare the next build without rewriting the journey plan

When every baseline task has a current validated `passed` or `failed` receipt,
the host can prepare the same journeys on a different build. Keep both build
artifacts and the original baseline; supply only the new build and reviewed
fixture context instead of authoring a second full swarm input:

```sh
python3 scripts/ux_personas.py replay --library LIBRARY --baseline BEFORE_RUN --run AFTER_RUN --build-id build-2 --artifact build-2.bin --isolation-id fixture-v2 --confirm-starting-state --confirm-isolation
# Packaged launcher: python3 scripts/remorsearch.py personas replay ...
# Add --format json for ux-persona-replay.v1 structured output.
```

The default text output gives the assigned namespaces/resources and runnable
`claim`, `receipt-starter`, `record`, `report` and original-baseline `compare`
commands. Claim/receipt filenames in those instructions are placeholders. Save
them privately with `umask 077`; they contain active lease credentials. The host
performs each real assigned journey and fills the draft with fresh observations.
No command here invokes a model, browser, worker, account or external service.

Replay preserves exact persona revision/fingerprint, PRD bindings, task IDs,
goals, starting-state descriptions, actions, decisions, success/recovery criteria,
stop conditions, requirement coverage and limits. It generates a fresh namespace
per task and resource per original sharing group. Tasks that previously shared
one resource still share one new resource, so their serial execution constraint
remains. Legacy coverage stays unassessed; excluded obligations remain excluded.
The candidate artifact's ID and content hash must both differ from the baseline.

`--confirm-starting-state` records the host's review of starting data, device
and input equivalence. `--confirm-isolation` records its review of owned isolated
fixtures. These attestations neither grant permissions nor prove real isolation,
deployment identity or equivalent data. The generated IDs do not create/reset
fixtures: inspect the returned assignments and materialize or verify their owned
resources before claiming. Existing access and side-effect boundaries still apply.

Every new task starts pending with zero attempts and empty history. Previous
receipts, observations, artifacts, leases, operation IDs, settlements and grants
are not copied. Current PRD, source/gate/capture eligibility, withdrawal/retention,
persona revision, build and all existing receipt artifacts are revalidated.
Missing, historical-only, pending, active, blocked, skipped or uncertain baseline
work is rejected without expiring its leases or changing its state. Continue or
inspect that original run under its existing retry/settlement rules. A PRD-only
persona remains a hypothesis; a sourced synthetic persona is never a real user.

A private `replay-index.json` in the existing library reserves one destination
for each normalized baseline path and candidate content hash. The Library lock
serializes competing preparations. Different build names, isolation IDs or
destination paths cannot create a second budget for that pair. An identical
request at its original destination returns `status: existing`, preserving
attempts, running/expired leases, receipts and history. A reservation written
before a process stops can finish on the same still-absent destination with the
same inputs. If any partial destination exists, replay stops and preserves it
for inspection; it does not overwrite or delete it. Preserve the index with the
library. This guarantee covers replay preparation in that library, not manual
plans, copied libraries or the behavior of external workers.

The initial run state contains `ux-persona-replay-origin.v1` provenance, retained
in claim/report and comparison output after restart. It records the original
baseline state/build, candidate hash, exact journey fingerprint and host
attestations, with no result or authority. Comparing this candidate requires the
recorded baseline path and snapshot; a subsequently changed baseline is not
silently substituted. Readable comparison still distinguishes incomplete work
and observed transitions, and always leaves `product_ready` and
`measured_ux_improvement` false. Authenticity, actual execution and human benefit
need independent evidence. Older readers may display ordinary v3 task state but
do not enforce this new replay preparation/provenance contract; use this revision
for replay and its paired comparison.

## 13. Import a current research export into the library

After `export-personas`, the host prepares an explicit PRD mapping and imports the
committed packet without rewriting its behavioral hypotheses. The developer does
not need to author this JSON. Run from the skill folder:

```sh
python3 scripts/ux_personas.py import-research --library LIBRARY --research-run RESEARCH_RUN --input research-mapping.json
```

Use separate private research and library directories, outside the installed skill
and project. The mapping is a private regular JSON file (0600). It has this shape:

```json
{
  "schema_version": "ux-persona-research-mapping.v1",
  "product_id": "demo",
  "context": {
    "prd_path": "/absolute/product/PRD.md",
    "prd_sha256": "<current PRD bytes SHA-256>",
    "requirements": [
      {"id": "REQ-reuse", "source_anchor": "Reuse", "excerpt": "<exact PRD excerpt>"}
    ]
  },
  "source_export": {
    "bundle_id": "QAB-<actual committed packet ID>",
    "sha256": "<engine-state.json outputs qa-personas.json SHA-256>"
  },
  "personas": [
    {"source_persona_id": "PER-research", "persona_id": "PER-saved", "requirement_ids": ["REQ-reuse"]}
  ],
  "review_days": 30
}
```

The host reads the current committed packet ID and manifest digest; placeholders
are never accepted. Source IDs are explicit because research and Library ID
formats differ. Missing personas, stale/failed exports, unsafe motivation, wrong
PRD mappings, broad file permissions and overlapping state paths block intake.
It never silently falls back to PRD-only research.

Each mapping row defaults to creating a new destination. An identical current
re-import is idempotent. To deliberately update an existing destination, include
`expected_revision` with the actual current revision; a stale revision conflicts
without changing stored profiles. All selected profiles commit together while
the matching Library and research locks are held, in that order.

The resulting profiles retain goals, expected behavior and decisions as
hypotheses, context, assumptions and unknowns. `profile.research_scenarios` retains
the source scenario, likely failure, product falsification test, interview
question, missing concrete inputs and exact motivation cards. Import provenance
pins the committed export and projection. These fields are generated by the
adapter, not accepted as arbitrary additions to ordinary `import` input.

After restart, `reuse` and `claim` expose the retained hypotheses while current
PRD/research/retention checks still run. The output gives next commands for the
host. The host must separately author safe actions, starting state, criteria,
PRD obligation coverage and isolation before `plan`; importing does not grant
permissions, start a worker or assert an observation. Replacing an export does
not rewrite earlier imported hypotheses; import a reviewed revision explicitly.

Public-page `observed` evidence means the cited statement was actually captured.
It does not mean a participant or product behavior was observed. Institution
guidance and secondhand research summaries can remain contextual `lead_only`
motivation for P2/P3 synthetic hypotheses, with date/method/population and transfer
uncertainties preserved. Never upgrade them to demonstrated demand or UX benefit.

CLI-only observations currently cannot satisfy the swarm `passed` receipt's
screenshot requirement. Do not create a fake image, weaken the receipt or
represent CLI contract checks as completed browser UX QA. Report the actual CLI
checks separately and keep affected journey results incomplete.

## Deliverable

Report persona IDs/versions and behavioral coverage; sourced facts versus assumptions/unknowns; research gaps and current reuse checks; task assignment outcomes with actual evidence; reproduced findings with impact and priority review; same-task replay and adjacent checks; retired/blocked versions and remaining work. Keep “planned,” “recorded,” “validated,” and “actually exercised” distinct. No number of synthetic personas or completed rows establishes whole-product readiness.
