# LinearSlide

LinearSlide is a composite service that turns an incremental motor and a linear position observer into a closed-loop **motion.position_actuator**.

## Required roles

The runtime supplies two dependencies:

| Role | Required capability |
|---|---|
| motor | motion.motion_actuator version 1, incremental mode |
| position | motion.position_observer version 1, linear, one-dimensional, metres |

~~~python
slide = LinearSlide(
    motor=stepper,
    position=carriage_position,
)
~~~

The constructor also accepts **position_observer** as the position role name for direct use.

## Control behavior

**move_to(target)**:

1. validates the target against configured travel limits;
2. reads the current PositionSample;
3. determines which motor direction reduces error;
4. commands one increment;
5. reads position again;
6. stops when error is within tolerance;
7. fails if the sample is invalid, motion is cancelled, or max_steps is reached.

The returned value is the final PositionSample in metres.

~~~python
final_sample = slide.move_to(0.100)
print(final_sample.value)
~~~

## Configuration

| Field | Meaning |
|---|---|
| positive_direction | Motor direction that increases observed position |
| tolerance_m | Allowed target error |
| max_steps | Maximum increments attempted by one move |
| min_position_m | Optional lower travel limit |
| max_position_m | Optional upper travel limit |

Travel limits and max_steps are independent safeguards.

## Lifecycle and ownership

The composite supports configure, init, start, stop, reset, and status.

Dependencies injected by PrimitiveRuntime remain owned by the supervisor. **shutdown()** stops motion but does not shut down injected services. This allows a sensor or motor capability to be shared safely.

## Operations

The canonical **component.yaml** declares:

| Operation | Purpose |
|---|---|
| observe_position | Return the current PositionSample |
| move_to | Move to an absolute target in metres |
| stop | Cancel and stop motion |
| get_position_mm | Return integer millimetres |
| goto_position_mm | Move using an integer millimetre target |

Applications and bridges should use the SI-based operations for capability interoperability. Millimetre operations are convenient at device and user-interface boundaries.

## Runtime assembly

~~~python
runtime.register(
    "lift",
    slide_manifest,
    factory=LinearSlide,
    bindings={
        "motor": "lift_motor",
        "position": "lift_position",
    },
    config={
        "positive_direction": True,
        "tolerance_m": 0.001,
        "max_steps": 10000,
    },
)
~~~

The motor can be any matching incremental actuator. The position role can be supplied by DistanceToPosition, an encoder adapter, a simulation, or a remote bridge.

## Direct hardware assembly

A direct application can supply I2C and pin values:

~~~python
slide = LinearSlide(
    i2c,
    step_pin=17,
    dir_pin=3,
    enable_pin=21,
    tolerance_mm=1,
    max_steps=10000,
)

position_mm = slide.get_position()
slide.goto_position(100)
slide.shutdown()
~~~

This constructor assembles the step_dir motor, VL53L4CD sensor, and DistanceToPosition adapter inside the composite and owns their lifecycle.

## Declarative tests

- **observe_position** reads position and verifies a valid linear sample in metres.
- **stop_motion** exercises the safe-state operation.
- **move_to_target** is a hardware test with an operator-selected target.

The hardware test requires explicit approval and verification of physical clearance and emergency power removal.

## Hardware test application

The combined stepper and VL53L4CD device application is stored at
`TestApps/linear_slide/main.py`. It uses step GPIO 17, direction GPIO 3,
enable GPIO 21, I2C SCL GPIO 4, and I2C SDA GPIO 5.

## Tests

Host-side tests use fake motor and position capabilities:

~~~bash
python -m unittest discover     -s RPStack/services/linear_slide/test     -v
~~~

## Repository layout

- `src/` contains importable modules and device startup files.
- `test/` contains host tests or hardware-test guidance.
- `package.json` maps source files to their MIP installation paths.
- `component.yaml` defines the service lifecycle, capabilities, operations, signals, and tests.
- Optional `examples/` and `tools/` directories contain development-only resources.

## MIP installation

All file sources in `package.json` are relative to this component directory. The package installs its Python modules under `/lib/rpstack/linear_slide/`, allowing applications to import `rpstack.linear_slide`.

From this component directory:

~~~bash
mpremote mip install ./package.json
~~~

From the repository root:

~~~bash
mpremote mip install RPStack/services/linear_slide/package.json
~~~

From GitHub on the development branch:

~~~bash
mpremote mip install github:ROSMicroPy/RobotPrimitivesStack/RPStack/services/linear_slide@archdef
~~~

A raw manifest URL is also supported:

~~~bash
mpremote mip install https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/archdef/RPStack/services/linear_slide/package.json
~~~
