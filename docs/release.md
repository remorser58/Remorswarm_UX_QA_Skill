# Local release candidate

The distribution installs one `remorsearch-ux-qa/` folder with exactly one
discoverable `SKILL.md`. The engine, workflows, discovery metadata and scripts
keep their normal paths. The original insane-search toolkit is included under
`references/insane-search/`; its SKILL.md is retained unchanged as `SOURCE.md`.
Both the repository-folder installation and the release ZIP include the toolkit.
Users need no separate search-skill installation.

## Install

Users install the whole skill with one command. The builder and checker below
remain maintainer tools for producing and validating the distribution.

```sh
python3 scripts/install.py --target codex
```

Use `--target claude` for `~/.claude/skills/remorsearch-ux-qa`, or
`--destination /path/to/folder` for an explicit path. The installer requires
Python 3.10+, Node.js 22 (>=22 <23) and npm up front, and checks them before
writing anything. It stages the deterministic payload from this builder,
verifies it against `manifest.remorsearch.json`, runs `npm ci` and the
Chromium install inside the staged copy's `drivers/web`, confirms an actual
Chromium launch, verifies the staged payload again after the dependencies land,
and only then activates the destination. A failure at any point before
activation discards the staged copy and leaves an existing installation
unchanged.

The installer refuses symlinked destination paths, destinations overlapping
this repository, the filesystem root, the home directory and unrelated existing
folders. Updating an owned installation first archives the complete previous
folder, including run records and symlinks, as
`remorsearch-ux-qa.backup-<timestamp>.tar.gz` beside the skill folder; hosts
discover folders, not archive files. npm dependencies live inside the
destination's `drivers/web/node_modules`; Chromium downloads into Playwright's
browser cache (`~/Library/Caches/ms-playwright` by default on macOS, overridable
with `PLAYWRIGHT_BROWSERS_PATH`). External accounts stay user prerequisites.

## Build and verify

Use Python 3.10+ on macOS, Linux or WSL. Run from this repository. The default
input is the checked-in toolkit; no network or installed-skill lookup is needed.

```sh
python3 scripts/build_insane_search_bundle.py --output dist/remorsearch-rc
python3 scripts/build_insane_search_bundle.py --verify dist/remorsearch-rc
python3 dist/remorsearch-rc/remorsearch-ux-qa/scripts/remorsearch.py smoke
python3 scripts/build_release_assets.py --output dist/release --commit "$(git rev-parse HEAD)"
(cd dist/release && shasum -a 256 -c SHA256SUMS.txt)
```

`scripts/build_release_assets.py` builds deterministic release ZIPs for both `remorsearch-ux-qa.zip` and `react-design-system.zip`, plus `release-manifest.json` (`remorswarm-release-manifest.v1`) and `SHA256SUMS.txt` used by `.github/workflows/release.yml` and `scripts/install.sh`. Both ZIPs include integrity manifests (`manifest.remorsearch.json` and `manifest.react-design-system.json`) and executable `0o755` permissions on bundled CLI scripts.

Note: `scripts/remorsearch.py` (including `remorsearch.py update`) exists inside generated release ZIPs (`remorsearch-ux-qa.zip`), whereas source/git-copied checkouts invoke `scripts/update_skill.py` directly.

The output contains the installable `remorsearch-ux-qa/` tree and
`remorsearch-ux-qa.zip`. SHA-256 receipts record the original inputs and shipped
content. Identical inputs produce identical ZIP bytes. Verification detects
missing, changed and extra files; it is an integrity check, not a publisher signature.

Maintainers may explicitly replace the toolkit with an existing local input:

```sh
python3 scripts/build_insane_search_bundle.py --base-skill /path/to/insane-search --output dist/remorsearch-custom
```

This option reads the input without changing it. The output keeps Remorsearch as
the installed skill and records whether the input matches the checked-in snapshot.
It retains supplied licenses and does not assign the upstream license to
unrelated or independently modified input.

After extracting the ZIP elsewhere, use the launcher's absolute path from any
working directory:

```sh
python3 /path/to/remorsearch-ux-qa/scripts/remorsearch.py paths
python3 /path/to/remorsearch-ux-qa/scripts/remorsearch.py verify
python3 /path/to/remorsearch-ux-qa/scripts/remorsearch.py research --help
python3 /path/to/remorsearch-ux-qa/scripts/remorsearch.py ref references/insane-search/SOURCE.md phase-0-특수-엔드포인트-인덱스
python3 /path/to/remorsearch-ux-qa/scripts/remorsearch.py ref references/insane-search/references/public-api.md stack-exchange-v23
python3 /path/to/remorsearch-ux-qa/scripts/remorsearch.py smoke
```

An omitted section ID lists headings only. The two reference commands above
load the source index body and an actual linked platform method body.

## Complete local check

Prepare the source tree's pinned web driver dependencies and Chromium using
Node.js 22. An installation made with `scripts/install.py` already carries its
own copy; these commands prepare the checkout the checker copies from:

On Ubuntu 26.04 x64 with Playwright 1.56.1, first export
`PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64` for installation and checks
(the [installation workaround](../README.md#install), not native platform support).
The override does not fix the Node.js 24.16+/26 install hang; keep Node.js 22.

```sh
(cd skills/remorsearch-ux-qa/drivers/web && npm ci && npx playwright install chromium)
python3 scripts/check_release.py --output dist/release-check
```

The checker runs the Python suite, release-file checks, the offline build,
tree/ZIP verification, extraction, relocated CLI and reference reads, both
synthetic smoke workflows, and the Chromium driver selftest suites (`selftest.mjs`, `state_oracle_selftest.mjs`, `temporal_selftest.mjs`) from the extracted
installation. It copies already prepared driver dependencies into that disposable
installation and performs no downloads or install hooks. It verifies package
integrity again after the browser test and compares the candidate with current
inputs. `validation.json` records each check and its log.

The extracted installation also runs `examples/journey/run_fixture.py`. This
starts from an empty directory, prepares three reviewed sample files, reuses two
pre-authored PRD hypotheses, invokes actual local Python adapters and verifies
current report/readback with the original Library preserved. Expected product
verdicts are one failed and one inconclusive; the diagnostic passes only when
those known synthetic outcomes are reported honestly. It is not a browser or
real-user check. Existing diagnostic output is never overwritten.

The same extracted launcher also runs the `--research` variant in a separate
new directory. It exercises the existing offline research input, real merge,
gate, authored export, persistent Library import, reviewed research scope,
current adapter execution and report/readback. Original research bytes, modes
and modification times remain unchanged. Its live-mode contract fields and
source grades belong to invented diagnostic inputs, not actual acquisition or
user evidence. Both original and research diagnostics retain zero product passes.

The browser gate also runs the pure bridge contract tests and the extracted
`examples/journey/run_browser_fixture.py --research` diagnostic. It reuses the
prepared Node 22 / Playwright 1.56.1 / Chromium runtime, starts owned headless
sessions over reviewed synthetic static bytes, and admits native checkpoints,
logs and PNGs through the real saved-persona receipt/audit path. The intentional
input-loss task must fail while the normal control passes. Earlier failure
survives final recovery, and repeated readback preserves the report and originals
without another dispatch. This is actual browser execution of an authored
diagnostic, not actual-user evidence, live-product QA or measured UX improvement.

The output must be a new directory. Failed checks return nonzero. `--skip-web`
produces a partial report with `ready: false`. Synthetic tests establish local
behavior and packaging; live community access, real-user preferences, Figma access
and accessibility certification remain outside this check.

The extracted package also checks `remorsearch.py swarm --help`, runs an eight-session
`examples/agents/scale_fixture.py` diagnostic at concurrency four, and reads it back
through `remorsearch.py swarm status`. These checks use the durable queue and existing
persona/evidence gates with authored model callbacks and generated PNGs. They make
zero model or browser calls. Larger 8/32/100/300 stages and their measured coordinator
cost are recorded separately in `docs/validation/scalable-swarm-results-20261113.md`.
The standard-library queue does not require the optional agent runtime below.

## Optional agent runtime checks

The default installation remains standard-library only. The optional
`requirements-agent.txt` pins LangGraph 1.2.20 and its SQLite checkpoint adapter
3.1.3. Prepare a separate environment; do not install into a user's global
Python or configure paid APIs/telemetry. The package actually compiles/invokes
StateGraph and AsyncSqliteSaver; a missing runtime is an explicit diagnosis.

Run the full check above with that interpreter and
`REMORSEARCH_REQUIRE_AGENT_RUNTIME=1`, then run the extracted installation's
`examples/agents/fixture.py --out NEW` and `scripts/ux_agents.py report`.
The optional gate must not silently skip when the dependency is required.
The owned browser variant accepts already-prepared Node 22, Playwright 1.56.1
and Chromium paths; reuse those runtimes without copying browser/build trees.
It verifies actual PNGs and model/tool-loop integration using authored decisions.
Actual approved-model execution remains a separate acceptance condition.
Document both optional-package-absent diagnosis and installed checks.

The optional Aside transport uses only an existing approved SSH/profile route
and the documented installed CLI REPL. It opens fresh owned temporary Pro
contexts, rejects user drafts and stale responses, and binds model/tool/review
receipts to the real graph. `tests/test_aside_transport.py` exercises protocol
failures without contacting a model. `examples/agents/aside_live.py` separately
records actual model decisions and owned Chromium observations; fixture
decisions and transport probes cannot satisfy its two-persona completion gate.
Default installs still need no new dependency. Aside/SSH/ChatGPT access is
supplied by the approved host, not installed or authorized by this package.

Keep real-run records separate from release regression results. Record both
successful and interrupted live attempts, cleanup receipts, prompt/reply/PNG
hashes and exact source manifests. MacBook coordinator elapsed/maxRSS excludes
remote model memory and aggregate browser memory. The live note diagnostic
does not establish arbitrary-product navigation, allowed public research,
representative personas or measured user benefit. The new transport leaves the
existing browser-run/driver/release-checker sources unchanged.

## Research and distribution boundary

Research plans its questions and discovers candidate URLs, then loads the bundled
search source and appropriate linked method for acquisition. Every selected method
follows Remorsearch's access, provenance and privacy controls. Supported captures
enter the existing reader/ingest checks; unsupported output remains a lead.
A site/run stop stays final across every toolkit method.

The build excludes dependencies, caches, local run state and internal handoff
records. It preserves Remorsearch's MIT license and third-party notices.
`references/insane-search/PROVENANCE.json` records the attributed original snapshot.
The installed original contained no license. The separately retrieved
[upstream MIT license](https://github.com/fivetaku/insane-search/blob/main/LICENSE)
is retained verbatim as `references/insane-search/upstream-LICENSE` and in the
repository at `integrations/insane-search/upstream-LICENSE`. Its retrieval date is
2026-10-02 (Asia/Seoul). Local hash matches prove byte identity with the recorded
snapshot; they do not prove current upstream authenticity or confer rights on a
different maintainer input.

These commands create local artifacts. Publishing, pushing commits and changing
installed skills are separate actions. Internal source-checkout records are
excluded from the distribution.
