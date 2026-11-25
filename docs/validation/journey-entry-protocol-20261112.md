# Journey entry implementation acceptance — 2026-11-12

This protocol is fixed before executing the new entry path. Base:
`0f623f1055b269249ea77ebec8493b2e203efa8f`. The earlier Peekly run is
evidence to preserve, not a new experiment to execute.

## Defect and intended outcome

The old benchmark `prepare` constructs `Pilot` first. Its constructor requires
an existing product folder and binding, so an empty workspace fails before
preparation. A novice cannot reach the actual persona/result path without
unpublished copying and manifest knowledge.

Provide a host-operated conversational entry backed by one installed CLI
start/status path. The host handles file selection and workspace arguments;
the user supplies the target. The current shipped source adapter is explicitly
the reviewed frozen Peekly copy, not arbitrary repository execution.

## Frozen checks

- An absent or empty destination can prepare the reviewed source without a
  hand-authored manifest, dependencies, installs, browser or product execution.
- One start call verifies copied bytes, revalidates and reuses the exact saved
  persona revisions, and writes a readable MD plus machine-readable JSON.
- The previous failed/inconclusive outcomes and both large-input attempts remain
  unchanged; new execution, UI observation, real-user effect and product readiness
  remain false.
- Repeating start/status is idempotent. A stopped file copy can continue with
  the same source and workspace; changed input or copied content cannot be
  silently replaced. Two callers cannot publish competing workspace contents.
- Missing files, unknown/changed source, nonempty foreign workspaces, traversal,
  symlinks (including parent components), hardlinks, special files, oversized
  inputs, key-shaped content, external PRD/build/evidence paths, expired personas,
  changed evidence and active prior tasks stop with an actionable error.
- Preparation reads only the reviewed file list and exact referenced saved
  artifacts. It never walks/copies node_modules, account exports, credentials,
  claims or arbitrary prior log trees.
- A relocated extracted distribution exposes the same entry. New tests, full
  Python regression, offline smokes and package checks run serially. Missing
  browser validation remains an explicit release limitation.

## Reuse and research decision

Reuse the existing argparse CLI, Library revision/current-source checks, swarm
receipt/report validators, Store locks, canonical hashing and atomic publication.
The existing release builder and source snapshot checker already demonstrate
bounded file inventories and no-follow reads. Python's standard library supplies
descriptor-relative I/O; no new framework, installer, browser harness or model
service is needed. The bundled insane-search methods concern external research,
not local project copying; no DC/YouTube acquisition is attempted.

This is code/CLI workflow work, with no screen composition or Figma operation.
The skill-creator guide informs concise host instructions; this change belongs
to the authorized Remorsearch repository, not a personal-skill installation.

## Evidence discipline

Use fresh owned test directories only. Harness regression fixtures are synthetic
and separate from the preserved actual Peekly core observations. Source-copy and
receipt revalidation do not prove current UI behavior or improved user outcomes.
Do not edit the old protocol, result documents, copied product, or original
Peekly checkout. The externally changed PaywallModal is outside this work.

## Additional generic preparation check, fixed before its first execution

After the host reviews exact relative files in another product, the same entry
must prepare those files without a source manifest or dependency copy. The host
supplies the reviewed selection; the end user supplies only the target. This
source-only path must not import arbitrary saved metadata, invent personas or
claim QA execution. Its input is a separate owned regression fixture, never a
substitute for the frozen Peekly result. Existing criteria above remain unchanged.
