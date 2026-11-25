# Remorsearch UX QA

English | [한국어](README.ko.md) | [PRD · 제품 요구사항](PRD.md)

Remorsearch (*ree-mor-search*, 리모서치) UX QA helps developers improve the UX of
an existing product in Claude Code or Codex. Provide a URL or repository and ask
for improvement. The host agent inspects the product and relevant developer
decisions, discovers questions through baseline QA, researches related user
experiences, applies scoped reversible fixes and replays the affected tasks.
A prepared problem list, persona set or research brief is optional.

## What it does

Four components support that workflow; you do not need to select modes or pass
artifacts between them. A research-only or review-only request keeps its scope.

| Component | What it does | Needs |
| --- | --- | --- |
| **research** | Finds task-specific experiences, workarounds and counterexamples in communities, comments, reviews and official sources; preserves source context and gaps. | A permitted source route. YouTube comments use your own YouTube Data API key (`REMORSEARCH_YOUTUBE_API_KEY`). |
| **persona-qa** | Exercises rendered UI layout scans, completion, state recovery probes, input preservation, errors/recovery, keyboard and accessibility (KWCAG/WCAG) on the real product or iOS XCTest captures. | An accessible product and safe fixtures; the bundled web driver needs Node.js 22 and Playwright. |
| **ergonomics** *(experimental)* | Screens reach, touch, perception, timing and layout with simulated profiles and route-level warning grouping (`--list-threshold`). | Relevant scenarios; model results remain separate from real-device and human evidence. |
| **loop** | Records bounded fixes, strict stdlib PNG/pixel-diff verification, current-build replay, regression and preserved-intent checks. | Host browser/Figma tools and actual receipts. Existing improvement authority is recorded explicitly for scoped local patches. |

The host-agent instructions implement this integrated entry path. The CLI validates
imported evidence, applies bounded local text patches and can execute owned core
tasks through an explicitly reviewed single Python adapter; the host performs
browser actions, Figma work and builds. Whole-product execution from request to
verified improvement still needs a separate live acceptance run. Existing fixture
and component tests do not establish that result.

## Install

Releases are published on `main` and versioned [GitHub Releases](https://github.com/remorser58/Remorswarm_UX_QA_Skill/releases)
(formerly `github.com/remorser58/Remorsearch_UX_QA_Skill`; GitHub redirects old remotes automatically).
See [replay validation and remaining limits](docs/validation/persona-journey-replay-20261111.md)
and the [persona library/task contract](skills/remorsearch-ux-qa/references/persona-qa/persona-library-swarm.md).
Do not overwrite a locally edited installation without preserving it first.

Install one folder into your skills directory. It includes the original
insane-search toolkit as reference material for Remorsearch's research stage;
users do not install a separate search skill. The Python tools need Python 3.10+
on macOS, Linux or WSL and use the standard library and POSIX file locks. If the
default `python3` is older (the macOS system Python is 3.9), the host runs
`python3 scripts/find_runtime.py` from the skill folder. It prints JSON with the
highest supported Python, a Node.js 22 path and any gaps; it installs nothing.

```sh
git clone https://github.com/remorser58/Remorswarm_UX_QA_Skill.git
# Claude Code (personal); use .claude/skills/ inside a project to share it with a team
mkdir -p ~/.claude/skills
cp -R Remorswarm_UX_QA_Skill/skills/remorsearch-ux-qa ~/.claude/skills/
# Codex
mkdir -p ~/.codex/skills
cp -R Remorswarm_UX_QA_Skill/skills/remorsearch-ux-qa ~/.codex/skills/
```

### Auto-update

Existing installations (including copies cloned before `v1.1.0`) can install or upgrade
from verified [GitHub Releases](https://github.com/remorser58/Remorswarm_UX_QA_Skill/releases) with SHA-256 verification, timestamped backups,
local-edit protection, and preserved `drivers/web/node_modules` and `.ux-*` state. On macOS where system `python3` is 3.9, replace `python3` below with the Python 3.10+ binary printed by `scripts/find_runtime.py`. Set `REMORSEARCH_NO_UPDATE_CHECK=1` to opt out of cached background checks.

```sh
curl -fsSL https://raw.githubusercontent.com/remorser58/Remorswarm_UX_QA_Skill/main/scripts/install.sh | bash -s -- --target claude --with-design-system
python3 "$HOME/.claude/skills/remorsearch-ux-qa/scripts/update_skill.py" check
python3 "$HOME/.claude/skills/remorsearch-ux-qa/scripts/update_skill.py" apply --with-design-system
```

Copying the folder completes the skill installation. Maintainer-only packaging
and integrity checks are documented in [build and release checks](docs/release.md).
To also install the optional companion React design-system skill, copy `skills/react-design-system/`
alongside `skills/remorsearch-ux-qa/` (or install from `https://github.com/remorser58/react-design-system-skill`).

The folder contains the Python tools, JSON schemas, demo fixtures, live web
driver, and original search instructions with their references and provenance.

The live web driver (persona-qa and ergonomics on real web pages) also needs Node.js
22 and Playwright. The commands below select the Codex installation. For Claude
Code, set `REMORSEARCH_SKILL_DIR` to `~/.claude/skills/remorsearch-ux-qa`.

```sh
REMORSEARCH_SKILL_DIR="$HOME/.codex/skills/remorsearch-ux-qa"
cd "$REMORSEARCH_SKILL_DIR/drivers/web"
npm ci && npx playwright install chromium
```

Use Node.js 22. With the pinned Playwright 1.56.1, `npx playwright install` hangs after the
download on Node.js 24.16 or later and on Node.js 26
([microsoft/playwright#40724](https://github.com/microsoft/playwright/issues/40724);
Playwright 1.60 works).

On Ubuntu 26.04 x64, Playwright 1.56.1 can fail with
`does not support chromium on ubuntu26.04-x64`. Use its Ubuntu 24.04 build
explicitly, keeping the override in the environment for both installation and
driver runs:

```sh
export PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64
npx playwright install chromium
```

This is a compatibility workaround, not native Ubuntu 26.04 support. Keep Node.js
22; the platform override does not fix the newer-Node installation hang.

## Use

Ask in plain words, or call it by name:

```text
/remorsearch-ux-qa Improve our app UX. URL: https://app.example.test or repository: /path/to/product
/remorsearch-ux-qa 우리 앱 UX 개선해줘. URL 또는 저장소는 여기야.
/remorsearch-ux-qa Find out why people abandon our checkout, from reviews and community posts.
/remorsearch-ux-qa 결제 화면을 처음 쓰는 사용자 페르소나로 QA해 줘. Figma 파일은 이거야.
/remorsearch-ux-qa Check one-handed and colour-blind usability of the signup flow on a Galaxy S24.
/remorsearch-ux-qa 간편결제 실패 경험을 한국어 커뮤니티와 앱 리뷰에서 근거 붙여서 정리해 줘.
```

The agent derives tasks, questions and scenarios from the product, inspects
relevant project documents and accessible intent memory, and preserves confirmed
decisions through replay. It asks only for material missing access or unresolved
decisions and continues unaffected work. Subagents are optional and inherit the
current session's model; you are asked only if you want to choose one.

One request is enough: a URL or repository, optionally a task. The agent first
writes a scoped baseline assessment of the tasks it actually reached, which is
useful on its own, then researches only the questions that assessment raised. It
makes a fix only when one is warranted and replays it. A missing optional source
or tool limits only the affected result. When it prepares a loop packet, the
host writes the observed facts and marks mechanical fields `@auto`;
`python3 scripts/ux_loop.py fill DRAFT.json --evidence-root EVIDENCE [--workspace PRODUCT] --out packet.json`
computes only hashes, digests, run links and fix revisions. It never fills
context, intent, grants, outcomes or severity, and a refused or invalid result is
not acceptance. A passed task shows that task only; it is not whole-product
readiness or measured user benefit.

Default research candidates are 당근 (Karrot), 디시인사이드 (DC Inside), 유튜브 댓글
(YouTube comments), X, 인스타그램 (Instagram) and Threads(쓰레드). The agent selects
those relevant to observed tasks; availability and collection are not guaranteed.
After URL discovery, the bundled insane-search methods remain subject to the
existing access/evidence rules. See the [operational checklist](skills/remorsearch-ux-qa/references/loop/product-improvement.md)
for the product-to-replay workflow and existing plan/bundle/loop commands.

### From an ordinary request to a current local QA report

For larger independent persona runs, the [queued swarm workflow](skills/remorsearch-ux-qa/references/persona-qa/scale-run.md)
connects current saved profiles to a durable provider-neutral model/tool loop.
The host previews session count, destinations, concurrent calls and budget before
recording explicit approval for paid calls. Pause/resume retains checkpoints and
unknown-send cost exposure; authored simulations and live model results remain
separate. The [current validation](docs/validation/scalable-swarm-results-20261113.md)
records exercised scale, failures and remaining live-provider gaps.

Tell the host the approved product folder and user goal. The host reviews the
minimal source, existing personas and permitted execution path; you do not need
to write JSON, copy a repository, manage leases or decide whether exit zero means
success. `start` prepares the reviewed files. For a reviewed owned single Python
adapter, `run` now executes the actual core tasks and joins their observations
to the existing receipt validator and immutable MD/JSON reports. `status` and a
repeated `start` show the current goals, failures, unexecuted criteria and next
action. The host reads that report back in ordinary language.

The report re-reads each stored execution log against its receipt and checks
repeated or contradictory observations for the same PRD obligation across
personas. Repeated evidence is not counted twice; conflicts stay visible and
require review. This is deterministic integrity/consistency checking, not an
independent human or model evaluator, and it cannot prove adapter observations true.

This bounded path reuses current PRD hypotheses and saved research-motivated
synthetic personas. The host explicitly reviews each research location; current
gate, source/capture retention and motivation checks remain mandatory, and the
original research is inspected without cleanup, copying or permission changes.
It creates no personas and has no general browser/service
adapter or OS/network sandbox. Source/Library changes block reuse; uncertain
dispatch is not replayed; recorded results are recovered without new attempts.
Core observations alone remain inconclusive, and no UI or real-user benefit is
claimed. Saved experiment baselines cannot be reset through this entry.

Host details: [start](skills/remorsearch-ux-qa/references/persona-qa/start.md),
[local execution contract](skills/remorsearch-ux-qa/references/persona-qa/local-run.md),
[fixed criteria](docs/validation/journey-run-protocol-20261112.md) and
[validation results](docs/validation/journey-run-results-20261112.md).
The additional [swarm evidence audit protocol](docs/validation/swarm-evidence-audit-protocol-20261112.md)
and [verification record](docs/validation/swarm-evidence-audit-results-20261112.md)
describe receipt/log rechecks, cross-persona duplicate/conflict detection and the
explicit boundary between deterministic consistency checks and independent review.
The installed `examples/journey/run_fixture.py` is a diagnostic with a known
synthetic defect, not an actual-user study. Release validation runs it from the
extracted package and keeps failed/inconclusive product verdicts distinct from
successful software checks.

Research reuse now reaches that same current execution/report path. Claim/source
IDs, gate status, exact persona version and export fingerprints remain distinct
from observed product behavior. See the [research reuse criteria](docs/validation/research-journey-protocol-20261112.md)
and [research reuse validation](docs/validation/research-journey-results-20261112.md).
The extracted `--research` diagnostic uses invented offline source contracts;
it does not repeat the historical public pilot or establish source authenticity.

### Execute a reviewed static browser journey

A separate reviewed static-browser plan now connects those saved personas to the
existing measured Playwright driver. The host derives actions and checkpoints
from the actual reviewed source and user goal. An owned headless Chromium
captures input retention, completion and recovery, with current task/build/persona
bindings, native logs and PNGs checked by the existing receipt/audit path.
An earlier failure survives later recovery; unseen or unvisited targets remain
unobserved. Completed readback does not launch a browser or spend another attempt.

This path supports reviewed owned static files and synthetic inputs. It does not
run an arbitrary product URL, backend, account or the user's browser. One task
scope may pass while real_user_evidence and product_ready remain false.
The installed browser diagnostic has a known input-loss path and normal control:
expected task outcomes are one failure and one pass, not a product-readiness claim.
See the [browser execution contract](skills/remorsearch-ux-qa/references/persona-qa/browser-run.md),
[fixed browser criteria](docs/validation/browser-journey-protocol-20261112.md)
and [browser verification record](docs/validation/browser-journey-results-20261112.md).

### Save researched personas for later QA

The host can import the current validated research export directly into the
versioned Library with `ux_personas.py import-research`. It prepares the exact PRD
mapping and explicit persona IDs, preserving authored scenarios, decisions,
falsifying tests and unknowns. Identical retries keep the revision; changed
existing profiles require the reviewed current revision. The command creates no
task or execution result. See the [research intake contract](skills/remorsearch-ux-qa/references/persona-qa/persona-library-swarm.md#13-import-a-current-research-export-into-the-library)
and [public evidence pilot](docs/validation/public-evidence-pilot-20261111.md).
Public-source capture, synthetic hypotheses, CLI verification and actual-user UX
evidence remain separate.

### Reuse completed journeys on the next build

From the skill folder, the host can prepare the next run without rewriting the
persona/task/criterion/PRD mapping JSON:

```sh
python3 scripts/ux_personas.py replay --library LIBRARY --baseline BEFORE_RUN --run AFTER_RUN --build-id build-2 --artifact build-2.bin --isolation-id fixture-v2 --confirm-starting-state --confirm-isolation
```

The output supplies fixture assignments and the next claim, receipt, report and
comparison commands. It retains exact current persona versions and reviewed
journeys, verifies existing evidence and prepares pending work on changed build
bytes. It copies no results or execution permissions and does not run workers.
The host still performs the journeys and records new observations. Same-pair
retries reuse the reserved destination; active or uncertain baseline work must
remain in its original execution/inspection flow. See the
[replay contract](skills/remorsearch-ux-qa/references/persona-qa/persona-library-swarm.md#12-prepare-the-next-build-without-rewriting-the-journey-plan)
for privacy, isolation, restart and evidence limits.

Journey receipts now validate and save one detached input snapshot and recheck
the original lease after evidence validation and serialization, immediately
before atomic storage. Late results preserve the run and evidence for explicit
inspection and recovery.

## Evidence rules

- Every statement is `observed`, `inferred` or `unknown`; repetition does not make
  inference a fact.
- Synthetic personas and simulated profiles create test situations. They never
  show real-user preference, prevalence or discomfort.
- Community signals are hypotheses until the behaviour is confirmed on the real
  product.
- Research/review requests remain read-only. An improvement request authorizes
  ordinary reversible fixes within its scope; the agent records that existing
  authority in CLI grants. Deployment, publication and real account changes need
  their own authorization.
- Screen composition and UX changes are created in Figma first, with actual file,
  node, version and readback records. Missing access blocks the affected change
  while feasible investigation and QA continue.
- Complete improvement requires current-build replay, adjacent regression and
  preserved-intent checks. If scoped QA finds no reproducible issue, inspection
  can finish without changes; missing required evidence stays incomplete.

Research and QA runs can exchange a machine-readable **evidence bundle**
(`schemas/ux-evidence-bundle.v1.schema.json`). The offline validator checks IDs,
cross-references, permission records, synthetic-persona misuse, unsupported
verified findings and retention dates that have passed. The skill ships a small
valid bundle to try it on:

```sh
python3 ~/.claude/skills/remorsearch-ux-qa/scripts/validate_bundle.py bundle.json
python3 ~/.claude/skills/remorsearch-ux-qa/scripts/validate_bundle.py ~/.claude/skills/remorsearch-ux-qa/examples/bundle/minimal.json
```

## Reading public pages

Research and persona-qa read what anyone can read without an account.

- **Tools.** The skill uses the best browser tool your agent host has: first an
  agentic tool that drives your own browser (Aside, Claude in Chrome, the Claude
  app's built-in browser), then an automation browser (Playwright MCP, Chrome
  DevTools MCP, or the bundled page reader `read_page.mjs`; the bundled live web
  driver tests your product, it does not read community pages), then its own
  reader, and last plain web search and fetch, whose results are leads only. It
  records which tool read each source.
- **The reader** (`scripts/ux_research.py`) climbs a short ladder only as far as
  needed: an official feed or API, one honestly identified request, the site's
  own mobile or feed version, then a real-browser render.
- **Stops.** It stops at logins, paywalls, member-only groups, age checks, human
  checks such as CAPTCHAs, bot blocks and "checking your browser" pages (it
  never waits one out), robots.txt and AI or TDM opt-outs, rate limits and
  removed posts, and reports each as a coverage gap. A check, a block or a rate
  limit stops the whole site for the run, and no browser render follows. It also
  stops where a
  platform's published terms or an official notice restrict automated collection
  or AI use (`terms_restricted`), and it honours robots.txt rules for AI agents
  that fetch pages on a user's behalf. It never reads search results pages. It
  never disguises itself, and it reads one page at a time per host, at least 8
  seconds apart by default, within a budget.
- **Privacy.** Quotes are short, authors become salted keys, and temporary page
  text is kept outside your project and deleted when the run closes. Phone
  numbers, e-mail addresses, ID numbers, card and account numbers and IP addresses
  are removed before the agent sees the text. Signed-in reading happens only in
  communities you authorise for the run, and keeps summaries only.

Details: [`public-page-access.md`](skills/remorsearch-ux-qa/references/research/public-page-access.md).

## Korean research

For a Korean product, Korean-speaking users or a report in Korean, research mode
also follows the Korean pack, which starts at
[`overview.md`](skills/remorsearch-ux-qa/references/research/korea/overview.md).
persona-qa adds the accessibility notes in
[`kwcag-2.2.md`](skills/remorsearch-ux-qa/references/persona-qa/kwcag-2.2.md). The
pack is written in Korean and adds:

- a map of 27 Korean channels: how public each is, the legitimate way to read it,
  the stops to expect and its terms status;
- Korean query craft and user-language reading (초성체, sarcasm, register);
- disclosure and review-reward markers, and the grading rules that follow from them;
- provenance cards and population frames for Korean statistics;
- a legal checklist (not legal advice) and a report template in Korean;
- KWCAG 2.2 and WCAG 2.2 accessibility results, reported apart.

**Terms stops.** Restricted hosts and their short links stop before any request.
Evidence status (`reported` or `confirmed`) is separate from `lift_requires`:
`never` prohibits a page lift; `written_permission` needs your current terms
check and applicable prior written permission; `terms_check` needs your current
check. Every covering entry must be lifted separately, with at most 10 documents
per entry across its hosts. Open-run commands revalidate the 365-day limit and
`effective_from`; older runs must restart. An agent never records a user's check.

YouTube pages, Meta, TikTok, Clien and App Store pages/feeds use `never`.
DC Inside, Naver, Coupang, X, Daangn and Reddit require written permission; the
Naver Cafe notice has its own terms URL and needs a separate current user check
and applicable prior written permission. YouTube keeps its
official-only Data API route. HN pages use `never`, and its official-only API
reports `official_route_unavailable` until an adapter exists. X oEmbed is removed
after an unauthenticated HTML response on 2026-09-30; no retirement notice was
found. Own-app App Store Connect exports remain `team_provided`.
See [the entries and checks](skills/remorsearch-ux-qa/references/research/public-page-access.md#171-entries).

**YouTube comments** come only through the YouTube Data API, with your own key in
the environment variable `REMORSEARCH_YOUTUBE_API_KEY` (`YOUTUBE_API_KEY` is
accepted as an alias). Keys are read from environment variables only, never from a
file. A missing key is a coverage gap and a question to you, never a reason to read
the page another way. As the key holder you follow YouTube's API terms and
developer policies. [Developer Policies III.E.4.d](https://developers.google.com/youtube/terms/developer-policies), read on 2026-09-30,
requires stored Non-Authorized Data to be deleted or refreshed after 30 calendar days.
The reader stamps each API item with `retention_until`, 30 days
after the fetch, and deletes its own page text when the run closes; you must delete
or re-read each item kept in bundles or reports by its `retention_until`
(`validate_bundle.py` reports one that is past it), and no bundle items are deleted
automatically yet.

**Plain limits.** Most Naver posts cannot be read by the agent. The automation
restrictions in [Naver’s terms](https://policy.naver.com/rules/service.html) and the
[cafe notice dated 2026-08-25](https://notice.naver.com/notices/cafe/33743) were read from the primary pages on 2026-10-01.
2026-08-31 was the press date. Each entry requires its own user check and applicable
prior written permission under `lift_requires: written_permission`. Naver and Kakao
search APIs stay off until the owner reads their current terms. Coverage gaps are
filled with team data, other channel families, surveys and interviews. Directly read
facts are marked 관찰됨; facts not reached in the primary source remain 미확인(...).
`verified_at` stays null until a person reads the primary page.

## Repository layout

```text
VERSION                      release version source
scripts/install.sh           one-command release installer/upgrader
scripts/build_release_assets.py release ZIP & manifest builder
skills/remorsearch-ux-qa/    the installable skill (copy this folder)
  VERSION                    installed skill version
  SKILL.md                   entry point: modes, shared rules, tools
  references/                mode workflows and reference material
    research/korea/          Korean research pack (in Korean): platform map, query craft, markers, statistics, legal checklist, report template
    persona-qa/kwcag-2.2.md  KWCAG 2.2 and WCAG 2.2 notes for Korean products (in Korean)
  scripts/                   CLIs: validate_bundle, ux_loop, ux_research, ergo_qa, update_skill, benchmarks
  uxloop/ uxresearch/        Python packages behind the loop CLI and the public-page reader
  ergoqa/ schemas/           ergonomics package and the JSON schemas used by the CLIs
  drivers/web/               live Playwright driver (Node.js)
  examples/loop/             synthetic demo fixture for the loop CLI
skills/react-design-system/  optional companion skill for React + Vite design systems, Base UI, Motion, Storybook, Safe Area, and TanStack/Zustand/ky
tests/                       unit tests and fixtures
benchmarks/                  blind benchmark suites with answer keys
docs/                        design notes, human-factors research, validation records
README.md, README.ko.md      this page in English and in Korean
```

Companion skill: [react-design-system](skills/react-design-system/SKILL.md) (standalone mirror at [react-design-system-skill](https://github.com/remorser58/react-design-system-skill)).

## Development

From a repository checkout:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 skills/remorsearch-ux-qa/scripts/smoke_loop.py
(cd skills/remorsearch-ux-qa/drivers/web && npm ci && node selftest.mjs)
python3 skills/remorsearch-ux-qa/scripts/ergo_bench.py --suite benchmarks/heldout-mixed --out .ergo-bench/heldout
```

The loop CLI's full reference, including resume, exit codes and trust limits, is
in [`references/loop/cli.md`](skills/remorsearch-ux-qa/references/loop/cli.md).

The tests never reach the network. The reader tests serve their pages from a local
server on 127.0.0.1.

Run the complete package check with Python 3.10+ and the pinned web
driver dependencies installed. The report records test results and verifies the
extracted ZIP from another working directory. See [release checks](docs/release.md).

```sh
python3 scripts/check_release.py --output dist/release-check
```

The [2026-11-11 controlled UX comparison](docs/validation/experiments/persona-workflow-20261111/README.md)
found three supported seeded defects in both conditions, but the persona condition
was incomplete after a connection loss. It does not establish a completed tie or
superiority. The saved/reused persona workflow, shortcomings and minimized
execution evidence are recorded. The [post-trial benchmark launcher](benchmarks/persona-effectiveness/RUNNING.md)
provides a portable local reproduction path; published cases are development fixtures,
not fresh held-out validation.
The [precommitted PE-2 comparison](docs/validation/experiments/persona-workflow-pe2-20261111/README.md)
completed all six cases under both budgets with the same three supported defects
and no clean-control false alarms. This bounded tie does not establish superiority,
real-user benefit or equal coverage.

## Limits

- Live browser research (Aside or another agentic browser), Figma and browser
  collection for the loop mode are provided by you or your agent host; the loop
  CLI imports their receipts and never launches them.
- The reader honours robots.txt and AI or TDM opt-outs and stops at bot blocks
  and browser checks, so some sites end up as coverage gaps. Renders never click, so long comment threads and "more reviews"
  lists are only partly read.
- Many Korean platforms restrict automated collection, so DC Inside, Naver and
  Coupang end as coverage gaps unless you record a terms check with their written
  permission, and YouTube is read
  only through its API with your key. The Korean pack is not legal advice.
- The ergonomics mode's thumb-reach model is uncalibrated, and its benchmark suites
  are small and authored by agents. Treat its findings as screening, not
  certification. See `docs/validation/`.
  The [recorded held-out evaluation](docs/validation/experiments/heldout-2-results.md)
  missed its confirmatory noise limit (1.75 P0–P2 units per clean scenario;
  limit 0.35) and condition-identification target. Later fixes do not establish
  that those original targets now pass; review findings before acting on them.
  This checkout includes only `benchmarks/heldout-2/audience/*.json`, not that
  evaluation's fixtures, scenarios or answer key. Its published results cannot
  be reproduced from this checkout; audience files are not a runnable suite.
- Only Chromium device emulation is exercised by the web driver; no real iOS
  Safari, native apps or real devices.

## License

MIT, see [`LICENSE`](LICENSE). Third-party material and references are listed in
[`THIRD_PARTY_NOTICES.md`](skills/remorsearch-ux-qa/THIRD_PARTY_NOTICES.md).

Credits: the public-page reader and the research gate were designed after studying
fivetaku's [insane-search](https://github.com/fivetaku/insane-search) and
[insane-research](https://github.com/fivetaku/insane-research) (both MIT). The original insane-search toolkit is bundled as reference material and invoked
during research acquisition. Its bytes, provenance and upstream license are
preserved. The gate draws ideas from insane-research; none of its code or text is included. The Korean pack and this README's bilingual layout also draw
ideas from [K-skill](https://github.com/NomaDamas/k-skill) (MIT), DaleSeo's
[korean-skills](https://github.com/DaleSeo/korean-skills) (MIT),
[SoDam-Persona-Codex](https://github.com/sodam-ai/SoDam-Persona-Codex) (Apache-2.0)
and fivetaku's [gptaku_plugins](https://github.com/fivetaku/gptaku_plugins) (MIT),
again ideas only. Platform names are descriptive; there is no affiliation with
any of them.
