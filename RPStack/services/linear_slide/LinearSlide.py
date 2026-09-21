"""Capability-oriented closed-loop linear-slide composite service."""

try:
    from RPInterfaces import PositionActuator, PrimitiveService
except ImportError:
    from RPStack.services.interfaces import PositionActuator, PrimitiveService


class LinearSlide(PrimitiveService, PositionActuator):
    """Coordinate a motion actuator and linear position observer.

    ``motor`` and ``position_observer`` are the preferred runtime-bound roles.
    The pin/I2C arguments remain as a compatibility path for existing devices;
    only that path constructs and owns concrete component services.
    """

    def __init__(self, i2c=None, step_pin=None, dir_pin=None, enable_pin=None,
                 sensor_address=0x29, positive_direction=True, tolerance_mm=1,
                 max_steps=10000, min_position_mm=None, max_position_mm=None,
                 step_delay_us=500, direction_settle_us=10,
                 enable_active_low=True, motor_controller=None,
                 sensor_controller=None, motor=None, position_observer=None,
                 position=None):
        if tolerance_mm < 0:
            raise ValueError("tolerance_mm must be non-negative")
        if max_steps <= 0:
            raise ValueError("max_steps must be greater than zero")
        if (min_position_mm is not None and max_position_mm is not None
                and min_position_mm > max_position_mm):
            raise ValueError("min_position_mm cannot exceed max_position_mm")
        if position is not None:
            if position_observer is not None:
                raise ValueError("use position or position_observer, not both")
            position_observer = position
        if (motor is None) != (position_observer is None):
            raise ValueError("motor and position_observer must be supplied together")

        self.positive_direction = bool(positive_direction)
        self.tolerance_m = float(tolerance_mm) / 1000.0
        self.max_steps = int(max_steps)
        self.min_position_m = _mm_to_m(min_position_mm)
        self.max_position_m = _mm_to_m(max_position_mm)
        self.motor_controller = None
        self.sensor_controller = None
        self._owns_dependencies = motor is None
        self._closed = False
        self._cancel_requested = False
        self._target_m = None

        if motor is not None:
            self.motor = motor
            self.position_observer = position_observer
            return

        if i2c is None or step_pin is None or dir_pin is None:
            raise ValueError(
                "runtime-bound motor and position_observer, or legacy i2c/step_pin/dir_pin, are required"
            )

        # Compatibility assembly for existing deployments. Imports are lazy so
        # a runtime-bound composite has no dependency on concrete packages.
        from MotorControl import MotorController, MotorType
        from DistanceSensor import DistanceSensorController
        try:
            from DistanceToPosition import DistanceToPositionAdapter
        except ImportError:
            from RPStack.services.distance_to_position import DistanceToPositionAdapter

        self.motor_controller = motor_controller or MotorController()
        self.sensor_controller = sensor_controller or DistanceSensorController()
        self.motor = self.motor_controller.create_motor(
            "linear_slide_motor", MotorType.STEPPER, "step_dir",
            enable_pin=enable_pin, step_pin=step_pin, dir_pin=dir_pin,
            enable_active_low=enable_active_low, step_delay_us=step_delay_us,
            direction_settle_us=direction_settle_us,
        )
        try:
            distance_sensor = self.sensor_controller.create_sensor(
                "linear_slide_distance", "vl53l4cd", i2c=i2c,
                address=sensor_address, timing_budget=200, inter_measurement=0,
            )
            self.position_observer = DistanceToPositionAdapter(
                distance_sensor,
                reference_frame="linear_slide.carriage",
                min_position_m=self.min_position_m,
                max_position_m=self.max_position_m,
            )
            self.position_observer.start()
        except Exception:
            self.motor_controller.shutdown()
            raise

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
            "position": self.position().as_dict() if not self._closed else None,
        }

    def position(self):
        self._require_open()
        sample = self.position_observer.position()
        if sample.kind != "linear" or sample.unit != "m":
            raise TypeError("position_observer must return linear positions in metres")
        return sample

    def move_to(self, target):
        """Move to ``target`` metres and return the final PositionSample."""
        self._require_open()
        target_m = float(target)
        self._validate_target(target_m)
        self._cancel_requested = False
        self._target_m = target_m
        current = self.position()

        for _ in range(self.max_steps):
            if self._cancel_requested:
                raise RuntimeError("Linear slide move was cancelled")
            if not current.valid:
                raise RuntimeError("Position observer returned an invalid sample")
            error_m = target_m - current.value
            if abs(error_m) <= self.tolerance_m:
                self._target_m = None
                return current
            direction = self.positive_direction if error_m > 0 else not self.positive_direction
            if not self.motor.command(direction, 1):
                raise RuntimeError("Motion actuator failed while moving the linear slide")
            current = self.position()

        self._target_m = None
        raise RuntimeError(
            "Target {} m was not reached after {} increments; last position was {} m".format(
                target_m, self.max_steps, current.value))

    def get_position(self):
        """Compatibility API returning integer millimetres."""
        return int(round(self.position().value * 1000.0))

    def goto_position(self, position_mm):
        """Compatibility API accepting and returning millimetres."""
        return int(round(self.move_to(float(position_mm) / 1000.0).value * 1000.0))

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
        dependency_result = True
        if self._owns_dependencies:
            sensor_result = self.sensor_controller.shutdown()
            controller_result = self.motor_controller.shutdown()
            dependency_result = sensor_result is not False and controller_result is not False
        self._closed = True
        return motor_result is not False and dependency_result

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.shutdown()


def _mm_to_m(value):
    return None if value is None else float(value) / 1000.0
