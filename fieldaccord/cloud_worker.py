"""Offline, intent-bound FieldCloudWorker observation projection. No IO or grants."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re

from .acquisition import strict_json
from .continuity import replay_work
from .core import ContractError, SHA256, _match, _record, digest, validate_intent

SOURCE = "github:MichaelWave369/FieldCloudWorker/docs/status.json"
REPO = "MichaelWave369/FieldCloudWorker"
WORKFLOW = ".github/workflows/worker.yml"
TASKS = {"heartbeat", "repo_layout", "github_repo_metrics"}
RUN_ID = re.compile(r"[1-9][0-9]{0,18}\Z")
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)\Z")
SHA7 = re.compile(r"[0-9a-f]{7}\Z")
ERR = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,50}\Z")


def check(ok, message):
    if not ok:
        raise ContractError("cloud_worker: " + message)


def when(text):
    check(type(text) is str and STAMP.fullmatch(text) is not None, "bad timestamp")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise ContractError("cloud_worker: bad calendar date") from exc


def parse_status(raw):
    check(type(raw) is bytes and 0 < len(raw) <= 16384, "bad status size")
    data = _record(strict_json(raw), {
        "schema", "receipt_kind", "run_at", "run_id", "trigger",
        "sha", "run_url", "overall", "results",
    }, "CloudStatus")
    check(data["schema"] == "fielddeck.cloud-observation.v1" and
          data["receipt_kind"] == "observation_not_authorization", "unsupported status schema")
    check(type(data["run_id"]) is str and RUN_ID.fullmatch(data["run_id"]) is not None, "bad run ID")
    check(type(data["sha"]) is str and SHA7.fullmatch(data["sha"]) is not None, "bad SHA")
    check(data["trigger"] in ("push", "schedule", "workflow_dispatch"), "bad event")
    check(data["run_url"] == "https://github.com/" + REPO + "/actions/runs/" + data["run_id"], "bad URL")
    check(data["overall"] in ("ok", "error"), "bad outcome")
    observed = when(data["run_at"])
    results = data["results"]
    check(type(results) is list and len(results) == 3, "bad task count")
    seen = set()
    projection = []
    for task in results:
        check(type(task) is dict and task.get("task") in TASKS and task["task"] not in seen, "unknown task")
        seen.add(task["task"])
        check(task.get("kind") == "observation" and task.get("status") in ("ok", "error"), "bad task status")
        duration = task.get("duration_s")
        check(type(duration) in (int, float) and 0 <= duration <= 600, "bad duration")
        if task["status"] == "error":
            _record(task, {"task", "kind", "status", "error_code", "duration_s"}, "CloudTaskError")
            check(type(task["error_code"]) is str and ERR.fullmatch(task["error_code"]) is not None, "bad error code")
        else:
            _record(task, {"task", "kind", "status", "output", "duration_s"}, "CloudTaskOK")
            output = task["output"]
            if task["task"] == "heartbeat":
                _record(output, {"signal"}, "Heartbeat")
                check(output["signal"] == "alive", "bad heartbeat")
            elif task["task"] == "repo_layout":
                _record(output, {"required_files", "present_files"}, "Layout")
                check(type(output["required_files"]) is int and type(output["present_files"]) is int and
                      output["required_files"] == 3 and output["present_files"] == 3, "bad layout")
            else:
                _record(output, {"repository", "stars", "open_issues_and_prs"}, "RepoMetrics")
                check(output["repository"] == REPO, "bad metric source")
                check(all(type(output[k]) is int and 0 <= output[k] < 1_000_000_000
                          for k in ("stars", "open_issues_and_prs")), "bad metrics")
        projection.append({"task": task["task"], "status": task["status"]})
    failed = sum(t["status"] == "error" for t in projection)
    check(data["overall"] == ("error" if failed else "ok"), "contradictory status")
    return data, observed, sorted(projection, key=lambda t: t["task"])


def check_history(raw, status, projection):
    check(type(raw) is bytes and 0 < len(raw) <= 32768, "bad history size")
    try:
        rows = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ContractError("cloud_worker: bad history encoding") from exc
    check(1 <= len(rows) <= 30 and all(line.strip() for line in rows), "bad history row count")
    prior = None
    seen = set()
    for line in rows:
        item = _record(strict_json(line.encode("utf-8")), {
            "schema", "run_id", "run_at", "overall", "ok_count", "error_count",
        }, "CloudHistory")
        check(item["schema"] == "fielddeck.cloud-history.v1", "bad history schema")
        check(type(item["run_id"]) is str and RUN_ID.fullmatch(item["run_id"]) is not None
              and item["run_id"] not in seen, "bad/duplicate history ID")
        seen.add(item["run_id"])
        stamp = when(item["run_at"])
        check(prior is None or stamp >= prior, "history reordered")
        prior = stamp
        check(item["overall"] in ("ok", "error"), "bad history result")
        check(type(item["ok_count"]) is int and type(item["error_count"]) is int and
              0 <= item["ok_count"] <= 3 and 0 <= item["error_count"] <= 3 and
              item["ok_count"] + item["error_count"] == 3 and
              item["overall"] == ("error" if item["error_count"] else "ok"), "bad history counts")
    successes = sum(t["status"] == "ok" for t in projection)
    check(item["run_id"] == status["run_id"] and item["run_at"] == status["run_at"]
          and item["overall"] == status["overall"] and item["ok_count"] == successes
          and item["error_count"] == 3-successes, "latest history mismatch")
    return len(rows)


def check_run(status, observed, run):
    check(type(run) is dict and type(run.get("repository")) is dict and
          run["repository"].get("full_name") == REPO, "wrong run repository")
    check(type(run.get("id")) is int and run["id"] == int(status["run_id"]), "wrong run identifier")
    check(run.get("name") == "FieldCloudWorker Observation Pilot" and run.get("path") == WORKFLOW, "wrong workflow")
    check(run.get("head_branch") == "main" and run.get("event") == status["trigger"], "wrong branch/event")
    check(type(run.get("head_sha")) is str and re.fullmatch(r"[0-9a-f]{40}", run["head_sha"]) is not None
          and run["head_sha"].startswith(status["sha"]), "wrong SHA")
    check(run.get("status") == "completed" and
          run.get("conclusion") == ("success" if status["overall"] == "ok" else "failure"), "wrong run outcome")
    check(run.get("html_url") == status["run_url"], "wrong run URL")
    created, updated = when(run.get("created_at")), when(run.get("updated_at"))
    drift = timedelta(minutes=5)
    check(created <= updated and created-drift <= observed <= updated+drift, "run timestamp drift")


def inspect_cloud_worker(intent, events, status_bytes, history_bytes, github_run, *,
                         expected_state_head, expected_status_sha256, now):
    """Inspect caller-supplied evidence; prior pins must originate outside this call."""
    work = validate_intent(intent)
    check("discovery.read" in work["requested_capabilities"], "read capability not requested")
    _match(expected_state_head, SHA256, "expected_state_head")
    _match(expected_status_sha256, SHA256, "expected_status_sha256")
    state = replay_work(work, events, expected_head=expected_state_head)
    check(state["status"] != "CLOSED", "work already closed")
    check(type(now) is datetime and now.tzinfo is not None and now.utcoffset() is not None,
          "timezone-aware clock required")
    now = now.astimezone(timezone.utc)
    check(type(status_bytes) is bytes and 0 < len(status_bytes) <= 16384, "bad status bytes")
    raw_sha = sha256(status_bytes).hexdigest()
    check(raw_sha == expected_status_sha256, "source hash drift")
    pins = [r for r in work["context_refs"] if r["reference"] == SOURCE and
            r["sha256"] == raw_sha and r["epistemic"] == "unverified"]
    check(len(pins) == 1, "independent WorkIntent pin missing")
    status, observed, projection = parse_status(status_bytes)
    check(observed <= now + timedelta(minutes=5), "future-dated source")
    count = check_history(history_bytes, status, projection)
    check_run(status, observed, github_run)
    stale = now-observed > timedelta(hours=8)
    disposition = ("STALE_OBSERVATION" if stale else
                   "TASK_FAILURE_OBSERVED" if status["overall"] == "error" else
                   "REVIEW_ONLY_OBSERVATION")
    receipt = {
        "schema": "fa.cloud_worker_observation.v0.1",
        "work_id": work["work_id"], "intent_head_sha256": expected_state_head,
        "source_locator": SOURCE, "source_status_sha256": raw_sha,
        "source_epistemic": "unverified",
        "run_id": status["run_id"], "run_url": status["run_url"],
        "observed_at": status["run_at"], "history_count": count,
        "task_statuses": projection, "disposition": disposition,
        "run_metadata_correlated": True, "observation_truth_authenticated": False,
        "source_authorship_authenticated": False, "authority_granted": False,
        "action_executed": False, "notification_dispatched": False,
        "memory_admitted": False, "network_accessed": False, "history_modified": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt
