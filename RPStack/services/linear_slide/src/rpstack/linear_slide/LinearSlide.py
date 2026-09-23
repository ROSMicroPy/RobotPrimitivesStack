"""Capability-oriented closed-loop linear-slide composite service."""

import _thread
import math

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
        self.steps_per_mm = None
        self._busy = False
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
            if not math.isfinite(tolerance) or tolerance < 0:
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

    async def init(self):
        """Measure 1,000 steps in each direction before accepting targets."""
        self._begin_motion()
        self.steps_per_mm = None
        try:
            before = await self._measurement()
            deltas = []
            for direction in (True, False):
                await self._run_steps(direction, 1000)
                after = await self._measurement()
                delta = after.value - before.value
                if delta == 0:
                    raise RuntimeError("No position change during slide calibration")
                deltas.append(delta)
                before = after
            if deltas[0] * deltas[1] >= 0:
                raise RuntimeError("Calibration directions did not produce opposite motion")
            self.positive_direction = deltas[0] > 0
            self.steps_per_mm = 2000.0 / (sum(abs(d) for d in deltas) * 1000.0)
            return True
        finally:
            self.motor.stop()
            self._busy = False

    def _begin_motion(self):
        self._require_open()
        if self._busy:
            raise RuntimeError("Linear slide is already moving")
        self._busy = True
        self._cancel_requested = False

    async def _measurement(self):
        sample = await self.position()
        if not sample.valid or not math.isfinite(sample.value):
            raise RuntimeError("Position observer returned an invalid sample")
        return sample

    async def _run_steps(self, direction, steps):
        """Run a fresh worker per batch; only the main loop reads position.

        Native motors expose command_blocking. Synchronous incremental
        capabilities are stepped directly. Async bridges retain their own loop.
        """
        done = _thread.allocate_lock()
        done.acquire()
        result = [None]
        pending = [None]

        def cancelled():
            return self._cancel_requested or self._closed

        def worker():
            try:
                if cancelled():
                    raise RuntimeError("Linear slide move was cancelled")
                blocking = getattr(self.motor, "command_blocking", None)
                if blocking:
                    if not blocking(direction, steps, cancelled):
                        raise RuntimeError("Motion actuator failed while moving the linear slide")
                else:
                    for _ in range(steps):
                        if cancelled():
                            raise RuntimeError("Linear slide move was cancelled")
                        response = self.motor.command(direction, 1)
                        if hasattr(response, "__await__") or hasattr(response, "send"):
                            pending[0] = response
                            break
                        if not response:
                            raise RuntimeError("Motion actuator failed while moving the linear slide")
            except BaseException as error:
                result[0] = error
            finally:
                done.release()

        _thread.start_new_thread(worker, ())
        try:
            while not done.acquire(False):
                await asyncio.sleep(0.001)
            done.release()
            if result[0] is not None:
                raise result[0]
            if cancelled():
                raise RuntimeError("Linear slide move was cancelled")
            if pending[0] is not None:
                response = pending[0]
                pending[0] = None
                if not await response:
                    raise RuntimeError("Motion actuator failed while moving the linear slide")
                for _ in range(steps - 1):
                    if cancelled():
                        raise RuntimeError("Linear slide move was cancelled")
                    if not await call(self.motor.command, direction, 1):
                        raise RuntimeError("Motion actuator failed while moving the linear slide")
            if cancelled():
                raise RuntimeError("Linear slide move was cancelled")
        finally:
            if not done.acquire(False):
                self._cancel_requested = True
                self.motor.stop()
                while not done.acquire(False):
                    await asyncio.sleep(0.001)
            done.release()
            if pending[0] is not None:
                pending[0].close()

    def start(self):
        self._require_open()
        return True

    def reset(self):
        if self._busy:
            raise RuntimeError("Linear slide is already moving")
        self._cancel_requested = False
        self._target_m = None
        return not self._closed

    def status(self):
        return {
            "active": not self._closed,
            "target_m": self._target_m,
            "calibrated": self.steps_per_mm is not None,
            "steps_per_mm": self.steps_per_mm,
            "positive_direction": self.positive_direction,
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
        """Approach the target in 96% batches, measuring between workers."""
        self._require_open()
        target_m = float(target)
        self._validate_target(target_m)
        if self.steps_per_mm is None:
            raise RuntimeError("Linear slide must be initialized before moving")
        self._begin_motion()
        self._target_m = target_m
        steps_commanded = 0
        metres_per_step = 0.001 / self.steps_per_mm
        moving_away_count = no_motion_count = 0
        try:
            current = await self._measurement()
            while True:
                if self._cancel_requested:
                    raise RuntimeError("Linear slide move was cancelled")
                error_m = target_m - current.value
                if abs(error_m) <= self.tolerance_m:
                    return current
                if steps_commanded >= self.max_steps:
                    raise RuntimeError(
                        "Target {} m was not reached after {} steps; last position was {} m".format(
                            target_m, steps_commanded, current.value))
                batch_size = min(max(1, int(abs(error_m) * 0.96 / metres_per_step)),
                                 self.max_steps - steps_commanded)
                direction = self.positive_direction if error_m > 0 else not self.positive_direction
                previous_value = current.value
                await self._run_steps(direction, batch_size)
                steps_commanded += batch_size
                current = await self._measurement()
                observed_m = abs(current.value - previous_value)
                if observed_m > 0:
                    no_motion_count = 0
                    metres_per_step = (metres_per_step + observed_m / batch_size) / 2.0
                else:
                    no_motion_count += 1
                    if no_motion_count >= self.no_motion_sample_limit:
                        raise RuntimeError("No position change detected after {} commanded steps".format(steps_commanded))
                if abs(target_m - current.value) > abs(error_m) + self.tolerance_m:
                    moving_away_count += 1
                else:
                    moving_away_count = 0
                if moving_away_count >= 3:
                    raise RuntimeError("Measured position is moving away from the target; invert positive_direction")
        except BaseException:
            self.motor.stop()
            raise
        finally:
            self._target_m = None
            self._busy = False

    async def jog_steps(self, steps, direction=True):
        """Move a fixed number of steps without closed-loop positioning."""
        self._require_open()
        steps = int(steps)
        if steps <= 0:
            raise ValueError("steps must be greater than zero")
        self._begin_motion()
        try:
            before = await self._measurement()
            await self._run_steps(bool(direction), steps)
            after = await self.position()
            return {
                "steps": steps, "direction": bool(direction),
                "position_before": before.as_dict(), "position_after": after.as_dict(),
            }
        finally:
            self.motor.stop()
            self._busy = False

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
        if not math.isfinite(target_m):
            raise ValueError("target must be finite")
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
