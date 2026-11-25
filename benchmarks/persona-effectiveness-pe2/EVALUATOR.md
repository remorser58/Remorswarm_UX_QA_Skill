# PE-2 black-box evaluator protocol

Only this file and PRD.md may be read as benchmark inputs. Do not read app/source, tests, hidden key, verification traces, other trial reports, earlier benchmark assets, or persona data unless explicitly supplied by the coordinator as your condition. Both conditions receive exactly the same public requirements. Interact only through the owned runner below; do not inspect JS, storage, network, page source, developer tools, filesystem inputs or internal state. Do not modify target or tooling.

## Start and keep open
Use prepared Node.js 22 and Playwright. No installation, personal browser, user profile, screen or tab is needed. From the repository root:

```
EVIDENCE_DIR=/absolute/new/nonexistent/directory /absolute/path/to/node22 benchmarks/persona-effectiveness-pe2/run.cjs
```

The directory's parent must exist. The runner resolves prepared `skills/remorsearch-ux-qa/drivers/web/node_modules/playwright` in this repository. An explicit PLAYWRIGHT_MODULE absolute path can select another already prepared dependency. There is no sibling-worktree fallback. Wait for the JSON `ready:true` before input. Maintain the same process with stdin open throughout your evaluation. Closing stdin ends the browser and owned loopback-only ephemeral server. SIGINT/SIGTERM also clean up. A failed setup is a limitation, not a pass. Isolated headless launch may need the approved sandbox escalation on this Mac.

## Operations: one JSON object per line
Submit one command, read its result, then decide the next command. No parallel commands, command arrays, bulk actions, arbitrary selectors/scripts, waits, silent retries or alternate browser paths. All accessible names are exact. Examples describe syntax, not a required test order:

```
{"op":"goto","case":"V7Q"}
{"op":"observe"}
{"op":"click","name":"Save care note"}
{"op":"fill","name":"Interval in days","value":"5"}
{"op":"select","name":"Route preference","value":"Avoid stairs"}
{"op":"key","role":"button","name":"Save care note","key":"Enter"}
{"op":"screenshot"}
```

click/key use role (default button) and exact accessible name; fill/select use exact label. Allowed keys are Enter, Tab, Space, Escape, ArrowDown and ArrowUp. No scripts or DOM mutation APIs exist. Synthetic input only: commands are logged. The visible page text and screenshot path are returned on every result, including failed operations. Screenshots live in the evidence directory's browser/ folder and may be viewed as visual evidence.

## Hard budget and evidence
60 attempted UI actions maximum across all cases combined, 12 minutes of monotonic time starting at the first attempted action. Each goto/click/fill/select/key attempt counts, even invalid names, invalid cases, timeouts or failed interactions. Observe/screenshot do not count. Never restart/reset/replace the runner to extend the budget. No individual action wait exceeds 2.5 seconds. Every result reports unique sequence, start/end wall and monotonic timestamps, first-action origin, cumulative action count and elapsed time; end marks operation completion before evidence capture. Evidence capture has its own end timestamp. Action 61 and actions after time exhaustion are truthfully blocked and do not execute. Observation remains available. Budget includes time spent deciding, reading and collecting evidence after first action. Preserve raw evidence. The runner records lifecycle, stdout and browser action JSONL plus screenshots. EOF is normal closure, not a claim every case passed. SIGKILL, machine loss or disk failure can prevent cleanup/evidence.

## Report before unblinding
Freeze one report: cases attempted, workflow obligations covered/not covered, reproducible findings with expected/observed and evidence, remaining uncertainty, attempted actions and exact elapsed time from harness. Explicitly distinguish clean tested behavior, untested behavior, a confirmed violation, and a harness/access block. Do not guess hidden classifications or use how many findings you expect as a stopping rule. Stop at the budget or when your bounded review is complete, close stdin, and send the report path and evidence path to the coordinator. No edits after unblinding.
