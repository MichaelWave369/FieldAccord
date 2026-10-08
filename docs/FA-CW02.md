# FA-CW02: Explicit live public read of FieldCloudWorker

**This is discovery, not trusted admission.** The new command makes four bounded, unauthenticated read-only GitHub API requests when explicitly invoked:

1. Read the current `main` commit SHA of FieldCloudWorker.
2. Read `docs/status.json` at that exact commit.
3. Read `docs/history.jsonl` at that same exact commit.
4. Read the public GitHub Actions run associated with the receipt.

For both files, verify content path, type, byte count, base64 decoding and recalculated Git blob SHA. Verify the frozen FA-CW01 task schema and sanitized history. Correlate run identity, path, event, branch, SHA prefix, timestamps and conclusion. Disallow redirects, credentials, arbitrary URLs, non-JSON data and oversized responses.

The source is a **snapshot of moving main**, not a code-reviewed independently established pin. A public summary returns `independent_prior_pin_verified=false` even when the run metadata correlates and the Git blob digests match. Hashes bind bytes but do not establish who published them or whether measurements are true.

The API function returns in-memory raw bytes to a caller that needs to separately bind the evidence to a **pre-existing** WorkIntent and WorkEvent anchor through FA-CW01. Do not build WorkIntent pins from newly retrieved untrusted data and then call the result independently verified. The CLI prints only a redacted, no-authority summary and writes nothing.

Run manually:

```sh
python -m fieldaccord fetch-cloud-worker
```

No scheduled polling, background service, workflow dispatches, commits, tokens, model prompts, memory admission, notifications or action grants are added. CI uses only injected offline transport fixtures and negative controls. Live availability still requires a manual check after merge.

**CAPABILITY ≠ AUTHORITY. API METADATA ≠ A SIGNED ATTESTATION.**
