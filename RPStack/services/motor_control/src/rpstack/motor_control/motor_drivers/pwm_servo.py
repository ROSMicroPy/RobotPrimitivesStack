"""PWM hobby-servo driver with configurable pulse and angle ranges."""

from rpstack.motor_control import ServoDriver


class PWMServoDriver(ServoDriver):
    def __init__(self):
        self.initialized = False
        self.position_degrees = 0.0
        self.pwm = None

    def initialize(self, pin, pwm_factory=None, frequency_hz=50, min_angle=0,
                   max_angle=180, min_pulse_us=500, max_pulse_us=2500, **_):
        if max_angle <= min_angle or max_pulse_us <= min_pulse_us:
            raise ValueError("maximum servo values must exceed minimum values")
        if pwm_factory is None:
            from machine import Pin, PWM
            pwm_factory = lambda value: PWM(Pin(value))
        self.pwm = pwm_factory(pin) if isinstance(pin, int) else pwm_factory(pin)
        self.frequency_hz = int(frequency_hz)
        self.min_angle = float(min_angle)
        self.max_angle = float(max_angle)
        self.min_pulse_us = int(min_pulse_us)
        self.max_pulse_us = int(max_pulse_us)
        self.pwm.freq(self.frequency_hz)
        self.initialized = True
        self.set_position(self.min_angle)
        return True

    def set_position(self, position):
        if not self.initialized:
            raise RuntimeError("servo driver is not initialized")
        position = float(position)
        if position < self.min_angle or position > self.max_angle:
            raise ValueError("position is outside the configured servo range")
        ratio = (position - self.min_angle) / (self.max_angle - self.min_angle)
        pulse_us = self.min_pulse_us + ratio * (self.max_pulse_us - self.min_pulse_us)
        period_us = 1000000.0 / self.frequency_hz
        self.pwm.duty_u16(int(round(65535 * pulse_us / period_us)))
        self.position_degrees = position
        return True

    def get_position(self):
        return self.position_degrees

    def shutdown(self):
        if self.pwm is not None:
            self.pwm.deinit()
        self.initialized = False
        return True

    def get_status(self):
        return {"initialized": self.initialized, "position_degrees": self.position_degrees,
                "frequency_hz": self.frequency_hz}


DRIVER_CLASS = PWMServoDriver
