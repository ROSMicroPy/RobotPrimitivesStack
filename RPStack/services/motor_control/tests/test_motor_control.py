import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, ".")

spec = importlib.util.spec_from_file_location(
    "MotorControl", Path("__init__.py"), submodule_search_locations=["."])
motor_control = importlib.util.module_from_spec(spec)
sys.modules["MotorControl"] = motor_control
spec.loader.exec_module(motor_control)

MotorController = motor_control.MotorController
MotorType = motor_control.MotorType
from MotorControl.motor_drivers.step_dir import StepDirDriver


class FakePin:
    def __init__(self):
        self.values = []

    def value(self, value):
        self.values.append(value)


class MotorControlTests(unittest.TestCase):
    def test_step_dir_generates_pulses_and_tracks_position(self):
        step, direction, enable = FakePin(), FakePin(), FakePin()
        driver = StepDirDriver()
        driver.initialize(step, direction, enable, step_delay_us=1)
        self.assertTrue(driver.move_steps(3, False))
        self.assertEqual(driver.get_position(), -3)
        self.assertEqual(step.values, [0, 1, 0, 1, 0, 1, 0])
        self.assertEqual(direction.values[-1], 0)

    def test_controller_accepts_explicit_driver_class(self):
        pins = [FakePin(), FakePin()]
        controller = MotorController()
        motor = controller.create_motor("axis", MotorType.STEPPER,
                                        driver_class=StepDirDriver,
                                        step_pin=pins[0], dir_pin=pins[1],
                                        step_delay_us=1)
        self.assertTrue(motor.move_steps(1))
        self.assertEqual(motor.get_position(), 1)
        self.assertTrue(controller.shutdown())


if __name__ == "__main__":
    unittest.main()
