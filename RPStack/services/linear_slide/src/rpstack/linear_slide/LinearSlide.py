"""Capability-oriented closed-loop linear-slide composite service."""

from rpstack.execution_engine import asyncio, call
from rpstack.interfaces import PositionActuator, PrimitiveService


class LinearSlide(PrimitiveService, PositionActuator):
    """Coordinate a motion actuator and linear position observer.

    Dependencies are created and owned by the node runtime.
    """

    def __init__(self, motor, position):
        self.motor = motor
        self.position_observer = position
        self.positive_direction = True
        self.tolerance_m = 0.001
        self.max_steps = 10000
        self.steps_per_sample = 1
        self.no_motion_sample_limit = 10
        self.min_position_m = self.max_position_m = None
        self._closed = False
        self._cancel_requested = False
        self._target_m = None
        self._last_position = None

    def configure(self, config=None):
        config = config or {}
        if "positive_direction" in config:
            self.positive_direction = bool(config["positive_direction"])
        if "tolerance_m" in config:
            tolerance = float(config["tolerance_m"])
            if tolerance < 0:
                raise ValueError("tolerance_m must be non-negative")
            self.tolerance_m = tolerance
        if "max_steps" in config:
            max_steps = int(config["max_steps"])
            if max_steps <= 0:
                raise ValueError("max_steps must be greater than zero")
            self.max_steps = max_steps
        if "steps_per_sample" in config:
            steps_per_sample = int(config["steps_per_sample"])
            if steps_per_sample <= 0:
                raise ValueError("steps_per_sample must be greater than zero")
            self.steps_per_sample = steps_per_sample
        for key in ("no_motion_sample_limit",):
            if key in config:
                value = int(config[key])
                if value <= 0:
                    raise ValueError(key + " must be positive")
                setattr(self, key, value)
        for key in ("min_position_m", "max_position_m"):
            if key in config:
                setattr(self, key, float(config[key]))
        if self.min_position_m is not None and self.max_position_m is not None and self.min_position_m > self.max_position_m:
            raise ValueError("minimum position exceeds maximum")
        return True

    def init(self):
        return not self._closed

    def start(self):
        self._require_open()
        return True

    def reset(self):
        self._cancel_requested = False
        self._target_m = None
        return not self._closed

    def status(self):
        return {
            "active": not self._closed,
            "target_m": self._target_m,
            "position": self._last_position.as_dict() if self._last_position else None,
        }

    async def position(self):
        self._require_open()
        sample = await call(self.position_observer.position)
        if sample.kind != "linear" or sample.unit != "m":
            raise TypeError("position_observer must return linear positions in metres")
        self._last_position = sample
        return sample

    async def move_to(self, target):
        """Move to ``target`` metres and return the final PositionSample."""
        self._require_open()
        target_m = float(target)
        self._validate_target(target_m)
        self._cancel_requested = False
        self._target_m = target_m
        steps_commanded = 0
        metres_per_step = None
        moving_away_count = 0
        no_motion_count = 0

        try:
            current = await self.position()
            while steps_commanded < self.max_steps:
                if self._cancel_requested:
                    raise RuntimeError("Linear slide move was cancelled")
                if not current.valid:
                    raise RuntimeError("Position observer returned an invalid sample")
                error_m = target_m - current.value
                if abs(error_m) <= self.tolerance_m:
                    return current

                batch_size = min(self.steps_per_sample,
                                 self.max_steps - steps_commanded)
                if metres_per_step:
                    remaining_m = max(0.0, abs(error_m) - self.tolerance_m)
                    estimated_steps = max(1, int(remaining_m / metres_per_step))
                    batch_size = min(batch_size, estimated_steps)

                direction = (self.positive_direction if error_m > 0
                             else not self.positive_direction)
                previous_value = current.value
                if not await call(self.motor.command, direction, batch_size):
                    raise RuntimeError(
                        "Motion actuator failed while moving the linear slide")
                await asyncio.sleep(0)
                steps_commanded += batch_size
                current = await self.position()

                observed_m = abs(current.value - previous_value)
                if observed_m > 0:
                    no_motion_count = 0
                    observation = observed_m / batch_size
                    metres_per_step = (
                        observation if metres_per_step is None
                        else (metres_per_step + observation) / 2.0)
                else:
                    no_motion_count += 1
                    if no_motion_count >= self.no_motion_sample_limit:
                        raise RuntimeError(
                            "No position change detected after {} commanded "
                            "steps; check STEP wiring, driver current, and "
                            "step rate".format(steps_commanded))

                next_error_m = abs(target_m - current.value)
                if next_error_m > abs(error_m) + self.tolerance_m:
                    moving_away_count += 1
                else:
                    moving_away_count = 0
                if moving_away_count >= 3:
                    raise RuntimeError(
                        "Measured position is moving away from the target; "
                        "invert positive_direction")

            raise RuntimeError(
                "Target {} m was not reached after {} steps; "
                "last position was {} m".format(
                    target_m, steps_commanded, current.value))
        except BaseException:
            self.motor.stop()
            raise
        finally:
            self._target_m = None

    async def jog_steps(self, steps, direction=True):
        """Move a fixed number of steps without closed-loop positioning."""
        self._require_open()
        steps = int(steps)
        if steps <= 0:
            raise ValueError("steps must be greater than zero")
        try:
            before = await self.position()
            if not await call(self.motor.command, bool(direction), steps):
                raise RuntimeError("Motion actuator failed while jogging")
            after = await self.position()
            return {
                "steps": steps, "direction": bool(direction),
                "position_before": before.as_dict(), "position_after": after.as_dict(),
            }
        finally:
            self.motor.stop()

    async def get_position(self):
        """Compatibility API returning integer millimetres."""
        return int(round((await self.position()).value * 1000.0))

    async def goto_position(self, position_mm):
        """Compatibility API accepting and returning millimetres."""
        return int(round((await self.move_to(float(position_mm) / 1000.0)).value * 1000.0))

    getPosition = get_position
    gotoPosition = goto_position

    def stop(self):
        self._cancel_requested = True
        self._target_m = None
        return self.motor.stop()

    def _validate_target(self, target_m):
        if self.min_position_m is not None and target_m < self.min_position_m:
            raise ValueError("target is below the configured minimum position")
        if self.max_position_m is not None and target_m > self.max_position_m:
            raise ValueError("target is above the configured maximum position")

    def _require_open(self):
        if self._closed:
            raise RuntimeError("LinearSlide has been shut down")

    def shutdown(self):
        if self._closed:
            return True
        motor_result = self.stop()
        self._closed = True
        return motor_result is not False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.shutdown()
