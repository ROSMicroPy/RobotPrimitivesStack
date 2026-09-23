import asyncio
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'TestApps/robie1'))
from simulation import MemoryTransport
from rpstack.primitive_runtime.node import NodeRuntime
from rpstack.signals import encode


class DistributedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.nodes = {}
        for name in ('arm', 'base', 'controller'):
            doc = json.loads((ROOT / 'TestApps/robie1' / (name + '.json')).read_text())
            doc['execution']['lease_ms'] = 150
            for flow in doc.get('flows', {}).values():
                flow['autostart'] = False
            node = NodeRuntime(doc)
            self.nodes[name] = node
            await node.boot()
        self.controller = self.nodes['controller']
        self.arm = self.nodes['arm']

    async def asyncTearDown(self):
        for node in reversed(list(self.nodes.values())):
            await node.shutdown()
        self.assertFalse(MemoryTransport.links)
        for node in self.nodes.values():
            self.assertFalse(node.tasks.snapshot())

    async def until(self, predicate, timeout=1):
        async def poll():
            while not predicate():
                await asyncio.sleep(0.005)
        await asyncio.wait_for(poll(), timeout)

    def motion_flow(self, duration=0.03):
        return {'start': 'move', 'nodes': {'move': {'node':'arm', 'service':'joint',
            'operation':'move', 'arguments': {'position':0.5, 'duration_s':duration}, 'timeout_s':2}}}

    async def test_manifest_robot_workflow_and_observed_state(self):
        task = self.controller.start_flow('reach')
        result = await asyncio.wait_for(self.controller.tasks.wait(task), 1)
        self.assertEqual(result, {'position':0.25})
        self.assertEqual(self.arm.instance('joint').calls, 1)
        self.assertEqual(self.nodes['base'].instance('joint').calls, 1)
        await self.until(lambda: any(r['state']=='succeeded' for r in self.arm.remote.states.values()))
        names = {r['name'] for r in self.controller.tasks.snapshot()}
        self.assertTrue({'signals:mesh:rx','signals:mesh:tx','signals:ros:rx','signals:ros:tx','execution:remote'} <= names)

    async def test_bridge_allows_mesh_worker_to_call_ros_worker(self):
        result = await asyncio.wait_for(self.arm.remote.invoke('base','joint','move',{'position':4},'arm-run'), 1)
        self.assertEqual(result, {'position':4})
        self.assertEqual(self.nodes['base'].instance('joint').calls, 1)

    async def test_duplicate_logical_request_does_not_repeat_action(self):
        task = self.controller.engine.start('move', self.motion_flow())
        await self.controller.tasks.wait(task)
        key, record = next(iter(self.arm.remote.records.items()))
        self.controller.signals.publish('_rp.call', {'service':'joint','operation':'move',
            'arguments':{'position':99},'lease_ms':150,'epoch':self.arm.remote.epoch},
            target='arm', correlation=key[2])
        await asyncio.sleep(0.06)
        self.assertEqual(self.arm.instance('joint').calls, 1)
        self.assertEqual(self.arm.instance('joint').position, 0.5)

    async def test_coordinator_stop_cancels_remote_motion(self):
        task = self.controller.engine.start('move', self.motion_flow(10))
        joint = self.arm.instance('joint')
        await self.until(lambda: joint.moving)
        await self.controller.stop()
        await self.until(lambda: joint.cancelled)
        self.assertEqual(self.controller.tasks.describe(task)['state'], 'cancelled')
        self.assertFalse(joint.moving)

    async def test_lost_cancel_and_renewals_expire_receiver_lease(self):
        task = self.controller.engine.start('move', self.motion_flow(10))
        joint = self.arm.instance('joint')
        await self.until(lambda: joint.moving)
        for _, transport in self.controller._signal_transports:
            transport.drop.update(('_rp.cancel','_rp.renew'))
        await self.controller.stop()
        await self.until(lambda: joint.cancelled, timeout=0.6)
        self.assertFalse(joint.moving)

    async def test_renewals_keep_a_long_action_alive(self):
        task = self.controller.engine.start('move', self.motion_flow(0.4))
        self.assertEqual(await asyncio.wait_for(self.controller.tasks.wait(task), 1), {'position':0.5})
        self.assertFalse(self.arm.instance('joint').cancelled)

    async def test_reset_rejects_delayed_call_from_old_generation(self):
        epoch = self.arm.remote.epoch
        await self.arm.reset()
        self.controller.signals.publish('_rp.call', {'service':'joint','operation':'move',
            'arguments':{'position':99},'lease_ms':150,'epoch':epoch}, target='arm', correlation='stale-run')
        await asyncio.sleep(0.05)
        self.assertEqual(self.arm.instance('joint').calls, 0)
        task = self.controller.engine.start('move', self.motion_flow())
        await self.controller.tasks.wait(task)
        self.assertEqual(self.arm.instance('joint').calls, 1)

    async def test_cancel_before_call_leaves_tombstone(self):
        self.controller.signals.publish('_rp.cancel', target='arm', correlation='reordered')
        await asyncio.sleep(0.025)
        self.controller.signals.publish('_rp.call', {'service':'joint','operation':'move',
            'arguments':{'position':99},'lease_ms':150,'epoch':self.arm.remote.epoch}, target='arm', correlation='reordered')
        await asyncio.sleep(0.04)
        self.assertEqual(self.arm.instance('joint').calls, 0)

    async def test_exposure_and_peer_allowlists(self):
        self.arm.remote.expose.clear()
        with self.assertRaisesRegex(RuntimeError, 'not exposed'):
            await self.controller.remote.invoke('arm','joint','move',{'position':0},'run')
        self.assertEqual(self.arm.instance('joint').calls, 0)
        with self.assertRaisesRegex(ValueError, 'undeclared'):
            await self.controller.remote.invoke('stranger','joint','move',{},'run')

    async def test_reordered_state_cannot_move_observer_backwards(self):
        for revision, state in ((3,'succeeded'),(1,'running')):
            self.controller.signals.publish('_rp.state', {'run_id':'run','revision':revision,'state':state}, correlation='run')
        await asyncio.sleep(0.04)
        self.assertEqual(next(iter(self.arm.remote.states.values()))['state'], 'succeeded')

    async def test_concurrent_correlated_waits_do_not_cross_runs(self):
        flow = {'start':'wait','nodes':{'wait':{'wait_for':'done','correlated':True,'timeout_s':0.5}}}
        first = self.controller.engine.start('first', flow)
        second = self.controller.engine.start('second', flow)
        await asyncio.sleep(0.02)
        one = self.controller.engine.runs[first]['run_id']
        two = self.controller.engine.runs[second]['run_id']
        self.arm.signals.publish('done', 2, correlation=two)
        self.assertEqual((await self.controller.tasks.wait(second))['payload'], 2)
        self.assertFalse(self.controller.tasks.records[first]['done'].is_set())
        self.arm.signals.publish('done', 1, correlation=one)
        self.assertEqual((await self.controller.tasks.wait(first))['payload'], 1)

    async def test_manifest_autostarts_distributed_flow(self):
        await self.controller.shutdown()
        self.controller = NodeRuntime.load(str(ROOT / 'TestApps/robie1/controller.json'))
        self.controller.remote.lease_ms = 150
        self.nodes['controller'] = self.controller
        await self.controller.boot()
        task = next(iter(self.controller.engine.runs))
        self.assertEqual(await asyncio.wait_for(self.controller.tasks.wait(task), 1), {'position':0.25})

    async def test_service_signals_arrive_during_remote_action(self):
        flow = self.motion_flow()
        flow['nodes']['move'].update(wait_for='joint.moved', signal_source='arm')
        task = self.controller.engine.start('observe', flow)
        result = await asyncio.wait_for(self.controller.tasks.wait(task), 1)
        self.assertEqual(result['source'], 'arm')
        self.assertEqual(result['payload'], {'position':0.5})
        self.assertIs(self.arm.instance('joint').signals, self.arm.signals)

    async def test_failed_transport_stops_application_and_blocks_unsafe_reset(self):
        rx = next(task for task, record in self.arm.tasks.records.items() if record['name']=='signals:mesh:rx')
        await self.arm.tasks.cancel(rx)
        await self.until(lambda: self.arm.state == 'failed')
        with self.assertRaisesRegex(RuntimeError, 'runtime listener stopped'):
            await self.arm.reset()
        self.assertFalse(self.arm.accepting)

    async def test_repeated_shutdown_closes_transports_once(self):
        calls = []
        transport = self.arm._signal_transports[0][1]
        original = transport.stop
        async def stop():
            calls.append('stop')
            await original()
        transport.stop = stop
        await self.arm.shutdown()
        await self.arm.shutdown()
        self.assertEqual(calls, ['stop'])
