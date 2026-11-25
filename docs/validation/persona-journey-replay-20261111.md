# Next-build journey replay — 2026-11-11

## Scope and reproduced product gap

Base: `rem/persona-evidence-boundary-20261111`,
`991c9db2c6dd551099850193931194a5727e8690`.
Independent branch: `rem/persona-journey-replay-20261111`.

The existing persistent library, evidence admission, retention protection,
receipt starter and paired comparison were retained. The missing connection was
preparing the next build's run from an already reviewed, observed journey.
Previously the host had to author another complete swarm-input JSON document,
restating persona IDs, actions, decisions, criteria, PRD coverage and limits.
The comparator correctly rejects unintended differences in those fields.

The new CLI end-to-end test first imported two personas bound to an owned
research fixture and recorded the baseline through the existing CLI. Before
implementation, the next `replay` command failed with argparse
`invalid choice: 'replay'` and exit 2. The test runner reported one failure in
1.736 seconds. The failure was the missing product command after valid baseline
preparation, not a browser or target-product defect.

All research material, personas, build bytes, observations and PNGs in this
verification are invented owned fixtures. The research gate/storage code and
CLI run for real, but no DC Inside/YouTube collection, account, browser or human
participant was used. Passing these fixtures does not establish actual product
execution, source authenticity, real needs, causal UX improvement or launch
readiness.

## Implemented user flow

From the skill directory:

```sh
python3 scripts/ux_personas.py replay --library LIBRARY --baseline BEFORE_RUN --run AFTER_RUN --build-id build-2 --artifact build-2.bin --isolation-id fixture-v2 --confirm-starting-state --confirm-isolation
```

Packaged entry point: `python3 scripts/remorsearch.py personas replay ...`.
Add `--format json` for integrations.

The host supplies the existing baseline and new build, rather than a second
authored task matrix. The readable response supplies the fixture assignment and
runnable claim, receipt-starter, record, report and original-baseline comparison
commands. The test actually parses and executes the printed claim command.
Claim/receipt filenames are placeholders and must be stored privately.

The feature:

- Revalidates the current exact persona/PRD/research bindings, retention and
  capture eligibility, both build artifacts and baseline receipt evidence.
- Requires a validated passed or failed observation for every baseline task.
  It refuses active, unobserved, uncertain or settled-inconclusive work without
  changing that work or its retry budget.
- Preserves exact journeys, task IDs, criteria, PRD obligation mapping, persona
  versions and limits. It preserves shared-resource grouping while generating
  fresh namespace/resource identifiers.
- Starts the new run pending, with zero attempts and no history. Prior receipt,
  lease, operation, result, settlement or grant is not copied.
- Saves replay provenance in the first state write and returns it after restart
  through claim/report/compare. Comparison refuses another baseline path or a
  changed original snapshot.
- Uses a private library reservation index and the existing Library lock so a
  baseline/candidate-content pair has one destination. Changing names or fixture
  aliases does not mint another replay budget. Exact retries return the current
  existing run without expiring its leases or resetting attempts.
- Resumes a reservation-only interruption at the same still-absent destination.
  If creation left a partial directory, it preserves that directory and stops.

The origin is audit provenance, not new execution authority. The existing v3
state execution/settlement contract remains; old readers do not enforce the new
replay preparation/paired-provenance contract. Use the current revision for
replay and comparison.

## Verification and measurements

Runtime: installed Homebrew Python 3.14 on the approved Mac.
No package installation or dependency update was performed.
Use an explicit supported interpreter: this machine's non-login bare
`python3` selects Xcode Python 3.9.6 and correctly fails the existing 3.10+
entrypoint requirement. That initial runtime selection was corrected without
changing the tests or product runtime requirement.

Measurements below are individual command runs, not statistical benchmarks or
user time-savings estimates. RSS is the macOS `/usr/bin/time -l` reported maximum
resident set size in bytes, not total memory summed across concurrent workers.

| Check | Observed result | Wall time | Maximum RSS |
| --- | --- | ---: | ---: |
| Initial independent replay suite | 35 tests passed; unittest 40.136 s | 40.36 s | 45,875,200 bytes |
| Added withdrawal/review-due and strengthened hypothesis-mode cases | 3 affected tests passed; final replay file has 37 tests | 3.99 s | 46,120,960 bytes |
| Existing paired-comparison regression | 21 tests passed; unittest 8.461 s | 8.65 s | 46,579,712 bytes |
| Offline loop smoke | 18 expected command outcomes; passed | 1.52 s | 31,129,600 bytes |
| Offline research fixture | Passed; reported zero network requests | 0.51 s | 51,806,208 bytes |
| Actual replay CLI, two gated fixture personas | Prepared two pending tasks; exit 0 | 0.279050 s | 41,254,912 bytes |
| Identical replay CLI after process restart | Existing run; still two pending tasks; exit 0 | 0.291922 s | 40,910,848 bytes |
| Full repository regression after reading-budget fix | 1,269 tests: 1,268 passed, one pre-existing real-capture condition skipped; unittest 120.938 s | 121.48 s checker step | Included in release RSS below |
| Full local release checker, browser excluded | 13 executed checks passed; only web-driver skipped; ready false, exit 1 | 124.86 s | 156,991,488 bytes |
| Extracted bundle replay + comparison regression | 58 passed (37 replay + 21 comparison), zero skipped; unittest 66.016 s | 66.23 s | 45,842,432 bytes |

The extracted check confirmed all 27 loaded product modules came from the
extracted bundle and used its actual launcher, including the printed next-step
claim. The original `ERGO_PAINT_CAPTURES`-conditioned test was the repository
suite's one skip; no skip or xfail was added. The release run checked source
stability, current bundle inputs and both bundle/extracted inventories.

These recorded full-run measurements precede this final report update. A new
commit-candidate release check uses the final report as a frozen input; the
prior output remains at `dist/persona-journey-replay-final-20261111`. No product
code changed between those checks. Its local ZIP SHA-256 was
`53d25626ef2a782594bf09c262a05769d0eb7df77e4f7fdad249a45736e941b2`
(4,088,511 bytes). The archive and generated logs are excluded from commit.

The replay CLI rows use `time.perf_counter()` around the actual
`/usr/bin/time -l python ... replay` subprocess. The tool's rounded `real`
values were 0.27 and 0.28 seconds. Baseline fixture creation is outside those two
measurements. An earlier probe completed both CLI operations but used an
incorrect test-helper cleanup attribute; it was corrected and rerun to exit 0.
This was a measurement-harness error, not a product pass or failure.

The regression file `tests/test_persona_replay.py` covers the complete two-persona
CLI path, new evidence requirements, provenance mode preservation, shared
resource serialization, incomplete comparison before execution, both observed
outcome directions after recording, wrong/changed baseline, restart,
expired-lease nonmutation, changed/superseded/retired/expired dependencies,
capture withdrawal, permissions, symlinks, concurrent duplicate preparation and
interrupted publication. Negative cases assert rejection and preservation;
none are marked xfail or weakened to accept missing behavior. Existing evidence
admission and capture-retention tests remain part of the repository suite.

The first full release check ran 1,269 tests and exposed five reading-budget
assertions: the added always-loaded skill paragraph made SKILL.md 8,477 bytes
(limit 8,192) and one first-read closure 42,329 bytes (limit 42,000). The long
paragraph was reduced to a short replay pointer; the complete instructions stay
in the lookup-only persona reference. The test limits were not changed. That
initial failed release output is retained separately from the final rerun.
The unchanged reading-budget suite then passed all 13 tests (0.25 seconds wall,
41,123,840 bytes maximum RSS).

### Reproduce full regression and package checks

Run from the repository checkout with Python 3.10+:

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -l /opt/homebrew/bin/python3.14 scripts/check_release.py --skip-web --output dist/persona-journey-replay-commit-20261111
```

The checker runs the full repository unittest suite, release-file checks, bundle
build/inventory verification, extraction verification, relocated runtime/help/
reference reads and offline smoke tests. It records each result and a stable
source-input fingerprint in the new output directory's `validation.json` and
logs. The output directory must be new; existing results are not overwritten.

The user's no-screen/no-Chrome instruction excludes the web-driver self-test.
Accordingly `--skip-web` deliberately leaves `ready: false` and exits 1 even
when every executed check passes. This result must not be called complete
browser release validation. The bundle is a local validation artifact, not an
installed/published skill or a deployment.

For the extra extracted-persona check, select the extracted
`scripts/remorsearch.py` through `REMORSEARCH_PERSONA_TEST_ENTRYPOINT`, replace
the test runtime import paths with the extracted skill paths before loading the
tests, and run `test_persona_replay` plus `test_persona_comparison`. Verify that
`uxpersonas` modules resolve inside the extracted tree. This exercises the
packaged CLI, printed next-step command, storage and API fault cases instead of
silently using the checkout's implementation.

## Remaining limits

- The initial PRD-to-research-to-reviewed-profile/task authoring still needs the
  host. This feature carries an already validated journey forward; it does not
  invent researched personas or autonomously create the initial plan.
- Actual source collection, honest task observations, independently verified
  source truth, real browser/device execution and user benefit were not tested.
  PRD hypotheses stay hypotheses; gated personas stay synthetic.
- Starting-state equivalence and fixture isolation are host attestations. IDs
  neither create fixtures nor prove actual resource separation/deployment.
- Baseline build/evidence artifacts and current authoritative source state must
  remain available. A changed or missing baseline blocks preparation/comparison.
- Partial directory recovery is manual and fail-closed. The new command does not
  delete, reset, settle or inspect uncertain execution on the host's behalf.
- Duplicate prevention is local to this library and replay path. It does not
  control manually authored plans, copied libraries or external workers.
- No actual screen/Chrome/tab/input/clipboard, Codex CLI/API/native/model quota,
  Figma, account login, permission expansion or unrelated project operation is
  part of this validation. Existing worktrees, processes and work ledger remain
  outside the change; generated test/bundle artifacts are excluded from commit.
