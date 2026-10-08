"""FA-04: opt-in pinned public GitHub read. No tokens, writes or execution.

Pinned Git blob comparison binds bytes to a reviewed repository revision;
it is NOT source-authorship authentication, consent, or evidence of truth.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import ssl
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .bridge import (
    FIELDDECK_LOCATOR, FIELDDECK_V07, MAX_BYTES, _fielddeck, inspect_snapshot,
)
from .core import ContractError, _record, digest

PIN_SCHEMA = "fa.source_pin.v0.1"
READ_SCHEMA = "fa.read_provenance.v0.1"
GITHUB_SHA = re.compile(r"[0-9a-f]{40}\Z")
RESPONSE_CAP = 180_000
PIN_FILE = Path(__file__).resolve().parent.parent / "pins" / "fielddeck-v07.json"
REPO = "MichaelWave369/FieldDeck"
FILE_PATH = "public/fielddeck.manifest.json"
API_PREFIX = ("https://api.github.com/repos/MichaelWave369/FieldDeck/"
              "contents/public/fielddeck.manifest.json?ref=")


def _pin(value: Any) -> dict[str, str]:
    obj = _record(value, {
        "schema", "provider", "repository", "path", "commit_sha",
        "git_blob_sha", "manifest_version", "source_kind", "source_locator",
    }, "SourcePin")
    if (
        obj["schema"] != PIN_SCHEMA or obj["provider"] != "github_public_contents"
        or obj["repository"] != REPO or obj["path"] != FILE_PATH
        or obj["source_locator"] != FIELDDECK_LOCATOR
        or obj["manifest_version"] != "0.7.0"
        or obj["source_kind"] != FIELDDECK_V07
    ):
        raise ContractError("SourcePin: unsupported source or version")
    for key in ("commit_sha", "git_blob_sha"):
        if type(obj[key]) is not str or not GITHUB_SHA.fullmatch(obj[key]):
            raise ContractError(f"SourcePin: invalid {key}")
    return obj


def strict_json(raw: bytes) -> Any:
    """Reject duplicate JSON keys, non-finite numbers, invalid UTF-8 and BOM."""
    if type(raw) is not bytes:
        raise ContractError("JSON: bytes required")

    def unique(pairs: list[tuple[str, Any]]) -> dict:
        record = {}
        for key, value in pairs:
            if key in record:
                raise ContractError("JSON: duplicate key")
            record[key] = value
        return record

    def nonfinite(value: str) -> None:
        raise ContractError("JSON: nonfinite number")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=nonfinite)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("JSON: malformed response") from exc


def load_reviewed_pin() -> dict[str, str]:
    """The only automatically selected production pin is checked into this repo."""
    try:
        return _pin(strict_json(PIN_FILE.read_bytes()))
    except (OSError, UnicodeError) as exc:
        raise ContractError("SourcePin: not readable") from exc


def git_blob_sha(raw: bytes) -> str:
    """Git SHA-1 blob ID (not a signature)."""
    prefix = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    return hashlib.sha1(prefix + raw).hexdigest()


class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ContractError("transport: redirect rejected")


def github_public_get(url: str) -> bytes:
    """One unauthenticated public HTTPS GET to an exact GitHub API file path."""
    if type(url) is not str or not url.startswith(API_PREFIX):
        raise ContractError("transport: URL outside pinned allowlist")
    if not GITHUB_SHA.fullmatch(url[len(API_PREFIX):]):
        raise ContractError("transport: unpinned commit")
    request = Request(
        url, method="GET", headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "FieldAccord-FA04-readonly",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    opener = build_opener(
        HTTPSHandler(context=ssl.create_default_context()), RejectRedirect(),
    )
    try:
        with opener.open(request, timeout=8) as response:
            if response.status != 200:
                raise ContractError("transport: non-200 response")
            ct = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ct not in ("application/json", "application/vnd.github+json"):
                raise ContractError("transport: non-JSON response")
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    n = int(length)
                except ValueError as exc:
                    raise ContractError("transport: invalid Content-Length") from exc
                if not 0 <= n <= RESPONSE_CAP:
                    raise ContractError("transport: oversized response")
            body = response.read(RESPONSE_CAP + 1)
            if len(body) > RESPONSE_CAP:
                raise ContractError("transport: oversized response")
            return body
    except (HTTPError, URLError, OSError) as exc:
        raise ContractError("transport: GitHub read failed") from exc


def acquire_fielddeck(
    *, transport: Callable[[str], bytes] | None = None,
    pin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Acquire an exact blob and return a redacted read-only projection.

    Injection of transport/pin is for offline testing and integrator review.
    A supplied pin is only as trustworthy as the caller's own pin custody.
    The CLI does not expose these injection parameters.
    """
    active = _pin(load_reviewed_pin() if pin is None else pin)
    url = API_PREFIX + active["commit_sha"]
    source_bytes = github_public_get(url) if transport is None else transport(url)
    if type(source_bytes) is not bytes or len(source_bytes) > RESPONSE_CAP:
        raise ContractError("GitHub: invalid or oversized response bytes")
    obj = _record(strict_json(source_bytes), {
        "type", "name", "path", "sha", "size", "encoding", "content",
        "url", "html_url", "git_url", "download_url", "_links",
    }, "GitHubContents")
    if (
        obj["type"] != "file" or obj["name"] != "fielddeck.manifest.json"
        or obj["path"] != FILE_PATH or obj["encoding"] != "base64"
        or obj["sha"] != active["git_blob_sha"]
    ):
        raise ContractError("GitHub: resource identity or pin mismatch")
    content = obj["content"]
    if type(content) is not str or len(content) > MAX_BYTES * 2:
        raise ContractError("GitHub: missing or excessive base64 content")
    try:
        raw = base64.b64decode("".join(content.split()), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ContractError("GitHub: malformed base64") from exc
    if type(obj["size"]) is not int or len(raw) != obj["size"] or len(raw) > MAX_BYTES:
        raise ContractError("GitHub: source size mismatch")
    if git_blob_sha(raw) != active["git_blob_sha"]:
        raise ContractError("GitHub: recomputed blob SHA mismatch")
    payload = strict_json(raw)
    projection, claimed = _fielddeck(payload, FIELDDECK_V07)
    if claimed:
        raise ContractError("GitHub: unexpected authority claim")
    return {
        "schema": READ_SCHEMA,
        "provider": active["provider"],
        "repository": REPO,
        "commit_sha": active["commit_sha"],
        "git_blob_sha": active["git_blob_sha"],
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "payload_sha256": digest(payload),
        "pin_sha256": digest(active),
        "source_kind": FIELDDECK_V07,
        "source_locator": FIELDDECK_LOCATOR,
        "raw_size": len(raw),
        "projection": projection,
        "payload": payload,
        "network_read_only": True,
        "source_authorship_authenticated": False,
        "authority_granted": False,
        "action_executed": False,
    }


def inspect_acquired_fielddeck(
    intent: Any, events: Any, *, expected_state_head: str,
    capture_id: str, transport: Callable[[str], bytes] | None = None,
    pin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pass an acquired source through FA-03's unchanged intent-bound gate."""
    read = acquire_fielddeck(transport=transport, pin=pin)
    snapshot = {
        "schema": "fa.source_snapshot.v0.1",
        "capture_id": capture_id, "work_id": intent.get("work_id"),
        "source_kind": read["source_kind"],
        "source_locator": read["source_locator"],
        "payload_sha256": read["payload_sha256"],
        "payload": read["payload"],
    }
    reviewed = inspect_snapshot(
        intent, events, snapshot, expected_state_head=expected_state_head,
        expected_payload_sha256=read["payload_sha256"],
    )
    return {
        "schema": "fa.pinned_bridge_result.v0.1",
        "source_pin_sha256": read["pin_sha256"],
        "source_commit_sha": read["commit_sha"],
        "source_git_blob_sha": read["git_blob_sha"],
        "source_raw_sha256": read["raw_sha256"],
        "bridge_receipt": reviewed,
        "authority_granted": False,
        "action_executed": False,
        "notification_dispatched": False,
    }


def public_summary(read: dict[str, Any]) -> dict[str, Any]:
    """Export only bounded discovery metadata, never raw source content."""
    return {
        "schema": read["schema"], "repository": read["repository"],
        "commit_sha": read["commit_sha"], "git_blob_sha": read["git_blob_sha"],
        "raw_sha256": read["raw_sha256"], "payload_sha256": read["payload_sha256"],
        "pin_sha256": read["pin_sha256"], "source_kind": read["source_kind"],
        "projection": read["projection"],
        "source_authorship_authenticated": False,
        "authority_granted": False, "action_executed": False,
    }
