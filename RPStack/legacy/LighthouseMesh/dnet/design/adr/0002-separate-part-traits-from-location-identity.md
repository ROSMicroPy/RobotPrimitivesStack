# ADR 0002: Separate Part Traits From Location Identity

- Status: Accepted
- Date: 2026-05-06

## Context

The design discussion identified three distinct concerns:

- intrinsic hardware traits
- mounted topology identity
- runtime state

Collapsing these into one object makes later identity upgrades harder and mixes mechanics with installation context.

## Decision

Model them separately:

- `part`: intrinsic mechanical or module traits
- `loc`: mounted topology identity
- `state`: runtime condition

The current node may synthesize location identity locally, but the protocol keeps that concern logically separate so a future QR, NFC, or other identity mechanism can replace only the location acquisition path.

## Consequences

Benefits:

- Hardware traits remain reusable across mounts.
- Location evidence can evolve independently.
- Trackers can validate compatibility between part and location.

Costs:

- Registration payloads become more structured.
- Some convenience shortcuts in the old model are removed.
