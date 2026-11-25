# PE-1 independent adjudication

## Verdict

**The primary head-to-head comparison is incomplete.** Both Q and R have evidence-backed reports matching all three seeded defects. Neither superiority nor a completed tie is established. R has no observed H9S outcome, and exact first-action-to-end timing cannot be recovered for either condition.

This is one worker per condition on six synthetic cases, not real-user evidence.

## Descriptive results

| Metric | Q | R |
|---|---:|---:|
| Unique seeded defects detected | 3/3 | 3/3 |
| Seeded defects missed in available findings | None | None |
| Unsupported unique reproduced-defect claims | 0 | 0 |
| Duplicate reports of one underlying defect | 0 | 0 |
| Clean-control false alarms observed | 0 | 0 |
| Clean controls with execution evidence | 3/3 | 2/3 |
| Complete clean-control false-positive rate | 0/3 | Not estimable; H9S unverified |
| Cases with execution evidence | 6/6 | 5/6 |
| Verified attempted actions | 60 | 45 |
| Successful / failed actions | 58 / 2 | 43 / 2 |
| Additional submitted, unconfirmed actions | 0 | 8 |
| Saved-screenshot interval | 107.584 s | 289.428 s |
| Exact total elapsed | Unknown | Unknown |

R also has one read-only observation, which does not increment action count. Its 45 verified plus eight unconfirmed submitted commands total 53 submitted actions, not 53 proved executions. Missing H9S execution is neither a pass nor a false alarm. The observed 0/2 control rate must not be presented as complete 0/3 coverage.

## Unique-claim checks

- **B7N / D2:** Q actions 11–16 show seats 27 becoming 14 after pause/resume, with Gold ribbons retained. R actions 30–38 show seats 23 becoming 14, with Ribbon planets retained, and 14 propagated into review/confirmation. Both match the oracle. R's propagated D1 consequence is the same defect, not another detection.
- **D5Q / I2:** Q actions 30–35 show Red clay, Twine, Red clay added on preview/back before Apply, then another batch on retry/apply. R actions 39–45 show Blue paper and Gold cord added before Apply, with later revised Silver ribbon/Wood beads appended once. Both match the oracle. Neither visible record localizes mutation to Preview versus Back. R's I1 label is not a separately demonstrated preview-only defect and earns no extra credit.
- **P8R / C1:** Q actions 36–40 and R actions 12–15 show selected Cedar becoming Maple after cost sorting and appearing in review. Q confirms Maple; R later deliberately replaces with Willow and confirms Willow. Both match the oracle; R does not claim erroneous Maple confirmation.

No genuine unseeded defect was established by these findings. The failed accessible-label operations are execution friction, not added product-defect claims.

## Evidence and coverage

Read the preregistration, public PRD and manifest, oracle key, verification and full 46-action oracle trace, both findings/summary files, and each condition's action log. Visually inspected 14 saved screenshots: Q actions 13, 15, 29, 33, 37, 38, 43; R actions 13, 14, 26, 29, 32, 34, 42. These directly support edited versus reset seats, chosen versus sorted room identity, canceled import changes and selected clean-control behavior. All referenced raw-log screenshots exist.

Q logs support bounded clean paths for K4M, T2V and H9S. R logs support K4M and T2V only. Q tested duplicate import names and reverse room sorting; R's plan explicitly excluded duplicate names and instead tested revised import content. These are differing bounded paths, not blanket PRD passes. Exact retained whitespace and transient import-preview state are unproved.

Three synthetic revision-1 saved profiles, import and unchanged revision-1 reimport records, the six-task/max-parallel-1 plan and persona-hash-matching receipts document workflow use. All 48 artifacts referenced by the five evidence-backed R receipts match their recorded hashes. The post-freeze H9S receipt has zero artifacts and remains inconclusive. Receipt acceptance is not independent proof of full PRD coverage.

## Integrity and deviations

All six fixture files match SHA256.json. Q frozen file hashes match the supplied pre-unblinding hashes. R file hashes match its recovery materialization, but its original conversational freeze is distinct from a pre-unblinding file hash. No new first-pass finding is present relative to the coordinator-provided frozen statement. Original freeze/exposure timing relies on coordinator provenance, not independently cryptographically verifiable evidence in these files.

Oracle trace hash matches verification.json and records 46 successful interactions across all six cases. However, the answer-key hash was not separately committed before the trial. Pretrial verification existed, but hashing the current key does not repair that precommitment gap.

Both first navigations failed with ERR_CONNECTION_REFUSED. Restoration of the same frozen server without resetting either budget is reported; the failed actions remain counted. Both then had a counted unsuccessful import-label fill. R additionally navigated to P8R before an accepted claim, then started fresh after the claim; both navigations count. R's rejected receipt/claim attempts are workflow friction, with some exact intermediate inputs not retained. No comparable model-call or token ledger exists.

R's existing log ends at action 45. The eight H9S commands have no retained execution result. A post-freeze inconclusive receipt does not settle their execution, and no new UI was performed for this review. Both initial failed actions lack exact timestamps: screenshot intervals are lower-bound observed portions, not total durations. Thus the exact 12-minute rule is not independently certified, although no logged action-count overrun is present.

Condition prose exposes strategy, so adjudication is not perfectly blinded. Logs contain no forbidden-operation evidence, but cannot prove the absence of every unrecorded action.

## Frozen hashes

- Q findings: `b27f18f280507bf6c14193449933ef7cdae9abbdd9271fd65648a5b7c7040aa1`
- Q summary: `0690c5ae56cae8d34e40cf0f3448390ba27c0352bae241400f19e483063a20b1`
- R findings: `fdd00d5aa4957700e7213cb2c64fda72028a00846eee75aff52bb87feb3558cd`
- R summary: `3430a8c00a983ac6db87799e461f9b4401b0780784a8e23eb33c6054765a1309`
- Current oracle key: `6eb1b9df13cee710971d1398e169358d995834741662827dbcc183507434fe7d`
- Oracle trace: `d1e45a3af77b7cd0aab8a63c9cb0617fca4513f9140ba067d306a68d7ee894af`

## Interpretation

Preserve the three supported findings per condition as descriptive partial observations. Do not rank the workflows, infer action/time efficiency, or treat this as proof of persona effectiveness. A fresh held-out experiment with complete execution receipts and timestamped starts is needed for a complete comparison. No target files were modified and no UI, commit or push was performed in adjudication.
