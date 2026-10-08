"""Field Accord CLI: local review-only and deterministic replay demonstrations."""

import argparse
import json
from pathlib import Path
import sys

from .core import ContractError, assess, digest
from .bridge import FIELDDECK, FIELDDECK_LOCATOR, inspect_snapshot
from .continuity import GENESIS, attention_review, make_event, replay_work


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _work_demo() -> dict:
    intent = _read(Path(__file__).resolve().parent.parent / "examples" / "intent.json")
    operator = {"kind": "human", "id": "operator"}
    opened = make_event(
        event_id="5461839b-f030-4d06-8f21-9ab12bca1be4",
        work_id=intent["work_id"], sequence=1, previous_hash=GENESIS,
        occurred_at="2026-10-07T20:00:00Z", actor=operator,
        kind="WORK_OPENED", data={"intent_sha256": digest(intent)},
    )
    lease = make_event(
        event_id="53510984-9647-424a-8bc0-954c63cb82bb",
        work_id=intent["work_id"], sequence=2, previous_hash=opened["event_hash"],
        occurred_at="2026-10-07T20:01:00Z", actor=operator,
        kind="ATTENTION_LEASE_SET",
        data={
            "lease_id": "caab426f-2a21-402e-bd2c-a299294f53c0",
            "recipient_id": "operator", "mode": "important",
            "expires_at": "2026-10-07T21:00:00Z",
        },
    )
    checkpoint = make_event(
        event_id="9a19932e-ff55-4f5a-8f35-30b5ebc2973e",
        work_id=intent["work_id"], sequence=3, previous_hash=lease["event_hash"],
        occurred_at="2026-10-07T20:02:00Z",
        actor={"kind": "agent", "id": "vessie"},
        kind="WORK_CHECKPOINTED",
        data={
            "summary": "Simulated diagnostic: no real CI logs accessed.",
            "pending_items": ["Human-approved evidence retrieval"],
        },
    )
    work = replay_work(intent, [opened, lease, checkpoint])
    attention = attention_review(
        work, recipient_id="operator", urgency="important",
        at="2026-10-07T20:03:00Z",
    )
    return {"work_state": work, "attention_decision": attention}


def _bridge_demo() -> dict:
    """Synthetic FieldDeck-shaped sample, not a live read of the repository."""
    intent = _read(Path(__file__).resolve().parent.parent / "examples" / "intent.json")
    payload = {
        "name": "FieldDeck", "schema_version": "0.6.0",
        "execution_policy": {
            "default": "deny", "require_authenticated_runner": True,
            "freeform_shell": False, "receipt_required": True,
        },
        "actions": [{
            "id": "catalog-health", "kind": "workflow",
            "status": "ready", "risk": "low",
            "task": "this is just text: never executed",
        }],
    }
    fingerprint = digest(payload)
    intent["requested_capabilities"].append("discovery.read")
    intent["context_refs"].append({
        "reference": FIELDDECK_LOCATOR,
        "sha256": fingerprint, "epistemic": "unverified",
    })
    opened = make_event(
        event_id="4ec0a353-f353-46d7-8aa3-2164929518fe",
        work_id=intent["work_id"], sequence=1,
        previous_hash=GENESIS, occurred_at="2026-10-07T20:00:00Z",
        actor={"kind": "human", "id": "operator"},
        kind="WORK_OPENED", data={"intent_sha256": digest(intent)},
    )
    snapshot = {
        "schema": "fa.source_snapshot.v0.1",
        "capture_id": "35a4d52d-7a33-458a-a29d-1d8a55f686ba",
        "work_id": intent["work_id"], "source_kind": FIELDDECK,
        "source_locator": FIELDDECK_LOCATOR,
        "payload_sha256": fingerprint, "payload": payload,
    }
    return inspect_snapshot(
        intent, [opened], snapshot,
        expected_state_head=opened["event_hash"],
        expected_payload_sha256=fingerprint,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Field Accord offline coordination contracts")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="FA-01 synthetic no-authority assessment")
    sub.add_parser("work-demo", help="FA-02 synthetic work replay and attention advice")
    sub.add_parser("bridge-demo", help="FA-03 synthetic read-only discovery projection")
    review = sub.add_parser("assess", help="Assess three local JSON files, without execution")
    for name in ("intent", "capability", "proposal"):
        review.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "bridge-demo":
            print(json.dumps(_bridge_demo(), indent=2, sort_keys=True))
            return 0
        if args.command == "work-demo":
            print(json.dumps(_work_demo(), indent=2, sort_keys=True))
            return 0
        if args.command == "demo":
            examples = Path(__file__).resolve().parent.parent / "examples"
            paths = [examples / name for name in ("intent.json", "capability.json", "proposal.json")]
        else:
            paths = [args.intent, args.capability, args.proposal]
        receipt = assess(*(_read(path) for path in paths))
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["decision"] == "REVIEW_REQUIRED" else 3
    except (OSError, ValueError, ContractError) as exc:
        print(f"Field Accord assessment refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
