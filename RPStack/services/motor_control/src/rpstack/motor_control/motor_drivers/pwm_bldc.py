"""Open-loop PWM/ESC driver for BLDC controllers with optional direction pin."""

from rpstack.motor_control import BLDCDriver


# Drive either a Pin-style output or a callable test pin.
def _write(pin, value):
    try:
        pin.value(value)
    except AttributeError:
        pin(value)


class PWMBLDCDriver(BLDCDriver):
    # Start with zero commanded speed and no PWM or direction output attached.
    def __init__(self):
        self.initialized = False
        self.speed_rpm = 0.0
        self.clockwise = True
        self.pwm = self.direction_pin = None

    # Create outputs, configure PWM frequency, and initialize the motor at zero duty.
    def initialize(self, pwm_pin, direction_pin=None, pwm_factory=None,
                   pin_factory=None, frequency_hz=20000, max_speed_rpm=10000, **_):
        if max_speed_rpm <= 0:
            raise ValueError("max_speed_rpm must be positive")
        if pwm_factory is None or pin_factory is None:
            from machine import Pin, PWM
            pwm_factory = pwm_factory or (lambda value: PWM(Pin(value)))
            pin_factory = pin_factory or (lambda value: Pin(value, Pin.OUT))
        self.pwm = pwm_factory(pwm_pin)
        self.direction_pin = pin_factory(direction_pin) if direction_pin is not None else None
        self.frequency_hz = int(frequency_hz)
        self.max_speed_rpm = float(max_speed_rpm)
        self.pwm.freq(self.frequency_hz)
        self.pwm.duty_u16(0)
        self.initialized = True
        self.set_direction(True)
        return True

    # Validate the requested RPM and map it proportionally onto PWM duty.
    def set_speed(self, rpm):
        if not self.initialized:
            raise RuntimeError("BLDC driver is not initialized")
        rpm = float(rpm)
        if rpm < 0 or rpm > self.max_speed_rpm:
            raise ValueError("rpm is outside the configured range")
        self.pwm.duty_u16(int(round(65535 * rpm / self.max_speed_rpm)))
        self.speed_rpm = rpm
        return True

    # Change the direction output only while commanded speed is zero.
    def set_direction(self, clockwise):
        if self.speed_rpm:
            raise RuntimeError("stop the motor before changing direction")
        self.clockwise = bool(clockwise)
        if self.direction_pin is not None:
            _write(self.direction_pin, int(self.clockwise))
        return True

    # Return commanded RPM; this driver does not measure actual shaft speed.
    def get_speed(self):
        return self.speed_rpm

    # Set zero PWM duty and clear the commanded speed.
    def stop(self):
        if self.pwm is not None:
            self.pwm.duty_u16(0)
        self.speed_rpm = 0.0
        return True

    # Stop the motor before releasing PWM resources and readiness.
    def shutdown(self):
        self.stop()
        if self.pwm is not None:
            self.pwm.deinit()
        self.initialized = False
        return True

    # Report commanded speed, direction, readiness, and the configured RPM limit.
    def get_status(self):
        return {"initialized": self.initialized, "speed_rpm": self.speed_rpm,
                "clockwise": self.clockwise, "max_speed_rpm": self.max_speed_rpm}
