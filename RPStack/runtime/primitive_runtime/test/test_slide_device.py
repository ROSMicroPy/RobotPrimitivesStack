"""Device package, native-REPL worker, and two-radio integration tests."""
import asyncio
import _thread
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
FOLDER = ROOT / 'TestApps/slide_nodes'
for path in list((ROOT / 'RPStack/runtime').glob('*/src')) + list((ROOT / 'RPStack/services').glob('*/src')):
    sys.path.insert(0, str(path))
sys.path.insert(0, str(FOLDER))
from slide_simulation import simulated_node, Carriage
from rpstack.primitive_runtime import NodeHost, NodeRuntime
from rpstack.meshnet import EspNowTransport
from rpstack.meshnet import shared


class Radio:
    radios = []

    def __init__(self):
        self.queue = []
        self.enabled = False
        self.mac = bytes([len(self.radios) + 1]) * 6
        self.radios.append(self)

    def active(self, enabled):
        self.enabled = enabled

    def add_peer(self, peer):
        pass

    def send(self, peer, data, sync):
        for radio in self.radios:
            if radio is not self and radio.enabled:
                radio.queue.append((self.mac, bytes(data)))

    def irecv(self, timeout):
        return self.queue.pop(0) if self.queue else (None, None)


def transport(entity, node, **options):
    return EspNowTransport(entity, node, radio=Radio(), **options)


# Separate class state represents two independent interpreters/devices.
class DeviceA(shared.SharedEspNowTransport):
    _hub = None
    _guard = None


class DeviceB(shared.SharedEspNowTransport):
    _hub = None
    _guard = None


def document(name):
    return json.loads((FOLDER / (name + '.device.json')).read_text())


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        Radio.radios = []
        Carriage.position_mm = 0
        Carriage.stalled = False
        self.factory = patch.object(shared, 'EspNowTransport', transport)
        self.factory.start()
        self.host = None

    async def asyncTearDown(self):
        if self.host:
            await self.host.shutdown()
        self.factory.stop()
        self.assertTrue(all(not radio.enabled for radio in Radio.radios))

    async def exercise(self, separate_devices):
        provider_doc, client_doc = document('node1'), document('node2')
        if separate_devices:
            for doc, cls in ((provider_doc, 'DeviceA'), (client_doc, 'DeviceB')):
                doc['signals']['transports'][0]['entry_point'] = __name__ + ':' + cls
        provider = simulated_node(provider_doc)
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

    async def test_same_manifests_on_one_radio(self):
        await self.exercise(False)

    async def test_same_apps_across_two_radios(self):
        await self.exercise(True)

    async def test_readiness_waits_for_late_provider(self):
        provider_doc, client_doc = document('node1'), document('node2')
        provider_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceA'
        client_doc['signals']['transports'][0]['entry_point'] = __name__ + ':DeviceB'
        provider = simulated_node(provider_doc)
        client = NodeRuntime(client_doc)
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
        def prepare(path, log):
            self.prepare_threads.append(_thread.get_ident())
            doc = original_prepare(path, log)
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

    def tearDown(self):
        try:
            self.module.stop()
        finally:
            self.resources_patch.stop()
            self.load_patch.stop()
            self.radio_patch.stop()
        self.assertTrue(all(not radio.enabled for radio in Radio.radios))

    def start(self):
        return self.module.start(provider_path=str(FOLDER / 'node1.device.json'),
                                 client_path=str(FOLDER / 'node2.device.json'), verbose=False)

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

    def test_client_only_requires_no_hardware_until_demo(self):
        self.module.start('client', client_path=str(FOLDER / 'node2.device.json'))
        self.assertEqual(self.load_mock.call_count, 1)
        self.assertTrue(self.load_mock.call_args.args[0].endswith('node2.device.json'))
        self.assertEqual(Radio.radios, [])
        self.assertEqual(self.module.status()['node1'], 'remote')
        with self.assertRaises(RuntimeError):
            self.module.demo(timeout_s=.05)
        self.assertEqual(self.module.status()['state'], 'running')
        self.assertEqual(self.module.status()['demo'], 'failed')
        self.assertTrue(all(not r.enabled for r in Radio.radios))

    def test_startup_error_reaches_repl(self):
        self.load_mock.side_effect = ValueError('sensor missing')
        with self.assertRaisesRegex(ValueError, 'sensor missing'):
            self.start()
        self.assertEqual(self.module.status()['state'], 'failed')
        # stop correctly reports the existing error as well.
        with self.assertRaisesRegex(RuntimeError, 'sensor missing'):
            self.module.stop()
        self.module._session = None

    def test_preload_on_foreground_and_explicit_worker_stack(self):
        main_thread = _thread.get_ident()
        original_stack_size = _thread.stack_size()
        actual_start = _thread.start_new_thread
        seen_stack_sizes = []
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

    def test_preload_failure_does_not_start_worker(self):
        self.load_mock.side_effect = ValueError('invalid manifest')
        with patch.object(_thread, 'start_new_thread') as launch:
            with self.assertRaisesRegex(ValueError, 'invalid manifest'):
                self.start()
            launch.assert_not_called()
        self.assertTrue(self.module._session.read()['finished'])
        self.module._session = None

    def test_thread_launch_failure_restores_stack_default(self):
        previous = _thread.stack_size()
        with patch.object(_thread, 'start_new_thread', side_effect=OSError('no thread memory')):
            with self.assertRaisesRegex(OSError, 'no thread memory'):
                self.start()
        self.assertEqual(_thread.stack_size(), previous)
        self.assertEqual(self.module.status()['state'], 'failed')
        self.module._session = None

    def test_package_contains_all_imports_and_no_boot_main(self):
        installed = {}
        visited = set()
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
        for name in ('slide_nodes.py', 'slide_node1.json', 'slide_node2.json',
                     'rpstack/meshnet/shared.py', 'rpstack/linear_slide/apps.py',
                     'rpstack/primitive_runtime/node.py', 'rpstack/execution_engine/tasks.py',
                     'rpstack/distance_sensor/distance_drivers/vl53l4cd_core.py'):
            self.assertIn(name, installed)
        self.assertNotIn('main.py', installed)
