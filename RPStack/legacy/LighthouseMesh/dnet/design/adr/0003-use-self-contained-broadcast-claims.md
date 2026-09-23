# ADR 0003: Use Self-Contained Broadcast Claims

- Status: Accepted
- Date: 2026-05-06

## Context

Composition trackers must not be fixed devices. Multiple trackers may observe the same system for redundancy or reduced latency.

That rules out a required node-to-server registration handshake.

## Decision

Nodes broadcast self-contained composition facts that any tracker can consume.

The core message family is:

- `a`: announce
- `c`: composition claim
- `u`: composition update
- `x`: withdraw
- `r`: optional tracker report
- `e`: transient runtime event

Correctness does not depend on hearing from any specific tracker.

## Consequences

Benefits:

- Many trackers can compute composition independently.
- Node behavior does not depend on a single authority.
- Broadcast meshes fit the protocol naturally.
- Runtime observers can respond to events without disturbing composition tracking.

Costs:

- Conflict handling and convergence rules must be explicit.
- Trackers must tolerate duplicate and reordered messages.
