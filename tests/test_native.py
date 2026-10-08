"""FA-08: real P1-B sealed-packet / PhiOS observation compatibility tests."""

import hashlib
import tempfile
from pathlib import Path
from copy import deepcopy
import unittest

from fieldaccord.continuity import GENESIS, make_event
from fieldaccord.core import ContractError, canonical_json, digest
from fieldaccord.handoff import WorkJournal
from fieldaccord.interop import PHIOS, VESSEL
from fieldaccord.native import (
    issue_native_phios_envelope, issue_native_vessie_envelope,
    native_phios_status_export, native_vessie_metadata_export,
)
from fieldaccord.producers import admit_export_frame, frame_export

WORK = "93f37662-58af-4ad1-b179-27c80dfe3139"
EVT = "821753f0-bc27-4d73-9a3b-253bf7a3e462"
SECRET = b"FA08-SYNTHETIC-HMAC-KEY-ONLY-NOT-PRODUCTION-000001"
ISSUED = "2026-10-07T22:00:00Z"
RECEIVED = "2026-10-07T22:00:01Z"


def sealed(source=None):
    body = source or {
        "schema_version": "1",
        "schema": "superphivessel.dlam.context-packet.v0.1",
        "task_id": "task-direct",
        "namespace_id": "namespace.lab",
        "agent_id": "vessie",
        "genius_profile_ref": None,
        "model_ref": "private-model-@version",
        "purpose": "private analysis notes",
        "target_surface": "private-model",
        "policy_epoch": 2,
        "authority_decision_ref": "private-decision",
        "authority_status": "CURRENT",
        "ledger_frontier_ref": "private-ledger",
        "index_manifest_ref": "fts5:namespace.lab:abc",
        "router_snapshot_ref": None,
        "tokenizer_id": "fixture-regex",
        "memory_budget_tokens": 4096,
        "query_hash": "b" * 64,
        "allowed_origins": ["OBSERVED", "VERIFIED"],
        "action_authority": "NONE",
        "disposition": "READY",
        "used_memory_tokens": 16,
        "items": [{"content": "NEVER-LEAK-THIS-MEMORY", "origin": "VERIFIED"}],
        "excluded": [],
        "omitted_dependencies": [],
        "epistemic_mix": {"VERIFIED": 1},
    }
    digest_value = hashlib.sha256(b"PV-DLAM-CONTEXT|" + canonical_json(body)).hexdigest()
    return {**body, "packet_id": "ctx_" + digest_value[:32], "packet_hash": digest_value}


class NativePhiOSObservation:
    def __init__(self):
        self.calls = 0
        self.item = {
            "schema_version": "phios.phivessel_observation.v0.1",
            "kind": "BRIDGE_STATUS",
            "observed_at": "2026-10-07T22:00:00+00:00",
            "source_id": "phivessel:local",
            "payload": {
                "bridge_version": "PV-PHIOS-BRIDGE-0.1",
                "observe_available": True,
                "proposal_available": True,
                "execution_available": True,
                "proposal_creates_authority_request": False,
                "proposal_creates_lease": False,
                "execute_accepts_lease_identity_only": True,
            },
            "policy_authority": False, "operational_authority": False,
            "action_authority": False, "execution_authority": False,
            "effect_performed": False,
        }
        self.item["observation_sha256"] = digest(self.item)

    def to_dict(self):
        self.calls += 1
        return deepcopy(self.item)


def intent_and_opened(signed):
    i = {
        "schema": "fa.work_intent.v0.1", "work_id": WORK,
        "initiator": {"kind": "human", "id": "operator"},
        "objective": "Inspect native metadata without granting action authority.",
        "requested_capabilities": ["discovery.read"], "attention_policy": "quiet",
        "context_refs": [{
            "reference": signed["source_locator"],
            "sha256": signed["export_sha256"], "epistemic": "unverified",
        }],
    }
    e = make_event(
        event_id=EVT, work_id=WORK, sequence=1, previous_hash=GENESIS,
        occurred_at=ISSUED, actor={"kind": "human", "id": "operator"},
        kind="WORK_OPENED", data={"intent_sha256": digest(i)},
    )
    return i, e


def v_envelope(source=None):
    return issue_native_vessie_envelope(
        sealed() if source is None else source, work_id=WORK,
        issuer_id="vessie:local", key_id="vessie-test",
        shared_secret=SECRET, issued_at=ISSUED, nonce="1" * 32,
    )


def p_envelope(source=None):
    return issue_native_phios_envelope(
        NativePhiOSObservation() if source is None else source, work_id=WORK,
        issuer_id="phios:local", key_id="phios-test",
        shared_secret=SECRET, issued_at=ISSUED, nonce="2" * 32,
    )


class NativeAdapterTests(unittest.TestCase):
    def test_real_p1b_shape_derives_only_metadata(self):
        raw = sealed()
        before = deepcopy(raw)
        result = native_vessie_metadata_export(raw)
        self.assertEqual(raw, before)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["action_authority"], "NONE")
        self.assertEqual(result["packet_id"], raw["packet_id"])
        self.assertNotIn("NEVER-LEAK", str(result))
        self.assertNotIn("private-model-@version", str(result))
        self.assertNotIn("private analysis notes", str(result))
        self.assertNotIn("private-ledger", str(result))
        self.assertNotIn("private-decision", str(result))
        self.assertNotIn("tokenizer_id", result)
        self.assertNotIn("query_hash", result)
        self.assertNotIn("packet_hash", result)

    def test_native_hmac_envelope_contains_derived_only(self):
        signed = v_envelope()
        self.assertEqual(signed["export"]["items"], [])
        self.assertEqual(signed["source_kind"], VESSEL)
        self.assertNotIn("NEVER-LEAK", str(signed))
        self.assertNotIn("private-decision", str(signed))

    def test_native_wrong_composer_hash_rejected(self):
        original = sealed()
        original["items"][0]["content"] = "substituted"
        with self.assertRaises(ContractError):
            native_vessie_metadata_export(original)

    def test_native_packet_id_rewritten_rejected(self):
        original = sealed()
        original["packet_id"] = "ctx_" + "0" * 32
        with self.assertRaises(ContractError):
            native_vessie_metadata_export(original)

    def test_native_unreviewed_extension_field_rejected(self):
        original = sealed()
        original["execute_approval"] = True
        with self.assertRaises(ContractError):
            native_vessie_metadata_export(original)

    def test_native_unsafe_authority_status_rejected(self):
        for value in ("STALE", "DENIED"):
            with self.subTest(value=value):
                packet = sealed({**{k:v for k,v in sealed().items() if k not in ("packet_id","packet_hash")},
                                 "authority_status": value, "disposition": "HELD",
                                 "items": []})
                with self.assertRaises(ContractError):
                    native_vessie_metadata_export(packet)

    def test_native_non_ready_context_rejected(self):
        body = {k:v for k,v in sealed().items() if k not in ("packet_id","packet_hash")}
        body["disposition"] = "INSUFFICIENT"
        body["items"] = []
        with self.assertRaises(ContractError):
            native_vessie_metadata_export(sealed(body))

    def test_native_action_authority_rejected(self):
        body = {k:v for k,v in sealed().items() if k not in ("packet_id","packet_hash")}
        body["action_authority"] = "GRANTED"
        with self.assertRaises(ContractError):
            native_vessie_metadata_export(sealed(body))

    def test_native_extra_private_nested_items_do_not_escape(self):
        raw = sealed()
        raw["items"][0]["secret"] = {"p": "never-export", "attack": "execute now"}
        raw = sealed({k:v for k,v in raw.items() if k not in ("packet_id","packet_hash")})
        self.assertNotIn("never-export", str(native_vessie_metadata_export(raw)))

    def test_native_wrong_schema_rejected(self):
        body = {k:v for k,v in sealed().items() if k not in ("packet_id","packet_hash")}
        body["schema"] = "different.dlam"
        with self.assertRaises(ContractError):
            native_vessie_metadata_export(sealed(body))

    def test_native_typed_epoch_refused(self):
        body = {k:v for k,v in sealed().items() if k not in ("packet_id","packet_hash")}
        body["policy_epoch"] = True
        with self.assertRaises(ContractError):
            native_vessie_metadata_export(sealed(body))

    def test_native_string_instead_of_items_refused(self):
        body = {k:v for k,v in sealed().items() if k not in ("packet_id","packet_hash")}
        body["items"] = "execute"
        with self.assertRaises(ContractError):
            native_vessie_metadata_export(sealed(body))

    def test_native_no_unsupported_spurious_kinds(self):
        with self.assertRaises(ContractError):
            native_vessie_metadata_export({"schema_version": "1"})

    def test_native_phios_object_accepted(self):
        ob = NativePhiOSObservation()
        data = native_phios_status_export(ob)
        self.assertEqual(ob.calls, 1)
        self.assertEqual(data["kind"], "BRIDGE_STATUS")
        self.assertFalse(data["effect_performed"])

    def test_native_phios_arbitrary_dict_refused(self):
        with self.assertRaises(ContractError):
            native_phios_status_export(NativePhiOSObservation().to_dict())

    def test_native_phios_lease_status_refused(self):
        ob = NativePhiOSObservation()
        ob.item["kind"] = "LEASE_STATUS"
        ob.item["observation_sha256"] = digest({
            k:v for k,v in ob.item.items() if k!="observation_sha256"
        })
        with self.assertRaises(ContractError):
            native_phios_status_export(ob)

    def test_native_phios_asserted_effect_rejected(self):
        ob = NativePhiOSObservation()
        ob.item["effect_performed"] = True
        ob.item["observation_sha256"] = digest({
            k:v for k,v in ob.item.items() if k!="observation_sha256"
        })
        with self.assertRaises(ContractError):
            native_phios_status_export(ob)

    def test_native_phios_to_dict_evaluated_once(self):
        ob = NativePhiOSObservation()
        issue_native_phios_envelope(
            ob, work_id=WORK, issuer_id="phios:local", key_id="phios-test",
            shared_secret=SECRET, issued_at=ISSUED, nonce="2" * 32,
        )
        self.assertEqual(ob.calls, 1)

    def test_native_phios_bad_to_dict_output_refused(self):
        class Bad:
            def to_dict(self):
                return "not-an-observation"
        with self.assertRaises(ContractError):
            native_phios_status_export(Bad())

    def test_end_to_end_native_vessie_durable_journal(self):
        signed = v_envelope()
        i, e = intent_and_opened(signed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "work.sqlite3"
            with WorkJournal(path) as journal:
                head = journal.begin_work(i, e)["head_hash"]
                receipt = admit_export_frame(
                    journal, frame_export(signed),
                    keyring={"vessie-test": {
                        "issuer_id": "vessie:local", "source_kind": VESSEL,
                        "secret": SECRET,
                    }},
                    now=RECEIVED, expected_head=head, expected_task_id="task-direct",
                )
            self.assertTrue(receipt["shared_key_verified"])
            self.assertFalse(receipt["operator_consent_verified"])
            self.assertFalse(receipt["action_executed"])
            self.assertFalse(receipt["memory_admitted"])
            self.assertEqual(receipt["interop_receipt"]["projection"]["item_count"], 0)

    def test_end_to_end_native_phios_durable_journal(self):
        signed = p_envelope()
        i, e = intent_and_opened(signed)
        with tempfile.TemporaryDirectory() as directory:
            with WorkJournal(Path(directory) / "work.sqlite3") as journal:
                head = journal.begin_work(i, e)["head_hash"]
                receipt = admit_export_frame(
                    journal, frame_export(signed),
                    keyring={"phios-test": {
                        "issuer_id": "phios:local", "source_kind": PHIOS,
                        "secret": SECRET,
                    }}, now=RECEIVED, expected_head=head,
                )
            self.assertFalse(receipt["action_executed"])
            self.assertFalse(receipt["authority_granted"])
            self.assertTrue(receipt["shared_key_verified"])

    def test_native_from_original_packet_not_pinned_to_context_refused(self):
        signed = v_envelope()
        i, e = intent_and_opened(signed)
        i["context_refs"][0]["sha256"] = digest(sealed())
        with tempfile.TemporaryDirectory() as directory:
            with WorkJournal(Path(directory) / "work.sqlite3") as journal:
                with self.assertRaises(ContractError):
                    journal.begin_work(i,e)


if __name__ == "__main__":
    unittest.main()
