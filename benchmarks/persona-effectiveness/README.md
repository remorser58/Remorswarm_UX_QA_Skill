# Blinded behavioral fixture

Coordinator: start `node benchmarks/persona-effectiveness/server.cjs` from repository root with the pinned Node 22 binary. Bind is loopback only, port 4187 (override PORT). Run one isolated headless browser per condition, no personal browser profiles. No installation is needed.

Evaluator: read only this README, PRD.md and the provided condition packet. Use `node benchmarks/persona-effectiveness/harness.cjs` from repository root with a fresh EVIDENCE_DIR. The default Playwright path is the already-prepared sibling retry worktree; PLAYWRIGHT_MODULE can override its absolute path. Send one JSON object per input line. It prints actual DOM text, screenshot path and action count after each call, with failures explicitly logged. Close stdin to finish. Use a persistent terminal session for interactive decisions.

Examples (not a prescribed test plan):
```
{"op":"goto","case":"K4M"}
{"op":"fill","label":"Workshop title","value":"Folded stars"}
{"op":"click","name":"Review draft"}
{"op":"observe"}
```
`click` and `press` use an exact accessible button name (`name`), optionally another `role`, or exact `label`. `fill` uses `label` and string `value`; `select` uses `label` and option `value` (`name` or `cost` for room sorting). `press` additionally uses `key`. `goto` accepts only the six case IDs. `observe`/`screenshot` inspect without consuming actions. Navigation, click, fill, key press and selection each cost one action, including failed attempts. A screenshot is automatically saved after each successful call. Do not use multi-action key sequences to evade the budget.

Common budget: 60 attempted UI actions total, 12 minutes browser time per condition. All six cases share that budget; inspection and report writing do not consume actions. Report action count and untested obligations. Initial navigation counts; resuming via a fresh URL resets the case intentionally. Source review, DevTools/runtime injection, network inspection, filesystem inspection of application files and private oracle are not permitted before findings freeze. No code changes during evaluation. UI defects outside these PRD obligations may be noted separately but are not scored as seeded findings.

Evidence is synthetic and supports only this fixture-level comparison. It cannot establish real-user benefit or population-level persona effectiveness.
