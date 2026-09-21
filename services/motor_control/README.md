# MotorControl

Reusable MicroPython motor interfaces and hardware drivers. This repository is
a generic component package; it contains no Rube Goldberg system sequencing.

Included drivers:

- `step_dir`: STEP/DIR/ENABLE controllers such as A4988, DRV8825, and TMC modules.
- `pwm_servo`: hobby servo PWM with configurable angle and pulse ranges.
- `pwm_bldc`: open-loop PWM/ESC output with optional direction control.

```python
from MotorControl import MotorController, MotorType

motors = MotorController()
axis = motors.create_motor(
    "axis",
    MotorType.STEPPER,
    "step_dir",
    step_pin=17,
    dir_pin=3,
    enable_pin=21,
)
axis.move_steps(200, True)
motors.shutdown()
```

Install from the repository root using MicroPython `mip`:

```python
import mip
mip.install("github:ROSMicroPy/mpylib_MotorControl")
```

`component.yaml` is the framework-facing contract. `package.json` is the mip
transport manifest. Pins and timing are instance data supplied by URDF or a
platform adapter rather than embedded in this package.

The public API lives in `__init__.py`. The mip manifest installs every file
under `lib/MotorControl/`, including `MotorControl/motor_drivers`, so the
component exposes no duplicate flat module or top-level driver namespace.
