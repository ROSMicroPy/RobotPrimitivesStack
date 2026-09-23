# MicroPython Codex Prompt

```text
You are a senior robotics software engineer working inside the LighthouseMesh project.

Implement or extend a MicroPython-friendly capability reconciliation system for modular robot components discovered over LighthouseMesh.

Project constraints:
- Target runtime includes MicroPython on ESP32-class devices.
- Keep memory usage low.
- Avoid heavy dependencies such as dataclasses, pydantic, or large rule engines.
- Prefer plain classes, dictionaries, and lists.
- Keep recurring mesh traffic small.
- Use the existing DistNet messaging package under `dnet/code/messaging`.
- Short advertisements must stay compact and continue to use service ids.
- Rich capability metadata should travel in long-form profile messages, typically inside `PROFILE.meta`.

Architecture to preserve:
- physical traits -> semantic roles -> derived behaviors -> personality/profile

Implementation goals:
1. Represent individual mesh nodes and composite units such as an arm.
2. Allow a composite unit to aggregate child nodes into one capability advertisement.
3. Match provided roles against robot required/optional roles.
4. Produce enabled, partial, and disabled behaviors.
5. Select the best personality profile for degraded operation.
6. Keep the code practical for both MicroPython and host-side CPython testing.

Existing package context:
- `dnet/code/messaging/schema.py` defines compact message field names.
- `dnet/code/messaging/codec.py` encodes/decodes short and long profile messages.
- `dnet/code/messaging/registry.py` stores advertisements and profiles.
- `dnet/code/messaging/protocol.py` exposes `MessagingEndpoint`.

Use or extend these concepts:

ComponentNode:
- id
- type
- mount_point
- parent_mount
- child_mounts
- provided_traits
- provided_roles
- control_interfaces
- sensors
- joints
- subcomponents
- diagnostics
- calibration_state
- confidence

CompositeUnit:
- unit_id
- mount_point
- subunits
- aggregated traits
- aggregated roles
- derived capabilities
- short advertisement
- long advertisement

RobotRequirements:
- required_roles
- optional_roles
- behavior_definitions
- personality_profiles

Required algorithm:

Phase 1: Candidate Mapping
- For each required role, find matching component candidates
- Compute a score from 0.0 to 1.0
- Support partial matching
- Example partials:
  - velocity-only actuator partially matches a position-controlled joint
  - low-confidence or uncalibrated sensor degrades the score

Phase 2: Assignment
- Choose the best unused candidate for each required role
- Reject hard failures such as:
  - wrong semantic role
  - insufficient DOF
  - missing required interface
  - invalid calibration state

Phase 3: Behavior Derivation
- Evaluate behavior rules from matched roles
- Return:
  - enabled behaviors
  - partial behaviors
  - disabled behaviors

Profile Selection:
- Evaluate personality profiles like:
  - full_manipulator
  - gestural_arm
  - sensor_only
  - disabled_limb
- Select the highest-priority compatible profile

Output shape:
{
  "match_score": 0.66,
  "role_assignment": {
    "shoulder": "shoulder_joint",
    "elbow": null
  },
  "matched_roles": ["shoulder"],
  "partial_matches": [],
  "missing_roles": ["elbow", "gripper"],
  "optional_roles": {
    "upper_arm_orientation": "matched",
    "lower_arm_orientation": "matched"
  },
  "enabled_behaviors": ["gesture", "pose_estimation_partial"],
  "partial_behaviors": [],
  "disabled_behaviors": ["can_pick", "can_reach"],
  "selected_profile": "gestural_arm",
  "diagnostics": [
    "shoulder matched by shoulder_joint",
    "elbow missing",
    "gripper missing"
  ]
}

Implementation requirements:
- Put the core logic in `dnet/code/messaging/capabilities.py`
- Export public classes in `dnet/code/messaging/__init__.py`
- Reuse the existing profile message path instead of inventing a separate transport
- Keep comments short and high-value
- Include a small runnable demo file that shows a degraded arm with shoulder + IMUs but no elbow/gripper

Design preference:
- Make the implementation deterministic and explainable before making it clever
- Optimize for constrained embedded systems first, then host-side convenience second
```
