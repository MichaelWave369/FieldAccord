"""FA-08 opt-in adapters for actual Vessie P1-B and PhiOS observation objects.

Everything stays local and read-only. No subscriber, socket, service startup,
model invocation, permission negotiation or device actuation is performed.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .core import ContractError, SHA256, _match, canonical_json
from .interop import PHIOS, VESSEL, _phios, _vessie
from .producers import (
    MAX_ORIGINAL_BYTES, issue_producer_envelope, phios_status_export,
    vessie_metadata_export,
)

DLAM_SCHEMA = "superphivessel.dlam.context-packet.v0.1"
NATIVE_PACKET_FIELDS = frozenset((
    "schema_version", "schema", "task_id", "namespace_id", "agent_id",
    "genius_profile_ref", "model_ref", "purpose", "target_surface",
    "policy_epoch", "authority_decision_ref", "authority_status",
    "ledger_frontier_ref", "index_manifest_ref", "router_snapshot_ref",
    "tokenizer_id", "memory_budget_tokens", "query_hash",
    "allowed_origins", "action_authority", "disposition",
    "used_memory_tokens", "items", "excluded", "omitted_dependencies",
    "epistemic_mix", "packet_id", "packet_hash",
))
INTEROP_PACKET_FIELDS = frozenset((
    "schema_version", "packet_id", "task_id", "namespace_id", "agent_id",
    "genius_profile_ref", "model_ref", "purpose", "target_surface",
    "policy_epoch", "authority_decision_ref", "ledger_frontier_ref",
    "index_manifest_ref", "router_snapshot_ref", "memory_budget_tokens",
    "items", "action_authority",
))


def _native_source_packet(packet: Any) -> dict[str, Any]:
    """Check the exact sealed P1-B composer output, including domain hash.

    Does not authenticate who created the packet. An attacker can recompute
    unkeyed hashes. A separate source-bound key and operator controls are
    still required before accepting the resulting derived export.
    """
    if type(packet) is not dict or set(packet) != NATIVE_PACKET_FIELDS:
        raise ContractError("native: unsupported Vessie P1-B packet fields")
    try:
        size = len(canonical_json(packet))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ContractError("native: invalid source JSON") from exc
    if size > MAX_ORIGINAL_BYTES:
        raise ContractError("native: source packet oversized")
    if packet["schema"] != DLAM_SCHEMA or packet["schema_version"] != "1":
        raise ContractError("native: unsupported DLAM packet version")
    if packet["action_authority"] != "NONE":
        raise ContractError("native: action authority cannot cross")
    if packet["authority_status"] != "CURRENT" or packet["disposition"] != "READY":
        raise ContractError("native: only current/ready context is eligible for metadata export")
    if type(packet["items"]) is not list or not packet["items"]:
        raise ContractError("native: READY must contain context items")
    if type(packet["used_memory_tokens"]) is not int or packet["used_memory_tokens"] < 0:
        raise ContractError("native: invalid used token count")
    if type(packet["allowed_origins"]) is not list or not all(
        isinstance(x, str) and x for x in packet["allowed_origins"]
    ):
        raise ContractError("native: invalid origin list")
    for key in ("excluded", "omitted_dependencies"):
        if type(packet[key]) is not list:
            raise ContractError(f"native: {key} must be a list")
    if type(packet["epistemic_mix"]) is not dict:
        raise ContractError("native: epistemic mix must be an object")
    for name in ("tokenizer_id",):
        if type(packet[name]) is not str or not packet[name]:
            raise ContractError(f"native: missing {name}")
    _match(packet["query_hash"], SHA256, "native.query_hash")
    _match(packet["packet_hash"], SHA256, "native.packet_hash")
    body = {key: value for key, value in packet.items() if key not in ("packet_id", "packet_hash")}
    expected = hashlib.sha256(b"PV-DLAM-CONTEXT|" + canonical_json(body)).hexdigest()
    if packet["packet_hash"] != expected or packet["packet_id"] != "ctx_" + expected[:32]:
        raise ContractError("native: composer packet digest or identity mismatch")

    # Explicit allowlist drops schema, status, query digest, tokenizer, raw
    # epistemic records, excluded memories and original seal. No user text is
    # copied out of memory items by the projection.
    subset = {key: packet[key] for key in INTEROP_PACKET_FIELDS}
    _vessie(subset, expected_task_id=packet["task_id"])
    return subset


def native_vessie_metadata_export(packet: Any) -> dict[str, Any]:
    """Adapt an actual P1-B sealed context packet into FA-07 scrubbed metadata."""
    return vessie_metadata_export(_native_source_packet(packet))


def issue_native_vessie_envelope(
    packet: Any, *, work_id: str, issuer_id: str, key_id: str,
    shared_secret: bytes, issued_at: str, ttl_seconds: int = 300,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Seal only a validated, newly-derived metadata packet. No transport."""
    metadata = _native_source_packet(packet)
    return issue_producer_envelope(
        metadata, source_kind=VESSEL, work_id=work_id, issuer_id=issuer_id,
        key_id=key_id, shared_secret=shared_secret, issued_at=issued_at,
        ttl_seconds=ttl_seconds, nonce=nonce,
    )


def native_phios_status_export(observation_object: Any) -> dict[str, Any]:
    """Take a native PhiVesselBridgeObservation object, never a lease/action.

    The host calls its trusted read-only observe(BRIDGE_STATUS) itself. This
    function does not dispatch to PhiOS; it only accepts that observation's
    public to_dict() result, preserving the native observation fingerprint.
    """
    if type(observation_object) is dict:
        raise ContractError("native: expected PhiOS observation object, not arbitrary dict")
    method = getattr(observation_object, "to_dict", None)
    if not callable(method):
        raise ContractError("native: PhiOS observation has no to_dict()")
    exported = method()
    if type(exported) is not dict:
        raise ContractError("native: PhiOS to_dict() must return dictionary")
    _phios(exported)
    return phios_status_export(exported)


def issue_native_phios_envelope(
    observation_object: Any, *, work_id: str, issuer_id: str, key_id: str,
    shared_secret: bytes, issued_at: str, ttl_seconds: int = 300,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Seal an already-created native PhiOS status object, never call execute."""
    raw = native_phios_status_export(observation_object)
    return issue_producer_envelope(
        raw, source_kind=PHIOS, work_id=work_id, issuer_id=issuer_id,
        key_id=key_id, shared_secret=shared_secret, issued_at=issued_at,
        ttl_seconds=ttl_seconds, nonce=nonce,
    )
