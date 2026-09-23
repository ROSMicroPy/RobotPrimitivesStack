"""Manifest-only boot and real HTTP concurrency with simulated hardware."""
import asyncio
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
for path in list((ROOT / 'RPStack/runtime').glob('*/src')) + list((ROOT / 'RPStack/services').glob('*/src')):
    sys.path.insert(0, str(path))
from rpstack.primitive_runtime.node import NodeRuntime
from rpstack.primitive_runtime.supervisor import BusyError
from rpstack.motor_control.motor_drivers.step_dir import StepDirDriver
from rpstack.execution_engine import asyncio as runtime_asyncio
from rpstack.shell.async_shell import AsyncShell


class Pin:
    def __init__(self, number):
        self.number, self.state = number, 0
    def value(self, value):
        self.state = value


class MotorDriver(StepDirDriver):
    def initialize(self, **kwargs):
        kwargs['pin_factory'] = Pin
        return super().initialize(**kwargs)


class DistanceDriver:
    async def initialize(self, **kwargs):
        self.active = True
        return True
    async def read_distance_mm(self):
        await asyncio.sleep(0.002)
        return 100
    def set_active(self, active):
        self.active = active
        return True
    def shutdown(self):
        self.active = False
        return True
    def get_status(self):
        return {'active': self.active}


class FailingDriver(DistanceDriver):
    async def initialize(self, **kwargs):
        raise RuntimeError('sensor initialization failed')


def document():
    doc = json.loads((ROOT / 'TestApps/linear_slide/manifest.json').read_text())
    for component, implementation, cls in (
        ('motor_control', 'step_dir', 'MotorDriver'),
        ('distance_sensor', 'vl53l4cd', 'DistanceDriver'),
    ):
        doc['components'][component]['service']['implementations'][implementation]['entry_point'] = __name__ + ':' + cls
    doc['apps'] = []
    doc['runtime'] = [{'id': 'http', 'entry_point': 'rpstack.micropyserver:NodeRestApi',
                       'config': {'host': '127.0.0.1', 'port': 0, 'request_timeout_s': 0.2}}]
    return doc


class NodeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.node = NodeRuntime(document(), {'i2c': lambda spec: object()})
        await self.node.boot()
        self.api = self.node._runtime_instances[0]
        self.port = self.api.server.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        await self.node.shutdown()

    async def request(self, method, path, body=None):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        data = json.dumps(body or {}).encode()
        writer.write(('{} {} HTTP/1.1\r\nHost: node\r\nContent-Length: {}\r\n\r\n'.format(method, path, len(data))).encode() + data)
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 2)
        writer.close()
        await writer.wait_closed()
        head, data = response.split(b'\r\n\r\n', 1)
        return int(head.split()[1]), json.loads(data)

    async def test_manifest_boot_registers_every_service_and_shell_ps(self):
        self.assertEqual(self.node._start_order, ['motor', 'distance', 'position', 'slide'])
        names = {r['name'] for r in self.node.tasks.snapshot()}
        self.assertTrue({'service:motor', 'service:distance', 'service:position', 'service:slide', 'runtime:http'} <= names)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            await AsyncShell(self.node).command('ps')
        self.assertIn('service:slide', output.getvalue())
        code, body = await self.request('GET', '/manifest')
        self.assertEqual(code, 200)
        self.assertEqual(body['manifest'], 'rp.node/v1')
        self.assertNotIn('resources', body)

    async def test_http_move_does_not_block_stop_or_status(self):
        code, job = await self.request('POST', '/api/services/slide/jog_steps', {'steps': 1000})
        self.assertEqual(code, 202)
        await asyncio.sleep(0.02)
        driver = self.node.instance('motor').driver
        self.assertGreater(driver.position_steps, 0)
        code, status = await self.request('GET', '/api/node/status')
        self.assertEqual((code, status['state']), (200, 'running'))
        code, conflict = await self.request('POST', '/api/services/motor/command', {'direction': True, 'amount': 1})
        self.assertEqual(code, 409)
        code, stopped = await self.request('POST', '/api/node/stop')
        self.assertEqual((code, stopped['state']), (200, 'stopped'))
        count = driver.position_steps
        await asyncio.sleep(0.03)
        self.assertEqual(driver.position_steps, count)
        self.assertFalse(driver.enabled)
        self.assertEqual(driver.step_pin.state, 0)
        code, result = await self.request('GET', job['status_url'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual((await self.request('POST', '/api/services/slide/jog_steps', {'steps': 1}))[0], 409)
        self.assertEqual((await self.request('POST', '/api/node/reset'))[0], 200)
        self.assertIsNot(self.node.instance('motor').driver, driver)
        self.assertTrue(self.node.accepting)
        self.assertEqual(driver.position_steps, count)

    async def test_event_flow_signal_and_stop_waiting_flow(self):
        flow_id = self.node.start_flow('observe_on_signal')
        await asyncio.sleep(0)
        self.node.engine.events.publish('observe', {'source': 'test'})
        result = await self.node.tasks.wait(flow_id)
        self.assertEqual(result.unit, 'm')
        flow_id = self.node.start_flow('observe_on_signal')
        await asyncio.sleep(0)
        await self.node.stop()
        self.assertEqual(self.node.tasks.describe(flow_id)['state'], 'cancelled')
        self.assertEqual(self.node.engine.events.subscribers, {})

    async def test_invalid_args_and_concurrent_connections(self):
        for args in ({'steps': 0}, {'steps': True}, {'steps': 1.2}, {'steps': 1, 'oops': True}):
            code, _ = await self.request('POST', '/api/services/slide/jog_steps', args)
            self.assertEqual(code, 422)
        results = await asyncio.gather(*(self.request('GET', '/manifest') for _ in range(4)))
        self.assertTrue(all(code == 200 and body['name'] == 'linear-slide-test' for code, body in results))

    async def test_slow_client_does_not_block_control(self):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        writer.write(b'POST /api/node/reset HTTP/1.1\r\nContent-Length: 20\r\n\r\n{')
        await writer.drain()
        code, _ = await self.request('POST', '/api/node/stop')
        self.assertEqual(code, 200)
        response = await asyncio.wait_for(reader.read(), 1)
        self.assertIn(b'400 Bad Request', response)
        writer.close()
        await writer.wait_closed()

    async def test_reset_during_motion_cancels_old_task_before_new_services(self):
        task_id = self.node.submit('slide', 'jog_steps', {'steps': 1000})
        await asyncio.sleep(0.02)
        motor = self.node.instance('motor').driver
        await self.node.reset()
        self.assertEqual(self.node.tasks.describe(task_id)['state'], 'cancelled')
        self.assertFalse(motor.enabled)
        next_job = self.node.submit('slide', 'jog_steps', {'steps': 1})
        result = await self.node.tasks.wait(next_job)
        self.assertEqual(result['steps'], 1)

    async def test_boot_failure_releases_initialized_motor(self):
        doc = document()
        doc['components']['distance_sensor']['service']['implementations']['vl53l4cd']['entry_point'] = __name__ + ':FailingDriver'
        node = NodeRuntime(doc, {'i2c': lambda spec: object()})
        with self.assertRaisesRegex(RuntimeError, 'sensor initialization failed'):
            await node.boot()
        self.assertFalse(node.instance('motor').driver.enabled)
        self.assertEqual(node.tasks.snapshot(), [])

    async def test_cancel_immediately_releases_resource_claims(self):
        task_id = self.node.submit('slide', 'jog_steps', {'steps': 1000})
        await self.node.tasks.cancel(task_id)
        self.assertEqual(self.node._claims, {})
        self.assertEqual(self.node.tasks.describe(task_id)['state'], 'cancelled')

    async def test_service_failure_stops_motion_and_health_survives_reset(self):
        async def fail():
            raise RuntimeError('polling failed')
        # Replace the resident task with a failing service task.
        old = self.node._service_tasks['distance']
        await self.node.tasks.cancel(old)
        self.node.tasks.records.pop(old)
        self.node._service_tasks['distance'] = self.node.tasks.spawn(
            'service:distance', fail, kind='service', owner='distance')
        await asyncio.sleep(0.12)
        self.assertEqual(self.node.state, 'failed')
        self.assertFalse(self.node.accepting)
        await self.node.reset()
        await asyncio.sleep(0.07)
        self.assertEqual(self.node.state, 'running')
        self.assertEqual(len([r for r in self.node.tasks.snapshot() if r['kind'] == 'service']), 4)

    async def test_repeated_resets_do_not_accumulate_resident_tasks(self):
        for _ in range(4):
            await self.node.reset()
        self.assertEqual(len([r for r in self.node.tasks.records.values() if r['kind'] == 'service']), 4)
        self.assertEqual(self.node._claims, {})

    async def test_workflow_capacity_keeps_http_stop_available(self):
        with self.assertRaisesRegex(RuntimeError, 'capacity'):
            for _ in range(100):
                self.node.start_flow('observe_on_signal')
        code, body = await self.request('POST', '/api/node/stop')
        self.assertEqual((code, body['state']), (200, 'stopped'))
        self.assertEqual(self.node.engine.events.subscribers, {})

    async def test_bad_binding_rejected_before_resource_creation(self):
        doc = document()
        doc['services']['slide']['bindings']['motor'] = 'distance'
        calls = []
        with self.assertRaises(RuntimeError):
            NodeRuntime(doc, {'i2c': lambda spec: calls.append(spec)})
        self.assertEqual(calls, [])

    async def test_shutdown_rejects_queued_reset(self):
        await self.node._control_lock.acquire()
        reset = asyncio.create_task(self.node.reset())
        shutdown = asyncio.create_task(self.node.shutdown())
        await asyncio.sleep(0)
        self.node._control_lock.release()
        with self.assertRaisesRegex(RuntimeError, 'shutting down'):
            await reset
        await shutdown
        self.assertFalse(self.node.accepting)
        self.assertEqual(self.node._started, [])

    async def test_signal_endpoint_and_execution_status(self):
        code, job = await self.request('POST', '/api/flows/start', {'name':'observe_on_signal'})
        self.assertEqual(code, 202)
        self.assertIn('run_id', job)
        code, body = await self.request('POST', '/api/signals', {'name':'observe','payload':{'ok':True}})
        self.assertEqual(code, 200)
        self.assertEqual(body['signal']['entity'], 'Robie1')
        await self.node.tasks.wait(job['task_id'])
        code, status = await self.request('GET', '/api/execution')
        self.assertEqual(code, 200)
        self.assertEqual(status['runs'][0]['state'], 'succeeded')
        for args in ({'name':'_rp.call'}, {'name':'x','routes':['missing']}, {'name':'x','ttl_ms':0}):
            self.assertEqual((await self.request('POST', '/api/signals', args))[0], 422)


if __name__ == '__main__':
    unittest.main()
