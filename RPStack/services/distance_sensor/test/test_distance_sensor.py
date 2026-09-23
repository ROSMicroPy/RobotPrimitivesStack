import itertools
from pathlib import Path
import sys
import asyncio
import unittest

COMPONENT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = COMPONENT_DIR.parent
sys.path.insert(0, str(SERVICES_DIR / "interfaces" / "src"))
sys.path.insert(0, str(COMPONENT_DIR / "src"))

for runtime_src in (SERVICES_DIR.parent / "runtime").glob("*/src"):
    sys.path.insert(0, str(runtime_src))

from rpstack.distance_sensor import DistanceSensor, DistanceSensorDriver
from rpstack.distance_sensor.distance_drivers.hcsr04 import HCSR04Driver
from rpstack.distance_sensor.distance_drivers.vl53l4cd_core import DEFAULT_CONFIGURATION, VL53L4CD


class FakeDriver(DistanceSensorDriver):
    def __init__(self, readings):
        self.readings = iter(readings)
        self.active = False

    def initialize(self, **_):
        self.active = True
        return True

    def read_distance_mm(self):
        return next(self.readings)

    def set_active(self, active):
        self.active = bool(active)
        return True


class FakePin:
    def __init__(self):
        self.values = []

    def value(self, value):
        self.values.append(value)


class FakeI2C:
    def __init__(self):
        self.pointer = 0
        self.writes = []
        self.registers = {0x010F: b"\xeb\xaa"}

    def writeto(self, address, data, stop=True):
        self.writes.append((address, bytes(data), stop))
        self.pointer = (data[0] << 8) | data[1]
        if len(data) > 2:
            self.registers[self.pointer] = bytes(data[2:])

    def readfrom(self, address, length):
        return self.registers.get(self.pointer, bytes(length))[:length]


class DistanceSensorTests(unittest.IsolatedAsyncioTestCase):
    async def make_sensor(self, readings):
        sensor = DistanceSensor("test", FakeDriver(readings))
        self.assertTrue(await sensor.initialize())
        return sensor

    async def test_read_rounds_to_integer_millimeters(self):
        self.assertEqual(await (await self.make_sensor([12.6])).read_distance_mm(), 13)

    async def test_alert_is_one_shot_unless_callback_returns_true(self):
        sensor = await self.make_sensor([10, 10])
        calls = []
        sensor.add_alert(10, lambda distance: calls.append(distance))
        await sensor.read_distance()
        await sensor.read_distance()
        self.assertEqual(calls, [10])

    async def test_background_polling(self):
        sensor = DistanceSensor("test", FakeDriver(itertools.repeat(10)))
        fired = asyncio.Event()
        sensor.add_alert(10, lambda _: fired.set())
        await sensor.initialize(poll_frequency_hz=100)
        task = asyncio.create_task(sensor.run())
        try:
            await asyncio.wait_for(fired.wait(), 0.5)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            sensor.shutdown()

    async def test_hcsr04_converts_round_trip_time_to_distance(self):
        trigger = FakePin()
        driver = HCSR04Driver()
        driver.initialize(trigger, FakePin(), time_pulse_us=lambda *_: 1000)
        self.assertAlmostEqual(driver.read_distance_mm(), 171.71, places=2)
        self.assertEqual(trigger.values[-3:], [0, 1, 0])

    async def test_vl53_uses_two_byte_register_pointer_and_native_i2c(self):
        i2c = FakeI2C()
        sensor = VL53L4CD(i2c)
        self.assertEqual(sensor._read_u16(0x010F), 0xEBAA)
        self.assertEqual(i2c.writes[-1], (0x29, b"\x01\x0f", False))
        self.assertEqual(len(DEFAULT_CONFIGURATION), 91)

    async def test_vl53_wait_is_cooperative_and_cancellable(self):
        from rpstack.distance_sensor.distance_drivers.vl53l4cd import VL53L4CDDriver
        class NotReady:
            data_ready = False
        driver = VL53L4CDDriver()
        driver.sensor = NotReady()
        driver.active = True
        task = asyncio.create_task(driver.read_distance_mm())
        await asyncio.sleep(0.005)
        self.assertFalse(task.done())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task


if __name__ == "__main__":
    unittest.main()
