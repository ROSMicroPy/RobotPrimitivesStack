#!/usr/bin/env python3
"""Move the linear-slide stepper 5,000 steps out and back.

Pin numbers are MicroPython GPIO numbers, not physical header pin numbers.
"""

import time

# MotorControl is installed into the MicroPython library path by mip.
from rpstack.motor_control import MotorController, MotorType


ENABLE_PIN = 21
STEP_PIN = 17
DIR_PIN = 3
TRAVEL_STEPS = 5_000
STEP_DELAY_US = 500
DIRECTION_SETTLE_US = 10
TURNAROUND_DELAY_MS = 500


def main():
    controller = MotorController()
    slide = controller.create_motor(
        "linear_slide",
        MotorType.STEPPER,
        "step_dir",
        enable_pin=ENABLE_PIN,
        step_pin=STEP_PIN,
        dir_pin=DIR_PIN,
        enable_active_low=True,
        step_delay_us=STEP_DELAY_US,
        direction_settle_us=DIRECTION_SETTLE_US,
    )

    try:
        print("Moving forward {} steps".format(TRAVEL_STEPS))
        if not slide.move_steps(TRAVEL_STEPS, True):
            raise RuntimeError("Forward movement failed")

        time.sleep_ms(TURNAROUND_DELAY_MS)

        print("Moving backward {} steps".format(TRAVEL_STEPS))
        if not slide.move_steps(TRAVEL_STEPS, False):
            raise RuntimeError("Backward movement failed")

        print("Test complete; position = {} steps".format(
            slide.get_stepper_position()
        ))
    finally:
        controller.shutdown()


if __name__ == "__main__":
    main()
