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
await motor.command(direction=True, amount=200)
motor.stop()
~~~

Run these examples inside an async function on the application event loop.

**amount** is a number of driver increments. Mechanism geometry and absolute positioning belong in an adapter or composite service.

## Direct construction

~~~python
from rpstack.motor_control import Motor, MotorType
from rpstack.motor_control.motor_drivers.step_dir import StepDirDriver

axis = Motor("lift_motor", MotorType.STEPPER, StepDirDriver())
axis.configure(dict(step_pin=17, dir_pin=3, enable_pin=21, step_delay_us=500))
axis.init()
axis.start()
try:
    await axis.command(True, 200)
finally:
    axis.shutdown()
~~~

Manifest deployments let the node runtime construct the service and own its lifecycle.

## Lifecycle

The Motor service supports configure, init, start, stop, reset, and status.

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

The node runtime rejects an operation that is not available for the registered implementation.

## Tests and safety

**report_status** is automatic and does not command motion.

**one_increment_each_direction** is a hardware test. It requires clearance in both directions and explicit operator approval before the test runner executes it.

## Packaging

**package.json** installs MotorControl, all three driver modules, and the RPInterfaces dependency.

## Repository layout

- `src/` contains importable modules and device startup files.
- `test/` contains host tests or hardware-test guidance.
- `package.json` maps source files to their MIP installation paths.
- `component.yaml` defines the service lifecycle, capabilities, operations, signals, and tests.
- Optional `examples/` and `tools/` directories contain development-only resources.

## MIP installation

All file sources in `package.json` are relative to this component directory. The package installs its Python modules under `/lib/rpstack/motor_control/`, allowing applications to import `rpstack.motor_control`.

From this component directory:

~~~bash
mpremote mip install ./package.json
~~~

From the repository root:

~~~bash
mpremote mip install RPStack/services/motor_control/package.json
~~~

From GitHub on the development branch:

~~~bash
mpremote mip install github:ROSMicroPy/RobotPrimitivesStack/RPStack/services/motor_control@archdef
~~~

A raw manifest URL is also supported:

~~~bash
mpremote mip install https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/archdef/RPStack/services/motor_control/package.json
~~~
