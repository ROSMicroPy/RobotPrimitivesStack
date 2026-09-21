"""Portable motor services and concrete driver factories for MicroPython."""

try:
    from importlib import import_module as _import_module
except ImportError:
    def _import_module(name):
        """Import and return a nested module without requiring importlib."""
        return __import__(name, None, None, ("*",))

try:
    from rpstack.interfaces import MotionActuator, PrimitiveService
except ImportError:  # Monorepo/host execution before mip packaging.
    from rpstack.interfaces import MotionActuator, PrimitiveService


class MotorType:
    SERVO = "servo"
    STEPPER = "stepper"
    BLDC = "bldc"


class MotorDriver:
    motor_type = None

    def initialize(self, **config):
        raise NotImplementedError

    def shutdown(self):
        raise NotImplementedError

    def get_status(self):
        raise NotImplementedError


class ServoDriver(MotorDriver):
    motor_type = MotorType.SERVO

    def set_position(self, position):
        raise NotImplementedError

    def get_position(self):
        raise NotImplementedError


class StepperDriver(MotorDriver):
    motor_type = MotorType.STEPPER

    def move_steps(self, steps, direction=True):
        raise NotImplementedError

    def set_speed(self, rpm):
        raise NotImplementedError

    def get_position(self):
        raise NotImplementedError


class BLDCDriver(MotorDriver):
    motor_type = MotorType.BLDC

    def set_speed(self, rpm):
        raise NotImplementedError

    def set_direction(self, clockwise):
        raise NotImplementedError

    def get_speed(self):
        raise NotImplementedError


class Motor(PrimitiveService, MotionActuator):
    """One runtime-managed motor backed by one concrete driver."""

    def __init__(self, name, motor_type, driver):
        self.name = name
        self.motor_type = motor_type
        self.driver = driver
        self.initialized = False
        self._config = {}

    def configure(self, config=None, **kwargs):
        values = dict(config or {})
        values.update(kwargs)
        self._config = values
        return True

    def init(self):
        if not self.initialized:
            self.initialized = bool(self.driver.initialize(**self._config))
        return self.initialized

    def start(self):
        return self.initialized or self.init()

    def initialize(self, **config):
        """Compatibility entry point combining configure/init/start."""
        return self.configure(config) and self.init() and self.start()

    def shutdown(self):
        if self.initialized:
            result = bool(self.driver.shutdown())
            if result:
                self.initialized = False
            return result
        return True

    def stop(self):
        stop = getattr(self.driver, "stop", None)
        return stop() if stop else self.shutdown()

    def reset(self):
        self.shutdown()
        return self.init() and self.start()

    def status(self):
        return self.get_status()

    def get_status(self):
        status = self.driver.get_status()
        status.update(name=self.name, type=self.motor_type, initialized=self.initialized)
        return status

    def command(self, direction, amount=1):
        """Implement incremental motion capability for stepper motors."""
        self._require_type(MotorType.STEPPER)
        amount = int(amount)
        if amount < 0:
            raise ValueError("amount must be non-negative")
        return self.driver.move_steps(amount, bool(direction))

    def set_position(self, position):
        self._require_type(MotorType.SERVO)
        return self.driver.set_position(position)

    def get_position(self):
        if self.motor_type == MotorType.STEPPER:
            return self.driver.get_position()
        self._require_type(MotorType.SERVO)
        return self.driver.get_position()

    def get_stepper_position(self):
        self._require_type(MotorType.STEPPER)
        return self.driver.get_position()

    def move_steps(self, steps, direction=True):
        self._require_type(MotorType.STEPPER)
        return self.driver.move_steps(steps, direction)

    def set_speed(self, rpm):
        if self.motor_type not in (MotorType.STEPPER, MotorType.BLDC):
            raise TypeError("Motor {} does not support speed control".format(self.name))
        return self.driver.set_speed(rpm)

    def get_speed(self):
        if self.motor_type == MotorType.STEPPER:
            return self.driver.speed_rpm
        self._require_type(MotorType.BLDC)
        return self.driver.get_speed()

    def set_direction(self, clockwise):
        self._require_type(MotorType.BLDC)
        return self.driver.set_direction(clockwise)

    def _require_type(self, expected):
        if self.motor_type != expected:
            raise TypeError("Motor {} is not a {} motor".format(self.name, expected))


class MotorController:
    """Compatibility factory; runtime manifests should create motors directly."""

    def __init__(self, driver_package="rpstack.motor_control.motor_drivers"):
        self.driver_package = driver_package
        self.motors = {}
        self._driver_cache = {}

    def _load_driver(self, driver_name):
        if driver_name in self._driver_cache:
            return self._driver_cache[driver_name]
        module = _import_module("{}.{}".format(self.driver_package, driver_name))
        driver_class = getattr(module, "DRIVER_CLASS", None)
        if driver_class is None:
            raise ImportError("{}.{} does not export DRIVER_CLASS".format(self.driver_package, driver_name))
        self._driver_cache[driver_name] = driver_class
        return driver_class

    def create_motor(self, name, motor_type, driver_name=None, driver_class=None, **config):
        if name in self.motors:
            raise ValueError("Motor {} already exists".format(name))
        if driver_class is None:
            if not driver_name:
                raise ValueError("driver_name or driver_class is required")
            driver_class = self._load_driver(driver_name)
        driver = driver_class()
        if getattr(driver, "motor_type", None) != motor_type:
            raise TypeError("Driver is not compatible with {} motors".format(motor_type))
        motor = Motor(name, motor_type, driver)
        if not motor.initialize(**config):
            raise RuntimeError("Driver failed to initialize motor {}".format(name))
        self.motors[name] = motor
        return motor

    def get_motor(self, name):
        return self.motors.get(name)

    def remove_motor(self, name):
        motor = self.motors.pop(name, None)
        return motor.shutdown() if motor else False

    def list_motors(self):
        return [motor.get_status() for motor in self.motors.values()]

    def shutdown(self):
        success = True
        for motor in tuple(self.motors.values()):
            try:
                success = motor.shutdown() and success
            except Exception:
                success = False
        self.motors.clear()
        return success


__all__ = ("BLDCDriver", "Motor", "MotorController", "MotorDriver", "MotorType",
           "ServoDriver", "StepperDriver")
