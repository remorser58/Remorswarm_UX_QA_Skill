# Reviewed local journey execution — implementation and validation

Date: 2026-11-12 KST. Branch: `rem/journey-run-report-20261112`.
Base: `21681e17d83357736df448e93b94ba96b539f4bf`.
Prior Peekly ancestor: `0f623f1055b269249ea77ebec8493b2e203efa8f`.
The remote heads and ancestor relationship were verified before creating the
independent worktree. Original worktrees, persona libraries and experiments are
outside the edit scope. No Peekly product code or previous result was changed.

## Outcome and original gap

The installed `start/status` path prepared files and revalidated history but
could not execute a new reviewed task and join its current observations to a
report. The first regression prepared a fresh owned workspace successfully,
then expected the new `run` entry to return a failed/inconclusive current report.
It failed with `AssertionError: 2 != 1` and argparse `invalid choice: 'run'`.
The original failure is retained in the local `first-red.log`.

The implemented path connects the existing workspace, selected current Library
versions, swarm plan/claim/receipt validation, and immutable reports to actual
reviewed Python child execution. The host authors criteria from the user's goal
and reviewed PRD; the end user does not need internal CLI/JSON/lease knowledge.
No automatic persona generation, new package dependency, shell command transport,
browser/service adapter, model call or deployment was added.

An existing source-only preparation now supports `run`; later `start/status`
report current goals, persona versions, failed/unexecuted criteria, observations,
evidence links and next actions. Core-only results cannot pass the existing full
QA gate. The report explicitly keeps UI, real-user evidence and product readiness
false. See the installed [host contract](../../skills/remorsearch-ux-qa/references/persona-qa/local-run.md).

## Criteria and reuse

[The fixed protocol](journey-run-protocol-20261112.md) was written before the first
red test and implementation. Expected outcomes were not changed after observing
results. Existing workspace intake, Library citation/version/expiry validation,
swarm claims/receipts/quarantine/coverage, Store locking/atomic publication and
the Python stdlib are reused. The existing frozen Peekly harness was reviewed as
an execution/receipt example, not rerun or promoted as a general provider. No
additional orchestration SDK or dependency was needed.

## Actual owned sample observation

The packaged sample is a purpose-built small in-memory product with a known
defect: it clears earlier items before rejecting malformed input. Two authored
PRD hypotheses existed in the sample Library before `run` selected them. This
tests execution/evidence plumbing and defect reporting; it is not a newly found
Peekly defect or a measurement of persona/user effectiveness.

| Goal | Actual local observation | Task verdict |
| --- | --- | --- |
| Load the candidate | Candidate loaded into memory | Inconclusive: browser recovery unobserved |
| Keep earlier items after rejected input | Earlier item lost after malformed input was rejected | Failed: criterion and execution-log evidence linked |

Totals: failed **1**, inconclusive **1**, passed **0**. Both current persona
versions/fingerprints are reused. The core obligation counts include one passed
and one failed observation; two browser recovery obligations remain `not_run`.
No whole PRD requirement is marked passed. Source diagnostic repeats `run` and
`status` without another dispatch and checks original Library bytes unchanged.

## Failure history and recovery decisions

1. First red: missing installed `run` command; exit 1 from the failed test,
   underlying CLI exit 2. Mac elapsed 0.35 s, maximum RSS 40,861,696 bytes.
2. First implementation entry test: passed; 0.44 s, 41,041,920 bytes.
3. First expanded targeted run: 48 tests, 1 failure and 3 errors; 4.53 s,
   46,186,496 bytes. The Mac boundary refused `os.killpg` with `PermissionError:
   Operation not permitted`, causing timeout/cancellation cleanup failures.
   No permission or security setting was changed. Group signalling was removed;
   cleanup is now limited to this call's direct owned `Popen` child. Descendant
   and background workers are explicitly unsupported. Failure to confirm child
   exit keeps dispatch uncertain and prevents remaining work. The two PIDs
   reported as still running by the failed test were later absent in a scoped
   read-only check; no old/global PID was signalled.
4. That run's other error was a test construction error: an inline fake secret
   was correctly blocked during source intake before reaching the intended
   output guard. The fixture now constructs the synthetic marker at runtime so
   both intake and output boundaries remain independently tested. No guard was
   weakened.
5. Corrected targeted run: 48/48 passed, 4.64 s, 45,694,976 bytes. Expanded
   interruption/expiry/permission checks: 55/55 passed, 5.12 s, 45,088,768 bytes.
   Targeted suite after fixture reuse and shared-resource checks: 56/56
   passed, 5.14 s, 44,990,464 bytes. This is 32 new local-run tests plus the 24
   preserved journey-entry tests.
6. First full release run: 1,367 unit tests, one README link-parity failure and
   the unchanged capture-dependent skip. The English README linked the preserved
   Peekly results but the Korean README omitted the same page. The Korean entry
   was corrected; the parity test was not changed. Packaging, integrity and the
   extracted local journey diagnostic passed in that run. Whole invocation:
   178.47 s, 147,783,680 bytes maximum RSS. The failed validation directory and
   logs remain preserved; a new directory is required for the corrected run.
7. After README repair, the 32 packaging tests passed in 0.30 s with 29,753,344
   bytes maximum RSS. Second full release: 1,367 tests, no failures and the same
   one skip; 177.29 s, 157,204,480 bytes. Non-web release checks passed and the
   browser skip correctly kept `ready:false` and exit 1.
8. Final scope review reproduced a separate admission defect: an extra file
   added to the prepared product copy was ignored by selected-file hash checks.
   The owned probe failed with `Unreviewed added file in the copied product was
   admitted for execution` (0.29 s, 40,058,880 bytes). This demonstrated an input
   admission gap, not execution of that extra file or access to private data.
   The implementation now checks the copied tree's exact allowed names before
   and after execution, rejects extras/directory links without following or
   deleting them, and keeps fixture writes in private scratch. Two new
   regressions cover file and directory-link admission. Original sources are
   still not recursively scanned. The extracted diagnostic now uses the actual
   generated `remorsearch.py personas` launcher; source checks retain the direct
   CLI where that bundle-generated file does not exist.
9. Final boundary regression: 58/58 passed, 5.26 s, 45,318,144 bytes maximum RSS.
   The suite contains 34 new local-run tests and 24 unchanged entry tests.

Recovery coverage includes fixed criteria before dispatch, missing approval,
original/copied input changes, exact persona identity and expiry, refusal of
external PRD/research references before following them, output privacy and size,
wrong attempt binding, nonzero/empty output, timeout/cancel, private files,
first-time empty directory without permission rewrites, interrupted setup,
claim/journal gap, lost receipt acknowledgement, lease expiry, concurrent CLI
calls, unconfirmed cleanup and existing write-resource quarantine. No uncertain
dispatch is retried and no receipt/UI pass gate or skip threshold was relaxed.

## Measurement method and current validation record

Mac: macOS 27.2 (26B123), arm64, 14 logical CPUs, 38,654,705,664 bytes RAM,
Python 3.14.7. Initial load average 11.46 / 8.79 / 7.55; later observed
7.50 / 6.15 / 6.72. Heavy checks run serially. Concurrency regression uses two
owned CLI callers, each with serial bounded adapters. `/usr/bin/time -l` measures
elapsed time and macOS maximum resident set size in bytes for each invocation;
RSS is not a sum of all processes or an isolated-adapter peak. These synthetic
measurements do not establish real-user performance or production throughput.

| Check | Exit | Elapsed | Maximum RSS |
| --- | ---: | ---: | ---: |
| Final targeted journey regression (58 tests) | 0 | 5.26 s | 45,318,144 B |
| Source installed-style diagnostic before copy-scope hardening | 0 | 0.84 s | 39,993,344 B |
| Source loop smoke | 0 | 1.51 s | 31,080,448 B |
| Source research fixture | 0 | 0.56 s | 51,232,768 B |
| Final complete release invocation, existing `--skip-web` policy | 1 | 180.13 s | 155,205,632 B |
| Final extracted launcher diagnostic in a new path containing spaces | 0 | 1.13 s | 40,271,872 B |
| Extracted integrity after diagnostic execution | 0 | 0.08 s | 22,167,552 B |

Final release: `dist/journey-run-release-20261112-03/validation.json`.
The complete unit suite ran **1,369 tests: 1,368 passed, 0 failed, 1 unchanged
skip** (`ERGO_PAINT_CAPTURES` required by the pre-existing capture-dependent test).
Unittest reported 174.891 s; the release runner measured 175.47 s for that check.
All **14 non-web release checks passed**; the fifteenth check, `web-driver`, was
explicitly skipped because the user forbids browser execution. Release exit
remains **1**, `ready:false`, `published:false`. It is not a fully accepted web
release. No threshold, skip condition or existing receipt gate was relaxed.

The release builds and verifies the tree/ZIP, extracts it, exercises relocated
commands, reads the bundled upstream references, runs smoke workflows and the
new installed local journey diagnostic, and confirms current source equality
and unchanged validation inputs. The extracted local check took 1.10 s inside
the release runner. The independent measured diagnostic then used the generated
`scripts/remorsearch.py personas` launcher from a new owned path containing
spaces. Its real command exits were `start:0`, `run:1`, repeated `run:1`,
`status:0`; its original Library bytes were unchanged. These expected nonzero
run exits preserve failed/inconclusive QA instead of pretending the target passed.

The ZIP contains 4,209,432 bytes at
`dist/journey-run-release-20261112-03/bundle/remorsearch-ux-qa.zip`.
SHA-256: `c9444bf456453f90095839c0fb42040897e15d3f76c0c4be59d154de9442c80a`.
After execution, the extracted verifier reported `valid:true`, 248 shipped
files, no problems, payload SHA-256
`eaf2fb7050ef107eb8f7b21c4b1b10b3fb38ff03efad9acbf8316c932e3be581`.

The [machine-readable record](journey-run-results-20261112.json) includes all
measurement log digests, the observed goal/criterion/evidence bindings, package
digest, release checks and validated source/test/reference file hashes. Raw logs
and the actual owned diagnostic reports remain under
`.ux-loop/validation/journey-run/`; they are not uploaded as user data. The MD/JSON
measurement record is finalized after checks. Executable, test and installable
reference/package bytes have not changed since final validation; their explicit
hashes avoid pretending that the result document existed before its measurements.

## Preservation and delivery scope

Before/after comparison matched the four existing in-root worktrees' HEAD,
porcelain status, all **2,598 tracked file contents**, and nonignored untracked
file inventories. The **17 captured Library/swarm/workspace state files** also
matched. Ten linked worktrees outside the approved repository root were only
seen in Git registration metadata and were not inspected or changed. The initial
process inventory included inspection subprocesses; it is not presented as a
claim that all those PIDs were persistent product workers. Only newly owned test
children were signalled. No other product process, account, global Library,
installed skill, permission setting or repository was modified.

Origin heads were rechecked before delivery: the requested journey-entry base
remained `21681e17d83357736df448e93b94ba96b539f4bf` and the Peekly ancestor branch
remained `0f623f1055b269249ea77ebec8493b2e203efa8f`; the new branch did not already
exist remotely. This work is delivered on `rem/journey-run-report-20261112` by
explicit-file commit and ordinary push, with its exact commit/remote match in
the final handoff. No force push, merge, PR-triggered browser job or deployment
is part of this work. Release `published:false` describes package publication,
separately from the authorized Git branch push.

## Boundaries retained

- Actual browser/UI, actual users, service acceptance, human usability and UX
  benefit remain unverified. No Chrome, existing tabs, screen/input/clipboard,
  real account, paid model/API or Codex execution was used.
- Python 3.14.7 on this Mac was executed. Other supported Python versions and
  operating systems were not executed here; no remote CI result is claimed.
- Only explicitly reviewed single Python adapters are supported. The host must
  assess their behavior and imports. No arbitrary repository code autoexecutes;
  this is not an OS/network sandbox or a universal personal-data detector.
- Only current PRD-hypothesis profiles with in-scope PRD are admitted by this
  adapter. Research-bound personas retain their separate current gate workflow.
- Original source/Library must remain available and unchanged for current
  validation. A changed or expired binding blocks reuse; saved evidence is kept.
- Hard interruption can leave unknown work. It never grants replay; actual
  process/effects inspection is required. No saved PID is killed on return.
- The user forbids browser execution. The existing `--skip-web` release path
  must remain non-ready with nonzero exit; no browser test is claimed.
- Previous Peekly evidence remains failed 1 / inconclusive 4 / passed 0, without
  being rerun or presented as actual UI/user evidence.
