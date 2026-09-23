# Candidate Node Mapping, Assignment, and Selection

This document explains how candidate node mapping works in `dnet/code/messaging/capabilities.py`, with emphasis on the `CapabilityMatcher.reconcile()` flow.

The matcher is intentionally simple:

- flatten the composite unit into a list of candidate component nodes
- score each node against each requested role
- assign the best unused node to each required role
- evaluate behaviors from the resulting assignment
- choose the highest-priority compatible personality profile

## Core Flow

`CapabilityMatcher.reconcile(composite_unit)` runs in five stages:

1. Flatten the unit into a linear list of `ComponentNode` objects.
2. Build a candidate map for every required role.
3. Assign the best unused candidate to each required role.
4. Evaluate optional roles without reserving nodes.
5. Derive behaviors and select the final profile.

The matcher returns a JSON-friendly structure with:

- `match_score`
- `role_assignment`
- `matched_roles`
- `partial_matches`
- `missing_roles`
- `optional_roles`
- `enabled_behaviors`
- `partial_behaviors`
- `disabled_behaviors`
- `selected_profile`
- `diagnostics`
- `candidate_map`

## Stage 1: Candidate Mapping

Candidate mapping is handled by `_map_candidates(role_req, nodes)`.

For each required role definition:

- every node in the flattened unit is checked
- `_score_role(role_req, node)` decides whether the node is usable
- only nodes with score greater than `0` become candidates
- candidates are sorted by score descending

Each candidate entry contains:

- `node`: the original `ComponentNode`
- `score`: an integer score
- `reason`: a short explanation string

### What counts as a valid candidate

A node is rejected immediately if any hard failure is found:

- the requested semantic role is not in `node.provided_roles`
- `node.calibration_state` is not one of `ready`, `calibrated`, `ok`, or `unknown`
- required DOF is higher than the best joint DOF on the node
- a required sensor type is missing
- required control interfaces are missing and the node does not expose either `velocity` or `torque`

If any of those conditions fail, the score is `0` and the node is excluded from the candidate list.

### Scoring model

The implementation uses integer scores:

- exact match: `100`
- partial match: `60`
- low-confidence fallback: `25`

The final serialized `candidate_map` divides by `100.0`, so user-facing scores appear as `1.0`, `0.6`, or `0.25`.

### How a node becomes partial instead of exact

A valid node can still be downgraded from exact to partial when:

- the node has more DOF than required
- some requested interfaces are missing, but the node still has `velocity` or `torque`
- node confidence is below `80`

A valid node is downgraded further to low-confidence when:

- node confidence is below `50`

The `reason` field records why the downgrade happened, such as:

- `extra dof`
- `missing interfaces: position`
- `reduced confidence`
- `low confidence`

If no downgrade applies, the reason is `exact`.

## Stage 2: Required Role Assignment

Required role assignment is handled directly inside `reconcile()` and uses `_select_candidate(candidates, used_nodes)`.

For each required role:

- look up the precomputed candidate list
- take the first candidate whose `node_id` is not already used
- reserve that node in `used_nodes`
- record the assignment in `role_assignment`

If no unused candidate exists:

- the role is assigned `None`
- the role is added to `missing_roles`
- a diagnostic like `elbow missing` is added

If a candidate is selected:

- `role_assignment[role_name]` is set to the selected `node_id`
- the node is marked used so it cannot satisfy another required role
- the role is recorded as either matched or partial based on score

### Why `used_nodes` matters

This prevents one component from satisfying multiple required roles unless the code is changed to allow it.

Example:

- if one node advertises both `shoulder` and `elbow`
- and it gets selected first for `shoulder`
- it will not be reused for the required `elbow` assignment

That behavior makes assignments deterministic and avoids over-claiming a shared component.

### Tie handling

There is no custom tie-breaker beyond sort order and traversal order.

In practice:

- candidates are sorted by score descending
- candidates with equal scores keep Python's stable sort order
- that stable order comes from the original flattened node order

So ties are resolved by whichever node appeared earlier in the composite structure.

## Stage 3: Optional Role Evaluation

Optional roles are evaluated after required-role assignment, but they do not consume nodes.

For each optional role:

- the matcher computes a fresh candidate list
- `_select_candidate(..., {})` is called with an empty `used_nodes` map
- the result is recorded as `matched` or `missing`

This means optional-role matching is independent of required-role reservations.

A node can therefore:

- be assigned to a required role
- also cause an optional role to report as `matched`

That is the current implementation behavior.

## Stage 4: Behavior Derivation

Behavior derivation uses:

- required-role assignment state
- partial match state
- optional-role results

The matcher builds a role-state map where each role becomes:

- `matched`
- `partial`
- `missing`

Behavior rules are then evaluated by `_evaluate_behavior_rule()`.

Supported rule forms:

- `requires`: every listed role must be present
- `requires_any`: at least one role or one full option group must be present

Behavior outcomes:

- `enabled`: the rule is fully satisfied
- `partial`: some useful but incomplete support exists
- `disabled`: the rule is not satisfied

## Stage 5: Profile Selection

Profile selection is handled by `_select_profile()`.

The matcher first builds:

- a lookup of matched required roles
- a lookup of matched optional roles
- a lookup of enabled behaviors

Then each personality profile is checked by `_profile_matches()`.

A profile can require:

- specific roles via `requires_roles`
- at least one role via `requires_any_role`
- specific enabled behaviors via `required_behaviors`
- absence of behaviors via `excluded_behaviors`

All compatible profiles are ranked by `priority`, highest first.

If no profile matches, the fallback is:

- `disabled_limb`

## Example Walkthrough

The sample `example_partial_arm()` contains:

- one shoulder joint controller
- one upper-arm IMU
- one lower-arm IMU
- no elbow
- no gripper

With `example_requirements()`:

- `shoulder` maps to the shoulder joint and scores exact
- `elbow` has no candidate and becomes missing
- `gripper` has no candidate and becomes missing
- `upper_arm_orientation` matches the upper IMU
- `lower_arm_orientation` matches the lower IMU

That leads to:

- required assignment only for `shoulder`
- optional matches for both IMU-based orientation roles
- enabled behaviors like `gesture`
- disabled behaviors like `can_reach` and `can_pick`
- selected profile `gestural_arm`

## Current Limitations

The current matcher is deliberately lightweight, but there are some important limits:

- assignment is greedy, not globally optimal
- equal-score ties depend on input order
- optional roles do not reserve nodes
- `hard_constraints` and `soft_constraints` are stored in `RobotRequirements` but not yet used by the matcher
- partial matching is rule-based and coarse, not probabilistic

## Practical Summary

The selection logic is best thought of as:

- filter out impossible nodes
- score the remaining nodes with simple deterministic rules
- greedily assign the best unused node to each required role
- treat optional roles as additional capability checks
- derive behaviors and choose the highest-priority compatible profile

That makes the system predictable, explainable, and small enough for MicroPython-class devices.
