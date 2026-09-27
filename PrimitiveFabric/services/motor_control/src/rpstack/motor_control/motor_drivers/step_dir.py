"""STEP/DIR driver for A4988, DRV8825, TMC and compatible controllers."""

import time

from rpstack.support import asyncio

from rpstack.motor_control import StepperDriver


# Write a digital level through a hardware pin or callable substitute.
def _write(pin, value):
    try:
        pin.value(value)
    except AttributeError:
        pin(value)


class StepDirDriver(StepperDriver):
    # Prepare pulse timing, step accounting, and enable polarity before pins are assigned.
    def __init__(self):
        self.initialized = False
        self.position_steps = 0
        self.speed_rpm = 0.0
        self.step_delay_us = 500
        self.direction_settle_us = 10
        self.steps_per_revolution = 200
        self.microsteps = 1
        self.enable_active_low = True
        self.enabled = False
        self.step_pin = self.dir_pin = self.enable_pin = None

    # Validate timing and geometry, bind output pins, and begin with the driver disabled.
    def initialize(self, step_pin, dir_pin, enable_pin=None, pin_factory=None,
                   enable_active_low=True, step_delay_us=500,
                   direction_settle_us=10, steps_per_revolution=200, microsteps=1,
                   initial_position_steps=0, **_):
        if step_delay_us < 1 or direction_settle_us < 0:
            raise ValueError("pulse timing must be non-negative")
        if steps_per_revolution < 1 or microsteps < 1:
            raise ValueError("steps_per_revolution and microsteps must be positive")
        if pin_factory is None and any(isinstance(pin, int) for pin in (step_pin, dir_pin, enable_pin) if pin is not None):
            from machine import Pin
            pin_factory = lambda number: Pin(number, Pin.OUT)
        self.step_pin = pin_factory(step_pin) if isinstance(step_pin, int) else step_pin
        self.dir_pin = pin_factory(dir_pin) if isinstance(dir_pin, int) else dir_pin
        self.enable_pin = pin_factory(enable_pin) if isinstance(enable_pin, int) else enable_pin
        self.enable_active_low = bool(enable_active_low)
        self.step_delay_us = int(step_delay_us)
        self.direction_settle_us = int(direction_settle_us)
        self.steps_per_revolution = int(steps_per_revolution)
        self.microsteps = int(microsteps)
        self.position_steps = int(initial_position_steps)
        _write(self.step_pin, 0)
        self._set_enabled(False)
        self.initialized = True
        return True

    # Apply the configured enable polarity and mirror the resulting logical state.
    def _set_enabled(self, enabled):
        if self.enable_pin is not None:
            _write(self.enable_pin, int(not enabled) if self.enable_active_low else int(enabled))
        self.enabled = bool(enabled)

    # Emit asynchronous step pulses, track signed position, and always disable outputs
    # afterward.
    async def move_steps(self, steps, direction=True):
        if not self.initialized:
            raise RuntimeError("step/dir driver is not initialized")
        steps = int(steps)
        if steps < 0:
            steps, direction = -steps, not direction
        self._set_enabled(True)
        _write(self.dir_pin, int(bool(direction)))
        try:
            await asyncio.sleep(self.direction_settle_us / 1000000.0)
            for _ in range(steps):
                if not self.enabled:
                    raise RuntimeError("motor stopped")
                _write(self.step_pin, 1)
                self.position_steps += 1 if direction else -1
                await asyncio.sleep(self.step_delay_us / 1000000.0)
                _write(self.step_pin, 0)
                await asyncio.sleep(self.step_delay_us / 1000000.0)
            return True
        finally:
            _write(self.step_pin, 0)
            self._set_enabled(False)

    def move_steps_blocking(self, steps, direction=True, cancelled=None):
        """Generate timed pulses without involving the async scheduler."""
        if not self.initialized:
            raise RuntimeError("step/dir driver is not initialized")
        steps = int(steps)
        if steps < 0:
            steps, direction = -steps, not direction

        # Use native microsecond sleeps where available, with a seconds-based host fallback.
        def delay(microseconds):
            if hasattr(time, "sleep_us"):
                time.sleep_us(microseconds)
            else:
                time.sleep(microseconds / 1000000.0)

        try:
            if cancelled and cancelled():
                raise RuntimeError("motor stopped")
            self._set_enabled(True)
            _write(self.dir_pin, int(bool(direction)))
            delay(self.direction_settle_us)
            for _ in range(steps):
                if not self.enabled or (cancelled and cancelled()):
                    raise RuntimeError("motor stopped")
                _write(self.step_pin, 1)
                self.position_steps += 1 if direction else -1
                delay(self.step_delay_us)
                _write(self.step_pin, 0)
                delay(self.step_delay_us)
            return True
        finally:
            _write(self.step_pin, 0)
            self._set_enabled(False)

    # Convert RPM and microstep geometry into the delay for each pulse half-cycle.
    def set_speed(self, rpm):
        rpm = float(rpm)
        if rpm <= 0:
            raise ValueError("rpm must be greater than zero")
        self.speed_rpm = rpm
        pulses_per_minute = rpm * self.steps_per_revolution * self.microsteps
        self.step_delay_us = max(1, int(30000000 / pulses_per_minute))
        return True

    # Return accumulated commanded steps; no encoder feedback is involved.
    def get_position(self):
        return self.position_steps

    # Hold the step output low and disable the driver to interrupt further pulses.
    def stop(self):
        if self.step_pin is not None:
            _write(self.step_pin, 0)
        self._set_enabled(False)
        return True

    # Disable pulse outputs and require reinitialization before future motion.
    def shutdown(self):
        if self.step_pin is not None:
            _write(self.step_pin, 0)
        self._set_enabled(False)
        self.initialized = False
        return True

    # Expose commanded position, speed, pulse timing, and driver enable state.
    def get_status(self):
        return {"initialized": self.initialized, "position_steps": self.position_steps,
                "speed_rpm": self.speed_rpm, "step_delay_us": self.step_delay_us,
                "enabled": self.enabled}
