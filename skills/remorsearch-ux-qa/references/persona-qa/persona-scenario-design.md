# Persona Scenario Design

## Purpose

Use personas to widen QA coverage and create realistic test conditions. When research mode has produced an audience file, build personas from its segments first. Otherwise use a small stratified sample of synthetic personas; do not attempt to treat a multi-million-profile dataset as a list of users to impersonate.

## Persona use policy

- A persona is a scenario generator, not a research participant. This holds for personas composed from audience research too.
- When an audience file exists (`ergo-audience.v1`, from `references/research/audience-pipeline.md`), each scenario row is a segment's typical member or a one-facet variant, times a key task. It cites `segment_id`, `task_id`, `facet` and gate-supported claim IDs.
- Synthetic dataset records may add only attributes that do not change the task.
- Composed personas stay `basis: synthetic` and carry `audience_ref` `{audience_id, segment_id, facet, claim_ids}`. They never support claims about real users.
- Raw community text never enters persona or scenario prompts. Only authored, scrubbed segment summaries and task data do.
- Resolve the exact dataset source and revision before reading it; do not assume that a field or value exists because another version had it.
- Inspect the schema first and prefer streaming, bounded sampling, or a local sample over full-dataset download.
- A persona attribute is relevant only when it changes a task, constraint, expectation, or failure risk.
- Do not infer personality, ability, income, or preference from age, region, job, or household alone.
- Keep the original dataset field names and values when they matter to reproducibility.
- Record the dataset name, version or access date, sample rule, and selected fields.
- If neither an audience file nor the dataset is available, use a manually defined scenario and mark population simulation as blocked.

## Dataset access record

Keep this record whenever a synthetic dataset is read, including when it only adds attributes to audience-composed personas.

```text
Dataset:
Source and revision:
Access date:
Schema inspected:
Sampling mode: streaming / bounded / local sample / manual
Sampling rule:
Fields used:
Fields omitted:
Reason for omission:
```

## Sampling strategy

Take strata from the audience file first: its segments, their conditions, contexts, devices and key tasks. Use the table below for dimensions the audience file does not cover, or when there is no audience file.

| Dimension | Example strata | QA value |
| --- | --- | --- |
| Product familiarity | first use, returning, expert | discoverability and efficiency |
| Device | small mobile, large mobile, desktop | reachability and responsive hierarchy |
| Input | touch, keyboard, assistive technology | interaction and accessibility |
| Context | hurried, interrupted, low connectivity | feedback and recovery |
| Goal | browse, compare, complete, recover | information hierarchy |
| Risk | low, financial, safety, privacy | trust and confirmation |
| Data state | normal, empty, partial, stale | state handling |

Use a supplied completed audience, brief-derived conditions, or an optional bounded dataset to select contexts. Missing audience or dataset never blocks QA. Create the actual task, with concrete data, from the product surface and the audience file's key tasks.

## Scenario format

For scenarios about discoverability, optional decisions, or recovery, look up
`references/persona-qa/behavior-guidance.md`: record the user goal, cue,
expected state change, and reject/return path in the existing scenario.
When that scenario depends on finding or safely disclosing information, look up
`references/persona-qa/information-architecture.md` for classification, case
evidence, and checks for first choice, disclosure, and privacy.
For method selection or a finding that needs stronger evidence, look up
`references/persona-qa/ux-qa-methods.md` and record the method and its limits.
For Korean search, forms, or composers, use the input-provenance checks in
`references/persona-qa/keyboard-recovery.md` when composition can affect the task.

```text
Scenario ID:
Audience ref (audience_id, segment_id, facet), or "none" with the reason:
Persona source:
Sample rule:
Relevant attributes:
User segment:
Task ID and concrete data:
Task goal:
Context:
Device and input:
Starting state:
Constraints:
Expected success:
Likely failure:
Claim IDs:
Evidence that motivated the scenario:
Untested steps and why (optional):
```

## Example

The IDs below are illustrative.

```text
Scenario ID: S-03
Audience ref: AU-shop-202609, SEG-evening-reorder, facet: one hand free (CTX-commute)
Persona source: composed from the audience file, basis synthetic; no dataset attributes added
Sample rule: the segment's typical member, varied in one facet (context)
Relevant attributes: evening routine, repeat purchase, one hand free
User segment: SEG-evening-reorder ("퇴근길에 생필품을 다시 주문하는 직장인")
Task ID and concrete data: T-reorder: reorder "생수 2L x 12" from the last order, delivery by Friday
Task goal: reorder a previously purchased item
Context: user is interrupted and has one hand available
Device and input: small mobile, touch
Starting state: signed in with a test account, previous order exists
Constraints: low patience, must confirm delivery date
Expected success: reorder without searching from the beginning
Likely failure: previous order is hard to find or delivery date is hidden
Claim IDs: CLM-7c2e9a41 (pain_point, supported_medium), CLM-0d5f3b18 (context_of_use, supported_high)
Evidence that motivated the scenario: two people in one community report that past orders are hard to find (CLM-7c2e9a41)
```

The example is a test condition. It is not evidence that every member of the segment behaves this way, and the segment's share says nothing about how many users would meet this failure.

## Draft vs. Save

If an existing layered confirmation applies to a draft and the underlying editor has a separate Save, add this recovery subcase. From the same safe starting state, exercise pointer and keyboard activation separately. The confirmation changes only the intended draft once, with no editor save or dismissal. Separately activate the editor's Save and check that the intended values persist once. Record actual focus, draft state, and persisted state independently. If the original opener was replaced by another item's control, return to a surviving, meaningful point in the still-open editor, not to the replacement by position or label. For [React portals](https://react.dev/reference/react-dom/createPortal#caveats), callback ancestry can differ from DOM ancestry; neither a parent callback nor a correct-looking screenshot establishes the save outcome. Use only existing authorized controls and mark unexercised branches untested.

For a disposable record, note its saved value before either run. In the no-save run, confirm a different value in the child, then close the editor without saving; reopen the same record and check for the original value. In the save run, start from the same baseline, confirm the change in the child, then choose Save in the editor; reopen the record and check for the changed value. If the product exposes no independent saved-state readback or save count, mark that fact unverified rather than inferring it from a toast or the open draft.

## Password visibility is not submission

Use an existing, authorized synthetic form with an inert local submit target and
an invented value. Never use a real account, credential or autofill data. Start
with valid synthetic input masked; from that same state, test the existing Show
then Hide control with pointer and keyboard in separate runs. For the keyboard
run, activate the focused toggle rather than pressing Enter in the input. Check
masking and any exposed action label or state; the value and intended field/form
association stay intact.
Record where focus actually lands and whether editing can resume at the expected
caret or selection, when observable. Focus on the toggle during keyboard use is
not itself input loss. Retain state observations, not the exposed value or an
unmasked screenshot.

Require zero submit attempts and no navigation from either toggle action, using
the fixture's existing submit and navigation observations rather than the
appearance of the form. In a separate run from the same valid baseline, activate
the explicit synthetic Submit once: require one observed attempt through the
same observer as a positive control, without sending to a real service. An
unobservable count or navigation result, or a positive control that does not
register once, cannot support a pass for the no-submit check. Mark unobservable
field identity, focus or caret/selection separately as `not_run`; do not infer
them from a screenshot.

Record the browser and OS. Exercise a browser-native reveal control separately
from the app control if normally available on that surface. Browser-managed
availability may depend on entry and focus; absence, interference you cannot
isolate, or an unavailable observation is `not_run`, not a pass for the native
path. Do not enable a control or change browser settings to complete the check.
See the [HTML button submission rules](https://html.spec.whatwg.org/multipage/form-elements.html#the-button-element),
the [GOV.UK password input example](https://design-system.service.gov.uk/components/password-input/),
and [Edge's native reveal conditions](https://learn.microsoft.com/en-us/microsoft-edge/web-platform/password-reveal).

## Korean products

Use this section for Korean product QA conditions. Report language alone changes headings and wording. Community research runs only when requested. It adds test conditions. None of it is evidence about real users. A cue from the Korean context becomes part of a claim only when a gate-supported claim, or a statistic with a source card (`references/research/korea/statistics.md`), backs it. Until then it is an assumption and is labelled as one. Read `references/persona-qa/kwcag-card.md` for safeguards; lookup `references/persona-qa/kwcag-2.2.md` by item. Only requested Korean research uses the channel router `references/research/korea/overview.md`; lookup channels by ID.

- **Identity and payment gates.** 본인인증, 간편인증, SMS 인증번호, CAPTCHA, 보안 키패드 and payment-module popups are stops on production. The agent does not pass them. Run the scenario on staging with mock verification, test numbers or a test payment mode, or mark the step untested (미검사) and say why. Use the team's test identities only. Never enter a real 주민등록번호, phone number, card or account number, and never take one from a dataset persona.
- **Entry through an in-app browser** (a link opened inside KakaoTalk, Naver or another app) is a context facet. Add it when the brief or a supported claim says users arrive that way. Mark the step untested when the driver cannot reproduce that entry.
- **초성 search** (typing only the initial consonants, such as ㅅㅅ), **English-only menus** and **queue pressure (눈치)** at a kiosk or counter are cues only when a claim supports them. The KCA kiosk studies in `references/research/korea/statistics.md` (section 4, question 6) are quota samples and self-reports. They can justify a time-pressed kiosk condition. They do not give a share of users.
- **Age thresholds differ by source.** The digital divide survey counts older adults from 55, the KCA older-consumer study from 65, and personas often use 60. Record the threshold the persona uses and where it comes from. Do not carry a value from one age frame to another (`references/research/korea/statistics.md`, section 3).
- **Speech register is an assumption.** A persona's 반말 or 존댓말, slang or 초성체 is a way to write test input. It says nothing about age, gender or ability. Dataset fields such as age or region change a scenario only when they change the task (`references/research/korea/query-craft.md`, section 5.6).
- **Community norms describe content, not people.** A board's usual tone, sarcasm or voting habits never become a persona's gender, age or political lean. A community's modelled audience is never attached to a poster, a claim or a persona (`references/research/korea/platform-map.md`, section 4).

Example of a Korean scenario (the IDs are illustrative):

```text
Scenario ID: S-05
Audience ref: none (no audience file; a manual scenario for a sign-up check)
Persona source: manual, basis synthetic
Sample rule: one first-time user, varied in one facet (entry)
Relevant attributes: opens the sign-up link inside a chat app's in-app browser (from the brief)
User segment: first-time user
Task ID and concrete data: T-signup: create an account with the team's test identity
Task goal: complete sign-up
Context: entry through the in-app browser; no other facet
Device and input: small mobile, touch
Starting state: staging with mock 본인인증 and a test SMS number the team provided
Constraints: the SMS code expires
Expected success: verification completes and the form keeps its input
Likely failure: the verification popup is blocked or lost in the in-app browser
Claim IDs: none (exploratory scenario)
Evidence that motivated the scenario: the brief lists in-app entry
Untested steps and why: production 본인인증 is a stop; recorded as untested (미검사)
```
