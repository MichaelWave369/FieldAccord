"""FA-06 local handoff: restart, MAC, source binding and transaction negative controls."""

from copy import deepcopy
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fieldaccord.continuity import GENESIS, make_event
from fieldaccord.core import ContractError, digest
from fieldaccord.handoff import (
    WorkJournal, sign_export_for_testing, verify_export,
)
from fieldaccord.interop import VESSEL, PHIOS

WORK = "0b75b0ef-7626-48a1-874a-5636eb153601"
EVENT1 = "426d5bdd-55c3-4c1c-982e-3a7b11ff20e2"
EVENT2 = "d1f12263-27f0-4d91-892f-c9f961771a04"
ISSUED = "2026-10-07T20:00:00Z"
NOW = "2026-10-07T20:01:00Z"
EXPIRES = "2026-10-07T20:08:00Z"
NONCE = "a" * 32
SECRET = b"local-test-only-hmac-key-not-for-production-00001"
KEYRING = {
    "vessie-test": {"issuer_id": "vessie:local", "source_kind": VESSEL, "secret": SECRET}
}


def packet():
    return {
        "schema_version": "1", "packet_id": "context-demo-1",
        "task_id": "task-demo", "namespace_id": "project.test",
        "agent_id": "vessie", "model_ref": "local:qwen",
        "purpose": "handoff_review", "target_surface": "fieldaccord",
        "policy_epoch": 1,
        "authority_decision_ref": "none",
        "ledger_frontier_ref": "ledger-state",
        "memory_budget_tokens": 512,
        "items": [{"content": "DO NOT EXECUTE ANYTHING"}],
        "action_authority": "NONE",
    }


def inputs():
    export = packet()
    locator = "vessie:dlam:context:context-demo-1"
    intent = {
        "schema": "fa.work_intent.v0.1",
        "work_id": WORK, "initiator": {"kind": "human", "id": "operator"},
        "objective": "Review Vessie task continuity without any external side effects.",
        "requested_capabilities": ["discovery.read"],
        "attention_policy": "important",
        "context_refs": [{
            "reference": locator, "sha256": digest(export), "epistemic": "unverified"
        }],
    }
    opened = make_event(
        event_id=EVENT1, work_id=WORK, sequence=1,
        previous_hash=GENESIS, occurred_at=ISSUED,
        actor={"kind": "human", "id": "operator"},
        kind="WORK_OPENED", data={"intent_sha256": digest(intent)},
    )
    signed = sign_export_for_testing(
        key_id="vessie-test", issuer_id="vessie:local", secret=SECRET,
        nonce=NONCE, work_id=WORK, source_kind=VESSEL,
        source_locator=locator, issued_at=ISSUED,
        expires_at=EXPIRES, export=export,
    )
    return intent, opened, signed


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "events.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        intent, opened, signed = inputs()
        with WorkJournal(self.db) as store:
            state = store.begin_work(intent, opened)
        return intent, opened, signed, state

    def test_key_verified_but_not_operator_or_execution(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store:
            result = store.admit_export(
                env, keyring=KEYRING, now=NOW, expected_head=state["head_hash"],
                expected_task_id="task-demo"
            )
        self.assertTrue(result["shared_key_verified"])
        self.assertFalse(result["person_or_device_identity_authenticated"])
        self.assertFalse(result["operator_consent_verified"])
        self.assertFalse(result["authority_granted"])
        self.assertFalse(result["action_executed"])
        self.assertFalse(result["memory_admitted"])
        self.assertNotIn("DO NOT EXECUTE", str(result))

    def test_durable_state_survives_restart(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store:
            seen = store.state(WORK, expected_head=state["head_hash"])
        self.assertEqual(seen, state)
        self.assertEqual(seen["status"], "OPEN")

    def test_durable_checkpoint_survives_restart(self):
        i, e, env, state = self.create()
        second = make_event(
            event_id=EVENT2, work_id=WORK, sequence=2,
            previous_hash=state["head_hash"], occurred_at=NOW,
            actor={"kind": "agent", "id": "vessie"},
            kind="WORK_CHECKPOINTED",
            data={"summary": "Reviewed only", "pending_items": ["Operator review"]},
        )
        with WorkJournal(self.db) as store:
            new = store.append_event(second, expected_head=state["head_hash"])
        with WorkJournal(self.db) as store:
            resumed = store.state(WORK, expected_head=new["head_hash"])
        self.assertEqual(resumed["latest_checkpoint"]["pending_items"], ["Operator review"])
        self.assertFalse(resumed["action_executed"])

    def test_replay_refused_across_restart(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store:
            store.admit_export(env, keyring=KEYRING, now=NOW,
                               expected_head=state["head_hash"],
                               expected_task_id="task-demo")
        with WorkJournal(self.db) as reopened:
            with self.assertRaises(ContractError):
                reopened.admit_export(env, keyring=KEYRING, now=NOW,
                                      expected_head=state["head_hash"],
                                      expected_task_id="task-demo")

    def test_key_rotated_or_removed_refused(self):
        _, _, env, _ = self.create()
        for keys in ({}, {"vessie-test": {
            "issuer_id": "vessie:local", "source_kind": VESSEL,
            "secret": b"different-key-even-after-revocation-000000"
        }}):
            with self.subTest(keys=keys), self.assertRaises(ContractError):
                verify_export(env, keyring=keys, now=NOW)

    def test_wrong_issuer_key_assignment_refused(self):
        _, _, env, _ = self.create()
        keys = {"vessie-test": {"issuer_id": "other:agent",
                "source_kind": VESSEL, "secret": SECRET}}
        with self.assertRaises(ContractError):
            verify_export(env, keyring=keys, now=NOW)

    def test_wrong_source_kind_key_assignment_refused(self):
        _, _, env, _ = self.create()
        keys = {"vessie-test": {"issuer_id": "vessie:local",
                "source_kind": PHIOS, "secret": SECRET}}
        with self.assertRaises(ContractError):
            verify_export(env, keyring=keys, now=NOW)

    def test_bad_mac_refused_without_nonce_consumption(self):
        i, e, env, state = self.create()
        forged = deepcopy(env)
        forged["mac_sha256"] = "0" * 64
        with WorkJournal(self.db) as store:
            with self.assertRaises(ContractError):
                store.admit_export(forged, keyring=KEYRING, now=NOW,
                                   expected_head=state["head_hash"],
                                   expected_task_id="task-demo")
            result = store.admit_export(env, keyring=KEYRING, now=NOW,
                                       expected_head=state["head_hash"],
                                       expected_task_id="task-demo")
        self.assertTrue(result["shared_key_verified"])

    def test_tampered_packet_refused(self):
        _, _, env, _ = self.create()
        env["export"]["items"].append({"content": "tampered"})
        with self.assertRaises(ContractError):
            verify_export(env, keyring=KEYRING, now=NOW)

    def test_expired_refused(self):
        _, _, env, _ = self.create()
        with self.assertRaises(ContractError):
            verify_export(env, keyring=KEYRING, now=EXPIRES)

    def test_future_issued_refused(self):
        _, _, env, _ = self.create()
        with self.assertRaises(ContractError):
            verify_export(env, keyring=KEYRING, now="2026-10-07T19:59:59Z")

    def test_overlong_ttl_refused_even_if_signed(self):
        _, _, env, _ = self.create()
        env = sign_export_for_testing(
            key_id="vessie-test", issuer_id="vessie:local", secret=SECRET,
            nonce=NONCE, work_id=WORK, source_kind=VESSEL,
            source_locator="vessie:dlam:context:context-demo-1",
            issued_at=ISSUED, expires_at="2026-10-08T20:08:00Z",
            export=packet(),
        )
        with self.assertRaises(ContractError):
            verify_export(env, keyring=KEYRING, now=NOW)

    def test_malformed_extra_approval_field_refused(self):
        _, _, env, _ = self.create()
        env["grant"] = True
        with self.assertRaises(ContractError):
            verify_export(env, keyring=KEYRING, now=NOW)

    def test_wrong_key_id_refused(self):
        _, _, env, _ = self.create()
        env["key_id"] = "other"
        with self.assertRaises(ContractError):
            verify_export(env, keyring=KEYRING, now=NOW)

    def test_short_key_refused(self):
        _, _, env, _ = self.create()
        with self.assertRaises(ContractError):
            verify_export(env, keyring={"vessie-test": {
                "issuer_id": "vessie:local", "source_kind": VESSEL,
                "secret": b"short",
            }}, now=NOW)

    def test_oversize_export_refused(self):
        oversized = packet()
        oversized["items"] = [{"content": "x" * 80000}]
        env = sign_export_for_testing(
            key_id="vessie-test", issuer_id="vessie:local", secret=SECRET,
            nonce=NONCE, work_id=WORK, source_kind=VESSEL,
            source_locator="vessie:dlam:context:context-demo-1",
            issued_at=ISSUED, expires_at=EXPIRES, export=oversized,
        )
        with self.assertRaises(ContractError):
            verify_export(env, keyring=KEYRING, now=NOW)

    def test_stale_head_refused_then_valid_retry(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store:
            with self.assertRaises(ContractError):
                store.admit_export(env, keyring=KEYRING, now=NOW,
                                   expected_head="0" * 64, expected_task_id="task-demo")
            self.assertTrue(store.admit_export(
                env, keyring=KEYRING, now=NOW,
                expected_head=state["head_hash"], expected_task_id="task-demo"
            )["shared_key_verified"])

    def test_task_mismatch_refused(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store, self.assertRaises(ContractError):
            store.admit_export(env, keyring=KEYRING, now=NOW,
                               expected_head=state["head_hash"],
                               expected_task_id="unrelated-task")

    def test_different_payload_same_nonce_rejected(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store:
            store.admit_export(env, keyring=KEYRING, now=NOW,
                               expected_head=state["head_hash"], expected_task_id="task-demo")
            other = deepcopy(env)
            other["export"]["model_ref"] = "other"
            other["export_sha256"] = digest(other["export"])
            # A different authentic message reusing the nonce must also fail.
            other = sign_export_for_testing(
                key_id="vessie-test", issuer_id="vessie:local", secret=SECRET,
                nonce=NONCE, work_id=WORK, source_kind=VESSEL,
                source_locator="vessie:dlam:context:context-demo-1",
                issued_at=ISSUED, expires_at=EXPIRES,
                export=other["export"],
            )
            with self.assertRaises(ContractError):
                store.admit_export(other, keyring=KEYRING, now=NOW,
                                   expected_head=state["head_hash"], expected_task_id="task-demo")

    def test_duplicate_opening_work_refused(self):
        i, e, _, _ = self.create()
        with WorkJournal(self.db) as store, self.assertRaises(sqlite3.IntegrityError):
            store.begin_work(i, e)

    def test_conflicting_concurrent_work_heads_refused(self):
        _, _, _, state = self.create()
        e2 = make_event(
            event_id=EVENT2, work_id=WORK, sequence=2, previous_hash=state["head_hash"],
            occurred_at=NOW, actor={"kind": "agent", "id": "vessie"},
            kind="WORK_NOTE_ADDED", data={"note": "New state"},
        )
        with WorkJournal(self.db) as left, WorkJournal(self.db) as right:
            left.append_event(e2, expected_head=state["head_hash"])
            e3 = make_event(
                event_id="745c181d-8f2f-45f2-a9ed-9316bec9f119",
                work_id=WORK, sequence=2, previous_hash=state["head_hash"],
                occurred_at=NOW, actor={"kind": "agent", "id": "vessie"},
                kind="WORK_NOTE_ADDED", data={"note": "Losing concurrent edit"},
            )
            with self.assertRaises(ContractError):
                right.append_event(e3, expected_head=state["head_hash"])

    def test_corrupted_stored_event_detected(self):
        _, _, _, state = self.create()
        with WorkJournal(self.db) as store:
            store.connection.execute("UPDATE work_event SET event_json='{}' WHERE work_id=?", (WORK,))
        with WorkJournal(self.db) as store, self.assertRaises(ContractError):
            store.state(WORK)

    def test_head_anchor_detects_history_replacement(self):
        _, _, _, state = self.create()
        with WorkJournal(self.db) as store:
            fake = make_event(event_id=EVENT2, work_id=WORK, sequence=2,
                previous_hash=state["head_hash"], occurred_at=NOW,
                actor={"kind":"agent","id":"vessie"}, kind="WORK_NOTE_ADDED",
                data={"note":"Local journal modified"})
            store.append_event(fake, expected_head=state["head_hash"])
        with WorkJournal(self.db) as store, self.assertRaises(ContractError):
            store.state(WORK, expected_head=state["head_hash"])

    def test_changed_intent_refused_for_export(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store:
            store.connection.execute(
                "UPDATE work SET intent_sha256=? WHERE work_id=?", ("1" * 64, WORK)
            )
        with WorkJournal(self.db) as store, self.assertRaises(ContractError):
            store.admit_export(env, keyring=KEYRING, now=NOW,
                               expected_head=state["head_hash"], expected_task_id="task-demo")

    def test_invalid_clock_string_refused(self):
        _, _, env, _ = self.create()
        with self.assertRaises(ContractError):
            verify_export(env, keyring=KEYRING, now="no-clock")

    def test_no_key_material_persisted_by_journal(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store:
            store.admit_export(env, keyring=KEYRING, now=NOW,
                               expected_head=state["head_hash"], expected_task_id="task-demo")
            tables = [name for (name,) in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )]
            self.assertIn("export_nonce", tables)
            rows = store.connection.execute(
                "SELECT envelope_sha256 FROM export_nonce"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertNotIn(SECRET.decode(), str(rows))

    def test_failed_interop_does_not_consume_nonce(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store:
            with self.assertRaises(ContractError):
                store.admit_export(env, keyring=KEYRING, now=NOW,
                                   expected_head=state["head_hash"], expected_task_id=None)
            self.assertTrue(store.admit_export(
                env, keyring=KEYRING, now=NOW,
                expected_head=state["head_hash"], expected_task_id="task-demo"
            )["shared_key_verified"])

    def test_mac_verified_envelope_without_work_is_refused(self):
        _, _, env = inputs()
        with WorkJournal(self.db) as store, self.assertRaises(ContractError):
            store.admit_export(env, keyring=KEYRING, now=NOW,
                               expected_head="0" * 64, expected_task_id="task-demo")

    def test_no_network_or_message_during_admission(self):
        i, e, env, state = self.create()
        with WorkJournal(self.db) as store:
            result = store.admit_export(env, keyring=KEYRING, now=NOW,
                                       expected_head=state["head_hash"], expected_task_id="task-demo")
            self.assertFalse(result["notification_dispatched"])
            self.assertFalse(result["interop_receipt"]["action_executed"])


if __name__ == "__main__":
    unittest.main()
