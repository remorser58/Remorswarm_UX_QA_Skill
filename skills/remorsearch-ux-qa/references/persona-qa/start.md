# Start from a target, not a manifest

## Host workflow

Accept the user's target folder and goal in ordinary language. Reuse the granted
scope and known workspace. Do not ask the user to copy code, write JSON, choose
Library commands, calculate hashes or explain internal task IDs.

1. Read the target's approved README/PRD and existing result summary. Identify the
   target, relevant goals, existing personas and actual execution boundaries.
   Read only task-relevant paths; do not search personal directories.
2. Prefer an existing reviewed source adapter. Use a reviewed saved experiment
   folder or explicit `--include relative/file` arguments. The host inspects the
   minimal relevant files first and selects explicit relative paths; the
   command generates their hashes and copy plan. Do not request a user-authored
   manifest or blindly copy a repository.
3. Choose a new or empty independent workspace and run `start`. The command
   announces the bounded copy, verifies file bytes, prepares the workspace and,
   when saved evidence is present, reuses the exact validated persona revisions
   and produces MD/JSON. No product, browser, dependency install or model runs.
4. For a new source-only workspace with a reviewed owned Python adapter and
   current saved personas, continue with `local-run.md` sections 1–4. For research
   motivation, also follow section 6: explicitly review its exact local research
   directory before connecting it. The host fixes
   goals/criteria and runs the adapter; the user need not learn receipt plumbing.
   Preserve prior experiments; do not start a new run to reset their limits.
5. Explain the result in terms of user goals: preparation, existing findings,
   untested obligations and the next permitted action. Read the generated report;
   do not equate process exit zero with a passed product task.
6. On return, run `status` or the identical `start`. Both recheck source/evidence
   and current persona validity. Do not rerun old tasks, renew deadlines, replace
   failed evidence or create another run to escape attempt limits.

The conversational interface is the skill's host. CLI examples are for that
host and maintainers, not prerequisites the end user must learn.

For a requested larger model-driven swarm, continue with `scale-run.md` after
current persona/source preparation. Preview available personas, provider data
destinations, concurrency and the maximum cost; obtain explicit approval before
paid calls. Pause/resume uses the same queue and budget. A fixture simulation
does not prove actual-model or actual-product UX performance.

For capture budgets or cleanup review, use the [storage retention guide](storage-retention.md).
List candidates only; preserve evidence and unresolved runs.

## Supported entry

From the installed skill folder:

```sh
python3 scripts/ux_personas.py start --source APPROVED_OWNED_FOLDER --work NEW_WORKSPACE
python3 scripts/ux_personas.py status --work NEW_WORKSPACE
```

The extracted distribution also exposes:

```sh
python3 scripts/remorsearch.py personas start --source APPROVED_OWNED_FOLDER --work NEW_WORKSPACE
```

Use `--format json` for integrations. The default output is a readable Korean
report with user goals and a report path. JSON preserves task IDs, exact persona
revisions/fingerprints, prior attempts, requirement exclusions and failed
criterion/evidence links without exposing lease tokens.

A direct reviewed source folder needs no prebuilt manifest. A saved owned pilot
folder adds the existing library and result link. Source-only preparation reports
that no QA result/persona was supplied; it does not invent either.

The saved-evidence adapter is intentionally bounded. Do not relabel a changed
product as a frozen prior run. Generic source preparation uses the host's
reviewed `--include` selection and never automatically ingests saved metadata.
It initially reports source preparation only. The bounded `run` integration in
`local-run.md` connects reviewed Python core execution to current observations
and reports. Other execution routes still use the normal host Library/claim/
receipt flow. No universal runner, automatic persona generation or native/browser
execution is claimed.

## Recovery and boundaries

The workspace records ownership before copying. An interrupted copy is resumed
by the same start command, retaining verified completed files. A foreign
nonempty destination, different source or edited copy is not overwritten.
Concurrent callers share the existing Store lock; an unowned in-progress folder
can be refused safely, then revisited after the owning start finishes.

Only approved relative file names and exact receipt-referenced artifacts are
read. Every component is opened without following symlinks; hardlinks, special
files, excessive sizes, key-shaped contents and external evidence/context
bindings are refused. Dependencies, arbitrary logs, claims, account exports and
unlisted files are not copied. This is a bounded intake guard, not an OS sandbox
or a universal detector of personal data. The host's content and scope review
remains necessary.

Prior Library/swarm files are copied privately before their existing validators
are used. Original locks, state, receipts and deadlines are not mutated. Exact
PRD/build bindings still refer to the approved original owned source; if it is
moved, changed or unavailable, review is blocked rather than silently rebinding
personas. No automatic revision/import is performed.

A missing or stale input gives a reason and next action without a Python
traceback. The host handles that action. Do not expand permissions, follow an
external dependency link, install runtimes, log in, deploy or bypass source
access controls merely to make preparation succeed.

## Evidence meaning

A preparation-only workspace report says `execution_performed: false`. After an
authorized local run, start/status show its current report; uncertain dispatch
is explicit and never replayed. Existing synthetic core
results remain prior evidence. A failed import is still failed; core successes
without required UI evidence remain inconclusive. Source copying, receipt
validation and exact persona reuse do not demonstrate a new journey, UI
usability, persona advantage, satisfaction or readiness. Preserve the old report
and every attempt when authorizing any subsequent real execution.
