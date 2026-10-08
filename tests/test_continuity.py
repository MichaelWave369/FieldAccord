"""FA-02 offline continuity/advisory attention negative controls."""

import copy
import json
from pathlib import Path
import unittest
from uuid import uuid4

from fieldaccord.core import ContractError, digest
from fieldaccord.continuity import (
    GENESIS, attention_review, make_event, replay_work, validate_event,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "intent.json"
T0 = "2026-10-07T20:00:00Z"
T1 = "2026-10-07T20:01:00Z"
T2 = "2026-10-07T20:02:00Z"
T3 = "2026-10-07T20:03:00Z"
EXPIRES = "2026-10-07T21:00:00Z"
HUMAN = {"kind": "human", "id": "operator"}
AGENT = {"kind": "agent", "id": "vessie"}


def intent():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def evt(i, seq, previous, kind, data, when=T1, actor=HUMAN):
    return make_event(
        event_id=str(uuid4()), work_id=i["work_id"], sequence=seq,
        previous_hash=previous, occurred_at=when, actor=actor,
        kind=kind, data=data,
    )


def opened(i):
    return evt(i, 1, GENESIS, "WORK_OPENED",
               {"intent_sha256": digest(i)}, T0)


def append(i, events, kind, data, when=T1, actor=HUMAN):
    event = evt(i, len(events) + 1, events[-1]["event_hash"],
                kind, data, when, actor)
    events.append(event)
    return event


def lease_data(mode="important"):
    return {
        "lease_id": str(uuid4()), "recipient_id": "operator",
        "mode": mode, "expires_at": EXPIRES,
    }


class ReplayTests(unittest.TestCase):
    def test_single_open_starts_at_open(self):
        i = intent()
        events = [opened(i)]
        s = replay_work(i, events)
        self.assertEqual(s["status"], "OPEN")
        self.assertEqual(s["sequence"], 1)
        self.assertEqual(s["head_hash"], events[-1]["event_hash"])
        self.assertFalse(s["authority_granted"])
        self.assertFalse(s["action_executed"])
        self.assertFalse(s["notification_dispatched"])

    def test_replay_is_deterministic(self):
        i = intent()
        events = [opened(i)]
        append(i, events, "WORK_NOTE_ADDED", {"note": "Diagnostic proposed"}, T1, AGENT)
        self.assertEqual(replay_work(i, events), replay_work(i, events))

    def test_checkpoint_survives_replay(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "WORK_CHECKPOINTED",
               {"summary": "Inspect CI logs", "pending_items": ["Read logs", "Draft fix"]}, T1, AGENT)
        state = replay_work(i, e)
        self.assertEqual(state["latest_checkpoint"]["pending_items"], ["Read logs", "Draft fix"])
        self.assertEqual(state["status"], "OPEN")

    def test_review_block_reopen(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "WORK_REVIEW_REQUESTED", {"question": "Choose fix?"}, T1, AGENT)
        append(i, e, "WORK_BLOCKED", {"reason": "Need operator input"}, T2)
        append(i, e, "WORK_REOPENED", {"reason": "Question addressed"}, T3)
        self.assertEqual(replay_work(i, e)["status"], "OPEN")

    def test_closed_is_not_a_success_claim(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "WORK_CLOSED", {"resolution": "archived", "note": "Superseded work"}, T1)
        s = replay_work(i, e)
        self.assertEqual(s["status"], "CLOSED")
        self.assertFalse(s["action_executed"])
        self.assertNotIn("success", s)

    def test_after_closed_rejected(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "WORK_CLOSED", {"resolution": "withdrawn", "note": "Cancelled"}, T1)
        append(i, e, "WORK_NOTE_ADDED", {"note": "Too late"}, T2)
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_close_clears_attention(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data(), T1)
        append(i, e, "WORK_CLOSED", {"resolution": "archived", "note": "Archived"}, T2)
        self.assertIsNone(replay_work(i, e)["active_attention_lease"])

    def test_event_identity_duplicate_rejected(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "WORK_NOTE_ADDED", {"note": "First"}, T1)
        duplicated = copy.deepcopy(e[-1])
        duplicated["sequence"] = 3
        duplicated["previous_hash"] = e[-1]["event_hash"]
        duplicated["event_hash"] = digest({k: v for k, v in duplicated.items() if k != "event_hash"})
        e.append(duplicated)
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_duplicate_sequence_rejected(self):
        i = intent()
        e = [opened(i)]
        second = evt(i, 1, e[-1]["event_hash"], "WORK_NOTE_ADDED", {"note": "Again"})
        with self.assertRaises(ContractError):
            replay_work(i, e + [second])

    def test_missing_sequence_rejected(self):
        i = intent()
        e = [opened(i)]
        second = evt(i, 3, e[-1]["event_hash"], "WORK_NOTE_ADDED", {"note": "Gap"})
        with self.assertRaises(ContractError):
            replay_work(i, e + [second])

    def test_tamper_detected(self):
        i = intent()
        e = [opened(i)]
        e[0]["data"]["intent_sha256"] = "2" * 64
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_forged_chain_link_rejected(self):
        i = intent()
        e = [opened(i)]
        e.append(evt(i, 2, GENESIS, "WORK_NOTE_ADDED", {"note": "Detached"}))
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_external_head_anchor_drift_rejected(self):
        i = intent()
        e = [opened(i)]
        with self.assertRaises(ContractError):
            replay_work(i, e, expected_head="0" * 64)
        self.assertEqual(replay_work(i, e, expected_head=e[-1]["event_hash"])["sequence"], 1)

    def test_work_intent_drift_rejected(self):
        i = intent()
        e = [opened(i)]
        i["objective"] += " And change permissions."
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_cross_work_event_rejected(self):
        i = intent()
        e = [opened(i)]
        other = copy.deepcopy(i)
        other["work_id"] = str(uuid4())
        e.append(evt(other, 2, e[-1]["event_hash"], "WORK_NOTE_ADDED", {"note": "Cross task"}))
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_non_monotonic_time_rejected(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "WORK_NOTE_ADDED", {"note": "Forward"}, T2)
        append(i, e, "WORK_NOTE_ADDED", {"note": "Backwards"}, T1)
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_invalid_transition_rejected(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "WORK_REOPENED", {"reason": "Not blocked"}, T1)
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_unknown_payload_extra_authority_rejected(self):
        i = intent()
        with self.assertRaises(ContractError):
            evt(i, 1, GENESIS, "WORK_OPENED",
                {"intent_sha256": digest(i), "is_approved": True}, T0)

    def test_bool_as_sequence_rejected(self):
        i = intent()
        e = [opened(i)]
        e[0]["sequence"] = True
        e[0]["event_hash"] = digest({k: v for k, v in e[0].items() if k != "event_hash"})
        with self.assertRaises(ContractError):
            validate_event(e[0])

    def test_event_timestamp_invalid_rejected(self):
        i = intent()
        with self.assertRaises(ContractError):
            evt(i, 1, GENESIS, "WORK_OPENED", {"intent_sha256": digest(i)},
                "2026-02-30T20:00:00Z")

    def test_unknown_event_kind_rejected(self):
        i = intent()
        with self.assertRaises(ContractError):
            evt(i, 1, GENESIS, "EXECUTE", {}, T0)

    def test_reopened_does_not_revive_grants(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "WORK_BLOCKED", {"reason": "No network"}, T1)
        append(i, e, "WORK_REOPENED", {"reason": "Available"}, T2)
        s = replay_work(i, e)
        self.assertFalse(s["authority_granted"])
        self.assertFalse(s["action_executed"])


class AttentionTests(unittest.TestCase):
    def test_no_lease_held(self):
        i = intent()
        s = replay_work(i, [opened(i)])
        r = attention_review(s, recipient_id="operator", urgency="critical", at=T2)
        self.assertEqual(r["decision"], "HOLD")
        self.assertEqual(r["reason"], "NO_LEASE")

    def test_important_lease_surfaces_important_as_candidate_only(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data(), T1)
        s = replay_work(i, e)
        r = attention_review(s, recipient_id="operator", urgency="important", at=T2)
        self.assertEqual(r["decision"], "REVIEW_CANDIDATE")
        self.assertFalse(r["notification_dispatched"])
        self.assertFalse(r["authority_granted"])
        self.assertTrue(r["operator_verification_required"])

    def test_quiet_filters_noncritical(self):
        i = intent()
        i["attention_policy"] = "quiet"
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data("quiet"), T1)
        s = replay_work(i, e)
        self.assertEqual(attention_review(s, recipient_id="operator", urgency="important", at=T2)["reason"], "FILTERED")
        self.assertEqual(attention_review(s, recipient_id="operator", urgency="critical", at=T2)["decision"], "REVIEW_CANDIDATE")

    def test_no_upgrading_above_intent_policy(self):
        i = intent()
        i["attention_policy"] = "quiet"
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data("collaborate"), T1)
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_agent_cannot_set_preference(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data(), T1, AGENT)
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_revocation_works_and_is_sticky(self):
        i = intent()
        e = [opened(i)]
        data = lease_data()
        append(i, e, "ATTENTION_LEASE_SET", data, T1)
        append(i, e, "ATTENTION_LEASE_REVOKED", {"lease_id": data["lease_id"]}, T2)
        s = replay_work(i, e)
        self.assertIsNone(s["active_attention_lease"])
        self.assertEqual(attention_review(s, recipient_id="operator", urgency="critical", at=T3)["reason"], "NO_LEASE")

    def test_wrong_lease_revocation_rejected(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data(), T1)
        append(i, e, "ATTENTION_LEASE_REVOKED", {"lease_id": str(uuid4())}, T2)
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_wrong_issuer_revocation_rejected(self):
        i = intent()
        e = [opened(i)]
        data = lease_data()
        append(i, e, "ATTENTION_LEASE_SET", data, T1)
        append(i, e, "ATTENTION_LEASE_REVOKED",
               {"lease_id": data["lease_id"]}, T2,
               {"kind": "human", "id": "stranger"})
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_second_unrevoked_lease_rejected(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data(), T1)
        append(i, e, "ATTENTION_LEASE_SET", lease_data(), T2)
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_expired_not_notified(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data(), T1)
        s = replay_work(i, e)
        r = attention_review(s, recipient_id="operator", urgency="critical", at=EXPIRES)
        self.assertEqual(r["reason"], "EXPIRED")
        self.assertFalse(r["notification_dispatched"])

    def test_not_yet_active_held(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data(), T1)
        s = replay_work(i, e)
        self.assertEqual(attention_review(s, recipient_id="operator", urgency="critical", at=T0)["reason"], "NOT_YET_ACTIVE")

    def test_recipient_is_bound(self):
        i = intent()
        e = [opened(i)]
        append(i, e, "ATTENTION_LEASE_SET", lease_data(), T1)
        s = replay_work(i, e)
        self.assertEqual(attention_review(s, recipient_id="someone_else", urgency="critical", at=T2)["reason"], "WRONG_RECIPIENT")

    def test_expiration_max_one_day(self):
        i = intent()
        e = [opened(i)]
        data = lease_data()
        data["expires_at"] = "2026-10-09T20:00:00Z"
        append(i, e, "ATTENTION_LEASE_SET", data, T1)
        with self.assertRaises(ContractError):
            replay_work(i, e)

    def test_mismatched_replay_head_does_not_emit(self):
        i = intent()
        e = [opened(i)]
        with self.assertRaises(ContractError):
            replay_work(i, e, expected_head="a" * 64)

    def test_advisory_state_tampered_with_executed_true_rejected(self):
        i = intent()
        s = replay_work(i, [opened(i)])
        s["action_executed"] = True
        with self.assertRaises(ContractError):
            attention_review(s, recipient_id="operator", urgency="critical", at=T2)


if __name__ == "__main__":
    unittest.main()
