# Behavior guidance QA

Use when a PRD task depends on finding, understanding, starting, continuing, declining or recovering an action. Optimize for the user's intended outcome, not for acceptance, dwell time or clicks. A refusal, pause or exit can be the correct outcome. This is a scenario-design reference, not a new runner, a permission grant, or a claim of human effectiveness.

## Turn research into a replayable check

| Step | What to record on the existing task | What to replay |
| --- | --- | --- |
| Goal and barrier | PRD goal and version, user outcome and constraints; note whether the blocker is understanding, opportunity/access, or a competing goal. Link an observation, not a guessed motive. | Start without telling the tester which control to use. Record where they first look or act and what actually changes. |
| Cue and decision | Place/time of the cue, what action it implies, visible and accessible labels, stated consequences, defaults and alternative routes. | Correct action, plausible wrong action, decline or later, keyboard/touch where relevant. Verify that declining really avoids the side effect. |
| Action and result | Expected target state or saved value; distinguish accepted input, waiting, completed, partial, failure and retryable states. | Observe the result, not just the click or toast. If correctness depends on persistence, reload or re-enter when approved. |
| Failure and return | Last safe state, input to preserve, duplicate-write risk, back/cancel/undo/timeout behavior. | On owned fixtures only, induce one representative failure; verify retained input, safe retry, no duplicate, and return to task. |
| Outcome and guardrails | Predeclare completion, accidental/duplicate actions, failed or false completion, and recovery. Capture time or steps only on comparable tasks. | Compare same initial state/build pair, device, data and inputs. Measure opt-out completion separately; check accessible feedback and unchanged adjacent flows. |

When a mechanism suggests several fixes, correct the blocker before adding a prompt. Examples: rename an ambiguous action before adding a tutorial; preserve a draft before adding a retry reminder; let users continue without optional permissions before moving the grant button. Record cue and result separately. Never use a synthetic run to claim a change in human motivation, long-term retention, population conversion or satisfaction.

## Source notes and transfer limits

- [Wharton, Rieman, Lewis & Polson, Cognitive Walkthrough](https://www.colorado.edu/ics/sites/default/files/attached-files/93-07.pdf), §2.3/Table 1: assess expected action, whether it is findable, whether it reads as relevant to the task, and whether feedback signals progress. Use it for an inspection and a replay hypothesis, not an estimate of first-time success rates.
- [Michie, van Stralen & West, Behaviour Change Wheel](https://doi.org/10.1186/1748-5908-6-42) (2011): use capability, opportunity and motivation to encode possible barriers. The public-health design framework does not demonstrate the effectiveness of any particular digital cue.
- [Don Norman, Signifiers, not Affordances](https://jnd.org/signifiers-not-affordances/) and [Jakob Nielsen, Ten Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/): a control can work but not advertise where or how to act. Inspect visible cues and user control, not discoverability by screenshot alone. These are practitioner inspection lenses, not effect-size estimates.
- [Gray et al., The Dark (Patterns) Side of UX Design](https://doi.org/10.1145/3173574.3174108) classifies manipulative designs, including obstruction. [Nouwens et al., Dark Patterns after the GDPR](https://people.csail.mit.edu/ilaria/papers/Midas-MITCHI2020.pdf) tests consent designs; hiding first-screen refusal increased acceptance in their cookie-banner experiment. High acceptance is not consent comprehension. Do not transplant the observed effect size to other products. Check unequal step count, visibility, preselection and reversibility on equivalent options.
- [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) SC 3.3.4, 3.3.7 and 4.1.3 cover defined web cases for error prevention, redundant entry and status messages respectively. Check their scope; the analogous product guidance is not by itself a WCAG conformance claim. [GOV.UK Error Summary](https://design-system.service.gov.uk/components/error-summary/) is a concrete pattern for form errors with links back to fields, not a universal layout for every failure.
- [Rodden, Hutchinson & Fu, HEART and Goals–Signals–Metrics](https://research.google/pubs/measuring-the-user-experience-on-a-large-scale-user-centered-metrics-for-web-applications/) (2010) separates product goals from chosen signals and metrics. [GOV.UK Usability Benchmarking](https://www.gov.uk/service-manual/measuring-success/usability-benchmarking-a-website-or-whole-service) distinguishes task success, completion time, abandonment and false success using observed tasks. Synthetic traces can demonstrate task behavior; human understanding or product-level lift needs separately authorized evidence.
- [Bell et al., Drink Less notification experiment](https://mhealth.jmir.org/2023/1/e38342) (2023), Table 2: notifications increased immediate app opens, while time to disengagement did not differ significantly across the three policies tested. Separate opening, finishing the user's task, and voluntarily returning when the need recurs. Do not transfer the effect size to other apps.

## Example: retry an import without losing the previous result

User outcome: save the reviewed import once. Baseline shows Save followed by a network failure; the list still has the previous data. On a failure fixture, inspect that the draft and old list survive, the next action says what it will do, a retry commits once, and a reopen shows the expected stored value. On the decline/cancel route, check that the original list remains unchanged. A successful click or temporary success notice alone cannot pass.

## Interrupted drafts: prove what will reopen

Use a disposable draft with distinguishable revisions A and B. Interrupt after B in each supported state: confirmed save, locally retained but not synced, and save unavailable. Before leaving, record what the UI says will survive, where it can be resumed, and what the user needs to do. Independently check the recovered revision, identity/account and storage scope; do not count a toast as evidence. Test another device only when the product promises it. For retryable commits, prove exactly one result; for collaborative flows, add a newer competing revision and verify both conflict handling and recovery.

[Figma documents](https://help.figma.com/hc/en-us/articles/360040328553-What-can-I-do-offline-in-Figma) offline edits in the current browser and later sync; pending edits are not portable. Its [engineering account](https://www.figma.com/blog/behind-the-feature-autosave/) explains crash recovery and the risk that applying stale edits makes newer work appear lost. [Google Forms documents](https://support.google.com/docs/answer/10952360?hl=en) a same-account draft retained for 30 days under supported conditions and no autosave offline. Offline input not saving does not imply the earlier online draft was deleted; a saved draft is not a submission. These are documented comparisons, not live observations or evidence that either design works for your users.

For user research, distinguish time to the first correct resumed action, wrong turns, and eventual completion. [Trafton et al.](https://interruptions.net/literature/Trafton-IJHCS03.pdf) motivate measuring resumption separately; their lab task supplies no product-specific timing target.

## Example: verify the exported file, not the export click

For a task that already supports export, use owned synthetic records and a separately approved download location. Record the selected scope, service readiness, transfer outcome, and file inspection separately. Inspect only the readable artifact tied to the current attempt (for example, by its observed download entry or a clean approved destination, not by filename alone). Check format, exact record identities, permitted columns and a distinguishing value. Record the verdict and permitted evidence reference, not private contents. If the transfer is observed to stop before completion, record it as interrupted. If the runner denies downloads, mark the transfer and inspection `not_run`; if a completed transfer's artifact cannot be read with approved access, preserve the observed transfer outcome and mark only inspection `not_run`. Do not change permissions or retry automatically.

Synthetic check: the current attempt should yield `report.csv`, only columns `record_id,revision`, and only row `T-17,B`. A current, readable file that matches is the positive control.

| Negative control | Expected verdict |
| --- | --- |
| Only a previous `report.csv` is found, even with the expected columns and `T-17,B`. | Current file inspection is `not_run`; byte equality cannot establish that this attempt produced the file. |
| The current readable file has `T-18,B` instead of `T-17,B`. | Content check fails for wrong record identity despite a completed transfer. |
| The current readable file has the expected row but adds a `private_note` column. | Content check fails for out-of-scope data. |
| The runner denies the download. | Transfer and file inspection are `not_run`; do not substitute an earlier file. |
| Transfer completion was observed, but approved access cannot open the current file. | Keep the transfer outcome; file inspection is `not_run`. |

[Shopify's report-export guide](https://help.shopify.com/en/manual/reports-and-analytics/shopify-reports/report-types/custom-reports/export-reports) documents opening a completed local download and shows how column scope can differ for some legacy finance reports. [Firefox Downloads](https://support.mozilla.org/en-US/kb/where-find-and-manage-downloaded-files-firefox) distinguishes transfer progress from a finished file that can be opened. These are documented examples, not observations of the product under test.
