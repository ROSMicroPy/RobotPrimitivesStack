# DistanceSensor

DistanceSensor wraps a concrete ranging device as a runtime-managed **sensing.distance_observer** service.

It reports raw distance along the sensor ray. Installation meaning, such as carriage position, belongs in an adapter.

## Included implementations

### hcsr04

Trigger/echo ultrasonic distance sensor.

Configuration:

- trigger_pin
- echo_pin
- timeout_us
- temperature_c

The driver uses the measured round-trip pulse time and temperature-adjusted speed of sound.

### vl53l4cd

ST VL53L4CD time-of-flight distance sensor using native MicroPython I2C calls.

Configuration:

- i2c
- address
- timing_budget
- inter_measurement
- read_timeout_ms

The driver performs direct **writeto** and **readfrom** operations and does not require CircuitPython I2CDevice.

## Capability API

~~~python
sample = await sensor.distance()

print(sample.value)            # metres
print(sample.unit)             # "m"
print(sample.reference_frame)
print(sample.valid)
print(sample.quality)
~~~

## Lifecycle

The service supports:

- configure
- init
- start
- stop
- reset
- status

## Direct construction

~~~python
from rpstack.distance_sensor import DistanceSensor
from rpstack.distance_sensor.distance_drivers.vl53l4cd import VL53L4CDDriver

sensor = DistanceSensor("lift_tof", VL53L4CDDriver(), reference_frame="lift.sensor")
sensor.configure(dict(i2c=i2c, address=0x29, timing_budget=50))
await sensor.init()
sensor.start()
try:
    sample = await sensor.distance()
finally:
    sensor.shutdown()
~~~

Run this inside an async function. Manifest deployments let the node runtime construct the service and own its lifecycle.

## Polling and alerts

Configure **poll_frequency_hz** to enable cooperative polling in the service’s async `run()` task. Polling updates the most recent reading and evaluates registered alerts.

~~~python
sensor.add_alert(
    target_mm=100,
    tolerance_mm=2,
    callback=on_target,
)
~~~

An alert is removed after firing unless its callback returns **True**.

A zero polling frequency selects on-demand readings through `await sensor.distance()`.

## Manifest operations

The canonical **component.yaml** declares:

- observe_distance
- set_active
- status

The **observe_once** automatic test acquires a sample and verifies canonical unit and validity fields.

## Packaging

**package.json** installs:

- DistanceSensor
- hcsr04
- vl53l4cd
- vl53l4cd_core
- RPInterfaces dependency

Install the package manifest with MicroPython mip or mpremote.

## Repository layout

- `src/` contains importable modules and device startup files.
- `test/` contains host tests or hardware-test guidance.
- `package.json` maps source files to their MIP installation paths.
- `component.yaml` defines the service lifecycle, capabilities, operations, signals, and tests.
- Optional `examples/` and `tools/` directories contain development-only resources.

## MIP installation

All file sources in `package.json` are relative to this component directory. The package installs its Python modules under `/lib/rpstack/distance_sensor/`, allowing applications to import `rpstack.distance_sensor`.

From this component directory:

~~~bash
mpremote mip install ./package.json
~~~

From the repository root:

~~~bash
mpremote mip install RPStack/services/distance_sensor/package.json
~~~

From GitHub on the development branch:

~~~bash
mpremote mip install github:ROSMicroPy/RobotPrimitivesStack/RPStack/services/distance_sensor@archdef
~~~

A raw manifest URL is also supported:

~~~bash
mpremote mip install https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/archdef/RPStack/services/distance_sensor/package.json
~~~
