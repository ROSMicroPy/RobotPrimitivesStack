# ADR 0005: Use Graph-First Morphology-Agnostic Modeling

- Status: Accepted
- Date: 2026-05-06

## Context

The protocol must support bipeds, wheeled humanoids, quadrupeds, snake robots, and hybrids.

An anatomy-first model built around concepts like shoulder, elbow, or arm would not generalize.

## Decision

Model composition as a graph of mounted parts.

The protocol core remains morphology-agnostic:

- parts expose traits and explicit DOFs
- locations identify topology slots
- trackers assemble the graph

Robot-family semantics such as humanoid or snake roles are layered on top of the composed graph, not embedded in the core protocol.

## Consequences

Benefits:

- One protocol shape works across many robot architectures.
- Repeated modules, such as snake segments, fit naturally.
- Humanoid-specific assumptions do not leak into the wire model.

Costs:

- Higher-level robot semantics move out of the base protocol.
- Trackers and planners must provide family-specific interpretation.
