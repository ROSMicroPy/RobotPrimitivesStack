"""Gateway semantics over real managed nodes and a lossy simulated transport."""
import asyncio
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[4]
for source in (ROOT / 'RPStack').glob('*/*/src'):
    sys.path.insert(0, str(source))
sys.path.insert(0, str(ROOT / 'examples/robie1'))
from simulation import MemoryTransport
from rpstack.node_runtime import NodeRuntime
from rpstack.apps.ros_gateway.controller import SlideController, position_sample
from rpstack.execution_engine.distributed import RemoteCancelled


class SimulatedSlide:
    def __init__(self, signals=None):
        self.signals = signals
        self.value, self.calls = 0.1, 0
        self.moving = self.cleaned = False
        self.duration = 0.12
        self.calibrated = True

    def status(self):
        return {'active': True, 'calibrated': self.calibrated,
                'range_mm': {'min_mm': 0, 'max_mm': 300}}

    def position(self):
        return dict(kind='linear', unit='m', value=self.value, valid=True,
                    quality=1.0, reference_frame='slide', timestamp_ns=123)

    async def move(self, target):
        self.calls += 1
        self.moving, self.cleaned = True, False
        try:
            await asyncio.sleep(self.duration / 2)
            self.value = (self.value + target) / 2
            self.signals.publish('motion.position.updated', dict(self.position(), service='slide'))
            await asyncio.sleep(self.duration / 2)
            self.value = target
            return self.position()
        finally:
            # Simulate asynchronous driver cleanup; confirmation must wait for it.
            await asyncio.sleep(0.02)
            self.moving, self.cleaned = False, True


def documents():
    base = {'manifest': 'rp.node/v1', 'name': 'gateway-test', 'components': {}, 'services': {},
            'identity': {'entity': 'RosGatewayTest', 'node': 'gateway'},
            'signals': {'routes': ['local', 'wire'], 'transports': [
                {'id': 'wire', 'entry_point': 'simulation:MemoryTransport'}]},
            'execution': {'peers': ['worker'], 'expose': [], 'lease_ms': 150}}
    import copy
    worker = copy.deepcopy(base)
    worker['identity']['node'] = 'worker'
    worker['execution'].update(peers=['gateway'], expose=['slide'])
    worker['components']['slide'] = {'manifest': 'rp.service/v1', 'service': {
        'name': 'test-slide', 'version': '1', 'kind': 'composite_driver', 'type': 'test.slide',
        'entry_point': __name__ + ':SimulatedSlide', 'operations': {
            'status': {'method': 'status', 'concurrency': 'read_only'},
            'observe_position': {'method': 'position', 'concurrency': 'read_only'},
            'move_to': {'method': 'move', 'arguments': {'target': {'type': 'number', 'required': True}}}}}}
    worker['services']['slide'] = {'component': 'slide', 'inject_signals': True}
    return base, worker


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        host, worker = documents()
        self.worker, self.host = NodeRuntime(worker), NodeRuntime(host)
        await self.worker.boot()
        await self.host.boot()
        self.slide = self.worker.instance('slide')
        self.controller = SlideController(self.host, 'worker', health_timeout_s=0.2,
                                          move_timeout_s=0.5, cancel_timeout_s=0.25)
        await self.controller.refresh()
        self.assertTrue(self.controller.ready, self.controller.fault)

    async def asyncTearDown(self):
        await self.host.shutdown()
        await self.worker.shutdown()
        self.assertFalse(MemoryTransport.links)

    async def until(self, predicate):
        async def wait():
            while not predicate():
                await asyncio.sleep(0.005)
        await asyncio.wait_for(wait(), 1)

    async def test_move_once_with_measured_feedback_and_resource_exclusion(self):
        sub = self.host.signals.subscribe('motion.position.updated', source='worker')
        self.assertTrue(self.controller.reserve(0.2))
        self.assertFalse(self.controller.reserve(0.25))
        task = asyncio.create_task(self.controller.move(0.2, asyncio.Event()))
        await self.until(lambda: self.slide.moving)
        with self.assertRaisesRegex(RuntimeError, 'busy'):
            await self.worker.invoke('slide', 'observe_position')
        feedback = (await sub.get(1))['payload']
        self.assertAlmostEqual(feedback['value'], 0.15)
        self.assertEqual((await task)['state'], 'succeeded')
        self.assertTrue(self.slide.cleaned)
        self.assertEqual(self.slide.calls, 1)
        self.assertAlmostEqual(self.controller.sample['value'], 0.2)
        sub.close()

    async def test_cancel_waits_for_worker_cleanup(self):
        self.slide.duration = 2
        cancel = asyncio.Event()
        self.assertTrue(self.controller.reserve(0.2))
        task = asyncio.create_task(self.controller.move(0.2, cancel))
        await self.until(lambda: self.slide.moving)
        cancel.set()
        result = await task
        self.assertEqual(result['state'], 'cancelled')
        self.assertTrue(result['confirmed'])
        self.assertTrue(self.slide.cleaned)
        self.assertFalse(self.worker._claims)

    async def test_lost_cancel_expires_lease_and_confirms_cleanup(self):
        self.slide.duration = 2
        self.controller.cancel_timeout = 0.5
        self.host._signal_transports[0][1].drop.add('_rp.cancel')
        cancel = asyncio.Event()
        self.assertTrue(self.controller.reserve(0.2))
        task = asyncio.create_task(self.controller.move(0.2, cancel))
        await self.until(lambda: self.slide.moving)
        cancel.set()
        self.assertEqual((await task)['state'], 'cancelled')
        self.assertTrue(self.slide.cleaned)

    async def test_lost_result_aborts_without_retry_or_false_success(self):
        self.worker._signal_transports[0][1].drop.add('_rp.result')
        self.assertTrue(self.controller.reserve(0.2))
        result = await self.controller.move(0.2, asyncio.Event())
        self.assertEqual(result['state'], 'aborted')
        self.assertFalse(result['confirmed'])
        self.assertEqual(self.slide.calls, 1)
        self.assertAlmostEqual(self.slide.value, 0.2)
        self.assertTrue(self.controller.uncertain)
        self.assertFalse(self.controller.reserve(0.1))

    async def test_disconnect_during_motion_aborts_and_expires_lease(self):
        self.slide.duration = 2
        self.assertTrue(self.controller.reserve(0.2))
        task = asyncio.create_task(self.controller.move(0.2, asyncio.Event()))
        await self.until(lambda: self.slide.moving)
        for node in (self.host, self.worker):
            node._signal_transports[0][1].drop.add('*')
        await self.controller.refresh()
        result = await task
        self.assertEqual(result['state'], 'aborted')
        self.assertFalse(result['confirmed'])
        await self.until(lambda: self.slide.cleaned)
        self.assertEqual(self.controller.diagnostic()[0], 2)

    async def test_worker_generation_change_fences_active_goal(self):
        self.slide.duration = 2
        self.assertTrue(self.controller.reserve(0.2))
        task = asyncio.create_task(self.controller.move(0.2, asyncio.Event()))
        await self.until(lambda: self.slide.moving)
        self.worker.remote.invalidate()
        await self.controller.refresh()
        self.assertEqual((await task)['state'], 'aborted')
        self.assertTrue(self.controller.uncertain)

    async def test_stale_invalid_out_of_range_and_uncalibrated_admission(self):
        for value in (float('nan'), float('inf'), -1, 1, True):
            self.assertFalse(self.controller.reserve(value))
        self.controller.last_seen = time.monotonic() - 1
        self.assertFalse(self.controller.reserve(0.2))
        self.controller.last_inventory = 0
        self.slide.calibrated = False
        await self.controller.refresh()
        self.assertFalse(self.controller.reserve(0.2))
        self.assertIn('calibration', self.controller.fault)
        records = len(self.worker.remote.records)
        await self.controller.refresh()
        self.assertEqual(len(self.worker.remote.records), records)

    async def test_cancel_before_dispatch_never_moves(self):
        cancel = asyncio.Event()
        cancel.set()
        with self.assertRaises(RemoteCancelled):
            await self.host.remote.invoke('worker', 'slide', 'move_to', {'target': 0.2},
                                          'cancel-first', cancel_event=cancel)
        self.assertEqual(self.slide.calls, 0)

    async def test_invalid_sample_is_rejected(self):
        for change in ({'value': float('nan')}, {'unit': 'mm'}, {'quality': 2}, {'valid': 1}):
            with self.assertRaises(ValueError):
                position_sample(dict(self.slide.position(), **change))

    async def test_real_slide_composite_runs_through_gateway(self):
        import json
        sys.path.insert(0, str(ROOT / 'examples/slide_nodes'))
        from slide_simulation import simulated_node, Carriage
        await self.worker.shutdown()
        doc = json.loads((ROOT / 'examples/slide_nodes/node1.json').read_text())
        _, base = documents()
        for key in ('identity', 'execution', 'signals'):
            doc[key] = base[key]
        doc['apps'], doc['runtime'] = [], []
        doc['services']['slide']['inject_signals'] = True
        Carriage.position_mm, Carriage.stalled = 0, False
        self.worker = simulated_node(doc, calibrate=True)
        await self.worker.boot()
        self.controller.epoch = None
        self.controller.last_inventory = 0
        await self.controller.refresh()
        self.assertTrue(self.controller.reserve(0.1), self.controller.fault)
        result = await self.controller.move(0.1, asyncio.Event())
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertAlmostEqual(self.controller.sample['value'], 0.1, delta=0.001)


if __name__ == '__main__':
    unittest.main()
