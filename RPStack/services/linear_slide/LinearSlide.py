"""Closed-loop linear slide controlled by a stepper and VL53L4CD sensor."""

from MotorControl import MotorController, MotorType
from DistanceSensor import DistanceSensorController


class LinearSlide:
    """Position a stepper-driven slide using ToF feedback in millimeters."""

    def __init__(self, i2c, step_pin, dir_pin, enable_pin=None,
                 sensor_address=0x29, positive_direction=True, tolerance_mm=1,
                 max_steps=10000, min_position_mm=None, max_position_mm=None,
                 step_delay_us=500, direction_settle_us=10,
                 enable_active_low=True, motor_controller=None,
                 sensor_controller=None):
        if tolerance_mm < 0:
            raise ValueError("tolerance_mm must be non-negative")
        if max_steps <= 0:
            raise ValueError("max_steps must be greater than zero")
        if (min_position_mm is not None and max_position_mm is not None
                and min_position_mm > max_position_mm):
            raise ValueError("min_position_mm cannot exceed max_position_mm")

        self.positive_direction = bool(positive_direction)
        self.tolerance_mm = int(tolerance_mm)
        self.max_steps = int(max_steps)
        self.min_position_mm = min_position_mm
        self.max_position_mm = max_position_mm
        self.motor_controller = motor_controller or MotorController()
        self.sensor_controller = sensor_controller or DistanceSensorController()
        self._closed = False
        self._cancel_requested = False
        self.motor = self.motor_controller.create_motor(
            "linear_slide_motor", MotorType.STEPPER, "step_dir",
            enable_pin=enable_pin, step_pin=step_pin, dir_pin=dir_pin,
            enable_active_low=enable_active_low, step_delay_us=step_delay_us,
            direction_settle_us=direction_settle_us,
        )
        try:
            self.position_sensor = self.sensor_controller.create_sensor(
                "linear_slide_position", "vl53l4cd", i2c=i2c,
                address=sensor_address, timing_budget=200, inter_measurement=0,
            )
        except Exception:
            self.motor_controller.shutdown()
            raise

    def get_position(self):
        self._require_open()
        return self.position_sensor.read_distance_mm()

    def goto_position(self, position_mm):
        self._require_open()
        self._cancel_requested = False
        target_mm = int(position_mm)
        self._validate_target(target_mm)
        current_mm = self.get_position()
        for _ in range(self.max_steps):
            if self._cancel_requested:
                raise RuntimeError("Linear slide move was cancelled")
            error_mm = target_mm - current_mm
            if abs(error_mm) <= self.tolerance_mm:
                return current_mm
            direction = self.positive_direction if error_mm > 0 else not self.positive_direction
            if not self.motor.move_steps(1, direction):
                raise RuntimeError("Stepper failed while moving the linear slide")
            current_mm = self.get_position()
        raise RuntimeError(
            "Target {} mm was not reached after {} steps; last position was {} mm".format(
                target_mm, self.max_steps, current_mm))

    # Compatibility with the first implementation.
    getPosition = get_position
    gotoPosition = goto_position

    def stop(self):
        self._cancel_requested = True
        stop = getattr(self.motor, "stop", None)
        return stop() if stop else True

    def _validate_target(self, target_mm):
        if self.min_position_mm is not None and target_mm < self.min_position_mm:
            raise ValueError("target is below the configured minimum position")
        if self.max_position_mm is not None and target_mm > self.max_position_mm:
            raise ValueError("target is above the configured maximum position")

    def _require_open(self):
        if self._closed:
            raise RuntimeError("LinearSlide has been shut down")

    def shutdown(self):
        if self._closed:
            return True
        self.stop()
        sensor_result = self.sensor_controller.shutdown()
        motor_result = self.motor_controller.shutdown()
        self._closed = True
        return sensor_result is not False and motor_result is not False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.shutdown()
