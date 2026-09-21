import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "runtime" / "primitive_runtime" / "src"))

from PrimitiveRuntime import (  # noqa: E402
    LifecycleError,
    ManifestTestError,
    ManifestTestRunner,
    ResolutionError,
    ServiceManifest,
    ServiceSupervisor,
)


SERVICES = ROOT / "services"


class Sample:
    def __init__(self, kind=None, value=0.1, unit="m", valid=True):
        self.kind = kind
        self.value = value
        self.unit = unit
        self.valid = valid

    def as_dict(self):
        result = {"value": self.value, "unit": self.unit, "valid": self.valid}
        if self.kind is not None:
            result["kind"] = self.kind
        return result


class FakeService:
    def __init__(self, events, name):
        self.events = events
        self.name = name

    def configure(self, config):
        self.events.append((self.name, "configure", config))
        return True

    def init(self):
        self.events.append((self.name, "init"))
        return True

    def start(self):
        self.events.append((self.name, "start"))
        return True

    def stop(self):
        self.events.append((self.name, "stop"))
        return True

    def reset(self):
        self.events.append((self.name, "reset"))
        return True

    def status(self):
        return {"name": self.name}


class FakeDistance(FakeService):
    def distance(self):
        return Sample()

    def read_distance_mm(self):
        return 100

    def set_active(self, active):
        return bool(active)


class FakeMotor(FakeService):
    def command(self, direction, amount=1):
        self.events.append((self.name, "command", direction, amount))
        return True


class FakePosition(FakeService):
    def __init__(self, events, distance_observer):
        super().__init__(events, "position")
        self.distance_observer = distance_observer

    def position(self):
        return Sample(kind="linear")


class FakeSlide(FakeService):
    def __init__(self, events, motor, position):
        super().__init__(events, "slide")
        self.motor = motor
        self.position_observer = position

    def position(self):
        return self.position_observer.position()

    def move_to(self, target):
        return Sample(kind="linear", value=target)

    def get_position(self):
        return 100

    def goto_position(self, position_mm):
        return position_mm


def load_manifest(directory):
    return ServiceManifest.load(str(SERVICES / directory / "component.yaml"))


class RuntimeTests(unittest.TestCase):
    def test_all_service_manifests_load(self):
        for directory in (
            "interfaces", "distance_sensor", "motor_control",
            "distance_to_position", "linear_slide",
        ):
            manifest = load_manifest(directory)
            self.assertEqual(manifest.document["manifest"], "rp.service/v1")

    def build_runtime(self):
        events = []
        runtime = ServiceSupervisor()
        runtime.register(
            "distance", load_manifest("distance_sensor"),
            factory=lambda: FakeDistance(events, "distance"),
            implementation="vl53l4cd",
        )
        runtime.register(
            "motor", load_manifest("motor_control"),
            factory=lambda: FakeMotor(events, "motor"),
            implementation="step_dir",
        )
        runtime.register(
            "position", load_manifest("distance_to_position"),
            factory=lambda distance_observer: FakePosition(events, distance_observer),
        )
        runtime.register(
            "slide", load_manifest("linear_slide"),
            factory=lambda motor, position: FakeSlide(events, motor, position),
        )
        return runtime, events

    def test_capabilities_bind_and_start_in_dependency_order(self):
        runtime, events = self.build_runtime()
        self.assertEqual(runtime.prepare(), ["distance", "motor", "position", "slide"])
        self.assertIs(runtime.instance("position").distance_observer,
                      runtime.instance("distance"))
        self.assertIs(runtime.instance("slide").motor, runtime.instance("motor"))
        self.assertEqual(runtime.start(), ["distance", "motor", "position", "slide"])
        self.assertTrue(runtime.stop())
        stops = [event[0] for event in events if event[1] == "stop"]
        self.assertEqual(stops, ["slide", "position", "motor", "distance"])

    def test_declared_operation_invocation_and_argument_allowlist(self):
        runtime, _ = self.build_runtime()
        runtime.start()
        sample = runtime.invoke("slide", "move_to", {"target": 0.25})
        self.assertEqual(sample.value, 0.25)
        with self.assertRaises(LifecycleError):
            runtime.invoke("slide", "move_to", {"target": 0.25, "unsafe": True})

    def test_implementation_specific_operation_is_enforced(self):
        events = []
        runtime = ServiceSupervisor()
        runtime.register(
            "servo", load_manifest("motor_control"),
            factory=lambda: FakeMotor(events, "servo"),
            implementation="pwm_servo",
        )
        runtime.start()
        with self.assertRaises(LifecycleError):
            runtime.invoke("servo", "command", {"direction": True, "amount": 1})

    def test_manifest_tests_execute_and_hardware_tests_require_approval(self):
        runtime, events = self.build_runtime()
        runtime.start()
        runner = ManifestTestRunner(runtime)
        result = runner.run("slide", "observe_position")
        self.assertTrue(result["passed"])
        with self.assertRaises(ManifestTestError):
            runner.run("slide", "move_to_target", parameters={"target": 0.2})
        result = runner.run(
            "slide", "move_to_target", parameters={"target": 0.2},
            allow_manual=True,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["steps"][0]["result"].value, 0.2)

    def test_ambiguous_capabilities_require_explicit_binding(self):
        runtime, _ = self.build_runtime()
        runtime.register(
            "position_backup", load_manifest("distance_to_position"),
            factory=lambda distance_observer: FakePosition([], distance_observer),
            bindings={"distance_observer": "distance"},
        )
        with self.assertRaises(ResolutionError):
            runtime.prepare()


if __name__ == "__main__":
    unittest.main()
