# Receipt starter and PE-2 validation

Base before this work: `328bc20`. The new receipt starter, PE-2 fixture and frozen
comparison inputs were committed locally in `37b9e89` before evaluator dispatch.
Post-trial changes fix bilingual README parity, add release-input stability checks
and document the results. Exact final aggregate outcomes, commands and source
hashes are in [the generated validation record](persona-pe2-tooling-20261111.json).
That result artifact is produced after the checks, not treated as an input to itself.

## Usable changes

`python3 skills/remorsearch-ux-qa/scripts/ux_personas.py receipt-starter --library LIBRARY --run RUN --claim CLAIM.json`

The host uses a private saved current claim to obtain exact task/build/persona/
worker/lease bindings and all success/recovery criteria. The returned schema is a
non-recordable draft: empty steps/artifacts, criteria not assessed, no pass or new
authority. The host supplies actual observations and evidence before recording.
Expired/mismatched claims and stale inputs remain blocked. The helper does not
assign work, renew leases, save expiry transitions or copy captures. Existing
private lock handling remains, including its normal permission normalization;
“read-only” describes logical state, not literally zero filesystem metadata work.

The actual PE-2 persona evaluator used six starters and submitted six accepted
receipts on the first attempt. This is observed workflow use, not a claim that
all authoring cost vanished. Preparation and helper writing still took work.

## Completed bounded comparison

[PE-2 evidence and interpretation](experiments/persona-workflow-pe2-20261111/README.md):
both conditions found the three seeded defects with zero false alarms on three
clean controls. All six cases were exercised under the frozen limits. Ordinary QA
used 60 attempts / 455.512 seconds; persona + plan QA used 37 / 321.832 seconds.
Different input/path coverage and unmeasured preparation prevent an efficiency or
superiority conclusion. The result is a small synthetic detection tie. It is not
an empirical-user study or a repair of incomplete PE-1 observations.

## Verification correction and prevention

The prior `328bc20` release check finished its unit stage before a late English
README change. It compared only the packaged skill source at the end, so it did
not catch the final README parity regression. The first PE-2 aggregate run found
three parity failures: 1,170 tests, three failures and one skip. Its browser checks
still passed 559/559, but the checker correctly returned `ready: false`, exit 1.
That failed run is preserved; no failed check is relabeled passed.

Both README languages now share headings and links. The focused packaging suite
passed 32 checks. A new `validation-inputs-stable` release check fingerprints
specified repository inputs before tests and after all checks. Added, removed,
changed or unreadable inputs make readiness false. It retains the existing skill
payload check and records relative paths/digests, never source contents.

Scope includes specified root README/PRD/license/configuration files and tests,
scripts, skill, integration, example, benchmark and documentation trees. It excludes
hidden/generated/dependency/virtual-environment/secret paths and the exact current
output subtree. An allowed output such as `docs/my-check` does not exclude sibling
documents or similarly named folders. External symlinks are not followed; unsafe
or oversized inputs fail validation. Git is not required. This is not a continuous
file monitor: changes restored between snapshots may evade it. Environment variables,
installed tools, external optional source inputs and unlisted root files are outside
this fingerprint scope. Final publication still requires checking the recorded input
hashes and identifying generated result artifacts added after validation.

Focused checks: 13 starter regressions, 13 new input-stability regressions, persona
subset 127, reading-budget 13, both launcher suites 10, extracted starter/diagnostics
21. Actual prototype execution and the two fresh evaluator runs used isolated
headless Chromium, never personal tabs/profiles. No dependency installation occurred.
Final complete-suite counts and exclusions are in the linked JSON, not inferred
from focused checks.

## Performance and boundaries

Five read-only starter calls over a real file-backed 128-task synthetic plan had
median 0.238016 seconds and maximum 0.240274 seconds; run-state bytes were unchanged.
This in-process measurement excludes Python startup/library acquisition and ran
alongside local release validation. It is not model cost, production UI latency or
a controlled speed comparison. Full-check process measurements are in the JSON.

The one usual Python skip requires ERGO_PAINT_CAPTURES. Real-browser handshake,
typography samples, real-user effectiveness and external research are not established
by package checks. DC permission, authorized YouTube API provenance/key and suitable
native study evidence remain missing. Existing original worktree files and Peekly
were preserved; no main merge, deployment, public visibility or installed-skill
change is part of this work.
