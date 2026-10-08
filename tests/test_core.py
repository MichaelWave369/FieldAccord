"""FA-01 regression and negative-control suite. No network, filesystem writes, or tools."""

import copy
import json
from pathlib import Path
import unittest

from fieldaccord.core import (
    ContractError, assess, receipt_digest_is_valid,
    validate_intent, validate_capability, validate_proposal,
)

ROOT = Path(__file__).resolve().parents[1] / "examples"


def fixtures():
    return [
        json.loads((ROOT / name).read_text(encoding="utf-8"))
        for name in ("intent.json", "capability.json", "proposal.json")
    ]


class FieldAccordTests(unittest.TestCase):
    def test_sample_is_review_only(self):
        i, c, p = fixtures()
        result = assess(i, c, p)
        self.assertEqual(result["decision"], "REVIEW_REQUIRED")
        self.assertEqual(result["reason"], "NO_EXECUTION_AUTHORITY")
        self.assertFalse(result["authority_granted"])
        self.assertFalse(result["action_executed"])
        self.assertTrue(receipt_digest_is_valid(result))

    def test_deterministic_replay(self):
        first = assess(*fixtures())
        second = assess(*fixtures())
        self.assertEqual(first, second)

    def test_different_payload_changes_receipt(self):
        i, c, p = fixtures()
        original = assess(i, c, p)
        p["payload_sha256"] = "2" * 64
        modified = assess(i, c, p)
        self.assertNotEqual(original["receipt_sha256"], modified["receipt_sha256"])

    def test_digest_tamper_detected_but_not_signature(self):
        receipt = assess(*fixtures())
        receipt["reason"] = "RESOURCE_OUT_OF_SCOPE"
        self.assertFalse(receipt_digest_is_valid(receipt))

    def test_work_mismatch_blocked(self):
        i, c, p = fixtures()
        p["work_id"] = "bb7a7af9-ce69-4056-8cfd-a481021f1274"
        self.assertEqual(assess(i, c, p)["reason"], "WORK_ID_MISMATCH")

    def test_capability_mismatch_blocked(self):
        i, c, p = fixtures()
        p["capability_id"] = "github.patch.draft"
        self.assertEqual(assess(i, c, p)["reason"], "CAPABILITY_MISMATCH")

    def test_unrequested_capability_blocked(self):
        i, c, p = fixtures()
        i["requested_capabilities"] = []
        self.assertEqual(assess(i, c, p)["reason"], "UNREQUESTED_CAPABILITY")

    def test_scope_mismatch_blocked(self):
        i, c, p = fixtures()
        p["resource"] = "github:MichaelWave369/PhiOS"
        self.assertEqual(assess(i, c, p)["reason"], "RESOURCE_OUT_OF_SCOPE")

    def test_absent_evidence_reference_blocked(self):
        i, c, p = fixtures()
        p["evidence_refs"] = ["github:example/not_in_intent"]
        self.assertEqual(assess(i, c, p)["reason"], "EVIDENCE_NOT_IN_CONTEXT")

    def test_all_effect_classes_remain_review_only(self):
        for effect in ("read", "write", "external", "physical"):
            with self.subTest(effect=effect):
                i, c, p = fixtures()
                c["effect"] = effect
                result = assess(i, c, p)
                self.assertEqual(result["decision"], "REVIEW_REQUIRED")
                self.assertFalse(result["authority_granted"])
                self.assertFalse(result["action_executed"])

    def test_agent_initiation_confers_no_grant(self):
        i, c, p = fixtures()
        i["initiator"] = {"kind": "agent", "id": "vessie"}
        self.assertFalse(assess(i, c, p)["authority_granted"])

    def test_intent_with_smuggled_approval_rejected(self):
        i, c, p = fixtures()
        i["operator_approved"] = True
        with self.assertRaises(ContractError):
            assess(i, c, p)

    def test_capability_with_claimed_permission_rejected(self):
        i, c, p = fixtures()
        c["execute_authorized"] = True
        with self.assertRaises(ContractError):
            assess(i, c, p)

    def test_proposal_with_execute_field_rejected(self):
        i, c, p = fixtures()
        p["execute"] = True
        with self.assertRaises(ContractError):
            assess(i, c, p)

    def test_noncanonical_id_rejected(self):
        i, _, _ = fixtures()
        i["work_id"] = "not-a-uuid"
        with self.assertRaises(ContractError):
            validate_intent(i)

    def test_stale_protocol_version_rejected(self):
        _, c, _ = fixtures()
        c["schema"] = "fa.capability_declaration.v0.0"
        with self.assertRaises(ContractError):
            validate_capability(c)

    def test_unknown_epistemic_promotion_rejected(self):
        i, _, _ = fixtures()
        i["context_refs"][0]["epistemic"] = "proved"
        with self.assertRaises(ContractError):
            validate_intent(i)

    def test_duplicate_context_reference_rejected(self):
        i, _, _ = fixtures()
        i["context_refs"].append(copy.deepcopy(i["context_refs"][0]))
        with self.assertRaises(ContractError):
            validate_intent(i)

    def test_wildcard_scope_rejected(self):
        _, c, _ = fixtures()
        c["scope"] = ["github:*"]
        with self.assertRaises(ContractError):
            validate_capability(c)

    def test_duplicate_evidence_rejected(self):
        _, _, p = fixtures()
        p["evidence_refs"].append(p["evidence_refs"][0])
        with self.assertRaises(ContractError):
            validate_proposal(p)

    def test_missing_property_rejected(self):
        _, _, p = fixtures()
        del p["payload_sha256"]
        with self.assertRaises(ContractError):
            validate_proposal(p)

    def test_boolean_not_accepted_as_object(self):
        with self.assertRaises(ContractError):
            validate_intent(True)

    def test_no_implicit_grant_in_output(self):
        record = assess(*fixtures())
        self.assertNotIn("approval_token", record)
        self.assertNotIn("permission", record)
        self.assertNotIn("tool_result", record)


if __name__ == "__main__":
    unittest.main()
