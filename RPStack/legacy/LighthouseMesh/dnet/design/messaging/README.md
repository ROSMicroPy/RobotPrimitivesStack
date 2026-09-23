# Messaging And Composition Design

This folder documents the messaging protocol direction for `dnet`.

## Documents

- `SCHEMA.md`
  - Replacement protocol for composition-oriented node claims.
- `../adr/`
  - Architecture decisions that explain why the protocol is structured this way.

## Design Status

The current code in `src/messaging` implements the replacement design:

- a composition channel for persistent robot facts
- an event channel for transient runtime observations and triggers

## Core Shift

The legacy protocol is service-first:

- discover nodes by service ID
- fetch richer profiles on demand

The replacement protocol is split into two layers:

- composition messages describe what physical part a node represents, where it is mounted, and what state it is in
- event messages carry transient observations such as `vision.person_detected`
- any tracker can observe composition claims and converge on the same composition graph
- any listener can receive events and decide to act on them or ignore them
