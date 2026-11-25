"""Prepare reviewed native inputs; never acquire sources or grant research support."""
from __future__ import annotations

import copy
from pathlib import Path

from .canonical import EngineError, byte_digest, canonical, digest, timestamp
from .merge import import_identity, load_imports, problem, validate_policy
from .schema import Resolver
from .storage import atomic, read_bytes, read_json, safe_path

SCHEMA = "ux-native-import-draft.v1"
FIELDS = {"artifact_ref", "source_type", "producer_org", "producer_stake",
          "acquisition", "sanitization", "retention_until"}
NATIVE_TYPES = {"product_analytics", "survey", "interview", "usability_test",
                "support_tickets", "product_brief", "expert_judgment"}
NEXT = ("Use genuine producer/owner-reviewed native research and its actual permission "
        "record. Web posts, browser captures and third-party API dumps need their "
        "original permitted reader/API route; this command cannot authorize them.")


def fail(code, reason, location="imports", next_step=NEXT, exit_code=2):
    raise EngineError(code, reason, exit_code, location=location, next_step=next_step)


def metadata_location(error, location):
    """Expose only pinned-schema field paths, never rejected values or keys."""
    path, _, detail = error.partition(": ")
    if detail.startswith("missing "):
        path += "." + detail.removeprefix("missing ")
    return location + path.removeprefix("$")


def prepare(args, run):
    """Check all inputs before writing a new immutable preparation directory."""
    validate_policy(run, open_required=True)
    draft = read_json(args.draft, private=True)
    if (not isinstance(draft, dict) or set(draft) != {"schema_version", "imports"}
            or draft["schema_version"] != SCHEMA or not isinstance(draft["imports"], list)
            or not 1 <= len(draft["imports"]) <= 64):
        fail("import_draft", "Provide a native-import draft with 1..64 imports.",
             next_step="Use ux-native-import-draft.v1 with schema_version and imports; see native-inputs.md.")
    resolver = Resolver()
    items, declarations = [], []
    for index, original in enumerate(draft["imports"]):
        loc = f"imports[{index}]"
        if not isinstance(original, dict) or set(original) != FIELDS | {"origin"}:
            fail("import_draft", "Import fields must match the native-input draft contract.", loc,
                 "Provide the documented provenance fields and origin; hashes and IDs are generated from actual bytes.")
        origin = original["origin"]
        if (not isinstance(origin, dict) or set(origin) != {"kind", "permission_confirmed"}
                or origin["kind"] not in {"native_team_data", "authorized_own_app_console"}
                or origin["permission_confirmed"] is not True):
            fail("import_origin", "Native origin and an actual scoped permission confirmation are required.", loc)
        item = {k: copy.deepcopy(original[k]) for k in FIELDS}
        # Validate every metadata field before paths or acquisition fields are used.
        item.update(content_sha256="0" * 64, import_id="IMP-" + "0" * 64)
        errors = resolver.validate(item, "ux-reader-return.v1.schema.json", "sanitizedImport")
        if errors:
            location = metadata_location(errors[0], loc)
            sanitization = item.get("sanitization")
            if (location == loc + ".sanitization.review_attestation"
                    and isinstance(sanitization, dict)
                    and (sanitization.get("review_attestation") is None
                         or sanitization.get("review_attestation") is False)):
                fail("unreviewed_import", "The producer/owner review has not been confirmed.", location,
                     "Obtain the actual producer/owner sanitization review first. Do not set review_attestation to true merely to pass validation.")
            fail("import_metadata", "Import metadata is incomplete or invalid.", location,
                 "Check the indicated field against native-inputs.md using actual provenance. Rejected values are not echoed or automatically corrected.")
        acq = item["acquisition"]
        if not acq["permission_ref"].strip() or not item["producer_org"].strip():
            fail("import_permission", "A real permission reference and producer are required.", loc)
        console = origin["kind"] == "authorized_own_app_console"
        if console:
            if acq["kind"] != "store_console_export" or item["source_type"] != "app_store_reviews":
                fail("import_origin", "Own-app console imports must retain their console route and review source type.", loc)
        elif acq["kind"] == "store_console_export" or item["source_type"] not in NATIVE_TYPES:
            fail("import_origin", "This source type is not native team research for this preparation path.", loc)
        now = timestamp(run.now_iso())
        if item["retention_until"] and timestamp(item["retention_until"]) <= now:
            fail("expired_import", "This import's retention deadline has passed.", loc,
                 "Do not reuse expired content. Obtain permitted current material and follow the existing retention process.")
        relative = Path(item["artifact_ref"])
        if relative.is_absolute() or ".." in relative.parts:
            fail("unsafe_import", "Import text must use a safe run-relative path.", loc,
                 "Place only the already-reviewed sanitized UTF-8 .txt/.text artifact inside this run.")
        raw = read_bytes(run.path / relative, private=True, root=run.path)
        if not raw.strip():
            fail("empty_import", "The sanitized artifact is empty.", loc,
                 "Provide actual reviewed research text; empty placeholders are not evidence.")
        item["content_sha256"] = byte_digest(raw)
        item["import_id"] = import_identity(item)
        items.append(item)
        declarations.append(dict(import_id=item["import_id"], origin=copy.deepcopy(origin)))
    if len({item["import_id"] for item in items}) != len(items):
        fail("duplicate_import", "The draft repeats the same content and acquisition.", next_step="Keep one import per content/acquisition identity.")
    doc = dict(schema_version="ux-sanitized-imports.v1", run_id=run.meta["run_id"], imports=items)
    issues = []
    load_imports(doc, run, resolver, issues)
    if issues:
        issue = issues[0]
        fail(issue["code"], issue["reason"], issue["location"],
             "Return the original to its producer/owner for sanitization and review. Refused content is not echoed or automatically repaired.",
             exit_code=1)
    warning = problem("prepared_not_gated", "imports",
                      "Preparation checks metadata and sanitized bytes, not legal rights, source truth or claim support.",
                      "Review typed source/excerpt/claim records, merge using the prepared imports, then run the unchanged gate and persona export.")
    if args.check_only:
        return 0, [], [], [warning]
    receipt = dict(schema_version="ux-import-preparation.v1", run_id=run.meta["run_id"],
                   draft_sha256=digest(draft), imports_sha256=digest(doc), origins=declarations,
                   authority="producer_owner_attestation_not_independent_rights_verification",
                   research_gate_run=False, personas_created=False)
    folder = safe_path(run.path / ("prepared-imports-" + digest(receipt)[:16]), run.path)
    outputs = {"sanitized-imports.json": canonical(doc), "preparation.json": canonical(receipt)}
    if folder.exists():
        if not folder.is_dir() or folder.stat().st_mode & 0o077 or set(p.name for p in folder.iterdir()) != set(outputs):
            fail("preparation_conflict", "A preparation directory is incomplete or unsafe.",
                 next_step="Inspect the prior attempt without overwriting it; preserve its files and resolve the incomplete output first.")
        if any(read_bytes(folder / name, private=True) != raw for name, raw in outputs.items()):
            fail("preparation_conflict", "Existing preparation bytes differ; they were preserved.",
                 next_step="Inspect the prior output. Never overwrite edited provenance or treat it as current.")
    else:
        folder.mkdir(mode=0o700)
        for name, raw in outputs.items():
            atomic(folder / name, raw)
    return 0, [str(folder / name) for name in outputs], [], [warning]
