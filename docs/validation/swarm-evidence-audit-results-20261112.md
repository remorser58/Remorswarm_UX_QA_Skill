# Swarm evidence consistency audit — verification record

Date: 2026-11-12 KST. Branch: `rem/swarm-evidence-audit-20261112`.
Base: `rem/research-journey-20261112` at
`3074f5089e0fdd22db932709370211656c90b3eb` (parent verified before edits).
Acceptance criteria were fixed in [the protocol](swarm-evidence-audit-protocol-20261112.md)
before the red regression and implementation.

## Selected gap and reproduction

The prior local-run report returned per-task outcomes and validated each swarm
receipt, but it did not independently reopen the execution log against that
receipt or adjudicate repeated/contradictory observations for the same PRD
obligation across personas. The first new report regression failed on the
unimplemented `evidence_audit` field (`KeyError`), proving the reporting gap.

## Implementation

`uxpersonas.local_run._evidence_audit` is a read-only second-path verifier in the
existing report projection. It reopens each current execution log through the
existing safe file reader, checks size/digest/schema/attempt/operation/build/persona
binding and execution-log diagnostic shape/completion, and reconstructs the expected receipt
steps and criteria from the stored observation. A mismatch blocks the audit and
preserves the original task outcome and evidence; it does not repair or rerun.

For cross-persona comparison, the exact requirement ID, obligation ID, authored
description, criterion references and exclusion reason must all match. Same
observation fingerprints are reported as duplicates, not extra corroboration.
Passed/failed disagreement remains an unresolved conflict. An obligation-ID
collision with a different definition is shown separately and is not compared
as if it were the same test. Unobserved and `not_run` obligations remain
incomplete. Task receipts, historical attempts, dispatch counts and the original
persona Library are not rewritten.

This is deterministic receipt/evidence consistency checking, not an independent
human or model reviewer. It cannot establish that the reviewed adapter's
observation is true, that two synthetic personas are independent people, or that
the PRD mapping is semantically complete. No model/API or new dependency was added.

## Focused regression (original implementation)

| Suite | Result |
| --- | ---: |
| Journey local-run tests | 39 passed |
| Persona swarm tests | 29 passed |
| Receipt admission tests | 17 passed |
| Persona comparison tests | 21 passed |
| Persona replay tests | 37 passed |
| Research journey tests | 28 passed |

Five new test methods cover the initial missing audit, normal multi-persona
execution, identical repeated observations, contradictory pass/fail outcomes,
same obligation ID with different criterion mappings, and a tampered observation
whose artifact hash was updated to match but whose receipt was not. The last case
is blocked by the second-path audit rather than accepted because the artifact hash
alone matches.

## Full release and extracted execution

The preserved acceptance run is `release-final3`; it ran the release checker with
`--skip-web`. The Python suite reported **1,402 run / 1,401 passed / 1 existing
skip / 0 failures** (167.361 seconds in unittest; 167.83 seconds for that release
check). Release-file checks,
bundle build and integrity, extracted integrity, relocated runtime discovery,
research help, bundled search source/method, smoke and both extracted journey
diagnostics passed. The source release-file list contained 248 files; the package
manifest contains 250 payload files, excluding the manifest itself. Bundle and extracted
integrity checks passed. No dependency installation or browser launch occurred.
An intermediate full release attempt exposed the repository's English/Korean
README link-parity requirement. The corresponding Korean links were added and
the final release run was repeated; only the final run is the acceptance result.

Both extracted diagnostics included the new report field and Markdown section.
Each reused two saved synthetic personas and reported one known synthetic failure,
one inconclusive task and zero product passes. Both retained
`diagnostic_checks_passed=true`, `product_qa_passed=false`, `ui_observed=false`
and `real_user_evidence=false`. The research diagnostic used invented offline
research contracts, recorded `actual_public_acquisition=false`, and preserved its
original research bytes. These are package/runtime checks, not real research or
user acceptance.

`--skip-web` intentionally left `ready=false` and `published=false`; the single
non-passing check is the explicitly skipped web driver. No actual browser,
Chrome profile, user tab, public-source collection, service account or external
product was accessed or modified. No Codex CLI, API, model quota, keyboard or
clipboard interaction occurred.

## Historical Mac measurements

Recorded environment: macOS 27.2, 14 logical CPUs, 36 GiB RAM, Python 3.14.7.
The earlier `release-final` run took **174.04 seconds wall time**
(123.84 user / 22.54 system), with **160,923,648 bytes maximum RSS**.
The later accepted `release-final3` run took **174.81 seconds wall time**
(124.28 user / 22.84 system), with **155,254,784 bytes maximum RSS**.
Both measurements come from their preserved `/usr/bin/time -l` logs. Both ran
1,402 tests with 1 existing skip; their timings and log hashes must not be mixed.
The previously recorded free disk space was approximately 24 GiB.

## Safe handover on 2026-11-12

Before any write, observations at 02:41:01.834007 and 02:42:55.261025 UTC
(113.432 seconds apart) found the same branch/base/origin, exactly nine changes,
and identical file mtimes and SHA-256 digests. No non-inspection process with the
target worktree cwd/path, open changed file, or relevant Git lock was found.
A third observation at 02:47:59.840914 UTC also matched, including the later
release report and unit log. This is a point-in-time takeover check.

All 699 current validation inputs matched the preserved `release-final3`
snapshot before these documentation corrections. Runtime, regression tests,
PRD, READMEs, protocol and installable reference were preserved byte-for-byte.
Read-only review found no blocking defect in the supported local-run path.
The diagnostic audit validates the execution log's shape/completion; it does
not assert equality with the dispatch journal's entire diagnostic object.

Only the 39 journey tests were rerun for runtime regression: **39 passed,
0 skipped, 0 failures**, 6.026 seconds in unittest (6.234149 seconds wall).
Existing bundle/ZIP and extracted-tree verification also passed, with the same
250-file payload digest. Existing extracted reports were read and checked;
their journeys were not executed again. No new worktree, build, extraction,
dependency installation, or browser session was created.

The Markdown and JSON verification records are the only post-release source
changes. The historical full-release snapshot therefore does not describe their
corrected bytes; it still describes the unchanged runtime and package. Narrow
README checks also passed: **2 run / 2 passed / 0 skipped / 0 failures**.
MD/JSON counts, timings, historical log hashes, package hashes and source delta
were checked against the preserved files. Exact commands/log hashes are recorded
under `handover` in the JSON record and in
`.ux-loop/validation/swarm-evidence-audit-20261112/handover-20261112T024931Z`.
These checks remain synthetic receipt-consistency checks, not real-user,
browser, source-authenticity or product-effect validation.

The machine-readable check list, input stability and exact scope are in
[the JSON record](swarm-evidence-audit-verification.json). `ready=false` is a
deliberate limitation, not a failed or completed browser gate.
