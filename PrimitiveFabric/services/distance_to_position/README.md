# DistanceToPosition

DistanceToPosition is an adapter service that converts a raw **sensing.distance_observer** into a one-dimensional linear **motion.position_observer**.

## Why the adapter exists

A distance sensor measures range along a sensing ray. The position of an installed carriage depends on how the sensor is mounted. The adapter holds that installation knowledge so both the sensor and the consuming composite remain reusable.

## Transformation

The adapter calculates:

~~~text
position_m = zero_offset_m + direction × distance_m
~~~

**direction** must be either 1 or -1.

The adapter preserves the source timestamp and quality. It marks the position invalid when it falls outside an optional configured range.

## Required capability

~~~yaml
distance_observer:
  interface: sensing.distance_observer
  version: 1
~~~

NodeRuntime passes the bound provider to the constructor using the **distance_observer** role name.

## Provided capability

~~~yaml
interface: motion.position_observer
version: 1
quantity: linear
dimensions: 1
canonical_unit: m
~~~

## Configuration

| Field | Meaning |
|---|---|
| zero_offset_m | Position offset in metres |
| direction | 1 or -1 |
| reference_frame | Frame assigned to output samples |
| min_position_m | Optional lower valid position |
| max_position_m | Optional upper valid position |

## Use

~~~python
from rpstack.distance_to_position import DistanceToPositionAdapter

position = DistanceToPositionAdapter(
    distance_observer=tof,
    zero_offset_m=0.300,
    direction=-1,
    reference_frame="lift.base",
    min_position_m=0.0,
    max_position_m=0.280,
)

position.start()
sample = position.position()
~~~

For a sensor reading of 0.200 m, this configuration reports 0.100 m.

## Lifecycle and status

The adapter supports configure, init, start, stop, reset, and status. It owns only the transformation state; the supervisor manages the lifecycle of the bound distance service.

## Manifest operations and tests

The canonical **component.yaml** declares:

- observe_position
- status

The **transform_once** automatic test reads one sample and verifies that the result is a linear position in metres.

## Repository layout

- `src/` contains importable modules and device startup files.
- `test/` contains host tests or hardware-test guidance.
- `package.json` maps source files to their MIP installation paths.
- `component.yaml` defines the service lifecycle, capabilities, operations, signals, and tests.
- Optional `examples/` and `tools/` directories contain development-only resources.

## MIP installation

All file sources in `package.json` are relative to this component directory. The package installs its Python modules under `/lib/rpstack/distance_to_position/`, allowing applications to import `rpstack.distance_to_position`.

From this component directory:

~~~bash
mpremote mip install ./package.json
~~~

From the repository root:

~~~bash
mpremote mip install RPStack/services/distance_to_position/package.json
~~~

From GitHub on the development branch:

~~~bash
mpremote mip install github:ROSMicroPy/RobotPrimitivesStack/RPStack/services/distance_to_position@archdef
~~~

A raw manifest URL is also supported:

~~~bash
mpremote mip install https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/archdef/RPStack/services/distance_to_position/package.json
~~~
