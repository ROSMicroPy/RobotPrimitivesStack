"""DistanceSensor adapter for the ST VL53L4CD time-of-flight sensor."""

import time
from rpstack.support import asyncio

from rpstack.distance_sensor import DistanceSensorDriver
from rpstack.distance_sensor.distance_drivers.vl53l4cd_core import VL53L4CD


class VL53L4CDDriver(DistanceSensorDriver):
    # Reserve the sensor reference and defaults for exposure and read timeouts.
    def __init__(self):
        self.sensor = None
        self.active = False
        self.read_timeout_ms = 1000
        self.frame_wait_ms = 55

    # Validate the exposure window, initialize the I2C sensor, and enable readings.
    async def initialize(self, i2c, address=0x29, timing_budget=50,
                   inter_measurement=0, read_timeout_ms=1000, **_):
        self.read_timeout_ms = int(read_timeout_ms)
        self.frame_wait_ms = max(int(timing_budget), int(inter_measurement)) + 5
        if self.read_timeout_ms <= self.frame_wait_ms:
            raise ValueError("read_timeout_ms must exceed the measurement period plus 5 ms")
        self.sensor = VL53L4CD(i2c, address, self.read_timeout_ms)
        await self.sensor.initialize(timing_budget, inter_measurement)
        self.active = True
        return True

    # Restart ranging for a fresh exposure, wait within the timeout, and validate the result.
    async def read_distance_mm(self):
        if not self.active:
            raise RuntimeError("VL53L4CD is inactive")
        start = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.monotonic() * 1000)
        # Restart at the observation boundary, so a frame from before motion
        # cannot be reused. Do not require polling to catch a ready-low edge.
        self.sensor.stop_ranging()
        self.sensor.clear_interrupt()
        try:
            self.sensor.start_ranging()
            # Allow a complete exposure even if the previous ready bit lingers.
            await asyncio.sleep(self.frame_wait_ms / 1000.0)
            while True:
                now = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.monotonic() * 1000)
                elapsed_ms = time.ticks_diff(now, start) if hasattr(time, "ticks_diff") else now - start
                if elapsed_ms >= self.read_timeout_ms:
                    raise RuntimeError("VL53L4CD timed out waiting for fresh measurement ({} ms)".format(
                        self.read_timeout_ms))
                if self.sensor.data_ready:
                    break
                await asyncio.sleep(0.001)
            result = self.sensor.read_result()
            if result["range_status"] != 0:
                raise RuntimeError("VL53L4CD invalid range status {}".format(result["range_status"]))
            return result["distance_mm"]
        finally:
            # Also stop on cancellation, timeout, invalid range or I2C error.
            self.sensor.stop_ranging()
            self.sensor.clear_interrupt()

    # Update availability, stopping ongoing ranging when the driver is deactivated.
    def set_active(self, active):
        if self.sensor is None:
            self.active = False
            return not active
        if not active and self.active:
            self.sensor.stop_ranging()
        self.active = bool(active)
        return True

    # Deactivate the driver through its normal ranging-stop path.
    def shutdown(self):
        return self.set_active(False)

    # Expose the sensor identity, I2C address, and active state.
    def get_status(self):
        return {"active": self.active,
                "address": self.sensor.address if self.sensor else None,
                "sensor": "VL53L4CD"}
