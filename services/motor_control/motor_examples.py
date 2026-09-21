"""On-device examples using the package's real hardware drivers."""

from MotorControl import MotorController, MotorType


def stepper_example():
    controller = MotorController()
    axis = controller.create_motor(
        "axis", MotorType.STEPPER, "step_dir",
        step_pin=17, dir_pin=3, enable_pin=21,
        steps_per_revolution=200, microsteps=1,
    )
    try:
        axis.set_speed(30)
        axis.move_steps(200, True)
        axis.move_steps(200, False)
    finally:
        controller.shutdown()


def servo_example():
    controller = MotorController()
    servo = controller.create_motor(
        "servo", MotorType.SERVO, "pwm_servo",
        pin=18, min_pulse_us=500, max_pulse_us=2500,
    )
    try:
        servo.set_position(90)
    finally:
        controller.shutdown()


if __name__ == "__main__":
    stepper_example()
