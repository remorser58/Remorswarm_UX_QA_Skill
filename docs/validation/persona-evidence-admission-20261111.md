# Persona evidence admission — 2026-11-11

## Scope and decision

Baseline: `rem/persona-journey-comparison-20261111`,
`30e029ada0da2c65ba54722b08838410e4c8a0f2`. The remote branch was checked with
`git ls-remote` and fetched before creating the independent
`rem/persona-evidence-boundary-20261111` branch.

The blocker was in Remorsearch's research-to-persona admission, not a defect in
a QA target product. A process-level passing research gate could supply a
persona card with no usable motivation. That card could be persisted and later
drive task assignments and reported results. Improving this boundary protects
the basis of later behavioral QA while retaining ordinary exploratory testing.

Relevant requirements: [PRD sections 6 and 9](../../PRD.md) and the existing
[claim-correction contract](../../skills/remorsearch-ux-qa/references/research/audience-pipeline.md).
The latter already required removing unsupported support/context links while
keeping contrary evidence and making the old claim non-exportable.

No public-service research was needed to reproduce this local defect. All new
research inputs, profiles, builds, screenshots and task receipts are owned,
invented fixtures. The fixture's local gate uses the existing live input
contract; that label does **not** mean a public source or real participant was
investigated.

## Reproduced failure

Before changing product code, the new regression file ran five test methods
and produced nine failed assertions, including subtests:

| Input | Baseline behavior |
| --- | --- |
| Counter evidence only; counting/context lists empty | Actual merge and gate passed; claim status was `conflicting`; CLI import exited 0 and saved revision 1 |
| Same evidence ID in counter and support/context | Card remained `exportable: true` |
| Support or context marked `inferred` / `unknown` | Actual CLI import exited 0 and saved the profile |
| Valid support mixed with grade-E material | Aggregate `supported_high` allowed a card containing the unfit dependency |
| Explicit synthetic context | Card remained exportable |

The counter-only error arose because `claim_cards` counted the union of
support, context and counter references as “evidence present.” Aggregate status
also failed to reject unfit contributions in a mixed claim. Explicit context
does not pass through every support-grading operation, so the consumer needs
the existing source-type, observation and exact-capture review boundaries too.

The pre-fix command was:

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -lp /opt/homebrew/bin/python3.14 \
  -m unittest discover -s tests -p 'test_persona_evidence_admission.py' -v
```

Observed: exit 1, five methods / nine assertion failures, 0.90 s elapsed,
47,939,584 bytes maximum RSS. No assertion was weakened and no new skip or
expected failure was added.

## Product change

[The shared card consumer](../../skills/remorsearch-ux-qa/uxresearch/personas.py)
now requires current gate counting/context evidence after removing counter IDs.
A counter cannot supply that basis merely by appearing in both roles. Counters,
source dependencies and their conflicting status remain preserved.

The consumer rejects non-observed motivation evidence, explicit
`synthetic`/`llm_output` sources, `source_family: none`, grade-E contributions,
and unresolved or confirmed virtual-person captures. Existing injection,
privacy, access-stop and withdrawal checks remain in force. Blocked cards
contain only identifiers, status and a reason, not source prose.

Virtual-person reviews must match the target and exact capture. The actual
merge path copies source flags into evidence: a valid source review covers
only those inherited flags. Additional excerpt flags still require their own
review, and a confirmed virtual-person decision remains a rejection. A newly
introduced over-rejection of inherited flags was caught by a failing regression
and fixed without relaxing its expected result.

[The persistent library](../../skills/remorsearch-ux-qa/uxpersonas/library.py)
continues to use the same gate/card consumer at import and every revalidation.
It returns `unsafe_motivation` with a concrete review/re-authoring next step.
No state schema or binding shape was changed.

Consequently, existing hash-valid profiles and previous passing fixture
receipts cannot bypass the new boundary through restart, reuse, plan, claim,
record, retry, report or compare. These were exercised through fresh CLI
processes. The historical fixtures serialize the former accepted contract;
they are not modifications of any existing user library.

Safe observed context, single-voice/lead-only exploratory material, and safe
support with distinct contrary evidence remain usable with their exact
uncertainty. `prd_hypothesis` remains available without claiming research
support. Identical valid imports retain their revision and fingerprint.

Admission failure alone neither deletes a profile nor authorizes cleanup.
Confirmed capture withdrawal still permits the existing prune operation;
pending/uncommitted withdrawal remains blocked without deleting the payload.
The compare and capture-retention implementations were not modified.

## Verification

Final executable code, skill instructions and regression inputs were fixed
before the final release check. This validation note was added afterward.
A final input-fingerprint comparison found only this note as an added input;
there were no removed or changed tested inputs. The shipped payload matched
the archived manifest exactly, and the ZIP retained the recorded SHA-256.

| Check | Result |
| --- | --- |
| Entire Python suite | 1,232 tests; 1,231 passed, 1 existing skip, 0 failures |
| New admission regression file | 18 tests passed, including restart, concurrency, permissions, contamination and retention boundaries |
| Extracted-package CLI: new admission + existing comparison suites | 39 passed, 0 failures |
| Release-file policy, bundle construction, tree/ZIP integrity, relocated runtime/help/reference reads, both offline smoke workflows | Passed |
| Shipped source match and inputs stable during final release check | Passed |
| Browser-driver execution | Intentionally skipped; release checker returns exit 1 and `ready: false` |

The existing Python skip is the real painted-state capture check requiring
`ERGO_PAINT_CAPTURES`. It was not supplied or synthesized to obtain a pass.
No user's browser, screen, tabs, keyboard or clipboard was accessed.

The first full check found four subtest failures because the new SKILL wording
exceeded an initial reading closure by 38 bytes. The text was shortened, the
13 reading-budget tests passed, and the entire final check was rerun.
Reading limits and existing test expectations were left unchanged.

Final release command:

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -lp /opt/homebrew/bin/python3.14 \
  scripts/check_release.py \
  --output dist/persona-evidence-admission-release-final-20261111 --skip-web
```

Extracted-package functional command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests \
REMORSEARCH_PERSONA_TEST_ENTRYPOINT="$PWD/dist/persona-evidence-admission-release-final-20261111/extracted/remorsearch-ux-qa/scripts/remorsearch.py" \
/usr/bin/time -lp /opt/homebrew/bin/python3.14 -m unittest \
  test_persona_evidence_admission test_persona_comparison
```

The 39-test run includes the actual multi-persona CLI path:
owned input → real merge/gate → persistent import → new-process reuse →
task plan/claim → fixture receipt → report → paired comparison.
Its recorded QA receipts are invented; their acceptance does not establish that
a real product was exercised or users benefited.

### Measurements

Machine: Apple M4 Max, 14 physical cores, 36 GiB RAM; macOS 27.2;
Python 3.14.7. Elapsed time and maximum RSS come from actual commands,
not estimates. RSS is the maximum reported by `/usr/bin/time -lp`, not the
sum of simultaneously resident processes.

| Command / phase | Elapsed | Maximum RSS |
| --- | ---: | ---: |
| Final whole release check, including entire regression and packaging | 73.04 s | 155,746,304 bytes (148.53 MiB) |
| Python suite within that check | 69.72 s stage time; unittest reported 69.211 s | Not measured separately |
| Bundle construction within that check | 0.19 s | Not measured separately |
| Extracted offline smoke workflows | 2.04 s | Not measured separately |
| Extracted-package admission + comparison suites, 39 tests | 17.21 s | 48,955,392 bytes (46.69 MiB) |

These small fixtures are a validation cost measurement, not production
throughput, public research latency or user time saved.

Bundle: 239 manifest payload files, 4,063,660-byte ZIP,
SHA-256 `ea32e2995715ddd35a816a0c34c114b71e18d0eded4f3c3425227c398dca9627`.
The archive, extracted tree and raw logs stay in ignored `dist/`; they are not
committed or installed. Logs are under
`dist/persona-evidence-admission-release-final-20261111/logs/`, including
`unit-tests.log` and `persona-relocated-e2e.log`.

## Preservation and publication boundary

Eight preexisting worktrees were fingerprinted before implementation, covering
5,102 tracked/nonignored files, branch/HEAD and dirty status. Two existing
Remorsearch-related Node processes were observed at roughly 41 hours old and
0.0% CPU. No preexisting work, process, ledger, branch or data was resumed,
stopped, overwritten or removed. The managed work had no open operation or
pending command at preflight.

The pre-commit recheck matched all eight original worktrees' file fingerprints,
file counts, HEADs, branches and dirty status. The same two processes remained
present at 0.0% CPU. The managed work remained at revision 29 with unchanged
update time, no open operations and no pending commands. The baseline remote
branch still resolved to the starting commit; the new branch did not yet exist.
The explicit eight-file publication set contained no credential-pattern matches;
this bounded scan supplements review and is not a general secret detector.

Only reviewed code, the new independent regression file, PRD/skill guidance and
this note belong in the commit. No validation archive, raw research, user data,
credentials, installed skill or security setting belongs in the publication.
The existing approved origin receives a normal new-branch push; no force push
or update of the baseline branch is required.

## Remaining limits

- The declared `observed` status and source metadata are not independent proof
  of authenticity. A fabricated but falsely labelled source still needs host
  review; hashes and these checks cannot establish truth.
- Claim-to-PRD fit and the semantic quality/diversity of authored personas
  remain host review responsibilities.
- Actual community/YouTube acquisition, current service access and real target
  interaction were not performed. No real-user prevalence, preference or UX
  benefit was measured.
- The swarm remains host-driven. This change does not launch workers or add
  continuous collection, automatic source monitoring or browser execution.
- Old installed versions retain their old admission behavior. Continue stored
  runs with the updated skill; installation was not performed in this task.
- Independently exported copies still need their own retention review.
  The release remains partial until the permitted real browser checks and
  separately scoped product/user validation are performed.
