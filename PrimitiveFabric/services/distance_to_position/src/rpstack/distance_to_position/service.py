"""Adapter from raw distance observations to installed linear position."""

from rpstack.support import call
from rpstack.interfaces import PositionObserver, PositionSample, PrimitiveService


class DistanceToPositionAdapter(PrimitiveService, PositionObserver):
    # Connect distance observations to a signed, offset position in the installed frame.
    def __init__(self, distance_observer, zero_offset_m=0.0, direction=1,
                 reference_frame="carriage", min_position_m=None,
                 max_position_m=None):
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        self.distance_observer = distance_observer
        self.zero_offset_m = float(zero_offset_m)
        self.direction = direction
        self.reference_frame = reference_frame
        self.min_position_m = min_position_m
        self.max_position_m = max_position_m
        self.running = False

    # Update the distance-to-position transform and optional travel bounds.
    def configure(self, config=None):
        config = config or {}
        if "zero_offset_m" in config:
            self.zero_offset_m = float(config["zero_offset_m"])
        if "direction" in config:
            direction = int(config["direction"])
            if direction not in (-1, 1):
                raise ValueError("direction must be -1 or 1")
            self.direction = direction
        if "reference_frame" in config:
            self.reference_frame = config["reference_frame"]
        self.min_position_m = config.get("min_position_m", self.min_position_m)
        self.max_position_m = config.get("max_position_m", self.max_position_m)
        return True

    # Acknowledge initialization; the runtime owns the underlying distance observer.
    def init(self):
        return True

    # Mark the adapter running without changing the underlying sensor.
    def start(self):
        self.running = True
        return True

    # Clear the running flag while leaving the shared observer under runtime ownership.
    def stop(self):
        self.running = False
        return True

    # Acknowledge reset without discarding the configured position transform.
    def reset(self):
        return True

    # Report the adapter's running flag and installed reference frame.
    def status(self):
        return {"running": self.running, "reference_frame": self.reference_frame}

    # Transform distance into metres of travel, preserving metadata and flagging out-of-range
    # samples.
    async def position(self):
        distance = await call(self.distance_observer.distance)
        value = self.zero_offset_m + self.direction * distance.value
        valid = distance.valid
        if self.min_position_m is not None and value < self.min_position_m:
            valid = False
        if self.max_position_m is not None and value > self.max_position_m:
            valid = False
        return PositionSample(
            PositionSample.LINEAR,
            value,
            "m",
            self.reference_frame,
            timestamp_ns=distance.timestamp_ns,
            valid=valid,
            quality=distance.quality,
        )


__all__ = ("DistanceToPositionAdapter",)
