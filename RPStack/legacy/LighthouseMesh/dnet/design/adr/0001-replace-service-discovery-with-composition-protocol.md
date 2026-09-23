# ADR 0001: Replace Service Discovery With A Composition Protocol

- Status: Accepted
- Date: 2026-05-06

## Context

The original messaging design centered on compact service discovery. Nodes advertised service identifiers and richer metadata lived behind a profile fetch step.

That model is a weak fit for modular robot assembly because the primary problem is not "which service provider exists" but "what physical part is this node, where is it mounted, and how does it contribute to robot composition."

## Decision

Replace the service-first registration model with a messaging protocol centered on:

- composition claims for persistent robot facts
- transient events for cross-node runtime coordination

Nodes will broadcast:

- part identity and traits
- mounted location identity
- current runtime state
- freshness metadata
- event observations and triggers when needed

## Consequences

Benefits:

- The protocol matches the robot assembly problem directly while still supporting runtime coordination.
- Physical structure becomes first-class instead of hidden in metadata.
- The model can support heterogeneous morphologies.

Costs:

- Messages become richer and less generic.
- Trackers must perform topology and conflict reasoning instead of simple service indexing.
- Existing code under `src/messaging` becomes legacy until migrated.
