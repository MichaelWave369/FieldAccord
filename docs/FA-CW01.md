# FA-CW01: Offline cloud observation admission

FieldAccord consumes supplied evidence from FieldCloudWorker through a strict, review-only adapter. The new module performs no network requests or filesystem writes, and it cannot invoke another agent or grant authority.

Inputs are: bounded original status.json and history.jsonl bytes; GitHub Actions run metadata supplied by the caller; a previously anchored expected status SHA-256; an intent with discovery.read, a source reference with unverified epistemic status, and an independently anchored WorkEvent head; plus an aware current clock.

The adapter accepts only three reviewed task identities. It refuses unexpected data, duplicate JSON keys, source hash drift, stale source claims, unknown run identities, changed branch/commit/workflow, contradictory run outcomes and modified history.

Outputs are a redacted, hashed review receipt with one of three dispositions: REVIEW_ONLY_OBSERVATION, TASK_FAILURE_OBSERVED, or STALE_OBSERVATION. None gives any permission. All authority, notification, execution, network, history modification and memory-admission flags remain false.

GitHub run metadata correlation does not prove the task output true, the author trusted, or a human approval. Caller-owned pins are useful only when established independently, before reading untrusted data. Integrating a live transport, Vessie, NBG, or PhiOS requires a separate reviewed step.

Acceptance command: python -m unittest discover -s tests -v

CAPABILITY DOES NOT CONFER AUTHORITY.
