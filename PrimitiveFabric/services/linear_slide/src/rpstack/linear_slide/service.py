"""Capability-oriented closed-loop linear-slide composite service."""

import _thread
import math

from rpstack.support import asyncio, call
from rpstack.interfaces import PositionActuator, PrimitiveService


class LinearSlide(PrimitiveService, PositionActuator):
    """Coordinate a motion actuator and linear position observer.

    Dependencies are created and owned by the node runtime.
    """

    # Connect motion and position capabilities, then prepare limits, calibration, and
    # cancellation state.
    def __init__(self, motor, position, signals=None):
        self.motor = motor
        self.signals = signals
        self.signal_id = 'slide'
        self.telemetry_dropped = 0
        self.position_observer = position
        self.positive_direction = True
        self.tolerance_m = 0.001
        self.max_steps = 10000
        self.no_motion_sample_limit = 10
        self.min_position_m = self.max_position_m = None
        self.calibration = None
        self.steps_per_mm = None
        self._busy = False
        self._closed = False
        self._cancel_requested = False
        self._target_m = None
        self._last_position = None

    # Validate travel and motion settings before storing them for subsequent slide commands.
    def configure(self, config=None):
        config = config or {}
        if 'signal_id' in config:
            if not isinstance(config['signal_id'], str) or not config['signal_id']:
                raise ValueError('signal_id must be a nonempty service ID')
            self.signal_id = config['signal_id']
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
        for key in ("no_motion_sample_limit",):
            if key in config:
                value = int(config[key])
                if value <= 0:
                    raise ValueError(key + " must be positive")
                setattr(self, key, value)
        lower = config.get("min_position_m", self.min_position_m)
        upper = config.get("max_position_m", self.max_position_m)
        for value in (lower, upper):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError("range bounds must be finite numbers")
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError("minimum position must be less than maximum")
        self.min_position_m, self.max_position_m = lower, upper
        return True

    def init(self):
        """Initialize without moving; calibrate is an explicit operation."""
        return not self._closed

    async def calibrate(self, steps=1000):
        """Measure full forward/reverse pulse runs, with no TOF reads in motion."""
        if type(steps) is not int or steps < 1:
            raise ValueError("steps must be a positive integer")
        if steps > self.max_steps:
            raise ValueError("distance test steps exceed max_steps")
        self._begin_motion()
        self.steps_per_mm = None
        self.calibration = None
        try:
            before = await self._measurement()
            readings = [before.value]
            deltas = []
            for direction in (True, False):
                label = "forward" if direction else "reverse"
                print("[calibrate] {} start TOF position: {} mm".format(
                    label, before.value * 1000))
                await self._run_steps(direction, steps)
                after = await self._measurement()
                delta = after.value - before.value
                print("[calibrate] {} end TOF position: {} mm (change: {} mm)".format(
                    label, after.value * 1000, delta * 1000))
                if abs(delta) < max(0.001, self.tolerance_m * 2):
                    raise RuntimeError(
                        "Calibration TOF displacement too small: direction={}, steps={}, "
                        "before_mm={}, after_mm={}, delta_mm={}, required_mm={}; "
                        "check stationary position readings and sensor target".format(
                            direction, steps, before.value * 1000, after.value * 1000,
                            delta * 1000, max(0.001, self.tolerance_m * 2) * 1000))
                deltas.append(delta)
                readings.append(after.value)
                before = after
            if deltas[0] * deltas[1] >= 0:
                raise RuntimeError("Calibration directions did not produce opposite motion")
            if abs(deltas[0] + deltas[1]) > max(2 * self.tolerance_m, max(abs(d) for d in deltas) * 0.25):
                raise RuntimeError("Calibration distances disagree; check lost steps, backlash, or TOF readings")
            self.positive_direction = deltas[0] > 0
            self.steps_per_mm = 2.0 * steps / (sum(abs(d) for d in deltas) * 1000.0)
            self.calibration = {
                "steps_each_direction": steps,
                "positions_mm": [value * 1000 for value in readings],
                "forward_mm": deltas[0] * 1000, "reverse_mm": deltas[1] * 1000,
                "steps_per_mm": self.steps_per_mm,
                "positive_direction": self.positive_direction,
            }
            return dict(self.calibration)
        finally:
            self.motor.stop()
            self._busy = False


    # Reject overlapping moves and establish fresh cancellation state for this operation.
    def _begin_motion(self):
        self._require_open()
        if self._busy:
            raise RuntimeError("Linear slide is already moving")
        self._busy = True
        self._cancel_requested = False

    # Require a valid, finite position sample before using it in motion calculations.
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

        # Let the pulse worker observe a stop request or service shutdown.
        def cancelled():
            return self._cancel_requested or self._closed

        # Run synchronous motor pulses in a worker, handing async work and errors back to the
        # caller.
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

        # Reserve stack for the pulse worker too, without changing defaults
        # for unrelated threads after dispatch.
        previous_stack = _thread.stack_size()
        try:
            _thread.stack_size(65536)
            _thread.start_new_thread(worker, ())
        finally:
            _thread.stack_size(previous_stack)
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

    # Confirm the slide remains open before acknowledging the runtime start hook.
    def start(self):
        self._require_open()
        return True

    # Clear idle command state without reopening a shut-down slide or interrupting motion.
    def reset(self):
        if self._busy:
            raise RuntimeError("Linear slide is already moving")
        self._cancel_requested = False
        self._target_m = None
        return not self._closed

    def set_range(self, min_mm, max_mm):
        """Update absolute target bounds in RAM; does not move the carriage."""
        self._require_open()
        if self._busy:
            raise RuntimeError("Cannot change range while the slide is moving")
        if any(type(value) not in (int, float) or not math.isfinite(value)
               for value in (min_mm, max_mm)):
            raise ValueError("range bounds must be finite numbers")
        if min_mm >= max_mm:
            raise ValueError("min_mm must be less than max_mm")
        self.min_position_m, self.max_position_m = min_mm / 1000.0, max_mm / 1000.0
        return self.get_range()

    # Present optional travel bounds in the millimetres used by the command interface.
    def get_range(self):
        return {"min_mm": self.min_position_m * 1000 if self.min_position_m is not None else None,
                "max_mm": self.max_position_m * 1000 if self.max_position_m is not None else None}

    # Collect calibration, travel limits, pulse mode, and the most recent observed position.
    def status(self):
        return {
            "active": not self._closed,
            "range_mm": self.get_range(),
            "max_steps": self.max_steps,
            "target_m": self._target_m,
            "calibrated": self.steps_per_mm is not None,
            "calibration": dict(self.calibration) if self.calibration else None,
            "pulse_mode": "blocking_worker" if getattr(self.motor, "command_blocking", None) else "capability_fallback",
            "steps_per_mm": self.steps_per_mm,
            "positive_direction": self.positive_direction,
            "position": self._last_position.as_dict() if self._last_position else None,
            "telemetry_dropped": self.telemetry_dropped,
        }

    # Read and retain a position sample, requiring linear coordinates in metres.
    async def position(self):
        self._require_open()
        sample = await call(self.position_observer.position)
        if sample.kind != "linear" or sample.unit != "m":
            raise TypeError("position_observer must return linear positions in metres")
        self._last_position = sample
        if self.signals is not None:
            try:
                self.signals.publish('motion.position.updated',
                                     dict(sample.as_dict(), service=self.signal_id))
            except (RuntimeError, ValueError):
                # Telemetry congestion must not interrupt motion or its cleanup.
                self.telemetry_dropped += 1
        return sample

    async def move_to(self, target):
        """Approach the target in 96% batches, measuring between workers."""
        self._require_open()
        target_m = float(target)
        self._validate_target(target_m)
        if self.steps_per_mm is None:
            raise RuntimeError("Run calibrate() before moving to calibrate scale and direction")
        self._begin_motion()
        self._target_m = target_m
        steps_commanded = 0
        metres_per_step = 0.001 / self.steps_per_mm
        no_motion_count = 0
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
                    raise RuntimeError("Measured position is moving away from the target; rerun calibrate to check positive_direction")
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




    # Signal cancellation to active motion, clear the target, and stop the motor.
    def stop(self):
        self._cancel_requested = True
        self._target_m = None
        return self.motor.stop()

    # Reject non-finite targets and commands outside the configured travel range.
    def _validate_target(self, target_m):
        if not math.isfinite(target_m):
            raise ValueError("target must be finite")
        if self.min_position_m is not None and target_m < self.min_position_m:
            raise ValueError("target is below the configured minimum position")
        if self.max_position_m is not None and target_m > self.max_position_m:
            raise ValueError("target is above the configured maximum position")

    # Prevent further operations after the slide has been shut down.
    def _require_open(self):
        if self._closed:
            raise RuntimeError("LinearSlide has been shut down")

    # Stop once and permanently close this slide instance.
    def shutdown(self):
        if self._closed:
            return True
        motor_result = self.stop()
        self._closed = True
        return motor_result is not False

    # Expose this slide to a with-block that owns its shutdown.
    def __enter__(self):
        return self

    # Shut down the slide when its with-block finishes, including on errors.
    def __exit__(self, exception_type, exception, traceback):
        self.shutdown()
