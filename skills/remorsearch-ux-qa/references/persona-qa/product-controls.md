# Product choices and selective rollback

These controls extend the existing persona Library, scale queue and UX loop.
They start no model, browser, process, worker, timer or external service.
Use the target project's current PRD and preserve its UI identity before selecting tasks.

## 1. Prepare the explicit choice

Use `uxpersonas.product_controls.propose(spec)` or:

```sh
python3 scripts/ux_personas.py configure --input reviewed-controls.json
python3 scripts/ux_personas.py select --input reviewed-controls.json --choice explicit-answer.json
```

The existing host may call `request_selection(spec, ask)`. Its `ask(proposal)`
callback must render the host's existing selection interface and return an explicit
answer, or `None` for cancellation. This library does not render a dialog.
A returned proposal has `ui_rendered: false`, makes no cost grant, and starts nothing.
The host must independently verify rendered labels, focus/keyboard behavior and cancellation.

The strict `ux-product-controls.v1` input contains:

| Field | Required content |
| --- | --- |
| product_id | Existing product identifier |
| context | Current PRD path/hash and exact requirement excerpts, using the Library contract |
| personas | Distinct saved persona IDs and current revisions, 1..1000 |
| models | Existing host route key, display label, exact model identity and reasoning effort |
| tasks | IDs, requirement IDs, goals, actions, success and conditional recovery criteria |
| style | Platform, hashed reviewed UI baseline, preserved invariants, per-component paths/properties/requirements |
| limits | Maximum unique personas, parallelism, turns, calls, budget in micro-USD, iterations and model allowlist |
| excluded_requirements | Optional explicit requirement/reason records; exclusions never imply whole-product completion |

Web component paths must end in `.module.css` or `.module.scss`. This is a declared
change boundary, not proof of computed CSS isolation. Use the target's existing compiler
to inspect `:global`, `composes`, shared tokens and transitive imports. The existing
Figma, readback, accessibility, browser and preserved-intent gates remain necessary.

The explicit answer contains the current `proposal_sha256`, `confirmed: true`,
ordered unique `persona_ids`, one `assignments` entry per selected ID, `parallel`,
`turns`, `max_model_calls`, `budget_microusd` and `max_iterations`.
The number of selected IDs is the count; multiple tasks or duplicated profiles do not
increase population coverage. No response, a stale digest or an unavailable route stops preparation.
The iteration value records the user's ceiling; the existing UX-loop packet must also
set `goal.max_iterations` within that ceiling. It is not a new auto-running optimizer.

## 2. Bind to actual execution

Pass the returned selection as `selection=` to the existing
`scale_entry.prepare_scale_goal(...)`, with the same selected IDs, assignments and
ScaleLimits. New live plans require this selection. Existing historical queue files
are not rewritten or replayed to add it.

Preparation checks current saved persona versions, PRD bytes, UI baseline, route identity
and limits, and preserves native requirement-specific checklists. The immutable queue plan
stores `product_selection`. ScaleExecution checks that binding on open and rechecks mutable
PRD/UI/model information before dispatch. It retains existing approval, price/destination,
budget, fencing, unknown-send and evidence checks.

A reasoning effort other than `none` requires the existing host provider to attest the
same `reasoning_effort` in addition to its exact model identity and adapter hash.
A label alone cannot turn another provider into Astra ultra. This extension does not add
an Astra adapter or bypass billing review. If the session permits only Dots Astra ultra,
offer only that verified host route and stop if it is unavailable. Never substitute Codex,
a new worker, another provider, or an inferred zero-cost route.

## 3. Attributed Korean synthetic seed input

```sh
python3 scripts/ux_personas.py seed-catalog
python3 scripts/ux_personas.py seed-input --input reviewed-seed-tasks.json
```

The catalog contains 32 minimized rows actually read from NVIDIA's documented dataset-viewer
API. Dataset revision, response hash, sampling limitations and CC BY 4.0 attribution are in
`uxpersonas/data/korea-seeds.v1.json` and `THIRD_PARTY_NOTICES.md`.
They are synthetic adult backgrounds, not Korean population estimates or actual user research.

A seed-task input has `product_id`, the current PRD `context`, and 1..32 `personas`.
Each persona has a unique `seed_id`, a product persona ID and the normal profile fields:
label, goals, behaviors, contexts, assumptions, unknowns and requirement IDs.
The output's `input` object goes through the existing Library import, which owns versioning.
Keep the surrounding provenance receipt with the project record. `seed-input` itself writes
no library and performs no generation.

Project behaviors are explicitly authored PRD hypotheses. Research enrichment still uses
the existing `import-research` route and its current gated sources. Never infer hand size,
grip, vision, motor ability or preference from age, province, occupation or nationality.
Observe/calibrate those separately, or leave them unknown.

For a provenance-only link to existing ergonomic profiles, run
`python3 scripts/ergo_qa.py bind-seeds --profiles profiles.json --bindings reviewed.json --out receipt.json`.
The `ergo-seed-bindings.v1` document declares `dataset` (`nvidia/Nemotron-Personas-Korea`),
`dataset_revision`, `seed_pack_sha256`, and 1..32 explicit `bindings` objects with
`seed_id` and `profile_id`. Use the installed pack's revision
`ada0f5b53a38bb5a30cce09358adde883c1ab63a` and canonical JSON digest
`677aba0ac8324b2006aad33a079b37c054a1fbabe905b83305917e6d00df31c1` (also returned
by `seed-input`), not the raw file or original API response hash. Each ID may appear
once; a conflicting existing `persona_ref` is rejected. The new receipt sorts
by seed ID and records a canonical digest of each profile; it does not change profiles,
bind historical sessions, or feed the reach model.

Reach evidence for this link remains unknown, even if the input profile already has a
number. Any future physical input must cite a compatible functional thumb tip-to-base
landmark and unit, resolve conflicts in the evidence, and keep measured/provided
values separate from any explicitly sourced synthetic reference. Without that evidence
there is no nearest match; do not fill by demographics or an average.

## 4. Improvement report and rollback selection

`uxloop.engine.report` includes per-improvement finding IDs, reason, expected effect,
changed paths, Figma reference, replay IDs, verification state and rollback availability.
Expected effect is not a measured user benefit. Public reports omit the stored file contents.

```sh
python3 scripts/ux_loop.py rollback --checkpoint CURRENT.json --fix fix-id
python3 scripts/ux_loop.py rollback --checkpoint CURRENT.json --fix fix-id \
  --confirm REVIEWED_CONFIRMATION_SHA --actor reviewed-user --reason explicit-selection
```

Without `--confirm`, the command returns a read-only preview. The host displays the exact
selection, dependent items, changed paths and revalidation requirement before taking an answer.
Repeat `--fix` for explicitly chosen dependent improvements. Do not silently add them.
The existing `code_write` grant is required and does not replace selection confirmation.

The preview binds current checkpoint/content hashes. Conflicting or unrecorded changes,
stale confirmation, missing original snapshots, a pending forward patch and held workspace
locks stop reversal. Unknown delivery is never retried automatically.
The supported atomic content scope is **one file**; multi-file changes stop before writing.
Recreating deleted originals also stops when their original permissions/metadata were not recorded.
The existing write-ahead record supports crash recovery, but is not multi-file atomicity.
Advisory locks coordinate cooperating writers; no filesystem compare-and-swap against
arbitrary noncooperating writers is claimed.

A successful reversal invalidates earlier acceptance. The same forward run cannot simply
reapply the reverted fix. Review the restored baseline, then use the existing replay and
adjacent-regression flow with fresh evidence. Until those gates pass the product remains incomplete.

## 5. Measured feedback and evidence limits

Reuse existing research acquisition/ledger, `ergo_experiments.py`, persona comparison and
bounded `uxloop` execution. Record a source and reading scope, a hypothesis, preregistered
acceptance limits, versions/conditions, baseline and candidate observations, an adopt/reject/hold
decision and regression evidence. Retain rejected outcomes and stop at the declared limits.

A human-use image may support visible contact, landmarks and grip under stated uncertainty.
A model estimate, a calibrated measurement and an unknown field must remain distinct.
Still images do not establish maximum motion range, discomfort, visual acuity or actual gaze.
No image analysis SDK or model is included by this change.

This release's tests use owned synthetic fixtures. They establish contracts and failure
handling; actual host dialogs, actual model execution, camera analysis, browser UX and human
benefit each need their own current observations.

## 6. Reduced motion must preserve task completion

Use the same existing, authorized synthetic progress or disclosure flow in two
fresh runs. Match build, initial state, viewport, input and action; vary only
the browser's reported [motion preference](https://www.w3.org/TR/mediaqueries-5/#prefers-reduced-motion)
(`no-preference` and `reduce`). Record how the preference was set and which
value the browser actually reports before the action. Record the authored
movement that the baseline actually shows and the reason any remaining
movement is essential to the function or information. Do not assume that
a necessary status message makes its decorative animation essential.

Before testing, define the expected settled state, next usable action and
observation limit. At the trigger and through completion, record actual focus,
visible and semantic state (for example, expanded where relevant), and the
available progress or completion cue. Verify within the same task bounds that
the reduced run suppresses the nonessential motion and still reaches the
intended usable result. A static cue can replace motion; identical animation
durations are not required. If the animation disappears but the flow stays
busy, focus is lost, the next action is blocked, or the result becomes
imperceptible, do not pass. A screenshot or an animation-end event alone does
not establish completion. Keep the observed timing and outcome for each run.

Report [WCAG 2.2 SC 2.3.3 (AAA)](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html)
for disabling nonessential interaction-triggered motion.
[C39](https://www.w3.org/WAI/WCAG22/Techniques/css/C39) is one technique, not a
requirement to use this CSS feature. Assess automatically started motion
under [2.2.2](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html)
only when its conditions apply, and applicable status messages under
[4.1.3](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)
separately. DOM evidence does not establish an assistive-technology announcement.
If no suitable existing flow or preference observation is available, mark
that comparison `not_run`. Browser emulation does not verify the operating
system setting or real-device behavior. If server-rendered initial paint or
the client handoff is relevant but unseen, mark it separately `not_run`;
do not infer it from a settled frame. A synthetic check is not a conformance
or product-readiness verdict.
