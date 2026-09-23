# ADR 0004: Use Lease-Based Claims With Deterministic Ordering

- Status: Accepted
- Date: 2026-05-06

## Context

With multiple trackers and broadcast delivery, nodes need a way to express freshness and trackers need a way to converge on the same current view.

## Decision

Each claim message includes:

- `n`: node id
- `b`: boot id
- `q`: monotonic sequence
- `ts`: node-local timestamp
- `ttl`: claim freshness window
- `cid`: claim id

Trackers apply these rules:

- new boot ids invalidate older claims from the same node
- higher sequence numbers supersede lower ones within the same boot
- claims expire when their lease is not refreshed
- duplicate messages are handled idempotently

## Consequences

Benefits:

- Independent trackers can converge on the same active claim set.
- Node restarts and stale claims are handled cleanly.
- The protocol supports intermittent links without a strict session.

Costs:

- Nodes must manage boot ids and monotonically increasing sequence counters.
- Trackers must implement lease expiration logic.
