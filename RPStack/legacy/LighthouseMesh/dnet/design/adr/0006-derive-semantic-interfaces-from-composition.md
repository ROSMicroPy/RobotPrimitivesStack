# ADR 0006: Derive Semantic Interfaces From Composition

- Status: Accepted
- Date: 2026-05-06

## Context

A joint's supported control interface depends on intrinsic mechanics and mounted role.
For example, a single-DOF servo cannot support commands that require an unsupported rotational axis.

Advertising high-level semantic interfaces directly from each node risks overclaiming capability before the full robot composition is known.

## Decision

Nodes publish raw mechanics and raw control modes.

Examples:

- DOFs such as `pitch`, `yaw`, or `roll`
- low-level control modes such as `position`, `velocity`, `stop`

Semantic robot-level interfaces are derived by trackers or higher-level planners after the robot graph is assembled.

## Consequences

Benefits:

- Interface compatibility follows actual mechanics.
- Robot-level meaning can vary by morphology and composition.
- Nodes remain simpler and less coupled to the whole robot plan.

Costs:

- Some semantic convenience shifts to the composition layer.
- Higher-level systems must map raw mechanics into task-oriented interfaces.
