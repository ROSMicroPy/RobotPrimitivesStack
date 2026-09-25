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

## Control behavior

`slide.init()` is stationary. Call `await slide.calibrate(steps=1000)` explicitly
to move that many steps in each direction and
measure before/between/after the runs. The runtime calls this through its optional
`lifecycle.calibrate` phase and reserves the slide and its dependencies.
It infers `positive_direction` and `steps_per_mm`, and returns a report with the
three positions and signed displacements. Too little motion, inconsistent return
travel, invalid readings, or same-direction responses fail calibration. A failed
calibration leaves target moves disabled.

Calibration moves hardware. Choose a step count with clearance in both directions;
position limits cannot bound this test before the scale is known. `max_steps`
bounds each calibration leg. Calibration is in-memory and must be repeated after
service reset, restart, or changing mechanics/microstep settings.

`await slide.move_to(target)` requires successful calibration and:

1. validates the target in metres against configured travel limits;
2. measures the current position and calculates steps for 96% of the error;
3. starts a fresh worker thread to execute that batch;
4. waits for the worker to finish, then measures the actual position;
5. updates the step estimate and repeats until within `tolerance_m`.

At least one step is attempted for errors outside tolerance. `max_steps` bounds
the entire target move, excluding initialization. Invalid readings, repeated
lack of motion, movement away from the target, and cancellation stop the move.
Concurrent motion requests are rejected. Cancellation waits for the worker to
exit before releasing the slide for another operation.

The STEP/DIR motor uses a blocking pulse loop on the worker, preserving configured
pulse timing without asyncio scheduling between pulses. Synchronous incremental
motors are stepped on the worker as well. Async-only capability bridges continue
on the main event loop; they need `command_blocking(direction, steps, cancelled)`
to support threaded pulse generation.

The returned value is the final PositionSample in metres. `status()` includes
`calibrated`, `positive_direction`, and `steps_per_mm`.

~~~python
slide.init()
await slide.calibrate(steps=1000)
final_sample = await slide.move_to(0.100)
print(final_sample.value)
~~~

## Configuration

| Field | Meaning |
|---|---|
| positive_direction | Initial direction setting; replaced by calibration |
| tolerance_m | Allowed target error |
| max_steps | Maximum increments attempted by one target move |
| no_motion_sample_limit | Consecutive batches without observed motion before failure |
| min_position_m | Optional lower travel limit |
| max_position_m | Optional upper travel limit |

Travel limits and max_steps are independent safeguards.

## Lifecycle and ownership

The composite supports configure, init, calibrate, start, stop, reset, and status.

Dependencies injected by NodeRuntime remain owned by the supervisor. **shutdown()** stops motion but does not shut down injected services. This allows a sensor or motor capability to be shared safely.

## Operations

The canonical **component.yaml** declares:

| Operation | Purpose |
|---|---|
| calibrate | Explicit forward/reverse distance calibration |
| observe_position | Return the current PositionSample |
| move_to | Move to an absolute target in metres |
| stop | Cancel and stop motion |

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

## Declarative tests

- **observe_position** reads position and verifies a valid linear sample in metres.
- **stop_motion** exercises the safe-state operation.
- **move_to_target** is a hardware test with an operator-selected target.

The hardware test requires explicit approval and verification of physical clearance and emergency power removal.

## Hardware test application

The combined stepper and VL53L4CD device application is stored at
`examples/linear_slide/main.py`. It uses step GPIO 17, direction GPIO 3,
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
