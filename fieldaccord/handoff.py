"""FA-06 local shared-key export admission and transactional WorkEvent journal.

Possession of an HMAC key is NOT proof of a human/device identity, consent, policy
authority, or execution authority. An explicit WorkIntent pin is also required.
No network, model invocation, notifications, or action execution occurs here.
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from .continuity import _time, replay_work, validate_event
from .core import (
    ContractError, SHA256, _match, _record, _uuid,
    canonical_json, digest, validate_intent,
)
from .interop import PHIOS, VESSEL, inspect_interop

ENVELOPE_SCHEMA = "fa.authenticated_export.v0.1"
HANDOFF_SCHEMA = "fa.handoff_receipt.v0.1"
KEY_ID = re.compile(r"[a-z][a-z0-9._-]{0,63}\Z")
ISSUER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}\Z")
NONCE = re.compile(r"[0-9a-f]{32}\Z")
MAX_EXPORT_BYTES = 65_536
MAX_ENVELOPE_BYTES = 75_000
MAX_TTL = timedelta(minutes=10)

ENVELOPE_FIELDS = {
    "schema", "key_id", "issuer_id", "nonce", "work_id",
    "source_kind", "source_locator", "issued_at", "expires_at",
    "export_sha256", "export", "mac_sha256",
}


def _key_config(keyring: Mapping[str, Any], key_id: str, issuer: str, kind: str) -> bytes:
    if type(keyring) is not dict or key_id not in keyring:
        raise ContractError("handoff: unknown/revoked signing key")
    record = _record(keyring[key_id], {"issuer_id", "source_kind", "secret"}, "keyring.entry")
    if record["issuer_id"] != issuer or record["source_kind"] != kind:
        raise ContractError("handoff: key not assigned to claimed issuer/source")
    key = record["secret"]
    if type(key) is not bytes or len(key) < 32:
        raise ContractError("handoff: trusted key must be >=32 random bytes")
    return key


def _envelope_body(obj: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in obj.items() if k != "mac_sha256"}


def sign_export_for_testing(
    *, key_id: str, issuer_id: str, secret: bytes, nonce: str, work_id: str,
    source_kind: str, source_locator: str, issued_at: str, expires_at: str,
    export: dict[str, Any],
) -> dict[str, Any]:
    """Fixture/integrator helper. Do not commit production keys or signed secrets."""
    body = dict(schema=ENVELOPE_SCHEMA, key_id=key_id, issuer_id=issuer_id,
                nonce=nonce, work_id=work_id, source_kind=source_kind,
                source_locator=source_locator, issued_at=issued_at,
                expires_at=expires_at, export_sha256=digest(export),
                export=export)
    if type(secret) is not bytes or len(secret) < 32:
        raise ContractError("handoff: signing key must be >=32 bytes")
    result = dict(body)
    result["mac_sha256"] = hmac.new(
        secret, canonical_json(body), hashlib.sha256
    ).hexdigest()
    return result


def verify_export(
    envelope: Any, *, keyring: Mapping[str, Any], now: str,
) -> dict[str, Any]:
    """Authenticate configured shared-key possession; never source identity or consent."""
    obj = _record(envelope, ENVELOPE_FIELDS, "AuthenticatedExport")
    if obj["schema"] != ENVELOPE_SCHEMA:
        raise ContractError("handoff: unsupported schema")
    _match(obj["key_id"], KEY_ID, "key_id")
    _match(obj["issuer_id"], ISSUER_ID, "issuer_id")
    _match(obj["nonce"], NONCE, "nonce")
    _uuid(obj["work_id"], "work_id")
    _match(obj["export_sha256"], SHA256, "export_sha256")
    _match(obj["mac_sha256"], SHA256, "mac_sha256")
    if obj["source_kind"] not in (VESSEL, PHIOS):
        raise ContractError("handoff: unsupported source kind")
    if type(obj["source_locator"]) is not str or not 1 <= len(obj["source_locator"]) <= 512:
        raise ContractError("handoff: invalid source locator")
    try:
        encoded = canonical_json(obj)
        payload = canonical_json(obj["export"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("handoff: invalid JSON") from exc
    if type(obj["export"]) is not dict or len(payload) > MAX_EXPORT_BYTES or len(encoded) > MAX_ENVELOPE_BYTES:
        raise ContractError("handoff: payload/envelope oversized")
    issued = _time(obj["issued_at"], "issued_at")
    expires = _time(obj["expires_at"], "expires_at")
    at = _time(now, "now")
    if not (issued <= at < expires and issued < expires <= issued + MAX_TTL):
        raise ContractError("handoff: not current or exceeds 10-minute TTL")
    if digest(obj["export"]) != obj["export_sha256"]:
        raise ContractError("handoff: export changed")
    secret = _key_config(keyring, obj["key_id"], obj["issuer_id"], obj["source_kind"])
    expected_mac = hmac.new(secret, canonical_json(_envelope_body(obj)), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_mac, obj["mac_sha256"]):
        raise ContractError("handoff: MAC verification failed")
    return obj


class WorkJournal:
    """One local SQLite/WAL journal, transactional single-writer CAS and nonce guard.

    Not an unmodifiable database, a global consensus service, a cryptographic
    actor attestation or an OS isolation boundary. DB directory must be secured
    by the local operator. Local backups must preserve replay nonce rows.
    """

    def __init__(self, path: str | Path):
        self.connection = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS work (
                work_id TEXT PRIMARY KEY, intent_json TEXT NOT NULL,
                intent_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS work_event (
                work_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                event_id TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL,
                event_hash TEXT NOT NULL, PRIMARY KEY(work_id, sequence),
                FOREIGN KEY(work_id) REFERENCES work(work_id)
            );
            CREATE TABLE IF NOT EXISTS export_nonce (
                issuer_id TEXT NOT NULL, nonce TEXT NOT NULL,
                work_id TEXT NOT NULL, envelope_sha256 TEXT NOT NULL,
                PRIMARY KEY(issuer_id, nonce)
            );
        """)

    def __enter__(self) -> "WorkJournal":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _load(self, work_id: str) -> tuple[dict, list[dict]]:
        record = self.connection.execute(
            "SELECT intent_json, intent_sha256 FROM work WHERE work_id=?", (work_id,)
        ).fetchone()
        if record is None:
            raise ContractError("journal: unknown work ID")
        try:
            intent = json.loads(record[0])
            rows = self.connection.execute(
                "SELECT event_json FROM work_event WHERE work_id=? ORDER BY sequence",
                (work_id,),
            ).fetchall()
            events = [json.loads(row[0]) for row in rows]
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ContractError("journal: unreadable records") from exc
        if digest(intent) != record[1]:
            raise ContractError("journal: stored intent changed")
        return intent, events

    def begin_work(self, intent: Any, opening_event: Any) -> dict[str, Any]:
        i = validate_intent(intent)
        state = replay_work(i, [opening_event])
        if state["sequence"] != 1 or state["status"] != "OPEN":
            raise ContractError("journal: first event must open work")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute(
                "INSERT INTO work(work_id,intent_json,intent_sha256) VALUES(?,?,?)",
                (i["work_id"], canonical_json(i).decode(), digest(i)),
            )
            self.connection.execute(
                "INSERT INTO work_event(work_id,sequence,event_id,event_json,event_hash) VALUES(?,?,?,?,?)",
                (i["work_id"], 1, opening_event["event_id"],
                 canonical_json(opening_event).decode(), opening_event["event_hash"]),
            )
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return state

    def state(self, work_id: str, *, expected_head: str | None = None) -> dict[str, Any]:
        _uuid(work_id, "work_id")
        intent, events = self._load(work_id)
        return replay_work(intent, events, expected_head=expected_head)

    def append_event(
        self, event: Any, *, expected_head: str,
    ) -> dict[str, Any]:
        e = validate_event(event)
        _match(expected_head, SHA256, "expected_head")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            intent, events = self._load(e["work_id"])
            old = replay_work(intent, events)
            if old["head_hash"] != expected_head:
                raise ContractError("journal: optimistic head conflict")
            after = replay_work(intent, events + [e])
            self.connection.execute(
                "INSERT INTO work_event(work_id,sequence,event_id,event_json,event_hash) VALUES(?,?,?,?,?)",
                (e["work_id"], e["sequence"], e["event_id"],
                 canonical_json(e).decode(), e["event_hash"]),
            )
            self.connection.execute("COMMIT")
            return after
        except Exception:
            self.connection.execute("ROLLBACK")
            raise

    def admit_export(
        self, envelope: Any, *, keyring: Mapping[str, Any],
        now: str, expected_head: str, expected_task_id: str | None = None,
    ) -> dict[str, Any]:
        """Atomic verify + local replay reservation. No effects or memory admission."""
        _match(expected_head, SHA256, "expected_head")
        verified = verify_export(envelope, keyring=keyring, now=now)
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            intent, events = self._load(verified["work_id"])
            state = replay_work(intent, events, expected_head=expected_head)
            if state["status"] == "CLOSED":
                raise ContractError("journal: work closed")
            reviewed = inspect_interop(
                intent, events, verified["export"],
                source_kind=verified["source_kind"],
                source_locator=verified["source_locator"],
                expected_payload_sha256=verified["export_sha256"],
                expected_state_head=expected_head,
                expected_task_id=expected_task_id,
            )
            # This INSERT is protected by the same SQLite single-writer transaction.
            # Replays are rejected even across process restarts of the same database.
            self.connection.execute(
                "INSERT INTO export_nonce(issuer_id,nonce,work_id,envelope_sha256) VALUES(?,?,?,?)",
                (verified["issuer_id"], verified["nonce"], verified["work_id"], digest(verified)),
            )
            result = {
                "schema": HANDOFF_SCHEMA,
                "work_id": verified["work_id"],
                "envelope_sha256": digest(verified),
                "key_id": verified["key_id"],
                "issuer_id_claim": verified["issuer_id"],
                "nonce": verified["nonce"],
                "shared_key_verified": True,
                "person_or_device_identity_authenticated": False,
                "operator_consent_verified": False,
                "export_received": True,
                "interop_receipt": reviewed,
                "authority_granted": False,
                "action_executed": False,
                "notification_dispatched": False,
                "memory_admitted": False,
            }
            self.connection.execute("COMMIT")
            return result
        except sqlite3.IntegrityError as exc:
            self.connection.execute("ROLLBACK")
            raise ContractError("journal: export replay or duplicate nonce") from exc
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
