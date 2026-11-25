# Local journey execution — criteria fixed before implementation

Date: 2026-11-12 KST. Base: `21681e17d83357736df448e93b94ba96b539f4bf`.
The remote heads and ancestor relationship were verified before creating the
branch.
Branch: `rem/journey-run-report-20261112`.

## Chosen gap and bounded product path

The installed start/status path only prepares code and revalidates historical
results. It cannot conduct a new reviewed journey and publish its current
observations as a readable report. Implement a local runner integration using
the existing workspace, persona Library, swarm claim/receipt/record/report,
privacy checks and atomic Store. No new model, browser, research crawler,
package dependency or general shell-command interface.

The conversational host reads the user's target and goal, reviews the minimal
source and runner, selects existing personas and authors the bounded criteria.
The user does not author JSON, leases, hashes or receipt plumbing. The initial
runner transport executes an explicitly reviewed, copied Python adapter in a
fresh owned process with a private per-attempt cwd, empty inherited environment,
fixed stdin/stdout observation protocol, output/time limits and no shell.
It is a reviewed-code execution boundary, NOT an OS/network sandbox. Never
automatically execute a script merely because it is present in a repository.

Existing PRD-hypothesis personas may be selected by their current versions with
exact source-context bindings. No persona is invented or imported automatically.
Research-linked records outside the reviewed source boundary must be refused,
not downgraded or relabelled. Existing research admission remains available in
its normal host-driven workflow. Preserve every original Library and prior run.
A prepared workspace containing prior results must not reset old attempts
by starting a new local execution; use the existing reviewed replay workflow.

## Fixed acceptance criteria

1. Reproduce the missing installed run entry after successful source-only
   preparation. Preserve the first failed assertion and exit result.
2. From a new owned workspace, run real local adapter processes for multiple
   existing synthetic personas. Bind source, exact current profile, goal,
   success/recovery criteria and declared PRD obligations before dispatch.
   Merely starting a process or exit zero never creates a passed QA result.
3. Persist dispatch intent before spawning. Repeated completed calls return the
   existing report without another execution. Interrupted/uncertain dispatch
   never automatically replays, renews a lease, resets a budget or claims safe
   effects. A recorded receipt whose final acknowledgement was lost is recovered
   by readback only. Concurrent callers cannot dispatch the same task twice.
4. Validate bounded real observations through the original receipt gate. Report
   a product failure only with actual steps and an evidence-linked failed
   criterion. Timeout, nonzero/malformed output, cancellation and unavailable
   execution remain infrastructure gaps/uncertainty. Core observations cannot
   produce screenshot/UI or real-user evidence; overall pass remains unavailable.
5. Reject missing approval, changed source/runner/Library/PRD, stale personas,
   foreign task/attempt/binding, unknown fields, external paths, links/special
   files, sensitive output and occupied state without changing originals.
   No inherited credentials, dependency traversal, install, account/network
   operation, browser or model is used by the validation fixtures.
6. Extend start/status to show current execution progress, user goals, exact
   persona reuse, failures, unexecuted obligations, evidence links and next
   actions in immutable MD/JSON reports. Preserve old entry reports and attempts.
7. Run relevant regressions, the complete existing release checker, extraction
   and relocated execution with Mac elapsed/max RSS. The user's browser ban
   requires the existing --skip-web path; release ready MUST remain false and
   exit nonzero. Retain the existing capture-dependent skip and every quality
   threshold. No installed browser or fabricated pass.
8. Review explicit changed files, sizes and hashes; preserve pre-existing
   worktree contents/status and processes; ordinary commit/push; verify remote
   SHA and clean new worktree. Record actual limits and failed attempts.

## Reuse review

- Existing workspace.start/status supplies descriptor-based minimal copying,
  immutable source identity, private reports and no-follow intake.
- Existing Library supplies version, PRD citation, review expiry, research and
  retention rules. Reuse a private selected snapshot; never mutate the original.
- Existing swarm supplies fixed plan validation, claims, deadlines, uncertainty,
  resource quarantine, receipt integrity and obligation reporting.
- Existing frozen benchmark pilots show the required claim -> real local process ->
  observations -> record sequence, but is an experiment-specific benchmark and
  must not be promoted as a general product or rerun without scope review.
- Existing Python stdlib subprocess/selectors/signal/time and release tooling
  suffice. Adding another orchestration or agent SDK would duplicate these
  mechanisms and increase supply-chain/permission surface.
- No visual composition is changed. Existing report/CLI conventions are reused;
  Figma, real UI and human usability acceptance remain outside this work.
