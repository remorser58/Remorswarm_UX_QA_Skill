"""Selective reversal of existing loop fixes; no Git, model, or host execution."""
from __future__ import annotations

from pathlib import Path

from .io import ContractError, GateStop, code_snapshot, digest, now
from .patching import finish_intent
from .storage import checkpoint_bytes, event, load, lock, save


def improvement_rows(state):
    fixes = {row["id"]: row for row in state["packet"]["fixes"]}
    findings = {row["id"]: row for row in state["packet"]["bundle"]["records"]["findings"]}
    reverted = {fid for row in state.get("rollback_events", []) for fid in row["fix_ids"]}
    applied = {row["fix_id"]: row for row in state["applied_fixes"]}
    result = []
    for fid, receipt in applied.items():
        fix = fixes[fid]
        available, limit = _availability(receipt, fix)
        result.append({
            "fix_id": fid,
            "finding_ids": fix["finding_ids"],
            "reason": fix["rationale"],
            "expected_effect": fix["expected_effect"],
            "replay_ids": [replay["id"] for replay in state["packet"]["replays"]
                           if any(round_["id"] == replay["round_id"] and fid in round_["fix_ids"]
                                  for round_ in state["packet"]["rounds"])],
            "scenario_ids": sorted({findings[x]["scenario_id"] for x in fix["finding_ids"]}),
            "changed_paths": fix["changed_paths"],
            "patch_artifact_id": fix["patch_artifact_id"],
            "figma_id": fix["figma_id"],
            "status": ("reverted" if fid in reverted else
                       "accepted" if fid in state["accepted_fix_ids"] else "applied_unverified"),
            "rollback_available": fid not in reverted and available,
            "rollback_limit": limit,
        })
    return result


def _snapshot(receipt, fix):
    value = receipt.get("rollback_snapshot")
    if not isinstance(value, dict):
        raise GateStop("blocked", "Original contents unavailable for legacy fix " + fix["id"])
    body = {k: v for k, v in value.items() if k != "sha256"}
    if (set(body) != {"before_files", "after_files"} or value.get("sha256") != digest(body)
            or not isinstance(body["before_files"], dict)
            or not isinstance(body["after_files"], dict)
            or set(body["before_files"]) != set(fix["changed_paths"])
            or set(body["after_files"]) != set(fix["changed_paths"])):
        raise ContractError("Invalid rollback snapshot for " + fix["id"])
    for files in body.values():
        if any(v is not None and not isinstance(v, str) for v in files.values()):
            raise ContractError("Rollback supports only recorded UTF-8 text files")
    return body


def _availability(receipt, fix):
    try:
        snapshot = _snapshot(receipt, fix)
    except (ContractError, GateStop) as exc:
        return False, str(exc)
    if len(fix["changed_paths"]) != 1:
        return False, "Multi-file atomic publication is unavailable; no rollback write is permitted."
    if any(value is not None and snapshot["after_files"][name] is None
           for name, value in snapshot["before_files"].items()):
        return False, "Deleted-file permissions/metadata were not recorded; automatic recreation is blocked."
    return True, None


def _plan(state, fix_ids):
    if (not isinstance(fix_ids, list) or not fix_ids
            or any(not isinstance(fid, str) for fid in fix_ids)
            or len(fix_ids) != len(set(fix_ids))):
        raise ContractError("Select one or more distinct applied improvement IDs")
    if state["pending_intent"] is not None:
        raise GateStop("blocked", "Reconcile the pending forward patch before rollback")
    fixes = {row["id"]: row for row in state["packet"]["fixes"]}
    undone = {fid for row in state.get("rollback_events", []) for fid in row["fix_ids"]}
    active = [row for row in state["applied_fixes"] if row["fix_id"] not in undone]
    selected = set(fix_ids)
    if not selected <= {row["fix_id"] for row in active}:
        raise ContractError("Selection includes an unknown or already reverted improvement")
    closure = set(selected)
    for i, receipt in enumerate(active):
        fid = receipt["fix_id"]
        if fid not in closure:
            continue
        paths = set(fixes[fid]["changed_paths"])
        for later in active[i + 1:]:
            if paths & set(fixes[later["fix_id"]]["changed_paths"]):
                closure.add(later["fix_id"])
    if closure != selected:
        raise GateStop("blocked", "Select dependent later improvements explicitly: "
                       + ", ".join(sorted(closure - selected)))
    workspace = Path(state["workspace"])
    before = code_snapshot(workspace, state["packet"]["goal"]["code_paths"])
    after = dict(before)
    ordered = [row for row in active if row["fix_id"] in selected]
    for receipt in reversed(ordered):
        fid = receipt["fix_id"]
        snapshot = _snapshot(receipt, fixes[fid])
        if any(value is not None and snapshot["after_files"][name] is None
               for name, value in snapshot["before_files"].items()):
            raise GateStop("blocked", "Deleted-file permissions/metadata are unavailable; no files were changed")
        for name, expected in snapshot["after_files"].items():
            if after[name] != expected:
                raise GateStop("blocked", "Concurrent or unrecorded edit prevents rollback: " + name)
            after[name] = snapshot["before_files"][name]
    changed = sorted(name for name in before if before[name] != after[name])
    if len(changed) > 1:
        raise GateStop("blocked", "Atomic multi-file rollback is unavailable in the existing host; no files were changed")
    public = {
        "schema_version": "ux-rollback-preview.v1",
        "run_id": state["run_id"],
        "fix_ids": [row["fix_id"] for row in ordered],
        "changed_paths": changed,
        "before_revision": digest(before),
        "after_revision": digest(after),
        "checkpoint_sha256": digest(state),
        "requires_code_write": "code_write" not in state["permissions"],
        "revalidation_required": True,
        "product_complete": False,
        "atomic_scope": "single_file" if changed else "no_content_change",
    }
    public["confirmation_sha256"] = digest(public)
    intent = {"fix_id": "rollback", "before_hashes": {k: digest(v) for k, v in before.items()},
              "after_files": after, "after_revision": digest(after), "changed_paths": changed}
    return public, intent


def validate_pending(state):
    """Validate a persisted recovery record before it can drive file writes."""
    pending = state.get("pending_rollback")
    if pending is None:
        return
    if not isinstance(pending, dict) or set(pending) != {"preview", "intent", "actor", "reason", "authorization_event"}:
        raise ContractError("Invalid pending rollback record")
    preview, intent = pending["preview"], pending["intent"]
    preview_keys = {"schema_version", "run_id", "fix_ids", "changed_paths", "before_revision",
                    "after_revision", "checkpoint_sha256", "requires_code_write",
                    "revalidation_required", "product_complete", "atomic_scope", "confirmation_sha256"}
    if not isinstance(preview, dict) or set(preview) != preview_keys:
        raise ContractError("Invalid pending rollback preview")
    if (preview["schema_version"] != "ux-rollback-preview.v1" or preview["run_id"] != state["run_id"]
            or preview["confirmation_sha256"] != digest({k: v for k, v in preview.items() if k != "confirmation_sha256"})):
        raise ContractError("Pending rollback preview binding changed")
    ids = preview["fix_ids"]
    applied = {row["fix_id"] for row in state["applied_fixes"]}
    reverted = {fid for row in state.get("rollback_events", []) for fid in row["fix_ids"]}
    if (not isinstance(ids, list) or not ids or any(not isinstance(fid, str) for fid in ids)
            or len(ids) != len(set(ids)) or not set(ids) <= applied - reverted):
        raise ContractError("Invalid pending rollback selection")
    fixes = {row["id"]: row for row in state["packet"]["fixes"]}
    receipts = {row["fix_id"]: row for row in state["applied_fixes"]}
    for fid in ids:
        snapshot = _snapshot(receipts[fid], fixes[fid])
        if any(value is not None and snapshot["after_files"][name] is None
               for name, value in snapshot["before_files"].items()):
            raise ContractError("Pending rollback cannot recreate deleted-file metadata")
    keys = {"fix_id", "before_hashes", "after_files", "after_revision", "changed_paths"}
    scope = set(state["packet"]["goal"]["code_paths"])
    if (not isinstance(intent, dict) or set(intent) != keys or intent["fix_id"] != "rollback"
            or not isinstance(intent["before_hashes"], dict) or set(intent["before_hashes"]) != scope
            or not isinstance(intent["after_files"], dict) or set(intent["after_files"]) != scope
            or any(v is not None and not isinstance(v, str) for v in intent["after_files"].values())
            or not isinstance(intent["changed_paths"], list) or len(intent["changed_paths"]) > 1
            or any(not isinstance(v, str) or v not in scope for v in intent["changed_paths"])
            or intent["changed_paths"] != preview["changed_paths"]
            or intent["after_revision"] != digest(intent["after_files"])
            or intent["after_revision"] != preview["after_revision"]):
        raise ContractError("Invalid pending rollback file intent")
    import re
    if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
           for v in intent["before_hashes"].values()):
        raise ContractError("Invalid pending rollback content hash")
    if any(not isinstance(pending[k], str) or not pending[k].strip() or len(pending[k]) > 1024
           for k in ("actor", "reason", "authorization_event")):
        raise ContractError("Invalid pending rollback attribution")


def _paths(checkpoint):
    if checkpoint.suffix == ".lock" or ".git" in checkpoint.parts:
        raise ContractError("Unsafe checkpoint path")
    if any(path.is_symlink() for path in (checkpoint, *checkpoint.parents)):
        raise ContractError("Checkpoint path cannot traverse symlinks")
    state = load(checkpoint)
    workspace = Path(state["workspace"])
    if any(path.is_symlink() for path in (workspace, *workspace.parents)):
        raise ContractError("Workspace path cannot traverse symlinks")
    return workspace


def preview(checkpoint: Path, fix_ids: list[str]) -> dict:
    workspace = _paths(checkpoint)
    with lock(workspace / ".ux-loop" / "workspace.lock"), lock(checkpoint.with_suffix(".lock")):
        state = load(checkpoint)
        if state["workspace"] != str(workspace.resolve()):
            raise ContractError("Checkpoint workspace changed")
        if state.get("pending_rollback"):
            pending = state["pending_rollback"]
            if set(fix_ids) != set(pending["preview"]["fix_ids"]):
                raise GateStop("blocked", "Resume the existing rollback selection first")
            return {**pending["preview"], "pending": True}
        result, _ = _plan(state, fix_ids)
        result["selection"] = {"kind": "confirm", "label": "선택한 개선 되돌리기",
                               "requires_explicit_response": True,
                               "silence_is_approval": False}
        return result


def apply(checkpoint: Path, fix_ids: list[str], confirmation: str, *, actor: str, reason: str) -> dict:
    if (not isinstance(actor, str) or not actor.strip() or len(actor) > 1024
            or not isinstance(reason, str) or not reason.strip() or len(reason) > 1024):
        raise ContractError("Rollback requires an explicit actor and reason")
    workspace = _paths(checkpoint)
    with lock(workspace / ".ux-loop" / "workspace.lock"), lock(checkpoint.with_suffix(".lock")):
        state = load(checkpoint)
        if state["workspace"] != str(workspace.resolve()):
            raise ContractError("Checkpoint workspace changed")
        if "code_write" not in state["permissions"]:
            raise GateStop("blocked", "Rollback needs an existing explicit code_write grant")
        pending = state.get("pending_rollback")
        if pending is None:
            proposal, intent = _plan(state, fix_ids)
            if confirmation != proposal["confirmation_sha256"]:
                raise GateStop("blocked", "Rollback preview changed; review and explicitly select again")
            pending = {"preview": proposal, "intent": intent, "actor": actor, "reason": reason,
                       "authorization_event": state["permissions"]["code_write"]["id"]}
            state["pending_rollback"] = pending
            event(state, state["phase"], "interrupted", "Durable rollback intent; completion invalidated")
            if len(checkpoint_bytes(state)) > 8 * 1024 * 1024 - 16384:
                raise GateStop("blocked", "Rollback checkpoint capacity is exhausted; no files were changed")
            validate_pending(state)
            save(checkpoint, state)
        elif (confirmation != pending["preview"]["confirmation_sha256"]
              or set(fix_ids) != set(pending["preview"]["fix_ids"])
              or len(fix_ids) != len(set(fix_ids))):
            raise GateStop("blocked", "Pending rollback requires its original explicit selection")
        finish_intent(workspace, pending["intent"])
        receipt = {"fix_ids": pending["preview"]["fix_ids"], "at": now(),
                   "before_revision": pending["preview"]["before_revision"],
                   "after_revision": pending["intent"]["after_revision"],
                   "confirmation_sha256": pending["preview"]["confirmation_sha256"],
                   "actor": pending["actor"], "reason": pending["reason"],
                   "authorization_event": pending["authorization_event"]}
        state.setdefault("rollback_events", []).append(receipt)
        state["pending_rollback"] = None
        event(state, state["phase"], "interrupted",
              "Selected improvements rolled back; a new baseline and replay are required")
        save(checkpoint, state)
        return {"status": "rolled_back", "receipt": receipt,
                "improvements": improvement_rows(state),
                "product_complete": False, "revalidation_required": True}
