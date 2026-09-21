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
sample = sensor.distance()

print(sample.value)            # metres
print(sample.unit)             # "m"
print(sample.reference_frame)
print(sample.valid)
print(sample.quality)
~~~

The millimetre convenience API is:

~~~python
distance_mm = sensor.read_distance_mm()
~~~

## Lifecycle

The service supports:

- configure
- init
- start
- stop
- reset
- status

**initialize()** combines configuration, initialization, and startup for direct use.

## Direct construction

~~~python
from DistanceSensor import DistanceSensorController

sensors = DistanceSensorController()

tof = sensors.create_sensor(
    "lift_tof",
    "vl53l4cd",
    i2c=i2c,
    address=0x29,
    timing_budget=50,
    reference_frame="lift.sensor",
)

sample = tof.distance()
sensors.shutdown()
~~~

**DistanceSensorController** is a convenient factory for direct applications. PrimitiveRuntime applications can supply a factory that constructs the same service and lets the supervisor own its lifecycle.

## Polling and alerts

A sensor can be initialized with **poll_frequency_hz** on systems with thread support. Polling updates the most recent reading and evaluates registered alerts.

~~~python
sensor.add_alert(
    target_mm=100,
    tolerance_mm=2,
    callback=on_target,
)
~~~

An alert is removed after firing unless its callback returns **True**.

On constrained targets without background threads, poll from the device event loop or an RPStack behavior.

## Manifest operations

The canonical **component.yaml** declares:

- observe_distance
- read_distance_mm
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
