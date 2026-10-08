"""FA-02 offline work continuity and attention *advice*.

No tool execution, network I/O, messaging, identity verification, or grant minting.
An event chain is only tamper-evident relative to a separately trusted head.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any

from .core import (
    ACTOR_ID, SHA256, ContractError, _list, _match, _record, _schema,
    _string, _uuid, digest, validate_intent,
)

EVENT_SCHEMA = "fa.work_event.v0.1"
STATE_SCHEMA = "fa.work_state.v0.1"
ATTENTION_SCHEMA = "fa.attention_decision.v0.1"
GENESIS = "0" * 64
UTC_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
KINDS = frozenset((
    "WORK_OPENED", "WORK_NOTE_ADDED", "WORK_CHECKPOINTED", "WORK_BLOCKED",
    "WORK_REVIEW_REQUESTED", "WORK_REOPENED", "WORK_CLOSED",
    "ATTENTION_LEASE_SET", "ATTENTION_LEASE_REVOKED",
))
MODES = {"quiet": 0, "important": 1, "collaborate": 2}
URGENCIES = {"routine": 0, "important": 1, "critical": 2}
MAX_EVENTS = 4096


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or UTC_TIME.fullmatch(value) is None:
        raise ContractError(f"{label}: UTC YYYY-MM-DDTHH:MM:SSZ required")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ContractError(f"{label}: invalid UTC calendar timestamp") from exc


def _actor(value: Any) -> dict[str, str]:
    obj = _record(value, {"kind", "id"}, "event.actor")
    if obj["kind"] not in ("human", "agent"):
        raise ContractError("event.actor.kind: unsupported")
    _match(obj["id"], ACTOR_ID, "event.actor.id")
    return obj


def _payload(kind: str, data: Any) -> dict[str, Any]:
    shape = {
        "WORK_OPENED": {"intent_sha256"},
        "WORK_NOTE_ADDED": {"note"},
        "WORK_CHECKPOINTED": {"summary", "pending_items"},
        "WORK_BLOCKED": {"reason"},
        "WORK_REVIEW_REQUESTED": {"question"},
        "WORK_REOPENED": {"reason"},
        "WORK_CLOSED": {"resolution", "note"},
        "ATTENTION_LEASE_SET": {"lease_id", "recipient_id", "mode", "expires_at"},
        "ATTENTION_LEASE_REVOKED": {"lease_id"},
    }
    if kind not in KINDS:
        raise ContractError("event.kind: unsupported")
    obj = _record(data, shape[kind], f"{kind}.data")
    if kind == "WORK_OPENED":
        _match(obj["intent_sha256"], SHA256, "intent_sha256")
    elif kind in ("WORK_NOTE_ADDED", "WORK_CLOSED"):
        _string(obj["note"], "note", 1, 1000)
        if kind == "WORK_CLOSED" and obj["resolution"] not in (
            "withdrawn", "superseded", "archived"
        ):
            raise ContractError("resolution: closure does not prove success")
    elif kind == "WORK_CHECKPOINTED":
        _string(obj["summary"], "summary", 1, 1000)
        pending = _list(obj["pending_items"], "pending_items", 16)
        for item in pending:
            _string(item, "pending_item", 1, 256)
        if len(set(pending)) != len(pending):
            raise ContractError("pending_items: duplicates")
    elif kind in ("WORK_BLOCKED", "WORK_REOPENED"):
        _string(obj["reason"], "reason", 1, 500)
    elif kind == "WORK_REVIEW_REQUESTED":
        _string(obj["question"], "question", 1, 500)
    elif kind == "ATTENTION_LEASE_SET":
        _uuid(obj["lease_id"], "lease_id")
        _match(obj["recipient_id"], ACTOR_ID, "recipient_id")
        if obj["mode"] not in MODES:
            raise ContractError("lease.mode: unsupported")
        _time(obj["expires_at"], "lease.expires_at")
    elif kind == "ATTENTION_LEASE_REVOKED":
        _uuid(obj["lease_id"], "lease_id")
    return obj


def validate_event(event: Any) -> dict[str, Any]:
    obj = _record(event, {
        "schema", "event_id", "work_id", "sequence", "previous_hash",
        "occurred_at", "actor", "kind", "data", "event_hash",
    }, "WorkEvent")
    _schema(obj["schema"], EVENT_SCHEMA, "WorkEvent")
    _uuid(obj["event_id"], "event_id")
    _uuid(obj["work_id"], "event.work_id")
    if type(obj["sequence"]) is not int or not 1 <= obj["sequence"] <= MAX_EVENTS:
        raise ContractError("event.sequence: 1..4096 integer required")
    _match(obj["previous_hash"], SHA256, "previous_hash")
    _time(obj["occurred_at"], "occurred_at")
    _actor(obj["actor"])
    _payload(obj["kind"], obj["data"])
    _match(obj["event_hash"], SHA256, "event_hash")
    if obj["event_hash"] != digest({k: v for k, v in obj.items() if k != "event_hash"}):
        raise ContractError("event_hash: payload or event modified")
    return obj


def make_event(
    *, event_id: str, work_id: str, sequence: int, previous_hash: str,
    occurred_at: str, actor: dict[str, str], kind: str, data: dict[str, Any],
) -> dict[str, Any]:
    """Convenience builder; hashing creates no signature or authority."""
    obj = {
        "schema": EVENT_SCHEMA,
        "event_id": event_id, "work_id": work_id, "sequence": sequence,
        "previous_hash": previous_hash, "occurred_at": occurred_at,
        "actor": actor, "kind": kind, "data": data,
    }
    obj["event_hash"] = digest(obj)
    return validate_event(obj)


def replay_work(
    intent: Any, events: Any, *, expected_head: str | None = None,
) -> dict[str, Any]:
    """Replay an *untrusted* ordered event stream deterministically.

    expected_head can detect drift only if a caller has independently trusted it.
    This function cannot authenticate event authors or event timestamps.
    """
    base = validate_intent(intent)
    history = _list(events, "events", MAX_EVENTS, minimum=1)
    if expected_head is not None:
        _match(expected_head, SHA256, "expected_head")
    state: dict[str, Any] = {
        "schema": STATE_SCHEMA,
        "work_id": base["work_id"],
        "intent_sha256": digest(base),
        "status": "UNOPENED",
        "sequence": 0,
        "head_hash": GENESIS,
        "note_count": 0,
        "latest_note": None,
        "latest_checkpoint": None,
        "review_question": None,
        "active_attention_lease": None,
        "authority_granted": False,
        "action_executed": False,
        "notification_dispatched": False,
    }
    prior_time = None
    seen_ids: set[str] = set()

    for event in history:
        e = validate_event(event)
        if e["work_id"] != base["work_id"]:
            raise ContractError("replay: work_id mismatch")
        if e["event_id"] in seen_ids:
            raise ContractError("replay: repeated event_id")
        seen_ids.add(e["event_id"])
        if e["sequence"] != state["sequence"] + 1:
            raise ContractError("replay: gap or duplicate sequence")
        if e["previous_hash"] != state["head_hash"]:
            raise ContractError("replay: hash-chain continuity failure")
        when = _time(e["occurred_at"], "occurred_at")
        if prior_time is not None and when < prior_time:
            raise ContractError("replay: event time moved backwards")
        prior_time = when
        kind, data, status = e["kind"], e["data"], state["status"]

        if kind == "WORK_OPENED":
            if status != "UNOPENED" or e["sequence"] != 1:
                raise ContractError("replay: WORK_OPENED must be first and unique")
            if data["intent_sha256"] != digest(base):
                raise ContractError("replay: bound WorkIntent changed")
            state["status"] = "OPEN"

        elif status in ("UNOPENED", "CLOSED"):
            raise ContractError("replay: event before opening or after closure")

        elif kind == "WORK_NOTE_ADDED":
            state["latest_note"] = data["note"]
            state["note_count"] += 1

        elif kind == "WORK_CHECKPOINTED":
            state["latest_checkpoint"] = {
                "summary": data["summary"],
                "pending_items": list(data["pending_items"]),
                "event_id": e["event_id"],
            }

        elif kind == "WORK_BLOCKED":
            if status not in ("OPEN", "NEEDS_REVIEW"):
                raise ContractError("replay: invalid transition to BLOCKED")
            state["status"] = "BLOCKED"
            state["review_question"] = None

        elif kind == "WORK_REVIEW_REQUESTED":
            if status not in ("OPEN", "BLOCKED"):
                raise ContractError("replay: invalid transition to NEEDS_REVIEW")
            state["status"] = "NEEDS_REVIEW"
            state["review_question"] = data["question"]

        elif kind == "WORK_REOPENED":
            if status not in ("BLOCKED", "NEEDS_REVIEW"):
                raise ContractError("replay: invalid transition to OPEN")
            state["status"] = "OPEN"
            state["review_question"] = None

        elif kind == "WORK_CLOSED":
            state["status"] = "CLOSED"
            state["review_question"] = None
            state["active_attention_lease"] = None

        elif kind == "ATTENTION_LEASE_SET":
            if e["actor"]["kind"] != "human":
                raise ContractError("replay: agent cannot claim to set attention preferences")
            if state["active_attention_lease"] is not None:
                raise ContractError("replay: revoke prior attention lease before replacement")
            if MODES[data["mode"]] > MODES[base["attention_policy"]]:
                raise ContractError("replay: lease expands intent attention policy")
            expires = _time(data["expires_at"], "lease.expires_at")
            if not when < expires <= when + timedelta(days=1):
                raise ContractError("replay: lease expiration outside 24h bounds")
            state["active_attention_lease"] = {
                "lease_id": data["lease_id"],
                "issuer_id": e["actor"]["id"],
                "recipient_id": data["recipient_id"],
                "mode": data["mode"],
                "issued_at": e["occurred_at"],
                "expires_at": data["expires_at"],
            }

        elif kind == "ATTENTION_LEASE_REVOKED":
            lease = state["active_attention_lease"]
            if lease is None or data["lease_id"] != lease["lease_id"]:
                raise ContractError("replay: nonexistent or wrong lease to revoke")
            if e["actor"]["kind"] != "human" or e["actor"]["id"] != lease["issuer_id"]:
                raise ContractError("replay: lease issuer mismatch")
            state["active_attention_lease"] = None

        else:
            raise ContractError("replay: unsupported event")

        state["sequence"] = e["sequence"]
        state["head_hash"] = e["event_hash"]

    if expected_head is not None and state["head_hash"] != expected_head:
        raise ContractError("replay: head differs from supplied anchor")
    return state


def attention_review(
    state: Any, *, recipient_id: str, urgency: str, at: str,
) -> dict[str, Any]:
    """Recommend whether human review is worth surfacing; NEVER send a message.

    No claimed human issuer is authenticated. This decision does NOT grant
    notification, tool, contact, or execution authority.
    """
    fields = {
        "schema", "work_id", "intent_sha256", "status", "sequence",
        "head_hash", "note_count", "latest_note", "latest_checkpoint",
        "review_question", "active_attention_lease", "authority_granted",
        "action_executed", "notification_dispatched",
    }
    obj = _record(state, fields, "WorkState")
    _schema(obj["schema"], STATE_SCHEMA, "WorkState")
    _uuid(obj["work_id"], "work_id")
    _match(obj["head_hash"], SHA256, "head_hash")
    _match(recipient_id, ACTOR_ID, "recipient_id")
    now = _time(at, "attention.at")
    if urgency not in URGENCIES:
        raise ContractError("urgency: invalid")
    if obj["authority_granted"] is not False or obj["action_executed"] is not False or obj["notification_dispatched"] is not False:
        raise ContractError("WorkState: forbidden side-effect claims")
    lease = obj["active_attention_lease"]
    decision, reason = "HOLD", "NO_LEASE"
    if obj["status"] == "CLOSED":
        reason = "WORK_CLOSED"
    elif lease is None:
        reason = "NO_LEASE"
    else:
        l = _record(lease, {"lease_id", "issuer_id", "recipient_id", "mode", "issued_at", "expires_at"}, "active_attention_lease")
        _uuid(l["lease_id"], "lease_id")
        _match(l["recipient_id"], ACTOR_ID, "lease.recipient_id")
        _match(l["issuer_id"], ACTOR_ID, "lease.issuer_id")
        if l["mode"] not in MODES:
            raise ContractError("lease.mode: invalid")
        if l["recipient_id"] != recipient_id:
            reason = "WRONG_RECIPIENT"
        elif now < _time(l["issued_at"], "lease.issued_at"):
            reason = "NOT_YET_ACTIVE"
        elif now >= _time(l["expires_at"], "lease.expires_at"):
            reason = "EXPIRED"
        elif (
            (l["mode"] == "quiet" and urgency != "critical")
            or (l["mode"] == "important" and urgency == "routine")
        ):
            reason = "FILTERED"
        else:
            decision, reason = "REVIEW_CANDIDATE", "LEASE_FILTER_MATCH"
    return {
        "schema": ATTENTION_SCHEMA,
        "work_id": obj["work_id"],
        "recipient_id": recipient_id,
        "urgency": urgency,
        "at": at,
        "decision": decision,
        "reason": reason,
        "operator_verification_required": True,
        "notification_dispatched": False,
        "authority_granted": False,
    }
