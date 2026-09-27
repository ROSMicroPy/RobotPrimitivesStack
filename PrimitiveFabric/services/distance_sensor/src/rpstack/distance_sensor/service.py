"""Distance-observer service with pluggable MicroPython hardware drivers."""

from rpstack.support import asyncio, call

from rpstack.interfaces import DistanceObserver, DistanceSample, PrimitiveService


class DistanceSensorDriver:
    # Require each hardware driver to configure and activate its sensor.
    def initialize(self, **config):
        raise NotImplementedError

    # Require a hardware reading expressed in millimetres.
    def read_distance_mm(self):
        raise NotImplementedError

    # Require drivers to implement the sensor's active/inactive transition.
    def set_active(self, active):
        raise NotImplementedError

    # Use the driver's inactive state as the default shutdown procedure.
    def shutdown(self):
        return self.set_active(False)

    # Provide an empty status for drivers without additional diagnostics.
    def get_status(self):
        return {}


class DistanceSensor(PrimitiveService, DistanceObserver):
    """Runtime-managed distance capability wrapping one concrete driver."""

    # Wrap a driver with lifecycle state, alert storage, and a lock for serial readings.
    def __init__(self, name, driver, reference_frame=None):
        self.name = name
        self.driver = driver
        self.reference_frame = reference_frame
        self.active = False
        self.alerts = []
        self.last_distance_mm = None
        self._read_lock = asyncio.Lock()
        self._config = {}

    # Save driver settings and the reference frame, rejecting negative polling rates.
    def configure(self, config=None, **kwargs):
        values = dict(config or {})
        values.update(kwargs)
        if values.get("poll_frequency_hz", 0) < 0:
            raise ValueError("poll_frequency_hz cannot be negative")
        self.reference_frame = values.get("reference_frame", self.reference_frame)
        self._config = values
        return True

    # Pass hardware settings to the driver and record whether initialization succeeded.
    async def init(self):
        config = dict(self._config)
        config.pop("poll_frequency_hz", None)
        self.active = bool(await call(self.driver.initialize, **config))
        return self.active

    # Reactivate the driver if needed before reporting service readiness.
    def start(self):
        if not self.active:
            self.active = bool(self.driver.set_active(True))
        return self.active

    # Poll at the configured rate, or wait indefinitely when readings are on demand.
    async def run(self):
        frequency = self._config.get("poll_frequency_hz", 0)
        if not frequency:
            await asyncio.Event().wait()
        while True:
            await self._read_distance_mm()
            await asyncio.sleep(1.0 / frequency)


    # Convert the millimetre reading into a distance sample in metres.
    async def distance(self):
        return DistanceSample(await self._read_distance_mm() / 1000.0, "m",
                              reference_frame=self.reference_frame)

    # Serialize hardware access, remember the rounded reading, then evaluate alerts.
    async def _read_distance_mm(self):
        if not self.active:
            raise RuntimeError("Distance sensor {} is inactive".format(self.name))
        async with self._read_lock:
            distance = int(round(await call(self.driver.read_distance_mm)))
        self.last_distance_mm = distance
        self._evaluate_alerts(distance)
        return distance


    # Register a distance target and tolerance for a callback on a matching reading.
    def add_alert(self, target_mm, callback, tolerance_mm=0):
        if tolerance_mm < 0:
            raise ValueError("tolerance_mm cannot be negative")
        self.alerts.append({"target": int(target_mm), "tolerance": int(tolerance_mm),
                            "callback": callback})

    # Remove every alert associated with this exact callback object.
    def remove_alert(self, callback):
        self.alerts = [alert for alert in self.alerts if alert["callback"] is not callback]

    # Fire matching alerts; keep them only when the callback explicitly returns True.
    def _evaluate_alerts(self, distance):
        retained = []
        for alert in self.alerts:
            if abs(distance - alert["target"]) <= alert["tolerance"]:
                if alert["callback"](distance) is True:
                    retained.append(alert)
            else:
                retained.append(alert)
        self.alerts = retained

    # Change local lifecycle state only after the driver accepts the transition.
    def set_active(self, active):
        result = bool(self.driver.set_active(bool(active)))
        if result:
            self.active = bool(active)
        return result

    # Deactivate the sensor through the same path used by explicit state changes.
    def stop(self):
        return self.set_active(False)

    # Stop the sensor, then initialize and reactivate it using the saved settings.
    async def reset(self):
        self.stop()
        return await self.init() and self.start()

    # Shut down the hardware and mark the service inactive.
    def shutdown(self):
        result = bool(self.driver.shutdown())
        self.active = False
        return result

    # Expose the combined sensor status through the runtime lifecycle interface.
    def status(self):
        return self.get_status()

    # Add service identity and the latest reading to the driver's diagnostics.
    def get_status(self):
        status = self.driver.get_status()
        status.update(name=self.name, active=self.active,
                      last_distance_mm=self.last_distance_mm)
        return status




__all__ = ("DistanceSensor", "DistanceSensorDriver")
