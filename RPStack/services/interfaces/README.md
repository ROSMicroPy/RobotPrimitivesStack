# RPInterfaces

RPInterfaces defines the hardware-independent contracts shared by Primitive Services, composites, bridges, simulations, and test doubles.

The package installs as **RPInterfaces** and avoids CPython-only dependencies.

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
from RPInterfaces import PositionSample

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
