"""FA-05 offline interoperability projections for Vessie DLAM and PhiOS observations.

This accepts *supplied exports* only. It never calls Vessie, PhiOS, tools, or
network services; it cannot admit a context packet into a model, authorize an
action, mint a lease, or verify an operator's identity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

from .bridge import MAX_BYTES
from .continuity import replay_work
from .core import (
    ContractError, SHA256, _list, _match, _record, _string, canonical_json,
    digest, validate_intent,
)

INTEROP_SCHEMA = "fa.interop_receipt.v0.1"
VESSEL = "vessie.dlam_context_packet.v1"
PHIOS = "phios.phivessel_observation.v0.1"
VESSEL_SCHEMA = "1"
PHIOS_SCHEMA = "phios.phivessel_observation.v0.1"
VERSION = "fa-05.0.1"
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}\Z")
MAX_ITEMS = 64
MAX_BYTES_INTEROP = MAX_BYTES


def _id(value: Any, name: str) -> str:
    return _match(value, IDENT, name)


def _no_authority(value: Any, field: str) -> None:
    if value is not False:
        raise ContractError(f"{field}: cannot carry authority or effects")


def _vessie(packet: Any, *, expected_task_id: str) -> dict[str, Any]:
    fields = {
        "schema_version", "packet_id", "task_id", "namespace_id", "agent_id",
        "model_ref", "purpose", "target_surface", "policy_epoch",
        "authority_decision_ref", "ledger_frontier_ref", "memory_budget_tokens",
        "items", "action_authority",
    }
    optional = {"genius_profile_ref", "index_manifest_ref", "router_snapshot_ref"}
    if type(packet) is not dict:
        raise ContractError("Vessie: expected object")
    if (fields - packet.keys()) or (packet.keys() - fields - optional):
        raise ContractError("Vessie: schema fields missing or unknown")
    if packet["schema_version"] != VESSEL_SCHEMA:
        raise ContractError("Vessie: unsupported context schema")
    for key in ("packet_id", "task_id", "namespace_id", "agent_id", "model_ref"):
        _id(packet[key], f"Vessie.{key}")
    for key in ("purpose", "target_surface", "authority_decision_ref", "ledger_frontier_ref"):
        _string(packet[key], f"Vessie.{key}", 1, 256)
    for key in optional:
        if key in packet and packet[key] is not None:
            _id(packet[key], f"Vessie.{key}")
    if packet["task_id"] != expected_task_id:
        raise ContractError("Vessie: explicit task binding mismatch")
    for key, ceiling in (("policy_epoch", 2**31 - 1), ("memory_budget_tokens", 200000)):
        value = packet[key]
        if type(value) is not int or value < 0 or value > ceiling:
            raise ContractError(f"Vessie.{key}: invalid integer")
    if packet["action_authority"] != "NONE":
        raise ContractError("Vessie: action authority cannot cross the bridge")
    items = _list(packet["items"], "Vessie.items", MAX_ITEMS)
    if any(type(item) is not dict for item in items):
        raise ContractError("Vessie: context item not an object")
    return {
        "projection_kind": "context_metadata_only",
        "packet_id": packet["packet_id"],
        "task_id": packet["task_id"],
        "namespace_id": packet["namespace_id"],
        "agent_id": packet["agent_id"],
        "model_identity_sha256": digest(packet["model_ref"]),
        "policy_epoch_claim": packet["policy_epoch"],
        "ledger_frontier_ref_sha256": digest(packet["ledger_frontier_ref"]),
        "item_count": len(items),
        "context_items_admitted": False,
        "model_context_delivered": False,
        "model_swap_safe_checkpoint_only": True,
    }


def _iso(value: Any, label: str) -> str:
    _string(value, label, 1, 64)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{label}: invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ContractError(f"{label}: timezone required")
    return dt.astimezone(timezone.utc).isoformat()


def _phios(data: Any) -> dict[str, Any]:
    fields = {
        "schema_version", "kind", "observed_at", "payload", "source_id",
        "policy_authority", "operational_authority", "action_authority",
        "execution_authority", "effect_performed", "observation_sha256",
    }
    obj = _record(data, fields, "PhiOS.BridgeObservation")
    if obj["schema_version"] != PHIOS_SCHEMA or obj["kind"] != "BRIDGE_STATUS":
        raise ContractError("PhiOS: only BRIDGE_STATUS v0.1 is supported")
    source_id = _id(obj["source_id"], "PhiOS.source_id")
    when = _iso(obj["observed_at"], "PhiOS.observed_at")
    for key in ("policy_authority", "operational_authority", "action_authority",
                "execution_authority", "effect_performed"):
        _no_authority(obj[key], f"PhiOS.{key}")
    _match(obj["observation_sha256"], SHA256, "PhiOS.observation_sha256")
    body = {key: val for key, val in obj.items() if key != "observation_sha256"}
    if digest(body) != obj["observation_sha256"]:
        raise ContractError("PhiOS: observation fingerprint mismatch")
    p = _record(obj["payload"], {
        "bridge_version", "observe_available", "proposal_available",
        "execution_available", "proposal_creates_authority_request",
        "proposal_creates_lease", "execute_accepts_lease_identity_only",
    }, "PhiOS.bridge_status")
    if p["bridge_version"] != "PV-PHIOS-BRIDGE-0.1":
        raise ContractError("PhiOS: unsupported bridge protocol")
    for name in ("observe_available", "proposal_available", "execution_available"):
        if type(p[name]) is not bool:
            raise ContractError("PhiOS: capability flags must be boolean")
    if (
        p["proposal_creates_authority_request"] is not False
        or p["proposal_creates_lease"] is not False
        or p["execute_accepts_lease_identity_only"] is not True
    ):
        raise ContractError("PhiOS: unsafe declared bridge invariant")
    return {
        "projection_kind": "bridge_status_metadata_only",
        "source_id_sha256": digest(source_id),
        "observed_at_claim": when,
        "observation_sha256": obj["observation_sha256"],
        "observe_available_claim": p["observe_available"],
        "proposal_available_claim": p["proposal_available"],
        "execute_available_claim": p["execution_available"],
        "source_clock_verified": False,
        "source_identity_authenticated": False,
        "lease_evaluated": False,
    }


def inspect_interop(
    intent: Any, events: Any, export: Any, *,
    source_kind: str, source_locator: str,
    expected_payload_sha256: str, expected_state_head: str,
    expected_task_id: str | None = None,
) -> dict[str, Any]:
    """Review a context/observation *export* with frozen WorkIntent binding.

    expected_payload_sha256 and expected_state_head must be caller-held anchors;
    passing values freshly copied from the export is NOT provenance assurance.
    """
    i = validate_intent(intent)
    if "discovery.read" not in i["requested_capabilities"]:
        raise ContractError("interop: discovery.read not requested")
    _match(expected_payload_sha256, SHA256, "expected_payload_sha256")
    _match(expected_state_head, SHA256, "expected_state_head")
    state = replay_work(i, events, expected_head=expected_state_head)
    if state["status"] == "CLOSED":
        raise ContractError("interop: work closed")
    if source_kind not in (VESSEL, PHIOS):
        raise ContractError("interop: unknown source kind")
    if type(export) is not dict:
        raise ContractError("interop: export must be object")
    try:
        size = len(canonical_json(export))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("interop: export not JSON") from exc
    if size > MAX_BYTES_INTEROP:
        raise ContractError("interop: export too large")
    actual = digest(export)
    if actual != expected_payload_sha256:
        raise ContractError("interop: source payload drift")
    if not any(
        ref["reference"] == source_locator and ref["sha256"] == actual
        for ref in i["context_refs"]
    ):
        raise ContractError("interop: source not pinned to WorkIntent")
    if source_kind == VESSEL:
        if expected_task_id is None:
            raise ContractError("interop: explicit Vessie task binding required")
        task_id = _id(expected_task_id, "expected_task_id")
        projection = _vessie(export, expected_task_id=task_id)
        if source_locator != "vessie:dlam:context:" + projection["packet_id"]:
            raise ContractError("interop: Vessie packet locator mismatch")
    else:
        if expected_task_id is not None:
            raise ContractError("interop: PhiOS observation has no task binding")
        projection = _phios(export)
        if source_locator != "phios:phivessel:observation:" + export["source_id"]:
            raise ContractError("interop: PhiOS observation locator mismatch")
    receipt = {
        "schema": INTEROP_SCHEMA,
        "engine": VERSION,
        "work_id": i["work_id"],
        "source_kind": source_kind,
        "source_locator_sha256": digest(source_locator),
        "payload_sha256": actual,
        "state_head_sha256": state["head_hash"],
        "intent_sha256": state["intent_sha256"],
        "disposition": "REVIEW_CANDIDATE",
        "projection": projection,
        "source_identity_authenticated": False,
        "source_freshness_verified": False,
        "authority_granted": False,
        "action_executed": False,
        "notification_dispatched": False,
        "memory_admitted": False,
        "work_history_modified": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt
