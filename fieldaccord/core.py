"""Deterministic offline contract admission. This module never executes a tool.

FA-01 deliberately has no allow/execute outcome or authority-grant API.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

INTENT_SCHEMA = "fa.work_intent.v0.1"
CAPABILITY_SCHEMA = "fa.capability_declaration.v0.1"
PROPOSAL_SCHEMA = "fa.action_proposal.v0.1"
RECEIPT_SCHEMA = "fa.work_receipt.v0.1"
ENGINE = "fa-01.0.1"
CAPABILITY_ID = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
RESOURCE = re.compile(r"[^\s*]{1,512}\Z")
ACTOR_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}\Z")


class ContractError(ValueError):
    """Untrusted input does not meet the frozen contract."""


def _record(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{label}: expected object")
    missing = fields - value.keys()
    extra = value.keys() - fields
    if missing or extra:
        raise ContractError(
            f"{label}: missing={sorted(missing)} extra={sorted(extra)}"
        )
    return value


def _string(value: Any, label: str, minimum: int = 1, maximum: int = 2000) -> str:
    if not isinstance(value, str) or len(value) < minimum or len(value) > maximum or not value.strip():
        raise ContractError(f"{label}: invalid text")
    return value


def _match(value: Any, regex: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or regex.fullmatch(value) is None:
        raise ContractError(f"{label}: invalid format")
    return value


def _uuid(value: Any, label: str) -> None:
    try:
        parsed = uuid.UUID(value) if isinstance(value, str) else None
    except (ValueError, AttributeError):
        parsed = None
    if parsed is None or parsed.version != 4 or str(parsed) != value:
        raise ContractError(f"{label}: canonical UUIDv4 required")


def _list(value: Any, label: str, maximum: int, minimum: int = 0) -> list[Any]:
    if type(value) is not list or len(value) < minimum or len(value) > maximum:
        raise ContractError(f"{label}: invalid list length")
    return value


def _unique(items: list[str], label: str) -> None:
    if len(set(items)) != len(items):
        raise ContractError(f"{label}: duplicate entry")


def _schema(value: Any, expected: str, label: str) -> None:
    if value != expected:
        raise ContractError(f"{label}: unsupported schema version")


def validate_intent(intent: Any) -> dict[str, Any]:
    obj = _record(intent, {
        "schema", "work_id", "initiator", "objective",
        "requested_capabilities", "attention_policy", "context_refs",
    }, "WorkIntent")
    _schema(obj["schema"], INTENT_SCHEMA, "WorkIntent")
    _uuid(obj["work_id"], "work_id")
    actor = _record(obj["initiator"], {"kind", "id"}, "initiator")
    if actor["kind"] not in ("human", "agent"):
        raise ContractError("initiator.kind: unsupported")
    _match(actor["id"], ACTOR_ID, "initiator.id")
    _string(obj["objective"], "objective", 10, 2000)
    requested = _list(obj["requested_capabilities"], "requested_capabilities", 16)
    for identifier in requested:
        _match(identifier, CAPABILITY_ID, "requested_capability")
    _unique(requested, "requested_capabilities")
    if obj["attention_policy"] not in ("quiet", "important", "collaborate"):
        raise ContractError("attention_policy: invalid mode")
    refs = _list(obj["context_refs"], "context_refs", 32)
    identifiers = []
    for index, item in enumerate(refs):
        ref = _record(item, {"reference", "sha256", "epistemic"}, f"context_refs[{index}]")
        identifiers.append(_match(ref["reference"], RESOURCE, "context.reference"))
        _match(ref["sha256"], SHA256, "context.sha256")
        if ref["epistemic"] not in ("observation", "inference", "unverified"):
            raise ContractError("context.epistemic: invalid")
    _unique(identifiers, "context_refs")
    return obj


def validate_capability(capability: Any) -> dict[str, Any]:
    obj = _record(capability, {
        "schema", "provider_id", "capability_id", "effect", "scope",
    }, "CapabilityDeclaration")
    _schema(obj["schema"], CAPABILITY_SCHEMA, "CapabilityDeclaration")
    _match(obj["provider_id"], ACTOR_ID, "provider_id")
    _match(obj["capability_id"], CAPABILITY_ID, "capability_id")
    if obj["effect"] not in ("read", "write", "external", "physical"):
        raise ContractError("effect: invalid")
    scope = _list(obj["scope"], "scope", 32, minimum=1)
    for resource in scope:
        _match(resource, RESOURCE, "scope.resource")
    _unique(scope, "scope")
    return obj


def validate_proposal(proposal: Any) -> dict[str, Any]:
    obj = _record(proposal, {
        "schema", "proposal_id", "work_id", "capability_id",
        "action", "resource", "payload_sha256", "evidence_refs",
    }, "ActionProposal")
    _schema(obj["schema"], PROPOSAL_SCHEMA, "ActionProposal")
    _uuid(obj["proposal_id"], "proposal_id")
    _uuid(obj["work_id"], "proposal.work_id")
    _match(obj["capability_id"], CAPABILITY_ID, "proposal.capability_id")
    _match(obj["action"], CAPABILITY_ID, "proposal.action")
    _match(obj["resource"], RESOURCE, "proposal.resource")
    _match(obj["payload_sha256"], SHA256, "payload_sha256")
    refs = _list(obj["evidence_refs"], "evidence_refs", 32)
    for reference in refs:
        _match(reference, RESOURCE, "evidence_ref")
    _unique(refs, "evidence_refs")
    return obj


def canonical_json(value: Any) -> bytes:
    """Stable serialization; does NOT establish trust or a digital signature."""
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def assess(intent: Any, capability: Any, proposal: Any) -> dict[str, Any]:
    """Admit for human review only; never authorize or perform external actions.

    A capability declaration is untrusted input, and no grant can be submitted
    to this function. Consequential actions must be approved and revalidated
    by a separate authority-bearing execution adapter in a future rung.
    """
    i = validate_intent(intent)
    c = validate_capability(capability)
    p = validate_proposal(proposal)
    if p["work_id"] != i["work_id"]:
        decision, reason = "BLOCKED", "WORK_ID_MISMATCH"
    elif p["capability_id"] != c["capability_id"]:
        decision, reason = "BLOCKED", "CAPABILITY_MISMATCH"
    elif p["capability_id"] not in i["requested_capabilities"]:
        decision, reason = "BLOCKED", "UNREQUESTED_CAPABILITY"
    elif p["resource"] not in c["scope"]:
        decision, reason = "BLOCKED", "RESOURCE_OUT_OF_SCOPE"
    elif not set(p["evidence_refs"]).issubset(
        {r["reference"] for r in i["context_refs"]}
    ):
        decision, reason = "BLOCKED", "EVIDENCE_NOT_IN_CONTEXT"
    else:
        decision, reason = "REVIEW_REQUIRED", "NO_EXECUTION_AUTHORITY"

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "engine": ENGINE,
        "work_id": i["work_id"],
        "proposal_id": p["proposal_id"],
        "decision": decision,
        "reason": reason,
        "declared_effect": c["effect"],
        "authority_granted": False,
        "action_executed": False,
        "referenced_evidence": list(p["evidence_refs"]),
        "input_digests": {
            "intent": digest(i),
            "capability": digest(c),
            "proposal": digest(p),
        },
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


def receipt_digest_is_valid(receipt: Any) -> bool:
    """Digest integrity check only. NOT authenticity or a signature."""
    if type(receipt) is not dict:
        return False
    value = receipt.get("receipt_sha256")
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        return False
    unsigned = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    try:
        return digest(unsigned) == value
    except (TypeError, ValueError, OverflowError):
        return False
