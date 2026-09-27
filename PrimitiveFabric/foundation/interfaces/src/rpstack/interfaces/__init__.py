"""Hardware-independent capability contracts for Robot Primitive services.

The contracts deliberately avoid ``abc`` and ``dataclasses`` so they remain
usable on constrained MicroPython targets.  Implementations may inherit from
these classes or satisfy them structurally (duck typing).
"""


class ServiceState:
    NEW = "new"
    CONFIGURED = "configured"
    INITIALIZED = "initialized"
    CALIBRATING = "calibrating"
    CALIBRATED = "calibrated"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class PrimitiveService:
    """Lifecycle contract implemented by every runtime-managed service."""

    # Require services to accept their configuration before initialization.
    def configure(self, config=None):
        raise NotImplementedError

    # Require services to prepare their resources for operation.
    def init(self):
        raise NotImplementedError

    def calibrate(self):
        """Optional explicit phase; a manifest hook opts a service in."""
        return True

    # Require services to enter their operational state.
    def start(self):
        raise NotImplementedError

    # Require services to stop activity through a common lifecycle hook.
    def stop(self):
        raise NotImplementedError

    # Require services to define how they return to a reusable state.
    def reset(self):
        raise NotImplementedError

    # Require services to expose their current lifecycle and diagnostic state.
    def status(self):
        raise NotImplementedError


class Measurement:
    """A timestamped, quality-qualified scalar measurement."""

    # Store a scalar sample and its context, rejecting quality values outside zero to one.
    def __init__(self, value, unit, timestamp_ns=None, valid=True, quality=1.0,
                 reference_frame=None):
        quality = float(quality)
        if quality < 0.0 or quality > 1.0:
            raise ValueError("quality must be between 0.0 and 1.0")
        self.value = float(value)
        self.unit = unit
        self.timestamp_ns = timestamp_ns
        self.valid = bool(valid)
        self.quality = quality
        self.reference_frame = reference_frame

    # Expose the measurement and its metadata as a transport-friendly dictionary.
    def as_dict(self):
        return {
            "value": self.value,
            "unit": self.unit,
            "timestamp_ns": self.timestamp_ns,
            "valid": self.valid,
            "quality": self.quality,
            "reference_frame": self.reference_frame,
        }


class DistanceSample(Measurement):
    """Distance along a sensing ray, canonically expressed in metres."""


class PositionSample(Measurement):
    """Linear or angular position, canonically expressed in m or rad."""

    LINEAR = "linear"
    ANGULAR = "angular"

    # Validate linear/metre or angular/radian units before storing the position sample.
    def __init__(self, kind, value, unit, reference_frame,
                 timestamp_ns=None, valid=True, quality=1.0):
        if kind not in (self.LINEAR, self.ANGULAR):
            raise ValueError("kind must be linear or angular")
        if kind == self.LINEAR and unit != "m":
            raise ValueError("linear positions use canonical unit m")
        if kind == self.ANGULAR and unit != "rad":
            raise ValueError("angular positions use canonical unit rad")
        Measurement.__init__(self, value, unit, timestamp_ns, valid, quality,
                             reference_frame)
        self.kind = kind

    # Extend the shared measurement representation with the position kind.
    def as_dict(self):
        value = Measurement.as_dict(self)
        value["kind"] = self.kind
        return value


class DistanceObserver:
    INTERFACE = "sensing.distance_observer"
    VERSION = 1

    def distance(self):
        """Return a :class:`DistanceSample` in metres."""
        raise NotImplementedError


class PositionObserver:
    INTERFACE = "motion.position_observer"
    VERSION = 1

    def position(self):
        """Return a :class:`PositionSample`."""
        raise NotImplementedError


class MotionActuator:
    INTERFACE = "motion.motion_actuator"
    VERSION = 1

    def command(self, direction, amount=1):
        """Command a relative amount of mechanism motion."""
        raise NotImplementedError

    # Require motion implementations to provide a stop operation.
    def stop(self):
        raise NotImplementedError


class PositionActuator:
    INTERFACE = "motion.position_actuator"
    VERSION = 1

    def move_to(self, target):
        """Move to a canonical-unit target and return the final sample."""
        raise NotImplementedError

    # Require position controllers to provide a stop operation.
    def stop(self):
        raise NotImplementedError


__all__ = (
    "DistanceObserver", "DistanceSample", "Measurement", "MotionActuator",
    "PositionActuator", "PositionObserver", "PositionSample",
    "PrimitiveService", "ServiceState",
)
