# Swarm artifact retention and storage management

Use this guide during Persona QA capture, at a checkpoint, and before handoff. It sets a capture and review procedure, not a cleanup command. A storage limit is not permission to delete evidence or rerun a job.

## Before starting

- Set a per-run budget for disk, capture count and duration, and a separate floor for free space. Record the scope, owner, capture purpose and required baseline, recovery and replay evidence. Size the budget using a short representative capture, expected concurrency and room to finalize in-flight captures. Check the destination volume, not just the workspace total.
- Prefer targeted screenshots and step logs for the transitions they can prove. Record video or an expanded trace when motion, timing, gesture or an intermittent failure requires it. Preserve the only usable recording of that behavior. Measure actual growth; a serialized receipt or model payload limit is not a disk limit.
- Capture only what the approved task needs. Redact private inputs before capture where possible. A recorder's output, temporary copies and a final report can have different access and retention requirements. Use existing access and evidence rules; do not send raw captures to a model or publish them simply to save space.

## During the swarm

1. At a natural settled checkpoint, record remaining disk space, in-flight capture producers, queue state, and where the evidence is referenced. Reduce optional future capture or stop admitting new tasks if the budget is at risk. Let owned writers settle through the supported workflow; if settlement is uncertain, preserve the run and explain the limit.
2. Treat a screenshot as final only after its receipt and SHA-256 can be read back. If Playwright video is enabled, successful awaited context closure is needed to finalize the video. For a manually collected Playwright trace, wait for tracing stop to succeed. Check the exact promised output exists and is readable; a close request, an apparent file age, or a closed page is not verification. Never interrupt an active writer to free disk.
3. Read the durable checkpoint, receipt and available manifests back from disk. Check current and prior reports, evidence links, queued work, review/export obligations and rollback references that apply to the run. Missing, stale, hashed-but-unreadable or conflicting references leave the decision unknown. A matching hash on two files does not prove that both paths are interchangeable.
   - Keep queue databases with their WAL/SHM/journal files, existing locks and checkpoints. Do not repair, compact or create locks during a storage inventory.
   - Keep an ergonomic recording's `run.json` together with the referenced snapshots, profile and logs. A run manifest can cause a recorder to skip a job while a missing snapshot silently reduces the evidence available for analysis. Check the referenced files, not just the manifest. This rule also covers receipt-linked release bundles and extracted fixtures.
4. Keep an inventory only: run and artifact ID, relative path, byte count, hash when safe, writer/queue state, references checked, classification and reason. Show estimated reclaimable bytes separately. Do not count unknown items, linked paths with unverified allocation, or speculative duplicates as reclaimed space.

For an authorized existing swarm run, inspect queue and evidence status with `python3 skills/remorsearch-ux-qa/scripts/ux_swarm.py status --run "$RUN" --format json` from the repository root. Status is not a storage scan. A paused queue stops admitting new work but does not prove that current writers have settled. An unassessed or invalid receipt is not cleanup evidence.

## Classify without deleting

| Class | Examples | Action |
| --- | --- | --- |
| Preserve | Active or uncertain worker, pending capture, queue/ledger, checkpoint, required input or receipt; cited screenshot, recording, trace, verdict or second-pass proof; original needed for rollback | Keep in place. Do not retry, rewrite or move to make the inventory pass. |
| Candidate for owner review only | In-scope generated scratch/export duplicate with known writer stopped, readable canonical copy, verified identity and no current, historical or pending path reference | List the reason and bytes. This guide runs no removal and grants no permission. |
| Unknown | Symlink or external path, incomplete reference list, interrupted writer, failed checksum, ambiguous owner or missing retention decision | Preserve; show the unresolved condition. |

Do not use research/Persona Library retention or pruning as a disk cleanup shortcut. It concerns source retention decisions bound to committed research state and is separate from QA capture scratch. Persona Library prune can retire profile revisions even when it returns a partial result; it is not a preview. Do not use age, count, unattended time, a successful-looking run, or a filename pattern as authority.

This storage procedure cannot extend data consent, license terms or source retention. Follow the existing [access card](../shared/access-card.md) and [persona library retention rules](persona-library-swarm.md) for sensitive or expired research inputs. Do not apply a target app's own data expiry rules to its QA evidence.

## Handoff checks

- Verify referenced files and receipts still read back. Check that an interrupted run's original checkpoint remains readable. Resume is a separate state-changing operation and is only possible when the existing run and host satisfy their resume contract. Do not restart unknown/uncertain work or delete a cited recording to test the procedure.
- Record bytes observed versus bytes proposed as candidates and amounts actually removed (zero for an inventory-only review), plus any non-covered artifacts. For a separate authorized cleanup, recheck ownership, path, references and file identity immediately before acting. Permanent removal requires explicit confirmation; do not weaken normal recovery, consent, or retention restrictions.
- See [Playwright video finalization](https://playwright.dev/docs/videos) and [Playwright Tracing](https://playwright.dev/docs/api/class-tracing) for capture behavior. These sources describe those optional features, not a claim that every Remorsearch run records video or traces.
