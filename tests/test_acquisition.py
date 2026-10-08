"""FA-04 offline tests: real source-wire shape, no actual network traffic."""

import base64
from copy import deepcopy
import json
import unittest

from fieldaccord.acquisition import (
    API_PREFIX, READ_SCHEMA, acquire_fielddeck, git_blob_sha,
    github_public_get, inspect_acquired_fielddeck, public_summary, strict_json,
)
from fieldaccord.bridge import FIELDDECK_LOCATOR, FIELDDECK_V07
from fieldaccord.continuity import GENESIS, make_event
from fieldaccord.core import ContractError, digest

WORK_ID = "19f55a2d-3d2f-42ba-bf70-a94f8cdb71e5"
EVENT_ID = "04e50b27-4cd3-4e12-aad4-45b87f8ec415"
CAPTURE_ID = "31f0c944-4f4e-4eb4-8889-b5e9da3f07dd"
COMMIT = "c" * 40


def manifest():
    return {
        "schema_version": "0.7.0", "name": "FieldDeck",
        "execution_policy": {
            "default": "deny", "require_authenticated_runner": True,
            "freeform_shell": False, "receipt_required": True,
        },
        "actions": [
            {"id": "catalog-health", "kind": "workflow",
             "status": "ready", "risk": "low", "task": "not executable"},
            {"id": "local-runner", "kind": "future",
             "status": "locked", "risk": "high", "task": "never execute"},
        ],
        "review_board_protocol": {
            "automatic_execution": False, "decision_commands": ["accept", "decline"]
        },
    }


def source(data=None):
    if data is None:
        data = manifest()
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    blob_sha = git_blob_sha(raw)
    pin = {
        "schema": "fa.source_pin.v0.1",
        "provider": "github_public_contents",
        "repository": "MichaelWave369/FieldDeck",
        "path": "public/fielddeck.manifest.json",
        "commit_sha": COMMIT, "git_blob_sha": blob_sha,
        "manifest_version": "0.7.0", "source_kind": FIELDDECK_V07,
        "source_locator": FIELDDECK_LOCATOR,
    }
    envelope = {
        "type": "file", "name": "fielddeck.manifest.json",
        "path": "public/fielddeck.manifest.json", "sha": blob_sha,
        "size": len(raw), "encoding": "base64",
        "content": base64.b64encode(raw).decode("ascii"),
        "url": "https://api.github.com/mock",
        "html_url": "https://github.com/mock",
        "git_url": "https://api.github.com/mock/blob",
        "download_url": None, "_links": {},
    }
    return pin, envelope, data


def fake_transport(envelope, spy=None):
    def fetch(url):
        if spy is not None:
            spy.append(url)
        return json.dumps(envelope).encode("utf-8")
    return fetch


def acquire(packet):
    pin, env, _ = packet
    return acquire_fielddeck(pin=pin, transport=fake_transport(env))


def work(data):
    pin, env, payload = data
    i = {
        "schema": "fa.work_intent.v0.1", "work_id": WORK_ID,
        "initiator": {"kind": "human", "id": "operator"},
        "objective": "Review the published FieldDeck manifest without taking any actions.",
        "requested_capabilities": ["discovery.read"],
        "attention_policy": "important",
        "context_refs": [{
            "reference": FIELDDECK_LOCATOR, "sha256": digest(payload),
            "epistemic": "unverified",
        }],
    }
    event = make_event(
        event_id=EVENT_ID, work_id=WORK_ID, sequence=1,
        previous_hash=GENESIS, occurred_at="2026-10-07T20:00:00Z",
        actor={"kind": "human", "id": "operator"},
        kind="WORK_OPENED", data={"intent_sha256": digest(i)},
    )
    return i, [event], event["event_hash"]


class AcquisitionTests(unittest.TestCase):
    def test_git_blob_sha_known_vector(self):
        self.assertEqual(
            git_blob_sha(b"test content\n"),
            "d670460b4b4aece5915caf5c68d12f560a9fe3e4",
        )

    def test_snapshot_accepts_pinned_blob_only(self):
        packet = source()
        result = acquire(packet)
        self.assertEqual(result["schema"], READ_SCHEMA)
        self.assertEqual(result["git_blob_sha"], packet[0]["git_blob_sha"])
        self.assertEqual(result["projection"]["action_count"], 2)
        self.assertFalse(result["authority_granted"])
        self.assertFalse(result["action_executed"])
        self.assertFalse(result["source_authorship_authenticated"])

    def test_exact_pinned_url_used(self):
        packet = source()
        spy = []
        acquire_fielddeck(pin=packet[0], transport=fake_transport(packet[1], spy))
        self.assertEqual(spy, [API_PREFIX + COMMIT])

    def test_projection_excludes_payloads_and_urls(self):
        text = str(public_summary(acquire(source())))
        self.assertNotIn("task", text)
        self.assertNotIn("not executable", text)
        self.assertNotIn("decision_commands", text)
        self.assertNotIn("github.com/mock", text)
        self.assertNotIn("'payload':", text)

    def test_bridge_handoff_is_no_authority(self):
        packet = source()
        intent, events, head = work(packet)
        result = inspect_acquired_fielddeck(
            intent, events, expected_state_head=head, capture_id=CAPTURE_ID,
            transport=fake_transport(packet[1]), pin=packet[0],
        )
        self.assertEqual(result["bridge_receipt"]["disposition"], "REVIEW_CANDIDATE")
        self.assertFalse(result["bridge_receipt"]["provenance_authenticated"])
        self.assertFalse(result["bridge_receipt"]["history_modified"])
        self.assertFalse(result["authority_granted"])
        self.assertFalse(result["action_executed"])

    def test_same_bytes_same_output(self):
        packet = source()
        self.assertEqual(public_summary(acquire(packet)), public_summary(acquire(packet)))

    def test_corrupt_content_refused(self):
        packet = source()
        packet[1]["content"] = "!!!"
        with self.assertRaises(ContractError):
            acquire(packet)

    def test_mutated_blob_with_old_id_refused(self):
        packet = source()
        payload = manifest()
        payload["actions"][0]["risk"] = "high"
        packet[1]["content"] = base64.b64encode(json.dumps(payload).encode()).decode()
        packet[1]["size"] = len(json.dumps(payload).encode())
        with self.assertRaises(ContractError):
            acquire(packet)

    def test_forged_blob_id_refused(self):
        packet = source()
        packet[1]["sha"] = "0" * 40
        with self.assertRaises(ContractError):
            acquire(packet)

    def test_changed_pin_commit_alters_requested_url(self):
        packet = source()
        packet[0]["commit_sha"] = "d" * 40
        spy = []
        acquire_fielddeck(pin=packet[0], transport=fake_transport(packet[1], spy))
        self.assertEqual(spy, [API_PREFIX + "d" * 40])

    def test_rejects_extra_pin_authority(self):
        packet = source()
        packet[0]["authority_granted"] = True
        with self.assertRaises(ContractError):
            acquire(packet)

    def test_rejects_wrong_repository(self):
        packet = source()
        packet[0]["repository"] = "attacker/FieldDeck"
        with self.assertRaises(ContractError):
            acquire(packet)

    def test_rejects_wrong_source_kind(self):
        packet = source()
        packet[0]["source_kind"] = "fielddeck.manifest.v0.6"
        with self.assertRaises(ContractError):
            acquire(packet)

    def test_rejects_manifest_policy_upgrade(self):
        p = manifest()
        p["execution_policy"]["default"] = "allow"
        with self.assertRaises(ContractError):
            acquire(source(p))

    def test_rejects_source_version_drift(self):
        p = manifest()
        p["schema_version"] = "0.8.0"
        with self.assertRaises(ContractError):
            acquire(source(p))

    def test_rejects_future_ready(self):
        p = manifest()
        p["actions"][1]["status"] = "ready"
        with self.assertRaises(ContractError):
            acquire(source(p))

    def test_rejects_payload_larger_than_limit(self):
        packet = source()
        packet[1]["size"] = 70000
        with self.assertRaises(ContractError):
            acquire(packet)

    def test_rejects_bad_envelope_field(self):
        packet = source()
        packet[1]["execute"] = True
        with self.assertRaises(ContractError):
            acquire(packet)

    def test_rejects_non_json_response(self):
        packet = source()
        with self.assertRaises(ContractError):
            acquire_fielddeck(pin=packet[0], transport=lambda url: b"<!DOCTYPE html>")

    def test_rejects_duplicate_json_keys(self):
        with self.assertRaises(ContractError):
            strict_json(b'{"name":"x","name":"y"}')

    def test_rejects_nonfinite_json_number(self):
        with self.assertRaises(ContractError):
            strict_json(b'{"x":NaN}')

    def test_rejects_invalid_utf8(self):
        with self.assertRaises(ContractError):
            strict_json(b"\xff")

    def test_refuse_external_host_without_network(self):
        with self.assertRaises(ContractError):
            github_public_get("https://evil.example/a?ref=" + COMMIT)

    def test_refuse_unpinned_branch_without_network(self):
        with self.assertRaises(ContractError):
            github_public_get(API_PREFIX + "main")

    def test_old_context_digest_rejected(self):
        packet = source()
        intent, events, head = work(packet)
        intent["context_refs"][0]["sha256"] = "0" * 64
        with self.assertRaises(ContractError):
            inspect_acquired_fielddeck(intent, events, expected_state_head=head,
                capture_id=CAPTURE_ID, transport=fake_transport(packet[1]), pin=packet[0])

    def test_stale_event_head_rejected(self):
        packet = source()
        intent, events, head = work(packet)
        with self.assertRaises(ContractError):
            inspect_acquired_fielddeck(intent, events, expected_state_head="0" * 64,
                capture_id=CAPTURE_ID, transport=fake_transport(packet[1]), pin=packet[0])

    def test_cross_work_id_rejected(self):
        packet = source()
        intent, events, head = work(packet)
        intent["work_id"] = "018c7d9b-7d72-4a7e-9c64-01d8ee3f3f19"
        with self.assertRaises(ContractError):
            inspect_acquired_fielddeck(intent, events, expected_state_head=head,
                capture_id=CAPTURE_ID, transport=fake_transport(packet[1]), pin=packet[0])

    def test_no_request_of_read_capability_refused(self):
        packet = source()
        intent, events, head = work(packet)
        intent["requested_capabilities"] = []
        with self.assertRaises(ContractError):
            inspect_acquired_fielddeck(intent, events, expected_state_head=head,
                capture_id=CAPTURE_ID, transport=fake_transport(packet[1]), pin=packet[0])


if __name__ == "__main__":
    unittest.main()
