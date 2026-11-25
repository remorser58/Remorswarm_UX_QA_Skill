# Persona workflow tooling validation, 2026-11-11

**Post-publication correction:** the recorded checker run passed before a final English README edit. That edit was not followed by the bilingual README checks, so these numbers did not certify the complete published `328bc20` tree. The next full suite detected three README parity failures. Both README versions are corrected in the PE-2 follow-up, with fresh validation recorded separately. The original run results and failed follow-up are retained; runtime/browser outcomes and the frozen PE-1 comparison are unchanged.

Base: `544615d`; this record accompanies the subsequent commit containing the
changes. Exact tested file digests and measurements are in the
[structured record](persona-workflow-tooling-20261111.json).

## Delivered changes

- Receipt validation now names the fixed-schema field that needs correction and
  gives safe guidance, without echoing rejected values, arbitrary keys or lease
  tokens. Existing privacy rejection, evidence checks and state-write boundaries
  remain unchanged. No automatic scrub, fabricated observation or pass fallback.
- A portable local benchmark launcher owns an ephemeral loopback server, verifies
  readiness before browser input, records lifecycle/forwarded-command times and
  closes its resources on EOF and supported signals. It never resets budgets or
  retries UI commands. It does not use a personal browser profile or install tools.
- PRD and user-facing usage/evidence guidance updated. Five launcher regressions
  are wired into the existing Node CI job; this does not change workflow triggers.
- [New controlled comparison](experiments/persona-workflow-20261111/README.md),
  frozen fixture/protocol, independent adjudication and minimized synthetic evidence
  are available in the repository. The comparison is incomplete, not a claimed win.

## Verification on final implementation

| Check | Result |
| --- | --- |
| Full Python 3.14.7 suite | 1,156 passed, 1 skipped; 51.637 s suite time |
| Persona subset including 8 new diagnostics tests | 114 passed |
| Chromium selftest through extracted installation | 559 passed, 0 failed; 262.92 s |
| Complete release checker | 16 checks passed, `ready: true`, `published: false` |
| Extracted-package diagnostics | 8 passed; imported implementation origin checked |
| Launcher focused tests | 5 passed; 0.197 s |
| Actual isolated launcher smoke | goto + observe, 1 counted action, exit 0; server closed |
| Actual launcher SIGINT | 0 UI actions, exit 130; server closed |
| Offline smoke/research fixtures | Passed; no external research requests |
| Diff whitespace and independent source/publication review | Passed |

Complete release command: `python3 scripts/check_release.py --output dist/persona-workflow-20261111-r1`,
with the prepared Node 22.23.4/Playwright 1.56.1 toolchain and isolated Chromium.
Existing dependencies were copied, not downloaded or reinstalled. The Mac requires
approved unsandboxed Chromium launch; no security setting or personal browser was changed.
The full check exited 0: 318.08 s wall, 117.83 s user, 31.06 s system,
250,593,280 bytes maximum RSS (about 239 MiB), zero swaps. These are local test-run
resource measurements, not production latency or persona-model cost.

The one Python skip needs `ERGO_PAINT_CAPTURES`; optional real-browser handshake
and typography samples were not supplied. Synthetic passing checks are not live
research, accessibility certification, real-user effectiveness or merge readiness.

## Diagnostic effect and limits

The original completed K4M receipt and its real synthetic-browser artifact files
were read again through both base and updated validators. The corrected receipt
was accepted by both. Two reconstructed error variants, a blank observation and
a timestamp-shaped evidence ID, were rejected by both with the same code/reason.
The updated errors named the actual observation/reference field instead of only
`input`. The original receipt and swarm-state bytes remained unchanged. This is
post-trial artifact validation, not a fresh browser run or a timed usability study.

A worker initially attributed the rejection partly to a local path. A generic
local path alone was not reproduced as a privacy violation; the timestamp reference
was. Do not repeat the path attribution as an established cause. The filter remains
conservative; descriptive evidence IDs with matching references are the supported
correction, while original evidence bytes are retained privately.

The new launcher cannot guarantee cleanup on SIGKILL, machine loss or filesystem
failure. Forwarding timestamps are not exact execution-start timestamps for queued
commands; exit 0 is not a guarantee that every UI operation succeeded.

## Remaining work

The comparison found the same three supported seeded defects per condition, but
one clean control remains unverified in the persona condition and full elapsed
times are unknown. No workflow superiority, completed tie or real-user benefit is
established. A next confirmatory experiment needs new held-out cases, an oracle
hash committed before execution, timestamped first interactions, complete receipts
and the same explicit budgets. Published PE-1 cases are now development fixtures.

DC permission, authorized YouTube API provenance/key and appropriate user-provided
native study evidence remain missing; this work does not bypass those gates.
No Peekly files, installed skill, main branch, merge, deployment or public sharing
settings were changed. The original worktree's HEAD/status and all 310 preserved
file digests still match the pre-publication snapshot.
