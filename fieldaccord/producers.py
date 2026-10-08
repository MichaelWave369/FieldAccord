"""FA-07 producer-side read-only envelopes and bounded local byte framing.

Vessie and PhiOS implementations remain *upstream-owned*. This SDK accepts their
existing typed export dictionaries, validates known formats, and strips prompt
content before it can leave the producer boundary. It never calls an agent,
executor, memory reader, network service, approval authority, or tool.
"""

from __future__ import annotations

from datetime import timedelta
import json
import secrets
from typing import Any, Mapping

from .acquisition import strict_json
from .continuity import _time
from .core import ContractError, canonical_json, digest, _uuid
from .handoff import (
    MAX_ENVELOPE_BYTES, WorkJournal, sign_export_for_testing, verify_export,
)
from .interop import PHIOS, VESSEL, _phios, _vessie

FRAME_LIMIT = MAX_ENVELOPE_BYTES
MAX_ORIGINAL_BYTES = 262_144
FRAME_HEADER = 4


def _clone(value: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(canonical_json(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("producer: source is not JSON") from exc


def vessie_metadata_export(packet: Any) -> dict[str, Any]:
    """Transform one *genuine-format* DLAM context packet into metadata only.

    Original context items, prompt-bearing fields, raw model identity and raw
    ledger-frontier pointers must NOT leave this producer. The output is a
    *derived* FA-07 packet, not the original source object or an admitted prompt.
    """
    if type(packet) is not dict:
        raise ContractError("producer: Vessie source must be a dictionary")
    try:
        if len(canonical_json(packet)) > MAX_ORIGINAL_BYTES:
            raise ContractError("producer: source packet too large")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("producer: invalid source JSON") from exc
    task = packet.get("task_id")
    _vessie(packet, expected_task_id=task)
    output = {
        "schema_version": "1",
        "packet_id": packet["packet_id"],
        "task_id": task,
        "namespace_id": packet["namespace_id"],
        "agent_id": packet["agent_id"],
        "model_ref": "model-sha256:" + digest(packet["model_ref"]),
        "purpose": "fieldaccord_metadata_observation",
        "target_surface": "fieldaccord",
        "policy_epoch": packet["policy_epoch"],
        "authority_decision_ref": "none:producer-observation",
        "ledger_frontier_ref": "sha256:" + digest(packet["ledger_frontier_ref"]),
        "memory_budget_tokens": 0,
        "items": [],
        "action_authority": "NONE",
    }
    _vessie(output, expected_task_id=task)
    return output


def phios_status_export(observation: Any) -> dict[str, Any]:
    """Accept only an actual-shape PhiOS PhiVessel BRIDGE_STATUS to_dict().

    The PhiOS host must call its own observation service and pass the resulting
    dictionary. This function never requests LEASE_STATUS or EXECUTE.
    """
    if type(observation) is not dict:
        raise ContractError("producer: expected PhiOS to_dict() dictionary")
    _phios(observation)
    return _clone(observation)


def issue_producer_envelope(
    source: Any, *, source_kind: str, work_id: str, issuer_id: str,
    key_id: str, shared_secret: bytes, issued_at: str,
    ttl_seconds: int = 300, nonce: str | None = None,
) -> dict[str, Any]:
    """Package a sanitized source for a separately approved local receiver.

    The receiver must have an already-open WorkIntent pinning the *derived*
    export digest and exact locator. Key provisioning is external; passing a
    shared key proves only its possession, NEVER operator identity or consent.
    """
    _uuid(work_id, "work_id")
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 600:
        raise ContractError("producer: TTL must be 1..600 seconds")
    at = _time(issued_at, "issued_at")
    if source_kind == VESSEL:
        export = vessie_metadata_export(source)
        locator = "vessie:dlam:context:" + export["packet_id"]
    elif source_kind == PHIOS:
        export = phios_status_export(source)
        locator = "phios:phivessel:observation:" + export["source_id"]
    else:
        raise ContractError("producer: unsupported source kind")
    expiry = (at + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    envelope = sign_export_for_testing(
        key_id=key_id, issuer_id=issuer_id, secret=shared_secret,
        nonce=nonce if nonce is not None else secrets.token_hex(16),
        work_id=work_id, source_kind=source_kind, source_locator=locator,
        issued_at=issued_at, expires_at=expiry, export=export,
    )
    # Verify before returning. This enforces the same bounds at both sides.
    verify_export(
        envelope,
        keyring={key_id: {
            "issuer_id": issuer_id,
            "source_kind": source_kind,
            "secret": shared_secret,
        }},
        now=issued_at,
    )
    return envelope


def frame_export(envelope: Any) -> bytes:
    """Create exactly one length-delimited local IPC frame (no socket opened)."""
    try:
        encoded = canonical_json(envelope)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("frame: invalid JSON") from exc
    if not 0 < len(encoded) <= FRAME_LIMIT:
        raise ContractError("frame: export oversized")
    return len(encoded).to_bytes(FRAME_HEADER, "big") + encoded


def decode_export_frame(frame: Any) -> dict[str, Any]:
    """Reject truncation, concatenated extra frames, JSON duplicates and oversize."""
    if type(frame) is not bytes or len(frame) < FRAME_HEADER:
        raise ContractError("frame: missing header")
    n = int.from_bytes(frame[:FRAME_HEADER], "big")
    if not 0 < n <= FRAME_LIMIT or len(frame) != FRAME_HEADER + n:
        raise ContractError("frame: invalid declared length")
    data = strict_json(frame[FRAME_HEADER:])
    if type(data) is not dict:
        raise ContractError("frame: top-level export must be object")
    return data


def admit_export_frame(
    journal: WorkJournal, frame: bytes, *,
    keyring: Mapping[str, Any], now: str, expected_head: str,
    expected_task_id: str | None = None,
) -> dict[str, Any]:
    """Inspect and atomically reserve one serialized export, with no execution."""
    return journal.admit_export(
        decode_export_frame(frame), keyring=keyring,
        now=now, expected_head=expected_head,
        expected_task_id=expected_task_id,
    )
