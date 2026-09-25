from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest

COMPONENT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = COMPONENT_DIR.parent


from rpstack.motor_control import Motor, MotorType
from rpstack.motor_control.motor_drivers.step_dir import StepDirDriver


class FakePin:
    # Prepare a pin-level history for inspecting generated motor pulses.
    def __init__(self):
        self.values = []

    # Record each requested output level without touching hardware.
    def value(self, value):
        self.values.append(value)


class MotorControlTests(unittest.IsolatedAsyncioTestCase):
    # Verify pulse shape, direction output, and signed position accounting.
    async def test_step_dir_generates_pulses_and_tracks_position(self):
        step, direction, enable = FakePin(), FakePin(), FakePin()
        driver = StepDirDriver()
        driver.initialize(step, direction, enable, step_delay_us=1)
        self.assertTrue(await driver.move_steps(3, False))
        self.assertEqual(driver.get_position(), -3)
        self.assertEqual(step.values, [0, 1, 0, 1, 0, 1, 0, 0])
        self.assertEqual(direction.values[-1], 0)

    # Check that a later move re-enables a stopped driver and disables it afterward.
    async def test_move_reenables_driver_after_stop(self):
        step, direction, enable = FakePin(), FakePin(), FakePin()
        driver = StepDirDriver()
        driver.initialize(step, direction, enable, step_delay_us=1)
        driver.stop()
        self.assertFalse(driver.get_status()["enabled"])
        await driver.move_steps(1)
        self.assertFalse(driver.get_status()["enabled"])
        self.assertEqual(enable.values[-2:], [0, 1])

    # Ensure blocking pulse batches preserve microsecond timing without asynchronous sleeps.
    def test_blocking_batch_preserves_100us_high_and_low_without_async_sleeps(self):
        from unittest.mock import patch
        from rpstack.motor_control.motor_drivers import step_dir
        step, direction = FakePin(), FakePin()
        driver = StepDirDriver()
        driver.initialize(step, direction, step_delay_us=100)
        delays = []
        with patch.object(step_dir.time, 'sleep_us', side_effect=delays.append, create=True), \
             patch.object(step_dir.asyncio, 'sleep', side_effect=AssertionError('async sleep inside pulse run')):
            driver.move_steps_blocking(200)
        self.assertEqual(delays, [10] + [100, 100] * 200)
        self.assertEqual(step.values.count(1), 200)
        self.assertFalse(driver.enabled)

    # Verify cancellation stops between pulses and the driver supports a subsequent move.
    def test_blocking_pulses_stop_between_steps(self):
        step, direction, enable = FakePin(), FakePin(), FakePin()
        driver = StepDirDriver()
        driver.initialize(step, direction, enable, step_delay_us=1)
        with self.assertRaisesRegex(RuntimeError, "motor stopped"):
            driver.move_steps_blocking(100, False, lambda: driver.position_steps <= -3)
        self.assertEqual(driver.position_steps, -3)
        self.assertEqual(step.values.count(1), 3)
        self.assertEqual(step.values[-1], 0)
        self.assertFalse(driver.enabled)
        self.assertTrue(driver.move_steps_blocking(2, True))
        self.assertEqual(driver.position_steps, -1)
        self.assertFalse(driver.enabled)

    # Exercise service configuration, startup, movement, and shutdown with an injected driver.
    async def test_service_initializes_injected_driver(self):
        pins = [FakePin(), FakePin()]
        motor = Motor("axis", MotorType.STEPPER, StepDirDriver())
        motor.configure(dict(step_pin=pins[0], dir_pin=pins[1], step_delay_us=1))
        self.assertTrue(motor.init())
        self.assertTrue(motor.start())
        self.assertTrue(await motor.move_steps(1))
        self.assertEqual(motor.get_position(), 1)
        self.assertTrue(motor.shutdown())


if __name__ == "__main__":
    unittest.main()
