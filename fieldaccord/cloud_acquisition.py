"""FA-CW02: explicit, bounded public GitHub read for FieldCloudWorker.

The checkout revision is taken from MOVING main. It is a consistency snapshot,
NOT an independently trusted pin. Callers who need FA-CW01 admission must
supply a preexisting separately held digest and WorkIntent/WorkEvent anchors.

No credentials, writes, retries, background work, execution, model admission,
notifications, or authority grants. The returned bytes stay in memory.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import hashlib
import re
import ssl
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener

from .acquisition import strict_json, git_blob_sha
from .cloud_worker import (
    REPO, parse_status, check_history, check_run,
)
from .core import ContractError

API = "https://api.github.com/repos/" + REPO
BRANCH = API + "/branches/main"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
MAX_RESPONSE = 100_000
MAX_STATUS = 16_384
MAX_HISTORY = 32_768
RUN = re.compile(r"[1-9][0-9]{0,18}\Z")
CONTENTS = {
    "status": "docs/status.json",
    "history": "docs/history.jsonl",
}


def demand(ok: bool, why: str) -> None:
    if not ok:
        raise ContractError("cloud_public: " + why)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ContractError("cloud_public: redirects are forbidden")


def _url_is_allowed(url: str) -> bool:
    if url == BRANCH:
        return True
    prefix = re.escape(API)
    return bool(
        re.fullmatch(prefix + r"/contents/docs/(?:status\.json|history\.jsonl)\?ref=[0-9a-f]{40}", url)
        or re.fullmatch(prefix + r"/actions/runs/[1-9][0-9]{0,18}", url)
    )


def public_github_get(url: str) -> bytes:
    """A single HTTPS GET to one exact GitHub resource; no authentication."""
    demand(type(url) is str and _url_is_allowed(url), "URL not on allowlist")
    request = Request(url, method="GET", headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "FieldAccord-FA-CW02-ReadOnly",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    try:
        with opener.open(request, timeout=8) as response:
            demand(response.status == 200, "unexpected HTTP status")
            media_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            demand(media_type in ("application/json", "application/vnd.github+json"), "unexpected media type")
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    parsed = int(length)
                except ValueError as exc:
                    raise ContractError("cloud_public: invalid content length") from exc
                demand(0 <= parsed <= MAX_RESPONSE, "response too large")
            body = response.read(MAX_RESPONSE + 1)
            demand(0 < len(body) <= MAX_RESPONSE, "response too large or empty")
            return body
    except (HTTPError, URLError, OSError) as exc:
        raise ContractError("cloud_public: public GitHub GET failed") from exc


def _json(url: str, transport: Callable[[str], bytes]) -> dict[str, Any]:
    demand(_url_is_allowed(url), "transport URL not allowed")
    raw = transport(url)
    demand(type(raw) is bytes and 0 < len(raw) <= MAX_RESPONSE, "transport response size/type invalid")
    doc = strict_json(raw)
    demand(type(doc) is dict, "response is not a JSON object")
    return doc


def _revision(transport: Callable[[str], bytes]) -> str:
    branch = _json(BRANCH, transport)
    demand(branch.get("name") == "main" and type(branch.get("commit")) is dict, "unexpected branch")
    commit = branch["commit"].get("sha")
    demand(type(commit) is str and SHA40.fullmatch(commit) is not None, "invalid branch commit")
    return commit


def _file_at(path: str, commit: str, cap: int, transport: Callable[[str], bytes]) -> bytes:
    url = API + "/contents/" + path + "?ref=" + commit
    doc = _json(url, transport)
    demand(doc.get("type") == "file" and doc.get("path") == path and
           doc.get("name") == path.rsplit("/", 1)[1] and
           doc.get("encoding") == "base64", "unexpected content identity")
    encoded = doc.get("content")
    demand(type(encoded) is str and len(encoded) <= cap * 2 + 100, "encoded content invalid")
    try:
        data = base64.b64decode("".join(encoded.split()), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ContractError("cloud_public: bad base64 content") from exc
    demand(type(doc.get("size")) is int and doc["size"] == len(data) and
           0 < len(data) <= cap, "content size mismatch")
    demand(type(doc.get("sha")) is str and doc["sha"] == git_blob_sha(data), "Git blob mismatch")
    return data


@dataclass(frozen=True)
class CloudPublicAcquisition:
    """Explicit untrusted acquisition. Do not print raw records in logs."""
    status_bytes: bytes = field(repr=False)
    history_bytes: bytes = field(repr=False)
    run_metadata: dict[str, Any] = field(repr=False)
    branch_commit_sha: str
    status_sha256: str
    observed_at: str
    run_id: str
    disposition: str
    task_statuses: tuple[tuple[str, str], ...]
    history_count: int

    def summary(self) -> dict[str, Any]:
        return {
            "schema": "fa.cloud_public_read.v0.1",
            "source_repository": REPO,
            "branch_snapshot_sha": self.branch_commit_sha,
            "status_sha256": self.status_sha256,
            "run_id": self.run_id,
            "observed_at": self.observed_at,
            "disposition": self.disposition,
            "task_statuses": [dict(task=name, status=state) for name, state in self.task_statuses],
            "history_count": self.history_count,
            "public_run_metadata_correlated": True,
            "independent_prior_pin_verified": False,
            "source_authorship_authenticated": False,
            "measurement_truth_authenticated": False,
            "authority_granted": False,
            "action_executed": False,
            "notification_dispatched": False,
            "memory_admitted": False,
            "source_files_modified": False,
        }


def acquire_cloud_worker_public(*, transport: Callable[[str], bytes] | None = None,
                                now: datetime | None = None) -> CloudPublicAcquisition:
    """Four public GETs when called explicitly, none on import. No auto pinning."""
    reader = public_github_get if transport is None else transport
    present = datetime.now(timezone.utc) if now is None else now
    demand(type(present) is datetime and present.tzinfo is not None and
           present.utcoffset() is not None, "aware clock required")
    present = present.astimezone(timezone.utc)

    commit = _revision(reader)
    status_raw = _file_at(CONTENTS["status"], commit, MAX_STATUS, reader)
    history_raw = _file_at(CONTENTS["history"], commit, MAX_HISTORY, reader)
    status, observed, projected = parse_status(status_raw)
    demand(observed <= present + timedelta(minutes=5), "future-dated observation")
    count = check_history(history_raw, status, projected)

    run_id = status["run_id"]
    demand(type(run_id) is str and RUN.fullmatch(run_id) is not None, "run ID invalid")
    run = _json(API + "/actions/runs/" + run_id, reader)
    check_run(status, observed, run)

    disposition = (
        "STALE_OBSERVATION" if present - observed > timedelta(hours=8)
        else "TASK_FAILURE_OBSERVED" if status["overall"] == "error"
        else "UNVERIFIED_PUBLIC_OBSERVATION"
    )
    return CloudPublicAcquisition(
        status_bytes=status_raw, history_bytes=history_raw, run_metadata=run,
        branch_commit_sha=commit,
        status_sha256=hashlib.sha256(status_raw).hexdigest(),
        observed_at=status["run_at"], run_id=run_id, disposition=disposition,
        task_statuses=tuple((task["task"], task["status"]) for task in projected),
        history_count=count,
    )
