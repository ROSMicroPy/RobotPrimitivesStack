"""Device package, native-REPL worker, and two-radio integration tests."""
import asyncio
import _thread
import importlib.util
import json
from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
FOLDER = ROOT / 'examples/slide_nodes'
sys.path.insert(0, str(FOLDER))
from slide_simulation import simulated_node, Carriage
from rpstack.node_runtime import NodeHost, NodeRuntime
from rpstack.espnow import EspNowTransport
from rpstack.espnow import shared


class Radio:
    radios = []

    # Register a simulated radio with a unique address and empty receive queue.
    def __init__(self):
        self.queue = []
        self.enabled = False
        self.mac = bytes([len(self.radios) + 1]) * 6
        self.radios.append(self)

    # Record whether this simulated radio participates in delivery.
    def active(self, enabled):
        self.enabled = enabled

    # Accept peer registration without restricting the simulated broadcast network.
    def add_peer(self, peer):
        pass

    # Copy a frame to every other enabled simulated radio.
    def send(self, peer, data, sync):
        for radio in self.radios:
            if radio is not self and radio.enabled:
                radio.queue.append((self.mac, bytes(data)))

    # Return the next queued radio frame or the nonblocking empty result.
    def irecv(self, timeout):
        return self.queue.pop(0) if self.queue else (None, None)


# Create the real framing transport around a simulated radio.
def transport(entity, node, **options):
    return EspNowTransport(entity, node, radio=Radio(), **options)


# Separate class state represents two independent interpreters/devices.
class DeviceA(shared.SharedEspNowTransport):
    _hub = None
    _guard = None


class DeviceB(shared.SharedEspNowTransport):
    _hub = None
    _guard = None


# Replace device Wi-Fi/listener settings while preserving catalog, HTTP, and application logic.
def host_runtime(doc):
    # Exercise real catalog/HTTP/apps; replace only device network setup.
    doc['runtime'] = [r for r in doc.get('runtime', []) if r['id'] != 'wifi']
    for r in doc['runtime']:
        if r['id'] == 'http':
            r['config'] = {'host': '127.0.0.1', 'port': 0}
    return doc


# Load a device deployment and adapt its runtime settings for host integration tests.
def document(name):
    return host_runtime(json.loads((FOLDER / (name + '.device.json')).read_text()))


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    # Reset simulated hardware and patch shared transport creation before each device scenario.
    async def asyncSetUp(self):
        Radio.radios = []
        Carriage.position_mm = 0
        Carriage.stalled = False
        self.factory = patch.object(shared, 'EspNowTransport', transport)
        self.factory.start()
        self.host = None

    # Shut down the host, remove the transport patch, and verify all radios are disabled.
    async def asyncTearDown(self):
        if self.host:
            await self.host.shutdown()
        self.factory.stop()
        self.assertTrue(all(not radio.enabled for radio in Radio.radios))

    # Run a slide command across one shared radio or two separate radios and verify independent
    # cleanup.
    async def exercise(self, separate_devices):
        provider_doc, client_doc = document('node1'), document('node2')
        if separate_devices:
            for doc, cls in ((provider_doc, 'DeviceA'), (client_doc, 'DeviceB')):
                doc['signals']['transports'][0]['entry_point'] = __name__ + ':' + cls
        provider = simulated_node(provider_doc, calibrate=True)
        client = NodeRuntime(client_doc)
        self.host = NodeHost([provider, client])
        await self.host.boot()
        await asyncio.wait_for(client.wait(), 3)
        self.assertEqual(len(Radio.radios), 2 if separate_devices else 1)
        self.assertEqual([s['name'] for s in client.apps['move'].received],
                         ['motion.started', 'motion.target.reached'])
        self.assertEqual(Carriage.position_mm, 100)
        await client.shutdown()
        self.assertTrue(provider.accepting)
        self.assertTrue(Radio.radios[0].enabled)
        self.assertEqual(sum(r.enabled for r in Radio.radios), 1)

    # Verify logical provider/client nodes share one physical radio successfully.
    async def test_same_manifests_on_one_radio(self):
        await self.exercise(False)

    # Verify unchanged applications communicate across separate simulated devices.
    async def test_same_apps_across_two_radios(self):
        await self.exercise(True)

    # Calibrate remotely before sending a move and verify the provider's calibration state.
    async def test_remote_explicit_calibration_then_move(self):
        provider_doc, client_doc = document('node1'), document('node2')
        provider_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceA'
        client_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceB'
        client_doc['apps'][0]['config'].update(command='calibrate', steps=200)
        provider = simulated_node(provider_doc)
        client = NodeRuntime(client_doc)
        self.host = NodeHost([provider, client])
        await self.host.boot()
        await asyncio.wait_for(client.wait(), 3)
        self.assertEqual(client.apps['move'].received[-1]['name'], 'slide.calibrated')
        self.assertEqual(provider.calibration_status()['slide']['state'], 'calibrated')
        self.assertEqual(provider.instance('slide').steps_per_mm, 1)
        await client.shutdown()
        move_doc = document('node2')
        move_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceB'
        move = NodeRuntime(move_doc)
        self.host._booted.append(move)
        await move.boot()
        await asyncio.wait_for(move.wait(), 3)
        self.assertEqual(Carriage.position_mm, 100)

    # Verify remote observation returns position without calibration or motor movement.
    async def test_remote_position_without_calibration_or_motion(self):
        provider_doc, client_doc = document('node1'), document('node2')
        provider_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceA'
        client_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceB'
        client_doc['apps'][0]['config'].update(command='observe')
        provider = simulated_node(provider_doc)
        client = NodeRuntime(client_doc)
        self.host = NodeHost([provider, client])
        await self.host.boot()
        await asyncio.wait_for(client.wait(), 3)
        replies = client.apps['move'].received
        self.assertEqual([reply['name'] for reply in replies], ['slide.position'])
        self.assertEqual(replies[0]['payload']['value'], 0)
        self.assertEqual(Carriage.position_mm, 0)
        self.assertIsNone(provider.instance('slide').steps_per_mm)

    # Check remote range updates are stationary and constrain later movement targets.
    async def test_remote_range_update_without_motion(self):
        provider_doc, client_doc = document('node1'), document('node2')
        provider_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceA'
        client_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceB'
        client_doc['apps'][0]['config'].update(command='set_range', min_mm=40, max_mm=250)
        provider = simulated_node(provider_doc)
        client = NodeRuntime(client_doc)
        self.host = NodeHost([provider, client])
        await self.host.boot()
        await asyncio.wait_for(client.wait(), 3)
        self.assertEqual([r['name'] for r in client.apps['move'].received], ['slide.range.updated'])
        self.assertEqual(provider.instance('slide').get_range(), {'min_mm': 40, 'max_mm': 250})
        self.assertEqual(Carriage.position_mm, 0)
        with self.assertRaisesRegex(RuntimeError, 'below the configured minimum'):
            await provider.invoke('slide', 'move_to', {'target': .03})

    # Verify radio discovery reaches the gateway and is exposed through its HTTP catalog
    # endpoint.
    async def test_gateway_catalog_across_two_devices_and_http(self):
        provider_doc, gateway_doc = document('node1'), document('client_host')
        provider_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceA'
        gateway_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceB'
        for doc in (provider_doc, gateway_doc):
            next(r for r in doc['runtime'] if r['id'] == 'catalog')['config'] = {'interval_ms': 100, 'ttl_ms': 1000}
        provider = simulated_node(provider_doc)
        gateway = NodeRuntime(gateway_doc)
        self.host = NodeHost([provider, gateway])
        await self.host.boot()
        # Wait until both devices' catalogs contain both nodes.
        async def discovered():
            while any(n.runtime_instances['catalog'].snapshot()['count'] < 2 for n in (provider, gateway)):
                await asyncio.sleep(.02)
        await asyncio.wait_for(discovered(), 3)
        server = gateway.runtime_instances['http'].server.server
        port = server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection('127.0.0.1', port)
        writer.write(b'GET /api/robot HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(), 3)
        writer.close()
        await writer.wait_closed()
        self.assertIn(b'200 OK', raw)
        payload = json.loads(raw.split(b'\r\n\r\n', 1)[1])
        self.assertEqual({n['node_id'] for n in payload['nodes']}, {'node1', 'node2-host'})
        self.assertIn('motion.position_actuator', json.dumps(payload))
        self.assertNotIn('WIFI_PASSWORD', json.dumps(payload))
        self.assertEqual(Carriage.position_mm, 0)

    # Ensure client readiness probes tolerate delayed provider initialization before sending
    # motion.
    async def test_readiness_waits_for_late_provider(self):
        provider_doc, client_doc = document('node1'), document('node2')
        provider_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceA'
        client_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceB'
        provider = simulated_node(provider_doc, calibrate=True)
        client = NodeRuntime(client_doc)
        # Delay sensor readiness and assert the carriage remains stationary during startup.
        async def delayed_sensor_init(driver, **kwargs):
            await asyncio.sleep(.35)
            self.assertEqual(Carriage.position_mm, 0)
            return True
        self.host = NodeHost([client, provider])
        with patch('slide_simulation.DistanceDriver.initialize', delayed_sensor_init):
            await self.host.boot()
        await asyncio.wait_for(client.wait(), 3)
        self.assertEqual(Carriage.position_mm, 100)
        self.assertTrue(client.apps['move'].command_sent)

    # Reject incompatible shared-radio peers without disabling the existing radio.
    async def test_duplicate_identity_and_mismatched_channel_rejected(self):
        a = shared.SharedEspNowTransport('robot', 'node1')
        duplicate = shared.SharedEspNowTransport('robot', 'node1')
        mismatch = shared.SharedEspNowTransport('robot', 'node2', channel=11)
        await a.start()
        try:
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                await duplicate.start()
            with self.assertRaisesRegex(ValueError, 'channel'):
                await mismatch.start()
            self.assertTrue(Radio.radios[0].enabled)
        finally:
            await a.stop()


class ReplTests(unittest.TestCase):
    # Load the device REPL helper and patch hardware/document preparation for host execution.
    def setUp(self):
        Radio.radios = []
        Carriage.position_mm = 0
        Carriage.stalled = False
        spec = importlib.util.spec_from_file_location('slide_nodes_device', FOLDER / 'device.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.radio_patch = patch.object(shared, 'EspNowTransport', transport)
        self.radio_patch.start()
        self.prepare_threads = []
        original_prepare = self.module._prepare_document
        # Record preload thread identity and substitute simulated hardware into provider
        # documents.
        def prepare(path, log):
            self.prepare_threads.append(_thread.get_ident())
            doc = host_runtime(original_prepare(path, log))
            if doc['identity']['node'] == 'node1':
                for component, implementation, cls in (
                    ('motor_control', 'step_dir', 'MotorDriver'),
                    ('distance_sensor', 'vl53l4cd', 'DistanceDriver'),
                ):
                    doc['components'][component]['service']['implementations'][implementation]['entry_point'] = 'slide_simulation:' + cls
            return doc
        self.load_patch = patch.object(self.module, '_prepare_document', side_effect=prepare)
        self.load_mock = self.load_patch.start()
        self.resources_patch = patch.object(NodeRuntime, '_create_resources',
            lambda node: node.resources.update({'carriage_bus': object()}))
        self.resources_patch.start()

    # Stop the device session, restore patches, and verify radio cleanup.
    def tearDown(self):
        try:
            self.module.stop()
        finally:
            self.resources_patch.stop()
            self.load_patch.stop()
            self.radio_patch.stop()
        self.assertTrue(all(not radio.enabled for radio in Radio.radios))

    # Start the local provider/client session and explicitly calibrate it for motion tests.
    def start(self):
        self.module.start(provider_path=str(FOLDER / 'node1.device.json'),
                          client_path=str(FOLDER / 'node2.device.json'), verbose=False)
        self.module.calibrate()
        return self.module.status()

    # Verify the native prompt can change travel bounds without moving hardware.
    def test_native_prompt_set_range(self):
        self.module.start(provider_path=str(FOLDER / 'node1.device.json'),
                          client_path=str(FOLDER / 'node2.device.json'), verbose=False)
        self.assertEqual(self.module.set_range(30, 300), {'min_mm': 30, 'max_mm': 300})
        self.assertEqual(Carriage.position_mm, 0)

    # Check native position observation neither moves nor calibrates the slide.
    def test_native_prompt_position_is_stationary(self):
        self.module.start(provider_path=str(FOLDER / 'node1.device.json'),
                          client_path=str(FOLDER / 'node2.device.json'), verbose=False)
        self.assertEqual(self.module.position()['value'], 0)
        self.assertEqual(Carriage.position_mm, 0)
        self.assertFalse(self.module.status()['slide']['calibrated'])

    # Exercise start, repeated moves, duplicate-start rejection, stop, and restart from the
    # prompt.
    def test_native_prompt_start_repeated_demo_stop_restart(self):
        self.assertEqual(self.start()['state'], 'running')
        with self.assertRaisesRegex(RuntimeError, 'already started'):
            self.start()
        self.assertAlmostEqual(self.module.demo()['value'], .1)
        self.assertAlmostEqual(self.module.demo(120)['value'], .12)
        self.assertEqual(self.module.status()['node1'], 'running')
        self.assertEqual(self.module.stop()['state'], 'stopped')
        self.assertEqual(self.start()['state'], 'running')
        self.assertAlmostEqual(self.module.demo(80)['value'], .08)

    # Ensure a remote-client timeout leaves its gateway and shared radio running.
    def test_client_gateway_stays_alive_between_commands(self):
        self.module.start('client', client_path=str(FOLDER / 'node2.device.json'),
                          gateway_path=str(FOLDER / 'client_host.device.json'))
        self.assertEqual(self.load_mock.call_count, 2)
        self.assertEqual(len(Radio.radios), 1)
        self.assertEqual(self.module.status()['node1'], 'remote')
        self.assertTrue(self.module.status()['gateway_url'].startswith('http://'))
        with self.assertRaises(RuntimeError):
            self.module.demo(timeout_s=.05)
        self.assertEqual(self.module.status()['state'], 'running')
        self.assertEqual(self.module.status()['demo'], 'failed')
        self.assertTrue(Radio.radios[0].enabled)

    # Verify startup failures remain visible through prompt calls and session status.
    def test_startup_error_reaches_repl(self):
        self.load_mock.side_effect = ValueError('sensor missing')
        with self.assertRaisesRegex(ValueError, 'sensor missing'):
            self.start()
        self.assertEqual(self.module.status()['state'], 'failed')
        # stop correctly reports the existing error as well.
        with self.assertRaisesRegex(RuntimeError, 'sensor missing'):
            self.module.stop()
        self.module._session = None

    # Check foreground preloading, worker stack sizing/restoration, and reuse across commands.
    def test_preload_on_foreground_and_explicit_worker_stack(self):
        main_thread = _thread.get_ident()
        original_stack_size = _thread.stack_size()
        actual_start = _thread.start_new_thread
        seen_stack_sizes = []
        # Record the configured stack size while preserving the host thread-launch behavior.
        def launch(function, args):
            # Python stack_size() resets its default on some host builds when
            # queried; restore it before dispatching the worker.
            size = _thread.stack_size()
            _thread.stack_size(size)
            seen_stack_sizes.append(size)
            return actual_start(function, args)
        with patch.object(_thread, 'start_new_thread', side_effect=launch):
            self.start()
        self.assertEqual(self.prepare_threads, [main_thread, main_thread])
        self.assertEqual(seen_stack_sizes[0], 65536)
        self.assertEqual(len(seen_stack_sizes), 3)  # runtime plus two calibration workers
        self.assertEqual(_thread.stack_size(), original_stack_size)
        self.module.demo(100)
        self.module.demo(120)
        self.assertEqual(self.load_mock.call_count, 2)  # no worker filesystem reads

    # Ensure invalid preloaded documents prevent thread creation and finish the failed session.
    def test_preload_failure_does_not_start_worker(self):
        self.load_mock.side_effect = ValueError('invalid manifest')
        with patch.object(_thread, 'start_new_thread') as launch:
            with self.assertRaisesRegex(ValueError, 'invalid manifest'):
                self.start()
            launch.assert_not_called()
        self.assertTrue(self.module._session.read()['finished'])
        self.module._session = None

    # Verify thread-launch failure restores stack configuration and marks the session failed.
    def test_thread_launch_failure_restores_stack_default(self):
        previous = _thread.stack_size()
        with patch.object(_thread, 'start_new_thread', side_effect=OSError('no thread memory')):
            with self.assertRaisesRegex(OSError, 'no thread memory'):
                self.start()
        self.assertEqual(_thread.stack_size(), previous)
        self.assertEqual(self.module.status()['state'], 'failed')
        self.module._session = None

    # Audit package dependencies for required runtime assets without installing a boot main
    # script.
    def test_package_contains_all_imports_and_no_boot_main(self):
        installed = {}
        visited = set()
        # Walk local package dependencies once and record every destination/source mapping.
        def visit(path):
            path = path.resolve()
            if path in visited:
                return
            visited.add(path)
            package = json.loads(path.read_text())
            for destination, source in package['urls']:
                source = path.parent / source
                self.assertTrue(source.exists(), str(source))
                installed[destination] = source
            for dependency, version in package.get('deps', []):
                self.assertFalse(dependency.startswith('github:'))
                visit(path.parent / dependency)
        visit(FOLDER / 'package.json')
        for name in ('slide_nodes.py', 'slide_node1.json', 'slide_node2.json', 'slide_client_host.json',
                     'rpstack/apps/robot_gateway/__init__.py', 'rpstack/catalog/__init__.py',
                     'rpstack/micropyserver/rest.py', 'rpstack/env/envstore.py',
                     'rpstack/espnow/shared.py', 'rpstack/apps/slide_commands/apps.py',
                     'rpstack/node_runtime/node.py', 'rpstack/execution_engine/tasks.py',
                     'rpstack/distance_sensor/distance_drivers/vl53l4cd_core.py'):
            self.assertIn(name, installed)
        self.assertNotIn('main.py', installed)
