"""Hardware-independent capability contracts for Robot Primitive services.

The contracts deliberately avoid ``abc`` and ``dataclasses`` so they remain
usable on constrained MicroPython targets.  Implementations may inherit from
these classes or satisfy them structurally (duck typing).
"""


class ServiceState:
    NEW = "new"
    CONFIGURED = "configured"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class PrimitiveService:
    """Lifecycle contract implemented by every runtime-managed service."""

    def configure(self, config=None):
        raise NotImplementedError

    def init(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError

    def status(self):
        raise NotImplementedError


class Measurement:
    """A timestamped, quality-qualified scalar measurement."""

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

    def stop(self):
        raise NotImplementedError


class PositionActuator:
    INTERFACE = "motion.position_actuator"
    VERSION = 1

    def move_to(self, target):
        """Move to a canonical-unit target and return the final sample."""
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError


__all__ = (
    "DistanceObserver", "DistanceSample", "Measurement", "MotionActuator",
    "PositionActuator", "PositionObserver", "PositionSample",
    "PrimitiveService", "ServiceState",
)
