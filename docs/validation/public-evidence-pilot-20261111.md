# Public evidence pilot and research-to-library intake — 2026-11-11

## Outcome and scope

This change connects a current research persona export to the persistent persona library without re-authoring the same behavioral hypothesis in a second input format. The real pilot collected three public institutional pages, retained their limited evidential status, saved two authored synthetic personas, reused them in fresh CLI processes, and exercised local journey planning, claims, draft rejection, evidence recording and reporting.

This is **not** evidence of representative DC/YouTube demand, observed participants, improved human UX, or product readiness. There were **zero direct user observations and zero browser captures**. Both actual CLI journey tasks remain `inconclusive`; three mapped requirement assignments remain incomplete. The eight local functional success/recovery criteria are supported by genuine CLI logs, not human behavior.

Base: `rem/persona-journey-replay-20261111` at `a54276f8bbff9047ff0625018fab3e99da374e7f`, verified against origin before creating the independent `rem/public-evidence-pilot-20261111` branch/worktree. Previous capture-retention, evidence-admission, comparison and replay changes remain in the ancestry.

## Actual missing connection and improvement

The existing `export-personas` command produced a validated `qa-personas.json` research packet. The library's ordinary `import` expected a different schema. On the actual first public export, the base commit's CLI rejected direct import with exit 2:

```text
persona_input: Missing or unexpected input fields.
```

This failure occurred after real merge, gate and export, not merely on an invented malformed JSON document. A separate owned regression also reproduced the missing `import-research` command before implementation.

The new product command is:

```sh
python3 skills/remorsearch-ux-qa/scripts/ux_personas.py import-research \
  --library /absolute/private/persona-library \
  --research-run /absolute/private/research-run \
  --input /absolute/private/research-mapping.json
```

The mapping names the product, exact PRD context, source export ID/hash, selected source/destination persona IDs and requirement IDs. It does not supply replacement source text, claim grades or authored personas. See [the mapping and workflow reference](../../skills/remorsearch-ux-qa/references/persona-qa/persona-library-swarm.md#13-import-a-current-research-export-into-the-library).

The adapter:

- Reads the authoritative committed export and current research gate; copied arbitrary packets do not establish provenance.
- Preserves decisions, expected behavior, failure hypotheses, both falsifying questions/tests, assumptions, unknowns, concrete-data absence and exact motivation cards in `profile.research_scenarios`.
- Keeps synthetic/inferred/unverified labels and existing claim support levels. It never creates tasks, permissions, observations or passed results.
- Publishes all selected profiles atomically while holding Library then Research locks. It rechecks export and PRD immediately before save.
- Leaves exact current retries byte-identical, including revisions. Changed destination contents require an explicit current `expected_revision`; prior history remains.
- Refuses stale/failed latest exports, missing or unsafe claims, withdrawn or expired source dependencies, unsafe paths/modes, retired destinations and corrupted existing profile fingerprints.
- Continues to validate structured projections on reuse, claim and report. Ordinary import cannot inject the adapter-only fields.

Source dates and scope remain available through the linked validated research bundle; the library does **not** duplicate full source cards. The host must still review PRD mappings and author actual journey actions and safe conditions.

## Public collection method and access limits

The bundled insane-search Phase 0 routing and provider guidance were read first. The installed GPTaku Insane Web connector's `research` workflow and URL reader were used for the public Stack Exchange API documentation and GOV.UK terms. Its exposed reader takes a URL rather than a free-form query. Allowed host search was therefore used for discovery and a counter-search; content capture used the shipped `ux_research.py read` route.

The new run was `run-20261111T133429Z-be609f`, with `test_hooks:false`, rendering off, honest user agent, no authentication, no terms override, host budget 5, document budget 15, search budget 8 and minimum request interval 8 seconds. No alternate browser, identity, renderer, API route or proxy was used after a site's stop.

| Attempt/source | UTC capture/decision time | Result and condition |
| --- | --- | --- |
| [DC programming board](https://gall.dcinside.com/board/lists/?id=programming) | 13:36:18 | Exit 3, `terms_restricted`, rule `dcinside-terms`, `written_permission` requirement. No current user terms check was supplied. `contacted:false`: stopped **before any request**, so there is no DC HTTP status. |
| YouTube | Preflight; no request timestamp | Neither supported API-key environment variable was present. Only presence was checked; no value was printed. No API request, channel or comment was collected. No account or credential setup was performed. |
| [GOV.UK analysis guidance](https://www.gov.uk/service-manual/user-research/analyse-a-research-session) | 13:36:31 | HTTP 200; robots HTTP 200/allowed; R1 honest UA; `ok_strong`. |
| [UX Stack Exchange candidate](https://ux.stackexchange.com/questions/126296/are-personas-actually-useful) | 13:36:43 | Robots HTTP 418 was recorded as unavailable; the document returned HTTP 403 with a JavaScript/browser-check interstitial. The reader stopped and opted out `stackexchange.com`. No bypass, render, API or subsequent candidate fetch was attempted. |
| [GOV.UK needs guidance](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs) | 13:38:39 | HTTP 200; previously checked robots HTTP 200/allowed; R1 honest UA; `ok_strong`. |
| [GOV Reuse Library research summary](https://reuselibrary.service.justice.gov.uk/research-on-reuse) | 13:38:52 | HTTP 200; robots HTTP 404/unavailable, permitted by the existing reader policy; R1 honest UA; `ok_weak`, not upgraded. |

The actual reader made **four document HTTP requests and three robots requests**, yielding three usable pages. DC's pre-request stop and YouTube's unconfigured route are not counted as document requests. Search-provider calls and the two connector reference/policy reads are separate from those counts.

[GOV.UK terms](https://www.gov.uk/help/terms-conditions) were checked through the installed URL reader at 13:39:36.138Z. They describe Crown copyright/OGL coverage and exceptions. This pilot keeps attribution and original summaries; it does not infer permission for unrelated community sites, claim government endorsement, or republish source pages. The Ministry of Justice page is retained only as a short contextual lead, with its weaker robots result and unspecified source date visible.

### Search timing precision

There were three real search tool calls with five query strings:

1. Two discovery queries for GOV.UK research guidance and UX Stack Exchange persona reuse. The original invocation timestamp was not captured. Its receipt explicitly uses **13:36:18Z as an upper bound**, not an exact search time.
2. Two discovery/limitation queries at **13:37:15.801Z**, including research reuse and assumptions versus actual users.
3. One GOV.UK counter-search at **13:41:33.454Z** concerning persona limitations and substitution for users.

Search snippets were leads only. The counter-search found limiting guidance; it does not establish exhaustive absence of contrary evidence. The three P2 context-only claims do not pretend to have completed formal per-claim counter-search outcomes.

## Minimal retained evidence

The three successful pages were scrubbed by the reader. A second review found no real names, handles, emails or other personal identifiers in the retained excerpts. Placeholder author markers and fictional travel/demographic examples were not restored or used as persona attributes. No author identity hashes, participant identifiers, profile URLs or demographic distributions were created.

| Source record | Capture | Scrubbed content SHA-256 | Source date and retained meaning |
| --- | --- | --- | --- |
| `SRC-e45b2798` | `F-6cdab81adb00` | `e47f1cfd5f710be504f1546c8fa26470549a2d15d9d33cefb34c77c1af57029b` | Published/updated 2016-05-24. Guidance on analysing, recording and sharing findings. |
| `SRC-cc79a1c6` | `F-99dbb90df8c8` | `d9a4e8a5fe3869ec481b2e3b183ae38433434269627202394d06fcc09625a5ed` | Published 2016-04-04, updated 2017-03-23. Guidance distinguishing suggestions from validated user needs. |
| `SRC-f051e488` | `F-dc29cc91bbbb` | `2439b8098caa0bcfbf6fe1d9d09e609d1f865e06ffa4ed4b2eaa45034036343c` | Publication/research date **null**. Institution-authored summary of difficulty judging reusable resources' currency, testing and suitability; sample and method unspecified. |

All sources are `official_docs`, family `intent`; their three evidence rows are context rather than counting evidence. The live procedural gate left all three claims `lead_only`, with **zero counting evidence and zero user-behavior observation records**. The old dates, null dates and institutional scope were preserved and checked after library reuse.

In the research schema, `observed` on these evidence rows means that the public statement was actually captured. It does not mean that its asserted facts were independently verified, that a participant was observed, or that a product action occurred. The two exported personas and their scenarios remain `synthetic`, `inferred`, `unverified`.

Only three short supporting excerpts (21, 21 and 16 words) and self-authored summaries remain in the private research state. No source excerpts, raw captures, private mappings, claim leases or library data are included in this commit. The shipped `close` command removed this run's three temporary page captures and salt at **14:03:56Z**, while preserving minimized validated research needed for later reuse. This cleanup touched only this newly created pilot; pre-existing data was not removed.

## PRD → evidence → persistent hypotheses → bounded journeys

The current export was `QAB-49f2814197e17003789c14e0`, packet SHA-256 `eef7f0a1bf9b387f2e0213a61ae44ca485766257e5e793c3ae4b4060fc05c149`. The PRD binding is `64e7c741aaccea8b9222c614933f2d0a8dbeadb31a3d2fe582242f958dc8fe94`.

| Persistent persona | Authored hypothesis, not a recruited group | PRD mapping | Revision/profile SHA-256 |
| --- | --- | --- | --- |
| `PER-public-reuse` | A developer checks context and uncertainty before reusing a saved research hypothesis. | `REQ-INTAKE`, `REQ-REUSE` | 1 / `eca28f4f45f3451aa45c44e170c745f3dff90548125d58e942dafd9750d2c416` |
| `PER-public-scope` | A researcher distinguishes institutional guidance, authored assumptions and actual execution status. | `REQ-EVIDENCE` | 1 / `8f8dba817b10ea276afe179ca87078ad43cde463d16b4dbbd2e755415a5d8a52` |

Transferring government research/reuse contexts to Remorsearch is an explicit unvalidated assumption. These are exploratory P2 scenarios, not evidence that either segment exists at an estimated frequency.

The actual post-import pilot checked **34 local functional invariants**. They include exact scenario/decision/falsifier preservation, lead-only claims, assumption and unknown retention, source dates/scope, identical retry without a new revision, fresh-process reuse after research close, pending/no-receipt planning, current claims, and rejection of an observation-free draft without changing state.

Both authored CLI tasks proceeded through `plan → claim → receipt-starter → record → report`. Actual command exit codes, elapsed times, output hashes and checked invariants were retained in private execution logs. The receipts state their CLI-only scope. Their functional criteria are not a human UX score.

Two harness issues are preserved in the execution notes:

- The first helper assumed `close` would leave an empty pages directory. The actual command correctly removed the directory and salt; the harness then stopped on `FileNotFoundError`. The subsequent check required absence and confirmed the real closed state. This was not a product failure.
- After the first task's truthful `inconclusive` receipt, the existing shared-resource quarantine withheld the second claim. The host checked the finished CLI process, saved profile and evidence digest, then used the existing explicit `settle` command. Neither state nor evidence was manually edited. The second task was likewise inspected and closed without retry or conversion to pass.

Final stored report:

```json
{
  "counts": {
    "pending": 0, "running": 0, "passed": 0, "failed": 0,
    "blocked": 0, "inconclusive": 2, "skipped": 0
  },
  "requirement_assignments": {
    "mapped": 3, "passed": 0, "failed": 0,
    "incomplete": 3, "excluded": 0, "unassessed": 0
  },
  "all_declared_requirements_passed": false,
  "product_ready": false
}
```

Both tasks retain their original single attempt and receipt. Three narrowly declared CLI obligations were checked, but the scheduler does not promote them to passed requirements when the task remains inconclusive. No PNG was manufactured to satisfy the existing passed-task evidence contract.

## Effect comparison boundary

The measurable before/after result is a product connection: the base CLI rejects the research packet; the new CLI persists two validated hypotheses and passes them unchanged into subsequent local assignments. This removes a second manual transcription step. It does **not** measure how much easier a person finds the workflow or whether it improves discovery of real UX defects.

No fresh blinded effectiveness result is claimed. The repository's PE1/PE2 protocols and adjudications are already published; those fixtures are development material after disclosure. The held-out-2 checkout contains audience material but lacks the complete product/scenario/key suite. The benchmark runner loads answer keys even for its planning path, so it was not used as a new blind experiment. Browser-based benchmark execution was also outside the allowed scope.

A meaningful effect study still needs independently prepared, sealed new cases or permitted real participant/product observations, a predeclared comparison and no answer leakage. No actual-user success rate, market share, prevalence or synthetic “UX improvement” percentage was fabricated.

## Regression and packaging verification

The new module contains 25 owned offline tests covering successful export/import/claim/report, source and ID mapping, idempotence, explicit revision/history, concurrent identical import, before-save failure, lost acknowledgement, restart/closed-research reuse, stale/failed exports, missing/unsafe/withdrawn/expired evidence, PRD changes, privacy and permission boundaries, retired destinations, malformed projections, corruption detection and review-deadline consistency.

One focused run passed 113 tests before the current-body integrity guard and two additional cases; a subsequent five-case affected-path run passed on that intermediate revision. After the review-deadline fix, all 45 intake and ordinary Library cases passed on final product code. No existing assertion was weakened, and no new xfail was added.

Independent code review reproduced a second concrete defect in the new adapter before publication: an identical request checked 1 ms before its review deadline and committed 1 ms after it could change revision 1 to 2 without `expected_revision`, despite identical profile content, and renew the review period. The new regression first failed with `[(2, True)]` instead of `[(1, False)]`. The fix uses one timestamp for the adapter's complete batch and its atomic commit. It preserves exact no-op bytes across that boundary; an already-expired-at-entry request still requires the explicit current revision, and an explicit reviewed update still creates revision 2. No deadline, existing assertion or permission requirement was relaxed.

The first full discovery ran 1,293 tests with one failure and one intentional skip: the failure was the README link to this validation document before it had been created. A subsequent preliminary release run put its test TMPDIR under the repository's `dist/` directory. Seven runtime-discovery cases then failed because the existing finder deliberately refuses PATH runtimes under the working tree. Its other 12 non-web checks passed. This was corrected by placing test temporary data in a new private sibling, without modifying runtime safeguards or test expectations. Those preliminary logs remain separate; only the final frozen-code results below are the release regression evidence.

The final product/test revision completed the following observed checks:

| Check | Observed result |
| --- | --- |
| Full unittest discovery | **1,294 tests, zero failures/errors, one intentional opt-in capture skip**; unittest time 142.273 s |
| Frozen-code focused intake + Library | **45/45 passed**, including the deadline regression |
| Extracted installed code | **25/25 intake tests passed**, no skips; unittest time 53.552 s |
| Packaging, integrity, relocation and source comparison | Passed the 12 checker items listed below |
| Browser driver | Intentionally not run; no browser-readiness claim |
| Input stability during the measured intermediate checker | Failed because this validation document was updated while the checker was running; no product/test source changed |

The 12 passing checker items were `unit-tests`, `release-files`, `bundle-build`, `bundle-integrity`, `extracted-integrity`, `extracted-runtime-discovery`, `extracted-research-help`, `extracted-search-source`, `extracted-search-method`, `search-method-body`, `extracted-smoke` and `current-source-match`. The separate `validation-inputs-stable` failure is preserved; extracted test success does not waive it. This intermediate checker correctly returned exit 1, `ready:false`, `published:false`.

The tested ZIP was **4,116,209 bytes**, SHA-256 **`42f26f66cbe785adef990ace527ed6af47d3898bbebb1acd932d1cffd029f7eb`**. The 25 unchanged test cases used the extracted CLI launcher **and** in-process runtime modules under `candidate/extracted/remorsearch-ux-qa`; they did not silently import the source checkout's implementation. Source/extracted fingerprints matched exactly:

- `uxpersonas/research_intake.py`: `e689fcf1629aa2c5c308fccf69a2b97334ed13b91bfc3efb2eadfb3c856e3b5c`
- `uxpersonas/library.py`: `5797a6d9f4067165d23b116056e3be50c49da005706ebe0d1ea9ec9ad45dbc56`

The single full-suite skip was `ActualPaintCaptures.test_frozen_browser_captures_feed_real_checks`, because `ERGO_PAINT_CAPTURES` was absent. It was not an intake, retention or replay regression.

Publication requires a subsequent standard `check_release.py --skip-web` invocation after **all nine files, including this completed measurement record, are frozen**. Its input-stability result and timing are reported in the completion record alongside the final commit/remote SHA; this file is not rewritten during that run to insert its own future results. Only a result with all 13 non-web checks passed is acceptable. The browser skip still requires `ready:false`; no release flag is overridden.

## Actual command measurements

MacBook, Python 3.14.7. Times and maximum resident set size below come from `/usr/bin/time -l` on actual commands; they are single observations, not statistical performance claims. Network wall times include policy checks and required pacing. RSS is reported as raw bytes to avoid platform-unit ambiguity.

| Command/scope | Result | Wall seconds | Peak RSS bytes |
| --- | --- | ---: | ---: |
| Real research `merge` | pass | 0.21 | 37,421,056 |
| Real research `gate` | pass; all three claims lead-only | 0.17 | 34,586,624 |
| First real `export-personas` | pass | 0.20 | 41,451,520 |
| Base ordinary import of real exported packet | expected exit 2 | 0.16 | 38,273,024 |
| New first `import-research`, two profiles | pass | 0.28 | 36,192,256 |
| Same-input import after close | unchanged revisions/bytes | 0.25 | 37,060,608 |
| Fresh-process reuse after close, reuse persona | pass | 0.12 | 35,635,200 |
| Fresh-process reuse after close, scope persona | pass | 0.12 | 35,766,272 |
| Two-task plan | pass, initially pending | 0.16 | 38,027,264 |
| Final report | exit 0; two inconclusive, no passes | 0.16 | 37,797,888 |
| Final-code public-packet reimport after the deadline fix | unchanged two revision-1 profiles | 0.24 | 36,536,320 |
| Final-code public-packet reuse, reuse persona | pass | 0.12 | 35,667,968 |
| Final-code public-packet reuse, scope persona | pass | 0.12 | 35,487,744 |
| Final-code report on preserved pilot | same two inconclusive results | 0.21 | 38,289,408 |
| Focused 113-test run before final guard | pass | 40.57 | 57,573,376 |
| Intermediate affected five tests | pass | 6.21 | 43,548,672 |
| New review-deadline regression before fix | expected failure; unauthorized revision reproduced | 1.09 | 43,827,200 |
| Final intake 25 + existing Library 20 cases | all 45 pass | 31.38 | 42,647,552 |
| Frozen-product checker while this document changed | functional 1,294-test result passed; input stability failed | 146.40 | 135,954,432 |
| Extracted installed intake cases | all 25 pass, no skips | 53.78 | 46,120,960 |
| Initial full suite before this document existed | one missing-link failure, one skip | 139.86 | 135,217,152 |
| Preliminary release with incorrect in-workspace TMPDIR | four failures, three errors, one skip | 147.43 | 154,189,824 |
| Required loop smoke, 18 commands | pass | 1.59 | 30,031,872 |
| Required research fixture | pass; zero network requests, invented content | 0.48 | 51,347,456 |

Actual reader invocation elapsed times: DC pre-request stop 0.110593 s; analysis guide 13.321004 s; blocked UX Stack Exchange 11.627508 s; needs guide 1.757757 s; reuse summary 13.505582 s. These are not per-page model latency or server-only timings. No RSS measurement was captured for those early reader calls. The refined final hypotheses were re-exported after semantic review; the 0.20 s export measurement refers to the earlier actual export, not that refinement.

The complete pilot used more than one coordinator invocation because of the two documented harness boundaries. Its final continuation measured 1.89 s and 38,174,720 bytes; this is not presented as the total collection-to-report duration. The original journey receipts retain their earlier CLI source-manifest binding unchanged. After the final deadline fix, actual import/reuse/report commands rechecked the same collected public packet and proved both the library and journey-state bytes unchanged (0.76 s, 38,289,408 bytes for that four-command coordinator). No historical build artifact or receipt was rewritten to claim new execution.

## Remaining product and research limits

1. **Direct community/YouTube need validation remains unperformed.** DC needs the applicable permission/terms basis; YouTube needs an existing permitted API configuration. Neither was created or bypassed here. A different legally accessible public community sample could also be scoped.
2. **This is an institutional-context pilot.** Three non-independent institutional pages, two old guidance dates and one undated summary do not validate target-user demand or representative persona populations.
3. **Journey planning remains host authored.** The new bridge preserves hypotheses but deliberately does not invent safe actions or semantic PRD coverage. The explicit mapping is still structured JSON.
4. **Source inspection is linked, not fully surfaced.** Dates and scope are in the validated research bundle; they are not all copied into the library summary/claim output.
5. **CLI-only task completion is not represented as a full pass by the current receipt contract.** It requires a genuine PNG for passed tasks. This pilot kept `inconclusive` and reported functional facts without weakening that contract.
6. **Closed research and library are local.** Reuse requires the valid linked run, unchanged PRD and permitted source retention. There is no automatic cloud export or cross-machine migration.
7. **Actual UX effects and browser release readiness remain unverified.** Existing public benchmarks were not relabeled blind, and no real account, deployed service or human session was changed.

## Repository preservation and publication scope

The approved fetch and push URL is `https://github.com/remorser58/Remorsearch_UX_QA_Skill.git`. The cumulative replay branch still resolved to `a54276f8bbff9047ff0625018fab3e99da374e7f` on the 14:15:46Z preservation check. Capture retention, comparison, evidence boundary and replay commits were verified as ancestors of this branch.

All ten pre-existing worktrees retained their initial HEAD, branch, porcelain status and aggregate tracked/nonignored-file hashes on that check, including the dirty integration tree. Both pre-existing long-lived processes remained present. The old managed work stayed at revision 29 with no open operations or pending commands; it was only inspected, never resumed or controlled.

The commit scope is the explicit nine files: PRD, both READMEs, the persona-library reference, CLI, Library, new intake module, new regression module and this validation document. Private research/persona/journey data, temporary command logs, fixtures created during validation and generated distribution output are excluded. Review included the exact diff, ancestor/remote checks, active-hook inspection and secret-pattern scanning of the selected files. No force push, remote rewrite, installed-skill change, global Git configuration change or deployment is part of this work.

The completion report supplies the final commit SHA and independently re-read remote branch SHA after the approved ordinary push. The published branch can be verified without checking out or modifying another worktree:

```sh
git ls-remote origin refs/heads/rem/public-evidence-pilot-20261111
```
