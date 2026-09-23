from pathlib import Path
import sys
import unittest

COMPONENT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = COMPONENT_DIR.parent
for component in ("interfaces", "distance_to_position", "linear_slide"):
    sys.path.insert(0, str(SERVICES_DIR / component / "src"))

for runtime_src in (SERVICES_DIR.parent / "runtime").glob("*/src"):
    sys.path.insert(0, str(runtime_src))

from rpstack.distance_to_position import DistanceToPositionAdapter
from rpstack.linear_slide import LinearSlide
from rpstack.interfaces import DistanceSample, PositionSample


class FakePositionObserver:
    def __init__(self, value=0.0):
        self.value = value

    def position(self):
        return PositionSample("linear", self.value, "m", "test.carriage")


class FakeMotor:
    def __init__(self, observer):
        self.observer = observer
        self.stopped = False
        self.shutdown_called = False
        self.commands = []

    def command(self, direction, amount=1):
        self.commands.append((direction, amount))
        delta = 0.001 * amount
        self.observer.value += delta if direction else -delta
        return True

    def stop(self):
        self.stopped = True
        return True

    def shutdown(self):
        self.shutdown_called = True
        return True


class FakeDistanceObserver:
    def __init__(self, value):
        self.value = value

    def distance(self):
        return DistanceSample(self.value, "m", quality=0.75)


class LinearSlideTests(unittest.IsolatedAsyncioTestCase):
    def make_slide(self, value=0.0, **kwargs):
        observer = FakePositionObserver(value)
        motor = FakeMotor(observer)
        slide = LinearSlide(motor=motor, position=observer)
        if "tolerance_mm" in kwargs:
            kwargs["tolerance_m"] = kwargs.pop("tolerance_mm") / 1000
        slide.configure(kwargs)
        return slide, motor

    async def test_runtime_bound_capabilities_drive_composite(self):
        slide, _ = self.make_slide(tolerance_mm=0, max_steps=10)
        final = await slide.move_to(0.003)
        self.assertAlmostEqual(final.value, 0.003)
        self.assertEqual(final.unit, "m")

    async def test_move_batches_steps_and_tapers_near_target(self):
        slide, motor = self.make_slide(
            tolerance_mm=0, max_steps=30, steps_per_sample=10)
        final = await slide.move_to(0.025)
        self.assertAlmostEqual(final.value, 0.025)
        self.assertEqual([amount for _, amount in motor.commands], [10, 10, 5])

    async def test_move_stops_when_position_repeatedly_moves_away(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        original_command = motor.command

        def reverse_command(direction, amount=1):
            return original_command(not direction, amount)

        motor.command = reverse_command
        slide = LinearSlide(motor=motor, position=observer)
        slide.configure(dict(tolerance_m=0, max_steps=100, steps_per_sample=10))
        with self.assertRaisesRegex(RuntimeError, "invert positive_direction"):
            await slide.move_to(0.1)
        self.assertTrue(motor.stopped)

    async def test_move_stops_when_no_position_change_is_observed(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)

        def stalled_command(direction, amount=1):
            motor.commands.append((direction, amount))
            return True

        motor.command = stalled_command
        slide = LinearSlide(motor=motor, position=observer)
        slide.configure(dict(tolerance_m=0, max_steps=100, steps_per_sample=10, no_motion_sample_limit=3))
        with self.assertRaisesRegex(RuntimeError, "No position change"):
            await slide.move_to(0.1)
        self.assertTrue(motor.stopped)
        self.assertEqual(sum(amount for _, amount in motor.commands), 30)

    async def test_jog_steps_bypasses_closed_loop_targeting(self):
        slide, motor = self.make_slide()
        result = await slide.jog_steps(5, False)
        self.assertEqual(result["steps"], 5)
        self.assertFalse(result["direction"])
        self.assertAlmostEqual(result["position_before"]["value"], 0.0)
        self.assertAlmostEqual(result["position_after"]["value"], -0.005)
        self.assertEqual(motor.commands, [(False, 5)])

    async def test_manifest_position_role_name_binds_to_constructor(self):
        observer = FakePositionObserver()
        slide = LinearSlide(motor=FakeMotor(observer), position=observer)
        self.assertIs(slide.position_observer, observer)

    async def test_legacy_mm_api_is_preserved(self):
        slide, _ = self.make_slide(tolerance_mm=0, max_steps=10)
        self.assertEqual(await slide.gotoPosition(2), 2)
        self.assertEqual(await slide.getPosition(), 2)

    async def test_composite_does_not_shutdown_runtime_owned_dependencies(self):
        slide, motor = self.make_slide()
        self.assertTrue(slide.shutdown())
        self.assertTrue(motor.stopped)
        self.assertFalse(motor.shutdown_called)

    async def test_distance_adapter_owns_installation_transform(self):
        adapter = DistanceToPositionAdapter(
            FakeDistanceObserver(0.2), zero_offset_m=0.5, direction=-1,
            reference_frame="lift.base",
        )
        sample = await adapter.position()
        self.assertAlmostEqual(sample.value, 0.3)
        self.assertEqual(sample.reference_frame, "lift.base")
        self.assertEqual(sample.quality, 0.75)

    async def test_initial_observation_failure_clears_target_and_stops(self):
        slide, motor = self.make_slide()
        async def broken():
            raise RuntimeError("sensor unavailable")
        slide.position_observer.position = broken
        with self.assertRaisesRegex(RuntimeError, "sensor unavailable"):
            await slide.move_to(0.1)
        self.assertIsNone(slide.status()["target_m"])
        self.assertTrue(motor.stopped)


if __name__ == "__main__":
    unittest.main()
