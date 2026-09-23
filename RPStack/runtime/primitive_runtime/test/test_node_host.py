"""Logical node isolation, command lifecycle, and task-only completion."""
import asyncio
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
for path in list((ROOT / 'RPStack/runtime').glob('*/src')) + list((ROOT / 'RPStack/services').glob('*/src')):
    sys.path.insert(0, str(path))
sys.path.insert(0, str(ROOT / 'TestApps/slide_nodes'))
from slide_simulation import simulated_node, Carriage
from rpstack.primitive_runtime import NodeHost, NodeRuntime, ManifestError
from rpstack.signals.inprocess import InProcessTransport


def document(name):
    return json.loads((ROOT / 'TestApps/slide_nodes' / (name + '.json')).read_text())


class HostTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        Carriage.position_mm = 0
        Carriage.stalled = False
        self.provider = simulated_node(document('node1'))
        self.client = NodeRuntime(document('node2'))
        self.host = NodeHost([self.provider, self.client])

    async def asyncTearDown(self):
        await self.host.shutdown()
        self.assertEqual(InProcessTransport._segments, {})

    async def test_move_once_and_independent_shutdown(self):
        await self.host.boot()
        app = self.client.apps['move']
        await asyncio.wait_for(self.client.wait(), 2)
        await asyncio.sleep(.08)  # health sees successful oneshot completion
        self.assertEqual(self.client.state, 'running')
        self.assertEqual([s['name'] for s in app.received], ['motion.started', 'motion.target.reached'])
        self.assertAlmostEqual(app.received[-1]['payload']['value'], .1)
        self.assertTrue(all(s['target'] == 'node2' and s['correlation'] == app.correlation for s in app.received))
        self.assertIsNot(self.provider.tasks, self.client.tasks)
        self.assertEqual(list(self.client.registry.definitions()), [])
        await self.client.shutdown()
        self.assertEqual(self.provider.state, 'running')
        self.assertTrue(self.provider.accepting)

    async def test_stalled_slide_reports_error_and_releases_claims(self):
        Carriage.stalled = True
        await self.host.boot()
        with self.assertRaisesRegex(RuntimeError, 'No position change'):
            await asyncio.wait_for(self.client.wait(), 2)
        self.assertEqual(self.client.apps['move'].received[-1]['name'], 'motion.target.failed')
        self.assertEqual(self.provider._claims, {})
        self.assertFalse(self.provider.instance('motor').driver.enabled)

    async def test_unknown_target_times_out(self):
        doc = document('node2')
        doc['apps'][0]['config'].update(target_node='missing', timeout_s=.03)
        self.client = NodeRuntime(doc)
        self.host = NodeHost([self.provider, self.client])
        await self.host.boot()
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(self.client.wait(), 1)
        self.assertEqual(Carriage.position_mm, 0)

    async def test_duplicate_identity_rejected(self):
        with self.assertRaisesRegex(ManifestError, 'unique'):
            NodeHost([self.client, NodeRuntime(document('node2'))])

    async def test_host_run_closes_task_only_nodes(self):
        doc = document('node2')
        doc['apps'][0]['entry_point'] = __name__ + ':CompleteApp'
        doc['apps'][0]['config'] = {}
        node = NodeRuntime(doc)
        self.host = NodeHost([node])
        await asyncio.wait_for(self.host.run(), 1)
        self.assertTrue(node._closed.is_set())
        self.assertEqual(node.tasks.snapshot(), [])

    async def test_host_rolls_back_partial_boot(self):
        doc = document('node2')
        doc['apps'][0]['entry_point'] = __name__ + ':FailStartApp'
        doc['apps'][0]['config'] = {}
        self.host = NodeHost([self.provider, NodeRuntime(doc)])
        with self.assertRaisesRegex(RuntimeError, 'start failed'):
            await self.host.boot()
        self.assertFalse(self.provider.accepting)
        self.assertEqual(self.provider.tasks.snapshot(), [])

    async def test_resident_app_exit_still_fails_health(self):
        doc = document('node2')
        doc['apps'][0].update(entry_point=__name__ + ':CompleteApp', mode='resident', config={})
        node = NodeRuntime(doc)
        self.host = NodeHost([node])
        await self.host.boot()
        await asyncio.sleep(.1)
        self.assertEqual(node.state, 'failed')

    async def test_failed_client_does_not_stop_provider(self):
        doc = document('node2')
        doc['apps'][0]['config'].update(target_node='missing', timeout_s=.02)
        self.client = NodeRuntime(doc)
        self.host = NodeHost([self.provider, self.client])
        running = asyncio.create_task(self.host.run())
        try:
            await asyncio.sleep(.12)
            self.assertTrue(self.client._closed.is_set())
            self.assertTrue(self.provider.accepting)
            self.assertIn(('SlideDemo', 'node2'), self.host.failures)
            self.assertFalse(running.done())
        finally:
            await self.host.shutdown()
            await asyncio.wait_for(running, 1)

    async def test_busy_command_is_rejected_and_targeting_is_respected(self):
        # Use a passive client so this test controls command admission.
        doc = document('node2')
        doc['apps'] = []
        self.client = NodeRuntime(doc)
        self.host = NodeHost([self.provider, self.client])
        await self.host.boot()
        replies = self.client.signals.subscribe('*', source='node1')
        self.client.publish_signal('slide.move', {'position_mm': 100},
                                   target='other', correlation='ignored')
        await asyncio.sleep(.02)
        self.assertEqual(Carriage.position_mm, 0)
        self.client.publish_signal('slide.move', {'position_mm': 100},
                                   target='node1', correlation='first')
        self.client.publish_signal('slide.move', {'position_mm': 200},
                                   target='node1', correlation='second')
        received = [await replies.get(1) for _ in range(3)]
        first = [s['name'] for s in received if s['correlation'] == 'first']
        second = [s for s in received if s['correlation'] == 'second']
        self.assertEqual(first, ['motion.started', 'motion.target.reached'])
        self.assertEqual(second[0]['name'], 'motion.target.failed')
        self.assertIn('busy', second[0]['payload']['error'])
        self.assertEqual(Carriage.position_mm, 100)
        replies.close()

    async def test_transport_isolation_and_bounded_delivery(self):
        a = InProcessTransport('a', '1')
        b = InProcessTransport('a', '2', capacity=1)
        c = InProcessTransport('b', '2')
        try:
            for port in (a, b, c):
                await port.start()
            await a.send(b'first')
            await a.send(b'second')
            self.assertEqual(await b.recv(), b'first')
            self.assertEqual(b.dropped, 1)
            self.assertEqual(c.items, [])
        finally:
            for port in (a, b, c):
                await port.stop()


class CompleteApp:
    def __init__(self, node):
        pass
    async def start(self):
        pass
    async def run(self):
        return 42
    async def stop(self):
        pass


class FailStartApp(CompleteApp):
    async def start(self):
        raise RuntimeError('start failed')
