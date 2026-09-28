"""
Compact schema constants and helpers for composition-oriented messaging.
"""


class Schema:
    """Protocol constants shared by codecs, transports, and registries."""

    PROTOCOL_VERSION = 2
    SHORT_PACKET_MAX_BYTES = 205

    # Message types.
    TYPE_ANNOUNCE = "a"
    TYPE_CLAIM = "c"
    TYPE_UPDATE = "u"
    TYPE_WITHDRAW = "x"
    TYPE_REPORT = "r"
    TYPE_EVENT = "e"

    # Common envelope.
    F_VERSION = "v"
    F_TYPE = "t"
    F_NODE_ID = "n"
    F_BOOT_ID = "b"
    F_SEQUENCE = "q"
    F_TIMESTAMP = "ts"
    F_TRACE = "otel"

    # Shared message fields.
    F_TTL = "ttl"
    F_CLAIM_ID = "cid"
    F_REASON = "reason"
    F_STATUS = "status"
    F_DETAIL = "detail"
    F_SUBJECT = "subject"
    F_FIRMWARE = "fw"
    F_PART_KIND = "pk"
    F_EVENT = "event"

    # Claim payloads.
    F_PART = "part"
    F_LOCATION = "loc"
    F_STATE = "state"

    # Event payloads.
    F_EVENT_NAME = "name"
    F_EVENT_PRIORITY = "priority"
    F_EVENT_TTL = "ttl"
    F_EVENT_PARAMETERS = "parameters"

    # Part fields.
    F_KIND = "kind"
    F_MODEL = "model"
    F_CLASS = "class"
    F_DOFS = "dofs"
    F_COUPLING = "coupling"
    F_CONTROL_MODES = "ctrl"
    F_FEEDBACK_MODES = "fb"

    # DOF fields.
    F_DOF_ID = "id"
    F_DOF_KIND = "kind"
    F_DOF_AXIS = "axis"
    F_DOF_MIN = "min"
    F_DOF_MAX = "max"
    F_DOF_UNIT = "unit"
    F_DOF_FRAME = "frame"
    F_DOF_MAX_VELOCITY = "max_velocity"
    F_DOF_MAX_ACCELERATION = "max_acceleration"
    F_DOF_RESOLUTION = "resolution"

    # Location fields.
    F_LOCATION_ID = "id"
    F_LOCATION_PARENT = "parent"
    F_LOCATION_FAMILY = "family"
    F_LOCATION_SOURCE = "src"
    F_LOCATION_CONFIDENCE = "conf"
    F_LOCATION_ORIENTATION = "orient"

    # State fields.
    F_STATE_CALIBRATION = "cal"
    F_STATE_HEALTH = "health"
    F_STATE_CONFIDENCE = "conf"
    F_STATE_FAULTS = "faults"
    F_STATE_TEMPERATURE = "temp"
    F_STATE_SUPPLY = "supply"

    # Catalog values.
    PART_JOINT = "joint"
    PART_WHEEL = "wheel"
    PART_SEGMENT = "segment"
    PART_SENSOR = "sensor"
    PART_POWER = "power"

    DOF_ANGULAR = "angular"
    DOF_LINEAR = "linear"
    DOF_CONTINUOUS = "continuous"

    COUPLING_INDEPENDENT = "independent"
    COUPLING_COUPLED = "coupled"
    COUPLING_MIMIC = "mimic"

    CONTROL_POSITION = "position"
    CONTROL_VELOCITY = "velocity"
    CONTROL_TORQUE = "torque"
    CONTROL_STOP = "stop"
    CONTROL_HOLD = "hold"

    FEEDBACK_NONE = "none"
    FEEDBACK_ENCODER = "encoder"
    FEEDBACK_ABSOLUTE_ENCODER = "absolute_encoder"
    FEEDBACK_CURRENT = "current"
    FEEDBACK_TORQUE_ESTIMATE = "torque_estimate"

    LOCATION_SYNTHETIC = "synthetic"
    LOCATION_QR = "qr"
    LOCATION_NFC = "nfc"
    LOCATION_MANUAL = "manual"

    CAL_UNKNOWN = "unknown"
    CAL_UNCALIBRATED = "uncalibrated"
    CAL_CALIBRATING = "calibrating"
    CAL_READY = "ready"
    CAL_FAULT = "fault"

    HEALTH_OK = "ok"
    HEALTH_DEGRADED = "degraded"
    HEALTH_FAULT = "fault"
    HEALTH_OFFLINE = "offline"

    EVENT_PRIORITY_LOW = "low"
    EVENT_PRIORITY_NORMAL = "normal"
    EVENT_PRIORITY_HIGH = "high"
    EVENT_PRIORITY_CRITICAL = "critical"

    UNIT_NONE = ""
    UNIT_DEGREES = "deg"
    UNIT_MM = "mm"
    UNIT_CM = "cm"
    UNIT_M = "m"
    UNIT_PERCENT = "%"
    UNIT_CELSIUS = "C"
    UNIT_DEG_PER_SEC = "deg/s"
    UNIT_BOOL = "bool"

    ANNOUNCE_SCHEMA = {
        "required": (F_VERSION, F_TYPE, F_NODE_ID, F_BOOT_ID, F_SEQUENCE, F_TIMESTAMP, F_TTL, F_PART_KIND),
        "type": TYPE_ANNOUNCE,
    }
    CLAIM_SCHEMA = {
        "required": (
            F_VERSION,
            F_TYPE,
            F_NODE_ID,
            F_BOOT_ID,
            F_SEQUENCE,
            F_TIMESTAMP,
            F_TTL,
            F_CLAIM_ID,
            F_PART,
            F_LOCATION,
            F_STATE,
        ),
        "type": TYPE_CLAIM,
    }
    UPDATE_SCHEMA = {
        "required": (
            F_VERSION,
            F_TYPE,
            F_NODE_ID,
            F_BOOT_ID,
            F_SEQUENCE,
            F_TIMESTAMP,
            F_TTL,
            F_CLAIM_ID,
            F_STATE,
        ),
        "type": TYPE_UPDATE,
    }
    WITHDRAW_SCHEMA = {
        "required": (
            F_VERSION,
            F_TYPE,
            F_NODE_ID,
            F_BOOT_ID,
            F_SEQUENCE,
            F_TIMESTAMP,
            F_CLAIM_ID,
            F_REASON,
        ),
        "type": TYPE_WITHDRAW,
    }
    REPORT_SCHEMA = {
        "required": (
            F_VERSION,
            F_TYPE,
            F_NODE_ID,
            F_BOOT_ID,
            F_SEQUENCE,
            F_TIMESTAMP,
            F_SUBJECT,
            F_STATUS,
        ),
        "type": TYPE_REPORT,
    }
    EVENT_SCHEMA = {
        "required": (
            F_VERSION,
            F_TYPE,
            F_NODE_ID,
            F_BOOT_ID,
            F_SEQUENCE,
            F_TIMESTAMP,
            F_EVENT,
        ),
        "type": TYPE_EVENT,
    }

    EVENT_PRIORITIES = (
        EVENT_PRIORITY_LOW,
        EVENT_PRIORITY_NORMAL,
        EVENT_PRIORITY_HIGH,
        EVENT_PRIORITY_CRITICAL,
    )

    @classmethod
    def dof_definition(
        cls,
        dof_id,
        kind,
        axis,
        min_value=None,
        max_value=None,
        unit=None,
        frame=None,
        max_velocity=None,
        max_acceleration=None,
        resolution=None,
    ):
        """Build one degree-of-freedom descriptor."""
        dof = {
            cls.F_DOF_ID: str(dof_id),
            cls.F_DOF_KIND: str(kind),
            cls.F_DOF_AXIS: str(axis),
        }
        if min_value is not None:
            dof[cls.F_DOF_MIN] = min_value
        if max_value is not None:
            dof[cls.F_DOF_MAX] = max_value
        if unit is not None:
            dof[cls.F_DOF_UNIT] = unit
        if frame is not None:
            dof[cls.F_DOF_FRAME] = str(frame)
        if max_velocity is not None:
            dof[cls.F_DOF_MAX_VELOCITY] = max_velocity
        if max_acceleration is not None:
            dof[cls.F_DOF_MAX_ACCELERATION] = max_acceleration
        if resolution is not None:
            dof[cls.F_DOF_RESOLUTION] = resolution
        return dof

    @classmethod
    def part_definition(
        cls,
        kind,
        model=None,
        part_class=None,
        dofs=None,
        coupling=None,
        control_modes=None,
        feedback_modes=None,
        **extra,
    ):
        """Build a generic part descriptor."""
        part = {cls.F_KIND: str(kind)}
        if model is not None:
            part[cls.F_MODEL] = str(model)
        if part_class is not None:
            part[cls.F_CLASS] = str(part_class)
        if dofs is not None:
            part[cls.F_DOFS] = list(dofs)
        if coupling is not None:
            part[cls.F_COUPLING] = str(coupling)
        if control_modes is not None:
            part[cls.F_CONTROL_MODES] = [str(value) for value in control_modes]
        if feedback_modes is not None:
            part[cls.F_FEEDBACK_MODES] = [str(value) for value in feedback_modes]
        for key, value in extra.items():
            part[key] = value
        return part

    @classmethod
    def joint_part_definition(
        cls,
        dofs,
        model=None,
        part_class="articulated_joint",
        coupling=COUPLING_INDEPENDENT,
        control_modes=None,
        feedback_modes=None,
        **extra,
    ):
        """Build a joint part descriptor."""
        return cls.part_definition(
            cls.PART_JOINT,
            model=model,
            part_class=part_class,
            dofs=dofs,
            coupling=coupling,
            control_modes=control_modes,
            feedback_modes=feedback_modes,
            **extra,
        )

    @classmethod
    def wheel_part_definition(
        cls,
        dofs,
        model=None,
        part_class="drive_module",
        control_modes=None,
        feedback_modes=None,
        **extra,
    ):
        """Build a wheel part descriptor."""
        return cls.part_definition(
            cls.PART_WHEEL,
            model=model,
            part_class=part_class,
            dofs=dofs,
            control_modes=control_modes,
            feedback_modes=feedback_modes,
            **extra,
        )

    @classmethod
    def location_definition(
        cls,
        location_id,
        parent=None,
        family=None,
        source=None,
        confidence=None,
        orientation=None,
        **extra,
    ):
        """Build a location identity descriptor."""
        location = {cls.F_LOCATION_ID: str(location_id)}
        if parent is not None:
            location[cls.F_LOCATION_PARENT] = str(parent)
        if family is not None:
            location[cls.F_LOCATION_FAMILY] = str(family)
        if source is not None:
            location[cls.F_LOCATION_SOURCE] = str(source)
        if confidence is not None:
            location[cls.F_LOCATION_CONFIDENCE] = int(confidence)
        if orientation is not None:
            location[cls.F_LOCATION_ORIENTATION] = str(orientation)
        for key, value in extra.items():
            location[key] = value
        return location

    @classmethod
    def state_definition(
        cls,
        calibration,
        health,
        confidence,
        faults=None,
        temperature=None,
        supply=None,
        **extra,
    ):
        """Build a runtime state descriptor."""
        state = {
            cls.F_STATE_CALIBRATION: str(calibration),
            cls.F_STATE_HEALTH: str(health),
            cls.F_STATE_CONFIDENCE: int(confidence),
        }
        if faults is not None:
            state[cls.F_STATE_FAULTS] = list(faults)
        if temperature is not None:
            state[cls.F_STATE_TEMPERATURE] = temperature
        if supply is not None:
            state[cls.F_STATE_SUPPLY] = supply
        for key, value in extra.items():
            state[key] = value
        return state
