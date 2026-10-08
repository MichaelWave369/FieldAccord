# Field Accord

**A human–silicon collaboration protocol.**

> Technology should carry the complexity, not the human.  
> Capability does not confer authority.

Field Accord is a **coordination contract**, not a new all-powerful agent. It aims to let people and independent software agents share goals, context, attention policies, work state, and verifiable outcomes without accidentally sharing permissions.

## Purpose

A person should be able to state an objective once, inspect how agents interpreted it, and remain in control of consequential actions. Model changes, disconnected devices, and worker failures must not silently rewrite that objective.

## Architectural boundaries

| Concern | Existing ecosystem home |
| --- | --- |
| Cognition and WorkObjects | [SuperPhiVessel](https://github.com/MichaelWave369/SuperPhiVessel) |
| Execution authority and verification | [PhiOS](https://github.com/MichaelWave369/PhiOS) |
| Cognitive resource routing | [BudgetGenius](https://github.com/MichaelWave369/BudgetGenius) |
| Temporal and evidence-linked memory | [NestedBubbleGear](https://github.com/MichaelWave369/NestedBubbleGear) |
| Human–agent presence and attention | [Commonline](https://github.com/MichaelWave369/Commonline) |
| Human-reviewed workflow actions | [FieldDeck](https://github.com/MichaelWave369/FieldDeck) |

The first rung is deliberately **offline and non-executing**: versioned contracts, a deterministic review-only policy engine, local evidence receipts, and rejection tests. No external tools, local scripts, secrets, network operations, or approvals are issued by this library.

## Core laws

1. **GOAL ≠ GRANT.** A request describes a desired outcome, not permission to execute.
2. **CAPABILITY ≠ AUTHORITY.** Declaring a tool never grants permission to use it.
3. **OBSERVATION ≠ INFERENCE.** Evidence keeps its epistemic type and origin.
4. **MEMORY ≠ AUTHORIZATION.** Retrieved context is never an action grant.
5. **ATTENTION ≠ PERMISSION.** Permission to notify is separate from permission to act.
6. **PROPOSAL ≠ EXECUTION.** A reviewable candidate is not a completed action.
7. **HASH ≠ TRUST.** A digest detects change only against a separately trusted anchor.

## Initial deliverable

**FA-01**: WorkIntent, CapabilityDeclaration, ActionProposal, PolicyDecision, and WorkReceipt, with a small offline demonstration and contract tests. Work is proposed on branches and reviewed before merging.

## Future rungs

- **FA-02:** adapters to the existing projects, preserving each system's authority boundary.
- **FA-03:** one end-to-end GitHub CI diagnosis, with human approval for external effects.
- **FA-04:** adversarial tests for restarts, replay, expired permissions, stale memory, model swaps, and partial failures.

## Project state

Experimental. Design contracts and software must be validated before connecting to real execution surfaces.

**Enter the Field. Carbon and silicon, building together.**
