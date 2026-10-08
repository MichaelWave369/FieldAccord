"""FA-03: read-only, pinned snapshot adapters for existing Field ecosystem records.

No network, filesystem I/O, execution, messaging, grant issuance, or event writes.
Digest binding only establishes consistency with a caller-supplied anchor.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .core import (
    ContractError, SHA256, _list, _match, _record, _schema, _string,
    _uuid, canonical_json, digest, validate_intent,
)
from .continuity import replay_work

SNAPSHOT_SCHEMA = "fa.source_snapshot.v0.1"
BRIDGE_SCHEMA = "fa.bridge_receipt.v0.1"
BRIDGE_ENGINE = "fa-03.0.1"
FIELDDECK = "fielddeck.manifest.v0.6"
NBG = "nbg.epistemic_memory.v1"
FIELDDECK_LOCATOR = "github:MichaelWave369/FieldDeck/public/fielddeck.manifest.json"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
MAX_BYTES = 65_536
MAX_ACTIONS = 64
MAX_EVIDENCE = 32


def _nonempty_id(value: Any, label: str) -> str:
    return _match(value, ID, label)


def _flag(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{label}: boolean required")
    return value


def _fielddeck(payload: Any) -> tuple[dict[str, Any], bool]:
    """Project only the published discovery fields, never commands or URLs."""
    if type(payload) is not dict:
        raise ContractError("FieldDeck: expected object")
    if payload.get("name") != "FieldDeck" or payload.get("schema_version") != "0.6.0":
        raise ContractError("FieldDeck: unsupported manifest")
    policy = payload.get("execution_policy")
    if type(policy) is not dict:
        raise ContractError("FieldDeck: missing execution policy")
    if (
        policy.get("default") != "deny"
        or policy.get("require_authenticated_runner") is not True
        or policy.get("freeform_shell") is not False
    ):
        raise ContractError("FieldDeck: cannot rely on discovery with unsafe policy")
    actions = _list(payload.get("actions"), "FieldDeck.actions", MAX_ACTIONS)
    output = []
    seen: set[str] = set()
    for action in actions:
        if type(action) is not dict:
            raise ContractError("FieldDeck: action must be object")
        identifier = _nonempty_id(action.get("id"), "FieldDeck.action.id")
        if identifier in seen:
            raise ContractError("FieldDeck: duplicate action id")
        seen.add(identifier)
        kind, status, risk = (
            action.get("kind"), action.get("status"), action.get("risk")
        )
        if kind not in ("workflow", "copy", "export", "link", "future"):
            raise ContractError("FieldDeck: unsupported action kind")
        if status not in ("ready", "locked"):
            raise ContractError("FieldDeck: unsupported status")
        if risk not in ("low", "medium", "high"):
            raise ContractError("FieldDeck: unsupported risk")
        if kind == "future" and status != "locked":
            raise ContractError("FieldDeck: future action cannot be ready")
        output.append({
            "id": identifier,
            "kind": kind,
            "status": status,
            "risk": risk,
        })
    output.sort(key=lambda a: a["id"])
    return {
        "projection_kind": "discovery_only",
        "action_count": len(output),
        "actions": output,
    }, False


def _nbg(payload: Any, locator: str) -> tuple[dict[str, Any], bool]:
    """Never surface memory content as tool instructions or claim verification."""
    if type(payload) is not dict or payload.get("schemaVersion") != "NBG_EPISTEMIC_1":
        raise ContractError("NBG: unsupported memory record")
    memory_id = _nonempty_id(payload.get("memoryId"), "NBG.memoryId")
    if locator != "nbg:memory:" + memory_id:
        raise ContractError("NBG: memory ID and source locator mismatch")
    _string(payload.get("recordFingerprint"), "NBG.recordFingerprint", 1, 128)
    epistemic = payload.get("epistemic")
    if type(epistemic) is not dict:
        raise ContractError("NBG: missing epistemic object")
    origin = epistemic.get("origin")
    if origin not in (
        "OBSERVED", "VERIFIED", "INFERRED", "DREAMED", "SIMULATED", "UNKNOWN"
    ):
        raise ContractError("NBG: invalid origin claim")
    confidence = epistemic.get("confidence")
    if (
        type(confidence) not in (int, float)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise ContractError("NBG: invalid confidence claim")
    authority = epistemic.get("authority")
    if type(authority) is not dict:
        raise ContractError("NBG: missing authority fields")
    for key in ("retainable", "reasoningUsable", "actionAuthorized"):
        _flag(authority.get(key), "NBG.authority." + key)
    evidence = _list(epistemic.get("evidence"), "NBG.evidence", MAX_EVIDENCE)
    ids: list[str] = []
    for item in evidence:
        if type(item) is not dict:
            raise ContractError("NBG: evidence must be object")
        ids.append(_nonempty_id(item.get("evidenceId"), "NBG.evidenceId"))
        _string(item.get("evidenceFingerprint"), "NBG.evidenceFingerprint", 1, 128)
        _string(item.get("kind"), "NBG.evidence.kind", 1, 128)
    if len(ids) != len(set(ids)):
        raise ContractError("NBG: duplicate evidence ID")
    claimed = authority["actionAuthorized"]
    return {
        "projection_kind": "untrusted_epistemic_metadata",
        "memory_id": memory_id,
        "origin_claim": origin,
        "confidence_claim": confidence,
        "evidence_ids": sorted(ids),
        "record_fingerprint_claim": payload["recordFingerprint"],
        "source_claims_action_authority": claimed,
        "content_redacted": True,
    }, claimed


def inspect_snapshot(
    intent: Any, events: Any, snapshot: Any,
    *, expected_state_head: str, expected_payload_sha256: str,
) -> dict[str, Any]:
    """Inspect a caller-supplied snapshot; never authorize or invoke anything.

    Both expected anchors MUST be obtained out-of-band by the caller.
    We also demand source digest and locator were listed in the original,
    intent-bound context. This prevents accidental cross-undertaking mixing,
    not malicious-source replacement when the caller itself is compromised.
    """
    base = validate_intent(intent)
    if "discovery.read" not in base["requested_capabilities"]:
        raise ContractError("bridge: discovery.read not requested by WorkIntent")
    _match(expected_state_head, SHA256, "expected_state_head")
    _match(expected_payload_sha256, SHA256, "expected_payload_sha256")
    state = replay_work(base, events, expected_head=expected_state_head)
    if state["status"] == "CLOSED":
        raise ContractError("bridge: work already closed")
    obj = _record(snapshot, {
        "schema", "capture_id", "work_id", "source_kind",
        "source_locator", "payload_sha256", "payload",
    }, "SourceSnapshot")
    _schema(obj["schema"], SNAPSHOT_SCHEMA, "SourceSnapshot")
    _uuid(obj["capture_id"], "capture_id")
    _uuid(obj["work_id"], "snapshot.work_id")
    if obj["work_id"] != base["work_id"]:
        raise ContractError("bridge: cross-work snapshot")
    if obj["source_kind"] not in (FIELDDECK, NBG):
        raise ContractError("bridge: unsupported source kind")
    locator = _string(obj["source_locator"], "source_locator", 1, 512)
    _match(obj["payload_sha256"], SHA256, "payload_sha256")
    try:
        encoded = canonical_json(obj["payload"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("bridge: invalid JSON payload") from exc
    if len(encoded) > MAX_BYTES:
        raise ContractError("bridge: payload exceeds 64KiB limit")
    actual = digest(obj["payload"])
    if actual != obj["payload_sha256"] or actual != expected_payload_sha256:
        raise ContractError("bridge: source digest drift")
    matching = [
        ref for ref in base["context_refs"]
        if ref["reference"] == locator
        and ref["sha256"] == actual
    ]
    if len(matching) != 1:
        raise ContractError("bridge: source not pinned by WorkIntent")
    if obj["source_kind"] == FIELDDECK:
        if locator != FIELDDECK_LOCATOR:
            raise ContractError("bridge: unexpected FieldDeck locator")
        projection, claimed = _fielddeck(obj["payload"])
    else:
        projection, claimed = _nbg(obj["payload"], locator)

    receipt = {
        "schema": BRIDGE_SCHEMA,
        "engine": BRIDGE_ENGINE,
        "work_id": base["work_id"],
        "capture_id": obj["capture_id"],
        "source_kind": obj["source_kind"],
        "source_locator": locator,
        "source_payload_sha256": actual,
        "state_head_sha256": state["head_hash"],
        "intent_sha256": state["intent_sha256"],
        "source_epistemic_label": matching[0]["epistemic"],
        "disposition": "QUARANTINED_AUTHORITY_CLAIM" if claimed else "REVIEW_CANDIDATE",
        "projection": projection,
        "provenance_authenticated": False,
        "source_claims_action_authority": claimed,
        "authority_granted": False,
        "action_executed": False,
        "notification_dispatched": False,
        "history_modified": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt
