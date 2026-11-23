# Evidence and Severity

## Evidence levels

### Verified product observation

The behavior was reproduced in the actual product or connected app with recorded steps.

### Verified design mismatch

The implementation differs from the current Figma or specification in a way that changes the intended task, state, hierarchy, or accessibility.

### Repeated user signal

Independent users describe a similar situation or workaround across one or more channels.

### Official constraint

Product documentation, policy, design system, or platform behavior explains the intended rule or limitation.

### Inference

The analyst connects evidence into a probable cause or outcome. Keep the supporting items visible.

### Unverified

The claim depends on inaccessible material, an unreproduced screen, a stale report, or ambiguous context.

## Severity

### P0

Blocks a critical task, causes serious data loss, creates a safety or privacy risk, or makes a high-stakes action misleading.

### P1

Causes repeated task failure, major confusion, lost work, inaccessible controls, or material trust damage for an important user segment.

### P2

Adds meaningful effort, slows comparison or completion, hides useful information, or causes avoidable support contact.

### P3

Minor inconsistency, visual polish issue, copy refinement, or low-impact deviation without meaningful task harm.

Severity follows user impact. Confidence describes the strength of evidence. Research gate statuses decide whether community evidence can motivate a scenario; an observed product failure retains its impact-based severity. A missing audience file does not reduce that severity. Ergonomics model/judgment caps apply to those evidence types; a reproduced state-loss or required-control failure is a product observation.

## Finding card

Use this order, also defined in [the QA report template](qa-report-template.md). Sort P0 → P1 → P2 → P3, then high → medium → low confidence.

```text
ID and severity: one-line user-impact rationale
Where: tested build ID; screen/state; device and CSS viewport/DPR; input
Who: persona or scenario ID and basis; task and intact completion condition
Steps: start URL and starting state, then numbered actions and exact inputs
Expected: intended behaviour, quoting relevant visible controls/labels
Observed: action followed by actual behaviour, quoting exact visible UI text
Evidence: capture link + receipt; matching text dump; supporting trace IDs
Why it matters: user consequence; possible product effects labelled inference
Cause: verified or inferred; supporting observation IDs; unknown layers stated
Fix: layer; concrete change; trade-off; screen state that proves success
Standards (accessibility only): KWCAG 2.2 item/status; WCAG 2.2 SC/status apart
Second pass: record below; disagreement and written resolution, if any
Confidence: high/medium/low and its evidence basis
```

For every P0/P1, explain the cause chain from screen state to interaction/state mechanism to user consequence. Label deeper causes as inferred and keep their unsupported details in the annex. A successful banner does not prove preserved inputs, correct amount or independent completion.

### Capture receipt

Write next to each capture during the run:

```json
{
  "artifact_path": "captures/example.png",
  "sha256": "[64 hexadecimal characters]",
  "captured_at": "[ISO timestamp with timezone]",
  "surface_url": "[captured URL]",
  "build_id": "[commit, version, deploy ID or page hash]",
  "device": "[device ID, viewport and DPR]",
  "quoted_ui_text": "[exact visible text]"
}
```

Record run start and link the capture's text dump. A P0/P1 without a receipt newer than run start stays unverified. A hash computed while assembling an archived report proves the bytes copied; capture-time provenance remains unknown. Leave unknown fields null and state the gap. Never substitute file-copy time for capture time.

### Second pass

For every P0/P1, use at most three priority scenario packets covering the findings. A separate reader sees only the capture and its text dump, without the draft. Freeze their assessment, then compare severity with the first pass and record:

```json
{
  "finding_id": "F-01",
  "reviewer": "self",
  "task_completed": null,
  "control_name": "[visible name]",
  "omitted": "[missing information or nothing omitted]",
  "severity": "agree",
  "inconclusive": true
}
```

Use actual JSON booleans/null in filled records. `reviewer` accepts `subagent` or `self`; severity comparison accepts `agree` or `disagree`. Hosts without subagents run the same capture-only record as a labelled self-pass and state its lack of independence. Resolve every disagreement in writing before finalising. If the packet cannot establish the behaviour, preserve the unverified status and name the needed trace/replay.

### Verification and accepted fixes

Keep unverified cards and unsupported community claims in the annex. Where the browser/surface cannot be exercised, evidence is stale or minimum coverage is missing, the decision is `inconclusive`; name the blocker. Absence of findings requires coverage proof before `ship` is possible.

An accepted fix records the baseline artifact/receipt/build, actual change and trade-off, then the fresh replay artifact/receipt/build on the same scenario and device. Repeat the second pass for P0/P1 fixes and record regressions. A comparison between A and B or a future test plan supplies no post-fix result.

### Synthetic evidence card: Undo the current list change

Use an owned, disposable list with `S-17` tagged Blue and a lookalike `S-18` tagged Gray. In each fresh run, change only `S-17` from Blue to Amber and first verify that change in a separate visible readback. Use the Undo offered for that specific change, not a global Undo history. Record which change the control identifies, what the UI reports, and the independently observed result. Use a fresh approved list view or reopen and match the stable record ID, tag and visible row count; the original optimistic view or a success toast cannot serve as independent readback.

| Synthetic branch | Evidence to retain |
| --- | --- |
| One timely Undo and reopen | Exactly one `S-17` row, Blue again; `S-18` still Gray. Check the persisted view after reopen. |
| The same change-specific Undo can still be invoked after the first success | On this fixture only, repeat that control once. The readback should be unchanged, with no added rows or changes to other records. A single visible row does not prove a single write; leave the write count unverified without independent evidence. |
| Reopen before Undo, or pass the declared expiry | Probe separately under the product's stated scope. If this Undo is still valid after reopen, use the timely check. If unavailable or expired, no restoration should be claimed and `S-17` should stay Amber. Never substitute another Undo. |
| A newer owned edit changes the same tag to Green before the old Undo | First verify Green in a fresh view. For a fixture whose rule rejects stale Undo, check that the old control is unavailable or rejected without a success claim and that Green survives. A silent rollback to Blue fails; if the product cannot safely expose this branch, leave it untested. |

If the original change or newer edit cannot be independently confirmed, the affected branch cannot establish a result. If fresh readback after Undo is unavailable, keep the UI and persistence verdicts separate and leave restoration unverified.

[Apple's Undo and Redo guidance](https://developer.apple.com/design/human-interface-guidelines/undo-and-redo) recommends making the affected action and result clear. [RFC 9110 §13.1.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1) describes conditional HTTP updates as one way to guard against overwriting newer state. These motivate the checks, not an implementation requirement or guarantee about expiry, reopening, or cross-session behavior.

## Writer self-check

- Decision first; impact-based P0–P3 and confidence kept separate.
- Every verified P0/P1 has a same-run receipt and a capture-only second pass; disagreements have written resolutions.
- Every research claim cited has a gate status; unsupported claims and unverified cards stay in the annex.
- Cards quote visible text and specify build, reproduction, cause, fix and replay criteria; standards have separate statuses.
- No names or handles; missing evidence, blockers and what was not tested are stated.
