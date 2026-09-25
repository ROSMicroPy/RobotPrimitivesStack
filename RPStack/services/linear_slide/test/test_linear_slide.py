from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest
import _thread
import asyncio
import time

COMPONENT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = COMPONENT_DIR.parent


from rpstack.distance_to_position import DistanceToPositionAdapter
from rpstack.linear_slide import LinearSlide
from rpstack.interfaces import DistanceSample, PositionSample


class FakePositionObserver:
    # Store a mutable simulated carriage position.
    def __init__(self, value=0.0):
        self.value = value

    # Expose the simulated carriage value as a canonical linear position sample.
    def position(self):
        return PositionSample("linear", self.value, "m", "test.carriage")


class FakeMotor:
    # Connect simulated motion to the observer and prepare command/cleanup histories.
    def __init__(self, observer):
        self.observer = observer
        self.stopped = False
        self.shutdown_called = False
        self.commands = []

    # Record a command and move the simulated carriage one millimetre per signed step.
    def command(self, direction, amount=1):
        self.commands.append((direction, amount))
        delta = 0.001 * amount
        self.observer.value += delta if direction else -delta
        return True

    # Expose the same simulated movement through the worker-thread capability interface.
    def command_blocking(self, direction, amount, cancelled):
        return self.command(direction, amount)

    # Record a stop request without releasing the simulated motor.
    def stop(self):
        self.stopped = True
        return True

    # Record dependency shutdown so ownership assertions can detect unwanted calls.
    def shutdown(self):
        self.shutdown_called = True
        return True


class FakeDistanceObserver:
    # Store a fixed raw distance for installation-transform tests.
    def __init__(self, value):
        self.value = value

    # Return the raw distance with known quality metadata.
    def distance(self):
        return DistanceSample(self.value, "m", quality=0.75)


class LinearSlideTests(unittest.IsolatedAsyncioTestCase):
    # Build and calibrate a simulated slide, then clear setup motion from assertion history.
    async def make_slide(self, value=0.0, **kwargs):
        observer = FakePositionObserver(value)
        motor = FakeMotor(observer)
        slide = LinearSlide(motor=motor, position=observer)
        if "tolerance_mm" in kwargs:
            kwargs["tolerance_m"] = kwargs.pop("tolerance_mm") / 1000
        slide.init()
        await slide.calibrate()
        slide.configure(kwargs)
        motor.commands.clear()
        motor.stopped = False
        return slide, motor

    # Verify invalid range updates preserve prior bounds and out-of-range targets never command
    # motion.
    async def test_range_updates_are_atomic_and_targets_are_bounded(self):
        slide, motor = await self.make_slide(value=.1)
        self.assertEqual(slide.set_range(30, 300), {'min_mm': 30, 'max_mm': 300})
        for bounds in [(300, 30), (30, 30), (float('nan'), 300), (30, float('inf')), (True, 300)]:
            with self.assertRaises(ValueError):
                slide.set_range(*bounds)
            self.assertEqual(slide.get_range(), {'min_mm': 30, 'max_mm': 300})
        for target in (.029, .301):
            with self.assertRaises(ValueError):
                await slide.move_to(target)
        self.assertEqual(motor.commands, [])
        for target in (.03, .3):
            slide._validate_target(target)
        slide._busy = True
        with self.assertRaises(RuntimeError):
            slide.set_range(40, 200)
        self.assertEqual(slide.status()['range_mm'], {'min_mm': 30, 'max_mm': 300})

    # Exercise a dense stepper scale against the demo's configured movement budget.
    async def test_high_step_density_move_uses_demo_budget(self):
        import json
        doc = json.loads((SERVICES_DIR.parent.parent / 'examples/slide_nodes/node1.device.json').read_text())
        observer = FakePositionObserver(.1)
        motor = FakeMotor(observer)
        # Simulate a high number of motor steps per metre while recording batches.
        def command(direction, amount=1):
            motor.commands.append((direction, amount))
            observer.value += (1 if direction else -1) * amount / 222222.222
            return True
        motor.command = command
        slide = LinearSlide(motor, observer)
        slide.configure(doc['services']['slide']['config'])
        await slide.calibrate(1000)
        motor.commands.clear()
        result = await slide.move_to(.2)
        self.assertLessEqual(abs(result.value - .2), slide.tolerance_m)
        self.assertGreater(sum(n for _, n in motor.commands), 10000)

    # Ensure initialization causes no motion and positioning requires explicit calibration.
    async def test_init_is_stationary_and_uncalibrated_moves_fail(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        slide = LinearSlide(motor, observer)
        self.assertTrue(slide.init())
        self.assertEqual(motor.commands, [])
        with self.assertRaisesRegex(RuntimeError, "calibrate"):
            await slide.move_to(.1)
        self.assertEqual(motor.commands, [])

    # Verify calibration measurements occur only between complete forward/backward motor runs.
    async def test_calibrate_samples_only_after_uninterrupted_runs(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        moving = [False]
        observed = []
        original = motor.command
        # Mark simulated motor execution so measurements can detect overlap.
        def command(direction, steps):
            moving[0] = True
            try:
                return original(direction, steps)
            finally:
                moving[0] = False
        # Assert the motor is idle before capturing a calibration sample.
        def measure():
            self.assertFalse(moving[0])
            observed.append(observer.value)
            return PositionSample("linear", observer.value, "m", "test")
        motor.command = command
        observer.position = measure
        slide = LinearSlide(motor, observer)
        report = await slide.calibrate(200)
        self.assertEqual(motor.commands, [(True, 200), (False, 200)])
        self.assertEqual(observed, [0, .2, 0])
        self.assertEqual(report['steps_per_mm'], 1)
        self.assertTrue(report['positive_direction'])
        self.assertEqual(slide.status()['pulse_mode'], 'blocking_worker')

    # Verify calibration discovers reversed motion polarity and the actual steps-per-millimetre
    # scale.
    async def test_calibrate_calibrates_reversed_direction_and_scale(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        # Simulate reversed wiring and quarter-millimetre steps for calibration.
        def reversed_command(direction, amount=1):
            motor.commands.append((direction, amount))
            observer.value += (-1 if direction else 1) * amount * 0.00025
            return True
        motor.command = reversed_command
        slide = LinearSlide(motor, observer)
        self.assertTrue(await slide.calibrate())
        self.assertEqual(motor.commands, [(True, 1000), (False, 1000)])
        self.assertFalse(slide.positive_direction)
        self.assertAlmostEqual(slide.steps_per_mm, 4)
        self.assertAlmostEqual(observer.value, 0)
        final = await slide.move_to(0.01)
        self.assertLessEqual(abs(final.value - 0.01), slide.tolerance_m)

    # Ensure motionless calibration fails, stops the motor, and leaves positioning disabled.
    async def test_failed_calibration_prevents_moves(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        motor.command = lambda *args: True
        slide = LinearSlide(motor, observer)
        with self.assertRaisesRegex(RuntimeError, "before_mm=0.*after_mm=0.*delta_mm=0.*required_mm=2"):
            await slide.calibrate()
        self.assertIsNone(slide.steps_per_mm)
        self.assertTrue(motor.stopped)
        with self.assertRaisesRegex(RuntimeError, "calibrate"):
            await slide.move_to(0.1)

    # Verify pulses run off-thread and position observations occur between worker batches.
    async def test_worker_finishes_before_measurement_and_restarts(self):
        slide, motor = await self.make_slide(tolerance_m=0)
        main_thread = _thread.get_ident()
        workers = []
        original = motor.command
        # Record the executing thread before applying simulated movement.
        def command(direction, amount):
            workers.append(_thread.get_ident())
            return original(direction, amount)
        motor.command = command
        observations = []
        # Assert observations stay on the main thread and retain sampled positions.
        def observe():
            self.assertEqual(_thread.get_ident(), main_thread)
            observations.append(motor.observer.value)
            return PositionSample("linear", motor.observer.value, "m", "test")
        slide.position_observer.position = observe
        await slide.move_to(0.025)
        self.assertEqual(len(workers), 2)
        self.assertTrue(all(worker != main_thread for worker in workers))
        self.assertEqual(observations, [0, 0.024, 0.025])

    # Ensure cancellation waits for the pulse worker and clears busy/target state.
    async def test_cancellation_waits_for_worker(self):
        slide, motor = await self.make_slide()
        started = _thread.allocate_lock()
        started.acquire()
        finished = []
        # Signal worker startup and remain active until the cancellation callback requests a
        # stop.
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

    # Verify fallback asynchronous motor capabilities execute on the main event loop.
    async def test_async_capability_remains_on_main_loop(self):
        slide, motor = await self.make_slide(tolerance_m=0, max_steps=3)
        original = motor.command
        main_thread = _thread.get_ident()
        # Assert main-thread execution before yielding and applying simulated motion.
        async def command(direction, amount):
            self.assertEqual(_thread.get_ident(), main_thread)
            await asyncio.sleep(0)
            return original(direction, amount)
        motor.command_blocking = None
        motor.command = command
        final = await slide.move_to(0.003)
        self.assertAlmostEqual(final.value, 0.003)

    # Ensure an invalid initial observation prevents calibration movement and stops the motor.
    async def test_invalid_calibration_sample_stops_before_motion(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        observer.value = float("nan")
        slide = LinearSlide(motor, observer)
        with self.assertRaisesRegex(RuntimeError, "invalid sample"):
            await slide.calibrate()
        self.assertEqual(motor.commands, [])
        self.assertTrue(motor.stopped)

    # Check that injected motion and position capabilities cooperate to reach a target.
    async def test_runtime_bound_capabilities_drive_composite(self):
        slide, _ = await self.make_slide(tolerance_mm=0, max_steps=10)
        final = await slide.move_to(0.003)
        self.assertAlmostEqual(final.value, 0.003)
        self.assertEqual(final.unit, "m")

    # Verify movement uses a large approach batch followed by a small final correction.
    async def test_move_batches_steps_and_tapers_near_target(self):
        slide, motor = await self.make_slide(
            tolerance_mm=0, max_steps=30)
        final = await slide.move_to(0.025)
        self.assertAlmostEqual(final.value, 0.025)
        self.assertEqual([amount for _, amount in motor.commands], [24, 1])

    # Ensure motion opposite the calibrated direction raises an error and stops the motor.
    async def test_move_stops_when_position_repeatedly_moves_away(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)
        original_command = motor.command

        # Reverse a previously calibrated motor's direction to simulate changed wiring.
        def reverse_command(direction, amount=1):
            return original_command(not direction, amount)

        slide = LinearSlide(motor=motor, position=observer)
        await slide.calibrate()
        motor.command = reverse_command
        slide.configure(dict(tolerance_m=0, max_steps=10000))
        with self.assertRaisesRegex(RuntimeError, "positive_direction"):
            await slide.move_to(0.1)
        self.assertTrue(motor.stopped)

    # Verify repeated stationary observations trip the no-motion limit and stop movement.
    async def test_move_stops_when_no_position_change_is_observed(self):
        observer = FakePositionObserver()
        motor = FakeMotor(observer)

        # Record accepted step commands without changing the simulated carriage position.
        def stalled_command(direction, amount=1):
            motor.commands.append((direction, amount))
            return True

        slide = LinearSlide(motor=motor, position=observer)
        await slide.calibrate()
        motor.commands.clear()
        motor.command = stalled_command
        slide.configure(dict(tolerance_m=0, max_steps=100, no_motion_sample_limit=3))
        with self.assertRaisesRegex(RuntimeError, "No position change"):
            await slide.move_to(0.003)
        self.assertTrue(motor.stopped)
        self.assertEqual(sum(amount for _, amount in motor.commands), 6)

    # Verify a fixed signed jog reports before/after positions without target seeking.
    async def test_jog_steps_bypasses_closed_loop_targeting(self):
        slide, motor = await self.make_slide()
        result = await slide.jog_steps(5, False)
        self.assertEqual(result["steps"], 5)
        self.assertFalse(result["direction"])
        self.assertAlmostEqual(result["position_before"]["value"], 0.0)
        self.assertAlmostEqual(result["position_after"]["value"], -0.005)
        self.assertEqual(motor.commands, [(False, 5)])

    # Check that the manifest's position dependency name matches the slide constructor.
    async def test_manifest_position_role_name_binds_to_constructor(self):
        observer = FakePositionObserver()
        slide = LinearSlide(motor=FakeMotor(observer), position=observer)
        self.assertIs(slide.position_observer, observer)

    # Ensure slide shutdown stops motion without releasing its runtime-owned motor.
    async def test_composite_does_not_shutdown_runtime_owned_dependencies(self):
        slide, motor = await self.make_slide()
        self.assertTrue(slide.shutdown())
        self.assertTrue(motor.stopped)
        self.assertFalse(motor.shutdown_called)

    # Check that the adapter owns offset, direction, frame, and quality propagation.
    async def test_distance_adapter_owns_installation_transform(self):
        adapter = DistanceToPositionAdapter(
            FakeDistanceObserver(0.2), zero_offset_m=0.5, direction=-1,
            reference_frame="lift.base",
        )
        sample = await adapter.position()
        self.assertAlmostEqual(sample.value, 0.3)
        self.assertEqual(sample.reference_frame, "lift.base")
        self.assertEqual(sample.quality, 0.75)

    # Verify an initial sensor failure clears the movement target and stops the motor.
    async def test_initial_observation_failure_clears_target_and_stops(self):
        slide, motor = await self.make_slide()
        # Inject an unavailable sensor before the first positioning observation.
        async def broken():
            raise RuntimeError("sensor unavailable")
        slide.position_observer.position = broken
        with self.assertRaisesRegex(RuntimeError, "sensor unavailable"):
            await slide.move_to(0.1)
        self.assertIsNone(slide.status()["target_m"])
        self.assertTrue(motor.stopped)


if __name__ == "__main__":
    unittest.main()
