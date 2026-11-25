# Prepare authorized native research

Use this path for original team research that the user is authorized to provide:
interviews, surveys, usability tests, support records, product analytics and
product briefs. An authorized own-app console export keeps its console route
and app identity. This is not an alternate reader for restricted websites.
Copied posts, screenshots, browser/DOM captures and third-party API dumps do not
become native research by being pasted into a document. DC permission, YouTube
Data API provenance and all other access rules still apply.

## Collect the facts, not a user-authored JSON exercise

Inspect the supplied material and existing permission records. The assistant
prepares the structured draft from those actual facts. Ask only for missing
authority or information that cannot be recovered. Never invent permission,
producer review, dates, sampling, participant counts or a passing gate.

The producer/owner must supply already sanitized, reviewed UTF-8 .txt/.text
inside the research run with mode 0600. This command does not scrub raw exports.
Preserve only task-relevant text; no individual identities or protected personal
attributes. Every import needs:

- Original source type and producer; producer_stake is official, independent or
  vendor as appropriate, not an inferred independence rating.
- Acquisition kind, product, applicable app ID/territory, actual export time and
  observation period, and a reference to actual scoped permission.
- Producer/owner sanitization method, review time, removed categories and true
  review attestation supplied by that producer/owner.
- Retention deadline where required. Expired material must not be re-imported.
- Native origin and confirmation of actual permission. These are declarations,
  not independent legal verification by the engine.

Allowed native source types are product_analytics, survey, interview,
usability_test, support_tickets, product_brief and expert_judgment. Use
authorized_own_app_console only for app_store_reviews acquired through
store_console_export with matching app permission. Preserve source meaning:
a vendor brief is not neutral user research, and a ticket count is not a
representative population estimate.

The following is a structural template, deliberately not executable evidence.
Replace placeholders from genuine records. False confirmations must remain
false until the corresponding fact is established; the command refuses them.
All objects use exact fields. IDs and hashes are computed, not authored.

```json
{
  "schema_version": "ux-native-import-draft.v1",
  "imports": [{
    "artifact_ref": "reviewed.txt",
    "source_type": "interview",
    "producer_org": "ACTUAL_PRODUCER",
    "producer_stake": "vendor",
    "origin": {"kind": "native_team_data", "permission_confirmed": false},
    "acquisition": {
      "kind": "document",
      "product": "ACTUAL_PRODUCT",
      "app_id": null,
      "territory": null,
      "exported_at": "ACTUAL_EXPORT_TIME",
      "period_start": "ACTUAL_PERIOD_START",
      "period_end": "ACTUAL_PERIOD_END",
      "permission_ref": "ACTUAL_SCOPED_PERMISSION_RECORD"
    },
    "sanitization": {
      "performed_by": "producer",
      "method": "producer_redaction",
      "reviewed_at": "ACTUAL_REVIEW_TIME",
      "removed_categories": ["ACTUAL_REMOVED_CATEGORIES"],
      "review_attestation": false
    },
    "retention_until": null
  }]
}
```

## Preflight and prepare

Run from the skill folder. Initialize the ordinary research brief and plan,
including honest gaps for unavailable sources. No fake search call is needed
for native-only evidence. Save the draft privately, then:

```sh
python3 scripts/ux_research.py prepare-imports --run RUN --draft RUN/native-draft.json --check-only
python3 scripts/ux_research.py prepare-imports --run RUN --draft RUN/native-draft.json
```

Preflight checks the open run, typed metadata, origin declarations, actual
private bytes, retention, timestamps and existing privacy/injection rules.
It writes no prepared output or gate; the common run lock may be created.
Preparation writes a content-addressed private directory containing
sanitized-imports.json and preparation.json. Use the exact returned path.
Identical preparation is idempotent. Changed or incomplete output is preserved
and refused, not overwritten. Neither command creates claims or personas,
changes support status, runs a gate or verifies the truth of permission.

Continue the existing audience-pipeline.md workflow: author typed source,
excerpt and claim records, merge with the returned --imports path, review
summaries and counter-evidence, and run the unchanged gate. A process pass alone
does not supply exportable claims. Use current eligible claim cards for
persona-starter, export-personas and the versioned library described in
../persona-qa/persona-library-swarm.md. Keep each test model synthetic and
separate its evidence from inferred behavior, unknowns and test conditions.

## Recovery and reuse

Diagnostics identify a zero-based import index and safe schema field path,
such as imports[1].acquisition.exported_at, without echoing rejected values or
unknown keys. Unconfirmed producer review gets a distinct unreviewed_import
instruction, not advice to set a flag just to pass. Privacy/injection errors
identify the affected import; the assistant must not repair or bless its text.

- Missing or invalid metadata: recover actual values from the producer/owner;
  do not choose plausible defaults or change source type to get a pass.
- Missing permission or review: preparation is blocked until real scoped
  authorization and producer/owner review exist. Other product QA can continue.
- Privacy/injection refusal: return the artifact to the producer/owner for
  sanitization and review. Refused text is not echoed or automatically repaired.
- Invalid paths, modes or raw file format: stage only the already-reviewed
  private text inside the run. Preserve originals; do not convert raw personal
  exports into a purportedly reviewed artifact.
- Expired or future-dated input: obtain current permitted material or correct
  a genuinely mistaken date from records. Never extend retention or backdate
  an action that has not happened.
- Preparation conflict: inspect and preserve prior output. Resolve the
  incomplete/edited attempt explicitly, rather than overwriting provenance.

Reuse validates the committed evidence snapshot and current source annotations,
gate and retention. It does not re-acquire the original file or independently
re-verify legal rights. Original corrections require new prepare → merge → gate
and persona review; editing the original .txt alone does not change an existing
capture. Explicit source withdrawal blocks reuse and affected assignments.
Blocking reuse is not cleanup. An uncommitted retention change makes library
prune report a blocker, not delete from an unverified mirror. For a confirmed
withdrawal, explicitly retire the affected persona; inspect research-run and
exported-copy retention separately. Keep non-content audit history where allowed.

Report actual provision separately from capability: without genuine supplied
research this is an available route, not completed research. Offline invented
fixtures can verify these mechanics, not participant behavior or UX benefit.
