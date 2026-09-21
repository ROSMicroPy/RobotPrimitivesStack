# MotorControl

MotorControl provides runtime-managed motor services with selectable hardware implementations.

## Included implementations

### step_dir

For STEP/DIR controllers such as A4988, DRV8825, and compatible TMC modules.

Configuration includes:

- step_pin
- dir_pin
- enable_pin
- enable_active_low
- step_delay_us
- direction_settle_us
- steps_per_revolution
- microsteps

This implementation provides:

~~~text
motion.motion_actuator version 1
mode: incremental
~~~

### pwm_servo

For hobby servos controlled by PWM. It supports setting and reading driver position.

### pwm_bldc

For open-loop PWM or ESC control with optional direction output. It supports speed, direction, and stop operations.

## Service model

**Motor** wraps one concrete driver and supplies lifecycle, status, safe stop, and type-checked operations.

Motor types are:

~~~python
MotorType.STEPPER
MotorType.SERVO
MotorType.BLDC
~~~

The selected implementation determines which manifest operations and capabilities are available.

## Incremental motion capability

A stepper instance exposes:

~~~python
motor.command(direction=True, amount=200)
motor.stop()
~~~

**amount** is a number of driver increments. Mechanism geometry and absolute positioning belong in an adapter or composite service.

## Direct construction

~~~python
from MotorControl import MotorController, MotorType

motors = MotorController()

axis = motors.create_motor(
    "lift_motor",
    MotorType.STEPPER,
    "step_dir",
    step_pin=17,
    dir_pin=3,
    enable_pin=21,
    step_delay_us=500,
)

axis.command(True, 200)
axis.stop()
motors.shutdown()
~~~

**MotorController** is a convenient factory for direct applications. PrimitiveRuntime applications can provide a factory that constructs a configured Motor instance.

## Lifecycle

The Motor service supports configure, init, start, stop, reset, and status. **initialize()** combines configuration and initialization for direct use.

Stopping calls the concrete driver stop operation when available. Shutdown releases driver resources.

## Manifest operations

The canonical **component.yaml** describes:

| Operation | Implementations |
|---|---|
| command | step_dir |
| stop | all |
| set_position | pwm_servo |
| set_speed | step_dir, pwm_bldc |
| status | all |

PrimitiveRuntime rejects an operation that is not available for the registered implementation.

## Tests and safety

**report_status** is automatic and does not command motion.

**one_increment_each_direction** is a hardware test. It requires clearance in both directions and explicit operator approval before the test runner executes it.

## Packaging

**package.json** installs MotorControl, all three driver modules, and the RPInterfaces dependency.
