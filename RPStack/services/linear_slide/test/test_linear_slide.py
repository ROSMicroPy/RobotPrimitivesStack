from pathlib import Path
import sys
import unittest
import _thread
import asyncio
import time

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

    def command_blocking(self, direction, amount, cancelled):
        return self.command(direction, amount)

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
    async def make_slide(self, value=0.0, **kwargs):
        observer = FakePositionObserver(value)
        motor = FakeMotor(observer)
        slide = LinearSlide(motor=motor, position=observer)
        if "tolerance_mm" in kwargs:
            kwargs["tolerance_m"] = kwargs.pop("tolerance_mm") / 1000
        slide.configure(kwargs)
        await slide.init()
        motor.commands.clear()
        motor.stopped = False
        return slide, motor

    async def test_init_calibrates_reversed_direction_and_scale(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        def reversed_command(direction, amount=1):
            motor.commands.append((direction, amount))
            observer.value += (-1 if direction else 1) * amount * 0.00025
            return True
        motor.command = reversed_command
        slide = LinearSlide(motor, observer)
        self.assertTrue(await slide.init())
        self.assertEqual(motor.commands, [(True, 1000), (False, 1000)])
        self.assertFalse(slide.positive_direction)
        self.assertAlmostEqual(slide.steps_per_mm, 4)
        self.assertAlmostEqual(observer.value, 0)
        final = await slide.move_to(0.01)
        self.assertLessEqual(abs(final.value - 0.01), slide.tolerance_m)

    async def test_failed_calibration_prevents_moves(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        motor.command = lambda *args: True
        slide = LinearSlide(motor, observer)
        with self.assertRaisesRegex(RuntimeError, "No position change"):
            await slide.init()
        self.assertIsNone(slide.steps_per_mm)
        self.assertTrue(motor.stopped)
        with self.assertRaisesRegex(RuntimeError, "initialized"):
            await slide.move_to(0.1)

    async def test_worker_finishes_before_measurement_and_restarts(self):
        slide, motor = await self.make_slide(tolerance_m=0)
        main_thread = _thread.get_ident()
        workers = []
        original = motor.command
        def command(direction, amount):
            workers.append(_thread.get_ident())
            return original(direction, amount)
        motor.command = command
        observations = []
        def observe():
            self.assertEqual(_thread.get_ident(), main_thread)
            observations.append(motor.observer.value)
            return PositionSample("linear", motor.observer.value, "m", "test")
        slide.position_observer.position = observe
        await slide.move_to(0.025)
        self.assertEqual(len(workers), 2)
        self.assertTrue(all(worker != main_thread for worker in workers))
        self.assertEqual(observations, [0, 0.024, 0.025])

    async def test_cancellation_waits_for_worker(self):
        slide, motor = await self.make_slide()
        started = _thread.allocate_lock()
        started.acquire()
        finished = []
        def blocking(direction, steps, cancelled):
            started.release()
            while not cancelled():
                time.sleep(0.001)
            finished.append(True)
            return True
        motor.command_blocking = blocking
        move = asyncio.create_task(slide.move_to(0.1))
        while not started.acquire(False):
            await asyncio.sleep(0.001)
        move.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await move
        self.assertTrue(finished)
        self.assertFalse(slide._busy)
        self.assertIsNone(slide.status()["target_m"])

    async def test_async_capability_remains_on_main_loop(self):
        slide, motor = await self.make_slide(tolerance_m=0, max_steps=3)
        original = motor.command
        main_thread = _thread.get_ident()
        async def command(direction, amount):
            self.assertEqual(_thread.get_ident(), main_thread)
            await asyncio.sleep(0)
            return original(direction, amount)
        motor.command_blocking = None
        motor.command = command
        final = await slide.move_to(0.003)
        self.assertAlmostEqual(final.value, 0.003)

    async def test_invalid_calibration_sample_stops_before_motion(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        observer.value = float("nan")
        slide = LinearSlide(motor, observer)
        with self.assertRaisesRegex(RuntimeError, "invalid sample"):
            await slide.init()
        self.assertEqual(motor.commands, [])
        self.assertTrue(motor.stopped)

    async def test_runtime_bound_capabilities_drive_composite(self):
        slide, _ = await self.make_slide(tolerance_mm=0, max_steps=10)
        final = await slide.move_to(0.003)
        self.assertAlmostEqual(final.value, 0.003)
        self.assertEqual(final.unit, "m")

    async def test_move_batches_steps_and_tapers_near_target(self):
        slide, motor = await self.make_slide(
            tolerance_mm=0, max_steps=30, steps_per_sample=10)
        final = await slide.move_to(0.025)
        self.assertAlmostEqual(final.value, 0.025)
        self.assertEqual([amount for _, amount in motor.commands], [24, 1])

    async def test_move_stops_when_position_repeatedly_moves_away(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        original_command = motor.command

        def reverse_command(direction, amount=1):
            return original_command(not direction, amount)

        slide = LinearSlide(motor=motor, position=observer)
        await slide.init()
        motor.command = reverse_command
        slide.configure(dict(tolerance_m=0, max_steps=10000, steps_per_sample=10))
        with self.assertRaisesRegex(RuntimeError, "invert positive_direction"):
            await slide.move_to(0.1)
        self.assertTrue(motor.stopped)

    async def test_move_stops_when_no_position_change_is_observed(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)

        def stalled_command(direction, amount=1):
            motor.commands.append((direction, amount))
            return True

        slide = LinearSlide(motor=motor, position=observer)
        await slide.init()
        motor.commands.clear()
        motor.command = stalled_command
        slide.configure(dict(tolerance_m=0, max_steps=100, steps_per_sample=10, no_motion_sample_limit=3))
        with self.assertRaisesRegex(RuntimeError, "No position change"):
            await slide.move_to(0.003)
        self.assertTrue(motor.stopped)
        self.assertEqual(sum(amount for _, amount in motor.commands), 6)

    async def test_jog_steps_bypasses_closed_loop_targeting(self):
        slide, motor = await self.make_slide()
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
        slide, _ = await self.make_slide(tolerance_mm=0, max_steps=10)
        self.assertEqual(await slide.gotoPosition(2), 2)
        self.assertEqual(await slide.getPosition(), 2)

    async def test_composite_does_not_shutdown_runtime_owned_dependencies(self):
        slide, motor = await self.make_slide()
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
        slide, motor = await self.make_slide()
        async def broken():
            raise RuntimeError("sensor unavailable")
        slide.position_observer.position = broken
        with self.assertRaisesRegex(RuntimeError, "sensor unavailable"):
            await slide.move_to(0.1)
        self.assertIsNone(slide.status()["target_m"])
        self.assertTrue(motor.stopped)


if __name__ == "__main__":
    unittest.main()
