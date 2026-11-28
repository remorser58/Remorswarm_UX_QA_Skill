# ergoqa live web driver (`drivers/web/`)

## Local persona-qa quickstart

Run these commands from `skills/remorsearch-ux-qa/`. Use Node.js 22 with the
installed Playwright package. For the example, serve the bundled fixture in a
separate terminal with `python3 -m http.server 8765 --bind 127.0.0.1 --directory drivers/web/fixtures`.
Replace the URL and action targets when testing your own local product.

Viewport emulation covers Chromium's viewport, DPR and input settings. It does
not test a real device or grip, an on-screen keyboard's occlusion, safe areas,
or a screen reader. Inspecting ARIA state is a DOM check; screen-reader speech
still needs a separate test.

Before starting, create `agent.json` with your actual operator's model family
and model name (or `human` for a human operator):

```json
{
  "model_family": "human",
  "model": "manual operator",
  "input_channel": "screenshot+a11y",
  "persona_arm": "neutral"
}
```

This combined channel permits both screenshots and state inspection. A blind
screenshot-only pass uses `"input_channel": "screenshot"`; run a separate
`a11y` or `screenshot+a11y` session for state checks. The server rejects
`inspect` in screenshot-only sessions.

On a host that cannot start Chromium, export the browser server's
`REMORSEARCH_BROWSER_WS` endpoint before command 3 (see the host setup below).
The five command stages are:

1. List device IDs and their viewport, DPR and input.

   ```sh
   node drivers/web/ergo_drive.mjs devices
   ```

2. Create a valid scenario with an empty step list and no assumed success criteria.

   ```sh
   node drivers/web/ergo_drive.mjs init --url http://127.0.0.1:8765/inspect.html --device desktop-1920 --task 'Check required options, error focus and order request persistence.' --out sc.json
   ```

3. Start one interactive session and leave it running in its terminal.

   ```sh
   node drivers/web/ergo_drive.mjs serve --scenario sc.json --device desktop-1920 --agent-json agent.json --out runs/ --run-id R-local --port 9477
   ```

4. In another terminal, send one request at a time. Repeat `act`, `inspect` and
   `screenshot` as you test the flow; each prints JSON.

   ```sh
   node drivers/web/drive_client.mjs --port 9477 act '{"action":"type","target":"#request","text":"No peanuts please"}'
   node drivers/web/drive_client.mjs --port 9477 act '{"action":"tap","target":"#submit-associated"}'
   node drivers/web/drive_client.mjs --port 9477 inspect
   node drivers/web/drive_client.mjs --port 9477 screenshot
   ```

   The fixture's omitted part produces `Choose a part.` and focuses `#part-a`.
   Inspect shows the request value and the error reference. Open the returned
   PNG path to view the screenshot. `observe` also captures a screen without acting.

5. Finish with the task's actual result. This omission example has not completed
   an order, so it finishes unsuccessful (exit 3).

   ```sh
   node drivers/web/drive_client.mjs --port 9477 finish '{"success":false}'
   ```

The `ready` event identifies `runs/R-local/` and the initial PNG. Each action or
screen capture writes `S-*.json`, `S-*.png` and a CSS-scale PNG there. Inspect
writes private, redacted `I-*.json` files in the same directory and returns their
`inspection` paths; it does not add an action or capture a screenshot. Finish
writes `run.json`, closes this session and stops serve. It can take up to about
a minute for the existing focus walks and reflow checks. A success claim is used
only when the scenario has no measured success criteria; an entered value being
lost still needs to be recorded and considered in the release decision.

For each required option, submit once with just that option omitted. After each
failed submit, check feedback, focus, `aria_invalid`, the described-by text and
`error_associated`. Compare every entered non-sensitive value before and after
validation, coupons, back/forward navigation and re-renders. Review
`reading_order` at intermediate screens too. On this fixture, choosing `#part-a`
then submitting exposes the address error; `#submit-unassociated` demonstrates
missing association and unchanged button focus, and `#keep` / `#clear` preserve
or clear the request during a re-render.

## Task-walk coverage

Before acting, enumerate task × required viewport × input rows, including a
whole keyboard-only pass, not just a Tab on the entry page. Keep exact CSS sizes.
For each row record reached screens, run/step/snapshot IDs, measurement output,
completion and remaining checks. Mark unvisited rows **not checked** (`untested`)
with the reason; do not remove them from the denominator or claim overall success.
At mobile widths, ground actions in currently visible controls. If a desktop
link is hidden, inspect the current mobile navigation rather than retrying that
hidden selector. A grounding failure is not proof the product task failed.

Measure **every screen reached during the task walk**, including detail views,
dialogs, saved lists, booking management and error/confirmation states at each
required viewport. Perform the walk through `serve` or authored `run` steps:
every action already writes measured geometry and text properties beside its
PNG. Use `observe` after asynchronous state changes and scroll to expose
below-fold actions. Analyze the **whole recorded run**, not just the initial
snapshot. `inspect` alone is not an ergonomic measurement. When a host browser
drives the task, collect equivalent per-screen measurements or replay those
transitions through the driver; starting another session at the entry URL does
not measure the screen the host browser reached. Keep `serve` running in one
terminal and send client commands from another, as in the quickstart above.

On Chromium 141 / Playwright 1.56.1, capturing an opened native `<select>`
popup can time out or disturb mobile emulation. If a capture reports a changed
viewport or pixel mapping, do not treat it as valid geometry. Preserve the
failed run; in a separate run, focus the closed select with Tab, choose with
arrow keys and Tab away without opening the popup. This can continue page
measurement, but does not validate the native popup or a whole keyboard task.

Report automated analyzer warnings at P0–P2 as individual findings. Summarize
lower-priority warnings as one row per rule and screen (`extra.screen`) with
finding/element counts, examples and observation/snapshot IDs; `swarm` writes
these `summaries` and `--list-threshold P3` lists everything. Task-state, timing,
focus and judgment results always stay individual.

Before reporting, check that each reached screen has a measurement snapshot and
analysis evidence. Missing measurements, capped reflow/focus probes or unsupported
text remain named coverage gaps, not passed checks. After a confirmation appears,
observe whether it disappears and whether the outcome/reference can be recovered.
For destructive actions on owned test data, check confirmation, undo and persisted
state. Do not infer irreversibility from a label or click alone. For timed text,
declare the observed selector as a `transient_text` timing window and replay with
a wait covering its disappearance (see "What is measured", Timing windows); no measured window
means timing is not checked, not passed.

## Editing the generated scenario

`init` validates the URL and catalogued device, includes every required scenario
field (including `surface.kind`), and refuses to overwrite an existing file.
`--task` is optional; the schema retains the name `task_goal_ko` even for English
task text. Interactive actions do not require editing `steps`. To replay a
scripted flow, add actions to `steps`, then use `run`:

```json
"steps": [
  {"action": "type", "target": "#request", "text": "No peanuts please"},
  {"action": "tap", "target": "#part-a"},
  {"action": "tap", "target": "#submit-associated"}
]
```

For a product with a completion page, replace `"success": null` with actual
completion criteria. All listed conditions must hold:

```json
"success": {
  "selector_visible": "#order-confirmed",
  "text_present": ["Order confirmed", "No peanuts please"],
  "url_contains": "/confirmation"
}
```

These are JSON fragments to place in the generated object. Use the names and
selectors your page actually exposes. A completion message alone does not show
that options, quantity, price and entered requests survived the flow; use state
checks and the confirmation details as well.

For material fields, opt into `success.task_checks`. Indices are **1-based action
indices** (`steps[0]` is step 1); `after_step` checks the captured state after that
action. Omit it for a fresh final capture. All declared checks must pass; a later
restoration cannot erase an earlier mismatch. `from_step` references an authored
`type` action's text, requires that action to have executed successfully, and
avoids copying the expected text. Interactive `/act` uses the same step indices
and checks; declared but unvisited checkpoints remain unevaluable.
An interactive source action must match the authored text; changed input is
unevaluable. Authored source redaction also applies to that interactive action.

```json
"steps": [
  {"action":"type","target":"#request","text":"No peanuts please","redact":true},
  {"action":"tap","target":"#submit"}
],
"success": {
  "selector_visible":"#confirmed",
  "task_checks":[
    {"id":"request-after-error","selector":"#request","property":"value","from_step":1,"after_step":2,
     "basis":{"kind":"task","reference":"Preserve the dietary request during correction."},
     "severity":"P1","consequence":"A required dietary request may be lost during recovery."},
    {"id":"request-final","selector":"#confirmed-request","property":"text","from_step":1,
     "basis":{"kind":"task","reference":"Submit the entered dietary request."},
     "severity":"P1","consequence":"The final request must match the entered request."},
    {"id":"option-final","selector":"#option","property":"checked","expected":true,
     "basis":{"kind":"task","reference":"Submit the selected option."},
     "severity":"P2","consequence":"The selected option must survive submission."}
  ]
}
```

Each check has a unique 1–128 character ID, CSS selector (≤1000 characters),
`property: value|text|checked|count`, exactly one of `expected`, `from_step` or `from_check`, and
authored `severity: P0|P1|P2|P3` plus `consequence` (≤1000 characters; no field
values). At most 64 checks. `expected` is a string (≤5000 characters, including
empty), a boolean for `checked`, or a non-negative integer for `count`.
`count` requires a visible `container`; only rendered matches inside it count.
Comparisons are exact: author `expected:""`
for intentional reset/cleanup, or the expected normalized string for deliberate
normalization. Missing, multiple, hidden or credential targets are unevaluable;
no label or demographic inference is used. Password/hidden/credential fields,
URL fields and value/URL attribute predicates are excluded.
Use plain CSS IDs/classes/structure. Literal attribute predicates, CSS escapes
and Playwright selector engines are rejected for task checks and redacted input.

`type.redact:true` hides that source text in saved actions/errors and masks its
selected region in captures. A referencing check inherits masking; a literal
expectation can use `redact:true` itself. These are explicit regions, not a
general privacy scrub: use owned synthetic input and declare every sensitive
display copy. Regular snapshots still omit input values. Results keep only
ID/selector/property/checkpoint/pass/fail/unevaluable and step/capture anchors;
they never contain actual/expected values or value hashes. P0/P1 still need
capture review. `TI-01` reports comparison failure only for the recorded owner;
authored consequence/severity do not prove downstream harm.

Supply `basis:{"kind":"product"|"task","reference":"visible promise or task rule"}`
for every grounded expectation. It is optional in the schema: missing basis loads
but records an unevaluable candidate (`reason:"expectation_basis_missing"`,
`comparison:"pass"|"fail"`), not a defect or pass.
Do not invent a preservation policy: changing the recipient may intentionally clear
a draft. `from_check` refers to an earlier captured check with the same property;
`delta` on counts expresses one approval → one new visible record (`1`), or
cancel/re-entry → no new record (`0`). Compare visible receipts/history, never
app storage or hidden keys. A same-run relation is an invariant, not metamorphic.

For a metamorphic comparison, opt into a fresh source/follow-up execution with
`follow_up` on the check. It requires `fixture:true`, `changes` drawn from
`back|cancel|reentry|edit_resubmit`, and `insertions:[{"after_step":N,"steps":[...]}]`.
The inserted steps use the ordinary action contract; `after_step:0` means before
the first action. The original run is preserved, the follow-up uses a new browser
context, and its run/captures are linked separately. Only use owned synthetic
data: replaying a prefix may submit again. Input cases name an authored `type`
step, `kind:blank|boundary|documented_valid|invalid`, `expectation:accept|reject`
and a product/task `basis`; documented alternatives are not automatically invalid.

For example, these are fields inside `success.task_checks`. The second check
counts rendered `.record` descendants of `#history` after one approval; the
follow-up then opens and cancels a draft before comparing with the source count.
`changes` is descriptive metadata, not generated actions. Insertion indices refer
to original steps; follow-up `input_cases[].step` refers to the expanded replay.

```json
[
  {"id":"before","selector":".record","container":"#history","property":"count",
   "expected":0,"after_step":1,"severity":"P1","consequence":"No request is saved yet.",
   "basis":{"kind":"task","reference":"Begin with an empty request history."}},
  {"id":"approved","selector":".record","container":"#history","property":"count",
   "from_check":"before","delta":1,"after_step":3,
   "severity":"P1","consequence":"One approval must create exactly one record.",
   "basis":{"kind":"product","reference":"Approve saves this request once; Cancel discards the draft."},
   "follow_up":{"fixture":true,"changes":["cancel"],
     "insertions":[{"after_step":3,"steps":[
       {"action":"click","target":"#new-request"},
       {"action":"click","target":"#cancel"}
     ]}]}}
]
```

`from_check` is the ID of a preceding check in the same run, with a strictly
earlier checkpoint and the same property. Count `delta` defaults to zero and may
be any safe integer; it is permitted only with `count` + `from_check`. A follow-up
compares the source check's observed scalar with the same visible property after
replaying its prefix plus insertions. `from_step` is only for `value`/`text`.
`text` reads `innerText`; neither text nor value comparisons trim or normalize.
Author the normalized literal only when the product itself performs that change.

Optional `input_cases` belongs to a check or its `follow_up`; it classifies
authored inputs rather than inventing formats. For example:

```json
"input_cases":[
  {"step":1,"kind":"blank","expectation":"reject",
   "basis":{"kind":"product","reference":"The field is visibly required."}},
  {"step":3,"kind":"boundary","expectation":"accept","boundary":"Maximum 60 characters",
   "basis":{"kind":"product","reference":"The visible counter permits 60 characters."}}
]
```

Each listed step must be a `type` action; `blank` requires `text:""`,
`documented_valid` requires `accept`, and `invalid` requires `reject`.
Only `boundary` carries a nonempty `boundary` description. Expectations need an
associated visible outcome check; classification alone never proves acceptance.
Invalid shapes/bounds are usage errors (exit 2). A valid but unavailable comparison
is unevaluable (exit 3 unless execution is blocked, exit 4).

With a visible completion page and a measured mismatch, `run.json` retains
`status:"completed"`, `success:false`, `success_basis:"measured"`, and the
driver exits **3**. Passing checks exit **0**; unevaluable checks yield
`success:null` unless another criterion failed. Captured completed mismatches
can be attached as defect evidence; the bundle keeps `task_success:false`.
Blocked/failed executions and missing captures retain their existing limits.
The opted property and visibility are sampled around each designated capture;
changed state is `unevaluable` with `capture_state_changed`. Cross-check/replay
scalars stay in private driver memory and are cleared after comparison; they are
never serialized. Temporary browser handles are disposed. Checks precede later
focus/reflow probes. Matching endpoints do not exclude a transition that returns
to the same state during capture; rapidly changing targets need another capture.

## Select one profile for a recorded run

From a writable work directory outside the installed skill, set `SKILL_DIR` to the absolute path of the skill folder containing `SKILL.md` (in a source checkout, `skills/remorsearch-ux-qa`). Use the same shell for the instructions below. Input and output paths such as `work/` and `runs/` belong to the work directory, not the installed skill.

```sh
SKILL_DIR=/absolute/path/to/remorsearch-ux-qa
if [ ! -e work/profiles.json ] && [ ! -L work/profiles.json ]; then
  python3 "$SKILL_DIR/scripts/ergo_qa.py" profiles --count 16 --seed 7 --devices galaxy-s24,iphone-15 --out work/profiles.json
fi
```

The command builds a default stratified list only when none exists.

`--profile` takes one `ergo-profile.v1` object, not the whole profiles document. Choose a profile ID and the device and orientation planned for the capture. The values below match `EP-01` in the stratified example above. For a different profile, set all three and choose a new output path.

```sh
PROFILE_ID=EP-01
DEVICE_ID=galaxy-s24
ORIENTATION=portrait
PROFILE_FILE=work/EP-01.json
python3 - "$PROFILE_ID" "$DEVICE_ID" "$ORIENTATION" "$PROFILE_FILE" <<'PY'
import json
from pathlib import Path
import sys

profile_id, device_id, orientation, output = sys.argv[1:]
profiles = json.loads(Path("work/profiles.json").read_text(encoding="utf-8"))["profiles"]
matches = [p for p in profiles if p["profile_id"] == profile_id]
if len(matches) != 1:
    raise SystemExit("Choose a unique profile_id from work/profiles.json.")
profile = matches[0]
attrs = profile["attributes"]
if profile["schema_version"] != "ergo-profile.v1" or (attrs["device_id"], attrs["orientation"]) != (device_id, orientation):
    raise SystemExit("Choose an ergo-profile.v1 profile for the planned device and orientation.")
with Path(output).open("x", encoding="utf-8") as file:
    json.dump(profile, file, ensure_ascii=False, indent=2)
    file.write("\n")
PY
```

The command refuses to overwrite an existing file. Keep `work/profiles.json` unchanged for analysis and use `PROFILE_FILE` and `PROFILE_ID` in the capture and attachment commands below.

### Capture and attach the selected profile

Use a matching scenario and set `PRODUCT_BUILD_ID` to the actual product build identity. The recorder keeps that operator-supplied identity on the run and its captures. Without it, do not claim same-build reproduction. A capture made with `--device` alone is for cross-profile analysis, not QA attachment as a recorded persona.

```sh
node "$SKILL_DIR/drivers/web/ergo_drive.mjs" run --scenario sc.json --profile "$PROFILE_FILE" \
  --build-id "$PRODUCT_BUILD_ID" --out runs/ --run-id R-persona-01
python3 "$SKILL_DIR/scripts/ergo_qa.py" analyze --runs runs/R-persona-01 --profiles work/profiles.json --scenario sc.json --out analysis.json
python3 "$SKILL_DIR/scripts/ergo_qa.py" attach --bundle qa/bundle.json --runs runs/R-persona-01 --profiles work/profiles.json \
  --scenario sc.json --bind "scenario-1=$PROFILE_ID" --receipts-dir receipts/ --out qa/bundle.ergo.json
python3 "$SKILL_DIR/scripts/validate_bundle.py" qa/bundle.ergo.json --artifacts-root receipts/
```

Ordinary profile-based capture uses `--profile`. Add `--bind-profile` to `run` or `serve` only when you need to pin the exact profile content and evaluator revision; otherwise the profile revision remains unverified.

## Binding a run to authored profile inputs

For a new run with an authored profile, add `--bind-profile` to `run` or `serve`.
This opt-in requires Python 3.10+ and a built-in catalog device matching the
profile orientation. The recorder pins digests of the bytes it read, canonical
profile content, resolved reach inputs and model source revision in `run.json`.
It does not store profile dimensions in the binding, calibrate captured coordinates,
or measure grip or anatomy. Matching digests establish consistency for the recorded
profile and selected reach-model revision, not capture authenticity.
A changed bound profile/model is rejected by default. Use `--analytical-rescore`
with `ergo_qa.py analyze` or `swarm` for a comparison, not an owner result.
`attach` refuses that changed analysis. ID-only captures can still be analyzed,
but their profile revision is unverified; their original task and capture
evidence is separate. Model predictions always remain inferred.

## State probes

A **committing task** creates, changes, deletes, sends or pays (order, booking, cancellation, profile save, message). Every committing task x viewport x input row needs the four probes below. Replays may submit again: use an owned synthetic fixture that starts each source/replay context with isolated, seeded state. `follow_up` does not reset a backend or pause for a manual reset. Without that isolation or authorization, stop at confirmation and mark the probes `not checked`. These templates do not authorize real charges, deletion or account changes; test-mode payment requires approved staging.

| Probe | Do | Pass when |
| --- | --- | --- |
| a Back/reopen | After completion, return to or reopen the completed step with the product's own control, then submit again | One record/charge/receipt, not two |
| b Keep | Open the cancel/delete confirmation, choose keep/close (or `press` Escape) | Saved state is unchanged |
| c Switch | Change item/date/recipient after entering dependent inputs | Stale selections, inputs and totals are cleared, or carried only where a visible product promise or task rule says so |
| d Error, fix, resubmit | Trigger a validation error, correct only the failing field, resubmit | Every other input and choice survives; one record |

Back is a control inside the page; the driver has no browser chrome (see "Not exercised"), so toolbar Back stays `not checked`. Compare rendered receipts/history (`count` with a visible `container`), never storage. Without visible evidence of record/charge count, a is `not checked`; b also needs saved content/status comparisons, since an unchanged count alone cannot prove unchanged state.

Replay prefix semantics: `follow_up` re-runs original actions 1..`after_step` in a new context, inserting after each named original index (0 = before step 1). Limits: 64 insertions, 64 actions each, 512 total replay actions. Its final capture is compared with the source checkpoint; provide `expected`, `from_step` or `from_check`, and `after_step` >= 1 (use a `snapshot` action for an entry checkpoint). Each check has its own replay: insertions are never shared. Missing/disabled targets yield `unevaluable` (`replay_failed`); any non-`ok` source step cancels all follow-ups, so keep exploratory attempts separate. `changes` labels a `back`/`reentry`, b `cancel`, c `reentry`, d `edit_resubmit`. The selector/property/container/`after_step` tuple must be unique per scenario.

Put these checks inside `success.task_checks` of an `init` scenario, author its `steps`, and execute `run` as described in "Editing the generated scenario" and "Commands". Use one scenario per probe/device row and an isolated fixture URL. For b, checkpoint before the synthetic delete/cancel; a and d must reach synthetic completion. Real destructive actions remain unauthorized. For d, also load **Error-recovery probe** below.

Fill every `<...>` from a screen reached in this run: selectors, step numbers, expected values and the visible promise quoted in `basis.reference`. Keep the other fields. Never leave a placeholder or borrow a selector or promise from another product; an unfilled probe is `not checked`. A missing `basis` records an unevaluable candidate, not a pass.

a, with its baseline (`M` < `N`, the commit step). If resubmit is visibly absent/disabled, omit that click: reviewed blocking evidence plus unchanged count is `done/pass` (duplicate prevention), not a successful resubmit. Otherwise perform it; an unexplained missing target is `not checked`:

```json
[
 {"id":"a-before","selector":"<record-row>","container":"<records-list>","property":"count",
  "expected":<fixture-seeded-count>,"after_step":<M>,"severity":"P1",
  "consequence":"Baseline before the commit.",
  "basis":{"kind":"task","reference":"<fixture starts with this many records>"}},
 {"id":"a-resubmit","selector":"<record-row>","container":"<records-list>","property":"count",
  "from_check":"a-before","delta":1,"after_step":<N>,"severity":"P1",
  "consequence":"Back or reopen, then resubmit, must not add a second record or charge.",
  "basis":{"kind":"<product|task>","reference":"<visible promise: one submission, one record>"},
  "follow_up":{"fixture":true,"changes":["back"],"insertions":[{"after_step":<N>,"steps":[
    {"action":"click","target":"<product Back/reopen control>"},
    {"action":"snapshot","label":"reopened"},
    {"action":"click","target":"<same submit control as step N>"}]}]}}
]
```

b. `K` is where the saved item is visible, before the real cancel/delete step. Compare each saved content/status field; use a summary containing them all or repeat this check with unique IDs/selectors. Also compare the saved-row count when available:

```json
{"id":"b-keep","selector":"<saved content and status summary>","property":"text",
 "expected":"<fixture-seeded saved summary>","after_step":<K>,"severity":"P1",
 "consequence":"Keep or close on the confirmation must leave saved data unchanged.",
 "basis":{"kind":"<product|task>","reference":"<visible confirmation text promising no change>"},
 "follow_up":{"fixture":true,"changes":["cancel"],"insertions":[{"after_step":<K>,"steps":[
   {"action":"click","target":"<cancel/delete control>"},
   {"action":"snapshot","label":"confirmation-open"},
   {"action":"click","target":"<keep/close control in the confirmation>"}]}]}}
```

c. The source path selects the target directly and does not retype the dependent field. The insertion at `k` (before that selection) makes the replay choose another item/date/recipient and fill the dependent input first. Add the carried check only when a visible rule says it is kept; with no grounded clear/carry rule, c is `not checked`:

```json
[
 {"id":"c-cleared","selector":"<dependent field, total or selection>","property":"<value|text|checked>",
  "expected":<value the rule states after the switch>,"after_step":<S>,"severity":"P1",
  "consequence":"A stale value from the previous item/date/recipient must not carry over.",
  "basis":{"kind":"<product|task>","reference":"<visible rule: changing X resets or recomputes Y>"},
  "follow_up":{"fixture":true,"changes":["reentry"],"insertions":[{"after_step":<k>,"steps":[
    {"action":"click","target":"<other item/date/recipient>"},
    {"action":"type","target":"<dependent input>","text":"<synthetic value>"}]}]}},
 {"id":"c-carried","selector":"<field the product promises to keep>","property":"value",
  "from_step":<n>,"after_step":<S>,"severity":"P2",
  "consequence":"An entry the product promises to keep was lost on the switch.",
  "basis":{"kind":"<product|task>","reference":"<visible rule: this entry is kept when X changes>"},
  "follow_up":{"fixture":true,"changes":["reentry"],"insertions":[{"after_step":<k>,"steps":[
    {"action":"click","target":"<other item/date/recipient>"},
    {"action":"type","target":"<dependent input>","text":"<synthetic value>"}]}]}}
]
```

## Error-recovery probe

Probe d uses the fixture/coverage rules in **State probes**. `M` is before commit; `k` precedes the fix; subsequent original steps correct the field and resubmit at `N`. `n` <= `k` types an unaffected input. Repeat its check for all unaffected fields/choices and review their `error-shown` captures too. At `N`, use the surviving input (`value`) or confirmation copy (`text`). For invalid text instead of omission, insert `type` before submit and set `clear:true` on the original fixing `type`. The record-count check repeats the same insertions in its own isolated replay; a source-only count would not test the error path.

```json
[
{"id":"d-before","selector":"<record-row>","container":"<records-list>","property":"count",
 "expected":<fixture-seeded-count>,"after_step":<M>,"severity":"P1",
 "consequence":"Baseline before the commit.",
 "basis":{"kind":"task","reference":"<fixture starts with this many records>"}},
{"id":"d-other-input","selector":"<unaffected input or confirmation copy>","property":"<value|text>","from_step":<n>,
 "after_step":<N>,"severity":"P1",
 "consequence":"Entries must survive the error and the resubmit.",
 "basis":{"kind":"<product|task>","reference":"<visible promise that entries are kept>"},
 "follow_up":{"fixture":true,"changes":["edit_resubmit"],"insertions":[{"after_step":<k>,"steps":[
   {"action":"click","target":"<submit control>"},
   {"action":"snapshot","label":"error-shown"}]}]}},
{"id":"d-one-record","selector":"<record-row>","container":"<records-list>","property":"count",
 "from_check":"d-before","delta":1,"after_step":<N>,"severity":"P1",
 "consequence":"Error correction and resubmit must create exactly one record.",
 "basis":{"kind":"task","reference":"<visible promise: one submission, one record>"},
 "follow_up":{"fixture":true,"changes":["edit_resubmit"],"insertions":[{"after_step":<k>,"steps":[
   {"action":"click","target":"<submit control>"},
   {"action":"snapshot","label":"error-shown"}]}]}}
]
```

## State-probe coverage

One row per committing task x viewport x input x probe; the denominator is the rows, never the tasks. Absent rows are `not checked`. Evidence is IDs and paths only (no field values): `run.json` `success_detail.criteria[]` (`id`, `step_index`, `snapshot_id`, `result`, `reason`), the `S-*` PNG, and for `follow_up` its `replay.run_id` and `state-oracle/<check-id>/run.json`.

| Task | Viewport (CSS px) | Input | Probe | Status | Result | Evidence | Reason or gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| <task> | <w x h, device ID> | <touch, mouse or keyboard> | a | done | pass or fail | <run, step, snapshot, check, replay run_path> | - |
| <task> | <w x h, device ID> | <input> | b | not applicable | - | <run, step, snapshot of the reached screens> | <what the task lacks> |
| <task> | <w x h, device ID> | <input> | c | not checked | - | - | <blocker> |

- `done`: the check was evaluated on the current build (`result` pass or fail, comparison done), with linked run, step and capture reviewed. A fail is still `done`.
- `not applicable`: the reached screens show the task has no such step (no confirmation, no switchable item/date/recipient, no validation). Cite their run, step and snapshot IDs; without them it is `not checked`.
- `not checked`: everything else, with the reason: no resettable fixture or authorization, no visible record list, ungrounded policy, toolbar Back, grounding failure, or any unevaluable result (`replay_failed`, `checkpoint_unvisited`, `capture_state_changed`, `expectation_basis_missing`).

Report `done k, not applicable m, not checked j of n rows`. Carry gaps into the verdict; `not checked` never counts as passed.

## Temporal candidates and intermediate keyboard replays

After actions, the existing page instrumentation records changed visible
status/alert/dialog regions and leaf text in `temporal_candidates` (up to 128;
output overflow is `temporal_candidates_dropped`; page sampling caps set
`temporal_sampling_truncated`). Each candidate keeps action/capture
anchors, appearance/disappearance times, a declared-window link or a proposed
`timing_window` object. These are **candidates**, not defects. Confirm the selector
against the UI, copy that object into `timing_windows`, and replay the recorded
steps with an explicit wait covering the observation window. Do not infer
"never disappears" from `open_at_observation_end`; its completed duration is null.
Polling can miss events shorter than 16 ms; this is not a screen-reader test.

A declared window may identify an untimed recovery location:

```json
"timing_windows": [{
  "id":"saved-notice", "selector":"#notice", "kind":"transient_text",
  "measure":"visible_duration",
  "recovery":{"selector":"#receipt","after_step":4}
}]
```

Omitting recovery `after_step` checks the final captured state. Only the same
visible text after an observed disappearance establishes `available`; an absent
match is `not_observed`, not proof that no alternative path exists. Text recovery
does not establish recovery of an action. `exception:{"kind":"extend","basis":"..."}`
records a claimed WCAG 2.2.1 exception/adjustment for review; supported kinds are
`turn_off`, `adjust`, `extend`, `real_time`, `essential`, `twenty_hours`.
CG-02 remains a reading-time model, not a WCAG verdict. WCAG 2.2.4 is **AAA**.

Declare intermediate states already reached by the task:

```json
"focus_walks": [{
  "id":"review", "after_step":3, "state":"modal", "selector":"#review",
  "return_selector":"#open-review", "fixture":true
}]
```

At most eight checks; states are `modal`, `validation_error`, `detail`,
`confirmation`. `fixture:true` authorizes prefix replay only on owned synthetic
data. Each uses a fresh browser context and the ordinary recorded actions, checks
the visible state selector, then performs Tab and Shift+Tab walks and Escape.
Results record focus indication, obscuring, cycles, return target and captures
under `probes/`. The analyzer keeps their own run IDs; `probe_replays` links the
source task and replay. A normal modal cycle is not a keyboard trap. Failure to
reproduce, capped walks and missing return expectations are gaps, not passes.
Neither these probes nor initial/final focus walks replace a whole keyboard task.

## Analysing a run recorded without a profile

Runs recorded with `--device` alone have `profile_id: "no-profile"`. Analyze the
original run under supplied profiles for its recorded device and orientation
with `--cross-profile`; no copies or profile edits are needed:

```sh
python3 scripts/ergo_qa.py profiles --count 4 --devices desktop-1920 --orientation landscape --out profiles.json
python3 scripts/ergo_qa.py analyze --runs runs/R-local --profiles profiles.json --scenario sc.json --cross-profile --out analysis.json
```

Without `--cross-profile`, the error names the required flag and profile input.
If no profile matches, the error identifies the recorded device and orientation.
Detector rules and thresholds are unchanged. Operator judgment notes remain in
the recorded evidence and are not assigned to any of these profiles.

Drives a real Chromium page with Playwright, emulating one catalogued device, and
writes the evidence that `ergoqa analyze` consumes: `ergo-snapshot.v1` files
(screenshot + measured element geometry/colour) and one `ergo-run.v1` per run.
The contract is [repository documentation: `docs/ergonomic-swarm-spec.md`](https://github.com/remorser58/Remorswarm_UX_QA_Skill/blob/main/docs/ergonomic-swarm-spec.md)
sections 3, 5 and 10. The driver measures; it never scores ergonomics and never
role-plays a user.

Requirements: Node.js 22 and `playwright@1.56.1` with its Chromium. Install once:

```sh
cd drivers/web
npm ci                      # pinned packages from package-lock.json
npx playwright install chromium
npx playwright install-deps chromium   # Linux only: system libraries, asks for sudo
node selftest.mjs           # a few minutes; expects 0 failed
```

If Ubuntu 26.04 x64 reports `does not support chromium on ubuntu26.04-x64`,
export `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64` before installation
and keep it exported for driver runs. This selects Playwright 1.56.1's Ubuntu
24.04 build, not native 26.04 support. Keep Node.js 22: the pinned installer can
hang after download on Node.js 24.16+ and 26; the platform override does not fix
that separate issue.

The package is resolved by normal module resolution (so `drivers/web/node_modules`
or a global install both work), then each `NODE_PATH` entry, then
`/opt/node22/lib/node_modules/playwright` (a pre-installed cloud container path).
The driver itself never installs anything.

## Hosts that sandbox commands (Codex)

A sandbox that blocks Chromium's helper processes but allows local files (Codex
on macOS) can launch it in one process, which is enough for captures and the
layout scan of a `file://` page:

```sh
REMORSEARCH_CHROMIUM_ARGS=--single-process python3 scripts/ergo_qa.py scan --url file:///path/to/page.html --out work/scan
```

`REMORSEARCH_CHROMIUM_ARGS` takes space-separated Chromium switches for a local
launch; anything that is not a `--switch` or `--switch=value` fails the run. Pages
on the network still need network permission from the host.

When a host's command sandbox cannot launch Chromium, start the browser server in
a terminal outside that sandbox, using the same pinned Playwright package:

```sh
cd skills/remorsearch-ux-qa/drivers/web  # from the repository root
npm ci
node browser_server.mjs --port 39123  # omit --port to choose an unused port
```

The server prints one `export REMORSEARCH_BROWSER_WS=ws://127.0.0.1:...` line.
Export that value in the environment inherited by the agent's commands. The
server runs until Ctrl-C or SIGTERM. Its endpoint has a random path and listens
only on 127.0.0.1. The clients accept only `ws://` URLs on `127.0.0.1`, `localhost`
or `[::1]`, without credentials or fragments. An invalid value fails the run;
it never falls back to launching locally.

Both the live driver and the page reader use `chromium.connect` with the
Playwright protocol to a `launchServer` endpoint. Playwright rejects incompatible
client/server versions at connection time; keep both packages at 1.56.1. This
changes only who launches Chromium. Each run creates a fresh context and closes
its own context before disconnecting. It does not close the shared server or use
another client's pages, cookies or storage.

Evidence collection, catalogued devices, network policy and every access-control
stop remain the same. The run records `browser_connected`, `browser_version` and
`playwright_client_version` next to the existing driver metadata; page captures
record the same fields. Run the complete self-test through the connection path:

```sh
REMORSEARCH_BROWSER_WS=ws://127.0.0.1:PORT/PATH node selftest.mjs
```

## Commands

```sh
# Catalog and scenario generator (no browser needed)
node drivers/web/ergo_drive.mjs devices
node drivers/web/ergo_drive.mjs init --url URL --device ID [--task TEXT] --out sc.json

# Scripted: execute scenario.steps
node drivers/web/ergo_drive.mjs run --scenario sc.json --profile p.json --out runs/ \
  [--run-id R-x] [--base http://127.0.0.1:8765] [--flash-sample-ms 1000]

# Interactive: an LLM persona agent looks at each screenshot and picks the next action
# (--agent-json is required: the operator record, see persona-agent-protocol.md)
node drivers/web/ergo_drive.mjs serve --scenario sc.json --profile p.json --agent-json agent.json --out runs/ --port 9477

# One interactive request (see drive_client.mjs --help)
node drivers/web/drive_client.mjs --port 9477 act '{"action":"tap","target":"#submit"}'
node drivers/web/drive_client.mjs --port 9477 inspect

# Self-test (local fixture server, a few minutes; --only focus2,reflow-copy runs groups)
node drivers/web/selftest.mjs [--keep] [--only GROUPS]
```

| Option | Meaning |
| --- | --- |
| `--profile P.json` | `ergo-profile.v1`; uses `profile_id`, `attributes.device_id`, `attributes.orientation` |
| `--device ID` | override the profile's device (or run without a profile: `profile_id` becomes `no-profile`) |
| `--device-json F` | a device object (`ergoqa.devices.Device.to_dict()`) instead of the built-in table |
| `--orientation O` | `portrait`/`landscape`; only phones, tablets and foldables rotate (width/height swap) |
| `--base URL` | replaces `{BASE}` in `surface.url` and `success.url_contains` |
| `--flash-sample-ms N` | sample the viewport for N ms after page load, after each input and during snapshot steps, and for the whole of each wait step |
| `--feedback-timeout-ms N` | max wait for the first feedback after an input (default 3000; per-step `feedback_timeout_ms`) |
| `--settle-ms N` | wait after the first feedback before the after-snapshot (default 300; per-step `settle_ms`) |
| `--allow-origin O` | extra origin the page may load (repeatable). Default: only the scenario's origin |
| `--continue-on-error` | scripted: continue after a failed step (default: stop, status `failed`) |
| `--no-auto-scroll` | never scroll a target into view; an off-screen target is `no_target` |
| `--no-visual-feedback` | only DOM mutations/navigation count as feedback |
| `--timeout-s`, `--idle-timeout-s` | scripted run limit / serve idle limit (default 900 s each; ends `blocked`) |
| `--locale`, `--timezone` | default `ko-KR`, `Asia/Seoul` |
| `--headed` | visible browser window (needs a display) |

Exit codes: **0** run completed and `success` is true; **3** run.json written but not
successful (success false or unknown, or a scripted step failed); **2** usage/input
error (nothing is run; an existing non-empty run directory is never overwritten);
**4** driver/browser failure, a `blocked` run or requested analysis failure (run.json is still written when the
run directory exists). `run` and `serve` print one JSON line per event on stdout
(`ready`, `finished`).

Add `--analyze` to `run` or `serve` with `--profile P.json` to screen that exact
recording once during finish:

```sh
node drivers/web/ergo_drive.mjs serve --scenario sc.json --profile p.json --agent-json agent.json --out runs/ --port 9477 --analyze --python python3
```

`--python` selects the interpreter; otherwise use `$ERGOQA_PYTHON` or `python3`.
At startup, `analyze-profiles.json` retains the complete selected profile and
`analyze-scenario.json` freezes sanitized identity, target roles and timing-window
metadata, including an explicitly authored boolean `has_action`. The allowlisted
source context stays immutable in memory; its sanitized copy and owned capture/
inspection JSON are refreshed at finish for later private input. Sensitive locators
become stable analysis bindings, with a warning that they cannot be replayed.
Run/scenario/profile/capture IDs stay intact. Timing text comes from the redacted run.
The context uses an inert local URL, empty steps and no success expectations;
the recorded run supplies the actual URL, steps and task-integrity evidence.
Private typed values, task-check expectations and arbitrary scenario extras are
omitted. Original source files are preserved, and later source edits do not alter
these analysis inputs.

After `run.json` is saved and the browser closes, the existing
`scripts/ergo_qa.py swarm` runs for at most 30 s within a shared 110 s finish budget;
the client retains its 120 s timeout. Browser work is capped at 75 s, and optional
probes stopped or skipped at the limit record warnings/gaps. Cancelled probes are
awaited before recording or analysis. The analyzer gets only the remaining budget;
an exhausted budget fails explicitly without starting it. An existing `swarm/` directory
is rejected. Only an exit 0 with valid `analyses.json`, `findings.json` and
`report.md` completes analysis. The `finished` event and `/finish` reply add
`analysis` with status, report paths, screening counts and any failure reason;
timeouts and other signals are identified separately. These counts are screening
data and require capture review. They do not establish a QA pass. Active
screenshot-only replies retain their channel limits. Analysis failure exits 4
while the measured product `status` and `success` remain in `run.json` and the
receipt. Commands without `--analyze` keep their existing behavior.

If `swarm` exits `3` for degraded coverage, all three reports can still be
present in `swarm/`. Check `analysis.status` rather than file presence: it is
`failed`, `analysis.exit_code` is `3`, and the driver exits `4`. The recorded
task's `status` and `success` are unchanged.

`drive_client.mjs` accepts `health`, `act`, `note`, `finish`, `inspect`, and
`observe` / `screenshot` / `snapshot` (three names for the existing snapshot
endpoint). `act` and `note` require a JSON object; `finish` accepts one optionally;
the read requests take no body. It connects only to `127.0.0.1` and prints JSON
for successes and errors. Its exits are 0 for a successful request, 2 for usage,
3 for a failed action or unsuccessful run, and 4 for a connection or HTTP error.
Finish returns the run's exit code.

Inspect returns `fields`, `invalid_fields`, `focus` and `reading_order`. Fields
include current values, checked/selected state, native validity, the raw
`aria_invalid` attribute, described-by IDs/text and error-message IDs/text.
`error_associated` means an invalid field has a non-empty `aria-describedby` or
`aria-errormessage` reference; inspect the text to distinguish an error from a
hint. Every field is included even when it has no invalid marker or association.
`reading_order` is document order of rendered interactive elements, including
off-screen controls; `in_viewport` distinguishes controls on the current screen.
It is not a Tab walk or a screen-reader transcript. Main-document fields and open
shadow roots are inspected; frame contents and closed shadow roots are omitted.

Password, card/payment, security-code, account, hidden/file and explicitly
`data-sensitive` / `data-private` field values are returned as `null` with
`redacted: true`. Sensitive select values and option text are omitted too. The
inspector also redacts long card-like numbers and known sensitive values echoed
in descriptions or labels before returning or saving evidence. Redaction applies
to inspection output; existing action records and screenshots retain their
existing behavior, so use test data when entering values.

## Reading public pages (`read_page.mjs`, rung R3)

`read_page.mjs` renders one public URL for the research mode's reader and writes one
`ux-page-read.v1` document (`schemas/ux-page-read.v1.schema.json`). It is not used
by the swarm runs.

```bash
capture_dir=$(mktemp -d "${TMPDIR:-/tmp}/remorsearch-capture.XXXXXXXX")
chmod 700 "$capture_dir"
trap 'rm -f "$capture_dir/page.json"; rmdir "$capture_dir"' EXIT
node drivers/web/read_page.mjs https://example.com/post/1 --out "$capture_dir/page.json" [--device desktop-1920]
python3 scripts/ux_research.py ingest "$capture_dir/page.json" --run RUN_DIR --url https://example.com/post/1 --context anonymous
rm -f "$capture_dir/page.json"
rmdir "$capture_dir"
trap - EXIT
```

Captures contain page text before `ux_research.py ingest` scrubs it. Every capture
file is written with mode 0600 in a private temporary folder, handed to `ingest`,
then deleted, including after a failed ingest. Captures never go into the project
folder. When using `--out`, use a path in that private temporary folder.

- A fresh anonymous context: no stored cookies, no sign-in. The browser keeps its
  own user agent; the device sets only the viewport. No stealth.
- Images, media and fonts are blocked.
- Text is taken from a detached body copy after the reader's chrome and author
  pass. Author labels become `[author]`, their dates/counts/ratings stay, and
  repeated comments/reviews get `---` boundaries. Long author-marked wrappers
  keep their bodies; nested labels and member/profile links are still scrubbed.
  The chrome/author/item/keep lists come from `markers.json` and fail closed when
  missing, empty or invalid. `driver_version` records `read_page/2; markers/VERSION`
  within the existing capture schema. JSON-LD and metadata still require ingest's
  privacy scrub, and capture files retain mode 0600.
- It only scrolls (8 screens by default, at most 50). It never clicks, types or
  presses keys, so "more comments" buttons and consent banners stay as they are.
- Any browser or human check stops immediately, including a "checking your
  browser" page that would clear by itself. Checks are inspected after navigation,
  after the load wait and after each scroll. No further scrolling or page text
  follows a stop; `waited_ms` is always 0. Human checks set
  `challenge.interactive`; both kinds record `challenge.markers`.
  `--max-wait-ms` is accepted for compatibility and never waits out a check.
  Missing, unreadable or corrupt marker data fails closed before navigation.
  A password field is reported
  (`login_form`); the reader's verdict decides whether the page is gated.
- Loopback, private and link-local addresses are refused unless `--allow-local`
  (for local fixtures).
- Pacing and budgets are the reader's job (`references/research/public-page-access.md`
  section 8). Run it only after an anonymous read of the same URL that did not stop.

Exit codes: 0 read (document written), 3 stopped at a browser or human check
(document written with empty text and JSON-LD), 2 usage or refused address,
4 unread (invalid markers, navigation failed or browser/connection failure).

## Devices

`devices.mjs` mirrors `ergoqa/devices.py` (ids, CSS viewport, DPR, input,
form factor); the self-test fails if they drift. Viewport and DPR always come from
the catalog; a named Playwright descriptor (`Galaxy S24`, `iPhone 15`,
`iPhone 15 Pro Max`, `Desktop Chrome`) only supplies its user agent, otherwise a
reduced Chrome UA is used. `hasTouch`/`isMobile` follow `Device.has_touch` /
`Device.is_mobile`. Screenshots are viewport-only PNGs in device pixels
(`viewport x dpr`, e.g. 1080x2340 for galaxy-s24).

## Actions and real input

Every action is dispatched as real browser input (CDP `Input.dispatchTouchEvent`,
Playwright touchscreen/mouse/keyboard), never as synthetic DOM events or `el.click()`.

| action | fields | touch devices | mouse devices |
| --- | --- | --- | --- |
| `tap`, `click` | `target`, `offset?` | touchStart/End | click |
| `double_tap` | `target` | two taps 120 ms apart | dblclick |
| `long_press` | `target`, `ms?` (800) | touch held `ms` | button held `ms` |
| `swipe` | `target?` (start, default centre), `to` or `dx/dy` or `direction`+`distance`, `duration_ms?` (200) | finger path (fling allowed) | drag path |
| `drag` | `target`, `to`/`dx/dy`/`direction`, `hold_ms?` (250), `duration_ms?` (600) | hold, move, hold 100 ms | same with mouse |
| `scroll` | `dx/dy` or `direction`+`distance` (content direction), `target?` | slow finger strokes, slop-compensated, corrected | mouse wheel |
| `type` | `text`, `target?` (tapped/clicked first), `clear?`, `delay_ms?` | keyboard | keyboard |
| `press` | `key`, `hold_ms?`, `repeat?` | keyboard | keyboard |
| `gamepad` | `key` or `keys` (the keyboard mapping), `button?` (label), `hold_ms?` | keyboard | keyboard |
| `wait` | `ms` | | |
| `snapshot` | | | |

Common optional fields: `settle_ms`, `feedback_timeout_ms`, `timeout_ms` (target
wait, default 5000), `auto_scroll`, and metadata (`note`, `label`, `comment`,
`description`, `id`, `intent`, `expected`). A remote (TV) device has no pointer:
pointer actions fall back to mouse events and a warning is recorded
(`input: "mouse(fallback)"`). The Switch-style handheld has a touchscreen and uses touch.

Targets: a Playwright selector (`#pay`, `text=결제하기`, `role=button[name="..."]`),
`hotspot:<id>` (from `scenario.hotspots` or the page's
`window.__ergoqa__.hotspots()`, which wins because it is live), or `{x, y}` viewport
CSS px. The pointer point is the element centre unless `offset` (from the
element's top-left) is given. The step records `point`, `target_element_id` (id in
the `before` snapshot), `hit_element_id` and `target_hit` (is the target the
top-most element at the point, i.e. not covered by an overlay).

If a target appears only after the last snapshot, or its point is outside the
viewport, the driver (unless `--no-auto-scroll`) scrolls it into view
programmatically and takes a **pre-action snapshot** (note
`pre_action_auto_scroll` / `pre_action_target_appeared`) that becomes the step's
`before`, so geometry always matches what was on screen when the input happened.
Snapshot ids are `S-<run_id>-<nnn>` in capture order; `step_index` is the step
they belong to (0 = initial load), so a step can own two snapshots.

## What is measured

- **Elements** (per snapshot, max 400: scenario-role and `data-ergo-role` elements
  first, then interactive, then `role=alert|status`, then visible text blocks):
  box (viewport CSS px), visible/in_viewport/enabled, accessible name
  (aria-labelledby, aria-label, alt, label, text, title), ARIA role (explicit or
  implicit, `generic` when none), tag, unique selector (`#id` preferred),
  font size/weight, `color_fg`, `color_bg`, `container_bg` (behind the element),
  `border_color` for controls, cumulative `opacity`, `roles[]` (scenario targets +
  `data-ergo-role`; unknown role names are dropped with a warning, never guessed),
  `source: "dom"`. Hotspots become `source: "manual"`, `role: "hotspot"`,
  `selector: "hotspot:<id>"`.
- **Repeated warnings**: geometry/readability findings share a screen, rule and
  `selector_family` (scoped class/structural path, preserving container and shadow
  host boundaries) plus semantic role. They report `element_count` and up to three
  selector `examples`; linked observations retain every element's measurement.
  A screen is the surface, title, device, visible headings and route with digit
  runs masked: scroll position, toasts, changed control lists and record IDs do
  not create a new screen; reach warnings group the same way. Missing family
  evidence keeps exact selectors separate; numbered IDs alone never establish a
  component family.
  Task, timing and multi-element relations are not collapsed by this grouping.
- **Colours**: the layers under the element's centre (`elementsFromPoint`, or the
  ancestor chain when off-screen) are composited over the page canvas with group
  opacity; `color_bg` is `null` when an image, video, canvas, SVG or
  background-image/gradient is underneath (unknown, not guessed).
- **Feedback latency**: an init-script `MutationObserver` timestamps DOM changes
  (only real ones: an attribute or text node written with the value it already had
  changes nothing on screen, and attributes of `<html>`/`<body>` are page-state
  markers such as input modality; a script that changes a field's `value` counts),
  and `input` events of text-like fields count too (a typed character shows in the
  field without any DOM mutation; checkbox, radio, range, color, file and select
  inputs are left out, since their own look is what the user sees, and are judged by
  mutations and pixels); both are reported as `dom_mutation`.
  `feedback_latency_ms` = first of these or a main-frame navigation after input
  dispatch, `null` if none within 3000 ms (`feedback_window_ms` says how long was
  observed). Only when neither occurs does a visual change of the viewport count
  (`feedback_source: "visual_change"`, ~30 ms resolution; covers canvas and
  CSS-only feedback; the focused field's box is masked, so a blinking caret is not
  feedback, and so are pixels that changed in either adjacent pair of three frames
  before the input. The extra earlier frame catches a pulsing color that reverses
  between the last two samples and happens to look identical in both;
  `feedback_visual_moving_px` counts them). `feedback_ambient_mutations` / `feedback_visual_ambient` flag
  pages that were already changing before the input (latency then is ambiguous).
- **Native state acknowledgment** (`feedback_native_state`, tap/click/double-tap/
  long-press steps): when the action activates a native checkbox/radio — the input
  itself, or the control of an associated `<label>` (explicit `for` or nested, the
  same `label.control` rule `controlOf` applies) — the driver snapshots the boolean
  `checked` state before the input and timestamps the control's own trusted
  `input`/`change` events, recording the boolean observed at event time and checking
  that it survives the event handlers before retaining that timestamp. The event
  time is converted through the calibrated page clock (`driver.clock.page_offset_ms`,
  the same single offset the DOM path uses), and the recorded `latency_ms` is the
  first trusted event whose state-at-event both differs from the armed state and
  matches the observed end state — an event whose state the page immediately
  restored never lends its timestamp to a later programmatic change (that change
  records `changed: true, event: null`), and an end state that does not settle
  records `stable: false`. When the boolean truly changes, the step records
  `{source: "native_state_change", via: direct|nested_label|label_for, type,
  dom_id, before, after, changed, event, latency_ms[, stable]}`. This exists
  because a 13×13 checkbox that toggles can paint fewer pixels than the
  downsampled visual comparison resolves, leaving `feedback_source` null although
  the control answered. It is a state/semantic acknowledgment of the activation
  only: it is not calibrated visible paint, perceptibility or a screen-reader
  announcement (those stay with the DOM/visual evidence), CG-03 classifies the
  acknowledgment with the same response-time bands as any other acknowledgment
  (≤400 ms suppresses the missing-response finding; >400 ms P3, >1000 ms P2,
  >10000 ms P1), a repeated click that changes nothing records `changed: false`
  and never acknowledges, and custom ARIA widgets (no native input) stay
  DOM/semantic evidence. A control the protected-target rule covers or that lies
  in an opted-out (`redact`) region is never armed: no id, no boolean, nothing
  recorded. `snapshot.validate_run` rejects malformed `feedback_native_state`
  (wrong shapes, unknown keys, non-boolean states, `changed` contradicting the
  states, non-finite/negative latencies, event/latency disagreement, latencies
  outside the step's observed feedback window/action interval) instead of letting it pass CG-03.
  Reads only tag/type/id and the boolean — never text or field values.
- **Timing windows**: each selector is polled in the page every 16 ms; a window
  reports `visible_ms` (shortest completed visible interval, the tightest window a
  user got; null if none completed), `intervals_ms`, `min/max_visible_ms`,
  `appearances`, `open_interval_ms` (still visible at the end, a lower bound, not
  counted), and the text seen. "Visible" = rendered with a non-zero box;
  off-viewport appearances are recorded separately. Non-CSS selectors fall back
  to Playwright polling (`method`). Observation ends before focus/reflow probes.
- **Screen coordinates**: boxes, points, hit tests and captures all use the screen
  (the visual viewport). CDP screenshot clips are in document coordinates, so frames
  are clipped at the visual viewport's page position (a clip at 0,0 captured the top
  of a scrolled document before this was fixed). When content is wider than a phone
  screen, the layout viewport widens and the screen pans inside it; boxes are then
  shifted to screen coordinates, hit tests shift points back, and frames are taken
  without a clip (a clip snaps the pan back and would move the page under the next
  tap) and downscaled in `png.mjs`. Snapshots record `surface.visual` (offsets, size,
  scale) so a reader can tell when boxes were shifted.
- **Flash sampling** (`--flash-sample-ms`): CDP screenshots of the screen
  downscaled to ~160 CSS px wide, as fast as possible (~30 fps here), decoded by
  the built-in PNG decoder (`png.mjs`). Each sample has `t_ms`, `mean_luminance`
  (WCAG relative luminance, 0..1), `frame_index`, `step_index`,
  `changed_fraction` (share of pixels whose luminance changed by >= 0.10 vs the
  previous frame of the burst), `flash_fraction` (same, with the darker state <
  0.80: the WCAG 2.3.1 pair condition) and `red_fraction` (saturated red).
  Each sample also carries a block grid for local and counter-phase flashes:
  `block_lum` and `block_red` (base64, one byte per block: mean relative
  luminance and share of saturated-red pixels, linear R/(R+G+B) >= 0.8 and
  (R-G-B) x 320 > 20), and `block_moved` + `motion_css` when the content moved
  (scrolling is motion, not flashing: the page's own measured scroll between two
  frames, `page_scroll_css`, is used as the motion; scroll that reverses direction
  more than 3 times within 1 s is marked `page_scroll_oscillating` and is not
  treated as motion, since only smooth motion in one direction is exempt). Blocks are at least 22 x 40 CSS px and at
  most 820 per frame; the layout is in `run.flash_sampling.block_grid`. A random
  0-15 ms pause between captures breaks phase lock with fast flicker, and
  `flash_sampling` records `sampled_ms`, `mean_fps`, `max_gap_ms`, `bursts` and
  `truncated` (sampling stops at about 6 MB of samples so `run.json` stays below
  ergoqa's input limit).
- **Keyboard focus walk** (mouse and keyboard devices by default; `--focus-walk`
  / `--no-focus-walk`): after the task, when the run ended normally, the driver
  Tabs through up to 40 stops of the end state and then of the initial screen (in a
  separate browser context with the same network policy), each walk within 8 s. It
  resets the sequential focus starting point to the top, turns smooth scrolling off
  and waits for scrolling to settle, and follows focus into open shadow roots and
  same-origin iframes. Per stop, `run.focus_walks[].stops[]` records the focused
  element (`selector`, `dom_id`, `role`, `name` — never a field's value — `box`,
  `frame`), `indicator_px` (pixels that change by >= 24/255 in the element box, its
  small wrappers and 4 px around them, between the focused state and the same
  element blurred at the same scroll position) and `obscured_fraction` /
  `obscured_by` (share of nine sample points covered by a painting fixed or sticky
  layer that does not contain the element). A bounded, read-only Chromium probe
  can also detect a solid opaque fixed/sticky HTML layer with
  `pointer-events: none`: it checks the top node at the same sample points
  independently of pointer input. Full coverage also requires a single opaque
  rectangle enclosing the focused element and the same top layer at its corners.
  One positive-area rectangle must enclose the target by itself; the bounding
  union of wrapped inline fragments and the interior samples do not prove it.
  Ordinary root scrolling is accounted for on both axes. If scroll or focus
  geometry changes during the probe, the supplemental signal is discarded. On a recorded
  focus change the supplement, when available, appears as `focus.paint_cover`.
  It does not alter click targeting or general element occlusion data. Recognized
  user-opened layers, complex clipping or masking (including Chromium's
  mask-box-image), frames and unsupported protocol results keep the existing
  evidence. The probe times out after 350 ms. A missed painted cover is still
  possible and the screenshot remains the visual record.
  `ended` says why a walk stopped
  (`cycle`, `left_document`, `max_stops`, `time_budget`, `opaque_frame`).
- **Focus probe before clicks** (same devices and switch as the walk): the walks see
  only the initial and end screens, so before a `tap`/`click` on a focusable
  control the driver captures the control, its small wrappers and the viewport
  twice unfocused (animations running), presses F24 through CDP (keyboard
  modality: `:focus-visible` applies, and so do modality scripts such as what-input
  or Angular CDK, which ignore Shift; scripts that react only to Tab are not
  triggered), focuses the control
  without scrolling, captures again, gives focus back to the element that had it
  where losing it would change the page (an expanded trigger, focus inside a dialog,
  menu, listbox or popover) and otherwise blurs the control (`restored`), and
  captures a third unfocused frame. A pixel counts only when the focused capture
  differs from all three unfocused ones (a clock that ticked between captures is not
  an indicator), and the previously focused control's own ring is masked (not when
  it holds the target; a large element along its edges only). When more than half of
  the target's box is masked, the probe is `inconclusive` (`indicator_px: null`).
  Before a button, a focused text field is blurred first and the screen settles and
  is measured again (`after_field`), since its blur would run at the click anyway;
  after typing in a field with suggestions, or before anything but a button, the
  click is not probed (`field_focused`: a list that hides on blur would be gone).
  `step.focus_probe` records the control like a walk stop plus `focus_visible`,
  `indicator_px`, `indicator_any_px`, `moved` (a focus handler scrolled; the page is
  scrolled back and the captures are not used), `masked_prev` and `snapshot_id` (the
  screen). If the control moved or
  something covers it after the probe, the target is resolved again and
  `disturbed: true` is set. Skipped, with `skipped`, for text-entry targets (the
  caret shows focus), controls inside menus, menubars, listboxes, trees and grids
  (`managed_focus`: they move focus themselves), game and timed targets, and when
  the control already has focus. At most 16 per run.
- **Click targets**: each tap or click records `step.target_control` for what it
  landed on (through open shadow roots): `tag`, `role`, `dom_id`, `control` (a
  control, or inside one within five levels; links and buttons at any depth),
  `contains_control`, `card_control` (the image or text of a card whose own link, or
  its one control, the keyboard reaches), `hidden` (inside `aria-hidden`/`inert`),
  `ancestor_ids` and `text`. SM-08 reads it.
- **Focus and layers**: each snapshot records `focus` (the deepest focused element's
  `tag`, `role`, `dom_id`, `on_body`, `expanded`, `controls`; never a value) and
  `layers[]` (declared dialogs and fixed or absolute painted boxes over ≥ 40 % of the
  viewport that cover rendered content): `selector`, `dom_id`, `kind`
  (`modal`/`dialog`/`sheet`), `box`, `contains_focus` (focus inside it, or on its
  `overlay_root` when that root wraps the layer: the outermost fixed ancestor that is
  not the app shell),
  `follows_focus` (the next Tab reaches it). After a tap, click or key press, layers
  that opened without focus are polled until 1 s after the input (0.7 s more after a
  wait or snapshot step), at least once; those that focus reached are listed in
  `step.focus_late_layers`. FM-02 reads these.
- **Reflow copies** (`--no-reflow` to skip; not on games, TVs and handheld
  consoles): at each snapshot the driver serialises the DOM as the browser holds it
  (CSSOM-inserted rules, adopted sheets, open shadow roots as declarative ones;
  scripts, `noscript` and meta refresh dropped) and keeps the newest copy per screen
  fingerprint (path, fragment, headings, dialogs, `main`/`form`/`section` with an id,
  large regions with an id and messages on screen, digits removed), for up to 12 screens (`reflow_screens_dropped` counts the
  rest). After the run each copy is loaded under its own URL (fulfilled from memory,
  scripts off) at the device width and at 320 CSS px. `run.reflow[]` has
  `snapshot_id`, `url`, `width`, `client_width`, `scroll_width`, `root_clips`,
  and `viewport_overflow_x` (effective horizontal viewport policy: `auto`,
  `scroll`, `hidden`, or `unknown`). The DOM's `scroll_width` can exceed the
  viewport even when the root stops direct user scrolling. The HTML body's
  overflow affects the viewport only when CSS overflow propagation applies;
  a boxless body (`display: contents`) does not supply it. A body-local
  horizontal clip can still cut away text, native controls, and labeled
  images that were visible at the device width, even without page overflow.
  For absolute children, the browser's layout anchor and its computed style
  must support body-local clipping; the body fallback alone is not evidence.
  Uncertain clip edges are not used for this test.
  Older ambiguous records ask for a new capture instead of inferring possible
  scrolling from geometric width alone. The record also contains
  `offenders[]` (outermost elements past the right edge, `fixed` when a fixed box
  holds them), `exempt_right` (how far exempt content reaches), `lost[]` (content ≥ 90 %
  visible at the device width, < 50 % at 320 px),
  `lost_height`, `scan_capped` (more than 20,000 elements), or `styles_lost` (the
  copy kept < 90 % of the live CSS rules; not measured) or `error`.
- **텍스트 간격과 짧은 창**: 같은 화면 복제를 재사용해 `run.adaptation[]`에
  `text_spacing`과 `short_height` 조건을 추가합니다. 간격 검사는 폭·높이·DPR을
  유지한 채 해당 HTML 텍스트의 줄 높이 1.5em, 문단 뒤 간격 2em, 자간 .12em,
  어간 .16em을 동시에 적용하고, 기존 값이 더 크면 보존합니다. 실제 적용된
  값은 `overrides[]`의 최대 20개 샘플과 `lost[].after.style`에 기록합니다.
  짧은 창은 폭과 DPR을 유지하고 높이를 `max(256, floor(원래 높이 / 2))`로
  바꾸는 실험입니다. 원래 높이가 256 CSS px 이하이면 `inapplicable`로 남깁니다.
  이 높이와 화면 비율에는 WCAG 통과·실패 기준을 부여하지 않습니다.
  [WCAG 1.4.12 해설](https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html)은
  간격을 바꾼 뒤에도 내용과 기능을 유지하도록 요구합니다.
  텍스트 `Range`와 조작 대상의 실제 범위를 비교해 새 잘림만 RF-02/RF-03으로
  기록합니다(P2). 원래 내용에 접근할 수 있고 변경 뒤 범위의 일부가 잘린 경우를
  비교하며, 계산 오차 허용량은 0.25 CSS px²입니다. 스크롤 길이를 반환하는
  정수 CSS API에는 실제 스크롤 범위가 있는 축에만 끝 경계 1 CSS px의 반올림
  오차를 허용합니다. 숨김 상자 자체의 경계는 유지합니다. 문서·컨테이너의 스크롤로
  도달하는 내용은 손실로 세지 않습니다. 기본 줄 간격은 판정 대상이 아닙니다.
  `source_snapshot_id`는 원본 화면, `baseline_snapshot_id`는 원래 크기의 복제,
  `snapshot_id`는 변경 조건의 복제를 가리킵니다. 보조 캡처는 `device.probe:
  adaptation`과 조건을 기록하며 기존 PNG 해시·QA 영수증 경로를 사용합니다.
  원본 과업의 화면 이력과 일반 인체공학 분석에서는 보조 캡처를 제외합니다.
  `applied`, `evaluable`, `scan_capped`, `styles`, `gaps`, `lost[].before/after`로
  실제 적용 여부와 비교 범위를 확인할 수 있습니다.
  읽을 수 없는 CSS, 스캔·시간 상한, 적용값 확인 실패는 측정 불가로 남깁니다.
  `normal` 줄 높이처럼 실제 값을 확정할 수 없는 텍스트, 입력 UI·아이콘·이미지
  문자, 일부 문자 체계, 세로쓰기와 상세·슬라이드 접근 경로는 `gaps`에 남습니다.
  한국어 어간처럼 존재하는 속성을 적용하며, 공백이 없는 텍스트의 어간과
  일본어·중국어의 문단 뒤 간격은 적용 범위를 줄입니다.
  스크립트로 바뀌는 배치, 실제 브라우저 확대·키보드 초점 이동, 가림을 모두
  재현하지 않습니다. 이 결과는 기록된 정적 복제의 잘림 관찰입니다.
  `unsupported_text` identifies excluded native text controls or private-use
  glyphs; `unsupported_text_metrics` includes computed `line-height: normal`,
  whose used value is not a numeric CSS metric. These gaps can make analysis
  health `degraded`; they are neither product failures nor passing spacing
  checks. Do not substitute a guessed line height or suppress the gaps.
  Record OS/browser, locale and installed/resolved fonts for comparisons.
  Korean fallback fonts can differ across hosts (for example, Noto Sans CJK KR
  versus WenQuanYi Zen Hei), changing glyph widths, wrapping and clipping.
  Match the font environment before attributing different results to code;
  a configured CSS font-family alone does not prove which font rendered Hangul.
- **Console**: `console.error` and uncaught page errors, per snapshot (since the
  previous one) and in `run.json`. Errors caused by the driver's own network block
  are counted separately, not reported as page errors.
- **Success**: `scenario.success` keys `selector_visible`, `url_contains`,
  `text_present` (string or list; all must hold) are measured at the end
  (`success_basis: "measured"`). Unknown keys make success unknown (`null`). In
  serve mode the persona's `/finish {"success": ...}` is kept as
  `persona_claimed_success` and used only when the scenario declares no criteria
  (`success_basis: "judgment"`).
- Times (`t_start_ms`, `t_end_ms`, `t_ms`) are ms since the initial navigation
  started; page timestamps are converted with a measured clock offset.

## Serve API (interactive persona sessions)

`serve` prints `{"event":"ready","url":"http://127.0.0.1:PORT",...,"snapshot":...,"png":...}`
after the initial snapshot. `--port 0` picks a free port.

| Endpoint | Body | Reply |
| --- | --- | --- |
| `GET /health` | | `{ok, run_id, steps, last_snapshot_id, finished}` |
| `GET /snapshot` | | new snapshot without acting: `{snapshot, png, snapshot_id, step_index, url, title, result}` |
| `GET /inspect` | | redacted form state: `{inspection, fields, invalid_fields, focus, reading_order, step_index, last_snapshot_id, observed_at}`; requires an accessibility channel |
| `POST /act` | one action object (table above) | same plus `result` (`ok`/`no_target`/`error`), `error`, `point`, `target_element_id`, `target_hit`, `feedback_latency_ms`, `feedback_source`, `before`, `auto_scrolled` |
| `POST /note` | required `confusion: bool`; optional `intent`, `expected`, `observed`, `step_index`, `failure_class`, `evidence`, `anchor`, `severity`, `corroborated` | `{ok, note_index, step_index}`; stored as `persona_notes` with `basis: "judgment"` |
| `POST /finish` | `{success?: bool}` | writes run.json, replies `{run, status, success, success_basis, exit_code, analysis?}`, then exits |

Requests run one at a time in arrival order. A `no_target` action does not end the
session; the persona can try something else. `status` is `completed` after
`/finish`, `blocked` after an idle timeout, signal or browser crash.

Unknown fields return HTTP 400 listing allowed keys. `/note.scope` and
`/finish.task_success_claimed` are not accepted. Send observations to `/note`,
then `/finish {"success":true|false}` or `{}` for unknown; measured scenario
criteria take precedence. Copy the exact field types and bounds from
`references/ergonomics/persona-agent-protocol.md` into the operator prompt.

## Security and scope

- The HTTP server binds **127.0.0.1 only**, checks `Host` (DNS rebinding) and
  rejects any foreign `Origin`/`Sec-Fetch-Site` (cross-site POSTs from a browser);
  POST bodies must be `application/json`, at most 64 KiB, JSON objects.
- Unknown actions and unknown action keys are rejected (400). **No endpoint
  evaluates JavaScript**, navigates to a request-supplied URL, or reads/writes a
  request-supplied path. Selectors go to Playwright's selector engines as data.
  There is no token: any local process can reach the port while a session runs,
  so use it on a single-user machine.
- Network policy: the page may load only from the scenario URL's origin (plus
  `data:`/`blob:` and any `--allow-origin`); everything else is aborted and listed
  in `run.json.driver.network_policy`. Service workers are blocked.
- The driver only performs the declared actions on the declared surface. Keep it on
  local fixtures or staging builds; do not point it at production accounts,
  payments or real user data. Screenshots and typed text are written to the run
  directory unredacted.
- Files are written atomically (temp file, fsync, rename); run directories are
  never overwritten.
- The page runs in the main world next to a small driver state object
  (`Symbol.for('ergoqa.driver.v1')`) and, when timing windows exist, a binding named
  `__ergoqaDriverTimingWindow`. A hostile page could read or spoof these; the page
  under test is trusted to that extent.

## Not exercised here (honest limits)

- **Only Chromium device emulation.** No real Android/iOS device, no Safari/WebKit
  or Firefox engine, no native apps, no desktop OS widgets. Android
  (uiautomator) and vision/annotation snapshots are separate drivers (spec
  section 11), not part of this one. An iPhone profile is Chromium with an iPhone
  user agent and viewport, not WebKit.
- No browser UI: the viewport is the full catalog screen (no address bar, system
  bars, notch/safe areas) and no on-screen keyboard (typing does not shrink the
  viewport). No pinch zoom, multi-touch, stylus, hover on touch, haptics or sound.
- Emulated touch in Chromium: a long press does not open a native context menu and
  a click still follows the release; touch slop and fling differ from devices.
- Elements inside iframes and closed shadow roots are not extracted (open shadow
  roots are, with selectors relative to their root). Text colour is the element's
  computed colour (mixed-colour children are separate elements only when they have
  their own direct text). Placeholder colour, text shadows, filters and blend modes
  are ignored; `color_bg` under non-ancestor translucent layers is approximate.
- Feedback latency counts any DOM mutation (including unrelated timers; see the
  ambient flags); CSS-only or canvas feedback is detected only visually at ~30 ms
  resolution; the `:active` state of a touch tap is usually too brief to capture.
- Flash sampling is ~25 fps with capture jitter, on a downscaled frame, and only
  during the sampled windows (after inputs, snapshot steps, whole waits); flicker
  faster than ~12 Hz is seen as flashing at an aliased rate, not its true rate.
  It is an input to the WCAG 2.3.1 check, not a certification.
- `window.__ergoqa__.hotspots()` and scenario hotspots are trusted as declared;
  scenario hotspot boxes are fixed viewport coordinates (only page-provided
  hotspots follow scrolling).
- Tested on Linux with Node 22.22 and Playwright 1.56.1 / Chromium 141 (headless).
  `--headed`, macOS and Windows have not been executed here.
