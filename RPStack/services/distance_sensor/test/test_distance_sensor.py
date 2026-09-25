import itertools
from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import asyncio
import unittest
from unittest.mock import patch

COMPONENT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = COMPONENT_DIR.parent


from rpstack.distance_sensor import DistanceSensor, DistanceSensorDriver
from rpstack.distance_sensor.distance_drivers.hcsr04 import HCSR04Driver
from rpstack.distance_sensor.distance_drivers.vl53l4cd_core import DEFAULT_CONFIGURATION, VL53L4CD


class FakeDriver(DistanceSensorDriver):
    # Prepare scripted distance readings and an initially inactive fake sensor.
    def __init__(self, readings):
        self.readings = iter(readings)
        self.active = False

    # Simulate successful sensor activation without hardware.
    def initialize(self, **_):
        self.active = True
        return True

    # Return the next scripted millimetre reading.
    def read_distance_mm(self):
        return next(self.readings)

    # Record requested activation changes for lifecycle assertions.
    def set_active(self, active):
        self.active = bool(active)
        return True


class FakePin:
    # Prepare a history of digital output values for pulse assertions.
    def __init__(self):
        self.values = []

    # Record each requested pin level instead of driving hardware.
    def value(self, value):
        self.values.append(value)


class FakeI2C:
    # Prepare an in-memory register map containing the expected VL53L4CD model ID.
    def __init__(self):
        self.pointer = 0
        self.writes = []
        self.registers = {0x010F: b"\xeb\xaa"}

    # Record bus writes and emulate register pointer selection and data storage.
    def writeto(self, address, data, stop=True):
        self.writes.append((address, bytes(data), stop))
        self.pointer = (data[0] << 8) | data[1]
        if len(data) > 2:
            self.registers[self.pointer] = bytes(data[2:])

    # Return bytes from the selected fake register, defaulting to zeros.
    def readfrom(self, address, length):
        return self.registers.get(self.pointer, bytes(length))[:length]


class DistanceSensorTests(unittest.IsolatedAsyncioTestCase):
    # Create and initialize a sensor backed by deterministic readings.
    async def make_sensor(self, readings):
        sensor = DistanceSensor("test", FakeDriver(readings))
        sensor.configure({})
        self.assertTrue(await sensor.init())
        self.assertTrue(sensor.start())
        return sensor

    # Verify fractional driver readings become rounded integer millimetres.
    async def test_read_rounds_to_integer_millimeters(self):
        self.assertAlmostEqual((await (await self.make_sensor([12.6])).distance()).value, 0.013)

    # Verify a callback that does not request retention fires only once.
    async def test_alert_is_one_shot_unless_callback_returns_true(self):
        sensor = await self.make_sensor([10, 10])
        calls = []
        sensor.add_alert(10, lambda distance: calls.append(distance))
        await sensor.distance()
        await sensor.distance()
        self.assertEqual(calls, [10])

    # Verify the polling loop reads the sensor and triggers registered alerts.
    async def test_background_polling(self):
        sensor = DistanceSensor("test", FakeDriver(itertools.repeat(10)))
        fired = asyncio.Event()
        sensor.add_alert(10, lambda _: fired.set())
        sensor.configure({"poll_frequency_hz": 100})
        await sensor.init()
        sensor.start()
        task = asyncio.create_task(sensor.run())
        try:
            await asyncio.wait_for(fired.wait(), 0.5)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            sensor.shutdown()

    # Check ultrasonic pulse timing converts into distance and drives the expected trigger
    # sequence.
    async def test_hcsr04_converts_round_trip_time_to_distance(self):
        trigger = FakePin()
        driver = HCSR04Driver()
        driver.initialize(trigger, FakePin(), time_pulse_us=lambda *_: 1000)
        self.assertAlmostEqual(driver.read_distance_mm(), 171.71, places=2)
        self.assertEqual(trigger.values[-3:], [0, 1, 0])

    # Check VL53 register addressing and the size of its default configuration block.
    async def test_vl53_uses_two_byte_register_pointer_and_native_i2c(self):
        i2c = FakeI2C()
        sensor = VL53L4CD(i2c)
        self.assertEqual(sensor._read_u16(0x010F), 0xEBAA)
        self.assertEqual(i2c.writes[-1], (0x29, b"\x01\x0f", False))
        self.assertEqual(len(DEFAULT_CONFIGURATION), 91)

    # Ensure each read waits for a fresh exposure even when the ready bit stays asserted.
    async def test_vl53_fresh_cycle_without_observable_ready_low(self):
        from rpstack.distance_sensor.distance_drivers.vl53l4cd import VL53L4CDDriver
        class HeldRange:
            data_ready = True  # Host never sees a low transition.
            value = 20
            # Prepare an operation log for a sensor whose ready bit never drops.
            def __init__(self):
                self.events = []
            # Record a stop so the test can inspect measurement restart order.
            def stop_ranging(self):
                self.events.append('stop')
            # Record the beginning of a fresh simulated exposure.
            def start_ranging(self):
                self.events.append('start')
            # Record interrupt acknowledgement in the simulated measurement sequence.
            def clear_interrupt(self):
                self.events.append('clear')
            # Return the fake exposure value with a successful range status.
            def read_result(self):
                self.events.append('read')
                return {'range_status': 0, 'distance_mm': self.value}
        driver = VL53L4CDDriver()
        driver.sensor = HeldRange()
        driver.active = True
        # Assert the exposure delay/order and replace the stale value with a fresh reading.
        async def exposure(delay):
            self.assertGreaterEqual(delay, .05)
            self.assertEqual(driver.sensor.events[-1], 'start')
            driver.sensor.value = 100
        with patch('rpstack.distance_sensor.distance_drivers.vl53l4cd.asyncio.sleep', exposure):
            self.assertEqual(await driver.read_distance_mm(), 100)
        self.assertEqual(driver.sensor.events, ['stop', 'clear', 'start', 'read', 'stop', 'clear'])

    # Verify a missing measurement times out and leaves the sensor stopped.
    async def test_vl53_fresh_measurement_timeout_stops_ranging(self):
        from rpstack.distance_sensor.distance_drivers.vl53l4cd import VL53L4CDDriver
        class NotReady:
            data_ready = False
            running = False
            # Mark the never-ready sensor running so cleanup can be verified.
            def start_ranging(self):
                self.running = True
            # Record that timeout cleanup stopped the simulated sensor.
            def stop_ranging(self):
                self.running = False
            # Accept interrupt clearing without making this simulated sensor ready.
            def clear_interrupt(self):
                pass
        driver = VL53L4CDDriver()
        driver.sensor = NotReady()
        driver.active = True
        driver.frame_wait_ms = 0
        driver.read_timeout_ms = 5
        with self.assertRaisesRegex(RuntimeError, "fresh measurement"):
            await driver.read_distance_mm()
        self.assertFalse(driver.sensor.running)

    # Check that stopping ranging writes the expected register value and clears local state.
    async def test_vl53_stop_uses_uld_stop_register_value(self):
        i2c = FakeI2C()
        sensor = VL53L4CD(i2c)
        sensor.stop_ranging()
        self.assertEqual(i2c.registers[0x0087], b"\x00")
        self.assertFalse(sensor.ranging)

    # Ensure a boot timeout retains a useful sensor-specific error message.
    async def test_vl53_boot_timeout_preserves_message(self):
        sensor = VL53L4CD(FakeI2C(), io_timeout_ms=5)
        with self.assertRaisesRegex(RuntimeError, "VL53L4CD boot timed out"):
            await sensor.initialize()

    # Verify pending sensor reads yield to the event loop and stop ranging on cancellation.
    async def test_vl53_wait_is_cooperative_and_cancellable(self):
        from rpstack.distance_sensor.distance_drivers.vl53l4cd import VL53L4CDDriver
        class NotReady:
            data_ready = False
            running = False
            # Mark the simulated sensor running before the cancellation exercise.
            def start_ranging(self):
                self.running = True
            # Record that cancellation cleanup stopped the simulated sensor.
            def stop_ranging(self):
                self.running = False
            # Accept interrupt acknowledgement while keeping the simulated measurement
            # unavailable.
            def clear_interrupt(self):
                pass
        driver = VL53L4CDDriver()
        driver.sensor = NotReady()
        driver.active = True
        task = asyncio.create_task(driver.read_distance_mm())
        await asyncio.sleep(0.005)
        self.assertFalse(task.done())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(driver.sensor.running)


if __name__ == "__main__":
    unittest.main()
