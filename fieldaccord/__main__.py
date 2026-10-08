"""Field Accord CLI: local review-only and deterministic replay demonstrations."""

import argparse
import json
from pathlib import Path
import sys

from .core import ContractError, assess, digest
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Field Accord offline coordination contracts")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="FA-01 synthetic no-authority assessment")
    sub.add_parser("work-demo", help="FA-02 synthetic work replay and attention advice")
    review = sub.add_parser("assess", help="Assess three local JSON files, without execution")
    for name in ("intent", "capability", "proposal"):
        review.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
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
