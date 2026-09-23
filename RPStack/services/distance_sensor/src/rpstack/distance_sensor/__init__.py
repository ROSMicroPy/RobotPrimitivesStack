"""Distance-observer service with pluggable MicroPython hardware drivers."""

try:
    from importlib import import_module as _import_module
except ImportError:
    def _import_module(name):
        """Import and return a nested module without requiring importlib."""
        return __import__(name, None, None, ("*",))

from rpstack.execution_engine import asyncio, call

from rpstack.interfaces import DistanceObserver, DistanceSample, PrimitiveService


class DistanceSensorDriver:
    def initialize(self, **config):
        raise NotImplementedError

    def read_distance_mm(self):
        raise NotImplementedError

    def set_active(self, active):
        raise NotImplementedError

    def shutdown(self):
        return self.set_active(False)

    def get_status(self):
        return {}


class DistanceSensor(PrimitiveService, DistanceObserver):
    """Runtime-managed distance capability wrapping one concrete driver."""

    def __init__(self, name, driver, reference_frame=None):
        self.name = name
        self.driver = driver
        self.reference_frame = reference_frame
        self.active = False
        self.alerts = []
        self.last_distance_mm = None
        self._read_lock = asyncio.Lock()
        self._config = {}

    def configure(self, config=None, **kwargs):
        values = dict(config or {})
        values.update(kwargs)
        if values.get("poll_frequency_hz", 0) < 0:
            raise ValueError("poll_frequency_hz cannot be negative")
        self.reference_frame = values.get("reference_frame", self.reference_frame)
        self._config = values
        return True

    async def init(self):
        config = dict(self._config)
        config.pop("poll_frequency_hz", None)
        self.active = bool(await call(self.driver.initialize, **config))
        return self.active

    def start(self):
        if not self.active:
            self.active = bool(self.driver.set_active(True))
        return self.active

    async def run(self):
        frequency = self._config.get("poll_frequency_hz", 0)
        if not frequency:
            await asyncio.Event().wait()
        while True:
            await self.read_distance()
            await asyncio.sleep(1.0 / frequency)

    async def initialize(self, poll_frequency_hz=0, **config):
        config["poll_frequency_hz"] = poll_frequency_hz
        return self.configure(config) and await self.init() and self.start()

    async def distance(self):
        return DistanceSample(await self.read_distance_mm() / 1000.0, "m",
                              reference_frame=self.reference_frame)

    async def read_distance(self):
        if not self.active:
            raise RuntimeError("Distance sensor {} is inactive".format(self.name))
        async with self._read_lock:
            distance = int(round(await call(self.driver.read_distance_mm)))
        self.last_distance_mm = distance
        self._evaluate_alerts(distance)
        return distance

    read_distance_mm = read_distance

    def add_alert(self, target_mm, callback, tolerance_mm=0):
        if tolerance_mm < 0:
            raise ValueError("tolerance_mm cannot be negative")
        self.alerts.append({"target": int(target_mm), "tolerance": int(tolerance_mm),
                            "callback": callback})

    def remove_alert(self, callback):
        self.alerts = [alert for alert in self.alerts if alert["callback"] is not callback]

    def _evaluate_alerts(self, distance):
        retained = []
        for alert in self.alerts:
            if abs(distance - alert["target"]) <= alert["tolerance"]:
                if alert["callback"](distance) is True:
                    retained.append(alert)
            else:
                retained.append(alert)
        self.alerts = retained

    def set_active(self, active):
        result = bool(self.driver.set_active(bool(active)))
        if result:
            self.active = bool(active)
        return result

    def stop(self):
        return self.set_active(False)

    async def reset(self):
        self.stop()
        return await self.init() and self.start()

    def shutdown(self):
        result = bool(self.driver.shutdown())
        self.active = False
        return result

    def status(self):
        return self.get_status()

    def get_status(self):
        status = self.driver.get_status()
        status.update(name=self.name, active=self.active,
                      last_distance_mm=self.last_distance_mm)
        return status


class DistanceSensorController:
    """Compatibility factory; runtime manifests should create services directly."""

    def __init__(self, driver_package="rpstack.distance_sensor.distance_drivers"):
        self.driver_package = driver_package
        self.sensors = {}
        self._driver_cache = {}

    def _load_driver(self, driver_name):
        if driver_name not in self._driver_cache:
            module = _import_module("{}.{}".format(self.driver_package, driver_name))
            driver_class = getattr(module, "DRIVER_CLASS", None)
            if driver_class is None:
                raise ImportError("{}.{} does not export DRIVER_CLASS".format(self.driver_package, driver_name))
            self._driver_cache[driver_name] = driver_class
        return self._driver_cache[driver_name]

    async def create_sensor(self, name, driver_name=None, driver_class=None, **config):
        if name in self.sensors:
            raise ValueError("Sensor {} already exists".format(name))
        if driver_class is None:
            if not driver_name:
                raise ValueError("driver_name or driver_class is required")
            driver_class = self._load_driver(driver_name)
        reference_frame = config.pop("reference_frame", None)
        sensor = DistanceSensor(name, driver_class(), reference_frame)
        if not await sensor.initialize(**config):
            raise RuntimeError("Driver failed to initialize sensor {}".format(name))
        self.sensors[name] = sensor
        return sensor

    def get_sensor(self, name):
        return self.sensors.get(name)

    def remove_sensor(self, name):
        sensor = self.sensors.pop(name, None)
        return sensor.shutdown() if sensor else False

    def shutdown(self):
        success = True
        for sensor in tuple(self.sensors.values()):
            try:
                success = sensor.shutdown() and success
            except Exception:
                success = False
        self.sensors.clear()
        return success


__all__ = ("DistanceSensor", "DistanceSensorController", "DistanceSensorDriver")
