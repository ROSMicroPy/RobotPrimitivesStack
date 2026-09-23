from pathlib import Path
import sys
import unittest

COMPONENT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = COMPONENT_DIR.parent
sys.path.insert(0, str(SERVICES_DIR / "interfaces" / "src"))
sys.path.insert(0, str(COMPONENT_DIR / "src"))

for runtime_src in (SERVICES_DIR.parent / "runtime").glob("*/src"):
    sys.path.insert(0, str(runtime_src))

from rpstack.motor_control import MotorController, MotorType
from rpstack.motor_control.motor_drivers.step_dir import StepDirDriver


class FakePin:
    def __init__(self):
        self.values = []

    def value(self, value):
        self.values.append(value)


class MotorControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_step_dir_generates_pulses_and_tracks_position(self):
        step, direction, enable = FakePin(), FakePin(), FakePin()
        driver = StepDirDriver()
        driver.initialize(step, direction, enable, step_delay_us=1)
        self.assertTrue(await driver.move_steps(3, False))
        self.assertEqual(driver.get_position(), -3)
        self.assertEqual(step.values, [0, 1, 0, 1, 0, 1, 0, 0])
        self.assertEqual(direction.values[-1], 0)

    async def test_move_reenables_driver_after_stop(self):
        step, direction, enable = FakePin(), FakePin(), FakePin()
        driver = StepDirDriver()
        driver.initialize(step, direction, enable, step_delay_us=1)
        driver.stop()
        self.assertFalse(driver.get_status()["enabled"])
        await driver.move_steps(1)
        self.assertFalse(driver.get_status()["enabled"])
        self.assertEqual(enable.values[-2:], [0, 1])

    async def test_controller_accepts_explicit_driver_class(self):
        pins = [FakePin(), FakePin()]
        controller = MotorController()
        motor = controller.create_motor("axis", MotorType.STEPPER,
                                        driver_class=StepDirDriver,
                                        step_pin=pins[0], dir_pin=pins[1],
                                        step_delay_us=1)
        self.assertTrue(await motor.move_steps(1))
        self.assertEqual(motor.get_position(), 1)
        self.assertTrue(controller.shutdown())


if __name__ == "__main__":
    unittest.main()
