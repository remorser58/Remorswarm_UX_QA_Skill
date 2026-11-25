"""Private, versioned behavioral personas; facts remain in the research ledger.

This is local bookkeeping, not a claim that a synthetic profile is a real person.
Revalidation reads the authoritative local research run; it does not discover
remote deletion or independently authenticate a research provider.
"""
from __future__ import annotations

import copy
import re
import time
from pathlib import Path

from uxresearch.canonical import EngineError, canonical, digest, timestamp
from uxresearch.merge import privacy_scan
from uxresearch.storage import Store, atomic, read_bytes, read_json, safe_path

SCHEMA = "ux-persona-library.v1"
INPUT_SCHEMA = "ux-persona-library-input.v1"
PROFILE_FIELDS = {"label", "goals", "behaviors", "contexts", "assumptions", "unknowns", "requirement_ids"}
MODES = {"prd_hypothesis", "gated_research"}


def fail(code, reason):
    raise EngineError(code, reason)


def identifier(value, label="identifier"):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
        fail("persona_input", f"Invalid {label}.")
    return value


def text_value(value, label, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        fail("persona_input", f"{label} must be bounded nonempty text.")
    if privacy_scan(value):
        fail("persona_privacy", f"{label} contains personal identifier patterns.")
    return value


def strings(value, label, minimum=1, maximum=24):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        fail("persona_input", f"{label} must have {minimum}..{maximum} items.")
    for item in value:
        text_value(item, label)
    if len(value) != len(set(value)):
        fail("persona_input", f"{label} contains duplicates.")
    return list(value)


def exact_keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        fail("persona_input", "Missing or unexpected input fields.")


def prd_context(context):
    exact_keys(context, {"prd_path", "prd_sha256", "requirements"})
    path = safe_path(context["prd_path"])
    raw = read_bytes(path)
    if digest_bytes(raw) != context["prd_sha256"]:
        fail("stale_prd", "The current PRD bytes differ from the persona binding.")
    try:
        content = raw.decode("utf-8")
    except UnicodeError:
        fail("persona_input", "The PRD must be a UTF-8 document.")
    requirements = context["requirements"]
    if not isinstance(requirements, list) or not 1 <= len(requirements) <= 64:
        fail("persona_input", "Provide 1..64 cited PRD requirements.")
    seen = set()
    for row in requirements:
        exact_keys(row, {"id", "source_anchor", "excerpt"})
        identifier(row["id"], "requirement id")
        text_value(row["source_anchor"], "source_anchor", 400)
        text_value(row["excerpt"], "PRD excerpt", 2000)
        if row["id"] in seen or row["excerpt"] not in content:
            fail("prd_citation", "PRD citations must be unique and match an exact current excerpt.")
        seen.add(row["id"])
    return {**copy.deepcopy(context), "prd_path": str(path)}


def digest_bytes(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def _research_binding(research, claim_ids, *, inspection=False):
    """Use the existing committed research gate, never an author-supplied status."""
    from uxresearch.engine import fresh
    from uxresearch.ledger import Run, RunError
    exact_keys(research, {"run", "bundle", "gate"})
    run_path = safe_path(research["run"])
    if inspection:
        from .research_access import ResearchView
        Run = ResearchView
    with Store(run_path, read_only=inspection) as store:
        try:
            run = Run(run_path)
            # This ordinary-import entry point owns its matching Store by construction.
            bundle, gate = fresh(run, store, Path(research["bundle"]), Path(research["gate"]))
        except RunError as exc:
            raise EngineError("research_policy", "The existing research policy or run metadata requires review.") from exc
        return _research_binding_record(research, claim_ids, bundle, gate)


def _research_binding_locked(research, claim_ids, run, store):
    """Internal shared validator; the caller already holds this research lock."""
    from uxresearch.engine import fresh
    exact_keys(research, {"run", "bundle", "gate"})
    run_path = safe_path(research["run"])
    if store.fd is None or store.root != run_path or safe_path(run.path) != run_path:
        fail("persona_lock", "The matching research lock is required.")
    bundle, gate = fresh(run, store, Path(research["bundle"]), Path(research["gate"]))
    return _research_binding_record(research, claim_ids, bundle, gate)


def _research_binding_record(research, claim_ids, bundle, gate):
    """Pure projection of a snapshot read inside one of the locked entry points."""
    from uxresearch.personas import claim_cards
    run_path = safe_path(research["run"])
    if gate.get("mode") != "live" or gate.get("result") != "pass":
        fail("research_not_live", "Only a current passing live research gate can motivate research personas.")
    cards = {row["claim_id"]: row for row in claim_cards(bundle, gate)}
    if not claim_ids or any(cid not in cards or not cards[cid]["exportable"] for cid in claim_ids):
        raise EngineError(
            "unsafe_motivation",
            "Selected research claims are missing, unsafe or lack observed non-counter motivation.",
            next_step="Inspect the current persona-starter claim cards. Preserve contrary evidence; review and re-author against usable sources. Without research, use an explicitly exploratory PRD hypothesis. Existing profiles are not deleted.")
    return {
        "run": str(run_path),
        "bundle": str(safe_path(research["bundle"])),
        "gate": str(safe_path(research["gate"])),
        "source_bundle_id": bundle["bundle_id"],
        "bundle_input_sha256": gate["bundle_input_sha256"],
        "process_input_sha256": gate["process_input_sha256"],
        "valid_until": gate.get("valid_until"),
        "claims": [{"claim_id": cid, "gate_status": cards[cid]["gate_status"],
                    "source_ids": cards[cid]["source_ids"],
                    "counting_evidence_ids": cards[cid]["counting_evidence_ids"],
                    "context_evidence_ids": cards[cid]["context_evidence_ids"]}
                   for cid in sorted(claim_ids)],
    }


def _retention_markers(source):
    """Compare cleanup-relevant annotations without treating mirrors as authority."""
    return {
        "status": source.get("retention_status"),
        "deadline": source.get("retention_until"),
        "tombstone": source.get("research_tombstone"),
        "captures": sorted(
            (capture["capture_ref"], capture["metadata"].get("retention_status"),
             capture["metadata"].get("retention_until"))
            for capture in source.get("captures", [])
        ),
    }


def retention_reason(record, now, *, inspection=False):
    """Only authoritative local deadlines/tombstones justify derivative removal."""
    provenance = record.get("provenance", {})
    if provenance.get("mode") != "gated_research":
        return None
    binding = provenance["research"]
    deadline = binding.get("valid_until")
    if deadline and timestamp(deadline).timestamp() <= now:
        return "The bound research retention or policy deadline expired."
    source_ids = {sid for claim in binding.get("claims", []) for sid in claim["source_ids"]}
    if not source_ids:
        return None
    with Store(safe_path(binding["run"]), read_only=inspection) as store:
        bundle = store.committed("bundle.json")
        sources = {source["id"]: source for source in bundle["records"]["sources"]}
        for source_id in sorted(source_ids & sources.keys()):
            source = sources[source_id]
            if source.get("research_tombstone") or source.get("retention_status") in {"withdrawn", "deleted", "redacted"}:
                return "An authoritative research source was withdrawn or removed."
            if any(capture["metadata"].get("retention_status") in {"withdrawn", "deleted", "redacted"}
                   for capture in source.get("captures", [])):
                return "An authoritative research capture was withdrawn or removed."
            deadlines = [source.get("retention_until")] + [capture["metadata"].get("retention_until") for capture in source.get("captures", [])]
            if any(timestamp(value, bare_date=True).timestamp() <= now for value in deadlines if value):
                return "An authoritative research source retention deadline expired."
        if source_ids - sources.keys():
            raise EngineError("retention_source_missing",
                              "A bound source is missing from authoritative retention state; no payload deleted.",
                              next_step="Recover the verified research state or explicitly retire this persona after reviewing the source disposition.")
        # A mirror may block reuse but must never authorize destructive cleanup.
        # Report pending changes rather than silently returning an empty success.
        live = read_json(binding["bundle"])
        live_sources = {source["id"]: source for source in live["records"]["sources"]}
        if (len(live_sources) != len(live["records"]["sources"])
                or live.get("bundle_id") != bundle.get("bundle_id")
                or any(source_id not in live_sources
                       or _retention_markers(live_sources[source_id]) != _retention_markers(sources[source_id])
                       for source_id in source_ids)):
            raise EngineError("retention_review_pending",
                              "Uncommitted research retention changes require review; no payload deleted.",
                              next_step="Review the pending source change. For a confirmed withdrawal, explicitly retire the affected persona; research-run and exported-copy cleanup remain separate.")
    return None


class Library:
    """Hold this context while importing, consuming or scheduling its personas."""

    def __init__(self, root, *, clock=None, reference_guard=None):
        self.root = safe_path(root)
        if self.root.is_relative_to(Path(__file__).resolve().parents[1]):
            fail("persona_path", "Persona state must stay outside the installed skill tree.")
        self.clock = clock or time.time
        self.lock = None
        self.reference_guard = reference_guard

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = Store(self.root)
        self.lock.__enter__()
        return self

    def __exit__(self, *args):
        if self.lock:
            self.lock.__exit__(*args)
            self.lock = None

    def _state(self):
        if self.lock is None:
            fail("persona_lock", "Use Library as a context manager.")
        path = self.root / "library.json"
        if not path.exists():
            return {"schema_version": SCHEMA, "entries": {}}
        envelope = read_json(path, private=True)
        state = envelope.get("state")
        if not isinstance(state, dict) or state.get("schema_version") != SCHEMA or digest(state) != envelope.get("sha256"):
            fail("persona_integrity", "The persona library state is invalid.")
        return state

    def _save(self, state):
        from uxresearch.storage import MAX_BYTES
        raw = canonical({"state": state, "sha256": digest(state)})
        if len(raw) > MAX_BYTES:
            fail("persona_capacity", "The library update exceeds its readable size limit; existing state is preserved.")
        atomic(self.root / "library.json", raw)

    @staticmethod
    def _key(product_id, persona_id):
        return identifier(product_id, "product id") + "/" + identifier(persona_id, "persona id")

    def import_profiles(self, doc):
        return self._commit_profiles(self._prepare_profiles(doc))

    def _prepare_profiles(self, doc, *, research_validator=None):
        """Validate a whole batch before touching library state."""
        exact_keys(doc, {"schema_version", "product_id", "mode", "context", "personas"}, {"research", "review_days"})
        if doc["schema_version"] != INPUT_SCHEMA or doc["mode"] not in MODES:
            fail("persona_input", "Unknown persona input schema or provenance mode.")
        product = identifier(doc["product_id"], "product id")
        context = prd_context(doc["context"])
        review_days = doc.get("review_days", 30)
        if type(review_days) is not int or not 1 <= review_days <= 90:
            fail("persona_input", "review_days must be an integer from 1 to 90.")
        if not isinstance(doc["personas"], list) or not 1 <= len(doc["personas"]) <= 32:
            fail("persona_input", "Import 1..32 personas at a time.")
        if (doc["mode"] == "gated_research") != ("research" in doc):
            fail("persona_input", "Only gated_research accepts and requires a research run binding.")
        required_ids = {row["id"] for row in context["requirements"]}
        prepared, seen = [], set()
        for item in doc["personas"]:
            exact_keys(item, PROFILE_FIELDS | {"persona_id", "claim_ids"})
            pid = identifier(item["persona_id"], "persona id")
            if not pid.startswith("PER-") or pid in seen:
                fail("persona_input", "Persona IDs must be unique PER- identifiers.")
            seen.add(pid)
            text_value(item["label"], "label", 160)
            profile = {field: copy.deepcopy(item[field]) for field in PROFILE_FIELDS}
            for field in PROFILE_FIELDS - {"label"}:
                strings(profile[field], field)
            if not set(profile["requirement_ids"]) <= required_ids:
                fail("prd_citation", "Every persona must map to current PRD requirements.")
            claim_ids = strings(item["claim_ids"], "claim_ids", minimum=0, maximum=32)
            if any(not re.fullmatch(r"CLM-[0-9a-f]{8}", cid) for cid in claim_ids):
                fail("persona_input", "Invalid research claim IDs.")
            provenance = {"mode": doc["mode"], "claim_ids": claim_ids}
            if doc["mode"] == "gated_research":
                provenance["research"] = (research_validator or _research_binding)(doc["research"], claim_ids)
            elif claim_ids:
                fail("persona_input", "PRD-only hypotheses cannot carry research claim IDs.")
            body = {"product_id": product, "persona_id": pid, "basis": "synthetic", "review_days": review_days,
                    "profile": profile, "context": context, "provenance": provenance}
            prepared.append((self._key(product, pid), body))
        return prepared

    def _commit_profiles(self, prepared, *, before_save=None, now=None):
        """One atomic publication; an identical current import does not rewrite."""
        state = self._state()
        result = []
        now = self.clock() if now is None else now
        for key, body in prepared:
            product = body["product_id"]
            history = state["entries"].setdefault(key, [])
            signature = digest(body)
            current = history[-1] if history else None
            if current and current["status"] == "active" and current["profile_sha256"] == signature and current["review_after"] > now:
                result.append({"product_id": product, "persona_id": body["persona_id"],
                               "revision": current["revision"], "profile_sha256": signature, "changed": False})
                continue
            revision = (current["revision"] if current else 0) + 1
            history.append({**body, "revision": revision, "profile_sha256": signature,
                            "status": "active", "created_at": now, "review_after": now + body["review_days"] * 86400})
            result.append({"product_id": product, "persona_id": body["persona_id"],
                           "revision": revision, "profile_sha256": signature, "changed": True})
        if any(row["changed"] for row in result):
            if before_save:
                before_save()
            self._save(state)
        return {"basis": "synthetic", "imported": result,
                "limits": "Stored test hypotheses, not real participants, prevalence or product results."}

    def _validate(self, record):
        if self.reference_guard is not None:
            self.reference_guard(record)
        if record.get("status") != "active":
            fail("persona_retired", "The persona was retired; re-author and import before reuse.")
        body = {key: record[key] for key in ("product_id", "persona_id", "basis", "review_days", "profile", "context", "provenance")}
        if digest(body) != record.get("profile_sha256"):
            fail("persona_integrity", "Persona revision content does not match its fingerprint.")
        if record["review_after"] <= self.clock():
            fail("persona_review_due", "Persona review is due; recheck the PRD and research before importing a new revision.")
        prd_context(record["context"])
        provenance = record["provenance"]
        if "research_scenarios" in record["profile"] or "research_export" in provenance:
            from .research_intake import validate_projection
            validate_projection(record)
        if provenance["mode"] == "gated_research":
            reason = retention_reason(record, self.clock(), inspection=self.reference_guard is not None)
            if reason:
                fail("persona_retention_due", reason + " Run prune to remove saved derived profiles.")
            previous = provenance["research"]
            current = _research_binding({k: previous[k] for k in ("run", "bundle", "gate")}, provenance["claim_ids"],
                                        inspection=self.reference_guard is not None)
            if current != previous:
                fail("stale_research", "Research changed since this persona revision; re-author against the current gate.")

    def get(self, product_id, persona_id, revision=None, revalidate=True):
        history = self._state()["entries"].get(self._key(product_id, persona_id), [])
        if not history:
            fail("persona_missing", "No persona exists for this product and ID.")
        record = history[-1]
        if revision is not None and (type(revision) is not int or revision != record["revision"]):
            fail("stale_persona_revision", "Only the current active persona revision may drive a new or continued run.")
        if revalidate:
            self._validate(record)
        return copy.deepcopy(record)

    def list(self, product_id=None):
        state = self._state()
        if product_id is not None:
            identifier(product_id, "product id")
        rows = []
        for key, history in sorted(state["entries"].items()):
            record = history[-1]
            if product_id is not None and record["product_id"] != product_id:
                continue
            row = {k: record[k] for k in ("product_id", "persona_id", "revision", "profile_sha256", "status")}
            row["revisions"] = len(history)
            try:
                self._validate(record)
                row["reusable"] = True
            except EngineError as exc:
                row["reusable"] = False
                row["blocker"] = exc.issue
            rows.append(row)
        return {"basis": "synthetic", "personas": rows}

    def retire(self, product_id, persona_id, reason):
        text_value(reason, "retirement reason", 500)
        state = self._state()
        key = self._key(product_id, persona_id)
        history = state["entries"].get(key)
        if not history:
            fail("persona_missing", "No persona exists for this product and ID.")
        if history[-1]["status"] == "retired":
            return {"product_id": product_id, "persona_id": persona_id, "status": "retired", "changed": False}
        # Do not keep derived source content alive in old library revisions.
        tombstones = [{k: row[k] for k in ("product_id", "persona_id", "revision", "profile_sha256", "created_at")}
                      for row in history]
        for row in tombstones:
            row.update(status="retired", retired_at=self.clock(), reason=reason)
        state["entries"][key] = tombstones
        self._save(state)
        return {"product_id": product_id, "persona_id": persona_id, "status": "retired", "changed": True,
                "limits": "Library payload removed. Separately exported task reports/evidence need their own retention review."}

    def prune(self):
        """Explicitly remove retained derivatives of known expired/withdrawn sources."""
        state = self._state()
        removed, blockers = [], []
        for history in state["entries"].values():
            if history[-1]["status"] == "retired":
                continue
            pending = None
            for record in history:
                try:
                    reason = retention_reason(record, self.clock())
                except (EngineError, OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
                    issue = exc.issue if isinstance(exc, EngineError) else {}
                    known = issue.get("code") in {"retention_source_missing", "retention_review_pending"}
                    pending = {"product_id": record["product_id"], "persona_id": record["persona_id"],
                                     "revision": record["revision"],
                                     "code": issue["code"] if known else "retention_check_unavailable",
                                     "reason": issue["reason"] if known else "Authoritative retention state could not be checked; no payload deleted.",
                                     "next_step": issue.get("next_step") if known else "Restore readable verified research state before retrying; do not treat cleanup as complete."}
                    continue
                if reason:
                    removed.append(self.retire(record["product_id"], record["persona_id"], reason))
                    break
            else:
                if pending:
                    blockers.append(pending)
        return {"result": "partial" if removed and blockers else "blocked" if blockers else "pass",
                "library_cleanup_complete": not blockers, "retired": removed, "blockers": blockers,
                "limits": "Checks local authoritative records, not remote deletion. Separate exported evidence needs its own cleanup."}
