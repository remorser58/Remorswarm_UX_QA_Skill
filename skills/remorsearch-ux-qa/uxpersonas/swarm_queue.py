"""Durable local queue for independent persona sessions, with no network code.

An intent is an exposure, not proof of delivery. Expired or cancelled intents
remain quarantined and keep both their cost reservation and capacity permit.
SQLite fencing protects local commits; it cannot cancel a provider request.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
import copy
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import time

from uxresearch.canonical import EngineError, canonical, digest
from uxresearch.storage import atomic, read_json, safe_path, sync_dir

SCHEMA = "ux-persona-queue.v1"
ACTIVE = ("intent", "uncertain")
CHECKPOINT_METADATA_BYTES = 1024 * 1024
CHECKPOINT_OBSERVATION_BYTES = 128 * 1024
OBSERVATION_CONTENT_BYTES = 65536


def fail(code, reason):
    raise EngineError(code, reason)


def bounded(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        fail("queue_input", f"{name} must be an integer from {low} to {high}.")
    return value


def data(value, limit=262144):
    try:
        raw = canonical(value)
        if len(raw) > limit:
            raise ValueError()
        return json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        fail("queue_input", "Queue data must be bounded finite JSON.")


def checkpoint_data(state, turns):
    """Bound durable history separately from a single model/tool request.

    Execution admits at most one observation per approved model turn. Its
    text/facts/checks retain the existing 64 KiB bound; a 128 KiB full envelope
    also accommodates the bounded action and duplicate artifact references.
    Receipt previews, judgments and all other state share the existing 1 MiB
    metadata allowance. No request, response or final-result limit is raised.
    """
    bounded(turns, 1, 80, "checkpoint turns")
    state = data(state, CHECKPOINT_METADATA_BYTES
                 + turns * (CHECKPOINT_OBSERVATION_BYTES + 1) + 32)
    if not isinstance(state, dict):
        fail("queue_input", "A checkpoint must be an object.")
    observations = state.get("observations", [])
    if not isinstance(observations, list) or len(observations) > turns:
        fail("queue_input", "Checkpoint history exceeds the approved observation count.")
    data({key: value for key, value in state.items() if key != "observations"},
         CHECKPOINT_METADATA_BYTES)
    for observation in observations:
        data(observation, CHECKPOINT_OBSERVATION_BYTES)
        # The queue also supports opaque checkpoint entries; the execution
        # layer owns their schema. Recheck the known browser content envelope
        # so storing history cannot enlarge the per-observation allowance.
        if isinstance(observation, dict) and all(key in observation for key in ("text", "facts", "checks")):
            data({key: observation[key] for key in ("text", "facts", "checks")},
                 OBSERVATION_CONTENT_BYTES)
    return state


def quote(spec, inputs=None, outputs=None):
    inputs = spec["input_token_cap"] if inputs is None else inputs
    outputs = spec["output_token_cap"] if outputs is None else outputs
    return (inputs * spec["input_price_per_million"] + outputs * spec["output_price_per_million"] + 999999) // 1000000


def _immutable(*args, **kwargs):
    fail("plan_immutable", "Execution plans cannot be edited after preparation or approval.")


class _FrozenDict(dict):
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _immutable

    def __deepcopy__(self, memo):
        return {key: copy.deepcopy(value, memo) for key, value in self.items()}


class _FrozenList(list):
    __setitem__ = __delitem__ = append = extend = insert = pop = remove = clear = reverse = sort = __iadd__ = __imul__ = _immutable

    def __deepcopy__(self, memo):
        return [copy.deepcopy(value, memo) for value in self]


def _freeze(value):
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList([_freeze(item) for item in value])
    return value


SQL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE jobs (
 id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL, provider TEXT NOT NULL,
 context_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL, checkpoint TEXT NOT NULL,
 checkpoint_sha TEXT NOT NULL, owner TEXT, lease_token TEXT, lease_until REAL,
 ready_at REAL NOT NULL DEFAULT 0, last_pick REAL NOT NULL DEFAULT 0,
 elapsed REAL NOT NULL DEFAULT 0, problem TEXT, result TEXT, result_sha TEXT
);
CREATE INDEX jobs_ready ON jobs(status, ready_at, last_pick, ordinal);
CREATE TABLE operations (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), provider TEXT NOT NULL,
 kind TEXT NOT NULL, slot TEXT NOT NULL, state TEXT NOT NULL, lease_token TEXT NOT NULL,
 request TEXT NOT NULL, request_sha TEXT NOT NULL, reply TEXT, reply_sha TEXT,
 reserved INTEGER NOT NULL CHECK(reserved>=0), charged INTEGER NOT NULL DEFAULT 0 CHECK(charged>=0),
 started REAL NOT NULL, ended REAL, deadline REAL NOT NULL, problem TEXT,
 UNIQUE(job_id, kind, slot)
);
CREATE INDEX operations_capacity ON operations(state, provider, kind);
CREATE INDEX operations_rate ON operations(provider, started);
CREATE TABLE approvals (
 id TEXT PRIMARY KEY, plan_sha TEXT NOT NULL, actor TEXT NOT NULL,
 consent_reference TEXT NOT NULL, ceiling INTEGER NOT NULL, created REAL NOT NULL,
 expires REAL NOT NULL
);
CREATE TABLE cooldowns (provider TEXT PRIMARY KEY, until REAL NOT NULL);
CREATE TABLE events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL,
 body TEXT NOT NULL, previous_sha TEXT NOT NULL, sha TEXT NOT NULL
);
"""


class Queue:
    def __init__(self, root, *, clock=None):
        self.root = safe_path(root)
        self.clock = clock or time.time
        self.path = safe_path(self.root / "queue.sqlite", self.root)
        if (not self.root.is_dir() or self.root.stat().st_mode & 0o077
                or not self.path.is_file() or self.path.stat().st_mode & 0o077
                or self.path.stat().st_nlink != 1):
            fail("queue_path", "Use the existing private queue directory; no new run was created.")
        envelope = read_json(self.root / "plan.json", private=True)
        self._plan = _freeze(envelope.get("plan"))
        self._plan_sha256 = envelope.get("sha256")
        if (not isinstance(self.plan, dict) or self.plan.get("schema_version") != SCHEMA
                or digest(self.plan) != self.plan_sha256):
            fail("plan_integrity", "The immutable execution plan changed.")
        self._jobs = _FrozenDict({job["id"]: job for job in self.plan["jobs"]})
        with self._db() as db:
            if self._get(db, "plan_sha") != self.plan_sha256 or self._get(db, "schema") != SCHEMA:
                fail("plan_integrity", "Database and approved plan do not match.")

    @property
    def plan(self):
        return self._plan

    @property
    def plan_sha256(self):
        return self._plan_sha256

    @property
    def jobs(self):
        return self._jobs

    @classmethod
    def create(cls, root, plan, *, clock=None):
        plan = data(plan, 16 * 1024 * 1024)
        if plan.get("schema_version") != SCHEMA or plan.get("mode") not in {"fixture", "live"}:
            fail("queue_input", "Unknown execution schema or provenance mode.")
        from .swarm_providers import ProviderSpec
        limits = plan["limits"]
        for name, low, high in (("parallel", 1, 64), ("turns", 1, 80),
                ("call_seconds", 1, 180), ("task_seconds", 1, 3600),
                ("lease_seconds", 10, 600), ("budget_microusd", 0, 10**12),
                ("max_model_calls", 1, 50000)):
            bounded(limits[name], low, high, name)
        jobs = plan.get("jobs")
        if not isinstance(jobs, list) or not 1 <= len(jobs) <= 1000:
            fail("queue_input", "Select one to one thousand distinct saved persona sessions.")
        if len({j["id"] for j in jobs}) != len(jobs) or len({j["task"]["persona_id"] for j in jobs}) != len(jobs):
            fail("queue_input", "A run needs distinct job and saved persona identities.")
        providers = plan.get("providers")
        if not isinstance(providers, dict) or not 1 <= len(providers) <= 16:
            fail("queue_input", "Select one to sixteen reviewed provider routes.")
        for key, provider in providers.items():
            spec = ProviderSpec(**provider["spec"]).validate()
            if spec["key"] != key or provider["mode"] != plan["mode"]:
                fail("queue_input", "Provider identities and fixture/live modes must match the plan.")
            if not isinstance(provider["adapter_sha256"], str) or len(provider["adapter_sha256"]) != 64:
                fail("queue_input", "Every route needs a reviewed adapter hash.")
            if plan["mode"] == "live" and not provider.get("credential_scope"):
                fail("queue_input", "Live routes require a non-secret credential/account scope reference.")
            if plan["mode"] == "live":
                review = provider.get("billing_review", {})
                fields = ("input_token_cap", "output_token_cap", "input_price_per_million", "output_price_per_million")
                if (not isinstance(review, dict) or any(review.get(name) != spec[name] for name in fields)
                        or review.get("no_unpriced_features") is not True
                        or not isinstance(review.get("source"), str) or not review["source"].strip()
                        or not isinstance(review.get("checked_at"), str) or not review["checked_at"].strip()
                        or not isinstance(provider.get("destination"), str) or not provider["destination"].strip()
                        or spec["protocol"] == "fixture"
                        or ((spec["input_price_per_million"] <= 0 or spec["output_price_per_million"] <= 0)
                            and not (
                                spec["key"] == "local-router"
                                and spec["protocol"] == "callback"
                                and spec["model"] == "tokenmaxx-deepseek-v4-1-flash-free"
                                and spec["input_price_per_million"] == 0
                                and spec["output_price_per_million"] == 0
                                and review.get("free_tier") is True
                                and review.get("billing_source") == "free"
                                and review.get("requested_model") == "TOKENMAXX/deepseek-v4.1-flash-free"))):
                    fail("billing_review_required", "Review the actual input context ceiling, output limit, prices and data destination before live approval.")
        if any(j["provider"] not in providers for j in jobs):
            fail("queue_input", "A session refers to an unreviewed provider.")
        root = safe_path(root)
        if root.exists():
            fail("run_exists", "Existing runs are preserved; resume the original run or select a new workspace.")
        root.mkdir(parents=True, mode=0o700)
        (root / "sessions").mkdir(mode=0o700)
        atomic(root / "plan.json", canonical(dict(plan=plan, sha256=digest(plan))))
        path = root / "queue.sqlite"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        db = sqlite3.connect(path, isolation_level=None)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(SQL)
            db.execute("BEGIN IMMEDIATE")
            db.executemany("INSERT INTO meta VALUES (?, ?)", [("schema", SCHEMA),
                ("plan_sha", digest(plan)), ("control", "paused" if plan["mode"] == "live" else "running")])
            for i, job in enumerate(jobs):
                context = "ctx-" + digest([digest(plan), job["id"]])[:40]
                db.execute("INSERT INTO jobs(id,ordinal,provider,context_id,status,checkpoint,checkpoint_sha) VALUES(?,?,?,?,?,?,?)",
                    (job["id"], i, job["provider"], context, "queued", "{}", digest({})))
            db.commit()
        finally:
            db.close()
        sync_dir(root)
        queue = cls(root, clock=clock)
        with queue._db(write=True) as db:
            queue._event(db, "created", dict(plan_sha256=queue.plan_sha256, mode=plan["mode"], sessions=len(jobs)))
        return queue

    @contextmanager
    def _db(self, *, write=False):
        safe_path(self.path)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = safe_path(str(self.path) + suffix)
            if sidecar.exists() and (not sidecar.is_file() or sidecar.stat().st_mode & 0o077):
                fail("queue_path", "Queue sidecars must remain private regular files.")
        with closing(sqlite3.connect(
                str(self.path) if write else self.path.as_uri() + "?mode=ro",
                timeout=5, isolation_level=None, uri=not write)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            if write:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                if write:
                    db.commit()
            except BaseException:
                if write:
                    db.rollback()
                raise

    @staticmethod
    def _get(db, key):
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _event(self, db, kind, body):
        previous = db.execute("SELECT sha FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = previous[0] if previous else "0" * 64
        at = self.clock()
        body = data(body)
        value = dict(at=at, kind=kind, body=body, previous_sha=previous)
        db.execute("INSERT INTO events(at,kind,body,previous_sha,sha) VALUES(?,?,?,?,?)",
                   (at, kind, canonical(body).decode(), previous, digest(value)))

    def authorize(self, *, plan_sha256, actor, consent_reference, expires_at, budget_microusd):
        if (plan_sha256 != self.plan_sha256 or budget_microusd != self.plan["limits"]["budget_microusd"]
                or not isinstance(actor, str) or not actor.strip() or len(actor) > 160
                or not isinstance(consent_reference, str) or not consent_reference.strip() or len(consent_reference) > 500
                or not isinstance(expires_at, (int, float)) or not math.isfinite(expires_at)
                or not self.clock() < expires_at <= self.clock() + 30 * 86400):
            fail("approval_invalid", "Record explicit user approval for this exact plan, amount and bounded expiry.")
        approval_id = "approval-" + secrets.token_hex(16)
        with self._db(write=True) as db:
            if self._get(db, "control") == "cancelled":
                fail("cancelled", "Cancellation is final; the original run is preserved.")
            db.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?,?)",
                (approval_id, plan_sha256, actor, consent_reference, budget_microusd, self.clock(), expires_at))
            self._event(db, "user_approval_recorded", dict(approval_id=approval_id, plan_sha256=plan_sha256,
                actor=actor, consent_reference=consent_reference, expires_at=expires_at))
        return approval_id

    def _approved(self, db):
        if self.plan["mode"] == "fixture":
            return True
        return db.execute("SELECT 1 FROM approvals WHERE plan_sha=? AND ceiling=? AND expires>? LIMIT 1",
            (self.plan_sha256, self.plan["limits"]["budget_microusd"], self.clock())).fetchone() is not None

    def control(self, action):
        if action not in {"pause", "resume", "cancel"}:
            fail("queue_input", "Use pause, resume or cancel.")
        with self._db(write=True) as db:
            current = self._get(db, "control")
            if current == "cancelled" and action != "cancel":
                fail("cancelled", "Cancelled work cannot silently restart.")
            if action == "resume" and not self._approved(db):
                fail("approval_required", "The exact live plan needs current explicit user cost approval.")
            value = {"pause": "paused", "resume": "running", "cancel": "cancelled"}[action]
            db.execute("UPDATE meta SET value=? WHERE key='control'", (value,))
            if action == "cancel":
                db.execute("UPDATE operations SET state='uncertain',problem='cancelled_after_intent' WHERE state='intent'")
                db.execute("UPDATE jobs SET status=CASE WHEN id IN (SELECT job_id FROM operations WHERE state='uncertain') THEN 'uncertain' ELSE 'cancelled' END, owner=NULL,lease_token=NULL,lease_until=NULL,problem='cancelled' WHERE status IN ('queued','running')")
            self._event(db, action, dict(previous=current))
        return self.report()

    def _expire(self, db):
        rows = db.execute("SELECT id FROM jobs WHERE status='running' AND lease_until<=?", (self.clock(),)).fetchall()
        for row in rows:
            job_id = row["id"]
            pending = db.execute("SELECT id FROM operations WHERE job_id=? AND state IN ('intent','uncertain')", (job_id,)).fetchall()
            if pending:
                db.execute("UPDATE operations SET state='uncertain',problem='expired_after_intent' WHERE job_id=? AND state='intent'", (job_id,))
            db.execute("UPDATE jobs SET status=?,owner=NULL,lease_token=NULL,lease_until=NULL,problem=? WHERE id=?",
                ("uncertain" if pending else "queued", "expired_after_intent" if pending else None, job_id))
            self._event(db, "lease_expired", dict(job_id=job_id, outcome="uncertain" if pending else "safe_checkpoint"))

    def _claim(self, db, claim):
        row = db.execute("SELECT * FROM jobs WHERE id=?", (claim["job_id"],)).fetchone()
        if (not row or row["status"] != "running" or row["lease_token"] != claim["lease_token"]
                or row["owner"] != claim.get("owner") or row["lease_until"] <= self.clock()):
            fail("stale_lease", "This worker no longer owns the session; late output cannot replace current evidence.")
        if digest(json.loads(row["checkpoint"])) != row["checkpoint_sha"]:
            fail("checkpoint_integrity", "The saved session checkpoint changed.")
        return row

    def assert_claim(self, claim):
        with self._db() as db:
            return dict(self._claim(db, claim))

    def claim(self, owner):
        if not isinstance(owner, str) or not owner or len(owner) > 64:
            fail("queue_input", "A bounded worker identity is required.")
        with self._db(write=True) as db:
            self._expire(db)
            if self._get(db, "control") != "running" or not self._approved(db):
                return None
            if db.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0] >= self.plan["limits"]["parallel"]:
                return None
            rows = db.execute("SELECT * FROM jobs WHERE status='queued' AND ready_at<=? ORDER BY last_pick,ordinal", (self.clock(),)).fetchall()
            for row in rows:
                cool = db.execute("SELECT until FROM cooldowns WHERE provider=?", (row["provider"],)).fetchone()
                if cool and cool[0] > self.clock():
                    continue
                if digest(json.loads(row["checkpoint"])) != row["checkpoint_sha"]:
                    fail("checkpoint_integrity", "The saved session checkpoint changed.")
                token = secrets.token_hex(24)
                until = self.clock() + self.plan["limits"]["lease_seconds"]
                db.execute("UPDATE jobs SET status='running',owner=?,lease_token=?,lease_until=?,last_pick=?,problem=NULL WHERE id=?",
                    (owner, token, until, self.clock(), row["id"]))
                self._event(db, "claimed", dict(job_id=row["id"], owner=owner))
                return dict(job_id=row["id"], provider=row["provider"], context_id=row["context_id"],
                    owner=owner, lease_token=token, lease_until=until,
                    checkpoint=json.loads(row["checkpoint"]), job=copy.deepcopy(self.jobs[row["id"]]))
        return None

    def renew(self, claim):
        with self._db(write=True) as db:
            self._claim(db, claim)
            until = self.clock() + self.plan["limits"]["lease_seconds"]
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?", (until, claim["job_id"]))
        claim["lease_until"] = until

    def _exposure(self, db):
        row = db.execute("SELECT COALESCE(SUM(charged),0), COALESCE(SUM(CASE WHEN state IN ('intent','uncertain') THEN reserved ELSE 0 END),0) FROM operations").fetchone()
        return row[0], row[1]

    def begin(self, claim, kind, slot, payload, timeout_seconds=None):
        if kind not in {"model", "review", "tool", "close"} or not isinstance(slot, (str, int)) or len(str(slot)) > 80:
            fail("queue_input", "Unknown bounded operation slot.")
        payload = data(payload)
        key = "op-" + digest([self.plan_sha256, claim["job_id"], kind, str(slot)])[:40]
        request_sha = digest(payload)
        with self._db(write=True) as db:
            job = self._claim(db, claim)
            previous = db.execute("SELECT * FROM operations WHERE id=?", (key,)).fetchone()
            if previous:
                if previous["request_sha"] != request_sha:
                    fail("operation_conflict", "An existing operation cannot receive different input.")
                if previous["state"] == "done":
                    reply = json.loads(previous["reply"])
                    if digest(reply) != previous["reply_sha"]:
                        fail("response_integrity", "The committed response changed.")
                    return dict(cached=True, request=json.loads(previous["request"]), reply=reply)
                if previous["state"] != "not_sent":
                    fail("uncertain_execution", "An earlier send may have happened; inspect it instead of repeating it.")
            control = self._get(db, "control")
            if control != "running":
                fail("cancelled" if control == "cancelled" else "paused", "No new operation may be sent while the run is stopped.")
            if not self._approved(db):
                fail("approval_required", "User approval is missing or expired; no paid request was sent.")
            now = self.clock()
            spec = self.plan["providers"][job["provider"]]["spec"]
            # An uncertain operation is durably quarantined, never replayed, but
            # its original transport is no longer an active execution slot. Keep
            # it in the audit ledger, RPM window and budget accounting below;
            # only live intents consume bounded in-flight concurrency.
            count = db.execute("SELECT COUNT(*) FROM operations WHERE state='intent'").fetchone()[0]
            if count >= self.plan["limits"]["parallel"]:
                fail("admission_wait", "The global in-flight request limit is occupied.")
            billed = kind in {"model", "review"}
            if billed:
                count = db.execute("SELECT COUNT(*) FROM operations WHERE provider=? AND kind IN ('model','review') AND state='intent'", (job["provider"],)).fetchone()[0]
                if count >= spec["concurrency"]:
                    fail("admission_wait", "This provider's in-flight capacity is occupied.")
                count = db.execute("SELECT COUNT(*) FROM operations WHERE provider=? AND kind IN ('model','review') AND started>? AND state!='not_sent'", (job["provider"], now - 60)).fetchone()[0]
                if count >= spec["requests_per_minute"]:
                    fail("admission_wait", "This provider's durable request window is full.")
                count = db.execute("SELECT COUNT(*) FROM operations WHERE kind IN ('model','review') AND state!='not_sent'").fetchone()[0]
                if count >= self.plan["limits"]["max_model_calls"]:
                    fail("session_budget", "The approved run request ceiling is reached.")
                cooldown = db.execute("SELECT until FROM cooldowns WHERE provider=?", (job["provider"],)).fetchone()
                if cooldown and cooldown[0] > now:
                    fail("admission_wait", "This provider is cooling down; other providers may continue.")
            reserve = quote(spec) if billed else 0
            charged, held = self._exposure(db)
            if charged + held + reserve > self.plan["limits"]["budget_microusd"]:
                if held and charged + reserve <= self.plan["limits"]["budget_microusd"]:
                    fail("admission_wait", "Outstanding requests may release unused reservations; wait before admitting another request.")
                fail("budget_exhausted", "The remaining approved budget cannot safely cover another request.")
            # Closing an owned context has its own short cleanup allowance; it
            # never grants another model call or releases an unknown operation.
            remaining = (min(15, self.plan["limits"]["call_seconds"]) if kind == "close"
                         else self.plan["limits"]["task_seconds"] - job["elapsed"])
            if timeout_seconds is not None and (type(timeout_seconds) not in {int, float}
                    or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
                fail("queue_input", "An operation timeout must be finite and positive.")
            seconds = min(timeout_seconds if timeout_seconds is not None else self.plan["limits"]["call_seconds"],
                          self.plan["limits"]["call_seconds"], remaining)
            if seconds <= 0:
                fail("session_budget", "This session has exhausted its active execution time.")
            deadline = now + seconds
            request = dict(operation_id=key, context_id=job["context_id"], request_sha256=request_sha,
                           deadline=deadline, payload=payload)
            if previous:
                db.execute("UPDATE operations SET state='intent',lease_token=?,request=?,reserved=?,started=?,deadline=?,problem=NULL WHERE id=?",
                    (claim["lease_token"], canonical(request).decode(), reserve, now, deadline, key))
            else:
                db.execute("INSERT INTO operations(id,job_id,provider,kind,slot,state,lease_token,request,request_sha,reserved,started,deadline) VALUES(?,?,?,?,?,'intent',?,?,?,?,?,?)",
                    (key, job["id"], job["provider"], kind, str(slot), claim["lease_token"], canonical(request).decode(), request_sha, reserve, now, deadline))
            until = max(job["lease_until"], deadline + 5)
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?", (until, job["id"]))
            self._event(db, "dispatch_intent", dict(operation_id=key, job_id=job["id"], kind=kind,
                request_sha256=request_sha, reserved_microusd=reserve, mode=self.plan["mode"],
                approval_id=(db.execute("SELECT id FROM approvals WHERE plan_sha=? AND expires>? ORDER BY created DESC LIMIT 1",
                    (self.plan_sha256, now)).fetchone()[0] if self.plan["mode"] == "live" else None)))
        claim["lease_until"] = until
        return dict(cached=False, request=request)

    def finish(self, claim, request, reply):
        reply = data(reply)
        with self._db(write=True) as db:
            job = self._claim(db, claim)
            op = db.execute("SELECT * FROM operations WHERE id=? AND job_id=?", (request["operation_id"], job["id"])).fetchone()
            if op and op["state"] == "done" and op["reply_sha"] == digest(reply):
                return copy.deepcopy(reply)
            if (not op or op["state"] != "intent" or op["lease_token"] != claim["lease_token"]
                    or json.loads(op["request"]) != request or self.clock() >= op["deadline"]):
                fail("stale_result", "Late or unowned response; its exposure remains reserved.")
            expected = {"operation_id", "context_id", "request_sha256", "trace_id", "result"}
            billed = op["kind"] in {"model", "review"}
            if billed:
                expected.add("usage")
            if (set(reply) != expected or any(reply.get(k) != request[k] for k in ("operation_id", "context_id", "request_sha256"))
                    or not isinstance(reply["trace_id"], str) or not 1 <= len(reply["trace_id"]) <= 256):
                fail("response_binding", "Response does not match this isolated operation.")
            charge = 0
            if billed:
                usage = reply["usage"]
                spec = self.plan["providers"][job["provider"]]["spec"]
                allowed_usage = {"input_tokens", "output_tokens", "provider", "model", "provider_cost_microusd",
                    "provider_reported_costs", "billing_sources", "cost_basis"}
                if not isinstance(usage, dict) or set(usage) - allowed_usage or not {"input_tokens", "output_tokens"} <= set(usage):
                    fail("usage_unknown", "Keep the reservation until provider usage is known.")
                bounded(usage["input_tokens"], 0, spec["input_token_cap"], "input_tokens")
                bounded(usage["output_tokens"], 0, spec["output_token_cap"], "output_tokens")
                for field in ("provider", "model", "cost_basis"):
                    if field in usage and (not isinstance(usage[field], str) or not usage[field] or len(usage[field]) > 160):
                        fail("usage_unknown", "Actual provider, model and cost basis labels must be bounded strings.")
                if "provider_cost_microusd" in usage and usage["provider_cost_microusd"] is not None:
                    charge = bounded(usage["provider_cost_microusd"], 0, 10**12, "provider_cost_microusd")
                else:
                    charge = quote(spec, usage["input_tokens"], usage["output_tokens"])
                if "provider_reported_costs" in usage and (
                        not isinstance(usage["provider_reported_costs"], list)
                        or len(usage["provider_reported_costs"]) > 32
                        or any(value is not None and (not isinstance(value, (str, int, float)) or isinstance(value, bool))
                               for value in usage["provider_reported_costs"])):
                    fail("usage_unknown", "Raw provider-reported cost fields must be retained without coercion.")
                if "billing_sources" in usage and (
                        not isinstance(usage["billing_sources"], list)
                        or len(usage["billing_sources"]) > 16
                        or any(not isinstance(value, str) or not value or len(value) > 80
                               for value in usage["billing_sources"])):
                    fail("usage_unknown", "Provider billing-source labels must be retained as bounded strings.")
                if charge > op["reserved"]:
                    fail("cost_bound", "Provider usage exceeded the reviewed reservation.")
            db.execute("UPDATE operations SET state='done',reply=?,reply_sha=?,charged=?,ended=? WHERE id=?",
                (canonical(reply).decode(), digest(reply), charge, self.clock(), op["id"]))
            db.execute("UPDATE jobs SET elapsed=elapsed+? WHERE id=?", (max(0, self.clock()-op["started"]), job["id"]))
            usage = reply.get("usage", {})
            self._event(db, "response_committed", dict(operation_id=op["id"], reply_sha256=digest(reply), charged_microusd=charge,
                actual_provider=usage.get("provider"), actual_model=usage.get("model"),
                input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                cost_basis=usage.get("cost_basis", "reviewed_price_quote")))
        return copy.deepcopy(reply)

    def uncertain(self, claim, operation_id, code, retry_after=0):
        with self._db(write=True) as db:
            op = db.execute("SELECT * FROM operations WHERE id=? AND job_id=?", (operation_id, claim["job_id"])).fetchone()
            if not op or op["lease_token"] != claim["lease_token"] or op["state"] not in ACTIVE:
                return
            db.execute("UPDATE operations SET state='uncertain',problem=? WHERE id=?", (str(code)[:160], operation_id))
            db.execute("UPDATE jobs SET status='uncertain',problem=?,owner=NULL,lease_token=NULL,lease_until=NULL WHERE id=? AND lease_token=?",
                (str(code)[:160], claim["job_id"], claim["lease_token"]))
            if retry_after and isinstance(retry_after, (int, float)) and math.isfinite(retry_after):
                until = self.clock() + min(86400, max(0, retry_after))
                db.execute("INSERT INTO cooldowns VALUES(?,?) ON CONFLICT(provider) DO UPDATE SET until=MAX(until,excluded.until)", (op["provider"], until))
            self._event(db, "outcome_unknown", dict(operation_id=operation_id, reason=str(code)[:160], automatic_retry=False))

    def not_sent(self, claim, operation_id, code, retry_after=0):
        with self._db(write=True) as db:
            self._claim(db, claim)
            op = db.execute("SELECT * FROM operations WHERE id=? AND job_id=?", (operation_id, claim["job_id"])).fetchone()
            if not op or op["state"] != "intent" or op["lease_token"] != claim["lease_token"]:
                fail("stale_result", "Only the owning pre-dispatch validation may release this reservation.")
            db.execute("UPDATE operations SET state='not_sent',ended=?,problem=? WHERE id=?", (self.clock(), str(code)[:160], operation_id))
            db.execute("UPDATE jobs SET ready_at=? WHERE id=?", (self.clock()+max(0, min(60, retry_after)), claim["job_id"]))
            self._event(db, "definitely_not_sent", dict(operation_id=operation_id, reason=str(code)[:160]))

    def checkpoint(self, claim, state):
        state = checkpoint_data(state, self.plan["limits"]["turns"])
        with self._db(write=True) as db:
            self._claim(db, claim)
            if db.execute("SELECT 1 FROM operations WHERE job_id=? AND state IN ('intent','uncertain')", (claim["job_id"],)).fetchone():
                fail("uncertain_execution", "Cannot advance a session past an unresolved operation.")
            db.execute("UPDATE jobs SET checkpoint=?,checkpoint_sha=? WHERE id=?",
                (canonical(state).decode(), digest(state), claim["job_id"]))
        claim["checkpoint"] = copy.deepcopy(state)

    def release(self, claim):
        with self._db(write=True) as db:
            self._claim(db, claim)
            if db.execute("SELECT 1 FROM operations WHERE job_id=? AND state IN ('intent','uncertain')", (claim["job_id"],)).fetchone():
                fail("uncertain_execution", "An unresolved call cannot be returned to the queue.")
            db.execute("UPDATE jobs SET status='queued',owner=NULL,lease_token=NULL,lease_until=NULL WHERE id=?", (claim["job_id"],))

    def block(self, claim, code):
        with self._db(write=True) as db:
            self._claim(db, claim)
            pending = db.execute("SELECT id FROM operations WHERE job_id=? AND state IN ('intent','uncertain')", (claim["job_id"],)).fetchone()
            if pending:
                fail("uncertain_execution", "Preserve unresolved exposure before blocking a session.")
            db.execute("UPDATE jobs SET status='blocked',problem=?,owner=NULL,lease_token=NULL,lease_until=NULL WHERE id=?", (str(code)[:160], claim["job_id"]))
            self._event(db, "session_blocked", dict(job_id=claim["job_id"], reason=str(code)[:160]))

    def complete(self, claim, result):
        result = data(result, 1024 * 1024)
        with self._db(write=True) as db:
            self._claim(db, claim)
            if db.execute("SELECT 1 FROM operations WHERE job_id=? AND state IN ('intent','uncertain')", (claim["job_id"],)).fetchone():
                fail("uncertain_execution", "A session with unresolved calls cannot complete.")
            db.execute("UPDATE jobs SET status='complete',result=?,result_sha=?,owner=NULL,lease_token=NULL,lease_until=NULL WHERE id=?",
                (canonical(result).decode(), digest(result), claim["job_id"]))
            self._event(db, "session_completed", dict(job_id=claim["job_id"], result_sha256=digest(result), mode=self.plan["mode"]))

    def resolve_unknown(self, operation_id, *, actor, evidence_reference, stopped, charged_microusd=None):
        """Operator reconciliation only; never requeues or repeats the old call.

        Unknown billing keeps the full reserve as conservative charged exposure.
        A claim of no effect/charge must be supported by an actual host receipt.
        """
        if stopped is not True or not isinstance(actor, str) or not actor.strip() or not isinstance(evidence_reference, str) or not evidence_reference.strip():
            fail("reconciliation_required", "Inspect the original send and record proof that execution has stopped.")
        with self._db(write=True) as db:
            op = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if not op or op["state"] != "uncertain":
                fail("reconciliation_required", "Select an existing unresolved operation.")
            amount = op["reserved"] if charged_microusd is None else bounded(charged_microusd, 0, 10**15, "charged_microusd")
            db.execute("UPDATE operations SET state='settled',charged=?,ended=?,problem='operator_reconciled_no_retry' WHERE id=?", (amount, self.clock(), operation_id))
            db.execute("UPDATE jobs SET status='blocked',problem='reconciled_no_automatic_retry' WHERE id=? AND status='uncertain'", (op["job_id"],))
            self._event(db, "reconciled", dict(operation_id=operation_id, actor=actor[:160], evidence_reference=evidence_reference[:500],
                charged_microusd=amount, amount_basis="reserved_upper_bound" if charged_microusd is None else "operator_receipt"))
            if amount > op["reserved"] and self._get(db, "control") != "cancelled":
                db.execute("UPDATE meta SET value='paused' WHERE key='control'")
                self._event(db, "billing_overage", dict(operation_id=operation_id, reserved=op["reserved"], observed=amount))
        return self.report()

    def resolve_verified_pre_dispatch_rejection(self, operation_id, *, actor,
            evidence_reference, host_context_live, no_effect_confirmed):
        """Reopen only a narrowly allowlisted browser rejection proven before dispatch.

        Unlike a general uncertain-send reconciliation, this path is limited to
        the CDP file-input lookup error raised before DOM.setFileInputFiles. The
        old operation is permanently marked not_sent; the checkpoint advances
        to a fresh model decision, never replays the rejected tool request.
        """
        if (not isinstance(actor, str) or not actor.strip()
                or not isinstance(evidence_reference, str) or not evidence_reference.strip()
                or host_context_live is not True or no_effect_confirmed is not True):
            fail("reconciliation_required", "A live owned context and pre-dispatch no-effect evidence are required.")
        with self._db(write=True) as db:
            op = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if (not op or op["state"] != "uncertain" or op["kind"] != "tool"
                    or op["problem"] != "host_execution_failed:browser_action_failed:upload_target_missing"):
                fail("reconciliation_required", "Only the exact pre-dispatch file-input lookup rejection can use this recovery.")
            job = db.execute("SELECT * FROM jobs WHERE id=?", (op["job_id"],)).fetchone()
            if not job or job["status"] != "uncertain":
                fail("reconciliation_required", "The matching session is not in an uncertain state.")
            checkpoint = json.loads(job["checkpoint"])
            if digest(checkpoint) != job["checkpoint_sha"]:
                fail("checkpoint_integrity", "The uncertain session checkpoint changed.")
            if checkpoint.get("phase") != "tool" or not isinstance(checkpoint.get("decision"), dict):
                fail("reconciliation_required", "The saved decision is not the rejected tool action.")
            decision = checkpoint["decision"]
            if decision.get("kind") != "tool" or decision.get("tool") != "upload":
                fail("reconciliation_required", "The rejected action is not the allowlisted fixture upload.")
            if db.execute("SELECT 1 FROM operations WHERE job_id=? AND id!=? AND state IN ('intent','uncertain')",
                          (op["job_id"], operation_id)).fetchone():
                fail("uncertain_execution", "Another unresolved operation remains in this session.")
            checkpoint["phase"] = "model"
            checkpoint["decision"] = None
            checkpoint["problem"] = None
            checkpoint.pop("receipt_preview", None)
            note_id = "obs-host-" + digest([operation_id, evidence_reference])[:16]
            observations = checkpoint.setdefault("observations", [])
            if any(row.get("id") == note_id for row in observations):
                fail("reconciliation_required", "This host rejection was already reconciled.")
            observations.append(dict(id=note_id, action="Host pre-dispatch rejection",
                text="The requested file-input selector was not found. The driver rejected the action before DOM.setFileInputFiles; no fixture was selected. Re-observe the current page and choose a fresh safe action. This note is operational context, not UI pass/fail evidence.",
                facts={"host_pre_dispatch_rejection": "upload_target_missing", "no_file_selected": True},
                checks=[], captures=[], artifacts=[]))
            now = self.clock()
            db.execute("UPDATE operations SET state='not_sent',reserved=0,ended=?,problem='verified_pre_dispatch_rejection_no_effect' WHERE id=?",
                       (now, operation_id))
            db.execute("UPDATE jobs SET status='queued',problem=NULL,owner=NULL,lease_token=NULL,lease_until=NULL,checkpoint=?,checkpoint_sha=?,ready_at=? WHERE id=?",
                       (canonical(checkpoint).decode(), digest(checkpoint), now, op["job_id"]))
            self._event(db, "verified_pre_dispatch_rejection", dict(operation_id=operation_id,
                actor=actor[:160], evidence_reference=evidence_reference[:500],
                next_action="fresh_model_decision", old_tool_request_resent=False))
        return self.report()

    def report(self):
        with self._db() as db:
            control = self._get(db, "control")
            charged, held = self._exposure(db)
            counts = {s: 0 for s in ("queued", "running", "complete", "blocked", "uncertain", "cancelled")}
            tasks = []
            for row in db.execute("SELECT * FROM jobs ORDER BY ordinal"):
                counts[row["status"]] += 1
                result = json.loads(row["result"]) if row["result"] else None
                if result is not None and digest(result) != row["result_sha"]:
                    fail("result_integrity", "A committed result changed.")
                checkpoint = json.loads(row["checkpoint"])
                if digest(checkpoint) != row["checkpoint_sha"]:
                    fail("checkpoint_integrity", "The saved session checkpoint changed.")
                tasks.append(dict(job_id=row["id"], persona_id=self.jobs[row["id"]]["task"]["persona_id"],
                    provider=row["provider"], context_id=row["context_id"], status=row["status"],
                    problem=row["problem"], result=result, result_sha256=row["result_sha"],
                    receipt_preview=checkpoint.get("receipt_preview") if result is None else None,
                    first_judgment_sha256=checkpoint.get("first_judgment_sha256")))
            operations = []
            for record in db.execute("SELECT id,job_id,provider,kind,state,request_sha,reply_sha,reserved,charged,started,ended,deadline,problem,reply FROM operations ORDER BY started,id"):
                item = {k: record[k] for k in record.keys() if k != "reply"}
                if record["reply"]:
                    usage = json.loads(record["reply"]).get("usage", {})
                    item.update(actual_provider=usage.get("provider"), actual_model=usage.get("model"),
                                input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                                cost_basis=usage.get("cost_basis", "reviewed_price_quote"))
                operations.append(item)
            approved = self._approved(db)
            tail = db.execute("SELECT sha FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            completed_models = sum(o["state"] == "done" and o["kind"] in {"model", "review"} for o in operations)
            model_intents = sum(o["state"] != "not_sent" and o["kind"] in {"model", "review"} for o in operations)
            uncertain = sum(o["reserved"] for o in operations if o["state"] == "uncertain")
            providers = {}
            for key, info in self.plan["providers"].items():
                active = [o for o in operations if o["provider"] == key and o["kind"] in {"model", "review"} and o["state"] in ACTIVE]
                cool = db.execute("SELECT until FROM cooldowns WHERE provider=?", (key,)).fetchone()
                providers[key] = dict(model=info["spec"]["model"], concurrency=info["spec"]["concurrency"],
                    active_or_uncertain=len(active), cooldown_until=cool[0] if cool else None,
                    endpoint=info["spec"]["endpoint"], credential_scope=info["credential_scope"])
        provider_usage = {}
        for operation in operations:
            if operation.get("state") != "done" or operation.get("kind") not in {"model", "review"}:
                continue
            provider_name = operation.get("actual_provider") or self.plan["providers"][operation["provider"]]["spec"]["key"]
            model_name = operation.get("actual_model") or self.plan["providers"][operation["provider"]]["spec"]["model"]
            key = provider_name + "/" + model_name
            totals = provider_usage.setdefault(key, dict(provider=provider_name, model=model_name, calls=0,
                input_tokens=0, output_tokens=0, charged_or_estimated_microusd=0, cost_bases={}))
            totals["calls"] += 1
            totals["input_tokens"] += operation.get("input_tokens") or 0
            totals["output_tokens"] += operation.get("output_tokens") or 0
            totals["charged_or_estimated_microusd"] += operation.get("charged") or 0
            basis = operation.get("cost_basis") or "reviewed_price_quote"
            totals["cost_bases"][basis] = totals["cost_bases"].get(basis, 0) + 1
        if control == "cancelled":
            next_action = "취소됐습니다. 이미 전송된 요청과 미확정 비용은 원래 실행 기록에서 확인하세요."
        elif not approved:
            next_action = "실제 호출 전 세션 수·전송 대상·최대 비용을 보여 주고 이 계획에 대한 승인을 받으세요."
        elif counts["uncertain"]:
            next_action = "응답이 확인되지 않은 요청은 재전송하지 않습니다. 원래 요청의 종료·사용량을 확인하세요."
        elif control == "paused":
            next_action = "진행 내용이 저장됐습니다. 이어서 실행하면 완료한 호출을 반복하지 않습니다."
        elif counts["blocked"]:
            next_action = "완료한 근거는 보존했습니다. 중단 이유를 확인한 뒤 새 범위를 계획하세요."
        elif counts["queued"]:
            next_action = "대기 중인 세션을 이어서 실행하세요. 속도·예산 한도 때문에 대기할 수 있습니다."
        else:
            next_action = "완료한 관측과 미실행 항목을 함께 검토하세요. 합성 페르소나는 실제 이용자 통계가 아닙니다."
        return dict(schema_version=SCHEMA, plan_sha256=self.plan_sha256, mode=self.plan["mode"], control=control,
            counts=counts, total_sessions=len(tasks), approved=approved, providers=providers,
            budget=dict(currency="USD", unit="micro_USD", ceiling=self.plan["limits"]["budget_microusd"],
                charged_or_settled=charged, reserved=held, uncertain_reserved=uncertain,
                remaining=max(0, self.plan["limits"]["budget_microusd"]-charged-held),
                exceeded_by=max(0, charged+held-self.plan["limits"]["budget_microusd"]),
                guarantee="reviewed_caps_and_prices; provider_billing_not_independently_verified"),
            authored_model_calls=completed_models if self.plan["mode"] == "fixture" else 0,
            actual_model_calls=completed_models if self.plan["mode"] == "live" else 0,
            actual_model_dispatch_intents=model_intents if self.plan["mode"] == "live" else 0,
            model_dispatch_intents=model_intents,
            actual_model_identity_basis="reviewed_host_transport_attestation",
            actual_model_execution=self.plan["mode"] == "live" and completed_models > 0,
            product_ready=False, real_user_evidence=False, os_or_network_sandbox=False,
            tasks=tasks, operations=operations, provider_usage=list(provider_usage.values()),
            event_chain_head=tail[0] if tail else None, next_action=next_action)

    def audit_operations(self):
        count = 0
        with self._db() as db:
            for row in db.execute("SELECT o.*,j.context_id FROM operations o JOIN jobs j ON j.id=o.job_id"):
                request = json.loads(row["request"])
                if (request.get("operation_id") != row["id"] or request.get("context_id") != row["context_id"]
                        or request.get("request_sha256") != row["request_sha"]
                        or digest(request.get("payload")) != row["request_sha"]
                        or request.get("deadline") != row["deadline"]
                        or self.jobs[row["job_id"]]["provider"] != row["provider"]):
                    fail("operation_integrity", "A retained request no longer matches its session and payload digest.")
                if row["state"] == "done":
                    reply = json.loads(row["reply"])
                    if (digest(reply) != row["reply_sha"]
                            or any(reply.get(k) != request[k] for k in ("operation_id", "context_id", "request_sha256"))):
                        fail("response_integrity", "A retained response no longer matches its operation and digest.")
                    if row["kind"] in {"model", "review"}:
                        usage = reply.get("usage", {})
                        spec = self.plan["providers"][row["provider"]]["spec"]
                        bounded(usage.get("input_tokens"), 0, spec["input_token_cap"], "input_tokens")
                        bounded(usage.get("output_tokens"), 0, spec["output_token_cap"], "output_tokens")
                        recorded = usage.get("provider_cost_microusd")
                        expected_charge = (recorded if type(recorded) is int else
                            quote(spec, usage["input_tokens"], usage["output_tokens"]))
                        if expected_charge != row["charged"]:
                            fail("cost_integrity", "Recorded cost differs from provider usage or the reviewed fallback rate.")
                count += 1
        return count

    def audit_events(self):
        previous = "0" * 64
        with self._db() as db:
            for row in db.execute("SELECT * FROM events ORDER BY seq"):
                value = dict(at=row["at"], kind=row["kind"], body=json.loads(row["body"]), previous_sha=row["previous_sha"])
                if row["previous_sha"] != previous or digest(value) != row["sha"]:
                    fail("event_integrity", "The event history changed.")
                previous = row["sha"]
        return previous
