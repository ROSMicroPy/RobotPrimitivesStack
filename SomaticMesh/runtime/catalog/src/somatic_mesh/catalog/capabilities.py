"""
MicroPython-friendly capability reconciliation for modular robot components.

These physical composition models build optional public composition metadata.
They are separate from the catalog signal protocol and runtime service binding.
Matching uses dictionaries and lists to avoid heavyweight dependencies.
"""

try:
    import ujson as json
except Exception:
    import json

from .schema import Schema


ROLE_SCORE_EXACT = 100
ROLE_SCORE_PARTIAL = 60
ROLE_SCORE_LOW = 25


def _copy_dict(value):
    """Recursively copy nested dictionaries without importing `copy`."""
    if not isinstance(value, dict):
        return value
    copied = {}
    for key in value:
        copied[key] = _copy_dict(value[key])
    return copied


def _copy_list(items):
    """Recursively copy nested lists used in capability payloads."""
    copied = []
    for item in items:
        if isinstance(item, dict):
            copied.append(_copy_dict(item))
        elif isinstance(item, list):
            copied.append(_copy_list(item))
        else:
            copied.append(item)
    return copied


def _stable_text_hash(text):
    """Return a small deterministic hash suitable for constrained runtimes."""
    # FNV-1a keeps the implementation small enough for MicroPython targets.
    value = 2166136261
    for ch in text:
        value ^= ord(ch)
        value = (value * 16777619) & 0xFFFFFFFF
    return "%08x" % value


class PhysicalComponent:
    """Describe a single hardware or sensing component in a composite unit."""

    # Describe one physical component's mounts, capabilities, subcomponents, and diagnostic
    # confidence.
    def __init__(
        self,
        node_id,
        node_type,
        mount_point=None,
        parent_mount=None,
        child_mounts=None,
        provided_traits=None,
        provided_roles=None,
        control_interfaces=None,
        sensors=None,
        joints=None,
        subcomponents=None,
        diagnostics=None,
        calibration_state="unknown",
        confidence=100,
    ):
        self.node_id = str(node_id)
        self.node_type = str(node_type)
        self.mount_point = mount_point
        self.parent_mount = parent_mount
        self.child_mounts = list(child_mounts or [])
        self.provided_traits = _copy_dict(provided_traits or {})
        self.provided_roles = list(provided_roles or [])
        self.control_interfaces = list(control_interfaces or [])
        self.sensors = _copy_list(sensors or [])
        self.joints = _copy_list(joints or [])
        self.subcomponents = list(subcomponents or [])
        self.diagnostics = list(diagnostics or [])
        self.calibration_state = calibration_state
        self.confidence = int(confidence)

    def to_dict(self):
        """Serialize the component into JSON-friendly primitives."""
        return {
            "id": self.node_id,
            "type": self.node_type,
            "mount_point": self.mount_point,
            "parent_mount": self.parent_mount,
            "child_mounts": list(self.child_mounts),
            "provided_traits": _copy_dict(self.provided_traits),
            "provided_roles": list(self.provided_roles),
            "control_interfaces": list(self.control_interfaces),
            "sensors": _copy_list(self.sensors),
            "joints": _copy_list(self.joints),
            "subcomponents": [child.to_dict() for child in self.subcomponents],
            "diagnostics": list(self.diagnostics),
            "calibration_state": self.calibration_state,
            "confidence": self.confidence,
        }

    def flatten(self):
        """Return this node and all nested subcomponents as a flat list."""
        nodes = [self]
        for child in self.subcomponents:
            child_nodes = child.flatten()
            for item in child_nodes:
                nodes.append(item)
        return nodes


class CompositeUnit:
    """Group a set of component nodes into one advertised assembly."""

    # Group subunits under a shared identity and mounting point.
    def __init__(self, unit_id, mount_point=None, subunits=None):
        self.unit_id = str(unit_id)
        self.mount_point = mount_point
        self.subunits = list(subunits or [])

    def flatten_nodes(self):
        """Return every component node in every subunit as a flat list."""
        nodes = []
        for unit in self.subunits:
            child_nodes = unit.flatten()
            for item in child_nodes:
                nodes.append(item)
        return nodes

    def aggregated_roles(self):
        """Collect unique semantic roles provided by the unit."""
        roles = []
        seen = {}
        for node in self.flatten_nodes():
            for role in node.provided_roles:
                if role not in seen:
                    seen[role] = True
                    roles.append(role)
        return roles

    def aggregated_traits(self):
        """Collect merged joints, sensors, and control interfaces."""
        traits = {
            "joints": [],
            "sensors": [],
            "control_interfaces": [],
        }
        interface_seen = {}
        for node in self.flatten_nodes():
            for joint in node.joints:
                traits["joints"].append(_copy_dict(joint))
            for sensor in node.sensors:
                traits["sensors"].append(_copy_dict(sensor))
            for control in node.control_interfaces:
                if control not in interface_seen:
                    interface_seen[control] = True
                    traits["control_interfaces"].append(control)
        return traits

    def derive_capabilities(self):
        """Infer higher-level capabilities from the aggregated role set."""
        roles = self.aggregated_roles()
        role_lookup = {}
        for role in roles:
            role_lookup[role] = True

        capabilities = []
        if role_lookup.get("shoulder") and role_lookup.get("elbow"):
            capabilities.append("can_reach")
        if role_lookup.get("shoulder") and role_lookup.get("elbow") and role_lookup.get("gripper"):
            capabilities.append("can_pick")
        if role_lookup.get("upper_arm_orientation") or role_lookup.get("lower_arm_orientation"):
            capabilities.append("can_estimate_pose")
        return capabilities

    def composition_summary(self):
        """Build a compact composition summary for local reasoning."""
        return {
            "unit": self.unit_id,
            "mount": self.mount_point,
            "roles": self.aggregated_roles(),
            "caps": self.derive_capabilities(),
        }

    def composition_snapshot(self):
        """Build a richer topology snapshot for local composition reasoning."""
        payload = {
            "unit_id": self.unit_id,
            "mount_point": self.mount_point,
            "subunits": [unit.to_dict() for unit in self.subunits],
            "aggregated_traits": self.aggregated_traits(),
            "aggregated_roles": self.aggregated_roles(),
            "derived_capabilities": self.derive_capabilities(),
            "summary": self.composition_summary(),
        }
        payload["snapshot_hash"] = self.snapshot_hash(payload)
        return payload

    def snapshot_hash(self, payload=None):
        """Hash the current unit snapshot for cheap change detection."""
        if payload is None:
            payload = {
                "unit_id": self.unit_id,
                "mount_point": self.mount_point,
                "subunits": [unit.to_dict() for unit in self.subunits],
                "aggregated_traits": self.aggregated_traits(),
                "aggregated_roles": self.aggregated_roles(),
                "derived_capabilities": self.derive_capabilities(),
                "summary": self.composition_summary(),
            }
        encoded = json.dumps(payload, separators=(",", ":"))
        return _stable_text_hash(encoded)


class RobotRequirements:
    """Define the desired roles, behaviors, and profiles for a robot."""

    # Collect the roles, behaviors, and constraints used to assess a robot's composition.
    def __init__(
        self,
        required_roles=None,
        optional_roles=None,
        behavior_definitions=None,
        personality_profiles=None,
        hard_constraints=None,
        soft_constraints=None,
    ):
        self.required_roles = list(required_roles or [])
        self.optional_roles = list(optional_roles or [])
        self.behavior_definitions = dict(behavior_definitions or {})
        self.personality_profiles = list(personality_profiles or [])
        self.hard_constraints = dict(hard_constraints or {})
        self.soft_constraints = dict(soft_constraints or {})


class CapabilityMatcher:
    """Match a composite unit against a `RobotRequirements` definition."""

    # Retain the requirements against which candidate capabilities will be evaluated.
    def __init__(self, requirements):
        self.requirements = requirements

    def reconcile(self, composite_unit):
        """Score available nodes, assign roles, and derive active behaviors."""
        nodes = composite_unit.flatten_nodes()
        required = self.requirements.required_roles
        optional = self.requirements.optional_roles

        candidate_map = {}
        used_nodes = {}
        assignments = {}
        matched_roles = []
        partial_matches = []
        missing_roles = []
        diagnostics = []

        for role_req in required:
            role_name = role_req.get("role")
            candidates = self._map_candidates(role_req, nodes)
            candidate_map[role_name] = candidates

        for role_req in required:
            role_name = role_req.get("role")
            chosen = self._select_candidate(candidate_map.get(role_name, []), used_nodes)
            if chosen is None:
                assignments[role_name] = None
                missing_roles.append(role_name)
                diagnostics.append("%s missing" % role_name)
                continue

            node_id = chosen["node"].node_id
            assignments[role_name] = node_id
            used_nodes[node_id] = True
            if chosen["score"] >= ROLE_SCORE_EXACT:
                matched_roles.append(role_name)
                diagnostics.append("%s matched by %s" % (role_name, node_id))
            else:
                partial_matches.append(role_name)
                diagnostics.append(
                    "%s partially matched by %s (%s)"
                    % (role_name, node_id, chosen["reason"])
                )

        optional_results = {}
        for role_req in optional:
            role_name = role_req.get("role")
            optional_choice = self._select_candidate(
                self._map_candidates(role_req, nodes),
                {},
            )
            optional_results[role_name] = "matched" if optional_choice else "missing"

        behavior_state = self._evaluate_behaviors(assignments, optional_results, partial_matches)
        selected_profile = self._select_profile(behavior_state, matched_roles, optional_results)

        total_roles = len(required)
        matched_score = len(matched_roles) * 100
        partial_score = len(partial_matches) * ROLE_SCORE_PARTIAL
        overall = 0
        if total_roles:
            overall = int((matched_score + partial_score) / total_roles)

        return {
            "match_score": overall / 100.0,
            "role_assignment": assignments,
            "matched_roles": matched_roles,
            "partial_matches": partial_matches,
            "missing_roles": missing_roles,
            "optional_roles": optional_results,
            "enabled_behaviors": behavior_state["enabled"],
            "partial_behaviors": behavior_state["partial"],
            "disabled_behaviors": behavior_state["disabled"],
            "selected_profile": selected_profile,
            "diagnostics": diagnostics,
            "candidate_map": self._serialize_candidates(candidate_map),
        }

    def _map_candidates(self, role_req, nodes):
        """Return scored candidates for a required or optional role."""
        candidates = []
        for node in nodes:
            score, reason = self._score_role(role_req, node)
            if score > 0:
                candidates.append({
                    "node": node,
                    "score": score,
                    "reason": reason,
                })
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates

    def _score_role(self, role_req, node):
        """Score how well a node satisfies one role requirement."""
        role_name = role_req.get("role")
        if role_name not in node.provided_roles:
            return 0, "semantic role missing"
        if node.calibration_state not in ("ready", "calibrated", "ok", "unknown"):
            return 0, "calibration invalid"

        score = ROLE_SCORE_EXACT
        reasons = []

        required_dof = int(role_req.get("dof", 0) or 0)
        if required_dof:
            best_dof = self._best_joint_dof(node)
            if best_dof < required_dof:
                return 0, "insufficient dof"
            if best_dof > required_dof:
                score = ROLE_SCORE_PARTIAL
                reasons.append("extra dof")

        required_interfaces = role_req.get("interfaces", [])
        if required_interfaces:
            missing = []
            for interface in required_interfaces:
                if interface not in node.control_interfaces:
                    missing.append(interface)
            if missing:
                if "velocity" in node.control_interfaces or "torque" in node.control_interfaces:
                    score = min(score, ROLE_SCORE_PARTIAL)
                    reasons.append("missing interfaces: %s" % ",".join(missing))
                else:
                    return 0, "missing interfaces"

        required_sensor = role_req.get("sensor")
        if required_sensor:
            if not self._has_sensor(node, required_sensor):
                return 0, "sensor missing"

        confidence = int(node.confidence)
        if confidence < 50:
            score = min(score, ROLE_SCORE_LOW)
            reasons.append("low confidence")
        elif confidence < 80:
            score = min(score, ROLE_SCORE_PARTIAL)
            reasons.append("reduced confidence")

        if not reasons:
            reasons.append("exact")
        return score, ", ".join(reasons)

    def _best_joint_dof(self, node):
        """Return the highest joint degree-of-freedom exposed by the node."""
        best = 0
        for joint in node.joints:
            value = int(joint.get("dof", 0) or 0)
            if value > best:
                best = value
        return best

    def _has_sensor(self, node, sensor_type):
        """Check whether a node exposes a sensor of the requested type."""
        for sensor in node.sensors:
            if sensor.get("type") == sensor_type:
                return True
        return False

    def _select_candidate(self, candidates, used_nodes):
        """Pick the best unused candidate from a scored candidate list."""
        for candidate in candidates:
            node_id = candidate["node"].node_id
            if not used_nodes.get(node_id):
                return candidate
        return None

    def _evaluate_behaviors(self, assignments, optional_results, partial_matches):
        """Compute enabled, partial, and disabled behaviors from role state."""
        enabled = []
        partial = []
        disabled = []
        role_state = {}
        for role_name in assignments:
            value = assignments[role_name]
            if value is None:
                role_state[role_name] = "missing"
            elif role_name in partial_matches:
                role_state[role_name] = "partial"
            else:
                role_state[role_name] = "matched"
        for role_name in optional_results:
            if optional_results[role_name] == "matched":
                role_state[role_name] = "matched"

        for behavior_name in self.requirements.behavior_definitions:
            definition = self.requirements.behavior_definitions[behavior_name]
            state = self._evaluate_behavior_rule(definition, role_state)
            if state == "enabled":
                enabled.append(behavior_name)
            elif state == "partial":
                partial.append(behavior_name)
            else:
                disabled.append(behavior_name)

        return {
            "enabled": enabled,
            "partial": partial,
            "disabled": disabled,
        }

    def _evaluate_behavior_rule(self, definition, role_state):
        """Evaluate a single behavior definition against the current role state."""
        required = definition.get("requires", [])
        if required:
            matched = 0
            partial = 0
            for role_name in required:
                state = role_state.get(role_name, "missing")
                if state == "matched":
                    matched += 1
                elif state == "partial":
                    partial += 1
            if matched == len(required):
                return "enabled"
            if matched + partial > 0:
                return "partial"
            return "disabled"

        requires_any = definition.get("requires_any", [])
        for option_group in requires_any:
            if isinstance(option_group, str):
                if role_state.get(option_group) == "matched":
                    return "enabled"
                if role_state.get(option_group) == "partial":
                    return "partial"
                continue

            all_matched = True
            partial_found = False
            for role_name in option_group:
                state = role_state.get(role_name, "missing")
                if state == "missing":
                    all_matched = False
                    partial_found = False
                    break
                if state == "partial":
                    partial_found = True
            if all_matched and not partial_found:
                return "enabled"
            if all_matched and partial_found:
                return "partial"

        return "disabled"

    def _select_profile(self, behavior_state, matched_roles, optional_results):
        """Pick the highest-priority personality profile that still fits."""
        role_lookup = {}
        for role_name in matched_roles:
            role_lookup[role_name] = True
        for role_name in optional_results:
            if optional_results[role_name] == "matched":
                role_lookup[role_name] = True

        enabled_lookup = {}
        for behavior_name in behavior_state["enabled"]:
            enabled_lookup[behavior_name] = True

        ranked = []
        for profile in self.requirements.personality_profiles:
            if not self._profile_matches(profile, role_lookup, enabled_lookup):
                continue
            ranked.append(profile)

        if not ranked:
            return "disabled_limb"

        ranked.sort(key=lambda profile: int(profile.get("priority", 0)), reverse=True)
        return ranked[0].get("name", "unknown")

    def _profile_matches(self, profile, role_lookup, enabled_lookup):
        """Check whether a personality profile is compatible with the match."""
        for role_name in profile.get("requires_roles", []):
            if not role_lookup.get(role_name):
                return False
        for behavior_name in profile.get("required_behaviors", []):
            if not enabled_lookup.get(behavior_name):
                return False
        for behavior_name in profile.get("excluded_behaviors", []):
            if enabled_lookup.get(behavior_name):
                return False
        requires_any = profile.get("requires_any_role", [])
        if requires_any:
            any_match = False
            for role_name in requires_any:
                if role_lookup.get(role_name):
                    any_match = True
                    break
            if not any_match:
                return False
        return True

    def _serialize_candidates(self, candidate_map):
        """Convert candidate objects into plain JSON-friendly structures."""
        result = {}
        for role_name in candidate_map:
            entries = []
            for candidate in candidate_map[role_name]:
                entries.append({
                    "node_id": candidate["node"].node_id,
                    "score": candidate["score"] / 100.0,
                    "reason": candidate["reason"],
                })
            result[role_name] = entries
        return result


def component_to_part(component, part_kind=None, control_modes=None, feedback_modes=None):
    """Build a composition protocol `part` object from a component node."""
    dofs = []
    for index, joint in enumerate(component.joints):
        joint_dof = int(joint.get("dof", 0) or 0)
        axes = joint.get("axis") or []
        if not isinstance(axes, list):
            axes = [axes]
        limits = joint.get("limits")
        min_value = None
        max_value = None
        if isinstance(limits, list) and len(limits) >= 2:
            min_value = limits[0]
            max_value = limits[1]
        for axis_index in range(joint_dof):
            axis_name = "axis_{}".format(axis_index)
            if axis_index < len(axes) and axes[axis_index]:
                axis_name = str(axes[axis_index])
            dofs.append(
                Schema.dof_definition(
                    dof_id="{}_{}".format(index, axis_name),
                    kind=Schema.DOF_ANGULAR,
                    axis=axis_name,
                    min_value=min_value,
                    max_value=max_value,
                    unit=Schema.UNIT_DEGREES,
                )
            )

    if not dofs and component.sensors:
        return Schema.part_definition(
            part_kind or Schema.PART_SENSOR,
            model=component.node_type,
            part_class="sensor_module",
            control_modes=control_modes or [],
            feedback_modes=feedback_modes or ["telemetry"],
            sensors=_copy_list(component.sensors),
            roles=list(component.provided_roles),
        )

    return Schema.part_definition(
        part_kind or Schema.PART_JOINT,
        model=component.node_type,
        part_class="articulated_joint",
        dofs=dofs,
        coupling=Schema.COUPLING_INDEPENDENT,
        control_modes=control_modes or list(component.control_interfaces),
        feedback_modes=feedback_modes or [Schema.FEEDBACK_ENCODER],
        traits=_copy_dict(component.provided_traits),
        roles=list(component.provided_roles),
    )


def component_to_location(component, location_id=None, parent_location_id=None, source=None):
    """Build a composition protocol `loc` object from a component node."""
    mount_family = None
    if component.provided_roles:
        mount_family = component.provided_roles[0]
    return Schema.location_definition(
        location_id or component.mount_point or component.node_id,
        parent=parent_location_id or component.parent_mount,
        family=mount_family,
        source=source or Schema.LOCATION_SYNTHETIC,
        confidence=component.confidence,
    )


def component_to_state(component):
    """Build a composition protocol `state` object from a component node."""
    health = Schema.HEALTH_OK
    if component.calibration_state not in ("ready", "calibrated", "ok", "unknown"):
        health = Schema.HEALTH_DEGRADED
    calibration = component.calibration_state
    if calibration == "ok":
        calibration = Schema.CAL_READY
    return Schema.state_definition(
        calibration=calibration,
        health=health,
        confidence=component.confidence,
        faults=list(component.diagnostics),
    )


def build_mount_claim(component, location_id=None, parent_location_id=None, source=None):
    """Build a self-contained `part` / `loc` / `state` claim payload."""
    return {
        "part": component_to_part(component),
        "loc": component_to_location(
            component,
            location_id=location_id,
            parent_location_id=parent_location_id,
            source=source,
        ),
        "state": component_to_state(component),
    }
