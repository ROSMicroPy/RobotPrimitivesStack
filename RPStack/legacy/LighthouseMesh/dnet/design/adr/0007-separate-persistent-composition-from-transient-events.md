# ADR 0007: Separate Persistent Composition From Transient Events

- Status: Accepted
- Date: 2026-05-07

## Context

The same network stack must support two different classes of information:

- persistent robot facts such as mounted parts and their state
- transient runtime observations such as `vision.person_detected`

These have different lifecycles and consumers. Composition trackers need deterministic convergence on persistent facts, while event listeners only need best-effort delivery and may ignore irrelevant events.

## Decision

Keep both concerns in the same messaging package, but model them as separate message types.

- Composition uses `a`, `c`, `u`, `x`, and `r`
- Runtime events use `e`

Event messages carry:

- event name
- parameters
- optional priority
- optional event TTL

The endpoint may dispatch received events to local listeners, and the registry may cache them briefly for inspection.

## Consequences

Benefits:

- Composition convergence rules stay clean.
- Event traffic can be consumed opportunistically by interested nodes.
- Nodes can coordinate on observations without turning those observations into persistent robot facts.

Costs:

- The messaging package now has two traffic classes to document and validate.
- Consumers must choose whether they are acting as composition trackers, event listeners, or both.
