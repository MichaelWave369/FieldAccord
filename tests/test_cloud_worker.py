"""Offline FA-CW01 source-admission negative controls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import unittest

from fieldaccord.cloud_worker import SOURCE, REPO, inspect_cloud_worker
from fieldaccord.continuity import GENESIS, make_event
from fieldaccord.core import ContractError, digest

NOW = datetime(2026, 10, 8, 21, 20, tzinfo=timezone.utc)
WORK = "19f55a2d-3d2f-42ba-bf70-a94f8cdb71e5"


def sample():
    status = {
        "schema": "fielddeck.cloud-observation.v1", "receipt_kind": "observation_not_authorization",
        "run_at": "2026-10-08T21:10:46+00:00", "run_id": "37844903712",
        "trigger": "push", "sha": "8e81ffe",
        "run_url": "https://github.com/" + REPO + "/actions/runs/37844903712",
        "overall": "ok",
        "results": [
            {"task": "heartbeat", "kind": "observation", "status": "ok", "output": {"signal": "alive"}, "duration_s": 0},
            {"task": "repo_layout", "kind": "observation", "status": "ok", "output": {"required_files": 3, "present_files": 3}, "duration_s": 0},
            {"task": "github_repo_metrics", "kind": "observation", "status": "ok",
             "output": {"repository": REPO, "stars": 0, "open_issues_and_prs": 0}, "duration_s": 0.394}
        ],
    }
    history = [{"schema": "fielddeck.cloud-history.v1", "run_id": status["run_id"],
                "run_at": status["run_at"], "overall": "ok", "ok_count": 3, "error_count": 0}]
    run = {"id": 37844903712, "repository": {"full_name": REPO},
           "name": "FieldCloudWorker Observation Pilot", "path": ".github/workflows/worker.yml",
           "head_branch": "main", "event": "push",
           "head_sha": "8e81ffe30ecaa5c898850da8f7fa9cdaf69ca2a6", "status": "completed",
           "conclusion": "success", "html_url": status["run_url"],
           "created_at": "2026-10-08T21:10:38Z", "updated_at": "2026-10-08T21:16:19Z"}
    return status, history, run


def rig(status=None, history=None, run=None, now=NOW):
    s, h, r = sample()
    s = deepcopy(s if status is None else status)
    h = deepcopy(h if history is None else history)
    r = deepcopy(r if run is None else run)
    raw = json.dumps(s).encode()
    hist = "".join(json.dumps(row) + "\n" for row in h).encode()
    sig = sha256(raw).hexdigest()
    intent = {"schema": "fa.work_intent.v0.1", "work_id": WORK,
              "initiator": {"kind": "human", "id": "operator"},
              "objective": "Review a pinned cloud observation without taking action.",
              "requested_capabilities": ["discovery.read"], "attention_policy": "quiet",
              "context_refs": [{"reference": SOURCE, "sha256": sig, "epistemic": "unverified"}]}
    opened = make_event(event_id="04e50b27-4cd3-4e12-aad4-45b87f8ec415",
                        work_id=WORK, sequence=1, previous_hash=GENESIS,
                        occurred_at="2026-10-08T21:00:00Z",
                        actor={"kind": "human", "id": "operator"}, kind="WORK_OPENED",
                        data={"intent_sha256": digest(intent)})
    return [intent, [opened], raw, hist, r, opened["event_hash"], sig, now]


def review(p):
    return inspect_cloud_worker(*p[:5], expected_state_head=p[5], expected_status_sha256=p[6], now=p[7])


class CloudWorkerTests(unittest.TestCase):
    def test_success_is_review_only_and_redacted(self):
        q = review(rig())
        self.assertEqual(q["disposition"], "REVIEW_ONLY_OBSERVATION")
        self.assertEqual(len(q["task_statuses"]), 3)
        self.assertFalse(q["authority_granted"])
        self.assertFalse(q["action_executed"])
        self.assertFalse(q["memory_admitted"])
        self.assertFalse(q["network_accessed"])
        self.assertNotIn("alive", str(q))
        self.assertNotIn("stars", str(q))

    def test_independent_pin_and_head_required(self):
        p = rig(); p[6] = "f"*64
        with self.assertRaises(ContractError): review(p)
        p = rig(); p[5] = "f"*64
        with self.assertRaises(ContractError): review(p)

    def test_schema_and_output_injection_refused(self):
        s, h, r = sample()
        s["results"][0]["output"]["cmd"] = "rm -rf /"
        with self.assertRaises(ContractError): review(rig(s, h, r))
        s, h, r = sample()
        s["results"][0]["task"] = "execute_shell"
        with self.assertRaises(ContractError): review(rig(s, h, r))
        s, h, r = sample()
        s["authority_granted"] = True
        with self.assertRaises(ContractError): review(rig(s, h, r))

    def test_failure_remains_failure(self):
        s, h, r = sample()
        s["results"][0] = {"task": "heartbeat", "kind": "observation",
                            "status": "error", "error_code": "RuntimeError", "duration_s": 0.1}
        s["overall"] = "error"
        h[0]["overall"] = "error"; h[0]["ok_count"] = 2; h[0]["error_count"] = 1
        r["conclusion"] = "failure"
        self.assertEqual(review(rig(s, h, r))["disposition"], "TASK_FAILURE_OBSERVED")

    def test_stale(self):
        self.assertEqual(review(rig(now=NOW+timedelta(hours=9)))["disposition"], "STALE_OBSERVATION")

    def test_wrong_run_identity_refused(self):
        for k, v in (("head_branch", "unauthorized"), ("head_sha", "f"*40),
                     ("conclusion", "failure"), ("html_url", "https://evil.invalid")):
            s, h, r = sample(); r[k] = v
            with self.subTest(k=k), self.assertRaises(ContractError): review(rig(s, h, r))
        s, h, r = sample(); r["repository"]["full_name"] = "unknown/other"
        with self.assertRaises(ContractError): review(rig(s, h, r))

    def test_history_drift(self):
        s, h, r = sample(); h[0]["run_id"] = "99"
        with self.assertRaises(ContractError): review(rig(s, h, r))
        s, h, r = sample(); h.append(deepcopy(h[0]))
        with self.assertRaises(ContractError): review(rig(s, h, r))

    def test_future_refused(self):
        with self.assertRaises(ContractError): review(rig(now=NOW-timedelta(minutes=20)))

    def test_no_read_capability(self):
        p = rig(); p[0]["requested_capabilities"] = []
        with self.assertRaises(ContractError): review(p)

    def test_epistemic_claim_refused(self):
        p = rig(); p[0]["context_refs"][0]["epistemic"] = "observation"
        with self.assertRaises(ContractError): review(p)

    def test_duplicate_keys_refused(self):
        p = rig()
        p[2] = p[2].replace(b'"schema":', b'"schema": "evil", "schema":', 1)
        p[6] = sha256(p[2]).hexdigest()
        with self.assertRaises(ContractError): review(p)


if __name__ == "__main__":
    unittest.main()
