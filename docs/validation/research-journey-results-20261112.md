# Reviewed research personas → current QA run and report

Date: 2026-11-12 KST. Branch: `rem/research-journey-20261112`.
Base: `d34a69fe706fcc68f637bcafdbbd71c6f80ab87a`.
The remote head and ancestry through `21681e1` and `0f623f1` were checked
before creating this separate worktree.

## Implemented path and actual limits

The existing installed local run rejected every research-backed saved persona.
It now accepts only exact host-reviewed research directories, reuses the current
Library revisions and existing research gate/retention/motivation/projection
checks, runs the same reviewed local adapter and links research provenance to
the current task report. Ordinary users provide product/goals; the host handles
reviewed paths, mappings and the internal commands. No persona is automatically
invented, downgraded or imported by run.

This completes this bounded code connection, not the whole QA product or an
actual-user study. No UI, browser/WebDriver, real account, model call, OS setup,
permission change, deployment, or external-product edit occurred.
The host displaying this conversation does not determine the executor machine.

## Reuse and root cause

The earlier public-evidence pilot and its research intake were read as historical
analysis. Its real collection, source dates, lead-only context and access stops
are not new evidence for this change; its original private runs were not opened.
The existing native-input builder, merge/gate, export/import, versioned Library,
swarm claims/receipts, owned subprocess executor and immutable report were reused.
No new dependency or copied third-party code was added; existing licenses and
pinned search toolkit remain unchanged.

Simply removing the PRD-only refusal was unsafe: the ordinary research reader's
constructor purges expired page caches, and ordinary Store opens/normalizes locks.
The new scoped inspection view keeps existing policy/gate checks but uses only
existing read-only shared locks and suppresses cache cleanup. It cannot publish,
collect or delete. It never copies raw captures, excerpts or a research tree into
the execution workspace. Only fixed bounded metadata and committed gate inputs
are read after the explicit scope check. This is cooperative local validation,
not an OS sandbox or a guarantee against malicious concurrent filesystem edits.

Scopes and exact selected personas are durable before dispatch. Research is
revalidated at admission, immediately before spawn, after the owned process and
during receipt/report/readback. A changed or withdrawn source blocks use; a
change during execution can leave the original attempt uncertain, never retried.
The original Library/research and prior reports remain intact. Confirmed
withdrawal does not authorize automatic pruning of these original records.

## Fixed criteria and failures

The [protocol](research-journey-protocol-20261112.md) preceded all new tests and
product edits. SHA-256:
`5fec197366a4f247e3d59e5210e478972a5b316156aa829172fb803e59434dea`.

1. The first new test used the shell's Python 3.9.6; the installed entry correctly
   refused it with “Python 3.10 or newer is required.” This is an environment
   failure, not the target product defect. Its log remains `first-red.log`.
   Existing `/opt/homebrew/bin/python3` was then verified as 3.14.7 and used
   explicitly. No runtime was installed or configured.
2. The supported-runtime feature red failed with argparse rejecting
   `--reviewed-research-run`, exit 2. A separate actual base CLI call without the
   new option returned `persona_scope` for otherwise valid saved gated-research
   personas. Both failures are preserved. New test expected a failed/inconclusive
   report from actual execution, not a task pass.
3. First implementation entry passed. The first expanded related run passed
   144 tests, including original entry/run/Library/intake/evidence admission
   regressions. Existing assertions and skip markers were not relaxed.
4. The first source diagnostic output named a child of a nonexistent `.ux-loop`
   parent. The existing new-directory builder refused it with FileNotFoundError;
   no source run occurred. The failed log is preserved. A new diagnostic path
   under the existing owned audit parent then completed. The output guard was
   unchanged.
5. The first full release run executed 1,397 Python tests and reported five
   reading-budget assertion failures plus one existing capture-dependent skip.
   The edited SKILL.md was 8,271 bytes (limit 8,192); four initial-reading
   combinations were 42,123 bytes (limit 42,000). Package checks and both
   extracted journey diagnostics passed. The limits, required references and
   tests stayed unchanged. Redundant router wording was shortened; detailed
   research-reuse instructions remain in local-run.md section 6. The failed
   release-01 artifacts are preserved, and the final run uses a new directory.

## Observed owned diagnostic

The shipped known-defect product clears earlier in-memory items before rejecting
malformed input. This is an authored diagnostic, not a new product discovery.
The new variant uses the shipped invented native-input contract and actual
merge → gate → authored export → Library import → current run → status.

| Goal | Actual owned observation | Task result |
| --- | --- | --- |
| Load a candidate | Candidate loaded into memory | Inconclusive; browser recovery not observed |
| Preserve earlier items after invalid input | Earlier item lost after input was rejected | Failed; criterion and execution-log evidence linked |

Counts remain failed 1 / inconclusive 1 / passed 0. Both exact current profile
versions are reused; structured scenario/export fingerprints remain linked.
Readback does not dispatch again. Original research and Library contents, modes
and modification times are checked. Sparse-context regression retains lead_only
and zero counting evidence; research provenance never becomes a product result.

The diagnostic's live-mode contract fields exercise existing validators on
**invented offline input**, not real public acquisition, observed participants,
source authenticity or prevalence. The diagnostic receipt separately sets
`research_contract: invented_offline_input`, `actual_public_acquisition: false`,
`product_qa_passed: false`, `ui_observed: false` and `real_user_evidence: false`.

## Verification record

All measurements below are actual Mac `/usr/bin/time -l` receipts, with maximum
RSS in bytes; RSS is not a sum of the whole process tree. Executor: macOS 27.2
(26B123), Darwin arm64, 14 logical CPUs, 38,654,705,664 bytes RAM; Python 3.14.7
at the existing `/opt/homebrew/bin/python3`. CPU load and VM were inspected;
heavy checks ran serially, with only the two owned callers in the concurrency
test running together. The measurement wrapper kept temporary inputs inside the
new task's audit directory. No machine model is inferred from the conversation UI.

| Check / preserved log | Observed result | Elapsed seconds | Maximum RSS bytes |
| --- | --- | ---: | ---: |
| first-red | 1 failed test; unsupported system Python | 0.40 | 37,191,680 |
| first-feature-red | 1 failed test; reviewed option missing | 0.45 | 47,857,664 |
| baseline-scope-rejection | Probe confirmed actual CLI `persona_scope`, exit 2 | 0.45 | 48,988,160 |
| first-green | 1 passed | 1.49 | 48,480,256 |
| targeted-01 | 144 passed | 57.87 | 51,150,848 |
| source-diagnostic | Failed before execution: output parent absent | 0.11 | 39,223,296 |
| source-diagnostic-02 | Structured research diagnostic passed; product pass 0 | 2.59 | 44,630,016 |
| targeted-final | 182 passed, including all 28 new regressions | 22.17 | 51,773,440 |
| reading-budget-fixed | 13 passed; unchanged size limits | 0.20 | 40,550,400 |
| release-01 | 1,397 tests; five reading-budget failures, one existing skip | 180.40 | 161,333,248 |
| release-02 | 1,396 passed / 1 existing skip; package and extraction passed | 176.39 | 158,121,984 |

The final unit run reports `Ran 1397 tests in 169.105s`, `OK (skipped=1)`.
The existing skip is
`test_ergo_painted_state.ActualPaintCaptures.test_frozen_browser_captures_feed_real_checks`:
no actual browser capture input was supplied. No original assertion, skip,
reading budget or quality gate was weakened. SKILL.md is now 8,089 bytes and the
previously failing initial reading combination is 41,941 bytes.

The 28 added regressions exercise actual CLI dispatch and reports, exact root
approval, bounds/links/permissions, current/failed/stale gates, source withdrawal
and expiry, original cache/Library preservation, interrupted preparation, lost
acknowledgement, scope changes, two concurrent CLI callers, mixed provenance,
lead-only context and structured export/import. Withdrawal before spawn prevents
dispatch; withdrawal during execution retains an uncertain attempt without replay.

`dist/research-journey-release-02/validation.json` contains 15 passed checks and
one skipped `web-driver` check. Release remains **`ready: false`, exit 1**,
`published: false`; browser authorization was absent. Both extracted diagnostics
used the generated `scripts/remorsearch.py`, starting from empty workspaces and
executing `start → run → repeated run → status` with exit codes `0, 1, 1, 0`.
The PRD diagnostic took 0.98 seconds and the research diagnostic 2.81 seconds
inside the release runner. Each reused two personas and retained product failed 1 /
inconclusive 1 / passed 0. These inner times are not separate RSS measurements.

The verified ZIP is 4,234,156 bytes, SHA-256
`1f9f5254b7b3bc4d2f34692db64c864fdba1836a93aea0525bab5436232cf66d`.
Its research diagnostic reports `original_research_unchanged: true` and
`original_library_unchanged: true`. Exact log/artifact hashes, measured results
and scope flags are in [the companion JSON](research-journey-results-20261112.json).

The measured release's input snapshot remained stable throughout execution.
Only this results MD and its companion JSON are finalized afterward. Before
commit, the final review compares all other source/test/skill bytes with that
snapshot and verifies the existing tree/ZIP/extraction against current packaged
inputs. Its separate `final-review.json` receipt does not rewrite the measured
release report or turn its browser gap into readiness.

## Preservation and delivery

The five original worktrees within the approved root retained the same HEAD,
status and all 3,295 tracked/nonignored files (content, mode, size and inventory).
All 15 original worktree registrations were retained; external registered
worktrees were not entered. No existing process was signalled or restarted.
The first preservation-helper invocation stopped before scanning at its own
scope guard because a relative helper path was not normalized. Normalizing that
owned helper path fixed the audit; the scope guard was retained. This was not a
product test failure or a permission-boundary bypass.

The new branch is a direct child of the verified cumulative base. Only reviewed
source, regression and documentation files are staged; generated logs, ZIPs,
synthetic research state and private execution workspaces remain untracked audit
artifacts outside the commit. Normal push, independent remote SHA equality,
clean status and a post-delivery preservation check are recorded separately in
`git-delivery.json` and `after-delivery-preservation.json` after delivery.

## Reproduction and evidence

Use an already installed Python 3.10+ and a new output directory each time.

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3 -m unittest discover -s tests -p 'test_*.py'
/opt/homebrew/bin/python3 scripts/check_release.py --skip-web --output dist/NEW_RELEASE_CHECK
/opt/homebrew/bin/python3 skills/remorsearch-ux-qa/examples/journey/run_fixture.py --research --out NEW_OWNED_OUTPUT
```

The normal host workflow is documented in
[local-run.md](../../skills/remorsearch-ux-qa/references/persona-qa/local-run.md#6-reuse-reviewed-research-in-the-same-run).
Users are not expected to run these commands. Validation logs and the Mac
measurement helper are retained in the task's separate audit parent, outside
the committed source worktree. Final commit/push/remote SHA/clean results are
recorded in its separate `git-delivery.json` after delivery.

## Unverified boundaries

- Actual public source authenticity, new public collection, remote source
  withdrawal detection, goal/persona semantic fit and general-user effectiveness.
- Browser UI, WebDriver, actual installed host-skill model behavior, Figma,
  accessibility acceptance or full-product readiness.
- Arbitrary adapters, descendants/background workers, network/account work,
  credential/permission setup or OS sandbox guarantees.
- Existing original research files and external registered worktrees were not
  entered. Local preservation checks cover the approved repository worktrees'
  tracked and nonignored files, not every ignored artifact on the host.
