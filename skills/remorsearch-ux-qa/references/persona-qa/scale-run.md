# Queued independent persona execution

Contents: user flow; host entry; providers and cost; recovery; evidence; diagnostics.

## User flow

Use this route for a requested larger swarm after inspecting product/PRD intent,
permitted research and the saved persona library. The host resolves approved
files, current persona versions, tool adapter and available model routes. Accept
an ordinary request such as “가입 흐름을 여러 페르소나로 확인해 줘”. Do not ask the
user to write JSON, calculate hashes, choose leases or prepare terminal commands.

1. Select relevant current saved personas. Report the actual available count and
   behavioral coverage. Never clone a profile merely to reach the requested count.
   Follow the existing research/import workflow for missing personas; PRD-only
   hypotheses stay exploratory and research restrictions remain unchanged.
2. Prepare the exact run with `scale_entry.prepare_scale_goal`. Show the number of
   sessions, concurrent calls, provider/model destinations, data scope and maximum
   budget in ordinary language. Distinguish the conservative cost of finishing
   every allowed turn from the smaller run budget, which may stop early.
3. An offline simulation needs no paid-call approval. For live calls, record the
   user's explicit consent to the displayed plan and amount with `Queue.authorize`.
   Development authorization, a test pass and a fixture consent are not paid-call
   authorization. Do not supply a fictional actor or consent reference.
4. Resume the approved plan and invoke `scale_run.execute_scale`. Show completed,
   running, queued, blocked and uncertain sessions, spent/settled/reserved cost,
   and concrete next actions. Count actual completed model calls separately from
   send intents whose outcome is unknown.
5. “잠깐 멈춰” pauses new admission. Already authorized requests can settle and cost
   money; the status still shows them. “이어서 해” resumes the same checkpoints
   and budget. The host handles identifiers and commands.
6. Report task failures and missing observations alongside execution completion.
   Review is the same persona checking its sealed judgment, not an independent
   second rater. A completed queue is neither product readiness nor user benefit.

The total session limit is 1,000 and concurrent external-operation limit is 64;
these are configuration bounds, not measured provider capacity. See the current
validation record for the largest actually exercised stage. Preserve the existing
2–8-context LangGraph/Aside route; it is not automatically scaled or selected.

## Host entry

The core uses Python 3.10+ standard library and an existing local SQLite database.
No LangGraph install, credentials, provider discovery or remote model is implicit.

`prepare_scale_goal(library, run_path, providers, tool_host, tools, ...)` accepts
host-resolved product/target/goal/build, current saved persona IDs, optional exact
provider assignments, `ScaleLimits`, credential scope references, billing reviews
and the tool evidence provenance. It reuses existing PRD/research/persona gates.
The default route assignment is deterministic round-robin over the explicitly
provided providers. There is no fallback to another model or endpoint.

The preview binds persona revisions, tasks, build, tools, code manifest, provider
specifications, source hashes, account scope references and limits. The same goal
and selected roster are reserved once in the library; a new directory cannot
silently reset uncertain effects or the approved budget. A partially created run
is preserved for inspection rather than replaced.

Construct each model adapter as `HTTPProvider` or `CallbackProvider` from
`uxpersonas.swarm_providers`. The tool host follows the existing CallbackHost
model/tool envelope for **tool and close** only. Its source hash, execution mode,
parallel safety and context isolation are part of the plan. Expose only reviewed
read-only or owned-fixture tools. No arbitrary shell/eval/file/network tool belongs
in this generic contract. Concurrent external research collection is not enabled.

Stateless provider requests carry only one persona's scrubbed profile, relevant
requirements, own observations and allowed tools. No other persona result is
included. Each session has its own context ID and evidence directory. The host
must implement actual browser/data/process isolation; these controls are not an
OS/network sandbox. A stateful tool context resumed after restart requires
`host.can_resume(context_id, observations) is True`, a synchronous read-only
attestation that the original owned state exists. Never recreate empty state and
claim it is a resumed session.

## Providers and cost

Implemented HTTP wire formats are OpenAI-compatible Chat Completions (including
an explicitly reviewed DeepSeek endpoint) and Anthropic Messages. Use an exact
model identifier and full HTTPS POST URL. Model aliases that return a different
identity stop instead of silently changing the approved model. No price or model
list is embedded. Haiku requires a reviewed Anthropic model ID; “Luna” remains an
unresolved provider/model label until the host identifies a supported approved
route. Naming it does not establish an integration.

Credentials come from an explicit host callback only at dispatch. The package
never reads environment keys, browser cookies, local tokens or account files.
No redirects, implicit proxy, SDK retry, native server tool, streaming or hidden
provider fallback is enabled. A model returns bounded JSON decisions for the
host's tools. HTTP errors, including 429, may still represent an accepted/billed
request; cooldown is recorded but uncertain requests are never automatically sent
again. This version does not claim provider idempotency or remote reconciliation.

Check both the serialized internal request and the final provider HTTP JSON body
in UTF-8 bytes. Each is capped at 256 KiB (262,144 bytes); protocol fields and
re-escaping the embedded JSON can make the body exceed the cap even when the
internal request fits. The local rejection is `provider_request_too_large`, before
transport. Track disk use, peak RAM and model tokens separately from both counts.

Prices use integer micro-USD per million tokens. The host records a billing review
matching the exact input/output prices and caps, its source and checked date,
and confirms `no_unpriced_features: true`. For live callbacks, also name the
actual destination and non-secret account/credential scope. The input cap must
cover the model's entire accepted input context, not an estimate from characters.
The single input price must cover the highest applicable input tier. The Chat
Completions adapter counts all reported prompt tokens at that rate; cache-hit/miss
metadata does not earn a discount in local accounting.
Every model/review call reserves that full input cap plus maximum output. Actual
reported usage releases the unused reservation. Unknown usage retains it.

Reservations, concurrency and request-per-minute admission commit atomically with
send intent. Global limits, provider limits and cooldowns are durable across
workers/restarts. Budget accounting uses reviewed context/rate assumptions; it
is not an independent verification of a provider's eventual invoice. Unpriced
features must be excluded during host review. Unsupported reasoning/tool/usage
responses quarantine the already sent request and keep its reservation; they do
not prove the provider rejected or did not bill it.

A host records approval with exact plan SHA, actor, actual consent reference,
amount and expiry. The CLI exposes this operator action but cannot authenticate
that a human actually consented; the conversational host must do so. Changed
providers, code, data or amounts require a new reviewed plan. No paid calls are
made by preview, status, pause, resume or approval commands themselves.

## Recovery and evidence

The queue uses SQLite WAL, FULL synchronization, short immediate transactions,
leases and fencing tokens. Do not place its database on a network filesystem or
share it across machines. No transaction spans a network call. Separate runner
processes share limits through the same queue. A worker must still own its lease
when committing a reply, checkpoint or result.

A completed response is saved before its next phase checkpoint. If acknowledgement
or the coordinator is lost, reuse that exact response locally; do not resend.
Lease expiry with no pending intent safely requeues the committed checkpoint.
Expiry, timeout, cancellation or lost connection after intent quarantines the
request, budget and capacity. This is intentionally conservative even if the
process died just before sending. Exactly-once remote execution is not promised.

Cancellation is final for that run and preserves uncertain exposure. To resolve
an uncertain operation, inspect the original host/provider request, record stopped
execution and a receipt reference through `resolve_unknown`. If billing is still
unknown, retain the entire upper bound as conservative settled exposure. This
operation never retries the old call. Keep late results out of current findings.

Model decisions must cite their own observed criteria. Existing PNG decode/hash,
attempt-path, receipt and native-failure checks are reused under the queue's own
lease. A later successful recovery cannot erase earlier input loss. Partial
receipt previews keep already observed failures visible after interruption.
Fixture and live runs cannot mix; generated fixture PNGs do not become browser
captures. First judgments, request/reply digests, usage, provenance and event-chain
hashes are retained. These hashes detect changes, not a dishonest host.

## Installed diagnostics

Maintainers can use a new output directory from any working directory:

~~~sh
python3 /path/to/remorsearch-ux-qa/examples/agents/scale_fixture.py --out NEW --stages 8,32,100,300 --parallel 16
python3 /path/to/remorsearch-ux-qa/scripts/ux_swarm.py preview --run NEW/stage-300/run
python3 /path/to/remorsearch-ux-qa/scripts/ux_swarm.py status --run NEW/stage-300/run
~~~

This executes authored model decisions and generated PNGs through the real queue,
Library, model/tool loop, evidence checks and report. It makes **zero actual model
or browser calls**. It is a scheduler/integration diagnostic, not live small-model
quality, allowed public research, arbitrary-product UX or measured user benefit.
Stages do not prove representative behavioral diversity. Test actual providers
only after a concrete preview and explicit paid-call approval.
