# PE-2 condition N: frozen independent report

All six cases exercised independently through one isolated runner. Three observable defects, not inferred implementation causes:

- **J2N:** Cancel removed Morning Birds, leaving River Sounds and count one. A later removal request timed out because its control was absent. Explicit confirmed removal remains not run. Evidence: browser captures 009–011 and raw actions log.
- **R5B:** After submitting zero, valid corrections to five and nine both left the old range error and no saved note. Counted as one recovery failure. Evidence: captures 020, 022, 024 and raw actions log.
- **D3W:** Retry changed Avoid stairs to Shortest path and displayed Hill steps, 0.8 km, includes stairs. A subsequent Avoid stairs preview did the same. Counted as one preference-preservation defect; shared implementation cause is only a hypothesis. Evidence: captures 031–033, 035, 037 and raw actions log.

V7Q passed the bounded zero → five → nine care-note recovery/edit task. H8C passed nondefault choice, required outage, retry and subsequent shortest route. L9F passed open, cancel, reopen and confirm. Defaults were observed independently in all six cases. Full per-criterion outcomes, exact steps, exclusions and coverage mappings are in findings.json. D3W's later explicit Shortest path preview passed narrowly, not the broader ability to change to the no-stairs route.

## Budget and evidence

37 attempted actions, one UI timeout, zero unknown execution outcomes; no command repeated for transport uncertainty. First action: 2026-11-11T01:16:06.743Z. Last action end: 2026-11-11T01:21:28.542Z. Last evidence end: 2026-11-11T01:21:28.574Z. Harness elapsed: 321832.00237500004 ms. Receipt authoring and between-case claims consumed this wall window. EOF closure completed at 2026-11-11T01:21:58.582Z; harness and launcher exit zero with shutdown_complete. No restart, reset or post-closure UI.

Three PRD-hypothesis personas were actually reused at revision one. Each of six cases was claimed before its UI, starter-generated, truthfully completed and recorded before the next claim. All six record calls passed gates on first submission; three tasks passed and three failed. Actual screenshots and unchanged execution-log snapshots were copied privately to each claim evidence directory with SHA-256 hashes. Three defect screenshots were visually inspected after closure. Source, tests, hidden keys, other conditions and external research were not inspected.

## Limits and authoring cost

Representative zero/five/nine inputs only; empty, nonnumeric, fractional, other out-of-range and endpoint matrices are excluded. J2N confirmed removal was prevented by the cancellation defect. No keyboard-only, accessibility, persistence, production or real-user effectiveness conclusions. Synthetic task results do not establish whole-product readiness.

Preparation was not zero-cost: allowed packet/CLI reading, three reuse calls, first claim/starter and an evidence helper preceded first UI; that preparation was not separately timed. An initial incorrect root CLI path failed and was corrected before UI. A second authoring helper was written inside the wall window. Each case required actual observation authoring, PNG/log copying, hashes, record and next claim/starter. No receipt rejection occurred. J2N's not-run criterion was explicitly authored with no evidence IDs. The only UI error was the bounded absent-button timeout, recovered by polling the same PTY, not retrying the command.

Frozen before any unblinding. No subsequent edits or UI authorized.
