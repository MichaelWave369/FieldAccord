# Field Accord

**A human–silicon collaboration protocol.**

> Technology should carry the complexity, not the human.  
> Capability does not confer authority.

Field Accord is a **coordination contract**, not a new all-powerful agent. It lets humans and independent agents describe shared goals, inspect work continuity, and consider attention preferences without silently granting permissions.

## Current rungs

- **FA-01 (merged):** review-only WorkIntent, CapabilityDeclaration, ActionProposal, WorkReceipt and a deterministic no-authority assessment. See [FA-01](docs/FA-01.md).
- **FA-02 (merged):** append-only, intent-bound WorkEvent chain; deterministic WorkState replay; checkpoints for model handoffs; short-lived, revocable AttentionLease semantics; and read-only attention advice. See [FA-02](docs/FA-02.md).

- **FA-03 (merged):** source-pinned, offline, read-only FieldDeck v0.6 and NBG epistemic-memory snapshot adapters. No execution authority, no retrieval, and no memory prompt admission. See [FA-03](docs/FA-03.md).

- **FA-04 (merged):** an explicit opt-in **public HTTPS GET** for a code-reviewed exact FieldDeck v0.7 commit + Git blob, with strict size/JSON/base64/provenance checks and FA-03 WorkIntent replay compatibility. See [FA-04](docs/FA-04.md).

- **FA-05 (merged):** two grounded *offline* source export adapters: Vessie PV-DLAM context-packet v1 and PhiOS PhiVessel `BRIDGE_STATUS` v0.1. Both require WorkIntent pin + anchored replay and return redacted, no-authority review receipts. No live WorkObject integration. See [FA-05](docs/FA-05.md).

- **FA-06 (candidate):** local HMAC-sealed Vessie/PhiOS export handoffs with 10-minute freshness, persisted replay/nonce refusal, and a SQLite/WAL WorkEvent journal with optimistic-head conflict detection. See [FA-06](docs/FA-06.md).

FA-01 through FA-03 and FA-05/FA-06 remain offline. FA-04's `fetch-fielddeck` is a **read-only network operation** and never invokes action workflows or writes to GitHub. No external tools, scripts, credentials, messaging, identity verification, or physical controls are enabled by Field Accord.

## Test locally

Requires Python 3.12+. No third-party dependencies.

```sh
python -m unittest discover -s tests -v
python -m fieldaccord demo
python -m fieldaccord work-demo
python -m fieldaccord bridge-demo
python -m fieldaccord interop-demo
python -m fieldaccord handoff-demo
# Optional: makes one public read-only GitHub API request
python -m fieldaccord fetch-fielddeck
```

The `demo`, `work-demo`, `bridge-demo`, and `interop-demo`, and `handoff-demo` demonstrations use synthetic data and produce **no network activity**. A `REVIEW_CANDIDATE` is a suggestion for a human-governed UI, **not** a notification or permission.

## Architectural boundaries

| Concern | Existing ecosystem home |
| --- | --- |
| Cognition and WorkObjects | [SuperPhiVessel](https://github.com/MichaelWave369/SuperPhiVessel) |
| Execution authority and verification | [PhiOS](https://github.com/MichaelWave369/PhiOS) |
| Cognitive resource routing | [BudgetGenius](https://github.com/MichaelWave369/BudgetGenius) |
| Temporal and evidence-linked memory | [NestedBubbleGear](https://github.com/MichaelWave369/NestedBubbleGear) |
| Human–agent presence and attention | [Commonline](https://github.com/MichaelWave369/Commonline) |
| Human-reviewed workflow actions | [FieldDeck](https://github.com/MichaelWave369/FieldDeck) |

## Core laws

1. **GOAL ≠ GRANT.** A desired outcome is not permission to execute.
2. **CAPABILITY ≠ AUTHORITY.** Declaring a tool does not permit using it.
3. **OBSERVATION ≠ INFERENCE.** Evidence retains its origin and type.
4. **MEMORY ≠ AUTHORIZATION.** Recalled context never conveys an action grant.
5. **ATTENTION ≠ PERMISSION.** A request to surface information is not permission to contact anyone.
6. **PROPOSAL ≠ EXECUTION.** A candidate repair is not a completed action.
7. **HASH ≠ TRUST.** A digest is not an identity or provenance signature.

## Planned rungs

- **FA-07:** authenticated producer-side connectors in Vessie/PhiOS, externally anchored journal heads, cross-device replay and consent/revocation qualification.
- **FA-08:** independently authorized execution handoff with explicit operator grant and action-time revalidation.

## Project state

Experimental. FA-02's event chain is **not** a trusted distributed event bus, a durable storage engine, or an authenticated notification grant. FA-03's expected digests and projections likewise are **not** source authentication or a tool execution path. FA-04 pins a published public GitHub blob, not a human identity, trusted timeline, operator consent, or a live automation authorization. Replacing a pin must go through human code review. FA-05 is metadata inspection only: it does not authenticate upstream identity or admit context into a model. FA-06's shared-key authentication only proves key possession and SQLite replay protection only covers one local database, not global identity, consent, or an immutable ledger. Prove remaining boundaries before wiring any execution.

**Enter the Field. Carbon and silicon, building together.**
