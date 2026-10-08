"""Field Accord CLI: local review-only and deterministic replay demonstrations."""

import argparse
import json
from pathlib import Path
import sys

from .core import ContractError, assess, digest
from .bridge import FIELDDECK, FIELDDECK_LOCATOR, inspect_snapshot
from .acquisition import acquire_fielddeck, public_summary
from .interop import inspect_interop, VESSEL
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


def _interop_demo() -> dict:
    """Entirely synthetic Vessie-shaped context; no actual model or PhiOS call."""
    intent = _read(Path(__file__).resolve().parent.parent / "examples" / "intent.json")
    export = {
        "schema_version": "1", "packet_id": "demo-packet", "task_id": "demo-task",
        "namespace_id": "demo", "agent_id": "vessie", "model_ref": "demo:model",
        "purpose": "offline_demo", "target_surface": "fieldaccord",
        "policy_epoch": 0, "authority_decision_ref": "not-an-approval",
        "ledger_frontier_ref": "demo-ledger", "memory_budget_tokens": 1000,
        "items": [{"content": "This is not passed to a model."}],
        "action_authority": "NONE",
    }
    locator = "vessie:dlam:context:demo-packet"
    source_hash = digest(export)
    intent["requested_capabilities"].append("discovery.read")
    intent["context_refs"].append({
        "reference": locator, "sha256": source_hash, "epistemic": "unverified",
    })
    opened = make_event(
        event_id="784e301a-e971-45df-957d-13d4847156e5",
        work_id=intent["work_id"], sequence=1, previous_hash=GENESIS,
        occurred_at="2026-10-07T20:00:00Z",
        actor={"kind": "human", "id": "operator"},
        kind="WORK_OPENED", data={"intent_sha256": digest(intent)},
    )
    return inspect_interop(
        intent, [opened], export, source_kind=VESSEL, source_locator=locator,
        expected_payload_sha256=source_hash,
        expected_state_head=opened["event_hash"], expected_task_id="demo-task",
    )


def _handoff_demo() -> dict:
    """Synthetic local durable handoff; fake shared key and temporary database."""
    import tempfile
    from pathlib import Path
    from .handoff import WorkJournal, sign_export_for_testing
    intent = _read(Path(__file__).resolve().parent.parent / 'examples' / 'intent.json')
    export = {
        'schema_version': '1', 'packet_id': 'handoff-demo', 'task_id': 'demo-task',
        'namespace_id': 'demo', 'agent_id': 'vessie', 'model_ref': 'demo:model',
        'purpose': 'synthetic', 'target_surface': 'fieldaccord', 'policy_epoch': 0,
        'authority_decision_ref': 'no-grant', 'ledger_frontier_ref': 'demo-frontier',
        'memory_budget_tokens': 100, 'items': [{'untrusted': 'never admitted'}],
        'action_authority': 'NONE',
    }
    locator = 'vessie:dlam:context:handoff-demo'
    intent['requested_capabilities'].append('discovery.read')
    intent['context_refs'].append({
        'reference': locator, 'sha256': digest(export), 'epistemic': 'unverified',
    })
    opened = make_event(
        event_id='21e19f5e-70b9-4692-b9c5-196355d91746',
        work_id=intent['work_id'], sequence=1, previous_hash=GENESIS,
        occurred_at='2026-10-07T20:00:00Z',
        actor={'kind': 'human', 'id': 'operator'},
        kind='WORK_OPENED', data={'intent_sha256': digest(intent)},
    )
    secret = b'ONLY-FOR-FA-06-DEMO-DO-NOT-USE-IN-PRODUCTION-KEY!'
    envelope = sign_export_for_testing(
        key_id='vessie-demo', issuer_id='vessie:local', secret=secret,
        nonce='1234567890abcdef1234567890abcdef',
        work_id=intent['work_id'], source_kind=VESSEL, source_locator=locator,
        issued_at='2026-10-07T20:00:00Z',
        expires_at='2026-10-07T20:08:00Z', export=export,
    )
    keys = {'vessie-demo': {'issuer_id':'vessie:local','source_kind':VESSEL,'secret':secret}}
    with tempfile.TemporaryDirectory() as location:
        with WorkJournal(Path(location) / 'handoff.sqlite3') as store:
            state = store.begin_work(intent, opened)
            result = store.admit_export(
                envelope, keyring=keys, now='2026-10-07T20:01:00Z',
                expected_head=state['head_hash'], expected_task_id='demo-task',
            )
        with WorkJournal(Path(location) / 'handoff.sqlite3') as store:
            resumed = store.state(intent['work_id'], expected_head=state['head_hash'])
            try:
                store.admit_export(envelope, keyring=keys, now='2026-10-07T20:01:00Z',
                    expected_head=state['head_hash'], expected_task_id='demo-task')
            except ContractError:
                replay_blocked = True
            else:
                replay_blocked = False
    return {'receipt': result, 'resumed_status': resumed['status'],
            'replay_blocked': replay_blocked, 'database_temporary': True}

def main() -> int:
    parser = argparse.ArgumentParser(description="Field Accord offline coordination contracts")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="FA-01 synthetic no-authority assessment")
    sub.add_parser("work-demo", help="FA-02 synthetic work replay and attention advice")
    sub.add_parser("bridge-demo", help="FA-03 synthetic read-only discovery projection")
    sub.add_parser("interop-demo", help="FA-05 synthetic Vessie/PhiOS interop review")
    sub.add_parser("handoff-demo", help="FA-06 synthetic shared-key and durable replay check")
    sub.add_parser("fetch-fielddeck", help="FA-04 opt-in public GitHub read of reviewed exact commit")
    review = sub.add_parser("assess", help="Assess three local JSON files, without execution")
    for name in ("intent", "capability", "proposal"):
        review.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "handoff-demo":
            print(json.dumps(_handoff_demo(), indent=2, sort_keys=True))
            return 0
        if args.command == "interop-demo":
            print(json.dumps(_interop_demo(), indent=2, sort_keys=True))
            return 0
        if args.command == "fetch-fielddeck":
            print(json.dumps(public_summary(acquire_fielddeck()), indent=2, sort_keys=True))
            return 0
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
