# RPInterfaces

RPInterfaces defines the hardware-independent contracts shared by Primitive Services, composites, bridges, simulations, and test doubles.

The package installs as **rpstack.interfaces** and avoids CPython-only dependencies.

## Lifecycle contract

**PrimitiveService** defines the runtime lifecycle:

~~~python
configure(config)
init()
start()
stop()
reset()
status()
~~~

A service manifest maps lifecycle stages to implementation methods. Functional capability methods remain separate from lifecycle methods.

## Measurements

**Measurement** is the base scalar measurement. It carries:

- value;
- unit;
- timestamp_ns;
- valid;
- quality from 0.0 to 1.0;
- reference_frame.

**DistanceSample** represents distance along a sensing ray.

**PositionSample** adds a **kind** field:

- linear values use metres;
- angular values use radians.

~~~python
from rpstack.interfaces import PositionSample

sample = PositionSample(
    PositionSample.LINEAR,
    0.100,
    "m",
    "lift.base",
    valid=True,
    quality=0.95,
)
~~~

**as_dict()** returns a transport-friendly mapping.

## Capability contracts

### DistanceObserver

~~~python
sample = observer.distance()
~~~

Returns a **DistanceSample** in metres.

Interface identifier:

~~~text
sensing.distance_observer version 1
~~~

### PositionObserver

~~~python
sample = observer.position()
~~~

Returns a linear or angular **PositionSample** in canonical units.

Interface identifier:

~~~text
motion.position_observer version 1
~~~

### MotionActuator

~~~python
actuator.command(direction=True, amount=1)
actuator.stop()
~~~

Represents relative motion. Manifests add semantic descriptors such as **mode: incremental**.

Interface identifier:

~~~text
motion.motion_actuator version 1
~~~

### PositionActuator

~~~python
sample = actuator.move_to(0.100)
actuator.stop()
~~~

Represents absolute target positioning.

Interface identifier:

~~~text
motion.position_actuator version 1
~~~

## Structural use

Implementations may inherit from these classes or satisfy the contracts structurally. Structural implementations are useful for small MicroPython drivers and host test doubles.

## Units

Capability boundaries use SI units:

| Quantity | Unit |
|---|---|
| Linear position or distance | m |
| Angular position | rad |
| Linear velocity | m/s |
| Angular velocity | rad/s |

Native-unit convenience operations can exist, but inter-service binding uses canonical capability semantics.

## Manifest

**component.yaml** documents the interface identifiers and operation names alongside the rp.service/v1 package definition.

## Repository layout

- `src/` contains importable modules and device startup files.
- `test/` contains host tests or hardware-test guidance.
- `package.json` maps source files to their MIP installation paths.
- `component.yaml` defines the service lifecycle, capabilities, operations, signals, and tests.
- Optional `examples/` and `tools/` directories contain development-only resources.

## MIP installation

All file sources in `package.json` are relative to this component directory. The package installs its Python modules under `/lib/rpstack/interfaces/`, allowing applications to import `rpstack.interfaces`.

From this component directory:

~~~bash
mpremote mip install ./package.json
~~~

From the repository root:

~~~bash
mpremote mip install RPStack/services/interfaces/package.json
~~~

From GitHub on the development branch:

~~~bash
mpremote mip install github:ROSMicroPy/RobotPrimitivesStack/RPStack/services/interfaces@archdef
~~~

A raw manifest URL is also supported:

~~~bash
mpremote mip install https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/archdef/RPStack/services/interfaces/package.json
~~~
