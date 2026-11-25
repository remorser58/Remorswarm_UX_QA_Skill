# UX controls: reuse and research decisions — 2026-11-19

## Scope and evidence

This review precedes expansion of the UX-controls implementation. It does not certify the
product, a device, a dependency release, or a human population. Dates are Korea time.
The feature branch starts at published `f60d79d3c31aff57a51d82ab041cb68da1fb2ff0`.
The separately owned latest worktree was read at
`982958e9f1fbbe2c058f9b6d8b8147add7565d1a` (clean; 46 ahead of local tracking).
No merge, reset, bulk push, or execution in that worktree was performed.

The complete difference is 13 files. Relevant source changes are the save-error wording
in `uxpersonas/peekly_criteria.py` and prerequisite ordering / bounded observation projection
in `uxpersonas/scale_run.py`. Those fixes must remain intact during later integration.
The root AGENTS, PRD and skill contracts did not differ between those revisions.

The current cohort receipt was read from the latest worktree:
`docs/validation/peekly-coverage-completion-20261115/cohort-20261116/cohort-receipt.{md,json}`.
Its JSON SHA-256 is `b37b7d0948e205e9dce0407cfb8380895cd3ee3e7fa5da766aa343d96348efc9`.
The receipt reports 32 final sessions, 136 criteria (113 passed, 23 not applicable),
1,196 artifacts, zero missing/hash discrepancies, and eleven sealed replaced rejudgments.
Both recorded engine source hashes were compared with the actual latest files and matched.
The user separately checked all eight queues: complete 39, uncertain 7, running 0, queued 0.
This development turn has not independently reread all eight databases or rehashed all
1,196 artifacts. These are historical evidence-integrity results, not a new UX experiment.
Preserve the seven uncertain outcomes and the repaired 030 result; do not resubmit them.

## Existing implementation before adding dependencies

| Need | Actual existing implementation | Decision |
| --- | --- | --- |
| Touch precision | `ergoqa/hf/pointing.py`: Fitts, FFitts and dual-Gaussian checks | Reuse; no new mathematical engine. Preserve calibrated versus assumed parameters. |
| Reach | `ergoqa/hf/reach.py`: `thumb-reach-v3-uncalibrated` | Retain as a limited heuristic. Newly located coefficients are a separate candidate, not an unreviewed replacement. |
| Gaze / viewing geometry | `ergoqa/hf/gaze.py`, perception helpers | Reuse geometry; modeled attention is not eye-tracking evidence. |
| Recorded experiments | `scripts/ergo_experiments.py`, existing benchmarks | Reuse same recorded runs for ablation. Do not tune on frozen held-out labels. |
| Personas and PRD | `uxpersonas/library.py`, research intake, coverage contracts | Extend current versioned import and exact PRD-byte checks. Do not add a persona database. |
| Execution | `scale_entry.py`, `scale_run.py`, SQLite queue | Bind choices to the existing plan and dispatch checks. No new scheduler. |
| UX fixes | `uxloop` checkpoints, patch intent, replay and intent gates | Extend receipts and selection. No Git reset and no second patch engine. |
| Browser evidence | `drivers/web`, `scale_browser_host.py` | Reuse installed driver. Manifest pins Playwright 1.56.1 and Node >=22,<23; this is not proof that either is installed or security-audited. |

## Open-source/API comparison and disposition

| Candidate / primary source | Actual interface and obligations inspected | Constraints and reasoned decision |
| --- | --- | --- |
| [CSS Modules](https://github.com/css-modules/css-modules), [composition](https://github.com/css-modules/css-modules/blob/master/docs/composition.md), [Vite](https://vite.dev/guide/features) | Existing bundlers interpret `.module.css`/`.module.scss`; importing returns a class map. `:global` and cross-file `composes` can escape a filename boundary. | **Reuse the target's existing compiler.** A path/property declaration alone cannot prove computed-style isolation. Require compiler-resolved imports, global selectors and affected components, plus Figma/readback and browser regression. Do not install Vite into this Python product merely to validate a suffix. |
| [postcss-modules API](https://github.com/madyankin/postcss-modules), [LICENSE](https://github.com/madyankin/postcss-modules/blob/master/LICENSE) | `getJSON(cssFileName, json, outputFileName)` exposes exported class mappings and may return a Promise. MIT requires preserving its copyright and permission notice when distributing substantial code. | **Use only if already in the target toolchain.** A class map is not an import/dependency graph or property diff. No new runtime CSS parser; no duplicated regex parser. Version, lockfile and advisory review remain per-target gates. Current upstream pages are not a pinned release audit. |
| [Nemotron-Personas-Korea card](https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea/blob/main/README.md), [viewer rows API](https://huggingface.co/docs/dataset-viewer/en/rows) | Documented rows endpoint; actual 32-row response revision `ada0f5b53a38bb5a30cce09358adde883c1ab63a`. Card declares CC BY 4.0. Retain attribution, license link, modification notice, revision and response hash. | **Adopt a minimized seed subset.** Keep age/province/occupation/education/family type; remove names and free-text narratives. First 32 adult rows are a convenience slice, not population coverage. Neither synthetic behavior nor hand size, impairment or viewing ability is observed from these demographics. |
| [NeMo DataDesigner](https://github.com/NVIDIA-NeMo/DataDesigner), [API guide](https://docs.nvidia.com/nemo/datadesigner/latest/getting-started/welcome), [LICENSE](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/LICENSE) | Builder/seed dataset APIs and model-provider orchestration. Apache-2.0 distribution requires the license, retained notices, change notices and applicable NOTICE handling; external models/datasets have separate terms. | **Do not adopt this orchestration dependency.** Current Library, research gate and queue already cover this product's need. Another generation framework adds model calls, destinations and maintenance without an established quality/performance gain. No package installed or provider called. |
| [MediaPipe HandLandmarker source](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/web/vision/hand_landmarker/hand_landmarker.ts), [guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker?tab=Web) | `detect(image)` and `detectForVideo(frame,timestamp)` are synchronous. Outputs include 21 landmarks and inferred world coordinates. Source header is Apache-2.0; the exact model artifact's terms/hash still need review. | **Candidate host adapter, not a new default dependency.** Synchronous inference can block interaction; benchmark existing host execution on actual devices. Pin SDK/model/WASM, avoid unversioned CDN assets, bound frames/retention. Monocular inferred meters are not calibrated physical measurements; occlusion, mirror/orientation and frame timing must be retained. Vendor latency is not our measured latency. |
| [OpenPose LICENSE](https://github.com/CMU-Perceptual-Computing-Lab/openpose/blob/master/LICENSE) | License limits the inspected distribution to noncommercial research; commercial use requires separate licensing. | **Reject as the product default.** Its licensing restriction and native model/runtime deployment burden do not fit a dependency-free extension. This is not interchangeable with an Apache/MIT component. No code/models redistributed. |
| [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), [metadata licensing](https://www.crossref.org/documentation/retrieve-metadata/) | `/works/{doi}` provides bibliographic metadata and deposited license/update information. Abstracts can remain copyrighted even when bibliographic facts are reusable. | **Reuse existing research HTTP/ledger gates.** Archive DOI/URL, retrieval/reading scope, version, rights and concise analysis. Do not add an SDK or mirror paywalled/full-text papers. A DOI record alone does not establish causal evidence or full-text reading. |
| [Python `os.replace`](https://docs.python.org/3/library/os.html#os.replace) | One successful rename/replacement is atomic; no multi-file transaction is promised. Existing `uxloop.io.atomic_bytes` already implements it. | **Reuse and narrow the guarantee.** Single-file reversal is supported with existing locks/checks. Block multi-file rollback before any write until the existing host provides a verified atomic publication transaction. A write-ahead recovery log is not multi-file atomic visibility. |

No new package was installed. No candidate is described as vulnerability-free: an exact
release/advisory audit is still required before adding an optional dependency. Changes to
third-party binaries, remote destinations, cameras or paid execution need their actual
authorization at integration, not a blanket consent inferred from silence.

### Maintenance/security screening boundary

The current upstream Playwright release page was checked; the repository's pinned 1.56.1
is not a current-release claim. The [reviewed advisory for CVE-2025-59288](https://github.com/advisories/GHSA-7mvr-c777-76hp)
lists affected versions below 1.55.1 and a fix at 1.55.1, so the manifest's 1.56.1 pin is
outside that particular range. This does not audit transitive packages or the actual
installed Chromium binary. The [maintainer advisory listing](https://github.com/microsoft/playwright/security/advisories)
being empty is therefore not evidence of zero vulnerabilities. No browser was downloaded
or dependency upgraded in this work. A locked runtime/browser update is a separate
compatibility and UX regression unit, using the existing driver.

The inspected [MediaPipe security page](https://github.com/google-ai-edge/mediapipe/security)
showed no published policy/advisories; no assurance is inferred from that absence.
Its synchronous inference API, model artifact terms and device measurements remain
concrete integration gates. The MIT/Apache code notices do not automatically license
datasets or downloaded models. NVIDIA seed attribution also follows
[CC BY 4.0 section 3](https://creativecommons.org/licenses/by/4.0/legalcode.en): retain
source/credit/license information and identify modifications. No endorsement is implied.

## Primary human-factors evidence

Facts below are from the specified original paper/author copy. An effect in a controlled
study is a hypothesis source for this product, not a product-level improvement result.

| Paper / reading scope | Sample, conditions and result | Application and limits |
| --- | --- | --- |
| [Parhi, Karlson & Bederson 2006](https://www.microsoft.com/en-us/research/wp-content/uploads/2006/01/parhi-mobileHCI06.pdf), DOI `10.1145/1152215.1152260`; methods/results read | 20 right-handed adults, 17 male/3 female, ages 19–42, HP iPAQ h4155, standing. Within-subject single and serial taps. Recommendations: 9.2mm discrete and 9.6mm serial. Discrete target-size effects include time F(1,25)=70.42 and error F(1,27)=49.18, p<.001; no standardized effect size was verified. | Physical-size sensitivity test, not a CSS-pixel constant. Older resistive PDA, convenience sample, fixed movement setup; first five participants had different block randomization. No basis to generalize to every hand, motion state or modern device. |
| [Bergstrom-Lehtovirta & Oulasvirta 2014](https://www.netlab.tkk.fi/~oulasvir/pubs/paper2117.pdf); model/methods/validation read | 20 adults (8 female), mean age 29.4, 160 trajectories on iPad Mini; constrained right-hand index placement, left-hand support permitted. Equation 5 coefficients: ay=-.013, h=-15.996, ak=-.257, bk=64.655. Mean reported cross-validation R²=.6799, RMSE=16.024mm. | Newly recovered coefficients close a knowledge gap, but do not justify automatic replacement of the existing heuristic. Need measured finger span/index placement and model axes. Extreme reachable area differs from comfortable repeated motion; error is material for small buttons. No age/nationality-to-hand-size inference. |
| [Lehmann & Kipp 2018 author copy](https://michaelkipp.de/publication/LehmannKipp18.pdf), DOI `10.1145/3279778.3279791`; methods and results tables read | 18 right-handed adults, ages 23–31; Nexus 5X, seated with elbows supported; three grips, 5/10mm targets, 25,920 trials. Median throughput: one thumb 4.52, two-hand index 5.87, two thumbs 7.18 bits/s; pairwise r=.62/.62/.58, p<.001. | Test grip/orientation as distinct conditions. Orientation and finger strategy vary with condition; this does not isolate a universal causal grip coefficient. Young right-handed lab sample, no walking or disability claim. Do not force adaptive layout shifts that harm learned positions. |
| [Bi, Li & Zhai 2013 FFitts](https://research.google/pubs/ffitts-law-modeling-finger-touch-with-fitts-law/), DOI `10.1145/2470654.2466180`; publisher/author abstract only | Three task experiments reported; R²>=.91 in the abstract. The linked full PDF was unavailable through the research tool. Sample sizes, uncertainty and detailed effect sizes were not verified here. | Reuse current FFitts implementation and its explicit calibration limits. Do not retune coefficients or claim independent replication from this abstract. Mark the missing methods as a research gap. |

Paper copies are read for analysis; they are not bundled. Original text, figures and code
have their own rights. This document stores concise paraphrases, numerical facts and URLs.

## Measurable acceptance gates (proposed, not measured claims)

PRD and safety constraints override an aggregate score. Record baseline and candidate
build/hash, PRD hash, persona revision, task, device/browser/version, viewport, zoom,
orientation, input/grip, starting data, cache state and observation time before comparison.

| Area | Gate and measurement | Stop / rejection |
| --- | --- | --- |
| PRD / intent | Every in-scope obligation has its existing criterion and current evidence; unrelated flows remain protected. | Missing evidence stays not_run; explicit scope exclusions do not turn into product completion. |
| UI identity | Baseline artifact hash + Figma node/version/readback; reviewed component/property allowlist; same-screen screenshots and bounding boxes. | Unreviewed global selector/import, layout movement or baseline drift blocks acceptance. No universal pixel tolerance is invented for all screens. |
| Accessibility | Existing target-size checks plus WCAG 2.2 SC 2.5.8 (24 CSS px or documented exception); keyboard focus/labels and contrast checks. | New critical violations or unavailable verification block acceptance. Physical target size is a separate calibrated measurement. |
| Selection dialog | Open focus, Tab/Shift-Tab containment, Escape/cancel, focus return, visible count/model/cost context; screen-reader labels. | No host render receipt means UI unverified. [WAI-ARIA modal guidance](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) supplies interaction requirements. |
| Runtime cost | Same-device interleaved baseline/candidate, warm-up separated, >=30 timed samples per path; report p50/p95, heap/RSS, artifact and bundle bytes. Proposed gate: no >5% p95/RSS growth and no new runtime dependency without an explained exception. | Unknown device/no samples cannot pass. 30 repetitions estimate device timing, not 30 independent users. Do not call this a population confidence interval. |
| Usability | Required task success must not regress. Measure errors, recovery, action count and duration separately for each condition. Human benefit needs a separately designed actual-human study. | Synthetic sessions/fixtures cannot establish prevalence, causal benefit or physiological capability. |
| Resource loop | Predeclare iteration/time/model-call/cost/frame/storage limits, original baseline and source versions. Cache only by all relevant hashes/conditions. | Stop on exhausted budget, stale evidence, uncertain send, access refusal, regression or repeated no-improvement; retain negative results. |
| Rollback | Preview binds exact state; dependent choices explicit; current content compared; restore only selected scope; invalidate prior acceptance and rerun existing replay. | Multiple changed files lack atomic publication support; block without writing. Concurrent unrelated edits must survive. |

## Follow-up experiments, without starting new workers

1. **Reach model:** compare current heuristic with the recovered quadratic model on a new,
   separately collected calibrated trace set. Report spatial error and false-safe targets,
   not only R²; do not train on frozen held-out defects. The current model stays default.
2. **Observed hand adapter:** pass hashed frames, timestamp, landmark method/version,
   occlusion and calibration uncertainty into existing snapshot metadata. Separate observed,
   model-estimated and unknown fields. A photo is not maximum range-of-motion evidence.
3. **Choice/dispatch:** exercise the actual host renderer, then verify selected IDs/revisions,
   Astra ultra route attestation and budget in the existing queue. A callback unit test is
   necessary but not evidence that the dialog rendered.
4. **CSS boundary:** consume the target compiler's AST/import graph and resolved styles;
   inspect shared tokens and global composition before accepting a component-only change.
5. **Atomic multi-file rollback:** use an existing host transaction/publication primitive if
   one is available and approved. Do not simulate atomicity with sequential file replacement.

Each experiment records source -> hypothesis -> predeclared criteria -> paired measurements
-> adopt/reject/hold -> existing regression replay. Missing host/data requirements remain
explicit blockers, not reasons to fabricate new observations.
