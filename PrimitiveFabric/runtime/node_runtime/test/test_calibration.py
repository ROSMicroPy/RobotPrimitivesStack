"""Explicit calibration is a managed lifecycle phase, never a boot side effect."""
import asyncio
import unittest
from test_runtime import ServiceSupervisor, LifecycleError
from rpstack.node_runtime.supervisor import BusyError


# Build a minimal service contract with optional sensor dependency and calibration hook.
def contract(name, dependency=False, calibrates=True):
    lifecycle = {'init': 'init'}
    if calibrates:
        lifecycle['calibrate'] = 'calibrate'
    return {'manifest': 'rp.service/v1', 'service': {
        'name': name, 'version': '1', 'kind': 'test', 'type': name,
        'lifecycle': lifecycle,
        'capabilities': {'provides': [{'interface': name, 'version': 1}],
                         'requires': {'sensor': {'interface': 'sensor', 'version': 1}} if dependency else {}},
        'operations': {'touch': {'method': 'touch', 'arguments': {}},
                       'calibrate': {'method': 'calibrate', 'arguments': {'offset': {'type': 'integer', 'default': 0}}}},
    }}


class Device:
    # Prepare a lifecycle event log and controllable calibration wait/failure behavior.
    def __init__(self, name, events, sensor=None):
        self.name, self.events, self.sensor = name, events, sensor
        self.waiting = None
        self.fail = False
    # Record initialization so tests can distinguish startup from calibration.
    def init(self):
        self.events.append(('init', self.name))
        return True
    # Record calibration, optionally block or fail, and otherwise return the requested offset.
    async def calibrate(self, offset=0):
        self.events.append(('calibrate', self.name))
        if self.waiting:
            await self.waiting.wait()
        if self.fail:
            return False
        return {'offset': offset}
    # Provide a trivial operation for checking resource admission during calibration.
    def touch(self):
        return True


class CalibrationTests(unittest.IsolatedAsyncioTestCase):
    # Start a dependency graph containing calibrating and passive services.
    async def asyncSetUp(self):
        self.events = []
        self.node = ServiceSupervisor()
        self.node.register('slide', contract('slide', dependency=True),
            factory=lambda sensor: Device('slide', self.events, sensor))
        self.node.register('sensor', contract('sensor'),
            factory=lambda: Device('sensor', self.events))
        self.node.register('passive', contract('passive', calibrates=False),
            factory=lambda: Device('passive', self.events))
        await self.node.start()

    # Stop services and resident tasks after each calibration scenario.
    async def asyncTearDown(self):
        await self.node.stop()

    # Verify calibration is explicit, dependency-ordered, skips passive services, and resets to
    # pending.
    async def test_explicit_phase_orders_dependencies_and_skips_unsupported(self):
        self.assertNotIn(('calibrate', 'sensor'), self.events)
        self.assertEqual(self.node.calibration_status()['slide']['state'], 'pending')
        report = await self.node.calibrate(arguments={'slide': {'offset': 3}})
        self.assertEqual([name for phase, name in self.events if phase == 'calibrate'], ['sensor', 'slide'])
        self.assertEqual(report['slide']['result'], {'offset': 3})
        self.assertEqual(report['passive']['state'], 'not_required')
        await self.node.reset()
        self.assertEqual(self.node.calibration_status()['slide']['state'], 'pending')

    # Check that calibration reserves dependencies until cancellation completes.
    async def test_cancellation_holds_then_releases_claims(self):
        self.node.instance('sensor').waiting = asyncio.Event()
        task = self.node.submit_calibration()
        await asyncio.sleep(0)
        self.assertEqual(self.node.calibration_status()['sensor']['state'], 'running')
        with self.assertRaises(BusyError):
            self.node.submit('slide', 'touch')
        await self.node.tasks.cancel(task)
        self.assertEqual(self.node.calibration_status()['sensor']['state'], 'cancelled')
        self.assertEqual(self.node._claims, {})

    # Ensure a failed provider calibration blocks consumers and releases resource claims.
    async def test_failed_dependency_prevents_later_calibration(self):
        self.node.instance('sensor').fail = True
        with self.assertRaisesRegex(RuntimeError, 'calibration failed'):
            await self.node.calibrate()
        self.assertNotIn(('calibrate', 'slide'), self.events)
        self.assertEqual(self.node.calibration_status()['sensor']['state'], 'failed')
        self.assertEqual(self.node._claims, {})

    # Verify invoking the calibration operation updates lifecycle calibration status.
    async def test_operation_dispatch_updates_lifecycle_state(self):
        result = await self.node.invoke('slide', 'calibrate', {'offset': 8})
        self.assertEqual(result, {'offset': 8})
        self.assertEqual(self.node.calibration_status()['slide']['state'], 'calibrated')

    # Reject malformed calibration arguments before any hook runs or resources are claimed.
    async def test_all_arguments_validated_before_any_calibration(self):
        for arguments in ([], False, '', {'slide': {'offset': 'bad'}}):
            with self.assertRaises(LifecycleError):
                await self.node.calibrate(arguments=arguments)
        self.assertFalse(any(phase == 'calibrate' for phase, _ in self.events))
        self.assertEqual(self.node._claims, {})
