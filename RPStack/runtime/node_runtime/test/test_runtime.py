from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest


ROOT = Path(__file__).resolve().parents[3]


from rpstack.node_runtime import (  # noqa: E402
    LifecycleError,
    ManifestTestError,
    ManifestTestRunner,
    ResolutionError,
    ServiceManifest,
    ServiceSupervisor,
)


SERVICES = ROOT / "services"


class Sample:
    # Create a minimal measurement substitute for manifest-operation assertions.
    def __init__(self, kind=None, value=0.1, unit="m", valid=True):
        self.kind = kind
        self.value = value
        self.unit = unit
        self.valid = valid

    # Serialize the fake measurement, adding position kind only when supplied.
    def as_dict(self):
        result = {"value": self.value, "unit": self.unit, "valid": self.valid}
        if self.kind is not None:
            result["kind"] = self.kind
        return result


class FakeService:
    # Bind a fake service identity to the shared lifecycle event log.
    def __init__(self, events, name):
        self.events = events
        self.name = name

    # Record configuration delivery for dependency-order assertions.
    def configure(self, config):
        self.events.append((self.name, "configure", config))
        return True

    # Record successful service initialization.
    def init(self):
        self.events.append((self.name, "init"))
        return True

    # Record successful entry into the running phase.
    def start(self):
        self.events.append((self.name, "start"))
        return True

    # Record service stopping so reverse dependency order can be checked.
    def stop(self):
        self.events.append((self.name, "stop"))
        return True

    # Record an explicit reset hook invocation if one occurs.
    def reset(self):
        self.events.append((self.name, "reset"))
        return True

    # Expose the fake service's identity as its status snapshot.
    def status(self):
        return {"name": self.name}


class FakeDistance(FakeService):
    # Return a fixed canonical distance sample.
    def distance(self):
        return Sample()


    # Echo the requested activation value for manifest operation tests.
    def set_active(self, active):
        return bool(active)


class FakeMotor(FakeService):
    # Record relative motion arguments and acknowledge the fake command.
    def command(self, direction, amount=1):
        self.events.append((self.name, "command", direction, amount))
        return True


class FakePosition(FakeService):
    # Retain the injected distance provider for dependency-binding checks.
    def __init__(self, events, distance_observer):
        super().__init__(events, "position")
        self.distance_observer = distance_observer

    # Return a fixed linear position sample.
    def position(self):
        return Sample(kind="linear")


class FakeSlide(FakeService):
    # Retain injected motor and position capabilities for composite-service assertions.
    def __init__(self, events, motor, position):
        super().__init__(events, "slide")
        self.motor = motor
        self.position_observer = position

    # Read position through the injected provider.
    def position(self):
        return self.position_observer.position()

    # Simulate successful arrival by returning the requested target as a position sample.
    def move_to(self, target):
        return Sample(kind="linear", value=target)




# Load a service's component contract from its YAML manifest.
def load_manifest(directory):
    folder = ROOT / "foundation" / directory if directory == "interfaces" else SERVICES / directory
    return ServiceManifest.load(str(folder / "component.yaml"))


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    # Validate that each supplied service manifest uses the supported contract schema.
    async def test_all_service_manifests_load(self):
        for directory in (
            "interfaces", "distance_sensor", "motor_control",
            "distance_to_position", "linear_slide",
        ):
            manifest = load_manifest(directory)
            self.assertEqual(manifest.document["manifest"], "rp.service/v1")

    # Assemble fake distance, motor, position, and slide services with real manifests.
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

    # Verify dependency injection, provider-first startup, and consumer-first shutdown.
    async def test_capabilities_bind_and_start_in_dependency_order(self):
        runtime, events = self.build_runtime()
        self.assertEqual(await runtime.prepare(), ["distance", "motor", "position", "slide"])
        self.assertIs(runtime.instance("position").distance_observer,
                      runtime.instance("distance"))
        self.assertIs(runtime.instance("slide").motor, runtime.instance("motor"))
        self.assertEqual(await runtime.start(), ["distance", "motor", "position", "slide"])
        self.assertTrue(await runtime.stop())
        stops = [event[0] for event in events if event[1] == "stop"]
        self.assertEqual(stops, ["slide", "position", "motor", "distance"])

    # Check declared operation dispatch and rejection of undeclared arguments.
    async def test_declared_operation_invocation_and_argument_allowlist(self):
        runtime, _ = self.build_runtime()
        await runtime.start()
        sample = await runtime.invoke("slide", "move_to", {"target": 0.25})
        self.assertEqual(sample.value, 0.25)
        with self.assertRaises(LifecycleError):
            await runtime.invoke("slide", "move_to", {"target": 0.25, "unsafe": True})

    # Ensure a servo implementation cannot invoke a stepper-only operation.
    async def test_implementation_specific_operation_is_enforced(self):
        events = []
        runtime = ServiceSupervisor()
        runtime.register(
            "servo", load_manifest("motor_control"),
            factory=lambda: FakeMotor(events, "servo"),
            implementation="pwm_servo",
        )
        await runtime.start()
        with self.assertRaises(LifecycleError):
            await runtime.invoke("servo", "command", {"direction": True, "amount": 1})

    # Exercise automatic manifest tests and the explicit opt-in gate for manual motion
    # scenarios.
    async def test_manifest_tests_execute_and_hardware_tests_require_approval(self):
        runtime, events = self.build_runtime()
        await runtime.start()
        runner = ManifestTestRunner(runtime)
        result = await runner.run("slide", "observe_position")
        self.assertTrue(result["passed"])
        with self.assertRaises(ManifestTestError):
            await runner.run("slide", "move_to_target", parameters={"target": 0.2})
        result = await runner.run(
            "slide", "move_to_target", parameters={"target": 0.2},
            allow_manual=True,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["steps"][0]["result"].value, 0.2)

    # Reject automatic dependency resolution when multiple compatible providers exist.
    async def test_ambiguous_capabilities_require_explicit_binding(self):
        runtime, _ = self.build_runtime()
        runtime.register(
            "position_backup", load_manifest("distance_to_position"),
            factory=lambda distance_observer: FakePosition([], distance_observer),
            bindings={"distance_observer": "distance"},
        )
        with self.assertRaises(ResolutionError):
            await runtime.prepare()


if __name__ == "__main__":
    unittest.main()
