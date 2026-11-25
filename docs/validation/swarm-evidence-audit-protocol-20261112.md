# Swarm evidence consistency audit — fixed protocol

Date: 2026-11-12 KST. Base: `3074f5089e0fdd22db932709370211656c90b3eb`.
Branch: `rem/swarm-evidence-audit-20261112`.

This protocol is fixed before the new regression and implementation. It does not
authorize browser, user, provider, network, model, or external-product activity.

## Selected gap

The existing swarm validates each receipt and the local runner records a bound
execution log, but the final user report does not independently reconcile the
persisted log against the receipt or compare observations across personas for
the same declared PRD obligation. Repeated wording can look like corroboration;
contradictory results remain separate rows without an explicit conflict verdict.

Implement a deterministic, read-only audit in the existing report path. Reuse
the durable dispatch journal, swarm report, receipt validator, fixed requirement
coverage, canonical hashes and immutable execution logs. Do not add a worker
framework, model evaluator, dependency, browser transport or parallel process.

## Fixed acceptance criteria

1. Preserve a red regression showing that the current report omits a swarm-level
   evidence audit for a run with multiple personas and a shared PRD obligation.
2. Re-open each recorded task's exact execution log using bounded no-follow file
   access. Verify the log digest, task/attempt/operation/build/persona binding,
   diagnostic completion, and exact observation-to-receipt correspondence.
   Missing, duplicated, mismatched or unreadable evidence blocks the audit; it
   never creates a pass or silently repairs a receipt.
3. Aggregate only the same `(requirement_id, obligation_id)` across distinct
   tasks/personas. Distinguish independent observations, byte-identical repeated
   observations and passed/failed contradictions. A duplicate is not another
   independent signal; a contradiction remains unresolved and visible.
4. Preserve per-task outcomes and original receipts. The audit is a separate
   deterministic assessment, not an LLM judgement, user study, or independent
   human reviewer. It cannot promote core-only results to UI/product passes.
5. Report declared obligations with no valid observation as incomplete, and
   retain task/criterion/evidence references for every duplicate or conflict.
   Never infer missing dispatches, fabricate observations, or replay work.
6. Repeated run/status reads produce byte-identical audit results and do not
   dispatch, rewrite evidence, alter Library/research, or change attempt budgets.
7. Test integrity tampering, wrong bindings, missing logs, duplicate evidence,
   contradictory outcomes, omitted criteria, and normal multi-persona execution.
   Run related regressions, full Python/release checks, extracted diagnostics,
   Mac elapsed/RSS measurements; browser remains prohibited and release remains
   non-ready under `--skip-web`.
8. Update PRD, installed skill instructions and immutable MD/JSON verification.
   Commit only reviewed files, normal-push, independently verify remote SHA and
   clean status, and preserve all pre-existing worktrees/processes.

## Evidence boundary

All new executions use the existing owned synthetic defective product and
invented/offline persona fixtures. A mechanically consistent receipt proves
internal linkage only; it does not establish that an adapter's prose is true,
that a source is authentic, that personas are independent real people, or that
the product works in a browser. Actual UI, public-source acquisition, user
research, service acceptance and human adjudication remain unverified.
