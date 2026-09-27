import asyncio
import copy
import json
from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest

ROOT = Path(__file__).resolve().parents[4]
from rpstack.catalog import Catalog, CATALOG_SIGNAL
from rpstack.node_runtime.node import NodeRuntime
from rpstack.node_runtime.manifest import ManifestError
from rpstack.support import now_ms



# Build a minimal catalog node, optionally adding HTTP and gateway application dependencies.
def document(name='one', gateway=False):
    doc = {'manifest': 'rp.node/v1', 'name': name, 'identity': {'entity': 'robot', 'node': name},
           'components': {}, 'services': {}, 'runtime': [{'id': 'catalog', 'entry_point': 'rpstack.catalog:Catalog'}]}
    if gateway:
        doc['runtime'].insert(0, {'id': 'http', 'entry_point': 'rpstack.micropyserver:NodeRestApi',
                                 'config': {'host': '127.0.0.1', 'port': 0}})
        doc['apps'] = [{'id': 'gateway', 'entry_point': 'rpstack.apps.robot_gateway:GatewayApp',
                        'requires': ['http', 'catalog']}]
    return doc


# Wrap each catalog profile fragment in a valid signal envelope.
def signals(catalog):
    return [catalog.node.signals.publish(CATALOG_SIGNAL, chunk) for chunk in catalog.frames()]


class CatalogTests(unittest.TestCase):
    # Prepare two independent catalog nodes for discovery ingestion tests.
    def setUp(self):
        self.a = Catalog(NodeRuntime(document('one')))
        self.b = Catalog(NodeRuntime(document('two')))

    # Verify reordered and duplicate fragments still assemble exactly one remote profile.
    def test_fragmented_profile_out_of_order_and_duplicate(self):
        frames = signals(self.a)
        for frame in reversed(frames):
            self.b.ingest(frame)
            self.b.ingest(frame)
        snapshot = self.b.snapshot()
        self.assertEqual({n['node_id'] for n in snapshot['nodes']}, {'one', 'two'})
        self.assertFalse(self.b.pending)

    # Check stale nodes expire and a new boot can replace their profile.
    def test_expiry_and_reboot_replacement(self):
        for frame in signals(self.a): self.b.ingest(frame)
        self.b.nodes['one']['seen'] = now_ms() - self.b.ttl_ms
        self.assertEqual(self.b.snapshot()['count'], 1)
        self.a.node.signals.boot = 'newboot'
        self.a.node.document['name'] = 'replacement'
        for frame in signals(self.a): self.b.ingest(frame)
        self.assertEqual(self.b.nodes['one']['profile']['name'], 'replacement')

    # Ensure delayed announcements from a retired boot cannot overwrite newer identity state.
    def test_old_boot_cannot_replace_a_new_boot(self):
        for frame in signals(self.a): self.b.ingest(frame)
        delayed = signals(self.a)
        self.a.node.signals.boot = 'newboot'
        self.a.node.document['name'] = 'replacement'
        for frame in signals(self.a): self.b.ingest(frame)
        for frame in delayed: self.b.ingest(frame)
        self.assertEqual(self.b.nodes['one']['boot'], 'newboot')

    # Reject foreign-entity traffic and malformed fragment metadata without retaining partial
    # state.
    def test_foreign_identity_and_malformed_chunks(self):
        frames = signals(self.a)
        bad = copy.deepcopy(frames[0]); bad['entity'] = 'other'; self.b.ingest(bad)
        bad = copy.deepcopy(frames[0]); bad['payload']['count'] = 100000; self.b.ingest(bad)
        self.assertEqual(self.b.snapshot()['count'], 1)
        self.assertEqual(self.b.stats['invalid'], 1)
        self.assertFalse(self.b.pending)

    # Verify node capacity and expiration of incomplete profile assemblies.
    def test_capacity_and_partial_profile_timeout(self):
        self.b.max_nodes = 1
        for frame in signals(self.a): self.b.ingest(frame)
        self.assertEqual(self.b.snapshot()['count'], 1)
        self.b.ingest(signals(self.a)[0])
        self.b.pending['one']['seen'] -= self.b.ttl_ms
        self.b.snapshot()
        self.assertFalse(self.b.pending)

    # Ensure public profiles omit private deployment data and message history stays bounded.
    def test_projection_hides_config_and_messages_are_bounded(self):
        self.a.node.document['secret'] = 'password'
        self.assertNotIn('password', json.dumps(self.a.profile()))
        for i in range(100):
            self.b.ingest({'entity': 'robot', 'source': 'one', 'name': 'event', 'payload': i})
        self.assertEqual(len(self.b.messages), 32)

    # Reject a gateway whose required runtime dependency is undeclared.
    def test_app_dependency_validation(self):
        doc = document(gateway=True)
        doc['apps'][0]['requires'] = ['missing']
        with self.assertRaises(ManifestError): NodeRuntime(doc)


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    # Verify discovery announcements wait while command replies occupy the transport queue.
    async def test_catalog_yields_to_pending_command_traffic(self):
        node = NodeRuntime(document())
        node.signals.add_transport('mesh', object())
        node.signals.routes = ['mesh']
        port = node.signals.ports['mesh']
        port['queue'].append(b'command-reply')
        catalog = Catalog(node)
        await catalog.start()
        task = asyncio.create_task(catalog.run())
        try:
            await asyncio.sleep(.025)
            self.assertEqual(node.signals.stats['published'], 0)
            self.assertEqual(port['queue'], [b'command-reply'])
            port['queue'].clear()
            await asyncio.sleep(.025)
            self.assertEqual(node.signals.stats['published'], 1)
            self.assertEqual(len(port['queue']), 1)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await catalog.stop()

    # Exercise gateway routes on the node's shared HTTP server across stop/reset and shutdown.
    async def test_shared_http_and_cleanup(self):
        node = NodeRuntime(document(gateway=True))
        await node.boot()
        server = node.runtime_instances['http'].server
        port = server.server.sockets[0].getsockname()[1]
        # Fetch and decode one JSON response from the local integration-test server.
        async def get(path):
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
            writer.write(('GET '+path+' HTTP/1.1\r\nHost: localhost\r\n\r\n').encode())
            await writer.drain()
            data = await reader.read()
            writer.close(); await writer.wait_closed()
            return json.loads(data.split(b'\r\n\r\n', 1)[1])
        try:
            robot, manifest, status = await asyncio.gather(get('/api/robot'), get('/manifest'), get('/api/robot/status'))
            self.assertEqual(robot['count'], 1)
            self.assertEqual(manifest['apps'][0]['id'], 'gateway')
            self.assertEqual(status['node_id'], 'one')
            self.assertIs(node.apps['gateway'].server, server)
            await node.stop()
            self.assertEqual((await get('/api/robot/status'))['state'], 'stopped')
            await node.reset()
            self.assertEqual((await get('/api/robot/status'))['state'], 'running')
        finally:
            await node.shutdown()
        self.assertFalse(any(path == '/api/robot' for _, path, _ in server.routes))
        self.assertFalse(node.signals.subscribers)

    # Verify two gateways independently discover the same robot through paired transports.
    async def test_two_gateways_observe_same_robot_over_signal_transport(self):
        class Transport:
            # Prepare an asynchronous mailbox for the paired test link.
            def __init__(self): self.queue = asyncio.Queue()
            # Acknowledge startup for the in-memory test transport.
            async def start(self): pass
            # Acknowledge shutdown; this queue-only test transport owns no external resources.
            async def stop(self): pass
            # Place outgoing bytes directly into the peer's mailbox.
            async def send(self, data): await self.peer.queue.put(data)
            # Await the next message placed in this transport's mailbox.
            async def recv(self): return await self.queue.get()
        nodes = [NodeRuntime(document(name, gateway=True)) for name in ('one', 'two')]
        ports = [Transport(), Transport()]
        ports[0].peer, ports[1].peer = ports[1], ports[0]
        for node, port in zip(nodes, ports):
            node.signals.add_transport('mesh', port)
            node.signals.routes = ['local', 'mesh']
            node._signal_transports.append(('mesh', port))
        try:
            for node in nodes: await node.boot()
            # Yield until both catalogs have learned both node profiles.
            async def discovered():
                while any(node.runtime_instances['catalog'].snapshot()['count'] != 2 for node in nodes):
                    await asyncio.sleep(.02)
            await asyncio.wait_for(discovered(), 3)
            for node in nodes:
                self.assertEqual({n['node_id'] for n in node.apps['gateway'].catalog.snapshot()['nodes']}, {'one', 'two'})
        finally:
            for node in nodes: await node.shutdown()


if __name__ == '__main__': unittest.main()
