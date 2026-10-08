"""FA-CW02 tests are completely offline. No public API is fetched."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import unittest

from fieldaccord.acquisition import git_blob_sha
from fieldaccord.cloud_acquisition import (
    API, BRANCH, CloudPublicAcquisition, _url_is_allowed,
    acquire_cloud_worker_public, public_github_get,
)
from fieldaccord.cloud_worker import inspect_cloud_worker, SOURCE
from fieldaccord.continuity import GENESIS, make_event
from fieldaccord.core import ContractError, digest

COMMIT = "c" * 40
NOW = datetime(2026, 10, 8, 21, 20, tzinfo=timezone.utc)
WORK = "19f55a2d-3d2f-42ba-bf70-a94f8cdb71e5"


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def records():
    state = {
        "schema": "fielddeck.cloud-observation.v1",
        "receipt_kind": "observation_not_authorization",
        "run_at": "2026-10-08T21:10:46+00:00", "run_id": "37844903712",
        "trigger": "push", "sha": "8e81ffe",
        "run_url": "https://github.com/MichaelWave369/FieldCloudWorker/actions/runs/37844903712",
        "overall": "ok",
        "results": [
            {"task": "heartbeat", "kind": "observation", "status": "ok",
             "output": {"signal": "alive"}, "duration_s": 0},
            {"task": "repo_layout", "kind": "observation", "status": "ok",
             "output": {"required_files": 3, "present_files": 3}, "duration_s": 0},
            {"task": "github_repo_metrics", "kind": "observation", "status": "ok",
             "output": {"repository": "MichaelWave369/FieldCloudWorker", "stars": 0,
                        "open_issues_and_prs": 0}, "duration_s": 0.394},
        ],
    }
    history = [{"schema": "fielddeck.cloud-history.v1", "run_id": state["run_id"],
                "run_at": state["run_at"], "overall": "ok", "ok_count": 3, "error_count": 0}]
    run = {
        "id": 37844903712, "repository": {"full_name": "MichaelWave369/FieldCloudWorker"},
        "name": "FieldCloudWorker Observation Pilot",
        "path": ".github/workflows/worker.yml", "head_branch": "main",
        "event": "push", "head_sha": "8e81ffe30ecaa5c898850da8f7fa9cdaf69ca2a6",
        "status": "completed", "conclusion": "success", "html_url": state["run_url"],
        "created_at": "2026-10-08T21:10:38Z", "updated_at": "2026-10-08T21:16:19Z",
    }
    return state, history, run


def contents(path, body):
    return {
        "type": "file", "path": path, "name": path.rsplit("/", 1)[1],
        "encoding": "base64", "size": len(body), "sha": git_blob_sha(body),
        "content": base64.b64encode(body).decode("ascii"),
    }


def fixture(status=None, history=None, run=None, revision=COMMIT):
    current = records()
    state = deepcopy(current[0] if status is None else status)
    hist = deepcopy(current[1] if history is None else history)
    workflow_run = deepcopy(current[2] if run is None else run)
    data = {
        BRANCH: {"name": "main", "commit": {"sha": revision}},
        API + "/contents/docs/status.json?ref=" + revision:
            contents("docs/status.json", json_bytes(state)),
        API + "/contents/docs/history.jsonl?ref=" + revision:
            contents("docs/history.jsonl", b"".join(json_bytes(v) + b"\n" for v in hist)),
        API + "/actions/runs/" + state["run_id"]: workflow_run,
    }
    calls = []
    def fetch(url):
        calls.append(url)
        if url not in data:
            raise AssertionError("unexpected network URL: " + url)
        return json_bytes(data[url])
    return fetch, calls, data


class PublicCloudReadTests(unittest.TestCase):
    def test_success_exact_four_gets_no_authority(self):
        fetch, calls, _ = fixture()
        record = acquire_cloud_worker_public(transport=fetch, now=NOW)
        self.assertIsInstance(record, CloudPublicAcquisition)
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0], BRANCH)
        self.assertEqual(calls[1], API + "/contents/docs/status.json?ref=" + COMMIT)
        self.assertEqual(record.disposition, "UNVERIFIED_PUBLIC_OBSERVATION")
        summary = record.summary()
        self.assertFalse(summary["independent_prior_pin_verified"])
        self.assertFalse(summary["authority_granted"])
        self.assertFalse(summary["memory_admitted"])
        self.assertFalse(summary["action_executed"])
        self.assertNotIn("alive", json.dumps(summary))
        self.assertNotIn("stars", json.dumps(summary))

    def test_no_freeform_URL_or_private_endpoint(self):
        self.assertFalse(_url_is_allowed("https://evil.test/api"))
        self.assertFalse(_url_is_allowed(API + "/actions/workflows/worker.yml/dispatches"))
        self.assertFalse(_url_is_allowed(API + "/contents/.env?ref=" + COMMIT))
        with self.assertRaises(ContractError):
            public_github_get("https://example.com/private")

    def test_revision_must_be_exact_commit(self):
        fetch, _, _ = fixture(revision="main")
        with self.assertRaises(ContractError): acquire_cloud_worker_public(transport=fetch, now=NOW)

    def test_invalid_blob_fails(self):
        fetch, _, data = fixture()
        path = API + "/contents/docs/status.json?ref=" + COMMIT
        data[path]["sha"] = "f" * 40
        with self.assertRaises(ContractError): acquire_cloud_worker_public(transport=fetch, now=NOW)

    def test_wrong_resource_identity_fails(self):
        fetch, _, data = fixture()
        path = API + "/contents/docs/history.jsonl?ref=" + COMMIT
        data[path]["path"] = "docs/other.jsonl"
        with self.assertRaises(ContractError): acquire_cloud_worker_public(transport=fetch, now=NOW)

    def test_bad_metrics_payload_fails(self):
        state, hist, run = records()
        state["results"][2]["output"]["token"] = "credential"
        fetch, _, _ = fixture(state, hist, run)
        with self.assertRaises(ContractError): acquire_cloud_worker_public(transport=fetch, now=NOW)

    def test_run_metadata_mismatch_fails(self):
        state, hist, run = records()
        run["head_branch"] = "fake-branch"
        fetch, _, _ = fixture(state, hist, run)
        with self.assertRaises(ContractError): acquire_cloud_worker_public(transport=fetch, now=NOW)

    def test_stale_and_future_dates(self):
        fetch, _, _ = fixture()
        late = acquire_cloud_worker_public(transport=fetch, now=NOW + timedelta(hours=9))
        self.assertEqual(late.disposition, "STALE_OBSERVATION")
        fetch, _, _ = fixture()
        with self.assertRaises(ContractError):
            acquire_cloud_worker_public(transport=fetch, now=NOW - timedelta(hours=1))

    def test_failed_run_stays_failure(self):
        state, hist, run = records()
        state["overall"] = "error"
        state["results"][0] = {"task": "heartbeat", "kind": "observation",
                               "status": "error", "error_code": "RuntimeError", "duration_s": 0}
        hist[0]["overall"] = "error"; hist[0]["ok_count"] = 2; hist[0]["error_count"] = 1
        run["conclusion"] = "failure"
        fetch, _, _ = fixture(state, hist, run)
        self.assertEqual(acquire_cloud_worker_public(transport=fetch, now=NOW).disposition,
                         "TASK_FAILURE_OBSERVED")

    def test_prior_intent_pin_required_for_FA_CW01_admission(self):
        fetch, _, _ = fixture()
        acquired = acquire_cloud_worker_public(transport=fetch, now=NOW)
        prior_sha = sha256(acquired.status_bytes).hexdigest()  # Synthetic independent fixture pin.
        intent = {
            "schema": "fa.work_intent.v0.1", "work_id": WORK,
            "initiator": {"kind": "human", "id": "operator"},
            "objective": "Review independently pinned cloud observation without invoking tools.",
            "requested_capabilities": ["discovery.read"], "attention_policy": "quiet",
            "context_refs": [{"reference": SOURCE, "sha256": prior_sha, "epistemic": "unverified"}],
        }
        event = make_event(
            event_id="04e50b27-4cd3-4e12-aad4-45b87f8ec415",
            work_id=WORK, sequence=1, previous_hash=GENESIS,
            occurred_at="2026-10-08T21:00:00Z", actor={"kind": "human", "id": "operator"},
            kind="WORK_OPENED", data={"intent_sha256": digest(intent)},
        )
        reviewed = inspect_cloud_worker(
            intent, [event], acquired.status_bytes, acquired.history_bytes, acquired.run_metadata,
            expected_state_head=event["event_hash"], expected_status_sha256=prior_sha, now=NOW)
        self.assertFalse(reviewed["authority_granted"])
        self.assertEqual(reviewed["disposition"], "REVIEW_ONLY_OBSERVATION")
        with self.assertRaises(ContractError):
            inspect_cloud_worker(
                intent, [event], acquired.status_bytes, acquired.history_bytes, acquired.run_metadata,
                expected_state_head=event["event_hash"], expected_status_sha256="e"*64, now=NOW)


if __name__ == "__main__":
    unittest.main()
