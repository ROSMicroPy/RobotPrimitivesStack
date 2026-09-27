"""Portable motor services and concrete driver factories for MicroPython."""

from rpstack.interfaces import MotionActuator, PrimitiveService


class MotorType:
    SERVO = "servo"
    STEPPER = "stepper"
    BLDC = "bldc"


class MotorDriver:
    motor_type = None

    # Require concrete drivers to prepare hardware from their configuration.
    def initialize(self, **config):
        raise NotImplementedError

    # Require concrete drivers to release or disable their hardware.
    def shutdown(self):
        raise NotImplementedError

    # Require concrete drivers to expose their operating state.
    def get_status(self):
        raise NotImplementedError


class ServoDriver(MotorDriver):
    motor_type = MotorType.SERVO

    # Define the servo driver's absolute position command.
    def set_position(self, position):
        raise NotImplementedError

    # Define how a servo driver reports its position.
    def get_position(self):
        raise NotImplementedError


class StepperDriver(MotorDriver):
    motor_type = MotorType.STEPPER

    # Define the stepper driver's relative movement operation.
    def move_steps(self, steps, direction=True):
        raise NotImplementedError

    # Define the stepper driver's speed setting in revolutions per minute.
    def set_speed(self, rpm):
        raise NotImplementedError

    # Define how a stepper driver reports its accumulated position.
    def get_position(self):
        raise NotImplementedError


class BLDCDriver(MotorDriver):
    motor_type = MotorType.BLDC

    # Define the brushless motor driver's speed command in revolutions per minute.
    def set_speed(self, rpm):
        raise NotImplementedError

    # Define the brushless motor driver's rotation direction command.
    def set_direction(self, clockwise):
        raise NotImplementedError

    # Define how a brushless driver reports speed.
    def get_speed(self):
        raise NotImplementedError


class Motor(PrimitiveService, MotionActuator):
    """One runtime-managed motor backed by one concrete driver."""

    # Bind a named motor and its type to a driver that will be initialized later.
    def __init__(self, name, motor_type, driver):
        self.name = name
        self.motor_type = motor_type
        self.driver = driver
        self.initialized = False
        self._config = {}

    # Merge and retain settings for the next hardware initialization.
    def configure(self, config=None, **kwargs):
        values = dict(config or {})
        values.update(kwargs)
        self._config = values
        return True

    # Initialize hardware once, retaining the driver's success flag.
    def init(self):
        if not self.initialized:
            self.initialized = bool(self.driver.initialize(**self._config))
        return self.initialized

    # Ensure hardware initialization has succeeded before reporting readiness.
    def start(self):
        return self.initialized or self.init()


    # Release initialized hardware and clear readiness only when shutdown succeeds.
    def shutdown(self):
        if self.initialized:
            result = bool(self.driver.shutdown())
            if result:
                self.initialized = False
            return result
        return True

    # Use the driver's stop operation when available, falling back to shutdown.
    def stop(self):
        stop = getattr(self.driver, "stop", None)
        return stop() if stop else self.shutdown()

    # Shut down and restart hardware with the saved configuration.
    def reset(self):
        self.shutdown()
        return self.init() and self.start()

    # Expose motor diagnostics through the runtime lifecycle interface.
    def status(self):
        return self.get_status()

    # Combine driver diagnostics with the motor's name, type, and readiness.
    def get_status(self):
        status = self.driver.get_status()
        status.update(name=self.name, type=self.motor_type, initialized=self.initialized)
        return status

    async def command(self, direction, amount=1):
        """Implement incremental motion capability for stepper motors."""
        self._require_type(MotorType.STEPPER)
        amount = int(amount)
        if amount < 0:
            raise ValueError("amount must be non-negative")
        return await self.driver.move_steps(amount, bool(direction))

    def command_blocking(self, direction, amount=1, cancelled=None):
        """Synchronous pulse path for a slide's dedicated worker thread."""
        self._require_type(MotorType.STEPPER)
        return self.driver.move_steps_blocking(int(amount), bool(direction), cancelled)

    # Accept absolute position commands only for servo motors.
    def set_position(self, position):
        self._require_type(MotorType.SERVO)
        return self.driver.set_position(position)

    # Read the driver position for a stepper or servo, rejecting other motor types.
    def get_position(self):
        if self.motor_type == MotorType.STEPPER:
            return self.driver.get_position()
        self._require_type(MotorType.SERVO)
        return self.driver.get_position()

    # Return the accumulated stepper position after checking the motor type.
    def get_stepper_position(self):
        self._require_type(MotorType.STEPPER)
        return self.driver.get_position()

    # Delegate asynchronous relative movement to a compatible stepper driver.
    async def move_steps(self, steps, direction=True):
        self._require_type(MotorType.STEPPER)
        return await self.driver.move_steps(steps, direction)

    # Allow RPM commands only for stepper and brushless motors.
    def set_speed(self, rpm):
        if self.motor_type not in (MotorType.STEPPER, MotorType.BLDC):
            raise TypeError("Motor {} does not support speed control".format(self.name))
        return self.driver.set_speed(rpm)

    # Read the stored stepper RPM or ask the brushless driver for its speed.
    def get_speed(self):
        if self.motor_type == MotorType.STEPPER:
            return self.driver.speed_rpm
        self._require_type(MotorType.BLDC)
        return self.driver.get_speed()

    # Forward rotation direction changes only to brushless motors.
    def set_direction(self, clockwise):
        self._require_type(MotorType.BLDC)
        return self.driver.set_direction(clockwise)

    # Reject commands that do not belong to this motor's capabilities.
    def _require_type(self, expected):
        if self.motor_type != expected:
            raise TypeError("Motor {} is not a {} motor".format(self.name, expected))




__all__ = ("BLDCDriver", "Motor", "MotorDriver", "MotorType",
           "ServoDriver", "StepperDriver")
