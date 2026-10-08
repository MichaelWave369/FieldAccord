# Field Accord

**A human–silicon collaboration protocol.**

> Technology should carry the complexity, not the human.  
> Capability does not confer authority.

Field Accord is a **coordination contract**, not a new all-powerful agent. It lets humans and independent agents describe shared goals, inspect work continuity, and consider attention preferences without silently granting permissions.

## Current rungs

- **FA-01 (merged):** review-only WorkIntent, CapabilityDeclaration, ActionProposal, WorkReceipt and a deterministic no-authority assessment. See [FA-01](docs/FA-01.md).
- **FA-02 (candidate):** append-only, intent-bound WorkEvent chain; deterministic WorkState replay; checkpoints for model handoffs; short-lived, revocable AttentionLease semantics; and read-only attention advice. See [FA-02](docs/FA-02.md).

Both rungs are **offline and non-executing**. No external tools, scripts, credentials, messaging, identity verification, or physical controls are enabled by Field Accord.

## Test locally

Requires Python 3.12+. No third-party dependencies.

```sh
python -m unittest discover -s tests -v
python -m fieldaccord demo
python -m fieldaccord work-demo
```

Both demonstrations use synthetic data and produce **no network activity**. A `REVIEW_CANDIDATE` is a suggestion for a human-governed UI, **not** a notification or permission.

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

- **FA-03:** bounded adapters to PhiOS, SuperPhiVessel, NBG and FieldDeck, with independent authorization before effects.
- **FA-04:** end-to-end GitHub CI diagnostic, with provenance, revocation, restart, and fault-injection tests.

## Project state

Experimental. FA-02's event chain is **not** a trusted distributed event bus, a durable storage engine, or an authenticated notification grant. Prove those boundaries before wiring it to live systems.

**Enter the Field. Carbon and silicon, building together.**
