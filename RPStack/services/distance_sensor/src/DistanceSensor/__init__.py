"""Distance-observer service with pluggable MicroPython hardware drivers."""

try:
    import importlib
except ImportError:
    import uimportlib as importlib

try:
    import threading
except ImportError:
    threading = None

try:
    from RPInterfaces import DistanceObserver, DistanceSample, PrimitiveService
except ImportError:  # Monorepo/host execution before mip packaging.
    from RPStack.services.interfaces import (
        DistanceObserver, DistanceSample, PrimitiveService,
    )


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
        self.last_poll_error = None
        self._polling = False
        self._poll_thread = None
        self._config = {}

    def configure(self, config=None, **kwargs):
        values = dict(config or {})
        values.update(kwargs)
        if values.get("poll_frequency_hz", 0) < 0:
            raise ValueError("poll_frequency_hz cannot be negative")
        self._config = values
        return True

    def init(self):
        config = dict(self._config)
        config.pop("poll_frequency_hz", None)
        self.active = bool(self.driver.initialize(**config))
        return self.active

    def start(self):
        if not self.active:
            self.active = bool(self.driver.set_active(True))
        frequency = self._config.get("poll_frequency_hz", 0)
        if self.active and frequency:
            self.start_polling(frequency)
        return self.active

    def initialize(self, poll_frequency_hz=0, **config):
        """Compatibility entry point combining configure/init/start."""
        config["poll_frequency_hz"] = poll_frequency_hz
        return self.configure(config) and self.init() and self.start()

    def distance(self):
        """Return a canonical SI distance sample."""
        return DistanceSample(
            self.read_distance_mm() / 1000.0,
            "m",
            reference_frame=self.reference_frame,
        )

    def read_distance(self):
        if not self.active:
            raise RuntimeError("Distance sensor {} is inactive".format(self.name))
        distance = int(round(self.driver.read_distance_mm()))
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
        if not active:
            self.stop_polling()
        result = bool(self.driver.set_active(bool(active)))
        if result:
            self.active = bool(active)
        return result

    def start_polling(self, frequency_hz):
        if threading is None:
            raise RuntimeError("background polling is unavailable; poll from an OnEvent task")
        if frequency_hz <= 0:
            raise ValueError("frequency_hz must be positive")
        if self._polling:
            return
        self._polling = True
        interval = 1.0 / float(frequency_hz)

        def poll():
            import time
            while self._polling:
                try:
                    self.read_distance()
                    self.last_poll_error = None
                except Exception as error:
                    self.last_poll_error = error
                time.sleep(interval)

        self._poll_thread = threading.Thread(target=poll, daemon=True)
        self._poll_thread.start()

    def stop_polling(self):
        self._polling = False
        if self._poll_thread and self._poll_thread is not threading.current_thread():
            self._poll_thread.join(timeout=1)
        self._poll_thread = None

    def stop(self):
        return self.set_active(False)

    def reset(self):
        self.stop()
        return self.init() and self.start()

    def shutdown(self):
        self.stop_polling()
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

    def __init__(self, driver_package="DistanceSensor.distance_drivers"):
        self.driver_package = driver_package
        self.sensors = {}
        self._driver_cache = {}

    def _load_driver(self, driver_name):
        if driver_name not in self._driver_cache:
            module = importlib.import_module("{}.{}".format(self.driver_package, driver_name))
            driver_class = getattr(module, "DRIVER_CLASS", None)
            if driver_class is None:
                raise ImportError("{}.{} does not export DRIVER_CLASS".format(self.driver_package, driver_name))
            self._driver_cache[driver_name] = driver_class
        return self._driver_cache[driver_name]

    def create_sensor(self, name, driver_name=None, driver_class=None, **config):
        if name in self.sensors:
            raise ValueError("Sensor {} already exists".format(name))
        if driver_class is None:
            if not driver_name:
                raise ValueError("driver_name or driver_class is required")
            driver_class = self._load_driver(driver_name)
        reference_frame = config.pop("reference_frame", None)
        sensor = DistanceSensor(name, driver_class(), reference_frame)
        if not sensor.initialize(**config):
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
