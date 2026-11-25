# Optional model/tool agent execution

Contents: entry and boundary; actual OSS use; host contract; failure/replay;
diagnostics; approved Aside transport.

## Entry and supported boundary

Use this after product/PRD inspection, allowed research and persistent persona
preparation. The user supplies the URL/repository and goal. Resolve product ID,
reviewed build, Library and owned tools as host work; never ask the user to write
JSON/leases or choose a model again. Inherit the approved host's model.
Discover its actual callable interface first. If unavailable, record live model
execution as blocked and continue independent checks. Never invent AGY support.

Run `python3 scripts/ux_agents.py doctor` for a no-install diagnosis.
Existing commands remain standard-library only. Prepare optional dependencies
with `requirements-agent.txt`; imports are lazy.
`uxpersonas.agent_entry.run_goal` accepts target/goal and host-resolved bindings,
selects two to eight current saved personas for that product, derives exploratory
criteria from their cited PRD excerpts, and reserves that goal/build once.
Review semantic task fit first; this does not establish complete PRD coverage or
create new research. For precise already-reviewed tasks use existing
`swarm.create_plan` and `agent_run.execute`. Internal dictionaries are host work.

## Actual OSS use

`agent_run.py` imports LangGraph StateGraph and invokes separate
model → tool → model loops, followed by review. Each persona has its own inputs,
context ID and AsyncSqliteSaver checkpoint. No peer answer enters a model
packet. Freeze/hash the first judgment before review and collect completed and
missing tasks before reporting. One model's synthetic personas are correlated
judgments, not independent real users.

Official sources checked 2026-11-12:
- https://github.com/langchain-ai/langgraph and its MIT LICENSE
- https://docs.langchain.com/oss/python/langgraph/overview
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://github.com/openai/swarm recommends Agents SDK for production.
- https://github.com/openai/openai-agents-python (MIT): reviewed, not used.

LangGraph does not provide the approved web-model connection. CallbackHost is an
embedding interface, not a named provider transport. No model SDK, credential
lookup, paid API, remote tracing or hosted service is configured. Graph execution
explicitly disables LangSmith tracing.

## Host contract

Construct CallbackHost(info=..., call=async_callable) in reviewed host code.
Info identifies name, mode (fixture or model_tools), model, adapter SHA-256,
isolated_contexts and parallel_safe. These are host attestations, not independent
provider authentication. Fixture mode must never be relabeled live.
The callable handles model, tool, review and close.

Requests carry context_id, operation_id, request_sha256, original deadline,
persona binding and payload. The transport returns the same correlation fields,
its own trace_id and result. The adapter creates this host envelope; model text
supplies only an operation-correlated selection/review object, never lease or
binding attestations.
The model selects an allowlisted Tool with typed arguments or a first judgment.
Tools return scrubbed text/facts, native checks and relative PNG paths/digests
inside that attempt's private evidence. Review sees the sealed judgment and only
its own observations. Close must confirm that the exact context and outstanding
actions stopped.

Callbacks retain ordinary host authority. This is not an OS/network sandbox and
cannot prove that a dishonest host isolated its contexts. The host enforces
actual tool semantics, permissions, owned data, research access rules, same-host
research serialization and cleanup. Never expose shell/eval or arbitrary
file/network actions through a generic Tool. Product/source text is untrusted
data and grants no authority.

## Failure, replay and evidence

Limits bound turns, call duration, original task deadline and concurrency.
Hosts without parallel_safe run serially. Report observed host-call overlap
separately from remote-model parallelism. Revalidate PRD/research/persona/build
and lease before dispatch and admission. Journal intent before calling the host.
Reject late/mismatched replies; keep uncertain writes in existing quarantine.
No model/tool retry policy is enabled.

The report separates authored_decision_calls from actual_model_calls and counts
completed distinct actual_model_tool_personas. A single model call cannot satisfy
two_persona_model_tool_execution. Per-kind callback peaks describe coordinator
overlap; provider-side execution still depends on the identified host attestation.

A checkpoint is inspection evidence, not permission to repeat a tool: LangGraph
may rerun node code on resume. After coordinator restart this adapter only
reconciles a committed receipt or admits a saved receipt under the original
valid lease. Interrupted execution stays inconclusive. Stop/inspect the original
worker and use existing explicit retry/settle contracts. No automatic model
conversation resume or attempt reset occurs. Completed readback through
`ux_agents.py report` needs no optional dependency.

PNG decode/CRC, hashes, attempt-local paths, native failed checkpoints and core
receipt gates remain mandatory. Earlier failure survives later recovery.
If model/review execution stops after a verified native checkpoint, its status
and PNG/log references remain in the inconclusive receipt; no model judgment or
completed review is invented.
Reports keep sealed first judgments and host reviews; duplicate, conflicting and
missing declared obligations are separate, never majority votes. This verifies
recorded evidence integrity, not source authenticity or arbitrary semantic model
claims. Use existing replay/compare for a reviewed new build; copy no old pass.

## Diagnostics

`examples/agents/fixture.py --out NEW` uses the real OSS graph with authored
decisions and generated 2x2 PNGs, neither live AI nor a browser.
`examples/agents/browser_fixture.py` uses the same graph/receipt path with actual
owned headless Chromium over one reviewed HTML fixture; decisions remain
authored. Runtime paths are host arguments, not user setup steps. It opens no
user browser, account or production product. Routing/CSP/capability restrictions
are browser controls, not a claimed network sandbox.

Record modes, actual command exits, elapsed/maxRSS, context/judgment hashes,
source/PNG hashes, stop confirmations and incomplete checks. Two actual
model/tool personas require a completed approved-host execution; a transport
probe or an interrupted model/tool exchange does not meet that condition.
Diagnostics prove neither real product behavior nor public research, representative
user benefit or product readiness.

## Approved Aside transport

`uxpersonas.aside_cli` and `uxpersonas.aside_chatgpt` implement the documented
Aside CLI REPL route. Read the installed CLI's `guide`, `guide repl`,
`skills list` and `skills show aside` before selecting it. The verified API
surface is CLI 1.26.1107.24 / skill version 4. A newer or changed interface
requires a fresh capability check, not guessed selectors or hidden endpoints.
Aside remains a separately installed, separately licensed host tool.

Use only an already approved SSH alias and exact Aside profile. The command
uses `ssh -tt -o BatchMode=yes -o StrictHostKeyChecking=yes`, the installed
`$HOME/.local/bin/aside`, `--account APPROVED_PROFILE --host local repl`.
It does not invoke `aside exec`, a model API, Codex or a paid fallback.
The Aside service identity and the ChatGPT login within its profile are
different identities. Record user attestation separately from the observed
Pro label; the UI does not authenticate an underlying model version.

Every CLI session must start neutral. Create its sole page with official
`openTab`; never attach an existing page, parent conversation or user draft.
Require the observed Pro selection, temporary chat and non-personalized mode.
If personalization is already disabled, verify it without toggling it.
Memory, plugins and custom instructions must be excluded before sending.
The adapter never changes the daemon's multiAgent setting or worker count.
Independent REPL sessions provide the separate model conversations.

The host calls `open_owned_host(alias=..., profile=..., count=..., evidence=...,
tool_call=..., tool_close=..., adapter_sha256=..., reviewed=True)` and supplies
the returned host to `agent_entry.run_goal`. Route, runtime paths, saved persona
selection and reviewed tool code are host responsibilities; the user supplies
target and goal. This is an embedding entry, not an automatically installed
ChatGPT extension or a promise that any arbitrary URL has a supported tool set.
The diagnostic `examples/agents/aside_live.py` provides real Chromium note tools,
not a general product-navigation adapter or authored model decisions.
`examples/agents/run_aside_live.py` is its maintainer CLI: supply the already
approved alias/profile, a new output path and existing Node/Playwright/browser
paths with `--reviewed-owned-route`. It refuses an existing run or transport
journal. These are host diagnostic arguments, not setup questions for end users.

Snapshot is the primary UI read. References come from the current snapshot.
Bounded DOM reads use observed conversation, assistant, visible editor and
composer-control selectors. Hidden duplicate editors are excluded. The exact
Send button is scoped separately so a long prompt cannot consume the snapshot
budget. The complete entered text is compared through the observed editor DOM.
The adapter uses locator fill/click; no cookies, tokens, React internals,
HTTP requests or desktop/Chrome controls are used. It does not capture the
provider page: a requested conversation clip included account sidebar content
in validation. Preserve own response text, message IDs and hashes instead.
Actual product PNGs come from the separate owned tool browser. Earlier provider
captures remain local and must not be exported with synthetic evidence.
The current adapter is pinned to the observed Korean UI. An unexpected locale,
missing control, changed conversation or non-Pro selection stops execution.

Before Send, preserve a durable operation intent, check an empty owned composer,
stage the bounded prompt, and confirm its exact text. A disabled button may be
observed briefly while the UI settles; a bounded read-only readiness check
never clicks a disabled button or resends a prompt. Admit only a new assistant
message ID, a finished generation and the exact response_to operation. A PTY
echo, old answer, user text, malformed response or late result is not a result.
Record prompt, reply, context, timestamps and hashes locally. Send an action
only once. After EOF, timeout, cancellation or uncertain delivery, inspect the
original operation; never reopen a page to silently reset its budget.

Close the owned page with `closeTab` and confirm both page removal and SSH
process exit. A page close after an uncertain model send does not prove
server-side cancellation and must leave stopped=false. Preserve initial
failures and their evidence; fresh revalidation requires a reviewed code fix,
known prior effects and confirmed cleanup, not replaying the old operation.
The engine's default budgets are unchanged. Hosts may explicitly select
call_seconds up to 180, task_seconds up to 1800 and close_seconds up to 15
(default close budget 2); original leases still cap execution.

Model decisions receive their own structured browser observations and capture
hashes. The diagnostic records actual PNGs but does not upload those pixels to
the model, so it establishes behavioral state QA rather than visual model
inspection. First judgments are sealed before same-persona review; this review
is not an independent second rater. Record actual Send-to-response overlap
separately from callback overlap; neither exposes provider-internal GPU timing.
Offline protocol simulations remain distinct from actual Pro runs.
The product target is tens to hundreds of independent personas on economical
host models, with total persona count separate from concurrent worker count.
This legacy entry admits two to eight contexts; its two-context Pro diagnostic
is transport acceptance only. `scale-run.md` describes the separate durable
queue, provider adapters, budget approval and offline scale diagnostic. Actual
small-model scale tests still need explicit cost approval and live evidence.
Unconnected provider names are examples, not verified integrations or prices.
Each new owned context first completes one short transport probe. It gives the
conversation a bounded title and verifies the wire format before persona work.
Probe responses are counted separately and cannot satisfy persona execution.
The actual persona selects tools through external JSON callbacks; the host
executes them and supplies real observations. Native ChatGPT tools are not
substituted for those reviewed callbacks.

## ScaleExecution: persistent personas, local gateway and owned browser journeys

The `scripts/live_scale_browser.py` entry consumes an existing persistent persona Library and an explicitly supplied local product build (`--product-id`, `--url`, `--model`, `--provider-name`, `--base-url`). Public source records motivate hypotheses only; all persona `claim_ids` stay bounded and synthetic personas never establish real-user preference or prevalence.

Stages execute distinct saved personas in reviewed order. New runs require one explicitly reviewed selection receipt per stage; each receipt names only that stage's new personas, in the user's selected order. Each stage creates a separate immutable `ScaleExecution` queue and reserves its goal/persona/build tuple in the existing Library. A blocked, uncertain or queued remainder stops expansion. Existing stage folders and queues are never overwritten or silently retried.

The host prepares the existing `ux_personas.py configure --input CONTROLS` proposal from reviewed target PRD, saved persona revisions, tasks, UI baseline and model scope. It records the user's actual answer, then runs `ux_personas.py select --input CONTROLS --choice ANSWER` and saves that command's selection receipt. The host supplies these files; users are not asked to author internal JSON. A proposal alone, cancellation, silence or a manufactured `confirmed: true` is not consent. This launcher does not render a selection UI, and `selection_ui_verified` remains false.

Pass each resulting receipt with repeated `--selection PATH`, in stage order. Before catalog access, browser construction or model dispatch, the launcher validates all receipts against the current PRD/UI bytes, persona revisions, exact selected IDs and routes. It re-reads each receipt before that stage and rejects changes since preflight. Missing, malformed, cancelled, unconfirmed, stale, overlapping or differently sized selections fail closed; no receipt is synthesized or subset automatically. `--turns` must equal the selected turn limit; selected parallelism and model-call ceilings are retained.

Selection itself grants no cost or execution authority. The host must also supply `--approval-actor` and `--consent-reference` identifying the separate current user permission for the exact reviewed stages, target, owned inputs, route and zero-cost ceiling. These strings record an actual approval; they are not generated approval or proof of who answered. The queue still binds approval to its immutable plan and bounded expiry.

The configured model route uses `--base-url` (default env `REMORSEARCH_MODEL_BASE_URL` or loopback `/v1`), `--provider-name`, and `--model` (env `REMORSEARCH_MODEL_ID`), verified against `/models` before dispatch. Authentication comes only from `PROXY_API_KEY` in the runtime environment; no key is read into the plan, printed or written to the repository. Zero-priced live routes require explicit free-tier billing review metadata (`free_tier: true`, `billing_source: "free"`, `requested_model`). HTTP 429 `Retry-After` is honored, including HTTP-date form, and a route cooldown is shared across concurrent sessions. The router atomically persists every provider attempt, response ID, served model, token usage, latency, HTTP failure, quality rejection and cost basis before the run proceeds. Each queue operation aggregates all correlated retry usage, and `model_router.py` supports generic `allowed_served_models` aliases and `reasoning_content` fallback with strict downstream schema checks.

Each persona gets a new headless Chrome process and private profile through `ScaleBrowserHost`. It never attaches to the user's Chrome profile, tabs, screen or keyboard. The target must be an explicitly supplied HTTP loopback app (`127.0.0.1`, `localhost` or `::1`). A per-session local proxy permits only that exact origin and rejects external HTTP, HTTPS CONNECT and WebSocket requests. Remote production URLs are not supported by this adapter. Only reviewed `observe`, `click`, `type`, `upload`, `upload_cancel`, `upload_save_failure`, `seed_legacy_unknown`, `scroll` and `wait` tools are available. Upload is restricted to a named file in a SHA-256-verified synthetic fixture manifest (`ux-synthetic-fixtures.v1`); arbitrary local file paths cannot be selected. Submit buttons, credential fields, password/email/telephone inputs, cross-origin links and arbitrary navigation are blocked. Text entered by a synthetic persona is tracked by hash; reports can say whether it survived without exposing the raw field value. Each action captures a private PNG with SHA-256 and the evidence receipt binds it to the queue operation.

For local web targets, fixtures, storage keys, progress markers, and legacy-seed expectations come from the host-reviewed `fixture-manifest.json` (`ux-synthetic-fixtures.v1`) and optional host `criteria_evaluator` / `legacy_seed_config` adapters rather than hardcoded app state. Flows must not use real logins, real accounts, cookies or external pages.

The model receives the persona, applicable requirements, visible page text, visible/off-screen control metadata, available fixture names and its own prior observations. Screenshot pixels remain local evidence and are not sent to the model in this adapter; this route therefore does not claim visual-model or screen-reader assessment. Browser observations are synthetic test evidence, not human-participant evidence. `real_user_evidence` and `product_ready` remain false.

Example invocation (all paths and IDs must be real, existing values; `--run-root` must be new and the local app must already be running):

    python3 scripts/live_scale_browser.py --library /absolute/path/to/reviewed-persona-library --product-id sample-product --model CONFIGURED_MODEL_ID --provider-name local-gateway --url http://127.0.0.1:4173/ --target "Reviewed owned flow" --goal "The current explicitly reviewed goal" --build-id reviewed-build --build-artifact /absolute/path/to/current-build-manifest.json --fixtures /absolute/path/to/reviewed-fixtures --run-root /absolute/path/to/new-run-root --stages 4 16 --selection /absolute/path/to/stage-4-selection.json --selection /absolute/path/to/stage-16-selection.json --approval-actor "ACTUAL_APPROVING_ACTOR" --consent-reference "REFERENCE_TO_CURRENT_EXPLICIT_EXECUTION_APPROVAL"

The run stores each stage's `ScaleExecution` queue/report, atomically updated per-attempt model usage ledger, zero-budget approval record, screenshots and hashes, fixture manifest digest, counts, failure rate, evidence validation and confirmed browser shutdown. Review all of those before interpreting UX outcomes.
